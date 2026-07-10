#!/usr/bin/env python
"""Plot putative same-unit stability across repeated recordings from one well."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import re
import textwrap
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
DEFAULT_RAW_METADATA_CSV = (
    PROJECT_ROOT
    / "jobs"
    / "axion_file_ground_truth_20260708_filter_metadata_patch"
    / "raw_files.csv"
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
    nbefore: int
    nafter: int
    channel_locations: np.ndarray
    sampling_frequency_hz: float
    duration_s: float
    spike_vector: np.ndarray
    spike_amplitudes: np.ndarray | None
    random_spikes_ext: object | None


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
    waveform_source: str
    usable_waveform_snippets: int


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=RESULTS_ROOT)
    parser.add_argument("--recording-pattern", default=DEFAULT_PATTERN)
    parser.add_argument("--include-repeats", default="")
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
    parser.add_argument("--matching-mode", choices=["exact_channel", "spatial_drift"], default="exact_channel")
    parser.add_argument("--max-best-channel-drift-um", type=float, default=0.0)
    parser.add_argument("--local-channels", type=int, default=16)
    parser.add_argument("--best-unit-only", action="store_true")
    parser.add_argument("--raw-metadata-csv", type=Path, default=DEFAULT_RAW_METADATA_CSV)
    parser.add_argument("--direct-trace-window-start-s", type=float, default=60.0)
    parser.add_argument("--direct-trace-window-duration-s", type=float, default=1.0)
    parser.add_argument("--disable-direct-trace-row", action="store_true")
    parser.add_argument("--export-formats", default="png,pdf,svg")
    args = parser.parse_args()

    import spikeinterface.full as si

    explicit_well = args.well.strip()
    target_well = explicit_well or WELL_NUMBER_MAP.get(str(args.well_number), str(args.well_number))
    well_request_label = f"explicit well {explicit_well}" if explicit_well else f"numeric well {args.well_number}"
    well_mapping_assumption = (
        "explicit well was supplied; numeric well mapping not used"
        if explicit_well
        else "1=A1, 2=A2, 3=A3, 4=B1, 5=B2, 6=B3"
    )
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    root_rows = discover_recording_roots(args.results_root.expanduser(), args.recording_pattern)
    include_repeats = parse_repeat_list(args.include_repeats)
    if include_repeats:
        root_rows = [row for row in root_rows if row["repeat"] in include_repeats]
    bundles: dict[str, Bundle] = {}
    availability_rows: list[dict[str, object]] = []
    unit_rows: list[dict[str, object]] = []
    candidates_by_repeat: dict[str, list[UnitCandidate]] = {}

    for row in root_rows:
        repeat = row["repeat"]
        analyzer_path = row["root"] / target_well / "postprocessed" / "block0_None_recording1.zarr"
        availability = {
            "repeat": repeat,
            "well_request": well_request_label,
            "well_number_requested": "" if explicit_well else args.well_number,
            "well_number_mapping_assumption": well_mapping_assumption,
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
        if args.best_unit_only:
            figure_paths.extend(render_best_unit_figure(selected_chains[0], bundles, availability_df, output_dir, target_well, args))
        else:
            figure_paths = render_stability_figure(selected_chains, bundles, availability_df, output_dir, target_well, args)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "results_root": str(args.results_root.expanduser().resolve()),
        "recording_pattern": args.recording_pattern,
        "well_request": well_request_label,
        "well_number_requested": "" if explicit_well else args.well_number,
        "well": target_well,
        "well_number_mapping_assumption": well_mapping_assumption,
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
            "matching_mode": args.matching_mode,
            "max_best_channel_drift_um": args.max_best_channel_drift_um,
            "best_unit_only": args.best_unit_only,
            "include_repeats": args.include_repeats,
            "raw_metadata_csv": str(args.raw_metadata_csv.expanduser()),
            "direct_trace_row": not args.disable_direct_trace_row,
            "direct_trace_window_start_s": args.direct_trace_window_start_s,
            "direct_trace_window_duration_s": args.direct_trace_window_duration_s,
        },
        "data_source": "Current Step 1 non-LFP th5 SpikeInterface sorting analyzers only.",
        "direct_trace_source": (
            "Best-unit figure direct traces are extracted with analyzer.recording.get_traces(return_in_uV=True) "
            "from the same Step 1 Neural Spikes recording stream used for Kilosort; raw_files.csv is used only "
            "to annotate acquisition timestamps."
        ),
        "missing_repeat_policy": "Repeats without a current analyzer are listed as unavailable and are not backfilled from historical sixwell_manual_primary outputs.",
        "outputs": {
            "availability": str(availability_path),
            "unit_inventory": str(unit_table_path),
            "chain_table": str(chain_table_path),
            "figures": [str(path) for path in figure_paths],
            "direct_trace_table": str(direct_trace_table_path(output_dir, target_well, args.date_label))
            if direct_trace_table_path(output_dir, target_well, args.date_label).exists()
            else "",
        },
        "usable_repeats": usable_repeats,
        "selected_chain_count": len(selected_chains),
    }
    provenance_path = output_dir / f"transient_plateing_{target_well}_recording_series_provenance_{args.date_label}.json"
    provenance_path.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print("Recording-series stability render complete")
    print(f"Well: {target_well} ({well_request_label})")
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


def parse_repeat_list(text: str) -> set[str]:
    repeats = set()
    for item in str(text).split(","):
        item = item.strip()
        if item:
            repeats.add(item.zfill(3))
    return repeats


def load_bundle(si, repeat: str, well: str, analyzer_path: Path) -> Bundle:
    analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
    templates_ext = analyzer.get_extension("templates")
    if templates_ext is None:
        raise ValueError("missing templates extension")
    spike_amplitudes_ext = analyzer.get_extension("spike_amplitudes")
    random_spikes_ext = analyzer.get_extension("random_spikes")
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
        nbefore=int(getattr(templates_ext, "nbefore", 0)),
        nafter=int(getattr(templates_ext, "nafter", 0)),
        channel_locations=np.asarray(analyzer.recording.get_channel_locations(), dtype=float),
        sampling_frequency_hz=float(analyzer.recording.get_sampling_frequency()),
        duration_s=float(analyzer.recording.get_total_duration()),
        spike_vector=np.asarray(analyzer.sorting.to_spike_vector()),
        spike_amplitudes=spike_amplitudes,
        random_spikes_ext=random_spikes_ext,
    )


def templates_average(templates_ext) -> np.ndarray:
    try:
        return np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        data = templates_ext.get_data()
        if isinstance(data, dict):
            data = data.get("average")
        return np.asarray(data, dtype=float)


def aligned_random_spike_mean(
    bundle: Bundle,
    unit_id: object,
    unit_index: int,
    channel_indices: list[int],
    *,
    alignment_channel_index: int,
    max_spikes: int = 500,
    search_radius: int = 6,
) -> tuple[np.ndarray, int, str]:
    if bundle.random_spikes_ext is None:
        return np.empty((0, len(channel_indices)), dtype=float), 0, "missing_random_spikes_extension"
    nbefore = int(bundle.nbefore)
    nafter = int(bundle.nafter)
    if nbefore <= 0 or nafter <= 0:
        nbefore = int(bundle.templates.shape[1] // 2)
        nafter = int(bundle.templates.shape[1] - nbefore)
    channel_ids = [bundle.channel_ids[int(index)] for index in channel_indices]
    align_channel_id = bundle.channel_ids[int(alignment_channel_index)]
    snippets = []
    align_snippets = []
    selected_total = 0
    for segment_index in range(bundle.analyzer.sorting.get_num_segments()):
        spike_train = np.asarray(
            bundle.analyzer.sorting.get_unit_spike_train(unit_id=unit_id, segment_index=segment_index),
            dtype=np.int64,
        )
        if spike_train.size == 0:
            continue
        try:
            selected_indices = np.asarray(
                bundle.random_spikes_ext.get_selected_indices_in_spike_train(unit_id, segment_index),
                dtype=np.int64,
            )
        except Exception:
            selected_indices = np.arange(spike_train.size, dtype=np.int64)
        selected_indices = selected_indices[(selected_indices >= 0) & (selected_indices < spike_train.size)]
        if selected_indices.size == 0:
            continue
        if selected_indices.size > max_spikes:
            keep = np.linspace(0, selected_indices.size - 1, max_spikes).round().astype(int)
            selected_indices = selected_indices[keep]
        selected_total += int(selected_indices.size)
        frames = spike_train[selected_indices]
        num_samples = int(bundle.analyzer.recording.get_num_samples(segment_index=segment_index))
        for frame in frames:
            start = int(frame) - nbefore
            end = int(frame) + nafter
            if start < 0 or end > num_samples or end <= start:
                continue
            trace = bundle.analyzer.recording.get_traces(
                segment_index=segment_index,
                start_frame=start,
                end_frame=end,
                channel_ids=channel_ids,
                return_in_uV=True,
            )
            align_trace = bundle.analyzer.recording.get_traces(
                segment_index=segment_index,
                start_frame=start,
                end_frame=end,
                channel_ids=[align_channel_id],
                return_in_uV=True,
            )
            trace = np.asarray(trace, dtype=float)
            align_trace = np.asarray(align_trace[:, 0], dtype=float)
            if trace.shape != (nbefore + nafter, len(channel_indices)) or align_trace.size != nbefore + nafter:
                continue
            snippets.append(trace)
            align_snippets.append(align_trace)
    if not snippets:
        return np.empty((0, len(channel_indices)), dtype=float), 0, f"no_usable_random_spike_snippets_selected_{selected_total}"
    snippets_array = np.stack(snippets, axis=0)
    align_array = np.stack(align_snippets, axis=0)
    aligned = align_multichannel_snippets_to_local_trough(
        snippets_array,
        align_array,
        target_index=nbefore,
        search_radius=search_radius,
    )
    return np.nanmean(aligned, axis=0), int(aligned.shape[0]), "aligned_persisted_random_spike_snippet_mean"


def align_multichannel_snippets_to_local_trough(
    snippets: np.ndarray,
    align_snippets: np.ndarray,
    *,
    target_index: int,
    search_radius: int,
) -> np.ndarray:
    aligned = np.full_like(snippets, np.nan, dtype=float)
    sample_index = np.arange(snippets.shape[1], dtype=float)
    left = max(0, target_index - search_radius)
    right = min(snippets.shape[1], target_index + search_radius + 1)
    for row_index, align_trace in enumerate(align_snippets):
        local = align_trace[left:right]
        if local.size == 0 or not np.isfinite(local).any():
            continue
        trough_index = left + int(np.nanargmin(local))
        shift = trough_index - target_index
        for channel_pos in range(snippets.shape[2]):
            aligned[row_index, :, channel_pos] = np.interp(
                sample_index + shift,
                sample_index,
                snippets[row_index, :, channel_pos],
                left=np.nan,
                right=np.nan,
            )
    return aligned


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
        template_waveform = np.asarray(template[:, best_channel_index], dtype=float)
        waveform, usable_snippets, waveform_source = aligned_random_spike_mean(
            bundle,
            unit_id,
            unit_index,
            [best_channel_index],
            alignment_channel_index=best_channel_index,
        )
        if waveform.ndim == 2 and waveform.shape[1] == 1:
            waveform = waveform[:, 0]
        else:
            waveform = template_waveform
            waveform_source = "fallback_templates_average_best_channel"
            usable_snippets = 0
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
                waveform_source=waveform_source,
                usable_waveform_snippets=int(usable_snippets),
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
        "waveform_source": candidate.waveform_source,
        "usable_waveform_snippets": candidate.usable_waveform_snippets,
    }


def build_chain_table(
    candidates_by_repeat: dict[str, list[UnitCandidate]],
    usable_repeats: list[str],
    args,
) -> tuple[pd.DataFrame, list[list[UnitCandidate]]]:
    if len(usable_repeats) < 2:
        return pd.DataFrame(), []
    rows = []
    chain_records = []
    for per_repeat in candidate_groups_for_matching(candidates_by_repeat, usable_repeats, args):
        total_combinations = int(np.prod([len(items) for items in per_repeat]))
        if total_combinations > args.max_chain_combinations_per_channel and args.matching_mode == "exact_channel":
            continue
        for combo in itertools.product(*per_repeat):
            combo = list(combo)
            spatial = best_channel_spatial_metrics(combo)
            if args.matching_mode == "spatial_drift" and spatial["max_best_channel_distance_um"] > args.max_best_channel_drift_um:
                continue
            similarities = pairwise_similarities(combo)
            firing_rates = np.asarray([candidate.firing_rate_hz for candidate in combo], dtype=float)
            ptps = np.asarray([candidate.best_channel_ptp_uV for candidate in combo], dtype=float)
            score = float(np.nanmean(similarities)) if similarities else np.nan
            max_contam = float(np.nanmax([candidate.contam_pct for candidate in combo]))
            row = {
                "chain_rank": np.nan,
                "well": combo[0].well,
                "matching_mode": args.matching_mode,
                "best_channel_index": combo[0].best_channel_index,
                "best_channel_id": combo[0].best_channel_id,
                "best_channel_indices": ";".join(str(candidate.best_channel_index) for candidate in combo),
                "best_channel_ids": ";".join(str(candidate.best_channel_id) for candidate in combo),
                "best_channel_x_values": ";".join(f"{candidate.best_channel_x:.6g}" for candidate in combo),
                "best_channel_y_values": ";".join(f"{candidate.best_channel_y:.6g}" for candidate in combo),
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
                **spatial,
            }
            row["stability_selection_score"] = stability_selection_score(row)
            row["passes_figure_thresholds"] = bool(
                row["min_abs_waveform_similarity"] >= args.min_chain_similarity
                and row["firing_rate_hz_cv"] <= args.max_chain_fr_cv
                and row["best_channel_ptp_uV_cv"] <= args.max_chain_ptp_cv
                and row["max_contam_pct"] <= args.max_chain_contam_pct
            )
            rows.append(row)
            chain_records.append((row, combo))
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
            np.nan_to_num(item[0]["stability_selection_score"], nan=-999.0),
            -np.nan_to_num(item[0]["firing_rate_hz_cv"], nan=999.0),
            -np.nan_to_num(item[0]["best_channel_ptp_uV_cv"], nan=999.0),
            np.nan_to_num(item[0]["min_abs_waveform_similarity"], nan=-1.0),
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
        (";".join(str(candidate.best_channel_index) for candidate in combo), ";".join(str(candidate.unit_id) for candidate in combo))
        for combo in selected
    }
    rows_df["selected_for_figure"] = [
        (row["best_channel_indices"], row["unit_ids"]) in selected_keys for row in rows_df.to_dict("records")
    ]
    rows_df = rows_df.sort_values("stability_selection_score", ascending=False).reset_index(drop=True)
    rows_df["stability_rank"] = np.arange(1, len(rows_df) + 1)
    return rows_df, selected


def candidate_groups_for_matching(
    candidates_by_repeat: dict[str, list[UnitCandidate]],
    usable_repeats: list[str],
    args,
) -> list[list[list[UnitCandidate]]]:
    if args.matching_mode == "spatial_drift":
        return [[candidates_by_repeat[repeat] for repeat in usable_repeats]]
    channel_sets = [{candidate.best_channel_index for candidate in candidates_by_repeat[repeat]} for repeat in usable_repeats]
    common_channels = sorted(set.intersection(*channel_sets)) if channel_sets else []
    return [
        [[candidate for candidate in candidates_by_repeat[repeat] if candidate.best_channel_index == channel] for repeat in usable_repeats]
        for channel in common_channels
    ]


def best_channel_spatial_metrics(combo: list[UnitCandidate]) -> dict[str, float]:
    xy = np.asarray([[candidate.best_channel_x, candidate.best_channel_y] for candidate in combo], dtype=float)
    if xy.shape[0] < 2:
        return {"max_best_channel_distance_um": 0.0, "mean_best_channel_distance_from_centroid_um": 0.0}
    distances = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(axis=2))
    centroid = np.nanmean(xy, axis=0)
    centroid_distances = np.sqrt(((xy - centroid[None, :]) ** 2).sum(axis=1))
    return {
        "max_best_channel_distance_um": float(np.nanmax(distances)),
        "mean_best_channel_distance_from_centroid_um": float(np.nanmean(centroid_distances)),
    }


def stability_selection_score(row: dict[str, object]) -> float:
    mean_similarity = safe_float(row.get("mean_abs_waveform_similarity"))
    min_similarity = safe_float(row.get("min_abs_waveform_similarity"))
    fr_cv = safe_float(row.get("firing_rate_hz_cv"))
    ptp_cv = safe_float(row.get("best_channel_ptp_uV_cv"))
    drift = safe_float(row.get("max_best_channel_distance_um"))
    contam = safe_float(row.get("max_contam_pct"))
    return float(
        2.0 * np.nan_to_num(mean_similarity, nan=0.0)
        + 1.0 * np.nan_to_num(min_similarity, nan=0.0)
        - 0.75 * np.nan_to_num(fr_cv, nan=10.0)
        - 0.65 * np.nan_to_num(ptp_cv, nan=10.0)
        - 0.25 * (np.nan_to_num(drift, nan=500.0) / 500.0)
        - 0.20 * (np.nan_to_num(contam, nan=20.0) / 20.0)
    )


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


def render_best_unit_figure(
    chain: list[UnitCandidate],
    bundles: dict[str, Bundle],
    availability_df: pd.DataFrame,
    output_dir: Path,
    target_well: str,
    args,
) -> list[Path]:
    direct_trace_infos = []
    if not args.disable_direct_trace_row:
        direct_trace_infos = direct_trace_info_for_chain(chain, bundles, args)
        write_direct_trace_table(direct_trace_infos, output_dir, target_well, args.date_label)
    has_direct_trace_row = bool(direct_trace_infos)

    if has_direct_trace_row:
        fig = plt.figure(figsize=(14.5, 11.1), constrained_layout=False)
        grid = GridSpec(4, 4, figure=fig, height_ratios=[1.45, 1.9, 1.1, 1.35], hspace=0.58, wspace=0.42)
    else:
        fig = plt.figure(figsize=(14.5, 8.6), constrained_layout=False)
        grid = GridSpec(3, 4, figure=fig, height_ratios=[1.55, 2.05, 1.25], hspace=0.52, wspace=0.42)

    ax_overlay = fig.add_subplot(grid[0, 0:2])
    draw_best_unit_waveform_overlay(ax_overlay, chain)

    ax_summary = fig.add_subplot(grid[0, 2:4])
    draw_best_unit_summary(ax_summary, chain, availability_df, target_well, args, has_direct_trace_row)

    for col, candidate in enumerate(chain):
        ax = fig.add_subplot(grid[1, col])
        draw_local_footprint(ax, candidate, bundles[candidate.repeat], args.local_channels)

    ax_fr = fig.add_subplot(grid[2, 0])
    ax_ptp = fig.add_subplot(grid[2, 1])
    ax_amp = fig.add_subplot(grid[2, 2])
    ax_spikes = fig.add_subplot(grid[2, 3])
    draw_single_chain_metric(ax_fr, chain, "firing_rate_hz", "Firing rate (Hz)")
    draw_single_chain_metric(ax_ptp, chain, "best_channel_ptp_uV", "Best-channel PTP (uV)")
    draw_single_chain_metric(ax_amp, chain, "amplitude_median_uV", "Spike amplitude median (uV)")
    draw_single_chain_metric(ax_spikes, chain, "num_spikes", "Spike count")

    if has_direct_trace_row:
        direct_ylim = common_direct_trace_ylim(direct_trace_infos)
        for col, info in enumerate(direct_trace_infos[:3]):
            ax = fig.add_subplot(grid[3, col])
            draw_direct_trace_panel(ax, info, direct_ylim)
        ax_note = fig.add_subplot(grid[3, 3])
        draw_direct_trace_note(ax_note, direct_trace_infos, args)

    channel_label = compact_channel_label(chain)
    fig.suptitle(f"Best putative stable unit, well {target_well}: {channel_label}", fontsize=15, fontweight="bold", y=0.985)
    stem = f"transient_plateing_{target_well}_best_unit_stability_{args.date_label}"
    paths = []
    for fmt in [item.strip().lower() for item in args.export_formats.split(",") if item.strip()]:
        path = output_dir / f"{stem}.{fmt}"
        fig.savefig(path, dpi=240, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    return paths


def draw_best_unit_waveform_overlay(ax, chain: list[UnitCandidate]) -> None:
    colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(chain)))
    for color, candidate in zip(colors, chain, strict=True):
        ax.plot(waveform_time_ms(candidate), candidate.waveform, lw=2.2, alpha=0.95, color=color, label=f"{candidate.repeat}: unit {candidate.unit_id}")
    ax.axhline(0, color="0.82", lw=0.8)
    ax.set_title("Aligned random-spike mean waveform overlay", fontsize=11)
    ax.set_xlabel("Time from trough (ms)")
    ax.set_ylabel("Mean waveform (uV)")
    ax.legend(frameon=False, fontsize=8.5, loc="best")
    ax.spines[["top", "right"]].set_visible(False)


def direct_trace_table_path(output_dir: Path, target_well: str, date_label: str) -> Path:
    return output_dir / f"transient_plateing_{target_well}_best_unit_direct_channel_trace_{date_label}.csv.gz"


def direct_trace_info_for_chain(chain: list[UnitCandidate], bundles: dict[str, Bundle], args) -> list[dict[str, object]]:
    metadata = raw_recording_metadata_by_repeat(args.raw_metadata_csv.expanduser(), [candidate.repeat for candidate in chain])
    first_start, reference_repeat = earliest_start_time_and_repeat(metadata, [candidate.repeat for candidate in chain])
    infos = []
    for candidate in chain:
        bundle = bundles[candidate.repeat]
        meta = metadata.get(candidate.repeat, {})
        start_s = max(0.0, float(args.direct_trace_window_start_s))
        duration_s = max(0.0, float(args.direct_trace_window_duration_s))
        num_samples = int(bundle.analyzer.recording.get_num_samples(segment_index=0))
        fs = float(bundle.sampling_frequency_hz)
        start_frame = int(round(start_s * fs))
        if start_frame >= num_samples:
            start_frame = max(0, num_samples - int(round(duration_s * fs)))
            start_s = start_frame / fs if fs > 0 else 0.0
        end_frame = min(num_samples, start_frame + max(1, int(round(duration_s * fs))))
        trace = bundle.analyzer.recording.get_traces(
            segment_index=0,
            start_frame=start_frame,
            end_frame=end_frame,
            channel_ids=[candidate.best_channel_id],
            return_in_uV=True,
        )
        trace = np.asarray(trace, dtype=float)
        voltage = trace[:, 0] if trace.ndim == 2 and trace.shape[1] else np.asarray([], dtype=float)
        time_s = start_s + np.arange(voltage.size, dtype=float) / fs if fs > 0 else np.arange(voltage.size, dtype=float)
        start_time = meta.get("block_vector_start_time")
        elapsed_hours = np.nan
        if isinstance(start_time, pd.Timestamp) and isinstance(first_start, pd.Timestamp):
            elapsed_hours = float((start_time - first_start).total_seconds() / 3600.0)
        infos.append(
            {
                "candidate": candidate,
                "time_s": time_s,
                "voltage_uV": voltage,
                "sampling_frequency_hz": fs,
                "trace_start_s": float(start_s),
                "trace_duration_s": float((end_frame - start_frame) / fs) if fs > 0 else np.nan,
                "start_frame": int(start_frame),
                "end_frame": int(end_frame),
                "block_vector_start_time": start_time,
                "experiment_start_time": meta.get("experiment_start_time"),
                "elapsed_hours_from_first_repeat": elapsed_hours,
                "elapsed_reference_repeat": reference_repeat,
                "raw_file": meta.get("raw_file", ""),
                "raw_name": meta.get("raw_name", ""),
                "filter_metadata_signature": meta.get("filter_metadata_signature", ""),
            }
        )
    return infos


def raw_recording_metadata_by_repeat(raw_metadata_csv: Path, repeats: list[str]) -> dict[str, dict[str, object]]:
    if not raw_metadata_csv.exists():
        return {}
    try:
        df = pd.read_csv(raw_metadata_csv)
    except Exception:
        return {}
    if df.empty:
        return {}
    metadata = {}
    raw_name = df.get("raw_name", pd.Series([""] * len(df))).astype(str)
    raw_variant = df.get("raw_variant", pd.Series([""] * len(df))).astype(str)
    raw_file = df.get("raw_file", pd.Series([""] * len(df))).astype(str)
    logical_folder = df.get("logical_folder", pd.Series([""] * len(df))).astype(str)
    for repeat in repeats:
        expected_name = f"My Experiment({str(repeat).zfill(3)}).raw"
        mask = raw_name.eq(expected_name) & raw_variant.eq("primary_raw")
        if not mask.any():
            mask = raw_file.str.endswith(expected_name)
        rows = df.loc[mask].copy()
        if rows.empty:
            continue
        preferred = rows[
            logical_folder.loc[rows.index].str.contains("Testing_mea_transient_plateing", regex=False, na=False)
            & logical_folder.loc[rows.index].str.contains("134-0150", regex=False, na=False)
        ]
        row = (preferred if not preferred.empty else rows).iloc[0]
        metadata[str(repeat).zfill(3)] = {
            "raw_name": row.get("raw_name", ""),
            "raw_file": row.get("raw_file", ""),
            "block_vector_start_time": parse_timestamp_or_none(row.get("block_vector_start_time", "")),
            "experiment_start_time": parse_timestamp_or_none(row.get("experiment_start_time", "")),
            "duration_s": safe_float(row.get("duration_s", np.nan)),
            "filter_metadata_signature": row.get("filter_metadata_signature", ""),
        }
    return metadata


def parse_timestamp_or_none(value: object) -> pd.Timestamp | None:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return None
    return timestamp


def earliest_start_time_and_repeat(metadata: dict[str, dict[str, object]], repeats: list[str]) -> tuple[pd.Timestamp | None, str]:
    starts = []
    for repeat in repeats:
        repeat_key = str(repeat).zfill(3)
        start = metadata.get(repeat_key, {}).get("block_vector_start_time")
        if isinstance(start, pd.Timestamp):
            starts.append((start, repeat_key))
    if not starts:
        return None, str(repeats[0]).zfill(3) if repeats else ""
    return min(starts, key=lambda item: item[0])


def write_direct_trace_table(infos: list[dict[str, object]], output_dir: Path, target_well: str, date_label: str) -> Path | None:
    if not infos:
        return None
    rows = []
    for info in infos:
        candidate = info["candidate"]
        time_s = np.asarray(info["time_s"], dtype=float)
        voltage = np.asarray(info["voltage_uV"], dtype=float)
        for sample_index, (sample_time_s, sample_voltage_uV) in enumerate(zip(time_s, voltage, strict=True)):
            rows.append(
                {
                    "repeat": candidate.repeat,
                    "well": candidate.well,
                    "unit_id": candidate.unit_id,
                    "best_channel_id": candidate.best_channel_id,
                    "best_channel_index": candidate.best_channel_index,
                    "sample_index_in_trace": sample_index,
                    "trace_time_s_in_recording": sample_time_s,
                    "voltage_uV": sample_voltage_uV,
                    "sampling_frequency_hz": info["sampling_frequency_hz"],
                    "trace_start_s": info["trace_start_s"],
                    "trace_duration_s": info["trace_duration_s"],
                    "block_vector_start_time": info["block_vector_start_time"],
                    "experiment_start_time": info["experiment_start_time"],
                    "elapsed_hours_from_first_repeat": info["elapsed_hours_from_first_repeat"],
                    "elapsed_reference_repeat": info["elapsed_reference_repeat"],
                    "raw_file": info["raw_file"],
                    "filter_metadata_signature": info["filter_metadata_signature"],
                    "trace_source": "Step 1 analyzer.recording Neural Spikes stream used for Kilosort",
                }
            )
    path = direct_trace_table_path(output_dir, target_well, date_label)
    pd.DataFrame(rows).to_csv(path, index=False, compression="gzip")
    return path


def common_direct_trace_ylim(infos: list[dict[str, object]]) -> tuple[float, float]:
    values = [np.asarray(info["voltage_uV"], dtype=float) for info in infos if np.asarray(info["voltage_uV"]).size]
    if not values:
        return (-1.0, 1.0)
    pooled = np.concatenate(values)
    pooled = pooled[np.isfinite(pooled)]
    if pooled.size == 0:
        return (-1.0, 1.0)
    center = float(np.nanmedian(pooled))
    half_range = float(np.nanpercentile(np.abs(pooled - center), 99.5) * 1.15)
    if not np.isfinite(half_range) or half_range <= 0:
        half_range = max(float(np.nanmax(np.abs(pooled - center))), 1.0)
    return (center - half_range, center + half_range)


def draw_direct_trace_panel(ax, info: dict[str, object], ylim: tuple[float, float]) -> None:
    candidate = info["candidate"]
    time_s = np.asarray(info["time_s"], dtype=float)
    voltage = np.asarray(info["voltage_uV"], dtype=float)
    ax.plot(time_s, voltage, color="#2b2b2b", lw=0.75)
    ax.axhline(0, color="0.86", lw=0.7)
    ax.set_ylim(*ylim)
    if time_s.size:
        ax.set_xlim(float(time_s[0]), float(time_s[-1]))
    elapsed = info.get("elapsed_hours_from_first_repeat")
    reference_repeat = info.get("elapsed_reference_repeat", "first")
    elapsed_text = "elapsed n/a" if not np.isfinite(elapsed) else f"+{elapsed:.2f} h from repeat {reference_repeat}"
    ax.set_title(
        f"Repeat {candidate.repeat}: ch {candidate.best_channel_id}\n{elapsed_text}",
        fontsize=9.5,
    )
    ax.set_xlabel("Time in recording (s)")
    ax.set_ylabel("Voltage (uV)")
    ax.grid(axis="y", color="0.9", lw=0.65)
    ax.spines[["top", "right"]].set_visible(False)


def draw_direct_trace_note(ax, infos: list[dict[str, object]], args) -> None:
    ax.axis("off")
    signatures = [str(info.get("filter_metadata_signature", "")) for info in infos if str(info.get("filter_metadata_signature", ""))]
    signature = signatures[0] if signatures else "metadata signature unavailable"
    wrapped_signature = textwrap.wrap(f"Filter: {signature}", width=62) or [f"Filter: {signature}"]
    lines = [
        "Direct channel trace row",
        "Source: Step 1 analyzer.recording, return_in_uV=True.",
        f"Window: {args.direct_trace_window_start_s:.1f}-{args.direct_trace_window_start_s + args.direct_trace_window_duration_s:.1f} s in each recording.",
        "Elapsed time: raw metadata block_vector_start_time, relative to first displayed repeat.",
        *wrapped_signature,
    ]
    ax.text(0.0, 0.98, "\n".join(lines), ha="left", va="top", fontsize=8.6, linespacing=1.26)


def draw_best_unit_summary(
    ax,
    chain: list[UnitCandidate],
    availability_df: pd.DataFrame,
    target_well: str,
    args,
    has_direct_trace_row: bool = False,
) -> None:
    ax.axis("off")
    usable = availability_df.loc[availability_df["status"].eq("usable"), "repeat"].astype(str).tolist()
    missing = availability_df.loc[~availability_df["status"].eq("usable"), "repeat"].astype(str).tolist()
    similarities = pairwise_similarities(chain)
    fr = np.asarray([candidate.firing_rate_hz for candidate in chain], dtype=float)
    ptp = np.asarray([candidate.best_channel_ptp_uV for candidate in chain], dtype=float)
    units = ";".join(str(candidate.unit_id) for candidate in chain)
    channels = ";".join(str(candidate.best_channel_id) for candidate in chain)
    spatial = best_channel_spatial_metrics(chain)
    lines = [
        f"Well {target_well}; repeats shown: {';'.join(candidate.repeat for candidate in chain)}",
        repeat_note(args, missing),
        f"KSLabel=good chain: units {units}; best channels {channels}",
        f"Mean/min waveform similarity: {np.nanmean(similarities):.3f} / {np.nanmin(similarities):.3f}",
        f"Max best-channel drift: {spatial['max_best_channel_distance_um']:.0f} um",
        f"Firing-rate CV: {coeff_var(fr):.3f}; PTP CV: {coeff_var(ptp):.3f}",
        "Waveforms: aligned persisted random-spike snippets from current Step 1 analyzer recording.",
    ]
    if has_direct_trace_row:
        lines.append("Bottom row: direct spike-band channel trace from the Kilosort input recording.")
    ax.text(0.0, 0.96, "\n".join(lines), va="top", ha="left", fontsize=10.5, linespacing=1.35)


def repeat_note(args, missing: list[str]) -> str:
    if args.include_repeats:
        return f"Displayed repeats restricted to {args.include_repeats}; skipped 003 for even spacing, 001 is missing."
    return f"Unavailable current repeats: {', '.join(missing) if missing else 'none'}"


def draw_single_chain_metric(ax, chain: list[UnitCandidate], attr: str, ylabel: str) -> None:
    repeats = [candidate.repeat for candidate in chain]
    values = [getattr(candidate, attr) for candidate in chain]
    ax.plot(repeats, values, marker="o", lw=2.0, ms=5.5, color="#1f77b4")
    ax.set_xlabel("Repeat")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color="0.88", lw=0.75)
    ax.spines[["top", "right"]].set_visible(False)


def compact_channel_label(chain: list[UnitCandidate]) -> str:
    channels = [str(candidate.best_channel_id) for candidate in chain]
    if len(set(channels)) == 1:
        return f"channel {channels[0]}"
    return "channels " + ";".join(channels)


def draw_note_panel(ax, availability_df: pd.DataFrame, target_well: str, args) -> None:
    ax.axis("off")
    usable = availability_df.loc[availability_df["status"].eq("usable"), "repeat"].astype(str).tolist()
    missing = availability_df.loc[~availability_df["status"].eq("usable"), "repeat"].astype(str).tolist()
    if args.well.strip():
        request_line = f"Requested explicit well {args.well.strip()}."
    else:
        request_line = f"Requested numeric well {args.well_number} -> {target_well} using 1=A1, 2=A2, 3=A3, 4=B1, 5=B2, 6=B3."
    lines = [
        request_line,
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
    locations = np.asarray(bundle.channel_locations, dtype=float)
    best_loc = locations[candidate.best_channel_index]
    distances = np.linalg.norm(locations - best_loc[None, :], axis=1)
    channel_indices = np.argsort(distances)[:local_channels]
    ptp = max(abs(candidate.best_channel_ptp_uV), 1e-12)
    x_span = np.ptp(locations[channel_indices, 0]) or 1.0
    y_span = np.ptp(locations[channel_indices, 1]) or 1.0
    dx = max(x_span / 8.0, 6.0)
    dy = max(y_span / 5.5, 10.0)
    mean_waveforms, _, source = aligned_random_spike_mean(
        bundle,
        candidate.unit_id,
        candidate.unit_index,
        [int(index) for index in channel_indices],
        alignment_channel_index=candidate.best_channel_index,
    )
    if mean_waveforms.shape != (bundle.templates.shape[1], len(channel_indices)):
        mean_waveforms = np.asarray(candidate.template[:, channel_indices], dtype=float)
        source = "fallback_templates_average_local_channels"
    t = np.linspace(-0.5, 0.5, mean_waveforms.shape[0])
    for channel_position, channel_index in enumerate(channel_indices):
        loc = locations[channel_index]
        trace = mean_waveforms[:, channel_position] / ptp
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
