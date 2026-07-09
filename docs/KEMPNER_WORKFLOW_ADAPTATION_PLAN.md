# Axion to AIND/Kempner Ephys Pipeline Handoff

Date updated: 2026-07-08 16:11 EDT

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

Formal pipeline state as of `2026-07-08 16:11 EDT`:

- Step 1 and Step 2 are now formally created.
- Step 1 generated completed AIND/Kilosort/NWB-units outputs for 122 wells.
- Step 2 is the frozen recovery/classification lane that starts from those Step
  1 outputs and computes the missing classifier/QC assets.
- Step 2 completed across every Step 1 well that completed `nwb_units`,
  regardless of plate size or lane.
- All 122 Step 2 jobs completed in Slurm, and all 122 wells have complete Step
  2 output sets.
- The recovery pipeline is functionally complete and frozen. Do not make further
  recovery-pipeline code changes unless a new software bug is discovered.

Formal Step 1 - Axion to AIND/NWB Units:

```text
purpose:
  Convert Axion per-well recordings into AIND-compatible inputs, run the
  maintained AIND/Kilosort4 pipeline, and produce the canonical sorted output
  tree through nwb_units.
inputs:
  Axion raw/continuous voltage recordings and per-well metadata.
  Axion well mapping / plate-family geometry.
  AIND per-well launch configuration.
outputs:
  Per-well AIND result directory:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/<recording>/<well>/
  Key Step 1 artifacts inside each completed well:
    postprocessed/block0_None_recording1.zarr
    curated/block0_None_recording1/
    nwb/*.nwb
    nextflow/trace.txt
  Ledger:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260708_130012/unified_well_status.csv
status:
  122 wells completed through nwb_units.
  54 FortyEightWellLumos / 48well_auto.
  67 SixWell / sixwell_manual_primary.
  1 SixWell / sixwell_smoke.
analysis label policy:
  Use original Kilosort4 good units plus independent electrophysiological QC as
  the current primary biological inclusion criterion. Downstream analyses may
  also include Kilosort4 MUA units when scientifically appropriate, but should
  not include units labeled as Kilosort noise.
rationale for analysis policy:
  The recovery pipeline was successfully validated on representative Lumos wells.
  UnitRefine and Bombcell executed without software errors, but both pretrained
  classifiers consistently labeled essentially all Kilosort units as noise across
  representative low-, medium-, and high-activity wells. This behavior was
  interpreted as a likely classifier calibration/domain mismatch for Axion Lumos
  organoid MEA recordings rather than a pipeline failure. Therefore, the recovery
  pipeline is retained for feature extraction and QC, while primary biological
  analyses are performed using Kilosort4 good units and may also include
  Kilosort4 MUA units. Kilosort noise units should remain excluded.
```

Formal Step 2 - Frozen Classification/QC Recovery:

```text
purpose:
  Reuse completed Step 1 AIND outputs and compute missing SpikeInterface assets
  needed for UnitRefine/Bombcell/default-QC metadata. Preserve classifier outputs
  as QC/metadata/supplementary information, not as the current primary biological
  inclusion criterion.
inputs:
  Step 1 per-well AIND result directory:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/<recording>/<well>/
  Required source analyzer:
    postprocessed/block0_None_recording1.zarr
  Recovery params:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_step2_full_20260708_153945/recovery_params.json
  Step 2 manifest:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_step2_full_20260708_153945/step2_full_manifest.csv
outputs:
  Per-well Step 2 result directory:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_unit_classification_step2_full/aind_unit_classification_step2_full_20260708_153945/<recording>/<well>/
  Key Step 2 artifacts:
    curation/unit_labels_block0_None_recording1.csv
    curation/curation_block0_None_recording1.json
    curation/unit_merges_block0_None_recording1.json
    quality_metrics_required_diagnostic.json
    classification_recovery_summary.json
    data_process_unit_classification_recovery.json
  Recomputed in memory for recovery:
    waveforms
    templates
    noise_levels
    spike_locations
    spike_amplitudes
    principal_components
    template_similarity
    template_metrics
    required quality_metrics
not computed:
  sd_ratio is intentionally not computed because it has no downstream Step 2
  recovery consumer in UnitRefine, Bombcell, default QC, curation outputs, or
  required provenance.
software validation:
  Axion MEA geometry supports spike_locations.
  Required SpikeInterface quality metrics compute successfully.
  UnitRefine completes.
  Bombcell completes.
  unit_labels.csv, curation JSON, merge JSON, summary JSON, and AIND DataProcess
  metadata are written successfully.
full-scale completion:
  122/122 submitted wells completed.
  122/122 unit label CSVs are present.
  122/122 curation JSONs are present.
  122/122 merge JSONs are present.
  122/122 classification summary JSONs are present.
  122/122 quality metric diagnostic JSONs are present.
  122/122 AIND DataProcess metadata JSONs are present.
```

Step 2 full-scale completion:

```text
batch root:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_step2_full_20260708_153945
manifest:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_step2_full_20260708_153945/step2_full_manifest.csv
submitted jobs:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_step2_full_20260708_153945/submitted_jobs.tsv
submission time:
  2026-07-08 15:39 EDT
submitted well count:
  122 total
  54 FortyEightWellLumos / 48well_auto
  67 SixWell / sixwell_manual_primary
  1 SixWell / sixwell_smoke
job ID range:
  first submitted: 53116835
  last submitted: 53116967
verified state at 2026-07-08 16:05 EDT:
  Slurm sacct:
    122 COMPLETED
  Slurm squeue:
    no submitted Step 2 jobs remain queued or running
  output completeness:
    122/122 unit_labels CSVs
    122/122 curation JSONs
    122/122 merge JSONs
    122/122 classification summary JSONs
    122/122 quality metric diagnostic JSONs
    122/122 AIND DataProcess metadata JSONs
monitor command:
  ROOT=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_step2_full_20260708_153945
  ids=$(cut -f5 "$ROOT/submitted_jobs.tsv" | tail -n +2 | paste -sd, -)
  squeue -h -j "$ids" -o '%T' | sort | uniq -c
```

Latest unified status was refreshed on `2026-07-08 13:01 EDT` using the
Great Lakes project conda environment from `config/greatlakes_project.env`
(`/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/envs/axion-kilosort`).
Do not run the status ledger with bare system `python` or `python3`.

Current ledger:

```text
latest symlink:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_latest
snapshot:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260708_130012
summary:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260708_130012/unified_status_summary.txt
well table:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260708_130012/unified_well_status.csv
recording table:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260708_130012/unified_recording_status.csv
unit metrics table:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260708_130012/unit_metrics_by_well.csv
```

Current submitted new-upload/SixWell status:

```text
expected_well_pipelines: 168
expected_recordings: 26
plate_family_counts_by_well: {"FortyEightWellLumos": 54, "SixWell": 114}
lane_counts_by_well: {"48well_auto": 54, "sixwell_manual_primary": 113, "sixwell_smoke": 1}
well_status_counts: {"complete_nwb_units": 122, "needs_attention:spikesort_kilosort4": 46}
kilosort_state_counts: {"COMPLETED": 122, "FAILED": 46}
nwb_units_state_counts: {"COMPLETED": 122, "not_entered": 46}
recording_status_counts: {"complete_all_wells": 12, "needs_attention": 14}
live_slurm_kilosort_child_state_counts: {}
live_slurm_aind_parent_state_counts: {}
unit_metrics_status_counts: {"missing_curated_sorting": 46, "ok": 122}
unit_metrics_totals:
  wells_with_unit_metrics: 122
  units_total: 9016
  kslabel_good_total: 998
  kslabel_mua_total: 8018
  kslabel_noise_total: 0
  total_sorted_spikes: 1039219231
```

Interpretation:

- The 6 submitted Lumos/48-well auto recordings are complete: 54/54 selected
  wells reached `nwb_units`.
- The SixWell smoke is complete: 1/1 well reached `nwb_units`.
- The SixWell manual-primary lane is partially successful: 67/113 wells reached
  `nwb_units`; 46/113 wells failed in `spikesort_kilosort4`.
- No Axion/AIND/Kilosort jobs from these submitted lanes are currently live in
  Slurm. The visible remaining `squeue` entry for this user is unrelated
  `siletti-div90-xfer-3d` held transfer work.
- The 46 current failures are standard-route Kilosort/signal failures, not raw
  export, NWB export, SpikeInterface prep, Python-shim, or path-quoting
  failures.
- Current SixWell failure split:
  - 42 wells: sparse activity, `n_samples < n_clusters=6`;
  - 3 wells: zero-sample `TruncatedSVD`;
  - 1 well: CUDA device-side assert, needs separate inspection.

Current reproducibility status:

- Step 1 is reproducible for raw variants that pass ingestion and for wells with
  enough sortable signal. It produced 122 completed `nwb_units` wells.
- Step 2 is reproducible and frozen for completed Step 1 wells. It has been
  submitted across all 122 completed Step 1 wells.
- Known terminal Step 1 classes remain for wells that did not complete Kilosort:
  blocked raw ingestion for older recordings, sparse/no-sortability Kilosort
  failures in SixWell, and one CUDA Kilosort failure needing separate inspection.
- UnitRefine/Bombcell labels are preserved as metadata, but current primary
  biological analysis should use Kilosort4 good units plus independent
  electrophysiological QC.

## Step 3 Biological Analysis Strategy

Step 1 AIND spike sorting and Step 2 recovery/classification are complete and
frozen. The sections above remain the implementation and validation record for
those phases. Step 3 is analysis mode, not continued pipeline development.

Objective:

- Generate biological analyses and manuscript-quality figures efficiently.
- Maximize reuse of the frozen Step 1 and Step 2 outputs.
- Build only the minimum reusable code required for the next biological
  analysis.
- Use Kilosort4 good units as the primary analysis set. Kilosort4 MUA units may
  be included when scientifically appropriate; Kilosort noise remains excluded.
- Preserve UnitRefine and Bombcell labels as metadata, not automatic exclusion
  criteria.

Guiding principle:

- Organize development around biological analyses, not figures and not software
  modules.
- Each biological analysis should produce one scientifically meaningful result,
  support one or more manuscript panels, expose reusable outputs for later
  analyses, and avoid recomputing information already produced by frozen Step 1.
- Figures are outputs of analyses, not development milestones.

Canonical data sources:

- Step 1 is the canonical scientific data source.
- Step 2 is metadata layered on top of Step 1: labels, curation, diagnostics,
  and provenance.
- Do not duplicate or recompute information already available unless a specific
  biological analysis requires it.

Biological analysis dependency graph:

```text
Spike Sorting
  -> Waveforms / Templates / Spike Times
  -> Waveform Metrics
  -> RS/FS Classification
  -> Optotagging
  -> Network & Population Analyses
  -> Manuscript Figures
```

Biological analysis blocks:

```text
1. Waveform Analysis
   purpose:
     Generate waveform-derived measurements.
   outputs:
     mean waveforms
     SEM waveforms
     normalized waveforms
     waveform metrics
     trough-to-peak duration
     waveform asymmetry
     repolarization slope
   supports:
     Supplementary RS/FS figure panels A-C
     Supplementary Optotagging figure panel F

2. RS/FS Classification
   purpose:
     Generate biological RS/FS classifications from waveform features.
   outputs:
     RS labels
     FS labels
     feature tables
     classification boundaries
   supports:
     Supplementary RS/FS figure panels A-C

3. Spike Stability Analysis
   outputs:
     waveform stability
     amplitude stability
     firing-rate stability
   supports:
     Supplementary RS/FS figure panel D
     Supplementary Optotagging figure panel G

4. Isolation Analysis
   outputs:
     autocorrelograms
     cross-correlograms
     spatial footprints
   supports:
     Supplementary RS/FS figure panels E-F
     Supplementary Optotagging figure panel G

5. Optotagging Analysis
   outputs:
     raster plots
     PSTHs
     first-spike latency
     response probability
     reliability
     optotagged neuron summary
   supports:
     Supplementary Optotagging figure panels C-H
```

Development philosophy:

1. Determine whether the required biological quantity already exists in frozen
   Step 1 outputs.
2. Build only the smallest reusable functions necessary for the current
   biological analysis.
3. Delay general software framework development until repeated analyses
   demonstrate a real need.
4. Every new function should directly contribute to one or more biological
   analyses or manuscript figure panels.

## Historical Step 2 Debug Log

The entries below are retained only to explain how the frozen Step 2 recovery
pipeline was debugged. They are not current operating instructions.

Step 2 canary submission history:

```text
first recovery root:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_131708
first canary manifest:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_131708/canary_manifest.csv
first params:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_131708/recovery_params.json
first submit script:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_131708/submit_canary.sh
first submitted table:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_131708/submitted_canary.tsv
first canary:
  recording: 6_22_2026_129-8445_ventral_sosrs_opsin_day3(000)_FortyEightWellLumos_primary_raw_NeuralBroadband
  well: A3
  recovery job: 53112023
  output dir:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_unit_classification_recovery/aind_unit_classification_recovery_20260708_131708/6_22_2026_129-8445_ventral_sosrs_opsin_day3(000)_FortyEightWellLumos_primary_raw_NeuralBroadband/A3
  status at 2026-07-08 13:17 EDT:
    PENDING on standard partition, reason Priority
  final status:
    FAILED exit 1 after 11s. The copied recovery analyzer could not reload its
    recording, causing SpikeInterface extension computation to fail with:
      AssertionError: Extension noise_levels requires the recording

retry recovery root:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_132136
retry canary manifest:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_132136/canary_manifest.csv
retry params:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_132136/recovery_params.json
retry submitted table:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_132136/submitted_canary.tsv
retry canary:
  recording: 6_22_2026_129-8445_ventral_sosrs_opsin_day3(000)_FortyEightWellLumos_primary_raw_NeuralBroadband
  well: A3
  recovery job: 53112108
  output dir:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_unit_classification_recovery/aind_unit_classification_recovery_20260708_132136/6_22_2026_129-8445_ventral_sosrs_opsin_day3(000)_FortyEightWellLumos_primary_raw_NeuralBroadband/A3
  status at 2026-07-08 13:21 EDT:
    RUNNING on standard partition node gl3151
  final status:
    FAILED exit 1 after 16s. This reached extension computation on the original
    source analyzer, but `compute_several_extensions(..., save=False)` still
    hit dependency ordering:
      AssertionError: Extension template_metrics requires templates to be computed first

third recovery root:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_132241
third submitted table:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_132241/submitted_canary.tsv
third canary:
  recording: 6_22_2026_129-8445_ventral_sosrs_opsin_day3(000)_FortyEightWellLumos_primary_raw_NeuralBroadband
  well: A3
  recovery job: 53112128
  final status:
    FAILED exit 1 after 5s. One-at-a-time extension computation progressed but
    hit a nonessential default extension dependency:
      AssertionError: Extension amplitude_scalings requires templates to be computed first

current Step 2 code state after fourth failure:
  scripts/run_aind_unit_classification_recovery.py computes the classification
  dependency chain in explicit order:
    noise_levels
    waveforms
    templates
    spike_amplitudes
    principal_components
    template_similarity
    template_metrics
    quality_metrics
  Do not submit scale-out until a canary with this dependency order
  produces `unit_labels_block0_None_recording1.csv` and
  `curation_block0_None_recording1.json`.

fourth recovery root:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_132528
fourth submitted table:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_132528/submitted_canary.tsv
fourth canary:
  recording: 6_22_2026_129-8445_ventral_sosrs_opsin_day3(000)_FortyEightWellLumos_primary_raw_NeuralBroadband
  well: A3
  recovery job: 53112920
  output dir:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_unit_classification_recovery/aind_unit_classification_recovery_20260708_132528/6_22_2026_129-8445_ventral_sosrs_opsin_day3(000)_FortyEightWellLumos_primary_raw_NeuralBroadband/A3
  status at 2026-07-08 13:25 EDT:
    PENDING on standard partition, reason Priority
  final status:
    FAILED exit 1 after 13s. Source A3 had only `random_spikes` and
    `correlograms`, so the recovery still needed to compute `templates` before
    `template_metrics`.

fifth recovery root:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_132827
fifth submitted table:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_132827/submitted_canary.tsv
fifth canary:
  recording: 6_22_2026_129-8445_ventral_sosrs_opsin_day3(000)_FortyEightWellLumos_primary_raw_NeuralBroadband
  well: A3
  recovery job: 53112964
  output dir:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_unit_classification_recovery/aind_unit_classification_recovery_20260708_132827/6_22_2026_129-8445_ventral_sosrs_opsin_day3(000)_FortyEightWellLumos_primary_raw_NeuralBroadband/A3
  status at 2026-07-08 13:30 EDT:
    PENDING on standard partition, reason Priority
  status at 2026-07-08 13:32 EDT:
    RUNNING on standard partition node gl3356. It has passed the immediate
    analyzer-load and extension-dependency failures from attempts 1-4 and is
    computing missing SpikeInterface metrics. No UnitRefine/Bombcell output has
    been produced yet.

Step 2 issue trail for clean-run gating:
  attempt 1, job 53112023:
    failed because copying the analyzer broke recording reload.
    action: changed recovery to load the original Step 1 analyzer instead of a
    copied analyzer.
  attempt 2, job 53112108:
    failed because dictionary/bulk extension computation hit dependency
    ordering at template_metrics.
    action: changed recovery to compute extensions one at a time.
  attempt 3, job 53112128:
    failed because the default AIND extension list included nonessential
    amplitude_scalings, which also hit dependency ordering.
    action: narrowed recovery to the minimal classification-required extension
    set.
  attempt 4, job 53112920:
    failed exit 1 after 13s. This exposed another assumption: the selected A3
    source analyzer had only `random_spikes` and `correlograms` loaded, so the
    recovery still needed to compute upstream classification dependencies such
    as `templates` before `template_metrics`.
    action: updated the recovery extension order to:
      noise_levels
      waveforms
      templates
      spike_amplitudes
      principal_components
      template_similarity
      template_metrics
      quality_metrics
  attempt 5, job 53112964:
    first canary using the full classification dependency order. It progressed
    beyond the immediate failures seen in attempts 1-4.
    Progress check at 2026-07-08 13:43 EDT:
      RUNNING on gl3356, elapsed 12m25s.
      AveCPU 16m06s, AveRSS ~1.65G, MaxRSS ~1.73G of 64G requested.
      Source analyzer gained a `templates` extension at 13:31.
      No final UnitRefine/Bombcell labels yet.
    Diagnostic improvement at 2026-07-08 13:46 EDT:
      `scripts/run_aind_unit_classification_recovery.py` now logs START/DONE
      timestamps and elapsed seconds around every extension compute and around
      default QC, UnitRefine, Bombcell, and SLAy. The already-running job
      53112964 will not gain these logs retroactively; the next retry or
      scale-out will show exactly which extension is slow.
    final status:
      FAILED exit 1 after 35m16s. Bulk `quality_metrics` completed, but
      UnitRefine failed immediately afterward because the analyzer did not
      contain required model features:
        drift_ptp
        drift_std
        drift_mad
      SpikeInterface skipped the `drift` quality metric because the source
      analyzer did not have the required `spike_locations` extension.
  parallel monitor canary, job 53113426:
    submitted at 2026-07-08 13:47 EDT on a different completed recording:
      recording:
        6_22_2026_129-8445_ventral_sosrs_opsin_day3(001)_FortyEightWellLumos_primary_raw_NeuralBroadband
      well: A3
      source units/spikes from latest ledger:
        50 units, 7613700 spikes
      recovery root:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_134734
      output:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_unit_classification_recovery/aind_unit_classification_recovery_20260708_134734/6_22_2026_129-8445_ventral_sosrs_opsin_day3(001)_FortyEightWellLumos_primary_raw_NeuralBroadband/A3
      status at 2026-07-08 13:47 EDT:
        RUNNING on standard partition node gl3409.
      final status:
        FAILED exit 1 after 16s. The new timing logs showed:
          noise_levels: 0.23s
          waveforms: 1.54s
          principal_components: 6.61s
          template_metrics: failed immediately
        Failure:
          AssertionError: Extension template_metrics requires templates to be computed first
        Interpretation:
          Even when `templates` is present in a loaded Step 1 analyzer, this
          SpikeInterface recovery path needs `templates` recomputed in the same
          session before `template_metrics`.
        Action:
          `scripts/run_aind_unit_classification_recovery.py` now forces
          `templates` into the recovery compute plan even when the source
          analyzer already lists a templates extension.
  active monitored retry, job 53113455:
    submitted at 2026-07-08 13:49 EDT on the same second recording as the
    parallel monitor canary:
      recording:
        6_22_2026_129-8445_ventral_sosrs_opsin_day3(001)_FortyEightWellLumos_primary_raw_NeuralBroadband
      well: A3
      source units/spikes from latest ledger:
        50 units, 7613700 spikes
      recovery root:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_134912
      output:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_unit_classification_recovery/aind_unit_classification_recovery_20260708_134912/6_22_2026_129-8445_ventral_sosrs_opsin_day3(001)_FortyEightWellLumos_primary_raw_NeuralBroadband/A3
      status at 2026-07-08 13:54 EDT:
        RUNNING on standard partition node gl3191, elapsed 5m18s.
        AveCPU 6m11s, AveRSS ~1.61G, MaxRSS ~1.69G of 64G requested.
        The per-extension logs show dependency recovery is working:
          noise_levels: 0.26s
          waveforms: 0.60s
          templates: 0.03s
          spike_amplitudes: 1.94s
          principal_components: 6.25s
          template_similarity: 12.40s
          template_metrics: 0.43s
        Current stage:
          START compute extension quality_metrics at 13:49:50 EDT.
        Interpretation:
          The current bottleneck is `quality_metrics`; the job has not failed
          and has not yet produced final UnitRefine/Bombcell labels.
      status at 2026-07-08 14:15 EDT:
        RUNNING on standard partition node gl3191, elapsed 26m31s. This job was
        started before `spike_locations` was added to the recovery order, so it
        is expected to reproduce the missing-drift-feature failure if it reaches
        UnitRefine.
  spike-location canary, job 53114765:
    submitted at 2026-07-08 14:15 EDT on the same monitored recording/well:
      recording:
        6_22_2026_129-8445_ventral_sosrs_opsin_day3(001)_FortyEightWellLumos_primary_raw_NeuralBroadband
      well: A3
      recovery root:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_141527
      output:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_unit_classification_recovery/aind_unit_classification_recovery_20260708_141527/6_22_2026_129-8445_ventral_sosrs_opsin_day3(001)_FortyEightWellLumos_primary_raw_NeuralBroadband/A3
      status at 2026-07-08 14:16 EDT:
        PENDING on standard partition, reason Priority.
      final status:
        CANCELLED after 2m10s. It proved `spike_locations` can compute on the
        Axion A3 analyzer:
          spike_locations completed in 44.34s.
        The job was cancelled because the per-metric diagnostic wrapper used
        the full quality metric list on each one-metric call, which triggered a
        SpikeInterface metric-propagation KeyError unrelated to the Axion
        geometry question.
      purpose:
        Test whether Axion channel geometry is sufficient to compute
        `spike_locations`, then let `quality_metrics` compute the `drift`
        columns required by UnitRefine.
      code state:
        `scripts/run_aind_unit_classification_recovery.py` now computes
        `spike_locations` after `templates` and before `quality_metrics`.
      prerequisite finding:
        The A3 source analyzer has a recording, 16 channels, 12.5 kHz sampling,
        and finite 2D channel locations in a 4x4 Axion grid with 350 um spacing.
        SpikeInterface 0.104.8 `spike_locations` requires `templates`, a
        recording, and valid channel/probe geometry; these appear satisfiable
        for the Axion MEA analyzer.
  corrected spike-location canary, job 53114826:
    submitted at 2026-07-08 14:19 EDT after fixing the per-metric diagnostic
    wrapper to call each quality metric with only its own `metric_names` entry:
      recovery root:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_141902
      output:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_unit_classification_recovery/aind_unit_classification_recovery_20260708_141902/6_22_2026_129-8445_ventral_sosrs_opsin_day3(001)_FortyEightWellLumos_primary_raw_NeuralBroadband/A3
      status at 2026-07-08 14:24 EDT:
        RUNNING on standard partition node gl3191, elapsed 4m12s.
      confirmed progress:
        `spike_locations` completed in 44.71s.
        `drift` quality metric completed in 1.55s once `spike_locations` was
        present.
      current quality metric findings:
        `amplitude_cutoff` failed because SI 0.104.8
        `compute_amplitude_cutoffs()` does not accept `peak_sign`.
        `amplitude_median` failed because SI 0.104.8
        `compute_amplitude_medians()` does not accept `peak_sign`.
        `synchrony` failed because SI 0.104.8
        `compute_synchrony_metrics()` does not accept `peak_sign`.
      interpretation:
        Axion geometry is sufficient for `spike_locations` and `drift`.
        The remaining visible blocker is now a params/API compatibility issue
        for required quality metrics, not missing Axion geometry.
```

New Step 2 implementation files:

```text
scripts/prepare_aind_unit_classification_recovery.py
scripts/run_aind_unit_classification_recovery.py
slurm/run_aind_unit_classification_recovery.sbatch
```

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

