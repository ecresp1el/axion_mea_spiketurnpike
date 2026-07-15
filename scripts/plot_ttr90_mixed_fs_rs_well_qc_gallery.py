#!/usr/bin/env python
"""Render same-well high-confidence FS/RS spatial and correlogram QC candidates."""

from __future__ import annotations

import argparse
import itertools
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams.update(
    {
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Nimbus Sans", "Helvetica", "DejaVu Sans"],
        "axes.linewidth": 0.7,
    }
)

import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from matplotlib.gridspec import GridSpecFromSubplotSpec
import numpy as np
import pandas as pd


PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_ANALYSIS_ROOT = (
    PROJECT_ROOT
    / "FINAL FIG 2"
    / "Population Panels"
    / "ventral_MGE_putative_FS_RS_TTR90_PCHIP_040_056_FINAL"
)
DEFAULT_UNIT_CSV = DEFAULT_ANALYSIS_ROOT / "lumos_ventral_ttr90_confidence_retained_FS_RS_units.csv"
DEFAULT_OUTPUT_DIR = DEFAULT_ANALYSIS_ROOT / "mixed_high_confidence_FS_RS_well_QC_candidates_20260714"

FS_BASE = "#B8742A"
RS_BASE = "#58758E"
NEUTRAL = "#2B2B2B"
LIGHT_GRAY = "#D8D8D8"


@dataclass
class UnitData:
    row: pd.Series
    sorting_unit_id: object
    unit_index: int
    class_label: str
    color: str
    spike_times_s: np.ndarray
    isi_lt_2ms_fraction: float
    template: np.ndarray
    footprint: np.ndarray
    normalized_footprint: np.ndarray
    best_channel_index: int
    best_channel_xy: np.ndarray
    centroid_xy: np.ndarray
    ks_label: str
    contam_pct: float


