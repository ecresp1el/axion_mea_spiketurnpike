from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from axion_mea.gui_stim_response import (  # noqa: E402
    AnalysisWindow,
    PsthConfig,
    PulseEpoch,
    PulseWindow,
    StimResponseInputs,
    UnitStimResponseBuilder,
    assess_stim_response_eligibility,
    build_rapid_opto_review_table,
    kslabel_good_unit_groups,
    load_aligned_waveform_reviews,
    load_opto_intervals_from_raw,
    inspect_pulse_structure,
    is_lumos_plate,
    resolve_stim_sidecars,
    stim_events_from_raw,
    _resolve_unit_selection_labels,
    _split_unit_selection_tokens,
    _default_opto_unit_labels,
    _label_to_unit_groups,
    _response_unit_label,
)


class FakeSorting:
    def __init__(
        self,
        spike_trains: dict[object, list[int]],
        sampling_frequency: float = 1000.0,
        properties: dict[str, list[object]] | None = None,
    ) -> None:
        self.spike_trains = spike_trains
        self.unit_ids = list(spike_trains)
        self.sampling_frequency = sampling_frequency
        self.properties = properties or {}

    def get_unit_spike_train(self, unit_id):
        return self.spike_trains.get(unit_id, [])

    def get_sampling_frequency(self) -> float:
        return self.sampling_frequency

    def get_property(self, name: str):
        return self.properties[name]


def stim_events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_time_s": [1.0, 2.0],
            "sequence_number": [1, 2],
            "stimulated_wells": ["A1", "A1"],
        }
    )


class TestStimResponseEligibility(unittest.TestCase):
    def test_lumos_plate_detection(self) -> None:
        self.assertTrue(is_lumos_plate(plate_family="lumos_48well"))
        self.assertTrue(is_lumos_plate(plate_type_name="FortyEightWellLumos"))
        self.assertFalse(is_lumos_plate(plate_family="cytoview_6well"))

    def test_non_lumos_is_disabled(self) -> None:
        eligibility = assess_stim_response_eligibility(
            StimResponseInputs(
                analyzer_path=None,
                recording_name="rec",
                well="A1",
                plate_family="cytoview_6well",
            ),
            stim_events=stim_events(),
        )

        self.assertFalse(eligibility.enabled)
        self.assertFalse(eligibility.is_lumos_plate)

    def test_lumos_without_events_is_disabled(self) -> None:
        eligibility = assess_stim_response_eligibility(
            StimResponseInputs(
                analyzer_path=None,
                recording_name="rec",
                well="A1",
                plate_family="lumos_48well",
            ),
            stim_events=pd.DataFrame(columns=["event_time_s", "sequence_number", "stimulated_wells"]),
        )

        self.assertFalse(eligibility.enabled)
        self.assertEqual(eligibility.stim_event_count, 0)

    def test_lumos_with_events_but_no_pulses_still_allows_train_context(self) -> None:
        pulse_structure = inspect_pulse_structure(stim_events(), [])
        eligibility = assess_stim_response_eligibility(
            StimResponseInputs(
                analyzer_path=None,
                recording_name="rec",
                well="A1",
                plate_family="lumos_48well",
            ),
            stim_events=stim_events(),
            pulse_structure=pulse_structure,
        )

        self.assertTrue(eligibility.enabled)
        self.assertEqual(pulse_structure.status, "disabled")
        self.assertFalse(pulse_structure.pulse_tab_enabled)


