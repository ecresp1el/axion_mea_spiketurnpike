#!/usr/bin/env bash
# Supervise one recording-level Axion AIND batch and submit sparse-well fallback.
#
# Submit from repo root:
#   RECORDING_STEM=<recording> sbatch slurm/run_aind_recording_supervisor.sbatch

#SBATCH --job-name=axion-aind-supervisor
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=10:00:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/aind/axion-aind-supervisor-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/aind/axion-aind-supervisor-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
source "${PROJECT_CONFIG}"

RECORDING_STEM="${RECORDING_STEM:-}"
if [[ -z "${RECORDING_STEM}" ]]; then
  echo "ERROR: set RECORDING_STEM." >&2
  exit 2
fi

POLL_SECONDS="${POLL_SECONDS:-120}"
TIMEOUT_HOURS="${TIMEOUT_HOURS:-8}"
SUPERVISOR_OUTPUT_DIR="${SUPERVISOR_OUTPUT_DIR:-${PROJECT_ROOT}/jobs/aind_recording_supervisors/${RECORDING_STEM}}"
FALLBACK_LABEL="${FALLBACK_LABEL:-low_activity_ks4_nt2_npcs2}"
FALLBACK_N_TEMPLATES="${FALLBACK_N_TEMPLATES:-2}"
FALLBACK_NEAREST_TEMPLATES="${FALLBACK_NEAREST_TEMPLATES:-2}"
FALLBACK_N_PCS="${FALLBACK_N_PCS:-2}"

mkdir -p "${AIND_LOG_ROOT}" "${SUPERVISOR_OUTPUT_DIR}"

source "${CONDA_BASE}/etc/profile.d/conda.sh"
set +u
conda activate "${CONDA_ENV}"
set -u

exec > >(tee -a "${SUPERVISOR_OUTPUT_DIR}/slurm_supervisor_${SLURM_JOB_ID:-manual}.log") 2>&1

echo "Axion AIND recording supervisor started: $(date)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "RECORDING_STEM=${RECORDING_STEM}"
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "SUPERVISOR_OUTPUT_DIR=${SUPERVISOR_OUTPUT_DIR}"
echo "POLL_SECONDS=${POLL_SECONDS}"
echo "TIMEOUT_HOURS=${TIMEOUT_HOURS}"
echo "FALLBACK_LABEL=${FALLBACK_LABEL}"

python "${REPO_ROOT}/scripts/run_aind_recording_supervisor.py" \
  --recording-stem "${RECORDING_STEM}" \
  --project-root "${PROJECT_ROOT}" \
  --project-config "${PROJECT_CONFIG}" \
  --output-dir "${SUPERVISOR_OUTPUT_DIR}" \
  --poll-seconds "${POLL_SECONDS}" \
  --timeout-hours "${TIMEOUT_HOURS}" \
  --fallback-label "${FALLBACK_LABEL}" \
  --fallback-n-templates "${FALLBACK_N_TEMPLATES}" \
  --fallback-nearest-templates "${FALLBACK_NEAREST_TEMPLATES}" \
  --fallback-n-pcs "${FALLBACK_N_PCS}"

echo "Axion AIND recording supervisor finished: $(date)"
