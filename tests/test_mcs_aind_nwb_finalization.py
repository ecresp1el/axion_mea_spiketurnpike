from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
import spikeinterface as si
import zarr
from hdmf_zarr import NWBZarrIO
from pynwb import NWBFile
from pynwb.file import Subject
from pynwb.misc import Units

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from finalize_mcs_aind_nwb import MOCK_SUBJECT, finalize, inspect_time_sources, read_subject


class McsNwbFinalizationTests(unittest.TestCase):
    def build_fixture(self, root, *, subject=None, channel_count=3, pitch=200, fs=10000):
        inputs, results = root / "inputs", root / "results"
        inputs.mkdir()
        (results / "nwb").mkdir(parents=True)
        xml = inputs / "acquisition_settings.xml"
        xml.write_text("<Settings><SampleRateElectrodes>10000</SampleRateElectrodes>"
                       "<StimulationLayoutConfigurationForMea21_256>Unknown</StimulationLayoutConfigurationForMea21_256></Settings>")
        source_h5 = inputs / "original.h5"
        with h5py.File(source_h5, "w") as handle:
            group = handle.create_group("Data")
            group.attrs["Date"] = "Tuesday, June 22, 2021"
            group.attrs["DateInTicks"] = 637599722064171084
            group.create_group("Recording_0").attrs["TimeStamp"] = 300000
        manifest = {
            "analysis_kind": "mcs_aind_single_mea_recording", "results_dir": str(results),
            "recording_id": "Actuators & Effectors/Stim 1/353.1/2021-06-22T15-23-26McsRecording",
            "sample_count": 1000, "sampling_frequency_hz": fs, "source_xml": str(xml), "first_timestamp": 300000,
            "source_file": str(source_h5),
        }
        (inputs / "mcs_recording_manifest.json").write_text(json.dumps(manifest))
        positions = np.asarray([[index % 8 * pitch, index // 8 * pitch] for index in range(channel_count)])
        with (inputs / "channels.csv").open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["channel_label", "x_um", "y_um"])
            for index, position in enumerate(positions):
                writer.writerow([str(index + 1), *position])
        binary = inputs / "recording.bin"
        np.random.default_rng(0).integers(-1000, 1000, (1000, channel_count), dtype=np.int32).tofile(binary)
        recording = si.read_binary(binary, sampling_frequency=fs, dtype="int32", num_channels=channel_count,
                                   gain_to_uV=0.059605, offset_to_uV=0)
        recording.set_dummy_probe_from_locations(positions)
        sorting = si.NumpySorting.from_unit_dict({11: np.asarray([100, 200, 300]), 23: np.asarray([400, 500, 600])}, fs)
        sorting.set_property("original_cluster_id", [111, 123])
        sorting.save(folder=results / "curated" / "recording1")
        analyzer = si.create_sorting_analyzer(sorting, recording, sparse=False)
        analyzer.compute("random_spikes", max_spikes_per_unit=3, seed=0)
        analyzer.compute("templates", operators=["average", "std"], ms_before=1, ms_after=2, n_jobs=1, progress_bar=False)
        analyzer.save_as(format="zarr", folder=results / "postprocessed" / "recording1.zarr")
        means = analyzer.get_extension("templates").get_templates()
        stds = analyzer.get_extension("templates").get_templates(operator="std")
        nwbfile = NWBFile(session_description="AIND exported recording", identifier="test-recording",
                          session_start_time=datetime(2026, 9, 17, tzinfo=timezone.utc),
                          subject=Subject(**(MOCK_SUBJECT if subject is None else subject)))
        device = nwbfile.create_device(name="MEA")
        group = nwbfile.create_electrode_group(name="MEA", description="MEA", location="unknown", device=device)
        for coordinate in ("rel_x", "rel_y"):
            nwbfile.add_electrode_column(name=coordinate, description="Position in micrometers")
        for position in positions:
            nwbfile.add_electrode(group=group, location="unknown", rel_x=float(position[0]), rel_y=float(position[1]))
        nwbfile.units = Units(name="units", waveform_rate=float(fs), waveform_unit="volts", resolution=1.0 / fs)
        nwbfile.add_unit_column(name="ks_unit_id", description="SI unit ID")
        nwbfile.add_unit_column(name="original_cluster_id", description="Original Kilosort cluster")
        for index, unit in enumerate(sorting.unit_ids):
            nwbfile.add_unit(spike_times=sorting.get_unit_spike_train(unit) / fs,
                             waveform_mean=means[index], waveform_sd=stds[index],
                             ks_unit_id=int(unit), original_cluster_id=int(unit + 100))
        nwb_path = results / "nwb" / "recording.nwb"
        with NWBZarrIO(path=str(nwb_path), mode="w") as io:
            io.write(nwbfile)
        return inputs, results, source_h5, nwb_path, means

    def test_corrects_only_known_faults_and_is_idempotent(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            inputs, results, source_h5, nwb_path, means = self.build_fixture(Path(tmp))
            plan = finalize(results, inputs, source_h5, apply=False)
            self.assertEqual(plan["status"], "planned")
            self.assertFalse((results / "repro").exists())
            report = finalize(results, inputs, source_h5, apply=True)
            self.assertEqual(report["status"], "corrected")
            self.assertEqual(report["source_time"]["source_nominal_acquisition_datetime"], "2021-06-22T15:23:26")
            self.assertIsNone(report["source_time"]["acquisition_utc"])
            self.assertEqual(report["after"]["spike_count"], 6)
            corrected = zarr.open_group(str(nwb_path), mode="r")
            self.assertIsNone(read_subject(corrected))
            np.testing.assert_allclose(corrected["units/waveform_mean"][:], means * 1e-6, rtol=1e-6)
            backup = zarr.open_group(report["original_nwb_backup"], mode="r")
            self.assertEqual(read_subject(backup), MOCK_SUBJECT)
            np.testing.assert_array_equal(backup["units/waveform_mean"][:], means)
            source_h5.unlink()
            (inputs / "acquisition_settings.xml").unlink()
            self.assertEqual(finalize(results, inputs, source_h5, apply=True)["status"], "already_corrected")
            np.testing.assert_allclose(corrected["units/waveform_mean"][:], means * 1e-6, rtol=1e-6)

    def test_unmatched_waveforms_fail_before_any_mutation(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            inputs, results, source_h5, nwb_path, means = self.build_fixture(Path(tmp))
            original = zarr.open_group(str(nwb_path), mode="r+")
            original["units/waveform_mean"][:] = means * 7
            with self.assertRaisesRegex(ValueError, "does not match analyzer"):
                finalize(results, inputs, source_h5, apply=True)
            self.assertFalse((results / "repro").exists())
            self.assertEqual(read_subject(original), MOCK_SUBJECT)

    def test_preserves_subject_metadata_that_is_not_exact_mock(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            subject = {"subject_id": "real-sample", "description": "Verified source sample"}
            inputs, results, source_h5, nwb_path, _ = self.build_fixture(Path(tmp), subject=subject)
            report = finalize(results, inputs, source_h5, apply=True)
            self.assertFalse(report["removed_exact_mock_subject"])
            self.assertEqual(read_subject(zarr.open_group(str(nwb_path), mode="r")), subject)

    def test_60_channels_and_missing_h5_and_xml_preserve_explicit_evidence_limits(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            inputs, results, source_h5, nwb_path, means = self.build_fixture(Path(tmp), channel_count=60, pitch=100, fs=20000)
            source_h5.unlink()
            (inputs / "acquisition_settings.xml").unlink()
            manifest_path = inputs / "mcs_recording_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["source_xml"] = None
            manifest["source_msrd"] = "/source/recording.msrd"
            manifest["source_msrd_metadata_file"] = str(inputs / "acquisition_msrd_header.json")
            manifest_path.write_text(json.dumps(manifest))
            report = finalize(results, inputs, apply=True)
            self.assertEqual(report["after"]["electrode_count"], 60)
            self.assertEqual(report["after"]["sampling_frequency_hz"], 20000)
            self.assertEqual(report["source_time"]["h5_evidence_status"], "unavailable")
            self.assertEqual(report["source_time"]["h5_temporal_attributes"], {})
            self.assertEqual(report["source_time"]["source_xml_paths_inspected"], [])
            self.assertIn("No local source H5 was available", report["corrected_notes"])
            self.assertIsNone(report["source_time"]["acquisition_utc"])
            np.testing.assert_allclose(zarr.open_group(str(nwb_path), mode="r")["units/waveform_mean"][:], means * 1e-6, rtol=1e-6)

    def test_persisted_source_time_evidence_survives_h5_removal_and_rejects_wrong_recording(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            inputs, results, source_h5, _, _ = self.build_fixture(Path(tmp))
            manifest = json.loads((inputs / "mcs_recording_manifest.json").read_text())
            evidence = inspect_time_sources(manifest, source_h5)
            evidence_path = inputs / "source_time_evidence.json"
            evidence["recording_id"] = "another/recording"
            evidence_path.write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, "recording identity"):
                finalize(results, inputs, apply=True, source_time_evidence=evidence_path)
            evidence["recording_id"] = manifest["recording_id"]
            evidence_path.write_text(json.dumps(evidence))
            source_h5.unlink()
            report = finalize(results, inputs, apply=True, source_time_evidence=evidence_path)
            self.assertEqual(report["source_time"]["h5_evidence_status"], "inspected")
            self.assertEqual(report["source_time"]["evidence_origin"], "persisted_source_time_audit")
            self.assertIn("Data", report["source_time"]["h5_temporal_attributes"])
            self.assertTrue((results / "repro/source_time_evidence.json").exists())


if __name__ == "__main__":
    unittest.main()
