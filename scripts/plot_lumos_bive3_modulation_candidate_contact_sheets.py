#!/usr/bin/env python
"""Render manual-review contact sheets for eligible BiVe3 modulation candidates."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d

from scripts.build_lumos_all_units_unified_psth_store import DEFAULT_JOB_DIR


ANALYSIS_DIR = "lumos_gaussian_opto_modulation_development"
UNIT_STORE_DIR = "lumos_all_units_per_unit_psth_development"
UNIT_STORE_NAME = "lumos_all_units_per_unit_psth_development.h5"
WAVEFORM_DIR = "lumos_all_units_waveform_classification_pre_peak_development"
WAVEFORM_FILE = "all_unit_normalized_waveform_traces.csv"
OUTPUT_NAME = "FINAL FIGS"
THRESHOLD_HZ = 1.0
SIGMA_MS = 1.5
BASELINE_WINDOW_MS = (-20.0, -5.0)
RESPONSE_WINDOW_MS = (5.0, 25.0)
DISPLAY_WINDOW_MS = (-10.0, 45.0)
CLASS_COLORS = {"positive": "#D1495B", "negative": "#3568A8"}
POPULATION_CLASS_COLORS = {
    "positive": "#D1495B",
    "negative": "#3568A8",
    "non_modulated": "#59636F",
}
CONDITION_COLORS = {"opsin": "#D1495B", "no_opsin": "#4C78A8"}
CONDITION_LABELS = {"opsin": "BiVe3 Opsin", "no_opsin": "No Opsin"}
TARGET_LABELS = {
    "first_pulse_50": "P1 only · 50 trials",
    "all_pulses_250": "All pulses flattened · 250 trials",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metrics-csv",
        type=Path,
        default=DEFAULT_JOB_DIR / ANALYSIS_DIR / "unit_target_modulation_metrics.csv",
    )
    parser.add_argument(
        "--unit-store",
        type=Path,
        default=DEFAULT_JOB_DIR / UNIT_STORE_DIR / UNIT_STORE_NAME,
    )
    parser.add_argument(
        "--waveform-traces",
        type=Path,
        default=DEFAULT_JOB_DIR / WAVEFORM_DIR / WAVEFORM_FILE,
    )
    parser.add_argument(
        "--command-trace",
        type=Path,
        default=DEFAULT_JOB_DIR / ANALYSIS_DIR / "raw_stimulation_command_trace.csv",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_JOB_DIR.parents[1] / OUTPUT_NAME
    )
    parser.add_argument("--minimum-baseline-rate-hz", type=float, default=THRESHOLD_HZ)
    parser.add_argument("--rows-per-page", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    output_dir = args.output_dir.expanduser().resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    metrics = pd.read_csv(args.metrics_csv.expanduser().resolve())
    waveforms = pd.read_csv(args.waveform_traces.expanduser().resolve())
    command_trace = pd.read_csv(args.command_trace.expanduser().resolve())
    candidates = _eligible_candidates(metrics, args.minimum_baseline_rate_hz)
    payloads = _build_payloads(
        candidates,
        waveforms,
        command_trace,
        args.unit_store.expanduser().resolve(),
    )
    page_rows, candidate_rows = _render_contact_sheets(
        plt,
        PdfPages,
        payloads,
        staging_dir,
        rows_per_page=args.rows_per_page,
        minimum_baseline_rate_hz=args.minimum_baseline_rate_hz,
    )
    population_payloads = _build_population_payloads(
        metrics,
        args.unit_store.expanduser().resolve(),
        minimum_baseline_rate_hz=args.minimum_baseline_rate_hz,
    )
    population_output_dir = staging_dir / "Population Panels"
    population_output_dir.mkdir()
    (
        population_unit_psth_rows,
        population_summary_rows,
        raster_event_rows,
        raster_index_rows,
    ) = _render_population_figures(
        plt,
        population_payloads,
        population_output_dir,
        minimum_baseline_rate_hz=args.minimum_baseline_rate_hz,
    )
    condition_population_payloads = _build_condition_population_payloads(
        metrics,
        args.unit_store.expanduser().resolve(),
        minimum_baseline_rate_hz=args.minimum_baseline_rate_hz,
    )
    _render_condition_population_figures(
        plt,
        condition_population_payloads,
        population_output_dir,
        minimum_baseline_rate_hz=args.minimum_baseline_rate_hz,
    )
    candidate_table = pd.DataFrame(candidate_rows)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging_dir.replace(output_dir)
    print(f"Output: {output_dir}")
    print(
        candidate_table.groupby(["target", "modulation_class"])
        .size()
        .rename("candidates")
        .to_string()
    )
    print("Final representative selection: pending manual review")
    return 0


def _eligible_candidates(metrics: pd.DataFrame, minimum_baseline_rate_hz: float):
    required = {
        "condition",
        "baseline_mean_hz",
        "positive_unrestricted",
        "negative_unrestricted",
        "target",
        "observation_id",
        "hdf5_group",
    }
    missing = required - set(metrics.columns)
    if missing:
        raise ValueError(f"Metrics lack required columns: {sorted(missing)}")
    eligible = metrics.loc[
        metrics["condition"].eq("opsin")
        & metrics["baseline_mean_hz"].ge(minimum_baseline_rate_hz)
        & (metrics["positive_unrestricted"] | metrics["negative_unrestricted"])
    ].copy()
    eligible["modulation_class"] = np.where(
        eligible["positive_unrestricted"], "positive", "negative"
    )
    if eligible.duplicated(["target", "observation_id"]).any():
        raise ValueError("Candidate observation-target pairs must be unique")
    return eligible.sort_values(
        ["target", "modulation_class", "well", "observation_id"]
    )


def _build_payloads(candidates, waveforms, command_trace, unit_store_path):
    waveform_groups = {
        str(key): data.sort_values("aligned_time_ms")
        for key, data in waveforms.groupby("unit_observation_id", sort=False)
    }
    command_groups = {
        str(key): data.groupby("time_ms", as_index=False)["command_intensity"].mean()
        for key, data in command_trace.groupby("recording", sort=False)
    }
    payloads = []
    with h5py.File(unit_store_path, "r") as store:
        time_ms = store["axes/pulse_bin_centers_ms"][:]
        response_mask = _window_mask(time_ms, RESPONSE_WINDOW_MS)
        display_mask = _window_mask(time_ms, DISPLAY_WINDOW_MS)
        response_times = time_ms[response_mask]
        for metric in candidates.itertuples(index=False):
            observation_id = str(metric.observation_id)
            if observation_id not in waveform_groups:
                raise ValueError(f"No waveform trace for {observation_id}")
            group = store[str(metric.hdf5_group).lstrip("/")]
            pulse_counts = group["pulse_250/counts"][:].astype(int)
            counts = (
                pulse_counts.reshape(50, 5, -1)[:, 0, :]
                if metric.target == "first_pulse_50"
                else pulse_counts
            )
            rates = counts.astype(float) * 1000.0
            raw_psth = rates.mean(axis=0)
            gaussian_psth = gaussian_filter1d(
                rates,
                sigma=SIGMA_MS,
                axis=-1,
                mode="nearest",
                truncate=4.0,
            ).mean(axis=0)
            response_counts = counts[:, response_mask]
            response_hits = response_counts.sum(axis=1) > 0
            first_latencies = np.asarray(
                [
                    response_times[np.flatnonzero(row > 0)[0]]
                    for row in response_counts[response_hits]
                ],
                dtype=float,
            )
            same_bin = (response_counts > 0).sum(axis=0)
            waveform = waveform_groups[observation_id]
            recording = str(metric.recording)
            if recording not in command_groups:
                raise ValueError(f"No raw command trace for {recording}")
            payloads.append(
                {
                    "metric": metric,
                    "time_ms": time_ms,
                    "counts": counts,
                    "raw_psth": raw_psth,
                    "gaussian_psth": gaussian_psth,
                    "waveform_time_ms": waveform["aligned_time_ms"].to_numpy(float),
                    "waveform": waveform["normalized_waveform"].to_numpy(float),
                    "command": command_groups[recording],
                    "response_probability": float(response_hits.mean()),
                    "first_spike_latency_median_ms": float(np.median(first_latencies))
                    if len(first_latencies)
                    else np.nan,
                    "first_spike_jitter_sd_ms": float(first_latencies.std(ddof=1))
                    if len(first_latencies) > 1
                    else np.nan,
                    "maximum_same_bin_trial_n": int(same_bin.max()),
                    "displayed_spike_trial_n": int(
                        (counts[:, display_mask].sum(axis=1) > 0).sum()
                    ),
                }
            )
    return payloads


def _build_population_payloads(
    metrics,
    unit_store_path,
    *,
    minimum_baseline_rate_hz,
):
    eligible = metrics.loc[
        metrics["condition"].eq("opsin")
        & metrics["baseline_mean_hz"].ge(minimum_baseline_rate_hz)
    ].copy()
    eligible["modulation_class"] = np.select(
        [eligible["positive_unrestricted"], eligible["negative_unrestricted"]],
        ["positive", "negative"],
        default="non_modulated",
    )
    if eligible.duplicated(["target", "observation_id"]).any():
        raise ValueError("Eligible population observation-target pairs must be unique")
    payloads = []
    with h5py.File(unit_store_path, "r") as store:
        time_ms = store["axes/pulse_bin_centers_ms"][:]
        for target in TARGET_LABELS:
            for modulation_class in ["positive", "negative", "non_modulated"]:
                selected = eligible.loc[
                    eligible["target"].eq(target)
                    & eligible["modulation_class"].eq(modulation_class)
                ].sort_values(["well", "observation_id"])
                units = []
                for metric in selected.itertuples(index=False):
                    group = store[str(metric.hdf5_group).lstrip("/")]
                    pulse_counts = group["pulse_250/counts"][:].astype(int)
                    counts = (
                        pulse_counts.reshape(50, 5, -1)[:, 0, :]
                        if target == "first_pulse_50"
                        else pulse_counts
                    )
                    rates = counts.astype(float) * 1000.0
                    raw_psth = rates.mean(axis=0)
                    gaussian_psth = gaussian_filter1d(
                        rates,
                        sigma=SIGMA_MS,
                        axis=-1,
                        mode="nearest",
                        truncate=4.0,
                    ).mean(axis=0)
                    units.append(
                        {
                            "metric": metric,
                            "counts": counts,
                            "raw_psth": raw_psth,
                            "gaussian_psth": gaussian_psth,
                        }
                    )
                if not units:
                    raise ValueError(
                        f"No eligible units for {target} / {modulation_class}"
                    )
                payloads.append(
                    {
                        "target": target,
                        "modulation_class": modulation_class,
                        "time_ms": time_ms,
                        "units": units,
                    }
                )
    return payloads


def _build_condition_population_payloads(
    metrics,
    unit_store_path,
    *,
    minimum_baseline_rate_hz,
):
    eligible = metrics.loc[
        metrics["condition"].isin(CONDITION_LABELS)
        & metrics["baseline_mean_hz"].ge(minimum_baseline_rate_hz)
    ].copy()
    if eligible.duplicated(["target", "observation_id"]).any():
        raise ValueError("Condition population observation-target pairs must be unique")
    payloads = []
    with h5py.File(unit_store_path, "r") as store:
        time_ms = store["axes/pulse_bin_centers_ms"][:]
        for target in TARGET_LABELS:
            for condition in ["opsin", "no_opsin"]:
                selected = eligible.loc[
                    eligible["target"].eq(target)
                    & eligible["condition"].eq(condition)
                ].sort_values(["well", "observation_id"])
                units = []
                for metric in selected.itertuples(index=False):
                    group = store[str(metric.hdf5_group).lstrip("/")]
                    pulse_counts = group["pulse_250/counts"][:].astype(int)
                    counts = (
                        pulse_counts.reshape(50, 5, -1)[:, 0, :]
                        if target == "first_pulse_50"
                        else pulse_counts
                    )
                    rates = counts.astype(float) * 1000.0
                    units.append(
                        {
                            "metric": metric,
                            "counts": counts,
                            "raw_psth": rates.mean(axis=0),
                            "gaussian_psth": gaussian_filter1d(
                                rates,
                                sigma=SIGMA_MS,
                                axis=-1,
                                mode="nearest",
                                truncate=4.0,
                            ).mean(axis=0),
                        }
                    )
                if not units:
                    raise ValueError(f"No eligible units for {target} / {condition}")
                payloads.append(
                    {
                        "target": target,
                        "condition": condition,
                        "time_ms": time_ms,
                        "units": units,
                    }
                )
    return payloads


def _render_population_figures(
    plt,
    payloads,
    output_dir,
    *,
    minimum_baseline_rate_hz,
):
    unit_psth_rows = []
    summary_rows = []
    raster_event_rows = []
    raster_index_rows = []
    for target in TARGET_LABELS:
        target_payloads = [item for item in payloads if item["target"] == target]
        by_class = {item["modulation_class"]: item for item in target_payloads}
        summaries = {}
        for modulation_class, payload in by_class.items():
            raw_matrix = np.asarray(
                [unit["raw_psth"] for unit in payload["units"]], dtype=float
            )
            gaussian_matrix = np.asarray(
                [unit["gaussian_psth"] for unit in payload["units"]], dtype=float
            )
            summaries[modulation_class] = {
                "raw_mean": raw_matrix.mean(axis=0),
                "gaussian_mean": gaussian_matrix.mean(axis=0),
                "gaussian_sem": (
                    gaussian_matrix.std(axis=0, ddof=1)
                    / np.sqrt(len(gaussian_matrix))
                    if len(gaussian_matrix) > 1
                    else np.zeros(gaussian_matrix.shape[1], dtype=float)
                ),
            }
        psth_upper = max(
            float(
                np.max(
                    np.r_[
                        summary["raw_mean"],
                        summary["gaussian_mean"] + summary["gaussian_sem"],
                    ]
                )
            )
            for summary in summaries.values()
        )
        figure, axes = plt.subplots(
            2, 3, figsize=(16.2, 9.2), sharex="col", squeeze=False
        )
        for column, modulation_class in enumerate(
            ["positive", "negative", "non_modulated"]
        ):
            payload = by_class[modulation_class]
            units = payload["units"]
            time_ms = payload["time_ms"]
            display_mask = _window_mask(time_ms, DISPLAY_WINDOW_MS)
            raster_axis = axes[0, column]
            row_offset = 0
            previous_displayed_well = None
            all_trial_rows = 0
            for unit_order, unit in enumerate(units, start=1):
                metric = unit["metric"]
                counts = unit["counts"]
                all_trial_rows += len(counts)
                display_counts = counts[:, display_mask]
                displayed_trial_mask = display_counts.sum(axis=1) > 0
                displayed_counts = display_counts[displayed_trial_mask]
                original_trial_indices = np.flatnonzero(displayed_trial_mask)
                spike_trials, spike_bins = np.nonzero(displayed_counts > 0)
                global_rows = row_offset + spike_trials + 1
                spike_times = time_ms[display_mask][spike_bins]
                raster_axis.scatter(
                    spike_times,
                    global_rows,
                    s=1.2,
                    marker="|",
                    linewidths=0.22,
                    color="#111827",
                    rasterized=True,
                )
                if len(spike_times):
                    raster_event_rows.extend(
                        {
                            "target": target,
                            "modulation_class": modulation_class,
                            "well": metric.well,
                            "observation_id": metric.observation_id,
                            "unit_order": unit_order,
                            "unit_trial": int(original_trial_indices[trial] + 1),
                            "displayed_trial_within_unit": int(trial + 1),
                            "population_raster_row": int(global_row),
                            "time_ms_bin_center": float(time),
                        }
                        for trial, global_row, time in zip(
                            spike_trials, global_rows, spike_times, strict=True
                        )
                    )
                raster_index_rows.append(
                    {
                        "target": target,
                        "modulation_class": modulation_class,
                        "unit_order": unit_order,
                        "well": metric.well,
                        "observation_id": metric.observation_id,
                        "unit_id": metric.unit_id,
                        "KSLabel": metric.KSLabel,
                        "waveform_class": metric.waveform_class,
                        "total_trials": len(counts),
                        "displayed_spike_trials": len(displayed_counts),
                        "population_row_start": row_offset + 1
                        if len(displayed_counts)
                        else np.nan,
                        "population_row_end": row_offset + len(displayed_counts)
                        if len(displayed_counts)
                        else np.nan,
                    }
                )
                if (
                    len(displayed_counts)
                    and previous_displayed_well is not None
                    and metric.well != previous_displayed_well
                ):
                    raster_axis.axhline(
                        row_offset + 0.5, color="#111827", lw=0.55, alpha=0.65
                    )
                row_offset += len(displayed_counts)
                if len(displayed_counts):
                    raster_axis.axhline(
                        row_offset + 0.5, color="#6B7280", lw=0.18, alpha=0.35
                    )
                    previous_displayed_well = metric.well
                for bin_index, time in enumerate(time_ms):
                    unit_psth_rows.append(
                        {
                            "target": target,
                            "modulation_class": modulation_class,
                            "well": metric.well,
                            "observation_id": metric.observation_id,
                            "unit_order": unit_order,
                            "trials": len(counts),
                            "time_ms_bin_center": time,
                            "unit_raw_psth_hz": unit["raw_psth"][bin_index],
                            "unit_gaussian_psth_hz": unit["gaussian_psth"][
                                bin_index
                            ],
                        }
                    )
            _response_annotations(raster_axis)
            raster_axis.set_xlim(*DISPLAY_WINDOW_MS)
            raster_axis.set_ylim(max(row_offset, 1) + 0.5, 0.5)
            raster_axis.set_ylabel("Spike-containing unit trial")
            raster_axis.set_title(
                (
                    f"{modulation_class.replace('_', ' ').title()}\n"
                    f"{len(units)} units · {row_offset:,}/{all_trial_rows:,} trials shown"
                ),
                loc="left",
                fontsize=10,
                fontweight="bold",
                color=POPULATION_CLASS_COLORS[modulation_class],
            )
            _clean_axis(raster_axis)

            psth_axis = axes[1, column]
            summary = summaries[modulation_class]
            color = POPULATION_CLASS_COLORS[modulation_class]
            psth_axis.plot(
                time_ms,
                summary["raw_mean"],
                color="#111827",
                lw=0.9,
                alpha=0.7,
                label="Mean unit raw PSTH",
            )
            psth_axis.plot(
                time_ms,
                summary["gaussian_mean"],
                color=color,
                lw=1.7,
                label="Mean unit Gaussian PSTH",
            )
            psth_axis.fill_between(
                time_ms,
                summary["gaussian_mean"] - summary["gaussian_sem"],
                summary["gaussian_mean"] + summary["gaussian_sem"],
                color=color,
                alpha=0.18,
                lw=0,
                label="Unit SEM",
            )
            _response_annotations(psth_axis)
            psth_axis.set_xlim(*DISPLAY_WINDOW_MS)
            psth_axis.set_ylim(0, max(psth_upper * 1.08, 1.0))
            psth_axis.set_ylabel("Population firing rate (Hz)")
            psth_axis.set_xlabel("Time from exact pulse onset (ms)")
            psth_axis.set_title(
                f"Equal-weight mean of {len(units)} unit PSTHs",
                loc="left",
                fontsize=9,
            )
            _clean_axis(psth_axis)
            if column == 0:
                psth_axis.legend(frameon=False, fontsize=7.5, loc="upper left")
            for bin_index, time in enumerate(time_ms):
                summary_rows.append(
                    {
                        "target": target,
                        "modulation_class": modulation_class,
                        "units": len(units),
                        "all_unit_trial_rows": all_trial_rows,
                        "displayed_spike_trial_rows": row_offset,
                        "time_ms_bin_center": time,
                        "population_raw_psth_hz": summary["raw_mean"][bin_index],
                        "population_gaussian_psth_hz": summary["gaussian_mean"][
                            bin_index
                        ],
                        "population_gaussian_sem_hz": summary["gaussian_sem"][
                            bin_index
                        ],
                    }
                )
        figure.suptitle(
            f"BiVe3 Opsin full eligible population · {TARGET_LABELS[target]}",
            x=0.055,
            y=0.99,
            ha="left",
            fontsize=14,
            fontweight="bold",
        )
        figure.text(
            0.055,
            0.955,
            (
                f"Baseline ≥{minimum_baseline_rate_hz:g} Hz. Display −10 to +45 ms; raster shows only "
                "spike-containing trials grouped within unit. PSTH still uses all trials and equal unit weights."
            ),
            fontsize=8.5,
            color="#4B5563",
        )
        figure.subplots_adjust(
            left=0.065,
            right=0.99,
            bottom=0.075,
            top=0.89,
            wspace=0.22,
            hspace=0.20,
        )
        base_name = f"{target}_population_raster_psth_by_modulation_class"
        figure.savefig(
            output_dir / f"{base_name}.png",
            dpi=300,
            bbox_inches="tight",
            facecolor="white",
        )
        figure.savefig(
            output_dir / f"{base_name}.pdf",
            bbox_inches="tight",
            facecolor="white",
        )
        plt.close(figure)
    return unit_psth_rows, summary_rows, raster_event_rows, raster_index_rows


def _render_condition_population_figures(
    plt,
    payloads,
    output_dir,
    *,
    minimum_baseline_rate_hz,
):
    for target in TARGET_LABELS:
        by_condition = {
            item["condition"]: item
            for item in payloads
            if item["target"] == target
        }
        summaries = {}
        for condition, payload in by_condition.items():
            raw_matrix = np.asarray(
                [unit["raw_psth"] for unit in payload["units"]], dtype=float
            )
            gaussian_matrix = np.asarray(
                [unit["gaussian_psth"] for unit in payload["units"]], dtype=float
            )
            summaries[condition] = {
                "raw_mean": raw_matrix.mean(axis=0),
                "gaussian_mean": gaussian_matrix.mean(axis=0),
                "gaussian_sem": (
                    gaussian_matrix.std(axis=0, ddof=1)
                    / np.sqrt(len(gaussian_matrix))
                    if len(gaussian_matrix) > 1
                    else np.zeros(gaussian_matrix.shape[1], dtype=float)
                ),
            }
        psth_upper = max(
            float(
                np.max(
                    np.r_[
                        summary["raw_mean"],
                        summary["gaussian_mean"] + summary["gaussian_sem"],
                    ]
                )
            )
            for summary in summaries.values()
        )
        figure, axes = plt.subplots(
            2, 2, figsize=(12.0, 9.2), sharex="col", squeeze=False
        )
        for column, condition in enumerate(["opsin", "no_opsin"]):
            payload = by_condition[condition]
            units = payload["units"]
            time_ms = payload["time_ms"]
            display_mask = _window_mask(time_ms, DISPLAY_WINDOW_MS)
            raster_axis = axes[0, column]
            row_offset = 0
            all_trial_rows = 0
            previous_displayed_well = None
            for unit in units:
                counts = unit["counts"]
                metric = unit["metric"]
                all_trial_rows += len(counts)
                displayed_counts = counts[:, display_mask]
                displayed_counts = displayed_counts[
                    displayed_counts.sum(axis=1) > 0
                ]
                spike_trials, spike_bins = np.nonzero(displayed_counts > 0)
                raster_axis.scatter(
                    time_ms[display_mask][spike_bins],
                    row_offset + spike_trials + 1,
                    s=1.2,
                    marker="|",
                    linewidths=0.22,
                    color="#111827",
                    rasterized=True,
                )
                if (
                    len(displayed_counts)
                    and previous_displayed_well is not None
                    and metric.well != previous_displayed_well
                ):
                    raster_axis.axhline(
                        row_offset + 0.5, color="#111827", lw=0.55, alpha=0.65
                    )
                row_offset += len(displayed_counts)
                if len(displayed_counts):
                    raster_axis.axhline(
                        row_offset + 0.5,
                        color="#6B7280",
                        lw=0.18,
                        alpha=0.35,
                    )
                    previous_displayed_well = metric.well
            _response_annotations(raster_axis)
            raster_axis.set_xlim(*DISPLAY_WINDOW_MS)
            raster_axis.set_ylim(max(row_offset, 1) + 0.5, 0.5)
            raster_axis.set_ylabel("Spike-containing unit trial")
            raster_axis.set_title(
                (
                    f"{CONDITION_LABELS[condition]}\n"
                    f"{len(units)} units · {row_offset:,}/{all_trial_rows:,} trials shown"
                ),
                loc="left",
                fontsize=11,
                fontweight="bold",
                color=CONDITION_COLORS[condition],
            )
            _clean_axis(raster_axis)

            psth_axis = axes[1, column]
            summary = summaries[condition]
            color = CONDITION_COLORS[condition]
            psth_axis.plot(
                time_ms,
                summary["raw_mean"],
                color="#111827",
                lw=0.9,
                alpha=0.7,
                label="Mean unit raw PSTH",
            )
            psth_axis.plot(
                time_ms,
                summary["gaussian_mean"],
                color=color,
                lw=1.8,
                label="Mean unit Gaussian PSTH",
            )
            psth_axis.fill_between(
                time_ms,
                summary["gaussian_mean"] - summary["gaussian_sem"],
                summary["gaussian_mean"] + summary["gaussian_sem"],
                color=color,
                alpha=0.18,
                lw=0,
                label="Unit SEM",
            )
            _response_annotations(psth_axis)
            psth_axis.set_xlim(*DISPLAY_WINDOW_MS)
            psth_axis.set_ylim(0, max(psth_upper * 1.08, 1.0))
            psth_axis.set_ylabel("Population firing rate (Hz)")
            psth_axis.set_xlabel("Time from exact pulse onset (ms)")
            psth_axis.set_title(
                f"Equal-weight mean of {len(units)} unit PSTHs",
                loc="left",
                fontsize=9,
            )
            _clean_axis(psth_axis)
            if column == 0:
                psth_axis.legend(frameon=False, fontsize=7.5, loc="upper left")
        figure.suptitle(
            f"Full eligible population · Opsin versus No Opsin · {TARGET_LABELS[target]}",
            x=0.06,
            y=0.99,
            ha="left",
            fontsize=14,
            fontweight="bold",
        )
        figure.text(
            0.06,
            0.955,
            (
                f"Baseline ≥{minimum_baseline_rate_hz:g} Hz. Display −10 to +45 ms; raster shows only "
                "spike-containing trials. PSTH uses all trials and equal unit weights within condition."
            ),
            fontsize=8.5,
            color="#4B5563",
        )
        figure.subplots_adjust(
            left=0.08,
            right=0.99,
            bottom=0.075,
            top=0.89,
            wspace=0.22,
            hspace=0.20,
        )
        base_name = f"{target}_population_raster_psth_opsin_vs_no_opsin"
        figure.savefig(
            output_dir / f"{base_name}.png",
            dpi=300,
            bbox_inches="tight",
            facecolor="white",
        )
        figure.savefig(
            output_dir / f"{base_name}.pdf",
            bbox_inches="tight",
            facecolor="white",
        )
        plt.close(figure)


def _render_contact_sheets(
    plt,
    PdfPages,
    payloads,
    output_dir,
    *,
    rows_per_page,
    minimum_baseline_rate_hz,
):
    page_rows = []
    candidate_rows = []
    display_order = 0
    for target in TARGET_LABELS:
        for modulation_class in ["positive", "negative"]:
            class_payloads = [
                item
                for item in payloads
                if item["metric"].target == target
                and item["metric"].modulation_class == modulation_class
            ]
            if not class_payloads:
                continue
            limits = _class_limits(class_payloads)
            pdf_name = f"{target}_{modulation_class}_candidate_contact_sheet.pdf"
            with PdfPages(output_dir / pdf_name) as pdf:
                for well in sorted({item["metric"].well for item in class_payloads}):
                    well_payloads = [
                        item for item in class_payloads if item["metric"].well == well
                    ]
                    for page_in_well, start in enumerate(
                        range(0, len(well_payloads), rows_per_page), start=1
                    ):
                        chunk = well_payloads[start : start + rows_per_page]
                        figure = _plot_page(
                            plt,
                            chunk,
                            limits,
                            target=target,
                            modulation_class=modulation_class,
                            well=well,
                            page_in_well=page_in_well,
                            minimum_baseline_rate_hz=minimum_baseline_rate_hz,
                        )
                        pdf.savefig(figure, bbox_inches="tight", facecolor="white")
                        png_name = (
                            f"{target}_{modulation_class}_{well}_page_{page_in_well:02d}.png"
                        )
                        figure.savefig(
                            output_dir / png_name,
                            dpi=220,
                            bbox_inches="tight",
                            facecolor="white",
                        )
                        plt.close(figure)
                        page_rows.append(
                            {
                                "target": target,
                                "modulation_class": modulation_class,
                                "well": well,
                                "page_in_well": page_in_well,
                                "pdf": pdf_name,
                                "png": png_name,
                                "candidate_n": len(chunk),
                                "observation_ids": ";".join(
                                    str(item["metric"].observation_id) for item in chunk
                                ),
                            }
                        )
                        for item in chunk:
                            display_order += 1
                            metric = item["metric"]
                            candidate_rows.append(
                                {
                                    "display_order": display_order,
                                    "candidate_id": (
                                        f"{target}|{metric.observation_id}|{modulation_class}"
                                    ),
                                    "observation_id": metric.observation_id,
                                    "unit_id": metric.unit_id,
                                    "well": metric.well,
                                    "condition": "BiVe3 Opsin",
                                    "recording": metric.recording,
                                    "raw_variant": metric.raw_variant,
                                    "KSLabel": metric.KSLabel,
                                    "waveform_class": metric.waveform_class,
                                    "target": target,
                                    "modulation_class": modulation_class,
                                    "minimum_baseline_rate_hz": minimum_baseline_rate_hz,
                                    "baseline_firing_rate_hz": metric.baseline_mean_hz,
                                    "baseline_sem_hz": metric.baseline_sem_hz,
                                    "response_firing_rate_hz": metric.response_mean_hz,
                                    "modulation_magnitude_hz": metric.response_minus_baseline_hz,
                                    "modulation_index": metric.response_window_mean_omi,
                                    "response_probability": item["response_probability"],
                                    "modulation_latency_ms": metric.modulation_onset_ms,
                                    "first_spike_latency_median_ms": item[
                                        "first_spike_latency_median_ms"
                                    ],
                                    "first_spike_jitter_sd_ms": item[
                                        "first_spike_jitter_sd_ms"
                                    ],
                                    "maximum_same_bin_trial_n": item[
                                        "maximum_same_bin_trial_n"
                                    ],
                                    "raster_displayed_spike_trials": item[
                                        "displayed_spike_trial_n"
                                    ],
                                    "raster_total_trials": len(item["counts"]),
                                    "contact_sheet_pdf": pdf_name,
                                    "contact_sheet_png": png_name,
                                    "contact_sheet_display_reason": (
                                        "All eligible BiVe3 positive/negative observation-target "
                                        "pairs are displayed for manual visual review"
                                    ),
                                    "manual_review_status": "awaiting_user_selection",
                                    "manually_selected_illustrative_example": False,
                                    "final_representative_class": "",
                                    "final_manual_selection_reason": "",
                                    "quantitative_analysis_dependency": (
                                        "none; full-population analysis is independent of display choice"
                                    ),
                                }
                            )
    return page_rows, candidate_rows


def _class_limits(payloads):
    finite_waveforms = [
        item["waveform"][np.isfinite(item["waveform"])] for item in payloads
    ]
    if any(not len(values) for values in finite_waveforms):
        raise ValueError("Every candidate waveform must contain finite samples")
    wave_min = min(float(np.min(values)) for values in finite_waveforms)
    wave_max = max(float(np.max(values)) for values in finite_waveforms)
    wave_pad = max((wave_max - wave_min) * 0.08, 0.05)
    psth_max = max(
        float(np.max(np.r_[item["raw_psth"], item["gaussian_psth"]]))
        for item in payloads
    )
    command_max = max(float(item["command"]["command_intensity"].max()) for item in payloads)
    return {
        "wave_y": (wave_min - wave_pad, wave_max + wave_pad),
        "psth_y": (0.0, max(psth_max * 1.08, 1.0)),
        "command_y": (0.0, max(command_max * 1.08, 0.1)),
    }


def _plot_page(
    plt,
    payloads,
    limits,
    *,
    target,
    modulation_class,
    well,
    page_in_well,
    minimum_baseline_rate_hz,
):
    figure, axes = plt.subplots(
        len(payloads),
        3,
        figsize=(15.5, max(5.4, 2.65 * len(payloads) + 1.8)),
        squeeze=False,
    )
    color = CLASS_COLORS[modulation_class]
    for row, item in enumerate(payloads):
        metric = item["metric"]
        wave_axis, raster_axis, psth_axis = axes[row]
        wave_axis.plot(
            item["waveform_time_ms"], item["waveform"], color="#111827", lw=1.25
        )
        wave_axis.axvline(0, color="#9CA3AF", lw=0.6, ls=":")
        wave_axis.set_xlim(
            item["waveform_time_ms"].min(), item["waveform_time_ms"].max()
        )
        wave_axis.set_ylim(*limits["wave_y"])
        wave_axis.set_ylabel("Normalized amplitude")
        wave_axis.set_xlabel("Time from trough (ms)")
        wave_axis.set_title(
            f"{metric.observation_id} · u{metric.unit_id} · {metric.KSLabel} / {metric.waveform_class}",
            loc="left",
            fontsize=9,
            fontweight="bold",
        )
        _clean_axis(wave_axis)

        display_mask = _window_mask(item["time_ms"], DISPLAY_WINDOW_MS)
        display_counts = item["counts"][:, display_mask]
        displayed_trial_mask = display_counts.sum(axis=1) > 0
        displayed_counts = display_counts[displayed_trial_mask]
        spike_trials, spike_bins = np.nonzero(displayed_counts > 0)
        raster_axis.scatter(
            item["time_ms"][display_mask][spike_bins],
            spike_trials + 1,
            s=7,
            marker="|",
            linewidths=0.5,
            color="#111827",
        )
        _response_annotations(raster_axis)
        raster_axis.set_xlim(*DISPLAY_WINDOW_MS)
        raster_axis.set_ylim(max(len(displayed_counts), 1) + 0.5, 0.5)
        raster_axis.set_ylabel("Spike-containing trial")
        raster_axis.set_xlabel("Time from exact pulse onset (ms)")
        raster_axis.set_title(
            (
                f"Raster · {len(displayed_counts)}/{len(item['counts'])} trials with spikes"
            ),
            loc="left",
            fontsize=9,
        )
        if not len(displayed_counts):
            raster_axis.text(
                0.5,
                0.5,
                "No spike-containing trials",
                transform=raster_axis.transAxes,
                ha="center",
                va="center",
                fontsize=8,
                color="#6B7280",
            )
        _clean_axis(raster_axis)

        psth_axis.plot(
            item["time_ms"], item["raw_psth"], color="#111827", lw=0.9, label="Raw 1 ms"
        )
        psth_axis.plot(
            item["time_ms"],
            item["gaussian_psth"],
            color=color,
            lw=1.5,
            label="Gaussian σ=1.5 ms",
        )
        _response_annotations(psth_axis)
        psth_axis.set_xlim(*DISPLAY_WINDOW_MS)
        psth_axis.set_ylim(*limits["psth_y"])
        psth_axis.set_ylabel("Firing rate (Hz)")
        psth_axis.set_xlabel("Time from exact pulse onset (ms)")
        psth_axis.set_title(
            f"{modulation_class.replace('_', ' ').title()} · ΔFR={metric.response_minus_baseline_hz:.2f} Hz",
            loc="left",
            fontsize=9,
            fontweight="bold",
            color=color,
        )
        psth_axis.text(
            0.99,
            0.96,
            (
                f"P(resp)={item['response_probability']:.3f}  "
                f"OMI={metric.response_window_mean_omi:.2f}\n"
                f"onset={_format_ms(metric.modulation_onset_ms)}  "
                f"jitter={_format_ms(item['first_spike_jitter_sd_ms'])}"
            ),
            transform=psth_axis.transAxes,
            ha="right",
            va="top",
            fontsize=7.6,
            color="#374151",
        )
        command_axis = psth_axis.twinx()
        command_axis.plot(
            item["command"]["time_ms"],
            item["command"]["command_intensity"],
            color="#D97706",
            lw=0.9,
            alpha=0.8,
            drawstyle="steps-post",
        )
        command_axis.set_ylim(*limits["command_y"])
        command_axis.set_yticks([])
        command_axis.spines[["top", "right"]].set_visible(False)
        if row == 0:
            psth_axis.legend(frameon=False, fontsize=7, loc="upper left")
        _clean_axis(psth_axis)
    figure.suptitle(
        (
            f"BiVe3 Opsin candidate review · {TARGET_LABELS[target]} · "
            f"{modulation_class.title()} · well {well} · page {page_in_well}"
        ),
        x=0.055,
        y=0.985,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    figure.text(
        0.055,
        0.935,
        (
            f"Eligible baseline ≥{minimum_baseline_rate_hz:g} Hz. Gray: −20 to −5 ms baseline; "
            "orange: 5–25 ms response; yellow: exact 0–9.5 ms light command. Manual-review display only."
        ),
        fontsize=8,
        color="#4B5563",
    )
    axes_top = 0.82 if len(payloads) == 1 else 0.88 if len(payloads) == 2 else 0.91
    figure.subplots_adjust(
        left=0.06,
        right=0.99,
        bottom=0.07,
        top=axes_top,
        wspace=0.25,
        hspace=0.58,
    )
    return figure


def _response_annotations(axis):
    axis.axvspan(*BASELINE_WINDOW_MS, color="#9CA3AF", alpha=0.15, lw=0)
    axis.axvspan(*RESPONSE_WINDOW_MS, color="#F59E0B", alpha=0.09, lw=0)
    axis.axvspan(0.0, 9.5, color="#F2CF5B", alpha=0.16, lw=0)
    axis.axvline(0.0, color="#8A4B08", ls="--", lw=0.8)


def _clean_axis(axis):
    axis.spines[["top", "right"]].set_visible(False)
    axis.tick_params(labelsize=7.5)


def _window_mask(time_ms, window):
    return (time_ms >= window[0]) & (time_ms < window[1])


def _format_ms(value):
    return "NA" if not np.isfinite(value) else f"{value:.1f} ms"


def _readme(candidate_table, minimum_baseline_rate_hz):
    counts = (
        candidate_table.groupby(["target", "modulation_class"])
        .size()
        .rename("n")
        .reset_index()
    )
    return f"""# BiVe3 modulation candidate contact sheets

These sheets display every BiVe3 Opsin unit-observation/target pair classified
as positive or negative after retaining baseline firing rates >=
{minimum_baseline_rate_hz:g} Hz.

No final representative unit has been selected. The candidate table explicitly
marks every row as awaiting manual review and not yet selected.

The contact-sheet decision is illustrative only. It must not change modulation
counts, percentages, heatmaps, latency distributions, response reliability,
waveform comparisons, statistical tests, or any other full-population result.

Candidate counts:

```
{counts.to_string(index=False)}
```

Each row shows the mean normalized best-channel waveform, unsmoothed raster,
raw 1-ms PSTH, Gaussian-smoothed PSTH, exact raw-file optical command timing,
baseline/response windows, response probability, firing-rate modulation,
OMI, modulation onset, and first-spike jitter.

The same output directory also contains full-eligible-population raster/PSTH
figures for positive, negative, and non-modulated units. Panels display -10 to
+45 ms. Population rasters show only trials with at least one spike in that
displayed window, with retained trials contiguous inside unit. Population PSTHs
still use every trial: each unit PSTH is constructed first and the arithmetic
mean is then taken across units. Displayed-example choices never enter this
calculation.
"""


if __name__ == "__main__":
    raise SystemExit(main())
