"""Reuse published post-stim panels; add saved effects and an explicit LDA panel."""
import argparse
import csv
import hashlib
import json
import warnings
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.impute import SimpleImputer
from sklearn.metrics import balanced_accuracy_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import explore_mcs_actuator_separation as base
import plot_mcs_poststim_publication as post
from load_mcs_locked_lda import load_units,project_units,CONFIG

SOURCE=post.OUT
OUT=SOURCE/'targeted_figure'
REPO=base.REPO
COLORS=post.prepub.COLORS

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read_csv(path):
    return list(csv.DictReader(Path(path).open()))

def forest(ax,stats,mode,letter):
    short=['Rate','Burst fraction','Active bins','Short ISIs','Long pauses']
    ordered=[next(r for r in stats if r['mode']==mode and r['metric']==metric and r['construct']==construct)
             for metric in post.METRICS for construct in base.CLASSES[1:]]
    for i,r in enumerate(ordered):
        pos=15-i;color=COLORS[base.CLASSES.index(r['construct'])]
        ax.plot([float(r['cliff_ci_low']),float(r['cliff_ci_high'])],[pos,pos],color=color,lw=1.2)
        ax.scatter(float(r['cliff_delta']),pos,color=color,s=17,zorder=3)
    ax.axvline(0,color='#777777',lw=.8,ls='--')
    ax.set_xlim(-1.03,1.03);ax.set_ylim(.3,15.7)
    ax.set_yticks(range(15,0,-1),[f'{short[i//3]}: {r["construct"]}' for i,r in enumerate(ordered)],fontsize=6.5)
    ax.set_xticks([-1,-.5,0,.5,1]);ax.tick_params(axis='x',labelsize=8)
    ax.set_xlabel('Cliff δ versus Control; pointwise 95% CI',fontsize=8)
    heading='Post-stim levels' if mode=='post' else 'Post − pre changes'
    ax.set_title(heading+'\nMagnitude and direction versus Control',fontsize=10,pad=12)
    ax.spines[['top','right']].set_visible(False)
    ax.text(-.20,1.09,letter,transform=ax.transAxes,fontweight='bold',fontsize=13)
    ax.text(.5,-.18,'← lower than Control     higher than Control →',transform=ax.transAxes,
            ha='center',fontsize=6.5)
    return ordered

def matrix_at_windows(after,change,indices,unit_indices=None):
    if unit_indices is None:unit_indices=np.arange(after.shape[1])
    return np.column_stack([data[m,unit_indices,indices[m]] for data in [after,change] for m in range(5)])

def targeted_pipeline(projection=False):
    return Pipeline([('impute',SimpleImputer(strategy='median',keep_empty_features=True)),
        ('scale',StandardScaler()),('lda',LinearDiscriminantAnalysis(
         solver='eigen' if projection else 'lsqr',shrinkage=.01,n_components=2 if projection else None))])

def targeted_lda(after,change,selected,y):
    indices=[r['window_index'] for r in selected]
    raw=matrix_at_windows(after,change,indices)
    x=np.sign(raw)*np.log1p(np.abs(raw))
    names=[n+'_post' for n in post.METRICS]+[n+'_change' for n in post.METRICS]
    fitted=targeted_pipeline(projection=True).fit(x,y)
    coordinates=fitted.transform(x)
    prediction=np.full(len(y),-1);folds=[]
    for fold,(train,test) in enumerate(StratifiedKFold(3,shuffle=True,random_state=20261114).split(x,y)):
        chosen=[post.optimum(after[m,train],y[train])[0] for m in range(5)]
        tr=matrix_at_windows(after,change,chosen,train);te=matrix_at_windows(after,change,chosen,test)
        tr=np.sign(tr)*np.log1p(np.abs(tr));te=np.sign(te)*np.log1p(np.abs(te))
        model=targeted_pipeline()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore');model.fit(tr,y[train])
        prediction[test]=model.predict(te)
        folds.append(dict(fold=fold,training_selected_window_indices=chosen))
    assert np.all(prediction>=0)
    score=float(balanced_accuracy_score(y,prediction))
    lda=fitted.named_steps['lda'];scaler=fitted.named_steps['scale'];imputer=fitted.named_steps['impute']
    model_path=OUT/'targeted_10_lda_state.npz'
    np.savez_compressed(model_path,feature_names=np.array(names),impute_median=imputer.statistics_,
        scale_mean=scaler.mean_,scale_std=scaler.scale_,lda_projection=lda.scalings_[:,:2],
        lda_coef=lda.coef_,lda_intercept=lda.intercept_,classes=lda.classes_)
    return coordinates,dict(mode='targeted10',feature_names=names,feature_count=10,
        fitted_state=str(model_path),fitted_state_sha256=sha(model_path),shrinkage=.01,
        full_data_fit=True,imputation='training/full-fit median as appropriate',
        transform='signed log1p, median imputation, standard scaling, shrinkage LDA',
        nested_unit_balanced_accuracy=score,validation='3 unit folds; post-window selection repeated on training units only',folds=folds)

