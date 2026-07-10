# Great Lakes Kilosort Transition Handoff

Date: 2026-07-05

This handoff mirrors the working habits from `mge_organoid_pipeline`:

- code and Slurm templates live in the Git repo,
- large data, logs, generated job files, and Kilosort outputs live in Turbo,
- jobs source small `.env` files for project/sample configuration,
- conda activation happens inside the Slurm script,
- every run writes a machine-readable manifest before heavy compute starts.
- every run output keeps a `repro/` folder with the exact submit/run command
  and copied resolved config, matching the older Axion project
  `repro/rebuild_command.sh` pattern.

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

Each per-well stage output should also keep its own local reproducibility
bundle:

```text
<stage-output>/repro/
  submit_command.sh               # exact sbatch command when run through Slurm
  python_command.sh or matlab_command.sh
  project_config.env
  sample/export/nwb_config.env
  submitted_job.sbatch            # future runs; current backfills may store current template
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

The default per-well geometry is a 4 x 4 grid with Axion channel labels
`11..44`. AxionFileLoader treats electrode labels as `column,row`: electrode
`31` is electrode column `3`, row `1`. The geometry CSV therefore stores
physical rows/columns this way, and the Kilosort channel order is row-major
physical layout: `11, 21, 31, 41, 12, ...`.

For Lumos MEA 48 runs, the repo now uses 350 um within-well electrode spacing
in `metadata/plate_maps/axion_per_well_4x4_electrode_geometry.csv`.

## Kilosort Boundary

Kilosort4 needs a continuous row-major binary trace and a probe geometry. The existing Axion pipeline can parse spike-list CSVs, `.spk` waveform snippets, and stimulation metadata in `.raw`, but those are not enough by themselves for Kilosort sorting.

The first Axion voltage-export scaffold is now:

```text
matlab/export_axion_well_kilosort_binary.m
slurm/export_axion_well_binary.sbatch
config/example_export_axion_well_binary.env
run_axion_binary_to_nwb.py
slurm/export_axion_well_nwb.sbatch
config/example_export_axion_well_nwb.env
```

It uses MATLAB AxionFileLoader to load one well from an Axion continuous
dataset, writes `int16` time-major/interleaved binary samples, and writes a
`channel_mapping.csv` showing the exact electrode/channel order used.

The NWB adapter packages the exported binary as an NWB `ElectricalSeries`,
copies Axion/Kilosort sidecars into NWB scratch space, stores the Axion channel
map in the NWB electrode table, and embeds the matched row from the MATLAB raw
metadata inventory as `axion_raw_metadata_inventory_row_json`. This is the
preferred bridge to the Kempner/AIND workflow because NWB is one of its
supported input types.

Current contract for real data:

1. Place or generate one continuous binary per well under:

   ```text
   ${PROJECT_ROOT}/data/interim/kilosort_binary/<recording_stem>/<well>.bin
   ```

2. Keep the original Axion export set under `data/raw/` or point `BINARY_FILE`/`RECORDING_STEM` to its source.

3. Run readiness first with `RUN_KILOSORT=false`.

4. Only after the manifest validates channel count, file size, plate map, and probe geometry, rerun with `RUN_KILOSORT=true`.

Current Lumos MEA 48 Kilosort4 defaults before multi-well scale-up:

- `n_chan_bin=16`, one binary per well.
- `nblocks=0` to skip drift correction.
- `nt=31`; `nt0min` left unset so Kilosort derives it.
- `dmin=350`, `dminx=350`, `max_channel_distance=400`, `x_centers=4`.
- `nearest_templates=16`, `nearest_chans=5`, `min_template_size=50`,
  `whitening_range=8`.
- Conservative thresholds retained: `Th_universal=9`, `Th_learned=8`,
  `Th_single_ch=6`.

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

Real Axion one-well proof completed:

- Export job `52953995` used MATLAB AxionFileLoader to export 60 seconds from
  `/nfs/turbo/umms-parent/axion_mea_files_directory/2_25_2026/129-8447/test(000)_BroadbandProcessor.raw`
  for well `A1`.
- Output binary:

  ```text
  ${PROJECT_ROOT}/data/interim/kilosort_binary/test_2_25_2026_129-8447_test(000)/A1/A1.bin
  ```

- Export manifest and channel map:

  ```text
  ${PROJECT_ROOT}/data/interim/kilosort_binary/test_2_25_2026_129-8447_test(000)/A1/binary_export_manifest.json
  ${PROJECT_ROOT}/data/interim/kilosort_binary/test_2_25_2026_129-8447_test(000)/A1/channel_mapping.csv
  ```

- The exported binary is `int16`, 16 channels, 750,000 samples, 60 seconds,
  24,000,000 bytes.
- The channel order is physical row-major:
  `11,21,31,41,12,22,32,42,13,23,33,43,14,24,34,44`.
- Readiness job `52954047` wrote a valid probe/readiness manifest.
- Kilosort job `52954130` completed with `RUN_KILOSORT_OVERRIDE=true`.
  Kilosort4 reported 4 total units, 1 good unit, and 217 spikes in this short
  test window. Results live under:

  ```text
  ${PROJECT_ROOT}/results/kilosort/test_2_25_2026_129-8447_test(000)/A1/kilosort4/
  ```

- Kilosort 4.1.3 calls the removed NumPy alias `np.in1d`; the repo now applies
  a compatibility shim before invoking Kilosort, and the Great Lakes env YAML
  pins future solves to `numpy<2.4`.

The first attempt against
`opto_test_meis2_with_E2opsin(000)_BroadbandProcessor.raw` from `2026-02-12`
was cancelled after `AxisFile(...)` stayed in metadata parsing for several
minutes. That opto file still needs a targeted path after the exporter is
validated on normal-offset files.

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

The Kempner/AIND ephys workflow was evaluated as a possible shortcut. The
current recommendation is to keep that repository as an external reference and
adapt only its orchestration ideas, not vendor the full repo here. See
`docs/KEMPNER_WORKFLOW_ADAPTATION_PLAN.md`.

## Axion Filter Metadata Rule

Updated 2026-07-08: the Great Lakes handoff must preserve the full Axion filter
metadata parsed from raw `dataset_description`. The old simplified extraction
was insufficient because repeated keys such as `High Pass Filter` and
`Low Pass Filter` can occur inside multiple named filter blocks.

The parser and pass-through patches are:

```text
src/axion_mea/filter_metadata.py
scripts/audit_axion_file_ground_truth.py
scripts/build_aind_recordings_manifest.py
scripts/prepare_aind_recording_batches.py
scripts/prepare_aind_well_batch.py
src/axion_mea/well_selection.py
```

Every future CSV handoff should preserve `filter_block_names`,
`filter_blocks_json`, derived cutoff frequency fields, and the section-specific
`digital_filter_settings_*` / `broadband_processor_*` columns. The corrected
audit root is:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_20260708_filter_metadata_patch/
```

## Step 1 V5 Ground-Truth Run State

Updated 2026-07-09. Treat this folder as the current single source for the
Step 1 v5 rerun state and batch cross-reference:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/
```

Key files:

```text
step1_v5_well_ground_truth.csv              # per-well status across batches
step1_v5_ground_truth_summary.txt           # human-readable current summary
step1_v5_ground_truth_summary.json          # machine-readable current summary
submitted_step1_v5_ground_truth_waves.tsv   # wave/batch submission labels
lumos_gui_ready_trial_tag_screen_250pulse_jitterwin_20260709.csv
lumos_manual_spike_sorting_guide_jitterwin_20260709.csv
lumos_candidate_waveform_gallery_columns_compare_20260709.png
lumos_candidate_waveform_best_channel_normalized_vs_unnormalized_20260709.png
lumos_candidate_waveform_kslabel_summary_20260709.csv
lumos_candidate_waveform_best_channel_traces_20260709.csv.gz
lumos_candidate_waveform_full_templates_20260709.npz
good_kslabel_ttp_distribution_template_best_ptp_20260709.png
good_kslabel_ttp_distribution_template_best_ptp_20260709.csv
good_kslabel_ttp_distribution_template_best_ptp_20260709_provenance.json
waveform_alignment_feature_audit_20260709/
lumos_alignment_cutoff_sensitivity_20260709/
```

## Current Single Source: Waveform Alignment, Cutoffs, And Denominators

Updated 2026-07-09 15:57 EDT. This section is the canonical source of truth
for the current waveform/cutoff/alignment inspection outputs until Step 2
filtering is implemented. The figures and CSVs below are denominator-preserving
inspection artifacts. Do not silently add extra filters, change unit inclusion,
or relabel the populations in place.

Future filtering rule:

- Current outputs preserve the full current inspection denominator.
- Any later post-Step-2 filtering must create a new dated filtered output
  folder, keep the original denominator CSV/provenance linked, and report the
  exclusion counts and reasons before any histogram or FS/RS interpretation.
- Step 2 classifier/QC outputs are metadata for future filtering. They should
  not be retroactively mixed into the current 2026-07-09 waveform figures unless
  a new filtered analysis is explicitly generated.

Canonical current denominator artifacts:

| Track | Biological/grouping meaning | Current denominator | Canonical output folder |
|---|---|---:|---|
| Lumos | Lumos/opto-track geometry only; all treated as opto/ventral-track review, not dorsal/ventral biology | `276` paired `KSLabel=good` units | `/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_geometry_alignment_cutoff_composite_20260709/` |
| Cytoview/SixWell | True dorsal/ventral track from plate-map-backed wells plus manual B1/B2 override layer | `237` paired `KSLabel=good` units | `/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dv_alignment_cutoff_composite_20260709/` |

Shared waveform math for both tracks:

- Use the same Step 1 `SortingAnalyzer` source for the unit.
- Use `KSLabel=good` as the current inclusion label.
- Select the best waveform channel as the channel with maximum
  peak-to-peak amplitude across `templates.average`.
- Use the persisted `random_spikes` selection from the analyzer so the before
  and after waveforms use the exact same sampled spike snippets.
- Cut snippets with `nbefore` / `nafter` from the analyzer `templates`
  extension.
- `unaligned` means directly averaging those snippets.
- `aligned` means shifting those exact same snippets so the local trough near
  the expected spike center aligns to the template trough sample, then averaging.
- Measure both averages with `_measure_spiketurnpike_waveform_metrics(...)`,
  the same TTP/half-width/REP logic, and the same REP50 fraction.
- Use the same binary FS/RS cutoff views at `0.37 ms` and `0.50 ms`.
- Keep the older conservative FS_like/borderline/RS_like audit separate from
  the binary cutoff figures.
- Sampling rate is `12.5 kHz`, so one sample is `0.08 ms`. One-sample shifts
  matter for TTP, half-width, REP, and any downstream FS/RS binning.

Preferred current figures:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_geometry_alignment_cutoff_composite_20260709/lumos_geometry_alignment_cutoff_composite_20260709.png
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dv_alignment_cutoff_composite_20260709/cytoview_dv_alignment_cutoff_composite_20260709.png
```

