#!/usr/bin/env python3
"""Audit exact-identity MCS source evidence without changing recording data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from axion_mea.io.mcs_h5 import ANALOG_PATH, inspect_mcs_h5
from axion_mea.io.mcs_msrd import _fields
from prepare_mcs_aind_recording import inspect_input, inspect_original_msrd


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def plain(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        return [plain(v) for v in value.tolist()]
    if isinstance(value, np.generic):
        return plain(value.item())
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def index_sources(roots: list[Path]) -> dict[str, dict[str, list[Path]]]:
    result: dict[str, dict[str, list[Path]]] = {}
    for root in roots:
        for path in root.rglob("*"):
            kind = path.suffix.lower()
            if kind not in {".h5", ".msrd", ".xml"} or not path.is_file():
                continue
            if kind == ".xml":
                match = re.fullmatch(r"(.+McsRecording)MEA[^/]*\.xml", path.name)
                if match is None:
                    continue
                stem = match[1]
            else:
                stem = path.stem
            recording_id = (path.parent.relative_to(root) / stem).as_posix()
            result.setdefault(recording_id, {}).setdefault(kind[1:], []).append(path)
    return result


def inspect_msrd_header(path: Path, prep: dict) -> dict:
    with path.open("rb") as handle:
        top_bytes = handle.read(1900)
        top = _fields(top_bytes)
        if top.get("FileID") != "MULTI_CHANNEL_SUITE" or top.get("FileVersion") != "17":
            raise ValueError("Unsupported source MSRD header")
        recording_offset = int(top["FPosFirstRecordingHdr"])
        handle.seek(recording_offset)
        rec = _fields(handle.read(1900))
        first_block = int(rec["FPosNext"])
        if not recording_offset < first_block <= 2_000_000:
            raise ValueError("Invalid source MSRD metadata boundary")
        handle.seek(0)
        metadata = handle.read(first_block)
    text = metadata[recording_offset:].decode("ascii", errors="strict")
    analog = text[text.index("DataType=Analog"):text.index("DataType=Event")]
    channels = [_fields(("Entity=" + part).encode("ascii"))
                for part in re.split(r"\r\nEntity=", analog)[1:]]
    channels = [row for row in channels if "ChID" in row]
    labels = [row["Label"] for row in channels]
    gains = [float(row["ConversionFactor"]) * 10.0 ** int(row["Exponent"]) for row in channels]
    zeros = [int(row["ADZero"]) for row in channels]
    ticks = [int(row["Tick"]) for row in channels]
    if labels != prep["channel_labels"] or [int(row["ChID"]) for row in channels] != list(range(len(labels))):
        raise ValueError("Source MSRD channel identities disagree with staged metadata")
    if any(t <= 0 or not np.isclose(1e6 / t, prep["sampling_frequency_hz"]) for t in ticks):
        raise ValueError("Source MSRD sample rate disagrees with staged metadata")
    if not np.allclose(gains, prep["conversion_to_volts"], rtol=1e-12, atol=0):
        raise ValueError("Source MSRD gains disagree with staged metadata")
    if any(zeros) or not np.all(np.isfinite(gains)) or min(gains) <= 0:
        raise ValueError("Source MSRD requires unsupported offset or invalid gain")
    if any(row.get("Unit") != "V" for row in channels):
        raise ValueError("Source MSRD analog calibration is not expressed in volts")
    if int(rec["TimeStamp"]) != int(prep["first_timestamp"]):
        raise ValueError("Source MSRD first timestamp disagrees with staged metadata")
    model = top.get("MeaName")
    match = re.fullmatch(r"60MEA(100|200)/(10|30)(iR)?", model or "")
    if match is None:
        raise ValueError(f"Unsupported source MSRD geometry {model!r}")
    if bool(match[3]) != ("Ref" in labels):
        raise ValueError("Source MSRD reference disagrees with its MEA model")
    return {"source_msrd": str(path), "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
            "metadata_bytes": len(metadata), "file_size": path.stat().st_size,
            "header": top, "recording_header": rec, "channel_metadata": channels,
            "configured_mea_name": model, "pitch_um": int(match[1]),
            "adc_zero": zeros, "conversion_to_volts": gains,
            "geometry_evidence": "original MSRD MeaName and MeaLayout, matched channel identities"}


def validate_timestamps(stamps: np.ndarray, samples: int, tick: int, first: int) -> None:
    if stamps.ndim != 2 or stamps.shape[1] != 3 or len(stamps) == 0:
        raise ValueError("Unsupported source timestamp layout")
    expected_index, expected_timestamp = 0, first
    for timestamp, start, end in stamps.tolist():
        if start != expected_index or timestamp != expected_timestamp or end < start:
            raise ValueError("Source timestamps have gaps, overlaps, or inconsistent time origins")
        expected_index = int(end) + 1
        expected_timestamp = first + expected_index * tick
    if expected_index != samples:
        raise ValueError("Source timestamp intervals do not cover staged samples")


def inspect_h5(path: Path, input_dir: Path, prep: dict, window_samples: int = 1024) -> dict:
    source = inspect_mcs_h5(path)
    if list(source.channel_labels) != prep["channel_labels"]:
        raise ValueError("Source HDF5 channel order differs from staged metadata")
    if source.sample_count != prep["sample_count"] or not np.isclose(source.sampling_frequency_hz, prep["sampling_frequency_hz"]):
        raise ValueError("Source HDF5 dimensions differ from staged metadata")
    if not np.allclose(source.conversion_to_volts, prep["conversion_to_volts"], rtol=1e-12, atol=0):
        raise ValueError("Source HDF5 gain differs from staged metadata")
    if list(source.events) != prep["events"]:
        raise ValueError("Source HDF5 hardware events differ from staged metadata")
    binary_path = input_dir / Path(prep["binary_file"]).name
    size = prep["sample_count"] * prep["n_chan_bin"] * 4
    if binary_path.stat().st_size != size:
        raise ValueError("Staged binary size mismatch")
    metadata = {"source_h5": str(path), "file_size": path.stat().st_size,
                "file_mtime_ns": path.stat().st_mtime_ns, "sampled_windows": []}
    with h5py.File(path, "r") as handle:
        stream = handle[ANALOG_PATH]
        info = stream["InfoChannel"][:]
        zeros_field = next((key for key in ("ADZero", "ADCZero") if key in info.dtype.names), None)
        if zeros_field is None:
            raise ValueError("Source HDF5 has no ADC zero metadata")
        zeros = np.asarray(info[zeros_field])
        if np.any(zeros != 0):
            raise ValueError("Source HDF5 nonzero ADC offsets require explicit calibration support")
        if "Unit" in info.dtype.names and any(plain(unit) != "V" for unit in info["Unit"]):
            raise ValueError("Source HDF5 analog calibration is not expressed in volts")
        stamps = stream["ChannelDataTimeStamps"][:]
        validate_timestamps(stamps, prep["sample_count"], int(info["Tick"][0]), prep["first_timestamp"])
        metadata["attributes"] = {key: {k: plain(v) for k, v in handle[key].attrs.items()}
                                  for key in ("Data", "Data/Recording_0", ANALOG_PATH)}
        metadata["channel_metadata"] = [{key: plain(row[key]) for key in info.dtype.names} for row in info]
        metadata["channel_timestamps"] = stamps.tolist()
        metadata["adc_zero"] = zeros.tolist()
        metadata["conversion_to_volts"] = list(source.conversion_to_volts)
        metadata["events"] = list(source.events)
        n = int(prep["sample_count"])
        width = min(window_samples, n)
        starts = sorted({0, max(0, n // 2 - width // 2), n - width})
        indices = list(source.signal_channel_indices)
        with binary_path.open("rb") as binary:
            for start in starts:
                binary.seek(start * prep["n_chan_bin"] * 4)
                data = binary.read(width * prep["n_chan_bin"] * 4)
                staged = np.frombuffer(data, dtype="<i4").reshape(width, prep["n_chan_bin"])
                original = stream["ChannelData"][indices, start:start + width].T
                if not np.array_equal(original, staged):
                    raise ValueError(f"Source HDF5/staged binary disagree at sample window {start}")
                metadata["sampled_windows"].append({"start_sample": start, "sample_count": width,
                    "sha256_int32_sample_major": hashlib.sha256(data).hexdigest(), "exact_match": True})
    metadata["status"] = "validated_sampled_windows"
    metadata["scope"] = "metadata and three windows across all signal channels; not a whole-file equivalence proof"
    return metadata


def nominal_time(stem: str) -> str | None:
    match = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})", stem)
    return f"{match[1]}T{match[2]}:{match[3]}:{match[4]}" if match else None


def audit(staged_root: Path, source_roots: list[Path], readiness_csv: Path, output_dir: Path,
          minimum_duration: float = 30.0, *, allow_staged_geometry: bool = False,
          allow_short_recordings: bool = False) -> dict:
    index = index_sources(source_roots)
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_root = output_dir / "source_evidence"
    evidence_root.mkdir(exist_ok=True)
    records = []
    staged_ids = set()
    for prep_path in sorted(staged_root.rglob("mcs_preparation_manifest.json")):
        input_dir = prep_path.parent
        recording_id = input_dir.relative_to(staged_root).as_posix()
        staged_ids.add(recording_id)
        prep = json.loads(prep_path.read_text())
        candidates = index.get(recording_id, {})
        duration = prep["sample_count"] / prep["sampling_frequency_hz"]
        row = {"recording_id": recording_id, "input_dir": str(input_dir), "source_xml": None,
               "source_h5": None, "source_msrd": None, "status": "ready", "reason": "",
               "duration_s": duration, "channel_count": prep["n_chan_bin"], "staged": True,
               "rejected_h5": []}
        reasons = []
        evidence = {"schema_version": 1, "recording_id": recording_id, "source_h5": None,
                    "h5_evidence_status": "unavailable", "h5_temporal_attributes": {},
                    "source_nominal_acquisition_datetime": nominal_time(input_dir.name),
                    "nominal_datetime_source": "original recording filename",
                    "acquisition_timezone": None, "acquisition_utc": None,
                    "first_sample_timestamp_microseconds": prep["first_timestamp"],
                    "source_xml_paths_inspected": [], "xml_clock_fields": {},
                    "source_preparation_manifest_sha256": hashlib.sha256(prep_path.read_bytes()).hexdigest(),
                    "source_xml_evidence": [], "source_msrd_evidence": [], "source_h5_evidence": []}
        xml_candidates = candidates.get("xml", [])
        if not xml_candidates:
            reasons.append("source_xml_missing")
        for path in xml_candidates:
            evidence["source_xml_paths_inspected"].append(str(path))
            try:
                checked = inspect_input(input_dir, path)
                entry = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "configured_mea_name": checked["model"], "pitch_um": checked["pitch_um"], "status": "verified"}
                row.update(source_xml=str(path), configured_mea_name=checked["model"], pitch_um=checked["pitch_um"])
                for element in ET.parse(path).getroot().iter():
                    tag = element.tag.rsplit("}", 1)[-1]
                    if re.search(r"(^UTC|TimeZone|Timezone|DateTime|AcquisitionDate|RecordingDate)", tag) and element.text:
                        evidence["xml_clock_fields"][tag] = element.text.strip()
            except Exception as exc:
                entry = {"path": str(path), "status": "failed", "error": str(exc)}
                reasons.append("source_xml_invalid:" + str(exc))
            evidence["source_xml_evidence"].append(entry)
        for path in candidates.get("msrd", []):
            row["source_msrd"] = str(path)
            try:
                entry = inspect_msrd_header(path, prep)
                if row.get("configured_mea_name") not in (None, entry["configured_mea_name"]):
                    raise ValueError("MSRD and XML geometry disagree")
                row["msrd_geometry_verified"] = True
                row.setdefault("configured_mea_name", entry["configured_mea_name"])
                row.setdefault("pitch_um", entry["pitch_um"])
            except Exception as exc:
                entry = {"source_msrd": str(path), "status": "failed", "error": str(exc)}
                reasons.append("source_msrd_invalid:" + str(exc))
            evidence["source_msrd_evidence"].append(entry)
        for path in candidates.get("h5", []):
            try:
                entry = inspect_h5(path, input_dir, prep)
                if row["source_h5"] is None:
                    row["source_h5"] = str(path)
                    evidence["source_h5"] = str(path)
                    evidence["h5_evidence_status"] = "inspected"
                    evidence["h5_temporal_attributes"] = {k: {name: value for name, value in values.items()
                        if name in {"Date", "DateInTicks", "DateTicks", "TimeStamp", "Duration", "Timezone", "TimeZone", "UTC"}}
                        for k, values in entry["attributes"].items()}
            except Exception as exc:
                entry = {"source_h5": str(path), "status": "failed", "error": str(exc)}
                row["rejected_h5"].append({"path": str(path), "reason": str(exc)})
            evidence["source_h5_evidence"].append(entry)
        h5_failed = bool(candidates.get("h5")) and row["source_h5"] is None
        if (not xml_candidates or h5_failed) and row["source_msrd"]:
            try:
                original = Path(row["source_msrd"])
                if not xml_candidates:
                    checked = inspect_input(input_dir, None, original)
                    source_checked = checked["msrd_evidence"]
                    row.update(configured_mea_name=checked["model"], pitch_um=checked["pitch_um"])
                    reasons.remove("source_xml_missing")
                else:
                    source_checked = inspect_original_msrd(original, prep, input_dir)
                evidence["source_msrd_continuity_and_samples"] = source_checked
                row["source_msrd_fully_inspected"] = True
                if h5_failed:
                    row["source_h5_warning"] = "Local HDF5 failed validation; original MSRD metadata and sample windows verified"
            except Exception as exc:
                reasons.append("source_msrd_full_validation_failed:" + str(exc))
        if h5_failed and not row.get("source_msrd_fully_inspected"):
            reasons.append("all_matching_h5_failed_validation")
        try:
            checked = inspect_input(input_dir, Path(row["source_xml"]) if row["source_xml"] else None,
                                    Path(row["source_msrd"]) if row["source_msrd"] and not row["source_xml"] else None,
                                    allow_staged_geometry=allow_staged_geometry)
            row.update(geometry_status=checked["geometry_status"], configured_mea_name=checked["model"],
                       pitch_um=checked["pitch_um"], sorting_pitch_um=checked["sorting_pitch_um"],
                       source_review_warning=checked["source_review_warning"],
                       source_h5_cleanup_allowed=checked["geometry_status"] == "source_verified")
            if allow_staged_geometry and checked["geometry_status"] == "staged_unverified":
                waived = [reason for reason in reasons if reason == "source_xml_missing"
                          or reason.startswith("source_msrd_full_validation_failed:")]
                reasons = [reason for reason in reasons if reason not in waived]
                row["waived_source_blockers"] = waived
        except Exception as exc:
            if allow_staged_geometry:
                reasons.append("staged_input_invalid:" + str(exc))
        if duration < minimum_duration:
            if not allow_short_recordings:
                reasons.append(f"duration_below_{minimum_duration:g}s_workflow_minimum")
            elif prep["sample_count"] < 4 * 31:
                reasons.append("too_few_samples_for_two_waveform_padded_batches")
            row["short_recording_policy"] = ("explicit_attempt_below_established_minimum"
                                              if allow_short_recordings else "blocked_by_established_minimum")
        else:
            row["short_recording_policy"] = "established_minimum"
        row["status"] = "blocked" if reasons else "ready"
        row["reason"] = "; ".join(reasons)
        row["eligibility"] = row["status"]
        row["source_h5_paths"] = [str(p) for p in candidates.get("h5", [])]
        row["cleanup_note"] = ("Rejected HDF5 copies must be retained" if row["rejected_h5"] else
                               "Only selected validated HDF5 may be considered after completed output validation"
                               if row["source_h5"] else "No local HDF5 available")
        if row.get("geometry_status") == "staged_unverified":
            row["cleanup_note"] = "No HDF5 deletion permitted for staged-geometry fallback"
        evidence["geometry_status"] = row.get("geometry_status")
        evidence["source_review_warning"] = row.get("source_review_warning")
        evidence["short_recording_policy"] = row["short_recording_policy"]
        evidence["preflight_status"] = row["status"]
        evidence["preflight_reason"] = row["reason"]
        evidence_path = evidence_root / (hashlib.sha256(recording_id.encode()).hexdigest()[:20] + ".json")
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
        row["source_time_evidence_json"] = str(evidence_path)
        records.append(row)
    for source in read_csv(readiness_csv):
        recording_id = "/".join([source["experimental_group"], source["condition_path"], source["recording_stem"]])
        if recording_id in staged_ids:
            continue
        records.append({"recording_id": recording_id, "input_dir": None, "source_xml": None,
                        "source_h5": None, "source_msrd": None, "status": "blocked", "eligibility": "blocked",
                        "reason": source["sorting_readiness"] + ": " + source["blocking_reason"],
                        "duration_s": source["duration_s"], "channel_count": source["signal_channel_count"],
                        "staged": False, "original_source_msrd": source["source_msrd_path"]})
    report = {"schema_version": 1, "generated_utc": datetime.now(timezone.utc).isoformat(),
              "staged_root": str(staged_root), "source_roots": [str(p) for p in source_roots],
              "policies": {"allow_staged_geometry": allow_staged_geometry,
                           "allow_short_recordings": allow_short_recordings,
                           "established_minimum_duration_s": minimum_duration},
              "summary": {"records": len(records), "staged_records": len(staged_ids),
                          "status_counts": dict(Counter(row["status"] for row in records)),
                          "geometry_counts": dict(Counter(row.get("geometry_status", "not_staged") for row in records)),
                          "matched_xml": sum(bool(row["source_xml"]) for row in records),
                          "matched_valid_h5": sum(bool(row["source_h5"]) for row in records),
                          "unmatched_local_sources": sorted(set(index) - staged_ids)}, "records": records}
    index_path = output_dir / "mcs_batch_source_index.json"
    temporary = index_path.with_suffix(".json.partial")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(index_path)
    keys = sorted({key for row in records for key in row})
    with (output_dir / "mcs_batch_source_index.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows({key: json.dumps(value) if isinstance(value, (dict, list)) else value
                         for key, value in row.items()} for row in records)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, action="append", required=True)
    parser.add_argument("--readiness-csv", type=Path, default=ROOT / "audit-output/mcs_sorting_readiness.csv")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--minimum-duration", type=float, default=30)
    parser.add_argument("--allow-staged-geometry", action="store_true")
    parser.add_argument("--allow-short-recordings", action="store_true")
    args = parser.parse_args()
    report = audit(args.staged_root.resolve(), [p.resolve() for p in args.source_root],
                   args.readiness_csv, args.output_dir.resolve(), args.minimum_duration,
                   allow_staged_geometry=args.allow_staged_geometry,
                   allow_short_recordings=args.allow_short_recordings)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
