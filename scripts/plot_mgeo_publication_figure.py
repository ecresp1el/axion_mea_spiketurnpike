#!/usr/bin/env python
"""Create the focused MGEO raw-voltage publication figure."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams.update(
    {
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 8,
        "axes.linewidth": 0.8,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "path.simplify": False,
        "agg.path.chunksize": 10000,
    }
)

import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from axion_mea.spontaneous_activity import (  # noqa: E402
    BurstDetectionParameters,
    count_burst_episodes,
    detect_negative_threshold_events,
    mean_pairwise_spike_time_tiling_coefficient,
    summarize_smoothed_inverse_isi_rate,
    summarize_unit_activity,
)


PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_STATS = (
    PROJECT_ROOT
    / "jobs/step1_nonlfp_th5_v5_ground_truth_latest/transient_plateing_raw_channel_snr_20260709"
    / "transient_plateing_raw_channel_repeat_stats_20260709_raw_snr.csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "jobs/step1_nonlfp_th5_v5_ground_truth_latest/transient_plateing_raw_channel_snr_20260709"
    / "publication_figure"
)
# The metadata start of source 000 is ~5 min after plating (user-provided setup timing).
RECORDING_000_START = pd.Timestamp("2026-05-23 10:08:59.034")
PLATING_TIME = RECORDING_000_START - pd.Timedelta(minutes=5)
REPEATS = ("000", "002", "003", "004")
PERSISTENCE_REPEATS = REPEATS
RAW_ACTIVITY_SNR_THRESHOLD = 5.0
SYNCHRONY_WINDOW_MS = 50.0
MUA_THRESHOLD_SIGMA = 5.0
MUA_REFRACTORY_PERIOD_MS = 1.0
MUA_CHUNK_DURATION_S = 60.0
MUA_MIN_SPIKES_FOR_SMOOTHED_RATE = 30
MUA_MIN_INTERBURST_INTERVAL_MS = 2000.0
SPATIAL_MGEO_REGIONS = {
    "A2-MGEOa": {"well": "A2", "channels": (4, 5, 6, 12, 13, 14)},
    "A2-MGEOb": {"well": "A2", "channels": (20, 21, 22, 28, 29)},
    "B2-MGEOa": {"well": "B2", "channels": (29, 30, 31, 36, 37, 38, 39)},
    "B2-MGEOb": {"well": "B2", "channels": (44, 45, 46, 53)},
}


@dataclass(frozen=True)
class Target:
    label: str
    well: str
    channel_id: int
    color: str


TARGETS = (
    Target("MGEO 1", "B2", 29, "#2878B5"),
    Target("MGEO 2", "A2", 28, "#D05A47"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stats-csv", type=Path, default=DEFAULT_STATS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--display-duration-min", type=float, default=10.0)
    parser.add_argument("--envelope-bins", type=int, default=1500)
    parser.add_argument("--sample-stride", type=int, default=25)
    parser.add_argument("--png-dpi", type=int, default=600)
    parser.add_argument("--export-formats", default="png,pdf,svg")
    parser.add_argument("--max-isi-ms", type=float, default=100.0)
    parser.add_argument("--min-spikes-per-burst", type=int, default=3)
    parser.add_argument("--min-burst-duration-ms", type=float, default=100.0)
    parser.add_argument("--synchrony-window-ms", type=float, default=SYNCHRONY_WINDOW_MS)
    parser.add_argument("--mua-threshold-sigma", type=float, default=MUA_THRESHOLD_SIGMA)
    parser.add_argument("--mua-refractory-ms", type=float, default=MUA_REFRACTORY_PERIOD_MS)
    parser.add_argument(
        "--mua-min-interburst-interval-ms",
        type=float,
        default=MUA_MIN_INTERBURST_INTERVAL_MS,
    )
    parser.add_argument("--mua-chunk-duration-s", type=float, default=MUA_CHUNK_DURATION_S)
    parser.add_argument(
        "--mua-min-spikes-for-smoothed-rate",
        type=int,
        default=MUA_MIN_SPIKES_FOR_SMOOTHED_RATE,
    )
    args = parser.parse_args()

    import spikeinterface.full as si

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stats = pd.read_csv(args.stats_csv.expanduser(), dtype={"repeat": str})
    stats["repeat"] = stats["repeat"].str.zfill(3)

    trace_data = {}
    metric_rows = []
    for target in TARGETS:
        rows = stats.loc[
            stats["well"].astype(str).eq(target.well)
            & pd.to_numeric(stats["channel_id"], errors="coerce").eq(target.channel_id)
            & stats["repeat"].isin(REPEATS)
        ].sort_values("repeat")
        if tuple(rows["repeat"]) != REPEATS:
            raise RuntimeError(f"Missing requested recordings for {target.label}: found {tuple(rows['repeat'])}")
        for row in rows.to_dict("records"):
            analyzer = si.load_sorting_analyzer(Path(row["analyzer_path"]), load_extensions=False)
            recording = analyzer.recording.select_channels([target.channel_id])
            summary = summarize_display_window(
                recording,
                duration_s=float(args.display_duration_min) * 60.0,
                envelope_bins=int(args.envelope_bins),
                sample_stride=int(args.sample_stride),
            )
            start = pd.to_datetime(row["block_vector_start_time"])
            displayed_end = start + pd.to_timedelta(summary["duration_s"], unit="s")
            elapsed_end_min = float((displayed_end - PLATING_TIME).total_seconds() / 60.0)
            summary.update(
                {
                    "label": target.label,
                    "well": target.well,
                    "channel_id": target.channel_id,
                    "repeat": row["repeat"],
                    "analyzer_path": row["analyzer_path"],
                    "source_start": start,
                    "elapsed_end_min": elapsed_end_min,
                }
            )
            trace_data[(target.label, row["repeat"])] = summary
            metric_rows.append(
                {
                    key: value
                    for key, value in summary.items()
                    if key
                    not in {
                        "time_min",
                        "minimum_uV",
                        "maximum_uV",
                        "mean_uV",
                    }
                }
            )

    metrics = pd.DataFrame(metric_rows)
    pooled_metrics, pooled_points, persistent_channels = build_pooled_snr(stats)
    burst_parameters = BurstDetectionParameters(
        max_isi_ms=float(args.max_isi_ms),
        min_spikes=int(args.min_spikes_per_burst),
        min_duration_ms=float(args.min_burst_duration_ms),
    )
    burst_parameters.validate()
    channel_activity, region_activity, pooled_activity = build_raw_channel_activity(
        stats,
        burst_parameters=burst_parameters,
        synchrony_window_ms=float(args.synchrony_window_ms),
        threshold_sigma=float(args.mua_threshold_sigma),
        refractory_period_ms=float(args.mua_refractory_ms),
        min_interburst_interval_ms=float(args.mua_min_interburst_interval_ms),
        chunk_duration_s=float(args.mua_chunk_duration_s),
        min_spikes_for_smoothed_rate=int(args.mua_min_spikes_for_smoothed_rate),
    )
    base_stem = "transient_plating_MGEO1_MGEO2_raw_channel_stability_temporal_SEM_20260710"
    figure_paths = []
    figure = render_figure(
        trace_data,
        metrics,
        float(args.display_duration_min),
        pooled_metrics=pooled_metrics,
        pooled_points=pooled_points,
        region_activity=region_activity,
        pooled_activity=pooled_activity,
    )
    for fmt in [item.strip().lower() for item in args.export_formats.split(",") if item.strip()]:
        path = output_dir / f"{base_stem}.{fmt}"
        figure.savefig(path, dpi=int(args.png_dpi) if fmt == "png" else 1200, bbox_inches="tight")
        figure_paths.append(path)
    plt.close(figure)

    metrics_path = output_dir / f"{base_stem}_temporal_window_metrics.csv"
    metrics.to_csv(metrics_path, index=False)
    pooled_path = output_dir / f"{base_stem}_pooled_snr_metrics.csv"
    pooled_metrics.to_csv(pooled_path, index=False)
    persistent_path = output_dir / f"{base_stem}_persistent_channels.csv"
    persistent_channels.to_csv(persistent_path, index=False)
    channel_activity_path = output_dir / f"{base_stem}_raw_channel_mua_metrics.csv"
    channel_activity.to_csv(channel_activity_path, index=False)
    region_activity_path = output_dir / f"{base_stem}_raw_channel_mua_region_metrics.csv"
    region_activity.to_csv(region_activity_path, index=False)
    pooled_activity_path = output_dir / f"{base_stem}_pooled_raw_channel_mua_metrics.csv"
    pooled_activity.to_csv(pooled_activity_path, index=False)
    provenance = {
        "figure": [str(path) for path in figure_paths],
        "temporal_metrics": str(metrics_path),
        "pooled_snr_metrics": str(pooled_path),
        "persistent_channels": str(persistent_path),
        "raw_channel_mua_metrics": str(channel_activity_path),
        "raw_channel_mua_region_metrics": str(region_activity_path),
        "pooled_raw_channel_mua_metrics": str(pooled_activity_path),
        "pooled_snr_threshold": (
            f"raw-voltage-derived activity threshold SNR >= {RAW_ACTIVITY_SNR_THRESHOLD:g}; "
            f"eligible wells have at least one channel active in {', '.join(PERSISTENCE_REPEATS)}; "
            "eligible wells are split into two predefined spatial MGEO regions; "
            "channel means within each region, then mean +/- 95% CI across regions"
        ),
        "targets": [target.__dict__ for target in TARGETS],
        "source_repeats": list(REPEATS),
        "persistence_repeats": list(PERSISTENCE_REPEATS),
        "pooled_snr_sample_note": "Pooled SNR summarizes n=4 spatial MGEO regions across N=4 recording timepoints.",
        "raw_channel_mua_activity": {
            "source": "the same Step 1 analyzer raw-channel Neural Spikes voltage stream used for SNR",
            "relationship_to_snr": "SNR calculation and panels A-C are unchanged; only panels D-G use detected MUA events",
            "event_detection": {
                "method": "negative local voltage minimum below a robust channel-specific threshold",
                "threshold": (
                    f"channel median - {float(args.mua_threshold_sigma):g} * "
                    "precomputed robust_noise_uV"
                ),
                "refractory_period_ms": float(args.mua_refractory_ms),
                "spike_sorting": False,
            },
            "firing_rate": (
                "per-channel detected MUA event count divided by recording duration, including zero-event "
                "channels, then mean across channels within each prespecified spatial MGEO region; the "
                "50-ms Gaussian-smoothed inverse-ISI temporal P99.9 is retained in the channel-level CSV "
                "as an audit metric but is not plotted because interleaved multiunit events inflate this "
                "single-unit temporal-extreme statistic"
            ),
            "burst_rate": (
                "accepted raw-channel bursts are consolidated into MUA burst episodes when the interburst gap is "
                f"< {float(args.mua_min_interburst_interval_ms):g} ms; episode count/min is then averaged across "
                "all region channels, with zero-episode channels retained; original unconsolidated burst counts "
                "and rates remain in the channel-level CSV"
            ),
            "burst_duration": (
                "per-channel mean duration of the original accepted ISI-defined bursts before episode "
                "consolidation, then mean across finite channel values"
            ),
            "plot_summary": (
                "colored points are spatial MGEO-region values; black points and error bars are mean +/- 95% "
                "t-confidence interval across finite region values when at least three regions contribute; "
                "R4 burst duration uses its two finite regions for the mean point but its CI is not drawn"
            ),
            "burst_detection": {
                "method": "contiguous adjacent-ISI threshold",
                "max_isi_ms": burst_parameters.max_isi_ms,
                "min_spikes": burst_parameters.min_spikes,
                "min_duration_ms": burst_parameters.min_duration_ms,
            },
            "synchrony": (
                "mean pairwise spike-time tiling coefficient among nonempty raw-channel MUA event trains; "
                f"coincidence window +/-{float(args.synchrony_window_ms):g} ms"
            ),
        },
        "display_duration_min": float(args.display_duration_min),
        "png_dpi": int(args.png_dpi),
        "vector_export_note": "PDF and SVG outputs are vector exports; PNG is exported at high DPI for raster preview/use.",
        "trace_rendering_note": (
            "Raw-voltage panels are plotted as very thin full-sample voltage traces, not filled envelopes. "
            "No downsampling is applied to the displayed voltage traces. Full-sample traces are drawn in "
            "short contiguous chunks only to avoid renderer path-length limits; dense traces are rasterized "
            "during PDF/SVG export."
        ),
        "plating_time_anchor": str(PLATING_TIME),
        "plating_time_note": "Estimated as 5 minutes before source 000 metadata start, per setup timing.",
        "metric_note": (
            "Mean +/- SEM across ten non-overlapping 1-minute windows within each displayed "
            "10-minute representative-channel trace (n=10 temporal windows; not biological replicates)."
        ),
    }
    provenance_path = output_dir / f"{base_stem}_provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    legend_path = output_dir / f"{base_stem}_figure_legend.txt"
    legend_path.write_text(
        build_figure_legend(
            figure_paths=figure_paths,
            metrics_path=metrics_path,
            pooled_path=pooled_path,
            persistent_path=persistent_path,
            channel_activity_path=channel_activity_path,
            region_activity_path=region_activity_path,
            pooled_activity_path=pooled_activity_path,
            png_dpi=int(args.png_dpi),
            burst_parameters=burst_parameters,
            synchrony_window_ms=float(args.synchrony_window_ms),
            threshold_sigma=float(args.mua_threshold_sigma),
            refractory_period_ms=float(args.mua_refractory_ms),
            min_interburst_interval_ms=float(args.mua_min_interburst_interval_ms),
            min_spikes_for_smoothed_rate=int(args.mua_min_spikes_for_smoothed_rate),
        ),
        encoding="utf-8",
    )
    for path in figure_paths:
        print(path)
    print(metrics_path)
    print(channel_activity_path)
    print(region_activity_path)
    print(pooled_activity_path)
    print(provenance_path)
    print(legend_path)
    return 0


def build_pooled_snr(stats: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, object]], pd.DataFrame]:
    """Pool SNR by biological replicate: one spatial MGEO region is one dot."""
    working = stats.copy()
    working["well"] = working["well"].astype(str)
    working["repeat"] = working["repeat"].astype(str).str.zfill(3)
    region_wells = tuple(sorted({region["well"] for region in SPATIAL_MGEO_REGIONS.values()}))
    persistent_rows = []
    eligible_wells = set()
    for well in region_wells:
        well_stats = working.loc[working["well"].eq(well)]
        active = well_stats.loc[
            well_stats["repeat"].isin(PERSISTENCE_REPEATS)
            & (pd.to_numeric(well_stats["snr"], errors="coerce") >= RAW_ACTIVITY_SNR_THRESHOLD)
        ]
        active_repeats = active.groupby("channel_id")["repeat"].agg(lambda values: set(values))
        persistent_channels = sorted(
            int(channel_id)
            for channel_id, repeats in active_repeats.items()
            if set(PERSISTENCE_REPEATS).issubset(repeats)
        )
        if persistent_channels:
            eligible_wells.add(well)
        for channel_id in persistent_channels:
            persistent_rows.append(
                {
                    "well": well,
                    "region_id": "well_seed",
                    "channel_id": channel_id,
                    "persistence_repeats": ",".join(PERSISTENCE_REPEATS),
                    "activity_threshold_snr": RAW_ACTIVITY_SNR_THRESHOLD,
                }
            )
    region_channels = {
        region_id: region
        for region_id, region in SPATIAL_MGEO_REGIONS.items()
        if region["well"] in eligible_wells
    }
    for region_id, region in region_channels.items():
        for channel_id in region["channels"]:
            persistent_rows.append(
                {
                    "well": region["well"],
                    "region_id": region_id,
                    "channel_id": channel_id,
                    "persistence_repeats": "spatial_region",
                    "activity_threshold_snr": np.nan,
                }
            )

    point_rows = []
    pooled_rows = []
    for repeat in REPEATS:
        region_values = []
        for region_id, region in region_channels.items():
            well = region["well"]
            channels = region["channels"]
            if not channels:
                continue
            values = working.loc[
                working["well"].eq(well)
                & working["repeat"].eq(repeat)
                & working["channel_id"].isin(channels),
                "snr",
            ].to_numpy(float)
            if values.size:
                region_value = float(np.mean(values))
                region_values.append(region_value)
                point_rows.append(
                    {
                        "repeat": repeat,
                        "well": well,
                        "region_id": region_id,
                        "snr": region_value,
                        "region_channel_count": len(channels),
                    }
                )
        sem = float(np.std(region_values, ddof=1) / np.sqrt(len(region_values))) if len(region_values) > 1 else np.nan
        pooled_rows.append(
            {
                "repeat": repeat,
                "snr_mean": float(np.mean(region_values)) if region_values else np.nan,
                "snr_sem": sem,
                "snr_ci95": confidence_interval_95(sem, len(region_values)),
                "qualifying_organoid_count": len(region_values),
            }
        )

    persistent = pd.DataFrame(
        persistent_rows,
        columns=["well", "region_id", "channel_id", "persistence_repeats", "activity_threshold_snr"],
    )
    return pd.DataFrame(pooled_rows), point_rows, persistent


def build_raw_channel_activity(
    stats: pd.DataFrame,
    *,
    burst_parameters: BurstDetectionParameters,
    synchrony_window_ms: float,
    threshold_sigma: float,
    refractory_period_ms: float,
    min_interburst_interval_ms: float,
    chunk_duration_s: float,
    min_spikes_for_smoothed_rate: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply the single-unit activity math to raw-channel MUA event trains."""
    import spikeinterface.full as si

    if not np.isfinite(threshold_sigma) or threshold_sigma <= 0:
        raise ValueError("threshold_sigma must be finite and > 0")
    if not np.isfinite(refractory_period_ms) or refractory_period_ms <= 0:
        raise ValueError("refractory_period_ms must be finite and > 0")
    if not np.isfinite(min_interburst_interval_ms) or min_interburst_interval_ms < 0:
        raise ValueError("min_interburst_interval_ms must be finite and >= 0")
    if not np.isfinite(chunk_duration_s) or chunk_duration_s <= 0:
        raise ValueError("chunk_duration_s must be finite and > 0")
    if min_spikes_for_smoothed_rate < 2:
        raise ValueError("min_spikes_for_smoothed_rate must be >= 2")

    working = stats.copy()
    working["well"] = working["well"].astype(str)
    working["repeat"] = working["repeat"].astype(str).str.zfill(3)
    analyzer_lookup = (
        working.loc[
            working["repeat"].isin(REPEATS)
            & working["well"].isin({region["well"] for region in SPATIAL_MGEO_REGIONS.values()})
        ]
        .drop_duplicates(["repeat", "well"])
        .set_index(["repeat", "well"])["analyzer_path"]
        .to_dict()
    )
    channel_rows: list[dict[str, object]] = []
    region_rows: list[dict[str, object]] = []
    for repeat in REPEATS:
        for well in sorted({region["well"] for region in SPATIAL_MGEO_REGIONS.values()}):
            analyzer_path = Path(str(analyzer_lookup[(repeat, well)]))
            analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=False)
            sampling_frequency = float(analyzer.recording.get_sampling_frequency())
            duration_s = float(analyzer.recording.get_total_duration())
            well_regions = {
                region_id: region
                for region_id, region in SPATIAL_MGEO_REGIONS.items()
                if region["well"] == well
            }
            channel_ids = sorted(
                {int(channel_id) for region in well_regions.values() for channel_id in region["channels"]}
            )
            channel_stats = (
                working.loc[
                    working["repeat"].eq(repeat)
                    & working["well"].eq(well)
                    & working["channel_id"].isin(channel_ids)
                ]
                .drop_duplicates("channel_id")
                .set_index("channel_id")
            )
            if set(channel_stats.index.astype(int)) != set(channel_ids):
                raise RuntimeError(f"Missing raw-channel SNR statistics for repeat={repeat}, well={well}")
            medians_uV = {
                int(channel_id): float(row["median_uV"])
                for channel_id, row in channel_stats.iterrows()
            }
            noise_uV = {
                int(channel_id): float(row["robust_noise_uV"])
                for channel_id, row in channel_stats.iterrows()
            }
            thresholds_uV = {
                channel_id: medians_uV[channel_id] - threshold_sigma * noise_uV[channel_id]
                for channel_id in channel_ids
            }
            events_by_channel = detect_recording_mua_events(
                analyzer.recording,
                channel_ids=channel_ids,
                thresholds_uV=thresholds_uV,
                refractory_period_ms=refractory_period_ms,
                chunk_duration_s=chunk_duration_s,
            )

            channel_records: dict[int, dict[str, object]] = {}
            for channel_id in channel_ids:
                spike_times_s = events_by_channel[channel_id]
                activity_summary, burst_events = summarize_unit_activity(
                    spike_times_s,
                    duration_s,
                    burst_parameters,
                )
                burst_episode_count = count_burst_episodes(
                    burst_events,
                    min_interburst_interval_ms=min_interburst_interval_ms,
                )
                smoothed_rate_summary = summarize_smoothed_inverse_isi_rate(
                    spike_times_s,
                    duration_s,
                    gaussian_sigma_ms=50.0,
                    evaluation_bin_ms=1.0,
                    min_spikes=min_spikes_for_smoothed_rate,
                )
                region_id = next(
                    region_name
                    for region_name, region in well_regions.items()
                    if channel_id in region["channels"]
                )
                record = {
                    "repeat": repeat,
                    "well": well,
                    "region_id": region_id,
                    "channel_id": channel_id,
                    "analyzer_path": str(analyzer_path),
                    "recording_duration_s": duration_s,
                    "sampling_frequency_hz": sampling_frequency,
                    "channel_median_uV": medians_uV[channel_id],
                    "robust_noise_uV": noise_uV[channel_id],
                    "negative_threshold_sigma": threshold_sigma,
                    "negative_threshold_uV": thresholds_uV[channel_id],
                    "refractory_period_ms": refractory_period_ms,
                    "minimum_interburst_interval_ms": min_interburst_interval_ms,
                    "detected_mua_event_count": int(spike_times_s.size),
                    "burst_episode_count": int(burst_episode_count),
                    "burst_episode_rate_per_min": float(
                        burst_episode_count / (duration_s / 60.0)
                    ),
                    **activity_summary,
                    **smoothed_rate_summary,
                }
                channel_records[channel_id] = {**record, "spike_times_s": spike_times_s}
                channel_rows.append(record)

            for region_id, region in well_regions.items():
                region_channels = [channel_records[int(channel_id)] for channel_id in region["channels"]]
                firing_rates = np.asarray(
                    [
                        channel["firing_rate_hz_recomputed"]
                        for channel in region_channels
                    ],
                    dtype=float,
                )
                burst_episode_rates = np.asarray(
                    [channel["burst_episode_rate_per_min"] for channel in region_channels],
                    dtype=float,
                )
                burst_durations = np.asarray(
                    [channel["mean_burst_duration_ms"] for channel in region_channels], dtype=float
                )
                finite_firing_rates = firing_rates[np.isfinite(firing_rates)]
                finite_burst_durations = burst_durations[np.isfinite(burst_durations)]
                synchrony, pair_count = mean_pairwise_spike_time_tiling_coefficient(
                    [channel["spike_times_s"] for channel in region_channels],
                    duration_s,
                    coincidence_window_ms=synchrony_window_ms,
                )
                region_rows.append(
                    {
                        "repeat": repeat,
                        "well": well,
                        "region_id": region_id,
                        "analyzer_path": str(analyzer_path),
                        "recording_duration_s": duration_s,
                        "region_channel_count": len(region_channels),
                        "detected_mua_event_count": int(
                            sum(int(channel["detected_mua_event_count"]) for channel in region_channels)
                        ),
                        "mua_event_rate_channel_count": int(finite_firing_rates.size),
                        "smoothed_rate_eligible_channel_count": int(
                            sum(
                                bool(channel["inverse_isi_gaussian_eligible"])
                                for channel in region_channels
                            )
                        ),
                        "burst_positive_channel_count": int(
                            sum(bool(channel["burst_positive"]) for channel in region_channels)
                        ),
                        "synchrony_pair_count": int(pair_count),
                        "mean_mua_event_rate_hz": (
                            float(np.mean(finite_firing_rates))
                            if finite_firing_rates.size
                            else np.nan
                        ),
                        "mean_burst_episode_rate_per_min": float(
                            np.mean(burst_episode_rates)
                        ),
                        "mean_burst_duration_ms": (
                            float(np.mean(finite_burst_durations))
                            if finite_burst_durations.size
                            else np.nan
                        ),
                        "mean_pairwise_sttc": synchrony,
                    }
                )

    channel_activity = pd.DataFrame(channel_rows).sort_values(
        ["repeat", "region_id", "channel_id"]
    ).reset_index(drop=True)
    region_activity = pd.DataFrame(region_rows).sort_values(
        ["repeat", "region_id"]
    ).reset_index(drop=True)
    pooled_rows = []
    activity_metrics = (
        "mean_mua_event_rate_hz",
        "mean_burst_episode_rate_per_min",
        "mean_burst_duration_ms",
        "mean_pairwise_sttc",
    )
    for repeat in REPEATS:
        repeat_rows = region_activity.loc[region_activity["repeat"].eq(repeat)]
        for metric in activity_metrics:
            values = pd.to_numeric(repeat_rows[metric], errors="coerce").dropna().to_numpy(float)
            sem = float(np.std(values, ddof=1) / np.sqrt(values.size)) if values.size > 1 else np.nan
            pooled_rows.append(
                {
                    "repeat": repeat,
                    "metric": metric,
                    "mean": float(np.mean(values)) if values.size else np.nan,
                    "sem": sem,
                    "ci95": confidence_interval_95(sem, int(values.size)),
                    "contributing_region_count": int(values.size),
                }
            )
    return channel_activity, region_activity, pd.DataFrame(pooled_rows)


