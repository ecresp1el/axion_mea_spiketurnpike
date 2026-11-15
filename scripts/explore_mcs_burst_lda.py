"""Expand per-unit burst features and compare LDA using nested unit validation."""
import csv
import json
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.impute import SimpleImputer
from sklearn.metrics import balanced_accuracy_score, confusion_matrix
from sklearn.model_selection import StratifiedKFold, StratifiedShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import explore_mcs_actuator_separation as base

OUT = base.OUT/'burst_lda'
THRESHOLDS = [.01,.025,.05,.1,.2]
MIN_SPIKES = [3,5]
DECORRELATE = '--decorrelate' in sys.argv
WINDOWS = {'pre5':(-5,0), 'pre10':(-10,0), 'post5':(0,5),
           'post10':(0,10), 'late':(.5,10)}

def burst_summary(spikes, start, stop, threshold, minimum):
    s=spikes[(spikes>=start)&(spikes<stop)]
    # Recording-relative subtraction can shift a nominal threshold by rounding.
    cuts=np.flatnonzero(np.diff(s)>threshold+1e-12)+1
    runs=np.split(s,cuts) if len(s) else []
    bursts=[r for r in runs if len(r)>=minimum]
    duration=stop-start
    n=len(bursts)
    lengths=np.array([r[-1]-r[0] for r in bursts])
    sizes=np.array([len(r) for r in bursts])
    gaps=np.array([b[0]-a[-1] for a,b in zip(bursts,bursts[1:])])
    within=np.concatenate([np.diff(r) for r in bursts]) if n else np.array([])
    return dict(
        count=n, rate_hz=n/duration, spike_fraction=float(sizes.sum()/len(s)) if len(s) else 0.,
        time_fraction=float(lengths.sum()/duration),
        duration_mean=float(lengths.mean()) if n else np.nan,
        duration_max=float(lengths.max()) if n else np.nan,
        duration_cv=float(lengths.std()/lengths.mean()) if n>1 and lengths.mean()>0 else np.nan,
        spikes_mean=float(sizes.mean()) if n else np.nan,
        spikes_max=float(sizes.max()) if n else np.nan,
        intraburst_hz=float(np.mean((sizes-1)/np.maximum(lengths,1e-9))) if n else np.nan,
        intraburst_isi_cv=float(within.std()/within.mean()) if len(within)>1 and within.mean()>0 else np.nan,
        interburst_gap_mean=float(gaps.mean()) if len(gaps) else np.nan,
        interburst_gap_cv=float(gaps.std()/gaps.mean()) if len(gaps)>1 and gaps.mean()>0 else np.nan,
        first_burst_latency=float(bursts[0][0]-start) if n else np.nan,
    )

def burst_metrics(t):
    d={}
    for threshold in THRESHOLDS:
        for minimum in MIN_SPIKES:
            prefix=f'burst_t{int(threshold*1000):03d}_n{minimum}'
            stats={w:burst_summary(t,a,b,threshold,minimum) for w,(a,b) in WINDOWS.items()}
            for window,values in stats.items():
                for name,value in values.items():
                    d[f'{prefix}__{window}__{name}']=value
            for post,pre in [('post5','pre5'),('post10','pre10'),('late','pre10')]:
                for name in stats[post]:
                    if name in ['count','first_burst_latency']:
                        continue
                    d[f'{prefix}__change_{post}__{name}']=stats[post][name]-stats[pre][name]
    for window,(a,b) in WINDOWS.items():
        s=t[(t>=a)&(t<b)]
        isi=np.diff(s)
        prefix='structure__'+window+'__'
        for q in [10,25,50,75,90]:
            d[prefix+'isi_q'+str(q)]=float(np.percentile(isi,q)) if len(isi) else np.nan
        d[prefix+'burstiness']=(float((isi.std()-isi.mean())/(isi.std()+isi.mean()))
                                if len(isi)>1 and isi.mean()>0 else np.nan)
        d[prefix+'log_isi_sd']=float(np.std(np.log(np.maximum(isi,1e-9)))) if len(isi)>1 else np.nan
        d[prefix+'isi_serial_correlation']=(float(np.corrcoef(isi[:-1],isi[1:])[0,1])
            if len(isi)>3 and isi[:-1].std()>0 and isi[1:].std()>0 else np.nan)
        for pause in [.2,.5,1.]:
            d[prefix+'pause_fraction_'+str(pause)]=float(np.mean(isi>pause)) if len(isi) else np.nan
        for width in [.05,.1,.25,.5,1.]:
            edges=np.arange(a,b+1e-9,width)
            counts=np.histogram(s,edges)[0]
            tag=str(width)
            d[prefix+'fano_'+tag]=float(counts.var()/counts.mean()) if counts.mean()>0 else 0.
            d[prefix+'active_fraction_'+tag]=float(np.mean(counts>0))
            d[prefix+'peak_rate_'+tag]=float(counts.max()/width)
    return d

