"""One compact overview from saved validated sorting labels; no signal loading."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
PROJECT = Path('/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder')
OUTPUT = Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/mcs_sua_mua_overview.png')

def main():
    mapping_path = REPO / 'metadata/mcs_recording_biology.csv'
    with mapping_path.open() as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames)
        records = list(reader)
    # Completed validated attempts take precedence over original failures.
    selected = {}
    latest = {}
    for ledger in sorted((PROJECT / 'jobs').glob('aind_mcs*/recordings.csv')):
        with ledger.open() as f:
            for row in csv.DictReader(f):
                latest[row['recording_id']] = row
                if row['status'] != 'completed':
                    continue
                report_path = Path(row['results_dir']) / 'validation_summary.json'
                report = json.loads(report_path.read_text())
                if report.get('errors'):
                    raise ValueError(f'Completed result has validation errors: {report_path}')
                labels = report['stages']['curated']['kilosort_label_counts']
                if set(labels) - {'good', 'mua'}:
                    raise ValueError(f'Unexpected labels: {labels}')
                candidate = (report['validated_at_utc'], row, labels)
                key = row['recording_id']
                if key not in selected or candidate[0] > selected[key][0]:
                    selected[key] = candidate
    for row in records:
        rid = row['recording_id']
        if rid in selected:
            _, saved, labels = selected[rid]
            row['sorting_status'] = 'completed; saved validation passed'
            row['sorting_output_path'] = saved['results_dir']
            row['duration_s'] = saved.get('duration_s') or row['duration_s']
            row['under_60s'] = str(float(row['duration_s']) < 60).lower()
        elif rid in latest:
            row['sorting_status'] = latest[rid]['status']
            row['sorting_output_path'] = latest[rid].get('results_dir', '')
    with mapping_path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    groups = ['Actuators + effectors', 'Actuators + vehicle', 'Plain neurons + effectors']
    eligible = [r for r in records if r['recording_id'] in selected
                and r['major_group'] in groups and float(r['duration_s']) >= 60]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.9), sharey=True)
    colors = ['#4878a8', '#d38b38', '#49947b']
    rng = np.random.default_rng(42)
    counts = []
    for ax, label, title in zip(axes, ['good', 'mua'], ['Putative SUA (KSLabel = good)', 'MUA (KSLabel = mua)']):
        for i, (group, color) in enumerate(zip(groups, colors)):
            subset = [r for r in eligible if r['major_group'] == group]
            values = [selected[r['recording_id']][2].get(label, 0) for r in subset]
            ax.scatter(i + rng.uniform(-.16, .16, len(values)), values,
                       color=color, s=25, alpha=.7, edgecolors='white', linewidths=.4)
            if values:
                ax.plot([i-.24, i+.24], [np.median(values)]*2, color='black', lw=2)
            if label == 'good':
                counts.append(len(values))
            print(group, label, 'recordings', len(values), 'units', sum(values),
                  'median', float(np.median(values)) if values else None)
        ax.set_title(title, fontsize=11)
        ax.set_xticks(range(3), ['Actuators +\neffectors', 'Actuators +\nvehicle', 'Plain neurons +\neffectors'])
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', alpha=.18)
    maximum = max(selected[r['recording_id']][2].get(label, 0)
                  for r in eligible for label in ['good', 'mua'])
    axes[0].set_ylim(-2, maximum * 1.08)
    axes[0].set_ylabel('Sorted units per recording')
    unresolved = sum(r['recording_id'] in selected and not r['major_group'] for r in records)
    short = sum(r['recording_id'] in selected and float(r['duration_s']) < 60 for r in records)
    fig.suptitle('MCS sorted-unit yield by biological group', fontsize=14)
    fig.text(.5, .025, 'Dots = recordings; black lines = medians. Group n = ' + ', '.join(map(str, counts))
             + f'.\nExcluded: {unresolved} treatment-unresolved recordings; {short} recording <60 s. '
             + 'SUA labels are automated, not manual validation.', ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .12, 1, .93))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=150)
    plt.close(fig)
    print('Validated unique recordings:', len(selected), 'Plotted:', len(eligible))
    print('Figure:', OUTPUT, 'Bytes:', OUTPUT.stat().st_size)

if __name__ == '__main__':
    main()
