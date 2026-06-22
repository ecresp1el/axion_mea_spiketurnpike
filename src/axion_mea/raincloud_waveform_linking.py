from __future__ import annotations
"""Link stim-locked waveform snippets back to retained raincloud points.

This module bridges two analyses that previously lived in parallel:

1. the pulse-trial raincloud summary, which quantifies pre-stimulus and peak
   post-stimulus firing rates for selected wells across recordings, and
2. the `.spk` waveform snippets, which store the raw spike shapes for each
   detected event.

The goal here is not spike sorting. Axion exports only channel-level spike
events in the CSV tables used elsewhere in this repository, so the best
available "unit" proxy is one electrode within one well. For each retained
raincloud point, this module therefore:

1. identifies the exact well/recording pair that survived the raincloud
   filtering step,
2. locates the peak post-stimulus PSTH bin used for that point,
3. selects the electrode with the most spikes in that exact peak bin, and
4. plots pre-stimulus and post-stimulus waveform snippets for that electrode.

Those panels are meant to answer a narrow question clearly: what does the
dominant opto-tagged electrode waveform look like for the same point shown in
the raincloud plot?
"""

import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .spike_waveform_overview import AxionSpikeWaveformFile


GROUP_DISPLAY_LABELS = {
    "opsin": "BiVe4-ChR2 (+ opsin)",
    "no_opsin": "BiVe4-mCherry (- opsin)",
}

GROUP_COLORS = {
    "opsin": "#0057ff",
    "no_opsin": "#64748b",
}


@dataclass(frozen=True)
class RaincloudWaveformLinkConfig:
    """Configuration for unit-proxy waveform panels linked to raincloud points."""

    peak_bin_ms: float = 1.0
    pre_window_start_ms: float = -10.0
    pre_window_end_ms: float = 0.0
    post_window_start_ms: float = 0.0
    post_window_end_ms: float = 40.0
    fs_rs_threshold_ms: float = 0.45
    max_overlay_pre: int = 140
    max_overlay_post: int = 180


@dataclass(frozen=True)
class RaincloudWaveformPoint:
    """One retained well/recording point from the raincloud comparison."""

    group: str
    well: str
    rank_within_group: int
    recording_label: str
    recording_index: str
    pre_stim_mean_rate_hz: float
    peak_post_stim_rate_hz: float
    peak_post_time_ms: float
    peak_minus_pre_hz: float


