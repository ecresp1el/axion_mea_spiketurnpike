from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
import seaborn as sns

from .csv_export_explorer import (
    find_first_file,
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
from .io import AxionStimFile
from .opsin_response_plots import (
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
from .stim_aligned_raster_plots import RasterPlotWriter, RasterWindow, StimAlignedSpikeDataset
from .stim_event_extractor import StimExtractionApp


@dataclass(frozen=True)
class ProjectBuildConfig:
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
    data_dir: Path
    spike_list_csv: Path
    spike_counts_csv: Path
    environmental_csv: Path | None
    raw_file: Path
    spk_file: Path | None

    @classmethod
    def discover(cls, data_dir: Path) -> "RecordingSourceBundle":
        resolved = data_dir.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Data directory does not exist: {resolved}")

        spike_list_csv = find_first_file(resolved, "_spike_list.csv")
        spike_counts_csv = find_first_file(resolved, "_spike_counts.csv")
        environmental_csv = find_first_file(resolved, "_environmental_data.csv")
        raw_file = find_first_file(resolved, ".raw")
        spk_file = find_first_file(resolved, ".spk")

        if spike_list_csv is None or spike_counts_csv is None or raw_file is None:
            raise FileNotFoundError(
                "Expected *_spike_list.csv, *_spike_counts.csv, and at least one .raw file in the data directory."
            )

        return cls(
            data_dir=resolved,
            spike_list_csv=spike_list_csv,
            spike_counts_csv=spike_counts_csv,
            environmental_csv=environmental_csv,
            raw_file=raw_file,
            spk_file=spk_file,
        )


@dataclass(frozen=True)
class ProjectLayout:
    root: Path

    @property
    def derived_dir(self) -> Path:
        return self.root / "derived"

    @property
    def csv_dir(self) -> Path:
        return self.derived_dir / "csv_explorer"

    @property
    def stim_times_dir(self) -> Path:
        return self.derived_dir / "stim_times"

    @property
    def stim_aligned_dir(self) -> Path:
        return self.derived_dir / "stim_aligned"

    @property
    def groups_dir(self) -> Path:
        return self.root / "groups"

    @property
    def manifest_path(self) -> Path:
        return self.root / "project_manifest.json"

    @property
    def summary_path(self) -> Path:
        return self.root / "PROJECT_SUMMARY.md"

    @property
    def repro_dir(self) -> Path:
        return self.root / "repro"

    @property
    def repro_code_dir(self) -> Path:
        return self.repro_dir / "code_snapshot"

    def create(self) -> None:
        for path in [
            self.root,
            self.csv_dir,
            self.stim_times_dir,
            self.stim_aligned_dir,
            self.groups_dir / "opsin",
            self.groups_dir / "no_opsin",
            self.repro_dir,
            self.repro_code_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def group_dir(self, group_name: str) -> Path:
        return self.groups_dir / group_name

    def well_dir(self, group_name: str, well: str) -> Path:
        return self.group_dir(group_name) / well


@dataclass(frozen=True)
class ExplorerArtifacts:
    output_dir: Path
    recording_name: str
    spike_list_clean_csv: Path
    well_metadata_csv: Path
    summary_json: Path


@dataclass(frozen=True)
class StimEventArtifacts:
    stim_events_csv: Path
    stim_events_json: Path


@dataclass(frozen=True)
class WellProjectGroup:
    name: str
    title_label: str
    wells: list[str]


@dataclass(frozen=True)
class WellResponseLayout:
    root: Path

    @property
    def overview_dir(self) -> Path:
        return self.root / "report"

    @property
    def train_dir(self) -> Path:
        return self.root / "train_response"

    @property
    def pulse_position_dir(self) -> Path:
        return self.root / "pulse_response_by_position"

    @property
    def pulse_trial_dir(self) -> Path:
        return self.root / "pulse_response_all_pulses"

    @property
    def shared_tables_dir(self) -> Path:
        return self.root / "tables"

    @property
    def manifest_path(self) -> Path:
        return self.root / "well_response_summary.json"

    def create(self) -> None:
        for path in [
            self.root,
            self.overview_dir,
            self.train_dir,
            self.pulse_position_dir,
            self.pulse_trial_dir,
            self.shared_tables_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)


class CsvExplorerStage:
    def __init__(self, bundle: RecordingSourceBundle, layout: ProjectLayout, config: ProjectBuildConfig) -> None:
        self.bundle = bundle
        self.layout = layout
        self.config = config

    def run(self) -> ExplorerArtifacts:
        spikes, recording_metadata, well_metadata = read_spike_list(self.bundle.spike_list_csv)
        well_long, electrode_long = read_spike_counts(self.bundle.spike_counts_csv)
        env = (
            read_environment(self.bundle.environmental_csv)
            if self.bundle.environmental_csv is not None
            else pd.DataFrame()
        )

        recording_name = recording_metadata.get("Recording Name", self.bundle.spike_list_csv.stem)
        output_dir = self.layout.csv_dir
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
            output_dir=output_dir,
            recording_name=recording_name,
            spike_list_clean_csv=output_dir / "spike_list_clean.csv",
            well_metadata_csv=output_dir / "well_metadata.csv",
            summary_json=output_dir / "summary.json",
        )


class StimEventStage:
    def __init__(self, bundle: RecordingSourceBundle, layout: ProjectLayout) -> None:
        self.bundle = bundle
        self.layout = layout

    def run(self) -> StimEventArtifacts:
        app = StimExtractionApp(self.bundle.raw_file, self.layout.stim_times_dir)
        app.run()
        stem = self.bundle.raw_file.stem
        return StimEventArtifacts(
            stim_events_csv=self.layout.stim_times_dir / f"{stem}_stim_events.csv",
            stim_events_json=self.layout.stim_times_dir / f"{stem}_stim_events.json",
        )


class StimAlignedStage:
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
            output_dir=layout.stim_aligned_dir,
            window=RasterWindow(start_ms=-abs(config.pre_ms), end_ms=abs(config.post_ms)),
        )
        self.top_channels_per_well = config.top_channels_per_well

    def run(self) -> Path:
        self.dataset.load()
        self.dataset.build_aligned_table()
        self.dataset.save_tables()
        writer = RasterPlotWriter(self.dataset)
        writer.plot_well_trial_rasters()
        writer.plot_channel_trial_rasters(self.top_channels_per_well)
        return self.dataset.output_dir / "stim_aligned_spikes.csv"


class WellGroupOrganizer:
    def __init__(self, well_metadata_csv: Path, aligned_spikes_csv: Path) -> None:
        self.well_metadata_csv = well_metadata_csv
        self.aligned_spikes_csv = aligned_spikes_csv

    def build(self) -> list[WellProjectGroup]:
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
        if pd.isna(value):
            return ""
        return str(value).strip().lower().replace("_", " ")

    @classmethod
    def _is_opsin_treatment(cls, value: str) -> bool:
        normalized = cls._normalize_treatment(value)
        if not normalized:
            return False
        if "no opsin" in normalized:
            return False
        return "opsin" in normalized


class PerWellSummaryStage:
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
            output_dir=layout.derived_dir,
            window=self.window,
        )
        self.raw_file = raw_file
        self.layout = layout
        self.waveform_render_config = WaveformRenderConfig(sample_dt_ms=1.0, smooth_window_ms=2.0)
        self.report_panel_composer = ReportPanelComposer()
        self.opto_on_intervals_ms: list[tuple[float, float, float]] = []
        self.pulse_epochs: list[PulseEpoch] = []

    def run(self, groups: list[WellProjectGroup]) -> None:
        self.dataset.load()
        self._load_opto_intervals()

        for group in groups:
            for well in group.wells:
                self._build_well_outputs(group, well)

    def _build_well_outputs(self, group: WellProjectGroup, well: str) -> None:
        bundle = WellResponseLayout(root=self.layout.well_dir(group.name, well))
        bundle.create()

        well_spikes = self.dataset.spikes_for_well(well)
        trials = self.dataset.well_trials(well)
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

        train_fig = OpsinWellFigure(
            well=well,
            well_spikes=well_spikes,
            trials=trials,
            psth=train_psth,
            trial_summary=trial_summary,
            pulse_summary=pulse_summary,
            window=self.window,
            psth_config=self.train_psth_config,
            opto_on_intervals_ms=self.opto_on_intervals_ms,
            pulse_epochs=self.pulse_epochs,
            waveform_model=waveform_model,
            well_context_label=group.title_label,
        ).save(bundle.train_dir, output_name="figure__train_response.png")
        pulse_position_fig = PulseAlignedWellFigure(
            well=well,
            pulse_aligned_spikes=pulse_aligned_spikes,
            trials=trials,
            pulse_epochs=self.pulse_epochs,
            pulse_window=self.pulse_window,
            opto_on_intervals_ms=self.opto_on_intervals_ms,
            waveform_model=waveform_model,
            well_context_label=group.title_label,
        ).save(bundle.pulse_position_dir, output_name="figure__pulse_response_by_position.png")
        pulse_trial_fig = PulseTrialSummaryFigure(
            well=well,
            pulse_aligned_spikes=pulse_aligned_spikes,
            pulse_trials=pulse_trials,
            pulse_summary=pulse_summary,
            psth=pulse_trial_psth,
            pulse_window=self.pulse_window,
            psth_config=self.pulse_trial_psth_config,
            pulse_epochs=self.pulse_epochs,
            waveform_model=waveform_model,
            well_context_label=group.title_label,
        ).save(bundle.pulse_trial_dir, output_name="figure__pulse_response_all_pulses.png")
        self.report_panel_composer.compose_report_panel(
            train_fig,
            pulse_trial_fig,
            pulse_position_fig,
            bundle.overview_dir / "figure__report_panel.png",
        )

        trial_summary.to_csv(bundle.train_dir / "table__train_response_latency.csv", index=False)
        pulse_summary[
            [
                "pulse_trial_index",
                "train_trial_index",
                "pulse_index",
                "pulse_label",
                "pulse_start_ms",
                "pulse_end_ms",
                "first_post_pulse_delay_ms",
            ]
        ].to_csv(bundle.pulse_position_dir / "table__pulse_response_by_position.csv", index=False)
        pulse_summary.to_csv(bundle.pulse_trial_dir / "table__pulse_response_all_pulses.csv", index=False)
        train_psth.to_csv(bundle.train_dir / "table__train_response_psth.csv", index=False)
        pulse_trial_psth.to_csv(bundle.pulse_trial_dir / "table__pulse_response_all_pulses_psth.csv", index=False)
        pulse_aligned_spikes.to_csv(bundle.shared_tables_dir / "table__pulse_aligned_spikes.csv", index=False)
        pulse_trials.to_csv(bundle.shared_tables_dir / "table__pulse_trials.csv", index=False)
        (bundle.manifest_path).write_text(
            json.dumps(
                {
                    "well": well,
                    "group": group.name,
                    "group_label": group.title_label,
                    "analysis_kind": "opto_stimulus_locked_spike_response_screen",
                    "analysis_description": "Spike timing is quantified relative to optogenetic stimulation at the train level and at the individual pulse level.",
                    "analysis_views": {
                        "report_panel": bundle.overview_dir.name,
                        "train_locked_response": bundle.train_dir.name,
                        "pulse_locked_response_by_position": bundle.pulse_position_dir.name,
                        "pulse_locked_response_all_pulses": bundle.pulse_trial_dir.name,
                        "shared_tables": bundle.shared_tables_dir.name,
                    },
                    "aligned_spike_count": int(len(well_spikes)),
                    "pulse_trial_count": int(len(pulse_trials)),
                    "pulse_count_per_train": int(len(self.pulse_epochs)),
                    "train_trial_count": int(len(trials)),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _load_opto_intervals(self) -> None:
        stim_file = AxionStimFile(self.raw_file)
        stim_file.parse()
        self.opto_on_intervals_ms = [
            (interval.start_ms, interval.end_ms, interval.intensity)
            for interval in stim_file.opto_on_intervals_ms()
        ]
        self.pulse_epochs = self._build_pulse_epochs(self.opto_on_intervals_ms)

    @staticmethod
    def _build_pulse_epochs(intervals: list[tuple[float, float, float]]) -> list[PulseEpoch]:
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
        manifest = {
            "project_root": str(self.layout.root),
            "recording_name": self.explorer.recording_name,
            "source_files": {
                "data_dir": str(self.bundle.data_dir),
                "spike_list_csv": str(self.bundle.spike_list_csv),
                "spike_counts_csv": str(self.bundle.spike_counts_csv),
                "environmental_csv": str(self.bundle.environmental_csv) if self.bundle.environmental_csv else None,
                "raw_file": str(self.bundle.raw_file),
                "spk_file": str(self.bundle.spk_file) if self.bundle.spk_file else None,
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
        lines = [
            "# Axion Project Summary",
            "",
            f"- Recording: `{self.explorer.recording_name}`",
            f"- Source folder: `{self.bundle.data_dir}`",
            f"- Raw file: `{self.bundle.raw_file.name}`",
            f"- Project root: `{self.layout.root}`",
            "",
            "## Derived Data",
            "",
            f"- CSV explorer outputs: `{self.layout.csv_dir}`",
            f"- Stim event outputs: `{self.layout.stim_times_dir}`",
            f"- Stim-aligned outputs: `{self.layout.stim_aligned_dir}`",
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
    def __init__(self, layout: ProjectLayout, config: ProjectBuildConfig) -> None:
        self.layout = layout
        self.config = config
        self.repo_root = Path(__file__).resolve().parents[2]

    def write(self) -> None:
        used_files = [
            self.repo_root / "run_axion_mea_opto_pipeline.py",
            self.repo_root / "environment.yml",
            self.repo_root / "requirements.txt",
            self.repo_root / "README.md",
            self.repo_root / "src" / "axion_mea" / "__init__.py",
            self.repo_root / "src" / "axion_mea" / "csv_export_explorer.py",
            self.repo_root / "src" / "axion_mea" / "stim_event_extractor.py",
            self.repo_root / "src" / "axion_mea" / "stim_aligned_raster_plots.py",
            self.repo_root / "src" / "axion_mea" / "opsin_response_plots.py",
            self.repo_root / "src" / "axion_mea" / "project_pipeline.py",
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
    def __init__(self, config: ProjectBuildConfig) -> None:
        self.config = config
        self.bundle = RecordingSourceBundle.discover(config.data_dir)
        self.layout = ProjectLayout(root=self._project_root())

    def run(self) -> Path:
        sns.set_theme(style="whitegrid")
        self.layout.create()

        explorer_artifacts = CsvExplorerStage(self.bundle, self.layout, self.config).run()
        stim_artifacts = StimEventStage(self.bundle, self.layout).run()
        aligned_spikes_csv = StimAlignedStage(
            spike_list_clean_csv=explorer_artifacts.spike_list_clean_csv,
            stim_events_csv=stim_artifacts.stim_events_csv,
            layout=self.layout,
            config=self.config,
        ).run()
        groups = WellGroupOrganizer(
            well_metadata_csv=explorer_artifacts.well_metadata_csv,
            aligned_spikes_csv=aligned_spikes_csv,
        ).build()
        PerWellSummaryStage(
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
        if self.config.project_name:
            name = sanitize_name(self.config.project_name)
        else:
            name = sanitize_name(self.bundle.raw_file.stem)
        return self.config.project_root.expanduser().resolve() / name
