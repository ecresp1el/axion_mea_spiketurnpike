# Handoff: Stim-Locked Raster/PSTH Window for SpikeInterface GUI

Date drafted: 2026-07-09

Single-source cross-reference, updated 2026-07-09 16:10 EDT:

- This handoff owns the Lumos stim-locked GUI/raster/PSTH behavior.
- It does not redefine the current waveform/cutoff/alignment denominators.
- For the current Lumos and Cytoview FS/RS cutoff, waveform alignment, valid
  unit denominator, and future Step 2 filtering rules, use
  `docs/GREATLAKES_KILOSORT_HANDOFF.md`, section "Current Single Source:
  Waveform Alignment, Cutoffs, And Denominators".
- Any later GUI-side filtering display should show the same denominator,
  exclusion reason, and filtered-output provenance as the post-Step-2 analysis
  artifacts rather than creating a separate hidden inclusion rule.

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

## 2026-07-09 Jitter-Aware Optotag Scoring Update

The Step 1 stim GUI still plots the pulse-locked view over the display context
`-25..+50 ms`, but default opto ranking now uses explicit scoring windows:

```text
baseline: -25..-8 ms relative to each pulse onset
response: -5..+50 ms relative to each pulse onset
during-stim QC: 0 ms through reconstructed pulse end
train-trial baseline: -10..-5 ms relative to train onset
train-trial response: -5..+50 ms relative to train onset
```

This is intentional because the Lumos pulse timing can jitter slightly around
nominal onset. The response rate is an average rate over all pulse pseudo-trials:
total spikes in the scoring window divided by total seconds in that window.
The `*_reliability_250` columns are trial fractions: pulse pseudo-trials with at
least one spike in the window divided by the first 250 pulse pseudo-trials.
All GUI PSTHs now use 1 ms bins. Both train-locked and pulse-locked smoothed
lines use a three-bin `[1, 1, 1]` boxcar kernel.
The refreshed CSVs include both window-average rates and peak 1 ms PSTH signal:
`*_rate_hz` columns are average rates over the named window, while
`*_peak_raw_rate_hz` and `*_peak_smooth_rate_hz` are the maximum raw/smoothed
1 ms PSTH rates inside that window.
The manual guide `review_rank` is sorted first by
`review_sort_peak_raw_response_hz`, which is the pulse-locked raw 1 ms peak in
the `-5..+50 ms` response window. D2 remains flagged as possible-real through
`review_tier`, but the rank itself is signal-first.

Current refreshed screen:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_gui_ready_trial_tag_screen_250pulse_jitterwin_20260709.csv
```

It supersedes the older same-day screen for jitter-aware review:

```text
lumos_gui_ready_trial_tag_screen_250pulse_20260709.csv
```

The latest 2026-07-09 13:42 EDT refreshed file has 150 Lumos GUI-ready wells:
108 scored with usable stim metadata and 42 marked `stim_unavailable`. Highest
peak-response rows include June/July Lumos `D6` and `B5` wells from the
opsin-related recordings. Columns are numeric well columns, so the June/July
prior "columns 4-8" means wells such as `B4`, `B5`, `C6`, `D6`, and `E5`.

Manual review guide:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_manual_spike_sorting_guide_jitterwin_20260709.csv
```

This guide deliberately promotes `D2` rows to the top review tier as possible
real outside-prior responses.

Regenerate both current CSVs with:

```bash
python scripts/refresh_lumos_optotag_analysis.py --date-label 20260709
```

## 2026-07-09 Lumos Candidate Waveform/KSLabel Gallery

The current waveform comparison figure is:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_candidate_waveform_gallery_columns_compare_20260709.png
```

The best-channel normalized-vs-unnormalized inspection figure is:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_candidate_waveform_best_channel_normalized_vs_unnormalized_20260709.png
```

