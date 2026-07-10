#!/usr/bin/env python3
"""Prepare and optionally submit the CytoView SUA spontaneous-activity job."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_CONFIG = REPO_ROOT / "config" / "greatlakes_project.env"
DEFAULT_JOB_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_UNIT_METRICS = DEFAULT_JOB_ROOT / "cytoview_dorsal_ventral_step1_20260709_unit_metrics.csv"
DEFAULT_ALIGNED_METRICS = (
    DEFAULT_JOB_ROOT
    / "waveform_alignment_feature_audit_20260709_cytoview"
    / "waveform_alignment_feature_audit_20260709_paired_unit_metrics.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_JOB_ROOT)
    parser.add_argument("--unit-metrics-csv", type=Path, default=DEFAULT_UNIT_METRICS)
    parser.add_argument("--aligned-metrics-csv", type=Path, default=DEFAULT_ALIGNED_METRICS)
    parser.add_argument("--date-label", default="20260710")
    parser.add_argument("--fs-cutoff-ms", type=float, default=0.50)
    parser.add_argument("--min-template-ptp-uv", type=float, default=None)
    parser.add_argument("--max-contam-pct", type=float, default=None)
    parser.add_argument("--max-isi-lt-2ms-fraction", type=float, default=None)
    parser.add_argument("--max-isi-ms", type=float, default=100.0)
    parser.add_argument("--min-spikes-per-burst", type=int, default=3)
    parser.add_argument("--min-burst-duration-ms", type=float, default=100.0)
    parser.add_argument("--inverse-isi-gaussian-sigma-ms", type=float, default=50.0)
    parser.add_argument("--inverse-isi-evaluation-bin-ms", type=float, default=1.0)
    parser.add_argument("--min-spikes-for-smoothed-rate", type=int, default=30)
    parser.add_argument("--export-formats", default="png,pdf,svg")
    parser.add_argument("--sbatch-time", default="01:00:00")
    parser.add_argument("--submit", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    template_suffix = (
        f"_template_ptp_ge{args.min_template_ptp_uv:g}uV"
        if args.min_template_ptp_uv is not None
        else ""
    )
    contamination_suffix = (
        f"_contam_le{args.max_contam_pct:g}pct" if args.max_contam_pct is not None else ""
    )
    refractory_suffix = (
        f"_isi2ms_le{100 * args.max_isi_lt_2ms_fraction:g}pct"
        if args.max_isi_lt_2ms_fraction is not None
        else ""
    )
    output_dir = (
        args.output_root.expanduser().resolve()
        / (
            f"cytoview_dv_sua_spontaneous_activity_{args.date_label}{template_suffix}"
            f"{contamination_suffix}{refractory_suffix}_{timestamp}"
        )
    )
    repro_dir = output_dir / "repro"
    logs_dir = output_dir / "logs"
    repro_dir.mkdir(parents=True, exist_ok=False)
    logs_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "python",
        "scripts/build_cytoview_dv_sua_spontaneous_activity.py",
        "--unit-metrics-csv",
        str(args.unit_metrics_csv.expanduser().resolve()),
        "--aligned-metrics-csv",
        str(args.aligned_metrics_csv.expanduser().resolve()),
        "--output-dir",
        str(output_dir),
        "--date-label",
        args.date_label,
        "--kslabel",
        "good",
        "--fs-cutoff-ms",
        str(args.fs_cutoff_ms),
        "--max-isi-ms",
        str(args.max_isi_ms),
        "--min-spikes-per-burst",
        str(args.min_spikes_per_burst),
        "--min-burst-duration-ms",
        str(args.min_burst_duration_ms),
        "--inverse-isi-gaussian-sigma-ms",
        str(args.inverse_isi_gaussian_sigma_ms),
        "--inverse-isi-evaluation-bin-ms",
        str(args.inverse_isi_evaluation_bin_ms),
        "--min-spikes-for-smoothed-rate",
        str(args.min_spikes_for_smoothed_rate),
        "--export-formats",
        args.export_formats,
    ]
    if args.min_template_ptp_uv is not None:
        command.extend(["--min-template-ptp-uv", str(args.min_template_ptp_uv)])
    if args.max_contam_pct is not None:
        command.extend(["--max-contam-pct", str(args.max_contam_pct)])
    if args.max_isi_lt_2ms_fraction is not None:
        command.extend(
            ["--max-isi-lt-2ms-fraction", str(args.max_isi_lt_2ms_fraction)]
        )
    command_text = " ".join(shlex.quote(item) for item in command)
    python_command = repro_dir / "python_command.sh"
    python_command.write_text(command_text + "\n", encoding="utf-8")
    python_command.chmod(0o755)
    shutil.copy2(PROJECT_CONFIG, repro_dir / "project_config.env")
    shutil.copy2(
        REPO_ROOT / "scripts" / "build_cytoview_dv_sua_spontaneous_activity.py",
        repro_dir / "build_cytoview_dv_sua_spontaneous_activity.py",
    )
    shutil.copy2(
        REPO_ROOT / "src" / "axion_mea" / "spontaneous_activity.py",
        repro_dir / "spontaneous_activity.py",
    )

    sbatch_path = repro_dir / "submitted_job.sbatch"
    sbatch_path.write_text(
        f"""#!/usr/bin/env bash
