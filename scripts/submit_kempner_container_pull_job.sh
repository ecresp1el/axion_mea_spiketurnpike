#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"
source "${PROJECT_CONFIG}"

mkdir -p "${KEMPNER_JOBS_ROOT}" "${KEMPNER_LOG_ROOT}"
job_file="${KEMPNER_JOBS_ROOT}/pull_kempner_containers.sbatch"
cp "${REPO_ROOT}/slurm/pull_kempner_containers.sbatch" "${job_file}"

echo "Submitting ${job_file}"
PROJECT_CONFIG="${PROJECT_CONFIG}" sbatch "${job_file}"
