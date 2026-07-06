#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"
source "${PROJECT_CONFIG}"

module load "${KEMPNER_SINGULARITY_MODULE}"
export SINGULARITY_CACHEDIR="${SINGULARITY_CACHEDIR:-${KEMPNER_SINGULARITY_CACHE_DIR}}"
export SINGULARITY_TMPDIR="${SINGULARITY_TMPDIR:-${KEMPNER_SINGULARITY_TMPDIR}}"

container_list="${KEMPNER_REPO_ROOT}/environment/task_container_list.txt"
if [[ ! -f "${container_list}" ]]; then
  echo "ERROR: missing Kempner container list: ${container_list}" >&2
  exit 2
fi

KEMPNER_SORTER="${KEMPNER_SORTER:-kilosort4}"
KEMPNER_PULL_ALL_CONTAINERS="${KEMPNER_PULL_ALL_CONTAINERS:-false}"

required_patterns=(
  "aind-ephys-pipeline-base:"
  "aind-ephys-pipeline-nwb:"
  "aind-ephys-unit-classifier:"
)
case "${KEMPNER_SORTER}" in
  kilosort4)
    required_patterns+=("aind-ephys-spikesort-kilosort4:")
    ;;
  kilosort25)
    required_patterns+=("aind-ephys-spikesort-kilosort25:")
    ;;
  spykingcircus2)
    required_patterns+=("aind-ephys-spikesort-spykingcircus2:")
    ;;
  *)
    echo "ERROR: unknown KEMPNER_SORTER=${KEMPNER_SORTER}" >&2
    exit 2
    ;;
esac

should_pull() {
  local image="$1"
  if [[ "${KEMPNER_PULL_ALL_CONTAINERS}" == "true" ]]; then
    return 0
  fi
  local pattern
  for pattern in "${required_patterns[@]}"; do
    if [[ "${image}" == *"/${pattern}"* ]]; then
      return 0
    fi
  done
  return 1
}

mkdir -p "${KEMPNER_CONTAINER_DIR}" "${SINGULARITY_CACHEDIR}" "${SINGULARITY_TMPDIR}"
while IFS= read -r image; do
  [[ -z "${image}" ]] && continue
  if ! should_pull "${image}"; then
    echo "Skipping ${image}"
    continue
  fi
  echo "Pulling ${image}"
  singularity pull --dir "${KEMPNER_CONTAINER_DIR}" "docker://${image}"
done < "${container_list}"

find "${KEMPNER_CONTAINER_DIR}" -maxdepth 1 -type f -name '*.sif' | sort
