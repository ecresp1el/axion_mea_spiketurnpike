#!/usr/bin/env python3
"""Read continuous Axion voltage, audit short windows, or export calibrated LFP.

Supports the raw-v1 and single-dataset named-continuous layouts observed in the
2024/2026 archive. Layout follows AxionFileLoader's BlockVectorHeader,
CombinedBlockVectorHeaderEntry, ContinuousDataSet, and ChannelMapping classes.
Unsupported layouts fail closed. Acquisition eligibility is a separate decision
from this signal check; resampling cannot restore frequencies lost at acquisition.
"""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import json
from pathlib import Path
import struct
import zlib

import numpy as np
from scipy import signal


def exact(f, n):
    b = f.read(n)
    if len(b) != n:
        raise EOFError(f"Expected {n} bytes, got {len(b)}")
    return b


def string(f):
    n = struct.unpack('<i', exact(f, 4))[0]
    if not 0 <= n <= 1_000_000:
        raise ValueError('Invalid metadata string length')
    return exact(f, n).decode('utf-8')


def crc(f, start, end):
    f.seek(start)
    actual = zlib.crc32(exact(f, end - start)) & 0xffffffff
    expected = struct.unpack('<I', exact(f, 4))[0]
    if actual != expected:
        raise ValueError(f'Metadata CRC mismatch at {start}')


def read_layout(path):
    """Return calibrated voltage layout and electrodes in actual storage order."""
    path = Path(path)
    size = path.stat().st_size
    channels, legacy, datasets, regions = [], [], [], {}
    with path.open('rb') as f:
        head = exact(f, 1024)
        if head[:8] != b'AxionBio' or struct.unpack_from('<H', head, 10)[0] != 1:
            raise ValueError('Only Axion format major version 1 supported')
        crc(f, 0, 1018)
        entries = struct.unpack_from('<123Q', head, 34)
        f.seek(struct.unpack_from('<q', head, 26)[0])
        terminated = False
        while not terminated:
            for word in entries:
                typ, length = word >> 56, word & ((1 << 56) - 1)
                if typ == 0:
                    terminated = True
                    break
                start = f.tell()
                if length == (1 << 56) - 1 or start + length > size:
                    raise ValueError('Unbounded or truncated entry')
                if typ == 2:
                    plate, n = struct.unpack('<II', exact(f, 8))
                    channels = []
                    for i in range(n):
                        wc, wr, ec, er, chip, chan, aux = struct.unpack('<6BH', exact(f, 8))
                        channels.append(dict(well=f'{chr(64 + wr)}{wc}', electrode_column=ec,
                                             electrode_row=er, amplifier_chip=chip,
                                             amplifier_channel=chan, auxiliary=aux))
                elif typ == 3:
                    b = exact(f, 64)
                    fs, scale = struct.unpack_from('<dd', b)
                    offset, n, samples, block = struct.unpack_from('<qIII', b, 44)
                    legacy.append(dict(sampling_hz=fs, voltage_scale_v_per_count=scale,
                                       data_start=offset, channels=n, samples_per_block=samples,
                                       block_header_bytes=block, format='raw_v1'))
                elif typ == 4:
                    regions[start] = length
                elif typ == 7:
                    b = exact(f, 100)
                    major, minor, dtype, sampletype = struct.unpack_from('<4H', b)
                    fs, scale = struct.unpack_from('<dd', b, 8)
                    n, nsets, samples, vector, block = struct.unpack_from('<5I', b, 24)
                    duration = struct.unpack('<d', exact(f, 8))[0] if major > 1 or minor >= 1 else None
                    name, description = string(f), string(f)
                    offset, length_data = struct.unpack('<qq', exact(f, 16))
                    crc(f, start, f.tell())
                    if dtype != 2 or sampletype != 0 or nsets != 1 or name != 'Voltage':
                        raise ValueError('Only a single signed-int16 continuous Voltage dataset supported')
                    extra_start = f.tell()
                    ids = struct.unpack(f'<{n}H', exact(f, 2*n))
                    names = [string(f) for _ in range(nsets)]
                    crc(f, extra_start, f.tell())
                    if vector != f.tell() - extra_start:
                        raise ValueError('Named-continuous vector metadata size mismatch')
                    datasets.append(dict(sampling_hz=fs, voltage_scale_v_per_count=scale,
                                         data_start=offset, data_bytes=length_data, channels=n,
                                         samples_per_block=samples, block_header_bytes=block,
                                         duration_declared_s=duration, channel_ids=ids,
                                         dataset_names=names, description=description,
                                         format='named_continuous_int16'))
                f.seek(start + length)
            if not terminated:
                sub = f.tell()
                if exact(f, 8) != b'AxionBio':
                    raise ValueError('Invalid subheader')
                entries = struct.unpack('<126Q', exact(f, 1008))
                crc(f, sub, sub + 1016)
                f.seek(sub + 1024)
    for d in legacy:
        if d['data_start'] not in regions:
            raise ValueError('Legacy data region missing')
        d['data_bytes'] = regions[d['data_start']]
        datasets.append(d)
    if len(datasets) != 1:
        raise ValueError(f'Expected one voltage dataset; found {len(datasets)}')
    d = datasets[0]
    if d['samples_per_block'] != 1 or d['block_header_bytes'] != 0:
        raise ValueError('Only sample-interleaved voltage without block headers supported')
    if not np.isfinite(d['voltage_scale_v_per_count']) or d['voltage_scale_v_per_count'] == 0:
        raise ValueError('Invalid voltage calibration')
    if d['sampling_hz'] <= 0 or not np.isfinite(d['sampling_hz']):
        raise ValueError('Invalid sample rate')
    if 'channel_ids' in d:
        lookup = {(c['amplifier_chip'] << 8) | c['amplifier_channel']: c for c in channels}
        channels = [lookup[c] for c in d.pop('channel_ids')]
    if len(channels) != d['channels'] or d['data_bytes'] % (2*d['channels']):
        raise ValueError('Channel count or sample byte count mismatch')
    if d['data_start'] < 1024 or d['data_start'] + d['data_bytes'] > size:
        raise ValueError('Truncated data region')
    if len({(c['well'], c['electrode_column'], c['electrode_row']) for c in channels}) != len(channels):
        raise ValueError('Duplicate electrode coordinates')
    d['sample_count'] = d['data_bytes'] // (2*d['channels'])
    d['duration_s'] = d['sample_count'] / d['sampling_hz']
    if d.get('duration_declared_s') is not None and abs(d['duration_s']-d['duration_declared_s']) > 1/d['sampling_hz']:
        raise ValueError('Declared duration disagrees with voltage byte count')
    d.update(raw_path=str(path), file_size_bytes=size, channel_map=channels,
             structural_check='passed', sample_dtype='<i2')
    return d


