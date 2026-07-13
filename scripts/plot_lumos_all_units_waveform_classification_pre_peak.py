#!/usr/bin/env python
"""Unify all-unit waveform classes with pre and peak train firing rates."""

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
from scripts.build_lumos_all_units_unified_psth_store import (  # noqa: E402
    DEFAULT_JOB_DIR,
    OUTPUT_NAME as UNIT_PSTH_OUTPUT_NAME,
)
from scripts.plot_lumos_opsin_pre_post_unit_firing_rates import (  # noqa: E402
    _match_unit_id,
    _unit_label,
)


OUTPUT_NAME = "lumos_all_units_waveform_classification_pre_peak_development"
UNIT_METADATA_NAME = "unit_metadata.csv"
UNIT_RESPONSE_DIR = "lumos_per_unit_threshold_response_development"
UNIT_RESPONSE_NAME = "per_unit_threshold_response_metrics.csv"
CLASS_ORDER = ["FS_like", "borderline", "RS_like"]
CLASS_LABELS = {"FS_like": "FS-like", "borderline": "Borderline", "RS_like": "RS-like"}
CLASS_COLORS = {"FS_like": "#3465A4", "borderline": "#9A7B4F", "RS_like": "#C44E52"}
CONDITION_ORDER = ["opsin", "no_opsin"]
CONDITION_LABELS = {"opsin": "+ opsin", "no_opsin": "− opsin"}
CONDITION_COLORS = {"opsin": "#E45756", "no_opsin": "#4C78A8"}
COMMON_TIME_MS = np.arange(-0.8, 1.6001, 0.04)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--unit-psth-dir",
        type=Path,
        default=DEFAULT_JOB_DIR / UNIT_PSTH_OUTPUT_NAME,
    )
    parser.add_argument(
        "--unit-response-csv",
        type=Path,
        default=DEFAULT_JOB_DIR / UNIT_RESPONSE_DIR / UNIT_RESPONSE_NAME,
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

    output_dir = args.output_dir.expanduser().resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    unit_metadata = pd.read_csv(
        args.unit_psth_dir.expanduser().resolve() / UNIT_METADATA_NAME
    )
    train_metrics = pd.read_csv(args.unit_response_csv.expanduser().resolve())
    train_metrics = train_metrics.loc[train_metrics["target"].eq("train_250ms")].copy()
    _validate_inputs(unit_metadata, train_metrics)
    rate_columns = [
        "unit_observation_id",
        "spontaneous_rate_hz",
        "subtraction_baseline_rate_hz",
        "peak_mean_excess_hz",
        "peak_latency_ms",
        "positive_going_psth_sum_spikes_per_trial",
        "maximum_trials_above_baseline_same_bin",
    ]
    units = unit_metadata.merge(
        train_metrics[rate_columns], on="unit_observation_id", how="left", validate="one_to_one"
    )
    units = units.rename(columns={"subtraction_baseline_rate_hz": "pre_rate_hz"})
    units["peak_post_rate_hz"] = units["pre_rate_hz"] + units["peak_mean_excess_hz"]
    units["peak_minus_pre_hz"] = units["peak_mean_excess_hz"]
    units["waveform_extraction_status"] = "not_attempted"

    trace_rows: list[dict[str, object]] = []
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
            sampling_frequency = float(analyzer.recording.get_sampling_frequency())
            unit_index_by_label = {
                _unit_label(unit_id): index for index, unit_id in enumerate(unit_ids)
            }
            for row_index, row in group.iterrows():
                try:
                    matched_id = _match_unit_id(unit_ids, row["unit_id"])
                    unit_index = unit_index_by_label[_unit_label(matched_id)]
                    channel_index = int(row["best_channel_index"])
                    waveform = np.asarray(
                        templates[unit_index, :, channel_index], dtype=float
                    )
                    aligned = _aligned_normalized_waveform(
                        waveform, sampling_frequency, COMMON_TIME_MS
                    )
                    if not np.isfinite(aligned).any():
                        raise ValueError("aligned waveform contains no finite values")
                    units.loc[row_index, "waveform_extraction_status"] = "available"
                    units.loc[row_index, "waveform_native_samples"] = len(waveform)
                    units.loc[row_index, "waveform_sampling_frequency_hz"] = sampling_frequency
                    for time_ms, value in zip(COMMON_TIME_MS, aligned, strict=True):
                        trace_rows.append(
                            {
                                "unit_observation_id": row["unit_observation_id"],
                                "condition": row["condition"],
                                "waveform_class": row["waveform_class"],
                                "aligned_time_ms": time_ms,
                                "normalized_waveform": value,
                            }
                        )
                except Exception as exc:  # noqa: BLE001
                    units.loc[row_index, "waveform_extraction_status"] = "error"
                    error_rows.append(
                        {
                            "unit_observation_id": row["unit_observation_id"],
                            "analyzer_path": str(analyzer_path),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            units.loc[group.index, "waveform_extraction_status"] = "analyzer_error"
            for row in group.itertuples(index=False):
                error_rows.append(
                    {
                        "unit_observation_id": row.unit_observation_id,
                        "analyzer_path": str(analyzer_path),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
        if progress % 10 == 0 or progress == units["analyzer_path"].nunique():
            print(
                f"[{progress:03d}/{units['analyzer_path'].nunique():03d}] analyzers",
                flush=True,
            )

    traces = pd.DataFrame(trace_rows)
    waveform_summary = _waveform_summary(traces)
    classification_summary = _classification_summary(units)
    rate_summary = _rate_summary(units)
    units.to_csv(staging_dir / "all_unit_waveform_pre_peak_metrics.csv", index=False)
    traces.to_csv(staging_dir / "all_unit_normalized_waveform_traces.csv", index=False)
    waveform_summary.to_csv(staging_dir / "mean_waveform_summary.csv", index=False)
    classification_summary.to_csv(
        staging_dir / "waveform_classification_summary.csv", index=False
    )
    rate_summary.to_csv(staging_dir / "pre_peak_rate_summary.csv", index=False)
    pd.DataFrame(
        error_rows, columns=["unit_observation_id", "analyzer_path", "error"]
    ).to_csv(staging_dir / "waveform_extraction_errors.csv", index=False)

    _style(plt)
    figure = _plot_overview(
        plt, units, waveform_summary, classification_summary, rate_summary
    )
    figure.savefig(
        staging_dir / "all_units_waveform_classification_pre_peak.png",
        dpi=400,
        bbox_inches="tight",
        facecolor="white",
    )
    figure.savefig(
        staging_dir / "all_units_waveform_classification_pre_peak.pdf",
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(figure)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "development_output": True,
        "overwrite_policy": "entire output directory replaced after successful run",
        "unit_observations": int(len(units)),
        "conditions": units["condition"].value_counts().to_dict(),
        "KSLabel": units["KSLabel"].value_counts().to_dict(),
        "waveform_classification": (
            "existing waveform_class from unified unit metadata; FS_like, borderline, RS_like"
        ),
        "waveform_display": (
            "best-channel templates.average; baseline-centered, aligned to trough, "
            "normalized by trough magnitude; group mean plus SEM"
        ),
        "unit_waveform_trace_table": "all_unit_normalized_waveform_traces.csv",
        "pre_rate_hz": "mean raw firing rate from -200 to 0 ms before pulse 1",
        "peak_post_rate_hz": (
            "maximum of the once-[1,1,1]/3-smoothed trial-mean PSTH during "
            "the continuous 0-250 ms train; pre_rate_hz + peak_mean_excess_hz"
        ),
        "trials": 50,
        "silent_trials": "retained",
        "aggregation": "one unit observation per recording/raw variant; no deduplication",
        "source_unit_metadata": str(
            args.unit_psth_dir.expanduser().resolve() / UNIT_METADATA_NAME
        ),
        "source_response_metrics": str(args.unit_response_csv.expanduser().resolve()),
    }
    (staging_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging_dir.replace(output_dir)
    print(f"\nOutput: {output_dir}")
    print(f"Unit observations: {len(units)}")
    print(
        "Waveforms: "
        f"{units['waveform_extraction_status'].value_counts(dropna=False).to_dict()}"
    )
    return 0


def _validate_inputs(unit_metadata: pd.DataFrame, train_metrics: pd.DataFrame) -> None:
    if unit_metadata["unit_observation_id"].duplicated().any():
        raise ValueError("unit metadata contains duplicate observation IDs")
    if train_metrics["unit_observation_id"].duplicated().any():
        raise ValueError("train metrics contain duplicate observation IDs")
    missing = set(unit_metadata["unit_observation_id"]) - set(
        train_metrics["unit_observation_id"]
    )
    if missing:
        raise ValueError(f"missing train metrics for {len(missing)} unit observations")


def _aligned_normalized_waveform(
    waveform: np.ndarray, sampling_frequency: float, common_time_ms: np.ndarray
) -> np.ndarray:
    if waveform.ndim != 1 or len(waveform) < 5 or not np.isfinite(waveform).any():
        raise ValueError("invalid best-channel waveform")
    baseline_samples = min(5, max(1, len(waveform) // 5))
    centered = waveform - float(np.nanmedian(waveform[:baseline_samples]))
    trough_index = int(np.nanargmin(centered))
    trough_magnitude = abs(float(centered[trough_index]))
    if not np.isfinite(trough_magnitude) or trough_magnitude <= 0:
        raise ValueError("waveform has zero trough magnitude")
    normalized = centered / trough_magnitude
    native_time_ms = (
        np.arange(len(normalized), dtype=float) - trough_index
    ) / sampling_frequency * 1000.0
    return np.interp(
        common_time_ms,
        native_time_ms,
        normalized,
        left=np.nan,
        right=np.nan,
    )


def _waveform_summary(traces: pd.DataFrame) -> pd.DataFrame:
    if traces.empty:
        return pd.DataFrame()
    return (
        traces.groupby(
            ["condition", "waveform_class", "aligned_time_ms"], dropna=False
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


def _classification_summary(units: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for condition in CONDITION_ORDER:
        subset = units.loc[units["condition"].eq(condition)]
        for class_label in CLASS_ORDER:
            class_subset = subset.loc[subset["waveform_class"].eq(class_label)]
            rows.append(
                {
                    "condition": condition,
                    "waveform_class": class_label,
                    "unit_observations": len(class_subset),
                    "condition_fraction": len(class_subset) / len(subset),
                    "good_units": int(class_subset["KSLabel"].eq("good").sum()),
                    "mua_units": int(class_subset["KSLabel"].eq("mua").sum()),
                }
            )
    return pd.DataFrame(rows)


def _rate_summary(units: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for condition in CONDITION_ORDER:
        for class_label in CLASS_ORDER:
            subset = units.loc[
                units["condition"].eq(condition)
                & units["waveform_class"].eq(class_label)
            ]
            for metric in ["pre_rate_hz", "peak_post_rate_hz", "peak_minus_pre_hz"]:
                values = subset[metric].dropna().to_numpy(float)
                rows.append(
                    {
                        "condition": condition,
                        "waveform_class": class_label,
                        "metric": metric,
                        "unit_observations": len(values),
                        "median_hz": float(np.median(values)),
                        "q25_hz": float(np.quantile(values, 0.25)),
                        "q75_hz": float(np.quantile(values, 0.75)),
                        "mean_hz": float(np.mean(values)),
                    }
                )
    return pd.DataFrame(rows)


def _plot_overview(plt, units, waveform_summary, classification_summary, rate_summary):
    figure, axes = plt.subplots(2, 3, figsize=(16, 9.4))
    _plot_classification(axes[0, 0], classification_summary)
    _plot_mean_waveforms(axes[0, 1], waveform_summary, "opsin")
    _plot_mean_waveforms(axes[0, 2], waveform_summary, "no_opsin")
    transformed_limits = _rate_transform_limits(units)
    _plot_rate_scatter(axes[1, 0], units, "opsin", transformed_limits)
    _plot_rate_scatter(axes[1, 1], units, "no_opsin", transformed_limits)
    _plot_rate_distributions(axes[1, 2], units)
    figure.suptitle(
        "All Lumos unit observations: waveform class and optical-train firing rate",
        x=0.02,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    figure.text(
        0.02,
        0.955,
        "All 689 good + MUA observations; every non-LFP raw variant retained. "
        "Pre = −200–0 ms before P1; peak post = maximum once-smoothed mean PSTH in 0–250 ms.",
        ha="left",
        fontsize=8.5,
        color="#4B5563",
    )
    figure.subplots_adjust(
        left=0.055,
        right=0.985,
        bottom=0.07,
        top=0.875,
        wspace=0.24,
        hspace=0.24,
    )
    return figure


def _plot_classification(ax, summary):
    bottoms = np.zeros(2)
    for class_label in CLASS_ORDER:
        subset = summary.loc[summary["waveform_class"].eq(class_label)].set_index(
            "condition"
        )
        values = np.array(
            [subset.loc[condition, "condition_fraction"] for condition in CONDITION_ORDER]
        )
        counts = np.array(
            [subset.loc[condition, "unit_observations"] for condition in CONDITION_ORDER]
        )
        ax.bar(
            range(2),
            values * 100,
            bottom=bottoms * 100,
            color=CLASS_COLORS[class_label],
            label=CLASS_LABELS[class_label],
            width=0.62,
        )
        for index, (value, count) in enumerate(zip(values, counts, strict=True)):
            if value > 0.06:
                ax.text(
                    index,
                    (bottoms[index] + value / 2) * 100,
                    f"{count}\n{value * 100:.1f}%",
                    ha="center",
                    va="center",
                    color="white",
                    fontsize=8,
                    fontweight="bold",
                )
        bottoms += values
    totals = summary.groupby("condition")["unit_observations"].sum()
    ax.set_xticks(range(2), [f"+ opsin\nn={totals['opsin']}", f"− opsin\nn={totals['no_opsin']}"])
    ax.set_ylim(0, 106)
    ax.set_ylabel("Units within condition (%)")
    ax.set_title("A  Existing waveform classification", loc="left", fontweight="bold")
    ax.legend(
        frameon=True,
        framealpha=0.88,
        facecolor="white",
        edgecolor="none",
        fontsize=8,
        loc="upper left",
    )


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
    ax.set_xlim(COMMON_TIME_MS[0], COMMON_TIME_MS[-1])
    ax.set_xlabel("Time from trough (ms)")
    ax.set_ylabel("Normalized template amplitude")
    panel = "B" if condition == "opsin" else "C"
    ax.set_title(
        f"{panel}  {CONDITION_LABELS[condition]} mean waveforms",
        loc="left",
        fontweight="bold",
    )
    ax.legend(frameon=False, fontsize=7.5)


def _rate_transform(values):
    return np.log10(np.asarray(values, dtype=float) + 0.1)


def _rate_transform_limits(units):
    all_values = np.concatenate(
        [units["pre_rate_hz"].to_numpy(float), units["peak_post_rate_hz"].to_numpy(float)]
    )
    transformed = _rate_transform(all_values[np.isfinite(all_values)])
    return float(transformed.min() - 0.08), float(transformed.max() + 0.08)


def _plot_rate_scatter(ax, units, condition, limits):
    subset = units.loc[units["condition"].eq(condition)]
    for class_label in CLASS_ORDER:
        class_subset = subset.loc[subset["waveform_class"].eq(class_label)]
        ax.scatter(
            _rate_transform(class_subset["pre_rate_hz"]),
            _rate_transform(class_subset["peak_post_rate_hz"]),
            s=13,
            alpha=0.48,
            color=CLASS_COLORS[class_label],
            edgecolor="none",
            label=f"{CLASS_LABELS[class_label]} n={len(class_subset)}",
        )
    ax.plot(limits, limits, color="#6B7280", lw=0.9, ls="--")
    ax.set_xlim(limits)
    ax.set_ylim(limits)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Pre rate: log10(Hz + 0.1)")
    ax.set_ylabel("Peak post rate: log10(Hz + 0.1)")
    panel = "D" if condition == "opsin" else "E"
    ax.set_title(
        f"{panel}  Every {CONDITION_LABELS[condition]} unit",
        loc="left",
        fontweight="bold",
    )
    ax.legend(frameon=False, fontsize=7, loc="lower right")


def _plot_rate_distributions(ax, units):
    positions = [0, 1, 3, 4]
    groups = [
        units.loc[units["condition"].eq("opsin"), "pre_rate_hz"],
        units.loc[units["condition"].eq("opsin"), "peak_post_rate_hz"],
        units.loc[units["condition"].eq("no_opsin"), "pre_rate_hz"],
        units.loc[units["condition"].eq("no_opsin"), "peak_post_rate_hz"],
    ]
    transformed = [_rate_transform(group.dropna()) for group in groups]
    violins = ax.violinplot(
        transformed,
        positions=positions,
        widths=0.78,
        showmeans=False,
        showmedians=False,
        showextrema=False,
    )
    colors = ["#AAB2BD", CONDITION_COLORS["opsin"], "#AAB2BD", CONDITION_COLORS["no_opsin"]]
    for body, color in zip(violins["bodies"], colors, strict=True):
        body.set_facecolor(color)
        body.set_edgecolor("none")
        body.set_alpha(0.62)
    for position, values, color in zip(positions, transformed, colors, strict=True):
        q25, median, q75 = np.quantile(values, [0.25, 0.5, 0.75])
        ax.plot([position, position], [q25, q75], color="#20242A", lw=2.2)
        ax.scatter(position, median, s=25, color="white", edgecolor="#20242A", zorder=3)
    for first, second in [(0, 1), (3, 4)]:
        medians = [np.median(transformed[positions.index(first)]), np.median(transformed[positions.index(second)])]
        ax.plot([first, second], medians, color="#374151", lw=0.9, alpha=0.8)
    tick_rates = np.array([0, 0.1, 0.3, 1, 3, 10, 30, 100], dtype=float)
    ax.set_yticks(_rate_transform(tick_rates), [f"{value:g}" for value in tick_rates])
    ax.set_xticks(positions, ["Pre", "Peak", "Pre", "Peak"])
    ax.text(0.5, 0.965, "+ opsin", transform=ax.get_xaxis_transform(), ha="center", va="top", color=CONDITION_COLORS["opsin"], fontweight="bold")
    ax.text(3.5, 0.965, "− opsin", transform=ax.get_xaxis_transform(), ha="center", va="top", color=CONDITION_COLORS["no_opsin"], fontweight="bold")
    ax.set_ylabel("Firing rate (Hz; log display)")
    ax.set_title("F  Pre and peak-post distributions", loc="left", fontweight="bold")


def _style(plt) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "axes.titlesize": 10,
            "axes.labelsize": 8.5,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.linewidth": 0.7,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
