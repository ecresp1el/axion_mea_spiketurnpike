#!/usr/bin/env python3
"""Prepare, submit and track bounded single-MEA AIND jobs and validated H5 cleanup."""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = Path('/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder')
DEFAULT_RAW = Path('/nfs/turbo/umms-parent/mea_multichannel_project/raw_data')


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix=path.name + '.', delete=False) as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.replace(path)


def key_for(recording_id: str) -> str:
    return hashlib.sha256(recording_id.encode()).hexdigest()[:20]


def snapshot_code(destination: Path) -> None:
    scripts = ['run_mcs_aind_batch.py', 'prepare_mcs_aind_recording.py',
               'validate_mcs_aind_output.py', 'finalize_mcs_aind_recording.py',
               'finalize_mcs_aind_nwb.py', 'cleanup_mcs_h5.py', 'monitor_aind_run.sh']
    for directory in ('scripts', 'slurm', 'config'):
        (destination / directory).mkdir(parents=True)
    for name in scripts:
        shutil.copy2(ROOT / 'scripts' / name, destination / 'scripts' / name)
    for name in ('run_mcs_aind_batch.sbatch', 'run_aind_nwb_well.sbatch'):
        shutil.copy2(ROOT / 'slurm' / name, destination / 'slurm' / name)
    for name in ('greatlakes_project.env', 'aind_mcs_nextflow_slurm.config',
                 'aind_nextflow_slurm_greatlakes.config',
                 'aind_axion_cytoview6_params_th5_kilosort_preproc_DRAFT.json'):
        shutil.copy2(ROOT / 'config' / name, destination / 'config' / name)
    shutil.copytree(ROOT / 'src', destination / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    hashes = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in destination.rglob('*') if p.is_file()}
    write_json(destination.parent / 'code_sha256.json', hashes)


def completed_run(project: Path, recording_id: str) -> dict | None:
    from prepare_mcs_aind_recording import slug
    parent = project / 'results/aind_mcs' / Path(*(slug(p) for p in Path(recording_id).parts))
    candidates = []
    for report_path in parent.glob('*/validation_summary.json'):
        report = read_json(report_path)
        input_path = Path(report.get('input', {}).get('manifest', '')).parent
        if not (input_path / 'mcs_recording_manifest.json').is_file():
            continue
        manifest = read_json(input_path / 'mcs_recording_manifest.json')
        result = report_path.parent
        if (report.get('status') == 'passed' and manifest.get('recording_id') == recording_id
                and Path(manifest['results_dir']).resolve() == result.resolve()
                and (result / 'durable_recording_report.json').is_file()
                and (result / 'repro/nwb_finalization_report.json').is_file()):
            candidates.append({'input_dir': str(input_path), 'results_dir': str(result),
                               'env_file': str(input_path / 'run_aind_mcs.env'),
                               'params_file': str(input_path / 'aind_params.json'),
                               'run_id': manifest['sorting_run_id'], 'reuse_completed': True})
    if len(candidates) > 1:
        raise ValueError(f'Multiple completed runs for {recording_id}; choose explicitly before cleanup')
    return candidates[0] if candidates else None


