#!/usr/bin/env python3
"""Prepare a labeled AIND/Kilosort4 fallback route for sparse Axion wells."""

from __future__ import annotations

import argparse
import csv
import json
import shlex
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
PROJECT_CONFIG = REPO_ROOT / "config" / "greatlakes_project.env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create per-well low-activity AIND params/env files and a submit "
            "script. This route is for wells that reached Kilosort4 but failed "
            "because template initialization had fewer clips than n_templates."
        )
    )
    parser.add_argument("--recording-stem", required=True)
    parser.add_argument("--wells", required=True, help="Comma-separated well IDs.")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--project-config", type=Path, default=PROJECT_CONFIG)
    parser.add_argument("--label", default="low_activity_ks4")
    parser.add_argument("--n-templates", type=int, default=2)
    parser.add_argument("--nearest-templates", type=int, default=2)
    parser.add_argument(
        "--n-pcs",
        type=int,
        default=None,
        help=(
            "Kilosort4 PCA/template dimension for the sparse fallback. "
            "Defaults to --n-templates because reducing n_templates alone "
            "left n_pcs=6 and produced KS4 shape mismatches."
        ),
    )
    parser.add_argument("--th-universal", type=float, default=None)
    parser.add_argument("--th-learned", type=float, default=None)
    return parser.parse_args()


def q(value: str | Path) -> str:
    return shlex.quote(str(value))


def update_params(params: dict, args: argparse.Namespace) -> dict:
    updated = json.loads(json.dumps(params))
    sorter = updated["spikesorting"]["kilosort4"]["sorter"]
    n_pcs = args.n_pcs if args.n_pcs is not None else args.n_templates

    # Sparse wells can fail standard KS4 before sorting because the sorter finds
    # fewer template-learning clips than the standard n_templates=6. The first
    # fallback attempt changed only n_templates/nearest_templates and then KS4
    # failed later with shapes like (..., 2) -> (..., 6). Keep n_pcs coupled to
    # the fallback template count so all related template/PCA dimensions move
    # together. This is intentionally scoped to labeled fallback params only.
    sorter["n_templates"] = args.n_templates
    sorter["nearest_templates"] = args.nearest_templates
    sorter["n_pcs"] = n_pcs
    if args.th_universal is not None:
        sorter["Th_universal"] = args.th_universal
    if args.th_learned is not None:
        sorter["Th_learned"] = args.th_learned
    return updated


def main() -> None:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    recording = args.recording_stem
    wells = [well.strip().upper() for well in args.wells.split(",") if well.strip()]
    if not wells:
        raise SystemExit("No wells requested.")

    fallback_root = project_root / "jobs" / "aind_fallbacks" / recording / args.label
    results_root = project_root / "results" / f"aind_{args.label}"
    work_root = project_root / "scratch" / f"aind_nextflow_{args.label}"
    nxf_home_root = project_root / "scratch" / f"aind_nextflow_home_{args.label}"
    rows = []
    submit_lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"cd {q(REPO_ROOT)}",
        f"submitted={q(fallback_root / 'submitted_jobs.tsv')}",
        ": > \"${submitted}\"",
        "",
        "submit_one() {",
        "  local well=\"$1\"",
        "  local env_file=\"$2\"",
        "  local job_id",
        f"  job_id=\"$(env PROJECT_CONFIG={q(args.project_config)} AIND_CONFIG=\"${{env_file}}\" sbatch --parsable {q(REPO_ROOT / 'slurm/run_aind_nwb_well.sbatch')})\"",
        "  printf 'well=%s aind_job=%s env_file=%s\\n' \"${well}\" \"${job_id}\" \"${env_file}\" | tee -a \"${submitted}\"",
        "}",
        "",
    ]

    for well in wells:
        source_dir = project_root / "jobs" / "aind" / recording / well / "spikeinterface"
        matches = sorted(source_dir.glob("*_aind_spikeinterface_params.json"))
        if len(matches) != 1:
            raise SystemExit(f"Expected one params file for {well} under {source_dir}; found {len(matches)}")
        source_params = matches[0]
        original = json.loads(source_params.read_text(encoding="utf-8"))
        params = update_params(original, args)

        well_dir = fallback_root / well
        well_dir.mkdir(parents=True, exist_ok=True)
        params_path = well_dir / f"{recording}_{well}_{args.label}_params.json"
        env_path = well_dir / f"run_aind_{args.label}.env"
        manifest_path = well_dir / f"{recording}_{well}_{args.label}_manifest.json"
        params_path.write_text(json.dumps(params, indent=2), encoding="utf-8")

        source_env = source_dir / "run_aind_spikeinterface.env"
        env_lines = [
            "#!/usr/bin/env bash",
            f'source "${{PROJECT_CONFIG:-{PROJECT_CONFIG}}}"',
            f'export RECORDING_STEM="{recording}"',
            f'export WELL="{well}"',
            f'export NWB_FILE="${{PROJECT_ROOT}}/data/interim/nwb/{recording}/{well}/{recording}_{well}.nwb"',
            'export AIND_RUNMODE="${AIND_RUNMODE:-full}"',
            'export AIND_SORTER="${AIND_SORTER:-kilosort4}"',
            f'export AIND_PARAMS_FILE="{params_path}"',
            'export AIND_ALLOW_OVERWRITE="true"',
            'export AIND_RESUME="false"',
            f'export AIND_RESULTS_ROOT="{results_root}"',
            f'export AIND_WORK_ROOT="{work_root}"',
            f'export AIND_NXF_HOME_ROOT="{nxf_home_root}"',
        ]
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        env_path.chmod(0o755)

        manifest = {
            "recording_stem": recording,
            "well": well,
            "fallback_label": args.label,
            "reason": "standard_kilosort4_failed_template_initialization_low_clip_count",
            "source_params": str(source_params),
            "source_env": str(source_env),
            "params_file": str(params_path),
            "env_file": str(env_path),
            "results_dir": str(results_root / recording / well),
            "work_dir": str(work_root / recording / well),
            "nxf_home": str(nxf_home_root / recording / well),
            "n_templates": args.n_templates,
            "nearest_templates": args.nearest_templates,
            "n_pcs": args.n_pcs if args.n_pcs is not None else args.n_templates,
            "fallback_param_reason": (
                "n_templates, nearest_templates, and n_pcs are changed together "
                "because low_activity_ks4_nt2 changed n_templates alone and KS4 "
                "later failed with a shape mismatch against the remaining "
                "standard n_pcs=6 dimension."
            ),
            "th_universal": args.th_universal,
            "th_learned": args.th_learned,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        rows.append(manifest)
        submit_lines.append(f"submit_one {q(well)} {q(env_path)}")

    fallback_root.mkdir(parents=True, exist_ok=True)
    submit_script = fallback_root / f"submit_{args.label}.sh"
    submit_script.write_text("\n".join(submit_lines) + "\n", encoding="utf-8")
    submit_script.chmod(0o755)
    manifest_csv = fallback_root / f"{args.label}_manifest.csv"
    with manifest_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (fallback_root / f"{args.label}_manifest.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    print(f"Prepared low-activity fallback for {len(rows)} wells")
    print(f"Submit script: {submit_script}")
    print(f"Manifest: {manifest_csv}")
    print(f"Results root: {results_root}")


if __name__ == "__main__":
    main()
