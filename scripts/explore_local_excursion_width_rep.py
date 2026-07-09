#!/usr/bin/env python
"""Compare current trough-depth and local-excursion half-width/REP metrics.

This is an exploratory metric audit. It does not replace existing waveform
metrics. For each current KSLabel=good unit, it recomputes the raw best-channel
template waveform and reports:

1. Current SpikeTurnpike-style half-width: half the trough depth relative to zero.
2. Local-excursion half-width: midpoint between Peak1 and trough.
3. Current REP50: trough recovery to 50% of trough depth relative to zero.
4. Local-excursion REP50: trough recovery to midpoint between Peak1 and trough.

The goal is to see whether local-excursion measurements behave better for
borderline units with large pre-peaks.
"""

from __future__ import annotations

import argparse
import json
import sys
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

from scripts.plot_lumos_candidate_waveform_gallery import (  # noqa: E402
    _measure_spiketurnpike_waveform_metrics,
)


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_DATE_LABEL = "20260709"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--input-csv", type=Path)
    parser.add_argument("--rep-fraction", type=float, choices=(0.25, 0.5, 0.63), default=0.5)
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import spikeinterface.full as si

    job_dir = args.job_dir.expanduser().resolve()
    input_csv = args.input_csv or job_dir / (
        f"good_kslabel_ttp_distribution_template_best_ptp_{args.date_label}.csv"
    )
    source = pd.read_csv(input_csv)
    rows, errors = _extract_comparison_rows(si, source, rep_fraction=args.rep_fraction)
    if not rows:
        raise SystemExit("No metric comparison rows could be computed.")

    table = pd.DataFrame(rows)
    stem = f"local_excursion_halfwidth_rep_comparison_{args.date_label}"
    comparison_csv = job_dir / f"{stem}.csv"
    summary_csv = job_dir / f"{stem}_summary.csv"
    plot_png = job_dir / f"{stem}.png"
    borderline_png = job_dir / f"{stem}_borderline_large_prepeak_waveforms.png"
    provenance_json = job_dir / f"{stem}_provenance.json"
    error_path = job_dir / f"{stem}_errors.txt"

    table.to_csv(comparison_csv, index=False)
    summary = _summary_table(table)
    summary.to_csv(summary_csv, index=False)
    _plot_comparison(plt, table, plot_png)
    _plot_borderline_large_prepeak_waveforms(plt, table, borderline_png)
    if errors:
        error_path.write_text("\n".join(errors) + "\n", encoding="utf-8")
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "input_csv": str(input_csv),
        "unit_count": int(len(table)),
        "borderline_count": int(table["rs_fs_classification"].eq("borderline").sum()),
        "rep_fraction": args.rep_fraction,
        "outputs": {
            "comparison_csv": str(comparison_csv),
            "summary_csv": str(summary_csv),
            "comparison_plot": str(plot_png),
            "borderline_large_prepeak_plot": str(borderline_png),
        },
        "notes": [
            "Exploratory only; current half-width and REP metrics are unchanged.",
            "Current half-width/REP50 use trough depth relative to zero.",
            "Local-excursion half-width/REP50 use the midpoint between Peak1 and trough.",
        ],
        "errors": errors,
    }
    provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Input: {input_csv}")
    print(f"Units analyzed: {len(table)}")
    print(f"Borderline units: {table['rs_fs_classification'].eq('borderline').sum()}")
    print(f"Comparison CSV: {comparison_csv}")
    print(f"Summary CSV: {summary_csv}")
    print(f"Comparison plot: {plot_png}")
    print(f"Borderline large-prepeak plot: {borderline_png}")
    print(f"Provenance: {provenance_json}")
    if errors:
        print(f"Skipped {len(errors)} entries; details: {error_path}")
    print("\nSummary:")
    print(summary.to_string(index=False))
    print("\nLargest borderline changes:")
    cols = [
        "recording",
        "well",
        "unit_id",
        "pre_peak_to_trough_ratio_uV",
        "current_half_width_ms",
        "local_half_width_ms",
        "half_width_delta_ms",
        "current_rep50_ms",
        "local_rep50_ms",
        "rep50_delta_ms",
    ]
    borderline = table.loc[table["rs_fs_classification"].eq("borderline")].copy()
    borderline["abs_total_delta"] = borderline["half_width_delta_ms"].abs() + borderline["rep50_delta_ms"].abs()
    print(borderline.sort_values("abs_total_delta", ascending=False)[cols].head(12).to_string(index=False))


