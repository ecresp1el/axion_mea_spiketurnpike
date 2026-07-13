#!/usr/bin/env python
"""Compare B4-included and B4-excluded controls at unit and channel levels."""

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
from scripts.launch_step1_sorting_analyzer_browser import DEFAULT_STIM_RAW_ROOTS
from scripts.plot_lumos_all_units_waveform_classification_pre_peak import (
    CLASS_COLORS,
    CLASS_LABELS,
    CLASS_ORDER,
    CONDITION_COLORS,
    OUTPUT_NAME as ALL_UNIT_OUTPUT_NAME,
)
from axion_mea.gui_stim_response import (
    find_matching_raw_file,
    list_raw_files,
    load_pulse_epochs_from_raw,
    stim_events_from_raw,
)


RESPONSIVE_OUTPUT_NAME = "lumos_corrected_opto_responsive_units_development"
CHANNEL_OUTPUT_NAME = "lumos_channel_pooled_threshold_response_development"
UNIT_PSTH_OUTPUT_NAME = "lumos_all_units_per_unit_psth_development"
UNIT_PSTH_STORE_NAME = "lumos_all_units_per_unit_psth_development.h5"
CHANNEL_PSTH_STORE_NAME = "lumos_channel_pooled_psth_development.h5"
OUTPUT_NAME = "lumos_b4_inclusion_unit_channel_comparison_development"
FILTER_OVERLAY_WIDTHS = (1, 3, 5, 11)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--responsive-csv",
        type=Path,
        default=DEFAULT_JOB_DIR / RESPONSIVE_OUTPUT_NAME / "responsive_unit_metrics.csv",
    )
    parser.add_argument(
        "--all-unit-csv",
        type=Path,
        default=DEFAULT_JOB_DIR
        / ALL_UNIT_OUTPUT_NAME
        / "all_unit_waveform_pre_peak_metrics.csv",
    )
    parser.add_argument(
        "--channel-dir",
        type=Path,
        default=DEFAULT_JOB_DIR / CHANNEL_OUTPUT_NAME,
    )
    parser.add_argument(
        "--unit-psth-store",
        type=Path,
        default=DEFAULT_JOB_DIR / UNIT_PSTH_OUTPUT_NAME / UNIT_PSTH_STORE_NAME,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_JOB_DIR / OUTPUT_NAME,
    )
    parser.add_argument(
        "--minimum-pre-rate-hz",
        type=float,
        default=0.0,
        help="Keep observations with pre-stimulus firing rate at or above this value.",
    )
    parser.add_argument(
        "--post-statistic",
        choices=["mean", "peak_psth"],
        default="mean",
        help="Plot a fixed-window mean or the maximum smoothed PSTH bin.",
    )
    parser.add_argument(
        "--include-psth-summary",
        action="store_true",
        help="Add group mean ± SEM full-train PSTHs beneath the rate panels.",
    )
    parser.add_argument(
        "--psth-boxcar-bins",
        type=int,
        default=3,
        help="Odd-width normalized boxcar applied per observation before peak/group summaries.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.psth_boxcar_bins < 1 or args.psth_boxcar_bins % 2 == 0:
        raise ValueError("--psth-boxcar-bins must be a positive odd integer")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = args.output_dir.expanduser().resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    responsive = pd.read_csv(args.responsive_csv.expanduser().resolve())
    all_units = pd.read_csv(args.all_unit_csv.expanduser().resolve())
    unit_groups = _unit_groups(responsive, all_units)
    unit_groups = _attach_fixed_window_rates(
        unit_groups,
        args.unit_psth_store.expanduser().resolve(),
        args.psth_boxcar_bins,
    )
    unit_groups = _filter_minimum_pre_rate(unit_groups, args.minimum_pre_rate_hz)

    channel_dir = args.channel_dir.expanduser().resolve()
    channel_metrics = pd.read_csv(channel_dir / "per_channel_threshold_response_metrics.csv")
    early_channels = pd.read_csv(channel_dir / "early_only_channel_details.csv")
    channel_groups = _channel_groups(channel_metrics, early_channels)
    channel_groups = _attach_fixed_window_rates(
        channel_groups,
        channel_dir / CHANNEL_PSTH_STORE_NAME,
        args.psth_boxcar_bins,
    )
    channel_groups = _filter_minimum_pre_rate(
        channel_groups, args.minimum_pre_rate_hz
    )

    unit_psth_summary = None
    channel_psth_summary = None
    unit_filter_summary = None
    channel_filter_summary = None
    if args.include_psth_summary:
        unit_psth_summary = _group_psth_summaries(
            unit_groups,
            args.unit_psth_store.expanduser().resolve(),
            args.psth_boxcar_bins,
        )
        channel_psth_summary = _group_psth_summaries(
            channel_groups,
            channel_dir / CHANNEL_PSTH_STORE_NAME,
            args.psth_boxcar_bins,
        )
        unit_filter_summary = _group_filter_psth_summaries(
            unit_groups,
            args.unit_psth_store.expanduser().resolve(),
            FILTER_OVERLAY_WIDTHS,
        )
        channel_filter_summary = _group_filter_psth_summaries(
            channel_groups,
            channel_dir / CHANNEL_PSTH_STORE_NAME,
            FILTER_OVERLAY_WIDTHS,
        )

    cutoff_label = (
        f"; pre-stimulus rate ≥{args.minimum_pre_rate_hz:g} Hz"
        if args.minimum_pre_rate_hz > 0
        else ""
    )

    _style(plt)
    unit_figure = _plot_window_comparison(
        plt,
        unit_groups,
        level="unit",
        title="Unit-level comparison: no-opsin controls with versus without B4",
        subtitle=(
            "Each point-pair is one unit observation. All controls are KSLabel=good; "
            f"recordings are retained independently{cutoff_label}."
        ),
        post_statistic=args.post_statistic,
        psth_summary=unit_psth_summary,
        boxcar_bins=args.psth_boxcar_bins,
    )
    statistic_stem = "fixed_window" if args.post_statistic == "mean" else "peak_psth"
    if args.post_statistic == "peak_psth":
        statistic_stem += f"_{args.psth_boxcar_bins}bin"
    if args.include_psth_summary:
        statistic_stem += "_with_group_psth"
    _save_figure(
        unit_figure,
        staging_dir / f"unit_{statistic_stem}_b4_included_vs_excluded",
    )
    plt.close(unit_figure)

    channel_figure = _plot_window_comparison(
        plt,
        channel_groups,
        level="channel",
        title="Channel-pooled comparison: no-opsin controls with versus without B4",
        subtitle=(
            "Each point-pair is one recording × well × channel. All spikes on that channel are "
            f"pooled; control channels contain at least one good unit{cutoff_label}."
        ),
        post_statistic=args.post_statistic,
        psth_summary=channel_psth_summary,
        boxcar_bins=args.psth_boxcar_bins,
    )
    _save_figure(
        channel_figure,
        staging_dir / f"channel_{statistic_stem}_b4_included_vs_excluded",
    )
    plt.close(channel_figure)

    if args.include_psth_summary:
        unit_filter_figure = _plot_alignment_filter_overlay(
            plt,
            unit_filter_summary,
            level="unit",
        )
        _save_figure(
            unit_filter_figure,
            staging_dir / "unit_psth_alignment_filter_overlay_raw_3bin_5bin_11bin",
        )
        plt.close(unit_filter_figure)
        channel_filter_figure = _plot_alignment_filter_overlay(
            plt,
            channel_filter_summary,
            level="channel",
        )
        _save_figure(
            channel_filter_figure,
            staging_dir / "channel_psth_alignment_filter_overlay_raw_3bin_5bin_11bin",
        )
        plt.close(channel_filter_figure)

    unit_table = _combined_table(unit_groups, "unit")
    channel_table = _combined_table(channel_groups, "channel")
    unit_table.to_csv(staging_dir / "unit_comparison_data.csv", index=False)
    channel_table.to_csv(staging_dir / "channel_comparison_data.csv", index=False)
    summary = pd.concat(
        [
            _summary_table(unit_groups, "unit", args.post_statistic),
            _summary_table(channel_groups, "channel", args.post_statistic),
        ],
        ignore_index=True,
    )
    summary.to_csv(staging_dir / "comparison_summary.csv", index=False)
    if unit_psth_summary is not None:
        _psth_summary_table(unit_psth_summary, "unit").to_csv(
            staging_dir / "unit_group_psth_mean_sem.csv", index=False
        )
        _psth_summary_table(channel_psth_summary, "channel").to_csv(
            staging_dir / "channel_group_psth_mean_sem.csv", index=False
        )
        _filter_psth_summary_table(unit_filter_summary, "unit").to_csv(
            staging_dir / "unit_filter_overlay_psth.csv", index=False
        )
        _filter_psth_summary_table(channel_filter_summary, "channel").to_csv(
            staging_dir / "channel_filter_overlay_psth.csv", index=False
        )

    alignment_audit, alignment_summary = _audit_alignment_timestamps(
        args.unit_psth_store.expanduser().resolve()
    )
    alignment_audit.to_csv(staging_dir / "psth_alignment_audit_by_recording.csv", index=False)
    (staging_dir / "psth_alignment_audit_summary.json").write_text(
        json.dumps(alignment_summary, indent=2) + "\n", encoding="utf-8"
    )

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "development_output": True,
        "overwrite_policy": "entire output directory replaced after successful run",
        "minimum_pre_rate_hz": args.minimum_pre_rate_hz,
        "post_statistic": args.post_statistic,
        "include_psth_summary": args.include_psth_summary,
        "psth_boxcar_bins": args.psth_boxcar_bins,
        "unit_level": {
            "opto_responsive_opsin": len(unit_groups["opto_responsive_opsin"]),
            "good_no_opsin_B4_included": len(unit_groups["no_opsin_B4_included"]),
            "good_no_opsin_B4_excluded": len(unit_groups["no_opsin_B4_excluded"]),
            "aggregation": "one unit observation; recordings/raw variants are not deduplicated",
        },
        "channel_level": {
            "opto_responsive_opsin": len(channel_groups["opto_responsive_opsin"]),
            "no_opsin_B4_included": len(channel_groups["no_opsin_B4_included"]),
            "no_opsin_B4_excluded": len(channel_groups["no_opsin_B4_excluded"]),
            "aggregation": (
                "spikes pooled across all sorted units sharing recording, well, and physical "
                "channel; recordings and wells remain separate"
            ),
            "control_requirement": "channel contains at least one KSLabel=good unit",
            "responsive_opsin_rule": "early-only P1/P2 channel response with >=3/50 coincidence",
        },
        "rate_definitions": {
            "pre": "mean raw firing rate during -200 to 0 ms before P1",
            "full_post": "mean raw firing rate during fixed 0 to 250 ms train window",
            "early_post": (
                "mean raw firing rate across fixed 0 to 50 ms windows after P1 and P2"
            ),
            "full_post_peak_psth": (
                f"maximum trial-averaged {args.psth_boxcar_bins}-bin normalized-boxcar "
                "PSTH bin during 0 to 250 ms"
            ),
            "early_post_peak_psth": (
                f"maximum trial-averaged {args.psth_boxcar_bins}-bin normalized-boxcar "
                "PSTH bin across P1 and P2 "
                "during 0 to 50 ms"
            ),
            "silent_trials": "retained",
        },
        "pass_annotation": (
            "early-only P1/P2 response with >=3/50 same-bin trials; displayed separately "
            "from the fixed-window rates"
        ),
        "condition_assignment": "D2 is opsin; no other well assignment exception",
        "alignment_audit": alignment_summary,
        "filter_overlay": {
            "boxcar_bins": list(FILTER_OVERLAY_WIDTHS),
            "smoothing": "centered normalized boxcar via numpy.convolve(..., mode='same')",
            "interpretation": (
                "centered smoothing is acausal and can spread a post-onset bin backward by "
                "floor(width/2) ms"
            ),
        },
    }
    (staging_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )

    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging_dir.replace(output_dir)
    print(f"Output: {output_dir}")
    print(
        "Units: "
        f"opsin={len(unit_groups['opto_responsive_opsin'])} / "
        f"no-opsin included={len(unit_groups['no_opsin_B4_included'])} / "
        f"excluded={len(unit_groups['no_opsin_B4_excluded'])}"
    )
    print(
        "Channels: "
        f"opsin={len(channel_groups['opto_responsive_opsin'])} / "
        f"no-opsin included={len(channel_groups['no_opsin_B4_included'])} / "
        f"excluded={len(channel_groups['no_opsin_B4_excluded'])}"
    )
    return 0


