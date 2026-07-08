#!/usr/bin/env python
"""Compare stored template waveforms with extracted analyzer-recording snippets."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import zarr

from axion_mea.master_unit_table import (
    CANONICAL_MASTER_UNIT_TABLE,
    DEFAULT_STEP2_MANIFEST,
    load_canonical_master_unit_table,
    load_step2_manifest,
    paths_from_manifest_row,
)
from axion_mea.rs_fs_waveform_templates import parse_template_reference
from axion_mea.step3_repro import DEFAULT_STEP3_REPRO_DIR, write_command_repro


DEFAULT_RECORDING = "sixwell_manual_primary_5_28_26_pvreporter_134-0150_pv_reporter_cl23_dorsal_and_ventral_exp17_2(000)"
DEFAULT_WELL = "B3"
DEFAULT_UNIT_ID = 1
DEFAULT_OUTPUT_DIR = CANONICAL_MASTER_UNIT_TABLE.parent / "figures" / "rs_fs_waveforms"
DEFAULT_FIGURE = DEFAULT_OUTPUT_DIR / "figure__representative_unit_template_vs_extracted_waveforms.png"
DEFAULT_WAVEFORM_CSV = CANONICAL_MASTER_UNIT_TABLE.with_name(
    "representative_unit_template_vs_extracted_waveforms.csv"
)
DEFAULT_PROVENANCE_JSON = CANONICAL_MASTER_UNIT_TABLE.with_name(
    "representative_unit_template_vs_extracted_waveforms_provenance.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare one unit's stored template against extracted analyzer-recording snippets."
    )
    parser.add_argument("--input-csv", type=Path, default=CANONICAL_MASTER_UNIT_TABLE)
    parser.add_argument("--manifest-csv", type=Path, default=DEFAULT_STEP2_MANIFEST)
    parser.add_argument("--recording", default=DEFAULT_RECORDING)
    parser.add_argument("--well", default=DEFAULT_WELL)
    parser.add_argument("--unit-id", type=int, default=DEFAULT_UNIT_ID)
    parser.add_argument("--all-spike-subsample", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260708)
    parser.add_argument("--output-figure", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument("--waveform-csv", type=Path, default=DEFAULT_WAVEFORM_CSV)
    parser.add_argument("--provenance-json", type=Path, default=DEFAULT_PROVENANCE_JSON)
    parser.add_argument("--repro-dir", type=Path, default=DEFAULT_STEP3_REPRO_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    table = load_canonical_master_unit_table(args.input_csv)
    manifest = load_step2_manifest(args.manifest_csv)
    unit_row = select_unit_row(table, args.recording, args.well, args.unit_id)
    manifest_row = select_manifest_row(manifest, args.recording, args.well)
    paths = paths_from_manifest_row(manifest_row)

    try:
        import spikeinterface as si
    except ImportError as exc:
        raise ImportError("SpikeInterface is required to load the Step 1 SortingAnalyzer.") from exc

    analyzer = si.load(paths["analyzer_zarr"])
    sorting = si.load(paths["curated_sorting"])
    templates_ext = analyzer.get_extension("templates")
    random_spikes_ext = analyzer.get_extension("random_spikes")
    if templates_ext is None or random_spikes_ext is None:
        raise ValueError("Analyzer must contain both templates and random_spikes extensions.")
    if analyzer.recording is None:
        raise ValueError("Analyzer does not contain a recording object.")

    unit_index, channel_index = parse_template_reference(str(unit_row["template_reference"]))
    templates = np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    template_waveform = templates[unit_index, :, channel_index].astype(float)
    nbefore = int(templates_ext.nbefore)
    nafter = int(templates_ext.nafter)
    sampling_frequency_hz = float(analyzer.recording.get_sampling_frequency())
    time_ms = (np.arange(template_waveform.size) - nbefore) * 1000.0 / sampling_frequency_hz

    random_spikes = random_spikes_ext.get_random_spikes()
    unit_random_spikes = random_spikes[random_spikes["unit_index"] == unit_index]
    random_mean, random_count, random_skipped = average_snippets(
        analyzer.recording,
        unit_random_spikes["sample_index"],
        channel_index=channel_index,
        nbefore=nbefore,
        nafter=nafter,
        return_in_uV=bool(analyzer.return_in_uV),
    )

    all_spike_train = sorting.get_unit_spike_train(unit_id=args.unit_id, segment_index=0)
    all_spike_subset = choose_spikes(all_spike_train, args.all_spike_subsample, seed=args.seed)
    subset_mean, subset_count, subset_skipped = average_snippets(
        analyzer.recording,
        all_spike_subset,
        channel_index=channel_index,
        nbefore=nbefore,
        nafter=nafter,
        return_in_uV=bool(analyzer.return_in_uV),
    )

    nwb_waveform, nwb_status = load_nwb_waveform(paths["source_results_dir"], unit_index, channel_index)
    phy_status = find_phy_status(paths["source_results_dir"])

    csv = build_waveform_csv(
        time_ms=time_ms,
        template_waveform=template_waveform,
        random_mean=random_mean,
        subset_mean=subset_mean,
        nwb_waveform=nwb_waveform,
        sampling_frequency_hz=sampling_frequency_hz,
    )
    args.output_figure.parent.mkdir(parents=True, exist_ok=True)
    args.waveform_csv.parent.mkdir(parents=True, exist_ok=True)
    args.provenance_json.parent.mkdir(parents=True, exist_ok=True)
    csv.to_csv(args.waveform_csv, index=False)
    plot_comparison(
        csv=csv,
        unit_row=unit_row,
        output_figure=args.output_figure,
        random_count=random_count,
        subset_count=subset_count,
        nwb_status=nwb_status,
        phy_status=phy_status,
    )

    command_repro = write_command_repro(
        repro_dir=args.repro_dir,
        stem="compare_representative_unit_waveform_representations",
        parsed_args={key: str(value) for key, value in vars(args).items()},
    )
    random_delta = random_mean - template_waveform
    subset_delta = subset_mean - template_waveform
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "recording": args.recording,
        "well": args.well,
        "unit_id": args.unit_id,
        "unit_row": unit_row.to_dict(),
        "source_results_dir": str(paths["source_results_dir"]),
        "analyzer_zarr": str(paths["analyzer_zarr"]),
        "curated_sorting": str(paths["curated_sorting"]),
        "figure": str(args.output_figure),
        "waveform_csv": str(args.waveform_csv),
        "sampling_frequency_hz": sampling_frequency_hz,
        "sample_dt_ms": 1000.0 / sampling_frequency_hz,
        "template_shape": list(templates.shape),
        "template_unit_index": unit_index,
        "template_channel_index": channel_index,
        "nbefore": nbefore,
        "nafter": nafter,
        "template_ms_before": templates_ext.params["ms_before"],
        "template_ms_after": templates_ext.params["ms_after"],
        "templates_operators": templates_ext.params["operators"],
        "analyzer_return_in_uV": bool(analyzer.return_in_uV),
        "recording_class": f"{type(analyzer.recording).__module__}.{type(analyzer.recording).__name__}",
        "recording_dtype": str(analyzer.recording.get_dtype()),
        "recording_has_scaleable_traces": bool(analyzer.recording.has_scaleable_traces()),
        "recording_annotations": getattr(analyzer.recording, "_annotations", {}),
        "random_spike_count_used": random_count,
        "random_spike_count_skipped_for_boundaries": random_skipped,
        "all_spike_count": int(len(all_spike_train)),
        "all_spike_subsample_requested": int(args.all_spike_subsample),
        "all_spike_subsample_used": subset_count,
        "all_spike_subsample_skipped_for_boundaries": subset_skipped,
        "max_abs_delta_random_spike_mean_vs_template": float(np.nanmax(np.abs(random_delta))),
        "rms_delta_random_spike_mean_vs_template": float(np.sqrt(np.nanmean(random_delta**2))),
        "max_abs_delta_all_spike_subsample_mean_vs_template": float(np.nanmax(np.abs(subset_delta))),
        "rms_delta_all_spike_subsample_mean_vs_template": float(np.sqrt(np.nanmean(subset_delta**2))),
        "nwb_waveform_status": nwb_status,
        "phy_kilosort_waveform_status": phy_status,
        "command_repro": command_repro,
    }
    args.provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Wrote waveform representation figure: {args.output_figure}")
    print(f"Wrote waveform representation CSV: {args.waveform_csv}")
    print(f"Wrote waveform representation provenance: {args.provenance_json}")
    print(
        "Random-spike snippet mean vs stored template max abs delta: "
        f"{provenance['max_abs_delta_random_spike_mean_vs_template']:.6g}"
    )
    print(f"Phy/Kilosort native waveform status: {phy_status['status']}")


def select_unit_row(table: pd.DataFrame, recording: str, well: str, unit_id: int) -> pd.Series:
    matches = table.loc[(table["recording"] == recording) & (table["well"] == well) & (table["unit_id"] == unit_id)]
    if matches.empty:
        raise ValueError(f"No unit row found for {recording} {well} unit {unit_id}")
    if len(matches) > 1:
        raise ValueError(f"Found multiple unit rows for {recording} {well} unit {unit_id}")
    return matches.iloc[0]


def select_manifest_row(manifest: pd.DataFrame, recording: str, well: str) -> pd.Series:
    matches = manifest.loc[(manifest["recording"] == recording) & (manifest["well"] == well)]
    if matches.empty:
        raise ValueError(f"No manifest row found for {recording} {well}")
    return matches.iloc[0]


def choose_spikes(spikes: np.ndarray, count: int, *, seed: int) -> np.ndarray:
    spikes = np.asarray(spikes, dtype=np.int64)
    if count <= 0 or len(spikes) <= count:
        return spikes
    rng = np.random.default_rng(seed)
    indices = np.sort(rng.choice(np.arange(len(spikes)), size=count, replace=False))
    return spikes[indices]


def average_snippets(
    recording,
    spike_samples: np.ndarray,
    *,
    channel_index: int,
    nbefore: int,
    nafter: int,
    return_in_uV: bool,
) -> tuple[np.ndarray, int, int]:
    waveform_sum = np.zeros(nbefore + nafter, dtype=float)
    used = 0
    skipped = 0
    num_samples = int(recording.get_num_samples(segment_index=0))
    channel_id = recording.channel_ids[channel_index]
    for sample in np.asarray(spike_samples, dtype=np.int64):
        start = int(sample) - nbefore
        end = int(sample) + nafter
        if start < 0 or end > num_samples:
            skipped += 1
            continue
        snippet = recording.get_traces(
            segment_index=0,
            start_frame=start,
            end_frame=end,
            channel_ids=[channel_id],
            return_in_uV=return_in_uV,
        )[:, 0]
        if snippet.size != nbefore + nafter:
            skipped += 1
            continue
        waveform_sum += snippet.astype(float)
        used += 1
    if used == 0:
        raise ValueError("No valid snippets were available for averaging.")
    return waveform_sum / used, used, skipped


def load_nwb_waveform(source_results_dir: Path, unit_index: int, channel_index: int) -> tuple[np.ndarray | None, dict[str, object]]:
    nwb_files = sorted((source_results_dir / "nwb").glob("*.nwb"))
    if not nwb_files:
        return None, {"status": "unavailable", "reason": "no_nwb_zarr_found"}
    nwb_path = nwb_files[0]
    try:
        root = zarr.open(str(nwb_path), mode="r")
        waveform_mean = root["units/waveform_mean"]
        waveform = np.asarray(waveform_mean[unit_index, :, channel_index], dtype=float)
        attrs = dict(waveform_mean.attrs)
    except Exception as exc:  # noqa: BLE001 - provenance should keep the exact read failure
        return None, {"status": "unavailable", "reason": f"{type(exc).__name__}: {exc}", "path": str(nwb_path)}
    return waveform, {
        "status": "available",
        "path": str(nwb_path),
        "shape": list(waveform_mean.shape),
        "attrs": attrs,
    }


def find_phy_status(source_results_dir: Path) -> dict[str, object]:
    required_names = {
        "templates.npy",
        "spike_times.npy",
        "spike_clusters.npy",
        "whitening_mat_inv.npy",
        "ops.npy",
    }
    found = []
    for path in source_results_dir.rglob("*"):
        if path.name in required_names or path.name == "params.py" or path.name == "cluster_group.tsv":
            found.append(str(path))
    has_required = required_names.issubset({Path(path).name for path in found})
    return {
        "status": "available" if has_required else "unavailable",
        "reason": "native_phy_kilosort_files_found" if has_required else "completed_step1_output_does_not_preserve_native_phy_kilosort_waveform_files",
        "candidate_files": found,
    }


def build_waveform_csv(
    *,
    time_ms: np.ndarray,
    template_waveform: np.ndarray,
    random_mean: np.ndarray,
    subset_mean: np.ndarray,
    nwb_waveform: np.ndarray | None,
    sampling_frequency_hz: float,
) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "sample_index": np.arange(template_waveform.size),
            "time_ms_from_spike": time_ms,
            "stored_templates_average_uV": template_waveform,
            "mean_extracted_analyzer_random_spikes_uV": random_mean,
            "mean_extracted_analyzer_all_spike_subsample_uV": subset_mean,
        }
    )
    if nwb_waveform is not None:
        nwb_time = (np.arange(nwb_waveform.size) - 0) * 1000.0 / sampling_frequency_hz
        out["nwb_waveform_mean_time_ms_from_nwb_sample0"] = np.nan
        out["nwb_waveform_mean_volts"] = np.nan
        n = min(len(out), len(nwb_waveform))
        out.loc[: n - 1, "nwb_waveform_mean_time_ms_from_nwb_sample0"] = nwb_time[:n]
        out.loc[: n - 1, "nwb_waveform_mean_volts"] = nwb_waveform[:n]
    return out


def plot_comparison(
    *,
    csv: pd.DataFrame,
    unit_row: pd.Series,
    output_figure: Path,
    random_count: int,
    subset_count: int,
    nwb_status: dict[str, object],
    phy_status: dict[str, object],
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    ax = axes[0, 0]
    ax.plot(csv["time_ms_from_spike"], csv["stored_templates_average_uV"], label="stored templates.average", linewidth=2.2)
    ax.plot(
        csv["time_ms_from_spike"],
        csv["mean_extracted_analyzer_random_spikes_uV"],
        "--",
        label=f"mean extracted snippets, template random spikes (n={random_count})",
        linewidth=1.8,
    )
    ax.plot(
        csv["time_ms_from_spike"],
        csv["mean_extracted_analyzer_all_spike_subsample_uV"],
        ":",
        label=f"mean extracted snippets, all-spike subsample (n={subset_count})",
        linewidth=2.0,
    )
    ax.axvline(0, color="#333333", linewidth=0.8)
    ax.set_title("Analyzer recording snippets vs stored template")
    ax.set_xlabel("Time from spike sample (ms)")
    ax.set_ylabel("Amplitude (uV)")
    ax.legend(fontsize=8)

    ax = axes[0, 1]
    ax.plot(
        csv["time_ms_from_spike"],
        csv["mean_extracted_analyzer_random_spikes_uV"] - csv["stored_templates_average_uV"],
        label="template random spikes - stored template",
        linewidth=1.8,
    )
    ax.plot(
        csv["time_ms_from_spike"],
        csv["mean_extracted_analyzer_all_spike_subsample_uV"] - csv["stored_templates_average_uV"],
        label="all-spike subsample - stored template",
        linewidth=1.8,
    )
    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.axvline(0, color="#333333", linewidth=0.8)
    ax.set_title("Difference from stored template")
    ax.set_xlabel("Time from spike sample (ms)")
    ax.set_ylabel("Delta amplitude (uV)")
    ax.legend(fontsize=8)

    ax = axes[1, 0]
    if nwb_status["status"] == "available" and "nwb_waveform_mean_volts" in csv:
        valid = csv["nwb_waveform_mean_volts"].notna()
        ax.plot(
            csv.loc[valid, "nwb_waveform_mean_time_ms_from_nwb_sample0"],
            csv.loc[valid, "nwb_waveform_mean_volts"],
            color="#0072b2",
            linewidth=2.0,
        )
        ax.set_title("NWB units/waveform_mean")
        ax.set_xlabel("Time from NWB sample 0 (ms)")
        ax.set_ylabel("Amplitude (volts)")
    else:
        ax.text(0.5, 0.5, nwb_status.get("reason", "unavailable"), ha="center", va="center", wrap=True)
        ax.set_title("NWB units/waveform_mean")
        ax.axis("off")

    ax = axes[1, 1]
    ax.text(
        0.02,
        0.98,
        "\n".join(
            [
                f"Recording: {unit_row['recording']}",
                f"Well: {unit_row['well']}",
                f"Unit: {unit_row['unit_id']}",
                f"Class: {unit_row['rs_fs_classification']}",
                f"Template reference: {unit_row['template_reference']}",
                f"Master TTP: {unit_row['trough_to_peak_duration_ms']} ms",
                f"Phy/Kilosort native waveform: {phy_status['status']}",
                str(phy_status.get("reason", "")),
            ]
        ),
        ha="left",
        va="top",
        fontsize=9,
        wrap=True,
    )
    ax.axis("off")
    fig.suptitle("Representative unit waveform representation validation", y=0.98)
    fig.tight_layout()
    fig.savefig(output_figure, dpi=220, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
