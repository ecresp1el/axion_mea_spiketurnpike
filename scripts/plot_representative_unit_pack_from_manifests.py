#!/usr/bin/env python
"""Render GUI-equivalent representative-unit plot panels from frozen manifests."""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
DEFAULT_JOB_DIR = PROJECT_ROOT / "jobs" / "step1_nonlfp_th5_v5_ground_truth_latest"
DEFAULT_SELECTION_ROOT = DEFAULT_JOB_DIR / "representative_units_20260709_final_selection_20260709_174251"
DEFAULT_SCORE_ROOT = DEFAULT_JOB_DIR / "representative_units_20260709_abc_scoring_20260709_172908"


GROUP_LABELS = {
    "lumos": "Lumos geometry",
    "cytoview_dorsal": "Cytoview dorsal",
    "cytoview_ventral": "Cytoview ventral",
}

GROUP_COLORS = {
    "lumos": "#2f6f9f",
    "cytoview_dorsal": "#2a9d8f",
    "cytoview_ventral": "#8e5ea2",
}

ERROR_COLUMNS = [
    "selection_group",
    "selection_wave",
    "recording",
    "well",
    "unit_id",
    "unit_id_a",
    "unit_id_b",
    "analyzer_path",
    "error_type",
    "error",
]


@dataclass
class AnalyzerBundle:
    analyzer: object
    unit_ids: list[object]
    unit_index: dict[str, int]
    sampling_frequency_hz: float
    duration_s: float
    templates: np.ndarray
    nbefore: int
    channel_locations: np.ndarray
    correlograms: np.ndarray | None
    correlogram_bins: np.ndarray | None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-root", type=Path, default=DEFAULT_SELECTION_ROOT)
    parser.add_argument("--score-root", type=Path, default=DEFAULT_SCORE_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--date-label", default="20260709")
    parser.add_argument("--bin-size-s", type=float, default=60.0)
    parser.add_argument("--correlogram-window-ms", type=float, default=100.0)
    parser.add_argument("--correlogram-bin-ms", type=float, default=2.0)
    parser.add_argument("--max-units-per-footprint", type=int, default=8)
    parser.add_argument("--limit-per-table", type=int, default=0, help="Debug limit; 0 renders all selected rows.")
    args = parser.parse_args()

    import spikeinterface.full as si

    selection_root = args.selection_root.expanduser().resolve()
    score_root = args.score_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    spatial_units = pd.read_csv(score_root / f"waveC_spatial_footprint_unit_scores_{args.date_label}.csv")
    bundle_cache: dict[str, AnalyzerBundle] = {}
    panel_rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []

    for group in ["lumos", "cytoview_dorsal", "cytoview_ventral"]:
        for wave, renderer in [
            ("waveA_stability_units", render_wave_a),
            ("waveB_correlogram_pairs", render_wave_b),
            ("waveC_spatial_wells", render_wave_c),
        ]:
            table_path = selection_root / f"final_selection_{group}_{wave}_{args.date_label}.csv"
            if not table_path.exists():
                continue
            table = pd.read_csv(table_path)
            if args.limit_per_table > 0:
                table = table.head(args.limit_per_table)
            for row in table.to_dict("records"):
                try:
                    bundle = get_bundle(si, bundle_cache, row["analyzer_path"])
                    panel = renderer(row, bundle, spatial_units, output_dir, args)
                    panel["selection_source_csv"] = str(table_path)
                    panel_rows.append(panel)
                except Exception as exc:  # noqa: BLE001 - keep rendering other selected panels
                    errors.append(
                        {
                            "selection_group": row.get("selection_group", group),
                            "selection_wave": row.get("selection_wave", wave),
                            "recording": row.get("recording", ""),
                            "well": row.get("well", ""),
                            "unit_id": row.get("unit_id", ""),
                            "unit_id_a": row.get("unit_id_a", ""),
                            "unit_id_b": row.get("unit_id_b", ""),
                            "analyzer_path": row.get("analyzer_path", ""),
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )

    panel_manifest = pd.DataFrame(panel_rows)
    errors_df = pd.DataFrame(errors, columns=ERROR_COLUMNS)
    panel_manifest_path = output_dir / f"representative_unit_plot_pack_manifest_{args.date_label}.csv"
    errors_path = output_dir / f"representative_unit_plot_pack_errors_{args.date_label}.csv"
    provenance_path = output_dir / f"representative_unit_plot_pack_provenance_{args.date_label}.json"
    panel_manifest.to_csv(panel_manifest_path, index=False)
    errors_df.to_csv(errors_path, index=False)
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "selection_root": str(selection_root),
        "score_root": str(score_root),
        "output_dir": str(output_dir),
        "date_label": args.date_label,
        "parameters": {
            "bin_size_s": args.bin_size_s,
            "correlogram_window_ms": args.correlogram_window_ms,
            "correlogram_bin_ms": args.correlogram_bin_ms,
            "max_units_per_footprint": args.max_units_per_footprint,
            "limit_per_table": args.limit_per_table,
        },
        "render_policy": {
            "source": "frozen final-selection manifests",
            "data": "Step 1 SortingAnalyzer sorting, templates, correlograms when available, and recording channel locations",
            "variant_policy": "preserve_all_raw_filter_broadband_variants_no_deduplication",
            "selection_pool_policy": "separate_lumos_cytoview_dorsal_cytoview_ventral",
        },
        "outputs": {
            "panel_manifest": str(panel_manifest_path),
            "errors": str(errors_path),
        },
        "rendered_panel_count": int(len(panel_manifest)),
        "error_count": int(len(errors_df)),
    }
    provenance_path.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print("Representative plot pack render complete")
    print(f"Rendered panels: {len(panel_manifest)}")
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
    sf = float(analyzer.recording.get_sampling_frequency())
    duration_s = float(analyzer.recording.get_num_frames()) / sf
    templates_ext = analyzer.get_extension("templates")
    if templates_ext is None:
        raise ValueError("missing templates extension")
    templates = templates_average(templates_ext)
    nbefore = int(getattr(templates_ext, "nbefore", templates.shape[1] // 2))
    channel_locations = np.asarray(analyzer.recording.get_channel_locations(), dtype=float)
    correlograms = None
    correlogram_bins = None
    if "correlograms" in set(analyzer.get_loaded_extension_names()):
        corr_data = analyzer.get_extension("correlograms").get_data()
        if isinstance(corr_data, tuple) and len(corr_data) >= 2:
            correlograms = np.asarray(corr_data[0], dtype=float)
            correlogram_bins = np.asarray(corr_data[1], dtype=float)
    bundle = AnalyzerBundle(
        analyzer=analyzer,
        unit_ids=unit_ids,
        unit_index=unit_index,
        sampling_frequency_hz=sf,
        duration_s=duration_s,
        templates=templates,
        nbefore=nbefore,
        channel_locations=channel_locations,
        correlograms=correlograms,
        correlogram_bins=correlogram_bins,
    )
    cache[analyzer_path] = bundle
    return bundle


def render_wave_a(row: dict[str, object], bundle: AnalyzerBundle, spatial_units: pd.DataFrame, output_dir: Path, args) -> dict[str, object]:
    del spatial_units
    unit_id = unit_id_for_sorting(row["unit_id"], bundle)
    unit_idx = bundle.unit_index[str(unit_id)]
    template = bundle.templates[unit_idx]
    footprint = np.ptp(template, axis=0)
    best_channel = int(np.nanargmax(footprint))
    waveform = template[:, best_channel]
    time_ms = template_time_ms(bundle)
    spike_frames = np.asarray(bundle.analyzer.sorting.get_unit_spike_train(unit_id), dtype=float)
    spike_times = spike_frames / bundle.sampling_frequency_hz
    bin_edges = np.arange(0.0, bundle.duration_s + args.bin_size_s, args.bin_size_s)
    if bin_edges.size < 2:
        bin_edges = np.array([0.0, bundle.duration_s])
    counts, _ = np.histogram(spike_times, bins=bin_edges)
    rates = counts / np.diff(bin_edges)
    centers_min = ((bin_edges[:-1] + bin_edges[1:]) / 2.0) / 60.0

    group = str(row.get("selection_group", "unknown"))
    panel_dir = output_dir / group / "waveA_stability"
    panel_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{int(row.get('selection_rank_within_group', 0)):02d}_{safe_slug(row['recording'])}_{row['well']}_u{row['unit_id']}"
    figure_path = panel_dir / f"{stem}.png"

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.8))
    color = GROUP_COLORS.get(group, "#444444")
    axes[0].plot(time_ms, waveform - np.nanmedian(waveform[: min(5, waveform.size)]), color=color, linewidth=1.8)
    axes[0].axhline(0, color="#d5d5d5", linewidth=0.8)
    axes[0].set_title("Best-channel template")
    axes[0].set_xlabel("Time from spike center (ms)")
    axes[0].set_ylabel("Amplitude (uV)")
    axes[1].plot(centers_min, rates, color=color, linewidth=1.6, marker="o", markersize=3)
    axes[1].set_title(f"Firing rate, {args.bin_size_s:g}s bins")
    axes[1].set_xlabel("Recording time (min)")
    axes[1].set_ylabel("Hz")
    title = (
        f"{GROUP_LABELS.get(group, group)} Wave A rank {row.get('selection_rank_within_group')} | "
        f"{row.get('well')} unit {row.get('unit_id')} | spikes={len(spike_times)}"
    )
    fig.suptitle(title, fontsize=11)
    fig.tight_layout()
    fig.savefig(figure_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return panel_row(row, "A", figure_path, "waveform_stability_firing_rate_over_time", unit_count=1)


def render_wave_b(row: dict[str, object], bundle: AnalyzerBundle, spatial_units: pd.DataFrame, output_dir: Path, args) -> dict[str, object]:
    del spatial_units
    unit_a = unit_id_for_sorting(row["unit_id_a"], bundle)
    unit_b = unit_id_for_sorting(row["unit_id_b"], bundle)
    idx_a = bundle.unit_index[str(unit_a)]
    idx_b = bundle.unit_index[str(unit_b)]
    group = str(row.get("selection_group", "unknown"))
    color = GROUP_COLORS.get(group, "#444444")
    panel_dir = output_dir / group / "waveB_correlograms"
    panel_dir.mkdir(parents=True, exist_ok=True)
    stem = (
        f"{int(row.get('selection_rank_within_group', 0)):02d}_{safe_slug(row['recording'])}_"
        f"{row['well']}_u{row['unit_id_a']}_u{row['unit_id_b']}"
    )
    figure_path = panel_dir / f"{stem}.png"

    wave_a, best_a = best_waveform(bundle.templates[idx_a])
    wave_b, best_b = best_waveform(bundle.templates[idx_b])
    time_ms = template_time_ms(bundle)
    spikes_a = np.asarray(bundle.analyzer.sorting.get_unit_spike_train(unit_a), dtype=float) / bundle.sampling_frequency_hz
    spikes_b = np.asarray(bundle.analyzer.sorting.get_unit_spike_train(unit_b), dtype=float) / bundle.sampling_frequency_hz
    bins_ms, ac_a = autocorr_hist(spikes_a, args.correlogram_window_ms, args.correlogram_bin_ms)
    _, ac_b = autocorr_hist(spikes_b, args.correlogram_window_ms, args.correlogram_bin_ms)
    _, cc = crosscorr_hist(spikes_a, spikes_b, args.correlogram_window_ms, args.correlogram_bin_ms)

    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.0))
    axes[0, 0].plot(time_ms, baseline(wave_a), color="#1f77b4", linewidth=1.5, label=f"u{row['unit_id_a']} {row.get('class_a', '')}")
    axes[0, 0].plot(time_ms, baseline(wave_b), color="#d95f02", linewidth=1.5, label=f"u{row['unit_id_b']} {row.get('class_b', '')}")
    axes[0, 0].axhline(0, color="#d5d5d5", linewidth=0.8)
    axes[0, 0].set_title(f"Templates, best ch {best_a}/{best_b}")
    axes[0, 0].set_xlabel("Time from spike center (ms)")
    axes[0, 0].set_ylabel("Amplitude (uV)")
    axes[0, 0].legend(fontsize=8, frameon=False)
    axes[0, 1].bar(bins_ms, ac_a, width=args.correlogram_bin_ms, color="#1f77b4", alpha=0.85)
    axes[0, 1].set_title(f"Autocorrelogram u{row['unit_id_a']}")
    axes[1, 0].bar(bins_ms, ac_b, width=args.correlogram_bin_ms, color="#d95f02", alpha=0.85)
    axes[1, 0].set_title(f"Autocorrelogram u{row['unit_id_b']}")
    axes[1, 1].bar(bins_ms, cc, width=args.correlogram_bin_ms, color=color, alpha=0.85)
    axes[1, 1].set_title("Cross-correlogram")
    for ax in [axes[0, 1], axes[1, 0], axes[1, 1]]:
        ax.axvline(0, color="#222222", linewidth=0.8)
        ax.set_xlabel("Lag (ms)")
        ax.set_ylabel("Count")
    title = (
        f"{GROUP_LABELS.get(group, group)} Wave B rank {row.get('selection_rank_within_group')} | "
        f"{row.get('well')} units {row.get('unit_id_a')}/{row.get('unit_id_b')} | "
        f"distance={float(row.get('best_channel_distance_um', np.nan)):.1f} um"
    )
    fig.suptitle(title, fontsize=11)
    fig.tight_layout()
    fig.savefig(figure_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return panel_row(row, "B", figure_path, "autocorrelogram_crosscorrelogram_fs_rs", unit_count=2)


def render_wave_c(row: dict[str, object], bundle: AnalyzerBundle, spatial_units: pd.DataFrame, output_dir: Path, args) -> dict[str, object]:
    group = str(row.get("selection_group", "unknown"))
    well_units = spatial_units.loc[
        spatial_units["recording"].astype(str).eq(str(row["recording"]))
        & spatial_units["well"].astype(str).eq(str(row["well"]))
    ].copy()
    if "selection_group" in well_units:
        well_units = well_units.loc[well_units["selection_group"].astype(str).eq(group)]
    if well_units.empty:
        raise ValueError("no Wave C unit-score rows matched selected well")
    well_units = well_units.sort_values("template_ptp_max_uV", ascending=False).head(args.max_units_per_footprint)
    panel_dir = output_dir / group / "waveC_spatial_footprints"
    panel_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{int(row.get('selection_rank_within_group', 0)):02d}_{safe_slug(row['recording'])}_{row['well']}"
    figure_path = panel_dir / f"{stem}.png"

    n_units = len(well_units)
    ncols = min(4, n_units)
    nrows = int(math.ceil(n_units / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.6 * ncols, 3.4 * nrows), squeeze=False)
    for ax in axes.flat:
        ax.axis("off")
    for ax, unit_row in zip(axes.flat, well_units.to_dict("records"), strict=False):
        unit_id = unit_id_for_sorting(unit_row["unit_id"], bundle)
        unit_idx = bundle.unit_index[str(unit_id)]
        template = bundle.templates[unit_idx]
        footprint = np.ptp(template, axis=0)
        sizes = 25 + 210 * footprint / max(float(np.nanmax(footprint)), 1e-9)
        scatter = ax.scatter(
            bundle.channel_locations[:, 0],
            bundle.channel_locations[:, 1],
            c=footprint,
            s=sizes,
            cmap="viridis",
            edgecolor="#222222",
            linewidth=0.3,
        )
        best_ch = int(np.nanargmax(footprint))
        ax.scatter(
            [bundle.channel_locations[best_ch, 0]],
            [bundle.channel_locations[best_ch, 1]],
            s=45,
            facecolor="none",
            edgecolor="#ff4d00",
            linewidth=1.5,
        )
        ax.set_aspect("equal", adjustable="box")
        ax.axis("on")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"u{unit_row['unit_id']} {unit_row.get('fs_rs_cutoff_0p50_aligned', '')}\nmax {np.nanmax(footprint):.1f} uV", fontsize=8)
        fig.colorbar(scatter, ax=ax, fraction=0.046, pad=0.02)
    title = (
        f"{GROUP_LABELS.get(group, group)} Wave C rank {row.get('selection_rank_within_group')} | "
        f"{row.get('well')} | plotted top {n_units} KSLabel=good footprints"
    )
    fig.suptitle(title, fontsize=11)
    fig.tight_layout()
    fig.savefig(figure_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return panel_row(row, "C", figure_path, "within_well_spatial_footprints", unit_count=n_units)


def panel_row(row: dict[str, object], wave: str, figure_path: Path, panel: str, *, unit_count: int) -> dict[str, object]:
    return {
        "selection_group": row.get("selection_group", ""),
        "selection_wave": wave,
        "selection_panel": panel,
        "selection_rank_within_group": row.get("selection_rank_within_group", ""),
        "recording": row.get("recording", ""),
        "well": row.get("well", ""),
        "unit_id": row.get("unit_id", ""),
        "unit_id_a": row.get("unit_id_a", ""),
        "unit_id_b": row.get("unit_id_b", ""),
        "track": row.get("track", ""),
        "region_label": row.get("region_label", ""),
        "lumos_geometry_group": row.get("lumos_geometry_group", ""),
        "raw_variant_inferred": row.get("raw_variant_inferred", ""),
        "variant_policy": row.get("variant_policy", ""),
        "selection_pool_policy": row.get("selection_pool_policy", ""),
        "analyzer_path": row.get("analyzer_path", ""),
        "rendered_unit_count": unit_count,
        "figure_path": str(figure_path),
        "gui_equivalent_rendered": True,
        "gui_equivalent_render_sources": "sorting spike trains;templates;correlograms when available;recording channel locations",
    }


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


def template_time_ms(bundle: AnalyzerBundle) -> np.ndarray:
    return (np.arange(bundle.templates.shape[1]) - bundle.nbefore) * 1000.0 / bundle.sampling_frequency_hz


def best_waveform(template: np.ndarray) -> tuple[np.ndarray, int]:
    footprint = np.ptp(template, axis=0)
    best_channel = int(np.nanargmax(footprint))
    return template[:, best_channel], best_channel


def baseline(waveform: np.ndarray) -> np.ndarray:
    return waveform - np.nanmedian(waveform[: min(5, waveform.size)])


def autocorr_hist(times: np.ndarray, window_ms: float, bin_ms: float) -> tuple[np.ndarray, np.ndarray]:
    return crosscorr_hist(times, times, window_ms, bin_ms, exclude_zero=True)


def crosscorr_hist(
    times_a: np.ndarray,
    times_b: np.ndarray,
    window_ms: float,
    bin_ms: float,
    *,
    exclude_zero: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    times_a = np.asarray(times_a, dtype=float)
    times_b = np.asarray(times_b, dtype=float)
    window_s = window_ms / 1000.0
    edges = np.arange(-window_ms, window_ms + bin_ms, bin_ms)
    values: list[float] = []
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


def safe_slug(value: object, max_len: int = 90) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_")
    if len(slug) <= max_len:
        return slug
    return slug[:max_len].rstrip("_")


if __name__ == "__main__":
    raise SystemExit(main())
