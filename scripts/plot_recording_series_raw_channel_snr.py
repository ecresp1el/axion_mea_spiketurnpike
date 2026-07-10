#!/usr/bin/env python
"""Rank stable high-SNR raw channels across repeated MEA recordings."""

from __future__ import annotations

import argparse
import json
import math
import re
import shlex
import subprocess
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams.update(
    {
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Nimbus Sans", "Helvetica", "DejaVu Sans"],
    }
)

import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np
import pandas as pd


PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
RESULTS_ROOT = PROJECT_ROOT / "results" / "aind"
DEFAULT_OUTPUT_ROOT = (
    PROJECT_ROOT
    / "jobs"
    / "step1_nonlfp_th5_v5_ground_truth_latest"
    / "transient_plateing_raw_channel_snr_20260709"
)
DEFAULT_RAW_METADATA_CSV = (
    PROJECT_ROOT
    / "jobs"
    / "axion_file_ground_truth_20260708_filter_metadata_patch"
    / "raw_files.csv"
)
DEFAULT_PATTERN = (
    "step1_nonlfp_th5_*Testing_mea_transient_plateing_134-0150_"
    "My_Experiment(*)_primary_Neural_Spikes_hp_200_Hz_IIR_lp_3_kHz_Kaiser_Window"
)
DEFAULT_WELLS = "A1,A2,A3,B1,B2,B3"
DEFAULT_DATE_LABEL = "20260709_raw_snr"
DEFAULT_BINARY_ROOT = PROJECT_ROOT / "data" / "interim" / "kilosort_binary"


