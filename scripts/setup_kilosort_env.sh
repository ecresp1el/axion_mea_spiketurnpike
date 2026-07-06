#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/envs/kilosort-greatlakes.yml"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"
if [[ -f "${PROJECT_CONFIG}" ]]; then
  source "${PROJECT_CONFIG}"
fi

ENV_NAME="${ENV_NAME:-axion-kilosort}"
PROJECT_ROOT="${PROJECT_ROOT:-/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder}"
ENV_PREFIX="${ENV_PREFIX:-${PROJECT_ROOT}/envs/${ENV_NAME}}"
export CONDA_PKGS_DIRS="${CONDA_PKGS_DIRS:-${PROJECT_ROOT}/conda_pkgs}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-${PROJECT_ROOT}/pip_cache}"
KILOSORT_VERSION="${KILOSORT_VERSION:-4.1.3}"

if ! command -v conda >/dev/null 2>&1; then
  echo "ERROR: conda is not on PATH. Load or initialize conda first." >&2
  exit 1
fi

CONDA_EXE="conda"
if command -v mamba >/dev/null 2>&1; then
  CONDA_EXE="mamba"
fi

mkdir -p "${ENV_PREFIX%/*}" "${CONDA_PKGS_DIRS}" "${PIP_CACHE_DIR}"

if [[ -d "${ENV_PREFIX}/conda-meta" ]]; then
  echo "Updating conda environment prefix: ${ENV_PREFIX}"
  "${CONDA_EXE}" env update -p "${ENV_PREFIX}" -f "${ENV_FILE}" --prune
else
  echo "Creating conda environment prefix: ${ENV_PREFIX}"
  "${CONDA_EXE}" env create -p "${ENV_PREFIX}" -f "${ENV_FILE}"
fi

echo "Installing Kilosort ${KILOSORT_VERSION} with pip inside: ${ENV_PREFIX}"
"${CONDA_EXE}" run -p "${ENV_PREFIX}" python -m pip install "kilosort==${KILOSORT_VERSION}"

echo "Environment ready."
echo "Activate with: conda activate ${ENV_PREFIX}"
echo "Check with: python scripts/check_kilosort_env.py"