def _unit_groups(responsive: pd.DataFrame, all_units: pd.DataFrame) -> dict[str, pd.DataFrame]:
    opsin = responsive.rename(
        columns={
            "recording_response": "recording",
            "well_response": "well",
            "condition_response": "condition",
            "raw_variant_response": "raw_variant",
            "unit_id_response": "unit_id",
            "KSLabel_response": "KSLabel",
            "waveform_class_unit": "waveform_class",
        }
    ).copy()
    no_opsin = all_units.loc[
        all_units["condition"].eq("no_opsin")
        & all_units["KSLabel"].str.lower().eq("good")
    ].copy()
    opsin["responsive_pass"] = True
    no_opsin["responsive_pass"] = False
    groups = {
        "opto_responsive_opsin": opsin,
        "no_opsin_B4_included": no_opsin,
        "no_opsin_B4_excluded": no_opsin.loc[no_opsin["well"].ne("B4")].copy(),
    }
    expected = {"opto_responsive_opsin": 19, "no_opsin_B4_included": 54, "no_opsin_B4_excluded": 27}
    _validate_group_counts(groups, expected, "unit")
    return groups


def _channel_groups(metrics: pd.DataFrame, early: pd.DataFrame) -> dict[str, pd.DataFrame]:
    train = metrics.loc[metrics["target"].eq("train_250ms")].copy()
    all_responsive_ids = set(early["channel_observation_id"])
    train["responsive_pass"] = train["channel_observation_id"].isin(
        all_responsive_ids
    )
    responsive_ids = set(
        early.loc[early["condition"].eq("opsin"), "channel_observation_id"]
    )
    opsin = train.loc[train["channel_observation_id"].isin(responsive_ids)].copy()
    no_opsin = train.loc[
        train["condition"].eq("no_opsin") & train["good_units_pooled"].ge(1)
    ].copy()
    groups = {
        "opto_responsive_opsin": opsin,
        "no_opsin_B4_included": no_opsin,
        "no_opsin_B4_excluded": no_opsin.loc[no_opsin["well"].ne("B4")].copy(),
    }
    expected = {"opto_responsive_opsin": 14, "no_opsin_B4_included": 53, "no_opsin_B4_excluded": 26}
    _validate_group_counts(groups, expected, "channel")
    for name, data in groups.items():
        if data["channel_observation_id"].duplicated().any():
            raise ValueError(f"{name}: duplicate channel observations")
        if data[["recording", "well", "best_channel_index"]].duplicated().any():
            raise ValueError(f"{name}: recording/well/channel grouping is not unique")
    return groups


