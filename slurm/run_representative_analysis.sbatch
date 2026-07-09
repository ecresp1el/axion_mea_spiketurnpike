#!/usr/bin/env bash
# Run a targeted representative-unit analysis command file.

#SBATCH --job-name=axion-rep-units
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=00:30:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/representative_units/axion-rep-units-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/representative_units/axion-rep-units-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
source "${PROJECT_CONFIG}"

REPRESENTATIVE_COMMAND_FILE="${REPRESENTATIVE_COMMAND_FILE:?set REPRESENTATIVE_COMMAND_FILE}"
REPRESENTATIVE_OUTPUT_DIR="${REPRESENTATIVE_OUTPUT_DIR:?set REPRESENTATIVE_OUTPUT_DIR}"

mkdir -p "${PROJECT_ROOT}/logs/representative_units" "${REPRESENTATIVE_OUTPUT_DIR}"

echo "Representative analysis started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "REPRESENTATIVE_COMMAND_FILE=${REPRESENTATIVE_COMMAND_FILE}"
echo "REPRESENTATIVE_OUTPUT_DIR=${REPRESENTATIVE_OUTPUT_DIR}"

bash "${REPRESENTATIVE_COMMAND_FILE}"

echo "Representative analysis finished: $(date)"
