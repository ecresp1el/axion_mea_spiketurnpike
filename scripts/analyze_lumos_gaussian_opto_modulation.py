#!/usr/bin/env python
"""Classify Lumos optogenetic modulation with a Gaussian PSTH and local baseline."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
from scipy.ndimage import gaussian_filter1d

from scripts.build_lumos_all_units_unified_psth_store import DEFAULT_JOB_DIR
from scripts.launch_step1_sorting_analyzer_browser import DEFAULT_STIM_RAW_ROOTS
from axion_mea.gui_stim_response import (
    find_matching_raw_file,
    list_raw_files,
    load_opto_intervals_from_raw,
)


UNIT_DIR = "lumos_all_units_per_unit_psth_development"
UNIT_STORE = "lumos_all_units_per_unit_psth_development.h5"
CHANNEL_DIR = "lumos_channel_pooled_threshold_response_development"
CHANNEL_STORE = "lumos_channel_pooled_psth_development.h5"
OUTPUT_NAME = "lumos_gaussian_opto_modulation_development"
SIGMA_MS = 1.5
BASELINE_WINDOW_MS = (-20.0, -5.0)
RESPONSE_WINDOW_MS = (5.0, 25.0)
IMMEDIATE_BASELINE_WINDOW_MS = (-6.0, -1.0)
ARTIFACT_REPAIR_WINDOW_MS = (-4.0, 4.0)
MINIMUM_BASELINE_RATE_HZ = 1.0
PULSE_COLORS = {"no_opsin": "#4C78A8", "opsin": "#E45756"}
TARGETS = ("first_pulse_50", "all_pulses_250")
TRAIN_CONTEXT_NAMES = (
    "early_direct_p1_5_25ms",
    "during_actual_train_0_209p5ms",
    "post_train_available_209p5_250ms",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--unit-store",
        type=Path,
        default=DEFAULT_JOB_DIR / UNIT_DIR / UNIT_STORE,
    )
    parser.add_argument(
        "--channel-store",
        type=Path,
        default=DEFAULT_JOB_DIR / CHANNEL_DIR / CHANNEL_STORE,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_JOB_DIR / OUTPUT_NAME,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = args.output_dir.expanduser().resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    command_intervals, command_trace, command_summary = _raw_command_waveforms(
        args.unit_store.expanduser().resolve()
    )
    command_intervals.to_csv(
        staging_dir / "raw_stimulation_command_intervals.csv", index=False
    )
    command_trace.to_csv(
        staging_dir / "raw_stimulation_command_trace.csv", index=False
    )

    level_results = {}
    context_results = {}
    for level, store_path in [
        ("unit", args.unit_store.expanduser().resolve()),
        ("channel", args.channel_store.expanduser().resolve()),
    ]:
        metrics, profiles, curves, axes, context_metrics, context_curves = _analyze_store(
            store_path, level
        )
        metrics.to_csv(staging_dir / f"{level}_target_modulation_metrics.csv", index=False)
        profiles.to_csv(staging_dir / f"{level}_modulation_profiles.csv", index=False)
        for target in TARGETS:
            metrics.loc[
                metrics["target"].eq(target) & metrics["positive_modulated"]
            ].to_csv(
                staging_dir / f"{level}_positive_{target}_all_observations.csv",
                index=False,
            )
        curves.to_csv(staging_dir / f"{level}_mean_psth_and_modulation_index.csv", index=False)
        context_metrics.to_csv(
            staging_dir / f"{level}_train_context_window_metrics.csv", index=False
        )
        context_curves.to_csv(
            staging_dir / f"{level}_train_context_mean_psth_and_modulation_index.csv",
            index=False,
        )
        figure = _plot_group_diagnostic(
            plt, curves, axes, level, command_trace=command_trace
        )
        _save_figure(figure, staging_dir / f"{level}_first50_vs_all250_gaussian_pchip")
        plt.close(figure)
        context_figure = _plot_train_context(
            plt,
            context_curves,
            axes,
            level,
            command_trace=command_trace,
        )
        _save_figure(
            context_figure,
            staging_dir / f"{level}_actual_train_context_gaussian_pchip",
        )
        plt.close(context_figure)
        level_results[level] = (metrics, profiles)
        context_results[level] = context_metrics

    summary = _summary_table(level_results)
    summary.to_csv(staging_dir / "classification_summary.csv", index=False)
    baseline_sensitivity = _baseline_threshold_sensitivity(
        level_results["unit"][0], thresholds_hz=(0.0, 1.0, 2.0)
    )
    baseline_sensitivity.to_csv(
        staging_dir / "unit_baseline_threshold_sensitivity.csv", index=False
    )
    organoid_sensitivity = _organoid_baseline_threshold_summary(
        level_results["unit"][0], thresholds_hz=(0.0, 1.0, 2.0)
    )
    organoid_sensitivity.to_csv(
        staging_dir / "unit_organoid_baseline_threshold_summary.csv", index=False
    )
    all_positive_trial_locking = _positive_trial_locking_diagnostic(
        level_results["unit"][0],
        args.unit_store.expanduser().resolve(),
        well=None,
        minimum_baseline_rate_hz=1.0,
    )
    all_positive_trial_locking.to_csv(
        staging_dir / "unit_all_positive_trial_locking_diagnostic.csv", index=False
    )
    b4_trial_locking = all_positive_trial_locking.loc[
        all_positive_trial_locking["well"].eq("B4")
    ]
    b4_trial_locking.to_csv(
        staging_dir / "unit_B4_positive_trial_locking_diagnostic.csv", index=False
    )
    organoid_locking_summary = _organoid_trial_locking_summary(
        all_positive_trial_locking
    )
    organoid_locking_summary.to_csv(
        staging_dir / "unit_organoid_positive_trial_locking_summary.csv", index=False
    )
    for threshold_hz in (1.0, 2.0):
        retained = level_results["unit"][0].loc[
            level_results["unit"][0]["baseline_mean_hz"].ge(threshold_hz)
        ]
        retained.to_csv(
            staging_dir
            / f"unit_target_modulation_metrics_baseline_ge{threshold_hz:g}hz.csv",
            index=False,
        )
    unit_classification_roster = _unit_classification_roster(
        level_results["unit"][0], thresholds_hz=(0.0, 1.0, 2.0)
    )
    unit_classification_roster.to_csv(
        staging_dir / "unit_modulation_classification_roster.csv", index=False
    )
    context_summary = _context_summary_table(context_results)
    context_summary.to_csv(
        staging_dir / "train_context_classification_summary.csv", index=False
    )
    specification = _method_specification(
        level_results,
        summary,
        context_summary,
        baseline_sensitivity,
        organoid_sensitivity,
        axes,
    )
    (staging_dir / "METHOD_SPECIFICATION.md").write_text(specification, encoding="utf-8")
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "development_output": True,
        "overwrite_policy": "entire output directory replaced after successful run",
        "population": (
            "all stored good and MUA unit observations; all pooled recording channels; "
            "no KSLabel quality filter"
        ),
        "analysis_assumption": "BiVe3 Opsin",
        "targets": {
            "first_pulse_50": "P1 only across 50 trains",
            "all_pulses_250": "P1-P5 flattened in train order as 250 independent pulse trials",
        },
        "train_context_windows_ms": {
            "early_direct_p1_5_25ms": [5.0, 25.0],
            "during_actual_train_0_209p5ms": [
                float(axes["pulse_starts_ms"][0]),
                float(axes["pulse_ends_ms"][-1]),
            ],
            "post_train_available_209p5_250ms": [
                float(axes["pulse_ends_ms"][-1]),
                250.0,
            ],
        },
        "train_context_trial_rows_per_observation": 50,
        "train_context_note": (
            "The actual five-pulse command spans 0-209.5 ms. The stored train axis "
            "ends at 250 ms, so only 209.5-250 ms is available after the train."
        ),
        "bin_ms": 1.0,
        "gaussian_sigma_ms": SIGMA_MS,
        "gaussian_mode": "scipy.ndimage.gaussian_filter1d; symmetric; mode=nearest; truncate=4",
        "baseline_window_ms": list(BASELINE_WINDOW_MS),
        "response_window_ms": list(RESPONSE_WINDOW_MS),
        "classification_threshold": (
            "baseline trial-rate mean +/- 2 SEM across the target's 50 or 250 trials"
        ),
        "classification_eligibility": (
            "baseline mean firing rate from -20 to -5 ms must be >= 1 Hz"
        ),
        "immediate_baseline_window_ms": list(IMMEDIATE_BASELINE_WINDOW_MS),
        "artifact_repair_window_ms": list(ARTIFACT_REPAIR_WINDOW_MS),
        "artifact_repair": (
            "PCHIP replacement of the trial-averaged Gaussian PSTH between the nearest "
            "unrepaired flanking bin centers; used for visualization, OMI, and onset only"
        ),
        "minimum_baseline_rate_hz": MINIMUM_BASELINE_RATE_HZ,
        "baseline_rate_sensitivity_thresholds_hz": [0.0, 1.0, 2.0],
        "baseline_rate_sensitivity_scope": (
            "target-specific sorted-unit sensitivity analysis; retain observations "
            "with baseline_mean_hz greater than or equal to each threshold"
        ),
        "organoid_aggregation": (
            "well identifies organoid across recordings; unit observations are pooled "
            "within well without deduplicating recordings or raw variants"
        ),
        "positive_trial_locking_diagnostic": (
            "unsmoothed 1-ms spike-count matrices; first-spike latency and trial "
            "coincidence measured in 5-25 ms for every positive unit retained at >=1 Hz"
        ),
        "raw_command_waveform": command_summary,
        "silent_trials": "retained",
    }
    (staging_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )

    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging_dir.replace(output_dir)
    print(f"Output: {output_dir}")
    print(summary.to_string(index=False))
    return 0


def _raw_command_waveforms(unit_store_path: Path):
    with h5py.File(unit_store_path, "r") as store:
        recordings = sorted(
            {str(group.attrs["recording"]) for group in store["units"].values()}
        )
    raw_paths = list_raw_files(DEFAULT_STIM_RAW_ROOTS)
    interval_rows = []
    trace_rows = []
    signatures = set()
    for recording in recordings:
        raw_file = find_matching_raw_file(
            recording, DEFAULT_STIM_RAW_ROOTS, raw_paths=raw_paths
        )
        if raw_file is None:
            raise FileNotFoundError(f"No .raw stimulation waveform for {recording}")
        intervals = load_opto_intervals_from_raw(raw_file)
        if not intervals:
            raise ValueError(f"No optical command intervals in {raw_file}")
        first_start = float(intervals[0][0])
        pulse_intervals = [
            (float(start) - first_start, float(end) - first_start, float(intensity))
            for start, end, intensity in intervals
            if float(start) - first_start < 50.0
        ]
        signatures.add(
            tuple((round(start, 6), round(end, 6), round(intensity, 9)) for start, end, intensity in pulse_intervals)
        )
        maximum_intensity = max(intensity for _, _, intensity in pulse_intervals)
        for step_index, (start, end, intensity) in enumerate(pulse_intervals, start=1):
            interval_rows.append(
                {
                    "recording": recording,
                    "raw_file": str(raw_file),
                    "step_index": step_index,
                    "relative_start_ms": start,
                    "relative_end_ms": end,
                    "command_intensity": intensity,
                }
            )
        time = np.arange(-25.0, 30.0 + 0.05, 0.1)
        command = np.zeros_like(time)
        for start, end, intensity in pulse_intervals:
            command[(time >= start) & (time < end)] = intensity
        trace_rows.extend(
            {
                "recording": recording,
                "raw_file": str(raw_file),
                "time_ms": sample_time,
                "command_intensity": sample_intensity,
                "maximum_command_intensity": maximum_intensity,
            }
            for sample_time, sample_intensity in zip(time, command, strict=True)
        )
    summary = {
        "source": "Axion .raw XML optical micro-op command intervals",
        "relationship_to_legacy_extraction": (
            "current equivalent of legacy StimVoltageTraces_ms/StimVoltageTrace_ms"
        ),
        "recording_variants": len(recordings),
        "unique_raw_files": len({row["raw_file"] for row in interval_rows}),
        "unique_pulse_templates": len(signatures),
        "measured_electrode_voltage": False,
    }
    return pd.DataFrame(interval_rows), pd.DataFrame(trace_rows), summary


def _analyze_store(store_path: Path, level: str):
    top = "units" if level == "unit" else "channels"
    id_attr = "unit_observation_id" if level == "unit" else "channel_observation_id"
    metric_rows = []
    curve_rows = []
    context_metric_rows = []
    context_curve_rows = []
    with h5py.File(store_path, "r") as store:
        time_ms = store["axes/pulse_bin_centers_ms"][:]
        train_time_ms = store["axes/train_bin_centers_ms"][:]
        pulse_starts = store["axes/pulse_onsets_within_train_ms"][:]
        pulse_ends = store["axes/pulse_offsets_within_train_ms"][:]
        _require_axis(time_ms)
        _require_train_axis(train_time_ms)
        baseline_mask = _window_mask(time_ms, BASELINE_WINDOW_MS)
        response_mask = _window_mask(time_ms, RESPONSE_WINDOW_MS)
        immediate_mask = _window_mask(time_ms, IMMEDIATE_BASELINE_WINDOW_MS)
        train_baseline_mask = _window_mask(train_time_ms, BASELINE_WINDOW_MS)
        train_immediate_mask = _window_mask(
            train_time_ms, IMMEDIATE_BASELINE_WINDOW_MS
        )
        train_context_windows = {
            "early_direct_p1_5_25ms": RESPONSE_WINDOW_MS,
            "during_actual_train_0_209p5ms": (
                float(pulse_starts[0]),
                float(pulse_ends[-1]),
            ),
            "post_train_available_209p5_250ms": (
                float(pulse_ends[-1]),
                250.0,
            ),
        }
        for group in store[top].values():
            observation_id = str(group.attrs[id_attr])
            raw_250 = group["pulse_250/rate_hz"][:].astype(float)
            if raw_250.shape != (250, 100):
                raise ValueError(
                    f"{observation_id}: expected pulse_250 shape (250, 100), found {raw_250.shape}"
                )
            raw_by_train = raw_250.reshape(50, 5, 100)
            target_trials = {
                "first_pulse_50": raw_by_train[:, 0, :],
                "all_pulses_250": raw_250,
            }
            for target, raw_trials in target_trials.items():
                trials = gaussian_filter1d(
                    raw_trials,
                    sigma=SIGMA_MS,
                    axis=-1,
                    mode="nearest",
                    truncate=4.0,
                )
                raw_mean = raw_trials.mean(axis=0)
                gaussian_mean = trials.mean(axis=0)
                repaired_mean = _pchip_repair(time_ms, gaussian_mean)
                baseline_trials = trials[:, baseline_mask].mean(axis=1)
                response_trials = trials[:, response_mask].mean(axis=1)
                immediate_trials = trials[:, immediate_mask].mean(axis=1)
                baseline_mean = float(baseline_trials.mean())
                baseline_sem = _sem(baseline_trials)
                response_mean = float(response_trials.mean())
                response_sem = _sem(response_trials)
                immediate_mean = float(immediate_trials.mean())
                immediate_sem = _sem(immediate_trials)
                baseline_eligible = bool(
                    baseline_mean >= MINIMUM_BASELINE_RATE_HZ
                )
                positive_unrestricted = bool(
                    response_mean > baseline_mean + 2 * baseline_sem
                )
                negative_unrestricted = bool(
                    response_mean < baseline_mean - 2 * baseline_sem
                )
                positive = baseline_eligible and positive_unrestricted
                negative = baseline_eligible and negative_unrestricted
                classification = (
                    "below_1hz_baseline"
                    if not baseline_eligible
                    else "positive"
                    if positive
                    else "negative"
                    if negative
                    else "non_modulated"
                )
                denominator = repaired_mean + baseline_mean
                omi = np.divide(
                    repaired_mean - baseline_mean,
                    denominator,
                    out=np.full_like(repaired_mean, np.nan, dtype=float),
                    where=np.abs(denominator) > 1e-12,
                )
                onset = _modulation_onset(
                    time_ms,
                    repaired_mean,
                    classification,
                    immediate_mean,
                    immediate_sem,
                )
                metadata = _metadata(group.attrs, level)
                common = {
                    "analysis_level": level,
                    "observation_id": observation_id,
                    **metadata,
                    "target": target,
                    "baseline_eligible": baseline_eligible,
                }
                metric_rows.append(
                    {
                        **common,
                        "trials": len(trials),
                        "baseline_start_ms": BASELINE_WINDOW_MS[0],
                        "baseline_end_ms": BASELINE_WINDOW_MS[1],
                        "baseline_mean_hz": baseline_mean,
                        "baseline_sem_hz": baseline_sem,
                        "response_start_ms": RESPONSE_WINDOW_MS[0],
                        "response_end_ms": RESPONSE_WINDOW_MS[1],
                        "response_mean_hz": response_mean,
                        "response_sem_hz": response_sem,
                        "response_minus_baseline_hz": response_mean - baseline_mean,
                        "positive_threshold_hz": baseline_mean + 2 * baseline_sem,
                        "negative_threshold_hz": baseline_mean - 2 * baseline_sem,
                        "positive_unrestricted": positive_unrestricted,
                        "positive_modulated": positive,
                        "negative_unrestricted": negative_unrestricted,
                        "negative_modulated": negative,
                        "classification": classification,
                        "immediate_baseline_mean_hz": immediate_mean,
                        "immediate_baseline_sem_hz": immediate_sem,
                        "modulation_onset_ms": onset,
                        "response_window_mean_omi": _safe_nan_stat(
                            omi[response_mask], "mean"
                        ),
                        "peak_positive_omi_0_50ms": _safe_nan_stat(
                            omi[time_ms >= 0], "max"
                        ),
                        "peak_negative_omi_0_50ms": _safe_nan_stat(
                            omi[time_ms >= 0], "min"
                        ),
                    }
                )
                for bin_index, time in enumerate(time_ms):
                    curve_rows.append(
                        {
                            **common,
                            "time_ms_bin_center": time,
                            "raw_mean_rate_hz": raw_mean[bin_index],
                            "gaussian_mean_rate_hz": gaussian_mean[bin_index],
                            "pchip_repaired_gaussian_mean_rate_hz": repaired_mean[bin_index],
                            "opto_modulation_index": omi[bin_index],
                        }
                    )
            raw_train = group["train_full_50/rate_hz"][:].astype(float)
            if raw_train.shape != (50, 750):
                raise ValueError(
                    f"{observation_id}: expected train_full_50 shape (50, 750), "
                    f"found {raw_train.shape}"
                )
            train_trials = gaussian_filter1d(
                raw_train,
                sigma=SIGMA_MS,
                axis=-1,
                mode="nearest",
                truncate=4.0,
            )
            train_raw_mean = raw_train.mean(axis=0)
            train_gaussian_mean = train_trials.mean(axis=0)
            train_repaired_mean = _pchip_repair_at_onsets(
                train_time_ms, train_gaussian_mean, pulse_starts
            )
            train_baseline_trials = train_trials[:, train_baseline_mask].mean(axis=1)
            train_baseline_mean = float(train_baseline_trials.mean())
            train_baseline_sem = _sem(train_baseline_trials)
            train_baseline_eligible = bool(
                train_baseline_mean >= MINIMUM_BASELINE_RATE_HZ
            )
            train_immediate_trials = train_trials[:, train_immediate_mask].mean(axis=1)
            train_immediate_mean = float(train_immediate_trials.mean())
            train_immediate_sem = _sem(train_immediate_trials)
            train_denominator = train_repaired_mean + train_baseline_mean
            train_omi = np.divide(
                train_repaired_mean - train_baseline_mean,
                train_denominator,
                out=np.full_like(train_repaired_mean, np.nan, dtype=float),
                where=np.abs(train_denominator) > 1e-12,
            )
            context_common = {
                "analysis_level": level,
                "observation_id": observation_id,
                **_metadata(group.attrs, level),
                "baseline_eligible": train_baseline_eligible,
            }
            for window_name, window in train_context_windows.items():
                window_mask = _window_mask(train_time_ms, window)
                if not window_mask.any():
                    raise ValueError(f"No bins found for train-context window {window_name}")
                response_trials = train_trials[:, window_mask].mean(axis=1)
                response_mean = float(response_trials.mean())
                response_sem = _sem(response_trials)
                positive_unrestricted = bool(
                    response_mean > train_baseline_mean + 2 * train_baseline_sem
                )
                negative_unrestricted = bool(
                    response_mean < train_baseline_mean - 2 * train_baseline_sem
                )
                positive = train_baseline_eligible and positive_unrestricted
                negative = train_baseline_eligible and negative_unrestricted
                classification = (
                    "below_1hz_baseline"
                    if not train_baseline_eligible
                    else "positive"
                    if positive
                    else "negative"
                    if negative
                    else "non_modulated"
                )
                onset_search_start = 0.0 if window_name != TRAIN_CONTEXT_NAMES[-1] else window[0]
                onset = _modulation_onset_between(
                    train_time_ms,
                    train_repaired_mean,
                    classification,
                    train_immediate_mean,
                    train_immediate_sem,
                    onset_search_start,
                    window[1],
                )
                context_metric_rows.append(
                    {
                        **context_common,
                        "window": window_name,
                        "trials": len(train_trials),
                        "baseline_start_ms": BASELINE_WINDOW_MS[0],
                        "baseline_end_ms": BASELINE_WINDOW_MS[1],
                        "baseline_mean_hz": train_baseline_mean,
                        "baseline_sem_hz": train_baseline_sem,
                        "response_start_ms": window[0],
                        "response_end_ms": window[1],
                        "response_bins": int(window_mask.sum()),
                        "response_mean_hz": response_mean,
                        "response_sem_hz": response_sem,
                        "response_minus_baseline_hz": response_mean
                        - train_baseline_mean,
                        "positive_threshold_hz": train_baseline_mean
                        + 2 * train_baseline_sem,
                        "negative_threshold_hz": train_baseline_mean
                        - 2 * train_baseline_sem,
                        "positive_unrestricted": positive_unrestricted,
                        "negative_unrestricted": negative_unrestricted,
                        "positive_modulated": positive,
                        "negative_modulated": negative,
                        "classification": classification,
                        "modulation_onset_ms": onset,
                        "response_window_mean_omi": _safe_nan_stat(
                            train_omi[window_mask], "mean"
                        ),
                    }
                )
            train_display_mask = train_time_ms >= -25.0
            for bin_index in np.flatnonzero(train_display_mask):
                context_curve_rows.append(
                    {
                        **context_common,
                        "time_ms_bin_center": train_time_ms[bin_index],
                        "raw_mean_rate_hz": train_raw_mean[bin_index],
                        "gaussian_mean_rate_hz": train_gaussian_mean[bin_index],
                        "pchip_repaired_gaussian_mean_rate_hz": train_repaired_mean[
                            bin_index
                        ],
                        "opto_modulation_index": train_omi[bin_index],
                    }
                )
    metrics = pd.DataFrame(metric_rows)
    profiles = _profiles(metrics)
    curves = pd.DataFrame(curve_rows)
    axes = {"pulse_starts_ms": pulse_starts, "pulse_ends_ms": pulse_ends}
    context_metrics = pd.DataFrame(context_metric_rows)
    context_curves = pd.DataFrame(context_curve_rows)
    return metrics, profiles, curves, axes, context_metrics, context_curves


def _metadata(attrs, level):
    columns = [
        "recording",
        "well",
        "condition",
        "raw_variant",
        "best_channel_index",
        "best_channel_id",
        "hdf5_group",
    ]
    if level == "unit":
        columns += ["unit_id", "KSLabel", "waveform_class"]
    else:
        columns += ["units_pooled", "good_units_pooled", "mua_units_pooled", "source_unit_ids"]
    return {column: attrs.get(column, "") for column in columns}


def _profiles(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for observation_id, group in metrics.groupby("observation_id", sort=False):
        first = group.iloc[0]
        row = {
            column: first[column]
            for column in metrics.columns
            if column
            in {
                "analysis_level",
                "recording",
                "well",
                "condition",
                "raw_variant",
                "best_channel_index",
                "best_channel_id",
                "unit_id",
                "KSLabel",
                "waveform_class",
                "units_pooled",
                "good_units_pooled",
                "mua_units_pooled",
                "source_unit_ids",
            }
        }
        row["observation_id"] = observation_id
        indexed = group.set_index("target")
        if set(indexed.index) != set(TARGETS):
            raise ValueError(f"{observation_id}: missing target rows")
        for target in TARGETS:
            selected = indexed.loc[target]
            for column in [
                "baseline_mean_hz",
                "baseline_sem_hz",
                "response_mean_hz",
                "response_minus_baseline_hz",
                "response_window_mean_omi",
                "modulation_onset_ms",
                "classification",
                "positive_modulated",
                "negative_modulated",
                "baseline_eligible",
                "trials",
            ]:
                row[f"{target}_{column}"] = selected[column]
        rows.append(row)
    return pd.DataFrame(rows)


def _pchip_repair(time_ms: np.ndarray, values: np.ndarray) -> np.ndarray:
    repaired = np.asarray(values, dtype=float).copy()
    gap = (time_ms >= ARTIFACT_REPAIR_WINDOW_MS[0]) & (time_ms <= ARTIFACT_REPAIR_WINDOW_MS[1])
    left_candidates = np.flatnonzero(time_ms < ARTIFACT_REPAIR_WINDOW_MS[0])
    right_candidates = np.flatnonzero(time_ms > ARTIFACT_REPAIR_WINDOW_MS[1])
    flank = np.concatenate([left_candidates[-4:], right_candidates[:4]])
    interpolator = PchipInterpolator(time_ms[flank], repaired[flank])
    repaired[gap] = interpolator(time_ms[gap])
    return repaired


def _pchip_repair_at_onsets(
    time_ms: np.ndarray, values: np.ndarray, onsets_ms: np.ndarray
) -> np.ndarray:
    repaired = np.asarray(values, dtype=float).copy()
    for onset in np.asarray(onsets_ms, dtype=float):
        gap_start = onset + ARTIFACT_REPAIR_WINDOW_MS[0]
        gap_end = onset + ARTIFACT_REPAIR_WINDOW_MS[1]
        gap = (time_ms >= gap_start) & (time_ms <= gap_end)
        left_candidates = np.flatnonzero(time_ms < gap_start)
        right_candidates = np.flatnonzero(time_ms > gap_end)
        flank = np.concatenate([left_candidates[-4:], right_candidates[:4]])
        interpolator = PchipInterpolator(time_ms[flank], repaired[flank])
        repaired[gap] = interpolator(time_ms[gap])
    return repaired


def _modulation_onset(time_ms, repaired_mean, classification, baseline_mean, baseline_sem):
    post = time_ms >= 0
    if classification == "positive":
        hits = np.flatnonzero(post & (repaired_mean > baseline_mean + 2 * baseline_sem))
    elif classification == "negative":
        hits = np.flatnonzero(post & (repaired_mean < baseline_mean - 2 * baseline_sem))
    else:
        return np.nan
    return float(time_ms[hits[0]]) if len(hits) else np.nan


def _modulation_onset_between(
    time_ms,
    repaired_mean,
    classification,
    baseline_mean,
    baseline_sem,
    search_start_ms,
    search_end_ms,
):
    search = (time_ms >= search_start_ms) & (time_ms < search_end_ms)
    if classification == "positive":
        hits = np.flatnonzero(
            search & (repaired_mean > baseline_mean + 2 * baseline_sem)
        )
    elif classification == "negative":
        hits = np.flatnonzero(
            search & (repaired_mean < baseline_mean - 2 * baseline_sem)
        )
    else:
        return np.nan
    return float(time_ms[hits[0]]) if len(hits) else np.nan


def _plot_group_diagnostic(plt, curves, axes, level, *, command_trace):
    figure, plot_axes = plt.subplots(2, 2, figsize=(12.5, 8.0), sharex=True, squeeze=False)
    command_templates = {
        maximum: data.groupby("time_ms", as_index=False)["command_intensity"].mean()
        for maximum, data in command_trace.groupby("maximum_command_intensity", sort=True)
    }
    target_labels = {
        "first_pulse_50": "First pulse only · 50 trials",
        "all_pulses_250": "All pulses flattened · 250 trials",
    }
    for row, target in enumerate(TARGETS):
        for column, condition in enumerate(["opsin", "no_opsin"]):
            axis = plot_axes[row, column]
            selected = curves.loc[
                curves["target"].eq(target)
                & curves["condition"].eq(condition)
                & curves["baseline_eligible"]
            ]
            group = selected.groupby("time_ms_bin_center")
            mean = group[
                ["raw_mean_rate_hz", "gaussian_mean_rate_hz", "pchip_repaired_gaussian_mean_rate_hz"]
            ].mean()
            time = mean.index.to_numpy(float)
            axis.axvspan(0, 9.5, color="#F2CF5B", alpha=0.10, lw=0)
            axis.axvline(0, color="#7C3E00", ls="--", lw=0.9)
            axis.axvspan(*BASELINE_WINDOW_MS, color="#9CA3AF", alpha=0.10, lw=0)
            axis.axvspan(*RESPONSE_WINDOW_MS, color="#F59E0B", alpha=0.07, lw=0)
            axis.plot(time, mean["raw_mean_rate_hz"], color="#111827", lw=1.0, alpha=0.55, label="raw")
            axis.plot(time, mean["gaussian_mean_rate_hz"], color="#2563EB", lw=1.5, label="Gaussian σ=1.5 ms")
            axis.plot(
                time,
                mean["pchip_repaired_gaussian_mean_rate_hz"],
                color="#DC2626",
                lw=1.25,
                ls="--",
                label="PCHIP-repaired",
            )
            command_axis = axis.twinx()
            for template_index, (maximum, template) in enumerate(command_templates.items()):
                command_axis.plot(
                    template["time_ms"],
                    template["command_intensity"],
                    color="#D97706",
                    lw=1.35,
                    ls="-" if template_index else "--",
                    alpha=0.85,
                    drawstyle="steps-post",
                    label=f"raw command max={maximum:g}",
                )
            command_axis.set_ylim(
                0,
                max(float(command_trace["command_intensity"].max()) * 3.0, 1.0),
            )
            command_axis.set_yticks([])
            command_axis.spines[["top", "right"]].set_visible(False)
            axis.set_xlim(-25, 30)
            axis.set_ylim(bottom=0)
            axis.set_title(
                f"{'ABCD'[row * 2 + column]}  {condition.replace('_', ' ').title()}\n"
                f"{target_labels[target]} · baseline ≥1 Hz · n={selected['observation_id'].nunique()}",
                loc="left",
                fontweight="bold",
            )
            axis.set_ylabel("Mean firing rate (Hz)")
            axis.set_xlabel("Time from exact pulse onset (ms)")
            axis.spines[["top", "right"]].set_visible(False)
            if row == 0 and column == 0:
                axis.legend(frameon=False, fontsize=8, loc="upper left")
                command_axis.legend(frameon=False, fontsize=8, loc="upper right")
    figure.suptitle(
        f"{level.capitalize()} Gaussian optogenetic-modulation diagnostic",
        x=0.06,
        y=0.985,
        ha="left",
        fontsize=14,
        fontweight="bold",
    )
    figure.text(
        0.06,
        0.94,
        "Gray: −20 to −5 ms baseline. Pale orange: 5–25 ms response. Dark-orange trace: raw-file optical command ramp/plateau.",
        fontsize=8.5,
        color="#4B5563",
    )
    figure.subplots_adjust(left=0.08, right=0.99, bottom=0.08, top=0.88, wspace=0.18, hspace=0.35)
    return figure


def _plot_train_context(plt, curves, axes, level, *, command_trace):
    figure, plot_axes = plt.subplots(
        2, 2, figsize=(13.0, 7.6), sharex=True, squeeze=False
    )
    command_templates = {
        maximum: data.groupby("time_ms", as_index=False)["command_intensity"].mean()
        for maximum, data in command_trace.groupby(
            "maximum_command_intensity", sort=True
        )
    }
    for column, condition in enumerate(["opsin", "no_opsin"]):
        selected = curves.loc[
            curves["condition"].eq(condition) & curves["baseline_eligible"]
        ]
        observation_n = selected["observation_id"].nunique()
        rate_group = selected.groupby("time_ms_bin_center")[
            "pchip_repaired_gaussian_mean_rate_hz"
        ]
        rate_mean = rate_group.mean()
        rate_sem = rate_group.std(ddof=1).fillna(0.0) / np.sqrt(observation_n)
        omi_group = selected.groupby("time_ms_bin_center")["opto_modulation_index"]
        omi_mean = omi_group.mean()
        omi_sem = omi_group.std(ddof=1).fillna(0.0) / np.sqrt(observation_n)
        time = rate_mean.index.to_numpy(float)
        for row, (mean, sem, color, ylabel) in enumerate(
            [
                (rate_mean, rate_sem, PULSE_COLORS[condition], "Mean firing rate (Hz)"),
                (omi_mean, omi_sem, "#6D28D9", "Optogenetic modulation index"),
            ]
        ):
            axis = plot_axes[row, column]
            for onset, offset in zip(
                axes["pulse_starts_ms"], axes["pulse_ends_ms"], strict=True
            ):
                axis.axvspan(onset, offset, color="#F2CF5B", alpha=0.16, lw=0)
                axis.axvline(onset, color="#7C3E00", ls="--", lw=0.7, alpha=0.8)
            axis.axvspan(*BASELINE_WINDOW_MS, color="#9CA3AF", alpha=0.12, lw=0)
            axis.axvspan(*RESPONSE_WINDOW_MS, color="#F59E0B", alpha=0.08, lw=0)
            axis.plot(time, mean.to_numpy(float), color=color, lw=1.5)
            axis.fill_between(
                time,
                mean.to_numpy(float) - sem.to_numpy(float),
                mean.to_numpy(float) + sem.to_numpy(float),
                color=color,
                alpha=0.16,
                lw=0,
            )
            axis.axvline(float(axes["pulse_ends_ms"][-1]), color="#111827", ls=":", lw=1.0)
            axis.set_xlim(-25, 250)
            axis.set_ylabel(ylabel)
            axis.spines[["top", "right"]].set_visible(False)
            if row == 0:
                axis.set_ylim(bottom=0)
                axis.set_title(
                    f"{'AB'[column]}  {condition.replace('_', ' ').title()} · n={observation_n}",
                    loc="left",
                    fontweight="bold",
                )
            else:
                axis.axhline(0, color="#6B7280", lw=0.7)
                axis.set_ylim(-1.05, 1.05)
                axis.set_xlabel("Time from exact P1 onset (ms)")
        command_axis = plot_axes[0, column].twinx()
        for template_index, (maximum, template) in enumerate(command_templates.items()):
            for onset in axes["pulse_starts_ms"]:
                command_axis.plot(
                    template["time_ms"] + onset,
                    template["command_intensity"],
                    color="#D97706",
                    lw=0.9,
                    ls="-" if template_index else "--",
                    alpha=0.55,
                    drawstyle="steps-post",
                )
        command_axis.set_ylim(
            0,
            max(float(command_trace["command_intensity"].max()) * 3.0, 1.0),
        )
        command_axis.set_yticks([])
        command_axis.spines[["top", "right"]].set_visible(False)
    figure.suptitle(
        f"BiVe3 Opsin · {level} actual five-pulse train context",
        x=0.065,
        y=0.985,
        ha="left",
        fontsize=14,
        fontweight="bold",
    )
    figure.text(
        0.065,
        0.94,
        "Pulses: 0, 50, 100, 150, 200 ms; light ends at 209.5 ms (dotted line). Curves: observation mean ± SEM; Gaussian σ=1.5 ms with PCHIP repair around each pulse for display and OMI.",
        fontsize=8.5,
        color="#4B5563",
    )
    figure.subplots_adjust(
        left=0.08, right=0.99, bottom=0.09, top=0.87, wspace=0.18, hspace=0.17
    )
    return figure


def _summary_table(level_results):
    rows = []
    for level, (metrics, _) in level_results.items():
        for target in TARGETS:
            target_data = metrics.loc[metrics["target"].eq(target)]
            for condition, all_data in target_data.groupby("condition", sort=False):
                data = all_data.loc[all_data["baseline_eligible"]]
                rows.append(
                    {
                        "analysis_level": level,
                        "target": target,
                        "condition": condition,
                        "trial_rows_per_observation": int(data["trials"].iloc[0]),
                        "n_total_observations": len(all_data),
                        "n_observations": len(data),
                        "n_excluded_below_1hz": len(all_data) - len(data),
                        "positive_modulated_n": int(data["positive_modulated"].sum()),
                        "positive_modulated_percent": 100
                        * data["positive_modulated"].mean(),
                        "negative_modulated_n": int(data["negative_modulated"].sum()),
                        "negative_modulated_percent": 100
                        * data["negative_modulated"].mean(),
                    }
                )
    return pd.DataFrame(rows)


def _context_summary_table(context_results):
    rows = []
    for level, metrics in context_results.items():
        for window in TRAIN_CONTEXT_NAMES:
            window_data = metrics.loc[metrics["window"].eq(window)]
            for condition, all_data in window_data.groupby("condition", sort=False):
                data = all_data.loc[all_data["baseline_eligible"]]
                rows.append(
                    {
                        "analysis_level": level,
                        "window": window,
                        "condition": condition,
                        "trial_rows_per_observation": int(data["trials"].iloc[0]),
                        "n_total_observations": len(all_data),
                        "n_observations": len(data),
                        "n_excluded_below_1hz": len(all_data) - len(data),
                        "positive_modulated_n": int(data["positive_modulated"].sum()),
                        "positive_modulated_percent": 100
                        * data["positive_modulated"].mean(),
                        "negative_modulated_n": int(data["negative_modulated"].sum()),
                        "negative_modulated_percent": 100
                        * data["negative_modulated"].mean(),
                    }
                )
    return pd.DataFrame(rows)


def _baseline_threshold_sensitivity(metrics, *, thresholds_hz):
    rows = []
    for target in TARGETS:
        target_data = metrics.loc[metrics["target"].eq(target)]
        for condition, all_data in target_data.groupby("condition", sort=False):
            for threshold_hz in thresholds_hz:
                retained = all_data.loc[
                    all_data["baseline_mean_hz"].ge(threshold_hz)
                ]
                positive_n = int(retained["positive_unrestricted"].sum())
                negative_n = int(retained["negative_unrestricted"].sum())
                non_modulated_n = len(retained) - positive_n - negative_n
                denominator = len(retained)
                zero_mean = retained["baseline_mean_hz"].abs().lt(1e-12)
                zero_sem = retained["baseline_sem_hz"].abs().lt(1e-12)
                rows.append(
                    {
                        "analysis_level": "unit",
                        "target": target,
                        "condition": condition,
                        "minimum_baseline_rate_hz": threshold_hz,
                        "n_total_observations": len(all_data),
                        "n_excluded": len(all_data) - denominator,
                        "excluded_percent": 100
                        * (len(all_data) - denominator)
                        / len(all_data),
                        "n_retained": denominator,
                        "retained_percent": 100 * denominator / len(all_data),
                        "positive_n": positive_n,
                        "positive_percent": 100 * positive_n / denominator
                        if denominator
                        else np.nan,
                        "negative_n": negative_n,
                        "negative_percent": 100 * negative_n / denominator
                        if denominator
                        else np.nan,
                        "non_modulated_n": non_modulated_n,
                        "non_modulated_percent": 100 * non_modulated_n / denominator
                        if denominator
                        else np.nan,
                        "remaining_baseline_mean_zero_n": int(zero_mean.sum()),
                        "remaining_baseline_sem_zero_n": int(zero_sem.sum()),
                        "remaining_baseline_mean_and_sem_zero_n": int(
                            (zero_mean & zero_sem).sum()
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _unit_classification_roster(metrics, *, thresholds_hz):
    rows = []
    roster_columns = [
        "analysis_level",
        "target",
        "condition",
        "well",
        "observation_id",
        "recording",
        "raw_variant",
        "unit_id",
        "KSLabel",
        "waveform_class",
        "trials",
        "baseline_mean_hz",
        "baseline_sem_hz",
        "response_mean_hz",
        "response_sem_hz",
        "response_minus_baseline_hz",
        "positive_threshold_hz",
        "negative_threshold_hz",
        "modulation_onset_ms",
        "response_window_mean_omi",
    ]
    for threshold_hz in thresholds_hz:
        retained = metrics.loc[metrics["baseline_mean_hz"].ge(threshold_hz)]
        for metric in retained.itertuples(index=False):
            classification = (
                "positive"
                if metric.positive_unrestricted
                else "negative"
                if metric.negative_unrestricted
                else "non_modulated"
            )
            row = {
                column: getattr(metric, column)
                for column in roster_columns
            }
            row["minimum_baseline_rate_hz"] = threshold_hz
            row["classification_at_threshold"] = classification
            rows.append(row)
    return pd.DataFrame(rows)[
        roster_columns[:4]
        + ["minimum_baseline_rate_hz", "classification_at_threshold"]
        + roster_columns[4:]
    ]


def _organoid_baseline_threshold_summary(metrics, *, thresholds_hz):
    condition_counts = metrics.groupby("well")["condition"].nunique()
    inconsistent = condition_counts.loc[condition_counts.ne(1)]
    if len(inconsistent):
        raise ValueError(
            "Each well must map to one condition across recordings; inconsistent wells: "
            + ", ".join(inconsistent.index.astype(str))
        )
    rows = []
    for target in TARGETS:
        target_data = metrics.loc[metrics["target"].eq(target)]
        for (well, condition), all_data in target_data.groupby(
            ["well", "condition"], sort=True
        ):
            for threshold_hz in thresholds_hz:
                retained = all_data.loc[
                    all_data["baseline_mean_hz"].ge(threshold_hz)
                ]
                positive_n = int(retained["positive_unrestricted"].sum())
                negative_n = int(retained["negative_unrestricted"].sum())
                non_modulated_n = len(retained) - positive_n - negative_n
                denominator = len(retained)
                rows.append(
                    {
                        "analysis_level": "organoid_well",
                        "target": target,
                        "well": well,
                        "condition": condition,
                        "minimum_baseline_rate_hz": threshold_hz,
                        "recordings_contributing_total": all_data[
                            "recording"
                        ].nunique(),
                        "recordings_contributing_retained": retained[
                            "recording"
                        ].nunique(),
                        "total_unit_observations": len(all_data),
                        "excluded_unit_observations": len(all_data) - denominator,
                        "retained_unit_observations": denominator,
                        "positive_n": positive_n,
                        "negative_n": negative_n,
                        "non_modulated_n": non_modulated_n,
                        "positive_fraction": positive_n / denominator
                        if denominator
                        else np.nan,
                        "positive_percent": 100 * positive_n / denominator
                        if denominator
                        else np.nan,
                        "negative_fraction": negative_n / denominator
                        if denominator
                        else np.nan,
                        "non_modulated_fraction": non_modulated_n / denominator
                        if denominator
                        else np.nan,
                        "remaining_baseline_mean_and_sem_zero_n": int(
                            (
                                retained["baseline_mean_hz"].abs().lt(1e-12)
                                & retained["baseline_sem_hz"].abs().lt(1e-12)
                            ).sum()
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _positive_trial_locking_diagnostic(
    metrics,
    unit_store_path,
    *,
    well,
    minimum_baseline_rate_hz,
):
    selection = metrics["baseline_mean_hz"].ge(
        minimum_baseline_rate_hz
    ) & metrics["positive_unrestricted"]
    if well is not None:
        selection &= metrics["well"].eq(well)
    selected = metrics.loc[selection].copy()
    rows = []
    with h5py.File(unit_store_path, "r") as store:
        time_ms = store["axes/pulse_bin_centers_ms"][:]
        baseline_mask = _window_mask(time_ms, BASELINE_WINDOW_MS)
        response_mask = _window_mask(time_ms, RESPONSE_WINDOW_MS)
        early_mask = _window_mask(time_ms, (5.0, 10.0))
        response_times = time_ms[response_mask]
        for metric in selected.itertuples(index=False):
            group = store[str(metric.hdf5_group).lstrip("/")]
            pulse_250 = group["pulse_250/counts"][:].astype(int)
            trials = (
                pulse_250.reshape(50, 5, -1)[:, 0, :]
                if metric.target == "first_pulse_50"
                else pulse_250
            )
            response_counts = trials[:, response_mask]
            baseline_counts = trials[:, baseline_mask]
            early_counts = trials[:, early_mask]
            response_trial_hits = response_counts.sum(axis=1) > 0
            baseline_trial_hits = baseline_counts.sum(axis=1) > 0
            early_trial_hits = early_counts.sum(axis=1) > 0
            first_latencies = np.asarray(
                [
                    response_times[np.flatnonzero(row > 0)[0]]
                    for row in response_counts[response_trial_hits]
                ],
                dtype=float,
            )
            same_bin_counts = (response_counts > 0).sum(axis=0)
            maximum_same_bin = int(same_bin_counts.max())
            maximum_same_bin_times = response_times[
                same_bin_counts == maximum_same_bin
            ]
            rows.append(
                {
                    "well": metric.well,
                    "condition": metric.condition,
                    "target": metric.target,
                    "observation_id": metric.observation_id,
                    "recording": metric.recording,
                    "raw_variant": metric.raw_variant,
                    "unit_id": metric.unit_id,
                    "KSLabel": metric.KSLabel,
                    "waveform_class": metric.waveform_class,
                    "baseline_mean_hz": metric.baseline_mean_hz,
                    "response_mean_hz": metric.response_mean_hz,
                    "retained_ge1hz": metric.baseline_mean_hz >= 1.0,
                    "retained_ge2hz": metric.baseline_mean_hz >= 2.0,
                    "classifier_onset_ms": metric.modulation_onset_ms,
                    "trials": len(trials),
                    "response_trials_with_spike_n": int(response_trial_hits.sum()),
                    "response_trial_fraction": float(response_trial_hits.mean()),
                    "early_5_10ms_trials_with_spike_n": int(early_trial_hits.sum()),
                    "early_5_10ms_trial_fraction": float(early_trial_hits.mean()),
                    "baseline_trials_with_spike_n": int(baseline_trial_hits.sum()),
                    "baseline_trial_fraction": float(baseline_trial_hits.mean()),
                    "first_spike_latency_median_ms": _safe_nan_stat(
                        first_latencies, "median"
                    ),
                    "first_spike_latency_mean_ms": _safe_nan_stat(
                        first_latencies, "mean"
                    ),
                    "first_spike_latency_sd_ms": float(
                        first_latencies.std(ddof=1)
                    )
                    if len(first_latencies) > 1
                    else np.nan,
                    "first_spike_latency_iqr_ms": float(
                        np.percentile(first_latencies, 75)
                        - np.percentile(first_latencies, 25)
                    )
                    if len(first_latencies)
                    else np.nan,
                    "maximum_same_bin_trial_n": maximum_same_bin,
                    "maximum_same_bin_trial_fraction": maximum_same_bin / len(trials),
                    "maximum_same_bin_latency_ms": ";".join(
                        f"{value:g}" for value in maximum_same_bin_times
                    ),
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["target", "condition", "well", "retained_ge2hz", "observation_id"],
        ascending=[True, True, True, False, True],
    )


def _organoid_trial_locking_summary(diagnostic):
    rows = []
    for target in TARGETS:
        target_data = diagnostic.loc[diagnostic["target"].eq(target)]
        for threshold_hz, threshold_column in [
            (1.0, "retained_ge1hz"),
            (2.0, "retained_ge2hz"),
        ]:
            retained = target_data.loc[target_data[threshold_column]]
            for (condition, well), group in retained.groupby(
                ["condition", "well"], sort=True
            ):
                rows.append(
                    {
                        "target": target,
                        "minimum_baseline_rate_hz": threshold_hz,
                        "condition": condition,
                        "well": well,
                        "positive_units": len(group),
                        "good_units": int(group["KSLabel"].eq("good").sum()),
                        "median_response_trial_fraction": group[
                            "response_trial_fraction"
                        ].median(),
                        "minimum_response_trial_fraction": group[
                            "response_trial_fraction"
                        ].min(),
                        "maximum_response_trial_fraction": group[
                            "response_trial_fraction"
                        ].max(),
                        "median_early_5_10ms_trial_fraction": group[
                            "early_5_10ms_trial_fraction"
                        ].median(),
                        "median_first_spike_latency_ms": group[
                            "first_spike_latency_median_ms"
                        ].median(),
                        "median_first_spike_jitter_sd_ms": group[
                            "first_spike_latency_sd_ms"
                        ].median(),
                        "median_maximum_same_bin_trial_fraction": group[
                            "maximum_same_bin_trial_fraction"
                        ].median(),
                        "maximum_same_bin_trial_n": int(
                            group["maximum_same_bin_trial_n"].max()
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _method_specification(
    level_results,
    summary,
    context_summary,
    baseline_sensitivity,
    organoid_sensitivity,
    axes,
):
    train_end = float(axes["pulse_ends_ms"][-1])
    return f"""# Gaussian optogenetic-modulation development analysis

