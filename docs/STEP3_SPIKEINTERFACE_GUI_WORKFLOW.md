# Step 3 SpikeInterface GUI Workflow

Date verified: 2026-07-08

## Purpose

This document defines the supported workflow for opening completed Step 1 AIND
`SortingAnalyzer` outputs in the SpikeInterface GUI from Great Lakes while
displaying the interface locally on a Mac. It covers two modes:

1. Early Step 1 per-well inspection during pipeline scale-up.
2. Later Step 3 manual curation after the downstream analysis dataset exists.

Step 1 remains frozen. The GUI workflow must not rerun Axion export, NWB export,
SpikeInterface prep, Kilosort4, AIND postprocessing, or Step 2 classification.
It starts from existing Step 1 analyzer outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/<recording>/<well>/postprocessed/block0_None_recording1.zarr
```

## Early Step 1 GUI Mode During Scale-Up

The old GUI workflow assumed that Step 1, Step 2, and Step 3 had all completed.
That is no longer the only supported path. During the TH=5 Step 1 scale-up, GUI
inspection can begin as soon as an individual well has completed Step 1 and has a
finalized per-well analyzer:

```text
results/aind/<recording>/<well>/postprocessed/block0_None_recording1.zarr
```

Per-well Step 1 completion is enough for early manual curation/QC. The full
recording does not need to be complete, and Step 2/Step 3 do not need to exist
yet.

Use this mode to inspect Kilosort output and export manual curation decisions
while the larger Step 1 submission is still scaling. Do not use this mode to
claim that the recording-level pipeline, Step 2 metadata recovery, or Step 3
master unit table is complete.

Important boundaries:

- Only wells with a completed Step 1 analyzer can be opened.
- Wells that failed standard KS4 because of sparse template-learning clips must
  complete the labeled fallback route before they are treated as completed Step 1
  wells.
- Manual curation output must be saved outside the frozen Step 1 analyzer.
- The Step 1 analyzer itself must not be modified.

Preferred launcher for this early mode:

```bash
cd /home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
source config/greatlakes_project.env
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"

python scripts/launch_step1_sorting_analyzer_browser.py \
  --root-folder /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind \
  --recording-prefix step1_nonlfp_th5_20260708_ \
  --curation-root /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/step1_gui_curation \
  --address localhost \
  --port 18765
```

Recommended early Step 1 curation root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/step1_gui_curation/<recording>/<well>/
```

The `--recording-prefix` filter is important during reruns because the shared
`results/aind` root also contains older analyzers. For the 2026-07-08 TH=5
rerun, completed wells are appearing under recording folders that begin with
`step1_nonlfp_th5_20260708_`; the browser should list only wells from those
folders while Step 1 is still partially complete.

The browser prints and displays the active assumptions when it starts:

- review only completed per-well Step 1 analyzers,
- do not assume Step 2, Step 3, or full recording completion,
- save decisions with `Save curation`, which writes external JSON under
  `results/step1_gui_curation`,
- use `Download JSON` only as an optional browser copy; the launcher redirects
  that export to the same external JSON path instead of a repo-local
  `curation.json`,
- keep saved decisions as per-well review notes until the rerun finishes.

The default layout groups the detailed unit-shape evidence along the bottom:
`waveform`, `maintemplate`, and `correlogram`/`isi`. The top row keeps the
curation table, unit list, merge list, traces, probe, similarity, and settings
available for context.

## Runtime Boundary

There are two separate Great Lakes runtime lanes:

1. AIND/Nextflow pipeline lane.
   The `.img` files under the Turbo container directory are for running AIND
   pipeline stages through Nextflow/Singularity.

   Current AIND images include:

   ```text
   /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/containers/aind_ephys/ghcr.io-allenneuraldynamics-aind-ephys-pipeline-base-si-0.104.8.img
   /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/containers/aind_ephys/ghcr.io-allenneuraldynamics-aind-ephys-pipeline-nwb-si-0.104.8.img
   /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/containers/aind_ephys/ghcr.io-allenneuraldynamics-aind-ephys-spikesort-kilosort4-si-0.104.8.img
   ```

2. Interactive analysis lane.
   The SpikeInterface GUI should run from the Turbo-backed Great Lakes conda
   environment:

   ```text
   /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/envs/axion-kilosort
   ```

   This env currently imports `spikeinterface==0.104.8`, matching the AIND
   Step 1 outputs. Use this conda env for Step 1 GUI inspection, Step 3
   curation export, and downstream analysis, not the pipeline `.img` files.

## Pre-Install Verification

The existing env was checked before installing `spikeinterface-gui`.

Current installed state:

```text
spikeinterface: present
spikeinterface_version: 0.104.8
spikeinterface_gui: absent
panel: absent
bokeh: absent
PySide6: absent
PyQt5: present
```

`pip check` reported:

```text
No broken requirements found.
```

Resolver dry-runs succeeded for both supported GUI extras:

```bash
python -m pip install --dry-run --report /tmp/spikeinterface_gui_web_dryrun.json 'spikeinterface-gui[web]'
python -m pip install --dry-run --report /tmp/spikeinterface_gui_desktop_dryrun.json 'spikeinterface-gui[desktop]'
```

Important dependency result:

- `spikeinterface-gui==0.13.1` requires Python `>=3.10`.
- It requires `spikeinterface[full]>=0.104.0`.
- The current env already satisfies `spikeinterface>=0.104.0` with
  `spikeinterface==0.104.8`; the resolver did not need to upgrade it.
- The web extra adds `panel`, `bokeh`, and related web packages.
- The desktop extra adds `PySide6` and `pyqtgraph`.

