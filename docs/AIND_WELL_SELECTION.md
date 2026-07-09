# AIND Well Selection And Asset Inventory

This step decides which Axion wells should be exported and submitted as independent AIND spike-sorting jobs. It is deliberately a lightweight provenance and activity gate before the expensive raw export, NWB writing, container setup, and Kilosort4 execution.

## What This Step Assumes

- Candidate wells come from the plate map CSV, not from the raw voltage file.
- The continuous `.raw` voltage file is not loaded during selection.
- Activity is scored from the Axion `*_spike_counts.csv` sidecar by summing interval spike counts per well.
- Active electrode counts are scored from electrode columns in `*_spike_counts.csv`, such as `A1_11`.
- Well annotations such as `Active`, `Control`, and `Treatment` are read from the `Well Information` block in `*_spike_list.csv` when that file is present.
- Raw provenance is joined from `matlab_axisfile_raw_metadata_inventory.csv` when exactly one row matches by `raw_file`, `raw_name`, or `recording_stem`.
- The default activity threshold is `min_total_spikes=11`, which means a well needs more than 10 total spikes to pass.

## Methods Used

This gate does not use SciPy signal-processing methods. It does not filter traces, detect spikes from voltage, or estimate noise. The computations are table operations:

- `csv.reader` parses the metadata header and `Well Information` block in `*_spike_list.csv`.
- `pandas.read_csv` loads `*_spike_counts.csv` and optional raw metadata inventory files.
- `pandas.melt` converts Axion's wide spike-count table into long well/electrode tables.
- `pandas.groupby(...).sum()` computes total spikes per well and per electrode.
- Boolean file checks record whether the raw file, spike-count sidecar, spike-list sidecar, plate map, and raw metadata inventory are present.

The actual spike sorting remains downstream in AIND/SpikeInterface/Kilosort4.

## Mapping And Ingestion Boundary

Well selection does not create the final spike-sorting geometry. It only decides
which wells deserve export. The canonical channel mapping is created later by
the per-well raw export as:

```text
data/interim/kilosort_binary/<recording_stem>/<well>/channel_mapping.csv
```

That file is the source of truth for ingestion because it records the binary
channel order, Axion channel identity, well label, electrode row/column, and
physical x/y coordinates. Downstream code must load it through
`src/axion_mea/well_mapping.py` so NWB electrode rows, ProbeInterface JSON,
Kilosort probe dictionaries, and channel-mapping manifests are all derived from
the same table.

## Generated Files

`scripts/select_aind_wells.sh` writes:

- `well_selection_manifest.json`: complete provenance, criteria, assumptions, asset status, summary, and per-well rows.
- `well_selection_manifest.csv`: per-well table for review and batch filtering.

Each well row includes:

- `selected`: whether the well passes the current gate.
- `selection_reason`: `selected` or semicolon-separated rejection reasons.
- `total_spikes`: total Axion spike-count sidecar events for that well.
- `active_electrodes`: electrodes with at least `min_spikes_per_active_electrode`.
- `raw_file_exists`, `spike_counts_csv_exists`, `spike_list_csv_exists`, `raw_metadata_matched`.
- `missing_assets`: missing file assets for the source recording.
- `selection_rank`: rank among selected wells by descending total spikes.

`scripts/inventory_aind_selection_assets.sh` writes:

- `aind_selection_asset_inventory.json`: complete raw-file asset inventory.
- `aind_selection_asset_inventory.csv`: one row per `.raw` file under `--raw-root`.

This inventory is how we keep track of files that cannot yet be evaluated because they are missing `*_spike_counts.csv`, `*_spike_list.csv`, or metadata provenance.

## Example Commands

Inventory all available raw files:

```bash
bash scripts/inventory_aind_selection_assets.sh \
  --raw-root /nfs/turbo/umms-parent/axion_mea_files_directory \
  --plate-map metadata/plate_maps/axion_48_well_opto_plate_map.csv \
  --raw-metadata-inventory /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/metadata/matlab_axisfile_raw_metadata_inventory.csv \
  --output-dir /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_selection_asset_inventory
```

Select useful wells for one recording:

