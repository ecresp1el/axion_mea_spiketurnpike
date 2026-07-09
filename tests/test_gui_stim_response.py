from __future__ import annotations

import sys
import unittest
from pathlib import Path

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
    load_opto_intervals_from_raw,
    inspect_pulse_structure,
    is_lumos_plate,
    resolve_stim_sidecars,
    stim_events_from_raw,
)


class FakeSorting:
    def __init__(self, spike_trains: dict[object, list[int]], sampling_frequency: float = 1000.0) -> None:
        self.spike_trains = spike_trains
        self.sampling_frequency = sampling_frequency

    def get_unit_spike_train(self, unit_id):
        return self.spike_trains.get(unit_id, [])

    def get_sampling_frequency(self) -> float:
        return self.sampling_frequency


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
