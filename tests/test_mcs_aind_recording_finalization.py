from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import spikeinterface as si
from probeinterface import generate_linear_probe

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "finalize_mcs_aind_recording", REPO_ROOT / "scripts/finalize_mcs_aind_recording.py"
)
finalizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(finalizer)


class McsRecordingFinalizationTests(unittest.TestCase):
    def test_preserves_six_extensions_and_loads_without_scratch_recording(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
            root = Path(temporary)
            results = root / "results"
            analyzer_path = results / "postprocessed/recording1.zarr"
            analyzer_path.parent.mkdir(parents=True)
            rng = np.random.default_rng(42)
            traces = rng.integers(-500, 501, size=(10000, 4), dtype=np.int32)
            traces[0, 0] = np.iinfo(np.int32).min
            traces[-1, -1] = np.iinfo(np.int32).max
            recording = si.NumpyRecording(traces, sampling_frequency=10000)
            recording.set_channel_gains([0.01, 0.02, 0.03, 0.04])
            recording.set_channel_offsets([0, 0, 0, 0])
            probe = generate_linear_probe(num_elec=4)
            probe.set_device_channel_indices(np.arange(4))
            recording = recording.set_probe(probe, in_place=False)
            scratch = root / "scratch/preprocessed"
            recording = recording.save(folder=scratch, format="binary", n_jobs=1, progress_bar=False)
            sorting = si.NumpySorting.from_unit_dict({7: np.arange(500, 9500, 500), 12: np.arange(750, 9500, 700)}, 10000)
            sorting.set_property("KSLabel", np.array(["mua", "good"]))
            sorting.set_property("original_cluster_id", np.array([17, 22]))
            analyzer = si.create_sorting_analyzer(sorting, recording, format="zarr", folder=analyzer_path, sparse=False)
            analyzer.compute({
                "random_spikes": {"max_spikes_per_unit": 10, "seed": 0},
                "templates": {}, "spike_amplitudes": {},
                "template_similarity": {"method": "l1"},
                "correlograms": {"method": "numpy"},
                "unit_locations": {"method": "center_of_mass"},
            }, n_jobs=1, progress_bar=False)
            source_hashes = {p.relative_to(scratch): finalizer.sha256(p) for p in scratch.rglob("*") if p.is_file()}
            report = finalizer.finalize(results, recording.get_binary_description()["file_paths"][0])
            self.assertEqual(report["status"], "validated")
            self.assertEqual(len(report["unchanged_extensions"]), 6)
            self.assertTrue(Path(report["original_analyzer_backup"]).is_dir())
            self.assertEqual(source_hashes, {p.relative_to(scratch): finalizer.sha256(p) for p in scratch.rglob("*") if p.is_file()})

            scratch.rename(scratch.with_name("scratch_unavailable"))
            reloaded = si.load_sorting_analyzer(analyzer_path)
            self.assertTrue(reloaded.has_recording())
            np.testing.assert_array_equal(reloaded.recording.get_traces(), traces)
            np.testing.assert_array_equal(reloaded.sorting.to_spike_vector(), sorting.to_spike_vector())
            np.testing.assert_array_equal(reloaded.recording.get_channel_gains(), [0.01, 0.02, 0.03, 0.04])
            finalizer.verify_analyzers(analyzer, reloaded)
            with self.assertRaises(FileExistsError):
                finalizer.finalize(results)

    def test_preservation_check_rejects_modified_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "templates"):
            finalizer.check_equal({"average": np.array([1, 2])}, {"average": np.array([1, 3])}, "templates")


if __name__ == "__main__":
    unittest.main()
