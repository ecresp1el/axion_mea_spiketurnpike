"""Exploratory metric search: actuator/effector STG recordings only.

Unit-level technical separation and whole-sample validation are explicitly separate.
No raw continuous signals are read and no class labels enter feature extraction.
"""
import csv
import itertools
import json
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
import numpy as np
from scipy.stats import entropy
from sklearn.decomposition import PCA
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, silhouette_score
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

REPO = Path(__file__).resolve().parents[1]
OUT = Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/actuator_metric_exploration')
CLASSES = ['Control', 'DREADD', 'LMO', 'PSAM']
WINDOWS = {
    'pre10': (-10, 0), 'pre5': (-5, 0), 'pre_early': (-10, -5),
    'post_0_005': (0, .05), 'post_005_025': (.05, .25),
    'post_025_05': (.25, .5), 'post_05_1': (.5, 1),
    'post_1_2': (1, 2), 'post_2_5': (2, 5), 'post_5_10': (5, 10),
    'post5': (0, 5), 'post10': (0, 10),
    'post_blank005_5': (.05, 5), 'post_blank01_5': (.1, 5),
    'post_blank025_5': (.25, 5), 'post_blank05_5': (.5, 5),
    'post_blank005_10': (.05, 10), 'post_blank01_10': (.1, 10),
    'post_blank025_10': (.25, 10), 'post_blank05_10': (.5, 10),
}

