# Handoff: CytoView Dorsal/Ventral Reviewer FSU/RSU and Burst Figure

Date drafted: 2026-07-10 EDT

## Objective

Build a publication-quality, reviewer-facing analysis of the current CytoView
dorsal/ventral cohort that addresses both:

1. the apparent FSU/RSU ratio; and
2. the previously incomplete burst analysis.

The requested quantitative endpoints are:

- unit firing-rate distributions;
- overall mean firing rate per recording/well;
- burst rate;
- mean firing rate within bursts;
- burst duration;
- spikes per burst;
- interburst interval; and
- fraction of spikes occurring in bursts.

This document records the completed input audit and the analysis contract for
the next implementation/figure iterations. It does not claim that the pilot
burst numbers below are final biological results.

## Ultimate Supplementary Figure Goal

Working title:

> **Supplementary Figure X. Quality control, classification, and spontaneous
> network activity of extracellularly recorded regular-spiking (RS) and
> fast-spiking (FS) units in dorsal and ventral forebrain organoids.**

Ultimate content, without locking the final layout yet:

- **A:** schematic of trough-to-peak duration, waveform asymmetry, and
  repolarization slope, plus the corresponding multidimensional waveform
  feature space;
- **B:** mean +/- SEM RS and FS waveforms and normalized individual waveforms
  overlaid on their population means;
- **C:** trough-to-peak distribution for all classified units, including a
  measurement inset;
- **D:** waveform stability, representative ACGs/CCGs, and spatial footprints
  supporting stable isolation and absence of duplicate unit detection; and
- **E:** dorsal/ventral spontaneous activity, including overall mean firing
  rate, burst rate, mean firing rate within bursts, burst duration, interburst
  interval, and spikes per burst.

The previously requested fraction of spikes occurring in bursts remains a
required computed/source-data endpoint even if it is ultimately placed in an
additional panel or supplementary source table.

## Locked Waveform Classification Contract

The following choices are now authoritative for panels A-C and for the class
labels merged into panel E:

```text
waveform state = spike-snippet aligned before feature extraction
FS = aligned trough-to-peak duration <= 0.50 ms
RS = aligned trough-to-peak duration > 0.50 ms
classification = binary; no borderline class in the publication view
```

Alignment must use the established 2026-07-09 method:

1. use the persisted `random_spikes` selection from each Step 1 analyzer;
2. use the same sampled snippets before and after alignment;
3. fix the best channel from the persisted `templates.average` maximum-PTP
   channel;
4. align each snippet's local trough to the template trough sample; and
5. average the aligned snippets before calculating TTP, waveform asymmetry,
   repolarization slope, or any other waveform feature.

The multidimensional feature space in panel A is a visualization/validation of
the aligned waveform phenotypes. The operational FS/RS label is the explicit
aligned 0.50-ms TTP threshold above unless a later user instruction changes
the classifier itself. This distinction must be clear in the legend and
methods.

Panel-specific carry-over:

- **A:** calculate TTP, waveform asymmetry, and repolarization slope from the
  aligned mean waveform; draw the measurement schematic from the same feature
  definitions.
- **B:** group waveforms using the aligned 0.50-ms binary label. The top traces
  show unnormalized uV mean +/- SEM; the bottom traces show each aligned
  waveform normalized to its own trough magnitude, with the class mean
  overlaid.
- **C:** plot the aligned TTP distribution and draw the FS/RS boundary at
  0.50 ms. The inset must illustrate the same aligned TTP measurement.
- **E:** burst detection uses spike times and is not changed by waveform
  alignment, but every RS/FS-stratified activity summary must merge the aligned
  0.50-ms class label by exact recording/well/unit key.

For implementation, the aligned feature columns are:

```text
TTP = after_trough_to_peak_duration_ms
waveform asymmetry = after_waveform_asymmetry
repolarization slope = after_post_trough_rebound_slope_uV_per_ms
```

Here, repolarization slope means post-trough rebound amplitude divided by the
trough-to-rebound-peak duration, matching the canonical waveform-feature
definition. It is not the separate REP50 recovery-slope metric.

Current coverage caveat: the existing CytoView alignment audit contains 237
`KSLabel=good` units only. It does not contain the 1,105 MUA units. The next
metrics job must rerun
`scripts/audit_waveform_alignment_before_feature_extraction.py` using the full
1,342-row CytoView unit table and `--kslabel all`. Units failing the prespecified
minimum aligned-snippet requirement must be enumerated rather than silently
dropped. Good and MUA rows remain separate strata after classification.

## Current Audit Result

All required sorted-unit spike data are currently readable from the Step 1
CytoView `SortingAnalyzer` assets.

