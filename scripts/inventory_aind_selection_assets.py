#!/usr/bin/env python3
"""Inventory raw files and sidecars needed for AIND well selection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from axion_mea.well_selection import inventory_selection_assets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scan an Axion raw-data directory and report which .raw files have "
            "the sidecars needed for well selection and AIND batch preparation."
        )
    )
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--plate-map", type=Path, default=None)
    parser.add_argument("--raw-metadata-inventory", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("AIND selection asset inventory assumptions")
    print("- Every .raw file under --raw-root is inventoried independently.")
    print("- Sidecars are inferred next to the raw file using the Axion recording stem.")
    print("- The continuous raw voltage is not opened; this is a file/provenance check.")
    print("- spike_counts_csv is required for activity scoring.")
    print("- spike_list_csv is used for well annotations when available.")
    manifest = inventory_selection_assets(
        args.raw_root,
        args.output_dir,
        plate_map_csv=args.plate_map,
        raw_metadata_inventory_csv=args.raw_metadata_inventory,
    )
    print("Inventory summary")
    print(json.dumps(manifest["summary"], indent=2))
    missing = [
        {
            "raw_name": row["raw_name"],
            "recording_stem": row["recording_stem"],
            "missing_assets": row["missing_assets"],
            "raw_metadata_matched": row["raw_metadata_matched"],
        }
        for row in manifest["files"]
        if row["missing_assets"] or not row["raw_metadata_matched"]
    ]
    print("Files missing assets or raw metadata match")
    print(json.dumps(missing, indent=2))
    print(
        json.dumps(
            {
                "inventory_json": manifest["inventory_json"],
                "inventory_csv": manifest["inventory_csv"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
