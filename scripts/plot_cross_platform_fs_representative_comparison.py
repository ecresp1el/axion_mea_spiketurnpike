#!/usr/bin/env python3
"""Compare the locked CytoView FS representatives with the best Lumos FS candidate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_cytoview_unified_rsfs_activity_figure import (  # noqa: E402
    CLASS_COLORS,
    _load_representative_assets,
    _plot_representative_acg,
    _plot_representative_spatial,
    _plot_representative_stability,
    _representative_source_tables,
)

JOB_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_CYTOVIEW_DIR = (
    JOB_ROOT / "cytoview_unified_rsfs_activity_figure_20260710_20260710_103600"
)
LUMOS_ALIGNMENT_DIR = JOB_ROOT / "waveform_alignment_feature_audit_20260709"
LUMOS_FIRING_PATH = JOB_ROOT / "lumos_gui_ready_unsorted_unit_firing_rates_20260709.csv"
STEM = "cross_platform_fs_representative_comparison_20260710"
LOCKED_LUMOS_CANDIDATE_KEY = (
    "step1_nonlfp_th5_20260708_2_25_2026_129-8447_test(000)_broadband_processor_raw|F8|5"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cytoview-dir", type=Path, default=DEFAULT_CYTOVIEW_DIR)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    selection = _comparison_selection(args.cytoview_dir)
    assets = _load_representative_assets(selection)
    assets = sorted(
        assets, key=lambda asset: asset["metadata"]["representative_order_within_class"]
    )
    qc = _qc_summary(assets)
    spatial, acg, stability = _representative_source_tables(assets)

    selection_path = output_dir / f"{STEM}_selection.csv"
    qc_path = output_dir / f"{STEM}_qc_summary.csv"
    spatial_path = output_dir / f"{STEM}_spatial_waveforms.csv.gz"
    acg_path = output_dir / f"{STEM}_autocorrelograms.csv"
    stability_path = output_dir / f"{STEM}_amplitude_stability.csv.gz"
    selection.to_csv(selection_path, index=False)
    qc.to_csv(qc_path, index=False)
    spatial.to_csv(spatial_path, index=False, compression="gzip")
    acg.to_csv(acg_path, index=False)
    stability.to_csv(stability_path, index=False, compression="gzip")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 7,
            "axes.titlesize": 8,
            "axes.labelsize": 7,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    fig = plt.figure(figsize=(13.5, 4.7), facecolor="white")
    grid = fig.add_gridspec(1, 3, wspace=0.18)
    for index, asset in enumerate(assets, start=1):
        card = grid[0, index - 1].subgridspec(
            3, 1, height_ratios=[2.75, 0.34, 0.20], hspace=0.08
        )
        axes = [fig.add_subplot(card[row]) for row in range(3)]
        _plot_representative_spatial(axes[0], asset, "FS", index)
        _plot_representative_acg(axes[1], asset, "FS", show_ylabel=False)
        _plot_representative_stability(axes[2], asset, "FS", show_ylabel=False)
    fig.suptitle(
        "Cross-platform FS representative QC: current CytoView units vs strongest Lumos candidate",
        x=0.02,
        y=0.995,
        ha="left",
        fontsize=11,
        fontweight="bold",
    )
    fig.text(
        0.02,
        0.965,
        "Identical 2.6× spatial display gain · raw unsmoothed probability ACG · sampled PTP stability",
        ha="left",
        va="top",
        fontsize=7,
        color="#555555",
    )
    fig.subplots_adjust(left=0.025, right=0.995, bottom=0.045, top=0.91)
    figure_paths = []
    for suffix in ["png", "pdf", "svg"]:
        path = (output_dir / STEM).with_suffix(f".{suffix}")
        kwargs = {"bbox_inches": "tight", "facecolor": "white", "transparent": False}
        if suffix == "png":
            kwargs["dpi"] = 600
        fig.savefig(path, **kwargs)
        figure_paths.append(path)
    plt.close(fig)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "comparison": ["current CytoView FS1", "current CytoView FS16", "Lumos F8 u5"],
        "lumos_candidate_selection": {
            "unit_key": LOCKED_LUMOS_CANDIDATE_KEY,
            "rule": (
                "highest cross-platform preliminary quality among Lumos aligned KSLabel=good "
                "TTP<=0.50 ms units with matched firing metadata, >=100 spikes, and template PTP>=10 uV"
            ),
            "duplicate_variant_policy": (
                "primary F8 u6 appears to represent the same biological unit and was not treated "
                "as an independent candidate"
            ),
        },
        "outputs": {
            "figures": [str(path) for path in figure_paths],
            "selection": str(selection_path),
            "qc_summary": str(qc_path),
            "spatial_waveforms": str(spatial_path),
            "autocorrelograms": str(acg_path),
            "amplitude_stability": str(stability_path),
        },
    }
    provenance_path = output_dir / f"{STEM}_provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(qc.to_string(index=False))
    print(f"Figure: {figure_paths[0]}")
    return 0


def _comparison_selection(cytoview_dir: Path) -> pd.DataFrame:
    cytoview_dir = Path(cytoview_dir).expanduser().resolve()
    cyto_path = (
        cytoview_dir
        / "cytoview_unified_rsfs_activity_figure_20260710_panels_B_C_representative_selection.csv"
    )
    cyto = pd.read_csv(cyto_path)
    cyto = cyto.loc[cyto["representative_display_id"].isin(["FS1", "FS16"])].copy()
    cyto["platform"] = "CytoView"
    order = {"FS1": 1, "FS16": 2}
    cyto["representative_order_within_class"] = cyto["representative_display_id"].map(order)

    paired = pd.read_csv(
        LUMOS_ALIGNMENT_DIR / "waveform_alignment_feature_audit_20260709_paired_unit_metrics.csv"
    )
    firing = pd.read_csv(LUMOS_FIRING_PATH)
    lumos = paired.merge(
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
    row = lumos.loc[lumos["unit_key"].eq(LOCKED_LUMOS_CANDIDATE_KEY)]
    if len(row) != 1:
        raise ValueError("Locked Lumos candidate was not found uniquely")
    row = row.iloc[0]
    lumos_metadata = {
        "unit_key": row["unit_key"],
        "recording_well_id": f"{row['recording']}|{row['well']}",
        "recording": row["recording"],
        "well": row["well"],
        "region_call": "Lumos",
        "raw_variant": "broadband_processor_raw",
        "unit_id": row["unit_id"],
        "KSLabel": "good",
        "analyzer_path": row["analyzer_path"],
        "source_spike_count": int(row["num_spikes"]),
        "source_firing_rate_hz": float(row["firing_rate_hz"]),
        "source_ContamPct": float(row["ContamPct"]),
        "template_ptp_best_channel_uV": float(row["after_template_ptp_best_channel_uV"]),
        "rs_fs_class": "FS",
        "feature_ttp_ms": float(row["after_trough_to_peak_duration_ms"]),
        "feature_spike_half_width_ms": float(row["after_spike_half_width_ms"]),
        "feature_repolarization_time_ms": float(row["after_repolarization_time_ms"]),
        "representative_order_within_class": 3,
        "representative_display_id": "LFS1",
        "platform": "Lumos",
    }
    return pd.concat([cyto, pd.DataFrame([lumos_metadata])], ignore_index=True, sort=False)


def _qc_summary(assets: list[dict[str, object]]) -> pd.DataFrame:
    rows = []
    for asset in assets:
        metadata = asset["metadata"]
        bundle = asset["bundle"]
        unit_row = asset["unit_row"]
        template = bundle.templates[int(unit_row["unit_index"])]
        ptp_by_channel = np.ptp(template, axis=0)
        ranked_ptp = np.sort(ptp_by_channel)[::-1]
        snippets = np.asarray(asset["snippets"], dtype=float)
        snippet_ptp = np.ptp(snippets, axis=1) if snippets.size else np.asarray([])
        median_ptp = float(np.nanmedian(snippet_ptp)) if snippet_ptp.size else np.nan
        mad_ptp = (
            float(np.nanmedian(np.abs(snippet_ptp - median_ptp)))
            if snippet_ptp.size
            else np.nan
        )
        rows.append(
            {
                "display_id": metadata["representative_display_id"],
                "platform": metadata.get("platform", "CytoView"),
                "well": metadata["well"],
                "unit_id": metadata["unit_id"],
                "unit_key": metadata["unit_key"],
                "aligned_ttp_ms": metadata["feature_ttp_ms"],
                "template_ptp_uV": metadata["template_ptp_best_channel_uV"],
                "spike_count": metadata["source_spike_count"],
                "firing_rate_hz": metadata["source_firing_rate_hz"],
                "contam_pct": metadata["source_ContamPct"],
                "p_abs_lag_le_2ms": float(asset["probability"]["p_refractory"]),
                "sampled_spike_ptp_median_uV": median_ptp,
                "sampled_spike_ptp_mad_over_median": mad_ptp / median_ptp if median_ptp > 0 else np.nan,
                "best_to_second_channel_ptp_ratio": (
                    float(ranked_ptp[0] / ranked_ptp[1])
                    if len(ranked_ptp) > 1 and ranked_ptp[1] > 0
                    else np.nan
                ),
                "local_footprint_channel_count": len(asset["local_channels"]),
            }
        )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    raise SystemExit(main())