| Audit item | Result |
|---|---:|
| Analyzer/well rows | 52 |
| Analyzer paths readable | 52 / 52 |
| All sorted units | 1,342 |
| `KSLabel=good` units | 237 |
| `KSLabel=mua` units | 1,105 |
| Units matched back to live sorting | 1,342 / 1,342 |
| Exported/live spike-count mismatches | 0 |
| Total accessible spikes | 1,190,516 |
| Sampling frequency | 12,500 Hz for all analyzers |
| Recording durations | 453.75, 525.00, 602.75, or 624.75 s |
| Analyzer load errors | 0 |

Authoritative biological identity rule: **one well contains one organoid**.
Because each accepted spike-bearing version remains a separate recording, the
unique analysis observation is the full recording-version identifier plus its
well. The current ready set therefore contains 52 recording/well organoid
observations: 23 dorsal and 29 ventral. Fifty of these contain at least one
`KSLabel=good` unit; all 52 contain at least one `KSLabel=mua` unit.

There are no matching Axion `_electrode_burst_list.csv` or
`_network_burst_list.csv` sidecars in the uploaded dorsal/ventral CytoView
cohort. All reviewer-facing burst metrics must therefore be recomputed from the
persisted Kilosort/SpikeInterface unit spike trains. This is feasible without
rerunning Kilosort.

## Frozen Input Sources

