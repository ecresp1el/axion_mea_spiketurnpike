# Embedded Axion well metadata

Read-only source audit, 2026-09-17. Original raw and plate-map files were not modified.

**LFP eligibility update:** use the [consolidated handoff](../../docs/AXION_LFP_CONSOLIDATED_HANDOFF_20260917.md). The stored well-label audit below is preserved, but three of the eight dorsal/ventral exports named1–200Hz have200Hz acquisition high-pass and are not conventional LFP sources: H1 plate133-1555 exp17_3(001), (002), (003). Of the five remaining dorsal/ventral originals, one is only5.25s. The current approved acquisition set is13 newer fusion +4 longer dorsal/ventral +1 oldLFP, with the short clip retained separately.

Axion WellTreatment tags were decoded using the layout in the locally installed AxionFileLoader `WellInformation.m`. Header chains were traversed by seeking over voltage data, retaining the latest revision per tag GUID. Labels below are stored user-entered annotations, not independently verified biological identities.

## LFP-capable fusion recordings

- [Six-well label matrix](lfp_well_label_matrix.csv): the 13 newly identified 2026 fusion recordings plus the previously identified April 17, 2024 LFP recording.
- [Detailed 2026 metadata](lfp_recordings_embedded_well_metadata.csv): 78 well records across the 13 recordings, including labels, additional information, enabled/control flags, treatment amount fields, source path, and tag revision.
- Twelve of the 13 newer recordings have labels for all six wells. Across those files, 64 entries name samples/treatments and eight explicitly say `empty`/`Empty`.
- `D307_EX14_Fusions_F5_85F_G12_with sc79(000).raw` has six blank well labels. Its filename does not establish a well-by-well allocation.
- All eight matching 1–200 Hz exports have the same labels and enabled/control flags as their primary raw files.
- Additional-information fields are blank and treatment amounts/units are unpopulated throughout these 13 recordings. The metadata does not provide a full code-to-genotype mapping or dose specification.
- All wells, including those labeled empty, are enabled. All control flags are false, including vehicle/no-drug conditions. Use the textual labels and experimental records to assign analysis groups; neither flag proves sample presence or treatment identity.
- The old 2024 LFP recording labels A1/A2 `79B fusion CV EX4`, A3 `79B fusion MW EX10`, and B1–B3 `H9 Fusion CV EX4`.
- Those generic `fusion` labels do not distinguish cortical–cortical controls from cortical–MGE assembloids. For the separate DIV140 dataset, historical cohort selection and saved plot outputs strongly support **A1–A3 = CxCx controls; B1–B3 = CxMGEO assembloids**. The inferred assignment is preserved separately from raw labels; DIV140 raw acquisition and LFP suitability remain unresolved. See [DIV140 comparison evidence and saved figures](../axion_2024_inventory_20260917/DIV140_COMPARISON_EVIDENCE.md).

## Dorsal/ventral LFP exports

[Detailed stored labels](dorsal_ventral_lfp_embedded_well_metadata.csv) cover eight May 28, 2026 1–200 Hz exports and 48 wells. Three files contain explicit dorsal/ventral labels; five contain blank labels.

- `h1_dorsal_and_ventral_exp17_2(001)`: A1–A3 are stored as `H1 Ventral SOSR`; B1–B3 as `H1 Dorsal SOSR`.
- The PV-reporter `exp17_2(000)` and `exp17_2_round2(000)` files store A1–A3 as `CL 23 PV Ventral SOSR` and B1–B3 as `CL 23 PV Dorsal SOSR`.
- The repo's `docs/GREATLAKES_KILOSORT_HANDOFF.md`, around line 1061, explicitly corrects B1/B2 of the H1 plate 134-0150 `exp17_2(001)` recording to **ventral** based on human notes. The CSV intentionally retains the original embedded labels; it does not overwrite this curated correction.

## Other fusion archive

[Other fusion metadata](other_fusion_recordings_well_metadata.csv) includes available tags from the 32 spike-band-only raw files under `Fusion MEA`, plus three standalone plate maps. Thirty of the 32 raw files have six well tags each: 149 sample/treatment names, 15 explicit empty entries, and 16 blanks. Two files lack well tags. All three standalone plate maps have six named entries.

Some annotations appear stale: a D169 filename retains well labels saying D146, and some EX13/EX14 filenames have tags saying EX15. Preserve these discrepancies for reconciliation against experimental notes. The presence of well labels does not change the earlier finding that these 32 files were acquired with a 200 Hz high-pass and are not conventional low-frequency LFP sources.