def detect_recording_mua_events(
    recording,
    *,
    channel_ids: list[int],
    thresholds_uV: dict[int, float],
    refractory_period_ms: float,
    chunk_duration_s: float,
) -> dict[int, np.ndarray]:
    """Detect raw-channel MUA events chunkwise without loading a full recording."""
    selected = recording.select_channels(channel_ids)
    sampling_frequency = float(selected.get_sampling_frequency())
    sample_count = int(selected.get_num_samples())
    chunk_samples = max(1, int(round(chunk_duration_s * sampling_frequency)))
    overlap_samples = max(
        2,
        int(np.ceil(refractory_period_ms / 1000.0 * sampling_frequency)),
    )
    chunks: dict[int, list[np.ndarray]] = {channel_id: [] for channel_id in channel_ids}
    for core_start in range(0, sample_count, chunk_samples):
        core_stop = min(sample_count, core_start + chunk_samples)
        read_start = max(0, core_start - overlap_samples)
        read_stop = min(sample_count, core_stop + overlap_samples)
        traces = np.asarray(
            selected.get_traces(
                start_frame=read_start,
                end_frame=read_stop,
                return_in_uV=True,
            ),
            dtype=np.float32,
        )
        for channel_index, channel_id in enumerate(channel_ids):
            local_events = detect_negative_threshold_events(
                traces[:, channel_index],
                sampling_frequency,
                thresholds_uV[channel_id],
                refractory_period_ms=refractory_period_ms,
            )
            global_events = local_events + read_start
            keep = (global_events >= core_start) & (global_events < core_stop)
            if keep.any():
                chunks[channel_id].append(global_events[keep])
    return {
        channel_id: (
            np.concatenate(channel_chunks).astype(float) / sampling_frequency
            if channel_chunks
            else np.asarray([], dtype=float)
        )
        for channel_id, channel_chunks in chunks.items()
    }


