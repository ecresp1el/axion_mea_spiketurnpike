#!/usr/bin/env python
"""Show every unit waveform underlying >=3/50 early-only channel candidates."""

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

from scripts.build_lumos_all_unit_waveform_metrics import _templates_average  # noqa: E402
from scripts.build_lumos_all_units_unified_psth_store import DEFAULT_JOB_DIR  # noqa: E402
from scripts.plot_lumos_all_units_waveform_classification_pre_peak import (  # noqa: E402
    CLASS_COLORS,
    CLASS_LABELS,
    CLASS_ORDER,
    COMMON_TIME_MS,
    CONDITION_COLORS,
    CONDITION_LABELS,
    CONDITION_ORDER,
    OUTPUT_NAME as ALL_UNIT_OUTPUT_NAME,
    _aligned_normalized_waveform,
)
from scripts.plot_lumos_opsin_pre_post_unit_firing_rates import (  # noqa: E402
    _match_unit_id,
    _unit_label,
)


CHANNEL_OUTPUT_NAME = "lumos_channel_pooled_threshold_response_development"
OUTPUT_NAME = "lumos_early_only_ge3_channel_unit_waveforms_development"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--channel-dir", type=Path, default=DEFAULT_JOB_DIR / CHANNEL_OUTPUT_NAME
    )
    parser.add_argument(
        "--all-unit-dir", type=Path, default=DEFAULT_JOB_DIR / ALL_UNIT_OUTPUT_NAME
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
    import spikeinterface.full as si
    from matplotlib.backends.backend_pdf import PdfPages

    channel_dir = args.channel_dir.expanduser().resolve()
    all_unit_dir = args.all_unit_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    channels = pd.read_csv(channel_dir / "early_only_channel_details.csv")
    profiles = pd.read_csv(channel_dir / "per_channel_pulse_position_profiles.csv")
    all_units = pd.read_csv(all_unit_dir / "all_unit_waveform_pre_peak_metrics.csv")
    links = _unit_channel_links(channels)
    units = links.merge(
        all_units,
        on="unit_observation_id",
        how="left",
        validate="many_to_one",
        suffixes=("_channel", "_unit"),
    )
    if units["unit_id"].isna().any():
        raise ValueError("some qualifying-channel source units are missing all-unit metadata")
    if not units["condition_channel"].eq(units["condition_unit"]).all():
        raise ValueError("channel and unit condition assignments disagree")

    waveform_lookup: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    normalized_rows: list[dict[str, object]] = []
    error_rows: list[dict[str, object]] = []
    for progress, (analyzer_path_text, group) in enumerate(
        units.groupby("analyzer_path", sort=True), start=1
    ):
        analyzer_path = Path(str(analyzer_path_text))
        try:
            analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
            templates_ext = analyzer.get_extension("templates")
            if templates_ext is None:
                raise ValueError("templates extension is unavailable")
            templates = _templates_average(templates_ext)
            unit_ids = list(analyzer.sorting.get_unit_ids())
            frequency = float(analyzer.recording.get_sampling_frequency())
            index_by_label = {
                _unit_label(unit_id): index for index, unit_id in enumerate(unit_ids)
            }
            for row in group.itertuples(index=False):
                matched = _match_unit_id(unit_ids, row.unit_id)
                unit_index = index_by_label[_unit_label(matched)]
                waveform = np.asarray(
                    templates[unit_index, :, int(row.best_channel_index)], dtype=float
                )
                baseline = float(np.nanmedian(waveform[: min(5, len(waveform))]))
                centered = waveform - baseline
                trough_index = int(np.nanargmin(centered))
                native_time = (
                    np.arange(len(centered), dtype=float) - trough_index
                ) / frequency * 1000.0
                waveform_lookup[str(row.unit_observation_id)] = (native_time, centered)
                normalized = _aligned_normalized_waveform(
                    waveform, frequency, COMMON_TIME_MS
                )
                for time_ms, value in zip(COMMON_TIME_MS, normalized, strict=True):
                    normalized_rows.append(
                        {
                            "unit_observation_id": row.unit_observation_id,
                            "condition": row.condition_channel,
                            "waveform_class": row.waveform_class,
                            "aligned_time_ms": time_ms,
                            "normalized_waveform": value,
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            for row in group.itertuples(index=False):
                error_rows.append(
                    {
                        "unit_observation_id": row.unit_observation_id,
                        "analyzer_path": str(analyzer_path),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        print(
            f"[{progress:02d}/{units['analyzer_path'].nunique():02d}] focused analyzers",
            flush=True,
        )
    if len(waveform_lookup) != len(units):
        raise ValueError(
            f"waveform extraction succeeded for {len(waveform_lookup)}/{len(units)} units"
        )

    normalized_traces = pd.DataFrame(normalized_rows)
    waveform_summary = _mean_waveform_summary(normalized_traces)
    units = units.sort_values(
        ["condition_order", "condition_rank", "channel_observation_id", "unit_id"]
    ).reset_index(drop=True)
    units.to_csv(staging_dir / "qualifying_channel_source_units.csv", index=False)
    normalized_traces.to_csv(
        staging_dir / "qualifying_unit_normalized_waveform_traces.csv", index=False
    )
    waveform_summary.to_csv(staging_dir / "mean_waveform_summary.csv", index=False)
    pd.DataFrame(
        error_rows, columns=["unit_observation_id", "analyzer_path", "error"]
    ).to_csv(staging_dir / "waveform_extraction_errors.csv", index=False)

    _style(plt)
    summary_figure = _plot_summary(plt, channels, profiles, units, waveform_summary)
    summary_figure.savefig(
        staging_dir / "qualifying_channel_unit_waveform_summary.png",
        dpi=400,
        bbox_inches="tight",
        facecolor="white",
    )
    opsin_figure = _plot_gallery(
        plt,
        units.loc[units["condition_channel"].eq("opsin")],
        waveform_lookup,
        condition="opsin",
        rows=4,
        columns=4,
    )
    opsin_figure.savefig(
        staging_dir / "qualifying_opsin_unit_waveform_gallery.png",
        dpi=350,
        bbox_inches="tight",
        facecolor="white",
    )
    no_opsin_figure = _plot_gallery(
        plt,
        units.loc[units["condition_channel"].eq("no_opsin")],
        waveform_lookup,
        condition="no_opsin",
        rows=2,
        columns=3,
    )
    no_opsin_figure.savefig(
        staging_dir / "qualifying_no_opsin_unit_waveform_gallery.png",
        dpi=350,
        bbox_inches="tight",
        facecolor="white",
    )
    with PdfPages(staging_dir / "qualifying_channel_unit_waveforms.pdf") as pdf:
        pdf.savefig(summary_figure, bbox_inches="tight")
        pdf.savefig(opsin_figure, bbox_inches="tight")
        pdf.savefig(no_opsin_figure, bbox_inches="tight")
    plt.close(summary_figure)
    plt.close(opsin_figure)
    plt.close(no_opsin_figure)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "development_output": True,
        "overwrite_policy": "entire output directory replaced after successful run",
        "channel_inclusion": (
            "trial-mean baseline-subtracted PSTH above zero and >=3/50 trials "
            "above baseline in the same 1-ms bin; P1 or P2 included and P3-P5 excluded"
        ),
        "qualifying_channels": channels["condition"].value_counts().to_dict(),
        "source_unit_observations": units["condition_channel"].value_counts().to_dict(),
        "waveforms": (
            "best-channel templates.average, baseline-centered and aligned to trough; "
            "gallery is physical template amplitude, group means are trough-normalized"
        ),
        "unit_pre_rate": "-200 to 0 ms before pulse 1",
        "unit_peak_post_rate": "maximum once-smoothed mean PSTH during 0-250 ms train",
        "channel_source": str(channel_dir / "early_only_channel_details.csv"),
        "unit_source": str(all_unit_dir / "all_unit_waveform_pre_peak_metrics.csv"),
    }
    (staging_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging_dir.replace(output_dir)
    print(f"\nOutput: {output_dir}")
    print(f"Qualifying channels: {channels['condition'].value_counts().to_dict()}")
    print(
        "Source units: "
        f"{units['condition_channel'].value_counts().to_dict()}"
    )
    return 0


def _unit_channel_links(channels: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for channel in channels.itertuples(index=False):
        for unit_observation_id in str(channel.source_unit_observation_ids).split(";"):
            rows.append(
                {
                    "condition_order": 0 if channel.condition == "opsin" else 1,
                    "condition_rank": int(channel.condition_rank),
                    "condition": channel.condition,
                    "channel_observation_id": channel.channel_observation_id,
                    "channel_well": channel.well,
                    "channel_physical_id": channel.best_channel_id,
                    "pulse_response_pattern": channel.pulse_response_pattern,
                    "full_train_peak_mean_excess_hz": channel.full_train_peak_mean_excess_hz,
                    "full_train_peak_latency_ms": channel.full_train_peak_latency_ms,
                    "full_train_max_same_bin_trials": channel.full_train_max_same_bin_trials,
                    "unit_observation_id": unit_observation_id,
                }
            )
    return pd.DataFrame(rows)


def _mean_waveform_summary(traces: pd.DataFrame) -> pd.DataFrame:
    return (
        traces.groupby(["condition", "waveform_class", "aligned_time_ms"])[
            "normalized_waveform"
        ]
        .agg(["count", "mean", "std"])
        .reset_index()
        .assign(sem=lambda frame: frame["std"] / np.sqrt(frame["count"]))
        .rename(
            columns={
                "count": "finite_unit_count",
                "mean": "mean_normalized_waveform",
                "std": "sd_normalized_waveform",
                "sem": "sem_normalized_waveform",
            }
        )
    )


def _plot_summary(plt, channels, profiles, units, waveform_summary):
    figure, axes = plt.subplots(2, 3, figsize=(16, 9.2))
    _plot_channel_summary_text(axes[0, 0], channels, profiles, units)
    _plot_unit_classification(axes[0, 1], units)
    _plot_channel_peak_timing(axes[0, 2], channels)
    _plot_mean_waveforms(axes[1, 0], waveform_summary, "opsin")
    _plot_mean_waveforms(axes[1, 1], waveform_summary, "no_opsin")
    _plot_unit_rates(axes[1, 2], units)
    figure.suptitle(
        "Units underlying early-only channels meeting the ≥3/50 same-bin rule",
        x=0.02,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    figure.text(
        0.02,
        0.95,
        "Channel selection is exact; all source good/MUA units are retained. "
        "Mean waveforms are trough-normalized; gallery pages show physical template amplitude.",
        ha="left",
        fontsize=8.5,
        color="#4B5563",
    )
    figure.subplots_adjust(
        left=0.055,
        right=0.985,
        bottom=0.07,
        top=0.87,
        wspace=0.26,
        hspace=0.28,
    )
    return figure


def _plot_channel_summary_text(ax, channels, profiles, units):
    ax.axis("off")
    totals = profiles.groupby("condition").size()
    counts = channels["condition"].value_counts()
    patterns = {
        condition: channels.loc[channels["condition"].eq(condition), "pulse_response_pattern"]
        .value_counts()
        .to_dict()
        for condition in CONDITION_ORDER
    }
    lines = [
        "CHANNEL RESPONSE SUBSET",
        "Mean-PSTH criterion + ≥3/50 same-bin trials",
        "",
        f"+ opsin: {counts.get('opsin', 0)}/{totals.get('opsin', 0)} "
        f"({100 * counts.get('opsin', 0) / totals.get('opsin', 1):.1f}%)",
        f"− opsin: {counts.get('no_opsin', 0)}/{totals.get('no_opsin', 0)} "
        f"({100 * counts.get('no_opsin', 0) / totals.get('no_opsin', 1):.1f}%)",
        "",
        "Full-train peak excess, median / maximum:",
        f"  + opsin {channels.loc[channels.condition.eq('opsin'), 'full_train_peak_mean_excess_hz'].median():.1f} / "
        f"{channels.loc[channels.condition.eq('opsin'), 'full_train_peak_mean_excess_hz'].max():.1f} Hz",
        f"  − opsin {channels.loc[channels.condition.eq('no_opsin'), 'full_train_peak_mean_excess_hz'].median():.1f} / "
        f"{channels.loc[channels.condition.eq('no_opsin'), 'full_train_peak_mean_excess_hz'].max():.1f} Hz",
        "",
        "Median full-train peak latency:",
        f"  + opsin {channels.loc[channels.condition.eq('opsin'), 'full_train_peak_latency_ms'].median():.1f} ms",
        f"  − opsin {channels.loc[channels.condition.eq('no_opsin'), 'full_train_peak_latency_ms'].median():.1f} ms",
        "",
        "Pulse patterns:",
        f"  + opsin: both={patterns['opsin'].get('P1=1;P2=1;P3=0;P4=0;P5=0', 0)}, "
        f"P2-only={patterns['opsin'].get('P1=0;P2=1;P3=0;P4=0;P5=0', 0)}, "
        f"P1-only={patterns['opsin'].get('P1=1;P2=0;P3=0;P4=0;P5=0', 0)}",
        f"  − opsin: both={patterns['no_opsin'].get('P1=1;P2=1;P3=0;P4=0;P5=0', 0)}, "
        f"P2-only={patterns['no_opsin'].get('P1=0;P2=1;P3=0;P4=0;P5=0', 0)}, "
        f"P1-only={patterns['no_opsin'].get('P1=1;P2=0;P3=0;P4=0;P5=0', 0)}",
        "",
        f"Underlying units: + opsin {int(units.condition_channel.eq('opsin').sum())}; "
        f"− opsin {int(units.condition_channel.eq('no_opsin').sum())}",
    ]
    ax.text(0, 1, "\n".join(lines), va="top", ha="left", fontsize=9, linespacing=1.28)
    ax.set_title("A  Exact subset", loc="left", fontweight="bold")


def _plot_unit_classification(ax, units):
    bottoms = np.zeros(2)
    for class_label in CLASS_ORDER:
        values = []
        counts = []
        for condition in CONDITION_ORDER:
            subset = units.loc[units["condition_channel"].eq(condition)]
            count = int(subset["waveform_class"].eq(class_label).sum())
            values.append(100 * count / len(subset))
            counts.append(count)
        ax.bar(range(2), values, bottom=bottoms, width=0.62, color=CLASS_COLORS[class_label], label=CLASS_LABELS[class_label])
        for index, (value, count) in enumerate(zip(values, counts, strict=True)):
            if value >= 8:
                ax.text(index, bottoms[index] + value / 2, str(count), ha="center", va="center", color="white", fontweight="bold")
        bottoms += values
    condition_counts = units["condition_channel"].value_counts()
    ax.set_xticks([0, 1], [f"+ opsin\nn={condition_counts.get('opsin', 0)}", f"− opsin\nn={condition_counts.get('no_opsin', 0)}"])
    ax.set_ylim(0, 106)
    ax.set_ylabel("Source units (%)")
    ax.set_title("B  Unit waveform classes", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=8, loc="upper right")


def _plot_channel_peak_timing(ax, channels):
    for condition in CONDITION_ORDER:
        subset = channels.loc[channels["condition"].eq(condition)]
        sizes = 25 + 13 * subset["full_train_max_same_bin_trials"].to_numpy(float)
        ax.scatter(
            subset["full_train_peak_latency_ms"],
            subset["full_train_peak_mean_excess_hz"],
            s=sizes,
            color=CONDITION_COLORS[condition],
            alpha=0.78,
            edgecolor="white",
            linewidth=0.5,
            label=f"{CONDITION_LABELS[condition]} n={len(subset)}",
        )
        for row in subset.itertuples(index=False):
            ax.text(row.full_train_peak_latency_ms, row.full_train_peak_mean_excess_hz, str(row.condition_rank), ha="center", va="center", fontsize=6, color="white", fontweight="bold")
    ax.set_xlabel("Full-train peak latency (ms)")
    ax.set_ylabel("Peak excess rate (Hz)")
    ax.set_title("C  Qualifying channels; label = rank", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=8)


def _plot_mean_waveforms(ax, summary, condition):
    for class_label in CLASS_ORDER:
        subset = summary.loc[
            summary["condition"].eq(condition)
            & summary["waveform_class"].eq(class_label)
        ].sort_values("aligned_time_ms")
        if subset.empty:
            continue
        x = subset["aligned_time_ms"].to_numpy(float)
        mean = subset["mean_normalized_waveform"].to_numpy(float)
        sem = subset["sem_normalized_waveform"].fillna(0).to_numpy(float)
        n = int(subset["finite_unit_count"].max())
        ax.plot(x, mean, color=CLASS_COLORS[class_label], lw=1.8, label=f"{CLASS_LABELS[class_label]} n={n}")
        ax.fill_between(x, mean - sem, mean + sem, color=CLASS_COLORS[class_label], alpha=0.18, linewidth=0)
    ax.axhline(0, color="#9CA3AF", lw=0.7)
    ax.axvline(0, color="#9CA3AF", lw=0.7, ls="--")
    ax.set_xlabel("Time from trough (ms)")
    ax.set_ylabel("Normalized amplitude")
    panel = "D" if condition == "opsin" else "E"
    ax.set_title(f"{panel}  {CONDITION_LABELS[condition]} source units", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=7.5)


def _plot_unit_rates(ax, units):
    for condition in CONDITION_ORDER:
        subset = units.loc[units["condition_channel"].eq(condition)]
        ax.scatter(
            subset["pre_rate_hz"],
            subset["peak_post_rate_hz"],
            s=35,
            color=CONDITION_COLORS[condition],
            alpha=0.72,
            edgecolor="white",
            linewidth=0.5,
            label=f"{CONDITION_LABELS[condition]} n={len(subset)}",
        )
    maximum = float(max(units["pre_rate_hz"].max(), units["peak_post_rate_hz"].max()))
    ax.plot([0, maximum], [0, maximum], color="#6B7280", ls="--", lw=0.8)
    ax.set_xlabel("Unit pre rate (Hz)")
    ax.set_ylabel("Unit peak post rate (Hz)")
    ax.set_title("F  Every contributing unit", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=8)


def _plot_gallery(plt, units, waveform_lookup, *, condition, rows, columns):
    figure, axes = plt.subplots(rows, columns, figsize=(16, 3.2 * rows), squeeze=False)
    flat_axes = axes.ravel()
    for axis, row in zip(flat_axes, units.itertuples(index=False), strict=False):
        time_ms, waveform = waveform_lookup[str(row.unit_observation_id)]
        color = CLASS_COLORS.get(str(row.waveform_class), "#444444")
        axis.plot(time_ms, waveform, color=color, lw=1.5)
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
            f"{str(row.KSLabel).upper()} | {CLASS_LABELS.get(str(row.waveform_class), row.waveform_class)}\n"
            f"unit pre→peak: {row.pre_rate_hz:.1f}→{row.peak_post_rate_hz:.1f} Hz @ {row.peak_latency_ms:.1f} ms\n"
            f"channel: {_compact_pattern(row.pulse_response_pattern)} | "
            f"peak excess {row.full_train_peak_mean_excess_hz:.1f} Hz @ "
            f"{row.full_train_peak_latency_ms:.1f} ms | "
            f"{int(row.full_train_max_same_bin_trials)}/50",
            transform=axis.transAxes,
            ha="left",
            va="top",
            fontsize=7,
            color="#30343B",
        )
        axis.set_xlabel("Time from trough (ms)")
        axis.set_ylabel("Template amplitude (µV)")
        axis.spines[["top", "right"]].set_visible(False)
    for axis in flat_axes[len(units) :]:
        axis.axis("off")
    figure.suptitle(
        f"{CONDITION_LABELS[condition]}: every unit underlying a qualifying early-only channel",
        x=0.02,
        y=0.995,
        ha="left",
        fontsize=14,
        fontweight="bold",
        color=CONDITION_COLORS[condition],
    )
    figure.text(
        0.02,
        0.948,
        "Physical best-channel template waveform; cards are ordered by channel response rank. "
        "Unit rates and channel response metrics are shown separately.",
        ha="left",
        fontsize=8,
        color="#4B5563",
    )
    figure.subplots_adjust(left=0.06, right=0.985, bottom=0.06, top=0.865, wspace=0.28, hspace=0.46)
    return figure


def _compact_pattern(pattern: str) -> str:
    active = [part.split("=")[0] for part in str(pattern).split(";") if part.endswith("=1")]
    return "+".join(active) if active else "none"


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
