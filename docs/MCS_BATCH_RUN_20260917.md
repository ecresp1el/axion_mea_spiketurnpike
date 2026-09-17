# MCS archive batch, 2026-09-17

Submitted at 19:54 UTC: Slurm array `61332895`, tasks `0-114`, concurrency 2.
The final scheduler/ledger collection job is `61332896` (`afterany:61332895`).
Run ID: `th5_batch_20260917_195003`. The full repository suite passed 99 tests.
Submission does not mean every recording has completed; consult the live ledger.

First verified batch outcome at 19:55:50 UTC: the existing 353.1 canary was
revalidated (44 units, 40,623 spikes) and its selected H5 was deleted after full
sample comparison, reclaiming 532,640,801 bytes. The original MSRD and retained
binary still exist. The per-result immutable deletion ledger records the proof.

Project-relative tracking paths:

```text
jobs/aind_mcs_batch_th5_20260917_195003/recordings.csv
jobs/aind_mcs_batch_th5_20260917_195003/summary.json
metadata/mcs_batch_sources_20260917_with_recovery/mcs_batch_source_index.json
```

## Scope and user decisions

Process every usable recording through the established Axion TH5 AIND route,
adapted to one physical MCS MEA per recording. Missing acquisition XML or
biological annotations must not, by themselves, exclude signal data. Keep
recording identity, channel order, calibration, reference exclusion and hardware
events separate from unconfirmed treatment or biological assignments.

The initial strict audit had 30 eligible recordings and 88 blocked rows. A
second inspection found intact signal binaries and essential sidecars for 84 of
those blocked rows. A further source inspection recovered a verified 105-second
common prefix from a truncated original. The revised target is **115 recording
attempts**, including reuse and revalidation of the completed 353.1 canary and
one explicitly labeled partial recording. Three source rows are header-only or
absent locally. Actual preparation and runtime outcomes are recorded
individually, not assumed successful from this inventory.

The user authorized deletion of selected local H5 files after successful output
validation and reported backups elsewhere. External backups have not been
independently inspected. This is not permission to remove original `.msrd`
files, retained recording binaries, rejected H5s, arbitrary duplicate files,
or failed/blocked recordings.

## Metadata and short recordings

Source-verified acquisition geometry takes precedence over previously staged
coordinates. The archive includes both 100 and 200 um pitch, and both 59 and 60
signal-channel maps. Channel count alone does not establish physical pitch.

Where the original acquisition metadata is unavailable, use the intact staged
channel map as explicitly **unverified computational geometry**. Preserve its
grid topology without inventing a configured array model or measured physical
spacing. Manifest and ledger flags distinguish this assumption from verified
geometry. NWB physical coordinates must not present assumed distances as
measurements. These runs retain any H5 inputs. Results using assumed geometry
are provisional for spatial interpretation; recovered acquisition geometry can
justify a new sorting run rather than silently relabeling existing clusters.

The recovered `353.1/2021-06-23T10-19-07McsRecording` contains only the complete
105-second common prefix, not the full acquisition. Original source hashing,
block links, channel identities, timing continuity and the truncated tail are
recorded separately. The original is retained; absent events in this prefix do
not establish that the experiment had no stimulation.

The seven recordings below the old 30-second preprocessing gate are attempted
with an explicit short-recording policy. The policy is recorded in each
manifest and effective parameter file: disable only that duration gate, and
reduce batch size from 15,000 to 6,500 samples for the 1.3-second recording so
Kilosort can estimate whitening from at least two processing batches. Other
recordings keep batch size 15,000. Detection thresholds, reference handling,
calibration and spike identity checks are not relaxed. Insufficient snippets,
no units, failed stages or corrupt outputs remain failures, with inputs retained.

## Batch execution and tracking

`scripts/run_mcs_aind_batch.py` prepares a frozen code snapshot and one saved
configuration per recording. A Slurm array runs at most two parent jobs at once;
each invokes the existing AIND Nextflow route with its CPU/GPU child jobs.
The existing successful canary is revalidated rather than sorted again.

The batch directory under `jobs/aind_mcs_batch_*/` contains:

- `batch_manifest.json`: recording identities, selected sources and policies.
- `source_index.json`: the complete audit, including unavailable sources.
- `code/` and `code_sha256.json`: exact batch code and configuration snapshot.
- `submission.json`: Slurm array and final ledger-collection job IDs.
- `status/`: atomic per-recording stage, validation and cleanup records.
- `recordings.csv`: a consolidated ledger, including blocked and failed rows.
- `summary.json`: counts and confirmed deleted H5 bytes.
- `logs/`: per-array-task stdout/stderr and final summary logs.

Each worker refreshes the ledger as it advances. A dependent `afterany` job
reconciles scheduler failures after the array finishes. For a fresh live view:

```bash
PROJECT=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder
"$PROJECT/envs/axion-kilosort/bin/python" scripts/run_mcs_aind_batch.py status \
  --batch-dir "$PROJECT/jobs/aind_mcs_batch_th5_20260917_195003" --scheduler
```

Outputs preserve the single-recording layout:

```text
data/interim/aind_mcs_inputs/<group>/<condition>/<recording>/<run>/
results/aind_mcs/<group>/<condition>/<recording>/<run>/
```

Each successful run retains SpikeInterface sorting, original cluster identities
and Kilosort labels, the calibrated sorting analyzer, durable recording, NWB,
channel/event sidecars, submitted parameters and validation reports. Technical
success does not establish single-neuron quality or manual curation. The
inherited AIND route removes temporary native Kilosort files after loading;
saved SpikeInterface outputs are the durable spike-sorting artifacts.

## H5 deletion gates

`scripts/cleanup_mcs_h5.py` defaults to dry-run. The worker requests `--apply`
only for an explicitly selected source-verified H5, after all 11 AIND stages,
durable-recording finalization, NWB correction and independent validation pass.

Cleanup revalidates outputs, checks complete retained-recording hashes, compares
every source signal sample against the retained int32 binary, and checks channel
order, gain, ADC offset, time intervals and events. Source paths must match the
exact recording identity inside the authorized raw-data directory. Alternate
local source collections require explicit source-selection evidence.

Before unlinking that one H5, the helper fsyncs immutable source metadata,
checksums and preparation evidence under `results/.../repro/h5_cleanup/`.
It then records deletion time and bytes. The batch ledger links this evidence.
Missing files without matching deletion proof are not treated as successful
cleanup. Existing canary provenance is preserved; new verification scripts are
stored in a separate batch-specific reproduction directory.

The actual canary dry-run passed a full-sample comparison before batch launch.
Its selected H5 was 532,640,801 bytes; source signal counts matched the retained
binary SHA256 `f4fc25f3072f8b5b8e431d40769e6f98faab05a82386343466b227b7e7fc0616`.
The dry-run itself deleted nothing. Consult the ledger for actual deletions.
