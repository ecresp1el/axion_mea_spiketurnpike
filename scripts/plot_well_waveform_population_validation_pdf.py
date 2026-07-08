#!/usr/bin/env python
"""Write one waveform-population review page per completed well."""

from __future__ import annotations

import argparse
import json
import math
import sys
import textwrap
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
from matplotlib.backends.backend_pdf import PdfPages

from axion_mea.master_unit_table import (
    CANONICAL_MASTER_UNIT_TABLE,
    DEFAULT_STEP2_MANIFEST,
    load_canonical_master_unit_table,
    load_step2_manifest,
    paths_from_manifest_row,
)
from axion_mea.rs_fs_waveform_templates import parse_template_reference
from axion_mea.step3_repro import DEFAULT_STEP3_REPRO_DIR, write_command_repro


DEFAULT_OUTPUT_DIR = CANONICAL_MASTER_UNIT_TABLE.parent / "figures" / "waveform_population"
DEFAULT_OUTPUT_PDF = DEFAULT_OUTPUT_DIR / "figure__well_waveform_unit_grid_review.pdf"
DEFAULT_SUMMARY_CSV = CANONICAL_MASTER_UNIT_TABLE.with_name("well_waveform_unit_grid_review_summary.csv")
DEFAULT_PROVENANCE_JSON = CANONICAL_MASTER_UNIT_TABLE.with_name("well_waveform_unit_grid_review_provenance.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot normalized dominant-channel template waveforms as one grid page per well.")
    parser.add_argument("--input-csv", type=Path, default=CANONICAL_MASTER_UNIT_TABLE)
    parser.add_argument("--manifest-csv", type=Path, default=DEFAULT_STEP2_MANIFEST)
    parser.add_argument("--output-pdf", type=Path, default=DEFAULT_OUTPUT_PDF)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    parser.add_argument("--provenance-json", type=Path, default=DEFAULT_PROVENANCE_JSON)
    parser.add_argument("--sampling-frequency-hz", type=float, default=12500.0)
    parser.add_argument("--baseline-samples", type=int, default=5)
    parser.add_argument("--time-min-ms", type=float, default=-2.0)
    parser.add_argument("--time-max-ms", type=float, default=3.0)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--repro-dir", type=Path, default=DEFAULT_STEP3_REPRO_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    table = load_canonical_master_unit_table(args.input_csv)
    manifest = load_step2_manifest(args.manifest_csv)
    source_lookup = {(row["recording"], row["well"]): row for _, row in manifest.iterrows()}
    grouped = list(table.groupby(["recording", "well"], sort=False))

    args.output_pdf.parent.mkdir(parents=True, exist_ok=True)
    args.summary_csv.parent.mkdir(parents=True, exist_ok=True)
    args.provenance_json.parent.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    with PdfPages(args.output_pdf) as pdf:
        for page_index, ((recording, well), well_units) in enumerate(grouped, start=1):
            if args.progress:
                print(f"[{page_index}/{len(grouped)}] {recording} {well} units={len(well_units)}", flush=True)
            manifest_row = source_lookup.get((recording, well))
            if manifest_row is None:
                raise ValueError(f"No manifest row for {recording} {well}")
            analyzer_path = paths_from_manifest_row(manifest_row)["analyzer_zarr"]
            templates, analyzer_sampling_frequency, filter_metadata = load_templates_sampling_and_filter_metadata(analyzer_path)
            sampling_frequency_hz = analyzer_sampling_frequency or args.sampling_frequency_hz
            waveforms = build_normalized_waveforms(
                well_units=well_units,
                templates=templates,
                sampling_frequency_hz=sampling_frequency_hz,
                baseline_samples=args.baseline_samples,
                time_min_ms=args.time_min_ms,
                time_max_ms=args.time_max_ms,
            )
            page_summary = summarize_well(
                recording=recording,
                well=well,
                well_units=well_units,
                waveforms=waveforms,
                page_index=page_index,
                page_count=len(grouped),
                filter_metadata=filter_metadata,
            )
            summary_rows.append(page_summary)
            fig = plot_well_page(page_summary, waveforms)
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(args.summary_csv, index=False)
    command_repro = write_command_repro(
        repro_dir=args.repro_dir,
        stem="plot_well_waveform_population_validation_pdf",
        parsed_args={key: str(value) for key, value in vars(args).items()},
    )
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "question": "Do well-level grids of Kilosort-good unit mean/template waveforms look like reasonable extracellular spike waveforms?",
        "input_csv": str(args.input_csv),
        "manifest_csv": str(args.manifest_csv),
        "output_pdf": str(args.output_pdf),
        "summary_csv": str(args.summary_csv),
        "well_count": int(len(summary)),
        "unit_count": int(len(table)),
        "normalization": (
            "For each Kilosort-good unit, use the dominant-channel Step 1 templates.average waveform, "
            "subtract the median of the first baseline_samples, divide by absolute trough depth, "
            "and align the detected trough to 0 ms."
        ),
        "layout": (
            "Each PDF page is one recording/well. Each subplot is one Kilosort-good unit's normalized "
            "dominant-channel templates.average waveform. The grid dimensions are computed from the number of units."
        ),
        "filtering_metadata": (
            "Filtering/preprocessing fields are copied from the Step 1 SortingAnalyzer sorting provenance and "
            "recording object. The analyzer recording is the object from which templates.average was computed."
        ),
        "exclusions": (
            "No units are classified, flagged, interpreted, or excluded beyond the canonical Kilosort-good master table."
        ),
        "filtering_metadata_unique_rows": summary[
            [
                "recording_is_filtered",
                "recording_class",
                "recording_dtype",
                "skip_kilosort_preprocessing",
                "kilosort_highpass_cutoff",
                "kilosort_do_CAR",
                "kilosort_do_correction",
                "kilosort_whitening_range",
            ]
        ].drop_duplicates().to_dict(orient="records"),
        "command_repro": command_repro,
    }
    args.provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Wrote waveform population PDF: {args.output_pdf}")
    print(f"Wrote well summary CSV: {args.summary_csv}")
    print(f"Wrote provenance JSON: {args.provenance_json}")
    print(f"Pages: {len(summary)}")


