# Handoff: Representative Units For Post-Step-1 Plot Waves

Date drafted: 2026-07-09 16:08 EDT

## Current Status

Updated 2026-07-09 16:22 EDT.

Wave 0 has been implemented and submitted through Slurm as a reproducible,
targeted job package. The completed output root is:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_wave0_20260709_162201/
```

Completed job:

```text
job_id: 53201743
state: COMPLETED
elapsed: 00:00:09
node: gl3102
```

The first submitted Wave 0 job, `53201718`, failed in `00:00:05` before analysis
because `conda activate` hit the known `set -u` / `MKL_INTERFACE_LAYER`
activation issue. The prep script was patched to disable nounset only around
`conda activate`, then the corrected job `53201743` completed.

Wave 0 outputs:

```text
representative_unit_index_20260709.csv
representative_unit_index_20260709_summary.csv
representative_unit_index_20260709_provenance.json
wave0_denominator_summary_20260709.csv
wave0_reconciliation_table_20260709.csv
wave0_missing_assets_20260709.csv
submitted_jobs.tsv
wave0_prepare_manifest.json
repro/
  project_config.env
  python_command.sh
  submit_command.sh
  submitted_job.sbatch
```

Wave 0 denominator result:

| Track | Expected | Observed | Difference | KSLabel=good | Step 1 analyzer ready | Step 2 linked assets |
|---|---:|---:|---:|---|---:|---:|
| Cytoview dorsal/ventral | 237 | 237 | 0 | all true | 237 | 0 |
| Lumos geometry | 276 | 276 | 0 | all true | 276 | 0 |

Metric-validity reconciliation:

| Track | Valid unaligned/aligned TTP | Valid unaligned/aligned half-width | Valid unaligned/aligned REP50 |
|---|---:|---:|---:|
| Cytoview dorsal/ventral | 237 / 237 | 237 / 237 | 229 / 235 |
| Lumos geometry | 276 / 276 | 276 / 276 | 262 / 268 |

Interpretation:

- Wave 0 preserves the exact current denominator: `513` total `KSLabel=good`
  units, split into `276` Lumos geometry units and `237` Cytoview dorsal/ventral
  units.
- Every unit has a ready Step 1 analyzer path.
- Step 2 linked assets are currently absent for this v5 representative-unit
  denominator, so Wave A/B/C should proceed from Step 1 analyzer-backed
  GUI-equivalent data. Step 2 remains a future optional linked metadata layer.

Wave A/B/C candidate scoring has also been implemented and submitted through
Slurm. The current corrected candidate source is:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_abc_scoring_20260709_172908/
```

Completed corrected job:

```text
job_id: 53210960
state: COMPLETED
elapsed: 00:00:30
node: gl3044
```

The first A/B/C scoring job, `53210725`, completed successfully but is
superseded for Wave B selection because its pair-distance search was too strict
(`200 um`) and admitted only same-best-channel pairs. The corrected job widens
the neighbor-pair search to `1000 um` and ranks nonzero-distance pairs first.

Corrected A/B/C output summary:

| Metric | Count |
|---|---:|
| Input units | 513 |
| Scored Wave A stability units | 513 |
| Selected Wave A units | 30 |
| Scored Wave B within-well pairs | 851 |
| Selected Wave B pairs | 40 |
| Selected Wave B nonzero-distance pairs | 40 / 40 |
| Scored Wave C wells | 176 |
| Selected Wave C wells | 20 |
| Analyzer errors | 0 |

Corrected A/B/C outputs:

```text
waveA_stability_candidate_scores_20260709.csv
waveA_stability_representative_units_20260709.csv
waveB_correlogram_pair_scores_20260709.csv
waveB_correlogram_representative_units_20260709.csv
waveC_spatial_footprint_unit_scores_20260709.csv
waveC_spatial_footprint_representative_wells_20260709.csv
abc_scoring_summary_20260709.csv
abc_scoring_errors_20260709.csv
abc_scoring_provenance_20260709.json
repro/
  project_config.env
  python_command.sh
  submit_command.sh
  submitted_job.sbatch
```

Top corrected candidate examples:

- Wave A stability rank 1: Lumos `D6`, unit `2`, recording
  `6_22_2026_129-8445_ventral_sosrs_opsin_day3(003)_filter_200Hz-3kHz`,
  `2433` spikes, presence ratio `1.0`, stability score `0.995509`.
- Wave B correlogram/pair rank 1: Lumos `B4`, units `2` and `6`, FS/RS,
  best-channel distance `700 um`, zero-lag duplicate score `0.0`.
- Wave C spatial footprint rank 1: Cytoview dorsal `B3`, recording
  `5_28_26_h1_134-0150_h1_dorsal_and_ventral_exp17_2(001)_filter_200Hz-3kHz`,
  `13` good units in well, max best-channel distance `1081.665 um`.

