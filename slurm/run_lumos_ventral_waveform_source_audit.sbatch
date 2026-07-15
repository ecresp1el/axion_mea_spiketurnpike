#!/usr/bin/env bash
#SBATCH --job-name=waveform_source_audit
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --time=02:00:00

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike}"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"
CLASSIFICATION_DIR="${CLASSIFICATION_DIR:?CLASSIFICATION_DIR must be set}"
OUTPUT_DIR="${OUTPUT_DIR:?OUTPUT_DIR must be set}"
MAX_UNITS="${MAX_UNITS:-}"

source "${PROJECT_CONFIG}"
set +u
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
set -u

mkdir -p "${OUTPUT_DIR}"
exec > >(tee -a "${OUTPUT_DIR}/waveform_source_audit.${SLURM_JOB_ID}.out") 2> >(tee -a "${OUTPUT_DIR}/waveform_source_audit.${SLURM_JOB_ID}.err" >&2)

echo "SLURM_JOB_ID=${SLURM_JOB_ID}"
echo "CLASSIFICATION_DIR=${CLASSIFICATION_DIR}"
echo "OUTPUT_DIR=${OUTPUT_DIR}"
echo "MAX_UNITS=${MAX_UNITS:-all}"

command=(
  python "${REPO_ROOT}/scripts/audit_lumos_ventral_waveform_sources.py"
  --classification-dir "${CLASSIFICATION_DIR}"
  --output-dir "${OUTPUT_DIR}"
)
if [[ -n "${MAX_UNITS}" ]]; then
  command+=(--max-units "${MAX_UNITS}")
fi
"${command[@]}"