def read_counts(layout, start_sample, stop_sample, channel_indices=None):
    if not 0 <= start_sample < stop_sample <= layout['sample_count']:
        raise ValueError('Requested samples outside recording')
    n = layout['channels']
    with open(layout['raw_path'], 'rb') as f:
        f.seek(layout['data_start'] + start_sample*n*2)
        values = np.frombuffer(exact(f, (stop_sample-start_sample)*n*2), dtype='<i2').reshape(-1, n)
    return values if channel_indices is None else values[:, channel_indices]


def resample_uv(counts, scale, fs, target_hz=1000):
    """Preserve signed calibration; FIR anti-alias before rational resampling."""
    ratio = Fraction(target_hz / fs).limit_denominator(100000)
    if target_hz > fs or abs(float(ratio)*fs-target_hz) > 1e-8:
        raise ValueError('Target must be an exact rational downsampling rate')
    uv = counts.astype(np.float32) * (scale*1e6)
    return signal.resample_poly(uv, ratio.numerator, ratio.denominator, axis=0,
                                window=('kaiser', 8.6), padtype='line').astype(np.float32)


def write_csv(path, rows):
    if not rows:
        return
    with Path(path).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def audit_file(path, out, window_s=4, pilot=False):
    d = read_layout(path)
    fs, scale = d['sampling_hz'], d['voltage_scale_v_per_count']
    if window_s < 3 or d['duration_s'] < 3.5:
        raise ValueError('At least 3s QC windows and 3.5s recording required')
    window_s = min(window_s, d['duration_s']-0.5)
    margin = min(1., (d['duration_s']-window_s)/4)
    starts = [margin, (d['duration_s']-window_s)/2, d['duration_s']-window_s-margin]
    rows, spectra = [], []
    wells = sorted({c['well'] for c in d['channel_map']})
    for wi, start in enumerate(starts):
        counts = read_counts(d, round(start*fs), round((start+window_s)*fs))
        varying = np.ptp(counts.astype(np.int32), axis=0) > 0
        rail = np.mean((counts == -32768) | (counts == 32767), axis=0)
        uv = resample_uv(counts, scale, fs)
        # Discard resampling boundaries for QC spectral estimates.
        core = uv[250:-250]
        freq, psd = signal.welch(core, fs=1000, nperseg=min(2000, len(core)),
                                 detrend='constant', axis=0)
        spectra.append(psd)
        for well in wells:
            ix = [i for i,c in enumerate(d['channel_map']) if c['well'] == well]
            band = (freq >= 1) & (freq <= 200)
            line = (freq >= 58) & (freq <= 62)
            power = np.trapezoid(psd[band][:,ix], freq[band], axis=0)
            line_power = np.trapezoid(psd[line][:,ix], freq[line], axis=0)
            rows.append(dict(raw_path=str(path), window_start_s=start, window_duration_s=window_s,
                             well=well, channels=len(ix), varying_channels=int(varying[ix].sum()),
                             all_zero_channels=int(np.all(counts[:,ix] == 0, axis=0).sum()),
                             channels_with_adc_rail=int((rail[ix]>0).sum()),
                             max_adc_rail_fraction=float(rail[ix].max()),
                             median_raw_std_uv=float(np.median(np.std(counts[:,ix].astype(np.float64),axis=0)*abs(scale)*1e6)),
                             median_1_200_hz_power_uv2=float(np.median(power)),
                             median_58_62_hz_power_fraction=float(np.median(line_power/np.maximum(power,1e-30)))))
        if pilot and wi == 1:
            np.savez_compressed(out/'pilot_1khz.npz', voltage_uv=uv, sampling_hz=1000.,
                                start_s=start, edge_trim_recommended_s=0.25,
                                channel_map_json=json.dumps(d['channel_map']), raw_path=str(path))
    flags = []
    if d['duration_s'] < 30:
        flags.append('very_short_recording_overlapping_qc_windows')
    if any(r['varying_channels'] != r['channels'] for r in rows):
        flags.append('constant_channels_in_sampled_windows')
    if any(r['channels_with_adc_rail'] for r in rows):
        flags.append('adc_rail_hits_in_sampled_windows')
    d.update(qc_windows_start_s=starts, qc_window_duration_s=window_s,
             qc_flags=flags, signal_check='review_flags' if flags else 'sampled_signal_checks_passed',
             qc_scope='Three short windows; does not establish biological activity or full-recording artifact freedom.')
    (out/'layout_and_qc.json').write_text(json.dumps(d, indent=2)+'\n')
    write_csv(out/'well_qc.csv', rows)
    np.savez_compressed(out/'sampled_psd.npz', frequency_hz=freq,
                        median_psd_uv2_per_hz=np.median(spectra, axis=0),
                        channel_map_json=json.dumps(d['channel_map']))
    return d, rows


