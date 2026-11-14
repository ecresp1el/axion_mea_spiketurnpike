> October 24, 2026 review: both selective retries subsequently completed and
> passed independent validation. The unique-recording total is now 10 technically
> validated, 13 unresolved, 92 canceled before execution, and 3 unavailable.
> See [the failure review and workflow update](/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/handoffs/MCS_FAILURE_REVIEW_20261024.md).
> The checkpoint below remains a historical September 17 snapshot.

# MCS stale batch canceled; selective retries running

Current checkpoint: 2026-09-17 21:31 UTC. The 92 unstarted main-array tasks
and their old collector were canceled at 21:25 UTC; none remain queued. The two selective retries were
submitted at 21:20:37 UTC. The isolated fallback passed independent validation
at 21:19 UTC. Retry `61347622_1` completed and validated at 21:30 UTC;
retry `61347622_0` is still running. The user explicitly confirmed that the
remaining 92 recordings are to be launched after validating recovery handling.
The main-batch accounting snapshot below is from 21:08 UTC and preserves
its original failed attempts.

## Current decision

The user requested review of prior Axion template-initialization failures,
then authorized one quick, full-AIND MCS test of the previously demonstrated
selective fallback. After sorting succeeded, the user asked to prepare and
launch the remaining appropriate retries without introducing artifacts.

The active session asked about follow-up scope; no explicit answer expanding
the scope arrived. The user's direct retry request was therefore implemented
narrowly: only the two other historically eligible failed recordings, main
tasks 2 and 11, after the isolated test's independent validation passed.
Those two retries were submitted as array `61347622`; one is now complete
and one remains running.
The 92 unstarted main tasks and old collector `61332896` are now canceled,
not held. The two active retries and their collector `61347623` were not
canceled. The 13 zero/one-snippet failures remain outside the proven fallback.
No replacement for the 92 unprocessed recordings has been submitted, and no
global sorting-parameter change has been applied.

### Required next launch

The user explicitly requested that the handoff commit to launching the rest.
The remaining 92 recordings are deferred, not abandoned. After checking the
active retry outcomes and implementing/testing selective recovery handling,
launch these 92 recordings as a new tracked Slurm batch. This is the agreed
next execution step, not an indefinite hold or a requirement to ask again
whether those recordings should be processed.

Use the established standard profile first and apply the separately labeled
2/2/2 fallback only to eligible initialization failures. Preserve each attempt,
source/channel/event metadata, validation results, and quality warnings.
Exclude already completed recordings from the replacement submission and
verify the exact 92-recording scope against canceled main tasks 23-114.
Keep the 13 zero/one-snippet failures in a separate unresolved worklist for
investigation; do not silently discard them or apply an unvalidated remedy.
No replacement batch has been launched yet.

After the user challenged why stale submissions remained queued, the session
verified all 92 tasks were still pending and canceled only `61332895_[23-114]`
and waiting collector `61332896`. `sacct --array` confirms 92 cancellations;
`squeue` confirms the old submissions are absent. No data or outputs were deleted.
Evidence: `jobs/aind_mcs_batch_th5_20260917_195003/cancellation_review_20260917_212500.json`.
Before restarting the remaining archive, implement
and validate a gated standard-profile workflow with separately labeled 2/2/2
retries only for eligible initialization failures; zero/one-snippet failures need
separate investigation. That broader workflow is not yet implemented or submitted.
The successful selective test does not justify applying 2/2/2 to every recording.

The authorized test is main-batch task 12:

```text
Actuators & Effectors/Stim 2/353.1/2021-07-05T10-31-31McsRecording
```

It has 119.8 seconds at 10 kHz, 60 channels, acquisition-verified 100 um
geometry, and a standard-run failure with five template-training snippets.
Change only these three Kilosort settings together:

```json
{"n_templates": 2, "nearest_templates": 2, "n_pcs": 2}
```

Retain the MCS TH5 profile and all other recording-specific parameters,
including Th_universal=5, Th_learned=8, Th_single_ch=6, nskip=25,
batch_size=15000, templates_from_data=true, CAR off, no sign inversion,
Kilosort preprocessing on, no motion correction, int32 outer preprocessing,
and the source-verified channel mapping and calibration. The test must use
a separate run/results location and preserve the failed standard run.
H5 cleanup is disabled for this fallback test.

The selected recording uses the verified original MSRD plus acquisition XML.
The alternate H5 under
`/nfs/turbo/umms-parent/mea_multichannel_project/raw_data/chemogenetic_project/Actuators & Effectors/Stim 2/353.1/2021-07-05T10-31-31McsRecording.h5`
was rejected because its hardware events differ from the staged metadata.
It is not an approved replacement input or cleanup target and must remain.