@dataclass(frozen=True)
class RecordingEntry:
    repeat: str
    well: str
    root: Path
    analyzer_path: Path
    binary_export_dir: Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=RESULTS_ROOT)
    parser.add_argument("--recording-pattern", default=DEFAULT_PATTERN)
    parser.add_argument("--wells", default=DEFAULT_WELLS)
    parser.add_argument("--include-repeats", default="")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--raw-metadata-csv", type=Path, default=DEFAULT_RAW_METADATA_CSV)
    parser.add_argument("--binary-root", type=Path, default=DEFAULT_BINARY_ROOT)
    parser.add_argument("--reference-repeat", default="000")
    parser.add_argument(
        "--plating-anchor-repeat",
        default="001",
        help="Repeat whose acquisition start approximates plating time for elapsed-time labels.",
    )
    parser.add_argument("--stats-sample-stride", type=int, default=25)
    parser.add_argument("--stats-chunk-samples", type=int, default=1_250_000)
    parser.add_argument("--plot-max-bins", type=int, default=2400)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-repeats", type=int, default=3)
    parser.add_argument("--min-snr", type=float, default=4.0)
    parser.add_argument("--min-abs-envelope-uV", type=float, default=12.0)
    parser.add_argument("--submit", action="store_true", help="Prepare and submit a Slurm job instead of running analysis now.")
    parser.add_argument("--sbatch-time", default="01:30:00")
    parser.add_argument("--export-formats", default="png,pdf,svg")
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.submit:
        submit_path = write_sbatch(args, output_dir)
        result = subprocess.run(["sbatch", "--parsable", str(submit_path)], check=False, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"sbatch failed: {result.stderr.strip()}")
        submission = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "submitted": True,
            "job_id": result.stdout.strip(),
            "sbatch": str(submit_path),
            "output_dir": str(output_dir),
        }
        (output_dir / "submission.json").write_text(json.dumps(submission, indent=2) + "\n", encoding="utf-8")
        print(f"Submitted raw-channel SNR job: {submission['job_id']}")
        print(f"Output dir: {output_dir}")
        return 0

    import spikeinterface.full as si

    wells = parse_list(args.wells)
    include_repeats = {item.zfill(3) for item in parse_list(args.include_repeats)}
    root_rows = discover_recording_roots(args.results_root.expanduser(), args.recording_pattern)
    if include_repeats:
        root_rows = [row for row in root_rows if row["repeat"] in include_repeats]
    entries = [
        RecordingEntry(
            repeat=row["repeat"],
            well=well,
            root=row["root"],
            analyzer_path=row["root"] / well / "postprocessed" / "block0_None_recording1.zarr",
            binary_export_dir=args.binary_root.expanduser() / row["root"].name / well,
        )
        for row in root_rows
        for well in wells
    ]
    metadata = raw_recording_metadata_by_repeat(
        args.raw_metadata_csv.expanduser(),
        sorted(
            {entry.repeat for entry in entries}
            | {str(args.reference_repeat).zfill(3), str(args.plating_anchor_repeat).zfill(3)}
        ),
    )
    plating_time = metadata.get(str(args.plating_anchor_repeat).zfill(3), {}).get("block_vector_start_time")
    stats_rows = []
    availability_rows = []
    envelope_cache: dict[tuple[str, str, int], dict[str, np.ndarray]] = {}
    for entry in entries:
        availability = {
            "repeat": entry.repeat,
            "well": entry.well,
            "recording_root": str(entry.root),
            "analyzer_path": str(entry.analyzer_path),
            "analyzer_exists": entry.analyzer_path.exists(),
            "binary_manifest": str(entry.binary_export_dir / "binary_export_manifest.json"),
            "status": "missing_recording_source",
        }
        try:
            recording, source_kind, source_path = load_recording_with_fallback(si, entry)
            rows, envelopes = summarize_recording_channels(recording, entry, metadata, args)
            stats_rows.extend(rows)
            envelope_cache.update(envelopes)
            availability.update(
                {
                    "status": "usable",
                    "source_kind": source_kind,
                    "source_path": str(source_path),
                    "sampling_frequency_hz": float(recording.get_sampling_frequency()),
                    "duration_s": float(recording.get_total_duration()),
                    "num_channels": int(recording.get_num_channels()),
                    "channel_ids": ";".join(str(item) for item in recording.get_channel_ids()),
                }
            )
        except Exception as exc:  # noqa: BLE001
            availability.update({"status": "load_failed", "error": f"{type(exc).__name__}: {exc}"})
        availability_rows.append(availability)

    availability_df = pd.DataFrame(availability_rows).sort_values(["well", "repeat"])
    channel_stats_df = pd.DataFrame(stats_rows)
    if channel_stats_df.empty:
        raise RuntimeError("No channel statistics were produced.")
    ranked_df = rank_channels(channel_stats_df, min_repeats=args.min_repeats)
    ranked_df["passes_strict_display_threshold"] = (
        (ranked_df["min_snr"] >= float(args.min_snr))
        & (ranked_df["min_abs_envelope_uV"] >= float(args.min_abs_envelope_uV))
    )
    selected_df = select_top_channels(ranked_df, int(args.top_n))

    availability_path = output_dir / f"transient_plateing_raw_channel_availability_{args.date_label}.csv"
    stats_path = output_dir / f"transient_plateing_raw_channel_repeat_stats_{args.date_label}.csv"
    ranked_path = output_dir / f"transient_plateing_raw_channel_ranked_summary_{args.date_label}.csv"
    selected_path = output_dir / f"transient_plateing_raw_channel_top{int(args.top_n)}_{args.date_label}.csv"
    availability_df.to_csv(availability_path, index=False)
    channel_stats_df.to_csv(stats_path, index=False)
    ranked_df.to_csv(ranked_path, index=False)
    selected_df.to_csv(selected_path, index=False)

    figure_paths = render_summary_figure(
        selected_df, channel_stats_df, availability_df, envelope_cache, plating_time, output_dir, args
    )
    per_well_outputs = {}
    for well in wells:
        well_ranked = ranked_df.loc[ranked_df["well"].astype(str).eq(str(well))].copy()
        well_selected = select_top_channels(well_ranked, int(args.top_n), local_rank_name="well_rank")
        well_selected_path = output_dir / (
            f"transient_plateing_raw_channel_{well}_top{int(args.top_n)}_{args.date_label}.csv"
        )
        well_selected.to_csv(well_selected_path, index=False)
        well_figure_paths = render_summary_figure(
            well_selected,
            channel_stats_df.loc[channel_stats_df["well"].astype(str).eq(str(well))],
            availability_df.loc[availability_df["well"].astype(str).eq(str(well))],
            envelope_cache,
            plating_time,
            output_dir,
            args,
            scope_slug=str(well),
            title=f"{well}: top {int(args.top_n)} raw channels across repeated recordings",
        )
        figure_paths.extend(well_figure_paths)
        per_well_outputs[str(well)] = {
            "selected_top": str(well_selected_path),
            "figures": [str(path) for path in well_figure_paths],
        }
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "analysis_lane": "raw_channel_snr_fallback_no_unit_tracking",
        "data_source": (
            "Current Step 1 analyzer.recording traces exported from the Axion raw files; "
            "no spike sorting labels, units, spike trains, templates, or Kilosort metrics are used for scoring."
        ),
        "recording_pattern": args.recording_pattern,
        "wells": wells,
        "include_repeats": sorted(include_repeats),
        "stats_definition": {
            "robust_noise_uV": "MAD(sampled voltage) / 0.67448975 after median centering",
            "abs_envelope_uV": "max(abs(p0.1), abs(p99.9)) from uniformly sampled full-recording trace",
            "snr": "abs_envelope_uV / robust_noise_uV",
            "ranking": "prioritizes high minimum SNR, high median SNR, high minimum amplitude envelope, and low across-repeat CV",
            "full_extrema": "per-repeat full-trace min/max are tracked chunkwise as artifact/context fields, not as the primary SNR numerator",
        },
        "outputs": {
            "availability": str(availability_path),
            "repeat_channel_stats": str(stats_path),
            "ranked_summary": str(ranked_path),
            "selected_top": str(selected_path),
            "figures": [str(path) for path in figure_paths],
            "per_well": per_well_outputs,
        },
    }
    provenance_path = output_dir / f"transient_plateing_raw_channel_snr_provenance_{args.date_label}.json"
    provenance_path.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print("Raw-channel SNR stability analysis complete")
    print(f"Output dir: {output_dir}")
    print(f"Ranked channels: {len(ranked_df)}")
    print(f"Selected channels: {len(selected_df)}")
    for path in figure_paths:
        print(f"Figure: {path}")
    return 0