def _validate_group_counts(groups, expected, level):
    observed = {name: len(data) for name, data in groups.items()}
    if observed != expected:
        raise ValueError(f"unexpected {level} group counts: {observed}; expected {expected}")


def _attach_fixed_window_rates(groups, store_path, boxcar_bins):
    cache: dict[str, tuple[float, float, float, float, float]] = {}
    with h5py.File(store_path, "r") as store:
        train_time = store["axes/train_bin_centers_ms"][:]
        pulse_time = store["axes/pulse_bin_centers_ms"][:]
        pre_mask = (train_time >= -200) & (train_time < 0)
        full_post_mask = (train_time >= 0) & (train_time < 250)
        early_mask = (pulse_time >= 0) & (pulse_time < 50)
        if (int(pre_mask.sum()), int(full_post_mask.sum()), int(early_mask.sum())) != (
            200,
            250,
            50,
        ):
            raise ValueError("fixed-window axes do not contain the expected 1-ms bins")
        for data in groups.values():
            pre_values = []
            full_values = []
            early_values = []
            full_peak_values = []
            early_peak_values = []
            for row in data.itertuples(index=False):
                group_path = str(row.hdf5_group).lstrip("/")
                if group_path not in cache:
                    group = store[group_path]
                    train_rate = group["train_full_50/rate_hz"][:]
                    pulse_rate = group["pulse_250/rate_hz"][:].reshape(50, 5, -1)
                    train_smoothed = _smooth_rows(train_rate, boxcar_bins)
                    pulse_smoothed = _smooth_rows(
                        pulse_rate.reshape(250, -1), boxcar_bins
                    ).reshape(50, 5, -1)
                    pre_rate = float(train_rate[:, pre_mask].mean())
                    full_post_rate = float(train_rate[:, full_post_mask].mean())
                    early_rate = float(pulse_rate[:, :2, :][:, :, early_mask].mean())
                    full_peak = float(
                        train_smoothed[:, full_post_mask].mean(axis=0).max()
                    )
                    early_peak = float(
                        pulse_smoothed[:, :2, :][:, :, early_mask]
                        .mean(axis=0)
                        .max()
                    )
                    cache[group_path] = (
                        pre_rate,
                        full_post_rate,
                        early_rate,
                        full_peak,
                        early_peak,
                    )
                (
                    pre_rate,
                    full_post_rate,
                    early_rate,
                    full_peak,
                    early_peak,
                ) = cache[group_path]
                pre_values.append(pre_rate)
                full_values.append(full_post_rate)
                early_values.append(early_rate)
                full_peak_values.append(full_peak)
                early_peak_values.append(early_peak)
            data["pre_rate_hz"] = pre_values
            data["full_post_mean_rate_hz"] = full_values
            data["early_p1_p2_mean_rate_hz"] = early_values
            data["full_post_peak_psth_hz"] = full_peak_values
            data["early_p1_p2_peak_psth_hz"] = early_peak_values
    return groups


