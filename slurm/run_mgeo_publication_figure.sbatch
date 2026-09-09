#!/usr/bin/env bash
#SBATCH --job-name=mgeo_snr_activity
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/transient_plateing_raw_channel_snr_20260709/publication_figure/logs/mgeo_snr_activity.%j.scheduler.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/transient_plateing_raw_channel_snr_20260709/publication_figure/logs/mgeo_snr_activity.%j.scheduler.err

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike}"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"
OUTPUT_DIR="${OUTPUT_DIR:-/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/step1_nonlfp_th5_v5_ground_truth_latest/transient_plateing_raw_channel_snr_20260709/publication_figure}"

source "${PROJECT_CONFIG}"
set +u
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
set -u

mkdir -p "${OUTPUT_DIR}/logs"
exec > >(tee -a "${OUTPUT_DIR}/logs/mgeo_snr_activity.${SLURM_JOB_ID}.out") \
  2> >(tee -a "${OUTPUT_DIR}/logs/mgeo_snr_activity.${SLURM_JOB_ID}.err" >&2)

echo "SLURM_JOB_ID=${SLURM_JOB_ID}"
echo "OUTPUT_DIR=${OUTPUT_DIR}"

python "${REPO_ROOT}/scripts/plot_mgeo_publication_figure.py" \
  --output-dir "${OUTPUT_DIR}" \
  --png-dpi 600 \
  --export-formats png,pdf,svg
