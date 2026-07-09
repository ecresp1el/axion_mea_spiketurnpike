#!/usr/bin/env python
"""Plot waveform/KSLabel galleries for Lumos optotag review candidates."""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.launch_step1_sorting_analyzer_browser import DEFAULT_AIND_RESULTS_ROOT  # noqa: E402
from axion_mea.rs_fs_classification import RSFSClassificationConfig  # noqa: E402


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
RECORDING_NAME = "block0_None_recording1.zarr"


@dataclass(frozen=True)
class CandidateWaveform:
    group: str
    review_rank: int
    recording: str
    well: str
    well_column: int
    unit_id: object
    unit_index: int
    kslabel: str
    contam_pct: float
    amplitude: float
    num_spikes: int
    firing_rate_hz: float
    review_sort_peak_raw_response_hz: float
    score_hz: float
    pulse_reliability: float
    best_channel_index: int
    template_ptp_best_channel_uV: float
    template_trough_best_channel_uV: float
    template_peak_best_channel_uV: float
    trough_index: int
    rebound_peak_index: int
    trough_time_ms: float
    rebound_peak_time_ms: float
    trough_to_peak_duration_ms: float
    rep_fraction: float
    rep_threshold_uV: float
    rep_recovery_index: int
    rep_recovery_time_ms: float
    repolarization_time_ms: float
    tentative_rs_fs_classification: str
    spiketurnpike_legacy_cell_type: str
    spiketurnpike_amplitude_uV: float
    pre_peak_index: int
    pre_peak_time_ms: float
    pre_peak_value_uV: float
    post_peak_value_uV: float
    normalized_trough_value: float
    peak1_normalized_amplitude: float
    peak2_normalized_amplitude: float
    peak1_to_trough_ratio: float
    peak2_to_trough_ratio: float
    peak_to_peak_ratio: float
    spike_half_width_ms: float
    half_width_start_index: int
    half_width_end_index: int
    half_width_start_time_ms: float
    half_width_end_time_ms: float
    time_ms: np.ndarray
    template: np.ndarray
    best_waveform_uV: np.ndarray
    normalized_best_waveform: np.ndarray
    analyzer_path: Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_AIND_RESULTS_ROOT)
    parser.add_argument("--date-label", default="20260709")
    parser.add_argument("--top-n-per-group", type=int, default=12)
    parser.add_argument(
        "--rep-fraction",
        type=float,
        choices=(0.25, 0.5, 0.63),
        default=0.5,
        help=(
            "Fraction of trough amplitude used for optional REP/repolarization time. "
            "REP is measured from trough until first recovery to this threshold."
        ),
    )
    parser.add_argument("--same-y-scale", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--mark-trough-peak",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Mark best-channel trough and post-trough rebound peak and label tentative FS/RS.",
    )
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import spikeinterface.full as si

    job_dir = args.job_dir.expanduser().resolve()
    guide_path = job_dir / f"lumos_manual_spike_sorting_guide_jitterwin_{args.date_label}.csv"
    guide = pd.read_csv(guide_path)
    guide = guide.loc[guide["status"].eq("ok")].copy()
    guide["well_column"] = pd.to_numeric(guide["well_column"], errors="coerce")
    guide["review_sort_peak_raw_response_hz"] = pd.to_numeric(
        guide["review_sort_peak_raw_response_hz"], errors="coerce"
    ).fillna(0.0)
    guide = guide.sort_values("review_rank")

    groups = [
        ("columns_4_8_prior", guide.loc[guide["well_column"].between(4, 8)].head(args.top_n_per_group)),
        ("columns_1_3_compare", guide.loc[guide["well_column"].between(1, 3)].head(args.top_n_per_group)),
    ]

    candidates: list[CandidateWaveform] = []
    errors: list[str] = []
    for group_name, group_rows in groups:
        for _, row in group_rows.iterrows():
            analyzer_path = (
                args.results_root.expanduser().resolve()
                / str(row["recording"])
                / str(row["well"])
                / "postprocessed"
                / RECORDING_NAME
            )
            try:
                candidates.append(_load_candidate(si, row, group_name, analyzer_path, args.rep_fraction))
            except Exception as exc:  # noqa: BLE001 - report failed candidates but keep figure useful
                errors.append(
                    f"{group_name} rank={row.get('review_rank')} {row.get('well')} "
                    f"unit={row.get('top_unit')}: {type(exc).__name__}: {exc}"
                )

    if not candidates:
        raise SystemExit("No candidate waveforms could be loaded.")

    summary = pd.DataFrame([_summary_row(candidate) for candidate in candidates])
    summary_path = job_dir / f"lumos_candidate_waveform_kslabel_summary_{args.date_label}.csv"
    summary.to_csv(summary_path, index=False)
    trace_path, npz_path = _write_waveform_cache(candidates, job_dir, args.date_label)

    figure_path = job_dir / f"lumos_candidate_waveform_gallery_columns_compare_{args.date_label}.png"
    _plot_gallery(
        candidates,
        figure_path,
        top_n_per_group=args.top_n_per_group,
        same_y_scale=args.same_y_scale,
        mark_trough_peak=args.mark_trough_peak,
    )
    normalized_figure_path = job_dir / (
        f"lumos_candidate_waveform_best_channel_normalized_vs_unnormalized_{args.date_label}.png"
    )
    _plot_best_channel_normalized_comparison(candidates, normalized_figure_path, top_n_per_group=args.top_n_per_group)

    print(f"Waveform comparison figure: {figure_path}")
    print(f"Normalized/unnormalized best-channel figure: {normalized_figure_path}")
    print(f"Waveform/KSLabel summary CSV: {summary_path}")
    print(f"Best-channel trace table: {trace_path}")
    print(f"Full multi-channel template cache: {npz_path}")
    print("\nKSLabel by group:")
    print(summary.groupby(["group", "KSLabel"]).size().to_string())
    if errors:
        error_path = job_dir / f"lumos_candidate_waveform_gallery_errors_{args.date_label}.txt"
        error_path.write_text("\n".join(errors) + "\n", encoding="utf-8")
        print(f"\nSkipped {len(errors)} candidate(s); details: {error_path}")


