#!/usr/bin/env python3
"""Prepare per-well Axion-to-AIND job configs and submit commands."""

import argparse
import csv
import json
import shlex
from pathlib import Path
from typing import List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_CONFIG = REPO_ROOT / "config" / "greatlakes_project.env"
DEFAULT_PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate per-well env files and exact submit commands for scaling "
            "Axion well NWBs through the current AIND pipeline."
        )
    )
    parser.add_argument("--recording-stem", required=True)
    parser.add_argument("--raw-file", type=Path, required=True)
    parser.add_argument("--plate-map", type=Path, default=REPO_ROOT / "metadata/plate_maps/axion_48_well_opto_plate_map.csv")
    parser.add_argument("--wells", default="all", help="Comma-separated wells, or 'all' from the plate map.")
    parser.add_argument(
        "--selection-manifest",
        type=Path,
        default=None,
        help="well_selection_manifest.csv/json; when provided, only selected wells are prepared.",
    )
    parser.add_argument("--dataset", default="BroadbandHighFrequency")
    parser.add_argument("--export-start-time-s", type=float, default=0)
    parser.add_argument("--export-duration-s", default="NaN")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--project-config", type=Path, default=PROJECT_CONFIG)
    parser.add_argument("--session-description", default="Axion MEA per-well continuous voltage export for AIND ingestion")
    parser.add_argument("--allow-aind-overwrite", action="store_true")
    return parser.parse_args()


def load_selected_wells(selection_manifest: Path) -> List[str]:
    resolved = selection_manifest.expanduser().resolve()
    if resolved.suffix.lower() == ".json":
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        rows = payload.get("wells", [])
    else:
        with resolved.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

    wells = []
    for row in rows:
        selected = row.get("selected", False)
        if isinstance(selected, bool):
            keep = selected
        else:
            keep = str(selected).strip().lower() in {"1", "true", "yes", "y"}
        if keep and row.get("well"):
            wells.append(str(row["well"]).strip().upper())
    if not wells:
        raise SystemExit(f"No selected wells found in {resolved}")
    return wells


def load_wells(plate_map: Path, wells_arg: str) -> List[str]:
    with plate_map.expanduser().resolve().open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    valid = [row["well"].strip().upper() for row in rows if row.get("well", "").strip()]
    if wells_arg.strip().lower() == "all":
        return valid
    requested = [well.strip().upper() for well in wells_arg.split(",") if well.strip()]
    missing = sorted(set(requested) - set(valid))
    if missing:
        raise SystemExit(f"Requested wells are not in {plate_map}: {', '.join(missing)}")
    return requested


def q(value) -> str:
    return shlex.quote(str(value))


