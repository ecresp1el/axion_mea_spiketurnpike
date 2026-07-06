# Kempner Workflow Handoff

Date: 2026-07-05

Reference evaluated:

- `KempnerInstitute/ephys-spike-sorting`
- inspected commit `15f4f4b388f9864fb6762b8ada3af209b576ec21`
- AIND job-dispatch capsule commit used by Kempner:
  `d6bdb9cc02d6711790a5c406cd50c1434074b5e2`

## Current Decision

Use Kempner/AIND as the downstream workflow that makes the final spike-sorting
output tree.

This repository owns only the Axion-specific preparation layer:

- read Axion `.raw` metadata and continuous traces,
- resolve the per-well 4x4 electrode geometry,
- export one well at a time to a valid NWB file,
- record Axion provenance and source metadata in the NWB/sibling manifests,
- submit that NWB file to the external Kempner Nextflow workflow.

The Kempner workflow owns the output structure after ingestion:

```text
results/kempner/<recording_stem>/<well>/
  curated/
  data_description.json
  nextflow/
  nwb/
  postprocessed/
  preprocessed/
  processing.json
  spikesorted/
  visualization_output.json
  repro/
```

Some folders depend on which Kempner/AIND steps complete and which run mode is
used, but those names and contents are produced by Kempner's
`results_collector`, not by our local Kilosort wrapper.

## Repository Boundary

Do not vendor the Kempner repository into this repository.

Keep it as a sibling checkout:

```bash
/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
/home/elcrespo/Desktop/githubprojects/ephys-spike-sorting
```

Our config points to that sibling checkout with:

```bash
KEMPNER_REPO_ROOT=/home/elcrespo/Desktop/githubprojects/ephys-spike-sorting
```

At run time, `slurm/run_kempner_nwb_well.sbatch` copies Kempner's
`pipeline/kempner_cluster` folder into the project job area and patches only the
cluster placeholders for Great Lakes. The upstream checkout stays unchanged.

## NWB Input Contract

Kempner calls the AIND job-dispatch capsule with:

```bash
--input nwb
```

The AIND capsule accepts exactly one `.nwb` file either directly in `DATA_PATH`
or inside one child folder. It then discovers acquisition `ElectricalSeries`
objects and keeps series sampled at 10 kHz or higher.

Our Axion NWB exporter writes a per-well acquisition `ElectricalSeries` at
12.5 kHz, so the current A1 full-length NWB is the correct handoff artifact:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/data/interim/nwb/test_2_25_2026_129-8447_test(000)_full_lumos_settings/A1/test_2_25_2026_129-8447_test(000)_full_lumos_settings_A1.nwb
```

## Great Lakes Launcher

The single-well Kempner run is configured by:

```text
config/example_kempner_nwb_well.env
```

and submitted with:

```bash
scripts/submit_kempner_nwb_well_job.sh config/example_kempner_nwb_well.env
```

The Slurm job:

1. creates a one-file NWB input folder under
   `${PROJECT_ROOT}/data/interim/kempner_nwb_inputs/<recording_stem>/<well>`,
2. copies Kempner's cluster pipeline into
   `${PROJECT_ROOT}/jobs/kempner/<recording_stem>/<well>/pipeline_kempner_cluster`,
3. patches `clusterOptions` for Great Lakes CPU/GPU partitions,
4. runs Kempner Nextflow with `--input nwb`, `--sorter kilosort4`, and the
   Axion/Lumos Kilosort4 parameter file,
5. writes final outputs under
   `${PROJECT_ROOT}/results/kempner/<recording_stem>/<well>`.

The exact launch command is stored in:

```text
results/kempner/<recording_stem>/<well>/repro/nextflow_command.sh
results/kempner/<recording_stem>/<well>/repro/submit_command.sh
```

The repro folder also stores copied configs, the input NWB path, patched job
script, and Kempner commit/status.

## Axion Kilosort4 Parameters

Kempner's Kilosort4 capsule accepts a custom JSON parameter file. For Axion
Lumos wells, use:

```text
config/kempner_kilosort4_axion_lumos_params.json
```

Key Axion-specific values:

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

This preserves the settings we validated locally, while allowing Kempner/AIND to
make the downstream folders.

## Setup Requirements

Nextflow and Singularity containers are external workflow requirements.

Install Nextflow into the project folder:

```bash
scripts/setup_kempner_nextflow.sh
```

Pull Kempner/AIND Singularity images into the project folder:

```bash
scripts/pull_kempner_singularity_containers.sh
```

These helpers use the Great Lakes modules configured in
`config/greatlakes_project.env`:

```text
openjdk/21.0.1
singularity/4.4.1
```

## Scaling Across Wells

For multiple wells on the same plate, repeat the same handoff per well:

```text
data/interim/nwb/<recording_stem>/<well>/<recording_stem>_<well>.nwb
results/kempner/<recording_stem>/<well>/
```

The geometry file does not change across wells:

```text
metadata/plate_maps/axion_per_well_4x4_electrode_geometry.csv
```

Only the selected source files, well label, and NWB path change. A later batch
submission layer can generate one `config/kempner_nwb_<well>.env` per row and
submit the same Kempner Slurm wrapper for each well.
