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
```

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

## Step 1 Ground Truth Snapshot, 2026-07-09 14:13 EDT

Use this Step 1 ledger as the current single source of truth for what is ready,
running, failed, or still not started:

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
| `gui_ready_standard` | 39 |
| `completed_standard_no_gui_analyzer_yet` | 29 |
| `running_standard` | 10 |
| `not_ready_or_not_started` | 118 |
| `standard_failed_sparse_fallback_candidate` | 2 |

Interpretation: Cytoview/SixWell is the dorsal/ventral Step 1 track. Do not use
Lumos opto assumptions here. The current biological Step 1 summaries should use
`KSLabel=good` units, TTP-based FS/borderline/RS designation, firing rate, and
ISI metrics computed directly from Step 1 SortingAnalyzer spike trains/templates.

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
| `cytoview_platemap_dv_priority_20_20260709_1408` | `gui_ready_standard` | 5 |
| `cytoview_platemap_dv_priority_20_20260709_1408` | `completed_standard_no_gui_analyzer_yet` | 5 |
| `cytoview_platemap_dv_priority_20_20260709_1408` | `running_standard` | 10 |
| `cytoview_remaining_all_20260709_0214` | `not_ready_or_not_started` | 118 |

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
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_step1_20260709_asset_status.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_step1_20260709_current_good_units.png
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dorsal_ventral_step1_20260709_provenance.json
```

Current snapshot contents:

| Metric | Value |
|---|---:|
| GUI-ready Cytoview wells scanned | 39 |
| Analyzer load errors | 0 |
| All sorted unit rows measured | 870 |
| `KSLabel=good` unit rows measured | 164 |
| Region override rules loaded | 2 |
| Unit rows with region override | 156 |
| Ready dorsal wells | 17 |
| Ready ventral wells | 22 |

Current `KSLabel=good` Cytoview regional summary, GUI-ready wells only:

| Region | Good units | Wells | Median firing rate Hz | Mean firing rate Hz | Median ISI ms | Median TTP ms | FS_like | Borderline | RS_like |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dorsal | 73 | 16 | 0.4034 | 0.6907 | 548.32 | 0.96 | 4 | 3 | 66 |
| ventral | 91 | 21 | 1.4105 | 1.7765 | 197.20 | 1.04 | 3 | 8 | 80 |

Treat this as a current Step 1 readiness/inspection snapshot, not a final
dorsal/ventral biological result, because additional Cytoview wells are still
running or not yet GUI-ready.

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
