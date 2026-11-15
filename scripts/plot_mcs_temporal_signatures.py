"""Unit-level activity signatures and honest time-resolved exploratory decoding."""
from pathlib import Path
import csv
import hashlib
import json
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score, confusion_matrix, balanced_accuracy_score
from load_mcs_locked_lda import load_units, project_units, CONFIG
from explore_mcs_burst_lda import burst_summary

REPO=Path(__file__).resolve().parents[1]
ROOT=Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis')
OUT=ROOT/'temporal_signatures'
GROUPS=['Control','DREADD','LMO','PSAM']
COLORS=['#777777','#e94b47','#64af54','#9462d5']
NAMES=['rate_change','fast_burst_rate','burst_duration','firing_rate','first_burst_delay','interburst_pause']
LABELS=['Firing-rate change','Fast bursts per second','Average burst duration','Firing rate','Delay to first burst','Pause between bursts']
UNITS=['Hz/unit','bursts/s','seconds','Hz/unit','seconds','seconds']
EDGES=np.arange(-10,11,dtype=float)
TIME=(EDGES[:-1]+EDGES[1:])/2

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def extract(meta):
    records={r['recording_id']:r for r in csv.DictReader((REPO/'metadata/mcs_recording_biology.csv').open())}
    x=np.full((len(meta),20,6),np.nan)
    sources=[]
    for rid, units in meta.groupby('recording_id',sort=False):
        record=records[rid]
        files=list((Path(record['sorting_output_path'])/'curated').glob('*/numpysorting_info.json'))
        assert len(files)==1
        info=json.loads(files[0].read_text());assert info['num_segments']==1
        fs=float(info['sampling_frequency']);onset=float(units['event_time_s'].iloc[0]);center=onset*fs
        if abs(center-round(center))<1e-7:center=float(round(center))
        assert onset>=10 and onset+10<=float(record['duration_s'])
        spikes=np.load(files[0].parent/'spikes.npy',mmap_mode='r',allow_pickle=False)
        lo,hi=np.searchsorted(spikes['sample_index'],[center-10*fs-1e-7,center+10*fs-1e-7])
        window=spikes[lo:hi];relative=window['sample_index']-center
        lookup={str(uid):i for i,uid in enumerate(info['unit_ids'])}
        for index, row in units.iterrows():
            samples=relative[window['unit_index']==lookup[row['unit_id']]]
            baseline=np.sum((samples>=-5*fs-1e-7)&(samples< -1e-7))/5
            for k,(a,b) in enumerate(zip(EDGES[:-1],EDGES[1:])):
                selected=samples[(samples>=a*fs-1e-7)&(samples<b*fs-1e-7)]/fs
                rate=len(selected)/(b-a)
                fast=burst_summary(selected,a,b,.010,3)
                duration=burst_summary(selected,a,b,.100,5)
                delay=burst_summary(selected,a,b,.100,3)
                pause=burst_summary(selected,a,b,.050,3)
                x[index,k]=[rate-baseline,fast['rate_hz'],duration['duration_mean'],rate,
                            delay['first_burst_latency'],pause['interburst_gap_mean']]
        sources.append(dict(recording_id=rid,sorting=str(files[0].parent),
                            info_sha256=sha(files[0]),onset_s=onset,units=len(units),
                            spike_file_bytes=(files[0].parent/'spikes.npy').stat().st_size))
        print('EXTRACTED',rid,len(units),flush=True)
    return x,sources

def signed(x):return np.sign(x)*np.log1p(np.abs(x))

def model():
    return make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler(),
                         LinearDiscriminantAnalysis(solver='lsqr',shrinkage=.01))