Final representative-figure selection manifests were then generated as a
separate reproducible Slurm job so Lumos, Cytoview dorsal, and Cytoview ventral
are selected independently from the same scored candidate tables. This is the
current source for the first static figure-rendering pass:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_final_selection_20260709_174251/
```

Completed final-selection job:

```text
job_id: 53212357
state: COMPLETED
elapsed: 00:00:06
node: gl3039
```

The final-selection job writes `48` selected rows total:

| Selection group | Wave A stability units | Wave B correlogram pairs | Wave C spatial wells |
|---|---:|---:|---:|
| Lumos geometry | 6 | 6 | 4 |
| Cytoview dorsal | 6 | 6 | 4 |
| Cytoview ventral | 6 | 6 | 4 |

Candidate denominators before final selection:

| Selection group | Wave A candidates | Wave B pair candidates | Wave C well candidates |
|---|---:|---:|---:|
| Lumos geometry | 276 | 256 | 126 |
| Cytoview dorsal | 113 | 312 | 22 |
| Cytoview ventral | 124 | 283 | 28 |

Final-selection outputs:

```text
final_representative_figure_selection_manifest_20260709.csv
final_representative_figure_selection_summary_20260709.csv
final_representative_figure_selection_provenance_20260709.json
final_selection_lumos_waveA_stability_units_20260709.csv
final_selection_lumos_waveB_correlogram_pairs_20260709.csv
final_selection_lumos_waveC_spatial_wells_20260709.csv
final_selection_cytoview_dorsal_waveA_stability_units_20260709.csv
final_selection_cytoview_dorsal_waveB_correlogram_pairs_20260709.csv
final_selection_cytoview_dorsal_waveC_spatial_wells_20260709.csv
final_selection_cytoview_ventral_waveA_stability_units_20260709.csv
final_selection_cytoview_ventral_waveB_correlogram_pairs_20260709.csv
final_selection_cytoview_ventral_waveC_spatial_wells_20260709.csv
repro/
  project_config.env
  python_command.sh
  submit_command.sh
  submitted_job.sbatch
```

The final manifest carries:

```text
variant_policy = preserve_all_raw_filter_broadband_variants_no_deduplication
selection_pool_policy = separate_lumos_cytoview_dorsal_cytoview_ventral
```

Selected rows include multiple raw/filter families (`primary_raw`,
`filter_200Hz-3kHz`, and `broadband_processor`). This is intentional. Do not
collapse those variants during representative selection or plotting.

First-pass GUI-equivalent static plot pack was then rendered from the frozen
final-selection manifests:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_plot_pack_20260709_175429/
```

Completed plot-pack job:

```text
job_id: 53213093
state: COMPLETED
elapsed: 00:00:41
node: gl3184
```

The plot-pack job wrote `48` PNG panels and `0` errors:

| Selection group | Wave A stability panels | Wave B correlogram panels | Wave C spatial panels |
|---|---:|---:|---:|
| Lumos geometry | 6 | 6 | 4 |
| Cytoview dorsal | 6 | 6 | 4 |
| Cytoview ventral | 6 | 6 | 4 |

Plot-pack outputs:

```text
representative_unit_plot_pack_manifest_20260709.csv
representative_unit_plot_pack_errors_20260709.csv
representative_unit_plot_pack_provenance_20260709.json
lumos/
  waveA_stability/
  waveB_correlograms/
  waveC_spatial_footprints/
cytoview_dorsal/
  waveA_stability/
  waveB_correlograms/
  waveC_spatial_footprints/
cytoview_ventral/
  waveA_stability/
  waveB_correlograms/
  waveC_spatial_footprints/
repro/
  project_config.env
  python_command.sh
  submit_command.sh
  submitted_job.sbatch
```

The renderer consumes only the frozen final-selection manifests plus the
Wave C unit-score table, then loads each Step 1 `SortingAnalyzer` for
templates, spike trains, correlograms when available, and channel locations.
It does not change ranking, labels, or denominator membership.

Visual sanity checks passed for representative Wave A, Wave B, and Wave C
panels. One scoring caveat is now visible: the top Lumos Wave B pair is clean
by duplicate-risk/distance criteria but includes a sparse unit (`23` spikes),
so some correlogram panels are visually thin. Before selecting publication
examples, add a stricter pair-level minimum-spike floor or use a manual
override table to prefer visually interpretable pairs.

Correction for Wave C spatial-footprint panels:

The first plot-pack Wave C panels showed amplitude footprint maps only. That is
not enough for the intended isolation/representative-unit review. Wave C was
updated to render multichannel templates laid out on the electrode geometry:
each channel's template waveform is plotted at its electrode location, the
strongest channels are highlighted, the best channel is circled, and a 20 uV /
1 ms scale cue is drawn on each unit panel.

Corrected multichannel plot pack:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_plot_pack_20260709_182100/
```

Completed corrected plot-pack job:

```text
job_id: 53215665
state: COMPLETED
elapsed: 00:00:47
node: gl3118
```

Corrected render counts:

| Selection group | Wave A stability panels | Wave B correlogram panels | Wave C multichannel-template panels |
|---|---:|---:|---:|
| Lumos geometry | 6 | 6 | 4 |
| Cytoview dorsal | 6 | 6 | 4 |
| Cytoview ventral | 6 | 6 | 4 |

The corrected manifest has `48` rows, `48` PNGs, `0` render errors, and all
`12` Wave C rows are marked:

```text
selection_panel = within_well_multichannel_template_footprints
```

Use this corrected `20260709_182100` plot-pack root for inspecting spatial
footprints. Keep the earlier `20260709_175429` root only as provenance for the
superseded dot-map version.

Additional spatial-isolation 1x2 panels:

To make the spatial-isolation argument more visually convincing, a separate
1x2 panel pack was generated. Each figure uses one selected multi-unit well:

- left panel: overlaid normalized spatial PTP profiles for selected
  `KSLabel=good` units from the same well,
- right panel: matching auto/cross-correlogram matrix for those same units.

This directly shows whether good units in the same well have minimally
overlapping spatial profiles and non-duplicate timing structure.

Output root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_spatial_isolation_1x2_20260709_182942/
```