Canonical Step 1 root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest
```

Primary unit metadata and analyzer pointers:

```text
cytoview_dorsal_ventral_step1_20260709_unit_metrics.csv
cytoview_dorsal_ventral_step1_20260709_provenance.json
step1_v5_well_ground_truth.csv
```

Region assignment sources:

```text
cytoview_platemap_dorsal_ventral_priority_20260709.csv
cytoview_platemap_dorsal_ventral_priority_20260709_batch_plan.csv
cytoview_dorsal_ventral_region_overrides_20260709.csv
```

Existing good-unit alignment/cutoff source:

```text
waveform_alignment_feature_audit_20260709_cytoview/
cytoview_dv_alignment_cutoff_composite_20260709/
```

Each row of `cytoview_dorsal_ventral_step1_20260709_unit_metrics.csv` carries
the exact `analyzer_path`. Spike times must be loaded from that analyzer's
sorting using `sorting.get_unit_spike_train(unit_id)` and divided by the
analyzer sampling frequency.

## Dorsal/Ventral and KSLabel Audit

Final region calls include the manual correction layer.

| Final region | `KSLabel=good` | `KSLabel=mua` | Total |
|---|---:|---:|---:|
| Dorsal | 113 | 522 | 635 |
| Ventral | 124 | 583 | 707 |
| Total | 237 | 1,105 | 1,342 |

Current firing-rate audit across all accepted spike-bearing recording versions:

| KS label | Region | Units | Unit median Hz | Unit mean Hz | Wells with label | Median well-mean Hz | Mean well-mean Hz |
|---|---|---:|---:|---:|---:|---:|---:|
| good | Dorsal | 113 | 0.5047 | 0.8129 | 22 | 0.5287 | 0.6304 |
| good | Ventral | 124 | 1.4010 | 1.7603 | 28 | 1.5499 | 1.5670 |
| MUA | Dorsal | 522 | 0.1629 | 2.0241 | 23 | 0.1249 | 1.0170 |
| MUA | Ventral | 583 | 0.0198 | 1.6087 | 29 | 1.0778 | 1.5251 |

These summaries preserve every current spike-bearing recording version as a
separate recording. No primary/filter/BroadbandProcessor deduplication is
applied.

All 635 dorsal unit rows come directly from the plate-map plan. Of the 707
ventral rows, 551 come directly from the plan and 156 are assigned by the
manual override. The override applies to `134-0150`, recording
`h1_dorsal_and_ventral_exp17_2(001)`, wells `B1` and `B2`. Their original plan
call was dorsal; their authoritative final call is ventral.

The current conservative waveform classes are:

| KS label | Region | FSU-like | Borderline | RSU-like |
|---|---|---:|---:|---:|
| good | Dorsal | 6 | 4 | 103 |
| good | Ventral | 3 | 9 | 112 |
| MUA | Dorsal | 57 | 45 | 420 |
| MUA | Ventral | 96 | 53 | 434 |

Binary trough-to-peak cutoff sensitivity:

| Cutoff | KS label | Region | FSU-like | RSU-like |
|---:|---|---|---:|---:|
| 0.37 ms | good | Dorsal | 6 | 107 |
| 0.37 ms | good | Ventral | 3 | 121 |
| 0.37 ms | MUA | Dorsal | 57 | 465 |
| 0.37 ms | MUA | Ventral | 96 | 487 |
| 0.50 ms | good | Dorsal | 10 | 103 |
| 0.50 ms | good | Ventral | 12 | 112 |
| 0.50 ms | MUA | Dorsal | 102 | 420 |
| 0.50 ms | MUA | Ventral | 149 | 434 |

The reviewer-facing FSU/RSU statement must report that waveforms were aligned
before feature extraction, use the locked 0.50-ms binary cutoff, state the
denominator, and state whether the displayed stratum is good or MUA. The
0.37-ms view remains historical sensitivity context, not the publication class
definition.

## Authoritative Recording/Well Mapping

The nine rows below are the nine distinct spike-bearing recording versions for
this analysis. They must remain separate recording observations. Only an
explicitly LFP/low-frequency-only version is excluded.

| Recording family / processing variant | Dorsal wells | Ventral wells | Dorsal good / MUA | Ventral good / MUA |
|---|---|---|---:|---:|
| H1 133-1555 exp17_3(000), filter 200 Hz-3 kHz | B1, B2, B3 | A2, A3 | 10 / 152 | 5 / 56 |
| H1 133-1555 exp17_3(000), primary raw | B1, B2, B3 | A2, A3 | 12 / 129 | 6 / 9 |
| H1 134-0150 exp17_2(001), filter 200 Hz-3 kHz | B3 | A1, A2, A3, B1, B2 | 13 / 29 | 20 / 183 |
| H1 134-0150 exp17_2(001), primary raw | B3 | A1, A2, A3, B1, B2 | 13 / 9 | 33 / 60 |
| PV reporter 134-0150 exp17_2(000), BroadbandProcessor raw | B1, B2, B3 | A1, A2, A3 | 8 / 15 | 8 / 26 |
| PV reporter 134-0150 exp17_2(000), filter 200 Hz-3 kHz | B1, B2, B3 | A1, A2, A3 | 14 / 80 | 8 / 102 |
| PV reporter 134-0150 exp17_2(000), primary raw | B1, B2, B3 | A1, A2, A3 | 8 / 12 | 9 / 20 |
| PV reporter 134-0150 exp17_2 round2(000), filter 200 Hz-3 kHz | B1, B2, B3 | A1, A2, A3 | 20 / 82 | 17 / 102 |
| PV reporter 134-0150 exp17_2 round2(000), primary raw | B1, B2, B3 | A1, A2, A3 | 15 / 14 | 18 / 25 |

Two wells contain MUA but no good unit in a particular processing variant:
H1 133-1555 primary B3 and PV reporter exp17_2(000) BroadbandProcessor A1.

## Recording-Version Inclusion Policy

User-authoritative policy:

- Treat every spike-bearing version as a separate recording.
- Keep `primary_raw`, `filter_200Hz-3kHz`, and
  `broadband_processor_raw` recording versions separate when they have current
  Step 1 spike-sorting/analyzer assets.
- Treat `round2` as a separate recording.
- Exclude only explicitly LFP-like or low-frequency-only versions.
- Do not collapse, deduplicate, average, or select one preferred spike-bearing
  version before the recording/well analysis.

The current 1,342-unit audit table contains no `raw_variant` explicitly labeled
LFP-only. Its three represented variant labels are `primary_raw`,
`filter_200Hz-3kHz`, and `broadband_processor_raw`, and all three have
Kilosort/SpikeInterface unit spike trains. They therefore remain included under
this policy. If a future input is labeled `lfp`, `low_frequency`, or as the
median-downsampled LFP branch, it must be excluded and enumerated in the
denominator flow.

Each analysis observation must carry a stable `recording_well_id` constructed
from the full recording-version identifier plus well. This key identifies one
organoid observation because one well equals one organoid. A
publication-facing organoid label may also be carried for display, but it must
not cause separate recording versions to be collapsed.

## Analysis Levels and Pseudoreplication Control

The output must preserve four levels:

```text
region -> recording version/well (= one organoid) -> sorted unit -> burst
```

Rules:

- Unit distributions may display individual units, but inferential statistics
  cannot treat units from one recording/well as independent observations.
- Burst-level rows are descriptive source rows only. Compute one summary per
  unit before any recording/well aggregation.
- Compute the publication comparison at the recording-version/well organoid
  level, or use a hierarchical model with the recording/well organoid
  explicitly represented.
- Keep `KSLabel=good` and `KSLabel=mua` as separate strata. `KSLabel=mua` means
  a Kilosort multi-unit label; it is not an Axion network-MUA time series.
- Compute both good-unit and MUA strata. Keep them separate in tables and
  figure facets so one cannot change the other's denominator.
- Preserve zero-burst units in denominators for burst rate and fraction of
  spikes in bursts.

## Burst Definition: Required Contract

The older `lmc_spikes_crespoetal2023/scripts/exports_analysis.py` implementation
uses contiguous spikes with adjacent ISI <=100 ms, at least 3 spikes, and burst
duration >=100 ms. It computes burst duration and firing rate within bursts,
but it does not provide the complete requested endpoint set. It was written
for a different experiment and must not be copied without validation.

Proposed explicit detector for the first CytoView implementation:

1. Sort each unit's spike times.
2. Form candidate bursts from contiguous runs in which every adjacent ISI is
   <= `max_isi_ms`.
3. Accept candidates with at least `min_spikes` and duration
   >= `min_duration_ms`.
4. Never assign one spike to more than one accepted burst.

Initial parameter set, retained for comparability with the older code:

```text
max_isi_ms = 100
min_spikes = 3
min_duration_ms = 100
```

This parameter set is provisional until the first raster/ISI sanity-check
gallery is reviewed. The job must also emit a parameter sensitivity table,
for example:

```text
max_isi_ms: 50, 100, 200
min_spikes: 3, 5
min_duration_ms: 0, 100
```

Do not select parameters based on which setting produces a preferred dorsal vs
ventral p-value.

## Exact Metric Definitions

All metrics must exist first at the unit level and then be aggregated to the
recording-version/well level.

| Metric | Unit-level definition | No-burst handling |
|---|---|---|
| Unit firing rate | total unit spikes / recording duration in seconds | 0 only for a zero-spike unit |
| Overall mean firing rate per recording/well | arithmetic mean of unit firing rates within the prespecified KS stratum; also emit median and summed population rate | defined when at least one included unit exists |
| Burst rate | accepted burst count / recording duration in minutes | 0 |
| Mean firing rate within bursts | mean across accepted bursts of `n_spikes / burst_duration_s`; also emit `(n_spikes - 1) / duration_s` as a transparent alternate | NA |
| Burst duration | mean and median of `(last_spike_time - first_spike_time)` across accepted bursts | NA |
| Spikes per burst | mean and median accepted-burst spike count | NA |
| Interburst interval | mean and median of `next_burst_start - previous_burst_end` | NA unless at least 2 bursts |
| Fraction of spikes in bursts | unique spikes assigned to accepted bursts / all unit spikes | 0 when the unit has spikes but no accepted burst |

For recording-version/well summaries, emit both:

- a summary across all included units, retaining zero-burst units where the
  metric is defined as zero; and
- a conditional summary among burst-positive units, clearly labeled.

Never replace an undefined burst duration, within-burst firing rate, spikes per
burst, or IBI with zero.

## Burst-Detectability Pilot (Not Final Results)

An in-memory audit used the older 100-ms/3-spike/100-ms-duration rule only to
confirm endpoint feasibility:

This pilot is superseded for numerical use by the completed Panel E SUA run
documented below. The production detector applies an explicit floating-point
tolerance at exact 100-ms sample boundaries and detected 7,962 rather than the
pilot's 7,958 good-unit bursts.

| KS label | Region | Units | Units with >=1 burst | Units with >=2 bursts | Total detected bursts |
|---|---|---:|---:|---:|---:|
| good | Dorsal | 113 | 83 | 70 | 1,765 |
| good | Ventral | 124 | 108 | 99 | 6,193 |
| MUA | Dorsal | 522 | 249 | 242 | 13,917 |
| MUA | Ventral | 583 | 204 | 197 | 26,627 |

These numbers preserve all nine spike-bearing recording versions as separate
recordings, as required. They are still not final burst results because the
detector parameters are provisional. They establish that all requested burst
endpoints are computationally available and that missing IBI/duration values
must be handled explicitly.

## Required Output Tables

The implementation should write long-form source tables plus well-level tables:

```text
cohort_recording_well_audit.csv
unit_metrics_with_region_kslabel_class.csv
burst_events_long.csv.gz
unit_burst_metrics.csv
recording_well_firing_rate_summary.csv
recording_well_burst_summary.csv
fsu_rsu_cutoff_sensitivity.csv
burst_parameter_sensitivity.csv
analysis_denominator_flow.csv
statistics_results.csv
figure_source_data.csv
analysis_provenance.json
analysis_errors.csv
```

Minimum keys:

```text
recording_well_id
organoid_label
logical_recording_id
recording
well
region_call
region_source
region_override_applied
raw_variant
unit_id
KSLabel
```

Every output must record the recording-version inclusion/exclusion policy,
FSU/RSU cutoff and alignment state, burst parameters, recording duration, and
software/git state.

## First Panel E SUA Run, 2026-07-10

The corrected SUA-only (`KSLabel=good`) Panel E analysis completed on Great
Lakes. It supersedes the earlier rendering-only run `53237567`; the corrected
run makes the no-recording-kind-filter denominator explicit.

```text
job_id: 53237612
state: COMPLETED
elapsed: 00:00:15
node: gl3441
```

Preferred output root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/
step1_nonlfp_th5_v5_ground_truth_latest/
cytoview_dv_sua_spontaneous_activity_20260710_20260710_051912/
```

