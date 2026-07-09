#!/usr/bin/env python
"""One-page Lumos geometry cutoff x alignment comparison figure."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_DATE_LABEL = "20260709"
STAGE_SPECS = {
    "unaligned": {"prefix": "before", "label": "unaligned", "waveform_column": "before_unaligned_average_uV"},
    "aligned": {"prefix": "after", "label": "aligned", "waveform_column": "after_aligned_average_uV"},
}
GEOMETRY_ORDER = ["columns_1_3_compare", "columns_4_8_prior"]
GEOMETRY_LABELS = {
    "columns_1_3_compare": "cols 1-3",
    "columns_4_8_prior": "cols 4-8",
}
GEOMETRY_COLORS = {"columns_1_3_compare": "#7a7a7a", "columns_4_8_prior": "#2a9d8f"}
CLASS_ORDER = ["FS_like", "RS_like"]
CLASS_COLORS = {"FS_like": "#d55e00", "RS_like": "#0072b2"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--cutoffs-ms", type=float, nargs="+", default=[0.37, 0.50])
    parser.add_argument("--audit-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
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
        else job_dir / f"lumos_geometry_alignment_cutoff_composite_{args.date_label}"
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

    paired["well_column"] = paired["well"].map(_well_column)
    paired["geometry_group"] = paired["well_column"].map(_geometry_group)
    paired = paired.loc[paired["geometry_group"].isin(GEOMETRY_ORDER)].copy()
    if paired.empty:
        raise SystemExit("No Lumos paired units mapped to columns 1-3 or 4-8 geometry groups.")

    classified_tables: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    conditions: list[tuple[float, str]] = []
    for cutoff in args.cutoffs_ms:
        for stage in ["unaligned", "aligned"]:
            table = _classified_table(paired, cutoff_ms=cutoff, stage=stage)
            classified_tables.append(table)
            summary_rows.extend(_summary_rows(table, cutoff_ms=cutoff, stage=stage))
            conditions.append((cutoff, stage))

    classified = pd.concat(classified_tables, ignore_index=True)
    summary = pd.DataFrame(summary_rows)
    figure_path = output_dir / f"lumos_geometry_alignment_cutoff_composite_{args.date_label}.png"
    classified_csv = output_dir / f"lumos_geometry_alignment_cutoff_composite_{args.date_label}_classified_units_long.csv"
    summary_csv = output_dir / f"lumos_geometry_alignment_cutoff_composite_{args.date_label}_summary.csv"
    provenance_json = output_dir / f"lumos_geometry_alignment_cutoff_composite_{args.date_label}_provenance.json"
    classified.to_csv(classified_csv, index=False)
    summary.to_csv(summary_csv, index=False)
    _plot_composite(plt, classified, traces, figure_path, conditions)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "paired_unit_metrics_csv": str(paired_csv),
        "waveform_traces_csv": str(traces_csv),
        "output_dir": str(output_dir),
        "paired_geometry_unit_count": int(len(paired)),
        "cutoffs_ms": [float(v) for v in args.cutoffs_ms],
        "conditions": [{"cutoff_ms": float(c), "stage": s} for c, s in conditions],
        "geometry_definition": {
            "columns_1_3_compare": "well column 1 through 3",
            "columns_4_8_prior": "well column 4 through 8",
        },
        "outputs": {
            "figure_png": str(figure_path),
            "classified_units_long_csv": str(classified_csv),
            "summary_csv": str(summary_csv),
        },
        "notes": [
            "This is the Lumos geometry counterpart to the Cytoview dorsal/ventral composite.",
            "Rows are cutoff x alignment conditions.",
            "All rows use the same paired Lumos KSLabel=good units.",
            "Lumos recordings here are treated as ventral/opto-track; geometry groups are plate-column groups, not dorsal/ventral biology.",
            "Unaligned uses before_* audit metrics; aligned uses after_* audit metrics.",
        ],
    }
    provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Paired Lumos geometry units: {len(paired)}")
    print(f"Figure: {figure_path}")
    print(f"Classified units: {classified_csv}")
    print(f"Summary: {summary_csv}")
    print(f"Provenance: {provenance_json}")
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
            "well_column",
            "geometry_group",
            "plate_family",
            "unit_id",
            "unit_index",
            "KSLabel",
            "best_channel_index",
            "usable_snippets",
        ]
    ].copy()
    out["cutoff_ms"] = float(cutoff_ms)
    out["stage"] = stage
    out["condition_label"] = f"FS <= {cutoff_ms:.2f} ms, {spec['label']}"
    for metric in [
        "trough_to_peak_duration_ms",
        "spike_half_width_ms",
        "repolarization_time_ms",
        "spiketurnpike_amplitude_uV",
        "template_ptp_best_channel_uV",
        "rep50_recovery_slope_uV_per_ms",
    ]:
        out[metric] = pd.to_numeric(paired[f"{prefix}_{metric}"], errors="coerce")
    ttp = out["trough_to_peak_duration_ms"]
    out["ttp_cutoff_classification"] = np.where(ttp.le(cutoff_ms), "FS_like", "RS_like")
    out.loc[ttp.isna(), "ttp_cutoff_classification"] = "unknown"
    return out


def _summary_rows(table: pd.DataFrame, *, cutoff_ms: float, stage: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for scope, subset in [("overall", table)] + [
        (group, table.loc[table["geometry_group"].eq(group)]) for group in GEOMETRY_ORDER
    ]:
        for class_label in CLASS_ORDER:
            class_subset = subset.loc[subset["ttp_cutoff_classification"].eq(class_label)]
            rows.append(
                {
                    "cutoff_ms": float(cutoff_ms),
                    "stage": stage,
                    "scope": scope,
                    "class": class_label,
                    "unit_count": int(len(class_subset)),
                    "scope_unit_count": int(len(subset)),
                    "scope_fraction": float(len(class_subset) / len(subset)) if len(subset) else np.nan,
                    "median_ttp_ms": _median(class_subset["trough_to_peak_duration_ms"]),
                    "median_half_width_ms": _median(class_subset["spike_half_width_ms"]),
                    "median_rep50_ms": _median(class_subset["repolarization_time_ms"]),
                    "median_amplitude_uV": _median(class_subset["spiketurnpike_amplitude_uV"]),
                }
            )
    return rows


def _plot_composite(plt, classified: pd.DataFrame, traces: pd.DataFrame, output_path: Path, conditions: list[tuple[float, str]]) -> None:
    nrows = len(conditions)
    ncols = 8
    fig, axes = plt.subplots(nrows, ncols, figsize=(31, 4.7 * nrows), squeeze=False)
    column_titles = [
        "Overall FS/RS",
        "Geometry class fraction",
        "Geometry class counts",
        "TTP by geometry",
        "Pooled waveforms, uV",
        "Individual waveforms + mean, uV",
        "Pooled waveforms, normalized",
        "Half-width and REP50",
    ]
    for col, title in enumerate(column_titles):
        axes[0, col].set_title(title, fontsize=11)

    for row_index, (cutoff, stage) in enumerate(conditions):
        subset = classified.loc[
            classified["cutoff_ms"].eq(cutoff) & classified["stage"].eq(stage)
        ].copy()
        condition_label = f"FS <= {cutoff:.2f} ms\n{STAGE_SPECS[stage]['label']}"
        axes[row_index, 0].set_ylabel(condition_label, fontsize=11, fontweight="bold")
        _plot_overall_counts(axes[row_index, 0], subset)
        _plot_geometry_fraction(axes[row_index, 1], subset)
        _plot_geometry_counts(axes[row_index, 2], subset)
        _plot_ttp_by_geometry(axes[row_index, 3], subset, cutoff)
        _plot_waveforms(axes[row_index, 4], subset, traces, stage, normalize=False)
        _plot_individual_waveforms_with_mean(axes[row_index, 5], subset, traces, stage)
        _plot_waveforms(axes[row_index, 6], subset, traces, stage, normalize=True)
        _plot_halfwidth_rep(axes[row_index, 7], subset)

    for ax in axes.ravel():
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.suptitle(
        "Lumos KSLabel=good units: TTP cutoff x waveform alignment x well-column geometry\n"
        "Same paired units in every row; waveform math matches Cytoview alignment/cutoff workflow",
        y=1.005,
        fontsize=14,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_overall_counts(ax, table: pd.DataFrame) -> None:
    counts = table["ttp_cutoff_classification"].value_counts()
    values = [int(counts.get(label, 0)) for label in CLASS_ORDER]
    x = np.arange(len(CLASS_ORDER))
    ax.bar(x, values, color=[CLASS_COLORS[label] for label in CLASS_ORDER])
    for xi, value in zip(x, values, strict=False):
        ax.text(xi, value + max(values + [1]) * 0.03, str(value), ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x, CLASS_ORDER)
    ax.set_ylabel("Units")
    ax.grid(axis="y", color="0.9")


def _plot_geometry_fraction(ax, table: pd.DataFrame) -> None:
    x = np.arange(len(GEOMETRY_ORDER))
    bottom = np.zeros(len(GEOMETRY_ORDER))
    for class_label in CLASS_ORDER:
        values = []
        for group in GEOMETRY_ORDER:
            subset = table.loc[table["geometry_group"].eq(group)]
            value = subset["ttp_cutoff_classification"].eq(class_label).mean() if len(subset) else 0.0
            values.append(float(value))
        ax.bar(x, values, bottom=bottom, color=CLASS_COLORS[class_label], label=class_label)
        for xi, value, base in zip(x, values, bottom, strict=False):
            if value > 0:
                ax.text(xi, base + value / 2, f"{value:.0%}", ha="center", va="center", color="white", fontsize=8)
        bottom += np.asarray(values)
    ax.set_xticks(x, [GEOMETRY_LABELS[g] for g in GEOMETRY_ORDER])
    ax.set_ylim(0, 1)
    ax.grid(axis="y", color="0.9")
    if ax.get_subplotspec().rowspan.start == 0:
        ax.legend(frameon=False, fontsize=8, loc="upper right")


def _plot_geometry_counts(ax, table: pd.DataFrame) -> None:
    width = 0.36
    x = np.arange(len(GEOMETRY_ORDER))
    for offset, class_label in [(-width / 2, "FS_like"), (width / 2, "RS_like")]:
        values = [
            int(table.loc[table["geometry_group"].eq(group), "ttp_cutoff_classification"].eq(class_label).sum())
            for group in GEOMETRY_ORDER
        ]
        ax.bar(x + offset, values, width=width, color=CLASS_COLORS[class_label], label=class_label)
        for xi, value in zip(x + offset, values, strict=False):
            ax.text(xi, value + max(values + [1]) * 0.03, str(value), ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x, [GEOMETRY_LABELS[g] for g in GEOMETRY_ORDER])
    ax.set_ylabel("Units")
    ax.grid(axis="y", color="0.9")


def _plot_ttp_by_geometry(ax, table: pd.DataFrame, cutoff: float) -> None:
    bins = np.arange(0, max(float(table["trough_to_peak_duration_ms"].max()) + 0.16, cutoff + 0.24), 0.08)
    for group in GEOMETRY_ORDER:
        values = pd.to_numeric(
            table.loc[table["geometry_group"].eq(group), "trough_to_peak_duration_ms"],
            errors="coerce",
        ).dropna()
        ax.hist(
            values,
            bins=bins,
            histtype="step",
            linewidth=1.8,
            color=GEOMETRY_COLORS[group],
            label=f"{GEOMETRY_LABELS[group]} n={len(values)}",
        )
    ax.axvline(cutoff, color="black", linestyle="--", linewidth=1.0)
    ax.set_xlabel("TTP (ms)")
    ax.set_ylabel("Units")
    ax.legend(frameon=False, fontsize=8)


def _plot_waveforms(ax, table: pd.DataFrame, traces: pd.DataFrame, stage: str, *, normalize: bool) -> None:
    waveform_col = STAGE_SPECS[stage]["waveform_column"]
    merged = traces.merge(table[["unit_key", "ttp_cutoff_classification"]], on="unit_key", how="inner")
    plot_col = waveform_col
    if normalize:
        plot_col = "_normalized_waveform"
        merged[plot_col] = merged.groupby("unit_key", group_keys=False)[waveform_col].transform(_trough_normalize_trace)
    for class_label in CLASS_ORDER:
        subset = merged.loc[merged["ttp_cutoff_classification"].eq(class_label)]
        if subset.empty:
            continue
        summary = (
            subset.groupby("time_ms", as_index=False)
            .agg(mean=(plot_col, "mean"), sem=(plot_col, _sem_series))
            .sort_values("time_ms")
        )
        time = summary["time_ms"].to_numpy(dtype=float)
        mean = summary["mean"].to_numpy(dtype=float)
        sem = summary["sem"].fillna(0).to_numpy(dtype=float)
        ax.fill_between(time, mean - sem, mean + sem, color=CLASS_COLORS[class_label], alpha=0.18, linewidth=0)
        ax.plot(time, mean, color=CLASS_COLORS[class_label], linewidth=2, label=f"{class_label} n={subset['unit_key'].nunique()}")
    ax.axvline(0, color="0.35", linestyle="--", linewidth=0.8)
    ax.axhline(0, color="0.86", linewidth=0.8)
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("trough-normalized" if normalize else "uV")
    if normalize:
        ax.set_ylim(-1.25, 1.05)
    ax.grid(color="0.92")
    ax.legend(frameon=False, fontsize=8)


def _plot_individual_waveforms_with_mean(ax, table: pd.DataFrame, traces: pd.DataFrame, stage: str) -> None:
    waveform_col = STAGE_SPECS[stage]["waveform_column"]
    merged = traces.merge(table[["unit_key", "ttp_cutoff_classification"]], on="unit_key", how="inner")
    y_bounds: list[float] = []
    for class_label in CLASS_ORDER:
        subset = merged.loc[merged["ttp_cutoff_classification"].eq(class_label)].copy()
        if subset.empty:
            continue
        for _, unit_trace in subset.groupby("unit_key", sort=False):
            values = unit_trace[waveform_col].to_numpy(dtype=float)
            if np.isfinite(values).any():
                y_bounds.extend([float(np.nanmin(values)), float(np.nanmax(values))])
            ax.plot(unit_trace["time_ms"], values, color=CLASS_COLORS[class_label], alpha=0.04, linewidth=0.55)
        summary = subset.groupby("time_ms", as_index=False).agg(mean=(waveform_col, "mean")).sort_values("time_ms")
        ax.plot(
            summary["time_ms"],
            summary["mean"],
            color=CLASS_COLORS[class_label],
            linewidth=2.4,
            label=f"{class_label} mean n={subset['unit_key'].nunique()}",
        )
    ax.axvline(0, color="0.35", linestyle="--", linewidth=0.8)
    ax.axhline(0, color="0.86", linewidth=0.8)
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("uV")
    ax.grid(color="0.92")
    ax.legend(frameon=False, fontsize=8)
    if y_bounds:
        y_min = min(y_bounds)
        y_max = max(y_bounds)
        margin = max((y_max - y_min) * 0.10, 0.35)
        ax.set_ylim(y_min - margin, y_max + margin)


def _plot_halfwidth_rep(ax, table: pd.DataFrame) -> None:
    for group in GEOMETRY_ORDER:
        subset = table.loc[table["geometry_group"].eq(group)].copy()
        ax.scatter(
            subset["spike_half_width_ms"],
            subset["repolarization_time_ms"],
            s=22,
            alpha=0.65,
            color=GEOMETRY_COLORS[group],
            edgecolor="none",
            label=f"{GEOMETRY_LABELS[group]} n={len(subset)}",
        )
    ax.set_xlabel("Half-width (ms)")
    ax.set_ylabel("REP50 (ms)")
    ax.grid(color="0.92")
    ax.legend(frameon=False, fontsize=8)


def _well_column(well: object) -> float:
    match = re.search(r"(\d+)$", str(well))
    return float(match.group(1)) if match else np.nan


def _geometry_group(column: float) -> str:
    if not np.isfinite(column):
        return "unknown"
    if 1 <= column <= 3:
        return "columns_1_3_compare"
    if 4 <= column <= 8:
        return "columns_4_8_prior"
    return "other"


def _median(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return float(clean.median()) if not clean.empty else np.nan


def _sem_array(values: np.ndarray) -> float:
    values = values[np.isfinite(values)]
    if values.size <= 1:
        return np.nan
    return float(np.nanstd(values, ddof=1) / np.sqrt(values.size))


def _sem_series(values: pd.Series) -> float:
    return _sem_array(pd.to_numeric(values, errors="coerce").to_numpy(dtype=float))


def _trough_normalize_trace(values: pd.Series) -> pd.Series:
    trace = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    if trace.size == 0 or not np.isfinite(trace).any():
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    trough = float(np.nanmin(trace))
    denom = abs(trough)
    if not np.isfinite(denom) or denom == 0:
        return pd.Series(np.full(len(values), np.nan), index=values.index)
    return pd.Series(trace / denom, index=values.index)


if __name__ == "__main__":
    main()
