# Separate activity-signature and temporal-decoding figure

**Current preferred figure:** see [MCS_PAPER_LAYOUT.md](MCS_PAPER_LAYOUT.md).
Its temporal decoder now uses equal class priors in `paper_layout/balanced_decoder/`.
The empirical-prior results below describe the original temporal analysis and
are preserved as provenance; the locked 215-feature LDA is unchanged.

Inspired by the activity-signature and decoding organization of
[Kochalka et al., Fig. 3](https://pmc.ncbi.nlm.nih.gov/articles/PMC13232143/#F3).
This is an adaptation to electrical-stimulation-aligned sorted units, not a
replication of directional behavior elements, injection responses, minute-wise
observations, or optogenetic source/sink experiments.

## Scope and time axis

Actuators + effectors only; 1,554 sorted units pooled across SUA/MUA: Control
473, DREADD 230, LMO 512, PSAM 339. The same units are followed through all bins.
Group assignment follows the biological mapping, never the recording date.
Time zero is the first STG electrical-stimulation train in each recording.

Twenty non-overlapping, half-open **1-second bins cover −10 to +10 seconds**.
There is no temporal smoothing. These are seconds, not the reference's minutes.
Burst computations use only spikes inside a bin, so bursts spanning boundaries
are truncated; gaps spanning bins are not measured. This boundary convention
is identical before and after stimulation and is not a continuous burst trace.
No electrical artifact blanking is applied.

## Six local measurement types

The model uses these same six types at every time. They adapt the six selected
interpretive patterns to equal-duration local bins; their numerical values are
not the frozen model's original unequal-window feature columns.

| Measurement | Definition in each 1-s bin |
| --- | --- |
| Firing-rate change | Bin firing rate minus that unit's −5 to 0 s firing rate, Hz/unit. |
| Fast bursts per second | Number of bursts with consecutive spike gaps ≤10 ms and ≥3 spikes, divided by 1 s. |
| Average burst duration | Mean last-minus-first spike time for bursts with gaps ≤100 ms and ≥5 spikes. |
| Firing rate | Bin spike count divided by 1 s, Hz/unit. |
| Delay to first burst | First burst onset minus bin start, for gaps ≤100 ms and ≥3 spikes. |
| Pause between bursts | Mean time from a burst's last spike to the next burst's first spike, gaps ≤50 ms and ≥3 spikes. |

Silent units have rate and burst count zero. Duration and first-burst delay
require a qualifying burst; mean pause requires two qualifying bursts. Missing
values remain missing in traces and are imputed only inside the fitted decoder.
Thus means of burst duration/pause are conditional on measurable units;
`activity_mean_sem.csv` records their exact valid denominators in every bin.

Baseline subtraction uses each unit's saved spike train, not group labels.
The −5 to 0 s reference contains information from other pre-stim bins; this is
an offline retrospective analysis, not a causal online decoder available before
the baseline has completed.

## Panels

- **a–d:** Firing rate, fast burst rate, burst duration, and interburst pause
  versus time; finite-unit mean ± SEM. Displayed SEM is descriptive unit-level
  spread/√n, not recording-level uncertainty or a significance test.
- **e–h:** One six-measurement time heatmap per group. Subtract the group's
  pre-stim mean (average of each unit's finite pre-bin mean), then divide by
  the pooled across-group standard deviation of unit/bin pre-stim values for
  that measurement. This shared scale is fixed across all groups. These are
  changes from own-group baseline, not absolute group differences. Symmetric
  colors saturate at the 98th percentile of absolute heatmap values, with a
  minimum limit of 0.25 baseline SD; untruncated values are exported.
- **i:** The exact, unchanged locked 215-metric LD1/LD2 unit projection, with
  group centroid stars. This panel uses the previously frozen full-data model.
- **j:** Same-time, out-of-fold one-vs-rest AUROC for each group and their
  macro average. Chance AUROC is 0.5.
- **k:** Row-normalized confusion matrix, averaging each held-out unit's
  predicted class probabilities over the five 0–5 s bins, then taking one
  class prediction per unit. Thus each unit contributes once, not five times.
- **l:** Cross-time macro AUROC. Row = time used to train; column = time used
  to test. Each time-pair is scored on held-out units with fixed partitions.
  Colors cover 0.5–1; values below 0.5, if present, saturate at the low end and
  remain available in the CSV.

## Temporal decoder and validation

This is a **separate six-feature temporal LDA**, not a replacement or repeated
fit of the locked 215-feature model. Signed log1p, training-fold median
imputation, and training-fold standardization precede LDA (`solver=lsqr`,
`shrinkage=0.01`). No temporal-window or feature search is performed here.
All-empty training features are retained and filled with zero by the imputer.

Three stratified unit folds use seed 20261114. The same unit partitions apply
at every training/testing time. A test unit never appears at any training time
within its fold. Preprocessing is fitted exclusively on that fold's training
units at the source time and applied unchanged to every testing time.

Units from the same recording may appear in training and test folds, consistent
with the requested unit-level exploratory analysis. Scores may therefore
recognize recording differences and do not establish generalization to new
recordings or biological replicates. The six measurement types were chosen
after earlier full-data exploration; this is not independent confirmation of
the feature-selection process. Baseline decoding can be high if groups already
differ before stimulation. No rise in accuracy, drug effect, significance, or
cross-time stability is assumed in advance.

## Observed exploratory results

The mean same-time macro AUROC is 0.688 before stimulation and 0.691 after
stimulation. The small difference is descriptive, not a tested stimulation
effect. Averaging each unit's predictions over 0–5 s produces macro AUROC
0.833 and balanced accuracy 0.536. These are different summaries: the latter
requires selecting one of four classes. The confusion matrix shows particularly
poor PSAM recall (about 10%); a high overall ranking score does not imply
accurate separation of all four classes. No sustained post-stim improvement or
near-perfect decoding is claimed. The locked 215-feature projection is a
different model with different input windows and a full-data descriptive fit;
its visually separated clouds are not a validation result for this decoder.

## Files

Scratch directory:

```text
/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/temporal_signatures/
```

- `temporal_activity_and_decoding.png` / `.pdf`: separate figure.
- `unit_window_metrics.npz`: 1,554 × 20 × 6 raw values, with unit keys and bins.
- `activity_mean_sem.csv`: per-group, per-bin measurement summaries/counts.
- `activity_heatmap_values.csv`: exact normalized heatmap cells.
- `time_resolved_decoding.csv`: per-time AUROCs and balanced accuracy.
- `cross_time_macro_auroc.csv`: full training-time × testing-time matrix.
- `poststim_confusion_matrix.csv`: row-normalized 0–5 s confusion matrix.
- `unit_folds_and_predictions.csv`: unit identities, fold IDs, post predictions.
- `summary.json`: settings, sources, checksums, group counts, headline scores.

Join unit tables with **recording_id + unit_id**. Renderer:
[plot_mcs_temporal_signatures.py](../scripts/plot_mcs_temporal_signatures.py).
All measurements come directly from saved curated sorting spike times and the
existing first-STG metadata. No continuous recordings are duplicated. The
reference-style locked-model figure and original model files remain unchanged.
