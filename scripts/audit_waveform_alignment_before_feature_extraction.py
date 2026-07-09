#!/usr/bin/env python
"""Audit whether waveform alignment should precede feature extraction.

For each unit, this script uses the same persisted random-spike snippets twice:

1. Average snippets without extra per-snippet alignment.
2. Align each snippet to its local trough on the selected channel, then average.

The same SpikeTurnpike landmark/feature measurement code is then applied to
both averages. This directly tests whether pre-feature alignment changes TTP,
half-width, REP, slopes, and amplitudes for the exact same unit/snippet
population.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.plot_lumos_candidate_waveform_gallery import (  # noqa: E402
    _measure_spiketurnpike_waveform_metrics,
)


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_DATE_LABEL = "20260709"
DEFAULT_INPUT_NAME = "good_kslabel_ttp_distribution_template_best_ptp_{date_label}.csv"
CLASS_ORDER = ["FS_like", "borderline", "RS_like", "unknown"]
CLASS_COLORS = {
    "FS_like": "#d55e00",
    "borderline": "#7a7a7a",
    "RS_like": "#0072b2",
    "unknown": "#b0b0b0",
}
METRIC_COLUMNS = [
    "trough_to_peak_duration_ms",
    "spike_half_width_ms",
    "repolarization_time_ms",
    "template_ptp_best_channel_uV",
    "spiketurnpike_amplitude_uV",
    "pre_peak_amplitude_uV",
    "post_peak_amplitude_uV",
    "depolarization_slope_uV_per_ms",
    "post_trough_rebound_slope_uV_per_ms",
    "rep50_recovery_slope_uV_per_ms",
    "waveform_asymmetry",
    "peak_to_peak_ratio",
]
LANDMARK_COLUMNS = [
    "pre_peak_time_ms",
    "trough_time_ms",
    "rebound_peak_time_ms",
    "half_width_start_time_ms",
    "half_width_end_time_ms",
    "rep_recovery_time_ms",
]


@dataclass(frozen=True)
class AlignmentAuditConfig:
    """Snippet extraction and trough-alignment settings."""

    max_spikes_per_unit: int = 500
    alignment_search_radius_samples: int = 5
    min_spikes_per_unit: int = 10
    rep_fraction: float = 0.5
    random_seed: int = 20260709


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--input-csv", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--kslabel", default="good", help="Filter KSLabel; use 'all' to keep all labels.")
    parser.add_argument("--max-units", type=int, default=None)
    parser.add_argument("--max-spikes-per-unit", type=int, default=500)
    parser.add_argument("--min-spikes-per-unit", type=int, default=10)
    parser.add_argument("--alignment-search-radius-samples", type=int, default=5)
    parser.add_argument("--rep-fraction", type=float, choices=(0.25, 0.5, 0.63), default=0.5)
    parser.add_argument("--random-seed", type=int, default=20260709)
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import spikeinterface.full as si

    job_dir = args.job_dir.expanduser().resolve()
    input_csv = args.input_csv or job_dir / DEFAULT_INPUT_NAME.format(date_label=args.date_label)
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else job_dir / f"waveform_alignment_feature_audit_{args.date_label}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    config = AlignmentAuditConfig(
        max_spikes_per_unit=args.max_spikes_per_unit,
        alignment_search_radius_samples=args.alignment_search_radius_samples,
        min_spikes_per_unit=args.min_spikes_per_unit,
        rep_fraction=args.rep_fraction,
        random_seed=args.random_seed,
    )

    source = pd.read_csv(input_csv)
    if args.kslabel.lower() != "all" and "KSLabel" in source.columns:
        source = source.loc[source["KSLabel"].astype(str).str.lower().eq(args.kslabel.lower())].copy()
    if args.max_units is not None:
        source = source.head(args.max_units).copy()
    if source.empty:
        raise SystemExit("No input unit rows remain after filtering.")

    paired, trace_rows, errors = _extract_alignment_comparison(si, source, config=config)
    if paired.empty:
        raise SystemExit("No paired before/after waveform rows could be computed.")

    summary = _metric_delta_summary(paired)
    class_counts = _class_count_summary(paired)
    landmark_summary = _landmark_delta_summary(paired)
    decision = _alignment_decision(summary, paired)

    stem = f"waveform_alignment_feature_audit_{args.date_label}"
    paired_csv = output_dir / f"{stem}_paired_unit_metrics.csv"
    summary_csv = output_dir / f"{stem}_metric_delta_summary.csv"
    class_counts_csv = output_dir / f"{stem}_class_counts.csv"
    landmark_summary_csv = output_dir / f"{stem}_landmark_delta_summary.csv"
    traces_csv = output_dir / f"{stem}_waveform_traces.csv.gz"
    delta_figure = output_dir / f"{stem}_metric_deltas.png"
    scatter_figure = output_dir / f"{stem}_before_after_scatter.png"
    waveform_figure = output_dir / f"{stem}_largest_change_waveforms.png"
    class_figure = output_dir / f"{stem}_class_counts_same_cutoffs.png"
    provenance_json = output_dir / f"{stem}_provenance.json"
    error_path = output_dir / f"{stem}_errors.txt"

    paired.to_csv(paired_csv, index=False)
    summary.to_csv(summary_csv, index=False)
    class_counts.to_csv(class_counts_csv, index=False)
    landmark_summary.to_csv(landmark_summary_csv, index=False)
    trace_rows.to_csv(traces_csv, index=False)
    _plot_metric_deltas(plt, paired, delta_figure)
    _plot_before_after_scatter(plt, paired, scatter_figure)
    _plot_largest_change_waveforms(plt, paired, trace_rows, waveform_figure)
    _plot_class_counts(plt, class_counts, class_figure)
    if errors:
        error_path.write_text("\n".join(errors) + "\n", encoding="utf-8")

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "input_csv": str(input_csv),
        "output_dir": str(output_dir),
        "unit_rows_input_after_filter": int(len(source)),
        "paired_unit_count": int(len(paired)),
        "config": asdict(config),
        "decision": decision,
        "outputs": {
            "paired_unit_metrics_csv": str(paired_csv),
            "metric_delta_summary_csv": str(summary_csv),
            "class_counts_csv": str(class_counts_csv),
            "landmark_delta_summary_csv": str(landmark_summary_csv),
            "waveform_traces_csv": str(traces_csv),
            "metric_delta_figure": str(delta_figure),
            "before_after_scatter_figure": str(scatter_figure),
            "largest_change_waveform_figure": str(waveform_figure),
            "class_counts_figure": str(class_figure),
        },
        "notes": [
            "Same units and same sampled snippets are used for before and after alignment.",
            "Before waveform is the unaligned average of selected snippets.",
            "After waveform is the average after shifting each snippet so its local trough aligns to the template trough sample.",
            "Best channel is fixed from the persisted templates.average PTP channel for both measurements.",
            "The same SpikeTurnpike landmark and cutoff logic is used for both measurements.",
        ],
        "errors": errors,
    }
    provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Input: {input_csv}")
    print(f"Output dir: {output_dir}")
    print(f"Units input after filter: {len(source)}")
    print(f"Paired units analyzed: {len(paired)}")
    print(f"Paired metrics: {paired_csv}")
    print(f"Metric delta summary: {summary_csv}")
    print(f"Landmark delta summary: {landmark_summary_csv}")
    print(f"Class counts: {class_counts_csv}")
    print(f"Figures: {delta_figure}, {scatter_figure}, {waveform_figure}, {class_figure}")
    print(f"Provenance: {provenance_json}")
    if errors:
        print(f"Skipped {len(errors)} unit/analyzer entries; details: {error_path}")
    print("\nDecision:")
    print(json.dumps(decision, indent=2))
    print("\nMetric delta summary:")
    print(summary.to_string(index=False))
    print("\nClass counts with same cutoffs:")
    print(class_counts.to_string(index=False))


def _extract_alignment_comparison(si, source: pd.DataFrame, *, config: AlignmentAuditConfig) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    rows: list[dict[str, Any]] = []
    traces: list[pd.DataFrame] = []
    errors: list[str] = []
    rng = np.random.default_rng(config.random_seed)
    required = {"analyzer_path", "unit_index"}
    missing = required.difference(source.columns)
    if missing:
        raise ValueError(f"Input table missing required columns: {sorted(missing)}")

    for analyzer_path_text, group in source.groupby("analyzer_path", dropna=False, sort=False):
        analyzer_path = Path(str(analyzer_path_text))
        try:
            analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
            sorting = analyzer.sorting
            recording = analyzer.recording
            templates_ext = analyzer.get_extension("templates")
            random_ext = analyzer.get_extension("random_spikes")
            if templates_ext is None:
                raise ValueError("missing templates extension")
            if random_ext is None:
                raise ValueError("missing random_spikes extension")
            templates = _templates_average(templates_ext)
            unit_ids = list(sorting.get_unit_ids())
            sampling_frequency = float(recording.get_sampling_frequency())
            nbefore = int(getattr(templates_ext, "nbefore", np.nan))
            nafter = int(getattr(templates_ext, "nafter", np.nan))
            if not np.isfinite(nbefore) or not np.isfinite(nafter):
                nbefore = int(templates.shape[1] // 2)
                nafter = int(templates.shape[1] - nbefore)
            channel_ids = list(recording.get_channel_ids())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{analyzer_path}: {type(exc).__name__}: {exc}")
            continue

        for _, source_row in group.iterrows():
            try:
                unit_index = int(source_row["unit_index"])
                if unit_index < 0 or unit_index >= len(unit_ids):
                    raise ValueError(f"unit_index={unit_index} outside analyzer unit count {len(unit_ids)}")
                unit_id = unit_ids[unit_index]
                template = np.asarray(templates[unit_index], dtype=float)
                if template.ndim != 2 or not np.isfinite(template).any():
                    raise ValueError("empty/nonfinite template")
                if "best_channel_index" in source_row and pd.notna(source_row["best_channel_index"]):
                    best_channel_index = int(source_row["best_channel_index"])
                else:
                    best_channel_index = int(np.nanargmax(np.ptp(template, axis=0)))
                channel_id = channel_ids[best_channel_index]
                snippets, selected_count, available_count = _extract_unit_snippets(
                    recording,
                    sorting,
                    random_ext,
                    unit_id,
                    channel_id,
                    nbefore=nbefore,
                    nafter=nafter,
                    max_spikes=config.max_spikes_per_unit,
                    rng=rng,
                )
                if snippets.shape[0] < config.min_spikes_per_unit:
                    raise ValueError(
                        f"only {snippets.shape[0]} usable snippets; min_spikes_per_unit={config.min_spikes_per_unit}"
                    )
                before_waveform = np.nanmean(snippets, axis=0)
                aligned_snippets, shifts = _align_snippets_to_local_trough(
                    snippets,
                    target_index=nbefore,
                    search_radius=config.alignment_search_radius_samples,
                )
                after_waveform = np.nanmean(aligned_snippets, axis=0)
                time_ms = (np.arange(before_waveform.size) - nbefore) / sampling_frequency * 1000.0
                before_metrics = _feature_metrics(before_waveform, time_ms, config.rep_fraction)
                after_metrics = _feature_metrics(after_waveform, time_ms, config.rep_fraction)
                row = _paired_row(
                    source_row,
                    analyzer_path,
                    unit_id,
                    unit_index,
                    best_channel_index,
                    snippets.shape[0],
                    selected_count,
                    available_count,
                    shifts,
                    before_metrics,
                    after_metrics,
                )
                rows.append(row)
                traces.append(_trace_rows(row["unit_key"], source_row, time_ms, before_waveform, after_waveform))
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"{source_row.get('recording')} / {source_row.get('well')} "
                    f"unit={source_row.get('unit_id', source_row.get('unit_index'))}: "
                    f"{type(exc).__name__}: {exc}"
                )

    paired = pd.DataFrame(rows)
    trace_table = pd.concat(traces, ignore_index=True) if traces else pd.DataFrame()
    return paired, trace_table, errors


def _extract_unit_snippets(
    recording,
    sorting,
    random_ext,
    unit_id: Any,
    channel_id: Any,
    *,
    nbefore: int,
    nafter: int,
    max_spikes: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, int, int]:
    snippets: list[np.ndarray] = []
    selected_total = 0
    available_total = 0
    for segment_index in range(sorting.get_num_segments()):
        spike_train = np.asarray(sorting.get_unit_spike_train(unit_id=unit_id, segment_index=segment_index), dtype=np.int64)
        available_total += int(spike_train.size)
        if spike_train.size == 0:
            continue
        try:
            selected_indices = np.asarray(random_ext.get_selected_indices_in_spike_train(unit_id, segment_index), dtype=np.int64)
        except Exception:  # noqa: BLE001
            selected_indices = np.arange(spike_train.size, dtype=np.int64)
        selected_indices = selected_indices[(selected_indices >= 0) & (selected_indices < spike_train.size)]
        if selected_indices.size == 0:
            continue
        if selected_indices.size > max_spikes:
            selected_indices = np.sort(rng.choice(selected_indices, size=max_spikes, replace=False))
        selected_total += int(selected_indices.size)
        frames = spike_train[selected_indices]
        num_samples = int(recording.get_num_samples(segment_index=segment_index))
        for frame in frames:
            start = int(frame) - nbefore
            end = int(frame) + nafter
            if start < 0 or end > num_samples or end <= start:
                continue
            trace = recording.get_traces(
                segment_index=segment_index,
                start_frame=start,
                end_frame=end,
                channel_ids=[channel_id],
                return_in_uV=True,
            )
            trace = np.asarray(trace, dtype=float)
            if trace.ndim != 2 or trace.shape[0] != nbefore + nafter:
                continue
            snippets.append(trace[:, 0])
    if not snippets:
        return np.empty((0, nbefore + nafter), dtype=float), selected_total, available_total
    return np.stack(snippets, axis=0), selected_total, available_total


def _align_snippets_to_local_trough(snippets: np.ndarray, *, target_index: int, search_radius: int) -> tuple[np.ndarray, np.ndarray]:
    aligned = np.full_like(snippets, np.nan, dtype=float)
    shifts = np.full(snippets.shape[0], np.nan, dtype=float)
    sample_index = np.arange(snippets.shape[1], dtype=float)
    left = max(0, target_index - search_radius)
    right = min(snippets.shape[1], target_index + search_radius + 1)
    for row_index, snippet in enumerate(snippets):
        if not np.isfinite(snippet).any():
            continue
        local = snippet[left:right]
        if local.size == 0 or not np.isfinite(local).any():
            continue
        trough_index = left + int(np.nanargmin(local))
        shift = trough_index - target_index
        aligned[row_index] = np.interp(sample_index + shift, sample_index, snippet, left=np.nan, right=np.nan)
        shifts[row_index] = float(shift)
    return aligned, shifts


def _feature_metrics(waveform: np.ndarray, time_ms: np.ndarray, rep_fraction: float) -> dict[str, Any]:
    current = _measure_spiketurnpike_waveform_metrics(waveform, time_ms, rep_fraction=rep_fraction)
    trough_index = int(current["trough_index"])
    pre_peak_index = int(current["pre_peak_index"])
    rebound_peak_index = int(current["rebound_peak_index"])
    trough_value = _value_at(waveform, trough_index)
    pre_peak_value = _value_at(waveform, pre_peak_index)
    post_peak_value = _value_at(waveform, rebound_peak_index)
    pre_peak_amplitude = pre_peak_value - trough_value if np.isfinite(pre_peak_value) and np.isfinite(trough_value) else np.nan
    post_peak_amplitude = post_peak_value - trough_value if np.isfinite(post_peak_value) and np.isfinite(trough_value) else np.nan
    pre_to_trough_ms = float(current["trough_time_ms"] - current["pre_peak_time_ms"])
    trough_to_peak_ms = float(current["trough_to_peak_duration_ms"])
    rep_ms = float(current["repolarization_time_ms"])
    rep_threshold = float(current["rep_threshold_uV"])
    amplitude_sum = pre_peak_amplitude + post_peak_amplitude
    return {
        **{k: v for k, v in current.items() if k != "normalized_best_waveform"},
        "template_ptp_best_channel_uV": float(np.nanmax(waveform) - np.nanmin(waveform)),
        "template_trough_best_channel_uV": float(np.nanmin(waveform)),
        "template_peak_best_channel_uV": float(np.nanmax(waveform)),
        "pre_peak_amplitude_uV": pre_peak_amplitude,
        "post_peak_amplitude_uV": post_peak_amplitude,
        "waveform_asymmetry": (
            (post_peak_amplitude - pre_peak_amplitude) / amplitude_sum
            if np.isfinite(amplitude_sum) and amplitude_sum > 0
            else np.nan
        ),
        "depolarization_slope_uV_per_ms": (
            pre_peak_amplitude / pre_to_trough_ms if np.isfinite(pre_peak_amplitude) and pre_to_trough_ms > 0 else np.nan
        ),
        "post_trough_rebound_slope_uV_per_ms": (
            post_peak_amplitude / trough_to_peak_ms if np.isfinite(post_peak_amplitude) and trough_to_peak_ms > 0 else np.nan
        ),
        "rep50_recovery_slope_uV_per_ms": (
            (rep_threshold - trough_value) / rep_ms
            if np.isfinite(rep_threshold) and np.isfinite(trough_value) and rep_ms > 0
            else np.nan
        ),
    }


def _paired_row(
    source_row: pd.Series,
    analyzer_path: Path,
    unit_id: Any,
    unit_index: int,
    best_channel_index: int,
    usable_snippets: int,
    selected_spikes: int,
    available_spikes: int,
    shifts: np.ndarray,
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    unit_key = f"{source_row.get('recording')}|{source_row.get('well')}|{unit_id}"
    row: dict[str, Any] = {
        "unit_key": unit_key,
        "recording": source_row.get("recording"),
        "well": source_row.get("well"),
        "plate_family": source_row.get("plate_family", ""),
        "unit_id": unit_id,
        "unit_index": unit_index,
        "KSLabel": source_row.get("KSLabel", ""),
        "input_rs_fs_classification": source_row.get("rs_fs_classification", ""),
        "analyzer_path": str(analyzer_path),
        "best_channel_index": best_channel_index,
        "available_spikes": available_spikes,
        "selected_spikes": selected_spikes,
        "usable_snippets": usable_snippets,
        "alignment_shift_median_samples": _nanmedian(shifts),
        "alignment_shift_mad_samples": _nanmedian(np.abs(shifts - _nanmedian(shifts))),
        "alignment_shift_min_samples": _nanmin(shifts),
        "alignment_shift_max_samples": _nanmax(shifts),
    }
    for metric in METRIC_COLUMNS + LANDMARK_COLUMNS:
        row[f"before_{metric}"] = before.get(metric, np.nan)
        row[f"after_{metric}"] = after.get(metric, np.nan)
        row[f"delta_{metric}"] = _delta(after.get(metric, np.nan), before.get(metric, np.nan))
        row[f"abs_delta_{metric}"] = abs(row[f"delta_{metric}"]) if np.isfinite(row[f"delta_{metric}"]) else np.nan
    for name in [
        "pre_peak_index",
        "trough_index",
        "rebound_peak_index",
        "half_width_start_index",
        "half_width_end_index",
        "rep_recovery_index",
    ]:
        row[f"before_{name}"] = before.get(name, -1)
        row[f"after_{name}"] = after.get(name, -1)
        row[f"delta_{name}"] = _delta(after.get(name, np.nan), before.get(name, np.nan))
    row["before_rs_fs_classification"] = before.get("tentative_rs_fs_classification", "unknown")
    row["after_rs_fs_classification"] = after.get("tentative_rs_fs_classification", "unknown")
    row["rs_fs_classification_changed"] = row["before_rs_fs_classification"] != row["after_rs_fs_classification"]
    row["alignment_total_abs_metric_change_rank"] = _combined_change_score(row)
    return row


def _trace_rows(unit_key: str, source_row: pd.Series, time_ms: np.ndarray, before: np.ndarray, after: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "unit_key": unit_key,
            "recording": source_row.get("recording"),
            "well": source_row.get("well"),
            "unit_id": source_row.get("unit_id"),
            "time_ms": time_ms,
            "before_unaligned_average_uV": before,
            "after_aligned_average_uV": after,
        }
    )


def _metric_delta_summary(paired: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for metric in METRIC_COLUMNS:
        before = pd.to_numeric(paired[f"before_{metric}"], errors="coerce")
        after = pd.to_numeric(paired[f"after_{metric}"], errors="coerce")
        delta = after - before
        abs_delta = delta.abs()
        denom = before.abs().replace(0, np.nan)
        abs_pct = abs_delta / denom * 100.0
        rows.append(
            {
                "metric": metric,
                "valid_pairs": int((before.notna() & after.notna()).sum()),
                "before_median": _series_median(before),
                "after_median": _series_median(after),
                "median_delta": _series_median(delta),
                "median_abs_delta": _series_median(abs_delta),
                "p90_abs_delta": _series_quantile(abs_delta, 0.90),
                "p95_abs_delta": _series_quantile(abs_delta, 0.95),
                "median_abs_pct_delta": _series_median(abs_pct),
                "mean_abs_delta": _series_mean(abs_delta),
            }
        )
    return pd.DataFrame(rows)


def _landmark_delta_summary(paired: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for landmark in LANDMARK_COLUMNS:
        delta = pd.to_numeric(paired[f"delta_{landmark}"], errors="coerce")
        rows.append(
            {
                "landmark": landmark,
                "valid_pairs": int(delta.notna().sum()),
                "median_delta_ms": _series_median(delta),
                "median_abs_delta_ms": _series_median(delta.abs()),
                "p95_abs_delta_ms": _series_quantile(delta.abs(), 0.95),
            }
        )
    for landmark in [
        "pre_peak_index",
        "trough_index",
        "rebound_peak_index",
        "half_width_start_index",
        "half_width_end_index",
        "rep_recovery_index",
    ]:
        delta = pd.to_numeric(paired[f"delta_{landmark}"], errors="coerce")
        rows.append(
            {
                "landmark": landmark,
                "valid_pairs": int(delta.notna().sum()),
                "median_delta_ms": _series_median(delta),
                "median_abs_delta_ms": _series_median(delta.abs()),
                "p95_abs_delta_ms": _series_quantile(delta.abs(), 0.95),
            }
        )
    return pd.DataFrame(rows)


def _class_count_summary(paired: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for stage, column in [("before_unaligned", "before_rs_fs_classification"), ("after_aligned", "after_rs_fs_classification")]:
        counts = paired[column].value_counts(dropna=False)
        for label in CLASS_ORDER:
            rows.append({"stage": stage, "rs_fs_classification": label, "unit_count": int(counts.get(label, 0))})
    rows.append(
        {
            "stage": "changed",
            "rs_fs_classification": "any",
            "unit_count": int(paired["rs_fs_classification_changed"].sum()),
        }
    )
    return pd.DataFrame(rows)


def _alignment_decision(summary: pd.DataFrame, paired: pd.DataFrame) -> dict[str, Any]:
    lookup = summary.set_index("metric").to_dict(orient="index")
    ttp = lookup.get("trough_to_peak_duration_ms", {})
    half_width = lookup.get("spike_half_width_ms", {})
    rep = lookup.get("repolarization_time_ms", {})
    amp = lookup.get("spiketurnpike_amplitude_uV", {})
    changed_fraction = float(paired["rs_fs_classification_changed"].mean()) if len(paired) else np.nan

    substantial = (
        _finite_ge(ttp.get("median_abs_delta"), 0.08)
        or _finite_ge(half_width.get("median_abs_delta"), 0.08)
        or _finite_ge(rep.get("median_abs_delta"), 0.16)
        or _finite_ge(amp.get("median_abs_pct_delta"), 10.0)
        or _finite_ge(changed_fraction, 0.05)
    )
    return {
        "substantial_alignment_effect": bool(substantial),
        "recommend_move_alignment_before_feature_extraction": bool(substantial),
        "criteria": {
            "ttp_median_abs_delta_ms_ge": 0.08,
            "half_width_median_abs_delta_ms_ge": 0.08,
            "rep_median_abs_delta_ms_ge": 0.16,
            "amplitude_median_abs_pct_delta_ge": 10.0,
            "rs_fs_classification_changed_fraction_ge": 0.05,
        },
        "observed": {
            "ttp_median_abs_delta_ms": ttp.get("median_abs_delta"),
            "half_width_median_abs_delta_ms": half_width.get("median_abs_delta"),
            "rep_median_abs_delta_ms": rep.get("median_abs_delta"),
            "amplitude_median_abs_pct_delta": amp.get("median_abs_pct_delta"),
            "rs_fs_classification_changed_fraction": changed_fraction,
        },
    }


def _plot_metric_deltas(plt, paired: pd.DataFrame, path: Path) -> None:
    metrics = [
        "trough_to_peak_duration_ms",
        "spike_half_width_ms",
        "repolarization_time_ms",
        "spiketurnpike_amplitude_uV",
        "template_ptp_best_channel_uV",
        "rep50_recovery_slope_uV_per_ms",
    ]
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 7.2))
    for ax, metric in zip(axes.ravel(), metrics, strict=True):
        values = pd.to_numeric(paired[f"delta_{metric}"], errors="coerce").dropna()
        ax.hist(values, bins=36, color="#4c78a8", alpha=0.86)
        ax.axvline(0, color="#222222", linewidth=1.0)
        ax.set_title(_metric_label(metric))
        ax.set_xlabel("after aligned - before unaligned")
        ax.set_ylabel("Units")
    fig.suptitle("Waveform feature deltas after per-spike trough alignment", y=0.995)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_before_after_scatter(plt, paired: pd.DataFrame, path: Path) -> None:
    metrics = [
        "trough_to_peak_duration_ms",
        "spike_half_width_ms",
        "repolarization_time_ms",
        "spiketurnpike_amplitude_uV",
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 9.0))
    for ax, metric in zip(axes.ravel(), metrics, strict=True):
        before = pd.to_numeric(paired[f"before_{metric}"], errors="coerce")
        after = pd.to_numeric(paired[f"after_{metric}"], errors="coerce")
        colors = paired["after_rs_fs_classification"].map(CLASS_COLORS).fillna("#444444")
        ax.scatter(before, after, c=colors, s=18, alpha=0.76, edgecolor="none")
        lim = _shared_limits(before, after)
        ax.plot(lim, lim, color="#222222", linestyle="--", linewidth=1.0)
        ax.set_xlim(lim)
        ax.set_ylim(lim)
        ax.set_title(_metric_label(metric))
        ax.set_xlabel("Before alignment")
        ax.set_ylabel("After alignment")
    fig.suptitle("Same-unit feature values before vs after spike-snippet alignment", y=0.995)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_largest_change_waveforms(plt, paired: pd.DataFrame, traces: pd.DataFrame, path: Path) -> None:
    if traces.empty:
        return
    top = paired.sort_values("alignment_total_abs_metric_change_rank", ascending=False).head(12)
    ncols = 4
    nrows = int(np.ceil(len(top) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 3.3, nrows * 2.6), squeeze=False)
    for ax in axes.ravel():
        ax.axis("off")
    for ax, (_, row) in zip(axes.ravel(), top.iterrows(), strict=False):
        unit_trace = traces.loc[traces["unit_key"].eq(row["unit_key"])]
        if unit_trace.empty:
            continue
        ax.axis("on")
        ax.axhline(0, color="#d0d0d0", linewidth=0.8)
        ax.plot(unit_trace["time_ms"], unit_trace["before_unaligned_average_uV"], color="#7a7a7a", linewidth=1.5, label="before")
        ax.plot(unit_trace["time_ms"], unit_trace["after_aligned_average_uV"], color="#d55e00", linewidth=1.5, label="after")
        ax.axvline(0, color="#222222", linestyle="--", linewidth=0.8)
        ax.set_title(
            f"{row['well']} u{row['unit_id']} {row['after_rs_fs_classification']}\n"
            f"TTP {row['before_trough_to_peak_duration_ms']:.2f}->{row['after_trough_to_peak_duration_ms']:.2f} ms",
            fontsize=8,
        )
        ax.tick_params(axis="both", labelsize=7)
    handles, labels = axes.ravel()[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper right")
    fig.suptitle("Largest same-unit waveform changes after spike-snippet alignment", y=0.995)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_class_counts(plt, class_counts: pd.DataFrame, path: Path) -> None:
    counts = class_counts.loc[class_counts["stage"].isin(["before_unaligned", "after_aligned"])].copy()
    pivot = counts.pivot(index="rs_fs_classification", columns="stage", values="unit_count").reindex(CLASS_ORDER).fillna(0)
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    x = np.arange(len(pivot))
    width = 0.36
    ax.bar(x - width / 2, pivot.get("before_unaligned", 0), width=width, color="#7a7a7a", label="before")
    ax.bar(x + width / 2, pivot.get("after_aligned", 0), width=width, color="#d55e00", label="after")
    ax.set_xticks(x)
    ax.set_xticklabels(pivot.index)
    ax.set_ylabel("Units")
    ax.set_title("RS/FS counts with unchanged TTP cutoffs")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _templates_average(templates_ext) -> np.ndarray:
    try:
        return np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        templates_data = templates_ext.get_data()
        if isinstance(templates_data, dict):
            templates_data = templates_data.get("average")
        return np.asarray(templates_data, dtype=float)


def _value_at(values: np.ndarray, index: int) -> float:
    if index < 0 or index >= values.size:
        return np.nan
    return float(values[index])


def _delta(after: Any, before: Any) -> float:
    try:
        after_float = float(after)
        before_float = float(before)
    except Exception:  # noqa: BLE001
        return np.nan
    if not np.isfinite(after_float) or not np.isfinite(before_float):
        return np.nan
    return after_float - before_float


def _combined_change_score(row: dict[str, Any]) -> float:
    parts = []
    for metric in [
        "trough_to_peak_duration_ms",
        "spike_half_width_ms",
        "repolarization_time_ms",
        "spiketurnpike_amplitude_uV",
    ]:
        before = row.get(f"before_{metric}", np.nan)
        delta = row.get(f"abs_delta_{metric}", np.nan)
        if np.isfinite(delta):
            denom = abs(float(before)) if np.isfinite(before) and float(before) != 0 else 1.0
            parts.append(float(delta) / denom)
    return float(np.nansum(parts)) if parts else np.nan


def _nanmedian(values: np.ndarray) -> float:
    clean = np.asarray(values, dtype=float)
    if clean.size == 0 or np.all(np.isnan(clean)):
        return np.nan
    return float(np.nanmedian(clean))


def _nanmin(values: np.ndarray) -> float:
    clean = np.asarray(values, dtype=float)
    if clean.size == 0 or np.all(np.isnan(clean)):
        return np.nan
    return float(np.nanmin(clean))


def _nanmax(values: np.ndarray) -> float:
    clean = np.asarray(values, dtype=float)
    if clean.size == 0 or np.all(np.isnan(clean)):
        return np.nan
    return float(np.nanmax(clean))


def _series_median(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return float(clean.median()) if not clean.empty else np.nan


def _series_mean(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return float(clean.mean()) if not clean.empty else np.nan


def _series_quantile(values: pd.Series, q: float) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return float(clean.quantile(q)) if not clean.empty else np.nan


def _finite_ge(value: Any, threshold: float) -> bool:
    try:
        numeric = float(value)
    except Exception:  # noqa: BLE001
        return False
    return bool(np.isfinite(numeric) and numeric >= threshold)


def _shared_limits(before: pd.Series, after: pd.Series) -> tuple[float, float]:
    values = pd.concat([pd.to_numeric(before, errors="coerce"), pd.to_numeric(after, errors="coerce")]).dropna()
    if values.empty:
        return (0.0, 1.0)
    low = float(values.min())
    high = float(values.max())
    if low == high:
        pad = abs(low) * 0.1 if low else 1.0
    else:
        pad = (high - low) * 0.08
    return (low - pad, high + pad)


def _metric_label(metric: str) -> str:
    return metric.replace("_", " ").replace(" uV", " (uV)").replace(" ms", " (ms)")


if __name__ == "__main__":
    main()
