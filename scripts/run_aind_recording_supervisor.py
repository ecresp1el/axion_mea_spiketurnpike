#!/usr/bin/env python3
"""Supervise one Axion recording-level AIND run and submit sparse-well fallback."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_PROJECT_CONFIG = REPO_ROOT / "config" / "greatlakes_project.env"
DEFAULT_FALLBACK_LABEL = "low_activity_ks4_nt2_npcs2"
SPARSE_KS4_RE = re.compile(
    r"n_samples\s*=\s*\d+\s+should be\s+>=\s+n_clusters\s*=\s*\d+",
    re.IGNORECASE,
)
TERMINAL_SUCCESS = {"complete_success", "complete_success_with_fallback", "no_selected_wells"}
TERMINAL_WITH_FAILURES = {"complete_with_failures"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Poll the recording-level AIND batch collector, detect standard KS4 "
            "failures caused by sparse template-learning clips, submit the labeled "
            "low-activity fallback once, and keep recording-level status files."
        )
    )
    parser.add_argument("--recording-stem", required=True)
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--project-config", type=Path, default=DEFAULT_PROJECT_CONFIG)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to <project-root>/jobs/aind_recording_supervisors/<recording_stem>.",
    )
    parser.add_argument("--poll-seconds", type=int, default=120)
    parser.add_argument("--timeout-hours", type=float, default=8.0)
    parser.add_argument("--fallback-label", default=DEFAULT_FALLBACK_LABEL)
    parser.add_argument("--fallback-n-templates", type=int, default=2)
    parser.add_argument("--fallback-nearest-templates", type=int, default=2)
    parser.add_argument("--fallback-n-pcs", type=int, default=2)
    parser.add_argument(
        "--no-submit-fallback",
        action="store_true",
        help="Only report fallback candidates; do not submit fallback jobs.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one collector pass and candidate check, then exit.",
    )
    return parser.parse_args()


def q(value: str | Path) -> str:
    return shlex.quote(str(value))


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log(message: str, log_path: Path) -> None:
    line = f"[{now()}] {message}"
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run_command(command: list[str], log_path: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    log("$ " + " ".join(q(part) for part in command), log_path)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.stdout:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(result.stdout)
            if not result.stdout.endswith("\n"):
                handle.write("\n")
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n", flush=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit {result.returncode}: {' '.join(command)}")
    return result


def write_command(path: Path, command: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(" ".join(q(part) for part in command) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def run_collector(recording: str, project_root: Path, output_dir: Path, log_path: Path) -> dict[str, Any]:
    status_dir = output_dir / "collector"
    command = [
        "bash",
        str(REPO_ROOT / "scripts" / "summarize_aind_batch_status.sh"),
        "--recording-stem",
        recording,
        "--project-root",
        str(project_root),
        "--output-dir",
        str(status_dir),
    ]
    run_command(command, log_path)
    return read_json(status_dir / "workflow_status_latest.json")


def latest_status_csv(output_dir: Path) -> Path:
    return output_dir / "collector" / "workflow_status_latest.csv"


def read_job_log(project_root: Path, job_id: str) -> tuple[Path | None, str]:
    if not job_id:
        return None, ""
    log_root = project_root / "logs" / "aind"
    candidates = [
        log_root / f"axion-aind-nwb-{job_id}.out",
        log_root / f"axion-aind-nwb-{job_id}.err",
    ]
    texts = []
    first_path = None
    for path in candidates:
        if path.is_file():
            first_path = first_path or path
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
    return first_path, "\n".join(texts)


def classify_fallback_candidate(row: dict[str, str], project_root: Path) -> tuple[bool, str]:
    """Return true only for the isolated sparse-KS4 failure this fallback changes."""
    if row.get("derived_stage") != "aind_failed":
        return False, ""
    if row.get("fallback_label"):
        return False, "fallback_already_submitted"
    log_path, text = read_job_log(project_root, row.get("aind_job", ""))
    if SPARSE_KS4_RE.search(text):
        return True, f"sparse_kilosort4_template_learning_clip_count:{log_path}"
    if "n_templates" in text and "n_clusters" in text:
        return True, f"probable_sparse_kilosort4_template_learning:{log_path}"
    return False, f"not_sparse_fallback_pattern:{log_path or 'missing_aind_log'}"


def append_tsv(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.is_file()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row), delimiter="\t")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def submitted_fallback_wells(project_root: Path, recording: str, label: str) -> set[str]:
    submitted = project_root / "jobs" / "aind_fallbacks" / recording / label / "submitted_jobs.tsv"
    wells = set()
    if not submitted.is_file():
        return wells
    for line in submitted.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.search(r"well=(\S+)", line)
        if match:
            wells.add(match.group(1).upper())
    return wells


def prepare_and_submit_fallback(
    args: argparse.Namespace,
    wells: list[str],
    output_dir: Path,
    log_path: Path,
) -> None:
    project_root = args.project_root.expanduser().resolve()
    fallback_root = project_root / "jobs" / "aind_fallbacks" / args.recording_stem / args.fallback_label
    prepare_command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "prepare_aind_low_activity_fallback.py"),
        "--recording-stem",
        args.recording_stem,
        "--wells",
        ",".join(wells),
        "--project-root",
        str(project_root),
        "--project-config",
        str(args.project_config.expanduser().resolve()),
        "--label",
        args.fallback_label,
        "--n-templates",
        str(args.fallback_n_templates),
        "--nearest-templates",
        str(args.fallback_nearest_templates),
        "--n-pcs",
        str(args.fallback_n_pcs),
    ]
    write_command(output_dir / "last_prepare_fallback_command.txt", prepare_command)
    run_command(prepare_command, log_path)

    submit_script = fallback_root / f"submit_{args.fallback_label}.sh"
    submit_command = ["bash", str(submit_script)]
    write_command(output_dir / "last_submit_fallback_command.txt", submit_command)
    run_command(submit_command, log_path)
    append_tsv(
        output_dir / "submitted_fallback_batches.tsv",
        {
            "submitted_at": now(),
            "recording_stem": args.recording_stem,
            "fallback_label": args.fallback_label,
            "wells": ",".join(wells),
            "prepare_command_file": str(output_dir / "last_prepare_fallback_command.txt"),
            "submit_command_file": str(output_dir / "last_submit_fallback_command.txt"),
            "submitted_jobs": str(fallback_root / "submitted_jobs.tsv"),
        },
    )


def save_state(output_dir: Path, state: dict[str, Any]) -> None:
    (output_dir / "supervisor_state_latest.json").write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else project_root / "jobs" / "aind_recording_supervisors" / args.recording_stem
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "supervisor.log"
    log_path.write_text("", encoding="utf-8")

    invocation = [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]
    write_command(output_dir / "supervisor_command.txt", invocation)
    deadline = datetime.now() + timedelta(hours=args.timeout_hours)
    log(f"Supervisor started for recording={args.recording_stem}", log_path)
    log(f"Project root={project_root}", log_path)
    log(f"Output dir={output_dir}", log_path)

    while True:
        payload = run_collector(args.recording_stem, project_root, output_dir, log_path)
        summary = payload.get("summary", {}).get("recordings", {}).get(args.recording_stem, {})
        status = str(summary.get("recording_status", "missing"))
        wells = read_csv(latest_status_csv(output_dir))
        candidates: list[tuple[str, str]] = []
        already_submitted = submitted_fallback_wells(project_root, args.recording_stem, args.fallback_label)
        for row in wells:
            well = row.get("well", "").upper()
            is_candidate, reason = classify_fallback_candidate(row, project_root)
            if is_candidate and well not in already_submitted:
                candidates.append((well, reason))

        state = {
            "checked_at": now(),
            "recording_stem": args.recording_stem,
            "recording_status": status,
            "summary": summary,
            "fallback_label": args.fallback_label,
            "fallback_candidates": [{"well": well, "reason": reason} for well, reason in candidates],
            "already_submitted_fallback_wells": sorted(already_submitted),
            "collector_csv": str(latest_status_csv(output_dir)),
            "collector_json": str(output_dir / "collector" / "workflow_status_latest.json"),
            "collector_txt": str(output_dir / "collector" / "workflow_status_latest.txt"),
        }
        save_state(output_dir, state)
        log(
            "Status "
            f"{status}: selected={summary.get('selected_wells', '')}, "
            f"completed={summary.get('selected_wells_completed', '')}, "
            f"standard={summary.get('selected_wells_standard_completed', '')}, "
            f"fallback_completed={summary.get('selected_wells_fallback_completed', '')}, "
            f"running={summary.get('selected_wells_running', '')}, "
            f"failed={summary.get('selected_wells_failed', '')}, "
            f"new_fallback_candidates={[well for well, _ in candidates]}",
            log_path,
        )

        if candidates and not args.no_submit_fallback:
            wells_to_submit = sorted(well for well, _ in candidates)
            log(f"Submitting fallback for wells={wells_to_submit}", log_path)
            prepare_and_submit_fallback(args, wells_to_submit, output_dir, log_path)
            if args.once:
                break
            time.sleep(args.poll_seconds)
            continue

        if status in TERMINAL_SUCCESS:
            log(f"Supervisor complete with status={status}", log_path)
            break
        if status in TERMINAL_WITH_FAILURES and not candidates:
            log("Supervisor stopped: recording terminal with non-fallback failures.", log_path)
            sys.exit(2)
        if args.once:
            log("Supervisor once mode complete.", log_path)
            break
        if datetime.now() >= deadline:
            log("Supervisor timed out before terminal recording status.", log_path)
            sys.exit(124)
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
