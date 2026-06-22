# axion_mea_spiketurnpike

Canonical documentation for how this repository processes one Axion Maestro Pro recording into one reproducible optogenetic spike-response project.

This document is intended to be the source of truth for:

- the exact order in which data moves through the pipeline,
- what every active `.py` file is responsible for,
- what every public function or method does,
- what files are written at each stage, and
- how the output project on disk should be interpreted.

## Repository Contract

There is one supported user entrypoint:

```bash
cd /Users/ecrespo/Documents/MATLAB/axion_mea_spiketurnpike
source /opt/anaconda3/etc/profile.d/conda.sh
conda activate /Users/ecrespo/Documents/MATLAB/axion_mea_spiketurnpike/.conda
python run_axion_mea_opto_pipeline.py
```

The repo expects one recording folder containing:

- `*_spike_list.csv`
- `*_spike_counts.csv`
- `*_environmental_data.csv` when present
- `.raw`
- `.spk` when present

By default, the current recording is read from:

```text
/Volumes/MannySSD/maestro_pro_output_meas/6_22_2026/129-8445
```

By default, the generated project is written to:

```text
/Volumes/MannySSD/axion_mea_projects/<recording_name>
```

## High-Level Flow

The pipeline always runs in this order:

1. `run_axion_mea_opto_pipeline.py`
   - Parses CLI arguments.
   - Creates `ProjectBuildConfig`.
   - Calls `AxionProjectBuilder.run()`.
2. `RecordingSourceBundle.discover()`
   - Resolves the exact source files for one recording.
3. `RecordingOverviewStage.run()`
   - Parses CSV exports.
   - Writes normalized recording-level tables and overview plots.
4. `StimEventStage.run()`
   - Parses the `.raw` file for stimulation-event tags.
   - Writes normalized stimulation event CSV and JSON files.
5. `StimLockedSpikeStage.run()`
   - Aligns spikes to each stimulation event.
   - Writes aligned spike tables and quick raster QC figures.
6. `WellGroupOrganizer.build()`
   - Classifies wells into `opsin` and `no_opsin`.
7. `WellResponseStage.run()`
   - Rebuilds well-level train and pulse analyses.
   - Writes per-well figures, tables, and well manifests.
8. `ProjectSummaryWriter`
   - Writes project-wide Markdown and JSON summaries.
9. `ReproducibilitySnapshotWriter`
   - Copies the exact code used.
   - Writes an exact rebuild shell script.

## Output Project Layout

For each recording, the generated project contains:

```text
<project_root>/
├── processed_data/
│   ├── recording_overview/
│   ├── stim_event_detection/
│   └── stim_locked_spikes/
├── groups/
│   ├── opsin/
│   │   └── <WELL>/
│   └── no_opsin/
│       └── <WELL>/
├── repro/
│   ├── code_snapshot/
│   ├── rebuild_command.sh
│   └── used_files.json
├── project_manifest.json
└── PROJECT_SUMMARY.md
```

### `processed_data/recording_overview/`

Produced by `RecordingOverviewStage.run()`.

Writes:

- `spike_list_clean.csv`
- `well_counts_long.csv`
- `electrode_counts_long.csv`
- `well_metadata.csv`
- `recording_metadata.json`
- `summary.json`
- `environment_clean.csv` when the source environmental CSV exists
- `well_spikes_over_time.png`
- `top_channels_by_well.png`
- `environment_over_time.png` when the source environmental CSV exists

### `processed_data/stim_event_detection/`

Produced by `StimEventStage.run()` through `StimEventExtractor.extract()`.

Writes:

- `<raw_stem>_stim_events.csv`
- `<raw_stem>_stim_events.json`

### `processed_data/stim_locked_spikes/`

Produced by `StimLockedSpikeStage.run()`.

Writes:

- `stim_aligned_spikes.csv`
- `stim_aligned_well_counts.csv`
- `stim_aligned_channel_counts.csv`
- `well_trial_rasters.png`
- `<WELL>_channel_trial_rasters.png` for wells that have active channels

### `groups/<group>/<well>/`

Produced by `WellResponseStage.run()` and `WellResponseBuilder.write()`.

Each analyzed well contains:

- `report/figure__report_panel.png`
- `train_response/figure__train_response.png`
- `train_response/table__train_response_latency.csv`
- `train_response/table__train_response_psth.csv`
- `pulse_response_by_position/figure__pulse_response_by_position.png`
- `pulse_response_by_position/table__pulse_response_by_position.csv`
- `pulse_response_all_pulses/figure__pulse_response_all_pulses.png`
- `pulse_response_all_pulses/table__pulse_response_all_pulses.csv`
- `pulse_response_all_pulses/table__pulse_response_all_pulses_psth.csv`
- `tables/table__pulse_aligned_spikes.csv`
- `tables/table__pulse_trials.csv`
- `well_response_summary.json`

## File-by-File Source of Truth

## `run_axion_mea_opto_pipeline.py`

Purpose:
- User-facing command-line wrapper.
- Adds `src/` to `sys.path` so the repo runs in-place without package installation.
- Converts CLI arguments into `ProjectBuildConfig`.
- Runs the full build.

Functions:

| Function | Role | Inputs | Returns / Side Effects |
|---|---|---|---|
| `parse_args()` | Defines CLI flags for one recording build. | CLI arguments | `argparse.Namespace` |
| `main()` | Builds config and launches the project builder. | Parsed args | Prints final project root |

## `src/axion_mea/__init__.py`

Purpose:
- Minimal public export surface for the package.

Exports:

| Name | Role |
|---|---|
| `AxionProjectBuilder` | Top-level pipeline object |
| `ProjectBuildConfig` | Pipeline configuration dataclass |

## `src/axion_mea/recording_overview.py`

Purpose:
- Parse the CSV exports.
- Normalize them into analysis-friendly tables.
- Produce recording-level overview plots before stimulation-locked analysis.

Functions:

| Function | Role | Inputs | Outputs / Side Effects |
|---|---|---|---|
| `find_first_file(data_dir, suffix)` | Finds the first matching source file in a recording folder. | recording directory, suffix | `Path | None` |
| `sanitize_name(name)` | Converts free text into a filesystem-safe name. | string | sanitized string |
| `read_spike_list(path)` | Parses spike rows plus the embedded `Well Information` footer. | spike-list CSV path | `spikes`, `recording_metadata`, `well_metadata` |
| `parse_well_information(rows)` | Converts footer rows into a tidy well metadata table. | raw footer rows | `DataFrame` |
| `read_spike_counts(path)` | Converts the wide count export into long well and channel tables. | spike-count CSV path | `well_long`, `electrode_long` |
| `read_environment(path)` | Parses environmental telemetry when present. | environmental CSV path | normalized environment `DataFrame` |
| `pick_active_wells(well_long, well_metadata)` | Chooses wells to display in overview plots. | well counts, well metadata | ordered list of wells |
| `save_summary(output_dir, ...)` | Writes a compact recording-level JSON summary. | normalized tables | `summary.json` |
| `plot_well_spikes(well_long, active_wells, output_path)` | Creates well-level heatmap and line overview. | well counts, selected wells | writes `well_spikes_over_time.png` |
| `plot_top_channels_by_well(electrode_long, ...)` | Plots top active channels inside selected wells. | channel counts, plotting config | writes `top_channels_by_well.png` |
| `plot_environment(env, output_path)` | Plots temperature and CO2 traces. | normalized environment table | writes `environment_over_time.png` |

## `src/axion_mea/stim_event_extractor.py`

Purpose:
- Use the low-level raw parser to produce normalized stimulation event exports.

Objects and methods:

| Component | Role |
|---|---|
| `StimEventExtractionResult` | Immutable summary of the stimulation-event extraction stage |
| `StimEventExtractor.__init__(raw_path, output_dir)` | Stores paths and prepares destination directory |
| `StimEventExtractor.extract()` | Parses the raw file and writes stimulation-event CSV/JSON |
| `StimEventExtractor.print_summary(result)` | Prints exact file paths and event counts for the build log |

Outputs:

- `<raw_stem>_stim_events.csv`
- `<raw_stem>_stim_events.json`

## `src/axion_mea/stim_locked_spike_rasters.py`

Purpose:
- Align spikes to each stimulation event using a train-level window.
- Produce the shared aligned spike table used later by the well-level analysis.
- Write quick QC raster figures.

Objects and methods:

| Component | Role |
|---|---|
| `RasterWindow` | Holds the train-level alignment window in ms and seconds |
| `StimAlignedSpikeDataset.load()` | Loads spike and stimulation CSV inputs |
| `StimAlignedSpikeDataset.build_aligned_table()` | Builds `stim_aligned_spikes.csv` |
| `StimAlignedSpikeDataset.save_tables()` | Writes aligned spike, well count, and channel count tables |
| `StimAlignedSpikeDataset.top_channels_by_well(top_n)` | Returns most active electrodes per well |
| `StimAlignedSpikeDataset.wells()` | Returns wells represented in the aligned data |
| `RasterPlotWriter.plot_well_trial_rasters()` | Writes `well_trial_rasters.png` |
| `RasterPlotWriter.plot_channel_trial_rasters(top_n_channels)` | Writes `<WELL>_channel_trial_rasters.png` files |

Primary table schema:

`stim_aligned_spikes.csv` contains:

- `trial_index`
- `stim_time_s`
- `source_kind`
- `well`
- `electrode`
- `channel_in_well`
- `time_s`
- `aligned_time_ms`
- `amplitude_mV`

## `src/axion_mea/well_response_analysis.py`

Purpose:
- Build the biological response views for each well after spikes are already train-aligned.

This module supports three views:

1. train-as-trial
2. pulse-by-position
3. pulse-as-trial pooled view

Configuration and dataset models:

| Component | Role |
|---|---|
| `AnalysisWindow` | Train-level window |
| `PulseWindow` | Pulse-level window |
| `PsthConfig` | PSTH binning and smoothing settings |
| `WaveformRenderConfig` | Resolution and smoothing for opto waveform rendering |
| `PulseEpoch` | One pulse interval inside the train |
| `OpsinStimDataset.load()` | Loads well metadata, train-aligned spikes, and stimulation events |
| `OpsinStimDataset.all_trials()` | Returns all train trial indices |
| `OpsinStimDataset.spikes_for_well(well)` | Returns aligned spikes for one well |

Summary builders:

| Component | Role |
|---|---|
| `TrialLatencyAnalyzer.build_trial_summary()` | One row per train trial with spike count and timing statistics |
| `PulseLatencyAnalyzer.build_pulse_summary()` | One row per pulse pseudo-trial with pulse delay statistics |
| `PulseAlignedSpikeBuilder.build()` | Converts train-aligned spikes into pulse pseudo-trials and pulse manifests |
| `PsthBuilder.build(window)` | Creates histogram bins, raw count, rate, and smoothed rate columns |

Waveform helper:

| Component | Role |
|---|---|
| `OptoWaveformModel.step_trace()` | Returns the intended command waveform as steps |
| `OptoWaveformModel.sampled_proxy()` | Returns the smoothed display proxy used in figures |
| `OptoWaveformModel.max_level_intervals()` | Returns intervals reaching max optical intensity |

Figure builders:

| Component | Role | Main file written |
|---|---|---|
| `OpsinWellFigure.save()` | Train-level summary panel | `train_response/figure__train_response.png` |
| `PulseAlignedWellFigure.save()` | Pulse-by-position diagnostic panel | `pulse_response_by_position/figure__pulse_response_by_position.png` |
| `PulseTrialSummaryFigure.save()` | Pooled pulse pseudo-trial panel | `pulse_response_all_pulses/figure__pulse_response_all_pulses.png` |
| `ReportPanelComposer.compose_report_panel()` | Combined stacked report image | `report/figure__report_panel.png` |

Important private figure helpers:

| Method | Role |
|---|---|
| `OpsinWellFigure._draw_waveform()` | Draws train-level opto waveform overlay |
| `OpsinWellFigure._draw_raster()` | Draws train-level raster |
| `OpsinWellFigure._draw_psth()` | Draws train-level PSTH |
| `OpsinWellFigure._draw_trial_boxplots()` | Draws per-trial spike-time distributions |
| `OpsinWellFigure._draw_delay_boxplot()` | Compares train vs pulse delays |
| `PulseAlignedWellFigure._draw_pulse_waveform()` | Draws per-pulse waveform template |
| `PulseAlignedWellFigure._draw_pulse_raster()` | Draws per-pulse raster with train order preserved |
| `PulseTrialSummaryFigure._draw_waveform()` | Draws pooled single-pulse template |
| `PulseTrialSummaryFigure._draw_raster()` | Draws pooled pseudo-trial raster in acquisition order |
| `PulseTrialSummaryFigure._draw_psth()` | Draws pooled pulse PSTH |
| `PulseTrialSummaryFigure._draw_delay_scatter()` | Draws per-pseudo-trial delay scatter |
| `PulseTrialSummaryFigure._draw_delay_boxplot()` | Draws pooled delay distributions |

