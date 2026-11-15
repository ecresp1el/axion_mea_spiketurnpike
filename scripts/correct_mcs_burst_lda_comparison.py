"""Actual original-only, new-burst-only, and forced-combination LDA comparison."""
import csv
import json
import warnings
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.impute import SimpleImputer
from sklearn.metrics import balanced_accuracy_score, confusion_matrix
from sklearn.model_selection import StratifiedKFold, StratifiedShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import explore_mcs_burst_lda as burst
import explore_mcs_actuator_separation as base

OUT=burst.OUT
MODES=['original','new_bursts','forced_combination']

class ForcedInputs(BaseEstimator,TransformerMixin):
    def __init__(self,mode='original',k=64,old_count=156):
        self.mode=mode;self.k=k;self.old_count=old_count

    def fit(self,x,y):
        self.support_=np.zeros(x.shape[1],dtype=bool)
        self.scores_=np.zeros(x.shape[1])
        slices=[]
        if self.mode in ['original','forced_combination']:
            slices.append(np.arange(self.old_count))
        if self.mode in ['new_bursts','forced_combination']:
            slices.append(np.arange(self.old_count,x.shape[1]))
        for indices in slices:
            selector=burst.CorrelationPrunedSelector(k=self.k).fit(x[:,indices],y)
            self.support_[indices[selector.get_support()]]=True
            self.scores_[indices]=selector.scores_
        if self.mode=='forced_combination':
            assert self.support_[:self.old_count].any() and self.support_[self.old_count:].any()
        return self

    def transform(self,x):
        return x[:,self.support_]

    def get_support(self):
        return self.support_

def pipeline(mode,config):
    k,shrink=config
    return Pipeline([('impute',SimpleImputer(strategy='median',keep_empty_features=True)),
        ('scale',StandardScaler()),('select',ForcedInputs(mode,k)),
        ('lda',LinearDiscriminantAnalysis(solver='lsqr',shrinkage=shrink))])

def tune(x,y,mode,seed):
    splits=list(StratifiedShuffleSplit(2,test_size=.25,random_state=seed).split(x,y))
    results=[]
    for k in [24,64,128]:
        for shrink in [.01,.1,'auto']:
            model=pipeline(mode,(k,shrink));scores=[]
            for train,test in splits:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore');model.fit(x[train],y[train])
                scores.append(balanced_accuracy_score(y[test],model.predict(x[test])))
            results.append((float(np.mean(scores)),(k,shrink)))
    return max(results,key=lambda z:z[0])

