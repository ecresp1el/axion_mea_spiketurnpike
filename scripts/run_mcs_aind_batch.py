#!/usr/bin/env python3
"""Prepare, submit and track bounded single-MEA AIND jobs and validated H5 cleanup."""
from __future__ import annotations

import argparse
import csv
import copy
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
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


def preserve_input_snapshot(inputs: Path, destination: Path) -> None:
    for source in inputs.rglob('*'):
        target = destination / source.relative_to(inputs)
        if source.is_file():
            if target.exists():
                if target.read_bytes() != source.read_bytes():
                    raise ValueError(f'Saved input provenance differs from current input: {target}')
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)


def snapshot_code(destination: Path) -> None:
    scripts = ['run_mcs_aind_batch.py', 'audit_mcs_batch_sources.py', 'recover_mcs_msrd_prefix.py',
               'prepare_mcs_aind_recording.py',
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
    for name, arguments in (('source_git_commit.txt', ['rev-parse', 'HEAD']),
                            ('source_git_status.txt', ['status', '--short'])):
        provenance = subprocess.run(['git', '-C', str(ROOT), *arguments],
                                    check=True, text=True, capture_output=True)
        (destination / name).write_text(provenance.stdout)
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
                  concurrency: int, delete_h5: bool, *, allow_staged_geometry: bool = False,
                  allow_short_recordings: bool = False, selective_fallback: bool = False,
                  minimum_duration_seconds: float = 0) -> dict:
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
            if float(row['duration_s']) < minimum_duration_seconds:
                raise ValueError(f'Recording below {minimum_duration_seconds:g} second inclusion cutoff')
            existing = completed_run(project, row['recording_id'])
            if existing:
                row.update(existing)
            elif source['status'] == 'ready':
                options = {'allow_staged_geometry': allow_staged_geometry,
                           'allow_short_recording': allow_short_recordings}
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
            manifest = read_json(Path(row['input_dir']) / 'mcs_recording_manifest.json')
            row.update(geometry_status=manifest.get('geometry_status', 'source_verified'),
                       sorting_pitch_um=manifest.get('sorting_pitch_um', manifest.get('pitch_um')),
                       short_recording_policy=manifest.get('short_recording_policy', 'standard_duration'),
                       source_review_warning=manifest.get('source_review_warning'),
                       recording_completeness=manifest.get('recording_completeness', 'complete_staged_recording'),
                       recovery_report=manifest.get('recovery_report'),
                       configured_mea_name=manifest.get('configured_mea_name'), pitch_um=manifest.get('pitch_um'))
            if (row['geometry_status'] != 'source_verified' or not manifest.get('source_h5_cleanup_allowed', True)) and row.get('source_h5'):
                row['retained_h5_cleanup_disabled'] = row.pop('source_h5')
                row['cleanup_note'] = 'H5 retained: preparation explicitly disallows source cleanup'
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
    # Exercise completed reuse, verified geometry, unknown geometry and a short input early.
    first = [row for row in eligible if row.get('reuse_completed')]
    for predicate in (
            lambda row: not row.get('reuse_completed') and row['geometry_status'] == 'source_verified',
            lambda row: row['geometry_status'] == 'staged_unverified' and row['duration_s'] >= 30,
            lambda row: row['duration_s'] < 30):
        representative = next((row for row in eligible if predicate(row)), None)
        if representative and representative not in first:
            first.append(representative)
    eligible = first + [row for row in eligible if row not in first]
    tasks = []
    for row in eligible:
        row['task_index'] = len(tasks)
        tasks.append(row['key'])
    plan = {'schema_version': 1, 'created_utc': now(), 'project_root': str(project),
            'run_id': run_id, 'batch_dir': str(batch_dir), 'code_root': str(code),
            'source_index': str(source_index), 'concurrency': concurrency,
            'delete_validated_local_h5': delete_h5, 'allowed_h5_root': str(DEFAULT_RAW),
            'selective_fallback': selective_fallback, 'minimum_duration_seconds': minimum_duration_seconds,
            'allow_staged_geometry': allow_staged_geometry, 'allow_short_recordings': allow_short_recordings,
            'backup_status': 'User reports source copies are backed up elsewhere; backup storage not independently inspected.',
            'records': records, 'tasks': tasks}
    write_json(batch_dir / 'batch_manifest.json', plan)
    return refresh(batch_dir)


