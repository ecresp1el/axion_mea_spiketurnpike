#!/usr/bin/env python
"""Render within-well spatial-isolation panels."""

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

import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpecFromSubplotSpec
import numpy as np
import pandas as pd


PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_JOB_DIR = PROJECT_ROOT / "jobs" / "step1_nonlfp_th5_v5_ground_truth_latest"
DEFAULT_SELECTION_ROOT = DEFAULT_JOB_DIR / "representative_units_20260709_final_selection_20260709_174251"
DEFAULT_SCORE_ROOT = DEFAULT_JOB_DIR / "representative_units_20260709_abc_scoring_20260709_172908"

GROUPS = ["lumos", "cytoview_dorsal", "cytoview_ventral"]
GROUP_LABELS = {
    "lumos": "Lumos geometry",
    "cytoview_dorsal": "Cytoview dorsal",
    "cytoview_ventral": "Cytoview ventral",
}
UNIT_COLORS = ["#1f77b4", "#d95f02", "#2ca02c", "#9467bd"]
ERROR_COLUMNS = ["selection_group", "recording", "well", "analyzer_path", "error_type", "error"]


@dataclass
class AnalyzerBundle:
    analyzer: object
    unit_ids: list[object]
    unit_index: dict[str, int]
    sampling_frequency_hz: float
    templates: np.ndarray
    nbefore: int
    channel_locations: np.ndarray


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-root", type=Path, default=DEFAULT_SELECTION_ROOT)
    parser.add_argument("--score-root", type=Path, default=DEFAULT_SCORE_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--date-label", default="20260709")
    parser.add_argument("--units-per-panel", type=int, default=3)
    parser.add_argument("--min-spikes", type=int, default=100)
    parser.add_argument("--footprint-threshold", type=float, default=0.12)
    parser.add_argument("--correlogram-window-ms", type=float, default=80.0)
    parser.add_argument("--correlogram-bin-ms", type=float, default=2.0)
    parser.add_argument("--layout", choices=["1x2", "1x3"], default="1x2")
    parser.add_argument("--highlight-channels-per-unit", type=int, default=8)
    parser.add_argument("--limit-per-group", type=int, default=0)
    args = parser.parse_args()

    import spikeinterface.full as si

    selection_root = args.selection_root.expanduser().resolve()
    score_root = args.score_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    spatial_units = pd.read_csv(score_root / f"waveC_spatial_footprint_unit_scores_{args.date_label}.csv")
    spatial_units = add_selection_group(spatial_units)
    bundle_cache: dict[str, AnalyzerBundle] = {}
    rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []

    for group in GROUPS:
        selected_path = selection_root / f"final_selection_{group}_waveC_spatial_wells_{args.date_label}.csv"
        if not selected_path.exists():
            continue
        selected_wells = pd.read_csv(selected_path)
        if args.limit_per_group > 0:
            selected_wells = selected_wells.head(args.limit_per_group)
        for well_row in selected_wells.to_dict("records"):
            try:
                bundle = get_bundle(si, bundle_cache, well_row["analyzer_path"])
                unit_rows = spatial_units.loc[
                    spatial_units["recording"].astype(str).eq(str(well_row["recording"]))
                    & spatial_units["well"].astype(str).eq(str(well_row["well"]))
                    & spatial_units["selection_group"].astype(str).eq(group)
                ].copy()
                if unit_rows.empty:
                    raise ValueError("no spatial unit rows matched selected well")
                selected_units, subset_metrics = choose_unit_subset(unit_rows, bundle, args)
                figure_path = render_panel(well_row, selected_units, subset_metrics, bundle, output_dir, args)
                rows.append(
                    {
                        "selection_group": group,
                        "recording": well_row.get("recording", ""),
                        "well": well_row.get("well", ""),
                        "analyzer_path": well_row.get("analyzer_path", ""),
                        "figure_path": str(figure_path),
                        "unit_ids": ";".join(str(row["unit_id"]) for row in selected_units),
                        "unit_count": len(selected_units),
                        **subset_metrics,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "selection_group": group,
                        "recording": well_row.get("recording", ""),
                        "well": well_row.get("well", ""),
                        "analyzer_path": well_row.get("analyzer_path", ""),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )

    manifest = pd.DataFrame(rows)
    errors_df = pd.DataFrame(errors, columns=ERROR_COLUMNS)
    output_stem = f"spatial_isolation_{args.layout}"
    manifest_path = output_dir / f"{output_stem}_manifest_{args.date_label}.csv"
    errors_path = output_dir / f"{output_stem}_errors_{args.date_label}.csv"
    provenance_path = output_dir / f"{output_stem}_provenance_{args.date_label}.json"
    manifest.to_csv(manifest_path, index=False)
    errors_df.to_csv(errors_path, index=False)
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "selection_root": str(selection_root),
        "score_root": str(score_root),
        "output_dir": str(output_dir),
        "parameters": {
            "units_per_panel": args.units_per_panel,
            "min_spikes": args.min_spikes,
            "footprint_threshold": args.footprint_threshold,
            "correlogram_window_ms": args.correlogram_window_ms,
            "correlogram_bin_ms": args.correlogram_bin_ms,
            "layout": args.layout,
            "highlight_channels_per_unit": args.highlight_channels_per_unit,
            "limit_per_group": args.limit_per_group,
        },
        "selection_logic": (
            "Within each selected Wave C well, choose a subset of good units that balances spike count, "
            "best-channel distance, and low normalized template-footprint cosine overlap."
        ),
        "panel_logic": panel_logic_description(args.layout),
        "outputs": {
            "manifest": str(manifest_path),
            "errors": str(errors_path),
        },
        "rendered_panel_count": int(len(manifest)),
        "error_count": int(len(errors_df)),
    }
    provenance_path.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Spatial isolation {args.layout} render complete")
    print(f"Rendered panels: {len(manifest)}")
    print(f"Errors: {len(errors_df)}")
    print(f"Output dir: {output_dir}")
    return 0 if errors_df.empty else 1


def get_bundle(si, cache: dict[str, AnalyzerBundle], analyzer_path: str) -> AnalyzerBundle:
    analyzer_path = str(Path(analyzer_path).expanduser().resolve())
    if analyzer_path in cache:
        return cache[analyzer_path]
    analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
    unit_ids = list(analyzer.sorting.unit_ids)
    unit_index = {str(unit_id): idx for idx, unit_id in enumerate(unit_ids)}
    templates_ext = analyzer.get_extension("templates")
    if templates_ext is None:
        raise ValueError("missing templates extension")
    bundle = AnalyzerBundle(
        analyzer=analyzer,
        unit_ids=unit_ids,
        unit_index=unit_index,
        sampling_frequency_hz=float(analyzer.recording.get_sampling_frequency()),
        templates=templates_average(templates_ext),
        nbefore=int(getattr(templates_ext, "nbefore", 0)),
        channel_locations=np.asarray(analyzer.recording.get_channel_locations(), dtype=float),
    )
    cache[analyzer_path] = bundle
    return bundle


def choose_unit_subset(unit_rows: pd.DataFrame, bundle: AnalyzerBundle, args) -> tuple[list[dict[str, object]], dict[str, object]]:
    candidates = []
    for row in unit_rows.to_dict("records"):
        unit_id = unit_id_for_sorting(row["unit_id"], bundle)
        unit_idx = bundle.unit_index.get(str(unit_id))
        if unit_idx is None:
            continue
        template = bundle.templates[unit_idx]
        footprint = np.ptp(template, axis=0).astype(float)
        norm = footprint / max(float(np.nanmax(footprint)), 1e-9)
        best_channel = int(np.nanargmax(footprint))
        row.update(
            {
                "sorting_unit_id": unit_id,
                "unit_index": unit_idx,
                "footprint": footprint,
                "normalized_footprint": norm,
                "best_channel_index_rendered": best_channel,
                "best_channel_xy_rendered": bundle.channel_locations[best_channel, :2],
            }
        )
        candidates.append(row)
    if len(candidates) < 2:
        raise ValueError("need at least two units for spatial isolation panel")

    spike_filtered = [row for row in candidates if int(row.get("num_spikes", 0)) >= args.min_spikes]
    pool = spike_filtered if len(spike_filtered) >= 2 else candidates
    subset_size = min(max(2, args.units_per_panel), len(pool))
    best_subset = None
    best_metrics = None
    for subset in itertools.combinations(pool, subset_size):
        metrics = subset_metrics(subset)
        score = (
            0.35 * min(metrics["mean_best_channel_distance_um"] / 600.0, 1.0)
            + 0.35 * (1.0 - metrics["mean_footprint_cosine_overlap"])
            + 0.20 * min(metrics["min_num_spikes"] / max(args.min_spikes, 1), 1.0)
            + 0.10 * min(metrics["mean_template_ptp_max_uV"] / 40.0, 1.0)
        )
        metrics["subset_score"] = float(score)
        if best_metrics is None or score > best_metrics["subset_score"]:
            best_subset = subset
            best_metrics = metrics
    assert best_subset is not None and best_metrics is not None
    return list(best_subset), best_metrics


def subset_metrics(subset: tuple[dict[str, object], ...]) -> dict[str, object]:
    distances = []
    overlaps = []
    for a, b in itertools.combinations(subset, 2):
        xy_a = np.asarray(a["best_channel_xy_rendered"], dtype=float)
        xy_b = np.asarray(b["best_channel_xy_rendered"], dtype=float)
        distances.append(float(np.linalg.norm(xy_a - xy_b)))
        overlaps.append(cosine_overlap(np.asarray(a["normalized_footprint"]), np.asarray(b["normalized_footprint"])))
    return {
        "mean_best_channel_distance_um": float(np.nanmean(distances)),
        "min_best_channel_distance_um": float(np.nanmin(distances)),
        "mean_footprint_cosine_overlap": float(np.nanmean(overlaps)),
        "max_footprint_cosine_overlap": float(np.nanmax(overlaps)),
        "min_num_spikes": int(min(int(row.get("num_spikes", 0)) for row in subset)),
        "mean_template_ptp_max_uV": float(np.nanmean([float(row.get("template_ptp_max_uV", np.nan)) for row in subset])),
    }


def render_panel(
    well_row: dict[str, object],
    selected_units: list[dict[str, object]],
    metrics: dict[str, object],
    bundle: AnalyzerBundle,
    output_dir: Path,
    args,
) -> Path:
    group = str(well_row.get("selection_group", "unknown"))
    panel_dir = output_dir / group
    panel_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{int(well_row.get('selection_rank_within_group', 0)):02d}_{safe_slug(well_row['recording'])}_{well_row['well']}"
    figure_path = panel_dir / f"{stem}_spatial_isolation_{args.layout}.png"

    if args.layout == "1x3":
        fig = plt.figure(figsize=(18.5, 6.4))
        outer = fig.add_gridspec(1, 3, width_ratios=[0.78, 1.10, 1.28], wspace=0.26)
        ax_mean = fig.add_subplot(outer[0, 0])
        ax_grid = fig.add_subplot(outer[0, 1])
        plot_centered_mean_waveforms(ax_mean, selected_units, bundle)
        plot_multichannel_waveforms_on_grid(ax_grid, selected_units, bundle, args)
        right = GridSpecFromSubplotSpec(len(selected_units), len(selected_units), subplot_spec=outer[0, 2], wspace=0.18, hspace=0.42)
        plot_correlogram_matrix(fig, right, selected_units, bundle, args)
    else:
        fig = plt.figure(figsize=(14.5, 6.2))
        outer = fig.add_gridspec(1, 2, width_ratios=[1.02, 1.28], wspace=0.22)
        ax_spatial = fig.add_subplot(outer[0, 0])
        plot_spatial_overlay(ax_spatial, selected_units, bundle, args)
        right = GridSpecFromSubplotSpec(len(selected_units), len(selected_units), subplot_spec=outer[0, 1], wspace=0.18, hspace=0.42)
        plot_correlogram_matrix(fig, right, selected_units, bundle, args)

    title = (
        f"{GROUP_LABELS.get(group, group)} | {well_row.get('well')} | "
        f"mean overlap={metrics['mean_footprint_cosine_overlap']:.2f}, "
        f"mean best-channel distance={metrics['mean_best_channel_distance_um']:.0f} um"
    )
    fig.suptitle(title, fontsize=12)
    fig.savefig(figure_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return figure_path


def panel_logic_description(layout: str) -> str:
    if layout == "1x3":
        return (
            "Left: centered best-channel mean waveforms. Middle: multichannel template waveforms laid out "
            "on electrode geometry. Right: auto/cross-correlogram matrix."
        )
    return "Left: overlaid normalized spatial PTP profiles. Right: auto/cross-correlogram matrix."


def plot_spatial_overlay(ax, selected_units: list[dict[str, object]], bundle: AnalyzerBundle, args) -> None:
    locations = bundle.channel_locations[:, :2]
    ax.scatter(locations[:, 0], locations[:, 1], s=13, color="#d0d0d0", zorder=1)
    for index, row in enumerate(selected_units):
        color = UNIT_COLORS[index % len(UNIT_COLORS)]
        norm = np.asarray(row["normalized_footprint"], dtype=float)
        mask = norm >= args.footprint_threshold
        ax.scatter(
            locations[mask, 0],
            locations[mask, 1],
            s=24 + 260 * norm[mask],
            color=color,
            alpha=0.30,
            edgecolor=color,
            linewidth=0.4,
            label=f"u{row['unit_id']} {row.get('fs_rs_cutoff_0p50_aligned', '')}",
            zorder=2 + index,
        )
        best = int(row["best_channel_index_rendered"])
        ax.scatter(
            [locations[best, 0]],
            [locations[best, 1]],
            s=90,
            facecolor="none",
            edgecolor=color,
            linewidth=2.0,
            zorder=10,
        )
        ax.text(locations[best, 0], locations[best, 1], f"u{row['unit_id']}", color=color, fontsize=8, ha="left", va="bottom")
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Normalized spatial profiles overlaid")
    ax.legend(loc="upper right", fontsize=8, frameon=False)


def plot_centered_mean_waveforms(ax, selected_units: list[dict[str, object]], bundle: AnalyzerBundle) -> None:
    time_ms = template_time_ms(bundle)
    for index, row in enumerate(selected_units):
        color = UNIT_COLORS[index % len(UNIT_COLORS)]
        template = bundle.templates[int(row["unit_index"])]
        best = int(row["best_channel_index_rendered"])
        waveform = baseline(template[:, best])
        ax.plot(time_ms, waveform, color=color, linewidth=1.8, label=f"u{row['unit_id']} {row.get('fs_rs_cutoff_0p50_aligned', '')}")
        trough_index = int(np.nanargmin(waveform))
        ax.scatter([time_ms[trough_index]], [waveform[trough_index]], color=color, s=18, zorder=4)
    ax.axvline(0, color="#222222", linewidth=0.7)
    ax.axhline(0, color="#d0d0d0", linewidth=0.7)
    ax.set_title("Centered mean waveforms")
    ax.set_xlabel("Time from spike center (ms)")
    ax.set_ylabel("Best-channel amplitude (uV)")
    ax.legend(fontsize=8, frameon=False)


def plot_multichannel_waveforms_on_grid(ax, selected_units: list[dict[str, object]], bundle: AnalyzerBundle, args) -> None:
    locations = bundle.channel_locations[:, :2]
    dx, dy = geometry_spacing(locations)
    x_half_width = 0.36 * dx
    y_half_height = 0.26 * dy
    local_time = np.linspace(-x_half_width, x_half_width, bundle.templates.shape[1])
    max_abs = max(
        float(np.nanmax(np.abs(baseline(bundle.templates[int(row["unit_index"]), :, int(row["best_channel_index_rendered"])]))))
        for row in selected_units
    )
    y_scale = y_half_height / max(max_abs, 1e-9)

    ax.scatter(locations[:, 0], locations[:, 1], s=9, color="#c8c8c8", alpha=0.8, zorder=1)
    for index, row in enumerate(selected_units):
        color = UNIT_COLORS[index % len(UNIT_COLORS)]
        template = bundle.templates[int(row["unit_index"])]
        footprint = np.asarray(row["footprint"], dtype=float)
        highlight_count = max(1, min(int(args.highlight_channels_per_unit), footprint.size))
        highlighted = set(np.argsort(footprint)[-highlight_count:].tolist())
        highlighted.add(int(row["best_channel_index_rendered"]))
        for channel_index in sorted(highlighted):
            waveform = baseline(template[:, channel_index])
            x0, y0 = locations[channel_index]
            strength = footprint[channel_index] / max(float(np.nanmax(footprint)), 1e-9)
            ax.plot(
                x0 + local_time,
                y0 + waveform * y_scale,
                color=color,
                alpha=0.22 + 0.65 * strength,
                linewidth=0.55 + 0.90 * strength,
                zorder=2 + strength,
            )
        best = int(row["best_channel_index_rendered"])
        ax.scatter(
            [locations[best, 0]],
            [locations[best, 1]],
            s=70,
            facecolor="none",
            edgecolor=color,
            linewidth=1.8,
            zorder=8,
        )
        ax.text(locations[best, 0], locations[best, 1], f"u{row['unit_id']}", color=color, fontsize=8, ha="left", va="bottom")
    draw_waveform_grid_scale(ax, locations, dx, dy, y_scale, bundle)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(float(np.nanmin(locations[:, 0]) - 0.72 * dx), float(np.nanmax(locations[:, 0]) + 0.72 * dx))
    ax.set_ylim(float(np.nanmin(locations[:, 1]) - 0.72 * dy), float(np.nanmax(locations[:, 1]) + 0.72 * dy))
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Multichannel waveforms on electrode grid")


def plot_correlogram_matrix(fig, grid, selected_units: list[dict[str, object]], bundle: AnalyzerBundle, args) -> None:
    for row_i, unit_a in enumerate(selected_units):
        spikes_a = spike_times(unit_a, bundle)
        for col_i, unit_b in enumerate(selected_units):
            spikes_b = spike_times(unit_b, bundle)
            ax = fig.add_subplot(grid[row_i, col_i])
            color = UNIT_COLORS[row_i % len(UNIT_COLORS)] if row_i == col_i else "#565656"
            if row_i == col_i:
                bins, counts = correlogram(spikes_a, spikes_a, args, exclude_zero=True)
                ax.set_title(f"auto u{unit_a['unit_id']}", fontsize=7)
            else:
                bins, counts = correlogram(spikes_a, spikes_b, args, exclude_zero=False)
                ax.set_title(f"u{unit_a['unit_id']} x u{unit_b['unit_id']}", fontsize=7)
            ax.bar(bins, counts, width=args.correlogram_bin_ms, color=color, alpha=0.85)
            ax.axvline(0, color="#111111", linewidth=0.7)
            ax.tick_params(labelsize=6, length=2)
            if row_i == len(selected_units) - 1:
                ax.set_xlabel("lag ms", fontsize=7)
            if col_i == 0:
                ax.set_ylabel("count", fontsize=7)


def spike_times(unit_row: dict[str, object], bundle: AnalyzerBundle) -> np.ndarray:
    frames = np.asarray(bundle.analyzer.sorting.get_unit_spike_train(unit_row["sorting_unit_id"]), dtype=float)
    return frames / bundle.sampling_frequency_hz


def template_time_ms(bundle: AnalyzerBundle) -> np.ndarray:
    return (np.arange(bundle.templates.shape[1]) - bundle.nbefore) * 1000.0 / bundle.sampling_frequency_hz


def baseline(waveform: np.ndarray) -> np.ndarray:
    return waveform - np.nanmedian(waveform[: min(5, waveform.size)])


def geometry_spacing(locations: np.ndarray) -> tuple[float, float]:
    x_unique = np.unique(np.round(locations[:, 0], 6))
    y_unique = np.unique(np.round(locations[:, 1], 6))
    dxs = np.diff(np.sort(x_unique))
    dys = np.diff(np.sort(y_unique))
    dx = float(np.nanmedian(dxs[dxs > 0])) if np.any(dxs > 0) else 350.0
    dy = float(np.nanmedian(dys[dys > 0])) if np.any(dys > 0) else dx
    return dx, dy


def draw_waveform_grid_scale(ax, locations: np.ndarray, dx: float, dy: float, y_scale: float, bundle: AnalyzerBundle) -> None:
    x0 = float(np.nanmin(locations[:, 0]) - 0.55 * dx)
    y0 = float(np.nanmin(locations[:, 1]) - 0.50 * dy)
    time_ms = 1.0
    template_duration_ms = max(bundle.templates.shape[1] * 1000.0 / bundle.sampling_frequency_hz, 1e-9)
    time_axis_width = 0.72 * dx * time_ms / template_duration_ms
    uv = 20.0
    ax.plot([x0, x0 + time_axis_width], [y0, y0], color="#333333", linewidth=0.8, zorder=10)
    ax.plot([x0, x0], [y0, y0 + uv * y_scale], color="#333333", linewidth=0.8, zorder=10)
    ax.text(x0 + time_axis_width * 0.5, y0 - 0.10 * dy, "1 ms", ha="center", va="top", fontsize=6)
    ax.text(x0 - 0.06 * dx, y0 + uv * y_scale * 0.5, "20 uV", ha="right", va="center", fontsize=6, rotation=90)


def correlogram(times_a: np.ndarray, times_b: np.ndarray, args, *, exclude_zero: bool) -> tuple[np.ndarray, np.ndarray]:
    window_s = args.correlogram_window_ms / 1000.0
    edges = np.arange(-args.correlogram_window_ms, args.correlogram_window_ms + args.correlogram_bin_ms, args.correlogram_bin_ms)
    values = []
    j0 = 0
    for t in times_a:
        while j0 < times_b.size and times_b[j0] < t - window_s:
            j0 += 1
        j = j0
        while j < times_b.size and times_b[j] <= t + window_s:
            delta = times_b[j] - t
            if not exclude_zero or abs(delta) > 1e-12:
                values.append(delta * 1000.0)
            j += 1
    counts, _ = np.histogram(values, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2.0
    return centers, counts


def add_selection_group(df: pd.DataFrame) -> pd.DataFrame:
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
    return out


def templates_average(templates_ext) -> np.ndarray:
    try:
        return np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        data = templates_ext.get_data()
        if isinstance(data, dict):
            data = data.get("average")
        return np.asarray(data, dtype=float)


def unit_id_for_sorting(value: object, bundle: AnalyzerBundle):
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


def cosine_overlap(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 0:
        return np.nan
    return float(np.dot(a, b) / denom)


def safe_slug(value: object, max_len: int = 90) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_")
    if len(slug) <= max_len:
        return slug
    return slug[:max_len].rstrip("_")


if __name__ == "__main__":
    raise SystemExit(main())
