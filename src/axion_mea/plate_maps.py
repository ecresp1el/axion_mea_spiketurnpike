"""Plate-map and per-well probe helpers for Axion MEA Kilosort runs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a small metadata CSV into a list of dictionaries."""
    with path.expanduser().resolve().open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def require_well_in_plate_map(plate_map_csv: Path, well: str) -> dict[str, str]:
    """Return one plate-map row, raising a clear error if the well is absent."""
    well = well.strip().upper()
    rows = read_csv_rows(plate_map_csv)
    for row in rows:
        if row.get("well", "").strip().upper() == well:
            return row
    valid = ", ".join(row.get("well", "") for row in rows)
    raise ValueError(f"Well {well!r} is not present in {plate_map_csv}. Valid wells: {valid}")


def load_electrode_geometry(electrode_geometry_csv: Path) -> list[dict[str, str]]:
    """Load connected electrode rows sorted by electrode row and column."""
    rows = [
        row
        for row in read_csv_rows(electrode_geometry_csv)
        if row.get("connected", "true").strip().lower() in {"1", "true", "yes", "y"}
    ]
    if not rows:
        raise ValueError(f"No connected electrodes found in {electrode_geometry_csv}")
    return sorted(rows, key=lambda row: (int(row["electrode_row"]), int(row["electrode_col"])))


def build_kilosort_probe(electrode_geometry_csv: Path) -> dict[str, np.ndarray | int]:
    """Build the Kilosort4 probe dictionary for one well.

    The binary row order is assumed to match the sorted geometry rows. For the
    default Axion 4x4 geometry that means channels 11, 12, 13, 14, 21, ...
    """
    rows = load_electrode_geometry(electrode_geometry_csv)
    n_chan = len(rows)
    return {
        "chanMap": np.arange(n_chan, dtype=np.int64),
        "xc": np.asarray([float(row["x_um"]) for row in rows], dtype=np.float64),
        "yc": np.asarray([float(row["y_um"]) for row in rows], dtype=np.float64),
        "kcoords": np.asarray([int(row.get("kcoords", 0) or 0) for row in rows], dtype=np.int64),
        "n_chan": n_chan,
    }


def probe_to_jsonable(probe: dict[str, np.ndarray | int]) -> dict[str, Any]:
    """Convert a Kilosort probe dictionary to JSON-serializable values."""
    jsonable: dict[str, Any] = {}
    for key, value in probe.items():
        if isinstance(value, np.ndarray):
            jsonable[key] = value.tolist()
        else:
            jsonable[key] = value
    return jsonable


def probe_from_json(path: Path) -> dict[str, np.ndarray | int]:
    """Load a probe JSON written by this repository back into Kilosort form."""
    payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    return {
        "chanMap": np.asarray(payload["chanMap"], dtype=np.int64),
        "xc": np.asarray(payload["xc"], dtype=np.float64),
        "yc": np.asarray(payload["yc"], dtype=np.float64),
        "kcoords": np.asarray(payload["kcoords"], dtype=np.int64),
        "n_chan": int(payload["n_chan"]),
    }


def write_probe_json(path: Path, electrode_geometry_csv: Path) -> dict[str, np.ndarray | int]:
    """Build and write a per-well Kilosort probe JSON."""
    probe = build_kilosort_probe(electrode_geometry_csv)
    path.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(probe_to_jsonable(probe), indent=2), encoding="utf-8")
    return probe
