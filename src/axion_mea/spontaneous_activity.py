"""Burst detection and unit-level spontaneous-activity summaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks


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


def detect_negative_threshold_events(
    trace_uV: np.ndarray,
    sampling_frequency_hz: float,
    threshold_uV: float,
    *,
    refractory_period_ms: float = 1.0,
) -> np.ndarray:
    """Detect negative local minima below a voltage threshold.

    This is a channel-level multiunit event detector, not spike sorting. The
    returned integer sample indices are separated by at least the requested
    refractory period.
    """

    trace = np.asarray(trace_uV, dtype=float)
    if trace.ndim != 1:
        raise ValueError("trace_uV must be one-dimensional")
    if not np.isfinite(trace).all():
        raise ValueError("trace_uV contains non-finite values")
    if not np.isfinite(sampling_frequency_hz) or sampling_frequency_hz <= 0:
        raise ValueError("sampling_frequency_hz must be finite and > 0")
    if not np.isfinite(threshold_uV):
        raise ValueError("threshold_uV must be finite")
    if not np.isfinite(refractory_period_ms) or refractory_period_ms <= 0:
        raise ValueError("refractory_period_ms must be finite and > 0")
    refractory_samples = max(
        1,
        int(round(refractory_period_ms / 1000.0 * sampling_frequency_hz)),
    )
    peaks, _ = find_peaks(
        -trace,
        height=-float(threshold_uV),
        distance=refractory_samples,
    )
    return peaks.astype(np.int64, copy=False)


def spike_time_tiling_coefficient(
    spike_times_a_s: np.ndarray,
    spike_times_b_s: np.ndarray,
    recording_duration_s: float,
    *,
    coincidence_window_ms: float = 50.0,
) -> float:
    """Return the pairwise spike-time tiling coefficient (STTC).

    STTC measures spike-time synchrony while correcting for the fraction of
    the recording covered by coincidence windows. Empty spike trains do not
    define a pairwise synchrony value and return ``nan``.
    """

    spikes_a = _validated_spike_times(spike_times_a_s)
    spikes_b = _validated_spike_times(spike_times_b_s)
    if not np.isfinite(recording_duration_s) or recording_duration_s <= 0:
        raise ValueError("recording_duration_s must be finite and > 0")
    if not np.isfinite(coincidence_window_ms) or coincidence_window_ms <= 0:
        raise ValueError("coincidence_window_ms must be finite and > 0")
    if spikes_a.size == 0 or spikes_b.size == 0:
        return np.nan
    if spikes_a[0] < 0 or spikes_b[0] < 0:
        raise ValueError("spike times must be >= 0")
    if spikes_a[-1] > recording_duration_s or spikes_b[-1] > recording_duration_s:
        raise ValueError("spike times must not exceed recording_duration_s")

    delta_s = coincidence_window_ms / 1000.0
    pa = _fraction_spikes_within_delta(spikes_a, spikes_b, delta_s)
    pb = _fraction_spikes_within_delta(spikes_b, spikes_a, delta_s)
    ta = _fraction_time_tiled(spikes_a, recording_duration_s, delta_s)
    tb = _fraction_time_tiled(spikes_b, recording_duration_s, delta_s)
    terms = []
    for proportion, tiled in ((pa, tb), (pb, ta)):
        denominator = 1.0 - proportion * tiled
        if np.isclose(denominator, 0.0):
            terms.append(1.0 if np.isclose(proportion, 1.0) else np.nan)
        else:
            terms.append((proportion - tiled) / denominator)
    return float(np.nanmean(terms)) if np.isfinite(terms).any() else np.nan


def mean_pairwise_spike_time_tiling_coefficient(
    spike_trains_s: list[np.ndarray],
    recording_duration_s: float,
    *,
    coincidence_window_ms: float = 50.0,
) -> tuple[float, int]:
    """Return mean pairwise STTC and the number of contributing unit pairs."""

    values = []
    for index, spikes_a in enumerate(spike_trains_s):
        for spikes_b in spike_trains_s[index + 1 :]:
            value = spike_time_tiling_coefficient(
                spikes_a,
                spikes_b,
                recording_duration_s,
                coincidence_window_ms=coincidence_window_ms,
            )
            if np.isfinite(value):
                values.append(value)
    return (_mean_or_nan(np.asarray(values, dtype=float)), len(values))


def count_burst_episodes(
    burst_events: list[BurstEvent],
    *,
    min_interburst_interval_ms: float,
) -> int:
    """Count burst episodes after consolidating closely spaced raw bursts.

    Each accepted ISI-defined burst starts a new episode only when its start is
    at least ``min_interburst_interval_ms`` after the end of the current
    episode. This leaves the accepted bursts themselves unchanged, so their
    individual durations can still be summarized independently.
    """

    if not np.isfinite(min_interburst_interval_ms) or min_interburst_interval_ms < 0:
        raise ValueError("min_interburst_interval_ms must be finite and >= 0")
    if not burst_events:
        return 0

    minimum_gap_s = min_interburst_interval_ms / 1000.0
    episode_count = 1
    episode_end_s = float(burst_events[0].end_time_s)
    for event in burst_events[1:]:
        if float(event.start_time_s) - episode_end_s >= minimum_gap_s:
            episode_count += 1
            episode_end_s = float(event.end_time_s)
        else:
            episode_end_s = max(episode_end_s, float(event.end_time_s))
    return episode_count


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
            "inverse_isi_gaussian_temporal_p99_hz": np.nan,
            "inverse_isi_gaussian_temporal_p99_9_hz": np.nan,
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
        "inverse_isi_gaussian_temporal_p99_hz": float(np.percentile(smoothed_rate_hz, 99.0)),
        "inverse_isi_gaussian_temporal_p99_9_hz": float(np.percentile(smoothed_rate_hz, 99.9)),
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
        "max_spikes_per_burst": float(np.max(spikes_per_burst)) if spikes_per_burst.size else np.nan,
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


def _fraction_spikes_within_delta(
    source_spikes: np.ndarray,
    target_spikes: np.ndarray,
    delta_s: float,
) -> float:
    insertion = np.searchsorted(target_spikes, source_spikes)
    right = np.minimum(insertion, target_spikes.size - 1)
    left = np.maximum(insertion - 1, 0)
    distance = np.minimum(
        np.abs(source_spikes - target_spikes[left]),
        np.abs(source_spikes - target_spikes[right]),
    )
    return float(np.mean(distance <= delta_s))


def _fraction_time_tiled(
    spikes: np.ndarray,
    recording_duration_s: float,
    delta_s: float,
) -> float:
    starts = np.maximum(0.0, spikes - delta_s)
    stops = np.minimum(recording_duration_s, spikes + delta_s)
    covered_s = 0.0
    current_start = float(starts[0])
    current_stop = float(stops[0])
    for start, stop in zip(starts[1:], stops[1:], strict=True):
        if start <= current_stop:
            current_stop = max(current_stop, float(stop))
        else:
            covered_s += current_stop - current_start
            current_start = float(start)
            current_stop = float(stop)
    covered_s += current_stop - current_start
    return float(covered_s / recording_duration_s)


def _mean_or_nan(values: np.ndarray) -> float:
    return float(np.mean(values)) if values.size else np.nan


def _median_or_nan(values: np.ndarray) -> float:
    return float(np.median(values)) if values.size else np.nan
