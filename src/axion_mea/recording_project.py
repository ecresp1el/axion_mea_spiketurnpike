from __future__ import annotations
"""Project-level orchestration for the full Axion MEA recording workflow.

This module is the repository's source of truth for how one recording is turned
into one reproducible analysis project. The pipeline is intentionally staged:

1. discover source files,
2. build recording-level normalized CSV products,
3. extract stimulation events from the `.raw` file,
4. align spikes to each stimulation event,
5. split wells into `opsin` and `no_opsin` groups,
6. build per-well train-level and pulse-level response summaries, and
7. snapshot the exact code and command used to generate the project.
"""

import json
import re
import shutil
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import pandas as pd
import seaborn as sns

from .recording_overview import (
    pick_active_wells,
    plot_environment,
    plot_top_channels_by_well,
    plot_well_spikes,
    read_environment,
    read_spike_counts,
    read_spike_list,
    sanitize_name,
    save_summary,
)
from .series_response_comparison import CrossRecordingOpsinComparator, SeriesRecordingProject
from .io import AxionStimFile
from .well_response_analysis import (
    AnalysisWindow,
    OpsinStimDataset,
    OpsinWellFigure,
    OptoWaveformModel,
    PsthBuilder,
    PsthConfig,
    PulseAlignedSpikeBuilder,
    PulseAlignedWellFigure,
    PulseEpoch,
    PulseLatencyAnalyzer,
    PulseTrialSummaryFigure,
    PulseWindow,
    ReportPanelComposer,
    TrialLatencyAnalyzer,
    WaveformRenderConfig,
)
from .stim_locked_spike_rasters import RasterPlotWriter, RasterWindow, StimAlignedSpikeDataset
from .stim_event_extractor import StimEventExtractor


@dataclass(frozen=True)
class ProjectBuildConfig:
    """Configuration shared across the recording or recording-series build."""

    data_dir: Path
    project_root: Path = Path("projects")
    project_name: str | None = None
    pre_ms: float = 100.0
    post_ms: float = 1000.0
    pulse_pre_ms: float = 10.0
    pulse_post_ms: float = 40.0
    train_bin_ms: float = 20.0
    boxcar_kernel: tuple[float, ...] = (1.0, 1.0, 1.0)
    top_channels_per_well: int = 4
    max_wells: int = 8


@dataclass(frozen=True)
class RecordingSourceBundle:
    """Resolved set of source files required to process one recording."""

    data_dir: Path
    recording_stem: str
    spike_list_csv: Path
    spike_counts_csv: Path
    environmental_csv: Path | None
    raw_file: Path
    spk_file: Path | None

    STEM_RE = re.compile(r"^(?P<recording_name>.+?)\((?P<recording_index>\d+)\)$")

    @property
    def recording_name(self) -> str:
        """Base recording name without the trailing Axion index suffix."""
        match = self.STEM_RE.fullmatch(self.recording_stem)
        return match.group("recording_name") if match else self.recording_stem

    @property
    def recording_index(self) -> str | None:
        """Optional zero-padded Axion recording index."""
        match = self.STEM_RE.fullmatch(self.recording_stem)
        return match.group("recording_index") if match else None

    @property
    def plate_id(self) -> str:
        """Parent folder label, which acts as the plate identifier here."""
        return self.data_dir.name

    @property
    def project_slug(self) -> str:
        """Stable filesystem-safe project slug for this recording instance."""
        if self.recording_index is None:
            return sanitize_name(self.recording_stem)
        return sanitize_name(f"{self.recording_name}_{self.recording_index}")

    @property
    def source_summary(self) -> dict[str, str | None]:
        """Machine-readable file summary used in manifests and series reports."""
        return {
            "data_dir": str(self.data_dir),
            "recording_stem": self.recording_stem,
            "recording_name": self.recording_name,
            "recording_index": self.recording_index,
            "plate_id": self.plate_id,
            "spike_list_csv": str(self.spike_list_csv),
            "spike_counts_csv": str(self.spike_counts_csv),
            "environmental_csv": str(self.environmental_csv) if self.environmental_csv else None,
            "raw_file": str(self.raw_file),
            "spk_file": str(self.spk_file) if self.spk_file else None,
        }

    @classmethod
    def discover(cls, data_dir: Path) -> "RecordingSourceBundle":
        """Locate the expected Axion exports when exactly one recording exists."""
        bundles = cls.discover_all(data_dir)
        if not bundles:
            raise FileNotFoundError(f"No Axion recording exports found under: {data_dir}")
        if len(bundles) > 1:
            raise ValueError(
                f"Expected one recording under {data_dir}, but found {len(bundles)}. "
                "Use the batch builder or point to one specific recording folder."
            )
        return bundles[0]

    @classmethod
    def discover_all(cls, data_dir: Path) -> list["RecordingSourceBundle"]:
        """Locate every recording instance inside a folder tree.

        This supports both of the Axion layouts observed in this project:
        1. one folder containing one recording's files, and
        2. one plate folder containing many indexed recordings like `(000)`,
           `(001)`, and so on.
        """
        resolved = data_dir.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Data directory does not exist: {resolved}")

        spike_list_paths = sorted(
            path
            for path in resolved.rglob("*_spike_list.csv")
            if not path.name.startswith("._")
        )
        bundles: list[RecordingSourceBundle] = []
        for spike_list_csv in spike_list_paths:
            recording_dir = spike_list_csv.parent.resolve()
            recording_stem = spike_list_csv.name[: -len("_spike_list.csv")]
            bundle = cls._discover_from_stem(recording_dir, recording_stem)
            if bundle is not None:
                bundles.append(bundle)

        if not bundles:
            raise FileNotFoundError(
                "Expected at least one Axion export set containing "
                "`*_spike_list.csv`, `*_spike_counts.csv`, and `<stem>.raw`."
            )
        return sorted(bundles, key=lambda bundle: (bundle.plate_id, bundle.recording_name, bundle.recording_index or ""))

    @classmethod
    def _discover_from_stem(cls, data_dir: Path, recording_stem: str) -> "RecordingSourceBundle" | None:
        """Build one bundle from the exact Axion recording stem."""
        spike_list_csv = data_dir / f"{recording_stem}_spike_list.csv"
        spike_counts_csv = data_dir / f"{recording_stem}_spike_counts.csv"
        environmental_csv = data_dir / f"{recording_stem}_environmental_data.csv"
        raw_file = data_dir / f"{recording_stem}.raw"
        spk_file = data_dir / f"{recording_stem}.spk"

        if not (spike_list_csv.exists() and spike_counts_csv.exists() and raw_file.exists()):
            return None

        return cls(
            data_dir=data_dir,
            recording_stem=recording_stem,
            spike_list_csv=spike_list_csv,
            spike_counts_csv=spike_counts_csv,
            environmental_csv=environmental_csv if environmental_csv.exists() else None,
            raw_file=raw_file,
            spk_file=spk_file if spk_file.exists() else None,
        )


