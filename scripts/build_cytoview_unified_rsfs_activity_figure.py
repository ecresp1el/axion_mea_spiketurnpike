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
DEFAULT_LUMOS_VENTRAL_RECOMPUTED_UNITS = (
    JOB_ROOT / ".channel_avg_work_20260713" / "lumos_ventral_unit_metrics_recomputed.csv"
)
DEFAULT_LUMOS_VENTRAL_CHANNEL_METRICS = (
    JOB_ROOT / ".channel_avg_work_20260713" / "channel_averaged_metrics.csv"
)
DEFAULT_TTR90_CLASSIFIER_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/FINAL FIG 2/"
    "Population Panels/ventral_MGE_putative_FS_RS_robust_PCHIP_FINAL/"
    "ttr90_canonical_negative_classifier"
)
DEFAULT_TTR90_AUDIT_DIR = DEFAULT_TTR90_CLASSIFIER_DIR.parent / "waveform_source_audit"
STEM = "cytoview_unified_rsfs_activity_figure_20260710"

CLASS_ORDER = ["FS", "RS"]
CLASS_COLORS = {"FS": "#B8742A", "RS": "#58758E"}
TTR90_FS_MAX_MS = 0.40
TTR90_RS_MIN_MS = 0.56
TTR90_INDETERMINATE_COLOR = "#999999"
REGION_ORDER = ["dorsal", "ventral"]
REGION_COLORS = {"dorsal": "#6F8477", "ventral": "#C8A05A"}
VARIANT_MARKERS = {
    "primary_raw": "o",
    "filter_200Hz-3kHz": "s",
    "broadband_processor_raw": "^",
}
CELL_LINE_MARKERS = {
    "CL32 PV": "o",
    "CL23 PV": "s",
    "H1": "^",
}
CELL_LINE_CODES = {
    "CL32 PV": "Cell line 1 · CL32 PV",
    "CL23 PV": "Cell line 2 · CL23 PV",
    "H1": "Cell line 3 · H1",
}
LUMOS_CELL_LINE_WELL_CORRECTIONS = {
    # Paired reviewed correction: preserve the balanced Lumos allocation while
    # restoring the CL32 identity of the RS-bearing plate-2 D2 organoid.
    "2026-06-18|plate2|129-8445|D2": "CL32 PV",
    "2026-06-18|plate2|129-8445|B5": "H1",
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
    parser.add_argument(
        "--output-stem",
        default=None,
        help="Optional exact output filename stem, without extension.",
    )
    parser.add_argument("--lumos-ventral-mode", action="store_true")
    parser.add_argument(
        "--recomputed-unit-metrics",
        type=Path,
        default=DEFAULT_LUMOS_VENTRAL_RECOMPUTED_UNITS,
    )
    parser.add_argument(
        "--channel-metrics",
        type=Path,
        default=DEFAULT_LUMOS_VENTRAL_CHANNEL_METRICS,
    )
    parser.add_argument(
        "--robust-pchip-dir",
        type=Path,
        default=None,
        help=(
            "Optional output directory from reclassify_lumos_ventral_robust_pchip_waveforms.py; "
            "when supplied, use robust-median PCHIP features and new FS/RS labels."
        ),
    )
    parser.add_argument(
        "--ttr90-classifier-dir",
        type=Path,
        default=None,
        help=(
            "Optional canonical-negative TTR90 classifier directory. Retain only "
            "high-confidence FS-like (<=0.40 ms) and RS-like (>=0.56 ms) units; "
            "indeterminate canonical units are shown only in gray in Panel A, "
            "and atypical units are excluded."
        ),
    )
    parser.add_argument(
        "--ttr90-audit-dir",
        type=Path,
        default=DEFAULT_TTR90_AUDIT_DIR,
        help=(
            "Waveform-source audit containing the template-best channel used for "
            "channel-first organoid aggregation in TTR90 mode."
        ),
    )
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

    if args.lumos_ventral_mode:
        return _main_lumos_ventral(args, plt, Line2D, inset_axes, output_dir)

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
    traces = traces.loc[traces["unit_key"].isin(units["unit_key"])].copy()
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


def _main_lumos_ventral(args, plt, Line2D, inset_axes, output_dir: Path) -> int:
    """Render the July-10 unified layout for pooled Lumos + ventral CytoView units."""
    recomputed = pd.read_csv(args.recomputed_unit_metrics.expanduser().resolve())
    lumos_paired = pd.read_csv(
        LUMOS_ALIGNMENT_DIR / "waveform_alignment_feature_audit_20260709_paired_unit_metrics.csv"
    )
    cyto_paired = pd.read_csv(
        DEFAULT_ALIGNMENT_DIR / "waveform_alignment_feature_audit_20260709_paired_unit_metrics.csv"
    )
    paired = pd.concat([lumos_paired, cyto_paired], ignore_index=True).drop_duplicates("unit_key")
    firing_lumos = pd.read_csv(LUMOS_FIRING_PATH)
    firing_lumos["unit_key"] = (
        firing_lumos["recording"].astype(str)
        + "|"
        + firing_lumos["well"].astype(str)
        + "|"
        + firing_lumos["unit_id"].astype(str)
    )
    cyto_units = pd.read_csv(
        DEFAULT_ACTIVITY_DIR / "cytoview_dv_sua_spontaneous_activity_20260710_unit_metrics.csv"
    )
    quality = pd.concat(
        [
            firing_lumos[["unit_key", "ContamPct"]].rename(
                columns={"ContamPct": "source_ContamPct"}
            ),
            cyto_units[["unit_key", "source_ContamPct"]],
        ],
        ignore_index=True,
    ).drop_duplicates("unit_key")
    feature_columns = [
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
        "analyzer_path",
        "usable_snippets",
    ]
    units = recomputed.merge(
        paired[["unit_key", *feature_columns]], on="unit_key", how="left", validate="one_to_one"
    ).merge(quality, on="unit_key", how="left", validate="one_to_one")
    units["recording_well_id"] = units["recording"].astype(str) + "|" + units["well"].astype(str)
    units["organoid_well"] = units["well"].astype(str)
    units["region_call"] = units["source_platform"].map(
        {"Lumos": "Lumos", "CytoView": "Ventral CytoView"}
    )
    units["raw_variant"] = units["recording"].map(_raw_variant_from_recording)
    units = _assign_cell_lines(units)
    units["source_firing_rate_hz"] = units["legacy_firing_rate_hz"]
    units["template_ptp_best_channel_uV"] = pd.to_numeric(
        units["template_ptp_uV"], errors="coerce"
    ).fillna(pd.to_numeric(units["after_template_ptp_best_channel_uV"], errors="coerce"))
    units["source_isi_lt_2ms_fraction"] = 0.0
    units["rs_fs_class"] = units["rs_fs_class"].astype(str)
    units["aligned_fs_rs_class"] = units["rs_fs_class"]
    units["aligned_trough_to_peak_duration_ms"] = units["unit_key"].map(
        paired.set_index("unit_key")["after_trough_to_peak_duration_ms"]
    )
    units["aligned_waveform_asymmetry"] = units["after_waveform_asymmetry"]
    units["aligned_repolarization_slope_uV_per_ms"] = units[
        "after_post_trough_rebound_slope_uV_per_ms"
    ]
    units["feature_ttp_ms"] = units["aligned_trough_to_peak_duration_ms"]
    units["feature_asymmetry"] = units["after_waveform_asymmetry"]
    units["feature_repolarization_slope_uV_per_ms"] = units[
        "after_post_trough_rebound_slope_uV_per_ms"
    ]
    units["feature_repolarization_time_ms"] = units["after_repolarization_time_ms"]
    units["feature_spike_half_width_ms"] = units["after_spike_half_width_ms"]
    units["timing_feature_label"] = "TTP"
    robust_pchip_mode = args.robust_pchip_dir is not None
    ttr90_mode = args.ttr90_classifier_dir is not None
    if robust_pchip_mode and ttr90_mode:
        raise ValueError("Choose either --robust-pchip-dir or --ttr90-classifier-dir")
    excluded_ttr90_units = pd.DataFrame()
    panel_a_indeterminate_units = pd.DataFrame()
    if ttr90_mode:
        ttr90_dir = args.ttr90_classifier_dir.expanduser().resolve()
        ttr90_metrics = pd.read_csv(
            ttr90_dir / "ttr90_canonical_negative_unit_metrics.csv"
        )
        ttr90_columns = [
            "unit_key",
            "morphology_class",
            "canonical_negative_trough",
            "valid_90pct_crossing_exists",
            "ttr90_ms",
            "ttr90_confidence_category",
            "raw_discrete_trough_to_global_peak_ms",
            "pchip_trough_to_global_peak_ms",
            "rebound_amplitude_uV",
        ]
        missing_columns = sorted(set(ttr90_columns).difference(ttr90_metrics.columns))
        if missing_columns:
            raise ValueError(f"TTR90 metrics missing columns: {missing_columns}")
        expected_keys = set(units["unit_key"])
        ttr90_keys = set(ttr90_metrics["unit_key"])
        if expected_keys != ttr90_keys:
            raise ValueError(
                "TTR90 unit roster mismatch: "
                f"missing={len(expected_keys - ttr90_keys)}, "
                f"extra={len(ttr90_keys - expected_keys)}"
            )
        units["previous_rs_fs_class"] = units["rs_fs_class"]
        units = units.merge(
            ttr90_metrics[ttr90_columns],
            on="unit_key",
            how="left",
            validate="one_to_one",
        )
        ttr90_audit_dir = args.ttr90_audit_dir.expanduser().resolve()
        ttr90_channels = pd.read_csv(
            ttr90_audit_dir / "waveform_source_audit_unit_metrics.csv",
            usecols=[
                "unit_key",
                "template_best_channel_id",
                "template_best_channel_index",
            ],
        ).rename(
            columns={
                "template_best_channel_id": "ttr90_template_best_channel_id",
                "template_best_channel_index": "ttr90_template_best_channel_index",
            }
        )
        if set(ttr90_channels["unit_key"]) != expected_keys:
            raise ValueError("TTR90 waveform-audit channel roster does not match units")
        units = units.merge(
            ttr90_channels,
            on="unit_key",
            how="left",
            validate="one_to_one",
        )
        class_map = {
            "high_confidence_FS_like": "FS",
            "high_confidence_RS_like": "RS",
        }
        units["ttr90_plot_class"] = units["ttr90_confidence_category"].map(class_map)
        excluded_ttr90_units = units.loc[units["ttr90_plot_class"].isna()].copy()
        panel_a_indeterminate_units = units.loc[
            units["ttr90_confidence_category"].eq("indeterminate")
        ].copy()
        panel_a_indeterminate_units["feature_ttp_ms"] = pd.to_numeric(
            panel_a_indeterminate_units["ttr90_ms"], errors="coerce"
        )
        units = units.loc[units["ttr90_plot_class"].isin(CLASS_ORDER)].copy()
        units["rs_fs_class"] = units["ttr90_plot_class"]
        units["aligned_fs_rs_class"] = units["rs_fs_class"]
        units["feature_ttp_ms"] = pd.to_numeric(units["ttr90_ms"], errors="coerce")
        units["aligned_trough_to_peak_duration_ms"] = units["feature_ttp_ms"]
        # Display shorthand only; the underlying timing column remains ttr90_ms.
        units["timing_feature_label"] = "TTP"
        units["classification_changed"] = units["previous_rs_fs_class"].ne(
            units["rs_fs_class"]
        )
        units["classification_transition"] = (
            units["previous_rs_fs_class"].astype(str)
            + "→"
            + units["rs_fs_class"].astype(str)
        )
        traces = pd.read_csv(
            ttr90_dir / "ttr90_canonical_negative_pchip_traces.csv.gz"
        ).rename(
            columns={
                "time_from_trough_ms": "time_ms",
                "pchip_waveform_uV": "after_aligned_average_uV",
            }
        )
        traces["time_ms"] = pd.to_numeric(traces["time_ms"], errors="coerce").round(6)
    elif robust_pchip_mode:
        robust_dir = args.robust_pchip_dir.expanduser().resolve()
        robust_metrics = pd.read_csv(robust_dir / "robust_pchip_unit_metrics.csv")
        robust_columns = [
            "unit_key",
            "old_rs_fs_class",
            "new_rs_fs_class",
            "classification_changed",
            "classification_transition",
            "robust_median_trough_to_peak_duration_ms",
            "robust_median_repolarization_time_ms",
            "robust_median_spike_half_width_ms",
            "robust_median_peak_detection_status",
            "aligned_mean_trough_to_peak_duration_ms",
            "alignment_shift_median_samples",
            "alignment_shift_mad_samples",
            "alignment_correlation_median",
        ]
        missing_columns = sorted(set(robust_columns).difference(robust_metrics.columns))
        if missing_columns:
            raise ValueError(f"Robust PCHIP metrics missing columns: {missing_columns}")
        expected_keys = set(units["unit_key"])
        robust_keys = set(robust_metrics["unit_key"])
        if expected_keys != robust_keys:
            raise ValueError(
                "Robust PCHIP unit roster mismatch: "
                f"missing={len(expected_keys - robust_keys)}, extra={len(robust_keys - expected_keys)}"
            )
        units = units.merge(
            robust_metrics[robust_columns],
            on="unit_key",
            how="left",
            validate="one_to_one",
        )
        old_disagreement = units["old_rs_fs_class"].ne(units["rs_fs_class"])
        if old_disagreement.any():
            raise ValueError(
                f"Old-class mismatch for {int(old_disagreement.sum())} robust PCHIP rows"
            )
        units["previous_rs_fs_class"] = units["rs_fs_class"]
        units["rs_fs_class"] = units["new_rs_fs_class"].astype(str)
        units["aligned_fs_rs_class"] = units["rs_fs_class"]
        units["feature_ttp_ms"] = pd.to_numeric(
            units["robust_median_trough_to_peak_duration_ms"], errors="coerce"
        )
        units["aligned_trough_to_peak_duration_ms"] = units["feature_ttp_ms"]
        units["feature_repolarization_time_ms"] = pd.to_numeric(
            units["robust_median_repolarization_time_ms"], errors="coerce"
        )
        units["feature_spike_half_width_ms"] = pd.to_numeric(
            units["robust_median_spike_half_width_ms"], errors="coerce"
        )
        traces = pd.read_csv(robust_dir / "robust_pchip_waveform_traces.csv.gz")
        traces = traces.rename(columns={"robust_median_uV": "after_aligned_average_uV"})
    else:
        trace_frames = []
        for directory in [LUMOS_ALIGNMENT_DIR, DEFAULT_ALIGNMENT_DIR]:
            trace_frames.append(
                pd.read_csv(
                    directory
                    / "waveform_alignment_feature_audit_20260709_waveform_traces.csv.gz"
                )
            )
        traces = pd.concat(trace_frames, ignore_index=True)
        traces = traces.loc[traces["unit_key"].isin(units["unit_key"])].copy()
    traces = traces.merge(
        units[["unit_key", "rs_fs_class"]], on="unit_key", how="left", validate="many_to_one"
    )
    traces = _normalize_waveforms(traces)
    waveform_summary = _waveform_summary(traces)
    representative_selection = _select_distinct_organoid_representatives(units, traces)
    representative_assets = _load_representative_assets(representative_selection)

    organoid_group_columns = [
        "source_platform",
        "recording",
        "well",
        "rs_fs_class",
        "cell_line",
    ]
    organoid_metric_map = {
        "inverse_isi_gaussian_temporal_p99_9_hz": (
            "mean_unit_inverse_isi_gaussian_temporal_p99_9_hz"
        ),
        "burst_rate_per_min": "mean_unit_burst_rate_per_min",
        "mean_firing_rate_within_bursts_hz": "mean_unit_firing_rate_within_bursts_hz",
        "mean_burst_duration_ms": "mean_unit_burst_duration_ms",
        "mean_interburst_interval_s": "mean_unit_interburst_interval_s",
        "mean_spikes_per_burst": "mean_unit_spikes_per_burst",
    }
    channel_level_activity = pd.DataFrame()
    if ttr90_mode:
        channel_group_columns = [
            *organoid_group_columns,
            "ttr90_template_best_channel_id",
        ]
        channel_level_activity = (
            units.groupby(channel_group_columns, dropna=False)[list(organoid_metric_map)]
            .mean()
            .reset_index()
        )
        channel_unit_counts = (
            units.groupby(channel_group_columns, dropna=False)
            .size()
            .rename("unit_count_on_best_channel")
            .reset_index()
        )
        channel_level_activity = channel_level_activity.merge(
            channel_unit_counts,
            on=channel_group_columns,
            validate="one_to_one",
        )
        wells = (
            channel_level_activity.groupby(organoid_group_columns, dropna=False)[
                list(organoid_metric_map)
            ]
            .mean()
            .reset_index()
            .rename(columns=organoid_metric_map)
        )
        best_channel_counts = (
            channel_level_activity.groupby(organoid_group_columns, dropna=False)
            .size()
            .rename("best_channel_count")
            .reset_index()
        )
        wells = wells.merge(
            best_channel_counts,
            on=organoid_group_columns,
            validate="one_to_one",
        )
    else:
        wells = (
            units.groupby(organoid_group_columns, dropna=False)[list(organoid_metric_map)]
            .mean()
            .reset_index()
            .rename(columns=organoid_metric_map)
        )
    unit_counts = (
        units.groupby(organoid_group_columns, dropna=False)
        .size()
        .rename("sua_unit_count")
        .reset_index()
    )
    eligible_counts = (
        units.assign(
            inverse_isi_eligible=units["inverse_isi_gaussian_eligible"].astype(bool)
        )
        .groupby(organoid_group_columns, dropna=False)["inverse_isi_eligible"]
        .sum()
        .rename("inverse_isi_gaussian_eligible_sua_unit_count")
        .reset_index()
    )
    wells = wells.merge(unit_counts, on=organoid_group_columns, validate="one_to_one")
    wells = wells.merge(eligible_counts, on=organoid_group_columns, validate="one_to_one")
    wells["region_call"] = wells["rs_fs_class"]
    wells["recording_well_id"] = wells["recording"].astype(str) + "|" + wells["well"].astype(str)
    wells["raw_variant"] = wells["recording"].map(_raw_variant_from_recording)

    if ttr90_mode:
        source_stem = "lumos_ventral_ttr90_confidence"
        all_ttr90_units = pd.concat(
            [units, excluded_ttr90_units], ignore_index=True, sort=False
        )
        lumos_cell_line_assignment = (
            all_ttr90_units.loc[
                all_ttr90_units["source_platform"].astype(str).eq("Lumos"),
                [
                    "lumos_biological_well_key",
                    "cell_line",
                    "cell_line_assignment_basis",
                ],
            ]
            .drop_duplicates()
            .sort_values("lumos_biological_well_key")
        )
        lumos_cell_line_assignment.to_csv(
            output_dir / f"{source_stem}_lumos_cell_line_well_assignment.csv",
            index=False,
        )
        units.to_csv(output_dir / f"{source_stem}_retained_FS_RS_units.csv", index=False)
        excluded_ttr90_units.to_csv(
            output_dir / f"{source_stem}_excluded_indeterminate_atypical_units.csv",
            index=False,
        )
        wells.to_csv(
            output_dir / f"{source_stem}_organoid_level_activity.csv", index=False
        )
        channel_level_activity.to_csv(
            output_dir / f"{source_stem}_channel_level_activity.csv", index=False
        )
        waveform_summary.to_csv(
            output_dir / f"{source_stem}_waveform_summary.csv", index=False
        )
        representative_selection.to_csv(
            output_dir / f"{source_stem}_representative_units.csv", index=False
        )
        (output_dir / f"{source_stem}_plotting_provenance.json").write_text(
            json.dumps(
                {
                    "classification_source": str(
                        args.ttr90_classifier_dir.expanduser().resolve()
                        / "ttr90_canonical_negative_unit_metrics.csv"
                    ),
                    "template_best_channel_source": str(
                        args.ttr90_audit_dir.expanduser().resolve()
                        / "waveform_source_audit_unit_metrics.csv"
                    ),
                    "unit_denominator_before_plot_filter": int(
                        len(units) + len(excluded_ttr90_units)
                    ),
                    "retained_plot_unit_count": int(len(units)),
                    "retained_class_counts": units["rs_fs_class"]
                    .value_counts()
                    .to_dict(),
                    "excluded_unit_count": int(len(excluded_ttr90_units)),
                    "excluded_category_counts": excluded_ttr90_units[
                        "ttr90_confidence_category"
                    ]
                    .value_counts()
                    .to_dict(),
                    "plot_mapping": {
                        "high_confidence_FS_like": "FS",
                        "high_confidence_RS_like": "RS",
                        "indeterminate": (
                            "Panel A histogram and 3D feature space only; gray"
                        ),
                        "unclassified_atypical": "excluded",
                    },
                    "panel_a_indeterminate_unit_count": int(
                        len(panel_a_indeterminate_units)
                    ),
                    "lumos_cell_line_assignment": (
                        "balanced deterministic assignment across unique "
                        "date/plate/barcode/well organoids with reviewed paired "
                        "well-label corrections; recording variants share the same "
                        "assignment"
                    ),
                    "lumos_unique_well_counts_by_cell_line": (
                        lumos_cell_line_assignment["cell_line"]
                        .value_counts()
                        .to_dict()
                    ),
                    "unit_level_panels": "one point per retained putative unit",
                    "organoid_level_panels": (
                        "mean of best-channel means within recording-version/well/class"
                    ),
                },
                indent=2,
            )
            + "\n"
        )

    paths = _plot_unified_figure(
        plt,
        Line2D,
        inset_axes,
        units,
        traces,
        waveform_summary,
        representative_assets,
        wells,
        _panel_f_specs(),
        output_dir
        / (
            args.output_stem
            or (
                "lumos_ventral_unified_putative_fsrs_ttr90_confidence_organoid_level"
                if ttr90_mode
                else (
                    "lumos_ventral_unified_putative_fsrs_robust_pchip_organoid_level"
                    if robust_pchip_mode
                    else "lumos_ventral_unified_putative_fsrs_organoid_level"
                )
            )
        ),
        args.export_formats,
        args.fs_cutoff_ms,
        pooled_fsrs_mode=True,
        robust_pchip_mode=robust_pchip_mode,
        ttr90_mode=ttr90_mode,
        panel_a_indeterminate_units=panel_a_indeterminate_units,
    )
    print(f"Pooled units: {len(units)}")
    print(f"Class counts: {units['rs_fs_class'].value_counts().to_dict()}")
    if ttr90_mode:
        print(
            "Panel A indeterminate canonical units: "
            f"{len(panel_a_indeterminate_units)}"
        )
    print("Representatives:")
    print(
        representative_selection[
            [
                "representative_display_id",
                "cell_line",
                "source_platform",
                "recording",
                "well",
                "unit_id",
            ]
        ].to_string(index=False)
    )
    print("Figures:")
    for path in paths:
        print(path)
    return 0


def _raw_variant_from_recording(recording: str) -> str:
    text = str(recording).lower()
    if "filter_200hz-3khz" in text:
        return "filter_200Hz-3kHz"
    if "broadband_processor_raw" in text:
        return "broadband_processor_raw"
    return "primary_raw"


def _cell_line_from_metadata(recording: str, source_platform: str) -> str:
    """Map non-Lumos biological cell lines from decoded recording identity."""
    text = str(recording).lower()
    if str(source_platform) == "Lumos":
        raise ValueError("Lumos cell lines require date/plate/well assignment")
    if "pvreporter" in text or "pv_reporter_cl23" in text:
        return "CL23 PV"
    if "_h1_" in text or "h1_dorsal_and_ventral" in text:
        return "H1"
    raise ValueError(f"Could not identify biological cell line from recording: {recording}")


def _lumos_plate_key(recording: str) -> str:
    """Return a stable date/plate/barcode identity across Lumos recording variants."""
    import re

    text = str(recording).lower()
    date_match = re.search(r"(?<!\d)(\d{1,2})_(\d{1,2})_(\d{4})(?!\d)", text)
    barcode_match = re.search(r"(?<!\d)(\d{3}-\d{4})(?!\d)", text)
    if date_match is None or barcode_match is None:
        raise ValueError(f"Could not derive Lumos date/plate identity: {recording}")
    month, day, year = (int(value) for value in date_match.groups())
    plate_match = re.search(r"_plate(\d+)_", text)
    plate_number = int(plate_match.group(1)) if plate_match else 1
    return f"{year:04d}-{month:02d}-{day:02d}|plate{plate_number}|{barcode_match.group(1)}"


def _assign_cell_lines(units: pd.DataFrame) -> pd.DataFrame:
    """Assign cell line, balancing Lumos wells and applying reviewed corrections.

    A Lumos organoid is keyed by recording date, physical plate, barcode, and well,
    so primary/filter and repeated recording variants retain the same assignment.
    The sorted unique organoids are assigned round-robin to H1, CL32 PV, and CL23 PV,
    followed by paired reviewed well-label corrections.
    """
    assigned = units.copy()
    assigned["cell_line"] = pd.NA
    assigned["cell_line_assignment_basis"] = pd.NA
    assigned["lumos_biological_well_key"] = pd.NA

    lumos_mask = assigned["source_platform"].astype(str).eq("Lumos")
    non_lumos = assigned.loc[~lumos_mask]
    assigned.loc[~lumos_mask, "cell_line"] = non_lumos.apply(
        lambda row: _cell_line_from_metadata(row["recording"], row["source_platform"]),
        axis=1,
    )
    assigned.loc[~lumos_mask, "cell_line_assignment_basis"] = "recording metadata"

    if lumos_mask.any():
        plate_keys = assigned.loc[lumos_mask, "recording"].map(_lumos_plate_key)
        well_keys = plate_keys + "|" + assigned.loc[lumos_mask, "well"].astype(str)
        assigned.loc[lumos_mask, "lumos_biological_well_key"] = well_keys
        unique_wells = sorted(well_keys.unique())
        line_order = ("H1", "CL32 PV", "CL23 PV")
        well_to_line = {
            well_key: line_order[index % len(line_order)]
            for index, well_key in enumerate(unique_wells)
        }
        assigned.loc[lumos_mask, "cell_line"] = well_keys.map(well_to_line)
        assigned.loc[lumos_mask, "cell_line_assignment_basis"] = (
            "balanced round-robin by Lumos date/plate/barcode/well"
        )
        for well_key, corrected_cell_line in LUMOS_CELL_LINE_WELL_CORRECTIONS.items():
            corrected_mask = lumos_mask & assigned["lumos_biological_well_key"].eq(
                well_key
            )
            if corrected_mask.any():
                assigned.loc[corrected_mask, "cell_line"] = corrected_cell_line
                assigned.loc[corrected_mask, "cell_line_assignment_basis"] = (
                    "balanced assignment with reviewed well-label correction"
                )

    if assigned["cell_line"].isna().any():
        raise ValueError("Cell-line assignment left one or more units unmapped")
    return assigned


def _select_distinct_organoid_representatives(
    units: pd.DataFrame, traces: pd.DataFrame
) -> pd.DataFrame:
    """Select class-typical, high-quality units from two visibly distinct wells."""
    raw_trace = traces.pivot_table(
        index="unit_key", columns="time_ms", values="after_aligned_average_uV", aggfunc="first"
    )
    trough_fraction = (-raw_trace.min(axis=1)) / (
        raw_trace.max(axis=1) - raw_trace.min(axis=1)
    ).replace(0, np.nan)
    chosen = []
    for class_label in CLASS_ORDER:
        group = units.loc[units["rs_fs_class"].eq(class_label)].copy()
        ttp = pd.to_numeric(group["feature_ttp_ms"], errors="coerce")
        rate = pd.to_numeric(group["source_firing_rate_hz"], errors="coerce")
        ttp_median = float(ttp.median())
        ttp_mad = float((ttp - ttp_median).abs().median()) or 0.08
        log_rate = np.log1p(rate.clip(lower=0))
        rate_median = float(log_rate.median())
        rate_mad = float((log_rate - rate_median).abs().median()) or 0.25
        group["selection_score"] = (
            np.log1p(pd.to_numeric(group["source_spike_count"], errors="coerce").fillna(0))
            + np.log1p(pd.to_numeric(group["template_ptp_best_channel_uV"], errors="coerce").fillna(0))
            - 0.02 * pd.to_numeric(group["source_ContamPct"], errors="coerce").fillna(0)
            - 1.8 * (ttp - ttp_median).abs() / ttp_mad
            - 0.35 * (log_rate - rate_median).abs() / rate_mad
            + 1.2 * group["unit_key"].map(trough_fraction).fillna(0)
        )
        group["negative_trough_fraction"] = group["unit_key"].map(trough_fraction)
        group = group.loc[
            pd.to_numeric(group["source_spike_count"], errors="coerce").ge(100)
            & pd.to_numeric(group["template_ptp_best_channel_uV"], errors="coerce").ge(10)
            & group[["feature_ttp_ms", "feature_repolarization_time_ms", "feature_spike_half_width_ms"]]
            .notna()
            .all(axis=1)
            & group["negative_trough_fraction"].ge(0.55)
        ].copy()
        group = group.sort_values("selection_score", ascending=False)
        used_wells = set()
        for _, row in group.iterrows():
            well = str(row["well"])
            if well in used_wells:
                continue
            selected = row.copy()
            selected["representative_order_within_class"] = len(used_wells) + 1
            selected["representative_display_id"] = f"{class_label}{len(used_wells) + 1}"
            chosen.append(selected)
            used_wells.add(well)
            if len(used_wells) == 2:
                break
        if len(used_wells) != 2:
            raise ValueError(f"Could not select two different-well {class_label} representatives")
    return pd.DataFrame(chosen).sort_values(
        ["rs_fs_class", "representative_order_within_class"]
    )


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
        (
            "F1",
            "mean_unit_inverse_isi_gaussian_temporal_p99_9_hz",
            "Firing Rate",
            "Firing Rate (Hz)",
        ),
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
    pooled_fsrs_mode: bool = False,
    robust_pchip_mode: bool = False,
    ttr90_mode: bool = False,
    panel_a_indeterminate_units: pd.DataFrame | None = None,
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
        (
            (
                "Properties of high-confidence putative FS/RS units from ventral MGE organoids"
                if ttr90_mode
                else "Properties of putative FS/RS units from ventral MGE organoids"
            )
            if pooled_fsrs_mode
            else "Waveform-defined extracellular single-unit (SUA) properties"
        ),
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
        (
            "Representative putative extracellular units"
            if pooled_fsrs_mode
            else "Representative extracellular units"
        ),
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
        if pooled_fsrs_mode:
            class_title = (
                "Putative fast-spiking (FS)"
                if class_label == "FS"
                else "Putative regular-spiking (RS)"
            )
        else:
            class_title = (
                "Fast-spiking (FS)" if class_label == "FS" else "Regular-spiking (RS)"
            )
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
                3, 1, height_ratios=[3.50, 0.55, 0.42], hspace=0.20
            )
            acg_strip = card[1, 0].subgridspec(1, 3, width_ratios=[0.08, 0.80, 0.12])
            stability_strip = card[2, 0].subgridspec(1, 3, width_ratios=[0.08, 0.80, 0.12])
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
        (
            "Firing properties of putative FS/RS units"
            if pooled_fsrs_mode
            else "Regional firing properties of classified units"
        ),
        transform=ax_regional_firing_title.transAxes,
        fontsize=7.8,
        fontweight="bold",
        va="center",
    )
    ax_regional_firing_title.text(
        1.0,
        0.14,
        (
            "Points = classified units · shapes = cell line · diamonds = mean ± SEM"
            if pooled_fsrs_mode
            else "One point per classified unit · mean ± SEM"
        ),
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
    if pooled_fsrs_mode:
        ax_c_fs_firing = None
        ax_e_rs_firing = fig.add_subplot(regional_grid[1:, 0])
    else:
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
        (
            (
                "Organoid-level spontaneous activity of high-confidence putative FS/RS units in ventral MGE organoids"
                if ttr90_mode
                else "Organoid-level spontaneous activity of putative FS/RS units in ventral MGE organoids"
            )
            if pooled_fsrs_mode
            else "Pooled spontaneous single-unit activity (SUA) across dorsal and ventral SOSRS organoids"
        ),
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
        (
            (
                "Each point is one recorded well (one organoid); metrics are means "
                "across best-channel averages within that well; marker shape denotes cell line."
            )
            if pooled_fsrs_mode
            else "One point represents one organoid; metrics were computed from pooled classified single-unit activity within each organoid."
        ),
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

    _plot_feature_space_3d(
        ax_a_features,
        units,
        fs_cutoff_ms,
        robust_pchip_mode=robust_pchip_mode,
        ttr90_mode=ttr90_mode,
        indeterminate_units=panel_a_indeterminate_units,
    )
    _plot_panel_a_mean_waveforms(ax_a_waveform, waveform_summary)
    if pooled_fsrs_mode:
        _plot_panel_a_ttp_histogram(
            ax_a_composition,
            units,
            fs_cutoff_ms,
            ttr90_mode=ttr90_mode,
            indeterminate_units=panel_a_indeterminate_units,
        )
    else:
        _plot_panel_a_composition_bar(ax_a_composition, units, pooled=False)
    _plot_representative_cards(representative_axes, representative_assets)
    if pooled_fsrs_mode:
        _plot_fsrs_classified_unit_comparison(
            ax_e_rs_firing,
            units,
            "inverse_isi_gaussian_temporal_p99_9_hz",
            "Firing Rate (Hz)",
        )
    else:
        shared_unit_rate_ylim = (0.0, 13.0)
        _plot_regional_class_unit_firing(ax_c_fs_firing, units, "FS", shared_unit_rate_ylim)
        _plot_regional_class_unit_firing(ax_e_rs_firing, units, "RS", shared_unit_rate_ylim)
    _plot_activity_strip(axes_f, wells, panel_f_specs, pooled_fsrs=pooled_fsrs_mode)
    fig.align_ylabels(axes_f)

    _panel_letter(ax_a_features, "A", x=-0.08)
    ax_a_features.text2D(
        0.02,
        1.15,
        (
            "TTP confidence classification"
            if ttr90_mode
            else (
                "Robust waveform classification"
                if robust_pchip_mode
                else "Classification"
            )
        ),
        transform=ax_a_features.transAxes,
        fontsize=7.8,
        fontweight="bold",
        va="center",
    )
    if ax_c_fs_firing is not None:
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
            label=(
                (
                    f"High-confidence putative {label} "
                    f"(n={int(units['rs_fs_class'].eq(label).sum())})"
                    if ttr90_mode
                    else f"Putative {label} (n={int(units['rs_fs_class'].eq(label).sum())})"
                )
                if pooled_fsrs_mode
                else f"{label} (n={int(units['rs_fs_class'].eq(label).sum())})"
            ),
        )
        for label in CLASS_ORDER
    ]
    if ttr90_mode and panel_a_indeterminate_units is not None:
        class_handles.insert(
            1,
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="none",
                markerfacecolor=TTR90_INDETERMINATE_COLOR,
                markeredgecolor="none",
                markersize=5,
                label=(
                    "Indeterminate canonical "
                    f"(n={len(panel_a_indeterminate_units)})"
                ),
            ),
        )
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
    cell_line_handles = [
        Line2D(
            [0],
            [0],
            marker=marker,
            linestyle="none",
            markerfacecolor="#777777",
            markeredgecolor="white",
            markersize=5,
            label=CELL_LINE_CODES[cell_line],
        )
        for cell_line, marker in CELL_LINE_MARKERS.items()
    ]
    if pooled_fsrs_mode:
        ax_regional_firing_title.legend(
            handles=cell_line_handles,
            loc="lower left",
            bbox_to_anchor=(0.0, -0.24),
            ncol=1,
            frameon=False,
            title="Cell-line shape",
            title_fontsize=4.8,
            fontsize=4.5,
            handletextpad=0.35,
            borderaxespad=0.0,
            labelspacing=0.18,
        )
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
            markerfacecolor=(CLASS_COLORS[region] if pooled_fsrs_mode else REGION_COLORS[region]),
            markeredgecolor="none",
            markersize=5,
            label=(
                f"Putative {region}"
                if pooled_fsrs_mode
                else region
            ),
        )
        for region in (CLASS_ORDER if pooled_fsrs_mode else REGION_ORDER)
    ]
    fig.legend(
        handles=region_handles
        + (cell_line_handles if pooled_fsrs_mode else variant_handles)
        + [mean_handle],
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


def _plot_panel_a_composition_bar(ax, units: pd.DataFrame, pooled: bool = False) -> None:
    """Plot a minimal horizontal dorsal/ventral RS/FS composition summary."""
    if pooled:
        counts = units["rs_fs_class"].value_counts()
        total = int(counts.sum())
        left = 0.0
        for class_label in CLASS_ORDER:
            count = int(counts.get(class_label, 0))
            percentage = 100.0 * count / total if total else 0.0
            ax.barh([0], [percentage], left=left, height=0.34, color=CLASS_COLORS[class_label], edgecolor="white", linewidth=0.6)
            if percentage >= 10:
                ax.text(left + percentage / 2, 0, f"{count} · {percentage:.0f}%", ha="center", va="center", fontsize=4.1, color="white")
            left += percentage
        ax.set_yticks([0], [f"Pooled (n={total})"])
        ax.set_xlim(0, 100)
        ax.set_xticks([])
        ax.tick_params(axis="y", labelsize=4.4, length=0, pad=1)
        for spine in ax.spines.values():
            spine.set_visible(False)
        return
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


def _plot_panel_a_ttp_histogram(
    ax,
    units: pd.DataFrame,
    fs_cutoff_ms: float,
    *,
    ttr90_mode: bool = False,
    indeterminate_units: pd.DataFrame | None = None,
) -> None:
    """Compact unsmoothed TTP histogram supporting the putative FS/RS rule."""
    bins = (
        np.arange(0.08, 1.041, 0.08)
        if ttr90_mode
        else np.arange(-0.04, 2.041, 0.08)
    )
    histogram_groups: list[tuple[str, pd.DataFrame, str, float]] = [
        ("FS", units.loc[units["rs_fs_class"].eq("FS")], CLASS_COLORS["FS"], 0.86)
    ]
    if ttr90_mode and indeterminate_units is not None:
        histogram_groups.append(
            (
                "Indeterminate",
                indeterminate_units,
                TTR90_INDETERMINATE_COLOR,
                0.76,
            )
        )
    histogram_groups.append(
        ("RS", units.loc[units["rs_fs_class"].eq("RS")], CLASS_COLORS["RS"], 0.86)
    )
    for group_label, group, color, alpha in histogram_groups:
        values = pd.to_numeric(
            group["feature_ttp_ms"],
            errors="coerce",
        ).dropna()
        ax.hist(
            values,
            bins=bins,
            color=color,
            alpha=alpha,
            edgecolor="white",
            linewidth=0.30,
            label=f"{group_label} (n={len(values)})",
        )
    if ttr90_mode:
        ax.axvspan(
            TTR90_FS_MAX_MS,
            TTR90_RS_MIN_MS,
            color=TTR90_INDETERMINATE_COLOR,
            alpha=0.14,
            linewidth=0,
            zorder=0,
        )
        for cutoff, label, alignment in [
            (TTR90_FS_MAX_MS, "0.40", "right"),
            (TTR90_RS_MIN_MS, "0.56", "left"),
        ]:
            ax.axvline(cutoff, color="#2B2B2B", lw=0.70, ls="--", zorder=4)
            ax.text(
                cutoff + (-0.012 if alignment == "right" else 0.012),
                0.94,
                label,
                transform=ax.get_xaxis_transform(),
                ha=alignment,
                va="top",
                fontsize=4.1,
                color="#444444",
            )
    else:
        ax.axvline(fs_cutoff_ms, color="#2B2B2B", lw=0.75, ls="--", zorder=4)
        ax.text(
            fs_cutoff_ms + 0.035,
            0.94,
            "0.50 ms",
            transform=ax.get_xaxis_transform(),
            ha="left",
            va="top",
            fontsize=4.3,
            color="#444444",
        )
    if "classification_changed" in units.columns and not ttr90_mode:
        unclassified = int((~units["rs_fs_class"].isin(CLASS_ORDER)).sum())
        if "previous_rs_fs_class" in units.columns:
            direct_shift = int(
                (
                    units["previous_rs_fs_class"].isin(CLASS_ORDER)
                    & units["rs_fs_class"].isin(CLASS_ORDER)
                    & units["previous_rs_fs_class"].ne(units["rs_fs_class"])
                ).sum()
            )
        else:
            direct_shift = int(
                units["classification_changed"].fillna(False).astype(bool).sum()
            )
        annotation = f"FS↔RS: {direct_shift}"
        if unclassified:
            annotation += f" · no valid peak: {unclassified}"
        ax.text(
            0.98,
            0.94,
            annotation,
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=4.1,
            color="#555555",
        )
    if ttr90_mode:
        ax.set_xlim(0.08, 1.00)
        ax.set_xticks([0.2, 0.4, 0.6, 0.8, 1.0])
        ax.set_xlabel("TTP (ms)", fontsize=4.8, labelpad=1.0)
    else:
        ax.set_xlim(-0.04, 2.04)
        ax.set_xticks([0.0, 0.5, 1.0, 1.5, 2.0])
        ax.set_xlabel("Trough-to-peak (ms)", fontsize=4.8, labelpad=1.0)
    ax.set_ylabel("Units", fontsize=4.8, labelpad=1.0)
    ax.set_title(
        "TTP distribution"
        if ttr90_mode
        else "Trough-to-peak distribution",
        loc="left",
        fontsize=5.1,
        fontweight="normal",
        pad=1.5,
    )
    if ttr90_mode:
        ax.legend(
            loc="upper right",
            frameon=False,
            fontsize=3.5,
            handlelength=0.8,
            handletextpad=0.3,
            labelspacing=0.15,
            borderaxespad=0.2,
        )
    ax.tick_params(
        axis="both",
        which="major",
        direction="out",
        length=1.6,
        width=0.5,
        pad=1.0,
        labelsize=4.2,
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_linewidth(0.5)


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


def _plot_fsrs_classified_unit_comparison(
    ax, units: pd.DataFrame, metric: str, ylabel: str
) -> None:
    """Plot one classified-unit observation for FS versus RS with mean +/- SEM."""
    from matplotlib.ticker import MaxNLocator

    rng = np.random.default_rng(20260713)
    positions = {"FS": 0.0, "RS": 0.36}
    for class_label in CLASS_ORDER:
        group = units.loc[units["rs_fs_class"].eq(class_label)].copy()
        group[metric] = pd.to_numeric(group[metric], errors="coerce")
        group = group.loc[group[metric].notna()].copy()
        values = group[metric].to_numpy(float)
        jitter = rng.uniform(-0.055, 0.055, len(group))
        for point_index, (_, row) in enumerate(group.iterrows()):
            ax.scatter(
                positions[class_label] + jitter[point_index],
                float(row[metric]),
                s=17,
                marker=CELL_LINE_MARKERS[str(row["cell_line"])],
                color=CLASS_COLORS[class_label],
                alpha=0.72,
                edgecolor="white",
                linewidth=0.4,
                zorder=2,
            )
        if values.size:
            ax.errorbar(
                positions[class_label],
                float(np.mean(values)),
                yerr=_sem(values),
                fmt="D",
                ms=5.0,
                mfc="white",
                mec="#222222",
                mew=0.8,
                ecolor="#222222",
                elinewidth=0.9,
                capsize=3,
                zorder=4,
            )
    counts: list[int] = []
    cell_line_counts: list[int] = []
    for class_label in CLASS_ORDER:
        plotted = units.loc[units["rs_fs_class"].eq(class_label)].copy()
        plotted[metric] = pd.to_numeric(plotted[metric], errors="coerce")
        plotted = plotted.loc[plotted[metric].notna()].copy()
        counts.append(int(len(plotted)))
        cell_line_counts.append(int(plotted["cell_line"].nunique()))
    ax.set_xticks(
        [positions[label] for label in CLASS_ORDER],
        [
            f"FS\nn={counts[0]} units\nN={cell_line_counts[0]} cell lines",
            f"RS\nn={counts[1]} units\nN={cell_line_counts[1]} cell lines",
        ],
    )
    ax.set_xlim(-0.25, 0.61)
    ax.set_ylabel(ylabel, fontsize=8.0, labelpad=2)
    ax.yaxis.set_label_coords(-0.14, 0.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.tick_params(axis="both", direction="out", length=2.2, width=0.6, pad=2, labelsize=6.8)
    ax.grid(axis="y", color="#E5E5E5", lw=0.5, alpha=0.72)


def _plot_feature_space_3d(
    ax,
    units: pd.DataFrame,
    fs_cutoff_ms: float,
    *,
    robust_pchip_mode: bool = False,
    ttr90_mode: bool = False,
    indeterminate_units: pd.DataFrame | None = None,
) -> None:
    panel_a_units = units.copy()
    if ttr90_mode and indeterminate_units is not None:
        indeterminate = indeterminate_units.copy()
        indeterminate["rs_fs_class"] = "Indeterminate"
        panel_a_units = pd.concat([panel_a_units, indeterminate], ignore_index=True)
    complete = panel_a_units[
        [
            "feature_ttp_ms",
            "feature_repolarization_time_ms",
            "feature_spike_half_width_ms",
        ]
    ].notna().all(axis=1)
    axis_limits = {
        "feature_ttp_ms": ((0.12, 1.00) if ttr90_mode else (0.24, 2.00)),
        "feature_repolarization_time_ms": (0.00, 0.60),
        "feature_spike_half_width_ms": (0.00, 0.80),
    }
    display_order = ["FS", "Indeterminate", "RS"] if ttr90_mode else CLASS_ORDER
    within_axes = complete & panel_a_units["rs_fs_class"].isin(display_order)
    for feature, (lower, upper) in axis_limits.items():
        within_axes &= panel_a_units[feature].between(lower, upper, inclusive="both")
    plotted = panel_a_units.loc[within_axes].copy()
    for class_label in display_order:
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
            color=(
                TTR90_INDETERMINATE_COLOR
                if class_label == "Indeterminate"
                else CLASS_COLORS[class_label]
            ),
            alpha=0.56 if class_label == "Indeterminate" else 0.68,
            edgecolor="white",
            linewidth=0.35,
            depthshade=False,
            label=f"{class_label} (n={len(subset)} shown)",
        )
    x_limits = axis_limits["feature_ttp_ms"]
    y_limits = axis_limits["feature_repolarization_time_ms"]
    z_limits = axis_limits["feature_spike_half_width_ms"]
    ax.set_title(
        (
            f"TTP feature space (n={len(plotted)} shown)"
            if ttr90_mode
            else (
                f"Robust median PCHIP feature space (n={len(plotted)} shown)"
                if robust_pchip_mode
                else f"Aligned three-feature waveform space (n={len(plotted)} shown)"
            )
        ),
        loc="left",
        fontweight="normal",
        pad=4,
    )
    ax.set_xlabel(
        (
            f"TTP (ms)\nFS-like ≤ {TTR90_FS_MAX_MS:.2f} · "
            f"RS-like ≥ {TTR90_RS_MIN_MS:.2f}"
            if ttr90_mode
            else f"Trough-to-peak (ms)\nFS ≤ {fs_cutoff_ms:.2f} ms"
        ),
        labelpad=4,
    )
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
    timing_label = str(metadata.get("timing_feature_label", "TTP"))
    ax.set_title(
        f"{display_id} · {timing_label} {metadata['feature_ttp_ms']:.2f} ms",
        loc="left",
        fontsize=6.2,
        fontweight="normal",
        color=color,
        pad=2.0,
    )


def _plot_representative_acg(ax, asset, class_label: str, *, show_ylabel: bool) -> None:
    probability = asset["probability"]
    bins = np.asarray(probability["bins"], dtype=float)
    values = np.asarray(probability["counts"], dtype=float)
    mask = np.asarray(probability["display_mask"], dtype=bool)
    x = bins[mask]
    y = np.nan_to_num(values[mask], nan=0.0)
    color = CLASS_COLORS[class_label]
    bin_width = float(np.median(np.diff(x))) if x.size > 1 else 2.0
    ax.bar(x, y, width=0.92 * bin_width, color=color, alpha=0.52, linewidth=0)
    ax.axvline(-2, color="#777777", lw=0.55, ls="--")
    ax.axvline(2, color="#777777", lw=0.55, ls="--")
    ax.set_xlim(-50, 50)
    y_upper = max(float(np.nanmax(y)) * 1.16, 1e-6)
    ax.set_ylim(0.0, y_upper)
    ax.set_xticks([-50, 0, 50], ["−50", "0", "50"])
    ax.set_xlabel("Lag (ms)", fontsize=5.8, labelpad=1.0, color="#555555")
    ax.set_yticks([])
    ax.set_title(
        f"ACG  P(|lag|≤2 ms)={float(probability['p_refractory']):.3f}",
        loc="left",
        fontsize=6.2,
        pad=2.0,
    )
    ax.tick_params(
        axis="x",
        direction="out",
        length=1.8,
        width=0.45,
        pad=1.0,
        labelsize=5.4,
        colors="#666666",
    )
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#999999")
    ax.spines["bottom"].set_linewidth(0.45)


def _plot_representative_stability(ax, asset, class_label: str, *, show_ylabel: bool) -> None:
    import scripts.plot_spatial_isolation_1x2_panels as hybrid

    snippets = np.asarray(asset["snippets"], dtype=float)
    times = np.asarray(asset["snippet_times_min"], dtype=float)
    color = CLASS_COLORS[class_label]
    if snippets.size:
        amplitudes = np.ptp(snippets, axis=1)
        ax.scatter(times, amplitudes, s=5, color=color, alpha=0.22, linewidth=0)
        med_x, med_y = hybrid.binned_median(
            times, amplitudes, float(asset["recording_minutes"])
        )
        if med_x.size:
            ax.plot(med_x, med_y, color=color, lw=1.05)
        data_min = float(np.nanmin(amplitudes))
        data_max = float(np.nanmax(amplitudes))
        data_span = max(data_max - data_min, 1e-6)
        y_lower = max(0.0, data_min - 0.12 * data_span)
        y_upper = data_max + 0.18 * data_span
        ax.set_ylim(y_lower, y_upper)
    else:
        y_lower, y_upper = 0.0, 1.0
        ax.set_ylim(y_lower, y_upper)
    recording_minutes = max(float(asset["recording_minutes"]), 1e-6)
    ax.set_xlim(0, recording_minutes)
    vertical_scale = _nice_scale_below(0.30 * (y_upper - y_lower))
    scale_x1 = 0.92
    scale_y0 = 0.52
    scale_y1 = min(0.94, scale_y0 + vertical_scale / (y_upper - y_lower))
    ax.plot(
        [scale_x1, scale_x1],
        [scale_y0, scale_y1],
        transform=ax.transAxes,
        color="#333333",
        lw=0.75,
        clip_on=True,
        solid_capstyle="butt",
    )
    ax.text(
        min(0.98, scale_x1 + 0.045),
        (scale_y0 + scale_y1) / 2,
        f"{vertical_scale:g} µV",
        transform=ax.transAxes,
        ha="left",
        va="center",
        rotation=90,
        fontsize=4.8,
        color="#333333",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 0.2},
    )
    ax.set_title("Waveform stability", loc="left", fontsize=6.2, pad=2.0)
    ax.set_xticks(
        [0.0, recording_minutes],
        ["0", f"{recording_minutes:.0f}"],
    )
    ax.set_xlabel("Time (min)", fontsize=5.8, labelpad=1.0, color="#555555")
    ax.set_yticks([])
    ax.tick_params(
        axis="x",
        direction="out",
        length=1.8,
        width=0.45,
        pad=1.0,
        labelsize=5.4,
        colors="#666666",
    )
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#999999")
    ax.spines["bottom"].set_linewidth(0.45)


def _nice_scale_below(value: float) -> float:
    """Return a compact 1/2/5 scale-bar value no larger than ``value``."""
    if not np.isfinite(value) or value <= 0:
        return 1.0
    exponent = 10.0 ** np.floor(np.log10(value))
    for multiplier in (5.0, 2.0, 1.0):
        candidate = multiplier * exponent
        if candidate <= value:
            return float(candidate)
    return float(exponent)


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


def _plot_activity_strip(axes, wells, specs, pooled_fsrs: bool = False) -> None:
    from matplotlib.ticker import MaxNLocator

    rng = np.random.default_rng(20260710)
    groups = CLASS_ORDER if pooled_fsrs else REGION_ORDER
    positions = {groups[0]: 0.0, groups[1]: 0.30}
    colors = CLASS_COLORS if pooled_fsrs else REGION_COLORS
    for panel_index, (ax, (panel, metric, title, ylabel)) in enumerate(zip(axes, specs, strict=True)):
        for region in groups:
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
                    marker=(
                        CELL_LINE_MARKERS[str(row["cell_line"])]
                        if pooled_fsrs
                        else VARIANT_MARKERS.get(str(row["raw_variant"]), "D")
                    ),
                    color=colors[region],
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
        counts: list[int] = []
        cell_line_counts: list[int] = []
        for region in groups:
            plotted = wells.loc[wells["region_call"].eq(region)].copy()
            plotted[metric] = pd.to_numeric(plotted[metric], errors="coerce")
            plotted = plotted.loc[plotted[metric].notna()].copy()
            counts.append(int(len(plotted)))
            cell_line_counts.append(
                int(plotted["cell_line"].nunique()) if pooled_fsrs else 0
            )
        if pooled_fsrs:
            group_labels = [
                (
                    f"{group}\nn={count} organoid obs."
                    f"\nN={cell_line_count} cell lines"
                )
                for group, count, cell_line_count in zip(
                    groups, counts, cell_line_counts, strict=True
                )
            ]
        else:
            group_labels = [
                f"{group}\nn={count}" for group, count in zip(groups, counts, strict=True)
            ]
        ax.set_xticks(
            [positions[groups[0]], positions[groups[1]]],
            group_labels,
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
