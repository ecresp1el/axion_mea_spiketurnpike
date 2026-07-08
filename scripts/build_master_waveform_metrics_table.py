#!/usr/bin/env python
"""Write the master waveform metrics table for downstream analyses."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from axion_mea.master_unit_table import DEFAULT_STEP2_MANIFEST, load_master_unit_table, load_step2_manifest


DEFAULT_OUTPUT_CSV = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/"
    "downstream/master_waveform_metrics_table.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build one canonical table row per Kilosort good unit using the "
            "frozen AIND Step 1 outputs and optional Step 2 metadata."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_STEP2_MANIFEST)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--skipped-csv", type=Path, default=None)
    parser.add_argument("--recording", default=None, help="Optional exact recording filter.")
    parser.add_argument("--well", default=None, help="Optional exact well filter.")
    parser.add_argument("--limit", type=int, default=None, help="Optional manifest row limit for smoke tests.")
    parser.add_argument(
        "--recording-name",
        default="block0_None_recording1",
        help="AIND per-well recording name used in output folder paths.",
    )
    parser.add_argument(
        "--require-step2-labels",
        action="store_true",
        help="Skip wells unless the Step 2 unit label CSV exists and matches Step 1 unit order.",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress per-well progress logging.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_step2_manifest(args.manifest)
    if args.recording:
        manifest = manifest.loc[manifest["recording"] == args.recording].copy()
    if args.well:
        manifest = manifest.loc[manifest["well"] == args.well].copy()
    if args.limit is not None:
        manifest = manifest.head(args.limit).copy()

    table, skipped = load_master_unit_table(
        manifest=manifest,
        manifest_path=args.manifest,
        require_step2_labels=args.require_step2_labels,
        recording_name=args.recording_name,
        progress=not args.quiet,
    )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.output_csv, index=False)

    if args.skipped_csv is not None:
        args.skipped_csv.parent.mkdir(parents=True, exist_ok=True)
        skipped.to_csv(args.skipped_csv, index=False)

    print(f"Wrote {len(table)} Kilosort good-unit rows to {args.output_csv}")
    print(f"Skipped {len(skipped)} manifest wells")
    if args.require_step2_labels:
        print("Step 2 label CSVs were required for inclusion.")
    else:
        print("Step 2 metadata was attached when available.")


if __name__ == "__main__":
    main()