Lumos grouping and counts:

- Groups are `columns_1_3_compare` and `columns_4_8_prior`.
- These are Lumos plate-column geometry/opto-review groups, not dorsal/ventral
  biological groups.
- Denominator is `276` paired Lumos `KSLabel=good` units:
  `127` from columns `1-3` and `149` from columns `4-8`.

| Cutoff | Alignment state | Overall FS | Overall RS | Columns 1-3 FS | Columns 1-3 RS | Columns 4-8 FS | Columns 4-8 RS |
|---:|---|---:|---:|---:|---:|---:|---:|
| `0.37 ms` | unaligned | 16 | 260 | 10 | 117 | 6 | 143 |
| `0.37 ms` | aligned | 24 | 252 | 12 | 115 | 12 | 137 |
| `0.50 ms` | unaligned | 56 | 220 | 36 | 91 | 20 | 129 |
| `0.50 ms` | aligned | 85 | 191 | 45 | 82 | 40 | 109 |

Cytoview dorsal/ventral grouping and counts:

- Groups are true `dorsal` and `ventral` labels from the current plate-map plan
  plus the manual B1/B2 override layer.
- Denominator is `237` paired Cytoview `KSLabel=good` units from the 52
  GUI-ready priority wells.
- Class-agnostic firing-rate panel pools all good units regardless of FS/RS:
  dorsal `113` units across `22` wells, median/mean `0.5047 / 0.8129 Hz`;
  ventral `124` units across `28` wells, median/mean `1.4010 / 1.7603 Hz`.

| Cutoff | Alignment state | Dorsal FS | Dorsal RS | Ventral FS | Ventral RS |
|---:|---|---:|---:|---:|---:|
| `0.37 ms` | unaligned | 6 | 107 | 3 | 121 |
| `0.37 ms` | aligned | 4 | 109 | 3 | 121 |
| `0.50 ms` | unaligned | 10 | 103 | 12 | 112 |
| `0.50 ms` | aligned | 20 | 93 | 18 | 106 |

Historical/prototype status:

- `lumos_alignment_cutoff_sensitivity_20260709/` contains the earlier four
  separate Lumos cutoff/alignment PNGs. They remain valid method QA outputs,
  but the Lumos geometry composite above is now the preferred Lumos figure.
- The older Lumos candidate waveform galleries remain useful manual-review
  screens for top optotag candidates, but they are not the current denominator
  reconciliation for all good units.

Next handoff target:

- Representative-unit plot waves should be built from the post-Step-1 unified
  unit/spike sources while preserving `KSLabel=good` as ground truth and linking
  Step 2/QC assets as metadata. The immediate targets are GUI-equivalent static
  panels for waveform/firing-rate stability over time, representative
  auto/cross-correlograms for FS/RS units, and within-well spatial footprints
  across neighboring electrodes, all rendered from the same Step 1 analyzer data
  that the GUI visualizes. Use:
  `docs/HANDOFF_REPRESENTATIVE_UNITS_POST_STEP1_PLOTS.md`.
- Wave 0 representative-unit indexing completed on 2026-07-09 16:22 EDT via
  Slurm job `53201743`:
  `/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_wave0_20260709_162201/`.
  It recovered the locked denominator exactly: `276 / 276` Lumos geometry units
  and `237 / 237` Cytoview dorsal/ventral units, all `KSLabel=good`, all with
  Step 1 analyzers ready. Step 2 linked assets were `0` for this v5 denominator,
  so A/B/C representative plots should use Step 1 analyzer-backed
  GUI-equivalent data first.
- Corrected Wave A/B/C representative candidate scoring completed on 2026-07-09
  17:30 EDT via Slurm job `53210960`:
  `/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_abc_scoring_20260709_172908/`.
  It scored `513` stability units, `851` within-well pairs, and `176` wells,
  with `0` analyzer errors. The selected candidate manifests are
  `waveA_stability_representative_units_20260709.csv`,
  `waveB_correlogram_representative_units_20260709.csv`, and
  `waveC_spatial_footprint_representative_wells_20260709.csv`. A prior scoring
  run `53210725` is superseded for Wave B because the pair-distance cutoff was
  too strict and returned same-best-channel pairs; job `53210960` ranks
  nonzero-distance neighboring-electrode pairs first.
- Final representative-figure selection manifests completed on 2026-07-09
  17:43 EDT via Slurm job `53212357`:
  `/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_final_selection_20260709_174251/`.
  This is the current source for first-pass representative figure rendering.
  It preserves separate selection pools for Lumos geometry, Cytoview dorsal,
  and Cytoview ventral. It writes `48` selected rows total: for each pool,
  `6` Wave A stability units, `6` Wave B correlogram pairs, and `4` Wave C
  spatial wells. Candidate denominators before final selection were Lumos
  `276` units / `256` pairs / `126` wells, Cytoview dorsal `113` units /
  `312` pairs / `22` wells, and Cytoview ventral `124` units / `283` pairs /
  `28` wells. The manifest explicitly carries
  `variant_policy=preserve_all_raw_filter_broadband_variants_no_deduplication`;
  do not collapse primary, filtered, or broadband-processor variants when
  rendering the figures.
- First-pass GUI-equivalent static representative plot pack completed on
  2026-07-09 17:55 EDT via Slurm job `53213093`:
  `/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_plot_pack_20260709_175429/`.
  It rendered `48` PNG panels and `0` errors: for each of Lumos geometry,
  Cytoview dorsal, and Cytoview ventral, `6` Wave A stability panels, `6`
  Wave B correlogram panels, and `4` Wave C spatial-footprint panels. The
  renderer consumes the frozen final-selection manifests and loads the Step 1
  `SortingAnalyzer` data for spike trains, templates, correlograms when
  available, and channel locations. Visual spot-checks confirmed nonblank
  Wave A/B/C panels. Caveat: some Wave B pairs are technically clean but sparse
  for publication-style correlogram examples; add a stricter pair-level
  minimum-spike floor or manual override before final figure selection.
- Corrected Wave C multichannel-template plot pack completed on 2026-07-09
  18:22 EDT via Slurm job `53215665`:
  `/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_plot_pack_20260709_182100/`.
  The previous Wave C panels were amplitude dot maps only. The corrected Wave C
  panels now plot each unit's template waveform at each electrode location,
  highlight the strongest channels, circle the best channel, and include a
  20 uV / 1 ms scale cue. The corrected pack again rendered `48` PNG panels and
  `0` errors, with all `12` Wave C rows marked
  `selection_panel=within_well_multichannel_template_footprints`. Use the
  `20260709_182100` root for spatial-footprint inspection; keep the
  `20260709_175429` root only as provenance for the superseded dot-map version.
- Spatial-isolation 1x2 panels completed on 2026-07-09 18:30 EDT via Slurm job
  `53216188`:
  `/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_spatial_isolation_1x2_20260709_182942/`.
  These are the most direct current panels for arguing that multiple
  `KSLabel=good` units in the same well have minimally overlapping spatial
  profiles and non-duplicate spike timing. Each figure has a left panel with
  overlaid normalized spatial PTP profiles and a right panel with the
  corresponding auto/cross-correlogram matrix. It rendered `12` PNG panels and
  `0` errors: `4` Lumos, `4` Cytoview dorsal, and `4` Cytoview ventral. The
  selected unit subsets use `min_spikes=100`; mean footprint overlap ranges
  from `0.0000` to `0.0280`, and mean best-channel distance ranges from `398`
  to `1293 um`.
