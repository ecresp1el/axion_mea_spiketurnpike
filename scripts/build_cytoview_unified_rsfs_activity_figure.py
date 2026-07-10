#!/usr/bin/env python3
"""Build the unified CytoView RS/FS classification and activity figure."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


JOB_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_ACTIVITY_DIR = (
    JOB_ROOT
    / "cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_"
    "isi2ms_le3pct_exclude2_dorsal_drivers_20260710_082420"
)
DEFAULT_ALIGNMENT_DIR = JOB_ROOT / "waveform_alignment_feature_audit_20260709_cytoview"
STEM = "cytoview_unified_rsfs_activity_figure_20260710"

CLASS_ORDER = ["FS", "RS"]
CLASS_COLORS = {"FS": "#E76F51", "RS": "#277DA1"}
REGION_ORDER = ["dorsal", "ventral"]
REGION_COLORS = {"dorsal": "#2A9D8F", "ventral": "#6A4C93"}
VARIANT_MARKERS = {
    "primary_raw": "o",
    "filter_200Hz-3kHz": "s",
    "broadband_processor_raw": "^",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activity-dir", type=Path, default=DEFAULT_ACTIVITY_DIR)
    parser.add_argument("--alignment-dir", type=Path, default=DEFAULT_ALIGNMENT_DIR)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--fs-cutoff-ms", type=float, default=0.50)
    parser.add_argument("--export-formats", default="png,pdf,svg")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    activity_dir = args.activity_dir.expanduser().resolve()
    alignment_dir = args.alignment_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from mpl_toolkits.axes_grid1.inset_locator import inset_axes

    activity_stem = "cytoview_dv_sua_spontaneous_activity_20260710"
    unit_path = activity_dir / f"{activity_stem}_unit_metrics.csv"
    well_path = activity_dir / f"{activity_stem}_recording_well_summary.csv"
    activity_provenance_path = activity_dir / f"{activity_stem}_provenance.json"
    exclusion_path = activity_dir / f"{activity_stem}_explicitly_excluded_units.csv"
    trace_path = alignment_dir / "waveform_alignment_feature_audit_20260709_waveform_traces.csv.gz"
    paired_metrics_path = (
        alignment_dir / "waveform_alignment_feature_audit_20260709_paired_unit_metrics.csv"
    )
    alignment_provenance_path = alignment_dir / "waveform_alignment_feature_audit_20260709_provenance.json"

    units = pd.read_csv(unit_path)
    wells = pd.read_csv(well_path)
    traces_all = pd.read_csv(trace_path)
    paired_metrics = pd.read_csv(paired_metrics_path)
    units = units.loc[units["aligned_fs_rs_class"].isin(CLASS_ORDER)].copy()
    audit_feature_columns = [
        "after_spike_half_width_ms",
        "after_repolarization_time_ms",
        "after_template_ptp_best_channel_uV",
        "after_spiketurnpike_amplitude_uV",
        "after_pre_peak_amplitude_uV",
        "after_post_peak_amplitude_uV",
        "after_depolarization_slope_uV_per_ms",
        "after_post_trough_rebound_slope_uV_per_ms",
        "after_rep50_recovery_slope_uV_per_ms",
        "after_waveform_asymmetry",
        "after_peak_to_peak_ratio",
    ]
    units = units.merge(
        paired_metrics[["unit_key", *audit_feature_columns]],
        on="unit_key",
        how="left",
        validate="one_to_one",
    )
    units["rs_fs_class"] = units["aligned_fs_rs_class"]
    units["feature_ttp_ms"] = pd.to_numeric(
        units["aligned_trough_to_peak_duration_ms"], errors="coerce"
    )
    units["feature_asymmetry"] = pd.to_numeric(
        units["aligned_waveform_asymmetry"], errors="coerce"
    )
    units["feature_repolarization_slope_uV_per_ms"] = pd.to_numeric(
        units["aligned_repolarization_slope_uV_per_ms"], errors="coerce"
    )
    units["feature_repolarization_time_ms"] = pd.to_numeric(
        units["after_repolarization_time_ms"], errors="coerce"
    )
    units["feature_spike_half_width_ms"] = pd.to_numeric(
        units["after_spike_half_width_ms"], errors="coerce"
    )
    expected_class = np.where(units["feature_ttp_ms"].le(args.fs_cutoff_ms), "FS", "RS")
    if not np.array_equal(expected_class, units["rs_fs_class"].to_numpy()):
        raise ValueError("Stored RS/FS classes do not match the requested aligned TTP cutoff")
    feature_columns = [
        "feature_ttp_ms",
        "feature_asymmetry",
        "feature_repolarization_slope_uV_per_ms",
        "feature_repolarization_time_ms",
        "feature_spike_half_width_ms",
    ]
    if units[["feature_ttp_ms", "feature_spike_half_width_ms"]].isna().any().any():
        raise ValueError("Class-defining TTP or spike half-width is missing for retained units")

    traces = traces_all.loc[traces_all["unit_key"].isin(units["unit_key"])].copy()
    if traces["unit_key"].nunique() != len(units):
        raise ValueError("Not every retained activity unit has an aligned waveform trace")
    traces = traces.merge(
        units[["unit_key", "rs_fs_class"]], on="unit_key", how="left", validate="many_to_one"
    )
    traces = _normalize_waveforms(traces)
    waveform_summary = _waveform_summary(traces)
    feature_selection_audit = _feature_selection_audit(units, audit_feature_columns)
    representative_ranking, representative_selection = _select_representatives(units)
    representative_assets = _load_representative_assets(representative_selection)
    representative_spatial_source, representative_acg_source, representative_amplitude_source = (
        _representative_source_tables(representative_assets)
    )
    panel_d_specs = _panel_d_specs()
    panel_d_source = _panel_d_source_data(wells, panel_d_specs)

    feature_path = output_dir / f"{STEM}_panel_A_aligned_features.csv"
    trace_output_path = output_dir / f"{STEM}_panel_A_landmark_waveform_traces.csv.gz"
    waveform_summary_path = output_dir / f"{STEM}_panel_A_landmark_waveform_summary.csv"
    feature_audit_path = output_dir / f"{STEM}_panel_A_feature_selection_audit.csv"
    representative_ranking_path = output_dir / f"{STEM}_panels_B_C_representative_ranking.csv"
    representative_selection_path = output_dir / f"{STEM}_panels_B_C_representative_selection.csv"
    representative_spatial_path = output_dir / f"{STEM}_panels_B_C_spatial_waveforms.csv.gz"
    representative_acg_path = output_dir / f"{STEM}_panels_B_C_autocorrelograms.csv"
    representative_amplitude_path = output_dir / f"{STEM}_panels_B_C_amplitude_stability.csv.gz"
    panel_d_path = output_dir / f"{STEM}_panel_D_activity_source_data.csv"
    units[
        [
            "unit_key",
            "recording_well_id",
            "recording",
            "well",
            "region_call",
            "raw_variant",
            "unit_id",
            "rs_fs_class",
            *feature_columns,
            "template_ptp_best_channel_uV",
            "source_isi_lt_2ms_fraction",
            "inverse_isi_gaussian_temporal_p99_9_hz",
        ]
    ].to_csv(feature_path, index=False)
    traces.to_csv(trace_output_path, index=False, compression="gzip")
    waveform_summary.to_csv(waveform_summary_path, index=False)
    feature_selection_audit.to_csv(feature_audit_path, index=False)
    representative_ranking.to_csv(representative_ranking_path, index=False)
    representative_selection.to_csv(representative_selection_path, index=False)
    representative_spatial_source.to_csv(
        representative_spatial_path, index=False, compression="gzip"
    )
    representative_acg_source.to_csv(representative_acg_path, index=False)
    representative_amplitude_source.to_csv(
        representative_amplitude_path, index=False, compression="gzip"
    )
    panel_d_source.to_csv(panel_d_path, index=False)

    figure_paths = _plot_unified_figure(
        plt,
        Line2D,
        inset_axes,
        units,
        traces,
        waveform_summary,
        representative_assets,
        wells,
        panel_d_specs,
        output_dir / STEM,
        args.export_formats,
        args.fs_cutoff_ms,
    )

    activity_provenance = json.loads(activity_provenance_path.read_text(encoding="utf-8"))
    excluded = pd.read_csv(exclusion_path)
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "figure_role": "unified supplementary figure; panels A-C RS/FS classification, panel D activity",
        "activity_source_dir": str(activity_dir),
        "activity_provenance": str(activity_provenance_path),
        "activity_provenance_sha256": _sha256(activity_provenance_path),
        "alignment_source_dir": str(alignment_dir),
        "alignment_provenance": str(alignment_provenance_path),
        "alignment_provenance_sha256": _sha256(alignment_provenance_path),
        "population": {
            "KSLabel": "good",
            "unit_count": int(len(units)),
            "class_counts": units["rs_fs_class"].value_counts().to_dict(),
            "aligned_before_feature_extraction": True,
            "FS_rule": f"aligned trough-to-peak duration <= {args.fs_cutoff_ms:.2f} ms",
            "RS_rule": f"aligned trough-to-peak duration > {args.fs_cutoff_ms:.2f} ms",
            "minimum_template_ptp_uV_inclusive": activity_provenance["unit_quality_filters"][
                "minimum_uV_inclusive"
            ],
            "maximum_isi_lt_2ms_fraction_inclusive": activity_provenance[
                "unit_quality_filters"
            ]["maximum_isi_lt_2ms_fraction_inclusive"],
            "explicit_dorsal_driver_units_excluded": int(len(excluded)),
            "explicit_exclusion_unit_keys": excluded["unit_key"].tolist(),
            "ventral_units_explicitly_excluded": int(excluded["region_call"].eq("ventral").sum()),
        },
        "panel_A": {
            "features": [
                "aligned trough-to-peak duration",
                "aligned repolarization time",
                "aligned spike half-width",
            ],
            "feature_space_encoding": (
                "3D x=TTP, y=repolarization time, z=spike half-width; "
                "point size=unit temporal P99.9 smoothed inverse-ISI firing rate; "
                "color=locked TTP-cutoff RS/FS class"
            ),
            "selection_result": (
                "repolarization time was the strongest non-TTP univariate feature; "
                "half-width was the second strongest and is an interpretable timing metric"
            ),
            "circular_pair_rejected": (
                "post-peak amplitude + post-trough rebound slope nearly reconstructs TTP "
                "because slope = amplitude / TTP; it was not used"
            ),
            "interpretation": (
                "exploratory same-dataset feature ranking; RS/FS labels remain defined only by aligned TTP"
            ),
            "units_with_complete_display_features": int(
                units[["feature_ttp_ms", "feature_repolarization_time_ms", "feature_spike_half_width_ms"]]
                .notna()
                .all(axis=1)
                .sum()
            ),
        },
        "panel_B": {
            "display": "three compact KSLabel=good FS representative-unit QC cards",
            "card_assets": ["local multichannel footprint", "probability autocorrelogram", "amplitude stability"],
        },
        "panel_C_representative_units": {
            "display": "three compact KSLabel=good RS representative-unit QC cards",
            "card_assets": ["local multichannel footprint", "probability autocorrelogram", "amplitude stability"],
            "selection": (
                "within-class waveform-feature centrality plus spike-count/template-PTP quality; "
                "at least one dorsal and one ventral unit per class when available"
            ),
        },
        "panel_D": {
            "layout": "single row, one metric per column, compact dorsal/ventral spacing",
            "metrics": [spec[1] for spec in panel_d_specs],
            "E1_choice": "legacy spike-count / recording-duration firing rate only",
            "aggregation": "one point per recording-version/well organoid; regional mean +/- SEM",
            "burst_detection": activity_provenance["burst_detection"],
        },
        "outputs": {
            "figures": [str(path) for path in figure_paths],
            "panel_A_features": str(feature_path),
            "panel_A_feature_selection_audit": str(feature_audit_path),
            "panels_B_C_representative_ranking": str(representative_ranking_path),
            "panels_B_C_representative_selection": str(representative_selection_path),
            "panels_B_C_spatial_waveforms": str(representative_spatial_path),
            "panels_B_C_autocorrelograms": str(representative_acg_path),
            "panels_B_C_amplitude_stability": str(representative_amplitude_path),
            "panel_A_landmark_traces": str(trace_output_path),
            "panel_A_landmark_summary": str(waveform_summary_path),
            "panel_D_source": str(panel_d_path),
        },
    }
    provenance_path = output_dir / f"{STEM}_provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(f"Retained units: {len(units)}")
    print(f"Class counts: {units['rs_fs_class'].value_counts().to_dict()}")
    print(f"Recording/well universe: {len(wells)}")
    print("Figures:")
    for path in figure_paths:
        print(path)
    print(f"Provenance: {provenance_path}")
    return 0


def _normalize_waveforms(traces: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for _, group in traces.groupby("unit_key", sort=False):
        group = group.sort_values("time_ms").copy()
        time = group["time_ms"].to_numpy(dtype=float)
        wave = group["after_aligned_average_uV"].to_numpy(dtype=float)
        baseline_mask = time <= -0.64
        baseline = float(np.nanmean(wave[baseline_mask])) if baseline_mask.any() else float(wave[0])
        centered = wave - baseline
        trough_amplitude = abs(float(np.nanmin(centered)))
        group["baseline_subtracted_waveform_uV"] = centered
        group["trough_normalized_waveform"] = (
            centered / trough_amplitude if trough_amplitude > 0 else np.nan
        )
        frames.append(group)
    return pd.concat(frames, ignore_index=True)


def _waveform_summary(traces: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (class_label, time_ms), group in traces.groupby(["rs_fs_class", "time_ms"], sort=True):
        for value_column, representation in [
            ("after_aligned_average_uV", "raw_uV"),
            ("trough_normalized_waveform", "trough_normalized"),
        ]:
            values = pd.to_numeric(group[value_column], errors="coerce").dropna().to_numpy(float)
            rows.append(
                {
                    "rs_fs_class": class_label,
                    "time_ms": float(time_ms),
                    "representation": representation,
                    "unit_count": int(values.size),
                    "mean": float(np.mean(values)),
                    "sem": _sem(values),
                }
            )
    return pd.DataFrame(rows)


def _feature_selection_audit(
    units: pd.DataFrame, candidate_features: list[str]
) -> pd.DataFrame:
    """Rank non-TTP features without changing the TTP-defined class labels."""
    from itertools import combinations

    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import RepeatedStratifiedKFold, cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import RobustScaler

    y = units["rs_fs_class"].eq("FS").astype(int).to_numpy()
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=5, random_state=20260710)

    def cv_score(features: list[str]) -> tuple[float, float]:
        model = make_pipeline(
            SimpleImputer(strategy="median"),
            RobustScaler(),
            LogisticRegression(C=1.0, class_weight="balanced", max_iter=3000),
        )
        scores = cross_val_score(
            model,
            units[features],
            y,
            cv=cv,
            scoring="roc_auc",
            n_jobs=1,
        )
        return float(np.mean(scores)), float(np.std(scores))

    selected_pair = frozenset(
        ["after_repolarization_time_ms", "after_spike_half_width_ms"]
    )
    circular_pair = frozenset(
        [
            "after_post_peak_amplitude_uV",
            "after_post_trough_rebound_slope_uV_per_ms",
        ]
    )
    rows: list[dict[str, object]] = []
    for feature in candidate_features:
        values = pd.to_numeric(units[feature], errors="coerce").to_numpy(float)
        valid = np.isfinite(values)
        apparent_auc = roc_auc_score(y[valid], values[valid])
        apparent_auc = max(float(apparent_auc), 1.0 - float(apparent_auc))
        mean_auc, sd_auc = cv_score([feature])
        rows.append(
            {
                "model_kind": "univariate_non_TTP",
                "feature_1": feature,
                "feature_2": "",
                "direction_invariant_apparent_auc": apparent_auc,
                "repeated_5x5fold_cv_roc_auc_mean": mean_auc,
                "repeated_5x5fold_cv_roc_auc_sd": sd_auc,
                "selected_for_panel_A": feature in selected_pair,
                "rejected_as_circular": False,
                "note": "labels are defined by aligned TTP; this is an exploratory association audit",
            }
        )
    for feature_1, feature_2 in combinations(candidate_features, 2):
        pair = frozenset([feature_1, feature_2])
        mean_auc, sd_auc = cv_score([feature_1, feature_2])
        rows.append(
            {
                "model_kind": "pair_non_TTP",
                "feature_1": feature_1,
                "feature_2": feature_2,
                "direction_invariant_apparent_auc": np.nan,
                "repeated_5x5fold_cv_roc_auc_mean": mean_auc,
                "repeated_5x5fold_cv_roc_auc_sd": sd_auc,
                "selected_for_panel_A": pair == selected_pair,
                "rejected_as_circular": pair == circular_pair,
                "note": (
                    "algebraically reconstructs TTP because rebound slope = post-peak amplitude / TTP"
                    if pair == circular_pair
                    else "exploratory same-dataset feature association"
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["model_kind", "repeated_5x5fold_cv_roc_auc_mean"],
        ascending=[True, False],
    )


def _select_representatives(units: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rank clean, class-central units and select three per class with region diversity."""
    frames: list[pd.DataFrame] = []
    feature_columns = [
        "feature_ttp_ms",
        "feature_repolarization_time_ms",
        "feature_spike_half_width_ms",
    ]
    for class_label in CLASS_ORDER:
        group = units.loc[units["rs_fs_class"].eq(class_label)].copy()
        group["representative_candidate"] = (
            pd.to_numeric(group["source_spike_count"], errors="coerce").ge(100)
            & pd.to_numeric(
                group["inverse_isi_gaussian_temporal_p99_9_hz"], errors="coerce"
            ).notna()
            & group[feature_columns].notna().all(axis=1)
        )
        candidate = group.loc[group["representative_candidate"]].copy()
        median = candidate[feature_columns].median()
        mad = (candidate[feature_columns] - median).abs().median().replace(0, 1.0)
        group["waveform_centrality_score"] = (
            (group[feature_columns] - median).abs().div(mad).mean(axis=1)
        )

        def robust_z(series: pd.Series) -> pd.Series:
            numeric = pd.to_numeric(series, errors="coerce")
            center = float(numeric.median())
            spread = float((numeric - center).abs().median())
            return (numeric - center) / (spread if spread > 0 else 1.0)

        group["representative_quality_score"] = (
            robust_z(np.log1p(pd.to_numeric(group["source_spike_count"], errors="coerce")))
            + robust_z(
                np.log1p(pd.to_numeric(group["template_ptp_best_channel_uV"], errors="coerce"))
            )
            + 0.8
            * robust_z(
                np.log1p(pd.to_numeric(group["source_firing_rate_hz"], errors="coerce"))
            )
            - 0.5 * robust_z(group["source_isi_lt_2ms_fraction"])
            - 0.2 * robust_z(group["source_ContamPct"])
        )
        group["representative_selection_score"] = (
            group["representative_quality_score"] - group["waveform_centrality_score"]
        )
        frames.append(group)
    ranking = pd.concat(frames, ignore_index=True).sort_values(
        ["rs_fs_class", "representative_selection_score"],
        ascending=[True, False],
    )

    selected_rows: list[pd.Series] = []
    for class_label in CLASS_ORDER:
        pool = ranking.loc[
            ranking["rs_fs_class"].eq(class_label)
            & ranking["representative_candidate"]
            & ranking["waveform_centrality_score"].le(1.25)
        ].sort_values("representative_selection_score", ascending=False)
        if len(pool) < 3:
            pool = ranking.loc[
                ranking["rs_fs_class"].eq(class_label)
                & ranking["representative_candidate"]
            ].sort_values("representative_selection_score", ascending=False)
        chosen_indices: list[int] = []
        used_analyzers: set[str] = set()
        for region in REGION_ORDER:
            region_pool = pool.loc[pool["region_call"].eq(region)]
            for index, row in region_pool.iterrows():
                analyzer = str(row["analyzer_path"])
                if analyzer not in used_analyzers:
                    chosen_indices.append(index)
                    used_analyzers.add(analyzer)
                    break
        for index, row in pool.iterrows():
            if len(chosen_indices) >= 3:
                break
            if index in chosen_indices:
                continue
            analyzer = str(row["analyzer_path"])
            if analyzer in used_analyzers:
                continue
            chosen_indices.append(index)
            used_analyzers.add(analyzer)
        for index, row in pool.iterrows():
            if len(chosen_indices) >= 3:
                break
            if index not in chosen_indices:
                chosen_indices.append(index)
        chosen = ranking.loc[chosen_indices].sort_values(
            "representative_selection_score", ascending=False
        )
        for order, (_, row) in enumerate(chosen.iterrows(), start=1):
            row = row.copy()
            row["representative_order_within_class"] = order
            selected_rows.append(row)
    selection = pd.DataFrame(selected_rows).sort_values(
        ["rs_fs_class", "representative_order_within_class"]
    )
    ranking["selected_for_figure"] = ranking["unit_key"].isin(selection["unit_key"])
    return ranking, selection


