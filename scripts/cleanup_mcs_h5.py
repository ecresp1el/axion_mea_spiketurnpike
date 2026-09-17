#!/usr/bin/env python3
"""Delete one explicitly identified local MCS H5 only after durable-output verification."""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import stat
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from axion_mea.io.mcs_h5 import ANALOG_PATH, inspect_mcs_h5
from finalize_mcs_aind_recording import sha256

DEFAULT_ALLOWED_ROOT = Path("/nfs/turbo/umms-parent/mea_multichannel_project/raw_data")
REQUIRED_STAGES = {
    "job_dispatch", "preprocessing", "nwb_ecephys", "spikesort_kilosort4", "postprocessing",
    "curation", "visualization", "results_collector", "quality_control", "nwb_units",
    "quality_control_collector",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def same_path(value, expected: Path) -> bool:
    return bool(value) and Path(value).expanduser().resolve() == expected.resolve()


def json_value(value):
    if isinstance(value, np.ndarray):
        return json_value(value.tolist())
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def candidate_path(source_h5: Path, allowed_root: Path, manifest: dict, input_dir: Path) -> Path:
    candidate = source_h5.expanduser().absolute()
    allowed_root = allowed_root.expanduser().resolve()
    require(allowed_root != Path("/"), "The filesystem root cannot be an H5 cleanup root")
    require(candidate == candidate.resolve(), "Symlink or noncanonical H5 paths are not permitted")
    candidate.relative_to(allowed_root)
    stem = Path(manifest["recording_id"]).name
    require(stem == manifest["recording_stem"], "Recording stem and recording_id disagree")
    require(candidate.name == stem + ".h5", "Only the exact original recording-stem H5 is supported")
    xml = Path(manifest["source_xml"])
    require(xml.name.startswith(stem + "MEA") and xml.suffix == ".xml", "Source XML does not identify this recording")
    if candidate != xml.parent / (stem + ".h5"):
        identity_path = Path(manifest["recording_id"])
        require(not identity_path.is_absolute() and ".." not in identity_path.parts,
                "Recording identity is not a safe relative source path")
        namespaces = ("MANNY_MEAs_chemogenetics", "chemogenetic_project")
        canonical_h5 = {allowed_root / namespace / identity_path.with_name(stem + ".h5")
                        for namespace in namespaces}
        canonical_xml_parents = {allowed_root / namespace / identity_path.parent for namespace in namespaces}
        require(candidate in canonical_h5 and xml.parent in canonical_xml_parents,
                "Cross-collection H5 is outside the exact canonical recording identity paths")
        evidence_path = input_dir / "source_time_evidence.json"
        require(evidence_path.is_file(), "Cross-collection H5 requires explicit source selection evidence")
        selection = read_json(evidence_path)
        require(selection.get("schema_version") == 1 and selection.get("recording_id") == manifest["recording_id"]
                and selection.get("h5_evidence_status") == "inspected"
                and same_path(selection.get("source_h5"), candidate),
                "Cross-collection H5 source selection evidence does not match this recording/path")
    if candidate.exists():
        require(stat.S_ISREG(candidate.lstat().st_mode), "H5 candidate must be a regular file")
    return candidate


def fingerprint(path: Path) -> dict:
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), "H5 candidate is no longer a regular file")
    return {"device": info.st_dev, "inode": info.st_ino, "bytes": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}


