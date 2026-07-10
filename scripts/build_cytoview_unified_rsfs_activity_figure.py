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
LUMOS_ALIGNMENT_DIR = JOB_ROOT / "waveform_alignment_feature_audit_20260709"
LUMOS_FIRING_PATH = JOB_ROOT / "lumos_gui_ready_unsorted_unit_firing_rates_20260709.csv"
STEM = "cytoview_unified_rsfs_activity_figure_20260710"

CLASS_ORDER = ["FS", "RS"]
CLASS_COLORS = {"FS": "#B8742A", "RS": "#58758E"}
REGION_ORDER = ["dorsal", "ventral"]
REGION_COLORS = {"dorsal": "#6F8477", "ventral": "#C8A05A"}
VARIANT_MARKERS = {
    "primary_raw": "o",
    "filter_200Hz-3kHz": "s",
    "broadband_processor_raw": "^",
}
LOCKED_CYTOVIEW_FS_UNIT_KEYS = [
    # Retained user-selected CytoView gallery FS1 (2026-07-10).
    "step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_5_28_26_h1_134-0150_h1_dorsal_and_ventral_exp17_2(001)_filter_200Hz-3kHz|B1|24",
]
LOCKED_LUMOS_FS_UNIT_KEY = (
    "step1_nonlfp_th5_20260708_2_25_2026_129-8447_test(000)_broadband_processor_raw|F8|5"
)
LOCKED_FS_UNIT_KEYS = [*LOCKED_CYTOVIEW_FS_UNIT_KEYS, LOCKED_LUMOS_FS_UNIT_KEY]
LOCKED_RS_UNIT_KEYS = [
    # User-selected existing RS1 and RS3, in that order (2026-07-10).
    "step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_5_28_26_h1_134-0150_h1_dorsal_and_ventral_exp17_2(001)_filter_200Hz-3kHz|B2|9",
    "step1_nonlfp_th5_20260708_incoming_manny4tbum_20260706_5_28_26_h1_134-0150_h1_dorsal_and_ventral_exp17_2(001)_filter_200Hz-3kHz|B3|29",
]

