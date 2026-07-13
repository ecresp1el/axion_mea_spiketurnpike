#!/usr/bin/env python
"""Compare suspected-opsin well D2 with the remaining nominal no-opsin wells."""

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
    OUTPUT_NAME as ALL_UNIT_OUTPUT_NAME,
)


UNIT_RESPONSE_DIR = "lumos_per_unit_threshold_response_development"
OUTPUT_NAME = "lumos_d2_vs_other_noopsin_units_development"
GROUP_ORDER = ["D2_suspected_opsin", "other_no_opsin"]
GROUP_LABELS = {
    "D2_suspected_opsin": "D2\nsuspected opsin",
    "other_no_opsin": "Other nominal\nno opsin",
}
GROUP_COLORS = {"D2_suspected_opsin": "#E45756", "other_no_opsin": "#4C78A8"}


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
        "--output-dir", type=Path, default=DEFAULT_JOB_DIR / OUTPUT_NAME
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    all_unit_dir = args.all_unit_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    units = pd.read_csv(all_unit_dir / "all_unit_waveform_pre_peak_metrics.csv")
    units = units.loc[units["condition"].eq("no_opsin")].copy()
    units["comparison_group"] = np.where(
        units["well"].eq("D2"), "D2_suspected_opsin", "other_no_opsin"
    )
    traces = pd.read_csv(all_unit_dir / "all_unit_normalized_waveform_traces.csv")
    traces = traces.loc[traces["unit_observation_id"].isin(units["unit_observation_id"])].copy()
    traces = traces.merge(
        units[["unit_observation_id", "comparison_group"]],
        on="unit_observation_id",
        validate="many_to_one",
    )

    response_metrics = pd.read_csv(args.unit_response_csv.expanduser().resolve())
    response_metrics = response_metrics.loc[
        response_metrics["unit_observation_id"].isin(units["unit_observation_id"])
    ].copy()
    response_metrics["combined_ge3_candidate"] = (
        response_metrics["mean_psth_above_baseline_candidate"].astype(bool)
        & response_metrics["maximum_trials_above_baseline_same_bin"].ge(3)
    )
    decision_metrics = response_metrics.copy()
    decision_metrics["mean_psth_above_baseline_candidate"] = decision_metrics[
        "combined_ge3_candidate"
    ]
    profiles = _pulse_position_profiles(decision_metrics, "unit_observation_id")
    profiles = profiles.merge(
        units[["unit_observation_id", "comparison_group"]],
        on="unit_observation_id",
        validate="one_to_one",
    )
    train = response_metrics.loc[response_metrics["target"].eq("train_250ms")][
        ["unit_observation_id", "combined_ge3_candidate"]
    ]
    units = units.merge(train, on="unit_observation_id", validate="one_to_one")
    units = units.merge(
        profiles[["unit_observation_id", "pulse_response_category"]],
        on="unit_observation_id",
        validate="one_to_one",
    )

    waveform_summary = _waveform_summary(traces)
    group_summary = _group_summary(units)
    units.to_csv(staging_dir / "d2_vs_other_noopsin_unit_metrics.csv", index=False)
    waveform_summary.to_csv(staging_dir / "d2_vs_other_mean_waveforms.csv", index=False)
    group_summary.to_csv(staging_dir / "d2_vs_other_summary.csv", index=False)

    _style(plt)
    figure = _plot_figure(plt, units, waveform_summary)
    figure.savefig(
        staging_dir / "d2_vs_other_noopsin_unit_comparison.png",
        dpi=400,
        bbox_inches="tight",
        facecolor="white",
    )
    figure.savefig(
        staging_dir / "d2_vs_other_noopsin_unit_comparison.pdf",
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(figure)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "development_output": True,
        "overwrite_policy": "entire output directory replaced after successful run",
        "status": (
            "comparison-only; D2 is labeled suspected opsin from user lab notes, "
            "but source condition metadata are not modified"
        ),
        "D2_unit_observations": int(units["well"].eq("D2").sum()),
        "other_nominal_no_opsin_wells": sorted(
            units.loc[~units["well"].eq("D2"), "well"].unique().tolist()
        ),
        "response_rule": "mean PSTH above baseline plus >=3/50 same-bin trials",
        "pre_rate": "-200 to 0 ms before pulse 1",
        "peak_post_rate": "maximum once-smoothed trial-mean PSTH during 0-250 ms",
        "waveforms": "trough-aligned and trough-normalized best-channel templates",
    }
    (staging_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging_dir.replace(output_dir)
    print(f"Output: {output_dir}")
    print(units["comparison_group"].value_counts().to_dict())
    return 0


def _waveform_summary(traces):
    return (
        traces.groupby(
            ["comparison_group", "waveform_class", "aligned_time_ms"]
        )["normalized_waveform"]
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


def _group_summary(units):
    rows = []
    for group in GROUP_ORDER:
        subset = units.loc[units["comparison_group"].eq(group)]
        rows.append(
            {
                "comparison_group": group,
                "unit_observations": len(subset),
                "wells": subset["well"].nunique(),
                "good_units": int(subset["KSLabel"].eq("good").sum()),
                "mua_units": int(subset["KSLabel"].eq("mua").sum()),
                "FS_like": int(subset["waveform_class"].eq("FS_like").sum()),
                "borderline": int(subset["waveform_class"].eq("borderline").sum()),
                "RS_like": int(subset["waveform_class"].eq("RS_like").sum()),
                "median_template_ptp_uV": subset["template_ptp_uV"].median(),
                "median_pre_rate_hz": subset["pre_rate_hz"].median(),
                "median_peak_post_rate_hz": subset["peak_post_rate_hz"].median(),
                "early_only_ge3_units": int(
                    subset["pulse_response_category"].eq("early_only_p1_p2").sum()
                ),
                "train_ge3_units": int(subset["combined_ge3_candidate"].sum()),
            }
        )
    return pd.DataFrame(rows)


def _plot_figure(plt, units, waveforms):
    figure, axes = plt.subplots(2, 4, figsize=(19, 9.4))
    _plot_classification(axes[0, 0], units)
    _plot_mean_waveforms(axes[0, 1], waveforms, "D2_suspected_opsin")
    _plot_mean_waveforms(axes[0, 2], waveforms, "other_no_opsin")
    _plot_ptp(axes[0, 3], units)
    _plot_rate_distributions(axes[1, 0], units)
    _plot_rate_scatter(axes[1, 1], units, "D2_suspected_opsin")
    _plot_rate_scatter(axes[1, 2], units, "other_no_opsin")
    _plot_response_rates(axes[1, 3], units)
    y_limits = (
        min(axes[0, 1].get_ylim()[0], axes[0, 2].get_ylim()[0]),
        max(axes[0, 1].get_ylim()[1], axes[0, 2].get_ylim()[1]),
    )
    axes[0, 1].set_ylim(y_limits)
    axes[0, 2].set_ylim(y_limits)
    figure.suptitle(
        "D2 suspected-opsin well versus the remaining nominal no-opsin wells",
        x=0.02,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    figure.text(
        0.02,
        0.95,
        "D2 contains 131 unit observations; comparison wells are A3, B2, B4, C3, and E2 (253 observations). "
        "No source condition labels have been changed.",
        ha="left",
        fontsize=8.5,
        color="#4B5563",
    )
    figure.subplots_adjust(
        left=0.05,
        right=0.99,
        bottom=0.07,
        top=0.87,
        wspace=0.29,
        hspace=0.28,
    )
    return figure


def _plot_classification(ax, units):
    bottoms = np.zeros(2)
    for class_label in CLASS_ORDER:
        fractions, counts = [], []
        for group in GROUP_ORDER:
            subset = units.loc[units["comparison_group"].eq(group)]
            count = int(subset["waveform_class"].eq(class_label).sum())
            fractions.append(100 * count / len(subset))
            counts.append(count)
        ax.bar(range(2), fractions, bottom=bottoms, width=0.65, color=CLASS_COLORS[class_label], label=CLASS_LABELS[class_label])
        for index, (fraction, count) in enumerate(zip(fractions, counts, strict=True)):
            if fraction > 6:
                ax.text(index, bottoms[index] + fraction / 2, str(count), ha="center", va="center", color="white", fontweight="bold")
        bottoms += fractions
    ax.set_xticks([0, 1], [f"D2\nn={len(units.loc[units.comparison_group.eq(GROUP_ORDER[0])])}", f"Other wells\nn={len(units.loc[units.comparison_group.eq(GROUP_ORDER[1])])}"])
    ax.set_ylabel("Units (%)")
    ax.set_title("A  Waveform classes", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=7.5)


def _plot_mean_waveforms(ax, summary, group):
    for class_label in CLASS_ORDER:
        subset = summary.loc[
            summary["comparison_group"].eq(group)
            & summary["waveform_class"].eq(class_label)
        ].sort_values("aligned_time_ms")
        x = subset["aligned_time_ms"].to_numpy(float)
        mean = subset["mean_normalized_waveform"].to_numpy(float)
        sem = subset["sem_normalized_waveform"].fillna(0).to_numpy(float)
        n = int(subset["finite_unit_count"].max())
        ax.plot(x, mean, color=CLASS_COLORS[class_label], lw=1.7, label=f"{CLASS_LABELS[class_label]} n={n}")
        ax.fill_between(x, mean - sem, mean + sem, color=CLASS_COLORS[class_label], alpha=0.16, linewidth=0)
    ax.axhline(0, color="#9CA3AF", lw=0.7)
    ax.axvline(0, color="#9CA3AF", lw=0.7, ls="--")
    ax.set_xlabel("Time from trough (ms)")
    ax.set_ylabel("Normalized waveform")
    panel = "B" if group == GROUP_ORDER[0] else "C"
    ax.set_title(f"{panel}  {GROUP_LABELS[group].replace(chr(10), ' ')}", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=7)


def _plot_ptp(ax, units):
    values = [
        np.log10(units.loc[units["comparison_group"].eq(group), "template_ptp_uV"].clip(lower=0.01))
        for group in GROUP_ORDER
    ]
    box = ax.boxplot(values, positions=[0, 1], widths=0.55, patch_artist=True, showfliers=False)
    for patch, group in zip(box["boxes"], GROUP_ORDER, strict=True):
        patch.set_facecolor(GROUP_COLORS[group]); patch.set_alpha(0.65)
    ticks = np.array([0.1, 0.3, 1, 3, 10, 30, 100])
    ax.set_yticks(np.log10(ticks), [f"{value:g}" for value in ticks])
    ax.set_xticks([0, 1], ["D2", "Other wells"])
    ax.set_ylabel("Template PTP (µV; log display)")
    ax.set_title("D  Template amplitude", loc="left", fontweight="bold")


def _rate_transform(values):
    return np.log10(np.asarray(values, dtype=float) + 0.1)


def _plot_rate_distributions(ax, units):
    positions = [0, 1, 3, 4]
    groups = [
        units.loc[units.comparison_group.eq(GROUP_ORDER[0]), "pre_rate_hz"],
        units.loc[units.comparison_group.eq(GROUP_ORDER[0]), "peak_post_rate_hz"],
        units.loc[units.comparison_group.eq(GROUP_ORDER[1]), "pre_rate_hz"],
        units.loc[units.comparison_group.eq(GROUP_ORDER[1]), "peak_post_rate_hz"],
    ]
    transformed = [_rate_transform(group) for group in groups]
    violin = ax.violinplot(transformed, positions=positions, widths=0.8, showextrema=False)
    colors = ["#C7CDD6", GROUP_COLORS[GROUP_ORDER[0]], "#C7CDD6", GROUP_COLORS[GROUP_ORDER[1]]]
    for body, color in zip(violin["bodies"], colors, strict=True):
        body.set_facecolor(color); body.set_edgecolor("none"); body.set_alpha(0.62)
    for position, values in zip(positions, transformed, strict=True):
        q25, median, q75 = np.quantile(values, [0.25, 0.5, 0.75])
        ax.plot([position, position], [q25, q75], color="#20242A", lw=2)
        ax.scatter(position, median, color="white", edgecolor="#20242A", s=22, zorder=3)
    tick_rates = np.array([0, 0.1, 0.3, 1, 3, 10, 30, 100])
    ax.set_yticks(_rate_transform(tick_rates), [f"{value:g}" for value in tick_rates])
    ax.set_xticks(positions, ["Pre", "Peak", "Pre", "Peak"])
    ax.text(0.5, 0.98, "D2", transform=ax.get_xaxis_transform(), ha="center", va="top", color=GROUP_COLORS[GROUP_ORDER[0]], fontweight="bold")
    ax.text(3.5, 0.98, "Other wells", transform=ax.get_xaxis_transform(), ha="center", va="top", color=GROUP_COLORS[GROUP_ORDER[1]], fontweight="bold")
    ax.set_ylabel("Rate (Hz; log display)")
    ax.set_title("E  Pre and peak-post rates", loc="left", fontweight="bold")


def _plot_rate_scatter(ax, units, group):
    subset = units.loc[units["comparison_group"].eq(group)]
    x = _rate_transform(subset["pre_rate_hz"])
    y = _rate_transform(subset["peak_post_rate_hz"])
    ax.scatter(x, y, s=12, alpha=0.45, color=GROUP_COLORS[group], edgecolor="none")
    limits = [min(x.min(), y.min()) - 0.05, max(x.max(), y.max()) + 0.05]
    ax.plot(limits, limits, color="#6B7280", ls="--", lw=0.8)
    ax.set_xlim(limits); ax.set_ylim(limits); ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Pre: log10(Hz + 0.1)")
    ax.set_ylabel("Peak: log10(Hz + 0.1)")
    panel = "F" if group == GROUP_ORDER[0] else "G"
    ax.set_title(f"{panel}  {GROUP_LABELS[group].replace(chr(10), ' ')}", loc="left", fontweight="bold")


def _plot_response_rates(ax, units):
    x = np.arange(2)
    width = 0.36
    for group, offset in [(GROUP_ORDER[0], -width / 2), (GROUP_ORDER[1], width / 2)]:
        subset = units.loc[units["comparison_group"].eq(group)]
        values = [
            100 * subset["pulse_response_category"].eq("early_only_p1_p2").mean(),
            100 * subset["combined_ge3_candidate"].mean(),
        ]
        bars = ax.bar(x + offset, values, width, color=GROUP_COLORS[group], label=GROUP_LABELS[group].replace("\n", " "))
        ax.bar_label(bars, labels=[f"{value:.1f}%" for value in values], fontsize=7)
    ax.set_xticks(x, ["Early-only\nunit", "Full-train\nunit"])
    ax.set_ylabel("Units meeting ≥3/50 rule (%)")
    ax.set_title("H  Unit-level response behavior", loc="left", fontweight="bold")
    ax.legend(frameon=False, fontsize=7)


def _style(plt):
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.2,
            "axes.titlesize": 9.4,
            "axes.labelsize": 8.2,
            "xtick.labelsize": 7.4,
            "ytick.labelsize": 7.4,
            "axes.linewidth": 0.7,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
