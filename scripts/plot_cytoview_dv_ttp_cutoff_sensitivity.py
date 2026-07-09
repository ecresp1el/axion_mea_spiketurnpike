#!/usr/bin/env python
"""Plot Cytoview dorsal/ventral summaries with an alternate TTP FS cutoff.

This is a Step 1 sensitivity view. It reads the current Cytoview Step 1 unit
metrics table and reclassifies KSLabel=good units using a single TTP cutoff:

    FS_like = TTP <= cutoff
    RS_like = TTP > cutoff

The production SpikeTurnpike TTP classifier in the source unit metrics is not
modified.
"""

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
REGION_ORDER = ["dorsal", "ventral", "unknown"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--fs-cutoff-ms", type=float, default=0.5)
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import spikeinterface.full as si

    job_dir = args.job_dir.expanduser().resolve()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else job_dir / f"cytoview_dorsal_ventral_step1_{args.date_label}_ttp_cutoff_sensitivity_modified"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    source_units_csv = job_dir / f"cytoview_dorsal_ventral_step1_{args.date_label}_unit_metrics.csv"
    units = pd.read_csv(source_units_csv)
    good = units.loc[units["KSLabel"].astype(str).str.lower().eq("good")].copy()
    if good.empty:
        raise SystemExit("No KSLabel=good units found in current Cytoview unit metrics.")

    cutoff_label = _cutoff_label(args.fs_cutoff_ms)
    stem = f"ttp_fs_cutoff_{cutoff_label}"
    good["ttp_cutoff_ms"] = args.fs_cutoff_ms
    good["ttp_cutoff_classification"] = np.where(
        pd.to_numeric(good["trough_to_peak_duration_ms"], errors="coerce").le(args.fs_cutoff_ms),
        "FS_like",
        "RS_like",
    )
    good.loc[pd.to_numeric(good["trough_to_peak_duration_ms"], errors="coerce").isna(), "ttp_cutoff_classification"] = "unknown"

    well_summary = _well_summary(good)
    region_summary = _region_summary(good)
    per_well_summary = _per_well_fraction_summary(well_summary)
    class_firing_rate_summary = _class_firing_rate_summary(good)
    waveform_traces = _extract_best_channel_waveforms(si, good)
    waveform_summary = _waveform_summary(waveform_traces)

    classified_csv = output_dir / f"{stem}_classified_good_units.csv"
    well_csv = output_dir / f"{stem}_well_summary.csv"
    region_csv = output_dir / f"{stem}_region_summary.csv"
    per_well_csv = output_dir / f"{stem}_per_well_class_fraction_summary.csv"
    class_fr_csv = output_dir / f"{stem}_class_firing_rate_summary.csv"
    waveform_traces_csv = output_dir / f"{stem}_pooled_best_channel_waveform_traces.csv.gz"
    waveform_summary_csv = output_dir / f"{stem}_pooled_best_channel_waveform_summary.csv"
    figure_png = output_dir / f"{stem}_current_good_units.png"
    provenance_json = output_dir / f"{stem}_provenance.json"

    good.to_csv(classified_csv, index=False)
    well_summary.to_csv(well_csv, index=False)
    region_summary.to_csv(region_csv, index=False)
    per_well_summary.to_csv(per_well_csv, index=False)
    class_firing_rate_summary.to_csv(class_fr_csv, index=False)
    waveform_traces.to_csv(waveform_traces_csv, index=False)
    waveform_summary.to_csv(waveform_summary_csv, index=False)
    _plot(
        plt,
        good,
        well_summary,
        region_summary,
        per_well_summary,
        waveform_traces,
        figure_png,
        args.fs_cutoff_ms,
    )

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "source_unit_metrics_csv": str(source_units_csv),
        "step1_only": True,
        "fs_cutoff_ms": args.fs_cutoff_ms,
        "classification_rule": "FS_like if trough_to_peak_duration_ms <= fs_cutoff_ms else RS_like",
        "production_classifier_modified": False,
        "waveform_alignment": "Best-channel raw uV template traces are aligned to each unit's negative trough before pooled mean/SEM calculation.",
        "output_dir": str(output_dir),
        "outputs": {
            "classified_good_units_csv": str(classified_csv),
            "well_summary_csv": str(well_csv),
            "region_summary_csv": str(region_csv),
            "per_well_class_fraction_summary_csv": str(per_well_csv),
            "class_firing_rate_summary_csv": str(class_fr_csv),
            "pooled_best_channel_waveform_traces_csv": str(waveform_traces_csv),
            "pooled_best_channel_waveform_summary_csv": str(waveform_summary_csv),
            "figure_png": str(figure_png),
        },
    }
    provenance_json.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(f"Source unit metrics CSV: {source_units_csv}")
    print(f"Output dir: {output_dir}")
    print(f"FS cutoff: TTP <= {args.fs_cutoff_ms:.3f} ms")
    print(f"Classified good units CSV: {classified_csv}")
    print(f"Well summary CSV: {well_csv}")
    print(f"Region summary CSV: {region_csv}")
    print(f"Per-well class fraction summary CSV: {per_well_csv}")
    print(f"Class firing-rate summary CSV: {class_fr_csv}")
    print(f"Pooled best-channel waveform traces CSV: {waveform_traces_csv}")
    print(f"Pooled best-channel waveform summary CSV: {waveform_summary_csv}")
    print(f"Figure PNG: {figure_png}")
    print(f"Provenance: {provenance_json}")
    print("\nRegion summary:")
    print(region_summary.to_string(index=False))
    print("\nPer-well mean class fraction summary:")
    print(per_well_summary.to_string(index=False))


