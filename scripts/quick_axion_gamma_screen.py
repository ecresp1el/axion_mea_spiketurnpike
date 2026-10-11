#!/usr/bin/env python3
"""Exploratory well-median gamma screen of preserved short-window Axion PSDs.

This is a descriptive background-adjusted peak screen, not a significance test,
not specparam/FOOOF, and not a classifier of neuronal oscillations.
"""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks, peak_widths

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'audit-output/axion_lfp_consolidated_20260917'
OUT = ROOT/'audit-output/axion_gamma_quick_screen_20260917'


def load_csv(name):
    with (SOURCE/name).open(newline='') as f:
        return list(csv.DictReader(f))


def background(frequency, power):
    """Robust log-log line; 10–200Hz with mains/harmonic neighborhoods excluded."""
    db = 10*np.log10(np.maximum(power,1e-20))
    smooth = gaussian_filter1d(db,2)  # sigma=1Hz at the stored0.5Hz spacing
    keep = (frequency>=10)&(frequency<=200)
    for hz in (60,120,180):
        keep &= abs(frequency-hz)>3
    design = np.column_stack([np.ones(keep.sum()),np.log10(frequency[keep])])
    y = smooth[keep]
    beta = np.linalg.lstsq(design,y,rcond=None)[0]
    for _ in range(12):
        residual = y-design@beta
        scale = max(.3,1.4826*np.median(abs(residual-np.median(residual))))
        weight = np.minimum(1,1.5*scale/np.maximum(abs(residual),1e-9))
        beta = np.linalg.lstsq(design*np.sqrt(weight[:,None]),y*np.sqrt(weight),rcond=None)[0]
    baseline = beta[0]+beta[1]*np.log10(np.maximum(frequency,.1))
    return db,smooth-baseline,baseline


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    records = load_csv('lfp_selected_recordings.csv')
    labels = {(w['raw_path'],w['well']):w for w in load_csv('lfp_selected_wells.csv')}
    rows, curves = [], {}
    for rec in records:
        if float(rec['duration_s'])<30:
            continue
        folder = ROOT/rec['signal_qc_artifact_dir']
        z = np.load(folder/'sampled_psd.npz')
        f, ps = z['frequency_hz'],z['median_psd_uv2_per_hz']
        cm = json.loads(str(z['channel_map_json']))
        number = int(folder.name.rsplit('_',1)[1])
        for well in sorted({c['well'] for c in cm}):
            meta = labels[(rec['raw_path'],well)]
            ix = [i for i,c in enumerate(cm) if c['well']==well]
            power = np.median(ps[:,ix],axis=1)
            db,residual,baseline = background(f,power)
            peaks,_ = find_peaks(residual,prominence=1)
            candidate = [i for i in peaks if 30<=f[i]<=80 and abs(f[i]-60)>5 and residual[i]>=2]
            candidate.sort(key=lambda i:residual[i],reverse=True)
            k = candidate[0] if candidate else None
            raw_peaks,_ = find_peaks(power)
            nearby = [j for j in raw_peaks if k is not None and abs(f[j]-f[k])<=2]
            j = max(nearby,key=lambda j:power[j]) if nearby else None
            width = float(peak_widths(power,[j])[0][0]*(f[1]-f[0])) if j is not None else None
            if rec['collection']=='dorsal_ventral_2026':
                group = meta['curated_identity']
            elif meta['curated_identity']=='empty':
                group = 'empty'
            elif not meta['stored_label']:
                group = 'unlabeled_fusion_recording'
            else:
                group = 'old_fusion' if rec['collection']=='fusion_2024' else 'new_fusion'
            # Integrate two disjoint segments; do not bridge the excluded60Hz band.
            band_power = 0.
            for a,b in [(30,55),(65,80)]:
                mask = (f>=a)&(f<=b)
                band_power += np.trapezoid(power[mask],f[mask])
            rows.append(dict(recording_id=rec['recording_id'],qc_recording_number=number,
                             filename=rec['filename'],raw_path=rec['raw_path'],recorded_at=rec['recorded_at'],
                             well=well,group=group,stored_label=meta['stored_label'],
                             identity_basis=meta['assignment_basis'],
                             candidate_peak_ge_2db=bool(candidate),
                             candidate_peak_ge_3db=bool(k is not None and residual[k]>=3),
                             strongest_candidate_hz=float(f[k]) if k is not None else '',
                             smoothed_peak_above_background_db=float(residual[k]) if k is not None else '',
                             unsmoothed_peak_hz=float(f[j]) if j is not None else '',
                             unsmoothed_peak_fwhm_hz=width if width is not None else '',
                             gamma_power_excluding_55_65hz_uv2=float(band_power)))
            curves[(number,well)] = (f,power,residual,baseline,group)
    with (OUT/'well_gamma_screen.csv').open('w',newline='') as h:
        w = csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary = {}
    for group in sorted({r['group'] for r in rows}):
        rr = [r for r in rows if r['group']==group]
        summary[group] = dict(well_recording_observations=len(rr),recordings=len({r['recording_id'] for r in rr}),
                              peaks_ge_2db=sum(r['candidate_peak_ge_2db'] for r in rr),
                              peaks_ge_3db=sum(r['candidate_peak_ge_3db'] for r in rr),
                              median_gamma_power_excluding_55_65hz_uv2=float(np.median([r['gamma_power_excluding_55_65hz_uv2'] for r in rr])))
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    fig,axs = plt.subplots(2,2,figsize=(12,8))
    for group,color in [('new_fusion','#bd4932'),('dorsal','#246aa6'),('empty','#6a6a6a')]:
        selected = [c for c in curves.values() if c[4]==group]
        y = np.array([c[1] for c in selected]);r = np.array([c[2] for c in selected]);f = selected[0][0];keep=(f>=20)&(f<=100)
        axs[0,0].semilogy(f[keep],np.median(y,axis=0)[keep],color=color,label=group.replace('_',' '))
        axs[0,1].plot(f[keep],np.median(r,axis=0)[keep],color=color,label=group.replace('_',' '))
    for num,well,label,color in [(1,'A1','Fusion A1, May27','#bd4932'),(1,'B1','EMPTY B1, same recording','#6a6a6a'),(18,'B1','Dorsal B1, May28','#246aa6')]:
        f,power,resid,base,group = curves[(num,well)]
        keep=(f>=25)&(f<=90);axs[1,0].semilogy(f[keep],power[keep],label=label,color=color)
    xlabels=['May27 fusion','Later fusion','Dorsal','May27 empty']
    sets=[[r for r in rows if r['group']=='new_fusion' and r['qc_recording_number']<=4],
          [r for r in rows if r['group']=='new_fusion' and r['qc_recording_number']>5],
          [r for r in rows if r['group']=='dorsal'],
          [r for r in rows if r['group']=='empty' and r['qc_recording_number']<=4]]
    counts=[sum(r['candidate_peak_ge_3db'] for r in rr) for rr in sets]
    axs[1,1].bar(xlabels,[n/len(rr)*100 for n,rr in zip(counts,sets)],color=['#bd4932','#dca196','#246aa6','#6a6a6a'])
    for i,(n,rr) in enumerate(zip(counts,sets)):
        axs[1,1].text(i,100*n/len(rr)+3,f'{n}/{len(rr)}',ha='center')
    axs[1,1].set_ylim(0,115);axs[1,1].set_ylabel('Well-recording observations with candidate (%)')
    axs[1,1].set_title('Peaks ≥3dB: descriptive screen, not biological n')
    for ax in [axs[0,0],axs[0,1],axs[1,0]]:
        ax.axvspan(55,65,color='gray',alpha=.15);ax.set_xlabel('Frequency (Hz)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    axs[0,0].set_ylabel('PSD (µV²/Hz)');axs[0,0].set_title('Median well spectra across available recordings')
    axs[0,1].set_ylabel('Power above fitted background (dB)');axs[0,1].set_title('Background-adjusted median spectra')
    axs[1,0].set_ylabel('PSD (µV²/Hz)');axs[1,0].set_title('72–73Hz feature is also present in an EMPTY well')
    fig.suptitle('Quick Axion gamma screen: shared narrow peak, not established fusion-specific neuronal gamma\nThree4s windows/recording; 30–80Hz screen excluding55–65Hz; unmatched cohorts',fontsize=11)
    fig.tight_layout(rect=[0,0,1,.94]);fig.savefig(OUT/'gamma_quick_comparison.png',dpi=150);fig.savefig(OUT/'gamma_quick_comparison.pdf');plt.close(fig)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
