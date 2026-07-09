#!/usr/bin/env python
"""Prepare and optionally submit representative-figure selection manifests."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_JOB_DIR = PROJECT_ROOT / "jobs" / "step1_nonlfp_th5_v5_ground_truth_latest"
DEFAULT_SCORE_ROOT = DEFAULT_JOB_DIR / "representative_units_20260709_abc_scoring_20260709_172908"
PROJECT_CONFIG = REPO_ROOT / "config" / "greatlakes_project.env"
SBATCH_TEMPLATE = REPO_ROOT / "slurm" / "run_representative_analysis.sbatch"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-label", default="20260709")
    parser.add_argument("--score-root", type=Path, default=DEFAULT_SCORE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--sbatch-time", default="00:20:00")
    parser.add_argument("--top-n-stability-per-group", type=int, default=6)
    parser.add_argument("--top-n-pairs-per-group", type=int, default=6)
    parser.add_argument("--top-n-wells-per-group", type=int, default=4)
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else DEFAULT_JOB_DIR / f"representative_units_{args.date_label}_final_selection_{timestamp}"
    )
    repro_dir = output_dir / "repro"
    output_dir.mkdir(parents=True, exist_ok=False)
    repro_dir.mkdir(parents=True, exist_ok=True)

    command_file = repro_dir / "python_command.sh"
    command_file.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"cd {shell_quote(REPO_ROOT)}",
                f"source {shell_quote(PROJECT_CONFIG)}",
                'source "${CONDA_BASE}/etc/profile.d/conda.sh"',
                "set +u",
                'conda activate "${CONDA_ENV}"',
                "set -u",
                (
                    "python scripts/build_representative_figure_selection_manifests.py "
                    f"--score-root {shell_quote(args.score_root.expanduser().resolve())} "
                    f"--date-label {shell_quote(args.date_label)} "
                    f"--output-dir {shell_quote(output_dir)} "
                    f"--top-n-stability-per-group {args.top_n_stability_per_group} "
                    f"--top-n-pairs-per-group {args.top_n_pairs_per_group} "
                    f"--top-n-wells-per-group {args.top_n_wells_per_group}"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )
    command_file.chmod(0o755)

    submitted_sbatch = repro_dir / "submitted_job.sbatch"
    shutil.copy2(SBATCH_TEMPLATE, submitted_sbatch)
    shutil.copy2(PROJECT_CONFIG, repro_dir / "project_config.env")

    submit_command = [
        "sbatch",
        "--parsable",
        f"--time={args.sbatch_time}",
        f"--export=PROJECT_CONFIG={PROJECT_CONFIG},REPRESENTATIVE_COMMAND_FILE={command_file},REPRESENTATIVE_OUTPUT_DIR={output_dir}",
        str(submitted_sbatch),
    ]
    (repro_dir / "submit_command.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\ncd "
        + shell_quote(REPO_ROOT)
        + "\n"
        + " ".join(shell_quote(part) for part in submit_command)
        + "\n",
        encoding="utf-8",
    )
    (repro_dir / "submit_command.sh").chmod(0o755)

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "date_label": args.date_label,
        "score_root": str(args.score_root.expanduser().resolve()),
        "output_dir": str(output_dir),
        "repro_dir": str(repro_dir),
        "command_file": str(command_file),
        "submitted_sbatch": str(submitted_sbatch),
        "submit_command": submit_command,
        "top_n_stability_per_group": args.top_n_stability_per_group,
        "top_n_pairs_per_group": args.top_n_pairs_per_group,
        "top_n_wells_per_group": args.top_n_wells_per_group,
        "submit": bool(args.submit),
    }

    if args.submit:
        result = subprocess.run(
            submit_command,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"sbatch failed: {result.stderr}")
        job_id = result.stdout.strip().split(";")[0]
        manifest["job_id"] = job_id
        (output_dir / "submitted_jobs.tsv").write_text(
            "submitted_at\twave_label\tjob_id\toutput_dir\tcommand_file\tsbatch\n"
            f"{datetime.now().isoformat(timespec='seconds')}\trepresentative_final_selection_{timestamp}\t{job_id}\t{output_dir}\t{command_file}\t{submitted_sbatch}\n",
            encoding="utf-8",
        )
        print(f"submitted_job_id={job_id}")

    (output_dir / "final_selection_prepare_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, default=str))
    return 0


def shell_quote(value: object) -> str:
    import shlex

    return shlex.quote(str(value))


if __name__ == "__main__":
    raise SystemExit(main())
