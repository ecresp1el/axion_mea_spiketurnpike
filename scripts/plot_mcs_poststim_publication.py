"""Optimized post-stim phenotypes and paired pre/post changes, per unit."""
import csv
import json
import sys
import warnings
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.transforms import blended_transform_factory
import numpy as np
from scipy.stats import ttest_1samp,wilcoxon
import explore_mcs_actuator_separation as base
import plot_mcs_baseline_publication as prepub

OUT=Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/poststim_publication')
CLASSES=base.CLASSES
METRICS=prepub.METRICS
WINDOWS=[(w,o) for w in [.25,.5,1.,2.,5.,10.] for o in [0.,.05,.1,.25,.5,1.,2.,5.] if w+o<=10]
TITLES=['Firing rate','Spikes in bursts\nISI ≤25 ms; ≥3 spikes','Active 1-s bins',
        'Short intervals\nISI <50 ms','Long pauses\nISI >200 ms']
UNITS=['Firing rate (Hz/unit)','Spikes in bursts (% of spikes)','Active bins (% of 1-s bins)','Short ISIs (% of intervals)','Long ISIs (% of intervals)']
N_PERM=999

def measures(relative_samples,a,b,fs):
    s=relative_samples[(relative_samples>=a*fs-1e-7)&(relative_samples<b*fs-1e-7)]
    isi=np.diff(s)/fs;result=np.full(5,np.nan)
    result[0]=len(s)/(b-a)
    if len(s):
        cuts=np.flatnonzero(isi>.025+1e-12)+1;sizes=np.diff(np.r_[0,cuts,len(s)])
        result[1]=np.sum(sizes[sizes>=3])/len(s)
    else:result[1]=0.
    if b-a>=1:
        bins=int(round(b-a));index=np.floor((s-a*fs)/fs+1e-7).astype(int)
        counts=np.bincount(index[(index>=0)&(index<bins)],minlength=bins)
        result[2]=np.mean(counts>0)
    if len(isi):
        result[3]=np.mean(isi<.05-1e-12)
        result[4]=np.mean(isi>.2+1e-12)
    return result

def optimum(data,y):
    d=prepub.effects(data,y);valid=np.all(np.isfinite(d),axis=0)
    score=np.full(len(WINDOWS),-np.inf);score[valid]=np.min(np.abs(d[:,valid]),axis=0)
    best=max(np.where(valid)[0],key=lambda j:(score[j],WINDOWS[j][0],-WINDOWS[j][1]))
    return int(best),float(score[best])

def extract(rows):
    records={r['recording_id']:r for r in csv.DictReader((base.REPO/'metadata/mcs_recording_biology.csv').open())}
    before=np.full((5,len(rows),len(WINDOWS)),np.nan);after=np.full_like(before,np.nan)
    groups={}
    for i,r in enumerate(rows):groups.setdefault(r['recording_id'],[]).append((i,r))
    for rid,units in groups.items():
        record=records[rid];files=list((Path(record['sorting_output_path'])/'curated').glob('*/numpysorting_info.json'));assert len(files)==1
        info=json.loads(files[0].read_text());assert info['num_segments']==1
        fs=float(info['sampling_frequency']);onset=float(units[0][1]['event_time_s']);center=onset*fs
        if abs(center-round(center))<1e-7:center=float(round(center))
        assert onset>=10 and onset+10<=float(record['duration_s'])
        spikes=np.load(files[0].parent/'spikes.npy',mmap_mode='r')
        lo,hi=np.searchsorted(spikes['sample_index'],[center-10*fs-1e-7,center+10*fs-1e-7])
        window=spikes[lo:hi];relative=window['sample_index']-center
        lookup={str(uid):i for i,uid in enumerate(info['unit_ids'])}
        for i,r in units:
            samples=relative[window['unit_index']==lookup[r['unit_id']]]
            for j,(width,offset) in enumerate(WINDOWS):
                before[:,i,j]=measures(samples,-offset-width,-offset,fs)
                after[:,i,j]=measures(samples,offset,offset+width,fs)
        print('Post/pre extracted',rid,flush=True)
    change=after-before
    np.savez_compressed(OUT/'pre_post_all_windows.npz',before=before,after=after,change=change,windows=np.array(WINDOWS),
        metric_names=np.array(METRICS),recording_id=np.array([r['recording_id'] for r in rows]),
        unit_id=np.array([r['unit_id'] for r in rows]),construct=np.array([r['construct'] for r in rows]))
    return before,after,change

