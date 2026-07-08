# Downstream Analysis Data Inventory

Date inspected: 2026-07-08 15:58 EDT

## Scope

The recovery pipeline is frozen. This document inventories the existing Step 1
and Step 2 AIND outputs and proposes the downstream analysis data model. It does
not define new recovery-pipeline work and does not require rerunning Kilosort,
UnitRefine, Bombcell, or SpikeInterface recovery.

The downstream analysis framework should follow this sequence:

1. Inventory: what exists.
2. Master table: create the canonical Step 3 dataset.
3. Loader API: load the canonical table first; reopen wells only for missing
   per-well assets.
4. Analysis modules: RS/FS, optotagging, QC, PSTHs, and related analyses.

## Output Roots

Step 1 AIND/Kilosort/NWB-units root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/<recording>/<well>/
```

Step 2 frozen classification/QC recovery root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_unit_classification_step2_full/aind_unit_classification_step2_full_20260708_153945/<recording>/<well>/
```

Step 2 batch manifest and submitted jobs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_step2_full_20260708_153945/step2_full_manifest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_step2_full_20260708_153945/submitted_jobs.tsv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_step2_full_20260708_153945/recovery_params.json
```

As of this inspection, Step 2 full-scale processing was still in progress:

```text
sacct state counts:
  80 COMPLETED
  28 RUNNING
  14 PENDING

visible Step 2 files:
  71 unit label CSVs
  67 classification summaries
  72 quality metric diagnostics
```

The data model should therefore support wells with Step 1 only and wells with
both Step 1 and completed Step 2 outputs.

## Representative Wells Inspected

Lumos 48-well sample:

```text
recording:
  6_22_2026_129-8445_ventral_sosrs_opsin_day3(003)_FortyEightWellLumos_primary_raw_NeuralBroadband
well:
  A3
channels:
  16
sampling rate:
  12500.0 Hz
duration:
  600.0 s
units:
  46
persisted SortingAnalyzer extensions:
  correlograms
  random_spikes
  templates
```

SixWell sample:

```text
recording:
  sixwell_manual_primary_5_25_26_pvreporter_134-0150_pv_reporter_cl32_dorsal_and_ventral_exp17(000)
well:
  A1
channels:
  64
sampling rate:
  12500.0 Hz
duration:
  600.0 s
units:
  82
persisted SortingAnalyzer extensions:
  correlograms
  random_spikes
  templates
```

Load checks were performed in the AIND SpikeInterface 0.104.8 container.

## Asset Inventory

### Well Manifest

Path:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_step2_full_20260708_153945/step2_full_manifest.csv
```

Format: CSV.

Useful columns:

```text
lane
plate_family
recording
well
source_results_dir
recovery_output_dir
recovery_params_json
unit_count_total
kslabel_good_count
kslabel_mua_count
spike_count_total
source_ledger_csv
```

Load with `pandas.read_csv`.

Canonical source: yes, for the Step 2 analysis universe and for mapping each
well to its Step 1 and Step 2 directories.

### Submitted Step 2 Jobs