def confidence_interval_95(sem: float, n: int) -> float:
    if n <= 1 or not np.isfinite(sem):
        return np.nan
    # Two-sided t critical values for small n; n=4 is the expected pooled replicate count.
    tcrit_by_df = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}
    return float(sem * tcrit_by_df.get(n - 1, 1.96))


def build_figure_legend(
    *,
    figure_paths: list[Path],
    metrics_path: Path,
    pooled_path: Path,
    persistent_path: Path,
    channel_activity_path: Path,
    region_activity_path: Path,
    pooled_activity_path: Path,
    png_dpi: int,
    burst_parameters: BurstDetectionParameters,
    synchrony_window_ms: float,
    threshold_sigma: float,
    refractory_period_ms: float,
    min_interburst_interval_ms: float,
    min_spikes_for_smoothed_rate: int,
) -> str:
    region_lines = [
        f"- {region_id}: well {region['well']}, channels {', '.join(map(str, region['channels']))}"
        for region_id, region in SPATIAL_MGEO_REGIONS.items()
    ]
    target_lines = [
        f"- {target.label}: well {target.well}, representative raw-voltage channel {target.channel_id}"
        for target in TARGETS
    ]
    output_lines = [f"- {path}" for path in figure_paths]
    return (
        "Figure legend and plotting details\n"
        "==================================\n\n"
        "Figure title/summary\n"
        "Raw-voltage stability of transiently plated MGEOs during the first hours after plating.\n\n"
        "Panel descriptions\n"
        "A, B. Representative raw-voltage traces from two transiently plated MGEO-containing wells. "
        "MGEO 1 is shown from well B2, channel 29. MGEO 2 is shown from well A2, channel 28. "
        "Within each panel, the same physical electrode channel is followed across recordings; "
        "the stacked traces therefore compare the same channel across time rather than different channels. "
        "For each MGEO, four recordings are shown from source files 000, 002, 003, and 004. "
        "The aborted short recording 001 is not plotted. Each trace is cropped to the first 10 minutes "
        "of that recording so all displayed traces have the same duration. Clock timestamps shown on the "
        "left are the recording metadata start times. Elapsed times shown on the right are the end of the "
        "displayed 10-minute window, calculated relative to an estimated plating time 5 minutes before "
        "the metadata start of recording 000. Raw-voltage traces are plotted as very thin full-sample "
        "voltage lines with no downsampling. Long traces are drawn in contiguous chunks only to avoid "
        "renderer path-length limits; no samples are skipped. No trace axes, tick marks, tick labels, grid lines, or frame are shown. Scale bars "
        "indicate 2 minutes and 10 uV.\n\n"
        "C. Pooled SNR across spatial MGEO regions. SNR values are calculated from raw-voltage-derived "
        "channel statistics. Eligible parent wells were required to have at least one channel with simple "
        f"raw-voltage threshold activity, defined as SNR >= {RAW_ACTIVITY_SNR_THRESHOLD:g}, persisting "
        f"across all four recordings ({', '.join(PERSISTENCE_REPEATS)}). The eligible wells were A2 and B2. "
        "Within those wells, spatially separated MGEO regions were defined from the electrode geometry, "
        "yielding n = 4 MGEO regions. For each recording, the colored jittered points show the four individual "
        "spatial MGEO-region SNR values, calculated as the mean SNR across channels assigned to that region. "
        "The black point shows the mean across the four MGEO regions. Vertical black bars show the 95% confidence "
        "interval around the mean using the t critical value for n = 4. Horizontal CI caps are omitted.\n\n"
        "D-G. Raw-channel multiunit-activity metrics for the same four spatial MGEO regions and recordings. "
        "No spike sorting or single-unit selection is used. Negative local voltage minima are detected independently "
        f"on each channel at channel median minus {threshold_sigma:g} times robust noise, with a "
        f"{refractory_period_ms:g}-ms refractory period. Colored points are individual "
        "spatial MGEO regions; black points and vertical bars show the mean and 95% t-confidence interval across "
        "finite region values when at least three regions contribute. The R4 burst-duration mean uses its two "
        "available regions, but no CI is drawn for that point. D, MUA firing rate is each channel's detected "
        "event count divided by recording "
        "duration and then averaged across all region channels, including zero-event channels. The 50-ms "
        "Gaussian-smoothed inverse-ISI temporal P99.9 from the final reformatted single-unit calculation is retained "
        "in the channel-level audit CSV but is not plotted: on an unsorted channel, interleaved events from multiple "
        "neurons create short ISIs and inflate that nonlinear temporal-extreme statistic. "
        f"The retained audit P99.9 requires at least {min_spikes_for_smoothed_rate} detected MUA events per channel. "
        "E, MUA burst-episode rate consolidates accepted raw-channel bursts separated "
        f"by less than {min_interburst_interval_ms:g} ms, then averages episode count per minute across all region "
        "channels; channels without episodes are retained as zero. The unconsolidated accepted-burst counts and "
        "rates remain in the channel-level CSV. F, burst duration is the mean duration of the original accepted "
        "ISI-defined bursts (before episode consolidation) and is "
        "undefined for regions without accepted bursts. Bursts are contiguous spike runs with adjacent ISIs <= "
        f"{burst_parameters.max_isi_ms:g} ms, at least {burst_parameters.min_spikes} spikes, and duration >= "
        f"{burst_parameters.min_duration_ms:g} ms. G, synchrony is the mean pairwise spike-time tiling coefficient "
        f"using a +/-{synchrony_window_ms:g} ms coincidence window; it is undefined when fewer than two nonempty "
        "channel MUA event trains are available. The original raw-voltage traces and SNR calculations in panels A-C "
        "are unchanged.\n\n"
        "Representative trace channels\n"
        + "\n".join(target_lines)
        + "\n\nSpatial MGEO regions used for pooled SNR\n"
        + "\n".join(region_lines)
        + "\n\nTiming\n"
        f"- Plating anchor: {PLATING_TIME} (estimated as 5 minutes before recording 000 metadata start).\n"
        "- Recordings plotted: 000, 002, 003, 004.\n"
        "- Displayed trace duration: 10 minutes per recording.\n\n"
        "Export and resolution\n"
        f"- PNG exported at {png_dpi} DPI.\n"
        "- PDF and SVG are vector exports and should be preferred for final manuscript layout when possible.\n"
        "- Matplotlib font handling keeps SVG text editable and embeds Type 42 fonts in PDF.\n\n"
        "Associated output files\n"
        + "\n".join(output_lines)
        + f"\n- Temporal trace metrics: {metrics_path}\n"
        + f"- Pooled SNR metrics: {pooled_path}\n"
        + f"- Persistent/region channel audit: {persistent_path}\n"
        + f"- Raw-channel MUA metrics: {channel_activity_path}\n"
        + f"- Spatial-region raw-channel MUA metrics: {region_activity_path}\n"
        + f"- Pooled raw-channel MUA metrics: {pooled_activity_path}\n"
    )


