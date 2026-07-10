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

### Outcome-guided QC search requested for mechanism discovery

The three-gate run above was subsequently rejected as a final approach. A new
exploratory objective was explicitly requested: search QC thresholds that lower
the dorsal smoothed inverse-ISI temporal-maximum mean while leaving the ventral
mean unchanged or minimally changed, then identify the units responsible. This
is intentionally outcome-guided mechanism discovery and must not be confused
with a prespecified confirmatory QC analysis.

The fixed starting population is the successful template-PTP >=10-uV run
(`...template_ptp_ge10uV_20260710_061756`). Baseline temporal-maximum means are
33.5529 Hz dorsal (17 recording/well observations, 74 eligible units) and
34.1974 Hz ventral (25 observations, 102 eligible units).

Audit output:

```text
...template_ptp_ge10uV_20260710_061756/
rs_max_driver_audit_iteration1_20260710/
```

Two outcome-selective candidate boundaries were found:

```text
short-ISI fraction <=3.0%:
  dorsal 33.5529 -> 30.7387 Hz (-8.39%)
  ventral unchanged at 34.1974 Hz
  removes 2 dorsal units, 0 ventral units
  dorsal recording/well n changes 17 -> 16; ventral remains 25

ContamPct <=19.4%:
  dorsal 33.5529 -> 30.8116 Hz (-8.17%)
  ventral unchanged at 34.1974 Hz
  removes 1 dorsal unit, 0 ventral units
  dorsal recording/well n changes 17 -> 16; ventral remains 25
```

Both results are driven primarily by B1-filter unit 9, an RS unit with temporal
maximum 77.4131 Hz, template PTP 28.2079 uV, ContamPct 19.5%, and 8/254 adjacent
ISIs below 2 ms (3.1496%). It is the only eligible SUA unit in that
recording/well, so excluding it removes the entire plotted 77.4-Hz observation.
The 3% short-ISI boundary additionally removes B3-filter unit 19, an RS unit
with temporal maximum 33.9705 Hz, PTP 24.5953 uV, ContamPct 0%, and 8/250 short
ISIs (3.2%); its incremental effect is small.

The threshold response is step-like: an ISI cutoff <=3.14% excludes B1-u9,
whereas 3.15% retains it and restores dorsal n=17. A ContamPct cutoff <=19.49%
excludes B1-u9, whereas 19.5% retains it. Thus the selective outcome is not a
broad distributional effect; it is mainly leverage from one single-unit
recording/well observation.

### Selected outcome-guided rerun: template PTP >=10 uV and short-ISI <=3%

The round 3% short-ISI candidate was selected for a complete rerun without a
ContamPct filter.

```text
job_id: 53239731
state: COMPLETED
elapsed: 00:01:03
exit_code: 0:0
stderr: 0 bytes
output:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/
step1_nonlfp_th5_v5_ground_truth_latest/
cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_
isi2ms_le3pct_20260710_071132/
```

Validated result:

```text
237 KSLabel=good units before added QC
59 excluded for template PTP <10 uV -> 178
0 excluded by ContamPct (no contamination filter)
2 dorsal RS units excluded for short-ISI fraction >3% -> 176
retained units: 74 dorsal, 102 ventral; 155 RS, 21 FS
smoothed-rate eligible units: 72 dorsal, 102 ventral
recording/well observations with qualifying SUA: 16 dorsal, 25 ventral
dorsal temporal-maximum mean: 33.5529 -> 30.7387 Hz (-8.39%)
ventral temporal-maximum mean: unchanged at 34.1974 Hz
accepted bursts: 7,101
```

The two excluded units are B1-filter u9 and B3-filter u19, described above.
B1-primary u38 remains as a 77.1-Hz dorsal observation because its short-ISI
fraction is 0.8688%, below the selected 3% cutoff.

The same selected analysis was rerun solely to make the E3 label explicit as
`Mean firing rate per burst (MFR/Burst)` / `MFR/Burst (Hz)`. The underlying E3
calculation remains spike count divided by burst duration for each accepted
burst, averaged across bursts per unit and across qualifying units per
recording/well. All unit and burst values were verified identical to job
53239731.

```text
job_id: 53240208
state: COMPLETED
elapsed: 00:00:57
stderr: 0 bytes
output:
.../cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_
isi2ms_le3pct_20260710_071723/
```

An E7 panel was then added for the separately defined metric requested by the
user: `Maximum spikes in a burst`. For each recording/well, this is the single
largest `spike_count` among all accepted bursts from all retained SUA units. It
is not MFR/Burst and it is not the mean spikes-per-burst metric in E6.

```text
job_id: 53240378
state: COMPLETED
elapsed: 00:01:00
stderr: 0 bytes
output:
.../cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_
isi2ms_le3pct_20260710_072146/
```

