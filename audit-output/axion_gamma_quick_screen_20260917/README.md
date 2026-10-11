# Quick fusion-versus-dorsal gamma screen

2026-09-17. **The quick screen does not establish fusion-specific neuronal gamma.** A narrow 72–73 Hz feature occurs in the May27 fusion recordings, but also in explicitly empty wells in those recordings. It is therefore a shared-signal/artifact concern. The later fusion and dorsal-only well-median spectra do not show comparable candidates in this screen.

| Subset | Well-recording observations with a candidate peak ≥3 dB above fitted background |
|---|---:|
| Named fusion wells, May27 | 20/20 across 4 recordings |
| Explicitly empty wells in the same May27 subset | 4/4 across 3 recordings |
| Named fusion wells, later dates | 0/44 across 8 recordings |
| Dorsal-only wells | 0/10 across 4 recordings |
| Old D235 fusion wells, outside the excluded mains band | 0/6 in 1 recording |

These are repeated well-recording observations, **not independent biological replicates**, and the thresholds are descriptive screening choices, not statistical significance. The six blank-label wells in a fifth May27 fusion recording are excluded from the biological comparison and retained in the output as unlabeled; they also show the shared feature. All eight explicitly empty wells remain available as background controls, including four later-date observations without the feature.

At a looser 2 dB threshold, only one additional named fusion observation qualifies (June26 B3, about 72 Hz). Dorsal remains 0/10. The original spectra show that the strongest May27 feature is narrow: representative fusion A1 and empty B1 in recording001 both peak at 72.5 Hz, with unsmoothed half-height widths about 0.68 Hz at 0.5 Hz resolution. Widths from smoothed spectra were not interpreted as biological bandwidth.

An additional short-preview check found approximately 0.91 coherence at 72 Hz between the spatial-median voltage of fusion A1 and empty B1 in that recording. This supports concern about a common signal; with only a 4 s preview, it is not proof of the mechanism. Electrical interference, cross-talk, and other shared sources have not been distinguished. The data do not support calling this a tissue-specific oscillation just because its frequency falls in the gamma range.

## What was analyzed

- Existing calibrated PSDs from three 4 s windows near the beginning, middle, and end of each of 18 longer recordings. Each electrode PSD used 2 s Welch segments (0.5 Hz spacing), and the stored PSD is the median across the three windows. The quick comparison uses the median of 64 electrode PSDs within each well.
- Gamma screen: 30–80 Hz, excluding 55–65 Hz to avoid the strong 60 Hz interference neighborhood. This deliberately cannot assess a neuronal oscillation lying inside that excluded interval.
- A robust linear background fit in log-frequency/log-power over 10–200 Hz, omitting ±3 Hz around 60/120/180 Hz. Log-PSD smoothing sigma 1 Hz supports candidate detection. Candidates have local prominence ≥1 dB and exceed background by ≥2 dB; the primary descriptive table uses ≥3 dB. This is a simple exploratory screen, **not FOOOF/specparam** or a validated oscillation classifier. Separating spectral peaks from aperiodic background follows the methodological distinction described by [Donoghue et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC8106550/).
- Dorsal subset: H1 exp17_3(000) B1–B3 (handoff default), H1 exp17_2(001) B3 (B1/B2 are ventral overrides), and B1–B3 in each PV-reporter recording. The 5.25 s clip is excluded.
- Named fusion versus dorsal cohorts differ in cell line, age, date, plating, and drug conditions. Repeated PV recordings and reused wells are not independent samples. Unresolved fusion composition/genotype mappings remain unresolved.

Raw gamma-band power alone is not the conclusion: it includes background and shared peaks. For reference, median 30–55 plus 65–80 Hz power was 0.160 µV² for named newer fusion observations, 0.104 µV² for dorsal observations, and 0.428 µV² for empty observations; these unmatched pooled values do not establish a biological effect. Old D235 is kept separate (different acquisition, prominent 60 Hz feature).

**Scope:** no reliable fusion-only gamma is established by the sampled well-median spectra. This does not rule out transient or spatially localized gamma, gamma outside 30–80 Hz, activity masked by the excluded mains band, or an effect in the unlocated DIV140 controls. Full-recording electrode/epoch analysis and matched biological controls would be needed for a stronger conclusion.

## Saved evidence

- [Comparison figure](gamma_quick_comparison.pdf) and [PNG](gamma_quick_comparison.png).
- [Every well's metrics, grouping, source path, and peak width](well_gamma_screen.csv).
- [Group summary](summary.json).
- Reproduce with `/home/elcrespo/miniconda3/envs/mge-organoid-python/bin/python scripts/quick_axion_gamma_screen.py` from the repository root.

Original metadata, recordings, prior notebooks, and previous audit outputs were not changed by this analysis.
