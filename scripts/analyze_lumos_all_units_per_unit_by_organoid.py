#!/usr/bin/env python
"""Analyze every Lumos unit within organoid using 250 pulses and 50 five-pulse trains."""

from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t, wilcoxon

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.analyze_lumos_good_opsin_independent_significance import (  # noqa: E402
    _counts_by_trial,
)
from scripts.launch_step1_sorting_analyzer_browser import DEFAULT_STIM_RAW_ROOTS  # noqa: E402
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
STEM = "lumos_all_units_per_unit_by_organoid_250pulse_vs_50train_20260713"
METHOD_ORDER = ["250_pulses", "50_trains_x5_pulses"]
METHOD_LABELS = {
    "250_pulses": "250 pulse trials",
    "50_trains_x5_pulses": "50 train blocks × 5 pulses",
}
CONDITION_LABELS = {"opsin": "+ opsin", "no_opsin": "− opsin"}
UNIT_COLORS = {"good": "#2166ac", "mua": "#d97706"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-metrics-csv", type=Path, default=DEFAULT_UNIT_METRICS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_JOB_DIR / STEM)
    parser.add_argument("--window-ms", type=float, default=25.0)
    parser.add_argument("--expected-trains", type=int, default=50)
    parser.add_argument("--expected-pulses-per-train", type=int, default=5)
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
        & source["KSLabel"].isin(["good", "mua"])
    ].copy()
    source["condition"] = source["well"].map(condition_map)
    source = source.loc[source["condition"].notna()].copy()
    if source.empty:
        raise SystemExit("No eligible good/MUA units were found.")

    unit_rows: list[dict[str, object]] = []
    trial_rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    analyzer_groups = list(source.groupby("analyzer_path", sort=True))
    for progress, (analyzer_path_text, group) in enumerate(analyzer_groups, start=1):
        analyzer_path = Path(str(analyzer_path_text))
        recording = str(group.iloc[0]["recording"])
        well = str(group.iloc[0]["well"])
        raw_variant = str(group.iloc[0]["raw_variant"])
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
            train_events = list(resolution.stim_events.itertuples(index=False))
            pulse_epochs = list(resolution.pulse_structure.pulse_epochs)
            if len(train_events) != args.expected_trains:
                raise ValueError(
                    f"expected {args.expected_trains} train trials, found {len(train_events)}"
                )
            if len(pulse_epochs) != args.expected_pulses_per_train:
                raise ValueError(
                    f"expected {args.expected_pulses_per_train} pulses/train, "
                    f"found {len(pulse_epochs)}"
                )
            pulse_onsets = np.asarray(
                [
                    float(event.event_time_s) + pulse.start_ms / 1000.0
                    for event in train_events
                    for pulse in pulse_epochs
                ],
                dtype=float,
            )
            expected_pulses = args.expected_trains * args.expected_pulses_per_train
            if len(pulse_onsets) != expected_pulses:
                raise ValueError(f"expected {expected_pulses} pulses, found {len(pulse_onsets)}")

            for _, unit_row in group.iterrows():
                unit_id = _match_unit_id(unit_ids, unit_row["unit_id"])
                unit_label = _unit_label(unit_id)
                spike_times = np.sort(
                    np.asarray(sorting.get_unit_spike_train(unit_id=unit_id), dtype=float)
                    / sampling_frequency
                )
                pulse_pre = _counts_by_trial(
                    spike_times, pulse_onsets, -args.window_ms, 0.0
                ).reshape(args.expected_trains, args.expected_pulses_per_train)
                pulse_post = _counts_by_trial(
                    spike_times, pulse_onsets, 0.0, args.window_ms
                ).reshape(args.expected_trains, args.expected_pulses_per_train)
                train_pre = pulse_pre.sum(axis=1)
                train_post = pulse_post.sum(axis=1)
                unit_key = f"{recording}|{well}|{unit_label}"
                base = {
                    "unit_key": unit_key,
                    "recording": recording,
                    "recording_label": _recording_label(recording, raw_variant),
                    "well": well,
                    "organoid_id": well,
                    "condition": condition_map[well],
                    "condition_label": CONDITION_LABELS[condition_map[well]],
                    "raw_variant": raw_variant,
                    "unit_id": unit_label,
                    "KSLabel": str(unit_row["KSLabel"]),
                    "analyzer_path": str(analyzer_path),
                }
                unit_rows.append(
                    _unit_method_summary(
                        base,
                        "250_pulses",
                        pulse_pre.ravel(),
                        pulse_post.ravel(),
                        args.window_ms,
                        pulses_per_observation=1,
                    )
                )
                unit_rows.append(
                    _unit_method_summary(
                        base,
                        "50_trains_x5_pulses",
                        train_pre,
                        train_post,
                        args.window_ms,
                        pulses_per_observation=args.expected_pulses_per_train,
                    )
                )
                for train_index in range(args.expected_trains):
                    for pulse_index in range(args.expected_pulses_per_train):
                        trial_rows.append(
                            {
                                **base,
                                "method": "250_pulses",
                                "observation_index": (
                                    train_index * args.expected_pulses_per_train + pulse_index + 1
                                ),
                                "train_index": train_index + 1,
                                "pulse_in_train": pulse_index + 1,
                                "pre_spikes": int(pulse_pre[train_index, pulse_index]),
                                "post_spikes": int(pulse_post[train_index, pulse_index]),
                            }
                        )
                    trial_rows.append(
                        {
                            **base,
                            "method": "50_trains_x5_pulses",
                            "observation_index": train_index + 1,
                            "train_index": train_index + 1,
                            "pulse_in_train": "all_5",
                            "pre_spikes": int(train_pre[train_index]),
                            "post_spikes": int(train_post[train_index]),
                        }
                    )
            status = f"{len(group)} units"
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
            f"[{progress:03d}/{len(analyzer_groups):03d}] {well} / {raw_variant}: {status}",
            flush=True,
        )

    units = pd.DataFrame(unit_rows)
    trials = pd.DataFrame(trial_rows)
    if units.empty:
        raise SystemExit("No unit responses were calculated.")
    units["unit_fdr_q_within_organoid_method"] = units.groupby(
        ["well", "method"], sort=False
    )["paired_wilcoxon_p"].transform(_benjamini_hochberg)
    units["enhanced_fdr05"] = (
        units["unit_fdr_q_within_organoid_method"].lt(0.05)
        & units["mean_delta_hz"].gt(0)
    )
    units["suppressed_fdr05"] = (
        units["unit_fdr_q_within_organoid_method"].lt(0.05)
        & units["mean_delta_hz"].lt(0)
    )

    recording_summary = _recording_summary(units)
    organoid_tests = _organoid_recording_tests(recording_summary)
    concordance = _unit_method_concordance(units)

    outputs = {
        "unit_summary": output_dir / f"{STEM}_unit_summary.csv",
        "trial_counts": output_dir / f"{STEM}_trial_counts.csv.gz",
        "recording_summary": output_dir / f"{STEM}_recording_summary.csv",
        "organoid_recording_tests": output_dir / f"{STEM}_organoid_recording_tests.csv",
        "method_concordance": output_dir / f"{STEM}_method_concordance.csv",
        "errors": output_dir / f"{STEM}_errors.csv",
    }
    units.to_csv(outputs["unit_summary"], index=False)
    trials.to_csv(outputs["trial_counts"], index=False, compression="gzip")
    recording_summary.to_csv(outputs["recording_summary"], index=False)
    organoid_tests.to_csv(outputs["organoid_recording_tests"], index=False)
    concordance.to_csv(outputs["method_concordance"], index=False)
    pd.DataFrame(
        errors, columns=["recording", "well", "analyzer_path", "error"]
    ).to_csv(outputs["errors"], index=False)

    overview_paths = _plot_overview(
        plt, units, recording_summary, organoid_tests, output_dir
    )
    organoid_paths = _plot_organoid_pages(plt, units, organoid_tests, output_dir)
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "analysis_population": "all KSLabel=good and KSLabel=mua units",
        "unit_analysis": "each point/row is one unit within one recording and organoid well",
        "biological_replicate": (
            "recording exactly as stored in the unit table; raw-version suffixes are not "
            "stripped and recordings are not deduplicated"
        ),
        "filter_handling": (
            "primary_raw and filter_200Hz-3kHz are pooled; filter_1Hz-200Hz remains excluded"
        ),
        "trial_definitions": {
            "250_pulses": "250 paired pulse windows (50 trains x 5 pulses)",
            "50_trains_x5_pulses": (
                "50 paired train blocks; each observation sums the five pulse windows "
                "inside that train"
            ),
        },
        "window_ms": {
            "pre": [-args.window_ms, 0.0],
            "post": [0.0, args.window_ms],
            "applied_relative_to": "each pulse onset",
        },
        "per_unit_inference": (
            "paired Wilcoxon signed-rank test across 250 pulses or 50 five-pulse blocks; "
            "Benjamini-Hochberg FDR within organoid and method"
        ),
        "organoid_inference": (
            "units pooled within each recording; recording mean unit delta is the replicate; "
            "exact sign-flip test across recordings; no recording deduplication"
        ),
        "silent_trials": "retained",
        "outputs": {key: str(value) for key, value in outputs.items()}
        | {
            "overview_figures": [str(path) for path in overview_paths],
            "organoid_figures": [str(path) for path in organoid_paths],
        },
    }
    (output_dir / f"{STEM}_provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )

    print("\nUnit observations:", units["unit_key"].nunique())
    print("Recording replicates:", units["recording"].nunique())
    print("\nOrganoid recording-level tests:")
    print(organoid_tests.to_string(index=False))
    print(f"\nOutput directory: {output_dir}")
    return 0


def _unit_method_summary(
    base: dict[str, object],
    method: str,
    pre_counts: np.ndarray,
    post_counts: np.ndarray,
    window_ms: float,
    *,
    pulses_per_observation: int,
) -> dict[str, object]:
    exposure_s = pulses_per_observation * window_ms / 1000.0
    pre_rate = np.asarray(pre_counts, dtype=float) / exposure_s
    post_rate = np.asarray(post_counts, dtype=float) / exposure_s
    differences = post_rate - pre_rate
    mean_delta = float(np.mean(differences))
    sem = (
        float(np.std(differences, ddof=1) / np.sqrt(len(differences)))
        if len(differences) > 1
        else np.nan
    )
    critical = float(t.ppf(0.975, len(differences) - 1)) if len(differences) > 1 else np.nan
    p_value = _paired_wilcoxon_p(pre_counts, post_counts)
    return {
        **base,
        "method": method,
        "method_label": METHOD_LABELS[method],
        "paired_observations": len(differences),
        "pulses_per_observation": pulses_per_observation,
        "total_pulses": len(differences) * pulses_per_observation,
        "window_ms_per_pulse": window_ms,
        "pre_spikes": int(np.sum(pre_counts)),
        "post_spikes": int(np.sum(post_counts)),
        "mean_pre_rate_hz": float(np.mean(pre_rate)),
        "mean_post_rate_hz": float(np.mean(post_rate)),
        "mean_delta_hz": mean_delta,
        "median_observation_delta_hz": float(np.median(differences)),
        "sem_delta_hz": sem,
        "ci95_low_hz": mean_delta - critical * sem,
        "ci95_high_hz": mean_delta + critical * sem,
        "pre_hit_fraction": float(np.mean(np.asarray(pre_counts) > 0)),
        "post_hit_fraction": float(np.mean(np.asarray(post_counts) > 0)),
        "paired_wilcoxon_p": p_value,
    }


def _paired_wilcoxon_p(pre_counts: np.ndarray, post_counts: np.ndarray) -> float:
    differences = np.asarray(post_counts, dtype=float) - np.asarray(pre_counts, dtype=float)
    if not np.any(differences):
        return 1.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = wilcoxon(
            post_counts,
            pre_counts,
            zero_method="pratt",
            correction=False,
            alternative="two-sided",
            method="approx",
        )
    return float(result.pvalue) if np.isfinite(result.pvalue) else 1.0


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


def _recording_summary(units: pd.DataFrame) -> pd.DataFrame:
    return (
        units.groupby(
            [
                "well",
                "condition",
                "recording",
                "recording_label",
                "raw_variant",
                "method",
                "method_label",
            ],
            dropna=False,
        )
        .agg(
            unit_observations=("unit_key", "size"),
            good_units=("KSLabel", lambda values: int(np.sum(values == "good"))),
            mua_units=("KSLabel", lambda values: int(np.sum(values == "mua"))),
            mean_unit_pre_rate_hz=("mean_pre_rate_hz", "mean"),
            mean_unit_post_rate_hz=("mean_post_rate_hz", "mean"),
            mean_unit_delta_hz=("mean_delta_hz", "mean"),
            median_unit_delta_hz=("mean_delta_hz", "median"),
            enhanced_unit_fraction_fdr05=("enhanced_fdr05", "mean"),
            suppressed_unit_fraction_fdr05=("suppressed_fdr05", "mean"),
        )
        .reset_index()
    )


def _organoid_recording_tests(recordings: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (well, condition, method), group in recordings.groupby(
        ["well", "condition", "method"], sort=True
    ):
        values = group["mean_unit_delta_hz"].to_numpy(dtype=float)
        effect, p_two, p_greater, p_less = _exact_sign_flip(values)
        rows.append(
            {
                "well": well,
                "organoid_id": well,
                "condition": condition,
                "condition_label": CONDITION_LABELS[condition],
                "method": method,
                "method_label": METHOD_LABELS[method],
                "recording_replicates": len(values),
                "unit_observations": int(group["unit_observations"].sum()),
                "mean_recording_delta_hz": effect,
                "exact_sign_flip_p_two_sided": p_two,
                "exact_sign_flip_p_greater": p_greater,
                "exact_sign_flip_p_less": p_less,
                "mean_enhanced_unit_fraction_fdr05": float(
                    group["enhanced_unit_fraction_fdr05"].mean()
                ),
                "mean_suppressed_unit_fraction_fdr05": float(
                    group["suppressed_unit_fraction_fdr05"].mean()
                ),
            }
        )
    tests = pd.DataFrame(rows)
    tests["holm_p_two_sided_across_organoids"] = tests.groupby("method")[
        "exact_sign_flip_p_two_sided"
    ].transform(_holm_adjust)
    return tests


def _exact_sign_flip(values: np.ndarray) -> tuple[float, float, float, float]:
    values = np.asarray(values, dtype=float)
    observed = float(np.mean(values))
    count = 1 << len(values)
    codes = np.arange(count, dtype=np.uint32)[:, None]
    bits = ((codes >> np.arange(len(values), dtype=np.uint32)) & 1).astype(np.int8)
    signs = bits * 2 - 1
    null = (signs * values).mean(axis=1)
    return (
        observed,
        float(np.mean(np.abs(null) >= abs(observed) - 1e-12)),
        float(np.mean(null >= observed - 1e-12)),
        float(np.mean(null <= observed + 1e-12)),
    )


def _holm_adjust(values: pd.Series) -> np.ndarray:
    p_values = values.to_numpy(dtype=float)
    order = np.argsort(p_values)
    adjusted_ordered = np.maximum.accumulate(
        p_values[order] * (len(p_values) - np.arange(len(p_values)))
    )
    result = np.empty_like(adjusted_ordered)
    result[order] = np.minimum(adjusted_ordered, 1.0)
    return result


def _unit_method_concordance(units: pd.DataFrame) -> pd.DataFrame:
    wide = units.pivot(
        index=[
            "unit_key",
            "recording",
            "recording_label",
            "well",
            "condition",
            "raw_variant",
            "unit_id",
            "KSLabel",
        ],
        columns="method",
        values=[
            "mean_delta_hz",
            "paired_wilcoxon_p",
            "unit_fdr_q_within_organoid_method",
            "enhanced_fdr05",
            "suppressed_fdr05",
            "ci95_low_hz",
            "ci95_high_hz",
        ],
    )
    wide.columns = [f"{metric}_{method}" for metric, method in wide.columns]
    return wide.reset_index()


def _recording_label(recording: str, raw_variant: str) -> str:
    date = "6/22" if "6_22_2026" in recording else "6/18"
    match = re.search(r"\((\d{3})\)", recording)
    index = match.group(1) if match else "?"
    variant = "P" if raw_variant == "primary_raw" else "F"
    return f"{date}-{index}-{variant}"


def _plot_overview(plt, units, recordings, tests, output_dir: Path) -> list[Path]:
    _style(plt)
    wells = sorted(units["well"].unique(), key=lambda value: (int(value[1:]), value[0]))
    fig, axes = plt.subplots(2, 2, figsize=(13.2, 8.4))
    method = "50_trains_x5_pulses"
    recording_method = recordings.loc[recordings["method"].eq(method)]
    for well_index, well in enumerate(wells):
        subset = recording_method.loc[recording_method["well"].eq(well)]
        condition = subset["condition"].iloc[0]
        color = "#2166ac" if condition == "opsin" else "#68717d"
        x = np.full(len(subset), well_index, dtype=float)
        if len(subset) > 1:
            x += np.linspace(-0.14, 0.14, len(subset))
        axes[0, 0].scatter(x, subset["mean_unit_delta_hz"], color=color, s=28, alpha=0.75)
        axes[0, 0].plot(
            [well_index - 0.18, well_index + 0.18],
            [subset["mean_unit_delta_hz"].mean()] * 2,
            color=color,
            lw=3,
        )
    axes[0, 0].axhline(0, color="#6b7280", ls="--", lw=0.8)
    axes[0, 0].set_xticks(range(len(wells)), wells)
    axes[0, 0].set_ylabel("Recording mean unit Δ (Hz)")
    axes[0, 0].set_title("A  Recording replicates within each organoid")

    test_method = tests.loc[tests["method"].eq(method)].set_index("well").reindex(wells)
    axes[0, 1].bar(
        np.arange(len(wells)) - 0.18,
        test_method["mean_enhanced_unit_fraction_fdr05"],
        width=0.36,
        color="#2166ac",
        label="enhanced",
    )
    axes[0, 1].bar(
        np.arange(len(wells)) + 0.18,
        test_method["mean_suppressed_unit_fraction_fdr05"],
        width=0.36,
        color="#b45309",
        label="suppressed",
    )
    axes[0, 1].set_xticks(range(len(wells)), wells)
    axes[0, 1].set_ylabel("Mean per-recording FDR-significant fraction")
    axes[0, 1].set_title("B  Individually responsive units · 50-train analysis")
    axes[0, 1].legend(frameon=False)

    method_counts = (
        units.groupby(["well", "method"])[["enhanced_fdr05", "suppressed_fdr05"]]
        .sum()
        .reset_index()
    )
    for method_index, method_name in enumerate(METHOD_ORDER):
        subset = method_counts.loc[method_counts["method"].eq(method_name)].set_index("well").reindex(wells)
        axes[1, 0].plot(
            range(len(wells)),
            subset["enhanced_fdr05"],
            marker="o",
            lw=1.5,
            label=f"enhanced · {METHOD_LABELS[method_name]}",
            color=["#60a5fa", "#1d4ed8"][method_index],
        )
        axes[1, 0].plot(
            range(len(wells)),
            subset["suppressed_fdr05"],
            marker="s",
            lw=1.5,
            label=f"suppressed · {METHOD_LABELS[method_name]}",
            color=["#fbbf24", "#b45309"][method_index],
        )
    axes[1, 0].set_xticks(range(len(wells)), wells)
    axes[1, 0].set_ylabel("FDR-significant unit observations")
    axes[1, 0].set_title("C  Detection changes: 250 pulses versus 50 trains")
    axes[1, 0].legend(frameon=False, fontsize=8)

    inventory = (
        units.drop_duplicates("unit_key")
        .groupby(["well", "KSLabel"])
        .size()
        .unstack(fill_value=0)
        .reindex(wells)
    )
    bottom = np.zeros(len(wells))
    for label in ["good", "mua"]:
        values = inventory[label].to_numpy() if label in inventory else np.zeros(len(wells))
        axes[1, 1].bar(
            range(len(wells)),
            values,
            bottom=bottom,
            color=UNIT_COLORS[label],
            label=label,
        )
        bottom += values
    axes[1, 1].set_xticks(range(len(wells)), wells)
    axes[1, 1].set_ylabel("Unit observations pooled across recordings")
    axes[1, 1].set_title("D  Per-organoid unit inventory")
    axes[1, 1].legend(frameon=False)

    for axis in axes.flat:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#e5e7eb", lw=0.65)
    fig.suptitle(
        "All units analyzed within organoid: recording is the biological replicate",
        x=0.055,
        y=0.985,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.955,
        "Primary and 200 Hz–3 kHz recordings pooled without deduplication · "
        "250 pulse trials compared with 50 train blocks of five pulses · 25-ms matched windows",
        ha="left",
        color="#4b5563",
        fontsize=9,
    )
    fig.tight_layout(rect=[0.03, 0.03, 1, 0.93], h_pad=2.2, w_pad=2.0)
    return _save_figure(fig, output_dir / f"{STEM}_overview")


def _plot_organoid_pages(plt, units, tests, output_dir: Path) -> list[Path]:
    paths = []
    for well in sorted(units["well"].unique(), key=lambda value: (int(value[1:]), value[0])):
        subset = units.loc[units["well"].eq(well)].copy()
        order = (
            subset.drop_duplicates("unit_key")
            .sort_values(["recording_label", "KSLabel", "unit_id"])["unit_key"]
            .tolist()
        )
        x_map = {unit_key: index for index, unit_key in enumerate(order)}
        fig, axes = plt.subplots(3, 1, figsize=(13.2, 9.0), gridspec_kw={"height_ratios": [1, 1, 0.85]})
        for axis, method in zip(axes[:2], METHOD_ORDER, strict=True):
            data = subset.loc[subset["method"].eq(method)].copy()
            data["x"] = data["unit_key"].map(x_map)
            for label in ["good", "mua"]:
                group = data.loc[data["KSLabel"].eq(label)]
                axis.errorbar(
                    group["x"],
                    group["mean_delta_hz"],
                    yerr=[
                        group["mean_delta_hz"] - group["ci95_low_hz"],
                        group["ci95_high_hz"] - group["mean_delta_hz"],
                    ],
                    fmt="o",
                    ms=3.2,
                    lw=0.65,
                    capsize=1.2,
                    color=UNIT_COLORS[label],
                    alpha=0.72,
                    label=label,
                )
            significant = data["unit_fdr_q_within_organoid_method"].lt(0.05)
            axis.scatter(
                data.loc[significant, "x"],
                data.loc[significant, "mean_delta_hz"],
                facecolors="none",
                edgecolors="#111827",
                s=44,
                lw=0.9,
                zorder=4,
                label="FDR q<0.05",
            )
            axis.axhline(0, color="#6b7280", ls="--", lw=0.8)
            axis.set_ylabel("Unit after − before (Hz)")
            axis.set_title(METHOD_LABELS[method], loc="left", fontweight="bold")
            axis.legend(frameon=False, ncol=3, fontsize=8, loc="upper right")
            _recording_boundaries(axis, data, x_map)

        wide = subset.pivot(index="unit_key", columns="method", values="paired_wilcoxon_p")
        wide = wide.reindex(order)
        x_values = -np.log10(np.maximum(wide["250_pulses"].to_numpy(dtype=float), 1e-300))
        y_values = -np.log10(
            np.maximum(wide["50_trains_x5_pulses"].to_numpy(dtype=float), 1e-300)
        )
        labels = subset.drop_duplicates("unit_key").set_index("unit_key")["KSLabel"].reindex(order)
        for label in ["good", "mua"]:
            mask = labels.eq(label).to_numpy()
            axes[2].scatter(
                x_values[mask],
                y_values[mask],
                color=UNIT_COLORS[label],
                s=24,
                alpha=0.72,
                label=label,
            )
        limit = max(float(np.max(x_values)), float(np.max(y_values)), 1.5) * 1.05
        axes[2].plot([0, limit], [0, limit], color="#9ca3af", ls="--", lw=0.8)
        axes[2].axvline(-np.log10(0.05), color="#6b7280", ls=":", lw=0.8)
        axes[2].axhline(-np.log10(0.05), color="#6b7280", ls=":", lw=0.8)
        axes[2].set_xlim(0, limit)
        axes[2].set_ylim(0, limit)
        axes[2].set_xlabel("−log10 paired p · 250 pulses")
        axes[2].set_ylabel("−log10 paired p · 50 train blocks")
        axes[2].set_title("Trial-resolution comparison for every unit", loc="left", fontweight="bold")
        axes[2].legend(frameon=False)

        test = tests.loc[
            tests["well"].eq(well) & tests["method"].eq("50_trains_x5_pulses")
        ].iloc[0]
        condition_label = CONDITION_LABELS[test["condition"]]
        fig.suptitle(
            f"Organoid {well} · {condition_label} · every unit across {test.recording_replicates} recordings",
            x=0.055,
            y=0.995,
            ha="left",
            fontsize=14,
            fontweight="bold",
        )
        fig.text(
            0.055,
            0.965,
            f"n={test.unit_observations} pooled unit observations · recording-level mean Δ "
            f"{test.mean_recording_delta_hz:+.3f} Hz · exact sign-flip p="
            f"{test.exact_sign_flip_p_two_sided:.3f} · circles outlined in black pass within-organoid FDR",
            ha="left",
            color="#4b5563",
            fontsize=8.5,
        )
        for axis in axes:
            axis.spines[["top", "right"]].set_visible(False)
            axis.grid(axis="y", color="#e5e7eb", lw=0.6)
        fig.tight_layout(rect=[0.035, 0.03, 1, 0.94], h_pad=1.6)
        paths.extend(_save_figure(fig, output_dir / f"{STEM}_organoid_{well}"))
    return paths


def _recording_boundaries(axis, data: pd.DataFrame, x_map: dict[str, int]) -> None:
    labels = []
    centers = []
    boundaries = []
    for recording_label, group in data.groupby("recording_label", sort=False):
        positions = sorted(group["unit_key"].map(x_map).unique())
        if not positions:
            continue
        centers.append(float(np.mean(positions)))
        labels.append(recording_label)
        boundaries.append(max(positions) + 0.5)
    for boundary in boundaries[:-1]:
        axis.axvline(boundary, color="#d1d5db", lw=0.55)
    axis.set_xticks(centers, labels, rotation=75, ha="right", fontsize=6.5)
    axis.set_xlabel("Recording replicate (units pooled regardless of filter)")


def _style(plt) -> None:
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


def _save_figure(fig, base: Path) -> list[Path]:
    paths = []
    for suffix in ("png", "pdf", "svg"):
        path = base.with_suffix(f".{suffix}")
        kwargs = {"bbox_inches": "tight", "facecolor": "white"}
        if suffix == "png":
            kwargs["dpi"] = 350
        fig.savefig(path, **kwargs)
        paths.append(path)
    fig.clf()
    return paths


if __name__ == "__main__":
    raise SystemExit(main())
