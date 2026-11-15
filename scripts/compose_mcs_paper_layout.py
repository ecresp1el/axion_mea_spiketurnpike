"""Match the condition-wise organization of reference Fig. 3 d–o, using saved data."""
from pathlib import Path
import hashlib
import json
import warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import to_rgb
from matplotlib.patches import Ellipse
from scipy.stats import ttest_ind
from load_mcs_locked_lda import load_units,project_units

ROOT=Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis')
SOURCE=ROOT/'temporal_signatures'
OUT=SOURCE/'paper_layout'
GROUPS=['Control','DREADD','LMO','PSAM']
GROUP_COLORS=['#777777','#e94b47','#64af54','#9462d5']
FEATURE_COLORS=['#e28b35','#d5ad28','#d75a55','#4d94b7','#9462c6','#4a9d8f']
SHORT=['Rate change','Fast bursts','Burst duration','Firing rate','Burst delay','Burst pause']

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def unit_spread_outline(ax,values,color,lw=1.0):
    covariance=np.cov(np.asarray(values).T,ddof=1)
    eigenvalues,eigenvectors=np.linalg.eigh(covariance)
    order=np.argsort(eigenvalues)[::-1];eigenvalues=eigenvalues[order];eigenvectors=eigenvectors[:,order]
    width,height=4*np.sqrt(np.maximum(eigenvalues,0))
    angle=np.degrees(np.arctan2(eigenvectors[1,0],eigenvectors[0,0]))
    patch=Ellipse(np.mean(values,axis=0),width,height,angle=angle,facecolor='none',edgecolor=color,lw=lw,alpha=.85,zorder=2)
    ax.add_patch(patch)
    return dict(LD1=float(np.mean(values,axis=0)[0]),LD2=float(np.mean(values,axis=0)[1]),
                width=float(width),height=float(height),angle_degrees=float(angle),n_units=len(values))

