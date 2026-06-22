# axion_mea_spiketurnpike

Python pipeline for Axion Maestro Pro optogenetic MEA recordings.

This repo does four things:

- reads the Axion CSV exports
- extracts stimulation timing from the `.raw` file
- aligns spikes to optogenetic stimulation
- writes a per-recording project folder with grouped well-level response summaries

## Quick start

Create the project-local conda environment once:

```bash
cd /Users/ecrespo/Documents/MATLAB/axion_mea_spiketurnpike
/opt/anaconda3/bin/conda env create -f environment.yml --prefix ./.conda
```

Activate it for each session:

```bash
source /opt/anaconda3/etc/profile.d/conda.sh
conda activate /Users/ecrespo/Documents/MATLAB/axion_mea_spiketurnpike/.conda
which python
```

Expected interpreter:

```bash
/Users/ecrespo/Documents/MATLAB/axion_mea_spiketurnpike/.conda/bin/python
```

Build the full reproducible project for the current recording with one command:

```bash
cd /Users/ecrespo/Documents/MATLAB/axion_mea_spiketurnpike
python run_axion_mea_opto_pipeline.py
```

By default this writes the project to:

```
/Volumes/MannySSD/axion_mea_projects/ventral_sosrs_opsin_day3_000
```

To process another recording later, run the same command with a different `--data-dir` and optionally a different `--project-name`.

If you prefer, you can still use `requirements.txt`, but the intended path for this repo is the local conda environment at `./.conda`.

Important:

- The environment is a local prefix env at `/Users/ecrespo/Documents/MATLAB/axion_mea_spiketurnpike/.conda`
- The default macOS `/usr/bin/python3` on this machine is not the intended interpreter for this repo
- Launch the script after `conda activate` so `numpy`, `pandas`, `matplotlib`, `seaborn`, and `pillow` resolve correctly

## Preferred Pipeline

The supported entrypoint is `run_axion_mea_opto_pipeline.py`.

It assumes the source folder contains the relevant Axion files together:

- `*_spike_list.csv`
- `*_spike_counts.csv`
- `*_environmental_data.csv` when present
- `.raw`
- `.spk` when present

For each recording, the builder creates one stable project folder under `/Volumes/MannySSD/axion_mea_projects/` by default:

- `derived/csv_explorer/`
- `derived/stim_times/`
- `derived/stim_aligned/`
- `groups/opsin/<WELL>/`
- `groups/no_opsin/<WELL>/`
- `project_manifest.json`
- `PROJECT_SUMMARY.md`

The group folders only include wells that actually have aligned data. Each well folder contains one optogenetic stimulation response screen for that well. Inside each well folder:

- `report/`
- `train_response/`
- `pulse_response_by_position/`
- `pulse_response_all_pulses/`
- `tables/`
- `well_response_summary.json`

What each analysis folder means:

- `train_response/`: each 5-pulse stimulation train is treated as one trial and aligned to train onset
- `pulse_response_by_position/`: pulse 1 through pulse 5 are aligned separately while preserving pulse identity within each train
- `pulse_response_all_pulses/`: every pulse is treated as its own event and stacked in acquisition order across the recording

This keeps the interpretation attached to the folder names themselves rather than hiding it in a vague bundle name.

To process another recording later, run the same builder again with a new `--data-dir`. That creates another project folder without disturbing existing ones.

## Source Layout

All active code lives under `src/axion_mea/`:

- `project_pipeline.py`: top-level recording builder
- `csv_export_explorer.py`: CSV parsing, cleaning, and basic exploratory plots
- `stim_event_extractor.py`: `.raw` stimulation event extraction
- `stim_aligned_raster_plots.py`: stimulation-aligned raster tables and raster figures
- `opsin_response_plots.py`: train-level and pulse-level response figures and PSTHs
- `io/raw_stim_parser.py`: low-level Axion `.raw` tag parser

The only intended top-level command is `python run_axion_mea_opto_pipeline.py`.

## Output

The script writes one reproducible recording project under `/Volumes/MannySSD/axion_mea_projects/` by default.

Within that project:

- `spike_list_clean.csv`
- `well_counts_long.csv`
- `electrode_counts_long.csv`
- `well_metadata.csv`
- `recording_metadata.json`
- `environment_clean.csv` when present
- `well_spikes_over_time.png`
- `top_channels_by_well.png`
- `environment_over_time.png` when present

Those files live in the derived subfolders documented above rather than in a flat repo-local `outputs/` directory.

## What the CSVs contain

What is available directly in CSV:

- Recording-level metadata embedded near the top of the export
- Well-level annotations from the `Well Information` table
- Spike times and amplitudes
- Per-second spike counts by well and electrode

What I do not see in these CSV exports:

- Explicit optogenetic stimulation timestamps
- LED pulse train timing
- Stimulation waveform parameters

Those are more likely to live in the `.raw` or `.spk` files. If needed, the next step is a second script that inspects stimulation events from the raw file.

## Raw and Spk Note

The CSV exports are good for quick spike exploration, but they are not enough for explicit optogenetic event timing.

- The `.raw` file is the most likely source of opto timing tags
- The `.spk` file contains spike timing and waveforms and may retain related metadata
- A pure Python path is possible, but there is not currently an official Axion Python loader in this repo
- The practical approach is to port the relevant parts of Axion's MATLAB loader into Python, starting with stimulation tags and event records rather than full waveform support

Current status in this repo:

- `stim_event_extractor.py` reads Axion tag records directly from `.raw` in pure Python
- It writes `*_stim_events.csv` and `*_stim_events.json`
- The sample file produced LED-linked stimulation timestamps successfully
- `stim_aligned_raster_plots.py` aligns spikes to each stimulation event and writes per-well and per-channel trial rasters
- `opsin_response_plots.py` focuses on opsin wells and writes:
  - a train-aligned summary figure
  - a per-pulse diagnostic figure
  - a pooled pulse-trial summary figure
- `run_axion_mea_opto_pipeline.py` is the reproducible project-level entrypoint
- `project_pipeline.py` ties the stages together and splits wells into `opsin` and `no_opsin`
  - a combined report panel for each analyzed well