The corrected output root is:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/
step1_nonlfp_th5_v5_ground_truth_latest/
cytoview_dv_sua_spontaneous_activity_20260710_20260710_052817/
```

Run contract:

```text
KSLabel = good (SUA only)
all nine current spike-bearing recording versions kept separate
explicit LFP/low-frequency-only exclusions = 0
one recording/well = one organoid observation
burst maximum adjacent ISI = 100 ms
minimum spikes per burst = 3
minimum burst duration = 100 ms
aligned FS threshold = TTP <= 0.50 ms
aligned RS threshold = TTP > 0.50 ms
```

Validated denominators:

| Item | Count |
|---|---:|
| SUA units | 237 |
| All non-LFP recording/well organoids retained | 52 |
| Dorsal non-LFP recording/well organoids retained | 23 |
| Ventral non-LFP recording/well organoids retained | 29 |
| Dorsal recording/well organoids with SUA | 22 |
| Ventral recording/well organoids with SUA | 28 |
| Total recording/well organoids with SUA | 50 |
| Accepted SUA bursts | 7,962 |
| Aligned FS units at 0.50 ms | 38 |
| Aligned RS units at 0.50 ms | 199 |
| Spike-count mismatches | 0 |
| Analyzer errors | 0 |

Initial recording/well descriptive results, mean +/- SEM:

| Metric | Dorsal | Ventral | Contributing N dorsal / ventral |
|---|---:|---:|---:|
| Overall mean SUA firing rate, Hz | 0.6304 +/- 0.0945 | 1.5670 +/- 0.1360 | 22 / 28 |
| Mean SUA burst rate, bursts/min | 1.4169 +/- 0.2551 | 4.9671 +/- 0.5849 | 22 / 28 |
| Mean firing rate within bursts, Hz | 28.7312 +/- 1.2740 | 25.9897 +/- 0.5573 | 20 / 28 |
| Mean burst duration, ms | 158.9977 +/- 6.1478 | 187.4965 +/- 6.7029 | 20 / 28 |
| Mean interburst interval, s | 60.0947 +/- 4.2240 | 30.3935 +/- 5.8981 | 20 / 28 |
| Mean spikes per burst | 4.4040 +/- 0.2465 | 4.8525 +/- 0.2613 | 20 / 28 |

Each plotted point is one recording-version/well organoid. All 52 non-LFP
recording/well organoids remain in the denominator audit; the two wells without
any `KSLabel=good` unit have `NA` SUA metrics and are not plotted as zero firing.
E1 and E2 therefore show 50 SUA-containing organoids. Two dorsal organoids
have no accepted SUA burst under the starting detector, so conditional burst
properties E3-E6 have dorsal N=20. Undefined conditional metrics remain NA,
not zero. No inferential p-values are included in this first plot.

### Mean/Median/Maximum Summary Variant

A targeted summary version was generated from the corrected recording/well
table without reopening analyzers or changing the SUA/LFP inclusion policy:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/
step1_nonlfp_th5_v5_ground_truth_latest/
cytoview_dv_sua_activity_mean_median_max_20260710/
```

