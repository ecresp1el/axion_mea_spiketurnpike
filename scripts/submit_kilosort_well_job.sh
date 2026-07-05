#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"
source "${PROJECT_CONFIG}"

SAMPLE_CONFIG="${1:-${SAMPLE_CONFIG:-}}"
if [[ -z "${SAMPLE_CONFIG}" ]]; then
  echo "Usage: scripts/submit_kilosort_well_job.sh /path/to/sample.env" >&2
  exit 2
fi

mkdir -p "${KILOSORT_JOBS_ROOT}" "${KILOSORT_LOG_ROOT}"
job_file="${KILOSORT_JOBS_ROOT}/run_kilosort_well.$(basename "${SAMPLE_CONFIG}" .env).sbatch"
cp "${REPO_ROOT}/slurm/run_kilosort_well.sbatch" "${job_file}"

echo "Submitting ${job_file}"
echo "Using SAMPLE_CONFIG=${SAMPLE_CONFIG}"
SAMPLE_CONFIG="${SAMPLE_CONFIG}" PROJECT_CONFIG="${PROJECT_CONFIG}" sbatch "${job_file}"
