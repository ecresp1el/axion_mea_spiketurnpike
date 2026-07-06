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

## Next Conversation Starting Point

Start with the current AIND repo:

```bash
cd /home/elcrespo/Desktop/githubprojects
git clone https://github.com/AllenNeuralDynamics/aind-ephys-pipeline.git
```

Then inspect:

```text
aind-ephys-pipeline/pipeline/main_multi_backend.nf
aind-ephys-pipeline/pipeline/capsule_versions.env
aind-ephys-pipeline/params_app/
aind-ephys-pipeline/sample_dataset/
aind-ephys-pipeline/docs/
```

Questions to answer next:

1. Which current AIND input path is best for Axion: NWB, SpikeInterface, or AIND
   session folder?
2. Does current AIND job-dispatch still accept NWB `ElectricalSeries` directly,
   or should the Axion bridge write a SpikeInterface-compatible folder instead?
3. What parameter file/schema does current AIND use for Kilosort4 settings?
4. How should Great Lakes Slurm resources map onto current
   `main_multi_backend.nf`?
5. Which current GHCR container tags are required, and should they replace the
   older `si-0.101.2` Kempner images?

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
