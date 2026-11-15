# Targeted post-stim phenotypes, effect sizes, and locked LDA

## Current decision

Use the five displayed phenotypes as the **targeted analysis set**. The user
explicitly chose the **existing locked 215-metric LDA** for the added bottom
panel. Its 87 original + 128 burst inputs, fitted state, and orientation remain
unchanged. The five displayed phenotypes are not the complete LDA input list.

Each dot is one sorted unit; SUA/MUA are pooled. All 1,554 units belong to
**Actuators + effectors**: Control 473, DREADD 230, LMO 512, PSAM 339. Dates do
not define groups. The first STG train starts at t = 0.

The machine-readable targeted registry is
[mcs_targeted_poststim_metrics.json](mcs_targeted_poststim_metrics.json).
The locked model is specified independently by
[mcs_active_lda_configuration.json](mcs_active_lda_configuration.json).

## Targeted definitions and selected intervals

| Metric | Post interval (s) | Paired pre interval (s) | Definition |
| --- | --- | --- | --- |
| Firing rate | 0 to 5 | −5 to 0 | Spike count divided by interval duration, Hz/unit. |
| Burst-spike fraction | 0.25 to 5.25 | −5.25 to −0.25 | Spikes in maximal runs of adjacent ISIs ≤25 ms and ≥3 spikes, divided by all spikes. |
| Active-bin fraction | 0.5 to 2.5 | −2.5 to −0.5 | Complete 1-s bins with at least one spike, divided by all complete bins. |
| Short-ISI fraction | 1 to 1.5 | −1.5 to −1 | Adjacent ISIs <50 ms, divided by all measurable ISIs. |
| Long-pause fraction | 2 to 7 | −7 to −2 | Adjacent ISIs >200 ms, divided by all measurable ISIs. |

Intervals are half-open: include the start, exclude the end. Post intervals were
selected from 41 candidates inside 0–10 s, maximizing the weakest absolute Cliff
delta among DREADD/LMO/PSAM versus Control. The figure reuses the **saved selected
intervals**; composition does not search again. Changes use the same selected
post interval and its mirror around t0; changes are not separately optimized.

For a unit, change = post − its own pre. Raw fractions are 0–1. The upper row
displays percentages; the second row displays **percentage points**, not relative
percent changes or fold changes. Rate changes remain Hz/unit.

Silent units have rate/active-bin/burst-spike fraction zero. ISI fractions require
at least two spikes in the relevant interval; otherwise they remain missing.
Paired ISI changes require measurable intervals on both sides. No missing ISI
is filled with zero in descriptive panels. Valid unit counts are displayed.

## Panel-by-panel data sources

The source directory is:

```text
/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/poststim_publication/
```

| Panels | Source | Computation |
| --- | --- | --- |
| a–e | `pre_post_all_windows.npz`, array `after`; `selected_conditions.csv` | Same saved post values, finite-unit means/SEMs, counts, and renderer as the previous figure. |
| f–j | Same archive, array `change` | Same-unit `after − before` at the same selected intervals. |
| Stars in a–j | `selected_control_tests.csv` | Saved Welch tests versus Control, mode `post` or `change`, Holm-adjusted over 4,111 prior/current hypotheses. |
| k | Same statistics CSV, rows `mode=post` | Saved `cliff_delta`, `cliff_ci_low`, `cliff_ci_high`, ordered by metric and construct. |
| l | Same statistics CSV, rows `mode=change` | Same effect-size fields applied to paired changes versus Control changes. |
| m | Frozen `locked_lda_215/active_215_unit_metrics.csv.gz` and `active_215_lda_state.npz` | Apply saved transform and join by recording ID + unit ID; no retraining, reselection, or rotation. |

`unit_mean_sem_and_paired_tests.csv` contains the exact means/SEMs, valid counts,
paired t tests, Wilcoxon checks, and within-group change intervals.
`selected_unit_pre_post.csv` is the simplest table of the plotted unit values.