def one_sample_p(v):
    v=v[np.isfinite(v)]
    if len(v)<2:return 1.,1.
    with warnings.catch_warnings():
        warnings.simplefilter('ignore');p=float(ttest_1samp(v,0).pvalue)
        q=float(wilcoxon(v,alternative='two-sided',zero_method='wilcox',method='auto').pvalue) if np.any(v!=0) else 1.
    return (p if np.isfinite(p) else 1.),(q if np.isfinite(q) else 1.)

def summarize(v):
    v=v[np.isfinite(v)]
    return dict(n=len(v),mean=float(v.mean()) if len(v) else np.nan,
                sem=float(v.std(ddof=1)/np.sqrt(len(v))) if len(v)>1 else np.nan)

def draw_metric_panels(axes,y,selected,after,change,stats):
    rng=np.random.default_rng(42)
    for m in range(5):
        j=selected[m]['window_index'];factor=1 if m==0 else 100
        for row,(mode,data) in enumerate([('post',after),('change',change)]):
            ax=axes[row,m];counts=[]
            for c,label in enumerate(CLASSES):
                v=data[m,y==c,j];v=v[np.isfinite(v)]*factor;counts.append(len(v))
                if len(v):
                    ax.scatter(c+rng.uniform(-.17,.17,len(v)),v,color=prepub.COLORS[c],s=4,alpha=.20,linewidths=0,rasterized=True)
                    ax.errorbar(c,v.mean(),yerr=v.std(ddof=1)/np.sqrt(len(v)) if len(v)>1 else None,
                        fmt='o',color='black',markersize=4,capsize=3,markeredgecolor='white',markeredgewidth=.5,zorder=3)
            if m==0:
                ax.set_yscale('symlog',linthresh=1)
                ax.set_ylabel('Post rate (Hz/unit; symlog)' if row==0 else 'Δ rate (Hz/unit; symlog)',fontsize=8)
                if row==0:ax.set_ylim(bottom=0)
            else:
                ax.set_ylabel(UNITS[m] if row==0 else 'Post − paired pre (percentage points)',fontsize=8)
                ax.set_ylim((-4,104) if row==0 else (-104,104))
            ax.axhline(0,color='#aaaaaa',lw=.5)
            ax.set_xticks(range(4),[f'{c}\nn={n}' + (f'/{np.sum(y==i)}' if m>=3 else '')
                for i,(c,n) in enumerate(zip(CLASSES,counts))],fontsize=7,rotation=35)
            ax.spines[['top','right']].set_visible(False)
            trans=blended_transform_factory(ax.transData,ax.transAxes)
            for c in [1,2,3]:
                s=next(s for s in stats if s['metric']==METRICS[m] and s['mode']==mode and s['construct']==CLASSES[c])
                h=1.03+(c-1)*.075
                ax.plot([0,0,c,c],[h-.01,h,h,h-.01],color='black',lw=.6,transform=trans,clip_on=False)
                label=prepub.stars(s['mean_holm_p']) if min(s['group_n'],s['control_n'])>=2 else 'n/a'
                ax.text(c/2,h+.005,label,transform=trans,ha='center',fontsize=7)
            selection=selected[m]
            if row:
                end=0. if abs(selection['pre_end_s'])<1e-12 else selection['pre_end_s']
                subtitle=f"pre: {selection['pre_start_s']:g} to {end:g} s"
                heading=['Firing-rate change','Burst-fraction change','Active-bin change','Short-ISI change','Long-pause change'][m]
            else:
                subtitle=f"post: +{selection['post_start_s']:g} to +{selection['post_end_s']:g} s"
                heading=TITLES[m]
            ax.set_title(heading+'\n'+subtitle,fontsize=9,y=1.29)
            ax.text(-.18,1.47,'abcdefghij'[row*5+m],transform=ax.transAxes,fontweight='bold',fontsize=12)