def extract(rows):
    mapping={r['recording_id']:r for r in csv.DictReader((base.REPO/'metadata/mcs_recording_biology.csv').open())}
    by_recording={}
    for i,r in enumerate(rows):
        by_recording.setdefault(r['recording_id'],[]).append((i,r))
    names=None
    data=None
    for rid,observations in by_recording.items():
        record=mapping[rid]
        onset=min(json.loads(record['pulse_start_times_s']))
        files=list((Path(record['sorting_output_path'])/'curated').glob('*/numpysorting_info.json'))
        assert len(files)==1
        info=json.loads(files[0].read_text())
        fs=info['sampling_frequency']
        spikes=np.load(files[0].parent/'spikes.npy',mmap_mode='r')
        lo,hi=np.searchsorted(spikes['sample_index'],[(onset-10)*fs,(onset+10)*fs])
        window=spikes[lo:hi]
        relative=window['sample_index']/fs-onset
        unit_indices={str(uid):i for i,uid in enumerate(info['unit_ids'])}
        for index,r in observations:
            t=relative[window['unit_index']==unit_indices[r['unit_id']]]
            values=burst_metrics(t)
            if names is None:
                names=list(values)
                data=np.empty((len(rows),len(names)))
            data[index]=[values[n] for n in names]
        print('Burst metrics extracted',rid,flush=True)
    np.savez_compressed(OUT/'burst_metrics.npz',values=data,names=np.array(names),
                        recording_id=np.array([r['recording_id'] for r in rows]),
                        unit_id=np.array([r['unit_id'] for r in rows]))
    base.write_csv(OUT/'burst_metric_catalog.csv',[dict(metric=n,missing_units=int(np.isnan(data[:,i]).sum()))
                   for i,n in enumerate(names)])
    return names,data

def families(old_names,new_names):
    old=len(old_names)
    all_names=old_names+new_names
    sets={'original':list(range(old)), 'expanded':list(range(len(all_names))),
          'bursts_only':[old+i for i,n in enumerate(new_names) if n.startswith('burst_')],
          'burst_changes':[old+i for i,n in enumerate(new_names) if '__change_' in n],
          'structure':[old+i for i,n in enumerate(new_names) if n.startswith('structure__')],
          'late_bursts':[old+i for i,n in enumerate(new_names) if '__late__' in n or '__change_late__' in n]}
    for threshold in THRESHOLDS:
        prefix=f'burst_t{int(threshold*1000):03d}_'
        sets[prefix+'plus_original']=list(range(old))+[old+i for i,n in enumerate(new_names) if n.startswith(prefix)]
    # Distinguish one short-ISI threshold from changes combining many thresholds.
    sets['changes_plus_original']=list(range(old))+sets['burst_changes']
    sets['late_plus_original']=base.feature_sets(old_names)['artifact_reduced']+sets['late_bursts']
    return sets