def export_voltage(path, out, start_s=0, duration_s=None, well=None, target_hz=1000):
    """Chunked export with FIR overlap; no whitening, spike HP, or rereference."""
    d = read_layout(path)
    fs = d['sampling_hz']
    ratio = Fraction(target_hz / fs).limit_denominator(100000)
    if target_hz < 500 or target_hz > fs:
        raise ValueError('Use target >=500 Hz and <= source sample rate')
    # Require an aligned output grid, including at chunk boundaries.
    first = round(start_s * fs)
    if first % ratio.denominator:
        raise ValueError('Start must align with rational resampling grid')
    last = d['sample_count'] if duration_s is None else min(d['sample_count'], first+round(duration_s*fs))
    if not 0 <= first < last <= d['sample_count']:
        raise ValueError('Empty or invalid export interval')
    ix = [i for i,c in enumerate(d['channel_map']) if well is None or c['well'] == well]
    if not ix:
        raise ValueError('Requested well not present')
    out.mkdir(parents=True, exist_ok=True)
    nout = ((last-first)*ratio.numerator+ratio.denominator-1)//ratio.denominator
    dest = np.lib.format.open_memmap(out/'voltage_uv.npy', mode='w+', dtype=np.float32, shape=(nout,len(ix)))
    chunk = int(10*fs)//ratio.denominator*ratio.denominator
    overlap = max(ratio.denominator, int(fs)//ratio.denominator*ratio.denominator)
    for a in range(first,last,chunk):
        b = min(a+chunk,last)
        left, right = max(0,a-overlap), min(d['sample_count'],b+overlap)
        x = read_counts(d,left,right,ix)
        y = resample_uv(x,d['voltage_scale_v_per_count'],fs,target_hz)
        skip = (a-left)*ratio.numerator//ratio.denominator
        offset = (a-first)*ratio.numerator//ratio.denominator
        count = min(nout-offset,((b-a)*ratio.numerator+ratio.denominator-1)//ratio.denominator)
        dest[offset:offset+count] = y[skip:skip+count]
    dest.flush()
    d.update(output_sampling_hz=target_hz, output_start_s=first/fs,
             output_units='microvolts', output_shape=[nout,len(ix)],
             output_channel_map=[d['channel_map'][i] for i in ix],
             processing='signed voltage scaling; scipy resample_poly Kaiser beta8.6 with 1s overlap; no additional highpass/notch/reference',
             acquisition_eligibility='Must be checked against consolidated manifest before biological LFP analysis')
    (out/'metadata.json').write_text(json.dumps(d,indent=2)+'\n')
    return d


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('audit')
    a.add_argument('--paths', required=True, help='JSON list of paths or objects with raw_path')
    a.add_argument('--output', type=Path, required=True)
    a.add_argument('--window-seconds', type=float, default=4)
    a.add_argument('--pilot', action='store_true', help='Save each recording midpoint at1kHz')
    e = sub.add_parser('export')
    e.add_argument('--raw', required=True)
    e.add_argument('--output', type=Path, required=True)
    e.add_argument('--start', type=float, default=0)
    e.add_argument('--duration', type=float)
    e.add_argument('--well')
    e.add_argument('--target-hz', type=float, default=1000)
    e.add_argument('--manifest', type=Path, help='Require raw path to be a preferred LFP original in this CSV')
    args = p.parse_args()
    if args.command == 'export':
        if args.manifest:
            with args.manifest.open(newline='') as f:
                approved = {str(Path(r['raw_path']).resolve()) for r in csv.DictReader(f)
                            if r.get('preferred_for_lfp', '').lower() == 'true'}
            if str(Path(args.raw).resolve()) not in approved:
                p.error('This source is not a preferred LFP original in the supplied manifest')
        d = export_voltage(args.raw,args.output,args.start,args.duration,args.well,args.target_hz)
        print(json.dumps({'output':str(args.output),'shape':d['output_shape']}))
        return
    args.output.mkdir(parents=True,exist_ok=True)
    inputs = json.loads(Path(args.paths).read_text())
    summaries, all_wells = [], []
    for i,item in enumerate(inputs):
        path = item if isinstance(item,str) else item['raw_path']
        out = args.output/f'recording_{i+1:03d}'
        out.mkdir(exist_ok=True)
        try:
            d,rows = audit_file(path,out,args.window_seconds,args.pilot)
            all_wells.extend(rows)
            summary=dict(raw_path=path,artifact_dir=str(out),status=d['signal_check'],
                         error='',duration_s=d['duration_s'],channels=d['channels'],
                         sampling_hz=d['sampling_hz'],voltage_scale_v_per_count=d['voltage_scale_v_per_count'],
                         flags=';'.join(d['qc_flags']))
        except Exception as exc:
            summary=dict(raw_path=path,artifact_dir=str(out),status='failed',error=str(exc),
                         duration_s='',channels='',sampling_hz='',voltage_scale_v_per_count='',flags='')
        summaries.append(summary)
        write_csv(args.output/'recording_qc.csv',summaries)
        write_csv(args.output/'all_well_qc.csv',all_wells)
        print(json.dumps(summary),flush=True)
    if any(x['status']=='failed' for x in summaries):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