E7 was validated directly against the long burst-event table for all 41
contributing recording/well observations. Region summaries are dorsal n=16,
mean=11.1875, median=10.5, maximum=30 spikes; ventral n=25, mean=24.12,
median=16, maximum=70 spikes. All previously plotted unit and burst metrics are
numerically identical to job 53240208.

Two robust instantaneous-rate summaries were then added without changing any
unit, burst, or QC rule: the temporal 99th and 99.9th percentiles of each unit's
50-ms Gaussian-smoothed inverse-ISI trace. Per-unit percentiles are averaged
across qualifying units within each recording/well, consistent with the other
E1 versions.

```text
job_id: 53240569
state: COMPLETED
elapsed: 00:01:22
stderr: 0 bytes
output:
.../cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_
isi2ms_le3pct_20260710_073045/
```

Region-level E1 means:

```text
summary       dorsal (n=16)   ventral (n=25)
maximum          30.7387         34.1974 Hz
99.9th pct       20.5516         24.8161 Hz
99th pct         11.1434         15.4684 Hz
```

Relative to the absolute maximum, P99.9 reduces dorsal by 33.14% and ventral by
27.43%; P99 reduces dorsal by 63.75% and ventral by 54.77%. These summaries do
not discard spikes or bursts; they change only the time-series summary used for
E1. All prior metrics, including E7, were verified identical to job 53240378.

An explicit ventral-dorsal separation ranking was generated in the same run
folder. Across all processing versions, the legacy spike-count/duration rate
has the largest standardized and proportional separation (dorsal 0.9361 Hz,
ventral 1.8412 Hz, +96.69%, Hedges g=1.191, Welch p=0.000163). The smoothed IFR
temporal mean is nearly identical (+93.22%, g=1.172, p=0.000192). Among the
high-rate summaries, P99 has the largest absolute difference (4.3250 Hz) but a
smaller standardized effect (g=0.597, p=0.0538).

By recording-processing variant, the 200-Hz-to-3-kHz version provides the
strongest comparison with more than two observations per group: for the legacy
rate, dorsal n=7 mean=0.9127 Hz and ventral n=10 mean=2.0569 Hz (+125.37%,
g=1.308, p=0.00781). Broadband processor has a larger apparent g but only n=2
per region and is not a stable basis for selection. Primary raw legacy gives
g=0.880 with n=7 dorsal and n=13 ventral.

A new integrated seven-panel composite was added at the user's request. E1
spans the full top row and displays legacy, IFR temporal mean, median, P99,
P99.9, and maximum together on a logarithmic Hz axis. E2-E7 occupy the next two
rows and retain their established definitions.

```text
job_id: 53240822
state: COMPLETED
elapsed: 00:01:27
stderr: 0 bytes
output:
.../cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_
isi2ms_le3pct_20260710_074119/
figure:
cytoview_dv_sua_spontaneous_activity_20260710_panel_e_all_firing_rate_methods.*
```

## Explicit dorsal-driver unit sensitivity run (2026-07-10)

At the user's direction, the two remaining individual dorsal units with a
50-ms Gaussian-smoothed inverse-ISI temporal maximum above 70 Hz were removed
by exact unit key, with no ventral exclusions and no additional recording-kind
filter:

```text
H1 exp17_3(000), filter_200Hz-3kHz, B3, unit 5: 79.3573 Hz
H1 exp17_3(000), primary_raw, B1, unit 38: 77.1146 Hz
```

This is an explicit outcome-guided sensitivity analysis, not a generalizable
QC threshold. Unit 5 was removed while the other B3 unit was retained. Unit 38
was the only qualifying SUA unit in its recording/well observation, so that
observation remains in the full non-LFP universe but has no qualifying SUA and
does not contribute to conditional E1-E7 summaries.

```text
job_id: 53241975
state: COMPLETED
elapsed: 00:01:32
stderr: 0 bytes
output:
.../cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_
isi2ms_le3pct_exclude2_dorsal_drivers_20260710_081502/
figure:
cytoview_dv_sua_spontaneous_activity_20260710_panel_e_all_firing_rate_methods.*
```

Validated result:

```text
retained units: 174 (153 RS, 21 FS)
smoothed-rate eligible units: 172
recording/well observations with qualifying smoothed SUA: 15 dorsal, 25 ventral
accepted bursts: 6,962
dorsal temporal-maximum mean: 30.7387 -> 26.3082 Hz
ventral temporal-maximum mean: unchanged at 34.1974 Hz
largest remaining dorsal recording/well mean temporal maximum: 39.1928 Hz
```

The run writes `*_explicitly_excluded_units.csv`, records both exact keys and
the no-ventral-exclusion statement in `*_provenance.json`, and carries the
exclusion through every firing-rate and burst panel.

## Locked publication Panel E (canonical as of 2026-07-10)

The user locked the final activity-panel content and order as:

