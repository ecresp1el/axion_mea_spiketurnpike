#!/usr/bin/env python
"""Plot putative same-unit stability across repeated recordings from one well."""

from __future__ import annotations

import argparse
import itertools
import json
import math
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
    }
)

import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np
import pandas as pd


PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
RESULTS_ROOT = PROJECT_ROOT / "results" / "aind"
DEFAULT_OUTPUT_ROOT = (
    PROJECT_ROOT
    / "jobs"
    / "step1_nonlfp_th5_v5_ground_truth_latest"
    / "transient_plateing_1340150_recording_series_stability_20260709"
)
DEFAULT_PATTERN = (
    "step1_nonlfp_th5_*Testing_mea_transient_plateing_134-0150_"
    "My_Experiment(*)_primary_Neural_Spikes_hp_200_Hz_IIR_lp_3_kHz_Kaiser_Window"
)
WELL_NUMBER_MAP = {"1": "A1", "2": "A2", "3": "A3", "4": "B1", "5": "B2", "6": "B3"}
CHAIN_COLORS = ["#1f77b4", "#d95f02", "#2ca02c", "#9467bd", "#8c564b"]


@dataclass
class Bundle:
    repeat: str
    well: str
    analyzer_path: Path
    analyzer: object
    unit_ids: list[object]
    channel_ids: list[object]
    templates: np.ndarray
    channel_locations: np.ndarray
    sampling_frequency_hz: float
    duration_s: float
    spike_vector: np.ndarray
    spike_amplitudes: np.ndarray | None


