#!/usr/bin/env bash
# Debug MATLAB metadata peep access for one Axion .raw file.
#
# Submit from repo root:
#   RAW_FILE=/path/to/file.raw sbatch slurm/debug_axisfile_one_raw.sbatch

#SBATCH --job-name=axion-axis-debug
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=128G
#SBATCH --time=00:30:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-axis-debug-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-axis-debug-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
if [[ -f "${PROJECT_CONFIG}" ]]; then
  source "${PROJECT_CONFIG}"
fi

RAW_FILE="${RAW_FILE:-}"
AXION_LOADER_ROOT="${AXION_LOADER_ROOT:-/nfs/turbo/umms-parent/MannyAxionMEAscripts_v1/AxionFileLoader-main}"

if [[ -z "${RAW_FILE}" ]]; then
  echo "ERROR: set RAW_FILE=/path/to/file.raw" >&2
  exit 2
fi

mkdir -p "${KILOSORT_LOG_ROOT}"
exec > >(tee -a "${KILOSORT_LOG_ROOT}/debug_axisfile_one_raw_${SLURM_JOB_ID:-manual}.log") 2>&1

echo "Axion metadata one-raw debug started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "RAW_FILE=${RAW_FILE}"
echo "AXION_LOADER_ROOT=${AXION_LOADER_ROOT}"

module purge
module load matlab/R2024b

matlab -batch "addpath(genpath('${AXION_LOADER_ROOT}'), '-end'); addpath('${REPO_ROOT}/matlab/axionfileloader_overrides', '-begin'); addpath('${REPO_ROOT}/matlab', '-begin'); rawFile='${RAW_FILE}'; fprintf('Opening rawFile=%s\n', rawFile); try, info=peek_axion_raw_metadata(rawFile); fprintf('OK\n'); fprintf('HeaderVersion=%g.%g\n', info.header_version_major, info.header_version_minor); fprintf('PrimaryDataType=%g\n', info.primary_data_type); fprintf('NumDataSets=%g\n', info.num_datasets); fprintf('NumPlateMap=%g\n', info.num_plate_map_entries); fprintf('NumChannels=%g\n', info.num_channels); fprintf('PlateType=%s\n', info.plate_type_name); fprintf('WellDimensions=%s\n', info.well_dimensions); fprintf('ElectrodeDimensions=%s\n', info.electrode_dimensions); fprintf('SamplingFrequency=%g\n', info.sampling_frequency_hz); fprintf('VoltageScale=%.17g\n', info.voltage_scale_v_per_sample); fprintf('Duration=%g\n', info.duration_s); fprintf('AnalogMode=%s\n', info.metadata_analog_mode); clear info; catch ME, fprintf('FAILED\n'); disp(getReport(ME,'extended','hyperlinks','off')); exit(1); end"

echo "Axion metadata one-raw debug finished: $(date)"
