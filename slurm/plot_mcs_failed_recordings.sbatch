#!/usr/bin/env bash
#SBATCH --job-name=mcs-failed-signal-review
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/mcs-failed-review-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/mcs-failed-review-%j.err

set -euo pipefail
source "${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
: "${MCS_BATCH_DIR:?Set MCS_BATCH_DIR to the saved batch directory}"
: "${SLURM_JOB_ID:?Submit this wrapper through Slurm}"
output="${MCS_REVIEW_OUTPUT_DIR:-${PROJECT_ROOT}/results/diagnostics/mcs_failed_review_${SLURM_JOB_ID}}"
export TMPDIR="${PROJECT_ROOT}/scratch/mcs_failed_review_${SLURM_JOB_ID}"
mkdir -p "${TMPDIR}"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
python "${REPO_ROOT}/scripts/plot_mcs_failed_recordings.py" \
    --batch-dir "${MCS_BATCH_DIR}" --output-dir "${output}"
cp "${BASH_SOURCE[0]}" "${output}/repro/submitted_job.sbatch"