@dataclass
class WellData:
    source_platform: str
    recording: str
    well: str
    analyzer_path: str
    analyzer: object
    sampling_frequency_hz: float
    templates: np.ndarray
    nbefore: int
    channel_locations: np.ndarray
    pitch_um: float
    units: list[UnitData]
    excluded_high_confidence: list[dict[str, object]]
    score: float


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-csv", type=Path, default=DEFAULT_UNIT_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-spikes", type=int, default=100)
    parser.add_argument("--max-isi-lt-2ms-fraction", type=float, default=0.01)
    parser.add_argument("--footprint-threshold", type=float, default=0.12)
    parser.add_argument("--surrounding-channels-per-unit", type=int, default=9)
    parser.add_argument("--correlogram-window-ms", type=float, default=50.0)
    parser.add_argument("--correlogram-bin-ms", type=float, default=1.0)
    parser.add_argument("--max-candidates", type=int, default=0)
    parser.add_argument("--export-formats", default="png,pdf,svg")
    args = parser.parse_args()

    import spikeinterface.full as si

    unit_csv = args.unit_csv.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    source = pd.read_csv(unit_csv)
    required = {
        "source_platform",
        "recording",
        "well",
        "unit_id",
        "analyzer_path",
        "ttr90_plot_class",
        "ttr90_ms",
    }
    missing = sorted(required - set(source.columns))
    if missing:
        raise ValueError(f"unit table is missing columns: {', '.join(missing)}")

    source = source.loc[source["ttr90_plot_class"].isin(["FS", "RS"])].copy()
    wells: list[WellData] = []
    errors: list[dict[str, object]] = []
    for key, group in source.groupby(["source_platform", "recording", "well"], sort=True):
        if set(group["ttr90_plot_class"]) != {"FS", "RS"}:
            continue
        try:
            well_data = load_well(si, key, group, args)
            if {unit.class_label for unit in well_data.units} == {"FS", "RS"}:
                wells.append(well_data)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "source_platform": key[0],
                    "recording": key[1],
                    "well": key[2],
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    wells.sort(key=lambda value: value.score, reverse=True)
    if args.max_candidates > 0:
        wells = wells[: args.max_candidates]

    candidate_rows: list[dict[str, object]] = []
    unit_rows: list[dict[str, object]] = []
    pair_rows: list[dict[str, object]] = []
    formats = [item.strip().lower() for item in args.export_formats.split(",") if item.strip()]
    for rank, well_data in enumerate(wells, start=1):
        stem = candidate_stem(rank, well_data)
        output_paths = render_candidate(well_data, output_dir, stem, formats, args)
        nature_paths: dict[str, Path] = {}
        if rank == 1:
            nature_paths = render_nature_candidate(
                well_data,
                output_dir,
                f"nature_minimal_{stem}",
                formats,
                args,
            )
        classes = pd.Series([unit.class_label for unit in well_data.units]).value_counts()
        candidate_rows.append(
            {
                "candidate_rank": rank,
                "source_platform": well_data.source_platform,
                "recording": well_data.recording,
                "well": well_data.well,
                "analyzer_path": well_data.analyzer_path,
                "candidate_score": well_data.score,
                "displayed_unit_count": len(well_data.units),
                "displayed_FS_count": int(classes.get("FS", 0)),
                "displayed_RS_count": int(classes.get("RS", 0)),
                "displayed_unit_ids": ";".join(str(unit.row["unit_id"]) for unit in well_data.units),
                "excluded_high_confidence_count": len(well_data.excluded_high_confidence),
                "excluded_high_confidence_units": ";".join(
                    f"u{row['unit_id']}:{row['reason']}" for row in well_data.excluded_high_confidence
                ),
                **{f"{fmt}_path": str(path) for fmt, path in output_paths.items()},
                **{f"nature_{fmt}_path": str(path) for fmt, path in nature_paths.items()},
            }
        )
        unit_rows.extend(unit_manifest_rows(rank, well_data))
        pair_rows.extend(pair_manifest_rows(rank, well_data, args))

    candidate_path = output_dir / "mixed_FS_RS_well_QC_candidate_manifest.csv"
    unit_path = output_dir / "mixed_FS_RS_well_QC_unit_manifest.csv"
    pair_path = output_dir / "mixed_FS_RS_well_QC_pair_manifest.csv"
    error_path = output_dir / "mixed_FS_RS_well_QC_errors.csv"
    pd.DataFrame(candidate_rows).to_csv(candidate_path, index=False)
    pd.DataFrame(unit_rows).to_csv(unit_path, index=False)
    pd.DataFrame(pair_rows).to_csv(pair_path, index=False)
    pd.DataFrame(errors, columns=["source_platform", "recording", "well", "error_type", "error"]).to_csv(
        error_path, index=False
    )

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "input_unit_csv": str(unit_csv),
        "output_dir": str(output_dir),
        "classification": {
            "measurement": "continuous PCHIP-interpolated TTR90",
            "high_confidence_FS": "TTR90 <= 0.40 ms",
            "high_confidence_RS": "TTR90 >= 0.56 ms",
            "indeterminate_and_atypical": "not present in the retained FS/RS input table",
        },
        "selection": {
            "minimum_spikes_in_analyzer": args.min_spikes,
            "maximum_fraction_of_adjacent_ISIs_below_2ms_inclusive": args.max_isi_lt_2ms_fraction,
            "KSLabel_filter": "none",
            "ContamPct_filter": "none",
            "well_requirement": "at least one displayed high-confidence FS and one displayed high-confidence RS unit",
            "display_rule": "all high-confidence FS/RS units in the well passing the spike-count and refractory-period criteria",
            "ranking_priority": "TTR90 confidence margin and recomputed refractory-period cleanliness, followed by spatial isolation, spike support, and amplitude",
        },
        "plot": {
            "spatial_map": "all displayed units overlaid on physical electrode coordinates; each unit normalized only by its own best-channel template PTP",
            "surrounding_channels_per_unit": args.surrounding_channels_per_unit,
            "correlograms": "raw unsmoothed 1-ms count bins by default",
            "ACG_color": "unit color",
            "CCG_color": "negative lags use the column-unit color and positive lags use the row-unit color",
            "FS_palette": FS_BASE,
            "RS_palette": RS_BASE,
        },
        "outputs": {
            "candidate_manifest": str(candidate_path),
            "unit_manifest": str(unit_path),
            "pair_manifest": str(pair_path),
            "errors": str(error_path),
        },
        "rendered_candidate_count": len(wells),
        "error_count": len(errors),
    }
    provenance_path = output_dir / "mixed_FS_RS_well_QC_provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Rendered candidates: {len(wells)}")
    for rank, well_data in enumerate(wells, start=1):
        labels = ", ".join(f"{unit.class_label} u{unit.row['unit_id']}" for unit in well_data.units)
        print(f"{rank}. {well_data.source_platform} {well_data.well}: {labels}")
    print(f"Errors: {len(errors)}")
    print(f"Output directory: {output_dir}")
    return 0 if not errors else 1