def write_csv(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def progress(text):
    print(text, flush=True)
    (OUT/'progress.txt').write_text(text+'\n')

def metrics(t):
    """All times relative to onset; counts/windows are half-open."""
    d = {}
    for name, (a, b) in WINDOWS.items():
        s = t[(t >= a) & (t < b)]
        rate = len(s)/(b-a)
        d['rate__'+name] = rate
        if name.startswith('post'):
            baseline = d['rate__pre5'] if b <= 5 else d['rate__pre10']
            d['delta__'+name] = rate-baseline
            d['logfold__'+name] = np.log2((rate+.2)/(baseline+.2))
            d['contrast__'+name] = (rate-baseline)/(rate+baseline+.4)
    for name, (a,b) in {'pre':(-10,0), 'post':(0,10), 'late':(.5,10)}.items():
        s = t[(t >= a)&(t < b)]
        isi = np.diff(s)
        bins = np.arange(a, b+.001, .5)
        h = np.histogram(s, bins)[0]
        d['variability__fano_'+name] = float(h.var()/h.mean()) if h.mean() else 0.
        d['variability__active_bins_'+name] = float(np.mean(h > 0))
        d['variability__entropy_'+name] = float(entropy(h+1e-12)/np.log(len(h)))
        d['variability__isi_cv_'+name] = float(isi.std()/isi.mean()) if len(isi)>1 else np.nan
        d['variability__isi_median_'+name] = float(np.median(isi)) if len(isi) else np.nan
        d['burst__isi_lt10ms_'+name] = float(np.mean(isi < .01)) if len(isi) else np.nan
        d['burst__isi_lt50ms_'+name] = float(np.mean(isi < .05)) if len(isi) else np.nan
        d['burst__isi_lt2ms_'+name] = float(np.mean(isi < .002)) if len(isi) else np.nan
        d['burst__max_halfsec_rate_'+name] = float(h.max()*2)
        if len(isi)>1:
            d['variability__cv2_'+name] = float(np.mean(2*np.abs(np.diff(isi))/(isi[1:]+isi[:-1]+1e-12)))
            d['variability__local_variation_'+name] = float(np.mean(3*np.diff(isi)**2/(isi[1:]+isi[:-1]+1e-12)**2))
        else:
            d['variability__cv2_'+name] = np.nan
            d['variability__local_variation_'+name] = np.nan
    for start in [0, .05, .1, .25, .5]:
        tag = str(start).replace('.', 'p')
        s = t[(t >= start)&(t < 10)]
        h, edges = np.histogram(s, np.linspace(start,10,21))
        hz = h/np.diff(edges)
        d['temporal__first_spike_'+tag] = float(s[0]) if len(s) else 10.
        d['temporal__peak_latency_'+tag] = float((edges[np.argmax(hz)]+edges[np.argmax(hz)+1])/2)
        d['temporal__peak_rate_'+tag] = float(hz.max())
        d['temporal__center_mass_'+tag] = float(np.mean(s)) if len(s) else np.nan
        d['temporal__early_fraction_'+tag] = float(np.mean(s<1)) if len(s) else 0.
        d['temporal__late_fraction_'+tag] = float(np.mean(s>=5)) if len(s) else 0.
    for i, (a,b) in enumerate(zip(np.arange(-10,10), np.arange(-9,11))):
        d[f'bin__{i:02d}'] = int(np.sum((t>=a)&(t<b)))
    d['delta__pre_drift'] = d['rate__pre5']-d['rate__pre_early']
    d['delta__recovery_5_10_minus_0_5'] = d['rate__post_5_10']-d['rate__post5']
    return d

def extract():
    rows = list(csv.DictReader((REPO/'metadata/mcs_recording_biology.csv').open()))
    extracted = []
    for r in rows:
        if r['major_group'] != 'Actuators + effectors' or not r['total_units'] or float(r['duration_s']) < 60:
            continue
        starts = sorted(json.loads(r['pulse_start_times_s'] or '[]'))
        if not starts:
            continue
        onset = starts[0]
        assert onset >= 10 and onset+10 <= float(r['duration_s'])
        next_trains = [b for a,b in zip(starts,starts[1:]) if b-a>.1]
        assert not next_trains or next_trains[0]>=onset+10
        files = list((Path(r['sorting_output_path'])/'curated').glob('*/numpysorting_info.json'))
        assert len(files)==1
        folder = files[0].parent
        info = json.loads(files[0].read_text())
        fs = info['sampling_frequency']
        spikes = np.load(folder/'spikes.npy',mmap_mode='r')
        labels = np.load(folder/'properties/KSLabel.npy',allow_pickle=False).astype(str)
        lo,hi = np.searchsorted(spikes['sample_index'],[(onset-10)*fs,(onset+10)*fs])
        window = spikes[lo:hi]
        relative = window['sample_index']/fs-onset
        assert info['num_segments']==1 and len(info['unit_ids'])==len(labels)
        for i, uid in enumerate(info['unit_ids']):
            assert labels[i] in ['good','mua']
            d = dict(recording_id=r['recording_id'], sample_id=r['sample_label'],
                     construct=r['construct'], unit_id=uid, kslabel=labels[i],
                     event_time_s=onset, duration_s=float(r['duration_s']))
            d.update(metrics(relative[window['unit_index']==i]))
            extracted.append(d)
        progress('Extracted '+r['recording_id'])
    write_csv(OUT/'unit_metrics.csv',extracted)
    return extracted

def feature_sets(names):
    families = {
        'baseline': [i for i,n in enumerate(names) if n.startswith('rate__pre') or n.endswith('_pre') or n=='delta__pre_drift'],
        'rates': [i for i,n in enumerate(names) if n.startswith('rate__')],
        'response': [i for i,n in enumerate(names) if n.startswith(('delta__','logfold__','contrast__'))],
        'variability': [i for i,n in enumerate(names) if n.startswith(('variability__','burst__'))],
        'temporal': [i for i,n in enumerate(names) if n.startswith('temporal__')],
        'bins': [i for i,n in enumerate(names) if n.startswith('bin__')],
    }
    # Predeclared family combinations; selection is fitted on training units only.
    for a,b in itertools.combinations(['rates','response','variability','temporal'],2):
        families[a+'+'+b] = sorted(set(families[a]+families[b]))
    families['all'] = list(range(len(names)))
    families['artifact_reduced'] = [i for i,n in enumerate(names) if (
        n.startswith('rate__pre') or 'post_blank05' in n or 'post_5_10' in n
        or n.endswith('_late') or n.startswith('temporal__') and n.endswith('_0p5'))]
    return families

def model(config, sets):
    family, k, estimator = config
    indices = sets[family]
    selection = min(k,len(indices)) if k else 'all'
    clf = (LogisticRegression(C=.5,max_iter=1200,class_weight='balanced') if estimator=='logistic'
           else SVC(C=3,kernel='rbf',class_weight='balanced'))
    return indices, Pipeline([
        ('impute',SimpleImputer(strategy='median',keep_empty_features=True)),
        ('scale',StandardScaler()), ('select',SelectKBest(f_classif,k=selection)),
        ('classifier',clf)])

def search(x,y,sets, configs, seed=41):
    splits=list(StratifiedShuffleSplit(n_splits=2,test_size=.25,random_state=seed).split(x,y))
    results=[]
    for config in configs:
        indices,pipeline=model(config,sets)
        values=[]
        for train,test in splits:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                pipeline.fit(x[train][:,indices],y[train])
            values.append(balanced_accuracy_score(y[test],pipeline.predict(x[test][:,indices])))
        results.append(dict(family=config[0], k=config[1], estimator=config[2],
                            technical_balanced_accuracy=float(np.mean(values)),
                            technical_split_sd=float(np.std(values))))
    results.sort(key=lambda r:r['technical_balanced_accuracy'],reverse=True)
    best=results[0]
    return (best['family'],best['k'],best['estimator']),results

def sample_predictions(pred, truth, meta):
    # Majority vote within a recording, then equal recording votes within sample.
    samples=[]
    for sample in sorted(set(m['sample_id'] for m in meta)):
        masks=[i for i,m in enumerate(meta) if m['sample_id']==sample]
        recids=sorted(set(meta[i]['recording_id'] for i in masks))
        votes=[]
        for rid in recids:
            p=pred[[i for i in masks if meta[i]['recording_id']==rid]]
            votes.append(np.array([np.mean(p==c) for c in np.unique(truth)]))
        label=np.unique(truth)[np.argmax(np.mean(votes,axis=0))]
        samples.append(dict(sample_id=sample, true=int(truth[masks[0]]),predicted=int(label)))
    return samples

def nested_sample_validation(x,y,meta,sets,configs):
    by_class={c:sorted(set(m['sample_id'] for m,t in zip(meta,y) if t==c)) for c in np.unique(y)}
    assert all(len(v)>=3 and len(v)%3==0 for v in by_class.values())
    preds=np.full(len(y),-1,dtype=int)
    folds=[]
    for fold in range(3):
        held={s for samples in by_class.values() for s in samples[fold::3]}
        test=np.array([i for i,m in enumerate(meta) if m['sample_id'] in held])
        train=np.array([i for i,m in enumerate(meta) if m['sample_id'] not in held])
        best,_=search(x[train],y[train],sets,configs,seed=100+fold)
        cols,pipeline=model(best,sets)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            pipeline.fit(x[train][:,cols],y[train])
        preds[test]=pipeline.predict(x[test][:,cols])
        folds.append(dict(fold=fold,held_samples=sorted(held),family=best[0],k=best[1],estimator=best[2]))
        progress('Finished whole-sample fold '+str(fold)+' held '+','.join(sorted(held)))
    assert np.all(preds>=0)
    sample_rows=sample_predictions(preds,y,meta)
    return preds,sample_rows,folds

def projection(x,y,names,sets,results):
    # Explore PCA feature families without pretending the search itself is label-blind.
    candidates=[]
    for family in sets:
        cols=sets[family]
        xx=SimpleImputer(strategy='median',keep_empty_features=True).fit_transform(x[:,cols])
        xx=StandardScaler().fit_transform(xx)
        for k in [8,24,0]:
            selector=SelectKBest(f_classif,k=min(k,len(cols)) if k else 'all')
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                zz=selector.fit_transform(xx,y)
            if zz.shape[1]<2:
                continue
            pca=PCA(n_components=2,svd_solver='full').fit(zz)
            coords=pca.transform(zz)
            score=float(silhouette_score(coords,y,sample_size=min(900,len(y)),random_state=42))
            candidates.append((score,family,k,pca,coords,zz,[names[cols[j]] for j in np.where(selector.get_support())[0]]))
    candidates.sort(key=lambda z:z[0],reverse=True)
    write_csv(OUT/'projection_search.csv',[dict(family=c[1],k=c[2],pca_2d_silhouette=c[0]) for c in candidates])
    best=candidates[0]
    # LDA has its own full-data exploratory feature-family search.
    lda_candidates=[]
    for c in candidates:
        lda=LinearDiscriminantAnalysis(solver='eigen',shrinkage='auto',n_components=2)
        try:
            coords=lda.fit_transform(c[5],y)
            score=float(silhouette_score(coords,y,sample_size=min(900,len(y)),random_state=42))
            lda_candidates.append((score,c,lda,coords))
        except (ValueError,np.linalg.LinAlgError):
            continue
    lda_candidates.sort(key=lambda z:z[0],reverse=True)
    write_csv(OUT/'lda_projection_search.csv',[dict(family=c[1][1],k=c[1][2],lda_2d_silhouette=c[0]) for c in lda_candidates])
    return best,lda_candidates[0]

def draw(pca,lda,y,sample_rows,technical,heldout):
    fig,axes=plt.subplots(1,3,figsize=(15,5.5))
    colors=['#7e7e7e','#e94b47','#64af54','#9462d5']
    for ax,coords,title in [(axes[0],pca[4],'Best explored PCA feature set'),
                             (axes[1],lda[3],'Best explored supervised LDA')]:
        for c,name in enumerate(CLASSES):
            pts=coords[y==c]
            ax.scatter(pts[:,0],pts[:,1],s=9,alpha=.35,color=colors[c],linewidths=0,label=f'{name} (units={len(pts)})')
            cov=np.cov(pts.T)
            vals,vecs=np.linalg.eigh(cov)
            angle=np.degrees(np.arctan2(vecs[1,-1],vecs[0,-1]))
            ax.add_patch(Ellipse(pts.mean(axis=0),2*np.sqrt(max(vals[-1],0)),2*np.sqrt(max(vals[0],0)),angle=angle,
                                 facecolor=colors[c],edgecolor=colors[c],alpha=.12))
        ax.axhline(0,color='gray',lw=.5,ls='--')
        ax.axvline(0,color='gray',lw=.5,ls='--')
        ax.set_title(title,fontsize=11)
        ax.spines[['top','right']].set_visible(False)
    axes[0].set_xlabel(f'PC1 ({pca[3].explained_variance_ratio_[0]*100:.1f}%)')
    axes[0].set_ylabel(f'PC2 ({pca[3].explained_variance_ratio_[1]*100:.1f}%)')
    axes[1].set_xlabel('LD1 (uses class labels)')
    axes[1].set_ylabel('LD2 (uses class labels)')
    axes[0].legend(fontsize=8,frameon=False)
    cm=confusion_matrix([r['true'] for r in sample_rows],[r['predicted'] for r in sample_rows],labels=range(4))
    axes[2].imshow(cm,vmin=0,vmax=3,cmap='Blues')
    for i in range(4):
        for j in range(4):
            axes[2].text(j,i,str(cm[i,j]),ha='center',va='center',color='white' if cm[i,j]>1 else 'black')
    axes[2].set_xticks(range(4),CLASSES,rotation=35,ha='right')
    axes[2].set_yticks(range(4),CLASSES)
    axes[2].set_xlabel('Predicted construct')
    axes[2].set_ylabel('Actual construct')
    axes[2].set_title(f'Whole-sample held-out accuracy: {heldout:.1%}',fontsize=11)
    fig.suptitle('Actuators + effectors only: exploratory separation and whole-sample holdout',fontsize=14)
    fig.text(.5,.025,f'PCA features and LDA chosen using all labels to maximize apparent separation; ellipses = 1-SD unit spread, not confidence intervals.\n'
             f'Unit technical CV (same samples may appear in train/test): {technical:.1%}. '
             'Right panel: nested selection, all units/recordings of each sample held out together.\n'
             'STG first train, −10 to +10 s. SUA/MUA pooled. No raw-signal artifact verification; exploratory recording differences are allowed.',
             ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.15,1,.94))
    fig.savefig(OUT/'actuator_separation.png',dpi=150)
    plt.close(fig)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    progress('Extracting label-independent metrics from saved sorted spikes')
    rows=extract()
    meta_keys=['recording_id','sample_id','construct','unit_id','kslabel','event_time_s','duration_s']
    names=[n for n in rows[0] if n not in meta_keys]
    raw=np.array([[r[n] for n in names] for r in rows],dtype=float)
    assert np.all(np.isfinite(raw)|np.isnan(raw))
    # A fixed signed-log transform reduces long tails without using labels.
    x=np.sign(raw)*np.log1p(np.abs(raw))
    y=np.array([CLASSES.index(r['construct']) for r in rows])
    sets=feature_sets(names)
    configs=[(family,k,estimator) for family in sets for k in [16,0] for estimator in ['logistic','rbf_svm']]
    catalog=[]
    for name in names:
        catalog.append(dict(metric=name,family=name.split('__')[0],
                            missing_units=int(np.isnan(raw[:,names.index(name)]).sum())))
    write_csv(OUT/'metric_catalog.csv',catalog)
    summary=dict(units=len(rows),recordings=len(set(r['recording_id'] for r in rows)),
                 samples=len(set(r['sample_id'] for r in rows)),metrics=len(names),candidate_models=len(configs),tasks={})
    for target in ['four_class','DREADD','LMO','PSAM']:
        progress('Searching metrics/models: '+target)
        mask=np.ones(len(y),dtype=bool) if target=='four_class' else np.isin(y,[0,CLASSES.index(target)])
        xx,yy=x[mask],y[mask]
        meta=[r for r,m in zip(rows,mask) if m]
        best,results=search(xx,yy,sets,configs)
        write_csv(OUT/(target+'_model_search.csv'),results)
        cols, fitted = model(best, sets)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            fitted.fit(xx[:, cols], yy)
        selector = fitted.named_steps['select']
        selected_names = [names[cols[i]] for i in np.where(selector.get_support())[0]]
        ranking = [dict(metric=names[index], selected=bool(selector.get_support()[j]),
                        exploratory_anova_f=float(np.nan_to_num(selector.scores_[j], nan=0, posinf=1e30)))
                   for j,index in enumerate(cols)]
        ranking.sort(key=lambda r:r['exploratory_anova_f'], reverse=True)
        write_csv(OUT/(target+'_metric_ranking.csv'), ranking)
        pred,sample_rows,folds=nested_sample_validation(xx,yy,meta,sets,configs)
        write_csv(OUT/(target+'_sample_predictions.csv'),sample_rows)
        for r,p in zip(meta,pred):
            r[target+'_heldout_prediction']=CLASSES[int(p)]
        unit_score=float(balanced_accuracy_score(yy,pred))
        sample_score=float(balanced_accuracy_score([r['true'] for r in sample_rows],[r['predicted'] for r in sample_rows]))
        summary['tasks'][target]=dict(best_config=best,technical_unit_cv=results[0]['technical_balanced_accuracy'],
                                      heldout_unit_accuracy=unit_score,heldout_sample_accuracy=sample_score,
                                      selected_metrics=selected_names,
                                      baseline_only_best=max(r['technical_balanced_accuracy'] for r in results if r['family']=='baseline'),
                                      response_only_best=max(r['technical_balanced_accuracy'] for r in results if r['family']=='response'),
                                      artifact_reduced_best=max(r['technical_balanced_accuracy'] for r in results if r['family']=='artifact_reduced'),
                                      folds=folds)
        progress(target+' technical '+str(results[0]['technical_balanced_accuracy'])+' sample-heldout '+str(sample_score))
        if target=='four_class':
            main_samples=sample_rows
            main_results=results
    progress('Searching exploratory PCA/LDA projections')
    pca,lda=projection(x,y,names,sets,main_results)
    summary['pca']=dict(family=pca[1],k=pca[2],silhouette=pca[0],selected_metrics=pca[6],
                        explained_variance=pca[3].explained_variance_ratio_.tolist())
    summary['lda']=dict(family=lda[1][1],k=lda[1][2],silhouette=lda[0],selected_metrics=lda[1][6])
    draw(pca,lda,y,main_samples,summary['tasks']['four_class']['technical_unit_cv'],
         summary['tasks']['four_class']['heldout_sample_accuracy'])
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    # Keep a compact unit table, including held-out predictions; no model or raw-signal copies.
    prediction_rows=[{k:r.get(k,'') for k in meta_keys+['four_class_heldout_prediction','DREADD_heldout_prediction',
                    'LMO_heldout_prediction','PSAM_heldout_prediction']} for r in rows]
    write_csv(OUT/'unit_heldout_predictions.csv',prediction_rows)
    lines=['# Actuator + effector separation exploration','',
           f"{len(rows)} unit-recording observations; {summary['recordings']} recordings; {summary['samples']} sample IDs; {len(names)} metrics.",
           '', 'Only STG-marked Actuators + effectors recordings are analyzed. First train per recording; full −10 to +10 s windows.',
           'Chemical additions are not pooled with STG. SUA/MUA are pooled; identity, sample label, date, duration, and unit label are not predictive features.',
           '', '## What was optimized', '',
           'Signed-log metric transform, training-only median imputation, centering/scaling, optional training-only top-16 ANOVA selection,',
           'logistic regression or RBF SVM. Candidate families and combinations include baseline, rates, response contrasts, temporal structure,',
           'variability/bursting, one-second bins, all metrics, and an artifact-reduced subset. Two fixed stratified unit splits per candidate.',
           'Technical splits intentionally permit units from the same recording/sample in train and test, as accepted by the user.',
           'The best technical result is exploratory and can recognize recordings. It is not evidence of generalization to new biological samples.',
           '', '## Results', '', '| Comparison | Best technical unit CV | Nested whole-sample accuracy |',
           '| --- | ---: | ---: |']
    for task,v in summary['tasks'].items():
        lines.append(f"| {task} | {v['technical_unit_cv']:.1%} | {v['heldout_sample_accuracy']:.1%} |")
    lines += ['', '### Which metrics provided the best technical separation?', '']
    for task,v in summary['tasks'].items():
        lines += [f'#### {task}', '', f"Best feature family / top-k / model: {v['best_config']}.",
                  f"Baseline-only: {v['baseline_only_best']:.1%}; response-only: {v['response_only_best']:.1%}; artifact-reduced: {v['artifact_reduced_best']:.1%}.",
                  'Selected metrics: '+', '.join('`'+n+'`' for n in v['selected_metrics'])+'.', '']
    lines += ['', 'Whole-sample evaluation holds out one sample ID per construct in each of three folds. All units and repeated recordings',
              'for those IDs are excluded from training. Feature/model selection repeats within each training fold. Sample prediction averages',
              'unit vote fractions within recordings, then weights each recording equally. Only three IDs per construct: estimates are coarse.',
              'The source key does not establish that sample IDs are independent biological replicates; this split is a conservative identity block.',
              'No p values or biological-effect claims are made.', '', '## Projections', '',
              f"Best explored PCA family: {pca[1]}, k={pca[2] or 'all'}, 2-D silhouette={pca[0]:.3f}.",
              f"Best explored LDA family: {lda[1][1]}, k={lda[1][2] or 'all'}, 2-D silhouette={lda[0]:.3f}.",
              'PCA axes use no labels after feature selection, but the feature-set/projection search uses all labels. LDA explicitly uses labels.',
              'These are fitted, optimized views. Ellipses show one-SD unit spread, not confidence intervals. Overlap is retained.',
              '', '## Metric definitions', '',
              'Rate = spikes/window duration. Delta = rate minus pre5 or pre10 baseline. Logfold = log2((rate+0.2)/(baseline+0.2)).',
              'Contrast = (rate−baseline)/(rate+baseline+0.4). Signed-log model transform is sign(x)×log1p(abs(x)).',
              'Fano, active-bin fraction, and normalized entropy use 0.5-s counts. ISI CV, CV2, local variation, median ISI,',
              'fractions below 2/10/50 ms, and peak 0.5-s rate describe variability and bursting; insufficient ISIs become missing.',
              'First spike, peak latency/rate (20 bins from the specified start to +10 s), mean spike time, early fraction (<1 s),',
              'and late fraction (≥5 s) describe response timing. Bin features are 20 one-second counts from −10 to +10 s.',
              'Post windows exclude 0/50/100/250/500 ms as named. This reduces early-time dependence; it does not verify artifact removal.',
              'Early artifact-linked activity, baseline differences, and recording conditions may explain separation.',
              '', '| Window | Start (s) | End (s), excluded |', '| --- | ---: | ---: |']
    lines += [f'| {n} | {a} | {b} |' for n,(a,b) in WINDOWS.items()]
    lines += ['', '### Full metric list', '']+[f'- `{n}`' for n in names]
    lines += ['', '## Storage and reproduction','',
              'One figure, compact CSVs, summary JSON, and this report only; no continuous-signal copies, analyzers, or trained model dumps.',
              'Source: scripts/explore_mcs_actuator_separation.py in the pipeline repo. All generated analysis artifacts are on scratch.']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n')
    progress('COMPLETE: '+str(OUT))

