#!/usr/bin/env python
"""Reconcile old vs local half-width/REP denominators for Lumos good units.

This script does not interpret histograms. It verifies whether old and local
metric plots share the same starting population and reports how many units are
valid or excluded for half-width and REP50 under each metric definition.
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
CLASS_ORDER = ["FS_like", "borderline", "RS_like"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--metrics-csv", type=Path)
    args = parser.parse_args()

    job_dir = args.job_dir.expanduser().resolve()
    metrics_csv = args.metrics_csv or job_dir / f"lumos_all_sorted_unit_waveform_metrics_{args.date_label}.csv"
    metrics = pd.read_csv(metrics_csv)
    good = metrics.loc[metrics["KSLabel"].astype(str).str.lower().eq("good")].copy()
    if good.empty:
        raise SystemExit("No KSLabel=good Lumos units found.")

    _coerce_numeric(good)
    summary = _summary_table(good)
    exclusions = _exclusion_table(good)
    unit_flags = _unit_flags(good)

    stem = f"lumos_good_halfwidth_rep_denominator_reconciliation_{args.date_label}"
    summary_csv = job_dir / f"{stem}.csv"
    exclusions_csv = job_dir / f"{stem}_exclusions.csv"
    unit_flags_csv = job_dir / f"{stem}_unit_flags.csv"
    provenance_json = job_dir / f"{stem}_provenance.json"

    summary.to_csv(summary_csv, index=False)
    exclusions.to_csv(exclusions_csv, index=False)
    unit_flags.to_csv(unit_flags_csv, index=False)
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "metrics_csv": str(metrics_csv),
        "starting_population": "KSLabel=good Lumos units in GUI-ready analyzers",
        "total_good_units": int(len(good)),
        "definitions": {
            "original_baseline": {
                "half_width": "current baseline-referenced SpikeTurnpike half-width",
                "rep50": "current baseline-referenced REP50",
            },
            "robust_local_excursion": {
                "half_width": "robust local-excursion half-width at (Peak1 + trough) / 2",
                "rep50": "robust local-excursion REP50 at (Peak1 + trough) / 2",
            },
        },
        "outputs": {
            "summary_csv": str(summary_csv),
            "exclusions_csv": str(exclusions_csv),
            "unit_flags_csv": str(unit_flags_csv),
        },
        "notes": [
            "This is denominator reconciliation only; it does not interpret histogram shape.",
            "TTP classes are not recalculated after metric exclusion; counts are current TTP labels among units with valid metric values.",
            "A reduction in valid local units is denominator loss from stricter crossing selection, not reclassification.",
        ],
    }
    provenance_json.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(f"Metrics CSV: {metrics_csv}")
    print(f"Total KSLabel=good Lumos units: {len(good)}")
    print(f"Summary CSV: {summary_csv}")
    print(f"Exclusions CSV: {exclusions_csv}")
    print(f"Unit flags CSV: {unit_flags_csv}")
    print(f"Provenance: {provenance_json}")
    print("\nSummary:")
    print(summary.to_string(index=False))
    print("\nExclusions:")
    print(exclusions.to_string(index=False))


def _coerce_numeric(table: pd.DataFrame) -> None:
    numeric_columns = [
        "current_half_width_ms",
        "current_rep50_ms",
        "robust_local_half_width_ms",
        "robust_local_rep50_ms",
        "trough_value_uV",
        "pre_peak_index",
        "trough_index",
        "rebound_peak_index",
        "robust_local_half_width_start_index",
        "robust_local_half_width_end_index",
        "robust_local_rep50_index",
    ]
    for column in numeric_columns:
        if column in table.columns:
            table[column] = pd.to_numeric(table[column], errors="coerce")


def _summary_table(good: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    specs = [
        ("original_baseline", "half_width", "current_half_width_ms", _original_half_width_reason),
        ("original_baseline", "rep50", "current_rep50_ms", _original_rep50_reason),
        ("robust_local_excursion", "half_width", "robust_local_half_width_ms", _robust_half_width_reason),
        ("robust_local_excursion", "rep50", "robust_local_rep50_ms", _robust_rep50_reason),
    ]
    for analysis, measure, metric_col, reason_fn in specs:
        valid = good[metric_col].replace([np.inf, -np.inf], np.nan).notna()
        excluded = ~valid
        row = {
            "analysis": analysis,
            "measure": measure,
            "total_good_units": int(len(good)),
            "valid_units": int(valid.sum()),
            "excluded_units": int(excluded.sum()),
        }
        valid_subset = good.loc[valid]
        for label in CLASS_ORDER:
            row[f"valid_{label}_count"] = int(valid_subset["rs_fs_classification"].eq(label).sum())
        row["exclusion_reasons"] = _reason_counts(good.loc[excluded], reason_fn)
        rows.append(row)
    return pd.DataFrame(rows)


def _exclusion_table(good: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    specs = [
        ("original_baseline", "half_width", "current_half_width_ms", _original_half_width_reason),
        ("original_baseline", "rep50", "current_rep50_ms", _original_rep50_reason),
        ("robust_local_excursion", "half_width", "robust_local_half_width_ms", _robust_half_width_reason),
        ("robust_local_excursion", "rep50", "robust_local_rep50_ms", _robust_rep50_reason),
    ]
    for analysis, measure, metric_col, reason_fn in specs:
        valid = good[metric_col].replace([np.inf, -np.inf], np.nan).notna()
        excluded = good.loc[~valid].copy()
        if excluded.empty:
            rows.append(
                {
                    "analysis": analysis,
                    "measure": measure,
                    "exclusion_reason": "none",
                    "excluded_units": 0,
                    "excluded_FS_like_count": 0,
                    "excluded_borderline_count": 0,
                    "excluded_RS_like_count": 0,
                }
            )
            continue
        excluded["exclusion_reason"] = excluded.apply(reason_fn, axis=1)
        for reason, subset in excluded.groupby("exclusion_reason", dropna=False):
            rows.append(
                {
                    "analysis": analysis,
                    "measure": measure,
                    "exclusion_reason": str(reason),
                    "excluded_units": int(len(subset)),
                    "excluded_FS_like_count": int(subset["rs_fs_classification"].eq("FS_like").sum()),
                    "excluded_borderline_count": int(subset["rs_fs_classification"].eq("borderline").sum()),
                    "excluded_RS_like_count": int(subset["rs_fs_classification"].eq("RS_like").sum()),
                }
            )
    return pd.DataFrame(rows)


def _unit_flags(good: pd.DataFrame) -> pd.DataFrame:
    out = good[
        [
            "recording",
            "well",
            "unit_id",
            "unit_index",
            "KSLabel",
            "rs_fs_classification",
            "current_half_width_ms",
            "current_rep50_ms",
            "robust_local_half_width_ms",
            "robust_local_rep50_ms",
            "robust_local_descent_status",
            "robust_local_recovery_status",
            "analyzer_path",
        ]
    ].copy()
    out["original_half_width_valid"] = out["current_half_width_ms"].replace([np.inf, -np.inf], np.nan).notna()
    out["original_rep50_valid"] = out["current_rep50_ms"].replace([np.inf, -np.inf], np.nan).notna()
    out["robust_local_half_width_valid"] = (
        out["robust_local_half_width_ms"].replace([np.inf, -np.inf], np.nan).notna()
    )
    out["robust_local_rep50_valid"] = out["robust_local_rep50_ms"].replace([np.inf, -np.inf], np.nan).notna()
    out["original_half_width_exclusion_reason"] = good.apply(_original_half_width_reason, axis=1)
    out["original_rep50_exclusion_reason"] = good.apply(_original_rep50_reason, axis=1)
    out["robust_local_half_width_exclusion_reason"] = good.apply(_robust_half_width_reason, axis=1)
    out["robust_local_rep50_exclusion_reason"] = good.apply(_robust_rep50_reason, axis=1)
    return out


def _reason_counts(excluded: pd.DataFrame, reason_fn) -> str:
    if excluded.empty:
        return "none"
    reasons = excluded.apply(reason_fn, axis=1).value_counts(dropna=False)
    return "; ".join(f"{reason}={count}" for reason, count in reasons.items())


def _original_half_width_reason(row: pd.Series) -> str:
    if _finite(row.get("current_half_width_ms")):
        return "valid"
    if not _valid_landmarks(row):
        return "missing_or_invalid_peak_trough_landmarks"
    if not _finite(row.get("trough_value_uV")):
        return "nan_trough_value"
    return "original_half_width_nan"


def _original_rep50_reason(row: pd.Series) -> str:
    if _finite(row.get("current_rep50_ms")):
        return "valid"
    if not _finite(row.get("trough_value_uV")):
        return "nan_trough_value"
    if float(row.get("trough_value_uV")) >= 0:
        return "nonnegative_trough"
    return "no_baseline_recovery_crossing"


def _robust_half_width_reason(row: pd.Series) -> str:
    if _finite(row.get("robust_local_half_width_ms")):
        return "valid"
    descent = str(row.get("robust_local_descent_status", "missing_descent_status"))
    recovery = str(row.get("robust_local_recovery_status", "missing_recovery_status"))
    if descent != "ok":
        return f"descent_{descent}"
    return f"recovery_{recovery}"


def _robust_rep50_reason(row: pd.Series) -> str:
    if _finite(row.get("robust_local_rep50_ms")):
        return "valid"
    recovery = str(row.get("robust_local_recovery_status", "missing_recovery_status"))
    return f"recovery_{recovery}"


def _valid_landmarks(row: pd.Series) -> bool:
    for column in ["pre_peak_index", "trough_index", "rebound_peak_index"]:
        value = row.get(column)
        if not _finite(value) or int(value) < 0:
            return False
    return True


def _finite(value: object) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return bool(np.isfinite(number))


if __name__ == "__main__":
    main()
