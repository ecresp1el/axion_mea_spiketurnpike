#!/usr/bin/env python3
"""Build a scale-up recordings manifest from an AIND selection asset inventory."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from axion_mea.plate_profiles import profile_from_metadata

DEFAULT_PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_RAW_METADATA_INVENTORY = (
    DEFAULT_PROJECT_ROOT / "metadata" / "matlab_axisfile_raw_metadata_inventory.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a raw-file asset inventory into the recordings_manifest.csv "
            "used by prepare_aind_recording_batches.py. This builder keeps one "
            "manifest row per usable raw-file variant so primary, filtered, and "
            "*_BroadbandProcessor.raw files remain independently traceable."
        )
    )
    parser.add_argument("--inventory-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--raw-metadata-inventory",
        type=Path,
        default=DEFAULT_RAW_METADATA_INVENTORY,
    )
    parser.add_argument("--aind-input", choices=["spikeinterface", "nwb"], default="spikeinterface")
    parser.add_argument("--min-total-spikes", type=int, default=11)
    parser.add_argument("--min-active-electrodes", type=int, default=1)
    parser.add_argument("--min-spikes-per-active-electrode", type=int, default=1)
    parser.add_argument(
        "--disable-submit",
        action="store_true",
        help="Write submit=false even for supported/ready recordings.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    text = path.expanduser().read_bytes().replace(b"\x00", b"").decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def truthy(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def normalize_token(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9()._-]+", "_", value.strip())
    return re.sub(r"_+", "_", cleaned).strip("_")


def scale_recording_stem(row: dict[str, str]) -> str:
    source_dir = Path(row["source_dir"])
    parts = source_dir.parts
    date = parts[-2] if len(parts) >= 2 else "unknown_date"
    barcode = parts[-1] if parts else "unknown_barcode"
    pieces = [
        date,
        barcode,
        row.get("recording_stem", ""),
        row.get("plate_type_name", ""),
        raw_variant_label(row),
    ]
    return normalize_token("_".join(piece for piece in pieces if piece))


def raw_variant_label(row: dict[str, str]) -> str:
    raw_name = row.get("raw_name", "")
    kind = row.get("raw_file_kind", "")
    if kind == "broadband_processor_raw" or "BroadbandProcessor" in raw_name:
        return "broadband_processor"
    match = re.search(r"_Filter\(([^)]+)\)", raw_name)
    if match:
        return "filter_" + normalize_token(match.group(1))
    analog = normalize_token(row.get("metadata_analog_mode", ""))
    return "_".join(piece for piece in ["primary_raw", analog] if piece)


def dataset_description_setting(row: dict[str, str], setting_name: str) -> str:
    description = row.get("dataset_description", "")
    for line in re.split(r"[\r\n]+", description):
        parts = [part.strip() for part in line.split(",")]
        if parts and parts[0].lower() == setting_name.lower():
            return ",".join(parts[1:]).strip()
    return ""


def filter_value(value: str) -> str:
    return value.strip() if value and value.strip() else "<blank>"


def filter_metadata_fields(row: dict[str, str]) -> dict[str, str]:
    values = {
        "acquisition_analog_mode_setting": (
            dataset_description_setting(row, "Analog Mode Setting")
            or row.get("metadata_analog_mode", "")
        ),
        "acquisition_digital_high_pass_filter": dataset_description_setting(
            row, "Digital High Pass Filter"
        ),
        "acquisition_digital_low_pass_filter": dataset_description_setting(
            row, "Digital Low Pass Filter"
        ),
        "derived_high_pass_filter": dataset_description_setting(row, "High Pass Filter"),
        "derived_low_pass_filter": dataset_description_setting(row, "Low Pass Filter"),
    }
    values["filter_metadata_signature"] = " | ".join(
        [
            f"analog={filter_value(values['acquisition_analog_mode_setting'])}",
            f"acquisition_hp={filter_value(values['acquisition_digital_high_pass_filter'])}",
            f"acquisition_lp={filter_value(values['acquisition_digital_low_pass_filter'])}",
            f"derived_hp={filter_value(values['derived_high_pass_filter'])}",
            f"derived_lp={filter_value(values['derived_low_pass_filter'])}",
        ]
    )
    return values


def loader_dataset_for_variant(row: dict[str, str]) -> str:
    raw_name = row.get("raw_name", "")
    kind = row.get("raw_file_kind", "")
    if kind == "broadband_processor_raw" or "BroadbandProcessor" in raw_name:
        return "BroadbandHighFrequency"
    return "RawVoltageData"


def voltage_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep every raw voltage variant as its own candidate row."""
    for row in rows:
        row.setdefault("raw_variant_label", raw_variant_label(row))
        row.setdefault("loader_dataset", loader_dataset_for_variant(row))
    return sorted(
        rows,
        key=lambda row: (
            row.get("source_dir", ""),
            row.get("recording_stem", ""),
            row.get("raw_variant_label", ""),
            row.get("raw_name", ""),
        ),
    )