The current all-good-unit TTP distribution, recomputed from the same
`templates.average` best-PTP-channel waveform logic rather than the older master
waveform table, is:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/good_kslabel_ttp_distribution_template_best_ptp_20260709.png
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/good_kslabel_ttp_distribution_template_best_ptp_20260709.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/good_kslabel_ttp_distribution_template_best_ptp_20260709_provenance.json
```

This scanned the current 150 GUI-ready wells and found 276 `KSLabel=good` units,
all currently Lumos. Using the current TTP thresholds, counts are 16 `FS_like`,
40 `borderline`, and 220 `RS_like`; median TTP is 0.720 ms. Regenerate with:

```bash
python scripts/plot_good_kslabel_ttp_distribution_from_templates.py --date-label 20260709
```

That figure has four rows:

```text
row 1: columns 4-8, unnormalized best-channel waveform in uV
row 2: columns 4-8, trough-normalized best-channel waveform
row 3: columns 1-3, unnormalized best-channel waveform in uV
row 4: columns 1-3, trough-normalized best-channel waveform
```

Dot colors on the normalized/unnormalized figure:

```text
blue: pre-trough peak / peak1
black: trough
orange: post-trough rebound peak / peak2
red-orange: half-width anchors
```

Per-unit titles report both TTP and optional REP:

```text
TTP = trough-to-peak time, from trough to rebound peak/peak2
REP = repolarization time, from trough until recovery to a configured fraction
      of the trough amplitude; default REP50, configurable as REP25, REP50, REP63
```

TTP and REP quantify different aspects of spike shape. TTP keeps the existing
rebound-peak definition and is used for the current tentative FS/RS label. REP
uses the post-trough recovery portion of the same waveform and does not change
the landmark detector.

Landmark quantification:

```text
1. Start with the selected best-channel waveform in uV:
   best_waveform = template[:, best_channel_index]

2. Detect the landmark sample indices on that unnormalized uV waveform:
   pre-peak / peak1 = maximum sample before or at the trough
   trough = minimum sample
   rebound peak / peak2 = maximum sample after the trough

3. Compute trough-normalized waveform:
   normalized = best_waveform / abs(min(best_waveform))

4. Compute half-width on the normalized waveform:
   half amplitude = normalized trough / 2
   left anchor = closest sample to half amplitude between pre-peak and trough
   right anchor = closest sample to half amplitude between trough and rebound peak

5. Plot the same landmark sample indices on both rows:
   uV rows show the raw uV amplitudes at those sample times
   normalized rows show the trough-normalized amplitudes at those same sample times

6. Compute optional REP without changing the landmarks:
   threshold_uV = trough_value_uV * rep_fraction
   rep_recovery_index = first post-trough sample where waveform_uV >= threshold_uV
   rep_recovery_time_ms = threshold crossing time, linearly interpolated between samples
   repolarization_time_ms = rep_recovery_time_ms - trough_time_ms
```

The feature logic is intentionally SpikeTurnpike-style. It mirrors the old
`ProcessSUA_main.m` definitions for peak1, trough, peak2, trough-normalized
waveform, peak/trough ratios, and spike half-width, with two explicit adaptations
for this Axion/SpikeInterface data: the selected waveform is the current gallery's
best peak-to-peak analyzer channel, and all durations use the analyzer sampling
rate rather than the old hard-coded 30 kHz conversion.

Its companion summary table is:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_candidate_waveform_kslabel_summary_20260709.csv
```