def _extract_comparison_rows(si, source: pd.DataFrame, *, rep_fraction: float) -> tuple[list[dict[str, object]], list[str]]:
    rows: list[dict[str, object]] = []
    errors: list[str] = []
    for analyzer_path_text, group in source.groupby("analyzer_path", dropna=False):
        analyzer_path = Path(str(analyzer_path_text))
        try:
            analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
            templates_ext = analyzer.get_extension("templates")
            if templates_ext is None:
                raise ValueError("missing templates extension")
            templates = _templates_average(templates_ext)
            sampling_frequency = float(analyzer.recording.get_sampling_frequency())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{analyzer_path}: {type(exc).__name__}: {exc}")
            continue

        for _, source_row in group.iterrows():
            try:
                unit_index = int(source_row["unit_index"])
                template = np.asarray(templates[unit_index], dtype=float)
                best_channel_index = int(np.nanargmax(np.ptp(template, axis=0)))
                waveform = template[:, best_channel_index]
                nbefore = int(getattr(templates_ext, "nbefore", np.nanargmin(waveform)))
                time_ms = (np.arange(waveform.size) - nbefore) / sampling_frequency * 1000.0
                current = _measure_spiketurnpike_waveform_metrics(waveform, time_ms, rep_fraction=rep_fraction)
                local = _measure_local_excursion_metrics(waveform, time_ms, current)
                row = {
                    "recording": source_row["recording"],
                    "well": source_row["well"],
                    "unit_id": source_row["unit_id"],
                    "unit_index": unit_index,
                    "KSLabel": source_row["KSLabel"],
                    "rs_fs_classification": source_row["rs_fs_classification"],
                    "analyzer_path": str(analyzer_path),
                    "best_channel_index": best_channel_index,
                    "trough_to_peak_duration_ms": current["trough_to_peak_duration_ms"],
                    "pre_peak_index": current["pre_peak_index"],
                    "trough_index": current["trough_index"],
                    "rebound_peak_index": current["rebound_peak_index"],
                    "pre_peak_value_uV": current["pre_peak_value_uV"],
                    "trough_value_uV": float(waveform[int(current["trough_index"])]),
                    "post_peak_value_uV": current["post_peak_value_uV"],
                    "current_half_width_ms": current["spike_half_width_ms"],
                    "current_half_width_start_index": current["half_width_start_index"],
                    "current_half_width_end_index": current["half_width_end_index"],
                    "current_rep50_ms": current["repolarization_time_ms"],
                    "current_rep50_index": current["rep_recovery_index"],
                    "local_half_width_ms": local["local_half_width_ms"],
                    "local_half_width_start_index": local["local_half_width_start_index"],
                    "local_half_width_end_index": local["local_half_width_end_index"],
                    "local_rep50_ms": local["local_rep50_ms"],
                    "local_rep50_index": local["local_rep50_index"],
                    "local_midpoint_uV": local["local_midpoint_uV"],
                    "pre_peak_to_trough_excursion_uV": local["pre_peak_to_trough_excursion_uV"],
                    "pre_peak_to_trough_ratio_uV": local["pre_peak_to_trough_ratio_uV"],
                    "waveform_time_ms_json": json.dumps(time_ms.tolist()),
                    "waveform_uV_json": json.dumps(waveform.astype(float).tolist()),
                }
                row["half_width_delta_ms"] = row["local_half_width_ms"] - row["current_half_width_ms"]
                row["rep50_delta_ms"] = row["local_rep50_ms"] - row["current_rep50_ms"]
                rows.append(row)
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"{source_row.get('recording')} / {source_row.get('well')} unit={source_row.get('unit_id')}: "
                    f"{type(exc).__name__}: {exc}"
                )
    return rows, errors


def _templates_average(templates_ext) -> np.ndarray:
    try:
        return np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        templates_data = templates_ext.get_data()
        if isinstance(templates_data, dict):
            templates_data = templates_data.get("average")
        return np.asarray(templates_data, dtype=float)