```text
E1a  Legacy overall firing rate (spike count / recording duration)
E1b  50-ms Gaussian-smoothed inverse-ISI temporal 99th percentile
E2   Burst rate
E3   Mean firing rate per burst (MFR/Burst)
E4   Burst duration
E5   Inter-burst interval
E6   Mean spikes per burst
E7   Maximum spikes in any SUA burst
```

This locked panel includes the exact two-unit dorsal-driver exclusion from the
preceding sensitivity run. It is a clean 2-by-4 composite, with internal
processing-version names replaced by readable legend labels. The exact panel
order, exclusion status, figure paths, and dedicated source-data path are also
stored under `final_locked_panel` in provenance.

```text
canonical_job_id: 53242259
state: COMPLETED
elapsed: 00:01:29
stderr: 0 bytes
canonical_output:
.../cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_
isi2ms_le3pct_exclude2_dorsal_drivers_20260710_082420/
canonical_figure:
cytoview_dv_sua_spontaneous_activity_20260710_panel_e_FINAL_
legacy_p99_burst_metrics.{png,pdf,svg}
canonical_source_data:
cytoview_dv_sua_spontaneous_activity_20260710_panel_e_FINAL_
legacy_p99_burst_metrics_source_data.csv
```

The 174-unit table, 52-row recording/well universe, two-row exclusion audit,
and region summary are exactly identical to the validated job 53241975. Do not
replace P99 with P99.9, maximum, mean, or median in this locked panel unless the
user explicitly revises the specification.

## Unified RS/FS classification plus activity figure (2026-07-10)

The user subsequently requested a single publication-style figure that makes
the activity summary panel D and places RS/FS classification panels A-C above
it. The canonical first unified build is:

```text
job_id: 53242707
state: COMPLETED
elapsed: 00:00:16
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_083726/
figure:
cytoview_unified_rsfs_activity_figure_20260710.{png,pdf,svg}
```

Layout and data lock:

```text
A  waveform-feature schematic + aligned multidimensional feature space
B  aligned RS/FS mean +/- SEM waveforms (top) + normalized individuals/means (bottom)
C  aligned trough-to-peak distribution + TTP measurement inset
D  seven metrics in one row/one metric per column:
   legacy firing rate, burst rate, MFR/Burst, burst duration,
   inter-burst interval, mean spikes/burst, maximum burst size
```

Panel D uses legacy firing rate only; it intentionally does not include the
smoothed inverse-ISI P99 view from the preceding locked activity-only figure.
The dorsal/ventral centers are reduced from 1.0 to 0.30 plotting units while
retaining jitter and mean +/- SEM.

Panels A-C use the exact post-QC/post-exclusion SUA population from the
canonical activity run, not the older 237-unit pre-QC waveform-composite pool:
174 aligned units total, 21 FS and 153 RS, with FS defined as aligned TTP <=
0.50 ms. All 174 units have aligned waveform traces and complete TTP,
asymmetry, and post-trough rebound/repolarization-slope features. This keeps
A-C and D population-coherent. The explicit two dorsal driver exclusions are
carried into the unified figure; zero ventral units are explicitly excluded.

Dedicated source outputs:

```text
*_panel_A_C_aligned_features.csv
*_panel_B_aligned_waveform_traces.csv.gz
*_panel_B_waveform_mean_sem.csv
*_panel_D_activity_source_data.csv
*_provenance.json
```

### Beautified unified figure and feature-separation audit

The user requested removal of the waveform-feature schematic from A, a much
smaller B showing only class-mean normalized waveforms, and a more separative
but scientifically interpretable feature combination. The revised canonical
unified build is:

```text
job_id: 53243805
state: COMPLETED
elapsed: 00:00:33
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_085229/
```

Panel A now plots aligned TTP versus aligned repolarization time, with point
size encoding aligned spike half-width. A repeated 5x5-fold, class-balanced
logistic feature audit found:

```text
repolarization time alone: CV ROC AUC 0.957865
spike half-width alone:    CV ROC AUC 0.832594
the selected non-TTP pair: CV ROC AUC 0.959320
```

This audit is exploratory because class labels remain defined by aligned TTP
<= 0.50 ms, not by a trained multifeature classifier. The apparent best pair,
post-peak amplitude plus post-trough rebound slope (CV AUC 0.999677), was
explicitly rejected as circular: rebound slope is post-peak amplitude divided
by TTP, so the two values algebraically reconstruct the class-defining TTP.
The full ranking is saved as `*_panel_A_feature_selection_audit.csv`.

Panel A displays 173 complete-feature units because one retained RS unit lacks
a defined repolarization-time value; it is not imputed or removed from the
underlying population. Panels B, C, and D retain the 174-unit source
population. Panel B now contains only the FS and RS class-mean normalized
waveforms, with no individual traces, raw-uV view, or SEM shading. Job
53243805 supersedes job 53242707 for unified-figure appearance.

