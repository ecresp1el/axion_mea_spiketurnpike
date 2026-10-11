# Older Axion recordings: LFP feasibility review

Reviewed 2026-09-17. Original recordings, notebooks, and prior audit artifacts were read only. This report adds an interpretation layer; it does not replace acquisition metadata or biological well annotations.

The **April 17, 2024 D235 dedicated LFP recording is the usable older low-frequency candidate**. The other four D212–D235 recordings used a spike-band analog acquisition mode. Their 5 Hz digital high-pass setting does not make them broadband. **The DIV140 cortical-control comparison is documented, but its continuous raw source and LFP acquisition settings have not been located.**

## Acquisition evidence independently rechecked

The first 12,000 bytes of each original raw file were reread and its ASCII Maestro Settings description compared against the preserved `embedded_metadata.json`; all five descriptions match exactly. This was an independent read of original headers, not merely a copy of the earlier interpretation. Files report AxIS, MiddleMan, and Maestro firmware version 2.5.2.1; CytoView MEA 6; 384 channels; 12,500 Hz sampling; and 5.51e-08 V/sample scaling. Digital low-pass is `None` for all five.

| Recording | Duration | Original analog mode | Acquisition digital high-pass | Referencing | LFP disposition |
|---|---:|---|---|---|---|
| 2024-03-25 D212 pre BIC | 299.75 s | Neural Spikes | 5 Hz IIR | Median | Exclude from conventional low-frequency LFP comparison: spike-band analog acquisition |
| 2024-03-25 D212 with BIC | 300 s | Neural Spikes | 5 Hz IIR | Median | Same limitation |
| 2024-03-31 D218 double washout | 299.75 s | Neural Spikes | 5 Hz IIR | Median | Same limitation |
| 2024-04-17 D235 Spike | 299.75 s | Neural Spikes | 5 Hz IIR | Median | Same limitation |
| 2024-04-17 D235 LFP | 120 s | Cardiac Low Amplitude | 0.1 Hz IIR | None | Low-frequency-capable candidate; assess recorded signal quality and usable channels |

Exact original paths, durations, and well tags remain in the [recording matrix](../axion_2024_inventory_20260917/recording_well_matrix.csv), [all decoded metadata](../axion_2024_inventory_20260917/embedded_metadata.json), and [well metadata](../axion_2024_inventory_20260917/well_metadata.csv). Duration values are from the prior byte-count/header-layout audit, not a fresh full-file voltage read.

The dedicated original is [2024-04-17_79B_H9 fusions_D235 dry_Maestro_LFP_(001).raw](</nfs/turbo/umms-parent/MannyAxionMEAscripts_v1/axion_mea_data_organoid_moredata/MEA files/2024-04-17_79B_H9 fusions_D235 dry_Maestro_LFP_(001).raw>).

## Hardware bandwidth versus later filtering

Axion's **legacy AxIS 2.4 User Guide**, section 3.2.1, printed pages 38–39, specifies nominal analog modes: Neural Spikes, 1200× gain, 200–5000 Hz; Cardiac Low Amplitude, 1200× gain, 0.1–2000 Hz. It distinguishes hardware acquisition bandwidth, fixed once recorded, from downstream Digital Filter processing that can be changed during reanalysis. This is manufacturer-authored documentation accessed through a [mirror of the AxIS 2.4 guide](https://www.scribd.com/document/553748244/AxIS-2-4-User-Guide).

The raw files identify version 2.5.2.1; the adjacent-version manual supports the nominal mode interpretation but is not a calibration certificate or exact frequency-response measurement for this instrument. The dedicated LFP therefore supports low-frequency analysis, without establishing a perfectly flat 1–200 Hz response. No analog roll-off order, instrument-specific transfer function, or calibration trace was found in the headers.

