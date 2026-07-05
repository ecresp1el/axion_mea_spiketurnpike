# Great Lakes Kilosort Transition Handoff

Date: 2026-07-05

This handoff mirrors the working habits from `mge_organoid_pipeline`:

- code and Slurm templates live in the Git repo,
- large data, logs, generated job files, and Kilosort outputs live in Turbo,
- jobs source small `.env` files for project/sample configuration,
- conda activation happens inside the Slurm script,
- every run writes a machine-readable manifest before heavy compute starts.

## Project Folder

Turbo project root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder
```

Expected layout:

```text
data/raw/                         # read-only Axion exports or links to source folders
data/interim/kilosort_binary/     # per-well continuous binaries for Kilosort
metadata/                         # copied run manifests or curated sample tables
results/kilosort/                 # Kilosort readiness manifests and results
logs/                             # Slurm stdout/stderr and tee logs
jobs/                             # copied sbatch files used for submission
scratch/                          # TMPDIR for jobs
handoffs/                         # run notes copied from repo docs as needed
```

Create it on Great Lakes:

```bash
cd /home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
bash scripts/create_greatlakes_project_folder.sh
```

## Environment

Conda file:

```text
envs/kilosort-greatlakes.yml
```

Create/update:

```bash
cd /home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
bash scripts/setup_kilosort_env.sh
conda activate /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/envs/axion-kilosort
python scripts/check_kilosort_env.py
```

Slurm GPU check:

```bash
mkdir -p /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs
sbatch slurm/check_kilosort_env.sbatch
```

## Plate Maps

Repo-controlled starting points:

```text
metadata/plate_maps/axion_48_well_opto_plate_map.csv
metadata/plate_maps/axion_24_well_plate_map.csv
metadata/plate_maps/axion_per_well_4x4_electrode_geometry.csv
```

The 48-well map is `A1:F8`. The 24-well map is `A1:D6`. Treatments are placeholders so they can be filled per experiment without changing code.

The default per-well geometry is a 4 x 4 grid with channel labels `11..44`. Edit this file if Axion exports or your MATLAB code confirm a different channel order or spacing.

## Kilosort Boundary

Kilosort4 needs a continuous row-major binary trace and a probe geometry. The existing Axion pipeline can parse spike-list CSVs, `.spk` waveform snippets, and stimulation metadata in `.raw`, but those are not enough by themselves for Kilosort sorting.

Current contract for real data:

1. Place or generate one continuous binary per well under:

   ```text
   ${PROJECT_ROOT}/data/interim/kilosort_binary/<recording_stem>/<well>.bin
   ```

2. Keep the original Axion export set under `data/raw/` or point `BINARY_FILE`/`RECORDING_STEM` to its source.

3. Run readiness first with `RUN_KILOSORT=false`.

4. Only after the manifest validates channel count, file size, plate map, and probe geometry, rerun with `RUN_KILOSORT=true`.

## One-Well Job

Copy and edit:

```bash
cp config/example_kilosort_well.env \
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/example_A1.env
```

Readiness-only submission:

```bash
SAMPLE_CONFIG=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/example_A1.env \
sbatch slurm/run_kilosort_well.sbatch
```

Or copy the sbatch template into the project folder and submit:

```bash
bash scripts/submit_kilosort_well_job.sh \
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/example_A1.env
```

Real Kilosort run:

```bash
RUN_KILOSORT=true \
SAMPLE_CONFIG=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/example_A1.env \
sbatch slurm/run_kilosort_well.sbatch
```

Outputs:

```text
results/kilosort/<recording_stem>/<well>/probe.json
results/kilosort/<recording_stem>/<well>/kilosort_ready_manifest.json
results/kilosort/<recording_stem>/<well>/kilosort4/       # after RUN_KILOSORT=true
```

## MATLAB Bridge

Use this from MATLAB to validate a well and locate source files/geometry:

```matlab
addpath("/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/matlab")
files = axion_well_source_files("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/data/raw", "A1");
```

The returned struct includes:

- `spike_list_csv`, `spike_counts_csv`, `raw_file`, `spk_file`
- `plate_row`
- `electrode_geometry`
- `recording_stem`

## Immediate Next Decision

The remaining missing piece is the Axion continuous-trace exporter: either your existing MATLAB code exports per-well row-major binaries, or we add a Python/SpikeInterface conversion path once the exact Axion raw-trace format is confirmed.