#SBATCH --job-name=cytoview_sua_E
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time={args.sbatch_time}
#SBATCH --output={logs_dir}/cytoview_sua_E_%j.out
#SBATCH --error={logs_dir}/cytoview_sua_E_%j.err

set -eo pipefail

REPO_ROOT={shlex.quote(str(REPO_ROOT))}
source "${{REPO_ROOT}}/config/greatlakes_project.env"
source "${{CONDA_BASE}}/etc/profile.d/conda.sh"
conda activate "${{CONDA_ENV}}"
cd "${{REPO_ROOT}}"

echo "Started: $(date)"
echo "Host: $(hostname)"
echo "SLURM_JOB_ID=${{SLURM_JOB_ID:-}}"
{command_text}
echo "Finished: $(date)"
""",
        encoding="utf-8",
    )
    sbatch_path.chmod(0o755)

    submit_command = repro_dir / "submit_command.sh"
    submit_command.write_text(f"sbatch --parsable {shlex.quote(str(sbatch_path))}\n", encoding="utf-8")
    submit_command.chmod(0o755)

    submission = {
        "prepared_at": datetime.now().isoformat(timespec="seconds"),
        "submitted": False,
        "job_id": "",
        "output_dir": str(output_dir),
        "sbatch": str(sbatch_path),
        "python_command": command_text,
        "recording_version_policy": (
            "all spike-bearing versions separate; exclude only explicit raw_variant LFP/low-frequency-only versions"
        ),
        "one_well_equals_one_organoid": True,
        "kslabel": "good",
        "aligned_fs_cutoff_ms": float(args.fs_cutoff_ms),
        "unit_quality_filters": {
            "metric": "template peak-to-peak amplitude on best channel",
            "minimum_uV_inclusive": args.min_template_ptp_uv,
            "maximum_ContamPct_inclusive": args.max_contam_pct,
            "maximum_isi_lt_2ms_fraction_inclusive": args.max_isi_lt_2ms_fraction,
        },
        "burst_parameters": {
            "max_isi_ms": float(args.max_isi_ms),
            "min_spikes": int(args.min_spikes_per_burst),
            "min_duration_ms": float(args.min_burst_duration_ms),
        },
        "inverse_isi_gaussian_firing_rate": {
            "min_spikes": int(args.min_spikes_for_smoothed_rate),
            "gaussian_sigma_ms": float(args.inverse_isi_gaussian_sigma_ms),
            "evaluation_bin_ms": float(args.inverse_isi_evaluation_bin_ms),
            "legacy_count_duration_rate_retained": True,
        },
    }
    if args.submit:
        result = subprocess.run(
            ["sbatch", "--parsable", str(sbatch_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            submission["submit_error"] = result.stderr.strip()
            (output_dir / "submission.json").write_text(
                json.dumps(submission, indent=2) + "\n", encoding="utf-8"
            )
            raise RuntimeError(f"sbatch failed: {result.stderr.strip()}")
        job_id = result.stdout.strip().split(";")[0]
        submission["submitted"] = True
        submission["job_id"] = job_id
        submission["submitted_at"] = datetime.now().isoformat(timespec="seconds")
        (output_dir / "submitted_jobs.tsv").write_text(
            "submitted_at\tjob_id\toutput_dir\tsbatch\n"
            f"{submission['submitted_at']}\t{job_id}\t{output_dir}\t{sbatch_path}\n",
            encoding="utf-8",
        )

    (output_dir / "submission.json").write_text(
        json.dumps(submission, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Output directory: {output_dir}")
    print(f"Sbatch: {sbatch_path}")
    print(f"Submitted: {submission['submitted']}")
    if submission["job_id"]:
        print(f"Job ID: {submission['job_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