class TestPulseStructure(unittest.TestCase):
    def test_uniform_non_five_pulse_template_is_dynamic(self) -> None:
        pulses = [
            PulseEpoch(pulse_index=1, start_ms=0.0, end_ms=5.0),
            PulseEpoch(pulse_index=2, start_ms=20.0, end_ms=25.0),
            PulseEpoch(pulse_index=3, start_ms=40.0, end_ms=45.0),
        ]

        report = inspect_pulse_structure(stim_events(), pulses)

        self.assertEqual(report.status, "uniform")
        self.assertTrue(report.pulse_tab_enabled)
        self.assertEqual(report.pulse_count_per_train, (3, 3))
        self.assertEqual([pulse.pulse_index for pulse in report.pulse_epochs], [1, 2, 3])

    def test_mixed_pulse_templates_are_reported(self) -> None:
        event_pulses = {
            1: [PulseEpoch(pulse_index=1, start_ms=0.0, end_ms=5.0)],
            2: [
                PulseEpoch(pulse_index=1, start_ms=0.0, end_ms=5.0),
                PulseEpoch(pulse_index=2, start_ms=20.0, end_ms=25.0),
            ],
        }

        report = inspect_pulse_structure(
            stim_events(),
            [],
            event_pulse_epochs=event_pulses,
        )

        self.assertEqual(report.status, "grouped_template")
        self.assertFalse(report.pulse_intervals_consistent)
        self.assertEqual(report.pulse_count_per_train, (1, 2))
        self.assertEqual(sorted(report.template_groups), ["template_1", "template_2"])

    def test_command_intervals_are_preserved_for_plotting(self) -> None:
        command_intervals = [(0.0, 2.0, 0.2), (2.0, 5.0, 1.0)]
        report = inspect_pulse_structure(
            stim_events(),
            [PulseEpoch(pulse_index=1, start_ms=0.0, end_ms=5.0)],
            command_intervals_ms=command_intervals,
        )

        self.assertEqual(report.status, "uniform")
        self.assertEqual(report.command_intervals_ms, tuple(command_intervals))


