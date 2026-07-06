#!/usr/bin/env bash
# Run one Axion well NWB through the current AIND ephys pipeline on Great Lakes.
#
# Submit from repo root:
#   AIND_CONFIG=config/example_aind_nwb_well.env sbatch slurm/run_aind_nwb_well.sbatch

#SBATCH --job-name=axion-aind-nwb
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=08:00:00
#SBATCH --output=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/aind/axion-aind-nwb-%j.out
#SBATCH --error=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/logs/aind/axion-aind-nwb-%j.err

set -euo pipefail

PROJECT_CONFIG="${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"
source "${PROJECT_CONFIG}"

AIND_CONFIG="${AIND_CONFIG:-}"
if [[ -n "${AIND_CONFIG}" ]]; then
  source "${AIND_CONFIG}"
fi

RECORDING_STEM="${RECORDING_STEM:-}"
WELL="${WELL:-}"
NWB_FILE="${NWB_FILE:-}"
AIND_RUNMODE="${AIND_RUNMODE:-fast}"
AIND_SORTER="${AIND_SORTER:-kilosort4}"
AIND_ALLOW_OVERWRITE="${AIND_ALLOW_OVERWRITE:-false}"
AIND_RESUME="${AIND_RESUME:-true}"
AIND_ENABLE_MONITOR="${AIND_ENABLE_MONITOR:-true}"
AIND_MONITOR_INTERVAL_SECONDS="${AIND_MONITOR_INTERVAL_SECONDS:-60}"

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
if [[ ! -f "${AIND_PIPELINE_ROOT}/pipeline/main_multi_backend.nf" ]]; then
  echo "ERROR: missing maintained AIND repo at ${AIND_PIPELINE_ROOT}." >&2
  exit 2
fi
if [[ ! -f "${AIND_PARAMS_FILE}" ]]; then
  echo "ERROR: missing AIND params file at ${AIND_PARAMS_FILE}." >&2
  exit 2
fi
if [[ ! -f "${AIND_SLURM_CONFIG}" ]]; then
  echo "ERROR: missing Great Lakes AIND Nextflow config at ${AIND_SLURM_CONFIG}." >&2
  exit 2
fi

