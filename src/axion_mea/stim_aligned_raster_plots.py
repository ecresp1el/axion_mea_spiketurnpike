#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


@dataclass(frozen=True)
class RasterWindow:
    start_ms: float
    end_ms: float

    @property
    def start_s(self) -> float:
        return self.start_ms / 1000.0

    @property
    def end_s(self) -> float:
        return self.end_ms / 1000.0


class StimAlignedSpikeDataset:
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
        aligned_rows: list[dict[str, object]] = []
        stimulated_wells = self._stimulated_wells()

        for _, stim in self.stim_events.iterrows():
            stim_time_s = float(stim["event_time_s"])
            trial_index = int(stim["sequence_number"])
            window_start_s = stim_time_s + self.window.start_s
            window_end_s = stim_time_s + self.window.end_s

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
        if self.aligned_spikes.empty:
            return self._stimulated_wells()
        return sorted(self.aligned_spikes["well"].unique())

    def _stimulated_wells(self) -> list[str]:
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
    def __init__(self, dataset: StimAlignedSpikeDataset) -> None:
        self.dataset = dataset
        sns.set_theme(style="whitegrid")

    def plot_well_trial_rasters(self) -> Path | None:
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


class StimAlignedRasterApp:
    def __init__(
        self,
        spike_csv: Path,
        stim_csv: Path,
        output_dir: Path,
        pre_ms: float,
        post_ms: float,
        top_n_channels: int,
    ) -> None:
        self.window = RasterWindow(start_ms=-abs(pre_ms), end_ms=abs(post_ms))
        self.dataset = StimAlignedSpikeDataset(
            spike_csv=spike_csv,
            stim_csv=stim_csv,
            output_dir=output_dir,
            window=self.window,
        )
        self.top_n_channels = top_n_channels

    def run(self) -> None:
        self.dataset.load()
        aligned = self.dataset.build_aligned_table()
        self.dataset.save_tables()

        plotter = RasterPlotWriter(self.dataset)
        well_plot = plotter.plot_well_trial_rasters()
        channel_plots = plotter.plot_channel_trial_rasters(self.top_n_channels)

        print(f"Aligned spikes: {len(aligned)}")
        print(f"Stim-aligned output directory: {self.dataset.output_dir}")
        if well_plot is not None:
            print(f"Well raster: {well_plot}")
        for path in channel_plots:
            print(f"Channel raster: {path}")
        if not aligned.empty:
            print(f"Wells: {', '.join(self.dataset.wells())}")
            print(
                f"Time window: {self.window.start_ms:.0f} ms to {self.window.end_ms:.0f} ms"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create stim-aligned raster plots from Axion spike CSV and extracted stim times."
    )
    parser.add_argument(
        "--spike-csv",
        type=Path,
        default=Path("outputs/ventral_sosrs_opsin_day3/spike_list_clean.csv"),
        help="Path to the cleaned spike list CSV.",
    )
    parser.add_argument(
        "--stim-csv",
        type=Path,
        default=Path("outputs/stim_times/ventral_sosrs_opsin_day3(000)_stim_events.csv"),
        help="Path to the extracted stimulation event CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/stim_aligned_rasters/ventral_sosrs_opsin_day3"),
        help="Directory for aligned tables and raster plots.",
    )
    parser.add_argument(
        "--pre-ms",
        type=float,
        default=500.0,
        help="Milliseconds before stim.",
    )
    parser.add_argument(
        "--post-ms",
        type=float,
        default=500.0,
        help="Milliseconds after stim.",
    )
    parser.add_argument(
        "--top-n-channels",
        type=int,
        default=4,
        help="Top channels per well for channel-level rasters.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = StimAlignedRasterApp(
        spike_csv=args.spike_csv,
        stim_csv=args.stim_csv,
        output_dir=args.output_dir,
        pre_ms=args.pre_ms,
        post_ms=args.post_ms,
        top_n_channels=args.top_n_channels,
    )
    app.run()


if __name__ == "__main__":
    main()
