"""Single first-train-aligned SUA/MUA overview across the three major groups."""
import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[1]
OUT = Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/mcs_stg_all_groups_5s.png')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--boxplot', action='store_true')
    args = parser.parse_args()
    with (REPO / 'metadata/mcs_recording_biology.csv').open() as f:
        records = list(csv.DictReader(f))
    groups = ['Actuators + effectors', 'Actuators + vehicle', 'Plain neurons + effectors']
    subgroups = [['DREADD', 'LMO', 'PSAM', 'Control']]*2 + [['CNO', 'CTZ', 'PSEM', 'NeuroBasal Medium']]
    bins = np.linspace(-5, 5, 21)
    centers = (bins[:-1] + bins[1:])/2
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
        if onset < 5 or onset+5 > float(r['duration_s']):
            raise ValueError('Incomplete window: '+r['recording_id'])
        next_trains = [b for a,b in zip(starts, starts[1:]) if b-a > .1]
        if next_trains and next_trains[0] < onset+5:
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
        lo,hi = np.searchsorted(spikes['sample_index'], [(onset-5)*fs, (onset+5)*fs])
        window = spikes[lo:hi]
        relative = window['sample_index']/fs-onset
        sub = r['treatment'] if g == groups[2] else r['construct']
        for label in ['good', 'mua']:
            n = int(np.sum(labels == label))
            if not n:
                continue
            counts = np.histogram(relative[labels[window['unit_index']] == label], bins)[0]
            hz = counts/(.5*n)
            delta = hz - counts[:10].sum()/(5*n)
            curves.setdefault((g,sub,label), []).append((hz,n))
        included[g] += 1
    if args.boxplot:
        plot_boxes(curves, groups, subgroups, included)
        return
    fig,axes = plt.subplots(3,2,figsize=(11,10),sharex=True,sharey=True)
    colors = ['#5779aa', '#388d83', '#c68b3e', '#777777']
    for row,g in enumerate(groups):
        for col,label in enumerate(['good','mua']):
            ax = axes[row,col]
            for sub,color in zip(subgroups[row],colors):
                entries = curves.get((g,sub,label),[])
                short = 'NB' if sub == 'NeuroBasal Medium' else sub
                if entries:
                    y = np.mean([v - np.mean(v[:10]) for v,n in entries],axis=0)
                    ax.step(centers,y,where='mid',color=color,lw=1.8,
                            label=f'{short}: {len(entries)} rec / {sum(n for v,n in entries)} units')
                else:
                    ax.plot([],[],color=color,label=f'{short}: no units')
            ax.axvline(0,color='black',ls='--',lw=.8)
            ax.axhline(0,color='black',lw=.5,alpha=.4)
            ax.set_title(g+' — '+('putative SUA' if label=='good' else 'MUA'),fontsize=11)
            ax.legend(fontsize=8,frameon=False,loc='upper right')
            ax.set_xlim(-5,5)
            ax.spines[['top','right']].set_visible(False)
            if col==0:
                ax.set_ylabel('Δ firing rate (Hz/unit)')
            if row==2:
                ax.set_xlabel('Time from first STG pulse (s)')
    fig.suptitle('STG-aligned responses across the three biological groups',fontsize=15)
    fig.text(.5,.018,'First train per recording; 0.5-s bins; baseline −5 to 0 s; response 0 to +5 s.\n'
             'Lines = equal-recording means; automated KSLabel good/mua; no artifact blanking.\n'
             'Recordings are not asserted to be independent biological replicates; dates do not define groups.',
             ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.085,1,.96))
    fig.savefig(OUT,dpi=150)
    plt.close(fig)
    print('Included recordings:',included)
    print('Saved',OUT,OUT.stat().st_size,'bytes')


def plot_boxes(curves, groups, subgroups, included):
    fig, axes = plt.subplots(3, 2, figsize=(12, 10), sharey=True)
    colors = ['#5779aa', '#388d83', '#c68b3e', '#777777']
    rng = np.random.default_rng(42)
    for row, group in enumerate(groups):
        for col, label in enumerate(['good', 'mua']):
            ax = axes[row, col]
            ticks = []
            for j, (sub, color) in enumerate(zip(subgroups[row], colors)):
                entries = curves.get((group, sub, label), [])
                pairs = np.array([[np.mean(v[:10]), np.mean(v[10:])] for v, n in entries])
                short = 'NB' if sub == 'NeuroBasal Medium' else sub
                ticks.append(f'{short}\nn={len(entries)}')
                positions = [j*3, j*3+1]
                if not len(entries):
                    continue
                bp = ax.boxplot([pairs[:,0], pairs[:,1]], positions=positions,
                                widths=.65, patch_artist=True, showfliers=False,
                                manage_ticks=False, medianprops=dict(color='black', linewidth=1.5))
                for patch, alpha in zip(bp['boxes'], [.22, .65]):
                    patch.set_facecolor(color)
                    patch.set_alpha(alpha)
                for pre, post in pairs:
                    offset = rng.uniform(-.10, .10)
                    ax.plot([positions[0]+offset, positions[1]+offset], [pre, post],
                            color=color, lw=.7, alpha=.55, marker='o', markersize=3)
                print(group, sub, label, 'n', len(pairs),
                      'median pre/post', np.median(pairs, axis=0).round(3).tolist())
            ax.set_xticks([j*3+.5 for j in range(4)], ticks)
            ax.set_xlim(-.8, 10.8)
            ax.set_title(group+' — '+('putative SUA' if label == 'good' else 'MUA'), fontsize=11)
            ax.spines[['top','right']].set_visible(False)
            ax.grid(axis='y', alpha=.15)
            if col == 0:
                ax.set_ylabel('Mean firing rate (Hz/unit)')
    max_rate = max(max(np.mean(v[:10]), np.mean(v[10:]))
                   for entries in curves.values() for v, n in entries)
    axes[0, 0].set_ylim(0, max_rate * 1.10)
    fig.suptitle('E-stim: paired pre/post firing rates across three biological groups', fontsize=14)
    fig.text(.5, .022, 'Each pair: PRE (left, pale) = −5 to 0 s; POST (right, dark) = 0 to +5 s. First STG train only.\n'
             'Dots/lines = paired recordings, each averaged over its units; n = recordings with that unit class.\n'
             'Boxes = median and IQR; whiskers = 1.5 IQR. Automated good/mua labels; no artifact blanking or significance tests.\n'
             'Recordings may be repeated measurements of the same biological sample.', ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .11, 1, .96))
    dest = OUT.with_name('mcs_stg_pre_post_boxplots_5s.png')
    fig.savefig(dest, dpi=150)
    plt.close(fig)
    print('Included recordings:', included)
    print('Saved', dest, dest.stat().st_size, 'bytes')

if __name__ == '__main__':
    main()
