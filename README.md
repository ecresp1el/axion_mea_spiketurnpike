# axion_mea_spiketurnpike

Source-of-truth documentation for how this repository turns Axion Maestro Pro exports into reproducible optogenetic spike-response projects.

This README is intentionally constrained to what the current code actually does. If a statement below is not supported by the active Python files under `src/axion_mea/`, it should be treated as a bug in the documentation.

## One Command

```bash
cd /Users/ecrespo/Documents/MATLAB/axion_mea_spiketurnpike
source /opt/anaconda3/etc/profile.d/conda.sh
conda activate /Users/ecrespo/Documents/MATLAB/axion_mea_spiketurnpike/.conda
python run_axion_mea_opto_pipeline.py
```

Default input:

```text
/Volumes/MannySSD/maestro_pro_output_meas/6_22_2026
```

Default output root:

```text
/Volumes/MannySSD/axion_mea_projects
```

The repository supports either:

- one folder containing one Axion recording export set, or
- one parent folder containing many indexed recordings from the same plate or date.

## Source File Contract

Each recording is identified by one shared stem such as `ventral_sosrs_opsin_day3(003)`.

The code looks for these files:

| Source file | Required | Used for |
|---|---|---|
| `<stem>_spike_list.csv` | yes | Per-spike event times, electrode labels, amplitudes, recording header metadata, `Well Information` footer metadata |
| `<stem>_spike_counts.csv` | yes | Interval spike counts by well and electrode |
| `<stem>_environmental_data.csv` | no | Temperature and CO2 telemetry overview |
| `<stem>.raw` | yes | Stimulation event timing, stimulated wells, waveform-program XML micro-ops |
| `<stem>.spk` | optional at discovery, but required by waveform-linking outputs | Spike waveform snippets and sample indices |

## Data Provenance Map

This is the shortest answer to “what can I find where?”

| Information | First source | Normalized output written by this repo | Notes |
|---|---|---|---|
| Per-spike time stamps | `<stem>_spike_list.csv` | `processed_data/recording_overview/spike_list_clean.csv` | Stored as `time_s` |
| Per-spike amplitude | `<stem>_spike_list.csv` | `processed_data/recording_overview/spike_list_clean.csv` | Stored as `amplitude_mV` |
| Well and electrode identity | `<stem>_spike_list.csv` | `processed_data/recording_overview/spike_list_clean.csv` | Stored as `well`, `electrode`, `channel_in_well` |
| Recording header metadata | `<stem>_spike_list.csv` header rows | `processed_data/recording_overview/recording_metadata.json` | Key-value pairs from the first two columns |
| Well treatment / active-control annotations | `Well Information` block inside `<stem>_spike_list.csv` | `processed_data/recording_overview/well_metadata.csv` | Includes `Treatment`, `Active`, `Control` when present |
| Interval spike counts by well | `<stem>_spike_counts.csv` | `processed_data/recording_overview/well_counts_long.csv` | Long format with `interval_start_s`, `interval_end_s` |
| Interval spike counts by electrode | `<stem>_spike_counts.csv` | `processed_data/recording_overview/electrode_counts_long.csv` | Long format with derived `well` and `channel_in_well` |
| Environmental telemetry | `<stem>_environmental_data.csv` | `processed_data/recording_overview/environment_clean.csv` | Only written when source file exists |
| Stim onsets and stimulated wells | `<stem>.raw` | `processed_data/stim_event_detection/<stem>_stim_events.csv` | Parsed from stimulation tags |
| Stim event JSON provenance | `<stem>.raw` | `processed_data/stim_event_detection/<stem>_stim_events.json` | Machine-readable copy of parsed event summaries |
| Train-aligned spikes | normalized spike CSV + stim-event CSV | `processed_data/stim_locked_spikes/stim_aligned_spikes.csv` | `aligned_time_ms` is relative to train onset |
| Pulse-aligned spikes | train-aligned spikes + raw-derived pulse epochs | `groups/<group>/<well>/tables/table__pulse_aligned_spikes.csv` | `pulse_aligned_time_ms` is relative to pulse onset |
| Train-level PSTH | train-aligned spikes | `groups/<group>/<well>/train_response/table__train_response_psth.csv` | One 5-pulse train = one trial |
| Pooled pulse PSTH | pulse-aligned spikes | `groups/<group>/<well>/pulse_response_all_pulses/table__pulse_response_all_pulses_psth.csv` | Each pulse instance = one pseudo-trial |
| Raw spike waveforms | `<stem>.spk` | extracted in memory by `AxionSpikeWaveformFile.extract()` | Used for waveform overview and raincloud linking |
| Cross-recording waveform-link summary | per-recording `.spk` + retained raincloud points | `cross_recording_group_psth_comparison/tables/table__raincloud_linked_unit_waveform_summary.csv` | Links selected rate points back to waveform snippets |