### Three-feature space plus six representative-unit QC cards

The next user-directed unified iteration supersedes job 53243805:

```text
job_id: 53245116
state: COMPLETED
elapsed: 00:00:46
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_091754/
```

Panel A is now a true three-axis aligned waveform space:

```text
x = aligned trough-to-peak duration
y = aligned repolarization time
z = aligned spike half-width
color = locked FS/RS class (aligned TTP <= 0.50 ms defines FS)
point size = unit temporal P99.9 of the 50-ms Gaussian-smoothed inverse-ISI rate
```

The small waveform next to A is display-only: the pooled normalized waveform
is Savitzky-Golay smoothed and only the trough and post-trough peak are marked.
No metric is recomputed from this smoothed display waveform.

Panels B and C now replace the former mean-waveform/TTP-histogram panels with
three `KSLabel=good` FS representatives and three `KSLabel=good` RS
representatives. Each compact card contains a local multichannel waveform
footprint, probability-normalized autocorrelogram with +/-2-ms reference
lines, and sampled-spike amplitude stability over recording time. Selection
combines within-class TTP/repolarization-time/half-width centrality with spike
count, template PTP, firing rate, short-ISI fraction, and ContamPct quality,
while requiring dorsal and ventral representation and preferring distinct
analyzers.

Selected units:

```text
FS1 ventral B1 u24, TTP 0.48 ms, P99.9 30.3154 Hz
FS2 dorsal  B3 u16, TTP 0.40 ms, P99.9 16.9691 Hz
FS3 ventral B1 u14, TTP 0.48 ms, P99.9  9.5126 Hz
RS1 ventral B2 u9,  TTP 0.88 ms, P99.9 25.6821 Hz
RS2 ventral B1 u17, TTP 0.80 ms, P99.9 26.1373 Hz
RS3 dorsal  B3 u29, TTP 0.64 ms, P99.9 14.7824 Hz
```

New dedicated source outputs include:

```text
*_panel_A_aligned_features.csv
*_panels_B_C_representative_ranking.csv
*_panels_B_C_representative_selection.csv
*_panels_B_C_spatial_waveforms.csv.gz
*_panels_B_C_autocorrelograms.csv
*_panels_B_C_amplitude_stability.csv.gz
```

Panel D remains the same legacy-firing-rate plus six burst-metric strip and
still carries the two explicit dorsal driver exclusions with zero explicit
ventral exclusions.

### Axis-clipped compact A, raw ACGs, and full FS candidate gallery

The next canonical visual iteration is:

```text
job_id: 53247598
state: COMPLETED
elapsed: 00:01:11
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_093726/
```

Panel A is smaller and less visually dominant. Its explicit display limits are
TTP 0.24-2.00 ms, repolarization time 0.00-0.60 ms, and spike half-width
0.00-0.80 ms. Points outside any displayed axis or lacking a displayed feature
are filtered before scatter rendering, so no marker is drawn beyond the axes.
This is a visual omission only: the source table still contains all 174 units.
The figure reports 164 units shown. Point size remains temporal P99.9 smoothed
inverse-ISI firing rate.

The compact waveform directly above A now overlays the FS and RS class-mean
aligned, trough-normalized waveforms. Savitzky-Golay smoothing is display-only;
trough and post-trough peak landmarks are marked for both classes. No metric or
class is recomputed from the smoothed inset.

Panel B preliminary FS representatives were tightened to clear compact-waveform
candidates (TTP <=0.40 ms and half-width <=0.24 ms):

```text
FS1 dorsal  B3 u16, TTP 0.40 ms
FS2 ventral B1 u16, TTP 0.40 ms
FS3 ventral B1 u22, TTP 0.40 ms
```

Representative-card changes:

- spatial waveform glyphs receive a uniform 1.8x display gain while preserving
  within-unit relative channel amplitudes;
- probability ACGs are plotted from the raw probability bins with absolutely
  no display smoothing;
- the ACG row is taller and the amplitude-stability PTP row underneath is
  substantially shorter.

A separate gallery shows all 19 retained FS units meeting the representative
completeness and >=100-spike rule, sorted by the reproducible QC score. Current
main-figure picks are marked, but the gallery is intended for user visual
override:

```text
cytoview_unified_rsfs_activity_figure_20260710_FS_candidate_gallery.{png,pdf,svg}
cytoview_unified_rsfs_activity_figure_20260710_FS_candidate_gallery_selection.csv
cytoview_unified_rsfs_activity_figure_20260710_FS_candidate_gallery_spatial_waveforms.csv.gz
cytoview_unified_rsfs_activity_figure_20260710_FS_candidate_gallery_autocorrelograms.csv
cytoview_unified_rsfs_activity_figure_20260710_FS_candidate_gallery_amplitude_stability.csv.gz
```

