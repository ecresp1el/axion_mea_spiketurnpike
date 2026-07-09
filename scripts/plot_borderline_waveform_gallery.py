#!/usr/bin/env python
"""Plot raw best-channel waveform galleries for current borderline units.

This exploratory visualization does not modify the production classifier. It
loads the current borderline-only subgroup assignments, reopens the corresponding
SortingAnalyzers, plots raw best-PTP-channel templates, and marks the existing
waveform landmarks so the 25 borderline units can be visually inspected before
any classifier change is considered.
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

from scripts.plot_lumos_candidate_waveform_gallery import (  # noqa: E402
    _measure_spiketurnpike_waveform_metrics,
)


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_DATE_LABEL = "20260709"
SORT_SPECS = [
    ("composite_non_ttp_rank", "Composite non-TTP rank", True),
    ("post_trough_rebound_slope_uV_per_ms", "Rebound slope, high to low", False),
    ("pre_trough_depolarization_slope_uV_per_ms", "Downstroke slope, most negative first", True),
    ("rep50_recovery_slope_uV_per_ms", "REP50 recovery slope, high to low", False),
    ("post_peak_amplitude_uV", "Post-peak amplitude, high to low", False),
    ("waveform_asymmetry", "Waveform asymmetry, high to low", False),
    ("spike_half_width_ms", "Half-width, narrow to broad", True),
]
CLUSTER_ORDER = {
    "FS_like_candidate": 0,
    "ambiguous_borderline": 1,
    "RS_like_candidate": 2,
}
CLUSTER_COLORS = {
    "FS_like_candidate": "#d55e00",
    "ambiguous_borderline": "#7a7a7a",
    "RS_like_candidate": "#0072b2",
}


@dataclass
class BorderlineWaveform:
    metadata: dict[str, object]
    time_ms: np.ndarray
    waveform_uV: np.ndarray
    metrics: dict[str, object]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--assignments-csv", type=Path)
    parser.add_argument("--rep-fraction", type=float, choices=(0.25, 0.5, 0.63), default=0.5)
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    import spikeinterface.full as si

    job_dir = args.job_dir.expanduser().resolve()
    assignments_csv = args.assignments_csv or job_dir / (
        f"borderline_waveform_substructure_non_ttp_{args.date_label}_unit_assignments.csv"
    )
    assignments = pd.read_csv(assignments_csv)
    assignments = _add_sort_scores(assignments)
    waveforms, errors = _load_waveforms(si, assignments, rep_fraction=args.rep_fraction)
    if not waveforms:
        raise SystemExit("No borderline waveforms could be loaded.")

    stem = f"borderline_waveform_gallery_{args.date_label}"
    overview_png = job_dir / f"{stem}_cluster_composite.png"
    pdf_path = job_dir / f"{stem}_sorted_by_non_ttp_features.pdf"
    sort_orders_csv = job_dir / f"{stem}_sort_orders.csv"
    provenance_json = job_dir / f"{stem}_provenance.json"
    error_path = job_dir / f"{stem}_errors.txt"

    _plot_gallery_page(
        plt,
        sorted(waveforms, key=lambda item: _sort_key(item, "composite_non_ttp_rank", ascending=True)),
        overview_png,
        title="Borderline units: raw best-channel waveforms sorted by exploratory cluster and composite non-TTP rank",
    )
    sort_rows = []
    with PdfPages(pdf_path) as pdf:
        for sort_name, sort_title, ascending in SORT_SPECS:
            ordered = sorted(waveforms, key=lambda item, name=sort_name, asc=ascending: _sort_key(item, name, asc))
            figure = _gallery_figure(
                plt,
                ordered,
                title=f"Borderline raw waveforms sorted by exploratory cluster and {sort_title}",
            )
            pdf.savefig(figure, bbox_inches="tight")
            plt.close(figure)
            for order_index, waveform in enumerate(ordered, start=1):
                sort_rows.append(
                    {
                        "sort_name": sort_name,
                        "sort_title": sort_title,
                        "sort_order": order_index,
                        "recording": waveform.metadata["recording"],
                        "well": waveform.metadata["well"],
                        "unit_id": waveform.metadata["unit_id"],
                        "borderline_exploratory_label": waveform.metadata["borderline_exploratory_label"],
                        "value": waveform.metadata.get(sort_name, np.nan),
                    }
                )
    pd.DataFrame(sort_rows).to_csv(sort_orders_csv, index=False)
    if errors:
        error_path.write_text("\n".join(errors) + "\n", encoding="utf-8")

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "assignments_csv": str(assignments_csv),
        "unit_count": len(waveforms),
        "cluster_counts": pd.Series([item.metadata["borderline_exploratory_label"] for item in waveforms]).value_counts().to_dict(),
        "sort_specs": [
            {"sort_name": name, "sort_title": title, "ascending": ascending}
            for name, title, ascending in SORT_SPECS
        ],
        "landmark_colors": {
            "pre_peak": "blue",
            "trough": "black",
            "rebound_peak": "orange",
            "rep_recovery": "green",
            "half_width": "red-orange",
        },
        "outputs": {
            "overview_png": str(overview_png),
            "sorted_pdf": str(pdf_path),
            "sort_orders_csv": str(sort_orders_csv),
        },
        "notes": [
            "Exploratory only; production TTP-based classifier is unchanged.",
            "Waveforms are raw best-PTP-channel templates.average traces in uV.",
            "TTP remains the primary classifier; this gallery is for visual inspection of borderline units only.",
        ],
        "errors": errors,
    }
    provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Assignments: {assignments_csv}")
    print(f"Borderline waveforms plotted: {len(waveforms)}")
    print(f"Overview PNG: {overview_png}")
    print(f"Sorted PDF: {pdf_path}")
    print(f"Sort orders CSV: {sort_orders_csv}")
    print(f"Provenance: {provenance_json}")
    if errors:
        print(f"Skipped {len(errors)} entries; details: {error_path}")


def _add_sort_scores(assignments: pd.DataFrame) -> pd.DataFrame:
    out = assignments.copy()
    rank_specs = [
        ("post_trough_rebound_slope_uV_per_ms", False),
        ("pre_trough_depolarization_slope_uV_per_ms", True),
        ("rep50_recovery_slope_uV_per_ms", False),
        ("post_peak_amplitude_uV", False),
        ("waveform_asymmetry", False),
        ("spike_half_width_ms", True),
    ]
    ranks = []
    for feature, ascending in rank_specs:
        values = pd.to_numeric(out[feature], errors="coerce")
        ranks.append(values.rank(ascending=ascending, method="average", na_option="bottom"))
    out["composite_non_ttp_rank"] = pd.concat(ranks, axis=1).mean(axis=1)
    return out


def _load_waveforms(si, assignments: pd.DataFrame, *, rep_fraction: float) -> tuple[list[BorderlineWaveform], list[str]]:
    waveforms: list[BorderlineWaveform] = []
    errors: list[str] = []
    for analyzer_path_text, group in assignments.groupby("analyzer_path", dropna=False):
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

        for _, row in group.iterrows():
            try:
                unit_index = int(row["unit_index"])
                template = np.asarray(templates[unit_index], dtype=float)
                channel_ptp = np.ptp(template, axis=0)
                best_channel_index = int(np.nanargmax(channel_ptp))
                waveform_uV = template[:, best_channel_index]
                nbefore = int(getattr(templates_ext, "nbefore", np.nanargmin(waveform_uV)))
                time_ms = (np.arange(waveform_uV.size) - nbefore) / sampling_frequency * 1000.0
                metrics = _measure_spiketurnpike_waveform_metrics(waveform_uV, time_ms, rep_fraction=rep_fraction)
                metadata = row.to_dict()
                metadata["best_channel_index_reloaded"] = best_channel_index
                metadata["template_reference_reloaded"] = (
                    f"templates.average[unit_index={unit_index},channel_index={best_channel_index}]"
                )
                waveforms.append(BorderlineWaveform(metadata=metadata, time_ms=time_ms, waveform_uV=waveform_uV, metrics=metrics))
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"{row.get('recording')} / {row.get('well')} unit={row.get('unit_id')}: "
                    f"{type(exc).__name__}: {exc}"
                )
    return waveforms, errors


def _templates_average(templates_ext) -> np.ndarray:
    try:
        return np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        templates_data = templates_ext.get_data()
        if isinstance(templates_data, dict):
            templates_data = templates_data.get("average")
        return np.asarray(templates_data, dtype=float)


def _sort_key(item: BorderlineWaveform, feature: str, ascending: bool) -> tuple[float, float, str, str, str]:
    cluster = str(item.metadata.get("borderline_exploratory_label", ""))
    value = _finite_sort_value(item.metadata.get(feature, np.nan))
    if not ascending and np.isfinite(value):
        value = -value
    return (
        CLUSTER_ORDER.get(cluster, 99),
        value,
        str(item.metadata.get("recording", "")),
        str(item.metadata.get("well", "")),
        str(item.metadata.get("unit_id", "")),
    )


def _finite_sort_value(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return np.inf
    return parsed if np.isfinite(parsed) else np.inf


def _plot_gallery_page(plt, waveforms: list[BorderlineWaveform], output_path: Path, *, title: str) -> None:
    figure = _gallery_figure(plt, waveforms, title=title)
    figure.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(figure)


def _gallery_figure(plt, waveforms: list[BorderlineWaveform], *, title: str):
    ncols = 5
    nrows = int(np.ceil(len(waveforms) / ncols))
    figure, axes = plt.subplots(nrows, ncols, figsize=(3.45 * ncols, 2.9 * nrows), squeeze=False, sharex=True)
    max_abs = max(float(np.nanmax(np.abs(item.waveform_uV))) for item in waveforms)
    y_limit = max(max_abs * 1.12, 1.0)
    for axis, waveform in zip(axes.ravel(), waveforms, strict=False):
        _plot_one_waveform(axis, waveform, y_limit)
    for axis in axes.ravel()[len(waveforms) :]:
        axis.axis("off")
    _add_legend(figure)
    figure.suptitle(title, y=0.995, fontsize=14)
    figure.tight_layout(rect=(0, 0, 1, 0.965))
    return figure


def _plot_one_waveform(axis, waveform: BorderlineWaveform, y_limit: float) -> None:
    metadata = waveform.metadata
    label = str(metadata.get("borderline_exploratory_label", ""))
    cluster_color = CLUSTER_COLORS.get(label, "#444444")
    axis.axhline(0, color="0.84", linewidth=0.7, zorder=0)
    axis.plot(waveform.time_ms, waveform.waveform_uV, color="black", linewidth=1.45)
    _scatter_landmarks(axis, waveform)
    axis.set_ylim(-y_limit, y_limit)
    axis.tick_params(axis="both", labelsize=7, length=2)
    for spine in axis.spines.values():
        spine.set_linewidth(1.25)
        spine.set_edgecolor(cluster_color)
    title = (
        f"{metadata.get('well')} u{metadata.get('unit_id')} {label.replace('_candidate', '')}\n"
        f"TTP {metadata.get('trough_to_peak_duration_ms'):.2f} REP {metadata.get('repolarization_time_ms'):.2f} "
        f"HW {metadata.get('spike_half_width_ms'):.2f}\n"
        f"reb {metadata.get('post_trough_rebound_slope_uV_per_ms'):.1f} "
        f"down {metadata.get('pre_trough_depolarization_slope_uV_per_ms'):.1f} "
        f"asym {metadata.get('waveform_asymmetry'):.2f}"
    )
    axis.set_title(title, fontsize=7.2)


def _scatter_landmarks(axis, waveform: BorderlineWaveform) -> None:
    specs = [
        ("pre_peak_index", "#0072b2", "white", 22),
        ("trough_index", "black", "white", 24),
        ("rebound_peak_index", "#e69f00", "black", 22),
        ("rep_recovery_index", "#009e73", "white", 24),
        ("half_width_start_index", "#d55e00", "white", 19),
        ("half_width_end_index", "#d55e00", "white", 19),
    ]
    for key, facecolor, edgecolor, size in specs:
        index = int(waveform.metrics.get(key, -1))
        if index < 0 or index >= waveform.waveform_uV.size:
            continue
        axis.scatter(
            [waveform.time_ms[index]],
            [waveform.waveform_uV[index]],
            color=facecolor,
            edgecolor=edgecolor,
            linewidth=0.5,
            s=size,
            zorder=5,
        )


def _add_legend(figure) -> None:
    legend_items = [
        ("blue pre-peak", "#0072b2"),
        ("black trough", "black"),
        ("orange rebound peak", "#e69f00"),
        ("green REP50 recovery", "#009e73"),
        ("red-orange half-width", "#d55e00"),
    ]
    x = 0.16
    y = 0.972
    for label, color in legend_items:
        figure.text(x, y, label, ha="left", va="center", fontsize=9, color=color, fontweight="bold")
        x += 0.15


if __name__ == "__main__":
    main()
