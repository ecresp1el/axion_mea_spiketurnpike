"""Pre-stim unit rates, control comparisons, window sweep, and baseline-only LDA."""
import csv
import gzip
import json
import warnings
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
from scipy.stats import mannwhitneyu
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.impute import SimpleImputer
from sklearn.metrics import balanced_accuracy_score,roc_auc_score
from sklearn.model_selection import StratifiedKFold,StratifiedShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import explore_mcs_actuator_separation as base
from explore_mcs_burst_lda import CorrelationPrunedSelector,burst_summary
import explore_mcs_burst_lda as burst_definitions

OUT=Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/prestim_baseline')
CLASSES=base.CLASSES
WIDTHS=[.25,.5,1.,2.,5.,10.,20.]
OFFSETS=[0.,.25,.5,1.,2.,5.,10.,15.]
WINDOWS=[(w,o) for w in WIDTHS for o in OFFSETS if w+o<=20]

def window_name(w,o):
    return f'rate_pre_{w+o:g}_to_{o:g}s'

def compare(x,c):
    x=x[np.isfinite(x)];c=c[np.isfinite(c)]
    if len(x)<2 or len(c)<2:
        return dict(p=1.,cliff_delta=0.,mean_difference=np.nan,median_difference=np.nan,
                    group_n=len(x),control_n=len(c))
    result=mannwhitneyu(x,c,alternative='two-sided',method='asymptotic')
    return dict(p=float(result.pvalue),cliff_delta=float(2*result.statistic/(len(x)*len(c))-1),
                mean_difference=float(x.mean()-c.mean()),median_difference=float(np.median(x)-np.median(c)),
                group_n=len(x),control_n=len(c))

def holm(rows):
    order=np.argsort([r['p'] for r in rows]);last=0.
    for rank,index in enumerate(order):
        last=max(last,min(1.,rows[index]['p']*(len(rows)-rank)))
        rows[index]['adjusted_p']=last
        rows[index]['clear_flag']=last<.05 and abs(rows[index]['cliff_delta'])>=.3

def best_window(rates,y):
    candidates=[]
    for j,(w,o) in enumerate(WINDOWS):
        effects=[abs(compare(rates[y==c,j],rates[y==0,j])['cliff_delta']) for c in [1,2,3]]
        candidates.append((min(effects),w,-o,j))
    return max(candidates)[-1]

def lda_pipeline(k,shrink):
    return Pipeline([('impute',SimpleImputer(strategy='median',keep_empty_features=True)),
        ('scale',StandardScaler()),('select',CorrelationPrunedSelector(k=k)),
        ('lda',LinearDiscriminantAnalysis(solver='lsqr',shrinkage=shrink))])