def _well_summary(good: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (recording, well), group in good.groupby(["recording", "well"], dropna=False):
        region = str(group["region_call"].iloc[0])
        row = {
            "recording": recording,
            "well": well,
            "region_call": region,
            "good_unit_count": int(len(group)),
            "good_median_firing_rate_hz": _median(group["firing_rate_hz"]),
            "good_mean_firing_rate_hz": _mean(group["firing_rate_hz"]),
            "good_median_isi_ms": _median(group["isi_median_ms"]),
        }
        for label in ["FS_like", "RS_like", "unknown"]:
            row[f"good_{label}_count"] = int(group["ttp_cutoff_classification"].eq(label).sum())
        denom = row["good_unit_count"]
        for label in ["FS_like", "RS_like", "unknown"]:
            row[f"good_{label}_fraction"] = row[f"good_{label}_count"] / denom if denom else np.nan
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["region_call", "recording", "well"]).reset_index(drop=True)


def _region_summary(good: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for region in REGION_ORDER:
        subset = good.loc[good["region_call"].eq(region)].copy()
        if subset.empty and region == "unknown":
            continue
        row = {
            "region_call": region,
            "good_unit_count": int(len(subset)),
            "recording_count": int(subset["recording"].nunique()) if not subset.empty else 0,
            "well_count": int(subset[["recording", "well"]].drop_duplicates().shape[0]) if not subset.empty else 0,
            "median_firing_rate_hz": _median(subset["firing_rate_hz"]),
            "mean_firing_rate_hz": _mean(subset["firing_rate_hz"]),
            "median_isi_ms": _median(subset["isi_median_ms"]),
            "median_ttp_ms": _median(subset["trough_to_peak_duration_ms"]),
        }
        for label in ["FS_like", "RS_like", "unknown"]:
            row[f"{label}_count"] = int(subset["ttp_cutoff_classification"].eq(label).sum())
        denom = row["good_unit_count"]
        for label in ["FS_like", "RS_like", "unknown"]:
            row[f"{label}_fraction"] = row[f"{label}_count"] / denom if denom else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _per_well_fraction_summary(well_summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    eligible = well_summary.loc[well_summary["good_unit_count"].gt(0)].copy()
    for region in REGION_ORDER:
        subset = eligible.loc[eligible["region_call"].eq(region)].copy()
        if subset.empty and region == "unknown":
            continue
        row: dict[str, object] = {
            "region_call": region,
            "well_count_with_good_units": int(len(subset)),
            "total_good_units": int(subset["good_unit_count"].sum()) if not subset.empty else 0,
        }
        for label in ["FS_like", "RS_like", "unknown"]:
            values = pd.to_numeric(subset[f"good_{label}_fraction"], errors="coerce").dropna()
            row[f"{label}_mean_per_well_fraction"] = _mean(values)
            row[f"{label}_sem_per_well_fraction"] = _sem(values)
            row[f"{label}_well_n"] = int(values.size)
            row[f"{label}_unit_count"] = int(subset[f"good_{label}_count"].sum()) if not subset.empty else 0
        rows.append(row)
    return pd.DataFrame(rows)


def _class_firing_rate_summary(good: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for class_label in ["FS_like", "RS_like", "unknown"]:
        subset = good.loc[good["ttp_cutoff_classification"].eq(class_label)]
        if subset.empty and class_label == "unknown":
            continue
        rows.append(_class_fr_row("overall", "all", class_label, subset))
    for region in REGION_ORDER:
        region_subset = good.loc[good["region_call"].eq(region)]
        if region_subset.empty and region == "unknown":
            continue
        for class_label in ["FS_like", "RS_like", "unknown"]:
            subset = region_subset.loc[region_subset["ttp_cutoff_classification"].eq(class_label)]
            if subset.empty and class_label == "unknown":
                continue
            rows.append(_class_fr_row("region", region, class_label, subset))
    return pd.DataFrame(rows)


def _class_fr_row(scope: str, group: str, class_label: str, subset: pd.DataFrame) -> dict[str, object]:
    return {
        "scope": scope,
        "group": group,
        "ttp_cutoff_classification": class_label,
        "unit_count": int(len(subset)),
        "median_firing_rate_hz": _median(subset["firing_rate_hz"]),
        "mean_firing_rate_hz": _mean(subset["firing_rate_hz"]),
        "sem_firing_rate_hz": _sem(subset["firing_rate_hz"]),
        "max_firing_rate_hz": _max(subset["firing_rate_hz"]),
    }


def _extract_best_channel_waveforms(si, good: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    required = {"analyzer_path", "unit_index", "best_channel_index"}
    if not required.issubset(good.columns):
        return pd.DataFrame(rows)
    for analyzer_path, group in good.groupby("analyzer_path", dropna=False):
        analyzer_path = str(analyzer_path)
        if not analyzer_path or analyzer_path == "nan":
            continue
        analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
        templates_ext = analyzer.get_extension("templates")
        if templates_ext is None:
            continue
        templates = _templates_average(templates_ext)
        if templates.ndim != 3:
            continue
        sampling_frequency = float(analyzer.recording.get_sampling_frequency())
        nbefore_attr = getattr(templates_ext, "nbefore", None)
        for row in group.itertuples(index=False):
            unit_index = int(getattr(row, "unit_index"))
            best_channel_index = int(getattr(row, "best_channel_index"))
            if unit_index < 0 or unit_index >= templates.shape[0]:
                continue
            if best_channel_index < 0 or best_channel_index >= templates.shape[2]:
                continue
            waveform = np.asarray(templates[unit_index, :, best_channel_index], dtype=float)
            if nbefore_attr is None:
                nbefore = int(np.nanargmin(waveform))
            else:
                nbefore = int(nbefore_attr)
            trough_index = int(np.nanargmin(waveform))
            template_time_ms = (np.arange(waveform.size) - nbefore) / sampling_frequency * 1000.0
            aligned_time_ms = (np.arange(waveform.size) - trough_index) / sampling_frequency * 1000.0
            unit_key = f"{getattr(row, 'recording')}|{getattr(row, 'well')}|{getattr(row, 'unit_id')}"
            for sample_index, (template_sample_time_ms, aligned_sample_time_ms, value) in enumerate(
                zip(template_time_ms, aligned_time_ms, waveform, strict=False)
            ):
                rows.append(
                    {
                        "recording": getattr(row, "recording"),
                        "well": getattr(row, "well"),
                        "region_call": getattr(row, "region_call"),
                        "unit_id": getattr(row, "unit_id"),
                        "unit_index": unit_index,
                        "best_channel_index": best_channel_index,
                        "unit_key": unit_key,
                        "ttp_cutoff_classification": getattr(row, "ttp_cutoff_classification"),
                        "trough_to_peak_duration_ms": getattr(row, "trough_to_peak_duration_ms"),
                        "firing_rate_hz": getattr(row, "firing_rate_hz"),
                        "sample_index": sample_index,
                        "template_time_ms": float(template_sample_time_ms),
                        "aligned_sample_index": int(sample_index - trough_index),
                        "aligned_time_ms": float(aligned_sample_time_ms),
                        "alignment_reference": "best_channel_negative_trough",
                        "trough_sample_index": trough_index,
                        "trough_uV": float(waveform[trough_index]),
                        "waveform_uV": float(value),
                    }
                )
    return pd.DataFrame(rows)


def _waveform_summary(waveform_traces: pd.DataFrame) -> pd.DataFrame:
    if waveform_traces.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    grouped = waveform_traces.groupby(
        ["ttp_cutoff_classification", "aligned_sample_index", "aligned_time_ms"],
        dropna=False,
    )
    for (class_label, aligned_sample_index, aligned_time_ms), subset in grouped:
        rows.append(
            {
                "ttp_cutoff_classification": class_label,
                "aligned_sample_index": int(aligned_sample_index),
                "aligned_time_ms": float(aligned_time_ms),
                "alignment_reference": "best_channel_negative_trough",
                "unit_count": int(subset["unit_key"].nunique()),
                "mean_waveform_uV": _mean(subset["waveform_uV"]),
                "sem_waveform_uV": _sem(subset["waveform_uV"]),
                "median_waveform_uV": _median(subset["waveform_uV"]),
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["ttp_cutoff_classification", "aligned_sample_index"])
        .reset_index(drop=True)
    )


def _plot(
    plt,
    good: pd.DataFrame,
    well_summary: pd.DataFrame,
    region_summary: pd.DataFrame,
    per_well_summary: pd.DataFrame,
    waveform_traces: pd.DataFrame,
    output_path: Path,
    fs_cutoff_ms: float,
) -> None:
    colors = {"FS_like": "#d55e00", "RS_like": "#0072b2", "unknown": "#bbbbbb"}
    region_colors = {"dorsal": "#2a9d8f", "ventral": "#6a4c93", "unknown": "#888888"}
    region_summary = region_summary.loc[region_summary["region_call"].isin(REGION_ORDER)].copy()
    per_well_summary = per_well_summary.loc[per_well_summary["region_call"].isin(region_summary["region_call"])].copy()

    fig, axes = plt.subplots(2, 4, figsize=(22.6, 9.6))
    axes = axes.ravel()
    x = np.arange(len(region_summary))

    bottom = np.zeros(len(region_summary))
    for label in ["FS_like", "RS_like"]:
        values = per_well_summary[f"{label}_mean_per_well_fraction"].fillna(0.0).to_numpy()
        sem_values = per_well_summary[f"{label}_sem_per_well_fraction"].fillna(0.0).to_numpy()
        axes[0].bar(x, values, bottom=bottom, color=colors[label], label=label)
        for xi, yi, bi, sem in zip(x, values, bottom, sem_values, strict=False):
            if yi > 0 and np.isfinite(sem) and sem > 0:
                axes[0].errorbar(
                    xi,
                    bi + yi / 2.0,
                    yerr=sem,
                    color="black",
                    capsize=3,
                    linewidth=0.9,
                    zorder=5,
                )
            if yi >= 0.055:
                axes[0].text(
                    xi,
                    bi + yi / 2.0,
                    f"{yi:.0%}\nSEM {sem:.0%}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white",
                )
        bottom += values
    axes[0].set_xticks(
        x,
        [
            f"{row.region_call}\n{int(row.total_good_units)} good units\n{int(row.well_count_with_good_units)} wells"
            for row in per_well_summary.itertuples()
        ],
    )
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("Mean per-well fraction")
    axes[0].set_title(f"FS/RS mean per-well proportions +/- SEM\nFS = TTP <= {fs_cutoff_ms:.2f} ms")
    axes[0].legend(frameon=False, fontsize=8)

    yield_ymax = float(well_summary["good_unit_count"].max()) + 3.0
    for region_index, region in enumerate(region_summary["region_call"]):
        subset = well_summary.loc[well_summary["region_call"].eq(region), "good_unit_count"].dropna()
        if subset.empty:
            continue
        jitter = _deterministic_jitter(len(subset), width=0.12)
        axes[1].scatter(
            np.full(len(subset), region_index) + jitter,
            subset,
            s=34,
            alpha=0.72,
            color=region_colors.get(str(region), "#888888"),
            edgecolor="white",
            linewidth=0.4,
        )
        axes[1].hlines(subset.median(), region_index - 0.23, region_index + 0.23, color="black", linewidth=2)
        axes[1].text(
            region_index,
            yield_ymax - 0.15,
            f"median/well {subset.median():.1f}\nmean/well {subset.mean():.1f}",
            ha="center",
            va="top",
            fontsize=8,
        )
    axes[1].set_xticks(np.arange(len(region_summary)), region_summary["region_call"])
    axes[1].set_ylim(-0.5, yield_ymax)
    axes[1].set_ylabel("KSLabel=good units per well")
    axes[1].set_title("Good-unit yield per GUI-ready well")
    axes[1].grid(axis="y", color="0.9")

    _plot_class_firing_rates_overall(axes[2], good, colors)
    _plot_pooled_waveforms(axes[3], waveform_traces, colors)

    for region, subset in good.groupby("region_call", dropna=False):
        region_index = REGION_ORDER.index(region) if region in REGION_ORDER else len(REGION_ORDER) - 1
        jitter = _deterministic_jitter(len(subset), width=0.16)
        axes[4].scatter(
            np.full(len(subset), region_index) + jitter,
            subset["firing_rate_hz"],
            s=20,
            alpha=0.62,
            color=region_colors.get(str(region), "#888888"),
            edgecolor="none",
        )
        axes[4].hlines(subset["firing_rate_hz"].median(), region_index - 0.26, region_index + 0.26, color="black", linewidth=2)
    axes[4].set_xticks(np.arange(len(region_summary)), region_summary["region_call"])
    axes[4].set_ylabel("Firing rate (Hz)")
    axes[4].set_title("All KSLabel=good firing rates by region")
    axes[4].grid(axis="y", color="0.9")

    _plot_class_firing_rates_by_region(axes[5], good, colors)
    _plot_ttp_distribution(axes[6], good, colors, fs_cutoff_ms)

    bar_width = 0.34
    median_values = region_summary["median_firing_rate_hz"].to_numpy(dtype=float)
    mean_values = region_summary["mean_firing_rate_hz"].to_numpy(dtype=float)
    axes[7].bar(x - bar_width / 2, median_values, width=bar_width, color="#4c78a8", label="median")
    axes[7].bar(x + bar_width / 2, mean_values, width=bar_width, color="#f58518", label="mean")
    for xi, median_value, mean_value in zip(x, median_values, mean_values, strict=False):
        axes[7].text(xi - bar_width / 2, median_value, f"{median_value:.2f}", ha="center", va="bottom", fontsize=8)
        axes[7].text(xi + bar_width / 2, mean_value, f"{mean_value:.2f}", ha="center", va="bottom", fontsize=8)
    axes[7].set_xticks(x, region_summary["region_call"])
    axes[7].set_ylabel("Firing rate (Hz)")
    axes[7].set_title("Overall firing-rate summary")
    axes[7].legend(frameon=False, fontsize=8)
    axes[7].grid(axis="y", color="0.9")

    for ax in axes:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.suptitle("Cytoview dorsal/ventral TTP cutoff sensitivity; KSLabel=good, Step 1 only", y=1.01, fontsize=13)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_class_firing_rates_overall(ax, good: pd.DataFrame, colors: dict[str, str]) -> None:
    class_order = ["FS_like", "RS_like"]
    ymax = _max(good["firing_rate_hz"])
    for class_index, class_label in enumerate(class_order):
        subset = good.loc[good["ttp_cutoff_classification"].eq(class_label)].copy()
        if subset.empty:
            continue
        jitter = _deterministic_jitter(len(subset), width=0.13)
        ax.scatter(
            np.full(len(subset), class_index) + jitter,
            subset["firing_rate_hz"],
            s=24,
            alpha=0.68,
            color=colors.get(class_label, "#888888"),
            edgecolor="none",
        )
        median = _median(subset["firing_rate_hz"])
        mean = _mean(subset["firing_rate_hz"])
        ax.hlines(median, class_index - 0.24, class_index + 0.24, color="black", linewidth=2)
        ax.text(
            class_index,
            float(subset["firing_rate_hz"].max()) + 0.35,
            f"n={len(subset)}\nmedian {median:.2f}\nmean {mean:.2f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    ax.set_xticks(np.arange(len(class_order)), [label.replace("_", "\n") for label in class_order])
    if np.isfinite(ymax):
        ax.set_ylim(-0.5, ymax + 2.2)
    ax.set_ylabel("Firing rate (Hz)")
    ax.set_title("Firing rate by FS/RS class, all regions")
    ax.grid(axis="y", color="0.9")


def _plot_pooled_waveforms(ax, waveform_traces: pd.DataFrame, colors: dict[str, str]) -> None:
    if waveform_traces.empty:
        ax.text(0.5, 0.5, "No waveform traces available", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        return
    y_limits: list[float] = []
    for class_label in ["FS_like", "RS_like"]:
        subset = waveform_traces.loc[waveform_traces["ttp_cutoff_classification"].eq(class_label)].copy()
        if subset.empty:
            continue
        unit_count = subset["unit_key"].nunique()
        for _, unit_trace in subset.groupby("unit_key", sort=False):
            ax.plot(
                unit_trace["aligned_time_ms"],
                unit_trace["waveform_uV"],
                color=colors.get(class_label, "#888888"),
                alpha=0.055,
                linewidth=0.65,
            )
        summary = (
            subset.groupby("aligned_time_ms", as_index=False)
            .agg(
                mean_waveform_uV=("waveform_uV", "mean"),
                sem_waveform_uV=("waveform_uV", lambda values: _sem(pd.Series(values))),
            )
            .sort_values("aligned_time_ms")
        )
        time_ms = summary["aligned_time_ms"].to_numpy(dtype=float)
        mean = summary["mean_waveform_uV"].to_numpy(dtype=float)
        sem = summary["sem_waveform_uV"].fillna(0.0).to_numpy(dtype=float)
        y_limits.extend([float(np.nanmin(mean - sem)), float(np.nanmax(mean + sem))])
        ax.fill_between(
            time_ms,
            mean - sem,
            mean + sem,
            color=colors.get(class_label, "#888888"),
            alpha=0.20,
            linewidth=0,
        )
        ax.plot(
            time_ms,
            mean,
            color=colors.get(class_label, "#888888"),
            linewidth=2.2,
            label=f"{class_label.replace('_like', '')} n={unit_count}",
        )
    ax.axvline(0, color="0.4", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Time from aligned negative trough (ms)")
    ax.set_ylabel("Best-channel template (uV)")
    ax.set_title("Pooled mean waveforms aligned to trough")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(color="0.92")
    if y_limits:
        y_min = min(y_limits)
        y_max = max(y_limits)
        margin = max((y_max - y_min) * 0.28, 0.4)
        ax.set_ylim(y_min - margin, y_max + margin)


def _plot_class_firing_rates_by_region(ax, good: pd.DataFrame, colors: dict[str, str]) -> None:
    positions: list[float] = []
    labels: list[str] = []
    ymax = _max(good["firing_rate_hz"])
    xpos = 0.0
    for region in ["dorsal", "ventral"]:
        for class_label in ["FS_like", "RS_like"]:
            subset = good.loc[
                good["region_call"].eq(region) & good["ttp_cutoff_classification"].eq(class_label)
            ].copy()
            positions.append(xpos)
            labels.append(f"{region}\n{class_label.replace('_like', '')}")
            if not subset.empty:
                jitter = _deterministic_jitter(len(subset), width=0.10)
                ax.scatter(
                    np.full(len(subset), xpos) + jitter,
                    subset["firing_rate_hz"],
                    s=24,
                    alpha=0.68,
                    color=colors.get(class_label, "#888888"),
                    edgecolor="none",
                )
                median = _median(subset["firing_rate_hz"])
                ax.hlines(median, xpos - 0.20, xpos + 0.20, color="black", linewidth=2)
                ax.text(
                    xpos,
                    float(subset["firing_rate_hz"].max()) + 0.35,
                    f"n={len(subset)}\nmed {median:.2f}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )
            xpos += 1.0
        xpos += 0.45
    ax.set_xticks(positions, labels)
    if np.isfinite(ymax):
        ax.set_ylim(-0.5, ymax + 2.2)
    ax.set_ylabel("Firing rate (Hz)")
    ax.set_title("Firing rate by FS/RS class within region")
    ax.grid(axis="y", color="0.9")


def _plot_ttp_distribution(ax, good: pd.DataFrame, colors: dict[str, str], fs_cutoff_ms: float) -> None:
    ttp = pd.to_numeric(good["trough_to_peak_duration_ms"], errors="coerce").dropna()
    if ttp.empty:
        ax.text(0.5, 0.5, "No TTP values available", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        return
    bin_max = max(float(ttp.max()) + 0.08, fs_cutoff_ms + 0.2)
    bins = np.linspace(0.0, bin_max, 28)
    for class_label in ["FS_like", "RS_like"]:
        subset = good.loc[good["ttp_cutoff_classification"].eq(class_label), "trough_to_peak_duration_ms"]
        values = pd.to_numeric(subset, errors="coerce").dropna()
        if values.empty:
            continue
        ax.hist(
            values,
            bins=bins,
            color=colors.get(class_label, "#888888"),
            alpha=0.62,
            label=f"{class_label.replace('_like', '')} n={len(values)}",
        )
    ax.axvline(fs_cutoff_ms, color="black", linewidth=1.5, linestyle="--", label=f"cutoff {fs_cutoff_ms:.2f} ms")
    ax.set_xlabel("TTP (ms)")
    ax.set_ylabel("Good-unit count")
    ax.set_title("TTP distribution, pooled good units")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(axis="y", color="0.92")


def _templates_average(templates_ext) -> np.ndarray:
    try:
        return np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        templates_data = templates_ext.get_data()
        if isinstance(templates_data, dict):
            templates_data = templates_data.get("average")
        return np.asarray(templates_data, dtype=float)


def _cutoff_label(value: float) -> str:
    return f"{value:.2f}".replace(".", "p")


def _deterministic_jitter(n: int, width: float) -> np.ndarray:
    if n <= 1:
        return np.zeros(n)
    return np.linspace(-width, width, n)


def _median(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    return float(values.median()) if not values.empty else np.nan


def _mean(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else np.nan


def _max(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    return float(values.max()) if not values.empty else np.nan


def _sem(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.size <= 1:
        return np.nan
    return float(values.std(ddof=1) / np.sqrt(values.size))


if __name__ == "__main__":
    main()