def _load_representative_assets(selection: pd.DataFrame) -> list[dict[str, object]]:
    from types import SimpleNamespace

    import spikeinterface.full as si
    import scripts.plot_spatial_isolation_1x2_panels as hybrid

    render_args = SimpleNamespace(
        highlight_channels_per_unit=8,
        footprint_threshold=0.12,
        snippet_cloud_max=100,
        amplitude_max_points=500,
        correlogram_window_ms=80.0,
        correlogram_bin_ms=2.0,
    )
    cache: dict[str, object] = {}
    assets: list[dict[str, object]] = []
    for metadata in selection.to_dict("records"):
        bundle = hybrid.get_bundle(si, cache, str(metadata["analyzer_path"]))
        sorting_unit_id = hybrid.unit_id_for_sorting(metadata["unit_id"], bundle)
        unit_index = bundle.unit_index.get(str(sorting_unit_id))
        if unit_index is None:
            raise ValueError(f"Representative unit missing from analyzer: {metadata['unit_key']}")
        unit_row = hybrid.unit_render_row(
            unit_id=sorting_unit_id,
            unit_idx=int(unit_index),
            bundle=bundle,
            unit_label=metadata["unit_id"],
            spike_count=int(metadata["source_spike_count"]),
            ks_label="good",
            contam_pct=metadata["source_ContamPct"],
        )
        local_channels = hybrid.local_channel_indices(unit_row, bundle, render_args)
        probability = hybrid.autocorrelogram_probability(unit_row, bundle, render_args)
        snippets, snippet_times_min = hybrid.sampled_best_channel_snippets(
            unit_row, bundle, render_args
        )
        assets.append(
            {
                "metadata": metadata,
                "bundle": bundle,
                "unit_row": unit_row,
                "local_channels": local_channels,
                "probability": probability,
                "snippets": snippets,
                "snippet_times_min": snippet_times_min,
                "render_args": render_args,
                "recording_minutes": float(
                    bundle.analyzer.recording.get_num_frames()
                    / bundle.sampling_frequency_hz
                    / 60.0
                ),
            }
        )
    return assets