## Main batch at the checkpoint

Main Slurm array: `61332895`, tasks `0-114`, concurrency 2.
Dependent final collection job: `61332896`, dependency
`afterany:61332895`. That old collection job was canceled at 21:25 UTC.

At 20:40 UTC, pending tasks `23-114` were held with `JobHeldUser`.
Tasks 21 and 22 were already running and were allowed to finish.
At 21:08 UTC, no main-array tasks were active.

The ledger at `2026-09-17T21:08:01.499424+00:00` records:

| State | Count |
| --- | ---: |
| Completed and validated | 7 |
| Failed | 16 |
| Submitted, held at the historical 21:08 checkpoint | 92 |
| Blocked/unavailable source rows | 3 |
| Inventory rows | 118 |
| Runnable array tasks, including completed canary reuse | 115 |

Current unique-recording view at 21:31 UTC, combining the preserved main
ledger with the separate fallback and retry records:

| State | Unique recordings |
| --- | ---: |
| Validated: 7 standard plus 2 fallback rescues | 9 |
| Selective retry running, not yet validated | 1 |
| Zero/one-snippet failures awaiting a different investigation | 13 |
| Unprocessed; stale jobs canceled before execution | 92 |
| Unavailable sources | 3 |
| Total inventory | 118 |

The baseline ledger's historical 16 failures remain unchanged. This combined
view tracks recordings across attempts and must not be added to those baseline
counts. The retry summary confirms one completed task, one running task, and
zero deleted bytes.

Three selected H5 files were deleted only after the batch's successful-output
and full-sample preservation checks. Confirmed reclaimed space:
`1,565,606,997 bytes` (1.565606997 GB decimal). Original MSRD files, retained
int32 binaries, failed-input data, and successful sorting outputs remain.
The user had authorized conditional H5 deletion for the main batch; external
backups were reported by the user but not independently verified.
This fallback test has cleanup disabled.

The main ledger was refreshed at 21:25:59 UTC: 92 `cancelled`, 7 `completed`,
16 `failed`, and 3 `blocked`. Explicit per-recording cancellation records mark
`cancelled_before_execution`; these are not processing failures. Frozen code
is unchanged. For this ended batch, refresh without `--scheduler`: that older
reconciliation code conflates canceled jobs with failures and does not expand
compressed array accounting. Use `sacct --array` separately for scheduler proof.

## Exact roots and evidence

Repository:

```text
/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
```