def _filter_minimum_pre_rate(groups, minimum_pre_rate_hz):
    if minimum_pre_rate_hz <= 0:
        return groups
    return {
        name: data.loc[data["pre_rate_hz"].ge(minimum_pre_rate_hz)].copy()
        for name, data in groups.items()
    }


def _group_psth_summaries(groups, store_path, boxcar_bins):
    summaries = {}
    cache: dict[str, np.ndarray] = {}
    with h5py.File(store_path, "r") as store:
        train_time = store["axes/train_bin_centers_ms"][:]
        pulse_onsets = store["axes/pulse_onsets_within_train_ms"][:]
        pulse_offsets = store["axes/pulse_offsets_within_train_ms"][:]
        display_mask = (train_time >= -200) & (train_time < 250)
        display_time = train_time[display_mask]
        for name, data in groups.items():
            curves = []
            for row in data.itertuples(index=False):
                group_path = str(row.hdf5_group).lstrip("/")
                if group_path not in cache:
                    raw_rate = store[group_path]["train_full_50/rate_hz"][:]
                    cache[group_path] = _smooth_rows(raw_rate, boxcar_bins)[
                        :, display_mask
                    ].mean(axis=0)
                curves.append(cache[group_path])
            matrix = np.asarray(curves, dtype=float)
            mean = matrix.mean(axis=0)
            sem = (
                matrix.std(axis=0, ddof=1) / np.sqrt(len(matrix))
                if len(matrix) > 1
                else np.zeros_like(mean)
            )
            summaries[name] = {
                "time_ms": display_time,
                "mean_rate_hz": mean,
                "sem_rate_hz": sem,
                "n": len(matrix),
                "pulse_onsets_ms": pulse_onsets,
                "pulse_offsets_ms": pulse_offsets,
            }
    return summaries


def _group_filter_psth_summaries(groups, store_path, boxcar_widths):
    summaries = {}
    with h5py.File(store_path, "r") as store:
        train_time = store["axes/train_bin_centers_ms"][:]
        train_edges = store["axes/train_bin_edges_ms"][:]
        pulse_onsets = store["axes/pulse_onsets_within_train_ms"][:]
        pulse_offsets = store["axes/pulse_offsets_within_train_ms"][:]
        display_mask = (train_time >= -25) & (train_time < 250)
        for name, data in groups.items():
            by_width = {}
            raw_curves = []
            for row in data.itertuples(index=False):
                group_path = str(row.hdf5_group).lstrip("/")
                raw_rate = store[group_path]["train_full_50/rate_hz"][:]
                raw_curves.append(raw_rate[:, display_mask].mean(axis=0))
            raw_matrix = np.asarray(raw_curves, dtype=float)
            for width in boxcar_widths:
                if width == 1:
                    curves = raw_matrix
                else:
                    curves = []
                    for row in data.itertuples(index=False):
                        group_path = str(row.hdf5_group).lstrip("/")
                        raw_rate = store[group_path]["train_full_50/rate_hz"][:]
                        curves.append(
                            _smooth_rows(raw_rate, width)[:, display_mask].mean(axis=0)
                        )
                    curves = np.asarray(curves, dtype=float)
                by_width[int(width)] = {
                    "mean_rate_hz": curves.mean(axis=0),
                    "sem_rate_hz": (
                        curves.std(axis=0, ddof=1) / np.sqrt(len(curves))
                        if len(curves) > 1
                        else np.zeros(curves.shape[1], dtype=float)
                    ),
                }
            summaries[name] = {
                "time_ms": train_time[display_mask],
                "bin_edges_ms": train_edges,
                "pulse_onsets_ms": pulse_onsets,
                "pulse_offsets_ms": pulse_offsets,
                "n": len(raw_matrix),
                "by_width": by_width,
            }
    return summaries


