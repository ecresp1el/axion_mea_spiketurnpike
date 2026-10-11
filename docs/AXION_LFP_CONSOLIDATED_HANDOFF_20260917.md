# Consolidated Axion metadata and LFP readiness

Updated 2026-09-17. This is the current entry point for the older Axion/DIV140 investigation and the newer fusion and dorsal/ventral files. Earlier inventories, raw annotations, original notebooks, and saved plot evidence are retained.

**Gamma comparison follow-up:** the [quick fusion-versus-dorsal screen](../audit-output/axion_gamma_quick_screen_20260917/README.md) found a narrow72–73 Hz feature in May27 fusion recordings that also appears in explicitly empty wells. No convincing fusion-specific neuronal gamma is established by this sampled analysis. The report preserves per-well metrics, a comparison figure, grouping, and limits; usable LFP acquisition is distinct from a demonstrated oscillation.

## What can be used for LFP

**18 recordings lasting at least two minutes have compatible low-frequency acquisition settings and pass the sampled voltage checks.** They provide **79.77 minutes** of recording time, before artifact rejection. One additional **5.25-second** H1 clip contains accessible low-frequency voltage but is retained for trace inspection, not stable slow-band PSD/coherence estimates.

| Collection | Use for LFP | Duration | Disposition of other recordings |
|---|---:|---:|---|
| May–June 2026 fusion recordings | 13 originals | 41 min total; 3–5 min each | Their filtered exports are alternate views of these recordings, not independent replicates. |
| May 2026 dorsal/ventral recordings | 4 longer originals | 36.77 min total | One additional 5.25s clip; three H1 acquisitions exclude conventional low-frequency LFP. |
| April 17, 2024 D235 dedicated LFP | 1 original | 2 min | The four other D212–D235 recordings used Neural Spikes analog acquisition and are excluded from conventional LFP. |
| December 2025–March 2026 `Fusion MEA` archive | 0 of 32 | — | Acquired with 200 Hz high-pass; retain for spike analysis. |
| Historical DIV140 CO–CO versus CO–MGEO comparison | Unconfirmed | Raw source not located | Well identities are reconstructed, but processed spike outputs do not establish an LFP source. |

**Correction to the earlier inventory:** a filename ending `Filter(1Hz-200Hz)` does not establish LFP suitability. H1 plate **133-1555**, `h1_dorsal_and_ventral_exp17_3(001)`, `(002)`, and `(003)` report **200 Hz acquisition high-pass in both their original and derived headers**. A later 1–200 Hz export cannot restore those lost low frequencies. Use `(000)` from this plate for LFP; its acquisition high-pass is 0.1 Hz.

