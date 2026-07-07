# Axion to AIND/Kempner Ephys Pipeline Handoff

Date updated: 2026-07-07 10:45 EDT

## Goal

Use the maintained Allen Neural Dynamics ephys pipeline and Kempner's cluster
adaptation instead of rebuilding spike sorting, postprocessing, curation,
visualization, result collection, or NWB-units export ourselves.

This repo should only own the Axion-specific bridge:

- read Axion `.raw`/continuous voltage data,
- resolve the Axion plate family, well map, and per-well electrode geometry,
- write one supported input artifact per well, preferably NWB or another input
  format accepted by the AIND pipeline,
- preserve Axion metadata/provenance,
- launch the upstream workflow so upstream code creates the output tree.

Once Axion data is presented in a supported format, downstream processing should
come from AIND/Kempner methods, not from new local reimplementations.

## Current Operational State

The single-recording gate is complete. A fresh recording-level run using
`*_BroadbandProcessor.raw` completed end-to-end:

```text
recording_stem:
  test_2_25_2026_129-8447_test(000)_full_lumos_settings_fresh_20260706_191012

recording_status: complete_success_with_fallback
candidate_wells: 48
selected_wells: 14
selected_wells_completed: 14
selected_wells_standard_completed: 11
selected_wells_fallback_completed: 3
selected_wells_failed: 0
```

The three sparse wells that failed standard Kilosort4 were automatically routed
through the labeled fallback and completed through `nwb_units`:

```text
B6 -> low_activity_ks4_nt2_npcs2
C7 -> low_activity_ks4_nt2_npcs2
F6 -> low_activity_ks4_nt2_npcs2
```

The current active phase is **raw-ingestion compatibility triage before any new
large scale-up submission**. The `20260706` Lumos scale-up has reached terminal
accounting:

- the previously validated `2_25_2026` recording completed successfully with
  fallback for 3 sparse wells,
- the `2_12_2026` and `2_20_2026` submitted recordings failed during Axion raw
  opening/export before NWB, SpikeInterface, AIND, or Kilosort,
- both primary `.raw` and `*_BroadbandProcessor.raw` variants fail preflight for
  the affected `2_12_2026` and `2_20_2026` logical recordings,
- both primary `.raw` and `*_BroadbandProcessor.raw` variants pass preflight for
  `2_25_2026`.

Do not submit another large export batch from the affected recordings until the
Axion loader compatibility issue is fixed or a different supported ingestion
path is chosen.

Plate handling is now metadata-driven. Raw metadata selects a locked downstream
profile:

```text
FortyEightWell/Lumos metadata:
  plate_family: lumos_48well
  plate_map: metadata/plate_maps/axion_48_well_opto_plate_map.csv
  electrode_geometry: metadata/plate_maps/axion_per_well_4x4_electrode_geometry.csv
  n_chan_bin: 16
  params_template: config/aind_axion_lumos_params.json

SixWell/CytoView metadata:
  plate_family: cytoview_6well
  plate_map: metadata/plate_maps/axion_6_well_plate_map.csv
  electrode_geometry: metadata/plate_maps/axion_per_well_8x8_electrode_geometry.csv
  n_chan_bin: 64
  params_template: config/aind_axion_cytoview6_params.json
```

Do not manually mix these settings. If raw metadata selects SixWell, all
downstream plate map, electrode geometry, channel count, and AIND/Kilosort
params must stay SixWell. If raw metadata selects Lumos 48-well, all downstream
settings must stay Lumos 48-well.

Moving forward, do not deduplicate primary `.raw`, filtered `.raw`, and
`*_BroadbandProcessor.raw` into a single preferred raw variant. Keep every
usable raw variant as its own manifest row with a unique recording stem and
carry filtering/provenance metadata through the manifest. The dataset selector
is an execution detail for that raw row, not a reason to discard other raw
variants.

Representative preflight for the newly uploaded incoming `SixWell` files
completed on `2026-07-07`. These files worked in the current MATLAB Axion File
Loader sense: `AxisFile` opened, the requested dataset resolved, and a 1-second
A1 tiny load succeeded. They are not yet cleared for production AIND submission
because the new SixWell metadata-driven route still needs a one-well smoke run.

```text
incoming preflight root:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_incoming_preflight_20260707_095329

metadata inventory:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_metadata_compare_20260707_094704/raw_metadata_inventory.csv

full incoming metadata inventory:
  incoming rows: 29
  status_counts: {"ok": 29}
  note: this confirms metadata parsing for the incoming set. The deeper
        AxisFile/dataset/tiny-load check was run on the 4 representative files
        below.

dry metadata-routing check:
  input rows: 29 incoming raw variants
  manifest rows emitted: 29
  plate_family counts: {"cytoview_6well": 29}
  dataset counts: {"RawVoltageData": 28, "BroadbandHighFrequency": 1}
  raw_variant counts:
    primary_raw_NeuralSpikes: 7
    primary_raw_NeuralBroadband: 7
    filter_1Hz-200Hz: 7
    filter_200Hz-3kHz: 7
    broadband_processor: 1
  single-well dry prep:
    SixWell A1 generated n_chan_bin=64, 8x8 geometry, and
    config/aind_axion_cytoview6_params.json.
  note: this validates config generation only. It is not yet a production
        AIND smoke run.

standalone file ground-truth audit:
  script: scripts/audit_axion_file_ground_truth.py
  report root:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_20260707_103911
  report files:
    ground_truth_report.md
    summary.json
    raw_files.csv
    logical_recording_groups.csv
    issues.csv
    upload_temp_fragments.csv
  snapshot time: 2026-07-07T10:39:12
  visible .raw files: 65
  logical raw groups: 29
  upload temp fragments: 1
  by scope:
    older_or_existing raw files: 14
    new_upload raw files: 51
  by plate metadata:
    FortyEightWellLumos: 10
    SixWell: 33
    metadata_missing: 22
  by raw variant:
    primary_raw: 29
    broadband_processor_raw: 8
    filter_1Hz-200Hz: 14
    filter_200Hz-3kHz: 14
  important caveat:
    rsync was still moving during this audit; rerun the audit after upload
    completion before treating counts as final.
  current flagged naming/folder issue:
    h1_exp17(000) appears in both:
      incoming/manny4tbum_20260706/5_25_2026/134-0150
      incoming/manny4tbum_20260706/5_25_2026/134-0150/134-0150
    This is likely a duplicate/nesting issue to resolve manually.
  current metadata-missing groups:
    pv_reporter_cl23_dorsal_and_ventral_exp17_2_round2(000)
    ventral_sosrs(000)
    ventral_sosrs(001)
    ventral_sosrs_2(000)
    ventral_sosrs_2_opsin(000)
    ventral_sosrs_2_opsin(001)
    ventral_sosrs_opsin_day3(000)
    ventral_sosrs_opsin_day3(001)
    These may be real gaps only if the metadata inventory remains missing after
    rsync completes and metadata inspection is rerun.
  intended use:
    This audit should be treated as a ground-truth reconciliation layer, not as
    an automatic pipeline driver yet. It is useful for:
      1. confirming every visible raw file is represented,
      2. grouping raw variants and sidecars by folder/stem,
      3. finding duplicate/nested saves,
      4. finding raw files missing metadata matches,
      5. reviewing which logical groups are safe to include in a manifest.
    The pipeline should continue to consume explicit reviewed manifests. After
    uploads are complete and this audit schema stabilizes, we can use
    logical_recording_groups.csv/raw_files.csv to generate candidate manifests,
    but only with a review step that freezes one audit snapshot. Do not let a
    live filesystem audit silently change downstream submissions while rsync or
    metadata inspection is still moving.
  integration recommendation:
    Use this as a preflight/reconciliation gate before manifest generation.
    The clean flow should be:
      raw filesystem -> ground-truth audit -> human-reviewed candidate manifest
      -> metadata-locked pipeline preparation -> one-well smoke -> scale-up.
    This avoids clunky pipeline logic while still giving us a consistent
    accounting source for messy naming and folder saves.

incoming_h1_5_25_primary
  raw: h1_exp17(000).raw
  dataset: RawVoltageData
  plate_type: SixWell
  analog_mode: NeuralSpikes
  duration_s: 856.75
  overall_status: ok
  axisfile_ok: true
  dataset_ok: true
  tiny_load_ok: true

incoming_h1_5_28_small_primary
  raw: h1_dorsal_and_ventral_exp17_2(000).raw
  dataset: RawVoltageData
  plate_type: SixWell
  analog_mode: NeuralBroadband
  duration_s: 5.25
  overall_status: ok
  axisfile_ok: true
  dataset_ok: true
  tiny_load_ok: true

incoming_pv_5_28_broadband
  raw: pv_reporter_cl23_dorsal_and_ventral_exp17_2(000)_BroadbandProcessor.raw
  dataset: BroadbandHighFrequency
  plate_type: SixWell
  analog_mode: NeuralBroadband
  duration_s: 602.75
  overall_status: ok
  axisfile_ok: true
  dataset_ok: true
  tiny_load_ok: true

incoming_pv_5_28_filter_200_3k
  raw: pv_reporter_cl23_dorsal_and_ventral_exp17_2(000)_Filter(200Hz-3kHz).raw
  dataset: RawVoltageData
  plate_type: SixWell
  analog_mode: NeuralBroadband
  duration_s: 602.75
  overall_status: ok
  axisfile_ok: true
  dataset_ok: true
  tiny_load_ok: true
```

Current collector snapshot as of `2026-07-07T09:31:23`:

```text
2_12_2026_129-8447_opto_test_meis2_with_E2opsin(000)_FortyEightWellLumos
  selected_wells: 10
  recording_status: complete_with_failures
  stage_counts: {"ingestion_open_failed": 10, "not_selected": 38}

2_12_2026_129-8447_opto_test_meis2_with_E2opsin(001)_FortyEightWellLumos
  selected_wells: 10
  recording_status: complete_with_failures
  stage_counts: {"ingestion_open_failed": 10, "not_selected": 38}

2_12_2026_129-8447_opto_test_meis2_with_E2opsin(002)_FortyEightWellLumos
  selected_wells: 7
  recording_status: complete_with_failures
  stage_counts: {"ingestion_open_failed": 7, "not_selected": 41}

2_20_2026_129-8447_test(000)_FortyEightWellLumos
  selected_wells: 24
  recording_status: complete_with_failures
  stage_counts: {"ingestion_open_failed": 24, "not_selected": 24}

2_25_2026_129-8447_test(000)_FortyEightWellLumos
  selected_wells: 14
  recording_status: complete_success_with_fallback
  selected_wells_standard_completed: 11
  selected_wells_fallback_completed: 3
  stage_counts: {"aind_completed": 11, "fallback_completed": 3, "not_selected": 34}
```

Status files refreshed by:

```text
bash scripts/summarize_aind_batch_status.sh \
  --output-dir /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/live_status \
  --recording-stem '2_12_2026_129-8447_opto_test_meis2_with_E2opsin(000)_FortyEightWellLumos' \
  --recording-stem '2_12_2026_129-8447_opto_test_meis2_with_E2opsin(001)_FortyEightWellLumos' \
  --recording-stem '2_12_2026_129-8447_opto_test_meis2_with_E2opsin(002)_FortyEightWellLumos' \
  --recording-stem '2_20_2026_129-8447_test(000)_FortyEightWellLumos' \
  --recording-stem '2_25_2026_129-8447_test(000)_FortyEightWellLumos'
```

Updated status outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/live_status/workflow_status_latest.txt
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/live_status/workflow_status_latest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/live_status/workflow_status_latest.json
```

Collector logic was updated on `2026-07-07` so export logs containing the Axion
block-vector metadata warnings and/or the downstream `LookupChannelID` /
`Index must not exceed 2880` signature are reported as:

```text
derived_stage: ingestion_open_failed
export_failure_class:
  axion_metadata_format_compatibility_issue
  or axion_axisfile_lookupchannel_open_failed
```

Current working interpretation after manual Maestro/MATLAB comparison:

```text
The affected .raw files open and function normally in Axion Maestro, so the
recordings are likely valid. The failure is specific to the MATLAB Axion File
Loader path. Header/core metadata can be parsed, including version, data type,
sampling frequency, and channel count, but block-vector metadata checksum and
length checks disagree with the current MATLAB parser's expectations. The
affected files appear to contain a larger metadata block than a known-working
file imported with the same MATLAB environment and Axion File Loader version.
Re-exporting from Maestro reproduces the same MATLAB loader behavior.

Treat this as a metadata-format compatibility issue between these valid Axion
raw files and the current MATLAB Axion File Loader, not as a MATLAB
installation problem and not as evidence that the recording is corrupt.
```

Pinned future work, not proceeding now:

```text
Custom low-level Axion rescue extraction may be possible because Axion's MATLAB
scripts show that the continuous voltage payload is interleaved int16 samples
with a structured channel map. However, the affected files currently produce
untrustworthy parsed data-region offsets through the stock loader, so a rescue
extractor would first need to reconstruct the real data-region boundary and
channel ordering without relying on the failing CombinedBlockVector parser.

Do not feed a custom extractor into AIND until it has been validated against a
known-good file such as 2_25_2026 by comparing the same well/channel/time window
against the official AxisFile/LoadData output.

This is parked as a future bypass/investigation path. The current operational
policy remains: classify the affected files as ingestion_open_failed under the
current loader, avoid treating those wells as running, and avoid large
submissions from affected recordings until a supported ingestion path is chosen.
```

The normal MATLAB export path now also writes a structured failure artifact
before rethrowing loader/export errors:

```text
<EXPORT_OUTPUT_DIR>/binary_export_failure.json
```

For the current Axion loader issue, that JSON records:

```text
analysis_kind: axion_well_kilosort_binary_export_failure
phase: axisfile_open
failure_class: axion_metadata_format_compatibility_issue
  or axion_axisfile_lookupchannel_open_failed
warning_identifier: <last MATLAB warning id>
warning_message: <last MATLAB warning message>
error_message: <MATLAB exception message>
error_report: <full MATLAB getReport output>
raw_file, recording_stem, well, dataset
```

The status collector reads `binary_export_failure.json` first and falls back to
log-signature detection for older jobs that failed before this structured
failure artifact existed.

This keeps raw ingestion/open failures separate from low-activity Kilosort4
failures, which remain handled by the `low_activity_ks4_nt2_npcs2` fallback.

Historical launch state from the initial `20260706` scale-up:

Scale-up launch state as of `2026-07-06T21:02:51`:

```text
logical_recordings_in_manifest: 7
eligible_lumos_recordings_submitted: 5
blocked_sixwell_recordings: 2
selected_well_pipelines_submitted: 65
recording_supervisors_submitted: 5
current_failed_or_cancelled: 0
```

Current checkpoint status:

```text
Submission safe:
  passed
  5 Lumos recordings submitted, 65 selected wells submitted, 5 supervisors submitted.

Export safe:
  not yet
  2_25_2026 has completed export and entered AIND.
  The other four submitted recordings are still in full-series export.

NWB/SI prep safe:
  not yet
  2_25_2026 has entered AIND for all 14 selected wells.
  The other four submitted recordings are waiting on export before NWB/SI prep can run.

AIND/Kilosort entered:
  partially
  2_25_2026 has 14 selected wells in AIND running.
  At least one 2_25_2026 well, A1, has completed spikesort_kilosort4.
  The other four submitted recordings have not reached AIND yet.

Recording safe:
  not yet
  No submitted scale-up recording is terminal yet.
