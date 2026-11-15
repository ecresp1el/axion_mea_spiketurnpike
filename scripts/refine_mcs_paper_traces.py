"""Fine firing-rate PSTHs and overlapping-window burst displays; no decoder changes."""
from pathlib import Path
import csv,json,warnings
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d
from load_mcs_locked_lda import load_units
from explore_mcs_burst_lda import burst_summary
from compose_mcs_paper_layout import SOURCE,OUT,GROUPS

REPO=Path(__file__).resolve().parents[1]

def main():
    meta,_=load_units();meta=meta.reset_index(drop=True)
    records={r['recording_id']:r for r in csv.DictReader((REPO/'metadata/mcs_recording_biology.csv').open())}
    edges=np.linspace(-10,10,2001);times=(edges[:-1]+edges[1:])/2
    # Centered 1-s burst support, evaluated every 50 ms; support never crosses t0.
    burst_centers=np.r_[np.arange(-9.5,-.49,.05),np.arange(.5,9.51,.05)]
    rates=np.zeros((len(meta),2000));baseline=np.zeros(len(meta))
    bursts=np.full((len(meta),len(burst_centers),4),np.nan)
    for rid,units in meta.groupby('recording_id',sort=False):
        record=records[rid];files=list((Path(record['sorting_output_path'])/'curated').glob('*/numpysorting_info.json'))
        assert len(files)==1
        info=json.loads(files[0].read_text());fs=float(info['sampling_frequency']);onset=float(units['event_time_s'].iloc[0]);center=onset*fs
        if abs(center-round(center))<1e-7:center=float(round(center))
        spikes=np.load(files[0].parent/'spikes.npy',mmap_mode='r')
        lo,hi=np.searchsorted(spikes['sample_index'],[center-10*fs-1e-7,center+10*fs-1e-7])
        selected=spikes[lo:hi];rel=selected['sample_index']-center
        lookup={str(uid):i for i,uid in enumerate(info['unit_ids'])}
        for i,r in units.iterrows():
            samples=rel[selected['unit_index']==lookup[r['unit_id']]]
            index=np.floor((samples/fs+10)/.01+1e-8).astype(int);index=index[(index>=0)&(index<2000)]
            rates[i]=np.bincount(index,minlength=2000)/.01
            baseline[i]=np.sum((samples>=-5*fs-1e-7)&(samples< -1e-7))/5
            for j,t in enumerate(burst_centers):
                a,b=t-.5,t+.5
                s=samples[(samples>=a*fs-1e-7)&(samples<b*fs-1e-7)]/fs
                fast=burst_summary(s,a,b,.01,3);duration=burst_summary(s,a,b,.1,5)
                delay=burst_summary(s,a,b,.1,3);pause=burst_summary(s,a,b,.05,3)
                bursts[i,j]=[fast['rate_hz'],duration['duration_mean'],delay['first_burst_latency'],pause['interburst_gap_mean']]
        print('REFINED',rid,len(units),flush=True)
    smooth=np.empty_like(rates)
    for a,b in [(0,1000),(1000,2000)]:smooth[:,a:b]=gaussian_filter1d(rates[:,a:b],30,axis=1,mode='reflect',truncate=3)
    # Smooth each unit's finite burst measurements, with normalized weights.
    # Missing values contribute no weight; estimates are display-only.
    burst_smooth=np.full_like(bursts,np.nan)
    for side in [burst_centers<0,burst_centers>0]:
        v=bursts[:,side,:];valid=np.isfinite(v)
        numerator=gaussian_filter1d(np.where(valid,v,0),6,axis=1,mode='reflect',truncate=3)
        weight=gaussian_filter1d(valid.astype(float),6,axis=1,mode='reflect',truncate=3)
        burst_smooth[:,side,:]=np.divide(numerator,weight,out=np.full_like(v,np.nan),where=weight>1e-8)
    bursts=burst_smooth
    reference=json.loads((OUT/'manifest.json').read_text());mean=np.array(reference['normalization_mean']);sd=np.array(reference['normalization_sd'])
    features={0:(times,smooth-baseline[:,None]),3:(times,smooth),
              1:(burst_centers,bursts[:,:,0]),2:(burst_centers,bursts[:,:,1]),
              4:(burst_centers,bursts[:,:,2]),5:(burst_centers,bursts[:,:,3])}
    rows=[]
    for f,(t,v) in features.items():
        normalized=(v-mean[f])/sd[f]
        for group in GROUPS:
            values=normalized[meta['construct'].to_numpy()==group]
            with warnings.catch_warnings():
                warnings.simplefilter('ignore');n=np.isfinite(values).sum(axis=0)
                m=np.nanmean(values,axis=0);sem=np.nanstd(values,axis=0,ddof=1)/np.sqrt(n)
            for j,tm in enumerate(t):rows.append(dict(construct=group,feature_index=f,time_s=float(tm),
                       mean=m[j],ci95_low=m[j]-1.96*sem[j],ci95_high=m[j]+1.96*sem[j],n_valid=int(n[j])))
    pd.DataFrame(rows).to_csv(OUT/'fine_display_time_courses.csv',index=False)
    print('COMPLETE fine display',len(rows),flush=True)

if __name__=='__main__':main()
