#!/usr/bin/env python3
"""Correct the new MCS NWB export after AIND completes, preserving its original store."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
import spikeinterface as si
import zarr
from hdmf_zarr import NWBZarrIO
from numcodecs import VLenUTF8


MOCK_SUBJECT = {"age": "P50D", "description": "this is a mock mouse.", "sex": "F", "subject_id": "subject"}
NOTE_MARKER = "MCS export provenance correction:"


def json_value(value):
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    return value.decode("utf-8") if isinstance(value, bytes) else value


def scalar_text(array) -> str:
    return str(json_value(np.asarray(array[...]).reshape(-1)[0]))


def one(paths, description: str) -> Path:
    paths = sorted(paths)
    if len(paths) != 1:
        raise ValueError(f"Expected one {description}, found {len(paths)}")
    return paths[0]


def is_timezone_field(name: str) -> bool:
    name = name.lower()
    return "timezone" in name or "utcoffset" in name or name.startswith("utc") or name.endswith("utc")


def inspect_time_sources(manifest: dict, source_h5: Path | None = None, evidence_path: Path | None = None) -> dict:
    """Keep source wall-clock evidence separate from the exporter's required zoned timestamp."""
    stem = manifest["recording_id"].split("/")[-1]
    match = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})", stem)
    if match is None:
        raise ValueError("Cannot identify source nominal acquisition datetime in recording_id")
    nominal = f"{match[1]}T{match[2]}:{match[3]}:{match[4]}"
    datetime.fromisoformat(nominal)
    if evidence_path is not None:
        evidence = json.loads(evidence_path.read_text())
        if evidence.get("schema_version") != 1 or evidence.get("recording_id") != manifest["recording_id"]:
            raise ValueError("Source-time evidence schema or recording identity does not match this recording")
        if evidence.get("source_nominal_acquisition_datetime") != nominal:
            raise ValueError("Persisted nominal acquisition datetime does not match original recording filename")
        if evidence.get("first_sample_timestamp_microseconds") != manifest.get("first_timestamp"):
            raise ValueError("Persisted source-time evidence differs from recording first timestamp")
        if evidence.get("h5_evidence_status") not in {"inspected", "unavailable"}:
            raise ValueError("Source-time evidence must explicitly identify whether H5 was inspected")
        if evidence.get("acquisition_timezone") is not None or evidence.get("acquisition_utc") is not None:
            raise ValueError("Source-time evidence has acquisition timezone information requiring separate review")
        return {**evidence, "evidence_file": str(evidence_path),
                "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                "evidence_origin": "persisted_source_time_audit"}
    if source_h5 is None and (manifest.get("source_h5") or manifest.get("source_file")):
        source_h5 = Path(manifest.get("source_h5") or manifest["source_file"])
    h5_available = source_h5 is not None and source_h5.is_file()
    h5_attributes = {}
    if h5_available:
        with h5py.File(source_h5, "r") as handle:
            def inspect(name, obj):
                relevant = {key: json_value(value) for key, value in obj.attrs.items()
                            if any(token in key.lower() for token in ("date", "time", "utc"))}
                if relevant:
                    h5_attributes[name or "/"] = relevant
            inspect("/", handle)
            handle.visititems(inspect)
    source_xml = Path(manifest["source_xml"]) if manifest.get("source_xml") else None
    source_xml_paths = sorted({path for path in ({source_xml, *source_xml.parent.glob(f"{stem}*.xml")} if source_xml else set())
                               if path.is_file()})
    xml_clock_fields = {}
    for xml_path in source_xml_paths:
        for element in ET.parse(xml_path).iter():
            name = element.tag.split("}")[-1]
            if is_timezone_field(name) or "datetime" in name.lower() or "datecreated" in name.lower():
                if element.text and element.text.strip():
                    xml_clock_fields[f"{xml_path.name}/{name}"] = element.text.strip()
    timezone_fields = {f"{group}/{key}": value for group, fields in h5_attributes.items() for key, value in fields.items()
                       if is_timezone_field(key)}
    timezone_fields.update({key: value for key, value in xml_clock_fields.items()
                            if is_timezone_field(key.split("/")[-1])})
    if timezone_fields:
        raise ValueError("Source has timezone/UTC metadata; review its semantics before using placeholder-time finalization")
    return {
        "schema_version": 1, "recording_id": manifest["recording_id"],
        "source_h5": str(source_h5) if source_h5 else None, "h5_temporal_attributes": h5_attributes,
        "h5_evidence_status": "inspected" if h5_available else "unavailable",
        "source_file_provenance": manifest.get("source_file"),
        "source_xml": str(source_xml) if source_xml else None, "source_xml_paths_inspected": [str(path) for path in source_xml_paths],
        "source_msrd": manifest.get("source_msrd"), "source_msrd_metadata_file": manifest.get("source_msrd_metadata_file"),
        "xml_clock_fields": xml_clock_fields,
        "source_nominal_acquisition_datetime": nominal, "nominal_datetime_source": "original recording filename",
        "acquisition_timezone": None, "acquisition_utc": None,
        "first_sample_timestamp_microseconds": manifest.get("first_timestamp"),
        "interpretation": ("Source clock has no verified timezone; no acquisition UTC instant is asserted." if h5_available else
                           "Local source H5 is unavailable and was not inspected. Nominal filename time has no verified timezone; no acquisition UTC instant is asserted."),
    }


def read_subject(root) -> dict | None:
    if "general/subject" not in root:
        return None
    return {key: scalar_text(root["general/subject"][key]) for key in root["general/subject"].array_keys()}


def compare_nwb(root, sorting, analyzer, channels: list[dict], manifest: dict, *, require_volts: bool) -> dict:
    """Reconcile all units, spike times and waveforms before any output is replaced."""
    units = root["units"]
    ids = units["ks_unit_id"][:]
    if len(ids) != len(sorting.unit_ids) or set(ids.tolist()) != set(sorting.unit_ids.tolist()):
        raise ValueError("NWB ks_unit_id does not match all curated units")
    if len(np.unique(ids)) != len(ids) or len(units["id"]) != len(ids):
        raise ValueError("NWB unit IDs are duplicated or incomplete")
    if not np.array_equal(units["original_cluster_id"][:], sorting.get_property("original_cluster_id", ids=ids)):
        raise ValueError("NWB original Kilosort IDs differ from curated sorting")
    indices = units["spike_times_index"][:]
    times = units["spike_times"]
    if len(indices) != len(ids) or np.any(np.diff(indices.astype("int64")) < 0) or int(indices[-1]) != len(times):
        raise ValueError("NWB ragged spike-time indices are inconsistent")
    fs = float(manifest["sampling_frequency_hz"])
    duration = int(manifest["sample_count"]) / fs
    start = 0
    for unit, stop in zip(ids, indices):
        observed = times[start:int(stop)]
        expected = sorting.get_unit_spike_train(unit) / fs
        if observed.shape != expected.shape or not np.allclose(observed, expected, rtol=0, atol=1e-10):
            raise ValueError(f"NWB spike times differ for curated unit {unit}")
        if np.any(observed < 0) or np.any(observed >= duration):
            raise ValueError(f"NWB spike times exceed source bounds for unit {unit}")
        start = int(stop)
    electrodes = root["general/extracellular_ephys/electrodes"]
    positions = np.asarray([[float(row["x_um"]), float(row["y_um"])] for row in channels])
    observed_positions = np.column_stack([electrodes["rel_x"][:], electrodes["rel_y"][:]])
    if len(electrodes["id"]) != len(channels) or observed_positions.shape != positions.shape or not np.allclose(observed_positions, positions):
        raise ValueError("NWB electrode geometry/order differs from prepared MCS channel map")
    if not analyzer.return_in_uV:
        raise ValueError("Analyzer waveforms are not calibrated in microvolts")
    if not np.array_equal(analyzer.channel_ids, analyzer.recording.channel_ids):
        raise ValueError("Analyzer waveform channel order differs from its recording")
    row_indices = analyzer.sorting.ids_to_indices(ids)
    extension = analyzer.get_extension("templates")
    waveform_checks = {}
    for name, operator in (("waveform_mean", "average"), ("waveform_sd", "std")):
        expected_uv = extension.get_templates(operator=operator)[row_indices]
        observed = units[name][:]
        if observed.shape != expected_uv.shape or not np.isfinite(observed).all():
            raise ValueError(f"NWB {name} shape or finite-value check failed")
        if units[name].attrs.get("unit") != "volts":
            raise ValueError(f"NWB {name} must declare volts per its schema")
        if units[name].attrs.get("sampling_rate") != fs:
            raise ValueError(f"NWB {name} sampling rate differs from source")
        already_volts = np.allclose(observed, expected_uv * 1e-6, rtol=1e-6, atol=1e-12)
        matches_microvolts = np.allclose(observed, expected_uv, rtol=1e-6, atol=1e-8)
        if not already_volts and not matches_microvolts:
            raise ValueError(f"NWB {name} does not match analyzer in either volts or microvolts")
        if require_volts and not already_volts:
            raise ValueError(f"NWB {name} is still numerically in microvolts")
        waveform_checks[name] = {"shape": list(observed.shape), "declared_unit": "volts",
                                 "scale_to_apply": 1.0 if already_volts else 1e-6,
                                 "matches_analyzer_after_scaling": True}
    return {"unit_count": len(ids), "spike_count": len(times), "sampling_frequency_hz": fs,
            "electrode_count": len(channels), "ks_unit_ids": ids.tolist(),
            "all_unit_spike_trains_match": True, "all_original_cluster_ids_match": True,
            "electrode_geometry_matches": True, "waveforms": waveform_checks}


def verify_pynwb(path: Path, expected_unit_count: int, removed_mock: bool) -> None:
    import pynwb

    with NWBZarrIO(path=str(path), mode="r", load_namespaces=True) as io:
        nwbfile = io.read()
        if len(nwbfile.units) != expected_unit_count or not nwbfile.notes or NOTE_MARKER not in nwbfile.notes:
            raise ValueError("PyNWB reread does not retain units and correction notes")
        if removed_mock and nwbfile.subject is not None:
            raise ValueError("Mock subject remains after correction")
        schema_errors = pynwb.validate(io=io)
        if schema_errors:
            raise ValueError(f"NWB schema validation failed: {[str(error) for error in schema_errors]}")


def finalize(results_dir: Path, input_dir: Path, source_h5: Path | None = None, *, apply: bool,
             source_time_evidence: Path | None = None) -> dict:
    manifest = json.loads((input_dir / "mcs_recording_manifest.json").read_text())
    if manifest.get("analysis_kind") != "mcs_aind_single_mea_recording":
        raise ValueError("Finalization is restricted to prepared single-MEA MCS runs")
    if Path(manifest["results_dir"]).resolve() != results_dir.resolve():
        raise ValueError("Prepared manifest does not identify this results directory")
    with (input_dir / "channels.csv").open(newline="") as handle:
        channels = list(csv.DictReader(handle))
    nwb_path = one((results_dir / "nwb").glob("*.nwb"), "final NWB store")
    if not nwb_path.is_dir():
        raise ValueError("This correction supports the established AIND NWB Zarr backend only")
    sorting = si.load(one((results_dir / "curated").glob("*/numpysorting_info.json"), "curated sorting").parent)
    if not len(sorting.unit_ids):
        raise ValueError("Cannot finalize an NWB with no curated units")
    analyzer = si.load_sorting_analyzer(one((results_dir / "postprocessed").glob("*.zarr"), "analyzer"), load_extensions=False)
    root = zarr.open_group(str(nwb_path), mode="r")
    before = compare_nwb(root, sorting, analyzer, channels, manifest, require_volts=False)
    subject = read_subject(root)
    original_notes = scalar_text(root["general/notes"]) if "general/notes" in root else None
    original_session_time = scalar_text(root["session_start_time"])
    original_reference_time = scalar_text(root["timestamps_reference_time"])
    repro = results_dir / "repro"
    report_path = repro / "nwb_finalization_report.json"
    backup_path = repro / "original_nwb_before_mcs_corrections" / nwb_path.name
    if report_path.exists():
        report = json.loads(report_path.read_text())
        if report.get("status") != "corrected" or report.get("nwb_path") != str(nwb_path):
            raise ValueError("Existing finalization report is incomplete or belongs to another NWB")
        if not backup_path.is_dir():
            raise ValueError("Original NWB backup is missing")
        if Path(report["input_dir"]).resolve() != input_dir.resolve():
            raise ValueError("Existing finalization report belongs to another prepared recording")
        if report["source_time"].get("recording_id", manifest["recording_id"]) != manifest["recording_id"]:
            raise ValueError("Saved timing evidence belongs to another recording")
        verified = compare_nwb(root, sorting, analyzer, channels, manifest, require_volts=True)
        verify_pynwb(nwb_path, len(sorting.unit_ids), report["removed_exact_mock_subject"])
        if any(check["scale_to_apply"] != 1 for check in before["waveforms"].values()):
            raise ValueError("Previously finalized waveform scaling has changed")
        return {**report, "status": "already_corrected", "after": verified}
    if NOTE_MARKER in (original_notes or "") or backup_path.exists():
        raise ValueError("Partial previous finalization detected; inspect saved backup before proceeding")
    if source_time_evidence is None and manifest.get("source_time_evidence_json"):
        source_time_evidence = Path(manifest["source_time_evidence_json"])
        if not source_time_evidence.is_absolute():
            source_time_evidence = input_dir / source_time_evidence
    source_time = inspect_time_sources(manifest, source_h5, source_time_evidence)
    removed_mock = subject == MOCK_SUBJECT
    note = (
        f"{NOTE_MARKER} session_start_time ({original_session_time}) and timestamps_reference_time "
        f"({original_reference_time}) are AIND processing-time placeholders, NOT verified acquisition times. "
        f"The original recording filename gives nominal acquisition wall time "
        f"{source_time['source_nominal_acquisition_datetime']}; acquisition timezone/UTC offset is unknown. "
        "Spike times are seconds from the first exported recording sample; no source clock or stimulus shift was applied. "
        "Waveform mean and standard deviation are stored numerically in volts, checked against the calibrated "
        "SpikeInterface analyzer in microvolts. "
        + ("The exact AIND mock Subject was removed; biological subject metadata is unassigned. " if removed_mock else "")
        + ("No local source H5 was available for source-clock inspection; the nominal time comes from the original filename. "
           if source_time["h5_evidence_status"] == "unavailable" else "")
        + "Original export and correction evidence are preserved in the result repro directory."
    )
    notes = f"{original_notes}\n\n{note}" if original_notes else note
    report = {
        "status": "planned", "nwb_path": str(nwb_path), "input_dir": str(input_dir),
        "original_nwb_backup": str(backup_path),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_time": source_time, "original_subject": subject, "removed_exact_mock_subject": removed_mock,
        "original_notes": original_notes, "original_session_start_time": original_session_time,
        "original_timestamps_reference_time": original_reference_time, "corrected_notes": notes,
        "time_action": "Retain and explicitly label processing-time placeholders; acquisition timezone is unknown.",
        "before": before,
    }
    if not apply:
        return report
    staging = nwb_path.with_name(nwb_path.name + ".mcs_finalizing")
    if staging.exists():
        raise ValueError(f"Finalization staging directory already exists: {staging}")
    repro.mkdir(exist_ok=True)
    script_copy = repro / Path(__file__).name
    shutil.copy2(Path(__file__), script_copy)
    report["script_sha256"] = hashlib.sha256(script_copy.read_bytes()).hexdigest()
    (repro / "source_time_evidence.json").write_text(json.dumps(source_time, indent=2) + "\n", encoding="utf-8")
    shutil.copytree(nwb_path, staging)
    try:
        corrected = zarr.open_group(str(staging), mode="r+")
        if removed_mock:
            del corrected["general/subject"]
        for name, check in before["waveforms"].items():
            if check["scale_to_apply"] != 1:
                corrected["units"][name][:] = corrected["units"][name][:] * check["scale_to_apply"]
        general = corrected["general"]
        notes_array = general.create_dataset("notes", data=np.asarray([notes], dtype=object),
                                             object_codec=VLenUTF8(), overwrite=True)
        notes_array.attrs["zarr_dtype"] = "scalar"
        zarr.consolidate_metadata(str(staging))
        report["after"] = compare_nwb(corrected, sorting, analyzer, channels, manifest, require_volts=True)
        verify_pynwb(staging, len(sorting.unit_ids), removed_mock)
        backup_path.parent.mkdir(exist_ok=True)
        nwb_path.rename(backup_path)
        try:
            staging.rename(nwb_path)
        except Exception:
            backup_path.rename(nwb_path)
            raise
        report["status"] = "corrected"
        report["pynwb_reread_and_schema_validation"] = "passed"
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--source-h5", type=Path, help="Optional local source H5 for temporal-metadata inspection")
    parser.add_argument("--source-time-evidence", type=Path, help="Optional persisted source-time audit JSON")
    parser.add_argument("--apply", action="store_true", help="Correct only after every AIND job has finished")
    args = parser.parse_args()
    report = finalize(args.results_dir.expanduser().resolve(), args.input_dir.expanduser().resolve(),
                      args.source_h5.expanduser().resolve() if args.source_h5 else None, apply=args.apply,
                      source_time_evidence=args.source_time_evidence.expanduser().resolve() if args.source_time_evidence else None)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
