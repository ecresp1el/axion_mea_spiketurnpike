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
DEFAULT_RAW_METADATA_INVENTORY = (
    DEFAULT_PROJECT_ROOT / "metadata" / "matlab_axisfile_raw_metadata_inventory.csv"
)


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
    parser.add_argument(
        "--export-duration-s",
        default="NaN",
        help=(
            "Finite export duration in seconds for debugging. Default NaN means "
            "full recording: the MATLAB exporter omits the AxionFileLoader "
            "timespan argument."
        ),
    )
    parser.add_argument("--raw-metadata-inventory", type=Path, default=DEFAULT_RAW_METADATA_INVENTORY)
    parser.add_argument("--aind-input", choices=["spikeinterface", "nwb"], default="spikeinterface")
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--project-config", type=Path, default=PROJECT_CONFIG)
    parser.add_argument("--session-description", default="Axion MEA per-well continuous voltage export for AIND ingestion")
    parser.add_argument("--allow-aind-overwrite", action="store_true")
    parser.add_argument(
        "--allow-unsupported-plate",
        action="store_true",
        help=(
            "Bypass the current guard that only the validated FortyEightWellLumos "
            "4x4-per-well geometry is supported for AIND scale-up."
        ),
    )
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


def _metadata_from_selection_manifest(selection_manifest: Path | None) -> dict[str, str]:
    if selection_manifest is None:
        return {}
    resolved = selection_manifest.expanduser().resolve()
    if not resolved.exists():
        return {}
    if resolved.suffix.lower() == ".json":
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        rows = payload.get("wells", [])
    else:
        with resolved.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    for row in rows:
        return {str(key): str(value) for key, value in row.items() if value not in (None, "")}
    return {}


def _metadata_from_raw_inventory(inventory_csv: Path | None, raw_file: Path) -> dict[str, str]:
    if inventory_csv is None:
        return {}
    resolved = inventory_csv.expanduser().resolve()
    if not resolved.exists():
        return {}
    raw_resolved = str(raw_file.expanduser().resolve())
    raw_name = raw_file.name
    with resolved.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for strategy in ("raw_file", "raw_name"):
        matches = [row for row in rows if str(row.get(strategy, "")) == (raw_resolved if strategy == "raw_file" else raw_name)]
        if len(matches) == 1:
            return {str(key): str(value) for key, value in matches[0].items() if value not in (None, "")}
    return {}


def source_metadata(args: argparse.Namespace) -> dict[str, str]:
    metadata = _metadata_from_raw_inventory(args.raw_metadata_inventory, args.raw_file)
    selection_metadata = _metadata_from_selection_manifest(args.selection_manifest)
    if selection_metadata:
        metadata.setdefault("plate_type_name", selection_metadata.get("raw_plate_type_name", ""))
        metadata.setdefault("duration_s", selection_metadata.get("raw_duration_s", ""))
    return metadata


