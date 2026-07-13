#!/usr/bin/env python
"""Visualize 12 qualifying opsin channels against one selected no-opsin channel."""

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

from scripts.build_lumos_all_units_unified_psth_store import DEFAULT_JOB_DIR  # noqa: E402
from scripts.plot_lumos_all_units_waveform_classification_pre_peak import (  # noqa: E402
    CLASS_COLORS,
    CLASS_LABELS,
    CLASS_ORDER,
    CONDITION_COLORS,
)


CHANNEL_OUTPUT_NAME = "lumos_channel_pooled_threshold_response_development"
FOCUSED_WAVEFORM_OUTPUT_NAME = "lumos_early_only_ge3_channel_unit_waveforms_development"
OUTPUT_NAME = "lumos_opsin12_vs_noopsin1_pre_peak_waveforms_development"
SELECTED_NO_OPSIN_CHANNEL = "C0354"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--channel-dir", type=Path, default=DEFAULT_JOB_DIR / CHANNEL_OUTPUT_NAME
    )
    parser.add_argument(
        "--focused-waveform-dir",
        type=Path,
        default=DEFAULT_JOB_DIR / FOCUSED_WAVEFORM_OUTPUT_NAME,
    )
    parser.add_argument(
        "--selected-no-opsin-channel", default=SELECTED_NO_OPSIN_CHANNEL
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_JOB_DIR / OUTPUT_NAME
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    channel_dir = args.channel_dir.expanduser().resolve()
    waveform_dir = args.focused_waveform_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    all_channels = pd.read_csv(channel_dir / "early_only_channel_details.csv")
    selected_channels = all_channels.loc[
        all_channels["condition"].eq("opsin")
        | all_channels["channel_observation_id"].eq(args.selected_no_opsin_channel)
    ].copy()
    _validate_selection(selected_channels, args.selected_no_opsin_channel)
    selected_channels["pre_rate_hz"] = selected_channels[
        "subtraction_baseline_rate_hz"
    ]
    selected_channels["peak_post_rate_hz"] = (
        selected_channels["pre_rate_hz"]
        + selected_channels["full_train_peak_mean_excess_hz"]
    )
    selected_channels["peak_minus_pre_hz"] = selected_channels[
        "full_train_peak_mean_excess_hz"
    ]

    all_source_units = pd.read_csv(
        waveform_dir / "qualifying_channel_source_units.csv"
    )
    selected_units = all_source_units.loc[
        all_source_units["channel_observation_id"].isin(
            selected_channels["channel_observation_id"]
        )
    ].copy()
    all_traces = pd.read_csv(
        waveform_dir / "qualifying_unit_normalized_waveform_traces.csv"
    )
    selected_traces = all_traces.loc[
        all_traces["unit_observation_id"].isin(selected_units["unit_observation_id"])
    ].copy()
    if selected_units["unit_observation_id"].nunique() != 17:
        raise ValueError(
            "expected 17 source unit observations (16 opsin + 1 no-opsin)"
        )

    selected_channels.to_csv(staging_dir / "selected_channel_metrics.csv", index=False)
    selected_units.to_csv(staging_dir / "selected_source_unit_metrics.csv", index=False)
    selected_traces.to_csv(
        staging_dir / "selected_normalized_waveform_traces.csv", index=False
    )

    _style(plt)
    summary = _plot_summary(plt, selected_channels, selected_units, selected_traces)
    summary.savefig(
        staging_dir / "opsin12_vs_noopsin1_pre_peak_waveform_summary.png",
        dpi=400,
        bbox_inches="tight",
        facecolor="white",
    )
    opsin_gallery = _plot_gallery(
        plt,
        selected_units.loc[selected_units["condition_channel"].eq("opsin")],
        selected_traces,
        condition="opsin",
        rows=4,
        columns=4,
    )
    opsin_gallery.savefig(
        staging_dir / "opsin12_source_unit_waveforms.png",
        dpi=350,
        bbox_inches="tight",
        facecolor="white",
    )
    control_gallery = _plot_gallery(
        plt,
        selected_units.loc[selected_units["condition_channel"].eq("no_opsin")],
        selected_traces,
        condition="no_opsin",
        rows=1,
        columns=1,
    )
    control_gallery.savefig(
        staging_dir / "selected_noopsin1_source_unit_waveform.png",
        dpi=350,
        bbox_inches="tight",
        facecolor="white",
    )
    with PdfPages(staging_dir / "opsin12_vs_noopsin1_pre_peak_waveforms.pdf") as pdf:
        pdf.savefig(summary, bbox_inches="tight")
        pdf.savefig(opsin_gallery, bbox_inches="tight")
        pdf.savefig(control_gallery, bbox_inches="tight")
    plt.close(summary)
    plt.close(opsin_gallery)
    plt.close(control_gallery)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "development_output": True,
        "overwrite_policy": "entire output directory replaced after successful run",
        "analysis_status": (
            "visualization-only sensitivity view; finalized 12-versus-3 response "
            "analysis and inclusion criteria are unchanged"
        ),
        "opsin_selection": "all 12 early-only channels meeting mean-PSTH + >=3/50 rule",
        "no_opsin_selection": (
            f"manual waveform-credibility selection: {args.selected_no_opsin_channel} "
            "(D2 physical channel 13, source unit 3)"
        ),
        "channel_pre_rate": "-200 to 0 ms before pulse 1",
        "channel_peak_post_rate": (
            "pre rate + peak baseline-subtracted once-smoothed mean PSTH during 0-250 ms"
        ),
        "waveforms": (
            "source-unit best-channel templates, aligned to trough and normalized by trough magnitude"
        ),
        "selected_channels": selected_channels["condition"].value_counts().to_dict(),
        "selected_source_units": selected_units[
            "condition_channel"
        ].value_counts().to_dict(),
    }
    (staging_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging_dir.replace(output_dir)
    print(f"Output: {output_dir}")
    print(f"Channels: {selected_channels['condition'].value_counts().to_dict()}")
    print(
        "Source units: "
        f"{selected_units['condition_channel'].value_counts().to_dict()}"
    )
    return 0


def _validate_selection(channels: pd.DataFrame, selected_control: str) -> None:
    counts = channels["condition"].value_counts().to_dict()
    if counts != {"opsin": 12, "no_opsin": 1}:
        raise ValueError(f"expected 12 opsin and 1 no-opsin channel, found {counts}")
    control = channels.loc[channels["condition"].eq("no_opsin")].iloc[0]
    if control["channel_observation_id"] != selected_control:
        raise ValueError("selected no-opsin channel mismatch")
    if int(control["units_pooled"]) != 1 or str(control["source_unit_ids"]) != "3":
        raise ValueError("selected no-opsin channel is not the expected single unit 3")


def _plot_summary(plt, channels, units, traces):
    figure, axes = plt.subplots(2, 3, figsize=(16, 9.2))
    _plot_selection_text(axes[0, 0], channels, units)
    _plot_pre_peak_pairs(axes[0, 1], channels)
    _plot_pre_peak_scatter(axes[0, 2], channels)
    _plot_waveform_overlay(axes[1, 0], units, traces)
    _plot_classification(axes[1, 1], units)
    _plot_latency_magnitude(axes[1, 2], channels)
    figure.suptitle(
        "Qualifying response comparison: 12 opsin channels versus one selected no-opsin channel",
        x=0.02,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    figure.text(
        0.02,
        0.95,
        "Visualization-only n=1 control selection; original ≥3/50 analysis remains 12 versus 3. "
        "Rates are channel pooled; waveforms are the linked source units.",
        ha="left",
        fontsize=8.5,
        color="#4B5563",
    )
    figure.subplots_adjust(
        left=0.06,
        right=0.985,
        bottom=0.07,
        top=0.87,
        wspace=0.27,
        hspace=0.28,
    )
    return figure


def _plot_selection_text(ax, channels, units):
    ax.axis("off")
    opsin = channels.loc[channels["condition"].eq("opsin")]
    control = channels.loc[channels["condition"].eq("no_opsin")].iloc[0]
    lines = [
        "DISPLAYED COMPARISON",
        "",
        "Opsin: all 12 qualifying channels",
        "No opsin: C0354 only",
        "  D2 channel 13, source unit 3",
        "  MUA, RS-like waveform",
        "",
        "Channel pre rate, median:",
        f"  + opsin {opsin['pre_rate_hz'].median():.1f} Hz",
        f"  − opsin {control['pre_rate_hz']:.1f} Hz",
        "",
        "Channel peak-post rate, median / value:",
        f"  + opsin {opsin['peak_post_rate_hz'].median():.1f} Hz",
        f"  − opsin {control['peak_post_rate_hz']:.1f} Hz",
        "",
        "Peak excess, median / value:",
        f"  + opsin {opsin['peak_minus_pre_hz'].median():.1f} Hz",
        f"  − opsin {control['peak_minus_pre_hz']:.1f} Hz",
        "",
        "Linked source units:",
        f"  + opsin {int(units.condition_channel.eq('opsin').sum())}",
        f"  − opsin {int(units.condition_channel.eq('no_opsin').sum())}",
    ]
    ax.text(0, 1, "\n".join(lines), ha="left", va="top", fontsize=9.3, linespacing=1.28)
    ax.set_title("A  Manual n=1 comparison view", loc="left", fontweight="bold")


def _plot_pre_peak_pairs(ax, channels):
    rng = np.random.default_rng(20260713)
    positions = {"opsin": (0, 1), "no_opsin": (3, 4)}
    for condition in ["opsin", "no_opsin"]:
        subset = channels.loc[channels["condition"].eq(condition)]
        color = CONDITION_COLORS[condition]
        jitter = rng.uniform(-0.13, 0.13, len(subset))
        for offset, row in zip(jitter, subset.itertuples(index=False), strict=True):
            x0, x1 = positions[condition]
            ax.plot(
                [x0 + offset, x1 + offset],
                [row.pre_rate_hz, row.peak_post_rate_hz],
                color=color,
                alpha=0.55,
                lw=0.9,
            )
            ax.scatter(
                [x0 + offset, x1 + offset],
                [row.pre_rate_hz, row.peak_post_rate_hz],
                color=color,
                s=23,
                edgecolor="white",
                linewidth=0.4,
                zorder=3,
            )
    ax.set_xticks([0, 1, 3, 4], ["Pre", "Peak", "Pre", "Peak"])
    ax.text(0.5, 0.98, "+ opsin n=12", transform=ax.get_xaxis_transform(), ha="center", va="top", color=CONDITION_COLORS["opsin"], fontweight="bold")
    ax.text(3.5, 0.98, "− opsin n=1", transform=ax.get_xaxis_transform(), ha="center", va="top", color=CONDITION_COLORS["no_opsin"], fontweight="bold")
    ax.set_ylabel("Channel firing rate (Hz)")
    ax.set_title("B  Pre to peak-post rate", loc="left", fontweight="bold")


def _plot_pre_peak_scatter(ax, channels):
    maximum = float(max(channels["pre_rate_hz"].max(), channels["peak_post_rate_hz"].max()))
    for condition in ["opsin", "no_opsin"]:
        subset = channels.loc[channels["condition"].eq(condition)]
        ax.scatter(
            subset["pre_rate_hz"],
            subset["peak_post_rate_hz"],
            s=45,
            color=CONDITION_COLORS[condition],
            alpha=0.78,
            edgecolor="white",
            linewidth=0.5,
            label=f"{'+' if condition == 'opsin' else '−'} opsin n={len(subset)}",
        )
        for row in subset.itertuples(index=False):
            ax.text(row.pre_rate_hz, row.peak_post_rate_hz, str(row.condition_rank), ha="center", va="center", color="white", fontsize=6.5, fontweight="bold")
    ax.plot([0, maximum], [0, maximum], color="#6B7280", ls="--", lw=0.8)
    ax.set_xlabel("Channel pre rate (Hz)")
    ax.set_ylabel("Channel peak-post rate (Hz)")
    ax.set_title("C  Every selected channel; label = rank", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=8)


def _plot_waveform_overlay(ax, units, traces):
    merged = traces.merge(
        units[["unit_observation_id", "condition_channel"]],
        on="unit_observation_id",
        how="inner",
        validate="many_to_one",
    )
    for condition in ["opsin", "no_opsin"]:
        subset = merged.loc[merged["condition_channel"].eq(condition)]
        color = CONDITION_COLORS[condition]
        for _, unit_trace in subset.groupby("unit_observation_id"):
            ordered = unit_trace.sort_values("aligned_time_ms")
            ax.plot(
                ordered["aligned_time_ms"],
                ordered["normalized_waveform"],
                color=color,
                alpha=0.18 if condition == "opsin" else 0.9,
                lw=0.75 if condition == "opsin" else 2.0,
            )
        mean = subset.groupby("aligned_time_ms")["normalized_waveform"].mean()
        ax.plot(
            mean.index,
            mean.values,
            color=color,
            lw=2.3,
            label=f"{'+' if condition == 'opsin' else '−'} opsin source units n={subset['unit_observation_id'].nunique()}",
        )
    ax.axhline(0, color="#9CA3AF", lw=0.7)
    ax.axvline(0, color="#9CA3AF", lw=0.7, ls="--")
    ax.set_xlabel("Time from trough (ms)")
    ax.set_ylabel("Normalized waveform")
    ax.set_title("D  Linked unit waveforms", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=8)


def _plot_classification(ax, units):
    x = np.arange(len(CLASS_ORDER))
    width = 0.36
    for condition, offset in [("opsin", -width / 2), ("no_opsin", width / 2)]:
        subset = units.loc[units["condition_channel"].eq(condition)]
        values = [int(subset["waveform_class"].eq(label).sum()) for label in CLASS_ORDER]
        bars = ax.bar(
            x + offset,
            values,
            width,
            color=CONDITION_COLORS[condition],
            label=f"{'+' if condition == 'opsin' else '−'} opsin",
        )
        ax.bar_label(bars, fontsize=8)
    ax.set_xticks(x, [CLASS_LABELS[label] for label in CLASS_ORDER])
    ax.set_ylabel("Source unit observations")
    ax.set_title("E  Waveform classification", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=8)


def _plot_latency_magnitude(ax, channels):
    for condition in ["opsin", "no_opsin"]:
        subset = channels.loc[channels["condition"].eq(condition)]
        ax.scatter(
            subset["full_train_peak_latency_ms"],
            subset["full_train_peak_mean_excess_hz"],
            s=35 + 14 * subset["full_train_max_same_bin_trials"],
            color=CONDITION_COLORS[condition],
            alpha=0.78,
            edgecolor="white",
            linewidth=0.5,
            label=f"{'+' if condition == 'opsin' else '−'} opsin",
        )
    ax.set_xlabel("Channel peak latency (ms)")
    ax.set_ylabel("Channel peak excess rate (Hz)")
    ax.set_title("F  Full-train timing and magnitude", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=8)


def _plot_gallery(plt, units, traces, *, condition, rows, columns):
    single_row = rows == 1
    figure, axes = plt.subplots(
        rows,
        columns,
        figsize=(16, 4.6 if single_row else 3.05 * rows),
        squeeze=False,
    )
    flat_axes = axes.ravel()
    ordered_units = units.sort_values(
        ["condition_rank", "channel_observation_id", "unit_id"]
    )
    for axis, row in zip(flat_axes, ordered_units.itertuples(index=False), strict=False):
        trace = traces.loc[
            traces["unit_observation_id"].eq(row.unit_observation_id)
        ].sort_values("aligned_time_ms")
        color = CLASS_COLORS.get(str(row.waveform_class), "#444444")
        axis.plot(
            trace["aligned_time_ms"],
            trace["normalized_waveform"],
            color=color,
            lw=1.6,
        )
        axis.axhline(0, color="#9CA3AF", lw=0.65)
        axis.axvline(0, color="#9CA3AF", lw=0.65, ls="--")
        axis.set_title(
            f"Rank {row.condition_rank} | {row.channel_observation_id} | "
            f"{row.channel_well} ch{row.channel_physical_id} | unit {row.unit_id}",
            loc="left",
            fontsize=8.2,
            fontweight="bold",
        )
        axis.text(
            0.02,
            0.97,
            f"{str(row.KSLabel).upper()} | {CLASS_LABELS.get(str(row.waveform_class), row.waveform_class)} | "
            f"PTP {row.template_ptp_uV:.1f} µV\n"
            f"unit pre→peak {row.pre_rate_hz:.1f}→{row.peak_post_rate_hz:.1f} Hz | "
            f"channel {row.pulse_response_pattern.replace(';P3=0;P4=0;P5=0', '')}",
            transform=axis.transAxes,
            ha="left",
            va="top",
            fontsize=7,
            color="#30343B",
        )
        axis.set_xlabel("Time from trough (ms)")
        axis.set_ylabel("Normalized amplitude")
        axis.spines[["top", "right"]].set_visible(False)
    for axis in flat_axes[len(ordered_units) :]:
        axis.axis("off")
    label = "+ opsin: 16 source-unit waveforms from 12 channels" if condition == "opsin" else "− opsin: selected C0354 source unit 3"
    figure.suptitle(
        label,
        x=0.02,
        y=0.995,
        ha="left",
        fontsize=14,
        fontweight="bold",
        color=CONDITION_COLORS[condition],
    )
    figure.text(
        0.02,
        0.91 if single_row else 0.948,
        "Best-channel template shape aligned to the trough and normalized by trough magnitude.",
        ha="left",
        fontsize=8,
        color="#4B5563",
    )
    figure.subplots_adjust(
        left=0.06,
        right=0.985,
        bottom=0.07,
        top=0.76 if single_row else 0.86,
        wspace=0.28,
        hspace=0.46,
    )
    return figure


def _style(plt) -> None:
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
