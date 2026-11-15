#!/usr/bin/env bash
#SBATCH --job-name=mcs-actuator-metrics
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=04:00:00
#SBATCH --output=/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/actuator_metric_exploration/job-%j.log

set -euo pipefail
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export MPLCONFIGDIR=/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/actuator_metric_exploration/.mplconfig
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/envs/axion-kilosort/bin/python -u \
  /home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/scripts/explore_mcs_actuator_separation.py