def summarize_display_window(
    recording,
    *,
    duration_s: float,
    envelope_bins: int,
    sample_stride: int,
) -> dict[str, object]:
    fs = float(recording.get_sampling_frequency())
    n_samples = min(int(round(duration_s * fs)), int(recording.get_num_samples()))
    edges = np.linspace(0, n_samples, envelope_bins + 1, dtype=np.int64)
    minimum = np.full(envelope_bins, np.nan)
    maximum = np.full(envelope_bins, np.nan)
    mean = np.full(envelope_bins, np.nan)
    full_trace = np.asarray(
        recording.get_traces(start_frame=0, end_frame=n_samples, return_in_uV=True), dtype=np.float32
    )[:, 0]
    for index, (start, stop) in enumerate(zip(edges[:-1], edges[1:], strict=True)):
        trace = full_trace[int(start) : int(stop)]
        finite = trace[np.isfinite(trace)]
        if finite.size:
            minimum[index] = float(np.min(finite))
            maximum[index] = float(np.max(finite))
            mean[index] = float(np.mean(finite))
    values = full_trace[:: max(1, sample_stride)].astype(float)
    values = values[np.isfinite(values)]
    window_size = int(round(60.0 * fs))
    window_rows = []
    for start in range(0, n_samples - window_size + 1, window_size):
        window = full_trace[start : start + window_size : max(1, sample_stride)].astype(float)
        window = window[np.isfinite(window)]
        median = float(np.median(window))
        noise = float(np.median(np.abs(window - median)) / 0.67448975)
        p01, p999 = np.percentile(window, [0.1, 99.9])
        signal = float(max(abs(p01), abs(p999)))
        window_rows.append((signal / noise, signal, noise))
    window_metrics = np.asarray(window_rows, dtype=float)
    if window_metrics.shape[0] < 2:
        raise RuntimeError("At least two complete 1-minute windows are required for SEM")
    means = np.mean(window_metrics, axis=0)
    sems = np.std(window_metrics, axis=0, ddof=1) / np.sqrt(window_metrics.shape[0])
    return {
        "time_min": (0.5 * (edges[:-1] + edges[1:])) / fs / 60.0,
        "minimum_uV": minimum,
        "maximum_uV": maximum,
        "mean_uV": mean,
        "duration_s": n_samples / fs,
        "metric_window_count": int(window_metrics.shape[0]),
        "snr_mean": float(means[0]),
        "snr_sem": float(sems[0]),
        "signal_mean_uV": float(means[1]),
        "signal_sem_uV": float(sems[1]),
        "noise_mean_uV": float(means[2]),
        "noise_sem_uV": float(sems[2]),
    }


