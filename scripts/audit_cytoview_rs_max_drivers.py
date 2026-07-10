#!/usr/bin/env python3
"""Rank SUA units that drive smoothed inverse-ISI maximum firing rates."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


JOB_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_RUN = (
    JOB_ROOT
    / "cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_20260710_061756"
)
DEFAULT_SOURCE = JOB_ROOT / "cytoview_dorsal_ventral_step1_20260709_unit_metrics.csv"
UNIT_METRIC = "inverse_isi_gaussian_temporal_max_hz"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--source-unit-metrics", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    units = pd.read_csv(run_dir / "cytoview_dv_sua_spontaneous_activity_20260710_unit_metrics.csv")
    source = pd.read_csv(args.source_unit_metrics.expanduser().resolve())
    quality_columns = [
        "recording",
        "well",
        "unit_id",
        "ContamPct",
        "isi_lt_2ms_count",
        "isi_count",
        "isi_lt_2ms_fraction",
        "template_ptp_best_channel_uV",
        "best_channel_index",
    ]
    units = units.merge(
        source[quality_columns],
        on=["recording", "well", "unit_id"],
        how="left",
        validate="one_to_one",
        suffixes=("", "_source"),
    )
    eligible = units.loc[
        units["inverse_isi_gaussian_eligible"].astype(bool) & units[UNIT_METRIC].notna()
    ].copy()
    if eligible.empty:
        raise SystemExit("No units have a defined smoothed inverse-ISI maximum")

    organoids = (
        eligible.groupby(
            ["recording_well_id", "recording", "well", "region_call", "raw_variant"],
            as_index=False,
        )
        .agg(
            eligible_unit_count=("unit_key", "size"),
            organoid_temporal_max_mean_hz=(UNIT_METRIC, "mean"),
            organoid_temporal_max_sum_hz=(UNIT_METRIC, "sum"),
        )
    )
    region_means = organoids.groupby("region_call")["organoid_temporal_max_mean_hz"].mean()
    region_counts = organoids.groupby("region_call")["recording_well_id"].nunique()

    rows: list[dict[str, object]] = []
    for recording_well_id, group in eligible.groupby("recording_well_id", sort=True):
        group = group.sort_values(UNIT_METRIC, ascending=False)
        values = group[UNIT_METRIC].to_numpy(dtype=float)
        count = int(values.size)
        organoid_mean = float(np.mean(values))
        organoid_sum = float(np.sum(values))
        region = str(group.iloc[0]["region_call"])
        regional_organoids = organoids.loc[organoids["region_call"].eq(region)].copy()
        current_region_mean = float(region_means.loc[region])
        for rank, (_, unit) in enumerate(group.iterrows(), start=1):
            unit_value = float(unit[UNIT_METRIC])
            if count > 1:
                loo_organoid_value = float((organoid_sum - unit_value) / (count - 1))
                revised_values = regional_organoids["organoid_temporal_max_mean_hz"].to_numpy(
                    dtype=float
                ).copy()
                target_index = int(
                    np.flatnonzero(
                        regional_organoids["recording_well_id"].eq(recording_well_id).to_numpy()
                    )[0]
                )
                revised_values[target_index] = loo_organoid_value
            else:
                loo_organoid_value = np.nan
                revised_values = regional_organoids.loc[
                    ~regional_organoids["recording_well_id"].eq(recording_well_id),
                    "organoid_temporal_max_mean_hz",
                ].to_numpy(dtype=float)
            revised_region_mean = float(np.mean(revised_values)) if revised_values.size else np.nan
            rows.append(
                unit.to_dict()
                | {
                    "eligible_unit_count_in_recording_well": count,
                    "rank_by_temporal_max_within_recording_well": rank,
                    "organoid_temporal_max_mean_hz": organoid_mean,
                    "unit_share_of_summed_temporal_max": (
                        unit_value / organoid_sum if organoid_sum > 0 else np.nan
                    ),
                    "leave_one_unit_out_organoid_value_hz": loo_organoid_value,
                    "leave_one_unit_out_organoid_reduction_hz": (
                        organoid_mean - loo_organoid_value if count > 1 else np.nan
                    ),
                    "single_unit_controls_recording_well_value": bool(count == 1),
                    "region_recording_well_count": int(region_counts.loc[region]),
                    "region_mean_temporal_max_hz": current_region_mean,
                    "region_mean_if_unit_removed_hz": revised_region_mean,
                    "region_mean_reduction_if_unit_removed_hz": (
                        current_region_mean - revised_region_mean
                        if np.isfinite(revised_region_mean)
                        else np.nan
                    ),
                    "screen_ContamPct_gt10": bool(float(unit["ContamPct"]) > 10.0),
                    "screen_isi_lt_2ms_fraction_gt1pct": bool(
                        float(unit["isi_lt_2ms_fraction"]) > 0.01
                    ),
                }
            )

    drivers = pd.DataFrame(rows)
    drivers["region_class_driver_rank"] = (
        drivers.groupby(["region_call", "aligned_fs_rs_class"])[
            "region_mean_reduction_if_unit_removed_hz"
        ]
        .rank(method="first", ascending=False)
        .astype(int)
    )
    drivers = drivers.sort_values(
        ["region_call", "aligned_fs_rs_class", "region_class_driver_rank"]
    ).reset_index(drop=True)
    drivers.to_csv(output_dir / "sua_temporal_max_unit_driver_table.csv", index=False)
    organoids.to_csv(output_dir / "sua_temporal_max_organoid_table.csv", index=False)

    top_dorsal_rs = drivers.loc[
        drivers["region_call"].eq("dorsal") & drivers["aligned_fs_rs_class"].eq("RS")
    ].nsmallest(25, "region_class_driver_rank")
    top_dorsal_rs.to_csv(output_dir / "top_25_dorsal_rs_temporal_max_drivers.csv", index=False)
    _plot_audit(drivers, organoids, output_dir)

    print(f"Eligible units ranked: {len(drivers)}")
    print(f"Organoid recording/well observations: {len(organoids)}")
    print(f"Dorsal RS units ranked: {len(top_dorsal_rs)} shown of "
          f"{len(drivers.loc[drivers['region_call'].eq('dorsal') & drivers['aligned_fs_rs_class'].eq('RS')])}")
    print(f"Output directory: {output_dir}")
    return 0


def _plot_audit(drivers: pd.DataFrame, organoids: pd.DataFrame, output_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(14.5, 10.0))
    fig.patch.set_facecolor("white")

    ax = axes[0, 0]
    positions = {
        ("dorsal", "RS"): 0,
        ("dorsal", "FS"): 1,
        ("ventral", "RS"): 3,
        ("ventral", "FS"): 4,
    }
    colors = {"dorsal": "#2A9D8F", "ventral": "#6A4C93"}
    rng = np.random.default_rng(20260710)
    for (region, unit_class), position in positions.items():
        subset = drivers.loc[
            drivers["region_call"].eq(region)
            & drivers["aligned_fs_rs_class"].eq(unit_class)
        ]
        x = position + rng.uniform(-0.12, 0.12, len(subset))
        ax.scatter(x, subset[UNIT_METRIC], s=30, color=colors[region], alpha=0.72)
    ax.set_xticks([0, 1, 3, 4], ["Dorsal RS", "Dorsal FS", "Ventral RS", "Ventral FS"])
    ax.set_ylabel("Per-unit temporal maximum (Hz)")
    ax.set_title("A. Unit-level maxima by region and waveform class", loc="left", fontweight="bold")

    ax = axes[0, 1]
    top = drivers.loc[
        drivers["region_call"].eq("dorsal") & drivers["aligned_fs_rs_class"].eq("RS")
    ].nlargest(15, "region_mean_reduction_if_unit_removed_hz").sort_values(
        "region_mean_reduction_if_unit_removed_hz"
    )
    labels = [
        f"{row.well} | {row.raw_variant.replace('_raw', '')} | u{_unit_id_text(row.unit_id)}"
        for row in top.itertuples()
    ]
    concern = top["screen_ContamPct_gt10"] | top["screen_isi_lt_2ms_fraction_gt1pct"]
    bar_colors = np.where(concern, "#D1495B", "#2A9D8F")
    ax.barh(np.arange(len(top)), top["region_mean_reduction_if_unit_removed_hz"], color=bar_colors)
    ax.set_yticks(np.arange(len(top)), labels, fontsize=8)
    ax.set_xlabel("Reduction in dorsal mean if unit is removed (Hz)")
    ax.set_title("B. Top dorsal RS influence ranking", loc="left", fontweight="bold")

    ax = axes[1, 0]
    dorsal_rs = drivers.loc[
        drivers["region_call"].eq("dorsal") & drivers["aligned_fs_rs_class"].eq("RS")
    ]
    sizes = 28 + 12 * np.sqrt(dorsal_rs["eligible_unit_count_in_recording_well"])
    scatter = ax.scatter(
        dorsal_rs["organoid_temporal_max_mean_hz"],
        dorsal_rs["unit_share_of_summed_temporal_max"],
        c=dorsal_rs["template_ptp_best_channel_uV"],
        s=sizes,
        cmap="viridis",
        alpha=0.8,
        edgecolor="white",
        linewidth=0.6,
    )
    ax.set_xlabel("Recording/well temporal-maximum value (Hz)")
    ax.set_ylabel("Unit share of summed unit maxima")
    ax.set_title("C. Dependence of dorsal RS observations on individual units", loc="left", fontweight="bold")
    fig.colorbar(scatter, ax=ax, label="Template PTP (uV)")

    ax = axes[1, 1]
    top_qc = drivers.loc[
        drivers["region_call"].eq("dorsal") & drivers["aligned_fs_rs_class"].eq("RS")
    ].nlargest(15, "region_mean_reduction_if_unit_removed_hz")
    scatter = ax.scatter(
        top_qc["ContamPct"],
        100 * top_qc["isi_lt_2ms_fraction"],
        c=top_qc[UNIT_METRIC],
        s=45 + 2 * top_qc["template_ptp_best_channel_uV"],
        cmap="magma",
        alpha=0.82,
        edgecolor="white",
        linewidth=0.7,
    )
    for row in top_qc.itertuples():
        ax.annotate(
            f"{row.well}-u{_unit_id_text(row.unit_id)}",
            (row.ContamPct, 100 * row.isi_lt_2ms_fraction),
            xytext=(3, 3),
            textcoords="offset points",
            fontsize=7,
        )
    ax.axvline(10, color="#777777", linestyle="--", linewidth=1)
    ax.axhline(1, color="#777777", linestyle="--", linewidth=1)
    ax.set_xlabel("ContamPct (%)")
    ax.set_ylabel("ISIs <2 ms (%)")
    ax.set_title("D. QC context for top dorsal RS drivers", loc="left", fontweight="bold")
    fig.colorbar(scatter, ax=ax, label="Per-unit temporal maximum (Hz)")

    for ax in axes.ravel():
        ax.grid(axis="y", color="#E0E0E0", linewidth=0.7, alpha=0.8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(
        "Iteration 1: units driving smoothed inverse-ISI maximum firing rates",
        fontsize=16,
        fontweight="bold",
        y=0.995,
    )
    fig.text(
        0.5,
        0.967,
        (
            "Influence ranking is diagnostic only, not an exclusion rule; input population has "
            "KSLabel=good and template PTP >=10 uV"
        ),
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0.02, 0.02, 0.99, 0.95), h_pad=2.4, w_pad=2.2)
    base = output_dir / "sua_temporal_max_rs_driver_audit"
    fig.savefig(base.with_suffix(".png"), dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    fig.savefig(base.with_suffix(".svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _unit_id_text(value: object) -> str:
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