@dataclass
class UnitCandidate:
    repeat: str
    well: str
    analyzer_path: Path
    unit_id: object
    unit_index: int
    num_spikes: int
    firing_rate_hz: float
    best_channel_index: int
    best_channel_id: object
    best_channel_x: float
    best_channel_y: float
    best_channel_ptp_uV: float
    contam_pct: float
    kslabel: str
    waveform: np.ndarray
    waveform_norm: np.ndarray
    template: np.ndarray
    amplitude_median_uV: float
    amplitude_mad_uV: float


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=RESULTS_ROOT)
    parser.add_argument("--recording-pattern", default=DEFAULT_PATTERN)
    parser.add_argument("--well", default="")
    parser.add_argument("--well-number", default="3")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--date-label", default="20260709")
    parser.add_argument("--top-chains", type=int, default=3)
    parser.add_argument("--min-chain-similarity", type=float, default=0.40)
    parser.add_argument("--max-chain-fr-cv", type=float, default=0.80)
    parser.add_argument("--max-chain-ptp-cv", type=float, default=1.00)
    parser.add_argument("--max-chain-contam-pct", type=float, default=20.0)
    parser.add_argument("--max-chain-combinations-per-channel", type=int, default=25000)
    parser.add_argument("--local-channels", type=int, default=16)
    parser.add_argument("--export-formats", default="png,pdf,svg")
    args = parser.parse_args()

    import spikeinterface.full as si

    target_well = args.well.strip() or WELL_NUMBER_MAP.get(str(args.well_number), str(args.well_number))
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    root_rows = discover_recording_roots(args.results_root.expanduser(), args.recording_pattern)
    bundles: dict[str, Bundle] = {}
    availability_rows: list[dict[str, object]] = []
    unit_rows: list[dict[str, object]] = []
    candidates_by_repeat: dict[str, list[UnitCandidate]] = {}

    for row in root_rows:
        repeat = row["repeat"]
        analyzer_path = row["root"] / target_well / "postprocessed" / "block0_None_recording1.zarr"
        availability = {
            "repeat": repeat,
            "well_number_requested": args.well_number,
            "well_number_mapping_assumption": "1=A1, 2=A2, 3=A3, 4=B1, 5=B2, 6=B3",
            "well": target_well,
            "recording_root": str(row["root"]),
            "analyzer_path": str(analyzer_path),
            "analyzer_exists": analyzer_path.exists(),
            "status": "missing_analyzer",
        }
        if analyzer_path.exists():
            try:
                bundle = load_bundle(si, repeat, target_well, analyzer_path)
                bundles[repeat] = bundle
                candidates = unit_candidates(bundle)
                candidates_by_repeat[repeat] = candidates
                availability.update(
                    {
                        "status": "usable",
                        "duration_s": bundle.duration_s,
                        "sampling_frequency_hz": bundle.sampling_frequency_hz,
                        "total_units": len(bundle.unit_ids),
                        "good_units": len(candidates),
                        "loaded_extensions": ";".join(bundle.analyzer.get_loaded_extension_names()),
                    }
                )
                for candidate in candidates:
                    unit_rows.append(unit_candidate_row(candidate))
            except Exception as exc:  # noqa: BLE001
                availability.update({"status": "load_failed", "error": f"{type(exc).__name__}: {exc}"})
        availability_rows.append(availability)

    availability_df = pd.DataFrame(availability_rows).sort_values("repeat")
    units_df = pd.DataFrame(unit_rows)
    usable_repeats = [repeat for repeat in sorted(candidates_by_repeat) if candidates_by_repeat[repeat]]
    chains_df, selected_chains = build_chain_table(candidates_by_repeat, usable_repeats, args)

    availability_path = output_dir / f"transient_plateing_{target_well}_recording_series_availability_{args.date_label}.csv"
    unit_table_path = output_dir / f"transient_plateing_{target_well}_good_unit_inventory_{args.date_label}.csv"
    chain_table_path = output_dir / f"transient_plateing_{target_well}_putative_same_channel_chains_{args.date_label}.csv"
    availability_df.to_csv(availability_path, index=False)
    units_df.to_csv(unit_table_path, index=False)
    chains_df.to_csv(chain_table_path, index=False)

    figure_paths = []
    if selected_chains:
        figure_paths = render_stability_figure(
            selected_chains,
            bundles,
            availability_df,
            output_dir,
            target_well,
            args,
        )

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "results_root": str(args.results_root.expanduser().resolve()),
        "recording_pattern": args.recording_pattern,
        "well_number_requested": args.well_number,
        "well": target_well,
        "well_number_mapping_assumption": "1=A1, 2=A2, 3=A3, 4=B1, 5=B2, 6=B3",
        "analysis_scope": "Isolated repeated-recording stability analysis; not included in dorsal/ventral summaries.",
        "matching_logic": (
            "KSLabel=good units are grouped by exact best-channel electrode across usable repeats. "
            "Chains are ranked by mean absolute normalized best-channel template cosine similarity. "
            "Figure-selected chains must also pass the configured minimum waveform-similarity, firing-rate CV, "
            "PTP CV, and saved contamination thresholds. These criteria support inspection but do not prove identity."
        ),
        "selection_thresholds": {
            "top_chains": args.top_chains,
            "min_chain_similarity": args.min_chain_similarity,
            "max_chain_fr_cv": args.max_chain_fr_cv,
            "max_chain_ptp_cv": args.max_chain_ptp_cv,
            "max_chain_contam_pct": args.max_chain_contam_pct,
        },
        "data_source": "Current Step 1 non-LFP th5 SpikeInterface sorting analyzers only.",
        "missing_repeat_policy": "Repeats without a current analyzer are listed as unavailable and are not backfilled from historical sixwell_manual_primary outputs.",
        "outputs": {
            "availability": str(availability_path),
            "unit_inventory": str(unit_table_path),
            "chain_table": str(chain_table_path),
            "figures": [str(path) for path in figure_paths],
        },
        "usable_repeats": usable_repeats,
        "selected_chain_count": len(selected_chains),
    }
    provenance_path = output_dir / f"transient_plateing_{target_well}_recording_series_provenance_{args.date_label}.json"
    provenance_path.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print("Recording-series stability render complete")
    print(f"Well: {target_well} (requested numeric well {args.well_number})")
    print(f"Usable repeats: {', '.join(usable_repeats) if usable_repeats else 'none'}")
    print(f"Selected chains: {len(selected_chains)}")
    print(f"Output dir: {output_dir}")
    for path in figure_paths:
        print(f"Figure: {path}")
    return 0 if selected_chains else 1


