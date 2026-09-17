from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import spikeinterface as si

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from validate_mcs_aind_output import REQUIRED_SORTER_SETTINGS, compare_sortings, inspect_sorting, scratch_references, validate, verify_input


def make_sorting(trains, sampling_frequency=10000):
    sorting = si.NumpySorting.from_unit_dict(trains, sampling_frequency=sampling_frequency)
    sorting.set_property("original_cluster_id", np.asarray(sorting.unit_ids) + 100)
    sorting.set_property("KSLabel", ["good"] * len(sorting.unit_ids))
    return sorting


def make_input_fixture(root, channel_count=59, pitch=200, fs=10000):
    inputs = root / "inputs"
    inputs.mkdir()
    binary_path = inputs / "mcs_signal_channels.int32.bin"
    np.random.default_rng(0).integers(-1000, 1000, (1000, channel_count), dtype=np.int32).tofile(binary_path)
    labels = [f"{row}{column}" for row in range(1, 9) for column in range(1, 9)
              if (row, column) not in {(1, 1), (1, 8), (8, 1), (8, 8)}]
    gains = [5.9605e-8] * 60 if channel_count == 59 else np.linspace(4e-8, 8e-8, 60).tolist()
    if channel_count == 59:
        labels[14] = "Ref"
        gains[14] = 9.9e-8
    indices = [index for index, label in enumerate(labels) if label != "Ref"]
    positions = np.asarray([[int(labels[index][1]) * pitch, int(labels[index][0]) * pitch] for index in indices])
    events = [{"event_id": 1, "event_label": "pulse", "timestamp": 23000, "time_from_recording_start_s": 0.02}]
    manifest = {
        "sample_count": 1000, "n_chan_bin": channel_count, "sampling_frequency_hz": fs,
        "binary_dtype": "int32", "binary_layout": "sample_major_row_major", "conversion_to_volts": gains,
        "binary_file": str(binary_path), "channels_csv": str(inputs / "channels.csv"),
        "channel_count_in_file": 60, "channel_labels": labels,
        "configured_mea_name": f"60MEA{pitch}/30" + ("iR" if channel_count == 59 else ""),
        "pitch_um": pitch, "first_timestamp": 3000, "timestamp_tick_seconds": 1e-6, "events": events,
    }
    for name in ("mcs_recording_manifest.json", "source_mcs_preparation_manifest.json"):
        (inputs / name).write_text(json.dumps(manifest))
    with (inputs / "events.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(events[0]))
        writer.writeheader()
        writer.writerows(events)
    with (inputs / "channels.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["binary_channel_index", "stream_channel_index", "channel_label", "x_um", "y_um", "gain_uv_per_count"])
        for index, (stream_index, position) in enumerate(zip(indices, positions)):
            writer.writerow([index, stream_index, labels[stream_index], *position, gains[stream_index] * 1e6])
    reader = {"file_paths": [str(binary_path)], "sampling_frequency": fs, "dtype": "int32", "num_channels": channel_count,
              "gain_to_uV": [gains[index] * 1e6 for index in indices], "offset_to_uV": 0}
    return inputs, manifest, reader, positions


class McsAindValidationTests(unittest.TestCase):
    def test_scratch_references_are_detected_recursively(self):
        self.assertEqual(scratch_references({"recording": {"kwargs": {
            "file_paths": ["/project/scratch/job/traces.raw", "/project/data/traces.raw"],
            "folder_path": "/project/scratchpad/stable"}}}), ["/project/scratch/job/traces.raw"])

    def test_bounds_use_exclusive_sample_count(self):
        sorting = make_sorting({11: np.asarray([-1, 0, 99, 100])})
        report = inspect_sorting(sorting, 100, 10000)
        self.assertEqual(report["out_of_bounds_spike_count"], 2)
        self.assertEqual(report["spike_count"], 4)
        self.assertEqual(report["kilosort_label_counts"], {"good": 1})

    def test_deduplication_preserves_remaining_spikes_and_original_ids(self):
        original = make_sorting({11: np.asarray([10, 20]), 23: np.asarray([30, 40])})
        retained = original.select_units([23])
        self.assertEqual(compare_sortings(original, retained, require_same_units=False), [])
        self.assertTrue(compare_sortings(original, retained, require_same_units=True))
        changed = make_sorting({23: np.asarray([30, 41])})
        self.assertIn("Spike train changed for unit 23", compare_sortings(original, changed, require_same_units=False))
        changed = make_sorting({23: np.asarray([30, 40])})
        changed.set_property("original_cluster_id", [999])
        self.assertIn("original_cluster_id changed for unit 23", compare_sortings(original, changed, require_same_units=False))

    def test_missing_labels_and_duplicate_original_ids_fail(self):
        sorting = make_sorting({11: np.asarray([10]), 23: np.asarray([30])})
        sorting.delete_property("KSLabel")
        sorting.set_property("original_cluster_id", [1, 1])
        errors = inspect_sorting(sorting, 100, 10000)["errors"]
        self.assertIn("Missing unit property: KSLabel", errors)
        self.assertIn("original_cluster_id does not uniquely identify units", errors)

    def test_durable_fixture_validates_and_detects_runtime_parameter_drift(self):
        self.check_durable_fixture(59, 200, 10000)

    def test_60_channel_100um_fixture_with_distinct_gains_and_rate(self):
        self.check_durable_fixture(60, 100, 20000)

    def test_unverified_59_and_60_channel_grids_do_not_claim_physical_pitch(self):
        for channel_count, pitch in ((59, 200), (60, 200), (60, 100)):
            with self.subTest(channel_count=channel_count, pitch=pitch):
                self.check_durable_fixture(channel_count, pitch, 10000, unverified=True)

    def check_durable_fixture(self, channel_count, pitch, fs, unverified=False):
        # Use local storage so open NumPy memmaps do not leave NFS deletion markers.
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            root = Path(tmp)
            inputs, manifest, reader, positions = make_input_fixture(root, channel_count, pitch, fs)
            if unverified:
                manifest.update(geometry_status="staged_unverified", configured_mea_name=None, pitch_um=None,
                                sorting_pitch_um=pitch, source_xml=None, source_msrd=None)
                (inputs / "mcs_recording_manifest.json").write_text(json.dumps(manifest))
            results = root / "results"
            results.mkdir()
            params = {
                "job_dispatch": {"spikeinterface_info": {"reader_kwargs": reader}},
                "spikesorting": {"kilosort4": {"sorter": REQUIRED_SORTER_SETTINGS}},
                "postprocessing": {"extensions": {"random_spikes": {}, "templates": {}, "correlograms": {}, "unit_locations": {}}},
            }
            params_path = inputs / "aind_params.json"
            params_path.write_text(json.dumps(params))
            processing = {"data_processes": [{"process_type": "Spike sorting", "code": {
                "parameters": {"sorter_params": dict(REQUIRED_SORTER_SETTINGS)}}}]}
            processing_path = results / "processing.json"
            processing_path.write_text(json.dumps(processing))
            recording = si.read_binary(**reader)
            recording.set_dummy_probe_from_locations(positions)
            original = make_sorting({11: np.asarray([100, 200, 300]), 23: np.asarray([400, 500, 600])}, fs)
            original.save(folder=results / "spikesorted" / "recording1")
            retained = original.select_units([23])
            retained.save(folder=results / "curated" / "recording1")
            analyzer = si.create_sorting_analyzer(retained, recording, sparse=False)
            analyzer.compute("random_spikes", max_spikes_per_unit=3, seed=0)
            analyzer.compute("templates", ms_before=1, ms_after=2, n_jobs=1, progress_bar=False)
            analyzer.compute("correlograms", method="numpy")
            analyzer.save_as(format="zarr", folder=results / "postprocessed" / "recording1.zarr")
            report, rows = validate(results, inputs, params_path)
            self.assertEqual(report["status"], "passed", report["errors"])
            self.assertEqual(len(report["input"]["gain_uv_per_count"]), channel_count)
            np.testing.assert_allclose(report["input"]["gain_uv_per_count"], reader["gain_to_uV"])
            self.assertEqual(report["input"]["events"]["event_count"], 1)
            self.assertEqual(report["input"]["physical_geometry_verified"], not unverified)
            if unverified:
                self.assertIsNone(report["input"]["pitch_um"])
                self.assertTrue(any("Physical MEA geometry is unknown" in warning for warning in report["warnings"]))
            self.assertEqual(report["cleanup"]["removed_unit_ids"], [11])
            self.assertEqual(report["stages"]["curated"]["spike_count"], 3)
            self.assertEqual(len(rows), 2)
            self.assertTrue(report["warnings"])
            processing["data_processes"][0]["code"]["parameters"]["sorter_params"]["Th_universal"] = 9
            processing_path.write_text(json.dumps(processing))
            report, _ = validate(results, inputs, params_path)
            self.assertEqual(report["status"], "failed")
            self.assertIn("Th_universal", report["parameters"]["mismatches"])

    def test_input_mapping_calibration_and_events_cannot_drift(self):
        for corruption in ("channel_order", "reference", "position", "gain", "event_identity", "event_time", "source_metadata"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory(dir="/tmp") as tmp:
                inputs, manifest, reader, _ = make_input_fixture(Path(tmp))
                if corruption in ("channel_order", "reference", "position", "gain"):
                    with (inputs / "channels.csv").open(newline="") as handle:
                        rows = list(csv.DictReader(handle))
                    if corruption == "channel_order":
                        rows[0], rows[1] = rows[1], rows[0]
                    elif corruption == "reference":
                        rows[0]["channel_label"] = "Ref"
                    elif corruption == "position":
                        rows[0]["x_um"] = float(rows[0]["x_um"]) + 100
                    else:
                        rows[0]["gain_uv_per_count"] = 0.07
                    with (inputs / "channels.csv").open("w", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                        writer.writeheader()
                        writer.writerows(rows)
                elif corruption == "source_metadata":
                    manifest["sampling_frequency_hz"] = 20000
                    reader["sampling_frequency"] = 20000
                    (inputs / "mcs_recording_manifest.json").write_text(json.dumps(manifest))
                else:
                    rows = manifest["events"]
                    rows[0]["event_id" if corruption == "event_identity" else "time_from_recording_start_s"] = 2 if corruption == "event_identity" else 0.04
                    with (inputs / "events.csv").open("w", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                        writer.writeheader()
                        writer.writerows(rows)
                with self.assertRaises(ValueError):
                    verify_input(inputs, {"job_dispatch": {"spikeinterface_info": {"reader_kwargs": reader}}}, {})

    def test_recording_without_hardware_events_is_valid(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            inputs, manifest, reader, _ = make_input_fixture(Path(tmp), channel_count=60, pitch=100)
            manifest["events"] = []
            for name in ("mcs_recording_manifest.json", "source_mcs_preparation_manifest.json"):
                (inputs / name).write_text(json.dumps(manifest))
            with (inputs / "events.csv").open("w", newline="") as handle:
                csv.writer(handle).writerow(["event_id", "event_label", "timestamp", "time_from_recording_start_s"])
            report = {}
            verify_input(inputs, {"job_dispatch": {"spikeinterface_info": {"reader_kwargs": reader}}}, report)
            self.assertEqual(report["input"]["events"]["event_count"], 0)

    def test_unverified_geometry_rejects_physical_claims_and_nominal_grid_drift(self):
        for corruption in ("physical_pitch", "model", "sorting_pitch", "position", "gain", "reference"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory(dir="/tmp") as tmp:
                inputs, manifest, reader, _ = make_input_fixture(Path(tmp))
                manifest.update(geometry_status="staged_unverified", configured_mea_name=None, pitch_um=None, sorting_pitch_um=200)
                if corruption == "physical_pitch":
                    manifest["pitch_um"] = 200
                elif corruption == "model":
                    manifest["configured_mea_name"] = "60MEA200/30iR"
                elif corruption == "sorting_pitch":
                    manifest["sorting_pitch_um"] = 100
                else:
                    with (inputs / "channels.csv").open(newline="") as handle:
                        rows = list(csv.DictReader(handle))
                    name, value = {"position": ("x_um", 999), "gain": ("gain_uv_per_count", 1),
                                   "reference": ("channel_label", "Ref")}[corruption]
                    rows[0][name] = value
                    with (inputs / "channels.csv").open("w", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                        writer.writeheader()
                        writer.writerows(rows)
                (inputs / "mcs_recording_manifest.json").write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    verify_input(inputs, {"job_dispatch": {"spikeinterface_info": {"reader_kwargs": reader}}}, {})


if __name__ == "__main__":
    unittest.main()