Completed job:

```text
job_id: 53216188
state: COMPLETED
elapsed: 00:00:39
node: gl3030
```

Outputs:

```text
spatial_isolation_1x2_manifest_20260709.csv
spatial_isolation_1x2_errors_20260709.csv
spatial_isolation_1x2_provenance_20260709.json
lumos/*.png
cytoview_dorsal/*.png
cytoview_ventral/*.png
```

Counts:

| Selection group | 1x2 panels | Render errors |
|---|---:|---:|
| Lumos geometry | 4 | 0 |
| Cytoview dorsal | 4 | 0 |
| Cytoview ventral | 4 | 0 |

The renderer chooses up to `3` units per selected well, with `min_spikes=100`,
and optimizes for stronger unit count, greater best-channel separation, and
lower normalized footprint cosine overlap. In the completed manifest, mean
footprint overlaps are low (`0.0000` to `0.0280`) and mean best-channel
distances are large (`398` to `1293 um`), making this the best current visual
summary for spatial separation plus correlogram evidence.

Preferred spatial-isolation 1x3 panels:

After reviewing the 1x2 panels, the spatial footprint view was extended to a
1x3 layout because the dot-only spatial overlay still did not show enough of
the waveform evidence. The 1x3 layout uses the same selected units and adds:

- left: centered best-channel mean waveforms for unit identity and waveform
  shape,
- middle: actual multichannel template waveforms laid out on the electrode
  grid,
- right: auto/cross-correlogram matrix for those exact units.

