#!/usr/bin/env bash
# Export one Axion well's continuous voltage trace as a Kilosort-ready binary.
#
# Submit from repo root:
#   EXPORT_CONFIG=config/example_export_axion_well_binary.env sbatch slurm/export_axion_well_binary.sbatch

#SBATCH --job-name=axion-export-well
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-export-well-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-export-well-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
if [[ -f "${PROJECT_CONFIG}" ]]; then
  source "${PROJECT_CONFIG}"
fi

EXPORT_CONFIG="${EXPORT_CONFIG:-}"
if [[ -n "${EXPORT_CONFIG}" ]]; then
  source "${EXPORT_CONFIG}"
fi

RAW_FILE="${RAW_FILE:-}"
WELL="${WELL:-}"
RECORDING_STEM="${RECORDING_STEM:-}"
DATASET="${DATASET:-BroadbandHighFrequency}"
AXION_LOADER_ROOT="${AXION_LOADER_ROOT:-/nfs/turbo/umms-parent/MannyAxionMEAscripts_v1/AxionFileLoader-main}"
ELECTRODE_GEOMETRY="${ELECTRODE_GEOMETRY:-${ELECTRODE_GEOMETRY_4X4}}"
EXPORT_START_TIME_S="${EXPORT_START_TIME_S:-0}"
EXPORT_DURATION_S="${EXPORT_DURATION_S:-120}"
EXPORT_OUTPUT_DIR="${EXPORT_OUTPUT_DIR:-${KILOSORT_BINARY_ROOT}/${RECORDING_STEM:-unknown_recording}/${WELL:-unknown_well}}"
BINARY_FILE="${BINARY_FILE:-${EXPORT_OUTPUT_DIR}/${WELL}.bin}"
KILOSORT_ENV_FILE="${KILOSORT_ENV_FILE:-${KILOSORT_JOBS_ROOT}/${RECORDING_STEM}_${WELL}_kilosort.env}"

if [[ -z "${RAW_FILE}" ]]; then
  echo "ERROR: set RAW_FILE to an Axion .raw file." >&2
  exit 2
fi
if [[ -z "${WELL}" ]]; then
  echo "ERROR: set WELL, for example WELL=A1." >&2
  exit 2
fi
if [[ -z "${RECORDING_STEM}" ]]; then
  echo "ERROR: set RECORDING_STEM." >&2
  exit 2
fi

mkdir -p "${EXPORT_OUTPUT_DIR}" "${KILOSORT_LOG_ROOT}" "${KILOSORT_JOBS_ROOT}" "${KILOSORT_SCRATCH_ROOT}"
export TMPDIR="${TMPDIR:-${KILOSORT_SCRATCH_ROOT}/export_tmp_${SLURM_JOB_ID:-manual}}"
mkdir -p "${TMPDIR}"
exec > >(tee -a "${EXPORT_OUTPUT_DIR}/export_axion_well_binary_${SLURM_JOB_ID:-manual}.log") 2>&1

echo "Axion well binary export started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "REPO_ROOT=${REPO_ROOT}"
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "RAW_FILE=${RAW_FILE}"
echo "RECORDING_STEM=${RECORDING_STEM}"
echo "WELL=${WELL}"
echo "DATASET=${DATASET}"
echo "EXPORT_START_TIME_S=${EXPORT_START_TIME_S}"
echo "EXPORT_DURATION_S=${EXPORT_DURATION_S}"
echo "ELECTRODE_GEOMETRY=${ELECTRODE_GEOMETRY}"
echo "BINARY_FILE=${BINARY_FILE}"
echo "EXPORT_OUTPUT_DIR=${EXPORT_OUTPUT_DIR}"

module purge
module load matlab/R2024b

matlab -batch "addpath('${REPO_ROOT}/matlab', '-begin'); manifest = export_axion_well_kilosort_binary('${RAW_FILE}', '${WELL}', '${BINARY_FILE}', 'ElectrodeGeometry', '${ELECTRODE_GEOMETRY}', 'OutputDir', '${EXPORT_OUTPUT_DIR}', 'AxionLoaderRoot', '${AXION_LOADER_ROOT}', 'StartTime', ${EXPORT_START_TIME_S}, 'Duration', ${EXPORT_DURATION_S}, 'Dataset', '${DATASET}', 'RecordingStem', '${RECORDING_STEM}'); disp(manifest);"

cat > "${KILOSORT_ENV_FILE}" <<EOF
#!/usr/bin/env bash
source "\${PROJECT_CONFIG:-${PROJECT_CONFIG}}"
export RECORDING_STEM="${RECORDING_STEM}"
export WELL="${WELL}"
export BINARY_FILE="${BINARY_FILE}"
export OUTPUT_DIR="${KILOSORT_RESULTS_ROOT}/${RECORDING_STEM}/${WELL}"
export PLATE_MAP="\${PLATE_MAP_48_OPTO}"
export ELECTRODE_GEOMETRY="\${ELECTRODE_GEOMETRY_4X4}"
export FS="12500"
export DTYPE="int16"
export N_CHAN_BIN="16"
export DO_CAR="true"
export INVERT_SIGN="false"
export RUN_KILOSORT="false"
EOF
chmod +x "${KILOSORT_ENV_FILE}"

echo "Wrote Kilosort env file: ${KILOSORT_ENV_FILE}"
echo "Next readiness command:"
echo "SAMPLE_CONFIG=${KILOSORT_ENV_FILE} sbatch ${REPO_ROOT}/slurm/run_kilosort_well.sbatch"
echo "Axion well binary export finished: $(date)"
find "${EXPORT_OUTPUT_DIR}" -maxdepth 2 -type f | sort
