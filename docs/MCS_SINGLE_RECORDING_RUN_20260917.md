# First complete MCS AIND recording run

## Recording and scope

Status: complete; all 11 AIND stages and final durable-output checks passed.
Slurm parent job `61321124` exited `0:0` in 6m 23s, with no failed stages or
retries. Only this recording was submitted.

The established Axion Step 1 AIND/SpikeInterface TH5 route ran on the
entire `Actuators & Effectors/Stim 1/353.1/2021-06-22T15-23-26McsRecording`
acquisition. This is one physical MEA, not an Axion well. Biological inclusion,
UnitRefine/Bombcell, manual curation and response statistics are separate work.

Project root on Great Lakes:
`/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder`.
On the Mac, the same root is `/Volumes/umms-parent/axion_mea_spiketurnpike_projectfolder`.

Paths below are relative to that root:

```text
data/interim/mcs_sorting_inputs/Actuators & Effectors/Stim 1/353.1/2021-06-22T15-23-26McsRecording/
data/interim/aind_mcs_inputs/Actuators_Effectors/Stim_1/353.1/2021-06-22T15-23-26McsRecording/th5_20260917_125847/
results/aind_mcs/Actuators_Effectors/Stim_1/353.1/2021-06-22T15-23-26McsRecording/th5_20260917_125847/
logs/aind_mcs/mcs-aind-61321124.out
logs/aind_mcs/mcs-aind-61321124.err
```

Runtime path components are sanitized because the external Nextflow pipeline
contains unquoted shell paths. Original source names are retained in the MCS
recording manifest; no source files were renamed or altered.

## Inputs and decisions

- All 6,184,000 samples at 10 kHz, lasting 618.4 seconds. The staged binary is
  exactly 1,459,424,000 bytes: lossless sample-major int32, not int16.
- 59 signal channels, with the source `Ref` channel at stream index 14 excluded.
  Gains are mapped by original stream index, not by slicing the 60-entry gain
  array. All selected channels have gain 0.059605 uV/count and zero ADC offset.
- Matching acquisition XML specifies `60MEA200/30iR`, 200 um pitch and 30 um
  contact diameter. XML hardware IDs and channel labels match the source order.
  A new ProbeInterface map is written without altering the old staged sidecar.
- The vendor HDF5 declares one continuous interval covering the full sample
  count. Small first, near-stimulus and final windows were checked against the
  staged binary. Hardware events retain their original IDs, labels and times:
  five pulse starts and five stops, first start at 299.3519 seconds.
- The CytoView TH5 configuration is the baseline, preserving thresholds 5/8,
  single-channel threshold 6, CAR off, sign inversion off, no motion correction,
  all Kilosort labels retained, batch size 15000 and Kilosort preprocessing on
  with its 300 Hz highpass. Outer preprocessing casts to int32 only.
- Geometry-dependent `dmin`/`dminx` become 200 um. The sorter channel-distance
  limit and analyzer sparsity radius become 233.333333 um, preserving CytoView's
  350/300 pitch ratio. This is an explicit adaptation, not a new parameter sweep.
- `nt=31` is retained, now 3.1 ms at 10 kHz. Kilosort's 0.25 ms duplicate-spike
  window and AIND's 0.9 redundant-unit threshold remain separate cleanup steps.
  Analyzer random-spike sampling is seeded with 0.
- Analyzer waveforms are extracted from the calibrated outer-preprocessed
  recording. They are not Kilosort's internally highpass-filtered templates.

## Code and execution

`scripts/prepare_mcs_aind_recording.py` validates the existing binary/sidecars
against acquisition XML and writes the probe, mapped gains, explicit parameters,
recording manifest and `run_aind_mcs.env`. It refuses an existing run path.

`slurm/run_aind_nwb_well.sbatch` now supports `AIND_INPUT_MODE=spikeinterface`
with a recording-relative run path. Its original Axion NWB mode remains the
default. No fake well or prerequisite Axion NWB is created for MCS.

The same external `aind-ephys-pipeline/pipeline/main_multi_backend.nf`, staged
capsules and `si-0.104.8` containers run in `full` mode. The MCS scheduler config
includes the existing Great Lakes config, with 10-minute CPU-stage and 30-minute
Kilosort limits for this single-recording canary. The parent limit is two hours.
Working files are under the parallel `scratch/aind_mcs_nextflow/` hierarchy.

## Outputs and interpretation

The output layout is:

```text
spikesorted/block0_None_recording1/       Saved initial SpikeInterface sorting
postprocessed/block0_None_recording1.zarr/  Calibrated sorting analyzer
curated/block0_None_recording1/          Postprocessed sorting and available labels
nwb/                                    Unit/electrode interchange export
quality_control/                        AIND quality-control artifacts
visualization/                          Raw and outer-preprocessed trace figures
repro/                                  Submitted settings and provenance
nextflow/                               Process trace, logs and execution reports
validation_summary.json                 Independent consistency checks
unit_summary.csv                        Unit IDs, labels and per-stage spike counts
```

