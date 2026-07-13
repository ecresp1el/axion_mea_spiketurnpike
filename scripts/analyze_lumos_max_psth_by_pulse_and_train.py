#!/usr/bin/env python
"""Analyze per-unit maximum Lumos PSTHs by pulse position and full train."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
import warnings

import h5py
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_lumos_all_units_unified_psth_store import (
    BOXCAR,
    DEFAULT_JOB_DIR,
    OUTPUT_NAME as PSTH_OUTPUT_NAME,
    STORE_NAME,
)


OUTPUT_NAME = "lumos_max_psth_by_pulse_and_train_development"
TARGET_ORDER = ["pulse_1", "pulse_2", "pulse_3", "pulse_4", "pulse_5", "train_250ms"]
TARGET_LABELS = {
    "pulse_1": "Pulse 1",
    "pulse_2": "Pulse 2",
    "pulse_3": "Pulse 3",
    "pulse_4": "Pulse 4",
    "pulse_5": "Pulse 5",
    "train_250ms": "Full train",
}
COLORS = {"no_opsin": "#4C78A8", "opsin": "#E45756"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--psth-dir",
        type=Path,
        default=DEFAULT_JOB_DIR / PSTH_OUTPUT_NAME,
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
    rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    curve_store_path = staging_dir / "mean_peak_psth_curves.h5"
    with h5py.File(psth_dir / STORE_NAME, "r") as source, h5py.File(
        curve_store_path, "w"
    ) as curves:
        pulse_time = source["axes/pulse_bin_centers_ms"][:]
        train_time = source["axes/train_bin_centers_ms"][:]
        train_baseline_mask = (train_time >= -250) & (train_time < 0)
        train_response_mask = (train_time >= 0) & (train_time < 250)
        curves.create_dataset("pulse_response_time_ms", data=pulse_time[pulse_time >= 0])
        curves.create_dataset("pulse_baseline_time_ms", data=pulse_time[pulse_time < 0])
        curves.create_dataset("train_response_time_ms", data=train_time[train_response_mask])
        curves.create_dataset("train_baseline_time_ms", data=train_time[train_baseline_mask])
        unit_curves = curves.create_group("units")

        for index, meta in metadata.iterrows():
            uid = str(meta["unit_observation_id"])
            source_unit = source[f"units/{uid}"]
            pulse_rate = source_unit["pulse_250/rate_hz"][:].reshape(50, 5, -1)
            train_rate = source_unit["train_full_50/rate_hz"][:]
            pulse_counts = source_unit["pulse_250/counts"][:].reshape(50, 5, -1)
            train_counts = source_unit["train_full_50/counts"][:]
            audit_rows.append(
                {
                    "unit_observation_id": uid,
                    "recording": meta["recording"],
                    "well": meta["well"],
                    "condition": meta["condition"],
                    "raw_variant": meta["raw_variant"],
                    "unit_id": meta["unit_id"],
                    "KSLabel": meta["KSLabel"],
                    "pretrain_50ms_spikes_across_50_trains": int(
                        pulse_counts[:, 0, pulse_time < 0].sum()
                    ),
                    "pulse1_0_50ms_spikes_across_50_trains": int(
                        pulse_counts[:, 0, pulse_time >= 0].sum()
                    ),
                    "pretrain_250ms_spikes_across_50_trains": int(
                        train_counts[:, train_baseline_mask].sum()
                    ),
                    "train_0_250ms_spikes_across_50_trains": int(
                        train_counts[:, train_response_mask].sum()
                    ),
                    "pretrain_50ms_rows_with_spikes": int(
                        (pulse_counts[:, 0, pulse_time < 0].sum(axis=1) > 0).sum()
                    ),
                    "pretrain_250ms_rows_with_spikes": int(
                        (train_counts[:, train_baseline_mask].sum(axis=1) > 0).sum()
                    ),
                }
            )
            unit_group = unit_curves.create_group(uid)
            baseline_pulse = pulse_rate[:, 0, :][:, pulse_time < 0]

            for pulse_index in range(5):
                target = f"pulse_{pulse_index + 1}"
                response = pulse_rate[:, pulse_index, :][:, pulse_time >= 0]
                rows.extend(
                    _analyze_target(
                        meta,
                        target,
                        baseline_pulse,
                        response,
                        pulse_time[pulse_time < 0],
                        pulse_time[pulse_time >= 0],
                        unit_group.create_group(target),
                    )
                )

            rows.extend(
                _analyze_target(
                    meta,
                    "train_250ms",
                    train_rate[:, train_baseline_mask],
                    train_rate[:, train_response_mask],
                    train_time[train_baseline_mask],
                    train_time[train_response_mask],
                    unit_group.create_group("train_250ms"),
                )
            )
            if (index + 1) % 50 == 0 or index + 1 == len(metadata):
                print(f"[{index + 1:03d}/{len(metadata):03d}] peak PSTHs analyzed", flush=True)

    results = pd.DataFrame(rows)
    results["enhanced_responsive"] = (
        results["peak_bin_mean_minus_baseline_hz"].gt(0)
        & results["per_unit_paired_wilcoxon_greater_p"].lt(0.05)
    )
    results.to_csv(staging_dir / "per_unit_max_psth_metrics.csv", index=False)
    pd.DataFrame(audit_rows).to_csv(
        staging_dir / "pre_stimulus_spike_audit.csv", index=False
    )
    enhanced = results.loc[
        results["trial_inclusion"].eq("all_rows")
        & results["enhanced_responsive"]
    ].copy()
    enhanced.to_csv(staging_dir / "per_unit_enhanced_units_all_rows.csv", index=False)
    _plot_overview(results, staging_dir / "per_unit_peak_enhancement_overview.png")
    _plot_responsive_units(
        results,
        psth_dir / STORE_NAME,
        staging_dir / "enhanced_unit_paired_raster_psth.pdf",
    )
    (staging_dir / "METHOD_SPECIFICATION.md").write_text(
        _method_specification(results), encoding="utf-8"
    )
    (staging_dir / "provenance.json").write_text(
        json.dumps(
            {
                "development_output": True,
                "overwrite_policy": "entire output directory replaced after every successful run",
                "source_psth_store": str((psth_dir / STORE_NAME).resolve()),
                "unit_observations": int(metadata.shape[0]),
                "metric_rows": int(results.shape[0]),
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
    print(f"\nPeak analysis: {output_dir}")
    print(f"Metric rows: {len(results)}")
    return 0


def _smooth_segments(matrix: np.ndarray) -> np.ndarray:
    return np.asarray(
        [np.convolve(row, BOXCAR, mode="same") for row in matrix], dtype=np.float32
    )


def _analyze_target(
    metadata: pd.Series,
    target: str,
    baseline_rate: np.ndarray,
    response_rate: np.ndarray,
    baseline_time: np.ndarray,
    response_time: np.ndarray,
    curve_group,
) -> list[dict[str, object]]:
    baseline_smoothed = _smooth_segments(baseline_rate)
    response_smoothed = _smooth_segments(response_rate)
    active_pair = (baseline_rate.sum(axis=1) + response_rate.sum(axis=1)) > 0
    output = []
    for inclusion, mask in [
        ("all_rows", np.ones(len(response_rate), dtype=bool)),
        ("active_rows_only", active_pair),
    ]:
        selected_baseline = baseline_smoothed[mask]
        selected_response = response_smoothed[mask]
        curve_subgroup = curve_group.create_group(inclusion)
        if len(selected_response):
            mean_baseline = selected_baseline.mean(axis=0)
            mean_response = selected_response.mean(axis=0)
            response_peak_index = int(np.argmax(mean_response))
            baseline_peak_index = int(np.argmax(mean_baseline))
            peak_bin_response = selected_response[:, response_peak_index]
            paired_baseline = selected_baseline.mean(axis=1)
            p_value = _paired_greater_p(peak_bin_response, paired_baseline)
            curve_subgroup.create_dataset("mean_baseline_psth_hz", data=mean_baseline)
            curve_subgroup.create_dataset("mean_response_psth_hz", data=mean_response)
            metrics = {
                "response_peak_hz": float(mean_response[response_peak_index]),
                "response_peak_latency_ms": float(response_time[response_peak_index]),
                "baseline_peak_hz": float(mean_baseline[baseline_peak_index]),
                "baseline_peak_latency_ms": float(baseline_time[baseline_peak_index]),
                "peak_minus_baseline_peak_hz": float(
                    mean_response[response_peak_index] - mean_baseline[baseline_peak_index]
                ),
                "mean_baseline_rate_hz": float(selected_baseline.mean()),
                "peak_bin_mean_response_hz": float(peak_bin_response.mean()),
                "paired_mean_baseline_rate_hz": float(paired_baseline.mean()),
                "peak_bin_mean_minus_baseline_hz": float(
                    (peak_bin_response - paired_baseline).mean()
                ),
                "peak_bin_median_minus_baseline_hz": float(
                    np.median(peak_bin_response - paired_baseline)
                ),
                "per_unit_paired_wilcoxon_greater_p": p_value,
            }
        else:
            curve_subgroup.create_dataset(
                "mean_baseline_psth_hz", data=np.full(baseline_rate.shape[1], np.nan)
            )
            curve_subgroup.create_dataset(
                "mean_response_psth_hz", data=np.full(response_rate.shape[1], np.nan)
            )
            metrics = {
                key: np.nan
                for key in [
                    "response_peak_hz",
                    "response_peak_latency_ms",
                    "baseline_peak_hz",
                    "baseline_peak_latency_ms",
                    "peak_minus_baseline_peak_hz",
                    "mean_baseline_rate_hz",
                    "peak_bin_mean_response_hz",
                    "paired_mean_baseline_rate_hz",
                    "peak_bin_mean_minus_baseline_hz",
                    "peak_bin_median_minus_baseline_hz",
                ]
            }
            metrics["per_unit_paired_wilcoxon_greater_p"] = 1.0
        output.append(
            {
                **{
                    key: metadata[key]
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
                "target": target,
                "target_label": TARGET_LABELS[target],
                "trial_inclusion": inclusion,
                "rows_total": len(response_rate),
                "rows_analyzed": int(mask.sum()),
                "excluded_silent_pairs": int(len(mask) - mask.sum()),
                "baseline_window_start_ms": float(baseline_time[0] - 0.5),
                "baseline_window_end_ms": float(baseline_time[-1] + 0.5),
                "response_window_start_ms": float(response_time[0] - 0.5),
                "response_window_end_ms": float(response_time[-1] + 0.5),
                **metrics,
            }
        )
    return output


def _paired_greater_p(response: np.ndarray, baseline: np.ndarray) -> float:
    difference = response - baseline
    if not len(difference) or not np.any(difference):
        return 1.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = wilcoxon(
            response,
            baseline,
            alternative="greater",
            zero_method="pratt",
            method="approx",
        )
    return float(result.pvalue) if np.isfinite(result.pvalue) else 1.0


def _plot_overview(results: pd.DataFrame, output_path: Path) -> None:
    data = results.loc[results["trial_inclusion"].eq("all_rows")].copy()
    rng = np.random.default_rng(20260713)
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    for row_index, label in enumerate(["good", "mua"]):
        subset = data.loc[data["KSLabel"].eq(label)]
        pulse = subset.loc[subset["target"].str.startswith("pulse_")]
        ax = axes[row_index, 0]
        for condition, offset in [("no_opsin", -0.12), ("opsin", 0.12)]:
            condition_data = pulse.loc[pulse["condition"].eq(condition)]
            for target_index, target in enumerate(TARGET_ORDER[:5]):
                values = condition_data.loc[
                    condition_data["target"].eq(target), "peak_bin_mean_minus_baseline_hz"
                ].dropna().to_numpy()
                x = target_index + offset + rng.normal(0, 0.035, len(values))
                ax.scatter(x, values, s=10, alpha=0.25, color=COLORS[condition])
                if len(values):
                    ax.plot(
                        [target_index + offset - 0.07, target_index + offset + 0.07],
                        [np.median(values)] * 2,
                        color=COLORS[condition],
                        linewidth=3,
                    )
                significant = condition_data.loc[
                    condition_data["target"].eq(target)
                    & condition_data["enhanced_responsive"]
                ]
                ax.scatter(
                    np.full(len(significant), target_index + offset),
                    significant["peak_bin_mean_minus_baseline_hz"],
                    marker="*",
                    s=70,
                    color="black",
                    zorder=5,
                )
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(range(5), [f"P{i}" for i in range(1, 6)])
        ax.set_ylabel("Maximum PSTH bin − baseline (Hz)")
        ax.set_title(f"{label.upper()}: separate 50-trial pulse positions")

        ax = axes[row_index, 1]
        train = subset.loc[subset["target"].eq("train_250ms")]
        for condition, x_center in [("no_opsin", 0), ("opsin", 1)]:
            condition_data = train.loc[train["condition"].eq(condition)]
            values = condition_data["peak_bin_mean_minus_baseline_hz"].dropna().to_numpy()
            x = x_center + rng.normal(0, 0.07, len(values))
            ax.scatter(x, values, s=12, alpha=0.3, color=COLORS[condition])
            if len(values):
                ax.plot(
                    [x_center - 0.18, x_center + 0.18],
                    [np.median(values)] * 2,
                    color=COLORS[condition],
                    linewidth=3,
                )
            significant = condition_data.loc[condition_data["enhanced_responsive"]]
            ax.scatter(
                np.full(len(significant), x_center),
                significant["peak_bin_mean_minus_baseline_hz"],
                marker="*",
                s=80,
                color="black",
                zorder=5,
            )
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks([0, 1], ["No opsin", "Opsin"])
        ax.set_ylabel("Maximum PSTH bin − baseline (Hz)")
        ax.set_title(f"{label.upper()}: maximum during 0–250 ms train")
    fig.suptitle("Per-unit maximum-PSTH enhancement (all 50 trains retained)", fontsize=15)
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def _plot_responsive_units(results: pd.DataFrame, psth_store_path: Path, output_path: Path) -> None:
    from matplotlib.backends.backend_pdf import PdfPages

    significant = results.loc[
        results["trial_inclusion"].eq("all_rows") & results["enhanced_responsive"]
    ].copy()
    with PdfPages(output_path) as pdf, h5py.File(psth_store_path, "r") as source:
        if significant.empty:
            fig, ax = plt.subplots(figsize=(8, 3))
            ax.axis("off")
            ax.text(0.5, 0.5, "No independently enhanced units.", ha="center", va="center")
            pdf.savefig(fig)
            plt.close(fig)
            return
        for _, row in significant.sort_values(["target", "well"]).iterrows():
            uid = row["unit_observation_id"]
            target = row["target"]
            if target == "train_250ms":
                full_time_ms = source["axes/train_bin_centers_ms"][:]
                display_mask = (full_time_ms >= -250) & (full_time_ms < 250)
                time_ms = full_time_ms[display_mask]
                counts = source[f"units/{uid}/train_full_50/counts"][:, display_mask]
                smoothed = source[f"units/{uid}/train_full_50/smoothed_rate_hz"][
                    :, display_mask
                ]
                pulse_starts = [0, 50, 100, 150, 200]
            else:
                pulse_index = int(target.rsplit("_", 1)[1]) - 1
                time_ms = source["axes/pulse_bin_centers_ms"][:]
                counts = source[f"units/{uid}/pulse_250/counts"][:].reshape(50, 5, -1)[
                    :, pulse_index, :
                ]
                smoothed = source[
                    f"units/{uid}/pulse_250/smoothed_rate_hz"
                ][:].reshape(50, 5, -1)[:, pulse_index, :]
                pulse_starts = [0]
                if pulse_index > 0:
                    pulse_starts.insert(0, -50)
            mean_psth = smoothed.mean(axis=0)
            spike_rows, spike_bins = np.nonzero(counts)
            multiplicities = counts[spike_rows, spike_bins].astype(int)
            raster_x = np.repeat(time_ms[spike_bins], multiplicities)
            raster_y = np.repeat(spike_rows + 1, multiplicities)

            fig, (raster_ax, psth_ax) = plt.subplots(
                2,
                1,
                figsize=(9, 6),
                sharex=True,
                gridspec_kw={"height_ratios": [2.2, 1.0], "hspace": 0.08},
            )
            raster_ax.scatter(raster_x, raster_y, s=5, color="black", linewidths=0)
            raster_ax.set_ylim(50.8, 0.2)
            raster_ax.set_ylabel("Train row")
            raster_ax.set_title(
                f"{uid} | {row['well']} {row['condition']} | {row['KSLabel']} | "
                f"{TARGET_LABELS[target]} | independent per-unit p="
                f"{row['per_unit_paired_wilcoxon_greater_p']:.3g}"
            )
            psth_ax.plot(
                time_ms,
                mean_psth,
                color=COLORS[row["condition"]],
                linewidth=1.6,
                drawstyle="steps-mid",
                label="Mean PSTH: 1-ms bins, one [1,1,1]/3 boxcar",
            )
            psth_ax.axhline(
                row["mean_baseline_rate_hz"],
                color="#666666",
                linestyle="--",
                linewidth=1,
                label="Matched pre-train mean baseline",
            )
            psth_ax.scatter(
                [row["response_peak_latency_ms"]],
                [row["response_peak_hz"]],
                color="black",
                zorder=5,
            )
            for ax in [raster_ax, psth_ax]:
                ax.axvline(0, color="black", linewidth=0.8)
                ax.grid(False)
            for pulse_start in pulse_starts:
                raster_ax.axvspan(
                    pulse_start, pulse_start + 9.5, color="#F2CF5B", alpha=0.28
                )
                psth_ax.axvspan(
                    pulse_start, pulse_start + 9.5, color="#F2CF5B", alpha=0.28
                )
            psth_ax.set_xlabel("Time relative to selected pulse/train onset (ms)")
            psth_ax.set_ylabel("Firing rate (Hz)")
            psth_ax.legend(frameon=False, fontsize=8, loc="upper left")
            pdf.savefig(fig)
            plt.close(fig)


def _method_specification(results: pd.DataFrame) -> str:
    all_rows = results.loc[results["trial_inclusion"].eq("all_rows")]
    responsive = all_rows.loc[all_rows["enhanced_responsive"]]
    return f"""# Maximum-PSTH analysis specification