def _representative_source_tables(
    assets: list[dict[str, object]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    import scripts.plot_spatial_isolation_1x2_panels as hybrid

    spatial_rows: list[dict[str, object]] = []
    acg_rows: list[dict[str, object]] = []
    amplitude_rows: list[dict[str, object]] = []
    for asset in assets:
        metadata = asset["metadata"]
        bundle = asset["bundle"]
        unit_row = asset["unit_row"]
        template = bundle.templates[int(unit_row["unit_index"])]
        best = int(unit_row["best_channel_index_rendered"])
        scale = max(float(np.ptp(template[:, best])), 1e-9)
        time_ms = hybrid.template_time_ms(bundle)
        for channel_index in asset["local_channels"]:
            waveform = hybrid.baseline(template[:, int(channel_index)]) / scale
            location = bundle.channel_locations[int(channel_index), :2]
            for sample_time, value in zip(time_ms, waveform, strict=True):
                spatial_rows.append(
                    {
                        "unit_key": metadata["unit_key"],
                        "rs_fs_class": metadata["rs_fs_class"],
                        "representative_order_within_class": metadata[
                            "representative_order_within_class"
                        ],
                        "channel_index": int(channel_index),
                        "channel_x_um": float(location[0]),
                        "channel_y_um": float(location[1]),
                        "is_best_channel": int(channel_index) == best,
                        "time_ms": float(sample_time),
                        "waveform_normalized_by_best_channel_ptp": float(value),
                    }
                )
        probability = asset["probability"]
        for lag, count, prob in zip(
            probability["bins"], probability["counts"], probability["probability"], strict=True
        ):
            acg_rows.append(
                {
                    "unit_key": metadata["unit_key"],
                    "rs_fs_class": metadata["rs_fs_class"],
                    "representative_order_within_class": metadata[
                        "representative_order_within_class"
                    ],
                    "lag_ms": float(lag),
                    "count": float(count),
                    "probability": float(prob) if np.isfinite(prob) else np.nan,
                    "p_abs_lag_le_2ms": float(probability["p_refractory"]),
                }
            )
        snippets = np.asarray(asset["snippets"], dtype=float)
        snippet_times = np.asarray(asset["snippet_times_min"], dtype=float)
        amplitudes = np.ptp(snippets, axis=1) if snippets.size else np.asarray([], dtype=float)
        for time_min, amplitude in zip(snippet_times, amplitudes, strict=True):
            amplitude_rows.append(
                {
                    "unit_key": metadata["unit_key"],
                    "rs_fs_class": metadata["rs_fs_class"],
                    "representative_order_within_class": metadata[
                        "representative_order_within_class"
                    ],
                    "recording_time_min": float(time_min),
                    "sampled_spike_ptp_uV": float(amplitude),
                }
            )
    return pd.DataFrame(spatial_rows), pd.DataFrame(acg_rows), pd.DataFrame(amplitude_rows)


def _panel_d_specs() -> list[tuple[str, str, str, str]]:
    return [
        ("D1", "mean_unit_firing_rate_hz", "Firing rate", "Mean firing rate\n(Hz)"),
        ("D2", "mean_unit_burst_rate_per_min", "Burst rate", "Burst rate\n(bursts/min)"),
        (
            "D3",
            "mean_unit_firing_rate_within_bursts_hz",
            "MFR/Burst",
            "MFR/Burst\n(Hz)",
        ),
        ("D4", "mean_unit_burst_duration_ms", "Burst duration", "Burst duration\n(ms)"),
        (
            "D5",
            "mean_unit_interburst_interval_s",
            "Inter-burst interval",
            "Inter-burst interval\n(s)",
        ),
        ("D6", "mean_unit_spikes_per_burst", "Spikes/burst", "Mean spikes\nper burst"),
        (
            "D7",
            "maximum_spikes_in_any_sua_burst",
            "Maximum burst size",
            "Maximum spikes\nin a burst",
        ),
    ]


def _panel_d_source_data(
    wells: pd.DataFrame, specs: list[tuple[str, str, str, str]]
) -> pd.DataFrame:
    id_columns = [
        "recording_well_id",
        "recording",
        "well",
        "region_call",
        "raw_variant",
        "sua_unit_count",
        "inverse_isi_gaussian_eligible_sua_unit_count",
    ]
    rows: list[dict[str, object]] = []
    for panel, metric, title, ylabel in specs:
        for _, row in wells.iterrows():
            rows.append(
                {column: row[column] for column in id_columns}
                | {
                    "panel": panel,
                    "metric": metric,
                    "panel_title": title,
                    "y_label": ylabel.replace("\n", " "),
                    "value": row[metric],
                }
            )
    return pd.DataFrame(rows)


def _plot_unified_figure(
    plt,
    Line2D,
    inset_axes,
    units: pd.DataFrame,
    traces: pd.DataFrame,
    waveform_summary: pd.DataFrame,
    representative_assets: list[dict[str, object]],
    wells: pd.DataFrame,
    panel_d_specs: list[tuple[str, str, str, str]],
    output_base: Path,
    export_formats: str,
    fs_cutoff_ms: float,
) -> list[Path]:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 7.0,
            "axes.titlesize": 8.0,
            "axes.labelsize": 7.0,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "axes.linewidth": 0.7,
            "xtick.major.width": 0.7,
            "ytick.major.width": 0.7,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    fig = plt.figure(figsize=(16.0, 10.8), facecolor="white")
    outer = fig.add_gridspec(2, 1, height_ratios=[1.85, 0.82], hspace=0.28)
    top = outer[0].subgridspec(
        2, 4, width_ratios=[1.45, 1.0, 1.0, 1.0], hspace=0.30, wspace=0.24
    )
    ax_a_features = fig.add_subplot(top[:, 0], projection="3d")
    representative_axes: dict[str, list[tuple[object, object, object]]] = {"FS": [], "RS": []}
    for row_index, class_label in enumerate(CLASS_ORDER):
        for column_index in range(3):
            card = top[row_index, column_index + 1].subgridspec(
                3, 1, height_ratios=[1.22, 0.52, 0.58], hspace=0.13
            )
            representative_axes[class_label].append(
                (
                    fig.add_subplot(card[0]),
                    fig.add_subplot(card[1]),
                    fig.add_subplot(card[2]),
                )
            )
    bottom = outer[1].subgridspec(1, 7, wspace=0.58)
    axes_d = [fig.add_subplot(bottom[index]) for index in range(7)]

    _plot_feature_space_3d(ax_a_features, units, fs_cutoff_ms)
    landmark_ax = ax_a_features.inset_axes([0.56, 0.72, 0.36, 0.18])
    _plot_smoothed_landmark_inset(landmark_ax, traces)
    _plot_representative_cards(representative_axes, representative_assets)
    _plot_activity_strip(axes_d, wells, panel_d_specs)

    _panel_letter(ax_a_features, "A", x=-0.08)
    _panel_letter(representative_axes["FS"][0][0], "B", x=-0.18)
    _panel_letter(representative_axes["RS"][0][0], "C", x=-0.18)
    fig.text(0.012, 0.325, "D", fontsize=12, fontweight="bold", va="top")

    class_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markerfacecolor=CLASS_COLORS[label],
            markeredgecolor="none",
            markersize=5,
            label=f"{label} (n={int(units['rs_fs_class'].eq(label).sum())})",
        )
        for label in CLASS_ORDER
    ]
    variant_handles = [
        Line2D(
            [0],
            [0],
            marker=marker,
            linestyle="none",
            markerfacecolor="#777777",
            markeredgecolor="white",
            markersize=5,
            label={
                "primary_raw": "Primary",
                "filter_200Hz-3kHz": "200 Hz-3 kHz",
                "broadband_processor_raw": "Broadband processor",
            }[variant],
        )
        for variant, marker in VARIANT_MARKERS.items()
    ]
    mean_handle = Line2D(
        [0],
        [0],
        marker="D",
        linestyle="none",
        markerfacecolor="white",
        markeredgecolor="black",
        markersize=5,
        label="Mean ± SEM",
    )
    size_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markerfacecolor="#A0A0A0",
            markeredgecolor="white",
            markersize=np.sqrt(_p99_marker_size(value)),
            label=f"P99.9 {value:g} Hz",
        )
        for value in [10.0, 20.0, 30.0]
    ]
    fig.legend(
        handles=class_handles + size_handles + variant_handles + [mean_handle],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.006),
        ncol=9,
        frameon=False,
        fontsize=7,
        handletextpad=0.4,
        columnspacing=1.2,
    )
    fig.subplots_adjust(left=0.045, right=0.995, top=0.982, bottom=0.075)

    output_paths: list[Path] = []
    for suffix in [part.strip().lower() for part in export_formats.split(",") if part.strip()]:
        path = output_base.with_suffix(f".{suffix}")
        kwargs: dict[str, object] = {
            "bbox_inches": "tight",
            "facecolor": "white",
            "transparent": False,
        }
        if suffix == "png":
            kwargs["dpi"] = 600
        fig.savefig(path, **kwargs)
        output_paths.append(path)
    plt.close(fig)
    return output_paths


