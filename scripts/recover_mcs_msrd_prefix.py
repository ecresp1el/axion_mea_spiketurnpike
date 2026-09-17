#!/usr/bin/env python3
"""Recover a synchronized prefix from an unfinalized MCS v17 acquisition."""
from __future__ import annotations

import argparse
import collections
import copy
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from axion_mea.io.mcs_msrd import _fields, _read_block
from axion_mea.io.mcs_h5 import mcs_60mea200_geometry
from prepare_mcs_aind_recording import inspect_input


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_prefix(source: Path, max_blocks: int = 10000) -> dict:
    size = source.stat().st_size
    with source.open("rb") as handle:
        top = _fields(handle.read(1900))
        if top.get("FileID") != "MULTI_CHANNEL_SUITE" or top.get("FileVersion") != "17":
            raise ValueError("Recovery only supports original Multi Channel Suite v17 files")
        recording_offset = int(top["FPosFirstRecordingHdr"])
        handle.seek(recording_offset)
        recording = _fields(handle.read(1900))
        first_block = int(recording["FPosNext"])
        if not recording_offset < first_block <= min(size, 2_000_000):
            raise ValueError("Invalid or absent acquisition metadata")
        handle.seek(0)
        metadata = handle.read(first_block)
        text = metadata[recording_offset:].decode("ascii")
        analog = text[text.index("DataType=Analog"):text.index("DataType=Event")]
        channels = [_fields(("Entity=" + part).encode()) for part in re.split(r"\r\nEntity=", analog)[1:]]
        channels = [row for row in channels if "ChID" in row]
        if not channels or [int(row["ChID"]) for row in channels] != list(range(len(channels))):
            raise ValueError("Missing or unordered analog channel identities")
        entities = [int(row["Entity"]) for row in channels]
        if len(set(entities)) != len(entities) or len({row["Label"] for row in channels}) != len(channels):
            raise ValueError("Duplicate source channel identities")
        ticks = {int(row["Tick"]) for row in channels}
        if len(ticks) != 1 or min(ticks) <= 0:
            raise ValueError("Source channel sample intervals are inconsistent")
        tick = ticks.pop()
        if any(row.get("RawDataType") != "Int" or row.get("Unit") != "V" or int(row["ADZero"]) != 0 for row in channels):
            raise ValueError("Recovery requires original integer voltage channels with zero ADC offsets")
        gains = [float(row["ConversionFactor"]) * 10.0 ** int(row["Exponent"]) for row in channels]
        if not np.all(np.isfinite(gains)) or min(gains) <= 0:
            raise ValueError("Invalid voltage calibration")
        event_part = text[text.index("DataType=Event"):]
        event_metadata = [_fields(("Entity=" + part).encode()) for part in re.split(r"\r\nEntity=", event_part)[1:]]
        event_metadata = {int(row["Entity"]): row for row in event_metadata if "EventID" in row}
        blocks = {entity: [] for entity in entities}
        samples = {entity: 0 for entity in entities}
        previous_entity = {entity: -1 for entity in entities}
        origin = int(recording["TimeStamp"])
        offset, previous, count = first_block, -1, 0
        observed_events = []
        while offset >= 0:
            if count >= max_blocks:
                raise ValueError("Bounded recovery scan reached its maximum block count")
            if offset + 350 > size:
                stop = {"kind": "incomplete_header", "offset": offset}
                break
            handle.seek(offset)
            fields = _fields(handle.read(350))
            entity = int(fields["Entity"])
            header_size = 350 if entity in blocks else 400 if entity in event_metadata else None
            if header_size is None:
                raise ValueError(f"Unsupported entity {entity} in global block chain")
            block = _read_block(handle, offset, header_size)
            if int(fields["FPosPrev"]) != previous:
                raise ValueError("Global backward pointer does not match the preceding complete block")
            if block.data_offset != offset + header_size:
                raise ValueError("Unexpected block header length")
            if block.data_offset + block.size_bytes > size:
                stop = {"kind": "incomplete_payload", "offset": offset, "entity": entity,
                        "payload_end": block.data_offset + block.size_bytes, "file_size": size}
                break
            if entity in blocks:
                if int(fields["FPosPrevID"]) != previous_entity[entity]:
                    raise ValueError("Per-channel backward pointer mismatch")
                if block.size_bytes <= 0 or block.size_bytes % 4 or block.timestamp != origin + samples[entity] * tick:
                    raise ValueError("Analog sample count or timestamp continuity is invalid")
                blocks[entity].append(block)
                samples[entity] += block.size_bytes // 4
                previous_entity[entity] = offset
            else:
                info = event_metadata[entity]
                observed_events.append({"event_id": int(info["EventID"]), "event_label": info.get("Label", ""),
                                        "timestamp": block.timestamp,
                                        "time_from_recording_start_s": (block.timestamp - origin) * 1e-6})
            count += 1
            if block.next_offset >= 0 and block.next_offset <= offset:
                raise ValueError("Global block chain is cyclic or moves backward")
            previous, offset = offset, block.next_offset
        else:
            stop = {"kind": "global_chain_end", "offset": offset}
    common = min(samples.values())
    if common <= 0:
        raise ValueError("No complete synchronized prefix exists across all channels")
    events = sorted((e for e in observed_events if origin <= e["timestamp"] < origin + common * tick),
                    key=lambda e: (e["timestamp"], e["event_id"]))
    return {"top": top, "recording": recording, "channels": channels, "entities": entities,
            "blocks": blocks, "samples": samples, "common_samples": common, "tick": tick,
            "first_timestamp": origin, "gains": gains, "events": events,
            "observed_event_count": len(observed_events), "complete_blocks": count, "stop": stop,
            "metadata_sha256": hashlib.sha256(metadata).hexdigest(), "metadata_bytes": len(metadata)}