def _measure_local_excursion_metrics(waveform: np.ndarray, time_ms: np.ndarray, current: dict[str, object]) -> dict[str, object]:
    pre_peak_index = int(current["pre_peak_index"])
    trough_index = int(current["trough_index"])
    rebound_peak_index = int(current["rebound_peak_index"])
    if pre_peak_index < 0 or trough_index < 0 or rebound_peak_index < 0:
        return _empty_local_metrics()
    pre_peak_value = float(waveform[pre_peak_index])
    trough_value = float(waveform[trough_index])
    local_midpoint = (pre_peak_value + trough_value) / 2.0
    left_index = _closest_index(waveform, pre_peak_index, trough_index, local_midpoint)
    right_index = _first_crossing_index(waveform, trough_index, rebound_peak_index, local_midpoint)
    local_rep_index = _first_crossing_index(waveform, trough_index, waveform.size - 1, local_midpoint)
    local_rep_time = _interpolated_crossing_time(waveform, time_ms, trough_index, local_rep_index, local_midpoint)
    return {
        "local_midpoint_uV": local_midpoint,
        "pre_peak_to_trough_excursion_uV": pre_peak_value - trough_value,
        "pre_peak_to_trough_ratio_uV": abs(pre_peak_value) / abs(trough_value) if trough_value != 0 else np.nan,
        "local_half_width_start_index": left_index,
        "local_half_width_end_index": right_index,
        "local_half_width_ms": float(time_ms[right_index] - time_ms[left_index])
        if left_index >= 0 and right_index >= 0
        else np.nan,
        "local_rep50_index": local_rep_index,
        "local_rep50_ms": local_rep_time - float(time_ms[trough_index]) if np.isfinite(local_rep_time) else np.nan,
    }


def _empty_local_metrics() -> dict[str, object]:
    return {
        "local_midpoint_uV": np.nan,
        "pre_peak_to_trough_excursion_uV": np.nan,
        "pre_peak_to_trough_ratio_uV": np.nan,
        "local_half_width_start_index": -1,
        "local_half_width_end_index": -1,
        "local_half_width_ms": np.nan,
        "local_rep50_index": -1,
        "local_rep50_ms": np.nan,
    }


def _closest_index(waveform: np.ndarray, start: int, end: int, value: float) -> int:
    if start < 0 or end < start:
        return -1
    segment = waveform[start : end + 1]
    if segment.size == 0:
        return -1
    return start + int(np.nanargmin(np.abs(segment - value)))


def _first_crossing_index(waveform: np.ndarray, start: int, end: int, value: float) -> int:
    if start < 0 or end < start:
        return -1
    segment = waveform[start : end + 1]
    offsets = np.flatnonzero(segment >= value)
    if offsets.size == 0:
        return -1
    return start + int(offsets[0])


def _interpolated_crossing_time(waveform: np.ndarray, time_ms: np.ndarray, trough_index: int, crossing_index: int, value: float) -> float:
    if crossing_index < 0:
        return np.nan
    if crossing_index <= trough_index:
        return float(time_ms[crossing_index])
    previous_index = crossing_index - 1
    previous_value = float(waveform[previous_index])
    crossing_value = float(waveform[crossing_index])
    if crossing_value == previous_value:
        return float(time_ms[crossing_index])
    fraction = (value - previous_value) / (crossing_value - previous_value)
    fraction = float(np.clip(fraction, 0.0, 1.0))
    return float(time_ms[previous_index] + fraction * (time_ms[crossing_index] - time_ms[previous_index]))


