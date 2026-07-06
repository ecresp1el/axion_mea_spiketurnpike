#!/usr/bin/env bash
# Pull Kempner/AIND Singularity images needed by the selected sorter.

#SBATCH --job-name=axion-kempner-img
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/kempner/axion-kempner-img-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/kempner/axion-kempner-img-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
source "${PROJECT_CONFIG}"

mkdir -p "${KEMPNER_LOG_ROOT}" "${KEMPNER_CONTAINER_DIR}" "${KEMPNER_SINGULARITY_CACHE_DIR}" "${KEMPNER_SINGULARITY_TMPDIR}"

exec > >(tee -a "${KEMPNER_LOG_ROOT}/pull_kempner_containers_${SLURM_JOB_ID:-manual}.log") 2>&1

echo "Kempner container pull started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "KEMPNER_REPO_ROOT=${KEMPNER_REPO_ROOT}"
echo "KEMPNER_CONTAINER_DIR=${KEMPNER_CONTAINER_DIR}"
echo "KEMPNER_SINGULARITY_CACHE_DIR=${KEMPNER_SINGULARITY_CACHE_DIR}"
echo "KEMPNER_SINGULARITY_TMPDIR=${KEMPNER_SINGULARITY_TMPDIR}"
echo "KEMPNER_SORTER=${KEMPNER_SORTER:-kilosort4}"
echo "KEMPNER_PULL_ALL_CONTAINERS=${KEMPNER_PULL_ALL_CONTAINERS:-false}"

"${REPO_ROOT}/scripts/pull_kempner_singularity_containers.sh"

echo "Kempner container pull finished: $(date)"
