#!/usr/bin/env bash
#SBATCH --job-name=dorsal_ttr90
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --time=04:00:00

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike}"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"
SOURCE_UNIT_METRICS="${SOURCE_UNIT_METRICS:?SOURCE_UNIT_METRICS must be set}"
OUTPUT_DIR="${OUTPUT_DIR:?OUTPUT_DIR must be set}"
EXPECTED_UNIT_COUNT="${EXPECTED_UNIT_COUNT:-74}"

source "${PROJECT_CONFIG}"
set +u
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
set -u

ROSTER_DIR="${OUTPUT_DIR}/roster"
CLASSIFICATION_DIR="${OUTPUT_DIR}/classification_audit"
WAVEFORM_AUDIT_DIR="${OUTPUT_DIR}/waveform_source_audit"
TTR90_DIR="${OUTPUT_DIR}/ttr90_canonical_negative_classifier"
ROSTER_PATH="${ROSTER_DIR}/cytoview_dorsal_unit_roster.csv"

mkdir -p "${OUTPUT_DIR}" "${ROSTER_DIR}" "${CLASSIFICATION_DIR}" "${WAVEFORM_AUDIT_DIR}" "${TTR90_DIR}"
exec > >(tee -a "${OUTPUT_DIR}/dorsal_ttr90_pipeline.${SLURM_JOB_ID}.out") \
  2> >(tee -a "${OUTPUT_DIR}/dorsal_ttr90_pipeline.${SLURM_JOB_ID}.err" >&2)

echo "SLURM_JOB_ID=${SLURM_JOB_ID}"
echo "SOURCE_UNIT_METRICS=${SOURCE_UNIT_METRICS}"
echo "OUTPUT_DIR=${OUTPUT_DIR}"
echo "EXPECTED_UNIT_COUNT=${EXPECTED_UNIT_COUNT}"

python "${REPO_ROOT}/scripts/prepare_cytoview_region_ttr90_roster.py" \
  --source-unit-metrics "${SOURCE_UNIT_METRICS}" \
  --region dorsal \
  --expected-unit-count "${EXPECTED_UNIT_COUNT}" \
  --output-roster "${ROSTER_PATH}"

python "${REPO_ROOT}/scripts/reclassify_lumos_ventral_robust_pchip_waveforms.py" \
  --roster "${ROSTER_PATH}" \
  --output-dir "${CLASSIFICATION_DIR}"

python "${REPO_ROOT}/scripts/audit_lumos_ventral_waveform_sources.py" \
  --classification-dir "${CLASSIFICATION_DIR}" \
  --output-dir "${WAVEFORM_AUDIT_DIR}"

python "${REPO_ROOT}/scripts/classify_lumos_ventral_ttr90.py" \
  --audit-dir "${WAVEFORM_AUDIT_DIR}" \
  --expected-unit-count "${EXPECTED_UNIT_COUNT}" \
  --output-dir "${TTR90_DIR}"
