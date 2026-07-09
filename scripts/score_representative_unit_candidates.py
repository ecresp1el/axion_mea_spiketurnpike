#!/usr/bin/env python
"""Score Wave A/B/C representative-unit candidates from Step 1 analyzers."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_WAVE0_ROOT = (
    PROJECT_ROOT
    / "jobs"
    / "step1_nonlfp_th5_v5_ground_truth_latest"
    / "representative_units_20260709_wave0_20260709_162201"
)


@dataclass
class AnalyzerBundle:
    analyzer: object
    unit_ids: list[object]
    unit_index: dict[str, int]
    sampling_frequency: float
    duration_s: float
    templates: np.ndarray
    channel_locations: np.ndarray
    template_similarity: np.ndarray | None
    correlograms: np.ndarray | None
    correlogram_bins: np.ndarray | None
    extension_names: set[str]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-index", type=Path, default=DEFAULT_WAVE0_ROOT / "representative_unit_index_20260709.csv")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--date-label", default="20260709")
    parser.add_argument("--bin-size-s", type=float, default=60.0)
    parser.add_argument("--min-spikes", type=int, default=100)
    parser.add_argument("--presence-threshold", type=float, default=0.80)
    parser.add_argument("--pair-max-distance-um", type=float, default=1000.0)
    parser.add_argument("--top-n-stability", type=int, default=30)
    parser.add_argument("--top-n-pairs", type=int, default=40)
    parser.add_argument("--top-n-wells", type=int, default=20)
    args = parser.parse_args()

    import spikeinterface.full as si

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    index = pd.read_csv(args.input_index)
    index = index.loc[index["ks_label"].astype(str).str.lower().eq("good")].copy()
    if index.empty:
        raise SystemExit("No KSLabel=good units in representative index.")

    stability_rows: list[dict[str, object]] = []
    pair_rows: list[dict[str, object]] = []
    unit_spatial_rows: list[dict[str, object]] = []
    well_rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []

    for analyzer_path, group in index.groupby("analyzer_path", sort=False):
        try:
            bundle = _load_analyzer_bundle(si, Path(analyzer_path))
            stability, spatial = _score_units_in_analyzer(group, bundle, args)
            pairs = _score_pairs_in_analyzer(group, bundle, stability, spatial, args)
            well = _score_well(group, bundle, spatial, pairs)
            stability_rows.extend(stability)
            unit_spatial_rows.extend(spatial)
            pair_rows.extend(pairs)
            if well:
                well_rows.append(well)
        except Exception as exc:  # noqa: BLE001 - preserve per-analyzer errors in output
            first = group.iloc[0]
            errors.append(
                {
                    "recording": first.get("recording", ""),
                    "well": first.get("well", ""),
                    "analyzer_path": analyzer_path,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    stability_df = pd.DataFrame(stability_rows)
    pairs_df = pd.DataFrame(pair_rows)
    spatial_units_df = pd.DataFrame(unit_spatial_rows)
    wells_df = pd.DataFrame(well_rows)
    errors_df = pd.DataFrame(errors)

    stability_candidates = _rank_stability(stability_df, args)
    pair_candidates = _rank_pairs(pairs_df, args)
    well_candidates = _rank_wells(wells_df, args)

    paths = {
        "waveA_stability_candidate_scores": output_dir / f"waveA_stability_candidate_scores_{args.date_label}.csv",
        "waveA_stability_representative_units": output_dir / f"waveA_stability_representative_units_{args.date_label}.csv",
        "waveB_correlogram_pair_scores": output_dir / f"waveB_correlogram_pair_scores_{args.date_label}.csv",
        "waveB_correlogram_representative_units": output_dir / f"waveB_correlogram_representative_units_{args.date_label}.csv",
        "waveC_spatial_footprint_unit_scores": output_dir / f"waveC_spatial_footprint_unit_scores_{args.date_label}.csv",
        "waveC_spatial_footprint_representative_wells": output_dir / f"waveC_spatial_footprint_representative_wells_{args.date_label}.csv",
        "abc_scoring_errors": output_dir / f"abc_scoring_errors_{args.date_label}.csv",
        "abc_scoring_summary": output_dir / f"abc_scoring_summary_{args.date_label}.csv",
        "abc_scoring_provenance": output_dir / f"abc_scoring_provenance_{args.date_label}.json",
    }
    stability_df.to_csv(paths["waveA_stability_candidate_scores"], index=False)
    stability_candidates.to_csv(paths["waveA_stability_representative_units"], index=False)
    pairs_df.to_csv(paths["waveB_correlogram_pair_scores"], index=False)
    pair_candidates.to_csv(paths["waveB_correlogram_representative_units"], index=False)
    spatial_units_df.to_csv(paths["waveC_spatial_footprint_unit_scores"], index=False)
    well_candidates.to_csv(paths["waveC_spatial_footprint_representative_wells"], index=False)
    errors_df.to_csv(paths["abc_scoring_errors"], index=False)

    summary = _summary(index, stability_df, stability_candidates, pairs_df, pair_candidates, wells_df, well_candidates, errors_df)
    summary.to_csv(paths["abc_scoring_summary"], index=False)
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "input_index": str(args.input_index),
        "output_dir": str(output_dir),
        "parameters": {
            "bin_size_s": args.bin_size_s,
            "min_spikes": args.min_spikes,
            "presence_threshold": args.presence_threshold,
            "pair_max_distance_um": args.pair_max_distance_um,
            "top_n_stability": args.top_n_stability,
            "top_n_pairs": args.top_n_pairs,
            "top_n_wells": args.top_n_wells,
        },
        "gui_equivalent_sources": [
            "sorting spike trains",
            "templates extension",
            "correlograms extension when available",
            "template_similarity extension",
            "recording channel locations",
            "unit_locations extension when available",
        ],
        "outputs": {key: str(value) for key, value in paths.items()},
    }
    paths["abc_scoring_provenance"].write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print("ABC representative candidate scoring complete")
    print(summary.to_string(index=False))
    print(f"Output dir: {output_dir}")
    return 0


def _load_analyzer_bundle(si, analyzer_path: Path) -> AnalyzerBundle:
    analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
    unit_ids = list(analyzer.sorting.unit_ids)
    unit_index = {str(unit_id): idx for idx, unit_id in enumerate(unit_ids)}
    sampling_frequency = float(analyzer.recording.get_sampling_frequency())
    duration_s = float(analyzer.recording.get_num_frames()) / sampling_frequency
    templates_ext = analyzer.get_extension("templates")
    if templates_ext is None:
        raise ValueError("missing templates extension")
    templates = _templates_average(templates_ext)
    channel_locations = np.asarray(analyzer.recording.get_channel_locations(), dtype=float)
    extension_names = set(analyzer.get_loaded_extension_names())
    template_similarity = None
    if "template_similarity" in extension_names:
        template_similarity = np.asarray(analyzer.get_extension("template_similarity").get_data(), dtype=float)
    correlograms = None
    correlogram_bins = None
    if "correlograms" in extension_names:
        corr_data = analyzer.get_extension("correlograms").get_data()
        if isinstance(corr_data, tuple) and len(corr_data) >= 2:
            correlograms = np.asarray(corr_data[0], dtype=float)
            correlogram_bins = np.asarray(corr_data[1], dtype=float)
    return AnalyzerBundle(
        analyzer=analyzer,
        unit_ids=unit_ids,
        unit_index=unit_index,
        sampling_frequency=sampling_frequency,
        duration_s=duration_s,
        templates=templates,
        channel_locations=channel_locations,
        template_similarity=template_similarity,
        correlograms=correlograms,
        correlogram_bins=correlogram_bins,
        extension_names=extension_names,
    )


def _score_units_in_analyzer(group: pd.DataFrame, bundle: AnalyzerBundle, args) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    stability_rows = []
    spatial_rows = []
    bin_edges = np.arange(0.0, bundle.duration_s + args.bin_size_s, args.bin_size_s)
    if bin_edges.size < 2:
        bin_edges = np.array([0.0, bundle.duration_s])
    for row in group.itertuples(index=False):
        unit_id = _unit_id_for_sorting(row.unit_id, bundle)
        unit_key = str(row.unit_key)
        if str(unit_id) not in bundle.unit_index:
            continue
        idx = bundle.unit_index[str(unit_id)]
        spike_frames = np.asarray(bundle.analyzer.sorting.get_unit_spike_train(unit_id), dtype=float)
        spike_times_s = spike_frames / bundle.sampling_frequency
        counts, _ = np.histogram(spike_times_s, bins=bin_edges)
        rates = counts / np.diff(bin_edges)
        nonzero = counts > 0
        firing_rate_hz = float(len(spike_times_s) / bundle.duration_s) if bundle.duration_s > 0 else np.nan
        firing_rate_cv = _cv(rates)
        slope = _rate_slope(rates, bin_edges)
        isi_s = np.diff(spike_times_s)
        isi_violations = int(np.sum(isi_s < 0.002))
        isi_violation_ratio = float(isi_violations / max(len(isi_s), 1))
        refractory_score = float(1.0 - min(isi_violation_ratio / 0.02, 1.0))
        template = np.asarray(bundle.templates[idx], dtype=float)
        footprint = np.ptp(template, axis=0)
        best_channel_index = int(np.nanargmax(footprint))
        best_xy = bundle.channel_locations[best_channel_index]
        centroid = _weighted_centroid(bundle.channel_locations, footprint)
        spread = _weighted_spread(bundle.channel_locations, footprint, centroid)
        stability_score = _stability_score(
            num_spikes=len(spike_times_s),
            presence_ratio=float(np.mean(nonzero)) if nonzero.size else np.nan,
            firing_rate_cv=firing_rate_cv,
            isi_violation_ratio=isi_violation_ratio,
            min_spikes=args.min_spikes,
        )
        common = _common_row(row)
        stability_rows.append(
            {
                **common,
                "num_spikes": int(len(spike_times_s)),
                "duration_s": bundle.duration_s,
                "firing_rate_hz_analyzer": firing_rate_hz,
                "firing_rate_bin_count": int(len(rates)),
                "firing_rate_bin_size_s": float(args.bin_size_s),
                "presence_ratio": float(np.mean(nonzero)) if nonzero.size else np.nan,
                "firing_rate_cv": firing_rate_cv,
                "firing_rate_slope_hz_per_min": slope,
                "isi_violations_count": isi_violations,
                "isi_violation_ratio": isi_violation_ratio,
                "refractory_score": refractory_score,
                "waveform_ptp_best_channel_uV": float(footprint[best_channel_index]),
                "best_channel_index_scored": best_channel_index,
                "best_channel_x": float(best_xy[0]),
                "best_channel_y": float(best_xy[1]),
                "template_centroid_x": float(centroid[0]),
                "template_centroid_y": float(centroid[1]),
                "template_spatial_spread_um": spread,
                "stability_score": stability_score,
                "passes_stability_prefilter": bool(
                    len(spike_times_s) >= args.min_spikes and (np.mean(nonzero) if nonzero.size else 0) >= args.presence_threshold
                ),
                "gui_equivalent_render_sources": "sorting spike train;templates;recording channel locations",
            }
        )
        spatial_rows.append(
            {
                **common,
                "num_spikes": int(len(spike_times_s)),
                "best_channel_index_scored": best_channel_index,
                "best_channel_x": float(best_xy[0]),
                "best_channel_y": float(best_xy[1]),
                "template_centroid_x": float(centroid[0]),
                "template_centroid_y": float(centroid[1]),
                "template_spatial_spread_um": spread,
                "template_ptp_total_uV": float(np.nansum(footprint)),
                "template_ptp_max_uV": float(np.nanmax(footprint)),
                "neighbor_channel_count": int(np.sum(footprint >= np.nanmax(footprint) * 0.25)),
                "gui_equivalent_render_sources": "templates;recording channel locations;unit_locations if needed",
            }
        )
    return stability_rows, spatial_rows


def _score_pairs_in_analyzer(group: pd.DataFrame, bundle: AnalyzerBundle, stability_rows: list[dict[str, object]], spatial_rows: list[dict[str, object]], args) -> list[dict[str, object]]:
    stability_by_key = {row["unit_key"]: row for row in stability_rows}
    spatial_by_key = {row["unit_key"]: row for row in spatial_rows}
    rows = []
    records = list(group.itertuples(index=False))
    for i, a in enumerate(records):
        for b in records[i + 1 :]:
            key_a = str(a.unit_key)
            key_b = str(b.unit_key)
            if key_a not in stability_by_key or key_b not in stability_by_key:
                continue
            class_a = getattr(a, "fs_rs_cutoff_0p50_aligned", "")
            class_b = getattr(b, "fs_rs_cutoff_0p50_aligned", "")
            xy_a = np.array([spatial_by_key[key_a]["best_channel_x"], spatial_by_key[key_a]["best_channel_y"]], dtype=float)
            xy_b = np.array([spatial_by_key[key_b]["best_channel_x"], spatial_by_key[key_b]["best_channel_y"]], dtype=float)
            distance = float(np.linalg.norm(xy_a - xy_b))
            if not np.isfinite(distance) or distance > args.pair_max_distance_um:
                continue
            idx_a = bundle.unit_index.get(str(_unit_id_for_sorting(a.unit_id, bundle)))
            idx_b = bundle.unit_index.get(str(_unit_id_for_sorting(b.unit_id, bundle)))
            similarity = np.nan
            if bundle.template_similarity is not None and idx_a is not None and idx_b is not None:
                similarity = float(bundle.template_similarity[idx_a, idx_b])
            cross_zero, cross_side, duplicate_score = _cross_duplicate_score(bundle, idx_a, idx_b, a.unit_id, b.unit_id)
            refractory_min = min(stability_by_key[key_a]["refractory_score"], stability_by_key[key_b]["refractory_score"])
            pair_score = _pair_score(refractory_min, duplicate_score, distance, similarity, class_a, class_b)
            rows.append(
                {
                    "recording": getattr(a, "recording"),
                    "well": getattr(a, "well"),
                    "analyzer_path": getattr(a, "analyzer_path"),
                    "unit_key_a": key_a,
                    "unit_key_b": key_b,
                    "unit_id_a": getattr(a, "unit_id"),
                    "unit_id_b": getattr(b, "unit_id"),
                    "class_a": class_a,
                    "class_b": class_b,
                    "num_spikes_a": stability_by_key[key_a]["num_spikes"],
                    "num_spikes_b": stability_by_key[key_b]["num_spikes"],
                    "isi_violation_ratio_a": stability_by_key[key_a]["isi_violation_ratio"],
                    "isi_violation_ratio_b": stability_by_key[key_b]["isi_violation_ratio"],
                    "best_channel_distance_um": distance,
                    "template_similarity": similarity,
                    "cross_zero_lag_count": cross_zero,
                    "cross_side_count_mean": cross_side,
                    "cross_correlogram_zero_lag_duplicate_score": duplicate_score,
                    "pair_score": pair_score,
                    "is_fs_rs_pair": bool({class_a, class_b} == {"FS_like", "RS_like"}),
                    "is_nonzero_neighbor_pair": bool(distance > 0),
                    "same_well_pair": True,
                    "gui_equivalent_render_sources": "sorting spike trains;correlograms/template_similarity/templates/probe",
                }
            )
    return rows


def _score_well(group: pd.DataFrame, bundle: AnalyzerBundle, spatial_rows: list[dict[str, object]], pair_rows: list[dict[str, object]]) -> dict[str, object] | None:
    if not spatial_rows:
        return None
    first = group.iloc[0]
    distances = []
    for i, row_a in enumerate(spatial_rows):
        for row_b in spatial_rows[i + 1 :]:
            xy_a = np.array([row_a["best_channel_x"], row_a["best_channel_y"]], dtype=float)
            xy_b = np.array([row_b["best_channel_x"], row_b["best_channel_y"]], dtype=float)
            distances.append(float(np.linalg.norm(xy_a - xy_b)))
    finite_distances = [d for d in distances if np.isfinite(d)]
    good_units = len(spatial_rows)
    fs_count = int(sum(str(getattr(row, "fs_rs_cutoff_0p50_aligned", "")) == "FS_like" for row in group.itertuples(index=False)))
    rs_count = int(sum(str(getattr(row, "fs_rs_cutoff_0p50_aligned", "")) == "RS_like" for row in group.itertuples(index=False)))
    median_distance = float(np.nanmedian(finite_distances)) if finite_distances else np.nan
    max_distance = float(np.nanmax(finite_distances)) if finite_distances else np.nan
    pair_count = len(pair_rows)
    well_score = good_units + min(max_distance if np.isfinite(max_distance) else 0.0, 300.0) / 100.0 + min(pair_count, 5) * 0.5
    return {
        "recording": first["recording"],
        "well": first["well"],
        "analyzer_path": first["analyzer_path"],
        "track": first["track"],
        "region_label": first.get("region_label", ""),
        "lumos_geometry_group": first.get("lumos_geometry_group", ""),
        "good_units_in_well": good_units,
        "fs_like_units_0p50_aligned": fs_count,
        "rs_like_units_0p50_aligned": rs_count,
        "pair_count_within_distance": pair_count,
        "median_best_channel_distance_um": median_distance,
        "max_best_channel_distance_um": max_distance,
        "well_spatial_score": float(well_score),
        "gui_equivalent_render_sources": "templates;recording channel locations;probe/similarity context",
    }


def _rank_stability(df: pd.DataFrame, args) -> pd.DataFrame:
    if df.empty:
        return df
    ranked = df.sort_values(
        ["passes_stability_prefilter", "stability_score", "presence_ratio", "num_spikes"],
        ascending=[False, False, False, False],
    ).copy()
    ranked["selection_wave"] = "A"
    ranked["selection_panel"] = "waveform_stability_firing_rate_over_time"
    ranked["selection_rank"] = np.arange(1, len(ranked) + 1)
    ranked["selection_reason"] = "ranked stable KSLabel=good unit from Step 1 analyzer spike train/template data"
    return ranked.head(args.top_n_stability)


def _rank_pairs(df: pd.DataFrame, args) -> pd.DataFrame:
    if df.empty:
        return df
    ranked = df.sort_values(
        ["is_nonzero_neighbor_pair", "is_fs_rs_pair", "pair_score", "cross_correlogram_zero_lag_duplicate_score"],
        ascending=[False, False, False, True],
    ).copy()
    ranked["selection_wave"] = "B"
    ranked["selection_panel"] = "autocorrelogram_crosscorrelogram_fs_rs"
    ranked["selection_rank"] = np.arange(1, len(ranked) + 1)
    ranked["selection_reason"] = "ranked within-well unit pair with refractory/duplicate-risk metrics"
    return ranked.head(args.top_n_pairs)


def _rank_wells(df: pd.DataFrame, args) -> pd.DataFrame:
    if df.empty:
        return df
    ranked = df.sort_values(
        ["good_units_in_well", "well_spatial_score", "max_best_channel_distance_um"],
        ascending=[False, False, False],
    ).copy()
    ranked["selection_wave"] = "C"
    ranked["selection_panel"] = "within_well_spatial_footprints"
    ranked["selection_rank"] = np.arange(1, len(ranked) + 1)
    ranked["selection_reason"] = "ranked well with multiple KSLabel=good units and separated template footprints"
    return ranked.head(args.top_n_wells)


def _cross_duplicate_score(bundle: AnalyzerBundle, idx_a: int | None, idx_b: int | None, unit_id_a, unit_id_b) -> tuple[float, float, float]:
    if bundle.correlograms is not None and idx_a is not None and idx_b is not None:
        corr = bundle.correlograms
        if corr.ndim == 3 and idx_a < corr.shape[0] and idx_b < corr.shape[1]:
            values = np.asarray(corr[idx_a, idx_b], dtype=float)
            zero_index = int(np.argmin(np.abs(_bin_centers(bundle.correlogram_bins, values.size))))
            zero = float(values[zero_index])
            mask = np.ones(values.size, dtype=bool)
            lo = max(0, zero_index - 2)
            hi = min(values.size, zero_index + 3)
            mask[lo:hi] = False
            side = float(np.nanmean(values[mask])) if np.any(mask) else 0.0
            score = float(zero / (side + 1.0))
            return zero, side, score
    spikes_a = np.asarray(bundle.analyzer.sorting.get_unit_spike_train(_unit_id_for_sorting(unit_id_a, bundle)), dtype=float)
    spikes_b = np.asarray(bundle.analyzer.sorting.get_unit_spike_train(_unit_id_for_sorting(unit_id_b, bundle)), dtype=float)
    if spikes_a.size == 0 or spikes_b.size == 0:
        return 0.0, 0.0, 0.0
    times_a = spikes_a / bundle.sampling_frequency
    times_b = spikes_b / bundle.sampling_frequency
    zero = _count_near_zero_lag(times_a, times_b, window_s=0.001)
    side = _count_near_zero_lag(times_a, times_b, window_s=0.010) / 20.0
    return float(zero), float(side), float(zero / (side + 1.0))


def _common_row(row) -> dict[str, object]:
    return {
        "recording": getattr(row, "recording"),
        "well": getattr(row, "well"),
        "unit_id": getattr(row, "unit_id"),
        "unit_key": getattr(row, "unit_key"),
        "analyzer_path": getattr(row, "analyzer_path"),
        "track": getattr(row, "track"),
        "region_label": getattr(row, "region_label", ""),
        "lumos_geometry_group": getattr(row, "lumos_geometry_group", ""),
        "fs_rs_cutoff_0p37_aligned": getattr(row, "fs_rs_cutoff_0p37_aligned", ""),
        "fs_rs_cutoff_0p50_aligned": getattr(row, "fs_rs_cutoff_0p50_aligned", ""),
        "opto_status": getattr(row, "opto_status", ""),
        "opto_review_rank": getattr(row, "opto_review_rank", np.nan),
        "opto_peak_raw_response_hz": getattr(row, "opto_peak_raw_response_hz", np.nan),
    }


def _summary(index, stability_df, stability_candidates, pairs_df, pair_candidates, wells_df, well_candidates, errors_df) -> pd.DataFrame:
    rows = [
        {"metric": "input_units", "value": len(index)},
        {"metric": "scored_stability_units", "value": len(stability_df)},
        {"metric": "selected_waveA_units", "value": len(stability_candidates)},
        {"metric": "scored_pairs", "value": len(pairs_df)},
        {"metric": "selected_waveB_pairs", "value": len(pair_candidates)},
        {"metric": "scored_wells", "value": len(wells_df)},
        {"metric": "selected_waveC_wells", "value": len(well_candidates)},
        {"metric": "analyzer_errors", "value": len(errors_df)},
    ]
    return pd.DataFrame(rows)


def _templates_average(templates_ext) -> np.ndarray:
    try:
        return np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        data = templates_ext.get_data()
        if isinstance(data, dict):
            data = data.get("average")
        return np.asarray(data, dtype=float)


def _unit_id_for_sorting(value, bundle: AnalyzerBundle):
    text = str(value)
    for unit_id in bundle.unit_ids:
        if str(unit_id) == text:
            return unit_id
    try:
        numeric = int(float(value))
    except Exception:
        return value
    for unit_id in bundle.unit_ids:
        try:
            if int(unit_id) == numeric:
                return unit_id
        except Exception:
            continue
    return value


def _cv(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    mean = float(np.nanmean(values)) if values.size else np.nan
    if not np.isfinite(mean) or mean <= 0:
        return np.nan
    return float(np.nanstd(values) / mean)


def _rate_slope(rates: np.ndarray, bin_edges: np.ndarray) -> float:
    if len(rates) < 2:
        return np.nan
    centers_min = ((bin_edges[:-1] + bin_edges[1:]) / 2.0) / 60.0
    try:
        return float(np.polyfit(centers_min, rates, 1)[0])
    except Exception:
        return np.nan


def _stability_score(*, num_spikes: int, presence_ratio: float, firing_rate_cv: float, isi_violation_ratio: float, min_spikes: int) -> float:
    spike_score = min(num_spikes / max(min_spikes, 1), 3.0) / 3.0
    presence = 0.0 if not np.isfinite(presence_ratio) else presence_ratio
    cv_penalty = min(firing_rate_cv if np.isfinite(firing_rate_cv) else 2.0, 2.0) / 2.0
    isi_penalty = min(isi_violation_ratio / 0.02 if np.isfinite(isi_violation_ratio) else 1.0, 1.0)
    return float(0.35 * presence + 0.25 * spike_score + 0.25 * (1 - cv_penalty) + 0.15 * (1 - isi_penalty))


def _pair_score(refractory_min: float, duplicate_score: float, distance: float, similarity: float, class_a: str, class_b: str) -> float:
    fs_rs_bonus = 0.25 if {class_a, class_b} == {"FS_like", "RS_like"} else 0.0
    distance_score = min(distance / 100.0, 1.0) if np.isfinite(distance) else 0.0
    duplicate_penalty = min(duplicate_score / 5.0, 1.0) if np.isfinite(duplicate_score) else 0.0
    similarity_penalty = min(abs(similarity), 1.0) if np.isfinite(similarity) else 0.0
    return float(0.35 * refractory_min + 0.20 * distance_score + 0.20 * (1 - duplicate_penalty) + 0.20 * (1 - similarity_penalty) + fs_rs_bonus)


def _weighted_centroid(locations: np.ndarray, weights: np.ndarray) -> np.ndarray:
    weights = np.asarray(weights, dtype=float)
    if not np.isfinite(weights).any() or np.nansum(weights) <= 0:
        return np.array([np.nan, np.nan])
    return np.nansum(locations[:, :2] * weights[:, None], axis=0) / np.nansum(weights)


def _weighted_spread(locations: np.ndarray, weights: np.ndarray, centroid: np.ndarray) -> float:
    if not np.isfinite(centroid).all() or np.nansum(weights) <= 0:
        return np.nan
    distances = np.linalg.norm(locations[:, :2] - centroid[None, :], axis=1)
    return float(np.nansum(distances * weights) / np.nansum(weights))


def _bin_centers(bins: np.ndarray | None, size: int) -> np.ndarray:
    if bins is None:
        return np.arange(size) - size // 2
    if bins.size == size + 1:
        return (bins[:-1] + bins[1:]) / 2.0
    if bins.size == size:
        return bins
    return np.arange(size) - size // 2


def _count_near_zero_lag(times_a: np.ndarray, times_b: np.ndarray, *, window_s: float) -> int:
    count = 0
    j0 = 0
    for t in times_a:
        while j0 < times_b.size and times_b[j0] < t - window_s:
            j0 += 1
        j = j0
        while j < times_b.size and times_b[j] <= t + window_s:
            count += 1
            j += 1
    return count


if __name__ == "__main__":
    raise SystemExit(main())
