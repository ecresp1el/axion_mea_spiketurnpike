#!/usr/bin/env python
"""Plot corrected D2-aware early-only responsive units and an empty control panel."""

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

from scripts.analyze_lumos_per_unit_threshold_response import (  # noqa: E402
    _pulse_position_profiles,
)
from scripts.build_lumos_all_units_unified_psth_store import DEFAULT_JOB_DIR  # noqa: E402
from scripts.plot_lumos_all_units_waveform_classification_pre_peak import (  # noqa: E402
    CLASS_COLORS,
    CLASS_LABELS,
    CLASS_ORDER,
    CONDITION_COLORS,
    OUTPUT_NAME as ALL_UNIT_OUTPUT_NAME,
)


CHANNEL_OUTPUT_NAME = "lumos_channel_pooled_threshold_response_development"
UNIT_RESPONSE_DIR = "lumos_per_unit_threshold_response_development"
OUTPUT_NAME = "lumos_corrected_opto_responsive_units_development"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all-unit-dir", type=Path, default=DEFAULT_JOB_DIR / ALL_UNIT_OUTPUT_NAME
    )
    parser.add_argument(
        "--unit-response-csv",
        type=Path,
        default=DEFAULT_JOB_DIR
        / UNIT_RESPONSE_DIR
        / "per_unit_threshold_response_metrics.csv",
    )
    parser.add_argument(
        "--channel-dir", type=Path, default=DEFAULT_JOB_DIR / CHANNEL_OUTPUT_NAME
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

    all_unit_dir = args.all_unit_dir.expanduser().resolve()
    channel_dir = args.channel_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    all_units = pd.read_csv(all_unit_dir / "all_unit_waveform_pre_peak_metrics.csv")
    all_traces = pd.read_csv(all_unit_dir / "all_unit_normalized_waveform_traces.csv")
    metrics = pd.read_csv(args.unit_response_csv.expanduser().resolve())
    metrics["combined_ge3_candidate"] = (
        metrics["mean_psth_above_baseline_candidate"].astype(bool)
        & metrics["maximum_trials_above_baseline_same_bin"].ge(3)
    )
    decision_metrics = metrics.copy()
    decision_metrics["mean_psth_above_baseline_candidate"] = decision_metrics[
        "combined_ge3_candidate"
    ]
    profiles = _pulse_position_profiles(decision_metrics, "unit_observation_id")
    responsive_profiles = profiles.loc[
        profiles["pulse_response_category"].eq("early_only_p1_p2")
    ].copy()
    condition_counts = responsive_profiles["condition"].value_counts().to_dict()
    if condition_counts != {"opsin": 19}:
        raise ValueError(
            f"expected 19 opsin and zero no-opsin responsive units, found {condition_counts}"
        )
    responsive_profiles["early_max_same_bin_trials"] = responsive_profiles[
        ["pulse_1_max_same_bin_trials", "pulse_2_max_same_bin_trials"]
    ].max(axis=1)
    responsive_profiles = responsive_profiles.sort_values(
        ["early_p1_p2_mean_excess_spikes_per_trial", "well", "unit_id"],
        ascending=[False, True, True],
    ).reset_index(drop=True)
    responsive_profiles.insert(0, "response_rank", np.arange(1, len(responsive_profiles) + 1))
    units = responsive_profiles.merge(
        all_units,
        on="unit_observation_id",
        how="left",
        validate="one_to_one",
        suffixes=("_response", "_unit"),
    )
    traces = all_traces.loc[
        all_traces["unit_observation_id"].isin(units["unit_observation_id"])
    ].copy()

    channel_details = pd.read_csv(channel_dir / "early_only_channel_details.csv")
    channel_profiles = pd.read_csv(
        channel_dir / "per_channel_pulse_position_profiles.csv"
    )
    channel_summary = _channel_summary(channel_details, channel_profiles)
    units.to_csv(staging_dir / "responsive_unit_metrics.csv", index=False)
    traces.to_csv(staging_dir / "responsive_unit_waveform_traces.csv", index=False)
    channel_summary.to_csv(staging_dir / "corrected_channel_summary.csv", index=False)

    _style(plt)
    summary_figure = _plot_summary(
        plt, units, traces, all_units, channel_details, channel_profiles
    )
    summary_figure.savefig(
        staging_dir / "corrected_opto_responsive_unit_summary.png",
        dpi=400,
        bbox_inches="tight",
        facecolor="white",
    )
    gallery_figure = _plot_opsin_gallery(plt, units, traces)
    gallery_figure.savefig(
        staging_dir / "opsin_responsive_unit_waveforms.png",
        dpi=350,
        bbox_inches="tight",
        facecolor="white",
    )
    empty_figure = _plot_empty_control(plt)
    empty_figure.savefig(
        staging_dir / "no_opsin_no_responsive_unit.png",
        dpi=350,
        bbox_inches="tight",
        facecolor="white",
    )
    with PdfPages(staging_dir / "corrected_opto_responsive_units.pdf") as pdf:
        pdf.savefig(summary_figure, bbox_inches="tight")
        pdf.savefig(gallery_figure, bbox_inches="tight")
        pdf.savefig(empty_figure, bbox_inches="tight")
    plt.close(summary_figure)
    plt.close(gallery_figure)
    plt.close(empty_figure)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "development_output": True,
        "overwrite_policy": "entire output directory replaced after successful run",
        "condition_assignment": (
            "D2 is lab-note-confirmed opsin; no other condition exception was introduced"
        ),
        "responsive_unit_rule": (
            "P1 or P2 trial-mean baseline-subtracted PSTH above zero, >=3/50 trials "
            "above baseline in the same 1-ms bin, and no qualifying P3-P5 response"
        ),
        "responsive_units": {"opsin": 19, "no_opsin": 0},
        "waveform_classes": units["waveform_class_unit"].value_counts().to_dict(),
        "control_display": "No opto-responsive unit detected",
        "channel_summary": channel_summary.to_dict(orient="records"),
    }
    (staging_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging_dir.replace(output_dir)
    print(f"Output: {output_dir}")
    print("Responsive units: opsin=19, no_opsin=0")
    print(f"Classes: {units['waveform_class_unit'].value_counts().to_dict()}")
    return 0


def _channel_summary(details, profiles):
    rows = []
    for condition in ["opsin", "no_opsin"]:
        condition_details = details.loc[details["condition"].eq(condition)]
        total = int(profiles["condition"].eq(condition).sum())
        rows.append(
            {
                "condition": condition,
                "early_only_channels": len(condition_details),
                "total_channels": total,
                "early_only_percent": 100 * len(condition_details) / total,
                "note": (
                    "pooled channel candidate; no individual responsive unit"
                    if condition == "no_opsin" and len(condition_details)
                    else ""
                ),
            }
        )
    return pd.DataFrame(rows)


def _plot_summary(plt, units, traces, all_units, channel_details, channel_profiles):
    figure, axes = plt.subplots(2, 3, figsize=(16, 9.2))
    _plot_summary_text(axes[0, 0], units, all_units, channel_details, channel_profiles)
    _plot_pre_peak(axes[0, 1], units)
    _plot_classes(axes[0, 2], units)
    _plot_mean_waveforms(axes[1, 0], units, traces)
    _plot_patterns(axes[1, 1], units)
    _plot_rate_scatter(axes[1, 2], units)
    figure.suptitle(
        "Corrected opto-responsive units after assigning D2 to opsin",
        x=0.02,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    figure.text(
        0.02,
        0.95,
        "Unit rule: early-only P1/P2 response plus ≥3/50 same-bin trials. "
        "All 19 detected units are opsin; no no-opsin unit meets the rule.",
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


def _plot_summary_text(ax, units, all_units, channel_details, channel_profiles):
    ax.axis("off")
    opsin_channels = int(channel_details["condition"].eq("opsin").sum())
    no_channels = int(channel_details["condition"].eq("no_opsin").sum())
    opsin_total_channels = int(channel_profiles["condition"].eq("opsin").sum())
    no_total_channels = int(channel_profiles["condition"].eq("no_opsin").sum())
    class_counts = units["waveform_class_unit"].value_counts()
    lines = [
        "CORRECTED CONDITION ASSIGNMENT",
        "D2 = opsin (confirmed by lab notes)",
        "No other well was reassigned",
        "",
        "Early-only responsive units:",
        f"  Opsin {len(units)}/{int(all_units.condition.eq('opsin').sum())}",
        f"  No opsin 0/{int(all_units.condition.eq('no_opsin').sum())}",
        "",
        "Waveform classes among responsive units:",
        f"  RS-like {int(class_counts.get('RS_like', 0))}",
        f"  Borderline {int(class_counts.get('borderline', 0))}",
        f"  FS-like {int(class_counts.get('FS_like', 0))}",
        "",
        "Channel-level early-only calls:",
        f"  Opsin {opsin_channels}/{opsin_total_channels}",
        f"  No opsin {no_channels}/{no_total_channels}",
        "  The remaining no-opsin call is pooled B4 activity;",
        "  no constituent unit independently meets the rule.",
    ]
    ax.text(0, 1, "\n".join(lines), ha="left", va="top", fontsize=9.2, linespacing=1.28)
    ax.set_title("A  Corrected result", loc="left", fontweight="bold")


def _plot_pre_peak(ax, units):
    rng = np.random.default_rng(20260713)
    offsets = rng.uniform(-0.14, 0.14, len(units))
    for offset, row in zip(offsets, units.itertuples(index=False), strict=True):
        ax.plot([offset, 1 + offset], [row.pre_rate_hz, row.peak_post_rate_hz], color=CONDITION_COLORS["opsin"], alpha=0.42, lw=0.8)
        ax.scatter([offset, 1 + offset], [row.pre_rate_hz, row.peak_post_rate_hz], color=CLASS_COLORS[row.waveform_class_unit], s=24, edgecolor="white", linewidth=0.4, zorder=3)
    ax.set_xticks([0, 1, 3], ["Pre", "Peak post", "No opsin"])
    ax.text(3, 0.5, "No opto-responsive\nunit detected", transform=ax.get_xaxis_transform(), ha="center", va="center", color=CONDITION_COLORS["no_opsin"], fontweight="bold")
    ax.set_xlim(-0.45, 3.65)
    ax.set_ylabel("Unit firing rate (Hz)")
    ax.set_title("B  Pre to peak-post rate", loc="left", fontweight="bold")


def _plot_classes(ax, units):
    values = [int(units["waveform_class_unit"].eq(label).sum()) for label in CLASS_ORDER]
    bars = ax.bar(range(3), values, color=[CLASS_COLORS[label] for label in CLASS_ORDER], width=0.65)
    ax.bar_label(bars, fontsize=9)
    ax.set_xticks(range(3), [CLASS_LABELS[label] for label in CLASS_ORDER])
    ax.set_xlim(-0.5, 3.4)
    ax.set_ylabel("Responsive opsin units")
    ax.set_title("C  Waveform classification", loc="left", fontweight="bold")
    ax.text(2.8, max(values) * 0.72, "No opto-responsive\nno-opsin unit detected", ha="right", color=CONDITION_COLORS["no_opsin"], fontweight="bold")


def _plot_mean_waveforms(ax, units, traces):
    merged = traces.merge(
        units[["unit_observation_id", "waveform_class_unit"]],
        on="unit_observation_id",
        validate="many_to_one",
    )
    for class_label in CLASS_ORDER:
        subset = merged.loc[merged["waveform_class_unit"].eq(class_label)]
        if subset.empty:
            continue
        summary = subset.groupby("aligned_time_ms")["normalized_waveform"].agg(["mean", "sem"])
        ax.plot(summary.index, summary["mean"], color=CLASS_COLORS[class_label], lw=1.8, label=f"{CLASS_LABELS[class_label]} n={subset['unit_observation_id'].nunique()}")
        ax.fill_between(summary.index, summary["mean"] - summary["sem"].fillna(0), summary["mean"] + summary["sem"].fillna(0), color=CLASS_COLORS[class_label], alpha=0.18, linewidth=0)
    ax.axhline(0, color="#9CA3AF", lw=0.7)
    ax.axvline(0, color="#9CA3AF", lw=0.7, ls="--")
    ax.set_xlabel("Time from trough (ms)")
    ax.set_ylabel("Normalized waveform")
    ax.set_title("D  Responsive opsin mean waveforms", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=8)


def _plot_patterns(ax, units):
    labels = ["P1 only", "P2 only", "P1 + P2"]
    patterns = [
        "P1=1;P2=0;P3=0;P4=0;P5=0",
        "P1=0;P2=1;P3=0;P4=0;P5=0",
        "P1=1;P2=1;P3=0;P4=0;P5=0",
    ]
    values = [int(units["pulse_response_pattern"].eq(pattern).sum()) for pattern in patterns]
    bars = ax.bar(range(3), values, color=CONDITION_COLORS["opsin"], width=0.65)
    ax.bar_label(bars, fontsize=9)
    ax.set_xticks(range(3), labels)
    ax.set_ylabel("Responsive opsin units")
    ax.set_title("E  Early pulse pattern", loc="left", fontweight="bold")


def _plot_rate_scatter(ax, units):
    for class_label in CLASS_ORDER:
        subset = units.loc[units["waveform_class_unit"].eq(class_label)]
        ax.scatter(subset["pre_rate_hz"], subset["peak_post_rate_hz"], s=42, color=CLASS_COLORS[class_label], alpha=0.75, edgecolor="white", linewidth=0.5, label=f"{CLASS_LABELS[class_label]} n={len(subset)}")
    maximum = float(max(units["pre_rate_hz"].max(), units["peak_post_rate_hz"].max()))
    ax.plot([0, maximum], [0, maximum], color="#6B7280", ls="--", lw=0.8)
    for row in units.itertuples(index=False):
        ax.text(row.pre_rate_hz, row.peak_post_rate_hz, str(row.response_rank), ha="center", va="center", fontsize=6, color="white", fontweight="bold")
    ax.set_xlabel("Pre rate (Hz)")
    ax.set_ylabel("Peak-post rate (Hz)")
    ax.set_title("F  Every responsive opsin unit; label = rank", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=7)


def _plot_opsin_gallery(plt, units, traces):
    rows, columns = 5, 4
    figure, axes = plt.subplots(rows, columns, figsize=(16, 3.0 * rows), squeeze=False)
    flat_axes = axes.ravel()
    for axis, row in zip(flat_axes, units.itertuples(index=False), strict=False):
        trace = traces.loc[traces["unit_observation_id"].eq(row.unit_observation_id)].sort_values("aligned_time_ms")
        color = CLASS_COLORS[row.waveform_class_unit]
        axis.plot(trace["aligned_time_ms"], trace["normalized_waveform"], color=color, lw=1.6)
        axis.axhline(0, color="#9CA3AF", lw=0.65)
        axis.axvline(0, color="#9CA3AF", lw=0.65, ls="--")
        axis.set_title(f"Rank {row.response_rank} | {row.well_response} | unit {row.unit_id_response}", loc="left", fontsize=8.3, fontweight="bold")
        axis.text(0.02, 0.97, f"{str(row.KSLabel_response).upper()} | {CLASS_LABELS[row.waveform_class_unit]} | {row.pulse_response_pattern.replace(';P3=0;P4=0;P5=0', '')}\npre→peak {row.pre_rate_hz:.1f}→{row.peak_post_rate_hz:.1f} Hz | same-bin max {int(row.early_max_same_bin_trials)}/50", transform=axis.transAxes, ha="left", va="top", fontsize=7, color="#30343B")
        axis.set_xlabel("Time from trough (ms)")
        axis.set_ylabel("Normalized amplitude")
        axis.spines[["top", "right"]].set_visible(False)
    for axis in flat_axes[len(units) :]:
        axis.axis("off")
    figure.suptitle("All 19 corrected opto-responsive opsin units", x=0.02, y=0.995, ha="left", fontsize=14, fontweight="bold", color=CONDITION_COLORS["opsin"])
    figure.text(0.02, 0.965, "D2 is included as opsin. Waveform color shows RS-like, borderline, or FS-like classification.", ha="left", fontsize=8, color="#4B5563")
    figure.subplots_adjust(left=0.06, right=0.985, bottom=0.055, top=0.90, wspace=0.28, hspace=0.46)
    return figure


def _plot_empty_control(plt):
    figure, ax = plt.subplots(figsize=(12, 5))
    ax.axis("off")
    ax.text(0.5, 0.58, "NO OPSIN", ha="center", va="center", fontsize=18, fontweight="bold", color=CONDITION_COLORS["no_opsin"])
    ax.text(0.5, 0.42, "No opto-responsive unit detected", ha="center", va="center", fontsize=24, fontweight="bold", color="#30343B")
    ax.text(0.5, 0.28, "No waveform or pre/post rate is plotted because no individual no-opsin unit meets the early-only ≥3/50 rule.", ha="center", va="center", fontsize=10, color="#6B7280")
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