- Preferred spatial-isolation 1x3 panels completed on 2026-07-09 18:39 EDT via
  Slurm job `53216594`:
  `/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_spatial_isolation_1x3_20260709_183800/`.
  This uses the same selected units as the 1x2 panels but adds the missing
  waveform evidence. Each figure has: left, centered best-channel mean
  waveforms for unit identity; middle, actual multichannel template waveforms
  plotted on the electrode grid; right, the auto/cross-correlogram matrix. It
  rendered `12` PNG panels and `0` errors: `4` Lumos, `4` Cytoview dorsal, and
  `4` Cytoview ventral. Use this `20260709_183800` root as the preferred
  spatial-isolation review pack.

Use `continuation_batch`, `ground_truth_wave_label`, submitted job ids, and
`ground_truth_status` in `step1_v5_well_ground_truth.csv` to cross-reference
batch 1 vs batch 2 vs batch 3. Do not infer batch membership from recording
name alone.

The jitter-aware Lumos trial-tagging screen uses:

```text
baseline: -25..-8 ms
response: -5..+50 ms
during-stim QC: 0 ms through reconstructed pulse end
train-trial baseline: -10..-5 ms
train-trial response: -5..+50 ms
```

As of the 2026-07-09 13:42 EDT refresh after Lumos standard-route completion,
the Lumos GUI-ready subset is 150 wells: 108 scored with usable stimulation
metadata and 42 marked `stim_unavailable`.

The manual guide CSV keeps `D2` as a top-priority review case rather than
treating it as a negative control, because the current working interpretation is
that `D2` may be a real outside-prior response.

The GUI PSTHs use 1 ms bins for both train-locked and pulse-locked views, with
a `[1, 1, 1]` smoothing kernel for the smoothed line. The Lumos screen/guide
CSV includes window-average rates plus peak 1 ms PSTH signal columns:
`*_rate_hz`, `*_peak_raw_rate_hz`, and `*_peak_smooth_rate_hz`. The manual guide
is ranked by `review_sort_peak_raw_response_hz`, the pulse-locked raw 1 ms peak
inside `-5..+50 ms`; D2 remains flagged as possible-real but is no longer forced
above stronger peak-raw candidates. Regenerate the current Lumos screen and
manual guide with:

```bash
python scripts/refresh_lumos_optotag_analysis.py --date-label 20260709
```

The waveform/KSLabel comparison gallery is generated with:

```bash
python scripts/plot_lumos_candidate_waveform_gallery.py --date-label 20260709
```

The current all-good-unit TTP distribution is generated with:

```bash
python scripts/plot_good_kslabel_ttp_distribution_from_templates.py --date-label 20260709
```

This TTP distribution intentionally replaces the older master-table waveform
metric path for current rerun inspection. It scans the current GUI-ready Step 1
analyzers, keeps `KSLabel=good`, loads `templates.average`, chooses the best
peak-to-peak channel, then measures trough to post-trough rebound peak with the
same landmark logic as the Lumos candidate waveform gallery. On the 2026-07-09
13:46 EDT refresh it scanned 150 GUI-ready wells and plotted 276 good units:
16 `FS_like`, 40 `borderline`, and 220 `RS_like`, median TTP 0.720 ms.

Waveform alignment audit, generated 2026-07-09 15:14 EDT:

```bash
python scripts/audit_waveform_alignment_before_feature_extraction.py
```

Audit outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/waveform_alignment_feature_audit_20260709/
waveform_alignment_feature_audit_20260709_paired_unit_metrics.csv
waveform_alignment_feature_audit_20260709_metric_delta_summary.csv
waveform_alignment_feature_audit_20260709_landmark_delta_summary.csv
waveform_alignment_feature_audit_20260709_class_counts.csv
waveform_alignment_feature_audit_20260709_waveform_traces.csv.gz
waveform_alignment_feature_audit_20260709_metric_deltas.png
waveform_alignment_feature_audit_20260709_before_after_scatter.png
waveform_alignment_feature_audit_20260709_largest_change_waveforms.png
waveform_alignment_feature_audit_20260709_class_counts_same_cutoffs.png
waveform_alignment_feature_audit_20260709_provenance.json
```

This audit is a paired before/after test, not a different unit population. The
input population is exactly
`good_kslabel_ttp_distribution_template_best_ptp_20260709.csv`, the same Lumos
`KSLabel=good` table used above (`276` units). For every unit, the best channel
is selected with the same rule as the TTP/gallery outputs:
`best_channel_index = argmax(max(template) - min(template))` across
`templates.average` channels. The script then reopens the same `analyzer_path`
and loads the persisted Step 1 `SortingAnalyzer` assets: `sorting`, `recording`,
`templates`, and `random_spikes`.

The before and after waveforms use the exact same sampled spikes. For each unit,
the persisted `random_spikes` selection is used to extract snippets from the
analyzer recording on the fixed best channel. Snippets are cut with the same
template window, `nbefore` / `nafter`, from the analyzer `templates` extension.
The before waveform is the plain average of those snippets without extra
alignment. The after waveform uses those exact same snippets, shifts each
snippet so its local trough near the expected spike center aligns to the
template trough sample, then averages the aligned snippets.

Feature extraction is then identical for before and after: both averages are
measured with `_measure_spiketurnpike_waveform_metrics(...)`, the same TTP
classifier, the same cutoffs, and the same REP fraction (`0.5`/REP50 by
default). This means the comparison does not mix different units, channels,
spikes, or thresholds. It isolates the effect of per-snippet trough alignment
before feature extraction.

Sampling-rate note: these Axion Step 1 analyzers are sampled at `12.5 kHz`, so
one sample is `0.08 ms`. One-sample landmark shifts therefore matter for TTP,
half-width, and REP-style measurements. In the full 276-unit Lumos good-unit
audit, median absolute TTP change after alignment was `0.08 ms`, and
`51 / 276` units changed FS/borderline/RS bin under the same TTP cutoffs
(`16/40/220` before alignment versus `24/61/191` after alignment for
FS_like/borderline/RS_like). Treat this as evidence that waveform alignment
should be considered before final SpikeTurnpike-style feature extraction, while
preserving this paired audit output as the denominator/methods record.

The four cutoff/alignment comparison figures requested after this audit are
generated with:

```bash
python scripts/plot_lumos_alignment_cutoff_sensitivity.py
```

These are four separate multi-panel outputs, all using the same `276` paired
Lumos `KSLabel=good` units and the same paired waveform traces:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_alignment_cutoff_sensitivity_20260709/
lumos_ttp_cutoff_0p37_unaligned_multipanel.png
lumos_ttp_cutoff_0p37_aligned_multipanel.png
lumos_ttp_cutoff_0p50_unaligned_multipanel.png
lumos_ttp_cutoff_0p50_aligned_multipanel.png
lumos_alignment_cutoff_sensitivity_20260709_classified_units_long.csv
lumos_alignment_cutoff_sensitivity_20260709_summary.csv
lumos_alignment_cutoff_sensitivity_20260709_provenance.json
```

Each figure has the same panel layout: TTP distribution, class counts, pooled
best-channel waveforms, half-width by class, REP50 by class, and amplitude by
class. The `unaligned` figures use the `before_*` metrics and
`before_unaligned_average_uV` traces from the paired audit. The `aligned`
figures use the `after_*` metrics and `after_aligned_average_uV` traces.
These Lumos figures are a unified-method QA/prototype for the spike-sorting
waveform workflow only. They are not dorsal/ventral biological comparisons,
because the dorsal/ventral grouping logic belongs to the Cytoview plate-map
track below.

The Lumos geometry counterpart, generated 2026-07-09 15:49 EDT, uses the same
paired waveform alignment audit and the same cutoff/alignment math as the
Cytoview composite, but groups wells by Lumos plate-column geometry:
`columns_1_3_compare` and `columns_4_8_prior`. These are geometry/opto-review
groups, not dorsal/ventral biological labels.

```bash
python scripts/plot_lumos_geometry_alignment_cutoff_composite.py
```

Outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_geometry_alignment_cutoff_composite_20260709/
lumos_geometry_alignment_cutoff_composite_20260709.png
lumos_geometry_alignment_cutoff_composite_20260709_classified_units_long.csv
lumos_geometry_alignment_cutoff_composite_20260709_summary.csv
lumos_geometry_alignment_cutoff_composite_20260709_provenance.json
```

This one-page Lumos figure has four rows (`0.37 ms unaligned`,
`0.37 ms aligned`, `0.50 ms unaligned`, `0.50 ms aligned`) and columns for
overall FS/RS counts, geometry-group FS/RS fractions, geometry-group counts,
TTP by geometry, pooled uV waveforms, individual uV traces with class means,
pooled trough-normalized waveforms, and half-width versus REP50. It uses the
same `276` paired Lumos `KSLabel=good` units as the alignment audit:
`127` units from columns `1-3` and `149` units from columns `4-8`.

Current Lumos geometry counts:

| Cutoff | Alignment state | Overall FS | Overall RS | Columns 1-3 FS | Columns 1-3 RS | Columns 4-8 FS | Columns 4-8 RS |
|---:|---|---:|---:|---:|---:|---:|---:|
| `0.37 ms` | unaligned | 16 | 260 | 10 | 117 | 6 | 143 |
| `0.37 ms` | aligned | 24 | 252 | 12 | 115 | 12 | 137 |
| `0.50 ms` | unaligned | 56 | 220 | 36 | 91 | 20 | 129 |
| `0.50 ms` | aligned | 85 | 191 | 45 | 82 | 40 | 109 |

Current four-condition counts:

| Cutoff | Alignment state | FS_like | RS_like | Unknown |
|---:|---|---:|---:|---:|
| `0.37 ms` | unaligned | 16 | 260 | 0 |
| `0.37 ms` | aligned | 24 | 252 | 0 |
| `0.50 ms` | unaligned | 56 | 220 | 0 |
| `0.50 ms` | aligned | 85 | 191 | 0 |

That script reads the jitter-aware manual guide, takes the top signal-ranked
`status == ok` rows from columns 4-8 and columns 1-3 separately, derives each
analyzer path as:

```text
<AIND results root>/<recording>/<well>/postprocessed/block0_None_recording1.zarr
```

For each candidate, it loads the persisted Step 1 `SortingAnalyzer`, pulls the
curated sorting properties (`KSLabel`, `ContamPct`, `Amplitude`), loads
`templates.average` from the analyzer `templates` extension, matches the guide
`top_unit` to the analyzer unit order, and plots the full multi-channel template
in grey with the best peak-to-peak channel in black.

The downstream data contract is:

```python
analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
sorting = analyzer.sorting
unit_ids = list(sorting.get_unit_ids())
unit_id = match_unit_id(unit_ids, guide_row["top_unit"])
unit_index = unit_ids.index(unit_id)
templates = analyzer.get_extension("templates").get_data(operator="average")
template = templates[unit_index]  # shape: n_template_samples x n_channels
channel_ptp = np.ptp(template, axis=0)
best_channel_index = int(np.nanargmax(channel_ptp))
best_waveform = template[:, best_channel_index]
trough_index = int(np.nanargmin(best_waveform))
search_start = min(trough_index + 1, best_waveform.size - 1)
rebound_peak_index = search_start + int(np.nanargmax(best_waveform[search_start:]))
```

Thus grey traces are `template[:, channel_index]` for every analyzer channel.
The black trace is the channel with the largest `max - min` amplitude across the
average template. The voltage peak/trough columns in the summary CSV are derived
from this black trace and are template amplitudes, not Kilosort optotag metrics.
The Kilosort/Phy-derived fields are the sorting properties such as `KSLabel`,
`ContamPct`, and `Amplitude`.

The trough/peak dots on the gallery use the same black trace: black dot =
minimum/trough of `best_waveform`; orange dot = maximum rebound peak after the
trough. Tentative FS/RS labels use the repo-wide conservative trough-to-peak rule:
`FS_like <= 0.37 ms`, `borderline` between `0.37..0.53 ms`, and
`RS_like >= 0.53 ms`. These labels are visual-review annotations only and should
not be treated as Kilosort labels.

The candidate summary also includes old SpikeTurnpike-style waveform metrics from
`Hochgeschwender-Lab/SpikeTurnpike/ProcessSUA_main.m`, computed on the same black
best-channel trace:

```text
spiketurnpike_amplitude_uV
spiketurnpike_legacy_cell_type
peak1_normalized_amplitude
peak2_normalized_amplitude
peak1_to_trough_ratio
peak2_to_trough_ratio
peak_to_peak_ratio
spike_half_width_ms
rep_fraction
rep_threshold_uV
rep_recovery_index
rep_recovery_time_ms
repolarization_time_ms
```

The old `UnNormalized_Template_Waveform` and `Normalized_Template_Waveform` are
stored in long form in
`lumos_candidate_waveform_best_channel_traces_20260709.csv.gz`; the full
multi-channel template cache is in
`lumos_candidate_waveform_full_templates_20260709.npz`. These cache files are the
preferred starting point for later visual inspection because they avoid reopening
the Step 1 analyzers. Do not add `waveform_asymmetry` or `repolarization_slope` to
this artifact; those are canonical axion table metrics but were intentionally
excluded from the SpikeTurnpike-style candidate view.

REP is included as an optional recovery-time metric, not as a replacement for
TTP. TTP is still the existing trough-to-rebound-peak time and continues to drive
the tentative FS/RS label. REP is measured from the trough until the post-trough
waveform first recovers to a configured fraction of the trough amplitude
(`--rep-fraction 0.25`, `0.5`, or `0.63`; default `0.5`/REP50), with linear
interpolation between samples. TTP and REP quantify different aspects of spike
shape and should both be reported.

For the NPZ arrays, dimensions mean:

```text
templates_uV: 24 candidates x 37 waveform samples x 16 analyzer channels
best_waveforms_uV: 24 candidates x 37 waveform samples
normalized_best_waveforms: 24 candidates x 37 waveform samples
```

The NPZ also stores REP arrays: `rep_fraction`, `rep_threshold_uV`,
`rep_recovery_index`, `rep_recovery_time_ms`, and `repolarization_time_ms`.

The normalized/unnormalized figure
`lumos_candidate_waveform_best_channel_normalized_vs_unnormalized_20260709.png`
shows the same black best-channel traces in both scales. Rows are columns 4-8 uV,
columns 4-8 normalized, columns 1-3 uV, columns 1-3 normalized. Marker colors:
blue = pre-trough peak, black = trough, orange = rebound peak, red-orange =
half-width anchors.

Landmark indices are detected on the unnormalized uV best-channel waveform:
pre-peak/peak1 is the maximum before or at the trough, trough is the minimum, and
rebound peak/peak2 is the maximum after the trough. The normalized waveform is
`best_waveform / abs(min(best_waveform))`. Half-width anchors are measured on that
normalized waveform at the closest samples to half the normalized trough
amplitude on the pre-trough and post-trough slopes. The same landmark sample
indices are displayed on both the uV and normalized rows. This is SpikeTurnpike
logic adapted to Axion/SpikeInterface templates: same peak/trough/ratio/half-width
definitions, but using the current gallery's best peak-to-peak analyzer channel
and the analyzer sampling rate instead of the old 30 kHz conversion.

REP uses the same trough index and the existing recovery side of the waveform:
`rep_threshold_uV = trough_value_uV * rep_fraction`, then the first post-trough
threshold crossing gives `repolarization_time_ms`. This does not change landmark
detection or the existing TTP metric.

Important amplitude interpretation: the plotted waveform values are uV-scaled
Step 1 analyzer template amplitudes, not raw acquisition traces and not native
Kilosort whitened/PCA templates. The templates are average snippets from the
preprocessed analyzer recording using uV scaling. The comparison gallery keeps a
shared y-axis scale across panels so columns 4-8 and columns 1-3 are visually
comparable. In contrast, `review_sort_peak_raw_response_hz` is not voltage; it is
the unsmoothed pulse-locked 1 ms PSTH peak firing rate in Hz.

Current gallery summary after the 2026-07-09 13:43 EDT refresh from the
150-well guide: top 12 columns 4-8 candidates have 4 `KSLabel=good` and
8 `KSLabel=mua`, median best-channel template PTP about 12.2 uV, median firing
rate 4.705 Hz, max firing rate 18.575 Hz, and max pulse-locked raw response
44 Hz. Top 12 columns 1-3 comparison candidates have 7 `KSLabel=good` and
5 `KSLabel=mua`, median best-channel template PTP about 10.1 uV, median firing
rate 1.077 Hz, max firing rate 3.432 Hz, and max pulse-locked raw response
20 Hz. Tentative TTP labels for this top-24 set are 12 RS-like/0 borderline/
0 FS-like in columns 4-8 and 7 RS-like/3 borderline/2 FS-like in columns 1-3.
Several columns 1-3 candidates remain clean `good` units, so outside-prior wells
should stay in manual review rather than being treated as automatically negative.

## Step 1 Ground Truth Snapshot, 2026-07-09 14:42 EDT

Use this Step 1 ledger as the current single source of truth for what is ready,
completed without analyzer assets, failed, or intentionally not run in the
current priority pass:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/step1_v5_well_ground_truth.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/step1_v5_ground_truth_summary.txt
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/step1_v5_ground_truth_summary.json
```