def write_sbatch(args, output_dir: Path) -> Path:
    repro_dir = output_dir / "repro"
    logs_dir = output_dir / "logs"
    repro_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [
        "python",
        "scripts/plot_recording_series_raw_channel_snr.py",
        "--results-root",
        str(args.results_root.expanduser()),
        "--recording-pattern",
        args.recording_pattern,
        "--wells",
        args.wells,
        "--include-repeats",
        args.include_repeats,
        "--output-dir",
        str(output_dir),
        "--date-label",
        args.date_label,
        "--raw-metadata-csv",
        str(args.raw_metadata_csv.expanduser()),
        "--binary-root",
        str(args.binary_root.expanduser()),
        "--reference-repeat",
        str(args.reference_repeat),
        "--plating-anchor-repeat",
        str(args.plating_anchor_repeat),
        "--stats-sample-stride",
        str(args.stats_sample_stride),
        "--stats-chunk-samples",
        str(args.stats_chunk_samples),
        "--plot-max-bins",
        str(args.plot_max_bins),
        "--top-n",
        str(args.top_n),
        "--min-repeats",
        str(args.min_repeats),
        "--min-snr",
        str(args.min_snr),
        "--min-abs-envelope-uV",
        str(args.min_abs_envelope_uV),
        "--export-formats",
        args.export_formats,
    ]
    (repro_dir / "python_command.sh").write_text(" ".join(shlex.quote(item) for item in cmd) + "\n", encoding="utf-8")
    sbatch_path = repro_dir / "raw_channel_snr.sbatch"
    template = f"""#!/usr/bin/env bash
#SBATCH --job-name=raw_channel_snr
#SBATCH --account=parent0
#SBATCH --partition=standard
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time={args.sbatch_time}
#SBATCH --output={logs_dir}/raw_channel_snr_%j.out
#SBATCH --error={logs_dir}/raw_channel_snr_%j.err

set -eo pipefail

REPO_ROOT={shlex.quote(str(repo_root))}
PROJECT_CONFIG="${{REPO_ROOT}}/config/greatlakes_project.env"
source "${{PROJECT_CONFIG}}"
source "${{CONDA_BASE}}/etc/profile.d/conda.sh"
conda activate "${{CONDA_ENV}}"
cd "${{REPO_ROOT}}"
{" ".join(shlex.quote(item) for item in cmd)}
"""
    sbatch_path.write_text(template, encoding="utf-8")
    sbatch_path.chmod(0o755)
    return sbatch_path


def discover_recording_roots(results_root: Path, pattern: str) -> list[dict[str, object]]:
    rows = []
    for root in sorted(results_root.glob(pattern)):
        match = re.search(r"My_Experiment\((\d+)\)", root.name)
        if match:
            rows.append({"repeat": match.group(1), "root": root})
    return sorted(rows, key=lambda row: row["repeat"])


def parse_list(text: str) -> list[str]:
    return [item.strip() for item in str(text).split(",") if item.strip()]


def load_recording_with_fallback(si, entry: RecordingEntry):
    """Load an analyzer recording, or reconstruct it from its exported Axion binary."""
    if entry.analyzer_path.exists():
        analyzer = si.load_sorting_analyzer(entry.analyzer_path, load_extensions=False)
        return analyzer.recording, "sorting_analyzer", entry.analyzer_path

    manifest_path = entry.binary_export_dir / "binary_export_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Neither analyzer {entry.analyzer_path} nor binary manifest {manifest_path} exists"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    binary_path = Path(manifest["output_bin"])
    mapping_path = Path(manifest["channel_mapping_csv"])
    if not binary_path.exists() or not mapping_path.exists():
        raise FileNotFoundError(
            f"Binary fallback is incomplete: binary={binary_path.exists()}, mapping={mapping_path.exists()}"
        )
    gain_to_uV = float(manifest["voltage_scale_v_per_sample"]) * 1e6
    recording = si.read_binary(
        binary_path,
        sampling_frequency=float(manifest["fs"]),
        dtype=str(manifest["dtype"]),
        num_channels=int(manifest["n_chan_bin"]),
        gain_to_uV=gain_to_uV,
        offset_to_uV=0.0,
        is_filtered=True,
    )
    mapping = pd.read_csv(mapping_path).sort_values("channel_index_zero_based")
    if len(mapping) != recording.get_num_channels():
        raise ValueError(
            f"Channel mapping has {len(mapping)} rows but binary has {recording.get_num_channels()} channels"
        )
    recording.set_channel_locations(mapping[["x_um", "y_um"]].to_numpy(dtype=float))
    expected_samples = int(manifest["n_samples"])
    if recording.get_num_samples() != expected_samples:
        raise ValueError(
            f"Binary has {recording.get_num_samples()} samples; manifest declares {expected_samples}"
        )
    return recording, "axion_binary_export_fallback", binary_path


