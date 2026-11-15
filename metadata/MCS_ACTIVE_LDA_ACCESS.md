# Locked MCS e-stim analysis: 215 metrics

## Active choice

Use **87 original metrics + 128 added burst metrics**, exactly **215 inputs**.
The user selected this combination explicitly. Keep it unless the user requests
a change; do not replace it based on discrimination-score comparisons.

- Experiment: **Actuators + effectors only**.
- Classes: DREADD (352), LMO (353), PSAM (354), Control (371).
- Observation and plot dot: **one sorted unit**; SUA/MUA pooled.
- Data coverage: **1,554 units** in the existing e-stim analysis.
- Alignment: **first STG pulse train starts at t = 0**.
- Windows: pre/post 5 seconds, pre/post 10 seconds, +0.5–10 seconds, and selected changes.
- Chemical-addition events remain separate. Dates are metadata, not groups.
- Model: LDA with covariance shrinkage **0.01**.

[mcs_active_lda_configuration.json](mcs_active_lda_configuration.json) is the
authoritative feature list and configuration. It lists all selected metrics in
input order. Loading the locked configuration performs no new feature selection.

## Exact data locations

All generated analysis data are on scratch:

```text
/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/
```

| File relative to that directory | Purpose |
| --- | --- |
| `locked_lda_215/active_215_unit_metrics.csv.gz` | Frozen raw table: one row per unit; 215 metric columns plus recording/unit/class/event metadata. |
| `locked_lda_215/active_215_lda_state.npz` | Frozen imputation medians, centering/scaling, LD projection, and fitted class coefficients. Numeric arrays; no pickle. |
| `locked_lda_215/manifest.json` | Configuration, exact features, provenance paths, and SHA256 checksums. |
| `actuator_metric_exploration/unit_metrics.csv` | Complete original 156-metric table from which the 87 original inputs were selected. |
| `actuator_metric_exploration/burst_lda/burst_metrics.npz` | Complete 1,190 added metrics, with names and recording/unit join keys. |
| `actuator_metric_exploration/burst_lda/burst_metric_catalog.csv` | Added metric definitions, windows, units, thresholds, minimum spike counts, and missingness. |
| `actuator_metric_exploration/burst_lda/actual_lda_selected_metrics.csv` | Input audit; filter `view == forced_combination` for the chosen 87 + 128. |
| `actuator_metric_exploration/burst_lda/burst_lda_actual_feature_comparison.png` | Three-view LDA comparison; right panel is the chosen combination. |

The frozen CSV is the simplest access point. It avoids joining the original CSV
and added-metric archive on every use. `recording_id` plus `unit_id` is the unique
unit key. Unit IDs alone can repeat between recordings. `construct` is metadata,
never a predictor. Missing raw measurements remain missing in the frozen table.

The stored LDA is the descriptive full-data fitted model. Its transform applies
signed `log1p`, saved median imputation, saved standardization, then the saved LD
projection. Loading does not retrain or change metrics. Its fitted classifications
are not held-out validation predictions.

## Load metrics and LD coordinates

Use the established Python environment:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/envs/axion-kilosort/bin/python
```

The loader is [load_mcs_locked_lda.py](../scripts/load_mcs_locked_lda.py).
It verifies frozen artifacts against checksums in the repo configuration.

```python
import sys
sys.path.insert(0, "/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/scripts")
from load_mcs_locked_lda import load_units, project_units

metadata, metrics = load_units()
print(metrics.shape)  # (1554, 215): raw values in documented measurement units
print(metadata[["recording_id", "unit_id", "construct"]].head())