Kilosort returned **44 units and 40,623 spikes**. All 44 units and their spike
trains survived empty-unit and redundant-unit cleanup. All are labeled `mua`
by Kilosort; none is labeled `good`. These are sorted clusters, not 44 confirmed
single neurons. The unit table preserves original `KSLabel`, `ContamPct` and
`Amplitude` properties without treating the native Kilosort amplitude property
as a calibrated analyzer waveform measurement.

All six configured analyzer extensions were saved: `random_spikes`, `templates`,
`spike_amplitudes`, `template_similarity`, `correlograms`, and `unit_locations`.
As in the adopted lightweight Axion Step 1 profile, quality/template metrics
were not requested, so the automatic curation stage explicitly skipped
classification. It generated no curation recommendations. The `curated` folder
therefore contains the postprocessed sorting, not manually approved units.

QC provides raw trace, PSD and RMS figures; overall review remains `Pending`.
Its channel-label counts are not single-unit quality counts. Hosted sorting
visualization was skipped because no Kachery credentials were configured. MCS
events remain in `events.csv` and `repro/mcs_input/events.csv`; the inherited
HARP-specific stimulus QC does not consume them automatically.

The established AIND sorter deletes its temporary native Kilosort folder after
loading it. The durable spike output is the saved SpikeInterface sorting, with
Kilosort labels and `original_cluster_id`. Postprocessing can remove redundant
whole units. The collector's `curated` sorting does not automatically apply
curation JSON recommendations; it is not evidence of manual review.

NWB is exported as a Zarr directory despite its `.nwb` suffix. No raw or LFP
traces are embedded, matching the submitted `write_raw=false`, `write_lfp=false`
settings. Its `ks_unit_id`
crosswalk identifies saved sorting units; spike times are seconds. Kilosort
labels remain in the SpikeInterface outputs. Default AIND session time is the
processing-time metadata, not verified MCS acquisition time; consult the source
recording identity and acquisition sidecars for acquisition provenance.

## Validation

Repository tests: 54 passed, including MCS source-channel/gain mapping,
59/60-channel and 100/200 um geometry cases, relocated source paths, exact binary
dimensions, int32 extreme values, settings propagation, spike consistency,
durable analyzer reload and NWB corrections. Run with `TMPDIR=/tmp` to avoid
NFS cleanup races involving open test memmaps; the default network temporary
directory caused one cleanup-only error before the full local-temp rerun passed.

Final-run spike validation passed, with all submitted settings matching recorded
settings and no missing configured analyzer extensions.
`scripts/validate_mcs_aind_output.py` checks
submitted versus recorded sorter settings, bounds, unit/cluster IDs, per-stage
spike preservation, analyzer extensions, calibrated trace reload and geometry.
It also rejects analyzer recording references into scratch and reports the
absence of Kilosort `good` labels as a scientific-review warning, not a broken
sorting artifact. This validator is explicitly scoped to this 59-channel,
10 kHz canary.

### Finalization performed after AIND completed

`scripts/finalize_mcs_aind_recording.py` copied the complete int32 recording to
`preprocessed/block0_None_recording1/` inside this result. It used the public
SpikeInterface load/save APIs to update the analyzer reference, without
recomputing extensions or changing spikes, labels, calibration or coordinates.
All copied files were checksum-verified. The full trace SHA256 matches the
original staged binary:

```text
f4fc25f3072f8b5b8e431d40769e6f98faab05a82386343466b227b7e7fc0616
```

`durable_recording_report.json` records the checks. The earlier analyzer remains
under `repro/analyzer_before_durable_recording/` for provenance; the active
analyzer has no scratch recording dependency. The source ProbeInterface file
retains physical contact labels/dimensions; the inherited AIND recording stores
locations without the full contact-vector property.

`scripts/finalize_mcs_aind_nwb.py` then corrected two inherited NWB-export defects
in this new run only: it removed the exact mock Subject and converted waveform
mean/SD values from microvolts to schema-required volts. It retained the required
processing-time timestamps but explicitly labeled them as placeholders in NWB
notes, together with source nominal acquisition time `2021-06-22T15:23:26` and
unknown acquisition timezone. No acquisition UTC instant was invented.

Every NWB unit ID, original cluster ID and spike train matches the saved sorting;
all 59 electrode positions and both waveform arrays match the calibrated
analyzer. PyNWB reread and schema validation passed, as did an idempotent repeat
of finalization. The original NWB is preserved under
`repro/original_nwb_before_mcs_corrections/`; the correction evidence is in
`repro/nwb_finalization_report.json`.

These finalizers ran after, not inside, the submitted AIND job. A future run must
perform the same finalization and validation steps before being called durable
and complete. The recording finalizer deliberately refuses an existing target;
the NWB finalizer verifies an already-corrected result without rescaling again.

One successful recording will not validate the entire archive. Other array
models, unresolved geometry, source reference roles and short recordings retain
the eligibility requirements in [the workflow map](AXION_TO_MCS_WORKFLOW_MAP.md).