def finalize():
    """Rank already-searched metrics without repeating completed model searches."""
    summary=json.loads((OUT/'summary.json').read_text())
    rows=list(csv.DictReader((OUT/'unit_metrics.csv').open()))
    names=[r['metric'] for r in csv.DictReader((OUT/'metric_catalog.csv').open())]
    raw=np.array([[float(r[n]) for n in names] for r in rows])
    x=np.sign(raw)*np.log1p(np.abs(raw))
    y=np.array([CLASSES.index(r['construct']) for r in rows])
    sets=feature_sets(names)
    extra=['## Best metric combinations and early-time sensitivity','',
           'These are exploratory technical accuracies from unit splits that can recognize recordings. They are not new-sample validation.',
           '', '| Comparison | Baseline only | Response only | Excluding first 500 ms | Best overall |',
           '| --- | ---: | ---: | ---: | ---: |']
    ranked={}
    for task,v in summary['tasks'].items():
        results=list(csv.DictReader((OUT/(task+'_model_search.csv')).open()))
        for key,family in [('baseline_only_best','baseline'),('response_only_best','response'),('artifact_reduced_best','artifact_reduced')]:
            v[key]=max(float(r['technical_balanced_accuracy']) for r in results if r['family']==family)
        if task.endswith('_vs_others'):
            mask=np.ones(len(y),dtype=bool)
            task_y=(y==CLASSES.index(task.removesuffix('_vs_others'))).astype(int)
        else:
            mask=np.ones(len(y),dtype=bool) if task=='four_class' else np.isin(y,[0,CLASSES.index(task)])
            task_y=y
        cols,fitted=model(tuple(v['best_config']),sets)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            fitted.fit(x[mask][:,cols],task_y[mask])
        selector=fitted.named_steps['select']
        v['selected_metrics']=[names[cols[i]] for i in np.where(selector.get_support())[0]]
        ranking=[dict(metric=names[index],selected=bool(selector.get_support()[j]),
                      exploratory_anova_f=float(np.nan_to_num(selector.scores_[j],nan=0,posinf=1e30)))
                 for j,index in enumerate(cols)]
        ranking.sort(key=lambda r:r['exploratory_anova_f'],reverse=True)
        write_csv(OUT/(task+'_metric_ranking.csv'),ranking)
        ranked[task]=ranking
        extra.append(f"| {task} | {v['baseline_only_best']:.1%} | {v['response_only_best']:.1%} | {v['artifact_reduced_best']:.1%} | {v['technical_unit_cv']:.1%} |")
    extra += ['', 'All family comparisons repeat feature selection and imputation within unit training splits.',
              'The artifact-reduced family excludes the first 500 ms for post-stim features, but does not verify that later spikes are artifact-free.',
              'Feature ANOVA F scores below are descriptive unit-level rankings, not inferential tests; no p values are used.', '']
    for task,v in summary['tasks'].items():
        extra += [f'### {task}', '', f"Best family / top-k / classifier: {v['best_config']}.",
                  f"Technical balanced accuracy: {v['technical_unit_cv']:.1%}; whole-sample held-out balanced accuracy: {v['heldout_sample_accuracy']:.1%}.",
                  '', 'Top 12 descriptive feature scores within that family:', '']
        extra += [f"- `{r['metric']}`: F={r['exploratory_anova_f']:.3f}" for r in ranked[task][:12]]
        extra += ['', 'Selected model inputs: '+', '.join('`'+n+'`' for n in v['selected_metrics'])+'.', '']
    report=OUT/'README.md'
    text=report.read_text()
    if '## Best metric combinations and early-time sensitivity' in text:
        text=text.split('## Best metric combinations and early-time sensitivity')[0]
    report.write_text(text+'\n'+'\n'.join(extra)+'\n')
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    # Recreate the same PCA/LDA views to apply the clearer holdout title.
    pca,lda=projection(x,y,names,sets,[])
    sample_rows=[{k:int(v) if k in ['true','predicted'] else v for k,v in r.items()}
                 for r in csv.DictReader((OUT/'four_class_sample_predictions.csv').open())]
    draw(pca,lda,y,sample_rows,summary['tasks']['four_class']['technical_unit_cv'],
         summary['tasks']['four_class']['heldout_sample_accuracy'])
    progress('COMPLETE: rankings and sensitivity report finalized')