def make_figure(y,selected,before,after,change,stats,family):
    fig,axes=plt.subplots(2,5,figsize=(17,9))
    draw_metric_panels(axes,y,selected,after,change,stats)
    fig.suptitle('Actuators + effectors: post-stim phenotypes and within-unit changes',fontsize=15,y=.995)
    fig.subplots_adjust(left=.055,right=.985,top=.83,bottom=.17,wspace=.55,hspace=1.07)
    fig.text(.5,.025,'TOP: post-stim level. BOTTOM: each unit’s post-minus-mirrored-pre change; percentage-point differences for proportion metrics.\n'
        'Dots = units; black = mean ± SEM; SUA/MUA pooled. Each metric uses its strongest shared post-stim window; the same window is used for its change plot.\n'
        f'Stars = Welch tests versus Control, Holm across {family:,} prior/current tests. ISI valid n is shown; paired ISI changes require measurable pre and post intervals.\n'
        'Stimulation artifacts are included; very early windows overlap the pulse train. Raw unit values retain their real discrete levels.',ha='center',fontsize=7)
    fig.savefig(OUT/'poststim_phenotypes_mean_sem.png',dpi=300)
    fig.savefig(OUT/'poststim_phenotypes_mean_sem.pdf',dpi=300);plt.close(fig)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=list(csv.DictReader((base.OUT/'unit_metrics.csv').open()));y=np.array([CLASSES.index(r['construct']) for r in rows])
    before,after,change=extract(rows)
    prior_w=[];prior_r=[]
    old=np.load(OUT.parent/'prestim_baseline/baseline_unit_metrics.npz',allow_pickle=False)['values']
    for j in range(old.shape[1]):
        for c in [1,2,3]:
            p,q,_=prepub.pair_stats(old[y==c,j],old[y==0,j]);prior_w.append(p);prior_r.append(q)
    for r in csv.DictReader((OUT.parent/'baseline_publication/all_window_control_tests.csv').open()):
        prior_w.append(float(r['welch_p']));prior_r.append(float(r['mannwhitney_p']))
    tests=[]
    for m,name in enumerate(METRICS):
        for j,(width,offset) in enumerate(WINDOWS):
            for mode,data in [('post',after),('change',change)]:
                for c in [1,2,3]:
                    p,q,d=prepub.pair_stats(data[m,y==c,j],data[m,y==0,j])
                    tests.append(dict(metric=name,window_index=j,mode=mode,construct=CLASSES[c],
                        mean_p=p,rank_p=q,cliff_delta=d))
            for c in range(4):
                p,q=one_sample_p(change[m,y==c,j])
                tests.append(dict(metric=name,window_index=j,mode='paired_pre_post',construct=CLASSES[c],
                                  mean_p=p,rank_p=q,cliff_delta=np.nan))
    wa=prepub.adjust(prior_w+[r['mean_p'] for r in tests])[len(prior_w):]
    ra=prepub.adjust(prior_r+[r['rank_p'] for r in tests])[len(prior_r):]
    for i,r in enumerate(tests):r.update(mean_holm_p=float(wa[i]),rank_holm_p=float(ra[i]))
    prepub.write(OUT/'all_window_tests.csv',tests)
    selected=[];stats=[];summaries=[];rng=np.random.default_rng(20261114)
    for m,name in enumerate(METRICS):
        best,objective=optimum(after[m],y);width,offset=WINDOWS[best]
        de=prepub.effects(change[m,:,best:best+1],y)[:,0]
        delta_objective=float(np.min(np.abs(de))) if np.isfinite(de).all() else None
        selected.append(dict(metric=name,window_index=best,post_start_s=offset,post_end_s=offset+width,
            pre_start_s=-offset-width,pre_end_s=-offset,post_min_abs_cliff_delta=objective,
            change_min_abs_cliff_delta=delta_objective))
        for c,label in enumerate(CLASSES):
            pre=before[m,y==c,best];post=after[m,y==c,best];delta=change[m,y==c,best]
            good=np.isfinite(delta);v=delta[good]
            ci=np.percentile(v[rng.integers(len(v),size=(2000,len(v)))].mean(axis=1),[2.5,97.5]).tolist() if len(v)>1 else [np.nan,np.nan]
            paired=next(t for t in tests if t['metric']==name and t['window_index']==best and t['mode']=='paired_pre_post' and t['construct']==label)
            summaries.append(dict(metric=name,construct=label,total_units=int(np.sum(y==c)),
                pre_n=summarize(pre)['n'],pre_mean=summarize(pre)['mean'],
                post_n=summarize(post)['n'],post_mean=summarize(post)['mean'],post_sem=summarize(post)['sem'],
                paired_n=len(v),paired_pre_mean=float(pre[good].mean()) if len(v) else np.nan,
                paired_post_mean=float(post[good].mean()) if len(v) else np.nan,
                change_mean=summarize(delta)['mean'],change_sem=summarize(delta)['sem'],
                change_ci_low=ci[0],change_ci_high=ci[1],paired_t_holm_p=paired['mean_holm_p'],
                paired_wilcoxon_holm_p=paired['rank_holm_p']))
        for mode,data in [('post',after),('change',change)]:
            for c in [1,2,3]:
                x=data[m,y==c,best];control=data[m,y==0,best];x=x[np.isfinite(x)];control=control[np.isfinite(control)]
                mean_ci,cliff_ci=prepub.bootstrap(x,control,rng)
                t=next(t for t in tests if t['metric']==name and t['window_index']==best and t['mode']==mode and t['construct']==CLASSES[c])
                stats.append(dict(**t,group_n=len(x),control_n=len(control),
                    mean_difference=float(x.mean()-control.mean()) if min(len(x),len(control)) else np.nan,
                    mean_ci_low=mean_ci[0],mean_ci_high=mean_ci[1],cliff_ci_low=cliff_ci[0],cliff_ci_high=cliff_ci[1]))
        print('Selected',selected[-1],flush=True)
    exceed_post=np.zeros(5,int);exceed_change=np.zeros(5,int)
    for iteration in range(N_PERM):
        yp=rng.permutation(y)
        for m in range(5):
            best,obj=optimum(after[m],yp)
            exceed_post[m]+=obj>=selected[m]['post_min_abs_cliff_delta']-1e-12
            if selected[m]['change_min_abs_cliff_delta'] is not None:
                d=prepub.effects(change[m,:,best:best+1],yp)[:,0]
                objective=float(np.min(np.abs(d))) if np.isfinite(d).all() else 0.
                exceed_change[m]+=objective>=selected[m]['change_min_abs_cliff_delta']-1e-12
        if (iteration+1)%100==0:print('Selection-aware permutations',iteration+1,flush=True)
    ppost=(exceed_post+1)/(N_PERM+1);pdelta=np.array([(exceed_change[i]+1)/(N_PERM+1)
        if selected[i]['change_min_abs_cliff_delta'] is not None else 1. for i in range(5)])
    corrected=prepub.adjust(np.r_[ppost,pdelta])
    for i,s in enumerate(selected):s.update(post_search_permutation_holm_p=float(corrected[i]),
                                         change_selection_permutation_holm_p=float(corrected[i+5]))
    prepub.write(OUT/'selected_conditions.csv',selected);prepub.write(OUT/'unit_mean_sem_and_paired_tests.csv',summaries)
    prepub.write(OUT/'selected_control_tests.csv',stats)
    unit_rows=[]
    for i,r in enumerate(rows):
        values=dict(recording_id=r['recording_id'],unit_id=r['unit_id'],construct=r['construct'])
        for m,name in enumerate(METRICS):
            j=selected[m]['window_index']
            for suffix,data in [('pre',before),('post',after),('change',change)]:values[name+'_'+suffix]=data[m,i,j]
        unit_rows.append(values)
    prepub.write(OUT/'selected_unit_pre_post.csv',unit_rows)
    family=len(prior_w)+len(tests)
    make_figure(y,selected,before,after,change,stats,family)
    summary=dict(scope='Actuators + effectors',units=len(rows),pool_sua_mua=True,observation='one unit',
        post_windows=len(WINDOWS),selected_conditions=selected,selection='Maximize minimum absolute Cliff delta of post levels versus Control',
        pre_window_rule='Mirror of post interval around t=0; same duration and distance from event',
        correction_family_size=family,unit_bootstrap=2000,permutations=N_PERM,
        paired_mean_test='Paired t test (one-sample test of within-unit delta)',paired_robust_test='Wilcoxon signed-rank',
        control_mean_test='Welch test of post levels or changes versus Control',
        current_lda_changed=False,artifact_blanking=False)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    lines=['# Post-stim phenotypes and paired unit changes','',
        'Actuators + effectors only. Each dot is one unit; SUA/MUA pooled. Precise proportion denominators are labeled.',
        '', '## Window selection','',
        f'{len(WINDOWS)} post intervals lie within 0–10 seconds. Each metric maximizes the weakest absolute post-level Cliff delta across the three actuator/Control comparisons.',
        'Paired baseline is the mirrored interval: post [a,b) corresponds to pre [−b,−a). The same post-level-selected condition is used for the change analysis; changes are not re-optimized.',
        'Top row is absolute post activity; bottom row is each unit’s change, directly compared with Control-unit changes.',
        'A percentage-point difference is subtraction of two percentages, not division by baseline. No undefined zero-baseline fold changes are introduced.',
        '', '| Metric | Post window | Mirrored pre | Post search permutation p | Change selection-aware p |',
        '| --- | --- | --- | ---: | ---: |']
    for s in selected:lines.append(f"| {s['metric']} | {s['post_start_s']:g} to {s['post_end_s']:g} | {s['pre_start_s']:g} to {s['pre_end_s']:g} | {s['post_search_permutation_holm_p']:.3g} | {s['change_selection_permutation_holm_p']:.3g} |")
    lines += ['', '## Statistics','',
        f'Welch mean tests, paired t tests, Mann-Whitney robustness tests and Wilcoxon paired robustness tests are corrected over {family} prior/current hypotheses (separate mean/rank families).',
        'Mean/SEM is computed across units. For ISI proportions, post levels require at least two post spikes; paired changes require measurable intervals in both periods.',
        'Counts and paired pre/post means are supplied so differing valid subsets are explicit. Missing ISIs are never imputed as zero.',
        '2,000 within-group unit bootstrap draws give pointwise mean-difference/effect intervals. These intervals are not selection-adjusted.',
        '999 label permutations repeat post-window selection, then evaluate both optimized post separation and change separation at that chosen window. Holm adjustment covers the ten omnibus tests.',
        'The plots are exploratory unit-level comparisons. Stimulation artifacts remain included, particularly in windows overlapping the approximately 41-ms train.',
        '', '## Files','',
        'poststim_phenotypes_mean_sem.png and .pdf: one figure, two formats.',
        'unit_mean_sem_and_paired_tests.csv: pre/post and paired-change summaries, valid counts, CIs, paired t/Wilcoxon tests.',
        'selected_control_tests.csv: post and change comparisons against 371 Control with corrected tests and effect-size intervals.',
        'selected_unit_pre_post.csv: the unit values behind the figure. all_window_tests.csv: complete search tests.',
        'pre_post_all_windows.npz: compressed pre/post/change values and unit identities. selected_conditions.csv and summary.json: methods and selections.',
        'Source: scripts/plot_mcs_poststim_publication.py. All artifacts are on scratch. The locked 215-metric LDA is unchanged.']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n')
    print('COMPLETE',OUT,flush=True)

def render_only():
    archive=np.load(OUT/'pre_post_all_windows.npz',allow_pickle=False)
    y=np.array([CLASSES.index(c) for c in archive['construct']])
    summary=json.loads((OUT/'summary.json').read_text())
    stats=list(csv.DictReader((OUT/'selected_control_tests.csv').open()))
    for r in stats:
        for key in ['mean_holm_p','group_n','control_n']:
            r[key]=float(r[key])
    make_figure(y,summary['selected_conditions'],archive['before'],archive['after'],archive['change'],stats,summary['correction_family_size'])
    print('PNG and PDF re-exported from saved post-stim data.',flush=True)

if __name__=='__main__':
    if '--render-only' in sys.argv:
        render_only()
    else:
        main()