The current active phase is **post-scale-up accounting and failure-policy
triage**. The older `20260706` Lumos scale-up has reached terminal accounting:

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
  wrapper: scripts/audit_axion_file_ground_truth.sh
  implementation: scripts/audit_axion_file_ground_truth.py
  environment rule:
    invoke the wrapper, not bare python. The wrapper sources
    config/greatlakes_project.env, activates
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/envs/axion-kilosort
    through /home/elcrespo/miniconda3, and then runs the Python audit. This
    preserves the Great Lakes conda/anaconda convention used by the rest of the
    repo.
  environment/container distinction:
    The conda env and the .img/.sif container images are different layers.
    The conda env is the host-side Great Lakes environment for repo wrappers,
    audits, manifest builders, and preparation utilities. The .img/.sif files
    are Singularity/Apptainer runtime images used by Nextflow/AIND/Kempner
    tasks. Do not treat the audit wrapper environment as the same thing as the
    Nextflow container runtime; they exchange reviewed manifests/configs and
    mounted paths, but they are not the same environment.
  report root:
    durable snapshot:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_20260707_103911
    current moving check:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_current_check
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
  latest moving check:
    Current check rerun at 2026-07-07T11:23:37 using
    scripts/audit_axion_file_ground_truth.sh. Counts at that moment:
      visible .raw files: 87
      logical raw groups: 41
      incoming/new_upload .raw files: 73
      incoming/new_upload logical groups: 34
      platemap files: 10
      platemap files with candidate biology labels: 10
      upload temp fragments: 1
    One final-looking file was still in flight as a hidden rsync partial:
      incoming/manny4tbum_20260706/scn8a_sosrs_dorsal_vs_ventrals/133-1555/.(000).raw.j3XgJz
    It was still growing when sampled at 2026-07-07T11:23:46-11:23:51, so
    rerun the audit after that partial is renamed to `(000).raw` before
    freezing a final manifest.
  latest post-upload-ish check:
    Current check rerun at 2026-07-07T11:27:40 using
    scripts/audit_axion_file_ground_truth.sh. Counts at that moment:
      visible .raw files: 88
      logical raw groups: 42
      incoming/new_upload .raw files: 74
      incoming/new_upload logical groups: 35
      upload temp fragments: 0
      platemap files: 10
      raw files with stimulation events: 35
      logical groups with stimulation events: 13
      logical groups with LED stimulation: 13
      logical groups with electrode stimulation: 0
      raw stim parse status: {"ok": 88}
    This suggests the last hidden partial had landed by this audit, but a final
    source-side rsync dry-run should still be used before freezing a manifest.
  frozen upload-set audit:
    After the user confirmed all potential processing files were finalized, a
    freeze-ready audit was written at 2026-07-07T11:30:03:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_20260707_1129_final_upload_set
    Counts:
      visible .raw files: 88
      logical raw groups: 42
      incoming/new_upload .raw files: 74
      incoming/new_upload logical groups: 35
      upload temp fragments: 0
      platemap files: 10
      raw stim parse status: {"ok": 88}
    Additional filter-provenance outputs were written:
      filter_ground_truth_summary.csv
      filter_ground_truth_summary.json
      filter_metadata_counts_by_raw_variant.csv
  refreshed final metadata inventory:
    The first post-upload MATLAB metadata inventory was launched serially as
    Slurm job 53046852, but this was canceled because slow/problematic older
    files made the whole pass serially fragile. The replacement approach used
    per-file array submission:
      slurm/inspect_axion_raw_metadata_array.sbatch
      job: 53047033, array 1-88%8, 32G per task
      high-memory retry: 53047284 for tasks 7-8 with 128G
    Tasks 7-8 were:
      2_20_2026/129-8447/test(000).raw
      2_20_2026/129-8447/test(000)_BroadbandProcessor.raw
    The parallel metadata inventory completed with 88/88 rows and status ok:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_metadata_final_20260707_1134_parallel/raw_metadata_inventory.csv
    The refreshed ground-truth audit using that inventory is:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_20260707_1134_final_refreshed_metadata
    Superseding block-vector-aware refresh at 2026-07-07T13:07:
      metadata job root:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_metadata_final_20260707_1252_blockvector_audit
      merged metadata inventory:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_metadata_final_20260707_1252_blockvector_audit/raw_metadata_inventory.csv
      ground-truth audit:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_20260707_1252_blockvector_audit
      Slurm metadata arrays:
        canceled all-32G attempt: 53050821
        regular 32G split: 53050852, 86/86 completed
        high-memory 128G split: 53050853, 2/2 completed
      The two high-memory tasks were the known 2_20_2026/129-8447
      primary/BroadbandProcessor files and each used about 83G MaxRSS.
      The refreshed metadata inventory has 88/88 rows with metadata status ok
      and now records:
        block_vector_warning_seen
        block_vector_warning_ids
        block_vector_warning_messages
      Block-vector-aware ground-truth counts:
        standard export allowed raw files: 75
        standard export blocked raw files: 13
        standard export block reason: block_vector_warning_seen
        logical groups with block_vector_warning_seen: 6
      Blocked logical groups:
        2_12_2026/129-8447/opto_test_meis2_with_E2opsin(000)
        2_12_2026/129-8447/opto_test_meis2_with_E2opsin(001)
        2_12_2026/129-8447/opto_test_meis2_with_E2opsin(002)
        2_20_2026/129-8447/test(000)
        2_24_2026/134-0150/test(000)
        incoming/manny4tbum_20260706/5_28_26_h1/133-1555/h1_dorsal_and_ventral_exp17_3(003)
      This snapshot also carries:
        filter metadata signatures/value counts
        sampling_frequency_hz and duration/timing fields
        stimulation/opto event counts, LED status, stimulated wells, event times
        platemap biology label candidates
        decoded dorsal/ventral well-label candidate CSV
        manual stability_recording annotations
      Treat this `20260707_1252_blockvector_audit` snapshot as the current
      ground truth before any next manifest/smoke/processing submission.
    Manual curation annotations in that audit:
      manual_logical_group_annotations.csv
      logical_recording_groups_annotated.csv
    The following five groups are manually labeled `stability_recording` with
    note "Proving stability recordings for later.":
      Testing_mea_transient_plateing/134-0150/My Experiment(000)
      Testing_mea_transient_plateing/134-0150/My Experiment(001)
      Testing_mea_transient_plateing/134-0150/My Experiment(002)
      Testing_mea_transient_plateing/134-0150/My Experiment(003)
      Testing_mea_transient_plateing/134-0150/My Experiment(004)
    This label is human-curated provenance, not inferred from `.raw` metadata
    or `.platemap` contents.
    Counts from refreshed audit at 2026-07-07T12:02:17:
      visible .raw files: 88
      logical raw groups: 42
      metadata matched raws: 88
      raw metadata status: {"ok": 88}
      plate type counts by raw:
        FortyEightWellLumos: 43
        SixWell: 45
      raw_metadata_missing issue: 0
    Filter/variant ground truth from this frozen audit:
      raw files by variant:
        primary_raw: 42
        filter_1Hz-200Hz: 19
        filter_200Hz-3kHz: 19
        broadband_processor_raw: 8
      logical group variant shapes:
        primary_raw only: 16
        primary_raw + broadband_processor_raw: 7
        primary_raw + filter_1Hz-200Hz + filter_200Hz-3kHz: 18
        primary_raw + filter_1Hz-200Hz + filter_200Hz-3kHz + broadband_processor_raw: 1
      Therefore, 19 logical recording groups have the matched Axion filter pair:
        _Filter(1Hz-200Hz).raw
        _Filter(200Hz-3kHz).raw
      These 19 groups account for 38 filtered raw files. All matched filter-pair
      groups are in the new_upload scope. The 7 primary+broadband-only groups
      are older_or_existing.
    Interpretation:
      Important correction: `primary_raw` only means the file has the primary
      Axion `.raw` filename, not that it is unfiltered. The acquisition filter
      settings for primary raws are in the raw `dataset_description` metadata.
      The audit now parses these into:
        acquisition_analog_mode_setting
        acquisition_digital_high_pass_filter
        acquisition_digital_low_pass_filter
        derived_high_pass_filter
        derived_low_pass_filter
      Refreshed primary_raw filter breakdown after 88/88 metadata completion:
        23 primary raws:
          Analog Mode Setting = Neural Broadband
          Digital High Pass Filter = 0.1 Hz IIR
          Digital Low Pass Filter = None
        14 primary raws:
          Analog Mode Setting = Neural Spikes
          Digital High Pass Filter = 200 Hz IIR
          Digital Low Pass Filter = 3 kHz Kaiser Window
        3 primary raws:
          Analog Mode Setting = Neural Broadband
          Digital High Pass Filter = 200 Hz IIR
          Digital Low Pass Filter = None
        2 primary raws:
          Analog Mode Setting = Neural Spikes
          Digital High Pass Filter = 200 Hz IIR
          Digital Low Pass Filter = None
      The Axion-generated raw filename/variant still identifies derived files
      such as `_Filter(1Hz-200Hz)`, `_Filter(200Hz-3kHz)`, and
      `_BroadbandProcessor`, but the primary `.raw` filter must be interpreted
      from metadata. The refreshed inventory now resolves the earlier
      metadata_missing caveat for the finalized upload set.
      Going forward, filter review and downstream manifests should use the
      metadata filter values as the primary filter identity, not only the
      filename variant labels. The filename variant should remain provenance,
      while the following columns define the filter state:
        acquisition_analog_mode_setting
        acquisition_digital_high_pass_filter
        acquisition_digital_low_pass_filter
        derived_high_pass_filter
        derived_low_pass_filter
        filter_metadata_signature
      The refreshed audit now writes:
        filter_metadata_signatures.csv
        filter_metadata_value_counts.csv
      Current distinct filter metadata signatures:
        23 raw files:
          analog=Neural Broadband
          acquisition_hp=0.1 Hz IIR
          acquisition_lp=None
          derived_hp=<blank>
          derived_lp=<blank>
        40 raw files:
          analog=Neural Broadband
          acquisition_hp=0.1 Hz IIR
          acquisition_lp=None
          derived_hp=Butterworth
          derived_lp=Butterworth
        3 raw files:
          analog=Neural Broadband
          acquisition_hp=200 Hz IIR
          acquisition_lp=None
          derived_hp=<blank>
          derived_lp=<blank>
        6 raw files:
          analog=Neural Broadband
          acquisition_hp=200 Hz IIR
          acquisition_lp=None
          derived_hp=Butterworth
          derived_lp=Butterworth
        14 raw files:
          analog=Neural Spikes
          acquisition_hp=200 Hz IIR
          acquisition_lp=3 kHz Kaiser Window
          derived_hp=<blank>
          derived_lp=<blank>
        2 raw files:
          analog=Neural Spikes
          acquisition_hp=200 Hz IIR
          acquisition_lp=None
          derived_hp=<blank>
          derived_lp=<blank>
      Current observed value ranges across the 88 raw files:
        acquisition_analog_mode_setting:
          Neural Broadband: 72 raw files, 26 logical groups
          Neural Spikes: 16 raw files, 16 logical groups
        acquisition_digital_high_pass_filter:
          0.1 Hz IIR: 63 raw files, 23 logical groups
          200 Hz IIR: 25 raw files, 19 logical groups
        acquisition_digital_low_pass_filter:
          None: 74 raw files, 28 logical groups
          3 kHz Kaiser Window: 14 raw files, 14 logical groups
        derived_high_pass_filter:
          <blank>: 42 raw files, 42 logical groups
          Butterworth: 46 raw files, 26 logical groups
        derived_low_pass_filter:
          <blank>: 42 raw files, 42 logical groups
          Butterworth: 46 raw files, 26 logical groups
      `scripts/build_aind_recordings_manifest.py` and
      `scripts/prepare_aind_recording_batches.py` now pass through the filter
      metadata signature and component fields so downstream batch manifests can
      be grouped or audited by true metadata filter state.
    Broadband dorsal/ventral review from the same frozen audit:
      summary:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_20260707_1134_final_refreshed_metadata/broadband_dorsal_ventral_summary.json
      logical groups:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_20260707_1134_final_refreshed_metadata/broadband_dorsal_ventral_logical_groups.csv
      well-label candidates:
        /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_20260707_1134_final_refreshed_metadata/platemap_well_label_candidates_dorsal_ventral.csv
      If "broadband filter" means metadata Analog Mode Setting = Neural
      Broadband, then the frozen audit has:
        Neural Broadband logical groups: 26
        Neural Broadband groups with dorsal or ventral labels: 19
        Neural Broadband groups with both dorsal and ventral labels: 8
        raw files inside those dorsal+ventral Neural Broadband groups: 25
      If "broadband" means the explicit Axion-derived
      `_BroadbandProcessor.raw` variant, then only one dorsal+ventral logical
      group currently has that explicit file:
        5_28_26_pvreporter/134-0150/pv_reporter_cl23_dorsal_and_ventral_exp17_2(000)
      That explicit `_BroadbandProcessor.raw` dorsal+ventral count is:
        logical groups: 1
        raw files: 1
      The eight Neural Broadband dorsal+ventral logical groups are:
        5_28_26_h1/133-1555/h1_dorsal_and_ventral_exp17_3(000)
        5_28_26_h1/133-1555/h1_dorsal_and_ventral_exp17_3(001)
        5_28_26_h1/133-1555/h1_dorsal_and_ventral_exp17_3(002)
        5_28_26_h1/133-1555/h1_dorsal_and_ventral_exp17_3(003)
        5_28_26_h1/134-0150/h1_dorsal_and_ventral_exp17_2(000)
        5_28_26_h1/134-0150/h1_dorsal_and_ventral_exp17_2(001)
        5_28_26_pvreporter/134-0150/pv_reporter_cl23_dorsal_and_ventral_exp17_2(000)
        5_28_26_pvreporter/134-0150/pv_reporter_cl23_dorsal_and_ventral_exp17_2_round2(000)
      Candidate well-level dorsal/ventral calls decoded from the matched
      `.platemap` sidecars are:
        H1 5_28 platemap:
          A1, A2, A3 = H1 Ventral SOSR
          B1, B2, B3 = H1 Dorsal SOSR
        CL23 PV 5_28 platemap:
          A1, A2, A3 = CL 23 PV Ventral SOSR
          B1, B2, B3 = CL 23 PV Dorsal SOSR
      Treat these as candidate well-level biology labels from decoded Axion
      platemap bytes until reviewed, but they are stronger evidence than
      filename-only dorsal/ventral inference.
  schema update:
    raw_files.csv now carries Axion metadata timing fields when metadata is
    available:
      block_vector_start_time
      experiment_start_time
      added_date
      metadata_modified_date
      duration_s
      sampling_frequency_hz
    logical_recording_groups.csv also rolls these up as per-group values:
      block_vector_start_times
      experiment_start_times
      added_dates
      metadata_modified_dates
      duration_s_values
      duration_min_s
      duration_max_s
      duration_max_min
      sampling_frequency_hz_values
      num_channels_values
    These are recording/file metadata times, distinct from filesystem
    modified_time, which mostly reflects upload/copy state.
  platemap/biology sidecar update:
    The audit now inventories Axion `.platemap` sidecars and writes:
      platemap_files.csv
    The `.platemap` files are binary AxionBio files, but readable biology labels
    are embedded as strings. Current incoming examples include:
      H1 ventral sosr
      H1 with virus
      no activity so will not use
      CL 23 PV Ventral SOSR
      CL 23 PV Dorsal SOSR
      CL 32 PV Ventral SOSR
      CL 32 PV Dorsal SOSR
      H1 Ventral SOSR
      H1 Dorsal SOSR
      Ventral - no as active
      no opsin
      opsin
      Dorsal iCtrl SCN8A
      Dorsal SCN8A mutant
      Ventral mut SCN8A
      Ventral iCtrl SCN8A
    logical_recording_groups.csv now includes:
      metadata_recording_names
      metadata_descriptions
      metadata_barcodes
      candidate_platemap_count
      candidate_platemap_files
      candidate_platemap_label_candidates
    Groups with no candidate `.platemap` match are flagged in issues.csv and
    logical_recording_groups.csv as:
      missing_candidate_platemap
    Current moving check at 2026-07-07T11:19:11 flagged 9 groups: 7
    older_or_existing groups and 2 new_upload groups. The new_upload missing
    groups are:
      incoming/manny4tbum_20260706/134-0150/(000)
      incoming/manny4tbum_20260706/134-0150/(001)
    The earlier CL23 PV `5_25_26_pvreporter/133-1555` group now matches the
    parent `pv_reporter_cl23_dorsal_and_ventral_exp17.platemap` after stem
    normalization, so it should not be treated as missing a platemap.
    Current interpretation: `.raw` metadata can provide recording-level notes
    such as RecordingName, Description, Barcode, plate dimensions, timing, and
    num_plate_map_entries. It does not yet provide trusted well-level biology
    labels in our extracted metadata. The `.platemap` sidecars are currently
    the clearest reviewable source for treatment/group biology. Do not let
    these labels automatically drive Nextflow yet; use them as ground-truth
    review/candidate-manifest context until we implement and validate an exact
    well-level Axion platemap decoder.
    Note: recordings with `raw_metadata_missing` can still have candidate
    `.platemap` labels, but their `.raw` recording description/barcode fields
    will remain blank in the audit until the MATLAB raw metadata inventory is
    rerun and matched.
  stimulation/opto update:
    The audit now uses the existing repo stimulation parser
    (`src/axion_mea/io/raw_stim_parser.py`) to inspect `.raw` stimulation tags
    without loading voltage data. This is not inferred from file names or
    platemap labels. raw_files.csv now includes:
      stim_parse_status
      stim_parse_error
      stim_event_count
      stim_led_event_count
      stim_electrode_event_count
      stim_unlinked_event_count
      stim_source_kinds
      stimulated_wells
      stim_first_event_time_s
      stim_last_event_time_s
      stim_event_time_s_values
      stim_event_descriptions
      opto_on_interval_count
    logical_recording_groups.csv now rolls those into:
      stim_parse_status_counts
      stim_parse_errors
      has_stim_events
      has_led_stimulation
      has_electrode_stimulation
      stim_event_count_values
      stim_event_count_max
      stim_led_event_count_values
      stim_led_event_count_max
      stim_electrode_event_count_values
      stim_electrode_event_count_max
      stim_unlinked_event_count_values
      stim_source_kinds
      stimulated_wells
      stim_first_event_time_s
      stim_last_event_time_s
      stim_event_time_s_values
      stim_event_descriptions
      opto_on_interval_count_values
    Refreshed final audit counts:
      raw files with any stimulation events: 35/88
      raw files with LED stimulation events: 35/88
      raw files with electrode stimulation events: 0/88
      logical groups with any stimulation events: 13/42
      logical groups with LED stimulation: 13/42
      logical groups with electrode stimulation: 0/42
      LED-positive raw files by variant:
        primary_raw: 13
        broadband_processor_raw: 4
        filter_1Hz-200Hz: 9
        filter_200Hz-3kHz: 9
    Current check at 2026-07-07T11:27:40 found 13 logical groups with LED
    stimulation. New-upload LED-stim groups were:
      6_18_2026_plate2/129-8445/ventral_sosrs_2(000):
        50 events, 302.22664-400.22736 s, wells B4;B5;D2;E2;E5
      6_18_2026_plate2/129-8445/129-8445/ventral_sosrs_2_opsin(000):
        50 events, 301.49272-399.49344 s, wells B2;B4;B5;C6;D2;D6;E2;E5
      6_18_2026_plate2/129-8445/129-8445/ventral_sosrs_2_opsin(001):
        50 events, 302.11552-400.11624 s, wells B2;B4;B5;C6;D2;D6;E2;E5
      6_22_2026/129-8445/ventral_sosrs_opsin_day3(000-005):
        each has 50 LED events, wells A3;B4;B5;C3;C5;C6;D2;D6;E5,
        with first/last event times around 300-400 s.
    Older LED-stim groups were the 2_12 opto_test files and 2_20 test(000).
    This can determine whether the recording had opto/LED stimulation and which
    wells were targeted according to raw stimulation tags. It should still be
    treated as ground-truth/preflight context; do not use it to silently drive
    Nextflow until a reviewed manifest explicitly selects how stimulation
    status should affect processing.
  known-usability rule:
    If Axion metadata duration_s is below 120 seconds, the audit marks the
    logical recording group with:
      duration_under_2min_unusable
    This is a ground-truth review flag: recordings shorter than 2 minutes are
    considered definitely not usable, even if the raw file imports cleanly.
    Current refreshed check at 2026-07-07T12:02:17 flagged 5 groups:
      older_or_existing/2_24_2026/134-0150/test(001): 1 s
      new_upload/5_28_26_h1/133-1555/h1_dorsal_and_ventral_exp17_3(001): 12.75 s
      new_upload/5_28_26_h1/133-1555/h1_dorsal_and_ventral_exp17_3(002): 12.5 s
      new_upload/5_28_26_h1/134-0150/h1_dorsal_and_ventral_exp17_2(000): 5.25 s
      new_upload/Testing_mea_transient_plateing/134-0150/My Experiment(001): 8.5 s
  current flagged naming/folder issue:
    h1_exp17(000) appears in both:
      incoming/manny4tbum_20260706/5_25_2026/134-0150
      incoming/manny4tbum_20260706/5_25_2026/134-0150/134-0150
    This is likely a duplicate/nesting issue to resolve manually.
  superseded metadata-missing note:
    Earlier moving checks listed metadata-missing new-upload groups while rsync
    and metadata inspection were still in progress. That note is superseded by
    the refreshed `20260707_1134_parallel` metadata inventory and refreshed
    ground-truth audit: 88/88 raw files now have metadata status `ok`, and
    `raw_metadata_missing` is currently 0 for the finalized upload set.
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
current loader, avoid treating those wells as running, and avoid any standard
MATLAB Axion File Loader voltage-export submission from affected recordings
until a supported ingestion path is chosen.

