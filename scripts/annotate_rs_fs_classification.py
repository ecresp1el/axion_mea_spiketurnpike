#!/usr/bin/env python
"""Annotate the canonical master unit table with RS/FS labels."""

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

from axion_mea.master_unit_table import CANONICAL_MASTER_UNIT_TABLE
from axion_mea.rs_fs_classification import (
    DEFAULT_RS_FS_SUMMARY_CSV,
    RSFSClassificationConfig,
    annotate_canonical_table_rs_fs,
)
from axion_mea.step3_repro import DEFAULT_STEP3_REPRO_DIR, write_command_repro


DEFAULT_PROVENANCE_JSON = CANONICAL_MASTER_UNIT_TABLE.with_name(
    "master_waveform_metrics_table_rs_fs_provenance.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill rs_fs_classification in the canonical Step 3 master table."
    )
    parser.add_argument("--input-csv", type=Path, default=CANONICAL_MASTER_UNIT_TABLE)
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Defaults to overwriting --input-csv atomically.",
    )
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_RS_FS_SUMMARY_CSV)
    parser.add_argument("--provenance-json", type=Path, default=DEFAULT_PROVENANCE_JSON)
    parser.add_argument("--threshold-ms", type=float, default=0.45)
    parser.add_argument("--sampling-frequency-hz", type=float, default=12500.0)
    parser.add_argument(
        "--margin-samples",
        type=float,
        default=1.0,
        help="Sample-margin around threshold. Use 0 for a hard binary FS/RS split.",
    )
    parser.add_argument("--repro-dir", type=Path, default=DEFAULT_STEP3_REPRO_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = RSFSClassificationConfig(
        trough_to_peak_threshold_ms=args.threshold_ms,
        sampling_frequency_hz=args.sampling_frequency_hz,
        classification_margin_samples=args.margin_samples,
    )
    annotated, summary = annotate_canonical_table_rs_fs(
        input_csv=args.input_csv,
        output_csv=args.output_csv,
        summary_csv=args.summary_csv,
        config=config,
    )
    output_csv = args.output_csv or args.input_csv
    command_repro = write_command_repro(
        repro_dir=args.repro_dir,
        stem="annotate_rs_fs_classification",
        parsed_args={key: str(value) for key, value in vars(args).items()},
    )
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_csv": str(args.input_csv),
        "output_csv": str(output_csv),
        "summary_csv": str(args.summary_csv),
        "row_count": int(len(annotated)),
        "classification": config.provenance(),
        "counts": {
            str(row["rs_fs_classification"]): int(row["unit_count"])
            for _, row in summary.iterrows()
        },
        "command_repro": command_repro,
    }
    args.provenance_json.parent.mkdir(parents=True, exist_ok=True)
    args.provenance_json.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(f"Annotated {len(annotated)} rows: {output_csv}")
    print(f"Wrote RS/FS summary: {args.summary_csv}")
    print(f"Wrote RS/FS provenance: {args.provenance_json}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