def load_templates_sampling_and_filter_metadata(analyzer_path: Path) -> tuple[np.ndarray, float | None, dict[str, object]]:
    try:
        import spikeinterface as si
    except ImportError as exc:
        raise ImportError("SpikeInterface is required to reopen Step 1 template analyzers.") from exc
    analyzer = si.load(analyzer_path)
    templates = np.asarray(analyzer.get_extension("templates").get_data(operator="average"), dtype=float)
    sampling_frequency = None
    recording_class = ""
    recording_dtype = ""
    recording_is_filtered = None
    if analyzer.recording is not None:
        sampling_frequency = float(analyzer.recording.get_sampling_frequency())
        recording_class = f"{type(analyzer.recording).__module__}.{type(analyzer.recording).__name__}"
        recording_dtype = str(analyzer.recording.get_dtype())
        recording_is_filtered = getattr(analyzer.recording, "_annotations", {}).get("is_filtered")
    provenance = json.loads((analyzer_path / "sorting" / ".zattrs").read_text(encoding="utf-8"))
    sorting_info = provenance.get("annotations", {}).get("__sorting_info__", {})
    sorter_params = sorting_info.get("params", {}).get("sorter_params", {})
    recording_info = sorting_info.get("recording", {})
    recording_annotations = recording_info.get("annotations", {})
    if recording_is_filtered is None:
        recording_is_filtered = recording_annotations.get("is_filtered")
    filter_metadata = {
        "recording_is_filtered": recording_is_filtered,
        "recording_class": recording_class or recording_info.get("class", ""),
        "recording_dtype": recording_dtype,
        "skip_kilosort_preprocessing": sorter_params.get("skip_kilosort_preprocessing"),
        "kilosort_highpass_cutoff": sorter_params.get("highpass_cutoff"),
        "kilosort_do_CAR": sorter_params.get("do_CAR"),
        "kilosort_do_correction": sorter_params.get("do_correction"),
        "kilosort_whitening_range": sorter_params.get("whitening_range"),
        "kilosort_save_preprocessed_copy": sorter_params.get("save_preprocessed_copy"),
        "kilosort_invert_sign": sorter_params.get("invert_sign"),
        "kilosort_scale": sorter_params.get("scale"),
        "kilosort_shift": sorter_params.get("shift"),
    }
    return templates, sampling_frequency, filter_metadata


