from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("recover_mcs_msrd_prefix", ROOT / "scripts/recover_mcs_msrd_prefix.py")
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)
LABELS = ("47 48 46 45 38 37 28 36 27 17 26 16 35 25 Ref 14 24 34 13 23 "
          "12 22 33 21 32 31 44 43 41 42 52 51 53 54 61 62 71 63 72 82 "
          "73 83 64 74 84 85 75 65 86 76 87 77 66 78 67 68 55 56 58 57").split()


def padded(fields, length):
    data = "".join(f"{key}={value}\r\n" for key, value in fields.items()).encode()
    if len(data) > length:
        raise AssertionError("Fixture header exceeds expected boundary")
    return data + b" " * (length - len(data))


def fixture(root: Path, corrupt=None):
    source = root / "2021-06-23T10-19-07McsRecording.msrd"
    first = 32768
    header = padded({"FileID": "MULTI_CHANNEL_SUITE", "FileVersion": 17,
                     "FPosFirstRecordingHdr": 1900, "MeaName": "60MEA200/30iR"}, 1900)
    metadata = f"RecordingID=0\r\nFPosNext={first}\r\nTimeStamp=300000\r\nDuration=0\r\nDataType=Analog\r\nEntities=60\r\n"
    for channel, label in enumerate(LABELS):
        metadata += "".join(f"{key}={value}\r\n" for key, value in {
            "Entity": channel + 1, "ChID": channel, "Label": label, "RawDataType": "Int", "Unit": "V",
            "ADZero": 0, "Tick": 100, "ConversionFactor": 59605, "Exponent": -12}.items())
    metadata += "DataType=Event\r\nEntities=0\r\n"
    contents = bytearray(header + metadata.encode() + b" " * (first - 1900 - len(metadata)))
    previous = -1
    previous_entity = {i: -1 for i in range(60)}
    for block_index in range(124):
        round_index, channel = divmod(block_index, 60)
        offset = len(contents)
        values = np.arange(64, dtype="<i4") + channel * 100 + round_index * 10000
        fields = {"Entity": channel + 1, "FPosPrev": previous, "FPosPrevID": previous_entity[channel],
                  "FPosNext": offset + 350 + values.nbytes, "FPosNextID": -1,
                  "TimeStamp": 300000 + round_index * 6400, "Size": values.nbytes}
        if block_index == 60 and corrupt == "pointer":
            fields["FPosPrevID"] = -1
        if block_index == 60 and corrupt == "timestamp":
            fields["TimeStamp"] += 100
        contents.extend(padded(fields, 350))
        payload = values.astype("<i4").tobytes()
        contents.extend(payload[:-10] if block_index == 123 else payload)
        previous, previous_entity[channel] = offset, offset
    source.write_bytes(contents)
    return source


class PrefixRecoveryTests(unittest.TestCase):
    def test_only_common_complete_prefix_is_exported_and_source_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = fixture(root)
            before = source.read_bytes()
            output = root / "staged/group/condition" / source.stem
            result = recovery.recover(source, output)
            report, prep = result["report"], result["preparation"]
            self.assertEqual(prep["sample_count"], 128)
            self.assertEqual(prep["n_chan_bin"], 59)
            self.assertEqual(report["stop"]["kind"], "incomplete_payload")
            self.assertEqual(report["complete_blocks_examined"], 123)
            self.assertTrue(report["all_retained_signal_samples_compared_to_original"])
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(report["source_sha256"], recovery.sha256(source))
            values = np.fromfile(prep["binary_file"], dtype="<i4").reshape(128, 59)
            expected = np.stack([np.r_[np.arange(64) + ch * 100, np.arange(64) + ch * 100 + 10000]
                                 for ch in range(60) if ch != 14], axis=1)
            np.testing.assert_array_equal(values, expected)
            self.assertEqual(prep["events"], [])
            self.assertIn("absent markers", report["source_review_warning"])
            with self.assertRaises(FileExistsError):
                recovery.recover(source, output)

    def test_corrupt_links_or_discontinuous_timestamps_are_not_salvaged(self):
        for failure in ("pointer", "timestamp"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                source = fixture(Path(temp), corrupt=failure)
                with self.assertRaises(ValueError):
                    recovery.inspect_prefix(source)

    def test_scan_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            source = fixture(Path(temp))
            with self.assertRaisesRegex(ValueError, "maximum block"):
                recovery.inspect_prefix(source, max_blocks=10)

    def test_index_replaces_only_recovered_row(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = fixture(root)
            staged = root / "staged"
            output = staged / "group/condition" / source.stem
            result = recovery.recover(source, output)
            identity = output.relative_to(staged).as_posix()
            other = {"recording_id": "untouched", "status": "ready", "staged": True, "source_xml": None}
            source_index = root / "source_index.json"
            source_index.write_text(json.dumps({"staged_root": str(staged), "summary": {"unmatched_local_sources": [identity]},
                "records": [other, {"recording_id": identity, "status": "blocked", "staged": False, "source_xml": None}]}))
            updated = recovery.update_index(source_index, root / "updated", output, source, None, result)
            document = json.loads(updated.read_text())
            self.assertEqual(document["records"][0], other)
            self.assertEqual(document["summary"]["status_counts"], {"ready": 2})
            row = document["records"][1]
            self.assertEqual(row["recording_completeness"], "recovered_prefix")
            self.assertFalse(row["source_h5_cleanup_allowed"])
            self.assertTrue(Path(row["recovery_report"]).is_file())


if __name__ == "__main__":
    unittest.main()
