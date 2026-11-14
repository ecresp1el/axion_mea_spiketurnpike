#!/usr/bin/env python3
"""Read-only signal review of failed MCS baseline attempts; PNGs and multipage PDF."""
from __future__ import annotations

import argparse
import csv
import json
import shlex
import shutil
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LogNorm
from matplotlib.collections import LineCollection
import numpy as np
from scipy.signal import butter, sosfiltfilt

from run_mcs_aind_batch import diagnose_recording


def load_json(path):
    return json.loads(Path(path).read_text())


def minmax_trace(x, y, bins=800):
    """Preserve extrema for display; do not thin signals by simple decimation."""
    step = max(1, len(y) // bins)
    n = len(y) // step * step
    if step == 1:
        return x, y
    blocks = y[:n].reshape(-1, step)
    low, high = blocks.argmin(1), blocks.argmax(1)
    indices = (np.arange(len(blocks))[:, None] * step + np.sort(np.c_[low, high], axis=1)).ravel()
    indices = np.r_[indices, np.arange(n, len(y))]
    return x[indices], y[indices]


def stacked(ax, data, fs, start, labels, title, events):
    centered = data - np.median(data, axis=0)
    peak = max(float(np.max(np.abs(centered))), 0.1)
    spacing = 2.2 * peak
    segments = []
    x = start + np.arange(len(data)) / fs
    for c in range(data.shape[1]):
        tx, yy = minmax_trace(x, centered[:, c])
        segments.append(np.c_[tx, yy + c * spacing])
    ax.add_collection(LineCollection(segments, colors='#174c70', linewidths=.45, rasterized=True))
    ax.set(xlim=(start, start + len(data) / fs), ylim=(-spacing, len(labels) * spacing),
           yticks=np.arange(len(labels)) * spacing, yticklabels=labels,
           xlabel='Seconds from recording start', title=title)
    ax.invert_yaxis()
    ax.tick_params(axis='y', labelsize=5, length=0)
    for event in events:
        if start <= event <= start + len(data) / fs:
            ax.axvline(event, color='#c05819', lw=.8, alpha=.8)
    ax.text(.99, .015, f'All channels: same scale; row spacing {spacing:.2f} µV',
            transform=ax.transAxes, ha='right', va='bottom', fontsize=7,
            bbox={'facecolor': 'white', 'alpha': .9, 'edgecolor': 'none'})
    for side in ('top', 'right', 'left'):
        ax.spines[side].set_visible(False)
    return peak


def recovered_recordings(project):
    recovered = {}
    for batch in sorted((project / 'jobs').glob('aind_mcs_fallback*')):
        ledger = batch / 'recordings.csv'
        if not ledger.exists():
            continue
        with ledger.open() as handle:
            for row in csv.DictReader(handle):
                report = Path(row.get('results_dir') or '.') / 'validation_summary.json'
                if row['status'] == 'completed' and report.is_file() and load_json(report).get('status') == 'passed':
                    recovered[row['recording_id']] = f"Later recovery validated: {row['unit_count']} clusters / {row['spike_count']} spikes"
    return recovered


def plot_recording(row, output, pdf, recovered):
    inputs = Path(row['input_dir'])
    manifest = load_json(inputs / 'mcs_recording_manifest.json')
    params = load_json(inputs / 'aind_params.json')
    reader = params['job_dispatch']['spikeinterface_info']['reader_kwargs']
    with (inputs / 'channels.csv').open() as handle:
        channels = sorted(csv.DictReader(handle), key=lambda c: int(c['binary_channel_index']))
    n, nc = int(manifest['sample_count']), int(manifest['signal_channel_count'])
    fs = float(manifest['sampling_frequency_hz'])
    if [int(c['binary_channel_index']) for c in channels] != list(range(nc)):
        raise ValueError('Channel mapping is not a complete ordered binary-channel map')
    if [c['channel_label'] for c in channels] != manifest['channel_labels']:
        raise ValueError('Channel identities differ between manifest and channel table')
    gains = np.broadcast_to(np.asarray(reader['gain_to_uV'], dtype=float), (nc,))
    offsets = np.broadcast_to(np.asarray(reader['offset_to_uV'], dtype=float), (nc,))
    if not np.allclose(gains, [float(c['gain_uv_per_count']) for c in channels]):
        raise ValueError('Channel gains differ between saved reader and channel table')
    binary = Path(manifest['binary_file'])
    dtype = np.dtype(manifest['binary_dtype'])
    if binary.stat().st_size != n * nc * dtype.itemsize:
        raise ValueError('Binary size does not match recording dimensions')
    raw = np.memmap(binary, dtype=dtype, mode='r', shape=(n, nc))
    # Full, contiguous coverage; each cell uses all samples in its time bin.
    chunk = round(fs)
    starts = np.arange(0, n, chunk)
    edges = np.r_[starts / fs, n / fs]
    rms = np.empty((len(starts), nc))
    constant = np.ones(nc, dtype=bool)
    for j, a in enumerate(starts):
        block = np.asarray(raw[a:min(a + chunk, n)], dtype=float) * gains + offsets
        rms[j] = block.std(axis=0)
        constant &= np.ptp(block, axis=0) == 0
    active_bin = int(np.argmax(np.median(rms, axis=1)))
    selected = int(starts[active_bin])
    end = min(selected + chunk, n)
    selected = max(0, end - chunk)
    active = np.asarray(raw[selected:end], dtype=float) * gains + offsets
    first = np.asarray(raw[:min(chunk, n)], dtype=float) * gains + offsets
    # Read filter margins and crop, rather than filtering a displayed snippet alone.
    margin = round(.2 * fs)
    a, b = max(0, selected - margin), min(n, end + margin)
    context = np.asarray(raw[a:b], dtype=float) * gains + offsets
    sos = butter(3, [300, min(3000, fs * .45)], btype='bandpass', fs=fs, output='sos')
    filtered = sosfiltfilt(sos, context, axis=0)[selected-a:end-a]
    with (inputs / 'events.csv').open() as handle:
        events = [float(e['time_from_recording_start_s']) for e in csv.DictReader(handle)]
    diagnosis = diagnose_recording(row)
    labels = [c['channel_label'] for c in channels]
    geometry = manifest['geometry_status']
    verified = geometry == 'source_verified'
    x = np.array([float(c['x_um']) for c in channels])
    y = np.array([float(c['y_um']) for c in channels])
    pitch = float(manifest['sorting_pitch_um'])
    # Coordinates are plotted in provided channel-map orientation; never imply a plate photo.
    map_start = selected
    map_end = min(end, map_start + round(.5 * fs))
    mapped = np.asarray(raw[map_start:map_end], dtype=float) * gains + offsets
    centered = mapped - np.median(mapped, axis=0)
    map_peak = max(float(np.max(np.abs(centered))), .1)
    color_rms = mapped.std(axis=0)
    positive = color_rms[color_rms > 0]
    vmin = max(float(positive.min()) if len(positive) else .001, .001)
    vmax = max(float(color_rms.max()), vmin * 1.01)
    norm = LogNorm(vmin=vmin, vmax=vmax)
    fig = plt.figure(figsize=(22, 16), facecolor='white')
    gs = fig.add_gridspec(3, 2, width_ratios=[1.1, 1], height_ratios=[1, 1, .65],
                          left=.045, right=.97, bottom=.085, top=.845, wspace=.15, hspace=.27)
    map_ax = fig.add_subplot(gs[:2, 0])
    time = np.arange(len(mapped)) / fs
    colors = plt.cm.viridis(norm(np.maximum(color_rms, vmin)))
    for c, label in enumerate(labels):
        map_ax.add_patch(plt.Rectangle((x[c] - pitch*.43, y[c] - pitch*.4), pitch*.86, pitch*.8,
                                      facecolor=colors[c], alpha=.13, edgecolor='#b6c4cb', lw=.6))
        tx, yy = minmax_trace(time, centered[:, c], bins=300)
        xx = x[c] + (tx / .5 - .5) * pitch * .8
        yy = y[c] + yy / map_peak * pitch * .27
        map_ax.plot(xx, yy, color='#164866', lw=.5, rasterized=True)
        map_ax.text(x[c]-pitch*.37, y[c]+pitch*.29, label, fontsize=8, weight='bold', va='center')
    map_ax.set_aspect('equal')
    map_ax.set(xlim=(x.min()-pitch*.6, x.max()+pitch*.6), ylim=(y.max()+pitch*.6, y.min()-pitch*.6))
    map_ax.set_title(f'Electrode map + raw analog signal | {selected/fs:.3f}–{map_end/fs:.3f} s\n'
                     f'Every electrode, shared ±{map_peak:.2f} µV scale; each trace median-centered', fontsize=11, pad=15)
    if verified:
        map_ax.set(xlabel='Source channel-map x (µm)', ylabel='Source channel-map y (µm)')
    else:
        # Keep topology but remove physical-unit claims for assumed geometry.
        xt, yt = np.unique(x), np.unique(y)
        map_ax.set(xticks=xt, xticklabels=[str(i+1) for i in range(len(xt))],
                   yticks=yt, yticklabels=[str(i+1) for i in range(len(yt))],
                   xlabel='Assumed grid column (unverified geometry)', ylabel='Assumed grid row (unverified geometry)')
    scale = plt.cm.ScalarMappable(norm=norm, cmap='viridis')
    colorbar = fig.colorbar(scale, ax=map_ax, fraction=.025, pad=.02, shrink=.75)
    colorbar.set_label('Raw AC RMS in displayed map window (µV)', fontsize=8)
    stacked(fig.add_subplot(gs[0, 1]), first, fs, 0, labels,
            'Raw analog signal | first 1 second | all electrodes', events)
    stacked(fig.add_subplot(gs[1, 1]), filtered, fs, selected/fs, labels,
            f'300–3000 Hz view | {selected/fs:.3f}–{end/fs:.3f} s | all electrodes', events)
    heat = fig.add_subplot(gs[2, :])
    valid = rms[rms > 0]
    hvmin = max(float(np.percentile(valid, 2)) if valid.size else .001, .001)
    hvmax = max(float(rms.max()), hvmin*1.01)
    image = heat.pcolormesh(edges, np.arange(nc+1)-.5, np.maximum(rms.T, hvmin),
                            norm=LogNorm(hvmin, hvmax), cmap='viridis', rasterized=True)
    # Nominal unpadded batch windows; padding and isolation boundaries are not shaded.
    ks_batch = int(params['spikesorting']['kilosort4']['sorter']['batch_size'])
    for sample in range(0, n, ks_batch * 25):
        heat.axvspan(sample/fs, min(n, sample+ks_batch)/fs, color='#ef8b2c', alpha=.2, lw=.7, ec='#ef8b2c')
    for event in events:
        heat.axvline(event, color='#c93226', lw=.7, alpha=.7)
    heat.axvspan(selected/fs, end/fs, facecolor='none', edgecolor='#fc4eab', lw=1.7)
    heat.set(ylim=(nc-.5, -.5), xlim=(0,n/fs), xlabel='Seconds from recording start',
             ylabel='Electrode label', yticks=np.arange(0,nc,3), yticklabels=labels[::3])
    heat.tick_params(axis='y', labelsize=6)
    heat.set_title('Full recording | raw AC RMS, contiguous ≤1 s bins | orange: nominal training windows; '
                   'pink: selected signal window; red: source hardware events', fontsize=10)
    fig.colorbar(image, ax=heat, pad=.01, fraction=.015, label='µV RMS')
    snippets = diagnosis['training_snippets']
    group = row['recording_id'].split('/')
    fig.suptitle(f"MCS failed-attempt review | task {int(row['task_index']):02d} | {' / '.join(group[:-1])}\n{group[-1]}",
                 x=.045, y=.975, ha='left', fontsize=18, weight='bold')
    status = recovered.get(row['recording_id'], 'Original failure unresolved; no validated recovery found')
    subtitle = (f"{n/fs:g} s • {fs/1000:g} kHz • {nc} signal channels • training snippets: {snippets} • {status}\n"
                f"Geometry: {manifest.get('configured_mea_name') or 'unknown array model'} | {geometry} | "
                f"{'pitch ' + str(manifest.get('pitch_um')) + ' µm' if verified else 'spacing is an unverified computational assumption'} | "
                f"{manifest.get('recording_completeness', '')}")
    fig.text(.045,.92,subtitle,fontsize=10,va='top',color='#6f390a' if not verified else '#283c49')
    medians = np.median(mapped, axis=0)
    fig.text(.045,.035,
             f"Raw traces are calibrated input counts (µV), without digital filtering; display median removed per channel. "
             f"Map-window channel medians: {medians.min():.2f} to {medians.max():.2f} µV.\n"
             "Filtered view: illustrative zero-phase Butterworth bandpass, not Kilosort's internal whitening/filtering. "
             "Selected window: largest median channel raw AC RMS among ≤1 s bins; may highlight artifacts.\n"
             "Signal extrema are preserved when reducing plotted point counts. Map uses the saved channel coordinates; "
             "orientation is not independently registered to a photograph. No biological assignment inferred.",
             fontsize=8,va='bottom',color='#43515c')
    name = f"task_{int(row['task_index']):02d}_{group[-2]}_{group[-1]}"
    png = output / f'{name}.png'
    fig.savefig(png, dpi=150)
    pdf.savefig(fig, dpi=150)
    plt.close(fig)
    metrics = {'recording_id': row['recording_id'], 'task_index': int(row['task_index']),
               'figure': png.name, 'sample_count': n, 'sampling_frequency_hz': fs,
               'duration_s': n/fs, 'channel_count': nc, 'geometry_status': geometry,
               'training_snippets': snippets, 'later_status': status,
               'selected_start_s': selected/fs, 'selected_end_s': end/fs,
               'map_shared_peak_uv': map_peak, 'source_binary': str(binary),
               'channels_constant_within_every_one_second_bin': ','.join(np.array(labels)[constant]),
               'input_manifest': str(inputs/'mcs_recording_manifest.json')}
    del raw
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    plan = load_json(args.batch_dir / 'batch_manifest.json')
    args.output_dir = args.output_dir.expanduser().resolve()
    results_root = Path(plan['project_root']).resolve() / 'results'
    if not args.output_dir.is_relative_to(results_root):
        parser.error(f'Generated figures must live under the Great Lakes project results root: {results_root}')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    repro = args.output_dir / 'repro'
    repro.mkdir()
    shutil.copy2(__file__, repro / Path(__file__).name)
    config = Path(__file__).resolve().parents[1] / 'config/greatlakes_project.env'
    shutil.copy2(config, repro / 'project_config.env')
    (repro / 'python_command.sh').write_text('#!/usr/bin/env bash\n' + shlex.join([sys.executable, *sys.argv]) + '\n')
    with (args.batch_dir / 'recordings.csv').open() as handle:
        failed_ids = {r['recording_id'] for r in csv.DictReader(handle) if r['status']=='failed'}
    rows = sorted([r for r in plan['records'] if r['recording_id'] in failed_ids], key=lambda r:r['task_index'])
    if not rows:
        raise ValueError('No failed recordings in the saved ledger')
    (args.output_dir / 'run_manifest.json').write_text(json.dumps({
        'batch_dir': str(args.batch_dir.resolve()), 'output_dir': str(args.output_dir),
        'recording_ids': [r['recording_id'] for r in rows],
        'slurm_job_id': __import__('os').environ.get('SLURM_JOB_ID'),
        'command': [sys.executable, *sys.argv]}, indent=2) + '\n')
    recovered = recovered_recordings(Path(plan['project_root']))
    metrics = []
    with PdfPages(args.output_dir / 'failed_MCS_recordings.pdf') as pdf:
        for row in rows:
            print(f"Plotting task {row['task_index']}: {row['recording_id']}", flush=True)
            metrics.append(plot_recording(row, args.output_dir, pdf, recovered))
            (args.output_dir/'review_manifest.json').write_text(json.dumps(metrics, indent=2)+'\n')
    with (args.output_dir/'recording_index.csv').open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metrics[0]))
        writer.writeheader()
        writer.writerows(metrics)
    (args.output_dir/'README.txt').write_text(
        f'{len(metrics)} figures, one per failed baseline recording, ordered by original Slurm task.\n'
        'Open failed_MCS_recordings.pdf to browse all pages. Individual PNGs use the same layout.\n'
        'Includes original failures with subsequently validated recoveries, marked in each title.\n'
        'Only saved signal binaries and metadata were read. No sorting or source data were modified.\n'
        'See each figure for scale, centering, filter, window-selection, and geometry caveats.\n')
    print(f'Completed {len(metrics)} figures: {args.output_dir}', flush=True)


if __name__ == '__main__':
    main()
