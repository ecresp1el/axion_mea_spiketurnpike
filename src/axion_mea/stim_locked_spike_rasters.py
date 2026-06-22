from __future__ import annotations
"""Stimulation-locked raster tables and overview figures.

This module takes the cleaned spike list plus extracted stimulation events and
re-expresses spikes in a stimulation-relative coordinate system. The resulting
tables support two downstream uses:

1. quick QC of stimulus-locked responses across wells and channels, and
2. a shared aligned-spike table consumed by the well-level response analysis.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


@dataclass(frozen=True)
class RasterWindow:
    """Symmetric plotting window stored in milliseconds and seconds."""

    start_ms: float
    end_ms: float

    @property
    def start_s(self) -> float:
        """Return the window start in seconds for timestamp arithmetic."""
        return self.start_ms / 1000.0

    @property
    def end_s(self) -> float:
        """Return the window end in seconds for timestamp arithmetic."""
        return self.end_ms / 1000.0


class StimAlignedSpikeDataset:
    """Load spikes and stimulation events, then build a stim-relative spike table."""

    def __init__(
        self,
        spike_csv: Path,
        stim_csv: Path,
        output_dir: Path,
        window: RasterWindow,
    ) -> None:
        self.spike_csv = spike_csv.expanduser().resolve()
        self.stim_csv = stim_csv.expanduser().resolve()
        self.output_dir = output_dir.expanduser().resolve()
        self.window = window

        self.spikes = pd.DataFrame()
        self.stim_events = pd.DataFrame()
        self.aligned_spikes = pd.DataFrame()

    def load(self) -> None:
        """Load input CSVs and coerce the timing columns to numeric values."""
        self.spikes = pd.read_csv(self.spike_csv)
        self.stim_events = pd.read_csv(self.stim_csv)
        self.spikes["time_s"] = pd.to_numeric(self.spikes["time_s"], errors="coerce")
        self.stim_events["event_time_s"] = pd.to_numeric(
            self.stim_events["event_time_s"], errors="coerce"
        )
        self.spikes = self.spikes.dropna(subset=["time_s"]).copy()
        self.stim_events = self.stim_events.dropna(subset=["event_time_s"]).copy()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_aligned_table(self) -> pd.DataFrame:
        """Create one row per spike that falls inside the stimulus-aligned window."""
        aligned_rows: list[dict[str, object]] = []
        stimulated_wells = self._stimulated_wells()

        for _, stim in self.stim_events.iterrows():
            stim_time_s = float(stim["event_time_s"])
            trial_index = int(stim["sequence_number"])
            window_start_s = stim_time_s + self.window.start_s
            window_end_s = stim_time_s + self.window.end_s

            # Restrict spikes to the current stimulus window and to wells that
            # were reported as stimulated by the raw-tag extraction step.
            in_window = self.spikes.loc[
                (self.spikes["time_s"] >= window_start_s)
                & (self.spikes["time_s"] <= window_end_s)
                & (self.spikes["well"].isin(stimulated_wells))
            ].copy()

            if in_window.empty:
                continue

            in_window["aligned_time_ms"] = (in_window["time_s"] - stim_time_s) * 1000.0
            in_window["trial_index"] = trial_index
            in_window["stim_time_s"] = stim_time_s
            in_window["source_kind"] = stim["source_kind"]
            aligned_rows.extend(in_window.to_dict(orient="records"))

        self.aligned_spikes = pd.DataFrame(aligned_rows)
        if not self.aligned_spikes.empty:
            self.aligned_spikes = self.aligned_spikes[
                [
                    "trial_index",
                    "stim_time_s",
                    "source_kind",
                    "well",
                    "electrode",
                    "channel_in_well",
                    "time_s",
                    "aligned_time_ms",
                    "amplitude_mV",
                ]
            ].sort_values(["well", "trial_index", "aligned_time_ms", "electrode"])
        return self.aligned_spikes

    def save_tables(self) -> None:
        """Write the aligned spike table plus simple well/channel count summaries."""
        if self.aligned_spikes.empty:
            return

        self.aligned_spikes.to_csv(self.output_dir / "stim_aligned_spikes.csv", index=False)

        well_counts = (
            self.aligned_spikes.groupby(["well", "trial_index"], as_index=False)
            .size()
            .rename(columns={"size": "spike_count"})
        )
        well_counts.to_csv(self.output_dir / "stim_aligned_well_counts.csv", index=False)

        channel_counts = (
            self.aligned_spikes.groupby(["well", "electrode"], as_index=False)
            .size()
            .rename(columns={"size": "spike_count"})
            .sort_values(["well", "spike_count"], ascending=[True, False])
        )
        channel_counts.to_csv(self.output_dir / "stim_aligned_channel_counts.csv", index=False)

    def top_channels_by_well(self, top_n: int) -> dict[str, list[str]]:
        """Return the top `top_n` electrodes per well by aligned spike count."""
        if self.aligned_spikes.empty:
            return {}

        counts = (
            self.aligned_spikes.groupby(["well", "electrode"], as_index=False)
            .size()
            .rename(columns={"size": "spike_count"})
            .sort_values(["well", "spike_count"], ascending=[True, False])
        )

        top_channels: dict[str, list[str]] = {}
        for well, group in counts.groupby("well"):
            top_channels[well] = group.head(top_n)["electrode"].tolist()
        return top_channels

    def wells(self) -> list[str]:
        """Return stimulated wells, preferring aligned-spike content when available."""
        if self.aligned_spikes.empty:
            return self._stimulated_wells()
        return sorted(self.aligned_spikes["well"].unique())

    def _stimulated_wells(self) -> list[str]:
        """Recover the stimulated well list from the extracted stimulation CSV."""
        stimulated: set[str] = set()
        if "stimulated_wells" not in self.stim_events.columns:
            return sorted(self.spikes["well"].unique())

        for value in self.stim_events["stimulated_wells"].dropna():
            for well in str(value).split(";"):
                well = well.strip()
                if well:
                    stimulated.add(well)
        return sorted(stimulated) if stimulated else sorted(self.spikes["well"].unique())


class RasterPlotWriter:
    """Create recording-level stimulus-locked raster figures."""

    def __init__(self, dataset: StimAlignedSpikeDataset) -> None:
        self.dataset = dataset
        sns.set_theme(style="whitegrid")

    def plot_well_trial_rasters(self) -> Path | None:
        """Render one trial raster panel per well."""
        aligned = self.dataset.aligned_spikes
        wells = self.dataset.wells()
        if aligned.empty or not wells:
            return None

        ncols = 3
        nrows = math.ceil(len(wells) / ncols)
        fig, axes = plt.subplots(
            nrows,
            ncols,
            figsize=(15, 4 * nrows),
            constrained_layout=True,
            squeeze=False,
        )

        for axis, well in zip(axes.ravel(), wells):
            well_df = aligned.loc[aligned["well"] == well]
            self._draw_trial_raster(axis, well_df, title=well)

        for axis in axes.ravel()[len(wells) :]:
            axis.set_visible(False)

        output_path = self.dataset.output_dir / "well_trial_rasters.png"
        fig.savefig(output_path, dpi=180)
        plt.close(fig)
        return output_path

    def plot_channel_trial_rasters(self, top_n_channels: int) -> list[Path]:
        """Render one raster figure per well for its most active electrodes."""
        aligned = self.dataset.aligned_spikes
        if aligned.empty:
            return []

        paths: list[Path] = []
        top_channels = self.dataset.top_channels_by_well(top_n_channels)
        for well in self.dataset.wells():
            electrodes = top_channels.get(well, [])
            if not electrodes:
                continue

            ncols = 2
            nrows = math.ceil(len(electrodes) / ncols)
            fig, axes = plt.subplots(
                nrows,
                ncols,
                figsize=(14, 3.5 * nrows),
                constrained_layout=True,
                squeeze=False,
            )

            for axis, electrode in zip(axes.ravel(), electrodes):
                electrode_df = aligned.loc[
                    (aligned["well"] == well) & (aligned["electrode"] == electrode)
                ]
                self._draw_trial_raster(axis, electrode_df, title=electrode)

            for axis in axes.ravel()[len(electrodes) :]:
                axis.set_visible(False)

            output_path = self.dataset.output_dir / f"{well}_channel_trial_rasters.png"
            fig.savefig(output_path, dpi=180)
            plt.close(fig)
            paths.append(output_path)

        return paths

    def _draw_trial_raster(self, axis: plt.Axes, df: pd.DataFrame, title: str) -> None:
        """Draw one raster axis from a single well or single electrode slice."""
        if df.empty:
            axis.set_title(f"{title} (no spikes)")
            axis.set_xlim(self.dataset.window.start_ms, self.dataset.window.end_ms)
            axis.axvline(0, color="crimson", linestyle="--", linewidth=1)
            axis.set_xlabel("time from stim (ms)")
            axis.set_ylabel("trial")
            return

        for trial_index, trial_df in df.groupby("trial_index"):
            axis.vlines(
                trial_df["aligned_time_ms"],
                ymin=trial_index - 0.4,
                ymax=trial_index + 0.4,
                color="black",
                linewidth=0.7,
            )

        axis.axvline(0, color="crimson", linestyle="--", linewidth=1)
        axis.set_xlim(self.dataset.window.start_ms, self.dataset.window.end_ms)
        axis.set_ylim(-1, df["trial_index"].max() + 1)
        axis.set_title(title)
        axis.set_xlabel("time from stim (ms)")
        axis.set_ylabel("trial")
