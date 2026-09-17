from __future__ import annotations

import csv
import gc
import importlib.util
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "prepare_mcs_aind_recording", REPO_ROOT / "scripts/prepare_mcs_aind_recording.py"
)
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)

SOURCE_LABELS = (
    "47 48 46 45 38 37 28 36 27 17 26 16 35 25 Ref 14 24 34 13 23 "
    "12 22 33 21 32 31 44 43 41 42 52 51 53 54 61 62 71 63 72 82 "
    "73 83 64 74 84 85 75 65 86 76 87 77 66 78 67 68 55 56 58 57"
).split()


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class McsAindPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.input_dir = (
            self.project / "data/interim/mcs_sorting_inputs"
            / "Actuators & Effectors/Stim 1/353.1/2021-06-22T15-23-26McsRecording"
        )
        self.input_dir.mkdir(parents=True)
        self.source_xml = self.project / (self.input_dir.name + "MEA21000.xml")

    def fixture(self, model: str = "60MEA200/30iR") -> dict:
        labels = list(SOURCE_LABELS)
        if not model.endswith("iR"):
            labels[14] = "15"
        indices = [i for i, label in enumerate(labels) if label != "Ref"]
        count = len(indices)
        samples = 4
        values = np.arange(samples * count, dtype=np.int32).reshape(samples, count)
        values[0, 0], values[-1, -1] = np.iinfo(np.int32).min, np.iinfo(np.int32).max
        binary = self.input_dir / "mcs_signal_channels.int32.bin"
        binary.write_bytes(values.astype("<i4").tobytes())
        event = {
            "event_id": 1, "event_label": "STG 1 Single Pulse Start", "timestamp": 300100,
            "time_from_recording_start_s": 0.0001,
        }
        manifest = {
            "binary_file": "/Volumes/Disconnected/mcs_signal_channels.int32.bin",
            "channels_csv": "/Volumes/Disconnected/channels.csv",
            "events_csv": "/Volumes/Disconnected/events.csv",
            "binary_dtype": "int32", "binary_layout": "sample_major_row_major",
            "n_chan_bin": count, "sample_count": samples, "sampling_frequency_hz": 10000,
            "first_timestamp": 300000, "timestamp_tick_seconds": 1e-6,
            "channel_count_in_file": 60, "signal_channel_count": count,
            "channel_labels": labels, "conversion_to_volts": [(i + 1) * 1e-8 for i in range(60)],
            "events": [event],
        }
        self.manifest_path = self.input_dir / "mcs_preparation_manifest.json"
        self.manifest_path.write_text(json.dumps(manifest))
        # Both archive cohorts were staged at 200 um; source XML must determine the derived pitch.
        write_csv(self.input_dir / "channels.csv", [
            {"stream_channel_index": i, "channel_label": labels[i],
             "x_um": int(labels[i][1]) * 200, "y_um": int(labels[i][0]) * 200}
            for i in indices
        ], ["stream_channel_index", "channel_label", "x_um", "y_um"])
        write_csv(self.input_dir / "events.csv", [event], list(event))
        xml = ET.Element("Instrument")
        settings = ET.SubElement(ET.SubElement(xml, "Settings"), "DataAcquisitionSettings")
        selected = ET.SubElement(settings, "SelectedMeaID")
        ET.SubElement(selected, "MeaName").text = model
        ET.SubElement(xml, "SampleRateElectrodes").text = "10000"
        states = ET.SubElement(ET.SubElement(settings, "MultiwellLayoutSettings"), "MeaButtonStates")
        for index, label in enumerate(labels):
            state = ET.SubElement(states, "ChannelState")
            ET.SubElement(state, "HardwareID").text = str(index)
            info = ET.SubElement(state, "MeaButtonStateInfo")
            ET.SubElement(info, "ChannelName").text = label
        ET.ElementTree(xml).write(self.source_xml, encoding="utf-8")
        return manifest

    def inspect(self) -> dict:
        return adapter.inspect_input(self.input_dir, self.source_xml)

    def test_relocated_input_uses_local_assets_and_original_channel_gains(self) -> None:
        manifest = self.fixture()
        inspected = self.inspect()
        self.assertEqual(inspected["binary"], self.input_dir / "mcs_signal_channels.int32.bin")
        self.assertEqual(len(inspected["channels"]), 59)
        self.assertNotIn(14, [row["stream_channel_index"] for row in inspected["channels"]])
        for binary_index, row in enumerate(inspected["channels"]):
            source_index = row["stream_channel_index"]
            self.assertEqual(row["binary_channel_index"], binary_index)
            self.assertEqual(row["channel_label"], manifest["channel_labels"][source_index])
            self.assertAlmostEqual(row["gain_uv_per_count"], (source_index + 1) * 0.01)

    def test_binary_requires_exact_declared_sample_count(self) -> None:
        self.fixture()
        binary = self.input_dir / "mcs_signal_channels.int32.bin"
        original = binary.read_bytes()
        for size in (len(original) - 4, len(original) - 59 * 4, len(original) + 4):
            with self.subTest(size=size):
                binary.write_bytes((original + b"\x00" * 4)[:size])
                with self.assertRaisesRegex(ValueError, "Binary size"):
                    self.inspect()

    def test_source_pitch_overrides_staged_coordinates_for_both_models(self) -> None:
        for model, pitch, count in (("60MEA200/30iR", 200, 59), ("60MEA100/10", 100, 60)):
            with self.subTest(model=model):
                self.fixture(model)
                inspected = self.inspect()
                self.assertEqual(inspected["pitch_um"], pitch)
                self.assertEqual(len(inspected["channels"]), count)
                first = inspected["channels"][0]
                self.assertEqual((first["x_um"], first["y_um"]), (7 * pitch, 4 * pitch))
                self.assertEqual(inspected["contact_radius_um"], 15 if count == 59 else 5)

    def test_missing_xml_requires_verified_original_msrd(self) -> None:
        prep = self.fixture("60MEA100/10")
        with self.assertRaisesRegex(ValueError, "original acquisition"):
            adapter.inspect_input(self.input_dir, None)
        msrd = self.project / (self.input_dir.name + ".msrd")
        evidence = {"configured_mea_name": "60MEA100/10", "sampling_frequency_hz": 10000,
                    "hardware_labels": dict(enumerate(prep["channel_labels"]))}
        with patch.object(adapter, "inspect_original_msrd", return_value=evidence) as inspect_source:
            inspected = adapter.inspect_input(self.input_dir, None, msrd)
        inspect_source.assert_called_once_with(msrd, prep, self.input_dir)
        self.assertEqual(inspected["pitch_um"], 100)
        self.assertIs(inspected["msrd_evidence"], evidence)
        self.assertIn("original MSRD", inspected["geometry_evidence"])
        with patch.object(adapter, "inspect_original_msrd", side_effect=ValueError("truncated source")):
            with self.assertRaisesRegex(ValueError, "truncated"):
                adapter.inspect_input(self.input_dir, None, msrd)

    def test_staged_geometry_requires_opt_in_and_does_not_invent_physical_pitch(self) -> None:
        self.fixture("60MEA100/10")
        inspected = adapter.inspect_input(self.input_dir, None, allow_staged_geometry=True)
        self.assertEqual(inspected["geometry_status"], "staged_unverified")
        self.assertIsNone(inspected["model"])
        self.assertIsNone(inspected["pitch_um"])
        self.assertIsNone(inspected["contact_radius_um"])
        self.assertEqual(inspected["sorting_pitch_um"], 200)
        self.assertEqual(len(inspected["channels"]), 60)
        self.assertIn("physical", inspected["source_review_warning"])
        channels_path = self.input_dir / "channels.csv"
        channels = adapter.read_csv(channels_path)
        channels[0]["x_um"] = "1401"
        write_csv(channels_path, channels, list(channels[0]))
        with self.assertRaisesRegex(ValueError, "consistent nominal"):
            adapter.inspect_input(self.input_dir, None, allow_staged_geometry=True)

    def test_staged_fallback_keeps_invalid_original_warning(self) -> None:
        self.fixture()
        msrd = self.project / (self.input_dir.name + ".msrd")
        with patch.object(adapter, "inspect_original_msrd", side_effect=ValueError("truncated source")):
            inspected = adapter.inspect_input(self.input_dir, None, msrd, allow_staged_geometry=True)
        self.assertEqual(inspected["geometry_status"], "staged_unverified")
        self.assertIn("truncated source", inspected["source_review_warning"])

    def test_short_override_changes_only_duration_and_necessary_batch_size(self) -> None:
        template_path = REPO_ROOT / "config/aind_axion_cytoview6_params_th5_kilosort_preproc_DRAFT.json"
        for samples, expected_batch in ((13000, 6500), (19000, 15000), (217000, 15000)):
            prep = self.fixture()
            prep["sample_count"] = samples
            self.manifest_path.write_text(json.dumps(prep))
            binary = self.input_dir / "mcs_signal_channels.int32.bin"
            with binary.open("wb") as handle:
                handle.truncate(samples * prep["n_chan_bin"] * 4)
            with self.assertRaisesRegex(ValueError, "established"):
                adapter.prepare(self.input_dir, self.source_xml, self.project, f"strict-{samples}", template_path)
            result = adapter.prepare(self.input_dir, None, self.project, f"short-{samples}", template_path,
                                     allow_staged_geometry=True, allow_short_recording=True)
            params = json.loads(Path(result["params_file"]).read_text())
            manifest = json.loads((Path(result["input_dir"]) / "mcs_recording_manifest.json").read_text())
            sorter = params["spikesorting"]["kilosort4"]["sorter"]
            self.assertEqual(sorter["batch_size"], expected_batch)
            self.assertEqual((sorter["Th_universal"], sorter["Th_learned"], sorter["nt"], sorter["n_templates"]), (5, 8, 31, 6))
            self.assertEqual(params["preprocessing"]["min_preprocessing_duration"], 0)
            self.assertFalse(manifest["source_h5_cleanup_allowed"])
            self.assertIsNone(manifest["pitch_um"])
            self.assertEqual(manifest["sorting_pitch_um"], 200)
            self.assertEqual(result["short_recording_policy"], "explicit_attempt_below_established_minimum")

    def test_partial_recovery_report_and_warning_are_retained(self) -> None:
        prep = self.fixture()
        source_report = self.project / "recovery.json"
        source_report.write_text(json.dumps({"recording_completeness": "recovered_prefix", "source_retained": True}))
        prep.update(recording_completeness="recovered_prefix", recovery_report=str(source_report),
                    source_review_warning="Recovered prefix only; incomplete tail omitted")
        self.manifest_path.write_text(json.dumps(prep))
        template = json.loads((REPO_ROOT / "config/aind_axion_cytoview6_params_th5_kilosort_preproc_DRAFT.json").read_text())
        template["preprocessing"]["min_preprocessing_duration"] = 0
        template_path = self.project / "partial-template.json"
        template_path.write_text(json.dumps(template))
        result = adapter.prepare(self.input_dir, self.source_xml, self.project, "partial", template_path)
        manifest = json.loads((Path(result["input_dir"]) / "mcs_recording_manifest.json").read_text())
        self.assertEqual(manifest["recording_completeness"], "recovered_prefix")
        self.assertEqual(Path(manifest["recovery_report"]).name, "source_recovery_report.json")
        self.assertEqual(Path(manifest["recovery_report"]).read_bytes(), source_report.read_bytes())
        self.assertEqual(manifest["source_review_warning"], prep["source_review_warning"])
        self.assertFalse(manifest["source_h5_cleanup_allowed"])

    def test_xml_recording_and_sampling_rate_must_match(self) -> None:
        self.fixture()
        wrong = self.project / "anotherRecordingMEA21000.xml"
        wrong.write_bytes(self.source_xml.read_bytes())
        with self.assertRaisesRegex(ValueError, "filename"):
            adapter.inspect_input(self.input_dir, wrong)
        xml = ET.parse(self.source_xml)
        xml.getroot().find("SampleRateElectrodes").text = "12500"
        xml.write(self.source_xml)
        with self.assertRaisesRegex(ValueError, "sample rates"):
            self.inspect()

    def test_xml_channel_identity_must_match_even_when_label_set_matches(self) -> None:
        self.fixture()
        xml = ET.parse(self.source_xml)
        labels = xml.getroot().findall(".//MeaButtonStateInfo/ChannelName")
        labels[0].text, labels[1].text = labels[1].text, labels[0].text
        xml.write(self.source_xml)
        with self.assertRaises(ValueError):
            self.inspect()

    def test_channel_table_reordering_and_reference_mismatch_rejected(self) -> None:
        self.fixture()
        rows = adapter.read_csv(self.input_dir / "channels.csv")
        rows[0], rows[1] = rows[1], rows[0]
        write_csv(self.input_dir / "channels.csv", rows, list(rows[0]))
        with self.assertRaisesRegex(ValueError, "channel order"):
            self.inspect()
        self.fixture()
        xml = ET.parse(self.source_xml)
        xml.getroot().find(".//MeaName").text = "60MEA200/30"
        xml.write(self.source_xml)
        with self.assertRaisesRegex(ValueError, "reference"):
            self.inspect()

    def test_prepare_preserves_int32_th5_settings_and_all_sources(self) -> None:
        self.fixture()
        template = json.loads((REPO_ROOT / "config/aind_axion_cytoview6_params_th5_kilosort_preproc_DRAFT.json").read_text())
        template["preprocessing"]["min_preprocessing_duration"] = 0
        template_path = self.project / "template.json"
        template_path.write_text(json.dumps(template))
        source_paths = [*self.input_dir.iterdir(), self.source_xml, template_path]
        before = {path: path.read_bytes() for path in source_paths}
        result = adapter.prepare(self.input_dir, self.source_xml, self.project, "test-th5", template_path)
        params = json.loads(Path(result["params_file"]).read_text())
        reader = params["job_dispatch"]["spikeinterface_info"]["reader_kwargs"]
        self.assertEqual(reader["dtype"], "int32")
        self.assertEqual(reader["file_paths"], [str(self.input_dir / "mcs_signal_channels.int32.bin")])
        self.assertEqual(params["preprocessing"]["custom_preprocessing_pipeline"], {"astype": {"dtype": "int32"}})
        sorter = params["spikesorting"]["kilosort4"]["sorter"]
        self.assertEqual((sorter["Th_universal"], sorter["Th_learned"]), (5, 8))
        self.assertFalse(sorter["do_CAR"])
        self.assertFalse(sorter["skip_kilosort_preprocessing"])
        self.assertEqual(sorter["nblocks"], 0)
        self.assertTrue(sorter["use_binary_file"])
        self.assertFalse(sorter["keep_good_only"])
        self.assertEqual(params["postprocessing"]["duplicate_threshold"], 0.9)
        self.assertTrue(params["postprocessing"]["return_in_uV"])

        import spikeinterface as si
        from probeinterface import read_probeinterface

        recording = si.read_binary(**reader)
        traces = recording.get_traces()
        self.assertEqual(traces.dtype, np.dtype("int32"))
        self.assertEqual(int(traces[0, 0]), np.iinfo(np.int32).min)
        self.assertEqual(int(traces[-1, -1]), np.iinfo(np.int32).max)
        np.testing.assert_allclose(recording.get_channel_gains(), reader["gain_to_uV"])
        probe_path = params["job_dispatch"]["spikeinterface_info"]["probe_paths"]
        probe = read_probeinterface(probe_path).probes[0]
        np.testing.assert_array_equal(probe.device_channel_indices, np.arange(59))
        self.assertEqual(list(probe.contact_ids), [label for label in SOURCE_LABELS if label != "Ref"])
        self.assertIn("results/aind_mcs/Actuators_Effectors/Stim_1/353.1/", result["results_dir"])
        self.assertEqual(before, {path: path.read_bytes() for path in source_paths})
        with self.assertRaises(FileExistsError):
            adapter.prepare(self.input_dir, self.source_xml, self.project, "test-th5", template_path)
        del traces, recording
        gc.collect()


if __name__ == "__main__":
    unittest.main()
