"""Reference-style raw-rate mean +/- SEM PSTH; each unit is an observation."""
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from load_mcs_locked_lda import load_units
import explore_mcs_actuator_separation as base

OUT=Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis')

def main():
    metadata,_=load_units()
    records={r['recording_id']:r for r in csv.DictReader((base.REPO/'metadata/mcs_recording_biology.csv').open())}
    edges=np.arange(-10,10.001,.5)
    centers=(edges[:-1]+edges[1:])/2
    rates={c:[] for c in base.CLASSES}
    provenance=[]
    for rid,units in metadata.groupby('recording_id',sort=False):
        record=records[rid]
        files=list((Path(record['sorting_output_path'])/'curated').glob('*/numpysorting_info.json'))
        assert len(files)==1
        info=json.loads(files[0].read_text());assert info['num_segments']==1
        expected={str(uid) for uid in info['unit_ids']}
        assert expected==set(units['unit_id'])
        onset=float(units['event_time_s'].iloc[0])
        assert onset>=10 and onset+10<=float(record['duration_s'])
        fs=float(info['sampling_frequency'])
        spikes=np.load(files[0].parent/'spikes.npy',mmap_mode='r',allow_pickle=False)
        lo,hi=np.searchsorted(spikes['sample_index'],[(onset-10)*fs,(onset+10)*fs])
        window=spikes[lo:hi]
        relative=window['sample_index']/fs-onset
        # Tiny arithmetic rounding tolerance; far below one sampling interval.
        bin_index=np.floor((relative+10)/.5+1e-10).astype(int)
        valid=(bin_index>=0)&(bin_index<len(centers))
        counts=np.zeros((len(info['unit_ids']),len(centers)),dtype=int)
        np.add.at(counts,(window['unit_index'][valid],bin_index[valid]),1)
        assert counts.sum()==int(np.sum(valid))
        construct=record['construct']
        rates[construct].append(counts/.5)
        provenance.append(dict(recording_id=rid,sorting=str(files[0].parent),event_time_s=onset,
                               construct=construct,units=len(counts)))
    fig,ax=plt.subplots(figsize=(8.5,5.5))
    colors={'Control':'#777777','DREADD':'#e94b47','LMO':'#64af54','PSAM':'#9462d5'}
    export=[]
    ax.axvspan(0,5,color='#dddddd',alpha=.6,zorder=0)
    ax.axvline(0,color='black',ls='--',lw=1.3,zorder=1)
    for construct in ['Control','DREADD','LMO','PSAM']:
        data=np.concatenate(rates[construct])
        expected=int(np.sum(metadata['construct']==construct))
        assert len(data)==expected
        mean=data.mean(axis=0)
        sem=data.std(axis=0,ddof=1)/np.sqrt(len(data))
        ax.step(centers,mean,where='mid',color=colors[construct],lw=2,
                label=f'{construct} (n={len(data)} units)')
        ax.fill_between(centers,np.maximum(0,mean-sem),mean+sem,step='mid',
                        color=colors[construct],alpha=.22,linewidth=0)
        for i in range(len(centers)):
            export.append(dict(construct=construct,bin_start_s=edges[i],bin_end_s=edges[i+1],
                               time_s=centers[i],mean_hz=mean[i],sem_hz=sem[i],unit_count=len(data)))
        print(construct,'units',len(data),'peak mean Hz',float(mean.max()),flush=True)
    ax.set_xlim(-10,10);ax.set_ylim(bottom=0)
    ax.set_xlabel('Time from first e-stim train (s)',fontsize=12)
    ax.set_ylabel('Firing rate (Hz/unit)',fontsize=12)
    ax.set_title('Actuators + effectors: e-stim-aligned PSTH',fontsize=14)
    ax.legend(frameon=False,fontsize=9,loc='upper right')
    ax.spines[['top','right']].set_visible(False)
    ax.tick_params(direction='out')
    fig.text(.5,.025,'Lines = mean across units; shaded bands = SEM; 0.5-s bins; SUA/MUA pooled.\n'
             'Gray = 0–5-s response window, not stimulus duration. First pulse train spans approximately 41 ms.\n'
             'Raw firing rates, without baseline subtraction or smoothing; stimulation artifacts remain included.',
             ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.13,1,1))
    destination=OUT/'estim_reference_style_psth.png'
    fig.savefig(destination,dpi=180);plt.close(fig)
    base.write_csv(OUT/'estim_reference_style_psth.csv',export)
    summary=dict(scope='Actuators + effectors',observation='one unit',pool_sua_mua=True,
                 units=len(metadata),window_s=[-10,10],bin_width_s=.5,
                 plotted_value='raw firing rate per unit in Hz',aggregation='arithmetic unit mean',
                 band='unit standard deviation / sqrt(unit count), ddof=1',
                 gray_region='0 to +5 s analysis response window; not stimulus duration',
                 baseline_subtraction=False,smoothing=False,recordings=provenance)
    (OUT/'estim_reference_style_psth_provenance.json').write_text(json.dumps(summary,indent=2))
    print('COMPLETE',destination,destination.stat().st_size,flush=True)

if __name__=='__main__':
    main()
