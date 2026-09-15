#!/usr/bin/env python3
"""Losslessly convert every validated MCS v17 source in a readiness CSV to HDF5.

Sources are never modified. Each output is first written as ``.partial`` and
renamed only after HDF5 closes. Existing completed outputs are revalidated and
skipped, so the job is safe to resume after interruption.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from axion_mea.io.mcs_h5 import inspect_mcs_h5  # noqa: E402
from axion_mea.io.mcs_msrd import export_msrd_h5, inspect_mcs_msrd  # noqa: E402


FIELDS = ["experimental_group", "condition_path", "recording_stem", "source_msrd_path", "output_h5_path", "status", "source_sample_count", "output_sample_count", "sampling_frequency_hz", "event_count", "message", "completed_utc"]


def validate_output(source, output: Path) -> None:
    converted = inspect_mcs_h5(output)
    checks = [
        (converted.sample_count == source.sample_count, "sample count"),
        (converted.sampling_frequency_hz == source.sampling_frequency_hz, "sampling frequency"),
        (converted.channel_labels == source.channel_labels, "channel labels"),
        (len(converted.events) == len(source.events), "event count"),
    ]
    failed = [name for passed, name in checks if not passed]
    if failed:
        raise ValueError(f"Post-write HDF5 validation failed: {', '.join(failed)}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness-csv", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of ready records to convert.")
    args = parser.parse_args()
    output_root = args.output_root.expanduser().resolve(); output_root.mkdir(parents=True, exist_ok=True)
    with args.readiness_csv.open(newline="", encoding="utf-8") as handle:
        ready = [row for row in csv.DictReader(handle) if row["sorting_readiness"] == "ready_to_export_for_sorting"]
    if args.limit is not None: ready = ready[:args.limit]
    manifest_path = output_root / "conversion_manifest.csv"
    existing = set()
    if manifest_path.exists():
        with manifest_path.open(newline="", encoding="utf-8") as handle:
            existing = {row["source_msrd_path"] for row in csv.DictReader(handle) if row["status"] in {"converted", "already_validated"}}
    with manifest_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if handle.tell() == 0: writer.writeheader()
        for number, row in enumerate(ready, 1):
            source_path = Path(row["source_msrd_path"])
            output_dir = output_root / row["experimental_group"] / row["condition_path"] / row["recording_stem"]
            output_path = output_dir / "McsRecording.analysis.h5"
            result = {key: row.get(key, "") for key in ("experimental_group", "condition_path", "recording_stem", "source_msrd_path")}
            result.update({"output_h5_path": str(output_path), "status": "", "source_sample_count": "", "output_sample_count": "", "sampling_frequency_hz": "", "event_count": "", "message": "", "completed_utc": datetime.now(timezone.utc).isoformat()})
            try:
                source = inspect_mcs_msrd(source_path)
                result.update({"source_sample_count": source.sample_count, "sampling_frequency_hz": source.sampling_frequency_hz, "event_count": len(source.events)})
                if str(source_path) in existing and output_path.is_file():
                    validate_output(source, output_path); result["status"] = "already_validated"
                else:
                    output_path = export_msrd_h5(source, output_dir)
                    validate_output(source, output_path)
                    result.update({"output_h5_path": str(output_path), "status": "converted"})
                result["output_sample_count"] = source.sample_count
            except Exception as exc:
                result.update({"status": "failed", "message": str(exc)})
            writer.writerow(result); handle.flush()
            print(json.dumps({"record": number, "total": len(ready), "status": result["status"], "source": str(source_path)}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
