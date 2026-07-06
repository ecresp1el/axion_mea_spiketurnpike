"""Readiness checks and execution helpers for Axion MEA Kilosort4 runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .plate_maps import probe_to_jsonable, require_well_in_plate_map, write_probe_json


@dataclass(frozen=True)
class KilosortWellConfig:
    """Configuration for one well-level Kilosort run."""

    binary_file: Path
    output_dir: Path
    well: str
    plate_map_csv: Path
    electrode_geometry_csv: Path
    recording_stem: str | None = None
    fs: float = 12500.0
    dtype: str = "int16"
    n_chan_bin: int = 16
    do_car: bool = True
    invert_sign: bool = False
    run_kilosort: bool = False
    clear_cache: bool = False
    save_preprocessed_copy: bool = False
    torch_thread_lim: int | None = None


def bool_from_text(value: str | bool | None, default: bool = False) -> bool:
    """Parse shell-style booleans."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def binary_shape(binary_file: Path, dtype: str, n_chan_bin: int, fs: float) -> dict[str, Any]:
    """Validate binary divisibility and return sample-count metadata."""
    path = binary_file.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Kilosort binary does not exist: {path}")
    np_dtype = np.dtype(dtype)
    bytes_per_sample = np_dtype.itemsize * n_chan_bin
    size_bytes = path.stat().st_size
    if size_bytes % bytes_per_sample != 0:
        raise ValueError(
            f"{path} has {size_bytes} bytes, which is not divisible by "
            f"dtype.itemsize({np_dtype.itemsize}) * n_chan_bin({n_chan_bin})."
        )
    n_samples = size_bytes // bytes_per_sample
    return {
        "binary_file": str(path),
        "dtype": np_dtype.name,
        "n_chan_bin": n_chan_bin,
        "size_bytes": size_bytes,
        "n_samples": n_samples,
        "duration_s": n_samples / fs if fs else None,
    }


def prepare_well_run(config: KilosortWellConfig) -> dict[str, Any]:
    """Write probe/readiness metadata for one well and return the manifest."""
    output_dir = config.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    plate_row = require_well_in_plate_map(config.plate_map_csv, config.well)
    probe_path = output_dir / "probe.json"
    probe = write_probe_json(probe_path, config.electrode_geometry_csv)
    shape = binary_shape(config.binary_file, config.dtype, config.n_chan_bin, config.fs)
    if int(probe["n_chan"]) != config.n_chan_bin:
        raise ValueError(
            f"Probe geometry has {probe['n_chan']} channels but n_chan_bin={config.n_chan_bin}. "
            "Update N_CHAN_BIN or the electrode geometry."
        )

    manifest = {
        "analysis_kind": "axion_mea_kilosort4_well_sorting",
        "recording_stem": config.recording_stem,
        "well": config.well.strip().upper(),
        "plate_map_row": plate_row,
        "plate_map_csv": str(config.plate_map_csv.expanduser().resolve()),
        "electrode_geometry_csv": str(config.electrode_geometry_csv.expanduser().resolve()),
        "probe_json": str(probe_path),
        "probe": probe_to_jsonable(probe),
        "binary": shape,
        "settings": {
            "fs": config.fs,
            "dtype": np.dtype(config.dtype).name,
            "n_chan_bin": config.n_chan_bin,
            "do_CAR": config.do_car,
            "invert_sign": config.invert_sign,
            "clear_cache": config.clear_cache,
            "save_preprocessed_copy": config.save_preprocessed_copy,
            "torch_thread_lim": config.torch_thread_lim,
        },
        "status": "ready_to_run" if not config.run_kilosort else "prepared_for_kilosort",
        "notes": [
            "Kilosort requires a continuous row-major binary trace for this well.",
            "Axion spike-list CSVs and .spk files are downstream spike products, not raw traces for sorting.",
        ],
    }
    manifest_path = output_dir / "kilosort_ready_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def run_kilosort4(config: KilosortWellConfig) -> dict[str, Any]:
    """Prepare and optionally execute Kilosort4 for one well."""
    manifest = prepare_well_run(config)
    output_dir = config.output_dir.expanduser().resolve()
    if not config.run_kilosort:
        return manifest

    if not hasattr(np, "in1d"):
        np.in1d = np.isin  # Kilosort 4.1.3 still calls the removed NumPy alias.

    from kilosort.run_kilosort import run_kilosort

    settings = {
        "n_chan_bin": config.n_chan_bin,
        "fs": config.fs,
    }
    result = run_kilosort(
        settings=settings,
        probe={
            "chanMap": np.asarray(manifest["probe"]["chanMap"], dtype=np.int64),
            "xc": np.asarray(manifest["probe"]["xc"], dtype=np.float64),
            "yc": np.asarray(manifest["probe"]["yc"], dtype=np.float64),
            "kcoords": np.asarray(manifest["probe"]["kcoords"], dtype=np.int64),
            "n_chan": int(manifest["probe"]["n_chan"]),
        },
        filename=config.binary_file.expanduser().resolve(),
        results_dir=output_dir / "kilosort4",
        data_dtype=np.dtype(config.dtype).name,
        do_CAR=config.do_car,
        invert_sign=config.invert_sign,
        clear_cache=config.clear_cache,
        save_preprocessed_copy=config.save_preprocessed_copy,
        torch_thread_lim=config.torch_thread_lim,
    )
    updated = dict(manifest)
    updated["status"] = "kilosort_finished"
    updated["kilosort_results_dir"] = str(output_dir / "kilosort4")
    updated["kilosort_return_summary"] = {
        "return_items": len(result) if isinstance(result, tuple) else 1,
    }
    (output_dir / "kilosort_ready_manifest.json").write_text(
        json.dumps(updated, indent=2),
        encoding="utf-8",
    )
    return updated


def config_to_json(config: KilosortWellConfig) -> dict[str, Any]:
    """Serialize a run config for logging."""
    payload = asdict(config)
    for key, value in payload.items():
        if isinstance(value, Path):
            payload[key] = str(value)
    return payload
