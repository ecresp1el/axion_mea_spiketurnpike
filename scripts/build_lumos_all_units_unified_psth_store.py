#!/usr/bin/env python
"""Build an overwrite-in-place unified per-unit Lumos PSTH matrix store."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import warnings
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.launch_step1_sorting_analyzer_browser import DEFAULT_STIM_RAW_ROOTS  # noqa: E402
from scripts.plot_lumos_opsin_pre_post_unit_firing_rates import (  # noqa: E402
    DEFAULT_JOB_DIR,
    DEFAULT_UNIT_METRICS,
    VARIANT_MARKERS,
    _load_condition_map,
    _match_unit_id,
    _unit_label,
)
from axion_mea.gui_stim_response import resolve_stim_sidecars  # noqa: E402


OUTPUT_NAME = "lumos_all_units_per_unit_psth_development"
STORE_NAME = "lumos_all_units_per_unit_psth_development.h5"
PULSE_START_MS = -50.0
PULSE_END_MS = 50.0
TRAIN_START_MS = -500.0
TRAIN_END_MS = 250.0
BIN_MS = 1.0
BOXCAR = np.asarray([1.0, 1.0, 1.0], dtype=np.float32) / 3.0
PULSE_ONSETS_WITHIN_TRAIN_MS = np.asarray([0.0, 50.0, 100.0, 150.0, 200.0])
PULSE_OFFSETS_WITHIN_TRAIN_MS = np.asarray([9.5, 59.5, 109.5, 159.5, 209.5])
PRIMARY_WINDOW = "0_15ms_provisional"
WINDOWS = (
    ("0_5ms", 5.0),
    ("0_9p5ms", 9.5),
    (PRIMARY_WINDOW, 15.0),
    ("0_25ms", 25.0),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-metrics-csv", type=Path, default=DEFAULT_UNIT_METRICS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_JOB_DIR / OUTPUT_NAME)
    parser.add_argument("--expected-trains", type=int, default=50)
    parser.add_argument("--expected-pulses-per-train", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import spikeinterface.full as si

    output_dir = args.output_dir.expanduser().resolve()
    staging_dir = output_dir.parent / f".{output_dir.name}.staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)
    store_path = staging_dir / STORE_NAME

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

    pulse_edges = np.arange(PULSE_START_MS, PULSE_END_MS + BIN_MS, BIN_MS)
    pulse_centers = (pulse_edges[:-1] + pulse_edges[1:]) / 2.0
    train_edges = np.arange(TRAIN_START_MS, TRAIN_END_MS + BIN_MS, BIN_MS)
    train_centers = (train_edges[:-1] + train_edges[1:]) / 2.0
    metadata_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    inventory_rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []

    with h5py.File(store_path, "w") as store:
        _initialize_store(store, pulse_edges, pulse_centers, train_edges, train_centers)
        units_group = store.create_group("units")
        analyzer_groups = list(source.groupby("analyzer_path", sort=True))
        unit_counter = 0
        for progress, (analyzer_path_text, group) in enumerate(analyzer_groups, start=1):
            analyzer_path = Path(str(analyzer_path_text))
            recording = str(group.iloc[0]["recording"])
            well = str(group.iloc[0]["well"])
            raw_variant = str(group.iloc[0]["raw_variant"])
            try:
                analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=False)
                sorting = analyzer.sorting
                recording_channel_ids = list(analyzer.recording.get_channel_ids())
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
                events = list(resolution.stim_events.itertuples(index=False))
                pulse_epochs = list(resolution.pulse_structure.pulse_epochs)
                if len(events) != args.expected_trains:
                    raise ValueError(f"expected 50 trains, found {len(events)}")
                if len(pulse_epochs) != args.expected_pulses_per_train:
                    raise ValueError(f"expected 5 pulses/train, found {len(pulse_epochs)}")
                relative_pulse_starts = np.asarray(
                    [pulse.start_ms - pulse_epochs[0].start_ms for pulse in pulse_epochs]
                )
                relative_pulse_ends = np.asarray(
                    [pulse.end_ms - pulse_epochs[0].start_ms for pulse in pulse_epochs]
                )
                if not np.allclose(relative_pulse_starts, PULSE_ONSETS_WITHIN_TRAIN_MS):
                    raise ValueError(f"unexpected pulse starts: {relative_pulse_starts.tolist()}")
                if not np.allclose(relative_pulse_ends, PULSE_OFFSETS_WITHIN_TRAIN_MS):
                    raise ValueError(f"unexpected pulse ends: {relative_pulse_ends.tolist()}")
                train_first_pulse_onsets = np.asarray(
                    [float(event.event_time_s) + pulse_epochs[0].start_ms / 1000.0 for event in events]
                )
                pulse_onsets = np.asarray(
                    [
                        float(event.event_time_s) + pulse.start_ms / 1000.0
                        for event in events
                        for pulse in pulse_epochs
                    ]
                )
                pulse_train_index = np.repeat(np.arange(1, len(events) + 1), len(pulse_epochs))
                pulse_in_train = np.tile(np.arange(1, len(pulse_epochs) + 1), len(events))

                for _, unit_row in group.iterrows():
                    unit_counter += 1
                    observation_id = f"U{unit_counter:04d}"
                    unit_id = _match_unit_id(unit_ids, unit_row["unit_id"])
                    unit_label = _unit_label(unit_id)
                    best_channel_index = int(unit_row["best_channel_index"])
                    if not 0 <= best_channel_index < len(recording_channel_ids):
                        raise ValueError(
                            f"best channel index {best_channel_index} outside "
                            f"0..{len(recording_channel_ids) - 1}"
                        )
                    best_channel_id = str(recording_channel_ids[best_channel_index])
                    spike_times = np.sort(
                        np.asarray(sorting.get_unit_spike_train(unit_id=unit_id), dtype=float)
                        / sampling_frequency
                    )
                    pulse_counts = _trial_histograms(spike_times, pulse_onsets, pulse_edges)
                    grouped_counts = pulse_counts.reshape(
                        len(events), len(pulse_epochs), len(pulse_centers)
                    ).sum(axis=1)
                    train_counts = _trial_histograms(
                        spike_times, train_first_pulse_onsets, train_edges
                    )
                    pulse_rate = pulse_counts.astype(np.float32) * 1000.0 / BIN_MS
                    grouped_rate = (
                        grouped_counts.astype(np.float32)
                        * 1000.0
                        / (BIN_MS * len(pulse_epochs))
                    )
                    train_rate = train_counts.astype(np.float32) * 1000.0 / BIN_MS

                    metadata = {
                        "unit_observation_id": observation_id,
                        "unit_key": f"{recording}|{well}|{unit_label}",
                        "recording": recording,
                        "well": well,
                        "organoid_id": well,
                        "condition": condition_map[well],
                        "raw_variant": raw_variant,
                        "unit_id": unit_label,
                        "KSLabel": str(unit_row["KSLabel"]),
                        "best_channel_index": best_channel_index,
                        "best_channel_id": best_channel_id,
                        "aligned_ttp_ms": unit_row.get("trough_to_peak_duration_ms", np.nan),
                        "template_ptp_uV": unit_row.get("template_ptp_best_channel_uV", np.nan),
                        "waveform_class": unit_row.get("rs_fs_classification", ""),
                        "analyzer_path": str(analyzer_path),
                        "hdf5_group": f"/units/{observation_id}",
                    }
                    metadata_rows.append(metadata)
                    unit_group = units_group.create_group(observation_id)
                    for key, value in metadata.items():
                        unit_group.attrs[key] = _hdf_attr(value)
                    _write_matrix_group(
                        unit_group.create_group("pulse_250"),
                        pulse_counts,
                        pulse_rate,
                        alignment_onset_s=pulse_onsets,
                        pulse_train_index=pulse_train_index,
                        pulse_in_train=pulse_in_train,
                        axis_path="/axes/pulse_bin_centers_ms",
                    )
                    _write_matrix_group(
                        unit_group.create_group("train_grouped_50x5"),
                        grouped_counts,
                        grouped_rate,
                        alignment_onset_s=train_first_pulse_onsets,
                        pulse_train_index=np.arange(1, len(events) + 1),
                        pulse_in_train=None,
                        axis_path="/axes/pulse_bin_centers_ms",
                    )
                    _write_matrix_group(
                        unit_group.create_group("train_full_50"),
                        train_counts,
                        train_rate,
                        alignment_onset_s=train_first_pulse_onsets,
                        pulse_train_index=np.arange(1, len(events) + 1),
                        pulse_in_train=None,
                        axis_path="/axes/train_bin_centers_ms",
                    )
                    for method, rate_matrix in [
                        ("pulse_250", pulse_rate),
                        ("train_grouped_50x5", grouped_rate),
                    ]:
                        for trial_inclusion in ["all_rows", "active_rows_only"]:
                            for window_name, response_end_ms in WINDOWS:
                                metric_rows.append(
                                    _response_metrics(
                                        metadata,
                                        method,
                                        rate_matrix,
                                        pulse_centers,
                                        trial_inclusion,
                                        window_name,
                                        response_end_ms,
                                    )
                                )
                    inventory_rows.append(
                        {
                            "unit_observation_id": observation_id,
                            "pulse_250_shape": str(tuple(pulse_counts.shape)),
                            "train_grouped_50x5_shape": str(tuple(grouped_counts.shape)),
                            "train_full_50_shape": str(tuple(train_counts.shape)),
                            "pulse_count_total": int(pulse_counts.sum()),
                            "train_full_count_total": int(train_counts.sum()),
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

        metadata = pd.DataFrame(metadata_rows)
        metrics = pd.DataFrame(metric_rows)
        metrics["fdr_q_within_organoid_method_window"] = metrics.groupby(
            ["well", "method", "trial_inclusion", "window"], sort=False
        )["paired_wilcoxon_p"].transform(_benjamini_hochberg)
        metrics["provisional_enhanced_responsive"] = (
            metrics["window"].eq(PRIMARY_WINDOW)
            & metrics["mean_delta_hz"].gt(0)
            & metrics["fdr_q_within_organoid_method_window"].lt(0.05)
        )
        metrics["provisional_suppressed_responsive"] = (
            metrics["window"].eq(PRIMARY_WINDOW)
            & metrics["mean_delta_hz"].lt(0)
            & metrics["fdr_q_within_organoid_method_window"].lt(0.05)
        )
        _write_metadata_table(store.create_group("metadata"), metadata)
        _write_response_table(store.create_group("response_metrics"), metrics)

    metadata.to_csv(staging_dir / "unit_metadata.csv", index=False)
    metrics.to_csv(staging_dir / "response_metrics_long.csv", index=False)
    pd.DataFrame(inventory_rows).to_csv(staging_dir / "matrix_inventory.csv", index=False)
    pd.DataFrame(
        errors, columns=["recording", "well", "analyzer_path", "error"]
    ).to_csv(staging_dir / "errors.csv", index=False)
    (staging_dir / "METHOD_SPECIFICATION.md").write_text(
        _method_specification(metadata, metrics), encoding="utf-8"
    )
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "development_output": True,
        "overwrite_policy": "entire output directory replaced after every successful run",
        "script": str(Path(__file__).resolve()),
        "hdf5_store": STORE_NAME,
        "unit_observations": len(metadata),
        "errors": len(errors),
        "boxcar_weights": BOXCAR.tolist(),
        "primary_responsiveness_window": PRIMARY_WINDOW,
    }
    (staging_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    if errors:
        raise RuntimeError(f"Refusing to replace development output: {len(errors)} errors")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging_dir.replace(output_dir)
    print(f"\nUnified store: {output_dir / STORE_NAME}")
    print(f"Unit observations: {len(metadata)}")
    print(f"Response rows: {len(metrics)}")
    print("Development output was replaced successfully.")
    return 0


def _initialize_store(store, pulse_edges, pulse_centers, train_edges, train_centers) -> None:
    store.attrs["format_version"] = "development_v1"
    store.attrs["bin_ms"] = BIN_MS
    store.attrs["boxcar_weights"] = BOXCAR
    store.attrs["boxcar_definition"] = "normalized [1,1,1] moving average; same; zero padded"
    store.attrs["pulse_alignment"] = "relative to each pulse onset"
    store.attrs["train_alignment"] = "relative to first pulse onset in each five-pulse train"
    axes = store.create_group("axes")
    axes.create_dataset("pulse_bin_edges_ms", data=pulse_edges)
    axes.create_dataset("pulse_bin_centers_ms", data=pulse_centers)
    axes.create_dataset("train_bin_edges_ms", data=train_edges)
    axes.create_dataset("train_bin_centers_ms", data=train_centers)
    axes.create_dataset("pulse_onsets_within_train_ms", data=PULSE_ONSETS_WITHIN_TRAIN_MS)
    axes.create_dataset("pulse_offsets_within_train_ms", data=PULSE_OFFSETS_WITHIN_TRAIN_MS)


def _trial_histograms(spike_times, onsets, edges_ms) -> np.ndarray:
    matrix = np.zeros((len(onsets), len(edges_ms) - 1), dtype=np.uint16)
    for row, onset in enumerate(onsets):
        left = np.searchsorted(spike_times, onset + edges_ms[0] / 1000.0, side="left")
        right = np.searchsorted(spike_times, onset + edges_ms[-1] / 1000.0, side="left")
        relative_ms = (spike_times[left:right] - onset) * 1000.0
        matrix[row] = np.histogram(relative_ms, bins=edges_ms)[0]
    return matrix


def _smooth_rows(rate_matrix: np.ndarray) -> np.ndarray:
    return np.asarray(
        [np.convolve(row, BOXCAR, mode="same") for row in rate_matrix],
        dtype=np.float32,
    )


def _write_matrix_group(
    group,
    counts,
    rate,
    *,
    alignment_onset_s,
    pulse_train_index,
    pulse_in_train,
    axis_path,
) -> None:
    options = {"compression": "gzip", "compression_opts": 4, "shuffle": True}
    group.create_dataset("counts", data=counts, **options)
    group.create_dataset("rate_hz", data=rate, **options)
    group.create_dataset("smoothed_rate_hz", data=_smooth_rows(rate), **options)
    group.create_dataset("row_has_any_spike", data=counts.sum(axis=1) > 0)
    group.create_dataset("alignment_onset_s", data=alignment_onset_s)
    group.create_dataset("trial_or_train_index", data=pulse_train_index)
    if pulse_in_train is not None:
        group.create_dataset("pulse_in_train", data=pulse_in_train)
    group.attrs["rows"] = counts.shape[0]
    group.attrs["columns_1ms_bins"] = counts.shape[1]
    group.attrs["boxcar_weights"] = BOXCAR
    group.attrs["time_axis"] = axis_path


def _response_metrics(
    metadata,
    method,
    rate_matrix,
    bin_centers,
    trial_inclusion,
    window_name,
    response_end_ms,
) -> dict[str, object]:
    total_rows = len(rate_matrix)
    active_row_mask = rate_matrix.sum(axis=1) > 0
    if trial_inclusion == "active_rows_only":
        rate_matrix = rate_matrix[active_row_mask]
    elif trial_inclusion != "all_rows":
        raise ValueError(f"Unsupported trial inclusion: {trial_inclusion}")
    pre_mask = (bin_centers >= -response_end_ms) & (bin_centers < 0.0)
    post_mask = (bin_centers >= 0.0) & (bin_centers < response_end_ms)
    pre = rate_matrix[:, pre_mask].mean(axis=1)
    post = rate_matrix[:, post_mask].mean(axis=1)
    differences = post - pre
    p_value = _paired_wilcoxon_p(pre, post)
    hit_rows = np.flatnonzero(rate_matrix[:, post_mask].sum(axis=1) > 0)
    first_latencies = []
    post_centers = bin_centers[post_mask]
    for row in hit_rows:
        active_bins = np.flatnonzero(rate_matrix[row, post_mask] > 0)
        if len(active_bins):
            first_latencies.append(float(post_centers[active_bins[0]]))
    return {
        **{key: metadata[key] for key in [
            "unit_observation_id", "unit_key", "recording", "well", "condition",
            "raw_variant", "unit_id", "KSLabel"
        ]},
        "method": method,
        "trial_inclusion": trial_inclusion,
        "window": window_name,
        "baseline_start_ms": -response_end_ms,
        "baseline_end_ms": 0.0,
        "response_start_ms": 0.0,
        "response_end_ms": response_end_ms,
        "trial_rows_total": total_rows,
        "trial_rows_analyzed": len(rate_matrix),
        "excluded_zero_spike_rows": int(total_rows - len(rate_matrix)),
        "mean_pre_rate_hz": float(pre.mean()) if len(pre) else np.nan,
        "mean_post_rate_hz": float(post.mean()) if len(post) else np.nan,
        "mean_delta_hz": float(differences.mean()) if len(differences) else np.nan,
        "median_delta_hz": float(np.median(differences)) if len(differences) else np.nan,
        "response_hit_fraction": (
            float(len(hit_rows) / len(rate_matrix)) if len(rate_matrix) else np.nan
        ),
        "median_first_active_bin_latency_ms": (
            float(np.median(first_latencies)) if first_latencies else np.nan
        ),
        "paired_wilcoxon_p": p_value,
    }


def _paired_wilcoxon_p(pre, post) -> float:
    if not len(pre):
        return 1.0
    if not np.any(np.asarray(post) - np.asarray(pre)):
        return 1.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = wilcoxon(post, pre, zero_method="pratt", method="approx")
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


def _write_metadata_table(group, table: pd.DataFrame) -> None:
    strings = h5py.string_dtype(encoding="utf-8")
    for column in table.columns:
        values = table[column]
        if pd.api.types.is_numeric_dtype(values):
            group.create_dataset(column, data=values.to_numpy())
        else:
            group.create_dataset(column, data=values.fillna("").astype(str).to_numpy(dtype=strings))


def _write_response_table(group, table: pd.DataFrame) -> None:
    _write_metadata_table(group, table)


def _hdf_attr(value):
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return np.nan
    return value


def _method_specification(metadata: pd.DataFrame, metrics: pd.DataFrame) -> str:
    enhanced = int(metrics["provisional_enhanced_responsive"].sum())
    suppressed = int(metrics["provisional_suppressed_responsive"].sum())
    return f"""# Lumos per-unit PSTH development specification