Job 53247598 supersedes job 53245116 for current unified-figure appearance and
FS representative review.

### User-locked FS representatives: gallery FS1, FS16, FS5

The user selected gallery candidates FS1, FS16, and FS5, in that order. The
canonical rerender is:

```text
job_id: 53248300
state: COMPLETED
elapsed: 00:01:13
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_095953/
```

Exact locked FS units:

```text
FS1  ventral B1 u24 | h1 exp17_2(001) filter_200Hz-3kHz | TTP 0.48 ms
FS16 dorsal  B3 u9  | pvreporter round2 filter_200Hz-3kHz | TTP 0.40 ms
FS5  ventral B1 u22 | h1 exp17_2(001) filter_200Hz-3kHz | TTP 0.40 ms
```

The exact unit keys are stored in `LOCKED_FS_UNIT_KEYS`, the representative
selection CSV, and provenance. Main-figure card titles retain the gallery IDs
FS1, FS16, and FS5 so the visual choice remains auditable. RS representatives
and panels A/D are unchanged. Job 53248300 supersedes 53247598.

### Four-unit spatial-footprint-forward aesthetics pass

The main unified figure was reduced to two user-locked representatives per
class:

```text
FS1  ventral B1 u24
FS16 dorsal  B3 u9
RS1  ventral B2 u9
RS3  dorsal  B3 u29
```

The exact FS1/FS16 and RS1/RS3 unit keys are now stored in
`LOCKED_FS_UNIT_KEYS` and `LOCKED_RS_UNIT_KEYS`. The spatial waveform display
gain increased uniformly from 1.8x to 2.6x, each footprint receives a much
larger share of the card, and the raw unsmoothed probability ACG and PTP
stability summaries are compressed into tick-free context strips. The outlined
best-channel center circles were removed from all four spatial footprints.

Canonical aesthetics-only rerender:

```text
job_id: 53251676
state: COMPLETED
elapsed: 00:00:56
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_101457/
```

Panels A and D retain their preceding data and calculations in this render.

### Exhaustive Panel A pairwise and three-feature separation audit

Before another Panel A design change, the locked 174-unit CytoView population
(21 FS, 153 RS) was audited across 18 unit-level features: 12 aligned waveform
metrics and six firing-rate summaries. This yields all 153 unique feature pairs
and all 816 unique three-feature combinations. Burst metrics were not included
because they summarize network activity rather than individual-unit
classification.

Pairwise separation was quantified using:

- Fisher trace ratio after pairwise z-scoring;
- regularized pooled-covariance Mahalanobis centroid distance;
- repeated 5x5-fold stratified CV ROC AUC from standardized class-balanced
  logistic regression;
- Euclidean silhouette score of the locked classes after z-scoring.

The overall pair rank is the mean of the four descending metric-specific ranks.
Three-feature models use standardized LDA with repeated 5x5-fold stratified CV
ROC AUC. Per-model feature importance is the absolute standardized full-data
LDA coefficient normalized to sum to one within the triple.

Canonical audit:

```text
job_id: 53251761
state: COMPLETED
elapsed: 00:02:20
stderr: 0 bytes
output:
.../cytoview_rsfs_feature_separability_20260710_20260710_102011/
```

The top overall pair is aligned TTP plus depolarization slope (CV AUC 1.000).
The top LDA triple is aligned TTP, repolarization time, and smoothed inverse-ISI
maximum (CV AUC 0.999667). Every top-10 LDA triple contains TTP, and TTP carries
about 86% of normalized standardized LDA importance across those top models.
This is expected because the current FS/RS label is defined by aligned TTP <=
0.50 ms. TTP-containing results are therefore tautological separation, not
independent validation.

The exact post-peak-amplitude plus rebound-slope pair is separately flagged
because it algebraically reconstructs TTP. The best pair excluding both direct
TTP and that exact algebraic pair is spike amplitude plus rebound slope (CV AUC
0.983320), but rebound slope remains mathematically timing-coupled and should
still be interpreted cautiously. Panel A was not changed automatically from
this audit.

Primary outputs include:

```text
cytoview_rsfs_feature_separability_20260710_complete_pairwise_scatter_matrix.*
cytoview_rsfs_feature_separability_20260710_all_pairwise_rankings.csv
cytoview_rsfs_feature_separability_20260710_top10_feature_pairs.*
cytoview_rsfs_feature_separability_20260710_all_three_feature_LDA_rankings.csv
cytoview_rsfs_feature_separability_20260710_all_three_feature_LDA_importance_long.csv
cytoview_rsfs_feature_separability_20260710_LDA_feature_importance_summary.csv
cytoview_rsfs_feature_separability_20260710_top10_LDA_triples_and_importance.*
cytoview_rsfs_feature_separability_20260710_provenance.json
```

### Lumos aligned good-unit FS gallery

