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

### Experiment: Well-Level Waveform Population Review PDF

Question tested:

```text
Can we generate a dataset-wide, well-level waveform population review artifact
that lets a human rapidly inspect whether each completed well's Kilosort-good
template waveforms look like reasonable extracellular spike waveforms?
```

Expected result:

```text
A single PDF should contain one page per completed well. Each page should show
all normalized Kilosort-good dominant-channel template waveforms in light gray,
the population mean waveform, and +/- SEM, with recording, well, Kilosort-good
unit count, mean trough-to-peak duration, and median trough-to-peak duration.
```

Experiment:

```text
Script:
  scripts/plot_well_waveform_population_validation_pdf.py
Input table:
  /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/master_waveform_metrics_table.csv
Completed wells plotted:
  99
Kilosort-good units plotted:
  998
```

Result:

```text
PDF generated successfully:
  99 pages
Summary CSV rows:
  99
Summary CSV Kilosort-good unit total:
  998
```

Outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/figures/waveform_population/figure__well_waveform_population_review.pdf
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/well_waveform_population_review_summary.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/well_waveform_population_review_provenance.json
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/repro/plot_well_waveform_population_validation_pdf_command.sh
```

Confirmed finding from this experiment:

```text
A population-level waveform review PDF now exists for all completed wells. The
experiment did not classify units, flag units, or interpret biological validity.
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
Human review of the well-level waveform population PDF. The reviewer should
scroll one page per well and decide whether the well-level waveform populations
look like reasonable extracellular spike waveforms.
```

Current status:

```text
Not started
```