def _summary_table(table: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for label, subset in [("all", table)] + list(table.groupby("rs_fs_classification", dropna=False)):
        for metric in ["half_width_delta_ms", "rep50_delta_ms", "pre_peak_to_trough_ratio_uV"]:
            values = pd.to_numeric(subset[metric], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
            rows.append(
                {
                    "group": label,
                    "metric": metric,
                    "count": int(values.size),
                    "median": float(values.median()) if not values.empty else np.nan,
                    "mean": float(values.mean()) if not values.empty else np.nan,
                    "min": float(values.min()) if not values.empty else np.nan,
                    "max": float(values.max()) if not values.empty else np.nan,
                }
            )
    return pd.DataFrame(rows)


def _plot_comparison(plt, table: pd.DataFrame, output_path: Path) -> None:
    colors = {"FS_like": "#d55e00", "borderline": "#7a7a7a", "RS_like": "#0072b2"}
    fig, axes = plt.subplots(2, 3, figsize=(15.5, 8.8))
    panels = [
        ("current_half_width_ms", "local_half_width_ms", "Half-width current vs local"),
        ("current_rep50_ms", "local_rep50_ms", "REP50 current vs local"),
        ("pre_peak_to_trough_ratio_uV", "half_width_delta_ms", "Half-width change vs pre-peak/trough"),
        ("pre_peak_to_trough_ratio_uV", "rep50_delta_ms", "REP50 change vs pre-peak/trough"),
        ("trough_to_peak_duration_ms", "half_width_delta_ms", "Half-width change vs TTP"),
        ("trough_to_peak_duration_ms", "rep50_delta_ms", "REP50 change vs TTP"),
    ]
    for axis, (x_col, y_col, title) in zip(axes.ravel(), panels, strict=True):
        for label, subset in table.groupby("rs_fs_classification", dropna=False):
            axis.scatter(
                subset[x_col],
                subset[y_col],
                s=24,
                alpha=0.78,
                linewidths=0,
                color=colors.get(label, "#444444"),
                label=str(label),
            )
        if x_col.startswith("current"):
            finite = table[[x_col, y_col]].replace([np.inf, -np.inf], np.nan).dropna()
            if not finite.empty:
                low = float(finite.min().min())
                high = float(finite.max().max())
                axis.plot([low, high], [low, high], color="0.25", linestyle="--", linewidth=1.0)
        axis.axhline(0, color="0.82", linewidth=0.8, zorder=0)
        axis.set_xlabel(_short_label(x_col))
        axis.set_ylabel(_short_label(y_col))
        axis.set_title(title)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="upper center", ncol=3)
    fig.suptitle("Current vs local-excursion half-width and REP50 metrics", y=0.995, fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_borderline_large_prepeak_waveforms(plt, table: pd.DataFrame, output_path: Path) -> None:
    borderline = table.loc[table["rs_fs_classification"].eq("borderline")].copy()
    if borderline.empty:
        return
    borderline = borderline.sort_values("pre_peak_to_trough_ratio_uV", ascending=False).head(12)
    ncols = 4
    nrows = int(np.ceil(len(borderline) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.25 * ncols, 3.45 * nrows), squeeze=False, sharex=True)
    for axis, (_, row) in zip(axes.ravel(), borderline.iterrows(), strict=False):
        time_ms = np.asarray(json.loads(row["waveform_time_ms_json"]), dtype=float)
        waveform = np.asarray(json.loads(row["waveform_uV_json"]), dtype=float)
        axis.axhline(0, color="0.84", linewidth=0.8)
        axis.plot(time_ms, waveform, color="black", linewidth=1.6)
        _scatter_indices(axis, time_ms, waveform, row)
        axis.axhline(row["local_midpoint_uV"], color="#009e73", linestyle=":", linewidth=1.0)
        current_level = row["trough_value_uV"] * 0.5
        axis.axhline(current_level, color="#d55e00", linestyle=":", linewidth=1.0)
        axis.set_title(
            f"{row['well']} u{row['unit_id']} ratio {row['pre_peak_to_trough_ratio_uV']:.2f}\n"
            f"HW cur/local {row['current_half_width_ms']:.2f}/{row['local_half_width_ms']:.2f} "
            f"REP {row['current_rep50_ms']:.2f}/{row['local_rep50_ms']:.2f}",
            fontsize=8,
        )
        axis.tick_params(labelsize=8, length=2)
    for axis in axes.ravel()[len(borderline) :]:
        axis.axis("off")
    fig.suptitle("Borderline units with largest pre-peak/trough ratios: current vs local midpoint levels", y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _scatter_indices(axis, time_ms: np.ndarray, waveform: np.ndarray, row: pd.Series) -> None:
    specs = [
        ("pre_peak_index", "#0072b2"),
        ("trough_index", "black"),
        ("rebound_peak_index", "#e69f00"),
        ("current_half_width_start_index", "#d55e00"),
        ("current_half_width_end_index", "#d55e00"),
        ("local_half_width_start_index", "#009e73"),
        ("local_half_width_end_index", "#009e73"),
        ("local_rep50_index", "#009e73"),
    ]
    for key, color in specs:
        index = int(row[key])
        if index < 0 or index >= waveform.size:
            continue
        axis.scatter([time_ms[index]], [waveform[index]], color=color, edgecolor="white", linewidth=0.5, s=26, zorder=5)


def _short_label(name: str) -> str:
    return {
        "current_half_width_ms": "current half-width ms",
        "local_half_width_ms": "local half-width ms",
        "current_rep50_ms": "current REP50 ms",
        "local_rep50_ms": "local REP50 ms",
        "half_width_delta_ms": "local-current half-width ms",
        "rep50_delta_ms": "local-current REP50 ms",
        "pre_peak_to_trough_ratio_uV": "|Peak1|/|trough|",
        "trough_to_peak_duration_ms": "TTP ms",
    }.get(name, name.replace("_", " "))


if __name__ == "__main__":
    main()
