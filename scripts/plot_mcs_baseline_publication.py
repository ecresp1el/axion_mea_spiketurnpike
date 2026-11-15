"""Selected-window baseline phenotypes: unit dots, mean/SEM, corrected tests."""
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
from scipy.stats import mannwhitneyu,rankdata,ttest_ind
import explore_mcs_actuator_separation as base
from explore_mcs_prestim_baseline import WINDOWS,window_name

OUT=Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/baseline_publication')
PRE=OUT.parent/'prestim_baseline'
CLASSES=base.CLASSES
METRICS=['firing_rate','burst_spike_fraction','active_1s_fraction','short_isi_fraction','long_pause_fraction']
TITLES=['Firing rate','Spikes in bursts (≤25 ms, ≥3 spikes)','Active 1-s bins',
        'Short intervals (<50 ms)','Long pauses (>200 ms)']
COLORS=['#777777','#e94b47','#64af54','#9462d5']
N_PERM=999
N_BOOT=2000

def write(path,rows):
    base.write_csv(path,rows)

def adjust(p):
    p=np.nan_to_num(np.asarray(p,dtype=float),nan=1.)
    order=np.argsort(p);result=np.empty(len(p));last=0.
    for rank,i in enumerate(order):
        last=max(last,min(1.,p[i]*(len(p)-rank)));result[i]=last
    return result

def pair_stats(x,c):
    x=x[np.isfinite(x)];c=c[np.isfinite(c)]
    if min(len(x),len(c))<2:return 1.,1.,0.
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        wp=float(ttest_ind(x,c,equal_var=False).pvalue)
    if not np.isfinite(wp):wp=1.
    test=mannwhitneyu(x,c,alternative='two-sided',method='asymptotic')
    return wp,float(test.pvalue),float(2*test.statistic/(len(x)*len(c))-1)

def effects(data,y):
    """Vectorized Cliff deltas for every window, preserving missing ISIs."""
    result=[];c=data[y==0]
    for group in [1,2,3]:
        x=data[y==group];pool=np.vstack([x,c])
        ranks=rankdata(pool,axis=0,nan_policy='omit')
        nx=np.sum(np.isfinite(x),axis=0);nc=np.sum(np.isfinite(c),axis=0)
        u=np.nansum(ranks[:len(x)],axis=0)-nx*(nx+1)/2
        with np.errstate(divide='ignore',invalid='ignore'):
            d=2*u/(nx*nc)-1
        d[(nx<2)|(nc<2)]=np.nan;result.append(d)
    return np.array(result)

def optimum(data,y):
    d=effects(data,y);valid=np.all(np.isfinite(d),axis=0)
    score=np.full(data.shape[1],-np.inf)
    score[valid]=np.min(np.abs(d[:,valid]),axis=0)
    if not valid.any():raise ValueError('No valid shared window')
    best=max(np.where(valid)[0],key=lambda j:(score[j],WINDOWS[j][0],-WINDOWS[j][1]))
    return int(best),float(score[best]),d

def extract(rows):
    records={r['recording_id']:r for r in csv.DictReader((base.REPO/'metadata/mcs_recording_biology.csv').open())}
    data=np.full((len(METRICS),len(rows),len(WINDOWS)),np.nan)
    groups={}
    for i,r in enumerate(rows):groups.setdefault(r['recording_id'],[]).append((i,r))
    for rid,units in groups.items():
        record=records[rid];files=list((Path(record['sorting_output_path'])/'curated').glob('*/numpysorting_info.json'));assert len(files)==1
        info=json.loads(files[0].read_text());fs=info['sampling_frequency'];onset=float(units[0][1]['event_time_s'])
        spikes=np.load(files[0].parent/'spikes.npy',mmap_mode='r')
        first=int(np.ceil(onset*fs-1e-7));lo,hi=np.searchsorted(spikes['sample_index'],[(onset-20)*fs,first])
        window=spikes[lo:hi];relative=window['sample_index']/fs-onset
        assert np.all(window['sample_index']<first)
        indices={str(uid):i for i,uid in enumerate(info['unit_ids'])}
        for index,r in units:
            t=relative[window['unit_index']==indices[r['unit_id']]]
            t=t[(t>=-20)&(t<0)]
            for j,(width,offset) in enumerate(WINDOWS):
                a,b=-width-offset,-offset
                s=t[(t>=a)&(t<b)];isi=np.diff(s)
                data[0,index,j]=len(s)/width
                if len(s):
                    cuts=np.flatnonzero(isi>.025+1e-12)+1
                    sizes=np.diff(np.r_[0,cuts,len(s)])
                    data[1,index,j]=np.sum(sizes[sizes>=3])/len(s)
                else:data[1,index,j]=0.
                if width>=1:
                    counts=np.histogram(s,a+np.arange(int(width)+1))[0]
                    data[2,index,j]=np.mean(counts>0)
                if len(isi):
                    data[3,index,j]=np.mean(isi<.05)
                    data[4,index,j]=np.mean(isi>.2)
        print('Extracted',rid,flush=True)
    np.savez_compressed(OUT/'all_window_measurements.npz',values=data,metric_names=np.array(METRICS),
        windows=np.array(WINDOWS),recording_id=np.array([r['recording_id'] for r in rows]),
        unit_id=np.array([r['unit_id'] for r in rows]),construct=np.array([r['construct'] for r in rows]))
    return data