def discover_recording_roots(results_root: Path, pattern: str) -> list[dict[str, object]]:
    rows = []
    for root in sorted(results_root.glob(pattern)):
        match = re.search(r"My_Experiment\((\d+)\)", root.name)
        if not match:
            continue
        rows.append({"repeat": match.group(1), "root": root})
    return sorted(rows, key=lambda row: row["repeat"])


def load_bundle(si, repeat: str, well: str, analyzer_path: Path) -> Bundle:
    analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
    templates_ext = analyzer.get_extension("templates")
    if templates_ext is None:
        raise ValueError("missing templates extension")
    spike_amplitudes_ext = analyzer.get_extension("spike_amplitudes")
    spike_amplitudes = None
    if spike_amplitudes_ext is not None:
        spike_amplitudes = np.asarray(spike_amplitudes_ext.get_data(), dtype=float)
    return Bundle(
        repeat=repeat,
        well=well,
        analyzer_path=analyzer_path,
        analyzer=analyzer,
        unit_ids=list(analyzer.sorting.unit_ids),
        channel_ids=list(analyzer.recording.channel_ids),
        templates=templates_average(templates_ext),
        channel_locations=np.asarray(analyzer.recording.get_channel_locations(), dtype=float),
        sampling_frequency_hz=float(analyzer.recording.get_sampling_frequency()),
        duration_s=float(analyzer.recording.get_total_duration()),
        spike_vector=np.asarray(analyzer.sorting.to_spike_vector()),
        spike_amplitudes=spike_amplitudes,
    )


def templates_average(templates_ext) -> np.ndarray:
    try:
        return np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        data = templates_ext.get_data()
        if isinstance(data, dict):
            data = data.get("average")
        return np.asarray(data, dtype=float)


def unit_candidates(bundle: Bundle) -> list[UnitCandidate]:
    kslabels = property_values(bundle.analyzer.sorting, "KSLabel", len(bundle.unit_ids), default="")
    contam = property_values(bundle.analyzer.sorting, "ContamPct", len(bundle.unit_ids), default=np.nan)
    candidates = []
    for unit_index, unit_id in enumerate(bundle.unit_ids):
        kslabel = str(kslabels[unit_index]).lower()
        if kslabel != "good":
            continue
        template = np.asarray(bundle.templates[unit_index], dtype=float)
        ptps = np.nanmax(template, axis=0) - np.nanmin(template, axis=0)
        best_channel_index = int(np.nanargmax(np.abs(ptps)))
        waveform = np.asarray(template[:, best_channel_index], dtype=float)
        waveform_norm = normalize_waveform_for_similarity(waveform)
        spike_mask = bundle.spike_vector["unit_index"] == unit_index
        num_spikes = int(np.count_nonzero(spike_mask))
        amplitudes = amplitudes_for_unit(bundle, unit_index)
        location = bundle.channel_locations[best_channel_index]
        candidates.append(
            UnitCandidate(
                repeat=bundle.repeat,
                well=bundle.well,
                analyzer_path=bundle.analyzer_path,
                unit_id=unit_id,
                unit_index=unit_index,
                num_spikes=num_spikes,
                firing_rate_hz=float(num_spikes / bundle.duration_s) if bundle.duration_s > 0 else np.nan,
                best_channel_index=best_channel_index,
                best_channel_id=bundle.channel_ids[best_channel_index],
                best_channel_x=float(location[0]),
                best_channel_y=float(location[1]),
                best_channel_ptp_uV=float(np.nanmax(waveform) - np.nanmin(waveform)),
                contam_pct=safe_float(contam[unit_index]),
                kslabel=str(kslabels[unit_index]),
                waveform=waveform,
                waveform_norm=waveform_norm,
                template=template,
                amplitude_median_uV=float(np.nanmedian(amplitudes)) if amplitudes.size else np.nan,
                amplitude_mad_uV=float(np.nanmedian(np.abs(amplitudes - np.nanmedian(amplitudes)))) if amplitudes.size else np.nan,
            )
        )
    return candidates