The corresponding Step 1 analyzer root remains:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/<recording>/<well>/postprocessed/block0_None_recording1.zarr
```

Current ledger rows: 454 total, split into 256 Lumos 48-well rows and
198 Cytoview/SixWell rows.

Lumos status, all current Lumos rows:

| Status | Count |
|---|---:|
| `gui_ready_standard` | 150 |
| `standard_failed_sparse_fallback_candidate` | 98 |
| `export_failed` | 8 |

Interpretation: Lumos is the optogenetics/optotagging track. Use the Lumos
manual sorting guide and pulse/train locked GUI panels only when stimulation
metadata are present and valid. The 150 GUI-ready Lumos wells are the current
source for optotagging/waveform visual inspection outputs; sparse fallback and
export-failed Lumos rows are not currently GUI-ready standard analyzers.

Cytoview/SixWell status, all current Cytoview rows:

| Status | Count |
|---|---:|
| `gui_ready_standard` | 52 |
| `completed_standard_no_gui_analyzer_yet` | 36 |
| `not_ready_or_not_started` | 108 |
| `standard_failed_sparse_fallback_candidate` | 2 |

Interpretation: Cytoview/SixWell is the dorsal/ventral Step 1 track. Do not use
Lumos opto assumptions here. The current biological Step 1 summaries should use
`KSLabel=good` units, TTP-based FS/borderline/RS designation, firing rate, and
ISI metrics computed directly from Step 1 SortingAnalyzer spike trains/templates.

Priority scope: only the 90 plate-map-backed dorsal/ventral Cytoview/SixWell
rows were clean-rerun in this cleanup. All 90 priority rows were submitted in
watched waves and drained. The remaining 108 Cytoview/SixWell rows were not
rerun here because they are outside the backed dorsal/ventral priority set; they
remain `not_ready_or_not_started` under the older canceled all-Cytoview wave
`cytoview_remaining_all_20260709_0214`.

Cytoview wave-label cross-reference:

| Wave label | Status | Count |
|---|---|---:|
| `cytoview_platemap_dv_priority_20_20260709_1308` | `gui_ready_standard` | 11 |
| `cytoview_platemap_dv_priority_20_20260709_1308` | `completed_standard_no_gui_analyzer_yet` | 8 |
| `cytoview_platemap_dv_priority_20_20260709_1308` | `standard_failed_sparse_fallback_candidate` | 1 |
| `cytoview_platemap_dv_priority_20_20260709_1311` | `gui_ready_standard` | 12 |
| `cytoview_platemap_dv_priority_20_20260709_1311` | `completed_standard_no_gui_analyzer_yet` | 8 |
| `cytoview_platemap_dv_priority_20_20260709_1330` | `gui_ready_standard` | 11 |
| `cytoview_platemap_dv_priority_20_20260709_1330` | `completed_standard_no_gui_analyzer_yet` | 8 |
| `cytoview_platemap_dv_priority_20_20260709_1330` | `standard_failed_sparse_fallback_candidate` | 1 |
| `cytoview_platemap_dv_priority_20_20260709_1408` | `gui_ready_standard` | 12 |
| `cytoview_platemap_dv_priority_20_20260709_1408` | `completed_standard_no_gui_analyzer_yet` | 8 |
| `cytoview_platemap_dv_priority_10_20260709_1420` | `gui_ready_standard` | 6 |
| `cytoview_platemap_dv_priority_10_20260709_1420` | `completed_standard_no_gui_analyzer_yet` | 4 |
| `cytoview_remaining_all_20260709_0214` | `not_ready_or_not_started` | 108 |

The dorsal/ventral plate-map plan is:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_platemap_dorsal_ventral_priority_20260709.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_platemap_dorsal_ventral_priority_20260709_batch_plan.csv
```

The plan has 90 priority rows: 45 dorsal and 45 ventral. A-row wells are
ventral and B-row wells are dorsal by default; the exact plan CSV should be
preferred when available. A manual correction layer is now applied after the
plan mapping:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_region_overrides_20260709.csv
```

Current correction law: for recordings containing
`h1_134-0150_h1_dorsal_and_ventral_exp17_2(001)`, wells `B1` and `B2` are
final-labeled as `ventral` even though the default B-row rule would label them
as dorsal. This is treated as human-notes ground truth for current Step 1
summaries.

Final priority outcome: `52 / 90` plate-map-backed dorsal/ventral priority
wells are GUI/analyzer-ready, `36 / 90` completed the standard route but did not
produce analyzer/unit assets, and `2 / 90` are sparse Kilosort fallback
candidates. Region split: dorsal `27 / 45` GUI-ready, `18 / 45` completed
without analyzer/unit assets, `0 / 45` sparse failures; ventral `25 / 45`
GUI-ready, `18 / 45` completed without analyzer/unit assets, `2 / 45` sparse
failures.

Current Step 1-only Cytoview dorsal/ventral snapshot was generated with:

```bash
conda run -p /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/envs/axion-kilosort \
  python scripts/build_cytoview_dorsal_ventral_step1_summary.py
```

The script intentionally does not read downstream/IAN master tables. It opens
current GUI-ready Cytoview Step 1 analyzers and computes per-unit `KSLabel`,
firing rate, ISI metrics, best-channel template TTP, and TTP-based
FS/borderline/RS labels directly from Step 1 assets.

Outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_step1_20260709_unit_metrics.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_step1_20260709_well_summary.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_step1_20260709_region_summary.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_step1_20260709_per_well_class_fraction_summary.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_step1_20260709_asset_status.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_step1_20260709_current_good_units.png
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_step1_20260709_provenance.json
```

Current snapshot contents:

| Metric | Value |
|---|---:|
| GUI-ready Cytoview wells scanned | 52 |
| Analyzer load errors | 0 |
| All sorted unit rows measured | 1342 |
| `KSLabel=good` unit rows measured | 237 |
| Region override rules loaded | 2 |
| Unit rows with region override | 156 |
| Ready dorsal wells | 23 |
| Ready ventral wells | 29 |

Current `KSLabel=good` Cytoview regional summary, GUI-ready wells only:

| Region | Good units | Wells | Median firing rate Hz | Mean firing rate Hz | Median ISI ms | Median TTP ms | FS_like | Borderline | RS_like |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dorsal | 113 | 22 | 0.5047 | 0.8129 | 599.84 | 0.88 | 6 | 4 | 103 |
| ventral | 124 | 28 | 1.4010 | 1.7603 | 201.32 | 0.96 | 3 | 9 | 112 |

The unit counts above are pooled across all current `KSLabel=good` units in each
region. The stacked FS/borderline/RS panel in
`cytoview_dorsal_ventral_step1_20260709_current_good_units.png` now uses the
average of per-well proportions with SEM, so each well contributes one
observation to the composition estimate.

Current per-well mean composition:

| Region | Wells with good units | Good units | FS_like mean ± SEM | Borderline mean ± SEM | RS_like mean ± SEM |
|---|---:|---:|---:|---:|---:|
| dorsal | 22 | 113 | 0.0535 ± 0.0246 | 0.0286 ± 0.0164 | 0.9180 ± 0.0327 |
| ventral | 28 | 124 | 0.0298 ± 0.0173 | 0.0563 ± 0.0205 | 0.9139 ± 0.0298 |

Alternate cutoff sensitivity, requested 2026-07-09: separate Step 1-only views
reclassify `KSLabel=good` units as `FS_like` when
`trough_to_peak_duration_ms <= cutoff` and `RS_like` otherwise. This does not
modify the production SpikeTurnpike classifier in the main unit metrics.

Alternate cutoff outputs are now grouped in one folder, with one file set per
cutoff label:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_step1_20260709_ttp_cutoff_sensitivity/
```

Current file sets:

```text
ttp_fs_cutoff_0p50_current_good_units.png
ttp_fs_cutoff_0p50_classified_good_units.csv
ttp_fs_cutoff_0p50_well_summary.csv
ttp_fs_cutoff_0p50_region_summary.csv
ttp_fs_cutoff_0p50_per_well_class_fraction_summary.csv
ttp_fs_cutoff_0p50_class_firing_rate_summary.csv

ttp_fs_cutoff_0p37_current_good_units.png
ttp_fs_cutoff_0p37_classified_good_units.csv
ttp_fs_cutoff_0p37_well_summary.csv
ttp_fs_cutoff_0p37_region_summary.csv
ttp_fs_cutoff_0p37_per_well_class_fraction_summary.csv
ttp_fs_cutoff_0p37_class_firing_rate_summary.csv
```

Each cutoff figure now includes FS/RS firing-rate panels: one panel pooled
across regions and one panel stratified by dorsal/ventral.

Alternate 0.50 ms cutoff pooled counts:

| Region | Good units | FS_like | RS_like | FS_like fraction |
|---|---:|---:|---:|---:|
| dorsal | 113 | 10 | 103 | 0.0885 |
| ventral | 124 | 12 | 112 | 0.0968 |

Alternate 0.50 ms cutoff per-well mean composition:

| Region | Wells with good units | Good units | FS_like mean ± SEM | RS_like mean ± SEM |
|---|---:|---:|---:|---:|
| dorsal | 22 | 113 | 0.0820 ± 0.0327 | 0.9180 ± 0.0327 |
| ventral | 28 | 124 | 0.0861 ± 0.0298 | 0.9139 ± 0.0298 |

Alternate 0.50 ms cutoff firing rate by class:

| Scope | Class | Units | Median FR Hz | Mean FR Hz |
|---|---|---:|---:|---:|
| overall | FS_like | 22 | 0.5454 | 0.9405 |
| overall | RS_like | 215 | 0.8154 | 1.3462 |
| dorsal | FS_like | 10 | 0.4098 | 0.4196 |
| dorsal | RS_like | 103 | 0.5602 | 0.8511 |
| ventral | FS_like | 12 | 1.0997 | 1.3746 |
| ventral | RS_like | 112 | 1.4329 | 1.8016 |

For comparison, the 0.37 ms cutoff file set is also present in the same folder.
With `FS_like = TTP <= 0.37 ms`, pooled counts are dorsal 6 FS/107 RS and
ventral 3 FS/121 RS.

Final Cytoview dorsal/ventral cutoff x alignment composite, generated
2026-07-09 15:31 EDT:

```bash
python scripts/audit_waveform_alignment_before_feature_extraction.py \
  --input-csv /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_step1_20260709_unit_metrics.csv \
  --output-dir /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/waveform_alignment_feature_audit_20260709_cytoview

python scripts/plot_cytoview_dv_alignment_cutoff_composite.py
```

Outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/waveform_alignment_feature_audit_20260709_cytoview/
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dv_alignment_cutoff_composite_20260709/
cytoview_dv_alignment_cutoff_composite_20260709.png
cytoview_dv_alignment_cutoff_composite_20260709_classified_units_long.csv
cytoview_dv_alignment_cutoff_composite_20260709_summary.csv
cytoview_dv_alignment_cutoff_composite_20260709_provenance.json
```