class TestUnitStimResponseBuilder(unittest.TestCase):
    def test_default_units_are_ranked_by_pulse_locked_response(self) -> None:
        events = stim_events()
        pulses = [PulseEpoch(pulse_index=1, start_ms=0.0, end_ms=5.0)]
        pulse_structure = inspect_pulse_structure(events, pulses)
        sorting = FakeSorting(
            {
                0: [990, 1990],  # baseline spikes before each event
                4: [1001, 2001],  # post-pulse spikes after each event
                5: [1002, 2002, 2003],  # strongest post-pulse unit
            }
        )
        builder = UnitStimResponseBuilder(
            sorting=sorting,
            sampling_frequency_hz=1000.0,
            stim_events=events,
            well="A1",
            pulse_structure=pulse_structure,
            train_window=AnalysisWindow(pre_ms=25.0, post_ms=50.0),
            pulse_window=PulseWindow(pre_ms=25.0, post_ms=50.0),
            train_psth_config=PsthConfig(bin_ms=10.0, boxcar_kernel=(1.0,)),
            pulse_psth_config=PsthConfig(bin_ms=10.0, boxcar_kernel=(1.0,)),
        )

        labels = _default_opto_unit_labels(
            builder,
            {"0": (0,), "4": (4,), "5": (5,)},
            limit=2,
        )

        self.assertEqual(labels, ["5", "4"])

    def test_pulse_ranking_uses_jitter_tolerant_response_window(self) -> None:
        events = stim_events()
        pulses = [PulseEpoch(pulse_index=1, start_ms=0.0, end_ms=5.0)]
        pulse_structure = inspect_pulse_structure(events, pulses)
        sorting = FakeSorting(
            {
                0: [990, 1990],  # baseline spikes at -10 ms
                7: [996, 1996],  # jittered response spikes at -4 ms
            }
        )
        builder = UnitStimResponseBuilder(
            sorting=sorting,
            sampling_frequency_hz=1000.0,
            stim_events=events,
            well="A1",
            pulse_structure=pulse_structure,
            train_window=AnalysisWindow(pre_ms=25.0, post_ms=50.0),
            pulse_window=PulseWindow(pre_ms=25.0, post_ms=50.0),
            train_psth_config=PsthConfig(bin_ms=10.0, boxcar_kernel=(1.0,)),
            pulse_psth_config=PsthConfig(bin_ms=10.0, boxcar_kernel=(1.0,)),
        )

        labels = _default_opto_unit_labels(
            builder,
            {"0": (0,), "7": (7,)},
            limit=2,
        )

        self.assertEqual(labels, ["7"])

    def test_pulse_ranking_cap_ignores_responses_after_first_n_trials(self) -> None:
        events = pd.DataFrame(
            {
                "event_time_s": [1.0, 2.0, 3.0],
                "sequence_number": [1, 2, 3],
                "stimulated_wells": ["A1", "A1", "A1"],
            }
        )
        pulses = [PulseEpoch(pulse_index=1, start_ms=0.0, end_ms=5.0)]
        sorting = FakeSorting(
            {
                0: [3001, 3002, 3003, 3004],  # strongest only after the review cap
                1: [1001, 2001],
            }
        )
        builder = UnitStimResponseBuilder(
            sorting=sorting,
            sampling_frequency_hz=1000.0,
            stim_events=events,
            well="A1",
            pulse_structure=inspect_pulse_structure(events, pulses),
        )

        labels = _default_opto_unit_labels(
            builder,
            {"0": (0,), "1": (1,)},
            limit=1,
            max_pulse_trials=2,
        )

        self.assertEqual(labels, ["1"])

    def test_curation_removed_units_and_merge_groups_are_reflected(self) -> None:
        groups = _label_to_unit_groups(
            [0, 4, 5, 9],
            {
                "removed": [9],
                "merges": [{"unit_ids": [0, 4]}],
            },
        )

        self.assertEqual(groups, {"merge:0+4": (0, 4), "5": (5,)})

    def test_response_label_handles_merged_unit_group(self) -> None:
        response = UnitStimResponseBuilder(
            sorting=FakeSorting({0: [], 4: []}),
            sampling_frequency_hz=1000.0,
            stim_events=stim_events(),
            well="A1",
            pulse_structure=inspect_pulse_structure(
                stim_events(),
                [PulseEpoch(pulse_index=1, start_ms=0.0, end_ms=5.0)],
            ),
        ).build([0, 4])

        self.assertEqual(_response_unit_label(response), "0+4")

    def test_unit_selection_text_accepts_dotted_or_comma_lists(self) -> None:
        label_to_unit = {"0": 0, "4": 4, "5": 5}

        self.assertEqual(_split_unit_selection_tokens(["0.4.5"]), ["0", "4", "5"])
        self.assertEqual(
            _resolve_unit_selection_labels(["0, 4 5"], label_to_unit, "0"),
            (["0", "4", "5"], []),
        )

    def test_invalid_unit_selection_does_not_fall_back_to_default_unit(self) -> None:
        label_to_unit = {"0": 0, "4": 4, "5": 5}

        labels, missing = _resolve_unit_selection_labels(["12"], label_to_unit, "0")

        self.assertEqual(labels, [])
        self.assertEqual(missing, ["12"])

    def test_unit_spikes_are_train_and_pulse_aligned(self) -> None:
        events = stim_events()
        pulses = [
            PulseEpoch(pulse_index=1, start_ms=0.0, end_ms=5.0),
            PulseEpoch(pulse_index=2, start_ms=20.0, end_ms=25.0),
        ]
        pulse_structure = inspect_pulse_structure(events, pulses)
        sorting = FakeSorting(
            {
                101: [
                    1000,  # trial 1, P1 at 0 ms
                    1019,  # trial 1, P1 before next pulse
                    1025,  # trial 1, P2 at 5 ms; not P1 because P1 truncates at 20 ms
                    2020,  # trial 2, P2 at 0 ms
                ]
            }
        )
        builder = UnitStimResponseBuilder(
            sorting=sorting,
            sampling_frequency_hz=1000.0,
            stim_events=events,
            well="A1",
            pulse_structure=pulse_structure,
            train_window=AnalysisWindow(pre_ms=5.0, post_ms=50.0),
            pulse_window=PulseWindow(pre_ms=5.0, post_ms=50.0),
            train_psth_config=PsthConfig(bin_ms=10.0, boxcar_kernel=(1.0,)),
            pulse_psth_config=PsthConfig(bin_ms=10.0, boxcar_kernel=(1.0,)),
        )

        response = builder.build([101])

        self.assertEqual(response.train_trials, (1, 2))
        self.assertEqual(
            [round(value, 6) for value in response.train_aligned_spikes["aligned_time_ms"].tolist()],
            [0.0, 19.0, 25.0, 20.0],
        )
        self.assertEqual(len(response.pulse_trials), 4)
        self.assertEqual(response.pulse_aligned_spikes["pulse_label"].tolist(), ["P1", "P1", "P2", "P2", "P2"])
        self.assertEqual(
            [round(value, 6) for value in response.pulse_aligned_spikes["pulse_aligned_time_ms"].tolist()],
            [0.0, 19.0, -1.0, 5.0, 0.0],
        )

        # Pulse PSTH denominator is four pseudo-trials, not two train trials.
        first_bin_rate = response.pulse_psth.loc[
            response.pulse_psth["bin_center_ms"] == 0.0,
            "rate_hz",
        ].iloc[0]
        self.assertEqual(first_bin_rate, 100.0)

    def test_build_many_matches_single_builds(self) -> None:
        events = stim_events()
        pulses = [
            PulseEpoch(pulse_index=1, start_ms=0.0, end_ms=5.0),
            PulseEpoch(pulse_index=2, start_ms=20.0, end_ms=25.0),
        ]
        builder = UnitStimResponseBuilder(
            sorting=FakeSorting({101: [1000, 1020], 202: [1001, 2020]}),
            sampling_frequency_hz=1000.0,
            stim_events=events,
            well="A1",
            pulse_structure=inspect_pulse_structure(events, pulses),
            train_window=AnalysisWindow(pre_ms=5.0, post_ms=50.0),
            pulse_window=PulseWindow(pre_ms=5.0, post_ms=50.0),
            train_psth_config=PsthConfig(bin_ms=10.0, boxcar_kernel=(1.0,)),
            pulse_psth_config=PsthConfig(bin_ms=10.0, boxcar_kernel=(1.0,)),
        )

        batched = builder.build_many([[101], [202]])
        single_101 = builder.build([101])
        single_202 = builder.build([202])

        self.assertEqual(len(batched[0].train_aligned_spikes), len(single_101.train_aligned_spikes))
        self.assertEqual(len(batched[0].pulse_aligned_spikes), len(single_101.pulse_aligned_spikes))
        self.assertEqual(len(batched[1].train_aligned_spikes), len(single_202.train_aligned_spikes))
        self.assertEqual(len(batched[1].pulse_aligned_spikes), len(single_202.pulse_aligned_spikes))

    def test_first_n_pulse_trials_caps_raster_and_psth_denominator(self) -> None:
        events = stim_events()
        pulses = [
            PulseEpoch(pulse_index=1, start_ms=0.0, end_ms=5.0),
            PulseEpoch(pulse_index=2, start_ms=20.0, end_ms=25.0),
        ]
        builder = UnitStimResponseBuilder(
            sorting=FakeSorting({101: [1000, 1020, 2000, 2020]}),
            sampling_frequency_hz=1000.0,
            stim_events=events,
            well="A1",
            pulse_structure=inspect_pulse_structure(events, pulses),
            train_window=AnalysisWindow(pre_ms=5.0, post_ms=50.0),
            pulse_window=PulseWindow(pre_ms=5.0, post_ms=50.0),
            pulse_psth_config=PsthConfig(bin_ms=10.0, boxcar_kernel=(1.0,)),
        )

        response = builder.build([101], max_pulse_trials=3)

        self.assertEqual(len(response.pulse_trials), 3)
        self.assertEqual(sorted(response.pulse_aligned_spikes["pulse_trial_index"].unique()), [1, 2, 3])
        first_bin_rate = response.pulse_psth.loc[
            response.pulse_psth["bin_center_ms"] == 0.0,
            "rate_hz",
        ].iloc[0]
        self.assertAlmostEqual(first_bin_rate, 100.0)

    def test_rapid_review_keeps_and_ranks_only_good_units(self) -> None:
        events = stim_events()
        pulses = [PulseEpoch(pulse_index=1, start_ms=0.0, end_ms=5.0)]
        sorting = FakeSorting(
            {0: [1001, 2001], 1: [1002, 2002, 2003], 2: [1003, 2003]},
            properties={"KSLabel": ["good", "mua", "good"]},
        )
        builder = UnitStimResponseBuilder(
            sorting=sorting,
            sampling_frequency_hz=1000.0,
            stim_events=events,
            well="A1",
            pulse_structure=inspect_pulse_structure(events, pulses),
        )
        groups = {"0": (0,), "1": (1,), "2": (2,)}

        good = kslabel_good_unit_groups(sorting, groups)
        table = build_rapid_opto_review_table(
            builder,
            groups,
            sorting,
            max_pulse_trials=2,
        )

        self.assertEqual(good, {"0": (0,), "2": (2,)})
        self.assertEqual(set(table["unit"]), {"0", "2"})
        self.assertTrue(table["KSLabel"].eq("good").all())
        self.assertTrue(table["pulse_trials_reviewed"].eq(2).all())

    def test_aligned_waveform_cache_loader_matches_recording_well_and_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics_path = root / "metrics.csv"
            traces_path = root / "traces.csv.gz"
            pd.DataFrame(
                {
                    "unit_key": ["rec|A1|4", "other|A1|4"],
                    "recording": ["rec", "other"],
                    "well": ["A1", "A1"],
                    "unit_id": [4, 4],
                    "KSLabel": ["good", "good"],
                    "usable_snippets": [500, 500],
                    "after_trough_to_peak_duration_ms": [0.4, 1.0],
                    "after_spike_half_width_ms": [0.16, 0.3],
                    "after_template_ptp_best_channel_uV": [40.0, 20.0],
                    "after_rs_fs_classification": ["FS_like", "RS_like"],
                }
            ).to_csv(metrics_path, index=False)
            pd.DataFrame(
                {
                    "unit_key": ["rec|A1|4", "rec|A1|4", "other|A1|4"],
                    "unit_id": [4, 4, 4],
                    "time_ms": [-0.1, 0.0, 0.0],
                    "after_aligned_average_uV": [1.0, -10.0, -2.0],
                }
            ).to_csv(traces_path, index=False, compression="gzip")

            reviews = load_aligned_waveform_reviews(
                "rec",
                "A1",
                metrics_csv=metrics_path,
                traces_csv=traces_path,
            )

        self.assertEqual(list(reviews), ["4"])
        self.assertEqual(reviews["4"].rs_fs_classification, "FS_like")
        np.testing.assert_allclose(reviews["4"].aligned_average_uv, [1.0, -10.0])

    def test_events_for_other_well_are_ignored(self) -> None:
        events = pd.DataFrame(
            {
                "event_time_s": [1.0],
                "sequence_number": [1],
                "stimulated_wells": ["B2"],
            }
        )
        pulse_structure = inspect_pulse_structure(
            events,
            [PulseEpoch(pulse_index=1, start_ms=0.0, end_ms=5.0)],
        )
        builder = UnitStimResponseBuilder(
            sorting=FakeSorting({101: [1000]}),
            sampling_frequency_hz=1000.0,
            stim_events=events,
            well="A1",
            pulse_structure=pulse_structure,
        )

        response = builder.build([101])

        self.assertEqual(response.train_trials, ())
        self.assertTrue(response.train_aligned_spikes.empty)
        self.assertTrue(response.pulse_trials.empty)