ld_coordinates, fitted_classes = project_units(metrics)
print(ld_coordinates.shape)  # (1554, 2): LD1 and LD2
```

`pandas.read_csv(path, dtype={"unit_id": str})` also reads the `.csv.gz` directly.
Do not feed identity or construct columns into LDA. Use the active JSON's exact
feature list. For one unit, filter both `recording_id` and `unit_id`; index the
metric table by exact catalog/configuration names.

The [recording biology CSV](mcs_recording_biology.csv) links recording identity
to source files, saved sorting outputs, duration, unit counts, and event times.

## Channel/unit post-minus-pre heatmap

The requested figure and numerical data are:

```text
estim_channel_unit_delta_heatmap.png
estim_channel_unit_deltas.csv
estim_channel_unit_delta_provenance.json
```

This is firing-rate change, not LD score:

- 5-second delta = rate in [0,+5) minus rate in [−5,0).
- 10-second delta = rate in [0,+10) minus rate in [−10,0).
- Unit channel = most-negative average saved template channel.
- Channel color = **mean unit delta** across units assigned to that channel.
- Unit color = individual-unit delta, with one row per unit.
- Shared symmetric-log scale: red increase, blue decrease, white zero;
  gray means no assigned units rather than a measured zero response.

There is one illustrative recording per construct, including Control, selected
by largest unit count among eligible recordings; recording identity breaks ties.
Response magnitude does not affect selection. The provenance JSON gives every
recording, source analyzer, geometry status, and mean delta. These are not group
averages. Channel-label topology is retained; unverified physical spacing is not
presented as measured distance.

An increase after e-stim is an outcome to inspect, not an assumption for all
constructs or units. Control can respond to e-stim too. These maps alone do not
establish a chemical-treatment effect. Stimulation artifacts remain included.

## Reproduction and storage

[lock_mcs_lda_and_plot_channel_deltas.py](../scripts/lock_mcs_lda_and_plot_channel_deltas.py)
freezes chosen inputs and fitted state, checks a load/project round-trip, and
makes the single figure from existing saved metrics/templates. It does not read
or copy continuous signals. Submit computational work through Slurm with the
existing `parent0` account and `standard` partition.

Keep large outputs on scratch. Create only requested plots and compact supporting
data. The active configuration and this guide stay in the repo.

## Current illustrative recording results

These are means across units in the selected individual recordings, not construct-wide averages.

| Construct | Recording | Units | Mean 5-s delta (Hz/unit) | Mean 10-s delta (Hz/unit) |
| --- | --- | ---: | ---: | ---: |
| DREADD | `Actuators & Effectors/Stim 1/352.1/2021-06-23T11-11-59McsRecording` | 76 | +15.561 | +7.391 |
| LMO | `Actuators & Effectors/Stim 4/353.2/2021-07-30T07-41-17McsRecording` | 81 | +0.200 | -1.079 |
| PSAM | `Actuators & Effectors/Stim 4/354.1/2021-07-30T08-47-27McsRecording` | 119 | +0.412 | +0.150 |
| Control | `Actuators & Effectors/Stim 4/371.3/2021-07-30T10-02-42McsRecording` | 112 | +1.707 | -1.941 |

Frozen table and saved projection passed a round-trip check for all 1,554 units and 215 inputs. The heatmap export contains 388 unique mapped units; all delta arithmetic was checked.

## Reference-style e-stim PSTH

`estim_reference_style_psth.png` shows raw firing-rate mean ± SEM across units
for Control (473), DREADD (230), LMO (512), and PSAM (339), all within
Actuators + effectors. First STG train is t = 0; display is −10 to +10 seconds
with 0.5-second bins. SUA/MUA are pooled. Gray shading marks the 0–5-second
response-analysis window, not stimulus duration (approximately 41 ms).

`estim_reference_style_psth.csv` holds the plotted mean/SEM/bin edges/counts;
`estim_reference_style_psth_provenance.json` identifies source recordings and
timing. No baseline subtraction or smoothing is applied. The bands are unit
SD/sqrt(n), not recording-level uncertainty. Stimulation artifacts remain included.
Source: scripts/plot_mcs_reference_style_psth.py. The locked LDA inputs are unchanged.

## Current high-resolution PSTH (supersedes the coarse view)

`estim_high_resolution_psth_10ms.png` uses **10-ms bins**, 50 times finer than
the prior 0.5-second plot. The onset panel spans −0.5 to +1 second; the overview
spans −5 to +10 seconds. Curves use a Gaussian kernel with sigma 20 ms, applied
to each unit separately and independently on either side of t0 before computing
the unit mean and SEM. Thus post-stim activity is not smoothed backward across
t0. The onset y axis is linear; the overview is linear from 0–10 Hz and
logarithmic above 10 Hz. Gray marks the approximately 41-ms pulse train.

The compressed CSV `estim_high_resolution_psth_10ms.csv.gz` contains both the
raw 10-ms mean/SEM and plotted smoothed mean/SEM, with all bin edges and counts.
The companion provenance JSON records smoothing and source recording paths.
The PNG is 300 dpi. Source: scripts/plot_mcs_high_resolution_psth.py.
No LDA inputs, windows, or fitted transforms were changed.

## Pre-stim baseline exploration

The requested baseline comparison is in scratch `prestim_baseline/`. It uses
1,554 units, no post-stim descriptors, and a strict sample cutoff before the
first e-stim sample. The common coverage is 20 seconds. There are 48 scanned
rate windows and 447 baseline-only rate/burst/ISI descriptors.

`prestim_baseline_comparison.png` shows the canonical 10-second baseline, the
exploratory shared-window optimum, the complete window/Control effect sweep,
and a separate baseline-only LDA diagnostic. `baseline_rate_summary.csv` gives
raw mean/median rates and Control comparisons. `baseline_control_comparisons.csv`
contains all 1,341 metric/Control comparisons with Holm-adjusted p values and
effect sizes. The README explains differences and the window-selection rule.

The strongest shared window is −1.5 to −0.5 s. It does not provide uniform
separation across other time windows; the full sweep remains available.
Baseline-only nested held-out-unit LDA accuracy is 68.4%. This diagnostic
does not change the active 215-metric pre/post LDA or its frozen state.
Source: scripts/explore_mcs_prestim_baseline.py.

## Publication-style baseline phenotype figure

The user requested **strongest-separation conditions**, not a fixed baseline
window. The new figure therefore optimizes one shared window per metric,
maximizing the weakest absolute Cliff delta across DREADD/LMO/PSAM versus
Control. These are the selected pre-stim intervals:

| Measurement | Selected interval before t0 |
| --- | --- |
| Firing rate | −1.5 to −0.5 s |
| Burst-spike fraction (ISI ≤25 ms, ≥3 spikes) | −7 to −2 s |
| Active 1-s bins | −4 to −2 s |
| Short ISI fraction (<50 ms) | −5.25 to −5 s |
| Long-pause fraction (>200 ms) | −3 to −2 s |

Files are in scratch `baseline_publication/`: `baseline_phenotypes_mean_sem.png`
and `.pdf`, `group_mean_sem.csv`, `selected_control_statistics.csv`, and
`README.md`. Each point is a unit; black symbols show mean ± SEM. Valid unit
counts are explicit; short/long ISI measurements require at least two spikes.

Welch mean tests and robust Mann–Whitney comparisons are each Holm-corrected
over 2,061 prior/current baseline tests. There are 2,000 unit-bootstrap
replicates for pointwise 95% mean-difference and Cliff-delta intervals, and
999 unit-label permutations repeating the complete window maximization.
Selection-aware omnibus permutation p values are Holm-adjusted across the
five metrics. Stars refer specifically to corrected Welch mean tests.

The selected conditions support the DREADD bursting and LMO activity statements,
and the conditional PSAM short-ISI statement. More PSAM long pauses is not
supported at the selected shared condition. The short-ISI LMO comparison has
only four measurable units; it is not an all-512-unit ISI estimate.

The complete condition search, unit values, statistics, and claim checks are
preserved in that directory. Source: scripts/plot_mcs_baseline_publication.py.
The active 215-input LDA and its frozen artifacts remain unchanged.

## Post-stim counterpart and paired baseline changes

The post-stim publication figure is in scratch `poststim_publication/` as
`poststim_phenotypes_mean_sem.png` and `.pdf`. The upper row shows absolute
post levels; the lower row shows each unit's post-minus-pre change. Each metric
selects its strongest shared post window; its baseline is the mirrored interval
of identical duration. Change values are not separately re-optimized.

The selected post windows are 0–5 s for rate, 0.25–5.25 s for burst-spike
fraction, 0.5–2.5 s for occupancy, 1–1.5 s for short ISIs, and 2–7 s for pauses.
Percent denominators are explicit; changes are percentage points. All dots are
units, SUA/MUA pooled. Mean ± SEM and corrected Control comparisons are shown.

`unit_mean_sem_and_paired_tests.csv` includes actual paired-unit counts, paired
means, changes, confidence intervals, paired t tests and Wilcoxon tests.
`selected_control_tests.csv` contains post-level and change comparisons against
Control. `selected_unit_pre_post.csv` supplies the plotted unit data. The README
and summary.json document 4,111-comparison correction and 999 selection-aware
permutations. Stimulation artifacts remain included.

All groups increase firing rate versus their own pre baseline in 0–5 s;
DREADD's increase exceeds Control, LMO's is not significantly different from
Control, and PSAM's is smaller than Control. The short-ISI paired-change panel
has a small conditional subset (including only six Control units).
Source: scripts/plot_mcs_poststim_publication.py. The frozen 215-input LDA is unchanged.

## Combined targeted post-stim figure with effects and locked LDA

The user chose to add the **locked 215-input model** to the targeted figure,
without retraining or replacing it. The five phenotype metrics are now
registered in `mcs_targeted_poststim_metrics.json`. See
[MCS_TARGETED_POSTSTIM_FIGURE.md](MCS_TARGETED_POSTSTIM_FIGURE.md) for the exact
windows, panel-by-panel sources, definitions, effect directions, statistics,
model transform, and join examples for future analyses.

The combined PNG/PDF, exact LD coordinate table and checksum manifest are in
scratch `poststim_publication/targeted_figure/`. The added bottom row contains
post-level effects versus Control, paired-change effects versus Control, and
the unchanged 87-original + 128-burst LDA. No statistics were recomputed.
