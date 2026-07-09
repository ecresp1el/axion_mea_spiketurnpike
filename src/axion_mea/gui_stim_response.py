"""Unit-level opto-stim response tables for GUI curation context.

This module is the data-only foundation for an Axion-specific response window
inside the SpikeInterface GUI. It intentionally does not import Panel/Bokeh:
the alignment and PSTH math should be testable before any GUI wiring exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence
import re

import numpy as np
import pandas as pd

from .io import AxionStimFile


@dataclass(frozen=True)
class AnalysisWindow:
    """Train-level alignment window expressed in milliseconds."""

    pre_ms: float
    post_ms: float

    @property
    def start_ms(self) -> float:
        return -abs(self.pre_ms)

    @property
    def end_ms(self) -> float:
        return abs(self.post_ms)


@dataclass(frozen=True)
class PulseWindow:
    """Pulse-level alignment window expressed in milliseconds."""

    pre_ms: float
    post_ms: float

    @property
    def start_ms(self) -> float:
        return -abs(self.pre_ms)

    @property
    def end_ms(self) -> float:
        return abs(self.post_ms)


@dataclass(frozen=True)
class PsthConfig:
    """Histogram and smoothing settings for PSTH construction."""

    bin_ms: float
    boxcar_kernel: tuple[float, ...]

    @property
    def normalized_kernel(self) -> np.ndarray:
        kernel = np.asarray(self.boxcar_kernel, dtype=float)
        return kernel / kernel.sum()


@dataclass(frozen=True)
class PulseEpoch:
    """One pulse interval inside a stimulation train."""

    pulse_index: int
    start_ms: float
    end_ms: float


class PsthBuilder:
    """Build peristimulus time histograms from aligned spike times."""

    def __init__(
        self,
        well_spikes: pd.DataFrame,
        trials: Sequence[int],
        config: PsthConfig,
        time_column: str,
    ) -> None:
        self.well_spikes = well_spikes
        self.trials = trials
        self.config = config
        self.time_column = time_column

    def build(self, window: AnalysisWindow | PulseWindow) -> pd.DataFrame:
        edges = np.arange(window.start_ms, window.end_ms + self.config.bin_ms, self.config.bin_ms)
        values = (
            self.well_spikes[self.time_column]
            if self.time_column in self.well_spikes.columns
            else pd.Series(dtype=float)
        )
        counts, edges = np.histogram(values, bins=edges)
        centers = (edges[:-1] + edges[1:]) / 2
        n_trials = max(len(self.trials), 1)
        bin_width_s = self.config.bin_ms / 1000.0
        rate_hz = counts / (n_trials * bin_width_s)
        smooth_rate_hz = np.convolve(rate_hz, self.config.normalized_kernel, mode="same")
        return pd.DataFrame(
            {
                "bin_center_ms": centers,
                "count": counts,
                "rate_hz": rate_hz,
                "smooth_rate_hz": smooth_rate_hz,
            }
        )


DEFAULT_TRAIN_WINDOW = AnalysisWindow(pre_ms=200.0, post_ms=800.0)
DEFAULT_PULSE_WINDOW = PulseWindow(pre_ms=25.0, post_ms=100.0)
DEFAULT_TRAIN_PSTH = PsthConfig(bin_ms=20.0, boxcar_kernel=(1.0, 1.0, 1.0))
DEFAULT_PULSE_PSTH = PsthConfig(bin_ms=1.0, boxcar_kernel=(1.0,))
DEFAULT_STIM_RAW_ROOTS = (
    Path("/nfs/turbo/umms-parent/axion_mea_files_directory/incoming/manny4tbum_20260706"),
    Path("/nfs/turbo/umms-parent/axion_mea_files_directory"),
)


@dataclass(frozen=True)
class StimResponseInputs:
    """Resolved sidecars and metadata for one GUI-opened analyzer/well."""

    analyzer_path: Path | None
    recording_name: str
    well: str
    plate_family: str = ""
    plate_type_name: str = ""
    stim_events_csv: Path | None = None
    raw_file: Path | None = None


@dataclass(frozen=True)
class PulseStructureReport:
    """Summary of whether pulse-level rendering is safe for one recording."""

    status: str
    pulse_count_per_train: tuple[int, ...]
    pulse_start_offsets_ms: tuple[tuple[float, ...], ...]
    pulse_durations_ms: tuple[tuple[float, ...], ...]
    pulse_intervals_consistent: bool
    pulse_epochs: tuple[PulseEpoch, ...] = ()
    template_groups: dict[str, list[int]] = field(default_factory=dict)
    message: str = ""

    @property
    def pulse_tab_enabled(self) -> bool:
        """Return whether pulse-level views can be rendered without guessing."""

        return self.status in {"uniform", "grouped_template"}


@dataclass(frozen=True)
class StimResponseEligibility:
    """Decision record for showing or hiding the opto-stim response window."""

    is_lumos_plate: bool
    has_stim_event_table: bool
    stim_event_count: int
    has_raw_or_cached_waveform: bool
    parse_status: str
    stimulated_wells: tuple[str, ...]
    pulse_structure_status: str
    message: str

    @property
    def enabled(self) -> bool:
        """Return whether the response window should be available."""

        return (
            self.is_lumos_plate
            and self.has_stim_event_table
            and self.stim_event_count > 0
            and self.parse_status == "ok"
        )


@dataclass(frozen=True)
class UnitStimResponse:
    """All unit-level response tables needed by the first GUI prototype."""

    selected_unit_ids: tuple[object, ...]
    train_aligned_spikes: pd.DataFrame
    train_trials: tuple[int, ...]
    train_psth: pd.DataFrame
    pulse_aligned_spikes: pd.DataFrame
    pulse_trials: pd.DataFrame
    pulse_psth: pd.DataFrame
    pulse_structure: PulseStructureReport


@dataclass(frozen=True)
class StimSidecarResolution:
    """Resolved raw/stim metadata for one recording opened in the GUI."""

    inputs: StimResponseInputs
    stim_events: pd.DataFrame | None
    pulse_structure: PulseStructureReport | None
    eligibility: StimResponseEligibility
    message: str


def load_stim_events_csv(path: str | Path) -> pd.DataFrame:
    """Load and normalize a stimulation event CSV."""

    stim_events = pd.read_csv(Path(path))
    return normalize_stim_events(stim_events)


def stim_events_from_raw(raw_file: str | Path) -> pd.DataFrame:
    """Parse one Axion raw file and return normalized stimulation events."""

    stim_file = AxionStimFile(Path(raw_file))
    stim_file.parse()
    rows = []
    for summary in stim_file.summarize_stimulation_events():
        rows.append(
            {
                "event_time_s": summary.event_time_s,
                "event_time_sample": summary.event_time_sample,
                "sequence_number": summary.sequence_number,
                "source_kind": summary.source_kind,
                "stimulation_duration_s": summary.stimulation_duration_s,
                "artifact_elimination_duration_s": summary.artifact_elimination_duration_s,
                "event_description": summary.event_description,
                "event_data_id": summary.event_data_id,
                "waveform_tag_guid": summary.waveform_tag_guid,
                "channels_tag_guid": summary.channels_tag_guid,
                "stimulated_wells": ";".join(summary.stimulated_wells),
                "led_count": len(summary.led_positions),
                "channel_mapping_count": len(summary.channel_mappings),
            }
        )
    return normalize_stim_events(pd.DataFrame(rows))


def normalize_stim_events(stim_events: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of stim events with numeric timing/index columns."""

    events = stim_events.copy()
    if "event_time_s" not in events.columns:
        raise ValueError("Stim event table is missing required column: event_time_s")
    if "sequence_number" not in events.columns:
        raise ValueError("Stim event table is missing required column: sequence_number")

    events["event_time_s"] = pd.to_numeric(events["event_time_s"], errors="coerce")
    events["sequence_number"] = pd.to_numeric(events["sequence_number"], errors="coerce").astype("Int64")
    events = events.dropna(subset=["event_time_s", "sequence_number"]).copy()
    events["sequence_number"] = events["sequence_number"].astype(int)
    return events.sort_values(["sequence_number", "event_time_s"]).reset_index(drop=True)