def plot_full_sample_trace(ax, item: dict[str, object], offset: float, color: str) -> None:
    import spikeinterface.full as si

    analyzer = si.load_sorting_analyzer(Path(item["analyzer_path"]), load_extensions=False)
    recording = analyzer.recording.select_channels([int(item["channel_id"])])
    fs = float(recording.get_sampling_frequency())
    n_samples = min(int(round(float(item["duration_s"]) * fs)), int(recording.get_num_samples()))
    trace = np.asarray(
        recording.get_traces(start_frame=0, end_frame=n_samples, return_in_uV=True), dtype=np.float32
    )[:, 0]
    time = (np.arange(n_samples, dtype=np.float32) / np.float32(fs) / np.float32(60.0)).astype(np.float32)
    chunk_size = 10000
    for start in range(0, n_samples, chunk_size):
        stop = min(n_samples, start + chunk_size)
        if start:
            start -= 1
        ax.plot(
            time[start:stop],
            trace[start:stop] + np.float32(offset),
            color=color,
            alpha=0.95,
            lw=0.18,
            solid_capstyle="butt",
            rasterized=True,
        )


def render_figure(
    trace_data: dict,
    metrics: pd.DataFrame,
    display_duration_min: float,
    *,
    pooled_metrics: pd.DataFrame,
    pooled_points: list[dict[str, object]],
    region_activity: pd.DataFrame,
    pooled_activity: pd.DataFrame,
):
    fig = plt.figure(figsize=(13.7, 3.45))
    grid = GridSpec(
        1,
        7,
        figure=fig,
        width_ratios=[3.05, 3.05, 0.85, 0.85, 0.85, 0.85, 0.85],
        wspace=0.58,
    )
    repeat_labels = {repeat: f"Recording {index + 1}" for index, repeat in enumerate(REPEATS)}
    envelope_grays = ("#BDBDBD", "#888888", "#4F4F4F", "#111111")
    for row_index, target in enumerate(TARGETS):
        ax_trace = fig.add_subplot(grid[0, row_index])
        target_traces = [trace_data[(target.label, repeat)] for repeat in REPEATS]
        extrema = np.concatenate(
            [np.asarray(item["minimum_uV"]) for item in target_traces]
            + [np.asarray(item["maximum_uV"]) for item in target_traces]
        )
        span = float(np.nanpercentile(extrema, 99.5) - np.nanpercentile(extrema, 0.5))
        row_gap = max(8.0, span * 1.25)
        for index, (repeat, item, gray) in enumerate(zip(REPEATS, target_traces, envelope_grays, strict=True)):
            offset = -index * row_gap
            plot_full_sample_trace(ax_trace, item, offset, gray)
            start_clock = pd.Timestamp(item["source_start"]).strftime("%H:%M:%S")
            ax_trace.text(
                -0.16,
                offset,
                start_clock,
                ha="right",
                va="center",
                fontsize=6.2,
                color="black",
            )
            ax_trace.text(
                display_duration_min + 0.16,
                offset,
                f"{item['elapsed_end_min']:+.0f} min\n{repeat_labels[repeat]}",
                ha="left",
                va="center",
                fontsize=6.2,
                color="black",
                linespacing=1.0,
            )
        ax_trace.set_xlim(-1.18, display_duration_min + 1.40)
        ax_trace.set_title(
            f"{chr(65 + row_index)}   {target.label}", loc="left", fontsize=10.5, fontweight="bold", pad=8
        )
        ax_trace.text(
            -0.16,
            1.02,
            "Timestamp",
            transform=ax_trace.get_xaxis_transform(),
            ha="right",
            va="bottom",
            fontsize=5.8,
            color="0.3",
        )
        ax_trace.text(
            display_duration_min + 0.16,
            1.02,
            "min from plating",
            transform=ax_trace.get_xaxis_transform(),
            ha="left",
            va="bottom",
            fontsize=5.8,
            color="0.3",
        )
        ax_trace.grid(False)
        for spine in ax_trace.spines.values():
            spine.set_visible(False)
        ax_trace.set_xticks([])
        ax_trace.set_yticks([])
        ax_trace.tick_params(bottom=False, left=False, labelbottom=False, labelleft=False)
        # Electrophysiology-style scale bars: 2 min horizontal, 10 µV vertical.
        bar_x = display_duration_min - 1.8
        bar_y = -3 * row_gap - 0.42 * row_gap
        ax_trace.plot([bar_x, bar_x + 2.0], [bar_y, bar_y], color="black", lw=1.2, clip_on=False)
        ax_trace.plot([bar_x, bar_x], [bar_y, bar_y + 10.0], color="black", lw=1.2, clip_on=False)
        ax_trace.text(bar_x + 1.0, bar_y - 0.05 * row_gap, "2 min", ha="center", va="top", fontsize=6.5)
        ax_trace.text(bar_x - 0.08, bar_y + 5.0, "10 µV", ha="right", va="center", fontsize=6.5)

    pooled = pooled_metrics.sort_values("repeat")
    pooled_x = 1.0 + 0.5 * np.arange(len(pooled))
    pooled_x_labels = [f"R{index + 1}" for index in range(len(pooled))]
    ax_pooled = fig.add_subplot(grid[0, 2])
    ax_pooled.set_title("C", loc="left", fontsize=10.5, fontweight="bold", pad=8)
    if pooled_points:
        point_df = pd.DataFrame(pooled_points)
        for region_id, point_group in point_df.groupby("region_id"):
            point_group = point_group.set_index("repeat").reindex(REPEATS).dropna()
            if point_group.empty:
                continue
            x_lookup = {repeat: pooled_x[index] for index, repeat in enumerate(REPEATS)}
            point_x = np.asarray(
                [x_lookup[repeat] + REGION_JITTER_OFFSETS.get(region_id, 0.12) for repeat in point_group.index]
            )
            ax_pooled.scatter(
                point_x,
                point_group["snr"],
                color=REGION_COLORS.get(region_id, "0.5"),
                alpha=0.72,
                s=24,
                linewidths=0,
                zorder=1,
            )
    ax_pooled.errorbar(
        pooled_x,
        pooled["snr_mean"],
        yerr=pooled["snr_ci95"],
        color="black",
        marker="o",
        lw=1.1,
        ms=5.8,
        capsize=0,
        capthick=0,
        zorder=3,
    )
    ax_pooled.set_xticks(pooled_x, pooled_x_labels)
    ax_pooled.set_ylabel("SNR")
    ax_pooled.set_xlim(0.85, 2.86)
    ax_pooled.grid(False)
    clean_axes(ax_pooled)
    activity_specs = (
        (
            "D",
            "mean_mua_event_rate_hz",
            "Firing rate (Hz)",
        ),
        (
            "E",
            "mean_burst_episode_rate_per_min",
            "Burst rate (episodes/min)",
        ),
        ("F", "mean_burst_duration_ms", "Burst duration (ms)"),
        ("G", "mean_pairwise_sttc", "Synchrony (STTC)"),
    )
    compact_metric_axes = [ax_pooled]
    for axis_index, (panel, metric, ylabel) in enumerate(activity_specs):
        axis = fig.add_subplot(grid[0, axis_index + 3])
        plot_region_metric(
            axis,
            region_activity=region_activity,
            pooled_activity=pooled_activity,
            metric=metric,
            pooled_x=pooled_x,
            pooled_x_labels=pooled_x_labels,
        )
        axis.set_title(panel, loc="left", fontsize=10.5, fontweight="bold", pad=8)
        axis.set_ylabel(ylabel)
        compact_metric_axes.append(axis)

    fig.subplots_adjust(left=0.035, right=0.99, top=0.86, bottom=0.11)
    for axis in compact_metric_axes:
        pos = axis.get_position()
        axis.set_position([pos.x0, pos.y0 + 0.18 * pos.height, pos.width, 0.64 * pos.height])
    return fig


