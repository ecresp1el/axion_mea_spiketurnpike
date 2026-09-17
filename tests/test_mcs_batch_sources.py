from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("audit_mcs_batch_sources", ROOT / "scripts/audit_mcs_batch_sources.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class SourceAuditTests(unittest.TestCase):
    def test_source_identity_includes_full_hierarchy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "A/Stim 1/353.1/2021-06-23T09-29-06McsRecording.h5"
            second = root / "A/Stim 1/354.1/2021-06-23T09-29-06McsRecording.h5"
            for path in (first, second):
                path.parent.mkdir(parents=True)
                path.touch()
            index = audit.index_sources([root])
            self.assertEqual(len(index), 2)
            self.assertEqual(index[str(first.relative_to(root).with_suffix(""))]["h5"], [first])

    def test_contiguous_timestamp_intervals(self):
        audit.validate_timestamps(np.array([[100, 0, 3], [500, 4, 7]]), 8, 100, 100)
        for rows in ([[100, 0, 3], [600, 4, 7]], [[100, 0, 3], [500, 5, 7]], [[100, 0, 6]]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                audit.validate_timestamps(np.array(rows), 8, 100, 100)

    def fixture(self, root: Path):
        path = root / "source.h5"
        dtype = np.dtype([("ChannelID", "<i4"), ("Label", h5py.string_dtype()),
                          ("Tick", "<i8"), ("Exponent", "<i4"),
                          ("ConversionFactor", "<i8"), ("ADZero", "<i4")])
        values = np.arange(36, dtype=np.int32).reshape(3, 12)
        info = np.array([(0, "47", 100, -12, 59605, 0), (1, "Ref", 100, -12, 59605, 0),
                         (2, "48", 100, -12, 59605, 0)], dtype=dtype)
        with h5py.File(path, "w") as handle:
            analog = handle.create_group(audit.ANALOG_PATH)
            analog.create_dataset("ChannelData", data=values)
            analog.create_dataset("InfoChannel", data=info)
            analog.create_dataset("ChannelDataTimeStamps", data=np.array([[300000, 0, 11]]))
        binary = root / "mcs_signal_channels.int32.bin"
        binary.write_bytes(values[[0, 2]].T.astype("<i4").tobytes())
        prep = {"channel_labels": ["47", "Ref", "48"], "sample_count": 12,
                "sampling_frequency_hz": 10000, "n_chan_bin": 2, "first_timestamp": 300000,
                "conversion_to_volts": [59605e-12] * 3, "events": [], "binary_file": str(binary)}
        return path, binary, prep

    def test_h5_evidence_preserves_calibration_and_exact_sample_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, _, prep = self.fixture(root)
            checked = audit.inspect_h5(path, root, prep, window_samples=3)
            self.assertEqual(len(checked["sampled_windows"]), 3)
            self.assertEqual(checked["adc_zero"], [0, 0, 0])
            self.assertTrue(all(item["exact_match"] for item in checked["sampled_windows"]))

    def test_h5_sample_mismatch_and_nonzero_adc_offset_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, binary, prep = self.fixture(root)
            with binary.open("r+b") as handle:
                handle.write(np.array([-100], dtype="<i4").tobytes())
            with self.assertRaisesRegex(ValueError, "disagree"):
                audit.inspect_h5(path, root, prep)
            path, _, prep = self.fixture(root)
            with h5py.File(path, "r+") as handle:
                dataset = handle[f"{audit.ANALOG_PATH}/InfoChannel"]
                info = dataset[:]
                info["ADZero"][0] = 1
                dataset[:] = info
            with self.assertRaisesRegex(ValueError, "ADC offsets"):
                audit.inspect_h5(path, root, prep)


if __name__ == "__main__":
    unittest.main()
