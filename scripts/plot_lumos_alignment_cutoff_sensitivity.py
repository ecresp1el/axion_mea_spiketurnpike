#!/usr/bin/env python
"""Plot Lumos TTP cutoff sensitivity before and after waveform alignment."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_DATE_LABEL = "20260709"
CLASS_ORDER = ["FS_like", "RS_like", "unknown"]
CLASS_COLORS = {"FS_like": "#d55e00", "RS_like": "#0072b2", "unknown": "#bbbbbb"}
STAGE_SPECS = {
    "unaligned": {
        "label": "before alignment",
        "prefix": "before",
        "waveform_column": "before_unaligned_average_uV",
    },
    "aligned": {
        "label": "after alignment",
        "prefix": "after",
        "waveform_column": "after_aligned_average_uV",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--audit-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--cutoffs-ms", type=float, nargs="+", default=[0.37, 0.50])
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    job_dir = args.job_dir.expanduser().resolve()
    audit_dir = (
        args.audit_dir.expanduser().resolve()
        if args.audit_dir is not None
        else job_dir / f"waveform_alignment_feature_audit_{args.date_label}"
    )
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else job_dir / f"lumos_alignment_cutoff_sensitivity_{args.date_label}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    paired_csv = audit_dir / f"waveform_alignment_feature_audit_{args.date_label}_paired_unit_metrics.csv"
    traces_csv = audit_dir / f"waveform_alignment_feature_audit_{args.date_label}_waveform_traces.csv.gz"
    paired = pd.read_csv(paired_csv)
    traces = pd.read_csv(traces_csv)
    if paired.empty:
        raise SystemExit(f"No paired units in {paired_csv}")
    if traces.empty:
        raise SystemExit(f"No waveform traces in {traces_csv}")

    classified_tables: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    figure_paths: dict[str, str] = {}
    for cutoff in args.cutoffs_ms:
        cutoff_label = _cutoff_label(cutoff)
        for stage, spec in STAGE_SPECS.items():
            table = _classified_table(paired, cutoff_ms=cutoff, stage=stage)
            classified_tables.append(table)
            summary_rows.extend(_summary_rows(table, cutoff_ms=cutoff, stage=stage))
            figure_path = output_dir / f"lumos_ttp_cutoff_{cutoff_label}_{stage}_multipanel.png"
            _plot_condition(plt, table, traces, figure_path, cutoff_ms=cutoff, stage=stage)
            figure_paths[f"{cutoff_label}_{stage}"] = str(figure_path)

            table_path = output_dir / f"lumos_ttp_cutoff_{cutoff_label}_{stage}_classified_units.csv"
            table.to_csv(table_path, index=False)

    combined = pd.concat(classified_tables, ignore_index=True)
    summary = pd.DataFrame(summary_rows)
    combined_csv = output_dir / f"lumos_alignment_cutoff_sensitivity_{args.date_label}_classified_units_long.csv"
    summary_csv = output_dir / f"lumos_alignment_cutoff_sensitivity_{args.date_label}_summary.csv"
    provenance_json = output_dir / f"lumos_alignment_cutoff_sensitivity_{args.date_label}_provenance.json"
    combined.to_csv(combined_csv, index=False)
    summary.to_csv(summary_csv, index=False)
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "paired_unit_metrics_csv": str(paired_csv),
        "waveform_traces_csv": str(traces_csv),
        "output_dir": str(output_dir),
        "unit_count": int(len(paired)),
        "cutoffs_ms": [float(v) for v in args.cutoffs_ms],
        "stages": list(STAGE_SPECS),
        "outputs": {
            "classified_units_long_csv": str(combined_csv),
            "summary_csv": str(summary_csv),
            "figures": figure_paths,
        },
        "notes": [
            "Each PNG is one cutoff/alignment condition.",
            "All four outputs use the exact same 276 paired Lumos KSLabel=good units.",
            "Unaligned panels use before_* metrics and before_unaligned_average_uV traces.",
            "Aligned panels use after_* metrics and after_aligned_average_uV traces.",
            "Classification rule is FS_like if TTP <= cutoff, RS_like otherwise; unknown if TTP is missing.",
        ],
    }
    provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Input paired units: {paired_csv}")
    print(f"Input waveform traces: {traces_csv}")
    print(f"Output dir: {output_dir}")
    print(f"Combined classified units: {combined_csv}")
    print(f"Summary: {summary_csv}")
    print(f"Provenance: {provenance_json}")
    print("\nFour multi-panel outputs:")
    for key, value in figure_paths.items():
        print(f"{key}: {value}")
    print("\nSummary:")
    print(summary.to_string(index=False))


def _classified_table(paired: pd.DataFrame, *, cutoff_ms: float, stage: str) -> pd.DataFrame:
    spec = STAGE_SPECS[stage]
    prefix = spec["prefix"]
    out = paired[
        [
            "unit_key",
            "recording",
            "well",
            "plate_family",
            "unit_id",
            "unit_index",
            "KSLabel",
            "best_channel_index",
            "usable_snippets",
            "alignment_shift_median_samples",
            "alignment_shift_mad_samples",
            "alignment_shift_min_samples",
            "alignment_shift_max_samples",
        ]
    ].copy()
    out["stage"] = stage
    out["stage_label"] = spec["label"]
    out["ttp_cutoff_ms"] = float(cutoff_ms)
    metric_map = {
        "trough_to_peak_duration_ms": "trough_to_peak_duration_ms",
        "spike_half_width_ms": "spike_half_width_ms",
        "repolarization_time_ms": "repolarization_time_ms",
        "template_ptp_best_channel_uV": "template_ptp_best_channel_uV",
        "spiketurnpike_amplitude_uV": "spiketurnpike_amplitude_uV",
        "pre_peak_amplitude_uV": "pre_peak_amplitude_uV",
        "post_peak_amplitude_uV": "post_peak_amplitude_uV",
        "depolarization_slope_uV_per_ms": "depolarization_slope_uV_per_ms",
        "post_trough_rebound_slope_uV_per_ms": "post_trough_rebound_slope_uV_per_ms",
        "rep50_recovery_slope_uV_per_ms": "rep50_recovery_slope_uV_per_ms",
        "waveform_asymmetry": "waveform_asymmetry",
        "peak_to_peak_ratio": "peak_to_peak_ratio",
    }
    for output_name, metric_name in metric_map.items():
        out[output_name] = pd.to_numeric(paired[f"{prefix}_{metric_name}"], errors="coerce")
    ttp = out["trough_to_peak_duration_ms"]
    out["ttp_cutoff_classification"] = np.where(ttp.le(cutoff_ms), "FS_like", "RS_like")
    out.loc[ttp.isna(), "ttp_cutoff_classification"] = "unknown"
    return out


def _summary_rows(table: pd.DataFrame, *, cutoff_ms: float, stage: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    counts = table["ttp_cutoff_classification"].value_counts(dropna=False)
    for label in CLASS_ORDER:
        subset = table.loc[table["ttp_cutoff_classification"].eq(label)]
        rows.append(
            {
                "cutoff_ms": float(cutoff_ms),
                "stage": stage,
                "class": label,
                "unit_count": int(counts.get(label, 0)),
                "unit_fraction": float(counts.get(label, 0) / len(table)) if len(table) else np.nan,
                "median_ttp_ms": _median(subset["trough_to_peak_duration_ms"]),
                "median_half_width_ms": _median(subset["spike_half_width_ms"]),
                "median_rep50_ms": _median(subset["repolarization_time_ms"]),
                "median_amplitude_uV": _median(subset["spiketurnpike_amplitude_uV"]),
            }
        )
    return rows


def _plot_condition(plt, table: pd.DataFrame, traces: pd.DataFrame, output_path: Path, *, cutoff_ms: float, stage: str) -> None:
    spec = STAGE_SPECS[stage]
    waveform_col = spec["waveform_column"]
    classified_traces = traces.merge(
        table[["unit_key", "ttp_cutoff_classification"]],
        on="unit_key",
        how="inner",
    )
    fig, axes = plt.subplots(2, 3, figsize=(16.8, 9.4))
    axes = axes.ravel()

    _plot_ttp_histogram(axes[0], table, cutoff_ms)
    _plot_class_counts(axes[1], table, cutoff_ms)
    _plot_pooled_waveforms(axes[2], classified_traces, waveform_col)
    _plot_metric_by_class(axes[3], table, "spike_half_width_ms", "Half-width (ms)")
    _plot_metric_by_class(axes[4], table, "repolarization_time_ms", "REP50 (ms)")
    _plot_metric_by_class(axes[5], table, "spiketurnpike_amplitude_uV", "Amplitude (uV)")

    for ax in axes:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.suptitle(
        f"Lumos KSLabel=good TTP cutoff sensitivity: {spec['label']}, FS <= {cutoff_ms:.2f} ms\n"
        f"Same paired units and snippets; n={len(table)}",
        y=1.01,
        fontsize=13,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_ttp_histogram(ax, table: pd.DataFrame, cutoff_ms: float) -> None:
    ttp = pd.to_numeric(table["trough_to_peak_duration_ms"], errors="coerce").dropna()
    if ttp.empty:
        ax.text(0.5, 0.5, "No TTP values", ha="center", va="center", transform=ax.transAxes)
        return
    bins = np.arange(0.0, max(float(ttp.max()) + 0.16, cutoff_ms + 0.24), 0.08)
    for label in ["FS_like", "RS_like", "unknown"]:
        values = pd.to_numeric(
            table.loc[table["ttp_cutoff_classification"].eq(label), "trough_to_peak_duration_ms"],
            errors="coerce",
        ).dropna()
        if values.empty:
            continue
        ax.hist(values, bins=bins, color=CLASS_COLORS[label], alpha=0.72, label=f"{label} n={len(values)}")
    ax.axvline(cutoff_ms, color="black", linestyle="--", linewidth=1.2, label=f"cutoff {cutoff_ms:.2f} ms")
    ax.set_xlabel("Trough-to-peak duration (ms)")
    ax.set_ylabel("Units")
    ax.set_title("TTP distribution")
    ax.legend(frameon=False, fontsize=8)


def _plot_class_counts(ax, table: pd.DataFrame, cutoff_ms: float) -> None:
    counts = table["ttp_cutoff_classification"].value_counts()
    values = [int(counts.get(label, 0)) for label in CLASS_ORDER]
    x = np.arange(len(CLASS_ORDER))
    ax.bar(x, values, color=[CLASS_COLORS[label] for label in CLASS_ORDER])
    for xi, value in zip(x, values, strict=False):
        ax.text(xi, value + max(values + [1]) * 0.02, str(value), ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x, [label.replace("_", "\n") for label in CLASS_ORDER])
    ax.set_ylabel("Units")
    ax.set_title(f"Class counts, FS <= {cutoff_ms:.2f} ms")
    ax.set_ylim(0, max(values + [1]) * 1.18)


def _plot_pooled_waveforms(ax, traces: pd.DataFrame, waveform_col: str) -> None:
    if traces.empty:
        ax.text(0.5, 0.5, "No waveform traces", ha="center", va="center", transform=ax.transAxes)
        return
    y_bounds: list[float] = []
    for label in ["FS_like", "RS_like"]:
        subset = traces.loc[traces["ttp_cutoff_classification"].eq(label)].copy()
        if subset.empty:
            continue
        for _, unit_trace in subset.groupby("unit_key", sort=False):
            ax.plot(
                unit_trace["time_ms"],
                unit_trace[waveform_col],
                color=CLASS_COLORS[label],
                alpha=0.045,
                linewidth=0.65,
            )
        summary = (
            subset.groupby("time_ms", as_index=False)
            .agg(
                mean_waveform=(waveform_col, "mean"),
                sem_waveform=(waveform_col, _sem),
            )
            .sort_values("time_ms")
        )
        time = summary["time_ms"].to_numpy(dtype=float)
        mean = summary["mean_waveform"].to_numpy(dtype=float)
        sem = summary["sem_waveform"].fillna(0.0).to_numpy(dtype=float)
        y_bounds.extend([float(np.nanmin(mean - sem)), float(np.nanmax(mean + sem))])
        ax.fill_between(time, mean - sem, mean + sem, color=CLASS_COLORS[label], alpha=0.20, linewidth=0)
        ax.plot(time, mean, color=CLASS_COLORS[label], linewidth=2.25, label=f"{label} n={subset['unit_key'].nunique()}")
    ax.axvline(0, color="0.35", linestyle="--", linewidth=0.9)
    ax.axhline(0, color="0.86", linewidth=0.8)
    ax.set_xlabel("Time from expected spike center (ms)")
    ax.set_ylabel("Best-channel waveform (uV)")
    ax.set_title("Pooled waveforms")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(color="0.92")
    if y_bounds:
        y_min = min(y_bounds)
        y_max = max(y_bounds)
        margin = max((y_max - y_min) * 0.18, 0.35)
        ax.set_ylim(y_min - margin, y_max + margin)


def _plot_metric_by_class(ax, table: pd.DataFrame, metric: str, label: str) -> None:
    ymax = _max(table[metric])
    for index, class_label in enumerate(["FS_like", "RS_like"]):
        values = pd.to_numeric(table.loc[table["ttp_cutoff_classification"].eq(class_label), metric], errors="coerce").dropna()
        if values.empty:
            continue
        jitter = _deterministic_jitter(len(values), width=0.12)
        ax.scatter(
            np.full(len(values), index) + jitter,
            values,
            s=22,
            alpha=0.68,
            color=CLASS_COLORS[class_label],
            edgecolor="none",
        )
        median = float(values.median())
        ax.hlines(median, index - 0.24, index + 0.24, color="black", linewidth=2)
        ax.text(index, float(values.max()), f"n={len(values)}\nmed {median:.3g}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks([0, 1], ["FS_like", "RS_like"])
    ax.set_ylabel(label)
    ax.set_title(label + " by class")
    if np.isfinite(ymax):
        ax.set_ylim(bottom=min(0.0, float(pd.to_numeric(table[metric], errors="coerce").min()) * 1.08), top=ymax * 1.16 + 1e-9)
    ax.grid(axis="y", color="0.9")


def _cutoff_label(value: float) -> str:
    return f"{value:.2f}".replace(".", "p")


def _deterministic_jitter(n: int, width: float) -> np.ndarray:
    if n <= 1:
        return np.zeros(n)
    return np.linspace(-width, width, n)


def _median(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return float(clean.median()) if not clean.empty else np.nan


def _max(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return float(clean.max()) if not clean.empty else np.nan


def _sem(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if clean.size <= 1:
        return np.nan
    return float(np.nanstd(clean, ddof=1) / np.sqrt(clean.size))


if __name__ == "__main__":
    main()
