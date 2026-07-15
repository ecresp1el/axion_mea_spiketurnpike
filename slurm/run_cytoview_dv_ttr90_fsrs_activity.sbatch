#!/usr/bin/env bash
#SBATCH --job-name=dv_ttr90_activity
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
OUTPUT_DIR="${OUTPUT_DIR:?OUTPUT_DIR must be set}"

source "${PROJECT_CONFIG}"
set +u
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
set -u

mkdir -p "${OUTPUT_DIR}"
exec > >(tee -a "${OUTPUT_DIR}/dv_ttr90_activity.${SLURM_JOB_ID}.out") \
  2> >(tee -a "${OUTPUT_DIR}/dv_ttr90_activity.${SLURM_JOB_ID}.err" >&2)

echo "SLURM_JOB_ID=${SLURM_JOB_ID}"
echo "OUTPUT_DIR=${OUTPUT_DIR}"

python "${REPO_ROOT}/scripts/analyze_cytoview_dv_ttr90_fsrs_activity.py" \
  --output-dir "${OUTPUT_DIR}"
