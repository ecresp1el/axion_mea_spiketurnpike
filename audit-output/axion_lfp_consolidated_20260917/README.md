# Consolidated Axion file metadata and LFP readiness

Start with the [complete handoff](../../docs/AXION_LFP_CONSOLIDATED_HANDOFF_20260917.md).

18 longer recordings support LFP analysis after epoch/channel QC; one additional 5.25s clip is for trace inspection. This corrects the earlier assumption that all eight dorsal/ventral exports named 1–200Hz were usable: three had 200Hz acquisition high-pass.

- `canonical_recordings_readiness.csv`:58 acquisitions plus the unlocated DIV140 dataset.
- `candidate_manifest.csv/json`:101 physical raw files, variants/copies, and complete preserved metadata.
- `combined_well_metadata.csv`:630 stored/curated well records.
- `lfp_selected_recordings.csv` and `lfp_selected_wells.csv`:19 voltage-accessible originals and 114 well records, with the short clip and empty wells flagged.
- `signal_qc/`:three sampled windows per recording, calibrated1kHz previews, PSDs, and detailed checks.
- `example_full_D235_A1_1khz/`:complete 120s,64-electrode A1 example export.
- `lfp_sampled_spectra_overview.pdf`:sampled spectral checks for all 19 originals.

Original raw files, notebooks, and earlier data inventories are preserved. See the handoff for biological assignments, exclusion reasons, exact scope of validation, and executable extraction instructions.
