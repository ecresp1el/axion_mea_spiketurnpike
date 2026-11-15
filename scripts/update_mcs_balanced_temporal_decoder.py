"""Recompute every temporal decoder panel using equal class priors."""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import roc_auc_score,confusion_matrix,balanced_accuracy_score
from compose_mcs_paper_layout import SOURCE,OUT,GROUPS

def main():
    dest=OUT/'balanced_decoder';dest.mkdir(parents=True,exist_ok=True)
    data=np.load(SOURCE/'unit_window_metrics.npz');x=data['values']
    times=(data['bin_edges_s'][:-1]+data['bin_edges_s'][1:])/2
    y=np.array([GROUPS.index(g) for g in data['construct']]);n=len(y)
    x=np.sign(x)*np.log1p(np.abs(x))
    folds=list(StratifiedKFold(3,shuffle=True,random_state=20261114).split(np.zeros(n),y))
    prob=np.full((20,20,n,4),np.nan);fold_id=np.full(n,-1)
    for fold,(train,test) in enumerate(folds):
        fold_id[test]=fold
        for source in range(20):
            fitted=make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler(),
                   LinearDiscriminantAnalysis(solver='lsqr',shrinkage=.01,priors=np.ones(4)/4)).fit(x[train,source],y[train])
            for target in range(20):prob[source,target,test]=fitted.predict_proba(x[test,target])
        print('BALANCED fold',fold,flush=True)
    assert np.isfinite(prob).all() and np.allclose(prob.sum(axis=3),1)
    def auc(p):return np.array([roc_auc_score(y==c,p[:,c]) for c in range(4)])
    per_class=np.array([auc(prob[t,t]) for t in range(20)])
    cross=np.array([[auc(prob[s,t]).mean() for t in range(20)] for s in range(20)])
    pooled=np.mean([prob[t,t] for t in np.flatnonzero((times>0)&(times<5))],axis=0)
    pred=pooled.argmax(axis=1);cm=confusion_matrix(y,pred,normalize='true')
    assert np.allclose(cross.diagonal(),per_class.mean(axis=1))
    pd.DataFrame(dict(time_s=times,macro_auroc=per_class.mean(axis=1),
                     **{g+'_auroc':per_class[:,c] for c,g in enumerate(GROUPS)},
                     balanced_accuracy=[balanced_accuracy_score(y,prob[t,t].argmax(axis=1)) for t in range(20)])).to_csv(dest/'time_resolved_decoding.csv',index=False)
    pd.DataFrame(cross,index=times,columns=times).rename_axis('training_bin_center_s').to_csv(dest/'cross_time_macro_auroc.csv')
    pd.DataFrame(cm,index=GROUPS,columns=GROUPS).rename_axis('true_construct').to_csv(dest/'poststim_confusion_matrix.csv')
    keys=pd.DataFrame(dict(recording_id=data['recording_id'],unit_id=data['unit_id'],construct=data['construct'],fold=fold_id,
                           poststim_predicted_construct=[GROUPS[i] for i in pred]))
    keys.to_csv(dest/'unit_folds_and_predictions.csv',index=False)
    audit=json.loads((OUT/'psam_diagnostic.json').read_text())['diagnostic']['equal_priors']
    assert np.allclose(cm,audit['confusion'])
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    summary=dict(active_temporal_decoder=True,priors=[.25]*4,feature_count=6,shrinkage=.01,
                 folds=3,seed=20261114,units=n,locked_215_model_changed=False,
                 post_0_5_macro_auroc=float(auc(pooled).mean()),
                 post_0_5_balanced_accuracy=float(balanced_accuracy_score(y,pred)),
                 psam_recall=float(cm[3,3]),pre_macro_auroc_mean=float(per_class[times<0].mean()),
                 post_macro_auroc_mean=float(per_class[times>0].mean()),
                 sources={str(p):sha(p) for p in [SOURCE/'unit_window_metrics.npz',Path(__file__)]})
    summary['outputs']={p.name:sha(p) for p in dest.glob('*.csv')}
    (dest/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('COMPLETE BALANCED',json.dumps(summary),flush=True)

if __name__=='__main__':main()
