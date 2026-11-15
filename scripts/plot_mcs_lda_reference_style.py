"""Reference-style interpretation panels for the frozen 215-feature unit LDA."""
from pathlib import Path
import hashlib
import json
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from load_mcs_locked_lda import load_units, project_units, CONFIG

ROOT = Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis')
OUT = ROOT/'lda_reference_style'
GROUPS = ['Control', 'DREADD', 'LMO', 'PSAM']
COLORS = ['#777777', '#e94b47', '#64af54', '#9462d5']

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def label(name):
    match = re.fullmatch(r'burst_t(\d+)_n(\d+)__(\w+)__(\w+)', name)
    if match:
        gap, minimum, window, metric = match.groups()
        interval = {'pre5': '−5 to 0 s', 'pre10': '−10 to 0 s',
                    'post5': '0–5 s', 'post10': '0–10 s', 'late': '0.5–10 s'}[window]
        description = {'first_burst_latency': 'Time to first burst',
                       'duration_mean': 'Average burst duration',
                       'duration_max': 'Longest burst duration',
                       'rate_hz': 'Bursts per second', 'count': 'Number of bursts',
                       'interburst_gap_mean': 'Average pause between bursts'}[metric]
        return f'{description}: {interval}\n(gaps ≤{int(gap)} ms; ≥{minimum} spikes per burst)'
    return {
        'delta__post_025_05': 'Firing-rate change: 0.25–0.5 s\n(relative to −5 to 0 s baseline)',
        'rate__post_05_1': 'Firing rate: 0.5–1 s after stimulation',
        'rate__post_2_5': 'Firing rate: 2–5 s after stimulation',
        'temporal__early_fraction_0p25': 'Fraction of spikes before 1 s\n(out of spikes from 0.25–10 s)',
        'temporal__early_fraction_0p5': 'Fraction of spikes before 1 s\n(out of spikes from 0.5–10 s)',
        'temporal__peak_latency_0p25': 'Time of peak firing\n(search interval: 0.25–10 s)',
    }[name]

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    metadata, raw = load_units()
    coords, _ = project_units(raw)
    cfg = json.loads(CONFIG.read_text())
    state = np.load(cfg['frozen_model_npz'], allow_pickle=False)
    assert coords.shape == (1554, 2)
    x = raw[state['feature_names'].tolist()].to_numpy(float)
    transformed = np.sign(x)*np.log1p(np.abs(x))
    transformed = np.where(np.isnan(transformed), state['impute_median'], transformed)
    z = (transformed-state['scale_mean'])/state['scale_std']
    assert np.allclose(z@state['lda_projection'], coords, atol=1e-12)
    # Pearson correlations of actual fitted inputs with the two frozen axes.
    xc = z-z.mean(axis=0)
    yc = coords-coords.mean(axis=0)
    denom = np.sqrt((xc**2).sum(axis=0)[:, None]*(yc**2).sum(axis=0)[None, :])
    corr = np.divide(xc.T@yc, denom, out=np.full((215, 2), np.nan), where=denom>0)
    names = state['feature_names'].tolist()
    structure = pd.DataFrame({'metric': names, 'block': ['original']*87+['added_burst']*128,
                              'LD1_r': corr[:, 0], 'LD2_r': corr[:, 1]})
    structure.to_csv(OUT/'structure_coefficients_all_215.csv', index=False)
    # Curated distinct activity patterns, not an arbitrary top-N correlation list.
    representatives = {
        'delta__post_025_05': 'Early evoked rate change; strongest LD1 association.',
        'burst_t010_n3__pre5__rate_hz': 'Fast baseline bursting; negative LD1 association.',
        'burst_t100_n5__post5__duration_mean': 'Post-stim burst duration; positive LD1 association.',
        'rate__post_05_1': 'Early post-stim firing level; positive LD2 association.',
        'burst_t100_n3__late__first_burst_latency': 'Post-stim burst timing; strongest negative LD2 association.',
        'burst_t050_n3__post10__interburst_gap_mean': 'Spacing between post-stim bursts; negative LD2 association.',
    }
    chosen = [names.index(name) for name in representatives]
    displayed = structure.iloc[chosen].copy()
    displayed['plain_english_label'] = [label(names[i]).replace('\n', ' ') for i in chosen]
    displayed['display_rationale'] = list(representatives.values())
    displayed.to_csv(OUT/'displayed_structure_coefficients.csv', index=False)
    coordtable = metadata[['recording_id', 'unit_id', 'construct']].copy()
    coordtable['LD1'], coordtable['LD2'] = coords.T
    coordtable.to_csv(OUT/'unit_ld_coordinates.csv', index=False)
    summaries = []
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 8,
                         'axes.titlesize': 10, 'axes.labelsize': 9,
                         'pdf.fonttype': 42, 'ps.fonttype': 42})
    fig = plt.figure(figsize=(14.5, 11.5))
    grid = fig.add_gridspec(3, 3, width_ratios=[1.4, 1, 1], height_ratios=[1.35, 1, .65],
                           left=.31, right=.98, bottom=.09, top=.88, wspace=.65, hspace=.70)
    heat = fig.add_subplot(grid[:2, 0])
    im = heat.imshow(corr[chosen], cmap='RdBu_r', vmin=-1, vmax=1, aspect='auto')
    heat.set_yticks(np.arange(len(chosen)), [label(names[i]) for i in chosen], fontsize=8)
    heat.set_xticks([0, 1], ['LD1', 'LD2'])
    heat.tick_params(length=0)
    heat.set_title('Measurements associated\nwith each axis', pad=16)
    heat.set_xlabel('LDA axis')
    for row, index in enumerate(chosen):
        for j in range(2):
            r = corr[index, j]
            heat.text(j, row, f'{r:.2f}', ha='center', va='center', fontsize=9,
                      color='white' if abs(r)>.60 else '#222222')
    bar = fig.colorbar(im, ax=heat, orientation='horizontal', fraction=.035, pad=.10,
                       ticks=[-1, -.5, 0, .5, 1])
    bar.set_label('Blue: lower score with more of this measurement\nRed: higher score with more of this measurement', fontsize=7)
    heat.text(-.16, 1.04, 'a', transform=heat.transAxes, fontsize=13, fontweight='bold')
    scatter = fig.add_subplot(grid[0, 1:])
    rng = np.random.default_rng(42)
    for group, color in zip(GROUPS, COLORS):
        mask = metadata['construct'].to_numpy()==group
        values = coords[mask]
        scatter.scatter(*values.T, s=8, c=color, alpha=.35, linewidths=0,
                        label=f'{group} (n = {mask.sum()})', rasterized=True)
        center = values.mean(axis=0)
        for recording in metadata.loc[mask, 'recording_id'].unique():
            center_r = coords[metadata['recording_id'].to_numpy()==recording].mean(axis=0)
            scatter.scatter(*center_r, marker='o', s=35, color=color, linewidths=0, zorder=4)
        dark = tuple(np.array(matplotlib.colors.to_rgb(color))*.55)
        scatter.scatter(*center, marker='o', s=100, color=dark, edgecolor='#111111', linewidth=1.2, zorder=10)
        for j in range(2):
            summaries.append({'construct': group, 'axis': f'LD{j+1}', 'n_units': len(values),
                              'mean': center[j], 'sd': values[:, j].std(ddof=1),
                              'median': np.median(values[:, j])})
    scatter.axhline(0, color='#dddddd', lw=.6, zorder=0)
    scatter.axvline(0, color='#dddddd', lw=.6, zorder=0)
    scatter.set(xlabel='LD1', ylabel='LD2', title='Unit projections onto the locked LDA')
    scatter.legend(frameon=False, fontsize=7, loc='best', markerscale=1.5)
    scatter.text(.02, .02, 'Filled circles: recording / dark group centroids', transform=scatter.transAxes, fontsize=7)
    scatter.text(-.13, 1.07, 'b', transform=scatter.transAxes, fontsize=13, fontweight='bold')
    for j in range(2):
        ax = fig.add_subplot(grid[1, j+1])
        for c, (group, color) in enumerate(zip(GROUPS, COLORS)):
            values = coords[metadata['construct'].to_numpy()==group, j]
            violin = ax.violinplot(values, positions=[c], widths=.75, showextrema=False, bw_method='scott')
            violin['bodies'][0].set(facecolor=color, edgecolor='none', alpha=.18)
            ax.scatter(c+rng.uniform(-.23, .23, len(values)), values, c=color, s=4, alpha=.40,
                       linewidths=0, rasterized=True)
            ax.plot([c-.30, c+.30], [values.mean()]*2, color='#222222', lw=1.8, zorder=4)
        ax.set_xticks(range(4), GROUPS, rotation=40, ha='right', fontsize=7)
        ax.set(ylabel=f'LD{j+1} score', title=f'LD{j+1} distributions')
        ax.set_xlim(-.6, 3.6)
        ax.text(-.23, 1.08, chr(ord('c')+j), transform=ax.transAxes, fontsize=13, fontweight='bold')
    for ax in [scatter, *fig.axes[-2:]]:
        ax.spines[['top', 'right']].set_visible(False)
    guide = fig.add_subplot(grid[2, 1:])
    guide.axis('off')
    guide.set_title('How to read the axes in this dataset', loc='left', pad=12)
    guide.text(0, .93,
        'Higher LD1 scores tend to accompany:\n'
        '• Larger early firing-rate increases (0.25–0.5 s).\n'
        '• Longer post-stim bursts and fewer fast baseline bursts.\n\n'
        'Higher LD2 scores tend to accompany:\n'
        '• More firing at 0.5–1 s and earlier bursts after 0.5 s.\n'
        '• Shorter pauses between post-stim bursts.\n\n'
        'These describe associations across units, not physical axis units.',
        transform=guide.transAxes, va='top', fontsize=8, linespacing=1.4)
    fig.suptitle('Actuators + effectors | Locked 215-metric unit LDA', fontsize=15, y=.97)
    fig.text(.56, .935, '87 original + 128 burst metrics • 1,554 units • stimulation begins at 0 s',
             ha='center', fontsize=9)
    fig.text(.56, .015, 'Each dot = one unit (SUA/MUA pooled). Filled circles = recording/group centroids; black bars = means.\n'
             'Supervised full-data descriptive fit; identical frozen LD1/LD2 coordinates. No model refit.',
             ha='center', fontsize=8)
    for suffix in ['png', 'pdf']:
        fig.savefig(OUT/f'locked_215_lda_reference_style.{suffix}', dpi=350, facecolor='white')
    plt.close(fig)
    pd.DataFrame(summaries).to_csv(OUT/'axis_group_summaries.csv', index=False)
    manifest = {'model_retrained': False, 'axes': ['LD1', 'LD2'], 'units': len(raw),
                'structure_definition': 'Pearson correlation of frozen preprocessed inputs with frozen LD coordinates',
                'display_rule': 'Curated representatives of six distinct activity patterns; not top-N or model feature reselection',
                'display_representatives': representatives,
                'sources': {str(p): sha(p) for p in [CONFIG, Path(cfg['frozen_raw_metrics_csv']),
                             Path(cfg['frozen_model_npz']), Path(__file__)]}}
    manifest['outputs'] = {p.name: sha(p) for p in OUT.iterdir() if p.suffix in ['.csv', '.png', '.pdf']}
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'COMPLETE {OUT}; {len(chosen)} displayed metrics; coordinates unchanged', flush=True)

if __name__ == '__main__':
    main()