Great Lakes project root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder
```

Paths below are relative to the Great Lakes project root:

```text
jobs/aind_mcs_batch_th5_20260917_195003/
jobs/aind_mcs_batch_th5_20260917_195003/batch_manifest.json
jobs/aind_mcs_batch_th5_20260917_195003/submission.json
jobs/aind_mcs_batch_th5_20260917_195003/recordings.csv
jobs/aind_mcs_batch_th5_20260917_195003/summary.json
jobs/aind_mcs_batch_th5_20260917_195003/hold_review_20260917.json
jobs/aind_mcs_batch_th5_20260917_195003/status/
jobs/aind_mcs_batch_th5_20260917_195003/logs/
jobs/aind_mcs_batch_th5_20260917_195003/code/
jobs/aind_mcs_batch_th5_20260917_195003/code_sha256.json
metadata/mcs_batch_sources_20260917_with_recovery/mcs_batch_source_index.json
data/interim/mcs_sorting_inputs/
data/interim/aind_mcs_inputs/
results/aind_mcs/
scratch/aind_mcs_nextflow/
```

Selected-recording staged input:

```text
data/interim/mcs_sorting_inputs/Actuators & Effectors/Stim 2/353.1/2021-07-05T10-31-31McsRecording/
```

Selected-recording standard input and failed output:

```text
data/interim/aind_mcs_inputs/Actuators_Effectors/Stim_2/353.1/2021-07-05T10-31-31McsRecording/th5_batch_20260917_195003/
results/aind_mcs/Actuators_Effectors/Stim_2/353.1/2021-07-05T10-31-31McsRecording/th5_batch_20260917_195003/
```

Raw acquisition sources are under:

```text
/nfs/turbo/umms-parent/mea_multichannel_project/raw_data/
```

The original batch executes its frozen `code/` snapshot, not whatever
subsequently changes in the working repository. Preserve that snapshot and
all original parameters. Relevant repository entry points are:

```text
scripts/run_mcs_aind_batch.py
scripts/prepare_mcs_aind_recording.py
scripts/validate_mcs_aind_output.py
scripts/finalize_mcs_aind_recording.py
scripts/finalize_mcs_aind_nwb.py
scripts/cleanup_mcs_h5.py
slurm/run_mcs_aind_batch.sbatch
slurm/run_aind_nwb_well.sbatch
config/aind_axion_cytoview6_params_th5_kilosort_preproc_DRAFT.json
```

## Why this fallback is selective

The historical Axion fix is in
`docs/KEMPNER_WORKFLOW_ADAPTATION_PLAN.md`:

- Lines 2405-2468: reducing template count without reducing PCA components
  failed; the corrected fallback couples all three settings to 2.
- Lines 2531-2577: B6, C7, and F6 completed on July 6 with 14, 32, and 17
  units respectively.
- Lines 4954-4972: the proven fallback requires at least two training snippets;
  it does not establish a fix for zero or one snippet.
- Lines 6405-6422: preserve standard settings and use a separately labeled
  fallback.
- Lines 7041-7048: the later July 9 TH5 continuation documented sparse failures
  and deferred fallback execution because of time.

Actual saved proof, relative to the project root:

```text
results/aind_low_activity_ks4_nt2_npcs2/test_2_25_2026_129-8447_test(000)_full_lumos_settings/B6/processing.json
results/aind_low_activity_ks4_nt2_npcs2/test_2_25_2026_129-8447_test(000)_full_lumos_settings/B6/nextflow/trace.txt
results/aind_low_activity_ks4_nt2_npcs2/test_2_25_2026_129-8447_test(000)_full_lumos_settings/C7/nextflow/trace.txt
results/aind_low_activity_ks4_nt2_npcs2/test_2_25_2026_129-8447_test(000)_full_lumos_settings/F6/nextflow/trace.txt
jobs/aind_fallbacks/test_2_25_2026_129-8447_test(000)_full_lumos_settings/low_activity_ks4_nt2_npcs2/
```

Those successful old fallback runs used TH9 and different preprocessing.
The current test copies only the coupled 2/2/2 fallback change onto the
adopted MCS TH5 configuration. It does not import the whole old configuration,
and success would not establish biological single-unit quality.

Current failures are classified in `hold_review_20260917.json`:

| Main task | Training snippets | Interpretation |
| --- | ---: | --- |
| 2 | 2 | Historical fallback candidate |
| 11 | 3 | Historical fallback candidate |
| 12 | 5 | Selected one-recording test |
| 5, 7 | 1 each | Outside the proven 2/2/2 rescue |
| 3, 4, 8, 9, 10, 13, 16, 17, 18, 19, 20 | 0 each | Empty PCA/SVD input; separate investigation |

Template-training snippet scarcity does not prove absence of neural activity.
The 13 zero/one-snippet failures must not be declared rescued or automatically
treated as eligible based on this one test. There is no documented adopted
zero-snippet remedy from the prior Axion outputs.

## Fallback launch status

Prepared isolated fallback batch:

```text
jobs/aind_mcs_fallback_nt2_npcs2_20260917_2108/
jobs/aind_mcs_fallback_nt2_npcs2_20260917_2108/fallback_test_context.json
jobs/aind_mcs_fallback_nt2_npcs2_20260917_2108/batch_manifest.json
jobs/aind_mcs_fallback_nt2_npcs2_20260917_2108/code/
```

Run ID: `th5_nt2_npcs2_test_20260917_2108`. Exact prepared input and
prospective results, relative to the project root:

```text
data/interim/aind_mcs_inputs/Actuators_Effectors/Stim_2/353.1/2021-07-05T10-31-31McsRecording/th5_nt2_npcs2_test_20260917_2108/
results/aind_mcs/Actuators_Effectors/Stim_2/353.1/2021-07-05T10-31-31McsRecording/th5_nt2_npcs2_test_20260917_2108/
```

The test code is frozen. Prepared parameters change only `n_templates: 6 -> 2`,
`n_pcs: 6 -> 2`, and `nearest_templates: 64 -> 2`. Both the batch and the
recording manifest disable source cleanup. The saved
`fallback_test_context.json` and recording-manifest decisions document
the difference from main task 12.

Submitted at **2026-09-17 21:10:38 UTC**:

- Isolated Slurm array: `61346385`, task `0` only.
- Dependent collection job: `61346386`.
- Submission record: `jobs/aind_mcs_fallback_nt2_npcs2_20260917_2108/submission.json`.
- Independent written-configuration preflight:
  `jobs/aind_mcs_fallback_nt2_npcs2_20260917_2108/fallback_test_preflight.json`.

Preflight passed: exactly the three intended sorter-setting changes;
preprocessing, postprocessing, continuous input reader, and calibration are
unchanged. Input: 60 channels, 10 kHz, 1,198,000 samples, 119.8 seconds,
100 um geometry, and one preserved event.

The main batch's 92 unstarted tasks were subsequently canceled. No additional
H5 deletion occurred during test preparation, submission, or cancellation.

Fallback result: **technically completed and independently validated**.
Validation passed at `2026-09-17T21:19:00.307217+00:00`; the worker recorded
completion at `2026-09-17T21:19:01.146638+00:00`. All 11 AIND stages
completed, durable-recording finalization and NWB correction passed, and
`validation_summary.json` records `status=passed`. Cleanup status is
`retained_rejected_h5`; this test deleted zero bytes.

Recorded `processing.json` confirms TH5 and all three coupled fallback
settings at 2. Saved sorter provenance confirms
**Kilosort 4.1.7**, not Kilosort 5:

```text
spikesorted/block0_None_recording1/spikeinterface_log.json
spikesorted/block0_None_recording1/provenance.json
curated/block0_None_recording1/si_folder.json
```

Observed outputs:

| Stage | Clusters | Spikes | Kilosort labels |
| --- | ---: | ---: | --- |
| Initial sorting | 24 | 63 | All MUA |
| After redundant-unit cleanup | 6 | 23 | All MUA |

The automatic curation log reports missing quality metrics and skipped
classification. A `curated/` directory therefore does not certify artifact-free
or manually accepted units. These sparse MUA clusters demonstrate that the
specific initialization failure was bypassed, not that the recording contains
six confirmed neurons or that artifacts are absent. Preserve original
cluster IDs, labels, spike counts, and the before/after cleanup distinction.

Independent numerical inspection confirmed every saved spike index is within
recording bounds, no duplicate `(unit, sample)` entries, finite waveform means
and standard deviations, and absolute waveform peaks from 24.57 to 90.22 uV.
These checks do not establish artifact-free units. Waveform, trace,
event-alignment, and unit-quality review remain necessary before scientific
interpretation. Do not lower detection thresholds, modify events, or label
these outputs artifact-free to make a retry appear successful. No duplicate
test should be launched.

## Two selective retries running

Submitted batch, relative to the project root:

```text
jobs/aind_mcs_fallback_nt2_npcs2_remaining_20260917_2119/
jobs/aind_mcs_fallback_nt2_npcs2_remaining_20260917_2119/batch_manifest.json
```

Run ID: `th5_nt2_npcs2_retry_20260917_2119`.

| Retry task | Original main task | Recording within Actuators & Effectors/Stim 2 | Geometry |
| --- | --- | --- | --- |
| 0 | 11 | 353.1/2021-07-05T10-29-33McsRecording | Source verified, 100 um, 60 channels |
| 1 | 2 | 353.3/2021-07-05T12-08-07McsRecording | Staged unverified, assumed 200 um, 60 channels |

Durations are 54.9 and 613 seconds respectively. Their standard runs had
three and two training snippets. The second recording retains the pre-existing
unverified computational geometry flag; retrying does not convert it to
source-verified geometry or establish spatial validity.

Input/output suffixes under `data/interim/aind_mcs_inputs/` and
`results/aind_mcs/`:

```text
Actuators_Effectors/Stim_2/353.1/2021-07-05T10-29-33McsRecording/th5_nt2_npcs2_retry_20260917_2119/
Actuators_Effectors/Stim_2/353.3/2021-07-05T12-08-07McsRecording/th5_nt2_npcs2_retry_20260917_2119/
```

Only the same three sorter settings change to 2. All other input,
calibration, preprocessing, postprocessing, events, and recording-specific
settings remain preserved. Both retries have cleanup disabled and use
separate result locations.

Submitted at `2026-09-17T21:20:37.575402+00:00`:

- Retry array: `61347622`, tasks `0-1%2`.
- Dependent collection job: `61347623`.
- Both tasks started; at 21:31 UTC task 1 is complete and task 0 is running.
- Preflight: `fallback_retry_preflight.json` in the retry batch directory.
- Independent verifier: `verify_retry_preflight.py` in the same directory.
- Submission evidence: `submission.json` in the same directory.

Preflight passed. Frozen executable code hashes match the canary snapshot
apart from saved Git-status provenance. Each recording's channels, events,
probe, and source sidecars match its baseline byte for byte. The only sorter
changes are the three intended 2/2/2 values; the probe path changes only to
reference the corresponding preserved map in the isolated run.

Retry task 1 (original main task 2) completed and validated at
`2026-09-17T21:30:26.214200+00:00`: 9 MUA-labeled clusters, 139 spikes,
zero bytes deleted. Its geometry remains explicitly unverified.
Retry task 0 (original main task 11) is still running, not yet validated.
No H5 files have been deleted by these retries or the completed fallback test. The 92 unstarted main
jobs and their old collector are canceled and no longer queued.

Accounting must preserve the original baseline ledger's 16 failed attempts.
Two unique recordings, original tasks 12 and 2, are confirmed technically
rescued so far. Do not count the remaining running retry as a rescue, or count repeated
attempts as separate recordings.

## Resume checks

Read the current state before taking any action. These commands inspect
scheduler and ledger files without resuming or cancelling jobs:

```bash
cd /home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
PROJECT=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder
BATCH="$PROJECT/jobs/aind_mcs_batch_th5_20260917_195003"
squeue -r -j 61332895,61332896 -o "%.20i %.12T %.12M %.60R"
sacct --array -j 61332895,61332896 --format=JobID,State,ExitCode,Elapsed -P
cat "$BATCH/summary.json"
cat "$BATCH/hold_review_20260917.json"
```

To regenerate the ended main batch's ledger from explicit recording statuses,
use its frozen script without scheduler reconciliation, preserving the
canceled-before-execution classification:

```bash
"$PROJECT/envs/axion-kilosort/bin/python" \
  "$BATCH/code/scripts/run_mcs_aind_batch.py" status \
  --batch-dir "$BATCH"
