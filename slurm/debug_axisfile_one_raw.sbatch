#!/usr/bin/env bash
# Debug MATLAB AxisFile metadata access for one Axion .raw file.
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

echo "AxisFile one-raw debug started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "RAW_FILE=${RAW_FILE}"
echo "AXION_LOADER_ROOT=${AXION_LOADER_ROOT}"

module purge
module load matlab/R2024b

matlab -batch "addpath(genpath('${AXION_LOADER_ROOT}'), '-end'); addpath('${REPO_ROOT}/matlab/axionfileloader_overrides', '-begin'); rawFile='${RAW_FILE}'; fprintf('Opening rawFile=%s\n', rawFile); try, A=AxisFile(rawFile); fprintf('OK\n'); fprintf('HeaderVersion=%d.%d\n', A.HeaderVersionMajor, A.HeaderVersionMinor); fprintf('PrimaryDataType=%g\n', double(A.PrimaryDataType)); fprintf('NumDataSets=%d\n', numel(A.DataSets)); fprintf('NumPlateMap=%d\n', numel(A.PlateMap)); fprintf('NumChannels=%d\n', numel(A.ChannelArray.Channels)); if ~isempty(A.DataSets), D=A.DataSets(1); fprintf('SamplingFrequency=%g\n', D.SamplingFrequency); fprintf('VoltageScale=%.17g\n', D.VoltageScale); if isprop(D,'Duration'), fprintf('Duration=%g\n', D.Duration); end; end; delete(A); clear A D; catch ME, fprintf('FAILED\n'); disp(getReport(ME,'extended','hyperlinks','off')); end"

echo "AxisFile one-raw debug finished: $(date)"
