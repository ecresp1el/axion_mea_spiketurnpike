"""Export Axion per-well Kilosort binaries to NWB for Kempner/AIND ingestion."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .well_mapping import AxionWellMapping


@dataclass(frozen=True)
class AxionWellNwbConfig:
    """Inputs needed to package one exported Axion well as NWB."""

    binary_file: Path
    output_nwb: Path
    channel_mapping_csv: Path
    export_manifest_json: Path
    recording_stem: str
    well: str
    session_description: str = "Axion MEA per-well continuous voltage export"
    identifier: str | None = None
    session_start_time: str | None = None
    timezone: str = "America/Detroit"
    dtype: str = "int16"
    fs: float = 12500.0
    n_chan_bin: int = 16
    voltage_scale_v_per_sample: float | None = None
    source_raw_file: Path | None = None
    raw_metadata_inventory_csv: Path | None = None
    kilosort_manifest_json: Path | None = None
    probe_json: Path | None = None
    run_command: str | None = None
    command_argv: list[str] | None = None
    working_directory: str | None = None


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return None
    return json.loads(resolved.read_text(encoding="utf-8"))


def _read_text(path: Path | None) -> str | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return None
    return resolved.read_text(encoding="utf-8")


def _read_csv_text_clean(path: Path | None) -> str | None:
    text = _read_text(path)
    if text is None:
        return None
    return text.replace("\x00", "")


def _json_ready(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def _raw_metadata_row(
    inventory_csv: Path | None,
    export_manifest: dict[str, Any],
    source_raw_file: Path | None,
) -> dict[str, Any] | None:
    text = _read_csv_text_clean(inventory_csv)
    if text is None:
        return None

    inventory = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False)
    if inventory.empty:
        return None

    source_candidates = []
    if source_raw_file is not None:
        source_candidates.append(str(source_raw_file.expanduser().resolve()))
    if export_manifest.get("raw_file"):
        source_candidates.append(str(Path(str(export_manifest["raw_file"])).expanduser().resolve()))

    for source in source_candidates:
        raw_file = inventory.get("raw_file")
        if raw_file is not None:
            matches = inventory[raw_file.astype(str) == source]
            if len(matches) == 1:
                return {key: _json_ready(value) for key, value in matches.iloc[0].to_dict().items()}

        raw_name = inventory.get("raw_name")
        if raw_name is not None:
            matches = inventory[raw_name.astype(str) == Path(source).name]
            if len(matches) == 1:
                return {key: _json_ready(value) for key, value in matches.iloc[0].to_dict().items()}

    recording_stem = str(export_manifest.get("recording_stem", ""))
    raw_stem = Path(str(export_manifest.get("raw_file", recording_stem))).name.replace(".raw", "")
    raw_stem = raw_stem.replace("_BroadbandProcessor", "")
    for candidate in (recording_stem, raw_stem):
        if not candidate:
            continue
        column = inventory.get("recording_stem")
        if column is None:
            continue
        matches = inventory[column.astype(str) == candidate]
        if len(matches) == 1:
            return {key: _json_ready(value) for key, value in matches.iloc[0].to_dict().items()}

    return None


def _parse_datetime(value: Any, tz: ZoneInfo) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed


def _session_start(
    config: AxionWellNwbConfig,
    export_manifest: dict[str, Any],
    raw_metadata: dict[str, Any] | None,
) -> datetime:
    tz = ZoneInfo(config.timezone)
    for raw_value in (
        config.session_start_time,
        export_manifest.get("session_start_time"),
        raw_metadata.get("experiment_start_time") if raw_metadata else None,
        raw_metadata.get("block_vector_start_time") if raw_metadata else None,
    ):
        parsed = _parse_datetime(raw_value, tz)
        if parsed is not None:
            return parsed
    return datetime.now(tz)


def _binary_shape(binary_file: Path, dtype: str, n_chan_bin: int) -> tuple[int, np.dtype]:
    resolved = binary_file.expanduser().resolve()
    np_dtype = np.dtype(dtype)
    bytes_per_sample = np_dtype.itemsize * n_chan_bin
    size_bytes = resolved.stat().st_size
    if size_bytes % bytes_per_sample != 0:
        raise ValueError(
            f"{resolved} has {size_bytes} bytes, not divisible by "
            f"{np_dtype.itemsize} * {n_chan_bin}."
        )
    return size_bytes // bytes_per_sample, np_dtype


def write_axion_well_nwb(config: AxionWellNwbConfig) -> dict[str, Any]:
    """Write one Axion well-level NWB file and return a manifest."""
    from hdmf.backends.hdf5.h5_utils import H5DataIO
    from pynwb import NWBFile, NWBHDF5IO
    from pynwb.ecephys import ElectricalSeries

    binary_file = config.binary_file.expanduser().resolve()
    output_nwb = config.output_nwb.expanduser().resolve()
    output_nwb.parent.mkdir(parents=True, exist_ok=True)

    export_manifest = _read_json(config.export_manifest_json) or {}
    kilosort_manifest = _read_json(config.kilosort_manifest_json)
    probe = _read_json(config.probe_json)
    well_mapping = AxionWellMapping.from_csv(config.channel_mapping_csv)
    channel_mapping = well_mapping.dataframe()
    source_raw = config.source_raw_file
    if source_raw is None and export_manifest.get("raw_file"):
        source_raw = Path(str(export_manifest["raw_file"]))
    raw_metadata = _raw_metadata_row(config.raw_metadata_inventory_csv, export_manifest, source_raw)

    fs = float(export_manifest.get("fs", config.fs))
    dtype = str(export_manifest.get("dtype", config.dtype))
    n_chan_bin = int(export_manifest.get("n_chan_bin", config.n_chan_bin))
    voltage_scale = config.voltage_scale_v_per_sample
    if voltage_scale is None:
        voltage_scale = float(export_manifest.get("voltage_scale_v_per_sample", 1.0))
    n_samples, np_dtype = _binary_shape(binary_file, dtype, n_chan_bin)
    if len(channel_mapping) != n_chan_bin:
        raise ValueError(
            f"Channel mapping has {len(channel_mapping)} rows but n_chan_bin={n_chan_bin}."
        )

    identifier = config.identifier or f"{config.recording_stem}_{config.well}_axion_well_nwb"
    nwbfile = NWBFile(
        session_description=config.session_description,
        identifier=identifier,
        session_start_time=_session_start(config, export_manifest, raw_metadata),
        institution="University of Michigan",
        lab="Parent Lab",
        experiment_description=(
            "Axion MEA per-well continuous voltage converted to NWB as a "
            "Kempner/AIND-compatible ingestion artifact."
        ),
        session_id=f"{config.recording_stem}_{config.well}",
        keywords=("Axion", "MEA", "Kilosort", "Kempner", "AIND"),
        notes=(
            "Voltage samples are raw int16 ADC counts from the Axion export. "
            "ElectricalSeries.conversion stores volts per sample."
        ),
    )

    device = nwbfile.create_device(
        name="Axion Maestro Pro",
        description=f"Source raw file: {source_raw}" if source_raw else "Axion MEA recording system",
        manufacturer="Axion BioSystems",
    )
    group = nwbfile.create_electrode_group(
        name=f"{config.well}_electrode_group",
        description=f"Axion well {config.well} 4x4 electrode grid",
        location=f"well {config.well}",
        device=device,
    )

    custom_columns = {
        "rel_x": "SpikeInterface-compatible relative electrode x coordinate in micrometers.",
        "rel_y": "SpikeInterface-compatible relative electrode y coordinate in micrometers.",
        "rel_z": "SpikeInterface-compatible relative electrode z coordinate in micrometers.",
        "well": "Axion well label.",
        "channel_in_well": "Axion electrode label within the well.",
        "electrode_row": "Physical electrode row used for probe geometry.",
        "electrode_col": "Physical electrode column used for probe geometry.",
        "axion_well_row": "AxionFileLoader well row index.",
        "axion_well_col": "AxionFileLoader well column index.",
        "axion_electrode_col": "AxionFileLoader electrode column index.",
        "axion_electrode_row": "AxionFileLoader electrode row index.",
        "channel_achk": "Axion amplifier chip identifier.",
        "channel_index": "Axion amplifier channel index.",
        "kilosort_channel_index": "Zero-based channel index in the binary and Kilosort probe.",
    }
    for name, description in custom_columns.items():
        nwbfile.add_electrode_column(name=name, description=description)

    for _, row in channel_mapping.iterrows():
        nwbfile.add_electrode(
            x=float(row["nwb_x"]),
            y=float(row["nwb_y"]),
            z=float(row["nwb_z"]),
            imp=np.nan,
            location=f"well {config.well}",
            filtering=str(export_manifest.get("dataset", "Axion continuous voltage")),
            group=group,
            rel_x=float(row["rel_x"]),
            rel_y=float(row["rel_y"]),
            rel_z=float(row["rel_z"]),
            well=str(row["well"]),
            channel_in_well=str(row["channel_in_well"]),
            electrode_row=int(row["electrode_row"]),
            electrode_col=int(row["electrode_col"]),
            axion_well_row=int(row["axion_well_row"]),
            axion_well_col=int(row["axion_well_col"]),
            axion_electrode_col=int(row["axion_electrode_col"]),
            axion_electrode_row=int(row["axion_electrode_row"]),
            channel_achk=int(row["channel_achk"]),
            channel_index=int(row["channel_index"]),
            kilosort_channel_index=int(row["channel_index_zero_based"]),
        )

    electrodes = nwbfile.create_electrode_table_region(
        region=list(range(n_chan_bin)),
        description=f"All exported channels for Axion well {config.well}.",
    )
    data = np.memmap(binary_file, dtype=np_dtype, mode="r", shape=(n_samples, n_chan_bin))
    electrical_series = ElectricalSeries(
        name=f"{config.well}_ElectricalSeries",
        description=(
            "Per-well Axion continuous voltage in Kilosort channel order; "
            "channel order is preserved in the electrode table."
        ),
        data=H5DataIO(data, compression="gzip", chunks=True),
        electrodes=electrodes,
        starting_time=float(export_manifest.get("start_time_s", 0.0)),
        rate=fs,
        conversion=float(voltage_scale),
    )
    nwbfile.add_acquisition(electrical_series)

    source_payload = {
        "binary_file": str(binary_file),
        "output_nwb": str(output_nwb),
        "source_raw_file": str(source_raw) if source_raw else None,
        "recording_stem": config.recording_stem,
        "well": config.well,
        "fs": fs,
        "dtype": dtype,
        "n_chan_bin": n_chan_bin,
        "n_samples": n_samples,
        "duration_s": n_samples / fs,
        "voltage_scale_v_per_sample": float(voltage_scale),
        "channel_order": channel_mapping["channel_in_well"].astype(str).tolist(),
        "channel_mapping_manifest": well_mapping.ingestion_manifest(),
        "raw_metadata_inventory_csv": str(config.raw_metadata_inventory_csv.expanduser().resolve())
        if config.raw_metadata_inventory_csv
        else None,
        "provenance": {
            "run_command": config.run_command,
            "command_argv": config.command_argv,
            "working_directory": config.working_directory,
        },
    }
    nwbfile.add_scratch(
        json.dumps(source_payload, indent=2),
        name="axion_nwb_source_manifest_json",
        description="Axion-to-NWB source manifest generated by this repository.",
    )
    nwbfile.add_scratch(
        channel_mapping,
        name="axion_channel_mapping_table",
        description="Original Axion channel mapping table used to write the binary and NWB electrodes.",
    )
    if raw_metadata is not None:
        nwbfile.add_scratch(
            json.dumps(raw_metadata, indent=2),
            name="axion_raw_metadata_inventory_row_json",
            description="Matched row from the MATLAB Axion raw metadata inventory.",
        )
    sidecars: list[tuple[str, Path | None, str]] = [
        ("axion_binary_export_manifest_json", config.export_manifest_json, "Binary export manifest JSON."),
        ("axion_channel_mapping_csv", config.channel_mapping_csv, "Binary export channel mapping CSV."),
        ("axion_kilosort_ready_manifest_json", config.kilosort_manifest_json, "Kilosort readiness/result manifest JSON."),
        ("axion_probe_json", config.probe_json, "Probe geometry JSON used by Kilosort."),
    ]
    for name, path, description in sidecars:
        text = _read_text(path)
        if text is not None:
            nwbfile.add_scratch(text, name=name, description=description)
    if kilosort_manifest is not None:
        nwbfile.add_scratch(
            json.dumps(kilosort_manifest, indent=2),
            name="axion_kilosort_manifest_structured_json",
            description="Parsed Kilosort manifest copied into NWB scratch.",
        )
    if probe is not None:
        nwbfile.add_scratch(
            json.dumps(probe, indent=2),
            name="axion_probe_structured_json",
            description="Parsed Kilosort probe JSON copied into NWB scratch.",
        )

    with NWBHDF5IO(output_nwb, "w") as io:
        io.write(nwbfile)

    manifest = {
        "analysis_kind": "axion_well_nwb_export",
        **source_payload,
        "nwb_identifier": identifier,
        "session_start_time": nwbfile.session_start_time.isoformat(),
        "electrical_series": electrical_series.name,
        "metadata_sidecars": {
            "export_manifest_json": str(config.export_manifest_json.expanduser().resolve()),
            "channel_mapping_csv": str(config.channel_mapping_csv.expanduser().resolve()),
            "kilosort_manifest_json": str(config.kilosort_manifest_json.expanduser().resolve())
            if config.kilosort_manifest_json
            else None,
            "probe_json": str(config.probe_json.expanduser().resolve()) if config.probe_json else None,
            "raw_metadata_inventory_csv": str(config.raw_metadata_inventory_csv.expanduser().resolve())
            if config.raw_metadata_inventory_csv
            else None,
        },
        "provenance": source_payload["provenance"],
    }
    manifest_path = output_nwb.with_suffix(".nwb_manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def config_to_json(config: AxionWellNwbConfig) -> dict[str, Any]:
    """Serialize config paths for command logging."""
    payload = asdict(config)
    for key, value in payload.items():
        if isinstance(value, Path):
            payload[key] = str(value)
    return payload