## Important Interpretation Rules Encoded in the Current Code

- The optical waveform shown in the report figures is not a measured analog trace.
  - It is reconstructed from `.raw` stimulation waveform micro-ops parsed from the XML program and then optionally smoothed for display.
- Train alignment and pulse alignment use spike times from `spike_list_clean.csv`, not `.spk`.
- `.spk` is only used for waveform-shape analyses.
- `OpsinStimDataset` loads `well_metadata.csv`, but the train-alignment math itself currently uses `stimulated_wells` from the extracted stim-event CSV rather than treatment metadata.
- The cross-recording pulse-delay raincloud is a delay plot in milliseconds.
  - Lower post-pulse values mean faster stimulus-locked spiking.
  - It is not a firing-rate plot.
- The cross-recording waveform-link stage expects the retained recordings to have resolvable `.spk` paths in their `project_manifest.json`.

## Pipeline Execution Order

The supported entrypoint is `run_axion_mea_opto_pipeline.py`.

The pipeline runs in this order:

1. Parse CLI arguments into `ProjectBuildConfig`.
2. Discover all recordings with `RecordingSourceBundle.discover_all()`.
3. For each recording, run `AxionProjectBuilder.run()`.
4. `RecordingOverviewStage.run()`
   - Parse CSV exports.
   - Write normalized recording-level tables and overview plots.
5. `StimEventStage.run()`
   - Parse `.raw`.
   - Write normalized stimulation event CSV and JSON files.
6. `StimLockedSpikeStage.run()`
   - Align spikes to train onsets.
   - Write aligned spike tables and quick raster QC figures.
7. `WellGroupOrganizer.build()`
   - Split wells into `opsin` and `no_opsin`.
8. `WellResponseStage.run()`
   - Build train-aligned, pulse-by-position, and pooled pulse-as-trial analyses.
9. `ProjectSummaryWriter`
   - Write project-wide manifest and Markdown summary.
10. `ReproducibilitySnapshotWriter`
   - Copy the exact active code and write an exact rebuild command.
11. If more than one recording was discovered, `CrossRecordingOpsinComparator.run()`
   - Rank wells across recordings.
   - Write train, pulse, delay, and waveform-link series summaries.
12. `RecordingSeriesSummaryWriter`
   - Write batch-level manifest and rebuild script.

## Output Layout

### Single recording project

```text
<project_root>/
├── processed_data/
│   ├── recording_overview/
│   ├── stim_event_detection/
│   └── stim_locked_spikes/
├── groups/
│   ├── opsin/
│   └── no_opsin/
├── repro/
│   ├── code_snapshot/
│   ├── rebuild_command.sh
│   └── used_files.json
├── project_manifest.json
└── PROJECT_SUMMARY.md
```

### Recording overview outputs

Written by `RecordingOverviewStage.run()`:

- `spike_list_clean.csv`
- `well_counts_long.csv`
- `electrode_counts_long.csv`
- `well_metadata.csv`
- `recording_metadata.json`
- `summary.json`
- `environment_clean.csv` when environmental CSV exists
- `well_spikes_over_time.png`
- `top_channels_by_well.png`
- `environment_over_time.png` when environmental CSV exists