def summarize_recording_channels(recording, entry: RecordingEntry, metadata: dict[str, dict[str, object]], args) -> tuple[list[dict[str, object]], dict[tuple[str, str, int], dict[str, np.ndarray]]]:
    fs = float(recording.get_sampling_frequency())
    n_samples = int(recording.get_num_samples(segment_index=0))
    channel_ids = list(recording.get_channel_ids())
    n_channels = len(channel_ids)
    locations = np.asarray(recording.get_channel_locations(), dtype=float)
    sampled_chunks = []
    full_min = np.full(n_channels, np.inf, dtype=float)
    full_max = np.full(n_channels, -np.inf, dtype=float)
    full_sum = np.zeros(n_channels, dtype=float)
    full_sum_sq = np.zeros(n_channels, dtype=float)
    full_count = 0
    envelope_bins = init_envelope_bins(n_samples, int(args.plot_max_bins))
    envelope_min = np.full((len(envelope_bins) - 1, n_channels), np.inf, dtype=float)
    envelope_max = np.full((len(envelope_bins) - 1, n_channels), -np.inf, dtype=float)
    envelope_sum = np.zeros((len(envelope_bins) - 1, n_channels), dtype=float)
    envelope_count = np.zeros(len(envelope_bins) - 1, dtype=np.int64)

    chunk_size = max(10_000, int(args.stats_chunk_samples))
    stride = max(1, int(args.stats_sample_stride))
    for start in range(0, n_samples, chunk_size):
        stop = min(n_samples, start + chunk_size)
        trace = np.asarray(
            recording.get_traces(segment_index=0, start_frame=start, end_frame=stop, return_in_uV=True),
            dtype=np.float32,
        )
        if trace.ndim != 2 or trace.shape[1] != n_channels:
            continue
        sampled_chunks.append(trace[::stride].astype(np.float32, copy=False))
        full_min = np.minimum(full_min, np.nanmin(trace, axis=0))
        full_max = np.maximum(full_max, np.nanmax(trace, axis=0))
        full_sum += np.nansum(trace, axis=0)
        full_sum_sq += np.nansum(trace.astype(np.float64) ** 2, axis=0)
        full_count += trace.shape[0]
        update_envelope(trace, start, envelope_bins, envelope_min, envelope_max, envelope_sum, envelope_count)

    sampled = np.concatenate(sampled_chunks, axis=0) if sampled_chunks else np.empty((0, n_channels), dtype=np.float32)
    rows = []
    meta = metadata.get(entry.repeat, {})
    start_time = meta.get("block_vector_start_time")
    for channel_index, channel_id in enumerate(channel_ids):
        values = sampled[:, channel_index].astype(float) if sampled.size else np.asarray([], dtype=float)
        values = values[np.isfinite(values)]
        median_uV = float(np.nanmedian(values)) if values.size else np.nan
        centered = values - median_uV if values.size else values
        mad = float(np.nanmedian(np.abs(centered))) if values.size else np.nan
        robust_noise = mad / 0.67448975 if np.isfinite(mad) and mad > 0 else np.nan
        p001, p01, p1, p50, p99, p999 = percentiles(values, [0.01, 0.1, 1, 50, 99, 99.9])
        abs_envelope = float(max(abs(p01), abs(p999))) if np.isfinite(p01) and np.isfinite(p999) else np.nan
        ptp_envelope = float(p999 - p01) if np.isfinite(p01) and np.isfinite(p999) else np.nan
        snr = float(abs_envelope / robust_noise) if np.isfinite(abs_envelope) and np.isfinite(robust_noise) and robust_noise > 0 else np.nan
        rms = float(math.sqrt(max(full_sum_sq[channel_index] / max(full_count, 1), 0.0))) if full_count else np.nan
        location = locations[channel_index] if locations.ndim == 2 and channel_index < locations.shape[0] else [np.nan, np.nan]
        rows.append(
            {
                "repeat": entry.repeat,
                "well": entry.well,
                "analyzer_path": str(entry.analyzer_path),
                "channel_index": channel_index,
                "channel_id": channel_id,
                "channel_x_um": float(location[0]),
                "channel_y_um": float(location[1]),
                "sampling_frequency_hz": fs,
                "duration_s": float(n_samples / fs) if fs > 0 else np.nan,
                "source_sample_count": n_samples,
                "sampled_point_count_for_percentiles": int(values.size),
                "sample_stride": stride,
                "median_uV": median_uV,
                "robust_noise_uV": robust_noise,
                "rms_uV": rms,
                "p00_01_uV": p001,
                "p00_1_uV": p01,
                "p01_uV": p1,
                "p50_uV": p50,
                "p99_uV": p99,
                "p99_9_uV": p999,
                "abs_envelope_uV": abs_envelope,
                "ptp_0p1_99p9_uV": ptp_envelope,
                "snr": snr,
                "full_min_uV": float(full_min[channel_index]),
                "full_max_uV": float(full_max[channel_index]),
                "block_vector_start_time": start_time,
                "raw_file": meta.get("raw_file", ""),
                "filter_metadata_signature": meta.get("filter_metadata_signature", ""),
            }
        )
    envelopes = {}
    time_s = envelope_time_s(envelope_bins, fs)
    for channel_index, channel_id in enumerate(channel_ids):
        valid = envelope_count > 0
        mean = np.full(envelope_count.shape, np.nan, dtype=float)
        mean[valid] = envelope_sum[valid, channel_index] / envelope_count[valid]
        envelopes[(entry.repeat, entry.well, int(channel_index))] = {
            "time_s": time_s,
            "min_uV": envelope_min[:, channel_index],
            "max_uV": envelope_max[:, channel_index],
            "mean_uV": mean,
            "count": envelope_count,
            "channel_id": np.asarray([channel_id]),
        }
    return rows, envelopes


