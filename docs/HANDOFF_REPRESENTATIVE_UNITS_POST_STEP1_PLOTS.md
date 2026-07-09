# Handoff: Representative Units For Post-Step-1 Plot Waves

Date drafted: 2026-07-09 16:08 EDT

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
scripts/select_representative_units_for_plot_waves.py
scripts/plot_representative_unit_pack.py
```

Implementation order:

1. Build the unified unit index and reconciliation tables.
2. Generate wave-specific representative-unit CSVs.
3. Render a small smoke-test plot pack for one Lumos unit, one Cytoview dorsal
   unit, one Cytoview ventral unit, and one alignment-sensitive unit.
4. Expand to the full representative plot pack only after the manifests look
   correct.

## What To Avoid

- Do not use Step 2 classifier labels as ground truth.
- Do not drop `KSLabel=good` units just because optional QC fields are missing.
- Do not mix Lumos geometry groups with Cytoview dorsal/ventral biology.
- Do not select representative units directly inside plotting code.
- Do not overwrite the denominator-preserving Lumos/Cytoview composites.
- Do not interpret filtered histograms until the reconciliation table is written.

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