```bash
bash scripts/select_aind_wells.sh \
  --recording-stem 'test_2_25_2026_129-8447_test(000)_full_lumos_settings' \
  --raw-file '/nfs/turbo/umms-parent/axion_mea_files_directory/2_25_2026/129-8447/test(000)_BroadbandProcessor.raw' \
  --plate-map metadata/plate_maps/axion_48_well_opto_plate_map.csv \
  --raw-metadata-inventory /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/metadata/matlab_axisfile_raw_metadata_inventory.csv \
  --output-dir '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/selection' \
  --min-total-spikes 11 \
  --min-active-electrodes 1
```

Prepare only selected wells for parallel export, NWB, and AIND sorting:

```bash
bash scripts/prepare_aind_well_batch.sh \
  --recording-stem 'test_2_25_2026_129-8447_test(000)_full_lumos_settings' \
  --raw-file '/nfs/turbo/umms-parent/axion_mea_files_directory/2_25_2026/129-8447/test(000)_BroadbandProcessor.raw' \
  --selection-manifest '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/selection/well_selection_manifest.csv' \
  --allow-aind-overwrite \
  --aind-input spikeinterface
```

## Scaling Across Recordings

Use `scripts/prepare_aind_recording_batches.sh` when the input is more than one
recording. It accepts a `recordings_manifest.csv` with one row per Axion raw
recording and writes saved scripts for both stages:

- `prepare_all_recordings.sh`: runs well selection when needed, then generates
  each recording's per-well env files, manifests, and `submit_all_wells.sh`.
- `submit_all_recordings.sh`: calls each generated `submit_all_wells.sh` so the
  selected wells become independent Slurm chains.

Minimum manifest:

```csv
recording_stem,raw_file
test_2_25_2026_129-8447_test(000)_full_lumos_settings,/nfs/turbo/umms-parent/axion_mea_files_directory/2_25_2026/129-8447/test(000)_BroadbandProcessor.raw
```

Generate the multi-recording plan:

```bash
bash scripts/prepare_aind_recording_batches.sh \
  --recordings-manifest /path/to/recordings_manifest.csv \
  --raw-metadata-inventory /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/metadata/matlab_axisfile_raw_metadata_inventory.csv \
  --allow-aind-overwrite \
  --aind-input spikeinterface
```

This writes the plan under:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_recording_batches/<manifest_stem>/
```

The important provenance boundary is unchanged: the selector decides which
wells are worth exporting, and the later per-well export creates the canonical
`channel_mapping.csv` used by NWB, ProbeInterface, Kilosort/AIND params, and
source-data remapping.

## Filter Metadata Provenance

As of 2026-07-08, well selection and AIND batch preparation must preserve the
structured Axion filter metadata parsed from `dataset_description`. Do not rely
only on the raw filename or the old single `metadata_high_pass_filter` /
`metadata_high_pass_cutoff` fields.

The inventory and batch manifests now pass through:

```text
filter_metadata_signature
filter_block_count
filter_block_names
filter_blocks_json
derived_high_pass_cutoff_freqs
derived_low_pass_cutoff_freqs
digital_filter_settings_* columns
broadband_processor_high_frequency_digital_filter_* columns
broadband_processor_low_frequency_median_filter_* columns
```

These fields are produced by:

```text
src/axion_mea/filter_metadata.py
src/axion_mea/well_selection.py
scripts/prepare_aind_recording_batches.py
scripts/prepare_aind_well_batch.py
```

The refreshed ground-truth audit containing the corrected columns is:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_20260708_filter_metadata_patch/
```

## Plate-Type Boundary

The current AIND scale-up route is validated for `FortyEightWellLumos` only:
48 wells, 16 electrodes per well, and the 4x4 per-well geometry in
`metadata/plate_maps/axion_per_well_4x4_electrode_geometry.csv`.

The raw inventory can contain other plate families, including SixWell/CytoView
data with 64 electrodes per well. Those recordings must not be passed through
the Lumos-48 route. `scripts/prepare_aind_well_batch.py` now checks raw metadata
and stops unless the recording matches the validated Lumos-48 shape, or
`--allow-unsupported-plate` is explicitly used for development.

## Full-Duration Export

The batch route exports the full recording, not a subset. AxionFileLoader's
documented optional-argument parser supports full recording by omitting the
timespan argument. Therefore generated export env files keep
`EXPORT_DURATION_S=NaN`, and the MATLAB exporter calls:

```matlab
dataSet.LoadData(char(well), LoadArgs.ByElectrodeDimensions)
```

Finite `[start stop]` ranges are only for explicit debugging runs.