def prepare_batch(source_index: Path, batch_dir: Path, project: Path, run_id: str,
                  concurrency: int, delete_h5: bool) -> dict:
    from prepare_mcs_aind_recording import prepare
    if concurrency not in range(1, 5):
        raise ValueError('Use 1-4 concurrent parent jobs to leave room for nested AIND tasks')
    if batch_dir.exists():
        raise FileExistsError('Batch already exists; use status/submit on its saved manifest')
    index = read_json(source_index)
    sources = index['records']
    ids = [row['recording_id'] for row in sources]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate recording identities in source index')
    batch_dir.mkdir(parents=True)
    code = batch_dir / 'code'
    snapshot_code(code)
    shutil.copy2(source_index, batch_dir / 'source_index.json')
    (batch_dir / 'status').mkdir()
    (batch_dir / 'logs').mkdir()
    template = code / 'config/aind_axion_cytoview6_params_th5_kilosort_preproc_DRAFT.json'
    records, tasks = [], []
    for source in sources:
        row = dict(source, key=key_for(source['recording_id']))
        row['status'] = 'blocked'
        row['stage'] = 'preflight'
        try:
            existing = completed_run(project, row['recording_id'])
            if existing:
                row.update(existing)
            elif source['status'] == 'ready':
                options = {}
                if not source.get('source_xml') and source.get('source_msrd'):
                    options['source_msrd'] = Path(source['source_msrd'])
                prepared = prepare(Path(source['input_dir']),
                                   Path(source['source_xml']) if source.get('source_xml') else None,
                                   project, run_id, template, **options)
                row.update(prepared, reuse_completed=False)
                with Path(row['env_file']).open('a') as handle:
                    for name, value in {'REPO_ROOT': code, 'PROJECT_CONFIG': code / 'config/greatlakes_project.env',
                                        'AIND_SLURM_CONFIG': code / 'config/aind_mcs_nextflow_slurm.config'}.items():
                        handle.write(f'export {name}={shlex.quote(str(value))}\n')
            else:
                records.append(row)
                continue
            evidence = source.get('source_time_evidence_json')
            if evidence and Path(evidence).is_file():
                target = Path(row['input_dir']) / 'source_time_evidence.json'
                if not target.exists():
                    shutil.copy2(evidence, target)
                row['source_time_evidence_json'] = str(target)
            row.update(status='prepared', stage='ready', reason='', task_index=len(tasks))
            tasks.append(row['key'])
        except Exception as exc:
            row.update(status='blocked', reason=f'{type(exc).__name__}: {exc}')
        records.append(row)
    eligible = sorted((row for row in records if row['status'] == 'prepared'),
                      key=lambda row: (not row.get('reuse_completed'), row.get('channel_count') != 60,
                                       not bool(row.get('source_h5')), row['recording_id']))
    tasks = []
    for row in eligible:
        row['task_index'] = len(tasks)
        tasks.append(row['key'])
    plan = {'schema_version': 1, 'created_utc': now(), 'project_root': str(project),
            'run_id': run_id, 'batch_dir': str(batch_dir), 'code_root': str(code),
            'source_index': str(source_index), 'concurrency': concurrency,
            'delete_validated_local_h5': delete_h5, 'allowed_h5_root': str(DEFAULT_RAW),
            'backup_status': 'User reports source copies are backed up elsewhere; backup storage not independently inspected.',
            'records': records, 'tasks': tasks}
    write_json(batch_dir / 'batch_manifest.json', plan)
    return refresh(batch_dir)