def read_range(handle, blocks: list, start: int, stop: int) -> np.ndarray:
    pieces, index = [], 0
    for block in blocks:
        end = index + block.size_bytes // 4
        low, high = max(start, index), min(stop, end)
        if high > low:
            handle.seek(block.data_offset + (low - index) * 4)
            data = handle.read((high - low) * 4)
            if len(data) != (high - low) * 4:
                raise ValueError("Source payload became incomplete during export")
            pieces.append(np.frombuffer(data, dtype="<i4"))
        index = end
        if index >= stop:
            break
    values = np.concatenate(pieces)
    if len(values) != stop - start:
        raise ValueError("Source blocks do not cover requested prefix range")
    return values


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def recover(source: Path, output_dir: Path, source_xml: Path | None = None) -> dict:
    source, output_dir = source.resolve(), output_dir.resolve()
    if source.stem != output_dir.name:
        raise ValueError("Recovered output must retain its original recording identity")
    if output_dir.exists():
        raise FileExistsError("Recovery output already exists; refusing to overwrite")
    original_stat = source.stat()
    inspected = inspect_prefix(source)
    source_hash = sha256(source)
    output_dir.mkdir(parents=True)
    labels = [row["Label"] for row in inspected["channels"]]
    signal_indices = [i for i, label in enumerate(labels) if label.lower() != "ref"]
    count, samples = len(signal_indices), inspected["common_samples"]
    fs = 1e6 / inspected["tick"]
    binary_path = output_dir / "mcs_signal_channels.int32.bin"
    temporary = binary_path.with_suffix(".bin.partial")
    digest = hashlib.sha256()
    with source.open("rb") as handle, temporary.open("wb") as out:
        for start in range(0, samples, 10000):
            stop = min(start + 10000, samples)
            values = np.stack([read_range(handle, inspected["blocks"][inspected["entities"][i]], start, stop)
                               for i in signal_indices], axis=1).astype("<i4", copy=False)
            data = values.tobytes(order="C")
            out.write(data)
            digest.update(data)
    # Compare every exported signal count against a fresh read of its linked source blocks.
    with source.open("rb") as handle, temporary.open("rb") as out:
        for start in range(0, samples, 10000):
            stop = min(start + 10000, samples)
            actual = np.frombuffer(out.read((stop - start) * count * 4), dtype="<i4").reshape(stop - start, count)
            for column, source_index in enumerate(signal_indices):
                expected = read_range(handle, inspected["blocks"][inspected["entities"][source_index]], start, stop)
                if not np.array_equal(actual[:, column], expected):
                    raise ValueError("Recovered binary differs from original source counts")
        if out.read(1):
            raise ValueError("Unexpected extra binary data")
    current_stat = source.stat()
    if (current_stat.st_size, current_stat.st_mtime_ns) != (original_stat.st_size, original_stat.st_mtime_ns):
        raise ValueError("Original source changed during recovery")
    if temporary.stat().st_size != samples * count * 4:
        raise ValueError("Recovered binary size mismatch")
    temporary.replace(binary_path)
    warning = (f"Recovered only the synchronized {samples / fs:g} s prefix of an incomplete acquisition; "
               "truncated or unequal channel tails omitted. Events are limited to the retained prefix; "
               "absent markers do not imply absence of stimulation.")
    report_path = output_dir / "mcs_partial_recovery_report.json"
    report = {"schema_version": 1, "recording_completeness": "recovered_prefix", "source_msrd": str(source),
              "source_size_bytes": original_stat.st_size, "source_mtime_ns": original_stat.st_mtime_ns,
              "source_sha256": source_hash, "source_retained": True,
              "original_header": inspected["top"], "original_recording_header": inspected["recording"],
              "source_metadata_sha256": inspected["metadata_sha256"], "source_metadata_bytes": inspected["metadata_bytes"],
              "source_channel_metadata": inspected["channels"], "first_timestamp": inspected["first_timestamp"],
              "sampling_frequency_hz": fs, "retained_sample_start": 0, "retained_sample_stop_exclusive": samples,
              "retained_duration_s": samples / fs, "complete_blocks_examined": inspected["complete_blocks"],
              "complete_samples_by_entity": inspected["samples"],
              "first_and_last_complete_block_offsets_by_entity": {
                  entity: [blocks[0].offset, blocks[-1].offset] for entity, blocks in inspected["blocks"].items()},
              "omitted_complete_samples_by_entity": {entity: value - samples for entity, value in inspected["samples"].items()},
              "stop": inspected["stop"], "global_forward_and_backward_links_validated": True,
              "per_channel_backward_links_and_timestamp_continuity_validated": True,
              "per_channel_forward_links": "Not relied on: acquisition was not fully finalized",
              "binary_file": str(binary_path), "binary_sha256": digest.hexdigest(),
              "binary_size_bytes": binary_path.stat().st_size,
              "all_retained_signal_samples_compared_to_original": True,
              "events_scope": "only events encountered in the complete global block chain within the retained prefix",
              "events_retained": inspected["events"], "source_review_warning": warning,
              "recovered_utc": datetime.now(timezone.utc).isoformat()}
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    geometry = mcs_60mea200_geometry(tuple(labels))
    write_csv(output_dir / "channels.csv", geometry, ["stream_channel_index", "channel_label", "x_um", "y_um"])
    write_csv(output_dir / "events.csv", inspected["events"], ["event_id", "event_label", "timestamp", "time_from_recording_start_s"])
    prep = {"analysis_kind": "mcs_recovered_partial_msrd_continuous_recording", "source_file": str(source),
            "sample_count": samples, "sampling_frequency_hz": fs, "duration_s": samples / fs,
            "first_timestamp": inspected["first_timestamp"], "timestamp_tick_seconds": 1e-6,
            "sample_tick_seconds": inspected["tick"] * 1e-6, "channel_count_in_file": len(labels),
            "signal_channel_count": count, "channel_labels": labels, "channel_ids": list(range(len(labels))),
            "events": inspected["events"], "binary_file": str(binary_path), "binary_dtype": "int32",
            "binary_layout": "sample_major_row_major", "n_chan_bin": count,
            "channels_csv": str(output_dir / "channels.csv"), "events_csv": str(output_dir / "events.csv"),
            "conversion_to_volts": inspected["gains"], "recording_completeness": "recovered_prefix",
            "recovery_report": str(report_path), "source_review_warning": warning,
            "source_h5_cleanup_allowed": False, "notes": [warning]}
    (output_dir / "mcs_preparation_manifest.json").write_text(json.dumps(prep, indent=2) + "\n")
    checked = inspect_input(output_dir, source_xml, allow_staged_geometry=source_xml is None)
    return {"preparation": prep, "report": report, "checked": checked}


