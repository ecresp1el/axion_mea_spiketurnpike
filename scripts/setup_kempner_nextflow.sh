#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_CONFIG="${PROJECT_CONFIG:-${REPO_ROOT}/config/greatlakes_project.env}"
source "${PROJECT_CONFIG}"

if [[ -n "${KEMPNER_OPENJDK_MODULE}" ]]; then
  module load "${KEMPNER_OPENJDK_MODULE}"
fi

mkdir -p "$(dirname "${KEMPNER_NEXTFLOW_BIN}")"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

cd "${tmp_dir}"
curl -fsSL https://get.nextflow.io -o get_nextflow.sh
NXF_VER="${KEMPNER_NEXTFLOW_VERSION}" bash get_nextflow.sh || true
if [[ -f nextflow ]]; then
  mv nextflow "${KEMPNER_NEXTFLOW_BIN}"
else
  nextflow_jar="$(find "${NXF_HOME:-${HOME}/.nextflow}/framework/${KEMPNER_NEXTFLOW_VERSION}" -type f -name 'nextflow-*-one.jar' | sort -V | tail -n 1)"
  if [[ -z "${nextflow_jar}" ]]; then
    echo "ERROR: Nextflow installer did not create a launcher or framework jar." >&2
    exit 1
  fi
  {
    echo "#!/usr/bin/env bash"
    echo "exec java \${NXF_OPTS:-} -jar ${nextflow_jar@Q} \"\$@\""
  } > "${KEMPNER_NEXTFLOW_BIN}"
fi
chmod +x "${KEMPNER_NEXTFLOW_BIN}"

"${KEMPNER_NEXTFLOW_BIN}" -version
