#!/usr/bin/env python3
"""Package an exported Axion well binary as NWB."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from axion_mea.nwb_export import AxionWellNwbConfig, config_to_json, write_axion_well_nwb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert one exported Axion per-well Kilosort binary into NWB."
    )
    parser.add_argument("--binary-file", type=Path, required=True)
    parser.add_argument("--output-nwb", type=Path, required=True)
    parser.add_argument("--channel-mapping", type=Path, required=True)
    parser.add_argument("--export-manifest", type=Path, required=True)
    parser.add_argument("--recording-stem", required=True)
    parser.add_argument("--well", required=True)
    parser.add_argument("--session-description", default="Axion MEA per-well continuous voltage export")
    parser.add_argument("--identifier", default=None)
    parser.add_argument("--session-start-time", default=None)
    parser.add_argument("--timezone", default="America/Detroit")
    parser.add_argument("--dtype", default="int16")
    parser.add_argument("--fs", type=float, default=12500.0)
    parser.add_argument("--n-chan-bin", type=int, default=16)
    parser.add_argument("--voltage-scale-v-per-sample", type=float, default=None)
    parser.add_argument("--source-raw-file", type=Path, default=None)
    parser.add_argument("--raw-metadata-inventory", type=Path, default=None)
    parser.add_argument("--kilosort-manifest", type=Path, default=None)
    parser.add_argument("--probe-json", type=Path, default=None)
    parser.add_argument("--run-command", default=None)
    parser.add_argument("--working-directory", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = AxionWellNwbConfig(
        binary_file=args.binary_file,
        output_nwb=args.output_nwb,
        channel_mapping_csv=args.channel_mapping,
        export_manifest_json=args.export_manifest,
        recording_stem=args.recording_stem,
        well=args.well,
        session_description=args.session_description,
        identifier=args.identifier,
        session_start_time=args.session_start_time,
        timezone=args.timezone,
        dtype=args.dtype,
        fs=args.fs,
        n_chan_bin=args.n_chan_bin,
        voltage_scale_v_per_sample=args.voltage_scale_v_per_sample,
        source_raw_file=args.source_raw_file,
        raw_metadata_inventory_csv=args.raw_metadata_inventory,
        kilosort_manifest_json=args.kilosort_manifest,
        probe_json=args.probe_json,
        run_command=args.run_command or shlex.join([sys.executable, *sys.argv]),
        command_argv=[sys.executable, *sys.argv],
        working_directory=args.working_directory or os.getcwd(),
    )
    print(json.dumps({"config": config_to_json(config)}, indent=2))
    manifest = write_axion_well_nwb(config)
    print(json.dumps({"manifest": manifest}, indent=2))


if __name__ == "__main__":
    main()
