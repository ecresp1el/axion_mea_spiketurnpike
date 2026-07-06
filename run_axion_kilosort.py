#!/usr/bin/env python3
"""Prepare or run Kilosort4 for one Axion MEA well."""

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

from axion_mea.kilosort_pipeline import KilosortWellConfig, bool_from_text, config_to_json, run_kilosort4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an Axion per-well binary/probe pair and optionally run Kilosort4."
    )
    parser.add_argument("--binary-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--well", required=True)
    parser.add_argument("--plate-map", type=Path, required=True)
    parser.add_argument("--electrode-geometry", type=Path, required=True)
    parser.add_argument("--recording-stem", default=None)
    parser.add_argument("--fs", type=float, default=12500.0)
    parser.add_argument("--dtype", default="int16")
    parser.add_argument("--n-chan-bin", type=int, default=16)
    parser.add_argument("--do-car", dest="do_car", action="store_true", default=True)
    parser.add_argument("--no-do-car", dest="do_car", action="store_false")
    parser.add_argument("--invert-sign", action="store_true")
    parser.add_argument("--clear-cache", action="store_true")
    parser.add_argument("--save-preprocessed-copy", action="store_true")
    parser.add_argument("--torch-thread-lim", type=int, default=None)
    parser.add_argument("--nblocks", type=int, default=0)
    parser.add_argument("--nt", type=int, default=31)
    parser.add_argument("--nt0min", type=int, default=None)
    parser.add_argument("--dmin", type=float, default=350.0)
    parser.add_argument("--dminx", type=float, default=350.0)
    parser.add_argument("--max-channel-distance", type=float, default=400.0)
    parser.add_argument("--x-centers", type=int, default=4)
    parser.add_argument("--nearest-templates", type=int, default=16)
    parser.add_argument("--nearest-chans", type=int, default=5)
    parser.add_argument("--min-template-size", type=float, default=50.0)
    parser.add_argument("--whitening-range", type=int, default=8)
    parser.add_argument("--th-universal", type=float, default=9.0)
    parser.add_argument("--th-learned", type=float, default=8.0)
    parser.add_argument("--th-single-ch", type=float, default=6.0)
    parser.add_argument(
        "--run",
        action="store_true",
        help="Actually execute Kilosort. Without this flag the command only writes readiness metadata.",
    )
    parser.add_argument(
        "--run-from-env",
        default=None,
        help="Optional shell boolean, typically RUN_KILOSORT, used by Slurm wrappers.",
    )
    parser.add_argument("--run-command", default=None)
    parser.add_argument("--working-directory", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = KilosortWellConfig(
        binary_file=args.binary_file,
        output_dir=args.output_dir,
        well=args.well,
        plate_map_csv=args.plate_map,
        electrode_geometry_csv=args.electrode_geometry,
        recording_stem=args.recording_stem,
        fs=args.fs,
        dtype=args.dtype,
        n_chan_bin=args.n_chan_bin,
        do_car=args.do_car,
        invert_sign=args.invert_sign,
        run_kilosort=args.run or bool_from_text(args.run_from_env, default=False),
        clear_cache=args.clear_cache,
        save_preprocessed_copy=args.save_preprocessed_copy,
        torch_thread_lim=args.torch_thread_lim,
        nblocks=args.nblocks,
        nt=args.nt,
        nt0min=args.nt0min,
        dmin=args.dmin,
        dminx=args.dminx,
        max_channel_distance=args.max_channel_distance,
        x_centers=args.x_centers,
        nearest_templates=args.nearest_templates,
        nearest_chans=args.nearest_chans,
        min_template_size=args.min_template_size,
        whitening_range=args.whitening_range,
        th_universal=args.th_universal,
        th_learned=args.th_learned,
        th_single_ch=args.th_single_ch,
        run_command=args.run_command or shlex.join([sys.executable, *sys.argv]),
        command_argv=[sys.executable, *sys.argv],
        working_directory=args.working_directory or os.getcwd(),
    )
    print(json.dumps({"config": config_to_json(config)}, indent=2))
    manifest = run_kilosort4(config)
    print(json.dumps({"manifest": manifest}, indent=2))


if __name__ == "__main__":
    main()