def refresh(batch_dir: Path, scheduler: bool = False) -> dict:
    plan = read_json(batch_dir / 'batch_manifest.json')
    scheduled = {}
    submission_path = batch_dir / 'submission.json'
    submission = read_json(submission_path) if submission_path.exists() else {}
    if scheduler and submission.get('job_id'):
        result = subprocess.run(['sacct', '-j', submission['job_id'], '--format=JobID,State,ExitCode',
                                 '--parsable2', '--noheader'], check=True, text=True, capture_output=True)
        scheduled = {parts[0]: parts[1:] for line in result.stdout.splitlines()
                     if len(parts := line.split('|')) >= 3 and '.' not in parts[0]}
    fields = ['recording_id', 'status', 'stage', 'reason', 'task_index', 'array_job_id', 'job_id',
              'scheduler_state', 'scheduler_exit', 'results_dir', 'input_dir', 'source_h5',
              'source_xml', 'source_msrd', 'source_time_evidence_json', 'reuse_completed',
              'duration_s', 'channel_count', 'configured_mea_name', 'pitch_um', 'cleanup_note', 'rejected_h5',
              'unit_count', 'spike_count', 'kilosort_label_counts', 'h5_cleanup_status',
              'deleted_bytes', 'h5_cleanup_ledger', 'updated_utc']
    with (batch_dir / 'ledger.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = []
        for item in plan['records']:
            row = dict(item)
            status_path = batch_dir / 'status' / f"{item['key']}.json"
            if status_path.exists():
                row.update(read_json(status_path))
            elif item.get('task_index') is not None and submission.get('job_id'):
                row.update(status='submitted', array_job_id=submission['job_id'])
            scheduler_key = f"{submission.get('job_id')}_{item.get('task_index')}"
            if scheduler_key in scheduled:
                state, exit_code = scheduled[scheduler_key][:2]
                row.update(scheduler_state=state, scheduler_exit=exit_code)
                if state.split()[0] in {'FAILED', 'TIMEOUT', 'CANCELLED', 'OUT_OF_MEMORY', 'NODE_FAIL', 'PREEMPTED'}:
                    if row['status'] not in {'failed', 'cleanup_failed', 'completed'}:
                        row.update(status='failed', reason=f'Scheduler {state} exit {exit_code}; input retained')
                elif state == 'COMPLETED' and row['status'] not in {'completed', 'cleanup_failed', 'failed'}:
                    row.update(status='failed', reason='Job ended without a validated completion record; input retained')
            rows.append({name: row.get(name, '') for name in fields})
        summary = {'updated_utc': now(), 'recordings': len(rows), 'tasks': len(plan['tasks']),
                   'concurrency': plan['concurrency'], 'statuses': dict(Counter(row['status'] for row in rows)),
                   'deleted_h5_bytes': sum(int(row.get('deleted_bytes') or 0) for row in rows),
                   'array_job_id': submission.get('job_id'), 'ledger': str(batch_dir / 'recordings.csv')}
        with tempfile.NamedTemporaryFile(mode='w', newline='', dir=batch_dir, delete=False) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        temporary.replace(batch_dir / 'recordings.csv')
        write_json(batch_dir / 'summary.json', summary)
    return summary


def submit(batch_dir: Path) -> dict:
    plan = read_json(batch_dir / 'batch_manifest.json')
    with (batch_dir / 'submit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (batch_dir / 'submission.json').exists():
            raise FileExistsError('Batch has already been submitted; refusing duplicate processing or cleanup')
        if (batch_dir / 'submission_intent.json').exists():
            raise FileExistsError('An earlier submission attempt needs scheduler reconciliation before retrying')
        if not plan['tasks']:
            raise ValueError('No eligible tasks in this batch')
        command = ['sbatch', '--parsable', f"--array=0-{len(plan['tasks'])-1}%{plan['concurrency']}",
                   f'--output={batch_dir}/logs/mcs-%A_%a.out', f'--error={batch_dir}/logs/mcs-%A_%a.err',
                   f'--export=ALL,MCS_BATCH_DIR={batch_dir}', str(Path(plan['code_root']) / 'slurm/run_mcs_aind_batch.sbatch')]
        write_json(batch_dir / 'submission_intent.json', {'command': command, 'created_utc': now()})
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        job_id = result.stdout.strip().split(';')[0]
        if not job_id.isdigit():
            raise ValueError(f'Unexpected sbatch response: {result.stdout!r}; inspect scheduler before any resubmission')
        submission = {'job_id': job_id, 'command': command, 'submitted_utc': now()}
        write_json(batch_dir / 'submission.json', submission)
        collector = ['sbatch', '--parsable', f'--dependency=afterany:{job_id}', '--job-name=mcs-ledger',
                     '--cpus-per-task=1', '--mem=2G', '--time=00:05:00',
                     f'--output={batch_dir}/logs/summary-%j.out', f'--error={batch_dir}/logs/summary-%j.err',
                     f'--export=ALL,MCS_BATCH_DIR={batch_dir},MCS_BATCH_SUMMARY_ONLY=1',
                     str(Path(plan['code_root']) / 'slurm/run_mcs_aind_batch.sbatch')]
        try:
            collected = subprocess.run(collector, check=True, text=True, capture_output=True)
            submission['summary_job_id'] = collected.stdout.strip().split(';')[0]
            submission['summary_command'] = collector
        except subprocess.CalledProcessError as exc:
            submission['summary_submission_error'] = exc.stderr
        write_json(batch_dir / 'submission.json', submission)
    return refresh(batch_dir)


def worker(batch_dir: Path, task_index: int) -> int:
    plan = read_json(batch_dir / 'batch_manifest.json')
    if task_index < 0 or task_index >= len(plan['tasks']):
        raise ValueError('Array task index outside prepared task list')
    key = plan['tasks'][task_index]
    row = next(item for item in plan['records'] if item['key'] == key)
    state = {name: row.get(name) for name in ('recording_id', 'input_dir', 'results_dir', 'task_index')}
    state.update(job_id=os.environ.get('SLURM_JOB_ID'), array_job_id=os.environ.get('SLURM_ARRAY_JOB_ID'))
    state_path = batch_dir / 'status' / f'{key}.json'
    code = Path(plan['code_root'])
    python = str(Path(plan['project_root']) / 'envs/axion-kilosort/bin/python')
    results, inputs = Path(row['results_dir']), Path(row['input_dir'])
    environment = os.environ | {'AIND_CONFIG': row['env_file'], 'REPO_ROOT': str(code),
                                'PROJECT_CONFIG': str(code / 'config/greatlakes_project.env')}

    def update(stage, status='running', **extra):
        state.update(stage=stage, status=status, updated_utc=now(), **extra)
        write_json(state_path, state)
        refresh(batch_dir)

    def run(name, arguments, capture=False):
        command = [python, str(code / 'scripts' / name), *map(str, arguments)]
        print(shlex.join(command), flush=True)
        result = subprocess.run(command, check=True, env=environment, text=True, capture_output=capture)
        if capture:
            print(result.stdout, flush=True)
            if result.stderr:
                print(result.stderr, file=sys.stderr, flush=True)
        return result

    with (batch_dir / 'status' / f'{key}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if state_path.exists() and read_json(state_path).get('status') == 'completed':
            raise ValueError('Recording already completed; refusing duplicate work')
        try:
            update('pipeline')
            if not row.get('reuse_completed'):
                subprocess.run(['bash', str(code / 'slurm/run_aind_nwb_well.sbatch')],
                               check=True, env=environment, cwd=code)
            trace = list(csv.DictReader((results / 'nextflow/trace.txt').open(), delimiter='\t'))
            if len(trace) != 11 or any(r['status'] != 'COMPLETED' or r['exit'] != '0' for r in trace):
                raise ValueError('Expected all 11 AIND stages to complete successfully before finalization')
            repro = results / 'repro'
            repro.mkdir(exist_ok=True)
            shutil.copytree(inputs, repro / 'mcs_input', dirs_exist_ok=True)
            for name in ('events.csv', 'channels.csv'):
                shutil.copy2(inputs / name, results / name)
            for name in ('prepare_mcs_aind_recording.py', 'finalize_mcs_aind_recording.py',
                         'finalize_mcs_aind_nwb.py', 'validate_mcs_aind_output.py', 'cleanup_mcs_h5.py'):
                shutil.copy2(code / 'scripts' / name, repro / name)
            manifest = read_json(inputs / 'mcs_recording_manifest.json')
            update('durable_recording')
            if not (results / 'durable_recording_report.json').exists():
                run('finalize_mcs_aind_recording.py', ['--results-dir', results, '--source-binary', manifest['binary_file']])
            update('nwb_finalization')
            args = ['--results-dir', results, '--input-dir', inputs, '--apply']
            if row.get('source_h5') and Path(row['source_h5']).is_file():
                args += ['--source-h5', row['source_h5']]
            if row.get('source_time_evidence_json'):
                args += ['--source-time-evidence', row['source_time_evidence_json']]
            run('finalize_mcs_aind_nwb.py', args)
            update('validation')
            run('validate_mcs_aind_output.py', ['--results-dir', results, '--input-dir', inputs,
                                             '--params-file', row['params_file']])
            validation = read_json(results / 'validation_summary.json')
            if validation['status'] != 'passed':
                raise ValueError('Independent validation did not pass; H5 retained')
            stats = validation['stages']['curated']
            update('validated', unit_count=stats['unit_count'], spike_count=stats['spike_count'],
                   kilosort_label_counts=stats['kilosort_label_counts'])
            if plan['delete_validated_local_h5'] and row.get('source_h5'):
                update('h5_cleanup')
                cleaned = run('cleanup_mcs_h5.py', ['--results-dir', results, '--input-dir', inputs,
                              '--source-h5', row['source_h5'], '--allowed-root', plan['allowed_h5_root'], '--apply'], capture=True)
                cleanup = json.loads(cleaned.stdout)
                if cleanup.get('status') not in {'deleted', 'already_deleted'}:
                    raise ValueError('Cleanup did not return a verified deletion result')
                update('complete', 'completed', h5_cleanup_status=cleanup['status'],
                       deleted_bytes=int(cleanup['deleted_bytes']), h5_cleanup_ledger=cleanup['ledger'])
            else:
                cleanup_status = 'retained_rejected_h5' if row.get('rejected_h5') else 'no_local_h5'
                update('complete', 'completed', h5_cleanup_status=cleanup_status if not row.get('source_h5') else 'retained', deleted_bytes=0)
            return 0
        except Exception as exc:
            cleanup_failed = state.get('stage') == 'h5_cleanup'
            update(state.get('stage', 'unknown'), 'cleanup_failed' if cleanup_failed else 'failed',
                   reason=f'{type(exc).__name__}: {exc}', h5_cleanup_status='not_deleted_or_check_deletion_ledger')
            print(state['reason'], file=sys.stderr, flush=True)
            return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('prepare')
    p.add_argument('--source-index', type=Path, required=True)
    p.add_argument('--batch-dir', type=Path, required=True)
    p.add_argument('--project-root', type=Path, default=DEFAULT_PROJECT)
    p.add_argument('--run-id', required=True)
    p.add_argument('--concurrency', type=int, default=2)
    p.add_argument('--delete-validated-h5', action='store_true')
    for name in ('submit', 'status', 'worker'):
        p = commands.add_parser(name)
        p.add_argument('--batch-dir', type=Path, required=True)
        if name == 'worker':
            p.add_argument('--task-index', type=int, required=True)
        if name == 'status':
            p.add_argument('--scheduler', action='store_true')
    args = parser.parse_args()
    batch = args.batch_dir.expanduser().resolve()
    if args.command == 'prepare':
        result = prepare_batch(args.source_index.resolve(), batch, args.project_root.resolve(),
                               args.run_id, args.concurrency, args.delete_validated_h5)
    elif args.command == 'submit':
        result = submit(batch)
    elif args.command == 'status':
        result = refresh(batch, args.scheduler)
    else:
        return worker(batch, args.task_index)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
