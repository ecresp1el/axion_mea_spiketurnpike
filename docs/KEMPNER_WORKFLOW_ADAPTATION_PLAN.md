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
timeout. The active blocker is that AIND's Nextflow processes clone capsule
repositories from GitHub at runtime, and Great Lakes compute-node/container
network access timed out. The next implementation step is to remove runtime
GitHub dependence from Slurm tasks, for example by pre-staging the pinned AIND
capsule repos locally and making AIND clone from local paths or `file://` URLs,
or by confirming a Great Lakes-supported proxy/network method for containerized
GitHub access.

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
runtime-clone issue is being fixed.

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
  `config/greatlakes_project.env`, packages the binary as a per-well NWB, and
  writes PyNWB/provenance outputs.
- `run_aind_nwb_well.sbatch`: loads OpenJDK and Singularity, stages the NWB as
  AIND input, runs current AIND `pipeline/main_multi_backend.nf`, and records
  the exact Nextflow command under the result `repro/` folder.

To submit all selected wells:

```bash
bash '/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/aind_batches/test_2_25_2026_129-8447_test(000)_full_lumos_settings/submit_all_wells.sh'
```

Important: do not submit the whole selected batch into AIND until the current
AIND runtime GitHub-clone issue is fixed. It is fine to use the first two jobs
to continue validating Axion export and NWB generation across selected wells.
For AIND itself, keep using a single well, currently A1, until `job_dispatch`
gets past local capsule staging.

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

Next technical step before another AIND retry:

1. Clone/stage the pinned capsule repos from
   `/home/elcrespo/Desktop/githubprojects/aind-ephys-pipeline/pipeline/capsule_versions.env`
   into a stable local/Turbo folder.
2. Add a `capsule_versions_custom.env` or local patch so
   `main_multi_backend.nf` clones those local repos instead of GitHub URLs at
   runtime.
3. Re-run only the A1 current-AIND smoke test.
4. After A1 passes `job_dispatch`, then scale the AIND job step to selected
   wells.

## Next Conversation Starting Point

Do not restart by asking whether AIND can use NWB, what the Kilosort4 parameter
mechanism is, or how Slurm resources map. Those questions are answered below.

Start here instead:

1. Implement local AIND capsule staging so Slurm tasks do not need outbound
   GitHub access from inside containers.
2. Re-run only the A1 current-AIND smoke test through `job_dispatch`.
3. If A1 passes job dispatch, continue through preprocessing and Kilosort4.
4. Only after one well completes, submit AIND for the selected wells prepared by
   `scripts/prepare_aind_well_batch.sh`.

Useful files to inspect first:

```text
/home/elcrespo/Desktop/githubprojects/aind-ephys-pipeline/pipeline/main_multi_backend.nf
/home/elcrespo/Desktop/githubprojects/aind-ephys-pipeline/pipeline/capsule_versions.env
/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/aind_nextflow_slurm_greatlakes.config
/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/slurm/run_aind_nwb_well.sbatch
```

The specific code path to address is the `clone_repo()` helper in
`main_multi_backend.nf`. It currently runs `git clone "${repo_url}"`
inside each AIND process. On Great Lakes this reached the container, then failed
while cloning `aind-ephys-job-dispatch` from GitHub. The next patch should make
those repo URLs local/staged for the pinned commits in `capsule_versions.env`.

## Current-AIND Questions Answered

Checked on `2026-07-06` against a fresh local clone of
`AllenNeuralDynamics/aind-ephys-pipeline` at:

```text
39b08d11c8c11f5b64078a9c2e789927518fccab
```

Answers:

1. Use the Axion per-well NWB as the first AIND input path.
   Current AIND docs list NWB as a supported input type, and the pinned
   `aind-ephys-job-dispatch` capsule accepts `--input nwb`. The job-dispatch
   code enumerates available NWB `ElectricalSeries` paths with
   `SpikeInterface` and reads acquisition series directly. The Axion NWB writer
   already creates an acquisition `ElectricalSeries` named
   `<WELL>_ElectricalSeries`, with 12.5 kHz sampling and electrode x/y
   locations. Therefore the first target should be direct NWB ingestion, not an
   AIND session folder. If this fails, the most likely reason is exact
   SpikeInterface probe/location interpretation, and the fallback is a
   SpikeInterface recording folder with an explicit `probe_paths` value.

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
x_centers = 4
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
- The Axion geometry file is stable across wells; only well label/source files
  change.

## Scaling Across Wells

Once one current-AIND run works, scale by generating one upstream-compatible
input directory per well:

```text
data/interim/nwb/<recording_stem>/<well>/<recording_stem>_<well>.nwb
```

or the equivalent current AIND-supported input folder.

Results should be separated by recording and well:

```text
results/aind/<recording_stem>/<well>/
```

or whatever current AIND's `RESULTS_PATH` convention requires.

The Axion geometry file remains:

```text
metadata/plate_maps/axion_per_well_4x4_electrode_geometry.csv
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
