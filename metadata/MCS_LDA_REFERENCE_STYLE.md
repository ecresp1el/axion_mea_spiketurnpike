# Reference-style figure for the locked unit LDA

Scope: **Actuators + effectors** only; Control 473, DREADD 230, LMO 512,
PSAM 339. Each observation is one sorted unit (1,554 total); SUA/MUA are pooled.

## Figure panels

**a. Metric–LD structure coefficients.** Pearson correlations between each
actual preprocessed model input and each frozen LD score, across all 1,554 units.
Inputs undergo the exact saved signed-log1p transform, median imputation, and
standardization. These are correlations, not classifier weights or independent
causal contributions. Warm colors indicate positive correlations; cool colors
indicate negative correlations. The displayed rows are curated representatives of distinct activity patterns:
early firing-rate change, fast baseline bursting, post-stim burst duration,
early post-stim firing level, time to first post-stim burst, and post-stim
interburst pauses. Repeated threshold/minimum-spike variants and overlapping
spike-fraction summaries are omitted to reduce repetition. This is a descriptive
interpretation set, not a top-N ranking or a claim of optimal independent
importance. Each row has a saved selection rationale. This display selection
does not change the 215-feature model.
The complete 215-row coefficient table is exported alongside the figure.
Constant inputs have undefined correlations and are excluded from display ranking.
Displayed labels use plain English and explicitly state the measurement window,
maximum adjacent-spike gap, and minimum spike count for each burst definition.
The displayed-coefficient CSV preserves both the original key and English label.

**b. Unit projections.** Exact frozen LD1/LD2 coordinates, colored by construct.
Stars mark the arithmetic group centroids. Each dot is one unit, not a minute
or a recording. No coordinates are refitted, rotated, or shifted to separate groups.

**c/d. Axis distributions.** Each unit's LD1 or LD2 score, displayed as jittered
dots with a lightly shaded Gaussian-kernel violin (Scott bandwidth). Horizontal
black bars are group means. Smoothing affects the displayed density only;
all dots, coordinates, and means use the original values.

## Interpreting LD1 and LD2

Each axis is a weighted combination of the 215 preprocessed measurements. Its
score has arbitrary model units; neither axis is a direct firing rate, burst
rate, nor a single biological mechanism. The structure correlations provide an
interpretation of the existing coordinates without fitting a different model.

- Higher LD1 correlates with a larger 0.25–0.5 s firing-rate change (r=0.675),
  longer average 0–5 s bursts under the 100 ms / five-spike definition (r=0.526),
  and fewer baseline 10 ms / three-spike bursts per second (r=−0.493).
- Higher LD2 correlates with more 0.5–1 s firing (r=0.508), a shorter delay to
  the first burst within 0.5–10 s under the 100 ms / three-spike definition
  (r=−0.565), and shorter average post-stim interburst pauses (50 ms / three
  spikes, 0–10 s; r=−0.460).

These statements describe pooled associations, including effects of correlated
features, group differences, and the model's saved imputation. They are not
independent feature effects or causal explanations. The `late` window in
original feature keys means **0.5–10 s**, not 5–10 s. First-burst latency is
measured relative to the start of its window. Peak firing time uses the
midpoint of the largest of 20 bins over the stated search interval.

## Relationship to the supplied reference

This adapts the reference's structure-coefficient, projection, and distribution
panels to the existing 215-feature unit model. The reference's minute-wise
directional behavior elements and their transition matrices are different
observations from these unit features. No directional-element events, event
thresholds, injection times, transition matrices, or permutation significance
marks are invented for this figure. Alignment remains to the first STG train;
the frozen features summarize pre/post intervals around that train.

The saved model contains two projection axes. LD3 is not stored and is not
generated through a new fit. All displayed points are from the previously
locked supervised full-data descriptive model, not independent validation.
Axis signs are inherited unchanged from that model. Correlations pool all
groups and can reflect between-group and within-group variation.

## Files and access

Output directory:

```text
/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/lda_reference_style/
```

- `locked_215_lda_reference_style.png` and `.pdf`: figure.
- `structure_coefficients_all_215.csv`: all feature–LD Pearson correlations.
- `displayed_structure_coefficients.csv`: the subset shown in panel a.
- `unit_ld_coordinates.csv`: recording ID, unit ID, construct, LD1, LD2.
- `axis_group_summaries.csv`: counts, means, standard deviations, and medians.
- `manifest.json`: source paths/checksums, output checksums, display rule.

Join unit tables using **recording_id + unit_id**, not unit ID alone.

Model configuration: [mcs_active_lda_configuration.json](mcs_active_lda_configuration.json).
Model access guide: [MCS_ACTIVE_LDA_ACCESS.md](MCS_ACTIVE_LDA_ACCESS.md).
Renderer: [plot_mcs_lda_reference_style.py](../scripts/plot_mcs_lda_reference_style.py).

The renderer verifies the model/raw-table hashes and checks that the frozen
preprocessing and projection reproduce the loader's coordinates to tolerance
1e-12. The model state and raw table are never overwritten.

The Desktop transfer bundle also contains a copy under `lda_reference_style/`;
major analysis outputs remain on scratch.