It contains the same six panels, with separate mean, median, and maximum
markers for each dorsal/ventral metric, plus PDF/SVG exports, a long-form
summary CSV, and provenance JSON. The two recording/well organoids without
SUA remain `NA` and do not contribute to these regional statistics.

Primary figure files:

```text
cytoview_dv_sua_spontaneous_activity_20260710.png
cytoview_dv_sua_spontaneous_activity_20260710.pdf
cytoview_dv_sua_spontaneous_activity_20260710.svg
```

Source/provenance files:

```text
cytoview_dv_sua_spontaneous_activity_20260710_unit_metrics.csv
cytoview_dv_sua_spontaneous_activity_20260710_burst_events_long.csv.gz
cytoview_dv_sua_spontaneous_activity_20260710_recording_well_summary.csv
cytoview_dv_sua_spontaneous_activity_20260710_region_summary.csv
cytoview_dv_sua_spontaneous_activity_20260710_figure_source_data.csv
cytoview_dv_sua_spontaneous_activity_20260710_denominator_flow.csv
cytoview_dv_sua_spontaneous_activity_20260710_provenance.json
submission.json
submitted_jobs.tsv
repro/
logs/
```

Implementation:

```text
src/axion_mea/spontaneous_activity.py
scripts/build_cytoview_dv_sua_spontaneous_activity.py
scripts/prepare_cytoview_dv_sua_spontaneous_activity_job.py
tests/test_spontaneous_activity.py
```

The submitted job passed four pure burst-detection tests, produced zero stderr,
and was independently checked for unit/burst/organoid denominators, live versus
exported spike-count equality, aligned class counts, six-panel source-data
coverage, and opaque-white figure rendering.

## Proposed Main-Figure Architecture

