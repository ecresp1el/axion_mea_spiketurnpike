#!/usr/bin/env python3
"""Plot every aligned KSLabel=good Lumos FS-like unit for rapid visual review."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

JOB_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_ALIGNMENT_DIR = JOB_ROOT / "waveform_alignment_feature_audit_20260709"
DEFAULT_CLASSIFIED = (
    JOB_ROOT
    / "lumos_alignment_cutoff_sensitivity_20260709"
    / "lumos_ttp_cutoff_0p50_aligned_classified_units.csv"
)
STEM = "lumos_good_fs_aligned_waveform_gallery_20260710"
FS_COLOR = "#E76F51"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alignment-dir", type=Path, default=DEFAULT_ALIGNMENT_DIR)
    parser.add_argument("--classified-units", type=Path, default=DEFAULT_CLASSIFIED)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--fs-cutoff-ms", type=float, default=0.50)
    parser.add_argument("--units-per-page", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    classified_path = args.classified_units.expanduser().resolve()
    alignment_dir = args.alignment_dir.expanduser().resolve()
    traces_path = alignment_dir / "waveform_alignment_feature_audit_20260709_waveform_traces.csv.gz"

    units = pd.read_csv(classified_path)
    units = units.loc[
        units["KSLabel"].eq("good")
        & units["stage"].eq("aligned")
        & pd.to_numeric(units["trough_to_peak_duration_ms"], errors="coerce").le(args.fs_cutoff_ms)
    ].copy()
    units = units.sort_values(
        ["template_ptp_best_channel_uV", "usable_snippets", "recording", "well", "unit_id"],
        ascending=[False, False, True, True, True],
    ).reset_index(drop=True)
    units.insert(0, "lumos_fs_gallery_rank", np.arange(1, len(units) + 1))
    units.insert(1, "lumos_fs_display_id", [f"LFS{rank}" for rank in units["lumos_fs_gallery_rank"]])

    traces = pd.read_csv(traces_path)
    traces = traces.loc[traces["unit_key"].isin(units["unit_key"])].copy()
    traces = traces.merge(
        units[["unit_key", "lumos_fs_gallery_rank", "lumos_fs_display_id"]],
        on="unit_key",
        how="left",
        validate="many_to_one",
    )
    if traces["unit_key"].nunique() != len(units):
        raise ValueError("Not every Lumos FS-like unit has an aligned waveform trace")
    traces["aligned_trough_normalized_amplitude"] = traces.groupby("unit_key", group_keys=False)[
        "after_aligned_average_uV"
    ].transform(_trough_normalize)

    selection_path = output_dir / f"{STEM}_selection.csv"
    trace_output_path = output_dir / f"{STEM}_aligned_traces.csv.gz"
    units.to_csv(selection_path, index=False)
    traces.to_csv(trace_output_path, index=False, compression="gzip")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _style(plt)
    page_paths = []
    units_per_page = args.units_per_page
    for page_index, start in enumerate(range(0, len(units), units_per_page), start=1):
        page_units = units.iloc[start : start + units_per_page]
        base = output_dir / f"{STEM}_page_{page_index:02d}"
        page_paths.extend(_plot_page(plt, page_units, traces, base, overview=False))
    overview_paths = _plot_page(
        plt,
        units,
        traces,
        output_dir / f"{STEM}_all_85_overview",
        overview=True,
    )

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "classified_units_source": str(classified_path),
        "aligned_trace_source": str(traces_path),
        "selection": {
            "plate_family": "lumos_48well",
            "KSLabel": "good",
            "stage": "aligned",
            "FS_rule": f"aligned trough-to-peak duration <= {args.fs_cutoff_ms:.2f} ms",
            "additional_QC_filters": "none",
            "unit_count": int(len(units)),
        },
        "ordering": "descending template PTP, then usable snippets, recording, well, and unit ID",
        "display": "aligned mean best-channel waveform; baseline corrected and normalized by absolute trough; no display smoothing",
        "outputs": {
            "selection": str(selection_path),
            "aligned_traces": str(trace_output_path),
            "page_figures": [str(path) for path in page_paths],
            "overview_figures": [str(path) for path in overview_paths],
        },
    }
    provenance_path = output_dir / f"{STEM}_provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(f"Lumos aligned KSLabel=good FS-like units: {len(units)}")
    print(f"Overview: {overview_paths[0]}")
    print(f"Selection: {selection_path}")
    return 0


def _trough_normalize(series: pd.Series) -> pd.Series:
    values = series.to_numpy(float)
    baseline = float(np.nanmedian(values[: min(5, len(values))]))
    centered = values - baseline
    scale = abs(float(np.nanmin(centered)))
    return pd.Series(centered / max(scale, 1e-9), index=series.index)


def _style(plt) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 6.5,
            "axes.titlesize": 7,
            "axes.labelsize": 6.5,
            "xtick.labelsize": 5.5,
            "ytick.labelsize": 5.5,
            "axes.linewidth": 0.65,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _plot_page(plt, units: pd.DataFrame, traces: pd.DataFrame, output_base: Path, *, overview: bool):
    ncols = 5
    nrows = int(np.ceil(len(units) / ncols))
    width = 12.0
    height_per_row = 1.65 if overview else 2.0
    fig, axes = plt.subplots(nrows, ncols, figsize=(width, height_per_row * nrows), squeeze=False)
    for ax, (_, unit) in zip(axes.ravel(), units.iterrows()):
        trace = traces.loc[traces["unit_key"].eq(unit["unit_key"])].sort_values("time_ms")
        ax.plot(trace["time_ms"], trace["aligned_trough_normalized_amplitude"], color=FS_COLOR, lw=1.0 if overview else 1.25)
        ax.axhline(0, color="#CFCFCF", lw=0.45, zorder=0)
        ax.axvline(0, color="#CFCFCF", lw=0.45, zorder=0)
        ax.set_xlim(-0.85, 1.55)
        ax.set_ylim(-1.18, 1.25)
        ax.set_title(
            f"{unit['lumos_fs_display_id']}  {unit['well']} u{unit['unit_id']}\n"
            f"TTP {unit['trough_to_peak_duration_ms']:.2f} ms · PTP {unit['template_ptp_best_channel_uV']:.1f} µV",
            loc="left",
            fontweight="bold",
            pad=1.5,
        )
        ax.spines[["top", "right"]].set_visible(False)
        if overview:
            ax.set_xticks([])
            ax.set_yticks([])
        else:
            ax.set_xticks([-0.5, 0, 0.5, 1.0])
            ax.set_yticks([-1, 0, 1])
            ax.tick_params(length=2, pad=1)
    for ax in axes.ravel()[len(units) :]:
        ax.set_axis_off()
    fig.suptitle(
        f"Lumos KSLabel=good aligned FS-like units (TTP ≤ 0.50 ms; n={len(units)})",
        x=0.025,
        y=0.997,
        ha="left",
        fontsize=11,
        fontweight="bold",
    )
    fig.text(
        0.025,
        0.982,
        "Aligned mean best-channel waveform · trough-normalized · no smoothing · gallery order by template PTP",
        ha="left",
        va="top",
        fontsize=7,
        color="#555555",
    )
    fig.subplots_adjust(left=0.045, right=0.995, bottom=0.025, top=0.965, wspace=0.32, hspace=0.56)
    paths = []
    for suffix in ["png", "pdf", "svg"]:
        path = output_base.with_suffix(f".{suffix}")
        kwargs = {"bbox_inches": "tight", "facecolor": "white", "transparent": False}
        if suffix == "png":
            kwargs["dpi"] = 400 if overview else 600
        fig.savefig(path, **kwargs)
        paths.append(path)
    plt.close(fig)
    return paths


if __name__ == "__main__":
    raise SystemExit(main())
