#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"
source "${PROJECT_CONFIG}"

KEMPNER_CONFIG="${1:-${KEMPNER_CONFIG:-}}"
if [[ -z "${KEMPNER_CONFIG}" ]]; then
  echo "Usage: scripts/submit_kempner_nwb_well_job.sh /path/to/kempner_well.env" >&2
  exit 2
fi

mkdir -p "${KEMPNER_JOBS_ROOT}" "${KEMPNER_LOG_ROOT}"
job_name="$(basename "${KEMPNER_CONFIG}" .env)"
job_file="${KEMPNER_JOBS_ROOT}/run_kempner_nwb_well.${job_name}.sbatch"
cp "${REPO_ROOT}/slurm/run_kempner_nwb_well.sbatch" "${job_file}"

echo "Submitting ${job_file}"
echo "Using KEMPNER_CONFIG=${KEMPNER_CONFIG}"
KEMPNER_CONFIG="${KEMPNER_CONFIG}" PROJECT_CONFIG="${PROJECT_CONFIG}" sbatch "${job_file}"
