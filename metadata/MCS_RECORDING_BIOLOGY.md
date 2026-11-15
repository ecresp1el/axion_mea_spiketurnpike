# MCS recording biology and inventory guide

Mapping recorded November 14, 2026, from the biological key supplied by the user
as three images in the conversation. The companion file is
[mcs_recording_biology.csv](mcs_recording_biology.csv).

## Experimental groups

Use exactly these three major biological groups, regardless of recording date:

1. **Actuators + effectors**
2. **Actuators + vehicle**
3. **Plain neurons + effectors**

Dates are recording metadata, not grouping variables. `MEA 2023` is an original
collection label, not a fourth biological group. Its recordings require explicit
effector-versus-vehicle assignment before including them in a major-group comparison.
Do not assign that treatment from a date or construct token alone.

## User-supplied biological key

| Major group | Folder/sample token | Biological identity |
| --- | --- | --- |
| Actuators + effectors | 352 | DREADD |
| Actuators + effectors | 353 | LMO |
| Actuators + effectors | 354 | PSAM |
| Actuators + effectors | 371 | Control |
| Actuators + vehicle | D3 | DREADD |
| Actuators + vehicle | 353 | LMO |
| Actuators + vehicle | 354 | PSAM |
| Actuators + vehicle | 371 | Control |
| Plain neurons + effectors | CNO1–3 | Plain neurons, CNO |
| Plain neurons + effectors | CTZ1–3 | Plain neurons, CTZ |
| Plain neurons + effectors | PSEM1–3 | Plain neurons, PSEM |
| Plain neurons + effectors | NB1–3 | Plain neurons, NeuroBasal Medium |

The images identify the collections as Macy, Summer 2021; Ute, Summer 2022;
and Ute, Spring 2022, respectively. These provenance labels do not define the
analysis groups. Preserve the exact original sample labels and suffixes.
Suffixes alone do not establish independent biological replicates or pairing.

`Stim 1`, `Stim 2`, and `Stim 4` remain subdivisions within Actuators + effectors.
The key does not establish that their numbers equal pulse counts, nor does it
specify exact effector compounds, doses, or timing for that arm. The CSV therefore
does not invent those assignments.

For the MEA 2023 collection, construct tokens 353, 354, 371, and D3 use the
corresponding supplied construct identities; treatment and major group remain
unresolved. These assignments should be checked against its acquisition records.

## Inventory coverage

The CSV contains **118 unique recording IDs**, including unavailable sources and
short recordings. This is an acquisition inventory, not a list of successful sorts
or a biological replicate count.

| Major group | Inventory recordings |
| --- | ---: |
| Actuators + effectors | 64 |
| Actuators + vehicle | 22 |
| Plain neurons + effectors | 13 |
| Major group unresolved (original collection: MEA 2023) | 19 |
| Total | 118 |

These counts come from the local readiness inventory. The staged inventory has
114 recordings; it is not the complete source inventory. Neither source inventory is itself a current sorting-completion ledger.
The companion CSV now joins the saved batch ledgers and validation reports.

## CSV columns

| Columns | Meaning |
| --- | --- |
| `recording_id` | Unique join key: original collection / condition path / recording stem. |
| `major_group` | One of the three biological groups; blank when unresolved. |
| `construct` | DREADD, LMO, PSAM, Control, or None (plain neurons). |
| `treatment` | Vehicle, named plain-neuron treatment, or generic effector label; blank when unresolved. |
| `mapping_token` | Folder token used to apply the supplied key. |
| `sample_label` | Original sample folder label, including suffixes and embedded dates. |
| `stim_label` | Literal Stim folder label, where present. |
| `original_collection`, `condition_path`, `recording_stem` | Original inventory identity and hierarchy. |
| `duration_s` | Duration from staged inventory when available, otherwise readiness inventory. |
| `under_60s` | Explicit flag for the previously requested one-minute cutoff; blank if duration is unknown. |
| `source_msrd_path_inventory`, `source_h5_path_inventory` | Original inventory paths; may refer to the original Mac volume and are not verified current cluster paths. |
| `staged_input_dir` | Documented cluster staging path for records found in the staged inventory; existence was not rechecked. |
| `inventory_readiness`, `inventory_blocking_reason` | Historical source-readiness status, not sorting success. |
| `sorting_status`, `sorting_output_path` | Reconciled with saved batch ledgers; completed attempts require a saved validation report without errors. Paths identify the selected attempt. |
| `mapping_source`, `mapping_review` | Mapping provenance and unresolved biological assignments. |

Join saved job results by full recording identity, preserving multiple attempts
separately before selecting a validated result. Do not count retries as additional
recordings. Do not infer successful sorting from source readiness or staging.

## Sources and limitations