The later [AxIS Navigator guide](https://cdn.stemcell.com/media/files/manual/10000031519-MAN_00.pdf), section 3.2.1, again separates hardware bandwidth from software processing, but lists different modern mode specifications. Its 200–3000 Hz Neural Spikes range should not be silently substituted for the legacy table.

Practical consequences:

- Refiltering an original broadband/low-frequency acquisition can produce a new LFP view when those frequencies were captured. Returning to that original is preferable to attempting to reverse a filtered export.
- Acquisition analog filtering has already attenuated frequencies before the stored samples. Applying a 1–200 Hz software filter to the four Neural Spikes originals cannot restore a valid broadband LFP measurement. Low-frequency leakage, noise, slow amplitude envelopes, and spike-derived population rates are not equivalent to an acquired LFP trace.
- The `5 Hz IIR` field is explicitly digital. It is not evidence that the analog passband begins at 5 Hz. The legacy mode table is the reason these four recordings are excluded.
- A digital processor setting that can be changed on replay is distinct from digital filtering already baked into a saved derived voltage stream. `.raw` denotes a container for continuous voltage, not a guarantee of unfiltered acquisition.

The local [Axion loader README](/home/elcrespo/Desktop/AxionFileLoader-main/AxionFileLoader-main/README.md) documents extraction of stored continuous voltage and separate spike waveforms/times; it supplies no operation that reconstructs uncaptured frequencies. The local [filter metadata handoff](/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/docs/DOWNSTREAM_ANALYSIS_DATA_INVENTORY.md:1260) and [parser](/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/src/axion_mea/filter_metadata.py) correctly preserve acquisition analog mode, acquisition digital settings, and each derived filter block separately. No exact legacy analog-bandwidth table was found in the checked local loader/script docs.

## DIV140 cortical controls: biology established by analysis, voltage feasibility unresolved

The preserved [DIV140 evidence](../axion_2024_inventory_20260917/DIV140_COMPARISON_EVIDENCE.md) and [inferred six-well map](../axion_2024_inventory_20260917/div140_inferred_well_map.csv) support A1–A3 as CO×CO controls and B1–B3 as CO×MGEO assembloids. These are strong analysis-based assignments; they are not recovered Axion header labels. The mapping must not be transferred to the D212–D235 plate merely because the well coordinates match.

Historical sources are `/Volumes/Manny2TB/axion_mea_data_organoid_d140/SpikeStuff/all_data.mat` (full comparison) and `all_data_MEA_d140.mat` (historical B-only age cohort). These are spike-analysis outputs, not identified continuous voltage acquisitions. The notebook's saved spike-rate and raster plots cannot establish LFP bandwidth.

A bounded filename inventory covered accessible files under `axion_mea_files_directory`, `MannyAxionMEAscripts_v1`, `MannyTest`, and `MEAscripts` in `/nfs/turbo/umms-parent/`; 148 filenames matched the selected raw/spike/spreadsheet/manifest/inventory/D140 patterns. No additional D140 or cortical-control raw was identified. Older 2024 matches were copies of the same five D212–D235 filenames. Relevant jobs manifests/inventories and local audit records likewise supplied no D140 acquisition path. This was not an exhaustive search of the entire storage system.

The accessible `/nfs/turbo/umms-parent/MannyTest/SpikeStuff/all_data.mat` has generic group `meaplate1`, six wells, and 139 units. Small metadata fields give 299.75 s and 12,500 Hz; all Header fields are empty and text fields are RS/FS classifications only. It has no D140 identity, raw filename, analog settings, or physical plate identifier. `MannyAxionMEAScripts_v1_2` was inaccessible. None of these facts establish absence of a D140 raw on another drive or archive.

## Use in the consolidated LFP inventory

Carry the D235 dedicated LFP forward for signal-quality assessment, with its exact stored mode and its biological-composition uncertainty. Keep the four Neural Spikes files as available spike recordings excluded from conventional LFP analysis. Keep DIV140 as an explicitly tracked **raw-source-needed** comparison with its biological metadata and figure provenance preserved. Sampled spectral power can support the presence of recorded low-frequency variation, but cannot alone prove neural origin or restore the missing D140 acquisition evidence.
