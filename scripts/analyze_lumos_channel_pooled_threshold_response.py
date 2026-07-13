#!/usr/bin/env python
"""Pool sorted-unit spikes by channel and require mean-PSTH plus trial coincidence."""

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
    OUTPUT_NAME as UNIT_PSTH_OUTPUT_NAME,
    STORE_NAME as UNIT_STORE_NAME,
    _write_metadata_table,
)
from scripts.analyze_lumos_per_unit_threshold_response import (  # noqa: E402
    RESPONSE_THRESHOLD_HZ_ABOVE_BASELINE,
    TARGETS,
    _early_decay_candidates,
    _plot_pulse_profiles,
    _pulse_position_profiles,
    _response_metrics,
)


OUTPUT_NAME = "lumos_channel_pooled_threshold_response_development"
CHANNEL_STORE_NAME = "lumos_channel_pooled_psth_development.h5"
COLORS = {"no_opsin": "#4C78A8", "opsin": "#E45756"}
MINIMUM_SAME_BIN_TRIALS = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--unit-psth-dir", type=Path, default=DEFAULT_JOB_DIR / UNIT_PSTH_OUTPUT_NAME
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_JOB_DIR / OUTPUT_NAME)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    unit_psth_dir = args.unit_psth_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    unit_metadata = pd.read_csv(unit_psth_dir / "unit_metadata.csv")
    required = {"best_channel_index", "best_channel_id", "unit_observation_id"}
    missing = required - set(unit_metadata.columns)
    if missing:
        raise ValueError(f"Unified unit metadata lacks channel fields: {sorted(missing)}")

    channel_metadata_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    inventory_rows: list[dict[str, object]] = []
    channel_store_path = staging_dir / CHANNEL_STORE_NAME
    group_columns = ["analyzer_path", "best_channel_index"]

    with h5py.File(unit_psth_dir / UNIT_STORE_NAME, "r") as units, h5py.File(
        channel_store_path, "w"
    ) as channels:
        _copy_axes_and_attributes(units, channels)
        channel_groups = channels.create_group("channels")
        pulse_time = units["axes/pulse_bin_centers_ms"][:]
        train_time = units["axes/train_bin_centers_ms"][:]
        spontaneous_mask = (train_time >= -500) & (train_time < 0)
        baseline_mask = (train_time >= -200) & (train_time < 0)
        pulse_response_mask = (pulse_time >= 0) & (pulse_time < 50)
        train_response_mask = (train_time >= 0) & (train_time < 250)

        grouped = list(unit_metadata.groupby(group_columns, sort=True, dropna=False))
        for index, ((analyzer_path, channel_index), members) in enumerate(grouped, start=1):
            channel_observation_id = f"C{index:04d}"
            first = members.iloc[0]
            _require_constant_metadata(members)
            unit_observation_ids = members["unit_observation_id"].astype(str).tolist()
            pulse_counts = _sum_unit_dataset(
                units, unit_observation_ids, "pulse_250/counts"
            )
            grouped_counts = _sum_unit_dataset(
                units, unit_observation_ids, "train_grouped_50x5/counts"
            )
            train_counts = _sum_unit_dataset(
                units, unit_observation_ids, "train_full_50/counts"
            )
            pulse_rate = pulse_counts.astype(np.float32) * 1000.0
            grouped_rate = grouped_counts.astype(np.float32) * 1000.0 / 5.0
            train_rate = train_counts.astype(np.float32) * 1000.0
            pulse_smoothed = _smooth_rows(pulse_rate)
            grouped_smoothed = _smooth_rows(grouped_rate)
            train_smoothed = _smooth_rows(train_rate)

            metadata = {
                "channel_observation_id": channel_observation_id,
                "channel_key": (
                    f"{first['recording']}|{first['well']}|{first['raw_variant']}|"
                    f"channel_index={int(channel_index)}"
                ),
                "recording": first["recording"],
                "well": first["well"],
                "organoid_id": first["organoid_id"],
                "condition": first["condition"],
                "raw_variant": first["raw_variant"],
                "analyzer_path": analyzer_path,
                "best_channel_index": int(channel_index),
                "best_channel_id": str(first["best_channel_id"]),
                "units_pooled": int(len(members)),
                "good_units_pooled": int(members["KSLabel"].eq("good").sum()),
                "mua_units_pooled": int(members["KSLabel"].eq("mua").sum()),
                "source_unit_observation_ids": ";".join(unit_observation_ids),
                "source_unit_ids": ";".join(members["unit_id"].astype(str)),
                "hdf5_group": f"/channels/{channel_observation_id}",
            }
            channel_metadata_rows.append(metadata)
            channel_group = channel_groups.create_group(channel_observation_id)
            for key, value in metadata.items():
                channel_group.attrs[key] = value
            _write_matrix_group(
                channel_group.create_group("pulse_250"),
                pulse_counts,
                pulse_rate,
                pulse_smoothed,
            )
            _write_matrix_group(
                channel_group.create_group("train_grouped_50x5"),
                grouped_counts,
                grouped_rate,
                grouped_smoothed,
            )
            _write_matrix_group(
                channel_group.create_group("train_full_50"),
                train_counts,
                train_rate,
                train_smoothed,
            )

            spontaneous_rate = float(train_rate[:, spontaneous_mask].mean())
            subtraction_baseline_rate = float(train_rate[:, baseline_mask].mean())
            baseline_mean_psth = train_smoothed[:, baseline_mask].mean(axis=0)
            baseline_sd = float(np.std(baseline_mean_psth, ddof=1))
            common = {
                **metadata,
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
            pulse_by_position = pulse_smoothed.reshape(50, 5, -1)
            for pulse_index in range(5):
                metric_rows.append(
                    _channel_response_metrics(
                        common,
                        f"pulse_{pulse_index + 1}",
                        pulse_by_position[:, pulse_index, :][:, pulse_response_mask],
                        pulse_time[pulse_response_mask],
                    )
                )
            metric_rows.append(
                _channel_response_metrics(
                    common,
                    "train_250ms",
                    train_smoothed[:, train_response_mask],
                    train_time[train_response_mask],
                )
            )
            inventory_rows.append(
                {
                    "channel_observation_id": channel_observation_id,
                    "units_pooled": len(members),
                    "pulse_250_shape": str(tuple(pulse_counts.shape)),
                    "train_grouped_50x5_shape": str(tuple(grouped_counts.shape)),
                    "train_full_50_shape": str(tuple(train_counts.shape)),
                    "total_train_window_spikes": int(train_counts.sum()),
                }
            )
            if index % 50 == 0 or index == len(grouped):
                print(f"[{index:03d}/{len(grouped):03d}] channels pooled", flush=True)

        channel_metadata = pd.DataFrame(channel_metadata_rows)
        metrics = pd.DataFrame(metric_rows)
        _write_metadata_table(channels.create_group("metadata"), channel_metadata)
        _write_metadata_table(channels.create_group("response_metrics"), metrics)

    channel_metadata.to_csv(staging_dir / "channel_metadata.csv", index=False)
    metrics.to_csv(staging_dir / "per_channel_threshold_response_metrics.csv", index=False)
    pd.DataFrame(inventory_rows).to_csv(staging_dir / "channel_matrix_inventory.csv", index=False)
    responsive = metrics.loc[metrics["responsive_candidate"]].copy()
    responsive.to_csv(staging_dir / "responsive_channel_targets.csv", index=False)
    decision_metrics = metrics.copy()
    decision_metrics["mean_psth_above_baseline_only_candidate"] = decision_metrics[
        "mean_psth_above_baseline_candidate"
    ]
    decision_metrics["mean_psth_above_baseline_candidate"] = decision_metrics[
        "responsive_candidate"
    ]
    profiles = _pulse_position_profiles(decision_metrics, "channel_observation_id")
    profiles.to_csv(staging_dir / "per_channel_pulse_position_profiles.csv", index=False)
    early_only_details = _early_only_channel_details(profiles, metrics)
    early_only_details.to_csv(staging_dir / "early_only_channel_details.csv", index=False)
    early_decay_profiles, early_decay_targets = _early_decay_candidates(
        profiles, decision_metrics, "channel_observation_id"
    )
    early_decay_profiles.to_csv(
        staging_dir / "top_50_early_greater_than_late_channel_profiles.csv", index=False
    )
    top_candidates = (
        responsive.sort_values(
            ["positive_going_psth_sum_spikes_per_trial", "peak_mean_excess_hz"],
            ascending=False,
        )
        .head(50)
        .copy()
    )
    top_candidates.to_csv(staging_dir / "top_50_mean_psth_channel_candidates.csv", index=False)
    _plot_overview(metrics, staging_dir / "channel_baseline_response_overview.png")
    _plot_pulse_profiles(
        decision_metrics,
        profiles,
        "channel_observation_id",
        staging_dir / "channel_pulse_position_dynamics.png",
    )
    _plot_early_only_heatmaps(
        early_only_details,
        staging_dir / "early_only_channel_five_pulse_heatmaps.png",
    )
    _plot_pages(
        top_candidates,
        channel_store_path,
        staging_dir / "top_50_mean_psth_channel_raster_psth.pdf",
    )
    _plot_pages(
        early_decay_targets,
        channel_store_path,
        staging_dir / "top_50_early_greater_than_late_channel_raster_psth.pdf",
    )
    _plot_early_only_five_pulse_pages(
        early_only_details,
        channel_store_path,
        staging_dir / "early_only_channel_five_pulse_raster_psth.pdf",
    )
    _plot_ranked_early_only_condition_comparison(
        early_only_details,
        channel_store_path,
        staging_dir / "ranked_opsin_vs_no_opsin_early_only_psth.pdf",
    )
    (staging_dir / "METHOD_SPECIFICATION.md").write_text(
        _method_specification(channel_metadata, metrics, early_only_details),
        encoding="utf-8",
    )
    (staging_dir / "provenance.json").write_text(
        json.dumps(
            {
                "development_output": True,
                "overwrite_policy": "entire output directory replaced after every successful run",
                "source_unit_store": str((unit_psth_dir / UNIT_STORE_NAME).resolve()),
                "channel_observations": int(len(channel_metadata)),
                "source_unit_observations": int(len(unit_metadata)),
                "response_threshold_hz_above_baseline": RESPONSE_THRESHOLD_HZ_ABOVE_BASELINE,
                "minimum_same_bin_trials": MINIMUM_SAME_BIN_TRIALS,
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
    print(f"\nChannel analysis: {output_dir}")
    print(f"Channel observations: {len(channel_metadata)}")
    print(f"Responsive target rows: {len(responsive)}")
    return 0


def _copy_axes_and_attributes(source, destination) -> None:
    for key, value in source.attrs.items():
        destination.attrs[key] = value
    destination.attrs["aggregation_level"] = "recording channel"
    destination.attrs["pooling_rule"] = "sum spikes across all good/MUA units with same best channel"
    source.copy("axes", destination)


def _require_constant_metadata(members: pd.DataFrame) -> None:
    for column in ["recording", "well", "condition", "raw_variant", "best_channel_id"]:
        if members[column].nunique(dropna=False) != 1:
            raise ValueError(f"Channel group has inconsistent {column}: {members[column].tolist()}")


def _sum_unit_dataset(source, unit_ids: list[str], relative_path: str) -> np.ndarray:
    first = source[f"units/{unit_ids[0]}/{relative_path}"][:].astype(np.uint32)
    result = first
    for uid in unit_ids[1:]:
        result += source[f"units/{uid}/{relative_path}"][:].astype(np.uint32)
    return result


def _smooth_rows(rate_matrix: np.ndarray) -> np.ndarray:
    return np.asarray(
        [np.convolve(row, BOXCAR, mode="same") for row in rate_matrix], dtype=np.float32
    )


def _channel_response_metrics(
    common: dict[str, object],
    target: str,
    response_smoothed: np.ndarray,
    time_ms: np.ndarray,
) -> dict[str, object]:
    """Retain the mean-PSTH flag and add the channel-level coincidence decision."""
    result = _response_metrics(common, target, response_smoothed, time_ms)
    coincidence = int(result["maximum_trials_above_baseline_same_bin"])
    result["minimum_same_bin_trials_required"] = MINIMUM_SAME_BIN_TRIALS
    result["same_bin_trial_coincidence_candidate"] = bool(
        coincidence >= MINIMUM_SAME_BIN_TRIALS
    )
    result["responsive_candidate"] = bool(
        result["mean_psth_above_baseline_candidate"]
        and result["same_bin_trial_coincidence_candidate"]
    )
    return result


def _write_matrix_group(group, counts, rate, smoothed) -> None:
    options = {"compression": "gzip", "compression_opts": 4, "shuffle": True}
    group.create_dataset("counts", data=counts, **options)
    group.create_dataset("rate_hz", data=rate, **options)
    group.create_dataset("smoothed_rate_hz", data=smoothed, **options)
    group.create_dataset("row_has_any_spike", data=counts.sum(axis=1) > 0)
    group.attrs["rows"] = counts.shape[0]
    group.attrs["columns_1ms_bins"] = counts.shape[1]
    group.attrs["boxcar_weights"] = BOXCAR


def _early_only_channel_details(
    profiles: pd.DataFrame, metrics: pd.DataFrame
) -> pd.DataFrame:
    details = profiles.loc[
        profiles["pulse_response_category"].eq("early_only_p1_p2")
    ].copy()
    if details.empty:
        return details
    indexed = metrics.set_index(["channel_observation_id", "target"])
    common = metrics.loc[metrics["target"].eq("pulse_1")].set_index(
        "channel_observation_id"
    )
    for column in [
        "spontaneous_rate_hz",
        "subtraction_baseline_rate_hz",
        "source_unit_ids",
        "good_units_pooled",
        "mua_units_pooled",
    ]:
        details[column] = details["channel_observation_id"].map(common[column])
    for pulse in range(1, 6):
        target = f"pulse_{pulse}"
        pulse_rows = indexed.xs(target, level="target")
        for source_column, output_column in [
            ("peak_mean_excess_hz", f"pulse_{pulse}_peak_mean_excess_hz"),
            ("peak_latency_ms", f"pulse_{pulse}_peak_latency_ms"),
            (
                "maximum_trial_fraction_above_baseline_same_bin",
                f"pulse_{pulse}_max_same_bin_trial_fraction",
            ),
        ]:
            details[output_column] = details["channel_observation_id"].map(
                pulse_rows[source_column]
            )
    train_rows = indexed.xs("train_250ms", level="target")
    for source_column, output_column in [
        (
            "positive_going_psth_sum_spikes_per_trial",
            "full_train_positive_excess_spikes_per_trial",
        ),
        ("peak_mean_excess_hz", "full_train_peak_mean_excess_hz"),
        ("peak_latency_ms", "full_train_peak_latency_ms"),
        (
            "maximum_trials_above_baseline_same_bin",
            "full_train_max_same_bin_trials",
        ),
        (
            "maximum_trial_fraction_above_baseline_same_bin",
            "full_train_max_same_bin_trial_fraction",
        ),
        ("responsive_candidate", "full_train_responsive_candidate"),
    ]:
        details[output_column] = details["channel_observation_id"].map(
            train_rows[source_column]
        )
    details["condition_order"] = details["condition"].map(
        {"opsin": 0, "no_opsin": 1}
    )
    details = details.sort_values(
        [
            "condition_order",
            "early_p1_p2_mean_excess_spikes_per_trial",
            "recording",
            "best_channel_index",
        ],
        ascending=[True, False, True, True],
    ).drop(columns="condition_order")
    details.insert(0, "early_only_rank", np.arange(1, len(details) + 1))
    details.insert(
        1,
        "condition_rank",
        details.groupby("condition", sort=False).cumcount().add(1).to_numpy(),
    )
    return details


def _plot_early_only_heatmaps(details: pd.DataFrame, output_path: Path) -> None:
    from matplotlib.colors import PowerNorm

    if details.empty:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.axis("off")
        ax.text(0.5, 0.5, "No early-only channels.", ha="center", va="center")
        fig.savefig(output_path, dpi=220)
        plt.close(fig)
        return
    magnitude_max = max(
        float(
            details[
                [
                    f"pulse_{pulse}_positive_excess_spikes_per_trial"
                    for pulse in range(1, 6)
                ]
            ].to_numpy(float).max()
        ),
        0.02,
    )
    coincidence_max = max(
        float(
            details[
                [f"pulse_{pulse}_max_same_bin_trials" for pulse in range(1, 6)]
            ].to_numpy(float).max()
        ),
        1,
    )
    fig, axes = plt.subplots(2, 2, figsize=(14, 12), constrained_layout=True)
    for column, condition in enumerate(["opsin", "no_opsin"]):
        subset = details.loc[details["condition"].eq(condition)]
        magnitude = subset[
            [f"pulse_{pulse}_positive_excess_spikes_per_trial" for pulse in range(1, 6)]
        ].to_numpy(float)
        coincidence = subset[
            [f"pulse_{pulse}_max_same_bin_trials" for pulse in range(1, 6)]
        ].to_numpy(float)
        candidate = subset[
            [f"pulse_{pulse}_responsive_candidate" for pulse in range(1, 6)]
        ].to_numpy(bool)
        labels = [
            f"R{row.condition_rank} | {row.channel_observation_id} | "
            f"{row.well} ch{row.best_channel_id}"
            for row in subset.itertuples(index=False)
        ]
        image = axes[0, column].imshow(
            magnitude,
            aspect="auto",
            cmap="magma",
            norm=PowerNorm(gamma=0.5, vmin=0, vmax=magnitude_max),
        )
        image2 = axes[1, column].imshow(
            coincidence,
            aspect="auto",
            cmap="viridis",
            vmin=0,
            vmax=coincidence_max,
        )
        for row_index in range(len(subset)):
            for pulse_index in range(5):
                if candidate[row_index, pulse_index]:
                    for ax in [axes[0, column], axes[1, column]]:
                        ax.text(
                            pulse_index,
                            row_index,
                            "★",
                            color="white",
                            ha="center",
                            va="center",
                            fontsize=8,
                        )
        for row_index, measure in enumerate(
            ["Positive response magnitude", "Trial coincidence (no cutoff)"]
        ):
            ax = axes[row_index, column]
            ax.set_xticks(range(5), ["P1", "P2", "P3", "P4", "P5"])
            ax.set_yticks(range(len(labels)), labels, fontsize=7)
            ax.set_title(f"{'Opsin' if condition == 'opsin' else 'No opsin'} | {measure}")
    fig.colorbar(image, ax=axes[0, :], label="Positive excess spikes/trial")
    fig.colorbar(
        image2,
        ax=axes[1, :],
        label="Maximum same-bin trials (descriptive)",
    )
    fig.suptitle(
        "Early-only recording-channel candidates ranked within condition; "
        "stars mark mean-PSTH + ≥3 same-bin trials",
        fontsize=14,
    )
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def _plot_early_only_five_pulse_pages(
    details: pd.DataFrame, store_path: Path, output_path: Path
) -> None:
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(output_path) as pdf, h5py.File(store_path, "r") as store:
        pulse_time = store["axes/pulse_bin_centers_ms"][:]
        if details.empty:
            fig, ax = plt.subplots(figsize=(8, 3))
            ax.axis("off")
            ax.text(0.5, 0.5, "No early-only channels.", ha="center", va="center")
            pdf.savefig(fig)
            plt.close(fig)
            return
        for row in details.itertuples(index=False):
            group = store[f"channels/{row.channel_observation_id}/pulse_250"]
            counts = group["counts"][:].reshape(50, 5, -1)
            smoothed = group["smoothed_rate_hz"][:].reshape(50, 5, -1)
            mean_excess = smoothed.mean(axis=0) - row.subtraction_baseline_rate_hz
            figure, axes = plt.subplots(
                2,
                5,
                figsize=(18, 7),
                sharex=True,
                gridspec_kw={"height_ratios": [2.2, 1.0], "hspace": 0.08, "wspace": 0.12},
            )
            psth_min = min(float(mean_excess.min()), 0.0)
            psth_max = max(float(mean_excess.max()), 0.01)
            for pulse_index in range(5):
                raster_ax = axes[0, pulse_index]
                psth_ax = axes[1, pulse_index]
                spike_rows, spike_bins = np.nonzero(counts[:, pulse_index, :])
                multiplicities = counts[spike_rows, pulse_index, spike_bins].astype(int)
                raster_ax.scatter(
                    np.repeat(pulse_time[spike_bins], multiplicities),
                    np.repeat(spike_rows + 1, multiplicities),
                    s=4,
                    color="black",
                    linewidths=0,
                )
                raster_ax.set_ylim(50.8, 0.2)
                candidate = bool(getattr(row, f"pulse_{pulse_index + 1}_responsive_candidate"))
                raster_ax.set_title(
                    f"P{pulse_index + 1} | candidate={candidate}\n"
                    f"positive area={getattr(row, f'pulse_{pulse_index + 1}_positive_excess_spikes_per_trial'):.3g} | "
                    f"max same-bin={getattr(row, f'pulse_{pulse_index + 1}_max_same_bin_trials')}/50",
                    fontsize=8.5,
                    color="#087830" if candidate else "#555555",
                )
                psth_ax.plot(
                    pulse_time,
                    mean_excess[pulse_index],
                    drawstyle="steps-mid",
                    color=COLORS[row.condition],
                    linewidth=1.3,
                )
                psth_ax.axhline(0, color="#555555", linewidth=0.8)
                psth_ax.set_ylim(psth_min - 0.05 * (psth_max - psth_min), psth_max * 1.05)
                for ax in [raster_ax, psth_ax]:
                    ax.axvline(0, color="black", linewidth=0.8)
                    ax.axvspan(0, 9.5, color="#F2CF5B", alpha=0.28)
                    if pulse_index > 0:
                        ax.axvspan(-50, -40.5, color="#F2CF5B", alpha=0.2)
                psth_ax.set_xlabel("Time (ms)")
                if pulse_index == 0:
                    raster_ax.set_ylabel("Trial")
                    psth_ax.set_ylabel("Excess Hz")
                else:
                    raster_ax.set_yticklabels([])
                    psth_ax.set_yticklabels([])
            figure.suptitle(
                f"Rank {row.early_only_rank} | {row.channel_observation_id} | "
                f"{row.well} {row.condition} | channel {row.best_channel_id} | "
                f"{row.units_pooled} units pooled | pattern {row.pulse_response_pattern}\n"
                "All five positions use the same −200–0 ms pre-pulse-1 baseline; "
                "PSTHs use one [1,1,1]/3 boxcar; candidates require ≥3/50 same-bin trials",
                fontsize=12,
            )
            pdf.savefig(figure)
            plt.close(figure)


def _plot_ranked_early_only_condition_comparison(
    details: pd.DataFrame, store_path: Path, output_path: Path
) -> None:
    """Place equally ranked opsin and no-opsin five-pulse PSTHs side by side."""
    from matplotlib.backends.backend_pdf import PdfPages

    per_page = 4
    opsin = details.loc[details["condition"].eq("opsin")].set_index("condition_rank")
    no_opsin = details.loc[details["condition"].eq("no_opsin")].set_index(
        "condition_rank"
    )
    maximum_rank = int(details["condition_rank"].max()) if not details.empty else 0
    with PdfPages(output_path) as pdf, h5py.File(store_path, "r") as store:
        pulse_time = store["axes/pulse_bin_centers_ms"][:]
        train_time = store["axes/train_bin_centers_ms"][:]
        train_display_mask = (train_time >= -200) & (train_time < 250)
        if maximum_rank == 0:
            figure, ax = plt.subplots(figsize=(8, 3))
            ax.axis("off")
            ax.text(0.5, 0.5, "No early-only channels.", ha="center", va="center")
            pdf.savefig(figure)
            plt.close(figure)
            return
        for first_rank in range(1, maximum_rank + 1, per_page):
            ranks = list(range(first_rank, min(first_rank + per_page, maximum_rank + 1)))
            figure, axes = plt.subplots(
                len(ranks),
                12,
                figsize=(24, 2.4 * len(ranks) + 1.4),
                squeeze=False,
                sharex=False,
                gridspec_kw={
                    "hspace": 0.48,
                    "wspace": 0.15,
                    "width_ratios": [1, 1, 1, 1, 1, 2.2, 1, 1, 1, 1, 1, 2.2],
                },
            )
            for row_index, rank in enumerate(ranks):
                paired_rows = [
                    opsin.loc[rank] if rank in opsin.index else None,
                    no_opsin.loc[rank] if rank in no_opsin.index else None,
                ]
                plotted: list[tuple[int, pd.Series, np.ndarray, np.ndarray]] = []
                for condition_index, candidate_row in enumerate(paired_rows):
                    start_column = condition_index * 6
                    if candidate_row is None:
                        for column in range(start_column, start_column + 6):
                            axes[row_index, column].axis("off")
                        continue
                    pulse_group = store[
                        f"channels/{candidate_row.channel_observation_id}/pulse_250"
                    ]
                    pulse_smoothed = pulse_group["smoothed_rate_hz"][:].reshape(
                        50, 5, -1
                    )
                    pulse_mean_excess = (
                        pulse_smoothed.mean(axis=0)
                        - float(candidate_row.subtraction_baseline_rate_hz)
                    )
                    train_smoothed = store[
                        f"channels/{candidate_row.channel_observation_id}/train_full_50/"
                        "smoothed_rate_hz"
                    ][:]
                    train_mean_excess = (
                        train_smoothed.mean(axis=0)
                        - float(candidate_row.subtraction_baseline_rate_hz)
                    )
                    plotted.append(
                        (
                            start_column,
                            candidate_row,
                            pulse_mean_excess,
                            train_mean_excess,
                        )
                    )
                if plotted:
                    y_min = min(
                        0.0,
                        *(
                            min(
                                float(pulse_values.min()),
                                float(train_values[train_display_mask].min()),
                            )
                            for _, _, pulse_values, train_values in plotted
                        ),
                    )
                    y_max = max(
                        0.01,
                        *(
                            max(
                                float(pulse_values.max()),
                                float(train_values[train_display_mask].max()),
                            )
                            for _, _, pulse_values, train_values in plotted
                        ),
                    )
                    padding = max((y_max - y_min) * 0.08, 0.5)
                for start_column, candidate_row, mean_excess, train_excess in plotted:
                    condition = str(candidate_row.condition)
                    for pulse_index in range(5):
                        ax = axes[row_index, start_column + pulse_index]
                        ax.plot(
                            pulse_time,
                            mean_excess[pulse_index],
                            drawstyle="steps-mid",
                            color=COLORS[condition],
                            linewidth=1.15,
                        )
                        ax.axhline(0, color="#666666", linewidth=0.7)
                        ax.axvline(0, color="black", linewidth=0.7)
                        ax.axvspan(0, 9.5, color="#F2CF5B", alpha=0.28)
                        if pulse_index > 0:
                            ax.axvspan(-50, -40.5, color="#F2CF5B", alpha=0.18)
                        ax.set_xlim(-50, 50)
                        ax.set_ylim(y_min - padding, y_max + padding)
                        is_candidate = bool(
                            candidate_row[f"pulse_{pulse_index + 1}_responsive_candidate"]
                        )
                        ax.set_title(
                            f"P{pulse_index + 1}{' ★' if is_candidate else ''}",
                            fontsize=8,
                            color="#087830" if is_candidate else "#555555",
                        )
                        ax.tick_params(labelsize=7)
                        if pulse_index == 0:
                            ax.set_ylabel(
                                f"Rank {rank}\n{candidate_row.channel_observation_id}\n"
                                f"{candidate_row.well} ch{candidate_row.best_channel_id}\nExcess Hz",
                                fontsize=7,
                            )
                        else:
                            ax.set_yticklabels([])
                        if row_index == len(ranks) - 1:
                            ax.set_xlabel("ms", fontsize=7)
                    train_ax = axes[row_index, start_column + 5]
                    train_ax.plot(
                        train_time[train_display_mask],
                        train_excess[train_display_mask],
                        drawstyle="steps-mid",
                        color=COLORS[condition],
                        linewidth=1.15,
                    )
                    train_ax.axhline(0, color="#666666", linewidth=0.7)
                    for pulse_start in [0, 50, 100, 150, 200]:
                        train_ax.axvline(pulse_start, color="black", linewidth=0.45)
                        train_ax.axvspan(
                            pulse_start,
                            pulse_start + 9.5,
                            color="#F2CF5B",
                            alpha=0.28,
                        )
                    train_ax.set_xlim(-200, 250)
                    train_ax.set_ylim(y_min - padding, y_max + padding)
                    train_candidate = bool(candidate_row.full_train_responsive_candidate)
                    train_ax.set_title(
                        f"FULL TRAIN 0–250 ms{' ★' if train_candidate else ''}",
                        fontsize=8,
                        color="#087830" if train_candidate else "#555555",
                    )
                    train_ax.tick_params(labelsize=7)
                    train_ax.set_yticklabels([])
                    if row_index == len(ranks) - 1:
                        train_ax.set_xlabel("ms", fontsize=7)
            figure.text(0.265, 0.965, "OPSIN", color=COLORS["opsin"], ha="center", fontsize=13)
            figure.text(
                0.755,
                0.965,
                "NO OPSIN",
                color=COLORS["no_opsin"],
                ha="center",
                fontsize=13,
            )
            figure.suptitle(
                "Early-only channel PSTHs paired by within-condition response-magnitude rank\n"
                "P1–P5 plus continuous full train; shared y-scale within each rank pair; "
                "one [1,1,1]/3 boxcar; shared pre-P1 baseline; ≥3/50 same-bin trials",
                y=1.035,
                fontsize=11,
            )
            figure.subplots_adjust(top=0.89, bottom=0.08, left=0.06, right=0.99)
            pdf.savefig(figure, bbox_inches="tight")
            plt.close(figure)


def _plot_overview(metrics: pd.DataFrame, output_path: Path) -> None:
    rng = np.random.default_rng(20260713)
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.5), constrained_layout=True)
    x = np.arange(len(TARGETS))
    for condition, offset in [("no_opsin", -0.12), ("opsin", 0.12)]:
        subset = metrics.loc[metrics["condition"].eq(condition)]
        for target_index, target in enumerate(TARGETS):
            values = subset.loc[
                subset["target"].eq(target),
                "maximum_trial_fraction_above_baseline_same_bin",
            ].to_numpy()
            axes[0].scatter(
                target_index + offset + rng.normal(0, 0.035, len(values)),
                values,
                s=10,
                alpha=0.3,
                color=COLORS[condition],
                label=condition if target_index == 0 else None,
            )
    axes[0].set_xticks(x, ["P1", "P2", "P3", "P4", "P5", "Train"])
    axes[0].set_ylabel("Maximum same-bin trial fraction")
    axes[0].set_title("Descriptive trial coincidence per recording-channel")
    axes[0].legend(frameon=False)

    summary = (
        metrics.groupby(["condition", "target"])[
            "responsive_candidate"
        ]
        .mean()
        .mul(100)
    )
    width = 0.36
    for condition, offset in [("no_opsin", -width / 2), ("opsin", width / 2)]:
        values = summary.loc[condition].reindex(TARGETS).fillna(0)
        axes[1].bar(x + offset, values, width, color=COLORS[condition], label=condition)
    axes[1].set_xticks(x, ["P1", "P2", "P3", "P4", "P5", "Train"])
    axes[1].set_ylabel("Channels meeting both criteria (%)")
    axes[1].set_title("Mean-PSTH + ≥3 same-bin-trial candidates")
    axes[1].legend(frameon=False)
    fig.suptitle("Spikes pooled within best channel; N = recording-channel observation")
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def _plot_pages(rows: pd.DataFrame, store_path: Path, output_path: Path) -> None:
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(output_path) as pdf, h5py.File(store_path, "r") as store:
        pulse_time = store["axes/pulse_bin_centers_ms"][:]
        train_time = store["axes/train_bin_centers_ms"][:]
        if rows.empty:
            fig, ax = plt.subplots(figsize=(8, 3))
            ax.axis("off")
            ax.text(0.5, 0.5, "No channels fulfilled both criteria.", ha="center", va="center")
            pdf.savefig(fig)
            plt.close(fig)
            return
        for _, row in rows.iterrows():
            cid = row["channel_observation_id"]
            target = row["target"]
            group = store[f"channels/{cid}"]
            if target == "train_250ms":
                time_ms = train_time
                counts = group["train_full_50/counts"][:]
                smoothed = group["train_full_50/smoothed_rate_hz"][:]
                pulse_starts = [0, 50, 100, 150, 200]
            else:
                pulse_index = int(target.rsplit("_", 1)[1]) - 1
                time_ms = pulse_time
                counts = group["pulse_250/counts"][:].reshape(50, 5, -1)[:, pulse_index, :]
                smoothed = group["pulse_250/smoothed_rate_hz"][:].reshape(50, 5, -1)[
                    :, pulse_index, :
                ]
                pulse_starts = [0] + ([-50] if pulse_index > 0 else [])
            mean_excess = smoothed.mean(axis=0) - row["subtraction_baseline_rate_hz"]
            spike_rows, spike_bins = np.nonzero(counts)
            multiplicities = counts[spike_rows, spike_bins].astype(int)
            fig, (raster_ax, psth_ax) = plt.subplots(
                2,
                1,
                figsize=(10, 6),
                sharex=True,
                gridspec_kw={"height_ratios": [2.2, 1], "hspace": 0.08},
            )
            raster_ax.scatter(
                np.repeat(time_ms[spike_bins], multiplicities),
                np.repeat(spike_rows + 1, multiplicities),
                s=5,
                color="black",
                linewidths=0,
            )
            raster_ax.set_ylim(50.8, 0.2)
            raster_ax.set_ylabel("Trial")
            raster_ax.set_title(
                f"{cid} | {row['well']} {row['condition']} | channel {row['best_channel_id']} | "
                f"{int(row['units_pooled'])} units pooled | {target} | "
                f"max coincidence={int(row['maximum_trials_above_baseline_same_bin'])}/50"
            )
            psth_ax.plot(
                time_ms,
                mean_excess,
                drawstyle="steps-mid",
                color=COLORS[row["condition"]],
                linewidth=1.5,
                label="Pooled baseline-subtracted PSTH; one [1,1,1]/3 boxcar",
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


def _method_specification(
    channel_metadata: pd.DataFrame,
    metrics: pd.DataFrame,
    early_only_details: pd.DataFrame,
) -> str:
    responsive = metrics.loc[metrics["responsive_candidate"]]
    early_only_counts = early_only_details["condition"].value_counts()
    return f"""# Channel-pooled independent baseline-subtracted response analysis

This development directory is fully overwritten on every successful run.

## Aggregation and N

- Source: the existing unified per-unit HDF5 matrices; stimulus access, alignment, trials, bins, and raw variants are unchanged.
- A channel observation is unique within analyzer/recording/raw variant. Channels are never pooled across recordings or wells.
- Every good or MUA unit is assigned to its template `best_channel_index` and physical analyzer `channel_id`.
- Count matrices from all units assigned to a channel are summed. This is equivalent to concatenating those units' spike trains before histogramming.
- The channel PSTH is calculated from pooled counts and receives exactly one normalized `[1, 1, 1] / 3` boxcar. Rasters remain unsmoothed.
- Channel observations: {len(channel_metadata)} from {int(channel_metadata['units_pooled'].sum())} source unit observations.

## Response criterion

- All 50 trials are retained.
- Spontaneous rate: −500–0 ms before pulse 1.
- Shared subtraction baseline: −200–0 ms before pulse 1.
- No SD cutoff is used; the response threshold is zero after subtraction of the shared pre-train baseline rate.
- A channel-target pair is included only when both criteria are met: (1) its trial-averaged baseline-subtracted PSTH rises above zero anywhere in the response window and (2) at least {MINIMUM_SAME_BIN_TRIALS}/50 trials exceed baseline in the same 1-ms bin.
- The original mean-PSTH-only flag, the same-bin count, and the final combined decision are all retained in `per_channel_threshold_response_metrics.csv`.
- No FDR or decision rule across channels, recordings, wells, or organoids is used.
- Pulses 1–5 use separate 0–50 ms response windows; the full train uses 0–250 ms.
- The same −200–0 ms window before pulse 1 is used for all five pulse positions. Pulses 2–5 are never re-baselined using earlier stimulated intervals.
- Per-channel pulse profiles classify `early_only_p1_p2`, sustained, late-only, or no qualifying response and store continuous early-versus-late magnitudes, ratios, habituation indices, and slopes. Continuous early-greater-than-late rankings are descriptive and do not confer candidate status.

## Focused early-only comparison

- `early_only_p1_p2` means P1 or P2 meets the combined mean-PSTH plus ≥{MINIMUM_SAME_BIN_TRIALS}-trial rule and none of P3–P5 meets it.
- Candidates are ranked separately within opsin and no-opsin conditions by descending mean P1/P2 positive-going excess PSTH area (spikes/trial).
- `ranked_opsin_vs_no_opsin_early_only_psth.pdf` places equal within-condition ranks side by side. Each channel includes P1–P5 plus the continuous −200–250 ms full-train view; the full-train candidate window is 0–250 ms. Each rank pair uses a common y-axis, and every panel is drawn from the same stored smoothed PSTHs used for classification.
- `early_only_channel_five_pulse_heatmaps.png` shows the same within-condition ranks side by side for response magnitude and descriptive trial coincidence.
- Early-only channels: {int(early_only_counts.get('opsin', 0))} opsin and {int(early_only_counts.get('no_opsin', 0))} no opsin.

Responsive target rows: {len(responsive)} across {responsive['channel_observation_id'].nunique()} channel observations.
"""


if __name__ == "__main__":
    raise SystemExit(main())
