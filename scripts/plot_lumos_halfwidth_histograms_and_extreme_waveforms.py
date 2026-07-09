#!/usr/bin/env python
"""Plot Lumos half-width histograms and extreme waveform overlays.

The main use case is KSLabel=good Lumos units, but the script can also render
MUA-only or all sorted-unit views from the same all-unit metric table. The old
half-width is the current baseline-referenced SpikeTurnpike metric. The new
half-width is the robust local-excursion metric:

    midpoint = (Peak1 + trough) / 2

with monotonic, interpolated crossing selection.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_DATE_LABEL = "20260709"
CLASS_ORDER = ["FS_like", "borderline", "RS_like"]
CLASS_COLORS = {"FS_like": "#d55e00", "borderline": "#777777", "RS_like": "#0072b2"}
RECORDING_NAME = "block0_None_recording1.zarr"


@dataclass(frozen=True)
class UnitWaveform:
    row_index: int
    metadata: dict[str, object]
    time_ms: np.ndarray
    waveform_uV: np.ndarray
    normalized: np.ndarray


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--metrics-csv", type=Path)
    parser.add_argument(
        "--kslabel",
        choices=("good", "mua", "all"),
        default="good",
        help="Which sorted units to include in the figure.",
    )
    parser.add_argument("--extreme-n", type=int, default=18)
    parser.add_argument(
        "--waveform-scale",
        choices=("normalized", "raw_uv"),
        default="normalized",
        help="Scale used only for waveform overlays; histograms remain metric values in ms.",
    )
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import spikeinterface.full as si

    job_dir = args.job_dir.expanduser().resolve()
    metrics_csv = args.metrics_csv or job_dir / f"lumos_all_sorted_unit_waveform_metrics_{args.date_label}.csv"
    metrics = pd.read_csv(metrics_csv)
    subset = _filter_subset(metrics, args.kslabel)
    if subset.empty:
        raise SystemExit(f"No rows found for kslabel={args.kslabel!r}.")
    subset = subset.sort_values(["rs_fs_classification", "recording", "well", "unit_index"]).reset_index(drop=True)

    waveforms = _load_waveforms(si, subset)
    if not waveforms:
        raise SystemExit("No waveforms could be loaded for plotting.")

    scale_suffix = "" if args.waveform_scale == "normalized" else "_raw_uv"
    stem = f"lumos_{args.kslabel}_halfwidth_histograms_extreme_waveforms_{args.date_label}{scale_suffix}"
    figure_png = job_dir / f"{stem}.png"
    figure_pdf = job_dir / f"{stem}.pdf"
    selected_csv = job_dir / f"{stem}_selected_extremes.csv"
    provenance_json = job_dir / f"{stem}_provenance.json"

    selected = _selected_extreme_rows(subset, extreme_n=args.extreme_n)
    selected.to_csv(selected_csv, index=False)
    figure = _make_figure(
        plt,
        subset,
        waveforms,
        selected,
        title_label=args.kslabel,
        waveform_scale=args.waveform_scale,
    )
    figure.savefig(figure_png, dpi=240, bbox_inches="tight")
    figure.savefig(figure_pdf, bbox_inches="tight")
    plt.close(figure)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "metrics_csv": str(metrics_csv),
        "kslabel": args.kslabel,
        "unit_count": int(len(subset)),
        "class_counts": subset["rs_fs_classification"].value_counts(dropna=False).to_dict(),
        "outputs": {
            "figure_png": str(figure_png),
            "figure_pdf": str(figure_pdf),
            "selected_extremes_csv": str(selected_csv),
        },
        "definitions": {
            "old_half_width": "current baseline-referenced SpikeTurnpike half-width",
            "new_half_width": "robust local-excursion half-width at (Peak1 + trough) / 2",
            "waveform_overlay": _waveform_scale_description(args.waveform_scale),
        },
    }
    provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Metrics CSV: {metrics_csv}")
    print(f"KSLabel subset: {args.kslabel}")
    print(f"Waveform overlay scale: {args.waveform_scale}")
    print(f"Units plotted: {len(subset)}")
    print("TTP class counts:")
    print(subset["rs_fs_classification"].value_counts(dropna=False).to_string())
    print(f"Figure PNG: {figure_png}")
    print(f"Figure PDF: {figure_pdf}")
    print(f"Selected extremes CSV: {selected_csv}")
    print(f"Provenance: {provenance_json}")


def _filter_subset(metrics: pd.DataFrame, kslabel: str) -> pd.DataFrame:
    out = metrics.copy()
    for column in [
        "current_half_width_ms",
        "robust_local_half_width_ms",
        "trough_to_peak_duration_ms",
        "pre_peak_to_trough_ratio_uV",
    ]:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    if kslabel != "all":
        out = out.loc[out["KSLabel"].astype(str).str.lower().eq(kslabel)].copy()
    return out.reset_index(drop=False).rename(columns={"index": "source_row_index"})


def _load_waveforms(si, subset: pd.DataFrame) -> list[UnitWaveform]:
    waveforms: list[UnitWaveform] = []
    for analyzer_path_text, group in subset.groupby("analyzer_path", dropna=False):
        analyzer_path = Path(str(analyzer_path_text))
        analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
        templates_ext = analyzer.get_extension("templates")
        if templates_ext is None:
            continue
        templates = _templates_average(templates_ext)
        sampling_frequency = float(analyzer.recording.get_sampling_frequency())
        for _, row in group.iterrows():
            unit_index = int(row["unit_index"])
            channel_index = int(row["best_channel_index"])
            if unit_index < 0 or unit_index >= templates.shape[0] or channel_index < 0 or channel_index >= templates.shape[2]:
                continue
            waveform = np.asarray(templates[unit_index, :, channel_index], dtype=float)
            nbefore = int(getattr(templates_ext, "nbefore", np.nanargmin(waveform)))
            time_ms = (np.arange(waveform.size) - nbefore) / sampling_frequency * 1000.0
            normalized = _trough_normalize(waveform)
            waveforms.append(
                UnitWaveform(
                    row_index=int(row["source_row_index"]),
                    metadata=row.to_dict(),
                    time_ms=time_ms,
                    waveform_uV=waveform,
                    normalized=normalized,
                )
            )
    return waveforms


def _templates_average(templates_ext) -> np.ndarray:
    try:
        return np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        templates_data = templates_ext.get_data()
        if isinstance(templates_data, dict):
            templates_data = templates_data.get("average")
        return np.asarray(templates_data, dtype=float)


def _trough_normalize(waveform: np.ndarray) -> np.ndarray:
    if waveform.size == 0 or not np.isfinite(waveform).any():
        return np.full_like(waveform, np.nan, dtype=float)
    trough = float(np.nanmin(waveform))
    depth = abs(trough)
    return waveform / depth if depth > 0 else np.full_like(waveform, np.nan, dtype=float)


def _selected_extreme_rows(subset: pd.DataFrame, *, extreme_n: int) -> pd.DataFrame:
    extreme_n = max(1, int(extreme_n))
    tables = []
    specs = [
        ("old_narrowest", "current_half_width_ms", True),
        ("old_broadest", "current_half_width_ms", False),
        ("new_narrowest", "robust_local_half_width_ms", True),
        ("new_broadest", "robust_local_half_width_ms", False),
    ]
    temp = subset.copy()
    temp["old_new_abs_delta_ms"] = (
        temp["robust_local_half_width_ms"] - temp["current_half_width_ms"]
    ).abs()
    specs.append(("largest_old_new_delta", "old_new_abs_delta_ms", False))
    for label, column, ascending in specs:
        selected = temp.dropna(subset=[column]).sort_values(column, ascending=ascending).head(extreme_n).copy()
        selected["selection_group"] = label
        selected["selection_metric"] = column
        tables.append(selected)
    return pd.concat(tables, ignore_index=True) if tables else subset.iloc[0:0].copy()


def _make_figure(
    plt,
    subset: pd.DataFrame,
    waveforms: list[UnitWaveform],
    selected: pd.DataFrame,
    *,
    title_label: str,
    waveform_scale: str,
):
    figure, axes = plt.subplots(2, 3, figsize=(18.0, 10.8))
    _plot_histogram(
        axes[0, 0],
        subset,
        metric="current_half_width_ms",
        title="Old half-width",
        xlabel="Baseline-referenced half-width (ms)",
    )
    _plot_histogram(
        axes[0, 1],
        subset,
        metric="robust_local_half_width_ms",
        title="New robust local-excursion half-width",
        xlabel="Robust local half-width (ms)",
    )
    _plot_mean_waveforms(axes[0, 2], waveforms, waveform_scale=waveform_scale)
    _plot_extreme_overlay(
        axes[1, 0],
        waveforms,
        selected,
        group_name="new_narrowest",
        title="Narrowest new local HW",
        waveform_scale=waveform_scale,
    )
    _plot_extreme_overlay(
        axes[1, 1],
        waveforms,
        selected,
        group_name="new_broadest",
        title="Broadest new local HW",
        waveform_scale=waveform_scale,
    )
    _plot_extreme_overlay(
        axes[1, 2],
        waveforms,
        selected,
        group_name="largest_old_new_delta",
        title="Largest old/new HW disagreement",
        waveform_scale=waveform_scale,
    )
    figure.suptitle(
        f"Lumos {title_label} units: half-width distributions and waveform extremes ({_waveform_scale_title(waveform_scale)})",
        y=0.995,
        fontsize=15,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.965))
    return figure


def _plot_histogram(axis, subset: pd.DataFrame, *, metric: str, title: str, xlabel: str) -> None:
    finite = subset[metric].replace([np.inf, -np.inf], np.nan).dropna()
    total_units = int(len(subset))
    valid_mask = subset[metric].replace([np.inf, -np.inf], np.nan).notna()
    valid_units = int(valid_mask.sum())
    excluded_units = int((~valid_mask).sum())
    if finite.empty:
        axis.text(0.5, 0.5, "No finite values", transform=axis.transAxes, ha="center", va="center")
        return
    high = min(max(float(finite.quantile(0.995)), 0.8), max(float(finite.max()), 0.8))
    bins = np.linspace(0.0, high, 36)
    for label in CLASS_ORDER:
        values = subset.loc[subset["rs_fs_classification"].eq(label), metric].replace([np.inf, -np.inf], np.nan).dropna()
        if values.empty:
            continue
        axis.hist(
            values,
            bins=bins,
            histtype="stepfilled",
            alpha=0.35,
            color=CLASS_COLORS[label],
            edgecolor=CLASS_COLORS[label],
            linewidth=1.3,
            label=f"{label} valid n={len(values)}",
        )
    axis.set_title(title)
    axis.set_xlabel(xlabel)
    axis.set_ylabel("Unit count")
    axis.legend(frameon=False, fontsize=8)
    axis.grid(axis="y", color="0.9", linewidth=0.7)
    _add_denominator_box(axis, subset, metric, total_units, valid_units, excluded_units)


def _add_denominator_box(
    axis,
    subset: pd.DataFrame,
    metric: str,
    total_units: int,
    valid_units: int,
    excluded_units: int,
) -> None:
    valid_mask = subset[metric].replace([np.inf, -np.inf], np.nan).notna()
    valid_subset = subset.loc[valid_mask]
    class_counts = ", ".join(
        f"{label.replace('_like', '')}={int(valid_subset['rs_fs_classification'].eq(label).sum())}"
        for label in CLASS_ORDER
    )
    text = f"Total={total_units}\nValid={valid_units}; excluded={excluded_units}\nValid TTP: {class_counts}"
    if excluded_units:
        excluded_subset = subset.loc[~valid_mask]
        excluded_counts = ", ".join(
            f"{label.replace('_like', '')}={int(excluded_subset['rs_fs_classification'].eq(label).sum())}"
            for label in CLASS_ORDER
        )
        text += f"\nExcluded TTP: {excluded_counts}"
    axis.text(
        0.98,
        0.96,
        text,
        transform=axis.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        bbox={"boxstyle": "round,pad=0.28", "facecolor": "white", "edgecolor": "0.75", "alpha": 0.9},
    )


def _plot_mean_waveforms(axis, waveforms: list[UnitWaveform], *, waveform_scale: str) -> None:
    plotted_values = []
    for label in CLASS_ORDER:
        class_waveforms = [item for item in waveforms if item.metadata.get("rs_fs_classification") == label]
        if not class_waveforms:
            continue
        time_ms = class_waveforms[0].time_ms
        stack = np.vstack([
            _waveform_values(item, waveform_scale)
            for item in class_waveforms
            if _waveform_values(item, waveform_scale).size == time_ms.size
        ])
        if stack.size == 0:
            continue
        mean = np.nanmean(stack, axis=0)
        plotted_values.append(mean)
        axis.plot(time_ms, mean, color=CLASS_COLORS[label], linewidth=2.6, label=f"{label} mean n={stack.shape[0]}")
        if label in {"FS_like", "RS_like"}:
            for item in class_waveforms[:40]:
                values = _waveform_values(item, waveform_scale)
                plotted_values.append(values)
                axis.plot(item.time_ms, values, color=CLASS_COLORS[label], alpha=0.08, linewidth=0.8)
    axis.axhline(0, color="0.84", linewidth=0.8)
    axis.axvline(0, color="0.84", linewidth=0.8)
    axis.set_title("Mean waveform by current TTP class")
    axis.set_xlabel("Time (ms)")
    axis.set_ylabel(_waveform_ylabel(waveform_scale))
    axis.legend(frameon=False, fontsize=8)
    axis.grid(color="0.92", linewidth=0.7)
    _apply_robust_waveform_ylim(axis, plotted_values, waveform_scale=waveform_scale)


def _plot_extreme_overlay(
    axis,
    waveforms: list[UnitWaveform],
    selected: pd.DataFrame,
    *,
    group_name: str,
    title: str,
    waveform_scale: str,
) -> None:
    selected_ids = set(selected.loc[selected["selection_group"].eq(group_name), "source_row_index"].astype(int))
    selected_waveforms = [item for item in waveforms if item.row_index in selected_ids]
    plotted_values = []
    for item in selected_waveforms:
        label = str(item.metadata.get("rs_fs_classification"))
        values = _waveform_values(item, waveform_scale)
        plotted_values.append(values)
        axis.plot(
            item.time_ms,
            values,
            color=CLASS_COLORS.get(label, "#444444"),
            alpha=0.48,
            linewidth=1.05,
        )
    axis.axhline(0, color="0.84", linewidth=0.8)
    axis.axvline(0, color="0.84", linewidth=0.8)
    axis.set_title(f"{title} (n={len(selected_waveforms)})")
    axis.set_xlabel("Time (ms)")
    axis.set_ylabel(_waveform_ylabel(waveform_scale))
    axis.grid(color="0.92", linewidth=0.7)
    _apply_robust_waveform_ylim(axis, plotted_values, waveform_scale=waveform_scale)


def _waveform_values(item: UnitWaveform, waveform_scale: str) -> np.ndarray:
    if waveform_scale == "raw_uv":
        return item.waveform_uV
    return item.normalized


def _waveform_ylabel(waveform_scale: str) -> str:
    return "Raw best-channel amplitude (uV)" if waveform_scale == "raw_uv" else "Trough-normalized amplitude"


def _waveform_scale_title(waveform_scale: str) -> str:
    return "raw uV overlays" if waveform_scale == "raw_uv" else "trough-normalized overlays"


def _waveform_scale_description(waveform_scale: str) -> str:
    if waveform_scale == "raw_uv":
        return "raw best-PTP-channel templates.average in uV"
    return "raw best-PTP-channel templates.average, trough-normalized for shape overlay"


def _apply_robust_waveform_ylim(axis, arrays: list[np.ndarray], *, waveform_scale: str) -> None:
    if not arrays:
        return
    values = np.concatenate([np.asarray(array, dtype=float).ravel() for array in arrays])
    values = values[np.isfinite(values)]
    if values.size == 0:
        return
    low, high = np.nanpercentile(values, [1, 99])
    if waveform_scale == "normalized":
        low = min(float(low), -1.05)
        high = max(float(high), 0.75)
    else:
        low = float(low)
        high = float(high)
        if low < 0 < high:
            span = max(abs(low), abs(high))
            low, high = -span, span
    if high <= low:
        return
    pad = (high - low) * 0.08
    axis.set_ylim(low - pad, high + pad)


if __name__ == "__main__":
    main()
