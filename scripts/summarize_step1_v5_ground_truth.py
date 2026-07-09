#!/usr/bin/env python3
"""Build the canonical well-level ledger for the Step 1 non-LFP TH=5 v5 rerun."""

from __future__ import annotations

import argparse
import csv
import getpass
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_RUN_ROOT = PROJECT_ROOT / "jobs" / "step1_nonlfp_th5_v5_submit_20260708_221826"
DEFAULT_CONTINUATION_ROOT = (
    PROJECT_ROOT / "jobs" / "step1_nonlfp_th5_v5_lumos_aind_continue_20260708_234646"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "jobs" / "step1_nonlfp_th5_v5_ground_truth_latest"
DEFAULT_RESULTS_ROOT = PROJECT_ROOT / "results" / "aind"
DEFAULT_LOG_ROOT = PROJECT_ROOT / "logs" / "aind"
DEFAULT_SUBMITTED_WAVES = DEFAULT_OUTPUT_DIR / "submitted_step1_v5_ground_truth_waves.tsv"


SIXWELL_FALLBACK_WELLS = ["A1", "A2", "A3", "B1", "B2", "B3"]

SPARSE_FAILURE_PATTERNS = [
    (
        "n_samples_lt_clusters",
        re.compile(r"n_samples\s*=\s*\d+\s+should be\s+>=\s+n_clusters\s*=\s*\d+", re.I),
    ),
    (
        "empty_truncated_svd",
        re.compile(
            r"0 sample\(s\).*TruncatedSVD|minimum of 1 is required by TruncatedSVD",
            re.I | re.S,
        ),
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recordings-manifest",
        type=Path,
        default=DEFAULT_RUN_ROOT / "recordings_manifest_nonlfp_th5_v5_SUBMIT_TRUE.csv",
    )
    parser.add_argument(
        "--workflow-status-json",
        type=Path,
        default=DEFAULT_RUN_ROOT / "live_status" / "workflow_status_latest.json",
    )
    parser.add_argument(
        "--continuation-crosswalk",
        type=Path,
        default=DEFAULT_CONTINUATION_ROOT / "submitted_lumos_aind_wave_batch_crosswalk.tsv",
    )
    parser.add_argument(
        "--fallback-candidates",
        type=Path,
        default=DEFAULT_CONTINUATION_ROOT / "standard_failed_sparse_fallback_candidates.tsv",
    )
    parser.add_argument(
        "--submitted-waves",
        type=Path,
        default=DEFAULT_SUBMITTED_WAVES,
        help="Append-only key=value ledger written by submit_next_step1_v5_ground_truth_wave.py.",
    )
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def plate_map_wells(path_text: str) -> list[str]:
    path = Path(path_text)
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [row["well"].strip().upper() for row in csv.DictReader(handle) if row.get("well")]


def split_wells(value: str, plate_map: str) -> list[str]:
    text = (value or "").strip()
    if text.lower() == "all":
        wells = plate_map_wells(plate_map)
        return wells or SIXWELL_FALLBACK_WELLS
    return [item.strip().upper() for item in text.replace(";", ",").split(",") if item.strip()]


def norm_plate_family(value: str) -> str:
    text = (value or "").lower()
    if "cytoview" in text or "sixwell" in text or "6well" in text:
        return "cytoview_6well"
    if "lumos" in text or "48well" in text or "fortyeight" in text:
        return "lumos_48well"
    return value


def parse_key_value_line(line: str) -> dict[str, str]:
    row: dict[str, str] = {}
    for item in line.strip().split():
        if "=" in item:
            key, value = item.split("=", 1)
            row[key] = value
    return row


def read_key_value_ledger(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(parse_key_value_line(line))
    return rows


def squeue_states() -> dict[str, dict[str, str]]:
    output = subprocess.run(
        ["squeue", "-u", getpass.getuser(), "-h", "-o", "%i|%T|%j|%R"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    states: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            states[parts[0]] = {"state": parts[1], "job_name": parts[2], "reason": parts[3]}
    return states


def sacct_states(job_ids: list[str]) -> dict[str, dict[str, str]]:
    clean = sorted({job for job in job_ids if job})
    states: dict[str, dict[str, str]] = {}
    for start in range(0, len(clean), 300):
        chunk = clean[start : start + 300]
        output = subprocess.run(
            [
                "sacct",
                "-X",
                "-n",
                "-P",
                "-j",
                ",".join(chunk),
                "-o",
                "JobIDRaw,State,ExitCode,Elapsed,JobName",
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
        for line in output.splitlines():
            parts = line.split("|")
            if len(parts) >= 5:
                states[parts[0]] = {
                    "state": parts[1],
                    "exit_code": parts[2],
                    "elapsed": parts[3],
                    "job_name": parts[4],
                }
    return states


def merged_state(job_id: str, sacct: dict[str, dict[str, str]], squeue: dict[str, dict[str, str]]) -> str:
    if not job_id:
        return ""
    if job_id in squeue:
        return squeue[job_id]["state"]
    if job_id in sacct:
        row = sacct[job_id]
        exit_code = row.get("exit_code", "")
        return f"{row.get('state', '')}:{exit_code}" if exit_code else row.get("state", "")
    return "UNKNOWN"


def has_gui_analyzer(results_root: Path, recording: str, well: str) -> bool:
    return (results_root / recording / well / "postprocessed" / "block0_None_recording1.zarr").is_dir()


def trace_stage_summary(results_root: Path, recording: str, well: str) -> dict[str, str]:
    trace_path = results_root / recording / well / "nextflow" / "trace.txt"
    if not trace_path.is_file():
        return {"trace_exists": "false", "highest_completed_stage": "", "first_failed_stage": ""}
    stages: list[dict[str, str]] = []
    with trace_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            name = (row.get("name") or "").split()[0]
            if name:
                stages.append({"name": name, "status": row.get("status", ""), "exit": row.get("exit", "")})
    completed = [row["name"] for row in stages if row["status"] == "COMPLETED" and row["exit"] == "0"]
    failed = [row["name"] for row in stages if row["status"] == "FAILED"]
    return {
        "trace_exists": "true",
        "highest_completed_stage": completed[-1] if completed else "",
        "first_failed_stage": failed[0] if failed else "",
    }


def classify_sparse_failure(
    log_root: Path,
    results_root: Path,
    recording: str,
    well: str,
    job_id: str,
) -> tuple[str, str, str]:
    if not job_id:
        return "", "", ""
    paths = [
        log_root / f"axion-aind-nwb-{job_id}.out",
        log_root / f"axion-aind-nwb-{job_id}.err",
        results_root / recording / well / f"run_aind_nwb_well_{job_id}.log",
        results_root / recording / well / "nextflow" / "nextflow.log",
    ]
    texts: list[str] = []
    first_path = ""
    for path in paths:
        if path.is_file():
            first_path = first_path or str(path)
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
    text = "\n".join(texts)
    for failure_class, pattern in SPARSE_FAILURE_PATTERNS:
        match = pattern.search(text)
        if match:
            start = max(0, match.start() - 120)
            end = min(len(text), match.end() + 160)
            snippet = " ".join(text[start:end].split())[:500]
            return failure_class, first_path, snippet
    return "", first_path, ""


def infer_status(row: dict[str, str]) -> str:
    if row["gui_analyzer_ready"] == "true":
        return "gui_ready_standard"
    if row["fallback_candidate"] == "true":
        return "standard_failed_sparse_fallback_candidate"
    state = (
        row["continuation_aind_state"]
        or row["ground_truth_wave_aind_state"]
        or row["original_aind_state"]
    )
    if state == "RUNNING":
        return "running_standard"
    if state == "PENDING":
        return "pending_standard"
    if state.startswith("FAILED"):
        return "failed_standard_needs_classification"
    if state.startswith("COMPLETED") and row["gui_analyzer_ready"] != "true":
        return "completed_standard_no_gui_analyzer_yet"
    if (
        row["spikeinterface_job_state"].startswith("COMPLETED")
        and not row["continuation_aind_job"]
        and not row["ground_truth_wave_aind_job"]
    ):
        return "pickup_ready_not_continued"
    if row["export_job_state"].startswith("FAILED"):
        return "export_failed"
    if row["nwb_job_state"].startswith("FAILED"):
        return "nwb_failed"
    if row["spikeinterface_job_state"].startswith("FAILED"):
        return "spikeinterface_failed"
    return "not_ready_or_not_started"


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows = read_csv(args.recordings_manifest)
    expected: list[dict[str, str]] = []
    for rec_row in manifest_rows:
        wells = split_wells(rec_row.get("wells", ""), rec_row.get("plate_map", ""))
        for well in wells:
            expected.append(
                {
                    "recording": rec_row["recording_stem"],
                    "well": well,
                    "plate_family": norm_plate_family(rec_row.get("plate_family", "")),
                    "plate_type_name": rec_row.get("plate_type_name", ""),
                    "raw_variant": rec_row.get("raw_variant", ""),
                    "selection_mode": rec_row.get("selection_mode", ""),
                    "well_selection_policy": rec_row.get("well_selection_policy", ""),
                    "manifest_wells_field": rec_row.get("wells", ""),
                }
            )

    workflow = json.loads(args.workflow_status_json.read_text(encoding="utf-8"))
    attempts = {
        (row["recording_stem"], row["well"]): row
        for row in workflow.get("attempts", [])
        if row.get("recording_stem") and row.get("well")
    }
    continuation = {
        (row["recording"], row["well"]): row for row in read_tsv(args.continuation_crosswalk)
    }
    submitted_waves = {
        (row["recording"], row["well"]): row for row in read_key_value_ledger(args.submitted_waves)
    }
    fallback = {
        (row["recording"], row["well"]): row for row in read_tsv(args.fallback_candidates)
    }

    job_ids: list[str] = []
    for row in expected:
        attempt = attempts.get((row["recording"], row["well"]), {})
        cont = continuation.get((row["recording"], row["well"]), {})
        wave = submitted_waves.get((row["recording"], row["well"]), {})
        job_ids.extend(
            [
                attempt.get("export_job", ""),
                attempt.get("nwb_job", ""),
                attempt.get("spikeinterface_job", ""),
                attempt.get("aind_job", ""),
                cont.get("aind_job", ""),
                wave.get("aind_job", ""),
            ]
        )

    live = squeue_states()
    accounting = sacct_states(job_ids)

    output_rows: list[dict[str, str]] = []
    for row in expected:
        key = (row["recording"], row["well"])
        attempt = attempts.get(key, {})
        cont = continuation.get(key, {})
        wave = submitted_waves.get(key, {})
        fb = fallback.get(key, {})
        trace = trace_stage_summary(args.results_root, row["recording"], row["well"])
        continuation_state = merged_state(cont.get("aind_job", ""), accounting, live)
        wave_state = merged_state(wave.get("aind_job", ""), accounting, live)
        original_state = merged_state(attempt.get("aind_job", ""), accounting, live)
        effective_job_for_failure = (
            cont.get("aind_job", "") or wave.get("aind_job", "") or attempt.get("aind_job", "")
        )
        sparse_failure_class = fb.get("failure_class", "")
        sparse_log_hint = fb.get("log_hint", "")
        sparse_error_snippet = fb.get("error_snippet", "")
        if not sparse_failure_class and (
            continuation_state.startswith("FAILED")
            or wave_state.startswith("FAILED")
            or original_state.startswith("FAILED")
        ):
            sparse_failure_class, sparse_log_hint, sparse_error_snippet = classify_sparse_failure(
                args.log_root,
                args.results_root,
                row["recording"],
                row["well"],
                effective_job_for_failure,
            )
        out = {
            **row,
            "source_recordings_manifest": str(args.recordings_manifest),
            "original_export_job": attempt.get("export_job", ""),
            "original_nwb_job": attempt.get("nwb_job", ""),
            "original_spikeinterface_job": attempt.get("spikeinterface_job", ""),
            "original_aind_job": attempt.get("aind_job", ""),
            "export_job_state": merged_state(attempt.get("export_job", ""), accounting, live),
            "nwb_job_state": merged_state(attempt.get("nwb_job", ""), accounting, live),
            "spikeinterface_job_state": merged_state(attempt.get("spikeinterface_job", ""), accounting, live),
            "original_aind_state": original_state,
            "continuation_batch": cont.get("batch", ""),
            "continuation_aind_job": cont.get("aind_job", ""),
            "continuation_aind_state": continuation_state,
            "ground_truth_wave_label": wave.get("wave_label", ""),
            "ground_truth_wave_submitted_at": wave.get("submitted_at", ""),
            "ground_truth_wave_aind_job": wave.get("aind_job", ""),
            "ground_truth_wave_aind_state": wave_state,
            "fallback_candidate": "true" if sparse_failure_class else "false",
            "fallback_failure_class": sparse_failure_class,
            "recommended_fallback_label": "low_activity_ks4_nt2_npcs2" if sparse_failure_class else "",
            "recommended_n_templates": "2" if sparse_failure_class else "",
            "recommended_nearest_templates": "2" if sparse_failure_class else "",
            "recommended_n_pcs": "2" if sparse_failure_class else "",
            "failure_log_hint": sparse_log_hint,
            "failure_error_snippet": sparse_error_snippet,
            "gui_analyzer_ready": "true" if has_gui_analyzer(args.results_root, row["recording"], row["well"]) else "false",
            **trace,
        }
        out["ground_truth_status"] = infer_status(out)
        output_rows.append(out)

    fieldnames = list(output_rows[0])
    csv_path = args.output_dir / "step1_v5_well_ground_truth.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_recordings_manifest": str(args.recordings_manifest),
        "rows": len(output_rows),
        "plate_family_counts": Counter(row["plate_family"] for row in output_rows),
        "ground_truth_status_counts": Counter(row["ground_truth_status"] for row in output_rows),
        "continuation_batch_counts": Counter(row["continuation_batch"] or "none" for row in output_rows),
        "ground_truth_wave_label_counts": Counter(
            row["ground_truth_wave_label"] or "none" for row in output_rows
        ),
        "fallback_candidate_count": sum(row["fallback_candidate"] == "true" for row in output_rows),
        "gui_ready_count": sum(row["gui_analyzer_ready"] == "true" for row in output_rows),
        "output_csv": str(csv_path),
    }
    serializable = json.loads(json.dumps(summary, default=dict))
    json_path = args.output_dir / "step1_v5_ground_truth_summary.json"
    json_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    txt_path = args.output_dir / "step1_v5_ground_truth_summary.txt"
    txt_path.write_text(
        "\n".join(
            [
                f"Generated: {serializable['generated_at']}",
                f"Rows: {serializable['rows']}",
                f"Plate family counts: {serializable['plate_family_counts']}",
                f"Ground truth status counts: {serializable['ground_truth_status_counts']}",
                f"Continuation batch counts: {serializable['continuation_batch_counts']}",
                f"Ground truth wave counts: {serializable['ground_truth_wave_label_counts']}",
                f"Fallback candidate count: {serializable['fallback_candidate_count']}",
                f"GUI-ready count: {serializable['gui_ready_count']}",
                f"CSV: {csv_path}",
                f"JSON: {json_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fallback_rows = [row for row in output_rows if row["fallback_candidate"] == "true"]
    fallback_path = args.output_dir / "step1_v5_sparse_fallback_candidates.csv"
    with fallback_path.open("w", newline="", encoding="utf-8") as handle:
        field_subset = [
            "recording",
            "well",
            "plate_family",
            "continuation_batch",
            "continuation_aind_job",
            "continuation_aind_state",
            "ground_truth_wave_label",
            "ground_truth_wave_aind_job",
            "ground_truth_wave_aind_state",
            "original_aind_job",
            "original_aind_state",
            "fallback_failure_class",
            "recommended_fallback_label",
            "recommended_n_templates",
            "recommended_nearest_templates",
            "recommended_n_pcs",
            "failure_log_hint",
            "failure_error_snippet",
        ]
        writer = csv.DictWriter(handle, fieldnames=field_subset, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(fallback_rows)
    print(txt_path.read_text(encoding="utf-8"))
    print(f"Sparse fallback candidates: {fallback_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
