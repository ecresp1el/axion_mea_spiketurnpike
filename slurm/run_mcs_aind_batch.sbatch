#!/usr/bin/env bash
# One complete MCS recording per array task; array concurrency is bounded at submission.
#SBATCH --job-name=mcs-aind-th5
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=02:00:00

set -euo pipefail
: "${MCS_BATCH_DIR:?Set MCS_BATCH_DIR to the prepared batch directory}"
python=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/envs/axion-kilosort/bin/python
if [[ "${MCS_BATCH_SUMMARY_ONLY:-0}" == 1 ]]; then
    sleep 10
    exec "${python}" "${MCS_BATCH_DIR}/code/scripts/run_mcs_aind_batch.py" status \
        --batch-dir "${MCS_BATCH_DIR}" --scheduler
fi
: "${SLURM_ARRAY_TASK_ID:?This wrapper requires a Slurm array task}"
exec "${python}" "${MCS_BATCH_DIR}/code/scripts/run_mcs_aind_batch.py" worker \
    --batch-dir "${MCS_BATCH_DIR}" --task-index "${SLURM_ARRAY_TASK_ID}"