### Stim event outputs

Written by `StimEventStage.run()`:

- `<stem>_stim_events.csv`
- `<stem>_stim_events.json`

### Stim-locked spike outputs

Written by `StimLockedSpikeStage.run()`:

- `stim_aligned_spikes.csv`
- `stim_aligned_well_counts.csv`
- `stim_aligned_channel_counts.csv`
- `well_trial_rasters.png`
- `<WELL>_channel_trial_rasters.png`

### Per-well response outputs

Written by `WellResponseStage.run()` and `WellResponseBuilder.write()`:

- `groups/<group>/<well>/report/figure__report_panel.png`
- `groups/<group>/<well>/train_response/figure__train_response.png`
- `groups/<group>/<well>/train_response/table__train_response_latency.csv`
- `groups/<group>/<well>/train_response/table__train_response_psth.csv`
- `groups/<group>/<well>/pulse_response_by_position/figure__pulse_response_by_position.png`
- `groups/<group>/<well>/pulse_response_by_position/table__pulse_response_by_position.csv`
- `groups/<group>/<well>/pulse_response_all_pulses/figure__pulse_response_all_pulses.png`
- `groups/<group>/<well>/pulse_response_all_pulses/table__pulse_response_all_pulses.csv`
- `groups/<group>/<well>/pulse_response_all_pulses/table__pulse_response_all_pulses_psth.csv`
- `groups/<group>/<well>/tables/table__pulse_aligned_spikes.csv`
- `groups/<group>/<well>/tables/table__pulse_trials.csv`
- `groups/<group>/<well>/well_response_summary.json`

### Multi-recording series outputs

```text
<series_root>/
├── cross_recording_group_psth_comparison/
│   ├── figures/
│   ├── tables/
│   └── cross_recording_group_psth_summary.json
├── recordings/
├── repro/
├── recording_series_manifest.json
└── RECORDING_SERIES_SUMMARY.md
```

The current cross-recording comparison writes:

- `figures/figure__train_psth_by_recording_and_group.png`
- `figures/figure__pulse_trial_psth_by_recording_and_group.png`
- `figures/figure__pulse_trial_rate_raincloud_by_group.png`
- `figures/figure__pulse_trial_spike_delay_raincloud_by_group.png`
- `figures/figure__raincloud_linked_unit_waveforms.png`
- `figures/figure__raincloud_linked_pre_vs_post_mean_waveforms.png`
- `figures/figure__raincloud_linked_unit_waveform_mathcheck.png`
- `tables/table__group_overall_firing_rates_by_recording.csv`
- `tables/table__group_well_ranking.csv`
- `tables/table__selected_group_train_psth_long.csv`
- `tables/table__selected_group_train_psth_metrics.csv`
- `tables/table__selected_group_pulse_trial_psth_long.csv`
- `tables/table__selected_group_pulse_trial_psth_metrics.csv`
- `tables/table__pulse_trial_group_rate_distribution.csv`
- `tables/table__pulse_trial_group_spike_delay_distribution.csv`
- `tables/table__raincloud_linked_unit_waveform_summary.csv`
- `cross_recording_group_psth_summary.json`

## File-by-File Source of Truth

### `run_axion_mea_opto_pipeline.py`

Role:

- User-facing CLI wrapper.
- Adds `src/` to `sys.path` for in-place execution.
- Converts CLI flags into `ProjectBuildConfig`.
- Launches `AxionProjectSeriesBuilder`.

Public functions:

- `parse_args()`: define repository CLI flags.
- `main()`: build config, run the pipeline, print the final output root.

### `src/axion_mea/__init__.py`

Role:

- Minimal package export surface.

Exports:

- `ProjectBuildConfig`
- `AxionProjectBuilder`
- `AxionProjectSeriesBuilder`

### `src/axion_mea/recording_project.py`

Role:

- Master orchestration layer for one recording and for one batch of repeated recordings.
- Defines the canonical folder layouts, stage ordering, manifests, and reproducibility snapshots.

