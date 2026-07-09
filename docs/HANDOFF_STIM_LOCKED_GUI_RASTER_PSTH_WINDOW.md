# Handoff: Stim-Locked Raster/PSTH Window for SpikeInterface GUI

Date drafted: 2026-07-09

## Confirmed Goal

Add a custom Axion/MEA response-inspection window to the existing
SpikeInterface GUI workflow so manual curation decisions can be made with
stimulation-locked context visible.

The target user flow is:

1. Open a completed Step 1 `SortingAnalyzer` in the existing web GUI launcher.
2. Select one unit, or a set of units being considered for merge/split/delete.
3. Open a single extra response window.
4. Use two tabs in that window:
   - tab 1: train/event locked view, where each stimulation train is one trial;
   - tab 2: pulse locked view, where each pulse inside the train can be viewed
     separately and/or pooled as pulse pseudo-trials.
5. Keep this view synchronized with curation work so that when units are
   selected, merged, split, restored, or compared, the raster and PSTH make
   biological sense in the same time-locked coordinate system.

The biological logic matches the existing downstream analysis:

- A tagged stimulation event marks the start of a train/trial.
- In the Lumos/opto case, one train can contain multiple pulses, currently
  represented as five pulses per train in the existing analysis outputs.
- Train-level alignment asks: does this unit respond around the whole 5-pulse
  train?
- Pulse-level alignment asks: does this unit respond to pulse P1, P2, P3, P4,
  P5, or to pooled pulse instances?
- The raster is trial-indexed and time-locked.
- The PSTH uses the same aligned spike table as the raster, so the visual
  interpretation is consistent.

## Existing Repo Pieces to Reuse

The current GUI launchers are:

```text
scripts/launch_step1_sorting_analyzer_browser.py
scripts/launch_step3_spikeinterface_gui.py
docs/STEP3_SPIKEINTERFACE_GUI_WORKFLOW.md
```

The current stimulation-locked analysis code is:

```text
src/axion_mea/stim_locked_spike_rasters.py
src/axion_mea/well_response_analysis.py
src/axion_mea/stim_event_extractor.py
src/axion_mea/io/raw_stim_parser.py
```

Important current behavior:

- `StimAlignedSpikeDataset` builds train-aligned spike rows with
  `aligned_time_ms` relative to `stim_events.event_time_s`.
- `PulseAlignedSpikeBuilder` converts train-aligned rows into pulse-aligned
  pseudo-trials with `pulse_aligned_time_ms`.
- `PsthBuilder` creates PSTH tables with raw counts, Hz rates, and optionally
  smoothed rates.
- `OptoWaveformModel.step_trace()` and `sampled_proxy()` reconstruct the
  command waveform from parsed `.raw` XML micro-ops.
- The plotted waveform is a reconstructed command/opto proxy, not a measured
  analog voltage trace. The handoff should preserve that distinction in code and
  labels, even if the user-facing shorthand is "analog" or "smoothed analog".

## Key Design Decision

The older analysis is well/electrode-level and uses Axion CSV spikes:

```text
processed_data/recording_overview/spike_list_clean.csv
```

The GUI curation window must be unit-level and use the active
`SortingAnalyzer`/sorting object instead.

Therefore, the new window should reuse the alignment, pulse, PSTH, and waveform
logic, but it should replace the spike source:

```text
old source:
  spike_list_clean.csv rows with time_s, well, electrode

new GUI source:
  analyzer.sorting spike trains for selected/current unit ids
```

This matters because curation is about Kilosort/SpikeInterface units, not only
Axion well/electrode event rows.

## Proposed User Interface

Add one Axion-specific response pane/window to the GUI launcher.

Recommended label:

```text
Stim response
```

Recommended structure:

```text
Stim response window
|-- Tab: Train locked
|   |-- reconstructed/smoothed opto command trace
|   |-- raster, rows = stimulation train trials
|   `-- PSTH, denominator = number of train trials
`-- Tab: Pulse locked
    |-- mode control: by pulse position / pooled pulses
    |-- reconstructed/smoothed single-pulse command trace
    |-- raster
    |   |-- by pulse position: rows = train trials, columns/facets = P1..P5
    |   `-- pooled pulses: rows = pulse pseudo-trials in appearance order
    `-- PSTH, denominator = pulse pseudo-trials
```

Initial implementation can be read-only for response context. It does not need
to write analysis tables into the frozen Step 1 analyzer. Curation saves should
continue using the existing external JSON policy.

## Required Data Inputs

For one selected analyzer/well:

```text
1. SortingAnalyzer path
   results/aind/<recording>/<well>/postprocessed/block0_None_recording1.zarr

2. Selected/current unit ids from the GUI controller

3. Sampling rate from analyzer.sorting or analyzer.recording

4. Stim event CSV for the matching recording
   processed_data/stim_event_detection/<stem>_stim_events.csv
   or an equivalent Step 3 canonical event table

5. Raw file or cached waveform intervals for the matching recording
   <stem>.raw, parsed through AxionStimFile
```

The main missing bridge is a resolver that maps:

```text
SortingAnalyzer recording folder name + well
to
raw/stim-event sidecar paths for the same biological recording
```

This should be explicit and testable. Do not guess from GUI labels alone if a
manifest or master table can provide the mapping.

