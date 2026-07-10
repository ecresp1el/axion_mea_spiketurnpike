#!/usr/bin/env python3
"""Render Panel E with mean, median, or max unit aggregation per organoid."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REGION_ORDER = ["dorsal", "ventral"]
REGION_COLORS = {"dorsal": "#2A9D8F", "ventral": "#6A4C93"}
VARIANT_MARKERS = {
    "primary_raw": "o",
    "filter_200Hz-3kHz": "s",
    "broadband_processor_raw": "^",
}
AGGREGATIONS = ["mean", "median", "max"]
METRICS = [
    ("firing_rate_hz_recomputed", "Overall mean firing rate", "SUA firing rate (Hz)"),
    ("burst_rate_per_min", "Burst rate", "SUA burst rate (bursts/min)"),
    (
        "mean_firing_rate_within_bursts_hz",
        "Firing rate within bursts",
        "Within-burst firing rate (Hz)",
    ),
    ("mean_burst_duration_ms", "Burst duration", "Burst duration (ms)"),
    ("mean_interburst_interval_s", "Inter-burst interval", "Inter-burst interval (s)"),
    ("mean_spikes_per_burst", "Spikes per burst", "Spikes per burst"),
]


def parse_args() -> argparse.Namespace:
    root = Path(
        "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
        "step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dv_sua_spontaneous_activity_20260710_20260710_052817"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--unit-metrics-csv",
        type=Path,
        default=root / "cytoview_dv_sua_spontaneous_activity_20260710_unit_metrics.csv",
    )
    parser.add_argument(
        "--recording-well-summary-csv",
        type=Path,
        default=root / "cytoview_dv_sua_spontaneous_activity_20260710_recording_well_summary.csv",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--date-label", default="20260710")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    unit_metrics_csv = args.unit_metrics_csv.expanduser().resolve()
    recording_well_summary_csv = args.recording_well_summary_csv.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    units = pd.read_csv(unit_metrics_csv)
    universe = pd.read_csv(recording_well_summary_csv)
    metadata_columns = [
        "recording_well_id",
        "recording",
        "well",
        "organoid_well",
        "region_call",
        "plate_id",
        "raw_variant",
        "recording_well_has_sua",
        "sua_unit_count",
    ]
    universe = universe[metadata_columns].drop_duplicates("recording_well_id")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    output_files: dict[str, list[str]] = {}
    organoid_frames: list[pd.DataFrame] = []
    regional_rows: list[dict[str, object]] = []
    for aggregation in AGGREGATIONS:
        organoids = _aggregate_units(units, universe, aggregation)
        organoid_frames.append(organoids.assign(unit_aggregation=aggregation))
        figure_base = output_dir / (
            f"cytoview_dv_sua_spontaneous_activity_{args.date_label}_unit_{aggregation}"
        )
        paths, rows = _plot_version(
            plt,
            Line2D,
            organoids,
            figure_base,
            aggregation=aggregation,
        )
        output_files[aggregation] = [str(path) for path in paths]
        regional_rows.extend(rows)

    organoid_values = pd.concat(organoid_frames, ignore_index=True)
    organoid_csv = output_dir / (
        f"cytoview_dv_sua_spontaneous_activity_{args.date_label}_unit_aggregation_organoid_values.csv"
    )
    regional_csv = output_dir / (
        f"cytoview_dv_sua_spontaneous_activity_{args.date_label}_unit_aggregation_region_summary.csv"
    )
    provenance_json = output_dir / (
        f"cytoview_dv_sua_spontaneous_activity_{args.date_label}_unit_aggregation_provenance.json"
    )
    organoid_values.to_csv(organoid_csv, index=False)
    pd.DataFrame(regional_rows).to_csv(regional_csv, index=False)
    provenance_json.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "script": str(Path(__file__).resolve()),
                "unit_metrics_csv": str(unit_metrics_csv),
                "recording_well_summary_csv": str(recording_well_summary_csv),
                "output_dir": str(output_dir),
                "unit_aggregations": AGGREGATIONS,
                "aggregation_definition": (
                    "For each recording/well organoid and metric, aggregate its SUA unit-level values "
                    "using mean, median, or maximum; then show the regional mean +/- SEM across organoids."
                ),
                "all_non_lfp_recording_wells": int(len(universe)),
                "recording_wells_with_sua": int(universe["recording_well_has_sua"].sum()),
                "recording_wells_without_sua": int((~universe["recording_well_has_sua"]).sum()),
                "sua_units": int(len(units)),
                "outputs": output_files
                | {
                    "organoid_values_csv": [str(organoid_csv)],
                    "regional_summary_csv": [str(regional_csv)],
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for aggregation, paths in output_files.items():
        print(aggregation, *paths, sep="\n  ")
    print(f"Organoid values\n  {organoid_csv}")
    print(f"Regional summary\n  {regional_csv}")
    return 0


def _aggregate_units(units: pd.DataFrame, universe: pd.DataFrame, aggregation: str) -> pd.DataFrame:
    if aggregation not in AGGREGATIONS:
        raise ValueError(f"Unsupported aggregation: {aggregation}")
    grouped_rows: list[dict[str, object]] = []
    for recording_well_id, group in units.groupby("recording_well_id", sort=True):
        row: dict[str, object] = {"recording_well_id": recording_well_id}
        for source_metric, _, _ in METRICS:
            values = pd.to_numeric(group[source_metric], errors="coerce").dropna().to_numpy(dtype=float)
            row[source_metric] = _aggregate(values, aggregation)
            row[f"{source_metric}__unit_n"] = int(values.size)
        grouped_rows.append(row)
    aggregated = pd.DataFrame(grouped_rows)
    out = universe.merge(aggregated, on="recording_well_id", how="left", validate="one_to_one")
    return out.sort_values(["region_call", "recording", "well"]).reset_index(drop=True)


def _plot_version(plt, Line2D, organoids: pd.DataFrame, output_base: Path, *, aggregation: str):
    fig, axes = plt.subplots(2, 3, figsize=(14.5, 8.8), constrained_layout=False)
    fig.patch.set_facecolor("white")
    rng = np.random.default_rng(20260710)
    regional_rows: list[dict[str, object]] = []
    for ax, (metric, title, ylabel) in zip(axes.ravel(), METRICS, strict=True):
        ax.set_facecolor("white")
        for region_index, region in enumerate(REGION_ORDER):
            subset = organoids.loc[organoids["region_call"].eq(region)].copy()
            jitter = rng.uniform(-0.10, 0.10, size=len(subset))
            for point_index, (_, row) in enumerate(subset.iterrows()):
                value = row[metric]
                if pd.isna(value):
                    continue
                ax.scatter(
                    region_index + jitter[point_index],
                    float(value),
                    s=42,
                    marker=VARIANT_MARKERS.get(str(row["raw_variant"]), "D"),
                    facecolor=REGION_COLORS[region],
                    edgecolor="white",
                    linewidth=0.7,
                    alpha=0.82,
                    zorder=3,
                )
            values = pd.to_numeric(subset[metric], errors="coerce").dropna().to_numpy(dtype=float)
            if values.size:
                region_mean = float(np.mean(values))
                region_sem = _sem(values)
                ax.errorbar(
                    region_index,
                    region_mean,
                    yerr=region_sem if np.isfinite(region_sem) else None,
                    fmt="D",
                    markersize=6,
                    color="black",
                    markerfacecolor="white",
                    markeredgewidth=1.2,
                    capsize=4,
                    linewidth=1.3,
                    zorder=5,
                )
                regional_rows.append(
                    {
                        "unit_aggregation": aggregation,
                        "metric": metric,
                        "metric_title": title,
                        "region_call": region,
                        "recording_well_n": int(values.size),
                        "region_mean": region_mean,
                        "region_sem": region_sem,
                        "region_median": float(np.median(values)),
                        "region_max": float(np.max(values)),
                    }
                )
        counts = [
            int(
                pd.to_numeric(
                    organoids.loc[organoids["region_call"].eq(region), metric], errors="coerce"
                ).notna().sum()
            )
            for region in REGION_ORDER
        ]
        ax.set_xticks([0, 1], [f"Dorsal\nn={counts[0]}", f"Ventral\nn={counts[1]}"])
        ax.set_xlim(-0.38, 1.38)
        ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
        ax.grid(axis="y", color="#D9D9D9", linewidth=0.8, alpha=0.8)
        ax.spines[["top", "right"]].set_visible(False)

    variant_handles = [
        Line2D(
            [0], [0], marker=marker, linestyle="none", markerfacecolor="#777777",
            markeredgecolor="white", markersize=7, label=label,
        )
        for label, marker in VARIANT_MARKERS.items()
    ]
    mean_handle = Line2D(
        [0], [0], marker="D", linestyle="none", markerfacecolor="white",
        markeredgecolor="black", label="Regional mean +/- SEM",
    )
    fig.legend(
        handles=variant_handles + [mean_handle],
        loc="upper center",
        ncol=4,
        frameon=False,
        bbox_to_anchor=(0.5, 0.945),
    )
    fig.suptitle(
        "SUA spontaneous activity in dorsal and ventral forebrain organoids",
        fontsize=15,
        fontweight="bold",
        y=0.995,
    )
    fig.text(
        0.5,
        0.955,
        (
            f"Within-organoid SUA unit aggregation: {aggregation}; each point is one recording/well organoid; "
            "spike-bearing versions remain separate; bursts: ISI <= 100 ms, >= 3 spikes, duration >= 100 ms"
        ),
        ha="center",
        va="top",
        fontsize=9,
    )
    fig.tight_layout(rect=(0.02, 0.03, 0.98, 0.91), h_pad=2.0, w_pad=2.0)
    paths: list[Path] = []
    for suffix, kwargs in [("png", {"dpi": 300}), ("pdf", {}), ("svg", {})]:
        path = output_base.with_suffix(f".{suffix}")
        fig.savefig(path, bbox_inches="tight", facecolor="white", transparent=False, **kwargs)
        paths.append(path)
    plt.close(fig)
    return paths, regional_rows


def _aggregate(values: np.ndarray, aggregation: str) -> float:
    if values.size == 0:
        return np.nan
    if aggregation == "mean":
        return float(np.mean(values))
    if aggregation == "median":
        return float(np.median(values))
    if aggregation == "max":
        return float(np.max(values))
    raise ValueError(aggregation)


def _sem(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return np.nan
    return float(np.std(values, ddof=1) / np.sqrt(values.size))


if __name__ == "__main__":
    raise SystemExit(main())