def _smooth_rows(rate_matrix, boxcar_bins):
    weights = np.ones(boxcar_bins, dtype=float) / boxcar_bins
    return np.asarray(
        [np.convolve(row, weights, mode="same") for row in rate_matrix],
        dtype=float,
    )


def _plot_window_comparison(
    plt,
    groups,
    *,
    level,
    title,
    subtitle,
    post_statistic,
    psth_summary=None,
    boxcar_bins=3,
):
    rows = 3 if psth_summary is not None else 2
    figure, axes = plt.subplots(
        rows,
        3,
        figsize=(13.8, 13.8 if rows == 3 else 10.2),
        sharey="row",
        squeeze=False,
    )
    noun = "units" if level == "unit" else "channels"
    specifications = [
        ("opto_responsive_opsin", "A  Opto-responsive opsin", "opsin"),
        ("no_opsin_B4_included", "B  No opsin · B4 included", "no_opsin"),
        ("no_opsin_B4_excluded", "C  No opsin · B4 excluded", "no_opsin"),
    ]
    if post_statistic == "mean":
        windows = [
            ("full_post_mean_rate_hz", "Fixed full-train mean · 0–250 ms"),
            ("early_p1_p2_mean_rate_hz", "Fixed early mean · P1/P2 0–50 ms"),
        ]
        method_note = "Rates use raw counts in prespecified windows; no maximum is selected."
    else:
        windows = [
            ("full_post_peak_psth_hz", "Peak PSTH bin · 0–250 ms"),
            ("early_p1_p2_peak_psth_hz", "Peak PSTH bin · P1/P2 0–50 ms"),
        ]
        method_note = (
            f"Post is the maximum trial-averaged [{','.join(['1'] * boxcar_bins)}]/"
            f"{boxcar_bins}-smoothed PSTH bin inside each stated window."
        )
    all_values = np.concatenate(
        [
            data[["pre_rate_hz", *[column for column, _ in windows]]]
            .to_numpy(float)
            .ravel()
            for data in groups.values()
        ]
    )
    ymax = max(float(np.nanmax(all_values)) * 1.09, 1.0)
    for row_index, (post_column, window_label) in enumerate(windows):
        for column_index, (key, panel_title, condition) in enumerate(specifications):
            axis = axes[row_index, column_index]
            data = groups[key]
            _paired_axis(
                axis,
                data,
                condition,
                post_column=post_column,
                seed=20260720 + row_index * 3 + column_index,
            )
            letter = chr(ord("A") + row_index * 3 + column_index)
            axis.set_title(
                f"{letter}  {panel_title[3:]}\n{window_label}\n(n={len(data)} {noun})",
                loc="left",
                fontweight="bold",
            )
            axis.set_ylim(-0.02 * ymax, ymax)
            if column_index:
                axis.tick_params(labelleft=False)
                axis.set_ylabel("")
            pre_median = float(data["pre_rate_hz"].median())
            post_median = float(data[post_column].median())
            pass_count = int(data["responsive_pass"].sum())
            axis.text(
                0.5,
                0.975,
                f"median {pre_median:.1f} → {post_median:.1f} Hz\n"
                f"early-only rule pass: {pass_count}/{len(data)}",
                transform=axis.transAxes,
                ha="center",
                va="top",
                fontsize=8,
                color="#4B5563",
            )
    if psth_summary is not None:
        for column_index, (key, panel_title, condition) in enumerate(specifications):
            axis = axes[2, column_index]
            _plot_group_psth(
                axis,
                psth_summary[key],
                condition=condition,
            )
            letter = chr(ord("A") + 6 + column_index)
            axis.set_title(
                f"{letter}  {panel_title[3:]}\nMean PSTH ± SEM (n={psth_summary[key]['n']} {noun})",
                loc="left",
                fontweight="bold",
            )
            if column_index:
                axis.tick_params(labelleft=False)
                axis.set_ylabel("")
    figure.suptitle(title, x=0.025, y=0.985, ha="left", fontsize=15, fontweight="bold")
    figure.text(
        0.025,
        0.945,
        subtitle + " " + method_note,
        ha="left",
        fontsize=8.5,
        color="#4B5563",
    )
    figure.subplots_adjust(
        left=0.07,
        right=0.99,
        bottom=0.07,
        top=0.88 if rows == 3 else 0.85,
        wspace=0.18,
        hspace=0.48 if rows == 3 else 0.42,
    )
    return figure


