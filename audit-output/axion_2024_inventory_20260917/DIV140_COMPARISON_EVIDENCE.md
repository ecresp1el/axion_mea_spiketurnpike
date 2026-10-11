# Older cortical–cortical versus cortical–MGE comparison

Checked 2026-09-17 after the user recalled cortical–cortical fusion controls. Original data and notebook were read only.

## Reconstructed well assignment

**Strong analysis-based inference: A1–A3 are cortical–cortical (CO–CO / CxCx) controls; B1–B3 are cortical–MGE (CO–MGEO / CxMGEO) assembloids at DIV140.** This updates the initial metadata-only conclusion that the rows were unresolved. It is supported by the user's saved analyses and manuscript figure identities, not by guessing the meaning of generic raw labels.

| DIV140 wells | Inferred composition | Saved plot group | Units per well | Group mean maximum firing rate |
|---|---|---|---|---:|
| A1, A2, A3 | Cortical–cortical control fusions | Group A | 7, 16, 39 | 6.5323 |
| B1, B2, B3 | Cortical–MGE assembloids | Group B | 12, 38, 12 | 9.3226 |

The 62 observations per group are sorted units pooled across three wells, not 62 biological replicates. These assignments apply to `Organoids_d140`; they must not be transferred to the separate D212–D235 raw files merely because well coordinates match.

The inference has three linked supports:

1. In historical commit `854f6b72a4fdc6f131e0f1f888e78399bdc1083f` (2025-03-20), the active DIV140 source in cell 28 is `all_data_MEA_d140.mat`. The full `all_data.mat` source is commented directly below `#only to combine CxCX vs CxMGEO`. Saved cell 54 lists **only B1, B2, B3** for the active DIV140 cohort. Historical cell 40 reports 62 units and mean maximum firing rate **9.322581**, matching Group B in the later full comparison; historical cell 63 retains N=62 in the age-comparison CDF outputs.
2. The [representative raster selection](/home/elcrespo/Desktop/githubprojects/lmc_spikes_crespoetal2023/axion_meas_emx_whiskercopy.ipynb:27450) uses **DIV140 B1** alongside the older groups. The [preprint](https://drive.google.com/file/d/1wy_6jGpuzQQ8Es6U7GVawp_SO6RHUm6m/view), version 2025-11-14, describes this three-age raster series as MGEO–CO at DIV140, DIV212, and DIV235 (Figure 6H). This provides a separate analysis-to-biological-label link for row B.
3. The [full comparison's saved output](/home/elcrespo/Desktop/githubprojects/lmc_spikes_crespoetal2023/axion_meas_emx_whiskercopy.ipynb:23421) gives Group A mean 6.5323 and Group B mean 9.3226, with 62 units each. The saved CDF shows Group A shifted toward lower maximum firing rates, matching the manuscript's identification of the lower-firing DIV140 group as CO–CO (Figure 6G). This corroborates the selection history; firing rate alone was not used as a biological classifier.

Preserved evidence:

- [Six-well inferred composition map](div140_inferred_well_map.csv), with assignment basis and confidence separate from raw annotations.
- [Original saved CDF/scatter image](div140_notebook_cell_61_output_2.png).
- [Original saved three-age raster image](div140_notebook_cell_82_output_1.png).
- [Historical and current notebook code/output excerpts](div140_plot_provenance.json), including source hashes, exact historical commit, and manuscript/figure source links. Cell indices are zero-based.

The notebook has mixed execution histories. It was not rerun or overwritten; historical and current saved outputs remain distinguished in the provenance file. The [December 2024 figure draft](https://docs.google.com/presentation/d/1gIQnjAP9WmY0XK9WDgtKoz6nFDn72tYA/edit) also contains the labels `CO x CO D140` and `CO x MGEO D140`.

## Confirmed documentation

The local [analysis notebook](/home/elcrespo/Desktop/githubprojects/lmc_spikes_crespoetal2023/axion_meas_emx_whiskercopy.ipynb:19669) contains the comment `#only to combine CxCX vs CxMGEO` and loads:

`/Volumes/Manny2TB/axion_mea_data_organoid_d140/SpikeStuff/all_data.mat`

Another comment at line 10856 says `#only to compare d140 Cx vs CXMgEO`. The notebook loads this DIV140 source separately from the no-BIC and BIC sources and assigns it the group name `Organoids_d140`.

The saved output of notebook cell 54 lists the DIV140 recording names as `A1`, `A2`, `A3`, `B1`, `B2`, `B3`. [Comparison code](/home/elcrespo/Desktop/githubprojects/lmc_spikes_crespoetal2023/axion_meas_emx_whiskercopy.ipynb:22841) filters to `Organoids_d140` and groups A1–A3 against B1–B3. It labels these only `Group A` and `Group B`.

The [revised manuscript](https://docs.google.com/document/d/1Nkk8_ySeZgsAeU5yjnf80GL47LBrIboY/edit) also describes CO–CO versus MGEO–CO assembloids at DIV140, including a comparison of putative-unit firing rates. This corroborates the existence of the biological comparison. It does not supply a well map in the inspected text.

Notebook history places both comparison comments in commit `854f6b7`, dated 2025-03-20. That is a code-history date, not an acquisition date.

A separate accessible `/nfs/turbo/umms-parent/MannyTest/SpikeStuff/all_data.mat` was checked for small metadata fields. It contains a generic `meaplate1` with all six wells and 139 units, each reporting 299.75 seconds and 12,500 Hz. Its headers are empty and it provides no DIV140 label, biological identities, source raw filename, or unique physical plate identifier. It cannot currently be identified as the notebook's DIV140 source. Other accessible MAT files in the checked old script directories are channel maps; `MannyAxionMEAScripts_v1_2` could not be inspected because access was denied.

## What this establishes and what remains unresolved

- The user's recalled cortical–cortical versus cortical–MGE comparison is documented.
- Comparing A1–A3 with B1–B3 within the DIV140 dataset supports a shared six-well plate as the working reconstruction. The physical plate identifier remains unavailable. Biological row identities are strongly inferred from the analysis trail above.
- The five inventoried March–April 2024 raw files are D212–D235. Their generic `fusion` labels do not resolve composition or connect them to the DIV140 comparison.
- The historical DIV140 path is a lead to a processed spike-analysis file. Its mention does not establish that an accessible raw recording exists or that LFP was acquired. Neither the acquisition date nor LFP suitability of DIV140 has been confirmed.

Preserve the exact raw well tags. Keep the DIV140 analysis-based composition assignment in its own fields with its supporting evidence; it is not an embedded Axion label. CV/MW abbreviations remain unresolved. All previously saved 2024 and 2026 recording/well inventories are retained.
