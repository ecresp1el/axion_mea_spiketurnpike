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

### Experiment: Well-Level Unit-Grid Waveform Review PDF

Question tested:

```text
Can we generate a dataset-wide, well-level unit-grid waveform review artifact
that lets a human rapidly inspect each Kilosort-good unit's normalized mean
template waveform, organized one page per completed well?
```

Expected result:

```text
A single PDF should contain one page per completed well. Each page should show a
grid of normalized Kilosort-good dominant-channel `templates.average` waveforms,
with one subplot per unit. Each page should include recording, well,
Kilosort-good unit count, mean trough-to-peak duration, median trough-to-peak
duration, and Step 1 filtering/preprocessing metadata.
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

Filtering/preprocessing metadata included on pages and in sidecars:

```text
recording_is_filtered:
  true
recording_class:
  spikeinterface.core.binaryfolder.BinaryFolderRecording
recording_dtype:
  int16
skip_kilosort_preprocessing:
  true
kilosort_highpass_cutoff:
  300
kilosort_do_CAR:
  false
kilosort_do_correction:
  false
kilosort_whitening_range:
  8 or 16, depending on the well
```

Outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/figures/waveform_population/figure__well_waveform_unit_grid_review.pdf
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/well_waveform_unit_grid_review_summary.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/well_waveform_unit_grid_review_provenance.json
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/repro/plot_well_waveform_population_validation_pdf_command.sh
```

Confirmed finding from this experiment:

```text
A unit-grid waveform review PDF now exists for all completed wells. The
experiment did not classify units, flag units, or interpret biological validity.
```

### Experiment: PV Reporter Filter-Variant Waveform Review Setup

Question tested:

```text
Can we produce one comparable unit-grid waveform PDF per filtering variant for
the same biological recording:
pv_reporter_cl23_dorsal_and_ventral_exp17_2(000)?
```

Expected result:

```text
Four filtering conditions should be represented:
primary Neural Broadband, BroadbandProcessor, Filter(1Hz-200Hz), and
Filter(200Hz-3kHz). Each condition should ultimately have a per-recording PDF
with one page per reviewed well and one subplot per Kilosort-good unit.
```

Experiment:

```text
Checked existing AIND/Step 1 outputs for the four raw variants.
Submitted a targeted AIND Step 1 lane for the three missing variants only.
Wells submitted for each missing variant:
  A2, A3, B1, B2, B3
```

Result:

```text
The primary Neural Broadband condition already has completed Step 1 outputs and
an existing waveform PDF. The three derived/filter variants did not yet have
completed Kilosort/Step 1 analyzer outputs, so true sorted-unit waveform PDFs
cannot be produced for them until those jobs finish.

Submitted missing Step 1 work on 2026-07-08:
  3 filtering variants x 5 wells = 15 well pipelines

Submitted variants:
  filterreview_pv_5_28_cl23_exp17_2_000_broadband_processor
  filterreview_pv_5_28_cl23_exp17_2_000_filter_1hz_200hz
  filterreview_pv_5_28_cl23_exp17_2_000_filter_200hz_3khz
```

Saved command inputs and follow-up scripts:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/filter_variant_waveform_review_20260708/pv_reporter_cl23_exp17_2_filter_variant_recordings_manifest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/filter_variant_waveform_review_20260708/recording_batch_plan/recording_batch_manifest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/filter_variant_waveform_review_20260708/recording_batch_plan/submitted_recording_batches.tsv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/filter_variant_waveform_review_20260708/build_filter_variant_waveform_pdfs_after_step1.sh
```

Readiness outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/filter_variant_waveform_review_20260708/filter_variant_step1_manifest.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/filter_variant_waveform_review_20260708/filter_variant_logical_groups.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/downstream/filter_variant_waveform_review_20260708/filter_variant_missing_step1_outputs.csv
```

Confirmed finding from this experiment:

```text
The existing waveform PDF for this biological recording represents only the
already completed primary/Neural Broadband AIND Step 1 output. The desired
per-filter waveform PDFs require independent Kilosort/Step 1 outputs for each
raw filter variant. Those missing Step 1 jobs have been submitted but are not
complete yet.
```

## Metadata Provenance Correction

Question tested:

```text
Are the numeric Axion filter settings for the PV reporter raw variants present
only in filenames, or are they present in raw metadata that should be parsed and
passed through the CSV handoffs?
```

Expected result:

```text
If Axion stored the values in `dataset_description`, the pipeline should parse
and carry them as structured columns instead of relying on filename labels.
```

Result:

```text
The values are present in `dataset_description`. The previous simplified
extraction kept only first repeated `High Pass Filter`/`Low Pass Filter` labels
and lost cutoff/pole values plus the second BroadbandProcessor filter block.
```

Confirmed finding from this experiment:

```text
Axion filter metadata must be treated as first-class provenance. The corrected
parser is `src/axion_mea/filter_metadata.py`, and the corrected audit output is:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/axion_file_ground_truth_20260708_filter_metadata_patch/
```

For `pv_reporter_cl23_dorsal_and_ventral_exp17_2(000)`, the parsed metadata is:

```text
primary .raw: Neural Broadband, acquisition high-pass 0.1 Hz IIR, low-pass None
_BroadbandProcessor.raw: 200 Hz to 5 kHz Butterworth plus 1 Hz to 200 Hz Median DownSampler
_Filter(1Hz-200Hz).raw: 1 Hz to 200 Hz Butterworth
_Filter(200Hz-3kHz).raw: 200 Hz to 3 kHz Butterworth
```

### Lumos Unit-Universe Correction And Robust Local-Excursion Metric

Question tested:

```text
Were the July 9 exploratory waveform metrics computed for all possible Lumos
units, or only a narrower KSLabel-good subset?
```

Result:

```text
The earlier 197-unit table was not the all-Lumos unit universe. It represented
only a narrower KSLabel=good subset from the then-current good-unit table.

The current Lumos pass contains:
  Lumos well rows in ground truth: 256
  GUI-ready Lumos wells with standard analyzers/templates: 150
  Sorted units measured from those GUI-ready analyzers: 900
  KSLabel counts: good=276, mua=624

Opto/stim status is independent of waveform metric availability:
  unit rows in stim-ok wells: 392
  unit rows in stim-unavailable wells: 211
  unit rows not represented in the stim guide table: 297
```

Outputs:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_all_sorted_unit_waveform_metrics_20260709.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_all_sorted_unit_waveform_metrics_20260709_summary.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/lumos_48well_good_kslabel_ttp_distribution_template_best_ptp_20260709_all_lumos.csv
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/local_excursion_halfwidth_rep_comparison_20260709_all_lumos.csv
```

Metric update:

```text
Added exploratory robust_local_* waveform metrics. These keep the
local-excursion amplitude definition, midpoint=(Peak1 + trough)/2, but change
crossing selection. Half-width and REP50 now use adjacent-sample crossings with
linear interpolation and require the crossing to occur on the immediate
monotonic descent/recovery limb. If the waveform reverses before reaching the
midpoint, the robust metric reports a status instead of using a later tail
crossing.
```

Confirmed finding:

```text
The issue with the previous local-excursion metric was crossing selection, not
the midpoint amplitude definition. The robust_local_* columns are exploratory
only. Production waveform metrics and the TTP-based FS/RS classifier are
unchanged.
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
Human review of the well-level unit-grid waveform PDF. The reviewer should
scroll one page per well and decide whether the per-unit mean/template waveforms
look like reasonable extracellular spike waveforms.
```

Current status:

```text
Not started
```

### PV Reporter Filter-Variant Waveform Comparison

Question:

```text
How do Kilosort-good unit waveforms differ across the primary Neural Broadband,
BroadbandProcessor, Filter(1Hz-200Hz), and Filter(200Hz-3kHz) variants of
pv_reporter_cl23_dorsal_and_ventral_exp17_2(000)?
```

Why it is important:

```text
The current biological-validity review depends on the waveform representation
used by Step 1. This targeted comparison will show whether the observed waveform
morphology depends strongly on the upstream Axion filtering variant.
```

Single experiment that will answer it:

```text
After the submitted Step 1 jobs complete, run:
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/filter_variant_waveform_review_20260708/build_filter_variant_waveform_pdfs_after_step1.sh
```

Current status:

```text
Running. The missing Step 1/Kilosort jobs have been submitted; waveform PDFs for
the three derived/filter variants do not exist yet.
```
