#!/usr/bin/env python3
"""Compare discrete peak, PCHIP peak, and TTR90 FS classifications.

Only fractionally aligned mean waveforms with canonical negative-trough
morphology are classified. Positive-first and other positive-dominant
waveforms remain explicitly unclassified.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq


DEFAULT_AUDIT_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/FINAL FIG 2/"
    "Population Panels/ventral_MGE_putative_FS_RS_robust_PCHIP_FINAL/"
    "waveform_source_audit"
)


@dataclass(frozen=True)
class Config:
    sampling_frequency_hz: float = 12_500.0
    fs_cutoff_ms: float = 0.50
    dense_step_ms: float = 0.005
    central_trough_radius_ms: float = 0.40
    post_window_start_ms: float = 0.08
    post_window_end_ms: float = 1.20
    rebound_fraction: float = 0.90
    high_confidence_fs_max_ms: float = 0.40
    high_confidence_rs_min_ms: float = 0.56


METHOD_COLUMNS = {
    "raw_discrete_global_peak": "raw_discrete_global_peak_class",
    "pchip_global_peak": "pchip_global_peak_class",
    "ttr90": "ttr90_class_direct_0_5ms",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--expected-unit-count",
        type=int,
        default=None,
        help="Optional exact roster-size assertion for cohort-specific runs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit_dir = args.audit_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    config = Config()

    source_metrics = pd.read_csv(audit_dir / "waveform_source_audit_unit_metrics.csv")
    traces = pd.read_csv(
        audit_dir / "waveform_source_audit_representations.csv.gz",
        usecols=[
            "unit_key",
            "sample_index",
            "sample_time_ms",
            "fractional_aligned_mean_uV",
        ],
    )
    unique_unit_count = int(source_metrics["unit_key"].nunique())
    if unique_unit_count != len(source_metrics):
        raise ValueError(
            f"unit roster contains duplicates: {len(source_metrics)} rows, "
            f"{unique_unit_count} unique unit keys"
        )
    if args.expected_unit_count is not None and len(source_metrics) != args.expected_unit_count:
        raise ValueError(
            f"expected {args.expected_unit_count} units, found {len(source_metrics)}"
        )

    rows: list[dict[str, Any]] = []
    dense_traces: list[pd.DataFrame] = []
    trace_groups = {
        key: group.sort_values("sample_index")
        for key, group in traces.groupby("unit_key", sort=False)
    }
    for _, source in source_metrics.iterrows():
        unit_key = str(source["unit_key"])
        if unit_key not in trace_groups:
            raise ValueError(f"missing aligned mean trace for {unit_key}")
        unit_trace = trace_groups[unit_key]
        sample_time_ms = unit_trace["sample_time_ms"].to_numpy(float)
        waveform_uV = unit_trace["fractional_aligned_mean_uV"].to_numpy(float)
        measurement, dense_trace = _measure_unit(
            sample_time_ms,
            waveform_uV,
            int(source["template_trough_sample"]),
            config,
        )
        audit_canonical = bool(
            source["fractional_aligned_mean_main_deflection_is_negative"]
        )
        if measurement["canonical_negative_trough"] != audit_canonical:
            raise ValueError(
                f"canonical morphology mismatch for {unit_key}: "
                f"recomputed={measurement['canonical_negative_trough']} "
                f"audit={audit_canonical}"
            )
        row = {
            "unit_key": unit_key,
            "source_platform": source["source_platform"],
            "recording": source["recording"],
            "well": source["well"],
            "unit_id": source["unit_id"],
            "analyzer_path": source["analyzer_path"],
            "recording_processing_variant": source[
                "recording_processing_variant"
            ],
            "old_rs_fs_class": source["old_rs_fs_class"],
            "strict_pchip_class": source["strict_pchip_class"],
            **measurement,
        }
        for method, class_column in METHOD_COLUMNS.items():
            timing_column = {
                "raw_discrete_global_peak": "raw_discrete_trough_to_global_peak_ms",
                "pchip_global_peak": "pchip_trough_to_global_peak_ms",
                "ttr90": "ttr90_ms",
            }[method]
            valid_column = {
                "raw_discrete_global_peak": "raw_discrete_global_peak_valid",
                "pchip_global_peak": "pchip_global_peak_valid",
                "ttr90": "valid_90pct_crossing_exists",
            }[method]
            row[class_column] = _classify(
                timing_ms=row[timing_column],
                valid=bool(row[valid_column]),
                canonical=bool(row["canonical_negative_trough"]),
                cutoff_ms=config.fs_cutoff_ms,
            )
        row["ttr90_confidence_category"] = _confidence_category(
            timing_ms=row["ttr90_ms"],
            valid=bool(row["valid_90pct_crossing_exists"]),
            canonical=bool(row["canonical_negative_trough"]),
            config=config,
        )
        rows.append(row)
        dense_trace.insert(0, "unit_key", unit_key)
        dense_traces.append(dense_trace)

    metrics = pd.DataFrame(rows)
    dense = pd.concat(dense_traces, ignore_index=True)
    transitions = _transition_table(metrics)
    cutoff_audit = _cutoff_transfer_audit(metrics, config)
    summary = _summary(metrics, transitions, cutoff_audit, config)

    metrics_path = output_dir / "ttr90_canonical_negative_unit_metrics.csv"
    dense_path = output_dir / "ttr90_canonical_negative_pchip_traces.csv.gz"
    transitions_path = output_dir / "ttr90_canonical_negative_transitions.csv"
    summary_path = output_dir / "ttr90_canonical_negative_summary.json"
    pdf_path = output_dir / "ttr90_canonical_negative_overlays.pdf"
    metrics.to_csv(metrics_path, index=False)
    dense.to_csv(dense_path, index=False, compression="gzip")
    transitions.to_csv(transitions_path, index=False)
    _plot_overlays(metrics, dense, traces, config, pdf_path)
    summary["generated_at"] = datetime.now().isoformat(timespec="seconds")
    summary["outputs"] = {
        "unit_metrics": str(metrics_path),
        "dense_pchip_traces": str(dense_path),
        "transitions": str(transitions_path),
        "overlays_pdf": str(pdf_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n")

    print(json.dumps(summary, indent=2, default=str))
    return 0


def _measure_unit(
    sample_time_ms: np.ndarray,
    waveform_uV: np.ndarray,
    expected_trough_sample: int,
    config: Config,
) -> tuple[dict[str, Any], pd.DataFrame]:
    if sample_time_ms.size != waveform_uV.size or sample_time_ms.size < 5:
        raise ValueError("invalid aligned waveform arrays")
    interpolator = PchipInterpolator(sample_time_ms, waveform_uV)
    dense_time_ms = np.arange(
        sample_time_ms[0],
        sample_time_ms[-1] + 0.5 * config.dense_step_ms,
        config.dense_step_ms,
    )
    dense_waveform_uV = interpolator(dense_time_ms)
    expected_trough_time_ms = float(sample_time_ms[expected_trough_sample])
    dense_central = np.flatnonzero(
        (dense_time_ms >= expected_trough_time_ms - config.central_trough_radius_ms)
        & (dense_time_ms <= expected_trough_time_ms + config.central_trough_radius_ms)
    )
    raw_central = np.flatnonzero(
        (sample_time_ms >= expected_trough_time_ms - config.central_trough_radius_ms)
        & (sample_time_ms <= expected_trough_time_ms + config.central_trough_radius_ms)
    )
    if dense_central.size == 0 or raw_central.size == 0:
        raise ValueError("empty central trough search region")
    trough_dense_index = int(
        dense_central[np.argmin(dense_waveform_uV[dense_central])]
    )
    trough_time_ms = float(dense_time_ms[trough_dense_index])
    trough_uV = float(dense_waveform_uV[trough_dense_index])
    raw_trough_index = int(raw_central[np.argmin(waveform_uV[raw_central])])
    raw_trough_time_ms = float(sample_time_ms[raw_trough_index])

    # Match the established morphology audit exactly: polarity dominance was
    # evaluated against the median of the first six waveform samples.
    baseline_stop = min(6, waveform_uV.size)
    baseline_uV = float(np.median(waveform_uV[:baseline_stop]))
    negative_amplitude_uV = baseline_uV - trough_uV
    positive_amplitude_uV = float(np.max(waveform_uV) - baseline_uV)
    global_positive_index = int(np.argmax(waveform_uV))
    canonical = bool(
        negative_amplitude_uV > 0
        and negative_amplitude_uV >= positive_amplitude_uV
    )
    if canonical:
        morphology_class = "canonical_negative_trough"
    elif sample_time_ms[global_positive_index] < trough_time_ms:
        morphology_class = "positive_first_atypical"
    elif positive_amplitude_uV > negative_amplitude_uV:
        morphology_class = "positive_dominant_post_trough_atypical"
    else:
        morphology_class = "other_atypical"

    raw_post = np.flatnonzero(
        (sample_time_ms >= raw_trough_time_ms + config.post_window_start_ms)
        & (sample_time_ms <= raw_trough_time_ms + config.post_window_end_ms)
    )
    dense_post = np.flatnonzero(
        (dense_time_ms >= trough_time_ms + config.post_window_start_ms)
        & (dense_time_ms <= trough_time_ms + config.post_window_end_ms)
    )
    if raw_post.size == 0 or dense_post.size == 0:
        raise ValueError("empty fixed post-trough search window")
    raw_peak_index = int(raw_post[np.argmax(waveform_uV[raw_post])])
    peak_dense_index = int(
        dense_post[np.argmax(dense_waveform_uV[dense_post])]
    )
    raw_peak_time_ms = float(sample_time_ms[raw_peak_index])
    raw_peak_uV = float(waveform_uV[raw_peak_index])
    peak_time_ms = float(dense_time_ms[peak_dense_index])
    peak_uV = float(dense_waveform_uV[peak_dense_index])
    rebound_amplitude_uV = peak_uV - trough_uV
    target_90_uV = trough_uV + config.rebound_fraction * rebound_amplitude_uV
    crossing_time_ms = _first_crossing(
        interpolator,
        dense_time_ms,
        dense_waveform_uV,
        trough_dense_index,
        peak_dense_index,
        target_90_uV,
    )
    crossing_valid = bool(np.isfinite(crossing_time_ms))

    metrics = {
        "morphology_class": morphology_class,
        "canonical_negative_trough": canonical,
        "ttr90_evaluated_for_classifier": canonical,
        "baseline_uV": baseline_uV,
        "principal_trough_time_ms": trough_time_ms,
        "principal_trough_uV": trough_uV,
        "raw_discrete_trough_time_ms": raw_trough_time_ms,
        "raw_discrete_global_peak_time_ms": raw_peak_time_ms,
        "raw_discrete_global_peak_uV": raw_peak_uV,
        "raw_discrete_trough_to_global_peak_ms": raw_peak_time_ms
        - raw_trough_time_ms,
        "raw_discrete_global_peak_valid": True,
        "pchip_global_peak_time_ms": peak_time_ms,
        "pchip_global_peak_uV": peak_uV,
        "pchip_trough_to_global_peak_ms": peak_time_ms - trough_time_ms,
        "pchip_global_peak_valid": True,
        "rebound_amplitude_uV": rebound_amplitude_uV,
        "target_90_uV": target_90_uV,
        "first_90pct_crossing_time_ms": crossing_time_ms,
        "ttr90_ms": crossing_time_ms - trough_time_ms
        if crossing_valid
        else np.nan,
        "valid_90pct_crossing_exists": crossing_valid,
        "post_window_start_time_ms": trough_time_ms
        + config.post_window_start_ms,
        "post_window_end_time_ms": trough_time_ms + config.post_window_end_ms,
        "global_positive_time_ms": float(sample_time_ms[global_positive_index]),
        "negative_trough_amplitude_uV": negative_amplitude_uV,
        "positive_deflection_amplitude_uV": positive_amplitude_uV,
    }
    dense_trace = pd.DataFrame(
        {
            "dense_time_ms": dense_time_ms,
            "time_from_trough_ms": dense_time_ms - trough_time_ms,
            "pchip_waveform_uV": dense_waveform_uV,
        }
    )
    return metrics, dense_trace


def _first_crossing(
    interpolator: PchipInterpolator,
    dense_time_ms: np.ndarray,
    dense_waveform_uV: np.ndarray,
    trough_index: int,
    peak_index: int,
    target_uV: float,
) -> float:
    if peak_index <= trough_index or not np.isfinite(target_uV):
        return np.nan
    segment = dense_waveform_uV[trough_index : peak_index + 1] - target_uV
    above = np.flatnonzero(segment >= 0)
    if above.size == 0:
        return np.nan
    upper_index = trough_index + int(above[0])
    if upper_index == trough_index:
        return float(dense_time_ms[upper_index])
    lower_index = upper_index - 1
    lower_time = float(dense_time_ms[lower_index])
    upper_time = float(dense_time_ms[upper_index])
    lower_value = float(interpolator(lower_time) - target_uV)
    upper_value = float(interpolator(upper_time) - target_uV)
    if np.isclose(lower_value, 0.0, atol=1e-12):
        return lower_time
    if np.isclose(upper_value, 0.0, atol=1e-12):
        return upper_time
    if lower_value > 0 or upper_value < 0:
        return np.nan
    return float(
        brentq(
            lambda time: float(interpolator(time) - target_uV),
            lower_time,
            upper_time,
        )
    )


def _classify(
    timing_ms: Any, valid: bool, canonical: bool, cutoff_ms: float
) -> str:
    if not canonical or not valid:
        return "unclassified"
    value = float(timing_ms)
    if not np.isfinite(value):
        return "unclassified"
    return "FS" if value <= cutoff_ms else "RS"


def _confidence_category(
    timing_ms: Any, valid: bool, canonical: bool, config: Config
) -> str:
    if not canonical:
        return "unclassified_atypical"
    if not valid or not np.isfinite(float(timing_ms)):
        return "unclassified_no_valid_crossing"
    value = float(timing_ms)
    if value <= config.high_confidence_fs_max_ms:
        return "high_confidence_FS_like"
    if value >= config.high_confidence_rs_min_ms:
        return "high_confidence_RS_like"
    return "indeterminate"


def _transition_table(metrics: pd.DataFrame) -> pd.DataFrame:
    comparisons = [
        ("established_old", "old_rs_fs_class", *next(iter(METHOD_COLUMNS.items()))),
        (
            "established_old",
            "old_rs_fs_class",
            "pchip_global_peak",
            METHOD_COLUMNS["pchip_global_peak"],
        ),
        (
            "established_old",
            "old_rs_fs_class",
            "ttr90",
            METHOD_COLUMNS["ttr90"],
        ),
        (
            "strict_pchip",
            "strict_pchip_class",
            "ttr90",
            METHOD_COLUMNS["ttr90"],
        ),
        (
            "raw_discrete_global_peak",
            METHOD_COLUMNS["raw_discrete_global_peak"],
            "pchip_global_peak",
            METHOD_COLUMNS["pchip_global_peak"],
        ),
        (
            "pchip_global_peak",
            METHOD_COLUMNS["pchip_global_peak"],
            "ttr90",
            METHOD_COLUMNS["ttr90"],
        ),
        (
            "established_old",
            "old_rs_fs_class",
            "ttr90_confidence_category",
            "ttr90_confidence_category",
        ),
        (
            "strict_pchip",
            "strict_pchip_class",
            "ttr90_confidence_category",
            "ttr90_confidence_category",
        ),
        (
            "pchip_global_peak",
            METHOD_COLUMNS["pchip_global_peak"],
            "ttr90_confidence_category",
            "ttr90_confidence_category",
        ),
    ]
    frames: list[pd.DataFrame] = []
    for from_method, from_column, to_method, to_column in comparisons:
        counts = (
            metrics.groupby([from_column, to_column], dropna=False)
            .size()
            .rename("unit_count")
            .reset_index()
            .rename(columns={from_column: "from_label", to_column: "to_label"})
        )
        counts.insert(0, "from_method", from_method)
        counts.insert(1, "to_method", to_method)
        counts["total_unit_denominator"] = len(metrics)
        frames.append(counts)
    return pd.concat(frames, ignore_index=True)


def _cutoff_transfer_audit(metrics: pd.DataFrame, config: Config) -> dict[str, Any]:
    eligible = metrics.loc[
        metrics["canonical_negative_trough"]
        & metrics["pchip_global_peak_valid"]
        & metrics["valid_90pct_crossing_exists"]
    ].copy()
    reference = eligible["pchip_global_peak_class"].eq("FS").to_numpy(bool)
    ttr90 = eligible["ttr90_ms"].to_numpy(float)
    direct = ttr90 <= config.fs_cutoff_ms
    thresholds = _threshold_candidates(ttr90)
    scored: list[tuple[float, float, float]] = []
    for threshold in thresholds:
        prediction = ttr90 <= threshold
        accuracy = float(np.mean(prediction == reference))
        sensitivity = float(np.mean(prediction[reference])) if reference.any() else np.nan
        specificity = (
            float(np.mean(~prediction[~reference])) if (~reference).any() else np.nan
        )
        balanced = float(np.nanmean([sensitivity, specificity]))
        scored.append((balanced, accuracy, float(threshold)))
    best_balanced, best_accuracy, best_threshold = max(
        scored,
        key=lambda item: (item[0], item[1], -abs(item[2] - config.fs_cutoff_ms)),
    )
    matched = ttr90 <= best_threshold
    return {
        "eligible_canonical_unit_count": int(len(eligible)),
        "direct_cutoff_ms": config.fs_cutoff_ms,
        "direct_cutoff_agreement_with_pchip_global_peak_class": float(
            np.mean(direct == reference)
        ),
        "direct_cutoff_confusion_against_pchip_global_peak": _confusion(
            reference, direct
        ),
        "best_empirical_ttr90_threshold_to_match_pchip_global_peak_ms": best_threshold,
        "best_empirical_threshold_balanced_accuracy": best_balanced,
        "best_empirical_threshold_accuracy": best_accuracy,
        "best_empirical_threshold_confusion": _confusion(reference, matched),
        "median_pchip_peak_minus_ttr90_ms": float(
            np.median(
                eligible["pchip_trough_to_global_peak_ms"]
                - eligible["ttr90_ms"]
            )
        ),
        "comparison_note": (
            "The direct 0.5-ms TTR90 split is retained as a separate sensitivity "
            "comparison. The primary TTR90 interpretation uses the supplied "
            "continuous PCHIP confidence anchors of <=0.40 ms and >=0.56 ms."
        ),
    }


def _threshold_candidates(values: np.ndarray) -> np.ndarray:
    unique = np.unique(np.asarray(values, dtype=float))
    if unique.size == 1:
        return unique
    midpoints = (unique[:-1] + unique[1:]) / 2.0
    epsilon = max(1e-6, 0.01 * float(np.min(np.diff(unique))))
    return np.concatenate(
        [[unique[0] - epsilon], unique, midpoints, [unique[-1] + epsilon]]
    )


def _confusion(reference_fs: np.ndarray, predicted_fs: np.ndarray) -> dict[str, int]:
    return {
        "FS_to_FS": int(np.sum(reference_fs & predicted_fs)),
        "FS_to_RS": int(np.sum(reference_fs & ~predicted_fs)),
        "RS_to_FS": int(np.sum(~reference_fs & predicted_fs)),
        "RS_to_RS": int(np.sum(~reference_fs & ~predicted_fs)),
    }


def _summary(
    metrics: pd.DataFrame,
    transitions: pd.DataFrame,
    cutoff_audit: dict[str, Any],
    config: Config,
) -> dict[str, Any]:
    strict_unclassified = metrics["strict_pchip_class"].eq("unclassified")
    class_counts = {
        method: {
            label: int((metrics[column] == label).sum())
            for label in ["FS", "RS", "unclassified"]
        }
        for method, column in METHOD_COLUMNS.items()
    }
    direct = transitions.loc[
        transitions["from_method"].eq("pchip_global_peak")
        & transitions["to_method"].eq("ttr90")
    ]
    confidence_counts = {
        str(label): int(count)
        for label, count in metrics["ttr90_confidence_category"].value_counts().items()
    }
    return {
        "unit_denominator": int(len(metrics)),
        "fs_cutoff_ms_applied_for_requested_comparison": config.fs_cutoff_ms,
        "morphology_counts": {
            str(label): int(count)
            for label, count in metrics["morphology_class"].value_counts().items()
        },
        "canonical_negative_trough_count": int(
            metrics["canonical_negative_trough"].sum()
        ),
        "positive_first_or_atypical_unclassified_count": int(
            (~metrics["canonical_negative_trough"]).sum()
        ),
        "valid_90pct_crossing_count_within_canonical_group": int(
            metrics.loc[
                metrics["canonical_negative_trough"],
                "valid_90pct_crossing_exists",
            ].sum()
        ),
        "class_counts_same_unit_denominator": class_counts,
        "ttr90_confidence_category_counts_same_unit_denominator": confidence_counts,
        "ttr90_confidence_anchors_ms": {
            "high_confidence_FS_like_maximum_inclusive": config.high_confidence_fs_max_ms,
            "indeterminate_interval": (
                f">{config.high_confidence_fs_max_ms:.2f} and "
                f"<{config.high_confidence_rs_min_ms:.2f}"
            ),
            "high_confidence_RS_like_minimum_inclusive": config.high_confidence_rs_min_ms,
            "measurement": "continuous PCHIP-interpolated TTR90; not discretized",
        },
        "previously_strict_unclassified": {
            "unit_count": int(strict_unclassified.sum()),
            "canonical_negative_trough_count": int(
                (
                    strict_unclassified & metrics["canonical_negative_trough"]
                ).sum()
            ),
            "newly_measurable_by_ttr90_count": int(
                (
                    strict_unclassified
                    & metrics["canonical_negative_trough"]
                    & metrics["valid_90pct_crossing_exists"]
                ).sum()
            ),
            "ttr90_FS_count": int(
                metrics.loc[strict_unclassified, METHOD_COLUMNS["ttr90"]]
                .eq("FS")
                .sum()
            ),
            "ttr90_RS_count": int(
                metrics.loc[strict_unclassified, METHOD_COLUMNS["ttr90"]]
                .eq("RS")
                .sum()
            ),
            "remaining_unclassified_count": int(
                metrics.loc[strict_unclassified, METHOD_COLUMNS["ttr90"]]
                .eq("unclassified")
                .sum()
            ),
            "confidence_category_counts": {
                str(label): int(count)
                for label, count in metrics.loc[
                    strict_unclassified, "ttr90_confidence_category"
                ]
                .value_counts()
                .items()
            },
        },
        "pchip_global_peak_to_ttr90_direct_transitions": [
            {
                "from_label": row["from_label"],
                "to_label": row["to_label"],
                "unit_count": int(row["unit_count"]),
            }
            for _, row in direct.iterrows()
        ],
        "timing_summary_canonical_ms": {
            column: {
                "median": float(
                    metrics.loc[metrics["canonical_negative_trough"], column].median()
                ),
                "q25": float(
                    metrics.loc[metrics["canonical_negative_trough"], column].quantile(
                        0.25
                    )
                ),
                "q75": float(
                    metrics.loc[metrics["canonical_negative_trough"], column].quantile(
                        0.75
                    )
                ),
            }
            for column in [
                "raw_discrete_trough_to_global_peak_ms",
                "pchip_trough_to_global_peak_ms",
                "ttr90_ms",
            ]
        },
        "cutoff_transfer_assessment": cutoff_audit,
        "config": asdict(config),
    }


def _plot_overlays(
    metrics: pd.DataFrame,
    dense: pd.DataFrame,
    samples: pd.DataFrame,
    config: Config,
    path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    canonical = metrics.loc[metrics["canonical_negative_trough"]].copy()
    canonical["diagnostic_priority"] = np.select(
        [
            canonical["strict_pchip_class"].eq("unclassified"),
            canonical["pchip_global_peak_class"].ne(
                canonical["ttr90_class_direct_0_5ms"]
            ),
        ],
        [0, 1],
        default=2,
    )
    canonical = canonical.sort_values(
        ["diagnostic_priority", "source_platform", "recording", "well", "unit_id"]
    )
    metric_lookup = canonical.set_index("unit_key")
    dense_lookup = {
        key: group.sort_values("dense_time_ms")
        for key, group in dense.groupby("unit_key", sort=False)
    }
    sample_lookup = {
        key: group.sort_values("sample_index")
        for key, group in samples.groupby("unit_key", sort=False)
    }
    with PdfPages(path) as pdf:
        for page_start in range(0, len(canonical), 4):
            page = canonical.iloc[page_start : page_start + 4]
            fig, axes = plt.subplots(2, 2, figsize=(11.0, 8.0), squeeze=False)
            for ax in axes.ravel():
                ax.set_visible(False)
            for ax, (_, selected) in zip(axes.ravel(), page.iterrows(), strict=False):
                ax.set_visible(True)
                unit_key = selected["unit_key"]
                row = metric_lookup.loc[unit_key]
                unit_dense = dense_lookup[unit_key]
                unit_samples = sample_lookup[unit_key]
                trough_time = float(row["principal_trough_time_ms"])
                dense_x = unit_dense["dense_time_ms"].to_numpy(float) - trough_time
                dense_y = unit_dense["pchip_waveform_uV"].to_numpy(float)
                sample_x = unit_samples["sample_time_ms"].to_numpy(float) - trough_time
                sample_y = unit_samples["fractional_aligned_mean_uV"].to_numpy(float)
                ax.plot(dense_x, dense_y, color="#303030", lw=1.4)
                ax.scatter(sample_x, sample_y, s=10, color="#777777", zorder=3)
                ax.scatter(
                    [0.0],
                    [row["principal_trough_uV"]],
                    s=28,
                    color="#111111",
                    zorder=5,
                    label="trough",
                )
                raw_peak_x = (
                    float(row["raw_discrete_global_peak_time_ms"]) - trough_time
                )
                peak_x = float(row["pchip_global_peak_time_ms"]) - trough_time
                crossing_x = float(row["first_90pct_crossing_time_ms"]) - trough_time
                ax.axhline(
                    float(row["target_90_uV"]),
                    color="#6F8477",
                    lw=0.9,
                    ls="--",
                    label="90% rebound level",
                )
                ax.axvline(
                    raw_peak_x,
                    color="#999999",
                    lw=0.8,
                    ls=":",
                    label="discrete peak time",
                )
                ax.axvline(
                    peak_x,
                    color="#B8742A",
                    lw=1.0,
                    ls="--",
                    label="PCHIP global peak time",
                )
                ax.axvline(
                    crossing_x,
                    color="#58758E",
                    lw=1.1,
                    label="TTR90",
                )
                ax.scatter(
                    [peak_x],
                    [row["pchip_global_peak_uV"]],
                    s=28,
                    color="#B8742A",
                    zorder=5,
                )
                ax.scatter(
                    [crossing_x],
                    [row["target_90_uV"]],
                    s=30,
                    color="#58758E",
                    zorder=6,
                )
                ax.axvspan(
                    config.post_window_start_ms,
                    config.post_window_end_ms,
                    color="#BBBBBB",
                    alpha=0.08,
                    lw=0,
                )
                ax.axhline(0, color="#DDDDDD", lw=0.5)
                ax.set_xlim(-0.75, 1.65)
                ax.set_title(
                    f"{row['source_platform']} {row['well']} u{row['unit_id']} · "
                    f"strict {row['strict_pchip_class']}\n"
                    f"discrete {row['raw_discrete_trough_to_global_peak_ms']:.3f} ms "
                    f"({row['raw_discrete_global_peak_class']}) · "
                    f"PCHIP {row['pchip_trough_to_global_peak_ms']:.3f} ms "
                    f"({row['pchip_global_peak_class']}) · "
                    f"TTR90 {row['ttr90_ms']:.3f} ms "
                    f"({row['ttr90_confidence_category'].replace('_', ' ')})",
                    fontsize=8,
                    loc="left",
                )
                ax.set_xlabel("Time from trough (ms)")
                ax.set_ylabel("Amplitude (µV)")
                ax.spines[["top", "right"]].set_visible(False)
            handles, labels = axes.ravel()[0].get_legend_handles_labels()
            fig.legend(
                handles,
                labels,
                loc="lower center",
                ncol=3,
                frameon=False,
                fontsize=7,
            )
            fig.suptitle(
                "Canonical negative-trough TTR90 classifier overlays · "
                f"page {page_start // 4 + 1}",
                fontsize=12,
                fontweight="bold",
            )
            fig.tight_layout(rect=[0.02, 0.07, 0.98, 0.95])
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
