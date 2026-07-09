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
class WaveformRenderConfig:
    """Display-resolution settings for the reconstructed command proxy."""

    sample_dt_ms: float
    smooth_window_ms: float

    @property
    def smooth_window_samples(self) -> int:
        return max(1, int(round(self.smooth_window_ms / self.sample_dt_ms)))


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
DEFAULT_PULSE_WINDOW = PulseWindow(pre_ms=25.0, post_ms=50.0)
OPTO_BASELINE_START_MS = -25.0
OPTO_BASELINE_END_MS = -8.0
OPTO_RESPONSE_START_MS = -5.0
OPTO_RESPONSE_END_MS = 50.0
DEFAULT_TRAIN_PSTH = PsthConfig(bin_ms=20.0, boxcar_kernel=(1.0, 1.0, 1.0))
DEFAULT_PULSE_PSTH = PsthConfig(bin_ms=1.0, boxcar_kernel=(1.0,))
DEFAULT_WAVEFORM_RENDER = WaveformRenderConfig(sample_dt_ms=1.0, smooth_window_ms=2.0)
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
    command_intervals_ms: tuple[tuple[float, float, float], ...] = ()
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
class OptoTaggedUnitScore:
    """Pulse-locked response score for choosing default stim panels."""

    unit_label: str
    unit_ids: tuple[object, ...]
    score_hz: float
    post_rate_hz: float
    baseline_rate_hz: float
    post_spikes: int
    baseline_spikes: int


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
    columns = [
        "event_time_s",
        "event_time_sample",
        "sequence_number",
        "source_kind",
        "stimulation_duration_s",
        "artifact_elimination_duration_s",
        "event_description",
        "event_data_id",
        "waveform_tag_guid",
        "channels_tag_guid",
        "stimulated_wells",
        "led_count",
        "channel_mapping_count",
    ]
    return normalize_stim_events(pd.DataFrame(rows, columns=columns))


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

    return build_pulse_epochs(load_opto_intervals_from_raw(raw_file))


def load_opto_intervals_from_raw(raw_file: str | Path) -> list[tuple[float, float, float]]:
    """Parse one Axion raw file and return raw XML optical command intervals."""

    stim_file = AxionStimFile(Path(raw_file))
    stim_file.parse()
    return [
        (float(interval.start_ms), float(interval.end_ms), float(interval.intensity))
        for interval in stim_file.opto_on_intervals_ms()
    ]


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
    source_label = "stimulation metadata"

    try:
        if stim_events_csv is not None and stim_events_csv.exists():
            source_label = "stim event CSV"
            stim_events = load_stim_events_csv(stim_events_csv)
            message_parts.append(f"Loaded stim events: {stim_events_csv}")
        elif resolved_raw is not None and resolved_raw.exists():
            source_label = "raw stimulation metadata"
            stim_events = stim_events_from_raw(resolved_raw)
            if stim_events.empty:
                message_parts.append(
                    "Parsed raw stimulation metadata, but no stimulation event tags were found."
                )
            else:
                message_parts.append(
                    f"Parsed {len(stim_events)} stim events from raw: {resolved_raw}"
                )
        else:
            message_parts.append("No matching raw/stim-event sidecar was resolved.")

        if stim_events is not None and resolved_raw is not None and resolved_raw.exists():
            command_intervals = load_opto_intervals_from_raw(resolved_raw)
            pulse_epochs = build_pulse_epochs(command_intervals)
            if not command_intervals:
                message_parts.append(
                    "No opto command intervals were reconstructed from raw XML micro-ops."
                )
            pulse_structure = inspect_pulse_structure(
                stim_events,
                pulse_epochs,
                command_intervals_ms=command_intervals,
            )
        elif stim_events is not None:
            pulse_structure = inspect_pulse_structure(stim_events, [])
    except Exception as exc:  # noqa: BLE001 - GUI should show parse failure, not crash
        parse_status = f"{type(exc).__name__}: {exc}"
        message_parts.append(f"{source_label.capitalize()} parse failed: {parse_status}")

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


def list_raw_files(raw_roots: Sequence[Path]) -> tuple[Path, ...]:
    """Return all raw files below the requested roots once for fast matching."""

    paths: list[Path] = []
    seen: set[Path] = set()
    for root in raw_roots:
        root = root.expanduser()
        if not root.exists():
            continue
        for path in root.rglob("*.raw"):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                paths.append(resolved)
    return tuple(paths)


