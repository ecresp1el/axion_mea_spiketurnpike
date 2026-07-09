#!/usr/bin/env python
"""Build Wave 0 representative-unit index from current Step 1 unit tables."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_JOB_DIR = PROJECT_ROOT / "jobs" / "step1_nonlfp_th5_v5_ground_truth_latest"
DEFAULT_AIND_RESULTS_ROOT = PROJECT_ROOT / "results" / "aind"
DEFAULT_STEP2_ROOT = (
    PROJECT_ROOT
    / "results"
    / "aind_unit_classification_step2_full"
    / "aind_unit_classification_step2_full_20260708_153945"
)
RECORDING_NAME = "block0_None_recording1"
EXPECTED_DENOMINATORS = {"lumos_geometry": 276, "cytoview_dv": 237}
METRIC_COLUMNS = [
    "trough_to_peak_duration_ms",
    "spike_half_width_ms",
    "repolarization_time_ms",
    "spiketurnpike_amplitude_uV",
    "template_ptp_best_channel_uV",
    "rep50_recovery_slope_uV_per_ms",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--date-label", default="20260709")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--aind-results-root", type=Path, default=DEFAULT_AIND_RESULTS_ROOT)
    parser.add_argument("--step2-root", type=Path, default=DEFAULT_STEP2_ROOT)
    args = parser.parse_args()

    job_dir = args.job_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    lumos_csv = (
        job_dir
        / f"lumos_geometry_alignment_cutoff_composite_{args.date_label}"
        / f"lumos_geometry_alignment_cutoff_composite_{args.date_label}_classified_units_long.csv"
    )
    cytoview_csv = (
        job_dir
        / f"cytoview_dv_alignment_cutoff_composite_{args.date_label}"
        / f"cytoview_dv_alignment_cutoff_composite_{args.date_label}_classified_units_long.csv"
    )
    optotag_screen_csv = job_dir / f"lumos_gui_ready_trial_tag_screen_250pulse_jitterwin_{args.date_label}.csv"
    optotag_guide_csv = job_dir / f"lumos_manual_spike_sorting_guide_jitterwin_{args.date_label}.csv"

    lumos = _collapse_classified_units(
        pd.read_csv(lumos_csv),
        track="lumos_geometry",
        date_label=args.date_label,
        aind_results_root=args.aind_results_root,
        step2_root=args.step2_root,
    )
    cytoview = _collapse_classified_units(
        pd.read_csv(cytoview_csv),
        track="cytoview_dv",
        date_label=args.date_label,
        aind_results_root=args.aind_results_root,
        step2_root=args.step2_root,
    )
    index = pd.concat([lumos, cytoview], ignore_index=True)
    index = _attach_lumos_optotag(index, optotag_screen_csv, optotag_guide_csv)
    index = _add_selection_placeholders(index)
    index = _ordered_columns(index)

    index_csv = output_dir / f"representative_unit_index_{args.date_label}.csv"
    summary_csv = output_dir / f"representative_unit_index_{args.date_label}_summary.csv"
    reconciliation_csv = output_dir / f"wave0_reconciliation_table_{args.date_label}.csv"
    missing_csv = output_dir / f"wave0_missing_assets_{args.date_label}.csv"
    denominator_csv = output_dir / f"wave0_denominator_summary_{args.date_label}.csv"
    provenance_json = output_dir / f"representative_unit_index_{args.date_label}_provenance.json"

    summary = _summary_table(index)
    reconciliation = _reconciliation_table(index)
    missing = _missing_assets_table(index)
    denominator = _denominator_summary(index)

    index.to_csv(index_csv, index=False)
    summary.to_csv(summary_csv, index=False)
    reconciliation.to_csv(reconciliation_csv, index=False)
    missing.to_csv(missing_csv, index=False)
    denominator.to_csv(denominator_csv, index=False)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "date_label": args.date_label,
        "job_dir": str(job_dir),
        "aind_results_root": str(args.aind_results_root),
        "step2_root": str(args.step2_root),
        "inputs": {
            "lumos_classified_units_long_csv": str(lumos_csv),
            "cytoview_classified_units_long_csv": str(cytoview_csv),
            "lumos_optotag_screen_csv": str(optotag_screen_csv),
            "lumos_manual_guide_csv": str(optotag_guide_csv),
        },
        "outputs": {
            "representative_unit_index_csv": str(index_csv),
            "representative_unit_index_summary_csv": str(summary_csv),
            "wave0_reconciliation_table_csv": str(reconciliation_csv),
            "wave0_missing_assets_csv": str(missing_csv),
            "wave0_denominator_summary_csv": str(denominator_csv),
        },
        "policy": [
            "KSLabel=good remains the ground-truth inclusion label.",
            "Step 2/QC assets are linked as metadata and are not replacement truth.",
            "Missing optional linked assets are recorded rather than silently filtered.",
            "This Wave 0 job builds manifests only; A/B/C scoring is a later targeted wave.",
        ],
    }
    provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Representative unit index: {index_csv}")
    print(f"Rows: {len(index)}")
    print("Denominator summary:")
    print(denominator.to_string(index=False))
    return 0


def _collapse_classified_units(
    table: pd.DataFrame,
    *,
    track: str,
    date_label: str,
    aind_results_root: Path,
    step2_root: Path,
) -> pd.DataFrame:
    required = {"unit_key", "recording", "well", "unit_id", "KSLabel", "cutoff_ms", "stage"}
    missing = required.difference(table.columns)
    if missing:
        raise ValueError(f"{track} classified table missing required columns: {sorted(missing)}")

    base_cols = [
        "unit_key",
        "recording",
        "well",
        "unit_id",
        "unit_index",
        "KSLabel",
        "best_channel_index",
        "usable_snippets",
        "plate_family",
    ]
    optional_cols = ["well_column", "geometry_group", "region_call", "plate_id", "firing_rate_hz"]
    base = table[[col for col in base_cols + optional_cols if col in table.columns]].drop_duplicates("unit_key").copy()
    base["track"] = track
    base["source_denominator"] = f"{track}_{date_label}"
    base["region_label"] = base.get("region_call", pd.Series("", index=base.index)).fillna("")
    base["lumos_geometry_group"] = base.get("geometry_group", pd.Series("", index=base.index)).fillna("")
    base["ks_label"] = base["KSLabel"].astype(str).str.lower()
    base["sorting_unit_id"] = base["unit_id"]
    base["analyzer_path"] = [
        str(aind_results_root / str(row.recording) / str(row.well) / "postprocessed" / f"{RECORDING_NAME}.zarr")
        for row in base.itertuples(index=False)
    ]
    base["has_step1_analyzer"] = base["analyzer_path"].map(lambda value: Path(value).is_dir())
    base["step2_result_path"] = [
        str(step2_root / str(row.recording) / str(row.well)) for row in base.itertuples(index=False)
    ]
    base["has_step2_linked_assets"] = base["step2_result_path"].map(lambda value: Path(value).is_dir())
    base["has_quality_metrics_required_diagnostic"] = base["step2_result_path"].map(
        lambda value: (Path(value) / "quality_metrics_required_diagnostic.json").is_file()
    )
    base["has_unit_labels_csv"] = base["step2_result_path"].map(
        lambda value: (Path(value) / "curation" / f"unit_labels_{RECORDING_NAME}.csv").is_file()
    )

    for stage in ["unaligned", "aligned"]:
        subset = table.loc[table["stage"].eq(stage)].drop_duplicates("unit_key")
        subset = subset.set_index("unit_key")
        suffix = "unaligned" if stage == "unaligned" else "aligned"
        for metric in METRIC_COLUMNS:
            if metric in subset.columns:
                base[f"{_metric_output_name(metric)}_{suffix}"] = base["unit_key"].map(subset[metric])

    for cutoff in sorted(pd.to_numeric(table["cutoff_ms"], errors="coerce").dropna().unique()):
        label = _cutoff_label(float(cutoff))
        for stage in ["unaligned", "aligned"]:
            subset = table.loc[table["stage"].eq(stage) & np.isclose(pd.to_numeric(table["cutoff_ms"], errors="coerce"), cutoff)]
            mapping = subset.drop_duplicates("unit_key").set_index("unit_key")["ttp_cutoff_classification"]
            base[f"fs_rs_cutoff_{label}_{stage}"] = base["unit_key"].map(mapping)

    if "firing_rate_hz" not in base.columns:
        base["firing_rate_hz"] = np.nan
    return base


def _attach_lumos_optotag(index: pd.DataFrame, screen_csv: Path, guide_csv: Path) -> pd.DataFrame:
    out = index.copy()
    for column in [
        "opto_status",
        "opto_review_rank",
        "opto_response_rate_hz",
        "opto_peak_raw_response_hz",
        "opto_train_response_rate_hz",
        "opto_train_peak_raw_response_hz",
        "opto_reason",
    ]:
        out[column] = np.nan if column != "opto_status" and column != "opto_reason" else ""

    if screen_csv.is_file():
        screen = pd.read_csv(screen_csv)
        well_status = screen[["recording", "well", "status", "reason"]].drop_duplicates(["recording", "well"])
        out = out.merge(well_status, on=["recording", "well"], how="left", suffixes=("", "_well_opto"))
        out["opto_status"] = out["status"].fillna(out["opto_status"])
        out["opto_reason"] = out["reason"].fillna(out["opto_reason"])
        out = out.drop(columns=[col for col in ["status", "reason"] if col in out.columns])

    if guide_csv.is_file():
        guide = pd.read_csv(guide_csv)
        guide = guide.loc[guide["top_unit"].notna()].copy()
        guide["unit_id"] = pd.to_numeric(guide["top_unit"], errors="coerce").astype("Int64").astype(str)
        out["unit_id_merge"] = pd.to_numeric(out["unit_id"], errors="coerce").astype("Int64").astype(str)
        guide_cols = [
            "recording",
            "well",
            "unit_id",
            "review_rank",
            "review_sort_peak_raw_response_hz",
            "score_hz",
            "train_response_rate_hz",
            "train_response_peak_raw_rate_hz",
            "reason",
        ]
        guide = guide[[col for col in guide_cols if col in guide.columns]].rename(
            columns={
                "review_rank": "opto_review_rank",
                "review_sort_peak_raw_response_hz": "opto_peak_raw_response_hz",
                "score_hz": "opto_response_rate_hz",
                "train_response_rate_hz": "opto_train_response_rate_hz",
                "train_response_peak_raw_rate_hz": "opto_train_peak_raw_response_hz",
                "reason": "opto_top_unit_reason",
            }
        )
        out = out.merge(
            guide,
            left_on=["recording", "well", "unit_id_merge"],
            right_on=["recording", "well", "unit_id"],
            how="left",
            suffixes=("", "_guide"),
        )
        for col in [
            "opto_review_rank",
            "opto_peak_raw_response_hz",
            "opto_response_rate_hz",
            "opto_train_response_rate_hz",
            "opto_train_peak_raw_response_hz",
        ]:
            guide_col = f"{col}_guide"
            if guide_col in out.columns:
                out[col] = out[guide_col].combine_first(out[col])
        if "opto_top_unit_reason" in out.columns:
            out["opto_reason"] = out["opto_top_unit_reason"].fillna(out["opto_reason"])
        out = out.drop(columns=[col for col in out.columns if col.endswith("_guide") or col in {"unit_id_merge", "unit_id_guide", "opto_top_unit_reason"}])
    return out


def _add_selection_placeholders(index: pd.DataFrame) -> pd.DataFrame:
    out = index.copy()
    placeholders = {
        "num_spikes": np.nan,
        "duration_s": np.nan,
        "presence_ratio": np.nan,
        "isi_violation_ratio": np.nan,
        "isi_violations_count": np.nan,
        "amplitude_cutoff": np.nan,
        "snr": np.nan,
        "firing_rate_bin_count": np.nan,
        "firing_rate_bin_size_s": np.nan,
        "firing_rate_cv": np.nan,
        "firing_rate_slope_hz_per_min": np.nan,
        "amplitude_bin_count": np.nan,
        "amplitude_median_uV": np.nan,
        "amplitude_cv": np.nan,
        "waveform_template_correlation_min": np.nan,
        "waveform_template_correlation_median": np.nan,
        "waveform_ptp_cv": np.nan,
        "best_channel_id": "",
        "best_channel_x": np.nan,
        "best_channel_y": np.nan,
        "template_centroid_x": np.nan,
        "template_centroid_y": np.nan,
        "template_spatial_spread_um": np.nan,
        "neighbor_channel_count": np.nan,
        "selection_pool": "wave0_index",
        "selection_reason": "current denominator unit; no A/B/C scoring applied yet",
        "manual_override_flag": False,
        "manual_override_reason": "",
        "gui_equivalent_rendered": False,
        "gui_equivalent_render_sources": "",
        "gui_equivalent_render_notes": "",
        "waveform_panel_source": "",
        "maintemplate_panel_source": "",
        "correlogram_panel_source": "",
        "isi_panel_source": "",
        "spikerate_panel_source": "",
        "probe_panel_source": "",
        "similarity_panel_source": "",
        "human_spotcheck_status": "",
        "human_spotcheck_notes": "",
    }
    for column, value in placeholders.items():
        if column not in out.columns:
            out[column] = value
    return out


def _ordered_columns(index: pd.DataFrame) -> pd.DataFrame:
    first = [
        "recording",
        "well",
        "unit_id",
        "unit_key",
        "analyzer_path",
        "sorting_unit_id",
        "ks_label",
        "KSLabel",
        "plate_family",
        "track",
        "region_label",
        "lumos_geometry_group",
        "source_denominator",
        "has_step1_analyzer",
        "has_step2_linked_assets",
        "step2_result_path",
        "has_quality_metrics_required_diagnostic",
        "has_unit_labels_csv",
        "firing_rate_hz",
    ]
    rest = [col for col in index.columns if col not in first]
    return index[first + rest]


def _summary_table(index: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for track, subset in index.groupby("track", dropna=False):
        rows.append(
            {
                "track": track,
                "unit_count": int(len(subset)),
                "expected_denominator": EXPECTED_DENOMINATORS.get(str(track), np.nan),
                "kslabel_good_count": int(subset["ks_label"].astype(str).str.lower().eq("good").sum()),
                "has_step1_analyzer_count": int(subset["has_step1_analyzer"].sum()),
                "has_step2_linked_assets_count": int(subset["has_step2_linked_assets"].sum()),
                "has_quality_metrics_required_diagnostic_count": int(
                    subset["has_quality_metrics_required_diagnostic"].sum()
                ),
                "has_unit_labels_csv_count": int(subset["has_unit_labels_csv"].sum()),
            }
        )
    return pd.DataFrame(rows)


def _reconciliation_table(index: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for track, subset in index.groupby("track", dropna=False):
        expected = EXPECTED_DENOMINATORS.get(str(track), np.nan)
        rows.append(
            {
                "track": track,
                "starting_population": "current cutoff/alignment composite unique units",
                "expected_denominator": expected,
                "observed_units": int(len(subset)),
                "matches_expected": bool(len(subset) == expected),
                "kslabel_good_units": int(subset["ks_label"].astype(str).str.lower().eq("good").sum()),
                "valid_unaligned_ttp": int(subset["trough_to_peak_duration_ms_unaligned"].notna().sum()),
                "valid_aligned_ttp": int(subset["trough_to_peak_duration_ms_aligned"].notna().sum()),
                "valid_unaligned_half_width": int(subset["half_width_ms_unaligned"].notna().sum()),
                "valid_aligned_half_width": int(subset["half_width_ms_aligned"].notna().sum()),
                "valid_unaligned_rep50": int(subset["rep50_ms_unaligned"].notna().sum()),
                "valid_aligned_rep50": int(subset["rep50_ms_aligned"].notna().sum()),
                "missing_step1_analyzer": int((~subset["has_step1_analyzer"]).sum()),
                "missing_step2_linked_assets": int((~subset["has_step2_linked_assets"]).sum()),
            }
        )
    return pd.DataFrame(rows)


def _missing_assets_table(index: pd.DataFrame) -> pd.DataFrame:
    rows = []
    checks = [
        ("missing_step1_analyzer", "has_step1_analyzer", True),
        ("missing_step2_linked_assets", "has_step2_linked_assets", True),
        ("missing_quality_metrics_required_diagnostic", "has_quality_metrics_required_diagnostic", True),
        ("missing_unit_labels_csv", "has_unit_labels_csv", True),
    ]
    for reason, column, expected in checks:
        missing = index.loc[index[column] != expected]
        for row in missing.itertuples(index=False):
            rows.append(
                {
                    "track": row.track,
                    "recording": row.recording,
                    "well": row.well,
                    "unit_id": row.unit_id,
                    "reason": reason,
                    "path": row.analyzer_path if reason == "missing_step1_analyzer" else row.step2_result_path,
                }
            )
    return pd.DataFrame(rows, columns=["track", "recording", "well", "unit_id", "reason", "path"])


def _denominator_summary(index: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for track, subset in index.groupby("track", dropna=False):
        expected = EXPECTED_DENOMINATORS.get(str(track), np.nan)
        rows.append(
            {
                "track": track,
                "expected_denominator": expected,
                "observed_unique_units": int(len(subset)),
                "difference": int(len(subset) - expected) if not pd.isna(expected) else np.nan,
                "all_kslabel_good": bool(subset["ks_label"].astype(str).str.lower().eq("good").all()),
                "step1_analyzer_ready_units": int(subset["has_step1_analyzer"].sum()),
                "step2_linked_asset_units": int(subset["has_step2_linked_assets"].sum()),
            }
        )
    return pd.DataFrame(rows)


def _metric_output_name(metric: str) -> str:
    return {
        "trough_to_peak_duration_ms": "trough_to_peak_duration_ms",
        "spike_half_width_ms": "half_width_ms",
        "repolarization_time_ms": "rep50_ms",
        "spiketurnpike_amplitude_uV": "amplitude_uV",
        "template_ptp_best_channel_uV": "template_ptp_best_channel_uV",
        "rep50_recovery_slope_uV_per_ms": "rep50_recovery_slope_uV_per_ms",
    }[metric]


def _cutoff_label(cutoff: float) -> str:
    return f"{cutoff:.2f}".replace(".", "p")


if __name__ == "__main__":
    raise SystemExit(main())
