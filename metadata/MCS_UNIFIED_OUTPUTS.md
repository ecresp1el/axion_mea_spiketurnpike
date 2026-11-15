# Unified current outputs

The authoritative current folder is `/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/unified_unit_analysis/`. Open its `README.md` for every figure, plotted data, generating functions, methods and regeneration command. `ALL_FIGURES.pdf` combines the five requested figures plus the 2D PSAM recording detail. `FUNCTION_INDEX.md` indexes every bundled function. `OUTPUT_MANIFEST.json` inventories all files with hashes.

All six figures were regenerated with Slurm job 66155453. Locked 215-feature model/metrics hashes and cumulative probability arrays were verified unchanged. Current centroids use solid circles with dark group means on top. Historical scattered output directories and the former `final_figure_pair` bundle are superseded; raw inputs remain in place. Future unified generation writes within the canonical scratch folder.

From your Mac, transfer this folder directly:

```bash
rsync -avh --progress elcrespo@greatlakes.arc-ts.umich.edu:/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/unified_unit_analysis/ /Users/ecrespo/Desktop/chemogenetics_tech_resources/
```

The trailing slashes copy the folder contents into the exact Desktop destination. This command does not delete older local files.