def is_lumos_plate(plate_family: str = "", plate_type_name: str = "") -> bool:
    """Return whether plate metadata identifies a Lumos 48-well recording."""

    text = f"{plate_family} {plate_type_name}".lower()
    return "lumos" in text or "fortyeightwell" in text or "48well" in text


def stimulated_wells_from_events(stim_events: pd.DataFrame) -> tuple[str, ...]:
    """Return sorted stimulated wells listed in the stim-event table."""

    if "stimulated_wells" not in stim_events.columns:
        return ()

    wells: set[str] = set()
    for value in stim_events["stimulated_wells"].dropna():
        for well in str(value).split(";"):
            clean = well.strip()
            if clean:
                wells.add(clean)
    return tuple(sorted(wells))


def build_pulse_epochs(
    intervals: Sequence[tuple[float, float, float] | object],
    merge_gap_ms: float = 5.0,
) -> list[PulseEpoch]:
    """Merge adjacent optical intervals into pulse epochs.

    The raw XML can encode one biological pulse as several micro-ops. This
    mirrors the existing well-response code while keeping it reusable here.
    """

    interval_rows: list[tuple[float, float]] = []
    for interval in intervals:
        if hasattr(interval, "start_ms") and hasattr(interval, "end_ms"):
            start_ms = float(getattr(interval, "start_ms"))
            end_ms = float(getattr(interval, "end_ms"))
        else:
            row = tuple(interval)  # type: ignore[arg-type]
            start_ms = float(row[0])
            end_ms = float(row[1])
        interval_rows.append((start_ms, end_ms))

    if not interval_rows:
        return []

    merged: list[list[float]] = []
    for start_ms, end_ms in sorted(interval_rows, key=lambda row: row[0]):
        if not merged:
            merged.append([start_ms, end_ms])
            continue
        previous = merged[-1]
        if start_ms - previous[1] <= merge_gap_ms:
            previous[1] = max(previous[1], end_ms)
        else:
            merged.append([start_ms, end_ms])

    return [
        PulseEpoch(pulse_index=index + 1, start_ms=start, end_ms=end)
        for index, (start, end) in enumerate(merged)
    ]


