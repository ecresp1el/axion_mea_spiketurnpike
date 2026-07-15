#!/usr/bin/env python3
"""Visualize continuous PCHIP TTR90 classes in dorsal versus ventral cohorts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

FS_MAX_MS = 0.40
RS_MIN_MS = 0.56
CATEGORY_ORDER = [
    "high_confidence_FS_like",
    "indeterminate",
    "high_confidence_RS_like",
    "unclassified_atypical",
]
CATEGORY_LABELS = {
    "high_confidence_FS_like": "FS-like",
    "indeterminate": "Indeterminate",
    "high_confidence_RS_like": "RS-like",
    "unclassified_atypical": "Atypical",
}
CATEGORY_COLORS = {
    "high_confidence_FS_like": "#B8742A",
    "indeterminate": "#999999",
    "high_confidence_RS_like": "#58758E",
    "unclassified_atypical": "#D4D4D4",
}
REGION_COLORS = {"dorsal": "#6F8477", "ventral": "#C8A05A"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ventral-classifier-dir", type=Path, required=True)
    parser.add_argument("--ventral-audit-dir", type=Path, required=True)
    parser.add_argument("--dorsal-classifier-dir", type=Path, required=True)
    parser.add_argument("--dorsal-audit-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    ventral = _load_region(
        args.ventral_classifier_dir,
        args.ventral_audit_dir,
        "ventral",
    )
    dorsal = _load_region(
        args.dorsal_classifier_dir,
        args.dorsal_audit_dir,
        "dorsal",
    )
    units = pd.concat([dorsal, ventral], ignore_index=True)
    unexpected = sorted(set(units["ttr90_confidence_category"]) - set(CATEGORY_ORDER))
    if unexpected:
        raise ValueError(f"unexpected confidence categories: {unexpected}")

    channel_keys = [
        "region",
        "source_platform",
        "recording",
        "well",
        "template_best_channel_id",
    ]
    indicators = pd.DataFrame(index=units.index)
    for category in CATEGORY_ORDER:
        indicators[category] = units["ttr90_confidence_category"].eq(category).astype(float)
    channel_input = pd.concat([units[channel_keys + ["unit_key"]], indicators], axis=1)
    channel = (
        channel_input.groupby(channel_keys, dropna=False)
        .agg(
            unit_count=("unit_key", "size"),
            **{category: (category, "mean") for category in CATEGORY_ORDER},
        )
        .reset_index()
    )
    organoid_keys = ["region", "source_platform", "recording", "well"]
    organoid = (
        channel.groupby(organoid_keys, dropna=False)
        .agg(
            unit_count=("unit_count", "sum"),
            best_channel_count=("template_best_channel_id", "size"),
            **{category: (category, "mean") for category in CATEGORY_ORDER},
        )
        .reset_index()
    )

    unit_counts = (
        units.groupby(["region", "ttr90_confidence_category"], dropna=False)
        .size()
        .rename("unit_count")
        .reset_index()
    )
    complete = pd.MultiIndex.from_product(
        [["dorsal", "ventral"], CATEGORY_ORDER],
        names=["region", "ttr90_confidence_category"],
    )
    unit_counts = (
        unit_counts.set_index(["region", "ttr90_confidence_category"])
        .reindex(complete, fill_value=0)
        .reset_index()
    )
    unit_counts["region_unit_total"] = unit_counts.groupby("region")["unit_count"].transform("sum")
    unit_counts["unit_percent"] = 100.0 * unit_counts["unit_count"] / unit_counts["region_unit_total"]

    units.to_csv(output_dir / "dorsal_ventral_ttr90_040_056_units.csv", index=False)
    channel.to_csv(output_dir / "dorsal_ventral_ttr90_040_056_channel_proportions.csv", index=False)
    organoid.to_csv(output_dir / "dorsal_ventral_ttr90_040_056_organoid_proportions.csv", index=False)
    unit_counts.to_csv(output_dir / "dorsal_ventral_ttr90_040_056_unit_counts.csv", index=False)
    paths = _plot(units, organoid, unit_counts, output_dir)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "measurement": "continuous PCHIP-interpolated TTR90; not discretized",
        "classification": {
            "high_confidence_FS_like": "TTR90 <= 0.40 ms; canonical negative trough",
            "indeterminate": "0.40 < TTR90 < 0.56 ms; canonical negative trough",
            "high_confidence_RS_like": "TTR90 >= 0.56 ms; canonical negative trough",
            "unclassified_atypical": "positive-first or other atypical morphology",
        },
        "regional_definition": {
            "dorsal": "dorsal CytoView",
            "ventral": "ventral CytoView plus all Lumos",
        },
        "unit_counts": {
            region: {
                CATEGORY_LABELS[row["ttr90_confidence_category"]]: int(row["unit_count"])
                for _, row in unit_counts.loc[unit_counts["region"].eq(region)].iterrows()
            }
            for region in ["dorsal", "ventral"]
        },
        "organoid_observation_counts": organoid.groupby("region").size().astype(int).to_dict(),
        "aggregation": (
            "unit category indicators averaged within best-template channel, then "
            "channels averaged within source-platform/recording/well organoid observation"
        ),
        "figures": [str(path) for path in paths],
    }
    (output_dir / "dorsal_ventral_ttr90_040_056_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))
    return 0


def _load_region(classifier_dir: Path, audit_dir: Path, region: str) -> pd.DataFrame:
    classifier_dir = classifier_dir.expanduser().resolve()
    audit_dir = audit_dir.expanduser().resolve()
    metrics = pd.read_csv(classifier_dir / "ttr90_canonical_negative_unit_metrics.csv")
    audit = pd.read_csv(
        audit_dir / "waveform_source_audit_unit_metrics.csv",
        usecols=["unit_key", "template_best_channel_id", "template_best_channel_index"],
    )
    metrics["region"] = region
    return metrics.merge(audit, on="unit_key", validate="one_to_one")


def _plot(
    units: pd.DataFrame,
    organoid: pd.DataFrame,
    unit_counts: pd.DataFrame,
    output_dir: Path,
) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Liberation Sans", "Nimbus Sans", "DejaVu Sans"],
            "font.size": 7,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    fig = plt.figure(figsize=(11.5, 7.0), facecolor="white")
    grid = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.82], hspace=0.42, wspace=0.28)
    hist_axes = [fig.add_subplot(grid[0, index]) for index in range(2)]
    bins = np.arange(0.08, 1.001, 0.04)
    canonical_categories = CATEGORY_ORDER[:3]
    for axis, region in zip(hist_axes, ["dorsal", "ventral"], strict=True):
        regional = units.loc[units["region"].eq(region)]
        canonical = regional.loc[
            regional["ttr90_confidence_category"].isin(canonical_categories)
        ]
        weights = np.full(len(canonical), 100.0 / len(canonical))
        axis.axvspan(
            FS_MAX_MS,
            RS_MIN_MS,
            color=CATEGORY_COLORS["indeterminate"],
            alpha=0.14,
            linewidth=0,
            zorder=0,
        )
        for category in canonical_categories:
            mask = canonical["ttr90_confidence_category"].eq(category)
            axis.hist(
                pd.to_numeric(canonical.loc[mask, "ttr90_ms"], errors="coerce"),
                bins=bins,
                weights=weights[mask.to_numpy()],
                color=CATEGORY_COLORS[category],
                alpha=0.82,
                edgecolor="white",
                linewidth=0.35,
                label=f"{CATEGORY_LABELS[category]} (n={int(mask.sum())})",
            )
        axis.axvline(FS_MAX_MS, color="#333333", ls="--", lw=0.8)
        axis.axvline(RS_MIN_MS, color="#333333", ls="--", lw=0.8)
        axis.text(FS_MAX_MS - 0.01, 0.96, "0.40", transform=axis.get_xaxis_transform(), ha="right", va="top", fontsize=6)
        axis.text(RS_MIN_MS + 0.01, 0.96, "0.56", transform=axis.get_xaxis_transform(), ha="left", va="top", fontsize=6)
        axis.set_xlim(0.08, 1.00)
        axis.set_xlabel("Continuous PCHIP TTR90 (ms)")
        axis.set_ylabel("Canonical units per bin (%)")
        source_label = "CytoView" if region == "dorsal" else "CytoView + Lumos"
        axis.set_title(f"{region.title()} · {source_label} (n={len(regional)} total units)", loc="left", fontsize=8)
        axis.legend(frameon=False, fontsize=6)
        axis.tick_params(length=3, width=0.6)

    ax_composition = fig.add_subplot(grid[1, 0])
    left = np.zeros(2, dtype=float)
    for category in CATEGORY_ORDER:
        rows = unit_counts.loc[
            unit_counts["ttr90_confidence_category"].eq(category)
        ].set_index("region").loc[["dorsal", "ventral"]]
        values = rows["unit_percent"].to_numpy(float)
        bars = ax_composition.barh(
            [0, 1],
            values,
            left=left,
            color=CATEGORY_COLORS[category],
            edgecolor="white",
            linewidth=0.6,
            label=CATEGORY_LABELS[category],
        )
        for bar, count, percent, start in zip(
            bars,
            rows["unit_count"].to_numpy(int),
            values,
            left,
            strict=True,
        ):
            if percent >= 8:
                ax_composition.text(
                    start + percent / 2,
                    bar.get_y() + bar.get_height() / 2,
                    f"{count}\n{percent:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=6,
                    color="#222222" if category in ["indeterminate", "unclassified_atypical"] else "white",
                )
        left += values
    ax_composition.set_yticks([0, 1], ["Dorsal\nCytoView", "Ventral\nCytoView + Lumos"])
    ax_composition.invert_yaxis()
    ax_composition.set_xlim(0, 100)
    ax_composition.set_xlabel("Units (%)")
    ax_composition.set_title("Regional unit composition", loc="left", fontsize=8)
    ax_composition.legend(frameon=False, fontsize=6, ncol=2, loc="lower center", bbox_to_anchor=(0.5, -0.42))

    ax_organoid = fig.add_subplot(grid[1, 1])
    rng = np.random.default_rng(20260714)
    base = np.arange(len(CATEGORY_ORDER), dtype=float)
    offsets = {"dorsal": -0.13, "ventral": 0.13}
    for region in ["dorsal", "ventral"]:
        regional = organoid.loc[organoid["region"].eq(region)]
        for category_index, category in enumerate(CATEGORY_ORDER):
            values = pd.to_numeric(regional[category], errors="coerce").dropna() * 100.0
            jitter = rng.uniform(-0.045, 0.045, len(values))
            position = base[category_index] + offsets[region]
            ax_organoid.scatter(
                position + jitter,
                values,
                s=18,
                color=REGION_COLORS[region],
                alpha=0.50,
                linewidths=0,
            )
            if len(values):
                ax_organoid.errorbar(
                    position,
                    values.mean(),
                    yerr=values.sem() if len(values) > 1 else 0,
                    fmt="D",
                    ms=4,
                    mfc="white",
                    mec="#222222",
                    ecolor="#222222",
                    lw=0.8,
                    capsize=2.5,
                    zorder=4,
                )
        ax_organoid.scatter([], [], color=REGION_COLORS[region], s=20, label=region.title())
    ax_organoid.set_xticks(base, [CATEGORY_LABELS[category] for category in CATEGORY_ORDER], rotation=25, ha="right")
    ax_organoid.set_ylabel("Channel-weighted units per organoid (%)")
    ax_organoid.set_title("Organoid-level class proportions", loc="left", fontsize=8)
    ax_organoid.legend(frameon=False, fontsize=6)
    ax_organoid.grid(axis="y", color="#E5E5E5", lw=0.5)

    fig.suptitle(
        "Regional continuous PCHIP TTR90 classification",
        fontsize=10,
        fontweight="bold",
        y=0.98,
    )
    png = output_dir / "dorsal_ventral_ttr90_040_056_comparison.png"
    pdf = output_dir / "dorsal_ventral_ttr90_040_056_comparison.pdf"
    svg = output_dir / "dorsal_ventral_ttr90_040_056_comparison.svg"
    fig.savefig(png, dpi=600, facecolor="white", bbox_inches="tight")
    fig.savefig(pdf, facecolor="white", bbox_inches="tight")
    fig.savefig(svg, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return [png, pdf, svg]


if __name__ == "__main__":
    raise SystemExit(main())
