#!/usr/bin/env bash
# Check the Axion Kilosort conda environment and GPU visibility on Great Lakes.
#
# Submit from repo root:
#   mkdir -p /nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs
#   sbatch slurm/check_kilosort_env.sbatch

#SBATCH --job-name=axion-ks-check
#SBATCH --account=parent0
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:20:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-ks-check-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/axion-ks-check-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
if [[ -f "${PROJECT_CONFIG}" ]]; then
  source "${PROJECT_CONFIG}"
fi

mkdir -p "${KILOSORT_LOG_ROOT}" "${KILOSORT_JOBS_ROOT}" "${KILOSORT_SCRATCH_ROOT}"
exec > >(tee -a "${KILOSORT_LOG_ROOT}/check_kilosort_env_${SLURM_JOB_ID:-manual}.log") 2>&1

echo "Axion Kilosort environment check started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "REPO_ROOT=${REPO_ROOT}"
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "CONDA_ENV=${CONDA_ENV}"

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
python "${REPO_ROOT}/run_axion_kilosort.py" --help >/dev/null

echo "Axion Kilosort environment check finished: $(date)"