def load_pulse_epochs_from_raw(raw_file: str | Path) -> list[PulseEpoch]:
    """Parse one Axion raw file and return merged optical pulse epochs."""

    stim_file = AxionStimFile(Path(raw_file))
    stim_file.parse()
    return build_pulse_epochs(stim_file.opto_on_intervals_ms())


def resolve_stim_sidecars(
    recording_name: str,
    well: str,
    *,
    analyzer_path: Path | None = None,
    raw_roots: Sequence[Path] = DEFAULT_STIM_RAW_ROOTS,
    stim_events_csv: Path | None = None,
    raw_file: Path | None = None,
    plate_family: str = "",
    plate_type_name: str = "",
) -> StimSidecarResolution:
    """Resolve and parse stim sidecars for a GUI-opened recording/well."""

    resolved_raw = raw_file.expanduser().resolve() if raw_file is not None else None
    if resolved_raw is None:
        resolved_raw = find_matching_raw_file(recording_name, raw_roots)

    inferred_plate_family = plate_family
    inferred_plate_type = plate_type_name
    if not inferred_plate_family and not inferred_plate_type:
        if _looks_like_lumos_recording(recording_name, resolved_raw):
            inferred_plate_family = "lumos_48well"

    inputs = StimResponseInputs(
        analyzer_path=analyzer_path,
        recording_name=recording_name,
        well=well,
        plate_family=inferred_plate_family,
        plate_type_name=inferred_plate_type,
        stim_events_csv=stim_events_csv,
        raw_file=resolved_raw,
    )

    stim_events: pd.DataFrame | None = None
    pulse_structure: PulseStructureReport | None = None
    parse_status = "ok"
    message_parts: list[str] = []

    try:
        if stim_events_csv is not None and stim_events_csv.exists():
            stim_events = load_stim_events_csv(stim_events_csv)
            message_parts.append(f"Loaded stim events: {stim_events_csv}")
        elif resolved_raw is not None and resolved_raw.exists():
            stim_events = stim_events_from_raw(resolved_raw)
            message_parts.append(f"Parsed stim events from raw: {resolved_raw}")
        else:
            message_parts.append("No matching raw/stim-event sidecar was resolved.")

        if stim_events is not None and resolved_raw is not None and resolved_raw.exists():
            pulse_epochs = load_pulse_epochs_from_raw(resolved_raw)
            pulse_structure = inspect_pulse_structure(stim_events, pulse_epochs)
        elif stim_events is not None:
            pulse_structure = inspect_pulse_structure(stim_events, [])
    except Exception as exc:  # noqa: BLE001 - GUI should show parse failure, not crash
        parse_status = f"{type(exc).__name__}: {exc}"
        message_parts.append(f"Stim sidecar parse failed: {parse_status}")

    eligibility = assess_stim_response_eligibility(
        inputs,
        stim_events=stim_events,
        pulse_structure=pulse_structure,
        parse_status=parse_status,
    )
    return StimSidecarResolution(
        inputs=inputs,
        stim_events=stim_events,
        pulse_structure=pulse_structure,
        eligibility=eligibility,
        message="\n".join(message_parts + [eligibility.message]),
    )