def classify_failure(text: str) -> dict:
    """Recognize only demonstrated KS4 training failures; unknown errors stay unknown."""
    result = {'failure_class': 'unclassified', 'training_snippets': None,
              'fallback_eligible': False, 'failure_evidence': ''}
    if 'extract_wPCA_wTEMP' not in text or 'spikedetect.py' not in text:
        return result
    counts = set(re.findall(r'n_samples=(\d+) should be >= n_clusters=(\d+)', text))
    zero = re.search(r'Found array with 0 sample\(s\).*?TruncatedSVD', text)
    if zero and not counts:
        result.update(failure_class='template_training_insufficient', training_snippets=0,
                      failure_evidence=zero.group(0))
        return result
    if zero:
        return result
    if len(counts) != 1:
        return result  # Conflicting attempts must be reviewed, never automatically retried.
    samples, templates = map(int, next(iter(counts)))
    eligible = templates == 6 and 2 <= samples <= 5
    result.update(failure_class='template_training_insufficient' if samples < 2 else
                  'template_initialization_sparse', training_snippets=samples,
                  fallback_eligible=eligible,
                  failure_evidence=zero.group(0) if zero else
                  f'n_samples={samples} should be >= n_clusters={templates}')
    return result


def diagnose_recording(row: dict) -> dict:
    log = Path(row.get('results_dir') or '.') / 'nextflow/nextflow.log'
    try:
        text = log.read_text(errors='replace') if row.get('results_dir') and log.is_file() else ''
    except OSError as exc:
        result = classify_failure('')
        result['failure_evidence'] = f'Cannot read diagnostic log: {exc}'
    else:
        result = classify_failure(text)
    result['failure_log'] = str(log) if row.get('results_dir') else ''
    return result


def diagnose_batch(batch_dir: Path) -> dict:
    """Read historical evidence without changing its status files or ledgers."""
    plan = read_json(batch_dir / 'batch_manifest.json')
    records = []
    for item in plan['records']:
        row = dict(item)
        status = batch_dir / 'status' / f"{item['key']}.json"
        if status.exists():
            row.update(read_json(status))
        record = {k: row.get(k) for k in ('recording_id', 'task_index', 'status', 'stage',
                                         'reason', 'duration_s', 'results_dir')}
        if row['status'] == 'failed':
            record.update(diagnose_recording(row))
        records.append(record)
    return {'batch_dir': str(batch_dir), 'records': records,
            'failure_classes': dict(Counter(r['failure_class'] for r in records if 'failure_class' in r)),
            'note': 'Attempt-level evidence; a failed baseline may have a successful separate retry.'}