Conclusion: no resolver-level incompatibility was found with the current Step 3
conda environment. Prefer the web extra for remote Mac display.

## Analyzer Compatibility

Representative Step 1 analyzers loaded directly from Turbo in the current conda
env before GUI installation:

```text
Lumos A3:
  path:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/6_22_2026_129-8445_ventral_sosrs_opsin_day3(003)_FortyEightWellLumos_primary_raw_NeuralBroadband/A3/postprocessed/block0_None_recording1.zarr
  units: 46
  channels: 16
  recording class: BinaryFolderRecording
  sampling rate: 12500.0 Hz
  duration: 600.0 s
  loaded extensions: correlograms, random_spikes, templates

SixWell A1:
  path:
    /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/sixwell_manual_primary_5_25_26_pvreporter_134-0150_pv_reporter_cl32_dorsal_and_ventral_exp17(000)/A1/postprocessed/block0_None_recording1.zarr
  units: 82
  channels: 64
  recording class: BinaryFolderRecording
  sampling rate: 12500.0 Hz
  duration: 600.0 s
  loaded extensions: correlograms, random_spikes, templates
```

Load command:

```python
import spikeinterface.full as si

analyzer = si.load_sorting_analyzer(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/<recording>/<well>/postprocessed/block0_None_recording1.zarr"
)
```

Conclusion: the GUI can directly open the frozen Step 1 analyzer Zarr folders,
because the same SpikeInterface loader can open them in the Step 3 env.

## Recording Access

The Step 1 analyzers contain recording references. For the checked Lumos A3
analyzer, the recording object was:

```text
BinaryFolderRecording
```

with a Turbo-backed folder reference:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/scratch/aind_nextflow/.../capsule/results/preprocessed_block0_None_recording1
```

A 10-frame, 2-channel trace read succeeded directly from that reference:

```text
tiny_traces_shape: (10, 2)
tiny_traces_dtype: int16
```

Conclusion: the GUI can lazily access the Turbo-backed recording data through
the analyzer's recording reference. No data copy is required for normal
inspection. This depends on the referenced Turbo scratch recording folders
remaining available. If a referenced recording folder is later removed, launch
with `--no-traces` or provide a replacement recording path explicitly.

## Frozen Output Rule For Curation

Do not use the GUI's built-in `Save in analyzer` action on Step 1 analyzers.

Reason: for Zarr analyzers, `spikeinterface_gui` opens the analyzer in write
mode and stores curation data inside the analyzer under a `spikeinterface_gui`
Zarr group/attribute. That would modify the frozen Step 1 output.

Supported save policy:

- For early Step 1 per-well inspection, prefer
  `scripts/launch_step1_sorting_analyzer_browser.py`, which writes curation JSON
  outside the analyzer under `results/step1_gui_curation`.
- For later Step 3 curation of one selected analyzer, prefer
  `scripts/launch_step3_spikeinterface_gui.py`, which uses the GUI's supported
  `curation_callback` hook to write manual curation JSON outside the analyzer.
- The GUI's JSON export/download action is also acceptable for manual curation
  output.
- Store curation JSON outside Step 1. Use `results/step1_gui_curation` for early
  scale-up inspection and `results/step3_gui_curation` for finalized downstream
  curation.

Recommended external curation root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/step1_gui_curation/<recording>/<well>/
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/step3_gui_curation/<recording>/<well>/
```

Recommended curation JSON filename:

```text
curation_<recording>_<well>.json
```

## Display Recommendation

Recommended: web backend through SSH port forwarding.

Do not use X11 forwarding as the default workflow. The desktop backend is
supported by `spikeinterface-gui[desktop]`, but it requires a remote Qt stack
and X11 forwarding from Great Lakes to macOS. That is heavier, more fragile, and
slower for this use case.

The web backend is supported by the GUI API and CLI:

```text
sigui <analyzer_folder> --mode web --address localhost --port <port>
```

Use SSH tunneling from the Mac to view the Great Lakes Panel/Bokeh server in a
local browser.

## One-Time Install

After the dry-run verification, install the web GUI extra into the existing
Turbo conda env:

```bash
cd /home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
source config/greatlakes_project.env
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
python -m pip install 'spikeinterface-gui[web]'
python -m pip check
```

This intentionally installs into the Step 3 conda env, not into an AIND
pipeline image.

## Launch Workflow

On the Mac, open an SSH tunnel to Great Lakes:

```bash
ssh -L 18765:localhost:18765 <uniqname>@greatlakes.arc-ts.umich.edu
```

In the Great Lakes shell reached by that SSH session:

```bash
cd /home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
source config/greatlakes_project.env
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"

ANALYZER='/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind/6_22_2026_129-8445_ventral_sosrs_opsin_day3(003)_FortyEightWellLumos_primary_raw_NeuralBroadband/A3/postprocessed/block0_None_recording1.zarr'

python scripts/launch_step3_spikeinterface_gui.py "${ANALYZER}" \
  --address localhost \
  --port 18765
```

Then open this local URL on the Mac:

```text
http://localhost:18765
```

In the GUI, use `Save curation`; the launcher writes the JSON to the Step 3
curation root printed at startup. Do not use raw `sigui --curation` as the
primary curation workflow unless you are using only the JSON download/export
button and avoiding `Save in analyzer`.

## Launcher Mode For Multiple Wells

To browse all analyzers under the Step 1 AIND results root:

```bash
sigui \
  --root-folder /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind \
  --mode web \
  --address localhost \
  --port 18765 \
  --disable_save_settings_button
```

Then open:

```text
http://localhost:18765/launcher
```

Use this for inspection. For curated Step 3 outputs, save JSON outside Step 1.
