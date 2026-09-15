#!/usr/bin/env python3
"""Inventory MCS acquisition packages and classify sorting-input readiness.

This audit is read-only with respect to source recordings. A package is ready
when its Multi Channel Suite v17 ``.msrd`` file is validated by the local
direct reader. No MCS vendor conversion is required.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from axion_mea.io.mcs_msrd import inspect_mcs_msrd  # noqa: E402


PRIMARY_GROUPS = {
    "Actuators & Effectors",
    "Actuators & Veh",
    "plain neurons & Effectors",
}
FIELDS = [
    "experimental_group", "group_scope", "condition_path", "recording_stem",
    "source_msrd_path", "source_msrd_size_bytes", "msrs_sidecar_present",
    "h5_path", "h5_present", "sorting_readiness", "blocking_reason",
    "next_action", "legacy_reader_status", "sampling_frequency_hz", "sample_count", "duration_s",
    "signal_channel_count", "event_count",
]


def audit(data_root: Path) -> list[dict[str, str | int | float]]:
    data_root = data_root.expanduser().resolve()
    if not data_root.is_dir():
        raise FileNotFoundError(f"Data root does not exist: {data_root}")
    rows: list[dict[str, str | int | float]] = []
    for msrd in sorted(data_root.rglob("*.msrd")):
        relative = msrd.relative_to(data_root)
        group = relative.parts[0]
        stem = msrd.name[: -len(".msrd")]
        h5 = msrd.with_name(f"{stem}.h5")
        row: dict[str, str | int | float] = {
            "experimental_group": group,
            "group_scope": "primary_experimental_group" if group in PRIMARY_GROUPS else "separate_2023_collection",
            "condition_path": str(relative.parent.relative_to(group)),
            "recording_stem": stem,
            "source_msrd_path": str(msrd),
            "source_msrd_size_bytes": msrd.stat().st_size,
            "msrs_sidecar_present": str(msrd.with_name(f"{stem}.msrs").is_file()).lower(),
            "h5_path": str(h5) if h5.is_file() else "",
            "h5_present": str(h5.is_file()).lower(),
            "sorting_readiness": "",
            "blocking_reason": "",
            "next_action": "",
            "sampling_frequency_hz": "",
            "sample_count": "",
            "duration_s": "",
            "signal_channel_count": "",
            "event_count": "",
        }
        if msrd.stat().st_size < 1_000_000:
            row.update({
                "sorting_readiness": "blocked_source_too_small",
                "blocking_reason": "The legacy .msrd file is under 1 MB and is not a plausible continuous recording.",
                "next_action": "Locate the complete recording package before attempting export.",
                "legacy_reader_status": "not_attempted_small_file",
            })
        else:
            try:
                recording = inspect_mcs_msrd(msrd)
            except ValueError as exc:
                row.update({
                    "sorting_readiness": "blocked_msrd_unreadable",
                    "blocking_reason": str(exc),
                    "next_action": "Preserve this source and investigate its file integrity before export.",
                    "legacy_reader_status": "failed",
                })
            else:
                row.update({
                    "sorting_readiness": "ready_to_export_for_sorting",
                    "blocking_reason": "",
                    "next_action": "Run run_mcs_h5_prepare.py --input-msrd <source> --export-binary, then run spike sorting on the derived 59-channel binary.",
                    "legacy_reader_status": "validated_direct_reader",
                    "sampling_frequency_hz": recording.sampling_frequency_hz,
                    "sample_count": recording.sample_count,
                    "duration_s": recording.duration_s,
                    "signal_channel_count": len(recording.signal_channel_indices),
                    "event_count": len(recording.events),
                })
        rows.append(row)
    return rows


def write_csv(rows: list[dict[str, str | int | float]], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output-csv", required=True, type=Path)
    args = parser.parse_args()
    rows = audit(args.data_root)
    write_csv(rows, args.output_csv)
    print(f"wrote={args.output_csv.resolve()}")
    for (group, readiness), count in sorted(Counter((r["experimental_group"], r["sorting_readiness"]) for r in rows).items()):
        print(f"{group}\t{readiness}\t{count}")


if __name__ == "__main__":
    main()
