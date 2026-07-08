#!/usr/bin/env python
"""Prepare a UnitRefine/Bombcell recovery canary from the latest AIND ledger."""

from __future__ import annotations

import argparse
import csv
import json
import shlex
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
AIND_PIPELINE_ROOT = Path("/home/elcrespo/Desktop/githubprojects/aind-ephys-pipeline")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def q(value: str | Path) -> str:
    return shlex.quote(str(value))


def build_recovery_params(template: Path, output: Path) -> None:
    params = json.loads(template.read_text(encoding="utf-8"))
    recovery = {
        "postprocessing": params["postprocessing"],
        "curation": params["curation"],
    }
    output.write_text(json.dumps(recovery, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger-csv",
        default=PROJECT_ROOT / "jobs" / "aind_unified_status_latest" / "unified_well_status.csv",
        type=Path,
    )
    parser.add_argument("--recording", default="")
    parser.add_argument("--well", default="")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--submit", action="store_true")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = args.output_root or PROJECT_ROOT / "jobs" / f"aind_unit_classification_recovery_{timestamp}"
    output_root.mkdir(parents=True, exist_ok=False)

    rows = read_rows(args.ledger_csv)
    candidates = [
        row
        for row in rows
        if row.get("well_status") == "complete_nwb_units"
        and row.get("trace_exists") == "True"
        and row.get("unit_metrics_status") == "ok"
    ]
    if args.recording:
        candidates = [row for row in candidates if row.get("recording") == args.recording]
    if args.well:
        candidates = [row for row in candidates if row.get("well") == args.well]
    if not candidates:
        raise SystemExit("No completed well candidate matched the requested filters.")

    selected = sorted(candidates, key=lambda row: (row.get("lane", ""), row.get("recording", ""), row.get("well", "")))[0]
    source_results_dir = PROJECT_ROOT / "results" / "aind" / selected["recording"] / selected["well"]
    recovery_output_dir = (
        PROJECT_ROOT
        / "results"
        / "aind_unit_classification_recovery"
        / output_root.name
        / selected["recording"]
        / selected["well"]
    )
    params_json = output_root / "recovery_params.json"
    build_recovery_params(AIND_PIPELINE_ROOT / "pipeline" / "default_params.json", params_json)

    manifest = output_root / "canary_manifest.csv"
    fieldnames = [
        "recording",
        "well",
        "lane",
        "plate_family",
        "source_results_dir",
        "recovery_output_dir",
        "recovery_params_json",
        "source_ledger_csv",
    ]
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "recording": selected["recording"],
                "well": selected["well"],
                "lane": selected["lane"],
                "plate_family": selected["plate_family"],
                "source_results_dir": str(source_results_dir),
                "recovery_output_dir": str(recovery_output_dir),
                "recovery_params_json": str(params_json),
                "source_ledger_csv": str(args.ledger_csv),
            }
        )

    submit_script = output_root / "submit_canary.sh"
    submit_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"cd {q(REPO_ROOT)}",
                (
                    "job_id=$(env "
                    f"PROJECT_CONFIG={q(REPO_ROOT / 'config' / 'greatlakes_project.env')} "
                    f"RECORDING_STEM={q(selected['recording'])} "
                    f"WELL={q(selected['well'])} "
                    f"SOURCE_RESULTS_DIR={q(source_results_dir)} "
                    f"RECOVERY_OUTPUT_DIR={q(recovery_output_dir)} "
                    f"RECOVERY_PARAMS_JSON={q(params_json)} "
                    f"sbatch --parsable {q(REPO_ROOT / 'slurm' / 'run_aind_unit_classification_recovery.sbatch')})"
                ),
                f"printf 'recording=%s well=%s recovery_job=%s output_dir=%s\\n' {q(selected['recording'])} {q(selected['well'])} \"${{job_id}}\" {q(recovery_output_dir)} | tee -a {q(output_root / 'submitted_canary.tsv')}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    submit_script.chmod(0o755)

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "output_root": str(output_root),
        "candidate_count": len(candidates),
        "selected": {
            "recording": selected["recording"],
            "well": selected["well"],
            "lane": selected["lane"],
            "plate_family": selected["plate_family"],
        },
        "source_results_dir": str(source_results_dir),
        "recovery_output_dir": str(recovery_output_dir),
        "recovery_params_json": str(params_json),
        "manifest": str(manifest),
        "submit_script": str(submit_script),
    }
    (output_root / "prepare_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))

    if args.submit:
        raise SystemExit("Prepared canary only. Run submit_canary.sh after reviewing the manifest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
