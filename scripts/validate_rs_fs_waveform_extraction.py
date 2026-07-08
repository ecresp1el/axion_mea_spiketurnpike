#!/usr/bin/env python
"""Validate RS/FS waveform extraction before interpreting waveform figures."""

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

from axion_mea.master_unit_table import CANONICAL_MASTER_UNIT_TABLE, DEFAULT_STEP2_MANIFEST, load_canonical_master_unit_table, load_step2_manifest, paths_from_manifest_row
from axion_mea.rs_fs_plots import CLASS_COLORS
from axion_mea.rs_fs_waveform_templates import (
    DEFAULT_RS_FS_WAVEFORM_DIR,
    RSFSWaveformPlotConfig,
    normalize_and_align_waveform,
    parse_template_reference,
)
from axion_mea.step3_repro import DEFAULT_STEP3_REPRO_DIR, write_command_repro


DEFAULT_AUDIT_CSV = CANONICAL_MASTER_UNIT_TABLE.with_name(
    "master_waveform_metrics_table_rs_fs_template_waveform_audit.csv"
)
DEFAULT_AUDIT_JSON = CANONICAL_MASTER_UNIT_TABLE.with_name(
    "master_waveform_metrics_table_rs_fs_template_waveform_audit.json"
)
DEFAULT_AUDIT_FIGURE = DEFAULT_RS_FS_WAVEFORM_DIR / "figure__rs_fs_template_waveform_trough_peak_audit_20.png"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit RS/FS template waveform extraction and alignment.")
    parser.add_argument("--input-csv", type=Path, default=CANONICAL_MASTER_UNIT_TABLE)
    parser.add_argument("--manifest-csv", type=Path, default=DEFAULT_STEP2_MANIFEST)
    parser.add_argument("--audit-csv", type=Path, default=DEFAULT_AUDIT_CSV)
    parser.add_argument("--audit-json", type=Path, default=DEFAULT_AUDIT_JSON)
    parser.add_argument("--audit-figure", type=Path, default=DEFAULT_AUDIT_FIGURE)
    parser.add_argument("--sampling-frequency-hz", type=float, default=12500.0)
    parser.add_argument("--time-min-ms", type=float, default=-1.2)
    parser.add_argument("--time-max-ms", type=float, default=4.2)
    parser.add_argument("--baseline-samples", type=int, default=5)
    parser.add_argument("--random-seed", type=int, default=20260708)
    parser.add_argument("--n-random-waveforms", type=int, default=20)
    parser.add_argument("--repro-dir", type=Path, default=DEFAULT_STEP3_REPRO_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = RSFSWaveformPlotConfig(
        sampling_frequency_hz=args.sampling_frequency_hz,
        time_min_ms=args.time_min_ms,
        time_max_ms=args.time_max_ms,
        baseline_samples=args.baseline_samples,
        random_seed=args.random_seed,
    )
    table = load_canonical_master_unit_table(args.input_csv)
    manifest = load_step2_manifest(args.manifest_csv)
    audit = build_waveform_audit_table(table, manifest, config)

    args.audit_csv.parent.mkdir(parents=True, exist_ok=True)
    args.audit_figure.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(args.audit_csv, index=False)
    plot_random_waveform_audit(audit, args.audit_figure, config, args.n_random_waveforms, args.random_seed)
    summary = build_audit_summary(audit, config)
    command_repro = write_command_repro(
        repro_dir=args.repro_dir,
        stem="validate_rs_fs_waveform_extraction",
        parsed_args={key: str(value) for key, value in vars(args).items()},
    )
    summary["command_repro"] = command_repro
    args.audit_json.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Wrote waveform audit table: {args.audit_csv}")
    print(f"Wrote waveform audit JSON: {args.audit_json}")
    print(f"Wrote 20-waveform audit figure: {args.audit_figure}")
    print(json.dumps(summary["headline"], indent=2))


def build_waveform_audit_table(
    table: pd.DataFrame,
    manifest: pd.DataFrame,
    config: RSFSWaveformPlotConfig,
) -> pd.DataFrame:
    try:
        import spikeinterface as si
    except ImportError as exc:
        raise ImportError("SpikeInterface is required to validate Step 1 templates.") from exc

    source_lookup = {(row["recording"], row["well"]): row for _, row in manifest.iterrows()}
    target = table.loc[table["rs_fs_classification"].isin(config.classes)].copy()
    rows = []
    grouped = list(target.groupby(["recording", "well"], sort=False))
    for well_number, ((recording, well), well_units) in enumerate(grouped, start=1):
        print(f"[{well_number}/{len(grouped)}] AUDIT {recording} {well} units={len(well_units)}", flush=True)
        manifest_row = source_lookup[(recording, well)]
        analyzer_path = paths_from_manifest_row(manifest_row)["analyzer_zarr"]
        analyzer = si.load(analyzer_path)
        templates = np.asarray(analyzer.get_extension("templates").get_data(operator="average"))
        analyzer_sampling_frequency = (
            float(analyzer.recording.get_sampling_frequency()) if analyzer.recording is not None else np.nan
        )
        template_sample_count = int(templates.shape[1])
        template_channel_count = int(templates.shape[2])

        for _, unit_row in well_units.iterrows():
            unit_index, channel_index = parse_template_reference(str(unit_row["template_reference"]))
            raw = templates[unit_index, :, channel_index].astype(float)
            baseline_n = min(max(config.baseline_samples, 1), raw.size)
            centered = raw - float(np.nanmedian(raw[:baseline_n]))
            trough_index = int(np.nanargmin(centered))
            peak_index = trough_index + int(np.nanargmax(centered[trough_index:]))
            trough_value = float(centered[trough_index])
            peak_value = float(centered[peak_index])
            trough_to_peak_ms = (peak_index - trough_index) * config.sample_dt_ms
            pre_support_ms = trough_index * config.sample_dt_ms
            post_support_ms = (template_sample_count - 1 - trough_index) * config.sample_dt_ms
            aligned = normalize_and_align_waveform(raw, config=config)
            rows.append(
                {
                    "recording": recording,
                    "well": well,
                    "unit_id": unit_row["unit_id"],
                    "rs_fs_classification": unit_row["rs_fs_classification"],
                    "template_reference": unit_row["template_reference"],
                    "analyzer_sampling_frequency_hz": analyzer_sampling_frequency,
                    "configured_sampling_frequency_hz": config.sampling_frequency_hz,
                    "template_sample_count": template_sample_count,
                    "template_channel_count": template_channel_count,
                    "unit_index": unit_index,
                    "channel_index": channel_index,
                    "trough_index": trough_index,
                    "peak_index": peak_index,
                    "trough_time_aligned_ms": 0.0,
                    "peak_time_aligned_ms": trough_to_peak_ms,
                    "trough_to_peak_duration_ms_recomputed": trough_to_peak_ms,
                    "trough_value_baseline_subtracted": trough_value,
                    "peak_value_baseline_subtracted": peak_value,
                    "pre_trough_support_ms": pre_support_ms,
                    "post_trough_support_ms": post_support_ms,
                    "plot_window_min_ms": config.time_min_ms,
                    "plot_window_max_ms": config.time_max_ms,
                    "valid_points_in_plot_window": int(np.isfinite(aligned).sum()),
                    "raw_waveform_json": json.dumps(raw.tolist()),
                    "centered_waveform_json": json.dumps(centered.tolist()),
                }
            )
    return pd.DataFrame(rows)


def build_audit_summary(audit: pd.DataFrame, config: RSFSWaveformPlotConfig) -> dict:
    grouped = audit.groupby("rs_fs_classification")
    support_summary = grouped.agg(
        unit_count=("unit_id", "size"),
        median_trough_index=("trough_index", "median"),
        median_peak_index=("peak_index", "median"),
        median_pre_trough_support_ms=("pre_trough_support_ms", "median"),
        median_post_trough_support_ms=("post_trough_support_ms", "median"),
        min_post_trough_support_ms=("post_trough_support_ms", "min"),
        median_recomputed_ttp_ms=("trough_to_peak_duration_ms_recomputed", "median"),
        min_valid_points_in_plot_window=("valid_points_in_plot_window", "min"),
        median_valid_points_in_plot_window=("valid_points_in_plot_window", "median"),
    ).reset_index()
    sample_counts = sorted(int(v) for v in audit["template_sample_count"].unique())
    sampling_rates = sorted(float(v) for v in audit["analyzer_sampling_frequency_hz"].dropna().unique())
    time_grid = config.time_grid_ms()
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "headline": {
            "unit_count": int(len(audit)),
            "classes": audit["rs_fs_classification"].value_counts().to_dict(),
            "sampling_rates_hz_observed": sampling_rates,
            "template_sample_counts_observed": sample_counts,
            "configured_sample_dt_ms": config.sample_dt_ms,
            "raw_template_duration_ms": {
                str(sample_count): (sample_count - 1) * config.sample_dt_ms for sample_count in sample_counts
            },
            "plot_time_grid_start_ms": float(time_grid[0]),
            "plot_time_grid_end_ms": float(time_grid[-1]),
            "plot_time_grid_points": int(len(time_grid)),
        },
        "support_summary_by_class": support_summary.to_dict(orient="records"),
        "interpretation_notes": [
            "The x-axis used for aligned waveforms is (sample_index - detected_trough_index) * 1000 / sampling_frequency_hz.",
            "The trough is therefore exactly 0 ms by construction for each aligned waveform.",
            "The current plot window extends beyond the valid post-trough template support for many units, so late time points are averages over a changing subset of units.",
            "A late rising class mean can occur when the right edge contains only units with long post-trough support rather than the full class.",
        ],
    }


