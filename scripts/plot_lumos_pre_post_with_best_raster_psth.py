#!/usr/bin/env python
"""Plot responsive-unit pre/peak-post rates beside the strongest raster and PSTH."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_lumos_all_units_unified_psth_store import DEFAULT_JOB_DIR
from scripts.plot_lumos_all_units_waveform_classification_pre_peak import (
    OUTPUT_NAME as ALL_UNIT_OUTPUT_NAME,
    CLASS_COLORS,
    CLASS_LABELS,
    CLASS_ORDER,
    CONDITION_COLORS,
)


RESPONSIVE_OUTPUT_NAME = "lumos_corrected_opto_responsive_units_development"
PSTH_OUTPUT_NAME = "lumos_all_units_per_unit_psth_development"
PSTH_STORE_NAME = "lumos_all_units_per_unit_psth_development.h5"
OUTPUT_NAME = "lumos_pre_post_with_best_raster_psth_development"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--responsive-csv",
        type=Path,
        default=DEFAULT_JOB_DIR / RESPONSIVE_OUTPUT_NAME / "responsive_unit_metrics.csv",
    )
    parser.add_argument(
        "--psth-store",
        type=Path,
        default=DEFAULT_JOB_DIR / PSTH_OUTPUT_NAME / PSTH_STORE_NAME,
    )
    parser.add_argument(
        "--all-unit-csv",
        type=Path,
        default=DEFAULT_JOB_DIR
        / ALL_UNIT_OUTPUT_NAME
        / "all_unit_waveform_pre_peak_metrics.csv",
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

    responsive_csv = args.responsive_csv.expanduser().resolve()
    psth_store = args.psth_store.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    units = pd.read_csv(responsive_csv).sort_values("response_rank").reset_index(drop=True)
    if len(units) != 19 or set(units["condition_response"]) != {"opsin"}:
        raise ValueError("expected the finalized set of 19 opsin-responsive units")
    all_units = pd.read_csv(args.all_unit_csv.expanduser().resolve())
    controls, matches = _baseline_matched_controls(units, all_units)
    representative_pool = units.loc[
        units["KSLabel_response"].str.lower().eq("good")
        & units["waveform_class_unit"].eq("RS_like")
    ]
    if representative_pool.empty:
        raise ValueError("no good RS-like responsive unit is available")
    representative = representative_pool.sort_values(
        ["peak_minus_pre_hz", "early_max_same_bin_trials"],
        ascending=False,
    ).iloc[0]

    with h5py.File(psth_store, "r") as store:
        centers_ms = store["axes/train_bin_centers_ms"][:]
        pulse_onsets_ms = store["axes/pulse_onsets_within_train_ms"][:]
        pulse_offsets_ms = store["axes/pulse_offsets_within_train_ms"][:]
        group = store[str(representative["hdf5_group"]).lstrip("/")]["train_full_50"]
        counts = group["counts"][:]
        smoothed_rate_hz = group["smoothed_rate_hz"][:]
        boxcar_weights = group.attrs["boxcar_weights"].tolist()

    if counts.shape[0] != 50 or counts.shape != smoothed_rate_hz.shape:
        raise ValueError(f"unexpected representative matrices: {counts.shape}")
    mean_smoothed_psth_hz = smoothed_rate_hz.mean(axis=0)

    _style(plt)
    figure = plt.figure(figsize=(16.2, 7.2))
    grid = figure.add_gridspec(
        2,
        3,
        width_ratios=[0.72, 0.72, 1.55],
        height_ratios=[1.18, 0.82],
        left=0.06,
        right=0.985,
        bottom=0.105,
        top=0.86,
        wspace=0.28,
        hspace=0.18,
    )
    rate_axis = figure.add_subplot(grid[:, 0])
    control_axis = figure.add_subplot(grid[:, 1], sharey=rate_axis)
    raster_axis = figure.add_subplot(grid[0, 2])
    psth_axis = figure.add_subplot(grid[1, 2], sharex=raster_axis)

    _plot_pre_post(rate_axis, units)
    _plot_control_pre_post(control_axis, controls, matches)
    _plot_raster(
        raster_axis,
        centers_ms,
        counts,
        pulse_onsets_ms,
        pulse_offsets_ms,
        representative,
    )
    _plot_psth(
        psth_axis,
        centers_ms,
        mean_smoothed_psth_hz,
        pulse_onsets_ms,
        pulse_offsets_ms,
        representative,
    )

    figure.suptitle(
        "Opto-responsive unit firing rates and strongest example response",
        x=0.025,
        y=0.975,
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
    figure.text(
        0.025,
        0.93,
        "Left: responsive opsin units and unique good no-opsin controls matched within 1 Hz "
        "pre rate. Right: all 50 trials from the best good RS-like example.",
        ha="left",
        fontsize=9,
        color="#4B5563",
    )

    png_path = staging_dir / "pre_post_rates_with_best_raster_psth.png"
    pdf_path = staging_dir / "pre_post_rates_with_best_raster_psth.pdf"
    figure.savefig(png_path, dpi=400, bbox_inches="tight", facecolor="white")
    figure.savefig(pdf_path, bbox_inches="tight", facecolor="white")
    plt.close(figure)

    units[
        [
            "response_rank",
            "unit_observation_id",
            "recording_response",
            "well_response",
            "unit_id_response",
            "KSLabel_response",
            "waveform_class_unit",
            "pre_rate_hz",
            "peak_post_rate_hz",
            "pulse_response_pattern",
            "early_max_same_bin_trials",
        ]
    ].to_csv(staging_dir / "plotted_unit_rates.csv", index=False)
    controls.to_csv(staging_dir / "matched_no_opsin_control_rates.csv", index=False)
    matches.to_csv(staging_dir / "baseline_matches.csv", index=False)
    pd.DataFrame(
        {
            "time_ms": centers_ms,
            "mean_boxcar_smoothed_rate_hz": mean_smoothed_psth_hz,
        }
    ).to_csv(staging_dir / "representative_psth.csv", index=False)
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "development_output": True,
        "overwrite_policy": "entire output directory replaced after successful run",
        "responsive_units": 19,
        "no_opsin_responsive_units": 0,
        "no_opsin_control_units": len(controls),
        "control_selection": (
            "unique KSLabel=good no-opsin units matched without replacement to responsive "
            "opsin units within 1 Hz pre rate; seeded random jitter breaks near ties"
        ),
        "unmatched_responsive_opsin_units": len(units) - len(matches),
        "representative_selection": (
            "largest peak-minus-pre firing-rate increase among KSLabel=good, "
            "RS-like responsive units"
        ),
        "representative_unit_observation_id": representative["unit_observation_id"],
        "representative_well": representative["well_response"],
        "representative_unit_id": str(representative["unit_id_response"]),
        "representative_KSLabel": representative["KSLabel_response"],
        "representative_waveform_class": representative["waveform_class_unit"],
        "raster_trials": 50,
        "raster_trial_inclusion": "all trials, including trials with zero spikes",
        "psth_bin_ms": 1,
        "psth_boxcar_weights": boxcar_weights,
        "condition_assignment": "D2 is opsin; no other assignment exception",
    }
    (staging_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )

    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging_dir.replace(output_dir)
    print(f"Output: {output_dir}")
    print(
        "Representative: "
        f"{representative['unit_observation_id']} / {representative['well_response']} / "
        f"unit {representative['unit_id_response']} / {representative['KSLabel_response']} / "
        f"{representative['waveform_class_unit']}"
    )
    return 0


def _baseline_matched_controls(
    responsive_units: pd.DataFrame, all_units: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    from scipy.optimize import linear_sum_assignment

    pool = all_units.loc[
        all_units["condition"].eq("no_opsin")
        & all_units["KSLabel"].str.lower().eq("good")
    ].reset_index(drop=True)
    if pool.empty:
        raise ValueError("no KSLabel=good no-opsin control units are available")

    target_pre = responsive_units["pre_rate_hz"].to_numpy(dtype=float)
    control_pre = pool["pre_rate_hz"].to_numpy(dtype=float)
    differences = np.abs(target_pre[:, None] - control_pre[None, :])
    rng = np.random.default_rng(20260713)
    tie_break = rng.uniform(0, 0.05, size=differences.shape)
    caliper_hz = 1.0
    costs = np.where(
        differences <= caliper_hz,
        differences + tie_break,
        100.0 + differences + tie_break,
    )
    target_indices, control_indices = linear_sum_assignment(costs)
    valid = differences[target_indices, control_indices] <= caliper_hz
    target_indices = target_indices[valid]
    control_indices = control_indices[valid]
    if len(control_indices) == 0:
        raise ValueError("no no-opsin controls fall within the 1-Hz baseline caliper")

    controls = pool.iloc[control_indices].copy().reset_index(drop=True)
    matched_targets = responsive_units.iloc[target_indices].reset_index(drop=True)
    controls.insert(0, "matched_opsin_response_rank", matched_targets["response_rank"])
    controls.insert(
        1,
        "baseline_difference_hz",
        np.abs(
            matched_targets["pre_rate_hz"].to_numpy()
            - controls["pre_rate_hz"].to_numpy()
        ),
    )
    matches = pd.DataFrame(
        {
            "opsin_response_rank": matched_targets["response_rank"],
            "opsin_unit_observation_id": matched_targets["unit_observation_id"],
            "opsin_pre_rate_hz": matched_targets["pre_rate_hz"],
            "no_opsin_unit_observation_id": controls["unit_observation_id"],
            "no_opsin_well": controls["well"],
            "no_opsin_pre_rate_hz": controls["pre_rate_hz"],
            "baseline_difference_hz": controls["baseline_difference_hz"],
        }
    ).sort_values("opsin_response_rank")
    controls = controls.sort_values("matched_opsin_response_rank").reset_index(drop=True)
    return controls, matches.reset_index(drop=True)


def _plot_pre_post(axis, units: pd.DataFrame) -> None:
    rng = np.random.default_rng(20260713)
    jitter = rng.uniform(-0.055, 0.055, len(units))
    for offset, row in zip(jitter, units.itertuples(index=False), strict=True):
        color = CLASS_COLORS[row.waveform_class_unit]
        axis.plot(
            [offset, 1 + offset],
            [row.pre_rate_hz, row.peak_post_rate_hz],
            color=color,
            alpha=0.35,
            lw=0.9,
        )
        axis.scatter(
            [offset, 1 + offset],
            [row.pre_rate_hz, row.peak_post_rate_hz],
            color=color,
            s=34,
            edgecolor="white",
            linewidth=0.55,
            zorder=3,
        )
    for class_name in CLASS_ORDER:
        count = int(units["waveform_class_unit"].eq(class_name).sum())
        if count:
            axis.scatter(
                [],
                [],
                color=CLASS_COLORS[class_name],
                label=f"{CLASS_LABELS[class_name]} n={count}",
            )
    axis.set_xticks([0, 1], ["Pre", "Peak post"])
    axis.set_xlim(-0.28, 1.28)
    axis.set_ylabel("Firing rate (Hz)")
    axis.set_title("A  Responsive opsin units (n=19)", loc="left", fontweight="bold")
    axis.legend(frameon=False, loc="upper left", fontsize=8)
    _clean_axis(axis)


def _plot_control_pre_post(axis, controls: pd.DataFrame, matches: pd.DataFrame) -> None:
    rng = np.random.default_rng(20260714)
    jitter = rng.uniform(-0.055, 0.055, len(controls))
    color = CONDITION_COLORS["no_opsin"]
    for offset, row in zip(jitter, controls.itertuples(index=False), strict=True):
        axis.plot(
            [offset, 1 + offset],
            [row.pre_rate_hz, row.peak_post_rate_hz],
            color=color,
            alpha=0.42,
            lw=0.9,
        )
        axis.scatter(
            [offset, 1 + offset],
            [row.pre_rate_hz, row.peak_post_rate_hz],
            color=color,
            s=34,
            edgecolor="white",
            linewidth=0.55,
            zorder=3,
        )
    axis.set_xticks([0, 1], ["Pre", "Peak post"])
    axis.set_xlim(-0.28, 1.28)
    axis.set_title(
        f"B  Matched good no-opsin controls (n={len(controls)})",
        loc="left",
        fontweight="bold",
    )
    axis.text(
        0.5,
        0.975,
        f"Matched to {len(matches)}/19 opsin units\n"
        "unique controls · pre-rate difference ≤1 Hz",
        transform=axis.transAxes,
        ha="center",
        va="top",
        fontsize=8,
        color="#4B5563",
    )
    axis.tick_params(labelleft=False)
    axis.set_ylabel("")
    _clean_axis(axis)


def _plot_raster(
    axis, centers_ms, counts, pulse_onsets_ms, pulse_offsets_ms, representative
) -> None:
    for trial_index, row in enumerate(counts, start=1):
        spike_bins = np.flatnonzero(row > 0)
        if len(spike_bins):
            axis.vlines(
                centers_ms[spike_bins],
                trial_index - 0.42,
                trial_index + 0.42,
                color="#111827",
                lw=0.55,
            )
    _shade_pulses(axis, pulse_onsets_ms, pulse_offsets_ms)
    axis.set_xlim(-200, 250)
    axis.set_ylim(0.2, 50.8)
    axis.set_ylabel("Trial")
    axis.set_title(
        f"C  Best good RS-like example: {representative['well_response']} "
        f"unit {representative['unit_id_response']}",
        loc="left",
        fontweight="bold",
    )
    axis.tick_params(labelbottom=False)
    _clean_axis(axis)


def _plot_psth(
    axis,
    centers_ms,
    mean_smoothed_psth_hz,
    pulse_onsets_ms,
    pulse_offsets_ms,
    representative,
) -> None:
    _shade_pulses(axis, pulse_onsets_ms, pulse_offsets_ms)
    axis.plot(centers_ms, mean_smoothed_psth_hz, color="#C44E52", lw=1.6)
    pre_mask = (centers_ms >= -200) & (centers_ms < 0)
    pre_mean = float(mean_smoothed_psth_hz[pre_mask].mean())
    axis.axhline(pre_mean, color="#6B7280", lw=0.8, ls="--", label=f"pre mean {pre_mean:.1f} Hz")
    axis.set_xlim(-200, 250)
    axis.set_ylim(bottom=0)
    axis.set_xlabel("Time from first pulse onset (ms)")
    axis.set_ylabel("Firing rate (Hz)")
    axis.set_title(
        "D  1-ms PSTH · [1,1,1]/3 boxcar",
        loc="left",
        fontweight="bold",
    )
    axis.text(
        0.99,
        0.95,
        f"pre → peak: {representative['pre_rate_hz']:.1f} → "
        f"{representative['peak_post_rate_hz']:.1f} Hz\n"
        f"pattern: {representative['pulse_response_pattern']}",
        transform=axis.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        color="#374151",
    )
    axis.legend(frameon=False, loc="upper left", fontsize=8)
    _clean_axis(axis)


def _shade_pulses(axis, pulse_onsets_ms, pulse_offsets_ms) -> None:
    for pulse_number, (start, end) in enumerate(
        zip(pulse_onsets_ms, pulse_offsets_ms, strict=True), start=1
    ):
        axis.axvspan(start, end, color="#F59E0B", alpha=0.22, lw=0)
        axis.axvline(start, color="#B45309", lw=0.55, alpha=0.7)
        if axis.get_subplotspec().rowspan.start == 0:
            axis.text(
                (start + end) / 2,
                0.985,
                f"P{pulse_number}",
                transform=axis.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=7.5,
                color="#92400E",
            )


def _clean_axis(axis) -> None:
    axis.spines[["top", "right"]].set_visible(False)


def _style(plt) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10.5,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.linewidth": 0.7,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