Per-well tables written by this module:

- `table__train_response_latency.csv`
- `table__train_response_psth.csv`
- `table__pulse_response_by_position.csv`
- `table__pulse_response_all_pulses.csv`
- `table__pulse_response_all_pulses_psth.csv`
- `table__pulse_aligned_spikes.csv`
- `table__pulse_trials.csv`

## `src/axion_mea/recording_project.py`

Purpose:
- This is the pipeline orchestrator.
- It is the authoritative map between source files, in-memory stages, and final on-disk outputs.

Core data models:

| Component | Role |
|---|---|
| `ProjectBuildConfig` | Global knobs for one run |
| `RecordingSourceBundle.discover()` | Resolves the actual input files |
| `ProjectLayout` | Defines the project folder tree |
| `ExplorerArtifacts` | Carries recording-overview outputs downstream |
| `StimEventArtifacts` | Carries stimulation-event outputs downstream |
| `WellProjectGroup` | Stores `opsin` and `no_opsin` group assignments |
| `WellResponseLayout` | Defines the per-well folder tree |
| `WellResponseAnalysis` | Holds one well's computed outputs before writing |

Analysis/writing helpers:

| Component | Role |
|---|---|
| `WellResponseBuilder.analyze()` | Computes all in-memory response tables for one well |
| `WellResponseBuilder.write()` | Writes all figures, tables, and `well_response_summary.json` for one well |

Pipeline stages:

| Component | Role | Writes |
|---|---|---|
| `RecordingOverviewStage.run()` | Recording-level CSV normalization and overview plotting | `processed_data/recording_overview/*` |
| `StimEventStage.run()` | Raw stimulation event extraction | `processed_data/stim_event_detection/*` |
| `StimLockedSpikeStage.run()` | Train-level spike alignment and raster QC | `processed_data/stim_locked_spikes/*` |
| `WellGroupOrganizer.build()` | Group wells by treatment label | in-memory group assignment only |
| `WellResponseStage.run(groups)` | Per-well response analysis | `groups/<group>/<well>/*` |

Project metadata writers:

| Component | Role |
|---|---|
| `ProjectSummaryWriter.write_manifest()` | Writes `project_manifest.json` |
| `ProjectSummaryWriter.write_summary()` | Writes `PROJECT_SUMMARY.md` |
| `ReproducibilitySnapshotWriter.write()` | Writes `repro/rebuild_command.sh`, `repro/used_files.json`, and `repro/code_snapshot/` |

Top-level orchestrator:

| Method | Role |
|---|---|
| `AxionProjectBuilder.__init__(config)` | Resolves sources and target layout |
| `AxionProjectBuilder.run()` | Runs every stage in order |
| `AxionProjectBuilder._project_root()` | Chooses the final folder name |

## `src/axion_mea/io/raw_stim_parser.py`

Purpose:
- Low-level Axion binary parser limited to stimulation tags needed by this repo.

Main type groups:

| Group | Members |
|---|---|
| Header record enums | `EntryRecordType`, `TagType` |
| Basic binary records | `EntryRecord`, `AxionDateTime`, `TagEntry`, `ChannelMapping`, `LedPosition` |
| Parsed stimulation tags | `StimulationEventData`, `StimulationWaveformTag`, `StimulationChannelsTag`, `StimulationLedsTag`, `StimulationEventTag` |
| Normalized exported models | `StimulationEventSummary`, `OpticalOnInterval` |
| Binary helper | `BinaryReader` |
| High-level parser | `AxionStimFile` |

`BinaryReader` methods:

- `tell()`
- `seek_absolute(offset)`
- `seek_relative(offset)`
- `read_exact(size)`
- `read_u8()`
- `read_u16()`
- `read_u32()`
- `read_u64()`
- `read_i64()`
- `read_f64()`
- `read_ascii(size)`
- `read_utf8()`
- `read_guid()`

`AxionStimFile` methods:

