#!/usr/bin/env bash
# Run one Axion well NWB through Kempner/AIND ephys-spike-sorting.
#
# Submit from repo root:
#   KEMPNER_CONFIG=config/example_kempner_nwb_well.env sbatch slurm/run_kempner_nwb_well.sbatch

#SBATCH --job-name=axion-kempner-nwb
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=08:00:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/kempner/axion-kempner-nwb-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/kempner/axion-kempner-nwb-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
source "${PROJECT_CONFIG}"

KEMPNER_CONFIG="${KEMPNER_CONFIG:-}"
if [[ -n "${KEMPNER_CONFIG}" ]]; then
  source "${KEMPNER_CONFIG}"
fi

RECORDING_STEM="${RECORDING_STEM:-}"
WELL="${WELL:-}"
NWB_FILE="${NWB_FILE:-}"
KEMPNER_SORTER="${KEMPNER_SORTER:-kilosort4}"
KEMPNER_RUNMODE="${KEMPNER_RUNMODE:-fast}"
KEMPNER_N_JOBS="${KEMPNER_N_JOBS:-4}"
KEMPNER_JOB_DISPATCH_ARGS="${KEMPNER_JOB_DISPATCH_ARGS:---input nwb}"
KEMPNER_PREPROCESSING_ARGS="${KEMPNER_PREPROCESSING_ARGS:-}"
KEMPNER_SPIKESORTING_ARGS="${KEMPNER_SPIKESORTING_ARGS:---params-file ${REPO_ROOT}/config/kempner_kilosort4_axion_lumos_params.json --min-drift-channels 17}"
KEMPNER_POSTPROCESSING_ARGS="${KEMPNER_POSTPROCESSING_ARGS:-}"
KEMPNER_UNIT_CLASSIFIER_ARGS="${KEMPNER_UNIT_CLASSIFIER_ARGS:-}"
KEMPNER_NWB_SUBJECT_ARGS="${KEMPNER_NWB_SUBJECT_ARGS:-}"
KEMPNER_NWB_ECEPHYS_ARGS="${KEMPNER_NWB_ECEPHYS_ARGS:-}"
KEMPNER_ALLOW_OVERWRITE="${KEMPNER_ALLOW_OVERWRITE:-false}"
KEMPNER_DRY_RUN="${KEMPNER_DRY_RUN:-false}"

if [[ -z "${RECORDING_STEM}" ]]; then
  echo "ERROR: set RECORDING_STEM." >&2
  exit 2
fi
if [[ -z "${WELL}" ]]; then
  echo "ERROR: set WELL." >&2
  exit 2
fi
if [[ -z "${NWB_FILE}" || ! -f "${NWB_FILE}" ]]; then
  echo "ERROR: set NWB_FILE to an existing per-well NWB file." >&2
  exit 2
fi
if [[ ! -d "${KEMPNER_REPO_ROOT}/pipeline/kempner_cluster" ]]; then
  echo "ERROR: missing Kempner repo at ${KEMPNER_REPO_ROOT}" >&2
  exit 2
fi
if [[ ! -x "${KEMPNER_NEXTFLOW_BIN}" ]]; then
  echo "ERROR: Nextflow not found at ${KEMPNER_NEXTFLOW_BIN}." >&2
  echo "Run scripts/setup_kempner_nextflow.sh first." >&2
  exit 2
fi

mkdir -p "${KEMPNER_LOG_ROOT}" "${KEMPNER_JOBS_ROOT}" "${KEMPNER_NWB_INPUT_ROOT}" "${KEMPNER_RESULTS_ROOT}" "${KEMPNER_WORK_ROOT}"

input_dir="${KEMPNER_NWB_INPUT_ROOT}/${RECORDING_STEM}/${WELL}"
results_dir="${KEMPNER_RESULTS_ROOT}/${RECORDING_STEM}/${WELL}"
work_dir="${KEMPNER_WORK_ROOT}/${RECORDING_STEM}/${WELL}"
run_job_dir="${KEMPNER_JOBS_ROOT}/${RECORDING_STEM}/${WELL}"
pipeline_run_dir="${run_job_dir}/pipeline_kempner_cluster"
repro_dir="${results_dir}/repro"

if [[ -d "${results_dir}" && "${KEMPNER_ALLOW_OVERWRITE}" != "true" ]]; then
  if find "${results_dir}" -mindepth 1 -maxdepth 1 ! -name repro | grep -q .; then
    echo "ERROR: results already exist at ${results_dir}." >&2
    echo "Set KEMPNER_ALLOW_OVERWRITE=true to reuse this folder." >&2
    exit 2
  fi
fi