Path:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_step2_full_20260708_153945/submitted_jobs.tsv
```

Format: TSV.

Load with `pandas.read_csv(path, sep="\t")`.

Canonical source: yes, for job IDs and submitted Step 2 well list. Not a
scientific data source.

### Recording

Primary path:

```text
<step1_well>/postprocessed/block0_None_recording1.zarr
```

Format: SpikeInterface `SortingAnalyzer` Zarr directory containing the recording
and sorting references.

Load with:

```python
import spikeinterface.full as si
analyzer = si.load_sorting_analyzer(path)
recording = analyzer.recording
```

Canonical source: yes, for SpikeInterface-native access to sampling rate,
channel count, channel locations, duration, and any downstream computations that
need the recording object.

Portable/archive path:

```text
<step1_well>/nwb/*.nwb
```

Format: NWB-Zarr directory, not a single HDF5 file.

Load with `hdmf_zarr.NWBZarrIO` or direct `zarr.open_group` for selected arrays.

Canonical source: yes for portable NWB export and `units` arrays; use the
SortingAnalyzer as the canonical SpikeInterface object.

### Sorting

Curated sorting path:

```text
<step1_well>/curated/block0_None_recording1/
```

Spikesorted sorting path:

```text
<step1_well>/spikesorted/block0_None_recording1/
```

Format: SpikeInterface `NumpyFolderSorting`.

Load with:

```python
import spikeinterface.full as si
sorting = si.load(path)
```

Persisted files:

```text
numpysorting_info.json
si_folder.json
spikes.npy
provenance.pkl or provenance.json
properties/Amplitude.npy
properties/ContamPct.npy
properties/KSLabel.npy
properties/KSLabel_repeat.npy
properties/original_cluster_id.npy
```

Canonical source: yes. For primary biological analyses, use the Step 1 curated
sorting and Kilosort4 labels. Current analysis policy is to use Kilosort4 good
units as the primary inclusion set, optionally include Kilosort4 MUA units when
scientifically appropriate, and exclude Kilosort noise units.

### SortingAnalyzer

Path:

```text
<step1_well>/postprocessed/block0_None_recording1.zarr
```

Format: SpikeInterface `SortingAnalyzer` Zarr directory.

Load with:

```python
import spikeinterface.full as si
analyzer = si.load_sorting_analyzer(path)
```

Canonical source: yes, for reusable SpikeInterface extensions. Loaders should
call `analyzer.get_loaded_extension_names()` or `analyzer.has_extension(name)`
for each well instead of assuming every extension exists.

Persisted extensions observed in representative wells:

```text
correlograms
random_spikes
templates
```

Not persisted as Step 1 analyzer extensions in the inspected wells:

```text
waveforms
quality_metrics
template_metrics
spike_locations
spike_amplitudes
principal_components
```

### Waveforms

NWB path:

```text
<step1_well>/nwb/*.nwb/units/waveform_mean
<step1_well>/nwb/*.nwb/units/waveform_sd
```

Format: Zarr arrays inside NWB-Zarr.

Observed shapes:

```text
Lumos A3 waveform_mean: (46, 37, 16)
SixWell A1 waveform_mean: (82, 37, 64)
```

Load with `hdmf_zarr.NWBZarrIO` or direct Zarr.

Canonical source: yes, for persisted mean and standard-deviation waveforms in
the NWB export. Individual extracted waveforms were not persisted in the
inspected Step 1 analyzer. Step 2 computes waveforms transiently for recovery
but does not persist them as reusable analysis assets.

### Templates

Analyzer path:

```text
<step1_well>/postprocessed/block0_None_recording1.zarr/extensions/templates/
```

Format: SpikeInterface analyzer extension in Zarr.

Load with:

```python
templates = analyzer.get_extension("templates").get_data()
```

Observed Lumos A3 shape:

```text
(46, 62, 16)
```

NWB alternative:

```text
<step1_well>/nwb/*.nwb/units/waveform_mean
```

Canonical source: yes, if `analyzer.has_extension("templates")` is true. Use
NWB `waveform_mean` for portable export or if a downstream workflow is NWB-first.

### Template Metrics

Step 2 diagnostic path:

```text
<step2_well>/quality_metrics_required_diagnostic.json
```

Format: JSON diagnostic/provenance file.

Load with `json.load`.

Canonical source: no, for per-unit template metric values. The diagnostic JSON
records available/configured metrics, required columns, feature audits, completed
metrics, failed metrics, and skipped metrics. It is not a per-unit metric table.

Template metrics were computed during Step 2 recovery for classifier execution,
but the inspected Step 2 outputs do not persist a reusable per-unit
`template_metrics` table or analyzer extension.

### Quality Metrics

Step 2 diagnostic path:

```text
<step2_well>/quality_metrics_required_diagnostic.json
```

Format: JSON diagnostic/provenance file.

Load with `json.load`.

Canonical source: no, for per-unit quality metric values. The diagnostic JSON is
canonical only for provenance and feature audit information.

Observed diagnostic keys include:

```text
spikeinterface_version
available_quality_metrics
configured_quality_metrics
required_pre_classifier_quality_metrics
optional_post_classifier_quality_metrics
computed_quality_metric_columns
completed_metrics
failed_metrics
skipped_metrics
unitrefine_feature_audit
unitrefine_required_columns
bombcell_required_columns
default_qc_required_columns
```

The inspected Step 1 analyzer does not persist a `quality_metrics` extension.
Step 2 computes metrics for classification but does not persist a reusable
per-unit quality-metrics DataFrame.

### Spike Locations

NWB paths:

```text
<step1_well>/nwb/*.nwb/units/estimated_x
<step1_well>/nwb/*.nwb/units/estimated_y
<step1_well>/nwb/*.nwb/units/estimated_z
<step1_well>/nwb/*.nwb/units/extremum_channel_index
```

Format: per-unit Zarr arrays inside NWB-Zarr.

Load with `hdmf_zarr.NWBZarrIO` or direct Zarr.

Canonical source: yes, for persisted per-unit estimated locations. Per-spike
`spike_locations` were computed transiently during Step 2 recovery but were not
persisted as a Step 2 analyzer extension in the inspected outputs.

### Correlograms

Analyzer path:

```text
<step1_well>/postprocessed/block0_None_recording1.zarr/extensions/correlograms/
```

Format: SpikeInterface analyzer extension in Zarr.

Load with:

```python
ccgs, bins = analyzer.get_extension("correlograms").get_data()
```

Observed Lumos A3 shape:

```text
ccgs: (46, 46, 52)
bins: (53,)
```

Canonical source: yes, if `analyzer.has_extension("correlograms")` is true.

### Spike Amplitudes

Sorting properties:

```text
<step1_well>/curated/block0_None_recording1/properties/Amplitude.npy
<step1_well>/spikesorted/block0_None_recording1/properties/Amplitude.npy
```

NWB unit amplitudes:

```text
<step1_well>/nwb/*.nwb/units/amplitude
```

Format: per-unit NumPy array or NWB-Zarr unit column.

Load sorting properties through SpikeInterface:

```python
amplitude = sorting.get_property("Amplitude")
```

Load NWB amplitude through `hdmf_zarr.NWBZarrIO` or direct Zarr.

Canonical source: yes, for per-unit amplitude summaries. A full per-spike
`spike_amplitudes` extension was not persisted in the inspected Step 1 analyzer.
Step 2 may compute spike amplitudes transiently for recovery, but the full
extension is not a reusable persisted analysis artifact in the inspected outputs.

### Principal Components

Path: no persisted Step 1 or Step 2 per-well PCA extension was found in the
inspected analyzer/output folders.

Format: not available as a persisted reusable asset.

Canonical source: no. Principal components were part of Step 2 recovery
computation, but downstream analysis loaders should not assume a reusable
`principal_components` extension exists.

### Unit Labels

Step 1 Kilosort labels:

```text
<step1_well>/curated/block0_None_recording1/properties/KSLabel.npy
<step1_well>/curated/block0_None_recording1/properties/KSLabel_repeat.npy
```

Load with:

```python
kslabel = sorting.get_property("KSLabel")
```

Step 2 classifier/default-QC labels:

```text
<step2_well>/curation/unit_labels_block0_None_recording1.csv
```

Format: CSV.

Observed columns:

```text
default_qc
unitrefine_label
unitrefine_probability
bombcell_label
```

Load with `pandas.read_csv`.

Canonical source: yes, for classifier/default-QC metadata. The CSV does not
include an explicit `unit_id` column, so the loader must attach unit IDs from
the Step 1 curated sorting or analyzer in the same row order.

Primary biological inclusion should still use Step 1 Kilosort4 labels plus
independent QC, not UnitRefine/Bombcell as an automatic exclusion gate.

### Curation JSON

Path:

```text
<step2_well>/curation/curation_block0_None_recording1.json
```

Format: SpikeInterface curation JSON.

Load with `json.load`.

Observed keys:

```text
supported_versions
format_version
unit_ids
label_definitions
manual_labels
removed
merges
splits
```

Canonical source: yes, for classifier-derived curation metadata.

### Merge JSON

Path:

```text
<step2_well>/curation/unit_merges_block0_None_recording1.json
```

Format: JSON list.

Load with `json.load`.

Canonical source: yes, for Step 2 merge metadata. Empty lists are valid.

### Step 2 Summary

Path:

```text
<step2_well>/classification_recovery_summary.json
```

Format: JSON.

Load with `json.load`.

Useful keys include:

```text
n_units
recording
well
labels_csv
curation_json
quality_metrics_diagnostic
unitrefine_counts
bombcell_counts
default_qc_pass
default_qc_fail
elapsed_seconds
source_analyzer
source_results_dir
output_dir
```

Canonical source: yes, for Step 2 run summary/provenance. Not a replacement for
the label CSV.

### AIND DataProcess Metadata

Path:

```text
<step2_well>/data_process_unit_classification_recovery.json
```

Format: AIND DataProcess JSON.

Load with `json.load`.

Canonical source: yes, for provenance. Not a scientific analysis table.

### NWB Units

Path:

```text
<step1_well>/nwb/*.nwb/units/
```

Format: NWB-Zarr unit table arrays.

Observed unit keys:

```text
amplitude
depth
device_name
electrodes
electrodes_index
estimated_x
estimated_y
estimated_z
extremum_channel_index
id
ks_unit_id
original_cluster_id
shank
spike_times
spike_times_index
unit_name
waveform_mean
waveform_sd
```

Load with `hdmf_zarr.NWBZarrIO` or direct Zarr access. Use `spike_times_index`
to split the flat `spike_times` array by unit.

Canonical source: yes, for portable NWB unit export. For SpikeInterface-native
analysis, prefer the Step 1 curated sorting and analyzer.

### Quality-Control Images

Paths:

```text
<step1_well>/quality_control/block0_None/traces_raw.png
<step1_well>/quality_control/block0_None/rms.png
<step1_well>/quality_control/block0_None/psd.png
<step1_well>/visualization/block0_None_recording1/traces_full_seg0.png
```

Format: PNG.

Load with image libraries such as Pillow or use directly in reports.

Canonical source: yes, for visual QC reports. Not machine-readable analysis
features.

### AIND Metadata and Reproducibility

Step 1 metadata paths:

```text
<step1_well>/data_description.json
<step1_well>/processing.json
<step1_well>/quality_control.json
<step1_well>/visualization_output.json
```

Step 1 reproducibility paths:

```text
<step1_well>/repro/aind_config.env
<step1_well>/repro/aind_params.json
<step1_well>/repro/aind_pipeline_commit.txt
<step1_well>/repro/aind_pipeline_status.txt
<step1_well>/repro/axion_repo_commit.txt
<step1_well>/repro/axion_repo_status.txt
<step1_well>/repro/nextflow_command.sh
<step1_well>/repro/submitted_job.sbatch
<step1_well>/repro/input_nwb.txt
<step1_well>/repro/data_path.txt
<step1_well>/repro/results_path.txt
```

Nextflow provenance:

```text
<step1_well>/nextflow/trace.txt
<step1_well>/nextflow/report.html
<step1_well>/nextflow/timeline.html
<step1_well>/nextflow/dag.html
<step1_well>/nextflow/nextflow.log
```

Format: JSON, text, shell script, HTML, and Nextflow trace tables.

Canonical source: yes, for provenance and reproducibility. Not primary
scientific feature tables.

## Proposed Data Model

The first downstream analysis deliverable should be a single master unit table,
not a figure and not a general well object model. This table is not an
intermediate artifact. It is the canonical Step 3 dataset.

Every downstream biological analysis should start by loading this table rather
than reopening 122 individual wells whenever possible. Reopen per-well
SortingAnalyzer, sorting, or NWB-Zarr outputs only when an analysis explicitly
requires an asset that is not represented in the master table.

The table is the canonical object for downstream analyses: feature-space plots,
RS/FS waveform grouping, trough-to-peak histograms, optotag filters, and
RS-vs-FS statistics should all start from this table.

```text
MasterUnitTable
  recording
  well
  unit_id
  spike_count
  firing_rate_hz
  template_reference
  trough_to_peak_duration_ms
  waveform_asymmetry
  repolarization_slope
  rs_fs_classification
  optotag_status
  optional Step 2 metadata columns
```

The current implementation writes:

```text
recording
well
unit_id
spike_count
firing_rate_hz
template_reference
trough_to_peak_duration_ms
waveform_asymmetry
repolarization_slope
rs_fs_classification
optotag_status
default_qc
unitrefine_label
unitrefine_probability
bombcell_label
```

The table is assembled from existing outputs only:

```text
Step 1 curated sorting:
  unit_id
  KSLabel inclusion filter
  spike_count

Step 1 SortingAnalyzer:
  recording duration
  sampling rate
  average templates
  trough-to-peak duration
  waveform asymmetry
  repolarization slope
  template reference

Step 2 label CSV when present:
  default_qc
  unitrefine_label
  unitrefine_probability
  bombcell_label
```

Current inclusion rule:

```text
emit rows where Step 1 curated sorting KSLabel == "good"
```

Do not use UnitRefine or Bombcell labels as automatic primary exclusion criteria
until a separate classifier-calibration project validates them for Axion Lumos
organoid MEA recordings.

## Step 3 Objective

Step 3 should build the canonical master unit table. It should not write
figures, write analysis modules, design a general `AnalysisWell` class, or
modify the frozen recovery pipeline.

Implemented entry point:

```text
scripts/build_master_waveform_metrics_table.py
```

Default output:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/master_waveform_metrics_table.csv
```

Canonical downstream loader:

```python
from axion_mea.master_unit_table import load_canonical_master_unit_table

units = load_canonical_master_unit_table()
```

The loader is intentionally minimal: it loads the Step 2 manifest, Step 1
curated sorting, Step 1 SortingAnalyzer templates, and optional Step 2 unit
labels. It computes only the columns needed for the master table.

## RS/FS Classification

RS/FS classification is the first biological annotation pass on the canonical
Step 3 table. It should not reopen all wells. It reads
`master_waveform_metrics_table.csv`, fills `rs_fs_classification`, and writes
summary/provenance sidecars.

Implemented entry point:

```text
scripts/annotate_rs_fs_classification.py
```

Current conservative rule:

```text
threshold:
  trough_to_peak_duration_ms = 0.45 ms
sampling rate:
  12500 Hz
sample margin:
  1 sample = 0.08 ms
FS_like:
  trough_to_peak_duration_ms <= 0.37 ms
borderline:
  0.37 ms < trough_to_peak_duration_ms < 0.53 ms
RS_like:
  trough_to_peak_duration_ms >= 0.53 ms
unknown:
  missing trough_to_peak_duration_ms
```

The margin preserves a small gray zone around the historical 0.45 ms heuristic
instead of forcing one-sample-boundary units into a biological class too early.

RS/FS outputs live next to the canonical table on Turbo:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/
  master_waveform_metrics_table.csv
  master_waveform_metrics_table_rs_fs_summary.csv
  master_waveform_metrics_table_rs_fs_provenance.json
  master_waveform_metrics_table_rs_fs_plot_provenance.json
  figures/rs_fs_classification/
    figure__rs_fs_class_counts.png
    figure__rs_fs_feature_space.png
    figure__rs_fs_firing_rate_by_class.png
    figure__rs_fs_trough_to_peak_histogram.png
  repro/
    annotate_rs_fs_classification_command.sh
    annotate_rs_fs_classification_command_context.json
    plot_rs_fs_classification_command.sh
    plot_rs_fs_classification_command_context.json
```

The `repro/` command files follow the existing handoff convention: source
`config/greatlakes_project.env`, activate the Great Lakes Conda environment, and
run the exact Step 3 command.

## Reuse vs Recomputation

| Analysis | Existing persisted asset | Recomputation required? |
|---|---|---|
| waveform QC | Step 1 analyzer `templates`; NWB-Zarr `units/waveform_mean`, `units/waveform_sd`; sorting `Amplitude` property | No for basic waveform shape, amplitude summaries, mean/SD inspection. Yes if the QC requires individual waveforms, waveform-over-time drift, or SpikeInterface `template_metrics` columns not persisted as tables. |
| RS/FS classification | Step 1 analyzer `templates`; NWB-Zarr `units/waveform_mean`; sampling rate from analyzer | No if RS/FS is computed directly from persisted mean/template waveforms. Yes only if choosing to rely on SpikeInterface `template_metrics` instead of computing waveform width/features from the persisted templates. |
| autocorrelograms | Step 1 analyzer `correlograms` extension | No. Autocorrelograms are the diagonal of the persisted correlogram tensor. |
| cross-correlograms | Step 1 analyzer `correlograms` extension | No. Cross-correlograms are the off-diagonal entries of the persisted correlogram tensor. |
| spatial footprints | Step 1 analyzer `templates`; analyzer channel locations; NWB-Zarr `units/estimated_x`, `estimated_y`, `estimated_z`, `extremum_channel_index` | No for per-unit location and template footprint maps. Yes if per-spike `spike_locations` or more detailed spatial metrics are required. |
| waveform stability | Step 1 sorting spike trains; Step 1 recording through analyzer; persisted mean/SD waveforms | Yes for true temporal waveform stability, because individual waveforms or time-binned waveforms are not persisted. Mean/SD waveforms only support coarse summary QC. |
| firing-rate stability | Step 1 curated sorting `spikes.npy` through SpikeInterface; NWB-Zarr `units/spike_times` | No. Compute binned firing rates from persisted spike times. |
| PSTHs | Step 1 curated sorting or NWB-Zarr `units/spike_times`; stimulus/event timing from NWB or Axion sidecars when present | No SpikeInterface recomputation. Requires a canonical event/stimulus table; if event timing is not already represented cleanly, the missing work is event loading, not recomputing SI extensions. |
| optotagging | Step 1 curated sorting or NWB-Zarr `units/spike_times`; stimulus/event timing from NWB or Axion sidecars; optional waveform templates | No SpikeInterface recomputation for spike-aligned response metrics. Requires canonical optical-stimulation event metadata. |
| latency analysis | Step 1 curated sorting or NWB-Zarr `units/spike_times`; stimulus/event timing from NWB or Axion sidecars | No SpikeInterface recomputation. Requires canonical event times. |
| synchrony | Step 1 analyzer `correlograms`; Step 1 sorting spike trains | No for synchrony derived from persisted correlograms or spike-time coincidence counts. Yes only if specifically using SpikeInterface `quality_metrics` synchrony columns, which are diagnostic/transient and not persisted as a reusable per-unit table. |
| network analyses | Step 1 curated sorting or NWB-Zarr `units/spike_times`; Step 1 analyzer `correlograms`; unit locations from NWB-Zarr | No for population rates, bursts, pairwise correlations, correlogram networks, graph summaries, and spatially annotated networks. Yes only for analyses requiring non-persisted features such as per-spike amplitudes, principal components, or individual waveform snippets. |

## Minimal Loader API

The first implementation exposes read-only table loaders. It does not recompute
missing SpikeInterface extensions by default.

```python
load_step2_manifest(path=None) -> pandas.DataFrame
```

Loads `step2_full_manifest.csv` and returns one row per submitted well.

```python
paths_from_manifest_row(row) -> dict[str, Path]
```

Returns only the paths required for the master table.

```python
is_completed_well(paths, require_step2_labels=False) -> bool
```

Checks for the curated sorting, Kilosort labels, analyzer, and templates.

```python
load_master_unit_table(manifest=None, manifest_path=...) -> tuple[pandas.DataFrame, pandas.DataFrame]
```

Builds the canonical table across all completed manifest wells and returns a
second skipped-well diagnostics table.

```python
load_master_unit_table_for_well(row) -> pandas.DataFrame
```

Builds the table rows for one well.

## Design Rules for Analysis Modules

1. Load the canonical Step 3 master table before reopening per-well outputs.
2. Reopen Step 1/Step 2 well assets only when the analysis requires data not
   represented in the master table.
3. Use existing AIND outputs whenever possible.
4. Treat the Step 1 curated sorting as the canonical spike/unit source when a
   per-well reopen is required.
5. Treat the Step 1 SortingAnalyzer as the canonical SpikeInterface object when
   a per-well reopen is required.
6. Treat Step 2 labels as metadata, not the current primary inclusion gate.
7. Treat NWB-Zarr as the portable export and source for persisted unit locations
   and waveform summaries.
8. Do not assume per-unit quality metric tables, template metric tables,
   principal components, individual waveforms, per-spike locations, or full
   per-spike amplitudes are persisted.
9. If a future analysis requires a missing derived asset, that should be a
   separate downstream analysis cache decision, not a recovery-pipeline change.