def find_matching_raw_file(recording_name: str, raw_roots: Sequence[Path]) -> Path | None:
    """Find the most likely Axion raw file for a Step 1 recording folder name."""

    recording_key = _normalized_match_text(recording_name)
    candidates: list[tuple[int, int, Path]] = []
    for root in raw_roots:
        root = root.expanduser()
        if not root.exists():
            continue
        for path in root.rglob("*.raw"):
            stem = _raw_base_stem(path)
            key = _normalized_match_text(stem)
            if not key or key not in recording_key:
                continue
            suffix_penalty = _raw_variant_penalty(path)
            candidates.append((len(key), -suffix_penalty, path.resolve()))

    if not candidates:
        return None
    return sorted(candidates, reverse=True)[0][2]


def inspect_pulse_structure(
    stim_events: pd.DataFrame,
    pulse_epochs: Sequence[PulseEpoch],
    *,
    event_pulse_epochs: Mapping[int, Sequence[PulseEpoch]] | None = None,
    max_grouped_templates: int = 4,
) -> PulseStructureReport:
    """Classify pulse structure as uniform, grouped-template, train-only, or disabled."""

    events = normalize_stim_events(stim_events)
    if events.empty:
        return PulseStructureReport(
            status="disabled",
            pulse_count_per_train=(),
            pulse_start_offsets_ms=(),
            pulse_durations_ms=(),
            pulse_intervals_consistent=False,
            message="No stimulation events are available.",
        )

    if not pulse_epochs and not event_pulse_epochs:
        return PulseStructureReport(
            status="disabled",
            pulse_count_per_train=tuple(0 for _ in events.itertuples()),
            pulse_start_offsets_ms=tuple(() for _ in events.itertuples()),
            pulse_durations_ms=tuple(() for _ in events.itertuples()),
            pulse_intervals_consistent=False,
            message="No pulse intervals were reconstructed.",
        )

    per_event_epochs: list[tuple[int, tuple[PulseEpoch, ...]]] = []
    for row in events.itertuples(index=False):
        sequence_number = int(getattr(row, "sequence_number"))
        epochs = (
            tuple(event_pulse_epochs.get(sequence_number, ()))  # type: ignore[union-attr]
            if event_pulse_epochs is not None
            else tuple(pulse_epochs)
        )
        per_event_epochs.append((sequence_number, epochs))

    signatures = [_pulse_signature(epochs) for _, epochs in per_event_epochs]
    unique_signatures = sorted(set(signatures))
    pulse_count_per_train = tuple(len(epochs) for _, epochs in per_event_epochs)
    pulse_start_offsets_ms = tuple(
        tuple(round(pulse.start_ms, 6) for pulse in epochs)
        for _, epochs in per_event_epochs
    )
    pulse_durations_ms = tuple(
        tuple(round(pulse.end_ms - pulse.start_ms, 6) for pulse in epochs)
        for _, epochs in per_event_epochs
    )

    if len(unique_signatures) == 1:
        representative_epochs = tuple(per_event_epochs[0][1])
        return PulseStructureReport(
            status="uniform",
            pulse_count_per_train=pulse_count_per_train,
            pulse_start_offsets_ms=pulse_start_offsets_ms,
            pulse_durations_ms=pulse_durations_ms,
            pulse_intervals_consistent=True,
            pulse_epochs=representative_epochs,
            template_groups={"template_1": [seq for seq, _ in per_event_epochs]},
            message=(
                f"Uniform {len(representative_epochs)}-pulse template across "
                f"{len(per_event_epochs)} stimulation events."
            ),
        )

    template_groups: dict[str, list[int]] = {}
    signature_to_label: dict[tuple[tuple[float, float], ...], str] = {}
    for sequence_number, epochs in per_event_epochs:
        signature = _pulse_signature(epochs)
        label = signature_to_label.setdefault(signature, f"template_{len(signature_to_label) + 1}")
        template_groups.setdefault(label, []).append(sequence_number)

    status = "grouped_template" if len(unique_signatures) <= max_grouped_templates else "train_only"
    message = (
        f"Found {len(unique_signatures)} pulse templates across {len(per_event_epochs)} "
        "stimulation events."
    )
    if status == "train_only":
        message += " Pulse pooling should be disabled until a template is selected."

    return PulseStructureReport(
        status=status,
        pulse_count_per_train=pulse_count_per_train,
        pulse_start_offsets_ms=pulse_start_offsets_ms,
        pulse_durations_ms=pulse_durations_ms,
        pulse_intervals_consistent=False,
        pulse_epochs=tuple(pulse_epochs),
        template_groups=template_groups,
        message=message,
    )