The same run also writes reusable waveform caches so downstream visual inspection
does not need to reopen every analyzer:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_candidate_waveform_best_channel_traces_20260709.csv.gz
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_candidate_waveform_full_templates_20260709.npz
```

The best-channel trace table is long-form, one row per candidate/sample, with:

```text
UnNormalized_Template_Waveform_uV
Normalized_Template_Waveform
is_pre_peak, is_trough, is_post_peak
is_rep_recovery
is_half_width_start, is_half_width_end
```

The NPZ stores the compact full multi-channel template arrays:

```text
templates_uV shape: 24 candidates x 37 samples x 16 channels
best_waveforms_uV shape: 24 candidates x 37 samples
normalized_best_waveforms shape: 24 candidates x 37 samples
```

The NPZ also stores REP metadata arrays:

```text
rep_fraction
rep_threshold_uV
rep_recovery_index
rep_recovery_time_ms
repolarization_time_ms
```

Dimension meaning:

```text
candidate axis: selected unit rows from the manual guide, in plotted/review-rank order
sample axis: time samples of the template waveform, aligned by templates_ext.nbefore
channel axis: analyzer channels for that Lumos well
```

Examples:

```python
npz["templates_uV"][0, :, :]   # all 16 grey/black channel traces for candidate 0
npz["templates_uV"][0, :, 9]   # candidate 0, channel 9 trace
npz["best_waveforms_uV"][0, :] # candidate 0 black trace in uV
npz["normalized_best_waveforms"][0, :] # candidate 0 black trace normalized by trough depth
```

Regenerate with:

```bash
python scripts/plot_lumos_candidate_waveform_gallery.py --date-label 20260709
python scripts/plot_lumos_candidate_waveform_gallery.py --date-label 20260709 --rep-fraction 0.25
python scripts/plot_lumos_candidate_waveform_gallery.py --date-label 20260709 --rep-fraction 0.63
```

Access logic:

1. Read `lumos_manual_spike_sorting_guide_jitterwin_20260709.csv`.
2. Keep `status == ok` rows and rank by existing `review_rank`.
3. Select the top rows from columns 4-8 and columns 1-3 separately.
4. Derive each analyzer path as
   `<AIND results root>/<recording>/<well>/postprocessed/block0_None_recording1.zarr`.
5. Load the Step 1 `SortingAnalyzer` with persisted extensions.
6. Use the curated sorting to read unit properties: `KSLabel`, `ContamPct`,
   `Amplitude`.
7. Load `templates.average` from the analyzer `templates` extension.
8. Match the guide `top_unit` to the analyzer unit ids, use that unit index into
   `templates.average`, and plot all channels in grey plus the best
   peak-to-peak channel in black.

Concrete data structure:

```python
analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
sorting = analyzer.sorting
unit_ids = list(sorting.get_unit_ids())
unit_id = match_unit_id(unit_ids, guide_row["top_unit"])
unit_index = unit_ids.index(unit_id)

