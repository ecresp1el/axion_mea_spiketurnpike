#!/usr/bin/env python3
"""Create a well-selection manifest for Axion-to-AIND batch sorting."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from axion_mea.well_selection import (
    DEFAULT_MIN_TOTAL_SPIKES,
    WellSelectionConfig,
    config_to_json,
    write_selection_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select useful wells for AIND spike sorting.")
    parser.add_argument("--recording-stem", required=True)
    parser.add_argument("--raw-file", type=Path, required=True)
    parser.add_argument("--plate-map", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--spike-counts-csv", type=Path, default=None)
    parser.add_argument("--spike-list-csv", type=Path, default=None)
    parser.add_argument("--raw-metadata-inventory", type=Path, default=None)
    parser.add_argument("--min-total-spikes", type=int, default=DEFAULT_MIN_TOTAL_SPIKES)
    parser.add_argument("--min-active-electrodes", type=int, default=1)
    parser.add_argument("--min-spikes-per-active-electrode", type=int, default=1)
    parser.add_argument("--require-active-flag", action="store_true")
    parser.add_argument("--exclude-control", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = WellSelectionConfig(
        recording_stem=args.recording_stem,
        raw_file=args.raw_file,
        plate_map_csv=args.plate_map,
        output_dir=args.output_dir,
        spike_counts_csv=args.spike_counts_csv,
        spike_list_csv=args.spike_list_csv,
        raw_metadata_inventory_csv=args.raw_metadata_inventory,
        min_total_spikes=args.min_total_spikes,
        min_active_electrodes=args.min_active_electrodes,
        min_spikes_per_active_electrode=args.min_spikes_per_active_electrode,
        require_active_flag=args.require_active_flag,
        exclude_control=args.exclude_control,
    )
    print("AIND well-selection assumptions")
    print("- Candidate wells come from the plate map.")
    print("- Activity is scored from Axion *_spike_counts.csv sidecars.")
    print("- Active/control/treatment annotations come from *_spike_list.csv when present.")
    print("- Raw voltage is not loaded during this selection step.")
    print("- Default min_total_spikes is 11, meaning wells need >10 total spikes.")
    print(json.dumps({"config": config_to_json(config)}, indent=2))
    manifest = write_selection_manifest(config)
    print("Asset status")
    print(json.dumps(manifest["asset_status"], indent=2))
    print("Selection summary")
    print(json.dumps({"summary": manifest["summary"]}, indent=2))
    selected = [
        {
            "rank": row["selection_rank"],
            "well": row["well"],
            "total_spikes": row["total_spikes"],
            "active_electrodes": row["active_electrodes"],
        }
        for row in manifest["wells"]
        if row["selected"]
    ]
    selected.sort(key=lambda row: row["rank"])
    rejected_reasons: dict[str, int] = {}
    for row in manifest["wells"]:
        if row["selected"]:
            continue
        for reason in str(row["selection_reason"]).split(";"):
            rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1
    print("Selected wells by spike count")
    print(json.dumps(selected, indent=2))
    print("Rejected reason counts")
    print(json.dumps(rejected_reasons, indent=2))
    print(json.dumps({"manifest_json": manifest["manifest_json"], "manifest_csv": manifest["manifest_csv"]}, indent=2))


if __name__ == "__main__":
    main()