def bootstrap(x,c,rng):
    x=x[np.isfinite(x)];c=c[np.isfinite(c)]
    if min(len(x),len(c))<2:return [np.nan,np.nan],[np.nan,np.nan]
    bx=x[rng.integers(len(x),size=(N_BOOT,len(x)))];bc=c[rng.integers(len(c),size=(N_BOOT,len(c)))]
    mean_ci=np.percentile(bx.mean(axis=1)-bc.mean(axis=1),[2.5,97.5])
    u=mannwhitneyu(bx,bc,axis=1,alternative='two-sided',method='asymptotic').statistic
    delta_ci=np.percentile(2*u/(len(x)*len(c))-1,[2.5,97.5])
    return mean_ci.tolist(),delta_ci.tolist()

def stars(p):
    if p<1e-4:return '****'
    if p<1e-3:return '***'
    if p<.01:return '**'
    if p<.05:return '*'
    return 'ns'

def make_figure(y,selected,selected_values,comparisons,correction_count):
    fig,axes=plt.subplots(2,3,figsize=(12.5,8.7));axes=axes.ravel();rng=np.random.default_rng(42)
    for metric,ax in enumerate(axes[:5]):
        values=selected_values[metric];factor=1 if metric==0 else 100
        for c,label in enumerate(CLASSES):
            v=values[y==c];v=v[np.isfinite(v)]*factor
            ax.scatter(c+rng.uniform(-.19,.19,len(v)),v,s=5,color=COLORS[c],alpha=.19,linewidths=0,zorder=1,rasterized=True)
            ax.errorbar(c,v.mean(),yerr=v.std(ddof=1)/np.sqrt(len(v)),fmt='o',color='black',
                markersize=5,capsize=4,elinewidth=1.4,markeredgecolor='white',markeredgewidth=.6,zorder=3)
        if metric==0:
            ax.set_yscale('symlog',linthresh=1);ax.set_ylabel('Firing rate (Hz; symlog)',fontsize=9);ax.set_ylim(bottom=0)
        else:ax.set_ylabel('Percent',fontsize=9);ax.set_ylim(-4,104)
        counts=[np.sum(np.isfinite(values[y==c])) for c in range(4)]
        ax.set_xticks(range(4),[f'{c}\nn={n}' + (f'/{np.sum(y==i)}' if metric>=3 else '') for i,(c,n) in enumerate(zip(CLASSES,counts))],fontsize=8,rotation=20)
        s=selected[metric]
        ax.set_title(f"{TITLES[metric]}\n{s['start_s']:g} to {s['end_s']:g} s",fontsize=10,y=1.27)
        trans=blended_transform_factory(ax.transData,ax.transAxes)
        for c in [1,2,3]:
            p=next(r['welch_holm_p'] for r in comparisons if r['metric']==METRICS[metric] and r['construct']==CLASSES[c])
            h=1.03+(c-1)*.075
            ax.plot([0,0,c,c],[h-.015,h,h,h-.015],color='black',lw=.6,transform=trans,clip_on=False)
            ax.text(c/2,h+.003,stars(p),ha='center',va='bottom',fontsize=8,transform=trans)
        ax.spines[['top','right']].set_visible(False);ax.tick_params(width=.7,length=3)
        ax.text(-.17,1.42,'abcde'[metric],transform=ax.transAxes,fontweight='bold',fontsize=13)
    ax=axes[5]
    short=['Rate','Burst spikes','Active bins','Short ISIs','Long pauses']
    for i,r in enumerate(comparisons):
        c=CLASSES.index(r['construct']);position=len(comparisons)-i
        ax.plot([r['cliff_ci_low'],r['cliff_ci_high']],[position,position],color=COLORS[c],lw=1.2)
        ax.scatter(r['cliff_delta'],position,color=COLORS[c],s=18)
    ax.axvline(0,color='#777777',lw=.7,ls='--');ax.set_xlim(-1,1)
    ax.set_yticks(range(15,0,-1),[f'{short[i//3]}: {r["construct"]}' for i,r in enumerate(comparisons)],fontsize=7)
    ax.set_xlabel('Cliff δ versus Control (95% CI)',fontsize=9)
    ax.set_title('Magnitude and direction of differences',fontsize=10,y=1.27)
    ax.text(-.17,1.42,'f',transform=ax.transAxes,fontweight='bold',fontsize=13)
    ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Pre-stim baseline phenotypes: optimized windows, Control comparisons',fontsize=14,y=.995)
    fig.subplots_adjust(left=.08,right=.98,top=.83,bottom=.16,hspace=1.00,wspace=.48)
    fig.text(.5,.025,'Each dot = one unit; black symbols = mean ± SEM; SUA/MUA pooled. Windows independently maximize the weakest |Cliff δ| across three Control comparisons.\n'
        f'Stars = Welch tests versus Control, Holm-adjusted across {correction_count:,} prior/current tests: *<0.05, **<0.01, ***<0.001, ****<0.0001; ns = not significant.\n'
        'Panel f: pointwise 95% unit-bootstrap intervals at selected windows (not selection-adjusted); full-search permutation tests are provided separately.\n'
        'ISI panels require at least two baseline spikes; valid n is displayed. All activity is strictly before first e-stim.',ha='center',fontsize=7)
    fig.savefig(OUT/'baseline_phenotypes_mean_sem.png',dpi=300)
    fig.savefig(OUT/'baseline_phenotypes_mean_sem.pdf',dpi=300)
    plt.close(fig)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=list(csv.DictReader((base.OUT/'unit_metrics.csv').open()));y=np.array([CLASSES.index(r['construct']) for r in rows])
    data=extract(rows)
    # Carry the prior broad baseline search into the correction family.
    previous=np.load(PRE/'baseline_unit_metrics.npz',allow_pickle=False)
    old=previous['values'];assert np.array_equal(previous['unit_id'],np.array([r['unit_id'] for r in rows]))
    prior_w=[];prior_m=[]
    for j in range(old.shape[1]):
        for c in [1,2,3]:
            w,m,_=pair_stats(old[y==c,j],old[y==0,j]);prior_w.append(w);prior_m.append(m)
    tests=[];welch=[];mw=[]
    for metric in range(len(METRICS)):
        for j in range(len(WINDOWS)):
            for c in [1,2,3]:
                w,m,d=pair_stats(data[metric,y==c,j],data[metric,y==0,j])
                tests.append(dict(metric=METRICS[metric],window_index=j,window=window_name(*WINDOWS[j]),construct=CLASSES[c],
                                  welch_p=w,mannwhitney_p=m,cliff_delta=d))
                welch.append(w);mw.append(m)
    wa=adjust(prior_w+welch)[len(prior_w):];ma=adjust(prior_m+mw)[len(prior_m):]
    for i,r in enumerate(tests):r.update(welch_holm_p=float(wa[i]),mannwhitney_holm_p=float(ma[i]))
    write(OUT/'all_window_control_tests.csv',tests)
    selected=[];group_summaries=[];comparisons=[];selected_values=[]
    rng=np.random.default_rng(20261114)
    for metric,name in enumerate(METRICS):
        best,objective,_=optimum(data[metric],y);width,offset=WINDOWS[best]
        selected.append(dict(metric=name,window_index=best,start_s=-width-offset,end_s=-offset,
                             minimum_absolute_cliff_delta=objective))
        values=data[metric,:,best];selected_values.append(values)
        for c,label in enumerate(CLASSES):
            v=values[y==c];v=v[np.isfinite(v)]
            group_summaries.append(dict(metric=name,construct=label,n=int(len(v)),total_units=int(np.sum(y==c)),
                mean=float(v.mean()),sem=float(v.std(ddof=1)/np.sqrt(len(v))),median=float(np.median(v)),
                start_s=-width-offset,end_s=-offset))
        for c in [1,2,3]:
            x=values[y==c];control=values[y==0];x=x[np.isfinite(x)];control=control[np.isfinite(control)]
            mean_ci,delta_ci=bootstrap(x,control,rng)
            test=next(r for r in tests if r['metric']==name and r['window_index']==best and r['construct']==CLASSES[c])
            comparisons.append(dict(**test,group_n=len(x),control_n=len(control),
                group_mean=float(x.mean()),control_mean=float(control.mean()),mean_difference=float(x.mean()-control.mean()),
                mean_difference_ci_low=mean_ci[0],mean_difference_ci_high=mean_ci[1],
                cliff_ci_low=delta_ci[0],cliff_ci_high=delta_ci[1],start_s=-width-offset,end_s=-offset))
        print('Selected',selected[-1],flush=True)
    # Repeat the complete window maximization after label permutation.
    exceed=np.zeros(len(METRICS),dtype=int)
    for iteration in range(N_PERM):
        permuted=rng.permutation(y)
        for metric in range(len(METRICS)):
            _,objective,_=optimum(data[metric],permuted)
            exceed[metric]+=objective>=selected[metric]['minimum_absolute_cliff_delta']-1e-12
        if (iteration+1)%100==0:print('Full-search permutations',iteration+1,flush=True)
    permutation_p=(exceed+1)/(N_PERM+1);permutation_adjusted=adjust(permutation_p)
    for i,s in enumerate(selected):s.update(search_permutation_p=float(permutation_p[i]),
                                          search_permutation_holm_p=float(permutation_adjusted[i]))
    write(OUT/'selected_conditions.csv',selected);write(OUT/'group_mean_sem.csv',group_summaries)
    write(OUT/'selected_control_statistics.csv',comparisons)
    unit_rows=[]
    for i,r in enumerate(rows):
        unit_rows.append(dict(recording_id=r['recording_id'],unit_id=r['unit_id'],construct=r['construct'],
                             **{n:selected_values[j][i] for j,n in enumerate(METRICS)}))
    write(OUT/'selected_unit_values.csv',unit_rows)
    make_figure(y,selected,selected_values,comparisons,len(prior_w)+len(tests))
    hypotheses=[('DREADD','burst_spike_fraction',-1),('LMO','firing_rate',1),('LMO','active_1s_fraction',1),
                ('PSAM','short_isi_fraction',-1),('PSAM','long_pause_fraction',1)]
    claims=[]
    for construct,metric,direction in hypotheses:
        r=next(r for r in comparisons if r['construct']==construct and r['metric']==metric)
        claims.append(dict(construct=construct,metric=metric,expected_direction='higher' if direction>0 else 'lower',
            observed_mean_difference=r['mean_difference'],welch_holm_p=r['welch_holm_p'],
            mannwhitney_holm_p=r['mannwhitney_holm_p'],
            supports_directional_mean_claim=bool(r['mean_difference']*direction>0 and r['welch_holm_p']<.05)))
    write(OUT/'claim_checks.csv',claims)
    summary=dict(units=len(rows),scope='Actuators + effectors',unit_is_observation=True,
        selected_conditions=selected,bootstrap_replicates=N_BOOT,permutations=N_PERM,
        primary_test='Two-sided Welch t test for means versus 371 Control',
        robustness_test='Two-sided Mann-Whitney U for distributions',
        holm_family_size=len(prior_w)+len(tests),claims=claims,
        fixed_window_override=False,selection_objective='Maximize minimum absolute Cliff delta over DREADD/LMO/PSAM versus Control',
        limitations='Exploratory analysis of existing units; confidence intervals are pointwise after selection; significance is not proof of a causal treatment effect')
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    lines=['# Publication-style selected-window baseline phenotype analysis','',
        'The user requested strongest-separation windows. Each metric therefore selects its own shared pre-stim window; no fixed-window override is used.',
        'The same selected window applies to all four groups within a panel. No unit is removed based on its response.',
        'Each dot is one unit; SUA/MUA pooled; Actuators + effectors only; all tests compare with 371 Control.',
        '', '## Selection and statistics','',
        'The 48 candidates lie entirely within −20 to 0 seconds. Selection maximizes the minimum absolute Cliff delta across the three actuator/Control comparisons.',
        'Bursting: fraction of spikes in consecutive-ISI clusters ≤25 ms, minimum 3 spikes; no-spike units have burst fraction zero.',
        'Occupancy: fraction of complete 1-s bins with spikes; widths shorter than 1 s are undefined and ineligible for this metric.',
        'Short ISIs: fraction below 50 ms; pauses: fraction above 200 ms. ISI proportions are undefined with fewer than two spikes and valid counts are displayed.',
        f'Welch mean tests and Mann-Whitney tests are each Holm-adjusted over {len(prior_w)} previous baseline comparisons plus {len(tests)} current candidate comparisons.',
        f'{N_PERM} unit-label permutations repeat the complete window search; permutation p values are further Holm-adjusted over the five metrics.',
        f'{N_BOOT} within-group unit bootstrap replicates provide 95% percentile intervals for mean differences and Cliff delta.',
        'Bootstrap intervals are pointwise at selected conditions, not selection-adjusted confidence intervals. Window-search permutation results address the selection separately.',
        '', '## Selected conditions','', '| Metric | Window (s) | Minimum abs δ | Search-adjusted permutation p |', '| --- | --- | ---: | ---: |']
    for s in selected:lines.append(f"| {s['metric']} | {s['start_s']:g} to {s['end_s']:g} | {s['minimum_absolute_cliff_delta']:.3f} | {s['search_permutation_holm_p']:.3g} |")
    lines += ['', '## Direct checks of the stated claims','', '| Construct | Claim | Mean difference | Welch adjusted p | Supported under selected condition? |','| --- | --- | ---: | ---: | --- |']
    for r in claims:lines.append(f"| {r['construct']} | {r['expected_direction']} {r['metric']} | {r['observed_mean_difference']:+.4g} | {r['welch_holm_p']:.3g} | {r['supports_directional_mean_claim']} |")
    lines += ['', 'Claims may change with the selected condition; unsupported or reversed claims are retained in the tables.',
        'Mean/SEM is a descriptive summary; raw unit dots display the skew and heterogeneity. Results are exploratory evidence in these units, not independent replication or causal proof.',
        '', '## Files','',
        'baseline_phenotypes_mean_sem.png: one 300-dpi six-panel figure. group_mean_sem.csv: exact means, SEMs, medians, counts.',
        'selected_control_statistics.csv: mean differences, bootstrap CIs, Cliff effects/CIs, Welch and Mann-Whitney raw/adjusted p values.',
        'all_window_control_tests.csv: every current search condition and Control test. selected_conditions.csv: search choices and permutation p values.',
        'claim_checks.csv: exact support/direction checks. selected_unit_values.csv: unit values behind the figure.',
        'all_window_measurements.npz: compact full-search values and join keys. summary.json: method and audit metadata.',
        'Source: scripts/plot_mcs_baseline_publication.py. The locked 215-feature LDA is unchanged. All outputs are on scratch.']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n')
    print('COMPLETE',json.dumps(claims),flush=True)

def render_only():
    records=list(csv.DictReader((OUT/'selected_unit_values.csv').open()))
    y=np.array([CLASSES.index(r['construct']) for r in records])
    values=[np.array([float(r[n]) for r in records]) for n in METRICS]
    selected=list(csv.DictReader((OUT/'selected_conditions.csv').open()))
    for r in selected:
        r['start_s']=float(r['start_s']);r['end_s']=float(r['end_s'])
    comparisons=list(csv.DictReader((OUT/'selected_control_statistics.csv').open()))
    for r in comparisons:
        for key in ['welch_holm_p','cliff_ci_low','cliff_ci_high','cliff_delta']:
            r[key]=float(r[key])
    summary=json.loads((OUT/'summary.json').read_text())
    make_figure(y,selected,values,comparisons,summary['holm_family_size'])
    print('PNG and PDF rendered from saved statistics.',flush=True)

if __name__=='__main__':
    if '--render-only' in sys.argv:
        render_only()
    else:
        main()