def init_envelope_bins(n_samples: int, max_bins: int) -> np.ndarray:
    max_bins = max(100, int(max_bins))
    n_bins = min(max_bins, max(n_samples, 1))
    edges = np.linspace(0, n_samples, n_bins + 1, dtype=np.int64)
    edges = np.unique(edges)
    if edges[-1] != n_samples:
        edges = np.append(edges, n_samples)
    return edges


def update_envelope(
    trace: np.ndarray,
    chunk_start: int,
    edges: np.ndarray,
    envelope_min: np.ndarray,
    envelope_max: np.ndarray,
    envelope_sum: np.ndarray,
    envelope_count: np.ndarray,
) -> None:
    chunk_stop = chunk_start + trace.shape[0]
    first_bin = max(0, int(np.searchsorted(edges, chunk_start, side="right") - 1))
    last_bin = min(len(edges) - 2, int(np.searchsorted(edges, chunk_stop, side="left")))
    for bin_index in range(first_bin, last_bin + 1):
        left = max(chunk_start, int(edges[bin_index]))
        right = min(chunk_stop, int(edges[bin_index + 1]))
        if right <= left:
            continue
        local = trace[left - chunk_start : right - chunk_start]
        envelope_min[bin_index] = np.minimum(envelope_min[bin_index], np.nanmin(local, axis=0))
        envelope_max[bin_index] = np.maximum(envelope_max[bin_index], np.nanmax(local, axis=0))
        envelope_sum[bin_index] += np.nansum(local, axis=0)
        envelope_count[bin_index] += local.shape[0]


def envelope_time_s(edges: np.ndarray, fs: float) -> np.ndarray:
    centers = 0.5 * (edges[:-1] + edges[1:] - 1)
    return centers / fs if fs > 0 else centers


def percentiles(values: np.ndarray, qs: list[float]) -> list[float]:
    if values.size == 0:
        return [np.nan] * len(qs)
    return [float(item) for item in np.nanpercentile(values, qs)]


