#!/usr/bin/env python
"""Plot every Kilosort-good unit from one well on its metric dominant channel."""

from __future__ import annotations

import argparse
import json
import math
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

from axion_mea.master_unit_table import (
    CANONICAL_MASTER_UNIT_TABLE,
    DEFAULT_STEP2_MANIFEST,
    load_canonical_master_unit_table,
    load_step2_manifest,
    paths_from_manifest_row,
)
from axion_mea.rs_fs_plots import CLASS_COLORS
from axion_mea.rs_fs_waveform_templates import parse_template_reference
from axion_mea.step3_repro import DEFAULT_STEP3_REPRO_DIR, write_command_repro


DEFAULT_RECORDING = "sixwell_manual_primary_5_28_26_pvreporter_134-0150_pv_reporter_cl23_dorsal_and_ventral_exp17_2(000)"
DEFAULT_WELL = "B3"
DEFAULT_OUTPUT_DIR = CANONICAL_MASTER_UNIT_TABLE.parent / "figures" / "rs_fs_waveforms"
DEFAULT_FIGURE = DEFAULT_OUTPUT_DIR / "figure__representative_well_B3_dominant_templates_trough_peak.png"
DEFAULT_AUDIT_CSV = CANONICAL_MASTER_UNIT_TABLE.with_name(
    "representative_well_B3_dominant_template_audit.csv"
)
DEFAULT_PROVENANCE_JSON = CANONICAL_MASTER_UNIT_TABLE.with_name(
    "representative_well_B3_dominant_template_audit_provenance.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that plotted templates use the same dominant channel as master metrics."
    )
    parser.add_argument("--input-csv", type=Path, default=CANONICAL_MASTER_UNIT_TABLE)
    parser.add_argument("--manifest-csv", type=Path, default=DEFAULT_STEP2_MANIFEST)
    parser.add_argument("--recording", default=DEFAULT_RECORDING)
    parser.add_argument("--well", default=DEFAULT_WELL)
    parser.add_argument("--output-figure", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument("--audit-csv", type=Path, default=DEFAULT_AUDIT_CSV)
    parser.add_argument("--provenance-json", type=Path, default=DEFAULT_PROVENANCE_JSON)
    parser.add_argument("--repro-dir", type=Path, default=DEFAULT_STEP3_REPRO_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    table = load_canonical_master_unit_table(args.input_csv)
    manifest = load_step2_manifest(args.manifest_csv)
    well_rows = table.loc[(table["recording"] == args.recording) & (table["well"] == args.well)].copy()
    if well_rows.empty:
        raise ValueError(f"No master-table rows found for {args.recording} {args.well}")
    manifest_match = manifest.loc[(manifest["recording"] == args.recording) & (manifest["well"] == args.well)]
    if manifest_match.empty:
        raise ValueError(f"No manifest row found for {args.recording} {args.well}")

    analyzer_path = paths_from_manifest_row(manifest_match.iloc[0])["analyzer_zarr"]
    templates, sampling_frequency_hz = load_templates_and_sampling_frequency(analyzer_path)
    audit = build_representative_well_audit(well_rows, templates, sampling_frequency_hz)
    mismatches = audit.loc[~audit["dominant_channel_matches_template_reference"]]
    if not mismatches.empty:
        raise RuntimeError(
            "Dominant channel mismatch between master table and fresh template calculation:\n"
            + mismatches[["unit_id", "template_channel_index", "recomputed_dominant_channel_index"]].to_string(index=False)
        )

    args.output_figure.parent.mkdir(parents=True, exist_ok=True)
    args.audit_csv.parent.mkdir(parents=True, exist_ok=True)
    args.provenance_json.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(args.audit_csv, index=False)
    plot_every_unit(audit, args.output_figure)
    command_repro = write_command_repro(
        repro_dir=args.repro_dir,
        stem="plot_representative_well_dominant_templates",
        parsed_args={key: str(value) for key, value in vars(args).items()},
    )
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "recording": args.recording,
        "well": args.well,
        "input_csv": str(args.input_csv),
        "manifest_csv": str(args.manifest_csv),
        "analyzer_zarr": str(analyzer_path),
        "output_figure": str(args.output_figure),
        "audit_csv": str(args.audit_csv),
        "unit_count": int(len(audit)),
        "sampling_frequency_hz": sampling_frequency_hz,
        "sample_dt_ms": 1000.0 / sampling_frequency_hz,
        "template_sample_count": int(templates.shape[1]),
        "template_channel_count": int(templates.shape[2]),
        "dominant_channel_matches_all_units": bool(audit["dominant_channel_matches_template_reference"].all()),
        "class_counts": audit["rs_fs_classification"].value_counts(dropna=False).to_dict(),
        "command_repro": command_repro,
    }
    args.provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Wrote representative well template figure: {args.output_figure}")
    print(f"Wrote representative well audit CSV: {args.audit_csv}")
    print(f"Wrote representative well provenance: {args.provenance_json}")
    print(f"Dominant channel matched for all {len(audit)} units.")


def load_templates_and_sampling_frequency(analyzer_path: Path) -> tuple[np.ndarray, float]:
    try:
        import spikeinterface as si
    except ImportError as exc:
        raise ImportError("SpikeInterface is required to load analyzer templates.") from exc
    analyzer = si.load(analyzer_path)
    templates = np.asarray(analyzer.get_extension("templates").get_data(operator="average"))
    if analyzer.recording is None:
        raise ValueError(f"Analyzer recording is missing: {analyzer_path}")
    return templates, float(analyzer.recording.get_sampling_frequency())


def build_representative_well_audit(
    well_rows: pd.DataFrame,
    templates: np.ndarray,
    sampling_frequency_hz: float,
) -> pd.DataFrame:
    rows = []
    sample_dt_ms = 1000.0 / sampling_frequency_hz
    for _, unit_row in well_rows.sort_values("unit_id").iterrows():
        unit_index, channel_index = parse_template_reference(str(unit_row["template_reference"]))
        template = templates[unit_index].astype(float)
        channel_amplitudes = np.nanmax(template, axis=0) - np.nanmin(template, axis=0)
        recomputed_channel_index = int(np.nanargmax(channel_amplitudes))
        waveform = template[:, channel_index]
        trough_index = int(np.nanargmin(waveform))
        peak_index = trough_index + int(np.nanargmax(waveform[trough_index:]))
        rows.append(
            {
                "recording": unit_row["recording"],
                "well": unit_row["well"],
                "unit_id": unit_row["unit_id"],
                "rs_fs_classification": unit_row["rs_fs_classification"],
                "template_reference": unit_row["template_reference"],
                "template_unit_index": unit_index,
                "template_channel_index": channel_index,
                "recomputed_dominant_channel_index": recomputed_channel_index,
                "dominant_channel_matches_template_reference": channel_index == recomputed_channel_index,
                "trough_index": trough_index,
                "peak_index": peak_index,
                "sample_dt_ms": sample_dt_ms,
                "trough_time_ms_from_template_start": trough_index * sample_dt_ms,
                "peak_time_ms_from_template_start": peak_index * sample_dt_ms,
                "trough_to_peak_duration_ms_recomputed": (peak_index - trough_index) * sample_dt_ms,
                "master_trough_to_peak_duration_ms": unit_row["trough_to_peak_duration_ms"],
                "waveform_json": json.dumps(waveform.tolist()),
            }
        )
    return pd.DataFrame(rows)


def plot_every_unit(audit: pd.DataFrame, output_figure: Path) -> None:
    unit_count = len(audit)
    ncols = 5
    nrows = math.ceil(unit_count / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(16, max(3.0, nrows * 2.2)), sharex=True)
    axes = np.asarray(axes).reshape(nrows, ncols)
    for ax in axes.flat:
        ax.axis("off")

    for ax, (_, row) in zip(axes.flat, audit.iterrows(), strict=False):
        ax.axis("on")
        waveform = np.asarray(json.loads(row["waveform_json"]), dtype=float)
        time_ms = np.arange(waveform.size) * float(row["sample_dt_ms"])
        centered = waveform - np.nanmedian(waveform[: min(5, waveform.size)])
        color = CLASS_COLORS.get(str(row["rs_fs_classification"]), "#444444")
        ax.plot(time_ms, centered, color=color, linewidth=1.2)
        trough_time = row["trough_time_ms_from_template_start"]
        peak_time = row["peak_time_ms_from_template_start"]
        ax.scatter([trough_time], [centered[int(row["trough_index"])]], color="#111111", s=18, zorder=4)
        ax.scatter([peak_time], [centered[int(row["peak_index"])]], color="#e69f00", s=18, zorder=4)
        ax.axhline(0, color="#d0d0d0", linewidth=0.6)
        ax.set_title(
            f"u{row['unit_id']} ch{row['template_channel_index']} {row['rs_fs_classification']}\n"
            f"TTP={row['trough_to_peak_duration_ms_recomputed']:.2f} ms",
            fontsize=7,
        )
    fig.supxlabel("Template time from sample 0 (ms)")
    fig.supylabel("Baseline-subtracted template amplitude")
    fig.suptitle(
        "Representative well B3: every Kilosort-good unit on metric dominant channel\n"
        "black = detected trough, orange = detected rebound peak",
        y=0.995,
    )
    fig.tight_layout()
    fig.savefig(output_figure, dpi=220, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
