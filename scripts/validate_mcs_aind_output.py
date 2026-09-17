#!/usr/bin/env python3
"""Validate durable outputs from one MCS recording in the established AIND route."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from axion_mea.io.mcs_h5 import mcs_60mea200_geometry


REQUIRED_EXTENSIONS = {"random_spikes", "templates", "correlograms"}
REQUIRED_SORTER_SETTINGS = {
    "Th_universal": 5,
    "Th_learned": 8,
    "do_CAR": False,
    "nblocks": 0,
    "keep_good_only": False,
    "skip_kilosort_preprocessing": False,
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def scalar(value):
    return value.item() if isinstance(value, np.generic) else value


def scratch_references(value) -> list[str]:
    if isinstance(value, dict):
        return sorted({path for item in value.values() for path in scratch_references(item)})
    if isinstance(value, (list, tuple)):
        return sorted({path for item in value for path in scratch_references(item)})
    if isinstance(value, str) and Path(value).is_absolute() and "scratch" in Path(value).parts:
        return [value]
    return []


def inspect_sorting(sorting, sample_count: int, sampling_frequency: float) -> dict:
    """Inspect spike arrays only; never load the continuous recording."""
    unit_ids = sorting.get_unit_ids()
    spikes = sorting.to_spike_vector()
    errors = []
    if sorting.get_num_segments() != 1:
        errors.append("Expected exactly one continuous segment")
    if not np.isclose(sorting.get_sampling_frequency(), sampling_frequency):
        errors.append("Sorting sampling frequency differs from input")
    invalid = (spikes["sample_index"] < 0) | (spikes["sample_index"] >= sample_count)
    invalid |= (spikes["segment_index"] != 0)
    invalid_units = (spikes["unit_index"] < 0) | (spikes["unit_index"] >= len(unit_ids))
    if np.any(invalid):
        errors.append(f"{int(invalid.sum())} spikes outside recording bounds")
    if np.any(invalid_units):
        errors.append(f"{int(invalid_units.sum())} spikes have invalid unit indices")
    properties = set(sorting.get_property_keys())
    for name in ("KSLabel", "original_cluster_id"):
        if name not in properties:
            errors.append(f"Missing unit property: {name}")
    originals = sorting.get_property("original_cluster_id") if "original_cluster_id" in properties else None
    if originals is not None and len(np.unique(originals)) != len(unit_ids):
        errors.append("original_cluster_id does not uniquely identify units")
    counts = np.bincount(spikes["unit_index"][~invalid_units], minlength=len(unit_ids))
    if len(unit_ids) and np.any(counts == 0):
        errors.append("Sorting contains empty units")
    label_counts = {}
    if "KSLabel" in properties:
        labels, label_totals = np.unique(sorting.get_property("KSLabel"), return_counts=True)
        label_counts = {str(label): int(total) for label, total in zip(labels, label_totals)}
    return {
        "unit_count": len(unit_ids),
        "spike_count": len(spikes),
        "sampling_frequency_hz": sorting.get_sampling_frequency(),
        "segment_count": sorting.get_num_segments(),
        "minimum_sample_index": int(spikes["sample_index"].min()) if len(spikes) else None,
        "maximum_sample_index": int(spikes["sample_index"].max()) if len(spikes) else None,
        "out_of_bounds_spike_count": int(invalid.sum()),
        "properties": sorted(properties),
        "unit_ids": [scalar(unit) for unit in unit_ids],
        "spikes_per_unit": counts.tolist(),
        "kilosort_label_counts": label_counts,
        "errors": errors,
    }


def compare_sortings(source, target, *, require_same_units: bool) -> list[str]:
    """Validate the AIND contract: deduplication removes whole units, preserving IDs."""
    errors = []
    source_ids = source.get_unit_ids().tolist()
    target_ids = target.get_unit_ids().tolist()
    if require_same_units and source_ids != target_ids:
        errors.append("Unit identities or order differ")
    if not set(target_ids).issubset(source_ids):
        errors.append("Target contains unit IDs absent from source")
    for unit in target_ids:
        if unit not in source_ids:
            continue
        if not np.array_equal(source.get_unit_spike_train(unit), target.get_unit_spike_train(unit)):
            errors.append(f"Spike train changed for unit {unit}")
        for prop in ("original_cluster_id", "KSLabel"):
            if prop in source.get_property_keys() and prop in target.get_property_keys():
                left = source.get_property(prop, ids=[unit])
                right = target.get_property(prop, ids=[unit])
                if not np.array_equal(left, right):
                    errors.append(f"{prop} changed for unit {unit}")
    return errors


def choose_one(paths, description: str) -> Path:
    paths = sorted(paths)
    if len(paths) != 1:
        raise ValueError(f"Expected one {description}, found {len(paths)}")
    return paths[0]


def verify_events(input_dir: Path, manifest: dict, duration_s: float) -> dict:
    path = input_dir / "events.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    expected = manifest["events"]
    if len(rows) != len(expected):
        raise ValueError("Event sidecar count differs from preparation manifest")
    tick = float(manifest["timestamp_tick_seconds"])
    first = int(manifest["first_timestamp"])
    if not np.isfinite(tick) or tick <= 0:
        raise ValueError("Invalid source timestamp tick")
    for actual, original in zip(rows, expected):
        time_s = float(actual["time_from_recording_start_s"])
        if (int(actual["event_id"]) != int(original["event_id"])
                or actual["event_label"] != original["event_label"]
                or int(actual["timestamp"]) != int(original["timestamp"])):
            raise ValueError("Event identity differs from source preparation manifest")
        if not np.isfinite(time_s) or not 0 <= time_s < duration_s:
            raise ValueError("Event timestamp falls outside recording bounds")
        if (not np.isclose(time_s, float(original["time_from_recording_start_s"]), rtol=0, atol=1e-9)
                or not np.isclose(time_s, (int(actual["timestamp"]) - first) * tick, rtol=0, atol=1e-9)):
            raise ValueError("Event timing differs from source timestamps or preparation manifest")
    return {"path": str(path), "event_count": len(rows),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "identities_and_relative_source_times_match": True}


def verify_input(input_dir: Path, params: dict, report: dict):
    import spikeinterface as si

    manifest_path = input_dir / "mcs_recording_manifest.json"
    if not manifest_path.exists():
        manifest_path = input_dir / "mcs_preparation_manifest.json"
    manifest = read_json(manifest_path)
    reader = params["job_dispatch"]["spikeinterface_info"]["reader_kwargs"]
    binary_path = input_dir / "mcs_signal_channels.int32.bin"
    if not binary_path.exists():
        binary_path = Path(manifest["binary_file"])
    channels_path = input_dir / "channels.csv"
    if not channels_path.exists():
        channels_path = Path(manifest["channels_csv"])
    with channels_path.open(newline="", encoding="utf-8") as handle:
        channels = list(csv.DictReader(handle))
    sample_count = int(manifest["sample_count"])
    channel_count = int(manifest["n_chan_bin"])
    fs = float(manifest["sampling_frequency_hz"])
    dtype = np.dtype(manifest["binary_dtype"])
    if sample_count <= 0 or not np.isfinite(fs) or fs <= 0:
        raise ValueError("Invalid recording sample count or sampling frequency")
    if "duration_s" in manifest and not np.isclose(float(manifest["duration_s"]), sample_count / fs, rtol=0, atol=1e-9):
        raise ValueError("Declared recording duration disagrees with sample count and rate")
    expected_bytes = sample_count * channel_count * dtype.itemsize
    if binary_path.stat().st_size != expected_bytes:
        raise ValueError("Input binary size disagrees with declared samples/channels/dtype")
    if channel_count not in (59, 60) or dtype != np.dtype("int32"):
        raise ValueError("MCS adapter requires 59 or 60 lossless int32 signal channels")
    if manifest["binary_layout"] != "sample_major_row_major":
        raise ValueError("Input binary must be sample-major")
    model = re.fullmatch(r"60MEA(100|200)/(10|30)(iR)?", manifest["configured_mea_name"])
    if model is None or float(model[1]) != float(manifest["pitch_um"]):
        raise ValueError("Configured MCS model and electrode pitch disagree")
    source_labels = manifest["channel_labels"]
    if len(source_labels) != 60 or int(manifest["channel_count_in_file"]) != len(source_labels):
        raise ValueError("Source channel labels do not describe the configured 60-contact MEA")
    expected_indices = [index for index, label in enumerate(source_labels) if label.lower() != "ref"]
    if len(expected_indices) != channel_count or (channel_count == 59) != bool(model[3]):
        raise ValueError("Configured MEA reference and exported signal-channel count disagree")
    if len(channels) != channel_count or len({row["channel_label"] for row in channels}) != channel_count:
        raise ValueError("Channel map is incomplete or has duplicate electrode labels")
    if any(row["channel_label"].lower() == "ref" for row in channels):
        raise ValueError("Reference electrode is present in the signal-channel map")
    stream_indices = [int(row["stream_channel_index"]) for row in channels]
    if len(set(stream_indices)) != channel_count:
        raise ValueError("Source stream indices are not unique")
    if stream_indices != expected_indices or [row["channel_label"] for row in channels] != [source_labels[i] for i in expected_indices]:
        raise ValueError("Channel mapping or order differs from source labels/reference exclusion")
    geometry = mcs_60mea200_geometry(tuple(row["channel_label"] for row in channels), pitch_um=float(model[1]))
    expected_positions = [[row["x_um"], row["y_um"]] for row in geometry]
    positions = [[float(row["x_um"]), float(row["y_um"])] for row in channels]
    if not np.allclose(positions, expected_positions, rtol=0, atol=1e-9):
        raise ValueError("Channel coordinates differ from source labels and configured MEA pitch")
    if "binary_channel_index" in channels[0]:
        if [int(row["binary_channel_index"]) for row in channels] != list(range(channel_count)):
            raise ValueError("Channel rows are not in binary channel order")
    source_gains = np.asarray(manifest["conversion_to_volts"], dtype=float)
    if source_gains.shape != (len(source_labels),) or min(stream_indices) < 0 or max(stream_indices) >= source_gains.size:
        raise ValueError("Source stream indices do not address the original MCS gain array")
    expected_gain = source_gains[stream_indices] * 1e6
    if expected_gain.shape != (channel_count,) or not np.isfinite(expected_gain).all() or np.any(expected_gain <= 0):
        raise ValueError("Source metadata has invalid MCS voltage gains")
    if "gain_uv_per_count" in channels[0]:
        if not np.allclose([float(row["gain_uv_per_count"]) for row in channels], expected_gain, rtol=1e-10, atol=0):
            raise ValueError("Channel-map calibration disagrees with original MCS gain")
    if "gain_uv_per_count" in manifest and not np.allclose(manifest["gain_uv_per_count"], expected_gain, rtol=1e-10, atol=0):
        raise ValueError("Prepared manifest calibration differs from source stream gains")
    source_prep_path = input_dir / "source_mcs_preparation_manifest.json"
    if manifest_path.name == "mcs_recording_manifest.json" and not source_prep_path.is_file():
        raise ValueError("Original preparation sidecar is required for source metadata validation")
    if source_prep_path.exists():
        source_prep = read_json(source_prep_path)
        for name in ("sample_count", "sampling_frequency_hz", "n_chan_bin", "channel_count_in_file", "channel_labels",
                     "binary_dtype", "binary_layout", "conversion_to_volts", "first_timestamp", "timestamp_tick_seconds", "events"):
            if source_prep.get(name) != manifest.get(name):
                raise ValueError(f"Prepared manifest {name} differs from original source preparation")
    events = verify_events(input_dir, manifest, sample_count / fs)
    for name, expected in (("num_channels", channel_count), ("sampling_frequency", fs), ("dtype", "int32")):
        if reader.get(name) != expected:
            raise ValueError(f"Submitted reader {name} does not match input")
    if reader.get("time_axis", 0) != 0 or reader.get("file_offset", 0) != 0:
        raise ValueError("Submitted reader changes sample-major layout or skips source bytes")
    if len(reader["file_paths"]) != 1 or Path(reader["file_paths"][0]).resolve() != binary_path.resolve():
        raise ValueError("Submitted reader points to a different binary")
    if not np.allclose(reader["gain_to_uV"], expected_gain, rtol=1e-10, atol=0) or not np.allclose(reader.get("offset_to_uV", 0), 0, rtol=0, atol=0):
        raise ValueError("Submitted reader calibration differs from MCS calibration")
    recording = si.read_binary(**reader)
    if recording.get_num_segments() != 1 or recording.get_num_samples() != sample_count:
        raise ValueError("Reloaded binary dimensions differ from source preparation")
    # Check several small windows, including the final samples, without materializing the recording.
    windows = []
    for start in sorted({0, sample_count // 2, max(0, sample_count - 32)}):
        stop = min(start + 32, sample_count)
        raw = recording.get_traces(start_frame=start, end_frame=stop)
        scaled = recording.get_traces(start_frame=start, end_frame=stop, return_in_uV=True)
        if not np.allclose(scaled, raw.astype("float64") * expected_gain, rtol=1e-5, atol=1e-6):
            raise ValueError("Reloaded recording does not reproduce uV calibration")
        windows.append({"start_frame": start, "end_frame": stop})
    report["input"] = {
        "manifest": str(manifest_path), "binary": str(binary_path), "channels_csv": str(channels_path),
        "recording_id": manifest.get("recording_id"), "sample_count": sample_count,
        "sampling_frequency_hz": fs, "duration_s": sample_count / fs,
        "channel_count": channel_count, "dtype": str(dtype), "binary_bytes": expected_bytes,
        "gain_uv_per_count": expected_gain.tolist(), "calibration_windows": windows,
        "configured_mea_name": manifest.get("configured_mea_name"), "pitch_um": manifest.get("pitch_um"),
        "reference_channel_excluded": channel_count == 59,
        "original_preparation_sidecar_verified": source_prep_path.exists(), "events": events,
    }
    return recording, channels, sample_count, fs, windows


def verify_params(results_dir: Path, params_path: Path, params: dict, report: dict) -> None:
    expected = params["spikesorting"]["kilosort4"]["sorter"]
    for name, value in REQUIRED_SORTER_SETTINGS.items():
        if expected.get(name) != value:
            report["errors"].append(f"Submitted sorter setting {name} does not preserve adopted TH5 workflow")
    processing = read_json(results_dir / "processing.json")
    sorting_processes = [p for p in processing["data_processes"] if p.get("process_type") == "Spike sorting"]
    if len(sorting_processes) != 1:
        raise ValueError(f"Expected one recorded spike-sorting process, found {len(sorting_processes)}")
    process = sorting_processes[0]
    actual = process["code"]["parameters"]["sorter_params"]
    mismatches = {key: {"submitted": value, "recorded": actual.get(key)}
                  for key, value in expected.items() if key not in actual or actual[key] != value}
    if mismatches:
        report["errors"].append("Recorded sorter parameters differ from submitted parameters")
    report["parameters"] = {
        "file": str(params_path), "sha256": hashlib.sha256(params_path.read_bytes()).hexdigest(),
        "submitted_sorter": expected, "recorded_sorter": actual, "mismatches": mismatches,
        "processing_output_parameters": process.get("output_parameters", {}),
    }


def validate(results_dir: Path, input_dir: Path, params_path: Path) -> tuple[dict, list[dict]]:
    import spikeinterface as si

    report = {"validated_at_utc": datetime.now(timezone.utc).isoformat(), "results_dir": str(results_dir),
              "spikeinterface_version": si.__version__, "errors": [], "warnings": [], "stages": {}}
    rows = []
    try:
        params = read_json(params_path)
        raw_recording, channels, sample_count, fs, windows = verify_input(input_dir, params, report)
        if (results_dir / "repro/mcs_input/events.csv").exists():
            copied_events = results_dir / "repro/mcs_input/events.csv"
            if hashlib.sha256(copied_events.read_bytes()).hexdigest() != report["input"]["events"]["sha256"]:
                report["errors"].append("Archived result event sidecar differs from prepared input")
        verify_params(results_dir, params_path, params, report)
        paths = {
            stage: choose_one((results_dir / stage).glob("*/numpysorting_info.json"), f"{stage} sorting").parent
            for stage in ("spikesorted", "curated")
        }
        analyzer_path = choose_one((results_dir / "postprocessed").glob("*.zarr"), "postprocessed analyzer")
        analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=False)
        sortings = {stage: si.load(path) for stage, path in paths.items()}
        sortings["postprocessed"] = analyzer.sorting
        for stage, sorting in sortings.items():
            stats = inspect_sorting(sorting, sample_count, fs)
            stats["path"] = str(analyzer_path if stage == "postprocessed" else paths[stage])
            report["stages"][stage] = stats
            report["errors"].extend(f"{stage}: {error}" for error in stats["errors"])
        for source, target, same in (("spikesorted", "postprocessed", False), ("postprocessed", "curated", True)):
            errors = compare_sortings(sortings[source], sortings[target], require_same_units=same)
            report["errors"].extend(f"{source} -> {target}: {error}" for error in errors)
        report["cleanup"] = {
            "redundant_units_removed": len(sortings["spikesorted"].unit_ids) - len(analyzer.unit_ids),
            "removed_unit_ids": [scalar(unit) for unit in sortings["spikesorted"].unit_ids if unit not in analyzer.unit_ids],
            "spikes_removed_with_units": report["stages"]["spikesorted"]["spike_count"] - report["stages"]["postprocessed"]["spike_count"],
            "curated_meaning": "Postprocessing sorting plus available labels; recommendations are not automatically applied.",
        }
        labels = report["stages"]["curated"]["kilosort_label_counts"]
        if labels and labels.get("good", 0) == 0:
            report["warnings"].append("No curated unit has Kilosort's good label; sorted units are not confirmed single neurons.")
        saved = set(analyzer.get_saved_extension_names())
        requested = set(params["postprocessing"].get("extensions", {}))
        report["analyzer"] = {"path": str(analyzer_path), "extensions": sorted(saved),
                              "missing_requested_extensions": sorted(requested - saved),
                              "return_in_uV": bool(analyzer.return_in_uV),
                              "has_recording": analyzer.has_recording()}
        for extension in sorted(REQUIRED_EXTENSIONS - saved):
            report["errors"].append(f"Missing required analyzer extension: {extension}")
        for extension in sorted(requested - saved - REQUIRED_EXTENSIONS):
            report["warnings"].append(f"Requested extension was not persisted by AIND: {extension}")
        for extension in sorted(REQUIRED_EXTENSIONS & saved):
            analyzer.get_extension(extension)
        if not analyzer.return_in_uV:
            report["errors"].append("Analyzer templates are not configured in uV")
        if not analyzer.has_recording():
            report["errors"].append("Analyzer recording cannot be reloaded at its saved paths")
        else:
            recording = analyzer.recording
            references = scratch_references(recording.to_dict(recursive=True))
            report["analyzer"]["scratch_recording_references"] = references
            if references:
                report["errors"].append("Analyzer recording depends on temporary scratch paths")
            if recording.get_num_segments() != 1 or recording.get_num_samples() != sample_count:
                report["errors"].append("Analyzer recording sample count or segment count differs from input")
            if recording.get_num_channels() != len(channels) or recording.get_sampling_frequency() != fs:
                report["errors"].append("Analyzer recording channels or sample rate differs from input")
            positions = np.asarray([[float(row["x_um"]), float(row["y_um"])] for row in channels])
            if not np.allclose(recording.get_channel_locations(), positions):
                report["errors"].append("Analyzer geometry or channel order differs from input mapping")
            for window in windows:
                actual = recording.get_traces(**window, return_in_uV=True)
                expected = raw_recording.get_traces(**window, return_in_uV=True)
                if not np.allclose(actual, expected, rtol=1e-5, atol=1e-6):
                    report["errors"].append(f"Analyzer calibration/counts differ at sample {window['start_frame']}")
            report["analyzer"]["recording_dtype"] = str(recording.get_dtype())
            report["analyzer"]["recording_gains_uv"] = recording.get_channel_gains().tolist()
        initial = sortings["spikesorted"]
        for unit in initial.unit_ids:
            row = {"unit_id": scalar(unit)}
            for stage, sorting in sortings.items():
                present = unit in sorting.unit_ids
                count = len(sorting.get_unit_spike_train(unit)) if present else 0
                row[f"{stage}_present"] = present
                row[f"{stage}_spike_count"] = count
            row["firing_rate_hz"] = row["curated_spike_count"] / (sample_count / fs)
            owner = sortings["curated"] if unit in sortings["curated"].unit_ids else initial
            for prop in owner.get_property_keys():
                value = owner.get_property(prop, ids=[unit])[0]
                row[prop] = scalar(value) if np.ndim(value) == 0 else json.dumps(value.tolist())
            rows.append(row)
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    no_units = bool(report["stages"]) and any(stage["unit_count"] == 0 for stage in report["stages"].values())
    if no_units:
        report["errors"].append("No units survived in at least one required output stage")
    report["status"] = "no_units" if no_units else ("failed" if report["errors"] else "passed")
    report["scope"] = "Durable sorting, analyzer, calibration and submitted-versus-recorded parameters; scheduler success is checked separately."
    return report, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--params-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    results_dir, input_dir, params_path = [path.expanduser().resolve() for path in (args.results_dir, args.input_dir, args.params_file)]
    output_dir = args.output_dir.expanduser().resolve() if args.output_dir else results_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    report, rows = validate(results_dir, input_dir, params_path)
    (output_dir / "validation_summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    columns = list(dict.fromkeys(key for row in rows for key in row)) or ["unit_id"]
    with (output_dir / "unit_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"status": report["status"], "errors": report["errors"], "warnings": report["warnings"],
                      "validation_summary": str(output_dir / "validation_summary.json"),
                      "unit_summary": str(output_dir / "unit_summary.csv")}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
