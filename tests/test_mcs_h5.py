from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
from axion_mea.io.mcs_h5 import export_mcs_binary, inspect_mcs_h5, mcs_60mea200_geometry  # noqa: E402


class McsH5Tests(unittest.TestCase):
    def test_60mea200_geometry_uses_numeric_row_column_labels_and_excludes_reference(self) -> None:
        geometry = mcs_60mea200_geometry(("47", "Ref", "12"))
        self.assertEqual(geometry, [
            {"stream_channel_index": 0, "channel_label": "47", "x_um": 1400.0, "y_um": 800.0},
            {"stream_channel_index": 2, "channel_label": "12", "x_um": 400.0, "y_um": 200.0},
        ])

    def _write_fixture(self, path: Path) -> None:
        info_type = np.dtype([
            ("ChannelID", "<i4"), ("Label", h5py.string_dtype()), ("Exponent", "<i4"),
            ("Tick", "<i8"), ("ConversionFactor", "<i8"),
        ])
        event_type = np.dtype([("EventID", "<i4"), ("Label", h5py.string_dtype())])
        with h5py.File(path, "w") as h5:
            analog = h5.create_group("Data/Recording_0/AnalogStream/Stream_0")
            analog.create_dataset("ChannelData", data=np.asarray([[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=np.int32))
            analog.create_dataset("ChannelDataTimeStamps", data=np.asarray([[1000, 0, 2]], dtype=np.int64))
            info = np.asarray([(0, "12", -12, 100, 59605), (1, "Ref", -12, 100, 59605), (2, "87", -12, 100, 59605)], dtype=info_type)
            analog.create_dataset("InfoChannel", data=info)
            event = h5.create_group("Data/Recording_0/EventStream/Stream_0")
            event.create_dataset("InfoEvent", data=np.asarray([(1, "pulse start")], dtype=event_type))
            event.create_dataset("EventEntity_1", data=np.asarray([[1200, 1300], [0, 0]], dtype=np.int64))

    def test_inspect_and_export_excludes_reference_and_is_sample_major(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "test.h5"
            self._write_fixture(source)
            recording = inspect_mcs_h5(source)
            self.assertEqual(recording.sampling_frequency_hz, 10_000.0)
            self.assertEqual(recording.signal_channel_indices, (0, 2))
            self.assertAlmostEqual(recording.events[0]["time_from_recording_start_s"], 0.0002)
            manifest = export_mcs_binary(recording, root / "out", chunk_samples=2)
            self.assertEqual(np.fromfile(manifest["binary_file"], dtype=np.int16).tolist(), [1, 7, 2, 8, 3, 9])
            self.assertEqual(json.loads((root / "out/mcs_preparation_manifest.json").read_text())["n_chan_bin"], 2)


if __name__ == "__main__":
    unittest.main()