def update_index(source_index: Path, output_root: Path, output_dir: Path, source: Path,
                 source_xml: Path | None, result: dict) -> Path:
    document = json.loads(source_index.read_text())
    recording_id = output_dir.relative_to(Path(document["staged_root"])).as_posix()
    matches = [i for i, row in enumerate(document["records"]) if row["recording_id"] == recording_id]
    if len(matches) != 1 or document["records"][matches[0]]["status"] != "blocked":
        raise ValueError("Source index must contain exactly one blocked row for this recording")
    document = copy.deepcopy(document)
    output_root.mkdir(parents=True, exist_ok=False)
    prep, checked = result["preparation"], result["checked"]
    nominal = re.fullmatch(r"(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})McsRecording", output_dir.name)
    if nominal is None:
        raise ValueError("Unsupported acquisition filename timestamp")
    evidence_path = output_root / "recovered_source_time_evidence.json"
    evidence = {"schema_version": 1, "recording_id": recording_id, "source_h5": None,
                "h5_evidence_status": "unavailable", "h5_temporal_attributes": {},
                "source_nominal_acquisition_datetime": f"{nominal[1]}T{nominal[2]}:{nominal[3]}:{nominal[4]}",
                "nominal_datetime_source": "original recording filename", "acquisition_timezone": None,
                "acquisition_utc": None, "first_sample_timestamp_microseconds": prep["first_timestamp"],
                "source_xml_paths_inspected": [str(source_xml)] if source_xml else [], "xml_clock_fields": {},
                "recording_completeness": "recovered_prefix", "recovery_report": prep["recovery_report"],
                "source_review_warning": prep["source_review_warning"], "source_msrd_header": result["report"]["original_header"]}
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    document["records"][matches[0]] = {"recording_id": recording_id, "input_dir": str(output_dir),
        "source_xml": str(source_xml) if source_xml else None, "source_h5": None, "source_msrd": str(source),
        "status": "ready", "eligibility": "ready", "reason": "", "staged": True,
        "duration_s": prep["duration_s"], "channel_count": prep["n_chan_bin"], "rejected_h5": [],
        "geometry_status": checked["geometry_status"], "configured_mea_name": checked["model"],
        "pitch_um": checked["pitch_um"], "sorting_pitch_um": checked["sorting_pitch_um"],
        "source_h5_cleanup_allowed": False, "cleanup_note": "Partial recovery: retain original source; no HDF5 deletion",
        "short_recording_policy": "established_minimum", "recording_completeness": "recovered_prefix",
        "recovery_report": prep["recovery_report"], "source_review_warning": prep["source_review_warning"],
        "source_time_evidence_json": str(evidence_path)}
    rows = document["records"]
    document["summary"].update(staged_records=sum(bool(row["staged"]) for row in rows),
        status_counts=dict(collections.Counter(row["status"] for row in rows)),
        geometry_counts=dict(collections.Counter(row.get("geometry_status", "not_staged") for row in rows)),
        matched_xml=sum(bool(row["source_xml"]) for row in rows))
    document["summary"]["unmatched_local_sources"] = [identity for identity in document["summary"].get("unmatched_local_sources", [])
                                                      if identity != recording_id]
    document["recovery_added_from_index"] = str(source_index)
    document["generated_utc"] = datetime.now(timezone.utc).isoformat()
    index_path = output_root / "mcs_batch_source_index.json"
    index_path.write_text(json.dumps(document, indent=2) + "\n")
    fieldnames = sorted({key for row in rows for key in row})
    write_csv(output_root / "mcs_batch_source_index.csv", [{key: json.dumps(value) if isinstance(value, (dict, list)) else value
              for key, value in row.items()} for row in rows], fieldnames)
    return index_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-msrd", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-xml", type=Path)
    parser.add_argument("--source-index", type=Path, required=True)
    parser.add_argument("--index-output-dir", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source_msrd.resolve(), args.output_dir.resolve()
    xml = args.source_xml.resolve() if args.source_xml else None
    if args.index_output_dir.exists():
        raise FileExistsError("Index output directory already exists")
    result = recover(source, output, xml)
    index = update_index(args.source_index.resolve(), args.index_output_dir.resolve(), output, source, xml, result)
    print(json.dumps({"index": str(index), "recovery_report": result["preparation"]["recovery_report"],
                      "duration_s": result["preparation"]["duration_s"], "sample_count": result["preparation"]["sample_count"]}, indent=2))


if __name__ == "__main__":
    main()
