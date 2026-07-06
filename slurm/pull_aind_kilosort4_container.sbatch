#!/usr/bin/env bash
# Pull the AIND Kilosort4 Singularity image with visible logs.
#
# Usage:
#   PROJECT_CONFIG=config/greatlakes_project.env sbatch slurm/pull_aind_kilosort4_container.sbatch

#SBATCH --job-name=aind-ks4-img
#SBATCH --partition=standard
#SBATCH --account=parent0
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/aind/aind-ks4-img-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/aind/aind-ks4-img-%j.err

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike}"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"

if [[ ! -f "${PROJECT_CONFIG}" ]]; then
  echo "Missing PROJECT_CONFIG: ${PROJECT_CONFIG}" >&2
  exit 2
fi

source "${PROJECT_CONFIG}"

IMAGE_URI="${AIND_KS4_IMAGE_URI:-docker://ghcr.io/allenneuraldynamics/aind-ephys-spikesort-kilosort4:si-0.104.8}"
IMAGE_NAME="${AIND_KS4_IMAGE_NAME:-ghcr.io-allenneuraldynamics-aind-ephys-spikesort-kilosort4-si-0.104.8.img}"
IMAGE_DIR="${AIND_CONTAINER_DIR:-${PROJECT_ROOT}/containers/aind_ephys}"
IMAGE_PATH="${IMAGE_DIR}/${IMAGE_NAME}"
LOCK_PATH="${IMAGE_DIR}/.${IMAGE_NAME}.lock"
PULLING_GLOB="${IMAGE_DIR}/${IMAGE_NAME}.pulling.*"

mkdir -p "${IMAGE_DIR}" "${AIND_SINGULARITY_CACHEDIR:-${PROJECT_ROOT}/scratch/aind_singularity_cache}"

module load singularity

export SINGULARITY_CACHEDIR="${AIND_SINGULARITY_CACHEDIR:-${PROJECT_ROOT}/scratch/aind_singularity_cache}"
export APPTAINER_CACHEDIR="${SINGULARITY_CACHEDIR}"
if [[ -n "${AIND_SINGULARITY_TMPDIR:-}" ]]; then
  export SINGULARITY_TMPDIR="${AIND_SINGULARITY_TMPDIR}"
else
  export SINGULARITY_TMPDIR="/tmp/${USER}/aind_singularity_tmp_${SLURM_JOB_ID:-manual}"
fi
export APPTAINER_TMPDIR="${SINGULARITY_TMPDIR}"
mkdir -p "${SINGULARITY_CACHEDIR}" "${SINGULARITY_TMPDIR}"
trap 'rm -rf "${SINGULARITY_TMPDIR}"' EXIT

echo "AIND Kilosort4 image pull started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-manual}"
echo "IMAGE_URI=${IMAGE_URI}"
echo "IMAGE_PATH=${IMAGE_PATH}"
echo "SINGULARITY_CACHEDIR=${SINGULARITY_CACHEDIR}"
echo "SINGULARITY_TMPDIR=${SINGULARITY_TMPDIR}"
df -h "${SINGULARITY_TMPDIR}" "${IMAGE_DIR}" || true
echo "singularity version: $(singularity --version)"

if [[ -f "${IMAGE_PATH}" ]]; then
  echo "Image already exists; not pulling again."
  ls -lh "${IMAGE_PATH}"
  exit 0
fi

if [[ -f "${LOCK_PATH}" ]]; then
  if lsof "${LOCK_PATH}" >/dev/null 2>&1; then
    echo "Lock is active; refusing to remove it: ${LOCK_PATH}" >&2
    lsof "${LOCK_PATH}" >&2 || true
    exit 3
  fi
  echo "Removing stale lock: ${LOCK_PATH}"
  rm -f "${LOCK_PATH}"
fi

shopt -s nullglob
pulling_files=( ${PULLING_GLOB} )
if (( ${#pulling_files[@]} )); then
  echo "Removing stale pulling files:"
  printf '  %s\n' "${pulling_files[@]}"
  rm -f "${pulling_files[@]}"
fi
shopt -u nullglob

echo "Running visible pull:"
cd "${IMAGE_DIR}"
set -x
singularity pull --force --name "${IMAGE_NAME}" "${IMAGE_URI}"
set +x

echo "Pull completed: $(date)"
ls -lh "${IMAGE_PATH}"
