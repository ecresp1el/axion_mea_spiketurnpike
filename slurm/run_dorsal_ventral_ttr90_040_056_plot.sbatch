#!/usr/bin/env bash
#SBATCH --job-name=dv_ttr90_plot
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=12G
#SBATCH --time=00:20:00

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike}"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"
VENTRAL_CLASSIFIER_DIR="${VENTRAL_CLASSIFIER_DIR:?VENTRAL_CLASSIFIER_DIR must be set}"
VENTRAL_AUDIT_DIR="${VENTRAL_AUDIT_DIR:?VENTRAL_AUDIT_DIR must be set}"
DORSAL_CLASSIFIER_DIR="${DORSAL_CLASSIFIER_DIR:?DORSAL_CLASSIFIER_DIR must be set}"
DORSAL_AUDIT_DIR="${DORSAL_AUDIT_DIR:?DORSAL_AUDIT_DIR must be set}"
OUTPUT_DIR="${OUTPUT_DIR:?OUTPUT_DIR must be set}"

source "${PROJECT_CONFIG}"
set +u
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
set -u

mkdir -p "${OUTPUT_DIR}"
exec > >(tee -a "${OUTPUT_DIR}/dv_ttr90_plot.${SLURM_JOB_ID}.out") \
  2> >(tee -a "${OUTPUT_DIR}/dv_ttr90_plot.${SLURM_JOB_ID}.err" >&2)

python "${REPO_ROOT}/scripts/plot_dorsal_ventral_ttr90_040_056.py" \
  --ventral-classifier-dir "${VENTRAL_CLASSIFIER_DIR}" \
  --ventral-audit-dir "${VENTRAL_AUDIT_DIR}" \
  --dorsal-classifier-dir "${DORSAL_CLASSIFIER_DIR}" \
  --dorsal-audit-dir "${DORSAL_AUDIT_DIR}" \
  --output-dir "${OUTPUT_DIR}"
