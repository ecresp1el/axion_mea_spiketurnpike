#!/usr/bin/env python
"""Test Lumos opsin effects using good units and independent organoid wells."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import binomtest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.launch_step1_sorting_analyzer_browser import DEFAULT_STIM_RAW_ROOTS  # noqa: E402
from scripts.plot_lumos_opsin_pre_post_organoid_firing_rates import DEFAULT_SOURCE_DIR  # noqa: E402
from scripts.plot_lumos_opsin_pre_post_unit_firing_rates import (  # noqa: E402
    DEFAULT_UNIT_METRICS,
    VARIANT_MARKERS,
    _load_condition_map,
    _match_unit_id,
    _unit_label,
)
from axion_mea.gui_stim_response import resolve_stim_sidecars  # noqa: E402


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
STEM = "lumos_good_opsin_independent_significance_20260710"
WINDOWS = (
    ("early_0_5ms", 5.0),
    ("during_pulse_0_9p5ms", 9.5),
    ("early_0_15ms", 15.0),
    ("standard_0_25ms", 25.0),
    ("extended_0_50ms", 50.0),
)
PRIMARY_WINDOW = "during_pulse_0_9p5ms"
PSTH_START_MS = -25.0
PSTH_END_MS = 50.0
PSTH_BIN_MS = 1.0
PSTH_TEST_END_MS = 25.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-metrics-csv", type=Path, default=DEFAULT_UNIT_METRICS)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_JOB_DIR / STEM)
    parser.add_argument("--expected-pulse-trials", type=int, default=250)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import spikeinterface.full as si

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    condition_map = _load_condition_map()
    source = pd.read_csv(args.unit_metrics_csv.expanduser().resolve())
    source = source.loc[
        source["recording"].astype(str).str.contains(
            "6_22_2026_129-8445_ventral_sosrs_opsin_day3|6_18_2026_plate2",
            regex=True,
        )
        & source["raw_variant"].isin(VARIANT_MARKERS)
        & source["KSLabel"].eq("good")
    ].copy()
    source["condition"] = source["well"].map(condition_map)
    source = source.loc[source["condition"].notna()].copy()
    if source.empty:
        raise SystemExit("No matching KSLabel=good units were found.")

    unit_rows: list[dict[str, object]] = []
    psth_rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    bin_edges = np.arange(PSTH_START_MS, PSTH_END_MS + PSTH_BIN_MS, PSTH_BIN_MS)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    analyzer_groups = list(source.groupby("analyzer_path", sort=True))
    for progress, (analyzer_path_text, group) in enumerate(analyzer_groups, start=1):
        analyzer_path = Path(str(analyzer_path_text))
        recording = str(group.iloc[0]["recording"])
        well = str(group.iloc[0]["well"])
        variant = str(group.iloc[0]["raw_variant"])
        try:
            analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=False)
            sorting = analyzer.sorting
            sampling_frequency = float(sorting.get_sampling_frequency())
            unit_ids = list(sorting.get_unit_ids())
            resolution = resolve_stim_sidecars(
                recording,
                well,
                analyzer_path=analyzer_path,
                raw_roots=DEFAULT_STIM_RAW_ROOTS,
                plate_family="lumos_48well",
            )
            if (
                not resolution.eligibility.enabled
                or resolution.stim_events is None
                or resolution.pulse_structure is None
            ):
                raise ValueError(resolution.eligibility.message)
            pulse_onsets = np.asarray(
                [
                    float(event.event_time_s) + pulse.start_ms / 1000.0
                    for event in resolution.stim_events.itertuples(index=False)
                    for pulse in resolution.pulse_structure.pulse_epochs
                ],
                dtype=float,
            )
            if len(pulse_onsets) != args.expected_pulse_trials:
                raise ValueError(
                    f"expected {args.expected_pulse_trials} pulses, found {len(pulse_onsets)}"
                )

            analyzer_histogram = np.zeros(len(bin_centers), dtype=float)
            for _, unit_row in group.iterrows():
                unit_id = _match_unit_id(unit_ids, unit_row["unit_id"])
                spike_times = np.sort(
                    np.asarray(sorting.get_unit_spike_train(unit_id=unit_id), dtype=float)
                    / sampling_frequency
                )
                analyzer_histogram += _relative_histogram(
                    spike_times, pulse_onsets, bin_edges
                )
                base = {
                    "recording": recording,
                    "biological_recording": _biological_recording(recording),
                    "well": well,
                    "condition": condition_map[well],
                    "raw_variant": variant,
                    "unit_id": _unit_label(unit_id),
                    "unit_key": f"{recording}|{well}|{_unit_label(unit_id)}",
                    "pulse_trials": len(pulse_onsets),
                    "analyzer_path": str(analyzer_path),
                }
                for window_name, duration_ms in WINDOWS:
                    pre = _counts_by_trial(
                        spike_times, pulse_onsets, -duration_ms, 0.0
                    )
                    post = _counts_by_trial(
                        spike_times, pulse_onsets, 0.0, duration_ms
                    )
                    exposure_s = len(pulse_onsets) * duration_ms / 1000.0
                    pre_total = int(pre.sum())
                    post_total = int(post.sum())
                    total = pre_total + post_total
                    p_value = (
                        binomtest(post_total, total, 0.5, alternative="two-sided").pvalue
                        if total
                        else 1.0
                    )
                    unit_rows.append(
                        {
                            **base,
                            "window": window_name,
                            "window_ms": duration_ms,
                            "pre_spikes": pre_total,
                            "post_spikes": post_total,
                            "pre_rate_hz": pre_total / exposure_s,
                            "post_rate_hz": post_total / exposure_s,
                            "rate_delta_hz": (post_total - pre_total) / exposure_s,
                            "pre_hit_fraction": float(np.mean(pre > 0)),
                            "post_hit_fraction": float(np.mean(post > 0)),
                            "hit_fraction_delta": float(np.mean(post > 0) - np.mean(pre > 0)),
                            "individual_exact_p": p_value,
                        }
                    )

            analyzer_rate = analyzer_histogram / (
                len(group) * len(pulse_onsets) * PSTH_BIN_MS / 1000.0
            )
            for center, rate in zip(bin_centers, analyzer_rate, strict=True):
                psth_rows.append(
                    {
                        "recording": recording,
                        "biological_recording": _biological_recording(recording),
                        "well": well,
                        "condition": condition_map[well],
                        "raw_variant": variant,
                        "n_good_units": len(group),
                        "bin_center_ms": center,
                        "mean_unit_rate_hz": rate,
                    }
                )
            status = f"{len(group)} good units"
        except Exception as exc:  # noqa: BLE001
            status = "error"
            errors.append(
                {
                    "recording": recording,
                    "well": well,
                    "analyzer_path": str(analyzer_path),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        print(
            f"[{progress:03d}/{len(analyzer_groups):03d}] {well} / {variant}: {status}",
            flush=True,
        )

    units = pd.DataFrame(unit_rows)
    analyzer_psth = pd.DataFrame(psth_rows)
    if units.empty or analyzer_psth.empty:
        raise SystemExit("No response metrics could be calculated.")
    units["individual_fdr_q_within_window"] = units.groupby("window")[
        "individual_exact_p"
    ].transform(_benjamini_hochberg)
    units["individually_enhanced_fdr05"] = (
        units["individual_fdr_q_within_window"].lt(0.05)
        & units["rate_delta_hz"].gt(0)
    )

    analyzer_summary, recording_summary, well_summary = _nested_window_summaries(units)
    tests = _independent_window_tests(well_summary)
    well_psth, psth_tests = _nested_psth_tests(analyzer_psth)
    state_tests = _activity_state_tests(well_summary)
    variant_sensitivity = _variant_sensitivity_tests(analyzer_summary)
    leave_one_well_out = _leave_one_well_out_state_tests(well_summary)

    outputs = {
        "unit_window_metrics": output_dir / f"{STEM}_unit_window_metrics.csv",
        "analyzer_window_summary": output_dir / f"{STEM}_analyzer_window_summary.csv",
        "recording_window_summary": output_dir / f"{STEM}_recording_window_summary.csv",
        "well_window_summary": output_dir / f"{STEM}_well_window_summary.csv",
        "independent_window_tests": output_dir / f"{STEM}_independent_window_tests.csv",
        "well_psth": output_dir / f"{STEM}_well_psth.csv",
        "psth_exact_tests": output_dir / f"{STEM}_psth_exact_tests.csv",
        "activity_state_tests": output_dir / f"{STEM}_activity_state_tests.csv",
        "variant_sensitivity_tests": output_dir / f"{STEM}_variant_sensitivity_tests.csv",
        "leave_one_well_out_state_tests": output_dir / f"{STEM}_leave_one_well_out_state_tests.csv",
        "errors": output_dir / f"{STEM}_errors.csv",
    }
    units.to_csv(outputs["unit_window_metrics"], index=False)
    analyzer_summary.to_csv(outputs["analyzer_window_summary"], index=False)
    recording_summary.to_csv(outputs["recording_window_summary"], index=False)
    well_summary.to_csv(outputs["well_window_summary"], index=False)
    tests.to_csv(outputs["independent_window_tests"], index=False)
    well_psth.to_csv(outputs["well_psth"], index=False)
    psth_tests.to_csv(outputs["psth_exact_tests"], index=False)
    state_tests.to_csv(outputs["activity_state_tests"], index=False)
    variant_sensitivity.to_csv(outputs["variant_sensitivity_tests"], index=False)
    leave_one_well_out.to_csv(outputs["leave_one_well_out_state_tests"], index=False)
    pd.DataFrame(
        errors, columns=["recording", "well", "analyzer_path", "error"]
    ).to_csv(outputs["errors"], index=False)

    figure_paths = _plot_results(
        plt, well_summary, tests, well_psth, psth_tests, state_tests, output_dir
    )
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "analysis_population": "KSLabel=good only",
        "independent_unit": "organoid well (4 opsin wells, 6 no-opsin wells)",
        "nesting": (
            "units summarized within analyzer; raw variants averaged within biological "
            "recording; repeated recordings averaged within well"
        ),
        "condition_assignment": (
            "user-confirmed plate rule: columns 1-4 no_opsin, columns 5-8 opsin"
        ),
        "primary_endpoint": (
            "mean per-good-unit post-minus-pre firing-rate change in matched 9.5-ms windows"
        ),
        "secondary_windows_ms": [duration for _, duration in WINDOWS if duration != 9.5],
        "multiple_testing": (
            "Holm correction across five latency windows within each response metric; "
            "PSTH bins use an exact max-|T| permutation correction"
        ),
        "permutation_space": "all C(10,4)=210 assignments of four opsin labels to ten wells",
        "raw_variants": list(VARIANT_MARKERS),
        "pulse_trials": args.expected_pulse_trials,
        "silent_trials": "retained",
        "plate_design_limitation": (
            "opsin status is confounded with left/right plate position, so the exact "
            "permutation test assumes wells would otherwise be exchangeable"
        ),
        "outputs": {key: str(value) for key, value in outputs.items()}
        | {"figures": [str(path) for path in figure_paths]},
    }
    (output_dir / f"{STEM}_provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )

    print("\nPrimary independent response test:")
    print(
        tests.loc[
            tests["window"].eq(PRIMARY_WINDOW)
            & tests["metric"].eq("mean_rate_delta_hz")
        ].to_string(index=False)
    )
    print("\nAbsolute activity-state tests:")
    print(state_tests.to_string(index=False))
    print("\nSmallest corrected PSTH p value:")
    print(psth_tests.nsmallest(5, "max_abs_fwer_p").to_string(index=False))
    print(f"\nOutput directory: {output_dir}")
    return 0


def _counts_by_trial(
    spike_times_s: np.ndarray,
    pulse_onsets_s: np.ndarray,
    start_ms: float,
    end_ms: float,
) -> np.ndarray:
    starts = pulse_onsets_s + start_ms / 1000.0
    ends = pulse_onsets_s + end_ms / 1000.0
    return np.searchsorted(spike_times_s, ends, side="left") - np.searchsorted(
        spike_times_s, starts, side="left"
    )


def _relative_histogram(
    spike_times_s: np.ndarray,
    pulse_onsets_s: np.ndarray,
    bin_edges_ms: np.ndarray,
) -> np.ndarray:
    histogram = np.zeros(len(bin_edges_ms) - 1, dtype=float)
    start_ms = float(bin_edges_ms[0])
    end_ms = float(bin_edges_ms[-1])
    for onset in pulse_onsets_s:
        left = np.searchsorted(spike_times_s, onset + start_ms / 1000.0, side="left")
        right = np.searchsorted(spike_times_s, onset + end_ms / 1000.0, side="left")
        relative_ms = (spike_times_s[left:right] - onset) * 1000.0
        histogram += np.histogram(relative_ms, bins=bin_edges_ms)[0]
    return histogram


def _biological_recording(recording: str) -> str:
    return re.sub(
        r"_(?:filter_200Hz-3kHz|primary_Neural_Broadband_hp_0\.1_Hz_IIR_lp_None)$",
        "",
        recording,
    )


def _benjamini_hochberg(values: pd.Series) -> np.ndarray:
    p_values = values.to_numpy(dtype=float)
    order = np.argsort(p_values)
    ranked = p_values[order]
    adjusted = np.minimum.accumulate(
        (ranked * len(ranked) / np.arange(1, len(ranked) + 1))[::-1]
    )[::-1]
    result = np.empty_like(adjusted)
    result[order] = np.minimum(adjusted, 1.0)
    return result


def _nested_window_summaries(
    units: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    group_columns = [
        "well",
        "condition",
        "biological_recording",
        "recording",
        "raw_variant",
        "window",
        "window_ms",
    ]
    analyzer = (
        units.groupby(group_columns, dropna=False)
        .agg(
            n_good_units=("unit_id", "size"),
            mean_pre_rate_hz=("pre_rate_hz", "mean"),
            mean_post_rate_hz=("post_rate_hz", "mean"),
            mean_rate_delta_hz=("rate_delta_hz", "mean"),
            median_rate_delta_hz=("rate_delta_hz", "median"),
            mean_hit_fraction_delta=("hit_fraction_delta", "mean"),
            positive_unit_fraction=("rate_delta_hz", lambda values: float(np.mean(values > 0))),
            fdr_enhanced_unit_fraction=("individually_enhanced_fdr05", "mean"),
        )
        .reset_index()
    )
    metrics = [
        "mean_pre_rate_hz",
        "mean_post_rate_hz",
        "mean_rate_delta_hz",
        "median_rate_delta_hz",
        "mean_hit_fraction_delta",
        "positive_unit_fraction",
        "fdr_enhanced_unit_fraction",
    ]
    recording = (
        analyzer.groupby(
            ["well", "condition", "biological_recording", "window", "window_ms"],
            dropna=False,
        )[metrics]
        .mean()
        .reset_index()
    )
    well = (
        recording.groupby(["well", "condition", "window", "window_ms"], dropna=False)
        .agg(
            **{metric: (metric, "mean") for metric in metrics},
            biological_recordings=("biological_recording", "nunique"),
        )
        .reset_index()
    )
    return analyzer, recording, well


def _exact_label_permutation(
    values: np.ndarray, labels: np.ndarray
) -> tuple[float, float, float, np.ndarray]:
    values = np.asarray(values, dtype=float)
    labels = np.asarray(labels, dtype=bool)
    observed = float(values[labels].mean() - values[~labels].mean())
    null = []
    for indices in combinations(range(len(values)), int(labels.sum())):
        permuted = np.zeros(len(values), dtype=bool)
        permuted[list(indices)] = True
        null.append(values[permuted].mean() - values[~permuted].mean())
    null_array = np.asarray(null, dtype=float)
    tolerance = 1e-12
    two_sided = float(np.mean(np.abs(null_array) >= abs(observed) - tolerance))
    greater = float(np.mean(null_array >= observed - tolerance))
    return observed, two_sided, greater, null_array


def _holm_adjust(values: pd.Series) -> np.ndarray:
    p_values = values.to_numpy(dtype=float)
    order = np.argsort(p_values)
    adjusted_ordered = np.maximum.accumulate(
        p_values[order] * (len(p_values) - np.arange(len(p_values)))
    )
    result = np.empty_like(adjusted_ordered)
    result[order] = np.minimum(adjusted_ordered, 1.0)
    return result


def _independent_window_tests(well: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "mean_rate_delta_hz",
        "median_rate_delta_hz",
        "mean_hit_fraction_delta",
        "positive_unit_fraction",
        "fdr_enhanced_unit_fraction",
    ]
    rows = []
    for window_name, duration_ms in WINDOWS:
        subset = well.loc[well["window"].eq(window_name)].sort_values("well")
        labels = subset["condition"].eq("opsin").to_numpy()
        for metric in metrics:
            observed, p_two, p_greater, _ = _exact_label_permutation(
                subset[metric].to_numpy(dtype=float), labels
            )
            rows.append(
                {
                    "window": window_name,
                    "window_ms": duration_ms,
                    "metric": metric,
                    "opsin_minus_no_opsin": observed,
                    "exact_p_two_sided": p_two,
                    "exact_p_greater": p_greater,
                    "opsin_wells": int(labels.sum()),
                    "no_opsin_wells": int((~labels).sum()),
                    "is_primary_endpoint": (
                        window_name == PRIMARY_WINDOW and metric == "mean_rate_delta_hz"
                    ),
                }
            )
    tests = pd.DataFrame(rows)
    tests["holm_p_two_sided_across_windows"] = tests.groupby("metric")[
        "exact_p_two_sided"
    ].transform(_holm_adjust)
    tests["holm_p_greater_across_windows"] = tests.groupby("metric")[
        "exact_p_greater"
    ].transform(_holm_adjust)
    return tests


def _nested_psth_tests(
    analyzer_psth: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    recording = (
        analyzer_psth.groupby(
            ["well", "condition", "biological_recording", "bin_center_ms"],
            dropna=False,
        )["mean_unit_rate_hz"]
        .mean()
        .reset_index()
    )
    well = (
        recording.groupby(["well", "condition", "bin_center_ms"], dropna=False)[
            "mean_unit_rate_hz"
        ]
        .mean()
        .reset_index()
    )
    baseline = (
        well.loc[(well["bin_center_ms"] >= -25.0) & (well["bin_center_ms"] < -5.0)]
        .groupby("well")["mean_unit_rate_hz"]
        .mean()
    )
    well["baseline_rate_hz"] = well["well"].map(baseline)
    well["baseline_subtracted_rate_hz"] = (
        well["mean_unit_rate_hz"] - well["baseline_rate_hz"]
    )
    matrix = well.pivot(index="well", columns="bin_center_ms", values="baseline_subtracted_rate_hz")
    condition = well.drop_duplicates("well").set_index("well")["condition"].reindex(matrix.index)
    labels = condition.eq("opsin").to_numpy()
    test_columns = np.flatnonzero(
        (matrix.columns.to_numpy(dtype=float) >= 0.0)
        & (matrix.columns.to_numpy(dtype=float) < PSTH_TEST_END_MS)
    )
    values = matrix.to_numpy(dtype=float)
    observed = values[labels].mean(axis=0) - values[~labels].mean(axis=0)
    null = []
    for indices in combinations(range(len(values)), int(labels.sum())):
        permuted = np.zeros(len(values), dtype=bool)
        permuted[list(indices)] = True
        null.append(values[permuted].mean(axis=0) - values[~permuted].mean(axis=0))
    null_array = np.asarray(null, dtype=float)
    max_abs = np.max(np.abs(null_array[:, test_columns]), axis=1)
    max_positive = np.max(null_array[:, test_columns], axis=1)
    rows = []
    for column_index in test_columns:
        effect = observed[column_index]
        rows.append(
            {
                "bin_center_ms": float(matrix.columns[column_index]),
                "opsin_minus_no_opsin_baseline_subtracted_hz": effect,
                "pointwise_exact_p_two_sided": float(
                    np.mean(np.abs(null_array[:, column_index]) >= abs(effect) - 1e-12)
                ),
                "max_abs_fwer_p": float(np.mean(max_abs >= abs(effect) - 1e-12)),
                "max_positive_fwer_p": float(np.mean(max_positive >= effect - 1e-12)),
            }
        )
    return well, pd.DataFrame(rows)


def _activity_state_tests(well: pd.DataFrame) -> pd.DataFrame:
    subset = well.loc[well["window"].eq("standard_0_25ms")].sort_values("well")
    labels = subset["condition"].eq("opsin").to_numpy()
    rows = []
    for metric in ["mean_pre_rate_hz", "mean_post_rate_hz"]:
        effect, p_two, p_greater, _ = _exact_label_permutation(
            subset[metric].to_numpy(dtype=float), labels
        )
        rows.append(
            {
                "test": metric,
                "opsin_minus_no_opsin_hz": effect,
                "exact_p_two_sided": p_two,
                "exact_p_greater": p_greater,
            }
        )
    pre = subset["mean_pre_rate_hz"].to_numpy(dtype=float)
    post = subset["mean_post_rate_hz"].to_numpy(dtype=float)
    fixed = np.column_stack([np.ones(len(pre)), pre])

    def coefficient(group: np.ndarray) -> float:
        design = np.column_stack([fixed, group.astype(float)])
        return float(np.linalg.lstsq(design, post, rcond=None)[0][-1])

    observed = coefficient(labels)
    null = []
    for indices in combinations(range(len(pre)), int(labels.sum())):
        permuted = np.zeros(len(pre), dtype=bool)
        permuted[list(indices)] = True
        null.append(coefficient(permuted))
    null_array = np.asarray(null, dtype=float)
    rows.append(
        {
            "test": "post_rate_adjusted_for_pre_rate",
            "opsin_minus_no_opsin_hz": observed,
            "exact_p_two_sided": float(np.mean(np.abs(null_array) >= abs(observed) - 1e-12)),
            "exact_p_greater": float(np.mean(null_array >= observed - 1e-12)),
        }
    )
    result = pd.DataFrame(rows)
    result.loc[result["test"].isin(["mean_pre_rate_hz", "mean_post_rate_hz"]), "holm_p_two_state_rates"] = _holm_adjust(
        result.loc[
            result["test"].isin(["mean_pre_rate_hz", "mean_post_rate_hz"]),
            "exact_p_two_sided",
        ]
    )
    return result


def _variant_sensitivity_tests(analyzer: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for variant in sorted(analyzer["raw_variant"].unique()):
        variant_table = analyzer.loc[analyzer["raw_variant"].eq(variant)]
        for window_name, duration_ms in WINDOWS:
            subset = (
                variant_table.loc[variant_table["window"].eq(window_name)]
                .groupby(["well", "condition"], dropna=False)[
                    ["mean_pre_rate_hz", "mean_post_rate_hz", "mean_rate_delta_hz"]
                ]
                .mean()
                .reset_index()
            )
            labels = subset["condition"].eq("opsin").to_numpy()
            for metric in ["mean_rate_delta_hz"] + (
                ["mean_pre_rate_hz", "mean_post_rate_hz"]
                if window_name == "standard_0_25ms"
                else []
            ):
                effect, p_two, p_greater, _ = _exact_label_permutation(
                    subset[metric].to_numpy(dtype=float), labels
                )
                rows.append(
                    {
                        "raw_variant": variant,
                        "window": window_name,
                        "window_ms": duration_ms,
                        "metric": metric,
                        "wells": len(subset),
                        "opsin_wells": int(labels.sum()),
                        "no_opsin_wells": int((~labels).sum()),
                        "opsin_minus_no_opsin": effect,
                        "exact_p_two_sided": p_two,
                        "exact_p_greater": p_greater,
                    }
                )
    return pd.DataFrame(rows)


def _leave_one_well_out_state_tests(well: pd.DataFrame) -> pd.DataFrame:
    state = well.loc[well["window"].eq("standard_0_25ms")].sort_values("well")
    rows = []
    for omitted_well in state["well"]:
        subset = state.loc[state["well"].ne(omitted_well)]
        labels = subset["condition"].eq("opsin").to_numpy()
        for metric in ["mean_pre_rate_hz", "mean_post_rate_hz"]:
            effect, p_two, p_greater, _ = _exact_label_permutation(
                subset[metric].to_numpy(dtype=float), labels
            )
            rows.append(
                {
                    "omitted_well": omitted_well,
                    "omitted_condition": state.loc[
                        state["well"].eq(omitted_well), "condition"
                    ].iloc[0],
                    "metric": metric,
                    "remaining_wells": len(subset),
                    "opsin_minus_no_opsin_hz": effect,
                    "exact_p_two_sided": p_two,
                    "exact_p_greater": p_greater,
                }
            )
    return pd.DataFrame(rows)


def _plot_results(
    plt, well, tests, well_psth, psth_tests, state_tests, output_dir: Path
) -> list[Path]:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    colors = {"opsin": "#2166ac", "no_opsin": "#68717d"}
    labels = {"opsin": "+ opsin", "no_opsin": "− opsin"}
    fig, axes = plt.subplots(2, 2, figsize=(12.4, 8.2))
    state = well.loc[well["window"].eq("standard_0_25ms")]
    for condition, x_offset in [("opsin", 0.0), ("no_opsin", 3.0)]:
        subset = state.loc[state["condition"].eq(condition)]
        for index, row in enumerate(subset.itertuples(index=False)):
            jitter = (index - (len(subset) - 1) / 2) * 0.035
            axes[0, 0].plot(
                [x_offset + jitter, x_offset + 1 + jitter],
                [row.mean_pre_rate_hz, row.mean_post_rate_hz],
                color=colors[condition],
                alpha=0.55,
                lw=1.0,
                marker="o",
                ms=4,
            )
    axes[0, 0].set_xticks([0, 1, 3, 4], ["Before", "After", "Before", "After"])
    axes[0, 0].text(0.16, 0.94, "+ opsin", transform=axes[0, 0].transAxes, ha="center", color=colors["opsin"], fontweight="bold")
    axes[0, 0].text(0.79, 0.94, "− opsin", transform=axes[0, 0].transAxes, ha="center", color=colors["no_opsin"], fontweight="bold")
    axes[0, 0].set_ylabel("Mean good-unit firing rate (Hz)")
    axes[0, 0].set_title("A  Independent organoid-well activity")
    before_p = state_tests.loc[
        state_tests["test"].eq("mean_pre_rate_hz"), "holm_p_two_state_rates"
    ].iloc[0]
    after_p = state_tests.loc[
        state_tests["test"].eq("mean_post_rate_hz"), "holm_p_two_state_rates"
    ].iloc[0]
    adjusted_p = state_tests.loc[
        state_tests["test"].eq("post_rate_adjusted_for_pre_rate"), "exact_p_two_sided"
    ].iloc[0]
    axes[0, 0].text(
        0.02,
        0.02,
        f"Absolute rates: before Holm p={before_p:.3f}; after Holm p={after_p:.3f}\n"
        f"After adjusted for before: exact p={adjusted_p:.3f}",
        transform=axes[0, 0].transAxes,
        va="bottom",
        color="#374151",
        fontsize=8,
    )

    order = [name for name, _ in WINDOWS]
    durations = [duration for _, duration in WINDOWS]
    for condition, offset in [("opsin", -0.12), ("no_opsin", 0.12)]:
        for index, window_name in enumerate(order):
            values = well.loc[
                well["condition"].eq(condition) & well["window"].eq(window_name),
                "mean_rate_delta_hz",
            ].to_numpy(dtype=float)
            axes[0, 1].scatter(
                np.full(len(values), index + offset),
                values,
                color=colors[condition],
                s=24,
                alpha=0.72,
                label=labels[condition] if index == 0 else None,
            )
            axes[0, 1].plot(
                [index + offset - 0.07, index + offset + 0.07],
                [values.mean(), values.mean()],
                color=colors[condition],
                lw=3,
            )
    axes[0, 1].axhline(0, color="#6b7280", ls="--", lw=0.8)
    axes[0, 1].set_xticks(range(len(order)), [f"{value:g}" for value in durations])
    axes[0, 1].set_xlabel("Matched before/after window (ms)")
    axes[0, 1].set_ylabel("After − before (Hz)")
    axes[0, 1].set_title("B  Response change across prespecified windows")
    axes[0, 1].legend(frameon=False)

    group_psth = (
        well_psth.groupby(["condition", "bin_center_ms"])["baseline_subtracted_rate_hz"]
        .agg(["mean", "sem"])
        .reset_index()
    )
    for condition in ["opsin", "no_opsin"]:
        subset = group_psth.loc[group_psth["condition"].eq(condition)]
        x = subset["bin_center_ms"].to_numpy(dtype=float)
        mean = subset["mean"].to_numpy(dtype=float)
        sem = subset["sem"].to_numpy(dtype=float)
        axes[1, 0].plot(x, mean, color=colors[condition], lw=1.8, label=labels[condition])
        axes[1, 0].fill_between(x, mean - sem, mean + sem, color=colors[condition], alpha=0.17)
    axes[1, 0].axvspan(0, 9.5, color="#f59e0b", alpha=0.13, lw=0)
    axes[1, 0].axvline(0, color="#9f1239", ls="--", lw=0.8)
    axes[1, 0].axhline(0, color="#6b7280", ls=":", lw=0.7)
    axes[1, 0].set_xlim(PSTH_START_MS, PSTH_END_MS)
    axes[1, 0].set_xlabel("Time from pulse onset (ms)")
    axes[1, 0].set_ylabel("Baseline-subtracted mean-unit rate (Hz)")
    axes[1, 0].set_title("C  Millisecond-resolved response across wells")
    axes[1, 0].legend(frameon=False)

    axes[1, 1].plot(
        psth_tests["bin_center_ms"],
        psth_tests["opsin_minus_no_opsin_baseline_subtracted_hz"],
        color="#7c3aed",
        lw=1.6,
    )
    significant = psth_tests["max_abs_fwer_p"].lt(0.05)
    axes[1, 1].scatter(
        psth_tests.loc[significant, "bin_center_ms"],
        psth_tests.loc[significant, "opsin_minus_no_opsin_baseline_subtracted_hz"],
        color="#b91c1c",
        s=28,
        zorder=3,
        label="max-|T| FWER p<0.05",
    )
    axes[1, 1].axvspan(0, 9.5, color="#f59e0b", alpha=0.13, lw=0)
    axes[1, 1].axhline(0, color="#6b7280", ls="--", lw=0.8)
    axes[1, 1].set_xlim(0, PSTH_TEST_END_MS)
    axes[1, 1].set_xlabel("Time from pulse onset (ms)")
    axes[1, 1].set_ylabel("Opsin − no-opsin evoked change (Hz)")
    axes[1, 1].set_title("D  Exact well-permutation PSTH contrast")
    if significant.any():
        axes[1, 1].legend(frameon=False)

    for axis in axes.flat:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#e5e7eb", lw=0.65)
    primary = tests.loc[
        tests["window"].eq(PRIMARY_WINDOW)
        & tests["metric"].eq("mean_rate_delta_hz")
    ].iloc[0]
    fig.suptitle(
        "Good units only: independent-well test of opsin-associated optical response",
        x=0.055,
        y=0.985,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.953,
        "4 opsin vs 6 no-opsin organoid wells · raw variants averaged within recording · "
        "repeated recordings averaged within well · all 250 pulses retained · "
        f"primary 9.5-ms Δ exact p={primary.exact_p_two_sided:.3f}",
        ha="left",
        color="#4b5563",
        fontsize=9,
    )
    fig.tight_layout(rect=[0.03, 0.03, 1, 0.93], h_pad=2.2, w_pad=2.2)
    paths = []
    for suffix in ("png", "pdf", "svg"):
        path = output_dir / f"{STEM}.{suffix}"
        kwargs = {"bbox_inches": "tight", "facecolor": "white"}
        if suffix == "png":
            kwargs["dpi"] = 350
        fig.savefig(path, **kwargs)
        paths.append(path)
    plt.close(fig)
    return paths


if __name__ == "__main__":
    raise SystemExit(main())
