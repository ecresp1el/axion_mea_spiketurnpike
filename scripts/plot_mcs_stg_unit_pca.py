"""Label-blind PCA of per-unit one-second e-stim firing rates."""
import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
REPO = Path(__file__).resolve().parents[1]
OUT = Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/mcs_stg_unit_pca.png')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--matched', action='store_true')
    args = parser.parse_args()
    with (REPO/'metadata/mcs_recording_biology.csv').open() as f:
        records = list(csv.DictReader(f))
    groups = ['Actuators + effectors', 'Actuators + vehicle', 'Plain neurons + effectors']
    matrices, identities = [], []
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
        features = np.zeros((len(labels), 20), dtype=float)
        bin_ids = np.floor(relative + 10).astype(int)
        np.add.at(features, (window['unit_index'], bin_ids), 1)
        matrices.append(features)
        identities.extend([(g, sub, r['recording_id'])] * len(labels))
        included[g] += 1
    x = np.log1p(np.concatenate(matrices))
    scale = x.std(axis=0)
    assert np.all(scale > 0) and np.all(np.isfinite(x))
    z = (x - x.mean(axis=0)) / scale
    u, singular, vt = np.linalg.svd(z, full_matrices=False)
    scores = z @ vt[:2].T
    variance = singular[:2]**2 / np.sum(singular**2)*100
    colors = dict(zip(groups, ['#4979b6', '#da8a32', '#459b79']))
    markers = {'DREADD':'o', 'LMO':'s', 'PSAM':'^', 'Control':'X',
               'CNO':'o', 'CTZ':'s', 'PSEM':'^', 'NeuroBasal Medium':'X'}
    ids = np.array(identities)
    if args.matched:
        plot_matched(scores, ids, variance, groups)
        return
    fig, axes = plt.subplots(1,2,figsize=(12,5.8),sharex=True,sharey=True)
    for group in groups:
        for sub in dict.fromkeys(ids[ids[:,0]==group,1]):
            mask = (ids[:,0]==group)&(ids[:,1]==sub)
            axes[0].scatter(scores[mask,0], scores[mask,1], c=colors[group],marker=markers[sub],
                            s=12,alpha=.25,linewidths=0)
            recids = list(dict.fromkeys(ids[mask,2]))
            means = np.array([scores[ids[:,2]==rid].mean(axis=0) for rid in recids])
            axes[1].scatter(means[:,0], means[:,1], c=colors[group],marker=markers[sub],
                            s=55,alpha=.8,edgecolors='white',linewidths=.5)
    axes[0].set_title(f'Each dot = unit ({len(scores):,} unit-recording observations)')
    axes[1].set_title(f'Each dot = recording mean ({sum(included.values())} recordings)')
    for ax in axes:
        ax.set_xlabel(f'PC1 ({variance[0]:.1f}% variance)')
        ax.set_ylabel(f'PC2 ({variance[1]:.1f}% variance)')
        ax.spines[['top','right']].set_visible(False)
        ax.axhline(0,color='gray',lw=.4,alpha=.3)
        ax.axvline(0,color='gray',lw=.4,alpha=.3)
    handles=[Line2D([],[],marker='o',ls='',color=colors[g],label=g) for g in groups]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.13),ncol=3,frameon=False)
    fig.suptitle('E-stim response PCA: group labels used only for coloring',fontsize=14)
    fig.text(.5,.025,'Features: 20 one-second firing-rate bins, −10 to +10 s around first STG train; log1p then feature standardization.\n'
             'SUA/MUA pooled. Shapes: circle DREADD/CNO; square LMO/CTZ; triangle PSAM/PSEM; X Control/NB.\n'
             'Same PCA axes in both panels; right panel averages unit scores within recordings. '
             'No artifact blanking; units are nested within recordings.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.22,1,.94))
    fig.savefig(OUT,dpi=150)
    plt.close(fig)
    print('Units:',len(scores),'Recordings:',included,'Variance:',variance.tolist())
    for group in groups:
        subset=scores[ids[:,0]==group]
        print(group,'unit centroid',subset.mean(axis=0).round(3).tolist(),
              'unit SD',subset.std(axis=0).round(3).tolist())
    print('Saved',OUT,OUT.stat().st_size,'bytes')


def plot_matched(scores, ids, variance, groups):
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.5), sharex=True, sharey=True)
    comparisons = [
        (groups[0], None, '#4979b6', 'o', 'Actuator + effector'),
        (groups[1], None, '#da8a32', 'o', 'Actuator + vehicle'),
        (groups[0], 'Control', '#444444', 'x', '371 Control in effector arm'),
        (groups[1], 'Control', '#a15a89', 'x', '371 Control in vehicle arm'),
    ]
    for ax, construct in zip(axes, ['DREADD', 'LMO', 'PSAM']):
        for group, fixed_sub, color, marker, title in comparisons:
            sub = fixed_sub or construct
            mask = (ids[:,0] == group) & (ids[:,1] == sub)
            nrec = len(set(ids[mask,2]))
            ax.scatter(scores[mask,0], scores[mask,1], color=color, marker=marker,
                       s=10 if marker == 'o' else 13, alpha=.33, linewidths=.55,
                       label=f'{title}: {mask.sum()} units / {nrec} rec')
            print(construct, title, 'units', mask.sum(), 'recordings', nrec)
        ax.set_title(construct, fontsize=13)
        ax.set_xlabel(f'PC1 ({variance[0]:.1f}%)')
        ax.spines[['top','right']].set_visible(False)
        ax.axhline(0, color='gray', lw=.4, alpha=.3)
        ax.axvline(0, color='gray', lw=.4, alpha=.3)
        ax.legend(fontsize=7, frameon=False, loc='lower left')
    axes[0].set_ylabel(f'PC2 ({variance[1]:.1f}%)')
    fig.suptitle('E-stim PCA: each actuator compared with vehicle and 371 controls', fontsize=14)
    fig.text(.5,.03,'Each dot = one unit in one recording; SUA/MUA pooled. '
             'Same previously fitted PCA axes in all panels; no refitting to separate groups.\n'
             '20 one-second bins (−10 to +10 s), log1p and feature standardization. '
             '371 controls repeat across panels; plain-neuron chemical pairings omitted.\n'
             'Units are nested within recordings; no artifact blanking or significance testing.',
             ha='center', fontsize=8)
    fig.tight_layout(rect=(0,.15,1,.93))
    dest = OUT.with_name('mcs_stg_pca_matched_actuators.png')
    fig.savefig(dest,dpi=150)
    plt.close(fig)
    print('Saved',dest,dest.stat().st_size,'bytes')

if __name__ == '__main__':
    main()