The selected newer originals use Neural Field Potentials acquisition, 0.1 Hz digital high-pass, and 2 kHz digital low-pass. The dedicated D235 recording uses Cardiac Low Amplitude acquisition with 0.1 Hz digital high-pass and no recorded digital low-pass. Legacy Axion documentation supports that mode as low-frequency-capable; see the [older-file review](../audit-output/axion_lfp_consolidated_20260917/old_2024_lfp_review.md) for exact settings and documentation/version limits. Hardware acquisition bandwidth and later digital processing are distinct in the [Axion guide](https://cdn.stemcell.com/media/files/manual/10000031519-MAN_00.pdf).

## Everything retained in the consolidated inventory

The audit covers **101 physical `.raw` files representing 58 acquisition recordings**, plus the unlocated DIV140 dataset. It includes 58 originals, 16 nominal LFP-filter exports, 16 spike-filter exports, 10 older archive copies, and one BroadbandProcessor export. Copies and derivatives share a recording ID with their source. All 101 have readable, complete declared data regions; duplicate evidence is sampled hashes, not full-file hashes.

- [Canonical recordings and final readiness](../audit-output/axion_lfp_consolidated_20260917/canonical_recordings_readiness.csv): one row per recording plus DIV140, with analysis disposition.
- [All physical files and acquisition/derived settings](../audit-output/axion_lfp_consolidated_20260917/candidate_manifest.csv): paths, dates, plate serials, duration, sampling, signed voltage scale, filters, referencing, file roles, integrity, and exclusion reasons.
- [Complete metadata archive](../audit-output/axion_lfp_consolidated_20260917/candidate_manifest.json): descriptions, raw metadata bytes, dataset headers, latest well tags, and previous audit records.
- [All well metadata](../audit-output/axion_lfp_consolidated_20260917/combined_well_metadata.csv): **630 rows**, including file variants, three standalone plate maps, and DIV140. Stored labels remain separate from curated identity, confidence, and human overrides.
- [Selected LFP originals](../audit-output/axion_lfp_consolidated_20260917/lfp_selected_recordings.csv) and [their 114 well records with QC](../audit-output/axion_lfp_consolidated_20260917/lfp_selected_wells.csv).
- [Schema and scope](../audit-output/axion_lfp_consolidated_20260917/MANIFEST_SCHEMA.md), [source provenance](../audit-output/axion_lfp_consolidated_20260917/inventory_source_provenance.json), and [machine-readable summary](../audit-output/axion_lfp_consolidated_20260917/lfp_readiness_summary.json).

The BroadbandProcessor derivative contains two streams, including one sampled at 100 Hz; it is not a substitute for the original when analyzing through 200 Hz. Thirteen of the 16 nominal 1–200 Hz exports have compatible source acquisitions, but their originals are preferred for reproducible processing.

## Well identities and biological comparisons

**DIV140:** A1–A3 are strongly inferred to be cortical–cortical control fusions (CO–CO/CxCx); B1–B3 are cortical–MGE assembloids (CO–MGEO/CxMGEO). The historical age-comparison cohort uses B1–B3, the representative raster uses B1, and the historical 62-unit mean matches Group B in the later full comparison. The manuscript's lower-firing CO–CO group matches Group A. Three wells per group supplied 62 sorted units per group; units are not biological replicates. [Saved plots, exact code/output provenance, and inferred well map](../audit-output/axion_2024_inventory_20260917/DIV140_COMPARISON_EVIDENCE.md) are preserved. This mapping applies only to DIV140.

**D212–D235:** all five recordings store A1/A2 `79B fusion CV EX4`, A3 `79B fusion MW EX10`, and B1–B3 `H9 Fusion CV EX4`. Generic `fusion` labels do not identify CO–CO versus CO–MGEO. CV/MW definitions and genotype assignments remain unresolved. A3's EX10 differs from EX4. The March31 filename says `9B_H9` while well tags say `79B`; both are retained.

**Newer fusion files:** 12 of 13 originals have populated well labels; across these, 64 entries name samples/treatments and eight explicitly mark empty wells. `D307_EX14_Fusions_F5_85F_G12_with sc79(000).raw` has six blank labels. Preserve sample/drug codes without inferring genotype or tissue composition. All wells were enabled and control flags were false, including explicitly empty or vehicle wells; these flags are not biological group labels. Eight empty wells are flagged out of tissue analysis even though their electrodes contain varying background voltage.

**Dorsal/ventral:** PV recordings explicitly store A1–A3 ventral and B1–B3 dorsal. H1 plate 134-0150 `exp17_2(001)` stores the same pattern, but human notes correct **B1/B2 to ventral**, leaving B3 dorsal. Both the original annotation and override are retained. Other H1 blank-label wells carry the handoff's A-row ventral/B-row dorsal default as a curated assignment with its source; that is not an embedded annotation. The 5.25s H1 `exp17_2(000)` is not a substitute for its 453.75s `(001)` recording.

File repetitions, same plate serials, paired filters, before/after drug conditions, and repeated wells must not be counted as independent biological samples. Across years, cell lines, ages, dry/with-media conditions, drug exposure, amplifier modes, and referencing need to be matched or modeled; file availability alone does not make them interchangeable controls.

## Signal checks completed

For all 19 selected originals, the reader validates supported voltage layout, metadata CRCs, signed calibration, actual electrode order, channel count, declared data bounds, and duration. It then reads three 4 s windows near the beginning, middle, and end across all 384 channels. Windows overlap in the short clip. That produced **57 voltage windows and 342 well-window checks**.

- All sampled channels varied; none were constant or all zero.
- No signed-int16 ADC rail hits occurred in the sampled windows.
- Stored metadata contains no latest DataLossEvent tags in the checked101 files. Absence of a tag does not prove every sample is artifact-free.
- [Per-recording results](../audit-output/axion_lfp_consolidated_20260917/signal_qc/recording_qc.csv), [per-well results](../audit-output/axion_lfp_consolidated_20260917/signal_qc/all_well_qc.csv), and [spectral overview](../audit-output/axion_lfp_consolidated_20260917/lfp_sampled_spectra_overview.pdf) are saved.
- Each `signal_qc/recording_NNN/` contains a calibrated **1kHz midpoint preview**, electrode map, sampled PSD, and layout/QC JSON. The selected-recordings table links each folder.

These checks establish accessible voltage and basic sampled signal integrity. They do not establish neuronal activity in every well, absence of artifacts elsewhere, oscillations, or a completed scientific LFP comparison. In particular, varying signals in empty wells are background, not evidence of tissue activity. Full epoch/channel QC remains part of the analysis.

The spectral preview shows a visible 60 Hz peak in the old D235 recording. Its sampled per-well median power fraction in 58–62 Hz reaches about 12.7% of 1–200 Hz power. This is recorded for line-noise review; the saved previews and exports have not been notched. Broad, similar spectra across wells do not by themselves establish tissue-specific oscillations.

## Ready-to-use extraction and analysis route

The tested [reader/exporter](../scripts/audit_axion_lfp_readiness.py) reads original voltage, applies the **signed** volts/count scale, preserves each electrode's well/position, and anti-aliases before downsampling from 12.5kHz to1kHz. It uses overlapped chunks for long recordings and does not whiten, apply a spike high-pass, notch, or rereference. [SciPy's polyphase resampling](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html) applies an FIR low-pass before reducing the sample rate. A1–A3/B1–B3 are recovered from stored channel mappings; channels are not assumed to be grouped consecutively by well.

