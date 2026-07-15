#!/usr/bin/env python3
"""Audit waveform sources before promoting the robust PCHIP FS/RS classifier."""

from __future__ import annotations

import argparse
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

from scripts.reclassify_lumos_ventral_robust_pchip_waveforms import (  # noqa: E402
    Config as AlignmentConfig,
    _baseline_center,
    _central_trough_index,
    _fractionally_align_snippets,
    _templates_average,
)

DEFAULT_AUDIT_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/FINAL FIG 2/"
    "Population Panels/ventral_MGE_putative_FS_RS_robust_PCHIP_FINAL/"
    "classification_audit"
)


@dataclass(frozen=True)
class AuditConfig:
    sampling_frequency_hz: float = 12_500.0
    fs_cutoff_ms: float = 0.50
    dense_step_ms: float = 0.005
    search_start_after_trough_ms: float = 0.08
    search_end_after_trough_ms: float = 1.20
    edge_guard_ms: float = 0.08
    min_recovery_fraction: float = 0.25
    min_prominence_fraction: float = 0.03
    min_prominence_uV: float = 0.25
    trimmed_fraction_each_tail: float = 0.10
    rising_edge_min_slope_uV_per_ms: float = 0.50
    alignment_failure_correlation: float = 0.50
    template_disagreement_correlation: float = 0.80
    template_disagreement_nrmse: float = 0.50
    competing_peak_prominence_ratio: float = 0.80
    random_seed: int = 20260714


REPRESENTATIONS = [
    "template",
    "unaligned_mean",
    "integer_aligned_mean",
    "fractional_aligned_mean",
    "fractional_aligned_median",
    "fractional_aligned_trimmed_mean",
]

