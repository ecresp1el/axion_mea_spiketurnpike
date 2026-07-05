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
  "${PROJECT_ROOT}/logs" \
  "${PROJECT_ROOT}/jobs" \
  "${PROJECT_ROOT}/scratch" \
  "${PROJECT_ROOT}/handoffs"

echo "Project folder ready: ${PROJECT_ROOT}"
find "${PROJECT_ROOT}" -maxdepth 2 -type d | sort
