#!/usr/bin/env python
"""Write RS/FS interpretation plots from the canonical Step 3 table."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from axion_mea.master_unit_table import CANONICAL_MASTER_UNIT_TABLE, load_canonical_master_unit_table
from axion_mea.rs_fs_classification import RSFSClassificationConfig
from axion_mea.rs_fs_plots import DEFAULT_RS_FS_FIGURE_DIR, write_rs_fs_plots
from axion_mea.step3_repro import DEFAULT_STEP3_REPRO_DIR, write_command_repro


DEFAULT_PLOT_PROVENANCE_JSON = CANONICAL_MASTER_UNIT_TABLE.with_name(
    "master_waveform_metrics_table_rs_fs_plot_provenance.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot RS/FS classifications from the canonical Step 3 table.")
    parser.add_argument("--input-csv", type=Path, default=CANONICAL_MASTER_UNIT_TABLE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RS_FS_FIGURE_DIR)
    parser.add_argument("--provenance-json", type=Path, default=DEFAULT_PLOT_PROVENANCE_JSON)
    parser.add_argument("--threshold-ms", type=float, default=0.45)
    parser.add_argument("--sampling-frequency-hz", type=float, default=12500.0)
    parser.add_argument("--margin-samples", type=float, default=1.0)
    parser.add_argument("--repro-dir", type=Path, default=DEFAULT_STEP3_REPRO_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = RSFSClassificationConfig(
        trough_to_peak_threshold_ms=args.threshold_ms,
        sampling_frequency_hz=args.sampling_frequency_hz,
        classification_margin_samples=args.margin_samples,
    )
    table = load_canonical_master_unit_table(args.input_csv)
    outputs = write_rs_fs_plots(
        table=table,
        input_csv=args.input_csv,
        output_dir=args.output_dir,
        config=config,
    )
    command_repro = write_command_repro(
        repro_dir=args.repro_dir,
        stem="plot_rs_fs_classification",
        parsed_args={key: str(value) for key, value in vars(args).items()},
    )
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_csv": str(args.input_csv),
        "output_dir": str(args.output_dir),
        "row_count": int(len(table)),
        "classification_counts": table["rs_fs_classification"].value_counts(dropna=False).to_dict(),
        "classification": config.provenance(),
        "figures": {key: str(path) for key, path in outputs.items()},
        "command_repro": command_repro,
    }
    args.provenance_json.parent.mkdir(parents=True, exist_ok=True)
    args.provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Wrote {len(outputs)} RS/FS figures to {args.output_dir}")
    for key, path in outputs.items():
        print(f"{key}: {path}")
    print(f"Wrote plot provenance: {args.provenance_json}")


if __name__ == "__main__":
    main()
