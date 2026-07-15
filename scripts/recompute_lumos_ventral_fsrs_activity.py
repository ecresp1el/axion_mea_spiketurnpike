#!/usr/bin/env python3
"""Recompute the locked SUA metrics for all Lumos good units + ventral CytoView units."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from axion_mea.spontaneous_activity import BurstDetectionParameters, summarize_unit_activity, summarize_smoothed_inverse_isi_rate

ROOT = Path('/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest')
CYTO = ROOT/'cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_isi2ms_le3pct_exclude2_dorsal_drivers_20260710_082420'
LUMOS = ROOT/'lumos_gui_ready_unsorted_unit_firing_rates_20260709.csv'
LMET = ROOT/'waveform_alignment_feature_audit_20260709'/'waveform_alignment_feature_audit_20260709_paired_unit_metrics.csv'
CMET = ROOT/'waveform_alignment_feature_audit_20260709_cytoview'/'waveform_alignment_feature_audit_20260709_paired_unit_metrics.csv'

def key(df): return df['recording'].astype(str)+'|'+df['well'].astype(str)+'|'+df['unit_id'].astype(str)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output-dir',type=Path,required=True); a=ap.parse_args(); a.output_dir.mkdir(parents=True,exist_ok=True)
    import spikeinterface.full as si
    cy=pd.read_csv(CYTO/'cytoview_dv_sua_spontaneous_activity_20260710_unit_metrics.csv'); cy=cy[(cy.region_call=='ventral') & cy.KSLabel.str.lower().eq('good')].copy(); cy['unit_key']=key(cy); cy['source_platform']='CytoView'; cy['scope_region']='ventral'
    lu=pd.read_csv(LUMOS); lu=lu[lu.KSLabel.str.lower().eq('good')].copy(); lu['unit_key']=key(lu); lu['source_platform']='Lumos'; lu['scope_region']='Lumos'
    lm=pd.read_csv(LMET); lm['unit_key']=key(lm); cm=pd.read_csv(CMET); cm['unit_key']=key(cm)
    lu=lu.merge(lm[['unit_key','analyzer_path','best_channel_index','after_trough_to_peak_duration_ms','after_waveform_asymmetry','after_post_trough_rebound_slope_uV_per_ms','after_rep50_recovery_slope_uV_per_ms']],on='unit_key',how='inner')
    cy=cy.merge(cm[['unit_key','best_channel_index','after_trough_to_peak_duration_ms','after_waveform_asymmetry','after_post_trough_rebound_slope_uV_per_ms','after_rep50_recovery_slope_uV_per_ms']],on='unit_key',how='left')
    src=pd.concat([cy,lu],ignore_index=True,sort=False); src['rs_fs_class']=np.where(pd.to_numeric(src.after_trough_to_peak_duration_ms).le(.5),'FS','RS'); src=src[src.rs_fs_class.isin(['FS','RS'])].copy()
    pars=BurstDetectionParameters(max_isi_ms=100,min_spikes=3,min_duration_ms=100); rows=[]; bursts=[]; errors=[]
    for path,g in src.groupby('analyzer_path'):
        try:
            an=si.load_sorting_analyzer(Path(str(path)),load_extensions=True); sorting=an.sorting; fs=float(an.recording.get_sampling_frequency()); dur=float(an.recording.get_total_duration()); ids={str(x):x for x in sorting.get_unit_ids()}
            for _,r in g.iterrows():
                uid=ids.get(str(int(r.unit_id)) if str(r.unit_id).replace('.0','',1).isdigit() else str(r.unit_id));
                if uid is None: raise ValueError(f'missing unit {r.unit_id}')
                st=np.asarray(sorting.get_unit_spike_train(uid),dtype=np.int64)/fs; sm= summarize_smoothed_inverse_isi_rate(st,dur,gaussian_sigma_ms=50,evaluation_bin_ms=1,min_spikes=30); su,ev=summarize_unit_activity(st,dur,pars)
                base={'unit_key':r.unit_key,'source_platform':r.source_platform,'scope_region':r.scope_region,'recording':r.recording,'well':r.well,'unit_id':r.unit_id,'best_channel_index':r.best_channel_index,'rs_fs_class':r.rs_fs_class,'recording_duration_s':dur,'source_spike_count':len(st),'legacy_firing_rate_hz':len(st)/dur,'template_ptp_uV':r.get('template_ptp_best_channel_uV',r.get('Amplitude',np.nan))}
                rows.append(base|{k:v for k,v in sm.items()}|{k:v for k,v in su.items()})
                bursts.extend([{'unit_key':r.unit_key,'rs_fs_class':r.rs_fs_class,**e.to_dict()} for e in ev])
        except Exception as e: errors.append({'analyzer_path':str(path),'error':str(e)})
    out=pd.DataFrame(rows); out.to_csv(a.output_dir/'lumos_ventral_unit_metrics_recomputed.csv',index=False); pd.DataFrame(bursts).to_csv(a.output_dir/'lumos_ventral_burst_events.csv',index=False); pd.DataFrame(errors).to_csv(a.output_dir/'analysis_errors.csv',index=False)
    metrics=[('legacy_firing_rate_hz','Overall firing rate (Hz)'),('inverse_isi_gaussian_temporal_p99_9_hz','Smoothed inverse-ISI P99.9 (Hz)'),('burst_rate_per_min','Burst rate (bursts/min)'),('mean_firing_rate_within_bursts_hz','MFR within bursts (Hz)'),('mean_burst_duration_ms','Burst duration (ms)'),('mean_interburst_interval_s','Inter-burst interval (s)'),('mean_spikes_per_burst','Spikes per burst')]
    channel_out=out.groupby(['source_platform','recording','best_channel_index','rs_fs_class'],dropna=False)[[m for m,_ in metrics]].mean().reset_index()
    channel_out.to_csv(a.output_dir/'channel_averaged_metrics.csv',index=False)
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    fig,axs=plt.subplots(1,len(metrics),figsize=(21,4.2),constrained_layout=True)
    for ax,(m,label) in zip(axs,metrics):
        vals=[]
        for i,c in enumerate(['FS','RS']):
            v=pd.to_numeric(channel_out.loc[channel_out.rs_fs_class.eq(c),m],errors='coerce').dropna(); vals.append(v)
            rng=np.random.default_rng(10+i); ax.scatter(np.full(len(v),i)+rng.uniform(-.08,.08,len(v)),v,s=12,alpha=.5,color={'FS':'#B8742A','RS':'#58758E'}[c],linewidths=0)
            if len(v): ax.errorbar(i,v.mean(),yerr=v.sem() if len(v)>1 else 0,fmt='o',color='#222',capsize=3,lw=1.2)
        ax.set_xticks([0,1],['FS','RS']); ax.set_title(label,fontsize=9); ax.spines[['top','right']].set_visible(False); ax.tick_params(labelsize=7)
    fig.savefig(a.output_dir/'lumos_ventral_fs_vs_rs_activity.png',dpi=600); fig.savefig(a.output_dir/'lumos_ventral_fs_vs_rs_activity.svg'); print(f'Recomputed {len(out)} units; FS={sum(out.rs_fs_class=="FS")}, RS={sum(out.rs_fs_class=="RS")}'); print(a.output_dir)
if __name__=='__main__': main()
