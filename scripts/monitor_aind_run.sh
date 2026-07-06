#!/usr/bin/env bash
# Periodically print useful state for an AIND Nextflow run.

set -uo pipefail

results_dir="${1:?results_dir is required}"
work_dir="${2:?work_dir is required}"
parent_job_id="${3:-}"
interval_seconds="${AIND_MONITOR_INTERVAL_SECONDS:-60}"
trace_file="${results_dir}/nextflow/trace.txt"
monitor_start_epoch="$(date +%s)"

newest_file_since_start() {
  local root="$1"
  local name="$2"
  [[ -d "${root}" ]] || return 1
  find "${root}" -type f -name "${name}" -printf '%T@ %p\n' 2>/dev/null \
    | awk -v min_time="${monitor_start_epoch}" '$1 >= min_time' \
    | sort -n \
    | tail -n 1 \
    | cut -d' ' -f2-
}

print_file_tail() {
  local label="$1"
  local file="$2"
  local lines="${3:-30}"
  if [[ -n "${file}" && -f "${file}" ]]; then
    echo "[monitor] ${label}: ${file}"
    tail -n "${lines}" "${file}" 2>/dev/null || true
  else
    echo "[monitor] ${label}: not available yet"
  fi
}

echo "[monitor] started at $(date '+%F %T')"
echo "[monitor] results_dir=${results_dir}"
echo "[monitor] work_dir=${work_dir}"
echo "[monitor] parent_job_id=${parent_job_id:-unknown}"
echo "[monitor] interval_seconds=${interval_seconds}"
echo "[monitor] only tailing task logs modified after $(date -d "@${monitor_start_epoch}" '+%F %T')"

while true; do
  echo
  echo "========== AIND monitor $(date '+%F %T') =========="

  if [[ -n "${parent_job_id}" ]] && command -v squeue >/dev/null 2>&1; then
    echo "[monitor] Slurm jobs for parent ${parent_job_id}:"
    squeue -j "${parent_job_id}" -o "%.18i %.9P %.32j %.8u %.2t %.10M %.10l %.6D %R" 2>/dev/null || true
    echo "[monitor] Recent AIND/Nextflow child jobs for ${USER:-unknown}:"
    squeue -u "${USER:-}" -o "%.18i %.9P %.32j %.8u %.2t %.10M %.10l %.6D %R" 2>/dev/null \
      | awk 'NR == 1 || /nf-|aind|axion|kilosort|spikesort|postprocessing|curation|visualization|quality|collector/' \
      || true
  fi

  echo "[monitor] Nextflow trace tail:"
  if [[ -s "${trace_file}" ]]; then
    tail -n 25 "${trace_file}" 2>/dev/null || true
  else
    echo "[monitor] trace not written yet: ${trace_file}"
  fi

  newest_out="$(newest_file_since_start "${work_dir}" ".command.out" || true)"
  newest_err="$(newest_file_since_start "${work_dir}" ".command.err" || true)"
  newest_log="$(newest_file_since_start "${work_dir}" ".command.log" || true)"
  print_file_tail "new .command.out since monitor start" "${newest_out}" 35
  if [[ -n "${newest_err}" && -s "${newest_err}" ]]; then
    print_file_tail "new non-empty .command.err since monitor start" "${newest_err}" 35
  else
    echo "[monitor] new .command.err since monitor start: no non-empty stderr yet"
  fi
  print_file_tail "new .command.log since monitor start" "${newest_log}" 20

  echo "[monitor] Recent capsule result locations:"
  if [[ -d "${work_dir}" ]]; then
    find "${work_dir}" -maxdepth 6 -path '*/capsule/results*' -printf '%TY-%Tm-%Td %TH:%TM %.10s %p\n' 2>/dev/null \
      | sort \
      | tail -n 20 \
      || true
  else
    echo "[monitor] work directory does not exist yet"
  fi

  echo "[monitor] Final results top level:"
  if [[ -d "${results_dir}" ]]; then
    find "${results_dir}" -mindepth 1 -maxdepth 2 -printf '%TY-%Tm-%Td %TH:%TM %.10s %p\n' 2>/dev/null \
      | sort \
      | tail -n 30 \
      || true
  else
    echo "[monitor] results directory does not exist yet"
  fi

  sleep "${interval_seconds}"
done