def locked_lda(records):
    metadata,values=load_units();coordinates,_=project_units(values)
    lookup={(r.recording_id,str(r.unit_id)):i for i,r in enumerate(metadata.itertuples())}
    indices=[lookup[(r['recording_id'],r['unit_id'])] for r in records]
    coordinates=coordinates[indices]
    assert np.array_equal(metadata.iloc[indices]['construct'].to_numpy(),np.array([r['construct'] for r in records]))
    config=json.loads(CONFIG.read_text())
    return coordinates,dict(mode='locked215',feature_count=215,
        feature_names=config['original_features']+config['new_burst_features'],
        source_configuration=str(CONFIG),configuration_sha256=sha(CONFIG),
        fitted_state=config['frozen_model_npz'],fitted_state_sha256=sha(config['frozen_model_npz']),
        raw_metrics=config['frozen_raw_metrics_csv'],raw_metrics_sha256=sha(config['frozen_raw_metrics_csv']),
        computation='Existing saved transform applied without refitting, reselection, or rotation',
        full_data_fit=True,shrinkage=.01)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--lda-input',choices=['locked215','targeted10'],default='locked215')
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    archive_path=SOURCE/'pre_post_all_windows.npz';archive=np.load(archive_path,allow_pickle=False)
    after=archive['after'];before=archive['before'];change=archive['change']
    records=read_csv(SOURCE/'selected_unit_pre_post.csv')
    assert np.array_equal(archive['recording_id'],np.array([r['recording_id'] for r in records]))
    assert np.array_equal(archive['unit_id'],np.array([r['unit_id'] for r in records]))
    assert np.allclose(after-before,change,equal_nan=True)
    y=np.array([base.CLASSES.index(c) for c in archive['construct']])
    previous=json.loads((SOURCE/'summary.json').read_text());selected=previous['selected_conditions']
    stats=read_csv(SOURCE/'selected_control_tests.csv')
    for r in stats:
        for k in ['mean_holm_p','group_n','control_n','cliff_delta','cliff_ci_low','cliff_ci_high']:
            r[k]=float(r[k])
    if args.lda_input=='locked215':coordinates,lda_info=locked_lda(records)
    else:coordinates,lda_info=targeted_lda(after,change,selected,y)
    targeted_names=[n+'_post' for n in post.METRICS]+[n+'_change' for n in post.METRICS]
    targeted=matrix_at_windows(after,change,[r['window_index'] for r in selected])
    for j,name in enumerate(targeted_names):
        exported=np.array([float(r[name]) for r in records])
        assert np.allclose(targeted[:,j],exported,equal_nan=True)
    registry=dict(status='targeted_phenotype_registry',scope='Actuators + effectors',unit_is_observation=True,
        pool_sua_mua=True,event='first STG train, t=0',unit_key=['recording_id','unit_id'],units=len(records),
        phenotype_names=post.METRICS,post_window_selection='Maximize weakest absolute Cliff delta versus 371 Control across DREADD/LMO/PSAM',
        selected_conditions=selected,paired_baseline='Mirror post [a,b) to pre [-b,-a)',
        raw_targeted_feature_names=targeted_names,targeted_feature_count=10,
        targeted_data_table=str(SOURCE/'selected_unit_pre_post.csv'),
        targeted_data_sha256=sha(SOURCE/'selected_unit_pre_post.csv'),
        figure_lda_mode=args.lda_input,figure_lda_inputs=lda_info['feature_count'],
        active_215_model_replaced=False,
        fractions='Raw fractions 0-1; display post percentages and change percentage points',
        definitions={'firing_rate':'spikes divided by interval duration, Hz',
            'burst_spike_fraction':'spikes in maximal consecutive-ISI clusters <=25 ms with >=3 spikes, divided by all spikes; no-spike units=0',
            'active_1s_fraction':'fraction of complete 1-second bins containing >=1 spike; undefined for intervals <1 s',
            'short_isi_fraction':'fraction of adjacent ISIs <50 ms; >=2 spikes required',
            'long_pause_fraction':'fraction of adjacent ISIs >200 ms; >=2 spikes required'},
        mean_sem='Mean and SD/sqrt(n) across finite unit values; no missing ISIs imputed in descriptive plots',
        effects='Cliff delta = P(group > Control)-P(group < Control); separate for post values and paired changes',
        intervals='Saved pointwise 95% percentile unit-bootstrap intervals, 2000 resamples, not adjusted for selection',
        stars='Previously saved Welch mean tests versus Control; Holm over 4111 previous/current hypotheses')
    registry_path=OUT/'mcs_targeted_poststim_metrics.json'
    registry_path.write_text(json.dumps(registry,indent=2)+'\n')
    fig=plt.figure(figsize=(17,15))
    outer=fig.add_gridspec(3,1,height_ratios=[1,1,1.5],hspace=1.05,left=.06,right=.98,top=.90,bottom=.105)
    axes=np.empty((2,5),dtype=object)
    for row in range(2):
        grid=outer[row].subgridspec(1,5,wspace=.55)
        for col in range(5):axes[row,col]=fig.add_subplot(grid[0,col])
    post.draw_metric_panels(axes,y,selected,after,change,stats)
    bottom=outer[2].subgridspec(1,3,width_ratios=[1,1,1.2],wspace=.62)
    ax_post=fig.add_subplot(bottom[0,0]);ax_change=fig.add_subplot(bottom[0,1]);ax_lda=fig.add_subplot(bottom[0,2])
    # Reserve room for the complete metric/construct labels on the left forest.
    position=ax_post.get_position()
    ax_post.set_position([position.x0+.03,position.y0,position.width-.03,position.height])
    effect_post=forest(ax_post,stats,'post','k');effect_change=forest(ax_change,stats,'change','l')
    for c,label in enumerate(base.CLASSES):
        points=coordinates[y==c]
        ax_lda.scatter(points[:,0],points[:,1],color=COLORS[c],s=6,alpha=.35,linewidths=0,rasterized=True,
                       label=f'{label}: {len(points)} units')
        vals,vecs=np.linalg.eigh(np.cov(points.T))
        ax_lda.add_patch(Ellipse(points.mean(axis=0),2*np.sqrt(max(vals[-1],0)),2*np.sqrt(max(vals[0],0)),
            angle=np.degrees(np.arctan2(vecs[1,-1],vecs[0,-1])),facecolor=COLORS[c],edgecolor=COLORS[c],alpha=.12))
    for c,label in enumerate(base.CLASSES):
        mask=y==c
        for recording in np.unique(archive['recording_id'][mask]):
            center=coordinates[archive['recording_id']==recording].mean(axis=0)
            ax_lda.scatter(*center,s=24,color=COLORS[c],linewidths=0,zorder=5)
        dark=tuple(np.array(matplotlib.colors.to_rgb(COLORS[c]))*.55)
        ax_lda.scatter(*coordinates[mask].mean(axis=0),s=65,color=dark,edgecolor='#111111',lw=1,zorder=10)
    ax_lda.axhline(0,color='gray',ls='--',lw=.5);ax_lda.axvline(0,color='gray',ls='--',lw=.5)
    title='Locked 215-input LDA' if args.lda_input=='locked215' else 'Targeted 10-input LDA'
    ax_lda.set_title(title+'\nEach dot = one unit',fontsize=10,pad=12)
    ax_lda.set_xlabel('LD1',fontsize=9);ax_lda.set_ylabel('LD2',fontsize=9)
    ax_lda.legend(frameon=False,fontsize=6.5,loc='best');ax_lda.spines[['top','right']].set_visible(False)
    ax_lda.text(-.12,1.09,'m',transform=ax_lda.transAxes,fontweight='bold',fontsize=13)
    fig.suptitle('Actuators + effectors: targeted phenotypes, effect sizes and LDA',fontsize=16,y=.985)
    lda_caption=('LDA is the unchanged frozen 87-original + 128-burst model; the five plotted phenotypes are not its complete input list.'
                 if args.lda_input=='locked215' else 'LDA uses the exact five plotted post levels plus five paired changes; supervised full-data fit.')
    fig.text(.5,.025,'Rows 1–2 reuse the existing post values, paired changes, unit counts and statistics. Dots = units; black = mean ± SEM; SUA/MUA pooled.\n'
        'Stars = saved Welch/Control tests, Holm over 4,111 hypotheses. k/l: saved Cliff δ ± pointwise 95% unit-bootstrap CI (not selection-adjusted).\n'
        'Positive effect = higher post level or larger paired change than Control; negative = lower level or smaller change, not necessarily a decrease from baseline.\n'
        +lda_caption+' Ellipses = 1-SD unit spread, not confidence intervals.\n'
        'ISI missing values remain missing in metric panels; LDA uses median imputation. Stimulation artifacts remain included. Panel sources are recorded in the manifest.',
        ha='center',fontsize=7)
    png=OUT/'targeted_poststim_effects_lda.png';pdf=OUT/'targeted_poststim_effects_lda.pdf'
    fig.savefig(png,dpi=300);fig.savefig(pdf,dpi=300);plt.close(fig)
    coordinate_rows=[dict(recording_id=r['recording_id'],unit_id=r['unit_id'],construct=r['construct'],
        LD1=float(coordinates[i,0]),LD2=float(coordinates[i,1]),lda_mode=args.lda_input) for i,r in enumerate(records)]
    base.write_csv(OUT/'lda_unit_coordinates.csv',coordinate_rows)
    source_paths=[archive_path,SOURCE/'selected_conditions.csv',SOURCE/'selected_control_tests.csv',
        SOURCE/'unit_mean_sem_and_paired_tests.csv',SOURCE/'selected_unit_pre_post.csv',SOURCE/'summary.json']
    manifest=dict(units=len(records),unit_key=['recording_id','unit_id'],source_directory=str(SOURCE),
        source_files=[dict(path=str(p),sha256=sha(p)) for p in source_paths],targeted_registry=str(registry_path),
        targeted_registry_sha256=sha(registry_path),lda=lda_info,
        panels={
            'a-e':dict(source=str(archive_path),array='after',conditions=str(SOURCE/'selected_conditions.csv'),computation='Same renderer and finite-unit mean/SEM as existing figure'),
            'f-j':dict(source=str(archive_path),array='change',computation='Same unit post minus mirrored pre; same selected conditions'),
            'k':dict(source=str(SOURCE/'selected_control_tests.csv'),row_filter='mode=post',values=['cliff_delta','cliff_ci_low','cliff_ci_high']),
            'l':dict(source=str(SOURCE/'selected_control_tests.csv'),row_filter='mode=change',values=['cliff_delta','cliff_ci_low','cliff_ci_high']),
            'm':dict(computation=lda_info,coordinates=str(OUT/'lda_unit_coordinates.csv'))},
        output_files=[dict(path=str(p),sha256=sha(p)) for p in [png,pdf,OUT/'lda_unit_coordinates.csv']],
        code_files=[dict(path=str(p),sha256=sha(p)) for p in [Path(__file__),Path(post.__file__)]],
        numerics_recomputed=False,lda_retrained=args.lda_input=='targeted10',active_215_model_changed=False)
    (OUT/'figure_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('COMPLETE',png,'LDA',args.lda_input,'units',len(records),flush=True)

if __name__=='__main__':
    main()
