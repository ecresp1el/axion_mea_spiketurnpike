#!/usr/bin/env python
"""Visual overlay gallery for original vs local-excursion width metrics.

This script is intentionally visual-only. It loads good-unit best-channel raw
waveforms and overlays both half-width/REP50 definitions on each trace:

1. Original baseline-referenced half-width/REP50, using half the trough depth
   relative to zero.
2. Local-excursion half-width/REP50, using the midpoint between Peak1 and the
   trough.

No clustering, model fitting, feature ranking, or classifier changes are made.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_DATE_LABEL = "20260709"
CLASS_ORDER = {"FS_like": 0, "borderline": 1, "RS_like": 2}
CLASS_COLORS = {"FS_like": "#d55e00", "borderline": "#707070", "RS_like": "#0072b2"}
ORIGINAL_COLOR = "#7b3294"
LOCAL_COLOR = "#008837"
ORIGINAL_REP_COLOR = "#c51b7d"
LOCAL_REP_COLOR = "#01665e"
PRE_PEAK_COLOR = "#56b4e9"
TROUGH_COLOR = "#111111"
REBOUND_COLOR = "#e69f00"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--input-csv", type=Path)
    parser.add_argument("--all-units-per-page", type=int, default=20)
    parser.add_argument("--exemplars-per-class", type=int, default=12)
    parser.add_argument(
        "--order-by",
        choices=("prepeak_ratio", "ttp", "well"),
        default="prepeak_ratio",
        help="Visual ordering within FS_like/borderline/RS_like groups; not used for statistics.",
    )
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    job_dir = args.job_dir.expanduser().resolve()
    input_csv = args.input_csv or job_dir / f"local_excursion_halfwidth_rep_comparison_{args.date_label}.csv"
    table = pd.read_csv(input_csv)
    table = _prepare_table(table, order_by=args.order_by)
    units = [_row_to_unit(row) for _, row in table.iterrows()]
    if not units:
        raise SystemExit("No good-unit waveform rows found.")

    stem = f"good_unit_halfwidth_rep_definition_overlay_gallery_{args.date_label}"
    all_pdf = job_dir / f"{stem}_all_good_units.pdf"
    exemplar_png = job_dir / f"{stem}_exemplars.png"
    exemplar_pdf = job_dir / f"{stem}_exemplars.pdf"
    manifest_csv = job_dir / f"{stem}_manifest.csv"
    provenance_json = job_dir / f"{stem}_provenance.json"

    _write_all_units_pdf(plt, units, all_pdf, units_per_page=args.all_units_per_page)
    exemplars = _select_exemplars(table, per_class=args.exemplars_per_class)
    exemplar_units = [_row_to_unit(row) for _, row in exemplars.iterrows()]
    figure = _gallery_figure(
        plt,
        exemplar_units,
        title=(
            "Good-unit exemplars: original baseline-referenced vs local-excursion "
            "half-width and REP50"
        ),
        ncols=6,
    )
    figure.savefig(exemplar_png, dpi=240, bbox_inches="tight")
    figure.savefig(exemplar_pdf, bbox_inches="tight")
    plt.close(figure)

    manifest = table[
        [
            "recording",
            "well",
            "unit_id",
            "rs_fs_classification",
            "trough_to_peak_duration_ms",
            "pre_peak_to_trough_ratio_uV",
            "current_half_width_ms",
            "local_half_width_ms",
            "current_rep50_ms",
            "local_rep50_ms",
            "analyzer_path",
            "best_channel_index",
        ]
    ].copy()
    manifest["visual_order"] = np.arange(1, len(manifest) + 1)
    manifest.to_csv(manifest_csv, index=False)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "input_csv": str(input_csv),
        "unit_count": int(len(table)),
        "classes_present": table["rs_fs_classification"].astype(str).drop_duplicates().tolist(),
        "visual_order": args.order_by,
        "outputs": {
            "all_good_units_pdf": str(all_pdf),
            "exemplar_png": str(exemplar_png),
            "exemplar_pdf": str(exemplar_pdf),
            "manifest_csv": str(manifest_csv),
        },
        "waveform_source": (
            "Raw best peak-to-peak channel from templates.average for each KSLabel=good unit; "
            "waveform arrays and landmark indices loaded from the local_excursion comparison cache."
        ),
        "overlay_colors": {
            "original_half_width_anchors": ORIGINAL_COLOR,
            "local_half_width_anchors": LOCAL_COLOR,
            "original_rep50_point": ORIGINAL_REP_COLOR,
            "local_rep50_point": LOCAL_REP_COLOR,
            "pre_peak": PRE_PEAK_COLOR,
            "trough": TROUGH_COLOR,
            "rebound_peak": REBOUND_COLOR,
        },
        "notes": [
            "Visual validation only; no statistical analyses, clustering, feature rankings, or classifier changes.",
            "Original half-width/REP50 use half the trough depth relative to zero.",
            "Local-excursion half-width/REP50 use the midpoint between Peak1 and trough.",
            "Measured values are annotated directly in each waveform panel.",
        ],
    }
    provenance_json.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(f"Input cache: {input_csv}")
    print(f"Good units plotted: {len(units)}")
    print(f"All-good-unit PDF: {all_pdf}")
    print(f"Exemplar PNG: {exemplar_png}")
    print(f"Exemplar PDF: {exemplar_pdf}")
    print(f"Manifest CSV: {manifest_csv}")
    print(f"Provenance: {provenance_json}")


def _prepare_table(table: pd.DataFrame, *, order_by: str) -> pd.DataFrame:
    out = table.copy()
    numeric_columns = [
        "trough_to_peak_duration_ms",
        "pre_peak_to_trough_ratio_uV",
        "current_half_width_ms",
        "local_half_width_ms",
        "current_rep50_ms",
        "local_rep50_ms",
        "best_channel_index",
    ]
    for column in numeric_columns:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    out["class_order"] = out["rs_fs_classification"].map(CLASS_ORDER).fillna(99)
    if order_by == "prepeak_ratio":
        out["within_class_order"] = -out["pre_peak_to_trough_ratio_uV"].replace([np.inf, -np.inf], np.nan)
    elif order_by == "ttp":
        out["within_class_order"] = out["trough_to_peak_duration_ms"].replace([np.inf, -np.inf], np.nan)
    else:
        out["within_class_order"] = 0.0
    out["within_class_order"] = out["within_class_order"].fillna(np.inf)
    return out.sort_values(
        ["class_order", "within_class_order", "recording", "well", "unit_id"],
        kind="mergesort",
    ).reset_index(drop=True)


def _select_exemplars(table: pd.DataFrame, *, per_class: int) -> pd.DataFrame:
    if per_class <= 0:
        return table.iloc[0:0].copy()
    parts = []
    for label in ["FS_like", "borderline", "RS_like"]:
        subset = table.loc[table["rs_fs_classification"].eq(label)].copy()
        parts.append(subset.head(per_class))
    return pd.concat(parts, ignore_index=True)


def _row_to_unit(row: pd.Series) -> dict[str, object]:
    return {
        "metadata": row.to_dict(),
        "time_ms": np.asarray(json.loads(row["waveform_time_ms_json"]), dtype=float),
        "waveform_uV": np.asarray(json.loads(row["waveform_uV_json"]), dtype=float),
    }


def _write_all_units_pdf(plt, units: list[dict[str, object]], output_path: Path, *, units_per_page: int) -> None:
    units_per_page = max(1, int(units_per_page))
    with PdfPages(output_path) as pdf:
        page_count = int(math.ceil(len(units) / units_per_page))
        for page_index in range(page_count):
            start = page_index * units_per_page
            page_units = units[start : start + units_per_page]
            figure = _gallery_figure(
                plt,
                page_units,
                title=(
                    "Good units: original baseline-referenced vs local-excursion "
                    f"half-width/REP50, page {page_index + 1} of {page_count}"
                ),
                ncols=5,
            )
            pdf.savefig(figure, bbox_inches="tight")
            plt.close(figure)


def _gallery_figure(plt, units: list[dict[str, object]], *, title: str, ncols: int):
    ncols = max(1, min(ncols, len(units)))
    nrows = int(math.ceil(len(units) / ncols))
    figure, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(3.75 * ncols, 3.35 * nrows),
        squeeze=False,
        sharex=True,
    )
    max_abs = max(_finite_absmax(unit["waveform_uV"]) for unit in units)
    y_limit = max(max_abs * 1.12, 1.0)
    for axis, unit in zip(axes.ravel(), units, strict=False):
        _plot_unit(axis, unit, y_limit=y_limit)
    for axis in axes.ravel()[len(units) :]:
        axis.axis("off")
    _add_legend(figure)
    figure.suptitle(title, y=0.997, fontsize=14)
    figure.tight_layout(rect=(0, 0, 1, 0.955))
    return figure


def _plot_unit(axis, unit: dict[str, object], *, y_limit: float) -> None:
    row = unit["metadata"]
    time_ms = unit["time_ms"]
    waveform = unit["waveform_uV"]
    label = str(row.get("rs_fs_classification", ""))
    class_color = CLASS_COLORS.get(label, "#444444")
    trough_index = _index(row, "trough_index", waveform)
    trough_time = float(time_ms[trough_index]) if trough_index >= 0 else np.nan

    axis.axhline(0, color="0.84", linewidth=0.75, zorder=0)
    axis.plot(time_ms, waveform, color="black", linewidth=1.35, zorder=2)
    _draw_half_width(axis, time_ms, waveform, row, prefix="current", color=ORIGINAL_COLOR, marker="o")
    _draw_half_width(axis, time_ms, waveform, row, prefix="local", color=LOCAL_COLOR, marker="s")
    _draw_rep50(
        axis,
        row,
        trough_time=trough_time,
        threshold=float(row["trough_value_uV"]) * 0.5,
        metric_key="current_rep50_ms",
        color=ORIGINAL_REP_COLOR,
        marker="X",
        label_y=0.94,
    )
    _draw_rep50(
        axis,
        row,
        trough_time=trough_time,
        threshold=float(row["local_midpoint_uV"]),
        metric_key="local_rep50_ms",
        color=LOCAL_REP_COLOR,
        marker="D",
        label_y=0.86,
    )
    _scatter_landmark(axis, time_ms, waveform, row, "pre_peak_index", PRE_PEAK_COLOR, "^")
    _scatter_landmark(axis, time_ms, waveform, row, "trough_index", TROUGH_COLOR, "v")
    _scatter_landmark(axis, time_ms, waveform, row, "rebound_peak_index", REBOUND_COLOR, "^")

    axis.set_ylim(-y_limit, y_limit)
    axis.tick_params(axis="both", labelsize=7, length=2)
    for spine in axis.spines.values():
        spine.set_linewidth(1.15)
        spine.set_edgecolor(class_color)
    axis.set_title(_panel_title(row), fontsize=7.2)


def _draw_half_width(axis, time_ms: np.ndarray, waveform: np.ndarray, row: dict[str, object], *, prefix: str, color: str, marker: str) -> None:
    start_index = _index(row, f"{prefix}_half_width_start_index", waveform)
    end_index = _index(row, f"{prefix}_half_width_end_index", waveform)
    if start_index < 0 or end_index < 0:
        return
    if prefix == "current":
        level = float(row["trough_value_uV"]) * 0.5
    else:
        level = float(row["local_midpoint_uV"])
    axis.hlines(
        level,
        float(time_ms[start_index]),
        float(time_ms[end_index]),
        color=color,
        linewidth=2.0,
        zorder=4,
    )
    axis.scatter(
        [time_ms[start_index], time_ms[end_index]],
        [waveform[start_index], waveform[end_index]],
        color=color,
        edgecolor="white",
        linewidth=0.55,
        s=30,
        marker=marker,
        zorder=6,
    )
    axis.vlines(
        [time_ms[start_index], time_ms[end_index]],
        ymin=min(level, np.nanmin(waveform)),
        ymax=max(level, np.nanmax(waveform)),
        color=color,
        linewidth=0.55,
        alpha=0.25,
        zorder=1,
    )


def _draw_rep50(
    axis,
    row: dict[str, object],
    *,
    trough_time: float,
    threshold: float,
    metric_key: str,
    color: str,
    marker: str,
    label_y: float,
) -> None:
    rep_ms = _finite_float(row.get(metric_key))
    if not np.isfinite(rep_ms) or not np.isfinite(trough_time) or not np.isfinite(threshold):
        return
    rep_time = trough_time + rep_ms
    axis.scatter(
        [rep_time],
        [threshold],
        color=color,
        edgecolor="white",
        linewidth=0.6,
        s=42,
        marker=marker,
        zorder=7,
    )
    axis.axvline(rep_time, color=color, linewidth=0.65, alpha=0.25, zorder=1)
    axis.text(
        0.02,
        label_y,
        _metric_label(metric_key, rep_ms),
        transform=axis.transAxes,
        color=color,
        fontsize=6.7,
        fontweight="bold",
        ha="left",
        va="top",
    )


def _scatter_landmark(axis, time_ms: np.ndarray, waveform: np.ndarray, row: dict[str, object], key: str, color: str, marker: str) -> None:
    index = _index(row, key, waveform)
    if index < 0:
        return
    axis.scatter(
        [time_ms[index]],
        [waveform[index]],
        color=color,
        edgecolor="white",
        linewidth=0.5,
        s=26,
        marker=marker,
        zorder=5,
    )


def _panel_title(row: dict[str, object]) -> str:
    return (
        f"{row.get('well')} u{row.get('unit_id')} {row.get('rs_fs_classification')}\n"
        f"TTP {float(row['trough_to_peak_duration_ms']):.2f} ms  "
        f"P1/tr {float(row['pre_peak_to_trough_ratio_uV']):.2f}\n"
        f"HW orig/local { _fmt(row.get('current_half_width_ms')) }/{ _fmt(row.get('local_half_width_ms')) } ms  "
        f"REP { _fmt(row.get('current_rep50_ms')) }/{ _fmt(row.get('local_rep50_ms')) } ms"
    )


def _metric_label(metric_key: str, value: float) -> str:
    if metric_key == "current_rep50_ms":
        return f"orig REP50 {value:.3f} ms"
    return f"local REP50 {value:.3f} ms"


def _fmt(value: object) -> str:
    number = _finite_float(value)
    return f"{number:.2f}" if np.isfinite(number) else "nan"


def _index(row: dict[str, object], key: str, waveform: np.ndarray) -> int:
    try:
        index = int(row.get(key, -1))
    except (TypeError, ValueError):
        return -1
    return index if 0 <= index < waveform.size else -1


def _finite_float(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return np.nan
    return number if np.isfinite(number) else np.nan


def _finite_absmax(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 1.0
    return float(np.nanmax(np.abs(finite)))


def _add_legend(figure) -> None:
    legend_items = [
        ("orig half-width anchors", ORIGINAL_COLOR),
        ("local half-width anchors", LOCAL_COLOR),
        ("orig REP50", ORIGINAL_REP_COLOR),
        ("local REP50", LOCAL_REP_COLOR),
        ("Peak1 / trough / rebound", TROUGH_COLOR),
    ]
    x = 0.09
    y = 0.973
    for label, color in legend_items:
        figure.text(x, y, label, ha="left", va="center", fontsize=8.6, color=color, fontweight="bold")
        x += 0.18


if __name__ == "__main__":
    main()