def _load_candidate(
    si,
    row: pd.Series,
    group_name: str,
    analyzer_path: Path,
    rep_fraction: float,
) -> CandidateWaveform:
    analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
    sorting = analyzer.sorting
    unit_ids = list(sorting.get_unit_ids())
    unit_id = _match_unit_id(unit_ids, row["top_unit"])
    unit_index = unit_ids.index(unit_id)

    templates_ext = analyzer.get_extension("templates")
    if templates_ext is None:
        raise ValueError(f"missing templates extension: {analyzer_path}")
    try:
        templates = np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        templates_data = templates_ext.get_data()
        if isinstance(templates_data, dict):
            templates_data = templates_data.get("average")
        templates = np.asarray(templates_data, dtype=float)
    if templates.ndim != 3:
        raise ValueError(f"expected templates with shape units x samples x channels, found {templates.shape}")
    template = templates[unit_index]

    channel_ptp = np.ptp(template, axis=0)
    best_channel_index = int(np.nanargmax(channel_ptp))
    best_waveform = template[:, best_channel_index]
    template_ptp = float(np.ptp(best_waveform))
    template_trough = float(np.nanmin(best_waveform))
    template_peak = float(np.nanmax(best_waveform))

    sampling_frequency = float(analyzer.recording.get_sampling_frequency())
    nbefore = int(getattr(templates_ext, "nbefore", np.nanargmin(best_waveform)))
    time_ms = (np.arange(template.shape[0]) - nbefore) / sampling_frequency * 1000.0
    waveform_metrics = _measure_spiketurnpike_waveform_metrics(best_waveform, time_ms, rep_fraction=rep_fraction)

    spike_train = sorting.get_unit_spike_train(unit_id)
    duration_s = _recording_duration_s(analyzer)
    num_spikes = int(len(spike_train))
    firing_rate_hz = num_spikes / duration_s if duration_s > 0 else np.nan

    return CandidateWaveform(
        group=group_name,
        review_rank=int(row["review_rank"]),
        recording=str(row["recording"]),
        well=str(row["well"]),
        well_column=int(row["well_column"]),
        unit_id=unit_id,
        unit_index=unit_index,
        kslabel=_property_for_unit(sorting, unit_ids, unit_id, "KSLabel", ""),
        contam_pct=_float_property_for_unit(sorting, unit_ids, unit_id, "ContamPct"),
        amplitude=_float_property_for_unit(sorting, unit_ids, unit_id, "Amplitude"),
        num_spikes=num_spikes,
        firing_rate_hz=float(firing_rate_hz),
        review_sort_peak_raw_response_hz=float(row["review_sort_peak_raw_response_hz"]),
        score_hz=float(row["score_hz"]),
        pulse_reliability=float(row["post_window_pulse_reliability_250"]),
        best_channel_index=best_channel_index,
        template_ptp_best_channel_uV=template_ptp,
        template_trough_best_channel_uV=template_trough,
        template_peak_best_channel_uV=template_peak,
        trough_index=waveform_metrics["trough_index"],
        rebound_peak_index=waveform_metrics["rebound_peak_index"],
        trough_time_ms=waveform_metrics["trough_time_ms"],
        rebound_peak_time_ms=waveform_metrics["rebound_peak_time_ms"],
        trough_to_peak_duration_ms=waveform_metrics["trough_to_peak_duration_ms"],
        rep_fraction=waveform_metrics["rep_fraction"],
        rep_threshold_uV=waveform_metrics["rep_threshold_uV"],
        rep_recovery_index=waveform_metrics["rep_recovery_index"],
        rep_recovery_time_ms=waveform_metrics["rep_recovery_time_ms"],
        repolarization_time_ms=waveform_metrics["repolarization_time_ms"],
        tentative_rs_fs_classification=waveform_metrics["tentative_rs_fs_classification"],
        spiketurnpike_legacy_cell_type=waveform_metrics["spiketurnpike_legacy_cell_type"],
        spiketurnpike_amplitude_uV=waveform_metrics["spiketurnpike_amplitude_uV"],
        pre_peak_index=waveform_metrics["pre_peak_index"],
        pre_peak_time_ms=waveform_metrics["pre_peak_time_ms"],
        pre_peak_value_uV=waveform_metrics["pre_peak_value_uV"],
        post_peak_value_uV=waveform_metrics["post_peak_value_uV"],
        normalized_trough_value=waveform_metrics["normalized_trough_value"],
        peak1_normalized_amplitude=waveform_metrics["peak1_normalized_amplitude"],
        peak2_normalized_amplitude=waveform_metrics["peak2_normalized_amplitude"],
        peak1_to_trough_ratio=waveform_metrics["peak1_to_trough_ratio"],
        peak2_to_trough_ratio=waveform_metrics["peak2_to_trough_ratio"],
        peak_to_peak_ratio=waveform_metrics["peak_to_peak_ratio"],
        spike_half_width_ms=waveform_metrics["spike_half_width_ms"],
        half_width_start_index=waveform_metrics["half_width_start_index"],
        half_width_end_index=waveform_metrics["half_width_end_index"],
        half_width_start_time_ms=waveform_metrics["half_width_start_time_ms"],
        half_width_end_time_ms=waveform_metrics["half_width_end_time_ms"],
        time_ms=time_ms,
        template=template,
        best_waveform_uV=best_waveform,
        normalized_best_waveform=waveform_metrics["normalized_best_waveform"],
        analyzer_path=analyzer_path,
    )


