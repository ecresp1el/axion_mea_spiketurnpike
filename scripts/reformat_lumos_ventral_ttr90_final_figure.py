#!/usr/bin/env python3
"""Reformat the locked Lumos + ventral CytoView TTR90 population figure.

This renderer changes graphical hierarchy only.  It reuses the persisted unit,
organoid, TTR90, and representative-unit sources from the July 14 population
figure and embeds the separately locked same-well spatial/ACG/CCG QC panel.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_cytoview_unified_rsfs_activity_figure as unified


PROJECT_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder"
)
DEFAULT_SOURCE_DIR = (
    PROJECT_ROOT
    / "FINAL FIG 2/Population Panels/ventral_MGE_putative_FS_RS_"
    "TTR90_PCHIP_040_056_FINAL"
)
DEFAULT_LOCKED_QC_PNG = (
    PROJECT_ROOT
    / "FINAL FIG 2/Population Panels/"
    "LOCKED_FINAL_putative_FS_RS_same_well_spatial_ACG_CCG_20260714/"
    "putative_FS_RS_same_well_spatial_ACG_CCG_FINAL.png"
)
DEFAULT_QC_CANDIDATE_MANIFEST = (
    DEFAULT_SOURCE_DIR
    / "mixed_high_confidence_FS_RS_well_QC_candidates_20260714/"
    "mixed_FS_RS_well_QC_candidate_manifest.csv"
)
DEFAULT_OUTPUT_DIR = (
    DEFAULT_SOURCE_DIR / "reformatted_histogram_best_units_activity_grid_20260714"
)
DEFAULT_REPRESENTATIVE_SHORTLIST = (
    DEFAULT_OUTPUT_DIR
    / "top4_FS_RS_representative_candidates_20260714/"
    "top4_putative_FS_RS_representative_selection_shortlist.csv"
)
FINAL_REPRESENTATIVE_IDS = {"FS": "FS3", "RS": "RS2"}

WAVEFORM_METRIC_SPECS = [
    ("ttr90_ms", "TTR90", "ms", "continuous PCHIP 90% rebound timing"),
    (
        "raw_discrete_trough_to_global_peak_ms",
        "Raw global-peak TTP",
        "ms",
        "discrete trough-to-global-post-trough-maximum timing",
    ),
    (
        "pchip_trough_to_global_peak_ms",
        "PCHIP global-peak TTP",
        "ms",
        "PCHIP trough-to-global-post-trough-maximum timing",
    ),
    ("after_spike_half_width_ms", "Spike half-width", "ms", "aligned waveform half-width"),
    (
        "after_repolarization_time_ms",
        "Repolarization time",
        "ms",
        "aligned waveform repolarization time",
    ),
    (
        "after_template_ptp_best_channel_uV",
        "Template PTP",
        "µV",
        "template peak-to-peak amplitude on the best-P2P channel",
    ),
    (
        "after_spiketurnpike_amplitude_uV",
        "Spike amplitude",
        "µV",
        "SpikeTurnpike waveform amplitude",
    ),
    (
        "after_pre_peak_amplitude_uV",
        "Pre-peak amplitude",
        "µV",
        "pre-trough positive-peak amplitude",
    ),
    (
        "after_post_peak_amplitude_uV",
        "Post-peak amplitude",
        "µV",
        "post-trough positive-peak amplitude",
    ),
    (
        "after_depolarization_slope_uV_per_ms",
        "Depolarization slope",
        "µV/ms",
        "aligned pre-trough depolarization slope",
    ),
    (
        "after_post_trough_rebound_slope_uV_per_ms",
        "Rebound slope",
        "µV/ms",
        "aligned post-trough rebound slope",
    ),
    (
        "after_rep50_recovery_slope_uV_per_ms",
        "Rep50 recovery slope",
        "µV/ms",
        "aligned 50% repolarization recovery slope",
    ),
    (
        "after_waveform_asymmetry",
        "Waveform asymmetry",
        "dimensionless",
        "aligned pre/post waveform asymmetry",
    ),
    (
        "after_peak_to_peak_ratio",
        "Peak ratio",
        "dimensionless",
        "aligned pre-peak to post-peak amplitude ratio",
    ),
    (
        "rebound_amplitude_uV",
        "Rebound amplitude",
        "µV",
        "post-window maximum minus principal trough voltage",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--locked-qc-png", type=Path, default=DEFAULT_LOCKED_QC_PNG)
    parser.add_argument(
        "--qc-candidate-manifest",
        type=Path,
        default=DEFAULT_QC_CANDIDATE_MANIFEST,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--representative-shortlist",
        type=Path,
        default=DEFAULT_REPRESENTATIVE_SHORTLIST,
    )
    parser.add_argument(
        "--output-stem",
        default="lumos_ventral_putative_fsrs_ttr90_reformatted_FINAL",
    )
    parser.add_argument("--export-formats", default="png,pdf,svg")
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _best_asset_per_class(
    assets: list[dict[str, object]],
) -> tuple[dict[str, dict[str, object]], pd.DataFrame]:
    """Choose one visually strong unit per class, prioritizing clean ACGs."""
    audit_rows: list[dict[str, object]] = []
    for asset in assets:
        metadata = asset["metadata"]
        p_refractory = float(asset["probability"]["p_refractory"])
        acg_support_count = float(
            np.nansum(np.asarray(asset["probability"]["counts"], dtype=float))
        )
        spike_count = float(metadata.get("source_spike_count", np.nan))
        template_ptp = float(metadata.get("template_ptp_best_channel_uV", np.nan))
        contamination = float(metadata.get("source_ContamPct", np.nan))
        secondary_score = (
            np.log1p(max(spike_count, 0.0))
            + np.log1p(max(template_ptp, 0.0))
            - 0.02 * max(contamination, 0.0)
        )
        audit_rows.append(
            {
                "unit_key": metadata["unit_key"],
                "rs_fs_class": metadata["rs_fs_class"],
                "source_platform": metadata["source_platform"],
                "recording": metadata["recording"],
                "well": metadata["well"],
                "unit_id": metadata["unit_id"],
                "ttr90_ms": metadata["feature_ttp_ms"],
                "source_spike_count": spike_count,
                "template_ptp_best_channel_uV": template_ptp,
                "source_ContamPct": contamination,
                "acg_refractory_probability": p_refractory,
                "acg_support_count": acg_support_count,
                "secondary_visual_quality_score": secondary_score,
            }
        )
    audit = pd.DataFrame(audit_rows)
    audit["selected"] = False
    selected: dict[str, dict[str, object]] = {}
    for class_label in unified.CLASS_ORDER:
        candidates = audit.loc[audit["rs_fs_class"].eq(class_label)].sort_values(
            [
                "acg_refractory_probability",
                "acg_support_count",
                "secondary_visual_quality_score",
            ],
            ascending=[True, False, False],
        )
        if candidates.empty:
            raise ValueError(f"No representative candidates were available for {class_label}")
        selected_key = str(candidates.iloc[0]["unit_key"])
        audit.loc[audit["unit_key"].eq(selected_key), "selected"] = True
        selected[class_label] = next(
            asset for asset in assets if str(asset["metadata"]["unit_key"]) == selected_key
        )
    return selected, audit.sort_values(
        [
            "rs_fs_class",
            "selected",
            "acg_refractory_probability",
            "acg_support_count",
            "secondary_visual_quality_score",
        ],
        ascending=[True, False, True, False, False],
    )


def _load_final_representatives_from_shortlist(
    shortlist: pd.DataFrame,
) -> tuple[dict[str, dict[str, object]], pd.DataFrame]:
    """Load the explicitly locked final FS3 and RS2 representative assets."""
    required = {
        "representative_display_id",
        "rs_fs_class",
        "unit_key",
        "analyzer_path",
        "feature_ttp_ms",
        "source_spike_count",
        "source_ContamPct",
    }
    missing = sorted(required - set(shortlist.columns))
    if missing:
        raise ValueError(f"Representative shortlist is missing columns: {missing}")
    selected_rows: list[pd.Series] = []
    audit = shortlist.copy()
    audit["selected"] = False
    for class_label in unified.CLASS_ORDER:
        display_id = FINAL_REPRESENTATIVE_IDS[class_label]
        candidate = audit.loc[
            audit["rs_fs_class"].eq(class_label)
            & audit["representative_display_id"].eq(display_id)
        ]
        if len(candidate) != 1:
            raise ValueError(
                f"Final representative {display_id} was not uniquely present: n={len(candidate)}"
            )
        row = candidate.iloc[0].copy()
        row["final_representative_display_id"] = display_id
        row["representative_order_within_class"] = 1
        selected_rows.append(row)
        audit.loc[candidate.index, "selected"] = True
    selection = pd.DataFrame(selected_rows)
    assets = unified._load_representative_assets(selection)
    selected_assets = {
        str(asset["metadata"]["rs_fs_class"]): asset for asset in assets
    }
    if set(selected_assets) != set(unified.CLASS_ORDER):
        raise ValueError(
            f"Final representative classes are incomplete: {sorted(selected_assets)}"
        )
    return selected_assets, audit


def _plot_mean_waveform_histogram_inset(ax, waveform_summary: pd.DataFrame) -> None:
    """Add the original-amplitude FS/RS mean waveforms within the TTR90 histogram."""
    from matplotlib.patches import FancyBboxPatch

    bounds = [0.57, 0.55, 0.40, 0.38]
    ax.add_patch(
        FancyBboxPatch(
            (bounds[0] - 0.015, bounds[1] - 0.025),
            bounds[2] + 0.025,
            bounds[3] + 0.045,
            transform=ax.transAxes,
            boxstyle="round,pad=0.004,rounding_size=0.018",
            facecolor="white",
            edgecolor="#D4D4D4",
            linewidth=0.45,
            alpha=0.94,
            zorder=7,
        )
    )
    inset = ax.inset_axes(bounds, zorder=8)
    unified._plot_panel_a_mean_waveforms(inset, waveform_summary)
    for line in inset.lines:
        line.set_linewidth(min(float(line.get_linewidth()), 0.85))


def _plot_c01_view3_feature_space(ax, waveform_metrics: pd.DataFrame) -> None:
    """Plot the locked C01/View 3 waveform space from the exported unit table."""
    from matplotlib.lines import Line2D

    category_order = [
        "High-confidence FS",
        "Indeterminate canonical",
        "High-confidence RS",
    ]
    expected_counts = {
        "High-confidence FS": 73,
        "Indeterminate canonical": 55,
        "High-confidence RS": 24,
    }
    plotted_columns = [
        "ttr90_ms",
        "after_post_trough_rebound_slope_uV_per_ms",
        "after_waveform_asymmetry",
        "inverse_isi_gaussian_temporal_p99_9_hz",
    ]
    required_columns = ["current_plot_category", *plotted_columns]
    missing_columns = [
        column for column in required_columns if column not in waveform_metrics.columns
    ]
    if missing_columns:
        raise ValueError(f"C01/View 3 source is missing columns: {missing_columns}")

    plotted = waveform_metrics.loc[
        waveform_metrics["current_plot_category"].isin(category_order),
        required_columns,
    ].copy()
    for column in plotted_columns:
        plotted[column] = pd.to_numeric(plotted[column], errors="coerce")
    finite = np.isfinite(plotted[plotted_columns].to_numpy(dtype=float)).all(axis=1)
    plotted = plotted.loc[finite].copy()
    observed_counts = (
        plotted["current_plot_category"]
        .value_counts()
        .reindex(category_order, fill_value=0)
        .astype(int)
        .to_dict()
    )
    if observed_counts != expected_counts:
        raise ValueError(
            "C01/View 3 filtered class counts do not match the locked denominator: "
            f"observed={observed_counts}, expected={expected_counts}"
        )

    rate_col = "inverse_isi_gaussian_temporal_p99_9_hz"
    rate_cap = float(plotted[rate_col].quantile(0.99))
    rate_for_size = plotted[rate_col].clip(upper=rate_cap)
    rmin = float(rate_for_size.min())
    rmax = float(rate_for_size.max())
    if rmax > rmin:
        plotted["_marker_area"] = 18.0 + (
            (rate_for_size - rmin) / (rmax - rmin)
        ) * (120.0 - 18.0)
    else:
        plotted["_marker_area"] = 60.0
    # The reference V07 plot uses a 6.144-inch-square 3D axis, whereas this
    # fixed multipanel layout provides a 2.102014-inch-square 3D axis. Scale
    # marker *area* by the squared linear-size ratio so the embedded points
    # retain the same apparent size relative to the axes as the V07 reference.
    multipanel_marker_area_scale = (
        (2.1020142254324936 / 6.144) ** 2 * 1.30 * 1.50 * 1.50
    )
    plotted["_marker_area"] *= multipanel_marker_area_scale

    category_style = {
        "High-confidence FS": {"label": "FS", "color": "#D28E3D", "alpha": 0.90},
        "Indeterminate canonical": {
            "label": "Indeterminate",
            "color": "#C7C7C7",
            "alpha": 0.40,
        },
        "High-confidence RS": {"label": "RS", "color": "#6F8799", "alpha": 0.90},
    }
    # The plotting order is intentional: ambiguous units recede behind the two
    # high-confidence classes while depth shading remains disabled.
    for category in [
        "Indeterminate canonical",
        "High-confidence FS",
        "High-confidence RS",
    ]:
        subset = plotted.loc[plotted["current_plot_category"].eq(category)]
        style = category_style[category]
        ax.scatter(
            subset["ttr90_ms"],
            subset["after_post_trough_rebound_slope_uV_per_ms"],
            subset["after_waveform_asymmetry"],
            s=subset["_marker_area"],
            marker="o",
            color=style["color"],
            alpha=style["alpha"],
            edgecolors="white",
            linewidths=0.40,
            depthshade=False,
            rasterized=False,
        )

    def limits_with_margin(values: pd.Series, fraction: float = 0.05) -> tuple[float, float]:
        lower = float(values.min())
        upper = float(values.max())
        span = max(upper - lower, np.finfo(float).eps)
        return lower - fraction * span, upper + fraction * span

    ax.set_xlim(limits_with_margin(plotted["ttr90_ms"]))
    ax.set_ylim(
        limits_with_margin(plotted["after_post_trough_rebound_slope_uV_per_ms"])
    )
    ax.set_zlim(limits_with_margin(plotted["after_waveform_asymmetry"]))
    ax.set_xticks([0.2, 0.4, 0.6, 0.8])
    ax.set_yticks([0, 50, 100, 150])
    ax.set_zticks([-0.4, -0.2, 0.0, 0.2])
    ax.set_xlabel("TTP (ms)", labelpad=5.0)
    ax.set_ylabel(r"Rebound slope (µV ms$^{-1}$)", labelpad=5.0)
    ax.set_zlabel("Waveform asymmetry", labelpad=2.0)
    ax.set_title("")
    ax.view_init(elev=12, azim=280)
    ax.set_proj_type("persp")
    ax.tick_params(axis="both", which="major", labelsize=6.5, pad=0.8, width=0.55)

    pane_color = (0.988, 0.988, 0.988, 1.0)
    grid_color = (0.82, 0.82, 0.82, 0.72)
    axis_color = "#666666"
    for axis in [ax.xaxis, ax.yaxis, ax.zaxis]:
        axis.set_pane_color(pane_color)
        axis._axinfo["grid"].update(
            {"color": grid_color, "linewidth": 0.45, "linestyle": "-"}
        )
        axis._axinfo["axisline"].update({"color": axis_color, "linewidth": 0.60})
        axis.line.set_color(axis_color)
        axis.line.set_linewidth(0.60)

    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markerfacecolor=category_style[category]["color"],
            markeredgecolor="white",
            markeredgewidth=0.45,
            markersize=5.2,
            label=(
                f"{category_style[category]['label']} "
                f"(n={observed_counts[category]})"
            ),
        )
        for category in category_order
    ]
    class_legend = ax.legend(
        handles=legend_handles,
        loc="upper left",
        bbox_to_anchor=(0.015, 0.995),
        frameon=False,
        fontsize=5.4,
        borderaxespad=0.0,
        handletextpad=0.35,
        labelspacing=0.24,
    )
    ax.add_artist(class_legend)

    size_legend_rates = [5.0, 35.0, 70.0]
    if rmax > rmin:
        size_legend_areas = [
            (
                18.0
                + (np.clip(rate, rmin, rmax) - rmin)
                / (rmax - rmin)
                * (120.0 - 18.0)
            )
            * multipanel_marker_area_scale
            for rate in size_legend_rates
        ]
    else:
        size_legend_areas = [60.0 * multipanel_marker_area_scale] * 3
    size_legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markerfacecolor="#777777",
            markeredgecolor="white",
            markeredgewidth=0.40,
            markersize=float(np.sqrt(area)),
            label=f"{rate:g}",
        )
        for rate, area in zip(size_legend_rates, size_legend_areas, strict=True)
    ]
    size_legend = ax.legend(
        handles=size_legend_handles,
        title="Firing Rate (Hz)",
        loc="upper center",
        bbox_to_anchor=(0.59, 0.995),
        ncol=3,
        frameon=False,
        fontsize=4.9,
        borderaxespad=0.0,
        handletextpad=0.25,
        columnspacing=0.45,
        labelspacing=0.20,
    )
    size_legend.get_title().set_fontsize(5.2)

    print("3D FS-RS waveform plot QC:")
    print("  camera elevation = 12")
    print("  camera azimuth = 280")
    print("  custom box aspect applied = no")
    print(f"  FS units = {observed_counts['High-confidence FS']}")
    print(f"  RS units = {observed_counts['High-confidence RS']}")
    print(f"  Indeterminate units = {observed_counts['Indeterminate canonical']}")
    print(f"  firing-rate minimum = {float(plotted[rate_col].min()):.9g}")
    print(f"  firing-rate maximum = {float(plotted[rate_col].max()):.9g}")
    print(f"  firing-rate 99th percentile = {rate_cap:.9g}")
    print(f"  minimum marker area = {float(plotted['_marker_area'].min()):.9g}")
    print(f"  maximum marker area = {float(plotted['_marker_area'].max()):.9g}")
    print(f"  multipanel marker-area scale = {multipanel_marker_area_scale:.9g}")
    print("  marker-size scaling computed globally across all plotted classes = yes")


def _plot_same_well_qc_stack(
    fig,
    spatial_spec,
    correlogram_spec,
    qc_well,
    qc_args,
) -> None:
    """Plot the approved QC well as spatial footprints above its ACG/CCG matrix."""
    from scripts import plot_ttr90_mixed_fs_rs_well_qc_gallery as qc_gallery

    ax_spatial = fig.add_subplot(spatial_spec)
    qc_gallery.plot_nature_spatial_map(ax_spatial, qc_well, qc_args)

    correlogram_block = correlogram_spec.subgridspec(
        2,
        1,
        height_ratios=[0.13, 0.87],
        hspace=0.015,
    )
    ax_corr_title = fig.add_subplot(correlogram_block[0, 0])
    ax_corr_title.set_axis_off()
    ax_corr_title.text(
        0.0,
        0.68,
        "ACGs (diagonal) · CCGs (upper triangle)",
        transform=ax_corr_title.transAxes,
        ha="left",
        va="center",
        fontsize=7.0,
        color="#666666",
    )
    unit_count = len(qc_well.units)
    matrix = correlogram_block[1, 0].subgridspec(
        unit_count,
        unit_count,
        wspace=0.48,
        hspace=0.38,
    )
    for row_index, row_unit in enumerate(qc_well.units):
        for col_index, col_unit in enumerate(qc_well.units):
            if row_index > col_index:
                continue
            ax = fig.add_subplot(matrix[row_index, col_index])
            qc_gallery.plot_nature_correlogram(
                ax,
                row_unit,
                col_unit,
                row_index,
                col_index,
                unit_count,
                qc_args,
            )
            ax.tick_params(axis="y", labelsize=5.6, pad=1.0)
            if row_index == 0:
                ax.text(
                    0.5,
                    1.10,
                    f"{col_unit.class_label} {int(float(col_unit.row['unit_id']))}",
                    transform=ax.transAxes,
                    ha="center",
                    va="bottom",
                    fontsize=5.8,
                    fontweight="bold",
                    color=col_unit.color,
                )


def _consolidate_waveform_metric_source(
    retained: pd.DataFrame,
    excluded: pd.DataFrame,
    classifier_metrics: pd.DataFrame,
) -> pd.DataFrame:
    """Return one current-scope row per unit with all available waveform metrics."""
    retained = retained.copy()
    retained["current_plot_category"] = retained["rs_fs_class"].map(
        {"FS": "High-confidence FS", "RS": "High-confidence RS"}
    )
    excluded = excluded.copy()
    excluded["current_plot_category"] = np.where(
        excluded["ttr90_confidence_category"].eq("indeterminate"),
        "Indeterminate canonical",
        "Unclassified atypical morphology",
    )
    combined = pd.concat([retained, excluded], ignore_index=True, sort=False)
    if combined["unit_key"].duplicated().any():
        raise ValueError("Consolidated waveform source contains duplicate unit keys")

    extra_classifier_columns = [
        column
        for column in classifier_metrics.columns
        if column == "unit_key" or column not in combined.columns
    ]
    combined = combined.merge(
        classifier_metrics[extra_classifier_columns],
        on="unit_key",
        how="left",
        validate="one_to_one",
    )
    combined["displayed_in_current_3d"] = (
        combined["current_plot_category"].isin(
            ["High-confidence FS", "Indeterminate canonical", "High-confidence RS"]
        )
        & pd.to_numeric(combined["ttr90_ms"], errors="coerce").between(
            0.12, 1.00, inclusive="both"
        )
        & pd.to_numeric(
            combined["after_repolarization_time_ms"], errors="coerce"
        ).between(0.00, 0.60, inclusive="both")
        & pd.to_numeric(combined["after_spike_half_width_ms"], errors="coerce").between(
            0.00, 0.80, inclusive="both"
        )
    )
    combined["current_3d_x_metric"] = "ttr90_ms"
    combined["current_3d_y_metric"] = "after_repolarization_time_ms"
    combined["current_3d_z_metric"] = "after_spike_half_width_ms"
    combined["current_3d_point_size_metric"] = "inverse_isi_gaussian_temporal_p99_9_hz"
    preferred = [
        "unit_key",
        "source_platform",
        "recording",
        "well",
        "unit_id",
        "cell_line",
        "current_plot_category",
        "displayed_in_current_3d",
        "morphology_class",
        "canonical_negative_trough",
        "valid_90pct_crossing_exists",
        "ttr90_confidence_category",
        "current_3d_x_metric",
        "current_3d_y_metric",
        "current_3d_z_metric",
        "current_3d_point_size_metric",
    ]
    metric_columns = [name for name, *_ in WAVEFORM_METRIC_SPECS]
    remaining = [
        column
        for column in combined.columns
        if column not in preferred and column not in metric_columns
    ]
    return combined[[*preferred, *metric_columns, *remaining]].sort_values(
        ["current_plot_category", "source_platform", "recording", "well", "unit_id"]
    )


def _waveform_metric_dictionary() -> pd.DataFrame:
    displayed_role = {
        "ttr90_ms": "3D x-axis and histogram",
        "after_repolarization_time_ms": "3D y-axis",
        "after_spike_half_width_ms": "3D z-axis",
    }
    rows = [
        {
            "column": column,
            "display_label": label,
            "unit": unit,
            "description": description,
            "role_in_current_main_figure": displayed_role.get(
                column, "available source metric; not displayed in current 3D axes"
            ),
        }
        for column, label, unit, description in WAVEFORM_METRIC_SPECS
    ]
    rows.append(
        {
            "column": "inverse_isi_gaussian_temporal_p99_9_hz",
            "display_label": "Temporal P99.9 firing rate",
            "unit": "Hz",
            "description": "temporal P99.9 of the smoothed inverse-ISI firing-rate trace",
            "role_in_current_main_figure": "3D point size",
        }
    )
    return pd.DataFrame(rows)


def _plot_waveform_metric_matrix(plt, source: pd.DataFrame, output_path: Path) -> None:
    """Export an editable pairwise matrix for all current waveform features."""
    from matplotlib.lines import Line2D
    from scipy.stats import spearmanr

    specs = [spec for spec in WAVEFORM_METRIC_SPECS if spec[0] in source.columns]
    columns = [spec[0] for spec in specs]
    labels = [spec[1] for spec in specs]
    count = len(columns)
    colors = {
        "High-confidence FS": unified.CLASS_COLORS["FS"],
        "Indeterminate canonical": unified.TTR90_INDETERMINATE_COLOR,
        "High-confidence RS": unified.CLASS_COLORS["RS"],
        "Unclassified atypical morphology": "#C8C8C8",
    }
    markers = {
        "High-confidence FS": "o",
        "Indeterminate canonical": "o",
        "High-confidence RS": "o",
        "Unclassified atypical morphology": "x",
    }
    categories = list(colors)
    fig, axes = plt.subplots(
        count,
        count,
        figsize=(1.42 * count, 1.42 * count),
        squeeze=False,
        facecolor="white",
    )
    for row, y_column in enumerate(columns):
        for col, x_column in enumerate(columns):
            ax = axes[row, col]
            if row < col:
                pair = source[[x_column, y_column]].apply(
                    pd.to_numeric, errors="coerce"
                ).dropna()
                if (
                    len(pair) >= 3
                    and pair[x_column].nunique() > 1
                    and pair[y_column].nunique() > 1
                ):
                    rho, _ = spearmanr(pair[x_column], pair[y_column])
                    ax.text(
                        0.5,
                        0.5,
                        f"ρ={rho:.2f}\nn={len(pair)}",
                        transform=ax.transAxes,
                        ha="center",
                        va="center",
                        fontsize=4.4,
                        color="#555555",
                    )
                ax.set_axis_off()
                continue
            if row == col:
                for category in categories:
                    values = pd.to_numeric(
                        source.loc[source["current_plot_category"].eq(category), x_column],
                        errors="coerce",
                    ).dropna()
                    if len(values):
                        ax.hist(
                            values,
                            bins=18,
                            histtype="stepfilled",
                            color=colors[category],
                            alpha=0.34,
                            linewidth=0,
                        )
            else:
                for category in categories:
                    subset = source.loc[source["current_plot_category"].eq(category)]
                    x = pd.to_numeric(subset[x_column], errors="coerce")
                    y = pd.to_numeric(subset[y_column], errors="coerce")
                    valid = x.notna() & y.notna()
                    if valid.any():
                        ax.scatter(
                            x.loc[valid],
                            y.loc[valid],
                            s=4.2,
                            marker=markers[category],
                            color=colors[category],
                            alpha=0.50 if category != "Unclassified atypical morphology" else 0.32,
                            linewidth=0.35 if markers[category] == "x" else 0,
                            rasterized=False,
                        )
            ax.spines[["top", "right"]].set_visible(False)
            ax.tick_params(axis="both", labelsize=3.6, length=1.5, width=0.4, pad=1.0)
            if row != count - 1:
                ax.set_xticklabels([])
            else:
                ax.set_xlabel(labels[col], fontsize=4.1, labelpad=1.5, rotation=18)
            if col != 0:
                ax.set_yticklabels([])
            else:
                ax.set_ylabel(labels[row], fontsize=4.1, labelpad=1.5)
    fig.suptitle(
        "Complete pairwise waveform-metric matrix · current Lumos + ventral CytoView scope",
        fontsize=10.5,
        fontweight="bold",
        y=0.998,
    )
    legend_handles = [
        Line2D(
            [0],
            [0],
            marker=markers[category],
            linestyle="none",
            color=colors[category],
            markersize=4,
            label=f"{category} (n={int(source['current_plot_category'].eq(category).sum())})",
        )
        for category in categories
    ]
    fig.legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.989),
        ncol=4,
        frameon=False,
        fontsize=5.2,
        handletextpad=0.3,
        columnspacing=0.8,
    )
    fig.subplots_adjust(
        left=0.055,
        right=0.995,
        top=0.972,
        bottom=0.055,
        wspace=0.13,
        hspace=0.13,
    )
    fig.savefig(output_path, format="svg", facecolor="white", transparent=False)
    plt.close(fig)


def _build_figure(
    plt,
    Line2D,
    units: pd.DataFrame,
    indeterminate_units: pd.DataFrame,
    waveform_metrics: pd.DataFrame,
    waveform_summary: pd.DataFrame,
    wells: pd.DataFrame,
    selected_assets: dict[str, dict[str, object]],
    qc_well,
    qc_args,
    output_base: Path,
    export_formats: str,
) -> list[Path]:
    from matplotlib.patches import FancyBboxPatch

    neutral = "#2B2B2B"
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "Nimbus Sans", "DejaVu Sans"],
            "font.size": 7.8,
            "axes.titlesize": 8.4,
            "axes.titleweight": "normal",
            "axes.labelsize": 7.5,
            "xtick.labelsize": 6.4,
            "ytick.labelsize": 6.4,
            "axes.linewidth": 0.65,
            "xtick.major.width": 0.65,
            "ytick.major.width": 0.65,
            "text.color": neutral,
            "axes.labelcolor": neutral,
            "axes.edgecolor": neutral,
            "xtick.color": neutral,
            "ytick.color": neutral,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )

    fig = plt.figure(figsize=(16.0, 9.2), facecolor="white")
    outer = fig.add_gridspec(
        2,
        1,
        height_ratios=[0.062, 0.938],
        hspace=0.035,
    )

    ax_header = fig.add_subplot(outer[0, 0])
    ax_header.set_axis_off()
    ax_header.add_patch(
        FancyBboxPatch(
            (0.0, 0.23),
            1.0,
            0.52,
            transform=ax_header.transAxes,
            boxstyle="round,pad=0.006,rounding_size=0.025",
            facecolor="#171717",
            edgecolor="#171717",
            linewidth=0,
        )
    )
    ax_header.text(
        0.5,
        0.49,
        "High-confidence putative FS and RS units in ventral MGE organoids",
        transform=ax_header.transAxes,
        ha="center",
        va="center",
        color="white",
        fontsize=10.0,
        fontweight="bold",
    )

    content = outer[1, 0].subgridspec(
        1,
        3,
        width_ratios=[0.275, 0.255, 0.470],
        wspace=0.145,
    )

    # Panel A is one column with four aligned rows: 3D feature space, compact
    # histogram (with original-amplitude waveform inset), spatial footprints,
    # and ACG/CCG.
    panel_a = content[0, 0].subgridspec(
        4,
        1,
        height_ratios=[0.400, 0.140, 0.300, 0.160],
        hspace=0.26,
    )
    feature_block = panel_a[0, 0].subgridspec(
        2,
        1,
        height_ratios=[0.18, 0.82],
        hspace=0.02,
    )
    ax_a_title = fig.add_subplot(feature_block[0, 0])
    ax_a_title.set_axis_off()
    ax_a_title.text(
        0.0,
        0.58,
        "A",
        transform=ax_a_title.transAxes,
        fontsize=11.0,
        fontweight="bold",
        va="center",
    )
    ax_feature = fig.add_subplot(feature_block[1, 0], projection="3d")
    _plot_c01_view3_feature_space(ax_feature, waveform_metrics)

    # Preserve the locked 3D geometry while introducing a small editorial
    # pause before the supporting histogram.
    histogram_vertical = panel_a[1, 0].subgridspec(
        2,
        1,
        height_ratios=[0.10, 0.90],
        hspace=0.0,
    )
    histogram_width = histogram_vertical[1, 0].subgridspec(
        1,
        3,
        width_ratios=[0.225, 0.550, 0.225],
        wspace=0.0,
    )
    ax_hist = fig.add_subplot(histogram_width[0, 1])
    unified._plot_panel_a_ttp_histogram(
        ax_hist,
        units,
        fs_cutoff_ms=0.50,
        ttr90_mode=True,
        indeterminate_units=indeterminate_units,
    )
    ax_hist.set_title("", loc="left")
    ax_hist.set_xlabel("TTP (ms)", fontsize=7.2, labelpad=2.0)
    ax_hist.set_ylabel("Units", fontsize=7.2, labelpad=2.0)
    ax_hist.tick_params(labelsize=6.3, length=2.2, width=0.6, pad=1.8)
    ax_hist.text(
        -0.41,
        1.12,
        "B",
        transform=ax_hist.transAxes,
        fontsize=11.0,
        fontweight="bold",
        ha="left",
        va="center",
        clip_on=False,
    )
    legend = ax_hist.get_legend()
    if legend is not None:
        legend.remove()
    _plot_mean_waveform_histogram_inset(ax_hist, waveform_summary)

    # Treat the spatial footprint and correlograms as one subordinate piece of
    # same-well isolation evidence.  A restrained shared frame supplies the
    # grouping without adding dashboard-like visual weight.
    qc_frame_spec = panel_a[2:, 0]
    ax_qc_frame = fig.add_subplot(qc_frame_spec)
    ax_qc_frame.set_axis_off()
    ax_qc_frame.add_patch(
        FancyBboxPatch(
            (0.008, 0.012),
            0.984,
            0.976,
            transform=ax_qc_frame.transAxes,
            boxstyle="round,pad=0.006,rounding_size=0.018",
            facecolor="#FCFCFC",
            edgecolor="#D6D6D6",
            linewidth=0.55,
            clip_on=False,
            zorder=0,
        )
    )
    qc_module = qc_frame_spec.subgridspec(
        4,
        1,
        height_ratios=[0.075, 0.440, 0.465, 0.020],
        hspace=0.060,
    )
    ax_qc_module_title = fig.add_subplot(qc_module[0, 0])
    ax_qc_module_title.set_axis_off()
    ax_qc_module_title.text(
        0.045,
        0.44,
        "C",
        transform=ax_qc_module_title.transAxes,
        ha="left",
        va="center",
        fontsize=11.0,
        fontweight="bold",
        color="#2B2B2B",
    )
    ax_qc_module_title.text(
        0.105,
        0.44,
        "Same-well unit-isolation QC",
        transform=ax_qc_module_title.transAxes,
        ha="left",
        va="center",
        fontsize=7.1,
        fontweight="bold",
        color="#4F4F4F",
    )
    spatial_padding = qc_module[1, 0].subgridspec(
        1,
        3,
        width_ratios=[0.035, 0.930, 0.035],
        wspace=0.0,
    )
    correlogram_padding = qc_module[2, 0].subgridspec(
        1,
        3,
        width_ratios=[0.045, 0.910, 0.045],
        wspace=0.0,
    )
    _plot_same_well_qc_stack(
        fig,
        spatial_padding[0, 1],
        correlogram_padding[0, 1],
        qc_well,
        qc_args,
    )

    # Panels D and E: one best clean-ACG representative per class.
    representatives = content[0, 1].subgridspec(
        5,
        1,
        height_ratios=[0.052, 0.055, 0.405, 0.055, 0.433],
        hspace=0.035,
    )
    ax_rep_title = fig.add_subplot(representatives[0, 0])
    ax_rep_title.set_axis_off()
    ax_rep_title.text(
        0.0,
        0.58,
        "Representative unit isolation",
        transform=ax_rep_title.transAxes,
        fontsize=9.1,
        fontweight="bold",
        va="center",
    )

    for header_index, card_index, class_label, letter in [
        (1, 2, "FS", "D"),
        (3, 4, "RS", "E"),
    ]:
        ax_class_header = fig.add_subplot(representatives[header_index, 0])
        ax_class_header.set_axis_off()
        ax_class_header.text(
            0.0,
            0.50,
            letter,
            transform=ax_class_header.transAxes,
            fontsize=11.0,
            fontweight="bold",
            va="center",
        )
        ax_class_header.text(
            0.085,
            0.50,
            "Putative FS unit"
            if class_label == "FS"
            else "Putative RS unit",
            transform=ax_class_header.transAxes,
            fontsize=8.2,
            color=unified.CLASS_COLORS[class_label],
            va="center",
        )
        if class_label == "RS":
            ax_class_header.plot(
                [0.0, 1.0],
                [1.0, 1.0],
                transform=ax_class_header.transAxes,
                color="#D5D5D5",
                lw=0.55,
                clip_on=False,
            )
        card = representatives[card_index, 0].subgridspec(
            3,
            1,
            height_ratios=[3.05, 0.76, 0.66],
            hspace=0.26,
        )
        spatial_ax = fig.add_subplot(card[0, 0])
        acg_ax = fig.add_subplot(card[1, 0])
        stability_ax = fig.add_subplot(card[2, 0])
        asset = selected_assets[class_label]
        unified._plot_representative_spatial(spatial_ax, asset, class_label, 1)
        unified._plot_representative_acg(acg_ax, asset, class_label, show_ylabel=True)
        unified._plot_representative_stability(
            stability_ax, asset, class_label, show_ylabel=True
        )
        if stability_ax.lines:
            stability_ax.lines[0].set_linewidth(0.32)
        if stability_ax.collections:
            stability_ax.collections[0].set_alpha(0.14)
        feature_ttr90_ms = float(asset["metadata"]["feature_ttp_ms"])
        representative_display_id = str(
            asset["metadata"].get("representative_display_id", f"{class_label}1")
        )
        spatial_ax.set_title(
            f"{representative_display_id} · TTP = {feature_ttr90_ms:.2f} ms",
            loc="left",
            fontsize=6.8,
            fontweight="normal",
            color=unified.CLASS_COLORS[class_label],
            pad=2.0,
        )
        p_refractory = float(asset["probability"]["p_refractory"])
        acg_ax.set_title(
            f"ACG · P(|lag| ≤ 2 ms) = {p_refractory:.3f}",
            loc="left",
            fontsize=6.8,
            fontweight="normal",
            pad=2.0,
        )
        stability_ax.set_title(
            "Waveform stability",
            loc="left",
            fontsize=6.8,
            fontweight="normal",
            pad=2.0,
        )

    # Former bottom row: promoted into a compact two-row by three-column grid.
    activity = content[0, 2].subgridspec(
        3,
        1,
        height_ratios=[0.075, 0.455, 0.470],
        hspace=0.18,
    )
    ax_activity_title = fig.add_subplot(activity[0, 0])
    ax_activity_title.set_axis_off()
    ax_activity_title.text(
        0.0,
        0.62,
        "Organoid-level spontaneous activity",
        transform=ax_activity_title.transAxes,
        fontsize=9.2,
        fontweight="bold",
        va="center",
    )
    ax_activity_title.text(
        1.0,
        0.15,
        "Each point represents one organoid; diamonds indicate overall mean ± s.e.m.",
        transform=ax_activity_title.transAxes,
        fontsize=5.5,
        color="#555555",
        ha="right",
        va="center",
    )
    ax_activity_title.plot(
        [0.0, 1.0],
        [0.0, 0.0],
        transform=ax_activity_title.transAxes,
        color="#BEBEBE",
        lw=0.6,
        clip_on=False,
    )
    activity_grid = activity[1:, 0].subgridspec(2, 3, wspace=0.34, hspace=0.42)
    activity_axes = [
        fig.add_subplot(activity_grid[row, column])
        for row in range(2)
        for column in range(3)
    ]
    nature_activity_specs = [
        (
            "F",
            "mean_unit_inverse_isi_gaussian_temporal_p99_9_hz",
            "Firing Rate",
            "Firing Rate (Hz)",
        ),
        (
            "G",
            "mean_unit_burst_rate_per_min",
            "Burst rate",
            "Burst rate (bursts/min)",
        ),
        (
            "H",
            "mean_unit_firing_rate_within_bursts_hz",
            "Firing rate within bursts",
            "Mean firing rate within bursts (Hz)",
        ),
        (
            "I",
            "mean_unit_burst_duration_ms",
            "Burst duration",
            "Burst duration (ms)",
        ),
        (
            "J",
            "mean_unit_interburst_interval_s",
            "Interburst interval",
            "Interburst interval (s)",
        ),
        (
            "K",
            "mean_unit_spikes_per_burst",
            "Spikes per burst",
            "Mean spikes per burst",
        ),
    ]
    unified._plot_activity_strip(
        activity_axes,
        wells,
        nature_activity_specs,
        pooled_fsrs=True,
    )
    for index, ax in enumerate(activity_axes):
        ax.set_title(
            chr(ord("F") + index),
            loc="left",
            fontsize=10.5,
            fontweight="bold",
            y=1.01,
            pad=0,
        )
        ax.set_ylabel(ax.get_ylabel(), fontsize=7.8, labelpad=2.0)
        ax.yaxis.set_label_coords(-0.16, 0.5)
        ax.tick_params(labelsize=6.4, length=2.0, width=0.6, pad=1.6)
        ax.yaxis.grid(False)
        ax.set_xticklabels(
            [
                "\n".join(
                    [
                        tick.get_text().splitlines()[0],
                        next(
                            (
                                line.replace("n=", "n = ").split(" organoid")[0]
                                for line in tick.get_text().splitlines()
                                if line.startswith("n=")
                            ),
                            "",
                        ),
                    ]
                ).rstrip()
                for tick in ax.get_xticklabels()
            ]
        )
    fig.align_ylabels(activity_axes)

    cell_line_handles = [
        Line2D(
            [0],
            [0],
            marker=marker,
            linestyle="none",
            markerfacecolor="#777777",
            markeredgecolor="white",
            markersize=5.5,
            label=unified.CELL_LINE_CODES[cell_line],
        )
        for cell_line, marker in unified.CELL_LINE_MARKERS.items()
    ]
    class_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markerfacecolor=unified.CLASS_COLORS[class_label],
            markeredgecolor="none",
            markersize=5.5,
            label=f"Putative {class_label}",
        )
        for class_label in unified.CLASS_ORDER
    ]
    mean_handle = Line2D(
        [0],
        [0],
        marker="D",
        linestyle="none",
        markerfacecolor="white",
        markeredgecolor="black",
        markersize=5.5,
        label="Overall mean ± s.e.m.",
    )
    fig.legend(
        handles=class_handles + cell_line_handles + [mean_handle],
        loc="lower center",
        bbox_to_anchor=(0.73, 0.006),
        ncol=6,
        frameon=False,
        fontsize=6.7,
        handletextpad=0.35,
        columnspacing=0.9,
    )

    fig.subplots_adjust(left=0.035, right=0.992, top=0.992, bottom=0.080)
    output_paths: list[Path] = []
    for suffix in [part.strip().lower() for part in export_formats.split(",") if part.strip()]:
        path = output_base.with_suffix(f".{suffix}")
        kwargs: dict[str, object] = {
            "bbox_inches": "tight",
            "facecolor": "white",
            "transparent": False,
        }
        if suffix == "png":
            kwargs["dpi"] = 600
        fig.savefig(path, **kwargs)
        output_paths.append(path)
    plt.close(fig)
    return output_paths


def main() -> int:
    args = parse_args()
    source_dir = args.source_dir.expanduser().resolve()
    locked_qc_png = args.locked_qc_png.expanduser().resolve()
    qc_candidate_manifest = args.qc_candidate_manifest.expanduser().resolve()
    representative_shortlist_path = args.representative_shortlist.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    source_stem = "lumos_ventral_ttr90_confidence"
    source_paths = {
        "retained_units": source_dir / f"{source_stem}_retained_FS_RS_units.csv",
        "excluded_units": source_dir / f"{source_stem}_excluded_indeterminate_atypical_units.csv",
        "organoid_activity": source_dir / f"{source_stem}_organoid_level_activity.csv",
        "representative_shortlist": representative_shortlist_path,
        "waveform_summary": source_dir / f"{source_stem}_waveform_summary.csv",
        "classifier_metrics": (
            source_dir
            / "ttr90_canonical_negative_classifier/ttr90_canonical_negative_unit_metrics.csv"
        ),
    }
    missing = [
        str(path)
        for path in [*source_paths.values(), locked_qc_png, qc_candidate_manifest]
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(f"Missing required sources: {missing}")

    units = pd.read_csv(source_paths["retained_units"])
    excluded = pd.read_csv(source_paths["excluded_units"])
    indeterminate = excluded.loc[
        excluded["ttr90_confidence_category"].eq("indeterminate")
    ].copy()
    indeterminate["feature_ttp_ms"] = pd.to_numeric(
        indeterminate["ttr90_ms"], errors="coerce"
    )
    wells = pd.read_csv(source_paths["organoid_activity"])
    waveform_summary = pd.read_csv(source_paths["waveform_summary"])
    classifier_metrics = pd.read_csv(source_paths["classifier_metrics"])
    all_waveform_metrics = _consolidate_waveform_metric_source(
        units, excluded, classifier_metrics
    )
    all_metrics_path = output_dir / f"{args.output_stem}_all_unit_waveform_metrics.csv"
    metric_dictionary_path = output_dir / f"{args.output_stem}_waveform_metric_dictionary.csv"
    metric_matrix_path = output_dir / f"{args.output_stem}_all_waveform_metrics_pairwise_matrix.svg"
    # Persist and read back the exact publication source table before drawing
    # Panel a so the embedded plot is reproducibly tied to the exported CSV.
    all_waveform_metrics.to_csv(all_metrics_path, index=False)
    waveform_metrics_for_plot = pd.read_csv(all_metrics_path)
    representative_shortlist = pd.read_csv(source_paths["representative_shortlist"])
    selected_assets, selection_audit = _load_final_representatives_from_shortlist(
        representative_shortlist
    )

    from scripts import plot_ttr90_mixed_fs_rs_well_qc_gallery as qc_gallery
    import spikeinterface.full as si

    qc_manifest = pd.read_csv(qc_candidate_manifest)
    qc_row = qc_manifest.sort_values("candidate_rank").iloc[0]
    qc_key = (
        str(qc_row["source_platform"]),
        str(qc_row["recording"]),
        str(qc_row["well"]),
    )
    qc_group = units.loc[
        units["source_platform"].astype(str).eq(qc_key[0])
        & units["recording"].astype(str).eq(qc_key[1])
        & units["well"].astype(str).eq(qc_key[2])
    ].copy()
    if qc_group.empty:
        raise ValueError(f"Locked QC well was absent from retained units: {qc_key}")
    qc_args = SimpleNamespace(
        min_spikes=100,
        max_isi_lt_2ms_fraction=0.01,
        footprint_threshold=0.12,
        surrounding_channels_per_unit=9,
        correlogram_window_ms=50.0,
        correlogram_bin_ms=1.0,
        spatial_waveform_gain=1.65,
        show_spatial_markers=False,
        show_spatial_unit_labels=True,
    )
    qc_well = qc_gallery.load_well(si, qc_key, qc_group, qc_args)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    output_base = output_dir / args.output_stem
    paths = _build_figure(
        plt,
        Line2D,
        units,
        indeterminate,
        waveform_metrics_for_plot,
        waveform_summary,
        wells,
        selected_assets,
        qc_well,
        qc_args,
        output_base,
        args.export_formats,
    )

    _waveform_metric_dictionary().to_csv(metric_dictionary_path, index=False)
    _plot_waveform_metric_matrix(plt, all_waveform_metrics, metric_matrix_path)

    selection_path = output_dir / f"{args.output_stem}_representative_selection_audit.csv"
    selection_audit.to_csv(selection_path, index=False)
    provenance_path = output_dir / f"{args.output_stem}_provenance.json"
    provenance_path.write_text(
        json.dumps(
            {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "scientific_content_change": False,
                "layout_changes": [
                    "locked final representative assets to shortlist candidates FS3 and RS2",
                    "replaced embedded 3D plot with locked C01/View 3 using TTR90, post-trough rebound slope, and waveform asymmetry",
                    "used all 73 FS, 55 indeterminate, and 24 RS finite canonical units in the embedded 3D plot",
                    "mapped P99-capped ISI-derived temporal P99.9 firing rate to a shared 18–120 point-squared marker-area scale",
                    "promoted continuous PCHIP TTR90 distribution",
                    "increased 3D feature-space area and reduced histogram area",
                    "constrained histogram width and enlarged spatial-footprint section without changing 3D geometry",
                    "increased the visual break between the 3D feature space and histogram without resizing the 3D plot",
                    "inserted original-amplitude FS/RS mean waveforms inside histogram",
                    "reconstructed approved same-well QC as spatial footprints above ACG/CCG",
                    "nested the same-well spatial footprints and ACG/CCG matrix within one subtle shared isolation frame",
                    "removed channel and best-channel markers from every spatial footprint so only waveform traces remain",
                    "increased only the Panel C spatial-waveform display gain by 65%",
                    "restored text-only unit labels beside the Panel C waveforms without restoring spatial markers",
                    "removed the offset cell-line mean and s.e.m. summaries while retaining the original overall mean and s.e.m.",
                    "reduced representative display to one clean-ACG FS and one clean-ACG RS unit",
                    "thinned representative waveform-stability median traces",
                    "removed classified-unit firing comparison Panel E",
                    "promoted six organoid metrics into a two-row by three-column grid",
                    "removed cell-line N labels beneath organoid-level groups",
                ],
                "classification_thresholds_ms": {
                    "FS_inclusive_max": unified.TTR90_FS_MAX_MS,
                    "indeterminate_strict_interval": [
                        unified.TTR90_FS_MAX_MS,
                        unified.TTR90_RS_MIN_MS,
                    ],
                    "RS_inclusive_min": unified.TTR90_RS_MIN_MS,
                },
                "sources": {
                    key: {"path": str(path), "sha256": _sha256(path)}
                    for key, path in source_paths.items()
                }
                | {
                    "locked_qc_insert": {
                        "path": str(locked_qc_png),
                        "sha256": _sha256(locked_qc_png),
                    },
                    "qc_candidate_manifest": {
                        "path": str(qc_candidate_manifest),
                        "sha256": _sha256(qc_candidate_manifest),
                    },
                    "embedded_3d_waveform_metrics_csv": {
                        "path": str(all_metrics_path),
                        "sha256": _sha256(all_metrics_path),
                    },
                },
                "selected_representatives": selection_audit.loc[
                    selection_audit["selected"]
                ][
                    [
                        "unit_key",
                        "rs_fs_class",
                        "source_platform",
                        "well",
                        "unit_id",
                        "ttr90_ms",
                        "acg_refractory_probability",
                    ]
                ].to_dict("records"),
                "outputs": [str(path) for path in paths],
                "waveform_metric_outputs": {
                    "all_unit_waveform_metrics": str(all_metrics_path),
                    "waveform_metric_dictionary": str(metric_dictionary_path),
                    "all_waveform_metrics_pairwise_matrix_svg": str(metric_matrix_path),
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"OUTPUT_DIR={output_dir}")
    print("Selected representative units:")
    print(
        selection_audit.loc[selection_audit["selected"]][
            [
                "rs_fs_class",
                "source_platform",
                "well",
                "unit_id",
                "ttr90_ms",
                "acg_refractory_probability",
            ]
        ].to_string(index=False)
    )
    print("Figures:")
    for path in paths:
        print(path)
    print("Waveform metric sources:")
    for path in [all_metrics_path, metric_dictionary_path, metric_matrix_path]:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