A separate rapid-review gallery was generated from the existing Lumos aligned
waveform audit. The denominator is all 276 paired Lumos `KSLabel=good` units;
85 satisfy aligned TTP <= 0.50 ms and are shown without any additional PTP,
SNR, firing-rate, or other QC exclusion. Units receive stable `LFS1` through
`LFS85` gallery identifiers and are ordered by descending template PTP, then
usable snippets and source identity. The displayed aligned mean best-channel
waveforms are baseline-corrected and trough-normalized with no smoothing.

```text
output:
.../lumos_good_fs_aligned_waveform_gallery_20260710_20260710_1025/
overview:
lumos_good_fs_aligned_waveform_gallery_20260710_all_85_overview.*
pages:
lumos_good_fs_aligned_waveform_gallery_20260710_page_01.* through page_05.*
source:
lumos_good_fs_aligned_waveform_gallery_20260710_selection.csv
lumos_good_fs_aligned_waveform_gallery_20260710_aligned_traces.csv.gz
```

### Panel A replaced by a two-by-two classification block

The 3D Panel A was replaced, without changing the locked population or RS/FS
rule, by:

```text
top left:     x=TTP, y=repolarization time
top right:    raw unsmoothed TTP histogram
bottom left:  x=TTP, y=spike half-width
bottom right: pooled dorsal/ventral RS/FS unit percentages and counts
```

Both scatterplots retain RS/FS color, temporal P99.9 smoothed inverse-ISI
firing-rate point sizes, the aligned 0.50-ms FS cutoff, and the preceding visual
axis-exclusion policy. The histogram uses the aligned 0.08-ms sampling grid and
no density smoothing. The regional summary is explicitly descriptive at the
pooled-unit level, not an organoid-level inferential analysis:

```text
dorsal:  10 FS + 62 RS = 72 units  | 13.89% FS
ventral: 11 FS + 91 RS = 102 units | 10.78% FS
```

Canonical clean render:

```text
job_id: 53252427
state: COMPLETED
elapsed: 00:01:00
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_103600/
```

The exact regional source table is
`cytoview_unified_rsfs_activity_figure_20260710_panel_A_region_classification_summary.csv`.
Panels B-D and their source calculations are unchanged.

### Cross-platform FS replacement: Lumos F8 u5 replaces CytoView FS16

The strongest eligible FS representative was evaluated across CytoView and
Lumos rather than restricting Panel B to CytoView. The matched-QC comparison
used the same aligned TTP <= 0.50-ms rule, `KSLabel=good`, spatial display gain,
raw unsmoothed probability ACG, and sampled PTP stability presentation.

Cross-platform comparison:

```text
job_id: 53254365
state: COMPLETED
elapsed: 00:00:15
stderr: 0 bytes
output:
.../cross_platform_fs_representative_comparison_20260710_20260710_104920/
```

Key QC values:

```text
             FS1 CytoView   FS16 CytoView   LFS1 Lumos F8 u5
TTP ms           0.48           0.40             0.40
template PTP uV 35.44          13.15            91.94
spike count      2258            279             2173
firing rate Hz   4.98           0.45             2.41
ContamPct        0.0            0.0              0.0
P(|lag|<=2 ms)   0.0075         0.0000           0.0000
PTP MAD/median   0.1681         0.0769           0.0473
```

Lumos F8 u5 has the strongest template PTP, clean refractory period, stable
sampled spike amplitude, and a localized spatial footprint. It therefore
replaces the weaker CytoView FS16; CytoView FS1 is retained. The primary F8 u6
processing counterpart appears to be the same biological unit and was not
treated as an independent representative.

Canonical unified render after replacement:

```text
job_id: 53254604
state: COMPLETED
elapsed: 00:00:57
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_105122/
Panel B: FS1 CytoView B1 u24 + LFS1 Lumos F8 u5
Panel C: RS1 CytoView B2 u9 + RS3 CytoView B3 u29
```

Only the Panel B representative changed. Panel A classification and Panel D
activity remain the locked CytoView dorsal/ventral population; the Lumos unit
is not included in those biological summaries.

### Official FS lock and restored 3D Panel A with companion summaries

The official FS representatives moving forward are now:

```text
FS1  CytoView ventral B1 u24
LFS1 Lumos F8 u5
```

CytoView FS16 is no longer selected for the unified figure. The exact current
keys remain in `LOCKED_FS_UNIT_KEYS` and the representative-selection CSV.

Panel A was restored to the large aligned three-feature CytoView waveform space
(x=TTP, y=repolarization time, z=spike half-width). Relative to the earlier 3D
version:

- the gray TTP cutoff plane was removed;
- the view changed from azimuth -56 to -46 degrees, a 10-degree rotation;
- the prose sentence describing point size was removed;
- P99.9 firing-rate size encoding remains documented only by the compact symbol
  key;