Every unit is matched by **recording_id + unit_id**. Unit IDs alone can repeat
between recordings. The renderer verifies source archive order, selected CSV
values, the paired-change arithmetic, and the locked-model unit identities.

## Magnitude and direction of effects

Panels k/l use **Cliff delta**:

```text
δ = P(actuator value > Control value) − P(actuator value < Control value)
```

It ranges from −1 to +1. It is a rank effect size, not a percent change, a mean
Hz difference, or an LD loading. In k, positive means larger post-stim values.
In l, positive means larger post-minus-pre changes than Control. Negative change
effects can describe a **smaller increase**, not necessarily a decrease from the
unit's own baseline. For example, PSAM's rate increases on average, but less than
Control's rate increase.

Bars are the previously saved **pointwise 95% percentile unit-bootstrap
intervals**, using 2,000 resamples. They are not selection-adjusted simultaneous
intervals. Mean tests and rank effect intervals answer different questions;
an interval can exclude zero while the corrected mean test is `ns`.
Raw mean differences and their confidence intervals remain in the statistics CSV.

## LDA computation and access

Panel m applies the frozen descriptive full-data fit:

1. Load the exact selected 87 original + 128 burst metrics in stored order.
2. Apply signed log1p, the saved imputation medians, and saved centering/scaling.
3. Multiply by the saved two-column LD projection matrix.
4. Color the resulting unit coordinates by construct.

Source loader: [load_mcs_locked_lda.py](../scripts/load_mcs_locked_lda.py).
There is no new feature selection, classifier fitting, projection rotation, or
new validation score in this panel. Its clouds are supervised full-data fitted
coordinates. Ellipses show **one-SD unit spread**, not confidence intervals.

The targeted registry also lists the five post fields plus five change fields
as a possible 10-feature targeted view. This version does **not** fit or display
that alternative: the user chose the locked 215-input model. It is retained only
as a clear mapping from the phenotype panels to their raw columns for future work.

## Outputs and provenance

The combined figure is saved under the source directory in `targeted_figure/`:

```text
targeted_poststim_effects_lda.png
targeted_poststim_effects_lda.pdf
lda_unit_coordinates.csv
figure_manifest.json
```

The manifest lists per-panel source files, row/array filters, model state, and
SHA256 hashes for numerical inputs, registry, renderer code, and generated
outputs. The coordinate CSV identifies each unit and its exact LD1/LD2 values.
The previous figures and numerical sources are retained. No continuous signals
or metric matrices are duplicated for this composition.

Renderer:
[compose_mcs_targeted_poststim_figure.py](../scripts/compose_mcs_targeted_poststim_figure.py).
Submit it through Slurm in the established environment with
`--lda-input locked215`. It reuses
[plot_mcs_poststim_publication.py](../scripts/plot_mcs_poststim_publication.py)
for the first ten panels. Numerical statistics and bootstrap intervals are read
from saved results, not recomputed during composition.

Stimulation artifacts remain included. The data support exploratory unit-level
comparisons; effect plots or supervised LDA alone do not establish chemical
treatment causation. Keep future outputs on scratch and generate only requested
plots/data.

## Joining targeted phenotypes to LD coordinates for follow-up

Use the shared unit key rather than row positions or unit IDs alone:

```python
import pandas as pd
from pathlib import Path

root = Path("/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/poststim_publication")
coordinates = pd.read_csv(root / "targeted_figure/lda_unit_coordinates.csv",
                          dtype={"unit_id": str})
phenotypes = pd.read_csv(root / "selected_unit_pre_post.csv",
                         dtype={"unit_id": str})
joined = coordinates.merge(phenotypes,
    on=["recording_id", "unit_id", "construct"], validate="one_to_one")
assert len(joined) == 1554
```

The joined frame provides LD1/LD2 and the targeted pre, post, and change
measurements without refitting LDA. Retain missing descriptive ISIs when
examining individual phenotype relationships; do not silently substitute the
LDA-imputed values for the raw measurements. No joined duplicate table is
saved automatically.
