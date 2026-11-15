"""Matched unit-label permutation null and conditional bootstrap bands for panel j."""
import hashlib,json,multiprocessing as mp,os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.model_selection import StratifiedKFold
from compose_mcs_paper_layout import SOURCE,OUT,GROUPS

PREPARED=None
LABELS=None
FOLDS=None
OBSERVED=None

def macro_auc(prob,labels):
    result=np.zeros(20)
    for c in range(4):
        positive=labels==c;npos=int(positive.sum());nneg=len(labels)-npos
        for t in range(20):
            ranks=rankdata(prob[t,:,c],method='average')
            result[t]+=(ranks[positive].sum()-npos*(npos+1)/2)/(npos*nneg)/4
    return result

def decoder(labels):
    prob=np.full((20,len(labels),4),np.nan)
    for train,test,training,testing in PREPARED:
        for t in range(20):
            fitted=LinearDiscriminantAnalysis(solver='lsqr',shrinkage=.01,priors=np.ones(4)/4).fit(training[t],labels[train])
            prob[t,test]=fitted.predict_proba(testing[t])
    assert np.isfinite(prob).all()
    return prob

def permute(seed):
    rng=np.random.default_rng(seed);labels=LABELS.copy()
    # Keep original class counts in every fixed fold; same shuffled label at all times.
    for _,test in FOLDS:labels[test]=rng.permutation(labels[test])
    return macro_auc(decoder(labels),labels)

def bootstrap(seed):
    rng=np.random.default_rng(seed)
    indices=np.concatenate([rng.choice(np.flatnonzero(LABELS==c),size=np.sum(LABELS==c),replace=True) for c in range(4)])
    return macro_auc(OBSERVED[:,indices,:],LABELS[indices])

def main():
    global PREPARED,LABELS,FOLDS,OBSERVED
    dest=OUT/'balanced_decoder';data=np.load(SOURCE/'unit_window_metrics.npz')
    x=data['values'];x=np.sign(x)*np.log1p(np.abs(x))
    LABELS=np.array([GROUPS.index(g) for g in data['construct']])
    FOLDS=list(StratifiedKFold(3,shuffle=True,random_state=20261114).split(np.zeros(len(x)),LABELS))
    PREPARED=[]
    for train,test in FOLDS:
        a=[];b=[]
        for t in range(20):
            preprocessing=make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler())
            a.append(preprocessing.fit_transform(x[train,t]));b.append(preprocessing.transform(x[test,t]))
        PREPARED.append((train,test,a,b))
    OBSERVED=decoder(LABELS);observed=macro_auc(OBSERVED,LABELS)
    original=pd.read_csv(dest/'time_resolved_decoding.csv')
    assert np.allclose(observed,original['macro_auroc'].to_numpy(),atol=1e-12,rtol=0)
    n_perm=1000;n_boot=1000
    workers=min(4,int(os.environ.get('SLURM_CPUS_PER_TASK','1')))
    # Fork shares read-only cached training transforms and held-out probabilities.
    with mp.get_context('fork').Pool(workers) as pool:
        null=[]
        for i,v in enumerate(pool.imap(permute,range(2026111500,2026111500+n_perm),chunksize=5),1):
            null.append(v)
            if i%100==0:print('PERMUTATIONS',i,'/',n_perm,flush=True)
        boots=list(pool.imap(bootstrap,range(2026112500,2026112500+n_boot),chunksize=10))
    null=np.array(null);boots=np.array(boots)
    assert null.shape==boots.shape==(1000,20)
    low,high=np.percentile(boots,[2.5,97.5],axis=0)
    null_low,null_high=np.percentile(null,[2.5,97.5],axis=0);null_mean=null.mean(axis=0)
    point=(1+(null>=observed).sum(axis=0))/(n_perm+1)
    null_max=np.max(null-null_mean,axis=1)
    family=(1+(null_max[:,None]>=observed[None,:]-null_mean).sum(axis=0))/(n_perm+1)
    table=pd.DataFrame(dict(time_s=original['time_s'],observed_macro_auroc=observed,
            observed_ci95_low=low,observed_ci95_high=high,null_mean=null_mean,
            null_percentile025=null_low,null_percentile975=null_high,
            permutation_p=point,maxT_20bin_p=family))
    table.to_csv(dest/'panel_j_observed_and_shuffled.csv',index=False)
    np.savez_compressed(dest/'panel_j_resamples.npz',null_macro_auroc=null,
                        bootstrap_macro_auroc=boots,time_s=original['time_s'].to_numpy())
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    info=dict(permutations=n_perm,bootstraps=n_boot,observation='sorted unit',
         shuffle='Permute unit labels independently within each fixed test-fold partition; one assignment shared across all times',
         refit='Refit each of 3 fold-specific LDA classifiers at each of 20 times per permutation',
         preprocessing='Training-only imputation/scaling cached because they are label independent and folds are fixed',
         priors=[.25]*4,observed_band='Pointwise 95% class-stratified unit-bootstrap interval of fixed out-of-fold predictions; no refit',
         null_band='Pointwise 2.5–97.5 percentile range across label-permuted refits, not CI of null mean',
         feature_selection='Fixed previously explored six features; selection is not repeated under permutation',
         workers=workers,mean_null=float(null.mean()),
         sources={str(p):sha(p) for p in [SOURCE/'unit_window_metrics.npz',dest/'time_resolved_decoding.csv',Path(__file__)]})
    info['outputs']={n:sha(dest/n) for n in ['panel_j_observed_and_shuffled.csv','panel_j_resamples.npz']}
    (dest/'panel_j_null_methods.json').write_text(json.dumps(info,indent=2)+'\n')
    print('COMPLETE null mean',null.mean(),'observed range',observed.min(),observed.max(),flush=True)

if __name__=='__main__':main()