def main() -> None:
    args = parse_args()
    inventory_rows = read_csv(args.inventory_csv)
    chosen_rows = voltage_rows(inventory_rows)
    manifest_rows: list[dict[str, Any]] = []
    summary = Counter()

    for row in chosen_rows:
        filter_fields = filter_metadata_fields(row)
        try:
            profile = profile_from_metadata(row)
            status = "supported"
            reason = f"{profile.family} profile selected from raw metadata"
        except ValueError as exc:
            profile = None
            status = "blocked_unknown_plate_type"
            reason = str(exc)
        assets_ready = (
            truthy(row.get("raw_file_exists", ""))
            and truthy(row.get("spike_counts_csv_exists", ""))
            and truthy(row.get("raw_metadata_matched", ""))
            and truthy(row.get("can_prepare_spike_sorting_inputs", ""))
        )
        enabled = assets_ready and status == "supported" and not args.disable_submit
        scale_status = "ready" if enabled else status
        if not assets_ready:
            scale_status = "blocked_missing_assets_or_metadata"
            reason = row.get("missing_assets", "") or "raw metadata did not match"
        manifest_row = {
            "recording_stem": scale_recording_stem(row),
            "raw_file": row["raw_file"],
            "plate_map": str(profile.plate_map.resolve()) if profile else "",
            "electrode_geometry": str(profile.electrode_geometry.resolve()) if profile else "",
            "params_template": str(profile.params_template.resolve()) if profile else "",
            "raw_metadata_inventory": str(args.raw_metadata_inventory.expanduser().resolve()),
            "spike_counts_csv": row.get("spike_counts_csv", ""),
            "spike_list_csv": row.get("spike_list_csv", ""),
            "dataset": row.get("loader_dataset", ""),
            "aind_input": args.aind_input,
            "allow_aind_overwrite": "true",
            "submit": str(enabled).lower(),
            "min_total_spikes": str(args.min_total_spikes),
            "min_active_electrodes": str(args.min_active_electrodes),
            "min_spikes_per_active_electrode": str(args.min_spikes_per_active_electrode),
            "scaleup_status": scale_status,
            "scaleup_reason": reason,
            "source_dir": row.get("source_dir", ""),
            "raw_name": row.get("raw_name", ""),
            "raw_variant_label": row.get("raw_variant_label", ""),
            "axion_recording_stem": row.get("recording_stem", ""),
            "raw_file_kind": row.get("raw_file_kind", ""),
            "dataset_description": row.get("dataset_description", ""),
            "filter_metadata_signature": filter_fields["filter_metadata_signature"],
            "acquisition_analog_mode_setting": filter_fields["acquisition_analog_mode_setting"],
            "acquisition_digital_high_pass_filter": filter_fields["acquisition_digital_high_pass_filter"],
            "acquisition_digital_low_pass_filter": filter_fields["acquisition_digital_low_pass_filter"],
            "derived_high_pass_filter": filter_fields["derived_high_pass_filter"],
            "derived_low_pass_filter": filter_fields["derived_low_pass_filter"],
            "metadata_analog_mode": row.get("metadata_analog_mode", ""),
            "metadata_high_pass_filter": row.get("metadata_high_pass_filter", ""),
            "metadata_high_pass_cutoff": row.get("metadata_high_pass_cutoff", ""),
            "metadata_low_pass_filter": row.get("metadata_low_pass_filter", ""),
            "metadata_low_pass_cutoff": row.get("metadata_low_pass_cutoff", ""),
            "metadata_axis_version": row.get("metadata_axis_version", ""),
            "metadata_instrument": row.get("metadata_instrument", ""),
            "metadata_firmware_version": row.get("metadata_firmware_version", ""),
            "plate_family": profile.family if profile else "",
            "plate_type_name": row.get("plate_type_name", ""),
            "well_dimensions": row.get("well_dimensions", ""),
            "electrode_dimensions": row.get("electrode_dimensions", ""),
            "num_channels": row.get("num_channels", ""),
            "n_chan_bin": str(profile.n_chan_bin) if profile else "",
            "dmin": str(profile.dmin) if profile else "",
            "dminx": str(profile.dminx) if profile else "",
            "max_channel_distance": str(profile.max_channel_distance) if profile else "",
            "x_centers": str(profile.x_centers) if profile else "",
            "nearest_templates": str(profile.nearest_templates) if profile else "",
            "nearest_chans": str(profile.nearest_chans) if profile else "",
            "whitening_range": str(profile.whitening_range) if profile else "",
            "duration_s": row.get("duration_s", ""),
        }
        manifest_rows.append(manifest_row)
        summary[f"status_{scale_status}"] += 1
        summary[f"plate_{row.get('plate_type_name', 'unknown')}"] += 1
        summary[f"variant_{row.get('raw_variant_label', 'unknown')}"] += 1

    output_dir = args.output_dir.expanduser().resolve()
    manifest_csv = output_dir / "recordings_manifest.csv"
    manifest_json = output_dir / "recordings_manifest.json"
    summary_json = output_dir / "recordings_manifest_summary.json"
    write_csv(manifest_csv, manifest_rows)
    manifest_json.write_text(json.dumps(manifest_rows, indent=2), encoding="utf-8")
    summary_payload = {
        "inventory_csv": str(args.inventory_csv.expanduser().resolve()),
        "recordings": len(manifest_rows),
        "ready_to_submit": sum(1 for row in manifest_rows if row["submit"] == "true"),
        "blocked": sum(1 for row in manifest_rows if row["submit"] != "true"),
        "counts": dict(summary),
        "manifest_csv": str(manifest_csv),
        "manifest_json": str(manifest_json),
    }
    summary_json.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    print(json.dumps(summary_payload, indent=2))


if __name__ == "__main__":
    main()
