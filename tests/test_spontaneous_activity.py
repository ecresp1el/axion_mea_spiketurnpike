from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from axion_mea.spontaneous_activity import (  # noqa: E402
    BurstDetectionParameters,
    count_burst_episodes,
    detect_negative_threshold_events,
    detect_bursts,
    mean_pairwise_spike_time_tiling_coefficient,
    spike_time_tiling_coefficient,
    summarize_smoothed_inverse_isi_rate,
    summarize_unit_activity,
)


class SpontaneousActivityTests(unittest.TestCase):
    def test_count_burst_episodes_consolidates_gaps_below_minimum(self) -> None:
        parameters = BurstDetectionParameters()
        spikes = np.asarray(
            [0.0, 0.05, 0.10, 1.0, 1.05, 1.10, 3.1, 3.15, 3.20]
        )
        events = detect_bursts(spikes, parameters)

        self.assertEqual(len(events), 3)
        self.assertEqual(
            count_burst_episodes(events, min_interburst_interval_ms=2000.0),
            2,
        )

    def test_negative_threshold_detector_uses_local_minima_and_refractory_period(self) -> None:
        trace = np.zeros(30, dtype=float)
        trace[[5, 7, 20]] = [-6.0, -8.0, -7.0]
        events = detect_negative_threshold_events(
            trace,
            sampling_frequency_hz=1000.0,
            threshold_uV=-5.0,
            refractory_period_ms=5.0,
        )

        self.assertEqual(events.tolist(), [7, 20])

    def test_sttc_is_one_for_identical_spike_trains(self) -> None:
        spikes = np.asarray([0.2, 1.0, 2.7, 4.9])
        value = spike_time_tiling_coefficient(spikes, spikes.copy(), 5.0)

        self.assertTrue(np.isclose(value, 1.0))

    def test_sttc_is_symmetric_and_empty_pairs_are_undefined(self) -> None:
        spikes_a = np.asarray([0.2, 1.0, 2.7, 4.9])
        spikes_b = np.asarray([0.22, 1.04, 3.5])
        ab = spike_time_tiling_coefficient(spikes_a, spikes_b, 5.0)
        ba = spike_time_tiling_coefficient(spikes_b, spikes_a, 5.0)

        self.assertTrue(np.isclose(ab, ba))
        self.assertTrue(np.isnan(spike_time_tiling_coefficient(spikes_a, np.asarray([]), 5.0)))

    def test_mean_pairwise_sttc_reports_contributing_pairs(self) -> None:
        spikes = np.asarray([0.2, 1.0, 2.7, 4.9])
        value, pair_count = mean_pairwise_spike_time_tiling_coefficient(
            [spikes, spikes.copy(), np.asarray([])],
            5.0,
        )

        self.assertEqual(pair_count, 1)
        self.assertTrue(np.isclose(value, 1.0))

    def test_smoothed_inverse_isi_rate_requires_minimum_spikes(self) -> None:
        summary = summarize_smoothed_inverse_isi_rate(
            np.linspace(0.0, 2.8, 29),
            3.0,
            min_spikes=30,
        )

        self.assertFalse(summary["inverse_isi_gaussian_eligible"])
        self.assertTrue(np.isnan(summary["inverse_isi_gaussian_temporal_mean_hz"]))
        self.assertTrue(np.isnan(summary["inverse_isi_gaussian_temporal_median_hz"]))
        self.assertTrue(np.isnan(summary["inverse_isi_gaussian_temporal_max_hz"]))

    def test_smoothed_inverse_isi_rate_summarizes_constant_rate(self) -> None:
        summary = summarize_smoothed_inverse_isi_rate(
            np.arange(0.0, 10.01, 0.1),
            10.01,
            gaussian_sigma_ms=50.0,
            evaluation_bin_ms=1.0,
            min_spikes=30,
        )

        self.assertTrue(summary["inverse_isi_gaussian_eligible"])
        self.assertTrue(
            np.isclose(summary["inverse_isi_gaussian_temporal_median_hz"], 10.0, atol=0.01)
        )
        self.assertTrue(
            np.isclose(summary["inverse_isi_gaussian_temporal_max_hz"], 10.0, atol=0.01)
        )
        self.assertTrue(
            np.isclose(summary["inverse_isi_gaussian_temporal_p99_hz"], 10.0, atol=0.01)
        )
        self.assertTrue(
            np.isclose(summary["inverse_isi_gaussian_temporal_p99_9_hz"], 10.0, atol=0.01)
        )
        self.assertGreater(summary["inverse_isi_gaussian_temporal_mean_hz"], 9.8)
        self.assertLessEqual(summary["inverse_isi_gaussian_temporal_mean_hz"], 10.0)

    def test_detect_bursts_accepts_exact_isi_and_duration_boundaries(self) -> None:
        parameters = BurstDetectionParameters(max_isi_ms=100, min_spikes=3, min_duration_ms=100)
        events = detect_bursts(np.asarray([0.0, 0.05, 0.10, 1.0]), parameters)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].spike_count, 3)
        self.assertTrue(np.isclose(events[0].duration_ms, 100.0))
        self.assertTrue(np.isclose(events[0].firing_rate_hz, 30.0))
        self.assertTrue(np.isclose(events[0].interval_rate_hz, 20.0))

    def test_detect_bursts_rejects_short_candidate_and_keeps_nonoverlap(self) -> None:
        parameters = BurstDetectionParameters(max_isi_ms=100, min_spikes=3, min_duration_ms=100)
        spikes = np.asarray([0.0, 0.02, 0.04, 1.0, 1.05, 1.10, 2.0, 2.05, 2.10])
        events = detect_bursts(spikes, parameters)

        self.assertEqual(len(events), 2)
        self.assertEqual(
            [(event.first_spike_index, event.last_spike_index) for event in events],
            [(3, 5), (6, 8)],
        )
        self.assertEqual(sum(event.spike_count for event in events), 6)

    def test_summarize_unit_activity_handles_zero_bursts(self) -> None:
        parameters = BurstDetectionParameters()
        summary, events = summarize_unit_activity(np.asarray([0.0, 1.0, 2.0]), 10.0, parameters)

        self.assertEqual(events, [])
        self.assertEqual(summary["burst_count"], 0)
        self.assertEqual(summary["burst_rate_per_min"], 0.0)
        self.assertEqual(summary["fraction_spikes_in_bursts"], 0.0)
        self.assertTrue(np.isnan(summary["mean_burst_duration_ms"]))
        self.assertTrue(np.isnan(summary["mean_interburst_interval_s"]))

    def test_summarize_unit_activity_computes_interburst_interval(self) -> None:
        parameters = BurstDetectionParameters()
        spikes = np.asarray([0.0, 0.05, 0.10, 1.0, 1.05, 1.10])
        summary, events = summarize_unit_activity(spikes, 2.0, parameters)

        self.assertEqual(len(events), 2)
        self.assertEqual(summary["interburst_interval_count"], 1)
        self.assertTrue(np.isclose(summary["mean_interburst_interval_s"], 0.9))
        self.assertTrue(np.isclose(summary["fraction_spikes_in_bursts"], 1.0))
        self.assertTrue(np.isclose(summary["burst_rate_per_min"], 60.0))
        self.assertEqual(summary["max_spikes_per_burst"], 3.0)


if __name__ == "__main__":
    unittest.main()