def find_matching_raw_file(
    recording_name: str,
    raw_roots: Sequence[Path],
    *,
    raw_paths: Sequence[Path] | None = None,
) -> Path | None:
    """Find the most likely Axion raw file for a Step 1 recording folder name."""

    recording_key = _normalized_match_text(recording_name)
    candidates: list[tuple[int, int, Path]] = []
    paths = raw_paths if raw_paths is not None else list_raw_files(raw_roots)
    for path in paths:
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
    command_intervals_ms: Sequence[tuple[float, float, float]] = (),
    max_grouped_templates: int = 4,
) -> PulseStructureReport:
    """Classify pulse structure as uniform, grouped-template, train-only, or disabled."""

    events = normalize_stim_events(stim_events)
    command_intervals = tuple(
        (float(start_ms), float(end_ms), float(intensity))
        for start_ms, end_ms, intensity in command_intervals_ms
    )
    if events.empty:
        return PulseStructureReport(
            status="disabled",
            pulse_count_per_train=(),
            pulse_start_offsets_ms=(),
            pulse_durations_ms=(),
            pulse_intervals_consistent=False,
            command_intervals_ms=command_intervals,
            message="No stimulation events are available.",
        )

    if not pulse_epochs and not event_pulse_epochs:
        return PulseStructureReport(
            status="disabled",
            pulse_count_per_train=tuple(0 for _ in events.itertuples()),
            pulse_start_offsets_ms=tuple(() for _ in events.itertuples()),
            pulse_durations_ms=tuple(() for _ in events.itertuples()),
            pulse_intervals_consistent=False,
            command_intervals_ms=command_intervals,
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
            command_intervals_ms=command_intervals,
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
        command_intervals_ms=command_intervals,
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

    def build_many(self, unit_groups: Sequence[Sequence[object]]) -> list[UnitStimResponse]:
        """Return response tables for many unit groups with shared alignment work."""

        normalized_groups = [tuple(group) for group in unit_groups]
        unique_units: list[object] = []
        for group in normalized_groups:
            for unit_id in group:
                if unit_id not in unique_units:
                    unique_units.append(unit_id)

        train_aligned_all = self.build_train_aligned_spikes(unique_units)
        train_trials = tuple(self._eligible_events()["sequence_number"].astype(int).tolist())
        responses: list[UnitStimResponse] = []
        for selected_unit_ids in normalized_groups:
            if train_aligned_all.empty or not selected_unit_ids:
                train_aligned = self.build_train_aligned_spikes(())
            else:
                train_aligned = train_aligned_all.loc[
                    train_aligned_all["unit_id"].isin(selected_unit_ids)
                ].copy()

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
            responses.append(
                UnitStimResponse(
                    selected_unit_ids=selected_unit_ids,
                    train_aligned_spikes=train_aligned,
                    train_trials=train_trials,
                    train_psth=train_psth,
                    pulse_aligned_spikes=pulse_aligned,
                    pulse_trials=pulse_trials,
                    pulse_psth=pulse_psth,
                    pulse_structure=self.pulse_structure,
                )
            )
        return responses

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


def make_stim_response_panel(
    analyzer,
    *,
    recording_name: str,
    well: str,
    analyzer_path: Path | None = None,
    raw_roots: Sequence[Path] = DEFAULT_STIM_RAW_ROOTS,
    stim_events_csv: Path | None = None,
    raw_file: Path | None = None,
    plate_family: str = "",
    plate_type_name: str = "",
    curation_state_provider=None,
):
    """Create a Panel tab for unit-level train/pulse response review."""

    import panel as pn

    pn.extension()
    resolution = resolve_stim_sidecars(
        recording_name,
        well,
        analyzer_path=analyzer_path,
        raw_roots=raw_roots,
        stim_events_csv=stim_events_csv,
        raw_file=raw_file,
        plate_family=plate_family,
        plate_type_name=plate_type_name,
    )
    status = pn.pane.Markdown(_format_resolution_status(resolution), sizing_mode="stretch_width")

    if not resolution.eligibility.enabled or resolution.stim_events is None:
        return pn.Column(
            pn.pane.Markdown("## Stim response"),
            status,
            sizing_mode="stretch_width",
        )

    sorting = _sorting_from_analyzer(analyzer)
    unit_ids = _unit_ids_from_sorting(sorting)
    if not unit_ids:
        return pn.Column(
            pn.pane.Markdown("## Stim response"),
            status,
            pn.pane.Markdown("No unit ids were available from the sorting object."),
            sizing_mode="stretch_width",
        )

    pulse_structure = resolution.pulse_structure or inspect_pulse_structure(resolution.stim_events, [])
    builder = UnitStimResponseBuilder.from_analyzer(
        analyzer,
        stim_events=resolution.stim_events,
        well=well,
        pulse_structure=pulse_structure,
    )

    label_to_units = _label_to_unit_groups(unit_ids, _current_curation_state(curation_state_provider))
    if not label_to_units:
        label_to_units = {_unit_label(unit_id): (unit_id,) for unit_id in unit_ids}
    default_labels = _default_opto_unit_labels(builder, label_to_units, limit=10)
    if not default_labels:
        default_labels = list(label_to_units)[:10]
    default_label = default_labels[0]
    unit_selector = pn.widgets.MultiChoice(
        name="Pick units",
        options=list(label_to_units),
        value=default_labels,
        sizing_mode="stretch_width",
    )
    unit_entry = pn.widgets.TextInput(
        name="Units",
        value=",".join(default_labels),
        placeholder="0,4,5",
        sizing_mode="stretch_width",
    )
    refresh_button = pn.widgets.Button(name="Refresh", button_type="primary", width=110)
    summary = pn.pane.Markdown("", sizing_mode="stretch_width")
    train_area = pn.Column(sizing_mode="stretch_width")
    pulse_area = pn.Column(sizing_mode="stretch_width")
    selection_status = pn.pane.Markdown("", sizing_mode="stretch_width")
    syncing_selection = {"active": False}
    active_tab = {"index": 0}
    cached_responses: dict[str, list[UnitStimResponse]] = {"responses": []}
    unit_group_state: dict[str, object] = {
        "label_to_units": label_to_units,
        "default_labels": default_labels,
    }

    def refresh_unit_groups(*, preserve_selection: bool = True) -> None:
        nonlocal default_label
        current_labels = unit_selector.value if preserve_selection else []
        current_entry = unit_entry.value if preserve_selection else ""
        current_unit_ids = _unit_ids_from_sorting(_sorting_from_analyzer(analyzer))
        refreshed = _label_to_unit_groups(
            current_unit_ids,
            _current_curation_state(curation_state_provider),
        )
        if not refreshed:
            refreshed = {_unit_label(unit_id): (unit_id,) for unit_id in current_unit_ids}
        if not refreshed:
            unit_group_state["label_to_units"] = {}
            unit_group_state["default_labels"] = []
            unit_selector.options = []
            unit_selector.value = []
            unit_entry.value = ""
            return

        unit_group_state["label_to_units"] = refreshed
        ranked_defaults = _default_opto_unit_labels(builder, refreshed, limit=10)
        if not ranked_defaults:
            ranked_defaults = list(refreshed)[:10]
        unit_group_state["default_labels"] = ranked_defaults
        default_label = ranked_defaults[0]
        unit_selector.options = list(refreshed)
        if preserve_selection:
            raw_values: Sequence[object] = [current_entry] if current_entry.strip() else current_labels
            labels, _ = _resolve_unit_selection_labels(raw_values, refreshed, default_label)
        else:
            labels = ranked_defaults
        if not labels:
            labels = ranked_defaults
        syncing_selection["active"] = True
        try:
            unit_selector.value = labels
            unit_entry.value = ",".join(labels)
        finally:
            syncing_selection["active"] = False

    def selected_units() -> tuple[list[tuple[object, ...]], list[str], list[str]]:
        current_label_to_units = unit_group_state["label_to_units"]
        if not isinstance(current_label_to_units, dict) or not current_label_to_units:
            return [], [], []
        raw_values: Sequence[object]
        if unit_entry.value.strip():
            raw_values = [unit_entry.value]
        else:
            raw_values = unit_selector.value or [default_label]
        labels, missing = _resolve_unit_selection_labels(raw_values, current_label_to_units, default_label)
        return [current_label_to_units[label] for label in labels], labels, missing

    def sync_picker_to_entry(labels: Sequence[str]) -> None:
        current_label_to_units = unit_group_state["label_to_units"]
        syncing_selection["active"] = True
        try:
            unit_selector.value = [label for label in labels if label in current_label_to_units]
        finally:
            syncing_selection["active"] = False

    def sync_entry_to_picker(*_: object) -> None:
        if syncing_selection["active"]:
            return
        current_label_to_units = unit_group_state["label_to_units"]
        labels, _ = _resolve_unit_selection_labels(unit_selector.value, current_label_to_units, default_label)
        syncing_selection["active"] = True
        try:
            unit_entry.value = ",".join(labels)
        finally:
            syncing_selection["active"] = False
        redraw()

    def redraw_from_entry(*_: object) -> None:
        if syncing_selection["active"]:
            return
        _, labels, _ = selected_units()
        sync_picker_to_entry(labels)
        redraw()

    def render_train(unit_responses: Sequence[UnitStimResponse]) -> None:
        train_items = [
            pn.pane.Matplotlib(
                plot_train_response(response, builder),
                sizing_mode="stretch_width",
                tight=True,
                margin=0,
            )
            for response in unit_responses
        ]
        train_area.objects = [
            pn.GridBox(*train_items, ncols=2, sizing_mode="stretch_width", margin=0)
            if train_items
            else pn.pane.Markdown("No units selected.")
        ]

    def render_pulse(unit_responses: Sequence[UnitStimResponse]) -> None:
        pulse_items = []
        for response in unit_responses:
            if response.pulse_structure.pulse_tab_enabled and not response.pulse_trials.empty:
                pulse_items.append(
                    pn.pane.Matplotlib(
                        plot_pulse_response(response, builder),
                        sizing_mode="stretch_width",
                        tight=True,
                        margin=0,
                    )
                )
            else:
                pulse_items.append(
                    pn.pane.Markdown(
                        f"### Unit {_response_unit_label(response)}\n"
                        f"Pulse view disabled: {response.pulse_structure.message}",
                        sizing_mode="stretch_width",
                    )
                )
        pulse_area.objects = [
            pn.GridBox(*pulse_items, ncols=2, sizing_mode="stretch_width", margin=0)
            if pulse_items
            else pn.pane.Markdown("No units selected.")
        ]

    def set_area_loading(area, message: str) -> None:
        area.objects = [pn.pane.Markdown(message)]
        if hasattr(area, "loading"):
            area.loading = True

    def set_area_ready(area) -> None:
        if hasattr(area, "loading"):
            area.loading = False

    def schedule_render_active_tab() -> None:
        doc = pn.state.curdoc
        if doc is not None:
            doc.add_next_tick_callback(render_active_tab)
        else:
            render_active_tab()

    def render_active_tab() -> None:
        unit_responses = cached_responses["responses"]
        if active_tab["index"] == 0:
            render_train(unit_responses)
            set_area_ready(train_area)
            set_area_ready(pulse_area)
            pulse_area.objects = [pn.pane.Markdown("Pulse locked plots render when this tab is opened.")]
        else:
            render_pulse(unit_responses)
            set_area_ready(pulse_area)
            if not train_area.objects:
                train_area.objects = [pn.pane.Markdown("Train plots render when this tab is opened.")]
            set_area_ready(train_area)

    def redraw(*_: object) -> None:
        if active_tab["index"] == 0:
            set_area_loading(train_area, "Loading top pulse-ranked units in the train locked view...")
            pulse_area.objects = [pn.pane.Markdown("Pulse locked plots render when this tab is opened.")]
        else:
            set_area_loading(pulse_area, "Loading pulse locked plots for the selected units...")
        refresh_unit_groups(preserve_selection=True)
        unit_groups, labels, missing = selected_units()
        selection_status.object = _format_unit_selection_status(labels, missing)
        unit_responses = builder.build_many(unit_groups)
        cached_responses["responses"] = unit_responses
        summary.object = _format_multi_unit_summary(unit_responses, resolution)
        render_active_tab()

    def on_tab_change(event) -> None:
        active_tab["index"] = int(event.new)
        if not cached_responses["responses"]:
            if active_tab["index"] == 0:
                set_area_loading(train_area, "Loading top pulse-ranked units in the train locked view...")
            else:
                set_area_loading(pulse_area, "Loading pulse locked plots for the selected units...")
            redraw()
        else:
            if active_tab["index"] == 0:
                set_area_loading(train_area, "Loading train locked plots for the selected units...")
            else:
                set_area_loading(pulse_area, "Loading pulse locked plots for the selected units...")
            schedule_render_active_tab()

    refresh_button.on_click(redraw)
    unit_selector.param.watch(sync_entry_to_picker, "value")
    unit_entry.param.watch(redraw_from_entry, "value")

    controls = pn.Row(unit_entry, unit_selector, refresh_button, sizing_mode="stretch_width")
    tabs = pn.Tabs(
        ("Train locked", pn.Column(summary, selection_status, train_area, sizing_mode="stretch_width")),
        ("Pulse locked", pn.Column(pulse_area, sizing_mode="stretch_width")),
        sizing_mode="stretch_width",
    )
    tabs.param.watch(on_tab_change, "active")
    selection_status.object = _format_unit_selection_status(default_labels, [])
    summary.object = (
        f"**Top pulse-ranked opto units selected:** `{', '.join(default_labels)}`  \n"
        "Plots will render automatically after the page loads."
    )
    set_area_loading(train_area, "Loading top pulse-ranked units in the train locked view...")
    pulse_area.objects = [pn.pane.Markdown("Pulse locked plots render when this tab is opened.")]
    pn.state.onload(redraw)
    return pn.Column(
        pn.pane.Markdown(
            "## Stim raster/PSTH\n"
            "- Train locked: raster/PSTH aligned to stimulation train onset at x = 0 ms.\n"
            "- Pulse locked: raster/PSTH aligned to each pulse onset at x = 0 ms; window is -25 to +50 ms.\n"
            "- Each selected unit is plotted in its own panel.",
            sizing_mode="stretch_width",
        ),
        status,
        controls,
        tabs,
        sizing_mode="stretch_width",
    )


def plot_train_response(response: UnitStimResponse, builder: UnitStimResponseBuilder):
    """Render train-locked command, raster, and PSTH for one selected unit."""

    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        3,
        1,
        figsize=(7.2, 4.8),
        sharex=True,
        gridspec_kw={"height_ratios": [0.55, 1.8, 1.0]},
        constrained_layout=True,
    )
    unit_label = _response_unit_label(response)
    _draw_train_waveform_axis(axes[0], builder)
    _draw_train_raster_axis(axes[1], response, builder)
    _draw_psth_axis(
        axes[2],
        response.train_psth,
        builder.train_psth_config,
        ylabel="rate (Hz)",
        title="PSTH: trains as trials",
    )
    axes[2].set_xlabel("ms from train onset")
    axes[2].set_xlim(builder.train_window.start_ms, builder.train_window.end_ms)
    fig.suptitle(f"Unit {unit_label}: train locked", fontsize=10)
    return fig