def _plot_feature_schematic(ax, waveform_summary: pd.DataFrame) -> None:
    summary = waveform_summary.loc[
        waveform_summary["rs_fs_class"].eq("RS")
        & waveform_summary["representation"].eq("trough_normalized")
    ].sort_values("time_ms")
    time = summary["time_ms"].to_numpy(float)
    wave = summary["mean"].to_numpy(float)
    ax.plot(time, wave, color="#303030", lw=1.5)
    trough_index = int(np.nanargmin(wave))
    pre_index = int(np.nanargmax(wave[: trough_index + 1]))
    post_index = trough_index + int(np.nanargmax(wave[trough_index:]))
    points = [pre_index, trough_index, post_index]
    ax.scatter(time[points], wave[points], s=14, color="#303030", zorder=4)
    ttp_arrow_y = wave[trough_index] + 0.08
    ax.annotate(
        "",
        xy=(time[post_index], ttp_arrow_y),
        xytext=(time[trough_index], ttp_arrow_y),
        arrowprops=dict(arrowstyle="<->", color=CLASS_COLORS["RS"], lw=1.0),
    )
    ax.text(
        (time[post_index] + time[trough_index]) / 2,
        ttp_arrow_y + 0.04,
        "Trough-to-peak",
        ha="center",
        va="bottom",
        color=CLASS_COLORS["RS"],
        fontsize=6.5,
    )
    ax.plot(
        [time[trough_index], time[post_index]],
        [wave[trough_index], wave[post_index]],
        color=CLASS_COLORS["FS"],
        lw=1.2,
        ls="--",
    )
    ax.text(
        time[post_index] + 0.04,
        (wave[trough_index] + wave[post_index]) / 2,
        "Repolarization\nslope",
        color=CLASS_COLORS["FS"],
        fontsize=6.2,
        va="center",
    )
    ax.annotate(
        "Pre/post amplitude\nasymmetry",
        xy=(time[pre_index], wave[pre_index]),
        xytext=(time.min() + 0.05, 0.30),
        fontsize=6.2,
        arrowprops=dict(arrowstyle="-", color="#555555", lw=0.8),
    )
    ax.set_title("Waveform features", loc="left", fontweight="bold")
    ax.set_xlabel("Time from trough (ms)")
    ax.set_ylabel("Normalized amplitude")
    ax.set_xlim(-0.85, 1.55)
    _clean_axis(ax)