```

Inspect the isolated fallback without affecting the main array:

```bash
FALLBACK="$PROJECT/jobs/aind_mcs_fallback_nt2_npcs2_20260917_2108"
squeue -r -j 61346385,61346386 -o "%.20i %.12T %.12M %.60R"
sacct -j 61346385,61346386 --format=JobID,State,ExitCode,Elapsed -P
cat "$FALLBACK/fallback_test_preflight.json"
cat "$FALLBACK/summary.json"
"$PROJECT/envs/axion-kilosort/bin/python" \
  "$FALLBACK/code/scripts/run_mcs_aind_batch.py" status \
  --batch-dir "$FALLBACK" --scheduler
```

The isolated test has passed final validation. Preserve its
`nextflow/trace.txt`, `processing.json`, `validation_summary.json`,
durable-recording report, and NWB finalization report. Inspect cluster counts,
Kilosort labels, spike preservation, calibration, geometry, and events when
reviewing results. Keep the test distinct from its standard failed attempt
and retain H5 input.

Inspect the two running retries and refresh their reporting independently:

```bash
RETRIES="$PROJECT/jobs/aind_mcs_fallback_nt2_npcs2_remaining_20260917_2119"
squeue -r -j 61347622,61347623 -o "%.20i %.12T %.12M %.60R"
sacct -j 61347622,61347623 --format=JobID,State,ExitCode,Elapsed -P
cat "$RETRIES/fallback_retry_preflight.json"
cat "$RETRIES/summary.json"
"$PROJECT/envs/axion-kilosort/bin/python" \
  "$RETRIES/code/scripts/run_mcs_aind_batch.py" status \
  --batch-dir "$RETRIES" --scheduler
```

Do not launch duplicate retries. These two jobs cover only main tasks 2 and 11,
each in a separate TH5 2/2/2 run with all other recording-specific parameters
preserved and cleanup disabled. Do not submit replacements for the 92 canceled
jobs without validated recovery handling, retry the 13 zero/one-snippet failures
with an unproven remedy, or change thresholds globally.

For each retry, require successful AIND execution, durable recording, corrected
NWB, and independent `validation_summary.json` before marking that recording
technically rescued. Preserve failed outcomes and quality caveats explicitly.
The next continuation must report both retry results, validate the selective
recovery workflow, and submit the agreed new batch for the remaining 92
recordings. The original main array is ended; do not try to release or reuse
its canceled jobs. Record the replacement job IDs and per-recording ledger
here after actual submission.

## Companion documents

Repository documents:

```text
docs/MCS_BATCH_RUN_20260917.md
docs/MCS_SINGLE_RECORDING_RUN_20260917.md
docs/AXION_TO_MCS_WORKFLOW_MAP.md
docs/KEMPNER_WORKFLOW_ADAPTATION_PLAN.md
```

This handoff is mirrored at:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/handoffs/HANDOFF_MCS_BATCH_PAUSED_FALLBACK_20260917.md
```
