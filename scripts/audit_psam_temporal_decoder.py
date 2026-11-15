"""Assess PSAM signal, support, and class-prior sensitivity without changing models."""
import json,warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import confusion_matrix,balanced_accuracy_score,roc_auc_score
from compose_mcs_paper_layout import SOURCE,OUT,GROUPS

def main():
    data=np.load(SOURCE/'unit_window_metrics.npz');x=data['values'];names=data['feature_names']
    y=np.array([GROUPS.index(g) for g in data['construct']]);post=range(10,15)
    folds=list(StratifiedKFold(3,shuffle=True,random_state=20261114).split(np.zeros(len(y)),y))
    results={}
    for name,priors in [('empirical_priors',None),('equal_priors',np.ones(4)/4)]:
        prob=np.zeros((len(y),4))
        for train,test in folds:
            for t in post:
                model=make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler(),
                           LinearDiscriminantAnalysis(solver='lsqr',shrinkage=.01,priors=priors))
                v=x[:,t];v=np.sign(v)*np.log1p(np.abs(v))
                model.fit(v[train],y[train]);prob[test]+=model.predict_proba(v[test])/5
        prediction=prob.argmax(axis=1);conf=confusion_matrix(y,prediction,normalize='true')
        results[name]=dict(confusion=conf.tolist(),balanced_accuracy=float(balanced_accuracy_score(y,prediction)),
                          macro_auroc=float(np.mean([roc_auc_score(y==c,prob[:,c]) for c in range(4)])),
                          psam_recall=float(conf[3,3]),psam_auroc=float(roc_auc_score(y==3,prob[:,3])))
        if name=='empirical_priors':
            old=pd.read_csv(SOURCE/'unit_folds_and_predictions.csv',dtype={'unit_id':str})
            assert np.array_equal(prediction,np.array([GROUPS.index(g) for g in old['poststim_predicted_construct']]))
    support=[]
    for c,g in enumerate(GROUPS):
        for f,n in enumerate(names):
            finite=np.isfinite(x[y==c,10:15,f])
            support.append(dict(construct=g,metric=str(n),units=int(np.sum(y==c)),
                                units_with_any_valid_post=int(finite.any(axis=1).sum()),
                                fraction_unit_bins_missing=float(1-finite.mean())))
    predictions=pd.read_csv(SOURCE/'unit_folds_and_predictions.csv',dtype={'unit_id':str})
    originals=pd.read_csv(SOURCE.parent/'poststim_publication/selected_unit_pre_post.csv',dtype={'unit_id':str})
    joined=predictions.merge(originals,on=['recording_id','unit_id','construct'],validate='one_to_one')
    per_record=[]
    for rid,v in joined.groupby('recording_id',sort=False):
        per_record.append(dict(recording_id=rid,construct=v['construct'].iloc[0],n_units=len(v),
                        recall=float((v['poststim_predicted_construct']==v['construct']).mean()),
                        pre_rate=float(v['firing_rate_pre'].mean()),post_rate=float(v['firing_rate_post'].mean()),
                        rate_change=float(v['firing_rate_change'].mean())))
    group_rates=joined.groupby('construct')[['firing_rate_pre','firing_rate_post','firing_rate_change']].mean().to_dict('index')
    result=dict(class_priors={g:float(np.mean(y==c)) for c,g in enumerate(GROUPS)},
                diagnostic=results,valid_support=support,raw_group_rates=group_rates,
                recording_counts=predictions.groupby('construct')['recording_id'].nunique().to_dict(),
                audit_does_not_modify_decoder=True)
    (OUT/'psam_diagnostic.json').write_text(json.dumps(result,indent=2)+'\n')
    pd.DataFrame(per_record).to_csv(OUT/'recording_decoder_audit.csv',index=False)
    print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