EXPLICIT_FAILURE_MODES = [
    "snippet_truncated_before_peak",
    "waveform_monotonic_recovery",
    "flat_recovery_no_local_maximum",
    "candidate_peak_below_rebound_threshold",
    "peak_at_right_boundary",
    "multiple_competing_peaks",
    "positive_polarity_waveform",
    "alignment_failure",
    "template_snippet_disagreement",
    "other",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classification-dir", type=Path, default=DEFAULT_AUDIT_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-units", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    classification_dir = args.classification_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    config = AuditConfig()
    alignment_config = AlignmentConfig()

    import spikeinterface.full as si

    strict = pd.read_csv(classification_dir / "robust_pchip_unit_metrics.csv")
    if args.max_units is not None:
        strict = strict.head(args.max_units).copy()
    metric_rows: list[dict[str, Any]] = []
    trace_frames: list[pd.DataFrame] = []
    errors: list[dict[str, Any]] = []

    analyzer_groups = strict.groupby("analyzer_path", sort=False)
    for analyzer_number, (analyzer_path_text, group) in enumerate(analyzer_groups, start=1):
        analyzer_path = Path(str(analyzer_path_text))
        print(
            f"[{analyzer_number}/{strict['analyzer_path'].nunique()}] "
            f"{analyzer_path} ({len(group)} units)",
            flush=True,
        )
        try:
            analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
            sorting = analyzer.sorting
            recording = analyzer.recording
            templates_ext = analyzer.get_extension("templates")
            random_ext = analyzer.get_extension("random_spikes")
            if templates_ext is None or random_ext is None:
                raise ValueError("templates and random_spikes extensions are required")
            templates = _templates_average(templates_ext)
            analyzer_channel_ids = np.asarray(analyzer.channel_ids)
            recording_channel_ids = np.asarray(recording.get_channel_ids())
            channel_axis_matches = bool(
                templates.shape[2] == analyzer_channel_ids.size
                and np.array_equal(analyzer_channel_ids, recording_channel_ids)
            )
            if not channel_axis_matches:
                raise ValueError(
                    "template channel axis does not match analyzer/recording channel ordering"
                )
            sampling_frequency = float(recording.get_sampling_frequency())
            if not np.isclose(sampling_frequency, config.sampling_frequency_hz, atol=1e-6):
                raise ValueError(f"unexpected sampling frequency {sampling_frequency}")
            nbefore = int(templates_ext.nbefore)
            nafter = int(templates_ext.nafter)
            unit_ids = list(sorting.get_unit_ids())
            recording_class_name = (
                f"{type(recording).__module__}.{type(recording).__name__}"
            )
            analyzer_sparsity_present = analyzer.sparsity is not None
        except Exception as exc:  # noqa: BLE001
            for _, row in group.iterrows():
                errors.append(_error_row(row, exc))
            continue

        for _, strict_row in group.iterrows():
            try:
                unit_index = int(strict_row["unit_index"])
                unit_id = unit_ids[unit_index]
                template = np.asarray(templates[unit_index], dtype=float)
                template_ptp = np.ptp(template, axis=0)
                template_best_index = int(np.nanargmax(template_ptp))
                template_best = _baseline_center(template[:, template_best_index], nbefore)
                template_trough_index = _central_trough_index(
                    template_best, nbefore, alignment_config
                )
                all_snippets, selected_count = _extract_all_channel_snippets(
                    recording,
                    sorting,
                    random_ext,
                    unit_id,
                    analyzer_channel_ids,
                    nbefore,
                    nafter,
                )
                if len(all_snippets) < alignment_config.min_usable_snippets:
                    raise ValueError(f"only {len(all_snippets)} usable persisted snippets")
                all_snippets = np.stack(
                    [
                        _baseline_center_multichannel(snippet, nbefore)
                        for snippet in all_snippets
                    ],
                    axis=0,
                )
                best_snippets = all_snippets[:, :, template_best_index]
                local_troughs = _local_trough_indices(
                    best_snippets, template_trough_index, alignment_config
                )
                integer_shifts = local_troughs - template_trough_index
                integer_aligned_all = _apply_integer_shifts(all_snippets, integer_shifts)
                _, fractional_shifts, fractional_correlations = _fractionally_align_snippets(
                    best_snippets,
                    template_best,
                    template_trough_index,
                    alignment_config,
                )
                fractional_aligned_all = _apply_fractional_shifts(
                    all_snippets, fractional_shifts
                )
                valid_alignment = (
                    np.isfinite(fractional_shifts)
                    & (
                        np.isfinite(fractional_aligned_all).sum(axis=(1, 2))
                        >= fractional_aligned_all.shape[1] * fractional_aligned_all.shape[2] // 2
                    )
                )
                if valid_alignment.sum() < alignment_config.min_usable_snippets:
                    raise ValueError(
                        f"only {int(valid_alignment.sum())} snippets survived fractional alignment"
                    )
                fractional_aligned_all = fractional_aligned_all[valid_alignment]
                fractional_shifts = fractional_shifts[valid_alignment]
                fractional_correlations = fractional_correlations[valid_alignment]
                integer_aligned_all = integer_aligned_all[
                    np.isfinite(integer_aligned_all).sum(axis=(1, 2))
                    >= integer_aligned_all.shape[1] * integer_aligned_all.shape[2] // 2
                ]

                unaligned_mean_all = _repair_multichannel(np.nanmean(all_snippets, axis=0))
                integer_mean_all = _repair_multichannel(
                    np.nanmean(integer_aligned_all, axis=0)
                )
                fractional_mean_all = _repair_multichannel(
                    np.nanmean(fractional_aligned_all, axis=0)
                )
                fractional_median_all = _repair_multichannel(
                    np.nanmedian(fractional_aligned_all, axis=0)
                )
                fractional_trimmed_all = _repair_multichannel(
                    _nan_trimmed_mean(
                        fractional_aligned_all,
                        proportion=config.trimmed_fraction_each_tail,
                    )
                )
                representations = {
                    "template": template_best,
                    "unaligned_mean": unaligned_mean_all[:, template_best_index],
                    "integer_aligned_mean": integer_mean_all[:, template_best_index],
                    "fractional_aligned_mean": fractional_mean_all[:, template_best_index],
                    "fractional_aligned_median": fractional_median_all[:, template_best_index],
                    "fractional_aligned_trimmed_mean": fractional_trimmed_all[
                        :, template_best_index
                    ],
                }
                measurements = {
                    name: _measure_representation(
                        waveform,
                        template_trough_index,
                        config,
                    )
                    for name, waveform in representations.items()
                }
                mean_best_index = int(
                    np.nanargmax(np.ptp(fractional_mean_all, axis=0))
                )
                median_best_index = int(
                    np.nanargmax(np.ptp(fractional_median_all, axis=0))
                )
                template_mean_corr, template_mean_nrmse = _agreement(
                    template_best, representations["fractional_aligned_mean"]
                )
                template_median_corr, template_median_nrmse = _agreement(
                    template_best, representations["fractional_aligned_median"]
                )
                template_trim_corr, template_trim_nrmse = _agreement(
                    template_best, representations["fractional_aligned_trimmed_mean"]
                )
                primary = measurements["fractional_aligned_mean"]
                failure_mode = _assign_failure_mode(
                    primary,
                    measurements,
                    template_mean_corr,
                    template_mean_nrmse,
                    fractional_correlations,
                    config,
                )
                sample_time_ms = (
                    np.arange(template.shape[0], dtype=float)
                    * 1000.0
                    / config.sampling_frequency_hz
                )
                available_after_trough_ms = float(
                    sample_time_ms[-1] - sample_time_ms[template_trough_index]
                )
                main_negative = _main_deflection_is_negative(template_best)
                row: dict[str, Any] = {
                    "unit_key": strict_row["unit_key"],
                    "source_platform": strict_row["source_platform"],
                    "recording": strict_row["recording"],
                    "well": strict_row["well"],
                    "unit_id": strict_row["unit_id"],
                    "analyzer_path": str(analyzer_path),
                    "recording_processing_variant": _recording_processing_variant(
                        analyzer_path
                    ),
                    "unit_index": unit_index,
                    "old_rs_fs_class": strict_row["old_rs_fs_class"],
                    "strict_pchip_class": strict_row["new_rs_fs_class"],
                    "strict_classification_transition": strict_row[
                        "classification_transition"
                    ],
                    "nbefore": nbefore,
                    "nafter": nafter,
                    "total_waveform_samples": nbefore + nafter,
                    "sampling_frequency_hz": sampling_frequency,
                    "recording_class_name": recording_class_name,
                    "analyzer_sparsity_present": analyzer_sparsity_present,
                    "sample_interval_ms": 1000.0 / sampling_frequency,
                    "template_trough_sample": template_trough_index,
                    "available_time_after_template_trough_ms": available_after_trough_ms,
                    "post_trough_window_is_at_least_1ms": available_after_trough_ms >= 1.0,
                    "post_trough_window_is_at_least_1_5ms": available_after_trough_ms >= 1.5,
                    "template_channel_axis_count": template.shape[1],
                    "analyzer_channel_count": analyzer_channel_ids.size,
                    "channel_axis_order_matches": channel_axis_matches,
                    "template_best_channel_index": template_best_index,
                    "template_best_channel_id": analyzer_channel_ids[template_best_index],
                    "aligned_mean_best_channel_index": mean_best_index,
                    "aligned_mean_best_channel_id": analyzer_channel_ids[mean_best_index],
                    "aligned_median_best_channel_index": median_best_index,
                    "aligned_median_best_channel_id": analyzer_channel_ids[median_best_index],
                    "template_vs_mean_best_channel_differs": mean_best_index
                    != template_best_index,
                    "template_vs_median_best_channel_differs": median_best_index
                    != template_best_index,
                    "template_main_deflection_is_negative": main_negative,
                    "positive_polarity_flag": not main_negative,
                    "persisted_random_spikes_selected": selected_count,
                    "usable_snippets": all_snippets.shape[0],
                    "median_snippet_trough_sample_before_alignment": float(
                        np.median(local_troughs)
                    ),
                    "min_snippet_trough_sample_before_alignment": int(
                        np.min(local_troughs)
                    ),
                    "max_snippet_trough_sample_before_alignment": int(
                        np.max(local_troughs)
                    ),
                    "std_snippet_trough_sample_before_alignment": float(
                        np.std(local_troughs, ddof=1)
                    ),
                    "integer_shift_median_samples": float(np.median(integer_shifts)),
                    "integer_shift_range_samples": float(
                        np.max(integer_shifts) - np.min(integer_shifts)
                    ),
                    "fractional_shift_median_samples": float(
                        np.median(fractional_shifts)
                    ),
                    "fractional_shift_min_samples": float(np.min(fractional_shifts)),
                    "fractional_shift_max_samples": float(np.max(fractional_shifts)),
                    "fractional_shift_std_samples": float(
                        np.std(fractional_shifts, ddof=1)
                    ),
                    "crosscorr_minus_integer_abs_median_samples": float(
                        np.median(
                            np.abs(
                                fractional_shifts
                                - integer_shifts[valid_alignment]
                            )
                        )
                    ),
                    "crosscorr_minus_integer_gt1_fraction": float(
                        np.mean(
                            np.abs(
                                fractional_shifts
                                - integer_shifts[valid_alignment]
                            )
                            > 1.0
                        )
                    ),
                    "fractional_alignment_correlation_median": float(
                        np.median(fractional_correlations)
                    ),
                    "template_aligned_mean_correlation": template_mean_corr,
                    "template_aligned_mean_nrmse": template_mean_nrmse,
                    "template_aligned_median_correlation": template_median_corr,
                    "template_aligned_median_nrmse": template_median_nrmse,
                    "template_aligned_trimmed_mean_correlation": template_trim_corr,
                    "template_aligned_trimmed_mean_nrmse": template_trim_nrmse,
                    "primary_failure_mode": failure_mode,
                }
                for name, measurement in measurements.items():
                    for key, value in measurement.items():
                        row[f"{name}_{key}"] = value
                    row[f"{name}_class_at_0_5ms"] = _classify_ttp(
                        measurement["trough_to_peak_duration_ms"],
                        config.fs_cutoff_ms,
                    )
                row["rescued_by_aligned_mean"] = (
                    strict_row["new_rs_fs_class"] == "unclassified"
                    and primary["peak_valid"]
                )
                row["rescued_by_trimmed_mean"] = (
                    strict_row["new_rs_fs_class"] == "unclassified"
                    and measurements["fractional_aligned_trimmed_mean"]["peak_valid"]
                )
                row["lost_only_with_median"] = (
                    not measurements["fractional_aligned_median"]["peak_valid"]
                    and (
                        primary["peak_valid"]
                        or measurements["fractional_aligned_trimmed_mean"]["peak_valid"]
                    )
                )
                row["requires_polarity_or_orientation_review"] = (
                    failure_mode == "positive_polarity_waveform"
                )
                row["any_representation_has_valid_peak"] = any(
                    measurements[name]["peak_valid"] for name in REPRESENTATIONS
                )
                row["genuinely_unmeasurable_after_audit"] = (
                    not row["any_representation_has_valid_peak"]
                    and not row["requires_polarity_or_orientation_review"]
                )
                metric_rows.append(row)
                trace_frames.append(
                    pd.DataFrame(
                        {
                            "unit_key": strict_row["unit_key"],
                            "sample_index": np.arange(template.shape[0], dtype=int),
                            "sample_time_ms": sample_time_ms,
                            "time_from_template_trough_ms": sample_time_ms
                            - sample_time_ms[template_trough_index],
                            **{
                                f"{name}_uV": waveform
                                for name, waveform in representations.items()
                            },
                        }
                    )
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(_error_row(strict_row, exc))

    metrics = pd.DataFrame(metric_rows)
    traces = pd.concat(trace_frames, ignore_index=True) if trace_frames else pd.DataFrame()
    errors_table = pd.DataFrame(errors)
    errors_path = output_dir / "waveform_source_audit_errors.csv"
    if not errors_table.empty:
        errors_table.to_csv(errors_path, index=False)
    if len(metrics) != len(strict) or not errors_table.empty:
        raise RuntimeError(
            f"Waveform-source audit completed {len(metrics)}/{len(strict)} units; "
            f"errors={len(errors_table)} ({errors_path})"
        )

    metrics_path = output_dir / "waveform_source_audit_unit_metrics.csv"
    traces_path = output_dir / "waveform_source_audit_representations.csv.gz"
    failure_counts_path = output_dir / "waveform_source_audit_failure_mode_counts.csv"
    summary_path = output_dir / "waveform_source_audit_summary.json"
    selection_path = output_dir / "waveform_source_audit_diagnostic_selection.csv"
    pdf_path = output_dir / "waveform_source_audit_diagnostics.pdf"
    metrics.to_csv(metrics_path, index=False)
    traces.to_csv(traces_path, index=False, compression="gzip")
    strict_unclassified = metrics["strict_pchip_class"].eq("unclassified")
    strict_outcomes = metrics.loc[
        strict_unclassified, "primary_failure_mode"
    ].replace({"valid_peak": "rescued_valid_peak_with_aligned_mean"})
    failure_order = ["rescued_valid_peak_with_aligned_mean", *EXPLICIT_FAILURE_MODES]
    failure_counts = (
        strict_outcomes.value_counts(dropna=False)
        .reindex(failure_order, fill_value=0)
        .rename_axis("failure_mode")
        .rename("unit_count")
        .reset_index()
    )
    failure_counts.to_csv(failure_counts_path, index=False)
    selection = _diagnostic_selection(metrics, config)
    selection.to_csv(selection_path, index=False)
    _plot_diagnostic_pdf(metrics, traces, selection, config, pdf_path)
    summary = _summary(metrics, failure_counts, config)
    summary["generated_at"] = datetime.now().isoformat(timespec="seconds")
    summary["outputs"] = {
        "unit_metrics": str(metrics_path),
        "representations": str(traces_path),
        "failure_mode_counts": str(failure_counts_path),
        "diagnostic_selection": str(selection_path),
        "diagnostic_pdf": str(pdf_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print("\nFailure modes among strict-unclassified units:")
    print(failure_counts.to_string(index=False))
    print("\nSummary:")
    print(json.dumps(summary, indent=2, default=str))
    return 0


def _extract_all_channel_snippets(
    recording,
    sorting,
    random_ext,
    unit_id: Any,
    channel_ids: np.ndarray,
    nbefore: int,
    nafter: int,
) -> tuple[list[np.ndarray], int]:
    snippets: list[np.ndarray] = []
    selected_total = 0
    for segment_index in range(sorting.get_num_segments()):
        spike_train = np.asarray(
            sorting.get_unit_spike_train(unit_id=unit_id, segment_index=segment_index),
            dtype=np.int64,
        )
        selected = np.asarray(
            random_ext.get_selected_indices_in_spike_train(unit_id, segment_index),
            dtype=np.int64,
        )
        selected = selected[(selected >= 0) & (selected < spike_train.size)]
        selected_total += int(selected.size)
        num_samples = int(recording.get_num_samples(segment_index=segment_index))
        for frame in spike_train[selected]:
            start, end = int(frame) - nbefore, int(frame) + nafter
            if start < 0 or end > num_samples:
                continue
            snippet = np.asarray(
                recording.get_traces(
                    segment_index=segment_index,
                    start_frame=start,
                    end_frame=end,
                    channel_ids=channel_ids,
                    return_in_uV=True,
                ),
                dtype=float,
            )
            if snippet.shape == (nbefore + nafter, channel_ids.size):
                snippets.append(snippet)
    return snippets, selected_total


def _baseline_center_multichannel(values: np.ndarray, nbefore: int) -> np.ndarray:
    baseline_stop = max(3, nbefore - 6)
    return values - np.median(values[:baseline_stop], axis=0, keepdims=True)


def _local_trough_indices(
    snippets: np.ndarray, target_index: int, config: AlignmentConfig
) -> np.ndarray:
    radius = max(
        1,
        int(
            round(
                config.local_trough_radius_ms
                * config.sampling_frequency_hz
                / 1000.0
            )
        ),
    )
    left = max(0, target_index - radius)
    right = min(snippets.shape[1], target_index + radius + 1)
    return left + np.argmin(snippets[:, left:right], axis=1)


def _apply_integer_shifts(values: np.ndarray, shifts: np.ndarray) -> np.ndarray:
    aligned = np.full_like(values, np.nan, dtype=float)
    n_samples = values.shape[1]
    for row_index, shift in enumerate(shifts.astype(int)):
        source = np.arange(n_samples) + shift
        valid = (source >= 0) & (source < n_samples)
        aligned[row_index, valid] = values[row_index, source[valid]]
    return aligned


def _apply_fractional_shifts(values: np.ndarray, shifts: np.ndarray) -> np.ndarray:
    sample_index = np.arange(values.shape[1], dtype=float)
    aligned = np.full_like(values, np.nan, dtype=float)
    for row_index, shift in enumerate(shifts):
        if not np.isfinite(shift):
            continue
        interpolator = PchipInterpolator(
            sample_index, values[row_index], axis=0, extrapolate=False
        )
        aligned[row_index] = interpolator(sample_index + shift)
    return aligned


def _nan_trimmed_mean(values: np.ndarray, proportion: float) -> np.ndarray:
    sorted_values = np.sort(values, axis=0)
    finite_counts = np.isfinite(sorted_values).sum(axis=0)
    low = np.floor(proportion * finite_counts).astype(int)
    high = finite_counts - low
    cumulative = np.nancumsum(sorted_values, axis=0)
    high_index = np.maximum(high - 1, 0)[None, ...]
    high_sum = np.take_along_axis(cumulative, high_index, axis=0)[0]
    low_index = np.maximum(low - 1, 0)[None, ...]
    low_sum = np.take_along_axis(cumulative, low_index, axis=0)[0]
    low_sum = np.where(low > 0, low_sum, 0.0)
    denominator = high - low
    return np.divide(
        high_sum - low_sum,
        denominator,
        out=np.full_like(high_sum, np.nan, dtype=float),
        where=denominator > 0,
    )


def _repair_multichannel(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float).copy()
    sample_index = np.arange(values.shape[0], dtype=float)
    for channel_index in range(values.shape[1]):
        finite = np.isfinite(values[:, channel_index])
        if finite.sum() < 3:
            raise ValueError(f"channel {channel_index} has fewer than three finite samples")
        if not finite.all():
            values[:, channel_index] = np.interp(
                sample_index,
                sample_index[finite],
                values[finite, channel_index],
            )
    return values


def _measure_representation(
    waveform: np.ndarray,
    expected_trough_index: int,
    config: AuditConfig,
) -> dict[str, Any]:
    waveform = np.asarray(waveform, dtype=float)
    sample_time = (
        np.arange(waveform.size, dtype=float) * 1000.0 / config.sampling_frequency_hz
    )
    dense_time = np.arange(
        sample_time[0],
        sample_time[-1] + 0.5 * config.dense_step_ms,
        config.dense_step_ms,
    )
    dense_wave = PchipInterpolator(sample_time, waveform)(dense_time)
    baseline_stop = max(3, expected_trough_index - 6)
    baseline = float(np.median(waveform[:baseline_stop]))
    expected_time = float(sample_time[expected_trough_index])
    trough_candidates = np.flatnonzero(
        (dense_time >= expected_time - 0.40) & (dense_time <= expected_time + 0.40)
    )
    trough_index = int(
        trough_candidates[np.argmin(dense_wave[trough_candidates])]
    )
    trough_time = float(dense_time[trough_index])
    trough_value = float(dense_wave[trough_index])
    trough_amplitude = baseline - trough_value
    main_negative = trough_amplitude > 0 and _main_deflection_is_negative(waveform)
    search_start = trough_time + config.search_start_after_trough_ms
    search_end = min(
        trough_time + config.search_end_after_trough_ms,
        sample_time[-1] - config.edge_guard_ms,
    )
    search_indices = np.flatnonzero(
        (dense_time >= search_start) & (dense_time <= search_end)
    )
    final_slope = _edge_slope(sample_time, waveform)
    rising_edge = bool(
        final_slope
        > max(
            config.rising_edge_min_slope_uV_per_ms,
            0.02 * max(trough_amplitude, 0.0) / (1000.0 / config.sampling_frequency_hz),
        )
    )
    result: dict[str, Any] = {
        "baseline_uV": baseline,
        "trough_time_ms": trough_time,
        "trough_sample_continuous": trough_time * config.sampling_frequency_hz / 1000.0,
        "trough_uV": trough_value,
        "search_start_ms": search_start,
        "search_end_ms": search_end,
        "available_after_trough_ms": sample_time[-1] - trough_time,
        "final_slope_uV_per_ms": final_slope,
        "rising_at_final_sample": rising_edge,
        "main_deflection_is_negative": main_negative,
        "peak_valid": False,
        "peak_time_ms": np.nan,
        "peak_uV": np.nan,
        "trough_to_peak_duration_ms": np.nan,
        "qualifying_peak_count": 0,
        "all_local_peak_count": 0,
        "peak_status": "unmeasured",
        "failed_candidate_time_ms": np.nan,
        "failed_candidate_uV": np.nan,
        "multiple_competing_peaks": False,
    }
    if not main_negative:
        result["peak_status"] = "positive_polarity_waveform"
        return result
    if search_indices.size < 3:
        result["peak_status"] = "snippet_truncated_before_peak"
        return result
    search_wave = dense_wave[search_indices]
    all_peaks, all_properties = find_peaks(
        search_wave,
        prominence=max(0.05, 0.005 * trough_amplitude),
    )
    threshold = trough_value + config.min_recovery_fraction * trough_amplitude
    prominence = max(
        config.min_prominence_uV,
        config.min_prominence_fraction * trough_amplitude,
    )
    qualifying, properties = find_peaks(
        search_wave,
        height=threshold,
        prominence=prominence,
        distance=max(1, int(round(0.08 / config.dense_step_ms))),
    )
    result["all_local_peak_count"] = int(all_peaks.size)
    result["qualifying_peak_count"] = int(qualifying.size)
    if qualifying.size:
        peak_index = int(search_indices[int(qualifying[0])])
        result.update(
            {
                "peak_valid": True,
                "peak_time_ms": float(dense_time[peak_index]),
                "peak_uV": float(dense_wave[peak_index]),
                "trough_to_peak_duration_ms": float(
                    dense_time[peak_index] - trough_time
                ),
                "peak_prominence_uV": float(properties["prominences"][0]),
                "peak_status": "first_meaningful_positive_going_local_maximum",
            }
        )
        if qualifying.size > 1:
            prominences = properties["prominences"]
            result["multiple_competing_peaks"] = bool(
                prominences[1] >= config.competing_peak_prominence_ratio * prominences[0]
            )
        else:
            result["multiple_competing_peaks"] = False
        return result
    if all_peaks.size:
        result["peak_status"] = "candidate_peak_below_rebound_threshold"
        candidate_index = int(search_indices[int(all_peaks[0])])
        result["failed_candidate_time_ms"] = float(dense_time[candidate_index])
        result["failed_candidate_uV"] = float(dense_wave[candidate_index])
    elif rising_edge:
        result["peak_status"] = "peak_at_right_boundary"
        result["failed_candidate_time_ms"] = float(dense_time[search_indices[-1]])
        result["failed_candidate_uV"] = float(dense_wave[search_indices[-1]])
    else:
        derivative = np.diff(search_wave)
        positive_fraction = float(np.mean(derivative >= 0)) if derivative.size else np.nan
        recovery_range = float(np.ptp(search_wave))
        if positive_fraction >= 0.80:
            result["peak_status"] = "waveform_monotonic_recovery"
        elif recovery_range <= max(0.5, 0.05 * trough_amplitude):
            result["peak_status"] = "flat_recovery_no_local_maximum"
        else:
            result["peak_status"] = "other"
    return result


def _assign_failure_mode(
    primary: dict[str, Any],
    measurements: dict[str, dict[str, Any]],
    template_mean_corr: float,
    template_mean_nrmse: float,
    fractional_correlations: np.ndarray,
    config: AuditConfig,
) -> str:
    if primary["peak_valid"]:
        return "valid_peak"
    if not primary["main_deflection_is_negative"]:
        return "positive_polarity_waveform"
    if np.nanmedian(fractional_correlations) < config.alignment_failure_correlation:
        return "alignment_failure"
    if (
        measurements["template"]["peak_valid"]
        and not primary["peak_valid"]
        and (
            template_mean_corr < config.template_disagreement_correlation
            or template_mean_nrmse > config.template_disagreement_nrmse
        )
    ):
        return "template_snippet_disagreement"
    status = str(primary["peak_status"])
    allowed = {
        "snippet_truncated_before_peak",
        "waveform_monotonic_recovery",
        "flat_recovery_no_local_maximum",
        "candidate_peak_below_rebound_threshold",
        "peak_at_right_boundary",
        "positive_polarity_waveform",
        "alignment_failure",
        "template_snippet_disagreement",
        "other",
        "multiple_competing_peaks",
    }
    return status if status in allowed else "other"


def _agreement(reference: np.ndarray, comparison: np.ndarray) -> tuple[float, float]:
    reference = reference - np.mean(reference)
    comparison = comparison - np.mean(comparison)
    denom = float(np.linalg.norm(reference) * np.linalg.norm(comparison))
    correlation = float(np.dot(reference, comparison) / denom) if denom > 0 else np.nan
    scale = float(np.ptp(reference))
    nrmse = (
        float(np.sqrt(np.mean((comparison - reference) ** 2)) / scale)
        if scale > 0
        else np.nan
    )
    return correlation, nrmse


def _classify_ttp(value: Any, cutoff_ms: float) -> str:
    try:
        ttp_ms = float(value)
    except (TypeError, ValueError):
        return "unclassified"
    if not np.isfinite(ttp_ms):
        return "unclassified"
    return "FS" if ttp_ms <= cutoff_ms else "RS"


def _recording_processing_variant(analyzer_path: Path) -> str:
    path_text = str(analyzer_path)
    patterns = [
        ("_broadband_processor_raw/", "broadband_processor_raw"),
        ("_filter_200Hz-3kHz/", "filter_200Hz-3kHz"),
        (
            "_primary_Neural_Broadband_hp_0.1_Hz_IIR_lp_None/",
            "primary_hp0.1_IIR_lp_None",
        ),
        (
            "_primary_Neural_Broadband_hp_0.1_Hz_IIR_lp/",
            "primary_hp0.1_IIR_lp",
        ),
    ]
    for marker, label in patterns:
        if marker in path_text:
            return label
    return "other_non_LFP"


def _main_deflection_is_negative(waveform: np.ndarray) -> bool:
    baseline = float(np.median(waveform[:6]))
    negative = baseline - float(np.min(waveform))
    positive = float(np.max(waveform)) - baseline
    return bool(negative >= positive)


def _edge_slope(time_ms: np.ndarray, waveform: np.ndarray) -> float:
    count = min(5, waveform.size)
    return float(np.polyfit(time_ms[-count:], waveform[-count:], deg=1)[0])


def _diagnostic_selection(metrics: pd.DataFrame, config: AuditConfig) -> pd.DataFrame:
    rng = np.random.default_rng(config.random_seed)
    groups: list[pd.DataFrame] = []

    def choose(label: str, frame: pd.DataFrame, n: int | None) -> None:
        if n is not None and len(frame) > n:
            frame = frame.iloc[np.sort(rng.choice(len(frame), size=n, replace=False))]
        selected = frame[["unit_key"]].copy()
        selected["diagnostic_group"] = label
        selected["group_order"] = np.arange(1, len(selected) + 1)
        groups.append(selected)

    choose(
        "random_strict_classified",
        metrics.loc[metrics["strict_pchip_class"].isin(["FS", "RS"])],
        10,
    )
    choose(
        "random_strict_unclassified",
        metrics.loc[metrics["strict_pchip_class"].eq("unclassified")],
        10,
    )
    choose(
        "formerly_RS_strict_unclassified",
        metrics.loc[
            metrics["old_rs_fs_class"].eq("RS")
            & metrics["strict_pchip_class"].eq("unclassified")
        ],
        10,
    )
    choose(
        "all_formerly_FS_strict_unclassified",
        metrics.loc[
            metrics["old_rs_fs_class"].eq("FS")
            & metrics["strict_pchip_class"].eq("unclassified")
        ],
        None,
    )
    choose(
        "all_direct_FS_RS_switchers",
        metrics.loc[
            metrics["strict_pchip_class"].isin(["FS", "RS"])
            & metrics["old_rs_fs_class"].ne(metrics["strict_pchip_class"])
        ],
        None,
    )
    choose(
        "highest_template_mean_disagreement",
        metrics.sort_values(
            ["template_aligned_mean_correlation", "template_aligned_mean_nrmse"],
            ascending=[True, False],
        ),
        10,
    )
    return pd.concat(groups, ignore_index=True)


def _plot_diagnostic_pdf(
    metrics: pd.DataFrame,
    traces: pd.DataFrame,
    selection: pd.DataFrame,
    config: AuditConfig,
    path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    colors = {
        "template": "#111111",
        "unaligned_mean": "#999999",
        "integer_aligned_mean": "#7A9A78",
        "fractional_aligned_mean": "#C87932",
        "fractional_aligned_median": "#58758E",
        "fractional_aligned_trimmed_mean": "#8B6F47",
    }
    metric_lookup = metrics.set_index("unit_key")
    with PdfPages(path) as pdf:
        for group_name, group in selection.groupby("diagnostic_group", sort=False):
            for page_start in range(0, len(group), 4):
                page = group.iloc[page_start : page_start + 4]
                fig, axes = plt.subplots(2, 2, figsize=(11.0, 8.0), squeeze=False)
                for ax in axes.ravel():
                    ax.set_visible(False)
                for ax, (_, selected) in zip(axes.ravel(), page.iterrows(), strict=False):
                    ax.set_visible(True)
                    unit_key = selected["unit_key"]
                    row = metric_lookup.loc[unit_key]
                    unit_trace = traces.loc[traces["unit_key"].eq(unit_key)].sort_values(
                        "sample_index"
                    )
                    primary_trough = float(row["fractional_aligned_mean_trough_time_ms"])
                    x = unit_trace["sample_time_ms"].to_numpy(float) - primary_trough
                    for name in REPRESENTATIONS:
                        y = unit_trace[f"{name}_uV"].to_numpy(float)
                        ax.plot(
                            x,
                            y,
                            color=colors[name],
                            lw=1.35 if name in {"template", "fractional_aligned_mean"} else 0.9,
                            alpha=0.92,
                            label=name.replace("_", " "),
                        )
                    primary_y = unit_trace["fractional_aligned_mean_uV"].to_numpy(float)
                    ax.scatter(x, primary_y, s=8, color=colors["fractional_aligned_mean"], zorder=4)
                    dense_x = np.arange(x[0], x[-1] + 0.5 * config.dense_step_ms, config.dense_step_ms)
                    dense_y = PchipInterpolator(x, primary_y)(dense_x)
                    ax.plot(dense_x, dense_y, color="#D55E00", lw=0.75, alpha=0.75)
                    ax.axvline(0, color="#222222", lw=0.7, ls="--")
                    search_start = float(row["fractional_aligned_mean_search_start_ms"]) - primary_trough
                    search_end = float(row["fractional_aligned_mean_search_end_ms"]) - primary_trough
                    ax.axvline(search_start, color="#777777", lw=0.65, ls=":")
                    ax.axvline(search_end, color="#777777", lw=0.65, ls=":")
                    trough_uV = float(row["fractional_aligned_mean_trough_uV"])
                    ax.scatter([0], [trough_uV], s=22, color="#111111", zorder=6)
                    if bool(row["fractional_aligned_mean_peak_valid"]):
                        peak_x = float(row["fractional_aligned_mean_peak_time_ms"]) - primary_trough
                        peak_y = float(row["fractional_aligned_mean_peak_uV"])
                        ax.scatter([peak_x], [peak_y], s=24, color="#D55E00", zorder=6)
                    elif np.isfinite(
                        float(row["fractional_aligned_mean_failed_candidate_time_ms"])
                    ):
                        failed_x = (
                            float(
                                row[
                                    "fractional_aligned_mean_failed_candidate_time_ms"
                                ]
                            )
                            - primary_trough
                        )
                        failed_y = float(
                            row["fractional_aligned_mean_failed_candidate_uV"]
                        )
                        ax.scatter(
                            [failed_x],
                            [failed_y],
                            s=30,
                            facecolors="none",
                            edgecolors="#D55E00",
                            marker="X",
                            linewidths=0.9,
                            zorder=6,
                        )
                    ax.set_xlim(-0.80, 1.95)
                    ax.axhline(0, color="#DDDDDD", lw=0.5)
                    ax.set_title(
                        f"{row['source_platform']} {row['well']} u{row['unit_id']} · "
                        f"{row['old_rs_fs_class']}→{row['strict_pchip_class']}\n"
                        f"mean audit: {row['fractional_aligned_mean_peak_status']} · "
                        f"failure: {row['primary_failure_mode']}",
                        fontsize=8,
                        loc="left",
                    )
                    ax.set_xlabel("Time from aligned trough (ms)")
                    ax.set_ylabel("Amplitude (µV)")
                    ax.spines[["top", "right"]].set_visible(False)
                handles, labels = axes.ravel()[0].get_legend_handles_labels()
                fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False, fontsize=7)
                fig.suptitle(
                    f"Waveform-source audit · {group_name} · page {page_start // 4 + 1}",
                    fontsize=12,
                    fontweight="bold",
                )
                fig.tight_layout(rect=[0.02, 0.07, 0.98, 0.95])
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)


def _summary(
    metrics: pd.DataFrame, failure_counts: pd.DataFrame, config: AuditConfig
) -> dict[str, Any]:
    strict_unclassified = metrics["strict_pchip_class"].eq("unclassified")
    gt1 = metrics["crosscorr_minus_integer_gt1_fraction"]
    representation_counts: dict[str, Any] = {}
    for name in REPRESENTATIONS:
        class_column = f"{name}_class_at_0_5ms"
        transition = (
            metrics["old_rs_fs_class"].astype(str)
            + "→"
            + metrics[class_column].astype(str)
        )
        representation_counts[name] = {
            "valid_peak_count": int(metrics[f"{name}_peak_valid"].sum()),
            "class_counts": {
                label: int((metrics[class_column] == label).sum())
                for label in ["FS", "RS", "unclassified"]
            },
            "strict_unclassified_valid_peak_count": int(
                metrics.loc[strict_unclassified, f"{name}_peak_valid"].sum()
            ),
            "transition_counts_from_original_labels": {
                label: int(count)
                for label, count in transition.value_counts().sort_index().items()
            },
            "changed_count_including_unclassified": int(
                metrics["old_rs_fs_class"].ne(metrics[class_column]).sum()
            ),
            "direct_FS_RS_switcher_count": int(
                (
                    metrics[class_column].isin(["FS", "RS"])
                    & metrics["old_rs_fs_class"].ne(metrics[class_column])
                ).sum()
            ),
        }
    template_valid = metrics["template_peak_valid"]
    mean_valid = metrics["fractional_aligned_mean_peak_valid"]
    median_valid = metrics["fractional_aligned_median_peak_valid"]
    trimmed_valid = metrics["fractional_aligned_trimmed_mean_peak_valid"]
    processing_variant_breakdown: dict[str, Any] = {}
    for variant, group in metrics.groupby("recording_processing_variant", sort=True):
        group_strict_unclassified = group["strict_pchip_class"].eq("unclassified")
        processing_variant_breakdown[str(variant)] = {
            "unit_count": int(len(group)),
            "strict_unclassified_count": int(group_strict_unclassified.sum()),
            "strict_unclassified_rescued_by_aligned_mean": int(
                group.loc[
                    group_strict_unclassified,
                    "fractional_aligned_mean_peak_valid",
                ].sum()
            ),
            "strict_unclassified_rescued_by_trimmed_mean": int(
                group.loc[
                    group_strict_unclassified,
                    "fractional_aligned_trimmed_mean_peak_valid",
                ].sum()
            ),
            "strict_unclassified_polarity_or_orientation_review": int(
                group.loc[
                    group_strict_unclassified,
                    "requires_polarity_or_orientation_review",
                ].sum()
            ),
            "strict_unclassified_rising_at_final_sample": int(
                group.loc[
                    group_strict_unclassified,
                    "fractional_aligned_mean_rising_at_final_sample",
                ].sum()
            ),
            "strict_unclassified_genuinely_unmeasurable": int(
                group.loc[
                    group_strict_unclassified,
                    "genuinely_unmeasurable_after_audit",
                ].sum()
            ),
            "template_vs_mean_best_channel_differs_count": int(
                group["template_vs_mean_best_channel_differs"].sum()
            ),
        }
    return {
        "unit_count": int(len(metrics)),
        "strict_unclassified_count": int(strict_unclassified.sum()),
        "failure_mode_counts_for_strict_unclassified": failure_counts.set_index(
            "failure_mode"
        )["unit_count"].to_dict(),
        "window": {
            "nbefore_values": sorted(metrics["nbefore"].unique().astype(int).tolist()),
            "nafter_values": sorted(metrics["nafter"].unique().astype(int).tolist()),
            "total_sample_values": sorted(
                metrics["total_waveform_samples"].unique().astype(int).tolist()
            ),
            "minimum_available_after_trough_ms": float(
                metrics["available_time_after_template_trough_ms"].min()
            ),
            "minimum_available_after_aligned_mean_trough_ms": float(
                metrics["fractional_aligned_mean_available_after_trough_ms"].min()
            ),
            "below_1ms_count": int(
                (~metrics["post_trough_window_is_at_least_1ms"]).sum()
            ),
            "below_1_5ms_count": int(
                (~metrics["post_trough_window_is_at_least_1_5ms"]).sum()
            ),
            "aligned_mean_below_1ms_count": int(
                (
                    metrics["fractional_aligned_mean_available_after_trough_ms"]
                    < 1.0
                ).sum()
            ),
            "aligned_mean_below_1_5ms_count": int(
                (
                    metrics["fractional_aligned_mean_available_after_trough_ms"]
                    < 1.5
                ).sum()
            ),
            "aligned_mean_full_1_2ms_search_plus_edge_guard_available_count": int(
                (
                    metrics["fractional_aligned_mean_available_after_trough_ms"]
                    >= config.search_end_after_trough_ms + config.edge_guard_ms
                ).sum()
            ),
            "strict_unclassified_rising_at_final_sample": int(
                metrics.loc[
                    strict_unclassified,
                    "fractional_aligned_mean_rising_at_final_sample",
                ].sum()
            ),
            "strict_unclassified_rising_at_final_sample_by_representation": {
                name: int(
                    metrics.loc[
                        strict_unclassified,
                        f"{name}_rising_at_final_sample",
                    ].sum()
                )
                for name in REPRESENTATIONS
            },
        },
        "channel_and_polarity": {
            "channel_axis_mismatch_count": int(
                (~metrics["channel_axis_order_matches"]).sum()
            ),
            "template_vs_mean_best_channel_differs_count": int(
                metrics["template_vs_mean_best_channel_differs"].sum()
            ),
            "template_vs_median_best_channel_differs_count": int(
                metrics["template_vs_median_best_channel_differs"].sum()
            ),
            "positive_polarity_count": int(metrics["positive_polarity_flag"].sum()),
            "aligned_mean_positive_polarity_count": int(
                (~metrics["fractional_aligned_mean_main_deflection_is_negative"]).sum()
            ),
            "strict_unclassified_aligned_mean_positive_polarity_count": int(
                (
                    strict_unclassified
                    & ~metrics[
                        "fractional_aligned_mean_main_deflection_is_negative"
                    ]
                ).sum()
            ),
            "template_vs_mean_best_channel_differs_percent": float(
                100.0 * metrics["template_vs_mean_best_channel_differs"].mean()
            ),
            "template_vs_median_best_channel_differs_percent": float(
                100.0 * metrics["template_vs_median_best_channel_differs"].mean()
            ),
            "analyzer_sparsity_present_count": int(
                metrics["analyzer_sparsity_present"].sum()
            ),
            "recording_class_names": sorted(
                metrics["recording_class_name"].dropna().astype(str).unique().tolist()
            ),
        },
        "alignment": {
            "median_fractional_alignment_correlation": float(
                metrics["fractional_alignment_correlation_median"].median()
            ),
            "units_with_any_gt1_sample_crosscorr_integer_difference": int(
                (gt1 > 0).sum()
            ),
            "units_with_gt1_sample_difference_for_gt10pct_snippets": int(
                (gt1 > 0.10).sum()
            ),
        },
        "template_vs_snippet": {
            "median_template_aligned_mean_correlation": float(
                metrics["template_aligned_mean_correlation"].median()
            ),
            "median_template_aligned_mean_nrmse": float(
                metrics["template_aligned_mean_nrmse"].median()
            ),
            "median_template_aligned_median_correlation": float(
                metrics["template_aligned_median_correlation"].median()
            ),
            "median_template_aligned_median_nrmse": float(
                metrics["template_aligned_median_nrmse"].median()
            ),
            "high_template_mean_disagreement_count": int(
                (
                    (
                        metrics["template_aligned_mean_correlation"]
                        < config.template_disagreement_correlation
                    )
                    | (
                        metrics["template_aligned_mean_nrmse"]
                        > config.template_disagreement_nrmse
                    )
                ).sum()
            ),
            "template_has_peak_mean_does_not_count": int(
                (template_valid & ~mean_valid).sum()
            ),
            "mean_has_peak_template_does_not_count": int(
                (mean_valid & ~template_valid).sum()
            ),
            "template_and_mean_both_lack_peak_count": int(
                (~template_valid & ~mean_valid).sum()
            ),
        },
        "representation_outcomes": {
            "all_representations": representation_counts,
            "strict_unclassified_rescued_by_aligned_mean": int(
                metrics["rescued_by_aligned_mean"].sum()
            ),
            "strict_unclassified_rescued_by_trimmed_mean": int(
                metrics["rescued_by_trimmed_mean"].sum()
            ),
            "lost_only_when_using_median": int(metrics["lost_only_with_median"].sum()),
            "strict_unclassified_lost_only_when_using_median": int(
                metrics.loc[strict_unclassified, "lost_only_with_median"].sum()
            ),
            "strict_unclassified_requires_polarity_or_orientation_review": int(
                metrics.loc[
                    strict_unclassified,
                    "requires_polarity_or_orientation_review",
                ].sum()
            ),
            "strict_unclassified_rescued_by_any_representation_after_polarity_priority": int(
                (
                    strict_unclassified
                    & metrics["any_representation_has_valid_peak"]
                    & ~metrics["requires_polarity_or_orientation_review"]
                ).sum()
            ),
            "strict_unclassified_valid_only_under_integer_or_unaligned_representation": int(
                (
                    strict_unclassified
                    & metrics["any_representation_has_valid_peak"]
                    & ~metrics[
                        [
                            "fractional_aligned_mean_peak_valid",
                            "fractional_aligned_median_peak_valid",
                            "fractional_aligned_trimmed_mean_peak_valid",
                        ]
                    ].any(axis=1)
                ).sum()
            ),
            "mean_valid_median_invalid_all_units": int(
                (mean_valid & ~median_valid).sum()
            ),
            "trimmed_mean_valid_arithmetic_mean_invalid_all_units": int(
                (trimmed_valid & ~mean_valid).sum()
            ),
            "genuinely_unmeasurable_after_all_checks": int(
                metrics["genuinely_unmeasurable_after_audit"].sum()
            ),
            "strict_unclassified_genuinely_unmeasurable_after_all_checks": int(
                metrics.loc[
                    strict_unclassified,
                    "genuinely_unmeasurable_after_audit",
                ].sum()
            ),
        },
        "signal_processing": {
            "snippet_source": "persisted random_spikes selections from each SortingAnalyzer",
            "baseline_operation": (
                "constant per-channel median subtraction from the pre-spike samples; "
                "this changes waveform offset but not peak or trough timing"
            ),
            "additional_filtering_during_audit": False,
            "non_LFP_processing_variant_breakdown": processing_variant_breakdown,
            "pchip_role": (
                "continuous landmark estimation after waveform aggregation only; "
                "not an increase in acquisition sampling rate"
            ),
        },
        "config": asdict(config),
    }


def _error_row(row: pd.Series, exc: Exception) -> dict[str, Any]:
    return {
        "unit_key": row.get("unit_key"),
        "source_platform": row.get("source_platform"),
        "recording": row.get("recording"),
        "well": row.get("well"),
        "unit_id": row.get("unit_id"),
        "analyzer_path": row.get("analyzer_path"),
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


if __name__ == "__main__":
    raise SystemExit(main())