def plot_random_waveform_audit(
    audit: pd.DataFrame,
    output_path: Path,
    config: RSFSWaveformPlotConfig,
    n_waveforms: int,
    random_seed: int,
) -> None:
    rng = np.random.default_rng(random_seed)
    sample = audit.sample(n=min(n_waveforms, len(audit)), random_state=int(rng.integers(0, 2**31 - 1)))
    ncols = 5
    nrows = int(np.ceil(len(sample) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(15, max(3.0, nrows * 2.4)), sharex=True, sharey=True)
    axes = np.asarray(axes).reshape(nrows, ncols)
    for ax in axes.flat:
        ax.axis("off")
    for ax, (_, row) in zip(axes.flat, sample.iterrows(), strict=False):
        ax.axis("on")
        raw = np.asarray(json.loads(row["centered_waveform_json"]), dtype=float)
        trough_index = int(row["trough_index"])
        peak_index = int(row["peak_index"])
        trough_depth = abs(raw[trough_index])
        normalized = raw / trough_depth if trough_depth > 0 else raw
        time_ms = (np.arange(len(normalized)) - trough_index) * config.sample_dt_ms
        color = CLASS_COLORS.get(str(row["rs_fs_classification"]), "#444444")
        ax.plot(time_ms, normalized, color=color, linewidth=1.4)
        ax.scatter([0.0], [normalized[trough_index]], color="#111111", s=22, zorder=4)
        ax.scatter([time_ms[peak_index]], [normalized[peak_index]], color="#e69f00", s=22, zorder=4)
        ax.axvline(0.0, color="#111111", linestyle="--", linewidth=0.9)
        ax.axhline(0.0, color="#d0d0d0", linewidth=0.7)
        ax.set_title(
            f"{row['rs_fs_classification']} {row['well']} u{row['unit_id']}\n"
            f"TTP={row['trough_to_peak_duration_ms_recomputed']:.2f} ms",
            fontsize=8,
        )
        ax.set_xlim(config.time_min_ms, config.time_max_ms)
    fig.supxlabel("Time from detected trough (ms)")
    fig.supylabel("Trough-normalized amplitude")
    fig.suptitle("Random template waveform audit: black = trough at 0 ms, orange = rebound peak", y=0.995)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