def _match_unit_id(unit_ids: list[object], value: object) -> object:
    candidates = [value]
    if isinstance(value, str):
        try:
            numeric = float(value)
            candidates.extend([int(numeric), str(int(numeric))] if numeric.is_integer() else [numeric, str(numeric)])
        except ValueError:
            pass
    elif isinstance(value, float) and value.is_integer():
        candidates.extend([int(value), str(int(value))])
    else:
        candidates.append(str(value))

    for candidate in candidates:
        if candidate in unit_ids:
            return candidate
    unit_ids_as_str = {str(unit_id): unit_id for unit_id in unit_ids}
    for candidate in candidates:
        if str(candidate) in unit_ids_as_str:
            return unit_ids_as_str[str(candidate)]
    raise ValueError(f"unit {value!r} not found among analyzer unit IDs")


def _recording_duration_s(analyzer) -> float:
    recording = analyzer.recording
    sampling_frequency = float(recording.get_sampling_frequency())
    try:
        total_samples = sum(recording.get_num_samples(segment_index=index) for index in range(recording.get_num_segments()))
    except TypeError:
        total_samples = recording.get_num_samples()
    return float(total_samples) / sampling_frequency if sampling_frequency > 0 else math.nan


def _property_for_unit(sorting, unit_ids: list[object], unit_id: object, name: str, default: object) -> object:
    values = sorting.get_property(name)
    if values is None:
        return default
    return values[unit_ids.index(unit_id)]