def _p99_marker_size(value_hz: float) -> float:
    if not np.isfinite(value_hz):
        return 10.0
    return float(10.0 + 1.7 * np.clip(value_hz, 0.0, 45.0))


def _plot_feature_space_3d(ax, units: pd.DataFrame, fs_cutoff_ms: float) -> None:
    complete = units[
        [
            "feature_ttp_ms",
            "feature_repolarization_time_ms",
            "feature_spike_half_width_ms",
        ]
    ].notna().all(axis=1)
    plotted = units.loc[complete].copy()
    for class_label in CLASS_ORDER:
        subset = plotted.loc[plotted["rs_fs_class"].eq(class_label)]
        sizes = [
            _p99_marker_size(value)
            for value in pd.to_numeric(
                subset["inverse_isi_gaussian_temporal_p99_9_hz"], errors="coerce"
            )
        ]
        ax.scatter(
            subset["feature_ttp_ms"],
            subset["feature_repolarization_time_ms"],
            subset["feature_spike_half_width_ms"],
            s=sizes,
            color=CLASS_COLORS[class_label],
            alpha=0.68,
            edgecolor="white",
            linewidth=0.35,
            depthshade=False,
        )
    y_limits = (
        float(plotted["feature_repolarization_time_ms"].min()),
        float(plotted["feature_repolarization_time_ms"].quantile(0.98)),
    )
    z_limits = (
        float(plotted["feature_spike_half_width_ms"].min()),
        float(plotted["feature_spike_half_width_ms"].quantile(0.98)),
    )
    yy, zz = np.meshgrid(
        np.linspace(y_limits[0], y_limits[1], 2),
        np.linspace(z_limits[0], z_limits[1], 2),
    )
    xx = np.full_like(yy, fs_cutoff_ms)
    ax.plot_surface(xx, yy, zz, color="#777777", alpha=0.09, shade=False)
    ax.set_title(
        f"Aligned three-feature waveform space (n={len(plotted)})",
        loc="left",
        fontweight="bold",
        pad=4,
    )
    ax.set_xlabel("Trough-to-peak (ms)", labelpad=5)
    ax.set_ylabel("Repolarization time (ms)", labelpad=6)
    ax.set_zlabel("Spike half-width (ms)", labelpad=5)
    ax.set_ylim(y_limits)
    ax.set_zlim(z_limits)
    ax.view_init(elev=22, azim=-56)
    ax.set_box_aspect((1.20, 0.95, 0.75))
    ax.tick_params(labelsize=6, pad=0)
    ax.grid(True, alpha=0.22)
    ax.text2D(
        0.03,
        0.03,
        "Point size: temporal P99.9 smoothed inverse-ISI firing rate",
        transform=ax.transAxes,
        fontsize=5.8,
        color="#555555",
    )