A compact 3 x 3 structure can contain the complete reviewer response:

| Panel | Content |
|---|---|
| A | Cohort/denominator flow plus aligned waveform-feature schematic/space and per-recording/well FS/RS composition at 0.50 ms |
| B | Unit firing-rate distributions, with recording/well-aware visual grouping |
| C | Overall mean firing rate per recording/well |
| D | Burst rate |
| E | Mean firing rate within bursts |
| F | Burst duration |
| G | Spikes per burst |
| H | Interburst interval |
| I | Fraction of spikes occurring in bursts |

Publication-display rules:

- Dorsal and ventral colors must remain consistent across all panels.
- Show recording/well observations, not only bars.
- Show central tendency and uncertainty without hiding the raw recording/well
  values.
- Put unit-level or burst-level distributions in the background only when the
  recording/well hierarchy is visually explicit.
- Label N as organoids/recording-wells first, then units in the caption; state
  explicitly that one well equals one organoid.
- Do not use MUA and good units in the same distribution without a clear facet
  or legend.
- Render both good and MUA versions; decide after the first draft whether MUA
  is a second main-figure row or a matched supplementary panel.
- Export PNG for review and PDF/SVG for publication editing.

## Statistical Plan to Implement Before Final Claims

The first output should be descriptive. Inferential tests should only be added
after the recording-version/well denominator table is frozen.

Preferred analysis structure:

- primary contrast: dorsal vs ventral;
- primary unit of inference: recording-version/well, with one well equal to
  one organoid;
- primary, filter, BroadbandProcessor, and round2 spike-bearing versions remain
  separate recording observations;
- explicitly LFP/low-frequency-only versions are excluded;
- effect size and confidence interval reported with every comparison;
- multiple-comparison correction across the prespecified endpoint family;
- no p-value calculated from burst-level rows as independent observations;
- report good-unit and MUA results separately.

If the number of recording/well observations is too small for a stable
hierarchical model, use transparent recording/well-level descriptive estimates
and an explicitly labeled exploratory test rather than inflating N with units
or bursts.

## Great Lakes Implementation and Submission Pattern

Repository:

```text
/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
```

Project environment:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/envs/axion-kilosort
```

Interactive activation:

```bash
cd /home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
source /home/elcrespo/miniconda3/etc/profile.d/conda.sh
conda activate /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/envs/axion-kilosort
```

Planned implementation files:

```text
scripts/build_cytoview_dv_reviewer_burst_metrics.py
scripts/plot_cytoview_dv_reviewer_final_figure.py
scripts/prepare_cytoview_dv_reviewer_final_job.py
slurm/run_cytoview_dv_reviewer_final.sbatch
tests/test_cytoview_dv_burst_metrics.py
```

Planned Turbo output root:

```text
${PROJECT_ROOT}/jobs/step1_nonlfp_th5_v5_ground_truth_latest/
  cytoview_dv_reviewer_final_<date>_<timestamp>/
```

Each run must contain:

```text
repro/
  project_config.env
  python_command.sh
  submit_command.sh
  submitted_job.sbatch
logs/
submission.json
submitted_jobs.tsv
```

Slurm-side activation must follow the corrected recent pattern:

```bash
#!/usr/bin/env bash
#SBATCH --job-name=cytoview_dv_bursts
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=01:00:00

set -eo pipefail

REPO_ROOT=/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike
source "${REPO_ROOT}/config/greatlakes_project.env"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
cd "${REPO_ROOT}"
```

Do not use uninterrupted `set -u` during conda activation. Previous jobs
failed because conda hooks referenced unset `MKL_INTERFACE_LAYER` or
`xml_catalog_files_libxml2` variables. Either use `set -eo pipefail`, as above,
or temporarily `set +u` around activation and restore it afterward.

Submission/monitoring contract:

```bash
# Prepare only first; inspect commands, inputs, output root, and sbatch.
python scripts/prepare_cytoview_dv_reviewer_final_job.py

# Submit only after the prepared package is inspected.
python scripts/prepare_cytoview_dv_reviewer_final_job.py --submit