```

Current per-recording collector status as of `2026-07-06T21:02:51`:

```text
2_12_2026_129-8447_opto_test_meis2_with_E2opsin(000)_FortyEightWellLumos
  selected_wells: 10
  current_stage: export_running

2_12_2026_129-8447_opto_test_meis2_with_E2opsin(001)_FortyEightWellLumos
  selected_wells: 10
  current_stage: export_running

2_12_2026_129-8447_opto_test_meis2_with_E2opsin(002)_FortyEightWellLumos
  selected_wells: 7
  current_stage: export_running

2_20_2026_129-8447_test(000)_FortyEightWellLumos
  selected_wells: 24
  current_stage: export_running

2_25_2026_129-8447_test(000)_FortyEightWellLumos
  selected_wells: 14
  current_stage: aind_running
```

Current elapsed-time checkpoint as of `2026-07-06T21:02:51`:

```text
2_12_2026_129-8447_opto_test_meis2_with_E2opsin(000) export jobs
  running since 20:16 EDT, about 46 minutes

2_12_2026_129-8447_opto_test_meis2_with_E2opsin(001) export jobs
  running since 20:19 EDT, about 43 minutes

2_12_2026_129-8447_opto_test_meis2_with_E2opsin(002) export jobs
  running since 20:23 EDT, about 39 minutes

2_20_2026_129-8447_test(000) export jobs
  running since 20:26 EDT, about 36 minutes

2_25_2026_129-8447_test(000) AIND jobs
  running since about 20:32-20:40 EDT, about 22-31 minutes
```

Why this checkpoint is waiting:

```text
1. The current scale-up exports the whole time series for each selected well.
   EXPORT_DURATION_S is intentionally NaN/full-series, not a subset window.

2. Multiple selected wells from the same Axion recording are exported in
   parallel, so those jobs compete for reads from the same large raw file and
   writes to the project output area.

3. Slurm is throttling some downstream work with AssocGrpMemLimit. This means
   the account/user memory limit is saturated, so some tasks are queued even
   though the workflow submitted them correctly.

4. Many downstream axion-export-nwb, axion-aind-si-prep, and axion-aind-nwb jobs
   are PENDING with Dependency because they correctly wait for export jobs to
   finish first.

5. At least one AIND/Kilosort task in the active scale-up has completed:
   2_25_2026 A1 completed spikesort_kilosort4 in about 12 minutes. Final
   recording-level success is still waiting on the remaining wells and final
   units/QC/result collector stages.
```

Follow-up checkpoint as of `2026-07-06T21:10:16`:

```text
The scale-up submission does not impose a recording-level dependency where
2_25_2026 must finish before the other recordings can progress. Each selected
well has its own dependency chain:

  axion-export-well -> axion-export-nwb / axion-aind-si-prep -> axion-aind-nwb

The reason the run looks partly serialized is cluster/resource pressure plus
full-series export cost, not an intentional "finish one recording first" rule.
Slurm showed Kilosort jobs pending for Priority/Resources and many downstream
jobs pending for Dependency.

New status observed after the 21:02 checkpoint:

2_25_2026_129-8447_test(000)_FortyEightWellLumos
  B6 standard AIND job 53023279 failed with the known sparse KS4 template issue:
    n_samples=4 should be >= n_clusters=6
  C7 standard AIND job 53023291 failed with the known sparse KS4 template issue:
    n_samples=2 should be >= n_clusters=6
  C7 was already submitted to low_activity_ks4_nt2_npcs2 fallback and was
  fallback_running.
  B6 was listed as a fallback candidate and should be submitted by the supervisor
  if the supervisor loop continues normally.

2_12_2026_129-8447_opto_test_meis2_with_E2opsin(000)_FortyEightWellLumos
  sacct showed all 10 selected export jobs failed after about 49-54 minutes.

2_12_2026_129-8447_opto_test_meis2_with_E2opsin(001)_FortyEightWellLumos
  sacct showed several selected export jobs failed after about 48-51 minutes;
  other selected wells were still running at the checkpoint.

2_12_2026_129-8447_opto_test_meis2_with_E2opsin(002)_FortyEightWellLumos
  sacct showed A1 export job 53023123 failed after about 50 minutes;
  other selected wells were still running at the checkpoint.

Confirmed 2_12 export failures occurred during AxisFile construction with:
  Index exceeds the number of array elements. Index must not exceed 2880.
  Error in BasicChannelArray/LookupChannel / LookupChannelID

This is separate from the Kilosort low-activity fallback issue. It indicates
some 2_12 BroadbandProcessor files may have Axion channel metadata that the
current export path cannot parse cleanly during full-series loading.
```

Correction checkpoint as of `2026-07-06T21:20:04`:

```text
The Axion LookupChannelID / "Index must not exceed 2880" export-open failure is
not limited to 2_12. It has been observed in 4 of the 5 submitted Lumos
BroadbandProcessor recordings.

Affected submitted recordings with the exact signature:

2_12_2026_129-8447_opto_test_meis2_with_E2opsin(000)_FortyEightWellLumos
  10/10 selected export logs contain the signature.
  sacct shows 10/10 export jobs failed.

2_12_2026_129-8447_opto_test_meis2_with_E2opsin(001)_FortyEightWellLumos
  10/10 selected export logs contain the signature.
  sacct shows 10/10 export jobs failed.

2_12_2026_129-8447_opto_test_meis2_with_E2opsin(002)_FortyEightWellLumos
  7/7 selected export logs contain the signature.
  sacct shows 7/7 export jobs failed.

2_20_2026_129-8447_test(000)_FortyEightWellLumos
  12/24 selected export logs contained the signature at this checkpoint.
  sacct showed multiple export jobs failed and others still running.

Not affected at this checkpoint:

2_25_2026_129-8447_test(000)_FortyEightWellLumos
  0/14 export logs contain the signature.
  14/14 export jobs completed and the recording entered AIND.

Interpretation:
  The issue is broader than a single recording date or opto recording. It is a
  BroadbandProcessor/raw-open compatibility problem affecting most submitted
  recordings except the previously validated 2_25 file. The next diagnostic
  should compare primary .raw vs *_BroadbandProcessor.raw for affected
  recordings using the debug AxisFile opener before launching more full export
  jobs.
```

Diagnostic preflight submitted as of `2026-07-06T21:32`:

```text
Purpose:
  Determine whether the export failures are caused by the chosen raw variant,
  especially whether primary .raw files can be opened when the matching
  *_BroadbandProcessor.raw files fail.

New diagnostic files:
  matlab/preflight_axion_raw_ingestion.m
  slurm/preflight_axion_raw_ingestion.sbatch

What the diagnostic checks:
  1. peek_axion_raw_metadata(rawFile)
     Metadata/header peep without constructing loadable Axion datasets.

  2. AxisFile(rawFile)
     The exact raw-file open path used by export_axion_well_kilosort_binary.m.
     This is where the current "LookupChannelID / index must not exceed 2880"
     failures occur.

  3. Dataset selection
     RawVoltageData for primary .raw files.
     BroadbandHighFrequency for *_BroadbandProcessor.raw files.

  4. Tiny well load
     LoadData on A1 for a 1 second window, only after AxisFile and dataset
     selection succeed.

Submitted comparison set:

53025406  2_12_000_primary     RawVoltageData           opto_test_meis2_with_E2opsin(000).raw
53025407  2_12_000_broadband   BroadbandHighFrequency   opto_test_meis2_with_E2opsin(000)_BroadbandProcessor.raw
53025408  2_12_001_primary     RawVoltageData           opto_test_meis2_with_E2opsin(001).raw
53025409  2_12_001_broadband   BroadbandHighFrequency   opto_test_meis2_with_E2opsin(001)_BroadbandProcessor.raw
53025410  2_12_002_primary     RawVoltageData           opto_test_meis2_with_E2opsin(002).raw
53025411  2_12_002_broadband   BroadbandHighFrequency   opto_test_meis2_with_E2opsin(002)_BroadbandProcessor.raw
53025412  2_20_000_primary     RawVoltageData           test(000).raw
53025413  2_20_000_broadband   BroadbandHighFrequency   test(000)_BroadbandProcessor.raw
53025414  2_25_000_primary     RawVoltageData           test(000).raw
53025415  2_25_000_broadband   BroadbandHighFrequency   test(000)_BroadbandProcessor.raw

Submission ledger:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_raw_preflight_20260706_2128/submitted_preflight_jobs.tsv

Per-job result location:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_raw_preflight_20260706_2128/<label>/preflight_result.json

Slurm state at follow-up check:
  53025406, the 2_12_000_primary RawVoltageData preflight, was RUNNING.
  The other 9 preflight jobs were PENDING due to Priority/Resources.
  No preflight_result.json files had landed yet.

How to interpret the result:
  If primary .raw passes while BroadbandProcessor fails, the scale-up ingestion
  rule should switch from blindly preferring *_BroadbandProcessor.raw to choosing
  the raw variant that passes preflight.

  If both primary and BroadbandProcessor fail for a recording, the issue is
  broader than the processed raw variant and should be treated as an Axion loader
  incompatibility or corrupted/unsupported raw metadata for that recording.

  If 2_25 remains the only passing recording, it should not be treated as proof
  the scale-up ingestion route is general; it is only proof that this one raw
  variant is compatible with the current loader/export path.
```

Preflight final readout as of `2026-07-07T09:31`:

```text
All 10 Slurm preflight jobs completed with exit 0 and wrote preflight_result.json.
The job exit code only means the diagnostic completed; the JSON status is the
raw-ingestion result.

2_12_000_primary
  raw: opto_test_meis2_with_E2opsin(000).raw
  dataset: RawVoltageData
  peek_ok: true
  axisfile_ok: false
  dataset_ok: false
  tiny_load_ok: false
  overall_status: axisfile_open_failed_after_metadata_peek
  error: Index exceeds the number of array elements. Index must not exceed 2880.

2_12_000_broadband
  raw: opto_test_meis2_with_E2opsin(000)_BroadbandProcessor.raw
  dataset: BroadbandHighFrequency
  peek_ok: true
  axisfile_ok: false
  dataset_ok: false
  tiny_load_ok: false
  overall_status: axisfile_open_failed_after_metadata_peek
  error: Index exceeds the number of array elements. Index must not exceed 2880.

2_12_001_primary
  raw: opto_test_meis2_with_E2opsin(001).raw
  dataset: RawVoltageData
  peek_ok: true
  axisfile_ok: false
  dataset_ok: false
  tiny_load_ok: false
  overall_status: axisfile_open_failed_after_metadata_peek
  error: Index exceeds the number of array elements. Index must not exceed 2880.

2_12_001_broadband
  raw: opto_test_meis2_with_E2opsin(001)_BroadbandProcessor.raw
  dataset: BroadbandHighFrequency
  peek_ok: true
  axisfile_ok: false
  dataset_ok: false
  tiny_load_ok: false
  overall_status: axisfile_open_failed_after_metadata_peek
  error: Index exceeds the number of array elements. Index must not exceed 2880.

2_12_002_primary
  raw: opto_test_meis2_with_E2opsin(002).raw
  dataset: RawVoltageData
  peek_ok: true
  axisfile_ok: false
  dataset_ok: false
  tiny_load_ok: false
  overall_status: axisfile_open_failed_after_metadata_peek
  error: Index exceeds the number of array elements. Index must not exceed 2880.

2_12_002_broadband
  raw: opto_test_meis2_with_E2opsin(002)_BroadbandProcessor.raw
  dataset: BroadbandHighFrequency
  peek_ok: true
  axisfile_ok: false
  dataset_ok: false
  tiny_load_ok: false
  overall_status: axisfile_open_failed_after_metadata_peek
  error: Index exceeds the number of array elements. Index must not exceed 2880.

2_20_000_primary
  raw: test(000).raw
  dataset: RawVoltageData
  peek_ok: true
  axisfile_ok: false
  dataset_ok: false
  tiny_load_ok: false
  overall_status: axisfile_open_failed_after_metadata_peek
  error: Index exceeds the number of array elements. Index must not exceed 2880.

2_20_000_broadband
  raw: test(000)_BroadbandProcessor.raw
  dataset: BroadbandHighFrequency
  peek_ok: true
  axisfile_ok: false
  dataset_ok: false
  tiny_load_ok: false
  overall_status: axisfile_open_failed_after_metadata_peek
  error: Index exceeds the number of array elements. Index must not exceed 2880.

2_25_000_primary
  raw: test(000).raw
  dataset: RawVoltageData
  peek_ok: true
  axisfile_ok: true
  dataset_ok: true
  tiny_load_ok: true
  overall_status: ok

2_25_000_broadband
  raw: test(000)_BroadbandProcessor.raw
  dataset: BroadbandHighFrequency
  peek_ok: true
  axisfile_ok: true
  dataset_ok: true
  tiny_load_ok: true
  overall_status: ok
```

Interpretation after final readout:

```text
Primary .raw does not rescue the affected recordings. The failure occurs in
AxisFile construction for both raw variants, after metadata peek succeeds.

Eligible for current AIND route without loader work:
  2_25_2026_129-8447_test(000)_FortyEightWellLumos

Blocked by Axion loader compatibility:
  2_12_2026_129-8447_opto_test_meis2_with_E2opsin(000)_FortyEightWellLumos
  2_12_2026_129-8447_opto_test_meis2_with_E2opsin(001)_FortyEightWellLumos
  2_12_2026_129-8447_opto_test_meis2_with_E2opsin(002)_FortyEightWellLumos
  2_20_2026_129-8447_test(000)_FortyEightWellLumos
```

Updated goals for `2026-07-07`:

```text
1. Completed: finish the raw-ingestion preflight readout.
   All 10 preflight jobs completed and wrote JSON. The affected recordings fail
   AxisFile for both primary .raw and *_BroadbandProcessor.raw. 2_25 passes for
   both variants.

2. Completed: decide immediate ingestion policy before more scale-up exports.
   Do not continue with the affected 2_12 or 2_20 recordings through the current
   AxisFile/export route. Switching to primary .raw is not sufficient.

3. Completed: separate the two failure classes clearly.
   Class A: raw ingestion/export-open failure:
     AxisFile(rawFile) fails because the current MATLAB Axion File Loader cannot
     handle the file's block-vector metadata format, often surfacing as
     BlockVectorMetaData checksum / Unexpected BlockVectorMetadata length
     warnings and then LookupChannelID / index must not exceed 2880.
     This blocks export before NWB, SpikeInterface, AIND, or Kilosort.

   Class B: low-activity Kilosort4 failure:
     Kilosort4 fails because n_samples/clips < n_templates.
     This is handled by the low_activity_ks4_nt2_npcs2 fallback.

4. Completed: update collector logic for known export-open failures.
   scripts/summarize_aind_batch_status.py now labels export logs or structured
   failure JSON containing the metadata-format warning and/or LookupChannelID /
   2880-index signature as ingestion_open_failed.

5. Preserve reproducibility.
   Every new manifest, preflight command, submitted Slurm command, and result
   summary should live under the project folder with a copied command/env/repro
   path. Avoid repo-root Nextflow/cache clutter.

6. Pinned for later: investigate or bypass the Axion AxisFile compatibility issue.
   Candidate paths:
     patch/override the Axion MATLAB loader for the affected channel metadata,
     use a different Axion-supported export/conversion route,
     acquire/export compatible raw files from AxIS if available,
     or prototype a custom low-level rescue extractor only after validation on
     known-good files. Do not proceed with this extractor work yet.

