#!/usr/bin/env bash
#SBATCH --job-name=ttr90_unified_figure
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
TTR90_CLASSIFIER_DIR="${TTR90_CLASSIFIER_DIR:?TTR90_CLASSIFIER_DIR must be set}"
TTR90_AUDIT_DIR="${TTR90_AUDIT_DIR:-}"
OUTPUT_STEM="${OUTPUT_STEM:-}"

source "${PROJECT_CONFIG}"
set +u
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
set -u

mkdir -p "${OUTPUT_DIR}"
exec > >(tee -a "${OUTPUT_DIR}/ttr90_unified_figure.${SLURM_JOB_ID}.out") 2> >(tee -a "${OUTPUT_DIR}/ttr90_unified_figure.${SLURM_JOB_ID}.err" >&2)

echo "SLURM_JOB_ID=${SLURM_JOB_ID}"
echo "OUTPUT_DIR=${OUTPUT_DIR}"
echo "TTR90_CLASSIFIER_DIR=${TTR90_CLASSIFIER_DIR}"
echo "TTR90_AUDIT_DIR=${TTR90_AUDIT_DIR:-default}"
echo "OUTPUT_STEM=${OUTPUT_STEM:-default}"

command=(
  python "${REPO_ROOT}/scripts/build_cytoview_unified_rsfs_activity_figure.py"
  --lumos-ventral-mode \
  --ttr90-classifier-dir "${TTR90_CLASSIFIER_DIR}" \
  --output-dir "${OUTPUT_DIR}" \
  --export-formats png,pdf,svg
)
if [[ -n "${TTR90_AUDIT_DIR}" ]]; then
  command+=(--ttr90-audit-dir "${TTR90_AUDIT_DIR}")
fi
if [[ -n "${OUTPUT_STEM}" ]]; then
  command+=(--output-stem "${OUTPUT_STEM}")
fi
"${command[@]}"
