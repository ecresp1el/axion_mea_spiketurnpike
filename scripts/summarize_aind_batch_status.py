#!/usr/bin/env python3
"""Summarize Axion-to-AIND batch progress across recordings and wells."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
FAILED_STATES = {"BOOT_FAIL", "CANCELLED", "DEADLINE", "FAILED", "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED", "TIMEOUT"}
ACTIVE_STATES = {"CONFIGURING", "COMPLETING", "PENDING", "RUNNING", "SUSPENDED"}
AXION_LOOKUPCHANNEL_PATTERNS = (
    "Index exceeds the number of array elements. Index must not exceed 2880",
    "BasicChannelArray/LookupChannel",
    "LookupChannelID",
)
JOB_LINE_RE = re.compile(
    r"well=(?P<well>\S+)\s+export_job=(?P<export_job>\S+)\s+"
    r"nwb_job=(?P<nwb_job>\S+)\s+spikeinterface_job=(?P<spikeinterface_job>\S+)\s+"
    r"aind_job=(?P<aind_job>\S+)"
)
FALLBACK_JOB_LINE_RE = re.compile(
    r"well=(?P<well>\S+)\s+aind_job=(?P<aind_job>\S+)\s+env_file=(?P<env_file>\S+)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write a live CSV/JSON/txt tally of selected wells, submitted jobs, "
            "Slurm states, and produced artifacts for Axion-to-AIND batches."
        )
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument(
        "--recording-stem",
        action="append",
        default=[],
        help="Recording stem to summarize. Can be repeated. Defaults to every batch with a well_batch_manifest.csv.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to <project-root>/jobs/aind_batch_status.",
    )
    parser.add_argument("--no-slurm", action="store_true", help="Do not call sacct/squeue.")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def optional_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return None if str(path) == "." else path


def path_exists(path: Path | None) -> bool:
    return bool(path and path.exists())


def file_size(path: Path | None) -> int:
    return path.stat().st_size if path_exists(path) and path.is_file() else 0


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_submitted_file(path: Path, recording_stem: str) -> list[dict[str, Any]]:
    attempts = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for match in JOB_LINE_RE.finditer(text):
        row = match.groupdict()
        row.update(
            {
                "recording_stem": recording_stem,
                "submitted_file": str(path),
                "submitted_file_name": path.name,
                "submitted_file_mtime": path.stat().st_mtime,
                "real_slurm_ids": all(str(row[key]).isdigit() for key in ["export_job", "nwb_job", "spikeinterface_job", "aind_job"]),
            }
        )
        attempts.append(row)
    return attempts


def parse_fallback_submitted_file(path: Path, recording_stem: str) -> list[dict[str, Any]]:
    attempts = []
    text = path.read_text(encoding="utf-8", errors="replace")
    fallback_label = path.parent.name
    for match in FALLBACK_JOB_LINE_RE.finditer(text):
        row = match.groupdict()
        manifest = path.parent / row["well"] / f"{recording_stem}_{row['well']}_{fallback_label}_manifest.json"
        manifest_data: dict[str, Any] = {}
        if manifest.is_file():
            try:
                manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest_data = {}
        row.update(
            {
                "recording_stem": recording_stem,
                "fallback_label": fallback_label,
                "submitted_file": str(path),
                "submitted_file_name": path.name,
                "submitted_file_mtime": path.stat().st_mtime,
                "real_slurm_ids": str(row["aind_job"]).isdigit(),
                "manifest_file": str(manifest) if manifest.is_file() else "",
                "fallback_reason": manifest_data.get("reason", ""),
                "fallback_results_dir": manifest_data.get("results_dir", ""),
                "fallback_work_dir": manifest_data.get("work_dir", ""),
                "n_templates": manifest_data.get("n_templates", ""),
                "nearest_templates": manifest_data.get("nearest_templates", ""),
                "n_pcs": manifest_data.get("n_pcs", ""),
            }
        )
        attempts.append(row)
    return attempts


def discover_batch_roots(project_root: Path, recording_stems: list[str]) -> list[Path]:
    batches_root = project_root / "jobs" / "aind_batches"
    if recording_stems:
        return [batches_root / stem for stem in recording_stems]
    return sorted(path.parent for path in batches_root.glob("*/well_batch_manifest.csv"))


def latest_attempts(attempts: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for attempt in attempts:
        if not attempt.get("real_slurm_ids"):
            continue
        key = (attempt["recording_stem"], attempt["well"])
        current = latest.get(key)
        current_sort = (
            current.get("submitted_file_mtime", 0) if current else -1,
            int(current.get("export_job", 0)) if current else -1,
        )
        new_sort = (attempt.get("submitted_file_mtime", 0), int(attempt.get("export_job", 0)))
        if current is None or new_sort > current_sort:
            latest[key] = attempt
    return latest


def latest_fallback_attempts(attempts: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for attempt in attempts:
        if not attempt.get("real_slurm_ids"):
            continue
        key = (attempt["recording_stem"], attempt["well"])
        current = latest.get(key)
        current_sort = (
            current.get("submitted_file_mtime", 0) if current else -1,
            int(current.get("aind_job", 0)) if current else -1,
        )
        new_sort = (attempt.get("submitted_file_mtime", 0), int(attempt.get("aind_job", 0)))
        if current is None or new_sort > current_sort:
            latest[key] = attempt
    return latest


def discover_fallback_attempts(project_root: Path, recording_stems: list[str]) -> list[dict[str, Any]]:
    fallbacks_root = project_root / "jobs" / "aind_fallbacks"
    stems = recording_stems or [path.name for path in discover_batch_roots(project_root, [])]
    attempts: list[dict[str, Any]] = []
    for stem in stems:
        recording_fallback_root = fallbacks_root / stem
        for submitted in sorted(recording_fallback_root.glob("*/submitted_jobs.tsv")):
            attempts.extend(parse_fallback_submitted_file(submitted, stem))
    return attempts


def query_sacct(job_ids: list[str]) -> dict[str, dict[str, str]]:
    if not job_ids or shutil.which("sacct") is None:
        return {}
    result = subprocess.run(
        [
            "sacct",
            "-j",
            ",".join(sorted(set(job_ids))),
            "--format=JobID,JobName%40,State,Elapsed,ExitCode",
            "--parsable2",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    states: dict[str, dict[str, str]] = {}
    rows = list(csv.DictReader(result.stdout.splitlines(), delimiter="|"))
    for row in rows:
        job_id = row.get("JobID", "")
        if not job_id or "." in job_id:
            continue
        states[job_id] = {
            "job_name": row.get("JobName", ""),
            "state": row.get("State", ""),
            "elapsed": row.get("Elapsed", ""),
            "exit_code": row.get("ExitCode", ""),
        }
    return states


def query_squeue(job_ids: list[str]) -> dict[str, dict[str, str]]:
    if not job_ids or shutil.which("squeue") is None:
        return {}
    result = subprocess.run(
        [
            "squeue",
            "-h",
            "-j",
            ",".join(sorted(set(job_ids))),
            "-o",
            "%i|%T|%M|%R",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    states = {}
    for line in result.stdout.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            states[parts[0]] = {"queue_state": parts[1], "queue_time": parts[2], "queue_reason": parts[3]}
    return states


def merge_job_state(job_id: str, sacct_states: dict[str, dict[str, str]], squeue_states: dict[str, dict[str, str]]) -> dict[str, str]:
    state = dict(sacct_states.get(job_id, {}))
    state.update(squeue_states.get(job_id, {}))
    if not state and not job_id:
        return {"state": ""}
    if not state:
        return {"state": "UNKNOWN"}
    if state.get("queue_state"):
        state["state"] = state["queue_state"]
    return state


def parse_trace(trace_path: Path) -> dict[str, Any]:
    if not trace_path.is_file():
        return {
            "trace_exists": False,
            "aind_trace_completed_tasks": 0,
            "aind_trace_failed_tasks": 0,
            "aind_trace_running_tasks": 0,
            "aind_trace_pending_tasks": 0,
            "aind_trace_nwb_units_completed": False,
        }
    rows = read_csv_tab(trace_path)
    statuses = Counter(row.get("status", "") for row in rows)
    names = {row.get("name", ""): row.get("status", "") for row in rows}
    normalized_names = {name.lower(): status for name, status in names.items()}
    return {
        "trace_exists": True,
        "aind_trace_completed_tasks": statuses.get("COMPLETED", 0),
        "aind_trace_failed_tasks": statuses.get("FAILED", 0),
        "aind_trace_running_tasks": statuses.get("RUNNING", 0),
        "aind_trace_pending_tasks": statuses.get("PENDING", 0),
        "aind_trace_nwb_units_completed": any(
            "nwb_units" in name and status == "COMPLETED"
            for name, status in normalized_names.items()
        ),
    }


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def export_failure_manifest(binary_file: Path | None) -> Path | None:
    if not binary_file:
        return None
    path = binary_file.parent / "binary_export_failure.json"
    return path if path.is_file() else None


def export_log_candidates(binary_file: Path | None, project_root: Path, export_job: str) -> list[Path]:
    if not export_job:
        return []
    candidates = []
    if binary_file:
        candidates.append(binary_file.parent / f"export_axion_well_binary_{export_job}.log")
    candidates.extend(
        [
            project_root / "logs" / f"axion-export-well-{export_job}.out",
            project_root / "logs" / f"axion-export-well-{export_job}.err",
        ]
    )
    seen = set()
    unique = []
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def classify_export_failure(binary_file: Path | None, project_root: Path, export_job: str) -> dict[str, str]:
    failure_json = export_failure_manifest(binary_file)
    failure_payload = read_json_object(failure_json) if failure_json else {}
    if failure_payload:
        failure_class = str(failure_payload.get("failure_class", "") or "")
        phase = str(failure_payload.get("phase", "") or "")
        message = str(failure_payload.get("error_message", "") or "")
        return {
            "export_failure_class": failure_class,
            "export_failure_reason": message or f"MATLAB export failed during {phase}.",
            "export_failure_phase": phase,
            "export_failure_json": str(failure_json),
            "export_failure_log": "",
        }
    for log_path in export_log_candidates(binary_file, project_root, export_job):
        if not log_path.is_file():
            continue
        text = log_path.read_text(encoding="utf-8", errors="replace")
        if all(pattern in text for pattern in AXION_LOOKUPCHANNEL_PATTERNS):
            return {
                "export_failure_class": "axion_axisfile_lookupchannel_open_failed",
                "export_failure_reason": "AxisFile(rawFile) failed during Axion channel lookup: index must not exceed 2880.",
                "export_failure_phase": "axisfile_open",
                "export_failure_json": "",
                "export_failure_log": str(log_path),
            }
    return {
        "export_failure_class": "",
        "export_failure_reason": "",
        "export_failure_phase": "",
        "export_failure_json": "",
        "export_failure_log": "",
    }


def read_csv_tab(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def slurm_state(row: dict[str, Any], prefix: str) -> str:
    return str(row.get(f"{prefix}_state", "") or "")


def state_is(row: dict[str, Any], prefix: str, state: str) -> bool:
    return slurm_state(row, prefix) == state


def state_in(row: dict[str, Any], prefix: str, states: set[str]) -> bool:
    return slurm_state(row, prefix) in states


def derive_stage(row: dict[str, Any]) -> str:
    if not row.get("selected"):
        return "not_selected"
    if not row.get("prepared"):
        return "selected_not_prepared"
    if row.get("aind_trace_nwb_units_completed"):
        return "aind_completed"

    if row.get("fallback_trace_nwb_units_completed"):
        return "fallback_completed"
    if int(row.get("fallback_trace_failed_tasks", 0) or 0) > 0 or state_in(row, "fallback_aind", FAILED_STATES):
        return "fallback_failed"
    if state_is(row, "fallback_aind", "RUNNING"):
        return "fallback_running"
    if state_is(row, "fallback_aind", "PENDING"):
        return "fallback_pending"

    if row.get("export_failure_class") == "axion_axisfile_lookupchannel_open_failed":
        return "ingestion_open_failed"
    if state_in(row, "export", FAILED_STATES):
        return "export_failed"
    if state_is(row, "export", "RUNNING"):
        return "export_running"
    if state_is(row, "export", "PENDING"):
        return "export_pending"
    if not row.get("binary_exists"):
        return "submitted_waiting_export" if row.get("latest_attempt_file") else "selected_not_submitted"

    if state_in(row, "nwb", FAILED_STATES):
        return "nwb_failed"
    if state_is(row, "nwb", "RUNNING"):
        return "nwb_running"
    if state_is(row, "nwb", "PENDING"):
        return "nwb_pending"
    if not row.get("nwb_exists"):
        return "export_completed"

    if state_in(row, "spikeinterface", FAILED_STATES):
        return "spikeinterface_failed"
    if state_is(row, "spikeinterface", "RUNNING"):
        return "spikeinterface_running"
    if state_is(row, "spikeinterface", "PENDING"):
        return "spikeinterface_pending"
    if not row.get("si_params_exists"):
        return "nwb_completed"

    if int(row.get("aind_trace_failed_tasks", 0) or 0) > 0 or state_in(row, "aind", FAILED_STATES):
        return "aind_failed"
    if state_is(row, "aind", "RUNNING"):
        return "aind_running"
    if state_is(row, "aind", "PENDING"):
        return "aind_pending"
    if row.get("trace_exists"):
        return "aind_trace_exists"
    return "si_prep_completed"


def summarize_recording(
    batch_root: Path,
    sacct_states: dict[str, dict[str, str]],
    squeue_states: dict[str, dict[str, str]],
    fallback_attempts: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    recording_stem = batch_root.name
    project_root = batch_root.parents[2]
    selection_rows = read_csv(batch_root / "selection" / "well_selection_manifest.csv")
    batch_rows = read_csv(batch_root / "well_batch_manifest.csv")
    batch_by_well = {row.get("well", ""): row for row in batch_rows}
    attempts = []
    for path in sorted(batch_root.glob("submitted*.tsv")) + sorted(batch_root.glob("*/retry*.tsv")):
        attempts.extend(parse_submitted_file(path, recording_stem))
    latest = latest_attempts(attempts)
    fallback_attempts = fallback_attempts or []
    latest_fallback = latest_fallback_attempts(fallback_attempts)
    rows = []
    for selected_row in selection_rows:
        well = selected_row.get("well", "")
        batch_row = batch_by_well.get(well, {})
        attempt = latest.get((recording_stem, well), {})
        binary_file = optional_path(batch_row.get("binary_file"))
        nwb_file = optional_path(batch_row.get("nwb_file"))
        spikeinterface_dir = optional_path(batch_row.get("spikeinterface_dir"))
        aind_results_dir = optional_path(batch_row.get("aind_results_dir"))
        trace = parse_trace(aind_results_dir / "nextflow" / "trace.txt") if aind_results_dir else parse_trace(Path(""))
        fallback_attempt = latest_fallback.get((recording_stem, well), {})
        fallback_results_dir = optional_path(fallback_attempt.get("fallback_results_dir"))
        fallback_trace = (
            parse_trace(fallback_results_dir / "nextflow" / "trace.txt")
            if fallback_results_dir
            else parse_trace(Path(""))
        )
        row: dict[str, Any] = {
            "recording_stem": recording_stem,
            "well": well,
            "selected": str(selected_row.get("selected", "")).lower() == "true",
            "selection_reason": selected_row.get("selection_reason", ""),
            "selection_rank": selected_row.get("selection_rank", ""),
            "total_spikes": selected_row.get("total_spikes", ""),
            "active_electrodes": selected_row.get("active_electrodes", ""),
            "prepared": bool(batch_row),
            "latest_attempt_file": attempt.get("submitted_file", ""),
            "attempt_count": sum(1 for item in attempts if item.get("well") == well),
            "export_job": attempt.get("export_job", ""),
            "nwb_job": attempt.get("nwb_job", ""),
            "spikeinterface_job": attempt.get("spikeinterface_job", ""),
            "aind_job": attempt.get("aind_job", ""),
            "binary_file": str(binary_file) if binary_file else "",
            "binary_exists": path_exists(binary_file),
            "binary_size_bytes": file_size(binary_file),
            "channel_mapping_exists": path_exists(binary_file.parent / "channel_mapping.csv") if binary_file else False,
            "binary_manifest_exists": path_exists(binary_file.parent / "binary_export_manifest.json") if binary_file else False,
            "nwb_file": str(nwb_file) if nwb_file else "",
            "nwb_exists": path_exists(nwb_file),
            "spikeinterface_dir": str(spikeinterface_dir) if spikeinterface_dir else "",
            "si_params_exists": any(spikeinterface_dir.glob("*_aind_spikeinterface_params.json")) if path_exists(spikeinterface_dir) else False,
            "aind_results_dir": str(aind_results_dir) if aind_results_dir else "",
            "fallback_attempt_count": sum(1 for item in fallback_attempts if item.get("well") == well),
            "fallback_label": fallback_attempt.get("fallback_label", ""),
            "fallback_reason": fallback_attempt.get("fallback_reason", ""),
            "fallback_aind_job": fallback_attempt.get("aind_job", ""),
            "fallback_env_file": fallback_attempt.get("env_file", ""),
            "fallback_manifest_file": fallback_attempt.get("manifest_file", ""),
            "fallback_results_dir": str(fallback_results_dir) if fallback_results_dir else "",
            "fallback_n_templates": fallback_attempt.get("n_templates", ""),
            "fallback_nearest_templates": fallback_attempt.get("nearest_templates", ""),
            "fallback_n_pcs": fallback_attempt.get("n_pcs", ""),
        }
        for prefix, job_key in [
            ("export", "export_job"),
            ("nwb", "nwb_job"),
            ("spikeinterface", "spikeinterface_job"),
            ("aind", "aind_job"),
        ]:
            state = merge_job_state(str(row.get(job_key, "")), sacct_states, squeue_states)
            row[f"{prefix}_state"] = state.get("state", "")
            row[f"{prefix}_elapsed"] = state.get("elapsed") or state.get("queue_time", "")
            row[f"{prefix}_exit_code"] = state.get("exit_code", "")
            row[f"{prefix}_queue_reason"] = state.get("queue_reason", "")
        if state_in(row, "export", FAILED_STATES):
            row.update(classify_export_failure(binary_file, project_root, str(row.get("export_job", ""))))
        else:
            row.update(
                {
                    "export_failure_class": "",
                    "export_failure_reason": "",
                    "export_failure_phase": "",
                    "export_failure_json": "",
                    "export_failure_log": "",
                }
            )
        row.update(trace)
        fallback_state = merge_job_state(str(row.get("fallback_aind_job", "")), sacct_states, squeue_states)
        row["fallback_aind_state"] = fallback_state.get("state", "")
        row["fallback_aind_elapsed"] = fallback_state.get("elapsed") or fallback_state.get("queue_time", "")
        row["fallback_aind_exit_code"] = fallback_state.get("exit_code", "")
        row["fallback_aind_queue_reason"] = fallback_state.get("queue_reason", "")
        for key, value in fallback_trace.items():
            if key == "trace_exists":
                fallback_key = "fallback_trace_exists"
            elif key.startswith("aind_trace_"):
                fallback_key = "fallback_trace_" + key[len("aind_trace_"):]
            else:
                fallback_key = f"fallback_{key}"
            row[fallback_key] = value
        row["derived_stage"] = derive_stage(row)
        rows.append(row)
    return rows, attempts


def build_summary(rows: list[dict[str, Any]], attempts: list[dict[str, Any]]) -> dict[str, Any]:
    by_recording: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["recording_stem"]].append(row)
    for recording, rec_rows in grouped.items():
        stages = Counter(row["derived_stage"] for row in rec_rows)
        current_failed = sum(1 for row in rec_rows if row["derived_stage"].endswith("_failed"))
        selected_rows = [row for row in rec_rows if row["selected"]]
        selected_completed = sum(1 for row in selected_rows if row["derived_stage"] in {"aind_completed", "fallback_completed"})
        selected_running = sum(1 for row in selected_rows if row["derived_stage"] in {"aind_running", "fallback_running"})
        selected_failed = sum(1 for row in selected_rows if row["derived_stage"].endswith("_failed"))
        selected_terminal = selected_completed + selected_failed
        fallback_completed = stages.get("fallback_completed", 0)
        fallback_running = stages.get("fallback_running", 0)
        fallback_failed = stages.get("fallback_failed", 0)
        if not selected_rows:
            recording_status = "no_selected_wells"
        elif selected_completed == len(selected_rows) and fallback_completed:
            recording_status = "complete_success_with_fallback"
        elif selected_completed == len(selected_rows):
            recording_status = "complete_success"
        elif selected_terminal == len(selected_rows):
            recording_status = "complete_with_failures"
        elif selected_running:
            recording_status = "running"
        else:
            recording_status = "incomplete"
        by_recording[recording] = {
            "recording_status": recording_status,
            "candidate_wells": len(rec_rows),
            "selected_wells": len(selected_rows),
            "prepared_wells": sum(1 for row in rec_rows if row["prepared"]),
            "submitted_wells_with_real_ids": sum(1 for row in rec_rows if row["export_job"]),
            "binary_exports_done": sum(1 for row in rec_rows if row["binary_exists"] and row["channel_mapping_exists"] and row["binary_manifest_exists"]),
            "nwb_exports_done": sum(1 for row in rec_rows if row["nwb_exists"]),
            "spikeinterface_prep_done": sum(1 for row in rec_rows if row["si_params_exists"]),
            "selected_wells_done_or_running": sum(1 for row in selected_rows if row["derived_stage"] in {"aind_completed", "aind_running", "fallback_completed", "fallback_running"}),
            "selected_wells_completed": selected_completed,
            "selected_wells_standard_completed": stages.get("aind_completed", 0),
            "selected_wells_fallback_completed": fallback_completed,
            "selected_wells_fallback_running": fallback_running,
            "selected_wells_fallback_failed": fallback_failed,
            "selected_wells_failed": selected_failed,
            "selected_wells_running": selected_running,
            "selected_wells_terminal": selected_terminal,
            "aind_completed": stages.get("aind_completed", 0),
            "fallback_completed": fallback_completed,
            "fallback_running": fallback_running,
            "fallback_failed": fallback_failed,
            "aind_running": stages.get("aind_running", 0),
            "current_failed_or_cancelled": current_failed,
            "historical_attempts_seen": sum(1 for item in attempts if item.get("recording_stem") == recording),
            "stage_counts": dict(stages),
        }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "recordings": by_recording,
        "total_rows": len(rows),
        "total_attempts": len(attempts),
    }


def write_text_summary(path: Path, summary: dict[str, Any]) -> None:
    lines = [f"Generated: {summary['generated_at']}", ""]
    for recording, rec in summary["recordings"].items():
        lines.append(f"Recording: {recording}")
        for key in [
            "recording_status",
            "candidate_wells",
            "selected_wells",
            "prepared_wells",
            "submitted_wells_with_real_ids",
            "binary_exports_done",
            "nwb_exports_done",
            "spikeinterface_prep_done",
            "selected_wells_done_or_running",
            "selected_wells_completed",
            "selected_wells_standard_completed",
            "selected_wells_fallback_completed",
            "selected_wells_fallback_running",
            "selected_wells_fallback_failed",
            "selected_wells_failed",
            "selected_wells_running",
            "selected_wells_terminal",
            "aind_running",
            "aind_completed",
            "fallback_completed",
            "fallback_running",
            "fallback_failed",
            "current_failed_or_cancelled",
            "historical_attempts_seen",
        ]:
            lines.append(f"  {key}: {rec[key]}")
        lines.append(f"  stage_counts: {json.dumps(rec['stage_counts'], sort_keys=True)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else project_root / "jobs" / "aind_batch_status"
    )
    batch_roots = discover_batch_roots(project_root, args.recording_stem)
    all_attempts = []
    for batch_root in batch_roots:
        for path in sorted(batch_root.glob("submitted*.tsv")) + sorted(batch_root.glob("*/retry*.tsv")):
            all_attempts.extend(parse_submitted_file(path, batch_root.name))
    fallback_attempts = discover_fallback_attempts(project_root, args.recording_stem)
    job_ids = []
    for attempt in all_attempts:
        if attempt.get("real_slurm_ids"):
            job_ids.extend([attempt["export_job"], attempt["nwb_job"], attempt["spikeinterface_job"], attempt["aind_job"]])
    for attempt in fallback_attempts:
        if attempt.get("real_slurm_ids"):
            job_ids.append(attempt["aind_job"])
    sacct_states = {} if args.no_slurm else query_sacct(job_ids)
    squeue_states = {} if args.no_slurm else query_squeue(job_ids)
    rows: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    for batch_root in batch_roots:
        rec_fallback_attempts = [item for item in fallback_attempts if item.get("recording_stem") == batch_root.name]
        rec_rows, rec_attempts = summarize_recording(batch_root, sacct_states, squeue_states, rec_fallback_attempts)
        rows.extend(rec_rows)
        attempts.extend(rec_attempts)
    summary = build_summary(rows, attempts)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"workflow_status_{timestamp}.csv"
    json_path = output_dir / f"workflow_status_{timestamp}.json"
    txt_path = output_dir / f"workflow_status_{timestamp}.txt"
    write_csv(csv_path, rows)
    json_path.write_text(
        json.dumps({"summary": summary, "wells": rows, "attempts": attempts, "fallback_attempts": fallback_attempts}, indent=2),
        encoding="utf-8",
    )
    write_text_summary(txt_path, summary)
    for source, latest_name in [
        (csv_path, "workflow_status_latest.csv"),
        (json_path, "workflow_status_latest.json"),
        (txt_path, "workflow_status_latest.txt"),
    ]:
        (output_dir / latest_name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    print((output_dir / "workflow_status_latest.txt").read_text(encoding="utf-8"))
    print(f"CSV: {output_dir / 'workflow_status_latest.csv'}")
    print(f"JSON: {output_dir / 'workflow_status_latest.json'}")


if __name__ == "__main__":
    main()