def _float_property_for_unit(sorting, unit_ids: list[object], unit_id: object, name: str) -> float:
    value = _property_for_unit(sorting, unit_ids, unit_id, name, np.nan)
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _measure_spiketurnpike_waveform_metrics(
    best_waveform: np.ndarray,
    time_ms: np.ndarray,
    *,
    rep_fraction: float,
) -> dict[str, object]:
    best_waveform = np.asarray(best_waveform, dtype=float)
    time_ms = np.asarray(time_ms, dtype=float)
    if best_waveform.size == 0 or time_ms.size != best_waveform.size or np.all(np.isnan(best_waveform)):
        return {
            "trough_index": -1,
            "pre_peak_index": -1,
            "rebound_peak_index": -1,
            "trough_time_ms": np.nan,
            "pre_peak_time_ms": np.nan,
            "rebound_peak_time_ms": np.nan,
            "trough_to_peak_duration_ms": np.nan,
            "rep_fraction": rep_fraction,
            "rep_threshold_uV": np.nan,
            "rep_recovery_index": -1,
            "rep_recovery_time_ms": np.nan,
            "repolarization_time_ms": np.nan,
            "tentative_rs_fs_classification": "unknown",
            "spiketurnpike_legacy_cell_type": "unknown",
            "spiketurnpike_amplitude_uV": np.nan,
            "pre_peak_value_uV": np.nan,
            "post_peak_value_uV": np.nan,
            "normalized_trough_value": np.nan,
            "peak1_normalized_amplitude": np.nan,
            "peak2_normalized_amplitude": np.nan,
            "peak1_to_trough_ratio": np.nan,
            "peak2_to_trough_ratio": np.nan,
            "peak_to_peak_ratio": np.nan,
            "spike_half_width_ms": np.nan,
            "half_width_start_index": -1,
            "half_width_end_index": -1,
            "half_width_start_time_ms": np.nan,
            "half_width_end_time_ms": np.nan,
            "normalized_best_waveform": np.full_like(best_waveform, np.nan),
        }

    trough_index = int(np.nanargmin(best_waveform))
    pre_peak_index = int(np.nanargmax(best_waveform[: trough_index + 1])) if trough_index > 0 else trough_index
    search_start = min(trough_index + 1, best_waveform.size - 1)
    rebound_peak_index = search_start + int(np.nanargmax(best_waveform[search_start:]))
    trough_time_ms = float(time_ms[trough_index])
    pre_peak_time_ms = float(time_ms[pre_peak_index])
    rebound_peak_time_ms = float(time_ms[rebound_peak_index])
    trough_to_peak_duration_ms = rebound_peak_time_ms - trough_time_ms
    trough_value = float(best_waveform[trough_index])
    trough_abs_value = abs(trough_value)
    normalized = best_waveform / trough_abs_value if trough_abs_value > 0 else np.full_like(best_waveform, np.nan)
    normalized_trough_value = float(normalized[trough_index])
    peak1_normalized_amplitude = float(normalized[pre_peak_index])
    peak2_normalized_amplitude = float(normalized[rebound_peak_index])
    peak1_abs_value = abs(peak1_normalized_amplitude)
    peak2_abs_value = abs(peak2_normalized_amplitude)
    normalized_trough_abs_value = abs(normalized_trough_value)
    peak1_to_trough_ratio = (
        peak1_abs_value / normalized_trough_abs_value if normalized_trough_abs_value > 0 else np.nan
    )
    peak2_to_trough_ratio = (
        peak2_abs_value / normalized_trough_abs_value if normalized_trough_abs_value > 0 else np.nan
    )
    peak_to_peak_ratio = peak1_abs_value / peak2_abs_value if peak2_abs_value > 0 else np.nan
    half_width = _measure_half_width(normalized, time_ms, pre_peak_index, trough_index, rebound_peak_index)
    rep = _measure_repolarization_time(best_waveform, time_ms, trough_index, rep_fraction)
    return {
        "trough_index": trough_index,
        "pre_peak_index": pre_peak_index,
        "rebound_peak_index": rebound_peak_index,
        "trough_time_ms": trough_time_ms,
        "pre_peak_time_ms": pre_peak_time_ms,
        "rebound_peak_time_ms": rebound_peak_time_ms,
        "trough_to_peak_duration_ms": trough_to_peak_duration_ms,
        "rep_fraction": rep["rep_fraction"],
        "rep_threshold_uV": rep["rep_threshold_uV"],
        "rep_recovery_index": rep["rep_recovery_index"],
        "rep_recovery_time_ms": rep["rep_recovery_time_ms"],
        "repolarization_time_ms": rep["repolarization_time_ms"],
        "tentative_rs_fs_classification": _tentative_rs_fs_label(trough_to_peak_duration_ms),
        "spiketurnpike_legacy_cell_type": _spiketurnpike_legacy_cell_type(trough_to_peak_duration_ms),
        "spiketurnpike_amplitude_uV": trough_abs_value,
        "pre_peak_value_uV": float(best_waveform[pre_peak_index]),
        "post_peak_value_uV": float(best_waveform[rebound_peak_index]),
        "normalized_trough_value": normalized_trough_value,
        "peak1_normalized_amplitude": peak1_normalized_amplitude,
        "peak2_normalized_amplitude": peak2_normalized_amplitude,
        "peak1_to_trough_ratio": peak1_to_trough_ratio,
        "peak2_to_trough_ratio": peak2_to_trough_ratio,
        "peak_to_peak_ratio": peak_to_peak_ratio,
        "spike_half_width_ms": half_width["spike_half_width_ms"],
        "half_width_start_index": half_width["half_width_start_index"],
        "half_width_end_index": half_width["half_width_end_index"],
        "half_width_start_time_ms": half_width["half_width_start_time_ms"],
        "half_width_end_time_ms": half_width["half_width_end_time_ms"],
        "normalized_best_waveform": normalized,
    }


