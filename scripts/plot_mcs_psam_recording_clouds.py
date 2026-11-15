"""Separate the five PSAM recording clouds without changing frozen LD coordinates."""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import to_rgb
from compose_mcs_paper_layout import OUT,GROUPS,GROUP_COLORS,unit_spread_outline

def main():
    source=OUT/'unit_lda_coordinates.csv';units=pd.read_csv(source,dtype={'unit_id':str})
    psam=units[units['construct']=='PSAM'];assert len(psam)==339 and psam['recording_id'].nunique()==5
    colors=['#0072B2','#E69F00','#009E73','#CC79A7','#D55E00']
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42})
    fig,axes=plt.subplots(1,2,figsize=(12,6))
    parameters=[];recording_table=[];handles=[]
    for g,color in zip(GROUPS,GROUP_COLORS):
        v=units[units['construct']==g];xy=v[['LD1','LD2']].to_numpy()
        axes[0].scatter(*xy.T,s=5,color=color,alpha=.25,lw=0,rasterized=True)
        params=unit_spread_outline(axes[0],xy,color,lw=1.2);parameters.append(dict(scope='group',label=g,**params))
        for rid,r in v.groupby('recording_id',sort=False):
            center=r[['LD1','LD2']].mean().to_numpy()
            axes[0].scatter(*center,s=35,facecolor=color,edgecolor='none',lw=0,zorder=4)
        center=xy.mean(axis=0)
        axes[0].scatter(*center,s=80,color=np.array(to_rgb(color))*.55,edgecolor='black',lw=1.2,zorder=5)
    for i,((rid,record),color) in enumerate(zip(psam.groupby('recording_id',sort=False),colors),1):
        xy=record[['LD1','LD2']].to_numpy();parts=rid.split('/');name=f'{parts[1]} / {parts[2]}'
        axes[1].scatter(*xy.T,s=12,color=color,alpha=.55,lw=0,rasterized=True)
        params=unit_spread_outline(axes[1],xy,color,lw=1.5)
        axes[1].scatter(params['LD1'],params['LD2'],s=75,facecolor=color,edgecolor='none',lw=0,zorder=5)
        parameters.append(dict(scope='PSAM recording',label=name,**params))
        recording_table.append(dict(recording_id=rid,label=name,construct='PSAM',color=color,**params))
        handles.append(Line2D([],[],marker='o',ls='-',color=color,markerfacecolor=color,markeredgewidth=1.5,
                              label=f'{name} ({len(record)} units)'))
    center=psam[['LD1','LD2']].mean().to_numpy()
    axes[1].scatter(*center,s=95,color='#3f255d',edgecolor='black',lw=1.4,zorder=6)
    axes[0].set_title('All groups: units, recordings, and group outlines')
    axes[1].set_title('PSAM: five individual recording clouds')
    axes[0].legend(handles=[Line2D([],[],marker='.',ls='none',color='#888888',label='Individual unit'),
                  Line2D([],[],marker='o',ls='none',markerfacecolor='#777777',color='#777777',label='Recording centroid'),
                  Line2D([],[],marker='o',ls='none',markerfacecolor='#333333',color='black',label='Group centroid')],
                  frameon=False,fontsize=8,loc='upper left')
    for i,ax in enumerate(axes):
        ax.set(xlabel='LD1',ylabel='LD2');ax.spines[['top','right']].set_visible(False)
        ax.axhline(0,color='#eeeeee',lw=.7,zorder=0);ax.axvline(0,color='#eeeeee',lw=.7,zorder=0)
        ax.text(-.10,1.06,chr(97+i),transform=ax.transAxes,fontweight='bold',fontsize=13)
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.52,.07),ncol=3,frameon=False,fontsize=8)
    fig.suptitle('Recording clouds in the unchanged 215-metric LDA',fontsize=14,y=.98)
    fig.text(.5,.015,'Dots = units; solid colored circles = recording means; dark filled circles = group means.\n'
             'Ellipses show two-SD covariance contours of unit spread, not confidence intervals. Overlap is retained.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.22,1,.93))
    for suffix in ['png','pdf']:fig.savefig(OUT/f'psam_individual_recording_clouds.{suffix}',dpi=330,bbox_inches='tight',facecolor='white')
    plt.close(fig)
    pd.DataFrame(recording_table).to_csv(OUT/'psam_recording_cloud_definitions.csv',index=False)
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    manifest=dict(units=1554,psam_units=339,psam_recordings=5,coordinates_changed=False,
                  outlines='Covariance ellipse with radius 2 standard deviations on each principal axis; not CI',
                  parameters=parameters)
    manifest['sources']={str(p):sha(p) for p in [source,OUT/'recording_lda_centroids.csv',__file__]}
    manifest['outputs']={n:sha(OUT/n) for n in ['psam_individual_recording_clouds.png','psam_individual_recording_clouds.pdf','psam_recording_cloud_definitions.csv']}
    (OUT/'psam_recording_cloud_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('COMPLETE PSAM recording clouds',flush=True)

if __name__=='__main__':main()