Important classes and methods:

- `ProjectBuildConfig`: shared runtime configuration.
- `RecordingSourceBundle.discover_all()`: discover valid recording stems from an input tree.
- `ProjectLayout` and `RecordingSeriesLayout`: define all on-disk folders.
- `RecordingOverviewStage.run()`: write normalized CSV-derived recording products.
- `StimEventStage.run()`: write `.raw`-derived stimulation products.
- `StimLockedSpikeStage.run()`: write train-aligned spike tables and raster QC outputs.
- `WellGroupOrganizer.build()`: classify aligned wells into `opsin` and `no_opsin`.
- `WellResponseStage.run()`: build per-well response bundles.
- `ProjectSummaryWriter.write_manifest()` and `write_summary()`: write project summaries.
- `ReproducibilitySnapshotWriter.write()`: copy the exact active code and rebuild command.
- `AxionProjectBuilder.run()`: execute the full single-recording workflow.
- `RecordingSeriesSummaryWriter.write()`: write batch manifest, summary, and rebuild script.
- `AxionProjectSeriesBuilder.run()`: build all recordings, then write cross-recording comparison outputs.

### `src/axion_mea/recording_overview.py`

Role:

- Parse the raw Axion CSV exports into normalized tables used by every later stage.

Data handled:

- `read_spike_list()`: parse per-spike rows plus the embedded `Well Information` block.
- `read_spike_counts()`: convert wide interval counts into long well/electrode tables.
- `read_environment()`: parse environmental telemetry when available.
- `save_summary()`: write recording-level summary JSON.
- `plot_well_spikes()`, `plot_top_channels_by_well()`, `plot_environment()`: write overview figures.

### `src/axion_mea/io/raw_stim_parser.py`

Role:

- Low-level `.raw` parser for only the stimulation-related Axion tag structures used by this repository.

What it recovers:

- stimulation event times,
- stimulation channel-group mappings,
- stimulation LED-group mappings,
- stimulated wells,
- raw tag metadata, and
- waveform-program XML micro-ops used to reconstruct the command waveform.

Primary entrypoint:

- `AxionStimFile.parse()`

Primary exports written by callers:

- event CSV and JSON summaries through `write_event_csv()` and `write_event_json()`
- optical on-interval reconstruction through `opto_on_intervals_ms()`

### `src/axion_mea/stim_event_extractor.py`

Role:

- Thin wrapper around `AxionStimFile`.
- Convert `.raw` parsing into the normalized stim-event files used downstream.

Public API:

- `StimEventExtractor.extract()`: parse `.raw`, write `<stem>_stim_events.csv` and `<stem>_stim_events.json`, return counts and output paths.
- `StimEventExtractor.print_summary()`: print extraction counts and stimulated wells.

### `src/axion_mea/stim_locked_spike_rasters.py`

Role:

- Re-express spikes in train-relative coordinates for QC and downstream reuse.

Public API:

- `StimAlignedSpikeDataset.load()`: read normalized spike and stim-event CSVs.
- `StimAlignedSpikeDataset.build_aligned_table()`: create `aligned_time_ms` rows for spikes inside the requested train window.
- `StimAlignedSpikeDataset.save_tables()`: write aligned spike and summary-count tables.
- `RasterPlotWriter.plot_well_trial_rasters()`: write one raster panel per stimulated well.
- `RasterPlotWriter.plot_channel_trial_rasters()`: write raster panels for top electrodes within each well.

### `src/axion_mea/well_response_analysis.py`

Role:

- Per-well biological analysis after train-aligned spikes already exist.

Three analysis views:

- train view: one 5-pulse train is one trial,
- pulse-by-position view: P1 through P5 stay separated inside each train,
- pooled pulse view: every pulse instance becomes its own pseudo-trial.

Important classes and methods:

- `OpsinStimDataset.load()`: load normalized per-recording inputs and build train-aligned spikes for well-level analysis.
- `TrialLatencyAnalyzer.build_trial_summary()`: summarize train-level spike times.
- `PulseAlignedSpikeBuilder.build()`: convert train-aligned spikes into pulse-aligned pseudo-trials.
- `PulseLatencyAnalyzer.build_pulse_summary()`: summarize pulse-level first-spike delays.
- `PsthBuilder.build()`: create PSTH tables with raw counts, rates, and smoothed rates.
- `OptoWaveformModel.step_trace()` and `sampled_proxy()`: reconstruct display waveforms from raw-derived on-intervals.
- `OpsinWellFigure.save()`: write the train-level summary figure.
- `PulseAlignedWellFigure.save()`: write the pulse-by-position figure.
- `PulseTrialSummaryFigure.save()`: write the pooled pulse-as-trial figure.
- `ReportPanelComposer.compose_report_panel()`: combine the three per-well figures into one report image.

### `src/axion_mea/series_response_comparison.py`

Role:

- Cross-recording comparison stage that operates only on previously written project outputs.

Inputs reused from each recording project:

- `processed_data/recording_overview/well_counts_long.csv`
- `processed_data/recording_overview/well_metadata.csv`
- well-level PSTH tables under `groups/`
- `groups/<group>/<well>/tables/table__pulse_aligned_spikes.csv`

Important methods:

- `CrossRecordingOpsinComparator.run()`: write all cross-recording figures and tables.
- `_build_rate_table()`: compute overall firing-rate rankings from interval counts.
- `_collect_psth_tables()`: pool selected per-well PSTHs across recordings.
- `_collect_group_metric_pool()`: build the retained pre/post firing-rate raincloud table.
- `_collect_pulse_delay_metric_pool()`: build the paired pre-pulse versus post-pulse delay table in milliseconds.

### `src/axion_mea/spike_waveform_overview.py`

Role:

- Parse `.spk` files into waveform snippets and quick waveform summary products.

Important objects:

- `SpikeWaveformMetadata`: sampling and voltage-scaling metadata.
- `AxionSpikeWaveformFile.extract()`: return `sample_indices` plus `waveforms_uv`.
- `SpikeWaveformClassifier.measure_extraction()`: compute trough-to-peak latency for each waveform.
- `SpikeWaveformOverviewWriter.write_series_overview()`: write pooled and per-recording waveform overview figures/tables.
- `SpikeWaveformOverviewWriter.write_trough_to_peak_overview()`: write heuristic FS/RS summary figures/tables.

### `src/axion_mea/raincloud_waveform_linking.py`

Role:

- Bridge cross-recording rate summaries back to the waveform snippets in `.spk`.

How the linkage works:

1. take retained well-recording points from the pulse-trial raincloud,
2. find the exact peak post-stimulus PSTH bin for each point,
3. select the electrode with the most spikes in that bin,
4. attach `.spk` waveform indices back to those spikes, and
5. summarize pre-stimulus and post-stimulus waveform shape for that electrode proxy.

Important methods:

- `RecordingSpikeWaveformMatcher.attach_waveform_indices()`: merge waveform indices onto spike rows from the same recording.
- `RaincloudWaveformLinkBuilder.write_linked_waveform_report()`: write linked waveform figures and summary tables.

## Current Assumptions That Matter

- Recording discovery requires `*_spike_list.csv`, `*_spike_counts.csv`, and `.raw`.
- Environmental data are optional.
- `.spk` is optional for discovery, but waveform-link outputs depend on it.
- The code infers one constant sample-index offset between `spike_list_clean.csv` and `.spk` within each recording.
- Pulse-level PSTHs in the pooled pulse view use fixed 1 ms bins with no smoothing.
- Train-level PSTHs use the configured `boxcar_kernel`.

## Reproducibility Artifacts

Every built project writes:

- a code snapshot under `repro/code_snapshot/`
- a shell rebuild command (`repro/rebuild_command.sh` or `repro/rebuild_all_recordings.sh`)
- a JSON file enumerating the copied code files (`repro/used_files.json`)

Those artifacts are the repository’s own record of exactly which code and parameters were used for a given analysis output.