def _measure_repolarization_time(
    waveform_uV: np.ndarray,
    time_ms: np.ndarray,
    trough_index: int,
    rep_fraction: float,
) -> dict[str, object]:
    if (
        trough_index < 0
        or trough_index >= waveform_uV.size
        or time_ms.size != waveform_uV.size
        or not np.isfinite(waveform_uV[trough_index])
    ):
        return _empty_repolarization(rep_fraction)

    trough_value = float(waveform_uV[trough_index])
    if trough_value >= 0:
        return _empty_repolarization(rep_fraction)

    threshold_uV = trough_value * rep_fraction
    post_trough = waveform_uV[trough_index + 1 :]
    recovery_offsets = np.flatnonzero(post_trough >= threshold_uV)
    if recovery_offsets.size == 0:
        return {
            "rep_fraction": rep_fraction,
            "rep_threshold_uV": threshold_uV,
            "rep_recovery_index": -1,
            "rep_recovery_time_ms": np.nan,
            "repolarization_time_ms": np.nan,
        }

    recovery_index = trough_index + 1 + int(recovery_offsets[0])
    previous_index = recovery_index - 1
    previous_value = float(waveform_uV[previous_index])
    recovery_value = float(waveform_uV[recovery_index])
    if recovery_value == previous_value:
        recovery_time_ms = float(time_ms[recovery_index])
    else:
        interpolation_fraction = (threshold_uV - previous_value) / (recovery_value - previous_value)
        interpolation_fraction = float(np.clip(interpolation_fraction, 0.0, 1.0))
        recovery_time_ms = float(
            time_ms[previous_index] + interpolation_fraction * (time_ms[recovery_index] - time_ms[previous_index])
        )
    return {
        "rep_fraction": rep_fraction,
        "rep_threshold_uV": threshold_uV,
        "rep_recovery_index": int(recovery_index),
        "rep_recovery_time_ms": recovery_time_ms,
        "repolarization_time_ms": recovery_time_ms - float(time_ms[trough_index]),
    }


def _empty_repolarization(rep_fraction: float) -> dict[str, object]:
    return {
        "rep_fraction": rep_fraction,
        "rep_threshold_uV": np.nan,
        "rep_recovery_index": -1,
        "rep_recovery_time_ms": np.nan,
        "repolarization_time_ms": np.nan,
    }


def _measure_half_width(
    normalized: np.ndarray,
    time_ms: np.ndarray,
    pre_peak_index: int,
    trough_index: int,
    rebound_peak_index: int,
) -> dict[str, object]:
    if (
        pre_peak_index < 0
        or trough_index < 0
        or rebound_peak_index < 0
        or pre_peak_index > trough_index
        or trough_index > rebound_peak_index
        or not np.isfinite(normalized[trough_index])
    ):
        return _empty_half_width()
    half_amplitude = normalized[trough_index] / 2.0
    left_segment = normalized[pre_peak_index : trough_index + 1]
    right_segment = normalized[trough_index : rebound_peak_index + 1]
    if left_segment.size == 0 or right_segment.size == 0:
        return _empty_half_width()
    left_index = pre_peak_index + int(np.nanargmin(np.abs(left_segment - half_amplitude)))
    right_index = trough_index + int(np.nanargmin(np.abs(right_segment - half_amplitude)))
    return {
        "spike_half_width_ms": float(time_ms[right_index] - time_ms[left_index]),
        "half_width_start_index": int(left_index),
        "half_width_end_index": int(right_index),
        "half_width_start_time_ms": float(time_ms[left_index]),
        "half_width_end_time_ms": float(time_ms[right_index]),
    }


def _empty_half_width() -> dict[str, object]:
    return {
        "spike_half_width_ms": np.nan,
        "half_width_start_index": -1,
        "half_width_end_index": -1,
        "half_width_start_time_ms": np.nan,
        "half_width_end_time_ms": np.nan,
    }


def _tentative_rs_fs_label(trough_to_peak_duration_ms: float) -> str:
    config = RSFSClassificationConfig()
    if not np.isfinite(trough_to_peak_duration_ms):
        return config.unknown_label
    if trough_to_peak_duration_ms <= config.fs_upper_bound_ms:
        return config.fs_label
    if trough_to_peak_duration_ms >= config.rs_lower_bound_ms:
        return config.rs_label
    return config.borderline_label


def _spiketurnpike_legacy_cell_type(trough_to_peak_duration_ms: float) -> str:
    if not np.isfinite(trough_to_peak_duration_ms):
        return "unknown"
    if trough_to_peak_duration_ms <= 0.40:
        return "FS"
    if trough_to_peak_duration_ms >= 0.41:
        return "RS"
    return "unassigned_0.40_0.41_gap"