def fresh_output_validation(results_dir: Path, input_dir: Path) -> dict:
    import spikeinterface as si
    from finalize_mcs_aind_nwb import finalize as validate_nwb
    from validate_mcs_aind_output import validate

    validation, _ = validate(results_dir, input_dir, input_dir / "aind_params.json")
    require(validation.get("status") == "passed" and not validation.get("errors"),
            f"Fresh output validation failed: {validation.get('errors')}")
    nwb = validate_nwb(results_dir, input_dir, source_h5=None, apply=False)
    require(nwb.get("status") == "already_corrected", "Fresh NWB validation did not confirm corrected output")
    analyzer = si.load_sorting_analyzer(Path(validation["analyzer"]["path"]), load_extensions=False)
    require(analyzer.has_recording(), "Analyzer recording cannot be reloaded")
    recording = analyzer.recording
    require(isinstance(recording, si.BinaryFolderRecording), "Expected durable BinaryFolderRecording")
    description = recording.get_binary_description()
    require(len(description["file_paths"]) == 1, "Expected exactly one retained recording binary")
    return {"validation": validation, "nwb": nwb,
            "recording_folder": recording.to_dict()["kwargs"]["folder_path"],
            "recording_binary": str(description["file_paths"][0])}


def verify_outputs(results_dir: Path, input_dir: Path) -> tuple[dict, dict]:
    manifest = read_json(input_dir / "mcs_recording_manifest.json")
    require(manifest.get("analysis_kind") == "mcs_aind_single_mea_recording", "Not a prepared single-MEA MCS run")
    require(same_path(manifest.get("results_dir"), results_dir), "Input manifest belongs to different results")
    for path in (results_dir / "mcs_recording_manifest.json", results_dir / "repro/mcs_input/mcs_recording_manifest.json"):
        saved = read_json(path)
        for key in ("recording_id", "sorting_run_id", "recording_stem", "source_xml_sha256"):
            require(saved.get(key) == manifest.get(key), f"Recording identity mismatch in {path.name}: {key}")
        require(same_path(saved.get("results_dir"), results_dir), "Saved manifest results path differs")
        require(same_path(saved.get("binary_file"), Path(manifest["binary_file"])), "Saved manifest binary differs")
    require(same_path((results_dir / "repro/results_path.txt").read_text().strip(), results_dir), "Run results provenance differs")
    require(same_path((results_dir / "repro/data_path.txt").read_text().strip(), input_dir), "Run input provenance differs")
    require(sha256(Path(manifest["source_xml"])) == manifest["source_xml_sha256"], "Acquisition XML changed")
    with (results_dir / "nextflow/trace.txt").open(newline="") as handle:
        trace = list(csv.DictReader(handle, delimiter="\t"))
    names = [row["name"].split(" (", 1)[0] for row in trace]
    require(len(trace) == 11 and set(names) == REQUIRED_STAGES, "Expected all 11 distinct pipeline stages")
    require(all(row["status"] == "COMPLETED" and row["exit"] == "0" for row in trace), "Pipeline stage failed or is incomplete")

    validation = read_json(results_dir / "validation_summary.json")
    require(validation.get("status") == "passed" and not validation.get("errors"), "Saved output validation did not pass")
    require(same_path(validation.get("results_dir"), results_dir), "Output validation belongs to another results directory")
    require(validation["input"].get("recording_id") == manifest["recording_id"], "Output validation recording identity differs")
    require(same_path(validation["input"].get("manifest"), input_dir / "mcs_recording_manifest.json"), "Output validation input differs")
    require(same_path(validation["input"].get("binary"), Path(manifest["binary_file"])), "Output validation binary differs")
    durable = read_json(results_dir / "durable_recording_report.json")
    require(durable.get("status") == "validated", "Durable recording was not validated")
    require(same_path(durable.get("analyzer"), Path(validation["analyzer"]["path"])), "Durability report analyzer differs")
    require(same_path(durable.get("original_staged_binary"), Path(manifest["binary_file"])), "Durability report staged binary differs")
    folder = Path(durable["durable_recording_folder"]).resolve()
    folder.relative_to(results_dir / "preprocessed")
    require("scratch" not in folder.parts, "Durable recording is under scratch")
    nwb_path = results_dir / "repro/nwb_finalization_report.json"
    nwb = read_json(nwb_path)
    require(nwb.get("status") == "corrected" and nwb.get("pynwb_reread_and_schema_validation") == "passed", "NWB correction/schema validation did not pass")
    require(same_path(nwb.get("input_dir"), input_dir), "NWB finalization input differs")
    Path(nwb["nwb_path"]).resolve().relative_to(results_dir / "nwb")

    fresh = fresh_output_validation(results_dir, input_dir)
    require(same_path(fresh["recording_folder"], folder), "Active analyzer recording differs from durable report")
    active_binary = Path(fresh["recording_binary"]).resolve()
    active_binary.relative_to(folder)
    require("scratch" not in active_binary.parts, "Active analyzer depends on scratch")
    require(same_path(fresh["nwb"].get("nwb_path"), Path(nwb["nwb_path"])), "Fresh NWB path differs from saved report")
    files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    require(files == sorted(durable["file_sha256"]), "Retained recording file inventory changed")
    hashes = {}
    for relative in files:
        path = folder / relative
        require(not path.is_symlink() and path.resolve().is_relative_to(folder), "Retained recording has a symlink dependency")
        hashes[relative] = sha256(path)
        require(hashes[relative] == durable["file_sha256"][relative], f"Retained recording changed: {relative}")
    binary = Path(manifest["binary_file"])
    require(binary.name == "mcs_signal_channels.int32.bin", "Unexpected staged binary name")
    require(binary.resolve().parent == Path(manifest["source_input_dir"]).resolve(), "Staged binary is outside its source input directory")
    binary_hash = sha256(binary)
    require(binary_hash == durable["original_staged_binary_sha256"], "Staged recording changed since durability validation")
    require(binary_hash == hashes[active_binary.relative_to(folder).as_posix()], "Durable recording differs from staged counts")
    expected_bytes = int(manifest["sample_count"]) * int(manifest["n_chan_bin"]) * 4
    require(binary.stat().st_size == expected_bytes, "Retained int32 dimensions differ from manifest")
    return manifest, {"recording_id": manifest["recording_id"], "sorting_run_id": manifest["sorting_run_id"],
                      "binary_sha256": binary_hash, "retained_binary": str(binary),
                      "durable_recording_binary": str(active_binary), "completed_stage_count": len(trace),
                      "fresh_output_status": fresh["validation"]["status"], "fresh_nwb_status": fresh["nwb"]["status"]}


