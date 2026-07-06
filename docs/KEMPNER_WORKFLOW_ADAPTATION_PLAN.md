# Axion to AIND/Kempner Ephys Pipeline Handoff

Date updated: 2026-07-06

## Goal

Use the maintained Allen Neural Dynamics ephys pipeline and Kempner's cluster
adaptation instead of rebuilding spike sorting, postprocessing, curation,
visualization, result collection, or NWB-units export ourselves.

This repo should only own the Axion-specific bridge:

- read Axion `.raw`/continuous voltage data,
- resolve the Axion well and 4x4 electrode geometry,
- write one supported input artifact per well, preferably NWB or another input
  format accepted by the AIND pipeline,
- preserve Axion metadata/provenance,
- launch the upstream workflow so upstream code creates the output tree.

Once Axion data is presented in a supported format, downstream processing should
come from AIND/Kempner methods, not from new local reimplementations.

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
the AIND containers as `/usr/local/bin/python`, pointing to
`/opt/conda/bin/python`. This is needed because AIND capsule `run` scripts call
`python`, while the base image's dependency-complete interpreter lives under
`/opt/conda`.

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

Status checked `2026-07-06 12:25 EDT`: job `52984769` completed
`job_dispatch`, `nwb_ecephys`, and neutral `preprocessing`, but did not run
Kilosort4. The parent job waited at the Kilosort4 Singularity image pull:

```text
Pulling Singularity image docker://ghcr.io/allenneuraldynamics/aind-ephys-spikesort-kilosort4:si-0.104.8
```

The Kilosort4 cache target does not exist yet; only the lock file exists:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/containers/aind_ephys/.ghcr.io-allenneuraldynamics-aind-ephys-spikesort-kilosort4-si-0.104.8.img.lock
```

Therefore: AIND ingestion and neutral preprocessing work; Kilosort4 execution
has not yet been proven. The Kilosort4 image lock was stale, so `52984769` was
cancelled and the stale lock file was removed after confirming no process had it
open.

The current corrected smoke job is:

```text
52986225  axion-aind-nwb  RUNNING
```

Status checked `2026-07-06 12:30 EDT`: job `52986225` started on `gl3206`,
loaded the fully corrected params file, and completed `job_dispatch`,
`preprocessing`, and `nwb_ecephys`. The preprocessing capsule used only the
neutral `astype` step, with motion compute/apply disabled:

```text
CUSTOM_PREPROCESSING_PIPELINE: {'astype': {'dtype': 'int16'}}
COMPUTE_MOTION: False
APPLY_MOTION: False
Running custom preprocessing pipeline with steps: ['astype']
```

It is now waiting at the AIND Kilosort4 Singularity image pull:

```text
Pulling Singularity image docker://ghcr.io/allenneuraldynamics/aind-ephys-spikesort-kilosort4:si-0.104.8
```

Live process inspection on `gl3206` confirmed this is an active Nextflow
Singularity pull/conversion, not Kilosort execution:

```text
singularity pull --name ghcr.io-allenneuraldynamics-aind-ephys-spikesort-kilosort4-si-0.104.8.img.pulling... \
  docker://ghcr.io/allenneuraldynamics/aind-ephys-spikesort-kilosort4:si-0.104.8
```

Nextflow redirects the pull output to `/dev/null`, so the normal Singularity
progress output is hidden. `/proc/<singularity_pid>/io` showed read/write byte
counters increasing, so it is slow rather than fully dead. The cache is large:

```text
26G  ${PROJECT_ROOT}/scratch/aind_singularity_cache
9.0G ${PROJECT_ROOT}/containers/aind_ephys
```

No final Kilosort4 `.img` exists yet; only the lock exists in
`${PROJECT_ROOT}/containers/aind_ephys`. This means the current remaining
blocker is not the Axion data, metadata, well mapping, or neutral preprocessing
logic. It is the AIND/Nextflow/containerized Kilosort4 setup path: pulling and
assembling the AIND Kilosort4 container on shared storage. A separate
user-managed Kilosort install may still run on Great Lakes; that is a different
execution path from the AIND sorter capsule.

Do not interpret the current AIND blocker as "Kilosort cannot run on Great
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
```

Job `52987650` used visible logs but still used Turbo scratch for
`SINGULARITY_TMPDIR`. It ran for ~22 minutes without producing the final image,
so it was cancelled.

The pull script was then refactored to use node-local temp space by default:

```text
SINGULARITY_TMPDIR=/tmp/${USER}/aind_singularity_tmp_${SLURM_JOB_ID}
```

On `gl3206`, `/tmp` had ~270G free, which should be enough for the image
conversion. The script also now `cd`s to the AIND image directory before running
`singularity pull`, so the final `.img` is written in the path Nextflow expects.

Current node-local-temp pull job:

```text
52991272  aind-ks4-img  PENDING
```

Submitted with saved command:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/container_pulls/submit_pull_aind_kilosort4_container_command.sh
```

Logs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/aind/aind-ks4-img-52987650.out
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/aind/aind-ks4-img-52987650.err
```

