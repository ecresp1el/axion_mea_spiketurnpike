#!/usr/bin/env python
"""Plot FS/RS class-average template waveforms from the canonical table."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from axion_mea.master_unit_table import CANONICAL_MASTER_UNIT_TABLE, DEFAULT_STEP2_MANIFEST
from axion_mea.rs_fs_waveform_templates import (
    DEFAULT_RS_FS_WAVEFORM_FIGURE,
    DEFAULT_RS_FS_WAVEFORM_MEAN_CSV,
    DEFAULT_RS_FS_WAVEFORM_PROVENANCE_JSON,
    RSFSWaveformPlotConfig,
    write_rs_fs_template_waveform_figure,
)
from axion_mea.step3_repro import DEFAULT_STEP3_REPRO_DIR, write_command_repro


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write FS/RS mean, overlay, and SEM waveform panels from Step 1 templates."
    )
    parser.add_argument("--input-csv", type=Path, default=CANONICAL_MASTER_UNIT_TABLE)
    parser.add_argument("--manifest-csv", type=Path, default=DEFAULT_STEP2_MANIFEST)
    parser.add_argument("--output-figure", type=Path, default=DEFAULT_RS_FS_WAVEFORM_FIGURE)
    parser.add_argument("--mean-sem-csv", type=Path, default=DEFAULT_RS_FS_WAVEFORM_MEAN_CSV)
    parser.add_argument("--provenance-json", type=Path, default=DEFAULT_RS_FS_WAVEFORM_PROVENANCE_JSON)
    parser.add_argument("--sampling-frequency-hz", type=float, default=12500.0)
    parser.add_argument("--time-min-ms", type=float, default=-1.2)
    parser.add_argument("--time-max-ms", type=float, default=4.2)
    parser.add_argument("--baseline-samples", type=int, default=5)
    parser.add_argument("--max-overlay-per-class", type=int, default=180)
    parser.add_argument("--random-seed", type=int, default=20260708)
    parser.add_argument("--repro-dir", type=Path, default=DEFAULT_STEP3_REPRO_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = RSFSWaveformPlotConfig(
        sampling_frequency_hz=args.sampling_frequency_hz,
        time_min_ms=args.time_min_ms,
        time_max_ms=args.time_max_ms,
        baseline_samples=args.baseline_samples,
        max_overlay_per_class=args.max_overlay_per_class,
        random_seed=args.random_seed,
    )
    figure_path, mean_sem_path, provenance_path = write_rs_fs_template_waveform_figure(
        input_csv=args.input_csv,
        manifest_csv=args.manifest_csv,
        output_figure=args.output_figure,
        mean_sem_csv=args.mean_sem_csv,
        provenance_json=args.provenance_json,
        config=config,
    )
    command_repro = write_command_repro(
        repro_dir=args.repro_dir,
        stem="plot_rs_fs_template_waveforms",
        parsed_args={key: str(value) for key, value in vars(args).items()},
    )
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["command_repro"] = command_repro
    provenance_path.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Wrote RS/FS waveform figure: {figure_path}")
    print(f"Wrote RS/FS waveform mean/SEM table: {mean_sem_path}")
    print(f"Wrote RS/FS waveform provenance: {provenance_path}")


if __name__ == "__main__":
    main()
