#!/usr/bin/env python3
"""Prepare and optionally submit the unified CytoView RS/FS/activity figure job."""

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
JOB_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=JOB_ROOT)
    parser.add_argument("--activity-dir", type=Path, default=None)
    parser.add_argument("--alignment-dir", type=Path, default=None)
    parser.add_argument("--fs-cutoff-ms", type=float, default=0.50)
    parser.add_argument("--export-formats", default="png,pdf,svg")
    parser.add_argument("--submit", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        args.output_root.expanduser().resolve()
        / f"cytoview_unified_rsfs_activity_figure_20260710_{timestamp}"
    )
    repro_dir = output_dir / "repro"
    logs_dir = output_dir / "logs"
    repro_dir.mkdir(parents=True, exist_ok=False)
    logs_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "python",
        "scripts/build_cytoview_unified_rsfs_activity_figure.py",
        "--output-dir",
        str(output_dir),
        "--fs-cutoff-ms",
        str(args.fs_cutoff_ms),
        "--export-formats",
        args.export_formats,
    ]
    if args.activity_dir is not None:
        command.extend(["--activity-dir", str(args.activity_dir.expanduser().resolve())])
    if args.alignment_dir is not None:
        command.extend(["--alignment-dir", str(args.alignment_dir.expanduser().resolve())])
    command_text = " ".join(shlex.quote(item) for item in command)

    (repro_dir / "python_command.sh").write_text(command_text + "\n", encoding="utf-8")
    shutil.copy2(PROJECT_CONFIG, repro_dir / "project_config.env")
    shutil.copy2(
        REPO_ROOT / "scripts" / "build_cytoview_unified_rsfs_activity_figure.py",
        repro_dir / "build_cytoview_unified_rsfs_activity_figure.py",
    )
    sbatch_path = repro_dir / "submitted_job.sbatch"
    sbatch_path.write_text(
        f"""#!/usr/bin/env bash
#SBATCH --job-name=cytoview_unified_fig
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output={logs_dir}/unified_figure_%j.out
#SBATCH --error={logs_dir}/unified_figure_%j.err

set -eo pipefail
REPO_ROOT={shlex.quote(str(REPO_ROOT))}
source "${{REPO_ROOT}}/config/greatlakes_project.env"
source "${{CONDA_BASE}}/etc/profile.d/conda.sh"
conda activate "${{CONDA_ENV}}"
cd "${{REPO_ROOT}}"
{command_text}
""",
        encoding="utf-8",
    )
    sbatch_path.chmod(0o755)

    submission: dict[str, object] = {
        "prepared_at": datetime.now().isoformat(timespec="seconds"),
        "submitted": False,
        "job_id": "",
        "output_dir": str(output_dir),
        "python_command": command_text,
        "sbatch": str(sbatch_path),
    }
    if args.submit:
        result = subprocess.run(
            ["sbatch", "--parsable", str(sbatch_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        submission["submitted"] = True
        submission["job_id"] = result.stdout.strip().split(";")[0]
        submission["submitted_at"] = datetime.now().isoformat(timespec="seconds")
    (output_dir / "submission.json").write_text(
        json.dumps(submission, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Output directory: {output_dir}")
    print(f"Submitted: {submission['submitted']}")
    print(f"Job ID: {submission['job_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
