"""Unit is the sampling observation for all splits, predictions, and plots."""
import csv
import json
import warnings
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
import numpy as np
from sklearn.metrics import balanced_accuracy_score, confusion_matrix
from sklearn.model_selection import StratifiedKFold

import explore_mcs_actuator_separation as base

OUT = base.OUT

def main():
    rows = list(csv.DictReader((OUT/'unit_metrics.csv').open()))
    names = [r['metric'] for r in csv.DictReader((OUT/'metric_catalog.csv').open())]
    raw = np.array([[float(r[n]) for n in names] for r in rows])
    x = np.sign(raw)*np.log1p(np.abs(raw))
    original_y = np.array([base.CLASSES.index(r['construct']) for r in rows])
    sets = base.feature_sets(names)
    configs = [(family,k,estimator) for family in sets for k in [16,0]
               for estimator in ['logistic','rbf_svm']]
    predictions = [{k:r[k] for k in ['recording_id','sample_id','construct','unit_id','kslabel']} for r in rows]
    summary = dict(observation='one sorted unit', units=len(rows), metrics=len(names),
                   split='three stratified unit folds, nested feature/model selection',
                   classes=base.CLASSES, tasks={})
    task_names = ['four_class', 'DREADD_vs_Control', 'LMO_vs_Control', 'PSAM_vs_Control',
                  'DREADD_vs_others', 'LMO_vs_others', 'PSAM_vs_others']
    result_rows = []
    four_pred = None
    for task in task_names:
        if task=='four_class':
            mask=np.ones(len(rows),dtype=bool)
            y=original_y.copy()
            label_names={i:c for i,c in enumerate(base.CLASSES)}
        elif task.endswith('_vs_Control'):
            target=task.split('_vs_')[0]
            mask=np.isin(original_y,[0,base.CLASSES.index(target)])
            y=original_y[mask]
            label_names={0:'Control',base.CLASSES.index(target):target}
        else:
            target=task.split('_vs_')[0]
            mask=np.ones(len(rows),dtype=bool)
            y=(original_y==base.CLASSES.index(target)).astype(int)
            label_names={0:'Others',1:target}
        xx=x[mask]
        indices=np.where(mask)[0]
        pred=np.full(len(y),-1,dtype=int)
        fold_rows=[]
        print('Starting unit discrimination:',task,flush=True)
        for fold,(train,test) in enumerate(StratifiedKFold(n_splits=3,shuffle=True,random_state=20261114).split(xx,y)):
            assert not set(train)&set(test)
            best,_=base.search(xx[train],y[train],sets,configs,seed=210+fold)
            cols,pipeline=base.model(best,sets)
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                pipeline.fit(xx[train][:,cols],y[train])
            pred[test]=pipeline.predict(xx[test][:,cols])
            fold_rows.append(dict(fold=fold,train_units=len(train),test_units=len(test),
                                  best_feature_family=best[0],top_k=best[1],classifier=best[2],
                                  balanced_accuracy=float(balanced_accuracy_score(y[test],pred[test]))))
            print(task,'unit fold',fold,fold_rows[-1],flush=True)
        assert np.all(pred>=0)
        score=float(balanced_accuracy_score(y,pred))
        cm=confusion_matrix(y,pred,labels=sorted(label_names))
        summary['tasks'][task]=dict(units=len(y),nested_unit_balanced_accuracy=score,
                                    label_order=[label_names[i] for i in sorted(label_names)],
                                    confusion_matrix=cm.tolist(),folds=fold_rows)
        result_rows.append(dict(comparison=task,units=len(y),nested_unit_balanced_accuracy=score))
        for index,value in zip(indices,pred):
            predictions[index][task+'_prediction']=label_names[int(value)]
        for index in np.where(~mask)[0]:
            predictions[index][task+'_prediction']=''
        if task=='four_class':
            four_pred=pred
        (OUT/'unit_discrimination_summary.json').write_text(json.dumps(summary,indent=2))
        print('Completed',task,score,flush=True)
    base.write_csv(OUT/'unit_discrimination_results.csv',result_rows)
    base.write_csv(OUT/'unit_discrimination_predictions.csv',predictions)
    # Previously searched descriptive projections; display only unit-level results.
    pca,lda=base.projection(x,original_y,names,sets,[])
    fig,axes=plt.subplots(1,3,figsize=(15,5.5))
    colors=['#7e7e7e','#e94b47','#64af54','#9462d5']
    for ax,coords,title in [(axes[0],pca[4],'PCA: selected firing metrics'),
                            (axes[1],lda[3],'LDA: supervised unit discrimination')]:
        for c,name in enumerate(base.CLASSES):
            pts=coords[original_y==c]
            ax.scatter(pts[:,0],pts[:,1],s=10,alpha=.40,color=colors[c],linewidths=0,
                       label=f'{name}: {len(pts)} units')
            vals,vecs=np.linalg.eigh(np.cov(pts.T))
            angle=np.degrees(np.arctan2(vecs[1,-1],vecs[0,-1]))
            ax.add_patch(Ellipse(pts.mean(axis=0),2*np.sqrt(max(vals[-1],0)),
                         2*np.sqrt(max(vals[0],0)),angle=angle,facecolor=colors[c],
                         edgecolor=colors[c],alpha=.14))
        ax.axhline(0,color='gray',ls='--',lw=.5)
        ax.axvline(0,color='gray',ls='--',lw=.5)
        ax.set_title(title,fontsize=11)
        ax.spines[['top','right']].set_visible(False)
    axes[0].set_xlabel(f'PC1 ({pca[3].explained_variance_ratio_[0]*100:.1f}%)')
    axes[0].set_ylabel(f'PC2 ({pca[3].explained_variance_ratio_[1]*100:.1f}%)')
    axes[0].legend(fontsize=8,frameon=False)
    axes[1].set_xlabel('LD1')
    axes[1].set_ylabel('LD2')
    cm=confusion_matrix(original_y,four_pred,labels=range(4))
    normalized=cm/cm.sum(axis=1,keepdims=True)*100
    axes[2].imshow(normalized,vmin=0,vmax=100,cmap='Blues')
    for i in range(4):
        for j in range(4):
            axes[2].text(j,i,f'{normalized[i,j]:.1f}%\n({cm[i,j]} units)',ha='center',va='center',
                         fontsize=8,color='white' if normalized[i,j]>50 else 'black')
    axes[2].set_xticks(range(4),base.CLASSES,rotation=35,ha='right')
    axes[2].set_yticks(range(4),base.CLASSES)
    axes[2].set_xlabel('Predicted unit class')
    axes[2].set_ylabel('Actual unit class')
    score=summary['tasks']['four_class']['nested_unit_balanced_accuracy']
    axes[2].set_title(f'Held-out UNITS: {score:.1%} balanced accuracy',fontsize=11)
    fig.suptitle('Actuators + effectors: discrimination among 1,554 units',fontsize=15)
    fig.text(.5,.024,'Each dot = one sorted unit; SUA/MUA pooled. Ellipses = 1-SD unit spread.\n'
             'PCA features and LDA optimized descriptively using all unit labels; right panel uses nested 3-fold unit validation.\n'
             'All preprocessing and model selection for validation use training units only. First STG train, −10 to +10 s; no artifact blanking.',
             ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.15,1,.94))
    destination=OUT/'unit_discrimination.png'
    fig.savefig(destination,dpi=150)
    plt.close(fig)
    lines=['# Discrimination among sorted units','',
           '**One sorted unit is one sample. Each dot is a unit; SUA and MUA are pooled.**',
           '', 'Actuators + effectors only: 1,554 units (230 DREADD, 512 LMO, 339 PSAM, 473 Control).',
           'Original folder and recording IDs are metadata and do not define the validation splits.',
           '', '## Unit validation', '',
           'Three stratified outer folds. Every unit is held out once. Within each outer training set,',
           '56 feature/model combinations are evaluated using two stratified unit splits; the best is fitted',
           'on outer training units and predicts outer held-out units. Imputation, centering/scaling,',
           'and feature selection are fitted on training units only. No original-folder holdout is used.',
           'Units from the same recording may occur in training and testing; this evaluates unit discrimination within this dataset.',
           '', '| Comparison | Units | Nested held-out-unit balanced accuracy |',
           '| --- | ---: | ---: |']
    lines += [f"| {r['comparison']} | {r['units']} | {r['nested_unit_balanced_accuracy']:.1%} |" for r in result_rows]
    lines += ['', '## Visualizations', '',
              'The PCA feature search and supervised LDA use all unit labels to find descriptive separation.',
              'Their displayed fitted clouds are not held-out predictions. The confusion matrix is held-out-unit prediction.',
              'Ellipses show one-SD spread, not confidence intervals. No stimulation-artifact validation or significance testing is added.',
              '', '## Metrics and reproducibility', '',
              'The 156 metrics and definitions are in README.md and metric_catalog.csv in this directory.',
              'The same unit_metrics.csv is reused without copying continuous signals or recomputing sorting.',
              'Fold-specific selected feature families and classifiers are in unit_discrimination_summary.json.',
              'Source: scripts/redo_mcs_unit_discrimination.py. Only one new PNG and compact result/prediction tables are saved.']
    (OUT/'UNIT_DISCRIMINATION.md').write_text('\n'.join(lines)+'\n')
    print('COMPLETE',destination,destination.stat().st_size,flush=True)

if __name__=='__main__':
    main()
