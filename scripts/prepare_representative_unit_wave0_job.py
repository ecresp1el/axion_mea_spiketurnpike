#!/usr/bin/env python
"""Prepare and optionally submit the Wave 0 representative-unit index job."""

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
PROJECT_CONFIG = REPO_ROOT / "config" / "greatlakes_project.env"
SBATCH_TEMPLATE = REPO_ROOT / "slurm" / "run_representative_analysis.sbatch"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--date-label", default="20260709")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--wave-label", default="")
    parser.add_argument("--sbatch-time", default="00:30:00")
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    wave_label = args.wave_label or f"representative_wave0_index_{timestamp}"
    job_dir = args.job_dir.expanduser().resolve()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else job_dir / f"representative_units_{args.date_label}_wave0_{timestamp}"
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
                    "python scripts/build_representative_unit_index.py "
                    f"--job-dir {shell_quote(job_dir)} "
                    f"--date-label {shell_quote(args.date_label)} "
                    f"--output-dir {shell_quote(output_dir)}"
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
    submit_file = repro_dir / "submit_command.sh"
    submit_file.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\ncd "
        + shell_quote(REPO_ROOT)
        + "\n"
        + " ".join(shell_quote(part) for part in submit_command)
        + "\n",
        encoding="utf-8",
    )
    submit_file.chmod(0o755)

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "wave_label": wave_label,
        "date_label": args.date_label,
        "job_dir": str(job_dir),
        "output_dir": str(output_dir),
        "repro_dir": str(repro_dir),
        "command_file": str(command_file),
        "submitted_sbatch": str(submitted_sbatch),
        "submit_command": submit_command,
        "submit": bool(args.submit),
        "expected_outputs": [
            str(output_dir / f"representative_unit_index_{args.date_label}.csv"),
            str(output_dir / f"representative_unit_index_{args.date_label}_summary.csv"),
            str(output_dir / f"wave0_reconciliation_table_{args.date_label}.csv"),
            str(output_dir / f"wave0_missing_assets_{args.date_label}.csv"),
            str(output_dir / f"wave0_denominator_summary_{args.date_label}.csv"),
            str(output_dir / f"representative_unit_index_{args.date_label}_provenance.json"),
        ],
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
        submitted_tsv = output_dir / "submitted_jobs.tsv"
        submitted_tsv.write_text(
            "submitted_at\twave_label\tjob_id\toutput_dir\tcommand_file\tsbatch\n"
            f"{datetime.now().isoformat(timespec='seconds')}\t{wave_label}\t{job_id}\t{output_dir}\t{command_file}\t{submitted_sbatch}\n",
            encoding="utf-8",
        )
        print(f"submitted_job_id={job_id}")

    (output_dir / "wave0_prepare_manifest.json").write_text(
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
