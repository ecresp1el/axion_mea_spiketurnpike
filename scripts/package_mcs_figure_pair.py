"""Collect the requested two figures, portable plotted values, and provenance."""
from pathlib import Path
import csv,hashlib,json,re,shutil,subprocess

REPO=Path(__file__).resolve().parents[1]
ROOT=Path('/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis')
PAPER=ROOT/'temporal_signatures/paper_layout'
TRAJECTORY=ROOT/'trajectory_decoder'
OUT=ROOT/'final_figure_pair'
DESKTOP=Path('/home/elcrespo/Desktop/MCS_Actuators_Effectors_Analysis')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    pairs=[(PAPER/'condition_signatures_paper_layout.png',OUT/'01_condition_signatures.png'),
           (TRAJECTORY/'unit_response_probability_trajectories.png',OUT/'02_unit_probability_trajectories.png'),
           (PAPER/'psam_individual_recording_clouds.png',OUT/'03_recording_clouds_and_psam_detail.png')]
    for n in ['recording_lda_centroids.csv','unit_lda_coordinates.csv','unit_post_0_5_summary.csv',
              'post_0_5_control_comparisons.csv','fine_display_time_courses.csv','manifest.json',
              'psam_recording_cloud_definitions.csv','psam_recording_cloud_manifest.json']:
        pairs.append((PAPER/n,OUT/'data/condition_signatures'/n))
    for n in ['time_resolved_decoding.csv','poststim_confusion_matrix.csv','cross_time_macro_auroc.csv',
              'panel_j_observed_and_shuffled.csv','panel_j_null_methods.json','summary.json']:
        pairs.append((PAPER/'balanced_decoder'/n,OUT/'data/snapshot_decoder'/n))
    for n in ['unit_probability_trajectories.npz','unit_trajectory_index.csv','probability_time_courses.csv',
              'response_time_courses.csv','trajectory_decoding_performance.csv','trajectory_model_manifest.json']:
        pairs.append((TRAJECTORY/n,OUT/'data/trajectory_decoder'/n))
    for n in ['MCS_PAPER_LAYOUT.md','MCS_UNIT_PROBABILITY_TRAJECTORIES.md','MCS_TEMPORAL_SIGNATURES.md',
              'mcs_active_lda_configuration.json']:
        pairs.append((REPO/'metadata'/n,OUT/'metadata'/n))
    for n in ['compose_mcs_paper_layout.py','refine_mcs_paper_traces.py','update_mcs_balanced_temporal_decoder.py',
              'compute_mcs_shuffled_decoder_null.py','audit_psam_temporal_decoder.py',
              'extract_mcs_unit_trajectories.py','decode_mcs_unit_trajectories.py','load_mcs_locked_lda.py',
              'package_mcs_figure_pair.py','plot_mcs_psam_recording_clouds.py']:
        pairs.append((REPO/'scripts'/n,OUT/'scripts'/n))
    three_d=ROOT/'lda_3d'
    has_3d=(three_d/'lda_215_3d_recordings.pdf').exists()
    if has_3d:
        pairs += [(three_d/'lda_215_3d_recordings.png',OUT/'04_lda_3d.png'),
                  (three_d/'lda_3d_interactive.html',OUT/'04_lda_3d_interactive.html'),
                  (REPO/'metadata/MCS_LDA_3D.md',OUT/'metadata/MCS_LDA_3D.md'),
                  (REPO/'scripts/plot_mcs_lda_3d.py',OUT/'scripts/plot_mcs_lda_3d.py')]
        for name in ['unit_ld1_ld2_ld3.csv','recording_centroids_3d.csv','group_centroids_3d.csv',
                     'extension_215_lda_state.npz','manifest.json']:
            pairs.append((three_d/name,OUT/'data/lda_3d'/name))
    records=[]
    for source,dest in pairs:
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
        assert sha(source)==sha(dest)
        records.append(dict(file=str(dest.relative_to(OUT)),source=str(source),sha256=sha(dest),bytes=dest.stat().st_size))
    rows=list(csv.DictReader((PAPER/'recording_lda_centroids.csv').open()))
    assert len(rows)==len({r['recording_id'] for r in rows})==29 and sum(int(r['n_units']) for r in rows)==1554
    pdf=OUT/'MCS_figures_and_unit_trajectories.pdf'
    inputs=[PAPER/'condition_signatures_paper_layout.pdf',TRAJECTORY/'unit_response_probability_trajectories.pdf',PAPER/'psam_individual_recording_clouds.pdf']
    if has_3d:inputs.append(three_d/'lda_215_3d_recordings.pdf')
    subprocess.run(['gs','-q','-dBATCH','-dNOPAUSE','-sDEVICE=pdfwrite','-dCompatibilityLevel=1.7',
                    '-dAutoRotatePages=/None','-dDownsampleColorImages=false','-dDownsampleGrayImages=false',
                    '-dDownsampleMonoImages=false','-sOutputFile='+str(pdf),*[str(p) for p in inputs]],check=True)
    assert len(re.findall(rb'/Type\s*/Page\b',pdf.read_bytes()))==len(inputs)
    (OUT/'README.md').write_text('''# Actuators + effectors: requested figure pair

Open **[MCS_figures_and_unit_trajectories.pdf](MCS_figures_and_unit_trajectories.pdf)** for all figures together in one PDF.

## Page 1: activity signatures and snapshot decoding

[Image](01_condition_signatures.png) · [Methods](metadata/MCS_PAPER_LAYOUT.md)

Panel I retains all 1,554 unit dots. Solid colored circles mark the centroids of 29 unique recordings. Four larger dark filled circles with bold outlines replace the former group stars. Each recording centroid is the mean of that recording's unit LD coordinates. Each group centroid remains the mean across its units, preserving unit weighting. Centroid overlays do not change models or statistical observations.

Panel J uses the six-feature local-window decoder with equal priors, a 1,000-refit unit-label shuffle null, and observed unit-bootstrap intervals. The locked 215-feature LDA remains the source of panel I. These are distinct models.

## Page 2: response and group-probability trajectories

[Image](02_unit_probability_trajectories.png) · [Methods](metadata/MCS_UNIT_PROBABILITY_TRAJECTORIES.md)

Every 100 ms the cumulative-response LDA uses the ordered spike-response bins available up to that endpoint to update each held-out unit's predicted group scores. Top: firing responses. Middle: all four predicted-group probability traces. Bottom: one row per unit, colored by the probability of its actual group. Scores are not calibrated biological probabilities. This prefix model is separate from page 1's local-window decoder.

## Page 3: recording clouds and PSAM detail

[Image](03_recording_clouds_and_psam_detail.png). Left: all units, 29 solid recording-centroid circles, four dark group-centroid circles, and group outlines. Right: all 339 PSAM unit dots, with a separate color, centroid circle, and outline for each of five recordings. Ellipses are two-SD covariance contours of unit spread, not confidence intervals. Overlap is retained; no coordinates are changed.

## Portable data

- `data/condition_signatures/`: unit coordinates, 29 recording centroids, summary dots, tests, smoothed curves, original figure manifest.
- `data/snapshot_decoder/`: AUROC/null curves, confusion and cross-time matrices, model/null provenance.
- `data/trajectory_decoder/`: every unit's four probability trajectories, index/folds, plotted summaries, performance, model provenance.

Identify units with **recording_id + unit_id**. The probability archive stores `(unit, time, predicted_class)` arrays with class order and times. Each dot/row remains one sorted unit; SUA/MUA are pooled. Recording overlays are summaries only.

`PACKAGE_MANIFEST.json` records original source paths and verified file hashes. Source manifests/scripts retain their original HPC paths for provenance; rerunning the scripts requires the original repository/environment and source data or path configuration. Portable figure values are provided here; continuous recordings are not duplicated. Major working outputs remain on scratch.
''')
    if has_3d:
        guide=OUT/'README.md';guide.write_text(guide.read_text()+'\n## Page 4: LD1–LD2–LD3\n\n[Static image](04_lda_3d.png) · [Rotate the 3D view offline](04_lda_3d_interactive.html) · [Methods](metadata/MCS_LDA_3D.md). The original LD1/LD2 coordinates are retained exactly; a matched three-component fit supplies LD3 without changing the locked model. Includes units, recording/group centroids, and three-dimensional unit-spread outlines.\n')
    manifest=dict(pages=len(inputs),scope='Actuators + effectors',units=1554,unique_recordings=29,
                  model_or_decoder_retrained_for_packaging=False,
                  pdf_sources={str(p):sha(p) for p in inputs},files=records,
                  combined_pdf_sha256=sha(pdf))
    (OUT/'PACKAGE_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    # Update existing transfer locations as well as the dedicated one-folder package.
    updates=[(PAPER/n,DESKTOP/'temporal_signatures/paper_layout'/n) for n in
             ['condition_signatures_paper_layout.png','condition_signatures_paper_layout.pdf',
              'recording_lda_centroids.csv','unit_lda_coordinates.csv','manifest.json']]
    updates += [(REPO/'metadata/MCS_PAPER_LAYOUT.md',DESKTOP/'metadata/MCS_PAPER_LAYOUT.md'),
                (REPO/'scripts/compose_mcs_paper_layout.py',DESKTOP/'scripts/compose_mcs_paper_layout.py')]
    package_paths=[OUT/r['file'] for r in records]+[pdf,OUT/'README.md',OUT/'PACKAGE_MANIFEST.json']
    updates += [(p,DESKTOP/'final_figure_pair'/p.relative_to(OUT)) for p in package_paths]
    all_records=json.loads((DESKTOP/'BUNDLE_MANIFEST.json').read_text())
    for source,dest in updates:
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest);assert sha(source)==sha(dest)
        rel=str(dest.relative_to(DESKTOP));all_records=[r for r in all_records if r['file']!=rel]
        all_records.append(dict(file=rel,source=str(source),sha256=sha(dest),bytes=dest.stat().st_size))
    (DESKTOP/'BUNDLE_MANIFEST.json').write_text(json.dumps(all_records,indent=2)+'\n')
    start=DESKTOP/'START_HERE.md'
    note='\n## Requested two-figure package\n\n[Both figures in one PDF](final_figure_pair/MCS_figures_and_unit_trajectories.pdf) · [Package guide](final_figure_pair/README.md). Includes the revised panel I with unit dots, recording circles, and dark group circles, plus the unit response/probability trajectories and their supporting tables.\n'
    if note not in start.read_text():start.write_text(start.read_text()+note)
    print('COMPLETE',OUT,str(len(inputs))+'-page PDF;',len(records),'source files;',sum(p.stat().st_size for p in package_paths)/1024**2,'MiB',flush=True)

if __name__=='__main__':main()
