#!/usr/bin/env python3
"""Prepare and submit the cross-platform FS representative comparison."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
JOB_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=JOB_ROOT)
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_root.expanduser().resolve() / f"cross_platform_fs_representative_comparison_20260710_{timestamp}"
    repro = output_dir / "repro"
    logs = output_dir / "logs"
    repro.mkdir(parents=True, exist_ok=False)
    logs.mkdir(parents=True, exist_ok=True)
    command = ["python", "scripts/plot_cross_platform_fs_representative_comparison.py", "--output-dir", str(output_dir)]
    command_text = " ".join(shlex.quote(value) for value in command)
    (repro / "python_command.sh").write_text(command_text + "\n", encoding="utf-8")
    shutil.copy2(REPO_ROOT / "config" / "greatlakes_project.env", repro / "project_config.env")
    shutil.copy2(REPO_ROOT / "scripts" / "plot_cross_platform_fs_representative_comparison.py", repro / "plot_cross_platform_fs_representative_comparison.py")
    sbatch = repro / "submitted_job.sbatch"
    sbatch.write_text(
        f"""#!/usr/bin/env bash
#SBATCH --job-name=fs_cross_platform
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output={logs}/comparison_%j.out
#SBATCH --error={logs}/comparison_%j.err

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
    sbatch.chmod(0o755)
    submission = {"submitted": False, "job_id": "", "output_dir": str(output_dir), "command": command_text}
    if args.submit:
        result = subprocess.run(["sbatch", "--parsable", str(sbatch)], capture_output=True, text=True, check=False)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        submission.update({"submitted": True, "job_id": result.stdout.strip().split(";")[0]})
    (output_dir / "submission.json").write_text(json.dumps(submission, indent=2) + "\n", encoding="utf-8")
    print(f"Output directory: {output_dir}")
    print(f"Job ID: {submission['job_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
