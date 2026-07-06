#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"
source "${PROJECT_CONFIG}"

if [[ -n "${AIND_OPENJDK_MODULE}" ]]; then
  module load "${AIND_OPENJDK_MODULE}"
fi

mkdir -p "$(dirname "${AIND_NEXTFLOW_BIN}")" "${PROJECT_ROOT}/tools" "${PROJECT_ROOT}/scratch/aind_nextflow_install"
tmp_dir="$(mktemp -d "${PROJECT_ROOT}/scratch/aind_nextflow_install/tmp.XXXXXX")"
trap 'rm -rf "${tmp_dir}"' EXIT

cd "${tmp_dir}"
curl -fsSL https://get.nextflow.io -o get_nextflow.sh
if [[ -n "${AIND_NEXTFLOW_VERSION}" ]]; then
  NXF_VER="${AIND_NEXTFLOW_VERSION}" bash get_nextflow.sh
else
  bash get_nextflow.sh
fi

if [[ -f nextflow ]]; then
  mv nextflow "${AIND_NEXTFLOW_BIN}"
else
  if [[ -n "${AIND_NEXTFLOW_VERSION}" ]]; then
    nextflow_jar="$(
      find "${NXF_HOME:-${HOME}/.nextflow}/framework/${AIND_NEXTFLOW_VERSION}" \
        -type f -name 'nextflow-*-one.jar' 2>/dev/null | sort -V | tail -n 1
    )"
  else
    nextflow_jar="$(
      find "${NXF_HOME:-${HOME}/.nextflow}/framework" \
        -type f -name 'nextflow-*-one.jar' 2>/dev/null | sort -V | tail -n 1
    )"
  fi
  if [[ -z "${nextflow_jar}" ]]; then
    echo "ERROR: Nextflow installer did not create a launcher or framework jar." >&2
    exit 1
  fi
  {
    echo "#!/usr/bin/env bash"
    echo "exec java \${NXF_OPTS:-} -jar ${nextflow_jar@Q} \"\$@\""
  } > "${AIND_NEXTFLOW_BIN}"
fi
chmod +x "${AIND_NEXTFLOW_BIN}"

"${AIND_NEXTFLOW_BIN}" -version