@dataclass(frozen=True)
class RecordingSeriesLayout:
    """Top-level folder layout when one command builds many recordings."""

    root: Path

    @property
    def recordings_dir(self) -> Path:
        """Parent folder containing one subproject per recording instance."""
        return self.root / "recordings"

    @property
    def manifest_path(self) -> Path:
        """Machine-readable batch manifest path."""
        return self.root / "recording_series_manifest.json"

    @property
    def summary_path(self) -> Path:
        """Human-readable batch summary path."""
        return self.root / "RECORDING_SERIES_SUMMARY.md"

    @property
    def repro_dir(self) -> Path:
        """Batch-level reproducibility metadata directory."""
        return self.root / "repro"

    @property
    def repro_code_dir(self) -> Path:
        """Batch-level code snapshot directory."""
        return self.repro_dir / "code_snapshot"

    def create(self) -> None:
        """Create the series root folders."""
        for path in [self.root, self.recordings_dir, self.repro_dir, self.repro_code_dir]:
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class ProjectLayout:
    """Central definition of the on-disk project folder structure."""

    root: Path

    @property
    def processed_data_dir(self) -> Path:
        """Top-level folder for normalized intermediate outputs."""
        return self.root / "processed_data"

    @property
    def recording_overview_dir(self) -> Path:
        """Outputs produced directly from the CSV exports."""
        return self.processed_data_dir / "recording_overview"

    @property
    def stim_event_dir(self) -> Path:
        """Outputs produced by parsing stimulation metadata from the raw file."""
        return self.processed_data_dir / "stim_event_detection"

    @property
    def stim_locked_spikes_dir(self) -> Path:
        """Outputs produced after aligning spikes to stimulation events."""
        return self.processed_data_dir / "stim_locked_spikes"

    @property
    def groups_dir(self) -> Path:
        """Parent folder for per-group and per-well response summaries."""
        return self.root / "groups"

    @property
    def manifest_path(self) -> Path:
        """Project-wide machine-readable manifest path."""
        return self.root / "project_manifest.json"

    @property
    def summary_path(self) -> Path:
        """Project-wide human-readable summary path."""
        return self.root / "PROJECT_SUMMARY.md"

    @property
    def repro_dir(self) -> Path:
        """Folder containing reproducibility metadata and code snapshots."""
        return self.root / "repro"

    @property
    def repro_code_dir(self) -> Path:
        """Snapshot destination for the exact source files used in this run."""
        return self.repro_dir / "code_snapshot"

    def create(self) -> None:
        """Create every top-level folder needed by the project layout."""
        for path in [
            self.root,
            self.recording_overview_dir,
            self.stim_event_dir,
            self.stim_locked_spikes_dir,
            self.groups_dir / "opsin",
            self.groups_dir / "no_opsin",
            self.repro_dir,
            self.repro_code_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def group_dir(self, group_name: str) -> Path:
        """Return the folder for one well group."""
        return self.groups_dir / group_name

    def well_dir(self, group_name: str, well: str) -> Path:
        """Return the folder for one well inside one group."""
        return self.group_dir(group_name) / well


@dataclass(frozen=True)
class ExplorerArtifacts:
    """Key recording-overview outputs reused by downstream stages."""

    recording_name: str
    spike_list_clean_csv: Path
    well_metadata_csv: Path


@dataclass(frozen=True)
class StimEventArtifacts:
    """Key stimulation-event outputs reused by downstream stages."""

    stim_events_csv: Path


@dataclass(frozen=True)
class WellProjectGroup:
    """Well grouping result used to separate opsin and non-opsin wells."""

    name: str
    title_label: str
    wells: list[str]


@dataclass(frozen=True)
class WellResponseLayout:
    """Folder layout for all response products written for one well."""

    root: Path

    @property
    def overview_dir(self) -> Path:
        """Combined figure panel for fast well-level review."""
        return self.root / "report"

    @property
    def train_dir(self) -> Path:
        """Outputs where one 5-pulse train is treated as one trial."""
        return self.root / "train_response"

    @property
    def pulse_position_dir(self) -> Path:
        """Outputs where pulses are separated by within-train position."""
        return self.root / "pulse_response_by_position"

    @property
    def pulse_trial_dir(self) -> Path:
        """Outputs where every pulse instance becomes one pseudo-trial."""
        return self.root / "pulse_response_all_pulses"

    @property
    def shared_tables_dir(self) -> Path:
        """Shared well-level tables used by multiple response views."""
        return self.root / "tables"

    @property
    def manifest_path(self) -> Path:
        """Machine-readable summary of one well's response outputs."""
        return self.root / "well_response_summary.json"

    def create(self) -> None:
        """Create the full per-well folder structure."""
        for path in [
            self.root,
            self.overview_dir,
            self.train_dir,
            self.pulse_position_dir,
            self.pulse_trial_dir,
            self.shared_tables_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class WellResponseAnalysis:
    """All computed response products for one well before files are written."""

    group: WellProjectGroup
    well: str
    layout: WellResponseLayout
    well_spikes: pd.DataFrame
    trials: list[int]
    trial_summary: pd.DataFrame
    pulse_aligned_spikes: pd.DataFrame
    pulse_trials: pd.DataFrame
    pulse_summary: pd.DataFrame
    train_psth: pd.DataFrame
    pulse_trial_psth: pd.DataFrame
    waveform_model: OptoWaveformModel


class WellResponseBuilder:
    """Analyze one well and write the train-level and pulse-level outputs."""

    def __init__(
        self,
        window: AnalysisWindow,
        pulse_window: PulseWindow,
        train_psth_config: PsthConfig,
        pulse_trial_psth_config: PsthConfig,
        opto_on_intervals_ms: list[tuple[float, float, float]],
        pulse_epochs: list[PulseEpoch],
        waveform_render_config: WaveformRenderConfig,
        report_panel_composer: ReportPanelComposer,
    ) -> None:
        self.window = window
        self.pulse_window = pulse_window
        self.train_psth_config = train_psth_config
        self.pulse_trial_psth_config = pulse_trial_psth_config
        self.opto_on_intervals_ms = opto_on_intervals_ms
        self.pulse_epochs = pulse_epochs
        self.waveform_render_config = waveform_render_config
        self.report_panel_composer = report_panel_composer

    def analyze(
        self,
        dataset: OpsinStimDataset,
        group: WellProjectGroup,
        well: str,
        layout: WellResponseLayout,
    ) -> WellResponseAnalysis:
        """Compute all in-memory response tables needed for one well."""
        well_spikes = dataset.spikes_for_well(well)
        trials = dataset.all_trials()
        waveform_model = OptoWaveformModel(
            opto_on_intervals_ms=self.opto_on_intervals_ms,
            pulse_epochs=self.pulse_epochs,
            render_config=self.waveform_render_config,
        )
        trial_summary = TrialLatencyAnalyzer(well_spikes=well_spikes, all_trials=trials).build_trial_summary()
        pulse_aligned_spikes, pulse_trials = PulseAlignedSpikeBuilder(
            well_spikes=well_spikes,
            all_trials=trials,
            pulse_epochs=self.pulse_epochs,
            pulse_window=self.pulse_window,
        ).build()
        pulse_summary = PulseLatencyAnalyzer(
            pulse_aligned_spikes=pulse_aligned_spikes,
            pulse_trials=pulse_trials,
        ).build_pulse_summary()
        train_psth = PsthBuilder(
            well_spikes=well_spikes,
            trials=trials,
            config=self.train_psth_config,
        ).build(self.window)
        pulse_trial_psth = PsthBuilder(
            well_spikes=pulse_aligned_spikes,
            trials=pulse_trials["pulse_trial_index"].astype(int).tolist(),
            config=self.pulse_trial_psth_config,
            time_column="pulse_aligned_time_ms",
        ).build(self.pulse_window)
        return WellResponseAnalysis(
            group=group,
            well=well,
            layout=layout,
            well_spikes=well_spikes,
            trials=trials,
            trial_summary=trial_summary,
            pulse_aligned_spikes=pulse_aligned_spikes,
            pulse_trials=pulse_trials,
            pulse_summary=pulse_summary,
            train_psth=train_psth,
            pulse_trial_psth=pulse_trial_psth,
            waveform_model=waveform_model,
        )

    def write(self, analysis: WellResponseAnalysis) -> None:
        """Persist all per-well figures, tables, and the well manifest."""
        train_fig = OpsinWellFigure(
            well=analysis.well,
            well_spikes=analysis.well_spikes,
            trials=analysis.trials,
            psth=analysis.train_psth,
            trial_summary=analysis.trial_summary,
            pulse_summary=analysis.pulse_summary,
            window=self.window,
            psth_config=self.train_psth_config,
            opto_on_intervals_ms=self.opto_on_intervals_ms,
            pulse_epochs=self.pulse_epochs,
            waveform_model=analysis.waveform_model,
            well_context_label=analysis.group.title_label,
        ).save(analysis.layout.train_dir, output_name="figure__train_response.png")
        pulse_position_fig = PulseAlignedWellFigure(
            well=analysis.well,
            pulse_aligned_spikes=analysis.pulse_aligned_spikes,
            trials=analysis.trials,
            pulse_epochs=self.pulse_epochs,
            pulse_window=self.pulse_window,
            opto_on_intervals_ms=self.opto_on_intervals_ms,
            waveform_model=analysis.waveform_model,
            well_context_label=analysis.group.title_label,
        ).save(analysis.layout.pulse_position_dir, output_name="figure__pulse_response_by_position.png")
        pulse_trial_fig = PulseTrialSummaryFigure(
            well=analysis.well,
            pulse_aligned_spikes=analysis.pulse_aligned_spikes,
            pulse_trials=analysis.pulse_trials,
            pulse_summary=analysis.pulse_summary,
            psth=analysis.pulse_trial_psth,
            pulse_window=self.pulse_window,
            psth_config=self.pulse_trial_psth_config,
            pulse_epochs=self.pulse_epochs,
            waveform_model=analysis.waveform_model,
            well_context_label=analysis.group.title_label,
        ).save(analysis.layout.pulse_trial_dir, output_name="figure__pulse_response_all_pulses.png")
        self.report_panel_composer.compose_report_panel(
            train_fig,
            pulse_trial_fig,
            pulse_position_fig,
            analysis.layout.overview_dir / "figure__report_panel.png",
        )

        analysis.trial_summary.to_csv(analysis.layout.train_dir / "table__train_response_latency.csv", index=False)
        analysis.pulse_summary[
            [
                "pulse_trial_index",
                "train_trial_index",
                "pulse_index",
                "pulse_label",
                "pulse_start_ms",
                "pulse_end_ms",
                "first_post_pulse_delay_ms",
            ]
        ].to_csv(analysis.layout.pulse_position_dir / "table__pulse_response_by_position.csv", index=False)
        analysis.pulse_summary.to_csv(
            analysis.layout.pulse_trial_dir / "table__pulse_response_all_pulses.csv",
            index=False,
        )
        analysis.train_psth.to_csv(analysis.layout.train_dir / "table__train_response_psth.csv", index=False)
        analysis.pulse_trial_psth.to_csv(
            analysis.layout.pulse_trial_dir / "table__pulse_response_all_pulses_psth.csv",
            index=False,
        )
        analysis.pulse_aligned_spikes.to_csv(
            analysis.layout.shared_tables_dir / "table__pulse_aligned_spikes.csv",
            index=False,
        )
        analysis.pulse_trials.to_csv(analysis.layout.shared_tables_dir / "table__pulse_trials.csv", index=False)
        analysis.layout.manifest_path.write_text(
            json.dumps(
                {
                    "well": analysis.well,
                    "group": analysis.group.name,
                    "group_label": analysis.group.title_label,
                    "analysis_kind": "opto_stimulus_locked_spike_response_screen",
                    "analysis_description": "Spike timing is quantified relative to optogenetic stimulation at the train level and at the individual pulse level.",
                    "analysis_views": {
                        "report_panel": analysis.layout.overview_dir.name,
                        "train_locked_response": analysis.layout.train_dir.name,
                        "pulse_locked_response_by_position": analysis.layout.pulse_position_dir.name,
                        "pulse_locked_response_all_pulses": analysis.layout.pulse_trial_dir.name,
                        "shared_tables": analysis.layout.shared_tables_dir.name,
                    },
                    "aligned_spike_count": int(len(analysis.well_spikes)),
                    "pulse_trial_count": int(len(analysis.pulse_trials)),
                    "pulse_count_per_train": int(len(self.pulse_epochs)),
                    "train_trial_count": int(len(analysis.trials)),
                },
                indent=2,
            ),
            encoding="utf-8",
        )


class RecordingOverviewStage:
    """Stage 1: parse the CSV exports and write recording-level overview products."""

    def __init__(self, bundle: RecordingSourceBundle, layout: ProjectLayout, config: ProjectBuildConfig) -> None:
        self.bundle = bundle
        self.layout = layout
        self.config = config

    def run(self) -> ExplorerArtifacts:
        """Write normalized CSV tables and recording-level overview plots."""
        spikes, recording_metadata, well_metadata = read_spike_list(self.bundle.spike_list_csv)
        well_long, electrode_long = read_spike_counts(self.bundle.spike_counts_csv)
        env = (
            read_environment(self.bundle.environmental_csv)
            if self.bundle.environmental_csv is not None
            else pd.DataFrame()
        )

        recording_name = recording_metadata.get("Recording Name", self.bundle.spike_list_csv.stem)
        output_dir = self.layout.recording_overview_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        spikes.to_csv(output_dir / "spike_list_clean.csv", index=False)
        well_long.to_csv(output_dir / "well_counts_long.csv", index=False)
        electrode_long.to_csv(output_dir / "electrode_counts_long.csv", index=False)
        well_metadata.to_csv(output_dir / "well_metadata.csv", index=False)
        if not env.empty:
            env.to_csv(output_dir / "environment_clean.csv", index=False)

        with (output_dir / "recording_metadata.json").open("w", encoding="utf-8") as handle:
            json.dump(recording_metadata, handle, indent=2)

        active_wells = pick_active_wells(well_long, well_metadata)
        save_summary(
            output_dir,
            recording_metadata,
            well_metadata,
            spikes,
            well_long,
            electrode_long,
        )
        plot_well_spikes(well_long, active_wells, output_dir / "well_spikes_over_time.png")
        plot_top_channels_by_well(
            electrode_long,
            active_wells,
            output_dir / "top_channels_by_well.png",
            max_wells=self.config.max_wells,
            top_channels_per_well=self.config.top_channels_per_well,
        )
        if not env.empty:
            plot_environment(env, output_dir / "environment_over_time.png")

        return ExplorerArtifacts(
            recording_name=recording_name,
            spike_list_clean_csv=output_dir / "spike_list_clean.csv",
            well_metadata_csv=output_dir / "well_metadata.csv",
        )


class StimEventStage:
    """Stage 2: extract stimulation event timing from the raw file."""

    def __init__(self, bundle: RecordingSourceBundle, layout: ProjectLayout) -> None:
        self.bundle = bundle
        self.layout = layout

    def run(self) -> StimEventArtifacts:
        """Write stimulation-event CSV/JSON products and return the CSV path."""
        extraction = StimEventExtractor(self.bundle.raw_file, self.layout.stim_event_dir).extract()
        StimEventExtractor.print_summary(extraction)
        return StimEventArtifacts(
            stim_events_csv=extraction.csv_path,
        )


class StimLockedSpikeStage:
    """Stage 3: align spikes to each stimulation event and write raster QC outputs."""

    def __init__(
        self,
        spike_list_clean_csv: Path,
        stim_events_csv: Path,
        layout: ProjectLayout,
        config: ProjectBuildConfig,
    ) -> None:
        self.dataset = StimAlignedSpikeDataset(
            spike_csv=spike_list_clean_csv,
            stim_csv=stim_events_csv,
            output_dir=layout.stim_locked_spikes_dir,
            window=RasterWindow(start_ms=-abs(config.pre_ms), end_ms=abs(config.post_ms)),
        )
        self.top_channels_per_well = config.top_channels_per_well

    def run(self) -> Path:
        """Write aligned spike tables and raster figures, then return the main table path."""
        self.dataset.load()
        self.dataset.build_aligned_table()
        self.dataset.save_tables()
        writer = RasterPlotWriter(self.dataset)
        writer.plot_well_trial_rasters()
        writer.plot_channel_trial_rasters(self.top_channels_per_well)
        return self.dataset.output_dir / "stim_aligned_spikes.csv"


class WellGroupOrganizer:
    """Assign wells with aligned spikes into `opsin` or `no_opsin` groups."""

    def __init__(self, well_metadata_csv: Path, aligned_spikes_csv: Path) -> None:
        self.well_metadata_csv = well_metadata_csv
        self.aligned_spikes_csv = aligned_spikes_csv

    def build(self) -> list[WellProjectGroup]:
        """Return ordered well groups containing only wells with aligned data."""
        metadata = pd.read_csv(self.well_metadata_csv)
        aligned_spikes = pd.read_csv(self.aligned_spikes_csv)
        wells_with_data = (
            aligned_spikes.groupby("well").size().sort_values(ascending=False).index.tolist()
            if not aligned_spikes.empty
            else []
        )

        treatment_map = {
            str(row["well"]): self._normalize_treatment(row.get("Treatment", ""))
            for _, row in metadata.iterrows()
            if pd.notna(row.get("well"))
        }

        grouped: dict[str, list[str]] = {"opsin": [], "no_opsin": []}
        for well in wells_with_data:
            group_name = "opsin" if self._is_opsin_treatment(treatment_map.get(well, "")) else "no_opsin"
            grouped[group_name].append(well)

        return [
            WellProjectGroup(name="opsin", title_label="opsin well", wells=grouped["opsin"]),
            WellProjectGroup(name="no_opsin", title_label="no opsin well", wells=grouped["no_opsin"]),
        ]

    @staticmethod
    def _normalize_treatment(value: object) -> str:
        """Normalize treatment labels for stable string comparisons."""
        if pd.isna(value):
            return ""
        return str(value).strip().lower().replace("_", " ")

    @classmethod
    def _is_opsin_treatment(cls, value: str) -> bool:
        """Classify a normalized treatment label as opsin-positive or not."""
        normalized = cls._normalize_treatment(value)
        if not normalized:
            return False
        if "no opsin" in normalized:
            return False
        return "opsin" in normalized


class WellResponseStage:
    """Stage 4: build train-level and pulse-level response products for each well."""

    def __init__(
        self,
        spike_list_clean_csv: Path,
        well_metadata_csv: Path,
        stim_events_csv: Path,
        raw_file: Path,
        layout: ProjectLayout,
        config: ProjectBuildConfig,
    ) -> None:
        self.window = AnalysisWindow(pre_ms=config.pre_ms, post_ms=config.post_ms)
        self.pulse_window = PulseWindow(pre_ms=config.pulse_pre_ms, post_ms=config.pulse_post_ms)
        self.train_psth_config = PsthConfig(bin_ms=config.train_bin_ms, boxcar_kernel=config.boxcar_kernel)
        self.pulse_trial_psth_config = PsthConfig(bin_ms=1.0, boxcar_kernel=(1.0,))
        self.dataset = OpsinStimDataset(
            spike_list_csv=spike_list_clean_csv,
            well_metadata_csv=well_metadata_csv,
            stim_events_csv=stim_events_csv,
            window=self.window,
        )
        self.raw_file = raw_file
        self.layout = layout
        self.waveform_render_config = WaveformRenderConfig(sample_dt_ms=1.0, smooth_window_ms=2.0)
        self.report_panel_composer = ReportPanelComposer()
        self.opto_on_intervals_ms: list[tuple[float, float, float]] = []
        self.pulse_epochs: list[PulseEpoch] = []

    def run(self, groups: list[WellProjectGroup]) -> None:
        """Analyze every grouped well and write its well-level response bundle."""
        self.dataset.load()
        self._load_opto_intervals()
        builder = WellResponseBuilder(
            window=self.window,
            pulse_window=self.pulse_window,
            train_psth_config=self.train_psth_config,
            pulse_trial_psth_config=self.pulse_trial_psth_config,
            opto_on_intervals_ms=self.opto_on_intervals_ms,
            pulse_epochs=self.pulse_epochs,
            waveform_render_config=self.waveform_render_config,
            report_panel_composer=self.report_panel_composer,
        )

        for group in groups:
            for well in group.wells:
                bundle = WellResponseLayout(root=self.layout.well_dir(group.name, well))
                bundle.create()
                analysis = builder.analyze(self.dataset, group, well, bundle)
                builder.write(analysis)

    def _load_opto_intervals(self) -> None:
        """Recover optical on-intervals from the raw waveform program."""
        stim_file = AxionStimFile(self.raw_file)
        stim_file.parse()
        self.opto_on_intervals_ms = [
            (interval.start_ms, interval.end_ms, interval.intensity)
            for interval in stim_file.opto_on_intervals_ms()
        ]
        self.pulse_epochs = self._build_pulse_epochs(self.opto_on_intervals_ms)

    @staticmethod
    def _build_pulse_epochs(intervals: list[tuple[float, float, float]]) -> list[PulseEpoch]:
        """Merge adjacent opto intervals into pulse epochs used across figures.

        The raw XML can encode a pulse using multiple micro-operations. This
        helper collapses very small inter-step gaps so downstream pulse-level
        analyses operate on biologically meaningful pulse windows instead of raw
        XML fragments.
        """
        if not intervals:
            return []
        merged: list[list[float]] = []
        merge_gap_ms = 5.0
        for start_ms, end_ms, _ in sorted(intervals, key=lambda row: row[0]):
            if not merged:
                merged.append([start_ms, end_ms])
                continue
            prev_start, prev_end = merged[-1]
            if start_ms - prev_end <= merge_gap_ms:
                merged[-1][1] = max(prev_end, end_ms)
            else:
                merged.append([start_ms, end_ms])
        return [
            PulseEpoch(pulse_index=index + 1, start_ms=start, end_ms=end)
            for index, (start, end) in enumerate(merged)
        ]


class ProjectSummaryWriter:
    """Write the human-readable and machine-readable project summaries."""

    def __init__(
        self,
        layout: ProjectLayout,
        bundle: RecordingSourceBundle,
        explorer: ExplorerArtifacts,
        groups: list[WellProjectGroup],
        config: ProjectBuildConfig,
    ) -> None:
        self.layout = layout
        self.bundle = bundle
        self.explorer = explorer
        self.groups = groups
        self.config = config

    def write_manifest(self) -> None:
        """Write the project-wide JSON manifest."""
        manifest = {
            "project_root": str(self.layout.root),
            "recording_name": self.explorer.recording_name,
            "recording_stem": self.bundle.recording_stem,
            "recording_index": self.bundle.recording_index,
            "plate_id": self.bundle.plate_id,
            "source_files": self.bundle.source_summary,
            "processed_data_dirs": {
                "recording_overview": str(self.layout.recording_overview_dir),
                "stim_event_detection": str(self.layout.stim_event_dir),
                "stim_locked_spikes": str(self.layout.stim_locked_spikes_dir),
            },
            "analysis_config": {
                "pre_ms": self.config.pre_ms,
                "post_ms": self.config.post_ms,
                "pulse_pre_ms": self.config.pulse_pre_ms,
                "pulse_post_ms": self.config.pulse_post_ms,
                "train_bin_ms": self.config.train_bin_ms,
                "boxcar_kernel": list(self.config.boxcar_kernel),
            },
            "groups": [asdict(group) for group in self.groups],
        }
        self.layout.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def write_summary(self) -> None:
        """Write the project-wide Markdown summary."""
        lines = [
            "# Axion Project Summary",
            "",
            f"- Recording: `{self.explorer.recording_name}`",
            f"- Source folder: `{self.bundle.data_dir}`",
            f"- Raw file: `{self.bundle.raw_file.name}`",
            f"- Project root: `{self.layout.root}`",
            "",
            "## Processed Data",
            "",
            f"- Recording overview outputs: `{self.layout.recording_overview_dir}`",
            f"- Stimulation event outputs: `{self.layout.stim_event_dir}`",
            f"- Stimulus-locked spike outputs: `{self.layout.stim_locked_spikes_dir}`",
            "",
            "## Groups",
            "",
            "Per-well analysis:",
            "- `train_response/`: each 5-pulse train treated as one trial, aligned to train onset.",
            "- `pulse_response_by_position/`: pulse 1-5 aligned separately while preserving pulse identity within each train.",
            "- `pulse_response_all_pulses/`: every pulse treated as its own event and stacked in acquisition order.",
            "",
        ]

        for group in self.groups:
            lines.append(f"### {group.name}")
            lines.append("")
            if not group.wells:
                lines.append("- No wells with aligned data.")
            else:
                for well in group.wells:
                    lines.append(f"- `{well}` -> `groups/{group.name}/{well}`")
            lines.append("")

        self.layout.summary_path.write_text("\n".join(lines), encoding="utf-8")


class ReproducibilitySnapshotWriter:
    """Record the exact code and command used to build the project."""

    def __init__(self, layout: ProjectLayout, config: ProjectBuildConfig) -> None:
        self.layout = layout
        self.config = config
        self.repo_root = Path(__file__).resolve().parents[2]

    def write(self) -> None:
        """Copy used source files and emit a shell command for exact rebuilding."""
        used_files = [
            self.repo_root / "run_axion_mea_opto_pipeline.py",
            self.repo_root / "environment.yml",
            self.repo_root / "requirements.txt",
            self.repo_root / "README.md",
            self.repo_root / "src" / "axion_mea" / "__init__.py",
            self.repo_root / "src" / "axion_mea" / "recording_overview.py",
            self.repo_root / "src" / "axion_mea" / "stim_event_extractor.py",
            self.repo_root / "src" / "axion_mea" / "stim_locked_spike_rasters.py",
            self.repo_root / "src" / "axion_mea" / "well_response_analysis.py",
            self.repo_root / "src" / "axion_mea" / "recording_project.py",
            self.repo_root / "src" / "axion_mea" / "series_response_comparison.py",
            self.repo_root / "src" / "axion_mea" / "spike_waveform_overview.py",
            self.repo_root / "src" / "axion_mea" / "raincloud_waveform_linking.py",
            self.repo_root / "src" / "axion_mea" / "io" / "__init__.py",
            self.repo_root / "src" / "axion_mea" / "io" / "raw_stim_parser.py",
        ]

        copied: list[str] = []
        for src in used_files:
            if not src.exists():
                continue
            relative = src.relative_to(self.repo_root)
            dst = self.layout.repro_code_dir / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(str(relative))

        command_text = "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "",
                "cd /Users/ecrespo/Documents/MATLAB/axion_mea_spiketurnpike",
                "source /opt/anaconda3/etc/profile.d/conda.sh",
                "conda activate /Users/ecrespo/Documents/MATLAB/axion_mea_spiketurnpike/.conda",
                "python run_axion_mea_opto_pipeline.py \\",
                f"  --data-dir {self.config.data_dir} \\",
                f"  --project-root {self.config.project_root} \\",
                f"  --pre-ms {self.config.pre_ms} \\",
                f"  --post-ms {self.config.post_ms} \\",
                f"  --pulse-pre-ms {self.config.pulse_pre_ms} \\",
                f"  --pulse-post-ms {self.config.pulse_post_ms} \\",
                f"  --train-bin-ms {self.config.train_bin_ms} \\",
                "  --boxcar-kernel " + " ".join(str(value) for value in self.config.boxcar_kernel) + " \\",
                f"  --top-channels-per-well {self.config.top_channels_per_well} \\",
                f"  --max-wells {self.config.max_wells}",
                "",
            ]
        )
        (self.layout.repro_dir / "rebuild_command.sh").write_text(command_text, encoding="utf-8")
        (self.layout.repro_dir / "used_files.json").write_text(
            json.dumps({"used_files": copied}, indent=2),
            encoding="utf-8",
        )