7. Only after ingestion compatibility is solved, prepare a fresh scale-up.
   Candidate next run should include only recordings/raw variants that pass
   preflight, preserve all available raw/filter variants as separate manifest
   rows, lock downstream configs from raw metadata, submit at recording level
   with per-well dependencies, and keep automatic low-activity fallback enabled.

8. Update this handoff before any new large submission.
   The handoff should state:
     which raw variants are included per biological recording,
     what filtering/provenance metadata each variant carries,
     how many recordings/wells are eligible,
     how many are blocked and why,
     where the submitted commands and live status will be stored.
```

The submitted scale-up recordings are:

```text
2_12_2026_129-8447_opto_test_meis2_with_E2opsin(000)_FortyEightWellLumos: 10 wells
2_12_2026_129-8447_opto_test_meis2_with_E2opsin(001)_FortyEightWellLumos: 10 wells
2_12_2026_129-8447_opto_test_meis2_with_E2opsin(002)_FortyEightWellLumos: 7 wells
2_20_2026_129-8447_test(000)_FortyEightWellLumos: 24 wells
2_25_2026_129-8447_test(000)_FortyEightWellLumos: 14 wells
```

The active scale-up control and status files are:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/recording_batch_plan/submitted_recording_batches.tsv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/recording_batch_plan/submitted_recording_supervisors.tsv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/live_status/workflow_status_latest.txt
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/live_status/workflow_status_latest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/live_status/workflow_status_latest.json
```

The submitted `20260706` run logic was:

```text
1. Use recordings_manifest.csv to include only ready FortyEightWellLumos
   *_BroadbandProcessor.raw recordings.
2. Submit all selected wells in parallel through the generated per-recording
   dependency chains.
3. Run one recording supervisor per submitted recording.
4. Let each supervisor detect sparse standard KS4 failures and submit the
   isolated low_activity_ks4_nt2_npcs2 fallback automatically.
5. Treat the collector outputs as the current ground truth for per-well and
   per-recording status.
```

Current policy after preflight:

```text
Do not reuse that broad *_BroadbandProcessor.raw preference for affected
recordings. 2_12 and 2_20 are blocked for both primary and BroadbandProcessor
variants under the current AxisFile/export route.
```

Scale-up safety checkpoints:

```text
1. Submission safe
   All intended Lumos recordings have submitted well job IDs, SixWell remains
   blocked, and one supervisor exists per submitted recording.

2. Export safe
   For each submitted recording:
     binary_exports_done == selected_wells
   This proves full-series Axion export works across the submitted recordings.

3. NWB/SI prep safe
   For each submitted recording:
     nwb_exports_done == selected_wells
     spikeinterface_prep_done == selected_wells
   This proves the per-well NWB, channel mapping, ProbeInterface, and AIND params
   assets were produced.

4. AIND/Kilosort entered
   For each submitted recording, at least one selected well reaches:
     derived_stage == aind_running
   or its Nextflow trace contains `spikesort_kilosort4`.
   This proves jobs progressed past export/prep into the maintained AIND sorter
   workflow.

5. Recording terminal safe
   Each submitted recording reaches one of:
     complete_success
     complete_success_with_fallback
   with selected_wells_failed == 0 and fallback_failed == 0.

6. Batch terminal safe
   All 5 submitted Lumos recordings are terminal safe.
```

## Historical Validation And Issue Log

The rest of this handoff keeps earlier failures and fixes as provenance. They
are not the active workflow unless explicitly referenced by the current
operational state above.

As of 2026-07-06 15:58 EDT, the single-well A1 AIND smoke test completed
end-to-end.

```text
53002656  axion-aind-nwb  COMPLETED  exit 0  elapsed 23m39s
```

Nextflow final summary:

```text
succeededCount = 11
failedCount = 0
runningCount = 0
pendingCount = 0
```

Completed steps and timings from `nextflow/trace.txt`:

```text
job_dispatch                 COMPLETED  duration 33.9s   realtime 3.4s
nwb_ecephys                  COMPLETED  duration 23.8s   realtime 5.7s
preprocessing                COMPLETED  duration 23.7s   realtime 5.8s
spikesort_kilosort4          COMPLETED  duration 15m15s  realtime 9m34s  14 units
postprocessing               COMPLETED  duration 3m05s   realtime 2m22s
curation                     COMPLETED  duration 59.8s   realtime 7.8s
visualization                COMPLETED  duration 34.8s   realtime 15.5s
results_collector            COMPLETED  duration 54.6s   realtime 22.6s
quality_control              COMPLETED  duration 34.2s   realtime 13.1s
quality_control_collector    COMPLETED  duration 4.9s    realtime 1.4s
nwb_units                    COMPLETED  duration 1m35s   realtime 1m03s
```

This is not an image-build wait. The AIND base, NWB, and Kilosort4 Singularity
images are present in the shared cache, and Nextflow found the cached KS4 image.
The local AIND path-quoting fix for `test(000)` paths worked:
`results_collector`, QC collection, and final `nwb_units` all completed in this
run.

Final organized outputs were written under:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/
```

Observed top-level outputs include:

```text
preprocessed/
spikesorted/
postprocessed/
curated/
visualization/
quality_control/
nwb/
processing.json
quality_control.json
visualization_output.json
nextflow/
repro/
```

Historical note: the A1 gate was the first proof that the AIND workflow could
complete on Axion/Lumos input. That gate is now superseded by the fresh
recording-level run, which completed 14/14 selected wells with 11 standard
completions and 3 automatic fallback completions.

Historical monitoring for the earlier single-recording batch moved away from
manually tailing one trace at a time and used the batch status collector:

```text
bash scripts/summarize_aind_batch_status.sh \
  --recording-stem 'test_2_25_2026_129-8447_test(000)_full_lumos_settings'
```

It writes timestamped and latest summaries here:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batch_status/workflow_status_latest.txt
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batch_status/workflow_status_latest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batch_status/workflow_status_latest.json
```

The collector tallies, per recording and per well:

- candidate wells from the selection manifest,
- selected wells,
- prepared wells,
- submitted wells with real Slurm IDs,
- binary export/NWB export/SpikeInterface prep artifacts,
- current AIND state from Slurm and Nextflow trace files,
- historical attempt count for provenance,
- current derived stage for each well.
- recording-level status:
  `running`, `complete_success`, `complete_with_failures`, `incomplete`, or
  `no_selected_wells`.

Workflow success gates:

```text
Per-well AIND success:
  derived_stage == aind_completed
  and Nextflow trace contains nwb_units COMPLETED.

Per-well accounted terminal state:
  aind_completed, or a documented failed/excluded state with reason.

Per-recording complete_success:
  every selected/included well for that recording is aind_completed.

Per-recording complete_with_failures:
  every selected/included well is terminal, but at least one well is failed or
  excluded with a documented reason.

Per-recording running:
  at least one selected/included well is still running or pending.
```

When the first rerun well from the 12-well fixed-cache batch reaches
`aind_completed`, update this handoff with:

- well ID,
- parent AIND job ID,
- completed Nextflow task count,
- output root,
- confirmation that `nwb_units` completed,
- any unit/spike summary available from AIND output.

When the recording reaches a terminal state, update the whole workflow section
with the recording-level result:

- total candidate wells,
- selected/included wells,
- completed wells,
- failed/excluded wells with reasons,
- final status file path,
- final exact submit command/table paths.

Deployable multi-recording scale-up logic:

```text
For each recording:
  1. Inventory raw/sidecar/metadata assets.
  2. Generate one selection manifest.
  3. Classify wells before sorting:
       standard_sorting
       fallback_candidate_low_activity
       excluded_missing_assets
       excluded_low_activity
  4. Submit standard_sorting wells in parallel.
  5. Track every well independently.
  6. If a standard well completes, mark standard_completed.
  7. If a standard well fails with a known sparse/low-sortability KS4 failure,
     automatically submit exactly one labeled fallback attempt.
  8. If fallback completes, mark fallback_completed.
  9. If fallback fails, mark fallback_failed_low_sortability.
 10. Mark the recording terminal only when every included well is terminal.
```

Important scaling rule: a sparse/fallback well must not block standard wells.
The workflow should continue running all wells that can proceed, while the
problematic wells are routed to fallback or terminal failure states with a clear
reason.

Automatic fallback trigger:

```text
Trigger condition:
  Standard AIND/Kilosort4 reaches spikesort_kilosort4 and fails with
  template-initialization clip count below requested n_templates, for example:
    n_samples=4 should be >= n_clusters=6
    n_samples=2 should be >= n_clusters=6

Action:
  Generate fallback params/env under jobs/aind_fallbacks/<recording>/<label>/.
  Submit fallback AIND job with separate results/work/NXF_HOME roots.
  Record fallback job ID in the status/provenance table.

Guardrails:
  Submit at most one fallback attempt per well per fallback label.
  Do not lower standard KS4 params globally.
  Do not overwrite standard AIND results.
  If fallback fails, mark the well terminal rather than looping forever.
```

Current implementation status:

```text
Already implemented:
  - standard per-well parallel AIND submission,
  - status collector with recording_status and per-well stages,
  - separate low_activity_ks4_nt2 fallback generator/submission script,
  - manual proof submission for B6 and C7 fallback,
  - coupled sparse-well fallback v2 submission for B6, C7, and F6,
  - fallback v2 has now completed the full AIND path through nwb_units for all
    three sparse wells.

Still needed before broad multi-recording deployment:
  - automate fallback detection/submission from the status collector or a
    recording supervisor script,
  - run the same state machine across multiple recordings.
```

Fresh collector snapshot for the first recording after fallback merge support:

```text
Generated: 2026-07-06T19:02:03
recording_status: complete_success_with_fallback
candidate_wells: 48
selected_wells: 14
prepared_wells: 14
submitted_wells_with_real_ids: 13
binary_exports_done: 13
nwb_exports_done: 14
spikeinterface_prep_done: 14
selected_wells_done_or_running: 14
selected_wells_completed: 14
selected_wells_standard_completed: 11
selected_wells_fallback_completed: 3
selected_wells_fallback_running: 0
selected_wells_fallback_failed: 0
selected_wells_failed: 0
selected_wells_running: 0
selected_wells_terminal: 14
aind_running: 0
aind_completed: 11
fallback_completed: 3
fallback_running: 0
fallback_failed: 0
current_failed_or_cancelled: 0
historical_attempts_seen: 89
stage_counts: {"aind_completed": 11, "fallback_completed": 3, "not_selected": 34}
```

Collector output paths:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batch_status/workflow_status_latest.txt
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batch_status/workflow_status_latest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batch_status/workflow_status_latest.json
```

Interpretation of that snapshot:

- The first recording is terminal after merging standard and fallback routes.
- 11 selected wells completed end-to-end through standard AIND.
- 3 selected wells failed standard Kilosort4 with sparse/low-sortability
  template-initialization errors, then completed through fallback v2.
- The fallback wells are now marked `fallback_completed` in the collector:
  B6, C7, F6.
- No AIND jobs from this recording are still running.
- The 12 quick AIND parent failures did not fail during export, NWB, or
  SpikeInterface prep. Those upstream per-well artifacts were produced, and the
  fixed-cache rerun supersedes those failed parent attempts.
- Those 12 AIND parent failures occurred in 4-6 seconds because concurrent
  Nextflow launches were all using the repo-root launch cache:

  ```text
  /home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/.nextflow/cache
  ```

  and collided on the same Nextflow session lock. This is a launcher/cache
  layout bug, not an Axion ingestion bug and not a Kilosort failure.
- B6 reached Kilosort4, so it did not have the lock-collision failure. It then
  failed because low activity produced too few spike clips for the current
  Kilosort4 template setting:

  ```text
  ValueError: n_samples=4 should be >= n_clusters=6
  ```

  B6 was selected from the Axion activity manifest because it had
  `total_spikes=2028`, but only `active_electrodes=1`. That Axion spike count is
  not the same as Kilosort4's internal template-learning clip count. AIND passed
  job dispatch, NWB ecephys, and preprocessing for B6; the failure is inside
  `spikesort_kilosort4`, where Kilosort4/SpikeInterface saw only 4 usable clips
  for KMeans template initialization while the current params request
  `n_templates=6`.

  Current interpretation: B6 is a low-sortability well under the current KS4
  parameters, not a raw export, mapping, NWB, cache, or AIND-launch failure.
  Before broad scale-up, decide whether low-sortability wells should be:
  excluded after the well-selection step, or rerun with a separate conservative
  low-activity KS4 parameter set. Simply lowering `n_templates` may make B6 run,
  but the result may be scientifically weak if only a few clips are available.

Policy for sparse activity:

```text
One active well in a recording:
  Valid. The recording can still be processed. The recording-level summary is
  computed over the one selected well.

One active electrode inside a well:
  Do not treat this as a normal 16-channel per-well Kilosort4 case by default.
  Route it to a low-sortability bucket or an explicit fallback run.
```

The selector already supports this split through `--min-active-electrodes`.
For standard 16-channel AIND/Kilosort4 scale-up, use a stricter standard gate,
for example:

```text
--min-total-spikes 11
--min-active-electrodes 2
--min-spikes-per-active-electrode 1
```

This would prevent B6-like wells from entering the standard route while still
preserving them in the manifest with a reason such as `active_electrodes<2`.
If single-electrode wells are scientifically important, handle them as a
separate named route:

```text
selected_standard:
  enough total spikes and at least the standard active-electrode threshold.

single_electrode_active:
  enough total spikes but only one active electrode; do not silently run with
  standard KS4 params.

excluded_low_activity:
  too few total spikes or missing required assets.
```

The fallback route for `single_electrode_active` should be opt-in and should
write a separate provenance label and parameter file, because lowering
`n_templates` globally to rescue one-electrode wells could weaken results for
normal multi-electrode wells.

Implemented fallback route for sparse/single-electrode wells:

```text
Script:
scripts/prepare_aind_low_activity_fallback.py

Purpose:
Create separate AIND params/env files and a submit script for wells that reached
Kilosort4 but failed because template initialization had fewer clips than
standard n_templates.

Fallback label:
low_activity_ks4_nt2

Fallback params:
n_templates=2
nearest_templates=2
```

This fallback is intentionally separate from standard AIND outputs:

```text
Fallback job/provenance root:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_fallbacks/test_2_25_2026_129-8447_test(000)_full_lumos_settings/low_activity_ks4_nt2

Fallback results root:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_low_activity_ks4_nt2

Fallback work root:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/aind_nextflow_low_activity_ks4_nt2

Fallback NXF_HOME root:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/aind_nextflow_home_low_activity_ks4_nt2
```

B6 and C7 have been submitted to this fallback because they failed standard KS4
with the same template-count failure mode:

```text
B6 standard failure: n_samples=4 should be >= n_clusters=6
C7 standard failure: n_samples=2 should be >= n_clusters=6

B6 fallback AIND parent: 53014414
C7 fallback AIND parent: 53014415
```

Exact fallback command:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_fallbacks/test_2_25_2026_129-8447_test(000)_full_lumos_settings/low_activity_ks4_nt2/submit_low_activity_ks4_nt2_command.txt
```