class TestRawStimResolution(unittest.TestCase):
    no_stim_raw = Path(
        "/nfs/turbo/umms-parent/axion_mea_files_directory/incoming/"
        "manny4tbum_20260706/6_18_2026/129-8445/ventral_sosrs(000).raw"
    )
    stim_raw = Path(
        "/nfs/turbo/umms-parent/axion_mea_files_directory/incoming/"
        "manny4tbum_20260706/6_22_2026/129-8445/"
        "ventral_sosrs_opsin_day3(003).raw"
    )

    def test_empty_raw_stim_table_is_valid_empty_dataframe(self) -> None:
        if not self.no_stim_raw.exists():
            self.skipTest("fixture raw file is not available")

        events = stim_events_from_raw(self.no_stim_raw)

        self.assertTrue(events.empty)
        self.assertIn("event_time_s", events.columns)
        self.assertIn("sequence_number", events.columns)

    def test_raw_no_stim_resolution_reports_no_events_not_sidecar_failure(self) -> None:
        if not self.no_stim_raw.exists():
            self.skipTest("fixture raw file is not available")

        resolution = resolve_stim_sidecars(
            recording_name="6_18_2026_129-8445_ventral_sosrs(000)",
            well="A3",
            raw_file=self.no_stim_raw,
            plate_family="lumos_48well",
        )

        self.assertFalse(resolution.eligibility.enabled)
        self.assertEqual(resolution.eligibility.parse_status, "ok")
        self.assertIn("no stimulation event tags", resolution.message)
        self.assertIn("No opto command intervals", resolution.message)
        self.assertNotIn("sidecar parse failed", resolution.message.lower())

    def test_raw_command_intervals_are_available_for_good_lumos_raw(self) -> None:
        if not self.stim_raw.exists():
            self.skipTest("fixture raw file is not available")

        intervals = load_opto_intervals_from_raw(self.stim_raw)
        resolution = resolve_stim_sidecars(
            recording_name="6_22_2026_129-8445_ventral_sosrs_opsin_day3(003)",
            well="A3",
            raw_file=self.stim_raw,
            plate_family="lumos_48well",
        )

        self.assertGreater(len(intervals), 0)
        self.assertTrue(resolution.eligibility.enabled)
        self.assertIsNotNone(resolution.pulse_structure)
        self.assertEqual(resolution.pulse_structure.command_intervals_ms, tuple(intervals))


if __name__ == "__main__":
    unittest.main()
