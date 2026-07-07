#!/usr/bin/env python3
"""Build a standalone ground-truth inventory of Axion files on disk.

This audit is intentionally separate from the AIND pipeline. It groups files by
folder plus normalized Axion recording stem, lists raw variants and sidecars,
joins raw files to a metadata inventory when available, and flags likely naming,
metadata, or upload issues.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


RAW_SUFFIXES = (
    ("_BroadbandProcessor.raw", "broadband_processor_raw"),
    (".raw", "primary_raw"),
)

SIDECAR_SUFFIXES = (
    ("_spike_counts.csv", "spike_counts"),
    ("_spike_list.csv", "spike_list"),
    ("_electrode_burst_list.csv", "electrode_burst_list"),
    ("_network_burst_list.csv", "network_burst_list"),
    ("_lfp_event_list.csv", "lfp_event_list"),
    ("_environmental_data.csv", "environmental_data"),
    ("_NeuralEventDetector.spk", "neural_event_detector_spk"),
    (".spk", "spk"),
    (".csv", "csv"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit Axion raw files, variants, sidecars, and metadata matches."
    )
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--metadata-inventory", type=Path, default=None)
    parser.add_argument(
        "--new-root",
        type=Path,
        default=None,
        help="Optional subtree to label as the newer upload batch.",
    )
    return parser.parse_args()


def read_metadata(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None or not path.exists():
        return {}
    text = path.read_bytes().replace(b"\x00", b"").decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        raw_file = row.get("raw_file") or row.get("axis_filename") or ""
        if raw_file:
            out[str(Path(raw_file).expanduser().resolve())] = row
    return out


def is_upload_temp(path: Path) -> bool:
    name = path.name
    return ".raw." in name and not name.endswith(".raw")


def classify_raw_name(name: str) -> tuple[str | None, str | None]:
    if name.endswith("_BroadbandProcessor.raw"):
        return name[: -len("_BroadbandProcessor.raw")], "broadband_processor_raw"
    match = re.search(r"_Filter\(([^)]+)\)\.raw$", name)
    if match:
        return name[: match.start()], f"filter_{match.group(1)}"
    if name.endswith(".raw"):
        return name[: -len(".raw")], "primary_raw"
    return None, None


def classify_file_name(name: str) -> tuple[str, str]:
    raw_base, raw_kind = classify_raw_name(name)
    if raw_kind:
        return raw_base or Path(name).stem, raw_kind
    for suffix, kind in SIDECAR_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)], kind
    return Path(name).stem, "other"


def scope_for(path: Path, new_root: Path | None) -> str:
    if new_root is None:
        return "all"
    try:
        path.relative_to(new_root)
        return "new_upload"
    except ValueError:
        return "older_or_existing"


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def context_key(folder: Path, raw_root: Path, new_root: Path | None) -> str:
    """Return a date/project + barcode-ish context for duplicate-stem checks."""
    base = new_root if new_root and folder.is_relative_to(new_root) else raw_root
    try:
        parts = folder.relative_to(base).parts
    except ValueError:
        parts = folder.parts
    if len(parts) >= 2:
        return "/".join(parts[:2])
    if parts:
        return parts[0]
    return "."


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    raw_root = args.raw_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    new_root = args.new_root.expanduser().resolve() if args.new_root else None
    metadata = read_metadata(args.metadata_inventory)

    groups: dict[tuple[Path, str], dict[str, Any]] = defaultdict(
        lambda: {
            "files": [],
            "raws": [],
            "sidecars": Counter(),
            "raw_variants": Counter(),
            "plate_types": Counter(),
            "metadata_statuses": Counter(),
        }
    )
    raw_rows: list[dict[str, Any]] = []
    temp_rows: list[dict[str, Any]] = []

    candidates = [
        path
        for path in raw_root.rglob("*")
        if path.is_file()
        and (
            path.suffix.lower() in {".raw", ".csv", ".spk"}
            or is_upload_temp(path)
        )
    ]
    for path in sorted(path.resolve() for path in candidates):
        if is_upload_temp(path):
            stat = path.stat()
            temp_rows.append(
                {
                    "scope": scope_for(path, new_root),
                    "path": str(path),
                    "relative_path": rel(path, raw_root),
                    "size_bytes": stat.st_size,
                    "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    "status": "upload_temp_fragment",
                }
            )
            continue

        base, kind = classify_file_name(path.name)
        group = groups[(path.parent, base)]
        group["files"].append(path)
        group["sidecars"][kind] += 1

        _, raw_kind = classify_raw_name(path.name)
        if raw_kind:
            meta = metadata.get(str(path))
            plate_type = meta.get("plate_type_name", "") if meta else ""
            metadata_status = meta.get("status", "") if meta else "missing"
            group["raws"].append(path)
            group["raw_variants"][raw_kind] += 1
            group["plate_types"][plate_type or "metadata_missing"] += 1
            group["metadata_statuses"][metadata_status or "ok"] += 1
            stat = path.stat()
            raw_rows.append(
                {
                    "scope": scope_for(path, new_root),
                    "logical_folder": str(path.parent),
                    "logical_folder_relative": rel(path.parent, raw_root),
                    "logical_recording_stem": base,
                    "raw_variant": raw_kind,
                    "raw_file": str(path),
                    "raw_file_relative": rel(path, raw_root),
                    "raw_name": path.name,
                    "size_bytes": stat.st_size,
                    "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    "metadata_matched": bool(meta),
                    "metadata_status": metadata_status,
                    "plate_type_name": plate_type,
                    "well_dimensions": meta.get("well_dimensions", "") if meta else "",
                    "electrode_dimensions": meta.get("electrode_dimensions", "") if meta else "",
                    "num_channels": meta.get("num_channels", "") if meta else "",
                    "duration_s": meta.get("duration_s", "") if meta else "",
                    "metadata_analog_mode": meta.get("metadata_analog_mode", "") if meta else "",
                    "metadata_high_pass_filter": meta.get("metadata_high_pass_filter", "") if meta else "",
                    "metadata_high_pass_cutoff": meta.get("metadata_high_pass_cutoff", "") if meta else "",
                    "metadata_low_pass_filter": meta.get("metadata_low_pass_filter", "") if meta else "",
                    "metadata_low_pass_cutoff": meta.get("metadata_low_pass_cutoff", "") if meta else "",
                }
            )

    stem_locations: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for (folder, base), group in groups.items():
        if group["raws"]:
            stem_locations[
                (scope_for(folder, new_root), context_key(folder, raw_root, new_root), base)
            ].add(str(folder))

    group_rows: list[dict[str, Any]] = []
    issue_rows: list[dict[str, Any]] = []
    for (folder, base), group in sorted(groups.items(), key=lambda item: (str(item[0][0]), item[0][1])):
        if not group["raws"]:
            continue
        raw_variants = sorted(group["raw_variants"])
        sidecar_counts = group["sidecars"]
        issues = []
        if group["plate_types"].get("metadata_missing"):
            issues.append("raw_metadata_missing")
        if len(group["plate_types"]) > 1:
            issues.append("mixed_or_missing_plate_metadata")
        if not sidecar_counts.get("spk") and not sidecar_counts.get("neural_event_detector_spk"):
            issues.append("no_spk_sidecar")
        if not sidecar_counts.get("spike_counts"):
            issues.append("no_spike_counts_csv")
        if not sidecar_counts.get("spike_list"):
            issues.append("no_spike_list_csv")
        duplicate_key = (scope_for(folder, new_root), context_key(folder, raw_root, new_root), base)
        if len(stem_locations[duplicate_key]) > 1:
            issues.append("same_stem_in_multiple_folders_same_context")

        row = {
            "scope": scope_for(folder, new_root),
            "logical_folder": str(folder),
            "logical_folder_relative": rel(folder, raw_root),
            "context_key": context_key(folder, raw_root, new_root),
            "logical_recording_stem": base,
            "raw_file_count": len(group["raws"]),
            "raw_variants": ";".join(raw_variants),
            "plate_type_counts": json.dumps(dict(group["plate_types"]), sort_keys=True),
            "metadata_status_counts": json.dumps(dict(group["metadata_statuses"]), sort_keys=True),
            "sidecar_counts": json.dumps(dict(sidecar_counts), sort_keys=True),
            "has_primary_raw": "primary_raw" in raw_variants,
            "has_broadband_processor_raw": "broadband_processor_raw" in raw_variants,
            "has_filter_1hz_200hz": "filter_1Hz-200Hz" in raw_variants,
            "has_filter_200hz_3khz": "filter_200Hz-3kHz" in raw_variants,
            "has_spk": bool(sidecar_counts.get("spk") or sidecar_counts.get("neural_event_detector_spk")),
            "has_spike_counts_csv": bool(sidecar_counts.get("spike_counts")),
            "has_spike_list_csv": bool(sidecar_counts.get("spike_list")),
            "same_stem_folder_count": len(stem_locations[duplicate_key]),
            "issues": ";".join(issues),
        }
        group_rows.append(row)
        for issue in issues:
            issue_rows.append(
                {
                    "scope": row["scope"],
                    "logical_folder_relative": row["logical_folder_relative"],
                    "logical_recording_stem": base,
                    "issue": issue,
                    "details": row["issues"],
                }
            )

    summary = {
        "analysis_kind": "axion_file_ground_truth_audit",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "raw_root": str(raw_root),
        "new_root": str(new_root) if new_root else "",
        "metadata_inventory": str(args.metadata_inventory.expanduser().resolve()) if args.metadata_inventory else "",
        "visible_raw_files": len(raw_rows),
        "logical_raw_groups": len(group_rows),
        "upload_temp_fragments": len(temp_rows),
        "raw_files_by_scope": dict(Counter(row["scope"] for row in raw_rows)),
        "logical_groups_by_scope": dict(Counter(row["scope"] for row in group_rows)),
        "raw_files_by_plate_type": dict(Counter(row["plate_type_name"] or "metadata_missing" for row in raw_rows)),
        "raw_files_by_variant": dict(Counter(row["raw_variant"] for row in raw_rows)),
        "logical_group_variant_shapes": dict(
            Counter(row["raw_variants"] for row in group_rows)
        ),
        "issues_by_type": dict(Counter(row["issue"] for row in issue_rows)),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "raw_files.csv", raw_rows)
    write_csv(output_dir / "logical_recording_groups.csv", group_rows)
    write_csv(output_dir / "issues.csv", issue_rows)
    write_csv(output_dir / "upload_temp_fragments.csv", temp_rows)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output_dir / "ground_truth_report.md").write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Axion File Ground Truth Audit",
        "",
        f"Created: {summary['created_at']}",
        f"Raw root: `{summary['raw_root']}`",
        f"New upload root: `{summary['new_root']}`",
        f"Metadata inventory: `{summary['metadata_inventory']}`",
        "",
        "## Counts",
        "",
        f"- Visible `.raw` files: {summary['visible_raw_files']}",
        f"- Logical raw groups: {summary['logical_raw_groups']}",
        f"- Upload temp fragments: {summary['upload_temp_fragments']}",
        "",
        "## Raw Files By Scope",
        "",
    ]
    for key, value in sorted(summary["raw_files_by_scope"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Raw Files By Plate Type", ""])
    for key, value in sorted(summary["raw_files_by_plate_type"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Raw Files By Variant", ""])
    for key, value in sorted(summary["raw_files_by_variant"].items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Logical Group Variant Shapes", ""])
    for key, value in sorted(summary["logical_group_variant_shapes"].items()):
        lines.append(f"- {key or 'none'}: {value}")
    lines.extend(["", "## Issues By Type", ""])
    if summary["issues_by_type"]:
        for key, value in sorted(summary["issues_by_type"].items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Output Tables",
            "",
            "- `raw_files.csv`: one row per visible `.raw` file.",
            "- `logical_recording_groups.csv`: one row per folder/stem group.",
            "- `issues.csv`: one row per flagged issue.",
            "- `upload_temp_fragments.csv`: rsync/temp raw fragments excluded from visible raw counts.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