def main():
    records=list(csv.DictReader((base.OUT/'unit_metrics.csv').open()))
    old_names=[r['metric'] for r in csv.DictReader((base.OUT/'metric_catalog.csv').open())]
    old=np.array([[float(r[n]) for n in old_names] for r in records])
    archive=np.load(OUT/'burst_metrics.npz',allow_pickle=False)
    assert np.array_equal(archive['recording_id'],np.array([r['recording_id'] for r in records]))
    assert np.array_equal(archive['unit_id'],np.array([r['unit_id'] for r in records]))
    new_mask=np.array([n.startswith('burst_t') for n in archive['names']])
    new_names=archive['names'][new_mask].tolist()
    names=old_names+new_names
    raw=np.column_stack([old,archive['values'][:,new_mask]])
    x=np.sign(raw)*np.log1p(np.abs(raw))
    y=np.array([base.CLASSES.index(r['construct']) for r in records])
    folds=list(StratifiedKFold(3,shuffle=True,random_state=20261114).split(x,y))
    summary=dict(units=len(y),original_metrics=len(old_names),new_burst_metrics=len(new_names),
                 excluded_new_structure_metrics=int(np.sum(~new_mask)),modes={})
    selected_rows=[];views=[]
    for mode in MODES:
        prediction=np.full(len(y),-1)
        fold_details=[]
        for fold,(train,test) in enumerate(folds):
            _,best=tune(x[train],y[train],mode,210+fold)
            model=pipeline(mode,best)
            with warnings.catch_warnings():
                warnings.simplefilter('ignore');model.fit(x[train],y[train])
            prediction[test]=model.predict(x[test])
            support=model.named_steps['select'].get_support()
            detail=dict(fold=fold,config=best,selected_original=int(support[:156].sum()),
                        selected_new_burst=int(support[156:].sum()))
            fold_details.append(detail)
            print(mode,detail,flush=True)
        assert np.all(prediction>=0)
        score=float(balanced_accuracy_score(y,prediction))
        _,best=tune(x,y,mode,41)
        fitted=pipeline(mode,best)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore');z=fitted[:-1].fit_transform(x,y)
        support=fitted.named_steps['select'].get_support()
        projection=LinearDiscriminantAnalysis(solver='eigen',shrinkage=best[1],n_components=2)
        coordinates=projection.fit_transform(z,y)
        original_count=int(support[:156].sum());new_count=int(support[156:].sum())
        assert (new_count==0 if mode=='original' else new_count>0)
        assert (original_count==0 if mode=='new_bursts' else original_count>0)
        summary['modes'][mode]=dict(nested_unit_balanced_accuracy=score,folds=fold_details,
            descriptive_config=best,selected_original=original_count,selected_new_burst=new_count,
            confusion_matrix=confusion_matrix(y,prediction).tolist())
        for i in np.where(support)[0]:
            selected_rows.append(dict(view=mode,metric=names[i],source='original' if i<156 else 'new_burst'))
        views.append((mode,coordinates,score,original_count,new_count))
        print('RESULT',mode,score,original_count,new_count,flush=True)
    base.write_csv(OUT/'actual_lda_selected_metrics.csv',selected_rows)
    (OUT/'actual_lda_comparison.json').write_text(json.dumps(summary,indent=2))
    fig,axes=plt.subplots(1,3,figsize=(15,5.4))
    colors=['#7e7e7e','#e94b47','#64af54','#9462d5']
    titles=['Original metrics only','New burst metrics only','Original + required burst metrics']
    for ax,(mode,coords,score,original_count,new_count),title in zip(axes,views,titles):
        for c,label in enumerate(base.CLASSES):
            p=coords[y==c]
            ax.scatter(p[:,0],p[:,1],s=9,alpha=.4,color=colors[c],linewidths=0,label=f'{label}: {len(p)} units')
            vals,vecs=np.linalg.eigh(np.cov(p.T))
            ax.add_patch(Ellipse(p.mean(axis=0),2*np.sqrt(max(vals[-1],0)),2*np.sqrt(max(vals[0],0)),
                angle=np.degrees(np.arctan2(vecs[1,-1],vecs[0,-1])),facecolor=colors[c],edgecolor=colors[c],alpha=.13))
        ax.set_title(f'{title}\n{original_count} original + {new_count} new inputs; held-out units {score:.1%}',fontsize=10)
        ax.set_xlabel('LD1');ax.set_ylabel('LD2')
        ax.axhline(0,color='gray',ls='--',lw=.5);ax.axvline(0,color='gray',ls='--',lw=.5)
        ax.spines[['top','right']].set_visible(False)
    axes[0].legend(fontsize=8,frameon=False)
    fig.suptitle('Actual burst-feature LDA comparisons: each dot is one unit',fontsize=15)
    fig.text(.5,.025,'Three separate supervised LDA fits: axis values are not directly comparable across panels. SUA/MUA pooled.\n'
             'Clouds = descriptive full-data fits; titles report nested 3-fold held-out-unit balanced accuracy. Ellipses = 1-SD unit spread.\n'
             'Burst-only and combined panels must include new burst inputs; combined selection is performed separately in each feature block.',
             ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.15,1,.93))
    destination=OUT/'burst_lda_actual_feature_comparison.png'
    fig.savefig(destination,dpi=150);plt.close(fig)
    lines=['# Corrected comparison of actual LDA inputs','',
           'The previous expanded-search figure repeated the original projection because it selected zero added metrics.',
           'This comparison forces the three input definitions below. One unit is one observation; SUA/MUA pooled.',
           '', '| View | Original inputs selected | New burst inputs selected | Nested held-out-unit balanced accuracy |',
           '| --- | ---: | ---: | ---: |']
    for mode,_,score,original_count,new_count in views:
        lines.append(f'| {mode} | {original_count} | {new_count} | {score:.1%} |')
    lines += ['', 'The 1,060 new burst inputs are genuine threshold/minimum-spike burst measurements and pre/post changes.',
              'The 130 additional generic spike-train structure metrics are excluded from these views to make the burst-only definition literal.',
              'Selection is train-only ANOVA ranking with correlation pruning. For the forced combination, each feature block is selected separately.',
              'Per-block caps 24/64/128 and LDA shrinkage 0.01/0.1/automatic are tuned within each outer training fold.',
              'Every unit is held out once using the same three stratified unit folds. Model fitting uses no held-out units.',
              'Visual clouds use all labels for descriptive LDA. Separate fits have separate coordinate systems; cloud positions cannot be compared directly.',
              'actual_lda_selected_metrics.csv lists every metric actually used in each full-data view.',
              'actual_lda_comparison.json records selected counts and configurations within all validation folds.',
              'Source: scripts/correct_mcs_burst_lda_comparison.py. No additional raw data or metric matrices are copied.']
    (OUT/'ACTUAL_FEATURE_COMPARISON.md').write_text('\n'.join(lines)+'\n')
    print('COMPLETE',destination,flush=True)

if __name__=='__main__':
    main()