Important correction from the aborted SixWell smoke attempt on 2026-07-07:
metadata peek success is not enough. If metadata inspection sees
BlockVectorMetaData checksum / Unexpected BlockVectorMetadata length warnings,
that raw must be considered metadata-only readable and blocked from the
standard voltage-export path. Do not submit it just to test geometry. The
metadata inventory, ground-truth audit, selection inventory, scale-up manifest
builder, and direct per-well prep now carry/consult:

```text
block_vector_warning_seen
block_vector_warning_ids
block_vector_warning_messages
```

Rows with `block_vector_warning_seen=true` should be treated as blocked for
standard export until we have a validated bypass/rescue extractor.
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
submission, but only after choosing a SixWell raw with
`block_vector_warning_seen=false`. Confirm one well exports with 64 channels,
writes a 64-row channel mapping, prepares SpikeInterface/AIND params from the
SixWell template, and does not reuse any Lumos 48-well geometry or
channel-count settings.

Aborted smoke attempt:

```text
recording: sixwell_smoke_2_24_2026_134-0150_test000_primary
raw: /nfs/turbo/umms-parent/axion_mea_files_directory/2_24_2026/134-0150/test(000).raw
well: B3
jobs:
  export_B3: 53047846
  nwb_B3: 53047847
  spikeinterface_B3: 53047848
  aind_B3: 53047849
outcome: canceled by user/Codex after BlockVector warnings appeared in the
  export log; downstream dependency jobs did not run.
correction: do not use this raw for a standard-loader SixWell smoke unless a
  refreshed metadata inventory proves `block_vector_warning_seen=false`.
```

Current SixWell smoke submitted on `2026-07-07`:

```text
recording: sixwell_smoke_20260528_134-0150_pv_cl23_dv_exp17_2_000_primary_raw
source logical group:
  incoming/manny4tbum_20260706/5_28_26_pvreporter/134-0150 ::
  pv_reporter_cl23_dorsal_and_ventral_exp17_2(000)
raw:
  /nfs/turbo/umms-parent/axion_mea_files_directory/incoming/manny4tbum_20260706/5_28_26_pvreporter/134-0150/pv_reporter_cl23_dorsal_and_ventral_exp17_2(000).raw
raw variant: primary_raw
loader dataset: RawVoltageData
metadata filter signature:
  analog=Neural Broadband |
  acquisition_hp=0.1 Hz IIR |
  acquisition_lp=None |
  derived_hp=<blank> |
  derived_lp=<blank>
metadata gate:
  plate_type_name=SixWell
  duration_s=602.75
  num_channels=384
  block_vector_warning_seen=false
  standard_export_allowed=true
well: A1
manual well-selection note:
  This recording has `.spk` sidecars but does not have exported
  `*_spike_counts.csv` or `*_spike_list.csv` files. That blocks automatic
  activity-based well selection, but it does not block a targeted one-well
  geometry/export smoke where the well is named explicitly.
generated batch:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/sixwell_smoke_20260528_134-0150_pv_cl23_dv_exp17_2_000_primary_raw
generated manifest sanity check:
  plate_family=cytoview_6well
  plate_map=metadata/plate_maps/axion_6_well_plate_map.csv
  electrode_geometry=metadata/plate_maps/axion_per_well_8x8_electrode_geometry.csv
  params_template=config/aind_axion_cytoview6_params.json
  n_chan_bin=64
submitted jobs:
  export_A1: 53051307
  nwb_A1: 53051308
  spikeinterface_A1: 53051309
  aind_A1: 53051310
initial Slurm resources:
  export_A1 requested 64G
  nwb_A1 requested 32G
  spikeinterface_A1 requested 8G
  aind_A1 requested 8G
current outcome:
  export_A1 completed, exit 0, elapsed 00:01:09, MaxRSS about 13.9 GB.
  nwb_A1 completed, exit 0, elapsed 00:00:40.
  spikeinterface_A1 completed, exit 0, elapsed 00:00:06.
  aind_A1 entered current AIND/Nextflow and is running.
export proof:
  binary:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/data/interim/kilosort_binary/sixwell_smoke_20260528_134-0150_pv_cl23_dv_exp17_2_000_primary_raw/A1/A1.bin
  binary_size_bytes: 964400000
  channel_mapping_rows: 64
  n_chan_bin: 64
  n_samples: 7534375
  duration_s: 602.75
  fs: 12500
  first mapped electrode: A1 channel 11 at x=0,y=0
  last mapped electrode: A1 channel 88 at x=2100,y=2100
AIND dispatch proof:
  job_dispatch completed and parsed SpikeInterface binary input as:
    reader_type=binary
    num_channels=64
    duration=602.75 s
    session=sixwell_smoke_20260528_134-0150_pv_cl23_dv_exp17_2_000_primary_raw_A1
  AIND params include SixWell values:
    dmin=300
    dminx=300
    x_centers=8
    nearest_templates=64
    whitening_range=16
AIND child-job status:
  job_dispatch: 53051358 completed, exit 0.
  preprocessing: 53051367 completed, exit 0.
  nwb_ecephys: 53051368 completed, exit 0.
  spikesort_kilosort4: 53051380 submitted to gpu partition and pending for a
    GPU slot with pending reason `(Resources)` at the time this note was
    written.
```

New-upload automatic spike-count lane submitted on `2026-07-07`:

```text
goal:
  Start processing every new-upload recording that is immediately safe for the
  existing automatic activity-selection route, without waiting serially for the
  SixWell smoke or for one recording to finish before the next recording starts.
guardrails:
  - only raw files with refreshed metadata matches were included,
  - rows with block_vector_warning_seen=true were blocked,
  - rows missing spike_counts_csv were not auto-selected,
  - selected wells came from Axion *_spike_counts.csv activity sidecars,
  - raw metadata still locked plate profile, channel count, geometry, and params.
root:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_autolane_new_upload_20260707_132852
inventory:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_autolane_new_upload_20260707_132852/selection_asset_inventory/aind_selection_asset_inventory.csv
manifest:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_autolane_new_upload_20260707_132852/recording_manifest_all_variants/recordings_manifest.csv
recording batch plan:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_autolane_new_upload_20260707_132852/recording_batch_plan
manifest counts:
  raw rows inventoried: 74
  ready_to_submit: 6
  blocked_missing_assets_or_metadata: 65
  blocked_blockvector_metadata_warning: 3
  ready plate profile: lumos_48well
  ready raw variant: primary_raw_NeuralBroadband
  ready loader dataset: RawVoltageData
important limitation:
  Filtered derived raws from the same recordings were inventoried but not
  submitted in this lane because the current selection asset inventory does not
  yet propagate the primary recording's spike_counts_csv/spike_list_csv to
  derived `_Filter(...)` raw variants. That is a later inventory-logic fix, not
  a raw-loader failure.
submitted recordings:
  6_22_2026/129-8445 :: ventral_sosrs_opsin_day3(000)
  6_22_2026/129-8445 :: ventral_sosrs_opsin_day3(001)
  6_22_2026/129-8445 :: ventral_sosrs_opsin_day3(002)
  6_22_2026/129-8445 :: ventral_sosrs_opsin_day3(003)
  6_22_2026/129-8445 :: ventral_sosrs_opsin_day3(004)
  6_22_2026/129-8445 :: ventral_sosrs_opsin_day3(005)
selected wells per recording:
  A3, B4, B5, C3, C5, C6, D2, D6, E5
selected well pipelines submitted:
  54
submitted jobs table:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_autolane_new_upload_20260707_132852/recording_batch_plan/submitted_recording_batches.tsv
supervisors submitted:
  53052723  ventral_sosrs_opsin_day3(000)
  53052724  ventral_sosrs_opsin_day3(001)
  53052725  ventral_sosrs_opsin_day3(002)
  53052726  ventral_sosrs_opsin_day3(003)
  53052727  ventral_sosrs_opsin_day3(004)
  53052728  ventral_sosrs_opsin_day3(005)
status at submission snapshot:
  The first export wave had begun running on the standard partition. Downstream
  NWB, SpikeInterface, and AIND jobs were pending on per-well dependencies.
  GPU Kilosort jobs will queue behind available gpu partition resources.
```

SixWell manual all-well discovery lane submitted on `2026-07-07`:

