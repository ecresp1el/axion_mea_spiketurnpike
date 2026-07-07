#!/usr/bin/env bash
# Prepare AIND SpikeInterface input files for one exported Axion well.
#
# Submit from repo root:
#   SPIKEINTERFACE_CONFIG=/path/to/prepare_spikeinterface.env sbatch slurm/prepare_aind_spikeinterface_well.sbatch

#SBATCH --job-name=axion-aind-si-prep
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-aind-si-prep-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-aind-si-prep-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
source "${PROJECT_CONFIG}"

SPIKEINTERFACE_CONFIG="${SPIKEINTERFACE_CONFIG:-}"
if [[ -n "${SPIKEINTERFACE_CONFIG}" ]]; then
  source "${SPIKEINTERFACE_CONFIG}"
fi

RECORDING_STEM="${RECORDING_STEM:-}"
WELL="${WELL:-}"
BINARY_FILE="${BINARY_FILE:-}"
CHANNEL_MAPPING_CSV="${CHANNEL_MAPPING_CSV:-}"
BINARY_EXPORT_MANIFEST="${BINARY_EXPORT_MANIFEST:-}"
SPIKEINTERFACE_OUTPUT_DIR="${SPIKEINTERFACE_OUTPUT_DIR:-${AIND_JOBS_ROOT}/${RECORDING_STEM}/${WELL}/spikeinterface}"
PARAMS_TEMPLATE="${PARAMS_TEMPLATE:-${AIND_PARAMS_FILE}}"
FS="${FS:-12500}"
DTYPE="${DTYPE:-int16}"
N_CHAN_BIN="${N_CHAN_BIN:-16}"
GAIN_TO_UV="${GAIN_TO_UV:-}"
OFFSET_TO_UV="${OFFSET_TO_UV:-0}"
IS_FILTERED="${IS_FILTERED:-true}"

if [[ -z "${RECORDING_STEM}" || -z "${WELL}" ]]; then
  echo "ERROR: set RECORDING_STEM and WELL." >&2
  exit 2
fi
for required_file in "${BINARY_FILE}" "${CHANNEL_MAPPING_CSV}" "${BINARY_EXPORT_MANIFEST}"; do
  if [[ -z "${required_file}" || ! -f "${required_file}" ]]; then
    echo "ERROR: missing required file for SpikeInterface prep: ${required_file}" >&2
    exit 2
  fi
done

mkdir -p "${SPIKEINTERFACE_OUTPUT_DIR}" "${AIND_LOG_ROOT}" "${AIND_JOBS_ROOT}"
exec > >(tee -a "${SPIKEINTERFACE_OUTPUT_DIR}/prepare_aind_spikeinterface_${SLURM_JOB_ID:-manual}.log") 2>&1

echo "AIND SpikeInterface prep started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "RECORDING_STEM=${RECORDING_STEM}"
echo "WELL=${WELL}"
echo "BINARY_FILE=${BINARY_FILE}"
echo "CHANNEL_MAPPING_CSV=${CHANNEL_MAPPING_CSV}"
echo "BINARY_EXPORT_MANIFEST=${BINARY_EXPORT_MANIFEST}"
echo "SPIKEINTERFACE_OUTPUT_DIR=${SPIKEINTERFACE_OUTPUT_DIR}"
echo "PARAMS_TEMPLATE=${PARAMS_TEMPLATE}"
echo "IS_FILTERED=${IS_FILTERED}"

REPRO_DIR="${SPIKEINTERFACE_OUTPUT_DIR}/repro"
mkdir -p "${REPRO_DIR}"
{
  echo "#!/usr/bin/env bash"
  echo "set -euo pipefail"
  echo "cd ${REPO_ROOT@Q}"
  printf 'PROJECT_CONFIG=%q SPIKEINTERFACE_CONFIG=%q sbatch %q\n' \
    "${PROJECT_CONFIG}" "${SPIKEINTERFACE_CONFIG}" "${REPO_ROOT}/slurm/prepare_aind_spikeinterface_well.sbatch"
} > "${REPRO_DIR}/submit_command.sh"
chmod +x "${REPRO_DIR}/submit_command.sh"
if [[ -f "${PROJECT_CONFIG}" ]]; then
  cp "${PROJECT_CONFIG}" "${REPRO_DIR}/project_config.env"
fi
if [[ -n "${SPIKEINTERFACE_CONFIG}" && -f "${SPIKEINTERFACE_CONFIG}" ]]; then
  cp "${SPIKEINTERFACE_CONFIG}" "${REPRO_DIR}/prepare_spikeinterface.env"
fi
if [[ -f "$0" ]]; then
  cp "$0" "${REPRO_DIR}/submitted_job.sbatch"
fi

args=(
  --recording-stem "${RECORDING_STEM}"
  --well "${WELL}"
  --binary-file "${BINARY_FILE}"
  --channel-mapping "${CHANNEL_MAPPING_CSV}"
  --export-manifest "${BINARY_EXPORT_MANIFEST}"
  --output-dir "${SPIKEINTERFACE_OUTPUT_DIR}"
  --params-template "${PARAMS_TEMPLATE}"
  --fs "${FS}"
  --dtype "${DTYPE}"
  --num-channels "${N_CHAN_BIN}"
  --offset-to-uV "${OFFSET_TO_UV}"
)
if [[ -n "${GAIN_TO_UV}" ]]; then
  args+=(--gain-to-uV "${GAIN_TO_UV}")
fi
if [[ "${IS_FILTERED,,}" == "true" || "${IS_FILTERED}" == "1" || "${IS_FILTERED,,}" == "yes" ]]; then
  args+=(--is-filtered)
fi

bash "${REPO_ROOT}/scripts/prepare_aind_spikeinterface_well.sh" "${args[@]}"

submit_command="${SPIKEINTERFACE_OUTPUT_DIR}/submit_aind_spikeinterface_command.sh"
{
  echo "#!/usr/bin/env bash"
  echo "set -euo pipefail"
  echo "cd ${REPO_ROOT@Q}"
  printf 'PROJECT_CONFIG=%q AIND_CONFIG=%q sbatch %q\n' \
    "${PROJECT_CONFIG}" "${SPIKEINTERFACE_OUTPUT_DIR}/run_aind_spikeinterface.env" "${REPO_ROOT}/slurm/run_aind_nwb_well.sbatch"
} > "${submit_command}"
chmod +x "${submit_command}"

echo "Wrote AIND submit command: ${submit_command}"
echo "AIND SpikeInterface prep finished: $(date)"
find "${SPIKEINTERFACE_OUTPUT_DIR}" -maxdepth 2 -type f | sort