class AxionProjectBuilder:
    """Top-level object that runs the complete per-recording project build."""

    def __init__(self, config: ProjectBuildConfig) -> None:
        """Resolve source files and initialize the target project layout."""
        self.config = config
        self.bundle = RecordingSourceBundle.discover(config.data_dir)
        self.layout = ProjectLayout(root=self._project_root())

    @classmethod
    def from_bundle(cls, config: ProjectBuildConfig, bundle: RecordingSourceBundle) -> "AxionProjectBuilder":
        """Construct a per-recording builder when the bundle is already known."""
        builder = cls.__new__(cls)
        builder.config = config
        builder.bundle = bundle
        builder.layout = ProjectLayout(root=builder._project_root())
        return builder

    def run(self) -> Path:
        """Execute all stages and return the root path of the generated project."""
        sns.set_theme(style="whitegrid")
        self.layout.create()

        explorer_artifacts = RecordingOverviewStage(self.bundle, self.layout, self.config).run()
        stim_artifacts = StimEventStage(self.bundle, self.layout).run()
        aligned_spikes_csv = StimLockedSpikeStage(
            spike_list_clean_csv=explorer_artifacts.spike_list_clean_csv,
            stim_events_csv=stim_artifacts.stim_events_csv,
            layout=self.layout,
            config=self.config,
        ).run()
        groups = WellGroupOrganizer(
            well_metadata_csv=explorer_artifacts.well_metadata_csv,
            aligned_spikes_csv=aligned_spikes_csv,
        ).build()
        WellResponseStage(
            spike_list_clean_csv=explorer_artifacts.spike_list_clean_csv,
            well_metadata_csv=explorer_artifacts.well_metadata_csv,
            stim_events_csv=stim_artifacts.stim_events_csv,
            raw_file=self.bundle.raw_file,
            layout=self.layout,
            config=self.config,
        ).run(groups)

        summary_writer = ProjectSummaryWriter(
            layout=self.layout,
            bundle=self.bundle,
            explorer=explorer_artifacts,
            groups=groups,
            config=self.config,
        )
        summary_writer.write_manifest()
        summary_writer.write_summary()
        ReproducibilitySnapshotWriter(self.layout, self.config).write()
        return self.layout.root

    def _project_root(self) -> Path:
        """Choose the final project folder name from CLI config or raw filename."""
        if self.config.project_name:
            name = sanitize_name(self.config.project_name)
        else:
            name = self.bundle.project_slug
        return self.config.project_root.expanduser().resolve() / name


