#!/usr/bin/env python3
"""Plot mean, median, and maximum SUA activity summaries by region."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


REGION_ORDER = ["dorsal", "ventral"]
REGION_COLORS = {"dorsal": "#2A9D8F", "ventral": "#6A4C93"}
STAT_ORDER = ["mean", "median", "max"]
STAT_COLORS = {"mean": "#222222", "median": "#E69F00", "max": "#D55E00"}
STAT_MARKERS = {"mean": "D", "median": "o", "max": "^"}
METRICS = [
    ("mean_unit_firing_rate_hz", "Overall mean firing rate", "Hz"),
    ("mean_unit_burst_rate_per_min", "Burst rate", "bursts/min"),
    ("mean_unit_firing_rate_within_bursts_hz", "Firing rate within bursts", "Hz"),
    ("mean_unit_burst_duration_ms", "Burst duration", "ms"),
    ("mean_unit_interburst_interval_s", "Inter-burst interval", "s"),
    ("mean_unit_spikes_per_burst", "Spikes per burst", "spikes/burst"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=Path(
            "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
            "step1_nonlfp_th5_v5_ground_truth_latest/cytoview_dv_sua_spontaneous_activity_20260710_20260710_052817/"
            "cytoview_dv_sua_spontaneous_activity_20260710_recording_well_summary.csv"
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--date-label", default="20260710")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_csv = args.input_csv.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    wells = pd.read_csv(input_csv)

    rows: list[dict[str, object]] = []
    for metric, title, units in METRICS:
        for region in REGION_ORDER:
            values = pd.to_numeric(
                wells.loc[wells["region_call"].eq(region), metric], errors="coerce"
            ).dropna().to_numpy(dtype=float)
            for statistic in STAT_ORDER:
                value = np.nan
                if values.size:
                    value = {
                        "mean": float(np.mean(values)),
                        "median": float(np.median(values)),
                        "max": float(np.max(values)),
                    }[statistic]
                rows.append(
                    {
                        "metric": metric,
                        "metric_title": title,
                        "units": units,
                        "region_call": region,
                        "statistic": statistic,
                        "value": value,
                        "n_contributing_recording_wells": int(values.size),
                    }
                )
    summary = pd.DataFrame(rows)
    stem = f"cytoview_dv_sua_activity_mean_median_max_{args.date_label}"
    summary_csv = output_dir / f"{stem}_summary.csv"
    figure_png = output_dir / f"{stem}.png"
    figure_pdf = output_dir / f"{stem}.pdf"
    figure_svg = output_dir / f"{stem}.svg"
    provenance_json = output_dir / f"{stem}_provenance.json"
    summary.to_csv(summary_csv, index=False)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, axes = plt.subplots(2, 3, figsize=(14.5, 8.8), constrained_layout=False)
    fig.patch.set_facecolor("white")
    for ax, (metric, title, units) in zip(axes.ravel(), METRICS, strict=True):
        ax.set_facecolor("white")
        panel = summary.loc[summary["metric"].eq(metric)]
        for region_index, region in enumerate(REGION_ORDER):
            region_values = panel.loc[panel["region_call"].eq(region)]
            for stat_index, statistic in enumerate(STAT_ORDER):
                record = region_values.loc[region_values["statistic"].eq(statistic)].iloc[0]
                value = record["value"]
                if pd.isna(value):
                    continue
                x = region_index + (stat_index - 1) * 0.16
                ax.scatter(
                    x,
                    value,
                    s=80,
                    marker=STAT_MARKERS[statistic],
                    facecolor=STAT_COLORS[statistic],
                    edgecolor="white",
                    linewidth=0.8,
                    zorder=3,
                )
                ax.annotate(
                    _format_value(float(value)),
                    (x, float(value)),
                    xytext=(0, 7),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color=STAT_COLORS[statistic],
                )
        ax.set_xticks([0, 1], ["Dorsal", "Ventral"])
        ax.set_xlim(-0.45, 1.45)
        ax.set_ylabel(f"{title} ({units})")
        ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
        ax.grid(axis="y", color="#D9D9D9", linewidth=0.8, alpha=0.8)
        ax.spines[["top", "right"]].set_visible(False)

    handles = [
        Line2D(
            [0],
            [0],
            marker=STAT_MARKERS[statistic],
            linestyle="none",
            markerfacecolor=STAT_COLORS[statistic],
            markeredgecolor="white",
            markersize=8,
            label=statistic.capitalize(),
        )
        for statistic in STAT_ORDER
    ]
    fig.legend(handles=handles, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.945))
    fig.suptitle(
        "SUA spontaneous activity: mean, median, and maximum by region",
        fontsize=15,
        fontweight="bold",
        y=0.995,
    )
    fig.text(
        0.5,
        0.955,
        "KSLabel=good; all non-LFP recording/well organoids retained; no recording-kind filter",
        ha="center",
        va="top",
        fontsize=9,
    )
    fig.tight_layout(rect=(0.02, 0.03, 0.98, 0.91), h_pad=2.0, w_pad=2.0)
    for path, kwargs in [
        (figure_png, {"dpi": 300}),
        (figure_pdf, {}),
        (figure_svg, {}),
    ]:
        fig.savefig(path, bbox_inches="tight", facecolor="white", transparent=False, **kwargs)
    plt.close(fig)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "input_recording_well_summary": str(input_csv),
        "output_dir": str(output_dir),
        "all_non_lfp_recording_wells": int(len(wells)),
        "recording_wells_with_sua": int(wells["recording_well_has_sua"].sum()),
        "recording_wells_without_sua": int((~wells["recording_well_has_sua"]).sum()),
        "statistics": STAT_ORDER,
        "metrics": [metric for metric, _, _ in METRICS],
        "outputs": {
            "summary_csv": str(summary_csv),
            "figure_png": str(figure_png),
            "figure_pdf": str(figure_pdf),
            "figure_svg": str(figure_svg),
        },
    }
    provenance_json.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(f"Summary CSV: {summary_csv}")
    print(f"PNG: {figure_png}")
    print(f"PDF: {figure_pdf}")
    print(f"SVG: {figure_svg}")
    return 0


def _format_value(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


if __name__ == "__main__":
    raise SystemExit(main())