The final PNG is one multi-panel figure with four rows:
`0.37 ms unaligned`, `0.37 ms aligned`, `0.50 ms unaligned`, and
`0.50 ms aligned`. Columns keep the dorsal/ventral logic visible: mean per-well
class fraction by region, unit counts by region/class, TTP distribution by
region, pooled mean/SEM waveforms in uV, individual uV waveforms with the class
mean overlaid, pooled trough-normalized waveforms, dorsal/ventral firing rates
pooled across all good units regardless of FS/RS class, firing rate by
region/class, and half-width versus REP50. The pooled dorsal/ventral firing-rate
column is intentionally class-agnostic: dorsal has `113` good units across
`22` wells with median/mean firing rate `0.5047 / 0.8129 Hz`; ventral has `124`
good units across `28` wells with median/mean firing rate `1.4010 / 1.7603 Hz`.
The mean/SEM uV waveform column preserves the actual best-channel amplitude
scale; the individual uV column shows unit-level spread and outliers with the
class mean on top; the normalized waveform column divides each unit trace by its
own negative trough depth so waveform shape can be compared independent of
amplitude. All four rows use the same `237` Cytoview `KSLabel=good` units from
the 52 GUI-ready priority wells. Dorsal/ventral labels come from the current
Cytoview plate-map plan plus the manual B1/B2 override layer.

Current final composite counts:

| Cutoff | Alignment state | Dorsal FS | Dorsal RS | Ventral FS | Ventral RS |
|---:|---|---:|---:|---:|---:|
| `0.37 ms` | unaligned | 6 | 107 | 3 | 121 |
| `0.37 ms` | aligned | 4 | 109 | 3 | 121 |
| `0.50 ms` | unaligned | 10 | 103 | 12 | 112 |
| `0.50 ms` | aligned | 20 | 93 | 18 | 106 |

Treat this as a current Step 1 readiness/inspection snapshot, not a final
dorsal/ventral biological result. All 90 backed priority wells have drained,
but only the 52 GUI-ready wells have analyzer/unit assets for current Step 1
unit-level summaries; the 36 completed-without-analyzer rows and 2 sparse
failure rows are excluded from unit-level biological plots until usable assets
exist.

### Cytoview B1/B2 Firing-Rate Audit, 2026-07-09

After the current dorsal/ventral snapshot, B1/B2 firing rates were audited
because a mislabeled dorsal/ventral plate or recording was suspected. The audit
confirmed the default plan has no A/B row-rule mismatches, then the manual
override layer was made authoritative for the suspect block. The current
unit-metrics table therefore has four intentional row-rule mismatches:
`134-0150 exp17_2(001)` `B1/B2` in two variants, all final-labeled as ventral.
There are zero unresolved label mismatches after applying this override.

Audit outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_b1_b2_firing_rate_audit_20260709.png
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_b1_b2_firing_rate_audit_20260709_label_validation.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_b1_b2_firing_rate_audit_20260709_well_summary.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_b1_b2_firing_rate_audit_20260709_high_b1_b2_good_units.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_b1_b2_firing_rate_audit_20260709_sensitivity.csv
```

The corrected ventral B1/B2 signal is concentrated in one recording block:

```text
plate_id=134-0150
recording contains h1_134-0150_h1_dorsal_and_ventral_exp17_2(001)
wells B1 and B2
```

Top B1/B2 examples from this block:

| Recording block | Well | Variant | Good units | Median FR Hz | Mean FR Hz | Max FR Hz |
|---|---|---|---:|---:|---:|---:|
| `134-0150 exp17_2(001)` | B2 | primary raw | 10 | 1.8590 | 3.5266 | 11.9559 |
| `134-0150 exp17_2(001)` | B2 | filter 200 Hz-3 kHz | 4 | 2.6138 | 2.8661 | 6.1113 |
| `134-0150 exp17_2(001)` | B1 | filter 200 Hz-3 kHz | 6 | 0.8220 | 1.5747 | 4.9763 |
| `134-0150 exp17_2(001)` | B1 | primary raw | 12 | 1.5030 | 1.8933 | 3.7906 |

Sensitivity check after applying the override:

| Scenario | Dorsal good units | Dorsal median FR Hz | Dorsal mean FR Hz | Ventral good units | Ventral median FR Hz | Ventral mean FR Hz |
|---|---:|---:|---:|---:|---:|---:|
| Current GUI-ready snapshot after override | 73 | 0.4034 | 0.6907 | 91 | 1.4105 | 1.7765 |
| Exclude `134-0150 exp17_2(001)` B1/B2 | 73 | 0.4034 | 0.6907 | 59 | 1.3642 | 1.4028 |
| Exclude entire `134-0150 exp17_2(001)` recording | 60 | 0.3309 | 0.5049 | 47 | 1.3413 | 1.3622 |

Interpretation for now: the active Step 1 truth is that
`134-0150 exp17_2(001)` `B1/B2` are ventral. Do not interpret those wells as
dorsal in Cytoview dorsal/ventral summaries unless the override CSV is
explicitly changed.

### Same-Well Hybrid Spatial QC Smoke Test, 2026-07-09

The existing same-well `spatial_isolation_1x3` code was extended with a new
`hybrid_qc` layout and smoke-tested on only the current Cytoview ventral B2
example. This is not a new unit-selection pass.

Output root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_spatial_isolation_hybrid_qc_20260709_195500/
```

Exact smoke-test population:

```text
selection_group=cytoview_ventral
well=B2
units=8;11;30
```

The new figure contains a combined same-well physical electrode map, per-unit
local multichannel waveform footprints, per-unit autocorrelograms, and per-unit
sampled best-channel spike-PTP stability. Display normalization is one scale
factor per unit, the absolute best-channel template PTP; channels are not
independently normalized and polarity is preserved.

Companion-manifest audit:

| Unit | Spike count | Best channel | Local channel IDs | Best-channel PTP uV |
|---:|---:|---:|---|---:|
| 8 | 1932 | 50 | `50;51;42;49;58;57;41;43;59` | 53.402 |
| 11 | 3930 | 28 | `28;29;20;27;36;19;35;21;37` | 14.218 |
| 30 | 663 | 53 | `53;54;45;52;61;60;44;46;62` | 19.457 |

Panel D uses persisted `random_spikes` snippets and computes best-channel PTP in
uV. The analyzer has `spike_amplitudes` with `peak_sign='neg'`, but that was not
used because it is not the positive/negative-safe PTP measurement requested for
this QC view. The previous `spatial_isolation_1x3_20260709_183800` output root
was not overwritten.

#### Hybrid Spatial QC v2, 2026-07-09

The same Cytoview ventral B2 hybrid QC example was revised without changing the
selected units, data source, colors, or calculations. The v2 files use a new
suffix and a new output root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_spatial_isolation_hybrid_qc_v2_20260709_203000/
```

V2 keeps the original units `8;11;30` and improves row B local waveform
visibility using horizontal multiplier `1.2`, base vertical multiplier `1.75`,
and auto-selected uniform local waveform display gain `1.527973` after the same
one-per-unit best-channel PTP normalization. Neighboring channels are not
independently normalized and relative channel amplitudes are preserved. Row C
remains the raw-count ACG, row D is now `Autocorrelogram — probability` with
dashed `-2 ms` and `+2 ms` boundary lines, and row E is amplitude stability.

Probability ACG normalization:

```text
p_i = count_i / sum(count_j for displayed bins j with center != 0 ms)
```

Validation from the v2 companion manifest:

| Unit | Probability sum over displayed nonzero bins | P(abs lag <= 2 ms) |
|---:|---:|---:|
| 8 | 1.000 | 0.001621 |
| 11 | 1.000 | 0.014843 |
| 30 | 1.000 | 0.000000 |

The original hybrid v1 root
`representative_units_20260709_spatial_isolation_hybrid_qc_20260709_195500`
was not overwritten.

#### Hybrid Spatial QC Strategic Review Pack, 2026-07-09

A broader review pack was rendered to support choosing final same-well examples
across Lumos, Cytoview dorsal, and Cytoview ventral.

Output root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/representative_units_20260709_spatial_isolation_hybrid_qc_v2_review_20260709_194340/
```

Scope: existing Wave C selected wells only, with top `3` same-well unit
combinations per selected well under the existing spatial-isolation score. The
run produced `36` panels total: `12` Lumos, `12` Cytoview dorsal, and `12`
Cytoview ventral, with `0` render errors. Each panel was exported as PNG, PDF,
and SVG.

Contact sheets for quick inspection:

```text
lumos_hybrid_qc_v2_review_contact_sheet.jpg
cytoview_dorsal_hybrid_qc_v2_review_contact_sheet.jpg
cytoview_ventral_hybrid_qc_v2_review_contact_sheet.jpg
```

The probability-normalized ACG row now uses a unit-color line with translucent
area fill. The displayed line uses only a one-bin-neighbor `[1, 2, 1] / 4`
smoothing kernel so it remains close to the raw binned shape. The raw-count ACG
row remains a bar plot. The probability normalization and manifest values are
still computed from the unsmoothed displayed-bin probabilities.

SVG export note: `scripts/plot_spatial_isolation_1x2_panels.py` now preserves
SVG text as editable `<text>` elements by setting `svg.fonttype = none` and
requests `Arial` first in the sans-serif font list, followed by `Nimbus Sans`,
`Helvetica`, and `DejaVu Sans`. The current system maps Arial to Nimbus Sans,
but Illustrator should now see editable text objects and can substitute Arial.
SVG-only rerenders completed for the good-unit review root and the
noise-comparator review root with `36` panels and `0` errors in each.