This output reproduces the supplied Gaussian optogenetic-modulation pipeline. It remains a development analysis until reviewed.

## Calculation

- Every stored trial is retained, including trials with zero spikes.
- One-ms per-trial firing-rate matrices are smoothed with a symmetric Gaussian kernel, sigma={SIGMA_MS:g} ms.
- Baseline is {BASELINE_WINDOW_MS[0]:g} to {BASELINE_WINDOW_MS[1]:g} ms relative to each pulse.
- Response is {RESPONSE_WINDOW_MS[0]:g} to {RESPONSE_WINDOW_MS[1]:g} ms relative to each pulse.
- Baseline mean and SEM are calculated across the target's trial-specific baseline-window rates: 50 rows for `first_pulse_50` or 250 rows for `all_pulses_250`.
- Positive: response-window mean exceeds baseline mean + 2 SEM.
- Negative: response-window mean is below baseline mean - 2 SEM.
- Classification requires a baseline mean firing rate of at least {MINIMUM_BASELINE_RATE_HZ:g} Hz in the -20 to -5 ms window. Lower-rate observations remain in the complete metric tables as `below_1hz_baseline` but are excluded from classification summaries, positive-candidate exports, and group PSTHs.
- The BiVe3 Opsin analysis is used.
- `first_pulse_50` analyzes only P1 across the 50 trains.
- `all_pulses_250` flattens P1-P5 in train order and analyzes them as 250 pulse trials; pulse positions are not classified separately.
- The separate train-context table uses 50 train trials aligned to P1. Its three windows are: P1 direct response at 5-25 ms, the actual five-pulse train at 0-{train_end:g} ms, and the available post-train interval at {train_end:g}-250 ms.
- The actual pulse onsets are 0, 50, 100, 150, and 200 ms; their command offsets are 9.5, 59.5, 109.5, 159.5, and {train_end:g} ms.
- The broad train and post-train classifications apply the same baseline mean +/- 2 SEM rule across 50 train trials. The broad train mean includes recorded bins surrounding later light artifacts; consult the PCHIP-repaired PSTH and OMI alongside that scalar classification.
- OMI at each millisecond is `(repaired Gaussian mean PSTH - baseline mean) / (repaired Gaussian mean PSTH + baseline mean)`.
- The pulse-aligned mean Gaussian PSTH from {ARTIFACT_REPAIR_WINDOW_MS[0]:g} to {ARTIFACT_REPAIR_WINDOW_MS[1]:g} ms is PCHIP-interpolated for visualization, OMI, and onset detection. The train-context PSTH applies the same repair around every pulse onset. Repair does not change the firing rates used for window classification.
- Modulation onset is the first post-trigger bin outside the immediate {IMMEDIATE_BASELINE_WINDOW_MS[0]:g} to {IMMEDIATE_BASELINE_WINDOW_MS[1]:g} ms mean +/- 2 SEM in the classified direction.

