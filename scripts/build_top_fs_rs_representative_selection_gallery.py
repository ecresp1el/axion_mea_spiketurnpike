#!/usr/bin/env python3
"""Rank and display the top four putative FS and RS representative candidates."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import re
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


PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
PANEL_DIR = (
    PROJECT_ROOT
    / "FINAL FIG 2/Population Panels/ventral_MGE_putative_FS_RS_"
    "TTR90_PCHIP_040_056_FINAL/reformatted_histogram_best_units_activity_grid_20260714"
)
DEFAULT_METRICS = (
    PANEL_DIR
    / "lumos_ventral_putative_fsrs_ttr90_reformatted_FINAL_all_unit_waveform_metrics.csv"
)
DEFAULT_CURRENT_AUDIT = (
    PANEL_DIR
    / "lumos_ventral_putative_fsrs_ttr90_reformatted_FINAL_representative_selection_audit.csv"
)
DEFAULT_OUTPUT_DIR = PANEL_DIR / "top4_FS_RS_representative_candidates_20260714"
STEM = "top4_putative_FS_RS_representative_selection"

CLASS_CATEGORY = {
    "FS": "High-confidence FS",
    "RS": "High-confidence RS",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--current-audit", type=Path, default=DEFAULT_CURRENT_AUDIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-per-class", type=int, default=4)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def biological_organoid_key(row: pd.Series) -> str:
    recording = str(row["recording"])
    base = re.sub(
        r"_(?:filter_200Hz-3kHz|primary_Neural_Broadband_hp_0\.1_Hz_IIR_lp_None|broadband_processor_raw)$",
        "",
        recording,
    )
    # Acquisition indices such as (000)/(001) are repeat recordings of the
    # same plate/well context, not independent organoids.
    base = re.sub(r"\(\d{3}\)$", "", base)
    return f"{row['source_platform']}|{base}|{row['well']}"


def robust_amplitude_cv(amplitudes: np.ndarray) -> float:
    values = np.asarray(amplitudes, dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    if values.size < 5:
        return float("inf")
    median = float(np.median(values))
    if median <= 0:
        return float("inf")
    mad = float(np.median(np.abs(values - median)))
    return 1.4826 * mad / median


def candidate_population(metrics: pd.DataFrame) -> pd.DataFrame:
    groups: list[pd.DataFrame] = []
    for class_label, category in CLASS_CATEGORY.items():
        group = metrics.loc[metrics["current_plot_category"].eq(category)].copy()
        group["rs_fs_class"] = class_label
        groups.append(group)
    candidates = pd.concat(groups, ignore_index=True, sort=False)
    numeric_columns = [
        "ttr90_ms",
        "source_spike_count",
        "source_ContamPct",
        "template_ptp_best_channel_uV",
    ]
    for column in numeric_columns:
        candidates[column] = pd.to_numeric(candidates[column], errors="coerce")
    finite = np.isfinite(candidates[numeric_columns].to_numpy(dtype=float)).all(axis=1)
    candidates = candidates.loc[finite & candidates["analyzer_path"].notna()].copy()
    candidates["feature_ttp_ms"] = candidates["ttr90_ms"]
    candidates["biological_organoid_key"] = candidates.apply(
        biological_organoid_key, axis=1
    )
    expected = {"FS": 73, "RS": 24}
    observed = (
        candidates["rs_fs_class"]
        .value_counts()
        .reindex(["FS", "RS"], fill_value=0)
        .astype(int)
        .to_dict()
    )
    if observed != expected:
        raise ValueError(
            f"High-confidence candidate denominator changed: {observed} != {expected}"
        )
    return candidates


def audit_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    """Compute ACG, spatial, and waveform-stability ranking evidence."""
    import spikeinterface.full as si
    import scripts.plot_spatial_isolation_1x2_panels as hybrid

    render_args = SimpleNamespace(
        highlight_channels_per_unit=8,
        footprint_threshold=0.12,
        snippet_cloud_max=100,
        amplitude_max_points=500,
        correlogram_window_ms=80.0,
        correlogram_bin_ms=2.0,
    )
    rows: list[dict[str, object]] = []
    grouped = candidates.groupby("analyzer_path", sort=False, dropna=False)
    for analyzer_path, group in grouped:
        cache: dict[str, object] = {}
        bundle = hybrid.get_bundle(si, cache, str(analyzer_path))
        for metadata in group.to_dict("records"):
            sorting_unit_id = hybrid.unit_id_for_sorting(metadata["unit_id"], bundle)
            unit_index = bundle.unit_index.get(str(sorting_unit_id))
            if unit_index is None:
                raise ValueError(f"Unit missing from analyzer: {metadata['unit_key']}")
            unit_row = hybrid.unit_render_row(
                unit_id=sorting_unit_id,
                unit_idx=int(unit_index),
                bundle=bundle,
                unit_label=metadata["unit_id"],
                spike_count=int(metadata["source_spike_count"]),
                ks_label="unfiltered",
                contam_pct=float(metadata["source_ContamPct"]),
            )
            probability = hybrid.autocorrelogram_probability(
                unit_row, bundle, render_args
            )
            snippets, _ = hybrid.sampled_best_channel_snippets(
                unit_row, bundle, render_args
            )
            amplitudes = (
                np.ptp(np.asarray(snippets, dtype=float), axis=1)
                if np.asarray(snippets).size
                else np.asarray([], dtype=float)
            )
            template = bundle.templates[int(unit_row["unit_index"])]
            channel_ptp = np.ptp(template, axis=0)
            ordered_ptp = np.sort(channel_ptp[np.isfinite(channel_ptp)])[::-1]
            spatial_peak_ratio = (
                float(ordered_ptp[0] / max(ordered_ptp[1], np.finfo(float).eps))
                if ordered_ptp.size >= 2
                else float("nan")
            )
            p_refractory = float(probability["p_refractory"])
            acg_support = float(
                np.nansum(np.asarray(probability["counts"], dtype=float))
            )
            stability_cv = robust_amplitude_cv(amplitudes)
            secondary_score = (
                np.log1p(max(acg_support, 0.0))
                + 0.30 * np.log1p(max(float(metadata["source_spike_count"]), 0.0))
                + 0.45
                * np.log1p(max(float(metadata["template_ptp_best_channel_uV"]), 0.0))
                + 0.30 * np.log1p(max(spatial_peak_ratio, 0.0))
                - 2.0 * min(stability_cv, 2.0)
                - 0.02 * max(float(metadata["source_ContamPct"]), 0.0)
            )
            rows.append(
                {
                    **metadata,
                    "acg_refractory_probability": p_refractory,
                    "acg_support_count": acg_support,
                    "waveform_stability_robust_cv": stability_cv,
                    "spatial_best_to_second_channel_ptp_ratio": spatial_peak_ratio,
                    "secondary_visual_quality_score": secondary_score,
                }
            )
        del bundle
        cache.clear()
        gc.collect()
    audit = pd.DataFrame(rows)
    ranked_frames: list[pd.DataFrame] = []
    for class_label in ["FS", "RS"]:
        group = audit.loc[audit["rs_fs_class"].eq(class_label)].sort_values(
            [
                "acg_refractory_probability",
                "acg_support_count",
                "waveform_stability_robust_cv",
                "secondary_visual_quality_score",
            ],
            ascending=[True, False, True, False],
            kind="mergesort",
        ).copy()
        group["rank_within_class"] = np.arange(1, len(group) + 1)
        ranked_frames.append(group)
    return pd.concat(ranked_frames, ignore_index=True)


def select_distinct_organoids(ranking: pd.DataFrame, top_per_class: int) -> pd.DataFrame:
    selected_rows: list[pd.Series] = []
    for class_label in ["FS", "RS"]:
        used_organoids: set[str] = set()
        group = ranking.loc[ranking["rs_fs_class"].eq(class_label)].sort_values(
            "rank_within_class"
        )
        for _, row in group.iterrows():
            organoid_key = str(row["biological_organoid_key"])
            if organoid_key in used_organoids:
                continue
            selected = row.copy()
            selected["representative_order_within_class"] = len(used_organoids) + 1
            selected["representative_display_id"] = (
                f"{class_label}{len(used_organoids) + 1}"
            )
            selected_rows.append(selected)
            used_organoids.add(organoid_key)
            if len(used_organoids) == top_per_class:
                break
        if len(used_organoids) != top_per_class:
            raise ValueError(
                f"Only {len(used_organoids)} distinct {class_label} organoids were available"
            )
    return pd.DataFrame(selected_rows).sort_values(
        ["rs_fs_class", "representative_order_within_class"]
    )


def plot_gallery(
    plt,
    selection: pd.DataFrame,
    assets: list[dict[str, object]],
    current_keys: set[str],
    output_dir: Path,
) -> list[Path]:
    asset_by_key = {str(asset["metadata"]["unit_key"]): asset for asset in assets}
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "Nimbus Sans", "DejaVu Sans"],
            "font.size": 7.0,
            "axes.titlesize": 7.0,
            "axes.labelsize": 6.5,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    fig = plt.figure(figsize=(15.5, 8.6), facecolor="white")
    outer = fig.add_gridspec(2, 4, hspace=0.30, wspace=0.16)
    for row_index, class_label in enumerate(["FS", "RS"]):
        class_rows = selection.loc[
            selection["rs_fs_class"].eq(class_label)
        ].sort_values("representative_order_within_class")
        for column_index, (_, metadata) in enumerate(class_rows.iterrows()):
            card = outer[row_index, column_index].subgridspec(
                4,
                1,
                height_ratios=[0.22, 2.80, 0.62, 0.46],
                hspace=0.13,
            )
            header = fig.add_subplot(card[0, 0])
            header.set_axis_off()
            display_id = str(metadata["representative_display_id"])
            header.text(
                0.0,
                0.66,
                display_id,
                ha="left",
                va="center",
                fontsize=8.2,
                fontweight="bold",
                color=unified.CLASS_COLORS[class_label],
            )
            header.text(
                0.12,
                0.66,
                (
                    f"{metadata['source_platform']} · {metadata['well']} · "
                    f"unit {int(float(metadata['unit_id']))}"
                ),
                ha="left",
                va="center",
                fontsize=6.7,
                color="#333333",
            )
            header.text(
                0.12,
                0.10,
                (
                    f"TTR90 = {float(metadata['ttr90_ms']):.3f} ms · "
                    f"{int(float(metadata['source_spike_count'])):,} spikes"
                ),
                ha="left",
                va="center",
                fontsize=5.5,
                color="#666666",
            )
            if str(metadata["unit_key"]) in current_keys:
                header.text(
                    1.0,
                    0.66,
                    "current pick",
                    ha="right",
                    va="center",
                    fontsize=5.6,
                    fontweight="bold",
                    color=unified.CLASS_COLORS[class_label],
                )
            asset = asset_by_key[str(metadata["unit_key"])]
            spatial_ax = fig.add_subplot(card[1, 0])
            acg_ax = fig.add_subplot(card[2, 0])
            stability_ax = fig.add_subplot(card[3, 0])
            unified._plot_representative_spatial(
                spatial_ax,
                asset,
                class_label,
                int(metadata["representative_order_within_class"]),
            )
            spatial_ax.set_title("", loc="left")
            unified._plot_representative_acg(
                acg_ax, asset, class_label, show_ylabel=column_index == 0
            )
            unified._plot_representative_stability(
                stability_ax, asset, class_label, show_ylabel=column_index == 0
            )
            acg_ax.set_title("ACG", loc="left", fontsize=6.1, pad=1.5)
            stability_ax.set_title(
                "Waveform stability", loc="left", fontsize=6.1, pad=1.5
            )
            if stability_ax.lines:
                stability_ax.lines[0].set_linewidth(0.34)
    fig.text(
        0.025,
        0.985,
        "Representative-unit candidate selection",
        ha="left",
        va="top",
        fontsize=12.0,
        fontweight="bold",
    )
    fig.text(
        0.025,
        0.958,
        (
            "Top four from distinct organoids per class · ranked by refractory-period "
            "ACG, correlogram support, waveform stability and spatial localization"
        ),
        ha="left",
        va="top",
        fontsize=7.0,
        color="#555555",
    )
    fig.text(
        0.009,
        0.735,
        "Putative FS",
        ha="left",
        va="center",
        rotation=90,
        fontsize=8.0,
        fontweight="bold",
        color=unified.CLASS_COLORS["FS"],
    )
    fig.text(
        0.009,
        0.295,
        "Putative RS",
        ha="left",
        va="center",
        rotation=90,
        fontsize=8.0,
        fontweight="bold",
        color=unified.CLASS_COLORS["RS"],
    )
    fig.subplots_adjust(left=0.035, right=0.995, top=0.925, bottom=0.035)
    outputs: list[Path] = []
    for suffix in ["png", "pdf", "svg"]:
        path = (output_dir / STEM).with_suffix(f".{suffix}")
        kwargs: dict[str, object] = {
            "bbox_inches": "tight",
            "facecolor": "white",
            "transparent": False,
        }
        if suffix == "png":
            kwargs["dpi"] = 600
        fig.savefig(path, **kwargs)
        outputs.append(path)
    plt.close(fig)
    return outputs


def main() -> int:
    args = parse_args()
    metrics_path = args.metrics.expanduser().resolve()
    current_audit_path = args.current_audit.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics = pd.read_csv(metrics_path)
    candidates = candidate_population(metrics)
    ranking = audit_candidates(candidates)
    selection = select_distinct_organoids(ranking, args.top_per_class)
    current_audit = pd.read_csv(current_audit_path)
    current_keys = set(
        current_audit.loc[current_audit["selected"].fillna(False).astype(bool), "unit_key"]
        .astype(str)
        .tolist()
    )
    selection["current_main_figure_pick"] = selection["unit_key"].astype(str).isin(
        current_keys
    )
    assets = unified._load_representative_assets(selection)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    outputs = plot_gallery(plt, selection, assets, current_keys, output_dir)
    ranking_path = output_dir / f"{STEM}_full_ranking.csv"
    selection_path = output_dir / f"{STEM}_shortlist.csv"
    ranking.to_csv(ranking_path, index=False)
    selection.to_csv(selection_path, index=False)
    provenance_path = output_dir / f"{STEM}_provenance.json"
    provenance_path.write_text(
        json.dumps(
            {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "metrics_source": str(metrics_path),
                "metrics_source_sha256": sha256(metrics_path),
                "candidate_denominator": {"FS": 73, "RS": 24},
                "minimum_spike_count_observed": int(candidates["source_spike_count"].min()),
                "ranking_order": [
                    "acg_refractory_probability ascending",
                    "acg_support_count descending",
                    "waveform_stability_robust_cv ascending",
                    "secondary_visual_quality_score descending",
                ],
                "distinct_organoid_policy": (
                    "source platform + recording stem with acquisition/filter suffix removed + well"
                ),
                "outputs": [str(path) for path in outputs],
                "full_ranking": str(ranking_path),
                "shortlist": str(selection_path),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"OUTPUT_DIR={output_dir}")
    print("SHORTLIST")
    print(
        selection[
            [
                "representative_display_id",
                "source_platform",
                "well",
                "unit_id",
                "ttr90_ms",
                "source_spike_count",
                "acg_refractory_probability",
                "waveform_stability_robust_cv",
                "current_main_figure_pick",
                "unit_key",
            ]
        ].to_string(index=False)
    )
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