- the FS <=0.50-ms and RS >0.50-ms TTP rules are stated in the class legend;
- the dorsal/ventral stacked RS/FS unit summary was added to the right;
- raw aligned trough-normalized FS/RS mean +/- SEM waveforms, without display
  smoothing, were added directly below the stacked summary.

The companion summaries remain CytoView-only and do not include the Lumos
representative. The first render (job 53258406) exposed a 3D/auxiliary-label
spacing collision. The clean canonical rerender widened Panel A and corrected
that collision:

```text
job_id: 53259205
state: COMPLETED
elapsed: 00:01:07
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_111720/
```

### Narrow representative QC and new regional FS-unit activity panel

The upper figure was reorganized to follow the publication narrative:

```text
A: waveform classification
B-C: cross-platform FS and CytoView RS representative-unit QC
D: dorsal versus ventral CytoView FS-unit firing rates
E: organoid-level spontaneous network metrics
```

The representative cards were made substantially narrower. Within each card,
the spatial footprint remains the dominant element, while raw unsmoothed ACG
and PTP stability are retained as short tick-free strips. Repeated labels and
empty space were minimized.

The Panel A waveform summary now uses the aligned waveforms at their original
uV amplitudes rather than trough-normalized amplitudes. It displays only the
overlaid class-mean FS and RS traces: no SEM shading, axes, ticks, grid, frame,
or surrounding box. A compact 0.5-ms / 5-uV scale bar is retained. These traces
are not display-smoothed.

Panel D plots one retained CytoView FS unit per point using the legacy
whole-recording firing rate. No region or well averaging occurs before
plotting. The overlay is the unit-level group mean +/- SEM and established
dorsal/ventral colors are used:

```text
dorsal:  10 FS units, 5 recording/well observations, 0.8299 +/- 0.2387 Hz
ventral: 11 FS units, 7 recording/well observations, 1.6676 +/- 0.3991 Hz
```

The Lumos LFS1 unit is a representative QC example only and is not included in
the dorsal/ventral activity comparison. The former D1-D7 network strip is now
E1-E7 with unchanged calculations and observations.

Canonical render:

```text
job_id: 53259724
state: COMPLETED
elapsed: 00:01:13
exit_code: 0:0
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_113238/
```

New/renamed source tables:

```text
cytoview_unified_rsfs_activity_figure_20260710_panel_D_regional_FS_unit_firing_rates.csv
cytoview_unified_rsfs_activity_figure_20260710_panel_E_activity_source_data.csv
```

### Final Nature-style two-row narrative layout

The unified figure was rebuilt into exactly two visual rows:

```text
top row:    A classification | B FS QC | C RS QC | D FS regional firing | E RS regional firing
bottom row: F1-F6 Regional spontaneous network activity
```

The transient three-row draft from job 53259943 is superseded. The top-row
regional firing panels now sit beside the unit-classification and QC panels.

Palette lock:

```text
waveform class panels A-C:
FS #B45F43 muted terracotta
RS #3E5C76 deep slate blue

regional panels D-F:
dorsal  #657A57 muted forest/sage
ventral #C08A3E warm ochre
```

Panel A retains the 3D aligned TTP/repolarization-time/half-width space as the
dominant element. The class-mean waveforms remain aligned, original-amplitude
uV traces with only a 0.5-ms/5-uV scale bar. The composition inset is now two
small horizontal 100% stacked bars for dorsal and ventral, with count and
percentage in each FS/RS segment. The class/P99.9 key is positioned with Panel
A; the bottom key contains only regional colors, processing-variant markers,
and mean +/- SEM.

Panels B and C contain only their respective FS and RS examples. Visible titles
are generic (`FS1`, `FS2`, `RS1`, `RS2`) plus TTP; platform, region, well, and
unit IDs remain available in source data but are not shown. Spatial footprints
dominate each narrow card, with raw ACG and PTP stability as secondary strips.

Panels D and E use one point per classified CytoView unit and share an exact
0-13 Hz y-axis:

```text
D FS: dorsal 10 units / 5 wells; ventral 11 units / 7 wells
E RS: dorsal 62 units / 15 wells; ventral 91 units / 25 wells
```

The bottom row is titled `Regional spontaneous network activity` and contains
only overall firing rate, burst rate, MFR within bursts, burst duration,
inter-burst interval, and spikes per burst. Maximum burst size was removed.

Canonical clean render:

```text
job_id: 53259978
state: COMPLETED
elapsed: 00:01:04
exit_code: 0:0
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_115637/
```

Current regional source tables:

```text
cytoview_unified_rsfs_activity_figure_20260710_panels_D_E_regional_classified_unit_firing_rates.csv
cytoview_unified_rsfs_activity_figure_20260710_panel_F_regional_spontaneous_network_activity.csv
```

### Corrected two-row hierarchy: B-to-D above C-to-E