def assess_stim_response_eligibility(
    inputs: StimResponseInputs,
    *,
    stim_events: pd.DataFrame | None = None,
    pulse_structure: PulseStructureReport | None = None,
    parse_status: str = "ok",
) -> StimResponseEligibility:
    """Return the gate decision for showing the opto-stim response window."""

    lumos = is_lumos_plate(inputs.plate_family, inputs.plate_type_name)
    has_table = stim_events is not None or (
        inputs.stim_events_csv is not None and Path(inputs.stim_events_csv).exists()
    )

    event_count = 0
    stimulated_wells: tuple[str, ...] = ()
    if stim_events is not None:
        normalized = normalize_stim_events(stim_events)
        event_count = len(normalized)
        stimulated_wells = stimulated_wells_from_events(normalized)
    elif inputs.stim_events_csv is not None and Path(inputs.stim_events_csv).exists():
        normalized = load_stim_events_csv(inputs.stim_events_csv)
        event_count = len(normalized)
        stimulated_wells = stimulated_wells_from_events(normalized)

    has_waveform = inputs.raw_file is not None and Path(inputs.raw_file).exists()
    if pulse_structure is not None and pulse_structure.pulse_epochs:
        has_waveform = True

    pulse_status = pulse_structure.status if pulse_structure is not None else "unknown"
    enabled = lumos and has_table and event_count > 0 and parse_status == "ok"
    if enabled:
        message = (
            f"Stim response enabled for Lumos recording with {event_count} "
            f"stimulation events; pulse status: {pulse_status}."
        )
    elif not lumos:
        message = "Stim response disabled: recording is not resolved as Lumos."
    elif not has_table or event_count == 0:
        message = "Stim response disabled: no usable stimulation events were found."
    else:
        message = f"Stim response disabled: stimulation parse status is {parse_status}."

    return StimResponseEligibility(
        is_lumos_plate=lumos,
        has_stim_event_table=has_table,
        stim_event_count=event_count,
        has_raw_or_cached_waveform=has_waveform,
        parse_status=parse_status,
        stimulated_wells=stimulated_wells,
        pulse_structure_status=pulse_status,
        message=message,
    )


