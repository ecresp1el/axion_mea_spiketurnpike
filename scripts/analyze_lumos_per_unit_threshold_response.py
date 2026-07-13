#!/usr/bin/env python
"""Apply a literature-inspired two-criterion response rule independently per unit."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_lumos_all_units_unified_psth_store import (  # noqa: E402
    BOXCAR,
    DEFAULT_JOB_DIR,
    OUTPUT_NAME as PSTH_OUTPUT_NAME,
    STORE_NAME,
)


OUTPUT_NAME = "lumos_per_unit_threshold_response_development"
RESPONSE_THRESHOLD_HZ_ABOVE_BASELINE = 0.0
TARGETS = ["pulse_1", "pulse_2", "pulse_3", "pulse_4", "pulse_5", "train_250ms"]
COLORS = {"no_opsin": "#4C78A8", "opsin": "#E45756"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--psth-dir", type=Path, default=DEFAULT_JOB_DIR / PSTH_OUTPUT_NAME
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_JOB_DIR / OUTPUT_NAME)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    psth_dir = args.psth_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    metadata = pd.read_csv(psth_dir / "unit_metadata.csv")
    metric_rows: list[dict[str, object]] = []
    with h5py.File(psth_dir / STORE_NAME, "r") as source:
        pulse_time = source["axes/pulse_bin_centers_ms"][:]
        train_time = source["axes/train_bin_centers_ms"][:]
        spontaneous_mask = (train_time >= -500) & (train_time < 0)
        baseline_mask = (train_time >= -200) & (train_time < 0)
        train_response_mask = (train_time >= 0) & (train_time < 250)
        pulse_response_mask = (pulse_time >= 0) & (pulse_time < 50)
        _require_bins(spontaneous_mask, 500, "−500–0 ms spontaneous")
        _require_bins(baseline_mask, 200, "−200–0 ms baseline")
        _require_bins(train_response_mask, 250, "0–250 ms train response")
        _require_bins(pulse_response_mask, 50, "0–50 ms pulse response")

        for index, meta in metadata.iterrows():
            uid = str(meta["unit_observation_id"])
            group = source[f"units/{uid}"]
            pulse_smoothed = group["pulse_250/smoothed_rate_hz"][:].reshape(50, 5, -1)
            train_rate = group["train_full_50/rate_hz"][:]
            train_smoothed = group["train_full_50/smoothed_rate_hz"][:]

            spontaneous_rate = float(train_rate[:, spontaneous_mask].mean())
            subtraction_baseline_rate = float(train_rate[:, baseline_mask].mean())
            baseline_mean_psth = train_smoothed[:, baseline_mask].mean(axis=0)
            baseline_sd = float(np.std(baseline_mean_psth, ddof=1))

            common = {
                **{
                    key: meta[key]
                    for key in [
                        "unit_observation_id",
                        "unit_key",
                        "recording",
                        "well",
                        "organoid_id",
                        "condition",
                        "raw_variant",
                        "unit_id",
                        "KSLabel",
                        "waveform_class",
                    ]
                },
                "trials": 50,
                "spontaneous_window_start_ms": -500.0,
                "spontaneous_window_end_ms": 0.0,
                "spontaneous_rate_hz": spontaneous_rate,
                "subtraction_baseline_start_ms": -200.0,
                "subtraction_baseline_end_ms": 0.0,
                "subtraction_baseline_rate_hz": subtraction_baseline_rate,
                "baseline_trial_averaged_psth_sd_hz": baseline_sd,
                "response_threshold_hz_above_baseline": RESPONSE_THRESHOLD_HZ_ABOVE_BASELINE,
            }
            for pulse_index in range(5):
                response = pulse_smoothed[:, pulse_index, :][:, pulse_response_mask]
                metric_rows.append(
                    _response_metrics(
                        common,
                        f"pulse_{pulse_index + 1}",
                        response,
                        pulse_time[pulse_response_mask],
                    )
                )
            metric_rows.append(
                _response_metrics(
                    common,
                    "train_250ms",
                    train_smoothed[:, train_response_mask],
                    train_time[train_response_mask],
                )
            )
            if (index + 1) % 50 == 0 or index + 1 == len(metadata):
                print(f"[{index + 1:03d}/{len(metadata):03d}] baseline-response units analyzed", flush=True)

        metrics = pd.DataFrame(metric_rows)
        metrics.to_csv(staging_dir / "per_unit_threshold_response_metrics.csv", index=False)
        responsive = metrics.loc[metrics["mean_psth_above_baseline_candidate"]].copy()
        responsive.to_csv(staging_dir / "responsive_unit_targets.csv", index=False)
        profiles = _pulse_position_profiles(metrics, "unit_observation_id")
        profiles.to_csv(staging_dir / "per_unit_pulse_position_profiles.csv", index=False)
        early_decay_profiles, early_decay_targets = _early_decay_candidates(
            profiles, metrics, "unit_observation_id"
        )
        early_decay_profiles.to_csv(
            staging_dir / "top_50_early_greater_than_late_unit_profiles.csv", index=False
        )
        top_candidates = (
            responsive.sort_values(
                ["positive_going_psth_sum_spikes_per_trial", "peak_mean_excess_hz"],
                ascending=False,
            )
            .head(50)
            .copy()
        )
        top_candidates.to_csv(staging_dir / "top_50_mean_psth_candidates.csv", index=False)
        _plot_overview(metrics, staging_dir / "baseline_response_overview.png")
        _plot_pulse_profiles(
            metrics,
            profiles,
            "unit_observation_id",
            staging_dir / "pulse_position_dynamics.png",
        )
        _plot_raster_psth_pages(
            top_candidates,
            source,
            pulse_time,
            train_time,
            staging_dir / "top_50_mean_psth_candidate_raster_psth.pdf",
        )
        _plot_raster_psth_pages(
            early_decay_targets,
            source,
            pulse_time,
            train_time,
            staging_dir / "top_50_early_greater_than_late_unit_raster_psth.pdf",
        )

    (staging_dir / "METHOD_SPECIFICATION.md").write_text(
        _method_specification(metrics), encoding="utf-8"
    )
    (staging_dir / "provenance.json").write_text(
        json.dumps(
            {
                "development_output": True,
                "overwrite_policy": "entire output directory replaced after every successful run",
                "source_psth_store": str((psth_dir / STORE_NAME).resolve()),
                "unit_observations": int(len(metadata)),
                "metric_rows": int(len(metrics)),
                "response_threshold_hz_above_baseline": RESPONSE_THRESHOLD_HZ_ABOVE_BASELINE,
                "boxcar_weights": BOXCAR.tolist(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging_dir.replace(output_dir)
    print(f"\nThreshold analysis: {output_dir}")
    print(f"Responsive target rows: {int(metrics.mean_psth_above_baseline_candidate.sum())}")
    return 0


def _require_bins(mask: np.ndarray, expected: int, label: str) -> None:
    if int(mask.sum()) != expected:
        raise ValueError(f"{label}: expected {expected} one-ms bins, found {int(mask.sum())}")


def _response_metrics(
    common: dict[str, object], target: str, response_smoothed: np.ndarray, time_ms: np.ndarray
) -> dict[str, object]:
    baseline_rate = float(common["subtraction_baseline_rate_hz"])
    threshold = float(common["response_threshold_hz_above_baseline"])
    baseline_subtracted_trials = response_smoothed - baseline_rate
    mean_excess_psth = baseline_subtracted_trials.mean(axis=0)
    trials_above_by_bin = (baseline_subtracted_trials > threshold).sum(axis=0)
    criterion2_bins = mean_excess_psth > threshold
    criterion2 = bool(criterion2_bins.any())
    peak_index = int(np.argmax(mean_excess_psth))
    coincidence_index = int(np.argmax(trials_above_by_bin))
    return {
        **common,
        "target": target,
        "response_window_start_ms": float(time_ms[0] - 0.5),
        "response_window_end_ms": float(time_ms[-1] + 0.5),
        "positive_going_psth_sum_spikes_per_trial": float(
            np.clip(mean_excess_psth, 0, None).sum() / 1000.0
        ),
        "peak_mean_excess_hz": float(mean_excess_psth[peak_index]),
        "peak_latency_ms": float(time_ms[peak_index]),
        "maximum_trials_above_baseline_same_bin": int(trials_above_by_bin.max()),
        "maximum_trial_fraction_above_baseline_same_bin": float(
            trials_above_by_bin.max() / len(response_smoothed)
        ),
        "maximum_coincidence_latency_ms": float(time_ms[coincidence_index]),
        "mean_psth_above_baseline_candidate": criterion2,
    }


def _plot_overview(metrics: pd.DataFrame, output_path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)
    rng = np.random.default_rng(20260713)
    for row_index, label in enumerate(["good", "mua"]):
        data = metrics.loc[metrics["KSLabel"].eq(label)]
        x = np.arange(len(TARGETS))
        ax = axes[row_index, 0]
        for condition, offset in [("no_opsin", -0.12), ("opsin", 0.12)]:
            condition_data = data.loc[data["condition"].eq(condition)]
            for target_index, target in enumerate(TARGETS):
                values = condition_data.loc[
                    condition_data["target"].eq(target),
                    "maximum_trial_fraction_above_baseline_same_bin",
                ].to_numpy()
                jitter = rng.normal(0, 0.035, len(values))
                ax.scatter(
                    target_index + offset + jitter,
                    values,
                    s=9,
                    alpha=0.28,
                    color=COLORS[condition],                )
        ax.set_xticks(x, ["P1", "P2", "P3", "P4", "P5", "Train"])
        ax.set_ylabel("Maximum same-bin trial fraction")
        ax.set_title(f"{label.upper()}: descriptive trial coincidence")

        ax = axes[row_index, 1]
        width = 0.36
        summary = (
            data.groupby(["condition", "target"])[
                "mean_psth_above_baseline_candidate"
            ]
            .mean()
            .mul(100)
        )
        for condition, offset in [("no_opsin", -width / 2), ("opsin", width / 2)]:
            values = summary.loc[condition].reindex(TARGETS).fillna(0)
            ax.bar(x + offset, values, width, color=COLORS[condition], label=condition)
        ax.set_xticks(x, ["P1", "P2", "P3", "P4", "P5", "Train"])
        ax.set_ylabel("Trial-averaged PSTH rises above baseline (%)")
        ax.set_title(f"{label.upper()}: mean-PSTH candidate rule")
        ax.legend(frameon=False)
    fig.suptitle("Independent mean-PSTH-above-baseline candidates; no trial minimum")
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def _plot_raster_psth_pages(
    responsive: pd.DataFrame,
    source,
    pulse_time: np.ndarray,
    train_time: np.ndarray,
    output_path: Path,
) -> None:
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(output_path) as pdf:
        if responsive.empty:
            fig, ax = plt.subplots(figsize=(8, 3))
            ax.axis("off")
            ax.text(0.5, 0.5, "No units fulfilled both criteria.", ha="center", va="center")
            pdf.savefig(fig)
            plt.close(fig)
            return
        plot_rows = (
            responsive.sort_values("early_decay_rank")
            if "early_decay_rank" in responsive.columns
            else responsive.sort_values(["target", "condition", "well"])
        )
        for _, row in plot_rows.iterrows():
            uid = row["unit_observation_id"]
            target = row["target"]
            unit = source[f"units/{uid}"]
            if target == "train_250ms":
                display_mask = (train_time >= -500) & (train_time < 250)
                time_ms = train_time[display_mask]
                counts = unit["train_full_50/counts"][:, display_mask]
                smoothed = unit["train_full_50/smoothed_rate_hz"][:, display_mask]
                pulse_starts = [0, 50, 100, 150, 200]
            else:
                pulse_index = int(target.rsplit("_", 1)[1]) - 1
                time_ms = pulse_time
                counts = unit["pulse_250/counts"][:].reshape(50, 5, -1)[:, pulse_index, :]
                smoothed = unit["pulse_250/smoothed_rate_hz"][:].reshape(50, 5, -1)[
                    :, pulse_index, :
                ]
                pulse_starts = [0] + ([-50] if pulse_index > 0 else [])
            mean_excess = smoothed.mean(axis=0) - row["subtraction_baseline_rate_hz"]
            spike_rows, spike_bins = np.nonzero(counts)
            multiplicities = counts[spike_rows, spike_bins].astype(int)
            raster_x = np.repeat(time_ms[spike_bins], multiplicities)
            raster_y = np.repeat(spike_rows + 1, multiplicities)
            fig, (raster_ax, psth_ax) = plt.subplots(
                2,
                1,
                figsize=(10, 6),
                sharex=True,
                gridspec_kw={"height_ratios": [2.2, 1.0], "hspace": 0.08},
            )
            raster_ax.scatter(raster_x, raster_y, s=5, color="black", linewidths=0)
            raster_ax.set_ylim(50.8, 0.2)
            raster_ax.set_ylabel("Trial")
            raster_ax.set_title(
                f"{uid} | {row['well']} {row['condition']} | {row['KSLabel']} | {target} | "
                f"max coincident trials={int(row['maximum_trials_above_baseline_same_bin'])}/50"
            )
            psth_ax.plot(
                time_ms,
                mean_excess,
                drawstyle="steps-mid",
                color=COLORS[row["condition"]],
                linewidth=1.5,
                label="Baseline-subtracted mean PSTH; one [1,1,1]/3 boxcar",
            )
            psth_ax.axhline(0, color="#666666", linewidth=0.8)
            for ax in [raster_ax, psth_ax]:
                ax.axvline(0, color="black", linewidth=0.8)
                for pulse_start in pulse_starts:
                    ax.axvspan(pulse_start, pulse_start + 9.5, color="#F2CF5B", alpha=0.28)
            psth_ax.set_xlabel("Time relative to selected pulse/train onset (ms)")
            psth_ax.set_ylabel("Excess rate (Hz)")
            psth_ax.legend(frameon=False, fontsize=8)
            pdf.savefig(fig)
            plt.close(fig)


def _pulse_position_profiles(metrics: pd.DataFrame, id_column: str) -> pd.DataFrame:
    pulse_metrics = metrics.loc[metrics["target"].str.startswith("pulse_")].copy()
    pulse_metrics["pulse_number"] = pulse_metrics["target"].str.rsplit("_", n=1).str[1].astype(int)
    metadata_columns = [
        column
        for column in [
            id_column,
            "recording",
            "well",
            "organoid_id",
            "condition",
            "raw_variant",
            "unit_id",
            "KSLabel",
            "waveform_class",
            "best_channel_index",
            "best_channel_id",
            "units_pooled",
            "good_units_pooled",
            "mua_units_pooled",
            "source_unit_observation_ids",
        ]
        if column in pulse_metrics.columns
    ]
    rows: list[dict[str, object]] = []
    for observation_id, group in pulse_metrics.groupby(id_column, sort=False):
        ordered = group.set_index("pulse_number").reindex(range(1, 6))
        response = ordered["positive_going_psth_sum_spikes_per_trial"].to_numpy(dtype=float)
        candidates = ordered["mean_psth_above_baseline_candidate"].fillna(False).to_numpy(bool)
        coincidence = ordered["maximum_trials_above_baseline_same_bin"].to_numpy(dtype=float)
        early_any = bool(candidates[:2].any())
        late_any = bool(candidates[2:].any())
        if early_any and not late_any:
            category = "early_only_p1_p2"
        elif early_any and late_any:
            category = "sustained_early_and_late"
        elif late_any:
            category = "late_only_p3_p5"
        else:
            category = "no_qualifying_pulse"
        early_magnitude = float(np.nanmean(response[:2]))
        late_magnitude = float(np.nanmean(response[3:]))
        denominator = abs(early_magnitude) + abs(late_magnitude)
        rows.append(
            {
                **{column: group.iloc[0][column] for column in metadata_columns},
                **{
                    f"pulse_{pulse}_positive_excess_spikes_per_trial": float(response[pulse - 1])
                    for pulse in range(1, 6)
                },
                **{
                    f"pulse_{pulse}_responsive_candidate": bool(candidates[pulse - 1])
                    for pulse in range(1, 6)
                },
                **{
                    f"pulse_{pulse}_max_same_bin_trials": int(coincidence[pulse - 1])
                    for pulse in range(1, 6)
                },
                "pulse_response_pattern": ";".join(
                    f"P{pulse}={int(candidates[pulse - 1])}" for pulse in range(1, 6)
                ),
                "pulse_response_category": category,
                "early_p1_p2_mean_excess_spikes_per_trial": early_magnitude,
                "late_p4_p5_mean_excess_spikes_per_trial": late_magnitude,
                "early_minus_late_excess_spikes_per_trial": early_magnitude - late_magnitude,
                "late_over_early_response_ratio": (
                    late_magnitude / early_magnitude if early_magnitude > 0 else np.nan
                ),
                "habituation_index_early_minus_late_over_sum": (
                    (early_magnitude - late_magnitude) / denominator if denominator > 0 else np.nan
                ),
                "linear_response_slope_spikes_per_pulse": float(
                    np.polyfit(np.arange(1, 6), response, 1)[0]
                ),
                "pulse_of_maximum_response": int(np.nanargmax(response) + 1),
            }
        )
    return pd.DataFrame(rows)


def _early_decay_candidates(
    profiles: pd.DataFrame,
    metrics: pd.DataFrame,
    id_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ranked = (
        profiles.loc[
            profiles["early_minus_late_excess_spikes_per_trial"].gt(0)
            & profiles["linear_response_slope_spikes_per_pulse"].lt(0)
        ]
        .sort_values("early_minus_late_excess_spikes_per_trial", ascending=False)
        .head(50)
        .copy()
    )
    ranked.insert(0, "early_decay_rank", np.arange(1, len(ranked) + 1))
    if ranked.empty:
        return ranked, metrics.iloc[0:0].copy()
    selected = ranked[[id_column, "early_decay_rank", "pulse_of_maximum_response"]].copy()
    selected["target"] = "pulse_" + selected["pulse_of_maximum_response"].astype(str)
    target_rows = selected.merge(metrics, on=[id_column, "target"], how="left", validate="one_to_one")
    return ranked, target_rows


def _plot_pulse_profiles(
    metrics: pd.DataFrame,
    profiles: pd.DataFrame,
    id_column: str,
    output_path: Path,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), constrained_layout=True)
    categories = [
        "early_only_p1_p2",
        "sustained_early_and_late",
        "late_only_p3_p5",
        "no_qualifying_pulse",
    ]
    labels = ["Early only", "Sustained", "Late only", "None"]
    x = np.arange(len(categories))
    width = 0.36
    for condition, offset in [("no_opsin", -width / 2), ("opsin", width / 2)]:
        subset = profiles.loc[profiles["condition"].eq(condition)]
        values = subset["pulse_response_category"].value_counts().reindex(categories).fillna(0)
        values = 100.0 * values / max(len(subset), 1)
        axes[0].bar(x + offset, values, width, color=COLORS[condition], label=condition)
    axes[0].set_xticks(x, labels, rotation=18)
    axes[0].set_ylabel(f"{id_column.replace('_', ' ').title()} (%)")
    axes[0].set_title("Five-pulse candidate-response pattern")
    axes[0].legend(frameon=False)

    pulse = metrics.loc[metrics["target"].str.startswith("pulse_")].copy()
    pulse["pulse_number"] = pulse["target"].str.rsplit("_", n=1).str[1].astype(int)
    for condition in ["no_opsin", "opsin"]:
        summary = (
            pulse.loc[pulse["condition"].eq(condition)]
            .groupby("pulse_number")["positive_going_psth_sum_spikes_per_trial"]
            .agg(["median", lambda values: values.quantile(0.25), lambda values: values.quantile(0.75)])
        )
        summary.columns = ["median", "q25", "q75"]
        axes[1].plot(summary.index, summary["median"], marker="o", color=COLORS[condition], label=condition)
        axes[1].fill_between(
            summary.index,
            summary["q25"],
            summary["q75"],
            color=COLORS[condition],
            alpha=0.18,
        )
    axes[1].set_xticks(range(1, 6))
    axes[1].set_xlabel("Pulse position within train")
    axes[1].set_ylabel("Positive excess spikes/trial")
    axes[1].set_title("Shared pre-train baseline; continuous response magnitude")
    axes[1].legend(frameon=False)
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def _method_specification(metrics: pd.DataFrame) -> str:
    responsive = metrics.loc[metrics["mean_psth_above_baseline_candidate"]]
    return f"""# Independent per-unit baseline-subtracted response rule

