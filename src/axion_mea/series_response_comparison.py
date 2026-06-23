from __future__ import annotations
"""Cross-recording comparison of group-level well responses.

This module operates only after a recording series has already been built. It
does not re-parse raw Axion files. Instead, it reuses the normalized
per-recording outputs already written by the pipeline and builds one
series-level summary focused on the strongest wells in each treatment group.

For now the comparison stage answers one narrow biological question:

1. which wells rank highest by overall firing rate within the `opsin` and
   `no_opsin` groups,
2. how does the train-level PSTH for those selected wells change across
   recordings, and
3. how does the pooled pulse-as-trial PSTH (the 250 pseudo-trial view here)
   change across recordings.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde

from .raincloud_waveform_linking import RaincloudWaveformLinkBuilder


GROUP_DISPLAY_LABELS = {
    "opsin": "BiVe4-ChR2 (+ opsin)",
    "no_opsin": "BiVe4-mCherry (- opsin)",
}

GROUP_COLORS = {
    "opsin": "#0057ff",
    "no_opsin": "#64748b",
}

PERIOD_DISPLAY_LABELS = {
    "pre_stim_mean_rate_hz": "Pre-stim mean rate",
    "peak_post_stim_rate_hz": "Peak post-stim rate",
}

PULSE_DELAY_PERIOD_DISPLAY_LABELS = {
    "pre_pulse_delay_ms_summary": "Pre-pulse nearest-spike delay",
    "post_pulse_delay_ms_summary": "Post-pulse first-spike delay",
}

INSTANTANEOUS_METHOD_DISPLAY_LABELS = {
    "separate_trial_median": "Current method: separate-trial median",
    "separate_trial_mean": "Separate-trial mean",
    "matched_trial_median": "Matched pulse-trial median",
    "matched_trial_mean": "Matched pulse-trial mean",
}

INSTANTANEOUS_MIN_DELAY_MS = 1.0

PAIR_COLORS = {
    ("opsin", "pre_stim_mean_rate_hz"): "#93c5fd",
    ("opsin", "peak_post_stim_rate_hz"): "#0057ff",
    ("no_opsin", "pre_stim_mean_rate_hz"): "#cbd5e1",
    ("no_opsin", "peak_post_stim_rate_hz"): "#64748b",
}


@dataclass(frozen=True)
class SeriesRecordingProject:
    """Minimal per-recording reference used in cross-recording summaries."""

    recording_label: str
    recording_index: str
    project_root: Path


@dataclass(frozen=True)
class CrossRecordingOpsinLayout:
    """Output layout for the series-level group comparison."""

    root: Path

    @property
    def figures_dir(self) -> Path:
        """Directory containing series-level comparison figures."""
        return self.root / "figures"

    @property
    def tables_dir(self) -> Path:
        """Directory containing series-level comparison tables."""
        return self.root / "tables"

    @property
    def summary_path(self) -> Path:
        """Machine-readable summary of the comparison stage."""
        return self.root / "cross_recording_group_psth_summary.json"

    def create(self) -> None:
        """Create the full output folder structure."""
        for path in [self.root, self.figures_dir, self.tables_dir]:
            path.mkdir(parents=True, exist_ok=True)


class CrossRecordingOpsinComparator:
    """Build cross-recording PSTH summaries for top wells in each group."""

    def __init__(self, series_root: Path, recording_projects: list[SeriesRecordingProject], top_n_per_group: int = 2) -> None:
        self.series_root = series_root.expanduser().resolve()
        self.recording_projects = sorted(recording_projects, key=lambda item: item.recording_index)
        self.top_n_per_group = top_n_per_group
        self.layout = CrossRecordingOpsinLayout(
            root=self.series_root / "cross_recording_group_psth_comparison"
        )

    def run(self) -> None:
        """Write ranking tables plus train and pulse PSTH comparison figures."""
        self.layout.create()
        self._remove_stale_outputs(
            [
                self.layout.tables_dir / "table__pulse_trial_group_instantaneous_rate_distribution.csv",
                self.layout.figures_dir / "figure__pulse_trial_instantaneous_rate_raincloud_by_group.png",
            ]
        )
        rate_table = self._build_rate_table()
        if rate_table.empty:
            return

        ranking_table = self._build_group_ranking_table(rate_table)
        selected_wells = self._selected_group_wells(ranking_table)
        train_psth = self._collect_psth_tables(selected_wells, response_dir_name="train_response")
        pulse_trial_psth = self._collect_psth_tables(
            selected_wells,
            response_dir_name="pulse_response_all_pulses",
        )
        train_metrics = self._summarize_psth_metrics(train_psth)
        pulse_trial_metrics = self._summarize_psth_metrics(pulse_trial_psth)
        pulse_trial_group_metrics = self._collect_group_metric_pool(
            selected_wells=selected_wells,
            response_dir_name="pulse_response_all_pulses"
        )
        pulse_delay_metrics = self._collect_pulse_delay_metric_pool(
            selected_wells=selected_wells,
            retained_rate_points=pulse_trial_group_metrics,
        )

        rate_table.to_csv(
            self.layout.tables_dir / "table__group_overall_firing_rates_by_recording.csv",
            index=False,
        )
        ranking_table.to_csv(
            self.layout.tables_dir / "table__group_well_ranking.csv",
            index=False,
        )
        train_psth.to_csv(
            self.layout.tables_dir / "table__selected_group_train_psth_long.csv",
            index=False,
        )
        pulse_trial_psth.to_csv(
            self.layout.tables_dir / "table__selected_group_pulse_trial_psth_long.csv",
            index=False,
        )
        train_metrics.to_csv(
            self.layout.tables_dir / "table__selected_group_train_psth_metrics.csv",
            index=False,
        )
        pulse_trial_metrics.to_csv(
            self.layout.tables_dir / "table__selected_group_pulse_trial_psth_metrics.csv",
            index=False,
        )
        pulse_trial_group_metrics.to_csv(
            self.layout.tables_dir / "table__pulse_trial_group_rate_distribution.csv",
            index=False,
        )
        pulse_delay_metrics.to_csv(
            self.layout.tables_dir / "table__pulse_trial_group_spike_delay_distribution.csv",
            index=False,
        )

        train_figure_path = self.layout.figures_dir / "figure__train_psth_by_recording_and_group.png"
        pulse_figure_path = self.layout.figures_dir / "figure__pulse_trial_psth_by_recording_and_group.png"
        raincloud_figure_path = self.layout.figures_dir / "figure__pulse_trial_rate_raincloud_by_group.png"
        pulse_delay_figure_path = (
            self.layout.figures_dir / "figure__pulse_trial_spike_delay_raincloud_by_group.png"
        )
        self._draw_group_psth_grid(
            ranking_table=ranking_table,
            train_psth=train_psth,
            metrics_table=train_metrics,
            selected_wells=selected_wells,
            output_path=train_figure_path,
            response_kind="train_response",
        )
        self._draw_group_psth_grid(
            ranking_table=ranking_table,
            train_psth=pulse_trial_psth,
            metrics_table=pulse_trial_metrics,
            selected_wells=selected_wells,
            output_path=pulse_figure_path,
            response_kind="pulse_response_all_pulses",
        )
        self._draw_rate_raincloud(
            metrics_long=pulse_trial_group_metrics,
            output_path=raincloud_figure_path,
        )
        self._draw_pulse_delay_raincloud(
            metrics_long=pulse_delay_metrics,
            output_path=pulse_delay_figure_path,
        )
        linked_waveform_outputs = RaincloudWaveformLinkBuilder(
            comparison_root=self.layout.root,
            recording_projects=self.recording_projects,
        ).write_linked_waveform_report(
            metrics_table=pulse_trial_metrics,
            retained_rate_points=pulse_trial_group_metrics,
        )
        self.layout.summary_path.write_text(
            json.dumps(
                {
                    "analysis_kind": "cross_recording_group_response_comparison",
                    "selected_top_n_per_group": self.top_n_per_group,
                    "selected_wells": selected_wells,
                    "files": {
                        "train_figure": str(train_figure_path),
                        "pulse_trial_figure": str(pulse_figure_path),
                        "pulse_trial_rate_raincloud_figure": str(raincloud_figure_path),
                        "overall_rates": str(
                            self.layout.tables_dir / "table__group_overall_firing_rates_by_recording.csv"
                        ),
                        "well_ranking": str(self.layout.tables_dir / "table__group_well_ranking.csv"),
                        "train_psth_long": str(self.layout.tables_dir / "table__selected_group_train_psth_long.csv"),
                        "train_psth_metrics": str(
                            self.layout.tables_dir / "table__selected_group_train_psth_metrics.csv"
                        ),
                        "pulse_trial_psth_long": str(
                            self.layout.tables_dir / "table__selected_group_pulse_trial_psth_long.csv"
                        ),
                        "pulse_trial_psth_metrics": str(
                            self.layout.tables_dir / "table__selected_group_pulse_trial_psth_metrics.csv"
                        ),
                        "pulse_trial_group_rate_distribution": str(
                            self.layout.tables_dir / "table__pulse_trial_group_rate_distribution.csv"
                        ),
                        "pulse_trial_group_spike_delay_distribution": str(
                            self.layout.tables_dir / "table__pulse_trial_group_spike_delay_distribution.csv"
                        ),
                        "pulse_trial_spike_delay_raincloud_figure": str(pulse_delay_figure_path),
                        "raincloud_linked_unit_waveform_figure": str(linked_waveform_outputs.get("figure", "")),
                        "raincloud_linked_prepost_waveform_figure": str(
                            linked_waveform_outputs.get("prepost_figure", "")
                        ),
                        "raincloud_linked_unit_waveform_mathcheck_figure": str(
                            linked_waveform_outputs.get("mathcheck_figure", "")
                        ),
                        "raincloud_linked_unit_waveform_summary": str(
                            linked_waveform_outputs.get("summary_table", "")
                        ),
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _remove_stale_outputs(paths: list[Path]) -> None:
        """Delete legacy outputs that would otherwise coexist with renamed files."""
        for path in paths:
            if path.exists():
                path.unlink()

    def _build_rate_table(self) -> pd.DataFrame:
        """Compute per-recording overall firing rates for opsin and no-opsin wells."""
        rows: list[dict[str, object]] = []

        for project in self.recording_projects:
            overview_dir = project.project_root / "processed_data" / "recording_overview"
            counts_path = overview_dir / "well_counts_long.csv"
            metadata_path = overview_dir / "well_metadata.csv"
            if not counts_path.exists() or not metadata_path.exists():
                continue

            counts = pd.read_csv(counts_path)
            metadata = pd.read_csv(metadata_path)
            interval_width_s = pd.to_numeric(counts["interval_end_s"], errors="coerce") - pd.to_numeric(
                counts["interval_start_s"], errors="coerce"
            )
            total_time_s = float(interval_width_s.dropna().sum())
            if total_time_s <= 0:
                continue

            for _, row in metadata.iterrows():
                well = str(row.get("well", "")).strip()
                if not well:
                    continue
                group_name = self._classify_group(row.get("Treatment"))
                if group_name is None:
                    continue
                total_spikes = int(counts.loc[counts["well"] == well, "spike_count"].sum())
                rows.append(
                    {
                        "group": group_name,
                        "recording_label": project.recording_label,
                        "recording_index": project.recording_index,
                        "well": well,
                        "total_spikes": total_spikes,
                        "overall_rate_hz": total_spikes / total_time_s,
                    }
                )

        return pd.DataFrame(rows).sort_values(["group", "well", "recording_index"]).reset_index(drop=True)

    def _build_group_ranking_table(self, rate_table: pd.DataFrame) -> pd.DataFrame:
        """Rank wells within each biological group by mean overall firing rate."""
        ranking = (
            rate_table.groupby(["group", "well"], as_index=False)
            .agg(
                mean_overall_rate_hz=("overall_rate_hz", "mean"),
                median_overall_rate_hz=("overall_rate_hz", "median"),
                mean_total_spikes=("total_spikes", "mean"),
                recording_count=("recording_index", "nunique"),
            )
            .sort_values(["group", "mean_overall_rate_hz", "mean_total_spikes"], ascending=[True, False, False])
            .reset_index(drop=True)
        )
        ranking["rank_within_group"] = ranking.groupby("group").cumcount() + 1
        ranking = ranking[["group", "rank_within_group", "well", "mean_overall_rate_hz", "median_overall_rate_hz", "mean_total_spikes", "recording_count"]]
        return ranking

    def _selected_group_wells(self, ranking_table: pd.DataFrame) -> list[dict[str, str]]:
        """Return selected wells in display order: opsin first, then no-opsin."""
        selected: list[dict[str, str]] = []
        for group_name in ["opsin", "no_opsin"]:
            group_rows = ranking_table.loc[ranking_table["group"] == group_name].head(self.top_n_per_group)
            for _, row in group_rows.iterrows():
                selected.append(
                    {
                        "group": str(row["group"]),
                        "well": str(row["well"]),
                        "rank_within_group": str(int(row["rank_within_group"])),
                    }
                )
        return selected

    def _collect_psth_tables(self, selected_wells: list[dict[str, str]], response_dir_name: str) -> pd.DataFrame:
        """Collect one long-format PSTH table across recordings for selected wells."""
        rows: list[pd.DataFrame] = []
        table_name = (
            "table__train_response_psth.csv"
            if response_dir_name == "train_response"
            else "table__pulse_response_all_pulses_psth.csv"
        )

        for project in self.recording_projects:
            for well_info in selected_wells:
                group_dir_name = "opsin" if well_info["group"] == "opsin" else "no_opsin"
                well = well_info["well"]
                table_path = (
                    project.project_root
                    / "groups"
                    / group_dir_name
                    / well
                    / response_dir_name
                    / table_name
                )
                if not table_path.exists():
                    continue
                psth = pd.read_csv(table_path)
                psth["recording_label"] = project.recording_label
                psth["recording_index"] = project.recording_index
                psth["well"] = well
                psth["group"] = well_info["group"]
                psth["rank_within_group"] = int(well_info["rank_within_group"])
                psth["response_view"] = response_dir_name
                rows.append(psth)

        if not rows:
            return pd.DataFrame()
        return pd.concat(rows, ignore_index=True)

    def _collect_group_metric_pool(self, selected_wells: list[dict[str, str]], response_dir_name: str) -> pd.DataFrame:
        """Collect pooled pre/post rate summaries for the selected top wells only."""
        psth_rows: list[pd.DataFrame] = []
        table_name = (
            "table__train_response_psth.csv"
            if response_dir_name == "train_response"
            else "table__pulse_response_all_pulses_psth.csv"
        )
        selected_lookup = {
            (entry["group"], entry["well"]): int(entry["rank_within_group"])
            for entry in selected_wells
        }

        for project in self.recording_projects:
            for (group_name, well_name), rank_within_group in selected_lookup.items():
                group_dir_name = "opsin" if group_name == "opsin" else "no_opsin"
                group_dir = project.project_root / "groups" / group_dir_name
                well_dir = group_dir / well_name
                if not well_dir.exists():
                    continue
                table_path = well_dir / response_dir_name / table_name
                if not table_path.exists():
                    continue
                psth = pd.read_csv(table_path)
                psth["recording_label"] = project.recording_label
                psth["recording_index"] = project.recording_index
                psth["well"] = well_name
                psth["group"] = group_name
                psth["rank_within_group"] = rank_within_group
                psth["response_view"] = response_dir_name
                psth_rows.append(psth)

        if not psth_rows:
            return pd.DataFrame()

        metrics = self._summarize_psth_metrics(pd.concat(psth_rows, ignore_index=True))
        # Remove weak-baseline pairs before plotting so every retained point
        # represents a well/recording pair with at least 1 Hz prestim activity.
        metrics = metrics.loc[metrics["pre_stim_mean_rate_hz"] >= 1.0].copy()
        long = metrics.melt(
            id_vars=[
                "group",
                "well",
                "recording_label",
                "recording_index",
                "response_view",
                "peak_post_time_ms",
                "peak_minus_pre_hz",
            ],
            value_vars=["pre_stim_mean_rate_hz", "peak_post_stim_rate_hz"],
            var_name="rate_period",
            value_name="firing_rate_hz",
        )
        long["group_label"] = long["group"].map(GROUP_DISPLAY_LABELS)
        long["period_label"] = long["rate_period"].map(PERIOD_DISPLAY_LABELS)
        long["raincloud_label"] = long["group_label"] + " | " + long["period_label"]
        return long.sort_values(
            ["group", "rate_period", "recording_index", "well"]
        ).reset_index(drop=True)

    def _collect_pulse_delay_metric_pool(
        self,
        selected_wells: list[dict[str, str]],
        retained_rate_points: pd.DataFrame,
    ) -> pd.DataFrame:
        """Collect retained-pair pulse-aligned spike-delay summaries.

        This branch intentionally stays in milliseconds. The prior version
        converted delay to `1000 / delay`, which made spontaneous pre-pulse
        spikes look like a strong baseline "rate" and visually inverted the
        post-stimulus effect relative to the PSTH-based rate summaries.
        """
        if retained_rate_points.empty:
            return pd.DataFrame()

        retained_pairs = retained_rate_points.loc[
            retained_rate_points["rate_period"] == "peak_post_stim_rate_hz",
            ["group", "well", "recording_label", "recording_index"],
        ].drop_duplicates()
        selected_lookup = {
            (entry["group"], entry["well"]): int(entry["rank_within_group"])
            for entry in selected_wells
        }
        summary_rows: list[dict[str, object]] = []

        for project in self.recording_projects:
            for (group_name, well_name), rank_within_group in selected_lookup.items():
                key_mask = (
                    (retained_pairs["group"] == group_name)
                    & (retained_pairs["well"] == well_name)
                    & (retained_pairs["recording_label"] == project.recording_label)
                    & (retained_pairs["recording_index"].astype(str) == str(project.recording_index))
                )
                if not key_mask.any():
                    continue

                group_dir_name = "opsin" if group_name == "opsin" else "no_opsin"
                aligned_spikes_path = (
                    project.project_root
                    / "groups"
                    / group_dir_name
                    / well_name
                    / "tables"
                    / "table__pulse_aligned_spikes.csv"
                )
                if not aligned_spikes_path.exists():
                    continue

                aligned = pd.read_csv(aligned_spikes_path)
                aligned["pulse_aligned_time_ms"] = pd.to_numeric(aligned["pulse_aligned_time_ms"], errors="coerce")
                pre_delay_ms = (
                    aligned.loc[aligned["pulse_aligned_time_ms"] < 0]
                    .groupby("pulse_trial_index")["pulse_aligned_time_ms"]
                    .max()
                    .abs()
                )
                post_delay_ms = (
                    aligned.loc[aligned["pulse_aligned_time_ms"] > 0]
                    .groupby("pulse_trial_index")["pulse_aligned_time_ms"]
                    .min()
                )
                pre_delay_ms = pre_delay_ms.loc[
                    (pre_delay_ms >= INSTANTANEOUS_MIN_DELAY_MS) & np.isfinite(pre_delay_ms)
                ]
                post_delay_ms = post_delay_ms.loc[
                    (post_delay_ms >= INSTANTANEOUS_MIN_DELAY_MS) & np.isfinite(post_delay_ms)
                ]
                if pre_delay_ms.empty or post_delay_ms.empty:
                    continue

                matched = pd.DataFrame(
                    {
                        "pre_delay_ms": pre_delay_ms,
                        "post_delay_ms": post_delay_ms,
                    }
                ).dropna()
                summary_rows.extend(
                    [
                        {
                            "group": group_name,
                            "group_label": GROUP_DISPLAY_LABELS[group_name],
                            "well": well_name,
                            "rank_within_group": rank_within_group,
                            "recording_label": project.recording_label,
                            "recording_index": project.recording_index,
                            "response_view": "pulse_response_all_pulses",
                            "method": "separate_trial_median",
                            "pre_pulse_delay_ms_summary": float(np.median(pre_delay_ms)),
                            "post_pulse_delay_ms_summary": float(np.median(post_delay_ms)),
                            "pre_pulse_trial_count": int(len(pre_delay_ms)),
                            "post_pulse_trial_count": int(len(post_delay_ms)),
                            "matched_pulse_trial_count": int(len(matched)),
                        },
                        {
                            "group": group_name,
                            "group_label": GROUP_DISPLAY_LABELS[group_name],
                            "well": well_name,
                            "rank_within_group": rank_within_group,
                            "recording_label": project.recording_label,
                            "recording_index": project.recording_index,
                            "response_view": "pulse_response_all_pulses",
                            "method": "separate_trial_mean",
                            "pre_pulse_delay_ms_summary": float(np.mean(pre_delay_ms)),
                            "post_pulse_delay_ms_summary": float(np.mean(post_delay_ms)),
                            "pre_pulse_trial_count": int(len(pre_delay_ms)),
                            "post_pulse_trial_count": int(len(post_delay_ms)),
                            "matched_pulse_trial_count": int(len(matched)),
                        },
                    ]
                )
                if not matched.empty:
                    summary_rows.extend(
                        [
                            {
                                "group": group_name,
                                "group_label": GROUP_DISPLAY_LABELS[group_name],
                                "well": well_name,
                                "rank_within_group": rank_within_group,
                                "recording_label": project.recording_label,
                                "recording_index": project.recording_index,
                                "response_view": "pulse_response_all_pulses",
                                "method": "matched_trial_median",
                                "pre_pulse_delay_ms_summary": float(np.median(matched["pre_delay_ms"])),
                                "post_pulse_delay_ms_summary": float(np.median(matched["post_delay_ms"])),
                                "pre_pulse_trial_count": int(len(pre_delay_ms)),
                                "post_pulse_trial_count": int(len(post_delay_ms)),
                                "matched_pulse_trial_count": int(len(matched)),
                            },
                            {
                                "group": group_name,
                                "group_label": GROUP_DISPLAY_LABELS[group_name],
                                "well": well_name,
                                "rank_within_group": rank_within_group,
                                "recording_label": project.recording_label,
                                "recording_index": project.recording_index,
                                "response_view": "pulse_response_all_pulses",
                                "method": "matched_trial_mean",
                                "pre_pulse_delay_ms_summary": float(np.mean(matched["pre_delay_ms"])),
                                "post_pulse_delay_ms_summary": float(np.mean(matched["post_delay_ms"])),
                                "pre_pulse_trial_count": int(len(pre_delay_ms)),
                                "post_pulse_trial_count": int(len(post_delay_ms)),
                                "matched_pulse_trial_count": int(len(matched)),
                            },
                        ]
                    )

        if not summary_rows:
            return pd.DataFrame()

        summary = pd.DataFrame(summary_rows).sort_values(
            ["group", "well", "recording_index"], kind="mergesort"
        ).reset_index(drop=True)
        long = summary.melt(
            id_vars=[
                "group",
                "group_label",
                "well",
                "rank_within_group",
                "recording_label",
                "recording_index",
                "response_view",
                "method",
                "pre_pulse_trial_count",
                "post_pulse_trial_count",
                "matched_pulse_trial_count",
            ],
            value_vars=["pre_pulse_delay_ms_summary", "post_pulse_delay_ms_summary"],
            var_name="delay_period",
            value_name="spike_delay_ms",
        )
        long["period_label"] = long["delay_period"].map(PULSE_DELAY_PERIOD_DISPLAY_LABELS)
        long["method_label"] = long["method"].map(INSTANTANEOUS_METHOD_DISPLAY_LABELS)
        return long.sort_values(
            ["method", "group", "delay_period", "recording_index", "well"], kind="mergesort"
        ).reset_index(drop=True)

    def _summarize_psth_metrics(self, psth_long: pd.DataFrame) -> pd.DataFrame:
        """Quantify baseline and peak post-stimulus firing rates from PSTHs.

        Baseline firing rate:
        - mean `rate_hz` across all bins with `bin_center_ms < 0`

        Peak post-stimulus firing rate:
        - maximum `rate_hz` across all bins with `bin_center_ms >= 0`
        - `peak_post_time_ms` records when that peak occurred
        """
        if psth_long.empty:
            return pd.DataFrame(
                columns=[
                    "group",
                    "well",
                    "rank_within_group",
                    "recording_label",
                    "recording_index",
                    "response_view",
                    "pre_stim_mean_rate_hz",
                    "peak_post_stim_rate_hz",
                    "peak_post_time_ms",
                    "peak_minus_pre_hz",
                    "window_start_ms",
                    "window_end_ms",
                ]
            )

        rows: list[dict[str, object]] = []
        group_cols = ["group", "well", "rank_within_group", "recording_label", "recording_index", "response_view"]
        for keys, one_panel in psth_long.groupby(group_cols, dropna=False, sort=True):
            panel = one_panel.sort_values("bin_center_ms").copy()
            pre = panel.loc[panel["bin_center_ms"] < 0, "rate_hz"]
            post_panel = panel.loc[panel["bin_center_ms"] >= 0].copy()
            pre_mean = float(pre.mean()) if not pre.empty else np.nan
            if post_panel.empty:
                peak_rate = np.nan
                peak_time = np.nan
            else:
                peak_idx = post_panel["rate_hz"].idxmax()
                peak_rate = float(post_panel.loc[peak_idx, "rate_hz"])
                peak_time = float(post_panel.loc[peak_idx, "bin_center_ms"])

            rows.append(
                {
                    "group": keys[0],
                    "well": keys[1],
                    "rank_within_group": keys[2],
                    "recording_label": keys[3],
                    "recording_index": keys[4],
                    "response_view": keys[5],
                    "pre_stim_mean_rate_hz": pre_mean,
                    "peak_post_stim_rate_hz": peak_rate,
                    "peak_post_time_ms": peak_time,
                    "peak_minus_pre_hz": peak_rate - pre_mean if pd.notna(peak_rate) and pd.notna(pre_mean) else np.nan,
                    "window_start_ms": float(panel["bin_center_ms"].min()),
                    "window_end_ms": float(panel["bin_center_ms"].max()),
                }
            )

        return pd.DataFrame(rows).sort_values(
            ["group", "rank_within_group", "well", "recording_index"]
        ).reset_index(drop=True)

    def _draw_group_psth_grid(
        self,
        ranking_table: pd.DataFrame,
        train_psth: pd.DataFrame,
        metrics_table: pd.DataFrame,
        selected_wells: list[dict[str, str]],
        output_path: Path,
        response_kind: str,
    ) -> None:
        """Draw one faceted PSTH figure with recordings separated by row."""
        if not selected_wells:
            return

        nrows = len(self.recording_projects) + 1
        ncols = len(selected_wells)
        fig, axes = plt.subplots(
            nrows,
            ncols,
            figsize=(4.6 * ncols, 2.2 * nrows),
            constrained_layout=True,
            gridspec_kw={"height_ratios": [0.8] + [1.6] * len(self.recording_projects)},
            squeeze=False,
        )

        for col_idx, well_info in enumerate(selected_wells):
            header_axis = axes[0, col_idx]
            header_axis.set_axis_off()
            well = well_info["well"]
            group = well_info["group"]
            ranking_row = ranking_table.loc[
                (ranking_table["group"] == group) & (ranking_table["well"] == well)
            ].iloc[0]
            mean_rate = float(ranking_row["mean_overall_rate_hz"])
            header_axis.text(
                0.5,
                0.68,
                well,
                ha="center",
                va="center",
                fontsize=13,
                fontweight="bold",
            )
            header_axis.text(
                0.5,
                0.34,
                f"{group.replace('_', ' ')} rank {int(ranking_row['rank_within_group'])}\nmean rate {mean_rate:.4f} Hz",
                ha="center",
                va="center",
                fontsize=9,
                color="#374151",
            )

        for row_idx, project in enumerate(self.recording_projects, start=1):
            for col_idx, well_info in enumerate(selected_wells):
                axis = axes[row_idx, col_idx]
                one_panel = train_psth.loc[
                    (train_psth["recording_index"] == project.recording_index)
                    & (train_psth["well"] == well_info["well"])
                    & (train_psth["group"] == well_info["group"])
                ].copy()
                one_metrics = metrics_table.loc[
                    (metrics_table["recording_index"] == project.recording_index)
                    & (metrics_table["well"] == well_info["well"])
                    & (metrics_table["group"] == well_info["group"])
                ].copy()
                is_leftmost = col_idx == 0
                is_bottom = row_idx == len(self.recording_projects)
                self._draw_single_psth_panel(
                    axis=axis,
                    psth=one_panel,
                    metrics_row=one_metrics.iloc[0] if not one_metrics.empty else None,
                    response_kind=response_kind,
                    recording_label=project.recording_label,
                    show_ylabel=is_leftmost,
                    show_xlabel=is_bottom,
                )

        title_text = (
            "Train PSTHs Across Recordings: top wells from opsin and no opsin groups"
            if response_kind == "train_response"
            else "250 Pseudo-Trial PSTHs Across Recordings: pooled across the whole stimulation session"
        )
        fig.suptitle(title_text, fontsize=15)
        fig.savefig(output_path, dpi=200, bbox_inches="tight")
        plt.close(fig)

    def _draw_single_psth_panel(
        self,
        axis: plt.Axes,
        psth: pd.DataFrame,
        metrics_row: pd.Series | None,
        response_kind: str,
        recording_label: str,
        show_ylabel: bool,
        show_xlabel: bool,
    ) -> None:
        """Draw one PSTH panel using the same histogram language as the well figures."""
        if psth.empty:
            axis.text(0.5, 0.5, f"{recording_label}\nno data", ha="center", va="center", transform=axis.transAxes)
            axis.set_xticks([])
            axis.set_yticks([])
            return

        psth = psth.sort_values("bin_center_ms")
        x = psth["bin_center_ms"].to_numpy(dtype=float)
        y = psth["rate_hz"].to_numpy(dtype=float)
        bin_width = self._bin_width_from_centers(x)
        if response_kind == "train_response":
            axis.axvspan(0, 500, color="#f59e0b", alpha=0.12, linewidth=0)
            axis.bar(
                x,
                y,
                width=bin_width,
                color="#d1d5db",
                edgecolor="#9ca3af",
                linewidth=0.5,
                align="center",
            )
            axis.set_xlim(float(np.min(x) - bin_width / 2.0), float(np.max(x) + bin_width / 2.0))
        else:
            axis.axvspan(0, 5, color="#f59e0b", alpha=0.12, linewidth=0)
            axis.bar(
                x,
                y,
                width=bin_width,
                color="#dbeafe",
                edgecolor="#93c5fd",
                linewidth=0.45,
                align="center",
            )
            axis.set_xlim(float(np.min(x) - bin_width / 2.0), float(np.max(x) + bin_width / 2.0))
        axis.axvline(0, color="crimson", linestyle="--", linewidth=1.0)
        axis.set_title(recording_label, fontsize=10)
        if show_xlabel:
            axis.set_xlabel("ms from train onset" if response_kind == "train_response" else "ms from pulse onset")
        else:
            axis.set_xlabel("")
        if show_ylabel:
            axis.set_ylabel("rate (Hz)")
        else:
            axis.set_ylabel("")
        axis.grid(True, alpha=0.2)
        axis.set_facecolor("white")
        if metrics_row is not None:
            pre_rate = float(metrics_row["pre_stim_mean_rate_hz"])
            peak_rate = float(metrics_row["peak_post_stim_rate_hz"])
            peak_time = float(metrics_row["peak_post_time_ms"])
            axis.text(
                0.985,
                0.96,
                f"pre {pre_rate:.1f} Hz\npeak {peak_rate:.1f} Hz @ {peak_time:.1f} ms",
                ha="right",
                va="top",
                transform=axis.transAxes,
                fontsize=8,
                color="#1f2937",
                bbox={"boxstyle": "round,pad=0.22", "facecolor": "white", "edgecolor": "#d1d5db", "alpha": 0.9},
            )

    def _draw_rate_raincloud(self, metrics_long: pd.DataFrame, output_path: Path) -> None:
        """Draw a raincloud-style comparison of pre and post rates pooled across recordings."""
        if metrics_long.empty:
            return

        order = [
            ("opsin", "pre_stim_mean_rate_hz"),
            ("opsin", "peak_post_stim_rate_hz"),
            ("no_opsin", "pre_stim_mean_rate_hz"),
            ("no_opsin", "peak_post_stim_rate_hz"),
        ]
        positions = [0.0, 1.0, 3.0, 4.0]
        plot_data = metrics_long.loc[
            metrics_long["group"].isin([group for group, _ in order])
            & metrics_long["rate_period"].isin([rate_period for _, rate_period in order])
        ].copy()
        fig, ax = plt.subplots(figsize=(8.8, 7.2), constrained_layout=True)
        point_x_map = self._paired_point_x_positions(plot_data, positions)
        self._draw_pair_connectors(ax, plot_data, point_x_map)

        for idx, ((group_name, rate_period), position) in enumerate(zip(order, positions, strict=True)):
            one = plot_data.loc[
                (plot_data["group"] == group_name) & (plot_data["rate_period"] == rate_period)
            ].copy()
            if one.empty:
                continue
            color = PAIR_COLORS[(group_name, rate_period)]
            values = one["firing_rate_hz"].astype(float).to_numpy()
            self._draw_vertical_half_violin(ax, values, center=position, color=color)
            self._draw_vertical_rain(
                ax,
                values=values,
                center=position,
                color=color,
                x_positions=one["pair_x_position"].to_numpy(dtype=float) if "pair_x_position" in one.columns else None,
            )
            self._draw_vertical_box(ax, values, center=position, color=color)

        ax.set_xticks(positions)
        ax.set_xticklabels(["Pre-stim", "Post-stim peak", "Pre-stim", "Post-stim peak"])
        ax.set_ylabel("firing rate (Hz)")
        ax.set_xlabel("")
        ax.set_title(
            "Top-2 Wells Per Group Across 6 Recordings\n250 pseudo-trial rates; each point = one well x one recording, pairs with prestim baseline < 1 Hz removed",
            fontsize=14,
        )
        ax.text(
            0.5,
            1.02,
            GROUP_DISPLAY_LABELS["opsin"],
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=11,
            color="#1e3a8a",
            fontweight="bold",
        )
        ax.text(
            3.5,
            1.02,
            GROUP_DISPLAY_LABELS["no_opsin"],
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=11,
            color="#475569",
            fontweight="bold",
        )
        ax.axvline(2.0, color="#e5e7eb", linewidth=1.0)
        ax.grid(axis="y", alpha=0.22)
        ax.set_axisbelow(True)
        self._style_spines(ax)
        fig.savefig(output_path, dpi=220, bbox_inches="tight")
        plt.close(fig)

    def _draw_pulse_delay_raincloud(self, metrics_long: pd.DataFrame, output_path: Path) -> None:
        """Draw paired pre/post pulse-aligned spike-delay summaries by method and group."""
        if metrics_long.empty:
            return

        order = [
            ("opsin", "pre_pulse_delay_ms_summary"),
            ("opsin", "post_pulse_delay_ms_summary"),
            ("no_opsin", "pre_pulse_delay_ms_summary"),
            ("no_opsin", "post_pulse_delay_ms_summary"),
        ]
        positions = [0.0, 1.0, 3.0, 4.0]
        method_order = [
            "separate_trial_median",
            "separate_trial_mean",
            "matched_trial_median",
            "matched_trial_mean",
        ]
        present_methods = [method for method in method_order if method in metrics_long["method"].unique()]
        nrows = len(present_methods)
        fig, axes = plt.subplots(
            nrows,
            1,
            figsize=(8.8, 4.2 * nrows),
            constrained_layout=True,
            squeeze=False,
            sharex=False,
        )

        for axis, method_name in zip(axes.ravel(), present_methods, strict=True):
            panel = metrics_long.loc[metrics_long["method"] == method_name].copy()
            point_x_map = self._paired_point_x_positions_generic(
                plot_data=panel,
                positions=positions,
                period_column="delay_period",
                period_order=["pre_pulse_delay_ms_summary", "post_pulse_delay_ms_summary"],
            )
            self._draw_pair_connectors_generic(
                axis=axis,
                plot_data=panel,
                point_x_map=point_x_map,
                period_column="delay_period",
                value_column="spike_delay_ms",
                pre_period="pre_pulse_delay_ms_summary",
                post_period="post_pulse_delay_ms_summary",
            )

            for (group_name, period_name), position in zip(order, positions, strict=True):
                one = panel.loc[
                    (panel["group"] == group_name)
                    & (panel["delay_period"] == period_name)
                ].copy()
                if one.empty:
                    continue
                values = one["spike_delay_ms"].astype(float).to_numpy()
                color = PAIR_COLORS[(
                    group_name,
                    "pre_stim_mean_rate_hz" if period_name == "pre_pulse_delay_ms_summary" else "peak_post_stim_rate_hz",
                )]
                self._draw_vertical_half_violin(axis, values, center=position, color=color)
                self._draw_vertical_rain(
                    axis,
                    values=values,
                    center=position,
                    color=color,
                    x_positions=one["pair_x_position"].to_numpy(dtype=float) if "pair_x_position" in one.columns else None,
                )
                self._draw_vertical_box(axis, values, center=position, color=color)

            axis.set_xticks(positions)
            axis.set_xticklabels(["Pre-pulse", "Post-pulse", "Pre-pulse", "Post-pulse"])
            axis.set_ylabel("spike delay from pulse onset (ms)")
            axis.set_xlabel("")
            axis.set_title(INSTANTANEOUS_METHOD_DISPLAY_LABELS[method_name], fontsize=13, pad=10)
            axis.text(
                0.20,
                1.005,
                GROUP_DISPLAY_LABELS["opsin"],
                transform=axis.transAxes,
                ha="center",
                va="bottom",
                fontsize=10.5,
                color="#1e3a8a",
                fontweight="bold",
            )
            axis.text(
                0.80,
                1.005,
                GROUP_DISPLAY_LABELS["no_opsin"],
                transform=axis.transAxes,
                ha="center",
                va="bottom",
                fontsize=10.5,
                color="#475569",
                fontweight="bold",
            )
            axis.axvline(2.0, color="#e5e7eb", linewidth=1.0)
            axis.grid(axis="y", alpha=0.22)
            axis.set_axisbelow(True)
            self._style_spines(axis)

            matched_counts = panel["matched_pulse_trial_count"].dropna().astype(int)
            pre_counts = panel["pre_pulse_trial_count"].dropna().astype(int)
            post_counts = panel["post_pulse_trial_count"].dropna().astype(int)
            note = f"delays < {INSTANTANEOUS_MIN_DELAY_MS:.1f} ms removed"
            if method_name.startswith("matched_trial"):
                note += f"; matched pulse trials per point median={int(np.median(matched_counts)) if not matched_counts.empty else 0}"
            else:
                note += (
                    f"; pre count median={int(np.median(pre_counts)) if not pre_counts.empty else 0},"
                    f" post count median={int(np.median(post_counts)) if not post_counts.empty else 0}"
                )
            axis.text(
                0.01,
                0.98,
                note,
                transform=axis.transAxes,
                ha="left",
                va="top",
                fontsize=8,
                bbox={"facecolor": "white", "alpha": 0.82, "edgecolor": "none", "pad": 2.0},
            )

        fig.suptitle(
            "Top-2 Wells Per Group Across 6 Recordings\n"
            "Pulse-aligned spike delay summary: lower post-pulse values mean faster stimulus-locked spiking; "
            "pre = nearest pre-pulse spike, post = first post-stim spike",
            fontsize=15,
        )
        fig.savefig(output_path, dpi=220, bbox_inches="tight")
        plt.close(fig)

    def _paired_point_x_positions_generic(
        self,
        plot_data: pd.DataFrame,
        positions: list[float],
        period_column: str,
        period_order: list[str],
    ) -> dict[tuple[str, str, str], float]:
        """Assign one stable horizontal offset per well/recording pair and period."""
        group_order = ["opsin", "no_opsin"]
        position_map: dict[tuple[str, str], float] = {}
        idx = 0
        for group_name in group_order:
            for period_name in period_order:
                position_map[(group_name, period_name)] = positions[idx]
                idx += 1
        pair_frame = (
            plot_data[
                ["group", "well", "recording_index", "recording_label", period_column]
            ]
            .drop_duplicates()
            .sort_values(["group", "well", "recording_index", period_column])
        )
        rng = np.random.default_rng(20260622)
        point_x_map: dict[tuple[str, str, str], float] = {}
        for group_name, pair_rows in pair_frame.groupby("group", sort=True):
            pairs = (
                pair_rows[["well", "recording_index", "recording_label"]]
                .drop_duplicates()
                .sort_values(["well", "recording_index"])
                .itertuples(index=False, name=None)
            )
            for well_name, recording_index, _recording_label in pairs:
                x_offset = rng.uniform(-0.055, 0.055)
                for period_name in period_order:
                    center = position_map[(group_name, period_name)]
                    point_x_map[(well_name, str(recording_index), period_name)] = center - 0.10 + x_offset
        plot_data["pair_x_position"] = plot_data.apply(
            lambda row: point_x_map[(str(row["well"]), str(row["recording_index"]), str(row[period_column]))],
            axis=1,
        )
        return point_x_map

    def _paired_point_x_positions(self, plot_data: pd.DataFrame, positions: list[float]) -> dict[tuple[str, str, str], float]:
        """Assign one stable horizontal offset per well/recording pair and period."""
        return self._paired_point_x_positions_generic(
            plot_data=plot_data,
            positions=positions,
            period_column="rate_period",
            period_order=["pre_stim_mean_rate_hz", "peak_post_stim_rate_hz"],
        )

    def _draw_pair_connectors(
        self,
        axis: plt.Axes,
        plot_data: pd.DataFrame,
        point_x_map: dict[tuple[str, str, str], float],
    ) -> None:
        """Connect each pre/post pair with a faint line."""
        self._draw_pair_connectors_generic(
            axis=axis,
            plot_data=plot_data,
            point_x_map=point_x_map,
            period_column="rate_period",
            value_column="firing_rate_hz",
            pre_period="pre_stim_mean_rate_hz",
            post_period="peak_post_stim_rate_hz",
        )

    def _draw_pair_connectors_generic(
        self,
        axis: plt.Axes,
        plot_data: pd.DataFrame,
        point_x_map: dict[tuple[str, str, str], float],
        period_column: str,
        value_column: str,
        pre_period: str,
        post_period: str,
    ) -> None:
        """Connect each pre/post pair with a faint line for any paired metric."""
        wide = (
            plot_data.pivot_table(
                index=["group", "well", "recording_index"],
                columns=period_column,
                values=value_column,
                aggfunc="first",
            )
            .reset_index()
        )
        for _, row in wide.iterrows():
            group_name = str(row["group"])
            well_name = str(row["well"])
            recording_index = str(row["recording_index"])
            pre_value = row.get(pre_period)
            peak_value = row.get(post_period)
            if pd.isna(pre_value) or pd.isna(peak_value):
                continue
            x_pre = point_x_map[(well_name, recording_index, pre_period)]
            x_peak = point_x_map[(well_name, recording_index, post_period)]
            axis.plot(
                [x_pre, x_peak],
                [float(pre_value), float(peak_value)],
                color=GROUP_COLORS[group_name],
                alpha=0.28,
                linewidth=1.0,
                zorder=2,
            )

    @staticmethod
    def _draw_vertical_half_violin(axis: plt.Axes, values: np.ndarray, center: float, color: str) -> None:
        """Draw an upward half violin for a vertical raincloud layout."""
        values = values[np.isfinite(values)]
        if values.size == 0:
            return
        if values.size == 1 or np.allclose(values, values[0]):
            y = np.array([values[0] - 0.25, values[0], values[0] + 0.25])
            density = np.array([0.0, 1.0, 0.0])
        else:
            kde = gaussian_kde(values)
            y = np.linspace(values.min(), values.max(), 256)
            density = kde(y)
            if np.max(density) > 0:
                density = density / np.max(density)
        width = 0.26
        x = center + density * width
        axis.fill_betweenx(y, center, x, color=color, alpha=0.28, linewidth=0)
        axis.plot(x, y, color=color, linewidth=1.1, alpha=0.9)

    @staticmethod
    def _draw_vertical_rain(
        axis: plt.Axes,
        values: np.ndarray,
        center: float,
        color: str,
        x_positions: np.ndarray | None = None,
    ) -> None:
        """Draw jittered raw points beside the vertical half violin."""
        values = values[np.isfinite(values)]
        if values.size == 0:
            return
        if x_positions is None:
            rng = np.random.default_rng(42 + int(round(center * 10)))
            x = center - 0.12 + rng.uniform(0.0, 0.10, size=values.size)
        else:
            x = np.asarray(x_positions, dtype=float)
        axis.scatter(
            x,
            values,
            s=24,
            color=color,
            alpha=0.55,
            linewidths=0.35,
            edgecolors="white",
            zorder=3,
        )

    @staticmethod
    def _draw_vertical_box(axis: plt.Axes, values: np.ndarray, center: float, color: str) -> None:
        """Draw a compact vertical boxplot slightly shifted from the density."""
        values = values[np.isfinite(values)]
        if values.size == 0:
            return
        axis.boxplot(
            [values],
            vert=True,
            positions=[center + 0.08],
            widths=0.14,
            manage_ticks=False,
            showfliers=False,
            showcaps=False,
            patch_artist=True,
            boxprops={"facecolor": "white", "edgecolor": color, "linewidth": 1.2},
            medianprops={"color": "#111827", "linewidth": 1.4},
            whiskerprops={"color": color, "linewidth": 1.1},
        )

    @staticmethod
    def _style_spines(axis: plt.Axes) -> None:
        """Apply a clean axis style used across summary figures."""
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)

    @staticmethod
    def _bin_width_from_centers(centers: np.ndarray) -> float:
        """Recover the histogram bin width from monotonically increasing centers."""
        if centers.size == 0:
            return 1.0
        if centers.size == 1:
            return 1.0
        return float(np.median(np.diff(centers)))

    @staticmethod
    def _classify_group(value: object) -> str | None:
        """Match the same treatment semantics used in the per-recording workflow."""
        if pd.isna(value):
            return None
        normalized = str(value).strip().lower().replace("_", " ")
        if not normalized:
            return None
        if "no opsin" in normalized:
            return "no_opsin"
        if "opsin" in normalized:
            return "opsin"
        return None
