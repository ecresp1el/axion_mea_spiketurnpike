# Waveform Validation Investigation Log

## Confirmed Findings

### Internal Correctness

- The Step 1 `templates.average` waveform is internally consistent with
  extracted analyzer snippets.
  - Verified by re-extracting B3 unit 1 snippets from the Step 1 analyzer
    recording at the exact `random_spikes` used by the SpikeInterface templates
    extension.
  - Result: max absolute difference from stored `templates.average` was
    `2.614423632696372e-06 uV`; RMS difference was
    `9.69948007837167e-07 uV`.

- Dominant channel selection is correct for the audited representative well.
  - Verified in B3 by recomputing the dominant template channel for every
    Kilosort-good unit.
  - Result: `50/50` Kilosort-good units used the same dominant channel encoded
    in `template_reference`.

- Waveform metric calculations are internally consistent with the stored
  templates.
  - Verified in B3 by recomputing trough, rebound peak, and trough-to-peak
    duration from each unit's stored dominant-channel template.
  - Result: recomputed trough-to-peak durations matched the master table
    exactly for `50/50` Kilosort-good units.

- The implementation has therefore been validated for internal correctness.
  The remaining question is biological validity, not whether the code retrieves
  or measures the stored templates consistently.

### Experiment: Representative Well B3 Rebound-Peak Biological Validity

Question tested:

```text
For one representative well, does the detected rebound peak correspond to the
visually expected post-trough rebound peak for every Kilosort-good unit?
```

Expected result:

```text
If current Step 1 template features are biologically acceptable, most
Kilosort-good units should have a visible post-trough rebound peak, and only a
small minority should be ambiguous because of edge-limited, weak/noisy, or late
rebound peaks.
```

Experiment:

```text
Representative recording:
  sixwell_manual_primary_5_28_26_pvreporter_134-0150_pv_reporter_cl23_dorsal_and_ventral_exp17_2(000)
Representative well:
  B3
Units inspected:
  50 Kilosort-good units
Input audit:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/representative_well_B3_dominant_template_audit.csv
Script:
  scripts/audit_representative_well_rebound_peak_biological_validity.py
```

Result:

```text
Biologically well measured:
  43/50 units = 86%
Ambiguous:
  7/50 units = 14%
```

Ambiguous units:

```text
unit 0:
  low_amplitude_noisy_rebound
unit 2:
  edge_limited_late_rebound
unit 57:
  late_rebound_limited_return_to_baseline
unit 66:
  edge_limited_no_visible_return_after_peak
unit 95:
  weak_noisy_late_rebound
unit 97:
  small_amplitude_late_rebound
unit 123:
  edge_limited_late_rebound
```

Outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/representative_well_B3_rebound_peak_biological_validity.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/representative_well_B3_rebound_peak_biological_validity_provenance.json
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/figures/rs_fs_waveforms/figure__representative_well_B3_rebound_peak_biological_validity.png
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/repro/audit_representative_well_rebound_peak_biological_validity_command.sh
```

Confirmed finding from this experiment:

```text
In representative well B3, the current Step 1 dominant-channel template
measurements appear biologically well measured for most Kilosort-good units
under visual rebound-peak inspection, but a nonzero ambiguous subset exists.
```

## Open Questions

### Biological Validity Of Current Step 1 Template Features

Question:

```text
Do the waveform features computed from the Step 1 templates correspond to
biologically valid extracellular waveform measurements suitable for RS/FS
classification across the Step 3 dataset?
```

Why it is important:

```text
The master table's RS/FS classification depends on whether trough-to-peak
duration, waveform asymmetry, and repolarization slope measured from Step 1
templates are biologically interpretable extracellular waveform features. The
internal implementation is now validated, but biological acceptability must be
established before changing metric definitions or waveform representations.
```

Single experiment that will answer it:

```text
Apply the same rebound-peak biological-validity audit to a representative
dataset-level sample of Kilosort-good units across completed wells, stratified
by recording, well, RS/FS class, and trough-to-peak range. Quantify the fraction
of biologically well measured versus ambiguous units and the ambiguity modes.
```

Current status:

```text
Running
```
