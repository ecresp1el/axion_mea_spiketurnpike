#!/usr/bin/env bash
# Prepare or run Kilosort4 for one Axion MEA well on Great Lakes.
#
# Submit from repo root:
#   SAMPLE_CONFIG=config/example_kilosort_well.env sbatch slurm/run_kilosort_well.sbatch
#
# Set RUN_KILOSORT=true only after the binary/probe readiness manifest is valid.

#SBATCH --job-name=axion-ks-well
#SBATCH --account=parent0
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-ks-well-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-ks-well-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
if [[ -f "${PROJECT_CONFIG}" ]]; then
  source "${PROJECT_CONFIG}"
fi

SAMPLE_CONFIG="${SAMPLE_CONFIG:-}"
if [[ -n "${SAMPLE_CONFIG}" ]]; then
  source "${SAMPLE_CONFIG}"
fi

BINARY_FILE="${BINARY_FILE:-}"
WELL="${WELL:-}"
PLATE_MAP="${PLATE_MAP:-${PLATE_MAP_48_OPTO}}"
ELECTRODE_GEOMETRY="${ELECTRODE_GEOMETRY:-${ELECTRODE_GEOMETRY_4X4}}"
OUTPUT_DIR="${OUTPUT_DIR:-${KILOSORT_RESULTS_ROOT}/${RECORDING_STEM:-unknown_recording}/${WELL:-unknown_well}}"
RECORDING_STEM="${RECORDING_STEM:-}"
FS="${FS:-12500}"
DTYPE="${DTYPE:-int16}"
N_CHAN_BIN="${N_CHAN_BIN:-16}"
DO_CAR="${DO_CAR:-true}"
INVERT_SIGN="${INVERT_SIGN:-false}"
RUN_KILOSORT="${RUN_KILOSORT:-false}"
CLEAR_CACHE="${CLEAR_CACHE:-false}"
SAVE_PREPROCESSED_COPY="${SAVE_PREPROCESSED_COPY:-false}"
TORCH_THREAD_LIM="${TORCH_THREAD_LIM:-}"

if [[ -z "${BINARY_FILE}" ]]; then
  echo "ERROR: set BINARY_FILE to a per-well continuous binary trace." >&2
  exit 2
fi
if [[ -z "${WELL}" ]]; then
  echo "ERROR: set WELL, for example WELL=A1." >&2
  exit 2
fi

mkdir -p "${OUTPUT_DIR}/logs" "${KILOSORT_LOG_ROOT}" "${KILOSORT_JOBS_ROOT}" "${KILOSORT_SCRATCH_ROOT}"
export TMPDIR="${TMPDIR:-${KILOSORT_SCRATCH_ROOT}/tmp_${SLURM_JOB_ID:-manual}}"
mkdir -p "${TMPDIR}"
exec > >(tee -a "${OUTPUT_DIR}/logs/run_kilosort_well_${SLURM_JOB_ID:-manual}.log") 2>&1

echo "Axion Kilosort well job started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "REPO_ROOT=${REPO_ROOT}"
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "BINARY_FILE=${BINARY_FILE}"
echo "OUTPUT_DIR=${OUTPUT_DIR}"
echo "RECORDING_STEM=${RECORDING_STEM}"
echo "WELL=${WELL}"
echo "PLATE_MAP=${PLATE_MAP}"
echo "ELECTRODE_GEOMETRY=${ELECTRODE_GEOMETRY}"
echo "RUN_KILOSORT=${RUN_KILOSORT}"

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi
else
  echo "WARNING: nvidia-smi is not on PATH."
fi

source "${CONDA_BASE}/etc/profile.d/conda.sh"
set +u
conda activate "${CONDA_ENV}"
set -u
python --version
which python
python "${REPO_ROOT}/scripts/check_kilosort_env.py"

args=(
  --binary-file "${BINARY_FILE}"
  --output-dir "${OUTPUT_DIR}"
  --well "${WELL}"
  --plate-map "${PLATE_MAP}"
  --electrode-geometry "${ELECTRODE_GEOMETRY}"
  --fs "${FS}"
  --dtype "${DTYPE}"
  --n-chan-bin "${N_CHAN_BIN}"
  --run-from-env "${RUN_KILOSORT}"
)

if [[ -n "${RECORDING_STEM}" ]]; then
  args+=(--recording-stem "${RECORDING_STEM}")
fi
if [[ "${DO_CAR}" != "true" ]]; then
  args+=(--no-do-car)
fi
if [[ "${INVERT_SIGN}" == "true" ]]; then
  args+=(--invert-sign)
fi
if [[ "${CLEAR_CACHE}" == "true" ]]; then
  args+=(--clear-cache)
fi
if [[ "${SAVE_PREPROCESSED_COPY}" == "true" ]]; then
  args+=(--save-preprocessed-copy)
fi
if [[ -n "${TORCH_THREAD_LIM}" ]]; then
  args+=(--torch-thread-lim "${TORCH_THREAD_LIM}")
fi

python "${REPO_ROOT}/run_axion_kilosort.py" "${args[@]}"

echo "Axion Kilosort well job finished: $(date)"
find "${OUTPUT_DIR}" -maxdepth 3 -type f | sort