## Replication

- Unit rows include every stored `KSLabel=good` and `KSLabel=mua` observation; no KSLabel quality filter is applied.
- Unit rows remain individual sorted-unit observations; raw variants and recordings are not deduplicated.
- Channel rows include every pooled recording x well x physical channel, with all good/MUA unit spikes assigned to that channel.
- Unit observations: {len(level_results['unit'][1])}.
- Channel observations: {len(level_results['channel'][1])}.

## Summary

### Direct pulse analyses

```
{summary.to_string(index=False)}
```

### Train-context analyses

```
{context_summary.to_string(index=False)}
```

### Sorted-unit baseline-rate sensitivity

The table below re-applies the unrestricted baseline +/- 2 SEM classification after
retaining observations with baseline mean firing rates greater than or equal to 0,
1, or 2 Hz. Percentages use the retained observations as their denominators.

```
{baseline_sensitivity.to_string(index=False)}
```

### Per-organoid baseline-rate sensitivity

Each well is treated as one organoid across recordings. Unit observations from every
recording and raw variant are retained as separate observations and pooled within well.

```
{organoid_sensitivity.to_string(index=False)}
```
"""


def _window_mask(time_ms, window):
    return (time_ms >= window[0]) & (time_ms < window[1])


def _sem(values):
    values = np.asarray(values, dtype=float)
    return float(values.std(ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0.0


def _safe_nan_stat(values, statistic):
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if not len(finite):
        return np.nan
    functions = {"mean": np.mean, "median": np.median, "max": np.max, "min": np.min}
    return float(functions[statistic](finite))


def _require_axis(time_ms):
    if len(time_ms) != 100 or not np.allclose(np.diff(time_ms), 1.0):
        raise ValueError("Expected the unified -50 to +50 ms axis with 100 one-ms bin centers")


def _require_train_axis(time_ms):
    if (
        len(time_ms) != 750
        or not np.allclose(np.diff(time_ms), 1.0)
        or not np.isclose(time_ms[0], -499.5)
        or not np.isclose(time_ms[-1], 249.5)
    ):
        raise ValueError(
            "Expected the unified -500 to +250 ms train axis with 750 one-ms bins"
        )


def _save_figure(figure, base_path):
    figure.savefig(base_path.with_suffix(".png"), dpi=350, bbox_inches="tight", facecolor="white")
    figure.savefig(base_path.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")


if __name__ == "__main__":
    raise SystemExit(main())
