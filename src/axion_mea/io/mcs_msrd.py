"""Direct reader for Multi Channel Suite v17 ``.msrd`` continuous recordings.

MCS stores an ASCII index followed by linked, little-endian int32 data blocks.
This reader follows those links; it never treats the proprietary file as a flat
binary stream.  It was verified against the matching MCS HDF5 export for the
included 60MEA200/30iR recording.
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import h5py

from .mcs_h5 import mcs_60mea200_geometry


_NUMBER = re.compile(r"(?:^|\r\n)([A-Za-z][A-Za-z0-9]*)=(-?\d+)")
_TEXT = re.compile(r"(?:^|\r\n)([A-Za-z][A-Za-z0-9]*)=([^\r\n]*)")


def _fields(blob: bytes) -> dict[str, str]:
    text = blob.decode("ascii", errors="ignore")
    return {key: value.strip() for key, value in _TEXT.findall(text)}


def _number(fields: dict[str, str], key: str) -> int:
    try:
        return int(fields[key])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Missing or invalid {key} in MCS MSRD header.") from exc


@dataclass(frozen=True)
class _Block:
    offset: int
    next_offset: int
    next_id_offset: int
    timestamp: int
    size_bytes: int
    header_bytes: int

    @property
    def data_offset(self) -> int:
        return self.next_offset - self.size_bytes if self.next_offset >= 0 else self.offset + self.header_bytes


@dataclass(frozen=True)
class McsMsrdRecording:
    source_file: Path
    channel_labels: tuple[str, ...]
    sample_count: int
    sampling_frequency_hz: float
    first_timestamp: int
    conversion_to_volts: tuple[float, ...]
    events: tuple[dict[str, Any], ...]
    blocks_by_channel: tuple[tuple[_Block, ...], ...]

    @property
    def duration_s(self) -> float:
        return self.sample_count / self.sampling_frequency_hz

    @property
    def signal_channel_indices(self) -> tuple[int, ...]:
        return tuple(i for i, label in enumerate(self.channel_labels) if label.lower() != "ref")

    def manifest(self) -> dict[str, Any]:
        return {
            "analysis_kind": "mcs_multi_channel_suite_msrd_continuous_recording",
            "source_file": str(self.source_file), "sample_count": self.sample_count,
            "sampling_frequency_hz": self.sampling_frequency_hz, "duration_s": self.duration_s,
            "first_timestamp": self.first_timestamp, "timestamp_tick_seconds": 1e-6,
            "channel_count_in_file": len(self.channel_labels), "signal_channel_count": len(self.signal_channel_indices),
            "channel_labels": list(self.channel_labels), "events": list(self.events),
        }


def _read_block(handle, offset: int, fallback_header_bytes: int | None = None) -> _Block:
    handle.seek(offset)
    # v17 analog headers are 350 bytes and event headers are 400 bytes.  Do
    # not read into the following linked header, whose fields would overwrite
    # this block's fields in the dictionary.
    fields = _fields(handle.read(400))
    next_offset = _number(fields, "FPosNext")
    size_bytes = _number(fields, "Size")
    if next_offset >= 0:
        header_bytes = next_offset - size_bytes - offset
    elif fallback_header_bytes is not None:
        header_bytes = fallback_header_bytes
    else:
        raise ValueError("Cannot determine final MCS block header length.")
    if header_bytes <= 0 or size_bytes < 0:
        raise ValueError(f"Invalid MCS block at byte offset {offset}.")
    return _Block(offset, next_offset, _number(fields, "FPosNextID"), _number(fields, "TimeStamp"), size_bytes, header_bytes)


def inspect_mcs_msrd(source_file: Path) -> McsMsrdRecording:
    source_file = source_file.expanduser().resolve()
    if not source_file.is_file():
        raise FileNotFoundError(source_file)
    with source_file.open("rb") as handle:
        top = _fields(handle.read(4096))
        if top.get("FileID") != "MULTI_CHANNEL_SUITE" or top.get("FileVersion") != "17":
            raise ValueError(f"{source_file} is not a supported Multi Channel Suite v17 .msrd file.")
        recording_offset = _number(top, "FPosFirstRecordingHdr")
        handle.seek(recording_offset)
        recording = _fields(handle.read(4096))
        first_block_offset = _number(recording, "FPosNext")
        first_timestamp = _number(recording, "TimeStamp")
        metadata_end = first_block_offset
        handle.seek(recording_offset)
        metadata = handle.read(metadata_end - recording_offset).decode("ascii", errors="ignore")
        analog = metadata[metadata.index("DataType=Analog"):metadata.index("DataType=Event")]
        channel_parts = re.split(r"\r\nEntity=", analog)[1:]
        labels, conversions = [], []
        for part in channel_parts:
            fields = _fields(("Entity=" + part).encode())
            if "ChID" not in fields:
                continue
            labels.append(fields["Label"])
            conversions.append(float(fields["ConversionFactor"]) * 10.0 ** int(fields["Exponent"]))
        channel_count = _number(_fields(analog.encode()), "Entities")
        if len(labels) != channel_count:
            raise ValueError("Could not recover all analog-channel metadata from the .msrd header.")
        tick_us = int(_fields(("Entity=" + channel_parts[0]).encode())["Tick"])
        first_blocks = []
        current = first_block_offset
        for _ in range(channel_count):
            block = _read_block(handle, current, first_blocks[0].header_bytes if first_blocks else None)
            first_blocks.append(block)
            current = block.next_offset
        blocks_by_channel: list[tuple[_Block, ...]] = []
        for first in first_blocks:
            chain, current = [], first.offset
            fallback = first.header_bytes
            while current >= 0:
                block = _read_block(handle, current, fallback)
                chain.append(block)
                current = block.next_id_offset
            blocks_by_channel.append(tuple(chain))
        sizes = [sum(block.size_bytes for block in chain) // 4 for chain in blocks_by_channel]
        if len(set(sizes)) != 1:
            raise ValueError("MCS analog channels have unequal sample counts.")
        events = _read_events(metadata, handle, first_timestamp)
    return McsMsrdRecording(source_file, tuple(labels), sizes[0], 1e6 / tick_us, first_timestamp, tuple(conversions), tuple(events), tuple(blocks_by_channel))


def _read_events(metadata: str, handle, first_timestamp: int) -> list[dict[str, Any]]:
    event_metadata = metadata[metadata.index("DataType=Event"):]
    result = []
    for part in re.split(r"\r\nEntity=", event_metadata)[1:]:
        fields = _fields(("Entity=" + part).encode())
        if "EventID" not in fields or "FPosNextID" not in fields:
            continue
        current = int(fields["FPosNextID"])
        label_match = re.search(r"\r\nLabel=([^\r\n]*)", "\r\n" + "Entity=" + part)
        event_id = int(fields["EventID"])
        label = label_match.group(1).strip() if label_match else f"Event {event_id}"
        while current >= 0:
            block = _read_block(handle, current, 400)
            result.append({"event_id": event_id, "event_label": label, "timestamp": block.timestamp,
                           "time_from_recording_start_s": (block.timestamp - first_timestamp) * 1e-6})
            current = block.next_id_offset
    return sorted(result, key=lambda row: (row["timestamp"], row["event_id"]))


def export_msrd_binary(recording: McsMsrdRecording, output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.expanduser().resolve(); output_dir.mkdir(parents=True, exist_ok=True)
    indices = recording.signal_channel_indices
    binary = output_dir / "mcs_signal_channels.int16.bin"
    with recording.source_file.open("rb") as handle, binary.open("wb") as out:
        for blocks in zip(*recording.blocks_by_channel):
            values = []
            for block in blocks:
                handle.seek(block.data_offset)
                value = np.frombuffer(handle.read(block.size_bytes), dtype="<i4")
                if value.min() < np.iinfo(np.int16).min or value.max() > np.iinfo(np.int16).max:
                    raise ValueError("MCS trace values do not fit int16; refusing a lossy export.")
                values.append(value)
            np.ascontiguousarray(np.stack(values, axis=1)[:, indices], dtype=np.int16).tofile(out)
    geometry = mcs_60mea200_geometry(recording.channel_labels)
    _csv(output_dir / "channels.csv", geometry, ["stream_channel_index", "channel_label", "x_um", "y_um"])
    _csv(output_dir / "events.csv", list(recording.events), ["event_id", "event_label", "timestamp", "time_from_recording_start_s"])
    manifest = recording.manifest() | {"binary_file": str(binary), "binary_dtype": "int16", "binary_layout": "sample_major_row_major", "n_chan_bin": len(indices), "channels_csv": str(output_dir / "channels.csv"), "events_csv": str(output_dir / "events.csv"), "conversion_to_volts": list(recording.conversion_to_volts)}
    (output_dir / "mcs_preparation_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def export_msrd_h5(recording: McsMsrdRecording, output_dir: Path) -> Path:
    """Write an analysis HDF5 representation with MCS-style stream paths.

    The source integer counts remain unchanged. The file also carries an
    explicit geometry table, which older MCS HDF5 exports do not consistently
    include. It is designed for this repository's MCS reader and downstream
    processing, not represented as a vendor-generated conversion.
    """
    output_dir = output_dir.expanduser().resolve(); output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "McsRecording.analysis.h5"
    temporary_path = output_dir / "McsRecording.analysis.h5.partial"
    string = h5py.string_dtype(encoding="utf-8")
    info_dtype = np.dtype([("ChannelID", "<i4"), ("Label", string), ("Exponent", "<i4"), ("Tick", "<i8"), ("ConversionFactor", "<i8")])
    geometry_dtype = np.dtype([("stream_channel_index", "<i4"), ("channel_label", string), ("x_um", "<f8"), ("y_um", "<f8")])
    tick_us = round(1e6 / recording.sampling_frequency_hz)
    with h5py.File(temporary_path, "w") as h5, recording.source_file.open("rb") as source:
        data = h5.create_group("Data")
        data.attrs["MeaName"] = "60MEA200/30iR"
        data.attrs["MeaLayout"] = "60MEA200_30_iR"
        data.attrs["ProgramName"] = "axion_mea direct MSRD reader"
        data.attrs["SourceFormat"] = "Multi Channel Suite FileVersion=17"
        rec = data.create_group("Recording_0")
        rec.attrs["Duration"] = int(recording.sample_count * tick_us)
        rec.attrs["TimeStamp"] = recording.first_timestamp
        stream = rec.create_group("AnalogStream/Stream_0")
        channel_data = stream.create_dataset("ChannelData", shape=(len(recording.channel_labels), recording.sample_count), dtype="<i4", chunks=(1, min(100_000, recording.sample_count)))
        for channel, blocks in enumerate(recording.blocks_by_channel):
            sample_start = 0
            for block in blocks:
                source.seek(block.data_offset)
                samples = np.frombuffer(source.read(block.size_bytes), dtype="<i4")
                channel_data[channel, sample_start:sample_start + len(samples)] = samples
                sample_start += len(samples)
        stream.create_dataset("ChannelDataTimeStamps", data=np.asarray([[recording.first_timestamp, 0, recording.sample_count - 1]], dtype="<i8"))
        info = np.empty(len(recording.channel_labels), dtype=info_dtype)
        for index, (label, conversion) in enumerate(zip(recording.channel_labels, recording.conversion_to_volts)):
            info[index] = (index, label, -12, tick_us, round(conversion * 1e12))
        stream.create_dataset("InfoChannel", data=info)
        geometry = []
        for row in mcs_60mea200_geometry(recording.channel_labels):
            geometry.append((row["stream_channel_index"], row["channel_label"], row["x_um"], row["y_um"]))
        h5.create_dataset("Geometry/ChannelGeometry", data=np.asarray(geometry, dtype=geometry_dtype))
        event_stream = rec.create_group("EventStream/Stream_0")
        by_event: dict[int, list[dict[str, Any]]] = {}
        for event in recording.events: by_event.setdefault(int(event["event_id"]), []).append(event)
        event_dtype = np.dtype([("EventID", "<i4"), ("Label", string)])
        event_info = np.asarray([(event_id, events[0]["event_label"]) for event_id, events in sorted(by_event.items())], dtype=event_dtype)
        event_stream.create_dataset("InfoEvent", data=event_info)
        for event_id, events in by_event.items():
            values = np.full((5, len(events)), -1, dtype="<i8")
            values[0] = [event["timestamp"] for event in events]
            values[1:3] = 0
            event_stream.create_dataset(f"EventEntity_{event_id}", data=values)
    temporary_path.replace(path)
    return path


def _csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
