# Handoff: Stim-Locked Raster/PSTH Window for SpikeInterface GUI

Date drafted: 2026-07-09

## Confirmed Goal

Add a custom Axion/MEA response-inspection window to the existing
SpikeInterface GUI workflow so manual curation decisions can be made with
stimulation-locked context visible.

This window is optogenetic-stimulation-specific. It should only be shown when
both conditions are true:

1. the recording is a Lumos plate recording, currently `plate_family ==
   "lumos_48well"` or equivalent raw metadata such as `FortyEightWellLumos`;
2. stimulation metadata are actually available and parseable for the matching
   recording.

For non-Lumos plates, or Lumos recordings with no usable stimulation events, the
regular SpikeInterface GUI should open exactly as it does now and the response
window should be hidden or disabled with a short status message.

Current working cohort assumption:

- If the recordings being curated are from the June/July Lumos opto-stim set,
  they are expected to be in scope for this response window.
- The implementation should still run the Lumos/stim preflight on every
  recording, because date/cohort is a helpful expectation rather than a
  sufficient technical guarantee.
- If a June/July recording fails the Lumos/stim preflight, treat that as a data
  resolution issue to surface clearly, not as a reason to guess pulse timing.

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
- The number of pulses must not be hard-coded. Five pulses is the known example,
  not a general rule.
- Train-level alignment asks: does this unit respond around the whole
  stimulation train, whatever pulse count that train contains?
- Pulse-level alignment asks: does this unit respond to pulse P1..PN, or to
  pooled pulse instances?
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
- `OptoWaveformModel.step_trace()` reconstructs the command timing from parsed
  `.raw` XML micro-ops.
- `OptoWaveformModel.sampled_proxy()` samples and smooths those metadata-derived
  micro-op intervals into the analog-like command trace used for display
  overlays.
- This is not a measured analog voltage channel. It is the reconstructed,
  smoothed opto command from raw metadata/XML micro-ops, and the GUI should
  label it that way.

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
|   |-- reconstructed opto command trace
|   |-- raster, rows = stimulation train trials
|   `-- PSTH, denominator = number of train trials
`-- Tab: Pulse locked
    |-- mode control: by pulse position / pooled pulses
    |-- reconstructed single-pulse command trace
    |-- raster
    |   |-- by pulse position: rows = train trials, columns/facets = P1..PN
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

6. Plate family / plate type metadata for the recording
   expected Lumos value: lumos_48well / FortyEightWellLumos
```

The main missing bridge is a resolver that maps:

```text
SortingAnalyzer recording folder name + well
to
raw/stim-event sidecar paths for the same biological recording
```

This should be explicit and testable. Do not guess from GUI labels alone if a
manifest or master table can provide the mapping.

## Eligibility and Stim Preflight

Before constructing the response window, run a preflight resolver/check:

```text
StimResponseEligibility
|-- is_lumos_plate
|-- has_stim_event_table
|-- stim_event_count
|-- has_raw_or_cached_waveform
|-- parse_status
|-- stimulated_wells
|-- pulse_structure_status
`-- message
```

The response window should be enabled only when:

```text
is_lumos_plate == true
has_stim_event_table == true
stim_event_count > 0
parse_status == "ok"
```

Recommended plate checks, in order:

1. use the Step 2/Step 3 manifest `plate_family` if available;
2. fall back to raw metadata parsed with existing Axion metadata helpers;
3. treat the recording as ineligible if the plate family cannot be resolved.

Recommended stimulation checks:

1. confirm a matching stim-event CSV or JSON exists;
2. confirm `event_time_s` and `sequence_number` are present and non-empty;
3. confirm the selected well appears in `stimulated_wells` when that column is
   available;
4. confirm `.raw` or cached pulse interval metadata can be loaded for waveform
   and pulse-epoch reconstruction.

If a Lumos recording has train event times but no waveform intervals, the first
implementation may still show the train-locked raster/PSTH, but it should hide
or disable pulse-locked rendering because pulse onsets are not defined.

## Pulse-Structure Strategy

Do not assume every recording has five pulses per train. Before drawing the
pulse tab, inspect the parsed waveform program and stimulation events.

The current `WellResponseStage._build_pulse_epochs()` collapses adjacent
raw XML micro-operations into biologically meaningful pulse windows using a
small merge gap. Keep that idea, but add a validation layer that reports:

```text
pulse_count_per_train
pulse_start_offsets_ms
pulse_durations_ms
pulse_intervals_consistent
```

Expected common case:

```text
all train events share the same pulse template
```

In that case:

- render the pulse tab normally;
- label facets dynamically as `P1..PN`;
- set the pooled pulse denominator to `number_of_train_trials * N`.

If pulse count or pulse timing differs across stimulation events, adapt before
plotting:

1. If events can be grouped into a small number of repeated templates, split the
   pulse tab by template group and show the template identity in the plot title.
2. If the pulse pattern varies event-by-event, do not pool all pulses into one
   PSTH by default. Show train-locked plots only, or require a manual/template
   selection before pulse pooling.
3. If pulse intervals cannot be reconstructed, disable the pulse tab and keep
   the train-locked tab available if event onsets are valid.

The implementation should surface the decision in the GUI status area, for
example:

```text
Stim response enabled: Lumos recording with 50 trains and uniform 5-pulse template.
```

or:

```text
Train-locked response only: Lumos recording has event onsets, but pulse templates vary across events.
```

## Computation Model

### Unit Spike Extraction

For each selected unit:

```python
spike_frames = sorting.get_unit_spike_train(unit_id=unit_id)
spike_times_s = spike_frames / sampling_frequency_hz
```

For multi-unit inspection, do not pool selected units into one raster by
default. Render a small per-unit panel for each selected unit:

```text
selected units = one raster/PSTH panel per unit id
```

If the GUI exposes a finalized curation model with merged/split unit ids, a
later version can render the post-curation unit train directly. The first pass
can still be useful if it updates from the current selected units in a grid.

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
PulseEpoch(pulse_index=N, start_ms=..., end_ms=...)
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

- per-pulse-position facets: P1 through PN, with train trials preserved; or
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
  plate_family
  stim_events_csv
  raw_file

StimResponseEligibility
  decides whether the opto-stim window should appear
  records why it is enabled/disabled

PulseStructureReport
  records pulse count/timing consistency
  chooses uniform, grouped-template, train-only, or disabled pulse mode
  carries raw XML command_intervals_ms for plotting command steps and the
  smoothed metadata-derived command overlay

UnitStimResponseBuilder
  extracts selected-unit spike times
  builds train-aligned and pulse-aligned DataFrames
  calls/reuses PsthBuilder and command waveform logic

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
- one non-Lumos plate, expected response window disabled;
- one Lumos recording with no stim events, expected response window disabled;
- one Lumos recording with event onsets but no pulse intervals, expected
  train-only behavior;
- one Lumos recording with non-five but uniform pulse count, expected dynamic
  `P1..PN` labels and correct pooled denominator;
- one Lumos recording with mixed pulse templates, expected pulse pooling
  disabled or grouped by template;
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
- confirm selected multi-unit/merge candidate views render one panel per unit;
- confirm no file is written inside the Step 1 analyzer Zarr.

## Open Questions

These should be resolved before implementation:

1. What canonical manifest should map Step 1 analyzer recordings to the Axion
   `.raw` and stim-event sidecars?
2. Should the first GUI version render only manually selected units, or all
   visible/selected units from the merge panel once live sync is available?
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
