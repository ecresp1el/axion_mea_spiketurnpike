#!/usr/bin/env bash
#SBATCH --job-name=ttr90_classifier
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=12G
#SBATCH --time=00:30:00

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike}"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"
AUDIT_DIR="${AUDIT_DIR:?AUDIT_DIR must be set}"
OUTPUT_DIR="${OUTPUT_DIR:?OUTPUT_DIR must be set}"

source "${PROJECT_CONFIG}"
set +u
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
set -u

mkdir -p "${OUTPUT_DIR}"
exec > >(tee -a "${OUTPUT_DIR}/ttr90_classifier.${SLURM_JOB_ID}.out") 2> >(tee -a "${OUTPUT_DIR}/ttr90_classifier.${SLURM_JOB_ID}.err" >&2)

echo "SLURM_JOB_ID=${SLURM_JOB_ID}"
echo "AUDIT_DIR=${AUDIT_DIR}"
echo "OUTPUT_DIR=${OUTPUT_DIR}"

python "${REPO_ROOT}/scripts/classify_lumos_ventral_ttr90.py" \
  --audit-dir "${AUDIT_DIR}" \
  --output-dir "${OUTPUT_DIR}"
