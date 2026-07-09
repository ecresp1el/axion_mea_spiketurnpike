"""Select Axion wells that should proceed to per-well AIND spike sorting."""

from __future__ import annotations

import json
import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .filter_metadata import parse_axion_filter_metadata
from .plate_maps import read_csv_rows


WELL_RE = re.compile(r"^[A-F][1-8]$")
ELECTRODE_RE = re.compile(r"^(?P<well>[A-F][1-8])_(?P<channel>\d{2})$")
DEFAULT_MIN_TOTAL_SPIKES = 11


@dataclass(frozen=True)
class WellSelectionConfig:
    """Configuration for selecting useful wells before export/sorting."""

    recording_stem: str
    raw_file: Path
    plate_map_csv: Path
    output_dir: Path
    spike_counts_csv: Path | None = None
    spike_list_csv: Path | None = None
    raw_metadata_inventory_csv: Path | None = None
    min_total_spikes: int = DEFAULT_MIN_TOTAL_SPIKES
    min_active_electrodes: int = 1
    min_spikes_per_active_electrode: int = 1
    require_active_flag: bool = False
    exclude_control: bool = False


def _json_ready(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def recording_stem_from_raw_file(raw_file: Path) -> str:
    """Return the Axion recording stem shared by raw and sidecar files."""
    raw_name = raw_file.name
    if raw_name.endswith("_BroadbandProcessor.raw"):
        return raw_name[: -len("_BroadbandProcessor.raw")]
    elif raw_name.endswith(".raw"):
        return raw_name[: -len(".raw")]
    return raw_file.stem


def _default_sidecar(raw_file: Path, suffix: str) -> Path:
    stem = recording_stem_from_raw_file(raw_file)
    return raw_file.with_name(f"{stem}{suffix}")


def infer_spike_counts_csv(raw_file: Path) -> Path:
    """Infer the Axion spike-count sidecar for a primary or Broadband raw file."""
    return _default_sidecar(raw_file, "_spike_counts.csv")


def infer_spike_list_csv(raw_file: Path) -> Path:
    """Infer the Axion spike-list sidecar for a primary or Broadband raw file."""
    return _default_sidecar(raw_file, "_spike_list.csv")


def _match_inventory(inventory: pd.DataFrame, column: str, value: str) -> pd.DataFrame:
    if column not in inventory.columns:
        return pd.DataFrame()
    return inventory[inventory[column].astype(str) == value]


def _load_raw_metadata(
    inventory_csv: Path | None,
    raw_file: Path,
    recording_stem: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    status: dict[str, Any] = {
        "raw_metadata_inventory_csv": str(inventory_csv.expanduser().resolve())
        if inventory_csv
        else None,
        "raw_metadata_inventory_exists": False,
        "raw_metadata_matched": False,
        "raw_metadata_match_strategy": None,
    }
    if inventory_csv is None:
        return {}, status
    resolved = inventory_csv.expanduser().resolve()
    if not resolved.exists():
        return {}, status
    status["raw_metadata_inventory_exists"] = True
    inventory = pd.read_csv(resolved, dtype=str, keep_default_na=False)
    raw_resolved = str(raw_file.expanduser().resolve())
    matches = _match_inventory(inventory, "raw_file", raw_resolved)
    match_strategy = "raw_file"
    if len(matches) != 1:
        matches = _match_inventory(inventory, "raw_name", raw_file.name)
        match_strategy = "raw_name"
    if len(matches) != 1:
        matches = _match_inventory(inventory, "recording_stem", recording_stem)
        match_strategy = "recording_stem"
    if len(matches) == 0:
        return {}, status
    status["raw_metadata_matched"] = len(matches) == 1
    status["raw_metadata_match_strategy"] = match_strategy if len(matches) == 1 else "ambiguous"
    if len(matches) != 1:
        return {}, status
    return {key: _json_ready(value) for key, value in matches.iloc[0].to_dict().items()}, status


def _asset_status(
    *,
    raw_file: Path,
    plate_map_csv: Path,
    spike_counts_csv: Path,
    spike_list_csv: Path,
    raw_metadata: dict[str, Any],
    raw_metadata_status: dict[str, Any],
) -> dict[str, Any]:
    plate_map_exists = plate_map_csv.exists()
    raw_exists = raw_file.exists()
    spike_counts_exists = spike_counts_csv.exists()
    spike_list_exists = spike_list_csv.exists()
    status = {
        "raw_file": str(raw_file),
        "raw_file_exists": raw_exists,
        "plate_map_csv": str(plate_map_csv),
        "plate_map_exists": plate_map_exists,
        "spike_counts_csv": str(spike_counts_csv),
        "spike_counts_csv_exists": spike_counts_exists,
        "spike_list_csv": str(spike_list_csv),
        "spike_list_csv_exists": spike_list_exists,
        **raw_metadata_status,
    }
    status["can_score_activity"] = plate_map_exists and spike_counts_exists
    status["can_read_well_annotations"] = spike_list_exists
    status["can_map_raw_metadata"] = bool(status.get("raw_metadata_matched"))
    status["block_vector_warning_seen"] = _truthy(raw_metadata.get("block_vector_warning_seen"))
    status["block_vector_warning_ids"] = raw_metadata.get("block_vector_warning_ids")
    status["block_vector_warning_messages"] = raw_metadata.get("block_vector_warning_messages")
    status["can_prepare_spike_sorting_inputs"] = (
        raw_exists
        and plate_map_exists
        and spike_counts_exists
        and not status["block_vector_warning_seen"]
    )
    missing = []
    for key, present in [
        ("raw_file", raw_exists),
        ("plate_map_csv", plate_map_exists),
        ("spike_counts_csv", spike_counts_exists),
        ("spike_list_csv", spike_list_exists),
    ]:
        if not present:
            missing.append(key)
    if status.get("raw_metadata_inventory_csv") and not status.get("raw_metadata_inventory_exists"):
        missing.append("raw_metadata_inventory_csv")
    if status["block_vector_warning_seen"]:
        missing.append("block_vector_warning_seen")
    status["missing_assets"] = ";".join(missing)
    return status


def _well_metadata_map(spike_list_csv: Path | None) -> tuple[pd.DataFrame, dict[str, str]]:
    if spike_list_csv is None or not spike_list_csv.exists():
        return pd.DataFrame(columns=["well"]), {}
    recording_metadata: dict[str, str] = {}
    well_info_rows: list[list[str]] = []
    in_well_info = False
    with spike_list_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row:
                continue
            key = row[0].strip()
            if len(row) >= 2 and key and key not in recording_metadata:
                recording_metadata[key] = row[1].strip()
            if key == "Well Information":
                in_well_info = True
                continue
            if in_well_info:
                well_info_rows.append(row)
    well_metadata = _parse_well_information(well_info_rows)
    return well_metadata, recording_metadata


def _parse_well_information(rows: list[list[str]]) -> pd.DataFrame:
    if not rows or not rows[0] or rows[0][0].strip() != "Well":
        return pd.DataFrame(columns=["well"])
    wells = [item.strip() for item in rows[0][1:] if item.strip()]
    data: dict[str, list[str]] = {}
    for row in rows[1:]:
        if not row:
            continue
        label = row[0].strip()
        if not label:
            continue
        data[label] = [item.strip() for item in row[1 : 1 + len(wells)]]
    well_metadata = pd.DataFrame(data, index=wells).reset_index(names="well")
    for col in ["Active", "Control"]:
        if col in well_metadata.columns:
            well_metadata[col] = well_metadata[col].map({"True": True, "False": False, "": pd.NA})
    for col in well_metadata.columns:
        if well_metadata[col].dtype == object:
            well_metadata[col] = well_metadata[col].replace("", pd.NA)
    info_cols = [col for col in well_metadata.columns if col != "well"]
    keep_mask = well_metadata[info_cols].notna().any(axis=1) if info_cols else []
    return well_metadata.loc[keep_mask].reset_index(drop=True)


def _activity_tables(spike_counts_csv: Path | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if spike_counts_csv is None or not spike_counts_csv.exists():
        return (
            pd.DataFrame(columns=["well", "spike_count"]),
            pd.DataFrame(columns=["well", "electrode", "spike_count"]),
        )
    counts = pd.read_csv(spike_counts_csv, encoding="utf-8-sig")
    start = pd.to_numeric(counts["Interval Start (S)"], errors="coerce")
    end = pd.to_numeric(counts["Interval End (S)"], errors="coerce")
    counts = counts.loc[start.notna() & end.notna()].copy()
    counts["interval_start_s"] = pd.to_numeric(counts["Interval Start (S)"])
    counts["interval_end_s"] = pd.to_numeric(counts["Interval End (S)"])

    well_cols = [col for col in counts.columns if isinstance(col, str) and WELL_RE.fullmatch(col)]
    electrode_cols = [
        col for col in counts.columns if isinstance(col, str) and ELECTRODE_RE.fullmatch(col)
    ]
    well_frame = counts[["interval_start_s", "interval_end_s"] + well_cols].copy()
    for col in well_cols:
        well_frame[col] = pd.to_numeric(well_frame[col], errors="coerce")
    well_long = well_frame.melt(
        id_vars=["interval_start_s", "interval_end_s"],
        value_vars=well_cols,
        var_name="well",
        value_name="spike_count",
    ).dropna(subset=["spike_count"])
    well_long["spike_count"] = well_long["spike_count"].astype(int)

    electrode_frame = counts[["interval_start_s", "interval_end_s"] + electrode_cols].copy()
    for col in electrode_cols:
        electrode_frame[col] = pd.to_numeric(electrode_frame[col], errors="coerce")
    electrode_long = electrode_frame.melt(
        id_vars=["interval_start_s", "interval_end_s"],
        value_vars=electrode_cols,
        var_name="electrode",
        value_name="spike_count",
    ).dropna(subset=["spike_count"])
    electrode_long["spike_count"] = electrode_long["spike_count"].astype(int)
    electrode_long["well"] = electrode_long["electrode"].str.extract(ELECTRODE_RE)["well"]
    electrode_long["channel_in_well"] = electrode_long["electrode"].str.extract(ELECTRODE_RE)[
        "channel"
    ]
    return well_long, electrode_long


def select_wells(config: WellSelectionConfig) -> dict[str, Any]:
    """Build a well-selection manifest from plate map, sidecars, and raw metadata."""
    raw_file = config.raw_file.expanduser().resolve()
    spike_counts_csv = config.spike_counts_csv or infer_spike_counts_csv(raw_file)
    spike_list_csv = config.spike_list_csv or infer_spike_list_csv(raw_file)
    plate_map_csv = config.plate_map_csv.expanduser().resolve()
    if not plate_map_csv.exists():
        raise FileNotFoundError(f"Plate map is required for candidate wells: {plate_map_csv}")
    plate_rows = read_csv_rows(plate_map_csv)
    raw_metadata, raw_metadata_status = _load_raw_metadata(
        config.raw_metadata_inventory_csv,
        raw_file,
        config.recording_stem,
    )
    asset_status = _asset_status(
        raw_file=raw_file,
        plate_map_csv=plate_map_csv,
        spike_counts_csv=spike_counts_csv,
        spike_list_csv=spike_list_csv,
        raw_metadata=raw_metadata,
        raw_metadata_status=raw_metadata_status,
    )
    well_metadata, recording_metadata = _well_metadata_map(spike_list_csv)
    well_long, electrode_long = _activity_tables(spike_counts_csv)

    well_totals = (
        well_long.groupby("well", as_index=False)["spike_count"].sum()
        if not well_long.empty
        else pd.DataFrame(columns=["well", "spike_count"])
    )
    electrode_totals = (
        electrode_long.groupby(["well", "electrode"], as_index=False)["spike_count"].sum()
        if not electrode_long.empty
        else pd.DataFrame(columns=["well", "electrode", "spike_count"])
    )
    metadata_by_well = {
        str(row["well"]).strip().upper(): row
        for row in well_metadata.astype(object).where(pd.notna(well_metadata), None).to_dict(orient="records")
        if row.get("well")
    }
    total_by_well = {
        str(row["well"]).strip().upper(): int(row["spike_count"])
        for row in well_totals.to_dict(orient="records")
    }
    active_electrodes_by_well = {}
    if not electrode_totals.empty:
        active = electrode_totals[
            electrode_totals["spike_count"] >= config.min_spikes_per_active_electrode
        ]
        active_electrodes_by_well = active.groupby("well")["electrode"].nunique().astype(int).to_dict()

    rows: list[dict[str, Any]] = []
    for plate_index, plate_row in enumerate(plate_rows, start=1):
        well = str(plate_row.get("well", "")).strip().upper()
        if not well:
            continue
        meta = metadata_by_well.get(well, {})
        total_spikes = int(total_by_well.get(well, 0))
        active_electrodes = int(active_electrodes_by_well.get(well, 0))
        active_flag = meta.get("Active")
        control_flag = meta.get("Control")

        reasons = []
        if not asset_status["raw_file_exists"]:
            reasons.append("missing_raw_file")
        if asset_status["block_vector_warning_seen"]:
            reasons.append("block_vector_warning_seen")
        if not asset_status["spike_counts_csv_exists"]:
            reasons.append("missing_spike_counts_csv")
        else:
            if total_spikes < config.min_total_spikes:
                reasons.append(f"total_spikes<{config.min_total_spikes}")
            if active_electrodes < config.min_active_electrodes:
                reasons.append(f"active_electrodes<{config.min_active_electrodes}")
        if config.require_active_flag and not asset_status["spike_list_csv_exists"]:
            reasons.append("missing_spike_list_csv")
        if config.require_active_flag and active_flag is not True:
            reasons.append("active_flag_not_true")
        if config.exclude_control and control_flag is True:
            reasons.append("control_excluded")

        selected = not reasons
        rows.append(
            {
                "recording_stem": config.recording_stem,
                "well": well,
                "selected": selected,
                "selection_reason": "selected" if selected else ";".join(reasons),
                "total_spikes": total_spikes,
                "active_electrodes": active_electrodes,
                "active_flag": active_flag,
                "control_flag": control_flag,
                "treatment": meta.get("Treatment"),
                "plate_type": plate_row.get("plate_type") or raw_metadata.get("plate_type_name"),
                "plate_row_label": plate_row.get("row_label"),
                "plate_row_index": plate_row.get("row_index"),
                "plate_column_index": plate_row.get("column_index"),
                "plate_order_index": plate_index,
                "raw_file": str(raw_file),
                "raw_file_kind": raw_metadata.get("raw_file_kind"),
                "raw_plate_type_name": raw_metadata.get("plate_type_name"),
                "raw_duration_s": raw_metadata.get("duration_s"),
                "block_vector_warning_seen": asset_status["block_vector_warning_seen"],
                "block_vector_warning_ids": asset_status["block_vector_warning_ids"],
                "block_vector_warning_messages": asset_status["block_vector_warning_messages"],
                "spike_counts_csv": str(spike_counts_csv) if spike_counts_csv else None,
                "spike_list_csv": str(spike_list_csv) if spike_list_csv else None,
                "raw_file_exists": asset_status["raw_file_exists"],
                "plate_map_exists": asset_status["plate_map_exists"],
                "spike_counts_csv_exists": asset_status["spike_counts_csv_exists"],
                "spike_list_csv_exists": asset_status["spike_list_csv_exists"],
                "raw_metadata_inventory_exists": asset_status["raw_metadata_inventory_exists"],
                "raw_metadata_matched": asset_status["raw_metadata_matched"],
                "raw_metadata_match_strategy": asset_status["raw_metadata_match_strategy"],
                "can_score_activity": asset_status["can_score_activity"],
                "can_read_well_annotations": asset_status["can_read_well_annotations"],
                "can_map_raw_metadata": asset_status["can_map_raw_metadata"],
                "can_prepare_spike_sorting_inputs": asset_status[
                    "can_prepare_spike_sorting_inputs"
                ],
                "missing_assets": asset_status["missing_assets"],
            }
        )

    selected_rows = [row for row in rows if row["selected"]]
    selected_rows.sort(key=lambda row: (-int(row["total_spikes"]), str(row["well"])))
    rank_by_well = {row["well"]: rank for rank, row in enumerate(selected_rows, start=1)}
    for row in rows:
        row["selection_rank"] = rank_by_well.get(row["well"])

    payload = {
        "analysis_kind": "axion_well_selection_for_aind",
        "recording_stem": config.recording_stem,
        "raw_file": str(raw_file),
        "plate_map_csv": str(plate_map_csv),
        "spike_counts_csv": str(spike_counts_csv) if spike_counts_csv else None,
        "spike_list_csv": str(spike_list_csv) if spike_list_csv else None,
        "raw_metadata_inventory_csv": str(config.raw_metadata_inventory_csv.expanduser().resolve())
        if config.raw_metadata_inventory_csv
        else None,
        "criteria": {
            "min_total_spikes": config.min_total_spikes,
            "min_active_electrodes": config.min_active_electrodes,
            "min_spikes_per_active_electrode": config.min_spikes_per_active_electrode,
            "require_active_flag": config.require_active_flag,
            "exclude_control": config.exclude_control,
        },
        "asset_status": asset_status,
        "assumptions": [
            "Candidate wells are read from the plate map; the continuous raw file is not loaded during selection.",
            "Activity is scored from the Axion *_spike_counts.csv sidecar by summing interval counts per well and electrode.",
            "Well annotations such as Active, Control, and Treatment are read from the Well Information block in *_spike_list.csv when present.",
            "Raw provenance is joined from the MATLAB raw metadata inventory when one matching row is found.",
            "The default min_total_spikes is 11, meaning wells need more than 10 total spikes to pass the activity gate.",
        ],
        "recording_metadata": recording_metadata,
        "raw_metadata": raw_metadata,
        "summary": {
            "candidate_wells": len(rows),
            "selected_wells": len(selected_rows),
            "rejected_wells": len(rows) - len(selected_rows),
            "selected_well_ids": [row["well"] for row in selected_rows],
            "wells_with_assets_for_activity_scoring": len(rows)
            if asset_status["can_score_activity"]
            else 0,
            "files_missing_required_activity_assets": 0
            if asset_status["can_score_activity"]
            else 1,
            "missing_assets": asset_status["missing_assets"],
        },
        "wells": rows,
    }
    return payload


def inventory_selection_assets(
    raw_root: Path,
    output_dir: Path,
    *,
    plate_map_csv: Path | None = None,
    raw_metadata_inventory_csv: Path | None = None,
) -> dict[str, Any]:
    """Inventory raw files and the sidecars needed for well selection."""
    resolved_root = raw_root.expanduser().resolve()
    rows: list[dict[str, Any]] = []
    plate_map_resolved = plate_map_csv.expanduser().resolve() if plate_map_csv else None
    plate_map_exists = plate_map_resolved.exists() if plate_map_resolved else None
    for raw_file in sorted(resolved_root.rglob("*.raw")):
        raw_file = raw_file.resolve()
        recording_stem = recording_stem_from_raw_file(raw_file)
        spike_counts_csv = infer_spike_counts_csv(raw_file)
        spike_list_csv = infer_spike_list_csv(raw_file)
        raw_metadata, raw_metadata_status = _load_raw_metadata(
            raw_metadata_inventory_csv,
            raw_file,
            recording_stem,
        )
        filter_fields = parse_axion_filter_metadata(raw_metadata)
        status = _asset_status(
            raw_file=raw_file,
            plate_map_csv=plate_map_resolved or Path(""),
            spike_counts_csv=spike_counts_csv,
            spike_list_csv=spike_list_csv,
            raw_metadata=raw_metadata,
            raw_metadata_status=raw_metadata_status,
        )
        if plate_map_resolved is None:
            status["plate_map_csv"] = None
            status["plate_map_exists"] = None
            status["can_score_activity"] = status["spike_counts_csv_exists"]
            status["can_prepare_spike_sorting_inputs"] = (
                status["raw_file_exists"]
                and status["spike_counts_csv_exists"]
                and not status["block_vector_warning_seen"]
            )
            status["missing_assets"] = ";".join(
                [
                    asset
                    for asset, exists in [
                    ("raw_file", status["raw_file_exists"]),
                    ("spike_counts_csv", status["spike_counts_csv_exists"]),
                    ("spike_list_csv", status["spike_list_csv_exists"]),
                ]
                    if not exists
                ]
                + (["block_vector_warning_seen"] if status["block_vector_warning_seen"] else [])
            )
        row = {
            "raw_file": str(raw_file),
            "source_dir": str(raw_file.parent),
            "raw_name": raw_file.name,
            "recording_stem": recording_stem,
            "raw_file_kind": raw_metadata.get(
                "raw_file_kind",
                "broadband_processor_raw"
                if raw_file.name.endswith("_BroadbandProcessor.raw")
                else "primary_raw",
            ),
            "plate_type_name": raw_metadata.get("plate_type_name"),
            "well_dimensions": raw_metadata.get("well_dimensions"),
            "electrode_dimensions": raw_metadata.get("electrode_dimensions"),
            "num_channels": raw_metadata.get("num_channels"),
            "dataset_description": raw_metadata.get("dataset_description"),
            "metadata_analog_mode": raw_metadata.get("metadata_analog_mode"),
            "metadata_high_pass_filter": raw_metadata.get("metadata_high_pass_filter"),
            "metadata_high_pass_cutoff": raw_metadata.get("metadata_high_pass_cutoff"),
            "metadata_low_pass_filter": raw_metadata.get("metadata_low_pass_filter"),
            "metadata_low_pass_cutoff": raw_metadata.get("metadata_low_pass_cutoff"),
            "metadata_axis_version": raw_metadata.get("metadata_axis_version"),
            "metadata_instrument": raw_metadata.get("metadata_instrument"),
            "metadata_firmware_version": raw_metadata.get("metadata_firmware_version"),
            "block_vector_warning_seen": raw_metadata.get("block_vector_warning_seen"),
            "block_vector_warning_ids": raw_metadata.get("block_vector_warning_ids"),
            "block_vector_warning_messages": raw_metadata.get("block_vector_warning_messages"),
            "duration_s": raw_metadata.get("duration_s"),
            "spike_counts_csv": str(spike_counts_csv),
            "spike_list_csv": str(spike_list_csv),
            **filter_fields,
            **{
                key: status[key]
                for key in [
                    "raw_file_exists",
                    "plate_map_exists",
                    "spike_counts_csv_exists",
                    "spike_list_csv_exists",
                    "raw_metadata_inventory_exists",
                    "raw_metadata_matched",
                    "raw_metadata_match_strategy",
                    "can_score_activity",
                    "can_read_well_annotations",
                    "can_map_raw_metadata",
                    "can_prepare_spike_sorting_inputs",
                    "missing_assets",
                ]
            },
        }
        if plate_map_resolved is not None:
            row["plate_map_csv"] = str(plate_map_resolved)
        rows.append(row)

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "raw_root": str(resolved_root),
        "raw_files": len(rows),
        "files_with_activity_assets": sum(row["can_score_activity"] for row in rows),
        "files_ready_for_selection_and_sorting_prep": sum(
            row["can_prepare_spike_sorting_inputs"] for row in rows
        ),
        "files_missing_spike_counts": sum(
            not row["spike_counts_csv_exists"] for row in rows
        ),
        "files_missing_spike_list": sum(not row["spike_list_csv_exists"] for row in rows),
        "files_with_raw_metadata_match": sum(row["raw_metadata_matched"] for row in rows),
        "files_missing_any_asset": sum(bool(row["missing_assets"]) for row in rows),
    }
    payload = {
        "analysis_kind": "axion_selection_asset_inventory",
        "assumptions": [
            "Each .raw file is inventoried independently.",
            "Sidecars are inferred by removing _BroadbandProcessor.raw or .raw and appending *_spike_counts.csv and *_spike_list.csv.",
            "The inventory does not load continuous raw voltage; it checks file presence and optional MATLAB metadata matches.",
        ],
        "summary": summary,
        "files": rows,
    }
    json_path = output_dir / "aind_selection_asset_inventory.json"
    csv_path = output_dir / "aind_selection_asset_inventory.csv"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    payload["inventory_json"] = str(json_path)
    payload["inventory_csv"] = str(csv_path)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def write_selection_manifest(config: WellSelectionConfig) -> dict[str, Any]:
    """Write JSON and CSV selection manifests and return the manifest payload."""
    output_dir = config.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = select_wells(config)
    rows = payload["wells"]
    json_path = output_dir / "well_selection_manifest.json"
    csv_path = output_dir / "well_selection_manifest.csv"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    payload["manifest_json"] = str(json_path)
    payload["manifest_csv"] = str(csv_path)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def config_to_json(config: WellSelectionConfig) -> dict[str, Any]:
    """Serialize a selection config for logs."""
    payload = asdict(config)
    for key, value in payload.items():
        if isinstance(value, Path):
            payload[key] = str(value)
    return payload