def plot_pulse_response(response: UnitStimResponse, builder: UnitStimResponseBuilder):
    """Render pulse-locked command, raster, and PSTH for one selected unit."""

    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(
        3,
        1,
        figsize=(7.2, 4.8),
        sharex=True,
        gridspec_kw={"height_ratios": [0.55, 1.8, 1.0]},
        constrained_layout=True,
    )
    unit_label = _response_unit_label(response)
    _draw_pulse_waveform_axis(axes[0], response, builder)
    _draw_pulse_raster_axis(axes[1], response, builder)
    _draw_psth_axis(
        axes[2],
        response.pulse_psth,
        builder.pulse_psth_config,
        ylabel="rate (Hz)",
        title="PSTH: pulses as pseudo-trials",
    )
    axes[2].set_xlabel("ms from pulse onset")
    axes[2].set_xlim(builder.pulse_window.start_ms, builder.pulse_window.end_ms)
    fig.suptitle(f"Unit {unit_label}: pulse locked", fontsize=10)
    return fig


def _pulse_signature(pulse_epochs: Sequence[PulseEpoch]) -> tuple[tuple[float, float], ...]:
    """Return a stable pulse template signature from starts and durations."""

    return tuple(
        (round(pulse.start_ms, 6), round(pulse.end_ms - pulse.start_ms, 6))
        for pulse in pulse_epochs
    )