def rank_channels(stats_df: pd.DataFrame, *, min_repeats: int) -> pd.DataFrame:
    rows = []
    for (well, channel_index), group in stats_df.groupby(["well", "channel_index"], sort=False):
        group = group.sort_values("repeat")
        snr = group["snr"].to_numpy(dtype=float)
        abs_env = group["abs_envelope_uV"].to_numpy(dtype=float)
        noise = group["robust_noise_uV"].to_numpy(dtype=float)
        rows.append(
            {
                "rank": np.nan,
                "well": well,
                "channel_index": int(channel_index),
                "channel_id": group["channel_id"].iloc[0],
                "channel_x_um": group["channel_x_um"].iloc[0],
                "channel_y_um": group["channel_y_um"].iloc[0],
                "repeat_count": int(group["repeat"].nunique()),
                "repeats": ";".join(group["repeat"].astype(str)),
                "median_snr": finite_median(snr),
                "min_snr": finite_min(snr),
                "snr_cv": coeff_var(snr),
                "median_abs_envelope_uV": finite_median(abs_env),
                "min_abs_envelope_uV": finite_min(abs_env),
                "abs_envelope_cv": coeff_var(abs_env),
                "median_noise_uV": finite_median(noise),
                "noise_cv": coeff_var(noise),
                "snr_values": ";".join(format_float(value) for value in snr),
                "abs_envelope_uV_values": ";".join(format_float(value) for value in abs_env),
                "robust_noise_uV_values": ";".join(format_float(value) for value in noise),
            }
        )
    ranked = pd.DataFrame(rows)
    if ranked.empty:
        return ranked
    ranked["raw_channel_stability_score"] = (
        1.8 * ranked["min_snr"].fillna(0.0)
        + 0.7 * ranked["median_snr"].fillna(0.0)
        + 0.035 * ranked["min_abs_envelope_uV"].fillna(0.0)
        + 0.01 * ranked["median_abs_envelope_uV"].fillna(0.0)
        - 2.8 * ranked["snr_cv"].fillna(3.0)
        - 2.0 * ranked["abs_envelope_cv"].fillna(3.0)
        - 1.2 * ranked["noise_cv"].fillna(3.0)
    )
    ranked["passes_min_repeat_count"] = ranked["repeat_count"] >= int(min_repeats)
    ranked = ranked.sort_values(
        ["passes_min_repeat_count", "raw_channel_stability_score", "min_snr", "min_abs_envelope_uV"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)
    ranked["rank"] = np.arange(1, len(ranked) + 1)
    return ranked


def select_top_channels(
    ranked_df: pd.DataFrame,
    top_n: int,
    *,
    local_rank_name: str | None = None,
) -> pd.DataFrame:
    """Select strict-pass channels first, then fill remaining slots by score order."""
    strict_df = ranked_df.loc[ranked_df["passes_strict_display_threshold"]].head(int(top_n))
    if len(strict_df) < int(top_n):
        filler_df = ranked_df.loc[~ranked_df.index.isin(strict_df.index)].head(int(top_n) - len(strict_df))
        selected = pd.concat([strict_df, filler_df], ignore_index=True)
    else:
        selected = strict_df.copy()
    selected = selected.sort_values("rank").reset_index(drop=True)
    if local_rank_name is not None:
        selected.insert(0, "global_rank", selected["rank"].astype(int))
        selected["rank"] = np.arange(1, len(selected) + 1)
        selected.insert(1, local_rank_name, selected["rank"].astype(int))
    return selected


def finite_median(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return float(np.nanmedian(values)) if values.size else np.nan


def finite_min(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return float(np.nanmin(values)) if values.size else np.nan


def coeff_var(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0 or float(np.nanmean(np.abs(values))) == 0:
        return np.nan
    return float(np.nanstd(values) / np.nanmean(np.abs(values)))


def format_float(value: float) -> str:
    return "nan" if not np.isfinite(value) else f"{value:.4g}"


def render_summary_figure(
    selected_df: pd.DataFrame,
    stats_df: pd.DataFrame,
    availability_df: pd.DataFrame,
    envelope_cache: dict[tuple[str, str, int], dict[str, np.ndarray]],
    plating_time: pd.Timestamp | None,
    output_dir: Path,
    args,
    *,
    scope_slug: str = "",
    title: str = "Raw channel SNR stability across repeated recordings",
) -> list[Path]:
    selected = selected_df.head(int(args.top_n)).copy()
    rows = max(1, len(selected))
    fig_height = max(9.0, 2.1 + 1.55 * rows)
    fig = plt.figure(figsize=(13.8, fig_height), constrained_layout=False)
    grid = GridSpec(rows + 1, 4, figure=fig, height_ratios=[0.45] + [1.0] * rows, width_ratios=[1.05, 1.15, 4.0, 0.9], hspace=0.56, wspace=0.32)
    fig.subplots_adjust(left=0.045, right=0.985, top=0.925, bottom=0.045)
    ax_note = fig.add_subplot(grid[0, :])
    draw_summary_note(ax_note, selected, availability_df, args)
    for row_index, row in enumerate(selected.to_dict("records"), start=1):
        well = str(row["well"])
        channel_index = int(row["channel_index"])
        group = stats_df.loc[(stats_df["well"].astype(str) == well) & (stats_df["channel_index"].astype(int) == channel_index)].sort_values("repeat")
        ax_metric = fig.add_subplot(grid[row_index, 0])
        draw_metric_panel(ax_metric, group, row)
        ax_amp = fig.add_subplot(grid[row_index, 1])
        draw_amplitude_panel(ax_amp, group)
        ax_trace = fig.add_subplot(grid[row_index, 2])
        draw_trace_stack_panel(ax_trace, group, envelope_cache, plating_time)
        ax_text = fig.add_subplot(grid[row_index, 3])
        draw_channel_text(ax_text, row)
    fig.suptitle(title, fontsize=15, fontweight="bold", y=0.975)
    scope_part = f"_{scope_slug}" if scope_slug else ""
    stem = f"transient_plateing_raw_channel{scope_part}_top{int(args.top_n)}_snr_stability_{args.date_label}"
    paths = []
    for fmt in [item.strip().lower() for item in str(args.export_formats).split(",") if item.strip()]:
        path = output_dir / f"{stem}.{fmt}"
        fig.savefig(path, dpi=240, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    return paths


def draw_summary_note(ax, selected: pd.DataFrame, availability_df: pd.DataFrame, args) -> None:
    ax.axis("off")
    usable = availability_df.loc[availability_df["status"].eq("usable")]
    missing = availability_df.loc[~availability_df["status"].eq("usable")]
    repeats = ";".join(sorted(usable["repeat"].astype(str).unique()))
    wells = ";".join(sorted(usable["well"].astype(str).unique()))
    text = (
        "Fallback lane: raw-channel voltage stability, no unit tracking. "
        "Rank score prioritizes large minimum SNR and large amplitude envelope across repeats, with penalties for across-repeat instability. "
        f"Usable repeats: {repeats or 'none'}; wells: {wells or 'none'}. "
        f"Unavailable analyzer rows: {len(missing)}. "
        f"Elapsed times use the start of source {str(args.plating_anchor_repeat).zfill(3)} as the estimated plating-time anchor. "
        "Each trace row shows a full-recording min/max envelope for the same physical channel across repeats; strict-pass channels are marked in the summary."
    )
    wrapped = "\n".join(textwrap.wrap(text, width=190))
    ax.text(0.0, 0.5, wrapped, ha="left", va="center", fontsize=10.2, linespacing=1.25)


def draw_metric_panel(ax, group: pd.DataFrame, row: dict[str, object]) -> None:
    repeats = group["repeat"].astype(str).to_list()
    snr = group["snr"].to_numpy(dtype=float)
    ax.plot(repeats, snr, marker="o", color="#0f6f72", lw=1.8, ms=4.8)
    ax.set_title(f"Rank {int(row['rank'])}: {row['well']} ch {row['channel_id']}", fontsize=9.2, loc="left")
    ax.set_ylabel("SNR")
    ax.grid(axis="y", color="0.88", lw=0.65)
    ax.spines[["top", "right"]].set_visible(False)


def draw_amplitude_panel(ax, group: pd.DataFrame) -> None:
    repeats = group["repeat"].astype(str).to_list()
    amp = group["abs_envelope_uV"].to_numpy(dtype=float)
    noise = group["robust_noise_uV"].to_numpy(dtype=float)
    ax.plot(repeats, amp, marker="o", color="#a44a3f", lw=1.8, ms=4.8, label="signal")
    ax.plot(repeats, noise, marker="o", color="#4b5563", lw=1.3, ms=4.0, label="noise")
    ax.set_ylabel("uV")
    ax.grid(axis="y", color="0.88", lw=0.65)
    ax.legend(frameon=False, fontsize=7.5, loc="best")
    ax.spines[["top", "right"]].set_visible(False)


def draw_trace_stack_panel(
    ax,
    group: pd.DataFrame,
    envelope_cache: dict[tuple[str, str, int], dict[str, np.ndarray]],
    plating_time: pd.Timestamp | None,
) -> None:
    all_values = []
    for record in group.to_dict("records"):
        env = envelope_cache.get((str(record["repeat"]), str(record["well"]), int(record["channel_index"])))
        if env is None:
            continue
        all_values.append(np.asarray(env["min_uV"], dtype=float))
        all_values.append(np.asarray(env["max_uV"], dtype=float))
    if all_values:
        low = float(np.nanmin([np.nanmin(values) for values in all_values if values.size]))
        high = float(np.nanmax([np.nanmax(values) for values in all_values if values.size]))
    else:
        low, high = -1.0, 1.0
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        low, high = -1.0, 1.0
    row_gap = (high - low) * 1.25
    colors = plt.cm.viridis(np.linspace(0.14, 0.86, len(group)))
    y_ticks = []
    y_labels = []
    for idx, (color, record) in enumerate(zip(colors, group.to_dict("records"), strict=True)):
        env = envelope_cache.get((str(record["repeat"]), str(record["well"]), int(record["channel_index"])))
        if env is None:
            continue
        offset = -idx * row_gap
        time_min = np.asarray(env["time_s"], dtype=float) / 60.0
        min_uV = np.asarray(env["min_uV"], dtype=float) + offset
        max_uV = np.asarray(env["max_uV"], dtype=float) + offset
        mean_uV = np.asarray(env["mean_uV"], dtype=float) + offset
        ax.fill_between(time_min, min_uV, max_uV, color=color, alpha=0.34, linewidth=0)
        ax.plot(time_min, mean_uV, color=color, lw=0.55, alpha=0.95)
        start_time = parse_timestamp_or_none(record.get("block_vector_start_time"))
        if start_time is not None:
            ax.text(
                0.006,
                offset + 0.40 * (high - low),
                f"start {start_time.strftime('%H:%M:%S')}",
                transform=ax.get_yaxis_transform(),
                ha="left",
                va="center",
                fontsize=6.3,
                color="0.25",
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 0.5},
            )
            if plating_time is not None and float(record.get("duration_s", 0.0)) >= 0:
                end_time = start_time + pd.to_timedelta(float(record["duration_s"]), unit="s")
                elapsed_s = float((end_time - plating_time).total_seconds())
                elapsed_label = format_elapsed_from_plating(elapsed_s)
                ax.text(
                    0.994,
                    offset + 0.40 * (high - low),
                    elapsed_label,
                    transform=ax.get_yaxis_transform(),
                    ha="right",
                    va="center",
                    fontsize=6.3,
                    fontweight="bold",
                    color="0.18",
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 0.5},
                )
        y_ticks.append(offset)
        y_labels.append(str(record["repeat"]))
    if group.shape[0] > 0:
        scale = nice_scale_value((high - low) * 0.35)
        x0 = ax.get_xlim()[1] if ax.get_xlim()[1] > ax.get_xlim()[0] else 1.0
        x_scale = x0 - 0.02 * max(x0, 1.0)
        y_scale = y_ticks[0] + low + 0.08 * (high - low)
        ax.plot([x_scale, x_scale], [y_scale, y_scale + scale], color="0.15", lw=1.1)
        ax.text(x_scale, y_scale + scale, f"{scale:g} uV", ha="right", va="bottom", fontsize=7.2)
    ax.set_xlabel("Minutes within recording")
    ax.set_ylabel("Repeat")
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_labels)
    ax.grid(axis="x", color="0.9", lw=0.55)
    ax.spines[["top", "right"]].set_visible(False)


def format_elapsed_from_plating(elapsed_s: float) -> str:
    before = elapsed_s < 0
    total_seconds = int(round(abs(elapsed_s)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    value = f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"ends {value} before plating" if before else f"end: total {value} since plating"


def draw_channel_text(ax, row: dict[str, object]) -> None:
    ax.axis("off")
    text = (
        f"min SNR {float(row['min_snr']):.2f}\n"
        f"median SNR {float(row['median_snr']):.2f}\n"
        f"min signal {float(row['min_abs_envelope_uV']):.1f} uV\n"
        f"SNR CV {float(row['snr_cv']):.2f}\n"
        f"score {float(row['raw_channel_stability_score']):.2f}\n"
        f"strict pass {'yes' if bool(row.get('passes_strict_display_threshold', False)) else 'no'}"
    )
    ax.text(0.0, 0.5, text, ha="left", va="center", fontsize=8.6, linespacing=1.25)


def nice_scale_value(value: float) -> float:
    if not np.isfinite(value) or value <= 0:
        return 10.0
    magnitude = 10 ** math.floor(math.log10(value))
    for multiplier in (1, 2, 5, 10):
        candidate = multiplier * magnitude
        if candidate >= value:
            return float(candidate)
    return float(10 * magnitude)


def raw_recording_metadata_by_repeat(raw_metadata_csv: Path, repeats: list[str]) -> dict[str, dict[str, object]]:
    if not raw_metadata_csv.exists():
        return {}
    try:
        df = pd.read_csv(raw_metadata_csv)
    except Exception:
        return {}
    if df.empty:
        return {}
    metadata = {}
    raw_name = df.get("raw_name", pd.Series([""] * len(df))).astype(str)
    raw_variant = df.get("raw_variant", pd.Series([""] * len(df))).astype(str)
    raw_file = df.get("raw_file", pd.Series([""] * len(df))).astype(str)
    logical_folder = df.get("logical_folder", pd.Series([""] * len(df))).astype(str)
    for repeat in repeats:
        expected_name = f"My Experiment({str(repeat).zfill(3)}).raw"
        mask = raw_name.eq(expected_name) & raw_variant.eq("primary_raw")
        if not mask.any():
            mask = raw_file.str.endswith(expected_name)
        rows = df.loc[mask].copy()
        if rows.empty:
            continue
        preferred = rows[
            logical_folder.loc[rows.index].str.contains("Testing_mea_transient_plateing", regex=False, na=False)
            & logical_folder.loc[rows.index].str.contains("134-0150", regex=False, na=False)
        ]
        row = (preferred if not preferred.empty else rows).iloc[0]
        metadata[str(repeat).zfill(3)] = {
            "raw_name": row.get("raw_name", ""),
            "raw_file": row.get("raw_file", ""),
            "block_vector_start_time": parse_timestamp_or_none(row.get("block_vector_start_time", "")),
            "filter_metadata_signature": row.get("filter_metadata_signature", ""),
        }
    return metadata


def parse_timestamp_or_none(value: object) -> pd.Timestamp | None:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    return timestamp


if __name__ == "__main__":
    raise SystemExit(main())
