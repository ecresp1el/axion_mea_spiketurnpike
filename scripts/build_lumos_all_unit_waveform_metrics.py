#!/usr/bin/env python
"""Build waveform metrics for every sorted unit in GUI-ready Lumos analyzers.

This is independent of opto/stim validity. It enumerates every unit present in
the completed Lumos SortingAnalyzer outputs, carries KSLabel as metadata, and
computes current, naive local-excursion, and robust local-excursion waveform
metrics on the raw best-PTP-channel ``templates.average`` waveform.

Failed/sparse-fallback wells are summarized separately because they do not have
a standard GUI-ready analyzer/template set to measure.
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

from scripts.explore_local_excursion_width_rep import (  # noqa: E402
    _measure_local_excursion_metrics,
    _measure_robust_local_excursion_metrics,
)
from scripts.launch_step1_sorting_analyzer_browser import DEFAULT_AIND_RESULTS_ROOT  # noqa: E402
from scripts.plot_lumos_candidate_waveform_gallery import (  # noqa: E402
    _measure_spiketurnpike_waveform_metrics,
)


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_DATE_LABEL = "20260709"
RECORDING_NAME = "block0_None_recording1.zarr"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_AIND_RESULTS_ROOT)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--rep-fraction", type=float, choices=(0.25, 0.5, 0.63), default=0.5)
    args = parser.parse_args()

    import spikeinterface.full as si

    job_dir = args.job_dir.expanduser().resolve()
    results_root = args.results_root.expanduser().resolve()
    ground_truth_path = job_dir / "step1_v5_well_ground_truth.csv"
    ground_truth = pd.read_csv(ground_truth_path)
    lumos = ground_truth.loc[ground_truth["plate_family"].astype(str).eq("lumos_48well")].copy()
    ready = lumos.loc[_truthy_series(lumos["gui_analyzer_ready"])].copy()
    stim_status = _load_stim_status(job_dir, args.date_label)

    rows: list[dict[str, object]] = []
    errors: list[str] = []
    for _, well_row in ready.sort_values(["recording", "well"]).iterrows():
        analyzer_path = (
            results_root
            / str(well_row["recording"])
            / str(well_row["well"])
            / "postprocessed"
            / RECORDING_NAME
        )
        try:
            rows.extend(
                _rows_for_analyzer(
                    si,
                    well_row,
                    analyzer_path,
                    stim_status=stim_status,
                    rep_fraction=args.rep_fraction,
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                f"{well_row.get('recording')} / {well_row.get('well')}: "
                f"{type(exc).__name__}: {exc}"
            )

    if not rows:
        raise SystemExit("No sorted units could be measured from GUI-ready Lumos analyzers.")

    table = pd.DataFrame(rows)
    stem = f"lumos_all_sorted_unit_waveform_metrics_{args.date_label}"
    metrics_csv = job_dir / f"{stem}.csv"
    summary_csv = job_dir / f"{stem}_summary.csv"
    provenance_json = job_dir / f"{stem}_provenance.json"
    error_path = job_dir / f"{stem}_errors.txt"

    table.to_csv(metrics_csv, index=False)
    summary = _summary_table(lumos, ready, table, errors)
    summary.to_csv(summary_csv, index=False)
    if errors:
        error_path.write_text("\n".join(errors) + "\n", encoding="utf-8")

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "ground_truth_csv": str(ground_truth_path),
        "unit_metrics_csv": str(metrics_csv),
        "summary_csv": str(summary_csv),
        "lumos_well_rows": int(len(lumos)),
        "gui_ready_lumos_wells": int(len(ready)),
        "measured_units": int(len(table)),
        "rep_fraction": args.rep_fraction,
        "notes": [
            "This table is all sorted units in GUI-ready Lumos analyzers, not only KSLabel=good units.",
            "Opto/stim availability is carried as metadata and is not used to filter units.",
            "Sparse-fallback/export-failed wells are not measured here because standard templates.average analyzers are unavailable.",
            "Current production waveform metrics and FS/RS classifier are not modified.",
        ],
        "errors": errors,
    }
    provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Lumos well rows in ground truth: {len(lumos)}")
    print(f"GUI-ready Lumos wells scanned: {len(ready)}")
    print(f"Sorted units measured: {len(table)}")
    print(f"Unit metrics CSV: {metrics_csv}")
    print(f"Summary CSV: {summary_csv}")
    print(f"Provenance: {provenance_json}")
    if errors:
        print(f"Skipped {len(errors)} analyzer(s); details: {error_path}")
    print("\nKSLabel counts:")
    print(table["KSLabel"].value_counts(dropna=False).to_string())
    print("\nStim status counts, by unit:")
    print(table["stim_status"].value_counts(dropna=False).to_string())
    print("\nRobust local recovery status:")
    print(table["robust_local_recovery_status"].value_counts(dropna=False).to_string())


def _rows_for_analyzer(
    si,
    well_row: pd.Series,
    analyzer_path: Path,
    *,
    stim_status: dict[tuple[str, str], str],
    rep_fraction: float,
) -> list[dict[str, object]]:
    analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
    sorting = analyzer.sorting
    unit_ids = list(sorting.get_unit_ids())
    templates_ext = analyzer.get_extension("templates")
    if templates_ext is None:
        raise ValueError("missing templates extension")
    templates = _templates_average(templates_ext)
    if templates.ndim != 3:
        raise ValueError(f"expected templates units x samples x channels, found {templates.shape}")
    if templates.shape[0] != len(unit_ids):
        raise ValueError(f"template unit count {templates.shape[0]} does not match unit IDs {len(unit_ids)}")

    sampling_frequency = float(analyzer.recording.get_sampling_frequency())
    kslabels = _unit_property_array(sorting, "KSLabel", unit_ids, default="")
    contam_pct = _unit_property_array(sorting, "ContamPct", unit_ids, default=np.nan)
    amplitudes = _unit_property_array(sorting, "Amplitude", unit_ids, default=np.nan)
    stim_key = (str(well_row["recording"]), str(well_row["well"]))
    rows: list[dict[str, object]] = []
    for unit_index, unit_id in enumerate(unit_ids):
        template = np.asarray(templates[unit_index], dtype=float)
        if template.ndim != 2 or not np.isfinite(template).any():
            continue
        best_channel_index = int(np.nanargmax(np.ptp(template, axis=0)))
        waveform = template[:, best_channel_index]
        nbefore = int(getattr(templates_ext, "nbefore", np.nanargmin(waveform)))
        time_ms = (np.arange(waveform.size) - nbefore) / sampling_frequency * 1000.0
        current = _measure_spiketurnpike_waveform_metrics(waveform, time_ms, rep_fraction=rep_fraction)
        local = _measure_local_excursion_metrics(waveform, time_ms, current)
        robust = _measure_robust_local_excursion_metrics(waveform, time_ms, current)
        trough_index = int(current["trough_index"])
        trough_value = float(waveform[trough_index]) if 0 <= trough_index < waveform.size else np.nan
        rows.append(
            {
                "recording": str(well_row["recording"]),
                "well": str(well_row["well"]),
                "plate_family": str(well_row.get("plate_family", "")),
                "raw_variant": str(well_row.get("raw_variant", "")),
                "ground_truth_status": str(well_row.get("ground_truth_status", "")),
                "stim_status": stim_status.get(stim_key, "not_in_stim_table"),
                "unit_id": unit_id,
                "unit_index": unit_index,
                "KSLabel": _normalize_label(kslabels[unit_index]),
                "ContamPct": _safe_float(contam_pct[unit_index]),
                "Amplitude": _safe_float(amplitudes[unit_index]),
                "analyzer_path": str(analyzer_path),
                "template_reference": f"templates.average[unit_index={unit_index},channel_index={best_channel_index}]",
                "best_channel_index": best_channel_index,
                "template_ptp_best_channel_uV": float(np.ptp(waveform)),
                "template_trough_best_channel_uV": float(np.nanmin(waveform)),
                "template_peak_best_channel_uV": float(np.nanmax(waveform)),
                "trough_to_peak_duration_ms": current["trough_to_peak_duration_ms"],
                "rs_fs_classification": current["tentative_rs_fs_classification"],
                "pre_peak_index": current["pre_peak_index"],
                "trough_index": current["trough_index"],
                "rebound_peak_index": current["rebound_peak_index"],
                "pre_peak_value_uV": current["pre_peak_value_uV"],
                "trough_value_uV": trough_value,
                "post_peak_value_uV": current["post_peak_value_uV"],
                "current_half_width_ms": current["spike_half_width_ms"],
                "current_rep50_ms": current["repolarization_time_ms"],
                "naive_local_half_width_ms": local["local_half_width_ms"],
                "naive_local_rep50_ms": local["local_rep50_ms"],
                "naive_local_midpoint_uV": local["local_midpoint_uV"],
                "robust_local_half_width_ms": robust["robust_local_half_width_ms"],
                "robust_local_rep50_ms": robust["robust_local_rep50_ms"],
                "robust_local_midpoint_uV": robust["robust_local_midpoint_uV"],
                "robust_local_half_width_start_index": robust["robust_local_half_width_start_index"],
                "robust_local_half_width_end_index": robust["robust_local_half_width_end_index"],
                "robust_local_half_width_start_time_ms": robust["robust_local_half_width_start_time_ms"],
                "robust_local_half_width_end_time_ms": robust["robust_local_half_width_end_time_ms"],
                "robust_local_rep50_index": robust["robust_local_rep50_index"],
                "robust_local_rep50_time_ms": robust["robust_local_rep50_time_ms"],
                "robust_local_descent_status": robust["robust_local_descent_status"],
                "robust_local_recovery_status": robust["robust_local_recovery_status"],
                "pre_peak_to_trough_ratio_uV": local["pre_peak_to_trough_ratio_uV"],
            }
        )
    return rows


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
    values = list(values)
    if len(values) != len(unit_ids):
        return [default] * len(unit_ids)
    return values


def _load_stim_status(job_dir: Path, date_label: str) -> dict[tuple[str, str], str]:
    path = job_dir / f"lumos_gui_ready_trial_tag_screen_250pulse_jitterwin_{date_label}.csv"
    if not path.exists():
        return {}
    table = pd.read_csv(path)
    if not {"recording", "well", "status"}.issubset(table.columns):
        return {}
    return {
        (str(row["recording"]), str(row["well"])): str(row["status"])
        for _, row in table.iterrows()
    }


def _summary_table(
    lumos: pd.DataFrame,
    ready: pd.DataFrame,
    units: pd.DataFrame,
    errors: list[str],
) -> pd.DataFrame:
    rows = [
        {"metric": "lumos_well_rows", "group": "all", "value": int(len(lumos))},
        {"metric": "gui_ready_lumos_wells", "group": "all", "value": int(len(ready))},
        {"metric": "measured_sorted_units", "group": "all", "value": int(len(units))},
        {"metric": "analyzer_load_errors", "group": "all", "value": int(len(errors))},
    ]
    for status, count in lumos["ground_truth_status"].value_counts(dropna=False).items():
        rows.append({"metric": "lumos_ground_truth_status_wells", "group": str(status), "value": int(count)})
    for label, count in units["KSLabel"].value_counts(dropna=False).items():
        rows.append({"metric": "unit_kslabel_count", "group": str(label), "value": int(count)})
    for status, count in units["stim_status"].value_counts(dropna=False).items():
        rows.append({"metric": "unit_stim_status_count", "group": str(status), "value": int(count)})
    for status, count in units["robust_local_recovery_status"].value_counts(dropna=False).items():
        rows.append({"metric": "robust_local_recovery_status_count", "group": str(status), "value": int(count)})
    return pd.DataFrame(rows)


def _truthy_series(values: pd.Series) -> pd.Series:
    if values.dtype == bool:
        return values.fillna(False)
    return values.astype(str).str.lower().isin({"true", "1", "yes", "y"})


def _normalize_label(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return value.tobytes().decode("utf-8")
    return str(value)


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


if __name__ == "__main__":
    main()