if [[ "${AIND_NEXTFLOW_BIN}" == */* ]]; then
  if [[ ! -x "${AIND_NEXTFLOW_BIN}" ]]; then
    echo "ERROR: AIND_NEXTFLOW_BIN is not executable: ${AIND_NEXTFLOW_BIN}" >&2
    exit 2
  fi
else
  if ! command -v "${AIND_NEXTFLOW_BIN}" >/dev/null 2>&1; then
    echo "ERROR: AIND_NEXTFLOW_BIN is not on PATH: ${AIND_NEXTFLOW_BIN}" >&2
    exit 2
  fi
fi

mkdir -p \
  "${AIND_LOG_ROOT}" \
  "${AIND_JOBS_ROOT}" \
  "${AIND_NWB_INPUT_ROOT}" \
  "${AIND_RESULTS_ROOT}" \
  "${AIND_WORK_ROOT}" \
  "${AIND_CONTAINER_DIR}" \
  "${AIND_CONTAINER_HOME}" \
  "${AIND_XDG_CACHE_HOME}" \
  "${AIND_XDG_CACHE_HOME}/matplotlib" \
  "${AIND_PYTHON_SHIM_DIR}" \
  "${AIND_SINGULARITY_CACHE_DIR}" \
  "${AIND_SINGULARITY_TMPDIR}"

input_dir="${AIND_NWB_INPUT_ROOT}/${RECORDING_STEM}/${WELL}"
results_dir="${AIND_RESULTS_ROOT}/${RECORDING_STEM}/${WELL}"
work_dir="${AIND_WORK_ROOT}/${RECORDING_STEM}/${WELL}"
run_job_dir="${AIND_JOBS_ROOT}/${RECORDING_STEM}/${WELL}"
repro_dir="${results_dir}/repro"

if [[ -d "${results_dir}" && "${AIND_ALLOW_OVERWRITE}" != "true" ]]; then
  if find "${results_dir}" -mindepth 1 -maxdepth 1 ! -name repro ! -name nextflow | grep -q .; then
    echo "ERROR: results already exist at ${results_dir}." >&2
    echo "Set AIND_ALLOW_OVERWRITE=true to reuse this folder." >&2
    exit 2
  fi
fi

mkdir -p "${input_dir}" "${results_dir}/nextflow" "${work_dir}" "${run_job_dir}" "${repro_dir}"
rm -f "${input_dir}"/*.nwb
ln -s "$(realpath "${NWB_FILE}")" "${input_dir}/$(basename "${NWB_FILE}")"

if [[ -n "${AIND_OPENJDK_MODULE}" ]]; then
  module load "${AIND_OPENJDK_MODULE}"
fi
module load "${AIND_SINGULARITY_MODULE}"

export AIND_ACCOUNT AIND_CPU_PARTITION AIND_GPU_PARTITION AIND_GPU_GRES
export NXF_SINGULARITY_CACHEDIR="${AIND_CONTAINER_DIR}"
export NXF_APPTAINER_CACHEDIR="${AIND_CONTAINER_DIR}"
export NXF_SYNTAX_PARSER="${NXF_SYNTAX_PARSER:-v1}"
export SINGULARITY_CACHEDIR="${AIND_SINGULARITY_CACHE_DIR}"
export SINGULARITY_TMPDIR="${AIND_SINGULARITY_TMPDIR}"
export APPTAINER_CACHEDIR="${AIND_SINGULARITY_CACHE_DIR}"
export APPTAINER_TMPDIR="${AIND_SINGULARITY_TMPDIR}"
export HOME="${AIND_CONTAINER_HOME}"
export XDG_CACHE_HOME="${AIND_XDG_CACHE_HOME}"
export MPLCONFIGDIR="${AIND_XDG_CACHE_HOME}/matplotlib"
export TMPDIR="${TMPDIR:-${work_dir}/tmp_${SLURM_JOB_ID:-manual}}"
mkdir -p "${TMPDIR}"

# AIND capsule run scripts call `python`, but the maintained si-0.104.8 images
# do not all use the same conda prefix. Use a real wrapper file so Singularity
# can bind it into `/usr/local/bin/python` inside the container.
rm -f "${AIND_PYTHON_SHIM_DIR}/python"
cat > "${AIND_PYTHON_SHIM_DIR}/python" <<'EOF'
#!/usr/bin/env sh
for candidate in \
  /opt/conda/bin/python \
  /home/miniconda3/bin/python \
  /usr/bin/python3
do
  if [ -x "${candidate}" ]; then
    exec "${candidate}" "$@"
  fi
done
echo "ERROR: no supported container Python found." >&2
exit 127
EOF
chmod +x "${AIND_PYTHON_SHIM_DIR}/python"
export PATH="${AIND_PYTHON_SHIM_DIR}:${PATH}"

exec > >(tee -a "${results_dir}/run_aind_nwb_well_${SLURM_JOB_ID:-manual}.log") 2>&1

echo "Axion AIND NWB job started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${SLURM_JOB_ID:-}"
echo "REPO_ROOT=${REPO_ROOT}"
echo "PROJECT_ROOT=${PROJECT_ROOT}"
echo "AIND_PIPELINE_ROOT=${AIND_PIPELINE_ROOT}"
echo "AIND_NEXTFLOW_BIN=${AIND_NEXTFLOW_BIN}"
echo "RECORDING_STEM=${RECORDING_STEM}"
echo "WELL=${WELL}"
echo "NWB_FILE=${NWB_FILE}"
echo "DATA_PATH=${input_dir}"
echo "RESULTS_PATH=${results_dir}"
echo "WORK_DIR=${work_dir}"
echo "AIND_PARAMS_FILE=${AIND_PARAMS_FILE}"
echo "AIND_RUNMODE=${AIND_RUNMODE}"
echo "AIND_SORTER=${AIND_SORTER}"
echo "AIND_ENABLE_MONITOR=${AIND_ENABLE_MONITOR}"
echo "AIND_MONITOR_INTERVAL_SECONDS=${AIND_MONITOR_INTERVAL_SECONDS}"
echo "AIND_CONTAINER_DIR=${AIND_CONTAINER_DIR}"
echo "AIND_CONTAINER_HOME=${AIND_CONTAINER_HOME}"
echo "AIND_XDG_CACHE_HOME=${AIND_XDG_CACHE_HOME}"
echo "AIND_PYTHON_SHIM_DIR=${AIND_PYTHON_SHIM_DIR}"
if [[ -f "${AIND_PIPELINE_ROOT}/pipeline/capsule_versions_custom.env" ]]; then
  echo "AIND_CAPSULE_VERSIONS=${AIND_PIPELINE_ROOT}/pipeline/capsule_versions_custom.env"
else
  echo "AIND_CAPSULE_VERSIONS=${AIND_PIPELINE_ROOT}/pipeline/capsule_versions.env"
fi
echo "NXF_SYNTAX_PARSER=${NXF_SYNTAX_PARSER}"

{
  echo "#!/usr/bin/env bash"
  echo "set -euo pipefail"
  echo "cd ${REPO_ROOT@Q}"
  printf 'PROJECT_CONFIG=%q AIND_CONFIG=%q sbatch %q\n' \
    "${PROJECT_CONFIG}" "${AIND_CONFIG}" "${REPO_ROOT}/slurm/run_aind_nwb_well.sbatch"
} > "${repro_dir}/submit_command.sh"
chmod +x "${repro_dir}/submit_command.sh"

nextflow_config="${AIND_PIPELINE_ROOT}/pipeline/nextflow_slurm.config,${AIND_SLURM_CONFIG}"
nextflow_command=(
  "${AIND_NEXTFLOW_BIN}"
  -C "${nextflow_config}"
  -log "${results_dir}/nextflow/nextflow.log"
  run "${AIND_PIPELINE_ROOT}/pipeline/main_multi_backend.nf"
  -work-dir "${work_dir}"
  --params_file "${AIND_PARAMS_FILE}"
  --runmode "${AIND_RUNMODE}"
  --sorter "${AIND_SORTER}"
)
if [[ "${AIND_RESUME}" == "true" ]]; then
  nextflow_command+=(-resume)
fi

{
  echo "#!/usr/bin/env bash"
  echo "set -euo pipefail"
  if [[ -n "${AIND_OPENJDK_MODULE}" ]]; then
    echo "module load ${AIND_OPENJDK_MODULE@Q}"
  fi
  echo "module load ${AIND_SINGULARITY_MODULE@Q}"
  echo "export NXF_SYNTAX_PARSER=${NXF_SYNTAX_PARSER@Q}"
  printf 'DATA_PATH=%q RESULTS_PATH=%q ' "${input_dir}" "${results_dir}"
  printf '%q ' "${nextflow_command[@]}"
  echo
} > "${repro_dir}/nextflow_command.sh"
chmod +x "${repro_dir}/nextflow_command.sh"

cp "${PROJECT_CONFIG}" "${repro_dir}/project_config.env"
if [[ -n "${AIND_CONFIG}" && -f "${AIND_CONFIG}" ]]; then
  cp "${AIND_CONFIG}" "${repro_dir}/aind_config.env"
fi
cp "${AIND_PARAMS_FILE}" "${repro_dir}/aind_params.json"
cp "${AIND_SLURM_CONFIG}" "${repro_dir}/aind_nextflow_slurm_greatlakes.config"
if [[ -f "${REPO_ROOT}/scripts/monitor_aind_run.sh" ]]; then
  cp "${REPO_ROOT}/scripts/monitor_aind_run.sh" "${repro_dir}/monitor_aind_run.sh"
fi
if [[ -f "${AIND_PIPELINE_ROOT}/pipeline/capsule_versions_custom.env" ]]; then
  cp "${AIND_PIPELINE_ROOT}/pipeline/capsule_versions_custom.env" "${repro_dir}/capsule_versions_custom.env"
else
  cp "${AIND_PIPELINE_ROOT}/pipeline/capsule_versions.env" "${repro_dir}/capsule_versions.env"
fi
cp "$0" "${repro_dir}/submitted_job.sbatch"
git -C "${REPO_ROOT}" rev-parse HEAD > "${repro_dir}/axion_repo_commit.txt"
git -C "${REPO_ROOT}" status --short > "${repro_dir}/axion_repo_status.txt"
git -C "${AIND_PIPELINE_ROOT}" rev-parse HEAD > "${repro_dir}/aind_pipeline_commit.txt"
git -C "${AIND_PIPELINE_ROOT}" status --short > "${repro_dir}/aind_pipeline_status.txt"
realpath "${NWB_FILE}" > "${repro_dir}/input_nwb.txt"
printf '%s\n' "${input_dir}" > "${repro_dir}/data_path.txt"
printf '%s\n' "${results_dir}" > "${repro_dir}/results_path.txt"

monitor_pid=""
cleanup_monitor() {
  if [[ -n "${monitor_pid}" ]] && kill -0 "${monitor_pid}" >/dev/null 2>&1; then
    kill "${monitor_pid}" >/dev/null 2>&1 || true
    wait "${monitor_pid}" >/dev/null 2>&1 || true
  fi
}
trap cleanup_monitor EXIT

if [[ "${AIND_ENABLE_MONITOR}" == "true" ]]; then
  monitor_log="${results_dir}/nextflow/monitor_${SLURM_JOB_ID:-manual}.log"
  AIND_MONITOR_INTERVAL_SECONDS="${AIND_MONITOR_INTERVAL_SECONDS}" \
    "${REPO_ROOT}/scripts/monitor_aind_run.sh" \
    "${results_dir}" \
    "${work_dir}" \
    "${SLURM_JOB_ID:-}" \
    > >(tee -a "${monitor_log}") 2>&1 &
  monitor_pid="$!"
  echo "AIND monitor started: pid=${monitor_pid}"
  echo "AIND monitor log: ${monitor_log}"
fi

DATA_PATH="${input_dir}" RESULTS_PATH="${results_dir}" "${nextflow_command[@]}"

echo "Axion AIND NWB job finished: $(date)"
