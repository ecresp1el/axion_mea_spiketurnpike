#!/usr/bin/env bash
#SBATCH --job-name=top4_fsrs_qc
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=00:30:00

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike}"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"
OUTPUT_DIR="${OUTPUT_DIR:-/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/FINAL FIG 2/Population Panels/ventral_MGE_putative_FS_RS_TTR90_PCHIP_040_056_FINAL/reformatted_histogram_best_units_activity_grid_20260714/top4_FS_RS_representative_candidates_20260714}"

source "${PROJECT_CONFIG}"
set +u
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
set -u

mkdir -p "${OUTPUT_DIR}"
exec > >(tee -a "${OUTPUT_DIR}/top4_FS_RS_candidates.${SLURM_JOB_ID}.out") \
  2> >(tee -a "${OUTPUT_DIR}/top4_FS_RS_candidates.${SLURM_JOB_ID}.err" >&2)

echo "SLURM_JOB_ID=${SLURM_JOB_ID}"
echo "OUTPUT_DIR=${OUTPUT_DIR}"

python "${REPO_ROOT}/scripts/build_top_fs_rs_representative_selection_gallery.py" \
  --output-dir "${OUTPUT_DIR}"