REGION_COLORS = {
    region_id: color
    for region_id, color in zip(
        ("A2-MGEOa", "A2-MGEOb", "B2-MGEOa", "B2-MGEOb"),
        ("#6A8CAF", "#9B6A8F", "#A07A55", "#5E8F99"),
        strict=True,
    )
}
REGION_JITTER_OFFSETS = {
    region_id: offset
    for region_id, offset in zip(
        ("A2-MGEOa", "A2-MGEOb", "B2-MGEOa", "B2-MGEOb"),
        (0.07, 0.11, 0.15, 0.19),
        strict=True,
    )
}


def plot_region_metric(
    ax,
    *,
    region_activity: pd.DataFrame,
    pooled_activity: pd.DataFrame,
    metric: str,
    pooled_x: np.ndarray,
    pooled_x_labels: list[str],
) -> None:
    x_lookup = {repeat: pooled_x[index] for index, repeat in enumerate(REPEATS)}
    for region_id, point_group in region_activity.groupby("region_id"):
        point_group = point_group.set_index("repeat").reindex(REPEATS)
        values = pd.to_numeric(point_group[metric], errors="coerce")
        finite = values.notna()
        if not finite.any():
            continue
        repeats = values.index[finite]
        point_x = np.asarray(
            [x_lookup[repeat] + REGION_JITTER_OFFSETS.get(region_id, 0.12) for repeat in repeats]
        )
        ax.scatter(
            point_x,
            values.loc[finite],
            color=REGION_COLORS.get(region_id, "0.5"),
            alpha=0.72,
            s=24,
            linewidths=0,
            zorder=1,
        )
    pooled = (
        pooled_activity.loc[pooled_activity["metric"].eq(metric)]
        .set_index("repeat")
        .reindex(REPEATS)
    )
    ax.errorbar(
        pooled_x,
        pooled["mean"],
        yerr=pooled["ci95"].where(pooled["contributing_region_count"].ge(3)),
        color="black",
        marker="o",
        lw=1.1,
        ms=5.8,
        capsize=0,
        capthick=0,
        zorder=3,
    )
    ax.set_xticks(pooled_x, pooled_x_labels)
    ax.set_xlim(0.85, 2.86)
    ax.grid(False)
    clean_axes(ax)


def clean_axes(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(direction="out", length=3)


if __name__ == "__main__":
    raise SystemExit(main())