def verify_h5(candidate: Path, manifest: dict, binary_hash: str) -> dict:
    before = fingerprint(candidate)
    recording = inspect_mcs_h5(candidate)
    require(list(recording.channel_labels) == manifest["channel_labels"], "H5 channel order differs from the prepared recording")
    require(recording.sample_count == int(manifest["sample_count"]), "H5 sample count differs")
    require(np.isclose(recording.sampling_frequency_hz, manifest["sampling_frequency_hz"], rtol=1e-12), "H5 sampling rate differs")
    require(np.allclose(recording.conversion_to_volts, manifest["conversion_to_volts"], rtol=1e-12, atol=0), "H5 gains differ")
    require(recording.first_timestamp == manifest["first_timestamp"], "H5 time origin differs")
    require(len(recording.events) == len(manifest["events"]), "H5 event count differs")
    for source, prepared in zip(recording.events, manifest["events"]):
        for key in ("event_id", "event_label", "timestamp"):
            require(source[key] == prepared[key], f"H5 event {key} differs")
        require(np.isclose(source["time_from_recording_start_s"], prepared["time_from_recording_start_s"], rtol=0, atol=1e-9), "H5 event time differs")
    indices = np.asarray(recording.signal_channel_indices)
    require(len(indices) == manifest["n_chan_bin"], "H5 signal/reference channel mapping differs")
    metadata = {"groups": {}, "channel_info": [], "timestamp_intervals": []}
    signal_digest = hashlib.sha256()
    retained = np.memmap(manifest["binary_file"], mode="r", dtype="<i4", shape=(recording.sample_count, len(indices)))
    with h5py.File(candidate, "r") as handle:
        stream = handle[ANALOG_PATH]
        data, info, stamps = stream["ChannelData"], stream["InfoChannel"][:], stream["ChannelDataTimeStamps"][:]
        require(data.dtype == np.dtype("int32"), "H5 trace dtype is not lossless int32")
        require("ADZero" in info.dtype.names and np.all(info["ADZero"] == 0), "H5 ADC zero differs from zero-offset retained input")
        require(stamps.ndim == 2 and stamps.shape[1] == 3 and len(stamps), "Unsupported H5 timing intervals")
        previous_end = -1
        for timestamp, start, end in stamps:
            require(int(start) == previous_end + 1 and int(end) >= int(start), "H5 timing intervals have gaps or overlap")
            require(int(timestamp) == recording.first_timestamp + int(start) * int(info["Tick"][0]), "H5 sample timestamps are discontinuous")
            previous_end = int(end)
        require(previous_end == recording.sample_count - 1, "H5 timing does not span all samples")
        for key in ("/", "Data", "Data/Recording_0", ANALOG_PATH):
            metadata["groups"][key] = {name: json_value(value) for name, value in handle[key].attrs.items()}
        metadata["channel_info"] = [{key: json_value(row[key]) for key in info.dtype.names} for row in info]
        metadata["timestamp_intervals"] = stamps.tolist()
        metadata["events"] = list(recording.events)
        # Compare every retained sample, including its exact channel order, before source removal.
        for start in range(0, recording.sample_count, 100000):
            stop = min(start + 100000, recording.sample_count)
            block = np.ascontiguousarray(data[:, start:stop][indices].T, dtype="<i4")
            require(np.array_equal(block, retained[start:stop]), f"H5 signal counts differ at frames {start}:{stop}")
            signal_digest.update(block.tobytes())
    require(signal_digest.hexdigest() == binary_hash, "Full H5 signal digest differs from retained binary")
    h5_hash = sha256(candidate)
    require(fingerprint(candidate) == before, "H5 changed during verification")
    return {"h5_sha256": h5_hash, "signal_sha256": signal_digest.hexdigest(), "fingerprint": before, "metadata": metadata}


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_immutable(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink()
    fsync_directory(path.parent)


def write_json_immutable(path: Path, value: dict) -> None:
    write_immutable(path, (json.dumps(value, indent=2) + "\n").encode("utf-8"))


def cleanup(results_dir: Path, input_dir: Path, source_h5: Path, allowed_root: Path = DEFAULT_ALLOWED_ROOT, *, apply: bool = False) -> dict:
    results_dir, input_dir = results_dir.expanduser().resolve(), input_dir.expanduser().resolve()
    initial_manifest = read_json(input_dir / "mcs_recording_manifest.json")
    candidate = candidate_path(source_h5, allowed_root, initial_manifest, input_dir)
    identity = hashlib.sha256((initial_manifest["recording_id"] + "\n" + str(candidate)).encode()).hexdigest()
    ledger = results_dir / "repro/h5_cleanup" / identity
    manifest, gates = verify_outputs(results_dir, input_dir)
    require(manifest == initial_manifest, "Prepared manifest changed during cleanup checks")
    if not candidate.exists():
        require((ledger / "deleted.json").is_file(), "Source H5 is absent without a completed cleanup ledger")
        deleted = read_json(ledger / "deleted.json")
        require(deleted.get("status") == "deleted" and deleted.get("source_h5") == str(candidate)
                and deleted.get("recording_id") == manifest["recording_id"], "Deletion ledger identity differs")
        require(deleted.get("retained_binary_sha256") == gates["binary_sha256"], "Deletion ledger retained counts differ")
        return {**deleted, "status": "already_deleted", "deleted_bytes": 0, "ledger": str(ledger)}
    evidence = verify_h5(candidate, manifest, gates["binary_sha256"])
    record = {"recording_id": manifest["recording_id"], "sorting_run_id": manifest["sorting_run_id"],
              "source_h5": str(candidate), "allowed_root": str(allowed_root.resolve()), "results_dir": str(results_dir),
              "h5_sha256": evidence["h5_sha256"], "bytes": evidence["fingerprint"]["bytes"],
              "size_bytes": evidence["fingerprint"]["bytes"],
              "retained_binary_sha256": gates["binary_sha256"], "fingerprint": evidence["fingerprint"],
              "verified_at_utc": datetime.now(timezone.utc).isoformat(), "gates": gates}
    if not apply:
        return {**record, "status": "eligible_dry_run", "deleted_bytes": 0, "ledger": str(ledger)}

    ledger.mkdir(parents=True, exist_ok=True)
    require(ledger == ledger.resolve(), "Cleanup ledger has a symlink path")
    fsync_directory(ledger.parent)
    fsync_directory(ledger.parent.parent)
    with (ledger / "apply.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(not (ledger / "deleted.json").exists(), "Cleanup already recorded; rerun to verify its final state")
        candidate_path(candidate, allowed_root, manifest, input_dir)
        require(fingerprint(candidate) == evidence["fingerprint"], "H5 changed before cleanup")
        prepared_path = ledger / "prepared.json"
        if prepared_path.exists():
            previous = read_json(prepared_path)
            require(previous.get("status") == "prepared", "Previous cleanup state is not prepared")
            for key in ("source_h5", "recording_id", "h5_sha256", "retained_binary_sha256", "fingerprint"):
                require(previous.get(key) == record[key], "Previous cleanup preparation does not match this H5")
            for name, expected in previous["evidence_sha256"].items():
                require(Path(name).name == name and sha256(ledger / name) == expected, "Prepared cleanup evidence changed")
        else:
            write_json_immutable(ledger / "h5_metadata.json", evidence["metadata"])
            proof_paths = {
                "mcs_recording_manifest.json": input_dir / "mcs_recording_manifest.json",
                "validation_summary.json": results_dir / "validation_summary.json",
                "durable_recording_report.json": results_dir / "durable_recording_report.json",
                "nwb_finalization_report.json": results_dir / "repro/nwb_finalization_report.json",
                "pipeline_trace.tsv": results_dir / "nextflow/trace.txt",
            }
            if (input_dir / "source_time_evidence.json").is_file():
                proof_paths["source_time_evidence.json"] = input_dir / "source_time_evidence.json"
            stem = manifest["recording_stem"]
            for path in Path(manifest["source_xml"]).parent.glob(stem + "*.xml"):
                require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 2_000_000, "Unexpected XML sidecar during evidence preservation")
                proof_paths[path.name] = path
            proof_hashes = {"h5_metadata.json": sha256(ledger / "h5_metadata.json")}
            for name, path in proof_paths.items():
                data = path.read_bytes()
                write_immutable(ledger / name, data)
                proof_hashes[name] = hashlib.sha256(data).hexdigest()
            write_json_immutable(prepared_path, {**record, "status": "prepared", "evidence_sha256": proof_hashes})
        fsync_directory(ledger)
        candidate_path(candidate, allowed_root, manifest, input_dir)
        require(fingerprint(candidate) == evidence["fingerprint"], "H5 changed after evidence was preserved")
        # This is the only source deletion. Neither source directories nor other formats are removed.
        candidate.unlink()
        fsync_directory(candidate.parent)
        deleted = {**record, "status": "deleted", "deleted_bytes": record["size_bytes"],
                   "deleted_at_utc": datetime.now(timezone.utc).isoformat()}
        write_json_immutable(ledger / "deleted.json", deleted)
    return {**deleted, "ledger": str(ledger)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--source-h5", type=Path, required=True)
    parser.add_argument("--allowed-root", type=Path, default=DEFAULT_ALLOWED_ROOT)
    parser.add_argument("--apply", action="store_true", help="Unlink only this verified H5 after writing a durable deletion ledger")
    args = parser.parse_args()
    print(json.dumps(cleanup(args.results_dir, args.input_dir, args.source_h5, args.allowed_root, apply=args.apply), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