class CorrelationPrunedSelector(BaseEstimator, TransformerMixin):
    """Train-only F ranking followed by removal of near-duplicate features."""
    def __init__(self,k=64,max_correlation=.9,max_candidates=400):
        self.k=k
        self.max_correlation=max_correlation
        self.max_candidates=max_candidates

    def fit(self,x,y):
        self.scores_,_=f_classif(x,y)
        scores=np.nan_to_num(self.scores_,nan=-np.inf,posinf=1e30)
        order=np.argsort(-scores,kind='stable')
        order=np.array([i for i in order if x[:,i].std()>1e-10])[:self.max_candidates]
        corr=np.atleast_2d(np.corrcoef(x[:,order],rowvar=False))
        keep=[]
        positions=[]
        for position,index in enumerate(order):
            if not positions or np.all(np.abs(corr[position,positions])<self.max_correlation):
                positions.append(position)
                keep.append(index)
            if len(keep)>=self.k:
                break
        self.support_=np.zeros(x.shape[1],dtype=bool)
        self.support_[keep]=True
        if not keep:
            raise ValueError('No variable predictors remain')
        return self

    def transform(self,x):
        return x[:,self.support_]

    def get_support(self):
        return self.support_

def pipeline(config,sets):
    family,k,shrink=config
    cols=sets[family]
    clf=LinearDiscriminantAnalysis(solver='lsqr',shrinkage=shrink)
    return cols,Pipeline([('impute',SimpleImputer(strategy='median',keep_empty_features=True)),
                          ('scale',StandardScaler()),
                          ('select',CorrelationPrunedSelector(k=min(k,len(cols))) if DECORRELATE
                           else SelectKBest(f_classif,k=min(k,len(cols)))),('lda',clf)])

def tune(x,y,sets,configs,seed):
    splits=list(StratifiedShuffleSplit(n_splits=2,test_size=.25,random_state=seed).split(x,y))
    results=[]
    for config in configs:
        cols,model=pipeline(config,sets)
        scores=[]
        for train,test in splits:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                model.fit(x[train][:,cols],y[train])
            scores.append(balanced_accuracy_score(y[test],model.predict(x[test][:,cols])))
        results.append((float(np.mean(scores)),config))
    results.sort(key=lambda r:r[0],reverse=True)
    return results[0][1],results

def validate(x,y,sets,configs,task):
    pred=np.full(len(y),-1)
    folds=[]
    for fold,(train,test) in enumerate(StratifiedKFold(3,shuffle=True,random_state=20261114).split(x,y)):
        best,_=tune(x[train],y[train],sets,configs,210+fold)
        cols,model=pipeline(best,sets)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            model.fit(x[train][:,cols],y[train])
        pred[test]=model.predict(x[test][:,cols])
        folds.append(dict(fold=fold,config=best,accuracy=float(balanced_accuracy_score(y[test],pred[test]))))
        print(task,'fold',fold,folds[-1],flush=True)
    assert np.all(pred>=0)
    return dict(balanced_accuracy=float(balanced_accuracy_score(y,pred)),folds=folds),pred

