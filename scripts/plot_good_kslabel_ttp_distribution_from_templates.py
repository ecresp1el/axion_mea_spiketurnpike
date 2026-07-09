#!/usr/bin/env python
"""Plot TTP for current KSLabel=good units using candidate-gallery waveform logic.

This intentionally does not read the older canonical master waveform table. It
loads current Step 1 SortingAnalyzers, extracts templates.average, selects the
best peak-to-peak template channel, and measures trough-to-post-trough-peak time
with the same landmark logic used by plot_lumos_candidate_waveform_gallery.py.
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

from axion_mea.rs_fs_classification import RSFSClassificationConfig  # noqa: E402
from scripts.launch_step1_sorting_analyzer_browser import DEFAULT_AIND_RESULTS_ROOT  # noqa: E402
from scripts.plot_lumos_candidate_waveform_gallery import (  # noqa: E402
    _measure_spiketurnpike_waveform_metrics,
)


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
RECORDING_NAME = "block0_None_recording1.zarr"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_AIND_RESULTS_ROOT)
    parser.add_argument("--date-label", default="20260709")
    parser.add_argument("--plate-family", default="all", help="Use 'all' or an exact plate_family value.")
    parser.add_argument("--kslabel", default="good")
    parser.add_argument("--rep-fraction", type=float, choices=(0.25, 0.5, 0.63), default=0.5)
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import spikeinterface.full as si

    job_dir = args.job_dir.expanduser().resolve()
    results_root = args.results_root.expanduser().resolve()
    ground_truth_path = job_dir / "step1_v5_well_ground_truth.csv"
    ground_truth = pd.read_csv(ground_truth_path)
    ready = ground_truth.loc[_truthy_series(ground_truth["gui_analyzer_ready"])].copy()
    if args.plate_family != "all":
        ready = ready.loc[ready["plate_family"].astype(str).eq(args.plate_family)].copy()
    ready = ready.sort_values(["recording", "well"]).reset_index(drop=True)

    rows: list[dict[str, object]] = []
    errors: list[str] = []
    for _, well_row in ready.iterrows():
        analyzer_path = (
            results_root
            / str(well_row["recording"])
            / str(well_row["well"])
            / "postprocessed"
            / RECORDING_NAME
        )
        try:
            rows.extend(_rows_for_analyzer(si, well_row, analyzer_path, args.kslabel, args.rep_fraction))
        except Exception as exc:  # noqa: BLE001 - keep the rest of the current rerun useful
            errors.append(
                f"{well_row.get('recording')} / {well_row.get('well')}: {type(exc).__name__}: {exc}"
            )

    if not rows:
        raise SystemExit(f"No units with KSLabel={args.kslabel!r} were loaded from {len(ready)} ready wells.")

    table = pd.DataFrame(rows)
    output_stem = f"good_kslabel_ttp_distribution_template_best_ptp_{args.date_label}"
    if args.plate_family != "all":
        output_stem = f"{args.plate_family}_{output_stem}"
    csv_path = job_dir / f"{output_stem}.csv"
    figure_path = job_dir / f"{output_stem}.png"
    provenance_path = job_dir / f"{output_stem}_provenance.json"
    error_path = job_dir / f"{output_stem}_errors.txt"

    table.to_csv(csv_path, index=False)
    _plot_ttp_distribution(table, figure_path, args.kslabel)
    provenance = _provenance(args, ground_truth_path, csv_path, figure_path, table, ready, errors)
    provenance_path.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")
    if errors:
        error_path.write_text("\n".join(errors) + "\n", encoding="utf-8")

    print(f"Input wells scanned: {len(ready)}")
    print(f"KSLabel={args.kslabel!r} units plotted: {len(table)}")
    print(f"TTP summary CSV: {csv_path}")
    print(f"TTP distribution figure: {figure_path}")
    print(f"Provenance JSON: {provenance_path}")
    if errors:
        print(f"Skipped {len(errors)} analyzer(s); details: {error_path}")
    print("\nRS/FS-like counts from same TTP thresholds:")
    print(table["rs_fs_classification"].value_counts(dropna=False).to_string())
    print("\nTTP milliseconds:")
    print(table["trough_to_peak_duration_ms"].describe().to_string())


def _rows_for_analyzer(si, well_row: pd.Series, analyzer_path: Path, kslabel_filter: str, rep_fraction: float) -> list[dict[str, object]]:
    analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
    sorting = analyzer.sorting
    unit_ids = list(sorting.get_unit_ids())
    kslabels = _unit_property_array(sorting, "KSLabel", unit_ids, default="")
    templates_ext = analyzer.get_extension("templates")
    if templates_ext is None:
        raise ValueError(f"missing templates extension: {analyzer_path}")
    templates = _templates_average(templates_ext)
    if templates.ndim != 3:
        raise ValueError(f"expected templates units x samples x channels, found {templates.shape}")
    if templates.shape[0] != len(unit_ids):
        raise ValueError(f"template unit count {templates.shape[0]} does not match sorting unit count {len(unit_ids)}")

    sampling_frequency = float(analyzer.recording.get_sampling_frequency())
    out: list[dict[str, object]] = []
    for unit_index, unit_id in enumerate(unit_ids):
        kslabel = _normalize_label(kslabels[unit_index])
        if kslabel.lower() != kslabel_filter.lower():
            continue

        template = np.asarray(templates[unit_index], dtype=float)
        if template.ndim != 2 or not np.isfinite(template).any():
            continue
        channel_ptp = np.ptp(template, axis=0)
        if not np.isfinite(channel_ptp).any():
            continue
        best_channel_index = int(np.nanargmax(channel_ptp))
        best_waveform = template[:, best_channel_index]
        nbefore = int(getattr(templates_ext, "nbefore", np.nanargmin(best_waveform)))
        time_ms = (np.arange(template.shape[0]) - nbefore) / sampling_frequency * 1000.0
        metrics = _measure_spiketurnpike_waveform_metrics(best_waveform, time_ms, rep_fraction=rep_fraction)
        out.append(
            {
                "recording": str(well_row["recording"]),
                "well": str(well_row["well"]),
                "plate_family": str(well_row.get("plate_family", "")),
                "ground_truth_status": str(well_row.get("ground_truth_status", "")),
                "unit_id": unit_id,
                "unit_index": unit_index,
                "KSLabel": kslabel,
                "template_reference": f"templates.average[unit_index={unit_index},channel_index={best_channel_index}]",
                "best_channel_index": best_channel_index,
                "template_ptp_best_channel_uV": float(np.ptp(best_waveform)),
                "template_trough_best_channel_uV": float(np.nanmin(best_waveform)),
                "template_peak_best_channel_uV": float(np.nanmax(best_waveform)),
                "trough_index": metrics["trough_index"],
                "rebound_peak_index": metrics["rebound_peak_index"],
                "trough_time_ms": metrics["trough_time_ms"],
                "rebound_peak_time_ms": metrics["rebound_peak_time_ms"],
                "trough_to_peak_duration_ms": metrics["trough_to_peak_duration_ms"],
                "rs_fs_classification": metrics["tentative_rs_fs_classification"],
                "rep_fraction": metrics["rep_fraction"],
                "rep_threshold_uV": metrics["rep_threshold_uV"],
                "rep_recovery_index": metrics["rep_recovery_index"],
                "rep_recovery_time_ms": metrics["rep_recovery_time_ms"],
                "repolarization_time_ms": metrics["repolarization_time_ms"],
                "analyzer_path": str(analyzer_path),
            }
        )
    return out


def _templates_average(templates_ext) -> np.ndarray:
    try:
        return np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        templates_data = templates_ext.get_data()
        if isinstance(templates_data, dict):
            templates_data = templates_data.get("average")
        return np.asarray(templates_data, dtype=float)


def _unit_property_array(sorting, name: str, unit_ids: list[object], default: object) -> list[object]:
    values = sorting.get_property(name)
    if values is None:
        return [default] * len(unit_ids)
    return list(values)


def _normalize_label(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return value.tobytes().decode("utf-8")
    return str(value)


def _truthy_series(values: pd.Series) -> pd.Series:
    if values.dtype == bool:
        return values.fillna(False)
    return values.astype(str).str.lower().isin({"true", "1", "yes", "y"})


def _plot_ttp_distribution(table: pd.DataFrame, output_path: Path, kslabel: str) -> None:
    import matplotlib.pyplot as plt

    config = RSFSClassificationConfig()
    valid = table.dropna(subset=["trough_to_peak_duration_ms"]).copy()
    max_ttp = float(valid["trough_to_peak_duration_ms"].max()) if not valid.empty else 1.0
    bin_width = config.sample_dt_ms
    bins = np.arange(0.0, max(2.0, max_ttp + bin_width * 2), bin_width)
    colors = {
        "FS_like": "#d55e00",
        "borderline": "#7a7a7a",
        "RS_like": "#0072b2",
        "unknown": "#bdbdbd",
    }

    fig, ax = plt.subplots(figsize=(9.0, 5.4))
    for label in ["FS_like", "borderline", "RS_like", "unknown"]:
        values = valid.loc[valid["rs_fs_classification"].eq(label), "trough_to_peak_duration_ms"]
        if values.empty:
            continue
        ax.hist(values, bins=bins, alpha=0.72, color=colors[label], label=f"{label} (n={len(values)})")

    ax.axvline(config.fs_upper_bound_ms, color="#1f1f1f", linestyle="--", linewidth=1.2)
    ax.axvline(config.rs_lower_bound_ms, color="#1f1f1f", linestyle="--", linewidth=1.2)
    ax.text(config.fs_upper_bound_ms, ax.get_ylim()[1] * 0.96, "FS bound", ha="right", va="top", fontsize=9)
    ax.text(config.rs_lower_bound_ms, ax.get_ylim()[1] * 0.96, "RS bound", ha="left", va="top", fontsize=9)
    ax.set_xlabel("Trough-to-peak time (ms)")
    ax.set_ylabel("KSLabel=good unit count")
    ax.set_title(
        "Current good-unit TTP distribution from templates.average best-PTP channel\n"
        f"KSLabel={kslabel}; extraction matches Lumos candidate waveform gallery logic"
    )
    ax.legend(frameon=False)
    _add_summary_box(ax, valid)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _add_summary_box(ax, valid: pd.DataFrame) -> None:
    if valid.empty:
        text = "No finite TTP values"
    else:
        counts = valid["rs_fs_classification"].value_counts()
        text = (
            f"n = {len(valid)}\n"
            f"median = {valid['trough_to_peak_duration_ms'].median():.3f} ms\n"
            f"mean = {valid['trough_to_peak_duration_ms'].mean():.3f} ms\n"
            f"FS = {int(counts.get('FS_like', 0))}, "
            f"borderline = {int(counts.get('borderline', 0))}, "
            f"RS = {int(counts.get('RS_like', 0))}"
        )
    ax.text(
        0.985,
        0.94,
        text,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "0.75", "alpha": 0.92},
    )


def _provenance(
    args: argparse.Namespace,
    ground_truth_path: Path,
    csv_path: Path,
    figure_path: Path,
    table: pd.DataFrame,
    ready: pd.DataFrame,
    errors: list[str],
) -> dict[str, object]:
    config = RSFSClassificationConfig()
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ground_truth_csv": str(ground_truth_path),
        "results_root": str(args.results_root),
        "job_dir": str(args.job_dir),
        "plate_family_filter": args.plate_family,
        "kslabel_filter": args.kslabel,
        "ready_wells_scanned": int(len(ready)),
        "unit_count": int(len(table)),
        "classification_counts": table["rs_fs_classification"].value_counts(dropna=False).to_dict(),
        "ttp_ms_describe": table["trough_to_peak_duration_ms"].describe().to_dict(),
        "classification": config.provenance(),
        "waveform_extraction": (
            "SortingAnalyzer -> templates.average -> unit index -> best peak-to-peak channel -> "
            "minimum trough -> maximum rebound peak after trough"
        ),
        "rep_fraction": args.rep_fraction,
        "outputs": {"csv": str(csv_path), "figure": str(figure_path)},
        "errors": errors,
    }


if __name__ == "__main__":
    main()
