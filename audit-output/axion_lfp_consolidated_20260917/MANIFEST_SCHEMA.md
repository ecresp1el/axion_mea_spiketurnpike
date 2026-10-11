# Consolidated manifest schema and scope

`candidate_manifest.csv` contains 101 physical raw files plus one historical dataset whose original recording is unlocated. The files represent **58 acquisition recordings**: 13 newer fusion recordings, 8 dorsal/ventral recordings, 5 older fusion recordings, and 32 spike-band fusion recordings. Derivatives and archive copies share a `recording_id` with their canonical acquisition; they are not independent recordings.

`preferred_for_lfp=True` selects **19 original files** with low-frequency acquisition settings and readable, complete data regions: 13 newer fusion, 5 dorsal/ventral, and 1 April 2024 LFP recording. This is an acquisition/access decision, not a biological signal-quality verdict. One selected H1 recording is only **5.25 seconds**, and is unsuitable for stable slow-band PSD/coherence estimates. Eighteen selected recordings are at least 120 seconds.

Three H1 plate 133-1555 `exp17_3` recordings, repeats `(001)`, `(002)`, and `(003)`, report an **acquisition high-pass of 200 Hz**, including in their exports named `Filter(1Hz-200Hz)`. Both the originals and those misleadingly named LFP exports are excluded. Thirteen of the sixteen 1–200 Hz exports have compatible acquisition settings; use their corresponding originals when available.

The remaining four canonical 2024 recordings use Neural Spikes analog mode with a 5 Hz digital high-pass. They are retained as restricted candidates rather than approved full-band LFP sources. The 32 other fusion acquisitions use a 200 Hz high-pass and are excluded from conventional LFP analysis. The PV BroadbandProcessor derivative contains two processed streams, including a 100 Hz stream with a 50 Hz Nyquist limit; it is preserved for review but is not preferred over the original.

Key columns:

| Column | Meaning |
|---|---|
| `recording_id` | Stable group ID based on canonical path; groups derived exports and archive copies. |
| `raw_path`, `canonical_source_path`, `variant_role` | Physical file, preferred acquisition provenance, and file role. |
| `preferred_for_lfp`, `lfp_eligibility`, `lfp_reason` | Acquisition-based inclusion and its rationale; downstream signal QC is separate. |
| `sampling_hz`, `voltage_scale`, `channels` | Stored sampling rate, signed volts/count calibration, and channel count. Preserve the calibration sign. |
| `data_start`, `data_bytes`, `duration_s` | First continuous data region offset, byte length, and duration. The BroadbandProcessor has two regions preserved in JSON. |
| `acquisition_*`, `derived_*` | Acquisition filter settings kept separate from later processing settings and cutoff frequencies. |
| `structural_integrity_pass` | All stated dataset regions fit the file, have complete sample/block byte counts, match data pointers, and permit first/last reads. This does not validate every sample or file CRC. |
| `duplicate_evidence` | Old archive copies match file sizes and sampled first/middle/last 1 MiB SHA256 checks. Full-file hashes were not computed. |
| `duration_caution` | Recordings under 30 seconds, retained with explicit duration limitations. |

`combined_well_metadata.csv` contains 630 rows: 606 well positions across raw files, 18 standalone plate-map entries, and six DIV140 inferred assignments. `stored_*` fields preserve decoded raw annotations. `curated_identity`, `assignment_basis`, `assignment_confidence`, and `human_override_applied` preserve interpretation separately. Empty labels and false control flags do not prove tissue identity or absence. For dorsal/ventral recordings with blank labels, the documented plate-map default is retained as a curated assignment; it is not presented as an embedded annotation.

The H1 `134-0150 exp17_2(001)` B1/B2 correction to **ventral** is applied to the original and both filtered variants while retaining their stored `H1 Dorsal SOSR` labels. The separate DIV140 assignment, **A1–A3 CO–CO and B1–B3 CO–MGEO**, is stored as a strong analysis-based inference, with original raw/LFP availability unconfirmed. It is not copied to the D212–D235 well labels.

`candidate_manifest.json` preserves the manifest, all well records, complete decoded recording descriptions, all continuous dataset headers/regions, primary header bytes, raw nonvoltage entry bytes, latest well-tag metadata, and earlier audit records. `inventory_source_provenance.json` records the source audit hashes and exact human-override CSV rows. Original raw files and earlier audit artifacts were not modified by this builder.

Rebuild with `python3.11 audit-output/axion_lfp_consolidated_20260917/build_candidate_manifest.py` from the repository root. The script performs header seeks and bounded reads; it does not load or rewrite full voltage recordings.
