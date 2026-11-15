# Evolving unit group probabilities from ordered responses

The requested view is **how each unit's predicted group evolves as its
post-stimulus response unfolds**, alongside observed response trajectories.
This separate figure replaces neither the locked 215-feature descriptive LDA
nor the earlier snapshot decoder. It directly displays unit-level predictions,
rather than only a curve of decoding accuracy.

## Temporal input and prediction

The same 1,554 Actuators + effectors units are followed from 0 to 10 seconds
after the first STG train. Raw spikes are counted in half-open 100-ms bins.
The extraction reproduces every unit's earlier −5–0 and 0–5 s firing rates.

At endpoint 0.1 s, the input is the ordered response in [0,0.1). At 0.2 s,
it is [0,0.1), [0.1,0.2). At 1 s there are ten ordered bins; at 10 s there
are 100. **Only spikes available by the current endpoint enter its prediction.**
Subtract each unit's pre-stimulus −5–0 s mean rate from every post bin, then
apply signed log1p. Standardization is fitted only on training units. This
removes a constant firing offset but does not guarantee removal of all
baseline, recording, or cell-specific information.

An LDA is fitted at each growing prefix (`solver=lsqr`, shrinkage 0.01,
equal priors 0.25). The input columns retain their ordered time positions,
so the classifier can assign different weights to early and late activity.
This is a sequence of prefix classifiers, not one recurrent model, and
prediction changes reflect both the added evidence and the prefix-specific
fitted classifier. It differs from the earlier model that used only a single
local window at each time without the preceding response trajectory.

Three stratified unit folds, seed 20261114, remain fixed across all 100
endpoints. Every plotted probability for a unit is from a classifier that
excluded that unit at every prefix. Units from a recording can still occur
in both training and testing; these results describe exploratory unit-level
recognition, not generalization to unseen recordings or biological replicates.
The locked 215-feature model is not modified or used for these predictions.

## How to read the figure

Each column is the unit's **actual biological group**.

- **a–d:** Observed firing responses, mean and pointwise `mean ±1.96 SEM`.
  A Gaussian sigma 100 ms smooths each unit's firing trace for display only.
  This display smoothing may use later post bins; it never enters the decoder.
- **e–h:** Four predicted-group probability traces per actual group, with
  consistent Control/DREADD/LMO/PSAM colors. Lines average the held-out
  unit probabilities; bands are pointwise `mean ±1.96 SEM`, clipped to [0,1].
  A high red line in the PSAM column means PSAM units are being assigned to
  DREADD. A rising purple line means confidence in PSAM is increasing as
  more response history becomes available.
- **i–l:** Every unit's probability of its actual group over time. One row
  is one unit. Rows retain recording/unit order; white lines mark recording
  boundaries. Bright rows represent confident correct-group scores; dark rows
  mean low probability of the true group. Rows are never sorted to improve
  the appearance of separation.

The dotted 0.25 line in probability panels is the equal-prior reference, not
a shuffled null. This figure displays probabilities, not shuffled AUROC. The
earlier paper-layout AUROC panel retains its own matched permutation null;
that null is not transferred to this different model. Decoder probabilities
are uncalibrated model scores, not probabilities that a biological mechanism
is present, and there is no imposed monotonic rise after stimulation.
Electrical-stimulation artifacts remain included.

## Timing versus firing-rate magnitude

A matched **rate-only** LDA uses one scalar at each endpoint: mean firing-rate
change over [0,current endpoint). Its probabilities and performance are saved
alongside the ordered-prefix outputs. This comparison asks whether keeping
time-bin structure improves descriptive unit recognition beyond the mean
response in the same time support. Both models use the same folds, baseline
reference, and class priors. No feature or endpoint optimization is performed.
No permutation significance claim is made for the comparison.

Observed held-out-unit results for the ordered-prefix model:

| Available history | Macro AUROC | Balanced accuracy | PSAM recall |
| --- | --- | --- | --- |
| 1 s | 0.811 | 59.1% | 31.3% |
| 5 s | 0.955 | 80.1% | 82.0% |
| 10 s | 0.972 | 84.0% | 87.3% |

The matched rate-only model's macro AUROCs are 0.620, 0.632, and 0.589 at
these endpoints. Thus keeping the ordered response bins supplies more group
recognition information here than a single average rate-change scalar.
This comparison does not independently prove a biological timing mechanism;
recording-specific burst timing and network dynamics can also supply such
information. White recording boundaries in the maps make those patterns
visible rather than hiding them. DREADD probabilities rise early, whereas
Control/LMO/PSAM predictions generally gain confidence over a longer history.
These values belong to the new prefix model and are not revisions of the
old six-feature snapshot model's performance.

## Files and access

```text
/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/trajectory_decoder/
```

- `unit_response_probability_trajectories.png` / `.pdf`: figure.
- `unit_100ms_spike_counts.npz`: ordered unit counts over −10 to +10 s.
- `extraction_manifest.json`: input recording paths, counts, checksums.
- `unit_probability_trajectories.npz`: every unit's four held-out probabilities
  at every endpoint, plus the matched rate-only probabilities.
- `unit_trajectory_index.csv`: unit keys, fold IDs, predictions and true-group
  probabilities at 1, 5, and 10 s.
- `probability_time_courses.csv`: the class-probability means and intervals.
- `response_time_courses.csv`: the firing-response means and intervals.
- `trajectory_decoding_performance.csv`: ordered-prefix versus rate-only AUROC
  and ordered-prefix balanced accuracy at each endpoint.
- `trajectory_model_manifest.json`: exact model settings, source/output hashes,
  and selected-endpoint confusion matrices.

Probability array shape is `(unit, endpoint, predicted_class)`; endpoint times
and class order are stored in the same archive. Use **recording_id + unit_id**
to identify a unit. Group labels and fold IDs accompany the probability arrays.

```python
import numpy as np
p = np.load('unit_probability_trajectories.npz')
unit_index = 0  # Resolve using recording_id AND unit_id first.
times = p['time_s']
probability_trace = p['probabilities'][unit_index]  # 100 endpoints × 4 groups
class_order = p['class_order']
```

Scripts: [extract_mcs_unit_trajectories.py](../scripts/extract_mcs_unit_trajectories.py)
and [decode_mcs_unit_trajectories.py](../scripts/decode_mcs_unit_trajectories.py).
