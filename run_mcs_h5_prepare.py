#!/usr/bin/env python3
"""Inspect or explicitly export an MCS MEA2100 HDF5 recording for sorting."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from axion_mea.io.mcs_h5 import export_mcs_binary, inspect_mcs_h5  # noqa: E402
from axion_mea.io.mcs_msrd import export_msrd_binary, export_msrd_h5, inspect_mcs_msrd  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input-h5", type=Path)
    inputs.add_argument("--input-msrd", type=Path)
    parser.add_argument("--output-dir", type=Path, help="Required with --export-binary.")
    parser.add_argument("--export-binary", action="store_true", help="Write a continuous int16 binary and metadata tables.")
    parser.add_argument("--export-h5", action="store_true", help="For --input-msrd, write an analysis HDF5 copy with geometry and events.")
    parser.add_argument("--chunk-samples", type=int, default=100_000)
    args = parser.parse_args()
    if (args.export_binary or args.export_h5) and args.output_dir is None:
        parser.error("--output-dir is required with --export-binary or --export-h5")
    if args.export_h5 and not args.input_msrd:
        parser.error("--export-h5 currently supports --input-msrd only")
    if args.input_h5:
        recording = inspect_mcs_h5(args.input_h5)
        result = export_mcs_binary(recording, args.output_dir, args.chunk_samples) if args.export_binary else recording.manifest()
    else:
        recording = inspect_mcs_msrd(args.input_msrd)
        result = recording.manifest()
        analysis_h5 = None
        if args.export_h5:
            analysis_h5 = str(export_msrd_h5(recording, args.output_dir))
        if args.export_binary:
            result = export_msrd_binary(recording, args.output_dir)
        if analysis_h5:
            result["analysis_h5_file"] = analysis_h5
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
