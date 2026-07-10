#!/usr/bin/env python3
"""Audit dorsal organoid points with high smoothed inverse-ISI maxima."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d


JOB_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_RUN = JOB_ROOT / "cytoview_dv_sua_spontaneous_activity_20260710_20260710_055705"
DEFAULT_SOURCE = JOB_ROOT / "cytoview_dorsal_ventral_step1_20260709_unit_metrics.csv"
DEFAULT_WAVEFORMS = (
    JOB_ROOT
    / "waveform_alignment_feature_audit_20260709_cytoview"
    / "waveform_alignment_feature_audit_20260709_waveform_traces.csv.gz"
)
WELL_METRIC = "mean_unit_inverse_isi_gaussian_temporal_max_hz"
UNIT_METRIC = "inverse_isi_gaussian_temporal_max_hz"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--source-unit-metrics", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--waveform-traces", type=Path, default=DEFAULT_WAVEFORMS)
    parser.add_argument("--threshold-hz", type=float, default=40.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    units = pd.read_csv(run_dir / "cytoview_dv_sua_spontaneous_activity_20260710_unit_metrics.csv")
    wells = pd.read_csv(
        run_dir / "cytoview_dv_sua_spontaneous_activity_20260710_recording_well_summary.csv"
    )
    source = pd.read_csv(args.source_unit_metrics.expanduser().resolve())
    high_wells = wells.loc[
        wells["region_call"].eq("dorsal") & wells[WELL_METRIC].gt(args.threshold_hz)
    ].copy()
    if high_wells.empty:
        raise SystemExit(f"No dorsal recording/well points exceed {args.threshold_hz:g} Hz")

    source_columns = [
        "recording",
        "well",
        "unit_id",
        "ContamPct",
        "Amplitude",
        "isi_median_ms",
        "isi_mean_ms",
        "isi_cv",
        "isi_lt_2ms_count",
        "isi_lt_2ms_fraction",
        "best_channel_index",
        "template_ptp_best_channel_uV",
        "template_trough_best_channel_uV",
        "template_peak_best_channel_uV",
    ]
    selected = units.loc[units["recording_well_id"].isin(high_wells["recording_well_id"])].copy()
    selected = selected.merge(
        source[source_columns],
        on=["recording", "well", "unit_id"],
        how="left",
        validate="one_to_one",
    )

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import spikeinterface.full as si

    diagnostic_rows: list[dict[str, object]] = []
    spike_times_by_unit_key: dict[str, np.ndarray] = {}
    for analyzer_path_text, group in selected.groupby("analyzer_path", sort=False):
        analyzer = si.load_sorting_analyzer(Path(str(analyzer_path_text)), load_extensions=True)
        sorting = analyzer.sorting
        sampling_frequency = float(analyzer.recording.get_sampling_frequency())
        duration_s = float(analyzer.recording.get_total_duration())
        unit_id_map = {_unit_id_text(unit_id): unit_id for unit_id in sorting.get_unit_ids()}
        noise_mad_uV = si.get_noise_levels(
            analyzer.recording,
            return_in_uV=True,
            method="mad",
        )
        local_spikes: dict[str, np.ndarray] = {}
        for _, row in group.iterrows():
            unit_id = unit_id_map[_unit_id_text(row["unit_id"])]
            spike_times_s = (
                np.asarray(sorting.get_unit_spike_train(unit_id), dtype=float) / sampling_frequency
            )
            local_spikes[str(row["unit_key"])] = spike_times_s
            spike_times_by_unit_key[str(row["unit_key"])] = spike_times_s

        for _, row in group.iterrows():
            unit_key = str(row["unit_key"])
            spike_times_s = local_spikes[unit_key]
            eligible = bool(row["inverse_isi_gaussian_eligible"])
            peak_hz = np.nan
            peak_time_s = np.nan
            temporal_p999_hz = np.nan
            temporal_p99_hz = np.nan
            max_after_2ms_cleanup_hz = np.nan
            refractory_spikes_removed = 0
            relative_spikes_ms = np.asarray([], dtype=float)
            local_coincident_count = 0
            if eligible:
                time_s, smoothed_hz = _smoothed_inverse_isi_trace(
                    spike_times_s,
                    duration_s,
                    sigma_ms=float(row["inverse_isi_gaussian_sigma_ms"]),
                    bin_ms=float(row["inverse_isi_gaussian_evaluation_bin_ms"]),
                )
                peak_index = int(np.argmax(smoothed_hz))
                peak_hz = float(smoothed_hz[peak_index])
                peak_time_s = float(time_s[peak_index])
                temporal_p999_hz = float(np.percentile(smoothed_hz, 99.9))
                temporal_p99_hz = float(np.percentile(smoothed_hz, 99.0))
                cleaned_spike_times_s = _remove_refractory_violations(spike_times_s)
                refractory_spikes_removed = int(spike_times_s.size - cleaned_spike_times_s.size)
                _, cleaned_smoothed_hz = _smoothed_inverse_isi_trace(
                    cleaned_spike_times_s,
                    duration_s,
                    sigma_ms=float(row["inverse_isi_gaussian_sigma_ms"]),
                    bin_ms=float(row["inverse_isi_gaussian_evaluation_bin_ms"]),
                )
                max_after_2ms_cleanup_hz = float(np.max(cleaned_smoothed_hz))
                relative_spikes_ms = (
                    spike_times_s[np.abs(spike_times_s - peak_time_s) <= 0.1] - peak_time_s
                ) * 1000.0
                for spike_time_s in spike_times_s[np.abs(spike_times_s - peak_time_s) <= 0.1]:
                    if any(
                        np.any(np.abs(other_spikes - spike_time_s) <= 0.002)
                        for other_key, other_spikes in local_spikes.items()
                        if other_key != unit_key
                    ):
                        local_coincident_count += 1

            channel_index = int(row["best_channel_index"])
            noise_uV = float(noise_mad_uV[channel_index])
            ptp_uV = float(row["template_ptp_best_channel_uV"])
            ptp_over_noise = ptp_uV / noise_uV if noise_uV > 0 else np.nan
            weak_template = bool(np.isfinite(ptp_over_noise) and ptp_over_noise < 4.0)
            high_contamination = bool(float(row["ContamPct"]) > 10.0)
            refractory_concern = bool(float(row["isi_lt_2ms_fraction"]) > 0.01)
            flags = []
            if weak_template:
                flags.append("PTP/noise<4")
            if high_contamination:
                flags.append("ContamPct>10")
            if refractory_concern:
                flags.append(">1% ISI<2ms")
            diagnostic_rows.append(
                row.to_dict()
                | {
                    "noise_mad_uV_best_channel": noise_uV,
                    "template_ptp_over_noise_mad": ptp_over_noise,
                    "smoothed_rate_peak_hz_verified": peak_hz,
                    "smoothed_rate_peak_time_s": peak_time_s,
                    "smoothed_rate_temporal_p99_9_hz": temporal_p999_hz,
                    "smoothed_rate_temporal_p99_hz": temporal_p99_hz,
                    "smoothed_rate_max_after_2ms_cleanup_hz": max_after_2ms_cleanup_hz,
                    "refractory_spikes_removed_for_sensitivity": refractory_spikes_removed,
                    "spikes_within_peak_plus_minus_100ms": int(relative_spikes_ms.size),
                    "relative_spike_times_within_peak_plus_minus_100ms": " ".join(
                        f"{value:.2f}" for value in relative_spikes_ms
                    ),
                    "peak_window_spikes_coincident_with_other_unit_plus_minus_2ms": int(
                        local_coincident_count
                    ),
                    "weak_template_proxy_flag": weak_template,
                    "high_contamination_flag": high_contamination,
                    "refractory_violation_flag": refractory_concern,
                    "diagnostic_flags": "; ".join(flags) if flags else "none",
                }
            )

    diagnostics = pd.DataFrame(diagnostic_rows).sort_values(
        ["well", "raw_variant", UNIT_METRIC], ascending=[True, True, False]
    )
    waveforms = pd.read_csv(args.waveform_traces.expanduser().resolve())
    waveforms = waveforms.loc[waveforms["unit_key"].isin(diagnostics["unit_key"])].copy()

    high_wells["unique_well_note"] = high_wells["well"].map(
        high_wells["well"].value_counts()
    ).map(lambda count: "appears in multiple processing versions" if count > 1 else "single processing version")
    high_wells.to_csv(output_dir / "dorsal_high_max_recording_well_points.csv", index=False)
    diagnostics.to_csv(output_dir / "dorsal_high_max_unit_diagnostics.csv", index=False)
    sensitivity = _sensitivity_summary(diagnostics, high_wells)
    sensitivity.to_csv(output_dir / "dorsal_high_max_sensitivity_summary.csv", index=False)
    _plot_diagnostics(plt, high_wells, diagnostics, waveforms, output_dir)
    _plot_sensitivity(plt, sensitivity, output_dir)

    print(f"High plotted recording/well points: {len(high_wells)}")
    print(f"Unique wells: {high_wells['well'].nunique()}")
    print(f"Units audited: {len(diagnostics)}")
    print(f"Units with any diagnostic flag: {(diagnostics['diagnostic_flags'] != 'none').sum()}")
    print(f"Output directory: {output_dir}")
    return 0


def _plot_diagnostics(plt, high_wells, diagnostics, waveforms, output_dir: Path) -> None:
    high_wells = high_wells.sort_values(WELL_METRIC, ascending=False).reset_index(drop=True)
    fig, axes = plt.subplots(len(high_wells), 4, figsize=(18.5, 4.0 * len(high_wells)))
    fig.patch.set_facecolor("white")
    if len(high_wells) == 1:
        axes = axes[np.newaxis, :]
    for row_index, (_, well_row) in enumerate(high_wells.iterrows()):
        group = diagnostics.loc[
            diagnostics["recording_well_id"].eq(well_row["recording_well_id"])
        ].sort_values(UNIT_METRIC, ascending=False)
        unit_labels = [f"u{_unit_id_text(value)}" for value in group["unit_id"]]
        flagged = group["diagnostic_flags"].ne("none").to_numpy()
        colors = np.where(flagged, "#D1495B", "#2A9D8F")

        ax = axes[row_index, 0]
        values = pd.to_numeric(group[UNIT_METRIC], errors="coerce").to_numpy(dtype=float)
        ax.bar(np.arange(len(group)), values, color=colors, alpha=0.9)
        ax.axhline(40.0, color="black", linestyle="--", linewidth=1)
        ax.set_xticks(np.arange(len(group)), unit_labels, rotation=45, ha="right")
        ax.set_ylabel("Temporal maximum (Hz)")
        ax.set_title("Unit contributions")

        ax = axes[row_index, 1]
        for unit_index, (_, unit_row) in enumerate(group.iterrows()):
            text = str(unit_row["relative_spike_times_within_peak_plus_minus_100ms"])
            relative = np.fromstring(text, sep=" ") if text and text != "nan" else np.asarray([])
            ax.vlines(relative, unit_index - 0.34, unit_index + 0.34, color=colors[unit_index], linewidth=1.1)
        ax.axvline(0.0, color="black", linewidth=0.8, alpha=0.6)
        ax.set_xlim(-100, 100)
        ax.set_yticks(np.arange(len(group)), unit_labels)
        ax.set_xlabel("Time from each unit's own rate maximum (ms)")
        ax.set_title("Spikes producing each maximum")

        ax = axes[row_index, 2]
        x = pd.to_numeric(group["template_ptp_over_noise_mad"], errors="coerce")
        y = 100.0 * pd.to_numeric(group["isi_lt_2ms_fraction"], errors="coerce")
        ax.scatter(x, y, c=colors, s=55, edgecolor="white", linewidth=0.7)
        for label, x_value, y_value in zip(unit_labels, x, y, strict=True):
            ax.annotate(label, (x_value, y_value), xytext=(3, 3), textcoords="offset points", fontsize=8)
        ax.axvline(4.0, color="#777777", linestyle="--", linewidth=1)
        ax.axhline(1.0, color="#777777", linestyle="--", linewidth=1)
        ax.set_xlabel("Template PTP / channel-noise MAD")
        ax.set_ylabel("ISIs <2 ms (%)")
        ax.set_title("Isolation/noise diagnostics")

        ax = axes[row_index, 3]
        for unit_index, (_, unit_row) in enumerate(group.iterrows()):
            trace = waveforms.loc[waveforms["unit_key"].eq(unit_row["unit_key"])].sort_values("time_ms")
            if trace.empty:
                continue
            values = trace["after_aligned_average_uV"].to_numpy(dtype=float)
            scale = np.max(np.abs(values))
            if scale <= 0 or not np.isfinite(scale):
                continue
            ax.plot(
                trace["time_ms"],
                values / scale,
                color=colors[unit_index],
                alpha=0.78,
                linewidth=1.1,
                label=unit_labels[unit_index],
            )
        ax.axvline(0.0, color="black", linewidth=0.7, alpha=0.5)
        ax.set_xlabel("Time from aligned trough (ms)")
        ax.set_ylabel("Normalized waveform")
        ax.set_title("Aligned waveform shapes")
        ax.legend(frameon=False, fontsize=7, ncol=2, loc="best")

        row_title = (
            f"{well_row['well']} | {well_row['raw_variant']} | plotted organoid value "
            f"{well_row[WELL_METRIC]:.1f} Hz | {len(group)} SUA units"
        )
        axes[row_index, 0].text(
            0.0,
            1.25,
            row_title,
            transform=axes[row_index, 0].transAxes,
            fontsize=12,
            fontweight="bold",
            va="bottom",
        )
        for ax in axes[row_index]:
            ax.grid(axis="y", color="#E0E0E0", linewidth=0.7, alpha=0.8)
            ax.spines[["top", "right"]].set_visible(False)

    fig.suptitle(
        "Dorsal recording/well points with smoothed inverse-ISI temporal maximum >40 Hz",
        fontsize=16,
        fontweight="bold",
        y=0.997,
    )
    fig.text(
        0.5,
        0.978,
        (
            "Red is a diagnostic concern (PTP/noise MAD <4, ContamPct >10%, or >1% of ISIs <2 ms); "
            "flags are screening aids, not automatic exclusions"
        ),
        ha="center",
        va="top",
        fontsize=9,
    )
    fig.tight_layout(rect=(0.02, 0.02, 0.99, 0.955), h_pad=3.0, w_pad=2.0)
    base = output_dir / "dorsal_high_max_diagnostic_figure"
    fig.savefig(base.with_suffix(".png"), dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    fig.savefig(base.with_suffix(".svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _smoothed_inverse_isi_trace(
    spike_times_s: np.ndarray,
    duration_s: float,
    *,
    sigma_ms: float,
    bin_ms: float,
) -> tuple[np.ndarray, np.ndarray]:
    intervals_s = np.diff(spike_times_s)
    if np.any(intervals_s <= 0):
        raise ValueError("Spike times must be strictly increasing")
    bin_s = bin_ms / 1000.0
    bin_count = int(np.ceil(duration_s / bin_s))
    time_s = (np.arange(bin_count, dtype=float) + 0.5) * bin_s
    time_s = np.minimum(time_s, np.nextafter(duration_s, 0.0))
    interval_indices = np.searchsorted(spike_times_s, time_s, side="right") - 1
    valid = (interval_indices >= 0) & (interval_indices < intervals_s.size)
    instantaneous_hz = np.zeros(bin_count, dtype=float)
    instantaneous_hz[valid] = 1.0 / intervals_s[interval_indices[valid]]
    smoothed_hz = gaussian_filter1d(
        instantaneous_hz,
        sigma=sigma_ms / bin_ms,
        mode="constant",
        cval=0.0,
        truncate=4.0,
    )
    return time_s, smoothed_hz


def _remove_refractory_violations(
    spike_times_s: np.ndarray,
    minimum_isi_s: float = 0.002,
) -> np.ndarray:
    keep = np.ones(spike_times_s.size, dtype=bool)
    previous_kept_spike_s = float(spike_times_s[0])
    for index in range(1, spike_times_s.size):
        if float(spike_times_s[index]) - previous_kept_spike_s < minimum_isi_s:
            keep[index] = False
        else:
            previous_kept_spike_s = float(spike_times_s[index])
    return spike_times_s[keep]


def _sensitivity_summary(diagnostics: pd.DataFrame, high_wells: pd.DataFrame) -> pd.DataFrame:
    eligible = diagnostics.loc[diagnostics["inverse_isi_gaussian_eligible"].astype(bool)].copy()
    summary = (
        eligible.groupby(["recording_well_id", "well", "raw_variant"], as_index=False)
        .agg(
            eligible_sua_units=("unit_id", "size"),
            refractory_spikes_removed=("refractory_spikes_removed_for_sensitivity", "sum"),
            absolute_max_mean_across_units_hz=("smoothed_rate_peak_hz_verified", "mean"),
            max_after_2ms_cleanup_mean_across_units_hz=(
                "smoothed_rate_max_after_2ms_cleanup_hz",
                "mean",
            ),
            temporal_p99_9_mean_across_units_hz=("smoothed_rate_temporal_p99_9_hz", "mean"),
            temporal_p99_mean_across_units_hz=("smoothed_rate_temporal_p99_hz", "mean"),
        )
    )
    return summary.merge(
        high_wells[["recording_well_id", WELL_METRIC]],
        on="recording_well_id",
        how="left",
        validate="one_to_one",
    ).sort_values("absolute_max_mean_across_units_hz", ascending=False)


def _plot_sensitivity(plt, sensitivity: pd.DataFrame, output_dir: Path) -> None:
    specs = [
        ("absolute_max_mean_across_units_hz", "Absolute maximum"),
        ("max_after_2ms_cleanup_mean_across_units_hz", "Maximum after\n<2-ms cleanup"),
        ("temporal_p99_9_mean_across_units_hz", "99.9th percentile"),
        ("temporal_p99_mean_across_units_hz", "99th percentile"),
    ]
    labels = [f"{row.well}\n{row.raw_variant}" for row in sensitivity.itertuples()]
    x = np.arange(len(sensitivity), dtype=float)
    width = 0.19
    fig, ax = plt.subplots(figsize=(11.2, 5.8))
    fig.patch.set_facecolor("white")
    colors = ["#D1495B", "#E9C46A", "#2A9D8F", "#457B9D"]
    for index, ((column, label), color) in enumerate(zip(specs, colors, strict=True)):
        offset = (index - 1.5) * width
        ax.bar(x + offset, sensitivity[column], width=width, label=label, color=color)
    ax.axhline(40.0, color="black", linestyle="--", linewidth=1, label="40-Hz screen")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Organoid-level rate summary (Hz)")
    ax.set_title(
        "Sensitivity of high dorsal points to refractory cleanup and percentile summaries",
        fontsize=13,
        fontweight="bold",
    )
    ax.grid(axis="y", color="#E0E0E0", linewidth=0.7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, 1.01))
    fig.text(
        0.5,
        0.01,
        "Sensitivity analysis only: the <2-ms cleanup and percentile summaries are not applied to the main figure.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0.02, 0.04, 0.99, 0.96))
    base = output_dir / "dorsal_high_max_sensitivity_figure"
    fig.savefig(base.with_suffix(".png"), dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    fig.savefig(base.with_suffix(".svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _unit_id_text(value: object) -> str:
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
