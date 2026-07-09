#!/usr/bin/env python3
"""Prepare AIND well batches across multiple Axion recordings."""

from __future__ import annotations

import argparse
import csv
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from axion_mea.filter_metadata import FILTER_METADATA_COLUMNS

PROJECT_CONFIG = REPO_ROOT / "config" / "greatlakes_project.env"
DEFAULT_PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_PLATE_MAP = REPO_ROOT / "metadata" / "plate_maps" / "axion_48_well_opto_plate_map.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate saved prepare/submit scripts for scaling the Axion-to-AIND "
            "workflow across many recordings and selected wells."
        )
    )
    parser.add_argument(
        "--recordings-manifest",
        type=Path,
        required=True,
        help="CSV with required columns recording_stem,raw_file.",
    )
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--project-config", type=Path, default=PROJECT_CONFIG)
    parser.add_argument("--plate-map", type=Path, default=DEFAULT_PLATE_MAP)
    parser.add_argument("--raw-metadata-inventory", type=Path, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to <project-root>/jobs/aind_recording_batches/<manifest_stem>.",
    )
    parser.add_argument("--aind-input", choices=["spikeinterface", "nwb"], default="spikeinterface")
    parser.add_argument("--min-total-spikes", type=int, default=11)
    parser.add_argument("--min-active-electrodes", type=int, default=1)
    parser.add_argument("--min-spikes-per-active-electrode", type=int, default=1)
    parser.add_argument("--require-active-flag", action="store_true")
    parser.add_argument("--exclude-control", action="store_true")
    parser.add_argument("--allow-aind-overwrite", action="store_true")
    parser.add_argument(
        "--run-prepare",
        action="store_true",
        help="Immediately run the generated prepare_all_recordings.sh script.",
    )
    return parser.parse_args()


def q(value: Any) -> str:
    return shlex.quote(str(value))


def truthy(value: str | None, default: bool) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "submit", "selected"}


def field(row: dict[str, str], name: str, default: str = "") -> str:
    return str(row.get(name, default) or "").strip()


def resolve_path(value: str, base: Path | None = None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute() and base is not None:
        path = base / path
    return path.resolve()


def read_manifest(path: Path) -> list[dict[str, str]]:
    resolved = path.expanduser()
    with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"recording_stem", "raw_file"}
    missing = required - set(rows[0].keys() if rows else [])
    if missing:
        raise SystemExit(
            f"{resolved} is missing required column(s): {', '.join(sorted(missing))}"
        )
    return rows


def logged_command(command: list[str]) -> str:
    return " ".join(q(part) for part in command) + ' 2>&1 | tee -a "${PREP_LOG}"'


def script_header() -> list[str]:
    return [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"cd {q(REPO_ROOT)}",
        "",
    ]


def add_optional_path(cmd: list[str], flag: str, path: Path | None) -> None:
    if path is not None:
        cmd.extend([flag, str(path)])