def _plot_group_psth(axis, summary, *, condition):
    time_ms = summary["time_ms"]
    mean = summary["mean_rate_hz"]
    sem = summary["sem_rate_hz"]
    color = CONDITION_COLORS[condition]

    axis.axvspan(-200, 0, color="#9CA3AF", alpha=0.08, lw=0)
    axis.axvspan(0, 100, color="#F59E0B", alpha=0.055, lw=0)
    axis.axvspan(100, 250, color="#60A5FA", alpha=0.035, lw=0)
    for boundary, boundary_color in [
        (-200, "#6B7280"),
        (0, "#111827"),
        (100, "#B45309"),
        (250, "#2563EB"),
    ]:
        axis.axvline(boundary, color=boundary_color, lw=0.8, ls="--", alpha=0.9)
    for pulse_start, pulse_end in zip(
        summary["pulse_onsets_ms"], summary["pulse_offsets_ms"], strict=True
    ):
        axis.axvspan(pulse_start, pulse_end, color="#F2CF5B", alpha=0.22, lw=0)
        axis.axvline(
            pulse_start,
            color="#7C3E00",
            lw=0.85,
            ls="--",
            alpha=0.95,
        )

    axis.fill_between(
        time_ms,
        mean - sem,
        mean + sem,
        color=color,
        alpha=0.20,
        linewidth=0,
        label="SEM across observations",
    )
    axis.plot(time_ms, mean, color=color, lw=1.55, label="Mean PSTH")
    pre_mask = (time_ms >= -200) & (time_ms < 0)
    pre_mean = float(mean[pre_mask].mean())
    axis.axhline(
        pre_mean,
        color="#6B7280",
        lw=0.75,
        ls="--",
        label=f"Mean pre rate {pre_mean:.1f} Hz",
    )
    axis.text(
        -100,
        0.98,
        "PRE\n−200–0 ms",
        transform=axis.get_xaxis_transform(),
        ha="center",
        va="top",
        fontsize=7,
        color="#4B5563",
    )
    axis.text(
        50,
        0.98,
        "EARLY PEAK SEARCH\nP1/P2: 0–100 ms train time",
        transform=axis.get_xaxis_transform(),
        ha="center",
        va="top",
        fontsize=7,
        color="#92400E",
    )
    axis.text(
        175,
        0.98,
        "FULL PEAK SEARCH END\n250 ms",
        transform=axis.get_xaxis_transform(),
        ha="center",
        va="top",
        fontsize=7,
        color="#1D4ED8",
    )
    axis.set_xlim(-205, 255)
    axis.set_ylim(bottom=0)
    axis.set_xlabel("Time from P1 onset (ms)")
    axis.set_ylabel("Firing rate (Hz)")
    axis.legend(frameon=False, fontsize=6.8, loc="upper left", bbox_to_anchor=(0, 0.82))
    axis.spines[["top", "right"]].set_visible(False)