| Method | Role |
|---|---|
| `parse()` | Reads header chains and loads stimulation tags |
| `summarize_stimulation_events()` | Resolves raw tags into normalized event summaries |
| `write_event_csv(output_path)` | Writes the flat stimulation event table |
| `write_event_json(output_path)` | Writes the structured stimulation event export |
| `opto_on_intervals_ms()` | Returns the first recovered optical waveform program as on-intervals |
| `_read_primary_header(reader)` | Reads the primary raw-file header |
| `_collect_latest_tag_entries(reader, entry_records)` | Walks the header chain and keeps latest tag revisions |
| `_load_stimulation_tags(reader)` | Converts cached tag entries into typed stimulation objects |
| `_well_name_from_position()` | Converts numeric well coordinates to `A1`-style names |
| `_parse_micro_ops_intervals(xml)` | Extracts optical intervals from waveform XML |
| `_find_trial_loop(root)` | Locates the XML loop corresponding to one trial |
| `_process_children_once(parent, context)` | Executes one pass through the micro-op program |
| `_parse_duration_ms(text)` | Converts XML duration strings into milliseconds |
| `_local_name(tag)` | Removes XML namespace prefixes |

## Exact Data Flow Between Modules

### Stage 1: source file discovery

Input:
- recording folder

Handled by:
- `RecordingSourceBundle.discover()`

Output:
- resolved paths to spike-list CSV, spike-count CSV, environmental CSV, raw file, and optional spk file

### Stage 2: recording overview

Inputs:
- `*_spike_list.csv`
- `*_spike_counts.csv`
- `*_environmental_data.csv` when present

Handled by:
- `read_spike_list()`
- `read_spike_counts()`
- `read_environment()`
- `save_summary()`
- `plot_well_spikes()`
- `plot_top_channels_by_well()`
- `plot_environment()`

Outputs:
- normalized CSVs and recording-level plots under `processed_data/recording_overview/`

### Stage 3: stimulation event detection

Input:
- `.raw`

Handled by:
- `StimEventExtractor.extract()`
- internally: `AxionStimFile.parse()`, `AxionStimFile.summarize_stimulation_events()`, `AxionStimFile.write_event_csv()`, `AxionStimFile.write_event_json()`

Outputs:
- stimulation-event CSV and JSON under `processed_data/stim_event_detection/`

### Stage 4: train-level spike alignment

Inputs:
- `spike_list_clean.csv`
- `<raw_stem>_stim_events.csv`

Handled by:
- `StimAlignedSpikeDataset.load()`
- `StimAlignedSpikeDataset.build_aligned_table()`
- `StimAlignedSpikeDataset.save_tables()`
- `RasterPlotWriter.plot_well_trial_rasters()`
- `RasterPlotWriter.plot_channel_trial_rasters()`

Outputs:
- aligned spike tables and QC rasters under `processed_data/stim_locked_spikes/`

### Stage 5: well grouping

Inputs:
- `well_metadata.csv`
- `stim_aligned_spikes.csv`

Handled by:
- `WellGroupOrganizer.build()`

Outputs:
- in-memory `opsin` and `no_opsin` well groups

### Stage 6: well response analysis

Inputs:
- `spike_list_clean.csv`
- `well_metadata.csv`
- `<raw_stem>_stim_events.csv`
- `.raw`

Handled by:
- `WellResponseStage.run()`
- `WellResponseBuilder.analyze()`
- `WellResponseBuilder.write()`
- `TrialLatencyAnalyzer`
- `PulseLatencyAnalyzer`
- `PulseAlignedSpikeBuilder`
- `PsthBuilder`
- `OpsinWellFigure`
- `PulseAlignedWellFigure`
- `PulseTrialSummaryFigure`
- `ReportPanelComposer`

Outputs:
- all per-well figures, tables, and manifests under `groups/opsin/<well>/` and `groups/no_opsin/<well>/`

### Stage 7: project metadata and reproducibility

Inputs:
- source paths
- config
- well groups
- final layout

Handled by:
- `ProjectSummaryWriter.write_manifest()`
- `ProjectSummaryWriter.write_summary()`
- `ReproducibilitySnapshotWriter.write()`

Outputs:
- `project_manifest.json`
- `PROJECT_SUMMARY.md`
- `repro/rebuild_command.sh`
- `repro/used_files.json`
- `repro/code_snapshot/`

## Active Files Only

Only these Python files are part of the active supported workflow:

- `run_axion_mea_opto_pipeline.py`
- `src/axion_mea/__init__.py`
- `src/axion_mea/recording_overview.py`
- `src/axion_mea/stim_event_extractor.py`
- `src/axion_mea/stim_locked_spike_rasters.py`
- `src/axion_mea/well_response_analysis.py`
- `src/axion_mea/recording_project.py`
- `src/axion_mea/io/__init__.py`
- `src/axion_mea/io/raw_stim_parser.py`

No other Python file is assumed by the supported one-command pipeline.