def prepare_selective_fallback(row: dict, diagnosis: dict) -> dict:
    """Create a separate attempt; preserve every baseline file and all other settings."""
    if not diagnosis.get('fallback_eligible') or diagnosis.get('training_snippets') not in range(2, 6):
        raise ValueError('Selective fallback requires 2-5 observed training snippets')
    old_input, old_result = Path(row['input_dir']), Path(row['results_dir'])
    manifest = read_json(old_input / 'mcs_recording_manifest.json')
    if manifest['sample_count'] / manifest['sampling_frequency_hz'] < 60:
        raise ValueError('Recordings under one minute are excluded')
    params = read_json(Path(row['params_file']))
    sorter = params['spikesorting']['kilosort4']['sorter']
    if not (sorter.get('templates_from_data') is True and sorter.get('n_templates') == 6
            and sorter.get('n_pcs') == 6 and sorter.get('nearest_templates') == 64):
        raise ValueError('Fallback requires the unchanged standard six-component profile')
    if sorter.get('Th_universal') != 5 or sorter.get('Th_learned') != 8:
        raise ValueError('Fallback requires the established TH5 profile')
    new_run = manifest['sorting_run_id'] + '_nt2_npcs2'
    new_input, new_result = old_input.with_name(new_run), old_result.with_name(new_run)
    if new_input.exists() or new_result.exists():
        raise FileExistsError('Separate fallback attempt already exists; refusing duplicate execution')
    shutil.copytree(old_input, new_input)

    def relocate(value):
        if isinstance(value, dict):
            return {k: relocate(v) for k, v in value.items()}
        if isinstance(value, list):
            return [relocate(v) for v in value]
        if isinstance(value, str):
            for old, new in ((old_input, new_input), (old_result, new_result)):
                if value == str(old) or value.startswith(str(old) + '/'):
                    return str(new) + value[len(str(old)):]
        return value

    changed = relocate(params)
    changed['spikesorting']['kilosort4']['sorter'].update(
        n_templates=2, nearest_templates=2, n_pcs=2)
    # Normalize intended differences and prove that every other parameter is identical.
    check = copy.deepcopy(changed)
    check['spikesorting']['kilosort4']['sorter'].update(
        **{k: sorter[k] for k in ('n_templates', 'nearest_templates', 'n_pcs')})
    if check != relocate(params):
        raise ValueError('Unexpected fallback parameter changes')
    write_json(new_input / 'aind_params.json', changed)
    updated = relocate(manifest)
    updated.update(sorting_run_id=new_run,
                   recording_path=str(Path(manifest['recording_path']).with_name(new_run)),
                   prepared_utc=now(), source_h5_cleanup_allowed=False,
                   fallback_provenance={'standard_results_dir': str(old_result),
                       'standard_input_dir': str(old_input), 'diagnosis': diagnosis,
                       'changed_sorter_settings': {'n_templates': 2, 'nearest_templates': 2, 'n_pcs': 2}})
    write_json(new_input / 'mcs_recording_manifest.json', updated)
    env = {}
    for line in Path(row['env_file']).read_text().splitlines():
        if line.startswith('export '):
            name, value = shlex.split(line[7:])[0].split('=', 1)
            env[name] = value
    env.update(AIND_INPUT_DIR=str(new_input), AIND_PARAMS_FILE=str(new_input / 'aind_params.json'),
               AIND_RECORDING_PATH=updated['recording_path'])
    env_file = new_input / 'run_aind_mcs.env'
    env_file.write_text(''.join(f'export {k}={shlex.quote(v)}\n' for k, v in env.items()))
    for name in ('channels.csv', 'events.csv', 'probeinterface.json', 'source_mcs_preparation_manifest.json'):
        if (old_input / name).read_bytes() != (new_input / name).read_bytes():
            raise ValueError(f'Fallback changed preserved input: {name}')
    write_json(new_input / 'fallback_preflight.json', {
        'status': 'passed', 'standard_results_dir': str(old_result),
        'sorter_changes': {k: [sorter[k], 2] for k in ('n_templates', 'nearest_templates', 'n_pcs')},
        'channels_events_probe_source_unchanged': True, 'h5_cleanup_enabled': False})
    result = dict(row, input_dir=str(new_input), results_dir=str(new_result),
                  params_file=str(new_input / 'aind_params.json'), env_file=str(env_file), run_id=new_run)
    if row.get('source_time_evidence_json'):
        result['source_time_evidence_json'] = str(new_input / 'source_time_evidence.json')
    return result