def one_vs_rest():
    summary=json.loads((OUT/'summary.json').read_text())
    rows=list(csv.DictReader((OUT/'unit_metrics.csv').open()))
    names=[r['metric'] for r in csv.DictReader((OUT/'metric_catalog.csv').open())]
    raw=np.array([[float(r[n]) for n in names] for r in rows])
    x=np.sign(raw)*np.log1p(np.abs(raw))
    sets=feature_sets(names)
    configs=[(family,k,estimator) for family in sets for k in [16,0] for estimator in ['logistic','rbf_svm']]
    for target in ['DREADD','LMO','PSAM']:
        task=target+'_vs_others'
        y=np.array([int(r['construct']==target) for r in rows])
        progress('Searching '+task)
        best,results=search(x,y,sets,configs)
        write_csv(OUT/(task+'_model_search.csv'),results)
        pred,sample_rows,folds=nested_sample_validation(x,y,rows,sets,configs)
        write_csv(OUT/(task+'_sample_predictions.csv'),sample_rows)
        summary['tasks'][task]=dict(best_config=best,technical_unit_cv=results[0]['technical_balanced_accuracy'],
            heldout_unit_accuracy=float(balanced_accuracy_score(y,pred)),
            heldout_sample_accuracy=float(balanced_accuracy_score([r['true'] for r in sample_rows],[r['predicted'] for r in sample_rows])),
            label_definition=f'0=all other constructs including Control; 1={target}',folds=folds)
        (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
        progress(task+' technical '+str(summary['tasks'][task]['technical_unit_cv'])+
                 ' sample-heldout '+str(summary['tasks'][task]['heldout_sample_accuracy']))
    finalize()

if __name__=='__main__':
    if '--one-vs-rest' in sys.argv:
        one_vs_rest()
    elif '--finalize' in sys.argv:
        finalize()
    else:
        main()