- [Source readiness inventory](../audit-output/mcs_sorting_readiness.csv): 118 recordings.
- [Staged inventory](../audit-output/mcs_staged_inventory_20260917.csv): 114 recordings.
- User-supplied biological key in the November 14, 2026 conversation.

The images were transcribed into the mapping; image copies were not added to the
repository. Saved job ledgers and validation reports were read on November 14, 2026:
95 unique recordings have completed attempts with error-free saved validation
reports. This checks saved reports, not a fresh rerun of signal validation.
The quick overview includes 75 recordings: 43 actuator/effector, 19
actuator/vehicle, and 13 plain-neuron/effector. It excludes 19 treatment-unresolved
recordings and one completed recording shorter than 60 seconds.

## Output policy for subsequent analysis

### Added recording length, unit counts, and stimulation timing

The companion CSV now includes the following per-recording fields:

- `duration_s` and `duration_min`: recording length, updated from the selected
  batch attempt when available.
- `total_units`, `sua_units`, `mua_units`, `total_spikes`: saved curated-stage
  validation counts. SUA means automated KSLabel `good`; MUA means KSLabel `mua`.
  Missing counts remain blank, not zero. `unit_count_source` links the report.
- `event_metadata_status`: `markers_present`, `no_markers_in_saved_file`, or
  `metadata_unavailable`. `has_stim_markers` is blank if metadata is unavailable.
  A file without markers does not prove stimulation did not happen.
- `event_count` and `event_labels`: all recorded hardware marker rows and labels.
- `pulse_start_count`, `pulse_stop_count`, `chemical_start_count`, and
  `chemical_stop_count`: counts of markers with those literal label terms.
  Pulse counts describe hardware events, not the Stim folder number.
- `pulse_start_times_s`, `pulse_stop_times_s`, `chemical_start_times_s`, and
  `chemical_stop_times_s`: JSON arrays of seconds from recording start.
- `first_event_s` and `last_event_s`: earliest/latest marker of any kind.
- `events_json`: complete original event rows, including original hardware
  timestamps, IDs, labels, and recording-relative seconds.
- `events_source_path`: exact event file read. Prefer the selected result's
  archived sidecar, then its prepared input, then existing staged/attempt inputs.

Coverage: 118 recordings; 95 have saved validated unit counts. There are 78
recordings with markers, 37 with a saved empty event file, and 3 without an
accessible event file. All loaded event times were checked against available
recording durations. These checks do not establish the physical modality of an
STG pulse or identify the chemical compound/dose from a generic chemical marker.

Example: `Actuators & Effectors/Stim 2/352.1/2021-07-05T12-36-38McsRecording`
has `Chemical START` at **60 seconds**. The pulse example
`Actuators & Effectors/Stim 1/352.1/2021-06-23T11-11-59McsRecording` has five
starts at 299.2607, 299.2709, 299.2811, 299.2913, and 299.3015 seconds.

Reproduce this enrichment with
[enrich_mcs_recording_metadata.py](../scripts/enrich_mcs_recording_metadata.py).
The CSV is approximately 319 KB. No additional plots or raw-data copies were made.

- Keep this small CSV and its guide with the repository.
- Write major analysis outputs to scratch. The user approved `/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/`.
- Generate only analyses, files, and plots explicitly requested by the user.
- Minimize space: avoid copying raw signals, existing sorting outputs, or analyzers
  merely to attach metadata; reference existing artifacts by path.
- Preserve the three biological groups across dates.

The requested quick overview is `mcs_sua_mua_overview.png` in that scratch
directory (about 79 KB). It uses curated-stage saved KSLabel counts: `good`
is putative SUA and `mua` is MUA. Dots represent recordings and black lines
are medians; recordings are not asserted to be independent biological replicates.
Reproduction script: [plot_mcs_unit_overview.py](../scripts/plot_mcs_unit_overview.py).
No raw signals were loaded or copied and no additional plot files were created.

## Actuator/effector metric exploration

The user subsequently requested a broad search for separation of DREADD, LMO,
and PSAM from the 371 control and from one another, restricted to the
**Actuators + effectors** major experiment. Recording-level separation is an
explicitly accepted exploratory outcome; it must be distinguished from
generalization to new sample IDs.

Source: [explore_mcs_actuator_separation.py](../scripts/explore_mcs_actuator_separation.py).
Results are stored under
`/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/actuator_metric_exploration/`.
The analysis README there contains all metric definitions, all 156 metric names,
the explored model families, selected metric combinations, early-time exclusion
sensitivity, and sample-blocked validation. `unit_metrics.csv` joins back to the
recording CSV through `recording_id`, with `unit_id` identifying a unit within
that selected sorting output. Repeated recordings are not silently deduplicated
into biological replicates.