def auc(y,prob):
    return np.array([roc_auc_score(y==c,prob[:,c]) for c in range(4)])

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    meta,raw=load_units();meta=meta.reset_index(drop=True)
    frozen,_=project_units(raw)
    y=np.array([GROUPS.index(v) for v in meta['construct']]);n=len(y)
    x,sources=extract(meta)
    np.savez_compressed(OUT/'unit_window_metrics.npz',values=x,feature_names=np.array(NAMES),
                        bin_edges_s=EDGES,recording_id=meta['recording_id'].to_numpy(str),
                        unit_id=meta['unit_id'].to_numpy(str),construct=meta['construct'].to_numpy(str))
    folds=list(StratifiedKFold(3,shuffle=True,random_state=20261114).split(np.zeros(n),y))
    fold_id=np.full(n,-1)
    # One fixed partition at all times; a held-out unit never enters any training time.
    probabilities=np.full((20,20,n,4),np.nan)
    for fold,(train,test) in enumerate(folds):
        fold_id[test]=fold
        for source in range(20):
            fitted=model().fit(signed(x[train,source]),y[train])
            for target in range(20):
                probabilities[source,target,test]=fitted.predict_proba(signed(x[test,target]))
        print('DECODED fold',fold,flush=True)
    assert np.isfinite(probabilities).all()
    class_auc=np.array([auc(y,probabilities[t,t]) for t in range(20)])
    cross=np.array([[auc(y,probabilities[a,b]).mean() for b in range(20)] for a in range(20)])
    post=np.flatnonzero((TIME>0)&(TIME<5))
    postprob=np.mean(np.array([probabilities[t,t] for t in post]),axis=0)
    # One prediction per held-out unit, averaged across the same five post bins.
    predicted=postprob.argmax(axis=1)
    confusion=confusion_matrix(y,predicted,labels=range(4),normalize='true')
    axis=pd.DataFrame({'time_s':TIME,'macro_auroc':class_auc.mean(axis=1),
                       **{g+'_auroc':class_auc[:,c] for c,g in enumerate(GROUPS)},
                       'balanced_accuracy':[balanced_accuracy_score(y,probabilities[t,t].argmax(axis=1)) for t in range(20)]})
    axis.to_csv(OUT/'time_resolved_decoding.csv',index=False)
    pd.DataFrame(cross,index=TIME,columns=TIME).rename_axis('training_bin_center_s').to_csv(OUT/'cross_time_macro_auroc.csv')
    pd.DataFrame(confusion,index=GROUPS,columns=GROUPS).rename_axis('true_construct').to_csv(OUT/'poststim_confusion_matrix.csv')
    table=meta[['recording_id','unit_id','construct']].copy();table['fold']=fold_id
    table['poststim_predicted_construct']=[GROUPS[c] for c in predicted]
    table.to_csv(OUT/'unit_folds_and_predictions.csv',index=False)
    means=np.full((4,20,6),np.nan);sems=np.full_like(means,np.nan);counts=np.zeros_like(means,int)
    for c in range(4):
        v=x[y==c];counts[c]=np.isfinite(v).sum(axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            means[c]=np.nanmean(v,axis=0)
            sems[c]=np.nanstd(v,axis=0,ddof=1)/np.sqrt(counts[c])
    summaries=[]
    for c,g in enumerate(GROUPS):
        for t in range(20):
            for f,name in enumerate(NAMES):
                summaries.append(dict(construct=g,time_s=TIME[t],metric=name,unit=UNITS[f],
                                      n_valid=counts[c,t,f],mean=means[c,t,f],sem=sems[c,t,f]))
    pd.DataFrame(summaries).to_csv(OUT/'activity_mean_sem.csv',index=False)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        baseline_scale=np.nanstd(x[:,TIME<0,:].reshape(-1,6),axis=0,ddof=1)
        baseline_mean=np.nanmean(x[:,TIME<0,:],axis=1)
        group_baseline=np.array([np.nanmean(baseline_mean[y==c],axis=0) for c in range(4)])
    heat=(means-group_baseline[:,None,:])/np.where(baseline_scale>0,baseline_scale,np.nan)
    # Export normalized heatmap cells for exact reconstruction.
    pd.DataFrame([dict(construct=g,time_s=TIME[t],metric=name,baseline_scaled_change=heat[c,t,f])
                  for c,g in enumerate(GROUPS) for t in range(20) for f,name in enumerate(NAMES)]).to_csv(
                      OUT/'activity_heatmap_values.csv',index=False)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':10,'pdf.fonttype':42})
    fig=plt.figure(figsize=(17,11.5))
    grid=fig.add_gridspec(4,4,left=.08,right=.97,bottom=.15,top=.89,hspace=.62,wspace=.55,
                          height_ratios=[1,1,.10,1.2])
    axes=[]
    for col,f in enumerate([3,1,2,5]):
        ax=fig.add_subplot(grid[0,col]);axes.append(ax)
        for c,g in enumerate(GROUPS):
            ax.plot(TIME,means[c,:,f],color=COLORS[c],lw=1.5,label=g)
            ax.fill_between(TIME,means[c,:,f]-sems[c,:,f],means[c,:,f]+sems[c,:,f],
                            color=COLORS[c],alpha=.15,linewidth=0)
        ax.axvline(0,color='black',ls='--',lw=.8)
        ax.set(xlabel='Time from e-stim (s)',ylabel=UNITS[f],title=LABELS[f])
        if col==0:ax.legend(frameon=False,fontsize=7)
        ax.spines[['top','right']].set_visible(False)
    bound=max(.25,float(np.nanpercentile(np.abs(heat),98)))
    for c,g in enumerate(GROUPS):
        ax=fig.add_subplot(grid[1,c]);axes.append(ax)
        im=ax.imshow(heat[c].T,origin='upper',aspect='auto',extent=[-10,10,5.5,-.5],
                     cmap='RdBu_r',vmin=-bound,vmax=bound)
        ax.axvline(0,color='black',ls='--',lw=.8)
        ax.set_yticks(range(6),LABELS if c==0 else ['']*6,fontsize=7)
        ax.set(xlabel='Time from e-stim (s)',title=f'{g}: activity signature')
    cax=fig.add_subplot(grid[2,1:3])
    cb=fig.colorbar(im,cax=cax,orientation='horizontal');cb.ax.tick_params(labelsize=6)
    cb.set_label('Change from own-group baseline (pooled baseline SD)',fontsize=7)
    ax=fig.add_subplot(grid[3,0]);axes.append(ax)
    for c,g in enumerate(GROUPS):
        v=frozen[y==c];ax.scatter(*v.T,s=3,color=COLORS[c],alpha=.30,linewidths=0,rasterized=True)
        ax.scatter(*v.mean(axis=0),s=90,marker='*',c=COLORS[c],edgecolor='#222222',linewidth=.5)
    ax.set(xlabel='LD1',ylabel='LD2',title='Locked 215-metric overview')
    ax=fig.add_subplot(grid[3,1]);axes.append(ax)
    for c,g in enumerate(GROUPS):ax.plot(TIME,class_auc[:,c],color=COLORS[c],lw=1,label=g)
    ax.plot(TIME,class_auc.mean(axis=1),color='black',lw=2,label='Macro average')
    ax.axhline(.5,color='#999999',lw=.8,ls=':');ax.axvline(0,color='black',lw=.8,ls='--')
    ax.set(xlabel='Time from e-stim (s)',ylabel='Held-out unit AUROC',ylim=(0,1.03),title='Time-resolved decoding')
    ax.legend(frameon=False,fontsize=6,loc='lower right')
    ax=fig.add_subplot(grid[3,2]);axes.append(ax)
    im2=ax.imshow(confusion,cmap='Blues',vmin=0,vmax=1)
    for a in range(4):
        for b in range(4):ax.text(b,a,f'{100*confusion[a,b]:.0f}%',ha='center',va='center',fontsize=8,
                                 color='white' if confusion[a,b]>.55 else 'black')
    ax.set_xticks(range(4),GROUPS,rotation=40,ha='right',fontsize=7);ax.set_yticks(range(4),GROUPS,fontsize=7)
    ax.set(xlabel='Predicted group',ylabel='Actual group',title='0–5 s decoding: one vote per unit')
    ax=fig.add_subplot(grid[3,3]);axes.append(ax)
    im3=ax.imshow(cross,origin='lower',extent=[-10,10,-10,10],aspect='auto',cmap='viridis',vmin=.5,vmax=1)
    ax.axhline(0,color='white',lw=.7,ls='--');ax.axvline(0,color='white',lw=.7,ls='--')
    ax.set(xlabel='Testing time from e-stim (s)',ylabel='Training time from e-stim (s)',title='Cross-time decoding (AUROC)')
    fig.colorbar(im3,ax=ax,fraction=.045,pad=.03).ax.tick_params(labelsize=6)
    for i,ax in enumerate(axes):ax.text(-.16,1.12,chr(97+i),transform=ax.transAxes,fontweight='bold',fontsize=12)
    fig.suptitle('Actuators + effectors | Activity signatures and decoding around e-stim',fontsize=16,y=.97)
    fig.text(.52,.93,'1,554 units • first STG train at 0 s • non-overlapping 1-s windows • SUA/MUA pooled',ha='center',fontsize=10)
    fig.text(.52,.045,'Traces: unit mean ± SEM; burst-duration/pause summaries require qualifying bursts. Heatmaps: baseline-scaled group changes.\n'
             'Temporal LDA: six fixed local measurements, shrinkage 0.01; 3-fold held-out units, same unit splits at every time.\n'
             'Units from a recording may occur in both train/test sets. AUROC chance = 0.5. No statistical significance is implied.\n'
             'Panel i alone uses the unchanged locked 215-metric projection. Electrical stimulation artifacts remain included.',
             ha='center',fontsize=8,linespacing=1.5)
    fig.savefig(OUT/'temporal_activity_and_decoding.png',dpi=300,facecolor='white')
    fig.savefig(OUT/'temporal_activity_and_decoding.pdf',dpi=300,facecolor='white');plt.close(fig)
    summary=dict(units=n,groups={g:int(np.sum(y==c)) for c,g in enumerate(GROUPS)},
                 temporal_feature_names=NAMES,temporal_model='Separate six-feature LDA; lsqr, shrinkage 0.01',
                 window_edges_s=EDGES.tolist(),unit_folds=3,seed=20261114,
                 locked_model_modified=False,post_0_5_macro_auroc=float(auc(y,postprob).mean()),
                 post_0_5_balanced_accuracy=float(balanced_accuracy_score(y,predicted)),
                 pre_macro_auroc_mean=float(class_auc[TIME<0].mean()),
                 post_macro_auroc_mean=float(class_auc[TIME>0].mean()),
                 heatmap_baseline_sd=baseline_scale.tolist(),heatmap_group_baselines=group_baseline.tolist(),
                 heatmap_color_limit=bound,recordings=sources,
                 sources={str(p):sha(p) for p in [CONFIG,REPO/'metadata/mcs_recording_biology.csv',Path(__file__),
                          REPO/'scripts/load_mcs_locked_lda.py',REPO/'scripts/explore_mcs_burst_lda.py',
                          Path(json.loads(CONFIG.read_text())['frozen_raw_metrics_csv']),
                          Path(json.loads(CONFIG.read_text())['frozen_model_npz'])]},
                 reference='https://pmc.ncbi.nlm.nih.gov/articles/PMC13232143/#F3')
    summary['output_hashes']={p.name:sha(p) for p in OUT.iterdir() if p.suffix in ['.csv','.png','.pdf','.npz']}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('COMPLETE',json.dumps({k:summary[k] for k in ['post_0_5_macro_auroc','post_0_5_balanced_accuracy','pre_macro_auroc_mean','post_macro_auroc_mean']}),flush=True)

if __name__=='__main__':main()
