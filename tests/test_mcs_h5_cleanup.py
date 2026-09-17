from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cleanup_mcs_h5", ROOT / "scripts/cleanup_mcs_h5.py")
cleanup_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup_tool)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class McsH5CleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.allowed = self.root / "raw_data"
        self.source_dir = self.allowed / "collection/group/condition"
        self.source_dir.mkdir(parents=True)
        self.stem = "2021-06-22T15-23-26McsRecording"
        self.h5 = self.source_dir / (self.stem + ".h5")
        self.xml = self.source_dir / (self.stem + "MEA21000.xml")
        self.xml.write_text("<Instrument><MeaName>60MEA200/30iR</MeaName></Instrument>")
        self.msrd = self.source_dir / (self.stem + ".msrd")
        self.msrd.write_bytes(b"original msrd must remain")
        self.other_h5 = self.source_dir / "unrelated.h5"
        self.other_h5.write_bytes(b"unrelated H5 must remain")
        self.input_dir = self.root / "prepared"
        self.results = self.root / "results"
        self.staged = self.root / "staged"
        self.staged.mkdir()
        self.binary = self.staged / "mcs_signal_channels.int32.bin"
        self.traces = np.arange(24, dtype="<i4").reshape(3, 8)
        self.traces[0, 0], self.traces[2, -1] = np.iinfo(np.int32).min, np.iinfo(np.int32).max
        self.binary.write_bytes(np.ascontiguousarray(self.traces[[0, 2]].T).tobytes())
        self.event = {"event_id": 1, "event_label": "STG 1 Single Pulse Start", "timestamp": 1100,
                      "time_from_recording_start_s": 0.0001}
        with h5py.File(self.h5, "w") as handle:
            stream = handle.create_group(cleanup_tool.ANALOG_PATH)
            stream.create_dataset("ChannelData", data=self.traces)
            stream.create_dataset("ChannelDataTimeStamps", data=[[1000, 0, 7]])
            dtype = np.dtype([("ChannelID", "<i4"), ("Label", h5py.string_dtype()), ("Tick", "<i8"),
                              ("Exponent", "<i4"), ("ConversionFactor", "<i8"), ("ADZero", "<i4")])
            stream.create_dataset("InfoChannel", data=np.asarray([(0, "12", 100, -12, 59605, 0),
                (1, "Ref", 100, -12, 59605, 0), (2, "87", 100, -12, 59605, 0)], dtype=dtype))
            events = handle.create_group("Data/Recording_0/EventStream/Stream_0")
            event_dtype = np.dtype([("EventID", "<i4"), ("Label", h5py.string_dtype())])
            events.create_dataset("InfoEvent", data=np.asarray([(1, self.event["event_label"])], dtype=event_dtype))
            events.create_dataset("EventEntity_1", data=[[1100], [0]])
        self.manifest = {
            "analysis_kind": "mcs_aind_single_mea_recording", "recording_id": "group/condition/" + self.stem,
            "recording_stem": self.stem, "sorting_run_id": "test-th5", "results_dir": str(self.results),
            "source_xml": str(self.xml), "source_xml_sha256": cleanup_tool.sha256(self.xml),
            "binary_file": str(self.binary), "source_input_dir": str(self.staged), "sample_count": 8,
            "n_chan_bin": 2, "sampling_frequency_hz": 10000, "first_timestamp": 1000,
            "channel_labels": ["12", "Ref", "87"], "conversion_to_volts": [59605e-12] * 3,
            "events": [self.event],
        }
        for path in (self.input_dir / "mcs_recording_manifest.json", self.results / "mcs_recording_manifest.json",
                     self.results / "repro/mcs_input/mcs_recording_manifest.json"):
            write_json(path, self.manifest)
        (self.results / "repro/data_path.txt").write_text(str(self.input_dir))
        (self.results / "repro/results_path.txt").write_text(str(self.results))
        self.trace = self.results / "nextflow/trace.txt"
        self.trace.parent.mkdir()
        with self.trace.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, ["name", "status", "exit"], delimiter="\t")
            writer.writeheader()
            writer.writerows({"name": name + " (task)", "status": "COMPLETED", "exit": "0"}
                             for name in sorted(cleanup_tool.REQUIRED_STAGES))
        self.analyzer = self.results / "postprocessed/recording.zarr"
        self.durable = self.results / "preprocessed/recording"
        self.durable.mkdir(parents=True)
        self.durable_binary = self.durable / "traces_cached_seg0.raw"
        self.durable_binary.write_bytes(self.binary.read_bytes())
        self.validation = {
            "status": "passed", "errors": [], "results_dir": str(self.results),
            "input": {"recording_id": self.manifest["recording_id"],
                      "manifest": str(self.input_dir / "mcs_recording_manifest.json"), "binary": str(self.binary)},
            "analyzer": {"path": str(self.analyzer)},
        }
        write_json(self.results / "validation_summary.json", self.validation)
        write_json(self.results / "durable_recording_report.json", {
            "status": "validated", "analyzer": str(self.analyzer), "durable_recording_folder": str(self.durable),
            "original_staged_binary": str(self.binary), "original_staged_binary_sha256": cleanup_tool.sha256(self.binary),
            "file_sha256": {self.durable_binary.name: cleanup_tool.sha256(self.durable_binary)},
        })
        self.nwb = {"status": "corrected", "pynwb_reread_and_schema_validation": "passed",
                    "input_dir": str(self.input_dir), "nwb_path": str(self.results / "nwb/recording.nwb")}
        write_json(self.results / "repro/nwb_finalization_report.json", self.nwb)
        self.fresh = patch.object(cleanup_tool, "fresh_output_validation", return_value={
            "validation": self.validation, "nwb": {**self.nwb, "status": "already_corrected"},
            "recording_folder": str(self.durable), "recording_binary": str(self.durable_binary),
        }).start()
        self.addCleanup(patch.stopall)

    def cleanup(self, *, apply: bool = False, candidate: Path | None = None) -> dict:
        return cleanup_tool.cleanup(self.results, self.input_dir, candidate or self.h5, self.allowed, apply=apply)

    def test_dry_run_then_delete_is_idempotent_and_preserves_other_inputs(self) -> None:
        binary_hash = cleanup_tool.sha256(self.binary)
        result = self.cleanup()
        self.assertEqual(result["status"], "eligible_dry_run")
        self.assertEqual(result["deleted_bytes"], 0)
        self.assertTrue(self.h5.exists())
        self.assertFalse(Path(result["ledger"]).exists())
        result = self.cleanup(apply=True)
        self.assertEqual(result["status"], "deleted")
        self.assertGreater(result["deleted_bytes"], 0)
        ledger = Path(result["ledger"])
        self.assertFalse(self.h5.exists())
        self.assertTrue((ledger / "prepared.json").is_file())
        self.assertTrue((ledger / "deleted.json").is_file())
        self.assertTrue((ledger / "h5_metadata.json").is_file())
        self.assertEqual((ledger / self.xml.name).read_bytes(), self.xml.read_bytes())
        self.assertEqual(self.msrd.read_bytes(), b"original msrd must remain")
        self.assertEqual(self.other_h5.read_bytes(), b"unrelated H5 must remain")
        self.assertEqual(cleanup_tool.sha256(self.binary), binary_hash)
        self.assertEqual(cleanup_tool.sha256(self.durable_binary), binary_hash)
        before = (ledger / "deleted.json").read_bytes()
        again = self.cleanup(apply=True)
        self.assertEqual(again["status"], "already_deleted")
        self.assertEqual(again["deleted_bytes"], 0)
        self.assertEqual((ledger / "deleted.json").read_bytes(), before)

    def test_failed_saved_or_fresh_validation_refuses_cleanup(self) -> None:
        path = self.results / "validation_summary.json"
        write_json(path, {**self.validation, "status": "failed"})
        with self.assertRaisesRegex(ValueError, "validation did not pass"):
            self.cleanup(apply=True)
        write_json(path, self.validation)
        self.fresh.side_effect = ValueError("fresh check failed")
        with self.assertRaisesRegex(ValueError, "fresh check failed"):
            self.cleanup(apply=True)
        self.assertTrue(self.h5.is_file())

    def test_foreign_report_and_failed_pipeline_refuse_cleanup(self) -> None:
        path = self.results / "validation_summary.json"
        write_json(path, {**self.validation, "results_dir": str(self.root / "other_run")})
        with self.assertRaisesRegex(ValueError, "another results"):
            self.cleanup(apply=True)
        write_json(path, self.validation)
        self.trace.write_text(self.trace.read_text().replace("COMPLETED\t0", "FAILED\t1", 1))
        with self.assertRaisesRegex(ValueError, "failed or is incomplete"):
            self.cleanup(apply=True)
        self.assertTrue(self.h5.is_file())

    def test_foreign_path_wrong_extension_and_symlink_refused(self) -> None:
        foreign = self.root / (self.stem + ".h5")
        foreign.write_bytes(self.h5.read_bytes())
        for candidate in (foreign, self.msrd, self.other_h5):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                self.cleanup(candidate=candidate, apply=True)
        backup = self.h5.with_suffix(".backed_up_h5")
        self.h5.rename(backup)
        self.h5.symlink_to(backup)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            self.cleanup(apply=True)
        self.assertTrue(backup.is_file())

    def test_mismatched_h5_trace_refused(self) -> None:
        with h5py.File(self.h5, "r+") as handle:
            handle[cleanup_tool.ANALOG_PATH + "/ChannelData"][0, 4] += 1
        with self.assertRaisesRegex(ValueError, "signal counts differ"):
            self.cleanup(apply=True)
        self.assertTrue(self.h5.is_file())

    def test_adc_zero_and_timestamp_mismatch_refused(self) -> None:
        with h5py.File(self.h5, "r+") as handle:
            info = handle[cleanup_tool.ANALOG_PATH + "/InfoChannel"][:]
            info[0]["ADZero"] = 1
            handle[cleanup_tool.ANALOG_PATH + "/InfoChannel"][:] = info
        with self.assertRaisesRegex(ValueError, "ADC zero"):
            self.cleanup(apply=True)
        with h5py.File(self.h5, "r+") as handle:
            info[0]["ADZero"] = 0
            handle[cleanup_tool.ANALOG_PATH + "/InfoChannel"][:] = info
            handle[cleanup_tool.ANALOG_PATH + "/ChannelDataTimeStamps"][:] = [[1000, 1, 7]]
        with self.assertRaisesRegex(ValueError, "timing intervals"):
            self.cleanup(apply=True)
        self.assertTrue(self.h5.is_file())

    def test_durable_recording_changed_refuses_cleanup(self) -> None:
        self.durable_binary.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Retained recording changed"):
            self.cleanup(apply=True)
        self.assertTrue(self.h5.is_file())

    def test_channel_gain_and_event_identity_mismatch_refused(self) -> None:
        with h5py.File(self.h5, "r+") as handle:
            info = handle[cleanup_tool.ANALOG_PATH + "/InfoChannel"][:]
            info[0]["ConversionFactor"] += 1
            handle[cleanup_tool.ANALOG_PATH + "/InfoChannel"][:] = info
        with self.assertRaisesRegex(ValueError, "gains differ"):
            self.cleanup(apply=True)
        with h5py.File(self.h5, "r+") as handle:
            info[0]["ConversionFactor"] -= 1
            info[0]["Label"], info[2]["Label"] = info[2]["Label"], info[0]["Label"]
            handle[cleanup_tool.ANALOG_PATH + "/InfoChannel"][:] = info
        with self.assertRaisesRegex(ValueError, "channel order"):
            self.cleanup(apply=True)
        with h5py.File(self.h5, "r+") as handle:
            info[0]["Label"], info[2]["Label"] = info[2]["Label"], info[0]["Label"]
            handle[cleanup_tool.ANALOG_PATH + "/InfoChannel"][:] = info
            handle["Data/Recording_0/EventStream/Stream_0/EventEntity_1"][0, 0] = 1200
        with self.assertRaisesRegex(ValueError, "event timestamp"):
            self.cleanup(apply=True)
        self.assertTrue(self.h5.is_file())

    def test_failed_nwb_and_missing_stage_refuse_cleanup(self) -> None:
        report_path = self.results / "repro/nwb_finalization_report.json"
        write_json(report_path, {**self.nwb, "pynwb_reread_and_schema_validation": "failed"})
        with self.assertRaisesRegex(ValueError, "NWB correction"):
            self.cleanup(apply=True)
        write_json(report_path, self.nwb)
        self.trace.write_text("\n".join(self.trace.read_text().splitlines()[:-1]) + "\n")
        with self.assertRaisesRegex(ValueError, "11 distinct"):
            self.cleanup(apply=True)
        self.assertTrue(self.h5.is_file())

    def test_prepared_ledger_survives_interrupted_unlink_and_can_resume(self) -> None:
        original_unlink = Path.unlink

        def interrupted(path, *args, **kwargs):
            if path == self.h5:
                raise OSError("simulated interruption before unlink")
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", interrupted), self.assertRaisesRegex(OSError, "simulated interruption"):
            self.cleanup(apply=True)
        self.assertTrue(self.h5.exists())
        prepared = next((self.results / "repro/h5_cleanup").glob("*/prepared.json"))
        before = prepared.read_bytes()
        result = self.cleanup(apply=True)
        self.assertEqual(result["status"], "deleted")
        self.assertEqual(prepared.read_bytes(), before)

    def test_cross_collection_requires_bound_source_evidence_and_preserves_xml(self) -> None:
        relative = Path(self.manifest["recording_id"])
        xml = self.allowed / "MANNY_MEAs_chemogenetics" / relative.parent / self.xml.name
        h5 = self.allowed / "chemogenetic_project" / relative.with_name(self.stem + ".h5")
        xml.parent.mkdir(parents=True)
        h5.parent.mkdir(parents=True)
        self.xml.rename(xml)
        self.h5.rename(h5)
        self.xml, self.h5 = xml, h5
        self.manifest["source_xml"] = str(xml)
        for path in (self.input_dir / "mcs_recording_manifest.json", self.results / "mcs_recording_manifest.json",
                     self.results / "repro/mcs_input/mcs_recording_manifest.json"):
            write_json(path, self.manifest)
        with self.assertRaisesRegex(ValueError, "explicit source selection evidence"):
            self.cleanup(apply=True)
        evidence = {"schema_version": 1, "recording_id": self.manifest["recording_id"],
                    "source_h5": str(h5), "h5_evidence_status": "inspected"}
        write_json(self.input_dir / "source_time_evidence.json", {**evidence, "recording_id": "foreign"})
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.cleanup(apply=True)
        write_json(self.input_dir / "source_time_evidence.json", evidence)
        self.assertEqual(self.cleanup()["status"], "eligible_dry_run")
        result = self.cleanup(apply=True)
        self.assertEqual(result["status"], "deleted")
        ledger = Path(result["ledger"])
        self.assertEqual((ledger / xml.name).read_bytes(), xml.read_bytes())
        self.assertEqual(json.loads((ledger / "source_time_evidence.json").read_text()), evidence)
        self.assertTrue(xml.exists())

    def test_cross_collection_foreign_path_cannot_be_authorized_by_evidence(self) -> None:
        wrong = self.allowed / "unlisted_namespace" / (self.stem + ".h5")
        wrong.parent.mkdir()
        wrong.write_bytes(self.h5.read_bytes())
        write_json(self.input_dir / "source_time_evidence.json", {
            "schema_version": 1, "recording_id": self.manifest["recording_id"],
            "source_h5": str(wrong), "h5_evidence_status": "inspected",
        })
        with self.assertRaisesRegex(ValueError, "canonical recording identity"):
            self.cleanup(candidate=wrong, apply=True)
        self.assertTrue(wrong.exists())


if __name__ == "__main__":
    unittest.main()