SPATIAL_WAVEFORM_DISPLAY_GAIN = 3.2


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
    representative_selection = pd.concat(
        [representative_selection, pd.DataFrame([_lumos_fs_representative_metadata()])],
        ignore_index=True,
        sort=False,
    ).sort_values(["rs_fs_class", "representative_order_within_class"])
    fs_gallery_selection = representative_ranking.loc[
        representative_ranking["rs_fs_class"].eq("FS")
        & representative_ranking["representative_candidate"]
    ].sort_values("representative_selection_score", ascending=False).copy()
    fs_gallery_selection["representative_order_within_class"] = np.arange(
        1, len(fs_gallery_selection) + 1
    )
    fs_gallery_selection["representative_display_id"] = [
        f"FS{rank}" for rank in fs_gallery_selection["representative_order_within_class"]
    ]
    asset_selection = pd.concat(
        [
            fs_gallery_selection,
            representative_selection,
        ],
        ignore_index=True,
    ).drop_duplicates("unit_key")
    all_representative_assets = _load_representative_assets(asset_selection)
    selected_keys = set(representative_selection["unit_key"])
    selected_metadata = {
        row["unit_key"]: row for row in representative_selection.to_dict("records")
    }
    representative_assets = []
    for asset in all_representative_assets:
        unit_key = asset["metadata"]["unit_key"]
        if unit_key in selected_keys:
            updated = dict(asset)
            updated["metadata"] = selected_metadata[unit_key]
            representative_assets.append(updated)
    fs_gallery_keys = set(fs_gallery_selection["unit_key"])
    fs_gallery_assets = [
        asset for asset in all_representative_assets if asset["metadata"]["unit_key"] in fs_gallery_keys
    ]
    representative_spatial_source, representative_acg_source, representative_amplitude_source = (
        _representative_source_tables(representative_assets)
    )
    fs_gallery_spatial_source, fs_gallery_acg_source, fs_gallery_amplitude_source = (
        _representative_source_tables(fs_gallery_assets)
    )
    panel_f_specs = _panel_f_specs()
    panel_f_source = _panel_activity_source_data(wells, panel_f_specs)
    regional_unit_source = _regional_classified_unit_firing_source(units)

    feature_path = output_dir / f"{STEM}_panel_A_aligned_features.csv"
    trace_output_path = output_dir / f"{STEM}_panel_A_landmark_waveform_traces.csv.gz"
    waveform_summary_path = output_dir / f"{STEM}_panel_A_landmark_waveform_summary.csv"
    feature_audit_path = output_dir / f"{STEM}_panel_A_feature_selection_audit.csv"
    classification_summary_path = output_dir / f"{STEM}_panel_A_region_classification_summary.csv"
    representative_ranking_path = output_dir / f"{STEM}_panels_B_C_representative_ranking.csv"
    representative_selection_path = output_dir / f"{STEM}_panels_B_C_representative_selection.csv"
    representative_spatial_path = output_dir / f"{STEM}_panels_B_C_spatial_waveforms.csv.gz"
    representative_acg_path = output_dir / f"{STEM}_panels_B_C_autocorrelograms.csv"
    representative_amplitude_path = output_dir / f"{STEM}_panels_B_C_amplitude_stability.csv.gz"
    fs_gallery_selection_path = output_dir / f"{STEM}_FS_candidate_gallery_selection.csv"
    fs_gallery_spatial_path = output_dir / f"{STEM}_FS_candidate_gallery_spatial_waveforms.csv.gz"
    fs_gallery_acg_path = output_dir / f"{STEM}_FS_candidate_gallery_autocorrelograms.csv"
    fs_gallery_amplitude_path = output_dir / f"{STEM}_FS_candidate_gallery_amplitude_stability.csv.gz"
    regional_unit_path = output_dir / f"{STEM}_panels_D_E_regional_classified_unit_firing_rates.csv"
    panel_f_path = output_dir / f"{STEM}_panel_F_regional_spontaneous_network_activity.csv"
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
    panel_a_classification_summary = _panel_a_region_classification_summary(units)
    panel_a_classification_summary.to_csv(classification_summary_path, index=False)
    representative_ranking.to_csv(representative_ranking_path, index=False)
    representative_selection.to_csv(representative_selection_path, index=False)
    representative_spatial_source.to_csv(
        representative_spatial_path, index=False, compression="gzip"
    )
    representative_acg_source.to_csv(representative_acg_path, index=False)
    representative_amplitude_source.to_csv(
        representative_amplitude_path, index=False, compression="gzip"
    )
    fs_gallery_selection.to_csv(fs_gallery_selection_path, index=False)
    fs_gallery_spatial_source.to_csv(fs_gallery_spatial_path, index=False, compression="gzip")
    fs_gallery_acg_source.to_csv(fs_gallery_acg_path, index=False)
    fs_gallery_amplitude_source.to_csv(
        fs_gallery_amplitude_path, index=False, compression="gzip"
    )
    panel_f_source.to_csv(panel_f_path, index=False)
    regional_unit_source.to_csv(regional_unit_path, index=False)

    figure_paths = _plot_unified_figure(
        plt,
        Line2D,
        inset_axes,
        units,
        traces,
        waveform_summary,
        representative_assets,
        wells,
        panel_f_specs,
        output_dir / STEM,
        args.export_formats,
        args.fs_cutoff_ms,
    )
    fs_gallery_paths = _plot_fs_candidate_gallery(
        plt,
        fs_gallery_assets,
        output_dir / f"{STEM}_FS_candidate_gallery",
        args.export_formats,
    )

    activity_provenance = json.loads(activity_provenance_path.read_text(encoding="utf-8"))
    excluded = pd.read_csv(exclusion_path)
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "figure_role": (
            "unified supplementary figure; panel A classification, panels B-C representative QC, "
            "panels D-E regional classified-unit firing, panel F organoid-level spontaneous network activity"
        ),
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
                "large 3D x=TTP/y=repolarization time/z=spike half-width scatter with no cutoff plane; "
                "point size=unit temporal P99.9 smoothed inverse-ISI firing rate and color=locked "
                "TTP-cutoff RS/FS class; companion column contains aligned original-amplitude "
                "class means above a minimal horizontal dorsal/ventral RS/FS composition summary"
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
            "visual_axis_policy": (
                "points outside the explicitly displayed scatter-axis limits are omitted before plotting, "
                "not rendered beyond the axes"
            ),
            "view": "elevation 22 degrees, azimuth -46 degrees; 10-degree rotation from prior -56 view",
            "cutoff_plane": False,
            "point_size_explanatory_sentence": False,
            "point_size_key": "compact symbol legend only",
            "classification_summary": (
                "pooled classified-unit percentages and counts by dorsal/ventral region; "
                "descriptive unit summary, not an organoid-level inferential analysis"
            ),
            "waveform_summary": (
                "aligned FS/RS class means at original uV amplitudes; no normalization, SEM shading, "
                "axes, ticks, grid, frame, or display smoothing"
            ),
            "units_with_complete_display_features": int(
                units[["feature_ttp_ms", "feature_repolarization_time_ms", "feature_spike_half_width_ms"]]
                .notna()
                .all(axis=1)
                .sum()
            ),
        },
        "panel_B": {
            "display": "two spatial-footprint-forward KSLabel=good cross-platform FS representative-unit QC cards",
            "selection": (
                "retained CytoView FS1 plus Lumos LFS1 F8 u5; Lumos candidate replaced CytoView FS16 "
                "after matched spatial/ACG/PTP-stability QC"
            ),
            "locked_unit_keys": LOCKED_FS_UNIT_KEYS,
            "card_assets": ["local multichannel footprint", "probability autocorrelogram", "amplitude stability"],
            "probability_acg_display_smoothing": "none",
            "spatial_waveform_uniform_display_gain": SPATIAL_WAVEFORM_DISPLAY_GAIN,
            "card_axis_ticks": "none",
            "best_channel_center_circle": False,
            "population_scope_note": (
                "representative cards are cross-platform; Panel A classification, Panels D-E regional "
                "unit activity, and Panel F network activity remain the locked CytoView population"
            ),
        },
        "panel_C_representative_units": {
            "display": "two spatial-footprint-forward KSLabel=good RS representative-unit QC cards",
            "card_assets": ["local multichannel footprint", "probability autocorrelogram", "amplitude stability"],
            "selection": "user-locked existing representatives RS1 and RS3 in that order",
            "locked_unit_keys": LOCKED_RS_UNIT_KEYS,
            "probability_acg_display_smoothing": "none",
            "spatial_waveform_uniform_display_gain": SPATIAL_WAVEFORM_DISPLAY_GAIN,
            "card_axis_ticks": "none",
            "best_channel_center_circle": False,
        },
        "FS_candidate_gallery": {
            "unit_count": int(len(fs_gallery_selection)),
            "scope": "all retained FS units meeting representative-candidate completeness and >=100 spike rule",
            "figures": [str(path) for path in fs_gallery_paths],
        },
        "panels_D_E_regional_classified_unit_activity": {
            "metric": "legacy whole-recording firing rate for each retained CytoView FS or RS unit",
            "plotting_unit": "one point per classified unit; no regional or well averaging before plotting",
            "overlay": "unit-level group mean +/- SEM",
            "shared_y_axis_hz": [0.0, 13.0],
            "region_colors": REGION_COLORS,
            "counts": {
                f"{class_label}_{region}": {
                    "units": int(len(group)),
                    "recording_well_observations": int(group["recording_well_id"].nunique()),
                }
                for (class_label, region), group in regional_unit_source.groupby(
                    ["rs_fs_class", "region_call"]
                )
            },
        },
        "panel_F": {
            "layout": "single row, one metric per column, compact dorsal/ventral spacing",
            "metrics": [spec[1] for spec in panel_f_specs],
            "F1_choice": "legacy spike-count / recording-duration firing rate only",
            "aggregation": "one point per recording-version/well organoid; regional mean +/- SEM",
            "burst_detection": activity_provenance["burst_detection"],
            "maximum_burst_size_removed": True,
        },
        "outputs": {
            "figures": [str(path) for path in figure_paths],
            "FS_candidate_gallery_figures": [str(path) for path in fs_gallery_paths],
            "panel_A_features": str(feature_path),
            "panel_A_feature_selection_audit": str(feature_audit_path),
            "panel_A_region_classification_summary": str(classification_summary_path),
            "panels_B_C_representative_ranking": str(representative_ranking_path),
            "panels_B_C_representative_selection": str(representative_selection_path),
            "panels_B_C_spatial_waveforms": str(representative_spatial_path),
            "panels_B_C_autocorrelograms": str(representative_acg_path),
            "panels_B_C_amplitude_stability": str(representative_amplitude_path),
            "FS_candidate_gallery_selection": str(fs_gallery_selection_path),
            "FS_candidate_gallery_spatial_waveforms": str(fs_gallery_spatial_path),
            "FS_candidate_gallery_autocorrelograms": str(fs_gallery_acg_path),
            "FS_candidate_gallery_amplitude_stability": str(fs_gallery_amplitude_path),
            "panels_D_E_regional_classified_unit_firing_rates": str(regional_unit_path),
            "panel_A_landmark_traces": str(trace_output_path),
            "panel_A_landmark_summary": str(waveform_summary_path),
            "panel_F_source": str(panel_f_path),
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
    print("FS candidate gallery:")
    for path in fs_gallery_paths:
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
    """Rank eligible units and return the exact user-locked two per class."""
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
    ranking["fs_gallery_rank"] = np.nan
    fs_ranked_indices = ranking.loc[
        ranking["rs_fs_class"].eq("FS") & ranking["representative_candidate"]
    ].sort_values("representative_selection_score", ascending=False).index
    ranking.loc[fs_ranked_indices, "fs_gallery_rank"] = np.arange(
        1, len(fs_ranked_indices) + 1
    )

    selected_rows: list[pd.Series] = []
    by_key = ranking.set_index("unit_key", drop=False)
    locked_by_class = {"FS": LOCKED_CYTOVIEW_FS_UNIT_KEYS, "RS": LOCKED_RS_UNIT_KEYS}
    locked_display_ids = {"FS": ["FS1"], "RS": ["RS1", "RS3"]}
    for class_label in CLASS_ORDER:
        locked_keys = locked_by_class[class_label]
        missing = [unit_key for unit_key in locked_keys if unit_key not in by_key.index]
        if missing:
            raise ValueError(f"Locked {class_label} unit keys missing from ranking: {missing}")
        for order, (unit_key, display_id) in enumerate(
            zip(locked_keys, locked_display_ids[class_label], strict=True), start=1
        ):
            row = by_key.loc[unit_key].copy()
            if row["rs_fs_class"] != class_label:
                raise ValueError(f"Locked {display_id} has class {row['rs_fs_class']}")
            if not bool(row["representative_candidate"]):
                raise ValueError(f"Locked {display_id} is not representative-eligible: {unit_key}")
            row["representative_order_within_class"] = order
            row["representative_display_id"] = display_id
            selected_rows.append(row)
    selection = pd.DataFrame(selected_rows).sort_values(
        ["rs_fs_class", "representative_order_within_class"]
    )
    ranking["selected_for_figure"] = ranking["unit_key"].isin(selection["unit_key"])
    return ranking, selection


def _lumos_fs_representative_metadata() -> dict[str, object]:
    """Return the locked Lumos F8 u5 metadata in the representative-card schema."""
    paired = pd.read_csv(
        LUMOS_ALIGNMENT_DIR / "waveform_alignment_feature_audit_20260709_paired_unit_metrics.csv"
    )
    firing = pd.read_csv(LUMOS_FIRING_PATH)
    merged = paired.merge(
        firing[
            [
                "recording",
                "well",
                "unit_id",
                "duration_s",
                "num_spikes",
                "firing_rate_hz",
                "ContamPct",
            ]
        ],
        on=["recording", "well", "unit_id"],
        how="left",
        validate="one_to_one",
    )
    candidate = merged.loc[merged["unit_key"].eq(LOCKED_LUMOS_FS_UNIT_KEY)]
    if len(candidate) != 1:
        raise ValueError("Locked Lumos FS candidate was not found uniquely")
    row = candidate.iloc[0]
    if row["KSLabel"] != "good" or float(row["after_trough_to_peak_duration_ms"]) > 0.50:
        raise ValueError("Locked Lumos FS candidate no longer satisfies the good/TTP rule")
    return {
        "unit_key": row["unit_key"],
        "recording_well_id": f"{row['recording']}|{row['well']}",
        "organoid_well": "not applicable; Lumos representative QC only",
        "recording": row["recording"],
        "well": row["well"],
        "region_call": "Lumos",
        "region_source": "lumos_48well geometry; not dorsal/ventral biology",
        "region_override_applied": False,
        "plate_id": "129-8447",
        "raw_variant": "broadband_processor_raw",
        "recording_duration_s": float(row["duration_s"]),
        "unit_id": row["unit_id"],
        "KSLabel": "good",
        "analyzer_path": row["analyzer_path"],
        "source_spike_count": int(row["num_spikes"]),
        "source_firing_rate_hz": float(row["firing_rate_hz"]),
        "source_ContamPct": float(row["ContamPct"]),
        "template_ptp_best_channel_uV": float(row["after_template_ptp_best_channel_uV"]),
        "aligned_usable_snippets": int(row["usable_snippets"]),
        "aligned_trough_to_peak_duration_ms": float(row["after_trough_to_peak_duration_ms"]),
        "aligned_waveform_asymmetry": float(row["after_waveform_asymmetry"]),
        "aligned_repolarization_slope_uV_per_ms": float(
            row["after_post_trough_rebound_slope_uV_per_ms"]
        ),
        "aligned_fs_rs_cutoff_ms": 0.50,
        "aligned_fs_rs_class": "FS",
        "rs_fs_class": "FS",
        "feature_ttp_ms": float(row["after_trough_to_peak_duration_ms"]),
        "feature_asymmetry": float(row["after_waveform_asymmetry"]),
        "feature_repolarization_slope_uV_per_ms": float(
            row["after_post_trough_rebound_slope_uV_per_ms"]
        ),
        "feature_repolarization_time_ms": float(row["after_repolarization_time_ms"]),
        "feature_spike_half_width_ms": float(row["after_spike_half_width_ms"]),
        "representative_candidate": True,
        "representative_order_within_class": 2,
        "representative_display_id": "LFS1",
        "representative_selection_provenance": "cross-platform matched-QC replacement for FS16",
    }


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


def _panel_f_specs() -> list[tuple[str, str, str, str]]:
    return [
        ("F1", "mean_unit_firing_rate_hz", "Firing rate", "Mean firing rate (Hz)"),
        ("F2", "mean_unit_burst_rate_per_min", "Burst rate", "Burst rate (bursts/min)"),
        (
            "F3",
            "mean_unit_firing_rate_within_bursts_hz",
            "MFR/Burst",
            "MFR/Burst (Hz)",
        ),
        ("F4", "mean_unit_burst_duration_ms", "Burst duration", "Burst duration (ms)"),
        (
            "F5",
            "mean_unit_interburst_interval_s",
            "Inter-burst interval",
            "Inter-burst interval (s)",
        ),
        ("F6", "mean_unit_spikes_per_burst", "Spikes/burst", "Mean spikes per burst"),
    ]


def _regional_classified_unit_firing_source(units: pd.DataFrame) -> pd.DataFrame:
    """Return one source-data row per retained CytoView classified unit."""
    columns = [
        "unit_key",
        "recording_well_id",
        "organoid_well",
        "recording",
        "well",
        "region_call",
        "raw_variant",
        "unit_id",
        "rs_fs_class",
        "source_spike_count",
        "recording_duration_s",
        "source_firing_rate_hz",
        "aligned_trough_to_peak_duration_ms",
        "template_ptp_best_channel_uV",
    ]
    source = units.loc[units["rs_fs_class"].isin(CLASS_ORDER), columns].copy()
    source = source.rename(columns={"source_firing_rate_hz": "classified_unit_firing_rate_hz"})
    groups = source.groupby(["rs_fs_class", "region_call"])
    source["group_classified_unit_count"] = groups["unit_key"].transform("size")
    source["group_recording_well_observation_count"] = groups["recording_well_id"].transform(
        "nunique"
    )
    source["summary_overlay"] = "unit-level mean +/- SEM; no pre-averaging"
    return source.sort_values(["rs_fs_class", "region_call", "recording_well_id", "unit_id"])


def _panel_activity_source_data(
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


def _panel_a_region_classification_summary(units: pd.DataFrame) -> pd.DataFrame:
    """Return pooled unit counts and percentages for the descriptive A4 panel."""
    counts = (
        units.groupby(["region_call", "rs_fs_class"], observed=False)
        .size()
        .rename("unit_count")
        .reset_index()
    )
    complete_index = pd.MultiIndex.from_product(
        [REGION_ORDER, CLASS_ORDER], names=["region_call", "rs_fs_class"]
    )
    counts = (
        counts.set_index(["region_call", "rs_fs_class"])
        .reindex(complete_index, fill_value=0)
        .reset_index()
    )
    counts["region_total_units"] = counts.groupby("region_call")["unit_count"].transform("sum")
    counts["percent_of_region_units"] = np.where(
        counts["region_total_units"].gt(0),
        100.0 * counts["unit_count"] / counts["region_total_units"],
        np.nan,
    )
    counts["summary_level"] = "pooled classified units; descriptive"
    return counts


def _plot_unified_figure(
    plt,
    Line2D,
    inset_axes,
    units: pd.DataFrame,
    traces: pd.DataFrame,
    waveform_summary: pd.DataFrame,
    representative_assets: list[dict[str, object]],
    wells: pd.DataFrame,
    panel_f_specs: list[tuple[str, str, str, str]],
    output_base: Path,
    export_formats: str,
    fs_cutoff_ms: float,
) -> list[Path]:
    from matplotlib.patches import FancyBboxPatch

    neutral = "#2B2B2B"
    plt.rcParams.update(
        {
            "font.family": "Nimbus Sans",
            "font.sans-serif": ["Nimbus Sans", "Liberation Sans", "DejaVu Sans"],
            "font.size": 7.0,
            "axes.titlesize": 7.6,
            "axes.titleweight": "normal",
            "axes.labelsize": 6.0,
            "xtick.labelsize": 5.3,
            "ytick.labelsize": 5.3,
            "axes.linewidth": 0.7,
            "xtick.major.width": 0.7,
            "ytick.major.width": 0.7,
            "text.color": neutral,
            "axes.labelcolor": neutral,
            "axes.edgecolor": neutral,
            "xtick.color": neutral,
            "ytick.color": neutral,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    fig = plt.figure(figsize=(16.0, 11.0), facecolor="white")
    outer = fig.add_gridspec(
        4,
        1,
        height_ratios=[0.050, 0.515, 0.105, 0.230],
        hspace=0.0,
    )
    ax_upper_title = fig.add_subplot(outer[0, 0])
    ax_upper_title.set_axis_off()
    ax_upper_title.add_patch(
        FancyBboxPatch(
            (0.0, 0.30),
            1.0,
            0.40,
            transform=ax_upper_title.transAxes,
            boxstyle="round,pad=0.008,rounding_size=0.035",
            facecolor="#171717",
            edgecolor="#171717",
            linewidth=0,
            clip_on=True,
            zorder=0,
        )
    )
    ax_upper_title.text(
        0.50,
        0.50,
        "Waveform-defined extracellular single-unit (SUA) properties",
        transform=ax_upper_title.transAxes,
        fontsize=8.8,
        fontweight="bold",
        color="white",
        ha="center",
        va="center",
        zorder=1,
    )
    upper = outer[1, 0].subgridspec(
        2, 3, width_ratios=[0.19, 0.66, 0.15], hspace=0.10, wspace=0.27
    )
    panel_a_grid = upper[:, 0].subgridspec(
        2, 1, height_ratios=[0.78, 0.22], hspace=0.045
    )
    ax_a_features = fig.add_subplot(panel_a_grid[0, 0], projection="3d")
    panel_a_support = panel_a_grid[1, 0].subgridspec(1, 2, wspace=0.12)
    ax_a_waveform = fig.add_subplot(panel_a_support[0, 0])
    ax_a_composition = fig.add_subplot(panel_a_support[0, 1])

    representative_grid = upper[:, 1].subgridspec(
        3, 1, height_ratios=[0.035, 0.500, 0.465], hspace=0.025
    )
    ax_representative_title = fig.add_subplot(representative_grid[0, 0])
    ax_representative_title.set_axis_off()
    ax_representative_title.text(
        0.0,
        0.62,
        "Representative extracellular units",
        transform=ax_representative_title.transAxes,
        fontsize=8.4,
        fontweight="bold",
        va="center",
    )
    representative_axes: dict[str, list[tuple[object, object, object]]] = {"FS": [], "RS": []}
    representative_class_headers: dict[str, object] = {}
    for row_index, class_label in enumerate(CLASS_ORDER):
        class_block = representative_grid[row_index + 1, 0].subgridspec(
            2, 1, height_ratios=[0.090, 0.910], hspace=0.005
        )
        class_header = fig.add_subplot(class_block[0, 0])
        class_header.set_axis_off()
        representative_class_headers[class_label] = class_header
        panel_letter = "B" if class_label == "FS" else "D"
        class_title = "Fast-spiking (FS)" if class_label == "FS" else "Regular-spiking (RS)"
        class_header.text(
            0.0,
            0.48,
            panel_letter,
            transform=class_header.transAxes,
            fontsize=11.0,
            fontweight="bold",
            va="center",
            color=neutral,
        )
        class_header.text(
            0.043,
            0.48,
            class_title,
            transform=class_header.transAxes,
            fontsize=7.8,
            fontweight="normal",
            va="center",
            color=CLASS_COLORS[class_label],
        )
        if class_label == "RS":
            class_header.plot(
                [0.0, 1.0],
                [1.02, 1.02],
                transform=class_header.transAxes,
                color="#D5D5D5",
                lw=0.55,
                clip_on=False,
            )
        class_grid = class_block[1, 0].subgridspec(1, 2, wspace=0.025)
        for unit_index in range(2):
            card = class_grid[0, unit_index].subgridspec(
                3, 1, height_ratios=[4.20, 0.27, 0.14], hspace=0.070
            )
            acg_strip = card[1, 0].subgridspec(1, 3, width_ratios=[0.14, 0.72, 0.14])
            stability_strip = card[2, 0].subgridspec(1, 3, width_ratios=[0.14, 0.72, 0.14])
            representative_axes[class_label].append(
                (
                    fig.add_subplot(card[0]),
                    fig.add_subplot(acg_strip[0, 1]),
                    fig.add_subplot(stability_strip[0, 1]),
                )
            )
    regional_grid = upper[:, 2].subgridspec(
        3, 1, height_ratios=[0.070, 0.465, 0.465], hspace=0.300
    )
    ax_regional_firing_title = fig.add_subplot(regional_grid[0, 0])
    ax_regional_firing_title.set_axis_off()
    ax_regional_firing_title.text(
        0.0,
        0.62,
        "Regional firing properties of classified units",
        transform=ax_regional_firing_title.transAxes,
        fontsize=7.8,
        fontweight="bold",
        va="center",
    )
    ax_regional_firing_title.text(
        1.0,
        0.14,
        "One point per classified unit · mean ± SEM",
        transform=ax_regional_firing_title.transAxes,
        fontsize=4.8,
        color="#555555",
        ha="right",
        va="center",
    )
    ax_regional_firing_title.plot(
        [0.0, 1.0],
        [1.02, 1.02],
        transform=ax_regional_firing_title.transAxes,
        color="#CFCFCF",
        lw=0.60,
        clip_on=False,
    )
    ax_c_fs_firing = fig.add_subplot(regional_grid[1, 0])
    ax_e_rs_firing = fig.add_subplot(regional_grid[2, 0], sharey=ax_c_fs_firing)

    ax_f_title = fig.add_subplot(outer[2, 0])
    ax_f_title.set_axis_off()
    ax_f_title.add_patch(
        FancyBboxPatch(
            (0.0, 0.34),
            1.0,
            0.30,
            transform=ax_f_title.transAxes,
            boxstyle="round,pad=0.008,rounding_size=0.035",
            facecolor="#171717",
            edgecolor="#171717",
            linewidth=0,
            clip_on=True,
            zorder=0,
        )
    )
    ax_f_title.text(
        0.50,
        0.50,
        "Pooled spontaneous single-unit activity (SUA) across dorsal and ventral SOSRS organoids",
        transform=ax_f_title.transAxes,
        fontsize=8.3,
        fontweight="bold",
        color="white",
        ha="center",
        va="center",
        zorder=1,
    )
    ax_f_title.text(
        0.50,
        0.16,
        "One point represents one organoid; metrics were computed from pooled classified single-unit activity within each organoid.",
        transform=ax_f_title.transAxes,
        fontsize=5.2,
        color="#555555",
        ha="center",
        va="center",
        zorder=1,
    )
    bottom = outer[3, 0].subgridspec(1, 6, wspace=0.20)
    axes_f = [fig.add_subplot(bottom[index]) for index in range(6)]
    fig.subplots_adjust(left=0.045, right=0.992, top=0.988, bottom=0.055)

    _plot_feature_space_3d(ax_a_features, units, fs_cutoff_ms)
    _plot_panel_a_mean_waveforms(ax_a_waveform, waveform_summary)
    _plot_panel_a_composition_bar(ax_a_composition, units)
    _plot_representative_cards(representative_axes, representative_assets)
    shared_unit_rate_ylim = (0.0, 13.0)
    _plot_regional_class_unit_firing(ax_c_fs_firing, units, "FS", shared_unit_rate_ylim)
    _plot_regional_class_unit_firing(ax_e_rs_firing, units, "RS", shared_unit_rate_ylim)
    _plot_activity_strip(axes_f, wells, panel_f_specs)
    fig.align_ylabels(axes_f)

    _panel_letter(ax_a_features, "A", x=-0.08)
    ax_a_features.text2D(
        0.02,
        1.15,
        "Classification",
        transform=ax_a_features.transAxes,
        fontsize=7.8,
        fontweight="bold",
        va="center",
    )
    _panel_letter(ax_c_fs_firing, "C", x=-0.12, y=1.00)
    _panel_letter(ax_e_rs_firing, "E", x=-0.12, y=1.00)

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
    class_legend = ax_a_features.legend(
        handles=class_handles,
        loc="upper right",
        bbox_to_anchor=(1.00, 0.98),
        ncol=1,
        frameon=False,
        fontsize=4.8,
        handletextpad=0.30,
        borderaxespad=0.0,
    )
    ax_a_features.add_artist(class_legend)
    ax_a_features.legend(
        handles=size_handles,
        loc="lower center",
        bbox_to_anchor=(0.50, -0.04),
        ncol=3,
        frameon=False,
        fontsize=4.2,
        handletextpad=0.15,
        columnspacing=0.40,
        borderaxespad=0.0,
    )
    region_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markerfacecolor=REGION_COLORS[region],
            markeredgecolor="none",
            markersize=5,
            label=region.title(),
        )
        for region in REGION_ORDER
    ]
    fig.legend(
        handles=region_handles + variant_handles + [mean_handle],
        loc="lower center",
        bbox_to_anchor=(0.5, 0.006),
        ncol=6,
        frameon=False,
        fontsize=7,
        handletextpad=0.4,
        columnspacing=1.2,
    )
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


def _panel_a_scatter(
    ax,
    units: pd.DataFrame,
    *,
    y_feature: str,
    y_label: str,
    y_limits: tuple[float, float],
    title: str,
    fs_cutoff_ms: float,
) -> None:
    x_limits = (0.24, 2.00)
    complete = units[["feature_ttp_ms", y_feature]].notna().all(axis=1)
    within_axes = (
        complete
        & units["feature_ttp_ms"].between(*x_limits, inclusive="both")
        & units[y_feature].between(*y_limits, inclusive="both")
    )
    plotted = units.loc[within_axes]
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
            subset[y_feature],
            s=sizes,
            color=CLASS_COLORS[class_label],
            alpha=0.68,
            edgecolor="white",
            linewidth=0.35,
            clip_on=True,
        )
    ax.axvline(fs_cutoff_ms, color="#666666", lw=0.8, ls="--", zorder=0)
    ax.set_xlim(x_limits)
    ax.set_ylim(y_limits)
    ax.set_xlabel("Trough-to-peak (ms)")
    ax.set_ylabel(y_label)
    ax.set_title(f"{title} (n={len(plotted)})", loc="left", fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="#E5E5E5", lw=0.5, alpha=0.75)
    ax.set_axisbelow(True)


def _plot_panel_a_2x2(axes: list[object], units: pd.DataFrame, fs_cutoff_ms: float) -> None:
    """Plot the requested two-by-two classification summary for Panel A."""
    ax_repolarization, ax_histogram, ax_half_width, ax_region = axes
    _panel_a_scatter(
        ax_repolarization,
        units,
        y_feature="feature_repolarization_time_ms",
        y_label="Repolarization time (ms)",
        y_limits=(0.00, 0.60),
        title="TTP vs repolarization",
        fs_cutoff_ms=fs_cutoff_ms,
    )

    histogram_units = units.loc[
        units["feature_ttp_ms"].between(0.24, 2.00, inclusive="both")
    ]
    bins = np.arange(0.24, 2.00 + 0.0801, 0.08)
    for class_label in CLASS_ORDER:
        values = histogram_units.loc[
            histogram_units["rs_fs_class"].eq(class_label), "feature_ttp_ms"
        ].to_numpy(float)
        ax_histogram.hist(
            values,
            bins=bins,
            color=CLASS_COLORS[class_label],
            alpha=0.72,
            edgecolor="white",
            linewidth=0.35,
            label=class_label,
        )
    ax_histogram.axvline(fs_cutoff_ms, color="#666666", lw=0.8, ls="--")
    ax_histogram.set_xlim(0.24, 2.00)
    ax_histogram.set_xlabel("Trough-to-peak (ms)")
    ax_histogram.set_ylabel("Units")
    ax_histogram.set_title("TTP distribution", loc="left", fontweight="bold")
    ax_histogram.spines[["top", "right"]].set_visible(False)
    ax_histogram.legend(frameon=False, fontsize=5.8, handletextpad=0.3)

    _panel_a_scatter(
        ax_half_width,
        units,
        y_feature="feature_spike_half_width_ms",
        y_label="Spike half-width (ms)",
        y_limits=(0.00, 0.80),
        title="Half-width vs TTP",
        fs_cutoff_ms=fs_cutoff_ms,
    )

    _plot_panel_a_region_summary(ax_region, units)


def _plot_panel_a_region_summary(ax_region, units: pd.DataFrame) -> None:
    """Plot the compact descriptive dorsal/ventral RS/FS stacked summary."""
    summary = _panel_a_region_classification_summary(units)
    x = np.arange(len(REGION_ORDER), dtype=float)
    bottom = np.zeros(len(REGION_ORDER), dtype=float)
    for class_label in CLASS_ORDER:
        class_rows = summary.loc[summary["rs_fs_class"].eq(class_label)].set_index("region_call")
        percentages = np.array(
            [class_rows.loc[region, "percent_of_region_units"] for region in REGION_ORDER],
            dtype=float,
        )
        counts = np.array(
            [class_rows.loc[region, "unit_count"] for region in REGION_ORDER], dtype=int
        )
        bars = ax_region.bar(
            x,
            percentages,
            bottom=bottom,
            width=0.58,
            color=CLASS_COLORS[class_label],
            edgecolor="white",
            linewidth=0.6,
            label=class_label,
        )
        for bar, count, percentage, base in zip(
            bars, counts, percentages, bottom, strict=True
        ):
            if percentage >= 7:
                ax_region.text(
                    bar.get_x() + bar.get_width() / 2,
                    base + percentage / 2,
                    f"{class_label}\nn={count}",
                    ha="center",
                    va="center",
                    fontsize=5.7,
                    color="white",
                    fontweight="normal",
                )
        bottom += percentages
    totals = summary.groupby("region_call")["region_total_units"].first()
    ax_region.set_xticks(
        x,
        [f"{region.title()}\nn={int(totals.loc[region])}" for region in REGION_ORDER],
    )
    ax_region.set_ylim(0, 100)
    ax_region.set_ylabel("Classified units (%)")
    ax_region.set_title("RS/FS units by region", loc="left", fontweight="bold")
    ax_region.spines[["top", "right"]].set_visible(False)
    ax_region.set_axisbelow(True)
    ax_region.grid(axis="y", color="#E5E5E5", lw=0.5, alpha=0.75)


def _plot_panel_a_composition_bar(ax, units: pd.DataFrame) -> None:
    """Plot a minimal horizontal dorsal/ventral RS/FS composition summary."""
    summary = _panel_a_region_classification_summary(units)
    y = np.arange(len(REGION_ORDER), dtype=float)
    left = np.zeros(len(REGION_ORDER), dtype=float)
    for class_label in CLASS_ORDER:
        class_rows = summary.loc[summary["rs_fs_class"].eq(class_label)].set_index("region_call")
        percentages = np.array(
            [class_rows.loc[region, "percent_of_region_units"] for region in REGION_ORDER],
            dtype=float,
        )
        counts = np.array(
            [class_rows.loc[region, "unit_count"] for region in REGION_ORDER], dtype=int
        )
        bars = ax.barh(
            y,
            percentages,
            left=left,
            height=0.34,
            color=CLASS_COLORS[class_label],
            edgecolor="white",
            linewidth=0.6,
        )
        for bar, count, percentage, base in zip(bars, counts, percentages, left, strict=True):
            if percentage >= 10:
                ax.text(
                    base + percentage / 2,
                    bar.get_y() + bar.get_height() / 2,
                    f"{count} · {percentage:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=4.1,
                    color="white",
                    fontweight="normal",
                )
        left += percentages
    totals = summary.groupby("region_call")["region_total_units"].first()
    ax.set_yticks(
        y,
        [f"{region.title()} (n={int(totals.loc[region])})" for region in REGION_ORDER],
    )
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xticks([])
    ax.tick_params(axis="y", labelsize=4.4, length=0, pad=1)
    for spine in ax.spines.values():
        spine.set_visible(False)


def _plot_panel_a_mean_waveforms(ax, waveform_summary: pd.DataFrame) -> None:
    """Plot aligned class means at original amplitude beneath the region summary."""
    all_means: list[np.ndarray] = []
    for class_label in CLASS_ORDER:
        summary = waveform_summary.loc[
            waveform_summary["rs_fs_class"].eq(class_label)
            & waveform_summary["representation"].eq("raw_uV")
        ].sort_values("time_ms")
        time = summary["time_ms"].to_numpy(float)
        mean = summary["mean"].to_numpy(float)
        all_means.append(mean)
        ax.plot(time, mean, color=CLASS_COLORS[class_label], lw=1.15, label=class_label)
    ax.set_xlim(-0.55, 1.15)
    ax.text(0.01, 0.90, "FS", transform=ax.transAxes, fontsize=5.2, color=CLASS_COLORS["FS"], va="top")
    ax.text(0.13, 0.90, "RS", transform=ax.transAxes, fontsize=5.2, color=CLASS_COLORS["RS"], va="top")
    combined = np.concatenate(all_means)
    y_min, y_max = float(np.nanmin(combined)), float(np.nanmax(combined))
    margin = 0.12 * max(y_max - y_min, 1.0)
    ax.set_ylim(y_min - margin, y_max + margin)
    scale_x = 0.50
    scale_y = 5.0
    x0 = 0.52
    y0 = y_min - 0.02 * max(y_max - y_min, 1.0)
    ax.plot([x0, x0 + scale_x], [y0, y0], color="#333333", lw=0.85, clip_on=False)
    ax.plot([x0 + scale_x, x0 + scale_x], [y0, y0 + scale_y], color="#333333", lw=0.85, clip_on=False)
    ax.text(x0 + scale_x / 2, y0 - 0.06 * (y_max - y_min), "0.5 ms", ha="center", va="top", fontsize=4.5)
    ax.text(x0 + scale_x + 0.035, y0 + scale_y / 2, "5 µV", ha="left", va="center", fontsize=4.5, rotation=90)
    ax.set_axis_off()


def _plot_regional_class_unit_firing(
    ax,
    units: pd.DataFrame,
    class_label: str,
    shared_ylim: tuple[float, float],
) -> None:
    """Plot one legacy whole-recording firing-rate point per retained classified unit."""
    from matplotlib.ticker import MaxNLocator

    source = _regional_classified_unit_firing_source(units)
    source = source.loc[source["rs_fs_class"].eq(class_label)].copy()
    rng = np.random.default_rng(20260710)
    positions = {"dorsal": 0.0, "ventral": 0.36}
    for region in REGION_ORDER:
        position = positions[region]
        group = source.loc[source["region_call"].eq(region)].copy()
        values = group["classified_unit_firing_rate_hz"].to_numpy(float)
        jitter = rng.uniform(-0.055, 0.055, size=len(group))
        ax.scatter(
            np.full(len(group), position, dtype=float) + jitter,
            values,
            s=20 if class_label == "FS" else 13,
            color=REGION_COLORS[region],
            alpha=0.78,
            edgecolor="white",
            linewidth=0.45,
            zorder=2,
        )
        mean = float(np.mean(values))
        sem = _sem(values)
        ax.errorbar(
            position,
            mean,
            yerr=sem,
            fmt="D",
            ms=5.2,
            mfc="white",
            mec="#222222",
            mew=0.8,
            ecolor="#222222",
            elinewidth=0.9,
            capsize=3,
            zorder=4,
        )
    labels = []
    for region in REGION_ORDER:
        group = source.loc[source["region_call"].eq(region)]
        labels.append(
            f"{region.title()}\n{len(group)} {class_label} units\n"
            f"{group['recording_well_id'].nunique()} wells"
        )
    ax.set_xticks([positions[region] for region in REGION_ORDER], labels)
    ax.set_xlim(-0.42, 0.78)
    ax.set_ylim(shared_ylim)
    ax.set_ylabel("Classified-unit firing rate (Hz)", fontsize=8.0, labelpad=2)
    ax.yaxis.set_label_coords(-0.14, 0.5)
    title = "Fast-spiking (FS)" if class_label == "FS" else "Regular-spiking (RS)"
    ax.set_title(title, loc="left", fontweight="normal", y=1.015, pad=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, prune=None))
    ax.tick_params(
        axis="both", which="major", direction="out", length=2.2, width=0.6, pad=2.0, labelsize=6.8
    )
    ax.grid(axis="y", color="#E5E5E5", lw=0.5, alpha=0.75)
    ax.set_axisbelow(True)