squeue -j <job_id>
sacct -j <job_id> --format=JobID,JobName,State,Elapsed,ExitCode,NodeList
```

The prep script should call `sbatch --parsable`, save the returned job ID in
`submission.json`/`submitted_jobs.tsv`, and never overwrite a previous run.

## Validation Gates

Do not promote a figure to final until all gates pass:

1. 1,342/1,342 units match live sorting or exclusions are enumerated.
2. Dorsal/ventral calls reproduce 635 dorsal and 707 ventral total unit rows.
3. Both B1/B2 override rules are loaded and applied.
4. Good/MUA counts reproduce 237/1,105 after retaining all nine current
   spike-bearing recording versions.
5. The recording-version inclusion table confirms that only explicit
   LFP/low-frequency versions were excluded; no accepted spike-bearing version
   was collapsed.
6. Every burst spike belongs to at most one burst.
7. Burst rate/fraction retain zero-burst units.
8. Conditional burst metrics retain NA rather than converting undefined values
   to zero.
9. IBI is emitted only for units with at least two bursts.
10. A hand-checked raster gallery confirms detector behavior for high-, medium-,
    low-, and zero-burst units in both regions and KS strata.
11. The locked aligned 0.50-ms class labels are reproduced for every eligible
    good and MUA unit; historical cutoff/alignment sensitivity remains labeled
    as secondary context.
12. Figure source data reproduce every plotted number.
13. PNG, PDF, SVG, provenance, logs, and the full `repro/` bundle exist.

## Decisions Required Before the First Final Plot

1. Approve the provisional burst detector and sensitivity grid after viewing
   raster examples.
2. Decide whether MUA is a second main-figure row or a matched supplementary
   output; it will be computed either way.
3. Provide/approve publication-facing organoid labels, using the authoritative
   one-well-equals-one-organoid mapping, without collapsing their separate
   recording versions.

## Cross-References

```text
docs/GREATLAKES_KILOSORT_HANDOFF.md
  Current Single Source: Waveform Alignment, Cutoffs, And Denominators
  Step 1 Ground Truth Snapshot
  Cytoview B1/B2 Firing-Rate Audit

docs/HANDOFF_REPRESENTATIVE_UNITS_POST_STEP1_PLOTS.md
  reproducible Slurm/repro packaging
  conda activation failures and corrected wrappers

docs/HANDOFF_STIM_LOCKED_GUI_RASTER_PSTH_WINDOW.md
  analyzer-backed spike extraction conventions

docs/DOWNSTREAM_ANALYSIS_DATA_INVENTORY.md
  persisted spike-time assets and network-analysis reuse policy