Submitted fallback table:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_fallbacks/test_2_25_2026_129-8447_test(000)_full_lumos_settings/low_activity_ks4_nt2/submitted_jobs.tsv
```

If `low_activity_ks4_nt2` completes, report it as a fallback success, not a
standard success. If it fails with too few clips even for `n_templates=2`, mark
the well as terminal `fallback_failed_low_sortability` and do not keep lowering
global standard params.

For the final deployable workflow, this fallback submission should happen
automatically after the standard failure is classified. The B6/C7 fallback jobs
listed here were launched manually only to prove the fallback route before
turning it into the automatic supervisor behavior.

Fallback v1 result as of 2026-07-06 17:52 EDT:

```text
B6 fallback parent 53014414 FAILED at spikesort_kilosort4.
C7 fallback parent 53014415 FAILED at spikesort_kilosort4.
```

This proved the fallback submission/provenance separation, but the `nt2`
parameter set is not yet the final sparse-well fallback. It moved past the
original KMeans clip-count error and failed with a KS4 shape mismatch:

```text
B6: could not broadcast input array from shape (16671,5,4) into shape (16671,5,6)
C7: could not broadcast input array from shape (16355,5,2) into shape (16355,5,6)
```

Interpretation: lowering `n_templates` alone is coupled to other KS4 dimensions
that still expect 6 components/templates. The next fallback parameter attempt
should be a new label, not an overwrite of `low_activity_ks4_nt2`, and should
adjust the coupled dimensions such as `n_pcs` along with `n_templates`.

Required isolated fallback v2 change:

```text
New fallback label:
  low_activity_ks4_nt2_npcs2

Only fallback params change; standard params remain unchanged.

Change together:
  n_templates=2
  nearest_templates=2
  n_pcs=2

Do not change globally:
  config/aind_axion_lumos_params.json standard route keeps n_templates=6,
  nearest_templates=16, n_pcs=6.
```

Why these must change together:

```text
Original standard failure:
  Kilosort4 could not initialize 6 templates from only 2-4 usable sparse-well
  clips. This is the n_samples < n_clusters failure.

Fallback v1 mistake:
  low_activity_ks4_nt2 reduced n_templates and nearest_templates to 2 but left
  n_pcs at the standard value of 6.

Fallback v1 failure:
  KS4 then created arrays with the reduced sparse/template dimension but later
  tried to write them into arrays still sized for the old 6-component dimension:
    B6: shape (16671,5,4) into (16671,5,6)
    C7: shape (16355,5,2) into (16355,5,6)

Fallback v2 intent:
  Keep the reduced sparse/template/PCA dimensions internally consistent by
  coupling n_pcs to n_templates for sparse fallback runs only.
```

Code note: `scripts/prepare_aind_low_activity_fallback.py` now defaults
`--n-pcs` to `--n-templates` and documents why. This preserves the standard
parameter file and makes the sparse fallback an explicit, isolated route.

F6 has now also failed standard KS4 with the same original sparse-template
initialization class:

```text
F6 standard failure: n_samples=4 should be >= n_clusters=6
```

F6 should be included in the next sparse-well fallback attempt after the coupled
KS4 fallback parameter set is corrected.

Final standard-route per-well result for first recording:

```text
Completed standard AIND through nwb_units:
  A1, B8, C1, D1, D7, E6, E7, E8, F1, F7, F8

Failed standard Kilosort4 sparse/low-sortability:
  B6: n_samples=4 should be >= n_clusters=6
  C7: n_samples=2 should be >= n_clusters=6
  F6: n_samples=4 should be >= n_clusters=6
```

Fallback v1 result:

```text
B6 fallback low_activity_ks4_nt2 parent 53014414 FAILED.
C7 fallback low_activity_ks4_nt2 parent 53014415 FAILED.
F6 was identified as a fallback candidate after v1 had already proven incomplete.
```

Next fallback action before multi-recording deployment:

```text
low_activity_ks4_nt2_npcs2 has now been prepared and submitted for B6, C7, and
F6.
```

Fallback v2 submission:

```text
Submitted 2026-07-06 18:27 EDT

B6 fallback v2 AIND parent: 53016428
C7 fallback v2 AIND parent: 53016429
F6 fallback v2 AIND parent: 53016430

Exact command:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_fallbacks/test_2_25_2026_129-8447_test(000)_full_lumos_settings/low_activity_ks4_nt2_npcs2/submit_low_activity_ks4_nt2_npcs2_command.txt

Submitted table:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_fallbacks/test_2_25_2026_129-8447_test(000)_full_lumos_settings/low_activity_ks4_nt2_npcs2/submitted_jobs.tsv

Fallback v2 results root:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_low_activity_ks4_nt2_npcs2

Fallback v2 params:
n_templates=2
nearest_templates=2
n_pcs=2
```

Fallback v2 final state as of 2026-07-06 19:05 EDT:

```text
Important distinction:
  Full fallback success is now confirmed for B6, C7, and F6.
  The status collector now merges fallback result roots and reports the first
  recording as complete_success_with_fallback.

B6:
  parent AIND job: 53016428 COMPLETED exit 0, elapsed 22m20s
  Kilosort4 child: 53016467 COMPLETED exit 0
  Kilosort4 trace duration: 14m20s, realtime 13m39s
  postprocessing child: 53016651 COMPLETED exit 0
  postprocessing trace duration: 3m15s, realtime 2m28s
  observed KS4/postprocessing unit count: 14
  nwb_units child: 53016784 COMPLETED exit 0
  quality_control_collector child: 53016810 COMPLETED exit 0

C7:
  parent AIND job: 53016429 COMPLETED exit 0, elapsed 21m48s
  Kilosort4 child: 53016472 COMPLETED exit 0
  Kilosort4 trace duration: 13m05s, realtime 12m55s
  postprocessing child: 53016638 COMPLETED exit 0
  postprocessing trace duration: 3m, realtime 2m44s
  curation child: 53016723 COMPLETED exit 0
  visualization child: 53016733 COMPLETED exit 0
  observed KS4 unit count: 32
  nwb_units child: 53016771 COMPLETED exit 0
  quality_control_collector child: 53016783 COMPLETED exit 0

F6:
  parent AIND job: 53016430 COMPLETED exit 0, elapsed 22m21s
  Kilosort4 child: 53016470 COMPLETED exit 0
  Kilosort4 trace duration: 13m30s, realtime 13m15s
  postprocessing child: 53016637 COMPLETED exit 0
  postprocessing trace duration: 3m, realtime 2m32s
  curation child: 53016722 COMPLETED exit 0
  observed KS4/postprocessing unit count: 17
  nwb_units child: 53016781 COMPLETED exit 0
  quality_control_collector child: 53016791 COMPLETED exit 0
```

This is the key fallback proof so far: the original standard failures
(`n_samples=2-4 should be >= n_clusters=6`) and the fallback v1 shape mismatch
were both avoided by coupling `n_templates`, `nearest_templates`, and `n_pcs`
to 2 for the isolated sparse-well fallback route.

True single-recording result, after counting fallback v2:

```text
candidate_wells: 48
selected_wells: 14
standard_completed_through_nwb_units: 11
standard_failed_then_fallback_completed: 3
unresolved_selected_wells: 0
true_recording_status: complete_success_with_fallback
```

Implemented collector change: `scripts/summarize_aind_batch_status.py` now
discovers `jobs/aind_fallbacks/<recording>/<label>/submitted_jobs.tsv`, reads
each fallback manifest/result root, parses fallback Nextflow traces, and
promotes a standard failed well to `fallback_completed` when the fallback trace
contains `nwb_units COMPLETED`.

Reproducible cache/layout rule for future AIND scale-up:

```text
Container image cache:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/containers/aind_ephys

Singularity/Apptainer build/cache/temp:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/aind_singularity_cache
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/aind_singularity_tmp

Nextflow work directory:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/aind_nextflow/<recording>/<well>

Nextflow launch/session cache:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/aind_nextflow/<recording>/<well>/launch/.nextflow

Nextflow home/framework/plugin cache:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/aind_nextflow_home/<recording>/<well>

Final AIND results and trace:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/<recording>/<well>/nextflow
```

The repo-root `.nextflow/` directory was an accidental historical artifact from
launching AIND while the Slurm working directory was the repo root. After the
pre-fix E7 jobs were cancelled, it was moved out of the repo and preserved here
for provenance:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/legacy_repo_root_nextflow_cache/.nextflow_20260706_1718
```

Future runs should not create `.nextflow/` in the repo root.

Superseding rerun after the Nextflow cache fix:

```text
Submitted 2026-07-06 17:16 EDT
Scope: 12 wells whose AIND parent jobs failed from repo-root Nextflow cache lock collision.
Excluded: A1 because it is complete; B6 because it reached Kilosort and failed
for low-activity/template-count reasons, not the cache collision.

Exact command file:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/rerun_aind_after_nxf_cache_fix_20260706_1716_command.txt

Submit script:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/rerun_aind_after_nxf_cache_fix_20260706_1716.sh

Latest submitted table:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/submitted_aind_rerun_after_nxf_cache_fix_20260706_1716_latest.tsv
```

Rerun AIND parent jobs:

```text
B8  aind=53010957
C1  aind=53010958
C7  aind=53010959
D1  aind=53010960
D7  aind=53010961
E6  aind=53010962
E7  aind=53010963
E8  aind=53010964
F1  aind=53010965
F6  aind=53010966
F7  aind=53010967
F8  aind=53010968
```

The old pre-fix E7 parent `53009954` and Kilosort child `53010442` were
cancelled before the rerun. The rerun is using fresh per-rerun scratch roots:

```text
Rerun work root:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/aind_nextflow_reruns/after_nxf_cache_fix_20260706_1716

Rerun NXF_HOME root:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/aind_nextflow_home_reruns/after_nxf_cache_fix_20260706_1716
```

Confirmed for B8 rerun parent `53010957`:

```text
WORK_DIR=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/aind_nextflow_reruns/after_nxf_cache_fix_20260706_1716/test_2_25_2026_129-8447_test(000)_full_lumos_settings/B8
NEXTFLOW_LAUNCH_DIR=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/aind_nextflow_reruns/after_nxf_cache_fix_20260706_1716/test_2_25_2026_129-8447_test(000)_full_lumos_settings/B8/launch
NXF_HOME=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/aind_nextflow_home_reruns/after_nxf_cache_fix_20260706_1716/test_2_25_2026_129-8447_test(000)_full_lumos_settings/B8
```

The rerun passed the previous immediate lock-collision failure mode: all 12
AIND parent jobs entered `RUNNING`, and Nextflow submitted child
`job_dispatch` jobs instead of failing in 4-6 seconds.

Initial selected-well scale-up submission, now historical/failed:

```text
Submitted 2026-07-06 16:33 EDT
Scope: 13 selected wells remaining after completed A1
Command file:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/submit_remaining_after_A1_command.txt
Submit script:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/submit_remaining_after_A1.sh
Submitted job table:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/submitted_remaining_after_A1_20260706_163355.tsv
Latest pointer:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/submitted_remaining_after_A1_latest.tsv
```

Initial failed dependency chains:

```text
B6  export=53006868  nwb=53006869  spikeinterface=53006870  aind=53006871
B8  export=53006872  nwb=53006873  spikeinterface=53006874  aind=53006875
C1  export=53006876  nwb=53006877  spikeinterface=53006878  aind=53006879
C7  export=53006881  nwb=53006882  spikeinterface=53006883  aind=53006884
D1  export=53006885  nwb=53006886  spikeinterface=53006887  aind=53006888
D7  export=53006889  nwb=53006890  spikeinterface=53006891  aind=53006892
E6  export=53006894  nwb=53006895  spikeinterface=53006896  aind=53006897
E7  export=53006898  nwb=53006899  spikeinterface=53006900  aind=53006901
E8  export=53006902  nwb=53006903  spikeinterface=53006904  aind=53006905
F1  export=53006906  nwb=53006907  spikeinterface=53006908  aind=53006909
F6  export=53006910  nwb=53006911  spikeinterface=53006912  aind=53006913
F7  export=53006914  nwb=53006915  spikeinterface=53006916  aind=53006917
F8  export=53006918  nwb=53006919  spikeinterface=53006920  aind=53006921
```

All 13 export jobs in this initial 16:33 submission failed at MATLAB export.
These job IDs are retained only for provenance; the active fixed submission is
the B6 no-timespan retry plus the 12-well relaunch listed below.

Scale-up failure and fix:

```text
Observed 2026-07-06 16:37-16:40 EDT
All 13 remaining selected wells failed at the first MATLAB export step.
No failed well reached NWB export, SpikeInterface prep, AIND, or Kilosort.
```

The failed export logs all had the same AxionFileLoader error:

```text
Invalid argument #4 to load_AxIS_file
...
waveforms = dataSet.LoadData(char(well), "all", timeRange, LoadArgs.ByElectrodeDimensions);
```

Root cause: the batch generator wrote `EXPORT_DURATION_S=NaN`, and
`export_axion_well_kilosort_binary.m` converted that to the string `"all"`.
AxionFileLoader's documented optional-argument parser supports full recording
by omitting the timespan argument; it does not support passing `"all"` in that
position when `LoadArgs.ByElectrodeDimensions` is also supplied. The fix is
therefore not a subset export and not a forced finite time window. The fix is
to keep `EXPORT_DURATION_S=NaN` as the full-recording request and call:

```text
dataSet.LoadData(char(well), LoadArgs.ByElectrodeDimensions)
```

When a finite debug duration is explicitly requested, the exporter uses
`LoadData(well, [start stop], LoadArgs.ByElectrodeDimensions)`.

Code changes made:

- `scripts/prepare_aind_well_batch.py` now defaults `--export-duration-s` to
  `NaN`, meaning whole recording. It still accepts a finite duration only for
  debugging.
- `matlab/export_axion_well_kilosort_binary.m` now omits the AxionFileLoader
  timespan argument for full-recording export instead of passing `"all"`.
- `scripts/prepare_aind_well_batch.py` now guards plate type. The current AIND
  scale-up path is validated only for `FortyEightWellLumos` /
  `well_dimensions=[6 8]` / `electrode_dimensions=[6 8 4 4]` /
  `num_channels=768`. SixWell/CytoView data must not use this route until it
  has its own plate map, per-well geometry, channel count, and Kilosort/AIND
  parameter set.
- `scripts/prepare_aind_recording_batches.py` now forwards
  `--raw-metadata-inventory` into per-recording batch preparation so duration
  and plate-type validation also work during multi-recording scale-up.