def property_values(sorting, key: str, n_units: int, default=math.nan) -> np.ndarray:
    try:
        values = sorting.get_property(key)
    except Exception:
        values = None
    if values is None:
        return np.asarray([default] * n_units)
    return np.asarray(values)


def normalize_waveform_for_similarity(waveform: np.ndarray) -> np.ndarray:
    centered = np.asarray(waveform, dtype=float) - float(np.nanmean(waveform))
    norm = float(np.linalg.norm(np.nan_to_num(centered)))
    if norm <= 0:
        return np.zeros(centered.shape, dtype=float)
    return centered / norm


def amplitudes_for_unit(bundle: Bundle, unit_index: int) -> np.ndarray:
    if bundle.spike_amplitudes is None or bundle.spike_amplitudes.shape[0] != bundle.spike_vector.shape[0]:
        return np.asarray([], dtype=float)
    return np.asarray(bundle.spike_amplitudes[bundle.spike_vector["unit_index"] == unit_index], dtype=float)


def safe_float(value: object) -> float:
    try:
        return float(value)
    except Exception:
        return np.nan


def unit_candidate_row(candidate: UnitCandidate) -> dict[str, object]:
    return {
        "repeat": candidate.repeat,
        "well": candidate.well,
        "analyzer_path": str(candidate.analyzer_path),
        "unit_id": candidate.unit_id,
        "unit_index": candidate.unit_index,
        "KSLabel": candidate.kslabel,
        "ContamPct": candidate.contam_pct,
        "num_spikes": candidate.num_spikes,
        "firing_rate_hz": candidate.firing_rate_hz,
        "best_channel_index": candidate.best_channel_index,
        "best_channel_id": candidate.best_channel_id,
        "best_channel_x": candidate.best_channel_x,
        "best_channel_y": candidate.best_channel_y,
        "best_channel_ptp_uV": candidate.best_channel_ptp_uV,
        "spike_amplitude_median_uV": candidate.amplitude_median_uV,
        "spike_amplitude_mad_uV": candidate.amplitude_mad_uV,
    }