templates_ext = analyzer.get_extension("templates")
templates = templates_ext.get_data(operator="average")
template = templates[unit_index]
```

The expected `templates.average` shape is:

```text
templates.shape == (n_units, n_template_samples, n_channels)
template.shape  == (n_template_samples, n_channels)
```

For one plotted candidate:

```python
channel_ptp = np.ptp(template, axis=0)
best_channel_index = int(np.nanargmax(channel_ptp))
best_waveform = template[:, best_channel_index]
template_trough_best_channel_uV = float(np.nanmin(best_waveform))
template_peak_best_channel_uV = float(np.nanmax(best_waveform))
template_ptp_best_channel_uV = template_peak_best_channel_uV - template_trough_best_channel_uV
```

Therefore, "all channels in grey" means plotting each column of
`template[:, channel_index]` for the selected unit. "Best peak-to-peak channel in
black" means plotting the single channel whose average template has the largest
`max - min` amplitude across template time samples. This best-channel choice is a
SpikeInterface/analyzer template measurement, not a separate Kilosort label.

The x-axis is reconstructed from the template extension alignment:

```python
sampling_frequency = analyzer.recording.get_sampling_frequency()
nbefore = templates_ext.nbefore
time_ms = (np.arange(template.shape[0]) - nbefore) / sampling_frequency * 1000
```

The trough/peak dots on the gallery are also computed from `best_waveform`:

```python
trough_index = int(np.nanargmin(best_waveform))
search_start = min(trough_index + 1, best_waveform.size - 1)
rebound_peak_index = search_start + int(np.nanargmax(best_waveform[search_start:]))
trough_to_peak_duration_ms = time_ms[rebound_peak_index] - time_ms[trough_index]
```

The optional REP metric uses the same trough index and the existing recovery
portion of `best_waveform`; it does not move or redefine the rebound-peak
landmark:

```python
rep_fraction = 0.50  # CLI choices: 0.25, 0.50, 0.63
rep_threshold_uV = best_waveform[trough_index] * rep_fraction
rep_recovery_index = first index after trough where best_waveform[index] >= rep_threshold_uV
repolarization_time_ms = interpolated_recovery_time_ms - time_ms[trough_index]
```

Dot colors:

```text
black dot: trough/minimum of the best-channel average template
orange dot: maximum rebound peak after that trough
```

Tentative FS/RS labels on this optotag-candidate gallery follow the current
repo-wide conservative RS/FS rule:

```text
FS_like: trough_to_peak_duration_ms <= 0.37 ms
borderline: 0.37 ms < trough_to_peak_duration_ms < 0.53 ms
RS_like: trough_to_peak_duration_ms >= 0.53 ms
unknown: missing/nonfinite trough_to_peak_duration_ms
```

These labels are visual-review annotations only; they are not Kilosort labels
and should not replace the canonical RS/FS table without validation. Edge-late
rebound peaks or very small templates should be treated cautiously.

Old SpikeTurnpike-style waveform metrics were added from the same black
best-channel trace. Do not add `waveform_asymmetry` or `repolarization_slope`
here; those are canonical axion table metrics but were intentionally excluded
from this candidate-inspection artifact.

The old SpikeTurnpike source normalized each selected waveform by trough depth:

```python
Normalized_Template_Waveform = best_waveform / abs(min(best_waveform))
```

The candidate summary CSV now includes:

```text
spiketurnpike_amplitude_uV        # abs(min(best_waveform))
spiketurnpike_legacy_cell_type    # old hard TTP rule: FS <= 0.40 ms, RS >= 0.41 ms
pre_peak_index, pre_peak_time_ms, pre_peak_value_uV
post_peak_value_uV
normalized_trough_value
peak1_normalized_amplitude
peak2_normalized_amplitude
peak1_to_trough_ratio
peak2_to_trough_ratio
peak_to_peak_ratio
spike_half_width_ms
half_width_start_index, half_width_end_index
half_width_start_time_ms, half_width_end_time_ms
rep_fraction
rep_threshold_uV
rep_recovery_index
rep_recovery_time_ms
repolarization_time_ms
```

Definitions mirror `Hochgeschwender-Lab/SpikeTurnpike/ProcessSUA_main.m`, with
one necessary update: durations use the analyzer sampling rate instead of the old
hard-coded `sample_delta / 30` conversion. `peak1` is the maximum before the
trough, `peak2` is the maximum after the trough, and `SpikeHalfWidth` is the
distance between the closest half-trough-amplitude samples on the pre-trough and
post-trough slopes. Ratios may exceed 1 for very small or odd/noisy templates
because the old convention normalizes by trough depth rather than by PTP.

Peak terminology:

- `template_peak_best_channel_uV` is the maximum voltage sample in the plotted
  best-channel average template.
- `template_trough_best_channel_uV` is the minimum voltage sample in that same
  waveform.
- `template_ptp_best_channel_uV` is their difference, `peak - trough`.
- These voltage peak/trough values are not Kilosort optotag peaks and are not the
  same as the Kilosort/Phy `Amplitude` property.
- `review_sort_peak_raw_response_hz` is the other "peak" in these tables. It is
  a firing-rate peak from the pulse-locked PSTH, not a voltage/template peak.

Amplitude/scale reminder:

- The waveform gallery y-axis is uV-scaled Step 1 template amplitude.
- These waveforms are average spike snippets from the preprocessed analyzer
  recording with uV scaling.
- They are not raw acquisition traces, not native Kilosort whitened templates,
  and not PCA reconstructions.
- The comparison gallery uses the same y-axis scale across all panels so
  columns 4-8 and columns 1-3 can be visually compared.
- `review_sort_peak_raw_response_hz` is separate from waveform amplitude. It is
  the unsmoothed pulse-locked 1 ms PSTH peak firing rate in Hz inside the
  jitter-aware `-5..+50 ms` response window.

Current comparison summary after the 2026-07-09 13:43 EDT refresh:

```text
columns 4-8 top 12: 4 KSLabel=good, 8 KSLabel=mua,
  median best-channel template PTP ~12.2 uV,
  median firing rate 4.705 Hz, max firing rate 18.575 Hz,
  max peak raw response 44 Hz

columns 1-3 top 12: 7 KSLabel=good, 5 KSLabel=mua,
  median best-channel template PTP ~10.1 uV,
  median firing rate 1.077 Hz, max firing rate 3.432 Hz,
  max peak raw response 20 Hz
```

After adding trough/rebound-peak dots, tentative TTP labels for the same top-24
comparison set are:

```text
columns 4-8 top 12: 12 RS_like, 0 borderline, 0 FS_like
columns 1-3 top 12: 7 RS_like, 3 borderline, 2 FS_like
```

Interpretation: columns 4-8 still have the stronger pulse-locked peak responses,
but the columns 1-3 comparison row still includes several clean `KSLabel=good`
units. Outside-prior wells should stay in manual review as possible real
responses, not be discarded automatically.