The primary e-stim dataset has 1,554 unit-recording observations in 29 recordings
and 12 sample IDs (three per construct). SUA/MUA are pooled. Only the first STG
train and complete −10 to +10-second windows are used. Chemical-addition events
remain separate. The search permits exploratory label-based feature selection
and supervised LDA, labeled explicitly in its outputs; nested held-out sample
evaluation repeats predictive feature/model selection within training samples.

## User-defined analysis sample: sorted unit

The user clarified on November 14, 2026 that each sorted unit is the sample
for the current exploratory analysis. Pool SUA and MUA unless requested
otherwise. Each observation is identified by the selected sorting output,
recording ID, and unit ID. Units in repeated recordings are not assumed to
be tracked versions of the same neuron.

Use unit-level splits and unit-level separation metrics as the primary results.
Keep original sample-folder and recording IDs as metadata. The earlier
whole-folder holdout is an additional sensitivity analysis, not the user's
primary denominator. Unit-level train/test partitions can contain units from
the same recording and folder. These results describe unit discrimination
within this recorded dataset; treating units as the denominator does not
establish independence between units or generalization to new experiments.

No additional plots were generated for this clarification.

### Redone unit discrimination

The subsequent requested redo uses each unit as the sample throughout:
[redo_mcs_unit_discrimination.py](../scripts/redo_mcs_unit_discrimination.py).
Its primary outputs are `unit_discrimination.png` and `UNIT_DISCRIMINATION.md`
under the existing scratch `actuator_metric_exploration/` directory. It compares
the four classes, each actuator versus Control, and each actuator versus all
others. Validation splits individual units, not original folder IDs. Three outer
unit folds each repeat feature/model selection using training units only.
The primary figure contains unit dots and a held-out-unit confusion matrix;
there is no folder-level holdout panel.

### Expanded burst metrics, LDA only

[explore_mcs_burst_lda.py](../scripts/explore_mcs_burst_lda.py) adds 1,190 burst
and spike-train structure metrics to the original 156 metrics. The observation
remains one sorted unit, with SUA/MUA pooled. Only LDA classifiers and LDA
projections are fitted for this extension. The same three outer unit folds
compare original and expanded feature sets; preprocessing, redundancy pruning,
and model/feature selection remain inside training folds.

Results, definitions, the complete added-metric catalog, and one figure are
under the existing scratch analysis directory in `burst_lda/`. Added metric
values are compressed in `burst_metrics.npz`, with recording and unit join IDs;
original metric values and continuous recordings are not duplicated.

Burst definitions sweep 10/25/50/100/200-ms maximum adjacent ISIs and minimum
3/5 spikes, separately in pre/post 5-second and 10-second windows and the
0.5–10-second response window. Metrics cover burst count/rate, spike/time
fractions, duration, spikes per burst, intraburst firing and variability,
interburst gaps, first-burst timing, and pre/post changes. Multiscale Fano,
active-bin fractions, peak rates, ISI quantiles, pause fractions, and serial
ISI structure supplement them. These are operational short-ISI burst metrics;
adding more predictors does not by itself establish better discrimination.

The user correctly noted that the initial expanded-search figure displayed
identical clouds. Its two fitted models both selected 87 original inputs and
zero new burst inputs. That figure is a search-outcome comparison, not a view
of new burst features. The corrected explicit input comparison is generated by
[correct_mcs_burst_lda_comparison.py](../scripts/correct_mcs_burst_lda_comparison.py):
original-only, new-burst-only, and a combination required to select from both
blocks. The scratch `burst_lda/ACTUAL_FEATURE_COMPARISON.md` and
`actual_lda_selected_metrics.csv` provide actual selected counts and names.

## Locked metric access and channel/unit maps

The active **87 original + 128 burst = 215-metric** configuration now has a
dedicated [access guide](MCS_ACTIVE_LDA_ACCESS.md), a frozen compressed unit table,
and saved numeric LDA transforms on scratch. Use the guide's loader to obtain
the exact inputs and LD coordinates without repeating feature selection.
The guide also defines the requested 5-/10-second e-stim channel/unit delta map,
its recording-selection rule, exact numerical export, and provenance.

## Active user-selected LDA configuration

The user explicitly selected **87 original + 128 new burst metrics (215 total)**
for subsequent work. Use this combined configuration unless the user changes it.
Do not replace it based on accuracy comparisons. Continue with Actuators +
effectors, one unit per dot/observation, and SUA/MUA pooled.

[mcs_active_lda_configuration.json](mcs_active_lda_configuration.json) lists the
exact 215 metric names, model settings, and source artifacts. This is the active
descriptive feature set; its feature selection used full-data labels. Keep new
major outputs on scratch and create only explicitly requested outputs/plots.