def build_normalized_waveforms(
    *,
    well_units: pd.DataFrame,
    templates: np.ndarray,
    sampling_frequency_hz: float,
    baseline_samples: int,
    time_min_ms: float,
    time_max_ms: float,
) -> pd.DataFrame:
    sample_dt_ms = 1000.0 / sampling_frequency_hz
    rows = []
    for _, unit_row in well_units.sort_values("unit_id").iterrows():
        unit_index, channel_index = parse_template_reference(str(unit_row["template_reference"]))
        waveform = templates[unit_index, :, channel_index].astype(float)
        baseline_n = min(max(int(baseline_samples), 1), waveform.size)
        centered = waveform - float(np.nanmedian(waveform[:baseline_n]))
        trough_index = int(np.nanargmin(centered))
        trough_depth = abs(float(centered[trough_index]))
        if not np.isfinite(trough_depth) or trough_depth == 0:
            normalized = np.full_like(centered, np.nan, dtype=float)
        else:
            normalized = centered / trough_depth
        time_ms = (np.arange(waveform.size) - trough_index) * sample_dt_ms
        keep = (time_ms >= time_min_ms) & (time_ms <= time_max_ms)
        rows.append(
            pd.DataFrame(
                {
                    "unit_id": unit_row["unit_id"],
                    "trough_to_peak_duration_ms": unit_row["trough_to_peak_duration_ms"],
                    "time_ms": time_ms[keep],
                    "normalized_amplitude": normalized[keep],
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def summarize_well(
    *,
    recording: str,
    well: str,
    well_units: pd.DataFrame,
    waveforms: pd.DataFrame,
    page_index: int,
    page_count: int,
    filter_metadata: dict[str, object],
) -> dict[str, object]:
    ttp = well_units["trough_to_peak_duration_ms"].dropna().astype(float)
    out = {
        "page_index": page_index,
        "page_count": page_count,
        "recording": recording,
        "well": well,
        "kilosort_good_unit_count": int(len(well_units)),
        "mean_trough_to_peak_duration_ms": float(ttp.mean()) if not ttp.empty else np.nan,
        "median_trough_to_peak_duration_ms": float(ttp.median()) if not ttp.empty else np.nan,
    }
    out.update(filter_metadata)
    return out


def plot_well_page(page_summary: dict[str, object], waveforms: pd.DataFrame) -> plt.Figure:
    unit_ids = list(waveforms["unit_id"].drop_duplicates())
    unit_count = max(len(unit_ids), 1)
    ncols = max(1, math.ceil(math.sqrt(unit_count * 1.45)))
    nrows = math.ceil(unit_count / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(11, 8.5), sharex=True, sharey=True)
    axes = np.asarray(axes).reshape(nrows, ncols)
    for ax in axes.flat:
        ax.axis("off")

    for ax, unit_id in zip(axes.flat, unit_ids, strict=False):
        unit_waveform = waveforms.loc[waveforms["unit_id"] == unit_id]
        ax.axis("on")
        ax.plot(unit_waveform["time_ms"], unit_waveform["normalized_amplitude"], color="#1f77b4", linewidth=1.15)
        ax.axvline(0.0, color="#111111", linestyle="--", linewidth=0.65)
        ax.axhline(0.0, color="#d0d0d0", linewidth=0.55)
        ttp = unit_waveform["trough_to_peak_duration_ms"].dropna()
        ttp_text = "nan" if ttp.empty else f"{float(ttp.iloc[0]):.2f}"
        ax.set_title(f"u{unit_id} | TTP {ttp_text} ms", fontsize=5.8, pad=1.5)
        ax.set_xlim(float(waveforms["time_ms"].min()), float(waveforms["time_ms"].max()))
        ax.set_ylim(-1.25, 2.35)
        ax.tick_params(labelsize=5, length=2, pad=1)
        ax.grid(True, color="#eeeeee", linewidth=0.45)

    recording = str(page_summary["recording"])
    title = "\n".join(textwrap.wrap(recording, width=96))
    stats_line = (
        f"Well {page_summary['well']} | "
        f"Kilosort good units: {page_summary['kilosort_good_unit_count']} | "
        f"Mean TTP: {page_summary['mean_trough_to_peak_duration_ms']:.3f} ms | "
        f"Median TTP: {page_summary['median_trough_to_peak_duration_ms']:.3f} ms"
    )
    filter_line = (
        f"Filter metadata: recording is_filtered={page_summary.get('recording_is_filtered')} | "
        f"skip KS preprocessing={page_summary.get('skip_kilosort_preprocessing')} | "
        f"KS highpass_cutoff={page_summary.get('kilosort_highpass_cutoff')} Hz | "
        f"do_CAR={page_summary.get('kilosort_do_CAR')} | "
        f"do_correction={page_summary.get('kilosort_do_correction')}"
    )
    fig.suptitle(f"{title}\n{stats_line}\n{filter_line}", y=0.985, fontsize=8.5)
    fig.supxlabel("Time from detected trough (ms)", fontsize=8, y=0.025)
    fig.supylabel("Normalized amplitude", fontsize=8, x=0.015)
    fig.text(
        0.99,
        0.015,
        f"Page {page_summary['page_index']} of {page_summary['page_count']}",
        ha="right",
        va="bottom",
        fontsize=7,
        color="#555555",
    )
    top = max(0.74, 0.92 - max(0, len(title.splitlines()) - 1) * 0.025)
    fig.tight_layout(rect=(0.035, 0.04, 0.985, top), h_pad=0.45, w_pad=0.35)
    return fig


def summarize_timepoints(waveforms: pd.DataFrame) -> pd.DataFrame:
    def sem(values: pd.Series) -> float:
        clean = values.dropna().to_numpy(dtype=float)
        if clean.size <= 1:
            return np.nan
        return float(np.nanstd(clean, ddof=1) / np.sqrt(clean.size))

    return (
        waveforms.groupby("time_ms", dropna=False)
        .agg(
            mean_normalized_amplitude=("normalized_amplitude", "mean"),
            sem_normalized_amplitude=("normalized_amplitude", sem),
            waveform_count=("normalized_amplitude", "count"),
        )
        .reset_index()
        .sort_values("time_ms")
    )


if __name__ == "__main__":
    main()