@dataclass(frozen=True)
class RecordingSeriesBuildResult:
    """Summary of one batch run across multiple independent recordings."""

    series_root: Path
    recording_projects: list[Path]
    recording_bundles: list[RecordingSourceBundle]


class RecordingSeriesSummaryWriter:
    """Write batch-level manifests describing independently processed recordings."""

    def __init__(
        self,
        layout: RecordingSeriesLayout,
        input_dir: Path,
        project_root: Path,
        config: ProjectBuildConfig,
        bundles: list[RecordingSourceBundle],
        project_paths: list[Path],
    ) -> None:
        self.layout = layout
        self.input_dir = input_dir
        self.project_root = project_root
        self.config = config
        self.bundles = bundles
        self.project_paths = project_paths

    def write(self) -> None:
        """Write machine-readable and human-readable batch summaries."""
        manifest = {
            "input_dir": str(self.input_dir),
            "series_root": str(self.layout.root),
            "recording_count": len(self.bundles),
            "analysis_kind": "independent_recording_repeats",
            "recordings": [
                {
                    **bundle.source_summary,
                    "project_root": str(project_path),
                }
                for bundle, project_path in zip(self.bundles, self.project_paths, strict=True)
            ],
            "analysis_config": {
                "pre_ms": self.config.pre_ms,
                "post_ms": self.config.post_ms,
                "pulse_pre_ms": self.config.pulse_pre_ms,
                "pulse_post_ms": self.config.pulse_post_ms,
                "train_bin_ms": self.config.train_bin_ms,
                "boxcar_kernel": list(self.config.boxcar_kernel),
                "top_channels_per_well": self.config.top_channels_per_well,
                "max_wells": self.config.max_wells,
            },
        }
        self.layout.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        lines = [
            "# Recording Series Summary",
            "",
            f"- Input folder: `{self.input_dir}`",
            f"- Output root: `{self.layout.root}`",
            f"- Independent recordings processed: `{len(self.bundles)}`",
            "",
            "## Interpretation",
            "",
            "- Each indexed Axion recording was processed as an independent project.",
            "- No cross-recording pooling was applied at this stage.",
            "- Each subproject keeps the same per-recording outputs used for a single run.",
            "",
            "## Recording Projects",
            "",
        ]

        for bundle, project_path in zip(self.bundles, self.project_paths, strict=True):
            index_label = bundle.recording_index if bundle.recording_index is not None else "single"
            lines.extend(
                [
                    f"### {bundle.project_slug}",
                    "",
                    f"- Plate: `{bundle.plate_id}`",
                    f"- Recording name: `{bundle.recording_name}`",
                    f"- Recording index: `{index_label}`",
                    f"- Source folder: `{bundle.data_dir}`",
                    f"- Project folder: `{project_path}`",
                    "",
                ]
            )

        self.layout.summary_path.write_text("\n".join(lines), encoding="utf-8")
        self._write_rebuild_script()
        self._write_code_snapshot()

    def _write_rebuild_script(self) -> None:
        """Write one stable command that reproduces the full batch analysis."""
        command_text = "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "",
                "cd /Users/ecrespo/Documents/MATLAB/axion_mea_spiketurnpike",
                "source /opt/anaconda3/etc/profile.d/conda.sh",
                "conda activate /Users/ecrespo/Documents/MATLAB/axion_mea_spiketurnpike/.conda",
                "python run_axion_mea_opto_pipeline.py \\",
                f"  --data-dir {self.input_dir} \\",
                f"  --project-root {self.project_root} \\",
                f"  --pre-ms {self.config.pre_ms} \\",
                f"  --post-ms {self.config.post_ms} \\",
                f"  --pulse-pre-ms {self.config.pulse_pre_ms} \\",
                f"  --pulse-post-ms {self.config.pulse_post_ms} \\",
                f"  --train-bin-ms {self.config.train_bin_ms} \\",
                "  --boxcar-kernel " + " ".join(str(value) for value in self.config.boxcar_kernel) + " \\",
                f"  --top-channels-per-well {self.config.top_channels_per_well} \\",
                f"  --max-wells {self.config.max_wells}",
                "",
            ]
        )
        (self.layout.repro_dir / "rebuild_all_recordings.sh").write_text(command_text, encoding="utf-8")

    def _write_code_snapshot(self) -> None:
        """Copy the active source files used by the batch build."""
        repo_root = Path(__file__).resolve().parents[2]
        used_files = [
            repo_root / "run_axion_mea_opto_pipeline.py",
            repo_root / "environment.yml",
            repo_root / "requirements.txt",
            repo_root / "README.md",
            repo_root / "src" / "axion_mea" / "__init__.py",
            repo_root / "src" / "axion_mea" / "recording_overview.py",
            repo_root / "src" / "axion_mea" / "stim_event_extractor.py",
            repo_root / "src" / "axion_mea" / "stim_locked_spike_rasters.py",
            repo_root / "src" / "axion_mea" / "well_response_analysis.py",
            repo_root / "src" / "axion_mea" / "recording_project.py",
            repo_root / "src" / "axion_mea" / "series_response_comparison.py",
            repo_root / "src" / "axion_mea" / "spike_waveform_overview.py",
            repo_root / "src" / "axion_mea" / "raincloud_waveform_linking.py",
            repo_root / "src" / "axion_mea" / "io" / "__init__.py",
            repo_root / "src" / "axion_mea" / "io" / "raw_stim_parser.py",
        ]
        copied: list[str] = []
        for src in used_files:
            if not src.exists():
                continue
            relative = src.relative_to(repo_root)
            dst = self.layout.repro_code_dir / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(str(relative))
        (self.layout.repro_dir / "used_files.json").write_text(
            json.dumps({"used_files": copied}, indent=2),
            encoding="utf-8",
        )