Regenerated current project batch files after the fix. Per-well export env files
now again show whole-recording export:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/well_batch_manifest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/<well>/export_binary.env
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/<well>/submit_commands.sh
EXPORT_DURATION_S=NaN
```

Historical focused retry for B6 with finite `[0 900]` completed export, NWB,
and SpikeInterface prep, but its AIND parent was cancelled when the route was
corrected to the no-timespan full-series API:

```text
B6 retry submitted 2026-07-06 16:48 EDT
export=53008559  nwb=53008560  spikeinterface=53008561  aind=53008562
```

Current focused retry for B6 with the no-timespan full-series API:

```text
B6 retry submitted 2026-07-06 after no-timespan patch
export=53009271  nwb=53009273  spikeinterface=53009275  aind=53009277
```

B6 no-timespan proof result:

```text
53009271 axion-export-well       COMPLETED 00:01:48 exit 0
53009273 axion-export-nwb        COMPLETED 00:00:21 exit 0
53009275 axion-aind-si-prep      COMPLETED 00:00:06 exit 0
53009277 axion-aind-nwb          RUNNING as of 2026-07-06 17:00 EDT
```

B6 export log confirms the intended full-series call:

```text
EXPORT_DURATION_S=NaN
Loaded ..., time range all time (timespan argument omitted)
Wrote B6.bin, channel_mapping.csv, binary_export_manifest.json
```

After B6 proved the export fix, the other 12 failed wells were relaunched:

```text
Submitted 2026-07-06 16:59 EDT
Command file:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/submit_remaining_after_no_timespan_B6_command.txt
Latest submitted table:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/submitted_remaining_after_no_timespan_B6_latest.tsv
```

Relaunched 12-well dependency chains:

```text
B8  export=53009927  nwb=53009928  spikeinterface=53009929  aind=53009930
C1  export=53009931  nwb=53009932  spikeinterface=53009933  aind=53009934
C7  export=53009935  nwb=53009936  spikeinterface=53009937  aind=53009938
D1  export=53009939  nwb=53009940  spikeinterface=53009941  aind=53009942
D7  export=53009943  nwb=53009944  spikeinterface=53009945  aind=53009946
E6  export=53009947  nwb=53009948  spikeinterface=53009949  aind=53009950
E7  export=53009951  nwb=53009952  spikeinterface=53009953  aind=53009954
E8  export=53009955  nwb=53009956  spikeinterface=53009957  aind=53009958
F1  export=53009959  nwb=53009960  spikeinterface=53009961  aind=53009962
F6  export=53009963  nwb=53009964  spikeinterface=53009965  aind=53009966
F7  export=53009967  nwb=53009968  spikeinterface=53009969  aind=53009970
F8  export=53009971  nwb=53009972  spikeinterface=53009973  aind=53009974
```

Queue state after relaunch: the 12 export jobs were `PENDING (Priority)`, their
downstream jobs were `PENDING (Dependency)`, and B6 AIND parent `53009277` was
running. B6 AIND had already submitted Nextflow child jobs
`53009975`/`53009976` for preprocessing/NWB ecephys.

## Historical Issues Log

Keep these issues logged because they explain the current implementation and are
the first places to check if scale-up fails:

- Older Kempner `pipeline/kempner_cluster` wrapper is DSL1-era and fragile with
  current Nextflow/JVM. Use maintained AIND `pipeline/main_multi_backend.nf`.
- Initial AIND direct-NWB input opened the A1 NWB but SpikeInterface did not see
  channel-location/probe metadata. The deployable route is currently
  SpikeInterface/binary input with explicit ProbeInterface JSON.
- Base/NWB/KS4 containers use different Python prefixes. The wrapper binds a
  dynamic `/usr/local/bin/python` shim that tries `/opt/conda/bin/python`,
  `/home/miniconda3/bin/python`, and `/usr/bin/python3`.
- Runtime GitHub cloning inside compute jobs timed out. The pinned AIND capsule
  repositories are staged locally and referenced by
  `pipeline/capsule_versions_custom.env`.
- Kilosort4 image pulling on shared storage was slow/opaque. The final KS4 image
  now exists in the shared container cache; use node-local temp only for future
  image conversions.
- Axion `_BroadbandProcessor.raw` is already filtered and median referenced. The
  AIND params use only neutral `astype`, disable motion apply/compute, disable
  Kilosort CAR, and set `skip_kilosort_preprocessing=true`.
- Kilosort4 with `batch_size=60000` hit a tensor size mismatch. Current working
  value is `batch_size=15000`.
- Full AIND postprocessing was too heavy for the smoke test. Current lean
  extensions are `random_spikes`, `templates`, `spike_amplitudes`,
  `template_similarity`, `correlograms`, and `unit_locations`.
- `results_collector` previously failed on `test(000)` because AIND passed
  `${DATA_PATH}` and `${RESULTS_PATH}` unquoted. Local AIND
  `pipeline/main_multi_backend.nf` now quotes those paths in `results_collector`
  and `quality_control`.
- First scale-up submission attempt used older generated per-well
  `submit_commands.sh` files with an `eval` wrapper. Those scripts failed to
  submit real Slurm jobs because `test(000)` paths were unquoted after argument
  expansion. Ignore
  `submitted_remaining_after_A1_20260706_163311.tsv`; it contains placeholder
  labels, not real Slurm IDs. `scripts/prepare_aind_well_batch.py` now emits
  direct `sbatch --parsable` commands, and the project submit scripts were
  regenerated before the real 16:33 submission.
- The real 16:33 submission then exposed a separate export-duration bug: the
  generated env files used `EXPORT_DURATION_S=NaN`, which drove the MATLAB
  exporter into AxionFileLoader's rejected `"all"` argument path. This is fixed
  by preserving `NaN` as the whole-recording request but omitting the timespan
  argument in the MATLAB `LoadData` call.

## Clearly Labeled Upstream Links

- Allen Neural Dynamics maintained pipeline:
  [AllenNeuralDynamics/aind-ephys-pipeline](https://github.com/AllenNeuralDynamics/aind-ephys-pipeline)
- AIND pipeline documentation:
  [aind-ephys-pipeline ReadTheDocs](https://aind-ephys-pipeline.readthedocs.io/en/latest/)
- AIND architecture:
  [Pipeline Architecture](https://aind-ephys-pipeline.readthedocs.io/en/latest/architecture.html)
- Kempner cluster derivative:
  [KempnerInstitute/ephys-spike-sorting](https://github.com/KempnerInstitute/ephys-spike-sorting)
- AIND result collector:
  [AllenNeuralDynamics/aind-ephys-results-collector](https://github.com/AllenNeuralDynamics/aind-ephys-results-collector)
- AIND Kilosort4 capsule:
  [AllenNeuralDynamics/aind-ephys-spikesort-kilosort4](https://github.com/AllenNeuralDynamics/aind-ephys-spikesort-kilosort4)
- AIND job dispatch capsule:
  [AllenNeuralDynamics/aind-ephys-job-dispatch](https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch)

## Important Update

Do not continue trying to force the older Kempner `pipeline/kempner_cluster`
wrapper to run by downgrading Nextflow or Java.

That route did successfully pull containers, but the workflow itself is an older
DSL1-style derivative and is fragile against current Nextflow/JVM behavior. The
better path is to move forward with the maintained AIND repo, especially its
current SLURM/local multi-backend workflow.

Current AIND documentation says:

- current release stream includes `1.3.0` on 2026-07-03,
- SLURM/local deployment uses `pipeline/main_multi_backend.nf`,
- the multi-backend workflow is Nextflow DSL2,
- the pipeline has 11 major steps: job dispatch, preprocessing, spike sorting,
  postprocessing, curation, visualization, result collection, QC, and NWB export,
- outputs are intended to include NWB, QC, and visualization products,
- container images are maintained through GHCR.

Kempner remains useful as a reference for cluster paths, Slurm expectations, and
the relationship to the Allen/AIND capsules, but the next implementation pass
should start from the current AIND pipeline rather than the older Kempner wrapper.

## What Already Worked

Axion-side work:

- Per-well Axion continuous voltage export exists.
- A1 full-length Lumos settings test exists.
- A1 NWB export validates with PyNWB.
- The NWB contains an acquisition `ElectricalSeries` at 12.5 kHz and includes
  electrode table/channel metadata.
- Geometry is corrected to the Lumos 4x4 350 um spacing.

Useful input artifact:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/data/interim/nwb/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/test_2_25_2026_129-8447_test(000)_full_lumos_settings_A1.nwb
```

Current AIND smoke test:

- Job `53002656` completed with exit 0.
- All 11 Nextflow tasks completed with `failedCount=0`.
- Kilosort4 returned 14 units on the full 900 s A1 recording.
- `results_collector`, `quality_control`, `quality_control_collector`, and
  `nwb_units` completed.
- Final outputs were published under:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/
```

Kempner/AIND container setup:

- Slurm job `52959088` completed successfully.
- It pulled the needed AIND/Kempner Singularity images for a Kilosort4 path:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/containers/kempner_ephys/aind-ephys-pipeline-base_si-0.101.2.sif
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/containers/kempner_ephys/aind-ephys-pipeline-nwb_si-0.101.2.sif
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/containers/kempner_ephys/aind-ephys-spikesort-kilosort4_si-0.101.2.sif
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/containers/kempner_ephys/aind-ephys-unit-classifier_si-0.101.2.sif
```

These are older `si-0.101.2` images from Kempner's derivative. They are useful
evidence that Great Lakes can pull/run AIND containers, but they should not be
treated as the final target if current AIND uses newer tags.

## What Did Not Work

The older Kempner wrapper did not complete the A1 run.

Failed jobs:

```text
52959089  axion-kempner-nwb  FAILED
52972323  axion-kempner-nwb  FAILED
```

Failure reasons:

- First failure: current Nextflow rejected old config references like
  `RESULTS_PATH` in `nextflow_slurm.config`.
- After patching that, current Nextflow parsed the config but rejected the old
  DSL1 workflow syntax.
- Forcing legacy parser got further, but current Nextflow no longer supports
  pieces used by that older wrapper, such as `Channel.create`.
- Trying to move to Nextflow `22.10.6` introduced JVM/Capsule issues on Great
  Lakes and would make the pipeline less maintainable.

Conclusion: do not spend more time making the old wrapper run. Use current AIND.

The current AIND route has progressed past the old Kempner/DSL1 problems, but
it has its own Great Lakes deployment blocker.

Current-AIND failed jobs:

```text
52973797  axion-aind-nwb  FAILED
52975962  axion-aind-nwb  FAILED
52976013  axion-aind-nwb  FAILED
52979722  axion-aind-nwb  FAILED
```

Current-AIND failure reasons:

- `52973797`: AIND launched successfully and began pulling
  `docker://ghcr.io/allenneuraldynamics/aind-ephys-pipeline-base:si-0.104.8`,
  but Nextflow killed the Singularity pull at its default 20 minute timeout
  while the SIF was still being created. The log also reported an NFS lock
  problem after the timeout. This was an environment/container staging problem,
  not an Axion data-ingestion problem.
- `52975962`: immediate retry failed before Nextflow because the previous failed
  results directory existed and `AIND_ALLOW_OVERWRITE` was not set.
- `52976013`: retry with overwrite got past image creation. The base image now
  exists:

  ```text
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/containers/aind_ephys/ghcr.io-allenneuraldynamics-aind-ephys-pipeline-base-si-0.104.8.img
  ```

  This run submitted the first AIND process, `job_dispatch`, but the process
  failed when the container tried to clone capsule code from GitHub:

  ```text
  fatal: unable to access 'https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch/':
  Failed to connect to github.com port 443: Connection timed out
  ```

Conclusion: do not keep treating the current blocker as "we need to build the
image." The base image was pulled successfully after increasing the pull
timeout. The runtime GitHub clone blocker was fixed by staging the pinned AIND
capsule repositories locally under:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/aind_capsule_repos
```

and writing:

```text
/home/elcrespo/Desktop/githubprojects/aind-ephys-pipeline/pipeline/capsule_versions_custom.env
```

with `file://` repo URLs. The helper script is:

```text
scripts/stage_aind_capsule_repos.sh
```

A second environment issue was fixed by binding a small `python` wrapper into
the AIND containers as `/usr/local/bin/python`. This is needed because AIND
capsule `run` scripts call `python`, but the maintained `si-0.104.8` images do
not all use the same conda prefix. The wrapper now tries
`/opt/conda/bin/python`, `/home/miniconda3/bin/python`, and `/usr/bin/python3`.
The AIND base/NWB images use `/opt/conda`, while the Kilosort4 image uses
`/home/miniconda3`.

The current AIND smoke path is no longer blocked at container build, GitHub
clone, or Python startup. It reached job dispatch and preprocessing with the
SpikeInterface input route. Job `52979722` then failed in the downstream
`nwb_ecephys` process because PyNWB/HDMF attempted to create a cache under the
read-only container view of `/home/elcrespo`:

```text
OSError: [Errno 30] Read-only file system: '/home/elcrespo'
```

That failure is an AIND container runtime environment issue, not an Axion
ingestion or mapping issue. The Great Lakes launcher/config now set writable
container cache paths:

```text
AIND_CONTAINER_HOME=${PROJECT_ROOT}/scratch/aind_container_home
AIND_XDG_CACHE_HOME=${PROJECT_ROOT}/scratch/aind_xdg_cache
```

and pass `HOME`, `XDG_CACHE_HOME`, and `MPLCONFIGDIR` into Singularity/Apptainer
processes.

Job `52982762` proved that the writable-cache fix worked: `job_dispatch`,
`nwb_ecephys`, and `preprocessing` all completed. It was intentionally cancelled
before Kilosort4 because the source file is an Axion `_BroadbandProcessor.raw`
stream that is already spike-band filtered and median referenced, while the old
AIND params would have high-pass filtered and common-referenced it again.

The corrected filtered-input A1 smoke job that still used an empty custom
preprocessing dict was:

```text
52984141  axion-aind-nwb  CANCELLED before Kilosort4
```

It was cancelled because AIND fast mode overwrote the preprocessing JSON with
`--motion skip`, causing the preprocessing capsule to fall back to highpass +
common reference again. The next corrected smoke job was:

```text
52984769  axion-aind-nwb  CANCELLED before Kilosort4
```

Historical note, superseded: at 2026-07-06 12:25 EDT, job `52984769` had proven
AIND `job_dispatch`, `nwb_ecephys`, and neutral `preprocessing`, but it was
cancelled before Kilosort4 because a stale KS4 Singularity image lock blocked
the sorter image pull. That was an image-staging problem, not an Axion data or
mapping problem.

The corrected preprocessing behavior from those runs remains important. The
preprocessing capsule used only the neutral `astype` step, with motion
compute/apply disabled:

```text
CUSTOM_PREPROCESSING_PIPELINE: {'astype': {'dtype': 'int16'}}
COMPUTE_MOTION: False
APPLY_MOTION: False
Running custom preprocessing pipeline with steps: ['astype']
```

Current replacement fact: the final AIND KS4 image now exists and is reused by
Nextflow:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/containers/aind_ephys/ghcr.io-allenneuraldynamics-aind-ephys-spikesort-kilosort4-si-0.104.8.img
```

Current replacement fact: AIND Kilosort4 execution has been proven on A1. Job
`52992352` completed KS4 with 14 units, job `53000354` completed KS4 again plus
lean postprocessing, curation, and visualization, and post-patch job `53002656`
completed the full AIND path through `results_collector`, QC, and `nwb_units`.

Do not interpret the earlier AIND image blocker as "Kilosort cannot run on Great
Lakes." The older Great Lakes Kilosort handoff documents that the repo's direct
conda/Kilosort path already ran successfully:

```text
docs/GREATLAKES_KILOSORT_HANDOFF.md
Kilosort job 52954130 completed with RUN_KILOSORT_OVERRIDE=true.
Kilosort4 reported 4 total units, 1 good unit, and 217 spikes in the short A1
test output.
```

If the AIND sorter image pull continues to block, the practical fallback is to
run the direct `slurm/run_kilosort_well.sbatch` path against the same exported
per-well binary and canonical `channel_mapping.csv`, then keep AIND integration
as a packaging/provenance target rather than the only path for making sorting
progress.

Standalone visible Kilosort4 image pull attempts:

```text
52987650  aind-ks4-img  CANCELLED
52991272  aind-ks4-img  CANCELLED
52991562  aind-ks4-img  COMPLETED
```

Job `52987650` used visible logs but still used Turbo scratch for
`SINGULARITY_TMPDIR`. It ran for ~22 minutes without producing the final image,
so it was cancelled.

Job `52991272` was intended to use node-local temp but still inherited the
Turbo temp setting, so it was cancelled quickly.

The pull script was then refactored to use node-local temp space by default:

```text
SINGULARITY_TMPDIR=/tmp/${USER}/aind_singularity_tmp_${SLURM_JOB_ID}
```

The successful node-local-temp pull was:

```text
52991562  aind-ks4-img  COMPLETED in 10:50 on gl3052
```

Submitted with saved command:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/container_pulls/submit_pull_aind_kilosort4_container_command.sh
```

