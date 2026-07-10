#!/usr/bin/env python
"""Rank and submit repeated-recording stability examples with stronger ACGs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_SOURCE_DIR = (
    PROJECT_ROOT
    / "jobs"
    / "step1_nonlfp_th5_v5_ground_truth_latest"
    / "transient_plateing_1340150_recording_series_stability_20260709"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT
    / "jobs"
    / "step1_nonlfp_th5_v5_ground_truth_latest"
    / "transient_plateing_top_acg_examples_20260709"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--date-label", default="20260709_top_acg")
    parser.add_argument("--min-waveform-similarity", type=float, default=0.75)
    parser.add_argument("--max-fr-cv", type=float, default=0.90)
    parser.add_argument("--max-ptp-cv", type=float, default=1.20)
    parser.add_argument("--min-repeat-count", type=int, default=3)
    parser.add_argument("--sbatch-time", default="01:00:00")
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    repro_dir = output_dir / "repro"
    logs_dir = output_dir / "logs"
    repro_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    ranked = rank_candidates(args)
    if ranked.empty:
        raise RuntimeError("No candidate chains passed the ranking filters.")
    selected = ranked.head(args.top_n).copy()
    selected["candidate_rank"] = np.arange(1, len(selected) + 1)
    selected["figure_suffix"] = selected.apply(
        lambda row: f"rank{int(row['candidate_rank']):02d}_{row['well']}_u{str(row['unit_ids']).replace(';', '-')}",
        axis=1,
    )

    manifest_path = output_dir / "top_acg_candidate_manifest.csv"
    selected.to_csv(manifest_path, index=False)
    full_ranking_path = output_dir / "all_ranked_candidates.csv"
    ranked.to_csv(full_ranking_path, index=False)

    commands_path = repro_dir / "render_top_acg_commands.tsv"
    write_commands(commands_path, selected, output_dir, args.date_label)
    sbatch_path = repro_dir / "render_top_acg_examples.sbatch"
    write_sbatch(sbatch_path, commands_path, logs_dir, args.sbatch_time, len(selected))

    submission = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "manifest": str(manifest_path),
        "full_ranking": str(full_ranking_path),
        "commands": str(commands_path),
        "sbatch": str(sbatch_path),
        "submitted": False,
        "job_id": "",
    }
    if args.submit:
        result = subprocess.run(["sbatch", "--parsable", str(sbatch_path)], check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"sbatch failed: {result.stderr.strip()}")
        submission["submitted"] = True
        submission["job_id"] = result.stdout.strip()
    (output_dir / "submission.json").write_text(json.dumps(submission, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote manifest: {manifest_path}")
    print(f"Wrote commands: {commands_path}")
    print(f"Wrote sbatch: {sbatch_path}")
    if submission["submitted"]:
        print(f"Submitted job: {submission['job_id']}")
    else:
        print("Prepared only; rerun with --submit to submit.")
    return 0


def rank_candidates(args) -> pd.DataFrame:
    rows = []
    for path in sorted(args.source_dir.glob("transient_plateing_*_putative_same_channel_chains_*.csv")):
        well = path.name.split("_")[2]
        df = pd.read_csv(path)
        if df.empty:
            continue
        for record in df.to_dict("records"):
            repeats = str(record.get("repeats", "")).split(";")
            if len(repeats) < args.min_repeat_count:
                continue
            fr_values = parse_float_list(record.get("firing_rate_hz_values", ""))
            ptp_values = parse_float_list(record.get("best_channel_ptp_uV_values", ""))
            if fr_values.size < args.min_repeat_count or ptp_values.size < args.min_repeat_count:
                continue
            min_similarity = safe_float(record.get("min_abs_waveform_similarity"))
            mean_similarity = safe_float(record.get("mean_abs_waveform_similarity"))
            fr_cv = safe_float(record.get("firing_rate_hz_cv"))
            ptp_cv = safe_float(record.get("best_channel_ptp_uV_cv"))
            max_contam = safe_float(record.get("max_contam_pct"))
            if min_similarity < args.min_waveform_similarity or fr_cv > args.max_fr_cv or ptp_cv > args.max_ptp_cv:
                continue
            min_spikes_est = float(np.nanmin(fr_values * 600.0))
            mean_spikes_est = float(np.nanmean(fr_values * 600.0))
            acg_strength_score = float(
                np.log1p(max(min_spikes_est, 0.0))
                + 0.45 * np.log1p(max(mean_spikes_est, 0.0))
                + 1.5 * np.nan_to_num(min_similarity, nan=0.0)
                + 0.5 * np.nan_to_num(mean_similarity, nan=0.0)
                - 0.45 * np.nan_to_num(fr_cv, nan=2.0)
                - 0.25 * np.nan_to_num(ptp_cv, nan=2.0)
                - 0.02 * np.nan_to_num(max_contam, nan=20.0)
            )
            row = dict(record)
            row.update(
                {
                    "well": well,
                    "source_chain_table": str(path),
                    "min_fr_hz": float(np.nanmin(fr_values)),
                    "mean_fr_hz": float(np.nanmean(fr_values)),
                    "min_spikes_est_600s": min_spikes_est,
                    "mean_spikes_est_600s": mean_spikes_est,
                    "acg_strength_score": acg_strength_score,
                }
            )
            rows.append(row)
    ranked = pd.DataFrame(rows)
    if ranked.empty:
        return ranked
    return ranked.sort_values(
        ["acg_strength_score", "min_spikes_est_600s", "min_abs_waveform_similarity"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def write_commands(commands_path: Path, selected: pd.DataFrame, output_dir: Path, date_label: str) -> None:
    with commands_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["candidate_rank", "well", "unit_ids", "command"])
        for row in selected.to_dict("records"):
            cmd = [
                "python",
                "scripts/plot_recording_series_unit_stability.py",
                "--well",
                str(row["well"]),
                "--include-repeats",
                str(row["repeats"]).replace(";", ","),
                "--top-chains",
                "1",
                "--best-unit-only",
                "--matching-mode",
                "spatial_drift",
                "--max-best-channel-drift-um",
                "500",
                "--force-chain-unit-ids",
                str(row["unit_ids"]).replace(";", ","),
                "--output-dir",
                str(output_dir),
                "--date-label",
                date_label,
                "--figure-stem-suffix",
                str(row["figure_suffix"]),
                "--export-formats",
                "png,pdf,svg",
            ]
            writer.writerow([int(row["candidate_rank"]), row["well"], row["unit_ids"], " ".join(shlex.quote(item) for item in cmd)])


def write_sbatch(sbatch_path: Path, commands_path: Path, logs_dir: Path, sbatch_time: str, array_count: int) -> None:
    array_count = max(int(array_count), 1)
    template = f"""#!/usr/bin/env bash