def _plot_smoothed_landmark_inset(ax, traces: pd.DataFrame) -> None:
    from scipy.signal import savgol_filter

    pooled = traces.groupby("time_ms", as_index=False)["trough_normalized_waveform"].mean()
    pooled = pooled.sort_values("time_ms")
    time = pooled["time_ms"].to_numpy(float)
    waveform = pooled["trough_normalized_waveform"].to_numpy(float)
    window = min(7, waveform.size if waveform.size % 2 else waveform.size - 1)
    smooth = savgol_filter(waveform, window_length=max(window, 3), polyorder=2)
    trough = int(np.nanargmin(smooth))
    post_indices = np.flatnonzero(time > time[trough])
    peak = int(post_indices[np.nanargmax(smooth[post_indices])]) if post_indices.size else trough
    ax.plot(time, smooth, color="#222222", lw=1.0)
    ax.scatter(
        time[[trough, peak]],
        smooth[[trough, peak]],
        s=14,
        color="#222222",
        edgecolor="white",
        linewidth=0.45,
        zorder=3,
    )
    ax.set_xlim(-0.55, 1.15)
    ax.set_axis_off()


def _plot_representative_cards(
    axes_by_class: dict[str, list[tuple[object, object, object]]],
    assets: list[dict[str, object]],
) -> None:
    for class_label in CLASS_ORDER:
        class_assets = sorted(
            [asset for asset in assets if asset["metadata"]["rs_fs_class"] == class_label],
            key=lambda asset: asset["metadata"]["representative_order_within_class"],
        )
        for index, (axes, asset) in enumerate(
            zip(axes_by_class[class_label], class_assets, strict=True), start=1
        ):
            _plot_representative_spatial(axes[0], asset, class_label, index)
            _plot_representative_acg(axes[1], asset, class_label, show_ylabel=index == 1)
            _plot_representative_stability(
                axes[2], asset, class_label, show_ylabel=index == 1
            )