class RecordingSpikeWaveformMatcher:
    """Attach `.spk` waveform indices to spikes from one recording.

    The critical bridge is the per-recording offset between the sample index
    encoded in `.spk` and the spike times exported in `spike_list_clean.csv`.
    The offset is inferred empirically from the sorted spike sample sequences,
    then used to build a one-to-one merge key based on:

    - corrected sample index, and
    - duplicate rank within that sample index.
    """

    KEY_COLUMNS = ["time_s", "well", "electrode", "channel_in_well", "amplitude_mV"]

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.expanduser().resolve()
        manifest = json.loads((self.project_root / "project_manifest.json").read_text(encoding="utf-8"))
        self.spk_file = Path(manifest["source_files"]["spk_file"]).expanduser().resolve()
        self.spike_list_clean_csv = (
            self.project_root / "processed_data" / "recording_overview" / "spike_list_clean.csv"
        )
        self.extraction = AxionSpikeWaveformFile(self.spk_file).extract()
        self.sample_index_offset = self._infer_sample_index_offset()
        self._recording_lookup = self._build_recording_lookup()

    def _infer_sample_index_offset(self) -> int:
        """Infer the constant offset between CSV spike times and `.spk` sample indices."""
        csv = pd.read_csv(self.spike_list_clean_csv)
        csv_sample = np.sort(
            (pd.to_numeric(csv["time_s"], errors="coerce") * self.extraction.metadata.sampling_hz)
            .round()
            .astype(np.int64)
            .to_numpy()
        )
        spk_sample = np.sort(self.extraction.sample_indices.astype(np.int64))
        if len(csv_sample) != len(spk_sample):
            raise ValueError(
                f"Spike count mismatch for {self.project_root.name}: csv={len(csv_sample)} vs spk={len(spk_sample)}."
            )
        deltas = spk_sample - csv_sample
        unique_deltas = np.unique(deltas)
        if unique_deltas.size != 1:
            raise ValueError(
                f"Expected one constant sample-index offset for {self.project_root.name}, found {unique_deltas[:10]}."
            )
        return int(unique_deltas[0])

    def _build_recording_lookup(self) -> pd.DataFrame:
        """Build a one-to-one lookup from exported spikes to waveform indices."""
        csv = pd.read_csv(self.spike_list_clean_csv).copy()
        for column in ["time_s", "amplitude_mV"]:
            csv[column] = pd.to_numeric(csv[column], errors="coerce")
        csv["channel_in_well"] = pd.to_numeric(csv["channel_in_well"], errors="coerce").astype("Int64")
        csv["sample_index"] = (
            (csv["time_s"] * self.extraction.metadata.sampling_hz).round().astype(np.int64) + self.sample_index_offset
        )
        csv = csv.reset_index(drop=False).rename(columns={"index": "recording_spike_row"})
        csv = csv.sort_values(["sample_index", "recording_spike_row"], kind="mergesort").reset_index(drop=True)
        csv["sample_rank"] = csv.groupby("sample_index").cumcount()

        waveform_lookup = pd.DataFrame(
            {
                "sample_index": self.extraction.sample_indices.astype(np.int64),
                "waveform_index": np.arange(len(self.extraction.sample_indices), dtype=int),
            }
        )
        waveform_lookup = waveform_lookup.sort_values(["sample_index", "waveform_index"], kind="mergesort").reset_index(
            drop=True
        )
        waveform_lookup["sample_rank"] = waveform_lookup.groupby("sample_index").cumcount()

        merged = csv.merge(
            waveform_lookup,
            on=["sample_index", "sample_rank"],
            how="left",
            validate="one_to_one",
        )
        if merged["waveform_index"].isna().any():
            raise ValueError(f"Waveform lookup failed for {self.project_root.name}.")
        return merged

    def attach_waveform_indices(self, spikes: pd.DataFrame) -> pd.DataFrame:
        """Attach waveform indices to a spike table derived from the same recording."""
        matched = spikes.copy()
        for column in ["time_s", "amplitude_mV"]:
            matched[column] = pd.to_numeric(matched[column], errors="coerce")
        matched["channel_in_well"] = pd.to_numeric(matched["channel_in_well"], errors="coerce").astype("Int64")

        merged = matched.merge(
            self._recording_lookup[self.KEY_COLUMNS + ["waveform_index", "sample_index"]],
            on=self.KEY_COLUMNS,
            how="left",
            validate="many_to_one",
        )
        if merged["waveform_index"].isna().any():
            raise ValueError(f"Could not attach waveform indices to all spikes for {self.project_root.name}.")
        return merged

    def waveforms_for_indices(self, waveform_indices: pd.Series) -> np.ndarray:
        """Return waveform rows for a list of waveform indices."""
        waveform_ids = waveform_indices.astype(int).to_numpy()
        return self.extraction.waveforms_uv[waveform_ids]


