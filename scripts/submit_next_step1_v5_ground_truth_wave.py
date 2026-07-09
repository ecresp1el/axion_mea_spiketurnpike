#!/usr/bin/env python3
"""Submit the next controlled AIND wave from the Step 1 v5 ground-truth ledger."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
GROUND_TRUTH_DIR = PROJECT_ROOT / "jobs" / "step1_nonlfp_th5_v5_ground_truth_latest"
DEFAULT_LEDGER = GROUND_TRUTH_DIR / "step1_v5_well_ground_truth.csv"
DEFAULT_SUBMITTED = GROUND_TRUTH_DIR / "submitted_step1_v5_ground_truth_waves.tsv"
PROJECT_CONFIG = REPO_ROOT / "config" / "greatlakes_project.env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--submitted", type=Path, default=DEFAULT_SUBMITTED)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--status",
        default="pickup_ready_not_continued",
        help="Comma-separated ground_truth_status values to submit.",
    )
    parser.add_argument(
        "--plate-family",
        default="",
        help="Optional exact plate_family filter, e.g. cytoview_6well or lumos_48well.",
    )
    parser.add_argument(
        "--wave-label",
        default="",
        help="Optional label written to the submit ledger. Defaults to timestamp label.",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Actually call sbatch. Without this flag, only print the planned wave.",
    )
    parser.add_argument(
        "--allow-resubmit",
        action="store_true",
        help="Allow rows already present in the submitted ledger to be submitted again.",
    )
    parser.add_argument(
        "--skip-submitted-wave-prefix",
        action="append",
        default=[],
        help=(
            "Even with --allow-resubmit, skip rows already submitted under a wave_label "
            "starting with this prefix. May be passed more than once."
        ),
    )
    parser.add_argument(
        "--sbatch-time",
        default="",
        help="Optional parent-wrapper walltime override passed to sbatch, e.g. 12:00:00.",
    )
    return parser.parse_args()


def already_submitted(path: Path, wave_prefixes: list[str] | None = None) -> set[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    if not path.is_file():
        return seen
    prefixes = tuple(prefix for prefix in (wave_prefixes or []) if prefix)
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.startswith("submitted_at\t"):
            continue
        row = dict(part.split("=", 1) for part in line.split() if "=" in part)
        if prefixes and not row.get("wave_label", "").startswith(prefixes):
            continue
        recording = row.get("recording", "")
        well = row.get("well", "")
        if recording and well:
            seen.add((recording, well))
    return seen


def aind_env_for(row: dict[str, str]) -> Path:
    return (
        PROJECT_ROOT
        / "jobs"
        / "aind"
        / row["recording"]
        / row["well"]
        / "spikeinterface"
        / "run_aind_spikeinterface.env"
    )


def main() -> int:
    args = parse_args()
    statuses = {item.strip() for item in args.status.split(",") if item.strip()}
    rows = list(csv.DictReader(args.ledger.open(newline="", encoding="utf-8")))
    submitted = already_submitted(args.submitted)
    skip_submitted = already_submitted(args.submitted, args.skip_submitted_wave_prefix)

    candidates: list[dict[str, str]] = []
    for row in rows:
        key = (row["recording"], row["well"])
        if key in skip_submitted:
            continue
        if key in submitted and not args.allow_resubmit:
            continue
        if row.get("ground_truth_status") not in statuses:
            continue
        if args.plate_family and row.get("plate_family") != args.plate_family:
            continue
        env_path = aind_env_for(row)
        if not env_path.is_file():
            continue
        candidates.append({**row, "aind_env": str(env_path)})
        if len(candidates) >= args.limit:
            break

    wave_label = args.wave_label or f"step1_v5_ground_truth_wave_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"wave_label={wave_label}")
    print(f"submit={args.submit}")
    print(f"planned_count={len(candidates)}")
    for row in candidates:
        print(f"{row['plate_family']} {row['recording']} {row['well']} {row['aind_env']}")

    if not args.submit:
        return 0

    args.submitted.parent.mkdir(parents=True, exist_ok=True)
    submitted_now: list[tuple[dict[str, str], str]] = []
    for row in candidates:
        command = [
            "sbatch",
            "--parsable",
            f"--export=PROJECT_CONFIG={PROJECT_CONFIG},AIND_CONFIG={row['aind_env']}",
        ]
        if args.sbatch_time:
            command.append(f"--time={args.sbatch_time}")
        command.append(str(REPO_ROOT / "slurm" / "run_aind_nwb_well.sbatch"))
        result = subprocess.run(command, cwd=REPO_ROOT, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            raise RuntimeError(f"sbatch failed for {row['recording']} {row['well']}: {result.stderr}")
        job_id = result.stdout.strip().split(";")[0]
        submitted_now.append((row, job_id))

    with args.submitted.open("a", encoding="utf-8") as handle:
        for row, job_id in submitted_now:
            handle.write(
                "submitted_at={submitted_at} wave_label={wave_label} plate_family={plate_family} "
                "recording={recording} well={well} aind_job={aind_job} aind_env={aind_env} "
                "source_ledger={source_ledger}\n".format(
                    submitted_at=dt.datetime.now().isoformat(),
                    wave_label=wave_label,
                    plate_family=row["plate_family"],
                    recording=row["recording"],
                    well=row["well"],
                    aind_job=job_id,
                    aind_env=row["aind_env"],
                    source_ledger=args.ledger,
                )
            )

    print(f"submitted_new={len(submitted_now)}")
    for _, job_id in submitted_now:
        print(job_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