def _plot_alignment_filter_overlay(plt, summaries, *, level):
    figure, axes = plt.subplots(3, 3, figsize=(14.4, 11.2), squeeze=False)
    noun = "units" if level == "unit" else "channels"
    specifications = [
        ("opto_responsive_opsin", "Opto-responsive opsin"),
        ("no_opsin_B4_included", "No opsin · B4 included"),
        ("no_opsin_B4_excluded", "No opsin · B4 excluded"),
    ]
    colors = {1: "#111827", 3: "#2563EB", 5: "#7C3AED", 11: "#DC2626"}
    labels = {1: "Unsmoothed (1-ms bins)", 3: "3-bin centered", 5: "5-bin centered", 11: "11-bin centered"}
    for column, (key, title) in enumerate(specifications):
        summary = summaries[key]
        for row in range(3):
            axis = axes[row, column]
            _draw_stimulation_annotations(axis, summary)
            for width in FILTER_OVERLAY_WIDTHS:
                axis.plot(
                    summary["time_ms"],
                    summary["by_width"][width]["mean_rate_hz"],
                    color=colors[width],
                    lw=1.05 if width == 1 else 1.5,
                    alpha=0.75 if width == 1 else 0.92,
                    label=labels[width],
                    zorder=3,
                )
            axis.set_ylim(bottom=0)
            axis.set_ylabel("Mean firing rate (Hz)" if column == 0 else "")
            axis.set_xlabel("Time from exact raw-file P1 command onset (ms)")
            axis.spines[["top", "right"]].set_visible(False)
            if row == 0:
                axis.set_xlim(-25, 250)
                axis.set_title(
                    f"{chr(ord('A') + column)}  {title}\nFull train (n={summary['n']} {noun})",
                    loc="left",
                    fontweight="bold",
                )
            else:
                pulse_index = row - 1
                selected_onset = float(summary["pulse_onsets_ms"][pulse_index])
                axis.set_xlim(selected_onset - 15, selected_onset + 25)
                axis.set_title(
                    f"{chr(ord('A') + row * 3 + column)}  P{pulse_index + 1} onset zoom",
                    loc="left",
                    fontweight="bold",
                )
            if column == 0 and row == 0:
                axis.legend(frameon=False, fontsize=8, loc="upper left")
    figure.suptitle(
        f"{level.capitalize()} PSTH alignment and centered-filter overlay",
        x=0.04,
        y=0.985,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    figure.text(
        0.04,
        0.935,
        (
            "Dashed brown lines are the exact raw-file optical-command onset offsets used for "
            "alignment; yellow spans use the paired raw-file command start/end offsets. "
            "PSTH samples are plotted at 1-ms bin centers (the first post-onset bin is +0.5 ms). "
            "Centered filters are acausal and can spread activity backward by 1, 2, or 5 ms."
        ),
        ha="left",
        fontsize=8.5,
        color="#4B5563",
    )
    figure.subplots_adjust(left=0.07, right=0.99, bottom=0.065, top=0.88, wspace=0.20, hspace=0.42)
    return figure


def _draw_stimulation_annotations(axis, summary):
    for pulse_start, pulse_end in zip(
        summary["pulse_onsets_ms"], summary["pulse_offsets_ms"], strict=True
    ):
        axis.axvspan(pulse_start, pulse_end, color="#F2CF5B", alpha=0.24, lw=0, zorder=0)
        axis.axvline(
            pulse_start,
            color="#7C3E00",
            lw=0.9,
            ls="--",
            alpha=0.95,
            zorder=2,
        )


def _paired_axis(axis, data, condition, *, post_column, seed):
    rng = np.random.default_rng(seed)
    jitter = rng.uniform(-0.06, 0.06, len(data))
    for offset, row in zip(jitter, data.itertuples(index=False), strict=True):
        if condition == "opsin" and hasattr(row, "waveform_class"):
            color = CLASS_COLORS.get(row.waveform_class, CONDITION_COLORS[condition])
        else:
            color = CONDITION_COLORS[condition]
        units_pooled = int(getattr(row, "units_pooled", 1))
        size = 25 + 6 * min(units_pooled - 1, 4)
        axis.plot(
            [offset, 1 + offset],
            [row.pre_rate_hz, getattr(row, post_column)],
            color=color,
            alpha=0.25,
            lw=0.75,
        )
        axis.scatter(
            [offset, 1 + offset],
            [row.pre_rate_hz, getattr(row, post_column)],
            color=color,
            s=size,
            alpha=0.78,
            edgecolor="white",
            linewidth=0.45,
            zorder=3,
        )
    post_label = "Peak PSTH" if "peak_psth" in post_column else "Fixed post"
    axis.set_xticks([0, 1], ["Pre", post_label])
    axis.set_xlim(-0.25, 1.25)
    axis.set_ylabel("Firing rate (Hz)")
    axis.spines[["top", "right"]].set_visible(False)


def _save_figure(figure, base_path):
    figure.savefig(base_path.with_suffix(".png"), dpi=400, bbox_inches="tight", facecolor="white")
    figure.savefig(base_path.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")


def _combined_table(groups, level):
    frames = []
    for group_name, data in groups.items():
        frame = data.copy()
        frame.insert(0, "comparison_group", group_name)
        frame.insert(0, "analysis_level", level)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False)


def _summary_table(groups, level, post_statistic):
    rows = []
    if post_statistic == "mean":
        windows = [
            ("full_train_0_250ms_mean", "full_post_mean_rate_hz"),
            ("early_p1_p2_0_50ms_mean", "early_p1_p2_mean_rate_hz"),
        ]
    else:
        windows = [
            ("full_train_0_250ms_peak_psth", "full_post_peak_psth_hz"),
            ("early_p1_p2_0_50ms_peak_psth", "early_p1_p2_peak_psth_hz"),
        ]
    for group_name, data in groups.items():
        for window, post_column in windows:
            rows.append(
                {
                    "analysis_level": level,
                    "comparison_group": group_name,
                    "post_window": window,
                    "n": len(data),
                    "responsive_pass_n": int(data["responsive_pass"].sum()),
                    "pre_median_hz": data["pre_rate_hz"].median(),
                    "pre_mean_hz": data["pre_rate_hz"].mean(),
                    "post_median_hz": data[post_column].median(),
                    "post_mean_hz": data[post_column].mean(),
                    "post_minus_pre_median_hz": (
                        data[post_column] - data["pre_rate_hz"]
                    ).median(),
                    "post_minus_pre_mean_hz": (
                        data[post_column] - data["pre_rate_hz"]
                    ).mean(),
                }
            )
    return pd.DataFrame(rows)


def _psth_summary_table(summaries, level):
    rows = []
    for group_name, summary in summaries.items():
        rows.append(
            pd.DataFrame(
                {
                    "analysis_level": level,
                    "comparison_group": group_name,
                    "n_observations": summary["n"],
                    "time_ms": summary["time_ms"],
                    "mean_rate_hz": summary["mean_rate_hz"],
                    "sem_rate_hz": summary["sem_rate_hz"],
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def _filter_psth_summary_table(summaries, level):
    rows = []
    for group_name, summary in summaries.items():
        for width, values in summary["by_width"].items():
            rows.append(
                pd.DataFrame(
                    {
                        "analysis_level": level,
                        "comparison_group": group_name,
                        "n_observations": summary["n"],
                        "boxcar_bins": width,
                        "centered_filter_backward_extent_ms": (width - 1) / 2,
                        "time_ms_bin_center": summary["time_ms"],
                        "mean_rate_hz": values["mean_rate_hz"],
                        "sem_rate_hz": values["sem_rate_hz"],
                    }
                )
            )
    return pd.concat(rows, ignore_index=True)


def _audit_alignment_timestamps(unit_store_path):
    tolerance_ms = 1e-6
    audit_rows = []
    internal_max_error_ms = 0.0
    unit_count = 0
    representative_by_recording = {}
    with h5py.File(unit_store_path, "r") as store:
        train_edges = store["axes/train_bin_edges_ms"][:]
        train_centers = store["axes/train_bin_centers_ms"][:]
        pulse_onsets_axis = store["axes/pulse_onsets_within_train_ms"][:]
        pulse_offsets_axis = store["axes/pulse_offsets_within_train_ms"][:]
        center_error = float(
            np.max(np.abs(train_centers - (train_edges[:-1] + train_edges[1:]) / 2.0))
        )
        for unit_group in store["units"].values():
            unit_count += 1
            train_onsets = unit_group["train_full_50/alignment_onset_s"][:]
            pulse_onsets = unit_group["pulse_250/alignment_onset_s"][:].reshape(
                len(train_onsets), len(pulse_onsets_axis)
            )
            relative_ms = (pulse_onsets - train_onsets[:, None]) * 1000.0
            error = float(np.max(np.abs(relative_ms - pulse_onsets_axis[None, :])))
            internal_max_error_ms = max(internal_max_error_ms, error)
            recording = str(unit_group.attrs["recording"])
            representative_by_recording.setdefault(
                recording,
                {
                    "train_onsets_s": train_onsets,
                    "pulse_onsets_s": pulse_onsets,
                },
            )

    raw_paths = list_raw_files(DEFAULT_STIM_RAW_ROOTS)
    for recording, stored in sorted(representative_by_recording.items()):
        row = {
            "recording": recording,
            "raw_file": "",
            "status": "error",
            "raw_event_count": np.nan,
            "raw_pulses_per_train": np.nan,
            "raw_first_command_offset_from_event_ms": np.nan,
            "relative_pulse_onsets_ms": "",
            "relative_pulse_offsets_ms": "",
            "max_abs_train_alignment_error_ms": np.nan,
            "max_abs_pulse_alignment_error_ms": np.nan,
            "passes_1e-6_ms_tolerance": False,
            "error": "",
        }
        try:
            raw_file = find_matching_raw_file(
                recording, DEFAULT_STIM_RAW_ROOTS, raw_paths=raw_paths
            )
            if raw_file is None:
                raise FileNotFoundError("no matching .raw file")
            events = stim_events_from_raw(raw_file)
            epochs = load_pulse_epochs_from_raw(raw_file)
            event_times = events["event_time_s"].to_numpy(dtype=float)
            epoch_starts_ms = np.asarray([epoch.start_ms for epoch in epochs], dtype=float)
            epoch_ends_ms = np.asarray([epoch.end_ms for epoch in epochs], dtype=float)
            expected_train_s = event_times + epoch_starts_ms[0] / 1000.0
            expected_pulse_s = event_times[:, None] + epoch_starts_ms[None, :] / 1000.0
            train_error_ms = float(
                np.max(np.abs(stored["train_onsets_s"] - expected_train_s)) * 1000.0
            )
            pulse_error_ms = float(
                np.max(np.abs(stored["pulse_onsets_s"] - expected_pulse_s)) * 1000.0
            )
            relative_starts = epoch_starts_ms - epoch_starts_ms[0]
            relative_ends = epoch_ends_ms - epoch_starts_ms[0]
            axes_match = bool(
                np.allclose(relative_starts, pulse_onsets_axis, atol=tolerance_ms, rtol=0)
                and np.allclose(relative_ends, pulse_offsets_axis, atol=tolerance_ms, rtol=0)
            )
            passed = bool(
                train_error_ms <= tolerance_ms
                and pulse_error_ms <= tolerance_ms
                and axes_match
            )
            row.update(
                {
                    "raw_file": str(raw_file),
                    "status": "pass" if passed else "mismatch",
                    "raw_event_count": len(events),
                    "raw_pulses_per_train": len(epochs),
                    "raw_first_command_offset_from_event_ms": float(epoch_starts_ms[0]),
                    "relative_pulse_onsets_ms": ";".join(f"{x:g}" for x in relative_starts),
                    "relative_pulse_offsets_ms": ";".join(f"{x:g}" for x in relative_ends),
                    "max_abs_train_alignment_error_ms": train_error_ms,
                    "max_abs_pulse_alignment_error_ms": pulse_error_ms,
                    "passes_1e-6_ms_tolerance": passed,
                }
            )
        except Exception as exc:  # noqa: BLE001 - audit retains per-recording failures
            row["error"] = f"{type(exc).__name__}: {exc}"
        audit_rows.append(row)

    audit = pd.DataFrame(audit_rows)
    raw_failures = int((~audit["passes_1e-6_ms_tolerance"]).sum())
    summary = {
        "unit_observations_checked": unit_count,
        "recording_variants_checked_against_raw": len(audit),
        "raw_alignment_failures": raw_failures,
        "all_raw_alignments_pass": raw_failures == 0,
        "alignment_tolerance_ms": tolerance_ms,
        "maximum_internal_pulse_vs_train_alignment_error_ms": internal_max_error_ms,
        "bin_width_ms": float(train_edges[1] - train_edges[0]),
        "bin_coordinate_convention": "edge histogram plotted at bin centers",
        "onset_bin_edges_ms": [0.0, 1.0],
        "onset_bin_center_ms": 0.5,
        "bin_center_midpoint_max_error_ms": center_error,
        "relative_pulse_onsets_ms": pulse_onsets_axis.tolist(),
        "relative_pulse_offsets_ms": pulse_offsets_axis.tolist(),
        "annotation_source": (
            "vertical onset lines and yellow windows both use the HDF5 axes copied from "
            "the same raw-file pulse epochs used to construct alignment_onset_s"
        ),
        "additional_plot_offset_ms": 0.0,
    }
    if internal_max_error_ms > tolerance_ms or center_error > tolerance_ms:
        raise ValueError(f"Internal PSTH alignment audit failed: {summary}")
    return audit, summary


def _style(plt):
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
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