mkdir -p "${input_dir}" "${results_dir}" "${work_dir}" "${run_job_dir}" "${repro_dir}"
rm -f "${input_dir}"/*.nwb
ln -s "$(realpath "${NWB_FILE}")" "${input_dir}/$(basename "${NWB_FILE}")"
rm -rf "${pipeline_run_dir}"
cp -R "${KEMPNER_REPO_ROOT}/pipeline/kempner_cluster" "${pipeline_run_dir}"

cpu_cluster_options=" -p ${KEMPNER_CPU_PARTITION}"
gpu_cluster_options="-p ${KEMPNER_GPU_PARTITION}"
if [[ -n "${KEMPNER_ACCOUNT}" ]]; then
  cpu_cluster_options="${cpu_cluster_options} -A ${KEMPNER_ACCOUNT}"
  gpu_cluster_options="${gpu_cluster_options} -A ${KEMPNER_ACCOUNT}"
fi
if [[ -n "${KEMPNER_GPU_GRES}" ]]; then
  gpu_cluster_options="${gpu_cluster_options} --gres=${KEMPNER_GPU_GRES}"
fi

python3 - "${pipeline_run_dir}" "${cpu_cluster_options}" "${gpu_cluster_options}" <<'PY'
from pathlib import Path
import sys

pipeline_dir = Path(sys.argv[1])
cpu_options = sys.argv[2]
gpu_options = sys.argv[3]

config = pipeline_dir / "nextflow_slurm.config"
text = config.read_text(encoding="utf-8")
text = text.replace("clusterOptions = ' -p <partition_name> -A <account_name>'", f"clusterOptions = '{cpu_options}'")
config.write_text(text, encoding="utf-8")

main = pipeline_dir / "main_slurm.nf"
text = main.read_text(encoding="utf-8")
text = text.replace("clusterOptions '-p <partition_name> -A <account_name> --gres=gpu:1'", f"clusterOptions '{gpu_options}'")
text = text.replace("clusterOptions '-p <partition_name> --constraint=intel --gres=gpu:1'", f"clusterOptions '{gpu_options}'")
main.write_text(text, encoding="utf-8")
PY

module load "${KEMPNER_OPENJDK_MODULE}"
module load "${KEMPNER_SINGULARITY_MODULE}"
export NXF_SINGULARITY_CACHEDIR="${KEMPNER_CONTAINER_DIR}"
export SINGULARITY_CACHEDIR="${SINGULARITY_CACHEDIR:-${KEMPNER_SINGULARITY_CACHE_DIR}}"
export SINGULARITY_TMPDIR="${SINGULARITY_TMPDIR:-${KEMPNER_SINGULARITY_TMPDIR}}"
export TMPDIR="${TMPDIR:-${work_dir}/tmp_${SLURM_JOB_ID:-manual}}"
mkdir -p "${TMPDIR}" "${SINGULARITY_CACHEDIR}" "${SINGULARITY_TMPDIR}"

exec > >(tee -a "${results_dir}/run_kempner_nwb_well_${SLURM_JOB_ID:-manual}.log") 2>&1

echo "Axion Kempner NWB job started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "REPO_ROOT=${REPO_ROOT}"
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "KEMPNER_REPO_ROOT=${KEMPNER_REPO_ROOT}"
echo "RECORDING_STEM=${RECORDING_STEM}"
echo "WELL=${WELL}"
echo "NWB_FILE=${NWB_FILE}"
echo "DATA_PATH=${input_dir}"
echo "RESULTS_PATH=${results_dir}"
echo "WORK_DIR=${work_dir}"
echo "PIPELINE_PATH=${pipeline_run_dir}"
echo "CONTAINER_DIR=${KEMPNER_CONTAINER_DIR}"
echo "KEMPNER_SORTER=${KEMPNER_SORTER}"
echo "KEMPNER_RUNMODE=${KEMPNER_RUNMODE}"
echo "KEMPNER_JOB_DISPATCH_ARGS=${KEMPNER_JOB_DISPATCH_ARGS}"
echo "KEMPNER_SPIKESORTING_ARGS=${KEMPNER_SPIKESORTING_ARGS}"
echo "KEMPNER_DRY_RUN=${KEMPNER_DRY_RUN}"

{
  echo "#!/usr/bin/env bash"
  echo "set -euo pipefail"
  echo "cd ${REPO_ROOT@Q}"
  printf 'PROJECT_CONFIG=%q KEMPNER_CONFIG=%q sbatch %q\n' \
    "${PROJECT_CONFIG}" "${KEMPNER_CONFIG}" "${REPO_ROOT}/slurm/run_kempner_nwb_well.sbatch"
} > "${repro_dir}/submit_command.sh"
chmod +x "${repro_dir}/submit_command.sh"

nextflow_command=(
  "${KEMPNER_NEXTFLOW_BIN}"
  -C "${pipeline_run_dir}/nextflow_slurm.config"
  -log "${results_dir}/nextflow.log"
  run "${pipeline_run_dir}/main_slurm.nf"
  -work-dir "${work_dir}"
  --n_jobs "${KEMPNER_N_JOBS}"
  --sorter "${KEMPNER_SORTER}"
  --runmode "${KEMPNER_RUNMODE}"
  --job_dispatch_args "${KEMPNER_JOB_DISPATCH_ARGS}"
  --spikesorting_args "${KEMPNER_SPIKESORTING_ARGS}"
)
if [[ -n "${KEMPNER_PREPROCESSING_ARGS}" ]]; then
  nextflow_command+=(--preprocessing_args "${KEMPNER_PREPROCESSING_ARGS}")
fi
if [[ -n "${KEMPNER_POSTPROCESSING_ARGS}" ]]; then
  nextflow_command+=(--postprocessing_args "${KEMPNER_POSTPROCESSING_ARGS}")
fi
if [[ -n "${KEMPNER_UNIT_CLASSIFIER_ARGS}" ]]; then
  nextflow_command+=(--unit_classifier_args "${KEMPNER_UNIT_CLASSIFIER_ARGS}")
fi
if [[ -n "${KEMPNER_NWB_SUBJECT_ARGS}" ]]; then
  nextflow_command+=(--nwb_subject_args "${KEMPNER_NWB_SUBJECT_ARGS}")
fi
if [[ -n "${KEMPNER_NWB_ECEPHYS_ARGS}" ]]; then
  nextflow_command+=(--nwb_ecephys_args "${KEMPNER_NWB_ECEPHYS_ARGS}")
fi

{
  echo "#!/usr/bin/env bash"
  echo "set -euo pipefail"
  echo "module load ${KEMPNER_OPENJDK_MODULE@Q}"
  echo "module load ${KEMPNER_SINGULARITY_MODULE@Q}"
  printf 'CONTAINER_DIR=%q DATA_PATH=%q RESULTS_PATH=%q ' "${KEMPNER_CONTAINER_DIR}" "${input_dir}" "${results_dir}"
  printf '%q ' "${nextflow_command[@]}"
  echo
} > "${repro_dir}/nextflow_command.sh"
chmod +x "${repro_dir}/nextflow_command.sh"

if [[ -f "${PROJECT_CONFIG}" ]]; then
  cp "${PROJECT_CONFIG}" "${repro_dir}/project_config.env"
fi
if [[ -n "${KEMPNER_CONFIG}" && -f "${KEMPNER_CONFIG}" ]]; then
  cp "${KEMPNER_CONFIG}" "${repro_dir}/kempner_config.env"
fi
cp "${REPO_ROOT}/config/kempner_kilosort4_axion_lumos_params.json" "${repro_dir}/kilosort4_axion_lumos_params.json"
if [[ -f "$0" ]]; then
  cp "$0" "${repro_dir}/submitted_job.sbatch"
fi
git -C "${KEMPNER_REPO_ROOT}" rev-parse HEAD > "${repro_dir}/kempner_repo_commit.txt"
git -C "${KEMPNER_REPO_ROOT}" status --short > "${repro_dir}/kempner_repo_status.txt"
realpath "${NWB_FILE}" > "${repro_dir}/input_nwb.txt"
printf '%s\n' "${input_dir}" > "${repro_dir}/data_path.txt"
printf '%s\n' "${results_dir}" > "${repro_dir}/results_path.txt"

missing_containers=()
required_sifs=(
  "aind-ephys-pipeline-base_si-0.101.2.sif"
  "aind-ephys-pipeline-nwb_si-0.101.2.sif"
  "aind-ephys-unit-classifier_si-0.101.2.sif"
)
case "${KEMPNER_SORTER}" in
  kilosort4)
    required_sifs+=("aind-ephys-spikesort-kilosort4_si-0.101.2.sif")
    ;;
  kilosort25)
    required_sifs+=("aind-ephys-spikesort-kilosort25_si-0.101.2.sif")
    ;;
  spykingcircus2)
    required_sifs+=("aind-ephys-spikesort-spykingcircus2_si-0.101.2.sif")
    ;;
esac
for sif_name in "${required_sifs[@]}"; do
  if [[ ! -f "${KEMPNER_CONTAINER_DIR}/${sif_name}" ]]; then
    missing_containers+=("${KEMPNER_CONTAINER_DIR}/${sif_name}")
  fi
done

if [[ "${KEMPNER_DRY_RUN}" == "true" ]]; then
  echo "Dry run complete. Repro files were written to ${repro_dir}."
  if (( ${#missing_containers[@]} > 0 )); then
    echo "Containers still need to be pulled before a real run:"
    printf '  %s\n' "${missing_containers[@]}"
  fi
  exit 0
fi

if (( ${#missing_containers[@]} > 0 )); then
  echo "ERROR: missing Kempner/AIND Singularity containers." >&2
  printf '  %s\n' "${missing_containers[@]}" >&2
  echo "Run scripts/pull_kempner_singularity_containers.sh before launching Kempner." >&2
  exit 2
fi

CONTAINER_DIR="${KEMPNER_CONTAINER_DIR}" DATA_PATH="${input_dir}" RESULTS_PATH="${results_dir}" "${nextflow_command[@]}"

echo "Axion Kempner NWB job finished: $(date)"
find "${results_dir}" -maxdepth 3 -type f | sort