This directory is **development output**. A successful rerun replaces the entire directory.

## Population and replication

- Units: all `KSLabel=good` and `KSLabel=mua` observations ({len(metadata)} total).
- Non-LFP representations: `primary_raw` and `filter_200Hz-3kHz`.
- No recording-name deduplication is performed.
- Organoid identity is the well.
- Recording identity is preserved exactly as stored in the source table.

## Matrices stored for every unit

- `pulse_250`: 250 rows × 100 one-ms bins, aligned −50 to +50 ms around each pulse. Rows are explicitly labeled pulse 1–5 within train.
- `train_grouped_50x5`: 50 rows × 100 one-ms bins. Each row sums the five pulse-aligned rows in its train; rate is normalized by five pulses.
- `train_full_50`: 50 rows × 750 one-ms bins, aligned −500 to +250 ms around the first pulse, showing pulses at 0, 50, 100, 150, and 200 ms. The longer pre-train coverage supports criteria that quantify spontaneous firing over 500 ms without changing the underlying data pathway.
- The corresponding pulse offsets are 9.5, 59.5, 109.5, 159.5, and 209.5 ms; each light pulse lasts 9.5 ms.
- Each group contains `counts`, `rate_hz`, and `smoothed_rate_hz`.
- Smoothing is a normalized `[1, 1, 1] / 3` moving average along time within each row, using `same` convolution and zero padding.
- Every row is retained. `row_has_any_spike` identifies rows with at least one spike anywhere in that stored window, allowing a silent-row sensitivity analysis without deleting data.
- `alignment_onset_s`, train/pulse indices, and the applicable time-axis path are stored with each matrix.