### Testing MEA Transient Plateing Recording-Series Rerun, 2026-07-09

The `Testing_mea_transient_plateing/134-0150/My Experiment(000..004)` block was
rerun in the current `step1_nonlfp_th5` parameter context after confirming that
the earlier `sixwell_manual_primary_*` outputs are historical only and should
not be treated as current Step 1 truth.

Scope and interpretation:

- Submitted 5 recordings x 6 wells = 30 Cytoview/SixWell AIND jobs.
- These recordings are not part of the dorsal/ventral plate-map analysis.
- Treat them as a separate recording-series cohort for comparisons across
  sequential recordings/timepoints only.
- Do not include these rows in dorsal-vs-ventral summaries unless external
  metadata later supplies a region label.

Submitted wave label:

```text
cytoview_recording_series_no_region_testing_mea_transient_20260709
```

Submitted job IDs:

```text
53220086-53220115
```

Submission source ledger:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/step1_v5_well_ground_truth.csv
```

Submission ledger:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/submitted_step1_v5_ground_truth_waves.tsv
```

The submission helper now supports targeted filters:

```bash
conda run -p /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/envs/axion-kilosort \
  python scripts/submit_next_step1_v5_ground_truth_wave.py \
  --status not_ready_or_not_started \
  --plate-family cytoview_6well \
  --recording-contains 'Testing_mea_transient_plateing_134-0150_My_Experiment' \
  --limit 30 \
  --allow-resubmit \
  --wave-label cytoview_recording_series_no_region_testing_mea_transient_20260709 \
  --sbatch-time 12:00:00 \
  --submit
```

Initial queue check immediately after submission showed all 30 jobs pending for
priority.

### Testing MEA Transient Plateing A3 Repeated-Recording Stability Figure, 2026-07-09

This is a separate figure lane from the finalized Lumos/dorsal/ventral hybrid
QC package.

User request:

- Use `Testing_mea_transient_plateing/134-0150/My Experiment(000..004).raw`.
- Treat the block as a repeated-recording/stability cohort, not as
  dorsal/ventral biology.
- Focus first on numeric well `3`.
- Find the best single-unit candidates that appear trackable across repeated
  recordings and plot whether the apparent same unit remains stable over time.

Current well-number assumption:

```text
1=A1, 2=A2, 3=A3, 4=B1, 5=B2, 6=B3
```

Under that assumption, numeric well `3` is `A3`. This assumption is written
into the output provenance and availability CSV so it can be changed later if
the wet-lab well numbering used a different convention.

Script:

```text
scripts/plot_recording_series_unit_stability.py
```

Command used:

```bash
source config/greatlakes_project.env
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
python scripts/plot_recording_series_unit_stability.py \
  --well-number 3 \
  --top-chains 3 \
  --export-formats png,pdf,svg
```

Data source:

- Current `step1_nonlfp_th5` SpikeInterface sorting analyzers only.
- Historical `sixwell_manual_primary_*` outputs were not used.
- `KSLabel=good` is the candidate-unit ground truth filter.
- Saved analyzer assets reused: `templates`, `spike_amplitudes`,
  `correlograms`, `random_spikes`, `unit_locations`, and sorting properties.

A3 current-analyzer availability:

| Repeat | A3 current analyzer | Duration | Sampling rate | Total units | KSLabel=good units |
|---|---|---:|---:|---:|---:|
| `000` | no |  |  |  |  |
| `001` | no |  |  |  |  |
| `002` | yes | `653.75 s` | `12500 Hz` | `42` | `15` |
| `003` | yes | `866.25 s` | `12500 Hz` | `41` | `11` |
| `004` | yes | `600.00 s` | `12500 Hz` | `39` | `15` |

Because A3 does not have current analyzers for `000` or `001`, the first A3
stability figure compares only repeats `002`, `003`, and `004`. Do not backfill
`000/001` from historical outputs unless this is explicitly chosen later.

Matching logic:

- Candidate units are restricted to `KSLabel=good`.
- Units are grouped only when the best-channel electrode is exactly the same
  across all usable repeats.
- Candidate chains are ranked by absolute cosine similarity of the normalized
  best-channel template waveform.
- Figure-selected chains must pass:
  - minimum pairwise waveform similarity `>= 0.40`
  - firing-rate coefficient of variation `<= 0.80`
  - best-channel PTP coefficient of variation `<= 1.00`
  - maximum saved `ContamPct <= 20`
- These criteria identify putative same-channel/same-unit candidates for visual
  inspection; they do not prove biological identity.

Outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/transient_plateing_1340150_recording_series_stability_20260709/
```

Files:

```text
transient_plateing_A3_putative_same_unit_stability_20260709.png
transient_plateing_A3_putative_same_unit_stability_20260709.pdf
transient_plateing_A3_putative_same_unit_stability_20260709.svg
transient_plateing_A3_recording_series_availability_20260709.csv
transient_plateing_A3_good_unit_inventory_20260709.csv
transient_plateing_A3_putative_same_channel_chains_20260709.csv
transient_plateing_A3_recording_series_provenance_20260709.json
```

First-pass A3 figure selection:

| Selected chain | Best channel | Unit IDs across `002;003;004` | Mean waveform similarity | Min waveform similarity | FR values (Hz) | PTP values (uV) | Comment |
|---:|---:|---|---:|---:|---|---|---|
| 1 | `45` | `1;32;34` | `0.709` | `0.595` | `0.405;0.425;0.237` | `0.520;1.396;0.871` | strongest A3 candidate |
| 2 | `45` | `2;12;7` | `0.581` | `0.442` | `0.421;0.414;0.425` | `1.103;0.461;5.658` | FR-stable but amplitude/PTP shifts strongly in `004`; inspect cautiously |

The SVG output was verified to contain editable `<text>` elements and requests
Arial first in the font family, matching the final hybrid QC export behavior.

### Testing MEA Transient Plateing Priority-Well Scan, 2026-07-09

Follow-up question:

1. Is there a well with more usable repeated recordings than A3?
2. Is there a `KSLabel=good` unit candidate that can be tracked across all of
   those usable repeats?
3. Avoid relying on the downstream transformed spike-metric manifest because
   those metrics are not yet unified with this repeated-recording manifest.

Answer:

- No well has all five repeats `000..004` in current Step 1 analyzer form.
  Repeat `001` has no usable current analyzer for any well.
- `B2` and `A2` are the highest-priority wells because both have four current
  Kilosort/Step 1 repeats: `000`, `002`, `003`, and `004`.
- `B2` is priority one because it has the larger good-unit pool and the cleaner
  four-repeat selected chain.
- `A2` is priority two because it also has a four-repeat `KSLabel=good` chain,
  but the selected chain has a large PTP increase in repeat `004`.

All-well audit outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/transient_plateing_1340150_recording_series_stability_20260709/transient_plateing_all_wells_current_step1_availability_20260709.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/transient_plateing_1340150_recording_series_stability_20260709/transient_plateing_all_wells_priority_summary_20260709.csv
```

Priority summary:

| Rank | Well | Usable repeats | Missing repeats | Good units across usable repeats | Selected units | Best channel | Mean similarity | Min similarity | FR values (Hz) | PTP values (uV) | Comment |
|---:|---|---|---|---:|---|---:|---:|---:|---|---|---|
| 1 | `B2` | `000;002;003;004` | `001` | `71` | `34;31;36;22` | `21` | `0.947` | `0.888` | `0.422;0.564;1.336;0.978` | `4.893;5.051;5.179;5.167` | cleanest four-repeat candidate; PTP CV `0.023` |
| 2 | `A2` | `000;002;003;004` | `001` | `61` | `41;40;41;25` | `15` | `0.987` | `0.975` | `0.687;0.904;1.385;2.110` | `4.784;5.235;5.948;18.687` | waveform similarity is high, but repeat `004` PTP jumps; inspect cautiously |
| 3 | `A3` | `002;003;004` | `000;001` | `41` | `1;32;34` | `45` | `0.709` | `0.595` | `0.405;0.425;0.237` | `0.520;1.396;0.871` | three-repeat candidate only |

Figures added:

```text
transient_plateing_B2_putative_same_unit_stability_20260709.png/pdf/svg
transient_plateing_A2_putative_same_unit_stability_20260709.png/pdf/svg
```

Spike-source guardrail:

- This audit does not consume the downstream transformed spike-metric manifest.
- Firing rates are computed directly from each current analyzer's
  `sorting.to_spike_vector()` and recording duration.
- Candidate matching uses saved analyzer templates and `KSLabel=good` sorting
  properties.
- Saved `spike_amplitudes` are displayed only as analyzer-backed stability
  summaries. They are not mixed with transformed downstream spike metrics.

Best-unit-only figure:

The broad screening layout was too cluttered for presentation, and the
same-channel rule was too strict because the apparent unit may drift across
neighboring electrodes over time. The current clean figure uses evenly spaced
repeats `000`, `002`, and `004` only, skipping `003` for temporal spacing and
omitting `001` because no current analyzer exists. It allows local best-channel
drift up to `500 um`.

Current selected B2 chain after stability-weighted reranking:

| Repeat | Unit | Best channel | Waveform source |
|---|---:|---:|---|
| `000` | `53` | `30` | aligned persisted `random_spikes` snippet mean |
| `002` | `52` | `30` | aligned persisted `random_spikes` snippet mean |
| `004` | `12` | `30` | aligned persisted `random_spikes` snippet mean |

