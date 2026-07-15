#!/usr/bin/env python3
"""Reclassify pooled Lumos + ventral CytoView units from robust waveforms.

The best channel is fixed from the maximum peak-to-peak amplitude across
``templates.average``.  Every persisted ``random_spikes`` selection is then
extracted from that channel, baseline centered, fractionally aligned to the
unit template by local-trough initialization plus template correlation, and
summarized with both the median and arithmetic mean.  PCHIP interpolation is
used only to estimate continuous waveform landmarks; it does not change the
12.5-kHz acquisition sampling rate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
from scipy.signal import find_peaks

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

JOB_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_ROSTER = JOB_ROOT / ".channel_avg_work_20260713/lumos_ventral_unit_metrics_recomputed.csv"
LUMOS_ALIGNMENT = JOB_ROOT / "waveform_alignment_feature_audit_20260709"
CYTOVIEW_ALIGNMENT = JOB_ROOT / "waveform_alignment_feature_audit_20260709_cytoview"
PAIRED_NAME = "waveform_alignment_feature_audit_20260709_paired_unit_metrics.csv"


@dataclass(frozen=True)
class Config:
    sampling_frequency_hz: float = 12_500.0
    fs_cutoff_ms: float = 0.50
    min_usable_snippets: int = 10
    central_trough_radius_ms: float = 0.40
    local_trough_radius_ms: float = 0.40
    match_before_trough_ms: float = 0.48
    match_after_trough_ms: float = 0.80
    fractional_refine_radius_samples: float = 1.00
    fractional_search_step_samples: float = 0.05
    dense_step_ms: float = 0.005
    post_peak_search_start_ms: float = 0.08
    post_peak_search_end_ms: float = 1.60
    edge_guard_ms: float = 0.16
    min_peak_height_fraction: float = 0.02
    min_peak_prominence_fraction: float = 0.03
    min_peak_prominence_uV: float = 0.25


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--fs-cutoff-ms", type=float, default=0.50)
    parser.add_argument("--dense-step-ms", type=float, default=0.005)
    parser.add_argument("--min-usable-snippets", type=int, default=10)
    parser.add_argument("--max-units", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    config = Config(
        fs_cutoff_ms=args.fs_cutoff_ms,
        dense_step_ms=args.dense_step_ms,
        min_usable_snippets=args.min_usable_snippets,
    )

    import spikeinterface.full as si

    roster_path = args.roster.expanduser().resolve()
    roster = pd.read_csv(roster_path)
    if args.max_units is not None:
        roster = roster.head(args.max_units).copy()
    paired = pd.concat(
        [
            pd.read_csv(LUMOS_ALIGNMENT / PAIRED_NAME),
            pd.read_csv(CYTOVIEW_ALIGNMENT / PAIRED_NAME),
        ],
        ignore_index=True,
    ).drop_duplicates("unit_key")
    source = roster.merge(
        paired[
            [
                "unit_key",
                "analyzer_path",
                "unit_index",
                "after_trough_to_peak_duration_ms",
            ]
        ],
        on="unit_key",
        how="left",
        validate="one_to_one",
    )
    if source[["analyzer_path", "unit_index"]].isna().any().any():
        missing = source.loc[source["analyzer_path"].isna(), "unit_key"].tolist()
        raise ValueError(f"Missing analyzer metadata for {len(missing)} units: {missing[:10]}")

    metric_rows: list[dict[str, Any]] = []
    trace_frames: list[pd.DataFrame] = []
    errors: list[dict[str, Any]] = []
    for analyzer_number, (analyzer_path_text, group) in enumerate(
        source.groupby("analyzer_path", sort=False), start=1
    ):
        analyzer_path = Path(str(analyzer_path_text))
        print(
            f"[{analyzer_number}/{source['analyzer_path'].nunique()}] "
            f"{analyzer_path} ({len(group)} roster units)",
            flush=True,
        )
        try:
            analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
            sorting = analyzer.sorting
            recording = analyzer.recording
            templates_ext = analyzer.get_extension("templates")
            random_ext = analyzer.get_extension("random_spikes")
            if templates_ext is None or random_ext is None:
                raise ValueError("analyzer requires templates and random_spikes extensions")
            templates = _templates_average(templates_ext)
            unit_ids = list(sorting.get_unit_ids())
            channel_ids = list(recording.get_channel_ids())
            sampling_frequency = float(recording.get_sampling_frequency())
            if not np.isclose(sampling_frequency, config.sampling_frequency_hz, rtol=0, atol=1e-6):
                raise ValueError(
                    f"sampling frequency {sampling_frequency} != {config.sampling_frequency_hz} Hz"
                )
            nbefore = int(templates_ext.nbefore)
            nafter = int(templates_ext.nafter)
        except Exception as exc:  # noqa: BLE001
            for _, row in group.iterrows():
                errors.append(_error_row(row, analyzer_path, exc))
            continue

        for _, source_row in group.iterrows():
            try:
                unit_index = int(source_row["unit_index"])
                if unit_index < 0 or unit_index >= len(unit_ids):
                    raise IndexError(f"unit_index {unit_index} outside {len(unit_ids)} units")
                unit_id = unit_ids[unit_index]
                template = np.asarray(templates[unit_index], dtype=float)
                if template.ndim != 2:
                    raise ValueError(f"template shape is {template.shape}, expected samples x channels")
                best_channel_index = int(np.nanargmax(np.ptp(template, axis=0)))
                best_channel_id = channel_ids[best_channel_index]
                template_waveform = _baseline_center(template[:, best_channel_index], nbefore)
                template_trough_index = _central_trough_index(
                    template_waveform, nbefore, config
                )
                snippets, selected_count, usable_count = _extract_persisted_snippets(
                    recording,
                    sorting,
                    random_ext,
                    unit_id,
                    best_channel_id,
                    nbefore,
                    nafter,
                )
                if usable_count < config.min_usable_snippets:
                    raise ValueError(
                        f"only {usable_count} usable persisted snippets; "
                        f"minimum is {config.min_usable_snippets}"
                    )
                snippets = np.stack(
                    [_baseline_center(snippet, nbefore) for snippet in snippets], axis=0
                )
                aligned, shifts, correlations = _fractionally_align_snippets(
                    snippets, template_waveform, template_trough_index, config
                )
                valid_rows = np.isfinite(aligned).sum(axis=1) >= max(8, aligned.shape[1] // 2)
                aligned = aligned[valid_rows]
                shifts = shifts[valid_rows]
                correlations = correlations[valid_rows]
                if aligned.shape[0] < config.min_usable_snippets:
                    raise ValueError(
                        f"only {aligned.shape[0]} snippets remained after fractional alignment"
                    )
                robust_median = _baseline_center(
                    _repair_finite(np.nanmedian(aligned, axis=0)), nbefore
                )
                aligned_mean = _baseline_center(
                    _repair_finite(np.nanmean(aligned, axis=0)), nbefore
                )
                median_features = _measure_pchip_features(
                    robust_median, template_trough_index, config
                )
                mean_features = _measure_pchip_features(
                    aligned_mean, template_trough_index, config
                )
                old_class = str(source_row["rs_fs_class"])
                new_class = _classify_ttp(
                    median_features["trough_to_peak_duration_ms"], config.fs_cutoff_ms
                )
                metric_rows.append(
                    {
                        "unit_key": source_row["unit_key"],
                        "source_platform": source_row["source_platform"],
                        "recording": source_row["recording"],
                        "well": source_row["well"],
                        "unit_id": source_row["unit_id"],
                        "analyzer_path": str(analyzer_path),
                        "unit_index": unit_index,
                        "analyzer_unit_id": unit_id,
                        "best_channel_index": best_channel_index,
                        "best_channel_id": best_channel_id,
                        "template_ptp_best_channel_uV": float(np.ptp(template_waveform)),
                        "template_trough_index": template_trough_index,
                        "persisted_random_spikes_selected": selected_count,
                        "usable_snippets_before_alignment": usable_count,
                        "usable_snippets_after_alignment": int(aligned.shape[0]),
                        "alignment_shift_median_samples": _safe_stat(np.nanmedian, shifts),
                        "alignment_shift_mad_samples": _safe_stat(
                            np.nanmedian, np.abs(shifts - np.nanmedian(shifts))
                        ),
                        "alignment_shift_min_samples": _safe_stat(np.nanmin, shifts),
                        "alignment_shift_max_samples": _safe_stat(np.nanmax, shifts),
                        "alignment_correlation_median": _safe_stat(np.nanmedian, correlations),
                        "old_trough_to_peak_duration_ms": source_row.get(
                            "after_trough_to_peak_duration_ms", np.nan
                        ),
                        "old_rs_fs_class": old_class,
                        **{f"robust_median_{key}": value for key, value in median_features.items()},
                        **{f"aligned_mean_{key}": value for key, value in mean_features.items()},
                        "new_rs_fs_class": new_class,
                        "classification_changed": old_class != new_class,
                        "classification_transition": f"{old_class}->{new_class}",
                    }
                )
                sample_time_ms = (
                    np.arange(robust_median.size, dtype=float)
                    * 1000.0
                    / config.sampling_frequency_hz
                )
                trace_frames.append(
                    pd.DataFrame(
                        {
                            "unit_key": source_row["unit_key"],
                            "sample_index": np.arange(robust_median.size, dtype=int),
                            "sample_time_ms": sample_time_ms,
                            "time_ms": sample_time_ms
                            - sample_time_ms[template_trough_index],
                            "robust_median_uV": robust_median,
                            "aligned_arithmetic_mean_uV": aligned_mean,
                            "template_best_channel_uV": template_waveform,
                        }
                    )
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(_error_row(source_row, analyzer_path, exc))

    metrics = pd.DataFrame(metric_rows)
    traces = pd.concat(trace_frames, ignore_index=True) if trace_frames else pd.DataFrame()
    errors_table = pd.DataFrame(errors)
    expected = len(source)
    if len(metrics) != expected or not errors_table.empty:
        errors_path = output_dir / "robust_pchip_errors.csv"
        errors_table.to_csv(errors_path, index=False)
        raise RuntimeError(
            f"Robust waveform extraction completed for {len(metrics)}/{expected} units; "
            f"{len(errors_table)} errors written to {errors_path}"
        )

    metrics_path = output_dir / "robust_pchip_unit_metrics.csv"
    traces_path = output_dir / "robust_pchip_waveform_traces.csv.gz"
    transitions_path = output_dir / "robust_pchip_classification_transitions.csv"
    transition_summary_path = output_dir / "robust_pchip_transition_summary.csv"
    provenance_path = output_dir / "robust_pchip_provenance.json"
    metrics.to_csv(metrics_path, index=False)
    traces.to_csv(traces_path, index=False, compression="gzip")
    transitions = metrics[
        [
            "unit_key",
            "source_platform",
            "recording",
            "well",
            "unit_id",
            "old_trough_to_peak_duration_ms",
            "robust_median_trough_to_peak_duration_ms",
            "aligned_mean_trough_to_peak_duration_ms",
            "old_rs_fs_class",
            "new_rs_fs_class",
            "classification_changed",
            "classification_transition",
        ]
    ].copy()
    transitions.to_csv(transitions_path, index=False)
    transition_summary = (
        metrics.groupby("classification_transition", dropna=False)
        .size()
        .rename("unit_count")
        .reset_index()
        .sort_values("classification_transition")
    )
    transition_summary.to_csv(transition_summary_path, index=False)
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "roster": str(roster_path),
        "roster_sha256": _sha256(roster_path),
        "unit_count": int(len(metrics)),
        "analyzer_count": int(source["analyzer_path"].nunique()),
        "config": asdict(config),
        "method": {
            "best_channel": "maximum PTP across templates.average channels",
            "snippet_source": "persisted random_spikes selections; no new resampling",
            "alignment": (
                "local trough initialization followed by fractional template-correlation "
                "refinement; fractional shifts applied with PCHIP"
            ),
            "representatives": "median and arithmetic mean across fractionally aligned snippets",
            "feature_interpolation": (
                "PCHIP on the original 12.5-kHz sample times, evaluated every "
                f"{config.dense_step_ms} ms only for continuous landmark estimation"
            ),
            "classification": f"FS if robust-median TTP <= {config.fs_cutoff_ms} ms; RS otherwise",
        },
        "transition_counts": transition_summary.set_index("classification_transition")[
            "unit_count"
        ].to_dict(),
        "changed_unit_count": int(metrics["classification_changed"].sum()),
        "outputs": {
            "unit_metrics": str(metrics_path),
            "waveform_traces": str(traces_path),
            "unit_transitions": str(transitions_path),
            "transition_summary": str(transition_summary_path),
        },
    }
    provenance_path.write_text(json.dumps(provenance, indent=2, default=str) + "\n")
    print("\nTransition summary:")
    print(transition_summary.to_string(index=False))
    print(f"Changed units: {int(metrics['classification_changed'].sum())}/{len(metrics)}")
    print(f"Metrics: {metrics_path}")
    print(f"Traces: {traces_path}")
    print(f"Provenance: {provenance_path}")
    return 0


def _extract_persisted_snippets(
    recording,
    sorting,
    random_ext,
    unit_id: Any,
    channel_id: Any,
    nbefore: int,
    nafter: int,
) -> tuple[list[np.ndarray], int, int]:
    snippets: list[np.ndarray] = []
    selected_total = 0
    for segment_index in range(sorting.get_num_segments()):
        spike_train = np.asarray(
            sorting.get_unit_spike_train(unit_id=unit_id, segment_index=segment_index),
            dtype=np.int64,
        )
        selected_indices = np.asarray(
            random_ext.get_selected_indices_in_spike_train(unit_id, segment_index),
            dtype=np.int64,
        )
        selected_indices = selected_indices[
            (selected_indices >= 0) & (selected_indices < spike_train.size)
        ]
        selected_total += int(selected_indices.size)
        num_samples = int(recording.get_num_samples(segment_index=segment_index))
        for frame in spike_train[selected_indices]:
            start = int(frame) - nbefore
            end = int(frame) + nafter
            if start < 0 or end > num_samples:
                continue
            trace = np.asarray(
                recording.get_traces(
                    segment_index=segment_index,
                    start_frame=start,
                    end_frame=end,
                    channel_ids=[channel_id],
                    return_in_uV=True,
                ),
                dtype=float,
            )
            if trace.shape == (nbefore + nafter, 1) and np.isfinite(trace).all():
                snippets.append(trace[:, 0])
    return snippets, selected_total, len(snippets)


def _fractionally_align_snippets(
    snippets: np.ndarray,
    template_waveform: np.ndarray,
    template_trough_index: int,
    config: Config,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    sample_index = np.arange(snippets.shape[1], dtype=float)
    sample_dt_ms = 1000.0 / config.sampling_frequency_hz
    local_radius = max(1, int(round(config.local_trough_radius_ms / sample_dt_ms)))
    match_left = max(
        0, template_trough_index - int(round(config.match_before_trough_ms / sample_dt_ms))
    )
    match_right = min(
        snippets.shape[1],
        template_trough_index
        + int(round(config.match_after_trough_ms / sample_dt_ms))
        + 1,
    )
    match_indices = np.arange(match_left, match_right, dtype=float)
    template_match = template_waveform[match_left:match_right]
    template_match = template_match - np.mean(template_match)
    template_norm = float(np.linalg.norm(template_match))
    residuals = np.arange(
        -config.fractional_refine_radius_samples,
        config.fractional_refine_radius_samples
        + 0.5 * config.fractional_search_step_samples,
        config.fractional_search_step_samples,
    )
    aligned = np.full_like(snippets, np.nan, dtype=float)
    shifts = np.full(snippets.shape[0], np.nan, dtype=float)
    correlations = np.full(snippets.shape[0], np.nan, dtype=float)
    left = max(0, template_trough_index - local_radius)
    right = min(snippets.shape[1], template_trough_index + local_radius + 1)
    for row_index, snippet in enumerate(snippets):
        local_trough_index = left + int(np.argmin(snippet[left:right]))
        initial_shift = float(local_trough_index - template_trough_index)
        interpolator = PchipInterpolator(sample_index, snippet, extrapolate=False)
        scores = np.full(residuals.size, -np.inf, dtype=float)
        for candidate_index, residual in enumerate(residuals):
            candidate = interpolator(match_indices + initial_shift + residual)
            if not np.isfinite(candidate).all():
                continue
            candidate = candidate - np.mean(candidate)
            denom = template_norm * float(np.linalg.norm(candidate))
            if denom > 0:
                scores[candidate_index] = float(np.dot(template_match, candidate) / denom)
        best_index = int(np.argmax(scores))
        if not np.isfinite(scores[best_index]):
            continue
        refined_residual = float(residuals[best_index])
        if 0 < best_index < scores.size - 1:
            y_left, y_center, y_right = scores[best_index - 1 : best_index + 2]
            denominator = y_left - 2.0 * y_center + y_right
            if np.isfinite(denominator) and denominator < 0:
                offset = 0.5 * (y_left - y_right) / denominator
                offset = float(np.clip(offset, -1.0, 1.0))
                refined_residual += offset * config.fractional_search_step_samples
        shift = initial_shift + refined_residual
        aligned[row_index] = interpolator(sample_index + shift)
        shifts[row_index] = shift
        correlations[row_index] = scores[best_index]
    return aligned, shifts, correlations


def _measure_pchip_features(
    waveform: np.ndarray, template_trough_index: int, config: Config
) -> dict[str, Any]:
    sample_time_ms = (
        np.arange(waveform.size, dtype=float) * 1000.0 / config.sampling_frequency_hz
    )
    dense_time_ms = np.arange(
        sample_time_ms[0], sample_time_ms[-1] + 0.5 * config.dense_step_ms, config.dense_step_ms
    )
    dense_waveform = PchipInterpolator(sample_time_ms, waveform)(dense_time_ms)
    baseline_stop = max(3, template_trough_index - 6)
    baseline_uV = float(np.median(waveform[:baseline_stop]))
    expected_trough_time = float(sample_time_ms[template_trough_index])
    trough_mask = (
        (dense_time_ms >= expected_trough_time - config.central_trough_radius_ms)
        & (dense_time_ms <= expected_trough_time + config.central_trough_radius_ms)
    )
    trough_candidates = np.flatnonzero(trough_mask)
    if trough_candidates.size == 0:
        raise ValueError("empty central trough search region")
    trough_dense_index = int(
        trough_candidates[np.argmin(dense_waveform[trough_candidates])]
    )
    trough_time_ms = float(dense_time_ms[trough_dense_index])
    trough_uV = float(dense_waveform[trough_dense_index])
    trough_amplitude_uV = baseline_uV - trough_uV
    if not np.isfinite(trough_amplitude_uV) or trough_amplitude_uV <= 0:
        raise ValueError("principal trough is not negative relative to baseline")
    search_end = min(
        trough_time_ms + config.post_peak_search_end_ms,
        sample_time_ms[-1] - config.edge_guard_ms,
    )
    post_mask = (
        (dense_time_ms >= trough_time_ms + config.post_peak_search_start_ms)
        & (dense_time_ms <= search_end)
    )
    post_indices = np.flatnonzero(post_mask)
    if post_indices.size < 3:
        raise ValueError("empty post-trough peak search region")
    post_values = dense_waveform[post_indices]
    min_height = baseline_uV + config.min_peak_height_fraction * trough_amplitude_uV
    min_prominence = max(
        config.min_peak_prominence_uV,
        config.min_peak_prominence_fraction * trough_amplitude_uV,
    )
    peaks, properties = find_peaks(
        post_values,
        height=min_height,
        prominence=min_prominence,
        distance=max(1, int(round(0.08 / config.dense_step_ms))),
    )
    if peaks.size == 0:
        return {
            "trough_to_peak_duration_ms": np.nan,
            "trough_time_ms": trough_time_ms,
            "post_trough_peak_time_ms": np.nan,
            "trough_uV": trough_uV,
            "post_trough_peak_uV": np.nan,
            "baseline_uV": baseline_uV,
            "spike_half_width_ms": _half_width(
                dense_time_ms, dense_waveform, trough_dense_index, baseline_uV
            ),
            "repolarization_time_ms": _repolarization_time(
                dense_time_ms, dense_waveform, trough_dense_index, baseline_uV
            ),
            "peak_detection_status": "no_physiologically_meaningful_positive_peak",
            "post_peak_search_end_ms": search_end,
        }
    peak_dense_index = int(post_indices[int(peaks[0])])
    peak_time_ms = float(dense_time_ms[peak_dense_index])
    peak_uV = float(dense_waveform[peak_dense_index])
    return {
        "trough_to_peak_duration_ms": peak_time_ms - trough_time_ms,
        "trough_time_ms": trough_time_ms,
        "post_trough_peak_time_ms": peak_time_ms,
        "trough_uV": trough_uV,
        "post_trough_peak_uV": peak_uV,
        "baseline_uV": baseline_uV,
        "spike_half_width_ms": _half_width(
            dense_time_ms, dense_waveform, trough_dense_index, baseline_uV
        ),
        "repolarization_time_ms": _repolarization_time(
            dense_time_ms, dense_waveform, trough_dense_index, baseline_uV
        ),
        "peak_prominence_uV": float(properties["prominences"][0]),
        "peak_detection_status": "first_meaningful_positive_local_maximum",
        "post_peak_search_end_ms": search_end,
    }


def _half_width(
    time_ms: np.ndarray, waveform: np.ndarray, trough_index: int, baseline_uV: float
) -> float:
    threshold = (baseline_uV + float(waveform[trough_index])) / 2.0
    left = np.flatnonzero(waveform[:trough_index] >= threshold)
    right = np.flatnonzero(waveform[trough_index + 1 :] >= threshold)
    if left.size == 0 or right.size == 0:
        return np.nan
    left_index = int(left[-1])
    right_index = int(trough_index + 1 + right[0])
    return float(time_ms[right_index] - time_ms[left_index])


def _repolarization_time(
    time_ms: np.ndarray, waveform: np.ndarray, trough_index: int, baseline_uV: float
) -> float:
    threshold = (baseline_uV + float(waveform[trough_index])) / 2.0
    right = np.flatnonzero(waveform[trough_index + 1 :] >= threshold)
    if right.size == 0:
        return np.nan
    recovery_index = int(trough_index + 1 + right[0])
    return float(time_ms[recovery_index] - time_ms[trough_index])


def _central_trough_index(waveform: np.ndarray, nbefore: int, config: Config) -> int:
    radius = max(
        1,
        int(
            round(
                config.central_trough_radius_ms
                * config.sampling_frequency_hz
                / 1000.0
            )
        ),
    )
    left = max(0, nbefore - radius)
    right = min(waveform.size, nbefore + radius + 1)
    return left + int(np.argmin(waveform[left:right]))


def _baseline_center(waveform: np.ndarray, nbefore: int) -> np.ndarray:
    waveform = np.asarray(waveform, dtype=float)
    baseline_stop = max(3, nbefore - 6)
    return waveform - float(np.median(waveform[:baseline_stop]))


def _repair_finite(waveform: np.ndarray) -> np.ndarray:
    waveform = np.asarray(waveform, dtype=float)
    finite = np.isfinite(waveform)
    if finite.sum() < 3:
        raise ValueError("representative waveform has fewer than three finite samples")
    if finite.all():
        return waveform
    sample_index = np.arange(waveform.size, dtype=float)
    return np.interp(sample_index, sample_index[finite], waveform[finite])


def _classify_ttp(ttp_ms: Any, cutoff_ms: float) -> str:
    try:
        value = float(ttp_ms)
    except Exception:  # noqa: BLE001
        return "unclassified"
    if not np.isfinite(value):
        return "unclassified"
    return "FS" if value <= cutoff_ms else "RS"


def _templates_average(templates_ext) -> np.ndarray:
    try:
        return np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        data = templates_ext.get_data()
        if isinstance(data, dict):
            data = data["average"]
        return np.asarray(data, dtype=float)


def _error_row(row: pd.Series, analyzer_path: Path, exc: Exception) -> dict[str, Any]:
    return {
        "unit_key": row.get("unit_key"),
        "source_platform": row.get("source_platform"),
        "recording": row.get("recording"),
        "well": row.get("well"),
        "unit_id": row.get("unit_id"),
        "analyzer_path": str(analyzer_path),
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def _safe_stat(function, values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    if values.size == 0 or not np.isfinite(values).any():
        return np.nan
    return float(function(values))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
