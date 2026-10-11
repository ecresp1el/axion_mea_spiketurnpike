# 2024 Axion recording and well inventory

Source audit: 2026-09-17. Original data were read only. The separate 2026 LFP inventory remains in `../assembloid_lfp_inventory_20260917/`.

The [consolidated LFP handoff](../../docs/AXION_LFP_CONSOLIDATED_HANDOFF_20260917.md) now includes independent signal checks and a working exporter. The dedicatedD235 LFP file supports low-frequency analysis; the four NeuralSpikes acquisitions are excluded from conventional LFP based on their analog mode, despite the5Hz digital high-pass field. All metadata below is retained.

Five recordings were found in `/nfs/turbo/umms-parent/MannyAxionMEAscripts_v1/axion_mea_data_organoid_moredata/MEA files/`. Matching archive copies were found elsewhere; they are not counted as additional recordings.

**Scope correction:** these five D212–D235 files are not the whole older comparison dataset. The separate DIV140 analysis supports **A1–A3 = cortical–cortical (CxCx / CO–CO) controls** and **B1–B3 = cortical–MGE (CxMGEO / CO–MGEO) assembloids**, inferred from historical cohort selection, saved plot outputs, and manuscript figure identities. A shared six-well plate is the working reconstruction; its physical identifier and usable DIV140 LFP remain unconfirmed. See [DIV140 comparison evidence and preserved plots](DIV140_COMPARISON_EVIDENCE.md) and the [inferred well map](div140_inferred_well_map.csv). This mapping applies only to DIV140, not to the D212–D235 raw tags below.

All five files contain the same six latest WellTreatment labels:

| Well(s) | Exact embedded label |
|---|---|
| A1, A2 | 79B fusion CV EX4 |
| A3 | 79B fusion MW EX10 |
| B1, B2, B3 | H9 Fusion CV EX4 |

These are stored annotations. CV/MW definitions and genotype mappings were not found in the bounded old script archives. A3 has a different experiment label (EX10) from A1/A2 (EX4). The word `fusion` does not distinguish cortical–cortical controls from cortical–MGE assembloids; these tags alone cannot establish or exclude either composition. Consistent labels across dates do not establish individual specimen continuity.

| Recording name/condition | Duration | Recorded mode | Digital high-pass |
|---|---:|---|---|
| March 25, D212, pre BIC | 299.75 s | Neural Spikes | 5 Hz IIR |
| March 25, D212, with BIC | 300 s | Neural Spikes | 5 Hz IIR |
| March 31, D218, Double Washout | 299.75 s | Neural Spikes | 5 Hz IIR |
| April 17, D235, Spike | 299.75 s | Neural Spikes | 5 Hz IIR |
| April 17, D235, LFP | 120 s | Cardiac Low Amplitude | 0.1 Hz IIR |

All recordings have 384 channels and 12.5 kHz sampling. Digital low-pass is recorded as None. The LFP recording has no referencing; the other four have Median referencing. Durations were derived from the declared continuous-data byte count and decoded channel/sample/block layout. The four Neural Spikes files are not established as equivalent LFP sources by this metadata audit.

The recording names provide the pre-BIC, with-BIC and washout conditions. Per-well additional information, numeric treatment amounts/units, and recording descriptions are blank; no user/system annotation tags were found. All wells have enabled=true and control=false. The control flag should not substitute for the named experimental conditions.

Outputs:

- [Recording and well-label matrix](recording_well_matrix.csv)
- [All 30 well metadata entries](well_metadata.csv)
- [Decoded acquisition settings, recording notes and well tags](embedded_metadata.json)

The March 31 filename says `9B_H9`, while its well tags say `79B`. Both are retained without correcting the original. No separate dorsal/ventral raw acquisitions or sidecar experiment notes were found in the two checked older script archives. This bounded search result does not exclude the separately documented DIV140 cortical–cortical control comparison.
