# Kempner Workflow Adaptation Plan

Date: 2026-07-05

Reference evaluated:

- `KempnerInstitute/ephys-spike-sorting`
- inspected commit `15f4f4b388f9864fb6762b8ada3af209b576ec21`

## Decision

Do not vendor the full Kempner repository inside this repository.

Use it as an external workflow reference and adapt the small parts that match
our Great Lakes Axion use case:

- Slurm/Nextflow orchestration pattern
- per-recording or per-well job fan-out
- explicit data/work/results paths
- container-aware execution model, if Great Lakes container setup becomes
  easier than the current Turbo conda environment
- post-sort result layout ideas: `preprocessed/`, `spikesorted/`,
  `postprocessed/`, `curated/`, and visualization outputs

The current Axion pipeline should keep ownership of Axion-specific work:

- Axion `.raw` metadata interpretation
- stimulated-well and waveform-program parsing
- plate maps and per-well electrode geometry
- optogenetic response tables and figures
- conversion from Axion continuous traces into the binary/probe pair that
  Kilosort needs

## Why Not Copy The Whole Repo

The Kempner project is primarily a Neuropixels/SpikeGLX-oriented wrapper around
the Allen Institute AIND ephys capsules. Its README says the workflow can handle
`aind`, `nwb`, `openephys`, and `SpikeGLX`, and the guide focuses on SpikeGLX.
It expects data folders that already contain continuous recording binaries plus
metadata, for example a `.bin`/`.meta` pair.

Our handoff identifies a different current boundary: Kilosort4 needs a
continuous row-major binary trace and probe geometry, but the existing Axion
pipeline mostly starts from Axion spike-list CSVs, `.spk` snippets, and `.raw`
stimulation metadata. Those files are valuable downstream products, but they do
not replace the continuous trace export.

Copying the whole Kempner repo would add:

- cluster-specific Harvard/Kempner paths,
- Nextflow plus Singularity assumptions,
- Allen AIND capsule dependencies,
- Neuropixels-oriented preprocessing defaults,
- files for Kilosort2.5, SpykingCircus2, NWB packaging, and Figurl that are not
  yet Axion-specific.

That would make the project larger before it solves the missing Axion conversion
step.

## Recommended Path

### Phase 1: Keep The Current Minimal Kilosort Path

Finish the direct Axion well-level path already scaffolded here:

1. Confirm continuous-trace export from Axion `.raw` for one well.
2. Write one row-major binary under:

   ```text
   ${PROJECT_ROOT}/data/interim/kilosort_binary/<recording_stem>/<well>.bin
   ```

3. Use the existing `run_axion_kilosort.py` readiness path with
   `RUN_KILOSORT=false`.
4. Only then run `RUN_KILOSORT=true` on one real well.

This is the shortest route to a real Axion Kilosort result.

### Phase 2: Add Pair-File Batch Submission

Once a real one-well binary works, add a small Axion-native batch layer instead
of importing Kempner wholesale:

- `metadata/kilosort_well_runs.csv`
- `scripts/submit_kilosort_well_batch.sh`

The CSV should be the run table and include one row per well:

```text
recording_stem,well,binary_file,plate_map,electrode_geometry,output_dir,fs,dtype,n_chan_bin,run_kilosort
```

The script should read that table, create one `.env` file per row under
`${PROJECT_ROOT}/jobs/`, and submit `slurm/run_kilosort_well.sbatch` for each
row. This captures the useful Kempner idea of multi-job fan-out without forcing
the whole project into Nextflow yet.

### Phase 3: Decide Whether Nextflow Is Worth It

Only add a Nextflow workflow after the direct Slurm path has real results and we
know we need more orchestration. The first Nextflow version should be
Axion-specific and small:

- one process to validate binary/probe readiness,
- one GPU process to run Kilosort4,
- one CPU process to collect/copy manifests and results.

Do not include AIND preprocessing, NWB export, unit classification, or Figurl
until there is an Axion-specific reason.

## Keep The Kempner Repo Separate

Recommended local practice:

```bash
mkdir -p /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/references
cd /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/references
git clone https://github.com/KempnerInstitute/ephys-spike-sorting.git
```

If we later need a reproducible snapshot, record the upstream commit hash in a
manifest. Avoid committing the cloned repository into this repo. If we need to
track it directly, prefer a git submodule over a plain copied folder, but only
after we decide we truly depend on its files.

## Immediate Next Step

Build the two-file Axion batch layer after the first real per-well continuous
binary is available:

- `metadata/kilosort_well_runs.csv`
- `scripts/submit_kilosort_well_batch.sh`

Before that, the critical missing piece remains the Axion continuous-trace
exporter. The batch layer can submit jobs, but it cannot create valid Kilosort
input without those binaries.