class AxionProjectSeriesBuilder:
    """Discover and build one project per recording instance in an input tree."""

    def __init__(self, config: ProjectBuildConfig) -> None:
        self.config = config
        self.input_dir = config.data_dir.expanduser().resolve()
        self.bundles = RecordingSourceBundle.discover_all(self.input_dir)
        self.layout = RecordingSeriesLayout(root=self._series_root())

    def run(self) -> RecordingSeriesBuildResult:
        """Build every discovered recording as an independent subproject."""
        self.layout.create()
        project_paths: list[Path] = []
        for bundle in self.bundles:
            recording_config = replace(
                self.config,
                data_dir=bundle.data_dir,
                project_root=self.layout.recordings_dir,
                project_name=bundle.project_slug,
            )
            project_path = AxionProjectBuilder.from_bundle(recording_config, bundle).run()
            project_paths.append(project_path)

        CrossRecordingOpsinComparator(
            series_root=self.layout.root,
            recording_projects=[
                SeriesRecordingProject(
                    recording_label=bundle.project_slug,
                    recording_index=bundle.recording_index or bundle.project_slug,
                    project_root=project_path,
                )
                for bundle, project_path in zip(self.bundles, project_paths, strict=True)
            ],
            top_n_per_group=2,
        ).run()

        RecordingSeriesSummaryWriter(
            layout=self.layout,
            input_dir=self.input_dir,
            project_root=self.config.project_root.expanduser().resolve(),
            config=self.config,
            bundles=self.bundles,
            project_paths=project_paths,
        ).write()
        return RecordingSeriesBuildResult(
            series_root=self.layout.root,
            recording_projects=project_paths,
            recording_bundles=self.bundles,
        )

    def _series_root(self) -> Path:
        """Choose a clear folder name for a set of repeated recordings."""
        if self.config.project_name:
            name = sanitize_name(self.config.project_name)
        elif len(self.bundles) == 1:
            name = self.bundles[0].project_slug
        else:
            plate_labels = sorted({bundle.plate_id for bundle in self.bundles})
            recording_names = sorted({bundle.recording_name for bundle in self.bundles})
            plate_label = "__".join(plate_labels)
            recording_label = "__".join(recording_names)
            name = sanitize_name(f"recording_series_{plate_label}_{recording_label}")
        return self.config.project_root.expanduser().resolve() / name