## Provisional responsiveness definition

This definition is deliberately marked provisional until approved:

1. Primary baseline: −15 to 0 ms relative to each pulse.
2. Primary response: 0 to 15 ms relative to each pulse.
3. `pulse_250`: paired Wilcoxon across 250 pulse rows.
4. `train_grouped_50x5`: paired Wilcoxon across 50 rows after summing the five pulses in each train.
5. Both `all_rows` and `active_rows_only` are calculated. An active row has at least one spike anywhere in that row's stored −50 to +50 ms PSTH. The original matrices are never pruned.
6. Benjamini–Hochberg FDR is applied within organoid × method × trial-inclusion rule × window.
7. Enhanced responsive: positive mean response-minus-baseline and `q < 0.05`.
8. Suppressed responsive: negative mean response-minus-baseline and `q < 0.05`.
9. Statistics use the unsmoothed per-row rate matrix. The smoothed matrix is stored for PSTH display; using it for pre/post inference would leak activity across the 0-ms boundary.

Provisional enhanced flags: {enhanced}. Provisional suppressed flags: {suppressed}.

Secondary matched windows (5, 9.5, and 25 ms) are stored in `response_metrics_long.csv` but do not define the provisional primary flag.

## HDF5 layout

- `/axes`: bin edges, centers, and pulse times.
- `/metadata`: one aligned vector per unit metadata field.
- `/response_metrics`: long-form metric table stored column-wise.
- `/units/U####/pulse_250`: per-unit 250-trial matrices.
- `/units/U####/train_grouped_50x5`: per-unit 50-row pooled-pulse matrices.
- `/units/U####/train_full_50`: per-unit full-train matrices.
"""


if __name__ == "__main__":
    raise SystemExit(main())