def _plot_representative_spatial(ax, asset, class_label: str, order: int) -> None:
    import scripts.plot_spatial_isolation_1x2_panels as hybrid

    metadata = asset["metadata"]
    bundle = asset["bundle"]
    unit_row = asset["unit_row"]
    local_channels = asset["local_channels"]
    template = bundle.templates[int(unit_row["unit_index"])]
    best = int(unit_row["best_channel_index_rendered"])
    scale = max(float(np.ptp(template[:, best])), 1e-9)
    locations = bundle.channel_locations[:, :2]
    dx, dy = hybrid.geometry_spacing(locations)
    local_time, y_scale = hybrid.waveform_grid_axes(
        bundle, dx, dy, x_multiplier=1.0, y_multiplier=1.30
    )
    color = CLASS_COLORS[class_label]
    ax.scatter(
        locations[local_channels, 0],
        locations[local_channels, 1],
        s=5,
        color="#DDDDDD",
        zorder=1,
    )
    for channel_index in local_channels:
        waveform = hybrid.baseline(template[:, int(channel_index)]) / scale
        x0, y0 = locations[int(channel_index)]
        ax.plot(
            x0 + local_time,
            y0 + waveform * y_scale,
            color=color,
            lw=1.35 if int(channel_index) == best else 0.75,
            alpha=1.0 if int(channel_index) == best else 0.72,
            zorder=3,
        )
    center = locations[best]
    ax.scatter(
        [center[0]],
        [center[1]],
        s=38,
        facecolor="none",
        edgecolor=color,
        linewidth=1.1,
        zorder=5,
    )
    local_xy = locations[local_channels]
    ax.set_xlim(local_xy[:, 0].min() - 0.55 * dx, local_xy[:, 0].max() + 0.55 * dx)
    ax.set_ylim(local_xy[:, 1].min() - 0.55 * dy, local_xy[:, 1].max() + 0.55 * dy)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(
        f"{class_label}{order}  {str(metadata['region_call']).title()} {metadata['well']} · "
        f"u{metadata['unit_id']} · TTP {metadata['feature_ttp_ms']:.2f} ms",
        loc="left",
        fontsize=7.0,
        fontweight="bold",
        pad=2,
    )


def _plot_representative_acg(ax, asset, class_label: str, *, show_ylabel: bool) -> None:
    import scripts.plot_spatial_isolation_1x2_panels as hybrid

    probability = asset["probability"]
    bins = np.asarray(probability["bins"], dtype=float)
    values = np.asarray(probability["probability"], dtype=float)
    mask = np.asarray(probability["display_mask"], dtype=bool)
    x = bins[mask]
    y = hybrid.smooth_probability_for_display(np.nan_to_num(values[mask], nan=0.0))
    color = CLASS_COLORS[class_label]
    ax.fill_between(x, 0, y, color=color, alpha=0.16, linewidth=0)
    ax.plot(x, y, color=color, lw=0.9)
    ax.axvline(-2, color="#777777", lw=0.55, ls="--")
    ax.axvline(2, color="#777777", lw=0.55, ls="--")
    ax.set_xlim(-50, 50)
    ax.set_xticks([-40, 0, 40])
    ax.set_title(
        f"ACG  P(|lag|≤2 ms)={float(probability['p_refractory']):.3f}",
        loc="left",
        fontsize=5.8,
        pad=1,
    )
    if show_ylabel:
        ax.set_ylabel("Probability", fontsize=5.5)
    else:
        ax.set_yticklabels([])
    ax.tick_params(labelsize=5, length=1.8, pad=1)
    ax.spines[["top", "right"]].set_visible(False)


def _plot_representative_stability(ax, asset, class_label: str, *, show_ylabel: bool) -> None:
    import scripts.plot_spatial_isolation_1x2_panels as hybrid

    snippets = np.asarray(asset["snippets"], dtype=float)
    times = np.asarray(asset["snippet_times_min"], dtype=float)
    color = CLASS_COLORS[class_label]
    if snippets.size:
        amplitudes = np.ptp(snippets, axis=1)
        ax.scatter(times, amplitudes, s=4, color=color, alpha=0.18, linewidth=0)
        med_x, med_y = hybrid.binned_median(
            times, amplitudes, float(asset["recording_minutes"])
        )
        if med_x.size:
            ax.plot(med_x, med_y, color=color, lw=0.85)
    ax.set_xlim(0, max(float(asset["recording_minutes"]), 1e-6))
    ax.set_title("Amplitude stability", loc="left", fontsize=5.8, pad=1)
    ax.set_xlabel("Time (min)", fontsize=5.5, labelpad=1)
    if show_ylabel:
        ax.set_ylabel("PTP (µV)", fontsize=5.5)
    else:
        ax.set_yticklabels([])
    ax.tick_params(labelsize=5, length=1.8, pad=1)
    ax.spines[["top", "right"]].set_visible(False)