def build_chain_table(
    candidates_by_repeat: dict[str, list[UnitCandidate]],
    usable_repeats: list[str],
    args,
) -> tuple[pd.DataFrame, list[list[UnitCandidate]]]:
    if len(usable_repeats) < 2:
        return pd.DataFrame(), []
    channel_sets = []
    for repeat in usable_repeats:
        channel_sets.append({candidate.best_channel_index for candidate in candidates_by_repeat[repeat]})
    common_channels = sorted(set.intersection(*channel_sets)) if channel_sets else []
    rows = []
    chain_records = []
    for channel in common_channels:
        per_repeat = [
            [candidate for candidate in candidates_by_repeat[repeat] if candidate.best_channel_index == channel]
            for repeat in usable_repeats
        ]
        total_combinations = int(np.prod([len(items) for items in per_repeat]))
        if total_combinations > args.max_chain_combinations_per_channel:
            continue
        for combo in itertools.product(*per_repeat):
            similarities = pairwise_similarities(combo)
            firing_rates = np.asarray([candidate.firing_rate_hz for candidate in combo], dtype=float)
            ptps = np.asarray([candidate.best_channel_ptp_uV for candidate in combo], dtype=float)
            score = float(np.nanmean(similarities)) if similarities else np.nan
            max_contam = float(np.nanmax([candidate.contam_pct for candidate in combo]))
            row = {
                "chain_rank": np.nan,
                "well": combo[0].well,
                "best_channel_index": channel,
                "best_channel_id": combo[0].best_channel_id,
                "repeat_count": len(combo),
                "repeats": ";".join(candidate.repeat for candidate in combo),
                "unit_ids": ";".join(str(candidate.unit_id) for candidate in combo),
                "unit_indices": ";".join(str(candidate.unit_index) for candidate in combo),
                "mean_abs_waveform_similarity": score,
                "min_abs_waveform_similarity": float(np.nanmin(similarities)) if similarities else np.nan,
                "firing_rate_hz_values": ";".join(f"{value:.6g}" for value in firing_rates),
                "firing_rate_hz_cv": coeff_var(firing_rates),
                "best_channel_ptp_uV_values": ";".join(f"{value:.6g}" for value in ptps),
                "best_channel_ptp_uV_cv": coeff_var(ptps),
                "contam_pct_values": ";".join(f"{candidate.contam_pct:.6g}" for candidate in combo),
                "max_contam_pct": max_contam,
            }
            row["passes_figure_thresholds"] = bool(
                row["min_abs_waveform_similarity"] >= args.min_chain_similarity
                and row["firing_rate_hz_cv"] <= args.max_chain_fr_cv
                and row["best_channel_ptp_uV_cv"] <= args.max_chain_ptp_cv
                and row["max_contam_pct"] <= args.max_chain_contam_pct
            )
            rows.append(row)
            chain_records.append((row, list(combo)))
    rows_df = pd.DataFrame(rows)
    if rows_df.empty:
        return rows_df, []
    sort_cols = ["mean_abs_waveform_similarity", "min_abs_waveform_similarity", "repeat_count"]
    rows_df = rows_df.sort_values(sort_cols, ascending=[False, False, False]).reset_index(drop=True)
    rows_df["chain_rank"] = np.arange(1, len(rows_df) + 1)
    rank_lookup = {
        (row["best_channel_index"], row["unit_ids"]): int(row["chain_rank"])
        for row in rows_df.to_dict("records")
    }
    selected = []
    used_units = set()
    for row, combo in sorted(
        chain_records,
        key=lambda item: (
            bool(item[0]["passes_figure_thresholds"]),
            np.nan_to_num(item[0]["mean_abs_waveform_similarity"], nan=-1.0),
            np.nan_to_num(item[0]["min_abs_waveform_similarity"], nan=-1.0),
            -np.nan_to_num(item[0]["firing_rate_hz_cv"], nan=999.0),
            -np.nan_to_num(item[0]["best_channel_ptp_uV_cv"], nan=999.0),
        ),
        reverse=True,
    ):
        if not row["passes_figure_thresholds"]:
            continue
        unit_keys = {(candidate.repeat, str(candidate.unit_id)) for candidate in combo}
        if used_units & unit_keys:
            continue
        selected.append(combo)
        used_units |= unit_keys
        if len(selected) >= args.top_chains:
            break
    selected_keys = {
        (combo[0].best_channel_index, ";".join(str(candidate.unit_id) for candidate in combo))
        for combo in selected
    }
    rows_df["selected_for_figure"] = [
        (row["best_channel_index"], row["unit_ids"]) in selected_keys for row in rows_df.to_dict("records")
    ]
    return rows_df, selected


def pairwise_similarities(combo: tuple[UnitCandidate, ...] | list[UnitCandidate]) -> list[float]:
    sims = []
    for left, right in itertools.combinations(combo, 2):
        sims.append(float(abs(np.dot(left.waveform_norm, right.waveform_norm))))
    return sims


