#!/usr/bin/env bash
set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
if [[ -f "${PROJECT_CONFIG}" ]]; then
  source "${PROJECT_CONFIG}"
fi

PROJECT_ROOT="${PROJECT_ROOT:-/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder}"

mkdir -p \
  "${PROJECT_ROOT}/data/raw" \
  "${PROJECT_ROOT}/data/interim/kilosort_binary" \
  "${PROJECT_ROOT}/metadata" \
  "${PROJECT_ROOT}/results/kilosort" \
  "${PROJECT_ROOT}/results/aind" \
  "${PROJECT_ROOT}/logs" \
  "${PROJECT_ROOT}/logs/aind" \
  "${PROJECT_ROOT}/jobs" \
  "${PROJECT_ROOT}/jobs/aind" \
  "${PROJECT_ROOT}/scratch" \
  "${PROJECT_ROOT}/scratch/aind_nextflow" \
  "${PROJECT_ROOT}/scratch/aind_nextflow_install" \
  "${PROJECT_ROOT}/aind_capsule_repos" \
  "${PROJECT_ROOT}/containers/aind_ephys" \
  "${PROJECT_ROOT}/tools" \
  "${PROJECT_ROOT}/tools/aind_python_shim" \
  "${PROJECT_ROOT}/handoffs"

echo "Project folder ready: ${PROJECT_ROOT}"
find "${PROJECT_ROOT}" -maxdepth 2 -type d | sort
