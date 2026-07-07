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
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from axion_mea.io import AxionStimFile


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
    (".platemap", "platemap"),
    (".spk", "spk"),
    (".csv", "csv"),
)

PLATEMAP_LABEL_KEYWORDS = (
    "activity",
    "cl ",
    "ctrl",
    "dorsal",
    "h1",
    "ictrl",
    "mut",
    "mutant",
    "opsin",
    "pv",
    "scn8",
    "sosr",
    "ventral",
    "virus",
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


def meta_value(meta: dict[str, str] | None, key: str) -> str:
    if not meta:
        return ""
    return meta.get(key, "")


def truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def dataset_description_setting(meta: dict[str, str] | None, setting_name: str) -> str:
    description = meta_value(meta, "dataset_description")
    for line in re.split(r"[\r\n]+", description):
        parts = [part.strip() for part in line.split(",")]
        if parts and parts[0].lower() == setting_name.lower():
            return ",".join(parts[1:]).strip()
    return ""


FILTER_METADATA_FIELDS = (
    "acquisition_analog_mode_setting",
    "acquisition_digital_high_pass_filter",
    "acquisition_digital_low_pass_filter",
    "derived_high_pass_filter",
    "derived_low_pass_filter",
)


def filter_value(value: str) -> str:
    return value.strip() if value and value.strip() else "<blank>"


def filter_metadata_signature(
    analog_mode_setting: str,
    digital_high_pass_filter: str,
    digital_low_pass_filter: str,
    derived_high_pass_filter: str,
    derived_low_pass_filter: str,
) -> str:
    parts = [
        ("analog", analog_mode_setting),
        ("acquisition_hp", digital_high_pass_filter),
        ("acquisition_lp", digital_low_pass_filter),
        ("derived_hp", derived_high_pass_filter),
        ("derived_lp", derived_low_pass_filter),
    ]
    return " | ".join(f"{key}={filter_value(value)}" for key, value in parts)


def standard_export_block_reasons(
    meta: dict[str, str] | None,
    metadata_status: str,
    block_vector_warning_seen: bool,
) -> list[str]:
    reasons: list[str] = []
    if not meta:
        reasons.append("raw_metadata_missing")
    elif metadata_status and metadata_status != "ok":
        reasons.append(f"raw_metadata_status_{metadata_status}")
    if block_vector_warning_seen:
        reasons.append("block_vector_warning_seen")
    return reasons


def add_group_value(group: dict[str, Any], key: str, value: str) -> None:
    if value:
        group[key].add(value)


def numeric_values(values: set[str]) -> list[float]:
    out: list[float] = []
    for value in values:
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def has_duration_below(values: set[str], threshold_s: float) -> bool:
    durations = numeric_values(values)
    return bool(durations) and min(durations) < threshold_s


def joined_values(values: set[str]) -> str:
    return ";".join(sorted(value for value in values if value))


def joined_numeric_values(values: set[str]) -> str:
    numeric = numeric_values(values)
    return ";".join(f"{value:.9g}" for value in numeric)


def printable_strings(path: Path) -> list[str]:
    data = path.read_bytes()
    strings = []
    for match in re.finditer(rb"[\x20-\x7e]{4,}", data):
        value = match.group(0).decode("ascii", errors="ignore").strip()
        if value:
            strings.append(value)
    return strings


def likely_platemap_label(value: str) -> bool:
    normalized = " ".join(value.strip().split())
    lower = normalized.lower()
    if not normalized or lower == "axionbio":
        return False
    return any(keyword in lower for keyword in PLATEMAP_LABEL_KEYWORDS)


def extract_platemap_strings(path: Path) -> tuple[list[str], list[str]]:
    values = printable_strings(path)
    unique_values = list(dict.fromkeys(values))
    labels = [value for value in unique_values if likely_platemap_label(value)]
    return unique_values, labels


def normalize_stem_for_match(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"\(\d+\)$", "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return normalized


def stem_related(recording_stem: str, platemap_stem: str) -> bool:
    recording = normalize_stem_for_match(recording_stem)
    platemap = normalize_stem_for_match(platemap_stem)
    return (
        recording == platemap
        or recording.startswith(platemap)
        or platemap.startswith(recording)
    )


def ancestor_folders(folder: Path, stop: Path) -> list[Path]:
    folders = []
    current = folder
    while True:
        folders.append(current)
        if current == stop or current.parent == current:
            return folders
        try:
            current.parent.relative_to(stop)
        except ValueError:
            return folders
        current = current.parent


def candidate_platemaps_for_group(
    folder: Path,
    recording_stem: str,
    raw_root: Path,
    new_root: Path | None,
    platemaps_by_folder: dict[Path, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    stop = new_root if new_root and folder.is_relative_to(new_root) else raw_root
    selected: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for candidate_folder in ancestor_folders(folder, stop):
        candidates = platemaps_by_folder.get(candidate_folder, [])
        if not candidates:
            continue
        related = [
            row for row in candidates
            if stem_related(recording_stem, str(row["platemap_stem"]))
        ]
        folder_selected = related
        if not folder_selected and len(candidates) == 1:
            folder_selected = candidates
        if not folder_selected and candidate_folder == folder:
            folder_selected = candidates
        for row in folder_selected:
            path = Path(str(row["platemap_file"]))
            if path not in seen:
                selected.append(row)
                seen.add(path)
    return selected


def summarize_raw_stimulation(path: Path) -> dict[str, Any]:
    try:
        stim_file = AxionStimFile(path)
        stim_file.parse()
        events = stim_file.summarize_stimulation_events()
        event_times = [event.event_time_s for event in events]
        source_kinds = sorted({event.source_kind for event in events})
        stimulated_wells = sorted({well for event in events for well in event.stimulated_wells})
        event_descriptions = sorted({
            event.event_description for event in events if event.event_description
        })
        return {
            "stim_parse_status": "ok",
            "stim_parse_error": "",
            "stim_event_count": len(events),
            "stim_led_event_count": sum(event.source_kind == "led" for event in events),
            "stim_electrode_event_count": sum(event.source_kind == "electrode" for event in events),
            "stim_unlinked_event_count": sum(event.source_kind == "unlinked" for event in events),
            "stim_source_kinds": ";".join(source_kinds),
            "stimulated_wells": ";".join(stimulated_wells),
            "stim_first_event_time_s": min(event_times) if event_times else "",
            "stim_last_event_time_s": max(event_times) if event_times else "",
            "stim_event_time_s_values": ";".join(f"{value:.9g}" for value in event_times),
            "stim_event_descriptions": ";".join(event_descriptions),
            "opto_on_interval_count": len(stim_file.opto_on_intervals_ms()),
        }
    except Exception as exc:
        return {
            "stim_parse_status": "failed",
            "stim_parse_error": f"{type(exc).__name__}: {exc}",
            "stim_event_count": "",
            "stim_led_event_count": "",
            "stim_electrode_event_count": "",
            "stim_unlinked_event_count": "",
            "stim_source_kinds": "",
            "stimulated_wells": "",
            "stim_first_event_time_s": "",
            "stim_last_event_time_s": "",
            "stim_event_time_s_values": "",
            "stim_event_descriptions": "",
            "opto_on_interval_count": "",
        }


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
            "block_vector_start_times": set(),
            "experiment_start_times": set(),
            "added_dates": set(),
            "modified_dates": set(),
            "duration_s_values": set(),
            "sampling_frequency_hz_values": set(),
            "num_channels_values": set(),
            "metadata_recording_names": set(),
            "metadata_descriptions": set(),
            "metadata_barcodes": set(),
            "acquisition_analog_mode_settings": set(),
            "acquisition_digital_high_pass_filters": set(),
            "acquisition_digital_low_pass_filters": set(),
            "derived_high_pass_filters": set(),
            "derived_low_pass_filters": set(),
            "filter_metadata_signatures": set(),
            "block_vector_warning_files": set(),
            "block_vector_warning_ids": set(),
            "block_vector_warning_messages": set(),
            "standard_export_allowed_values": set(),
            "standard_export_block_reasons": set(),
            "stim_parse_statuses": Counter(),
            "stim_parse_errors": set(),
            "stim_event_counts": set(),
            "stim_led_event_counts": set(),
            "stim_electrode_event_counts": set(),
            "stim_unlinked_event_counts": set(),
            "stim_source_kinds": set(),
            "stimulated_wells": set(),
            "stim_first_event_times": set(),
            "stim_last_event_times": set(),
            "stim_event_time_values": set(),
            "stim_event_descriptions": set(),
            "opto_on_interval_counts": set(),
        }
    )
    raw_rows: list[dict[str, Any]] = []
    temp_rows: list[dict[str, Any]] = []
    platemap_rows: list[dict[str, Any]] = []
    platemaps_by_folder: dict[Path, list[dict[str, Any]]] = defaultdict(list)

    platemap_files = sorted(path.resolve() for path in raw_root.rglob("*.platemap") if path.is_file())
    for path in platemap_files:
        stat = path.stat()
        printable, labels = extract_platemap_strings(path)
        row = {
            "scope": scope_for(path, new_root),
            "platemap_file": str(path),
            "platemap_file_relative": rel(path, raw_root),
            "platemap_folder": str(path.parent),
            "platemap_folder_relative": rel(path.parent, raw_root),
            "platemap_stem": path.stem,
            "size_bytes": stat.st_size,
            "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            "printable_strings": ";".join(printable),
            "biology_label_candidates": ";".join(labels),
            "biology_label_candidate_count": len(labels),
        }
        platemap_rows.append(row)
        platemaps_by_folder[path.parent].append(row)

    candidates = [
        path
        for path in raw_root.rglob("*")
        if path.is_file()
        and (
            path.suffix.lower() in {".raw", ".csv", ".spk", ".platemap"}
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
            stim_summary = summarize_raw_stimulation(path)
            plate_type = meta.get("plate_type_name", "") if meta else ""
            metadata_status = meta.get("status", "") if meta else "missing"
            block_vector_warning_seen = truthy(meta_value(meta, "block_vector_warning_seen"))
            export_block_reasons = standard_export_block_reasons(
                meta, metadata_status, block_vector_warning_seen
            )
            standard_export_allowed = not export_block_reasons
            group["raws"].append(path)
            group["raw_variants"][raw_kind] += 1
            group["plate_types"][plate_type or "metadata_missing"] += 1
            group["metadata_statuses"][metadata_status or "ok"] += 1
            add_group_value(group, "block_vector_start_times", meta_value(meta, "block_vector_start_time"))
            add_group_value(group, "experiment_start_times", meta_value(meta, "experiment_start_time"))
            add_group_value(group, "added_dates", meta_value(meta, "added_date"))
            add_group_value(group, "modified_dates", meta_value(meta, "modified_date"))
            add_group_value(group, "duration_s_values", meta_value(meta, "duration_s"))
            add_group_value(group, "sampling_frequency_hz_values", meta_value(meta, "sampling_frequency_hz"))
            add_group_value(group, "num_channels_values", meta_value(meta, "num_channels"))
            add_group_value(group, "metadata_recording_names", meta_value(meta, "metadata_recording_name"))
            add_group_value(group, "metadata_descriptions", meta_value(meta, "metadata_description"))
            add_group_value(group, "metadata_barcodes", meta_value(meta, "metadata_barcode"))
            if block_vector_warning_seen:
                add_group_value(group, "block_vector_warning_files", rel(path, raw_root))
            add_group_value(group, "block_vector_warning_ids", meta_value(meta, "block_vector_warning_ids"))
            add_group_value(group, "block_vector_warning_messages", meta_value(meta, "block_vector_warning_messages"))
            add_group_value(group, "standard_export_allowed_values", str(standard_export_allowed).lower())
            for reason in export_block_reasons:
                add_group_value(group, "standard_export_block_reasons", reason)
            analog_mode_setting = dataset_description_setting(meta, "Analog Mode Setting") or meta_value(meta, "metadata_analog_mode")
            digital_high_pass_filter = dataset_description_setting(meta, "Digital High Pass Filter")
            digital_low_pass_filter = dataset_description_setting(meta, "Digital Low Pass Filter")
            derived_high_pass_filter = dataset_description_setting(meta, "High Pass Filter")
            derived_low_pass_filter = dataset_description_setting(meta, "Low Pass Filter")
            filter_signature = filter_metadata_signature(
                analog_mode_setting,
                digital_high_pass_filter,
                digital_low_pass_filter,
                derived_high_pass_filter,
                derived_low_pass_filter,
            )
            add_group_value(group, "acquisition_analog_mode_settings", analog_mode_setting)
            add_group_value(group, "acquisition_digital_high_pass_filters", digital_high_pass_filter)
            add_group_value(group, "acquisition_digital_low_pass_filters", digital_low_pass_filter)
            add_group_value(group, "derived_high_pass_filters", derived_high_pass_filter)
            add_group_value(group, "derived_low_pass_filters", derived_low_pass_filter)
            add_group_value(group, "filter_metadata_signatures", filter_signature)
            group["stim_parse_statuses"][str(stim_summary["stim_parse_status"])] += 1
            add_group_value(group, "stim_parse_errors", str(stim_summary["stim_parse_error"]))
            add_group_value(group, "stim_event_counts", str(stim_summary["stim_event_count"]))
            add_group_value(group, "stim_led_event_counts", str(stim_summary["stim_led_event_count"]))
            add_group_value(group, "stim_electrode_event_counts", str(stim_summary["stim_electrode_event_count"]))
            add_group_value(group, "stim_unlinked_event_counts", str(stim_summary["stim_unlinked_event_count"]))
            for source_kind in str(stim_summary["stim_source_kinds"]).split(";"):
                add_group_value(group, "stim_source_kinds", source_kind)
            for well in str(stim_summary["stimulated_wells"]).split(";"):
                add_group_value(group, "stimulated_wells", well)
            add_group_value(group, "stim_first_event_times", str(stim_summary["stim_first_event_time_s"]))
            add_group_value(group, "stim_last_event_times", str(stim_summary["stim_last_event_time_s"]))
            for event_time in str(stim_summary["stim_event_time_s_values"]).split(";"):
                add_group_value(group, "stim_event_time_values", event_time)
            for description in str(stim_summary["stim_event_descriptions"]).split(";"):
                add_group_value(group, "stim_event_descriptions", description)
            add_group_value(group, "opto_on_interval_counts", str(stim_summary["opto_on_interval_count"]))
            stat = path.stat()
            raw_row = {
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
                "sampling_frequency_hz": meta.get("sampling_frequency_hz", "") if meta else "",
                "block_vector_start_time": meta.get("block_vector_start_time", "") if meta else "",
                "experiment_start_time": meta.get("experiment_start_time", "") if meta else "",
                "added_date": meta.get("added_date", "") if meta else "",
                "metadata_modified_date": meta.get("modified_date", "") if meta else "",
                "duration_s": meta.get("duration_s", "") if meta else "",
                "metadata_analog_mode": meta.get("metadata_analog_mode", "") if meta else "",
                "metadata_high_pass_filter": meta.get("metadata_high_pass_filter", "") if meta else "",
                "metadata_high_pass_cutoff": meta.get("metadata_high_pass_cutoff", "") if meta else "",
                "metadata_low_pass_filter": meta.get("metadata_low_pass_filter", "") if meta else "",
                "metadata_low_pass_cutoff": meta.get("metadata_low_pass_cutoff", "") if meta else "",
                "metadata_recording_name": meta.get("metadata_recording_name", "") if meta else "",
                "metadata_description": meta.get("metadata_description", "") if meta else "",
                "metadata_barcode": meta.get("metadata_barcode", "") if meta else "",
                "block_vector_warning_seen": block_vector_warning_seen,
                "block_vector_warning_ids": meta.get("block_vector_warning_ids", "") if meta else "",
                "block_vector_warning_messages": meta.get("block_vector_warning_messages", "") if meta else "",
                "standard_export_allowed": standard_export_allowed,
                "standard_export_block_reasons": ";".join(export_block_reasons),
                "acquisition_analog_mode_setting": analog_mode_setting,
                "acquisition_digital_high_pass_filter": digital_high_pass_filter,
                "acquisition_digital_low_pass_filter": digital_low_pass_filter,
                "derived_high_pass_filter": derived_high_pass_filter,
                "derived_low_pass_filter": derived_low_pass_filter,
                "filter_metadata_signature": filter_signature,
            }
            raw_row.update(stim_summary)
            raw_rows.append(raw_row)

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
        if group["block_vector_warning_files"]:
            issues.append("block_vector_warning_seen")
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
        durations = numeric_values(group["duration_s_values"])
        duration_min_s = min(durations) if durations else ""
        duration_max_s = max(durations) if durations else ""
        if has_duration_below(group["duration_s_values"], 120.0):
            issues.append("duration_under_2min_unusable")
        stim_event_counts = numeric_values(group["stim_event_counts"])
        stim_led_event_counts = numeric_values(group["stim_led_event_counts"])
        stim_electrode_event_counts = numeric_values(group["stim_electrode_event_counts"])
        stim_first_event_times = numeric_values(group["stim_first_event_times"])
        stim_last_event_times = numeric_values(group["stim_last_event_times"])
        has_stim_events = any(value > 0 for value in stim_event_counts)
        has_led_stim = any(value > 0 for value in stim_led_event_counts)
        has_electrode_stim = any(value > 0 for value in stim_electrode_event_counts)
        standard_export_allowed_values = group["standard_export_allowed_values"]
        standard_export_allowed_raw_count = group["standard_export_allowed_values"].count("true") if hasattr(group["standard_export_allowed_values"], "count") else sum(
            1 for raw in group["raws"]
            if not standard_export_block_reasons(
                metadata.get(str(raw)),
                metadata.get(str(raw), {}).get("status", "") if metadata.get(str(raw)) else "missing",
                truthy(meta_value(metadata.get(str(raw)), "block_vector_warning_seen")),
            )
        )
        standard_export_blocked_raw_count = len(group["raws"]) - standard_export_allowed_raw_count
        if group["stim_parse_statuses"].get("failed"):
            issues.append("stim_parse_failed")
        if has_led_stim:
            issues.append("has_led_stimulation")
        elif has_electrode_stim:
            issues.append("has_electrode_stimulation")
        elif has_stim_events:
            issues.append("has_unresolved_stimulation")
        candidate_platemaps = candidate_platemaps_for_group(
            folder, base, raw_root, new_root, platemaps_by_folder
        )
        if not candidate_platemaps:
            issues.append("missing_candidate_platemap")
        candidate_platemap_files = [
            rel(Path(str(row["platemap_file"])), raw_root) for row in candidate_platemaps
        ]
        candidate_platemap_labels = sorted({
            label
            for row in candidate_platemaps
            for label in str(row["biology_label_candidates"]).split(";")
            if label
        })

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
            "block_vector_start_times": joined_values(group["block_vector_start_times"]),
            "experiment_start_times": joined_values(group["experiment_start_times"]),
            "added_dates": joined_values(group["added_dates"]),
            "metadata_modified_dates": joined_values(group["modified_dates"]),
            "duration_s_values": joined_values(group["duration_s_values"]),
            "duration_min_s": duration_min_s,
            "duration_max_s": duration_max_s,
            "duration_max_min": round(duration_max_s / 60, 3) if duration_max_s != "" else "",
            "sampling_frequency_hz_values": joined_values(group["sampling_frequency_hz_values"]),
            "num_channels_values": joined_values(group["num_channels_values"]),
            "metadata_recording_names": joined_values(group["metadata_recording_names"]),
            "metadata_descriptions": joined_values(group["metadata_descriptions"]),
            "metadata_barcodes": joined_values(group["metadata_barcodes"]),
            "block_vector_warning_seen": bool(group["block_vector_warning_files"]),
            "block_vector_warning_files": joined_values(group["block_vector_warning_files"]),
            "block_vector_warning_ids": joined_values(group["block_vector_warning_ids"]),
            "block_vector_warning_messages": joined_values(group["block_vector_warning_messages"]),
            "has_standard_export_allowed_raw": "true" in standard_export_allowed_values,
            "standard_export_allowed_raw_count": standard_export_allowed_raw_count,
            "standard_export_blocked_raw_count": standard_export_blocked_raw_count,
            "standard_export_block_reasons": joined_values(group["standard_export_block_reasons"]),
            "acquisition_analog_mode_settings": joined_values(group["acquisition_analog_mode_settings"]),
            "acquisition_digital_high_pass_filters": joined_values(group["acquisition_digital_high_pass_filters"]),
            "acquisition_digital_low_pass_filters": joined_values(group["acquisition_digital_low_pass_filters"]),
            "derived_high_pass_filters": joined_values(group["derived_high_pass_filters"]),
            "derived_low_pass_filters": joined_values(group["derived_low_pass_filters"]),
            "filter_metadata_signatures": joined_values(group["filter_metadata_signatures"]),
            "stim_parse_status_counts": json.dumps(dict(group["stim_parse_statuses"]), sort_keys=True),
            "stim_parse_errors": joined_values(group["stim_parse_errors"]),
            "has_stim_events": has_stim_events,
            "has_led_stimulation": has_led_stim,
            "has_electrode_stimulation": has_electrode_stim,
            "stim_event_count_values": joined_numeric_values(group["stim_event_counts"]),
            "stim_event_count_max": max(stim_event_counts) if stim_event_counts else "",
            "stim_led_event_count_values": joined_numeric_values(group["stim_led_event_counts"]),
            "stim_led_event_count_max": max(stim_led_event_counts) if stim_led_event_counts else "",
            "stim_electrode_event_count_values": joined_numeric_values(group["stim_electrode_event_counts"]),
            "stim_electrode_event_count_max": max(stim_electrode_event_counts) if stim_electrode_event_counts else "",
            "stim_unlinked_event_count_values": joined_numeric_values(group["stim_unlinked_event_counts"]),
            "stim_source_kinds": joined_values(group["stim_source_kinds"]),
            "stimulated_wells": joined_values(group["stimulated_wells"]),
            "stim_first_event_time_s": min(stim_first_event_times) if stim_first_event_times else "",
            "stim_last_event_time_s": max(stim_last_event_times) if stim_last_event_times else "",
            "stim_event_time_s_values": joined_numeric_values(group["stim_event_time_values"]),
            "stim_event_descriptions": joined_values(group["stim_event_descriptions"]),
            "opto_on_interval_count_values": joined_numeric_values(group["opto_on_interval_counts"]),
            "candidate_platemap_count": len(candidate_platemaps),
            "candidate_platemap_files": ";".join(candidate_platemap_files),
            "candidate_platemap_label_candidates": ";".join(candidate_platemap_labels),
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

    filter_metadata_signature_rows: list[dict[str, Any]] = []
    signatures = sorted({row["filter_metadata_signature"] for row in raw_rows})
    for signature in signatures:
        rows = [row for row in raw_rows if row["filter_metadata_signature"] == signature]
        groups_with_signature = {
            (row["logical_folder_relative"], row["logical_recording_stem"]) for row in rows
        }
        first = rows[0]
        filter_metadata_signature_rows.append(
            {
                "filter_metadata_signature": signature,
                "raw_file_count": len(rows),
                "logical_group_count": len(groups_with_signature),
                "raw_variants": ";".join(sorted({row["raw_variant"] for row in rows})),
                "scopes": ";".join(sorted({row["scope"] for row in rows})),
                "plate_type_names": ";".join(
                    sorted({row["plate_type_name"] for row in rows if row["plate_type_name"]})
                ),
                "acquisition_analog_mode_setting": first["acquisition_analog_mode_setting"],
                "acquisition_digital_high_pass_filter": first["acquisition_digital_high_pass_filter"],
                "acquisition_digital_low_pass_filter": first["acquisition_digital_low_pass_filter"],
                "derived_high_pass_filter": first["derived_high_pass_filter"],
                "derived_low_pass_filter": first["derived_low_pass_filter"],
            }
        )

    filter_metadata_value_rows: list[dict[str, Any]] = []
    for field in FILTER_METADATA_FIELDS:
        values = sorted({filter_value(str(row.get(field, ""))) for row in raw_rows})
        for value in values:
            rows = [row for row in raw_rows if filter_value(str(row.get(field, ""))) == value]
            groups_with_value = {
                (row["logical_folder_relative"], row["logical_recording_stem"]) for row in rows
            }
            filter_metadata_value_rows.append(
                {
                    "field": field,
                    "value": value,
                    "raw_file_count": len(rows),
                    "logical_group_count": len(groups_with_value),
                    "raw_variants": ";".join(sorted({row["raw_variant"] for row in rows})),
                    "scopes": ";".join(sorted({row["scope"] for row in rows})),
                    "plate_type_names": ";".join(
                        sorted({row["plate_type_name"] for row in rows if row["plate_type_name"]})
                    ),
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
        "platemap_files": len(platemap_rows),
        "platemap_files_with_label_candidates": sum(
            bool(row["biology_label_candidates"]) for row in platemap_rows
        ),
        "upload_temp_fragments": len(temp_rows),
        "raw_files_by_scope": dict(Counter(row["scope"] for row in raw_rows)),
        "logical_groups_by_scope": dict(Counter(row["scope"] for row in group_rows)),
        "raw_files_by_plate_type": dict(Counter(row["plate_type_name"] or "metadata_missing" for row in raw_rows)),
        "raw_files_by_variant": dict(Counter(row["raw_variant"] for row in raw_rows)),
        "raw_files_by_filter_metadata_signature": dict(
            Counter(row["filter_metadata_signature"] for row in raw_rows)
        ),
        "raw_files_by_standard_export_allowed": dict(
            Counter(str(row["standard_export_allowed"]).lower() for row in raw_rows)
        ),
        "raw_files_by_standard_export_block_reason": dict(
            Counter(
                reason
                for row in raw_rows
                for reason in str(row["standard_export_block_reasons"]).split(";")
                if reason
            )
        ),
        "platemap_files_by_scope": dict(Counter(row["scope"] for row in platemap_rows)),
        "raw_files_by_stim_parse_status": dict(Counter(row["stim_parse_status"] for row in raw_rows)),
        "raw_files_with_stim_events": sum(
            int(row["stim_event_count"] or 0) > 0 for row in raw_rows
        ),
        "logical_groups_with_stim_events": sum(row["has_stim_events"] for row in group_rows),
        "logical_groups_with_led_stimulation": sum(row["has_led_stimulation"] for row in group_rows),
        "logical_groups_with_electrode_stimulation": sum(
            row["has_electrode_stimulation"] for row in group_rows
        ),
        "logical_group_variant_shapes": dict(
            Counter(row["raw_variants"] for row in group_rows)
        ),
        "logical_group_filter_metadata_shapes": dict(
            Counter(row["filter_metadata_signatures"] for row in group_rows)
        ),
        "issues_by_type": dict(Counter(row["issue"] for row in issue_rows)),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "raw_files.csv", raw_rows)
    write_csv(output_dir / "logical_recording_groups.csv", group_rows)
    write_csv(output_dir / "filter_metadata_signatures.csv", filter_metadata_signature_rows)
    write_csv(output_dir / "filter_metadata_value_counts.csv", filter_metadata_value_rows)
    write_csv(output_dir / "platemap_files.csv", platemap_rows)
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
        f"- `.platemap` files: {summary['platemap_files']}",
        f"- `.platemap` files with candidate biology labels: {summary['platemap_files_with_label_candidates']}",
        f"- Upload temp fragments: {summary['upload_temp_fragments']}",
        f"- Raw files with stimulation events: {summary['raw_files_with_stim_events']}",
        f"- Logical groups with stimulation events: {summary['logical_groups_with_stim_events']}",
        f"- Logical groups with LED stimulation: {summary['logical_groups_with_led_stimulation']}",
        f"- Logical groups with electrode stimulation: {summary['logical_groups_with_electrode_stimulation']}",
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
    lines.extend(["", "## Raw Files By Filter Metadata Signature", ""])
    if summary["raw_files_by_filter_metadata_signature"]:
        for key, value in sorted(summary["raw_files_by_filter_metadata_signature"].items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.extend(["", "## Raw Files By Standard Export Allowed", ""])
    if summary["raw_files_by_standard_export_allowed"]:
        for key, value in sorted(summary["raw_files_by_standard_export_allowed"].items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.extend(["", "## Raw Files By Standard Export Block Reason", ""])
    if summary["raw_files_by_standard_export_block_reason"]:
        for key, value in sorted(summary["raw_files_by_standard_export_block_reason"].items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.extend(["", "## Raw Files By Stim Parse Status", ""])
    if summary["raw_files_by_stim_parse_status"]:
        for key, value in sorted(summary["raw_files_by_stim_parse_status"].items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.extend(["", "## Platemap Files By Scope", ""])
    if summary["platemap_files_by_scope"]:
        for key, value in sorted(summary["platemap_files_by_scope"].items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.extend(["", "## Logical Group Variant Shapes", ""])
    for key, value in sorted(summary["logical_group_variant_shapes"].items()):
        lines.append(f"- {key or 'none'}: {value}")
    lines.extend(["", "## Logical Group Filter Metadata Shapes", ""])
    for key, value in sorted(summary["logical_group_filter_metadata_shapes"].items()):
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
            "- `filter_metadata_signatures.csv`: one row per distinct combined filter metadata signature.",
            "- `filter_metadata_value_counts.csv`: one row per observed value for each filter metadata field.",
            "- `platemap_files.csv`: one row per `.platemap` file, with extracted candidate biology labels.",
            "- `issues.csv`: one row per flagged issue.",
            "- `upload_temp_fragments.csv`: rsync/temp raw fragments excluded from visible raw counts.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