class UnitStimResponseBuilder:
    """Build train- and pulse-locked response tables for selected units."""

    def __init__(
        self,
        sorting,
        sampling_frequency_hz: float,
        stim_events: pd.DataFrame,
        well: str,
        pulse_structure: PulseStructureReport,
        *,
        train_window: AnalysisWindow = DEFAULT_TRAIN_WINDOW,
        pulse_window: PulseWindow = DEFAULT_PULSE_WINDOW,
        train_psth_config: PsthConfig = DEFAULT_TRAIN_PSTH,
        pulse_psth_config: PsthConfig = DEFAULT_PULSE_PSTH,
    ) -> None:
        self.sorting = sorting
        self.sampling_frequency_hz = float(sampling_frequency_hz)
        self.stim_events = normalize_stim_events(stim_events)
        self.well = well
        self.pulse_structure = pulse_structure
        self.train_window = train_window
        self.pulse_window = pulse_window
        self.train_psth_config = train_psth_config
        self.pulse_psth_config = pulse_psth_config

    @classmethod
    def from_analyzer(
        cls,
        analyzer,
        stim_events: pd.DataFrame,
        well: str,
        pulse_structure: PulseStructureReport,
        **kwargs,
    ) -> "UnitStimResponseBuilder":
        """Create a builder from a SpikeInterface SortingAnalyzer-like object."""

        sorting = _sorting_from_analyzer(analyzer)
        sampling_frequency_hz = _sampling_frequency_from_analyzer(analyzer, sorting)
        return cls(
            sorting=sorting,
            sampling_frequency_hz=sampling_frequency_hz,
            stim_events=stim_events,
            well=well,
            pulse_structure=pulse_structure,
            **kwargs,
        )

    def build(self, unit_ids: Sequence[object]) -> UnitStimResponse:
        """Return all response tables for the selected units."""

        selected_unit_ids = tuple(unit_ids)
        train_aligned = self.build_train_aligned_spikes(selected_unit_ids)
        train_trials = tuple(self._eligible_events()["sequence_number"].astype(int).tolist())
        train_psth = PsthBuilder(
            well_spikes=train_aligned,
            trials=list(train_trials),
            config=self.train_psth_config,
            time_column="aligned_time_ms",
        ).build(self.train_window)

        pulse_aligned, pulse_trials = self.build_pulse_aligned_spikes(train_aligned, train_trials)
        pulse_trial_ids = (
            pulse_trials["pulse_trial_index"].astype(int).tolist()
            if not pulse_trials.empty
            else []
        )
        pulse_psth = PsthBuilder(
            well_spikes=pulse_aligned,
            trials=pulse_trial_ids,
            config=self.pulse_psth_config,
            time_column="pulse_aligned_time_ms",
        ).build(self.pulse_window)

        return UnitStimResponse(
            selected_unit_ids=selected_unit_ids,
            train_aligned_spikes=train_aligned,
            train_trials=train_trials,
            train_psth=train_psth,
            pulse_aligned_spikes=pulse_aligned,
            pulse_trials=pulse_trials,
            pulse_psth=pulse_psth,
            pulse_structure=self.pulse_structure,
        )

    def build_train_aligned_spikes(self, unit_ids: Sequence[object]) -> pd.DataFrame:
        """Create one row per selected-unit spike inside each train window."""

        events = self._eligible_events()
        columns = [
            "unit_id",
            "trial_index",
            "stim_time_s",
            "time_s",
            "aligned_time_ms",
        ]
        if events.empty or not unit_ids:
            return pd.DataFrame(columns=columns)

        spike_table = self._selected_spike_table(unit_ids)
        if spike_table.empty:
            return pd.DataFrame(columns=columns)

        rows: list[dict[str, object]] = []
        for event in events.itertuples(index=False):
            stim_time_s = float(getattr(event, "event_time_s"))
            trial_index = int(getattr(event, "sequence_number"))
            window_start_s = stim_time_s + (self.train_window.start_ms / 1000.0)
            window_end_s = stim_time_s + (self.train_window.end_ms / 1000.0)
            in_window = spike_table.loc[
                (spike_table["time_s"] >= window_start_s)
                & (spike_table["time_s"] <= window_end_s)
            ].copy()
            if in_window.empty:
                continue
            in_window["trial_index"] = trial_index
            in_window["stim_time_s"] = stim_time_s
            in_window["aligned_time_ms"] = (in_window["time_s"] - stim_time_s) * 1000.0
            rows.extend(in_window[columns].to_dict(orient="records"))

        if not rows:
            return pd.DataFrame(columns=columns)
        return pd.DataFrame(rows).sort_values(["trial_index", "aligned_time_ms", "unit_id"]).reset_index(drop=True)

    def build_pulse_aligned_spikes(
        self,
        train_aligned_spikes: pd.DataFrame,
        train_trials: Sequence[int],
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Convert train-aligned spikes into pulse-aligned pseudo-trials."""

        pulse_epochs = list(self.pulse_structure.pulse_epochs)
        pulse_trial_columns = [
            "pulse_trial_index",
            "train_trial_index",
            "pulse_index",
            "pulse_label",
            "pulse_start_ms",
            "pulse_end_ms",
            "pulse_window_start_ms",
            "pulse_window_end_ms",
        ]
        spike_columns = [
            "unit_id",
            "pulse_trial_index",
            "train_trial_index",
            "trial_index",
            "pulse_index",
            "pulse_label",
            "pulse_onset_ms",
            "pulse_end_ms",
            "aligned_time_ms",
            "pulse_aligned_time_ms",
            "time_s",
        ]
        if not self.pulse_structure.pulse_tab_enabled or not pulse_epochs:
            return pd.DataFrame(columns=spike_columns), pd.DataFrame(columns=pulse_trial_columns)

        pulse_rows: list[dict[str, object]] = []
        spike_rows: list[dict[str, object]] = []
        pulse_trial_index = 1
        for train_trial_index in train_trials:
            trial_spikes = train_aligned_spikes.loc[
                train_aligned_spikes["trial_index"] == train_trial_index
            ].copy()
            for pulse_idx, pulse in enumerate(pulse_epochs):
                next_start = (
                    pulse_epochs[pulse_idx + 1].start_ms
                    if pulse_idx + 1 < len(pulse_epochs)
                    else np.inf
                )
                pulse_window_start = pulse.start_ms + self.pulse_window.start_ms
                pulse_window_end = min(pulse.start_ms + self.pulse_window.end_ms, next_start)
                pulse_rows.append(
                    {
                        "pulse_trial_index": pulse_trial_index,
                        "train_trial_index": int(train_trial_index),
                        "pulse_index": pulse.pulse_index,
                        "pulse_label": f"P{pulse.pulse_index}",
                        "pulse_start_ms": pulse.start_ms,
                        "pulse_end_ms": pulse.end_ms,
                        "pulse_window_start_ms": pulse_window_start,
                        "pulse_window_end_ms": pulse_window_end,
                    }
                )

                if not trial_spikes.empty:
                    in_window = trial_spikes.loc[
                        (trial_spikes["aligned_time_ms"] >= pulse_window_start)
                        & (trial_spikes["aligned_time_ms"] <= pulse_window_end)
                    ].copy()
                    if not in_window.empty:
                        in_window["pulse_trial_index"] = pulse_trial_index
                        in_window["train_trial_index"] = int(train_trial_index)
                        in_window["pulse_index"] = pulse.pulse_index
                        in_window["pulse_label"] = f"P{pulse.pulse_index}"
                        in_window["pulse_onset_ms"] = pulse.start_ms
                        in_window["pulse_end_ms"] = pulse.end_ms
                        in_window["pulse_aligned_time_ms"] = (
                            in_window["aligned_time_ms"] - pulse.start_ms
                        )
                        spike_rows.extend(in_window[spike_columns].to_dict(orient="records"))
                pulse_trial_index += 1

        pulse_trials = pd.DataFrame(pulse_rows, columns=pulse_trial_columns)
        if not spike_rows:
            return pd.DataFrame(columns=spike_columns), pulse_trials
        pulse_aligned = pd.DataFrame(spike_rows, columns=spike_columns).sort_values(
            ["pulse_trial_index", "pulse_aligned_time_ms", "unit_id"]
        )
        return pulse_aligned.reset_index(drop=True), pulse_trials

    def _eligible_events(self) -> pd.DataFrame:
        """Return events that apply to this well when well metadata is available."""

        if "stimulated_wells" not in self.stim_events.columns:
            return self.stim_events.copy()

        mask = self.stim_events["stimulated_wells"].apply(
            lambda value: _event_includes_well(value, self.well)
        )
        filtered = self.stim_events.loc[mask].copy()
        return filtered if not filtered.empty else self.stim_events.iloc[0:0].copy()

    def _selected_spike_table(self, unit_ids: Sequence[object]) -> pd.DataFrame:
        """Return sorted spike times for all selected unit ids."""

        rows: list[pd.DataFrame] = []
        for unit_id in unit_ids:
            spike_frames = np.asarray(
                self.sorting.get_unit_spike_train(unit_id=unit_id),
                dtype=float,
            )
            if spike_frames.size == 0:
                continue
            rows.append(
                pd.DataFrame(
                    {
                        "unit_id": [unit_id] * len(spike_frames),
                        "time_s": spike_frames / self.sampling_frequency_hz,
                    }
                )
            )
        if not rows:
            return pd.DataFrame(columns=["unit_id", "time_s"])
        return pd.concat(rows, ignore_index=True).sort_values(["time_s", "unit_id"]).reset_index(drop=True)


def _pulse_signature(pulse_epochs: Sequence[PulseEpoch]) -> tuple[tuple[float, float], ...]:
    """Return a stable pulse template signature from starts and durations."""

    return tuple(
        (round(pulse.start_ms, 6), round(pulse.end_ms - pulse.start_ms, 6))
        for pulse in pulse_epochs
    )


def _event_includes_well(value: object, well: str) -> bool:
    """Return whether a semicolon-separated stimulated-wells value includes a well."""

    if pd.isna(value):
        return False
    return well in {item.strip() for item in str(value).split(";") if item.strip()}


def _sorting_from_analyzer(analyzer):
    """Return a sorting object from a SortingAnalyzer-like object."""

    if hasattr(analyzer, "sorting"):
        return analyzer.sorting
    if hasattr(analyzer, "get_sorting"):
        return analyzer.get_sorting()
    raise AttributeError("Analyzer does not expose .sorting or .get_sorting().")


def _sampling_frequency_from_analyzer(analyzer, sorting) -> float:
    """Return sampling frequency from analyzer recording or sorting."""

    recording = getattr(analyzer, "recording", None)
    if recording is not None and hasattr(recording, "get_sampling_frequency"):
        return float(recording.get_sampling_frequency())
    if hasattr(sorting, "get_sampling_frequency"):
        return float(sorting.get_sampling_frequency())
    raise AttributeError("Could not resolve sampling frequency from analyzer or sorting.")
