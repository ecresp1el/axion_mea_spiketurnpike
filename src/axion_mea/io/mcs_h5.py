"""Read and prepare Multi Channel Systems MEA2100 HDF5 recordings.

This is deliberately separate from the Axion CSV/``.raw`` intake: an MCS
recording contains continuous traces and hardware event streams, rather than
pre-detected spike tables.  It produces the row-major int16 binary and probe
metadata needed by Kilosort, without altering the source recording.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np


ANALOG_PATH = "Data/Recording_0/AnalogStream/Stream_0"
EVENT_PATH = "Data/Recording_0/EventStream/Stream_0"


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


@dataclass(frozen=True)
class McsH5Recording:
    """Metadata and source paths for one MCS continuous-trace recording."""

    source_file: Path
    channel_labels: tuple[str, ...]
    channel_ids: tuple[int, ...]
    sample_count: int
    sampling_frequency_hz: float
    first_timestamp: int
    timestamp_tick_seconds: float
    sample_tick_seconds: float
    conversion_to_volts: tuple[float, ...]
    events: tuple[dict[str, Any], ...]

    @property
    def duration_s(self) -> float:
        return self.sample_count / self.sampling_frequency_hz

    @property
    def signal_channel_indices(self) -> tuple[int, ...]:
        """All non-reference channels, in on-disk order."""
        return tuple(i for i, label in enumerate(self.channel_labels) if label.lower() != "ref")

    def manifest(self) -> dict[str, Any]:
        return {
            "analysis_kind": "mcs_mea2100_continuous_recording",
            "source_file": str(self.source_file),
            "sample_count": self.sample_count,
            "sampling_frequency_hz": self.sampling_frequency_hz,
            "duration_s": self.duration_s,
            "first_timestamp": self.first_timestamp,
            "timestamp_tick_seconds": self.timestamp_tick_seconds,
            "sample_tick_seconds": self.sample_tick_seconds,
            "channel_count_in_file": len(self.channel_labels),
            "signal_channel_count": len(self.signal_channel_indices),
            "channel_labels": list(self.channel_labels),
            "events": list(self.events),
        }


def inspect_mcs_h5(source_file: Path) -> McsH5Recording:
    """Inspect a standard MCS HDF5 file without loading its trace matrix."""
    source_file = source_file.expanduser().resolve()
    try:
        with h5py.File(source_file, "r") as h5:
            stream = h5[ANALOG_PATH]
            samples = stream["ChannelData"]
            info = stream["InfoChannel"][:]
            stamps = stream["ChannelDataTimeStamps"][:]
            if samples.ndim != 2 or len(info) != samples.shape[0] or stamps.shape[1] < 3:
                raise ValueError(f"{source_file} has an unsupported MCS analog-stream layout.")
            ticks = np.asarray(info["Tick"], dtype=np.int64)
            if not np.all(ticks == ticks[0]) or ticks[0] <= 0:
                raise ValueError(f"{source_file} has inconsistent or invalid per-channel Tick metadata.")
            # MCS stores analog sampling intervals in microseconds.  Event and
            # ChannelDataTimeStamps values are absolute microsecond timestamps.
            sample_tick_seconds = float(ticks[0]) * 1e-6
            timestamp_tick_seconds = 1e-6
            labels = tuple(_text(row["Label"]) for row in info)
            conversions = tuple(float(row["ConversionFactor"]) * 10.0 ** int(row["Exponent"]) for row in info)
            events = _read_events(h5, int(stamps[0, 0]), timestamp_tick_seconds)
    except (OSError, RuntimeError, KeyError) as exc:
        raise ValueError(f"Cannot read MCS HDF5 recording {source_file}: {exc}") from exc
    return McsH5Recording(
        source_file=source_file,
        channel_labels=labels,
        channel_ids=tuple(int(row["ChannelID"]) for row in info),
        sample_count=int(samples.shape[1]),
        sampling_frequency_hz=1.0 / sample_tick_seconds,
        first_timestamp=int(stamps[0, 0]),
        timestamp_tick_seconds=timestamp_tick_seconds,
        sample_tick_seconds=sample_tick_seconds,
        conversion_to_volts=conversions,
        events=tuple(events),
    )


def _read_events(h5: h5py.File, first_timestamp: int, tick_seconds: float) -> list[dict[str, Any]]:
    if EVENT_PATH not in h5:
        return []
    stream = h5[EVENT_PATH]
    info = stream.get("InfoEvent")
    labels = {} if info is None else {int(row["EventID"]): _text(row["Label"]) for row in info[:]}
    events: list[dict[str, Any]] = []
    for name, dataset in stream.items():
        if not name.startswith("EventEntity_"):
            continue
        event_id = int(name.rsplit("_", 1)[1])
        values = dataset[:]
        if values.ndim != 2 or values.shape[0] < 1:
            continue
        for timestamp in values[0]:
            timestamp = int(timestamp)
            events.append({
                "event_id": event_id,
                "event_label": labels.get(event_id, name),
                "timestamp": timestamp,
                "time_from_recording_start_s": (timestamp - first_timestamp) * tick_seconds,
            })
    return sorted(events, key=lambda row: (row["timestamp"], row["event_id"]))


def mcs_60mea200_geometry(channel_labels: tuple[str, ...], pitch_um: float = 200.0) -> list[dict[str, Any]]:
    """Return a 60MEA200/30iR grid geometry from its standard numeric labels.

    MCS labels such as ``47`` encode row 4, column 7.  The reference is not
    a recording electrode and is excluded by the caller.
    """
    rows = []
    for index, label in enumerate(channel_labels):
        if label.lower() == "ref":
            continue
        if len(label) != 2 or not label.isdigit() or "0" in label or "9" in label:
            raise ValueError(f"Cannot derive 60MEA200 geometry from channel label {label!r}.")
        row, column = int(label[0]), int(label[1])
        rows.append({"stream_channel_index": index, "channel_label": label, "x_um": column * pitch_um, "y_um": row * pitch_um})
    return rows


def export_mcs_binary(
    recording: McsH5Recording,
    output_dir: Path,
    chunk_samples: int = 100_000,
    output_dtype: str = "int16",
) -> dict[str, Any]:
    """Export signal channels as row-major integer data plus event/probe tables."""
    if chunk_samples <= 0:
        raise ValueError("chunk_samples must be positive.")
    dtype = np.dtype(output_dtype)
    if dtype not in (np.dtype("int16"), np.dtype("int32")):
        raise ValueError("output_dtype must be int16 or int32.")
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    indices = np.asarray(recording.signal_channel_indices, dtype=int)
    binary_path = output_dir / f"mcs_signal_channels.{dtype.name}.bin"
    with h5py.File(recording.source_file, "r") as h5, binary_path.open("wb") as out:
        source = h5[f"{ANALOG_PATH}/ChannelData"]
        for start in range(0, recording.sample_count, chunk_samples):
            stop = min(start + chunk_samples, recording.sample_count)
            block = source[indices, start:stop]
            bounds = np.iinfo(dtype)
            if block.min() < bounds.min or block.max() > bounds.max:
                raise ValueError(f"MCS trace values do not fit {dtype.name}; refusing a lossy export.")
            np.ascontiguousarray(block.T, dtype=dtype).tofile(out)
    geometry = mcs_60mea200_geometry(recording.channel_labels)
    _write_csv(output_dir / "channels.csv", geometry, ["stream_channel_index", "channel_label", "x_um", "y_um"])
    _write_csv(output_dir / "events.csv", list(recording.events), ["event_id", "event_label", "timestamp", "time_from_recording_start_s"])
    manifest = recording.manifest() | {
        "binary_file": str(binary_path), "binary_dtype": dtype.name, "binary_layout": "sample_major_row_major",
        "n_chan_bin": len(indices), "channels_csv": str(output_dir / "channels.csv"), "events_csv": str(output_dir / "events.csv"),
        "conversion_to_volts": list(recording.conversion_to_volts),
        "notes": ["Reference channel is excluded.", "Raw integer counts are exported; volts per count are retained in this manifest."],
    }
    (output_dir / "mcs_preparation_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
