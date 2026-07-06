#!/usr/bin/env bash
# Inspect Axion .raw metadata through MATLAB AxisFile without copying data.
#
# Submit from repo root:
#   sbatch slurm/inspect_axion_raw_metadata.sbatch

#SBATCH --job-name=axion-raw-meta
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=128G
#SBATCH --time=02:00:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-raw-meta-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-raw-meta-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
if [[ -f "${PROJECT_CONFIG}" ]]; then
  source "${PROJECT_CONFIG}"
fi

AXION_SOURCE_ROOT="${AXION_SOURCE_ROOT:-/nfs/turbo/umms-parent/axion_mea_files_directory}"
AXION_LOADER_ROOT="${AXION_LOADER_ROOT:-/nfs/turbo/umms-parent/MannyAxionMEAscripts_v1/AxionFileLoader-main}"
OUTPUT_CSV="${OUTPUT_CSV:-${PROJECT_ROOT}/metadata/matlab_axisfile_raw_metadata_inventory.csv}"

mkdir -p "${KILOSORT_LOG_ROOT}" "$(dirname "${OUTPUT_CSV}")"
exec > >(tee -a "${KILOSORT_LOG_ROOT}/inspect_axion_raw_metadata_${SLURM_JOB_ID:-manual}.log") 2>&1

echo "Axion raw metadata inspection started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "AXION_SOURCE_ROOT=${AXION_SOURCE_ROOT}"
echo "AXION_LOADER_ROOT=${AXION_LOADER_ROOT}"
echo "OUTPUT_CSV=${OUTPUT_CSV}"

module purge
module load matlab/R2024b

matlab -batch "addpath('${REPO_ROOT}/matlab'); T = inspect_axion_raw_metadata('${AXION_SOURCE_ROOT}', '${OUTPUT_CSV}', '${AXION_LOADER_ROOT}'); disp(T(:, {'raw_name','raw_file_kind','status','sampling_frequency_hz','num_channels','num_plate_map_entries','plate_type_name','well_dimensions','electrode_dimensions','duration_s','metadata_analog_mode'}));"

echo "Axion raw metadata inspection finished: $(date)"