def coeff_var(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0 or float(np.nanmean(np.abs(values))) == 0:
        return np.nan
    return float(np.nanstd(values) / np.nanmean(np.abs(values)))


def render_stability_figure(
    selected_chains: list[list[UnitCandidate]],
    bundles: dict[str, Bundle],
    availability_df: pd.DataFrame,
    output_dir: Path,
    target_well: str,
    args,
) -> list[Path]:
    repeats = sorted({candidate.repeat for chain in selected_chains for candidate in chain})
    n_chains = len(selected_chains)
    fig = plt.figure(figsize=(17.5, 11.5), constrained_layout=False)
    grid = GridSpec(
        4,
        max(3, len(repeats)),
        figure=fig,
        height_ratios=[0.85, 1.45, 2.2, 1.35],
        hspace=0.58,
        wspace=0.42,
    )

    ax_note = fig.add_subplot(grid[0, :])
    draw_note_panel(ax_note, availability_df, target_well, args)

    for chain_idx, chain in enumerate(selected_chains):
        ax = fig.add_subplot(grid[1, chain_idx])
        draw_waveform_overlay(ax, chain, chain_idx)
    for col in range(n_chains, max(3, len(repeats))):
        ax = fig.add_subplot(grid[1, col])
        ax.axis("off")

    best_chain = selected_chains[0]
    for col, candidate in enumerate(best_chain):
        ax = fig.add_subplot(grid[2, col])
        draw_local_footprint(ax, candidate, bundles[candidate.repeat], args.local_channels)
    for col in range(len(best_chain), max(3, len(repeats))):
        ax = fig.add_subplot(grid[2, col])
        ax.axis("off")

    ax_fr = fig.add_subplot(grid[3, 0])
    ax_ptp = fig.add_subplot(grid[3, 1])
    ax_amp = fig.add_subplot(grid[3, 2])
    draw_metric_trends(ax_fr, selected_chains, "firing_rate_hz", "Firing rate (Hz)")
    draw_metric_trends(ax_ptp, selected_chains, "best_channel_ptp_uV", "Best-channel PTP (uV)")
    draw_metric_trends(ax_amp, selected_chains, "amplitude_median_uV", "Saved spike amplitude median (uV)")

    fig.suptitle(
        f"Testing_mea_transient_plateing/134-0150 repeated-recording stability, well {target_well}",
        fontsize=14,
        fontweight="bold",
        y=0.985,
    )
    stem = f"transient_plateing_{target_well}_putative_same_unit_stability_{args.date_label}"
    paths = []
    for fmt in [item.strip().lower() for item in args.export_formats.split(",") if item.strip()]:
        path = output_dir / f"{stem}.{fmt}"
        fig.savefig(path, dpi=220, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    return paths


def draw_note_panel(ax, availability_df: pd.DataFrame, target_well: str, args) -> None:
    ax.axis("off")
    usable = availability_df.loc[availability_df["status"].eq("usable"), "repeat"].astype(str).tolist()
    missing = availability_df.loc[~availability_df["status"].eq("usable"), "repeat"].astype(str).tolist()
    lines = [
        f"Requested numeric well {args.well_number} -> {target_well} using 1=A1, 2=A2, 3=A3, 4=B1, 5=B2, 6=B3.",
        f"Current Step 1 analyzers usable: {', '.join(usable) if usable else 'none'}; unavailable in current analyzers: {', '.join(missing) if missing else 'none'}.",
        "Chains use KSLabel=good units only, exact same best electrode across usable repeats, ranked by absolute normalized waveform similarity.",
        "Identity is putative; firing rate, PTP, saved spike-amplitude median, and local footprint are shown to decide whether the candidate is convincing.",
    ]
    ax.text(0.01, 0.95, "\n".join(lines), va="top", ha="left", fontsize=10)


def draw_waveform_overlay(ax, chain: list[UnitCandidate], chain_idx: int) -> None:
    color = CHAIN_COLORS[chain_idx % len(CHAIN_COLORS)]
    for candidate in chain:
        t_ms = waveform_time_ms(candidate)
        ax.plot(t_ms, candidate.waveform, lw=1.8, alpha=0.9, label=f"{candidate.repeat} u{candidate.unit_id}")
    ax.axhline(0, color="0.82", lw=0.7)
    ax.set_title(
        f"Chain {chain_idx + 1}: ch {chain[0].best_channel_id}\n"
        f"mean sim {np.nanmean(pairwise_similarities(chain)):.2f}",
        fontsize=10,
        color=color,
    )
    ax.set_xlabel("Time from template window center (ms)")
    ax.set_ylabel("Template waveform (uV)")
    ax.legend(frameon=False, fontsize=8, loc="best")
    ax.spines[["top", "right"]].set_visible(False)


def waveform_time_ms(candidate: UnitCandidate) -> np.ndarray:
    n = candidate.waveform.size
    center = int(np.nanargmin(candidate.waveform))
    sf = 12500.0
    return (np.arange(n) - center) / sf * 1000.0


def draw_local_footprint(ax, candidate: UnitCandidate, bundle: Bundle, local_channels: int) -> None:
    template = np.asarray(candidate.template, dtype=float)
    locations = np.asarray(bundle.channel_locations, dtype=float)
    best_loc = locations[candidate.best_channel_index]
    distances = np.linalg.norm(locations - best_loc[None, :], axis=1)
    channel_indices = np.argsort(distances)[:local_channels]
    ptp = max(abs(candidate.best_channel_ptp_uV), 1e-12)
    x_span = np.ptp(locations[channel_indices, 0]) or 1.0
    y_span = np.ptp(locations[channel_indices, 1]) or 1.0
    dx = max(x_span / 8.0, 6.0)
    dy = max(y_span / 5.5, 10.0)
    t = np.linspace(-0.5, 0.5, template.shape[0])
    for channel_index in channel_indices:
        loc = locations[channel_index]
        trace = template[:, channel_index] / ptp
        lw = 2.2 if channel_index == candidate.best_channel_index else 1.15
        alpha = 1.0 if channel_index == candidate.best_channel_index else 0.78
        color = "#1f77b4" if channel_index == candidate.best_channel_index else "0.22"
        ax.plot(loc[0] + t * dx, loc[1] + trace * dy * 2.1, color=color, lw=lw, alpha=alpha)
        ax.scatter([loc[0]], [loc[1]], s=8, color="0.72", zorder=0)
    ax.scatter([best_loc[0]], [best_loc[1]], s=38, facecolor="#1f77b4", edgecolor="white", linewidth=0.8, zorder=4)
    pad_x = max(dx, 8.0)
    pad_y = max(dy * 2.4, 14.0)
    ax.set_xlim(np.nanmin(locations[channel_indices, 0]) - pad_x, np.nanmax(locations[channel_indices, 0]) + pad_x)
    ax.set_ylim(np.nanmin(locations[channel_indices, 1]) - pad_y, np.nanmax(locations[channel_indices, 1]) + pad_y)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(
        f"Repeat {candidate.repeat}, unit {candidate.unit_id}\n"
        f"FR {candidate.firing_rate_hz:.2f} Hz, PTP {candidate.best_channel_ptp_uV:.2f} uV",
        fontsize=10,
    )
    ax.set_xticks([])
    ax.set_yticks([])
    ax.text(
        0.02,
        0.02,
        "All traces scaled by unit best-channel PTP",
        transform=ax.transAxes,
        fontsize=7.5,
        va="bottom",
        ha="left",
        color="0.25",
    )
    for spine in ax.spines.values():
        spine.set_color("0.75")
        spine.set_linewidth(0.7)


def draw_metric_trends(ax, selected_chains: list[list[UnitCandidate]], attr: str, ylabel: str) -> None:
    for chain_idx, chain in enumerate(selected_chains):
        color = CHAIN_COLORS[chain_idx % len(CHAIN_COLORS)]
        repeats = [candidate.repeat for candidate in chain]
        values = [getattr(candidate, attr) for candidate in chain]
        ax.plot(repeats, values, marker="o", lw=1.6, ms=5, color=color, label=f"Chain {chain_idx + 1}")
    ax.set_xlabel("Repeat")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color="0.88", lw=0.7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="best")


if __name__ == "__main__":
    raise SystemExit(main())