The job used node-local `/tmp` with ~270G available:

```text
SINGULARITY_TMPDIR=/tmp/elcrespo/aind_singularity_tmp_52991562
/dev/mapper/arcts_vol1-slurm_tmp  272G  2.0G  270G  1% /tmp
```

The active child process was `mksquashfs`, which confirmed this was container
filesystem compression, not Kilosort execution. The final Kilosort4 image now
exists and should be reused by Nextflow:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/containers/aind_ephys/ghcr.io-allenneuraldynamics-aind-ephys-spikesort-kilosort4-si-0.104.8.img
size: 6.5G
```

After the image pull completed, A1 was resubmitted through the saved
SpikeInterface command. Job `52992101` completed `job_dispatch`,
`preprocessing`, and `nwb_ecephys`, then reached `spikesort_kilosort4` using the
cached image. That KS4 process failed immediately with exit `127`:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/tools/aind_python_shim/python: 2:
exec: /opt/conda/bin/python: not found
```

This was a Python-shim mismatch, not an image-pull problem and not an Axion data
problem. The KS4 image uses `/home/miniconda3/bin/python`, while the base/NWB
images use `/opt/conda/bin/python`.

Fix applied:

- `slurm/run_aind_nwb_well.sbatch` now writes a dynamic Python wrapper that
  tries `/opt/conda/bin/python`, then `/home/miniconda3/bin/python`, then
  `/usr/bin/python3`.
- `config/aind_nextflow_slurm_greatlakes.config` now includes
  `/home/miniconda3/bin` in the container `PATH`.

The wrapper was tested against both containers:

```text
KS4 image -> /home/miniconda3/bin/python 3.12.11
NWB image -> /opt/conda/bin/python 3.11.5
```

The next A1 retry after this fix was:

```text
52992259  axion-aind-nwb  FAILED
```

That job reached real Kilosort4 execution inside the AIND Kilosort4 image, but
failed in Kilosort 4.1.7 template matching with:

```text
RuntimeError: The expanded size of the tensor (425) must match the existing size (815)
```

This was not an image/build failure. It loaded the 900 s, 16-channel A1 binary
and entered Kilosort. The working mitigation is to reduce the Kilosort sorter
`batch_size` from `60000` to `15000`.

After reducing `batch_size`, job `52992352` completed AIND Kilosort4
successfully:

```text
spikesort_kilosort4  COMPLETED  exit 0  realtime 9m 38s
Raw sorting output: KiloSortSortingExtractor: 14 units - 1 segments - 12.5kHz
Sorting output without empty units: UnitsSelectionSorting: 14 units - 1 segments - 12.5kHz
SPIKE SORTING time: 574.12s
```

That is the key proof-of-function point: AIND can run Kilosort4 on the Axion A1
SpikeInterface/binary input on Great Lakes, with the canonical probeinterface
mapping, filtered-input settings, and no repeated CAR/highpass preprocessing.

The same run failed one step later in AIND `postprocessing` because the params
file lacked the explicit `postprocessing.extensions` block required by newer
AIND postprocessing:

```text
ValueError: 'random_spikes' extension is required postprocessing and downstream steps, but not found in parameters
```

The repo default and generated A1 params now include a lean postprocessing
extension block suitable for the smoke test, including `random_spikes`,
`templates`, `spike_amplitudes`, `template_similarity`, `correlograms`, and
`unit_locations`.

After reducing postprocessing to those lean extensions, job `53000354`
progressed further:

```text
job_dispatch          COMPLETED
nwb_ecephys           COMPLETED
preprocessing         COMPLETED
spikesort_kilosort4   COMPLETED, 14 units, SPIKE SORTING time 577.28s
postprocessing        COMPLETED, POSTPROCESSING time 139.71s
curation              COMPLETED, skipped curation because no quality metrics found
visualization         COMPLETED, local visualization generated
results_collector     FAILED, exit 2
```

The remaining failure was not Kilosort, preprocessing, mapping, image pulling,
or postprocessing. It was a shell quoting issue in the local AIND
`results_collector` command: the path contains `test(000)`, and
`pipeline/main_multi_backend.nf` passed `${DATA_PATH}` and `${RESULTS_PATH}`
unquoted. The local AIND repo was patched to quote those path arguments in
`results_collector` and `quality_control`.

The Great Lakes wrapper now also launches a lightweight monitor by default. It
prints Slurm state, `nextflow/trace.txt`, newest `.command.out/.err/.log`, and
recent output directories every 60 seconds into:

```text
<RESULTS_PATH>/nextflow/monitor_<jobid>.log
```

Current retry after the quoted-path patch:

```text
53002656  axion-aind-nwb  submitted 2026-07-06 15:34 EDT
as of 2026-07-06 15:58 EDT:
  parent job         COMPLETED, exit 0, elapsed 23m39s
  all 11 Nextflow tasks completed
  failedCount        0
```

Scale-up gate result: passed. This retry completed
`postprocessing -> curation -> visualization -> results_collector -> QC ->
nwb_units`. The previously observed blocker was `results_collector` shell
quoting for `test(000)` paths; that is patched locally in the AIND repo and
the patched path completed successfully.

Corrected params for the filtered-input route:

```text
job_dispatch.spikeinterface_info.reader_kwargs.is_filtered = true
preprocessing.custom_preprocessing_pipeline = {"astype": {"dtype": "int16"}}
preprocessing.motion_correction.compute = false
preprocessing.motion_correction.apply = false
spikesorting.kilosort4.sorter.do_CAR = false
spikesorting.kilosort4.sorter.skip_kilosort_preprocessing = true
spikesorting.kilosort4.sorter.batch_size = 15000
postprocessing.extensions.random_spikes = present
postprocessing.extensions.templates = present
AIND_RUNMODE = full
```

Note: job `52984769` was generated before the final motion-compute template
patch, so it printed `COMPUTE_MOTION: True` and `APPLY_MOTION: False`.
Because `APPLY_MOTION` was false, that did not modify the voltage series. Job
`52986225` and future regenerated selected-well jobs now use:

```text
preprocessing.motion_correction.compute = false
preprocessing.motion_correction.apply = false
```

## Desired Architecture Going Forward

Keep the repos separate:

```text
/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
/home/elcrespo/Desktop/githubprojects/ephys-spike-sorting
/home/elcrespo/Desktop/githubprojects/aind-ephys-pipeline
```

Recommended source of truth:

1. Current AIND pipeline repo for workflow implementation.
2. Kempner repo for notes about cluster deployment and how they adapted AIND.
3. This Axion repo for data conversion, metadata, geometry, provenance, and
   launch configs only.

Pre-AIND well selection and raw/sidecar asset tracking are documented in
`docs/AIND_WELL_SELECTION.md`. That gate records which raw files have the
required `*_spike_counts.csv` activity asset, optional `*_spike_list.csv`
annotations, raw metadata matches, and which wells pass the current
`min_total_spikes=11` threshold before parallel job preparation.

Canonical per-well channel mapping:

- The per-well `channel_mapping.csv` written by the raw binary export is the
  ground truth for downstream ingestion. It contains the exact binary channel
  order plus Axion channel identity and physical electrode coordinates.
- All ingestion-specific geometry must be derived through
  `src/axion_mea/well_mapping.py`, not copied by hand from another plate map.
- `AxionWellMapping` validates the mapping columns and contiguous
  `channel_index_zero_based` order, then emits the NWB electrode rows,
  SpikeInterface/ProbeInterface JSON, Kilosort probe dictionaries, and a compact
  `*_channel_mapping_manifest.json`.
- The static 4x4 geometry CSV is only an upstream template used to write the
  per-well export. After export, the per-well `channel_mapping.csv` is the
  source of truth.

The output tree should be made by upstream AIND result collection/NWB export
steps, not by our own local sorting wrapper.

Expected upstream-style outputs include:

```text
preprocessed/
spikesorted/
postprocessed/
curated/
nwb/
visualization/
visualization_output.json
data_description.json
processing.json
QC outputs when enabled
```

Exact folder names should follow the current AIND pipeline's result collector
and documentation.

Operational order in the current AIND `main_multi_backend.nf` is:

```text
job_dispatch
  -> nwb_ecephys + preprocessing
  -> spikesort_kilosort4
  -> postprocessing
  -> curation
  -> visualization
  -> results_collector
  -> quality_control + quality_control_collector
  -> nwb_units
```

In plain terms: `preprocessed/` is created before Kilosort, `spikesorted/` is
created by Kilosort, and `postprocessed/` is created afterward from the
preprocessed recording plus sorted spikes. `postprocessing/` does not generate
the first sorted output; it computes analyzer extensions such as random spikes,
templates, amplitudes, correlograms, template similarity, and unit locations.
Final top-level result folders under `RESULTS_PATH` are organized by the AIND
`results_collector`. Before `results_collector` succeeds, many real outputs live
only in Nextflow work directories under `scratch/aind_nextflow/.../capsule/results`.

## Reproducible Deployment Checklist

For a recording/plate to be deployable, keep one saved command and one manifest
for each stage. Do not rely on terminal history.

Required repo/project configuration:

```text
config/greatlakes_project.env
config/aind_axion_lumos_params.json
config/aind_nextflow_slurm_greatlakes.config
/home/elcrespo/Desktop/githubprojects/aind-ephys-pipeline/pipeline/capsule_versions_custom.env
```

Required generated selection/provenance assets:

```text
jobs/aind_selection_asset_inventory/aind_selection_asset_inventory.csv
jobs/aind_batches/<recording_stem>/selection/well_selection_manifest.csv
jobs/aind_batches/<recording_stem>/selection/well_selection_manifest.json
jobs/aind_batches/<recording_stem>/submit_all_wells.sh
```

Per-well generated assets that must exist before AIND sorting:

```text
data/interim/kilosort_binary/<recording_stem>/<well>/<well>.bin
data/interim/kilosort_binary/<recording_stem>/<well>/channel_mapping.csv
data/interim/kilosort_binary/<recording_stem>/<well>/binary_export_manifest.json
data/interim/nwb/<recording_stem>/<well>/<recording_stem>_<well>.nwb
jobs/aind/<recording_stem>/<well>/spikeinterface/*_probeinterface.json
jobs/aind/<recording_stem>/<well>/spikeinterface/*_channel_mapping_manifest.json
jobs/aind/<recording_stem>/<well>/spikeinterface/*_aind_spikeinterface_params.json
jobs/aind/<recording_stem>/<well>/spikeinterface/submit_aind_spikeinterface_command.sh
```

Submit/retry rule:

```bash
bash 'jobs/aind/<recording_stem>/<well>/spikeinterface/submit_aind_spikeinterface_command.sh'
```

The wrapper uses Nextflow `-resume`, so completed tasks should be reused on
retry. If a run fails after Kilosort, completed Kilosort work should be cached.
If a run fails before a task completes, only that incomplete task and its
downstream tasks should rerun. Shared Singularity images are already cached under
the project container directory and should not be pulled again unless the image
tag changes or the cache is removed.

Monitoring files for every AIND run:

```text
results/aind/<recording_stem>/<well>/run_aind_nwb_well_<jobid>.log
results/aind/<recording_stem>/<well>/nextflow/monitor_<jobid>.log
results/aind/<recording_stem>/<well>/nextflow/trace.txt
results/aind/<recording_stem>/<well>/nextflow/nextflow.log
results/aind/<recording_stem>/<well>/repro/
```

## How To Begin The Pipeline From Raw Data

This is the operational starting sequence. It is intentionally split into an
Axion ingestion stage and an AIND execution stage so selection, provenance,
binary export, NWB writing, and AIND execution remain reproducible and
independently inspectable.

### Required Source Assets

For each Axion recording, the bridge expects:

```text
<recording_stem>_BroadbandProcessor.raw or <recording_stem>.raw
<recording_stem>_spike_counts.csv
<recording_stem>_spike_list.csv
metadata/plate_maps/axion_48_well_opto_plate_map.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/metadata/matlab_axisfile_raw_metadata_inventory.csv
```

What each file is used for:

- `.raw`: continuous voltage source for per-well binary export.
- `*_spike_counts.csv`: lightweight activity gate before sorting. This is where
  total spikes and active-electrode counts are computed.
- `*_spike_list.csv`: well annotations such as `Active`, `Control`, and
  `Treatment` when present.
- plate map CSV: defines candidate well IDs and plate position metadata.
- raw metadata inventory: joins raw-file provenance such as plate type,
  duration, sampling rate, raw kind, and source paths.

Assumptions:

- Each well is treated as an independent recording for export, NWB, and AIND
  sorting. The channel count is locked by the metadata-derived plate profile:
  16 channels for Lumos 48-well, 64 channels for SixWell/CytoView.
- Wells on the same plate type share the same per-well electrode geometry:
  4x4 at 350 um for Lumos 48-well, 8x8 at 300 um for SixWell/CytoView.
- Once a well is exported, downstream ingestion reads that well's
  `channel_mapping.csv` as the canonical mapping. The mapping must include
  binary order, well label, Axion channel identity, electrode row/column, and
  x/y coordinates.
- Selection does not open the continuous raw voltage. It only checks file assets
  and reads Axion CSV sidecars.
- The default activity gate is `min_total_spikes=11`, meaning a well needs more
  than 10 total Axion sidecar spikes to proceed.
- Current selected wells for the 2026-02-25 test recording are:

  ```text
  D7 C1 F8 E7 A1 E6 F7 B8 B6 D1 F6 C7 E8 F1
  ```

### Environment Setup

Use the repo wrappers because they source `config/greatlakes_project.env` and
activate the existing conda environment where appropriate.

```bash
cd /home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
bash scripts/create_greatlakes_project_folder.sh
bash scripts/setup_aind_nextflow.sh
```

Important environment files:

```text
config/greatlakes_project.env
config/aind_axion_lumos_params.json
config/aind_nextflow_slurm_greatlakes.config
```

`config/greatlakes_project.env` defines project roots, conda env paths, Slurm
partitions/accounts, AIND paths, Singularity cache paths, and plate-map paths.
`config/aind_axion_lumos_params.json` holds the AIND/Kilosort4 parameters for
Axion/Lumos wells. `config/aind_nextflow_slurm_greatlakes.config` maps AIND
processes to Great Lakes Slurm and now sets a longer
`singularity.pullTimeout = '2h'` / `apptainer.pullTimeout = '2h'`.

### Step 1: Inventory Which Recordings Have Usable Assets

Run this before selecting wells. It answers which raw files do and do not have
the sidecars needed for the activity gate.

```bash
bash scripts/inventory_aind_selection_assets.sh \
  --raw-root /nfs/turbo/umms-parent/axion_mea_files_directory \
  --plate-map metadata/plate_maps/axion_48_well_opto_plate_map.csv \
  --raw-metadata-inventory /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/metadata/matlab_axisfile_raw_metadata_inventory.csv \
  --output-dir /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_selection_asset_inventory
```

