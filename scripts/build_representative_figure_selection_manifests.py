#!/usr/bin/env python
"""Build final representative-figure selection manifests from A/B/C scores.

This step intentionally separates Lumos geometry and Cytoview dorsal/ventral
selection pools. It does not deduplicate raw/filter/broadband variants; the
recording stem remains part of the analyzed identity.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_JOB_DIR = PROJECT_ROOT / "jobs" / "step1_nonlfp_th5_v5_ground_truth_latest"
DEFAULT_SCORE_ROOT = DEFAULT_JOB_DIR / "representative_units_20260709_abc_scoring_20260709_172908"


SELECTION_GROUPS = {
    "lumos": {
        "track": "lumos_geometry",
        "region_label": "",
        "description": "Lumos/opto-track geometry; not dorsal/ventral biology",
    },
    "cytoview_dorsal": {
        "track": "cytoview_dv",
        "region_label": "dorsal",
        "description": "Cytoview/SixWell plate-map-backed dorsal wells",
    },
    "cytoview_ventral": {
        "track": "cytoview_dv",
        "region_label": "ventral",
        "description": "Cytoview/SixWell plate-map-backed ventral wells",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-root", type=Path, default=DEFAULT_SCORE_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--date-label", default="20260709")
    parser.add_argument("--top-n-stability-per-group", type=int, default=6)
    parser.add_argument("--top-n-pairs-per-group", type=int, default=6)
    parser.add_argument("--top-n-wells-per-group", type=int, default=4)
    args = parser.parse_args()

    score_root = args.score_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    stability = pd.read_csv(score_root / f"waveA_stability_candidate_scores_{args.date_label}.csv")
    pairs = pd.read_csv(score_root / f"waveB_correlogram_pair_scores_{args.date_label}.csv")
    spatial_units = pd.read_csv(score_root / f"waveC_spatial_footprint_unit_scores_{args.date_label}.csv")

    stability = _add_selection_group(stability)
    spatial_units = _add_selection_group(spatial_units)
    pairs = _annotate_pairs(pairs, stability)
    wells = _build_well_scores(spatial_units, pairs)

    selected_tables: dict[str, pd.DataFrame] = {}
    summary_rows: list[dict[str, object]] = []
    for group_name, spec in SELECTION_GROUPS.items():
        group_stability = _filter_group(stability, group_name)
        group_pairs = _filter_group(pairs, group_name)
        group_wells = _filter_group(wells, group_name)

        selected_stability = _select_stability(group_stability, args.top_n_stability_per_group)
        selected_pairs = _select_pairs(group_pairs, args.top_n_pairs_per_group)
        selected_wells = _select_wells(group_wells, args.top_n_wells_per_group)

        selected_tables[f"{group_name}_waveA_stability_units"] = selected_stability
        selected_tables[f"{group_name}_waveB_correlogram_pairs"] = selected_pairs
        selected_tables[f"{group_name}_waveC_spatial_wells"] = selected_wells

        for wave_label, source_df, selected_df in [
            ("A_stability_units", group_stability, selected_stability),
            ("B_correlogram_pairs", group_pairs, selected_pairs),
            ("C_spatial_wells", group_wells, selected_wells),
        ]:
            summary_rows.append(
                {
                    "selection_group": group_name,
                    "track": spec["track"],
                    "region_label": spec["region_label"],
                    "description": spec["description"],
                    "wave": wave_label,
                    "candidate_rows": len(source_df),
                    "selected_rows": len(selected_df),
                    "unique_recordings_selected": _nunique(selected_df, "recording"),
                    "unique_wells_selected": _nunique(selected_df, "well"),
                }
            )

    manifest_rows = []
    for table_name, df in selected_tables.items():
        path = output_dir / f"final_selection_{table_name}_{args.date_label}.csv"
        df.to_csv(path, index=False)
        manifest_rows.extend(_manifest_rows(table_name, df, path))

    manifest = pd.DataFrame(manifest_rows)
    manifest_path = output_dir / f"final_representative_figure_selection_manifest_{args.date_label}.csv"
    summary = pd.DataFrame(summary_rows)
    summary_path = output_dir / f"final_representative_figure_selection_summary_{args.date_label}.csv"
    manifest.to_csv(manifest_path, index=False)
    summary.to_csv(summary_path, index=False)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "score_root": str(score_root),
        "output_dir": str(output_dir),
        "date_label": args.date_label,
        "selection_groups": SELECTION_GROUPS,
        "parameters": {
            "top_n_stability_per_group": args.top_n_stability_per_group,
            "top_n_pairs_per_group": args.top_n_pairs_per_group,
            "top_n_wells_per_group": args.top_n_wells_per_group,
        },
        "policies": {
            "ks_label_policy": "KSLabel=good is the ground-truth inclusion population inherited from Wave 0/A/B/C.",
            "selection_pool_policy": "Lumos, Cytoview dorsal, and Cytoview ventral are selected as separate pools.",
            "variant_policy": "No deduplication of primary/filter/broadband/raw variants. Recording stem remains part of identity.",
            "figure_policy": "These are frozen selection manifests; plotting must render from analyzer-backed data and this manifest.",
        },
        "outputs": {
            "manifest": str(manifest_path),
            "summary": str(summary_path),
            **{name: str(output_dir / f"final_selection_{name}_{args.date_label}.csv") for name in selected_tables},
        },
    }
    provenance_path = output_dir / f"final_representative_figure_selection_provenance_{args.date_label}.json"
    provenance_path.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print("Representative figure selection manifests complete")
    print(summary.to_string(index=False))
    print(f"Output dir: {output_dir}")
    return 0


def _add_selection_group(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    track = out.get("track", pd.Series("", index=out.index)).fillna("").astype(str)
    region = out.get("region_label", pd.Series("", index=out.index)).fillna("").astype(str).str.lower()
    out["selection_group"] = np.select(
        [
            track.eq("lumos_geometry"),
            track.eq("cytoview_dv") & region.eq("dorsal"),
            track.eq("cytoview_dv") & region.eq("ventral"),
        ],
        ["lumos", "cytoview_dorsal", "cytoview_ventral"],
        default="unassigned",
    )
    out["selection_pool_policy"] = "separate_lumos_cytoview_dorsal_cytoview_ventral"
    out["variant_policy"] = "preserve_all_raw_filter_broadband_variants_no_deduplication"
    out["raw_variant_inferred"] = out.get("recording", pd.Series("", index=out.index)).map(_infer_variant)
    return out


def _annotate_pairs(pairs: pd.DataFrame, stability: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "unit_key",
        "track",
        "region_label",
        "lumos_geometry_group",
        "selection_group",
        "raw_variant_inferred",
        "opto_status",
        "opto_review_rank",
        "opto_peak_raw_response_hz",
    ]
    annot = stability[[col for col in cols if col in stability.columns]].drop_duplicates("unit_key")
    out = pairs.merge(annot.add_suffix("_a"), left_on="unit_key_a", right_on="unit_key_a", how="left")
    out = out.merge(annot.add_suffix("_b"), left_on="unit_key_b", right_on="unit_key_b", how="left")
    out["track"] = out["track_a"].fillna(out["track_b"]).fillna("")
    out["region_label"] = out["region_label_a"].fillna(out["region_label_b"]).fillna("")
    out["lumos_geometry_group"] = out["lumos_geometry_group_a"].fillna(out["lumos_geometry_group_b"]).fillna("")
    out["selection_group"] = out["selection_group_a"].fillna(out["selection_group_b"]).fillna("unassigned")
    out["raw_variant_inferred"] = out["raw_variant_inferred_a"].fillna(out["raw_variant_inferred_b"]).fillna(
        out.get("recording", pd.Series("", index=out.index)).map(_infer_variant)
    )
    out["same_selection_group_pair"] = out["selection_group_a"].fillna("") == out["selection_group_b"].fillna("")
    out["selection_pool_policy"] = "separate_lumos_cytoview_dorsal_cytoview_ventral"
    out["variant_policy"] = "preserve_all_raw_filter_broadband_variants_no_deduplication"
    return out


def _build_well_scores(spatial_units: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    pair_counts = pairs.groupby(["recording", "well"]).size().to_dict() if not pairs.empty else {}
    for (recording, well), group in spatial_units.groupby(["recording", "well"], dropna=False):
        distances = []
        points = group[["best_channel_x", "best_channel_y"]].astype(float).to_numpy()
        for i, point_a in enumerate(points):
            for point_b in points[i + 1 :]:
                distances.append(float(np.linalg.norm(point_a - point_b)))
        finite = [value for value in distances if np.isfinite(value)]
        first = group.iloc[0]
        good_units = len(group)
        max_distance = float(np.nanmax(finite)) if finite else np.nan
        median_distance = float(np.nanmedian(finite)) if finite else np.nan
        pair_count = int(pair_counts.get((recording, well), 0))
        well_score = good_units + min(max_distance if np.isfinite(max_distance) else 0.0, 300.0) / 100.0 + min(pair_count, 5) * 0.5
        rows.append(
            {
                "recording": recording,
                "well": well,
                "analyzer_path": first.get("analyzer_path", ""),
                "track": first.get("track", ""),
                "region_label": first.get("region_label", ""),
                "lumos_geometry_group": first.get("lumos_geometry_group", ""),
                "selection_group": first.get("selection_group", ""),
                "raw_variant_inferred": first.get("raw_variant_inferred", ""),
                "good_units_in_well": good_units,
                "fs_like_units_0p50_aligned": int((group.get("fs_rs_cutoff_0p50_aligned", "") == "FS_like").sum()),
                "rs_like_units_0p50_aligned": int((group.get("fs_rs_cutoff_0p50_aligned", "") == "RS_like").sum()),
                "pair_count_within_distance": pair_count,
                "median_best_channel_distance_um": median_distance,
                "max_best_channel_distance_um": max_distance,
                "well_spatial_score": float(well_score),
                "selection_pool_policy": "separate_lumos_cytoview_dorsal_cytoview_ventral",
                "variant_policy": "preserve_all_raw_filter_broadband_variants_no_deduplication",
                "gui_equivalent_render_sources": "templates;recording channel locations;probe/similarity context",
            }
        )
    return pd.DataFrame(rows)


def _filter_group(df: pd.DataFrame, group_name: str) -> pd.DataFrame:
    if df.empty or "selection_group" not in df:
        return df.iloc[0:0].copy()
    return df.loc[df["selection_group"].astype(str).eq(group_name)].copy()


def _select_stability(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    ranked = df.sort_values(
        ["passes_stability_prefilter", "stability_score", "presence_ratio", "num_spikes"],
        ascending=[False, False, False, False],
    ).copy()
    ranked["selection_wave"] = "A"
    ranked["selection_panel"] = "waveform_stability_firing_rate_over_time"
    ranked["selection_rank_within_group"] = np.arange(1, len(ranked) + 1)
    ranked["selection_reason"] = "top stability candidate within separated selection group; variants preserved"
    return ranked.head(top_n)


def _select_pairs(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    ranked = df.loc[df.get("same_selection_group_pair", True).astype(bool)].copy()
    ranked = ranked.sort_values(
        ["is_nonzero_neighbor_pair", "is_fs_rs_pair", "pair_score", "cross_correlogram_zero_lag_duplicate_score"],
        ascending=[False, False, False, True],
    )
    ranked["selection_wave"] = "B"
    ranked["selection_panel"] = "autocorrelogram_crosscorrelogram_fs_rs"
    ranked["selection_rank_within_group"] = np.arange(1, len(ranked) + 1)
    ranked["selection_reason"] = "top within-well correlogram pair within separated selection group; variants preserved"
    return ranked.head(top_n)


def _select_wells(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    ranked = df.sort_values(
        ["good_units_in_well", "well_spatial_score", "max_best_channel_distance_um"],
        ascending=[False, False, False],
    ).copy()
    ranked["selection_wave"] = "C"
    ranked["selection_panel"] = "within_well_spatial_footprints"
    ranked["selection_rank_within_group"] = np.arange(1, len(ranked) + 1)
    ranked["selection_reason"] = "top spatial-footprint well within separated selection group; variants preserved"
    return ranked.head(top_n)


def _manifest_rows(table_name: str, df: pd.DataFrame, path: Path) -> list[dict[str, object]]:
    rows = []
    for row in df.itertuples(index=False):
        rows.append(
            {
                "selection_table": table_name,
                "selection_group": getattr(row, "selection_group", ""),
                "selection_wave": getattr(row, "selection_wave", ""),
                "selection_panel": getattr(row, "selection_panel", ""),
                "selection_rank_within_group": getattr(row, "selection_rank_within_group", ""),
                "recording": getattr(row, "recording", ""),
                "well": getattr(row, "well", ""),
                "unit_id": getattr(row, "unit_id", ""),
                "unit_id_a": getattr(row, "unit_id_a", ""),
                "unit_id_b": getattr(row, "unit_id_b", ""),
                "track": getattr(row, "track", ""),
                "region_label": getattr(row, "region_label", ""),
                "lumos_geometry_group": getattr(row, "lumos_geometry_group", ""),
                "raw_variant_inferred": getattr(row, "raw_variant_inferred", ""),
                "source_csv": str(path),
                "variant_policy": getattr(row, "variant_policy", ""),
            }
        )
    return rows


def _infer_variant(recording: object) -> str:
    text = str(recording).lower()
    if "filter_200hz-3khz" in text or "filter_200hz_3khz" in text:
        return "filter_200Hz-3kHz"
    if "filter_1hz-200hz" in text or "filter_1hz_200hz" in text:
        return "filter_1Hz-200Hz"
    if "broadband_processor" in text or "broadbandprocessor" in text:
        return "broadband_processor"
    if "primary" in text:
        return "primary_raw"
    return "unknown_or_unencoded_variant"


def _nunique(df: pd.DataFrame, column: str) -> int:
    return int(df[column].nunique()) if column in df and not df.empty else 0


if __name__ == "__main__":
    raise SystemExit(main())
