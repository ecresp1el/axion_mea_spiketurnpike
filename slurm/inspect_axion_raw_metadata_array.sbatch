#!/usr/bin/env bash
# Inspect Axion .raw metadata through MATLAB AxisFile, one raw per array task.
#
# Submit from repo root after creating RAW_FILE_LIST:
#   RAW_FILE_LIST=/path/raw_files.txt \
#   OUTPUT_DIR=/path/per_file_csv \
#   sbatch --array=1-N%8 slurm/inspect_axion_raw_metadata_array.sbatch

#SBATCH --job-name=axion-raw-meta-array
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-raw-meta-array-%A_%a.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-raw-meta-array-%A_%a.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
if [[ -f "${PROJECT_CONFIG}" ]]; then
  source "${PROJECT_CONFIG}"
fi

RAW_FILE_LIST="${RAW_FILE_LIST:?set RAW_FILE_LIST=/path/to/raw_files.txt}"
OUTPUT_DIR="${OUTPUT_DIR:?set OUTPUT_DIR=/path/to/per_file_csv_dir}"
AXION_LOADER_ROOT="${AXION_LOADER_ROOT:-/nfs/turbo/umms-parent/MannyAxionMEAscripts_v1/AxionFileLoader-main}"

task_id="${SLURM_ARRAY_TASK_ID:?SLURM_ARRAY_TASK_ID is required}"
RAW_FILE="$(sed -n "${task_id}p" "${RAW_FILE_LIST}")"
if [[ -z "${RAW_FILE}" ]]; then
  echo "ERROR: no raw file at array index ${task_id}" >&2
  exit 2
fi

mkdir -p "${KILOSORT_LOG_ROOT}" "${OUTPUT_DIR}"
OUTPUT_CSV="${OUTPUT_DIR}/raw_metadata_${task_id}.csv"

exec > >(tee -a "${KILOSORT_LOG_ROOT}/inspect_axion_raw_metadata_array_${SLURM_ARRAY_JOB_ID:-manual}_${task_id}.log") 2>&1

echo "Axion one-raw metadata inspection started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_ARRAY_JOB_ID=${SLURM_ARRAY_JOB_ID:-}"
echo "SLURM_ARRAY_TASK_ID=${task_id}"
echo "RAW_FILE=${RAW_FILE}"
echo "OUTPUT_CSV=${OUTPUT_CSV}"
echo "AXION_LOADER_ROOT=${AXION_LOADER_ROOT}"

module purge
module load matlab/R2024b

matlab -batch "addpath('${REPO_ROOT}/matlab'); T = inspect_axion_raw_metadata('${RAW_FILE}', '${OUTPUT_CSV}', '${AXION_LOADER_ROOT}'); disp(T(:, {'raw_name','raw_file_kind','status','sampling_frequency_hz','num_channels','num_plate_map_entries','plate_type_name','well_dimensions','electrode_dimensions','duration_s','metadata_analog_mode'}));"

echo "Axion one-raw metadata inspection finished: $(date)"