The earlier interpretation that placed A-E in a single top-line sequence was
not the intended hierarchy. The upper row is now one composite block: Panel A
spans the full left height, and the area to its right is split into two
horizontal narratives:

```text
upper subrow: B representative FS units -> D regional FS-unit firing
lower subrow: C representative RS units -> E regional RS-unit firing
```

The full-width bottom row remains F1-F6 regional spontaneous network activity.
No data, palette, shared D/E y-axis, representative selection, or lower activity
calculation changed in this layout correction.

Canonical render:

```text
job_id: 53260022
state: COMPLETED
elapsed: 00:01:24
exit_code: 0:0
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_120059/
```

### Layout-only Nature/Neuron hierarchy revision

No data or panel content changed. Relative to job 53260022, Panel A's upper
width allocation decreased by approximately 28%, the representative B/C column
increased by approximately 31%, and D/E increased modestly. The upper hierarchy
remains A spanning both rows, B-to-D above C-to-E.

Panels B and C now use pale 6%-opacity rounded background tints with no outline,
properly aligned internal section headers, generic unit/TTP titles, dominant
spatial footprints, and secondary raw ACG/PTP strips. Unit-title text and traces
use the class accent while QC annotations remain neutral.

The exact palette is now:

```text
FS       #C87932
RS       #4F718C
dorsal   #6F8061
ventral  #C59A52
neutral  #2B2B2B
```

The lower row was enlarged and standardized. Its full-width header has a thin
0.65-pt neutral rule; point size, mean-diamond size, error-bar caps, title
position, and spacing are uniform across F1-F6. No full lower enclosure is used.

Canonical layout-only render:

```text
job_id: 53262237
state: COMPLETED
elapsed: 00:01:05
exit_code: 0:0
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_121758/
```

Byte-level SHA-256 comparison against job 53260022 confirmed that the B/C
representative selection, D/E classified-unit firing source, and F network
activity source CSVs are identical. This is therefore strictly a layout/color
revision.

### Editorial hierarchy revision: two clearly separated scientific stories

This layout-only pass further separates the figure into an upper
`Waveform-defined unit classification and validation` section and a lower
`Regional spontaneous network activity` section. The lower section retains its
full-width heading and thin neutral divider.

The upper width allocation is now approximately 27% classification, 46%
representative-unit QC, and 28% regional classified-unit firing. This reduces
Panel A by 25% relative to job 53262237 and makes the representative FS and RS
evidence the dominant visual element. Within-pair spacing was tightened for the
two FS cards, two RS cards, and dorsal/ventral unit comparisons, while spacing
between the three upper concepts was increased. F1-F6 spacing was compressed
and typography was standardized so the lower row reads as one analysis strip.

Regional colors are now explicitly derived from the class palette:

```text
FS       #C87932
RS       #4F718C
dorsal   #70877F
ventral  #C59A52
neutral  #2B2B2B
```

Canonical render:

```text
job_id: 53262409
state: COMPLETED
runtime: 00:00:58
exit_code: 0:0
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_123303/
```

SHA-256/cmp checks against job 53262237 confirmed byte-identical B/C
representative selection, D/E classified-unit firing source, and F regional
network-activity source CSVs. No unit selection, metric, or biological result
changed.

### Asymmetric editorial redesign: representative units as the visual anchor

The next design pass responds to the publication-layout review while keeping
the data and panel content unchanged. The figure is now a deliberately
asymmetric 16 × 11 inch composition:

- Panel A is a compact 19%-width support column. Its 3D feature space is
  followed by a micro mean-waveform display labelled only FS/RS and a small
  RS/FS composition annotation.
- Panels B/C occupy the remaining 81% of the upper validation section. They
  share one section title, `Representative extracellular units`, with only the
  class subtitles `Fast-spiking (FS)` and `Regular-spiking (RS)`. The beige
  backgrounds and rounded dashboard-style fills were removed; a single thin
  neutral divider separates the class rows.
- Panels D/E are now one paired comparison under the shared title `Regional
  firing properties of classified units`, with FS on the left and RS on the
  right, common y-limits, and a single y-axis label.
- The lower six activity plots use a tighter continuous strip with aligned
  title and y-label baselines. The intentional vertical gap between the upper
  validation section and regional physiology creates the section hierarchy.

The publication palette is now:

```text
FS       #B8742A
RS       #58758E
dorsal   #6F8477
ventral  #C8A05A
neutral  #2B2B2B
```

Canonical render:

```text
job_id: 53262736
state: COMPLETED
runtime: 00:00:58
exit_code: 0:0
stderr: 0 bytes
output:
.../cytoview_unified_rsfs_activity_figure_20260710_20260710_124710/
```

The render was visually inspected. The B/C, D/E, and F source CSVs are
byte-identical to job 53262409, confirming a layout/color-only revision.