class RaincloudWaveformLinkBuilder:
    """Write electrode-proxy waveform panels linked to retained raincloud points."""

    def __init__(
        self,
        comparison_root: Path,
        recording_projects: list[object],
        config: RaincloudWaveformLinkConfig | None = None,
    ) -> None:
        self.comparison_root = comparison_root.expanduser().resolve()
        self.recording_projects = sorted(recording_projects, key=lambda item: item.recording_index)
        self.config = config or RaincloudWaveformLinkConfig()
        self.project_by_label = {project.recording_label: project for project in self.recording_projects}
        self._matcher_cache: dict[str, RecordingSpikeWaveformMatcher] = {}

    def write_linked_waveform_report(
        self,
        metrics_table: pd.DataFrame,
        retained_rate_points: pd.DataFrame,
    ) -> dict[str, Path]:
        """Write one figure and one table for the raincloud-linked waveform panels."""
        point_table = self._build_retained_point_table(metrics_table, retained_rate_points)
        if point_table.empty:
            return {}

        summaries: list[dict[str, object]] = []
        panel_payloads: dict[tuple[str, str], dict[str, object]] = {}

        for point in self._iter_points(point_table):
            payload = self._build_point_payload(point)
            panel_payloads[(point.recording_label, point.well)] = payload
            summaries.append(payload["summary"])

        summary_table = pd.DataFrame(summaries).sort_values(
            ["group", "well", "recording_index"], kind="mergesort"
        ).reset_index(drop=True)
        summary_table_path = self.comparison_root / "tables" / "table__raincloud_linked_unit_waveform_summary.csv"
        summary_table.to_csv(summary_table_path, index=False)

        figure_path = self.comparison_root / "figures" / "figure__raincloud_linked_unit_waveforms.png"
        self._draw_linked_waveform_grid(summary_table, panel_payloads, figure_path)

        manifest_path = self.comparison_root / "raincloud_linked_unit_waveform_summary.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "analysis_kind": "raincloud_linked_unit_waveforms",
                    "figure": str(figure_path),
                    "summary_table": str(summary_table_path),
                    "note": "Each panel uses the electrode with the most spikes in the exact peak post-stimulus PSTH bin for the retained raincloud point.",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "figure": figure_path,
            "summary_table": summary_table_path,
            "manifest": manifest_path,
        }

    def _build_retained_point_table(self, metrics_table: pd.DataFrame, retained_rate_points: pd.DataFrame) -> pd.DataFrame:
        """Keep only the well/recording pairs that actually appear in the raincloud plot."""
        retained_keys = retained_rate_points.loc[
            retained_rate_points["rate_period"] == "peak_post_stim_rate_hz",
            ["group", "well", "recording_label", "recording_index"],
        ].drop_duplicates()
        return metrics_table.merge(
            retained_keys,
            on=["group", "well", "recording_label", "recording_index"],
            how="inner",
        ).sort_values(["group", "rank_within_group", "well", "recording_index"], kind="mergesort")

    @staticmethod
    def _iter_points(point_table: pd.DataFrame) -> list[RaincloudWaveformPoint]:
        """Materialize retained metrics rows as dataclass points."""
        return [
            RaincloudWaveformPoint(
                group=str(row["group"]),
                well=str(row["well"]),
                rank_within_group=int(row["rank_within_group"]),
                recording_label=str(row["recording_label"]),
                recording_index=str(row["recording_index"]),
                pre_stim_mean_rate_hz=float(row["pre_stim_mean_rate_hz"]),
                peak_post_stim_rate_hz=float(row["peak_post_stim_rate_hz"]),
                peak_post_time_ms=float(row["peak_post_time_ms"]),
                peak_minus_pre_hz=float(row["peak_minus_pre_hz"]),
            )
            for _, row in point_table.iterrows()
        ]

    def _matcher_for_recording(self, recording_label: str) -> RecordingSpikeWaveformMatcher:
        """Load or reuse the waveform matcher for one recording."""
        if recording_label not in self._matcher_cache:
            project = self.project_by_label[recording_label]
            self._matcher_cache[recording_label] = RecordingSpikeWaveformMatcher(project.project_root)
        return self._matcher_cache[recording_label]

    def _build_point_payload(self, point: RaincloudWaveformPoint) -> dict[str, object]:
        """Build one panel payload for one retained raincloud point."""
        matcher = self._matcher_for_recording(point.recording_label)
        point_spikes_path = (
            matcher.project_root / "groups" / point.group / point.well / "tables" / "table__pulse_aligned_spikes.csv"
        )
        spikes = pd.read_csv(point_spikes_path)
        spikes = matcher.attach_waveform_indices(spikes)

        bin_half_width = self.config.peak_bin_ms / 2.0
        peak_bin = spikes.loc[
            (spikes["pulse_aligned_time_ms"] >= point.peak_post_time_ms - bin_half_width)
            & (spikes["pulse_aligned_time_ms"] < point.peak_post_time_ms + bin_half_width)
        ].copy()

        summary: dict[str, object] = {
            "group": point.group,
            "group_label": GROUP_DISPLAY_LABELS[point.group],
            "well": point.well,
            "rank_within_group": point.rank_within_group,
            "recording_label": point.recording_label,
            "recording_index": point.recording_index,
            "pre_stim_mean_rate_hz": point.pre_stim_mean_rate_hz,
            "peak_post_stim_rate_hz": point.peak_post_stim_rate_hz,
            "peak_post_time_ms": point.peak_post_time_ms,
            "peak_minus_pre_hz": point.peak_minus_pre_hz,
            "sample_index_offset": matcher.sample_index_offset,
        }

        if peak_bin.empty:
            summary.update(
                {
                    "status": "missing_peak_bin_spikes",
                    "selected_electrode": None,
                    "peak_bin_spike_count": 0,
                    "pre_waveform_count": 0,
                    "post_waveform_count": 0,
                    "post_mean_trough_to_peak_ms": np.nan,
                    "post_waveform_class": None,
                }
            )
            return {"summary": summary, "status": "missing_peak_bin_spikes"}

        electrode_counts = peak_bin["electrode"].value_counts()
        selected_electrode = str(electrode_counts.index[0])
        selected_spikes = spikes.loc[spikes["electrode"] == selected_electrode].copy()
        pre_spikes = selected_spikes.loc[
            (selected_spikes["pulse_aligned_time_ms"] >= self.config.pre_window_start_ms)
            & (selected_spikes["pulse_aligned_time_ms"] < self.config.pre_window_end_ms)
        ].copy()
        post_spikes = selected_spikes.loc[
            (selected_spikes["pulse_aligned_time_ms"] >= self.config.post_window_start_ms)
            & (selected_spikes["pulse_aligned_time_ms"] <= self.config.post_window_end_ms)
        ].copy()
        peak_electrode_spikes = peak_bin.loc[peak_bin["electrode"] == selected_electrode].copy()

        pre_waveforms = (
            matcher.waveforms_for_indices(pre_spikes["waveform_index"]) if not pre_spikes.empty else np.empty((0, 38))
        )
        post_waveforms = (
            matcher.waveforms_for_indices(post_spikes["waveform_index"]) if not post_spikes.empty else np.empty((0, 38))
        )
        post_ttp_ms = self._mean_waveform_trough_to_peak_ms(matcher.extraction.metadata.time_axis_ms, post_waveforms)
        post_class = self._classify_ttp(post_ttp_ms)

        summary.update(
            {
                "status": "ok",
                "selected_electrode": selected_electrode,
                "peak_bin_spike_count": int(len(peak_electrode_spikes)),
                "pre_waveform_count": int(len(pre_waveforms)),
                "post_waveform_count": int(len(post_waveforms)),
                "post_mean_trough_to_peak_ms": post_ttp_ms,
                "post_waveform_class": post_class,
            }
        )
        return {
            "summary": summary,
            "status": "ok",
            "time_axis_ms": matcher.extraction.metadata.time_axis_ms,
            "pre_waveforms": pre_waveforms,
            "post_waveforms": post_waveforms,
        }

    def _draw_linked_waveform_grid(
        self,
        summary_table: pd.DataFrame,
        panel_payloads: dict[tuple[str, str], dict[str, object]],
        output_path: Path,
    ) -> None:
        """Draw one panel per retained raincloud point with pre/post waveform overlays."""
        column_table = summary_table[["group", "well", "rank_within_group"]].drop_duplicates().sort_values(
            ["group", "rank_within_group", "well"], kind="mergesort"
        )
        columns = [tuple(row) for row in column_table.itertuples(index=False, name=None)]

        fig, axes = plt.subplots(
            len(self.recording_projects),
            len(columns),
            figsize=(4.4 * len(columns), 2.55 * len(self.recording_projects)),
            constrained_layout=True,
            squeeze=False,
        )

        for row_idx, project in enumerate(self.recording_projects):
            for col_idx, (group, well, _rank) in enumerate(columns):
                axis = axes[row_idx, col_idx]
                row = summary_table.loc[
                    (summary_table["recording_label"] == project.recording_label)
                    & (summary_table["group"] == group)
                    & (summary_table["well"] == well)
                ]

                if row.empty:
                    axis.set_axis_off()
                    axis.text(0.5, 0.5, "not retained in raincloud", ha="center", va="center", fontsize=9)
                    continue

                one_row = row.iloc[0]
                payload = panel_payloads[(project.recording_label, well)]
                if payload["status"] != "ok":
                    axis.set_axis_off()
                    axis.text(0.5, 0.5, "no peak-bin spikes", ha="center", va="center", fontsize=9)
                    continue

                self._draw_one_panel(axis, one_row, payload)

        fig.suptitle(
            "Raincloud-linked unit-proxy waveforms\n"
            "electrode selected from the exact peak post-stimulus PSTH bin for each retained point",
            fontsize=14,
        )
        fig.savefig(output_path, dpi=230, bbox_inches="tight")
        plt.close(fig)

    def _draw_one_panel(self, axis: plt.Axes, summary_row: pd.Series, payload: dict[str, object]) -> None:
        """Draw one pre/post waveform overlay panel for one retained point."""
        time_ms = payload["time_axis_ms"]
        pre_waveforms = payload["pre_waveforms"]
        post_waveforms = payload["post_waveforms"]
        group = str(summary_row["group"])
        color = GROUP_COLORS[group]
        rng = np.random.default_rng(20260622)

        if len(pre_waveforms) > 0:
            pre_overlay = self._sample_waveforms(pre_waveforms, self.config.max_overlay_pre, rng)
            axis.plot(time_ms, pre_overlay.T, color="#cbd5e1", alpha=0.08, linewidth=0.7)
            axis.plot(time_ms, pre_waveforms.mean(axis=0), color="#475569", linestyle="--", linewidth=1.8, label="pre mean")

        if len(post_waveforms) > 0:
            post_overlay = self._sample_waveforms(post_waveforms, self.config.max_overlay_post, rng)
            axis.plot(time_ms, post_overlay.T, color=color, alpha=0.05, linewidth=0.75)
            axis.plot(time_ms, post_waveforms.mean(axis=0), color=color, linewidth=2.6, label="post mean")

        axis.axvline(0, color="crimson", linestyle="--", linewidth=0.9)
        axis.axhline(0, color="#cbd5e1", linewidth=0.8)
        axis.grid(True, alpha=0.18)
        axis.set_title(f"{summary_row['recording_label']} | {summary_row['selected_electrode']}", fontsize=10)
        axis.set_xlabel("ms around spike")
        axis.set_ylabel("uV")
        axis.legend(loc="upper right", fontsize=7)
        axis.text(
            0.02,
            0.98,
            (
                f"{GROUP_DISPLAY_LABELS[group]}\n"
                f"{summary_row['well']} | pre {summary_row['pre_stim_mean_rate_hz']:.1f} Hz"
                f" | peak {summary_row['peak_post_stim_rate_hz']:.1f} Hz @ {summary_row['peak_post_time_ms']:.1f} ms\n"
                f"post n={int(summary_row['post_waveform_count'])}"
                f" | peak-bin n={int(summary_row['peak_bin_spike_count'])}"
                f" | TTP={summary_row['post_mean_trough_to_peak_ms']:.3f} ms"
                f" ({summary_row['post_waveform_class']})"
            ),
            transform=axis.transAxes,
            ha="left",
            va="top",
            fontsize=7.6,
            bbox={"facecolor": "white", "alpha": 0.86, "edgecolor": "none", "pad": 2.5},
        )

    @staticmethod
    def _sample_waveforms(waveforms: np.ndarray, max_count: int, rng: np.random.Generator) -> np.ndarray:
        """Randomly sample waveforms for plotting without replacement."""
        if len(waveforms) <= max_count:
            return waveforms
        keep = rng.choice(len(waveforms), size=max_count, replace=False)
        return waveforms[keep]

    def _classify_ttp(self, trough_to_peak_ms: float) -> str:
        """Return a coarse FS-like or RS-like label from mean-waveform width."""
        if np.isnan(trough_to_peak_ms):
            return "unknown"
        return "FS_like" if trough_to_peak_ms <= self.config.fs_rs_threshold_ms else "RS_like"

    @staticmethod
    def _mean_waveform_trough_to_peak_ms(time_ms: np.ndarray, waveforms: np.ndarray) -> float:
        """Measure trough-to-peak latency on the mean waveform of one panel."""
        if waveforms.size == 0:
            return np.nan
        mean_waveform = waveforms.mean(axis=0)
        trough_index = int(np.argmin(mean_waveform))
        if trough_index >= len(mean_waveform) - 1:
            return np.nan
        peak_index = trough_index + 1 + int(np.argmax(mean_waveform[trough_index + 1 :]))
        return float(time_ms[peak_index] - time_ms[trough_index])
