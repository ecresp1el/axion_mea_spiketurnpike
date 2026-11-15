"""Compact ordered 100-ms unit spike counts around the first STG train."""
from pathlib import Path
import csv,json,hashlib
import numpy as np
from load_mcs_locked_lda import load_units,CONFIG

REPO=Path(__file__).resolve().parents[1]
OUT=Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/trajectory_decoder')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    meta,_=load_units();meta=meta.reset_index(drop=True)
    records={r['recording_id']:r for r in csv.DictReader((REPO/'metadata/mcs_recording_biology.csv').open())}
    counts=np.zeros((len(meta),200),dtype=np.int32);sources=[]
    for rid,units in meta.groupby('recording_id',sort=False):
        record=records[rid];files=list((Path(record['sorting_output_path'])/'curated').glob('*/numpysorting_info.json'))
        assert len(files)==1
        info=json.loads(files[0].read_text());fs=float(info['sampling_frequency']);onset=float(units['event_time_s'].iloc[0]);center=onset*fs
        if abs(center-round(center))<1e-7:center=float(round(center))
        assert onset>=10 and onset+10<=float(record['duration_s'])
        spikes=np.load(files[0].parent/'spikes.npy',mmap_mode='r')
        lo,hi=np.searchsorted(spikes['sample_index'],[center-10*fs-1e-7,center+10*fs-1e-7]);window=spikes[lo:hi]
        rel=window['sample_index']-center;lookup={str(uid):i for i,uid in enumerate(info['unit_ids'])}
        for i,row in units.iterrows():
            samples=rel[window['unit_index']==lookup[row['unit_id']]]
            bins=np.floor((samples/fs+10)/.1+1e-8).astype(int);valid=(bins>=0)&(bins<200)
            counts[i]=np.bincount(bins[valid],minlength=200)
        sources.append(dict(recording_id=rid,sorting=str(files[0].parent),onset_s=onset,units=len(units)))
    # Check against the previously plotted five-second firing rates for every unit.
    saved={(r['recording_id'],r['unit_id']):r for r in csv.DictReader((OUT.parent/'poststim_publication/selected_unit_pre_post.csv').open())}
    for i,row in meta.iterrows():
        original=saved[(row['recording_id'],row['unit_id'])]
        assert abs(counts[i,100:150].sum()/5-float(original['firing_rate_post']))<1e-10
        assert abs(counts[i,50:100].sum()/5-float(original['firing_rate_pre']))<1e-10
    dest=OUT/'unit_100ms_spike_counts.npz'
    np.savez_compressed(dest,counts=counts,bin_edges_s=np.linspace(-10,10,201),
                        recording_id=meta['recording_id'].to_numpy(str),unit_id=meta['unit_id'].to_numpy(str),
                        construct=meta['construct'].to_numpy(str))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    manifest=dict(units=len(meta),bin_s=.1,window_s=[-10,10],half_open=True,
                  verified_five_second_rates_against_prior_tables=True,recordings=sources,
                  sources={str(p):sha(p) for p in [CONFIG,Path(__file__)]},
                  output_sha256=sha(dest))
    (OUT/'extraction_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('COMPLETE ordered counts',counts.shape,flush=True)

if __name__=='__main__':main()