def watch(batch_dir: Path, interval: int = 20) -> int:
    """Continuously publish one shared ledger, progress page, and transition log."""
    terminal = {'completed', 'failed', 'cleanup_failed', 'cancelled', 'blocked'}
    while True:
        try:
            summary = refresh(batch_dir, scheduler=True)
            print(f"[{now()}] {json.dumps(summary['statuses'], sort_keys=True)} "
                  f"finished={summary['finished']}/{summary['recordings']}", flush=True)
            if summary['array_job_id'] and set(summary['statuses']) <= terminal:
                return 0
        except (OSError, subprocess.SubprocessError) as exc:
            print(f'[{now()}] Monitor refresh error; retrying: {exc}', file=sys.stderr, flush=True)
        time.sleep(max(10, interval))


def refresh(batch_dir: Path, scheduler: bool = False) -> dict:
    plan = read_json(batch_dir / 'batch_manifest.json')
    scheduled = {}
    submission_path = batch_dir / 'submission.json'
    submission = read_json(submission_path) if submission_path.exists() else {}
    if scheduler and submission.get('job_id'):
        result = subprocess.run(['sacct', '--array', '-j', submission['job_id'], '--format=JobID%40,State%30,ExitCode',
                                 '--parsable2', '--noheader'], check=True, text=True, capture_output=True)
        scheduled = {parts[0]: parts[1:] for line in result.stdout.splitlines()
                     if len(parts := line.split('|')) >= 3 and '.' not in parts[0]}
    live = {}
    if scheduler and submission.get('job_id'):
        queued = subprocess.run(['squeue', '--array', '--noheader', '-j', submission['job_id'],
                                 '--format=%i|%T|%R|%M'], text=True, capture_output=True)
        if queued.returncode and 'Invalid job id' not in queued.stderr:
            raise subprocess.CalledProcessError(queued.returncode, queued.args, queued.stdout, queued.stderr)
        live = {p[0]: p[1:] for line in queued.stdout.splitlines()
                if len(p := line.strip().split('|')) >= 4}
    fields = ['recording_id', 'status', 'stage', 'reason', 'task_index', 'array_job_id', 'job_id',
              'scheduler_state', 'scheduler_exit', 'scheduler_reason', 'scheduler_elapsed',
              'started_utc', 'finished_utc', 'attempt_profile', 'fallback_used',
              'standard_results_dir', 'standard_input_dir', 'standard_failure_class', 'standard_training_snippets',
              'pipeline_completed_stages', 'pipeline_failed_stages', 'failure_class', 'training_snippets',
              'fallback_eligible', 'failure_evidence', 'failure_log', 'results_dir', 'input_dir', 'source_h5',
              'source_xml', 'source_msrd', 'source_time_evidence_json', 'reuse_completed',
              'duration_s', 'channel_count', 'configured_mea_name', 'pitch_um', 'cleanup_note', 'rejected_h5',
              'geometry_status', 'sorting_pitch_um', 'short_recording_policy', 'source_review_warning',
              'retained_h5_cleanup_disabled',
              'recording_completeness', 'recovery_report',
              'unit_count', 'spike_count', 'kilosort_label_counts', 'h5_cleanup_status',
              'deleted_bytes', 'h5_cleanup_ledger', 'updated_utc']
    with (batch_dir / 'ledger.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous_path = batch_dir / 'recordings.csv'
        if previous_path.exists():
            with previous_path.open() as handle:
                previous = {r['recording_id']: r for r in csv.DictReader(handle)}
        else:
            previous = {}
        rows = []
        for item in plan['records']:
            row = dict(item)
            status_path = batch_dir / 'status' / f"{item['key']}.json"
            if status_path.exists():
                row.update(read_json(status_path))
            elif item.get('task_index') is not None and submission.get('job_id'):
                row.update(status='submitted', array_job_id=submission['job_id'])
            if not scheduler:
                old = previous.get(row['recording_id'], {})
                for name in ('scheduler_state', 'scheduler_exit', 'scheduler_reason', 'scheduler_elapsed'):
                    if old.get(name):
                        row[name] = old[name]
                if row['status'] in {'submitted', 'prepared'} and old.get('status') in {'queued', 'running'}:
                    row['status'] = old['status']
                if row['status'] in {'submitted', 'prepared', 'running'} and old.get('status') in {'failed', 'cancelled'}:
                    for name in ('status', 'reason', 'failure_class'):
                        row[name] = old.get(name, row.get(name, ''))
            scheduler_key = f"{submission.get('job_id')}_{item.get('task_index')}"
            if scheduler_key in scheduled:
                state, exit_code = scheduled[scheduler_key][:2]
                row.update(scheduler_state=state, scheduler_exit=exit_code)
                if state.split()[0].rstrip('+') == 'CANCELLED':
                    if row['status'] not in {'failed', 'cleanup_failed', 'completed', 'cancelled'}:
                        row.update(status='cancelled', reason=f'Scheduler {state} exit {exit_code}')
                elif state.split()[0] in {'FAILED', 'TIMEOUT', 'OUT_OF_MEMORY', 'NODE_FAIL', 'PREEMPTED'}:
                    if row['status'] not in {'failed', 'cleanup_failed', 'completed'}:
                        row.update(status='failed', failure_class='scheduler_' + state.split()[0].lower(),
                                   reason=f'Scheduler {state} exit {exit_code}; inspect recording and cleanup status')
                elif state == 'COMPLETED' and row['status'] not in {'completed', 'cleanup_failed', 'failed'}:
                    row.update(status='failed', reason='Job ended without a validated completion record; inspect cleanup status')
            if scheduler_key in live:
                live_state, reason, elapsed = live[scheduler_key][:3]
                row.update(scheduler_state=live_state, scheduler_reason=reason, scheduler_elapsed=elapsed)
                if row['status'] not in {'completed', 'failed', 'cleanup_failed', 'cancelled'}:
                    row['status'] = 'running' if live_state in {'RUNNING', 'COMPLETING'} else 'queued'
            trace_path = Path(row.get('results_dir') or '.') / 'nextflow/trace.txt'
            if row.get('results_dir') and trace_path.is_file():
                with trace_path.open() as handle:
                    stages = list(csv.DictReader(handle, delimiter='\t'))
                row['pipeline_completed_stages'] = sum(r.get('status') == 'COMPLETED' for r in stages)
                row['pipeline_failed_stages'] = ';'.join(r.get('name', '') for r in stages if r.get('status') == 'FAILED')
            if row.get('source_h5') and row.get('results_dir') and row.get('stage') == 'h5_cleanup':
                source_path = str(Path(row['source_h5']).resolve())
                identity = hashlib.sha256((row['recording_id'] + '\n' + source_path).encode()).hexdigest()
                deletion_path = Path(row['results_dir']) / 'repro/h5_cleanup' / identity / 'deleted.json'
                if deletion_path.is_file():
                    deletion = read_json(deletion_path)
                    if (deletion.get('status') == 'deleted' and deletion.get('recording_id') == row['recording_id']
                            and deletion.get('source_h5') == source_path):
                        row.update(h5_cleanup_status='deleted_confirmed_from_ledger',
                                   deleted_bytes=deletion['deleted_bytes'], h5_cleanup_ledger=str(deletion_path.parent))
            rows.append({name: row.get(name, '') for name in fields})
        changes = []
        observed = ('status', 'stage', 'attempt_profile', 'pipeline_completed_stages', 'scheduler_state')
        for row in rows:
            old = previous.get(row['recording_id'], {})
            if any(str(old.get(k, '')) != str(row.get(k, '')) for k in observed):
                changes.append(f"[{now()}] task={row.get('task_index')} status={row['status']} "
                    f"stage={row['stage']} profile={row.get('attempt_profile') or 'standard'} "
                    f"pipeline={row.get('pipeline_completed_stages') or 0}/11 "
                    f"recording={row['recording_id']} reason={row.get('failure_evidence') or row.get('reason') or ''}\n")
        if changes:
            with (batch_dir / 'progress.log').open('a') as handle:
                handle.writelines(changes)
        finished = sum(row['status'] in {'completed', 'failed', 'cleanup_failed', 'cancelled', 'blocked'} for row in rows)
        summary = {'updated_utc': now(), 'recordings': len(rows), 'tasks': len(plan['tasks']),
                   'finished': finished, 'remaining': len(rows) - finished,
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
        active = [r for r in rows if r['status'] == 'running']
        text = (f"MCS BATCH {plan.get('run_id', batch_dir.name)}\nUpdated UTC: {summary['updated_utc']}\n"
                f"Slurm array: {summary['array_job_id']} | concurrent recordings: {plan['concurrency']}\n"
                f"Finished: {finished}/{len(rows)} | remaining: {len(rows)-finished}\n"
                f"Counts: {json.dumps(summary['statuses'], sort_keys=True)}\n"
                f"Shared ledger: {batch_dir / 'recordings.csv'}\n\nRUNNING\n")
        for r in active:
            text += (f"task {r['task_index']} | {r['stage']} | {r.get('attempt_profile') or 'standard'} | "
                     f"{r.get('pipeline_completed_stages') or 0}/11 pipeline stages | {r['recording_id']}\n")
        failed = [r for r in rows if r['status'] in {'failed', 'cleanup_failed'}]
        text += '\nFAILED\n' + ''.join(f"task {r['task_index']} | {r.get('failure_class')} | {r.get('failure_evidence') or r['reason']} | {r['recording_id']}\n" for r in failed)
        temporary = batch_dir / 'PROGRESS.txt.tmp'
        temporary.write_text(text)
        temporary.replace(batch_dir / 'PROGRESS.txt')
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
                   f'--export=ALL,MCS_BATCH_DIR={batch_dir},MCS_BATCH_SUMMARY_ONLY=0,MCS_BATCH_WATCH_ONLY=0',
                   str(Path(plan['code_root']) / 'slurm/run_mcs_aind_batch.sbatch')]
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
                     f'--export=ALL,MCS_BATCH_DIR={batch_dir},MCS_BATCH_SUMMARY_ONLY=1,MCS_BATCH_WATCH_ONLY=0',
                     str(Path(plan['code_root']) / 'slurm/run_mcs_aind_batch.sbatch')]
        try:
            collected = subprocess.run(collector, check=True, text=True, capture_output=True)
            submission['summary_job_id'] = collected.stdout.strip().split(';')[0]
            submission['summary_command'] = collector
        except subprocess.CalledProcessError as exc:
            submission['summary_submission_error'] = exc.stderr
        watcher = ['sbatch', '--parsable', '--job-name=mcs-live-progress',
                   '--cpus-per-task=1', '--mem=1G', '--time=08:00:00',
                   f'--output={batch_dir}/logs/progress-%j.out', f'--error={batch_dir}/logs/progress-%j.err',
                   f'--export=ALL,MCS_BATCH_DIR={batch_dir},MCS_BATCH_WATCH_ONLY=1,MCS_BATCH_SUMMARY_ONLY=0',
                   str(Path(plan['code_root']) / 'slurm/run_mcs_aind_batch.sbatch')]
        try:
            watched = subprocess.run(watcher, check=True, text=True, capture_output=True)
            submission['watch_job_id'] = watched.stdout.strip().split(';')[0]
            submission['watch_command'] = watcher
        except subprocess.CalledProcessError as exc:
            submission['watch_submission_error'] = exc.stderr
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
        if status == 'running' and not state.get('started_utc'):
            state['started_utc'] = now()
        if status in {'completed', 'failed', 'cleanup_failed'}:
            state['finished_utc'] = now()
        state.update(stage=stage, status=status, updated_utc=now(), **extra)
        write_json(state_path, state)
        summary = refresh(batch_dir)
        print(f"[{now()}] TASK {task_index} {status.upper()} stage={stage} "
              f"profile={state.get('attempt_profile', 'standard')} | {row['recording_id']} | "
              f"batch={json.dumps(summary['statuses'], sort_keys=True)}", flush=True)

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
            if plan.get('minimum_duration_seconds', 0):
                inclusion = read_json(inputs / 'mcs_recording_manifest.json')
                if inclusion['sample_count'] / inclusion['sampling_frequency_hz'] < plan['minimum_duration_seconds']:
                    raise ValueError('Recording below saved batch duration cutoff; refusing execution')
            update('pipeline', attempt_profile='standard', fallback_used=False)
            if not row.get('reuse_completed'):
                try:
                    subprocess.run(['bash', str(code / 'slurm/run_aind_nwb_well.sbatch')],
                                   check=True, env=environment, cwd=code)
                except subprocess.CalledProcessError:
                    diagnosis = diagnose_recording(row)
                    if not plan.get('selective_fallback') or not diagnosis['fallback_eligible']:
                        raise
                    update('fallback_preparation', standard_results_dir=str(results),
                           standard_input_dir=str(inputs), standard_failure_class=diagnosis['failure_class'],
                           standard_training_snippets=diagnosis['training_snippets'])
                    row = prepare_selective_fallback(row, diagnosis)
                    results, inputs = Path(row['results_dir']), Path(row['input_dir'])
                    environment['AIND_CONFIG'] = row['env_file']
                    update('pipeline', attempt_profile='nt2_npcs2', fallback_used=True,
                           input_dir=str(inputs), results_dir=str(results))
                    subprocess.run(['bash', str(code / 'slurm/run_aind_nwb_well.sbatch')],
                                   check=True, env=environment, cwd=code)
            with (results / 'nextflow/trace.txt').open(newline='') as handle:
                trace = list(csv.DictReader(handle, delimiter='\t'))
            if len(trace) != 11 or any(r['status'] != 'COMPLETED' or r['exit'] != '0' for r in trace):
                raise ValueError('Expected all 11 AIND stages to complete successfully before finalization')
            repro = results / 'repro'
            repro.mkdir(exist_ok=True)
            preserve_input_snapshot(inputs, repro / 'mcs_input')
            for name in ('events.csv', 'channels.csv'):
                shutil.copy2(inputs / name, results / name)
            verification_code = repro / 'batch_verification' / plan['run_id']
            verification_code.mkdir(parents=True, exist_ok=True)
            shutil.copy2(batch_dir / 'code_sha256.json', verification_code / 'code_sha256.json')
            for name in ('prepare_mcs_aind_recording.py', 'finalize_mcs_aind_recording.py',
                         'finalize_mcs_aind_nwb.py', 'validate_mcs_aind_output.py', 'cleanup_mcs_h5.py'):
                shutil.copy2(code / 'scripts' / name, verification_code / name)
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
            if not (results / 'README.md').exists():
                (results / 'README.md').write_text(
                    '# MCS Single-MEA Sorting\n\n'
                    f"Recording: `{row['recording_id']}`\n\n"
                    f"Run: `{manifest['sorting_run_id']}`. Kilosort4 with the established TH5 profile; "
                    'single-MEA channel order, reference exclusion and calibration.\n\n'
                    f"Geometry status: `{manifest.get('geometry_status', 'source_verified')}`. "
                    'Unverified geometry is a computational assumption, not measured physical spacing. '
                    'See the recording manifest for source evidence and any short-duration adjustments.\n\n'
                    f"Recording completeness: `{manifest.get('recording_completeness', 'complete_staged_recording')}`. "
                    'A recovered prefix contains only the documented intact part of an incomplete original.\n\n'
                    f"Validated output: {stats['unit_count']} units, {stats['spike_count']} spikes. "
                    f"Kilosort labels: `{json.dumps(stats['kilosort_label_counts'], sort_keys=True)}`. "
                    'Technical validation is not manual curation or a claim that all units are good.\n\n'
                    '- `validation_summary.json`: input, output and event checks.\n'
                    '- `channels.csv` and `events.csv`: recording-specific metadata; events are not inferred treatments.\n'
                    '- `preprocessed/` and `durable_recording_report.json`: retained recording and checksums.\n'
                    '- `nwb/` and `repro/nwb_finalization_report.json`: corrected NWB output.\n'
                    '- `repro/mcs_input/`: acquisition metadata, parameters and provenance.\n'
                    '- `repro/h5_cleanup/`: source metadata and deletion proof, when H5 cleanup occurred.\n\n'
                    f"Batch ledger: `{batch_dir / 'recordings.csv'}`\n"
                )
            update('validated', unit_count=stats['unit_count'], spike_count=stats['spike_count'],
                   kilosort_label_counts=stats['kilosort_label_counts'])
            if plan['delete_validated_local_h5'] and row.get('source_h5') and not state.get('fallback_used'):
                update('h5_cleanup')
                cleaned = run('cleanup_mcs_h5.py', ['--results-dir', results, '--input-dir', inputs,
                              '--source-h5', row['source_h5'], '--allowed-root', plan['allowed_h5_root'], '--apply'], capture=True)
                cleanup = json.loads(cleaned.stdout)
                if cleanup.get('status') not in {'deleted', 'already_deleted'}:
                    raise ValueError('Cleanup did not return a verified deletion result')
                update('complete', 'completed', h5_cleanup_status=cleanup['status'],
                       deleted_bytes=int(cleanup['deleted_bytes']), h5_cleanup_ledger=cleanup['ledger'])
            else:
                cleanup_status = ('retained_cleanup_disabled' if row.get('retained_h5_cleanup_disabled') else
                                  'retained_rejected_h5' if row.get('rejected_h5') else 'no_local_h5')
                update('complete', 'completed', h5_cleanup_status=cleanup_status if not row.get('source_h5') else 'retained', deleted_bytes=0)
            return 0
        except Exception as exc:
            cleanup_failed = state.get('stage') == 'h5_cleanup'
            update(state.get('stage', 'unknown'), 'cleanup_failed' if cleanup_failed else 'failed',
                   reason=f'{type(exc).__name__}: {exc}', h5_cleanup_status='not_deleted_or_check_deletion_ledger',
                   **(diagnose_recording(row) if state.get('stage') == 'pipeline' else {}))
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
    p.add_argument('--allow-staged-geometry', action='store_true')
    p.add_argument('--allow-short-recordings', action='store_true')
    p.add_argument('--selective-fallback', action='store_true')
    p.add_argument('--minimum-duration-seconds', type=float, default=0)
    for name in ('submit', 'status', 'worker', 'diagnose', 'watch'):
        p = commands.add_parser(name)
        p.add_argument('--batch-dir', type=Path, required=True)
        if name == 'worker':
            p.add_argument('--task-index', type=int, required=True)
        if name == 'watch':
            p.add_argument('--interval', type=int, default=20)
        if name == 'status':
            p.add_argument('--scheduler', action='store_true')
    args = parser.parse_args()
    batch = args.batch_dir.expanduser().resolve()
    if args.command == 'prepare':
        result = prepare_batch(args.source_index.resolve(), batch, args.project_root.resolve(),
                               args.run_id, args.concurrency, args.delete_validated_h5,
                               allow_staged_geometry=args.allow_staged_geometry,
                               allow_short_recordings=args.allow_short_recordings,
                               selective_fallback=args.selective_fallback,
                               minimum_duration_seconds=args.minimum_duration_seconds)
    elif args.command == 'submit':
        result = submit(batch)
    elif args.command == 'watch':
        return watch(batch, args.interval)
    elif args.command == 'diagnose':
        result = diagnose_batch(batch)
    elif args.command == 'status':
        result = refresh(batch, args.scheduler)
    else:
        return worker(batch, args.task_index)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
