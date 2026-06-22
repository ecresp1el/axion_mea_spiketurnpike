from __future__ import annotations
"""Well-level train and pulse response analysis.

This module owns the second half of the biological analysis after spikes have
already been aligned to stimulation events. It builds three complementary views:

1. train-level analysis, where one 5-pulse train is treated as one trial,
2. pulse-by-position analysis, where P1..P5 are separated but train identity is
   preserved, and
3. pooled pulse analysis, where every pulse instance becomes its own pseudo-trial.

The classes below are arranged in the same order they are used by the pipeline:
window/config models, aligned dataset helpers, summary-table builders, waveform
reconstruction helpers, and figure writers.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from PIL import Image


@dataclass(frozen=True)
class AnalysisWindow:
    """Train-level alignment window expressed in milliseconds."""

    pre_ms: float
    post_ms: float

    @property
    def start_ms(self) -> float:
        """Return the negative pre-stimulus bound."""
        return -abs(self.pre_ms)

    @property
    def end_ms(self) -> float:
        """Return the positive post-stimulus bound."""
        return abs(self.post_ms)


@dataclass(frozen=True)
class PulseWindow:
    """Pulse-level alignment window expressed in milliseconds."""

    pre_ms: float
    post_ms: float

    @property
    def start_ms(self) -> float:
        """Return the negative pre-pulse bound."""
        return -abs(self.pre_ms)

    @property
    def end_ms(self) -> float:
        """Return the positive post-pulse bound."""
        return abs(self.post_ms)


@dataclass(frozen=True)
class PsthConfig:
    """Histogram and smoothing settings for PSTH construction."""

    bin_ms: float
    boxcar_kernel: tuple[float, ...]

    @property
    def normalized_kernel(self) -> np.ndarray:
        """Return the boxcar kernel normalized to unit sum."""
        kernel = np.asarray(self.boxcar_kernel, dtype=float)
        return kernel / kernel.sum()


@dataclass(frozen=True)
class WaveformRenderConfig:
    """Display-resolution settings for the opto waveform proxy."""

    sample_dt_ms: float
    smooth_window_ms: float

    @property
    def smooth_window_samples(self) -> int:
        """Convert the smoothing window from ms to discrete samples."""
        return max(1, int(round(self.smooth_window_ms / self.sample_dt_ms)))


@dataclass(frozen=True)
class PulseEpoch:
    """One pulse interval inside a stimulation train."""

    pulse_index: int
    start_ms: float
    end_ms: float


OPTO_BLUE = "#0057ff"


class OpsinStimDataset:
    """Rebuild train-aligned spike tables for well-level response analysis."""

    def __init__(
        self,
        spike_list_csv: Path,
        well_metadata_csv: Path,
        stim_events_csv: Path,
        window: AnalysisWindow,
    ) -> None:
        self.spike_list_csv = spike_list_csv.expanduser().resolve()
        self.well_metadata_csv = well_metadata_csv.expanduser().resolve()
        self.stim_events_csv = stim_events_csv.expanduser().resolve()
        self.window = window

        self.spikes = pd.DataFrame()
        self.aligned_spikes = pd.DataFrame()
        self.well_metadata = pd.DataFrame()
        self.stim_events = pd.DataFrame()

    def load(self) -> None:
        """Load source CSVs and construct the train-aligned spike table."""
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

    def _build_aligned_spikes(self) -> pd.DataFrame:
        """Align every spike to every stimulation train that includes its well."""
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
        """Recover the set of wells reported as stimulated in the event CSV."""
        stimulated: set[str] = set()
        if "stimulated_wells" not in self.stim_events.columns:
            return sorted(self.spikes["well"].dropna().astype(str).unique())

        for value in self.stim_events["stimulated_wells"].dropna():
            for well in str(value).split(";"):
                well = well.strip()
                if well:
                    stimulated.add(well)
        return sorted(stimulated) if stimulated else sorted(self.spikes["well"].dropna().astype(str).unique())

    def all_trials(self) -> list[int]:
        """Return all tagged stimulation trial indices in ascending order."""
        all_trials = self.stim_events["sequence_number"].dropna().astype(int).tolist()
        return sorted(all_trials)

    def spikes_for_well(self, well: str) -> pd.DataFrame:
        """Return the aligned spikes for one well."""
        return self.aligned_spikes.loc[self.aligned_spikes["well"] == well].copy()


class TrialLatencyAnalyzer:
    """Summarize train-level spike timing for one well."""

    def __init__(self, well_spikes: pd.DataFrame, all_trials: list[int]) -> None:
        self.well_spikes = well_spikes.copy()
        self.all_trials = all_trials

    def build_trial_summary(self) -> pd.DataFrame:
        """Build one summary row per train trial."""
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
    """Summarize pulse-level spike timing for pooled pulse trials."""

    def __init__(self, pulse_aligned_spikes: pd.DataFrame, pulse_trials: pd.DataFrame) -> None:
        self.pulse_aligned_spikes = pulse_aligned_spikes.copy()
        self.pulse_trials = pulse_trials.copy()

    def build_pulse_summary(self) -> pd.DataFrame:
        """Build one summary row per pulse pseudo-trial."""
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
    """Render the intended optical waveform from parsed raw-tag intervals."""

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
        """Return a piecewise-constant command trace over a requested window."""
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
        """Return a smoothed sampled proxy used for visually readable overlays."""
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
        """Return intervals that reached the maximum optical intensity."""
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
    """Convert train-aligned spikes into pulse-aligned pseudo-trials."""

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
        """Return pulse-aligned spikes plus the pulse-trial manifest table."""
        pulse_rows: list[dict[str, object]] = []
        spike_rows: list[dict[str, object]] = []
        pulse_trial_index = 1

        for train_trial_index in self.all_trials:
            for pulse_idx, pulse in enumerate(self.pulse_epochs):
                # Truncate the pulse-alignment window at the next pulse onset so
                # late spikes are not misattributed across adjacent pulses.
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
    """Build peristimulus time histograms from aligned spike times."""

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
        """Return a PSTH table with raw counts, rates, and smoothed rates."""
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
    """Compose the train-level summary figure for one well."""

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
        """Render and save the full train-level summary panel."""
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
        """Draw the train-level opto waveform and pulse labels."""
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
        """Draw the train-aligned raster for one well."""
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
        """Draw the train-level PSTH as raw and smoothed histograms."""
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
        """Draw per-trial spike-time distributions with mean/median overlays."""
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
        """Compare first-spike delays measured at train and pulse scales."""
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
        """Shade the full train stimulation epoch behind a panel."""
        for start_ms, end_ms in self._merged_trial_epochs():
            axis.axvspan(start_ms, end_ms, color="#f59e0b", alpha=0.12, linewidth=0)

    def _merged_trial_epochs(self) -> list[tuple[float, float]]:
        """Merge nearby opto intervals into one train-level shaded region."""
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
    """Compose the pulse-by-position diagnostic figure for one well."""

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
        """Render and save the pulse-by-position figure."""
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
        """Draw one pulse-centered waveform panel."""
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
        """Draw one pulse-specific raster while preserving train trial order."""
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
        """Return step and smoothed traces recentered around one pulse onset."""
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
    """Compose the pooled pulse-as-trial summary figure for one well."""

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
        """Render and save the pooled pulse pseudo-trial figure."""
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
        """Draw the single-pulse waveform template used for pooled trials."""
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
        """Draw the pooled pseudo-trial raster in appearance order."""
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
        """Draw the pooled pulse PSTH using fixed-width histogram bins."""
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
        """Draw first-post-pulse delays across pseudo-trials."""
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
        """Draw pooled delay distributions for all pulses and for each pulse index."""
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
        """Return the duration of the first pulse template."""
        if not self.pulse_epochs:
            return 0.0
        first_pulse = self.pulse_epochs[0]
        return first_pulse.end_ms - first_pulse.start_ms

    def _pulse_waveform_trace(self, pulse: PulseEpoch) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return step and smoothed traces recentered around one pulse onset."""
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
    """Combine the three major per-well figures into one stacked report image."""

    def compose_report_panel(
        self,
        train_path: Path,
        pooled_pulse_path: Path,
        per_pulse_path: Path,
        output_path: Path,
    ) -> Path:
        """Compose and save the combined per-well report panel."""
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
        """Resize an image while preserving aspect ratio to a target height."""
        if image.height == target_height:
            return image
        scale = target_height / image.height
        new_width = int(round(image.width * scale))
        return image.resize((new_width, target_height))

    @staticmethod
    def _resize_to_width(image: Image.Image, target_width: int) -> Image.Image:
        """Resize an image while preserving aspect ratio to a target width."""
        if image.width == target_width:
            return image
        scale = target_width / image.width
        new_height = int(round(image.height * scale))
        return image.resize((target_width, new_height))