```text
policy decision:
  FortyEightWell/Lumos recordings must remain spike-count/activity gated before
  broad submission because 48 wells per recording can waste substantial compute.
  SixWell/CytoView recordings are allowed to run all wells when spike-count
  sidecars are missing, because there are only six wells and this is currently
  the practical way to discover whether usable spikes exist.
code change:
  scripts/prepare_aind_recording_batches.py now supports manifest rows with an
  explicit `wells` column and no `selection_manifest`. In that case it skips
  `select_aind_wells.sh` and calls `prepare_aind_well_batch.sh --wells ...`.
  This preserves the 48-well activity-filter route while allowing deliberate
  SixWell all-well discovery rows.
scope:
  new-upload SixWell primary raw rows only
  standard_export_allowed=true
  block_vector_warning_seen=false
  duration_s >= 120
  raw_variant=primary_raw
  loader dataset=RawVoltageData
excluded:
  SixWell filtered and BroadbandProcessor derived variants were not submitted
  in this lane. The first discovery pass is primary raw only to avoid multiplying
  jobs across duplicate filter variants before we know which wells are useful.
  BlockVector-warning rows remain blocked.
root:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_sixwell_manual_primary_20260707_133604
manifest:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_sixwell_manual_primary_20260707_133604/sixwell_manual_primary_recordings_manifest.csv
recording batch plan:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_sixwell_manual_primary_20260707_133604/recording_batch_plan
submitted jobs table:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_sixwell_manual_primary_20260707_133604/recording_batch_plan/submitted_recording_batches.tsv
submitted supervisor table:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_sixwell_manual_primary_20260707_133604/recording_batch_plan/submitted_recording_supervisors.tsv
counts:
  recordings: 19
  all-six-well recordings: 18
  one recording with A1 excluded because A1 was already submitted as the SixWell
    smoke: 1
  selected/manual well pipelines submitted: 113
submitted supervisors:
  53054491..53054509, one per SixWell manual recording.
status at submission snapshot:
  113 SixWell export jobs were queued on the standard partition, with each
  downstream NWB, SpikeInterface, and AIND job pending on its per-well
  dependency chain.
```

Live AIND launcher issue found during the `2026-07-07` new-upload scale-up:

