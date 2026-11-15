"""Regenerate the complete current figure set in one portable, canonical scratch folder."""
from pathlib import Path
import argparse,ast,hashlib,json,shutil,sys,subprocess,os
ROOT=Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis')
REPO=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'unified_unit_analysis'
MODULES=['compose_mcs_paper_layout','plot_mcs_psam_recording_clouds','plot_mcs_lda_3d','decode_mcs_unit_trajectories','plot_mcs_lda_reference_style','compose_mcs_targeted_poststim_figure']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def copy(source,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    if source.resolve()!=dest.resolve():shutil.copy2(source,dest)
    assert sha(source)==sha(dest)
def prepare(out):
    """Collect compact saved numerical inputs and the complete local Python import closure."""
    if (out/'inputs/READY.json').exists():return
    sources=[]
    def put(source,relative):
        dest=out/relative;copy(source,dest);sources.append(dict(file=relative,source=str(source),sha256=sha(dest)))
    config=json.loads((REPO/'metadata/mcs_active_lda_configuration.json').read_text())
    for key in ['frozen_raw_metrics_csv','frozen_model_npz']:
        p=Path(config[key]);put(p,'inputs/locked/'+p.name)
    put(REPO/'metadata/mcs_active_lda_configuration.json','metadata/mcs_active_lda_configuration.json')
    put(ROOT/'temporal_signatures/unit_window_metrics.npz','inputs/unit_window_metrics.npz')
    put(ROOT/'temporal_signatures/paper_layout/fine_display_time_courses.csv','figures/01_activity_signatures/fine_display_time_courses.csv')
    for name in ['time_resolved_decoding.csv','poststim_confusion_matrix.csv','cross_time_macro_auroc.csv','summary.json','panel_j_observed_and_shuffled.csv','panel_j_null_methods.json','panel_j_resamples.npz']:
        put(ROOT/'temporal_signatures/paper_layout/balanced_decoder'/name,'figures/01_activity_signatures/balanced_decoder/'+name)
    put(ROOT/'trajectory_decoder/unit_100ms_spike_counts.npz','figures/03_probability_trajectories/unit_100ms_spike_counts.npz')
    for name in ['pre_post_all_windows.npz','selected_unit_pre_post.csv','summary.json','selected_control_tests.csv','selected_conditions.csv','unit_mean_sem_and_paired_tests.csv']:
        put(ROOT/'poststim_publication'/name,'inputs/targeted/'+name)
    pending=MODULES+['regenerate_mcs_unified_analysis','refine_mcs_paper_traces','update_mcs_balanced_temporal_decoder','compute_mcs_shuffled_decoder_null','extract_mcs_unit_trajectories','explore_mcs_burst_lda','lock_mcs_lda_and_plot_channel_deltas']
    seen=set()
    while pending:
        name=pending.pop()
        if name in seen:continue
        seen.add(name);p=REPO/'scripts'/(name+'.py')
        if not p.exists():continue
        put(p,'scripts/'+p.name)
        for node in ast.walk(ast.parse(p.read_text())):
            names=[a.name.split('.')[0] for a in node.names] if isinstance(node,ast.Import) else [node.module.split('.')[0]] if isinstance(node,ast.ImportFrom) and node.module else []
            pending.extend(n for n in names if (REPO/'scripts'/(n+'.py')).exists())
    for p in (REPO/'metadata').glob('MCS_*.md'):put(p,'metadata/'+p.name)
    for name in ['mcs_recording_biology.csv','mcs_targeted_poststim_metrics.json']:
        p=REPO/'metadata'/name
        if p.exists():put(p,'metadata/'+name)
    (out/'inputs/READY.json').write_text(json.dumps(sources,indent=2)+'\n')
def regenerate(out):
    """Render every figure; refit only the separate cumulative decoder and LD3 extension."""
    sys.path.insert(0,str(out/'scripts'))
    import importlib
    import load_mcs_locked_lda as loader
    config=out/'metadata/mcs_active_lda_configuration.json';cfg=json.loads(config.read_text())
    for key in ['frozen_raw_metrics_csv','frozen_model_npz']:cfg[key]=str(out/'inputs/locked'/Path(cfg[key]).name)
    config.write_text(json.dumps(cfg,indent=2)+'\n')
    original_load,original_project=loader.load_units,loader.project_units
    loader.CONFIG=config
    loader.load_units=lambda:original_load(config)
    loader.project_units=lambda values:original_project(values,config)
    paper=importlib.import_module(MODULES[0]);paper.SOURCE=out/'inputs';paper.OUT=out/'figures/01_activity_signatures';paper.main()
    clouds=importlib.import_module(MODULES[1]);clouds.OUT=paper.OUT;clouds.main()
    for name,folder in [(MODULES[2],'02_lda_3d'),(MODULES[3],'03_probability_trajectories'),(MODULES[4],'04_lda_interpretation'),(MODULES[5],'05_targeted_phenotypes')]:
        module=importlib.import_module(name);module.OUT=out/'figures'/folder;module.OUT.mkdir(parents=True,exist_ok=True)
        if name==MODULES[5]:module.SOURCE=out/'inputs/targeted'
        old=sys.argv;sys.argv=[name];module.main();sys.argv=old
    pdfs=[paper.OUT/'condition_signatures_paper_layout.pdf',out/'figures/02_lda_3d/lda_215_3d_recordings.pdf',out/'figures/03_probability_trajectories/unit_response_probability_trajectories.pdf',out/'figures/04_lda_interpretation/locked_215_lda_reference_style.pdf',out/'figures/05_targeted_phenotypes/targeted_poststim_effects_lda.pdf',paper.OUT/'psam_individual_recording_clouds.pdf']
    subprocess.run(['gs','-q','-dBATCH','-dNOPAUSE','-sDEVICE=pdfwrite','-dAutoRotatePages=/None','-dDownsampleColorImages=false','-dDownsampleGrayImages=false','-sOutputFile='+str(out/'ALL_FIGURES.pdf')]+[str(p) for p in pdfs],check=True)
    document(out)
def document(out):
    entries=[('Activity signatures, unit summaries, snapshot decoding','01_activity_signatures/condition_signatures_paper_layout','compose_mcs_paper_layout','main; unit_spread_outline','MCS_PAPER_LAYOUT.md'),('3D LD1–LD2–LD3 and PSAM recordings','02_lda_3d/lda_215_3d_recordings','plot_mcs_lda_3d','main; ellipsoid','MCS_LDA_3D.md'),('Evolving unit group probabilities','03_probability_trajectories/unit_response_probability_trajectories','decode_mcs_unit_trajectories','main','MCS_UNIT_PROBABILITY_TRAJECTORIES.md'),('Plain-English LDA associations and distributions','04_lda_interpretation/locked_215_lda_reference_style','plot_mcs_lda_reference_style','main; label','MCS_LDA_REFERENCE_STYLE.md'),('Targeted post values, paired changes, effect sizes and LDA','05_targeted_phenotypes/targeted_poststim_effects_lda','compose_mcs_targeted_poststim_figure','main; locked_lda; forest; post.draw_metric_panels','MCS_TARGETED_POSTSTIM_FIGURE.md'),('Additional 2D recording clouds and PSAM detail','01_activity_signatures/psam_individual_recording_clouds','plot_mcs_psam_recording_clouds','main; unit_spread_outline','MCS_PAPER_LAYOUT.md')]
    text='# Unified Actuators + effectors unit analysis\n\nThis is the canonical output folder. Start with [ALL_FIGURES.pdf](ALL_FIGURES.pdf): the five requested figures, followed by the related 2D PSAM detail. Each figure also has PNG/PDF exports below. All regeneration writes stay inside this folder.\n\n'
    text+='| Figure | Image | PDF | Generator / functions | Methods |\n|---|---|---|---|---|\n'
    for title,path,module,functions,method in entries:text+=f'| {title} | [PNG](figures/{path}.png) | [PDF](figures/{path}.pdf) | [scripts/{module}.py](scripts/{module}.py): `{functions}` | [Details](metadata/{method}) |\n'
    text+='''\n## What the points and models mean\n\nActuators + effectors only: 1,554 units across 29 recordings. Control: 473 units/8 recordings; DREADD: 230/5; LMO: 512/11; PSAM: 339/5. SUA/MUA pooled. Unit identity is `(recording_id, unit_id)`. Grouping follows biology, never dates. Small dots are units; solid colored circles are recording means; larger dark circles are unit-weighted group means, drawn on top. Covariance outlines show unit spread, not confidence intervals.\n\nThe locked descriptive LDA uses all 215 metrics (87 original + 128 burst). Its frozen LD1/LD2 are preserved. LD3 comes from a matched three-axis extension. The six displayed heatmap measurements explain associations; they do not replace the 215 model inputs.\n\nThe snapshot decoder uses six local-window features and held-out units. Panel J's null uses 1,000 label shuffles with refits. The cumulative trajectory decoder is separate: every 100 ms it uses only the ordered post-stimulus response available so far, with three fixed held-out-unit folds and equal priors. It is refitted during regeneration. Decoder scores are not calibrated biological probabilities. Unit splits can recognize recording-specific properties; they do not establish generalization to independent biological recordings.\n\nTime zero is the first STG train. Electrical stimulation artifacts remain included. Activity traces use Gaussian display smoothing, sigma 300 ms, applied separately before/after stimulation. The probability figure's firing display uses sigma 100 ms; classification uses unsmoothed 100-ms counts. No new metric/window selection occurs during regeneration. Targeted windows retain the prior optimized choices; their bootstrap intervals are pointwise and not adjusted for that selection. See each methods file and adjacent JSON manifest for exact definitions, missing-value handling, windows, statistics and normalization.\n\n## Where the numbers are\n\n- `inputs/locked/`: complete raw 215-feature unit table and immutable fitted state. `metadata/mcs_active_lda_configuration.json` gives feature order and hashes. `scripts/load_mcs_locked_lda.py`: `load_units()` and `project_units()` access them.\n- `inputs/unit_window_metrics.npz`: original unit × local-time-window × six-feature values.\n- `figures/01_activity_signatures/`: plotted traces, per-unit post summaries, tests, unit/recording LD coordinates and fine display curves. `balanced_decoder/` holds AUROC, shuffled/observed intervals, confusion, cross-time matrices and shuffle resamples.\n- `figures/02_lda_3d/`: unit/recording/group LD1–LD3 CSVs, extension state and [offline rotatable view](figures/02_lda_3d/lda_3d_interactive.html).\n- `figures/03_probability_trajectories/`: original 100-ms spike counts; probability archive indexed unit × endpoint × predicted class; unit IDs/folds, response/probability summaries and decoding performance.\n- `figures/04_lda_interpretation/`: correlations for all 215 metrics, six displayed English labels/rationales, unit LD coordinates and axis summaries.\n- `inputs/targeted/`: all pre/post candidate-window values, selected per-unit measurements and saved tests. `figures/05_targeted_phenotypes/` holds the updated metric registry, figure manifest and LD coordinates.\n- [FUNCTION_INDEX.md](FUNCTION_INDEX.md): every bundled Python function and its source line. `metadata/` contains detailed methods; legacy absolute paths there document historical origins. Current portable locations are listed here.\n- `inputs/READY.json`: original input paths and hashes. `OUTPUT_MANIFEST.json`: complete current file inventory, SHA-256 hashes and sizes. Adjacent figure manifests record panel inputs and settings.\n\n## Regenerate everything\n\nRun in a Python environment with NumPy, pandas, SciPy, Matplotlib and scikit-learn; Ghostscript must be installed. This command uses the bundled compact inputs, with no raw recording access:\n\n```bash\npython scripts/regenerate_mcs_unified_analysis.py --output-dir "$PWD"\n```\n\nRun from this folder. On Great Lakes submit it as a Slurm job; do not run decoder fitting on the login node. The runner updates local paths in the bundled configuration, checks frozen input/state hashes, rebuilds all six figures and the combined PDF. It reuses saved snapshot decoding/null results and saved fine display curves; it does not rerun the 1,000-shuffle analysis or extract raw spikes. Their generating scripts and provenance are included. It reruns the cumulative decoder and the matched LD3 fit. Historical analysis directories are input provenance, not the current output destination. No continuous recordings or duplicate image formats beyond PNG/PDF are copied.\n'''
    (out/'README.md').write_text(text)
    index='# Generating functions\n\nSource is bundled; line links open the exact implementation. `main()` functions are called by the unified runner. Extraction/search scripts are included for historical derivation, and are not called unless stated in README.\n\n'
    for p in sorted((out/'scripts').glob('*.py')):
        tree=ast.parse(p.read_text());index+='## '+p.name+'\n\n'+(ast.get_docstring(tree) or '')+'\n\n'
        for node in tree.body:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                index+=f'- [`{node.name}()`](scripts/{p.name}#L{node.lineno}) — '+(ast.get_docstring(node) or 'See implementation and figure methods for calculations.').split('\n')[0]+'\n'
        index+='\n'
    (out/'FUNCTION_INDEX.md').write_text(index)
    try:
        import platform, importlib.metadata as versions
        packages={name:versions.version(name) for name in ['numpy','pandas','scipy','matplotlib','scikit-learn']}
        (out/'requirements.txt').write_text(''.join(k+'=='+v+'\n' for k,v in packages.items()))
    except Exception:
        pass
    files=[]
    for directory,dirs,names in os.walk(str(out),followlinks=False):
        assert len(Path(directory).relative_to(out).parts)<6
        dirs[:]=[d for d in dirs if d!='__pycache__']
        for name in sorted(names):
            p=Path(directory)/name
            if name in ['OUTPUT_MANIFEST.json'] or name.endswith('.log'):continue
            files.append(dict(file=str(p.relative_to(out)),sha256=sha(p),bytes=p.stat().st_size))
    (out/'OUTPUT_MANIFEST.json').write_text(json.dumps(dict(scope='Actuators + effectors',units=1554,recordings=29,figures=6,files=files),indent=2)+'\n')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,default=DEFAULT);parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True);prepare(out)
    if not args.prepare_only:regenerate(out)
    print('UNIFIED OUTPUT',out,flush=True)
if __name__=='__main__':main()
