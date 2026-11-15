"""Freeze selected metrics/model; one illustrative e-stim channel/unit delta figure."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import SymLogNorm
import numpy as np
import spikeinterface as si
from spikeinterface.core import get_template_extremum_channel
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

import explore_mcs_actuator_separation as base
from load_mcs_locked_lda import load_units,project_units

REPO=base.REPO
OUT=Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis')
LOCK=OUT/'locked_lda_215'
CONFIG=REPO/'metadata/mcs_active_lda_configuration.json'

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def freeze(rows):
    LOCK.mkdir(parents=True,exist_ok=True)
    config=json.loads(CONFIG.read_text())
    names=config['original_features']+config['new_burst_features']
    assert len(names)==len(set(names))==215
    source=base.OUT/'burst_lda/burst_metrics.npz'
    new=np.load(source,allow_pickle=False)
    assert np.array_equal(new['recording_id'],np.array([r['recording_id'] for r in rows]))
    assert np.array_equal(new['unit_id'],np.array([r['unit_id'] for r in rows]))
    lookup={n:i for i,n in enumerate(new['names'])}
    added_values=new['values']
    original_values=np.array([[float(r[n]) for n in config['original_features']] for r in rows])
    added_columns=[lookup[n] for n in config['new_burst_features']]
    raw=np.column_stack([original_values,added_values[:,added_columns]])
    metadata=['recording_id','unit_id','construct','kslabel','event_time_s','duration_s']
    table=LOCK/'active_215_unit_metrics.csv.gz'
    with gzip.open(table,'wt',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(metadata+names)
        for row,values in zip(rows,raw):
            writer.writerow([row[k] for k in metadata]+values.tolist())
    x=np.sign(raw)*np.log1p(np.abs(raw))
    imputer=SimpleImputer(strategy='median',keep_empty_features=True)
    filled=imputer.fit_transform(x)
    scaler=StandardScaler().fit(filled)
    z=scaler.transform(filled)
    target=np.array([base.CLASSES.index(r['construct']) for r in rows])
    lda=LinearDiscriminantAnalysis(solver='eigen',shrinkage=config['fitted_configuration'][1],n_components=2).fit(z,target)
    model=LOCK/'active_215_lda_state.npz'
    np.savez_compressed(model,feature_names=np.array(names),impute_median=imputer.statistics_,
        scale_mean=scaler.mean_,scale_std=scaler.scale_,lda_projection=lda.scalings_[:,:2],
        lda_coef=lda.coef_,lda_intercept=lda.intercept_,
        class_labels=np.array([base.CLASSES[int(c)] for c in lda.classes_]))
    config.update(frozen_raw_metrics_csv=str(table),frozen_raw_metrics_sha256=digest(table),
                  frozen_model_npz=str(model),frozen_model_sha256=digest(model),frozen_units=len(rows),
                  fitted_model_status='Descriptive full-data LDA; use saved transforms without feature reselection',
                  metric_loader=str(REPO/'scripts/load_mcs_locked_lda.py'),
                  source_original_metrics=str(base.OUT/'unit_metrics.csv'),
                  source_original_metrics_sha256=digest(base.OUT/'unit_metrics.csv'),
                  source_added_metrics=str(source),source_added_metrics_sha256=digest(source))
    CONFIG.write_text(json.dumps(config,indent=2)+'\n')
    (LOCK/'manifest.json').write_text(json.dumps(config,indent=2)+'\n')
    meta,values=load_units()
    coords,labels=project_units(values)
    assert values.shape==(1554,215) and np.allclose(values.to_numpy(),raw,equal_nan=True)
    assert np.allclose(coords,lda.transform(z))
    assert np.array_equal(labels,np.array([base.CLASSES[int(c)] for c in lda.predict(z)]))
    print('Frozen raw metrics and model round-trip verified.',flush=True)

def heatmap(rows):
    records=list(csv.DictReader((REPO/'metadata/mcs_recording_biology.csv').open()))
    eligible={r['recording_id'] for r in rows}
    units_by_recording={}
    for r in rows:
        units_by_recording.setdefault(r['recording_id'],[]).append(r)
    selected=[];export=[];all_values=[]
    for construct in ['DREADD','LMO','PSAM','Control']:
        candidates=[r for r in records if r['recording_id'] in eligible and r['construct']==construct]
        candidates.sort(key=lambda r:(-int(r['total_units']),r['recording_id']))
        record=candidates[0]
        result=Path(record['sorting_output_path'])
        analyzers=list((result/'postprocessed').glob('*.zarr'))
        assert len(analyzers)==1
        analyzer=si.load_sorting_analyzer(analyzers[0],load_extensions=False)
        peak=get_template_extremum_channel(analyzer,peak_sign='neg',outputs='index')
        peak={str(k):int(v) for k,v in peak.items()}
        channel_path=result/'repro/mcs_input/channels.csv'
        channels=sorted(csv.DictReader(channel_path.open()),key=lambda r:int(r['binary_channel_index']))
        positions=np.array([[float(r['x_um']),float(r['y_um'])] for r in channels])
        assert len(channels)==len(analyzer.channel_ids)
        assert np.array_equal(np.asarray(analyzer.channel_ids),np.arange(len(channels)))
        assert np.allclose(positions,analyzer.get_channel_locations()[:,:2])
        units=units_by_recording[record['recording_id']]
        assert set(peak)=={r['unit_id'] for r in units}
        values=np.array([[float(r['rate__post5'])-float(r['rate__pre5']),
                          float(r['rate__post10'])-float(r['rate__pre10'])] for r in units])
        assignment=np.array([peak[r['unit_id']] for r in units])
        labels=[channels[index]['channel_label'] for index in assignment]
        order=sorted(range(len(units)),key=lambda i:(int(labels[i]),int(units[i]['unit_id'])))
        means=np.full((len(channels),2),np.nan)
        for index in range(len(channels)):
            if np.any(assignment==index):means[index]=values[assignment==index].mean(axis=0)
        manifest=json.loads((result/'repro/mcs_input/mcs_recording_manifest.json').read_text())
        selected.append(dict(construct=construct,record=record,channels=channels,positions=positions,
            units=units,values=values,assignment=assignment,order=order,means=means,
            analyzer_path=str(analyzers[0]),geometry_status=manifest['geometry_status']))
        all_values.extend(values.ravel())
        for i,r in enumerate(units):
            export.append(dict(recording_id=record['recording_id'],construct=construct,unit_id=r['unit_id'],
                peak_channel_label=labels[i],peak_binary_channel_index=assignment[i],
                pre5_hz=float(r['rate__pre5']),post5_hz=float(r['rate__post5']),delta5_hz=values[i,0],
                pre10_hz=float(r['rate__pre10']),post10_hz=float(r['rate__post10']),delta10_hz=values[i,1]))
        print(construct,record['recording_id'],'units',len(units),'mean delta',values.mean(axis=0).tolist(),flush=True)
    limit=max(1.,float(np.max(np.abs(all_values))))
    norm=SymLogNorm(linthresh=1,vmin=-limit,vmax=limit,base=10)
    cmap=plt.get_cmap('RdBu_r').copy();cmap.set_bad('#dddddd')
    fig,axes=plt.subplots(4,3,figsize=(12,14),gridspec_kw={'width_ratios':[1,1,1.2]})
    image=None
    for row,item in enumerate(selected):
        x=np.unique(item['positions'][:,0]);y=np.unique(item['positions'][:,1])
        for window in range(2):
            grid=np.full((len(y),len(x)),np.nan)
            for i,channel in enumerate(item['channels']):
                ix=int(np.where(x==item['positions'][i,0])[0][0]);iy=int(np.where(y==item['positions'][i,1])[0][0])
                grid[iy,ix]=item['means'][i,window]
            ax=axes[row,window]
            image=ax.imshow(grid,origin='lower',cmap=cmap,norm=norm,interpolation='nearest')
            for i,channel in enumerate(item['channels']):
                ix=int(np.where(x==item['positions'][i,0])[0][0]);iy=int(np.where(y==item['positions'][i,1])[0][0])
                ax.text(ix,iy,channel['channel_label'],ha='center',va='center',fontsize=6,
                        color='black',bbox=dict(facecolor='white',edgecolor='none',alpha=.55,pad=.15))
            ax.set_xticks([]);ax.set_yticks([])
            ax.set_title(('5-s' if window==0 else '10-s')+' channel mean ΔHz/unit',fontsize=10)
            if window==0:
                r=item['record'];ax.set_ylabel(f"{item['construct']} | {r['stim_label']} / {r['sample_label']}\n{len(item['units'])} units",fontsize=10)
        ax=axes[row,2]
        ordered=item['values'][item['order']]
        ax.imshow(ordered,aspect='auto',cmap=cmap,norm=norm,interpolation='nearest')
        ticks=[];ticklabels=[]
        ordered_labels=[item['channels'][item['assignment'][i]]['channel_label'] for i in item['order']]
        for label in dict.fromkeys(ordered_labels):
            indices=[i for i,l in enumerate(ordered_labels) if l==label]
            ticks.append(float(np.mean(indices)));ticklabels.append(label)
            ax.axhline(indices[-1]+.5,color='white',lw=.35)
        ax.set_yticks(ticks,ticklabels,fontsize=5)
        ax.set_ylabel('Peak channel; one row per unit',fontsize=8)
        ax.set_xticks([0,1],['5 s','10 s'])
        ax.set_title('Individual-unit ΔHz',fontsize=10)
    fig.suptitle('Actuators + effectors: e-stim post-minus-pre firing-rate maps',fontsize=15,y=.985)
    fig.subplots_adjust(left=.10,right=.88,top=.95,bottom=.09,hspace=.32,wspace=.40)
    cax=fig.add_axes([.91,.17,.017,.64])
    fig.colorbar(image,cax=cax,label='ΔHz/unit; linear within ±1 Hz, logarithmic beyond')
    fig.text(.5,.025,'First STG train = t0. 5 s: [0,+5) − [−5,0); 10 s: [0,+10) − [−10,0). SUA/MUA pooled.\n'
        'Channel = most-negative template channel; channel color = mean unit delta. Gray = no assigned units.\n'
        'One recording per construct, selected by largest unit count, not response. Channel-label grid; physical spacing unverified in some recordings.\n'
        'These are illustrative recordings, not group averages or evidence of chemical-treatment causation. Stimulation artifacts remain included.',
        ha='center',fontsize=8)
    destination=OUT/'estim_channel_unit_delta_heatmap.png'
    fig.savefig(destination,dpi=150);plt.close(fig)
    base.write_csv(OUT/'estim_channel_unit_deltas.csv',export)
    provenance=dict(selection='Largest completed unit count per construct in the existing 29-recording STG analysis; recording_id breaks ties',
                    channel_assignment='Most negative average saved template channel',channel_aggregation='Mean delta across assigned units',
                    windows={'5s':{'pre':[-5,0],'post':[0,5]},'10s':{'pre':[-10,0],'post':[0,10]}},
                    color='Common symmetric log normalization; linear within +/-1 Hz; no clipping',
                    recordings=[dict(construct=i['construct'],recording_id=i['record']['recording_id'],
                    sorting_output=i['record']['sorting_output_path'],analyzer=i['analyzer_path'],units=len(i['units']),
                    geometry_status=i['geometry_status'],mean_delta_5s=float(i['values'][:,0].mean()),
                    mean_delta_10s=float(i['values'][:,1].mean())) for i in selected])
    (OUT/'estim_channel_unit_delta_provenance.json').write_text(json.dumps(provenance,indent=2))
    print('Saved',destination,destination.stat().st_size,flush=True)

def main():
    rows=list(csv.DictReader((base.OUT/'unit_metrics.csv').open()))
    freeze(rows)
    heatmap(rows)

if __name__=='__main__':
    main()