```text
status checked:
  2026-07-07 early afternoon EDT
submitted processing scope:
  48-well auto lane: 6 recordings, 54 selected well pipelines
  SixWell manual lane: 19 recordings, 113 selected/manual well pipelines
  total new scale-up lanes: 25 recordings, 167 well pipelines
  plus separate SixWell smoke A1: 1 well pipeline
observed failure:
  Thirty-seven AIND parent jobs failed in about 0-1 seconds while using the
  pre-fix submitted sbatch body. The first ten observed failures were 48-well
  AIND parents:
    53052522  6_22_2026/129-8445 ventral_sosrs_opsin_day3(000) C6
    53052530  6_22_2026/129-8445 ventral_sosrs_opsin_day3(000) D6
    53052538  6_22_2026/129-8445 ventral_sosrs_opsin_day3(001) A3
    53052542  6_22_2026/129-8445 ventral_sosrs_opsin_day3(001) B4
    53052587  6_22_2026/129-8445 ventral_sosrs_opsin_day3(002) C3
    53052591  6_22_2026/129-8445 ventral_sosrs_opsin_day3(002) C5
    53052603  6_22_2026/129-8445 ventral_sosrs_opsin_day3(002) D6
    53052611  6_22_2026/129-8445 ventral_sosrs_opsin_day3(003) A3
    53052619  6_22_2026/129-8445 ventral_sosrs_opsin_day3(003) B5
    53052623  6_22_2026/129-8445 ventral_sosrs_opsin_day3(003) C3
  Additional SixWell manual AIND parents then failed with the same shared
  shim/stale-handle pattern. The full failed parent list is captured in the
  reproducible rerun manifest below; initial examples were:
    53054122  sixwell_manual_primary_5_25_2026_134-0150_134-0150_h1_exp17(001) B1
    53054130  sixwell_manual_primary_5_25_2026_134-0150_134-0150_h1_exp17(001) B3
    53054154  sixwell_manual_primary_5_25_2026_134-0150_h1_exp17(000) B3
    53054166  sixwell_manual_primary_5_25_26_pvreporter_133-1555_pv_reporter_cl23_dorsal_and_ventral(000) A3
    53054210  sixwell_manual_primary_5_28_26_h1_133-1555_h1_dorsal_and_ventral_exp17_3(000) A2
    53054218  sixwell_manual_primary_5_28_26_h1_133-1555_h1_dorsal_and_ventral_exp17_3(000) B1
    53054226  sixwell_manual_primary_5_28_26_h1_133-1555_h1_dorsal_and_ventral_exp17_3(000) B3
    53054234  sixwell_manual_primary_5_28_26_h1_134-0150_h1_dorsal_and_ventral_exp17_2(001) A2
    53054303  sixwell_manual_primary_Testing_mea_transient_plateing_134-0150_My_Experiment(000) A2
important interpretation:
  For inspected failed lanes, export, NWB export, and SpikeInterface prep all
  completed before the AIND parent failed. This is not evidence that those raw
  files, wells, SixWell geometry, or Kilosort are bad.
error signature:
  chmod: cannot access
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/tools/aind_python_shim/python:
    No such file or directory
root cause:
  Same class as the historical concurrent Nextflow launch/cache collision, but
  this time the shared runtime object was the Python shim. Multiple AIND parent
  jobs were concurrently removing/writing/chmod'ing the same shared
  `tools/aind_python_shim/python` file.
fix applied:
  `slurm/run_aind_nwb_well.sbatch` now creates a per-job shim under:
    scratch/aind_nextflow/<recording>/<well>/python_shim/<slurm_job_id>/python
  and exports that per-job `AIND_PYTHON_SHIM_DIR` before launching Nextflow.
  This keeps the existing multi-prefix Python wrapper logic while removing the
  cross-job race on the shared shim file.
operational warning:
  Slurm snapshots the sbatch script at submit time. Any already-submitted
  pending AIND parent jobs still carry the old shared-shim launcher body. To
  guarantee the fix, cancel/resubmit only the affected AIND parent jobs using
  the saved per-well submit commands or regenerate the batch plan with the fixed
  wrapper. Do not rerun raw export/NWB/SpikeInterface prep unless those upstream
  jobs actually failed.
reproducible recovery path:
  Recovery must be AIND-parent-only for this failure class. The upstream
  per-well raw export, NWB export, and SpikeInterface prep products remain the
  provenance-backed inputs. The rerun command for each failed AIND parent keeps
  the original per-well `AIND_CONFIG`, `NWB_FILE`, result directory, and
  `afterok:<spikeinterface_job>:<nwb_job>` dependency chain.
  Recovery root:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_resubmit_after_python_shim_fix_20260707_1430
  Rerun manifest with old job IDs, upstream dependency IDs, per-well env paths,
  NWB inputs, result folders, exact commands, and new job IDs:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_resubmit_after_python_shim_fix_20260707_1430/failed_aind_parent_resubmit_manifest.csv
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_resubmit_after_python_shim_fix_20260707_1430/failed_aind_parent_resubmit_manifest.json
  Submit script:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_resubmit_after_python_shim_fix_20260707_1430/submit_failed_aind_parents_only.sh
  Submitted old-to-new job table:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_resubmit_after_python_shim_fix_20260707_1430/submitted_failed_aind_parent_reruns.tsv
  Submitted reruns:
    rows: 37
    new AIND parent jobs: 53055454..53055490
    immediate status check after submission: all 37 PENDING with reason
      `(Priority)`, no immediate shim failure observed.
clear-slate status snapshot:
  Because raw Slurm job counts are not one-to-one with wells, the current unit
  of account is the well pipeline: recording/well through export -> NWB ->
  SpikeInterface prep -> AIND/Nextflow -> Kilosort4 child. The first clear
  slate snapshot was written here:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_clear_slate_20260707_1445/clear_slate_summary.txt
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_clear_slate_20260707_1445/well_pipeline_clear_slate.csv
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_clear_slate_20260707_1445/well_pipeline_clear_slate.json
  Snapshot counts:
    total well pipelines including smoke: 168
    48well_auto: 54 wells across 6 recordings
    sixwell_manual: 113 wells across 19 recordings
    sixwell_smoke: 1 well
    export: 168/168 completed
    NWB export: 168/168 completed
    SpikeInterface prep: 168/168 completed
    original AIND parents: 131 running, 37 failed old-wrapper attempts
    effective AIND parents after replacement: 131 running, 37 pending
  Interpretation:
    One running Kilosort4 child proves that at least one well has reached the
    GPU sorter stage, so the route is live. It does not prove every well will
    finish successfully; each well can still fail later for biological/signal
    reasons, Kilosort low-activity/template issues, GPU/runtime failures, or
    postprocessing. Use the clear-slate CSV, not raw `squeue`, to decide which
    well pipelines are accounted for.
return-later checkpoint at 2026-07-07 13:58 EDT:
  Per-well step model:
    Axion prep layer:
      1. export_axion_well_binary
      2. export_axion_well_nwb
      3. prepare_aind_spikeinterface_well
    AIND/Nextflow layer:
      4. job_dispatch
      5. preprocessing
      6. nwb_ecephys
      7. spikesort_kilosort4
      8. postprocessing
      9. curation
      10. visualization
      11. results_collector / quality-control collection
      12. nwb_units
  Current interpretation:
    The Axion prep layer is complete for all 168 well pipelines.
    No current well has yet been confirmed complete through all AIND downstream
    stages to `nwb_units`.
    Two wells have completed the GPU Kilosort4 stage successfully:
      - sixwell_smoke_20260528_134-0150_pv_cl23_dv_exp17_2_000_primary_raw / A1
        Kilosort4 job 53051380, COMPLETED exit 0.
      - 6_22_2026_129-8445_ventral_sosrs_opsin_day3(001)_FortyEightWellLumos_primary_raw_NeuralBroadband / E5
        Kilosort4 job 53053851, COMPLETED exit 0.
    Live Kilosort4 scheduler state:
      completed today: 2
      running: 2
      pending: 110
      failed observed at this checkpoint: 0
    The Kilosort4 stage is GPU-scheduler limited. Each Kilosort4 child requests
    `gpu` partition and `gres/gpu:1`; this is not a pipeline logic limit of one
    Kilosort at a time.
  When returning later, check:
    1. whether any trace has `nwb_units COMPLETED`,
    2. whether Kilosort4 failures appeared,
    3. whether the fixed-wrapper rerun jobs 53055454..53055490 moved from
       pending into running/completed,
    4. regenerate a new clear-slate snapshot rather than relying only on raw
       `squeue` totals.
return-later checkpoint at 2026-07-07 14:25 EDT:
  Progress:
    Kilosort4 completed: 16 well pipelines
    postprocessing completed: 15 well pipelines
    results_collector completed: 12 well pipelines
    quality_control completed: 12 well pipelines
    quality_control_collector completed: 11 well pipelines
    nwb_units completed: 12 well pipelines
  First confirmed current-batch wells through `nwb_units`:
    6_22_2026_129-8445_ventral_sosrs_opsin_day3(000): B4, B5, C3, E5
    6_22_2026_129-8445_ventral_sosrs_opsin_day3(001): B5, C3, C5, C6, D2, D6, E5
    sixwell_smoke_20260528_134-0150_pv_cl23_dv_exp17_2_000_primary_raw: A1
  Live Kilosort4 scheduler state:
    completed today: 16
    running: 4
    pending: 111
    failed observed at this checkpoint: 0
  New issue:
    The 37 AIND parent reruns submitted as 53055454..53055490 all failed after
    reaching Nextflow `job_dispatch`, not with the old 1-second shared-shim
    failure. The observed error is:
      /var/spool/slurmd.spool/job<child>/slurm_script: line 317:
      syntax error near unexpected token `('
    The failing command contains unescaped paths/session names with parentheses
    such as `ventral_sosrs_opsin_day3(000)` and
    `sixwell_manual_primary_scn8a_sosrs_dorsal_vs_ventrals_133-1555_(000)`.
    Treat this as a generated Nextflow/Slurm script quoting issue for rerun
    paths, not a raw export/NWB/SpikeInterface/Kilosort failure.
  Operational interpretation:
    Original AIND jobs are producing valid end-to-end outputs through
    `nwb_units`; the pipeline itself is working. The rerun recovery path still
    needs a quoting fix before rerunning those 37 failed AIND parents again.
return-later checkpoint at 2026-07-07 14:46 EDT:
  Main pipeline progress:
    Kilosort4 completed: 28 well pipelines
    Kilosort4 failed observed: 0
    postprocessing completed: 28 well pipelines
    results_collector completed: 27 well pipelines
    quality_control completed: 23 well pipelines
    quality_control_collector completed: 18 well pipelines
    nwb_units completed: 18 well pipelines
  Rerun recovery status:
    The 37 failed AIND parent reruns did need to be rerun, but not from raw
    export/NWB/SpikeInterface. Only the AIND parent layer needed another
    recovery submission.
    Root:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_rerun_after_runoptions_quote_fix_20260707_1445
    Manifest:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_rerun_after_runoptions_quote_fix_20260707_1445/quote_fix_rerun_manifest.csv
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_rerun_after_runoptions_quote_fix_20260707_1445/quote_fix_rerun_manifest.json
    Fix applied:
      `config/aind_nextflow_slurm_greatlakes.config` now quotes the
      Singularity/Apptainer `-B <python_shim>/python:/usr/local/bin/python`
      bind and the `--env PATH/HOME/XDG_CACHE_HOME/MPLCONFIGDIR` values. This
      prevents generated Nextflow child scripts from choking on parentheses in
      per-well work paths.
    Canary:
      old AIND parent: 53052522
      failed rerun parent: 53055454
      quote-fix rerun parent: 53060114
      status: RUNNING at checkpoint; child `job_dispatch` 53060117 completed
      exit 0 and `preprocessing` 53060184 completed exit 0. This proves the
      parenthesis quoting bug was fixed for at least the canary.
    Remaining 36 quote-fix reruns:
      submitted as 53060261..53060296
      status at checkpoint: all 36 RUNNING, no immediate quote failure observed.
    Operational interpretation:
      Do not rerun the whole pipeline. The 37 affected wells are now represented
      by quote-fix AIND parent jobs 53060114 and 53060261..53060296. Continue
      monitoring these new AIND parents and their child `job_dispatch` traces.
return-later checkpoint at 2026-07-07 14:53 EDT:
  Main pipeline progress:
    Kilosort4 completed: 33 well pipelines
    Kilosort4 failed observed: 0
    postprocessing completed: 30 well pipelines
    results_collector completed: 28 well pipelines
    quality_control completed: 28 well pipelines
    quality_control_collector completed: 28 well pipelines
    nwb_units completed: 28 well pipelines
  Rerun recovery status:
    The quote-fix recovery jobs are now fully submitted:
      canary: 53060114
      remaining 36: 53060261..53060296
    At this checkpoint all 37 quote-fix AIND parent jobs are RUNNING and none
    have failed. The canary already proved `job_dispatch` and preprocessing
    after the quoting fix.
  Live scheduler interpretation:
    Five Kilosort4 children are running on GPU nodes, and the remaining
    Kilosort4 children are queued. Pending Kilosort4 reason includes
    `AssocGrpGRES`, so the remaining throughput is GPU/account scheduling, not
    a missing submission step.
  Operational interpretation:
    No full raw/NWB/SpikeInterface rerun is needed. The missing affected wells
    have active corrected AIND-parent jobs, and the rest of the run should
    continue through AIND/Nextflow as scheduler resources release.
return-later checkpoint at 2026-07-07 15:08 EDT:
  Unified status logic:
    `scripts/summarize_aind_current_well_ledger.py` is now the single current
    status ledger for this submission. It starts from the expected well rows in
    the submitted batch manifests, joins old failed AIND parents to their
    quote-fix rerun parents, then reads each per-well Nextflow `trace.txt`.
    Do not use raw `squeue` alone as truth because it mixes parent wrappers and
    internal Nextflow child jobs.
  Current ledger outputs:
    latest symlink:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_latest
    snapshot:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260707_150831
    files:
      unified_well_status.csv
      unified_recording_status.csv
      unified_status_summary.txt
      unified_status_summary.json
  Definitions:
    Unit of account: one recording plus one well.
    Passed Kilosort: `spikesort_kilosort4` is `COMPLETED` in that well's
    Nextflow trace.
    Fully done: `nwb_units` is `COMPLETED` in that well's Nextflow trace.
    Effective AIND parent: quote-fix rerun job when one exists, otherwise the
    originally submitted AIND parent job.
  Current unified status at 2026-07-07 15:08:31 EDT:
    expected well pipelines: 168
    expected recordings: 26
    plate-family wells: 54 FortyEightWellLumos, 114 SixWell
    lane wells: 54 48well_auto, 113 sixwell_manual_primary, 1 sixwell_smoke
    Kilosort4 completed: 44 well pipelines
    Kilosort4 failed: 3 well pipelines
    Kilosort4 not entered yet: 121 well pipelines
    nwb_units fully completed: 36 well pipelines
    live Slurm Kilosort4 children: 4 RUNNING, 116 PENDING
    live AIND parent jobs: 131 RUNNING
  Current real Kilosort failures:
    sixwell_manual_primary_134-0150_(001) B2:
      ValueError: Found array with 0 sample(s) (shape=(0, 31)) while a minimum
      of 1 is required by TruncatedSVD.
    sixwell_manual_primary_134-0150_(001) B3:
      ValueError: n_samples=4 should be >= n_clusters=6.
    sixwell_manual_primary_5_25_2026_134-0150_134-0150_h1_exp17(001) A3:
      ValueError: n_samples=2 should be >= n_clusters=6.
    These are low-activity/sparse Kilosort failures, not export/NWB,
    SpikeInterface-prep, quote-path, or raw-ingestion failures.
  Practical interpretation:
    There is now one slate: `unified_well_status.csv`. Counts should be quoted
    from that file. A recording can have some wells fully done while other wells
    are pending Kilosort or have failed Kilosort; therefore "recording done"
    means all expected wells for that recording have `nwb_units COMPLETED`.
return-later checkpoint at 2026-07-07 15:20 EDT:
  Refreshed unified ledger:
    latest symlink:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_latest
    snapshot:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260707_152015
  Current unified status at 2026-07-07 15:20:16 EDT:
    expected well pipelines: 168
    expected recordings: 26
    Kilosort4 completed: 54 well pipelines
    Kilosort4 failed: 16 well pipelines
    Kilosort4 not entered yet: 98 well pipelines
    nwb_units fully completed: 47 well pipelines
    live Slurm Kilosort4 children: 5 RUNNING, 92 PENDING
    live AIND parent jobs: 105 RUNNING
  Recording-level status:
    complete_all_wells: 3 recordings
      - 6_22_2026_129-8445_ventral_sosrs_opsin_day3(004), 9/9 wells
      - 6_22_2026_129-8445_ventral_sosrs_opsin_day3(005), 9/9 wells
      - sixwell_smoke_20260528_134-0150_pv_cl23_dv_exp17_2_000_primary_raw,
        1/1 well
    partially_through_kilosort: 6 recordings
    needs_attention: 6 recordings
    in_progress_before_or_waiting_kilosort: 11 recordings
  Failure interpretation:
    Most current failures are the known sparse/low-activity Kilosort class
    (`n_samples < n_clusters` or zero samples for TruncatedSVD). One current
    SixWell Kilosort failure reports `CUDA error: device-side assert triggered`
    and should be inspected separately before deciding whether it belongs to the
    same sparse-sortability bucket or needs a rerun.
return-later checkpoint at 2026-07-07 15:46 EDT:
  Refreshed unified ledger:
    latest symlink:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_latest
    snapshot:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260707_154654
  Current unified status at 2026-07-07 15:46:56 EDT:
    expected well pipelines: 168
    expected recordings: 26
    Kilosort4 completed: 79 well pipelines
    Kilosort4 failed: 26 well pipelines
    Kilosort4 not entered yet: 63 well pipelines
    nwb_units fully completed: 71 well pipelines
    live Slurm Kilosort4 children: 5 RUNNING, 58 PENDING
    live AIND parent jobs: 72 RUNNING
  Recording-level status:
    complete_all_wells: 3 recordings
      - 6_22_2026_129-8445_ventral_sosrs_opsin_day3(004), 9/9 wells
      - 6_22_2026_129-8445_ventral_sosrs_opsin_day3(005), 9/9 wells
      - sixwell_smoke_20260528_134-0150_pv_cl23_dv_exp17_2_000_primary_raw,
        1/1 well
    all_wells_passed_kilosort_downstream_active: 1 recording
    partially_through_kilosort: 9 recordings
    needs_attention: 10 recordings
    in_progress_before_or_waiting_kilosort: 3 recordings
  Practical interpretation:
    The run is still actively advancing. The 48-well Lumos recordings remain
    successful so far, with two fully done and the remaining four partially or
    fully through Kilosort. Most newly observed failures are in SixWell primary
    recordings and should be triaged as sparse/low-activity Kilosort failures
    unless their per-well `failure_summary` says otherwise.
  Low-activity fallback clarification:
    We already proved an isolated fallback route for sparse Kilosort failures:
    `low_activity_ks4_nt2_npcs2`. That route changes `n_templates`,
    `nearest_templates`, and `n_pcs` together to 2. The current 26 Kilosort
    failures are standard-route failures; they have not yet been promoted
    through the fallback route in this bulk SixWell submission.
    Eligibility distinction:
      - `n_samples >= 2` with `n_samples < n_clusters=6` should be eligible for
        the `low_activity_ks4_nt2_npcs2` fallback.
      - `n_samples=1` is still below `n_clusters=2`, so the existing nt2 fallback
        is not expected to rescue it.
      - zero-sample TruncatedSVD failures are no-sortability failures for this
        fallback unless we create a separate no-spikes/no-units terminal route.
      - CUDA device-side assert is separate until inspected.
    Approximate current split from the 26 failures:
      19 likely eligible for `low_activity_ks4_nt2_npcs2`.
      4 have `n_samples=1` and need a different policy.
      2 have zero samples/TruncatedSVD and need a no-sortability policy.
      1 has CUDA device-side assert and needs separate inspection.
return-later checkpoint at 2026-07-07 15:59 EDT:
  Unit-metrics sheet update:
    `scripts/summarize_aind_current_well_ledger.py` now appends per-well unit
    metrics into `unified_well_status.csv` and also writes a compact sheet:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_latest/unit_metrics_by_well.csv
    Current backing snapshot:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260707_160537
  Unit metric definitions:
    Unit metrics are read from each well's curated SpikeInterface output:
      results/aind/<recording>/<well>/curated/block0_None_recording1/
    `unit_count_total` is the number of curated unit IDs.
    `unit_count_sua` maps `KSLabel=good`.
    `unit_count_mua` maps `KSLabel=mua`.
    `unit_count_noise` maps `KSLabel=noise` only if that label is present.
    Important: these are Kilosort/Phy `KSLabel` values propagated through AIND
    postprocessing/curation, not an independent AIND unit-classifier noise call.
    Current observed labels are `good` and `mua`; therefore `unit_count_noise=0`
    means the selected label source did not emit `noise`, not that no unit is
    biologically/noise-like.
    `spike_count_range_per_unit` is min-max spike count across units from
    `curated/block0_None_recording1/spikes.npy`.
  Corrected unit metric totals at 2026-07-07 16:03:27 EDT:
    wells with unit metrics: 87
    units total: 6563
    SUA/good-by-KSLabel total: 853
    MUA-by-KSLabel total: 5710
    noise-by-KSLabel total: 0
    total sorted spikes across metric-populated wells: 732663022
  Correction made after review:
    The compact sheet now includes `unit_labels_observed`, `unit_label_source`,
    and `unit_label_warning` columns. This was added because the earlier summary
    could be misread as "noise was measured and found to be zero." The actual
    source is `curated/block0_None_recording1/properties/KSLabel.npy`, and no
    separate unit-classifier noise labels were found in the current AIND outputs.
  Confirmed provenance at 2026-07-07 16:06 EDT:
    The currently populated unit labels are Kilosort/Phy `KSLabel` values, not
    AIND UnitRefine/Bombcell post-curation labels. Evidence:
      - `spikesorted/.../properties/KSLabel.npy` and
        `curated/.../properties/KSLabel.npy` are identical for inspected wells.
      - the AIND curation task completed, but its log reports:
        `No quality metrics found for block0_None_recording1. Skipping curation`.
      - `processing.json` for inspected wells lists preprocessing, spike
        sorting, postprocessing, and visualization; it does not include an
        `Ephys curation` data process with UnitRefine/Bombcell output.
      - no `unit_labels_<recording>.csv` file was found in the current result
        folders for inspected wells.
    Sheet correction:
      `unit_metrics_by_well.csv` now includes explicit `kslabel_good_count`,
      `kslabel_mua_count`, and `kslabel_noise_count` columns. The older
      `unit_count_sua`, `unit_count_mua`, and `unit_count_noise` columns are
      currently aliases of these KSLabel-derived counts and should not be
      interpreted as independent classifier calls.
    Latest corrected unit totals at 2026-07-07 16:06:28 EDT:
      wells with unit metrics: 88
      units total: 6627
      kslabel_good_total: 854
      kslabel_mua_total: 5773
      kslabel_noise_total: 0
      total sorted spikes across metric-populated wells: 741903432
  Why UnitRefine/Bombcell did not run in the current jobs:
    The current AIND postprocessing parameter set is intentionally lean. For
    inspected completed wells, `repro/aind_params.json` requested only:
      random_spikes, templates, spike_amplitudes, template_similarity,
      correlograms, and unit_locations.
    It did not request `quality_metrics` or `template_metrics`.
    The AIND curation capsule requires `quality_metrics` to do default QC and
    requires `template_metrics` to run UnitRefine/Bombcell unit classification.
    Because those extensions were absent, the curation task exited cleanly but
    skipped classification. This is why Slurm/Nextflow can say curation
    COMPLETED while the output still has only KSLabel-derived labels.
  How to address this without rerunning everything:
    Do not rerun raw import, NWB export, SpikeInterface prep, or Kilosort for
    wells that already have completed Kilosort/postprocessed outputs.
    Add a targeted curation/classification recovery lane:
      1. Select wells with existing completed analyzer output:
           results/aind/<recording>/<well>/postprocessed/block0_None_recording1.zarr
         and/or curated sorting output:
           results/aind/<recording>/<well>/curated/block0_None_recording1/
      2. For each selected well, compute only the missing postprocessing
         extensions on the existing sorting analyzer:
           `quality_metrics`
           `template_metrics`
      3. Rerun only the AIND curation logic, or a small wrapper around the same
         curation code, so UnitRefine/Bombcell can emit:
           `unit_labels_<recording>.csv`
           `curation_<recording>.json`
      4. Do a one-well canary first. Confirm the recovery output produces real
         `unitrefine_*` and/or `bombcell_*` labels before scaling to all completed
         wells.
      5. Keep the recovery outputs under a new timestamped provenance root, for
         example:
           jobs/aind_unit_classification_recovery_YYYYMMDD_HHMMSS/
           results/aind_unit_classification_recovery/<recording>/<well>/
         Do not overwrite the existing AIND results until the recovery lane has
         been validated and joined back into the ledger.
      6. Update `scripts/summarize_aind_current_well_ledger.py` after the canary
         so the ledger prefers true curation labels when present, while keeping
         KSLabel counts as separate provenance columns.
    The recovered ledger should carry both sources explicitly:
      KSLabel columns:
        `kslabel_good_count`, `kslabel_mua_count`, `kslabel_noise_count`
      UnitRefine/Bombcell columns, when recovery exists:
        `unitrefine_sua_count`, `unitrefine_mua_count`,
        `unitrefine_noise_count`, `bombcell_sua_count`, `bombcell_mua_count`,
        `bombcell_noise_count`, `curation_label_source`,
        `curation_recovery_status`
    This is the reproducible middle path: it avoids a full expensive rerun, but
    also avoids reporting KSLabel-only counts as postprocessing curation.
  Future-run parameter decision:
    For new submissions where true SUA/MUA/noise classification is required,
    include `quality_metrics` and `template_metrics` in the AIND postprocessing
    extension list before curation. This should be tested first on one completed
    SixWell recording because it increases compute and may expose dependency or
    metric-computation issues.
  Practical caveat:
    `unit_metrics_status=missing_curated_sorting` means the well has not yet
    produced curated sorting output or failed before that stage. Re-run the
    unified ledger later to populate more rows as the active jobs finish.
return-later checkpoint at 2026-07-08 13:01 EDT:
  Environment:
    The unified ledger was regenerated from the intended Great Lakes conda
    environment, not from the login-node system Python:
      source config/greatlakes_project.env
      source "${CONDA_BASE}/etc/profile.d/conda.sh"
      conda activate "${CONDA_ENV}"
      python scripts/summarize_aind_current_well_ledger.py --output-dir ...
    Effective Python:
      Python 3.11.6 from
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/envs/axion-kilosort
  Current ledger outputs:
    latest symlink:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_latest
    snapshot:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260708_130012
    summary:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260708_130012/unified_status_summary.txt
    well table:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260708_130012/unified_well_status.csv
    recording table:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260708_130012/unified_recording_status.csv
    unit metrics table:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unified_status_20260708_130012/unit_metrics_by_well.csv
  Current unified status:
    expected well pipelines: 168
    expected recordings: 26
    plate-family wells: 54 FortyEightWellLumos, 114 SixWell
    lane wells: 54 48well_auto, 113 sixwell_manual_primary, 1 sixwell_smoke
    wells complete through nwb_units: 122
    wells needing attention at spikesort_kilosort4: 46
    Kilosort4 completed: 122
    Kilosort4 failed: 46
    recordings complete_all_wells: 12
    recordings needs_attention: 14
    live Slurm Kilosort4 children: 0
    live AIND parent jobs: 0
  Recording-level result:
    48well_auto:
      6/6 recordings complete, 54/54 selected wells through nwb_units.
    sixwell_smoke:
      1/1 well through nwb_units.
    sixwell_manual_primary:
      5/19 recordings complete_all_wells, plus 14 recordings needs_attention.
      67/113 wells completed through nwb_units.
      46/113 wells failed at spikesort_kilosort4.
  Current SixWell failure split from `failure_summary`:
    15 wells: ValueError: n_samples=4 should be >= n_clusters=6.
    8 wells: ValueError: n_samples=5 should be >= n_clusters=6.
    7 wells: ValueError: n_samples=3 should be >= n_clusters=6.
    7 wells: ValueError: n_samples=2 should be >= n_clusters=6.
    5 wells: ValueError: n_samples=1 should be >= n_clusters=6.
    3 wells: zero-sample TruncatedSVD.
    1 well: CUDA device-side assert triggered.
  Current unit metrics:
    wells with curated sorting metrics: 122
    total units: 9016
    kslabel_good_total: 998
    kslabel_mua_total: 8018
    kslabel_noise_total: 0
    total sorted spikes across metric-populated wells: 1039219231
  Reproducibility interpretation:
    The workflow is reproducible from accepted raw/NWB-prep inputs through AIND
    and nwb_units for wells with sortable signal. The current run proves this
    at scale for all 54 Lumos auto selected wells, the SixWell smoke, and 67
    SixWell manual wells.
    The broad system is not yet "no issue" because three categories still need
    explicit policy or recovery automation:
      1. older 2_12_2026 and 2_20_2026 raw-ingestion incompatibility,
      2. sparse/no-sortability SixWell Kilosort failures,
      3. one CUDA Kilosort failure requiring inspection.
    For future unattended runs, the next reproducibility step is not another
    full rerun. It is to codify terminal/fallback handling for sparse SixWell
    failures and, separately, add a targeted UnitRefine/Bombcell recovery lane
    if true classifier-derived SUA/MUA/noise labels are required.
return-later checkpoint at 2026-07-08 13:11 EDT:
  Next phase decision:
    Proceed with UnitRefine/Bombcell-style curation/classification using the
    completed AIND outputs wherever possible. The starting population is the
    122 wells that reached nwb_units and have curated SpikeInterface/Kilosort
    outputs under:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/<recording>/<well>/
  Reuse rule:
    For those 122 wells, do not rerun raw Axion export, NWB export,
    SpikeInterface prep, or Kilosort4 just to get classifier labels. Start from
    existing completed outputs:
      postprocessed/block0_None_recording1.zarr
      curated/block0_None_recording1/
    and compute only the missing postprocessing metrics required by curation.
  Built-in status:
    AIND has the curation/classification path, but it was not actually activated
    for the current submitted runs because the active params did not request:
      quality_metrics
      template_metrics
    The current ledger's unit counts are therefore KSLabel-derived counts, not
    UnitRefine/Bombcell-derived labels.
  Required recovery lane:
    1. Pick one completed well as a canary.
    2. Compute missing `quality_metrics` and `template_metrics` on the existing
       analyzer/sorting outputs.
    3. Run only the AIND curation/classification logic, or a small wrapper around
       the same logic, to produce true classification outputs such as:
         unit_labels_<recording>.csv
         curation_<recording>.json
    4. Store canary and scaled outputs under a new timestamped root, for example:
         jobs/aind_unit_classification_recovery_YYYYMMDD_HHMMSS/
         results/aind_unit_classification_recovery/<recording>/<well>/
    5. Extend `scripts/summarize_aind_current_well_ledger.py` so it keeps
       KSLabel counts and UnitRefine/Bombcell counts as separate provenance
       fields and prefers true classifier labels only when present.
  Practical answer:
    It is not "already built in" as a completed current-output product. It is
    partially built into the upstream AIND workflow, but this repo still needs a
    validated targeted recovery lane to apply it to the 122 completed wells
    without a full expensive rerun.
return-later checkpoint at 2026-07-08 13:17 EDT:
  Pipeline step model is now explicit:
    Step 1:
      Axion raw/NWB preparation through AIND/Kilosort/postprocessing/curation/
      results/QC/nwb_units. The output of Step 1 is the per-well AIND result
      folder and unified ledger status.
    Step 2:
      UnitRefine/Bombcell-style classification recovery on Step 1 completed
      wells only. Step 2 starts from existing postprocessed/curated outputs,
      computes missing `quality_metrics` and `template_metrics`, and reruns only
      curation/classification logic.
  New Step 2 implementation files:
    scripts/prepare_aind_unit_classification_recovery.py
    scripts/run_aind_unit_classification_recovery.py
    slurm/run_aind_unit_classification_recovery.sbatch
  Canary prepared from latest ledger:
    candidate completed wells: 122
    recovery root:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_131708
    manifest:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_131708/canary_manifest.csv
    params:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_131708/recovery_params.json
    submit script:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_131708/submit_canary.sh
    submitted table:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_unit_classification_recovery_20260708_131708/submitted_canary.tsv
  Canary submitted:
    recording:
      6_22_2026_129-8445_ventral_sosrs_opsin_day3(000)_FortyEightWellLumos_primary_raw_NeuralBroadband
    well: A3
    Slurm job: 53112023
    output:
      /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind_unit_classification_recovery/aind_unit_classification_recovery_20260708_131708/6_22_2026_129-8445_ventral_sosrs_opsin_day3(000)_FortyEightWellLumos_primary_raw_NeuralBroadband/A3
    status at checkpoint:
      PENDING on standard partition, reason Priority.
  Validation before scale-out:
    The canary must produce:
      classification_recovery_summary.json
      curation/unit_labels_block0_None_recording1.csv
      curation/curation_block0_None_recording1.json
    and those labels must include UnitRefine and, if successful, Bombcell fields.
    Only after this canary is reviewed should Step 2 be scaled to the remaining
    completed wells.
reproducibility rule going forward:
  Treat every launcher/environment fix as a new provenance event. Preserve:
    - original batch manifests,
    - old failed job IDs and error signatures,
    - exact fixed code path used for resubmission,
    - exact per-well env files,
    - upstream dependency job IDs,
    - new submitted job IDs.
  Do not replace the ground truth by memory. Add a timestamped recovery root and
  join old->new job IDs back into a CSV/JSON manifest before considering the
  recovery reproducible.
```

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

## 2026-07-08 Axion Filter Metadata Correction

The Axion file ground-truth and AIND scale-up handoffs now parse structured
filter blocks from raw `dataset_description` text. This is a major provenance
boundary: numeric filter cutoffs and poles are metadata, not just filename
labels.

The old simplified extraction collapsed repeated settings such as
`High Pass Filter` and `Low Pass Filter`, which lost the difference between:

```text
primary Neural Broadband acquisition high-pass/low-pass settings
BroadbandProcessor high-frequency digital filter
BroadbandProcessor low-frequency median filter
Filter(1Hz-200Hz) digital filter settings
Filter(200Hz-3kHz) digital filter settings
```

Code paths updated:

```text
src/axion_mea/filter_metadata.py
scripts/audit_axion_file_ground_truth.py
scripts/build_aind_recordings_manifest.py
scripts/prepare_aind_recording_batches.py
scripts/prepare_aind_well_batch.py
src/axion_mea/well_selection.py
```

Corrected audit output:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_20260708_filter_metadata_patch/
```

CSV handoffs that should carry these columns:

```text
raw_files.csv
logical_recording_groups.csv
filter_metadata_signatures.csv
filter_metadata_value_counts.csv
recordings_manifest.csv
recording_batch_manifest.csv
well_batch_manifest.csv
aind_selection_asset_inventory.csv
```

Required columns include `filter_block_count`, `filter_block_names`,
`filter_blocks_json`, `derived_high_pass_cutoff_freqs`,
`derived_low_pass_cutoff_freqs`, and the section-specific
`digital_filter_settings_*`,
`broadband_processor_high_frequency_digital_filter_*`, and
`broadband_processor_low_frequency_median_filter_*` fields.

## 2026-07-08 Step 1 v4 Manifest Policy: Lumos Plate Maps and CytoView Fallback

A revised no-submit Step 1 manifest was created after confirming that Lumos
standalone Axion `.platemap` files encode active/labeled 48-well state blocks.
The `.platemap` row-major decoding was validated against the 6/22 Lumos
`*_spike_list.csv` Well Information truth table:

```text
6/22 Lumos active wells from sidecar:
A3 B4 B5 C3 C5 C6 D2 D6 E5

6/22 Lumos active/labeled wells decoded from .platemap:
A3 B4 B5 C3 C5 C6 D2 D6 E5
```

The v4 policy is:

```text
Lumos 48-well:
  - Use direct Axion spike sidecars when present.
  - Use matched primary sidecars for matching Filter(200Hz-3kHz) exports.
  - If sidecar CSVs are missing, use decoded standalone .platemap active/labeled
    wells.
  - Do not run all 48 Lumos wells unless no subset can be recovered and the user
    explicitly approves.

CytoView 6-well:
  - For included non-LFP raws, run all six wells.
  - Do not block on missing or low-yield activity sidecars because the plate is
    small.

LFP exports:
  - Excluded.

BlockVector-warning exports:
  - Held/excluded from submit candidates.
```

Current v4 no-submit artifacts:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_manifest_design_20260708_no_submit/raw_variant_decision_manifest_DRAFT_v4_lumos_platemap_cytoview_allwells_review.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_manifest_design_20260708_no_submit/recordings_manifest_nonlfp_th5_DRAFT_v4_lumos_platemap_cytoview_allwells_submit_false.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_manifest_design_20260708_no_submit/summary_v4_lumos_platemap_cytoview_allwells_review.json
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_manifest_design_20260708_no_submit/v4_manifest_policy_command.txt
```

The v4 recordings manifest intentionally keeps `submit=false` for every row.
Counts:

```text
candidate raw rows: 57
expected per-well jobs: 454

CytoView 6-well:
  rows: 33
  well jobs: 198
  policy: all 6 wells

Lumos 48-well:
  rows: 24
  well jobs: 256
  policy:
    direct sidecars: 8 rows, 82 well jobs
    matched primary sidecars: 6 rows, 54 well jobs
    decoded .platemap wells: 10 rows, 120 well jobs
```

Decoded Lumos missing-sidecar well sets:

```text
incoming/manny4tbum_20260706/6_18_2026/129-8445
  A3,B2,B3,B4,B5,C3,D2,D3,E2,E3,E5,F3

incoming/manny4tbum_20260706/6_18_2026_plate2/129-8445
  B2,B4,B5,B6,C6,C7,D2,D6,D7,E2,E5,E6

incoming/manny4tbum_20260706/6_18_2026_plate2/129-8445/129-8445
  B2,B4,B5,B6,C6,C7,D2,D6,D7,E2,E5,E6
```

Important operational note: do not submit the v4 manifest until it has been
reviewed. The v4 manifest is the current clean draft for the next Step 1
submission decision.

Preflight correction after v4 creation: all 57 rows now explicitly carry the
TH=5/Kilosort-preprocessing params template. This avoids falling back to any
older default params during preparation.

```text
CytoView rows:
  config/aind_axion_cytoview6_params_th5_kilosort_preproc_DRAFT.json
  Th_universal = 5
  skip_kilosort_preprocessing = false

Lumos rows:
  config/aind_axion_lumos_params_th5_kilosort_preproc_DRAFT.json
  Th_universal = 5
  skip_kilosort_preprocessing = false

blank params_template rows: 0
missing raw/plate-map/electrode-geometry/params/raw-metadata paths: 0
existing results/aind recording_stem collisions: 0
```

The old `results/aind` contents were not deleted. Instead, the v4 manifest uses
new `step1_nonlfp_th5_20260708_...` recording stems, and a preflight check found
no matching existing result directories. This preserves old Step 1 provenance
while keeping the next run separated by name.

## 2026-07-08 Step 1 v5 Manifest Policy: Lumos Activity OR Plate Map

The Lumos well-selection policy was tightened after review. The correct rule is
an OR union, not a fallback-only rule:

```text
For every included Lumos row:
  final wells = Axion activity-sidecar-selected wells
                OR decoded Axion .platemap active/labeled wells
```

The v5 manifest writes that explicit union into the `wells` column for every
Lumos row, so the preparation step will not silently use only one source.

Current v5 no-submit artifacts:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_manifest_design_20260708_no_submit/raw_variant_decision_manifest_DRAFT_v5_lumos_activity_OR_platemap_review.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_manifest_design_20260708_no_submit/recordings_manifest_nonlfp_th5_DRAFT_v5_lumos_activity_OR_platemap_submit_false.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_manifest_design_20260708_no_submit/summary_v5_lumos_activity_OR_platemap_review.json
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_manifest_design_20260708_no_submit/v5_lumos_OR_policy_command.txt
```

Counts remain unchanged from v4 because the 6/22 Lumos activity-sidecar wells
match the decoded `.platemap` wells exactly:

```text
candidate raw rows: 57
expected per-well jobs: 454

CytoView 6-well:
  rows: 33
  well jobs: 198
  selection mode: manual_all_wells_sixwell_policy

Lumos 48-well:
  rows: 24
  well jobs: 256
  selection mode: manual_lumos_activity_OR_platemap
```

Lumos source behavior in v5:

```text
2/25 Lumos:
  activity sidecar only
  2 rows x 14 wells = 28 jobs

6/18 Lumos:
  decoded .platemap only
  10 rows x 12 wells = 120 jobs

6/22 Lumos:
  activity sidecar + decoded .platemap
  both sources give A3,B4,B5,C3,C5,C6,D2,D6,E5
  12 rows x 9 wells = 108 jobs
```

Preflight for v5:

```text
submit=false rows: 57
blank params_template rows: 0
missing raw/plate-map/electrode-geometry/params/raw-metadata paths: 0
existing results/aind recording_stem collisions: 0
```

Use the v5 recordings manifest, not v4, for the next reviewed Step 1 submission
copy.

## 2026-07-08 Step 1 TH=5 v5 Submission Launched

The reviewed v5 Step 1 rerun was submitted from a timestamped submission package:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_submit_20260708_221826
```

Submission manifest:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_submit_20260708_221826/recordings_manifest_nonlfp_th5_v5_SUBMIT_TRUE.csv
```

Saved command files:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_submit_20260708_221826/01_generate_recording_batch_plan_command.sh
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_submit_20260708_221826/02_prepare_all_recordings_command.sh
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_submit_20260708_221826/03_submit_all_recordings_command.sh
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_submit_20260708_221826/04_supervise_all_recordings_command.sh
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_submit_20260708_221826/05_summarize_live_status_command.sh
```

Launch summary:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_submit_20260708_221826/submission_launch_summary.json
```

Submitted workload:

```text
recording rows prepared: 57
well chains submitted: 454
pipeline Slurm jobs submitted: 1816
pipeline job ID range: 53132868-53134685
recording supervisor jobs submitted: 57
supervisor job ID range: 53134690-53134747
```

Submission ledgers:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_submit_20260708_221826/recording_batch_plan/submitted_recording_batches.tsv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_submit_20260708_221826/recording_batch_plan/submitted_recording_supervisors.tsv
```

Initial scoped live-status snapshot:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_submit_20260708_221826/live_status/workflow_status_latest.json
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_submit_20260708_221826/live_status/workflow_status_latest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_submit_20260708_221826/live_status/workflow_status_latest.txt
```

During preparation, the first attempt failed before any Slurm submission because
`scripts/prepare_aind_well_batch.py` locked `params_template` to the plate-profile
default params and refused the explicit TH=5/preprocessing params from the
manifest. The script was patched so plate map and electrode geometry remain
metadata-locked, but an explicit manifest `params_template` is allowed if the
file exists. Preparation was rerun successfully after that patch, then the
Step 1 jobs and supervisors were submitted.

Important params used by the prepared well manifests:

```text
config/aind_axion_lumos_params_th5_kilosort_preproc_DRAFT.json
config/aind_axion_cytoview6_params_th5_kilosort_preproc_DRAFT.json

Th_universal = 5
skip_kilosort_preprocessing = false
```

### Live Status at 2026-07-08 23:04 EDT

This snapshot was taken after the Step 1 TH=5 v5 submission had begun moving
through Slurm but before any well had entered AIND preprocessing.

Overall submitted workload remains:

```text
well chains submitted: 454
top-level Slurm IDs tracked, including supervisors: 1873
```

Current Step 1 stage position:

```text
Nextflow traces present: 245 wells
Nextflow traces header-only: 245 wells
No Nextflow trace yet: 209 wells

job_dispatch completed: 0 wells
preprocessing submitted: 0 wells
nwb_ecephys submitted: 0 wells
spikesort_kilosort4 submitted: 0 wells
nwb_units completed: 0 wells
```

Interpretation:

```text
axion-aind-nwb wrapper jobs are running and have launched Nextflow.
Nextflow has submitted its first child process, job_dispatch.
The inner job_dispatch tasks are pending in Slurm with Reason=Priority.
Because job_dispatch has not run, preprocessing has not yet been submitted.
This is not a Kilosort preprocessing failure; the workflow has not reached the
Kilosort code path yet.
```

Representative inner child-job evidence:

```text
outer wrapper:
  axion-aind-nwb 53132959 RUNNING
inner first Nextflow task:
  nf-job_dispatch 53134864 PENDING
  Reason=Priority
  Dependency=(null)

outer wrapper:
  axion-aind-nwb 53132983 RUNNING
inner first Nextflow task:
  nf-job_dispatch 53134870 PENDING
  Reason=Priority
  Dependency=(null)
```

Queue summary at this snapshot:

```text
245 nf-job_dispatch jobs pending by Priority
201 axion-aind-nwb jobs pending by Dependency
196 axion-export-nwb jobs pending by Dependency
196 axion-aind-si-prep jobs pending by Dependency
186 axion-export-well jobs pending by Priority
57 axion-aind-supervisor jobs pending by Priority
```

Eight well chains had failed at the export stage by this snapshot. These are not
Kilosort failures. They are MATLAB/Axion export failures where the requested
well contains channels/electrodes that are not recorded in the raw file.

Failed well chains:

```text
recording:
  step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_6_18_2026_plate2_129-8445_129-8445_ventral_sosrs_2_opsin(000)_primary_Neural_Broadband_hp_0.1_Hz_IIR_lp_None
failed wells:
  B6, C7, D7, E6

recording:
  step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_6_18_2026_plate2_129-8445_129-8445_ventral_sosrs_2_opsin(000)_filter_200Hz-3kHz
failed wells:
  B6, C7, D7, E6
```

Representative export error:

```text
Loaded .../6_18_2026_plate2/129-8445/129-8445/ventral_sosrs_2_opsin(000).raw,
well B6, dataset RawVoltageData, time range all time

Error using export_axion_well_kilosort_binary (line 116)
Missing waveform for B6_11 at Axion index {2,6,1,1}.
```

The same missing-waveform pattern was observed for C7, D7, and E6, and for the
corresponding `Filter(200Hz-3kHz)` raw variant. The manifest selected these
wells from the decoded Lumos `.platemap` only:

```text
wells selected for the affected 6/18 opsin(000) rows:
  B2,B4,B5,B6,C6,C7,D2,D6,D7,E2,E5,E6
activity_sidecar_wells:
  blank
well_selection_policy:
  lumos_activity_OR_platemap_union
```

Operational implication:

```text
The unaffected well chains should continue. The affected wells should not be
counted as Kilosort/preprocessing failures. They are evidence that for this
recording the decoded plate-map active-well list included wells that the raw
file did not actually record. Any targeted recovery should resubmit only the
valid recorded wells for these two recording variants, not rerun the full 454
well manifest.
```

### Recovery Action at 2026-07-08 23:49 EDT

The initial TH=5 Step 1 submission over-launched the AIND wrapper layer. At the
time of recovery, many `axion-aind-nwb` wrappers were occupying cluster
resources while their inner Nextflow `nf-job_dispatch` children were still
pending. No wells had reached AIND preprocessing, `nwb_ecephys`,
`spikesort_kilosort4`, or `nwb_units`.

To avoid wasting allocation time, the stuck AIND layer was cancelled while
preserving completed upstream products.

Cancelled job set:

```text
top-level AIND/supervisor Slurm IDs cancelled: 511
inner nf-job_dispatch Slurm IDs cancelled: 250
total unique Slurm IDs cancelled: 761
```

Recovery package:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_lumos_aind_continue_20260708_234646
```

Recovery audit files:

```text
cancel_stuck_aind_and_inner_job_ids.txt
cancel_stuck_aind_and_inner_command.sh
recovery_context.json
lumos_ready_aind_continuation_manifest.csv
submit_next_lumos_aind_wave.py
submitted_lumos_aind_wave.tsv
```

Original-run reconciliation files were added so the first TH=5 submission does
not get lost while continuing in smaller waves:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_lumos_aind_continue_20260708_234646/reconciliation/step1_th5_v5_reconciliation_summary.txt
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_lumos_aind_continue_20260708_234646/reconciliation/step1_th5_v5_original_well_reconciliation.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_lumos_aind_continue_20260708_234646/reconciliation/step1_th5_v5_original_supervisor_reconciliation.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_lumos_aind_continue_20260708_234646/reconciliation/step1_th5_v5_original_aind_asset_audit.csv
```

Current reconciliation counts:

```text
original well chains: 454
original recording supervisors: 57
original per-well Slurm jobs, export + NWB + SI-prep + AIND: 1816
original AIND jobs cancelled: 454
original supervisors cancelled: 57
Lumos continuation-ready wells: 106
Lumos recovery wave submitted wells: 20
total cancelled IDs recorded, including inner nf-job_dispatch IDs: 761
```

Asset audit for the 454 original AIND wrapper jobs:

```text
original AIND wrapper jobs: 454
result directories created: 250
original wrapper log files created: 250
Nextflow traces missing: 204
Nextflow traces header-only: 250
Nextflow traces with task rows: 0

actual AIND pipeline assets produced: 0
final/sorting-like assets produced: 0
preprocessed dirs: 0
spikesorted dirs: 0
postprocessed dirs: 0
curated dirs: 0
nwb dirs: 0
quality_control dirs/files: 0
visualization dirs/files: 0
metadata JSON assets: 0
```

For this audit, wrapper logs, empty/header-only Nextflow traces, and
`nextflow/` orchestration files are not counted as AIND assets. The upstream
export, export-to-NWB, and SpikeInterface-prep products are tracked separately
from AIND assets.

The continuation manifest contains only Lumos wells whose export,
export-to-NWB, and SpikeInterface-prep products were already present:

```text
ready Lumos well chains: 106
ready Lumos recording variants: 10
missing continuation env files: 0
```

These continuation jobs use the existing per-well environment files:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/<recording>/<well>/spikeinterface/run_aind_spikeinterface.env
```

Those env files include:

```text
AIND_ALLOW_OVERWRITE="true"
```

This is intentional because the cancelled wrapper attempts left top-level
`run_aind_nwb_well_<jobid>.log` files in some result directories.

The first controlled Lumos continuation wave was submitted with 20
`axion-aind-nwb` jobs:

```text
submitted jobs: 53136425-53136444
submission ledger:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_lumos_aind_continue_20260708_234646/submitted_lumos_aind_wave.tsv
```

At the immediate post-submit checkpoint, all 20 were pending by Slurm priority:

```text
20 axion-aind-nwb jobs pending, Reason=Priority
0 continuation AIND jobs running yet
```

Operational rule for the next step:

```text
Do not submit the remaining Lumos continuation waves until this first 20-job
wave demonstrates that inner Nextflow job_dispatch and preprocessing can begin.
If the first wave starts cleanly, submit the remaining Lumos continuation jobs
in controlled waves from the same recovery package rather than relaunching the
full 454-well manifest.
```

### Required Future Step 1 Submission Logic

The 2026-07-08 TH=5 run failed operationally because too many AIND wrapper jobs
were launched before the cluster had enough room for the inner Nextflow tasks.
The wrapper jobs occupied allocation while `nf-job_dispatch` remained pending,
so the run had a large Slurm footprint without producing AIND assets.

Future Step 1 submissions must treat AIND/Kilosort as a downstream continuation
from a verified pickup boundary, not as something blindly launched for every
manifest row at the same time.

Required per-well gate before submitting `axion-aind-nwb`:

```text
1. Binary export exists:
   data/interim/kilosort_binary/<recording>/<well>/*.bin

2. Interim NWB exists:
   data/interim/nwb/<recording>/<well>/*.nwb

3. AIND SpikeInterface-prep env exists:
   jobs/aind/<recording>/<well>/spikeinterface/run_aind_spikeinterface.env

4. AIND SpikeInterface params exist:
   jobs/aind/<recording>/<well>/spikeinterface/*_aind_spikeinterface_params.json
```

Only wells passing all four checks are eligible for AIND/Kilosort submission.
Wells that have not passed this boundary should remain in the upstream
export/NWB/SI-prep queue, not be submitted to AIND yet.

Current boundary audit at 2026-07-09 00:00 EDT:

```text
original well chains: 454
pickup-ready for AIND/Kilosort: 363
not pickup-ready: 91

not pickup-ready breakdown:
  no export/NWB/SI-prep assets yet: 82
  binary export exists but interim NWB/SI-prep not complete yet: 9
```

Live boundary update at 2026-07-09 00:03 EDT:

```text
original well chains: 454
pickup-ready for AIND/Kilosort: 410
not pickup-ready: 44

not pickup-ready breakdown:
  no export/NWB/SI-prep assets yet: 26
  binary export exists but interim NWB/SI-prep not complete yet: 18

submitted controlled AIND continuation wave: 20 jobs
controlled AIND continuation wave state: 20 pending by Slurm priority
controlled AIND continuation Nextflow traces: 20 header-only
controlled AIND continuation task rows: 0
```

The 204 original AIND jobs that never created a Nextflow trace should not be
treated as lost biological outputs. They did not produce AIND assets, but they
can still be advanced once their wells pass the pickup boundary above. The
target remains to account for all 454 original well chains, with invalid export
failures tracked explicitly rather than silently retried forever.

Future operational policy:

```text
1. Submit export, export-to-NWB, and SI-prep stages first.
2. Build an AIND continuation manifest only from wells passing the four pickup
   checks above.
3. Submit AIND/Kilosort in controlled waves, not all ready wells at once.
4. After each wave starts, confirm that inner Nextflow job_dispatch and
   preprocessing tasks actually begin.
5. Only then submit the next wave.
6. Keep a reconciliation table linking original export/NWB/SI/AIND job IDs to
   any continuation AIND job IDs.
```

This staged handoff is required for future large Step 1 reruns. It prevents
hundreds of idle AIND wrappers from occupying Slurm resources while their inner
Nextflow jobs wait in priority, and it preserves one auditable lineage from the
original manifest row to the final AIND/Kilosort result.