def _command_intervals_for_plot(
    pulse_structure: PulseStructureReport,
) -> tuple[tuple[float, float, float], ...]:
    """Return raw micro-op intervals, with pulse epochs as a display fallback."""

    if pulse_structure.command_intervals_ms:
        return pulse_structure.command_intervals_ms
    return tuple(
        (pulse.start_ms, pulse.end_ms, 1.0)
        for pulse in pulse_structure.pulse_epochs
    )


def _command_step_trace(
    intervals: Sequence[tuple[float, float, float]],
    start_ms: float,
    end_ms: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return a piecewise-constant command trace over a requested window."""

    if not intervals:
        return np.array([start_ms, end_ms]), np.array([0.0, 0.0])

    x: list[float] = [start_ms]
    y: list[float] = [0.0]
    for interval_start, interval_end, intensity in sorted(intervals, key=lambda row: row[0]):
        if interval_end < start_ms or interval_start > end_ms:
            continue
        clipped_start = max(float(interval_start), start_ms)
        clipped_end = min(float(interval_end), end_ms)
        if x[-1] < clipped_start:
            x.append(clipped_start)
            y.append(0.0)
        x.extend([clipped_start, clipped_end, clipped_end])
        y.extend([float(intensity), float(intensity), 0.0])

    if x[-1] < end_ms:
        x.append(end_ms)
        y.append(0.0)
    return np.asarray(x), np.asarray(y)


def _command_smoothed_proxy(
    intervals: Sequence[tuple[float, float, float]],
    start_ms: float,
    end_ms: float,
    render_config: WaveformRenderConfig = DEFAULT_WAVEFORM_RENDER,
) -> tuple[np.ndarray, np.ndarray]:
    """Sample and smooth the metadata-derived command for readable overlays."""

    dt = render_config.sample_dt_ms
    x = np.arange(start_ms, end_ms + dt, dt, dtype=float)
    y = np.zeros_like(x)
    for interval_start, interval_end, intensity in intervals:
        mask = (x >= float(interval_start)) & (x <= float(interval_end))
        y[mask] = np.maximum(y[mask], float(intensity))

    kernel = np.ones(render_config.smooth_window_samples, dtype=float)
    kernel /= kernel.sum()
    return x, np.convolve(y, kernel, mode="same")


def _max_level_intervals(
    intervals: Sequence[tuple[float, float, float]],
    start_ms: float,
    end_ms: float,
) -> list[tuple[float, float]]:
    """Return intervals that reached the maximum command intensity."""

    if not intervals:
        return []
    max_intensity = max(float(intensity) for _, _, intensity in intervals)
    return [
        (max(float(interval_start), start_ms), min(float(interval_end), end_ms))
        for interval_start, interval_end, intensity in intervals
        if float(intensity) == max_intensity
        and float(interval_end) >= start_ms
        and float(interval_start) <= end_ms
    ]


def _draw_train_waveform_axis(axis, builder: UnitStimResponseBuilder) -> None:
    pulse_epochs = builder.pulse_structure.pulse_epochs
    intervals = _command_intervals_for_plot(builder.pulse_structure)
    start_ms = builder.train_window.start_ms
    end_ms = builder.train_window.end_ms
    step_x, step_y = _command_step_trace(intervals, start_ms, end_ms)
    proxy_x, proxy_y = _command_smoothed_proxy(intervals, start_ms, end_ms)

    for pulse in pulse_epochs:
        axis.axvspan(pulse.start_ms, pulse.end_ms, color="#f59e0b", alpha=0.28, linewidth=0)
        axis.text(
            (pulse.start_ms + pulse.end_ms) / 2,
            0.72,
            f"P{pulse.pulse_index}",
            ha="center",
            va="center",
            fontsize=8,
        )
    for span_start, span_end in _max_level_intervals(intervals, start_ms, end_ms):
        axis.axvspan(span_start, span_end, color="#dc2626", alpha=0.10, linewidth=0)
    axis.fill_between(step_x, 0, step_y, color="#f59e0b", alpha=0.18)
    axis.plot(
        step_x,
        step_y,
        color="#b45309",
        linewidth=1.3,
        drawstyle="steps-post",
        label="command steps",
    )
    axis.plot(
        proxy_x,
        proxy_y,
        color="#0057ff",
        linewidth=2.2,
        alpha=0.92,
        label="smoothed metadata command",
    )
    axis.axvline(0, color="crimson", linestyle="--", linewidth=1.1)
    waveform_peak = max(float(np.max(step_y)) if step_y.size else 0.0, float(np.max(proxy_y)) if proxy_y.size else 0.0)
    axis.set_ylim(-0.02, max(0.55, waveform_peak * 1.15 if waveform_peak > 0 else 0.55))
    axis.set_xlim(start_ms, end_ms)
    axis.set_ylabel("LED")
    axis.set_title("Reconstructed opto command from raw metadata")
    axis.legend(loc="upper right", fontsize=7)


def _draw_train_raster_axis(axis, response: UnitStimResponse, builder: UnitStimResponseBuilder) -> None:
    for trial_index in response.train_trials:
        trial_spikes = response.train_aligned_spikes.loc[
            response.train_aligned_spikes["trial_index"] == trial_index
        ]
        if trial_spikes.empty:
            continue
        axis.vlines(
            trial_spikes["aligned_time_ms"],
            ymin=trial_index - 0.4,
            ymax=trial_index + 0.4,
            color="black",
            linewidth=0.8,
        )
    for pulse in builder.pulse_structure.pulse_epochs:
        axis.axvspan(pulse.start_ms, pulse.end_ms, color="#f59e0b", alpha=0.08, linewidth=0)
    axis.axvline(0, color="crimson", linestyle="--", linewidth=1.1)
    axis.set_xlim(builder.train_window.start_ms, builder.train_window.end_ms)
    axis.set_ylim(
        min(response.train_trials) - 1 if response.train_trials else -1,
        max(response.train_trials) + 1 if response.train_trials else 1,
    )
    axis.set_title(f"Raster: {len(response.train_trials)} train trials")
    axis.set_ylabel("trial")


def _draw_pulse_waveform_axis(axis, response: UnitStimResponse, builder: UnitStimResponseBuilder) -> None:
    first = response.pulse_structure.pulse_epochs[0] if response.pulse_structure.pulse_epochs else None
    pulse_duration = (first.end_ms - first.start_ms) if first is not None else 0.0
    intervals = _command_intervals_for_plot(response.pulse_structure)
    if first is not None:
        abs_start = first.start_ms + builder.pulse_window.start_ms
        abs_end = first.start_ms + builder.pulse_window.end_ms
        step_x, step_y = _command_step_trace(intervals, abs_start, abs_end)
        proxy_x, proxy_y = _command_smoothed_proxy(intervals, abs_start, abs_end)
        step_x = step_x - first.start_ms
        proxy_x = proxy_x - first.start_ms
        max_spans = [
            (span_start - first.start_ms, span_end - first.start_ms)
            for span_start, span_end in _max_level_intervals(intervals, abs_start, abs_end)
        ]
    else:
        step_x = np.array([builder.pulse_window.start_ms, builder.pulse_window.end_ms])
        step_y = np.array([0.0, 0.0])
        proxy_x = step_x
        proxy_y = step_y
        max_spans = []

    axis.axvspan(0, pulse_duration, color="#f59e0b", alpha=0.28, linewidth=0)
    for span_start, span_end in max_spans:
        axis.axvspan(span_start, span_end, color="#dc2626", alpha=0.10, linewidth=0)
    axis.fill_between(step_x, 0, step_y, color="#f59e0b", alpha=0.18)
    axis.plot(
        step_x,
        step_y,
        color="#b45309",
        linewidth=1.3,
        drawstyle="steps-post",
        label="command steps",
    )
    axis.plot(
        proxy_x,
        proxy_y,
        color="#0057ff",
        linewidth=2.2,
        alpha=0.92,
        label="smoothed metadata command",
    )
    axis.axvline(0, color="crimson", linestyle="--", linewidth=1.1)
    waveform_peak = max(float(np.max(step_y)) if step_y.size else 0.0, float(np.max(proxy_y)) if proxy_y.size else 0.0)
    axis.set_ylim(-0.02, max(0.55, waveform_peak * 1.15 if waveform_peak > 0 else 0.55))
    axis.set_ylabel("LED")
    axis.set_xlim(builder.pulse_window.start_ms, builder.pulse_window.end_ms)
    axis.set_title("Single-pulse command window")
    axis.legend(loc="upper right", fontsize=7)


def _draw_pulse_raster_axis(axis, response: UnitStimResponse, builder: UnitStimResponseBuilder) -> None:
    for pulse_trial_index in response.pulse_trials["pulse_trial_index"].astype(int).tolist():
        trial_spikes = response.pulse_aligned_spikes.loc[
            response.pulse_aligned_spikes["pulse_trial_index"] == pulse_trial_index
        ]
        if trial_spikes.empty:
            continue
        axis.vlines(
            trial_spikes["pulse_aligned_time_ms"],
            ymin=pulse_trial_index - 0.4,
            ymax=pulse_trial_index + 0.4,
            color="black",
            linewidth=0.8,
        )
    first = response.pulse_structure.pulse_epochs[0] if response.pulse_structure.pulse_epochs else None
    if first is not None:
        axis.axvspan(0, first.end_ms - first.start_ms, color="#f59e0b", alpha=0.08, linewidth=0)
    axis.axvline(0, color="crimson", linestyle="--", linewidth=1.1)
    axis.set_xlim(builder.pulse_window.start_ms, builder.pulse_window.end_ms)
    axis.set_ylim(-1, len(response.pulse_trials) + 1 if not response.pulse_trials.empty else 1)
    axis.set_title(f"Raster: {len(response.pulse_trials)} pulse pseudo-trials")
    axis.set_ylabel("pseudo-trial")


def _draw_psth_axis(axis, psth: pd.DataFrame, config: PsthConfig, *, ylabel: str, title: str) -> None:
    axis.bar(
        psth["bin_center_ms"],
        psth["rate_hz"],
        width=config.bin_ms,
        color="#dbeafe",
        edgecolor="#93c5fd",
        linewidth=0.5,
        align="center",
        label="raw",
    )
    axis.plot(
        psth["bin_center_ms"],
        psth["smooth_rate_hz"],
        color="#0f766e",
        linewidth=1.5,
        label="smoothed",
    )
    axis.axvline(0, color="crimson", linestyle="--", linewidth=1.1)
    axis.set_title(title)
    axis.set_ylabel(ylabel)
    axis.legend(loc="upper right", fontsize=8)


def _format_resolution_status(resolution: StimSidecarResolution) -> str:
    eligibility = resolution.eligibility
    lines = [
        f"**Status:** {'enabled' if eligibility.enabled else 'disabled'}",
        f"**Reason:** {eligibility.message}",
    ]
    if resolution.inputs.raw_file is not None:
        lines.append(f"**Raw:** `{resolution.inputs.raw_file}`")
    if resolution.pulse_structure is not None:
        lines.append(f"**Pulse structure:** {resolution.pulse_structure.message}")
    if resolution.message:
        lines.append(f"```text\n{resolution.message}\n```")
    return "  \n".join(lines)


def rank_opto_tagged_unit_groups(
    builder: UnitStimResponseBuilder,
    label_to_units: Mapping[str, Sequence[object]],
    *,
    limit: int | None = None,
) -> list[OptoTaggedUnitScore]:
    """Rank unit groups by pulse-locked post-stim response above baseline."""

    scores: list[OptoTaggedUnitScore] = []
    for unit_label, unit_ids in label_to_units.items():
        scores.append(_score_opto_tagged_unit_group(unit_label, tuple(unit_ids), builder))

    ranked = sorted(
        scores,
        key=lambda score: (
            score.score_hz,
            score.post_rate_hz,
            score.post_spikes,
            -score.baseline_rate_hz,
        ),
        reverse=True,
    )
    return ranked[:limit] if limit is not None else ranked


def _score_opto_tagged_unit_group(
    unit_label: str,
    unit_ids: tuple[object, ...],
    builder: UnitStimResponseBuilder,
) -> OptoTaggedUnitScore:
    """Score one unit/group by counting spikes in pulse-locked windows."""

    events = builder._eligible_events()
    pulse_epochs = list(builder.pulse_structure.pulse_epochs)
    if events.empty or not pulse_epochs:
        return OptoTaggedUnitScore(
            unit_label=unit_label,
            unit_ids=unit_ids,
            score_hz=0.0,
            post_rate_hz=0.0,
            baseline_rate_hz=0.0,
            post_spikes=0,
            baseline_spikes=0,
        )

    baseline_intervals: list[tuple[float, float]] = []
    post_intervals: list[tuple[float, float]] = []
    for event in events.itertuples(index=False):
        stim_time_s = float(getattr(event, "event_time_s"))
        for pulse_index, pulse in enumerate(pulse_epochs):
            next_start_ms = (
                pulse_epochs[pulse_index + 1].start_ms
                if pulse_index + 1 < len(pulse_epochs)
                else np.inf
            )
            onset_s = stim_time_s + pulse.start_ms / 1000.0
            baseline_start_s = onset_s + OPTO_BASELINE_START_MS / 1000.0
            baseline_end_s = onset_s + OPTO_BASELINE_END_MS / 1000.0
            if baseline_end_s > baseline_start_s:
                baseline_intervals.append((baseline_start_s, baseline_end_s))

            post_start_ms = OPTO_RESPONSE_START_MS
            post_end_ms = min(pulse.start_ms + OPTO_RESPONSE_END_MS, next_start_ms) - pulse.start_ms
            if post_end_ms > post_start_ms:
                post_intervals.append(
                    (
                        onset_s + post_start_ms / 1000.0,
                        onset_s + post_end_ms / 1000.0,
                    )
                )

    baseline_spikes = 0
    post_spikes = 0
    for unit_id in unit_ids:
        spike_frames = np.asarray(builder.sorting.get_unit_spike_train(unit_id=unit_id), dtype=float)
        if spike_frames.size == 0:
            continue
        spike_times = np.sort(spike_frames / builder.sampling_frequency_hz)
        baseline_spikes += _count_spikes_in_intervals(spike_times, baseline_intervals)
        post_spikes += _count_spikes_in_intervals(spike_times, post_intervals)

    baseline_durations = sum(max(end_s - start_s, 0.0) for start_s, end_s in baseline_intervals)
    baseline_rate = baseline_spikes / baseline_durations if baseline_durations > 0 else 0.0
    post_durations = sum(max(end_s - start_s, 0.0) for start_s, end_s in post_intervals)
    post_rate = post_spikes / post_durations if post_durations > 0 else 0.0
    return OptoTaggedUnitScore(
        unit_label=unit_label,
        unit_ids=unit_ids,
        score_hz=post_rate - baseline_rate,
        post_rate_hz=post_rate,
        baseline_rate_hz=baseline_rate,
        post_spikes=post_spikes,
        baseline_spikes=baseline_spikes,
    )


def _count_spikes_in_intervals(
    sorted_spike_times_s: np.ndarray,
    intervals: Sequence[tuple[float, float]],
) -> int:
    """Count sorted spike times inside half-open time intervals."""

    count = 0
    for start_s, end_s in intervals:
        if end_s <= start_s:
            continue
        start_index = int(np.searchsorted(sorted_spike_times_s, start_s, side="left"))
        end_index = int(np.searchsorted(sorted_spike_times_s, end_s, side="left"))
        count += end_index - start_index
    return count


def _score_opto_tagged_response(
    unit_label: str,
    unit_ids: tuple[object, ...],
    response: UnitStimResponse,
    builder: UnitStimResponseBuilder,
) -> OptoTaggedUnitScore:
    """Score one response as post-pulse rate minus pre-pulse baseline rate."""

    pulse_spikes = response.pulse_aligned_spikes
    n_trials = max(len(response.pulse_trials), 1)
    baseline_duration_ms = OPTO_BASELINE_END_MS - OPTO_BASELINE_START_MS
    post_duration_ms = OPTO_RESPONSE_END_MS - OPTO_RESPONSE_START_MS

    if pulse_spikes.empty:
        baseline_spikes = 0
        post_spikes = 0
    else:
        times = pulse_spikes["pulse_aligned_time_ms"]
        baseline_spikes = int(
            ((times >= OPTO_BASELINE_START_MS) & (times < OPTO_BASELINE_END_MS)).sum()
        )
        post_spikes = int(
            ((times >= OPTO_RESPONSE_START_MS) & (times <= OPTO_RESPONSE_END_MS)).sum()
        )

    baseline_rate = (
        baseline_spikes / (n_trials * (baseline_duration_ms / 1000.0))
        if baseline_duration_ms > 0
        else 0.0
    )
    post_rate = (
        post_spikes / (n_trials * (post_duration_ms / 1000.0)) if post_duration_ms > 0 else 0.0
    )
    return OptoTaggedUnitScore(
        unit_label=unit_label,
        unit_ids=unit_ids,
        score_hz=post_rate - baseline_rate,
        post_rate_hz=post_rate,
        baseline_rate_hz=baseline_rate,
        post_spikes=post_spikes,
        baseline_spikes=baseline_spikes,
    )


def _default_opto_unit_labels(
    builder: UnitStimResponseBuilder,
    label_to_units: Mapping[str, Sequence[object]],
    *,
    limit: int,
) -> list[str]:
    """Return top opto-tagged unit labels, falling back to first units if needed."""

    if not label_to_units:
        return []
    ranked = rank_opto_tagged_unit_groups(builder, label_to_units, limit=None)
    positive = [score.unit_label for score in ranked if score.score_hz > 0.0 and score.post_spikes > 0]
    if positive:
        return positive[:limit]
    return [score.unit_label for score in ranked[:limit]]


def _format_response_summary(response: UnitStimResponse, resolution: StimSidecarResolution) -> str:
    return (
        f"**Selected units:** `{_response_unit_label(response)}`  \n"
        f"**Train trials:** {len(response.train_trials)}  \n"
        f"**Train-aligned spikes:** {len(response.train_aligned_spikes)}  \n"
        f"**Pulse mode:** {response.pulse_structure.status}  \n"
        f"**Pulse pseudo-trials:** {len(response.pulse_trials)}  \n"
        f"**Pulse-aligned spikes:** {len(response.pulse_aligned_spikes)}  \n"
        f"**Stimulated wells:** `{', '.join(resolution.eligibility.stimulated_wells)}`"
    )


def _format_multi_unit_summary(
    responses: Sequence[UnitStimResponse],
    resolution: StimSidecarResolution,
) -> str:
    if not responses:
        return "No units selected."

    rows = [
        "| Unit | train spikes | pulse spikes | pulse pseudo-trials |",
        "|---|---:|---:|---:|",
    ]
    for response in responses:
        unit_label = _response_unit_label(response)
        rows.append(
            f"| `{unit_label}` | {len(response.train_aligned_spikes)} | "
            f"{len(response.pulse_aligned_spikes)} | {len(response.pulse_trials)} |"
        )
    first = responses[0]
    header = (
        f"**Units selected:** {len(responses)}  \n"
        f"**Train trials:** {len(first.train_trials)}  \n"
        f"**Pulse mode:** {first.pulse_structure.status}  \n"
        f"**Stimulated wells:** `{', '.join(resolution.eligibility.stimulated_wells)}`"
    )
    return header + "\n\n" + "\n".join(rows)


def _split_unit_selection_tokens(raw_values: Sequence[object]) -> list[str]:
    """Split picker/text unit selections into display labels."""

    tokens: list[str] = []
    for value in raw_values:
        for token in re.split(r"[\s,;]+|(?<=\d)\.(?=\d)", str(value).strip()):
            clean = token.strip()
            if clean:
                tokens.append(clean)
    return tokens


def _resolve_unit_selection_labels(
    raw_values: Sequence[object],
    label_to_unit: Mapping[str, object],
    default_label: str,
) -> tuple[list[str], list[str]]:
    """Resolve raw unit entries to valid labels and missing labels."""

    tokens = _split_unit_selection_tokens(raw_values)
    if not tokens:
        tokens = [default_label]

    labels: list[str] = []
    missing: list[str] = []
    for token in tokens:
        if token not in label_to_unit:
            missing.append(token)
            continue
        if token not in labels:
            labels.append(token)
    return labels, missing


def _format_unit_selection_status(labels: Sequence[str], missing: Sequence[str]) -> str:
    """Return a compact status line for unit selection parsing."""

    parts = [f"**Units plotted:** `{', '.join(labels) if labels else 'none'}`"]
    if missing:
        parts.append(f"**Ignored unknown units:** `{', '.join(missing)}`")
    return "  \n".join(parts)


def _response_unit_label(response: UnitStimResponse) -> str:
    return "+".join(_unit_label(unit_id) for unit_id in response.selected_unit_ids)


def _current_curation_state(curation_state_provider) -> Mapping[str, object] | None:
    if curation_state_provider is None:
        return None
    try:
        state = curation_state_provider()
    except Exception:  # noqa: BLE001 - stale GUI state should not break stim rendering
        return None
    return state if isinstance(state, Mapping) else None


def _label_to_unit_groups(
    unit_ids: Sequence[object],
    curation_state: Mapping[str, object] | None,
) -> dict[str, tuple[object, ...]]:
    """Return selectable unit/group labels after current curation edits."""

    unit_by_label = {_unit_label(unit_id): unit_id for unit_id in unit_ids}
    if not curation_state:
        return {label: (unit_id,) for label, unit_id in unit_by_label.items()}

    removed_labels = {
        _unit_label(unit_id)
        for unit_id in curation_state.get("removed", [])  # type: ignore[union-attr]
    }
    merged_member_labels: set[str] = set()
    merge_groups: dict[str, tuple[object, ...]] = {}
    for merge in curation_state.get("merges", []):  # type: ignore[union-attr]
        if not isinstance(merge, Mapping):
            continue
        labels = [
            _unit_label(unit_id)
            for unit_id in merge.get("unit_ids", [])
            if _unit_label(unit_id) in unit_by_label and _unit_label(unit_id) not in removed_labels
        ]
        if len(labels) < 2:
            continue
        merged_member_labels.update(labels)
        merge_label = "merge:" + "+".join(labels)
        merge_groups[merge_label] = tuple(unit_by_label[label] for label in labels)

    groups = dict(merge_groups)
    for label, unit_id in unit_by_label.items():
        if label in removed_labels or label in merged_member_labels:
            continue
        groups[label] = (unit_id,)
    return groups


def _unit_label(unit_id: object) -> str:
    return str(unit_id)


def _unit_ids_from_sorting(sorting) -> list[object]:
    unit_ids = list(getattr(sorting, "unit_ids", []))
    if not unit_ids and hasattr(sorting, "get_unit_ids"):
        unit_ids = list(sorting.get_unit_ids())
    return unit_ids


def _raw_base_stem(path: Path) -> str:
    stem = path.stem
    for suffix in ("_BroadbandProcessor", "_Filter(1Hz-200Hz)", "_Filter(200Hz-3kHz)"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _raw_variant_penalty(path: Path) -> int:
    name = path.name
    if "_Filter(" in name:
        return 20
    if "_BroadbandProcessor" in name:
        return 10
    return 0


def _normalized_match_text(value: object) -> str:
    text = str(value).lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def _looks_like_lumos_recording(recording_name: str, raw_file: Path | None) -> bool:
    text = f"{recording_name} {raw_file or ''}".lower()
    if "lumos" in text or "fortyeightwell" in text:
        return True
    if "129-8445" in text or "129-8447" in text:
        return True
    return False


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
