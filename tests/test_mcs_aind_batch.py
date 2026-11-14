from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_mcs_aind_batch import prepare_selective_fallback, classify_failure, diagnose_batch, key_for, preserve_input_snapshot, refresh, submit, worker, write_json


class McsBatchTests(unittest.TestCase):
    def test_failure_classification_requires_training_context_and_unambiguous_counts(self):
        context = 'spikedetect.py extract_wPCA_wTEMP '
        for count in range(6):
            result = classify_failure(context + f'n_samples={count} should be >= n_clusters=6.')
            self.assertEqual(result['training_snippets'], count)
            self.assertEqual(result['fallback_eligible'], count >= 2)
        zero = classify_failure(context + 'Found array with 0 sample(s) (shape=(0, 31)) while a minimum of 1 is required by TruncatedSVD.')
        self.assertEqual(zero['training_snippets'], 0)
        for text in ('CUDA out of memory', 'n_samples=3 should be >= n_clusters=6.',
                     context + 'n_samples=3 should be >= n_clusters=6. n_samples=0 should be >= n_clusters=6.'):
            self.assertFalse(classify_failure(text)['fallback_eligible'])
        self.assertFalse(classify_failure(context + 'n_samples=3 should be >= n_clusters=8.')['fallback_eligible'])

    def test_diagnosis_preserves_historical_status_and_ledgers(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            plan = self.make_plan(root)
            row = plan['records'][0]
            row['results_dir'] = str(root / 'results')
            write_json(root / 'batch_manifest.json', plan)
            state = root / 'status' / f"{row['key']}.json"
            write_json(state, {'status': 'failed'})
            log = root / 'results/nextflow/nextflow.log'
            log.parent.mkdir(parents=True)
            log.write_text('spikedetect.py extract_wPCA_wTEMP n_samples=3 should be >= n_clusters=6.')
            before = state.read_bytes()
            report = diagnose_batch(root)
            self.assertEqual(report['failure_classes'], {'template_initialization_sparse': 1})
            self.assertEqual(state.read_bytes(), before)
            self.assertFalse((root / 'recordings.csv').exists())

    def test_scheduler_cancellation_preserves_explicit_cancellation_and_failed_attempts(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            plan = self.make_plan(root)
            write_json(root / 'submission.json', {'job_id': '12345'})
            write_json(root / 'status' / f"{plan['tasks'][0]}.json",
                       {'status': 'cancelled', 'stage': 'cancelled_before_execution', 'reason': 'user request'})
            with patch('run_mcs_aind_batch.subprocess.run') as run:
                run.return_value.returncode = 0
                run.return_value.stdout = '12345_0|CANCELLED by 42|0:0|\n12345_1|CANCELLED+|0:0|\n'
                summary = refresh(root, scheduler=True)
                self.assertIn('--array', run.call_args.args[0])
            self.assertEqual(summary['statuses'], {'cancelled': 2, 'blocked': 1})
            with (root / 'recordings.csv').open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]['stage'], 'cancelled_before_execution')
            self.assertEqual(rows[0]['reason'], 'user request')

    def test_fallback_is_isolated_preserves_calibration_and_changes_only_three_sorter_settings(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            inputs, results = root / 'inputs/standard', root / 'results/standard'
            inputs.mkdir(parents=True)
            results.mkdir(parents=True)
            (results / 'failure.txt').write_text('original failure')
            row = {'input_dir': str(inputs), 'results_dir': str(results),
                   'params_file': str(inputs / 'aind_params.json'), 'env_file': str(inputs / 'run_aind_mcs.env')}
            params = {'spikesorting': {'kilosort4': {'sorter': {
                'templates_from_data': True, 'n_templates': 6, 'n_pcs': 6, 'nearest_templates': 64,
                'Th_universal': 5, 'Th_learned': 8, 'nskip': 25, 'do_CAR': False}}},
                'job_dispatch': {'probe_paths': str(inputs / 'probeinterface.json'),
                                 'gain_to_uV': [.059605], 'offset_to_uV': 0}}
            write_json(inputs / 'aind_params.json', params)
            write_json(inputs / 'mcs_recording_manifest.json', {
                'sample_count': 1000000, 'sampling_frequency_hz': 10000, 'sorting_run_id': 'standard',
                'recording_path': 'group/condition/recording/standard', 'binary_file': '/retained/data.bin',
                'results_dir': str(results), 'gain_uv_per_count': [.059605]})
            for name in ('channels.csv', 'events.csv', 'probeinterface.json', 'source_mcs_preparation_manifest.json'):
                (inputs / name).write_text('preserved source evidence')
            (inputs / 'run_aind_mcs.env').write_text('export AIND_INPUT_MODE=spikeinterface\nexport AIND_INPUT_DIR=' + str(inputs) + '\n')
            before = {p.name: p.read_bytes() for p in inputs.iterdir()}
            diagnosis = classify_failure('spikedetect.py extract_wPCA_wTEMP n_samples=3 should be >= n_clusters=6.')
            retry = prepare_selective_fallback(row, diagnosis)
            self.assertEqual(before, {p.name: p.read_bytes() for p in inputs.iterdir()})
            changed = json.loads(Path(retry['params_file']).read_text())
            sorter = changed['spikesorting']['kilosort4']['sorter']
            self.assertEqual([sorter[k] for k in ('n_templates','nearest_templates','n_pcs')], [2,2,2])
            self.assertEqual(sorter['Th_universal'], 5)
            self.assertEqual(sorter['nskip'], 25)
            self.assertEqual(changed['job_dispatch']['gain_to_uV'], [.059605])
            self.assertEqual(changed['job_dispatch']['offset_to_uV'], 0)
            self.assertNotEqual(retry['results_dir'], row['results_dir'])
            self.assertEqual((results / 'failure.txt').read_text(), 'original failure')
            with self.assertRaises(FileExistsError):
                prepare_selective_fallback(row, diagnosis)
            with self.assertRaises(ValueError):
                prepare_selective_fallback(row, {'fallback_eligible': False, 'training_snippets': 1})

    def test_live_progress_reports_running_stage_and_records_one_shared_transition_log(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            plan = self.make_plan(root)
            row = plan['records'][0]
            row['results_dir'] = str(root / 'results')
            write_json(root / 'batch_manifest.json', plan)
            write_json(root / 'submission.json', {'job_id': '12345'})
            log = root / 'results/nextflow/trace.txt'
            log.parent.mkdir(parents=True)
            log.write_text('name\tstatus\texit\npreprocessing\tCOMPLETED\t0\n')
            with patch('run_mcs_aind_batch.subprocess.run') as run:
                run.side_effect = [SimpleNamespace(stdout='12345_0|RUNNING|0:0|\n'),
                    SimpleNamespace(returncode=0, stdout='12345_0|RUNNING|gl3009|1:23\n12345_1|PENDING|Priority|0:00\n')]
                summary = refresh(root, scheduler=True)
            self.assertEqual(summary['statuses'], {'running': 1, 'queued': 1, 'blocked': 1})
            with (root / 'recordings.csv').open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]['pipeline_completed_stages'], '1')
            self.assertEqual(rows[1]['scheduler_reason'], 'Priority')
            self.assertIn('running', (root / 'PROGRESS.txt').read_text())
            self.assertIn('pipeline=1/11', (root / 'progress.log').read_text())

    def test_input_provenance_is_never_overwritten(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            write_json(root / 'input/manifest.json', {'value': 1})
            preserve_input_snapshot(root / 'input', root / 'repro')
            preserve_input_snapshot(root / 'input', root / 'repro')
            write_json(root / 'input/new_evidence.json', {'source': 'reviewed'})
            preserve_input_snapshot(root / 'input', root / 'repro')
            self.assertTrue((root / 'repro/new_evidence.json').exists())
            write_json(root / 'input/manifest.json', {'value': 2})
            with self.assertRaisesRegex(ValueError, 'provenance differs'):
                preserve_input_snapshot(root / 'input', root / 'repro')
            self.assertEqual(json.loads((root / 'repro/manifest.json').read_text()), {'value': 1})

    def make_plan(self, root):
        ids = ['group/condition/one', 'group/condition/two', 'group/condition/missing']
        rows = [{'recording_id': value, 'key': key_for(value), 'status': 'prepared' if i < 2 else 'blocked',
                 'stage': 'ready' if i < 2 else 'preflight', 'reason': '' if i < 2 else 'Missing acquisition geometry',
                 **({'task_index': i} if i < 2 else {})} for i, value in enumerate(ids)]
        plan = {'records': rows, 'tasks': [r['key'] for r in rows[:2]], 'concurrency': 2, 'code_root': str(root / 'code')}
        write_json(root / 'batch_manifest.json', plan)
        return plan

    def test_ledger_keeps_blocked_rows_and_combines_per_recording_state(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            plan = self.make_plan(root)
            write_json(root / 'submission.json', {'job_id': '12345'})
            write_json(root / 'status' / f"{plan['tasks'][0]}.json",
                       {'status': 'completed', 'stage': 'complete', 'deleted_bytes': 1024, 'h5_cleanup_status': 'deleted'})
            summary = refresh(root)
            self.assertEqual(summary['statuses'], {'completed': 1, 'submitted': 1, 'blocked': 1})
            self.assertEqual(summary['deleted_h5_bytes'], 1024)
            with (root / 'recordings.csv').open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[2]['reason'], 'Missing acquisition geometry')

    def test_submit_is_bounded_and_refuses_duplicates_or_ambiguous_retry(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            self.make_plan(root)
            with patch('run_mcs_aind_batch.subprocess.run') as run:
                run.return_value.returncode = 0
                run.return_value.stdout = '12345;cluster\n'
                submit(root)
                self.assertIn('--array=0-1%2', run.call_args_list[0].args[0])
                self.assertIn('--dependency=afterany:12345', run.call_args_list[1].args[0])
                with self.assertRaises(FileExistsError):
                    submit(root)
                self.assertEqual(run.call_count, 3)
            (root / 'submission.json').unlink()
            with self.assertRaises(FileExistsError):
                submit(root)

    def test_scheduler_timeout_is_not_left_running(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            plan = self.make_plan(root)
            write_json(root / 'submission.json', {'job_id': '12345'})
            write_json(root / 'status' / f"{plan['tasks'][0]}.json", {'status': 'running', 'stage': 'pipeline'})
            with patch('run_mcs_aind_batch.subprocess.run') as run:
                run.return_value.returncode = 0
                run.return_value.stdout = '12345_0|TIMEOUT|0:0|\n12345_1|PENDING|0:0|\n'
                summary = refresh(root, scheduler=True)
            self.assertEqual(summary['statuses'], {'failed': 1, 'queued': 1, 'blocked': 1})

    def test_interrupted_worker_deletion_is_recovered_from_durable_ledger(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            plan = self.make_plan(root)
            row = plan['records'][0]
            row.update(source_h5=str(root / 'raw/source.h5'), results_dir=str(root / 'results'))
            write_json(root / 'batch_manifest.json', plan)
            write_json(root / 'status' / f"{row['key']}.json", {'status': 'cleanup_failed', 'stage': 'h5_cleanup'})
            identity = hashlib.sha256((row['recording_id'] + '\n' + row['source_h5']).encode()).hexdigest()
            write_json(root / 'results/repro/h5_cleanup' / identity / 'deleted.json',
                       {'status': 'deleted', 'recording_id': row['recording_id'], 'source_h5': row['source_h5'],
                        'deleted_bytes': 4096})
            summary = refresh(root)
            self.assertEqual(summary['deleted_h5_bytes'], 4096)
            self.assertEqual(summary['statuses']['cleanup_failed'], 1)
            with (root / 'recordings.csv').open() as handle:
                first = next(csv.DictReader(handle))
            self.assertEqual(first['h5_cleanup_status'], 'deleted_confirmed_from_ledger')

    def test_worker_rejects_out_of_range_before_any_processing(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            self.make_plan(root)
            with patch('run_mcs_aind_batch.subprocess.run') as run:
                with self.assertRaises(ValueError):
                    worker(root, -1)
                with self.assertRaises(ValueError):
                    worker(root, 2)
                run.assert_not_called()

    def make_worker_plan(self, root):
        plan = self.make_plan(root)
        plan.update(project_root=str(root / 'project'), delete_validated_local_h5=True,
                    allowed_h5_root=str(root / 'raw'), run_id='test_batch')
        row = plan['records'][0]
        row.update(input_dir=str(root / 'input'), results_dir=str(root / 'results'),
                   env_file=str(root / 'input/run.env'), params_file=str(root / 'input/params.json'),
                   source_h5=str(root / 'raw/one.h5'), reuse_completed=False)
        (root / 'status').mkdir()
        write_json(root / 'batch_manifest.json', plan)
        return row

    def test_pipeline_failure_never_calls_cleanup(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            row = self.make_worker_plan(root)
            with patch('run_mcs_aind_batch.subprocess.run',
                       side_effect=subprocess.CalledProcessError(1, 'pipeline')) as run:
                self.assertEqual(worker(root, 0), 1)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0][0], 'bash')
            state = json.loads((root / 'status' / f"{row['key']}.json").read_text())
            self.assertEqual(state['status'], 'failed')
            self.assertEqual(state['stage'], 'pipeline')

    def test_incomplete_pipeline_never_finalizes_or_deletes(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            row = self.make_worker_plan(root)
            (root / 'results/nextflow').mkdir(parents=True)
            (root / 'results/nextflow/trace.txt').write_text('name\tstatus\texit\nspikesort_kilosort4\tCOMPLETED\t0\n')
            with patch('run_mcs_aind_batch.subprocess.run') as run:
                self.assertEqual(worker(root, 0), 1)
                self.assertEqual(run.call_count, 1)
            state = json.loads((root / 'status' / f"{row['key']}.json").read_text())
            self.assertIn('11 AIND stages', state['reason'])

    def prepare_worker_outputs(self, root):
        row = self.make_worker_plan(root)
        (root / 'results/nextflow').mkdir(parents=True)
        stages = ['job_dispatch', 'preprocessing', 'nwb_ecephys', 'spikesort_kilosort4', 'postprocessing',
                  'curation', 'visualization', 'results_collector', 'quality_control', 'nwb_units',
                  'quality_control_collector']
        (root / 'results/nextflow/trace.txt').write_text(
            'name\tstatus\texit\n' + ''.join(f'{stage}\tCOMPLETED\t0\n' for stage in stages))
        write_json(root / 'input/mcs_recording_manifest.json',
                   {'sorting_run_id': 'test_batch', 'binary_file': str(root / 'signal.bin')})
        for name in ('channels.csv', 'events.csv'):
            (root / 'input' / name).write_text('test\n')
        write_json(root / 'results/durable_recording_report.json', {})
        write_json(root / 'code_sha256.json', {})
        (root / 'code/scripts').mkdir(parents=True)
        for name in ('prepare_mcs_aind_recording.py', 'finalize_mcs_aind_recording.py',
                     'finalize_mcs_aind_nwb.py', 'validate_mcs_aind_output.py', 'cleanup_mcs_h5.py'):
            (root / 'code/scripts' / name).write_text('# batch verification script\n')
        (root / 'results/repro').mkdir()
        (root / 'results/repro/finalize_mcs_aind_nwb.py').write_text('# original executed script\n')
        (root / 'raw').mkdir()
        (root / 'raw/one.h5').write_bytes(b'untouched')
        return row

    def test_worker_retries_only_eligible_failure_and_never_cleans_up_fallback(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root = Path(tmp)
            row = self.prepare_worker_outputs(root)
            plan = json.loads((root / 'batch_manifest.json').read_text())
            plan['selective_fallback'] = True
            write_json(root / 'batch_manifest.json', plan)
            (root / 'results/nextflow/nextflow.log').write_text(
                'spikedetect.py extract_wPCA_wTEMP n_samples=3 should be >= n_clusters=6.')
            retry = dict(row, results_dir=str(root / 'retry_results'), input_dir=str(root / 'retry_input'),
                         env_file=str(root / 'retry_input/run.env'), params_file=str(root / 'retry_input/params.json'))
            shutil.copytree(root / 'results', root / 'retry_results')
            shutil.copytree(root / 'input', root / 'retry_input')
            pipelines = []
            def fake_run(command, **kwargs):
                if command[0] == 'bash':
                    pipelines.append(kwargs['env']['AIND_CONFIG'])
                    if len(pipelines) == 1:
                        raise subprocess.CalledProcessError(1, command)
                elif Path(command[1]).name == 'validate_mcs_aind_output.py':
                    write_json(root / 'retry_results/validation_summary.json', {
                        'status': 'passed', 'stages': {'curated': {'unit_count': 2, 'spike_count': 10,
                                                                'kilosort_label_counts': {'mua': 2}}}})
                return SimpleNamespace(stdout='', stderr='')
            with patch('run_mcs_aind_batch.subprocess.run', side_effect=fake_run) as run, \
                 patch('run_mcs_aind_batch.prepare_selective_fallback', return_value=retry) as prepare_retry:
                self.assertEqual(worker(root, 0), 0)
                prepare_retry.assert_called_once()
                self.assertEqual(len(pipelines), 2)
                self.assertEqual(pipelines[1], retry['env_file'])
                self.assertFalse(any(len(c.args[0]) > 1 and Path(c.args[0][1]).name == 'cleanup_mcs_h5.py'
                                     for c in run.call_args_list))
            state = json.loads((root / 'status' / f"{row['key']}.json").read_text())
            self.assertTrue(state['fallback_used'])
            self.assertEqual(state['status'], 'completed')
            self.assertEqual(state['standard_training_snippets'], 3)
            self.assertEqual(state['results_dir'], retry['results_dir'])
            self.assertTrue((root / 'results/nextflow/nextflow.log').exists())

    def test_unknown_or_zero_snippet_failure_does_not_retry(self):
        for error in ('CUDA out of memory', 'spikedetect.py extract_wPCA_wTEMP Found array with 0 sample(s) while a minimum of 1 is required by TruncatedSVD.'):
            with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
                root = Path(tmp)
                row = self.make_worker_plan(root)
                plan = json.loads((root / 'batch_manifest.json').read_text())
                plan['selective_fallback'] = True
                write_json(root / 'batch_manifest.json', plan)
                log = root / 'results/nextflow/nextflow.log'
                log.parent.mkdir(parents=True)
                log.write_text(error)
                with patch('run_mcs_aind_batch.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'pipeline')) as run, \
                     patch('run_mcs_aind_batch.prepare_selective_fallback') as prepare_retry:
                    self.assertEqual(worker(root, 0), 1)
                    prepare_retry.assert_not_called()
                    self.assertEqual(run.call_count, 1)

    def test_cleanup_only_after_passing_validation_and_preserves_original_provenance(self):
        for passed in (False, True):
            with self.subTest(passed=passed), tempfile.TemporaryDirectory(dir='/tmp') as tmp:
                root = Path(tmp)
                row = self.prepare_worker_outputs(root)

                def fake_run(command, **kwargs):
                    if Path(command[1]).name == 'validate_mcs_aind_output.py':
                        write_json(root / 'results/validation_summary.json',
                                   {'status': 'passed' if passed else 'failed',
                                    'stages': {'curated': {'unit_count': 2, 'spike_count': 100,
                                                          'kilosort_label_counts': {'mua': 2}}}})
                    payload = {'status': 'deleted', 'deleted_bytes': 9, 'ledger': '/deletion/proof'}
                    return SimpleNamespace(stdout=json.dumps(payload), stderr='')

                with patch('run_mcs_aind_batch.subprocess.run', side_effect=fake_run) as run:
                    self.assertEqual(worker(root, 0), 0 if passed else 1)
                    cleanup_calls = [c for c in run.call_args_list if Path(c.args[0][1]).name == 'cleanup_mcs_h5.py']
                    self.assertEqual(len(cleanup_calls), 1 if passed else 0)
                state = json.loads((root / 'status' / f"{row['key']}.json").read_text())
                self.assertEqual(state['status'], 'completed' if passed else 'failed')
                self.assertEqual((root / 'results/repro/finalize_mcs_aind_nwb.py').read_text(),
                                 '# original executed script\n')
                self.assertEqual((root / 'raw/one.h5').read_bytes(), b'untouched')


if __name__ == '__main__':
    unittest.main()