```

## Added Firing-Rate Method Comparison (2026-07-10)

The original overall firing-rate measurement is retained unchanged:

```text
per-unit legacy firing rate = total unit spikes / full recording duration_s
per-organoid value = mean across KSLabel=good units
```

A second, separately named rate family was added after confirming the intended
published method:

1. retain a `KSLabel=good` unit only when it has at least 30 detected spikes;
2. calculate each positive adjacent ISI and its reciprocal in Hz;
3. hold that reciprocal rate across its corresponding interspike interval on a
   1-ms evaluation grid, with zero rate before the first and after the last
   spike;
4. Gaussian smooth the complete trace using sigma = 50 ms and truncate = 4
   sigma; and
5. store the temporal mean, median, and maximum of the smoothed trace as three
   separate unit metrics.

For the organoid plots, each smoothed-rate temporal summary is averaged across
eligible SUA units in the recording/well. The old count/duration Panel E remains
available. Three additional otherwise-identical Panel E figures replace only
E1 with the smoothed inverse-ISI temporal mean, median, or maximum; E2-E6 are
unchanged. A four-panel comparison figure shows the old E1 measurement beside
the three new E1 measurements.

Final successful run:

```text
job_id: 53237736
state: COMPLETED
elapsed: 00:01:21
exit_code: 0:0
stderr: 0 bytes
output:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/
step1_nonlfp_th5_v5_ground_truth_latest/
cytoview_dv_sua_spontaneous_activity_20260710_20260710_055705/
```

Validation results:

```text
237 total SUA units
233 units eligible for the >=30-spike smoothed-rate analysis
4 units retained in the legacy/burst tables but ineligible for smoothed rate
22 dorsal and 28 ventral recording/well organoids have smoothed-rate values
all legacy unit and burst metrics exactly match the corrected 052817 run
E2-E6 are numerically identical across all three new Panel E versions
six automated spontaneous-activity tests pass
```

### Audit of dorsal temporal-maximum points above 40 Hz

The four plotted dorsal recording/well points above 40 Hz are only three
unique wells because B1 appears as both `primary_raw` and
`filter_200Hz-3kHz`, consistent with the locked policy of retaining
spike-bearing processing versions separately. The four values are:

```text
B1 filter_200Hz-3kHz: 77.4 Hz (1 eligible SUA unit)
B1 primary_raw:       73.7 Hz (5 eligible SUA units)
B3 filter_200Hz-3kHz: 42.9 Hz (4 eligible SUA units)
B2 primary_raw:       41.3 Hz (6 eligible SUA units; one additional unit <30 spikes)
```

Targeted audit output:

```text
cytoview_dv_sua_spontaneous_activity_20260710_20260710_055705/
dorsal_high_max_diagnostics_20260710/
```

The audit traces each point to its contributing units and includes peak-aligned
spikes, aligned waveform shapes, contamination, ISIs below 2 ms, template
peak-to-peak amplitude, robust best-channel noise MAD, and the explicitly
labeled `template PTP / noise MAD` proxy. This proxy is not silently treated as
a precomputed formal SNR.

Fifteen of 17 audited units triggered at least one screening concern using the
exploratory thresholds PTP/noise <4, ContamPct >10%, or >1% of ISIs below 2 ms.
This does not by itself authorize exclusion. B1 and B2 primary-raw units are
especially concerning because most template PTP/noise ratios are below 4.
B1-filter and the leading B3-filter unit have stronger templates, although both
have refractory/contamination concerns. B1-filter unit 9 and B1-primary unit 12
peak at the same underlying event near 402.07 s, showing that the two plotted B1
points are not independent biological organoids.

Sensitivity analysis (organoid means across eligible units):

```text
recording/well       absolute max   max after <2-ms cleanup   p99.9   p99
B1 filter                 77.4                 77.4             33.9   11.6
B1 primary                73.7                 68.7             45.3   21.7
B3 filter                 42.9                 38.8             25.0    9.7
B2 primary                41.3                 40.1             25.0    3.1
```

Thus the large maximum is not explained solely by individual <2-ms violations,
but it is highly sensitive to using an absolute maximum: the 99th-percentile
values are far lower. Treat the maximum as an exploratory peak statistic until
the unit-level QC decision and the independence/replicate model are locked.

### Full SUA rerun with a 10-uV template-amplitude gate

After reviewing the weak-template dorsal units, the complete SUA analysis was
rerun with an absolute template-amplitude filter, not an SNR filter:

```text
retain when live average-template peak-to-peak amplitude on the best channel
is >= 10 uV
exclude when template PTP is < 10 uV or undefined
```

All other rules are unchanged: `KSLabel=good`, aligned FS/RS cutoff 0.50 ms,
all non-LFP spike-bearing processing versions retained separately, one well is
one organoid, inverse-ISI Gaussian sigma 50 ms with >=30 spikes, and burst
detection at adjacent ISI <=100 ms, >=3 spikes, duration >=100 ms.

Successful Great Lakes run:

```text
job_id: 53238377
state: COMPLETED
elapsed: 00:01:00
exit_code: 0:0
stderr: 0 bytes
output:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/
step1_nonlfp_th5_v5_ground_truth_latest/
cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_20260710_061756/
```

Denominators and validation:

```text
237 KSLabel=good units before template filter
59 units excluded below 10 uV
178 units retained: 76 dorsal, 102 ventral
aligned classes retained: 21 FS, 157 RS
176 retained units also pass the >=30-spike smoothed-rate requirement
52 total non-LFP recording/well observations preserved
42 observations contain >=1 qualifying SUA unit: 17 dorsal, 25 ventral
10 observations contain no qualifying SUA and remain in the universe with NA metrics
7,109 accepted bursts
minimum retained template PTP: 10.3705 uV
six automated spontaneous-activity tests pass
```

The 10-uV filter removes the weak B2-primary high-maximum point. Three dorsal
recording/well points remain above 40 Hz because their contributing templates
pass the hard amplitude gate: B1-filter (77.4 Hz), B1-primary (77.1 Hz), and
B3-filter (59.3 Hz). The cutoff therefore filters on waveform amplitude rather
than being tuned to remove every high firing-rate observation.

### Full SUA rerun with all three unit-quality gates

The complete analysis was subsequently rerun using the inclusive AND rule:

```text
template PTP >= 10 uV
ContamPct <= 10%
fraction of adjacent ISIs <2 ms <= 0.01 (1%)
```

Successful Great Lakes run:

```text
job_id: 53239364
state: COMPLETED
elapsed: 00:00:58
exit_code: 0:0
stderr: 0 bytes
output:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/
step1_nonlfp_th5_v5_ground_truth_latest/
cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_
contam_le10pct_isi2ms_le1pct_20260710_064443/
```

Sequential denominator flow:

```text
237 KSLabel=good units before added QC
59 excluded for template PTP <10 uV -> 178
27 additional units excluded for ContamPct >10% -> 151
4 additional units excluded for short-ISI fraction >1% -> 147
147 retained units: 70 dorsal, 77 ventral
aligned classes retained: 18 FS, 129 RS
145 retained units also pass the >=30-spike smoothed-rate requirement
52 total recording/well observations preserved
39 observations contain >=1 qualifying SUA unit: 16 dorsal, 23 ventral
13 observations contain no qualifying SUA and remain with NA metrics
3,848 accepted bursts
```

All 147 output unit rows were programmatically verified to satisfy all three
inclusive gates. After applying the three filters, only B1-primary remains above
40 Hz in the dorsal temporal-maximum panel (unit 38; organoid value 77.1 Hz).
That unit passes all locked QC gates and is therefore retained rather than
removed based on its biological outcome.