def validate_supported_plate(args: argparse.Namespace) -> dict[str, str]:
    metadata = source_metadata(args)
    if args.allow_unsupported_plate:
        return metadata
    plate_type_name = metadata.get("plate_type_name") or metadata.get("raw_plate_type_name") or ""
    well_dimensions = metadata.get("well_dimensions", "")
    electrode_dimensions = metadata.get("electrode_dimensions", "")
    num_channels = metadata.get("num_channels", "")
    looks_lumos48 = (
        plate_type_name == "FortyEightWellLumos"
        or (
            well_dimensions == "[6 8]"
            and electrode_dimensions == "[6 8 4 4]"
            and num_channels == "768"
        )
    )
    if not looks_lumos48:
        raise SystemExit(
            "Unsupported or unknown plate type for this AIND scale-up path. "
            "Current validated route is FortyEightWellLumos / 48 wells / 16 "
            "electrodes per well / 4x4 geometry. "
            f"Observed plate_type_name={plate_type_name!r}, "
            f"well_dimensions={well_dimensions!r}, "
            f"electrode_dimensions={electrode_dimensions!r}, "
            f"num_channels={num_channels!r}. "
            "SixWell/CytoView needs its own plate map, per-well geometry, channel "
            "count, and Kilosort/AIND params before scale-up."
        )
    return metadata


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
    source_metadata_row = validate_supported_plate(args)
    export_duration_s = str(args.export_duration_s).strip() or "NaN"
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
        "  out=\"$(\"$@\")\"",
        "  echo \"${label}: ${out}\" >&2",
        "  printf '%s\\n' \"${out}\"",
        "}",
        "",
    ]

    for well in wells:
        well_job_dir = batch_root / well
        binary_dir = binary_root / well
        nwb_dir = nwb_root / well
        aind_dir = aind_results_root / well
        spikeinterface_dir = project_root / "jobs" / "aind" / recording_stem / well / "spikeinterface"
        binary_file = binary_dir / f"{well}.bin"
        channel_mapping_csv = binary_dir / "channel_mapping.csv"
        binary_export_manifest = binary_dir / "binary_export_manifest.json"
        nwb_file = nwb_dir / f"{recording_stem}_{well}.nwb"

        export_env = well_job_dir / "export_binary.env"
        nwb_env = well_job_dir / "export_nwb.env"
        spikeinterface_env = well_job_dir / "prepare_spikeinterface.env"
        aind_env = well_job_dir / "run_aind.env"
        spikeinterface_aind_env = spikeinterface_dir / "run_aind_spikeinterface.env"

        write_env(
            export_env,
            [
                ("RECORDING_STEM", recording_stem),
                ("WELL", well),
                ("RAW_FILE", str(args.raw_file.expanduser().resolve())),
                ("DATASET", args.dataset),
                ("EXPORT_START_TIME_S", str(args.export_start_time_s)),
                ("EXPORT_DURATION_S", export_duration_s),
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
                ("CHANNEL_MAPPING_CSV", str(channel_mapping_csv)),
                ("BINARY_EXPORT_MANIFEST", str(binary_export_manifest)),
                ("NWB_OUTPUT_DIR", str(nwb_dir)),
                ("OUTPUT_NWB", str(nwb_file)),
                ("SESSION_DESCRIPTION", args.session_description),
            ],
        )
        write_env(
            spikeinterface_env,
            [
                ("RECORDING_STEM", recording_stem),
                ("WELL", well),
                ("BINARY_FILE", str(binary_file)),
                ("CHANNEL_MAPPING_CSV", str(channel_mapping_csv)),
                ("BINARY_EXPORT_MANIFEST", str(binary_export_manifest)),
                ("SPIKEINTERFACE_OUTPUT_DIR", str(spikeinterface_dir)),
                ("FS", "12500"),
                ("DTYPE", "int16"),
                ("N_CHAN_BIN", "16"),
                ("OFFSET_TO_UV", "0"),
                ("IS_FILTERED", "true"),
            ],
        )
        write_env(
            aind_env,
            [
                ("RECORDING_STEM", recording_stem),
                ("WELL", well),
                ("NWB_FILE", str(nwb_file)),
                ("AIND_RUNMODE", "full"),
                ("AIND_SORTER", "kilosort4"),
                ("AIND_ALLOW_OVERWRITE", "true" if args.allow_aind_overwrite else "false"),
                ("AIND_RESUME", "true"),
            ],
        )

        export_cmd = f"env PROJECT_CONFIG={q(args.project_config)} EXPORT_CONFIG={q(export_env)} sbatch --parsable {q(REPO_ROOT / 'slurm/export_axion_well_binary.sbatch')}"
        nwb_cmd = f"env PROJECT_CONFIG={q(args.project_config)} NWB_CONFIG={q(nwb_env)} sbatch --parsable --dependency=afterok:${{export_job}} {q(REPO_ROOT / 'slurm/export_axion_well_nwb.sbatch')}"
        spikeinterface_cmd = f"env PROJECT_CONFIG={q(args.project_config)} SPIKEINTERFACE_CONFIG={q(spikeinterface_env)} sbatch --parsable --dependency=afterok:${{export_job}} {q(REPO_ROOT / 'slurm/prepare_aind_spikeinterface_well.sbatch')}"
        if args.aind_input == "spikeinterface":
            aind_cmd = f"env PROJECT_CONFIG={q(args.project_config)} AIND_CONFIG={q(spikeinterface_aind_env)} sbatch --parsable --dependency=afterok:${{spikeinterface_job}}:${{nwb_job}} {q(REPO_ROOT / 'slurm/run_aind_nwb_well.sbatch')}"
        else:
            aind_cmd = f"env PROJECT_CONFIG={q(args.project_config)} AIND_CONFIG={q(aind_env)} sbatch --parsable --dependency=afterok:${{nwb_job}} {q(REPO_ROOT / 'slurm/run_aind_nwb_well.sbatch')}"

        well_submit_lines = [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            f"cd {q(REPO_ROOT)}",
            "submit_one() {",
            "  local label=\"$1\"",
            "  shift",
            "  local out",
            "  out=\"$(\"$@\")\"",
            "  echo \"${label}: ${out}\" >&2",
            "  printf '%s\\n' \"${out}\"",
            "}",
            f"export_job=$(submit_one export_{well} {export_cmd})",
            f"nwb_job=$(submit_one nwb_{well} {nwb_cmd})",
            f"spikeinterface_job=$(submit_one spikeinterface_{well} {spikeinterface_cmd})",
            f"aind_job=$(submit_one aind_{well} {aind_cmd})",
            "printf 'well=%s export_job=%s nwb_job=%s spikeinterface_job=%s aind_job=%s\\n' "
            f"{q(well)} \"${{export_job}}\" \"${{nwb_job}}\" \"${{spikeinterface_job}}\" \"${{aind_job}}\"",
        ]
        (well_job_dir / "submit_commands.sh").write_text(
            "\n".join(well_submit_lines) + "\n",
            encoding="utf-8",
        )
        (well_job_dir / "submit_commands.sh").chmod(0o755)

        submit_lines.extend(
            [
                f"echo 'Submitting {well}'",
                f"export_job=$(submit_one export_{well} {export_cmd})",
                f"nwb_job=$(submit_one nwb_{well} {nwb_cmd})",
                f"spikeinterface_job=$(submit_one spikeinterface_{well} {spikeinterface_cmd})",
                f"aind_job=$(submit_one aind_{well} {aind_cmd})",
                "printf 'well=%s export_job=%s nwb_job=%s spikeinterface_job=%s aind_job=%s\\n' "
                f"{q(well)} \"${{export_job}}\" \"${{nwb_job}}\" \"${{spikeinterface_job}}\" \"${{aind_job}}\" | tee -a {q(batch_root / 'submitted_jobs.tsv')}",
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
                "spikeinterface_env": str(spikeinterface_env),
                "spikeinterface_dir": str(spikeinterface_dir),
                "aind_env": str(spikeinterface_aind_env if args.aind_input == "spikeinterface" else aind_env),
                "aind_input": args.aind_input,
                "plate_type_name": source_metadata_row.get("plate_type_name", ""),
                "well_dimensions": source_metadata_row.get("well_dimensions", ""),
                "electrode_dimensions": source_metadata_row.get("electrode_dimensions", ""),
                "num_channels": source_metadata_row.get("num_channels", ""),
                "export_duration_s": export_duration_s,
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