def holm(p):
    order=np.argsort(p);out=np.empty(len(p));out[order]=np.minimum(1,np.maximum.accumulate(np.asarray(p)[order]*np.arange(len(p),0,-1)))
    return out

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    data=np.load(SOURCE/'unit_window_metrics.npz',allow_pickle=False)
    x=data['values'];time=(data['bin_edges_s'][:-1]+data['bin_edges_s'][1:])/2
    groups=data['construct'];names=data['feature_names'];y=np.array([GROUPS.index(g) for g in groups])
    baseline=x[:,time<0,:].reshape(-1,6)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        mean=np.nanmean(baseline,axis=0);sd=np.nanstd(baseline,axis=0,ddof=1)
        values=(x-mean)/sd
        summary=np.nanmean(values[:,(time>0)&(time<5)],axis=1)
    assert np.isfinite(sd).all() and np.all(sd>0)
    means=np.full((4,20,6),np.nan);sems=np.full_like(means,np.nan)
    for c in range(4):
        v=values[y==c]
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            means[c]=np.nanmean(v,axis=0)
            sems[c]=np.nanstd(v,axis=0,ddof=1)/np.sqrt(np.isfinite(v).sum(axis=0))
    tests=[]
    for c in range(1,4):
        for f in range(6):
            a=summary[y==c,f];b=summary[y==0,f];a=a[np.isfinite(a)];b=b[np.isfinite(b)]
            pooled=np.sqrt(((len(a)-1)*np.var(a,ddof=1)+(len(b)-1)*np.var(b,ddof=1))/(len(a)+len(b)-2))
            tests.append(dict(construct=GROUPS[c],metric=str(names[f]),feature_index=f,n_group=len(a),n_control=len(b),
                              mean_difference=a.mean()-b.mean(),cohen_d=(a.mean()-b.mean())/pooled,
                              welch_p=float(ttest_ind(a,b,equal_var=False).pvalue)))
    for row,p in zip(tests,holm([r['welch_p'] for r in tests])):row['holm_p']=float(p)
    pd.DataFrame(tests).to_csv(OUT/'post_0_5_control_comparisons.csv',index=False)
    keys=pd.DataFrame({'recording_id':data['recording_id'],'unit_id':data['unit_id'],'construct':groups})
    for f,name in enumerate(names):keys[str(name)+'_post_0_5_baseline_scaled']=summary[:,f]
    keys.to_csv(OUT/'unit_post_0_5_summary.csv',index=False)
    curves=pd.DataFrame([dict(construct=g,time_s=time[t],metric=str(names[f]),
                             mean=means[c,t,f],ci95_low=means[c,t,f]-1.96*sems[c,t,f],
                             ci95_high=means[c,t,f]+1.96*sems[c,t,f])
                          for c,g in enumerate(GROUPS) for t in range(20) for f in range(6)])
    curves.to_csv(OUT/'standardized_time_courses.csv',index=False)
    fine_path=OUT/'fine_display_time_courses.csv'
    fine=pd.read_csv(fine_path) if fine_path.exists() else None
    decoder_source=OUT/'balanced_decoder'
    decoder_info=json.loads((decoder_source/'summary.json').read_text())
    assert decoder_info['priors']==[.25]*4
    temporal=pd.read_csv(decoder_source/'time_resolved_decoding.csv')
    shuffled=pd.read_csv(decoder_source/'panel_j_observed_and_shuffled.csv')
    assert np.allclose(shuffled['observed_macro_auroc'],temporal['macro_auroc'],atol=1e-12)
    confusion=pd.read_csv(decoder_source/'poststim_confusion_matrix.csv',index_col=0).to_numpy()
    cross=pd.read_csv(decoder_source/'cross_time_macro_auroc.csv',index_col=0).to_numpy()
    meta,raw=load_units();coords,_=project_units(raw)
    assert np.array_equal(meta['unit_id'].to_numpy(str),data['unit_id'])
    assert np.array_equal(meta['recording_id'].to_numpy(str),data['recording_id'])
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':9,
                         'axes.linewidth':.8,'xtick.labelsize':7,'ytick.labelsize':7,
                         'pdf.fonttype':42})
    fig=plt.figure(figsize=(12.8,9.6))
    grid=fig.add_gridspec(3,2,left=.085,right=.965,bottom=.16,top=.84,wspace=.24,hspace=.65,
                          height_ratios=[1,1,1.05])
    rng=np.random.default_rng(42)
    # Shared physical normalization and shared time-course limits across all conditions.
    low=float(fine['ci95_low'].min()) if fine is not None else float(np.nanmin(means-1.96*sems))
    high=float(fine['ci95_high'].max()) if fine is not None else float(np.nanmax(means+1.96*sems))
    span=high-low;limits=(low-.06*span,high+.10*span)
    if fine is not None:limits=(low-.10*max(1,abs(low)),high+.10*max(1,abs(high)))
    for c,g in enumerate(GROUPS):
        sub=grid[c//2,c%2].subgridspec(1,2,width_ratios=[2.45,1.1],wspace=.30)
        trace=fig.add_subplot(sub[0]);dots=fig.add_subplot(sub[1])
        box=grid[c//2,c%2].get_position(fig)
        fig.patches.append(plt.Rectangle((box.x0,box.y1+.032),box.width,.022,
                          transform=fig.transFigure,facecolor=GROUP_COLORS[c],alpha=.17,edgecolor='none'))
        fig.text((box.x0+box.x1)/2,box.y1+.043,g,ha='center',va='center',fontsize=10)
        trace.axvspan(0,5,color='#cccccc',alpha=.65,lw=0,zorder=0)
        trace.axvline(0,color='#555555',ls=(0,(3,3)),lw=.8)
        for f,color in enumerate(FEATURE_COLORS):
            if fine is not None:
                selected=fine[(fine['construct']==g)&(fine['feature_index']==f)]
                for side in [selected['time_s']<0,selected['time_s']>0]:
                    v=selected[side]
                    trace.plot(v['time_s'].to_numpy(),v['mean'].to_numpy(),color=color,lw=1.1)
                    trace.fill_between(v['time_s'].to_numpy(),v['ci95_low'].to_numpy(),v['ci95_high'].to_numpy(),
                                       color=color,alpha=.15,lw=0)
            else:
                trace.plot(time,means[c,:,f],color=color,lw=1.1)
                trace.fill_between(time,means[c,:,f]-1.96*sems[c,:,f],means[c,:,f]+1.96*sems[c,:,f],
                                   color=color,alpha=.15,lw=0)
            v=summary[y==c,f];v=v[np.isfinite(v)]
            dots.scatter(f+rng.uniform(-.17,.17,len(v)),v,s=3,color=color,alpha=.23,lw=0,rasterized=True)
            avg=v.mean();ci=1.96*v.std(ddof=1)/np.sqrt(len(v))
            dots.errorbar(f,avg,yerr=ci,fmt='_',ms=10,color='#222222',lw=.8,zorder=4)
            if c:
                p=next(r['holm_p'] for r in tests if r['construct']==g and r['feature_index']==f)
                star='***' if p<.001 else '**' if p<.01 else '*' if p<.05 else 'ns'
                dots.text(f,1.01,star,transform=dots.get_xaxis_transform(),ha='center',fontsize=6)
        trace.set(xlim=(-10,10),ylim=limits,xticks=[-10,0,10],xlabel='Time from e-stim (s)',
                  ylabel='Activity (baseline SD)')
        if fine is not None:trace.set_yscale('symlog',linthresh=2,linscale=1)
        dots.set_xticks(range(6),['Δ rate','Bursts','Duration','Rate','Delay','Pause'],rotation=65,ha='right',fontsize=6)
        dots.set(xlim=(-.6,5.6),ylabel='0–5 s activity\n(baseline SD)')
        dots.axhline(0,color='#dddddd',lw=.6,zorder=0)
        for ax,letter in [(trace,chr(97+2*c)),(dots,chr(98+2*c))]:
            ax.spines[['top','right']].set_visible(False)
            ax.text(-.18,1.06,letter,transform=ax.transAxes,fontweight='bold',fontsize=12)
    bottom=grid[2,:].subgridspec(1,4,wspace=.65)
    axes=[fig.add_subplot(bottom[i]) for i in range(4)]
    centroid_rows=[]
    unit_coordinates=meta[['recording_id','unit_id','construct']].copy()
    unit_coordinates['LD1'],unit_coordinates['LD2']=coords.T
    for c,g in enumerate(GROUPS):
        v=coords[y==c];axes[0].scatter(*v.T,s=3,color=GROUP_COLORS[c],alpha=.3,lw=0,rasterized=True)
        unit_spread_outline(axes[0],v,GROUP_COLORS[c],lw=.9)
        group_units=unit_coordinates[unit_coordinates['construct']==g]
        for rid,record in group_units.groupby('recording_id',sort=False):
            center=record[['LD1','LD2']].mean().to_numpy()
            axes[0].scatter(*center,marker='o',s=35,facecolor=GROUP_COLORS[c],edgecolor='none',lw=0,zorder=4)
            centroid_rows.append(dict(recording_id=rid,construct=g,n_units=len(record),LD1=center[0],LD2=center[1]))
        dark=np.array(to_rgb(GROUP_COLORS[c]))*.55
        axes[0].scatter(*v.mean(axis=0),marker='o',s=70,color=dark,edgecolor='#111111',lw=1.3,zorder=5)
    assert len(centroid_rows)==meta['recording_id'].nunique()==29
    pd.DataFrame(centroid_rows).to_csv(OUT/'recording_lda_centroids.csv',index=False)
    unit_coordinates.to_csv(OUT/'unit_lda_coordinates.csv',index=False)
    axes[0].set(xlabel='LD1',ylabel='LD2',title='Locked LDA space')
    axes[0].legend(handles=[Line2D([],[],marker='.',ls='none',color='#888888',markersize=3,label='Unit'),
                 Line2D([],[],marker='o',ls='none',markerfacecolor='#777777',markeredgecolor='#777777',markersize=4,label='Recording centroid'),
                 Line2D([],[],marker='o',ls='none',markerfacecolor='#333333',markeredgecolor='black',markersize=5,label='Group centroid')],
                 loc='upper left',frameon=False,fontsize=5.2,handletextpad=.3,labelspacing=.25)
    axes[1].axvspan(0,5,color='#dddddd',alpha=.5,lw=0)
    jt=shuffled['time_s'].to_numpy()
    axes[1].fill_between(jt,shuffled['null_percentile025'].to_numpy(),shuffled['null_percentile975'].to_numpy(),
                         color='#bbbbbb',alpha=.45,lw=0,zorder=1)
    axes[1].plot(jt,shuffled['null_mean'],color='#888888',lw=1,label='Shuffled',zorder=2)
    axes[1].fill_between(jt,shuffled['observed_ci95_low'].to_numpy(),shuffled['observed_ci95_high'].to_numpy(),
                         color='#b9776a',alpha=.30,lw=0,zorder=3)
    axes[1].plot(jt,shuffled['observed_macro_auroc'],color='#8b473e',lw=1.7,label='AUROC',zorder=4)
    axes[1].axvline(0,color='#777777',ls='--',lw=.8)
    axes[1].set(xlabel='Time from e-stim (s)',ylabel='Macro AUROC',ylim=(.4,1),title='Time-resolved decoding')
    axes[1].legend(frameon=False,fontsize=6,loc='upper right')
    cm=axes[2].imshow(confusion,cmap='Greys',vmin=0,vmax=1)
    for a in range(4):
        for b in range(4):axes[2].text(b,a,f'{confusion[a,b]:.2f}',ha='center',va='center',fontsize=6,
                                     color='white' if confusion[a,b]>.5 else 'black')
    axes[2].set_xticks(range(4),GROUPS,rotation=55,ha='right',fontsize=6)
    axes[2].set_yticks(range(4),GROUPS,fontsize=6)
    axes[2].set(xlabel='Predicted group',ylabel='Actual group',title='Decoding confusion')
    image=axes[3].imshow(cross,origin='lower',aspect='auto',extent=[-10,10,-10,10],
                         cmap='inferno',vmin=.5,vmax=1)
    axes[3].axhline(0,color='white',ls='--',lw=.5);axes[3].axvline(0,color='white',ls='--',lw=.5)
    axes[3].set(xlabel='Test time (s)',ylabel='Train time (s)',title='Cross-time decoding')
    fig.colorbar(image,ax=axes[3],fraction=.055,pad=.04).ax.tick_params(labelsize=6)
    for i,ax in enumerate(axes):
        ax.text(-.20,1.12,chr(105+i),transform=ax.transAxes,fontweight='bold',fontsize=12)
        if i<2:ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Actuators + effectors',fontsize=14,y=.98)
    handles=[plt.Line2D([0],[0],color=c,lw=2,label=n) for c,n in zip(FEATURE_COLORS,SHORT)]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.52,.95),ncol=6,frameon=False,fontsize=8,
               handlelength=1.2,columnspacing=1.3)
    fig.text(.52,.035,'Traces: unit means ± pointwise 95% intervals. Gray window: 0–5 s summary. Each dot = one unit.\n'
             'Shared normalization: pooled pre-stim mean and SD for each measurement. Stars: Welch versus Control, Holm across 18 tests.\n'
             'Display smoothing: Gaussian σ = 300 ms, applied per unit separately before/after stimulation. Trace axes: linear ±2 SD, log outside.\n'
             'J: observed 95% unit-bootstrap interval; shuffled 95% permutation range from 1,000 unit-label shuffles with refits.\n'
             'Locked LDA: 215 metrics. Temporal decoder: six features, equal class priors, held-out units. Artifacts included.',
             ha='center',fontsize=6.5,linespacing=1.25)
    for suffix in ['png','pdf']:fig.savefig(OUT/f'condition_signatures_paper_layout.{suffix}',dpi=350,facecolor='white')
    plt.close(fig)
    sources=[SOURCE/'unit_window_metrics.npz']+[decoder_source/n for n in ['time_resolved_decoding.csv',
                                'poststim_confusion_matrix.csv','cross_time_macro_auroc.csv','summary.json',
                                'panel_j_observed_and_shuffled.csv','panel_j_null_methods.json']]
    if fine is not None:sources += [fine_path,Path(__file__).with_name('refine_mcs_paper_traces.py')]
    manifest=dict(reference='https://pmc.ncbi.nlm.nih.gov/articles/PMC13232143/#F3',
                  reference_panels='Adapted Fig. 3 d–o: paired condition traces/summaries and decoding row',
                  composition_retrains_decoder=False,temporal_decoder_refit_for_equal_priors=True,
                  locked_model_modified=False,
                  temporal_decoder_source=str(decoder_source),temporal_decoder_priors=[.25]*4,
                  display_smoothing_sigma_s=.3,
                  lda_markers=dict(unit='Small colored dot',recording='Solid colored circle, mean of that recording’s unit coordinates',
                                   group='Large dark filled circle, unit-weighted group mean',unique_recordings=29,
                                   outlines='Two-SD covariance contours of unit spread, not confidence intervals'),
                  normalization_mean=mean.tolist(),normalization_sd=sd.tolist(),
                  fine_display=fine is not None,
                  statistics='Welch tests of one 0–5 s mean per unit; Holm adjustment across 18 comparisons',
                  intervals='Pointwise normal approximation: mean ± 1.96 SEM; unit-level, not recording-level',
                  sources={str(p):sha(p) for p in sources+[Path(__file__)]})
    output_names=['condition_signatures_paper_layout.png','condition_signatures_paper_layout.pdf',
                  'post_0_5_control_comparisons.csv','unit_post_0_5_summary.csv','standardized_time_courses.csv',
                  'recording_lda_centroids.csv','unit_lda_coordinates.csv']
    manifest['outputs']={name:sha(OUT/name) for name in output_names}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('COMPLETE',OUT,flush=True)

if __name__=='__main__':main()
