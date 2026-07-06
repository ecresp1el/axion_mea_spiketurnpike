#!/usr/bin/env bash
# Package one exported Axion well binary as NWB.
#
# Submit from repo root:
#   NWB_CONFIG=config/example_export_axion_well_nwb.env sbatch slurm/export_axion_well_nwb.sbatch

#SBATCH --job-name=axion-export-nwb
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-export-nwb-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-export-nwb-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
if [[ -f "${PROJECT_CONFIG}" ]]; then
  source "${PROJECT_CONFIG}"
fi

NWB_CONFIG="${NWB_CONFIG:-}"
if [[ -n "${NWB_CONFIG}" ]]; then
  source "${NWB_CONFIG}"
fi

RECORDING_STEM="${RECORDING_STEM:-}"
WELL="${WELL:-}"
EXPORT_OUTPUT_DIR="${EXPORT_OUTPUT_DIR:-${KILOSORT_BINARY_ROOT}/${RECORDING_STEM:-unknown_recording}/${WELL:-unknown_well}}"
BINARY_FILE="${BINARY_FILE:-${EXPORT_OUTPUT_DIR}/${WELL}.bin}"
CHANNEL_MAPPING_CSV="${CHANNEL_MAPPING_CSV:-${EXPORT_OUTPUT_DIR}/channel_mapping.csv}"
BINARY_EXPORT_MANIFEST="${BINARY_EXPORT_MANIFEST:-${EXPORT_OUTPUT_DIR}/binary_export_manifest.json}"
KILOSORT_OUTPUT_DIR="${KILOSORT_OUTPUT_DIR:-${KILOSORT_RESULTS_ROOT}/${RECORDING_STEM:-unknown_recording}/${WELL:-unknown_well}}"
KILOSORT_MANIFEST="${KILOSORT_MANIFEST:-${KILOSORT_OUTPUT_DIR}/kilosort_ready_manifest.json}"
PROBE_JSON="${PROBE_JSON:-${KILOSORT_OUTPUT_DIR}/probe.json}"
RAW_METADATA_INVENTORY="${RAW_METADATA_INVENTORY:-${PROJECT_ROOT}/metadata/matlab_axisfile_raw_metadata_inventory.csv}"
NWB_OUTPUT_DIR="${NWB_OUTPUT_DIR:-${PROJECT_ROOT}/data/interim/nwb/${RECORDING_STEM:-unknown_recording}/${WELL:-unknown_well}}"
OUTPUT_NWB="${OUTPUT_NWB:-${NWB_OUTPUT_DIR}/${RECORDING_STEM}_${WELL}.nwb}"
SESSION_DESCRIPTION="${SESSION_DESCRIPTION:-Axion MEA per-well continuous voltage export for Kempner/AIND ingestion}"
TIMEZONE="${TIMEZONE:-America/Detroit}"

if [[ -z "${RECORDING_STEM}" ]]; then
  echo "ERROR: set RECORDING_STEM." >&2
  exit 2
fi
if [[ -z "${WELL}" ]]; then
  echo "ERROR: set WELL." >&2
  exit 2
fi
for required_file in "${BINARY_FILE}" "${CHANNEL_MAPPING_CSV}" "${BINARY_EXPORT_MANIFEST}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "ERROR: required file is missing: ${required_file}" >&2
    exit 2
  fi
done

mkdir -p "${NWB_OUTPUT_DIR}" "${KILOSORT_LOG_ROOT}" "${KILOSORT_SCRATCH_ROOT}"
export TMPDIR="${TMPDIR:-${KILOSORT_SCRATCH_ROOT}/nwb_tmp_${SLURM_JOB_ID:-manual}}"
mkdir -p "${TMPDIR}"
exec > >(tee -a "${NWB_OUTPUT_DIR}/export_axion_well_nwb_${SLURM_JOB_ID:-manual}.log") 2>&1

echo "Axion well NWB export started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "REPO_ROOT=${REPO_ROOT}"
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "RECORDING_STEM=${RECORDING_STEM}"
echo "WELL=${WELL}"
echo "BINARY_FILE=${BINARY_FILE}"
echo "CHANNEL_MAPPING_CSV=${CHANNEL_MAPPING_CSV}"
echo "BINARY_EXPORT_MANIFEST=${BINARY_EXPORT_MANIFEST}"
echo "KILOSORT_MANIFEST=${KILOSORT_MANIFEST}"
echo "PROBE_JSON=${PROBE_JSON}"
echo "RAW_METADATA_INVENTORY=${RAW_METADATA_INVENTORY}"
echo "OUTPUT_NWB=${OUTPUT_NWB}"

source "${CONDA_BASE}/etc/profile.d/conda.sh"
set +u
conda activate "${CONDA_ENV}"
set -u
python --version
python - <<'PY'
import pynwb
print("pynwb:", pynwb.__version__)
PY

args=(
  --binary-file "${BINARY_FILE}"
  --output-nwb "${OUTPUT_NWB}"
  --channel-mapping "${CHANNEL_MAPPING_CSV}"
  --export-manifest "${BINARY_EXPORT_MANIFEST}"
  --recording-stem "${RECORDING_STEM}"
  --well "${WELL}"
  --session-description "${SESSION_DESCRIPTION}"
  --timezone "${TIMEZONE}"
)
if [[ -f "${KILOSORT_MANIFEST}" ]]; then
  args+=(--kilosort-manifest "${KILOSORT_MANIFEST}")
fi
if [[ -f "${PROBE_JSON}" ]]; then
  args+=(--probe-json "${PROBE_JSON}")
fi
if [[ -f "${RAW_METADATA_INVENTORY}" ]]; then
  args+=(--raw-metadata-inventory "${RAW_METADATA_INVENTORY}")
fi

python "${REPO_ROOT}/run_axion_binary_to_nwb.py" "${args[@]}"

echo "Axion well NWB export finished: $(date)"
find "${NWB_OUTPUT_DIR}" -maxdepth 2 -type f | sort
