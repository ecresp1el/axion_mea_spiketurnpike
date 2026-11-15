"""Attach saved unit counts and hardware event timing to the biology CSV."""
import csv
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT = Path('/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder')

def main():
    path = REPO / 'metadata/mcs_recording_biology.csv'
    with path.open() as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames)
        records = list(reader)
    added = ['duration_min', 'total_units', 'sua_units', 'mua_units', 'total_spikes',
             'unit_count_source', 'event_metadata_status', 'has_stim_markers',
             'event_count', 'pulse_start_count', 'pulse_stop_count',
             'chemical_start_count', 'chemical_stop_count', 'event_labels',
             'pulse_start_times_s', 'pulse_stop_times_s', 'chemical_start_times_s',
             'chemical_stop_times_s', 'first_event_s', 'last_event_s',
             'events_json', 'events_source_path']
    fields += [x for x in added if x not in fields]
    attempts = {}
    for ledger in sorted((PROJECT / 'jobs').glob('aind_mcs*/recordings.csv')):
        with ledger.open() as f:
            for row in csv.DictReader(f):
                attempts.setdefault(row['recording_id'], []).append(row)
    summary = {}
    for r in records:
        for name in added:
            r[name] = ''
        related = attempts.get(r['recording_id'], [])
        chosen = next((a for a in related if a.get('results_dir') == r['sorting_output_path']), None)
        if chosen and chosen.get('duration_s'):
            r['duration_s'] = chosen['duration_s']
        duration = float(r['duration_s']) if r['duration_s'] else None
        if duration is not None:
            r['duration_min'] = round(duration / 60, 6)
            r['under_60s'] = str(duration < 60).lower()
        output = Path(r['sorting_output_path']) if r['sorting_output_path'] else None
        report_path = output / 'validation_summary.json' if output else None
        if 'completed' in r['sorting_status'] and report_path and report_path.exists():
            report = json.loads(report_path.read_text())
            if report['errors']:
                raise ValueError(f'Validation errors: {report_path}')
            stats = report['stages']['curated']
            labels = stats['kilosort_label_counts']
            r.update(total_units=stats['unit_count'], sua_units=labels.get('good', 0),
                     mua_units=labels.get('mua', 0), total_spikes=stats['spike_count'],
                     unit_count_source=str(report_path))
            assert r['total_units'] == sum(labels.values())
        candidates = []
        if output:
            candidates.append(output / 'repro/mcs_input/events.csv')
        if chosen and chosen.get('input_dir'):
            candidates.append(Path(chosen['input_dir']) / 'events.csv')
        if r['staged_input_dir']:
            candidates.append(Path(r['staged_input_dir']) / 'events.csv')
        for a in reversed(related):
            if a.get('input_dir'):
                candidates.append(Path(a['input_dir']) / 'events.csv')
        events_path = next((p for p in candidates if p.is_file()), None)
        if events_path:
            with events_path.open() as f:
                events = list(csv.DictReader(f))
            for e in events:
                t = float(e['time_from_recording_start_s'])
                if not math.isfinite(t) or t < 0 or (duration is not None and t >= duration):
                    raise ValueError(f'Out-of-bounds event: {events_path}: {e}')
            r['events_source_path'] = str(events_path)
            r['event_metadata_status'] = 'markers_present' if events else 'no_markers_in_saved_file'
            r['has_stim_markers'] = str(bool(events)).lower()
            r['event_count'] = len(events)
            r['event_labels'] = json.dumps(list(dict.fromkeys(e['event_label'] for e in events)))
            for kind in ['pulse', 'chemical']:
                for edge in ['start', 'stop']:
                    times = [float(e['time_from_recording_start_s']) for e in events
                             if kind in e['event_label'].lower() and edge in e['event_label'].lower()]
                    r[f'{kind}_{edge}_count'] = len(times)
                    r[f'{kind}_{edge}_times_s'] = json.dumps(times, separators=(',', ':'))
            times = [float(e['time_from_recording_start_s']) for e in events]
            if times:
                r['first_event_s'], r['last_event_s'] = min(times), max(times)
            r['events_json'] = json.dumps(events, separators=(',', ':'))
        else:
            r['event_metadata_status'] = 'metadata_unavailable'
        summary[r['event_metadata_status']] = summary.get(r['event_metadata_status'], 0) + 1
    assert len(records) == len({r['recording_id'] for r in records}) == 118
    pending = path.with_suffix('.csv.tmp')
    with pending.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    pending.replace(path)
    print('Recordings:', len(records), 'with unit counts:', sum(r['total_units'] != '' for r in records))
    print('Events:', summary, 'bytes:', path.stat().st_size)
    for r in records:
        if r['event_count'] and r['chemical_start_count']:
            print('Chemical example:', r['recording_id'], r['event_labels'], r['chemical_start_times_s'])
            break

if __name__ == '__main__':
    main()