Generated files:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_selection_asset_inventory/aind_selection_asset_inventory.json
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_selection_asset_inventory/aind_selection_asset_inventory.csv
```

Current result for the visible raw tree: 14 raw files found, 14 have
`*_spike_counts.csv`, 14 have `*_spike_list.csv`, 14 have raw metadata matches,
and 0 are missing required selection assets.

### Step 2: Select Wells For One Recording

Example for the 2026-02-25 test recording:

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

Generated files:

```text
.../selection/well_selection_manifest.json
.../selection/well_selection_manifest.csv
```

The manifest records selected/rejected wells, spike counts, active electrodes,
missing assets, source raw file, plate mapping, raw metadata match status, and
selection rank. The selector prints the assumptions, asset status, selected
wells, and rejection reason counts to stdout.

### Step 3: Generate Per-Well Job Files And Submit Commands

Use the selection manifest to prepare only wells that pass the activity gate:

```bash
bash scripts/prepare_aind_well_batch.sh \
  --recording-stem 'test_2_25_2026_129-8447_test(000)_full_lumos_settings' \
  --raw-file '/nfs/turbo/umms-parent/axion_mea_files_directory/2_25_2026/129-8447/test(000)_BroadbandProcessor.raw' \
  --selection-manifest '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/selection/well_selection_manifest.csv' \
  --allow-aind-overwrite \
  --aind-input spikeinterface
```

Generated files:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/well_batch_manifest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/well_batch_manifest.json
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/submit_all_wells.sh
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/<well>/export_binary.env
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/<well>/export_nwb.env
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/<well>/prepare_spikeinterface.env
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/<well>/run_aind.env
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/<well>/submit_commands.sh
```

For the 2026-02-25 test, this currently prepares 14 wells.

### Step 4: Slurm Jobs Used By The Pipeline

The batch submit scripts chain four jobs per selected well:

```text
slurm/export_axion_well_binary.sbatch
slurm/export_axion_well_nwb.sbatch
slurm/prepare_aind_spikeinterface_well.sbatch
slurm/run_aind_nwb_well.sbatch
```

Job responsibilities:

- `export_axion_well_binary.sbatch`: loads MATLAB, reads the Axion raw file with
  AxionFileLoader, exports one well's continuous voltage to `A1.bin`-style
  binary, writes `channel_mapping.csv`, `binary_export_manifest.json`, and a
  reproducible submit command.
- `export_axion_well_nwb.sbatch`: activates the conda env from
  `config/greatlakes_project.env`, reads the canonical `channel_mapping.csv`
  through `AxionWellMapping`, packages the binary as a per-well NWB, and writes
  PyNWB/provenance outputs.
- `prepare_aind_spikeinterface_well.sbatch`: activates the same conda env,
  reads `channel_mapping.csv`, and writes the ProbeInterface JSON,
  channel-mapping manifest, AIND SpikeInterface params JSON, and exact AIND
  submit command for the selected well.
- `run_aind_nwb_well.sbatch`: loads OpenJDK and Singularity, stages the NWB as
  provenance, runs current AIND `pipeline/main_multi_backend.nf` with
  SpikeInterface/binary input, and records the exact Nextflow command under the
  result `repro/` folder.

To submit all selected wells:

```bash
bash '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/submit_all_wells.sh'
```

### Step 5: Scale Across Recordings

For many recordings, use a recording manifest instead of manually repeating the
single-recording commands. This is the intended information flow:

```text
recordings_manifest.csv
  -> scripts/prepare_aind_recording_batches.sh
  -> one selection manifest per recording
  -> one per-recording submit_all_wells.sh
  -> scripts-generated submit_all_recordings.sh
  -> independent Slurm chains per selected well
```

Required manifest columns:

```text
recording_stem,raw_file
```

Useful optional columns:

```text
selection_manifest,plate_map,raw_metadata_inventory,spike_counts_csv,spike_list_csv,wells,aind_input,submit,allow_aind_overwrite,min_total_spikes,min_active_electrodes,min_spikes_per_active_electrode
```

Example `recordings_manifest.csv` row:

```csv
recording_stem,raw_file,submit,aind_input,allow_aind_overwrite
test_2_25_2026_129-8447_test(000)_full_lumos_settings,/nfs/turbo/umms-parent/axion_mea_files_directory/2_25_2026/129-8447/test(000)_BroadbandProcessor.raw,true,spikeinterface,true
```

Generate saved prepare and submit scripts:

```bash
bash scripts/prepare_aind_recording_batches.sh \
  --recordings-manifest /path/to/recordings_manifest.csv \
  --raw-metadata-inventory /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/metadata/matlab_axisfile_raw_metadata_inventory.csv \
  --allow-aind-overwrite \
  --aind-input spikeinterface
```

This writes:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_recording_batches/<manifest_stem>/recording_batch_manifest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_recording_batches/<manifest_stem>/prepare_all_recordings.sh
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_recording_batches/<manifest_stem>/submit_all_recordings.sh
```

Then run preparation:

```bash
bash /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_recording_batches/<manifest_stem>/prepare_all_recordings.sh
```

Inspect the generated per-recording `well_batch_manifest.csv` files and saved
`submit_all_wells.sh` files. If the plan is correct, submit all recordings:

```bash
bash /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_recording_batches/<manifest_stem>/submit_all_recordings.sh
```

What is clear now:

- The scaling unit is one well, not one electrode. Each selected well is an
  independent recording for AIND/Kilosort4.
- Wells from the same Axion plate type share geometry logic, but every well gets
  its own `channel_mapping.csv`, binary export manifest, ProbeInterface JSON,
  AIND params, result folder, and saved submit command.
- Across recordings, the wrapper only orchestrates generation/submission. The
  per-well dependency graph remains the proven one from the A1 smoke test.
- Slurm controls actual concurrency. Submitting many wells does not mean they
  all run simultaneously; they become eligible as dependencies and GPU resources
  allow.

What still needs to be measured during scale-up:

- Throughput across many wells/recordings on the shared GPU partition.
- Whether all wells finish with the same lean postprocessing/QC settings.
- Whether any particular raw recording has missing sidecars or metadata that
  prevents the selection gate from producing a usable manifest.
- Whether direct NWB input should be retried after regenerating NWB files with
  the latest mapping metadata. The deployable route remains SpikeInterface input.

Current gate result: A1 completed the final AIND packaging path, including
Kilosort4, lean postprocessing, curation/visualization, `results_collector`, QC
collection, and `nwb_units`. The runtime GitHub-clone issue is handled by local
capsule staging, and the container image pull/build issue is handled by the
shared image cache. The next risk is scale-up behavior across many wells and
recordings, not the single-well AIND path.

### Step 6: Single-Well Current-AIND Smoke Test

For the current A1 SpikeInterface/binary route, the exact submit command is
saved here:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/spikeinterface/submit_aind_spikeinterface_command.sh
```

The older direct-NWB submit commands are still preserved here for provenance,
but they are not the current smoke-test route:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/submit_aind_nwb_well_command.sh
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/submit_aind_nwb_well_retry_allow_overwrite_command.sh
```

Monitoring commands:

```bash
squeue -j <job_id> -o '%.18i %.9P %.32j %.2t %.12M %.12L %.6D %R'
sacct -j <job_id> --format=JobID,JobName%32,State,ExitCode,Elapsed,MaxRSS,NodeList -P
tail -f '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/run_aind_nwb_well_<job_id>.log'
tail -f '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/nextflow/monitor_<job_id>.log'
tail -f '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/nextflow/trace.txt'
```

Current A1 result:

1. Job `53002656` completed successfully with exit 0.
2. The trace advanced through `postprocessing`, `curation`, `visualization`,
   `results_collector`, QC collection, and `nwb_units`.
3. Final `RESULTS_PATH` contains organized top-level output folders, not only
   Nextflow work-dir capsule outputs.
4. The remaining selected-well batch has been launched; monitor each well.
5. Regenerate A1 NWB with the patched NWB writer before retrying direct NWB input;
   the current deployable route remains SpikeInterface/binary input.

### Direct NWB Versus SpikeInterface Input

Direct NWB input reached AIND `job_dispatch`, and AIND opened the existing A1
NWB file, but `se.read_nwb_recording(...).has_channel_location()` returned
false:

```text
acquisition/A1_ElectricalSeries does not have probe information. Skipping.
No recordings found to process after parsing the input folder.
```

That A1 NWB was generated before the NWB writer was patched. SpikeInterface's
NWB extractor expects relative electrode columns named `rel_x`, `rel_y`, and
`rel_z`; the old NWB had normal NWB `x/y/z` columns but not those relative
columns. The writer now gets all electrode rows from `AxionWellMapping` and
writes both `x/y/z` and `rel_x/rel_y/rel_z`. Therefore direct NWB should be
retested only after regenerating the NWB; the old failed file is not evidence
that the mapping fix is absent.

The working ingestion path is:

```text
Axion raw -> per-well binary + channel_mapping.csv -> ProbeInterface JSON -> AIND job_dispatch input=spikeinterface
```

For A1 this was generated with:

```bash
bash scripts/prepare_aind_spikeinterface_well.sh \
  --recording-stem 'test_2_25_2026_129-8447_test(000)_full_lumos_settings' \
  --well A1 \
  --binary-file '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/data/interim/kilosort_binary/test_2_25_2026_129-8447_test(000)_full/A1/A1.bin' \
  --channel-mapping '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/data/interim/kilosort_binary/test_2_25_2026_129-8447_test(000)_full/A1/channel_mapping.csv' \
  --output-dir '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/spikeinterface' \
  --gain-to-uV -0.05484861781483107
```

Generated A1 SpikeInterface files:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/spikeinterface/test_2_25_2026_129-8447_test(000)_full_lumos_settings_A1_probeinterface.json
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/spikeinterface/test_2_25_2026_129-8447_test(000)_full_lumos_settings_A1_channel_mapping_manifest.json
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/spikeinterface/test_2_25_2026_129-8447_test(000)_full_lumos_settings_A1_aind_spikeinterface_params.json
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/spikeinterface/run_aind_spikeinterface.env
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/spikeinterface/submit_aind_spikeinterface_command.sh
```

Submitted A1 SpikeInterface smoke test:

```text
52979722  axion-aind-nwb  FAILED
```

Confirmed progress for `52979722`:

```text
job_dispatch (job-dispatch)  COMPLETED
preprocessing (preprocessing) COMPLETED
```

It found one recording:

```text
test_2_25_2026_129-8447_test(000)_full_lumos_settings_A1
Duration: 900.0 s
Num. channels: 16
```

It then pulled the Kilosort4 image and submitted `nwb_ecephys`, which failed
before Kilosort4 because PyNWB/HDMF tried to create a cache under read-only
`/home/elcrespo`:

```text
OSError: [Errno 30] Read-only file system: '/home/elcrespo'
```

Fix applied after that failure: the AIND launcher/config now set `HOME`,
`XDG_CACHE_HOME`, and `MPLCONFIGDIR` to writable Turbo scratch paths before
running Nextflow. The saved SpikeInterface submit command was then resubmitted
as `52982762`, which completed `job_dispatch`, `nwb_ecephys`, and
`preprocessing`.

```text
52982762  axion-aind-nwb  CANCELLED before Kilosort4
```

That run used the old redundant-processing settings. It was cancelled after raw
metadata confirmed this input is already an Axion BroadbandProcessor spike-band
stream with median referencing.

First corrected filtered-input A1 smoke test:

```text
52984141  axion-aind-nwb  CANCELLED before Kilosort4
```

That run still used AIND fast mode, which overwrote the custom preprocessing
JSON and allowed the default highpass/common-reference preprocessing to run
again. The next corrected filtered-input A1 smoke test was:

```text
52984769  axion-aind-nwb  CANCELLED before Kilosort4
```

It proved AIND ingestion and neutral preprocessing, but was cancelled because a
stale Kilosort4 image lock blocked the sorter image pull. A later visible
node-local-temp pull completed the KS4 image successfully. The follow-up A1
smoke job reached `spikesort_kilosort4`, proving that Nextflow can reuse the
cached KS4 image, but failed on a Python-shim mismatch because the KS4 image
uses `/home/miniconda3/bin/python` instead of `/opt/conda/bin/python`.

Historical corrected filtered-input A1 smoke retry, superseded by successful
job `53002656`:

```text
52992259  axion-aind-nwb  PENDING at submission, reason: Priority
```

Do not monitor `52992259` as the current run. It was part of the historical
debug sequence before the final Python-shim, batch-size, postprocessing, and
path-quoting fixes. The current proof-of-function is completed job `53002656`.

### Filtered BroadbandProcessor Input Policy

The current A1 source is:

```text
/nfs/turbo/umms-parent/axion_mea_files_directory/2_25_2026/129-8447/test(000)_BroadbandProcessor.raw
```

MATLAB raw metadata for this file reports:

```text
Sampling Frequency: 12.5 kHz
Voltage Scale: -5.484861781483107E-08 V/sample
Referencing Method: Median
Analog Mode Setting: Neural Broadband
Broadband Processor High Frequency Digital Filter:
  High Pass Filter: Butterworth, 1 pole, 200 Hz
  Low Pass Filter: Butterworth, 1 pole, 5 kHz
```

Therefore do not re-run a 300 Hz high-pass, common reference/median subtraction,
or Kilosort4 CAR on this already spike-band filtered and median-referenced
input. The Axion/AIND filtered-input params use:

```text
job_dispatch.spikeinterface_info.reader_kwargs.is_filtered = true
preprocessing.custom_preprocessing_pipeline = {"astype": {"dtype": "int16"}}
spikesorting.kilosort4.sorter.do_CAR = false
spikesorting.kilosort4.sorter.skip_kilosort_preprocessing = true
AIND_RUNMODE = full
```

For future regenerated selected-well jobs, the preprocessing motion block is
also disabled:

```text
preprocessing.motion_correction.compute = false
preprocessing.motion_correction.apply = false
```

Why `AIND_RUNMODE=full`: AIND fast mode overwrites the preprocessing args with
`--motion skip`, which prevents the custom preprocessing JSON from reaching the
capsule. The neutral `astype` step is needed because the AIND Kilosort4 capsule
expects a `preprocessed_*` folder from the preprocessing capsule. `astype` does
not high-pass filter, median-reference, whiten, or CAR the voltage series.
Kilosort4 internal preprocessing and CAR are disabled separately.

Evidence from job `52984769` before it was cancelled at the stale Kilosort4
image lock:

```text
INPUT: spikeinterface
sampling_frequency: 12500.0
gain_to_uV: -0.054848617814831066
is_filtered: True
CUSTOM_PREPROCESSING_PIPELINE: {'astype': {'dtype': 'int16'}}
Running custom preprocessing pipeline with steps: ['astype']
```

The previous `52982762` preprocessing provenance showed the old behavior was:

```text
BinaryRecordingExtractor
  -> HighpassFilterRecording
  -> DetectAndRemoveBadChannelsRecording
  -> CommonReferenceRecording
```

That old behavior should not be used for `_BroadbandProcessor.raw` scale-up.

## Next Conversation Starting Point

Do not restart by asking whether AIND can use NWB, what the Kilosort4 parameter
mechanism is, or how Slurm resources map. Those questions are answered below.

Start here instead:

1. Treat A1 job `53002656` as the completed end-to-end proof.
2. Treat the 13-well scale-up submission at 16:33 EDT as failed at MATLAB
   export because it used `EXPORT_DURATION_S=NaN`.
3. Inspect the final A1 output tree if needed:
   `results/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/`.
4. Monitor B6 AIND parent `53009277` and its Nextflow trace under
   `results/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/B6/`.