Summary: mean/min waveform similarity `0.978 / 0.966`, maximum best-channel
drift `0 um`, firing-rate CV `0.094`, PTP CV `0.124`.

Selection note:

The earlier drift-tolerant pick (`34;16;22`, channels `21;28;21`) was selected
because waveform similarity dominated the ranking, but it had a firing-rate CV
of `0.520`. The current selection uses `stability_selection_score`, which keeps
waveform similarity high while penalizing firing-rate instability, PTP
instability, contamination, and spatial drift.

```text
transient_plateing_B2_best_unit_stability_20260709.png
transient_plateing_B2_best_unit_stability_20260709.pdf
transient_plateing_B2_best_unit_stability_20260709.svg
```

Render command:

```bash
python scripts/plot_recording_series_unit_stability.py \
  --well B2 \
  --include-repeats 000,002,004 \
  --top-chains 1 \
  --best-unit-only \
  --matching-mode spatial_drift \
  --max-best-channel-drift-um 500 \
  --export-formats png,pdf,svg
```

Direct trace expansion, 2026-07-09 21:12 EDT:

- The same B2 best-unit figure now includes a bottom row with direct continuous
  channel data from best channel `30` for repeats `000`, `002`, and `004`.
- The trace is extracted from the current Step 1 analyzer recording with
  `analyzer.recording.get_traces(return_in_uV=True)`, so it is the same
  `Neural Spikes` stream used for Kilosort: `200 Hz IIR` high pass and
  `3 kHz Kaiser Window` low pass.
- The upper waveform overlay and local-footprint panels are unchanged: they are
  aligned persisted `random_spikes` snippet means, not raw template glyphs.
- The raw metadata inventory is used only for acquisition timing:
  `/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_20260708_filter_metadata_patch/raw_files.csv`.
- The short `60.0-61.0 s` trace window was removed. The plotted trace now spans
  the entire continuous channel recording for each displayed repeat: `900.00 s`
  for repeat `000`, `653.75 s` for repeat `002`, and `600.00 s` for repeat
  `004`.
- The trace display is now three long, full-width panels stacked vertically
  under the stability metrics, not three small side-by-side panels.
- Each full recording is represented in the figure as a `3,000`-bin min/max
  envelope computed from all source samples. This preserves the full time span
  while keeping PNG/PDF/SVG exports usable.
- The trace display is not time-locked. The only alignment is acquisition order:
  repeat `000`, then repeat `002`, then repeat `004`. Each stacked row uses its
  own x-axis in minutes within that recording. Row-label timing is contextual
  only, not a shared aligned time axis.
- Row timing now uses repeat `000` as timepoint one/reference. Row labels are:
  repeat `000` starts `+0.0 min`, repeat `002` starts `+23.5 min`, and repeat
  `004` starts `+173.1 min` from the repeat `000` raw start.
- Red tick marks above each voltage trace are the plotted unit's exact
  SpikeInterface/Kilosort spike times from `sorting.get_unit_spike_train(...)`,
  converted to minutes within that recording. Tick counts match the selected
  unit spike counts: `261` for repeat `000` unit `53`, `238` for repeat `002`
  unit `52`, and `207` for repeat `004` unit `12`.
- Each trace row now has a compact ACG panel immediately to the right. The ACG
  uses the same plotted-unit spike times as the red ticks, with `1 ms` bins over
  a `+/-100 ms` lag window and self-lags excluded. The center/self bin is `0` by
  construction.
- All three stacked trace panels share the same voltage y-limits computed from
  the full min/max envelope across all traces, with padding. The earlier
  percentile-style display limit was removed so voltage extrema are not clipped.

Elapsed acquisition timing:

| Repeat | Raw start time | Elapsed from repeat `000` |
|---|---|---:|
| `000` | `2026-05-23 10:08:59.034` | `0.000 h` |
| `002` | `2026-05-23 10:32:28.627` | `0.392 h` |
| `004` | `2026-05-23 13:02:08.023` | `2.886 h` |

New sidecar output:

```text
transient_plateing_B2_best_unit_direct_channel_trace_20260709.csv.gz
transient_plateing_B2_best_unit_direct_channel_spike_ticks_20260709.csv
transient_plateing_B2_best_unit_direct_channel_acg_20260709.csv
```

The sidecar has `9,000` envelope rows and records repeat, unit, channel, plotted
bin time in recording, plotted minutes from repeat `000`, bin min/max/mean
voltage in uV, raw samples represented per bin, full source sample count, raw
acquisition start time, reference repeat/time, elapsed hours, raw file path, and
filter metadata signature. The spike-tick sidecar stores exact tick times in
seconds/minutes within each recording. The ACG sidecar stores the plotted
lag-bin counts for the right-hand ACG panels.

### Testing MEA Transient Plateing Top-10 ACG Example Pack, 2026-07-09

The best-unit recording-series figure was generalized into a contained top-10
rendering pass so multiple candidate chains can be inspected in the same final
layout. This pass keeps the final B2 figure style: aligned random-spike
best-channel waveform overlay, local multichannel footprint panels, stability
metrics, full continuous voltage traces stacked by repeat order, red spike
ticks on the traces, and an ACG panel beside each trace row.

Top-10 output root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/transient_plateing_top_acg_examples_20260709/
```

Script:

```text
scripts/prepare_recording_series_top_acg_examples.py
```

Reproducibility assets:

```text
top_acg_candidate_manifest.csv
all_ranked_candidates.csv
top_acg_rendered_output_summary.csv
top10_acg_examples_contact_sheet.png
submission.json
repro/render_top_acg_commands.tsv
repro/render_top_acg_examples.sbatch
logs/
```

Slurm history:

| Job | State | Note |
|---:|---|---|
| `53227028` | cancelled/failed early | First array hit the known conda activation problem under `set -u`: `xml_catalog_files_libxml2: unbound variable`. No figure outputs were produced from this failed array. |
| `53227050` | completed | Corrected array used `set -eo pipefail` so conda activation could complete; all 10 candidate figures and sidecars rendered. |

Candidate ranking:

- Candidate chains came from the existing repeated-recording chain tables in
  `transient_plateing_1340150_recording_series_stability_20260709`.
- The ranking keeps `KSLabel=good` analyzer units and the same waveform
  extraction/display logic as the final B2 figure.
- Candidates are filtered for at least 3 repeats, minimum waveform similarity,
  firing-rate CV, and PTP CV, then ranked to favor enough spikes for a visible
  ACG while preserving waveform/stability quality.
- The repeated recordings are shown in acquisition order only. The traces are
  not time-locked; repeat `000` is the timing reference for row labels.

Rendered top-10 candidates:

| Rank | Well | Units across repeats | Best channels | Tick counts `000;002;004` | ACG counts `000;002;004` | Near-2 ms ACG fraction `000;002;004` |
|---:|---|---|---|---|---|---|
| 1 | `B2` | `16;16;22` | `28;28;21` | `893;1149;587` | `1954;4224;920` | `0.0061;0.0080;0.0065` |
| 2 | `B2` | `16;31;22` | `28;21;21` | `893;369;587` | `1954;252;920` | `0.0061;0.0079;0.0065` |
| 3 | `B2` | `31;7;24` | `36;29;37` | `517;1484;2793` | `72;5732;8034` | `0.0000;0.0080;0.0087` |
| 4 | `B2` | `31;26;24` | `36;37;37` | `517;1723;2793` | `72;8078;8034` | `0.0000;0.0089;0.0087` |
| 5 | `B2` | `34;16;22` | `21;28;21` | `380;1149;587` | `212;4224;920` | `0.0094;0.0080;0.0065` |
| 6 | `B2` | `51;26;24` | `36;37;37` | `447;1723;2793` | `30;8078;8034` | `0.0000;0.0089;0.0087` |
| 7 | `B2` | `51;7;24` | `36;29;37` | `447;1484;2793` | `30;5732;8034` | `0.0000;0.0080;0.0087` |
| 8 | `B2` | `34;31;22` | `21;21;21` | `380;369;587` | `212;252;920` | `0.0094;0.0079;0.0065` |
| 9 | `B2` | `55;26;24` | `44;37;37` | `422;1723;2793` | `44;8078;8034` | `0.0000;0.0089;0.0087` |
| 10 | `A2` | `41;40;18` | `15;15;15` | `618;591;449` | `1004;1132;72` | `0.0080;0.0141;0.0000` |

Each rank writes:

```text
transient_plateing_<WELL>_best_unit_stability_rank##_..._20260709_top_acg.png
transient_plateing_<WELL>_best_unit_stability_rank##_..._20260709_top_acg.pdf
transient_plateing_<WELL>_best_unit_stability_rank##_..._20260709_top_acg.svg
transient_plateing_<WELL>_best_unit_direct_channel_trace_rank##_..._20260709_top_acg.csv.gz
transient_plateing_<WELL>_best_unit_direct_channel_spike_ticks_rank##_..._20260709_top_acg.csv
transient_plateing_<WELL>_best_unit_direct_channel_acg_rank##_..._20260709_top_acg.csv
transient_plateing_<WELL>_recording_series_provenance_rank##_..._20260709_top_acg.json
```

Use `top10_acg_examples_contact_sheet.png` for a quick screen of all 10, then
open the per-rank PNG/PDF/SVG for detailed inspection.