def _plot_feature_space_3d(ax, units: pd.DataFrame, fs_cutoff_ms: float) -> None:
    complete = units[
        [
            "feature_ttp_ms",
            "feature_repolarization_time_ms",
            "feature_spike_half_width_ms",
        ]
    ].notna().all(axis=1)
    axis_limits = {
        "feature_ttp_ms": (0.24, 2.00),
        "feature_repolarization_time_ms": (0.00, 0.60),
        "feature_spike_half_width_ms": (0.00, 0.80),
    }
    within_axes = complete.copy()
    for feature, (lower, upper) in axis_limits.items():
        within_axes &= units[feature].between(lower, upper, inclusive="both")
    plotted = units.loc[within_axes].copy()
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
    x_limits = axis_limits["feature_ttp_ms"]
    y_limits = axis_limits["feature_repolarization_time_ms"]
    z_limits = axis_limits["feature_spike_half_width_ms"]
    ax.set_title(
        f"Aligned three-feature waveform space (n={len(plotted)} shown)",
        loc="left",
        fontweight="normal",
        pad=4,
    )
    ax.set_xlabel(f"Trough-to-peak (ms)\nFS ≤ {fs_cutoff_ms:.2f} ms", labelpad=4)
    ax.set_ylabel("Repolarization time (ms)", labelpad=3)
    ax.set_zlabel("Spike half-width (ms)", labelpad=1)
    ax.set_xlim(x_limits)
    ax.set_ylim(y_limits)
    ax.set_zlim(z_limits)
    ax.view_init(elev=22, azim=-46)
    ax.set_box_aspect((1.20, 0.95, 0.75))
    ax.tick_params(labelsize=6, pad=0)
    ax.grid(True, alpha=0.16)


