#!/usr/bin/env python3
"""Build a scale-up recordings manifest from an AIND selection asset inventory."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_RAW_METADATA_INVENTORY = (
    DEFAULT_PROJECT_ROOT / "metadata" / "matlab_axisfile_raw_metadata_inventory.csv"
)
PLATE_MAP_48 = REPO_ROOT / "metadata" / "plate_maps" / "axion_48_well_opto_plate_map.csv"
PLATE_MAP_24 = REPO_ROOT / "metadata" / "plate_maps" / "axion_24_well_plate_map.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a raw-file asset inventory into the recordings_manifest.csv "
            "used by prepare_aind_recording_batches.py. This builder makes one "
            "manifest row per logical recording and currently prefers the "
            "BroadbandProcessor raw file when both primary .raw and "
            "*_BroadbandProcessor.raw are present. That is a deliberate "
            "scale-up assumption, not a statement that the paired primary .raw "
            "is unusable."
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
    with path.expanduser().open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


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
    ]
    return normalize_token("_".join(piece for piece in pieces if piece))


def plate_map_for(row: dict[str, str]) -> tuple[str, str, str]:
    plate_type = row.get("plate_type_name", "")
    if "FortyEightWell" in plate_type or "48" in plate_type:
        return str(PLATE_MAP_48.resolve()), "supported", "48-well/Lumos plate map available"
    if "TwentyFour" in plate_type or "24" in plate_type:
        return str(PLATE_MAP_24.resolve()), "supported", "24-well plate map available"
    if "SixWell" in plate_type or "6" in plate_type:
        return "", "blocked_missing_plate_map", "SixWell recording detected; add/confirm a SixWell plate map before enabling"
    return "", "blocked_unknown_plate_type", f"Unknown plate_type_name={plate_type!r}"


def choose_voltage_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Choose one voltage file per logical recording for the current scale-up plan.

    This intentionally de-duplicates paired Axion primary .raw and
    *_BroadbandProcessor.raw files. For now we prefer BroadbandProcessor because
    the validated fresh AIND workflow used that file family. A future comparison
    workflow should emit separate manifest rows for primary-vs-broadband inputs,
    with distinct recording_stem values, so filtered-input effects on sorting can
    be compared without overwriting results.
    """
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (row.get("source_dir", ""), row.get("recording_stem", ""))
        grouped.setdefault(key, []).append(row)
    chosen = []
    for group_rows in grouped.values():
        broadband = [row for row in group_rows if row.get("raw_file_kind") == "broadband_processor_raw"]
        chosen.append((broadband or group_rows)[0])
    return sorted(chosen, key=lambda row: (row.get("source_dir", ""), row.get("recording_stem", ""), row.get("raw_name", "")))


def main() -> None:
    args = parse_args()
    inventory_rows = read_csv(args.inventory_csv)
    chosen_rows = choose_voltage_rows(inventory_rows)
    manifest_rows: list[dict[str, Any]] = []
    summary = Counter()

    for row in chosen_rows:
        plate_map, status, reason = plate_map_for(row)
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
            "plate_map": plate_map,
            "raw_metadata_inventory": str(args.raw_metadata_inventory.expanduser().resolve()),
            "spike_counts_csv": row.get("spike_counts_csv", ""),
            "spike_list_csv": row.get("spike_list_csv", ""),
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
            "axion_recording_stem": row.get("recording_stem", ""),
            "raw_file_kind": row.get("raw_file_kind", ""),
            "plate_type_name": row.get("plate_type_name", ""),
            "duration_s": row.get("duration_s", ""),
        }
        manifest_rows.append(manifest_row)
        summary[f"status_{scale_status}"] += 1
        summary[f"plate_{row.get('plate_type_name', 'unknown')}"] += 1

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