Working environment used: `/home/elcrespo/miniconda3/envs/mge-organoid-python/bin/python` (Python3.11, NumPy2.4.4, SciPy1.17.1). Four targeted tests pass for old/new layouts, channel reordering, negative calibration, truncation rejection, alias suppression, chunk continuity, and the short-clip flag. An independent review also checked subset/well exports against whole-recording resampling.

From the repository root, this exports the full old LFP A1 well; replacing `--raw` with another selected original and `--well` with its well works the same way. Omit `--well` to export all 384 channels. Use an output folder with adequate space; full selected recordings at 1 kHz/all 384channels require about 7.35GB as float32, versus much larger original recordings.

```bash
/home/elcrespo/miniconda3/envs/mge-organoid-python/bin/python scripts/audit_axion_lfp_readiness.py export \
  --raw '/nfs/turbo/umms-parent/MannyAxionMEAscripts_v1/axion_mea_data_organoid_moredata/MEA files/2024-04-17_79B_H9 fusions_D235 dry_Maestro_LFP_(001).raw' \
  --well A1 \
  --manifest audit-output/axion_lfp_consolidated_20260917/candidate_manifest.csv \
  --output audit-output/axion_lfp_consolidated_20260917/example_full_D235_A1_1khz
```

`voltage_uv.npy` is time×electrode float32 in microvolts; `metadata.json` records calibration, source, sample rates, start time, processing, and electrode map. This command has been run for the complete 120s D235 A1 recording. The output is downsampled voltage, not an already final 1–200Hz bandpass. The manifest option rejects sources not selected as LFP originals.

The [complete D235 A1 example](../audit-output/axion_lfp_consolidated_20260917/example_full_D235_A1_1khz/metadata.json) contains 120,000 samples × 64 electrodes, all finite and varying. `full_recording_psd.npz` contains an actual Welch PSD of this full export (4 s Hann windows, 50% overlap, 0.25 Hz frequency spacing), and `verification.json` records the check. To reproduce that basic analysis:

```python
import numpy as np
from scipy.signal import welch

x = np.load('audit-output/axion_lfp_consolidated_20260917/example_full_D235_A1_1khz/voltage_uv.npy', mmap_mode='r')
frequency_hz, psd_uv2_per_hz = welch(
    x, fs=1000, nperseg=4000, noverlap=2000,
    detrend='constant', axis=0,
)
lfp_band = (frequency_hz >= 1) & (frequency_hz <= 200)
```

For actual LFP comparisons, use a consistent analysis band such as 1–200Hz on eligible sources; account for filter roll-off at band edges. Inspect raw/downsampled traces and spectra, exclude empty wells and bad channels/epochs, assess 60Hz interference and harmonics, and apply any notch/reference consistently with documented parameters. Filter before further decimation, pad/trim filter edges, and never run the LFP through spike-sorting whitening or the 200–300Hz spike high-pass. Compute PSD, band power, spectrograms, or within-recording synchrony after this QC. Inspect shared-reference/common-mode contamination before interpreting coherence. Use longer windows and adequate recording duration for slow frequencies; the 5.25s clip is unsuitable for the primary slow-band comparison.

The available files support LFP analysis of the 18 longer sources. **A cortical-control versus cortical–MGE LFP comparison specifically at DIV140 still requires locating its original continuous recording.** Its spike plots and inferred well map are preserved but cannot supply missing LFP voltage.