This directory is development output and is fully replaced after every successful run.

## Pulse-position analysis

- The 250 pulse rows are separated into pulse positions 1–5.
- Each pulse position therefore contains 50 paired train repetitions per unit.
- The response search is 0–50 ms relative to that pulse.
- Every pulse position is compared with the same matched −50–0 ms pre-train baseline taken before pulse 1. Later pulses are never compared with the response to the preceding pulse.

## Full-train analysis

- There are 50 train repetitions per unit.
- The response search is 0–250 ms relative to pulse 1.
- The matched baseline is −250–0 ms before pulse 1.
- Pulses begin at 0, 50, 100, 150, and 200 ms and end 9.5 ms later.

## Peak and enhancement definition

- Mean PSTHs use 1-ms bins and a normalized `[1, 1, 1] / 3` boxcar.
- Baseline and response segments are smoothed separately so activity cannot leak across 0 ms.
- Reported peak rate and latency are the maximum of the mean response PSTH in the complete search window.
- For each unit independently, the response peak bin is selected from that unit's mean PSTH across its analyzed rows.
- The smoothed firing rate at that peak bin is paired row-by-row with the same train's mean firing rate across the complete matched pre-train baseline.
- A one-sided paired Wilcoxon test asks whether peak response is greater than baseline.
- No pooling or multiple-testing correction is performed across units, recordings, wells, organoids, conditions, or targets.
- Enhanced responsive requires a positive per-unit mean difference and unadjusted per-unit `p < 0.05`.
- Both all rows and active paired rows are reported. Active-pair selection requires a spike in either the baseline or response window; no source matrix rows are deleted.

## Raster/PSTH pages

- The raster uses unsmoothed 1-ms spike-count bins from all 50 rows.
- The PSTH directly beneath it is the mean of those rows after exactly one normalized `[1, 1, 1] / 3` boxcar along time. No additional smoothing is applied.
- Pulse-position pages show the actual continuous −50 to +50 ms window around that pulse. For pulses 2–5, negative time therefore contains the preceding pulse response rather than the separate pre-train baseline used by the statistical comparison.
- Full-train pages show the actual continuous −250 to +250 ms window.

All-row enhanced result rows: {len(responsive)} across {responsive['unit_observation_id'].nunique()} unique unit observations.
"""


if __name__ == "__main__":
    raise SystemExit(main())
