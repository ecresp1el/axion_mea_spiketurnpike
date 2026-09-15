#!/usr/bin/env python3
"""Prepare or run Kilosort4 on one standardized MCS sorter-input folder."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from axion_mea.kilosort_pipeline import binary_shape  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True, help="One folder written by prepare_mcs_sorting_inputs.py.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run", action="store_true", help="Execute Kilosort4. Without this, only write readiness metadata.")
    parser.add_argument("--do-car", dest="do_car", action="store_true", default=True)
    parser.add_argument("--no-do-car", dest="do_car", action="store_false")
    parser.add_argument("--invert-sign", action="store_true")
    parser.add_argument("--nblocks", type=int, default=0)
    parser.add_argument("--nt", type=int, default=31)
    parser.add_argument("--dmin", type=float, default=200.0)
    parser.add_argument("--dminx", type=float, default=200.0)
    parser.add_argument("--max-channel-distance", type=float, default=400.0)
    parser.add_argument("--nearest-templates", type=int, default=16)
    parser.add_argument("--nearest-chans", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.expanduser().resolve()
    prep = json.loads((input_dir / "mcs_preparation_manifest.json").read_text(encoding="utf-8"))
    binary = Path(prep["binary_file"])
    channels = list(csv.DictReader(Path(prep["channels_csv"]).open(encoding="utf-8", newline="")))
    n_chan = int(prep["n_chan_bin"])
    if len(channels) != n_chan:
        raise ValueError("channels.csv count does not match the exported binary channel count.")
    shape = binary_shape(binary, prep["binary_dtype"], n_chan, float(prep["sampling_frequency_hz"]))
    probe = {
        "n_chan": n_chan,
        "chanMap": list(range(n_chan)),
        "xc": [float(row["x_um"]) for row in channels],
        "yc": [float(row["y_um"]) for row in channels],
        "kcoords": [1] * n_chan,
    }
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = {
        "n_chan_bin": n_chan, "fs": float(prep["sampling_frequency_hz"]),
        "nblocks": args.nblocks, "nt": args.nt, "dmin": args.dmin, "dminx": args.dminx,
        "max_channel_distance": args.max_channel_distance,
        "nearest_templates": args.nearest_templates, "nearest_chans": args.nearest_chans,
    }
    manifest = {
        "analysis_kind": "mcs_60mea200_kilosort4_sorting",
        "input_preparation_manifest": str(input_dir / "mcs_preparation_manifest.json"),
        "binary": shape, "probe": probe, "settings": settings,
        "do_CAR": args.do_car, "invert_sign": args.invert_sign,
        "status": "ready_to_run" if not args.run else "prepared_for_kilosort",
        "notes": ["Reference channel excluded during standardized binary export.", "Run Kilosort on a CUDA-capable Linux environment, not this Mac."],
    }
    manifest_path = output_dir / "mcs_kilosort_ready_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if args.run:
        if not hasattr(np, "in1d"):
            np.in1d = np.isin
        from kilosort.run_kilosort import run_kilosort
        run_kilosort(settings=settings, probe={key: np.asarray(value) if key != "n_chan" else value for key, value in probe.items()}, filename=binary, results_dir=output_dir / "kilosort4", data_dtype=prep["binary_dtype"], do_CAR=args.do_car, invert_sign=args.invert_sign)
        manifest["status"] = "kilosort_finished"
        manifest["kilosort_results_dir"] = str(output_dir / "kilosort4")
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
