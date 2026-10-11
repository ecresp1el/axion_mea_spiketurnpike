#!/usr/bin/env python3
"""Rebuild the bounded Axion recording/well inventory without modifying sources."""
from __future__ import annotations
import csv
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import re
import struct
import sys
from collections import Counter
from dataclasses import asdict

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[1]
AUD = REPO / 'audit-output/assembloid_lfp_inventory_20260917'
OLD = REPO / 'audit-output/axion_2024_inventory_20260917'
spec = importlib.util.spec_from_file_location('raw_parser_inventory', REPO / 'src/axion_mea/io/raw_stim_parser.py')
parser = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = parser
spec.loader.exec_module(parser)

def read_csv(path):
    return list(csv.DictReader(path.open(), delimiter='\t' if path.suffix == '.tsv' else ','))

def write_csv(name, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (OUT/name).open('w', newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader();w.writerows(rows)

def string(f):
    n=struct.unpack('<i',f.read(4))[0]
    if n<0 or n>1000000: raise ValueError('Invalid string length')
    return f.read(n).decode('utf8',errors='replace')

def settings(description):
    return {r[0]: ','.join(r[1:]) for r in csv.reader(io.StringIO(description)) if len(r)>1}

def inspect_raw(path):
    """Decode layouts documented by AxionFileLoader and preserve all header entries."""
    out={'exists':path.exists(),'readable':False,'raw_path':str(path),'header_entries':[],'wells':[]}
    if not out['exists']: return out
    out['file_size']=path.stat().st_size
    with path.open('rb') as f:
        out['readable']=True
        a=parser.AxionStimFile(path);r=parser.BinaryReader(f);es=a._read_primary_header(r)
        a._collect_latest_tag_entries(r,es)
        latest=a._latest_tag_entries
        f.seek(0);out['primary_header_hex']=f.read(a.entries_start).hex()
        r.seek_absolute(a.entries_start)
        stop=False;regions=[];headers=[]
        while not stop:
            for e in es:
                if e.record_type==parser.EntryRecordType.TERMINATE:
                    stop=True;break
                start=r.tell()
                if e.length<0:raise ValueError('Infinite length unsupported')
                if e.record_type==parser.EntryRecordType.BLOCK_VECTOR_DATA:
                    regions.append({'data_start':start,'data_bytes':e.length})
                else:
                    b=r.read_exact(e.length)
                    out['header_entries'].append({'entry_type':e.record_type.name,'offset':start,'length':e.length,'bytes_hex':b.hex()})
                    if e.record_type==parser.EntryRecordType.BLOCK_VECTOR_HEADER:
                        fs,scale=struct.unpack_from('<dd',b)
                        ds,nc,spb,bh=struct.unpack_from('<qIII',b,44)
                        headers.append({'sampling_hz':fs,'voltage_scale':scale,'channels':nc,'samples_per_block':spb,'block_header_bytes':bh,'vector_header_bytes':0,'datasets_per_block':1,'data_start_header':ds})
                    elif e.record_type==parser.EntryRecordType.BLOCK_VECTOR_HEADER_EXTENSION:
                        headers[-1]['description']=b[84:].decode('utf8',errors='replace').rstrip('\x00')
                    elif e.record_type==parser.EntryRecordType.COMBINED_BLOCK_VECTOR_HEADER:
                        bf=io.BytesIO(b)
                        maj,minr,dtype,stype=struct.unpack('<HHHH',bf.read(8))
                        fs,scale=struct.unpack('<dd',bf.read(16))
                        nc,nd,spb,vh,bh=struct.unpack('<IIIII',bf.read(20))
                        bf.read(56)
                        dur=struct.unpack('<d',bf.read(8))[0] if maj>1 or minr>=1 else None
                        name=string(bf);desc=string(bf)
                        ds,db=struct.unpack('<qq',bf.read(16))
                        headers.append({'sampling_hz':fs,'voltage_scale':scale,'channels':nc,'samples_per_block':spb,'block_header_bytes':bh,'vector_header_bytes':vh,'datasets_per_block':nd,'data_start_header':ds,'data_bytes_header':db,'duration_s_header':dur,'description':desc,'dataset_name':name,'sample_type':stype,'data_type':dtype})
                r.seek_absolute(start+e.length)
            if not stop:
                if r.read_ascii(len(a.MAGIC_WORD))!=a.MAGIC_WORD:raise ValueError('Bad subheader magic')
                es=[parser.EntryRecord.from_uint64(r.read_u64()) for _ in range(a.SUBHEADER_MAX_ENTRIES)]
                r.seek_relative(8)
        out['data_regions']=regions;out['block_headers']=headers
        out['single_continuous_dataset']=len(headers)==1 and len(regions)==1
        if not headers or not regions:raise ValueError('No continuous dataset found')
        out.update(headers[0]);out.update(regions[0]);out['settings']=settings(out.get('description',''))
        # VectorHeaderSize describes the continuous vector's metadata, not a
        # prefix repeated per electrode/sample. Axion ContinuousDataSet.m reads
        # interleaved int16 values directly from DataRegionStart.
        stride=out['block_header_bytes']+out['datasets_per_block']*out['channels']*2*out['samples_per_block']
        out['block_stride_bytes']=stride
        out['duration_s']=out['data_bytes']/stride*out['samples_per_block']/out['sampling_hz']
        out['sample_bytes_match']=(out['data_bytes']%stride==0)
        out['data_region_within_file']=out['data_start']+out['data_bytes']<=out['file_size']
        out['data_pointer_matches']=out['data_start_header']==out['data_start']
        out['data_region_boundary_readable']=False
        f.seek(out['data_start']);head=f.read(16)
        f.seek(out['data_start']+out['data_bytes']-16);tail=f.read(16)
        out['data_region_boundary_readable']=len(head)==16 and len(tail)==16
        out['all_dataset_regions_intact']=len(headers)==len(regions)
        for h,region in zip(headers,regions):
            stride_h=h['block_header_bytes']+h['datasets_per_block']*h['channels']*2*h['samples_per_block']
            valid=(region['data_bytes']%stride_h==0 and region['data_start']==h['data_start_header'] and region['data_start']+region['data_bytes']<=out['file_size'])
            f.seek(region['data_start']);valid=valid and len(f.read(16))==16
            f.seek(region['data_start']+region['data_bytes']-16);valid=valid and len(f.read(16))==16
            out['all_dataset_regions_intact']=out['all_dataset_regions_intact'] and valid
        for t in latest.values():
            if t.tag_type!=parser.TagType.WELL_TREATMENT:continue
            f.seek(t.start+t.BASE_SIZE)
            col,row,ec,er,flags=struct.unpack('<BBBBB',f.read(5))
            w={'well':f'{chr(64+row)}{col}','enabled':bool(flags&1),'is_control':bool(flags&2),'label':'','additional_information':'','amount':'','unit_exponent':'','unit':'','tag_guid':t.tag_guid,'tag_revision':t.revision_number,'creation_time':asdict(t.creation_time)}
            if t.start+t.length-f.tell()>=12:
                w['rgb']=list(f.read(3));w['label']=string(f);w['additional_information']=string(f)
                if t.start+t.length-f.tell()>9:
                    amount=struct.unpack('<d',f.read(8))[0];w['amount']='NaN' if math.isnan(amount) else amount
                    w['unit_exponent']=struct.unpack('<b',f.read(1))[0];w['unit']=string(f)
            out['wells'].append(w)
    return out

def canonical_path(p):
    return re.sub(r'_Filter\([^)]*\)(?=\.raw$)|_BroadbandProcessor(?=\.raw$)','',p)

def variant(p):
    if '_Filter(1Hz-200Hz)' in p:return 'lfp_filter_export'
    if '_Filter(200Hz-3kHz)' in p:return 'spike_filter_export'
    if '_BroadbandProcessor' in p:return 'broadband_processor_export'
    return 'original'

def sampled_hash(path):
    n=path.stat().st_size;h=hashlib.sha256()
    with path.open('rb') as f:
        for off in (0,max(0,n//2-524288),max(0,n-1048576)):
            f.seek(off);b=f.read(1048576);h.update(struct.pack('<Q',off));h.update(b)
    return h.hexdigest()

sources={};records={};origin_audit={}
for name in ['file_metadata.json']:
    for r in json.load((AUD/name).open()):
        p=r['raw_path'];sources[p]=('fusion_2026',canonical_path(p),variant(p));origin_audit[p]=[{'source':str(AUD/name),'record':r}]
for r in json.load((OLD/'embedded_metadata.json').open()):
    p=r['raw_path'];sources[p]=('fusion_2024',p,'original');origin_audit[p]=[{'source':str(OLD/'embedded_metadata.json'),'record':r}]
    for archive in ['MEAscripts/MannyAxionMEAscripts_v1','MannyTest/MannyAxionMEAscripts_v1']:
        q=p.replace('/MannyAxionMEAscripts_v1/',f'/{archive}/')
        sources[q]=('fusion_2024',p,'archive_copy')
for r in read_csv(AUD/'excluded_spike_band_recordings.tsv'):
    p=r['path'];sources[p]=('fusion_spike_band_2025_2026',p,'original');origin_audit[p]=[{'source':str(AUD/'excluded_spike_band_recordings.tsv'),'record':r}]
dv_dirs={Path(r['path']).parent for r in read_csv(AUD/'dorsal_ventral_lfp_embedded_well_metadata.csv')}
for d in sorted(dv_dirs):
    for p in sorted(d.glob('*.raw')):
        sources[str(p)]=('dorsal_ventral_2026',canonical_path(str(p)),variant(str(p)))
for name in ['lfp_recordings_embedded_well_metadata.csv','dorsal_ventral_lfp_embedded_well_metadata.csv','other_fusion_recordings_well_metadata.csv']:
    for r in read_csv(AUD/name):
        p=r.get('raw_path',r.get('path'))
        origin_audit.setdefault(p,[]).append({'source':str(AUD/name),'record':r})

manifest=[];wells=[];rawmeta=[]
for i,(p,(collection,canonical,role)) in enumerate(sorted(sources.items()),1):
    print(f'{i}/{len(sources)} {Path(p).name}',flush=True)
    m=inspect_raw(Path(p));m['prior_audit_records']=origin_audit.get(p,[]);rawmeta.append(m)
    rid='axion_'+hashlib.sha256(canonical.encode()).hexdigest()[:12]
    ss=m.get('settings',{})
    hp=ss.get('Digital High Pass Filter','');lp=ss.get('Digital Low Pass Filter','')
    mode=ss.get('Analog Mode Setting','')
    dhp=ss.get('High Pass Filter','');dlp=ss.get('Low Pass Filter','')
    if role=='spike_filter_export' or hp.startswith('200'):
        eligibility='excluded_high_pass_200hz';why='200 Hz high-pass removes conventional LFP frequencies.'
    elif collection=='fusion_2024' and 'LFP_' not in p:
        eligibility='restricted_5hz_neural_spikes';why='5 Hz digital high-pass and Neural Spikes analog mode; not approved for full-band LFP, especially below 5 Hz.'
    elif role=='lfp_filter_export':
        eligibility='eligible_1_200hz_export';why='Stored 1–200 Hz processed derivative; do not count independently or use below 1 Hz.'
    elif role=='broadband_processor_export':
        eligibility='review_processed_variant';why='Two processed datasets (12.5 kHz high-frequency and 100 Hz low-frequency stream); prefer original. Low stream Nyquist is 50 Hz, despite 200 Hz processor metadata.'
    elif hp.startswith('0.1') and mode in ['Neural Field Potentials','Neural Broadband','Cardiac Low Amplitude']:
        eligibility='eligible_low_frequency_acquisition';why='Acquisition retains low-frequency continuous voltage; signal QC remains separate.'
    else:
        eligibility='review_acquisition_settings';why='Acquisition settings require review.'
    intact=all(m.get(k,False) for k in ['readable','sample_bytes_match','data_region_within_file','data_pointer_matches','data_region_boundary_readable','all_dataset_regions_intact'])
    r={'recording_id':rid,'collection':collection,'raw_path':p,'filename':Path(p).name,'canonical_source_path':canonical,'variant_role':role,'preferred_for_lfp':role=='original' and eligibility=='eligible_low_frequency_acquisition' and intact,'lfp_eligibility':eligibility,'lfp_reason':why,'exists':m['exists'],'readable':m['readable'],'structural_integrity_pass':intact,'duration_s':m.get('duration_s',''),'sampling_hz':m.get('sampling_hz',''),'channels':m.get('channels',''),'voltage_scale':m.get('voltage_scale',''),'samples_per_block':m.get('samples_per_block',''),'block_header_bytes':m.get('block_header_bytes',''),'vector_header_bytes':m.get('vector_header_bytes',''),'datasets_per_block':m.get('datasets_per_block',''),'data_start':m.get('data_start',''),'data_bytes':m.get('data_bytes',''),'file_size':m.get('file_size',''),'analog_mode':mode,'acquisition_high_pass':hp,'acquisition_low_pass':lp,'derived_high_pass':dhp,'derived_low_pass':dlp,'referencing':ss.get('Referencing Method',''),'recorded_at':ss.get('Original File Time',''),'plate_serial':ss.get('Plate Serial Number',''),'well_tag_count':len(m['wells']),'duplicate_evidence':''}
    if collection=='fusion_2024':
        r['sampled_sha256_first_middle_last_1mib']=sampled_hash(Path(p))
    r['derived_high_pass_cutoff']=ss.get('High Pass Cutoff Freq.','')
    r['derived_low_pass_cutoff']=ss.get('Low Pass Cutoff Freq.','')
    r['continuous_dataset_count']=len(m.get('block_headers',[]))
    r['duration_caution']='Very short recording; unsuitable for stable slow-band PSD/coherence estimates.' if m.get('duration_s',0)<30 else ''
    manifest.append(r)
    bywell={w['well']:w for w in m['wells']}
    for wn in ['A1','A2','A3','B1','B2','B3']:
        w=bywell.get(wn,{})
        label=w.get('label','');curated='unresolved';basis='No composition assignment from generic fusion/sample codes';confidence='unresolved';override=False
        if label.lower()=='empty':curated='empty';basis='Explicit embedded well label';confidence='stored annotation'
        elif collection=='dorsal_ventral_2026':
            if 'Ventral' in label or 'Dorsal' in label:
                curated='ventral' if 'Ventral' in label else 'dorsal';basis='Explicit embedded well label';confidence='stored annotation'
            else:
                curated='ventral' if wn[0]=='A' else 'dorsal';basis='Documented A-row ventral/B-row dorsal plate-map default in GREATLAKES_KILOSORT_HANDOFF.md';confidence='curated plate-map default; embedded label blank'
            if '5_28_26_h1/134-0150/h1_dorsal_and_ventral_exp17_2(001)' in p and wn in ['B1','B2']:
                curated='ventral';basis='Human-notes override cytoview_dorsal_ventral_region_overrides_20260709.csv';confidence='human-notes ground truth';override=True
        elif not label:
            basis='Blank or absent embedded label; filename does not locate samples in wells'
        wells.append({'recording_id':rid,'collection':collection,'raw_path':p,'variant_role':role,'well':wn,'stored_label':label,'stored_enabled':w.get('enabled',''),'stored_is_control':w.get('is_control',''),'stored_additional_information':w.get('additional_information',''),'stored_amount':w.get('amount',''),'stored_unit_exponent':w.get('unit_exponent',''),'stored_unit':w.get('unit',''),'stored_tag_guid':w.get('tag_guid',''),'stored_tag_revision':w.get('tag_revision',''),'stored_tag_present':bool(w),'curated_identity':curated,'assignment_basis':basis,'assignment_confidence':confidence,'human_override_applied':override,'lfp_eligibility':eligibility,'preferred_for_lfp':r['preferred_for_lfp'],'source_metadata_json':json.dumps(w,sort_keys=True)})

canonical_hash={r['raw_path']:r.get('sampled_sha256_first_middle_last_1mib') for r in manifest if r['collection']=='fusion_2024' and r['variant_role']=='original'}
for r in manifest:
    if r['variant_role']=='archive_copy':
        same=r['sampled_sha256_first_middle_last_1mib']==canonical_hash[r['canonical_source_path']]
        r['duplicate_evidence']='same size and first/middle/last 1 MiB sampled SHA256; not full-file hash' if same else 'sampled mismatch; review copy'

for p,rr in origin_audit.items():
    if not p.endswith('.platemap'):continue
    rid='platemap_'+hashlib.sha256(p.encode()).hexdigest()[:12]
    for source in rr:
        w=source['record'];wells.append({'recording_id':rid,'collection':'standalone_plate_map','raw_path':p,'variant_role':'metadata_sidecar','well':w['well'],'stored_label':w.get('label',''),'stored_enabled':w.get('on',''),'stored_is_control':w.get('control',''),'curated_identity':'unresolved','assignment_basis':'Standalone plate map; recording linkage unconfirmed','assignment_confidence':'unresolved','lfp_eligibility':'metadata_only','preferred_for_lfp':False,'source_metadata_json':json.dumps(source,sort_keys=True)})

divrows=read_csv(OLD/'div140_inferred_well_map.csv')
for w in divrows:
    wells.append({'recording_id':'div140_original_unlocated','collection':'div140_historical_analysis','raw_path':'','variant_role':'dataset_unlocated','well':w['well'],'stored_label':'','stored_tag_present':False,'curated_identity':w['inferred_composition'],'assignment_basis':w['assignment_basis'],'assignment_confidence':w['confidence'],'lfp_eligibility':'unconfirmed_source_unlocated','preferred_for_lfp':False,'source_metadata_json':json.dumps(w,sort_keys=True)})
manifest.append({'recording_id':'div140_original_unlocated','collection':'div140_historical_analysis','raw_path':'','filename':'Organoids_d140','canonical_source_path':'/Volumes/Manny2TB/axion_mea_data_organoid_d140/SpikeStuff/all_data.mat','variant_role':'dataset_unlocated','preferred_for_lfp':False,'lfp_eligibility':'unconfirmed_source_unlocated','lfp_reason':'Historical processed spike dataset; original continuous raw acquisition not located. DIV140 A1–A3 CO–CO / B1–B3 CO–MGEO inference does not establish LFP availability.','exists':False,'readable':False,'structural_integrity_pass':False})

write_csv('candidate_manifest.csv',manifest)
write_csv('combined_well_metadata.csv',wells)
(OUT/'candidate_manifest.json').write_text(json.dumps({'recordings':manifest,'raw_metadata':rawmeta,'well_metadata':wells,'scope':'Known fusion, dorsal/ventral and historical 2024/DIV140 Axion holdings. Variants and archive copies are grouped, not independent recordings. Structural integrity is not biological signal quality.'},indent=2))
summary={'physical_raw_files':len(sources),'canonical_recordings':len({r['recording_id'] for r in manifest if r['raw_path']}),'preferred_lfp_originals':sum(r['preferred_for_lfp'] for r in manifest),'preferred_lfp_duration_s':sum(r.get('duration_s',0) for r in manifest if r['preferred_for_lfp']),'structural_pass_files':sum(r.get('structural_integrity_pass',False) for r in manifest),'variant_counts':dict(Counter(r['variant_role'] for r in manifest)),'eligibility_counts':dict(Counter(r['lfp_eligibility'] for r in manifest)),'well_metadata_rows':len(wells)}
(OUT/'manifest_summary.json').write_text(json.dumps(summary,indent=2))
source_files=sorted({Path(source['source']) for entries in origin_audit.values() for source in entries} | {OLD/'div140_inferred_well_map.csv',OLD/'DIV140_COMPARISON_EVIDENCE.md',OLD/'div140_plot_provenance.json'})
provenance=[]
for path in source_files:
    data=path.read_bytes()
    provenance.append({'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
override_path=Path('/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_region_overrides_20260709.csv')
(OUT/'inventory_source_provenance.json').write_text(json.dumps({'audit_sources':provenance,'human_override_source_path':str(override_path),'human_override_rows':read_csv(override_path),'dv_default_source':str(REPO/'docs/GREATLAKES_KILOSORT_HANDOFF.md'),'dv_default_rule':'A-row ventral, B-row dorsal; human B1/B2 H1 exp17_2(001) overrides take precedence','scope_note':'Known bounded inventories consolidated; source files preserved in place. File variants/archive copies do not increase independent recording counts.'},indent=2))
print(json.dumps(summary,indent=2))
