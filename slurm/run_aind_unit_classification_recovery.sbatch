#!/usr/bin/env bash
# Recover UnitRefine/Bombcell labels for one completed AIND well.

#SBATCH --job-name=axion-unit-classify
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=08:00:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/aind/axion-unit-classify-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/aind/axion-unit-classify-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
source "${PROJECT_CONFIG}"

RECORDING_STEM="${RECORDING_STEM:?set RECORDING_STEM}"
WELL="${WELL:?set WELL}"
SOURCE_RESULTS_DIR="${SOURCE_RESULTS_DIR:?set SOURCE_RESULTS_DIR}"
RECOVERY_OUTPUT_DIR="${RECOVERY_OUTPUT_DIR:?set RECOVERY_OUTPUT_DIR}"
RECOVERY_PARAMS_JSON="${RECOVERY_PARAMS_JSON:?set RECOVERY_PARAMS_JSON}"
RECOVERY_RECORDING_NAME="${RECOVERY_RECORDING_NAME:-block0_None_recording1}"
RECOVERY_N_JOBS="${RECOVERY_N_JOBS:-${SLURM_CPUS_PER_TASK:-8}}"

module load "${AIND_SINGULARITY_MODULE}"

base_image="${AIND_CONTAINER_DIR}/ghcr.io-allenneuraldynamics-aind-ephys-pipeline-base-si-0.104.8.img"
if [[ ! -f "${base_image}" ]]; then
  echo "ERROR: missing AIND base image: ${base_image}" >&2
  exit 2
fi

mkdir -p \
  "${AIND_LOG_ROOT}" \
  "${AIND_CONTAINER_HOME}" \
  "${AIND_XDG_CACHE_HOME}" \
  "${AIND_XDG_CACHE_HOME}/matplotlib" \
  "${AIND_SINGULARITY_CACHE_DIR}" \
  "${AIND_SINGULARITY_TMPDIR}" \
  "$(dirname "${RECOVERY_OUTPUT_DIR}")"

export SINGULARITY_CACHEDIR="${AIND_SINGULARITY_CACHE_DIR}"
export SINGULARITY_TMPDIR="${AIND_SINGULARITY_TMPDIR}"
export APPTAINER_CACHEDIR="${AIND_SINGULARITY_CACHE_DIR}"
export APPTAINER_TMPDIR="${AIND_SINGULARITY_TMPDIR}"
export HOME="${AIND_CONTAINER_HOME}"
export XDG_CACHE_HOME="${AIND_XDG_CACHE_HOME}"
export MPLCONFIGDIR="${AIND_XDG_CACHE_HOME}/matplotlib"
export N_JOBS_EXT="${RECOVERY_N_JOBS}"

echo "Axion unit classification recovery started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "RECORDING_STEM=${RECORDING_STEM}"
echo "WELL=${WELL}"
echo "SOURCE_RESULTS_DIR=${SOURCE_RESULTS_DIR}"
echo "RECOVERY_OUTPUT_DIR=${RECOVERY_OUTPUT_DIR}"
echo "RECOVERY_PARAMS_JSON=${RECOVERY_PARAMS_JSON}"
echo "RECOVERY_RECORDING_NAME=${RECOVERY_RECORDING_NAME}"
echo "RECOVERY_N_JOBS=${RECOVERY_N_JOBS}"

singularity exec --cleanenv \
  -B /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder:/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder \
  -B /home/elcrespo/Desktop/githubprojects:/home/elcrespo/Desktop/githubprojects \
  -B "${HOME}:${HOME}" \
  -B "${XDG_CACHE_HOME}:${XDG_CACHE_HOME}" \
  --env HOME="${HOME}" \
  --env XDG_CACHE_HOME="${XDG_CACHE_HOME}" \
  --env MPLCONFIGDIR="${MPLCONFIGDIR}" \
  --env N_JOBS_EXT="${N_JOBS_EXT}" \
  "${base_image}" \
  /opt/conda/bin/python "${REPO_ROOT}/scripts/run_aind_unit_classification_recovery.py" \
    --source-results-dir "${SOURCE_RESULTS_DIR}" \
    --output-dir "${RECOVERY_OUTPUT_DIR}" \
    --params-json "${RECOVERY_PARAMS_JSON}" \
    --recording "${RECORDING_STEM}" \
    --well "${WELL}" \
    --recording-name "${RECOVERY_RECORDING_NAME}" \
    --n-jobs "${RECOVERY_N_JOBS}"

echo "Axion unit classification recovery finished: $(date)"