def draw(x,y,sets,configs,summary):
    fit_views=[]
    ranks=[]
    for label,candidates in [('Original metrics',[c for c in configs if c[0]=='original']),
                              ('Burst-expanded metrics',configs)]:
        if '--render' in sys.argv:
            best=tuple(summary[label]['config'])
            descriptive_score=summary[label]['descriptive_validation_score']
        else:
            best,results=tune(x,y,sets,candidates,41)
            descriptive_score=results[0][0]
        cols,fitted=pipeline(best,sets)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            z=fitted[:-1].fit_transform(x[:,cols],y)
        projection=LinearDiscriminantAnalysis(solver='eigen',shrinkage=best[2],n_components=2)
        coords=projection.fit_transform(z,y)
        selected=fitted.named_steps['select'].get_support()
        selected_names=[summary['metric_names'][cols[i]] for i in np.where(selected)[0]]
        summary[label]=dict(config=best,selected_metrics=selected_names,
                            descriptive_validation_score=descriptive_score)
        fit_views.append((label,coords))
        if label=='Burst-expanded metrics':
            scores=fitted.named_steps['select'].scores_
            ranks=[dict(metric=summary['metric_names'][cols[i]],selected=bool(selected[i]),
                        descriptive_f=float(np.nan_to_num(scores[i],nan=0,posinf=1e30))) for i in range(len(cols))]
    ranks.sort(key=lambda r:r['descriptive_f'],reverse=True)
    base.write_csv(OUT/'expanded_metric_ranking.csv',ranks)
    fig,axes=plt.subplots(1,3,figsize=(15,5.6))
    colors=['#7e7e7e','#e94b47','#64af54','#9462d5']
    for ax,(label,coords) in zip(axes[:2],fit_views):
        for c,name in enumerate(base.CLASSES):
            p=coords[y==c]
            ax.scatter(p[:,0],p[:,1],s=9,alpha=.4,color=colors[c],linewidths=0,label=f'{name}: {len(p)} units')
            vals,vecs=np.linalg.eigh(np.cov(p.T))
            ax.add_patch(Ellipse(p.mean(axis=0),2*np.sqrt(max(vals[-1],0)),2*np.sqrt(max(vals[0],0)),
                         angle=np.degrees(np.arctan2(vecs[1,-1],vecs[0,-1])),alpha=.13,
                         facecolor=colors[c],edgecolor=colors[c]))
        title=("Expanded search: original inputs retained" if label=='Burst-expanded metrics'
               and summary[label]['config'][0]=='original' else label+' — supervised LDA')
        ax.set_title(title,fontsize=11)
        ax.set_xlabel('LD1'); ax.set_ylabel('LD2')
        ax.axhline(0,color='gray',ls='--',lw=.5); ax.axvline(0,color='gray',ls='--',lw=.5)
        ax.spines[['top','right']].set_visible(False)
    axes[0].legend(fontsize=8,frameon=False)
    cm=np.array(summary['tasks']['four_class']['confusion_matrix'])
    percentages=cm/cm.sum(axis=1,keepdims=True)*100
    axes[2].imshow(percentages,vmin=0,vmax=100,cmap='Blues')
    for i in range(4):
        for j in range(4):
            axes[2].text(j,i,f'{percentages[i,j]:.1f}%\n({cm[i,j]})',ha='center',va='center',fontsize=8,
                         color='white' if percentages[i,j]>50 else 'black')
    axes[2].set_xticks(range(4),base.CLASSES,rotation=35,ha='right')
    axes[2].set_yticks(range(4),base.CLASSES)
    axes[2].set_xlabel('Predicted unit class');axes[2].set_ylabel('Actual unit class')
    score=summary['tasks']['four_class']['expanded']['balanced_accuracy']
    axes[2].set_title(f'Held-out units, LDA: {score:.1%}',fontsize=11)
    original=summary['tasks']['four_class']['original']['balanced_accuracy']
    fig.suptitle('Actuators + effectors: expanded burst metrics, LDA only',fontsize=15)
    fig.text(.5,.025,f'Each dot = one unit; SUA/MUA pooled. Original-metric LDA: {original:.1%}; burst-expanded LDA: {score:.1%} (nested unit validation).\n'
             'Burst ISI thresholds 10/25/50/100/200 ms; ≥3 or ≥5 spikes; pre/post 5 s, 10 s, and +0.5–10 s.\n'
             'Clouds are full-data supervised fits; ellipses = 1-SD unit spread. Right panel = held-out-unit predictions. No raw-signal artifact validation.',
             ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.15,1,.94))
    fig.savefig(OUT/'burst_lda.png',dpi=150)
    plt.close(fig)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=list(csv.DictReader((base.OUT/'unit_metrics.csv').open()))
    old_names=[r['metric'] for r in csv.DictReader((base.OUT/'metric_catalog.csv').open())]
    old=np.array([[float(r[n]) for n in old_names] for r in rows])
    if DECORRELATE and '--refresh-metrics' not in sys.argv:
        archive=np.load(OUT/'burst_metrics.npz',allow_pickle=False)
        assert np.array_equal(archive['recording_id'],np.array([r['recording_id'] for r in rows]))
        assert np.array_equal(archive['unit_id'],np.array([r['unit_id'] for r in rows]))
        new_names,new=archive['names'].tolist(),archive['values']
        (OUT/'first_pass_summary.json').write_text((OUT/'summary.json').read_text())
    else:
        new_names,new=extract(rows)
    names=old_names+new_names
    raw=np.column_stack([old,new])
    assert np.all(np.isfinite(raw)|np.isnan(raw))
    x=np.sign(raw)*np.log1p(np.abs(raw))
    original_y=np.array([base.CLASSES.index(r['construct']) for r in rows])
    sets=families(old_names,new_names)
    shrinkages=[.01,.1,.5,'auto'] if DECORRELATE else [.1,'auto']
    top_k=[24,64,128] if DECORRELATE else [32,96]
    configs=[(family,k,shrink) for family in sets for k in top_k for shrink in shrinkages]
    original_configs=[('original',k,shrink) for k in [16,32,64,96,128] for shrink in shrinkages]
    configs=list(dict.fromkeys(configs+original_configs))
    summary=dict(units=len(rows),original_metrics=len(old_names),added_metrics=len(new_names),
                 metric_names=names,candidate_lda_models=len(configs),
                 correlation_pruning=DECORRELATE,correlation_threshold=.9 if DECORRELATE else None,tasks={})
    output_rows=[]
    predictions=[{k:r[k] for k in ['recording_id','unit_id','construct']} for r in rows]
    tasks=['four_class','DREADD_vs_Control','LMO_vs_Control','PSAM_vs_Control',
           'DREADD_vs_others','LMO_vs_others','PSAM_vs_others']
    for task in tasks:
        if task=='four_class':
            mask=np.ones(len(rows),dtype=bool);y=original_y
        elif task.endswith('_vs_Control'):
            target=task.split('_vs_')[0]
            mask=np.isin(original_y,[0,base.CLASSES.index(target)]);y=original_y[mask]
        else:
            mask=np.ones(len(rows),dtype=bool)
            y=(original_y==base.CLASSES.index(task.split('_vs_')[0])).astype(int)
        xx=x[mask]
        print('LDA comparison',task,'units',len(y),'total metrics',len(names),flush=True)
        original_score,_=validate(xx,y,sets,original_configs,task+' original')
        expanded_score,pred=validate(xx,y,sets,configs,task+' expanded')
        cm=confusion_matrix(y,pred)
        summary['tasks'][task]=dict(original=original_score,expanded=expanded_score,confusion_matrix=cm.tolist())
        for i,p in zip(np.where(mask)[0],pred):
            predictions[i][task]=int(p)
        for i in np.where(~mask)[0]:
            predictions[i][task]=''
        output_rows.append(dict(comparison=task,units=len(y),original_lda=original_score['balanced_accuracy'],
                           expanded_lda=expanded_score['balanced_accuracy'],
                           change_percentage_points=100*(expanded_score['balanced_accuracy']-original_score['balanced_accuracy'])))
        (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
        print('RESULT',output_rows[-1],flush=True)
    base.write_csv(OUT/'lda_comparisons.csv',output_rows)
    base.write_csv(OUT/'unit_predictions.csv',predictions)
    draw(x,original_y,sets,configs,summary)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    lines=['# Expanded bursting metrics: unit-level LDA','',
           f"One unit is one observation. SUA/MUA pooled. {len(rows)} units; {len(old_names)} original metrics plus {len(new_names)} new metrics.",
           '', '## Method', '',
           'Only Actuators + effectors STG first-train recordings; pre/post 10 seconds. Three stratified outer unit folds',
           'use the identical seed as the previous unit analysis. Model and feature selection repeat within each outer training fold.',
           'Only shrinkage LDA is used for both classifiers and projections. Imputation, scaling and ANOVA selection are training-only.',
           f"Candidate count: {len(configs)}; top-k upper limits as applicable: {top_k}; shrinkage values {shrinkages}.",
           ('Within each training split, rank by ANOVA F, examine the top 400 variable features, and greedily remove features with absolute correlation ≥0.9 before selecting up to k.'
            if DECORRELATE else 'Train-only ANOVA top-k selection without correlation pruning.'),
           'The expanded search also includes original-only candidates, so it may choose them when additional burst metrics do not help.',
           '', '## Results', '', '| Comparison | Original LDA | Expanded LDA | Change (percentage points) |', '| --- | ---: | ---: | ---: |']
    lines += [f"| {r['comparison']} | {r['original_lda']:.1%} | {r['expanded_lda']:.1%} | {r['change_percentage_points']:+.2f} |" for r in output_rows]
    lines += ['', 'Scores are balanced accuracies on held-out units. Units from a recording may occur in both training and testing.',
              'Visual clouds are supervised full-data fits; the confusion matrix uses held-out units. No p values or raw-signal artifact checks.',
              '', '## Operational burst definitions', '',
              'A burst is a maximal run of consecutive spikes whose adjacent ISIs are at most the threshold, with at least the minimum spike count.',
              'Thresholds: 10, 25, 50, 100, 200 ms. Minimum spike counts: 3 and 5. No additional merge, minimum duration, or maximum duration rule.',
              'Windows: pre5 [−5,0), pre10 [−10,0), post5 [0,5), post10 [0,10), late [+0.5,10).',
              'Spikes outside a window are excluded before detecting bursts, so boundary-crossing bursts are truncated/reclassified.',
              'This is a sensitivity sweep of operational short-ISI clusters, not a validated physiological burst detector.',
              '', 'Each threshold/window provides burst count/rate, burst-spike fraction, burst-time fraction, duration mean/max/CV,',
              'spikes per burst mean/max, intraburst rate and ISI CV, interburst gap mean/CV, and first-burst latency.',
              'No-burst count/rate/fractions are zero; undefined durations, gaps, and latency are missing rather than invented values.',
              'Changes compare post5 with pre5, post10 with pre10, and late with pre10 (count/latency differences omitted).',
              '', 'Additional structure metrics: ISI quantiles, burstiness (SD−mean)/(SD+mean), log-ISI SD, adjacent-ISI correlation,',
              'pause fractions above 0.2/0.5/1 s, and Fano/active-bin fraction/peak rate at 50/100/250/500/1000 ms bins.',
              'Binned structure measures use complete bins only, dropping any trailing partial bin.',
              'Signed-log transforms precede training-only imputation/scaling. Missingness and correlated metrics can affect selection.',
              '', '## Best descriptive full-data LDA inputs', '']
    for key in ['Original metrics','Burst-expanded metrics']:
        lines += [f'### {key}', '', f"Configuration: {summary[key]['config']}.", '']
        lines += ['- `'+n+'`' for n in summary[key]['selected_metrics']]
    lines += ['', '## Files', '',
              'burst_metrics.npz holds only added metric values/names and recording/unit join IDs, avoiding duplication of original metrics.',
              'burst_metric_catalog.csv lists every new metric and missing-unit count. expanded_metric_ranking.csv is descriptive, not inferential.',
              'lda_comparisons.csv and summary.json record validation and selected fold configurations. unit_predictions.csv stores held-out labels.',
              'Source: scripts/explore_mcs_burst_lda.py. All generated files live in this scratch directory. One PNG only.']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n')
    print('COMPLETE',OUT,flush=True)

def render():
    rows=list(csv.DictReader((base.OUT/'unit_metrics.csv').open()))
    old_names=[r['metric'] for r in csv.DictReader((base.OUT/'metric_catalog.csv').open())]
    old=np.array([[float(r[n]) for n in old_names] for r in rows])
    archive=np.load(OUT/'burst_metrics.npz',allow_pickle=False)
    names=archive['names'].tolist()
    raw=np.column_stack([old,archive['values']])
    x=np.sign(raw)*np.log1p(np.abs(raw))
    y=np.array([base.CLASSES.index(r['construct']) for r in rows])
    summary=json.loads((OUT/'summary.json').read_text())
    draw(x,y,families(old_names,names),[],summary)
    print('Rendering complete',flush=True)

if __name__=='__main__':
    if '--render' in sys.argv:
        render()
    else:
        main()
