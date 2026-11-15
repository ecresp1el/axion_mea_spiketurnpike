"""Plot only the requested +/-5-second chemical-addition response."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
DEST = Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/mcs_chemical_psth_5s.png')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--event', choices=['chemical', 'pulse'], default='chemical')
    kind = parser.parse_args().event
    destination = DEST if kind == 'chemical' else DEST.with_name('mcs_stg_psth_5s.png')
    with (REPO / 'metadata/mcs_recording_biology.csv').open() as f:
        records = list(csv.DictReader(f))
    constructs = ['DREADD', 'LMO', 'PSAM', 'Control']
    bins = np.linspace(-5, 5, 21)
    centers = (bins[:-1] + bins[1:]) / 2
    curves = {(c, label): [] for c in constructs for label in ['good', 'mua']}
    unit_counts = {key: 0 for key in curves}
    for r in records:
        if (r['major_group'] != 'Actuators + effectors' or not r['total_units']
                or float(r['duration_s']) < 60):
            continue
        events = json.loads(r['events_json'] or '[]')
        starts = [float(e['time_from_recording_start_s']) for e in events
                  if ((kind == 'chemical' and e['event_label'].strip().lower() == 'chemical start')
                      or (kind == 'pulse' and 'pulse start' in e['event_label'].lower()))]
        if not starts:
            continue
        if kind == 'chemical' and len(starts) != 1:
            raise ValueError('Multiple additions require an explicit repeated-event policy')
        if kind == 'pulse' and max(starts) - min(starts) > .1:
            raise ValueError('Multiple pulse trains require an explicit trial policy')
        onset = min(starts)
        if onset < 5 or onset + 5 > float(r['duration_s']):
            raise ValueError('Incomplete baseline/response window: ' + r['recording_id'])
        folders = list((Path(r['sorting_output_path']) / 'curated').glob('*/numpysorting_info.json'))
        if len(folders) != 1:
            raise ValueError('Ambiguous sorting: ' + r['recording_id'])
        folder = folders[0].parent
        info = json.loads(folders[0].read_text())
        labels = np.load(folder / 'properties/KSLabel.npy', allow_pickle=False).astype(str)
        spikes = np.load(folder / 'spikes.npy', mmap_mode='r', allow_pickle=False)
        fs = float(info['sampling_frequency'])
        assert info['num_segments'] == 1 and len(labels) == len(info['unit_ids'])
        samples = spikes['sample_index']
        lo, hi = np.searchsorted(samples, [(onset - 5) * fs, (onset + 5) * fs], side='left')
        window = spikes[lo:hi]
        relative = window['sample_index'] / fs - onset
        for label in ['good', 'mua']:
            n = int(np.sum(labels == label))
            if not n:
                continue  # No units of this class is missing, not a zero-rate response.
            mask = labels[window['unit_index']] == label
            counts = np.histogram(relative[mask], bins=bins)[0]
            hz = counts / (.5 * n)
            baseline = counts[:10].sum() / (5 * n)
            key = (r['construct'], label)
            curves[key].append(hz - baseline)
            unit_counts[key] += n
            print(r['construct'], label, r['sample_label'], 'units', n,
                  'baseline_hz', round(baseline, 3),
                  'post_hz', round(counts[10:].sum() / (5*n), 3))
    fig, axes = plt.subplots(2, 4, figsize=(12, 6), sharex=True, sharey=True)
    colors = dict(zip(constructs, ['#5779aa', '#388d83', '#c68b3e', '#777777']))
    for col, construct in enumerate(constructs):
        for row, label in enumerate(['good', 'mua']):
            ax = axes[row, col]
            values = curves[(construct, label)]
            for y in values:
                ax.step(centers, y, where='mid', color=colors[construct], alpha=.25, lw=.9)
            if values:
                ax.step(centers, np.mean(values, axis=0), where='mid', color=colors[construct], lw=2)
            else:
                ax.text(.5, .5, 'No units of this class', transform=ax.transAxes, ha='center', fontsize=9)
            ax.axvline(0, color='black', linestyle='--', lw=.8)
            ax.axhline(0, color='black', lw=.5, alpha=.4)
            ax.set_title(f'{construct}: {len(values)} rec / {unit_counts[(construct,label)]} units', fontsize=10)
            ax.spines[['top', 'right']].set_visible(False)
            ax.set_xlim(-5, 5)
            if col == 0:
                ax.set_ylabel(('Putative SUA' if label == 'good' else 'MUA') + '\nΔ firing rate (Hz/unit)')
            if row == 1:
                ax.set_xlabel('Time from addition (s)' if kind == 'chemical' else 'Time from first STG pulse (s)')
    fig.suptitle('Actuators + effectors: ' + ('chemical-addition' if kind == 'chemical' else 'STG pulse-train') + '-aligned PSTH', fontsize=14)
    fig.text(.5, .02, '0.5-s bins; baseline = −5 to 0 s; response = 0 to +5 s. '
             'Faint = recordings; bold = equal-recording mean.\nAutomated KSLabel good/mua; '
             'repeated recordings are not independent biological replicates. ' +
             ('Pulse events excluded.' if kind == 'chemical' else 'First of 5 pulses = t0; train spans 41 ms; no artifact blanking.'),
             ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .10, 1, .94))
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=150)
    plt.close(fig)
    print('Saved', destination, destination.stat().st_size, 'bytes')

if __name__ == '__main__':
    main()
