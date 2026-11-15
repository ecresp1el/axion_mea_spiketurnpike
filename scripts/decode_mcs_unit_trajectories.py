"""Causal-prefix LDA: evolving class probabilities from ordered unit responses."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter1d
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import roc_auc_score,balanced_accuracy_score,confusion_matrix
from extract_mcs_unit_trajectories import OUT

GROUPS=['Control','DREADD','LMO','PSAM']
COLORS=['#777777','#e94b47','#64af54','#9462d5']

def main():
    source=OUT/'unit_100ms_spike_counts.npz';data=np.load(source)
    counts=data['counts'];y=np.array([GROUPS.index(v) for v in data['construct']]);n=len(y)
    baseline=counts[:,50:100].sum(axis=1)/5
    rate=counts[:,100:]/.1
    response=rate-baseline[:,None]
    x=np.sign(response)*np.log1p(np.abs(response))
    endpoints=np.arange(1,101)*.1
    probability=np.full((n,100,4),np.nan,dtype=np.float64)
    rate_only=np.full_like(probability,np.nan);fold_id=np.full(n,-1)
    folds=list(StratifiedKFold(3,shuffle=True,random_state=20261114).split(np.zeros(n),y))
    for fold,(train,test) in enumerate(folds):
        fold_id[test]=fold
        for h in range(1,101):
            # Prefix slicing is the only input: no bins after this endpoint.
            scaler=StandardScaler().fit(x[train,:h]);a=scaler.transform(x[train,:h]);b=scaler.transform(x[test,:h])
            fitted=LinearDiscriminantAnalysis(solver='lsqr',shrinkage=.01,priors=np.ones(4)/4).fit(a,y[train])
            probability[test,h-1]=fitted.predict_proba(b)
            assert np.array_equal(fitted.classes_,np.arange(4))
            scalar=response[:,:h].mean(axis=1)[:,None]
            scalar=np.sign(scalar)*np.log1p(np.abs(scalar))
            scale=StandardScaler().fit(scalar[train])
            control=LinearDiscriminantAnalysis(solver='lsqr',shrinkage=.01,priors=np.ones(4)/4).fit(scale.transform(scalar[train]),y[train])
            rate_only[test,h-1]=control.predict_proba(scale.transform(scalar[test]))
        print('TRAJECTORY fold',fold,'100 prefixes',flush=True)
    assert np.isfinite(probability).all() and np.allclose(probability.sum(axis=2),1)
    assert np.isfinite(rate_only).all() and np.allclose(rate_only.sum(axis=2),1)
    # Save every unit, every endpoint, every class probability for direct access.
    np.savez_compressed(OUT/'unit_probability_trajectories.npz',probabilities=probability.astype(np.float32),
                rate_only_probabilities=rate_only.astype(np.float32),time_s=endpoints,
                class_order=np.array(GROUPS),recording_id=data['recording_id'],unit_id=data['unit_id'],
                construct=data['construct'],fold=fold_id)
    keys=pd.DataFrame(dict(recording_id=data['recording_id'],unit_id=data['unit_id'],construct=data['construct'],fold=fold_id))
    for h in [9,49,99]:
        keys[f'prediction_{endpoints[h]:g}s']=[GROUPS[c] for c in probability[:,h].argmax(axis=1)]
        keys[f'true_group_probability_{endpoints[h]:g}s']=probability[np.arange(n),h,y]
    keys.to_csv(OUT/'unit_trajectory_index.csv',index=False)
    summary=[];performance=[]
    for h,t in enumerate(endpoints):
        pred=probability[:,h].argmax(axis=1);auc=[];rate_auc=[]
        for c in range(4):
            auc.append(roc_auc_score(y==c,probability[:,h,c]))
            rate_auc.append(roc_auc_score(y==c,rate_only[:,h,c]))
        performance.append(dict(time_available_s=t,prefix_100ms_bins=h+1,
                        trajectory_macro_auroc=np.mean(auc),rate_only_macro_auroc=np.mean(rate_auc),
                        trajectory_balanced_accuracy=balanced_accuracy_score(y,pred)))
        for c,g in enumerate(GROUPS):
            v=probability[y==c,h,:]
            for k,predicted in enumerate(GROUPS):
                avg=v[:,k].mean();sem=v[:,k].std(ddof=1)/np.sqrt(len(v))
                summary.append(dict(actual_group=g,predicted_group=predicted,time_s=t,n_units=len(v),
                             mean_probability=avg,ci95_low=max(0,avg-1.96*sem),ci95_high=min(1,avg+1.96*sem)))
    summaries=pd.DataFrame(summary);summaries.to_csv(OUT/'probability_time_courses.csv',index=False)
    pd.DataFrame(performance).to_csv(OUT/'trajectory_decoding_performance.csv',index=False)
    # Display rates with modest smoothing; this smoothing never enters a decoder.
    smooth=gaussian_filter1d(rate,1,axis=1,mode='reflect',truncate=3)
    response_summary=[]
    for c,g in enumerate(GROUPS):
        v=smooth[y==c];mean=v.mean(axis=0);sem=v.std(axis=0,ddof=1)/np.sqrt(len(v))
        for j in range(100):response_summary.append(dict(construct=g,time_s=(j+.5)*.1,
                            mean_hz=mean[j],ci95_low=max(0,mean[j]-1.96*sem[j]),ci95_high=mean[j]+1.96*sem[j]))
    responses=pd.DataFrame(response_summary);responses.to_csv(OUT/'response_time_courses.csv',index=False)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':10,'pdf.fonttype':42})
    fig=plt.figure(figsize=(14,10))
    grid=fig.add_gridspec(3,4,left=.075,right=.95,bottom=.13,top=.87,wspace=.34,hspace=.40,
                          height_ratios=[.75,1,1.15])
    for c,g in enumerate(GROUPS):
        a=fig.add_subplot(grid[0,c]);v=responses[responses['construct']==g]
        a.plot(v['time_s'],v['mean_hz'],color=COLORS[c],lw=1.4)
        a.fill_between(v['time_s'].to_numpy(),v['ci95_low'].to_numpy(),v['ci95_high'].to_numpy(),color=COLORS[c],alpha=.2,lw=0)
        a.set(title=f'{g} · {np.sum(y==c)} units',xlim=(0,10),ylim=(0,responses['ci95_high'].max()*1.05))
        if c==0:a.set_ylabel('Observed firing\n(Hz/unit)')
        a.set_xticklabels([]);a.spines[['top','right']].set_visible(False)
        a.text(-.15,1.08,chr(97+c),transform=a.transAxes,fontweight='bold',fontsize=12)
        b=fig.add_subplot(grid[1,c])
        for k,predicted in enumerate(GROUPS):
            v=summaries[(summaries['actual_group']==g)&(summaries['predicted_group']==predicted)]
            b.plot(v['time_s'],v['mean_probability'],color=COLORS[k],lw=1.4)
            b.fill_between(v['time_s'].to_numpy(),v['ci95_low'].to_numpy(),v['ci95_high'].to_numpy(),color=COLORS[k],alpha=.12,lw=0)
        b.axhline(.25,color='#aaaaaa',ls=':',lw=.8)
        b.set(xlim=(0,10),ylim=(0,1));b.set_xticklabels([])
        if c==0:b.set_ylabel('Predicted group\nprobability')
        b.spines[['top','right']].set_visible(False)
        b.text(-.15,1.08,chr(101+c),transform=b.transAxes,fontweight='bold',fontsize=12)
        heat=fig.add_subplot(grid[2,c])
        indices=np.flatnonzero(y==c)
        # Natural recording/unit order; never sort units by successful predictions.
        trueprob=probability[indices,:,c]
        im=heat.imshow(trueprob,origin='upper',aspect='auto',extent=[.05,10.05,len(indices)+.5,.5],
                       cmap='viridis',vmin=0,vmax=1,interpolation='nearest')
        rid=data['recording_id'][indices]
        for boundary in np.flatnonzero(rid[1:]!=rid[:-1])+1:heat.axhline(boundary+.5,color='white',lw=.35,alpha=.6)
        heat.set(xlim=(0,10),xlabel='Available post-stimulus time (s)')
        if c==0:heat.set_ylabel('Units\n(recording boundaries in white)')
        heat.text(-.15,1.08,chr(105+c),transform=heat.transAxes,fontweight='bold',fontsize=12)
    colorbar=fig.add_axes([.96,.13,.009,.25]);fig.colorbar(im,cax=colorbar).set_label('True-group probability',fontsize=7,labelpad=2)
    fig.suptitle('How each unit’s group prediction evolves after stimulation',fontsize=15,y=.97)
    handles=[plt.Line2D([0],[0],color=color,lw=2,label=g) for g,color in zip(GROUPS,COLORS)]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.51,.935),ncol=4,frameon=False,title='Predicted group')
    fig.text(.51,.025,'Each 100-ms update uses only the ordered response from 0 to the current endpoint; no later post-stimulus bins enter the prediction.\n'
        'Three fixed held-out-unit folds; equal class priors. Top: firing responses. Middle: mean class probabilities ± pointwise unit intervals.\n'
        'Bottom: one row per unit, colored by probability of its actual group. These are decoder scores, not calibrated biological probabilities.\n'
        'Separate cumulative-response LDA; locked 215-feature model unchanged. Unit-wise baseline correction uses −5 to 0 s. E-stim artifacts included.',
        ha='center',fontsize=7,linespacing=1.4)
    for suffix in ['png','pdf']:fig.savefig(OUT/f'unit_response_probability_trajectories.{suffix}',dpi=320,facecolor='white',bbox_inches='tight')
    plt.close(fig)
    selected={}
    for h in [9,49,99]:
        pred=probability[:,h].argmax(axis=1)
        selected[str(endpoints[h])]=dict(performance=performance[h],confusion=confusion_matrix(y,pred,normalize='true').tolist())
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    info=dict(model='LDA with increasing ordered 100-ms response prefix',priors=[.25]*4,shrinkage=.01,
              units=n,folds=3,seed=20261114,prefix_endpoints_s=endpoints.tolist(),
              baseline='Per-unit mean firing in −5 to 0 s subtracted from each post-bin firing rate',
              preprocessing='Signed log1p; scaling fitted only on training units at each prefix',
              smoothing='Top firing display only: sigma 100 ms; decoder uses unsmoothed counts',
              score_intervals='Mean ±1.96 SEM over held-out units; descriptive pointwise intervals',
              locked_215_model_modified=False,selected_endpoints=selected,
              sources={str(p):sha(p) for p in [source,Path(__file__)]})
    info['outputs']={p.name:sha(p) for p in OUT.iterdir() if p.suffix in ['.csv','.npz','.png','.pdf']}
    (OUT/'trajectory_model_manifest.json').write_text(json.dumps(info,indent=2)+'\n')
    print('COMPLETE TRAJECTORY',json.dumps(selected),flush=True)

if __name__=='__main__':main()
