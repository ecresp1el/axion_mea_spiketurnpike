#!/usr/bin/env python
"""Plot the no-B4 control comparison and audit all B4 unit waveforms."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_lumos_all_units_unified_psth_store import DEFAULT_JOB_DIR
from scripts.plot_lumos_all_units_waveform_classification_pre_peak import (
    CLASS_COLORS,
    CLASS_LABELS,
    CLASS_ORDER,
    CONDITION_COLORS,
    OUTPUT_NAME as ALL_UNIT_OUTPUT_NAME,
)


RESPONSIVE_OUTPUT_NAME = "lumos_corrected_opto_responsive_units_development"
MATCH_OUTPUT_NAME = "lumos_pre_post_with_best_raster_psth_development"
OUTPUT_NAME = "lumos_b4_exclusion_and_waveforms_development"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--responsive-csv",
        type=Path,
        default=DEFAULT_JOB_DIR / RESPONSIVE_OUTPUT_NAME / "responsive_unit_metrics.csv",
    )
    parser.add_argument(
        "--all-unit-dir",
        type=Path,
        default=DEFAULT_JOB_DIR / ALL_UNIT_OUTPUT_NAME,
    )
    parser.add_argument(
        "--matched-control-csv",
        type=Path,
        default=DEFAULT_JOB_DIR / MATCH_OUTPUT_NAME / "matched_no_opsin_control_rates.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_JOB_DIR / OUTPUT_NAME,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    all_unit_dir = args.all_unit_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    responsive = pd.read_csv(args.responsive_csv.expanduser().resolve())
    all_units = pd.read_csv(all_unit_dir / "all_unit_waveform_pre_peak_metrics.csv")
    traces = pd.read_csv(all_unit_dir / "all_unit_normalized_waveform_traces.csv")
    selected_controls = pd.read_csv(args.matched_control_csv.expanduser().resolve())
    selected_ids = set(selected_controls["unit_observation_id"])

    non_b4_controls = all_units.loc[
        all_units["condition"].eq("no_opsin")
        & all_units["KSLabel"].str.lower().eq("good")
        & all_units["well"].ne("B4")
    ].copy()
    b4_units = all_units.loc[
        all_units["condition"].eq("no_opsin") & all_units["well"].eq("B4")
    ].copy()
    b4_traces = traces.loc[
        traces["unit_observation_id"].isin(b4_units["unit_observation_id"])
    ].copy()
    if len(non_b4_controls) != 27 or len(b4_units) != 122:
        raise ValueError(
            f"expected 27 non-B4 good controls and 122 B4 units; found "
            f"{len(non_b4_controls)} and {len(b4_units)}"
        )

    _style(plt)
    rate_figure = _plot_rate_comparison(plt, responsive, non_b4_controls)
    rate_figure.savefig(
        staging_dir / "pre_post_rates_excluding_b4.png",
        dpi=400,
        bbox_inches="tight",
        facecolor="white",
    )
    rate_figure.savefig(
        staging_dir / "pre_post_rates_excluding_b4.pdf",
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(rate_figure)

    summary_figure = _plot_b4_summary(
        plt, b4_units, b4_traces, selected_ids
    )
    summary_figure.savefig(
        staging_dir / "b4_waveform_summary.png",
        dpi=400,
        bbox_inches="tight",
        facecolor="white",
    )
    summary_figure.savefig(
        staging_dir / "b4_waveform_summary.pdf",
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(summary_figure)

    good_b4 = b4_units.loc[b4_units["KSLabel"].str.lower().eq("good")].copy()
    good_gallery = _plot_gallery_page(
        plt,
        good_b4,
        b4_traces,
        selected_ids,
        title="All 27 KSLabel=good B4 waveforms",
        subtitle="Blue frames mark the nine B4 units previously selected as baseline-matched controls.",
        rows=5,
        columns=6,
    )
    good_gallery.savefig(
        staging_dir / "b4_good_unit_waveform_gallery.png",
        dpi=400,
        bbox_inches="tight",
        facecolor="white",
    )
    good_gallery.savefig(
        staging_dir / "b4_good_unit_waveform_gallery.pdf",
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(good_gallery)

    with PdfPages(staging_dir / "b4_all_122_unit_waveforms.pdf") as pdf:
        ordered_b4 = b4_units.sort_values(
            ["KSLabel", "waveform_class", "pre_rate_hz", "unit_observation_id"],
            ascending=[True, True, False, True],
        )
        for page_number, start in enumerate(range(0, len(ordered_b4), 24), start=1):
            page_units = ordered_b4.iloc[start : start + 24]
            page = _plot_gallery_page(
                plt,
                page_units,
                b4_traces,
                selected_ids,
                title=f"B4 waveforms: all units · page {page_number}",
                subtitle=(
                    "Blue frames = previously selected controls. Waveforms are trough-normalized; "
                    "no display smoothing."
                ),
                rows=4,
                columns=6,
            )
            pdf.savefig(page, bbox_inches="tight")
            plt.close(page)

    non_b4_controls.to_csv(staging_dir / "non_b4_good_no_opsin_units.csv", index=False)
    b4_units.assign(
        previously_selected_control=b4_units["unit_observation_id"].isin(selected_ids)
    ).to_csv(staging_dir / "b4_unit_metrics.csv", index=False)
    b4_traces.to_csv(staging_dir / "b4_waveform_traces.csv", index=False)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "development_output": True,
        "overwrite_policy": "entire output directory replaced after successful run",
        "rate_comparison": {
            "responsive_opsin_units": len(responsive),
            "good_no_opsin_units_excluding_B4": len(non_b4_controls),
            "important": "the non-B4 controls are all plotted but are not baseline matched",
            "opsin_pre_median_hz": float(responsive["pre_rate_hz"].median()),
            "non_b4_control_pre_median_hz": float(non_b4_controls["pre_rate_hz"].median()),
            "non_b4_control_pre_max_hz": float(non_b4_controls["pre_rate_hz"].max()),
        },
        "B4": {
            "all_units": len(b4_units),
            "good_units": int(b4_units["KSLabel"].str.lower().eq("good").sum()),
            "mua_units": int(b4_units["KSLabel"].str.lower().eq("mua").sum()),
            "waveform_class_counts": b4_units["waveform_class"].value_counts().to_dict(),
            "previously_selected_controls": int(
                b4_units["unit_observation_id"].isin(selected_ids).sum()
            ),
        },
        "waveform_display": "trough-normalized cached traces; no display smoothing",
    }
    (staging_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )

    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging_dir.replace(output_dir)
    print(f"Output: {output_dir}")
    print("No-B4 good controls: 27")
    print("B4 units: 122 total / 27 good / 95 MUA")
    return 0


def _plot_rate_comparison(plt, responsive, controls):
    figure, axes = plt.subplots(1, 2, figsize=(9.5, 6.8), sharey=True)
    _paired_rate_axis(
        axes[0],
        responsive,
        condition="opsin",
        title=f"A  Responsive opsin units (n={len(responsive)})",
        class_column="waveform_class_unit",
    )
    _paired_rate_axis(
        axes[1],
        controls,
        condition="no_opsin",
        title=f"B  Good no-opsin units excluding B4 (n={len(controls)})",
        class_column="waveform_class",
    )
    axes[1].tick_params(labelleft=False)
    axes[1].set_ylabel("")
    figure.suptitle(
        "Pre and peak-post firing rates after excluding B4",
        x=0.03,
        y=0.985,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    figure.text(
        0.03,
        0.94,
        f"All remaining good no-opsin units are shown; they are not baseline matched. "
        f"Pre medians: opsin {responsive['pre_rate_hz'].median():.1f} Hz, "
        f"no opsin {controls['pre_rate_hz'].median():.1f} Hz.",
        ha="left",
        fontsize=8.5,
        color="#4B5563",
    )
    figure.subplots_adjust(left=0.10, right=0.985, bottom=0.10, top=0.86, wspace=0.18)
    return figure


def _paired_rate_axis(axis, units, *, condition, title, class_column):
    rng = np.random.default_rng(20260715 if condition == "opsin" else 20260716)
    jitter = rng.uniform(-0.055, 0.055, len(units))
    for offset, row in zip(jitter, units.itertuples(index=False), strict=True):
        class_name = getattr(row, class_column)
        color = CLASS_COLORS.get(class_name, CONDITION_COLORS[condition])
        axis.plot(
            [offset, 1 + offset],
            [row.pre_rate_hz, row.peak_post_rate_hz],
            color=color,
            alpha=0.32,
            lw=0.8,
        )
        axis.scatter(
            [offset, 1 + offset],
            [row.pre_rate_hz, row.peak_post_rate_hz],
            color=color,
            s=29,
            edgecolor="white",
            linewidth=0.45,
            zorder=3,
        )
    axis.set_xticks([0, 1], ["Pre", "Peak post"])
    axis.set_xlim(-0.25, 1.25)
    axis.set_ylabel("Firing rate (Hz)")
    axis.set_title(title, loc="left", fontweight="bold")
    axis.spines[["top", "right"]].set_visible(False)


def _plot_b4_summary(plt, units, traces, selected_ids):
    figure, axes = plt.subplots(2, 2, figsize=(12.5, 8.5))
    good = units.loc[units["KSLabel"].str.lower().eq("good")]
    mua = units.loc[units["KSLabel"].str.lower().eq("mua")]
    _plot_trace_group(axes[0, 0], good, traces, "A  B4 good waveforms (n=27)")
    _plot_trace_group(axes[0, 1], mua, traces, "B  B4 MUA waveforms (n=95)")
    _plot_class_counts(axes[1, 0], units)
    _plot_b4_rates(axes[1, 1], good, selected_ids)
    figure.suptitle(
        "B4 waveform and unit-quality audit",
        x=0.03,
        y=0.99,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    figure.text(
        0.03,
        0.95,
        "Every B4 waveform was available. Thin lines are individual trough-normalized units; "
        "thick lines are class means. No display smoothing.",
        ha="left",
        fontsize=8.5,
        color="#4B5563",
    )
    figure.subplots_adjust(left=0.075, right=0.985, bottom=0.08, top=0.89, wspace=0.24, hspace=0.30)
    return figure


def _plot_trace_group(axis, units, traces, title):
    merged = traces.merge(
        units[["unit_observation_id", "waveform_class"]],
        on=["unit_observation_id", "waveform_class"],
        how="inner",
        validate="many_to_one",
    )
    for class_name in CLASS_ORDER:
        class_units = units.loc[units["waveform_class"].eq(class_name)]
        class_traces = merged.loc[merged["waveform_class"].eq(class_name)]
        if class_traces.empty:
            continue
        for _, trace in class_traces.groupby("unit_observation_id", sort=False):
            axis.plot(
                trace["aligned_time_ms"],
                trace["normalized_waveform"],
                color=CLASS_COLORS[class_name],
                lw=0.45,
                alpha=0.16,
            )
        mean_trace = class_traces.groupby("aligned_time_ms")["normalized_waveform"].mean()
        axis.plot(
            mean_trace.index,
            mean_trace,
            color=CLASS_COLORS[class_name],
            lw=2.0,
            label=f"{CLASS_LABELS[class_name]} n={len(class_units)}",
        )
    axis.axhline(0, color="#9CA3AF", lw=0.65)
    axis.axvline(0, color="#9CA3AF", lw=0.65, ls="--")
    axis.set_xlabel("Time from trough (ms)")
    axis.set_ylabel("Normalized waveform")
    axis.set_title(title, loc="left", fontweight="bold")
    axis.legend(frameon=False, fontsize=8)
    axis.spines[["top", "right"]].set_visible(False)


def _plot_class_counts(axis, units):
    x = np.arange(len(CLASS_ORDER))
    width = 0.36
    good_values = [
        int((units["KSLabel"].str.lower().eq("good") & units["waveform_class"].eq(c)).sum())
        for c in CLASS_ORDER
    ]
    mua_values = [
        int((units["KSLabel"].str.lower().eq("mua") & units["waveform_class"].eq(c)).sum())
        for c in CLASS_ORDER
    ]
    good_bars = axis.bar(x - width / 2, good_values, width, color="#374151", label="Good")
    mua_bars = axis.bar(x + width / 2, mua_values, width, color="#9CA3AF", label="MUA")
    axis.bar_label(good_bars, fontsize=8)
    axis.bar_label(mua_bars, fontsize=8)
    axis.set_xticks(x, [CLASS_LABELS[c] for c in CLASS_ORDER])
    axis.set_ylabel("B4 units")
    axis.set_title("C  B4 waveform classifications", loc="left", fontweight="bold")
    axis.legend(frameon=False)
    axis.spines[["top", "right"]].set_visible(False)


def _plot_b4_rates(axis, good_units, selected_ids):
    for class_name in CLASS_ORDER:
        subset = good_units.loc[good_units["waveform_class"].eq(class_name)]
        axis.scatter(
            subset["pre_rate_hz"],
            subset["peak_post_rate_hz"],
            s=38,
            color=CLASS_COLORS[class_name],
            alpha=0.72,
            edgecolor="white",
            linewidth=0.5,
            label=f"{CLASS_LABELS[class_name]} n={len(subset)}",
        )
    selected = good_units.loc[good_units["unit_observation_id"].isin(selected_ids)]
    axis.scatter(
        selected["pre_rate_hz"],
        selected["peak_post_rate_hz"],
        s=92,
        facecolor="none",
        edgecolor=CONDITION_COLORS["no_opsin"],
        linewidth=1.5,
        label=f"Previously selected n={len(selected)}",
    )
    maximum = float(max(good_units["pre_rate_hz"].max(), good_units["peak_post_rate_hz"].max()))
    axis.plot([0, maximum], [0, maximum], color="#6B7280", lw=0.8, ls="--")
    axis.set_xlabel("Pre rate (Hz)")
    axis.set_ylabel("Peak-post rate (Hz)")
    axis.set_title("D  B4 good-unit rates", loc="left", fontweight="bold")
    axis.legend(frameon=False, fontsize=7.5)
    axis.spines[["top", "right"]].set_visible(False)


def _plot_gallery_page(
    plt,
    units,
    traces,
    selected_ids,
    *,
    title,
    subtitle,
    rows,
    columns,
):
    figure, axes = plt.subplots(rows, columns, figsize=(16, 2.55 * rows), squeeze=False)
    flat_axes = axes.ravel()
    for axis, row in zip(flat_axes, units.itertuples(index=False), strict=False):
        trace = traces.loc[
            traces["unit_observation_id"].eq(row.unit_observation_id)
        ].sort_values("aligned_time_ms")
        color = CLASS_COLORS[row.waveform_class]
        axis.plot(trace["aligned_time_ms"], trace["normalized_waveform"], color=color, lw=1.35)
        axis.axhline(0, color="#9CA3AF", lw=0.55)
        axis.axvline(0, color="#9CA3AF", lw=0.55, ls="--")
        selected = row.unit_observation_id in selected_ids
        marker = "MATCHED CONTROL · " if selected else ""
        axis.set_title(
            f"{marker}{row.unit_observation_id} · u{row.unit_id}",
            loc="left",
            fontsize=7.6,
            fontweight="bold",
            color=CONDITION_COLORS["no_opsin"] if selected else "#111827",
        )
        axis.text(
            0.02,
            0.97,
            f"{str(row.KSLabel).upper()} · {CLASS_LABELS[row.waveform_class]}\n"
            f"pre→peak {row.pre_rate_hz:.1f}→{row.peak_post_rate_hz:.1f} Hz · "
            f"PTP {row.template_ptp_uV:.1f} µV",
            transform=axis.transAxes,
            ha="left",
            va="top",
            fontsize=6.6,
            color="#374151",
        )
        if selected:
            for spine in axis.spines.values():
                spine.set_color(CONDITION_COLORS["no_opsin"])
                spine.set_linewidth(1.5)
        else:
            axis.spines[["top", "right"]].set_visible(False)
        axis.set_xlabel("ms from trough", fontsize=6.5)
        axis.set_ylabel("normalized", fontsize=6.5)
        axis.tick_params(labelsize=6)
    for axis in flat_axes[len(units) :]:
        axis.axis("off")
    figure.suptitle(title, x=0.02, y=0.995, ha="left", fontsize=14, fontweight="bold")
    figure.text(0.02, 0.965, subtitle, ha="left", fontsize=8, color="#4B5563")
    figure.subplots_adjust(left=0.055, right=0.99, bottom=0.055, top=0.90, wspace=0.30, hspace=0.52)
    return figure


def _style(plt):
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "axes.titlesize": 10,
            "axes.labelsize": 8.5,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "axes.linewidth": 0.7,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