def _summary_row(candidate: CandidateWaveform) -> dict[str, object]:
    return {
        "group": candidate.group,
        "review_rank": candidate.review_rank,
        "recording": candidate.recording,
        "well": candidate.well,
        "well_column": candidate.well_column,
        "unit_id": candidate.unit_id,
        "KSLabel": candidate.kslabel,
        "ContamPct": candidate.contam_pct,
        "Amplitude": candidate.amplitude,
        "num_spikes": candidate.num_spikes,
        "firing_rate_hz": candidate.firing_rate_hz,
        "review_sort_peak_raw_response_hz": candidate.review_sort_peak_raw_response_hz,
        "score_hz": candidate.score_hz,
        "post_window_pulse_reliability_250": candidate.pulse_reliability,
        "best_channel_index": candidate.best_channel_index,
        "template_trough_best_channel_uV": candidate.template_trough_best_channel_uV,
        "template_peak_best_channel_uV": candidate.template_peak_best_channel_uV,
        "template_ptp_best_channel_uV": candidate.template_ptp_best_channel_uV,
        "trough_index": candidate.trough_index,
        "rebound_peak_index": candidate.rebound_peak_index,
        "trough_time_ms": candidate.trough_time_ms,
        "rebound_peak_time_ms": candidate.rebound_peak_time_ms,
        "trough_to_peak_duration_ms": candidate.trough_to_peak_duration_ms,
        "rep_fraction": candidate.rep_fraction,
        "rep_threshold_uV": candidate.rep_threshold_uV,
        "rep_recovery_index": candidate.rep_recovery_index,
        "rep_recovery_time_ms": candidate.rep_recovery_time_ms,
        "repolarization_time_ms": candidate.repolarization_time_ms,
        "tentative_rs_fs_classification": candidate.tentative_rs_fs_classification,
        "spiketurnpike_legacy_cell_type": candidate.spiketurnpike_legacy_cell_type,
        "spiketurnpike_amplitude_uV": candidate.spiketurnpike_amplitude_uV,
        "pre_peak_index": candidate.pre_peak_index,
        "pre_peak_time_ms": candidate.pre_peak_time_ms,
        "pre_peak_value_uV": candidate.pre_peak_value_uV,
        "post_peak_value_uV": candidate.post_peak_value_uV,
        "normalized_trough_value": candidate.normalized_trough_value,
        "peak1_normalized_amplitude": candidate.peak1_normalized_amplitude,
        "peak2_normalized_amplitude": candidate.peak2_normalized_amplitude,
        "peak1_to_trough_ratio": candidate.peak1_to_trough_ratio,
        "peak2_to_trough_ratio": candidate.peak2_to_trough_ratio,
        "peak_to_peak_ratio": candidate.peak_to_peak_ratio,
        "spike_half_width_ms": candidate.spike_half_width_ms,
        "half_width_start_index": candidate.half_width_start_index,
        "half_width_end_index": candidate.half_width_end_index,
        "half_width_start_time_ms": candidate.half_width_start_time_ms,
        "half_width_end_time_ms": candidate.half_width_end_time_ms,
        "analyzer_path": str(candidate.analyzer_path),
    }


def _write_waveform_cache(candidates: list[CandidateWaveform], job_dir: Path, date_label: str) -> tuple[Path, Path]:
    trace_path = job_dir / f"lumos_candidate_waveform_best_channel_traces_{date_label}.csv.gz"
    trace_rows: list[pd.DataFrame] = []
    for candidate_index, candidate in enumerate(candidates):
        candidate_key = _candidate_key(candidate)
        sample_index = np.arange(candidate.best_waveform_uV.size)
        trace_rows.append(
            pd.DataFrame(
                {
                    "candidate_index": candidate_index,
                    "candidate_key": candidate_key,
                    "group": candidate.group,
                    "review_rank": candidate.review_rank,
                    "recording": candidate.recording,
                    "well": candidate.well,
                    "unit_id": candidate.unit_id,
                    "best_channel_index": candidate.best_channel_index,
                    "sample_index": sample_index,
                    "time_ms": candidate.time_ms,
                    "UnNormalized_Template_Waveform_uV": candidate.best_waveform_uV,
                    "Normalized_Template_Waveform": candidate.normalized_best_waveform,
                    "is_pre_peak": sample_index == candidate.pre_peak_index,
                    "is_trough": sample_index == candidate.trough_index,
                    "is_post_peak": sample_index == candidate.rebound_peak_index,
                    "is_rep_recovery": sample_index == candidate.rep_recovery_index,
                    "is_half_width_start": sample_index == candidate.half_width_start_index,
                    "is_half_width_end": sample_index == candidate.half_width_end_index,
                }
            )
        )
    pd.concat(trace_rows, ignore_index=True).to_csv(trace_path, index=False)

    npz_path = job_dir / f"lumos_candidate_waveform_full_templates_{date_label}.npz"
    templates = np.stack([candidate.template for candidate in candidates], axis=0)
    np.savez_compressed(
        npz_path,
        templates_uV=templates,
        best_waveforms_uV=np.stack([candidate.best_waveform_uV for candidate in candidates], axis=0),
        normalized_best_waveforms=np.stack([candidate.normalized_best_waveform for candidate in candidates], axis=0),
        time_ms=np.stack([candidate.time_ms for candidate in candidates], axis=0),
        candidate_key=np.asarray([_candidate_key(candidate) for candidate in candidates], dtype=str),
        group=np.asarray([candidate.group for candidate in candidates], dtype=str),
        recording=np.asarray([candidate.recording for candidate in candidates], dtype=str),
        well=np.asarray([candidate.well for candidate in candidates], dtype=str),
        unit_id=np.asarray([str(candidate.unit_id) for candidate in candidates], dtype=str),
        review_rank=np.asarray([candidate.review_rank for candidate in candidates], dtype=int),
        best_channel_index=np.asarray([candidate.best_channel_index for candidate in candidates], dtype=int),
        rep_fraction=np.asarray([candidate.rep_fraction for candidate in candidates], dtype=float),
        rep_threshold_uV=np.asarray([candidate.rep_threshold_uV for candidate in candidates], dtype=float),
        rep_recovery_index=np.asarray([candidate.rep_recovery_index for candidate in candidates], dtype=int),
        rep_recovery_time_ms=np.asarray([candidate.rep_recovery_time_ms for candidate in candidates], dtype=float),
        repolarization_time_ms=np.asarray([candidate.repolarization_time_ms for candidate in candidates], dtype=float),
    )
    return trace_path, npz_path