5. Monitor the 12 relaunched export jobs listed in
   `submitted_remaining_after_no_timespan_B6_latest.tsv`; they should write
   `<well>.bin`, `channel_mapping.csv`, and `binary_export_manifest.json` before
   their NWB/SpikeInterface/AIND dependencies release.
6. For future rest-of-recording submissions, use the generated
   `jobs/aind_batches/<recording_stem>/submit_all_wells.sh`; it has been
   regenerated with the fixed `sbatch --parsable` submit mechanism.
7. For multiple recordings, create a `recordings_manifest.csv`, run
   `scripts/prepare_aind_recording_batches.sh`, then inspect and submit the
   generated `jobs/aind_recording_batches/<manifest_stem>/submit_all_recordings.sh`.
8. Monitor each well with its `run_aind_nwb_well_<jobid>.log`,
   `nextflow/monitor_<jobid>.log`, and `nextflow/trace.txt`.
9. Regenerate A1 NWB before retrying direct NWB input, because the existing A1
   NWB predates the `rel_x/rel_y/rel_z` mapping fix.

Useful files to inspect first:

```text
/home/elcrespo/Desktop/githubprojects/aind-ephys-pipeline/pipeline/main_multi_backend.nf
/home/elcrespo/Desktop/githubprojects/aind-ephys-pipeline/pipeline/capsule_versions.env
/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/aind_nextflow_slurm_greatlakes.config
/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/slurm/run_aind_nwb_well.sbatch
/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/src/axion_mea/well_mapping.py
/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/scripts/prepare_aind_spikeinterface_well.py
```

The specific code path to address is the `clone_repo()` helper in
`main_multi_backend.nf`. The runtime GitHub clone issue is fixed for the current
run by `capsule_versions_custom.env`; do not remove that file unless replacing
it with another local staging strategy.

## Current-AIND Questions Answered

Checked on `2026-07-06` against a fresh local clone of
`AllenNeuralDynamics/aind-ephys-pipeline` at:

```text
39b08d11c8c11f5b64078a9c2e789927518fccab
```

Answers:

1. Use the Axion per-well NWB as a supported AIND input path after regenerating
   it with the patched mapping writer.
   Current AIND docs list NWB as a supported input type, and the pinned
   `aind-ephys-job-dispatch` capsule accepts `--input nwb`. The job-dispatch
   code enumerates available NWB `ElectricalSeries` paths with
   `SpikeInterface` and reads acquisition series directly. The Axion NWB writer
   now creates an acquisition `ElectricalSeries` named `<WELL>_ElectricalSeries`
   with 12.5 kHz sampling, normal NWB `x/y/z`, and SpikeInterface-compatible
   `rel_x/rel_y/rel_z` columns derived from the canonical `channel_mapping.csv`.
   The current active smoke test uses the SpikeInterface binary route because
   it is already past ingestion and preprocessing.

2. The current Kilosort4 parameter mechanism is the AIND top-level JSON
   parameter file passed to `main_multi_backend.nf` with `--params_file`.
   Kilosort4 settings live under:

   ```json
   {
     "spikesorting": {
       "sorter": "kilosort4",
       "kilosort4": {
         "skip_motion_correction": true,
         "min_drift_channels": 17,
         "sorter": {}
       }
     }
   }
   ```

   The nested `spikesorting.kilosort4.sorter` object is forwarded to the
   SpikeInterface Kilosort4 wrapper. AIND's current schema does not accept the
   old direct-run integer `x_centers=4`; the Axion params file leaves
   `x_centers` as `null` because drift correction is disabled with `nblocks=0`,
   `do_correction=false`, `skip_motion_correction=true`, and
   `min_drift_channels=17` for a 16-channel well.

3. Great Lakes resources map through a custom Nextflow config layered after
   AIND's `pipeline/nextflow_slurm.config`. The base AIND config owns per-step
   CPU, memory, time, and GPU process definitions. The Axion override sets:

   ```text
   params.default_queue = standard
   params.gpu_queue = gpu
   process.clusterOptions = -A parent0
   spikesort_kilosort4.clusterOptions = -A parent0 --gres=gpu:1
   ```

   This preserves AIND's step-level defaults while mapping partitions, account,
   and GPU request to Great Lakes. With Nextflow `26.04.4`, AIND's current
   `nextflow_slurm.config` also needs `NXF_SYNTAX_PARSER=v1` so its Groovy-style
   config declarations parse cleanly; the launcher exports this by default.

New current-AIND scaffold:

```text
config/aind_axion_lumos_params.json
config/aind_nextflow_slurm_greatlakes.config
config/example_aind_nwb_well.env
slurm/run_aind_nwb_well.sbatch
```

Submit the first current-AIND one-well run with:

```bash
cd /home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
bash scripts/setup_aind_nextflow.sh
AIND_CONFIG=config/example_aind_nwb_well.env sbatch slurm/run_aind_nwb_well.sbatch
```

The current AIND pipeline derives the container tag from
`pipeline/capsule_versions.env`; the checked clone uses
`SPIKEINTERFACE_VERSION=0.104.8`, so the target images are `si-0.104.8` images,
not the older Kempner `si-0.101.2` images.

## Axion-Specific Settings To Carry Forward

These are not the whole pipeline. They are Axion/Lumos-specific settings that
should be expressed through the current AIND parameter mechanism if possible:

```text
nblocks = 0
nt = 31
nt0min = null
dmin = 350
dminx = 350
max_channel_distance = 400
x_centers = null
nearest_templates = 16
nearest_chans = 5
min_template_size = 50
whitening_range = 8
Th_universal = 9
Th_learned = 8
Th_single_ch = 6
do_correction = false
```

Rationale:

- 4x4 Axion well geometry is fixed.
- Channels are sparse compared with Neuropixels.
- We do not want Neuropixels-style drift correction by default for a 16-channel
  well.
- The per-well `channel_mapping.csv` is stable in shape across wells of the
  same plate type, but each well keeps its own source file, well label, and
  manifest for provenance.

## Scaling Across Wells

Once one current-AIND run works, scale by generating one upstream-compatible
input directory per well:

```text
data/interim/nwb/<recording_stem>/<well>/<recording_stem>_<well>.nwb
```

or the equivalent current AIND-supported input folder.

For the current SpikeInterface route, each selected well needs:

```text
data/interim/kilosort_binary/<recording_stem_without_lumos_suffix>/<well>/<well>.bin
data/interim/kilosort_binary/<recording_stem_without_lumos_suffix>/<well>/channel_mapping.csv
jobs/aind/<recording_stem>/<well>/spikeinterface/<recording_stem>_<well>_probeinterface.json
jobs/aind/<recording_stem>/<well>/spikeinterface/<recording_stem>_<well>_channel_mapping_manifest.json
jobs/aind/<recording_stem>/<well>/spikeinterface/<recording_stem>_<well>_aind_spikeinterface_params.json
jobs/aind/<recording_stem>/<well>/spikeinterface/run_aind_spikeinterface.env
jobs/aind/<recording_stem>/<well>/spikeinterface/submit_aind_spikeinterface_command.sh
```

The mapping manifest is the audit trail that lets AIND outputs map back to the
original Axion raw file, plate, well, and channel order.

The selected-well batch generator now writes this dependency chain for each
selected well:

```text
export_axion_well_binary.sbatch
  -> export_axion_well_nwb.sbatch
  -> prepare_aind_spikeinterface_well.sbatch
export_axion_well_nwb.sbatch + prepare_aind_spikeinterface_well.sbatch
  -> run_aind_nwb_well.sbatch using SpikeInterface params
```

The AIND job is submitted with `afterok:${spikeinterface_job}:${nwb_job}`. The
NWB dependency is currently retained because `run_aind_nwb_well.sbatch` still
expects an `NWB_FILE` to stage, even when AIND `job_dispatch.input` is
`spikeinterface`.

The 2026-02-25 selected-well batch has been regenerated for 14 wells with:

```bash
bash scripts/prepare_aind_well_batch.sh \
  --recording-stem 'test_2_25_2026_129-8447_test(000)_full_lumos_settings' \
  --raw-file '/nfs/turbo/umms-parent/axion_mea_files_directory/2_25_2026/129-8447/test(000)_BroadbandProcessor.raw' \
  --selection-manifest '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/selection/well_selection_manifest.csv' \
  --allow-aind-overwrite \
  --aind-input spikeinterface
```

Generated scale-up submit script:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/submit_all_wells.sh
```

Historical note: this 14-well launch instruction is superseded by the completed
fresh recording-level run and the active Lumos `_BroadbandProcessor.raw`
multi-recording scale-up. Use the current operational state at the top of this
handoff for active commands and status paths.

Results should be separated by recording and well:

```text
results/aind/<recording_stem>/<well>/
```

or whatever current AIND's `RESULTS_PATH` convention requires.

The Axion geometry template remains:

```text
metadata/plate_maps/axion_per_well_4x4_electrode_geometry.csv
```

but downstream ingestion should use the generated per-well `channel_mapping.csv`
through `AxionWellMapping`.

### 2026-07-06 Fresh Recording Run And Scale-Up Prep

A fresh recording-level run was started under a new recording namespace so it
does not overwrite the earlier successful proof run:

```text
test_2_25_2026_129-8447_test(000)_full_lumos_settings_fresh_20260706_191012
```

The exact commands are saved in:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_fresh_runs/test_2_25_2026_129-8447_test(000)_full_lumos_settings_fresh_20260706_191012/fresh_run_commands.sh
```

Final fresh-run status at `2026-07-06T20:10:18`:

```text
candidate_wells: 48
selected_wells: 14
binary_exports_done: 14
nwb_exports_done: 14
spikeinterface_prep_done: 14
selected_wells_completed: 14
selected_wells_standard_completed: 11
selected_wells_fallback_completed: 3
aind_running: 0
fallback_running: 0
selected_wells_failed: 0
recording_status: complete_success_with_fallback
```

The recording supervisor proved the intended recording-level fallback behavior.
Sparse standard KS4 failures were detected at different times and were
automatically routed to the labeled fallback `low_activity_ks4_nt2_npcs2`:

```text
C7 -> fallback job 53018023
F6 -> fallback job 53018548
B6 -> fallback job 53019665
```

The collector is the current ground truth for this fresh run:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_recording_supervisors/test_2_25_2026_129-8447_test(000)_full_lumos_settings_fresh_20260706_191012/collector/workflow_status_latest.txt
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_recording_supervisors/test_2_25_2026_129-8447_test(000)_full_lumos_settings_fresh_20260706_191012/collector/workflow_status_latest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_recording_supervisors/test_2_25_2026_129-8447_test(000)_full_lumos_settings_fresh_20260706_191012/supervisor.log
```

Scale-up preparation was generated from the raw-data inventory and the
Lumos-only `_BroadbandProcessor.raw` scale-up has now been submitted. The large
batch was launched only after the fresh run reached
`complete_success_with_fallback`.

Inventory output:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_selection_asset_inventory_20260706_scaleup/aind_selection_asset_inventory.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_selection_asset_inventory_20260706_scaleup/aind_selection_asset_inventory.json
```

Scale-up manifest and saved commands:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/recordings_manifest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/recordings_manifest_summary.json
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/scaleup_prepare_commands.sh
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/scaleup_prepared_recordings_summary.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/scaleup_prepared_recordings_summary.json
```

Prepared scale-up batch plan:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/recording_batch_plan/prepare_all_recordings.sh
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/recording_batch_plan/submit_all_recordings.sh
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/recording_batch_plan/supervise_all_recordings.sh
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/recording_batch_plan/recording_batch_manifest.csv
```

Scale-up launch summary:

```text
logical_recordings_total: 7
raw_files_inventoried: 14
eligible_lumos_recordings_submitted: 5
recordings_blocked: 2
selected_well_pipelines_submitted: 65
recording_supervisors_submitted: 5
```

Historical note: the original `20260706` scale-up manifest de-duplicated paired
Axion primary `.raw` and `*_BroadbandProcessor.raw` files into one logical
recording and chose the `*_BroadbandProcessor.raw` file because the successful
proof run used that continuous voltage input. That assumption is superseded.
Moving forward, primary `.raw`, filtered `.raw`, and `*_BroadbandProcessor.raw`
files should remain separate manifest rows with distinct `recording_stem` values
and carried filtering/provenance metadata.

Submitted FortyEightWellLumos recordings and selected wells:

```text
2_12_2026_129-8447_opto_test_meis2_with_E2opsin(000)_FortyEightWellLumos: 10 wells
2_12_2026_129-8447_opto_test_meis2_with_E2opsin(001)_FortyEightWellLumos: 10 wells
2_12_2026_129-8447_opto_test_meis2_with_E2opsin(002)_FortyEightWellLumos: 7 wells
2_20_2026_129-8447_test(000)_FortyEightWellLumos: 24 wells
2_25_2026_129-8447_test(000)_FortyEightWellLumos: 14 wells
```

Previously blocked SixWell recordings:

```text
2_24_2026_134-0150_test(000)_SixWell
2_24_2026_134-0150_test(001)_SixWell
```

These SixWell recordings have raw files, spike-count sidecars, spike-list
sidecars, and metadata matches. They were originally `submit=false` because
the repo only had 48-well and 24-well plate maps. As of `2026-07-07`, SixWell
profile assets have been added:

```text
metadata/plate_maps/axion_6_well_plate_map.csv
metadata/plate_maps/axion_per_well_8x8_electrode_geometry.csv
config/aind_axion_cytoview6_params.json
src/axion_mea/plate_profiles.py
```

The next step for these recordings is a small SixWell smoke run, not a large
submission. Confirm one well exports with 64 channels, writes a 64-row channel
mapping, prepares SpikeInterface/AIND params from the SixWell template, and
does not reuse any Lumos 48-well geometry or channel-count settings.

The scale-up submission has already been run:

```bash
bash /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/recording_batch_plan/submit_all_recordings.sh
bash /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/recording_batch_plan/supervise_all_recordings.sh
```

Submission provenance:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/recording_batch_plan/submitted_recording_batches.tsv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/recording_batch_plan/submitted_recording_supervisors.tsv
```

Current scale-up monitoring ground truth:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/live_status/workflow_status_latest.txt
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/live_status/workflow_status_latest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_scaleup_20260706/live_status/workflow_status_latest.json
```

## Do Not Reinvent

Do not reimplement these locally unless the upstream method cannot accept Axion
data even after a reasonable adapter:

- Kilosort orchestration,
- preprocessing,
- postprocessing metrics,
- curation,
- visualization/Figurl products,
- result collection,
- NWB units export,
- QC summaries.

The correct shape is:

```text
Axion bridge -> current AIND/Kempner-supported input -> upstream pipeline outputs
```

not:

```text
Axion bridge -> local clone of every upstream processing step
```

## Current Local Artifacts To Be Aware Of

The following local files/scripts exist from the first Kempner attempt. Treat
them as experimental scaffolding, not the final direction:

```text
slurm/run_kempner_nwb_well.sbatch
slurm/pull_kempner_containers.sbatch
scripts/setup_kempner_nextflow.sh
scripts/pull_kempner_singularity_containers.sh
scripts/submit_kempner_nwb_well_job.sh
scripts/submit_kempner_container_pull_job.sh
config/example_kempner_nwb_well.env
config/kempner_kilosort4_axion_lumos_params.json
```

The useful pieces to reuse are the paths, provenance habits, Axion settings, and
container-pull lessons. The workflow target should now be current AIND
`main_multi_backend.nf`.
