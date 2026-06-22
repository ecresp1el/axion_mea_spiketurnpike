#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from axion_mea import AxionProjectBuilder, ProjectBuildConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a reproducible Axion MEA optogenetic response project."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("/Volumes/MannySSD/maestro_pro_output_meas/6_22_2026/129-8445"),
        help="Folder containing the raw/spk/csv files for one recording.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("/Volumes/MannySSD/axion_mea_projects"),
        help="Base directory where project folders will be created.",
    )
    parser.add_argument(
        "--project-name",
        type=str,
        default=None,
        help="Optional override for the project folder name.",
    )
    parser.add_argument("--pre-ms", type=float, default=100.0, help="Milliseconds before train onset.")
    parser.add_argument("--post-ms", type=float, default=1000.0, help="Milliseconds after train onset.")
    parser.add_argument(
        "--pulse-pre-ms",
        type=float,
        default=10.0,
        help="Milliseconds before pulse onset for pulse-aligned views.",
    )
    parser.add_argument(
        "--pulse-post-ms",
        type=float,
        default=40.0,
        help="Milliseconds after pulse onset for pulse-aligned views.",
    )
    parser.add_argument("--train-bin-ms", type=float, default=20.0, help="Bin width for train-aligned PSTHs.")
    parser.add_argument(
        "--boxcar-kernel",
        type=float,
        nargs="+",
        default=[1.0, 1.0, 1.0],
        help="Smoothing kernel for train-aligned PSTHs.",
    )
    parser.add_argument(
        "--top-channels-per-well",
        type=int,
        default=4,
        help="Number of stimulated channels to plot per well in the aligned raster stage.",
    )
    parser.add_argument(
        "--max-wells",
        type=int,
        default=8,
        help="Maximum number of active wells in the CSV exploration channel overview.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ProjectBuildConfig(
        data_dir=args.data_dir,
        project_root=args.project_root,
        project_name=args.project_name,
        pre_ms=args.pre_ms,
        post_ms=args.post_ms,
        pulse_pre_ms=args.pulse_pre_ms,
        pulse_post_ms=args.pulse_post_ms,
        train_bin_ms=args.train_bin_ms,
        boxcar_kernel=tuple(args.boxcar_kernel),
        top_channels_per_well=args.top_channels_per_well,
        max_wells=args.max_wells,
    )
    project_root = AxionProjectBuilder(config).run()
    print(f"Project built: {project_root}")


if __name__ == "__main__":
    main()