def tune_lda(x,y,seed):
    splits=list(StratifiedShuffleSplit(2,test_size=.25,random_state=seed).split(x,y))
    results=[]
    for k in [16,32,64]:
        for shrink in [.01,.1,'auto']:
            scores=[]
            for train,test in splits:
                model=lda_pipeline(k,shrink)
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore');model.fit(x[train],y[train])
                scores.append(balanced_accuracy_score(y[test],model.predict(x[test])))
            results.append((float(np.mean(scores)),k,shrink))
    return max(results,key=lambda r:r[0])[1:]

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=list(csv.DictReader((base.OUT/'unit_metrics.csv').open()))
    record_map={r['recording_id']:r for r in csv.DictReader((base.REPO/'metadata/mcs_recording_biology.csv').open())}
    y=np.array([CLASSES.index(r['construct']) for r in rows])
    rates=np.zeros((len(rows),len(WINDOWS)))
    old_names=[n for n in rows[0] if n.startswith('rate__pre') or n.endswith('_pre') or n=='delta__pre_drift'
               or n.startswith('bin__') and int(n.split('__')[1])<10]
    archive=np.load(base.OUT/'burst_lda/burst_metrics.npz',allow_pickle=False)
    assert np.array_equal(archive['unit_id'],np.array([r['unit_id'] for r in rows]))
    assert np.array_equal(archive['recording_id'],np.array([r['recording_id'] for r in rows]))
    added_names=[n for n in archive['names'].tolist() if '__pre5__' in n or '__pre10__' in n]
    old=np.empty((len(rows),len(old_names)))
    added=np.empty((len(rows),len(added_names)))
    groups={}
    for i,r in enumerate(rows):groups.setdefault(r['recording_id'],[]).append((i,r))
    extra_names=None;extra_values=None
    for rid,units in groups.items():
        record=record_map[rid];onset=float(units[0][1]['event_time_s']);assert onset>=20
        files=list((Path(record['sorting_output_path'])/'curated').glob('*/numpysorting_info.json'));assert len(files)==1
        info=json.loads(files[0].read_text());assert info['num_segments']==1
        fs=float(info['sampling_frequency']);spikes=np.load(files[0].parent/'spikes.npy',mmap_mode='r')
        first_stim_sample=int(np.ceil(onset*fs-1e-7))
        lo,hi=np.searchsorted(spikes['sample_index'],[(onset-20)*fs,first_stim_sample])
        window=spikes[lo:hi];relative=window['sample_index']/fs-onset
        assert np.all(window['sample_index']<first_stim_sample)
        index={str(uid):i for i,uid in enumerate(info['unit_ids'])}
        for i,r in units:
            t=relative[window['unit_index']==index[r['unit_id']]]
            t=t[(t>=-20)&(t<0)]
            for j,(width,offset) in enumerate(WINDOWS):
                rates[i,j]=np.sum((t>=-offset-width)&(t<-offset))/width
            # Recompute baseline descriptors from strictly pre-onset spikes;
            # no cached post-stim values enter this analysis.
            original_features=base.metrics(t)
            added_features=burst_definitions.burst_metrics(t)
            old[i]=[original_features[n] for n in old_names]
            added[i]=[added_features[n] for n in added_names]
            extra={}
            for threshold in [.025,.05,.1]:
                values=burst_summary(t,-20,0,threshold,3)
                extra.update({f'baseline20_burst_{int(threshold*1000)}ms__{k}':v for k,v in values.items()})
            if extra_names is None:
                extra_names=list(extra);extra_values=np.empty((len(rows),len(extra_names)))
            extra_values[i]=[extra[n] for n in extra_names]
        print('Baseline extracted',rid,flush=True)
    names=[window_name(w,o) for w,o in WINDOWS]+old_names+added_names+extra_names
    raw=np.column_stack([rates,old,added,extra_values])
    assert np.all(np.isfinite(raw)|np.isnan(raw)) and len(names)==len(set(names))
    assert not any('__post' in n or '__change' in n or '__late' in n for n in names)
    np.savez_compressed(OUT/'baseline_unit_metrics.npz',values=raw,names=np.array(names),
        recording_id=np.array([r['recording_id'] for r in rows]),unit_id=np.array([r['unit_id'] for r in rows]),
        construct=np.array([r['construct'] for r in rows]))
    stats=[]
    for j,n in enumerate(names):
        for c in [1,2,3]:
            effect=compare(raw[y==c,j],raw[y==0,j])
            stats.append(dict(metric=n,construct=CLASSES[c],**effect))
    holm(stats)
    base.write_csv(OUT/'baseline_control_comparisons.csv',stats)
    rate_stats=[r for r in stats if r['metric'] in names[:len(WINDOWS)]]
    best=best_window(rates,y);standard=WINDOWS.index((10.,0.))
    folds=list(StratifiedKFold(3,shuffle=True,random_state=20261114).split(raw,y))
    x=np.sign(raw)*np.log1p(np.abs(raw));pred=np.full(len(y),-1);fold_info=[]
    window_validation=[]
    for fold,(train,test) in enumerate(folds):
        selected=best_window(rates[train],y[train])
        for c in [1,2,3]:
            train_effect=compare(rates[train][y[train]==c,selected],rates[train][y[train]==0,selected])['cliff_delta']
            pair=test[np.isin(y[test],[0,c])]
            auc=roc_auc_score((y[pair]==c).astype(int),rates[pair,selected]*(1 if train_effect>=0 else -1))
            window_validation.append(dict(fold=fold,construct=CLASSES[c],selected_window=names[selected],auc=float(auc)))
        k,shrink=tune_lda(x[train],y[train],210+fold);model=lda_pipeline(k,shrink)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore');model.fit(x[train],y[train])
        pred[test]=model.predict(x[test]);fold_info.append(dict(fold=fold,k=k,shrinkage=shrink))
        print('Baseline unit fold',fold,k,shrink,flush=True)
    lda_score=float(balanced_accuracy_score(y,pred))
    k,shrink=tune_lda(x,y,41);model=lda_pipeline(k,shrink)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore');z=model[:-1].fit_transform(x,y)
    lda=LinearDiscriminantAnalysis(solver='eigen',shrinkage=shrink,n_components=2).fit(z,y)
    coords=lda.transform(z);selected_names=np.array(names)[model.named_steps['select'].get_support()].tolist()
    summary=dict(units=len(rows),baseline_only=True,strict_preonset_sample_boundary=True,
        common_precoverage_s=20,rate_windows=len(WINDOWS),
        baseline_metrics=len(names),selection_rule='Maximize the weakest absolute Cliff delta of the three actuator-versus-Control comparisons',
        best_window=names[best],best_window_width_s=WINDOWS[best][0],best_window_ends_before_stim_s=WINDOWS[best][1],
        significance_correction=f'Holm across all {len(stats)} metric/control comparisons',clear_flag='adjusted p <0.05 and absolute Cliff delta >=0.3',
        window_consistency={},nested_selected_window_auc=window_validation,
        baseline_lda_nested_unit_balanced_accuracy=lda_score,lda_folds=fold_info,
        descriptive_lda_inputs=selected_names)
    for c in [1,2,3]:
        group=[r for r in rate_stats if r['construct']==CLASSES[c]]
        summary['window_consistency'][CLASSES[c]]=dict(clear_windows=sum(r['clear_flag'] for r in group),
            windows=len(group),min_cliff_delta=min(r['cliff_delta'] for r in group),max_cliff_delta=max(r['cliff_delta'] for r in group),
            positive_windows=sum(r['cliff_delta']>0 for r in group),negative_windows=sum(r['cliff_delta']<0 for r in group))
    summary['windows_clear_for_all_three']=[names[j] for j in range(len(WINDOWS)) if all(
        next(r for r in rate_stats if r['metric']==names[j] and r['construct']==CLASSES[c])['clear_flag'] for c in [1,2,3])]
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    base.write_csv(OUT/'selected_window_unit_validation.csv',window_validation)
    color=['#777777','#e94b47','#64af54','#9462d5'];rng=np.random.default_rng(42)
    fig,axes=plt.subplots(2,2,figsize=(13,10))
    for ax,j,title in [(axes[0,0],standard,'Standard baseline: −10 to 0 s'),
                        (axes[0,1],best,f'Exploratory strongest shared window: −{WINDOWS[best][0]+WINDOWS[best][1]:g} to −{WINDOWS[best][1]:g} s')]:
        for c,label in enumerate(CLASSES):
            values=rates[y==c,j]
            box=ax.boxplot([values],positions=[c],widths=.5,showfliers=False,patch_artist=True,manage_ticks=False,
                           medianprops={'color':'black','linewidth':1.5})
            box['boxes'][0].set_facecolor(color[c]);box['boxes'][0].set_alpha(.3)
            ax.scatter(c+rng.uniform(-.18,.18,len(values)),values,s=7,color=color[c],alpha=.35,linewidths=0)
        ax.set_yscale('symlog',linthresh=1);ax.set_ylim(bottom=0)
        ax.set_xticks(range(4),[f'{c}\nn={np.sum(y==i)}' for i,c in enumerate(CLASSES)])
        ax.set_title(title,fontsize=11);ax.set_ylabel('Pre-stim firing rate (Hz/unit; symlog)')
        ax.spines[['top','right']].set_visible(False)
    effects=np.array([[next(r['cliff_delta'] for r in rate_stats if r['construct']==CLASSES[c] and r['metric']==n)
                       for n in names[:len(WINDOWS)]] for c in [1,2,3]])
    image=axes[1,0].imshow(effects,aspect='auto',cmap='RdBu_r',vmin=-1,vmax=1)
    axes[1,0].set_yticks(range(3),CLASSES[1:])
    axes[1,0].set_xticks(range(len(WINDOWS)),[f'−{w+o:g}:−{o:g}' for w,o in WINDOWS],rotation=90,fontsize=6)
    axes[1,0].add_patch(Rectangle((best-.5,-.5),1,3,fill=False,edgecolor='black',lw=1.5))
    axes[1,0].set_title('Every window versus Control: rank effect size',fontsize=11)
    axes[1,0].set_xlabel('Baseline window start:end (seconds)')
    fig.colorbar(image,ax=axes[1,0],shrink=.65,label='Cliff δ: positive = actuator higher')
    for c,label in enumerate(CLASSES):
        axes[1,1].scatter(coords[y==c,0],coords[y==c,1],s=8,color=color[c],alpha=.35,linewidths=0,label=label)
    axes[1,1].set_title(f'Baseline-only LDA; held-out units {lda_score:.1%}',fontsize=11)
    axes[1,1].set_xlabel('LD1');axes[1,1].set_ylabel('LD2');axes[1,1].legend(frameon=False,fontsize=8)
    axes[1,1].spines[['top','right']].set_visible(False)
    fig.suptitle('Actuators + effectors: differences already present before e-stim',fontsize=15)
    fig.text(.5,.018,'Each dot = one unit; SUA/MUA pooled; all comparisons use 371 Control. No post-stim features are used.\n'
        'Top boxes = median/IQR. Strongest window is exploratory; the full sweep is shown below. Rate axes are linear 0–1 Hz, log above.\n'
        'LDA cloud = supervised full-data fit; accuracy = nested held-out-unit validation. Pre-stim does not establish pre-chemical-treatment status.',
        ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.09,1,.95));fig.savefig(OUT/'prestim_baseline_comparison.png',dpi=220);plt.close(fig)
    lines=['# Pre-stim baseline differences','',f'{len(rows)} units; Actuators + effectors only; first e-stim marker = t0; SUA/MUA pooled.',
           'This measures baseline before e-stim, not necessarily before chemical exposure. Dates and identities are not predictors.',
           'All baseline descriptors are recomputed from spikes strictly before the first stimulation sample, with a sub-sample rounding tolerance to exclude onset spikes.',
           '', '## Rate window search','',f'{len(WINDOWS)} windows entirely inside the common 20-second pre-stim interval.',
           f"Strongest shared window: {names[best]}. Selection maximizes the weakest absolute Cliff delta across all three comparisons with Control.",
           'This is effect-size optimization, not minimization of p values. No units are filtered to obtain separation.',
           '', '| Construct | Clear windows / tested | Minimum Cliff delta | Maximum Cliff delta |', '| --- | ---: | ---: | ---: |']
    for label,v in summary['window_consistency'].items():
        lines.append(f"| {label} | {v['clear_windows']} / {v['windows']} | {v['min_cliff_delta']:+.3f} | {v['max_cliff_delta']:+.3f} |")
    lines += ['', f"Clear = adjusted p <0.05 and |Cliff delta| ≥0.3. {summary['significance_correction']}.",
              f"Windows meeting that rule for all three: {summary['windows_clear_for_all_three']}.",
              'Positive Cliff delta means higher activity in the actuator group than Control; zero means no rank separation.',
              'Rates include zero-rate units. Conditional burst/ISI statistics omit undefined values only for their individual univariate comparisons;',
              'group_n and control_n are reported. LDA includes all units using training-only median imputation.',
              '', '## What differs from Control','']
    for c in [1,2,3]:
        group=[r for r in stats if r['construct']==CLASSES[c] and r['group_n']>=.8*np.sum(y==c) and r['control_n']>=.8*np.sum(y==0)]
        group.sort(key=lambda r:abs(r['cliff_delta']),reverse=True)
        lines += [f'### {CLASSES[c]}','', '| Metric | Cliff delta | Median difference | Adjusted p |','| --- | ---: | ---: | ---: |']
        for r in group[:10]:lines.append(f"| `{r['metric']}` | {r['cliff_delta']:+.3f} | {r['median_difference']:+.3g} | {r['adjusted_p']:.3g} |")
    lines += ['', '## Baseline-only LDA','',f'Nested held-out-unit balanced accuracy: {lda_score:.1%}.',
              'Three stratified unit folds repeat preprocessing, correlation-pruned feature selection, and shrinkage LDA tuning within training units.',
              'Only pre-stim rates, pre-stim ISI/burst structure, pre-stim bins, and baseline drift are allowed. Post-stim columns are excluded explicitly.',
              'This is a separate baseline diagnostic; the active 215-feature pre/post LDA remains unchanged.',
              '', 'Selected descriptive full-data LDA inputs:', '']+['- `'+n+'`' for n in selected_names]
    lines += ['', '## Files','',
              'baseline_unit_metrics.npz: raw baseline values/names, recording/unit keys, and construct labels.',
              'baseline_control_comparisons.csv: every metric versus Control, effect sizes, raw/adjusted p values, valid counts, and clear flags.',
              'selected_window_unit_validation.csv: held-out-unit AUC after selecting the window on training units only.',
              'summary.json: window consistency, all fold settings, and selected metrics. One PNG only.',
              'Source: scripts/explore_mcs_prestim_baseline.py. All artifacts are on scratch. No continuous signals are loaded or copied.']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n')
    print('COMPLETE',json.dumps({k:v for k,v in summary.items() if k in ['best_window','window_consistency','baseline_lda_nested_unit_balanced_accuracy','windows_clear_for_all_three']}),flush=True)

if __name__=='__main__':
    main()
