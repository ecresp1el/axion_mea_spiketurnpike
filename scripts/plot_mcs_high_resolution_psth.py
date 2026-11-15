"""10-ms e-stim PSTHs with onset zoom, unitwise 20-ms smoothing, mean/SEM."""
import csv
import gzip
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter1d
from load_mcs_locked_lda import load_units
import explore_mcs_actuator_separation as base

OUT=Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis')
WIDTH=.01
SIGMA=.02

def main():
    meta,_=load_units()
    records={r['recording_id']:r for r in csv.DictReader((base.REPO/'metadata/mcs_recording_biology.csv').open())}
    edges=np.linspace(-10,10,2001);centers=(edges[:-1]+edges[1:])/2
    matrices={c:[] for c in base.CLASSES}
    sources=[]
    for rid,units in meta.groupby('recording_id',sort=False):
        record=records[rid]
        files=list((Path(record['sorting_output_path'])/'curated').glob('*/numpysorting_info.json'))
        assert len(files)==1
        info=json.loads(files[0].read_text());assert info['num_segments']==1
        assert {str(uid) for uid in info['unit_ids']}==set(units['unit_id'])
        onset=float(units['event_time_s'].iloc[0]);fs=float(info['sampling_frequency'])
        spikes=np.load(files[0].parent/'spikes.npy',mmap_mode='r',allow_pickle=False)
        lo,hi=np.searchsorted(spikes['sample_index'],[(onset-10)*fs,(onset+10)*fs])
        window=spikes[lo:hi]
        relative=window['sample_index']/fs-onset
        index=np.floor((relative+10)/WIDTH+1e-9).astype(int)
        valid=(index>=0)&(index<len(centers))
        counts=np.zeros((len(info['unit_ids']),len(centers)),dtype=np.int32)
        np.add.at(counts,(window['unit_index'][valid],index[valid]),1)
        assert counts.sum()==valid.sum()
        matrices[record['construct']].append(counts/WIDTH)
        sources.append(dict(recording_id=rid,units=len(counts),onset_s=onset,sorting=str(files[0].parent)))
    fig,axes=plt.subplots(1,2,figsize=(12,5.3))
    colors={'Control':'#777777','DREADD':'#e94b47','LMO':'#64af54','PSAM':'#9462d5'}
    results=[]
    for construct in ['Control','DREADD','LMO','PSAM']:
        raw=np.concatenate(matrices[construct])
        assert len(raw)==int(np.sum(meta['construct']==construct))
        smooth=np.empty_like(raw)
        # Never smooth stimulus-driven activity backward across t=0.
        smooth[:,:1000]=gaussian_filter1d(raw[:,:1000],SIGMA/WIDTH,axis=1,mode='reflect')
        smooth[:,1000:]=gaussian_filter1d(raw[:,1000:],SIGMA/WIDTH,axis=1,mode='reflect')
        mean=smooth.mean(axis=0);sem=smooth.std(axis=0,ddof=1)/np.sqrt(len(smooth))
        raw_mean=raw.mean(axis=0);raw_sem=raw.std(axis=0,ddof=1)/np.sqrt(len(raw))
        for ax in axes:
            ax.plot(centers,mean,color=colors[construct],lw=1.6,label=f'{construct} ({len(raw)} units)')
            ax.fill_between(centers,np.maximum(0,mean-sem),mean+sem,color=colors[construct],alpha=.20,linewidth=0)
        for i,t in enumerate(centers):
            results.append(dict(construct=construct,time_s=t,bin_start_s=edges[i],bin_end_s=edges[i+1],
                unit_count=len(raw),raw_mean_hz=raw_mean[i],raw_sem_hz=raw_sem[i],
                smoothed_mean_hz=mean[i],smoothed_sem_hz=sem[i]))
        print(construct,'units',len(raw),'raw bins',len(centers),'smoothed peak',float(mean.max()),flush=True)
    for ax in axes:
        ax.axvspan(0,.041,color='#bbbbbb',alpha=.35,zorder=0)
        ax.axvline(0,color='black',lw=1,ls='--')
        ax.spines[['top','right']].set_visible(False)
        ax.set_xlabel('Time from first e-stim pulse (s)',fontsize=11)
        ax.set_ylabel('Firing rate (Hz/unit)',fontsize=11)
        ax.set_ylim(bottom=0)
    axes[0].set_xlim(-.5,1)
    axes[0].set_title('Onset detail: −0.5 to +1 s',fontsize=12)
    axes[1].set_xlim(-5,10)
    axes[1].set_yscale('symlog',linthresh=10,linscale=1,base=10)
    axes[1].set_title('Overview: −5 to +10 s',fontsize=12)
    axes[1].set_ylabel('Firing rate (Hz/unit; linear 0–10, log above)',fontsize=10)
    axes[1].legend(frameon=False,fontsize=8,loc='upper right')
    fig.suptitle('Actuators + effectors: high-resolution e-stim PSTHs',fontsize=15)
    fig.text(.5,.025,'10-ms bins (50× finer than previous plot); Gaussian σ = 20 ms; lines = unit mean, bands = unit SEM.\n'
             'Smoothing is applied separately before/after t0. Gray = actual ~41-ms pulse-train span. SUA/MUA pooled.\n'
             'Overview uses a linear/log y scale to show baseline and peak together. Stimulation artifacts remain included.',
             ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.15,1,.94))
    destination=OUT/'estim_high_resolution_psth_10ms.png'
    fig.savefig(destination,dpi=300);plt.close(fig)
    with gzip.open(OUT/'estim_high_resolution_psth_10ms.csv.gz','wt',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
    report=dict(observation='one unit',units=len(meta),scope='Actuators + effectors',pool_sua_mua=True,
        bin_width_s=WIDTH,computed_window_s=[-10,10],onset_view_s=[-.5,1],overview_s=[-5,10],
        smoothing=dict(method='Gaussian',sigma_s=SIGMA,each_unit_before_aggregation=True,
                       pre_post_separate=True,boundary_mode='reflect'),
        band='unit SD / sqrt(n), ddof=1, after smoothing',
        y_scale={'onset':'linear','overview':'symlog, linear 0-10 Hz, logarithmic above 10 Hz'},
        pixel_dpi=300,baseline_subtraction=False,artifact_blanking=False,recordings=sources)
    (OUT/'estim_high_resolution_psth_10ms_provenance.json').write_text(json.dumps(report,indent=2))
    print('COMPLETE',destination,destination.stat().st_size,flush=True)

if __name__=='__main__':
    main()