#SBATCH --job-name=top_acg_examples
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time={sbatch_time}
#SBATCH --array=1-{array_count}%2
#SBATCH --output={logs_dir}/top_acg_%A_%a.out
#SBATCH --error={logs_dir}/top_acg_%A_%a.err

set -eo pipefail

REPO_ROOT={shlex.quote(str(REPO_ROOT))}
PROJECT_CONFIG="${{REPO_ROOT}}/config/greatlakes_project.env"
source "${{PROJECT_CONFIG}}"
source "${{CONDA_BASE}}/etc/profile.d/conda.sh"
conda activate "${{CONDA_ENV}}"

cd "${{REPO_ROOT}}"
COMMANDS={shlex.quote(str(commands_path))}
TASK_ID="${{SLURM_ARRAY_TASK_ID:-1}}"
COMMAND=$(awk -F '\\t' -v id="${{TASK_ID}}" 'NR>1 && $1==id {{print $4}}' "${{COMMANDS}}")
if [[ -z "${{COMMAND}}" ]]; then
  echo "No command for task ${{TASK_ID}}" >&2
  exit 2
fi
echo "Running task ${{TASK_ID}}"
echo "${{COMMAND}}"
eval "${{COMMAND}}"
"""
    sbatch_path.write_text(template, encoding="utf-8")
    sbatch_path.chmod(0o755)


def parse_float_list(value: object) -> np.ndarray:
    values = []
    for item in str(value).split(";"):
        try:
            values.append(float(item))
        except ValueError:
            pass
    return np.asarray(values, dtype=float)


def safe_float(value: object) -> float:
    try:
        value = float(value)
    except Exception:
        return math.nan
    return value


if __name__ == "__main__":
    raise SystemExit(main())
