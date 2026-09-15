#!/usr/bin/env python3
"""Export validated MCS analysis HDF5 files into resumable sorter inputs.

The input is the ``conversion_manifest.csv`` made by
``convert_mcs_msrd_archive.py``.  Every successful source is re-inspected,
exported to a lossless sample-major int32 binary with the reference removed, and logged
in a separate preparation manifest.  The source HDF5 and legacy files are
never changed.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from axion_mea.io.mcs_h5 import export_mcs_binary, inspect_mcs_h5  # noqa: E402


FIELDS = [
    "experimental_group", "condition_path", "recording_stem", "source_h5_path",
    "output_dir", "binary_file", "channels_csv", "events_csv", "status",
    "sample_count", "sampling_frequency_hz", "n_chan_bin", "event_count",
    "message", "completed_utc",
]


def latest_completed_conversion_rows(path: Path) -> list[dict[str, str]]:
    """Return the latest successful conversion result for each source HDF5."""
    latest: OrderedDict[str, dict[str, str]] = OrderedDict()
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("status") in {"converted", "already_validated"}:
                latest[row["output_h5_path"]] = row
    return list(latest.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversion-manifest", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--chunk-samples", type=int, default=100_000)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    if args.chunk_samples <= 0:
        parser.error("--chunk-samples must be positive")

    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    rows = latest_completed_conversion_rows(args.conversion_manifest)
    if args.limit is not None:
        rows = rows[:args.limit]
    manifest_path = output_root / "sorting_input_manifest.csv"
    completed: set[str] = set()
    if manifest_path.exists():
        with manifest_path.open(newline="", encoding="utf-8") as handle:
            completed = {
                row["source_h5_path"] for row in csv.DictReader(handle)
                if row.get("status") in {"prepared", "already_validated"}
            }

    with manifest_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if handle.tell() == 0:
            writer.writeheader()
        for number, conversion in enumerate(rows, start=1):
            source = Path(conversion["output_h5_path"])
            output_dir = (
                output_root / conversion["experimental_group"] /
                conversion["condition_path"] / conversion["recording_stem"]
            )
            result = {
                "experimental_group": conversion["experimental_group"],
                "condition_path": conversion["condition_path"],
                "recording_stem": conversion["recording_stem"],
                "source_h5_path": str(source), "output_dir": str(output_dir),
                "binary_file": str(output_dir / "mcs_signal_channels.int32.bin"),
                "channels_csv": str(output_dir / "channels.csv"),
                "events_csv": str(output_dir / "events.csv"), "status": "",
                "sample_count": "", "sampling_frequency_hz": "", "n_chan_bin": "",
                "event_count": "", "message": "",
                "completed_utc": datetime.now(timezone.utc).isoformat(),
            }
            try:
                recording = inspect_mcs_h5(source)
                result.update({
                    "sample_count": recording.sample_count,
                    "sampling_frequency_hz": recording.sampling_frequency_hz,
                    "n_chan_bin": len(recording.signal_channel_indices),
                    "event_count": len(recording.events),
                })
                binary = Path(result["binary_file"])
                expected_bytes = recording.sample_count * len(recording.signal_channel_indices) * 4
                if str(source) in completed and binary.is_file() and binary.stat().st_size == expected_bytes:
                    result["status"] = "already_validated"
                else:
                    exported = export_mcs_binary(recording, output_dir, args.chunk_samples, output_dtype="int32")
                    result.update({
                        "binary_file": exported["binary_file"],
                        "channels_csv": exported["channels_csv"],
                        "events_csv": exported["events_csv"],
                        "status": "prepared",
                    })
            except Exception as exc:
                result.update({"status": "failed", "message": str(exc)})
            writer.writerow(result)
            handle.flush()
            print(json.dumps({"record": number, "total": len(rows), "status": result["status"], "source": str(source)}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
