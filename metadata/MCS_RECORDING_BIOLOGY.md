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