def _candidate_key(candidate: CandidateWaveform) -> str:
    return f"rank{candidate.review_rank}_{candidate.well}_unit{candidate.unit_id}"


def _plot_gallery(
    candidates: list[CandidateWaveform],
    figure_path: Path,
    *,
    top_n_per_group: int,
    same_y_scale: bool,
    mark_trough_peak: bool,
) -> None:
    import matplotlib.pyplot as plt

    group_order = ["columns_4_8_prior", "columns_1_3_compare"]
    grouped = {group: [candidate for candidate in candidates if candidate.group == group] for group in group_order}
    max_columns = max(top_n_per_group, max((len(values) for values in grouped.values()), default=1))

    figure, axes = plt.subplots(
        nrows=len(group_order),
        ncols=max_columns,
        figsize=(max_columns * 2.25, len(group_order) * 2.7),
        squeeze=False,
        sharex=True,
    )
    if same_y_scale:
        all_values = np.concatenate([candidate.template.ravel() for candidate in candidates])
        max_abs = float(np.nanmax(np.abs(all_values))) if all_values.size else 1.0
        y_limit = max(max_abs * 1.08, 1.0)
    else:
        y_limit = None

    for row_index, group_name in enumerate(group_order):
        values = grouped[group_name]
        for column_index in range(max_columns):
            axis = axes[row_index, column_index]
            if column_index >= len(values):
                axis.axis("off")
                continue

            candidate = values[column_index]
            axis.axhline(0, color="0.82", linewidth=0.7, zorder=0)
            axis.plot(candidate.time_ms, candidate.template, color="0.78", linewidth=0.55, alpha=0.7)
            axis.plot(
                candidate.time_ms,
                candidate.template[:, candidate.best_channel_index],
                color="black",
                linewidth=1.6,
            )
            if mark_trough_peak and candidate.trough_index >= 0 and candidate.rebound_peak_index >= 0:
                best_waveform = candidate.template[:, candidate.best_channel_index]
                axis.scatter(
                    [candidate.time_ms[candidate.trough_index]],
                    [best_waveform[candidate.trough_index]],
                    color="black",
                    edgecolor="white",
                    linewidth=0.6,
                    s=26,
                    zorder=5,
                )
                axis.scatter(
                    [candidate.time_ms[candidate.rebound_peak_index]],
                    [best_waveform[candidate.rebound_peak_index]],
                    color="#e69f00",
                    edgecolor="black",
                    linewidth=0.45,
                    s=26,
                    zorder=5,
                )
            if y_limit is not None:
                axis.set_ylim(-y_limit, y_limit)
            axis.set_title(
                (
                    f"#{candidate.review_rank} {candidate.well} u{candidate.unit_id}\n"
                    f"{candidate.kslabel}, {candidate.review_sort_peak_raw_response_hz:g} Hz, "
                    f"TTP {candidate.trough_to_peak_duration_ms:.2f} ms, "
                    f"REP{_rep_fraction_label(candidate.rep_fraction)} {candidate.repolarization_time_ms:.2f} ms "
                    f"{candidate.tentative_rs_fs_classification}"
                ),
                fontsize=8,
            )
            axis.tick_params(axis="both", labelsize=7, length=2)
            if column_index == 0:
                axis.set_ylabel(_group_label(group_name) + "\nAmplitude (uV)", fontsize=9)
            if row_index == len(group_order) - 1:
                axis.set_xlabel("Time from spike (ms)", fontsize=8)

    figure.suptitle(
        "Lumos candidate templates: columns 4-8 prior vs columns 1-3 comparison\n"
        "Grey = all analyzer channels; black = best PTP channel; dots = trough/rebound peak; tentative FS/RS from TTP",
        fontsize=12,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.92))
    figure.savefig(figure_path, dpi=220)
    plt.close(figure)