def _plot_smoothed_landmark_inset(ax, waveform_summary: pd.DataFrame) -> None:
    from scipy.signal import savgol_filter

    for class_label in CLASS_ORDER:
        summary = waveform_summary.loc[
            waveform_summary["rs_fs_class"].eq(class_label)
            & waveform_summary["representation"].eq("trough_normalized")
        ].sort_values("time_ms")
        time = summary["time_ms"].to_numpy(float)
        waveform = summary["mean"].to_numpy(float)
        window = min(7, waveform.size if waveform.size % 2 else waveform.size - 1)
        smooth = savgol_filter(waveform, window_length=max(window, 3), polyorder=2)
        trough = int(np.nanargmin(smooth))
        post_indices = np.flatnonzero(time > time[trough])
        peak = (
            int(post_indices[np.nanargmax(smooth[post_indices])])
            if post_indices.size
            else trough
        )
        ax.plot(time, smooth, color=CLASS_COLORS[class_label], lw=0.9)
        ax.scatter(
            time[[trough, peak]],
            smooth[[trough, peak]],
            s=10,
            color=CLASS_COLORS[class_label],
            edgecolor="white",
            linewidth=0.35,
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
    display_gain = SPATIAL_WAVEFORM_DISPLAY_GAIN
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
            y0 + waveform * y_scale * display_gain,
            color=color,
            lw=1.35 if int(channel_index) == best else 0.75,
            alpha=1.0 if int(channel_index) == best else 0.72,
            zorder=3,
        )
    local_xy = locations[local_channels]
    ax.set_xlim(local_xy[:, 0].min() - 0.55 * dx, local_xy[:, 0].max() + 0.55 * dx)
    ax.set_ylim(local_xy[:, 1].min() - 0.55 * dy, local_xy[:, 1].max() + 0.55 * dy)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    display_id = f"{class_label}{order}"
    ax.set_title(
        f"{display_id} · TTP {metadata['feature_ttp_ms']:.2f} ms",
        loc="left",
        fontsize=6.2,
        fontweight="normal",
        color=color,
        pad=2.0,
    )


