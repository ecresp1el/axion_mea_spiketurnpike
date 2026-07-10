"""Burst detection and unit-level spontaneous-activity summaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.ndimage import gaussian_filter1d


@dataclass(frozen=True)
class BurstDetectionParameters:
    """Parameters for contiguous-ISI burst detection."""

    max_isi_ms: float = 100.0
    min_spikes: int = 3
    min_duration_ms: float = 100.0

    def validate(self) -> None:
        if not np.isfinite(self.max_isi_ms) or self.max_isi_ms <= 0:
            raise ValueError("max_isi_ms must be finite and > 0")
        if self.min_spikes < 2:
            raise ValueError("min_spikes must be >= 2")
        if not np.isfinite(self.min_duration_ms) or self.min_duration_ms < 0:
            raise ValueError("min_duration_ms must be finite and >= 0")


@dataclass(frozen=True)
class BurstEvent:
    """One accepted burst in one sorted unit."""

    burst_index: int
    first_spike_index: int
    last_spike_index: int
    start_time_s: float
    end_time_s: float
    duration_ms: float
    spike_count: int
    firing_rate_hz: float
    interval_rate_hz: float

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


def summarize_smoothed_inverse_isi_rate(
    spike_times_s: np.ndarray,
    recording_duration_s: float,
    *,
    gaussian_sigma_ms: float = 50.0,
    evaluation_bin_ms: float = 1.0,
    min_spikes: int = 30,
) -> dict[str, int | float | bool]:
    """Summarize a Gaussian-smoothed inverse-ISI firing-rate trace.

    The reciprocal of each positive interspike interval is treated as the
    instantaneous rate throughout that interval. The resulting piecewise
    trace is evaluated on a regular grid, smoothed with a Gaussian whose sigma
    is specified in milliseconds, and summarized over the full recording.
    Time before the first spike and after the last spike is represented as
    zero rate. Units below ``min_spikes`` are retained but return undefined
    temporal summaries.
    """

    spikes = _validated_spike_times(spike_times_s)
    if not np.isfinite(recording_duration_s) or recording_duration_s <= 0:
        raise ValueError("recording_duration_s must be finite and > 0")
    if not np.isfinite(gaussian_sigma_ms) or gaussian_sigma_ms <= 0:
        raise ValueError("gaussian_sigma_ms must be finite and > 0")
    if not np.isfinite(evaluation_bin_ms) or evaluation_bin_ms <= 0:
        raise ValueError("evaluation_bin_ms must be finite and > 0")
    if min_spikes < 2:
        raise ValueError("min_spikes must be >= 2")

    eligible = bool(spikes.size >= min_spikes)
    base: dict[str, int | float | bool] = {
        "inverse_isi_gaussian_eligible": eligible,
        "inverse_isi_gaussian_min_spikes": int(min_spikes),
        "inverse_isi_gaussian_sigma_ms": float(gaussian_sigma_ms),
        "inverse_isi_gaussian_evaluation_bin_ms": float(evaluation_bin_ms),
    }
    if not eligible:
        return base | {
            "inverse_isi_gaussian_temporal_mean_hz": np.nan,
            "inverse_isi_gaussian_temporal_median_hz": np.nan,
            "inverse_isi_gaussian_temporal_max_hz": np.nan,
        }

    intervals_s = np.diff(spikes)
    if np.any(intervals_s <= 0):
        raise ValueError("inverse-ISI rate requires strictly increasing spike times")

    bin_s = evaluation_bin_ms / 1000.0
    bin_count = int(np.ceil(recording_duration_s / bin_s))
    time_s = (np.arange(bin_count, dtype=float) + 0.5) * bin_s
    time_s = np.minimum(time_s, np.nextafter(recording_duration_s, 0.0))
    interval_indices = np.searchsorted(spikes, time_s, side="right") - 1
    in_interval = (interval_indices >= 0) & (interval_indices < intervals_s.size)
    instantaneous_rate_hz = np.zeros(bin_count, dtype=float)
    instantaneous_rate_hz[in_interval] = 1.0 / intervals_s[interval_indices[in_interval]]

    sigma_bins = gaussian_sigma_ms / evaluation_bin_ms
    smoothed_rate_hz = gaussian_filter1d(
        instantaneous_rate_hz,
        sigma=sigma_bins,
        mode="constant",
        cval=0.0,
        truncate=4.0,
    )
    return base | {
        "inverse_isi_gaussian_temporal_mean_hz": float(np.mean(smoothed_rate_hz)),
        "inverse_isi_gaussian_temporal_median_hz": float(np.median(smoothed_rate_hz)),
        "inverse_isi_gaussian_temporal_max_hz": float(np.max(smoothed_rate_hz)),
    }


def detect_bursts(
    spike_times_s: np.ndarray,
    parameters: BurstDetectionParameters,
) -> list[BurstEvent]:
    """Detect bursts as contiguous runs whose adjacent ISIs do not exceed a limit."""

    parameters.validate()
    spikes = _validated_spike_times(spike_times_s)
    if spikes.size < parameters.min_spikes:
        return []

    max_isi_s = parameters.max_isi_ms / 1000.0
    min_duration_s = parameters.min_duration_ms / 1000.0
    # A small numerical tolerance keeps exact decimal boundaries such as 100 ms
    # stable after conversion from sample indices to seconds.
    tolerance_s = max(np.finfo(float).eps * 16.0, 1e-12)
    split_after = np.flatnonzero(np.diff(spikes) > max_isi_s + tolerance_s)
    starts = np.concatenate(([0], split_after + 1))
    stops = np.concatenate((split_after + 1, [spikes.size]))

    events: list[BurstEvent] = []
    for start, stop in zip(starts, stops, strict=True):
        spike_count = int(stop - start)
        if spike_count < parameters.min_spikes:
            continue
        duration_s = float(spikes[stop - 1] - spikes[start])
        if duration_s + tolerance_s < min_duration_s:
            continue
        firing_rate_hz = float(spike_count / duration_s) if duration_s > 0 else np.nan
        interval_rate_hz = float((spike_count - 1) / duration_s) if duration_s > 0 else np.nan
        events.append(
            BurstEvent(
                burst_index=len(events),
                first_spike_index=int(start),
                last_spike_index=int(stop - 1),
                start_time_s=float(spikes[start]),
                end_time_s=float(spikes[stop - 1]),
                duration_ms=duration_s * 1000.0,
                spike_count=spike_count,
                firing_rate_hz=firing_rate_hz,
                interval_rate_hz=interval_rate_hz,
            )
        )
    return events


def summarize_unit_activity(
    spike_times_s: np.ndarray,
    recording_duration_s: float,
    parameters: BurstDetectionParameters,
) -> tuple[dict[str, int | float | bool], list[BurstEvent]]:
    """Return one unit summary and its accepted burst events."""

    spikes = _validated_spike_times(spike_times_s)
    if not np.isfinite(recording_duration_s) or recording_duration_s <= 0:
        raise ValueError("recording_duration_s must be finite and > 0")
    events = detect_bursts(spikes, parameters)
    burst_spike_count = int(sum(event.spike_count for event in events))
    if burst_spike_count > spikes.size:
        raise AssertionError("burst spike assignment exceeded total unit spikes")

    ibis_s = np.asarray(
        [events[index].start_time_s - events[index - 1].end_time_s for index in range(1, len(events))],
        dtype=float,
    )
    durations_ms = np.asarray([event.duration_ms for event in events], dtype=float)
    spikes_per_burst = np.asarray([event.spike_count for event in events], dtype=float)
    burst_rates_hz = np.asarray([event.firing_rate_hz for event in events], dtype=float)
    interval_rates_hz = np.asarray([event.interval_rate_hz for event in events], dtype=float)
    spike_count = int(spikes.size)

    summary: dict[str, int | float | bool] = {
        "spike_count_recomputed": spike_count,
        "recording_duration_s_recomputed": float(recording_duration_s),
        "firing_rate_hz_recomputed": float(spike_count / recording_duration_s),
        "burst_count": int(len(events)),
        "burst_positive": bool(events),
        "burst_rate_per_min": float(len(events) / (recording_duration_s / 60.0)),
        "burst_spike_count": burst_spike_count,
        "fraction_spikes_in_bursts": float(burst_spike_count / spike_count) if spike_count else 0.0,
        "mean_firing_rate_within_bursts_hz": _mean_or_nan(burst_rates_hz),
        "mean_interval_rate_within_bursts_hz": _mean_or_nan(interval_rates_hz),
        "mean_burst_duration_ms": _mean_or_nan(durations_ms),
        "median_burst_duration_ms": _median_or_nan(durations_ms),
        "mean_spikes_per_burst": _mean_or_nan(spikes_per_burst),
        "median_spikes_per_burst": _median_or_nan(spikes_per_burst),
        "interburst_interval_count": int(ibis_s.size),
        "mean_interburst_interval_s": _mean_or_nan(ibis_s),
        "median_interburst_interval_s": _median_or_nan(ibis_s),
    }
    return summary, events


def _validated_spike_times(spike_times_s: np.ndarray) -> np.ndarray:
    spikes = np.asarray(spike_times_s, dtype=float)
    if spikes.ndim != 1:
        raise ValueError("spike_times_s must be one-dimensional")
    if not np.isfinite(spikes).all():
        raise ValueError("spike_times_s contains non-finite values")
    if spikes.size > 1 and np.any(np.diff(spikes) < 0):
        raise ValueError("spike_times_s must be sorted")
    return spikes


def _mean_or_nan(values: np.ndarray) -> float:
    return float(np.mean(values)) if values.size else np.nan


def _median_or_nan(values: np.ndarray) -> float:
    return float(np.median(values)) if values.size else np.nan