This is a new response criterion applied to the same unified data construction. The directory is fully overwritten on every successful rerun.

## Data handling held constant

- Every unit observation is read from the unified HDF5 store.
- All 50 train rows are retained; silent trials are not removed.
- The 250 pulse rows remain explicitly indexed as five pulse positions × 50 trains.
- Spike counts use 1-ms bins.
- PSTHs use exactly one normalized `[1, 1, 1] / 3` boxcar along time. Rasters are unsmoothed.
- No pooling, FDR, or other decision rule across recordings, wells, organoids, or units is used.

## Adaptation of the cited rule

- Spontaneous firing rate: mean raw rate during −500–0 ms before the first pulse.
- Baseline subtraction: mean raw rate during −200–0 ms before the first pulse.
- No SD cutoff is used. The response threshold is zero after subtraction of the shared pre-train baseline rate.
- Pulse-position response duration: 0–50 ms relative to each pulse, analyzed separately for pulses 1–5.
- Full-train response duration: 0–250 ms relative to pulse 1.
- Positive-going response magnitude: sum of positive baseline-subtracted mean-PSTH bins × 0.001 s, reported as excess spikes/trial.
- There is no minimum number or fraction of responsive trials. Same-bin trial coincidence remains stored only as a descriptive metric.
- A unit-target pair is called a candidate when its trial-averaged baseline-subtracted PSTH rises above zero anywhere in the response window.
- This is a descriptive mean-PSTH rule, not a statistical-significance test.
- The same −200–0 ms window before pulse 1 is used for every pulse position. Pulses 2–5 are never locally re-baselined because their preceding windows contain earlier pulses.
- Per-observation pulse profiles store the five candidate flags, each pulse's positive excess-spike magnitude, the mean of pulses 1–2 versus pulses 4–5, their difference and ratio, a five-pulse linear slope, and the pulse of maximum response.
- `early_only_p1_p2` means pulse 1 or 2 qualifies while none of pulses 3–5 qualifies. The continuous early-greater-than-late ranking is descriptive and does not itself confer candidate status.

Responsive target rows: {len(responsive)} across {responsive['unit_observation_id'].nunique()} unique unit observations.
"""


if __name__ == "__main__":
    raise SystemExit(main())