def write_env(path: Path, lines: List[Tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = ["#!/usr/bin/env bash", f"source \"${{PROJECT_CONFIG:-{PROJECT_CONFIG}}}\""]
    for key, value in lines:
        payload.append(f"export {key}={q(value)}")
    path.write_text("\n".join(payload) + "\n", encoding="utf-8")
    path.chmod(0o755)


def main() -> None:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    recording_stem = args.recording_stem
    if args.selection_manifest is not None:
        selected = set(load_selected_wells(args.selection_manifest))
        wells = [well for well in load_wells(args.plate_map, "all") if well in selected]
    else:
        wells = load_wells(args.plate_map, args.wells)
    batch_root = project_root / "jobs" / "aind_batches" / recording_stem
    binary_root = project_root / "data" / "interim" / "kilosort_binary" / recording_stem
    nwb_root = project_root / "data" / "interim" / "nwb" / recording_stem
    aind_results_root = project_root / "results" / "aind" / recording_stem
    manifest_rows = []
    submit_lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"cd {q(REPO_ROOT)}",
        "",
        "submit_one() {",
        "  local label=\"$1\"",
        "  shift",
        "  local out",
        "  out=\"$(eval \"$*\")\"",
        "  echo \"${label}: ${out}\"",
        "  sed -n 's/Submitted batch job //p' <<<\"${out}\"",
        "}",
        "",
    ]

    for well in wells:
        well_job_dir = batch_root / well
        binary_dir = binary_root / well
        nwb_dir = nwb_root / well
        aind_dir = aind_results_root / well
        binary_file = binary_dir / f"{well}.bin"
        nwb_file = nwb_dir / f"{recording_stem}_{well}.nwb"

        export_env = well_job_dir / "export_binary.env"
        nwb_env = well_job_dir / "export_nwb.env"
        aind_env = well_job_dir / "run_aind.env"

        write_env(
            export_env,
            [
                ("RECORDING_STEM", recording_stem),
                ("WELL", well),
                ("RAW_FILE", str(args.raw_file.expanduser().resolve())),
                ("DATASET", args.dataset),
                ("EXPORT_START_TIME_S", str(args.export_start_time_s)),
                ("EXPORT_DURATION_S", str(args.export_duration_s)),
                ("PLATE_MAP", str(args.plate_map.expanduser().resolve())),
                ("EXPORT_OUTPUT_DIR", str(binary_dir)),
                ("BINARY_FILE", str(binary_file)),
                ("KILOSORT_ENV_FILE", str(well_job_dir / "kilosort_ready.env")),
            ],
        )
        write_env(
            nwb_env,
            [
                ("RECORDING_STEM", recording_stem),
                ("WELL", well),
                ("EXPORT_OUTPUT_DIR", str(binary_dir)),
                ("BINARY_FILE", str(binary_file)),
                ("CHANNEL_MAPPING_CSV", str(binary_dir / "channel_mapping.csv")),
                ("BINARY_EXPORT_MANIFEST", str(binary_dir / "binary_export_manifest.json")),
                ("NWB_OUTPUT_DIR", str(nwb_dir)),
                ("OUTPUT_NWB", str(nwb_file)),
                ("SESSION_DESCRIPTION", args.session_description),
            ],
        )
        write_env(
            aind_env,
            [
                ("RECORDING_STEM", recording_stem),
                ("WELL", well),
                ("NWB_FILE", str(nwb_file)),
                ("AIND_RUNMODE", "fast"),
                ("AIND_SORTER", "kilosort4"),
                ("AIND_ALLOW_OVERWRITE", "true" if args.allow_aind_overwrite else "false"),
                ("AIND_RESUME", "true"),
            ],
        )

        export_cmd = f"PROJECT_CONFIG={q(args.project_config)} EXPORT_CONFIG={q(export_env)} sbatch {q(REPO_ROOT / 'slurm/export_axion_well_binary.sbatch')}"
        nwb_cmd = f"PROJECT_CONFIG={q(args.project_config)} NWB_CONFIG={q(nwb_env)} sbatch --dependency=afterok:${{export_job}} {q(REPO_ROOT / 'slurm/export_axion_well_nwb.sbatch')}"
        aind_cmd = f"PROJECT_CONFIG={q(args.project_config)} AIND_CONFIG={q(aind_env)} sbatch --dependency=afterok:${{nwb_job}} {q(REPO_ROOT / 'slurm/run_aind_nwb_well.sbatch')}"
        (well_job_dir / "submit_commands.sh").write_text(
            "\n".join(
                [
                    "#!/usr/bin/env bash",
                    "set -euo pipefail",
                    f"cd {q(REPO_ROOT)}",
                    "submit_one() {",
                    "  local label=\"$1\"",
                    "  shift",
                    "  local out",
                    "  out=\"$(eval \"$*\")\"",
                    "  echo \"${label}: ${out}\"",
                    "  sed -n 's/Submitted batch job //p' <<<\"${out}\"",
                    "}",
                    f"export_job=$(submit_one export_{well} {export_cmd})",
                    f"nwb_job=$(submit_one nwb_{well} {nwb_cmd})",
                    f"aind_job=$(submit_one aind_{well} {aind_cmd})",
                    "printf 'well=%s export_job=%s nwb_job=%s aind_job=%s\\n' "
                    f"{q(well)} \"${{export_job}}\" \"${{nwb_job}}\" \"${{aind_job}}\"",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (well_job_dir / "submit_commands.sh").chmod(0o755)

        submit_lines.extend(
            [
                f"echo 'Submitting {well}'",
                f"export_job=$(submit_one export_{well} {export_cmd})",
                f"nwb_job=$(submit_one nwb_{well} {nwb_cmd})",
                f"aind_job=$(submit_one aind_{well} {aind_cmd})",
                "printf 'well=%s export_job=%s nwb_job=%s aind_job=%s\\n' "
                f"{q(well)} \"${{export_job}}\" \"${{nwb_job}}\" \"${{aind_job}}\" | tee -a {q(batch_root / 'submitted_jobs.tsv')}",
                "",
            ]
        )
        manifest_rows.append(
            {
                "recording_stem": recording_stem,
                "well": well,
                "selection_manifest": str(args.selection_manifest.expanduser().resolve()) if args.selection_manifest else "",
                "raw_file": str(args.raw_file.expanduser().resolve()),
                "binary_file": str(binary_file),
                "nwb_file": str(nwb_file),
                "aind_results_dir": str(aind_dir),
                "job_dir": str(well_job_dir),
                "export_env": str(export_env),
                "nwb_env": str(nwb_env),
                "aind_env": str(aind_env),
            }
        )

    submit_script = batch_root / "submit_all_wells.sh"
    batch_root.mkdir(parents=True, exist_ok=True)
    submit_script.write_text("\n".join(submit_lines) + "\n", encoding="utf-8")
    submit_script.chmod(0o755)
    with (batch_root / "well_batch_manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]))
        writer.writeheader()
        writer.writerows(manifest_rows)
    (batch_root / "well_batch_manifest.json").write_text(json.dumps(manifest_rows, indent=2), encoding="utf-8")

    print(f"Prepared {len(wells)} wells under {batch_root}")
    print(f"Submit script: {submit_script}")
    print(f"Manifest: {batch_root / 'well_batch_manifest.csv'}")


if __name__ == "__main__":
    main()
