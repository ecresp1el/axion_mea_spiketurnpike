"""Per-unit paired e-stim response, pooling good/mua, for 5- and 10-second windows."""
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
OUT = Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/mcs_stg_units_pre_post_5s_10s.png')

def main():
    with (REPO/'metadata/mcs_recording_biology.csv').open() as f:
        records = list(csv.DictReader(f))
    groups = ['Actuators + effectors', 'Actuators + vehicle', 'Plain neurons + effectors']
    subgroups = [['DREADD', 'LMO', 'PSAM', 'Control']]*2 + [['CNO', 'CTZ', 'PSEM', 'NeuroBasal Medium']]
    curves = {}
    included = {g: 0 for g in groups}
    for r in records:
        g = r['major_group']
        if g not in groups or not r['total_units'] or float(r['duration_s']) < 60:
            continue
        starts = sorted(json.loads(r['pulse_start_times_s'] or '[]'))
        if not starts:
            continue
        onset = starts[0]
        if onset < 10 or onset+10 > float(r['duration_s']):
            raise ValueError('Incomplete window: '+r['recording_id'])
        next_trains = [b for a,b in zip(starts, starts[1:]) if b-a > .1]
        if next_trains and next_trains[0] < onset+10:
            raise ValueError('Another train contaminates response window')
        files = list((Path(r['sorting_output_path'])/'curated').glob('*/numpysorting_info.json'))
        if len(files) != 1:
            raise ValueError('Ambiguous sorting')
        info = json.loads(files[0].read_text())
        folder = files[0].parent
        labels = np.load(folder/'properties/KSLabel.npy', allow_pickle=False).astype(str)
        spikes = np.load(folder/'spikes.npy', mmap_mode='r', allow_pickle=False)
        fs = info['sampling_frequency']
        assert info['num_segments'] == 1 and len(labels) == len(info['unit_ids'])
        lo,hi = np.searchsorted(spikes['sample_index'], [(onset-10)*fs, (onset+10)*fs])
        window = spikes[lo:hi]
        relative = window['sample_index']/fs-onset
        sub = r['treatment'] if g == groups[2] else r['construct']
        valid = np.isin(labels, ['good', 'mua'])
        if not np.all(valid):
            raise ValueError('Unexpected labels; review before pooling')
        for seconds in [5, 10]:
            pre = (relative >= -seconds) & (relative < 0)
            post = (relative >= 0) & (relative < seconds)
            before = np.bincount(window['unit_index'][pre], minlength=len(labels))/seconds
            after = np.bincount(window['unit_index'][post], minlength=len(labels))/seconds
            pairs = np.column_stack([before, after])
            curves.setdefault((g, sub, seconds), []).append(pairs)
        included[g] += 1
    fig, axes = plt.subplots(3, 2, figsize=(13, 11), sharey=True)
    rng = np.random.default_rng(42)
    colors = ['#5779aa', '#388d83', '#c68b3e', '#777777']
    maximum = 0
    for row, group in enumerate(groups):
        for col, seconds in enumerate([5, 10]):
            ax = axes[row, col]
            ticks = []
            for j, (sub, color) in enumerate(zip(subgroups[row], colors)):
                batches = curves.get((group, sub, seconds), [])
                pairs = np.concatenate(batches) if batches else np.empty((0, 2))
                short = 'NB' if sub == 'NeuroBasal Medium' else sub
                ticks.append(f'{short}\n{len(pairs)} units / {len(batches)} rec')
                if not len(pairs):
                    continue
                maximum = max(maximum, float(pairs.max()))
                positions = np.array([j*3, j*3+1])
                bp = ax.boxplot([pairs[:, 0], pairs[:, 1]], positions=positions,
                                widths=.65, patch_artist=True, showfliers=False,
                                manage_ticks=False, medianprops=dict(color='black', linewidth=1.4),
                                zorder=3)
                for patch, alpha in zip(bp['boxes'], [.20, .60]):
                    patch.set_facecolor(color)
                    patch.set_alpha(alpha)
                offsets = rng.uniform(-.19, .19, len(pairs))
                ax.plot(np.vstack([positions[0]+offsets, positions[1]+offsets]),
                        pairs.T, color=color, lw=.3, alpha=.09, zorder=1)
                for k in range(2):
                    ax.scatter(positions[k]+offsets, pairs[:, k], s=4, color=color, alpha=.30,
                               linewidths=0, zorder=2)
                print(group, sub, seconds, 'units', len(pairs), 'recordings', len(batches),
                      'median pre/post', np.median(pairs, axis=0).round(3).tolist())
            ax.set_xticks([j*3+.5 for j in range(4)], ticks, fontsize=8)
            ax.set_xlim(-.8, 10.8)
            ax.set_title(f'{group} | {seconds}-s windows', fontsize=11)
            ax.spines[['top', 'right']].set_visible(False)
            ax.grid(axis='y', alpha=.15)
            if col == 0:
                ax.set_ylabel('Unit firing rate (Hz)')
    # A shared symmetric-log scale keeps zero-rate units and large responses visible.
    axes[0, 0].set_yscale('symlog', linthresh=1, linscale=1)
    axes[0, 0].set_ylim(0, maximum*1.08)
    fig.suptitle('E-stim: per-unit pre/post activity, SUA and MUA pooled', fontsize=15)
    fig.text(.5, .02, 'Each dot = one sorted unit in one recording; faint lines pair the same unit. '
             'PRE = left/pale; POST = right/dark.\n'
             '5 s: [−5,0) vs [0,+5); 10 s: [−10,0) vs [0,+10). '
             'First STG train only; boxes = median/IQR.\n'
             'Y axis: linear 0–1 Hz, logarithmic above 1 Hz. '
             'Units are nested within recordings; no significance tests or artifact blanking.\n'
             'The 5- and 10-s windows overlap: these compare cumulative response duration, not independent time intervals.',
             ha='center', fontsize=8)
    fig.tight_layout(rect=(0,.105,1,.96))
    fig.savefig(OUT,dpi=150)
    plt.close(fig)
    print('Included recordings:', included)
    print('Saved', OUT, OUT.stat().st_size, 'bytes')

if __name__ == '__main__':
    main()