def _plot_feature_space(ax, units: pd.DataFrame, fs_cutoff_ms: float) -> None:
    half_width = units["feature_spike_half_width_ms"].to_numpy(float)
    ranks = pd.Series(half_width).rank(pct=True).to_numpy(float)
    sizes = 8.0 + 26.0 * ranks
    for class_label in CLASS_ORDER:
        mask = units["rs_fs_class"].eq(class_label).to_numpy()
        ax.scatter(
            units.loc[mask, "feature_ttp_ms"],
            units.loc[mask, "feature_repolarization_time_ms"],
            s=sizes[mask],
            color=CLASS_COLORS[class_label],
            alpha=0.62,
            edgecolor="white",
            linewidth=0.35,
        )
    ax.axvline(fs_cutoff_ms, color="#333333", lw=0.9, ls="--")
    ax.text(
        fs_cutoff_ms + 0.015,
        0.98,
        "0.50 ms",
        transform=ax.get_xaxis_transform(),
        va="top",
        fontsize=6.2,
    )
    complete_count = int(
        units[["feature_ttp_ms", "feature_repolarization_time_ms"]]
        .notna()
        .all(axis=1)
        .sum()
    )
    ax.set_title(
        f"Aligned waveform feature space (n={complete_count})",
        loc="left",
        fontweight="bold",
    )
    ax.set_xlabel("Trough-to-peak (ms)")
    ax.set_ylabel("Repolarization time (ms)")
    ax.text(
        0.98,
        0.02,
        "Point size ∝ spike half-width",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=5.8,
        color="#555555",
    )
    _clean_axis(ax)


def _plot_mean_normalized_waveforms(ax, summary: pd.DataFrame) -> None:
    for class_label in CLASS_ORDER:
        normalized = summary.loc[
            summary["rs_fs_class"].eq(class_label)
            & summary["representation"].eq("trough_normalized")
        ].sort_values("time_ms")
        ax.plot(
            normalized["time_ms"],
            normalized["mean"],
            color=CLASS_COLORS[class_label],
            lw=1.6,
        )
    ax.axvline(0, color="#999999", lw=0.6, ls=":")
    ax.set_title("Mean normalized waveform", loc="left", fontweight="bold")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Normalized amplitude")
    ax.set_xlim(-0.75, 1.00)
    _clean_axis(ax)


def _plot_ttp_distribution(ax, inset_axes, units, waveform_summary, fs_cutoff_ms: float) -> None:
    bins = np.arange(-0.04, max(2.04, units["feature_ttp_ms"].max() + 0.12), 0.08)
    for class_label in CLASS_ORDER:
        values = units.loc[units["rs_fs_class"].eq(class_label), "feature_ttp_ms"].to_numpy(float)
        ax.hist(
            values,
            bins=bins,
            color=CLASS_COLORS[class_label],
            alpha=0.72,
            edgecolor="white",
            linewidth=0.35,
        )
    ax.axvline(fs_cutoff_ms, color="#222222", lw=1.0, ls="--")
    ax.text(
        fs_cutoff_ms + 0.025,
        0.97,
        "FS ≤ 0.50 ms",
        transform=ax.get_xaxis_transform(),
        va="top",
        fontsize=6.2,
    )
    ax.set_title("Aligned trough-to-peak distribution", loc="left", fontweight="bold")
    ax.set_xlabel("Trough-to-peak duration (ms)")
    ax.set_ylabel("Units")
    _clean_axis(ax)

    inset = inset_axes(ax, width="46%", height="35%", loc="upper right", borderpad=1.1)
    rs = waveform_summary.loc[
        waveform_summary["rs_fs_class"].eq("RS")
        & waveform_summary["representation"].eq("trough_normalized")
    ].sort_values("time_ms")
    time = rs["time_ms"].to_numpy(float)
    wave = rs["mean"].to_numpy(float)
    trough = int(np.nanargmin(wave))
    peak = trough + int(np.nanargmax(wave[trough:]))
    inset.plot(time, wave, color=CLASS_COLORS["RS"], lw=1.0)
    inset.scatter(time[[trough, peak]], wave[[trough, peak]], s=7, color="#222222", zorder=3)
    inset.annotate(
        "",
        xy=(time[peak], wave[trough] - 0.10),
        xytext=(time[trough], wave[trough] - 0.10),
        arrowprops=dict(arrowstyle="<->", lw=0.7, color="#222222"),
    )
    inset.text(
        (time[trough] + time[peak]) / 2,
        wave[trough] - 0.20,
        "TTP",
        ha="center",
        va="top",
        fontsize=5.5,
    )
    inset.set_xlim(-0.35, 1.35)
    inset.set_xticks([])
    inset.set_yticks([])
    inset.spines[["top", "right"]].set_visible(False)


def _plot_activity_strip(axes, wells, specs) -> None:
    rng = np.random.default_rng(20260710)
    positions = {"dorsal": 0.0, "ventral": 0.30}
    for ax, (panel, metric, title, ylabel) in zip(axes, specs, strict=True):
        for region in REGION_ORDER:
            subset = wells.loc[wells["region_call"].eq(region)].copy()
            values = pd.to_numeric(subset[metric], errors="coerce")
            valid = values.notna()
            plotted = subset.loc[valid]
            plotted_values = values.loc[valid].to_numpy(float)
            jitter = rng.uniform(-0.045, 0.045, len(plotted))
            for point_index, (_, row) in enumerate(plotted.iterrows()):
                ax.scatter(
                    positions[region] + jitter[point_index],
                    float(row[metric]),
                    s=17,
                    marker=VARIANT_MARKERS.get(str(row["raw_variant"]), "D"),
                    color=REGION_COLORS[region],
                    edgecolor="white",
                    linewidth=0.35,
                    alpha=0.78,
                    zorder=3,
                )
            if plotted_values.size:
                ax.errorbar(
                    positions[region],
                    float(np.mean(plotted_values)),
                    yerr=_sem(plotted_values),
                    fmt="D",
                    ms=3.6,
                    color="black",
                    markerfacecolor="white",
                    markeredgewidth=0.8,
                    capsize=2.5,
                    lw=0.8,
                    zorder=5,
                )
        counts = [
            int(pd.to_numeric(wells.loc[wells["region_call"].eq(region), metric], errors="coerce").notna().sum())
            for region in REGION_ORDER
        ]
        ax.set_xticks(
            [positions["dorsal"], positions["ventral"]],
            [f"Dorsal\nn={counts[0]}", f"Ventral\nn={counts[1]}"],
        )
        ax.set_xlim(-0.18, 0.48)
        ax.set_title(f"{panel}  {title}", loc="left", fontweight="bold", pad=4)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", color="#DDDDDD", lw=0.55, alpha=0.8)
        _clean_axis(ax)


def _panel_letter(ax, label: str, *, x: float) -> None:
    method = getattr(ax, "text2D", ax.text)
    method(x, 1.08, label, transform=ax.transAxes, fontsize=12, fontweight="bold", va="top")


def _clean_axis(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(direction="out", length=2.6, pad=2)


def _sem(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return float("nan")
    return float(np.std(values, ddof=1) / np.sqrt(values.size))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
