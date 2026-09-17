from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_mcs_aind_batch import key_for, preserve_input_snapshot, refresh, submit, worker, write_json


class McsBatchTests(unittest.TestCase):
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
                run.return_value.stdout = '12345;cluster\n'
                submit(root)
                self.assertIn('--array=0-1%2', run.call_args_list[0].args[0])
                self.assertIn('--dependency=afterany:12345', run.call_args_list[1].args[0])
                with self.assertRaises(FileExistsError):
                    submit(root)
                self.assertEqual(run.call_count, 2)
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
                run.return_value.stdout = '12345_0|TIMEOUT|0:0|\n12345_1|PENDING|0:0|\n'
                summary = refresh(root, scheduler=True)
            self.assertEqual(summary['statuses'], {'failed': 1, 'submitted': 1, 'blocked': 1})

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