def main() -> None:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    manifest_path = args.recordings_manifest.expanduser()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else project_root / "jobs" / "aind_recording_batches" / manifest_path.stem
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows = read_manifest(manifest_path)
    prepare_lines = script_header()
    prepare_lines.extend(
        [
            f"PREP_LOG={q(output_dir / 'prepare_all_recordings.log')}",
            ": > \"${PREP_LOG}\"",
            "",
        ]
    )
    submit_lines = script_header()
    submit_lines.extend(
        [
            f"MASTER_LOG={q(output_dir / 'submit_all_recordings.log')}",
            f"MASTER_JOBS={q(output_dir / 'submitted_recording_batches.tsv')}",
            ": > \"${MASTER_LOG}\"",
            ": > \"${MASTER_JOBS}\"",
            "",
            "run_recording_submit() {",
            "  local recording=\"$1\"",
            "  local submit_script=\"$2\"",
            "  local submitted_jobs=\"$3\"",
            "  local before_lines=0",
            "  if [[ -f \"${submitted_jobs}\" ]]; then",
            "    before_lines=$(wc -l < \"${submitted_jobs}\")",
            "  fi",
            "  echo \"Submitting recording ${recording}: ${submit_script}\" | tee -a \"${MASTER_LOG}\"",
            "  bash \"${submit_script}\" 2>&1 | tee -a \"${MASTER_LOG}\"",
            "  if [[ -f \"${submitted_jobs}\" ]]; then",
            "    awk -v rec=\"${recording}\" -v first_new=\"$((before_lines + 1))\" 'NR >= first_new {print \"recording=\" rec \" \" $0}' \"${submitted_jobs}\" >> \"${MASTER_JOBS}\"",
            "  fi",
            "}",
            "",
        ]
    )
    supervisor_lines = script_header()
    supervisor_lines.extend(
        [
            f"SUPERVISOR_LOG={q(output_dir / 'supervise_all_recordings.log')}",
            f"SUPERVISOR_JOBS={q(output_dir / 'submitted_recording_supervisors.tsv')}",
            ": > \"${SUPERVISOR_LOG}\"",
            ": > \"${SUPERVISOR_JOBS}\"",
            "",
            "run_recording_supervisor() {",
            "  local recording=\"$1\"",
            "  local supervisor_output_dir=\"$2\"",
            "  local job_id",
            "  echo \"Starting supervisor for ${recording}\" | tee -a \"${SUPERVISOR_LOG}\"",
            "  job_id=\"$(env "
            f"PROJECT_CONFIG={q(args.project_config.expanduser().resolve())} "
            "RECORDING_STEM=\"${recording}\" "
            "SUPERVISOR_OUTPUT_DIR=\"${supervisor_output_dir}\" "
            f"sbatch --parsable {q(REPO_ROOT / 'slurm/run_aind_recording_supervisor.sbatch')})\"",
            "  printf 'recording=%s supervisor_job=%s output_dir=%s\\n' \"${recording}\" \"${job_id}\" \"${supervisor_output_dir}\" | tee -a \"${SUPERVISOR_LOG}\" | tee -a \"${SUPERVISOR_JOBS}\"",
            "}",
            "",
        ]
    )

    planned_rows: list[dict[str, str]] = []
    for index, row in enumerate(manifest_rows, start=1):
        enabled = truthy(field(row, "submit", field(row, "selected", "")), default=True)
        recording_stem = field(row, "recording_stem")
        raw_file = resolve_path(field(row, "raw_file"), manifest_path.parent)
        if not recording_stem:
            raise SystemExit(f"Row {index} is missing recording_stem")
        if raw_file is None:
            raise SystemExit(f"Row {index} ({recording_stem}) is missing raw_file")

        plate_map = resolve_path(field(row, "plate_map"), manifest_path.parent) or args.plate_map.resolve()
        raw_inventory = (
            resolve_path(field(row, "raw_metadata_inventory"), manifest_path.parent)
            or args.raw_metadata_inventory
        )
        if raw_inventory is not None:
            raw_inventory = raw_inventory.expanduser().resolve()
        selection_manifest = resolve_path(field(row, "selection_manifest"), manifest_path.parent)
        selection_dir = (
            project_root / "jobs" / "aind_batches" / recording_stem / "selection"
        )
        generated_selection_manifest = selection_dir / "well_selection_manifest.csv"
        batch_root = project_root / "jobs" / "aind_batches" / recording_stem
        submit_script = batch_root / "submit_all_wells.sh"
        submitted_jobs = batch_root / "submitted_jobs.tsv"
        supervisor_output_dir = project_root / "jobs" / "aind_recording_supervisors" / recording_stem
        aind_input = field(row, "aind_input", args.aind_input) or args.aind_input
        dataset = field(row, "dataset")
        electrode_geometry = resolve_path(field(row, "electrode_geometry"), manifest_path.parent)
        params_template = resolve_path(field(row, "params_template"), manifest_path.parent)
        allow_overwrite = truthy(
            field(row, "allow_aind_overwrite", ""),
            default=args.allow_aind_overwrite,
        )

        if aind_input not in {"spikeinterface", "nwb"}:
            raise SystemExit(
                f"Row {index} ({recording_stem}) has invalid aind_input={aind_input!r}"
            )

        wells = field(row, "wells")
        manual_wells = bool(wells and selection_manifest is None)
        select_cmd: list[str] | None = None
        if selection_manifest is None and not manual_wells:
            select_cmd = [
                "bash",
                str(REPO_ROOT / "scripts" / "select_aind_wells.sh"),
                "--recording-stem",
                recording_stem,
                "--raw-file",
                str(raw_file),
                "--plate-map",
                str(plate_map),
                "--output-dir",
                str(selection_dir),
                "--min-total-spikes",
                field(row, "min_total_spikes", str(args.min_total_spikes)),
                "--min-active-electrodes",
                field(row, "min_active_electrodes", str(args.min_active_electrodes)),
                "--min-spikes-per-active-electrode",
                field(
                    row,
                    "min_spikes_per_active_electrode",
                    str(args.min_spikes_per_active_electrode),
                ),
            ]
            add_optional_path(select_cmd, "--raw-metadata-inventory", raw_inventory)
            add_optional_path(
                select_cmd,
                "--spike-counts-csv",
                resolve_path(field(row, "spike_counts_csv"), manifest_path.parent),
            )
            add_optional_path(
                select_cmd,
                "--spike-list-csv",
                resolve_path(field(row, "spike_list_csv"), manifest_path.parent),
            )
            if truthy(field(row, "require_active_flag", ""), default=args.require_active_flag):
                select_cmd.append("--require-active-flag")
            if truthy(field(row, "exclude_control", ""), default=args.exclude_control):
                select_cmd.append("--exclude-control")
            selection_manifest_for_prepare = generated_selection_manifest
        elif manual_wells:
            selection_manifest_for_prepare = None
        else:
            selection_manifest_for_prepare = selection_manifest

        prepare_cmd = [
            "bash",
            str(REPO_ROOT / "scripts" / "prepare_aind_well_batch.sh"),
            "--recording-stem",
            recording_stem,
            "--raw-file",
            str(raw_file),
            "--plate-map",
            str(plate_map),
            "--project-root",
            str(project_root),
            "--project-config",
            str(args.project_config.expanduser().resolve()),
            "--aind-input",
            aind_input,
        ]
        if selection_manifest_for_prepare is not None:
            prepare_cmd.extend(["--selection-manifest", str(selection_manifest_for_prepare)])
        if manual_wells:
            prepare_cmd.extend(["--wells", wells])
        if dataset:
            prepare_cmd.extend(["--dataset", dataset])
        add_optional_path(prepare_cmd, "--electrode-geometry", electrode_geometry)
        add_optional_path(prepare_cmd, "--params-template", params_template)
        add_optional_path(prepare_cmd, "--raw-metadata-inventory", raw_inventory)
        if allow_overwrite:
            prepare_cmd.append("--allow-aind-overwrite")

        if enabled:
            prepare_lines.extend(
                [
                    f"echo 'Preparing recording {recording_stem}'",
                    f"mkdir -p {q(selection_dir)}",
                ]
            )
            if select_cmd is not None:
                prepare_lines.append(logged_command(select_cmd))
            prepare_lines.append(logged_command(prepare_cmd))
            prepare_lines.append("")
            submit_lines.append(
                "run_recording_submit "
                f"{q(recording_stem)} {q(submit_script)} {q(submitted_jobs)}"
            )
            supervisor_lines.append(
                "run_recording_supervisor "
                f"{q(recording_stem)} {q(supervisor_output_dir)}"
            )
        else:
            prepare_lines.append(f"echo 'Skipping disabled recording {recording_stem}'")
            supervisor_lines.append(f"echo 'Skipping disabled recording {recording_stem}'")

        planned_row = {
                "enabled": str(enabled).lower(),
                "recording_stem": recording_stem,
                "raw_file": str(raw_file),
                "selection_manifest": str(selection_manifest_for_prepare) if selection_manifest_for_prepare else "",
                "selection_manifest_source": (
                    "manual_wells"
                    if manual_wells
                    else "provided"
                    if selection_manifest
                    else "generated"
                ),
                "wells": wells,
                "plate_map": str(plate_map),
                "electrode_geometry": str(electrode_geometry) if electrode_geometry else "",
                "params_template": str(params_template) if params_template else "",
                "dataset": dataset,
                "plate_family": field(row, "plate_family"),
                "raw_variant_label": field(row, "raw_variant_label"),
                "raw_file_kind": field(row, "raw_file_kind"),
                "filter_metadata_signature": field(row, "filter_metadata_signature"),
                "acquisition_analog_mode_setting": field(row, "acquisition_analog_mode_setting"),
                "acquisition_digital_high_pass_filter": field(row, "acquisition_digital_high_pass_filter"),
                "acquisition_digital_low_pass_filter": field(row, "acquisition_digital_low_pass_filter"),
                "derived_high_pass_filter": field(row, "derived_high_pass_filter"),
                "derived_low_pass_filter": field(row, "derived_low_pass_filter"),
                "raw_metadata_inventory": str(raw_inventory) if raw_inventory else "",
                "aind_input": aind_input,
                "allow_aind_overwrite": str(allow_overwrite).lower(),
                "batch_root": str(batch_root),
                "prepare_submit_script": str(submit_script),
                "submitted_jobs": str(submitted_jobs),
                "supervisor_output_dir": str(supervisor_output_dir),
        }
        for field_name in FILTER_METADATA_COLUMNS:
            planned_row[field_name] = field(row, field_name)
        planned_rows.append(planned_row)

    prepare_script = output_dir / "prepare_all_recordings.sh"
    submit_script = output_dir / "submit_all_recordings.sh"
    supervisor_script = output_dir / "supervise_all_recordings.sh"
    prepare_script.write_text("\n".join(prepare_lines) + "\n", encoding="utf-8")
    submit_script.write_text("\n".join(submit_lines) + "\n", encoding="utf-8")
    supervisor_script.write_text("\n".join(supervisor_lines) + "\n", encoding="utf-8")
    prepare_script.chmod(0o755)
    submit_script.chmod(0o755)
    supervisor_script.chmod(0o755)

    fieldnames = [
        "enabled",
        "recording_stem",
        "raw_file",
        "selection_manifest",
        "selection_manifest_source",
        "wells",
        "plate_map",
        "electrode_geometry",
        "params_template",
        "dataset",
        "plate_family",
        "raw_variant_label",
        "raw_file_kind",
        *FILTER_METADATA_COLUMNS,
        "raw_metadata_inventory",
        "aind_input",
        "allow_aind_overwrite",
        "batch_root",
        "prepare_submit_script",
        "submitted_jobs",
        "supervisor_output_dir",
    ]
    with (output_dir / "recording_batch_manifest.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(planned_rows)
    (output_dir / "recording_batch_manifest.json").write_text(
        json.dumps(planned_rows, indent=2), encoding="utf-8"
    )

    print(f"Prepared recording batch plan for {len(planned_rows)} recordings under {output_dir}")
    print(f"Prepare script: {prepare_script}")
    print(f"Submit script: {submit_script}")
    print(f"Supervisor script: {supervisor_script}")
    print(f"Manifest: {output_dir / 'recording_batch_manifest.csv'}")
    if args.run_prepare:
        subprocess.run(["bash", str(prepare_script)], check=True)


if __name__ == "__main__":
    main()