## Computation Model

### Unit Spike Extraction

For each selected unit:

```python
spike_frames = sorting.get_unit_spike_train(unit_id=unit_id)
spike_times_s = spike_frames / sampling_frequency_hz
```

For merged candidate views, the simplest display rule is:

```text
selected-unit view = union of spike times across selected units
```

If the GUI exposes a finalized curation model with merged/split unit ids, a
later version can render the post-curation unit train directly. The first pass
can still be useful if it updates from the current selected units.

### Train-Locked Tab

For every stimulation train event:

```text
window_start_s = event_time_s + train_window.start_s
window_end_s   = event_time_s + train_window.end_s
aligned_time_ms = (spike_time_s - event_time_s) * 1000
trial_index = sequence_number
```

Render:

- top: command waveform over the train window;
- middle: raster rows as train trials;
- bottom: PSTH with train trial count as denominator.

### Pulse-Locked Tab

Recover pulse epochs from the raw-derived waveform program:

```text
PulseEpoch(pulse_index=1, start_ms=..., end_ms=...)
...
PulseEpoch(pulse_index=5, start_ms=..., end_ms=...)
```

For each train trial and each pulse:

```text
pulse_absolute_onset_s = train_event_time_s + pulse.start_ms / 1000
pulse_aligned_time_ms = (spike_time_s - pulse_absolute_onset_s) * 1000
```

Use the current `PulseAlignedSpikeBuilder` attribution rule:

- truncate a pulse window at the next pulse onset so late spikes are not
  assigned across adjacent pulses;
- keep `train_trial_index`, `pulse_index`, and `pulse_trial_index`.

Render either:

- per-pulse-position facets: P1 through P5, with train trials preserved; or
- pooled pulse pseudo-trials: every pulse instance gets its own raster row.

## Suggested Module Layout

Add a small GUI-facing module rather than stuffing this into the launcher:

```text
src/axion_mea/gui_stim_response.py
```

Suggested objects:

```text
StimResponseInputs
  analyzer_path
  recording_name
  well
  stim_events_csv
  raw_file

UnitStimResponseBuilder
  extracts selected-unit spike times
  builds train-aligned and pulse-aligned DataFrames
  calls/reuses PsthBuilder and OptoWaveformModel

StimResponsePanel
  creates Panel/Bokeh tabs
  exposes update_selected_units(unit_ids)
```

The code should keep pure data-building functions separate from Panel/Bokeh
rendering so unit tests can verify alignment without starting a GUI server.

## Launcher Integration

Update both GUI launch paths after the standalone panel works:

```text
scripts/launch_step1_sorting_analyzer_browser.py
scripts/launch_step3_spikeinterface_gui.py
```

The integration can be incremental:

1. Add CLI args for sidecar resolution:
   - `--stim-events-root`
   - `--raw-root`
   - or `--response-manifest`
2. Build the normal SpikeInterface GUI as today.
3. Add an adjacent/extra Panel column or route containing the new
   `StimResponsePanel`.
4. Hook unit-selection changes from the SpikeInterface GUI controller into the
   response panel.
5. If selection hooks are hard to expose in `spikeinterface-gui`, start with a
   manual unit id selector in the response window, then replace it with live GUI
   selection sync once the controller API is confirmed.

## Validation Plan

Unit tests:

- one fake unit with known spike times;
- two train events;
- five pulse epochs per train;
- verify train-aligned `aligned_time_ms`;
- verify pulse-aligned `pulse_aligned_time_ms`;
- verify pulse windows truncate at the next pulse onset;
- verify PSTH denominator differs between train trials and pulse pseudo-trials.

Visual/manual tests:

- use a known recording where the old report produced approximately 50 train
  trials and five pulses per trial;
- compare GUI train-locked raster/PSTH against existing saved train report;
- compare GUI pulse-locked pooled view against existing
  `figure__pulse_response_all_pulses.png`;
- confirm selected units with no spikes show an empty but well-scaled plot;
- confirm selected multi-unit/merge candidate views render the union of spikes;
- confirm no file is written inside the Step 1 analyzer Zarr.

## Open Questions

These should be resolved before implementation:

1. What canonical manifest should map Step 1 analyzer recordings to the Axion
   `.raw` and stim-event sidecars?
2. Should the first GUI version render only the selected unit, or the union of
   all visible/selected units in the merge panel?
3. For splits, should the response panel show the pre-split original unit, the
   proposed split children, or both? This depends on what split state
   `spikeinterface-gui` exposes during editing.
4. Should pulse tab default to per-pulse-position or pooled pulse-as-trial? The
   requested two-tab design can include both within the pulse tab, but a default
   should be chosen.

## Recommended First Implementation Pass

Build this in three passes:

1. Data-only prototype:
   create unit-level train and pulse aligned tables from a `SortingAnalyzer`,
   stim-event CSV, and raw-derived pulse epochs.
2. Standalone Panel window:
   a manual unit selector plus two tabs, independent of live GUI curation state.
3. GUI-linked version:
   synchronize the selected unit ids from the existing SpikeInterface GUI
   controller and keep the response plots updating during merge/split review.

This sequence keeps the important biology correct first, then wires it into the
curation interface.
