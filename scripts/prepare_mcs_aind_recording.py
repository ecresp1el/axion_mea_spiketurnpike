#!/usr/bin/env python3
"""Prepare one source-verified MCS recording for the established AIND workflow."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import re
import shlex
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from axion_mea.io.mcs_h5 import mcs_60mea200_geometry
from axion_mea.io.mcs_msrd import _fields, inspect_mcs_msrd


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_.")
    if not value or value in {".", ".."}:
        raise ValueError("Empty or unsafe recording path component.")
    return value


def inspect_original_msrd(source_msrd: Path, prep: dict, input_dir: Path | None = None) -> dict:
    recording = inspect_mcs_msrd(source_msrd)
    if (list(recording.channel_labels) != prep["channel_labels"]
            or recording.sample_count != prep["sample_count"]
            or recording.sampling_frequency_hz != prep["sampling_frequency_hz"]
            or recording.first_timestamp != prep["first_timestamp"]):
        raise ValueError("Original MSRD recording identity or dimensions disagree with staged input.")
    if list(recording.conversion_to_volts) != prep["conversion_to_volts"]:
        raise ValueError("Original MSRD calibration disagrees with staged input.")
    tick = round(1e6 / recording.sampling_frequency_hz)
    for blocks in recording.blocks_by_channel:
        expected = recording.first_timestamp
        for block in blocks:
            if block.size_bytes % 4 or block.timestamp != expected:
                raise ValueError("Original MSRD timestamps are discontinuous.")
            expected += (block.size_bytes // 4) * tick
    with source_msrd.open("rb") as handle:
        metadata = handle.read(recording.blocks_by_channel[0][0].offset)
    top = _fields(metadata[:1900])
    text = metadata.decode("ascii")
    analog = text[text.index("DataType=Analog"):text.index("DataType=Event")]
    channels = [_fields(("Entity=" + part).encode("ascii"))
                for part in re.split(r"\r\nEntity=", analog)[1:]]
    channels = [row for row in channels if "ChID" in row]
    if any(int(row["ADZero"]) != 0 for row in channels):
        raise ValueError("Original MSRD nonzero ADC offsets require calibration support.")
    if any(row.get("Unit") != "V" for row in channels):
        raise ValueError("Original MSRD calibration must be expressed in volts.")
    hardware_labels = {int(row["ChID"]): row["Label"] for row in channels}
    if len(hardware_labels) != len(prep["channel_labels"]):
        raise ValueError("Original MSRD hardware channel identities are incomplete.")
    if list(recording.events) != prep["events"]:
        raise ValueError("Original MSRD events disagree with staged input.")
    windows = []
    if input_dir is not None:
        import numpy as np
        width = min(1024, recording.sample_count)
        starts = sorted({0, max(0, recording.sample_count // 2 - width // 2), recording.sample_count - width})
        binary_path = input_dir / Path(prep["binary_file"]).name
        with source_msrd.open("rb") as source, binary_path.open("rb") as binary:
            for start in starts:
                values = []
                for channel in recording.signal_channel_indices:
                    sample_index, pieces = 0, []
                    for block in recording.blocks_by_channel[channel]:
                        block_end = sample_index + block.size_bytes // 4
                        low, high = max(start, sample_index), min(start + width, block_end)
                        if high > low:
                            source.seek(block.data_offset + (low - sample_index) * 4)
                            pieces.append(np.frombuffer(source.read((high - low) * 4), dtype="<i4"))
                        sample_index = block_end
                        if sample_index >= start + width:
                            break
                    values.append(np.concatenate(pieces))
                original = np.stack(values, axis=1)
                binary.seek(start * prep["n_chan_bin"] * 4)
                data = binary.read(width * prep["n_chan_bin"] * 4)
                staged = np.frombuffer(data, dtype="<i4").reshape(width, prep["n_chan_bin"])
                if not np.array_equal(original, staged):
                    raise ValueError(f"Original MSRD sample window {start} differs from staged binary.")
                windows.append({"start_sample": start, "sample_count": width, "exact_match": True,
                                "sha256_int32_sample_major": hashlib.sha256(data).hexdigest()})
    return {"source_msrd": str(source_msrd), "header": top, "channel_metadata": channels,
            "metadata_sha256": hashlib.sha256(metadata).hexdigest(), "metadata_bytes": len(metadata),
            "configured_mea_name": top.get("MeaName"), "hardware_labels": hardware_labels,
            "sampling_frequency_hz": recording.sampling_frequency_hz,
            "sample_count": recording.sample_count, "first_timestamp": recording.first_timestamp,
            "timestamps_contiguous": True, "events": list(recording.events), "sampled_windows": windows}


def inspect_input(input_dir: Path, source_xml: Path | None, source_msrd: Path | None = None,
                  *, allow_staged_geometry: bool = False) -> dict:
    prep = json.loads((input_dir / "mcs_preparation_manifest.json").read_text())
    channels = read_csv(input_dir / "channels.csv")
    events = read_csv(input_dir / "events.csv")
    binary = input_dir / Path(prep["binary_file"]).name
    if prep["binary_dtype"] != "int32" or prep["binary_layout"] != "sample_major_row_major":
        raise ValueError("This adapter requires the lossless sample-major int32 export.")
    count = int(prep["n_chan_bin"])
    samples = int(prep["sample_count"])
    fs = float(prep["sampling_frequency_hz"])
    if count <= 0 or samples <= 0 or not math.isfinite(fs) or fs <= 0:
        raise ValueError("Invalid recording dimensions or sample rate.")
    if binary.stat().st_size != samples * count * 4:
        raise ValueError("Binary size does not match declared sample count, channel count and int32 dtype.")
    if len(channels) != count:
        raise ValueError("Channel table count does not match binary.")
    indices = [int(c["stream_channel_index"]) for c in channels]
    labels = [c["channel_label"] for c in channels]
    if len(set(indices)) != count or len(set(labels)) != count:
        raise ValueError("Channel source indices and labels must be unique.")
    expected_indices = [i for i, label in enumerate(prep["channel_labels"]) if label.lower() != "ref"]
    if indices != expected_indices or any(prep["channel_labels"][i] != label for i, label in zip(indices, labels)):
        raise ValueError("Exported channel order disagrees with source metadata.")
    if len(prep["conversion_to_volts"]) != len(prep["channel_labels"]):
        raise ValueError("Calibration entry count disagrees with source channel count.")
    has_ref = any(label.lower() == "ref" for label in prep["channel_labels"])
    if len(prep["channel_labels"]) != 60 or count != (59 if has_ref else 60):
        raise ValueError("Staged reference channel and exported channel count disagree.")
    msrd_evidence = None
    source_review_warning = None
    geometry_status = "source_verified"
    model = None
    if source_xml is not None:
        if not source_xml.name.startswith(input_dir.name + "MEA"):
            raise ValueError("Acquisition XML filename does not identify this recording.")
        xml = ET.parse(source_xml).getroot()
        for element in xml.iter():
            element.tag = element.tag.rsplit("}", 1)[-1]
        models = {e.text for e in xml.iter("MeaName") if e.text}
        if len(models) != 1:
            raise ValueError(f"Expected one configured MEA model, found {models}.")
        model = models.pop()
        hardware_labels = {}
        for channel in xml.findall(".//MultiwellLayoutSettings/MeaButtonStates/ChannelState"):
            hardware_id = int(channel.findtext("HardwareID"))
            label = channel.findtext("MeaButtonStateInfo/ChannelName")
            if hardware_id in hardware_labels and hardware_labels[hardware_id] != label:
                raise ValueError("Conflicting hardware channel labels in acquisition XML.")
            hardware_labels[hardware_id] = label
        rates = {float(e.text) for e in xml.iter("SampleRateElectrodes") if e.text}
        geometry_evidence = "recording-matched acquisition XML model and channel labels"
    elif source_msrd is not None:
        if source_msrd.stem != input_dir.name:
            raise ValueError("Original MSRD filename does not identify this recording.")
        try:
            msrd_evidence = inspect_original_msrd(source_msrd, prep, input_dir)
            model = msrd_evidence["configured_mea_name"]
            hardware_labels = msrd_evidence["hardware_labels"]
            rates = {msrd_evidence["sampling_frequency_hz"]}
            geometry_evidence = "recording-matched original MSRD MeaName and channel identities; contiguous original block timestamps"
        except (OSError, ValueError) as exc:
            if not allow_staged_geometry:
                raise
            source_review_warning = f"Original MSRD could not be fully verified: {exc}"
    elif not allow_staged_geometry:
        raise ValueError("An original acquisition XML or original MSRD is required to verify geometry.")
    if model is not None:
        model_match = re.fullmatch(r"60MEA(100|200)/(10|30)(iR)?", model)
        if model_match is None:
            raise ValueError(f"Unsupported source MEA geometry: {model}")
        pitch = float(model_match[1])
        radius = float(model_match[2]) / 2.0
        sorting_pitch, sorting_radius = pitch, radius
        if any(hardware_labels.get(i) != label for i, label in enumerate(prep["channel_labels"])):
            raise ValueError("Source channel order does not match acquisition hardware labels.")
        if bool(model_match[3]) != has_ref:
            raise ValueError("Configured array reference and exported channels disagree.")
        if rates != {fs}:
            raise ValueError(f"Source sample rates {rates} disagree with preparation rate {fs}.")
        positions = mcs_60mea200_geometry(tuple(labels), pitch_um=pitch)
    else:
        if not allow_staged_geometry:
            raise ValueError("Source geometry was not verified.")
        geometry_status = "staged_unverified"
        pitch, radius = None, None
        unit_grid = mcs_60mea200_geometry(tuple(labels), pitch_um=1)
        positions = [{"x_um": float(c["x_um"]), "y_um": float(c["y_um"])} for c in channels]
        pitches = [position[axis] / grid[axis] for position, grid in zip(positions, unit_grid)
                   for axis in ("x_um", "y_um")]
        sorting_pitch = pitches[0]
        if (not math.isfinite(sorting_pitch) or sorting_pitch <= 0
                or any(not math.isfinite(value) or not math.isclose(value, sorting_pitch) for value in pitches)):
            raise ValueError("Staged coordinates do not define a consistent nominal MCS label grid.")
        sorting_radius = sorting_pitch / 20
        geometry_evidence = "staged channel-label grid used as nominal computational geometry; physical model and pitch unverified"
        source_review_warning = source_review_warning or "Original acquisition geometry unavailable; physical distances remain unknown"
    mapped = []
    for binary_index, (source_index, channel, position) in enumerate(zip(indices, channels, positions)):
        gain = float(prep["conversion_to_volts"][source_index]) * 1e6
        if not math.isfinite(gain) or gain <= 0:
            raise ValueError("Invalid physical voltage gain.")
        mapped.append({"binary_channel_index": binary_index, "stream_channel_index": source_index,
                       "channel_label": channel["channel_label"], "x_um": position["x_um"],
                       "y_um": position["y_um"], "gain_uv_per_count": gain})
    for event in events:
        time_s = float(event["time_from_recording_start_s"])
        if not math.isfinite(time_s) or not 0 <= time_s < samples / fs:
            raise ValueError("Hardware event falls outside the recording.")
    if len(events) != len(prep["events"]):
        raise ValueError("Event sidecar disagrees with preparation manifest.")
    for actual, expected in zip(events, prep["events"]):
        if (int(actual["event_id"]) != int(expected["event_id"])
                or actual["event_label"] != expected["event_label"]
                or int(actual["timestamp"]) != int(expected["timestamp"])
                or float(actual["time_from_recording_start_s"]) != float(expected["time_from_recording_start_s"])):
            raise ValueError("Event identity or timing disagrees with preparation manifest.")
    return {"preparation": prep, "binary": binary, "channels": mapped, "events": events,
            "model": model, "pitch_um": pitch, "contact_radius_um": radius,
            "sorting_pitch_um": sorting_pitch, "sorting_contact_radius_um": sorting_radius,
            "geometry_status": geometry_status, "source_review_warning": source_review_warning,
            "geometry_evidence": geometry_evidence, "msrd_evidence": msrd_evidence}


def make_params(template: dict, inspected: dict, probe_path: Path, session_name: str) -> dict:
    params = copy.deepcopy(template)
    params.pop("axion_manifest_design_note", None)
    prep = inspected["preparation"]
    params["job_dispatch"].update({"input": "spikeinterface", "split_segments": True,
        "split_groups": True, "spikeinterface_info": {
            "reader_type": "binary", "reader_kwargs": {
                "file_paths": [str(inspected["binary"])], "sampling_frequency": prep["sampling_frequency_hz"],
                "dtype": "int32", "num_channels": prep["n_chan_bin"], "time_axis": 0,
                "gain_to_uV": [c["gain_uv_per_count"] for c in inspected["channels"]],
                "offset_to_uV": 0.0, "is_filtered": False},
            "probe_paths": str(probe_path), "session_names": session_name}})
    params["preprocessing"]["custom_preprocessing_pipeline"] = {"astype": {"dtype": "int32"}}
    params["preprocessing"]["motion_correction"].update({"compute": False, "apply": False})
    ks = params["spikesorting"]["kilosort4"]
    ks.update({"skip_motion_correction": True, "min_drift_channels": prep["n_chan_bin"] + 1})
    # Preserve the CytoView neighborhood in units of electrode pitch.
    sorting_pitch = inspected["sorting_pitch_um"]
    neighborhood = sorting_pitch * 350.0 / 300.0
    ks["sorter"].update({"Th_universal": 5, "Th_learned": 8, "do_CAR": False,
        "invert_sign": False, "nblocks": 0, "do_correction": False, "keep_good_only": False,
        "skip_kilosort_preprocessing": False, "nt": 31,
        "dmin": sorting_pitch, "dminx": sorting_pitch,
        "max_channel_distance": neighborhood, "use_binary_file": True})
    params["postprocessing"]["sparsity"]["radius_um"] = neighborhood
    params["postprocessing"]["extensions"]["random_spikes"]["seed"] = 0
    return params


def prepare(input_dir: Path, source_xml: Path | None, project: Path, run_id: str, template_path: Path,
            *, source_msrd: Path | None = None, allow_staged_geometry: bool = False,
            allow_short_recording: bool = False) -> dict:
    input_dir, project = (p.expanduser().resolve() for p in (input_dir, project))
    source_xml = source_xml.expanduser().resolve() if source_xml is not None else None
    source_msrd = source_msrd.expanduser().resolve() if source_msrd is not None else None
    staged_root = project / "data/interim/mcs_sorting_inputs"
    recording_id = input_dir.relative_to(staged_root).as_posix()
    relative_parts = Path(recording_id).parts
    if len(relative_parts) < 3:
        raise ValueError("Expected group/condition/recording hierarchy.")
    inspected = inspect_input(input_dir, source_xml, source_msrd, allow_staged_geometry=allow_staged_geometry)
    prep = inspected["preparation"]
    template = json.loads(template_path.read_text())
    minimum = float(template["preprocessing"]["min_preprocessing_duration"])
    short = prep["sample_count"] / prep["sampling_frequency_hz"] < minimum
    if short and not allow_short_recording:
        raise ValueError(f"Recording is shorter than the established {minimum:g} s preprocessing minimum.")
    if short and prep["sample_count"] < 4 * 31:
        raise ValueError("Recording is too short to form two waveform-padded sorter batches.")
    record_path = Path(*(slug(p) for p in relative_parts)) / slug(run_id)
    prepared_dir = project / "data/interim/aind_mcs_inputs" / record_path
    results_dir = project / "results/aind_mcs" / record_path
    if prepared_dir.exists() or results_dir.exists():
        raise FileExistsError("Run paths already exist; use the saved run config to resume or choose a new run ID.")
    prepared_dir.mkdir(parents=True)
    probe_path = prepared_dir / "probeinterface.json"
    import numpy as np
    from probeinterface import Probe, write_probeinterface
    probe_name = inspected["model"] or "MCS nominal computational grid; physical geometry unverified"
    probe = Probe(ndim=2, si_units="um", name=probe_name, manufacturer="Multi Channel Systems")
    probe.set_contacts(np.array([[c["x_um"], c["y_um"]] for c in inspected["channels"]]),
                       shapes="circle", shape_params={"radius": inspected["sorting_contact_radius_um"]})
    probe.set_device_channel_indices(np.arange(prep["n_chan_bin"]))
    probe.set_contact_ids([c["channel_label"] for c in inspected["channels"]])
    probe.create_auto_shape(probe_type="rect")
    write_probeinterface(probe_path, probe)
    session_name = "mcs_" + slug(input_dir.name)
    params = make_params(template, inspected, probe_path, session_name)
    short_policy = "established_minimum"
    if short:
        params["preprocessing"]["min_preprocessing_duration"] = 0
        sorter_params = params["spikesorting"]["kilosort4"]["sorter"]
        if prep["sample_count"] <= sorter_params["batch_size"]:
            sorter_params["batch_size"] = prep["sample_count"] // 2
        short_policy = "explicit_attempt_below_established_minimum"
    params_path = prepared_dir / "aind_params.json"
    params_path.write_text(json.dumps(params, indent=2) + "\n")
    channels_path = prepared_dir / "channels.csv"
    with channels_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(inspected["channels"][0]))
        writer.writeheader()
        writer.writerows(inspected["channels"])
    shutil.copy2(input_dir / "events.csv", prepared_dir / "events.csv")
    shutil.copy2(input_dir / "channels.csv", prepared_dir / "source_channels.csv")
    shutil.copy2(input_dir / "mcs_preparation_manifest.json", prepared_dir / "source_mcs_preparation_manifest.json")
    if source_xml is not None:
        shutil.copy2(source_xml, prepared_dir / "acquisition_settings.xml")
    msrd_metadata_file = None
    if inspected["msrd_evidence"] is not None:
        msrd_metadata_file = prepared_dir / "acquisition_msrd_header.json"
        msrd_metadata_file.write_text(json.dumps(inspected["msrd_evidence"], indent=2) + "\n")
    completeness = prep.get("recording_completeness", "complete_staged_recording")
    recovery_report = None
    if completeness == "recovered_prefix":
        source_report = Path(prep["recovery_report"])
        recovery_report = prepared_dir / "source_recovery_report.json"
        shutil.copy2(source_report, recovery_report)
    source_warning = "; ".join(dict.fromkeys(value for value in (
        prep.get("source_review_warning"), inspected["source_review_warning"]) if value)) or None
    shutil.copy2(template_path, prepared_dir / "source_axion_th5_params.json")
    manifest = prep | {"analysis_kind": "mcs_aind_single_mea_recording", "recording_id": recording_id,
        "experimental_group": relative_parts[0], "condition_path": "/".join(relative_parts[1:-1]),
        "recording_stem": input_dir.name, "sorting_run_id": run_id, "recording_path": str(record_path),
        "source_input_dir": str(input_dir), "source_xml": str(source_xml) if source_xml else None,
        "source_xml_sha256": hashlib.sha256(source_xml.read_bytes()).hexdigest() if source_xml else None,
        "source_msrd": str(source_msrd) if source_msrd else None,
        "source_msrd_metadata_file": str(msrd_metadata_file) if msrd_metadata_file else None,
        "configured_mea_name": inspected["model"], "pitch_um": inspected["pitch_um"],
        "geometry_status": inspected["geometry_status"], "sorting_pitch_um": inspected["sorting_pitch_um"],
        "sorting_contact_radius_um": inspected["sorting_contact_radius_um"],
        "source_review_warning": source_warning,
        "recording_completeness": completeness,
        "recovery_report": str(recovery_report) if recovery_report else None,
        "source_h5_cleanup_allowed": inspected["geometry_status"] == "source_verified" and completeness != "recovered_prefix",
        "short_recording_policy": short_policy, "established_minimum_duration_s": minimum,
        "effective_kilosort_batch_size": params["spikesorting"]["kilosort4"]["sorter"]["batch_size"],
        "geometry_evidence": inspected["geometry_evidence"],
        "binary_file": str(inspected["binary"]), "channels_csv": str(channels_path),
        "events_csv": str(prepared_dir / "events.csv"), "probeinterface_json": str(probe_path),
        "gain_uv_per_count": [c["gain_uv_per_count"] for c in inspected["channels"]],
        "params_file": str(params_path), "results_dir": str(results_dir),
        "prepared_utc": datetime.now(timezone.utc).isoformat(),
        "decisions": {"source_counts": "unchanged int32", "source_filter_state": "raw acquisition; no claim about analog frontend",
            "outer_preprocessing": "int32 cast only", "kilosort_preprocessing": "enabled; highpass 300 Hz; CAR disabled",
            "waveform_window": "nt=31 retained, 3.1 ms at 10 kHz",
            "spatial_radius": "CytoView 350/300 times sorting_pitch_um; physical interpretation follows geometry_status",
            "spike_cleanup": "established Kilosort 0.25 ms duplicate window and AIND 0.9 redundant-unit threshold",
            "analyzer_waveforms": "from outer-preprocessed calibrated recording, not Kilosort internal templates"}}
    (prepared_dir / "mcs_recording_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    env = {"AIND_INPUT_MODE": "spikeinterface", "AIND_INPUT_DIR": str(prepared_dir),
        "AIND_RECORDING_PATH": str(record_path), "RECORDING_STEM": session_name,
        "AIND_PARAMS_FILE": str(params_path), "AIND_RUNMODE": "full", "AIND_RESUME": "true",
        "AIND_RESULTS_ROOT": str(project / "results/aind_mcs"),
        "AIND_WORK_ROOT": str(project / "scratch/aind_mcs_nextflow"),
        "AIND_NXF_HOME_ROOT": str(project / "scratch/aind_mcs_nextflow_home"),
        "AIND_JOBS_ROOT": str(project / "jobs/aind_mcs"), "AIND_LOG_ROOT": str(project / "logs/aind_mcs"),
        "AIND_SLURM_CONFIG": str(ROOT / "config/aind_mcs_nextflow_slurm.config")}
    env_path = prepared_dir / "run_aind_mcs.env"
    env_path.write_text("\n".join(f"export {key}={shlex.quote(value)}" for key, value in env.items()) + "\n")
    return {"input_dir": str(prepared_dir), "env_file": str(env_path), "params_file": str(params_path),
            "results_dir": str(results_dir), "recording_id": recording_id, "run_id": run_id,
            "geometry_status": inspected["geometry_status"], "sorting_pitch_um": inspected["sorting_pitch_um"],
            "source_review_warning": source_warning,
            "short_recording_policy": short_policy}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--source-xml", type=Path)
    sources.add_argument("--source-msrd", type=Path)
    parser.add_argument("--allow-staged-geometry", action="store_true")
    parser.add_argument("--allow-short-recording", action="store_true")
    parser.add_argument("--project-root", type=Path, default=Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder"))
    parser.add_argument("--run-id", default="th5_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--params-template", type=Path, default=ROOT / "config/aind_axion_cytoview6_params_th5_kilosort_preproc_DRAFT.json")
    args = parser.parse_args()
    print(json.dumps(prepare(args.input_dir, args.source_xml, args.project_root, args.run_id,
                             args.params_template, source_msrd=args.source_msrd,
                             allow_staged_geometry=args.allow_staged_geometry,
                             allow_short_recording=args.allow_short_recording), indent=2))


if __name__ == "__main__":
    main()
