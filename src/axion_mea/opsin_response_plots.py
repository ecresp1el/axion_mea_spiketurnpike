#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from PIL import Image

from .io import AxionStimFile


@dataclass(frozen=True)
class AnalysisWindow:
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
    bin_ms: float
    boxcar_kernel: tuple[float, ...]

    @property
    def normalized_kernel(self) -> np.ndarray:
        kernel = np.asarray(self.boxcar_kernel, dtype=float)
        return kernel / kernel.sum()


@dataclass(frozen=True)
class WaveformRenderConfig:
    sample_dt_ms: float
    smooth_window_ms: float

    @property
    def smooth_window_samples(self) -> int:
        return max(1, int(round(self.smooth_window_ms / self.sample_dt_ms)))


@dataclass(frozen=True)
class PulseEpoch:
    pulse_index: int
    start_ms: float
    end_ms: float


OPTO_BLUE = "#0057ff"


class OpsinStimDataset:
    def __init__(
        self,
        spike_list_csv: Path,
        well_metadata_csv: Path,
        stim_events_csv: Path,
        output_dir: Path,
        window: AnalysisWindow,
    ) -> None:
        self.spike_list_csv = spike_list_csv.expanduser().resolve()
        self.well_metadata_csv = well_metadata_csv.expanduser().resolve()
        self.stim_events_csv = stim_events_csv.expanduser().resolve()
        self.output_dir = output_dir.expanduser().resolve()
        self.window = window

        self.spikes = pd.DataFrame()
        self.aligned_spikes = pd.DataFrame()
        self.well_metadata = pd.DataFrame()
        self.stim_events = pd.DataFrame()

    def load(self) -> None:
        self.spikes = pd.read_csv(self.spike_list_csv)
        self.well_metadata = pd.read_csv(self.well_metadata_csv)
        self.stim_events = pd.read_csv(self.stim_events_csv)

        self.spikes["time_s"] = pd.to_numeric(self.spikes["time_s"], errors="coerce")
        self.stim_events["sequence_number"] = pd.to_numeric(
            self.stim_events["sequence_number"], errors="coerce"
        ).astype("Int64")
        self.stim_events["event_time_s"] = pd.to_numeric(
            self.stim_events["event_time_s"], errors="coerce"
        )

        self.spikes = self.spikes.dropna(subset=["time_s", "well"]).copy()
        self.stim_events = self.stim_events.dropna(subset=["sequence_number", "event_time_s"]).copy()
        self.aligned_spikes = self._build_aligned_spikes()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _build_aligned_spikes(self) -> pd.DataFrame:
        aligned_rows: list[dict[str, object]] = []
        stimulated_wells = self._stimulated_wells()

        for _, stim in self.stim_events.iterrows():
            stim_time_s = float(stim["event_time_s"])
            trial_index = int(stim["sequence_number"])
            window_start_s = stim_time_s + (self.window.start_ms / 1000.0)
            window_end_s = stim_time_s + (self.window.end_ms / 1000.0)

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

        if not aligned_rows:
            return pd.DataFrame(
                columns=[
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
            )

        aligned = pd.DataFrame(aligned_rows)
        aligned["trial_index"] = pd.to_numeric(aligned["trial_index"], errors="coerce").astype("Int64")
        aligned["aligned_time_ms"] = pd.to_numeric(aligned["aligned_time_ms"], errors="coerce")
        return aligned.dropna(subset=["aligned_time_ms", "trial_index", "well"]).sort_values(
            ["well", "trial_index", "aligned_time_ms", "electrode"]
        )

    def _stimulated_wells(self) -> list[str]:
        stimulated: set[str] = set()
        if "stimulated_wells" not in self.stim_events.columns:
            return sorted(self.spikes["well"].dropna().astype(str).unique())

        for value in self.stim_events["stimulated_wells"].dropna():
            for well in str(value).split(";"):
                well = well.strip()
                if well:
                    stimulated.add(well)
        return sorted(stimulated) if stimulated else sorted(self.spikes["well"].dropna().astype(str).unique())

    def opsin_wells(self, top_n: int | None = None) -> list[str]:
        metadata = self.well_metadata.copy()
        metadata["Treatment"] = metadata["Treatment"].fillna("").astype(str).str.strip().str.lower()
        opsin_wells = metadata.loc[metadata["Treatment"] == "opsin", "well"].tolist()
        if not opsin_wells:
            return []

        counts = (
            self.aligned_spikes.loc[self.aligned_spikes["well"].isin(opsin_wells)]
            .groupby("well")
            .size()
            .sort_values(ascending=False)
        )
        ordered = counts.index.tolist()
        if top_n is None:
            return ordered
        return ordered[:top_n]

    def well_trials(self, well: str) -> list[int]:
        all_trials = self.stim_events["sequence_number"].dropna().astype(int).tolist()
        return sorted(all_trials)

    def spikes_for_well(self, well: str) -> pd.DataFrame:
        return self.aligned_spikes.loc[self.aligned_spikes["well"] == well].copy()

    def save_trial_summary(self, well: str, summary: pd.DataFrame) -> Path:
        path = self.output_dir / f"{well}_trial_latency_summary.csv"
        summary.to_csv(path, index=False)
        return path

    def save_pulse_summary(self, well: str, summary: pd.DataFrame) -> Path:
        path = self.output_dir / f"{well}_pulse_latency_summary.csv"
        summary.to_csv(path, index=False)
        return path

    def save_pulse_trial_summary(self, well: str, summary: pd.DataFrame) -> Path:
        path = self.output_dir / f"{well}_pulse_trial_latency_summary.csv"
        summary.to_csv(path, index=False)
        return path


class TrialLatencyAnalyzer:
    def __init__(self, well_spikes: pd.DataFrame, all_trials: list[int]) -> None:
        self.well_spikes = well_spikes.copy()
        self.all_trials = all_trials

    def build_trial_summary(self) -> pd.DataFrame:
        grouped = (
            self.well_spikes.groupby("trial_index")["aligned_time_ms"]
            .agg(
                spike_count="size",
                mean_time_to_spike_ms="mean",
                median_time_to_spike_ms="median",
                first_spike_ms="min",
            )
            .reset_index()
        )

        summary = pd.DataFrame({"trial_index": self.all_trials})
        summary = summary.merge(grouped, on="trial_index", how="left")

        post_stim_first = (
            self.well_spikes.loc[self.well_spikes["aligned_time_ms"] >= 0]
            .groupby("trial_index")["aligned_time_ms"]
            .min()
            .reset_index(name="first_post_stim_spike_ms")
        )
        summary = summary.merge(post_stim_first, on="trial_index", how="left")
        return summary


class PulseLatencyAnalyzer:
    def __init__(self, pulse_aligned_spikes: pd.DataFrame, pulse_trials: pd.DataFrame) -> None:
        self.pulse_aligned_spikes = pulse_aligned_spikes.copy()
        self.pulse_trials = pulse_trials.copy()

    def build_pulse_summary(self) -> pd.DataFrame:
        if self.pulse_trials.empty:
            return pd.DataFrame(
                columns=[
                    "pulse_trial_index",
                    "train_trial_index",
                    "pulse_index",
                    "pulse_label",
                    "pulse_start_ms",
                    "pulse_end_ms",
                    "spike_count",
                    "mean_time_to_spike_ms",
                    "median_time_to_spike_ms",
                    "first_spike_ms",
                    "first_post_pulse_delay_ms",
                ]
            )

        grouped = (
            self.pulse_aligned_spikes.groupby("pulse_trial_index")["pulse_aligned_time_ms"]
            .agg(
                spike_count="size",
                mean_time_to_spike_ms="mean",
                median_time_to_spike_ms="median",
                first_spike_ms="min",
            )
            .reset_index()
        )
        post_stim_first = (
            self.pulse_aligned_spikes.loc[self.pulse_aligned_spikes["pulse_aligned_time_ms"] >= 0]
            .groupby("pulse_trial_index")["pulse_aligned_time_ms"]
            .min()
            .reset_index(name="first_post_pulse_delay_ms")
        )
        summary = self.pulse_trials.merge(grouped, on="pulse_trial_index", how="left")
        summary = summary.merge(post_stim_first, on="pulse_trial_index", how="left")
        return summary.sort_values(["pulse_trial_index"]).reset_index(drop=True)


class OptoWaveformModel:
    def __init__(
        self,
        opto_on_intervals_ms: list[tuple[float, float, float]],
        pulse_epochs: list[PulseEpoch],
        render_config: WaveformRenderConfig,
    ) -> None:
        self.opto_on_intervals_ms = sorted(opto_on_intervals_ms, key=lambda row: row[0])
        self.pulse_epochs = pulse_epochs
        self.render_config = render_config

    def step_trace(self, start_ms: float, end_ms: float) -> tuple[np.ndarray, np.ndarray]:
        if not self.opto_on_intervals_ms:
            return np.array([start_ms, end_ms]), np.array([0.0, 0.0])

        x: list[float] = [start_ms]
        y: list[float] = [0.0]

        for interval_start, interval_end, intensity in self.opto_on_intervals_ms:
            if interval_end < start_ms or interval_start > end_ms:
                continue
            interval_start = max(interval_start, start_ms)
            interval_end = min(interval_end, end_ms)
            if x[-1] < interval_start:
                x.append(interval_start)
                y.append(0.0)
            x.extend([interval_start, interval_end, interval_end])
            y.extend([intensity, intensity, 0.0])

        if x[-1] < end_ms:
            x.append(end_ms)
            y.append(0.0)

        return np.asarray(x), np.asarray(y)

    def sampled_proxy(self, start_ms: float, end_ms: float) -> tuple[np.ndarray, np.ndarray]:
        dt = self.render_config.sample_dt_ms
        x = np.arange(start_ms, end_ms + dt, dt, dtype=float)
        y = np.zeros_like(x)

        for interval_start, interval_end, intensity in self.opto_on_intervals_ms:
            mask = (x >= interval_start) & (x <= interval_end)
            y[mask] = np.maximum(y[mask], intensity)

        kernel = np.ones(self.render_config.smooth_window_samples, dtype=float)
        kernel /= kernel.sum()
        smooth = np.convolve(y, kernel, mode="same")
        return x, smooth

    def max_level_intervals(self, start_ms: float, end_ms: float) -> list[tuple[float, float]]:
        if not self.opto_on_intervals_ms:
            return []
        max_intensity = max(intensity for _, _, intensity in self.opto_on_intervals_ms)
        intervals: list[tuple[float, float]] = []
        for interval_start, interval_end, intensity in self.opto_on_intervals_ms:
            if intensity != max_intensity:
                continue
            if interval_end < start_ms or interval_start > end_ms:
                continue
            intervals.append((max(interval_start, start_ms), min(interval_end, end_ms)))
        return intervals


class PulseAlignedSpikeBuilder:
    def __init__(
        self,
        well_spikes: pd.DataFrame,
        all_trials: list[int],
        pulse_epochs: list[PulseEpoch],
        pulse_window: PulseWindow,
    ) -> None:
        self.well_spikes = well_spikes.copy()
        self.all_trials = all_trials
        self.pulse_epochs = pulse_epochs
        self.pulse_window = pulse_window

    def build(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        pulse_rows: list[dict[str, object]] = []
        spike_rows: list[dict[str, object]] = []
        pulse_trial_index = 1

        for train_trial_index in self.all_trials:
            for pulse_idx, pulse in enumerate(self.pulse_epochs):
                next_start = (
                    self.pulse_epochs[pulse_idx + 1].start_ms
                    if pulse_idx + 1 < len(self.pulse_epochs)
                    else np.inf
                )
                pulse_window_end = min(pulse.start_ms + self.pulse_window.end_ms, next_start)
                pulse_window_start = pulse.start_ms + self.pulse_window.start_ms
                pulse_rows.append(
                    {
                        "pulse_trial_index": pulse_trial_index,
                        "train_trial_index": train_trial_index,
                        "pulse_index": pulse.pulse_index,
                        "pulse_label": f"P{pulse.pulse_index}",
                        "pulse_start_ms": pulse.start_ms,
                        "pulse_end_ms": pulse.end_ms,
                        "pulse_window_start_ms": pulse_window_start,
                        "pulse_window_end_ms": pulse_window_end,
                    }
                )
                trial_spikes = self.well_spikes.loc[
                    self.well_spikes["trial_index"] == train_trial_index
                ].copy()
                in_window = trial_spikes.loc[
                    (trial_spikes["aligned_time_ms"] >= pulse_window_start)
                    & (trial_spikes["aligned_time_ms"] <= pulse_window_end)
                ].copy()
                if not in_window.empty:
                    in_window["pulse_trial_index"] = pulse_trial_index
                    in_window["train_trial_index"] = train_trial_index
                    in_window["pulse_index"] = pulse.pulse_index
                    in_window["pulse_label"] = f"P{pulse.pulse_index}"
                    in_window["pulse_onset_ms"] = pulse.start_ms
                    in_window["pulse_end_ms"] = pulse.end_ms
                    in_window["pulse_aligned_time_ms"] = in_window["aligned_time_ms"] - pulse.start_ms
                    spike_rows.extend(in_window.to_dict(orient="records"))
                pulse_trial_index += 1

        pulse_trials = pd.DataFrame(pulse_rows)
        if not spike_rows:
            return (
                pd.DataFrame(
                    columns=[
                        "pulse_trial_index",
                        "train_trial_index",
                        "pulse_index",
                        "pulse_label",
                        "pulse_onset_ms",
                        "pulse_end_ms",
                        "well",
                        "electrode",
                        "aligned_time_ms",
                        "pulse_aligned_time_ms",
                        "amplitude_mV",
                    ]
                ),
                pulse_trials,
            )

        pulse_aligned_spikes = pd.DataFrame(spike_rows).sort_values(
            ["pulse_trial_index", "pulse_aligned_time_ms", "electrode"]
        )
        return pulse_aligned_spikes, pulse_trials


class PsthBuilder:
    def __init__(
        self,
        well_spikes: pd.DataFrame,
        trials: list[int],
        config: PsthConfig,
        time_column: str = "aligned_time_ms",
    ) -> None:
        self.well_spikes = well_spikes
        self.trials = trials
        self.config = config
        self.time_column = time_column

    def build(self, window: AnalysisWindow | PulseWindow) -> pd.DataFrame:
        edges = np.arange(window.start_ms, window.end_ms + self.config.bin_ms, self.config.bin_ms)
        counts, edges = np.histogram(self.well_spikes[self.time_column], bins=edges)
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


class OpsinWellFigure:
    def __init__(
        self,
        well: str,
        well_spikes: pd.DataFrame,
        trials: list[int],
        psth: pd.DataFrame,
        trial_summary: pd.DataFrame,
        pulse_summary: pd.DataFrame,
        window: AnalysisWindow,
        psth_config: PsthConfig,
        opto_on_intervals_ms: list[tuple[float, float, float]],
        pulse_epochs: list[PulseEpoch],
        waveform_model: OptoWaveformModel,
        well_context_label: str = "opsin well",
    ) -> None:
        self.well = well
        self.well_spikes = well_spikes
        self.trials = trials
        self.psth = psth
        self.trial_summary = trial_summary
        self.pulse_summary = pulse_summary
        self.window = window
        self.psth_config = psth_config
        self.opto_on_intervals_ms = opto_on_intervals_ms
        self.pulse_epochs = pulse_epochs
        self.waveform_model = waveform_model
        self.well_context_label = well_context_label

    def save(self, output_dir: Path, output_name: str | None = None) -> Path:
        fig, axes = plt.subplots(
            4,
            2,
            figsize=(15, 13.5),
            constrained_layout=True,
            gridspec_kw={
                "height_ratios": [0.8, 2.0, 1.3, 1.8],
                "width_ratios": [3.4, 1.2],
            },
        )

        self._draw_waveform(axes[0, 0])
        axes[0, 1].set_visible(False)
        self._draw_raster(axes[1, 0])
        axes[1, 1].set_visible(False)
        self._draw_psth(axes[2, 0])
        axes[2, 1].set_visible(False)
        self._draw_trial_boxplots(axes[3, 0])
        self._draw_delay_boxplot(axes[3, 1])

        fig.suptitle(
            f"{self.well} {self.well_context_label}: train-aligned raster/PSTH with train-vs-pulse latency summaries",
            fontsize=14,
        )
        output_path = output_dir / (
            output_name if output_name is not None else f"{self.well}_opsin_raster_psth_boxplot.png"
        )
        fig.savefig(output_path, dpi=180)
        plt.close(fig)
        return output_path

    def _draw_waveform(self, axis: plt.Axes) -> None:
        waveform_x, waveform_y = self.waveform_model.step_trace(
            self.window.start_ms, self.window.end_ms
        )
        proxy_x, proxy_y = self.waveform_model.sampled_proxy(
            self.window.start_ms, self.window.end_ms
        )
        self._draw_trial_epoch_overlay(axis)
        for start_ms, end_ms in self.waveform_model.max_level_intervals(
            self.window.start_ms, self.window.end_ms
        ):
            axis.axvspan(start_ms, end_ms, color="#dc2626", alpha=0.12, linewidth=0)
        axis.plot(
            waveform_x,
            waveform_y,
            color="#b45309",
            linewidth=1.8,
            drawstyle="steps-post",
            label="command steps",
        )
        axis.plot(
            proxy_x,
            proxy_y,
            color=OPTO_BLUE,
            linewidth=3.2,
            alpha=0.95,
            label="smoothed opto proxy",
        )
        axis.fill_between(waveform_x, 0, waveform_y, color="#f59e0b", alpha=0.22)
        axis.axvline(0, color="crimson", linestyle="--", linewidth=1.2)
        axis.set_xlim(self.window.start_ms, self.window.end_ms)
        waveform_peak = float(np.max(waveform_y)) if waveform_y.size else 0.0
        axis.set_ylim(-0.02, max(0.55, waveform_peak * 1.15 if waveform_peak > 0 else 0.55))
        axis.set_title("Opto LED Waveform Within One Tagged Train Trial")
        axis.set_xlabel("time from stim (ms)")
        axis.set_ylabel("LED level")
        if self._merged_trial_epochs():
            first_epoch = self._merged_trial_epochs()[0]
            axis.text((first_epoch[0] + first_epoch[1]) / 2, axis.get_ylim()[1] * 0.92, "train trial", ha="center", va="top", fontsize=10, color="#92400e")
        for pulse in self.pulse_epochs:
            center = (pulse.start_ms + pulse.end_ms) / 2
            axis.text(center, axis.get_ylim()[1] * 0.72, f"P{pulse.pulse_index}", ha="center", va="center", fontsize=8, color="#78350f")
        axis.text(
            0.99,
            0.93,
            "command waveform from raw XML,\nnot measured analog trace",
            ha="right",
            va="top",
            transform=axis.transAxes,
            fontsize=8,
            color="#7c2d12",
        )
        axis.legend(loc="upper left", fontsize=8)

    def _draw_raster(self, axis: plt.Axes) -> None:
        self._draw_trial_epoch_overlay(axis)
        for trial_index in self.trials:
            trial_spikes = self.well_spikes.loc[self.well_spikes["trial_index"] == trial_index]
            if trial_spikes.empty:
                continue
            axis.vlines(
                trial_spikes["aligned_time_ms"],
                ymin=trial_index - 0.4,
                ymax=trial_index + 0.4,
                color="black",
                linewidth=0.7,
            )

        axis.axvline(0, color="crimson", linestyle="--", linewidth=1.2)
        axis.set_xlim(self.window.start_ms, self.window.end_ms)
        axis.set_ylim(-1, max(self.trials) + 1 if self.trials else 1)
        axis.set_title("Raster: trials = 5-pulse trains")
        axis.set_xlabel("time from stim (ms)")
        axis.set_ylabel("trial")

    def _draw_psth(self, axis: plt.Axes) -> None:
        self._draw_trial_epoch_overlay(axis)
        axis.bar(
            self.psth["bin_center_ms"],
            self.psth["rate_hz"],
            width=self.psth_config.bin_ms,
            color="#d1d5db",
            edgecolor="#9ca3af",
            linewidth=0.5,
            align="center",
            label="raw",
        )
        axis.bar(
            self.psth["bin_center_ms"],
            self.psth["smooth_rate_hz"],
            width=self.psth_config.bin_ms * 0.78,
            color="#0f766e",
            edgecolor="#0f766e",
            linewidth=0.4,
            alpha=0.75,
            align="center",
            label=f"boxcar {list(self.psth_config.boxcar_kernel)}",
        )
        axis.axvline(0, color="crimson", linestyle="--", linewidth=1.2)
        axis.set_xlim(self.window.start_ms, self.window.end_ms)
        axis.set_title("PSTH: trials = 5-pulse trains")
        axis.set_xlabel("time from stim (ms)")
        axis.set_ylabel("rate (Hz)")
        axis.legend(loc="upper right")

    def _draw_trial_boxplots(self, axis: plt.Axes) -> None:
        boxplot_data = []
        positions = []
        for trial_index in self.trials:
            trial_spikes = self.well_spikes.loc[self.well_spikes["trial_index"] == trial_index, "aligned_time_ms"]
            if trial_spikes.empty:
                continue
            boxplot_data.append(trial_spikes.values)
            positions.append(trial_index)

        if boxplot_data:
            axis.boxplot(
                boxplot_data,
                positions=positions,
                widths=0.65,
                patch_artist=True,
                boxprops={"facecolor": "#cbd5e1", "edgecolor": "#475569"},
                medianprops={"color": "#b91c1c", "linewidth": 1.6},
                whiskerprops={"color": "#475569"},
                capprops={"color": "#475569"},
                flierprops={
                    "marker": ".",
                    "markersize": 3,
                    "markerfacecolor": "#475569",
                    "markeredgecolor": "#475569",
                },
            )

        trial_summary = self.trial_summary.sort_values("trial_index")
        axis.plot(
            trial_summary["trial_index"],
            trial_summary["mean_time_to_spike_ms"],
            color="#0369a1",
            marker="o",
            markersize=4,
            linewidth=1.2,
            label="mean",
        )
        axis.plot(
            trial_summary["trial_index"],
            trial_summary["median_time_to_spike_ms"],
            color="#dc2626",
            marker="s",
            markersize=4,
            linewidth=1.2,
            label="median",
        )

        axis.axhline(0, color="crimson", linestyle="--", linewidth=1.2)
        axis.set_xlim(-1, max(self.trials) + 1 if self.trials else 1)
        axis.set_title("Spike-Time Distribution: trials = trains")
        axis.set_xlabel("trial")
        axis.set_ylabel("aligned spike time (ms)")
        axis.legend(loc="upper right")

    def _draw_delay_boxplot(self, axis: plt.Axes) -> None:
        train_delay_values = (
            self.trial_summary["first_post_stim_spike_ms"]
            .dropna()
            .astype(float)
            .to_numpy()
        )

        pulse_groups: list[tuple[str, np.ndarray]] = []
        for pulse_index in sorted(self.pulse_summary["pulse_index"].dropna().unique()):
            values = (
                self.pulse_summary.loc[self.pulse_summary["pulse_index"] == pulse_index, "first_post_pulse_delay_ms"]
                .dropna()
                .astype(float)
                .to_numpy()
            )
            pulse_groups.append((f"P{int(pulse_index)}", values))

        grouped_values: list[np.ndarray] = []
        labels: list[str] = []
        if len(train_delay_values) > 0:
            grouped_values.append(train_delay_values)
            labels.append("Train")
        for label, values in pulse_groups:
            if len(values) > 0:
                grouped_values.append(values)
                labels.append(label)

        if not grouped_values:
            axis.set_title("Delay Comparison")
            axis.set_ylabel("delay from onset (ms)")
            axis.set_xticks([])
            axis.text(0.5, 0.5, "no post-stim spikes", ha="center", va="center", transform=axis.transAxes)
            return

        axis.boxplot(
            grouped_values,
            positions=list(range(1, len(grouped_values) + 1)),
            widths=0.45,
            patch_artist=True,
            boxprops={"facecolor": "#bfdbfe", "edgecolor": "#1d4ed8"},
            medianprops={"color": "#b91c1c", "linewidth": 1.6},
            whiskerprops={"color": "#1d4ed8"},
            capprops={"color": "#1d4ed8"},
            flierprops={
                "marker": ".",
                "markersize": 3,
                "markerfacecolor": "#1d4ed8",
                "markeredgecolor": "#1d4ed8",
            },
        )
        for idx, values in enumerate(grouped_values, start=1):
            jitter = np.linspace(-0.09, 0.09, len(values)) if len(values) > 1 else np.array([0.0])
            axis.scatter(idx + jitter, values, s=18, color="#1d4ed8", alpha=0.8, zorder=3)
        axis.axhline(0, color="crimson", linestyle="--", linewidth=1.2)
        axis.set_xlim(0.5, len(grouped_values) + 0.5)
        axis.set_xticks(list(range(1, len(labels) + 1)))
        axis.set_xticklabels(labels)
        axis.set_title("Delay Comparison: train vs pulse")
        axis.set_ylabel("delay from onset (ms)")

    def _draw_trial_epoch_overlay(self, axis: plt.Axes) -> None:
        for start_ms, end_ms in self._merged_trial_epochs():
            axis.axvspan(start_ms, end_ms, color="#f59e0b", alpha=0.12, linewidth=0)

    def _merged_trial_epochs(self) -> list[tuple[float, float]]:
        if not self.opto_on_intervals_ms:
            return []

        merged: list[list[float]] = []
        merge_gap_ms = 100.0
        for start_ms, end_ms, _ in sorted(self.opto_on_intervals_ms, key=lambda row: row[0]):
            if not merged:
                merged.append([start_ms, end_ms])
                continue
            prev_start, prev_end = merged[-1]
            if start_ms - prev_end <= merge_gap_ms:
                merged[-1][1] = max(prev_end, end_ms)
            else:
                merged.append([start_ms, end_ms])
        return [(start, end) for start, end in merged]

class PulseAlignedWellFigure:
    def __init__(
        self,
        well: str,
        pulse_aligned_spikes: pd.DataFrame,
        trials: list[int],
        pulse_epochs: list[PulseEpoch],
        pulse_window: PulseWindow,
        opto_on_intervals_ms: list[tuple[float, float, float]],
        waveform_model: OptoWaveformModel,
        well_context_label: str = "opsin well",
    ) -> None:
        self.well = well
        self.pulse_aligned_spikes = pulse_aligned_spikes
        self.trials = trials
        self.pulse_epochs = pulse_epochs
        self.pulse_window = pulse_window
        self.opto_on_intervals_ms = opto_on_intervals_ms
        self.waveform_model = waveform_model
        self.well_context_label = well_context_label

    def save(self, output_dir: Path, output_name: str | None = None) -> Path:
        ncols = max(len(self.pulse_epochs), 1)
        fig, axes = plt.subplots(
            2,
            ncols,
            figsize=(3.1 * ncols, 7.5),
            constrained_layout=True,
            squeeze=False,
            gridspec_kw={"height_ratios": [0.9, 2.4]},
        )

        for idx, pulse in enumerate(self.pulse_epochs):
            self._draw_pulse_waveform(axes[0, idx], pulse)
            self._draw_pulse_raster(axes[1, idx], pulse)

        fig.suptitle(
            f"{self.well} {self.well_context_label}: pulse-by-position diagnostics with train trials preserved",
            fontsize=14,
        )
        output_path = output_dir / (
            output_name if output_name is not None else f"{self.well}_pulse_aligned_rasters.png"
        )
        fig.savefig(output_path, dpi=180)
        plt.close(fig)
        return output_path

    def _draw_pulse_waveform(self, axis: plt.Axes, pulse: PulseEpoch) -> None:
        x, y, proxy_x, proxy_y = self._pulse_waveform_trace(pulse)
        axis.axvspan(0, pulse.end_ms - pulse.start_ms, color="#f59e0b", alpha=0.12, linewidth=0)
        for start_ms, end_ms in self.waveform_model.max_level_intervals(
            pulse.start_ms + self.pulse_window.start_ms,
            pulse.start_ms + self.pulse_window.end_ms,
        ):
            axis.axvspan(start_ms - pulse.start_ms, end_ms - pulse.start_ms, color="#dc2626", alpha=0.12, linewidth=0)
        axis.plot(
            x,
            y,
            color="#b45309",
            linewidth=1.6,
            drawstyle="steps-post",
            label="command steps",
        )
        axis.plot(
            proxy_x,
            proxy_y,
            color=OPTO_BLUE,
            linewidth=3.0,
            alpha=0.95,
            label="smoothed opto proxy",
        )
        axis.fill_between(x, 0, y, color="#f59e0b", alpha=0.22)
        axis.axvline(0, color="crimson", linestyle="--", linewidth=1.0)
        axis.set_xlim(self.pulse_window.start_ms, self.pulse_window.end_ms)
        waveform_peak = float(np.max(y)) if y.size else 0.0
        axis.set_ylim(-0.02, max(0.55, waveform_peak * 1.15 if waveform_peak > 0 else 0.55))
        axis.set_title(f"P{pulse.pulse_index}")
        axis.set_xlabel("ms from pulse onset")
        axis.set_ylabel("LED")
        if pulse.pulse_index == 1:
            axis.legend(loc="upper left", fontsize=7)

    def _draw_pulse_raster(self, axis: plt.Axes, pulse: PulseEpoch) -> None:
        pulse_df = self.pulse_aligned_spikes.loc[
            self.pulse_aligned_spikes["pulse_index"] == pulse.pulse_index
        ]
        axis.axvspan(0, pulse.end_ms - pulse.start_ms, color="#f59e0b", alpha=0.12, linewidth=0)
        for trial_index in self.trials:
            trial_spikes = pulse_df.loc[pulse_df["trial_index"] == trial_index]
            if trial_spikes.empty:
                continue
            axis.vlines(
                trial_spikes["pulse_aligned_time_ms"],
                ymin=trial_index - 0.4,
                ymax=trial_index + 0.4,
                color="black",
                linewidth=0.7,
            )
        axis.axvline(0, color="crimson", linestyle="--", linewidth=1.0)
        axis.set_xlim(self.pulse_window.start_ms, self.pulse_window.end_ms)
        axis.set_ylim(-1, max(self.trials) + 1 if self.trials else 1)
        axis.set_title(f"Raster: pulse P{pulse.pulse_index}")
        axis.set_xlabel("ms from pulse onset")
        axis.set_ylabel("train trial")

    def _pulse_waveform_trace(self, pulse: PulseEpoch) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        abs_start = pulse.start_ms + self.pulse_window.start_ms
        abs_end = pulse.start_ms + self.pulse_window.end_ms
        step_x, step_y = self.waveform_model.step_trace(abs_start, abs_end)
        proxy_x, proxy_y = self.waveform_model.sampled_proxy(abs_start, abs_end)
        return (
            step_x - pulse.start_ms,
            step_y,
            proxy_x - pulse.start_ms,
            proxy_y,
        )


class PulseTrialSummaryFigure:
    def __init__(
        self,
        well: str,
        pulse_aligned_spikes: pd.DataFrame,
        pulse_trials: pd.DataFrame,
        pulse_summary: pd.DataFrame,
        psth: pd.DataFrame,
        pulse_window: PulseWindow,
        psth_config: PsthConfig,
        pulse_epochs: list[PulseEpoch],
        waveform_model: OptoWaveformModel,
        well_context_label: str = "opsin well",
    ) -> None:
        self.well = well
        self.pulse_aligned_spikes = pulse_aligned_spikes
        self.pulse_trials = pulse_trials
        self.pulse_summary = pulse_summary
        self.psth = psth
        self.pulse_window = pulse_window
        self.psth_config = psth_config
        self.pulse_epochs = pulse_epochs
        self.waveform_model = waveform_model
        self.well_context_label = well_context_label

    def save(self, output_dir: Path, output_name: str | None = None) -> Path:
        fig, axes = plt.subplots(
            4,
            2,
            figsize=(15, 13.5),
            constrained_layout=True,
            gridspec_kw={
                "height_ratios": [0.8, 2.0, 1.3, 1.8],
                "width_ratios": [3.4, 1.2],
            },
        )

        self._draw_waveform(axes[0, 0])
        axes[0, 1].set_visible(False)
        self._draw_raster(axes[1, 0])
        axes[1, 1].set_visible(False)
        self._draw_psth(axes[2, 0])
        axes[2, 1].set_visible(False)
        self._draw_delay_scatter(axes[3, 0])
        self._draw_delay_boxplot(axes[3, 1])

        fig.suptitle(
            f"{self.well} {self.well_context_label}: pooled pulse-trial raster/PSTH where each pulse instance is one pseudo-trial",
            fontsize=14,
        )
        output_path = output_dir / (
            output_name if output_name is not None else f"{self.well}_pulse_trial_summary.png"
        )
        fig.savefig(output_path, dpi=180)
        plt.close(fig)
        return output_path

    def _draw_waveform(self, axis: plt.Axes) -> None:
        if not self.pulse_epochs:
            axis.set_visible(False)
            return
        pulse = self.pulse_epochs[0]
        step_x, step_y, proxy_x, proxy_y = self._pulse_waveform_trace(pulse)
        axis.axvspan(0, pulse.end_ms - pulse.start_ms, color="#f59e0b", alpha=0.12, linewidth=0)
        axis.plot(
            step_x,
            step_y,
            color="#b45309",
            linewidth=1.8,
            drawstyle="steps-post",
            label="command steps",
        )
        axis.plot(
            proxy_x,
            proxy_y,
            color=OPTO_BLUE,
            linewidth=3.2,
            alpha=0.95,
            label="smoothed opto proxy",
        )
        axis.fill_between(step_x, 0, step_y, color="#f59e0b", alpha=0.22)
        axis.axvline(0, color="crimson", linestyle="--", linewidth=1.2)
        axis.set_xlim(self.pulse_window.start_ms, self.pulse_window.end_ms)
        waveform_peak = float(np.max(step_y)) if step_y.size else 0.0
        axis.set_ylim(-0.02, max(0.55, waveform_peak * 1.15 if waveform_peak > 0 else 0.55))
        axis.set_title("Single-Pulse Template for Pooled Pulse Trials")
        axis.set_xlabel("ms from pulse onset")
        axis.set_ylabel("LED level")
        axis.legend(loc="upper left", fontsize=8)

    def _draw_raster(self, axis: plt.Axes) -> None:
        for pulse_trial_index in self.pulse_trials["pulse_trial_index"].astype(int).tolist():
            pseudo_spikes = self.pulse_aligned_spikes.loc[
                self.pulse_aligned_spikes["pulse_trial_index"] == pulse_trial_index
            ]
            if pseudo_spikes.empty:
                continue
            axis.vlines(
                pseudo_spikes["pulse_aligned_time_ms"],
                ymin=pulse_trial_index - 0.4,
                ymax=pulse_trial_index + 0.4,
                color="black",
                linewidth=1.15,
            )
        axis.axvspan(0, self._pulse_duration_ms(), color="#f59e0b", alpha=0.12, linewidth=0)
        axis.axvline(0, color="crimson", linestyle="--", linewidth=1.2)
        axis.set_xlim(self.pulse_window.start_ms, self.pulse_window.end_ms)
        axis.set_ylim(-1, len(self.pulse_trials) + 1 if not self.pulse_trials.empty else 1)
        axis.set_yticks(np.arange(0, len(self.pulse_trials) + 1, 50) if not self.pulse_trials.empty else [0])
        axis.set_title(
            f"Raster: pulse-as-trial pooled view in appearance order ({len(self.pulse_trials)} pseudo-trials)"
        )
        axis.set_xlabel("ms from pulse onset")
        axis.set_ylabel("pseudo-trial")
        axis.text(
            0.995,
            0.98,
            "rows follow appearance order\nwithin each train block: P1 to P5",
            ha="right",
            va="top",
            transform=axis.transAxes,
            fontsize=8,
            color="#1e3a8a",
        )
        axis.set_facecolor("white")

    def _draw_psth(self, axis: plt.Axes) -> None:
        axis.axvspan(0, self._pulse_duration_ms(), color="#f59e0b", alpha=0.12, linewidth=0)
        axis.bar(
            self.psth["bin_center_ms"],
            self.psth["rate_hz"],
            width=self.psth_config.bin_ms,
            color="#dbeafe",
            edgecolor="#93c5fd",
            linewidth=0.5,
            align="center",
            label=f"{self.psth_config.bin_ms:.0f} ms bins",
        )
        axis.axvline(0, color="crimson", linestyle="--", linewidth=1.2)
        axis.set_xlim(self.pulse_window.start_ms, self.pulse_window.end_ms)
        axis.set_title("PSTH: pulse-as-trial pooled view, 1 ms bins, no smoothing")
        axis.set_xlabel("ms from pulse onset")
        axis.set_ylabel("rate (Hz)")
        axis.legend(loc="upper right")

    def _draw_delay_scatter(self, axis: plt.Axes) -> None:
        palette = sns.color_palette("tab10", n_colors=max(len(self.pulse_epochs), 1))
        for pulse_idx, pulse in enumerate(self.pulse_epochs, start=1):
            pulse_df = self.pulse_summary.loc[self.pulse_summary["pulse_index"] == pulse_idx]
            pulse_df = pulse_df.dropna(subset=["first_post_pulse_delay_ms"])
            if pulse_df.empty:
                continue
            axis.scatter(
                pulse_df["pulse_trial_index"],
                pulse_df["first_post_pulse_delay_ms"],
                s=16,
                alpha=0.78,
                color=palette[pulse_idx - 1],
                label=f"P{pulse_idx}",
            )

        axis.axhline(0, color="crimson", linestyle="--", linewidth=1.2)
        axis.set_xlim(0.5, len(self.pulse_trials) + 0.5 if not self.pulse_trials.empty else 1.5)
        axis.set_title("First Post-Pulse Delay Across Pooled Pseudo-Trials")
        axis.set_xlabel("pseudo-trial")
        axis.set_ylabel("delay from pulse onset (ms)")
        if self.pulse_epochs:
            axis.legend(loc="upper right", ncols=min(len(self.pulse_epochs), 5), fontsize=8)

    def _draw_delay_boxplot(self, axis: plt.Axes) -> None:
        grouped_values: list[np.ndarray] = []
        labels: list[str] = []

        all_values = self.pulse_summary["first_post_pulse_delay_ms"].dropna().astype(float).to_numpy()
        if len(all_values) > 0:
            grouped_values.append(all_values)
            labels.append("All")

        for pulse_index in sorted(self.pulse_summary["pulse_index"].dropna().unique()):
            values = (
                self.pulse_summary.loc[
                    self.pulse_summary["pulse_index"] == pulse_index, "first_post_pulse_delay_ms"
                ]
                .dropna()
                .astype(float)
                .to_numpy()
            )
            if len(values) == 0:
                continue
            grouped_values.append(values)
            labels.append(f"P{int(pulse_index)}")

        if not grouped_values:
            axis.set_title("Pooled Pulse Delays")
            axis.set_ylabel("delay from onset (ms)")
            axis.set_xticks([])
            axis.text(0.5, 0.5, "no post-pulse spikes", ha="center", va="center", transform=axis.transAxes)
            return

        axis.boxplot(
            grouped_values,
            positions=list(range(1, len(grouped_values) + 1)),
            widths=0.45,
            patch_artist=True,
            boxprops={"facecolor": "#bfdbfe", "edgecolor": "#1d4ed8"},
            medianprops={"color": "#b91c1c", "linewidth": 1.6},
            whiskerprops={"color": "#1d4ed8"},
            capprops={"color": "#1d4ed8"},
            flierprops={
                "marker": ".",
                "markersize": 3,
                "markerfacecolor": "#1d4ed8",
                "markeredgecolor": "#1d4ed8",
            },
        )
        for idx, values in enumerate(grouped_values, start=1):
            jitter = np.linspace(-0.09, 0.09, len(values)) if len(values) > 1 else np.array([0.0])
            axis.scatter(idx + jitter, values, s=18, color="#1d4ed8", alpha=0.8, zorder=3)
        axis.axhline(0, color="crimson", linestyle="--", linewidth=1.2)
        axis.set_xlim(0.5, len(grouped_values) + 0.5)
        axis.set_xticks(list(range(1, len(labels) + 1)))
        axis.set_xticklabels(labels)
        axis.set_title("Pooled Pulse Delay Distribution")
        axis.set_ylabel("delay from onset (ms)")

    def _pulse_duration_ms(self) -> float:
        if not self.pulse_epochs:
            return 0.0
        first_pulse = self.pulse_epochs[0]
        return first_pulse.end_ms - first_pulse.start_ms

    def _pulse_waveform_trace(self, pulse: PulseEpoch) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        abs_start = pulse.start_ms + self.pulse_window.start_ms
        abs_end = pulse.start_ms + self.pulse_window.end_ms
        step_x, step_y = self.waveform_model.step_trace(abs_start, abs_end)
        proxy_x, proxy_y = self.waveform_model.sampled_proxy(abs_start, abs_end)
        return (
            step_x - pulse.start_ms,
            step_y,
            proxy_x - pulse.start_ms,
            proxy_y,
        )


class ReportPanelComposer:
    def compose_report_panel(
        self,
        train_path: Path,
        pooled_pulse_path: Path,
        per_pulse_path: Path,
        output_path: Path,
    ) -> Path:
        train = Image.open(train_path)
        pooled = Image.open(pooled_pulse_path)
        per_pulse = Image.open(per_pulse_path)

        target_top_height = max(train.height, pooled.height)
        train = self._resize_to_height(train, target_top_height)
        pooled = self._resize_to_height(pooled, target_top_height)

        top_width = train.width + pooled.width
        top_row = Image.new("RGB", (top_width, target_top_height), "white")
        top_row.paste(train, (0, 0))
        top_row.paste(pooled, (train.width, 0))

        per_pulse = self._resize_to_width(per_pulse, top_width)
        canvas = Image.new("RGB", (top_width, top_row.height + per_pulse.height), "white")
        canvas.paste(top_row, (0, 0))
        canvas.paste(per_pulse, (0, top_row.height))
        canvas.save(output_path)
        return output_path

    @staticmethod
    def _resize_to_height(image: Image.Image, target_height: int) -> Image.Image:
        if image.height == target_height:
            return image
        scale = target_height / image.height
        new_width = int(round(image.width * scale))
        return image.resize((new_width, target_height))

    @staticmethod
    def _resize_to_width(image: Image.Image, target_width: int) -> Image.Image:
        if image.width == target_width:
            return image
        scale = target_width / image.width
        new_height = int(round(image.height * scale))
        return image.resize((target_width, new_height))


class OpsinStimSummaryApp:
    def __init__(
        self,
        spike_list_csv: Path,
        well_metadata_csv: Path,
        stim_events_csv: Path,
        output_dir: Path,
        pre_ms: float,
        post_ms: float,
        pulse_pre_ms: float,
        pulse_post_ms: float,
        bin_ms: float,
        boxcar_kernel: tuple[float, ...],
        raw_file: Path | None,
        top_n_opsin_wells: int | None,
    ) -> None:
        self.window = AnalysisWindow(pre_ms=pre_ms, post_ms=post_ms)
        self.pulse_window = PulseWindow(pre_ms=pulse_pre_ms, post_ms=pulse_post_ms)
        self.psth_config = PsthConfig(bin_ms=bin_ms, boxcar_kernel=boxcar_kernel)
        self.pulse_trial_psth_config = PsthConfig(bin_ms=1.0, boxcar_kernel=(1.0,))
        self.dataset = OpsinStimDataset(
            spike_list_csv=spike_list_csv,
            well_metadata_csv=well_metadata_csv,
            stim_events_csv=stim_events_csv,
            output_dir=output_dir,
            window=self.window,
        )
        self.raw_file = raw_file.expanduser().resolve() if raw_file is not None else None
        self.top_n_opsin_wells = top_n_opsin_wells
        self.opto_on_intervals_ms: list[tuple[float, float, float]] = []
        self.pulse_epochs: list[PulseEpoch] = []
        self.waveform_render_config = WaveformRenderConfig(sample_dt_ms=1.0, smooth_window_ms=2.0)
        self.report_panel_composer = ReportPanelComposer()

    def run(self) -> None:
        sns.set_theme(style="whitegrid")
        self.dataset.load()
        self._load_opto_intervals()
        opsin_wells = self.dataset.opsin_wells(self.top_n_opsin_wells)

        print(f"Opsin wells selected: {', '.join(opsin_wells)}")
        print(f"Output directory: {self.dataset.output_dir}")

        for well in opsin_wells:
            well_spikes = self.dataset.spikes_for_well(well)
            trials = self.dataset.well_trials(well)
            waveform_model = OptoWaveformModel(
                opto_on_intervals_ms=self.opto_on_intervals_ms,
                pulse_epochs=self.pulse_epochs,
                render_config=self.waveform_render_config,
            )

            analyzer = TrialLatencyAnalyzer(well_spikes=well_spikes, all_trials=trials)
            trial_summary = analyzer.build_trial_summary()
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
            psth = PsthBuilder(
                well_spikes=well_spikes,
                trials=trials,
                config=self.psth_config,
            ).build(self.window)
            pulse_trial_psth = PsthBuilder(
                well_spikes=pulse_aligned_spikes,
                trials=pulse_trials["pulse_trial_index"].astype(int).tolist(),
                config=self.pulse_trial_psth_config,
                time_column="pulse_aligned_time_ms",
            ).build(self.pulse_window)

            figure_path = OpsinWellFigure(
                well=well,
                well_spikes=well_spikes,
                trials=trials,
                psth=psth,
                trial_summary=trial_summary,
                pulse_summary=pulse_summary,
                window=self.window,
                psth_config=self.psth_config,
                opto_on_intervals_ms=self.opto_on_intervals_ms,
                pulse_epochs=self.pulse_epochs,
                waveform_model=waveform_model,
            ).save(self.dataset.output_dir)
            pulse_trial_figure_path = PulseTrialSummaryFigure(
                well=well,
                pulse_aligned_spikes=pulse_aligned_spikes,
                pulse_trials=pulse_trials,
                pulse_summary=pulse_summary,
                psth=pulse_trial_psth,
                pulse_window=self.pulse_window,
                psth_config=self.pulse_trial_psth_config,
                pulse_epochs=self.pulse_epochs,
                waveform_model=waveform_model,
            ).save(self.dataset.output_dir)

            summary_path = self.dataset.save_trial_summary(well, trial_summary)
            pulse_delay_summary = pulse_summary[
                [
                    "pulse_trial_index",
                    "train_trial_index",
                    "pulse_index",
                    "pulse_label",
                    "pulse_start_ms",
                    "pulse_end_ms",
                    "first_post_pulse_delay_ms",
                ]
            ].copy()
            pulse_summary_path = self.dataset.save_pulse_summary(well, pulse_delay_summary)
            pulse_trial_summary_path = self.dataset.save_pulse_trial_summary(well, pulse_summary)
            psth_path = self.dataset.output_dir / f"{well}_psth.csv"
            psth.to_csv(psth_path, index=False)
            pulse_trial_psth_path = self.dataset.output_dir / f"{well}_pulse_trial_psth.csv"
            pulse_trial_psth.to_csv(pulse_trial_psth_path, index=False)
            pulse_aligned_path = self.dataset.output_dir / f"{well}_pulse_aligned_spikes.csv"
            pulse_aligned_spikes.to_csv(pulse_aligned_path, index=False)
            pulse_trials_path = self.dataset.output_dir / f"{well}_pulse_trials.csv"
            pulse_trials.to_csv(pulse_trials_path, index=False)
            pulse_figure_path = PulseAlignedWellFigure(
                well=well,
                pulse_aligned_spikes=pulse_aligned_spikes,
                trials=trials,
                pulse_epochs=self.pulse_epochs,
                pulse_window=self.pulse_window,
                opto_on_intervals_ms=self.opto_on_intervals_ms,
                waveform_model=waveform_model,
            ).save(self.dataset.output_dir)
            combined_panel_path = self.report_panel_composer.compose_report_panel(
                figure_path,
                pulse_trial_figure_path,
                pulse_figure_path,
                self.dataset.output_dir / f"{well}_report_panel.png",
            )

            print(f"{well}: spikes={len(well_spikes)}, figure={figure_path}")
            print(f"{well}: pooled pulse-trial figure={pulse_trial_figure_path}")
            print(f"{well}: pulse figure={pulse_figure_path}")
            print(f"{well}: combined panel={combined_panel_path}")
            print(f"{well}: trial summary={summary_path}")
            print(f"{well}: pulse summary={pulse_summary_path}")
            print(f"{well}: pulse-trial summary={pulse_trial_summary_path}")
            print(f"{well}: pulse aligned spikes={pulse_aligned_path}")
            print(f"{well}: pulse trials={pulse_trials_path}")
            print(f"{well}: psth={psth_path}")
            print(f"{well}: pulse-trial psth={pulse_trial_psth_path}")

        self._write_report(opsin_wells)

    def _load_opto_intervals(self) -> None:
        if self.raw_file is None:
            return
        stim_file = AxionStimFile(self.raw_file)
        stim_file.parse()
        self.opto_on_intervals_ms = [
            (interval.start_ms, interval.end_ms, interval.intensity)
            for interval in stim_file.opto_on_intervals_ms()
        ]
        self.pulse_epochs = self._build_pulse_epochs(self.opto_on_intervals_ms)

    def _build_pulse_epochs(self, intervals: list[tuple[float, float, float]]) -> list[PulseEpoch]:
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

    def _write_report(self, opsin_wells: list[str]) -> None:
        report_path = self.dataset.output_dir / "REPORT.md"
        lines = [
            "# Opsin Summary Report",
            "",
            "This report distinguishes three analysis modes:",
            "",
            "- `train-as-trial`: one trial is one 5-pulse train, aligned to the train onset at `0 ms`.",
            "- `pulse-by-position`: each column shows one pulse position `P1..P5`, while rows remain the original train trials.",
            "- `pooled pulse-as-trial`: each individual pulse instance is promoted to its own pseudo-trial, so `n_pulses x n_train_trials` is inferred dynamically.",
            "",
            f"Train-aligned window: `{self.window.start_ms:.1f}` to `{self.window.end_ms:.1f}` ms.",
            f"Pulse-aligned window: `{self.pulse_window.start_ms:.1f}` to `{self.pulse_window.end_ms:.1f}` ms.",
            "",
            "Pulse epochs recovered from the raw optical program:",
        ]
        for pulse in self.pulse_epochs:
            lines.append(f"- `P{pulse.pulse_index}`: `{pulse.start_ms:.1f}` to `{pulse.end_ms:.1f}` ms")
        lines.extend(
            [
                "",
                "**Waveform Note**",
                "",
                "- The waveform drawn in the figure is reconstructed from the optical command program stored in the raw-file XML.",
                "- It is not a measured analog trace from the LED driver.",
                "- The neural recording sampling frequency in the CSV metadata is `12.5 kHz`, which corresponds to `0.08 ms` per sample.",
                "- The optical command itself includes `500 us` step segments, so the plotted waveform is best interpreted as the intended stimulation program.",
                "",
                "## Wells",
            ]
        )
        for well in opsin_wells:
            train_fig = f"{well}_opsin_raster_psth_boxplot.png"
            pooled_pulse_fig = f"{well}_pulse_trial_summary.png"
            pulse_fig = f"{well}_pulse_aligned_rasters.png"
            combined_fig = f"{well}_report_panel.png"
            train_summary = f"{well}_trial_latency_summary.csv"
            pulse_summary = f"{well}_pulse_latency_summary.csv"
            pulse_trial_summary = f"{well}_pulse_trial_latency_summary.csv"
            pulse_spikes = f"{well}_pulse_aligned_spikes.csv"
            pulse_trials = f"{well}_pulse_trials.csv"
            psth_file = f"{well}_psth.csv"
            pulse_trial_psth = f"{well}_pulse_trial_psth.csv"
            pooled_count = len(self.pulse_epochs) * len(self.dataset.well_trials(well))
            lines.append(f"### {well}")
            lines.append("")
            lines.append(
                f"- Dynamic pooled pulse-trial count: `{len(self.pulse_epochs)} x {len(self.dataset.well_trials(well))} = {pooled_count}` pseudo-trials."
            )
            lines.append("")
            lines.append("Combined report panel: train-as-trial, pooled pulse-as-trial, and per-pulse diagnostics")
            lines.append(f"![{combined_fig}](./{combined_fig})")
            lines.append("")
            lines.append("Individual figures")
            lines.append(f"- Train-aligned figure: `{train_fig}`")
            lines.append(f"- Pooled pulse-trial figure: `{pooled_pulse_fig}`")
            lines.append(f"- Pulse-aligned figure: `{pulse_fig}`")
            lines.append("")
            lines.append("Artifacts")
            lines.append(f"- Train summary: `{train_summary}`")
            lines.append(f"- Pulse delay summary: `{pulse_summary}`")
            lines.append(f"- Pulse-trial summary with spike-time stats: `{pulse_trial_summary}`")
            lines.append(f"- Pulse aligned spikes: `{pulse_spikes}`")
            lines.append(f"- Pulse trials: `{pulse_trials}`")
            lines.append(f"- PSTH: `{psth_file}`")
            lines.append(f"- Pulse-trial PSTH: `{pulse_trial_psth}`")
            lines.append("")
        report_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create stacked raster/PSTH/trial-summary plots for opsin wells."
    )
    parser.add_argument(
        "--spike-list-csv",
        type=Path,
        default=Path("outputs/ventral_sosrs_opsin_day3/spike_list_clean.csv"),
        help="Cleaned spike list CSV used to rebuild the aligned table for the current window.",
    )
    parser.add_argument(
        "--well-metadata-csv",
        type=Path,
        default=Path("outputs/ventral_sosrs_opsin_day3/well_metadata.csv"),
        help="Well metadata with treatment labels.",
    )
    parser.add_argument(
        "--stim-events-csv",
        type=Path,
        default=Path("outputs/stim_times/ventral_sosrs_opsin_day3(000)_stim_events.csv"),
        help="Stim event CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/opsin_summary/ventral_sosrs_opsin_day3"),
        help="Output directory for opsin summary figures and tables.",
    )
    parser.add_argument("--pre-ms", type=float, default=500.0, help="Milliseconds before stim.")
    parser.add_argument("--post-ms", type=float, default=500.0, help="Milliseconds after stim.")
    parser.add_argument(
        "--pulse-pre-ms",
        type=float,
        default=10.0,
        help="Milliseconds before each pulse onset for pulse-aligned rasters.",
    )
    parser.add_argument(
        "--pulse-post-ms",
        type=float,
        default=40.0,
        help="Milliseconds after each pulse onset for pulse-aligned rasters.",
    )
    parser.add_argument("--bin-ms", type=float, default=20.0, help="PSTH bin width in ms.")
    parser.add_argument(
        "--boxcar-kernel",
        type=float,
        nargs="+",
        default=[1.0, 1.0, 1.0],
        help="Boxcar weights for PSTH smoothing, e.g. --boxcar-kernel 1 1 1",
    )
    parser.add_argument(
        "--raw-file",
        type=Path,
        default=Path("/Volumes/MannySSD/maestro_pro_output_meas/6_22_2026/129-8445/ventral_sosrs_opsin_day3(000).raw"),
        help="Raw Axion file used to recover the opto-on intervals for overlay.",
    )
    parser.add_argument(
        "--top-n-opsin-wells",
        type=int,
        default=None,
        help="Limit to the top N opsin wells by aligned spike count.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = OpsinStimSummaryApp(
        spike_list_csv=args.spike_list_csv,
        well_metadata_csv=args.well_metadata_csv,
        stim_events_csv=args.stim_events_csv,
        output_dir=args.output_dir,
        pre_ms=args.pre_ms,
        post_ms=args.post_ms,
        pulse_pre_ms=args.pulse_pre_ms,
        pulse_post_ms=args.pulse_post_ms,
        bin_ms=args.bin_ms,
        boxcar_kernel=tuple(args.boxcar_kernel),
        raw_file=args.raw_file,
        top_n_opsin_wells=args.top_n_opsin_wells,
    )
    app.run()


if __name__ == "__main__":
    main()