def load_well(si, key, group: pd.DataFrame, args) -> WellData:
    source_platform, recording, well = (str(value) for value in key)
    analyzer_paths = group["analyzer_path"].astype(str).unique()
    if analyzer_paths.size != 1:
        raise ValueError(f"expected one analyzer path, found {analyzer_paths.size}")
    analyzer_path = str(Path(analyzer_paths[0]).expanduser().resolve())
    analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
    templates_ext = analyzer.get_extension("templates")
    if templates_ext is None:
        raise ValueError("missing templates extension")
    templates = templates_average(templates_ext)
    nbefore = int(getattr(templates_ext, "nbefore", templates.shape[1] // 2))
    sampling_frequency_hz = float(analyzer.recording.get_sampling_frequency())
    channel_locations = np.asarray(analyzer.recording.get_channel_locations(), dtype=float)[:, :2]
    pitch_um = minimum_channel_pitch(channel_locations)
    unit_ids = list(analyzer.sorting.unit_ids)
    unit_lookup = {str(unit_id): unit_id for unit_id in unit_ids}
    unit_index = {str(unit_id): index for index, unit_id in enumerate(unit_ids)}
    property_maps = {
        name: sorting_property_map(analyzer.sorting, name)
        for name in ["KSLabel", "ContamPct"]
    }

    preliminary: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for _, row in group.iterrows():
        sorting_unit_id = unit_for_sorting(row["unit_id"], unit_lookup)
        index = unit_index[str(sorting_unit_id)]
        spike_frames = np.asarray(analyzer.sorting.get_unit_spike_train(sorting_unit_id), dtype=float)
        spike_times_s = spike_frames / sampling_frequency_hz
        isi_s = np.diff(spike_times_s)
        isi_fraction = float(np.mean(isi_s < 0.002)) if isi_s.size else np.nan
        reasons = []
        if spike_times_s.size < args.min_spikes:
            reasons.append(f"spikes<{args.min_spikes}")
        if not np.isfinite(isi_fraction) or isi_fraction > args.max_isi_lt_2ms_fraction:
            reasons.append(f"ISI<2ms>{100 * args.max_isi_lt_2ms_fraction:g}%")
        if reasons:
            excluded.append(
                {
                    "unit_id": row["unit_id"],
                    "class_label": row["ttr90_plot_class"],
                    "reason": "+".join(reasons),
                    "isi_lt_2ms_fraction": isi_fraction,
                    "spike_count": int(spike_times_s.size),
                }
            )
            continue

        template = np.asarray(templates[index], dtype=float)
        footprint = np.ptp(template, axis=0)
        best_channel_index = int(np.nanargmax(footprint))
        normalized_footprint = footprint / max(float(np.nanmax(footprint)), 1e-12)
        centroid_xy = weighted_centroid(channel_locations, footprint)
        ks_label = str(property_maps["KSLabel"].get(str(sorting_unit_id), ""))
        contam_pct = safe_float(property_maps["ContamPct"].get(str(sorting_unit_id), np.nan))
        preliminary.append(
            {
                "row": row,
                "sorting_unit_id": sorting_unit_id,
                "unit_index": index,
                "class_label": str(row["ttr90_plot_class"]),
                "spike_times_s": spike_times_s,
                "isi_lt_2ms_fraction": isi_fraction,
                "template": template,
                "footprint": footprint,
                "normalized_footprint": normalized_footprint,
                "best_channel_index": best_channel_index,
                "best_channel_xy": channel_locations[best_channel_index],
                "centroid_xy": centroid_xy,
                "ks_label": ks_label,
                "contam_pct": contam_pct,
            }
        )

    preliminary.sort(key=lambda value: (0 if value["class_label"] == "FS" else 1, int(float(value["row"]["unit_id"]))))
    colors = class_colors(preliminary)
    units = [UnitData(color=color, **values) for values, color in zip(preliminary, colors)]
    score = candidate_score(units, pitch_um)
    return WellData(
        source_platform=source_platform,
        recording=recording,
        well=well,
        analyzer_path=analyzer_path,
        analyzer=analyzer,
        sampling_frequency_hz=sampling_frequency_hz,
        templates=templates,
        nbefore=nbefore,
        channel_locations=channel_locations,
        pitch_um=pitch_um,
        units=units,
        excluded_high_confidence=excluded,
        score=score,
    )


def render_candidate(well: WellData, output_dir: Path, stem: str, formats: list[str], args) -> dict[str, Path]:
    unit_count = len(well.units)
    fig_height = max(7.4, 2.05 * unit_count + 1.5)
    fig = plt.figure(figsize=(15.4, fig_height), facecolor="white")
    outer = fig.add_gridspec(1, 2, width_ratios=[0.88, 1.32], wspace=0.19, left=0.045, right=0.985, top=0.82, bottom=0.075)
    ax_map = fig.add_subplot(outer[0, 0])
    plot_combined_spatial_map(ax_map, well, args)
    matrix = GridSpecFromSubplotSpec(unit_count, unit_count, subplot_spec=outer[0, 1], wspace=0.20, hspace=0.28)
    plot_correlogram_matrix(fig, matrix, well, args)

    fs_count = sum(unit.class_label == "FS" for unit in well.units)
    rs_count = sum(unit.class_label == "RS" for unit in well.units)
    fig.suptitle(
        f"Same-well putative-unit isolation candidate | {well.source_platform} {well.well} | "
        f"{fs_count} FS, {rs_count} RS",
        x=0.045,
        y=0.965,
        ha="left",
        fontsize=14,
        fontweight="bold",
        color=NEUTRAL,
    )
    fig.text(
        0.045,
        0.925,
        "High-confidence continuous TTR90 classes; displayed units have at least "
        f"{args.min_spikes} spikes and ≤{100 * args.max_isi_lt_2ms_fraction:g}% of adjacent ISIs below 2 ms. "
        "No KSLabel or ContamPct filter.",
        ha="left",
        va="center",
        fontsize=9.3,
        color="#555555",
    )
    fig.text(
        0.425,
        0.865,
        "Raw binned auto- and cross-correlograms",
        ha="left",
        va="center",
        fontsize=11,
        color=NEUTRAL,
    )
    outputs: dict[str, Path] = {}
    for fmt in formats:
        path = output_dir / f"{stem}.{fmt}"
        save_kwargs = {"bbox_inches": "tight", "facecolor": "white"}
        if fmt == "png":
            save_kwargs["dpi"] = 600
        fig.savefig(path, **save_kwargs)
        outputs[fmt] = path
    plt.close(fig)
    return outputs


def render_nature_candidate(
    well: WellData,
    output_dir: Path,
    stem: str,
    formats: list[str],
    args,
) -> dict[str, Path]:
    """Render the selected well as a compact editorial panel."""
    unit_count = len(well.units)
    if unit_count != 4:
        raise ValueError(f"Nature-minimal layout currently expects four units, found {unit_count}")

    fig = plt.figure(figsize=(7.15, 4.45), facecolor="white")
    grid = fig.add_gridspec(
        unit_count,
        unit_count,
        left=0.555,
        right=0.985,
        top=0.800,
        bottom=0.145,
        wspace=0.16,
        hspace=0.16,
    )

    for row_index, row_unit in enumerate(well.units):
        for col_index, col_unit in enumerate(well.units):
            if row_index > col_index:
                continue
            ax = fig.add_subplot(grid[row_index, col_index])
            plot_nature_correlogram(ax, row_unit, col_unit, row_index, col_index, unit_count, args)

    ax_spatial = fig.add_axes([0.050, 0.105, 0.475, 0.645])
    plot_nature_spatial_map(ax_spatial, well, args)

    fig.text(0.020, 0.965, "B", ha="left", va="top", fontsize=15, fontweight="bold", color=NEUTRAL)
    fig.text(
        0.065,
        0.955,
        "Representative extracellular units",
        ha="left",
        va="top",
        fontsize=10.2,
        color=NEUTRAL,
    )
    fig.text(
        0.985,
        0.935,
        "ACG diagonal  ·  CCG upper triangle",
        ha="right",
        va="top",
        fontsize=6.6,
        color="#777777",
    )
    for col_index, unit in enumerate(well.units):
        position = grid[0, col_index].get_position(fig)
        fig.text(
            0.5 * (position.x0 + position.x1),
            0.825,
            f"{unit.class_label} {int(float(unit.row['unit_id']))}",
            ha="center",
            va="bottom",
            fontsize=7.2,
            fontweight="bold",
            color=unit.color,
        )

    outputs: dict[str, Path] = {}
    for fmt in formats:
        path = output_dir / f"{stem}.{fmt}"
        save_kwargs = {"bbox_inches": "tight", "facecolor": "white"}
        if fmt == "png":
            save_kwargs["dpi"] = 600
        fig.savefig(path, **save_kwargs)
        outputs[fmt] = path
    plt.close(fig)
    return outputs


def plot_nature_correlogram(
    ax,
    row_unit: UnitData,
    col_unit: UnitData,
    row_index: int,
    col_index: int,
    unit_count: int,
    args,
) -> None:
    is_auto = row_index == col_index
    bins, counts = correlogram(
        row_unit.spike_times_s,
        col_unit.spike_times_s,
        window_ms=args.correlogram_window_ms,
        bin_ms=args.correlogram_bin_ms,
        exclude_self=is_auto,
    )
    if is_auto:
        ax.bar(
            bins,
            counts,
            width=args.correlogram_bin_ms,
            color=row_unit.color,
            alpha=0.52,
            linewidth=0,
        )
    else:
        negative = bins < 0
        positive = ~negative
        ax.bar(
            bins[negative],
            counts[negative],
            width=args.correlogram_bin_ms,
            color=col_unit.color,
            alpha=0.27,
            linewidth=0,
        )
        ax.bar(
            bins[positive],
            counts[positive],
            width=args.correlogram_bin_ms,
            color=row_unit.color,
            alpha=0.27,
            linewidth=0,
        )
    ax.axvspan(-2.0, 2.0, color="#C8C8C8", alpha=0.12, linewidth=0, zorder=0)
    ax.axvline(0, color="#8A8A8A", linewidth=0.45, zorder=4)
    ax.set_xlim(-args.correlogram_window_ms, args.correlogram_window_ms)
    count_limit = nice_count_limit(float(np.max(counts)) if counts.size else 0.0)
    ax.set_ylim(0, count_limit)
    ax.set_yticks([0, count_limit])
    ax.set_yticklabels(["0", f"{count_limit:g}"], fontsize=5.1, color="#777777")
    ax.tick_params(axis="y", length=1.8, width=0.45, pad=1.2, colors="#777777")
    if row_index == 0 and col_index == 0:
        ax.set_ylabel("count", fontsize=5.8, color="#777777", labelpad=1.5)
    if row_index == unit_count - 1 and col_index == unit_count - 1:
        ax.set_xticks([-args.correlogram_window_ms, 0, args.correlogram_window_ms])
        ax.set_xticklabels(
            [f"−{args.correlogram_window_ms:g}", "0", f"{args.correlogram_window_ms:g}"],
            fontsize=6.5,
            color="#666666",
        )
        ax.set_xlabel("lag (ms)", fontsize=6.8, color="#666666", labelpad=2)
        ax.tick_params(axis="x", length=2.0, width=0.45, pad=1.5)
    else:
        ax.set_xticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_color("#AAAAAA")
    ax.spines["left"].set_linewidth(0.45)
    if row_index == unit_count - 1 and col_index == unit_count - 1:
        ax.spines["bottom"].set_visible(True)
        ax.spines["bottom"].set_color("#AAAAAA")
        ax.spines["bottom"].set_linewidth(0.45)


def plot_nature_spatial_map(ax, well: WellData, args) -> None:
    locations = well.channel_locations
    dx, dy = geometry_spacing(locations)
    local_x = np.linspace(-0.32 * dx, 0.32 * dx, well.templates.shape[1])
    y_scale = 0.45 * dy * float(getattr(args, "spatial_waveform_gain", 1.0))
    show_markers = bool(getattr(args, "show_spatial_markers", True))
    show_unit_labels = bool(getattr(args, "show_spatial_unit_labels", True))
    relevant_channels: set[int] = set()
    channel_occurrences: dict[int, list[UnitData]] = {}
    for unit in well.units:
        channel_occurrences.setdefault(unit.best_channel_index, []).append(unit)
    for unit in well.units:
        distances = np.linalg.norm(locations - unit.best_channel_xy[None, :], axis=1)
        channel_count = max(1, min(int(args.surrounding_channels_per_unit), locations.shape[0]))
        channels = np.argsort(distances)[:channel_count].astype(int).tolist()
        if unit.best_channel_index not in channels:
            channels.append(unit.best_channel_index)
        relevant_channels.update(channels)
        scale = max(float(np.ptp(unit.template[:, unit.best_channel_index])), 1e-12)
        for channel_index in sorted(set(channels)):
            waveform = baseline(unit.template[:, channel_index]) / scale
            strength = float(unit.normalized_footprint[channel_index])
            x0, y0 = locations[channel_index]
            ax.plot(
                x0 + local_x,
                y0 + waveform * y_scale,
                color=unit.color,
                alpha=0.18 + 0.72 * strength,
                linewidth=0.50 + 1.05 * strength,
                zorder=3 + strength,
            )
        x, y = unit.best_channel_xy
        same_channel = channel_occurrences[unit.best_channel_index]
        same_rank = next(index for index, candidate in enumerate(same_channel) if candidate is unit)
        y_offset = (same_rank - 0.5 * (len(same_channel) - 1)) * 0.16 * dy
        if show_markers:
            ax.scatter(
                [x],
                [y],
                s=43 + 12 * same_rank,
                facecolor="white",
                edgecolor=unit.color,
                linewidth=1.25,
                zorder=10 + same_rank,
            )
        if show_unit_labels:
            ax.text(
                x + 0.07 * dx,
                y + 0.07 * dy + y_offset,
                f"{unit.class_label} {int(float(unit.row['unit_id']))}",
                color=unit.color,
                fontsize=6.8,
                fontweight="bold",
                ha="left",
                va="bottom",
                zorder=12,
            )
    relevant_xy = locations[sorted(relevant_channels)]
    ax.set_xlim(float(np.min(relevant_xy[:, 0]) - 0.62 * dx), float(np.max(relevant_xy[:, 0]) + 0.62 * dx))
    ax.set_ylim(float(np.min(relevant_xy[:, 1]) - 0.60 * dy), float(np.max(relevant_xy[:, 1]) + 0.62 * dy))
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.text(
        0.0,
        1.01,
        "Spatial waveform footprints",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=7.8,
        color="#555555",
    )
    duration_ms = well.templates.shape[1] * 1000.0 / well.sampling_frequency_hz
    scale_width = 0.64 * dx * 1.0 / max(duration_ms, 1e-12)
    x0 = float(np.min(relevant_xy[:, 0]))
    y0 = float(np.max(relevant_xy[:, 1]) + 0.43 * dy)
    ax.plot([x0, x0 + scale_width], [y0, y0], color=NEUTRAL, linewidth=0.8, zorder=20)
    ax.text(x0 + scale_width * 0.5, y0 + 0.06 * dy, "1 ms", ha="center", va="bottom", fontsize=6.2, color="#555555")


def plot_combined_spatial_map(ax, well: WellData, args) -> None:
    locations = well.channel_locations
    dx, dy = geometry_spacing(locations)
    local_x = np.linspace(-0.34 * dx, 0.34 * dx, well.templates.shape[1])
    y_scale = 0.30 * dy
    relevant_channels: set[int] = set()
    channel_occurrences: dict[int, list[UnitData]] = {}
    for unit in well.units:
        channel_occurrences.setdefault(unit.best_channel_index, []).append(unit)
    for unit in well.units:
        distances = np.linalg.norm(locations - unit.best_channel_xy[None, :], axis=1)
        channel_count = max(1, min(int(args.surrounding_channels_per_unit), locations.shape[0]))
        channels = np.argsort(distances)[:channel_count].astype(int).tolist()
        if unit.best_channel_index not in channels:
            channels.append(unit.best_channel_index)
        relevant_channels.update(channels)
        scale = max(float(np.ptp(unit.template[:, unit.best_channel_index])), 1e-12)
        for channel_index in sorted(set(channels)):
            waveform = baseline(unit.template[:, channel_index]) / scale
            strength = float(unit.normalized_footprint[channel_index])
            x0, y0 = locations[channel_index]
            ax.plot(
                x0 + local_x,
                y0 + waveform * y_scale,
                color=unit.color,
                alpha=0.25 + 0.68 * strength,
                linewidth=0.55 + 1.05 * strength,
                zorder=3 + strength,
            )
        x, y = unit.best_channel_xy
        same_channel_units = channel_occurrences[unit.best_channel_index]
        same_channel_rank = next(index for index, candidate in enumerate(same_channel_units) if candidate is unit)
        vertical_offset = (same_channel_rank - 0.5 * (len(same_channel_units) - 1)) * 0.18 * dy
        ax.scatter(
            [x],
            [y],
            s=78 + 22 * same_channel_rank,
            facecolor="white",
            edgecolor=unit.color,
            linewidth=1.8,
            zorder=10 + same_channel_rank,
        )
        ax.text(
            x + 0.08 * dx,
            y + 0.08 * dy + vertical_offset,
            f"{unit.class_label} u{unit.row['unit_id']}",
            color=unit.color,
            fontsize=8,
            fontweight="bold",
            ha="left",
            va="bottom",
            zorder=11,
        )
    if not relevant_channels:
        relevant_channels = {unit.best_channel_index for unit in well.units}
    relevant_xy = locations[sorted(relevant_channels)]
    ax.set_xlim(float(np.min(relevant_xy[:, 0]) - dx), float(np.max(relevant_xy[:, 0]) + dx))
    ax.set_ylim(float(np.min(relevant_xy[:, 1]) - dy), float(np.max(relevant_xy[:, 1]) + dy))
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title("All qualifying units on one spatial map", loc="left", fontsize=11, color=NEUTRAL, pad=10)
    duration_ms = well.templates.shape[1] * 1000.0 / well.sampling_frequency_hz
    scale_width = 0.68 * dx * 1.0 / max(duration_ms, 1e-12)
    scale_x = float(np.min(relevant_xy[:, 0]))
    scale_y = float(np.max(relevant_xy[:, 1]) + 0.66 * dy)
    ax.plot([scale_x, scale_x + scale_width], [scale_y, scale_y], color=NEUTRAL, linewidth=1.0, zorder=20)
    ax.text(scale_x + scale_width * 0.5, scale_y + 0.08 * dy, "1 ms", ha="center", va="bottom", fontsize=7, color=NEUTRAL)
    legend_lines = []
    for unit in well.units:
        ttr = float(unit.row["ttr90_ms"])
        legend_lines.append(
            f"{unit.class_label} u{unit.row['unit_id']}   TTR90 {ttr:.3f} ms   "
            f"n={unit.spike_times_s.size:,}   ISI<2 ms {100 * unit.isi_lt_2ms_fraction:.2f}%   "
            f"KSLabel {unit.ks_label or 'NA'}"
        )
    y0 = 0.02
    for index, (unit, label) in enumerate(zip(well.units, legend_lines)):
        ax.text(0.01, y0 + 0.048 * (len(legend_lines) - 1 - index), "—", transform=ax.transAxes, color=unit.color, fontsize=12, va="bottom")
        ax.text(0.055, y0 + 0.048 * (len(legend_lines) - 1 - index), label, transform=ax.transAxes, color=NEUTRAL, fontsize=7.4, va="bottom")
    ax.text(
        0.01,
        -0.045,
        "Spatial traces normalized within unit by its best-channel template PTP; no smoothing.",
        transform=ax.transAxes,
        fontsize=7.5,
        color="#666666",
        ha="left",
        va="top",
    )


def plot_correlogram_matrix(fig, grid, well: WellData, args) -> None:
    units = well.units
    for row_index, row_unit in enumerate(units):
        for col_index, col_unit in enumerate(units):
            ax = fig.add_subplot(grid[row_index, col_index])
            if row_index > col_index:
                ax.axis("off")
                continue
            is_auto = row_index == col_index
            bins, counts = correlogram(
                row_unit.spike_times_s,
                col_unit.spike_times_s,
                window_ms=args.correlogram_window_ms,
                bin_ms=args.correlogram_bin_ms,
                exclude_self=is_auto,
            )
            if is_auto:
                ax.bar(bins, counts, width=args.correlogram_bin_ms, color=row_unit.color, alpha=0.92, linewidth=0)
                title = "ACG"
            else:
                negative = bins < 0
                positive = ~negative
                ax.bar(
                    bins[negative],
                    counts[negative],
                    width=args.correlogram_bin_ms,
                    color=col_unit.color,
                    alpha=0.88,
                    linewidth=0,
                )
                ax.bar(
                    bins[positive],
                    counts[positive],
                    width=args.correlogram_bin_ms,
                    color=row_unit.color,
                    alpha=0.88,
                    linewidth=0,
                )
                title = "CCG"
            ax.axvspan(-2.0, 2.0, color="#BDBDBD", alpha=0.18, linewidth=0, zorder=0)
            ax.axvline(0, color="#555555", linewidth=0.55, zorder=4)
            ax.set_xlim(-args.correlogram_window_ms, args.correlogram_window_ms)
            ax.set_ylim(bottom=0)
            ax.set_title(title, fontsize=7.2, color=NEUTRAL, pad=2.5)
            ax.tick_params(axis="both", labelsize=6.2, length=2.2, width=0.6, pad=1.5, colors=NEUTRAL)
            ax.set_xticks([-args.correlogram_window_ms, 0, args.correlogram_window_ms])
            if row_index != len(units) - 1:
                ax.set_xticklabels([])
            else:
                ax.set_xlabel("lag (ms)", fontsize=7, labelpad=2)
            if not is_auto:
                ax.set_yticklabels([])
            else:
                ax.set_ylabel("count", fontsize=7.2, color=row_unit.color, labelpad=4)
            if row_index == 0:
                ax.text(
                    0.5,
                    1.12,
                    f"{col_unit.class_label} u{col_unit.row['unit_id']}",
                    transform=ax.transAxes,
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    fontweight="bold",
                    color=col_unit.color,
                )
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_color("#777777")
            ax.spines["bottom"].set_color("#777777")
def candidate_score(units: list[UnitData], pitch_um: float) -> float:
    if not units or {unit.class_label for unit in units} != {"FS", "RS"}:
        return -np.inf
    confidence = []
    acg = []
    spikes = []
    amplitudes = []
    acg_support = []
    acg_trough = []
    for unit in units:
        ttr = float(unit.row["ttr90_ms"])
        margin = 0.40 - ttr if unit.class_label == "FS" else ttr - 0.56
        confidence.append(min(max(margin, 0.0) / 0.16, 1.0))
        acg.append(1.0 - min(unit.isi_lt_2ms_fraction / 0.01, 1.0))
        spikes.append(min(unit.spike_times_s.size / 1000.0, 1.0))
        amplitudes.append(min(float(np.max(unit.footprint)) / 30.0, 1.0))
        bins, counts = correlogram(
            unit.spike_times_s,
            unit.spike_times_s,
            window_ms=50.0,
            bin_ms=1.0,
            exclude_self=True,
        )
        acg_support.append(min(np.log1p(float(np.sum(counts))) / np.log1p(500.0), 1.0))
        central = np.abs(bins) < 2.0
        side = (np.abs(bins) >= 10.0) & (np.abs(bins) <= 50.0)
        central_rate = float(np.mean(counts[central])) if np.any(central) else 0.0
        side_rate = float(np.mean(counts[side])) if np.any(side) else 0.0
        ratio = central_rate / side_rate if side_rate > 0 else (0.0 if central_rate == 0 else np.inf)
        acg_trough.append(1.0 - min(ratio, 1.0))
    separations = []
    overlaps = []
    for first, second in itertools.combinations(units, 2):
        separations.append(min(float(np.linalg.norm(first.best_channel_xy - second.best_channel_xy)) / max(2 * pitch_um, 1e-12), 1.0))
        overlaps.append(cosine(first.normalized_footprint, second.normalized_footprint))
    class_balance = min(sum(unit.class_label == "FS" for unit in units), sum(unit.class_label == "RS" for unit in units))
    return float(
        2.0 * np.mean(acg)
        + 1.25 * np.mean(acg_support)
        + 0.75 * np.mean(acg_trough)
        + 1.8 * np.mean(confidence)
        + 0.9 * np.mean(spikes)
        + 0.7 * np.mean(amplitudes)
        + 0.8 * (np.mean(separations) if separations else 0.0)
        + 0.6 * (1.0 - np.mean(overlaps) if overlaps else 0.0)
        + 0.15 * class_balance
    )


def unit_manifest_rows(rank: int, well: WellData) -> list[dict[str, object]]:
    rows = []
    for unit in well.units:
        rows.append(
            {
                "candidate_rank": rank,
                "source_platform": well.source_platform,
                "recording": well.recording,
                "well": well.well,
                "unit_id": unit.row["unit_id"],
                "class_label": unit.class_label,
                "ttr90_ms": float(unit.row["ttr90_ms"]),
                "spike_count_analyzer": int(unit.spike_times_s.size),
                "isi_lt_2ms_fraction_recomputed": unit.isi_lt_2ms_fraction,
                "best_channel_index": unit.best_channel_index,
                "best_channel_x_um": float(unit.best_channel_xy[0]),
                "best_channel_y_um": float(unit.best_channel_xy[1]),
                "template_centroid_x_um": float(unit.centroid_xy[0]),
                "template_centroid_y_um": float(unit.centroid_xy[1]),
                "template_ptp_best_channel_uV": float(np.max(unit.footprint)),
                "KSLabel": unit.ks_label,
                "ContamPct": unit.contam_pct,
                "display_color": unit.color,
            }
        )
    return rows


def pair_manifest_rows(rank: int, well: WellData, args) -> list[dict[str, object]]:
    rows = []
    for first, second in itertools.combinations(well.units, 2):
        _, counts = correlogram(
            first.spike_times_s,
            second.spike_times_s,
            window_ms=args.correlogram_window_ms,
            bin_ms=args.correlogram_bin_ms,
            exclude_self=False,
        )
        rows.append(
            {
                "candidate_rank": rank,
                "source_platform": well.source_platform,
                "recording": well.recording,
                "well": well.well,
                "unit_a": first.row["unit_id"],
                "class_a": first.class_label,
                "unit_b": second.row["unit_id"],
                "class_b": second.class_label,
                "same_best_channel": first.best_channel_index == second.best_channel_index,
                "best_channel_distance_um": float(np.linalg.norm(first.best_channel_xy - second.best_channel_xy)),
                "centroid_distance_um": float(np.linalg.norm(first.centroid_xy - second.centroid_xy)),
                "footprint_cosine_overlap": cosine(first.normalized_footprint, second.normalized_footprint),
                "CCG_total_counts_in_display_window": int(np.sum(counts)),
            }
        )
    return rows


def correlogram(
    times_a: np.ndarray,
    times_b: np.ndarray,
    *,
    window_ms: float,
    bin_ms: float,
    exclude_self: bool,
) -> tuple[np.ndarray, np.ndarray]:
    times_a = np.asarray(times_a, dtype=float)
    times_b = np.asarray(times_b, dtype=float)
    window_s = window_ms / 1000.0
    edges = np.arange(-window_ms, window_ms + bin_ms * 1.0001, bin_ms)
    values: list[np.ndarray] = []
    for time in times_a:
        left = int(np.searchsorted(times_b, time - window_s, side="left"))
        right = int(np.searchsorted(times_b, time + window_s, side="right"))
        if right <= left:
            continue
        delta = (times_b[left:right] - time) * 1000.0
        if exclude_self:
            delta = delta[np.abs(delta) > 1e-9]
        if delta.size:
            values.append(delta)
    pooled = np.concatenate(values) if values else np.empty(0, dtype=float)
    counts, _ = np.histogram(pooled, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2.0
    return centers, counts


def templates_average(extension) -> np.ndarray:
    try:
        return np.asarray(extension.get_data(operator="average"), dtype=float)
    except TypeError:
        data = extension.get_data()
        if isinstance(data, dict):
            data = data.get("average")
        return np.asarray(data, dtype=float)


def sorting_property_map(sorting, property_name: str) -> dict[str, object]:
    try:
        values = sorting.get_property(property_name)
    except Exception:
        return {}
    if values is None:
        return {}
    return {str(unit_id): values[index] for index, unit_id in enumerate(sorting.unit_ids) if index < len(values)}


def unit_for_sorting(value: object, lookup: dict[str, object]) -> object:
    candidates = [str(value)]
    try:
        candidates.append(str(int(float(value))))
    except (TypeError, ValueError):
        pass
    for candidate in candidates:
        if candidate in lookup:
            return lookup[candidate]
    raise KeyError(f"unit {value!r} was not found in sorting")


def class_colors(preliminary: list[dict[str, object]]) -> list[str]:
    by_class: dict[str, list[int]] = {"FS": [], "RS": []}
    for index, unit in enumerate(preliminary):
        by_class[unit["class_label"]].append(index)
    colors = [NEUTRAL] * len(preliminary)
    for class_label, indices in by_class.items():
        base = FS_BASE if class_label == "FS" else RS_BASE
        variants = palette_variants(base, len(indices))
        for index, color in zip(indices, variants):
            colors[index] = color
    return colors


def palette_variants(base: str, count: int) -> list[str]:
    if count <= 1:
        return [base]
    rgb = np.asarray(to_rgb(base), dtype=float)
    amounts = np.linspace(-0.16, 0.20, count)
    colors = []
    for amount in amounts:
        adjusted = rgb * (1.0 + amount) if amount <= 0 else rgb + (1.0 - rgb) * amount
        colors.append(matplotlib.colors.to_hex(np.clip(adjusted, 0, 1)))
    return colors


def baseline(waveform: np.ndarray) -> np.ndarray:
    waveform = np.asarray(waveform, dtype=float)
    return waveform - np.nanmedian(waveform[: min(5, waveform.size)])


def weighted_centroid(locations: np.ndarray, weights: np.ndarray) -> np.ndarray:
    total = float(np.nansum(weights))
    if total <= 0:
        return np.full(2, np.nan)
    return np.nansum(locations * weights[:, None], axis=0) / total


def minimum_channel_pitch(locations: np.ndarray) -> float:
    distances = np.linalg.norm(locations[:, None, :] - locations[None, :, :], axis=2)
    nonzero = distances[np.isfinite(distances) & (distances > 1e-9)]
    return float(np.min(nonzero)) if nonzero.size else np.nan


def geometry_spacing(locations: np.ndarray) -> tuple[float, float]:
    x_unique = np.unique(np.round(locations[:, 0], 6))
    y_unique = np.unique(np.round(locations[:, 1], 6))
    dx_values = np.diff(np.sort(x_unique))
    dy_values = np.diff(np.sort(y_unique))
    dx = float(np.median(dx_values[dx_values > 0])) if np.any(dx_values > 0) else 350.0
    dy = float(np.median(dy_values[dy_values > 0])) if np.any(dy_values > 0) else 350.0
    return dx, dy


def cosine(first: np.ndarray, second: np.ndarray) -> float:
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    return float(np.dot(first, second) / denominator) if denominator > 0 else np.nan


def nice_count_limit(value: float) -> float:
    if not np.isfinite(value) or value <= 0:
        return 1.0
    magnitude = 10.0 ** np.floor(np.log10(value))
    scaled = value / magnitude
    if scaled <= 1.0:
        factor = 1.0
    elif scaled <= 2.0:
        factor = 2.0
    elif scaled <= 5.0:
        factor = 5.0
    else:
        factor = 10.0
    return float(factor * magnitude)


def safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def candidate_stem(rank: int, well: WellData) -> str:
    platform = re.sub(r"[^A-Za-z0-9]+", "_", well.source_platform).strip("_").lower()
    recording = re.sub(r"[^A-Za-z0-9_.-]+", "_", well.recording).strip("_")
    if len(recording) > 96:
        recording = recording[:96].rstrip("_")
    return f"candidate_{rank:02d}_{platform}_{well.well}_{recording}_mixed_FS_RS_spatial_ACG_CCG"


if __name__ == "__main__":
    raise SystemExit(main())