def _plot_representative_acg(ax, asset, class_label: str, *, show_ylabel: bool) -> None:
    import scripts.plot_spatial_isolation_1x2_panels as hybrid

    probability = asset["probability"]
    bins = np.asarray(probability["bins"], dtype=float)
    values = np.asarray(probability["probability"], dtype=float)
    mask = np.asarray(probability["display_mask"], dtype=bool)
    x = bins[mask]
    y = np.nan_to_num(values[mask], nan=0.0)
    color = CLASS_COLORS[class_label]
    ax.fill_between(x, 0, y, color=color, alpha=0.16, linewidth=0)
    ax.plot(x, y, color=color, lw=0.9)
    ax.axvline(-2, color="#777777", lw=0.55, ls="--")
    ax.axvline(2, color="#777777", lw=0.55, ls="--")
    ax.set_xlim(-50, 50)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(
        f"ACG  P(|lag|≤2 ms)={float(probability['p_refractory']):.3f}",
        loc="left",
        fontsize=5.8,
        pad=2.0,
    )
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)


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
    ax.set_title("PTP stability", loc="left", fontsize=5.8, pad=2.0)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)


def _plot_fs_candidate_gallery(
    plt,
    assets: list[dict[str, object]],
    output_base: Path,
    export_formats: str,
) -> list[Path]:
    assets = sorted(
        assets,
        key=lambda asset: asset["metadata"]["representative_order_within_class"],
    )
    ncols = 5
    nrows = int(np.ceil(len(assets) / ncols))
    fig = plt.figure(figsize=(18.0, 3.65 * nrows), facecolor="white")
    outer = fig.add_gridspec(nrows, ncols, hspace=0.30, wspace=0.24)
    for index, asset in enumerate(assets):
        row, column = divmod(index, ncols)
        card = outer[row, column].subgridspec(
            3, 1, height_ratios=[1.18, 0.72, 0.34], hspace=0.13
        )
        axes = (
            fig.add_subplot(card[0]),
            fig.add_subplot(card[1]),
            fig.add_subplot(card[2]),
        )
        _plot_representative_spatial(axes[0], asset, "FS", index + 1)
        _plot_representative_acg(axes[1], asset, "FS", show_ylabel=column == 0)
        _plot_representative_stability(axes[2], asset, "FS", show_ylabel=column == 0)
        if bool(asset["metadata"].get("selected_for_figure", False)):
            axes[0].text(
                0.98,
                0.98,
                "current pick",
                transform=axes[0].transAxes,
                ha="right",
                va="top",
                fontsize=5.5,
                color=CLASS_COLORS["FS"],
                fontweight="bold",
            )
    for index in range(len(assets), nrows * ncols):
        row, column = divmod(index, ncols)
        ax = fig.add_subplot(outer[row, column])
        ax.set_axis_off()
    fig.suptitle(
        "Retained QC-eligible FS candidates for representative-unit selection",
        fontsize=14,
        fontweight="bold",
        y=0.995,
    )
    fig.subplots_adjust(left=0.035, right=0.995, top=0.965, bottom=0.035)
    output_paths: list[Path] = []
    for suffix in [part.strip().lower() for part in export_formats.split(",") if part.strip()]:
        path = output_base.with_suffix(f".{suffix}")
        kwargs: dict[str, object] = {
            "bbox_inches": "tight",
            "facecolor": "white",
            "transparent": False,
        }
        if suffix == "png":
            kwargs["dpi"] = 300
        fig.savefig(path, **kwargs)
        output_paths.append(path)
    plt.close(fig)
    return output_paths


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
    from matplotlib.ticker import MaxNLocator

    rng = np.random.default_rng(20260710)
    positions = {"dorsal": 0.0, "ventral": 0.30}
    for panel_index, (ax, (panel, metric, title, ylabel)) in enumerate(zip(axes, specs, strict=True)):
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
                    s=20,
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
                    ms=4.4,
                    color="black",
                    markerfacecolor="white",
                    markeredgewidth=0.8,
                    capsize=3.0,
                    lw=0.9,
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
        ax.set_title(
            chr(ord("F") + panel_index),
            loc="left",
            fontsize=11.0,
            fontweight="bold",
            y=1.015,
            pad=0,
        )
        ax.set_ylabel(ylabel, fontsize=8.0, labelpad=2)
        ax.yaxis.set_label_coords(-0.14, 0.5)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4, prune="both"))
        ax.tick_params(
            axis="both", which="major", direction="out", length=2.2, width=0.6, pad=2.0, labelsize=6.8
        )
        ax.grid(axis="y", color="#E5E5E5", lw=0.5, alpha=0.72)
        _clean_axis(ax)


def _panel_letter(ax, label: str, *, x: float, y: float = 1.08) -> None:
    method = getattr(ax, "text2D", ax.text)
    method(x, y, label, transform=ax.transAxes, fontsize=11.0, fontweight="bold", va="top")


def _clean_axis(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(direction="out", length=2.2, width=0.6, pad=1.5)


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