Output root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_spatial_isolation_1x3_20260709_183800/
```

Completed job:

```text
job_id: 53216594
state: COMPLETED
elapsed: 00:00:31
node: gl3051
```

Outputs:

```text
spatial_isolation_1x3_manifest_20260709.csv
spatial_isolation_1x3_errors_20260709.csv
spatial_isolation_1x3_provenance_20260709.json
lumos/*.png
cytoview_dorsal/*.png
cytoview_ventral/*.png
```

Counts:

| Selection group | 1x3 panels | Render errors |
|---|---:|---:|
| Lumos geometry | 4 | 0 |
| Cytoview dorsal | 4 | 0 |
| Cytoview ventral | 4 | 0 |

Use the `20260709_183800` 1x3 root as the preferred spatial-isolation review
pack. Keep the `20260709_182942` 1x2 root as a simpler summary, and the
`20260709_182100` root as the per-unit multichannel-template view.

## Goal

Build a unified, reproducible representative-unit selection layer for the next
major figure pass. The unit pool should come from completed Step 1 analyzers,
with `KSLabel=good` kept as the ground-truth inclusion label. Extra QC metrics,
waveform metrics, firing rates, optotag response metrics, and Step 2 recovered
assets should be linked around those Step 1 units as features for ranking,
annotation, and later filtering.

This handoff is about choosing representative units for specific plots. It is
not a new sorting pass, not a replacement curation policy, and not a change to
the current denominator-preserving Lumos/Cytoview waveform figures.

## GUI-Equivalent Rendering Rule

There is already GUI-backed functionality under the hood. The representative
plot scripts should reproduce what the Step 1 SpikeInterface GUI visualizes by
reading the same `SortingAnalyzer` objects, extensions, spike trains,
templates, channel locations, correlograms/ISI, similarity, and unit properties.
Do not create a separate recalculation path that can drift from the GUI.

The GUI itself is optional for human spot-checking. The required behavior is
that static/exported plots are GUI-equivalent and provenance-backed: every panel
should be traceable to the exact analyzer path, extension/data source, unit id,
channel ids, and parameters used to render it.

Use the existing Step 1 browser:

```bash
python scripts/launch_step1_sorting_analyzer_browser.py \
  --root-folder /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind \
  --recording-prefix step1_nonlfp_th5_20260708_ \
  --curation-root /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/step1_gui_curation \
  --address localhost \
  --port 18765
```

The current Step 1 GUI layout shows the same views the static plot pack should
replicate from analyzer data:

```text
zone3: trace, spikerate, probe, similarity, mainsettings
zone5: waveform
zone6: maintemplate
zone7: correlogram, isi
```

Displayed unit properties include:

```text
KSLabel
Amplitude
ContamPct
classifier_label
classifier_probability
original_cluster_id
firing_rate
num_spikes
x
y
```

Representative-unit manifests must include GUI-equivalent provenance fields:

```text
gui_equivalent_rendered
gui_equivalent_render_sources
gui_equivalent_render_notes
waveform_panel_source
maintemplate_panel_source
correlogram_panel_source
isi_panel_source
spikerate_panel_source
probe_panel_source
similarity_panel_source
human_spotcheck_status
human_spotcheck_notes
```

The default state for `gui_equivalent_rendered` is false until the static plots
have been generated from analyzer-backed data. `human_spotcheck_status` is
optional and should be used only when a candidate was manually reviewed in the
interactive GUI.

## Non-Negotiable Policy

1. `KSLabel=good` remains the primary ground-truth inclusion rule for this
   representative-unit pool.
2. Step 2 outputs are linked assets. They can provide QC/features/metadata, but
   their classifier labels do not replace Kilosort `KSLabel=good`.
3. Any later filtering must report the starting denominator, valid metric
   counts, excluded units, exclusion reasons, and final counts before
   interpreting histograms or representative examples.
4. Representative-unit selection must write a manifest before making plots, so
   every example unit can be traced back to recording, well, unit id, analyzer,
   ranking score, and selection reason.
5. Manual picks are allowed, but they must be stored as an override table with a
   reason column. Do not hard-code hand-picked units inside plotting scripts.
6. Lumos and Cytoview/SixWell dorsal/ventral examples must be selected as
   separate pools. Lumos geometry is the opto/geometry track, not a
   dorsal/ventral biological comparison.
7. Do not deduplicate primary, filtered, broadband-processor, or other raw-file
   variants during selection. Each analyzed variant remains a separate
   candidate row identified by its recording stem and provenance.

## Canonical Sources

Current Step 1 v5 root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/
```

Per-well Step 1 analyzer pattern:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/<recording>/<well>/postprocessed/block0_None_recording1.zarr
```

Step 1 v5 status and ready-state files:

```text
step1_v5_well_ground_truth.csv
step1_v5_ground_truth_summary.txt
step1_v5_ground_truth_summary.json
```

Current Lumos denominator/composite source:

```text
lumos_geometry_alignment_cutoff_composite_20260709/
  lumos_geometry_alignment_cutoff_composite_20260709_classified_units_long.csv
  lumos_geometry_alignment_cutoff_composite_20260709_summary.csv
  lumos_geometry_alignment_cutoff_composite_20260709_provenance.json
```

Current Cytoview denominator/composite source:

```text
cytoview_dv_alignment_cutoff_composite_20260709/
  cytoview_dv_alignment_cutoff_composite_20260709_classified_units_long.csv
  cytoview_dv_alignment_cutoff_composite_20260709_summary.csv
  cytoview_dv_alignment_cutoff_composite_20260709_provenance.json
```

Current Lumos optotag/ranking sources:

```text
lumos_gui_ready_trial_tag_screen_250pulse_jitterwin_20260709.csv
lumos_manual_spike_sorting_guide_jitterwin_20260709.csv
```

Step 2 linked-asset root, when available:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_unit_classification_step2_full/aind_unit_classification_step2_full_20260708_153945/<recording>/<well>/
```

Step 2 files to link, not use as replacement truth:

```text
curation/unit_labels_block0_None_recording1.csv
curation/curation_block0_None_recording1.json
curation/unit_merges_block0_None_recording1.json
quality_metrics_required_diagnostic.json
classification_recovery_summary.json
data_process_unit_classification_recovery.json
```

## Unified Unit Index To Build First

Create a dated output folder:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709/
```

First artifact:

```text
representative_unit_index_20260709.csv
representative_unit_index_20260709_summary.csv
representative_unit_index_20260709_provenance.json
```

Minimum unit-index columns:

```text
recording
well
unit_id
analyzer_path
sorting_unit_id
ks_label
contam_pct
kilosort_amplitude
plate_family
track
region_label
lumos_geometry_group
source_denominator
has_step1_analyzer
has_step2_linked_assets
step2_result_path
has_quality_metrics_required_diagnostic
has_unit_labels_csv
firing_rate_hz
trough_to_peak_duration_ms_unaligned
trough_to_peak_duration_ms_aligned
half_width_ms_unaligned
half_width_ms_aligned
rep50_ms_unaligned
rep50_ms_aligned
amplitude_uV_unaligned
amplitude_uV_aligned
fs_rs_cutoff_0p37_unaligned
fs_rs_cutoff_0p37_aligned
fs_rs_cutoff_0p50_unaligned
fs_rs_cutoff_0p50_aligned
opto_status
opto_review_rank
opto_response_rate_hz
opto_peak_raw_response_hz
num_spikes
duration_s
presence_ratio
isi_violation_ratio
isi_violations_count
amplitude_cutoff
snr
firing_rate_bin_count
firing_rate_bin_size_s
firing_rate_cv
firing_rate_slope_hz_per_min
amplitude_bin_count
amplitude_median_uV
amplitude_cv
waveform_template_correlation_min
waveform_template_correlation_median
waveform_ptp_cv
best_channel_id
best_channel_x
best_channel_y
template_centroid_x
template_centroid_y
template_spatial_spread_um
neighbor_channel_count
selection_pool
selection_reason
manual_override_flag
manual_override_reason
```

The index should preserve units even when optional linked assets are missing.
Missing linked assets should be encoded as `has_* == false` and `NaN` metric
columns, not silently dropped.

## Plot Waves

### Wave 0 - Reconciliation And Asset Linking

Purpose:

- Build the unified unit index.
- Confirm the same unit population used by the current Lumos and Cytoview
  composites can be recovered.
- Link Step 2 QC/metadata paths without changing inclusion labels.

Required checks:

- Lumos denominator recovers `276` paired `KSLabel=good` units.
- Cytoview denominator recovers `237` paired `KSLabel=good` units.
- Every included unit has `recording`, `well`, `unit_id`, and `analyzer_path`.
- Step 2 linked-asset status is reported per unit/well.
- Missing QC/Step 2 assets are counted and listed.

Outputs:

```text
wave0_reconciliation_table_20260709.csv
wave0_missing_assets_20260709.csv
wave0_denominator_summary_20260709.csv
```

### Wave A - Waveform Stability And Firing Rate Over Time

Purpose:

- Produce `1-3` representative examples showing stable spike isolation across
  the spontaneous recording period.
- Reproduce the GUI spikerate, waveform, template, and trace views from the
  same analyzer-backed data.

Candidate pool:

- `KSLabel=good`
- enough spikes for time-resolved stability, with `num_spikes` stored
- completed Step 1 analyzer with `templates`, `random_spikes`, and recording
  access
- prefer units from wells/recordings that are already part of the Lumos or
  Cytoview representative pools

Numeric preselection:

- Split the recording into fixed time bins, initially `30 s` or `60 s`.
- Compute firing rate per bin, spike count per bin, and presence ratio.
- Compute amplitude distribution per bin when spike amplitudes are available.
- Compute waveform/template stability from sampled snippets or per-bin mean
  waveforms on the same best channel.
- Rank stable examples using low firing-rate CV, low amplitude CV, high
  presence ratio, low waveform drift, and enough spikes in most bins.

Suggested candidate criteria:

```text
presence_ratio >= 0.80
firing_rate_bin_count >= 8
num_spikes >= 100
firing_rate_cv not extreme within its class/region
amplitude_cv not extreme when available
waveform_template_correlation_median high
waveform_template_correlation_min not obviously poor
```

Outputs:

```text
waveA_stability_representative_units_20260709.csv
waveA_stability_candidate_scores_20260709.csv
```

Expected plots:

- firing rate over time
- amplitude over time, if available
- waveform snippets or per-bin mean waveforms overlaid on the same best channel
- final average waveform/template for the same unit
- small provenance strip with analyzer path, unit id, source extensions, and
  stability metrics

GUI-equivalent rendering:

- Static plots should use the same unit spike train that drives the GUI
  spikerate view.
- Waveform/template panels should come from the analyzer `templates` and/or
  `random_spikes` assets, not from a separate waveform table.
- The rendered panel should include `KSLabel`, `Amplitude`, `ContamPct`,
  `firing_rate`, and `num_spikes` from the same sorting/analyzer properties the
  GUI displays.

### Wave B - Auto/Cross-Correlogram FS-RS Examples

Purpose:

- Produce representative autocorrelograms and cross-correlograms for isolated
  `2-3` FS/RS unit examples or pairs.
- Demonstrate refractory periods and absence of duplicate unit detection across
  neighboring electrodes.
- Reproduce the GUI `correlogram` and `isi` views from the same analyzer-backed
  correlogram/ISI data or equivalent SpikeInterface computation with recorded
  parameters.

Candidate pool:

- `KSLabel=good`
- same well for any cross-correlogram pair
- preferably one FS-like and one RS-like unit, using the current selected cutoff
  view for the figure being prepared
- enough spikes for interpretable autocorrelograms/cross-correlograms
- units should not be marked as likely duplicates by zero-lag cross-correlogram
  structure or extremely similar templates

Numeric preselection:

- Compute autocorrelogram around zero lag and ISI histogram for each candidate
  unit.
- Score refractory quality from low short-ISI mass, low `isi_violation_ratio`,
  and a visible trough around zero lag.
- For within-well pairs, compute cross-correlograms for nearby units and score
  potential duplicate risk from zero-lag peak, template similarity, best-channel
  overlap, and spatial distance.
- Prefer FS/RS examples that are close enough spatially to be a meaningful
  duplicate-detection test, but not so similar that they look like duplicate
  units.

Suggested candidate criteria:

```text
num_spikes per unit >= 100
isi_violation_ratio low or visibly acceptable
autocorrelogram refractory trough present
cross_correlogram_zero_lag_duplicate_score low
best_channel_distance_um > 0 when comparing units
template_similarity not extreme for the selected pair
same_well_pair == true
```

Outputs:

```text
waveB_correlogram_representative_units_20260709.csv
waveB_correlogram_pair_scores_20260709.csv
```

Expected plots:

- autocorrelogram for each selected unit
- ISI histogram or refractory inset
- cross-correlogram for each selected within-well pair
- waveform/template inset for the same units
- metadata strip with well, unit ids, FS/RS label, firing rate, best channel,
  distance, and duplicate-risk score

GUI-equivalent rendering:

- Autocorrelogram and ISI panels should use the same binning/window logic as the
  analyzer/GUI view whenever the persisted `correlograms` extension is present.
- Cross-correlogram duplicate-risk panels should use the same selected spike
  trains and record the bin size/window parameters in provenance.
- Waveform, maintemplate, probe, and similarity insets should come from the same
  analyzer extensions/properties that back the GUI panes.

### Wave C - Spatial Footprints Within Wells

Purpose:

- Produce spatial footprints of representative units across neighboring
  electrodes, illustrating spatial separation of independently isolated units.
- All selected spatial-footprint examples must be within a well.
- Use a couple of representative wells across recordings, not only one well.

Candidate pool:

- `KSLabel=good`
- same well for all units shown in one spatial-footprint panel
- multiple good units in the well, ideally including both FS-like and RS-like
  examples when available
- completed Step 1 analyzer with templates and channel locations

Numeric preselection:

- For every candidate unit, compute a template footprint across all channels in
  that well using peak-to-peak amplitude per channel.
- Extract best channel, footprint centroid, spatial spread, and footprint
  overlap with neighboring units.
- Score wells by having multiple `KSLabel=good` units, spatially separated best
  channels/centroids, and non-identical template footprints.
- Select a small number of wells across different recordings, then select units
  within each well that illustrate separation.

Suggested candidate criteria:

```text
good_units_in_well >= 2
neighbor_channel_count > 1
best_channel_distance_um between selected units is nonzero and interpretable
footprint_centroid_distance_um between selected units is interpretable
footprint_overlap_score not extreme
templates not near-identical
recording diversity favored across final selected wells
```

Outputs:

```text
waveC_spatial_footprint_representative_wells_20260709.csv
waveC_spatial_footprint_unit_scores_20260709.csv
```

Expected plots:

- per-unit template footprint across neighboring electrodes inside one well
- electrode map with footprint amplitude encoded by color/size
- best channel and centroid markers
- waveform/template insets for selected units
- optional cross-correlogram inset for units that are spatially nearby but
  independently isolated

GUI-equivalent rendering:

- Probe/footprint panels should use the same channel locations and templates
  available to the GUI `probe`, `waveform`, and `maintemplate` panes.
- Similarity/overlap annotations should come from the analyzer similarity data
  when available, with the fallback calculation recorded in provenance.
- The renderer must enforce one well per footprint map.

### Wave 1 - Lumos Optotag Representative Units

Purpose:

- Select representative Lumos units for optotag response plots.
- Keep the Lumos grouping as opto-track geometry, not dorsal/ventral biology.

Candidate pool:

- `KSLabel=good`
- `opto_status == ok`
- Lumos geometry groups:
  - `columns_1_3_compare`
  - `columns_4_8_prior`

Recommended bins:

- strongest pulse-locked responders by peak raw PSTH response
- strongest train-locked responders
- clean low-baseline/high-response examples
- non-responder or weak-responder examples that are still `KSLabel=good`
- geometry-balanced examples from columns `1-3` and `4-8`

Outputs:

```text
wave1_lumos_optotag_representative_units_20260709.csv
wave1_lumos_optotag_selection_summary_20260709.csv
```

Expected plots:

- train-locked raster/PSTH with reconstructed command trace
- pulse-locked raster/PSTH with reconstructed command trace
- waveform panel for the same unit
- small metadata strip: recording, well, unit id, KSLabel, firing rate,
  opto response rank, geometry group

### Wave 2 - Cytoview Dorsal/Ventral Representative Units

Purpose:

- Select representative Cytoview units for dorsal/ventral biological
  comparisons.

Candidate pool:

- `KSLabel=good`
- Cytoview/SixWell current GUI-ready priority wells
- plate-map-backed `dorsal` or `ventral` region, including the current B1/B2
  override layer

Recommended bins:

- dorsal high firing-rate examples
- dorsal low firing-rate examples
- ventral high firing-rate examples
- ventral low firing-rate examples
- typical units nearest each region/class median
- boundary units near the TTP cutoff to show classification sensitivity

Outputs:

```text
wave2_cytoview_dv_representative_units_20260709.csv
wave2_cytoview_dv_selection_summary_20260709.csv
```

Expected plots:

- firing-rate comparison examples
- dorsal/ventral waveform examples
- TTP/half-width/REP examples
- region-balanced summary panels

### Wave 3 - FS/RS And Alignment-Sensitivity Representative Units

Purpose:

- Choose examples that explain why alignment and cutoff choices matter.

Candidate pool:

- Lumos and Cytoview `KSLabel=good` units from the paired alignment audits.

Recommended bins:

- stable RS across all four conditions
- stable FS across all four conditions
- switches at `0.37 ms` after alignment
- switches at `0.50 ms` after alignment
- units with one-sample TTP shifts that change class
- units with large half-width or REP changes after alignment

Outputs:

```text
wave3_alignment_sensitivity_representative_units_20260709.csv
wave3_alignment_sensitivity_selection_summary_20260709.csv
```

Expected plots:

- before/after uV waveform overlays
- individual snippets plus mean waveform
- normalized waveform panels
- metric delta panels for TTP, half-width, REP50, amplitude

### Wave 4 - QC/Asset Edge Cases

Purpose:

- Document examples where a unit is `KSLabel=good` but linked assets are
  incomplete, borderline, or need careful interpretation.

Candidate pool:

- `KSLabel=good` units with missing optional Step 2/QC-linked fields
- valid Step 1 units with incomplete optotag metadata
- units near metric validity boundaries, such as no crossing, NaN REP, or
  failed half-width anchor detection

Outputs:

```text
wave4_qc_asset_edge_cases_20260709.csv
wave4_qc_asset_edge_case_summary_20260709.csv
```

Expected plots:

- small audit panels, not primary biology figures
- reason-coded examples for missing metric/asset categories

### Wave 5 - Final Representative Plot Pack

Purpose:

- Render the selected representative units into publication-style or
  lab-meeting-style panels from frozen manifests.

Inputs:

```text
wave1_lumos_optotag_representative_units_20260709.csv
wave2_cytoview_dv_representative_units_20260709.csv
wave3_alignment_sensitivity_representative_units_20260709.csv
wave4_qc_asset_edge_cases_20260709.csv
```

Outputs:

```text
representative_units_plot_pack_20260709/
  lumos_optotag_examples/
  cytoview_dorsal_ventral_examples/
  alignment_sensitivity_examples/
  qc_edge_case_examples/
  representative_units_plot_pack_manifest_20260709.csv
  representative_units_plot_pack_provenance_20260709.json
```

## Selection Scoring

Use transparent scores and store all score components. Recommended scoring
rules:

- For strong optotag examples, rank by pulse-locked peak raw response first,
  then response-minus-baseline, then firing-rate stability.
- For typical D/V examples, select units closest to the median of their group
  for firing rate and waveform metrics.
- For FS/RS examples, select units far from cutoff boundaries for stable
  exemplars and close to boundaries for sensitivity exemplars.
- For alignment examples, rank by absolute metric delta and by class-switch
  status.
- For QC edge cases, rank by interpretability and explicit reason category, not
  by biological strength.

Every selected row must include:

```text
selection_wave
selection_panel
selection_rank
selection_score
selection_reason
selection_metric_primary
selection_metric_secondary
```

## Manual Override File

Create this only when manual choices are needed:

```text
representative_unit_manual_overrides_20260709.csv
```

Minimum columns:

```text
selection_wave
recording
well
unit_id
action
reason
requested_by
timestamp
```

Allowed `action` values:

```text
include
exclude
pin_rank
replace_with
```

Manual overrides must be applied after the automated candidate table is written
and must be reflected in the final provenance JSON.

## Implementation Target

Recommended new scripts:

```text
scripts/build_representative_unit_index.py
scripts/prepare_representative_unit_wave0_job.py
scripts/score_representative_unit_candidates.py
scripts/prepare_representative_unit_abc_scoring_job.py
scripts/build_representative_figure_selection_manifests.py
scripts/prepare_representative_figure_selection_job.py
scripts/plot_representative_unit_pack_from_manifests.py
scripts/prepare_representative_plot_pack_job.py
scripts/plot_representative_unit_pack.py
```

Implementation order:

1. Build the unified unit index and reconciliation tables.
2. Score Wave A/B/C candidates numerically from the existing Step 1 analyzer
   assets and write candidate tables.
3. Build the final representative selection manifests as separated Lumos,
   Cytoview dorsal, and Cytoview ventral pools. Do not deduplicate recording
   variants.
4. Render GUI-equivalent static panels from the same analyzer-backed data used
   by the Step 1 GUI. Optional human spot-checks can be recorded, but are not
   required for automated plot generation.
5. Generate wave-specific representative-unit CSVs for Lumos, Cytoview,
   alignment-sensitivity, and QC-edge examples.
6. Render a small smoke-test plot pack for one stability unit, one FS/RS
   correlogram pair, one spatial-footprint well, one Lumos optotag unit, one
   Cytoview dorsal unit, one Cytoview ventral unit, and one alignment-sensitive
   unit.
7. Expand to the full representative plot pack only after the manifests look
   correct.

## Same-Well Hybrid Spatial QC Smoke Test, 2026-07-09

- [x] 2026-07-09 19:12 EDT - Added and smoke-rendered the hybrid same-well
  spatial QC layout for the existing Cytoview ventral B2 example.

  This pass did not reselect, rerank, substitute, or filter units. It reused the
  existing `spatial_isolation_1x3` B2 selection exactly:

  ```text
  selection_group=cytoview_ventral
  well=B2
  unit_ids=8;11;30
  analyzer_path=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_5_28_26_h1_134-0150_h1_dorsal_and_ventral_exp17_2(001)_primary_Neural_Broadband_hp_0.1_Hz_IIR_lp_None/B2/postprocessed/block0_None_recording1.zarr
  ```

  New output root:

  ```text
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_spatial_isolation_hybrid_qc_20260709_195500/
  ```

  Rendered outputs:

  ```text
  cytoview_ventral/02_step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_5_28_26_h1_134-0150_h1_dorsal_and_v_B2_spatial_isolation_hybrid_qc.png
  cytoview_ventral/02_step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_5_28_26_h1_134-0150_h1_dorsal_and_v_B2_spatial_isolation_hybrid_qc.pdf
  cytoview_ventral/02_step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_5_28_26_h1_134-0150_h1_dorsal_and_v_B2_spatial_isolation_hybrid_qc.svg
  cytoview_ventral/02_step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_5_28_26_h1_134-0150_h1_dorsal_and_v_B2_spatial_isolation_hybrid_qc_companion_manifest.csv
  spatial_isolation_hybrid_qc_manifest_20260709.csv
  spatial_isolation_hybrid_qc_errors_20260709.csv
  spatial_isolation_hybrid_qc_provenance_20260709.json
  ```

  Figure layout:
  A, combined physical electrode map with all selected units and their
  multichannel mean waveforms; B, one local multichannel waveform footprint per
  unit using best electrode plus the eight nearest electrodes; C, one
  autocorrelogram per unit; D, sampled best-channel spike-PTP stability over
  recording time.

  Normalization rule:
  for display only, traces are divided once per unit by that unit's absolute
  best-channel template PTP. Neighboring channels are never normalized
  independently, waveform polarity is preserved, and no RS/FS labels are shown.

  Companion-manifest audit values:

  | Unit | Spike count | Best channel | Local channel IDs | Best-channel PTP uV | Amplitude source |
  |---:|---:|---:|---|---:|---|
  | 8 | 1932 | 50 | `50;51;42;49;58;57;41;43;59` | 53.402 | persisted `random_spikes` best-channel snippet PTP |
  | 11 | 3930 | 28 | `28;29;20;27;36;19;35;21;37` | 14.218 | persisted `random_spikes` best-channel snippet PTP |
  | 30 | 663 | 53 | `53;54;45;52;61;60;44;46;62` | 19.457 | persisted `random_spikes` best-channel snippet PTP |

  Analyzer inspection found a `spike_amplitudes` extension with
  `params={'peak_sign': 'neg'}`. It was not used for panel D because the hybrid
  QC figure requires best-channel peak-to-peak amplitude so positive- and
  negative-going waveforms are handled consistently.

  The previous preferred 1x3 output root was not overwritten:

  ```text
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_spatial_isolation_1x3_20260709_183800/
  ```

- [x] 2026-07-09 20:30 EDT - Revised only the hybrid same-well spatial QC
  figure for the same Cytoview ventral B2 example and saved a new v2 suffix.

  New v2 output root:

  ```text
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_spatial_isolation_hybrid_qc_v2_20260709_203000/
  ```

  Rendered outputs:

  ```text
  cytoview_ventral/02_step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_5_28_26_h1_134-0150_h1_dorsal_and_v_B2_spatial_isolation_hybrid_qc_v2.png
  cytoview_ventral/02_step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_5_28_26_h1_134-0150_h1_dorsal_and_v_B2_spatial_isolation_hybrid_qc_v2.pdf
  cytoview_ventral/02_step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_5_28_26_h1_134-0150_h1_dorsal_and_v_B2_spatial_isolation_hybrid_qc_v2.svg
  cytoview_ventral/02_step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_5_28_26_h1_134-0150_h1_dorsal_and_v_B2_spatial_isolation_hybrid_qc_v2_companion_manifest.csv
  ```

  Changes relative to v1:
  row B local waveform panels use horizontal display multiplier `1.2`, base
  vertical display multiplier `1.75`, and an auto-selected uniform local
  waveform display gain of `1.527973` after the same within-unit best-channel
  PTP normalization. Neighboring channels are still not normalized
  independently; the uniform glyph gain affects every channel trace equally and
  preserves relative channel amplitudes. The individual sampled-spike cloud
  remains only on the best channel and was lightened for readability. A new row
  D shows probability-normalized autocorrelograms under the existing count ACG
  row, with dashed boundary lines at `-2 ms` and `+2 ms` instead of a filled
  refractory box. Amplitude stability is now row E.

  Probability ACG equation:

  ```text
  p_i = count_i / sum(count_j for displayed bins j with center != 0 ms)
  ```

  Validation:

  | Unit | Displayed probability sum | P(abs lag <= 2 ms) |
  |---:|---:|---:|
  | 8 | 1.000 | 0.001621 |
  | 11 | 1.000 | 0.014843 |
  | 30 | 1.000 | 0.000000 |

  The original v1 hybrid figure root remains intact:

  ```text
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_spatial_isolation_hybrid_qc_20260709_195500/
  ```

- [x] 2026-07-09 19:50 EDT - Rendered a broader strategic hybrid QC review
  pack so final same-well examples can be chosen visually across Lumos,
  Cytoview dorsal, and Cytoview ventral.

  Output root:

  ```text
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_spatial_isolation_hybrid_qc_v2_review_20260709_194340/
  ```

  Scope:
  existing Wave C selected wells were reused; no cross-well mixing was allowed.
  For each selected well, the renderer scored all same-well unit combinations
  with the existing spatial-isolation score and saved the top `3` combinations.
  This created `36` hybrid QC panels total:

  | Group | Panels | Unique wells |
  |---|---:|---:|
  | Lumos | 12 | 2 |
  | Cytoview dorsal | 12 | 2 |
  | Cytoview ventral | 12 | 4 |

  Outputs:
  `36` PNG, `36` PDF, and `36` SVG panels were written, with `0` render errors.
  The manifest is:

  ```text
  spatial_isolation_hybrid_qc_manifest_20260709.csv
  ```

  Quick-screen contact sheets:

  ```text
  lumos_hybrid_qc_v2_review_contact_sheet.jpg
  cytoview_dorsal_hybrid_qc_v2_review_contact_sheet.jpg
  cytoview_ventral_hybrid_qc_v2_review_contact_sheet.jpg
  ```

  Plotting update:
  the probability-normalized ACG row is now a line with a light unit-color area
  fill underneath. The displayed line uses only a one-bin-neighbor smoothing
  kernel, `[1, 2, 1] / 4`, so it remains close to the raw binned probability
  shape. The count ACG row remains raw bars. The probability values and
  validation sums remain based on the unsmoothed displayed-bin probabilities;
  smoothing is display-only.

## What To Avoid

- Do not use Step 2 classifier labels as ground truth.
- Do not drop `KSLabel=good` units just because optional QC fields are missing.
- Do not mix Lumos geometry groups with Cytoview dorsal/ventral biology.
- Do not use one global top-N ranking as the final representative selection;
  final examples must be chosen within separate Lumos, dorsal, and ventral
  pools.
- Do not deduplicate raw/filter/broadband variants during representative
  selection or plotting.
- Do not select representative units directly inside plotting code.
- Do not overwrite the denominator-preserving Lumos/Cytoview composites.
- Do not interpret filtered histograms until the reconciliation table is written.
- Do not make spatial-footprint panels that mix units across wells.
- Do not promote an autocorrelogram/cross-correlogram example without a
  duplicate-risk check and analyzer-backed correlogram/ISI provenance.
- Do not claim waveform stability from a single average template alone; show
  time-resolved firing rate and waveform/amplitude stability.

## Cross-References

Detailed denominator/cutoff/alignment source:

```text
docs/GREATLAKES_KILOSORT_HANDOFF.md
section: Current Single Source: Waveform Alignment, Cutoffs, And Denominators
```

Stim-locked GUI/raster/PSTH source:

```text
docs/HANDOFF_STIM_LOCKED_GUI_RASTER_PSTH_WINDOW.md
```

Operational Step 1/Step 2 history:

```text
docs/KEMPNER_WORKFLOW_ADAPTATION_PLAN.md
```
