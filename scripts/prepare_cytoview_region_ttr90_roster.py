#!/usr/bin/env python3
"""Prepare an exact CytoView regional unit roster for waveform classification."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-unit-metrics", type=Path, required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--expected-unit-count", type=int, default=None)
    parser.add_argument("--output-roster", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = args.source_unit_metrics.expanduser().resolve()
    output_path = args.output_roster.expanduser().resolve()
    source = pd.read_csv(source_path)
    required = {"unit_key", "recording", "well", "unit_id", "region_call"}
    missing = sorted(required.difference(source.columns))
    if missing:
        raise ValueError(f"source unit metrics missing columns: {missing}")
    if "rs_fs_class" not in source.columns:
        if "aligned_fs_rs_class" not in source.columns:
            raise ValueError(
                "source unit metrics require rs_fs_class or aligned_fs_rs_class"
            )
        source["rs_fs_class"] = source["aligned_fs_rs_class"]

    region = str(args.region).strip().lower()
    roster = source.loc[
        source["region_call"].astype(str).str.strip().str.lower().eq(region)
    ].copy()
    if roster.empty:
        raise ValueError(f"no units found for region {region!r}")
    if roster["unit_key"].duplicated().any():
        duplicates = roster.loc[roster["unit_key"].duplicated(), "unit_key"].tolist()
        raise ValueError(f"duplicate unit keys in regional roster: {duplicates[:10]}")
    if args.expected_unit_count is not None and len(roster) != args.expected_unit_count:
        raise ValueError(
            f"expected {args.expected_unit_count} {region} units, found {len(roster)}"
        )

    roster["source_platform"] = "CytoView"
    roster["scope_region"] = region
    roster = roster[
        [
            "unit_key",
            "source_platform",
            "scope_region",
            "recording",
            "well",
            "unit_id",
            "rs_fs_class",
        ]
    ].copy()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    roster.to_csv(output_path, index=False)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_unit_metrics": str(source_path),
        "source_sha256": _sha256(source_path),
        "region": region,
        "unit_count": int(len(roster)),
        "recording_count": int(roster["recording"].nunique()),
        "recording_well_count": int(
            roster[["recording", "well"]].drop_duplicates().shape[0]
        ),
        "selection": "exact region_call match; no additional unit exclusions",
        "output_roster": str(output_path),
    }
    output_path.with_suffix(".provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )
    print(json.dumps(provenance, indent=2))
    return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