As of `2026-07-06 13:19 EDT`, monitor `52991272`. It has not started yet.
When it starts, confirm the log reports node-local `/tmp` for
`SINGULARITY_TMPDIR`.

The previous visible pull reached:

```text
INFO:    Converting OCI blobs to SIF format
INFO:    Starting build...
INFO:    Fetching OCI image...
INFO:    Extracting OCI image...
```

The final target image is:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/containers/aind_ephys/ghcr.io-allenneuraldynamics-aind-ephys-spikesort-kilosort4-si-0.104.8.img
```

Do not resubmit AIND until that `.img` exists.

Corrected params for the filtered-input route:

```text
job_dispatch.spikeinterface_info.reader_kwargs.is_filtered = true
preprocessing.custom_preprocessing_pipeline = {"astype": {"dtype": "int16"}}
spikesorting.kilosort4.sorter.do_CAR = false
spikesorting.kilosort4.sorter.skip_kilosort_preprocessing = true
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

## How To Begin The Pipeline From Raw Data

This is the operational starting sequence. It is intentionally split into an
Axion ingestion stage and an AIND execution stage so we can keep making progress
on selection, provenance, binary export, and NWB writing even while the AIND
runtime is still being validated.

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

- Each well is treated as an independent 16-channel recording for export, NWB,
  and AIND sorting.
- Wells on the same plate type share the same 4x4 electrode geometry:
  `metadata/plate_maps/axion_per_well_4x4_electrode_geometry.csv`.
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
  --allow-aind-overwrite
```

Generated files:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/well_batch_manifest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/well_batch_manifest.json
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/submit_all_wells.sh
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/<well>/export_binary.env
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/<well>/export_nwb.env
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/<well>/run_aind.env
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/<recording_stem>/<well>/submit_commands.sh
```

For the 2026-02-25 test, this currently prepares 14 wells.

### Step 4: Slurm Jobs Used By The Pipeline

The batch submit scripts chain three jobs per selected well:

```text
slurm/export_axion_well_binary.sbatch
slurm/export_axion_well_nwb.sbatch
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
- `run_aind_nwb_well.sbatch`: loads OpenJDK and Singularity, stages the NWB as
  AIND input, runs current AIND `pipeline/main_multi_backend.nf`, and records
  the exact Nextflow command under the result `repro/` folder.

To submit all selected wells:

```bash
bash '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/submit_all_wells.sh'
```

Important: do not submit the whole selected batch into AIND until the A1 smoke
test completes Kilosort4 and downstream AIND outputs. The runtime GitHub-clone
issue is already handled by local capsule staging. It is fine to continue using
the first two jobs to validate binary export, canonical mapping, and NWB
generation across selected wells while the single-well AIND run finishes.

### Step 5: Single-Well Current-AIND Smoke Test

For the already exported A1 NWB, the exact submit command is saved here:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/submit_aind_nwb_well_command.sh
```

The overwrite retry command is saved here:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/submit_aind_nwb_well_retry_allow_overwrite_command.sh
```

Monitoring commands:

```bash
squeue -j <job_id> -o '%.18i %.9P %.32j %.2t %.12M %.12L %.6D %R'
sacct -j <job_id> --format=JobID,JobName%32,State,ExitCode,Elapsed,MaxRSS,NodeList -P
tail -f '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/run_aind_nwb_well_<job_id>.log'
tail -f '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/nextflow/trace.txt'
```

Next technical step:

1. Keep the corrected SpikeInterface binary + ProbeInterface input route running
   for A1.
2. Keep monitoring A1 retry job `52986225`.
3. If A1 completes Kilosort4 and downstream AIND outputs, generalize
   `scripts/prepare_aind_spikeinterface_well.py` into the selected-well batch
   preparation flow.
4. Regenerate the A1 NWB with the patched NWB writer before retesting direct NWB
   input.
5. After one well completes, scale the AIND job step to selected wells.

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
stale Kilosort4 image lock blocked the sorter image pull. Current corrected
filtered-input A1 smoke test:

```text
52986225  axion-aind-nwb  RUNNING
```

Monitor `52986225` next. It has completed `job_dispatch`, neutral
`preprocessing`, and `nwb_ecephys`, and is currently waiting at the AIND
Kilosort4 Singularity image pull. If the image pull continues to block, the next
debug target is the AIND sorter container/cache mechanism, not Axion ingestion
and not the user's separate working Kilosort install.

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

1. Check A1 corrected filtered-input SpikeInterface retry job `52986225`.
2. If A1 passes Kilosort4 and downstream AIND steps, generalize the
   SpikeInterface input generation across selected wells.
3. Only after one well completes, submit AIND for the selected wells prepared by
   `scripts/prepare_aind_well_batch.sh`.
4. Regenerate A1 NWB before retrying direct NWB input, because the existing A1
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

Do not launch the 14-well AIND batch until the active A1 smoke test confirms the
Kilosort4 step runs successfully.

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
