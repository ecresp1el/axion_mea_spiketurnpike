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

## Raw File Inventory And Filtering State

Source Axion raw tree on Great Lakes:

```text
/nfs/turbo/umms-parent/axion_mea_files_directory
```

MATLAB/Slurm metadata inventory output:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/metadata/matlab_axisfile_raw_metadata_inventory.csv
```

Inventory provenance:

- Slurm job `52953365` completed the first full MATLAB metadata pass on
  `2026-07-05`; all 14 `.raw` files returned `status=ok`.
- Slurm job `52953515` reran the inventory after adding explicit filter fields;
  it completed on `2026-07-05` in `00:06:41` on `gl3460`.
- The metadata path opens one raw file at a time through MATLAB AxionFileLoader
  classes, reads header/tag metadata only, closes the file, and does not load
  continuous voltage traces.

Current file count:

| File state | Count | Filtering interpretation from MATLAB metadata |
|---|---:|---|
| Primary `.raw` | 7 | `AnalogMode=NeuralBroadband`; `Digital High Pass Filter=0.1 Hz IIR`; `Digital Low Pass Filter=None` |
| `_BroadbandProcessor.raw` | 7 | Same recording metadata plus Broadband Processor high-frequency band `200 Hz` high-pass to `5 kHz` low-pass, both `Butterworth`, `1` pole |
| Total `.raw` files | 14 | All sampled at `12500 Hz` |

Important interpretation:

- The `200 Hz` to `5 kHz` spike-band filtering applies to the
  `_BroadbandProcessor.raw` files only: **7 of 14 total raw files**.
- The primary `.raw` files are not the `200 Hz` to `5 kHz` Broadband Processor
  outputs. They are NeuralBroadband recordings with AxIS metadata showing
  `0.1 Hz IIR` digital high-pass and no digital low-pass.
- The `_BroadbandProcessor.raw` metadata also reports a low-frequency median
  processor branch: `1 Hz` to `200 Hz` using `Median DownSampler`. For spike
  sorting, the relevant Broadband Processor spike-band branch is the
  high-frequency `200 Hz` to `5 kHz` band.
- The inventory CSV can look visually awkward if opened as plain text because
  Axion stores some settings inside multiline description fields. Use the
  explicit filter columns and this handoff interpretation rather than manually
  reading embedded description lines.

Raw files currently present:

| Source folder | Primary raw | BroadbandProcessor raw | Plate state | Duration from metadata |
|---|---:|---:|---|---:|
| `2_12_2026/129-8447` | 3 | 3 | `FortyEightWellLumos`, 768 channels | 600 s; one primary is 599.75 s |
| `2_20_2026/129-8447` | 1 | 1 | `FortyEightWellLumos`, 768 channels | 2252 s |
| `2_24_2026/134-0150` | 2 | 2 | `SixWell`, 384 channels | 1199.75 s and 1 s test |
| `2_25_2026/129-8447` | 1 | 1 | `FortyEightWellLumos`, 768 channels | 900 s |

Exact raw paths:

```text
/nfs/turbo/umms-parent/axion_mea_files_directory/2_12_2026/129-8447/opto_test_meis2_with_E2opsin(000).raw
/nfs/turbo/umms-parent/axion_mea_files_directory/2_12_2026/129-8447/opto_test_meis2_with_E2opsin(000)_BroadbandProcessor.raw
/nfs/turbo/umms-parent/axion_mea_files_directory/2_12_2026/129-8447/opto_test_meis2_with_E2opsin(001).raw
/nfs/turbo/umms-parent/axion_mea_files_directory/2_12_2026/129-8447/opto_test_meis2_with_E2opsin(001)_BroadbandProcessor.raw
/nfs/turbo/umms-parent/axion_mea_files_directory/2_12_2026/129-8447/opto_test_meis2_with_E2opsin(002).raw
/nfs/turbo/umms-parent/axion_mea_files_directory/2_12_2026/129-8447/opto_test_meis2_with_E2opsin(002)_BroadbandProcessor.raw
/nfs/turbo/umms-parent/axion_mea_files_directory/2_20_2026/129-8447/test(000).raw
/nfs/turbo/umms-parent/axion_mea_files_directory/2_20_2026/129-8447/test(000)_BroadbandProcessor.raw
/nfs/turbo/umms-parent/axion_mea_files_directory/2_24_2026/134-0150/test(000).raw
/nfs/turbo/umms-parent/axion_mea_files_directory/2_24_2026/134-0150/test(000)_BroadbandProcessor.raw
/nfs/turbo/umms-parent/axion_mea_files_directory/2_24_2026/134-0150/test(001).raw
/nfs/turbo/umms-parent/axion_mea_files_directory/2_24_2026/134-0150/test(001)_BroadbandProcessor.raw
/nfs/turbo/umms-parent/axion_mea_files_directory/2_25_2026/129-8447/test(000).raw
/nfs/turbo/umms-parent/axion_mea_files_directory/2_25_2026/129-8447/test(000)_BroadbandProcessor.raw
```

## Environment

Conda file:

```text
envs/kilosort-greatlakes.yml
```

Important difference from older project envs:

- This env is intentionally installed under Turbo, not under
  `/home/elcrespo/miniconda3/envs`.
- Kilosort pulls in PyTorch plus CUDA libraries, so it is much larger than the
  older Axion/opto analysis envs. On 2026-07-05, a home-prefix install failed
  with `No space left on device`.
- The repo therefore sends both conda packages and pip wheels to Turbo:

  ```text
  CONDA_ENV=${PROJECT_ROOT}/envs/axion-kilosort
  CONDA_PKGS_DIRS=${PROJECT_ROOT}/conda_pkgs
  PIP_CACHE_DIR=${PROJECT_ROOT}/pip_cache
  ```

- `scripts/setup_kilosort_env.sh` uses a two-step install on purpose:
  first conda creates the Python/PyTorch/CUDA environment from
  `envs/kilosort-greatlakes.yml`, then pip installs `kilosort==4.1.3` inside
  the completed environment. Keeping Kilosort out of the YAML makes failures
  easier to diagnose and avoids hiding pip errors inside a conda rollback.

Create/update:

```bash
cd /home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
bash scripts/setup_kilosort_env.sh
conda activate /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/envs/axion-kilosort
python scripts/check_kilosort_env.py
```

Expected storage footprint after the successful 2026-07-05 install:

```text
${PROJECT_ROOT}/envs/axion-kilosort  ~9.2G
${PROJECT_ROOT}/conda_pkgs           ~5.5G
${PROJECT_ROOT}/pip_cache            ~127M
```

Slurm GPU check:

```bash
mkdir -p /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs
sbatch slurm/check_kilosort_env.sbatch
```

On 2026-07-05 this completed as Slurm job `52950844` on `gl1020` with:

```text
Python 3.11.6
torch: 2.5.1
kilosort: 4.1.3
torch cuda available: True
torch cuda device 0: Tesla V100-PCIE-16GB
kilosort import check: ok
```

If a Slurm wrapper fails during `conda activate` with an error like
`MKL_INTERFACE_LAYER: unbound variable`, keep the `set +u` / `set -u` guard
around conda activation. Some conda activation hooks read unset variables, so
strict shell mode must be paused only for activation.

Do not treat `torch cuda available: False` on a login node as a failure. Login
nodes do not expose the GPU. The authoritative check is the Slurm GPU job.

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

Smoke test already performed:

- Slurm job `52950875` ran `slurm/run_kilosort_well.sbatch` on a tiny synthetic
  A1 binary with `RUN_KILOSORT=false`.
- It confirmed GPU visibility, Kilosort import, plate-map lookup, probe JSON
  writing, binary shape validation, and readiness manifest writing.
- It did not run spike sorting, because fake 0.1 second data are only useful
  for wiring checks.

Synthetic smoke outputs live under:

```text
${PROJECT_ROOT}/scratch/env_smoke/slurm_A1_ready/
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
