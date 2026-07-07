#!/usr/bin/env bash
# Diagnostic preflight for one Axion raw file.
#
# Submit from repo root:
#   RAW_FILE=/path/to/file.raw sbatch slurm/preflight_axion_raw_ingestion.sbatch

#SBATCH --job-name=axion-raw-preflight
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=128G
#SBATCH --time=02:00:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-raw-preflight-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-raw-preflight-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
if [[ -f "${PROJECT_CONFIG}" ]]; then
  source "${PROJECT_CONFIG}"
fi

RAW_FILE="${RAW_FILE:-}"
DATASET="${DATASET:-BroadbandHighFrequency}"
TEST_WELL="${TEST_WELL:-A1}"
DO_TINY_LOAD="${DO_TINY_LOAD:-false}"
TINY_LOAD_DURATION_S="${TINY_LOAD_DURATION_S:-1}"
AXION_LOADER_ROOT="${AXION_LOADER_ROOT:-/nfs/turbo/umms-parent/MannyAxionMEAscripts_v1/AxionFileLoader-main}"
PREFLIGHT_ROOT="${PREFLIGHT_ROOT:-${PROJECT_ROOT}/jobs/axion_raw_preflight}"

if [[ -z "${RAW_FILE}" ]]; then
  echo "ERROR: set RAW_FILE=/path/to/file.raw" >&2
  exit 2
fi

raw_base="$(basename "${RAW_FILE}")"
safe_raw_base="${raw_base//[^A-Za-z0-9._-]/_}"
run_id="${SLURM_JOB_ID:-manual}_$(date +%Y%m%d_%H%M%S)"
OUTPUT_DIR="${OUTPUT_DIR:-${PREFLIGHT_ROOT}/${safe_raw_base}_${run_id}}"
OUTPUT_JSON="${OUTPUT_JSON:-${OUTPUT_DIR}/preflight_result.json}"

mkdir -p "${OUTPUT_DIR}" "${KILOSORT_LOG_ROOT}"
exec > >(tee -a "${OUTPUT_DIR}/preflight_${SLURM_JOB_ID:-manual}.log") 2>&1

echo "Axion raw ingestion preflight started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "REPO_ROOT=${REPO_ROOT}"
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "RAW_FILE=${RAW_FILE}"
echo "DATASET=${DATASET}"
echo "TEST_WELL=${TEST_WELL}"
echo "DO_TINY_LOAD=${DO_TINY_LOAD}"
echo "TINY_LOAD_DURATION_S=${TINY_LOAD_DURATION_S}"
echo "AXION_LOADER_ROOT=${AXION_LOADER_ROOT}"
echo "OUTPUT_JSON=${OUTPUT_JSON}"

REPRO_DIR="${OUTPUT_DIR}/repro"
mkdir -p "${REPRO_DIR}"
{
  echo "#!/usr/bin/env bash"
  echo "set -euo pipefail"
  echo "cd ${REPO_ROOT@Q}"
  printf 'PROJECT_CONFIG=%q RAW_FILE=%q DATASET=%q TEST_WELL=%q DO_TINY_LOAD=%q TINY_LOAD_DURATION_S=%q OUTPUT_DIR=%q sbatch %q\n' \
    "${PROJECT_CONFIG}" "${RAW_FILE}" "${DATASET}" "${TEST_WELL}" "${DO_TINY_LOAD}" "${TINY_LOAD_DURATION_S}" "${OUTPUT_DIR}" "${REPO_ROOT}/slurm/preflight_axion_raw_ingestion.sbatch"
} > "${REPRO_DIR}/submit_command.sh"
chmod +x "${REPRO_DIR}/submit_command.sh"
if [[ -f "${PROJECT_CONFIG}" ]]; then
  cp "${PROJECT_CONFIG}" "${REPRO_DIR}/project_config.env"
fi
if [[ -f "$0" ]]; then
  cp "$0" "${REPRO_DIR}/submitted_job.sbatch"
fi

module purge
module load matlab/R2024b

matlab_command="addpath('${REPO_ROOT}/matlab', '-begin'); result = preflight_axion_raw_ingestion('${RAW_FILE}', '${OUTPUT_JSON}', 'AxionLoaderRoot', '${AXION_LOADER_ROOT}', 'Dataset', '${DATASET}', 'TestWell', '${TEST_WELL}', 'DoTinyLoad', ${DO_TINY_LOAD}, 'TinyLoadDurationS', ${TINY_LOAD_DURATION_S}); disp(result);"
printf 'matlab -batch %q\n' "${matlab_command}" > "${REPRO_DIR}/matlab_command.sh"
chmod +x "${REPRO_DIR}/matlab_command.sh"

matlab -batch "${matlab_command}"

echo "Axion raw ingestion preflight finished: $(date)"
find "${OUTPUT_DIR}" -maxdepth 3 -type f | sort