def _plot_best_channel_normalized_comparison(
    candidates: list[CandidateWaveform],
    figure_path: Path,
    *,
    top_n_per_group: int,
) -> None:
    import matplotlib.pyplot as plt

    group_order = ["columns_4_8_prior", "columns_1_3_compare"]
    grouped = {group: [candidate for candidate in candidates if candidate.group == group] for group in group_order}
    max_columns = max(top_n_per_group, max((len(values) for values in grouped.values()), default=1))
    row_specs = [
        ("columns_4_8_prior", "unnormalized"),
        ("columns_4_8_prior", "normalized"),
        ("columns_1_3_compare", "unnormalized"),
        ("columns_1_3_compare", "normalized"),
    ]

    figure, axes = plt.subplots(
        nrows=len(row_specs),
        ncols=max_columns,
        figsize=(max_columns * 2.25, len(row_specs) * 2.25),
        squeeze=False,
        sharex=True,
    )
    y_limit_uV = max(
        float(np.nanmax(np.abs(np.concatenate([candidate.best_waveform_uV for candidate in candidates])))) * 1.08,
        1.0,
    )
    y_limit_norm = max(
        float(np.nanmax(np.abs(np.concatenate([candidate.normalized_best_waveform for candidate in candidates])))) * 1.08,
        1.2,
    )

    for row_index, (group_name, waveform_kind) in enumerate(row_specs):
        values = grouped[group_name]
        for column_index in range(max_columns):
            axis = axes[row_index, column_index]
            if column_index >= len(values):
                axis.axis("off")
                continue

            candidate = values[column_index]
            waveform = (
                candidate.best_waveform_uV
                if waveform_kind == "unnormalized"
                else candidate.normalized_best_waveform
            )
            y_limit = y_limit_uV if waveform_kind == "unnormalized" else y_limit_norm
            axis.axhline(0, color="0.82", linewidth=0.7, zorder=0)
            axis.plot(candidate.time_ms, waveform, color="black", linewidth=1.5)
            _scatter_waveform_landmarks(axis, candidate, waveform)
            axis.set_ylim(-y_limit, y_limit)
            axis.tick_params(axis="both", labelsize=7, length=2)
            if row_index in (0, 2):
                axis.set_title(
                    f"#{candidate.review_rank} {candidate.well} u{candidate.unit_id}\n"
                    f"{candidate.kslabel}, TTP {candidate.trough_to_peak_duration_ms:.2f} ms, "
                    f"REP{_rep_fraction_label(candidate.rep_fraction)} {candidate.repolarization_time_ms:.2f} ms",
                    fontsize=8,
                )
            if column_index == 0:
                axis.set_ylabel(
                    f"{_group_label(group_name)}\n"
                    + ("uV" if waveform_kind == "unnormalized" else "norm trough=-1"),
                    fontsize=9,
                )
            if row_index == len(row_specs) - 1:
                axis.set_xlabel("Time from spike (ms)", fontsize=8)

    figure.suptitle(
        "Best-channel candidate waveforms: unnormalized uV and SpikeTurnpike trough-normalized views\n"
        "Landmarks are detected on the uV trace and shown at the same sample times after normalization",
        fontsize=12,
    )
    _add_colored_landmark_legend(figure)
    figure.tight_layout(rect=(0, 0, 1, 0.91))
    figure.savefig(figure_path, dpi=220)
    plt.close(figure)


def _add_colored_landmark_legend(figure) -> None:
    legend_items = [
        ("blue = pre-peak / peak1", "#0072b2"),
        ("black = trough", "black"),
        ("orange = rebound peak / peak2", "#e69f00"),
        ("red-orange = half-width anchors", "#d55e00"),
    ]
    start_x = 0.24
    y = 0.935
    x_step = 0.15
    for index, (label, color) in enumerate(legend_items):
        figure.text(
            start_x + index * x_step,
            y,
            label,
            ha="left",
            va="center",
            color=color,
            fontsize=10,
            fontweight="bold",
        )


def _scatter_waveform_landmarks(axis, candidate: CandidateWaveform, waveform: np.ndarray) -> None:
    landmark_specs = [
        (candidate.pre_peak_index, "#0072b2", "white"),
        (candidate.trough_index, "black", "white"),
        (candidate.rebound_peak_index, "#e69f00", "black"),
        (candidate.half_width_start_index, "#d55e00", "white"),
        (candidate.half_width_end_index, "#d55e00", "white"),
    ]
    for index, facecolor, edgecolor in landmark_specs:
        if index < 0 or index >= waveform.size:
            continue
        axis.scatter(
            [candidate.time_ms[index]],
            [waveform[index]],
            color=facecolor,
            edgecolor=edgecolor,
            linewidth=0.45,
            s=22,
            zorder=5,
        )


def _group_label(group_name: str) -> str:
    if group_name == "columns_4_8_prior":
        return "Columns 4-8"
    if group_name == "columns_1_3_compare":
        return "Columns 1-3"
    return group_name


def _rep_fraction_label(rep_fraction: float) -> str:
    return f"{rep_fraction * 100:g}"


if __name__ == "__main__":
    main()
