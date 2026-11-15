"""Three-axis extension of the frozen 215-feature LDA; preserve locked LD1/LD2."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from load_mcs_locked_lda import load_units,project_units,CONFIG

ROOT=Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis')
OUT=ROOT/'lda_3d'
GROUPS=['Control','DREADD','LMO','PSAM']
COLORS=['#777777','#e94b47','#64af54','#9462d5']
RECORD_COLORS=['#0072B2','#E69F00','#009E73','#CC79A7','#D55E00']

def ellipsoid(points):
    values,vectors=np.linalg.eigh(np.cov(points.T,ddof=1))
    radii=2*np.sqrt(np.maximum(values,0))
    u=np.linspace(0,2*np.pi,25);v=np.linspace(0,np.pi,13)
    sphere=np.stack([np.outer(np.cos(u),np.sin(v)),np.outer(np.sin(u),np.sin(v)),
                     np.outer(np.ones_like(u),np.cos(v))],axis=-1)
    xyz=(sphere*radii)@vectors.T+points.mean(axis=0)
    wires=[xyz[i].tolist() for i in range(0,25,6)]+[xyz[:,j].tolist() for j in [3,6,9]]
    return xyz,wires,dict(center=points.mean(axis=0).tolist(),radii_2sd=radii.tolist(),eigenvectors=vectors.tolist())

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    config=json.loads(CONFIG.read_text());meta,raw=load_units();old,_=project_units(raw)
    state=np.load(config['frozen_model_npz'],allow_pickle=False)
    x=raw[state['feature_names'].tolist()].to_numpy(float)
    x=np.sign(x)*np.log1p(np.abs(x));x=np.where(np.isnan(x),state['impute_median'],x)
    z=(x-state['scale_mean'])/state['scale_std']
    y=np.array([GROUPS.index(g) for g in meta['construct']])
    fitted=LinearDiscriminantAnalysis(solver='eigen',shrinkage=.01,n_components=3).fit(z,y)
    new_projection=fitted.scalings_[:,:3].copy();refit=z@new_projection
    alignment=[]
    for axis in range(2):
        sign=1 if np.dot(refit[:,axis],old[:,axis])>=0 else -1
        new_projection[:,axis]*=sign;refit[:,axis]*=sign
        alignment.append(dict(axis=axis+1,sign=sign,max_absolute_error=float(np.max(np.abs(refit[:,axis]-old[:,axis])))))
        assert np.allclose(refit[:,axis],old[:,axis],atol=1e-7,rtol=1e-7),alignment
    # Retain the original two projection columns exactly; append only the new LD3.
    projection=np.column_stack([state['lda_projection'],new_projection[:,2]])
    coordinates=np.column_stack([old,z@projection[:,2]])
    assert np.array_equal(coordinates[:,:2],old) and np.allclose(z@projection,coordinates,atol=1e-12)
    units=meta[['recording_id','unit_id','construct']].copy()
    units[['LD1','LD2','LD3']]=coordinates
    units.to_csv(OUT/'unit_ld1_ld2_ld3.csv',index=False)
    centroids=units.groupby(['construct','recording_id'],sort=False).agg(n_units=('unit_id','size'),
                    LD1=('LD1','mean'),LD2=('LD2','mean'),LD3=('LD3','mean')).reset_index()
    assert len(centroids)==29
    centroids.to_csv(OUT/'recording_centroids_3d.csv',index=False)
    units.groupby('construct',sort=False).agg(n_units=('unit_id','size'),LD1=('LD1','mean'),
                    LD2=('LD2','mean'),LD3=('LD3','mean')).reset_index().to_csv(OUT/'group_centroids_3d.csv',index=False)
    np.savez_compressed(OUT/'extension_215_lda_state.npz',feature_names=state['feature_names'],
                       impute_median=state['impute_median'],scale_mean=state['scale_mean'],
                       scale_std=state['scale_std'],lda_projection=projection)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'pdf.fonttype':42})
    fig=plt.figure(figsize=(13,6.2));axes=[fig.add_subplot(1,2,i+1,projection='3d',computed_zorder=False) for i in range(2)]
    all_wires=[];psam_wires=[];ellipse_definitions=[]
    for c,g in enumerate(GROUPS):
        selected=units[units['construct']==g];p=selected[['LD1','LD2','LD3']].to_numpy()
        axes[0].scatter(*p.T,s=4,color=COLORS[c],alpha=.25,depthshade=False,rasterized=True,linewidths=0,zorder=2)
        surface,wires,definition=ellipsoid(p)
        axes[0].plot_wireframe(surface[:,:,0],surface[:,:,1],surface[:,:,2],rstride=6,cstride=4,
                               color=COLORS[c],lw=.45,alpha=.3,zorder=1)
        all_wires.append(dict(color=COLORS[c],lines=wires));ellipse_definitions.append(dict(scope='group',label=g,**definition))
        for _,r in centroids[centroids['construct']==g].iterrows():
            axes[0].scatter(r['LD1'],r['LD2'],r['LD3'],s=35,color=COLORS[c],linewidths=0,depthshade=False,zorder=20)
        axes[0].scatter(*p.mean(axis=0),s=80,color=np.array(to_rgb(COLORS[c]))*.55,edgecolor='black',lw=1.1,depthshade=False,zorder=100)
    psam=units[units['construct']=='PSAM'];record_map={};record_handles=[]
    for (rid,record),color in zip(psam.groupby('recording_id',sort=False),RECORD_COLORS):
        parts=rid.split('/');label=f'{parts[1]} / {parts[2]}';record_map[rid]=dict(color=color,label=label)
        p=record[['LD1','LD2','LD3']].to_numpy()
        axes[1].scatter(*p.T,s=9,color=color,alpha=.5,depthshade=False,rasterized=True,linewidths=0,zorder=2)
        surface,wires,definition=ellipsoid(p)
        axes[1].plot_wireframe(surface[:,:,0],surface[:,:,1],surface[:,:,2],rstride=6,cstride=4,color=color,lw=.55,alpha=.3,zorder=1)
        axes[1].scatter(*p.mean(axis=0),s=65,color=color,linewidths=0,depthshade=False,zorder=20)
        psam_wires.append(dict(color=color,lines=wires));ellipse_definitions.append(dict(scope='PSAM recording',label=label,**definition))
        record_handles.append(Line2D([],[],marker='o',color=color,markerfacecolor=color,label=f'{label} ({len(record)} units)'))
    axes[1].scatter(*psam[['LD1','LD2','LD3']].mean().to_numpy(),s=85,color='#3f255d',edgecolor='black',lw=1.2,depthshade=False,zorder=100)
    for i,ax in enumerate(axes):
        ax.set(xlabel='LD1',ylabel='LD2',zlabel='');ax.view_init(elev=23,azim=-58)
        ax.text2D(.96,.55,'LD3',transform=ax.transAxes,fontsize=9)
        ax.set_box_aspect((1,1,1));ax.tick_params(labelsize=7,pad=0)
        for axis in [ax.xaxis,ax.yaxis,ax.zaxis]:
            axis.set_major_locator(MaxNLocator(nbins=3))
            axis._axinfo['grid'].update(color='#dddddd',linewidth=.5)
        for pane in [ax.xaxis.pane,ax.yaxis.pane,ax.zaxis.pane]:pane.set_facecolor('white')
        ax.text2D(.02,.95,chr(97+i),transform=ax.transAxes,fontweight='bold',fontsize=13)
    axes[0].set_title('All units and recording centroids',pad=12)
    axes[0].legend(handles=[Line2D([],[],marker='.',ls='none',color=color,label=g) for g,color in zip(GROUPS,COLORS)],
                   loc='upper left',bbox_to_anchor=(0,.88),frameon=False,fontsize=7)
    axes[1].set_title('PSAM: five recording clouds',pad=12)
    fig.legend(handles=[Line2D([],[],marker='.',ls='none',color='#888888',label='Unit'),
              Line2D([],[],marker='o',ls='none',color='#777777',markerfacecolor='#777777',label='Recording centroid'),
              Line2D([],[],marker='o',ls='none',color='black',markerfacecolor='#333333',label='Group centroid')],
              loc='upper center',bbox_to_anchor=(.50,.92),ncol=3,frameon=False,fontsize=8)
    fig.legend(handles=record_handles,loc='lower center',bbox_to_anchor=(.52,.065),ncol=3,frameon=False,fontsize=8)
    fig.suptitle('Actuators + effectors in LD1–LD2–LD3 space',fontsize=14,y=.99)
    fig.text(.5,.015,'Same 215 metrics and frozen preprocessing. Original LD1/LD2 retained exactly; LD3 added from a matched three-axis fit.\n'
             'Dots = units; circles = centroids. Wireframes = two-SD covariance ellipsoids of unit spread, not confidence intervals.',ha='center',fontsize=7)
    fig.subplots_adjust(left=.025,right=.975,bottom=.24,top=.84,wspace=.04)
    for ext in ['png','pdf']:fig.savefig(OUT/f'lda_215_3d_recordings.{ext}',dpi=330,facecolor='white',bbox_inches='tight')
    plt.close(fig)
    # Self-contained rotatable view; no external libraries, network, or server needed.
    points=[]
    for _,r in units.iterrows():points.append(dict(p=[r['LD1'],r['LD2'],r['LD3']],g=GROUPS.index(r['construct']),r=r['recording_id']))
    recording_points=[dict(p=[r['LD1'],r['LD2'],r['LD3']],g=GROUPS.index(r['construct']),r=r['recording_id']) for _,r in centroids.iterrows()]
    group_points=[dict(p=units[units['construct']==g][['LD1','LD2','LD3']].mean().tolist(),g=c) for c,g in enumerate(GROUPS)]
    payload=dict(points=points,records=recording_points,groups=group_points,colors=COLORS,
                 names=GROUPS,recordMap=record_map,wires=[all_wires,psam_wires])
    html='''<!doctype html><meta charset="utf-8"><title>3D unit and recording LDA</title>
<style>body{font:15px system-ui;margin:24px;color:#222}h1{font-size:22px}.views{display:flex;gap:16px}section{width:50%;border:1px solid #ddd;border-radius:8px;padding:8px}canvas{width:100%;height:520px;touch-action:none}button{margin:6px;padding:7px 14px}.legend{line-height:1.8;font-size:13px}small{color:#555}</style>
<h1>LD1–LD2–LD3: units, recordings and cloud outlines</h1><p>Drag either view to rotate; scroll to zoom. <button id="reset">Reset view</button> <label><input id="wire" type="checkbox" checked>Cloud outlines</label></p>
<div class="views"><section><h3>All groups · 1,554 units · 29 recordings</h3><canvas id="all"></canvas><div id="legend0" class="legend"></div></section><section><h3>PSAM · 339 units · five recordings</h3><canvas id="psam"></canvas><div id="legend1" class="legend"></div></section></div>
<p><small>Small dots: units. Solid colored circles: recording centroids. Large dark circles: group centroids, always drawn on top. Outlines: two-SD unit-spread ellipsoids, not confidence intervals. This descriptive full-data LDA uses the same 215 metrics. LD1/LD2 are unchanged; LD3 is a separately saved extension.</small></p>
<script>const D=PAYLOAD;
const state={az:-.9,el:.4,zoom:1};
function draw(canvas,index){let box=canvas.getBoundingClientRect(),ratio=devicePixelRatio||1,w=box.width,h=box.height;canvas.width=w*ratio;canvas.height=h*ratio;let ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.clearRect(0,0,w,h);
let pts=D.points.filter(p=>index===0||p.g===3),recs=D.records.filter(p=>index===0||p.g===3),groups=D.groups.filter(p=>index===0||p.g===3),center=[0,0,0],lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];pts.forEach(v=>v.p.forEach((a,j)=>{lo[j]=Math.min(lo[j],a);hi[j]=Math.max(hi[j],a)}));center=lo.map((a,j)=>(a+hi[j])/2);let span=Math.max(...hi.map((a,j)=>a-lo[j])),scale=Math.min(w,h)*.65/span*state.zoom;
function project(p){let [x,y,z]=p.map((a,j)=>a-center[j]),a=Math.cos(state.az),b=Math.sin(state.az),c=Math.cos(state.el),d=Math.sin(state.el),xx=a*x-b*y,yy=b*x+a*y;return [w/2+scale*xx,h/2-scale*(c*z-d*yy),c*yy+d*z]}
function line(points,color,width,alpha){ctx.beginPath();points.forEach((p,i)=>{let v=project(p);i?ctx.lineTo(v[0],v[1]):ctx.moveTo(v[0],v[1])});ctx.strokeStyle=color;ctx.lineWidth=width;ctx.globalAlpha=alpha;ctx.stroke();ctx.globalAlpha=1}
if(document.getElementById('wire').checked)D.wires[index].forEach(o=>o.lines.forEach(v=>line(v,o.color,.7,.30)));
for(let j=0;j<3;j++){let start=center.slice(),end=center.slice();start[j]=lo[j];end[j]=hi[j];line([start,end],'#aaa',1,.7);let v=project(end);ctx.fillStyle='#222';ctx.font='13px system-ui';ctx.fillText('LD'+(j+1),v[0]+5,v[1]-5)}
pts.map(p=>({v:project(p.p),p})).sort((a,b)=>a.v[2]-b.v[2]).forEach(o=>{ctx.beginPath();ctx.arc(o.v[0],o.v[1],index===0?1.5:2.5,0,Math.PI*2);ctx.fillStyle=index===0?D.colors[o.p.g]:D.recordMap[o.p.r].color;ctx.globalAlpha=.45;ctx.fill();ctx.globalAlpha=1});
recs.forEach(p=>{let v=project(p.p);ctx.beginPath();ctx.arc(v[0],v[1],5,0,Math.PI*2);ctx.fillStyle=index===0?D.colors[p.g]:D.recordMap[p.r].color;ctx.fill()});groups.forEach(p=>{let v=project(p.p);ctx.beginPath();ctx.arc(v[0],v[1],8,0,Math.PI*2);ctx.fillStyle=D.colors[p.g];ctx.fill();ctx.fillStyle='#0008';ctx.fill();ctx.strokeStyle='#111';ctx.lineWidth=2;ctx.stroke()});}
const canvases=[document.getElementById('all'),document.getElementById('psam')];function render(){canvases.forEach(draw)};
canvases.forEach(canvas=>{let drag=null;canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId)};canvas.onpointermove=e=>{if(drag){state.az+=(e.clientX-drag[0])*.008;state.el=Math.max(-1.5,Math.min(1.5,state.el+(e.clientY-drag[1])*.008));drag=[e.clientX,e.clientY];render()}};canvas.onpointerup=()=>drag=null;canvas.onpointercancel=()=>drag=null;canvas.addEventListener('wheel',e=>{e.preventDefault();state.zoom=Math.max(.3,Math.min(4,state.zoom*Math.exp(-e.deltaY*.001)));render()},{passive:false})});
document.getElementById('reset').onclick=()=>{state.az=-.9;state.el=.4;state.zoom=1;render()};document.getElementById('wire').onchange=render;window.onresize=render;
document.getElementById('legend0').innerHTML=D.names.map((g,i)=>'<span style="color:'+D.colors[i]+'">● '+g+'</span>').join(' &nbsp; ');
document.getElementById('legend1').innerHTML=Object.values(D.recordMap).map(v=>'<span style="color:'+v.color+'">● '+v.label+'</span>').join(' &nbsp; ');render();</script>'''
    (OUT/'lda_3d_interactive.html').write_text(html.replace('PAYLOAD',json.dumps(payload,separators=(',',':'))))
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    manifest=dict(units=len(units),recordings=len(centroids),features=215,axes=3,
                  original_model_modified=False,original_LD1_LD2_exactly_preserved=True,refit_alignment=alignment,
                  display=dict(group_centroids='Solid dark circles; manual zorder 100 above every unit, recording and wireframe',
                               recording_centroids='Solid colored circles',grid='Max three major intervals per axis; light lines',
                               wireframe='Reduced meridians and parallels'),
                  matched_refit=dict(solver='eigen',shrinkage=.01,n_components=3,priors='Original empirical class priors'),
                  ellipsoids=ellipse_definitions,
                  sources={str(p):sha(p) for p in [CONFIG,config['frozen_raw_metrics_csv'],config['frozen_model_npz'],__file__]})
    manifest['outputs']={p.name:sha(p) for p in OUT.iterdir() if p.suffix in ['.csv','.png','.pdf','.npz','.html']}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('COMPLETE 3D',json.dumps(alignment),flush=True)

if __name__=='__main__':main()
