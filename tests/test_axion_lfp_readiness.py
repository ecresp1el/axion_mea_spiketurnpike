"""Critical voltage layout, calibration, and resampling checks."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

import numpy as np

_spec = importlib.util.spec_from_file_location(
    'lfp_readiness', Path(__file__).resolve().parents[1]/'scripts/audit_axion_lfp_readiness.py')
lfp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lfp)


def text(s):
    b = s.encode()
    return struct.pack('<i', len(b)) + b


def checked(b):
    return b + struct.pack('<I', zlib.crc32(b) & 0xffffffff)


def fixture(path, values, combined=False, fs=12500.):
    scale = -5.5e-8
    channels = struct.pack('<II', 0, 2)
    channels += struct.pack('<6BH', 1,1,1,1,0,0,0)
    channels += struct.pack('<6BH', 1,2,1,1,0,1,0)
    data = values.astype('<i2').tobytes()
    if combined:
        vector = checked(struct.pack('<2H', 1,0)+text('Raw'))
        base = struct.pack('<4Hdd5I', 1,1,2,0,fs,scale,2,1,1,len(vector),0)+bytes(56)
        base += struct.pack('<d', len(values)/fs)+text('Voltage')+text('')
        offset = 1024+len(channels)+len(base)+16+4+len(vector)
        meta = checked(base+struct.pack('<qq',offset,len(data)))+vector
        blocks = [(2,channels),(7,meta),(4,data)]
    else:
        offset = 1024+64+len(channels)
        meta = struct.pack('<dd',fs,scale)+bytes(28)+struct.pack('<qIII',offset,2,1,0)
        blocks = [(3,meta),(2,channels),(4,data)]
    head = b'AxionBio'+struct.pack('<HHHQIq',0,1,3,0,0,1024)
    entries = [(kind<<56)|len(b) for kind,b in blocks]
    head += struct.pack('<123Q',*(entries+[0]*(123-len(entries))))
    path.write_bytes(checked(head)+bytes(2)+b''.join(b for _,b in blocks))


class TestLFPReadiness(unittest.TestCase):
    def test_storage_order_and_negative_scale(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            for combined, expected in [(False,['A1','B1']),(True,['B1','A1'])]:
                p = Path(tmp)/'test.raw'
                x = np.array([[1,-2],[300,-400],[0,10]],dtype=np.int16)
                fixture(p,x,combined)
                d = lfp.read_layout(p)
                self.assertEqual([c['well'] for c in d['channel_map']],expected)
                np.testing.assert_array_equal(lfp.read_counts(d,0,3),x)
                uv = lfp.resample_uv(x,d['voltage_scale_v_per_count'],12500,12500)
                np.testing.assert_allclose(uv,x*(-0.055),rtol=1e-6)
                p.write_bytes(p.read_bytes()[:-1])
                with self.assertRaises(ValueError):
                    lfp.read_layout(p)

    def test_alias_rejection_and_preserved_low_frequency_amplitude(self):
        fs = 12500
        t = np.arange(fs*3)/fs
        x = (1000*np.sin(2*np.pi*50*t)+1000*np.sin(2*np.pi*1300*t))[:,None]
        y = lfp.resample_uv(x,1e-6,fs,1000)[250:-250,0]
        tt = np.arange(len(y))/1000
        amplitude = lambda hz: abs(2*np.mean(y*np.exp(-2j*np.pi*hz*tt)))
        self.assertAlmostEqual(amplitude(50),1000,delta=2)
        self.assertLess(amplitude(300),1)

    def test_chunked_export_matches_full_resampling(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            p = Path(tmp)/'long.raw'
            fs = 12500
            t = np.arange(fs*22)/fs
            x = np.column_stack([1000*np.sin(2*np.pi*7*t),1000*np.cos(2*np.pi*91*t)]).astype(np.int16)
            fixture(p,x,combined=True)
            out = Path(tmp)/'export'
            lfp.export_voltage(p,out)
            actual = np.load(out/'voltage_uv.npy')
            expected = lfp.resample_uv(x,-5.5e-8,fs)
            np.testing.assert_allclose(actual,expected,atol=1e-5)

    def test_short_clip_is_audited_and_flagged(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            p = Path(tmp)/'short.raw'
            t = np.arange(65625)/12500
            x = np.column_stack([500*np.sin(2*np.pi*9*t),500*np.cos(2*np.pi*13*t)]).astype(np.int16)
            fixture(p,x,combined=True)
            d,rows = lfp.audit_file(p,Path(tmp))
            self.assertEqual(d['duration_s'],5.25)
            self.assertIn('very_short_recording_overlapping_qc_windows',d['qc_flags'])
            self.assertEqual(len(rows),6)


if __name__ == '__main__':
    unittest.main()
