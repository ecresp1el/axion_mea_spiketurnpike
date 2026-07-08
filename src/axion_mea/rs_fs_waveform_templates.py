"""RS/FS waveform panels from Step 1 template waveforms."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .master_unit_table import (
    CANONICAL_MASTER_UNIT_TABLE,
    DEFAULT_STEP2_MANIFEST,
    load_canonical_master_unit_table,
    load_step2_manifest,
    paths_from_manifest_row,
)
from .rs_fs_plots import CLASS_COLORS


DEFAULT_RS_FS_WAVEFORM_DIR = CANONICAL_MASTER_UNIT_TABLE.parent / "figures" / "rs_fs_waveforms"
DEFAULT_RS_FS_WAVEFORM_FIGURE = DEFAULT_RS_FS_WAVEFORM_DIR / "figure__rs_fs_template_waveform_summary.png"
DEFAULT_RS_FS_WAVEFORM_MEAN_CSV = CANONICAL_MASTER_UNIT_TABLE.with_name(
    "master_waveform_metrics_table_rs_fs_template_waveform_mean_sem.csv"
)
DEFAULT_RS_FS_WAVEFORM_PROVENANCE_JSON = CANONICAL_MASTER_UNIT_TABLE.with_name(
    "master_waveform_metrics_table_rs_fs_template_waveform_provenance.json"
)

TEMPLATE_REFERENCE_PATTERN = re.compile(r"unit_index=(?P<unit_index>\d+),channel_index=(?P<channel_index>\d+)")


@dataclass(frozen=True)
class RSFSWaveformPlotConfig:
    """Settings for class-level waveform panels."""

    sampling_frequency_hz: float = 12500.0
    time_min_ms: float = -1.2
    time_max_ms: float = 4.2
    baseline_samples: int = 5
    max_overlay_per_class: int = 180
    random_seed: int = 20260708
    classes: tuple[str, str] = ("FS_like", "RS_like")

    @property
    def sample_dt_ms(self) -> float:
        return 1000.0 / self.sampling_frequency_hz

    def time_grid_ms(self) -> np.ndarray:
        return np.arange(self.time_min_ms, self.time_max_ms + self.sample_dt_ms / 2, self.sample_dt_ms)


def load_rs_fs_template_waveforms(
    table: pd.DataFrame | None = None,
    manifest: pd.DataFrame | None = None,
    input_csv: str | Path = CANONICAL_MASTER_UNIT_TABLE,
    manifest_csv: str | Path = DEFAULT_STEP2_MANIFEST,
    config: RSFSWaveformPlotConfig | None = None,
    progress: bool = False,
) -> pd.DataFrame:
    """Load normalized, trough-aligned template waveforms for FS/RS units."""

    config = config or RSFSWaveformPlotConfig()
    table = load_canonical_master_unit_table(input_csv) if table is None else table.copy()
    manifest = load_step2_manifest(manifest_csv) if manifest is None else manifest.copy()
    source_lookup = {
        (row["recording"], row["well"]): row
        for _, row in manifest.iterrows()
    }
    target = table.loc[table["rs_fs_classification"].isin(config.classes)].copy()
    if target.empty:
        raise ValueError(f"No units found for classes: {config.classes}")

    rows: list[pd.DataFrame] = []
    grouped = list(target.groupby(["recording", "well"], sort=False))
    for well_number, ((recording, well), well_units) in enumerate(grouped, start=1):
        if progress:
            print(
                f"[{well_number}/{len(grouped)}] START {recording} {well} "
                f"units={len(well_units)}",
                flush=True,
            )
        manifest_row = source_lookup.get((recording, well))
        if manifest_row is None:
            raise ValueError(f"No manifest row for {recording} {well}")
        analyzer_path = paths_from_manifest_row(manifest_row)["analyzer_zarr"]
        templates = _load_average_templates(analyzer_path)

        for _, unit_row in well_units.iterrows():
            unit_index, channel_index = parse_template_reference(str(unit_row["template_reference"]))
            waveform = templates[unit_index, :, channel_index].astype(float)
            aligned = normalize_and_align_waveform(waveform, config=config)
            rows.append(
                pd.DataFrame(
                    {
                        "recording": recording,
                        "well": well,
                        "unit_id": unit_row["unit_id"],
                        "rs_fs_classification": unit_row["rs_fs_classification"],
                        "time_ms": config.time_grid_ms(),
                        "normalized_amplitude": aligned,
                    }
                )
            )
        if progress:
            print(f"[{well_number}/{len(grouped)}] DONE {recording} {well}", flush=True)
    return pd.concat(rows, ignore_index=True)


def parse_template_reference(reference: str) -> tuple[int, int]:
    """Parse unit/channel indices from a template reference string."""

    match = TEMPLATE_REFERENCE_PATTERN.search(reference)
    if match is None:
        raise ValueError(f"Could not parse template reference: {reference}")
    return int(match.group("unit_index")), int(match.group("channel_index"))


def normalize_and_align_waveform(waveform: np.ndarray, config: RSFSWaveformPlotConfig) -> np.ndarray:
    """Baseline-subtract, trough-normalize, and interpolate a waveform around trough."""

    waveform = np.asarray(waveform, dtype=float)
    baseline_n = min(max(config.baseline_samples, 1), waveform.size)
    centered = waveform - float(np.nanmedian(waveform[:baseline_n]))
    trough_index = int(np.nanargmin(centered))
    trough_depth = abs(float(centered[trough_index]))
    if not np.isfinite(trough_depth) or trough_depth == 0:
        return np.full_like(config.time_grid_ms(), np.nan, dtype=float)
    normalized = centered / trough_depth
    relative_time_ms = (np.arange(waveform.size) - trough_index) * config.sample_dt_ms
    return np.interp(config.time_grid_ms(), relative_time_ms, normalized, left=np.nan, right=np.nan)


def summarize_waveforms_long(waveforms_long: pd.DataFrame) -> pd.DataFrame:
    """Return class mean, SEM, and counts on the common waveform time axis."""

    def sem(values: pd.Series) -> float:
        clean = values.dropna().to_numpy(dtype=float)
        if clean.size <= 1:
            return np.nan
        return float(np.nanstd(clean, ddof=1) / np.sqrt(clean.size))

    summary = (
        waveforms_long.groupby(["rs_fs_classification", "time_ms"], dropna=False)
        .agg(
            mean_normalized_amplitude=("normalized_amplitude", "mean"),
            sem_normalized_amplitude=("normalized_amplitude", sem),
            waveform_count=("normalized_amplitude", "count"),
        )
        .reset_index()
    )
    return summary


def write_rs_fs_template_waveform_figure(
    input_csv: str | Path = CANONICAL_MASTER_UNIT_TABLE,
    manifest_csv: str | Path = DEFAULT_STEP2_MANIFEST,
    output_figure: str | Path = DEFAULT_RS_FS_WAVEFORM_FIGURE,
    mean_sem_csv: str | Path = DEFAULT_RS_FS_WAVEFORM_MEAN_CSV,
    provenance_json: str | Path = DEFAULT_RS_FS_WAVEFORM_PROVENANCE_JSON,
    config: RSFSWaveformPlotConfig | None = None,
) -> tuple[Path, Path, Path]:
    """Write the RS/FS template waveform summary figure and sidecars."""

    config = config or RSFSWaveformPlotConfig()
    output_figure = Path(output_figure)
    mean_sem_csv = Path(mean_sem_csv)
    provenance_json = Path(provenance_json)
    output_figure.parent.mkdir(parents=True, exist_ok=True)
    mean_sem_csv.parent.mkdir(parents=True, exist_ok=True)
    provenance_json.parent.mkdir(parents=True, exist_ok=True)

    waveforms_long = load_rs_fs_template_waveforms(
        input_csv=input_csv,
        manifest_csv=manifest_csv,
        config=config,
        progress=True,
    )
    mean_sem = summarize_waveforms_long(waveforms_long)
    mean_sem.to_csv(mean_sem_csv, index=False)
    _plot_waveform_summary(waveforms_long, mean_sem, output_figure, config)
    unique_units = waveforms_long[["recording", "well", "unit_id", "rs_fs_classification"]].drop_duplicates()
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_csv": str(input_csv),
        "manifest_csv": str(manifest_csv),
        "output_figure": str(output_figure),
        "mean_sem_csv": str(mean_sem_csv),
        "row_count_long_waveforms": int(len(waveforms_long)),
        "unit_counts": unique_units.groupby("rs_fs_classification").size().to_dict(),
        "config": asdict(config),
        "normalization": (
            "Selected-channel analyzer average templates are baseline-subtracted using the "
            "first baseline_samples, divided by trough depth, aligned to trough=0 ms, "
            "and interpolated onto a common time grid."
        ),
    }
    provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")
    return output_figure, mean_sem_csv, provenance_json


def _load_average_templates(analyzer_path: Path) -> np.ndarray:
    try:
        import spikeinterface as si
    except ImportError as exc:
        raise ImportError("SpikeInterface is required to reopen Step 1 template analyzers.") from exc
    analyzer = si.load(analyzer_path)
    extension = analyzer.get_extension("templates")
    if extension is None:
        raise ValueError(f"Analyzer missing templates extension: {analyzer_path}")
    try:
        templates = extension.get_data(operator="average")
    except TypeError:
        templates = extension.get_data()
    return np.asarray(templates)


def _plot_waveform_summary(
    waveforms_long: pd.DataFrame,
    mean_sem: pd.DataFrame,
    output_figure: Path,
    config: RSFSWaveformPlotConfig,
) -> None:
    rng = np.random.default_rng(config.random_seed)
    fig, axes = plt.subplots(
        len(config.classes),
        3,
        figsize=(13.5, 6.8),
        sharex=True,
        sharey=True,
    )
    if len(config.classes) == 1:
        axes = np.asarray([axes])

    for row_index, class_label in enumerate(config.classes):
        class_waveforms = waveforms_long.loc[waveforms_long["rs_fs_classification"] == class_label]
        class_summary = mean_sem.loc[mean_sem["rs_fs_classification"] == class_label]
        time_ms = class_summary["time_ms"].to_numpy(dtype=float)
        mean = class_summary["mean_normalized_amplitude"].to_numpy(dtype=float)
        sem = class_summary["sem_normalized_amplitude"].to_numpy(dtype=float)
        color = CLASS_COLORS.get(class_label, "#444444")
        unit_count = class_waveforms["unit_id"].nunique()

        unit_keys = class_waveforms[["recording", "well", "unit_id"]].drop_duplicates()
        if len(unit_keys) > config.max_overlay_per_class:
            keep_indices = rng.choice(len(unit_keys), size=config.max_overlay_per_class, replace=False)
            unit_keys = unit_keys.iloc[np.sort(keep_indices)]
        overlay = class_waveforms.merge(unit_keys, on=["recording", "well", "unit_id"], how="inner")

        ax_overlay, ax_mean, ax_sem = axes[row_index]
        for _, unit_waveform in overlay.groupby(["recording", "well", "unit_id"], sort=False):
            ax_overlay.plot(
                unit_waveform["time_ms"],
                unit_waveform["normalized_amplitude"],
                color=color,
                alpha=0.08,
                linewidth=0.7,
            )
        ax_overlay.plot(time_ms, mean, color="#111111", linewidth=2.2)
        ax_overlay.set_title(f"{class_label}: individual templates + mean\nn={unit_count}")

        ax_mean.plot(time_ms, mean, color=color, linewidth=2.8)
        ax_mean.axhline(0, color="#c8c8c8", linewidth=0.8)
        ax_mean.set_title(f"{class_label}: mean normalized waveform")

        ax_sem.plot(time_ms, mean, color=color, linewidth=2.4)
        ax_sem.fill_between(time_ms, mean - sem, mean + sem, color=color, alpha=0.24, linewidth=0)
        ax_sem.axhline(0, color="#c8c8c8", linewidth=0.8)
        ax_sem.set_title(f"{class_label}: mean +/- SEM")

        for ax in [ax_overlay, ax_mean, ax_sem]:
            ax.axvline(0, color="#1f1f1f", linestyle="--", linewidth=1.0)
            ax.set_xlim(config.time_min_ms, config.time_max_ms)
            ax.set_ylim(-1.18, 1.05)
            ax.grid(axis="y", color="#eeeeee", linewidth=0.7)

    for ax in axes[-1]:
        ax.set_xlabel("Time from trough (ms)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Normalized amplitude")
    fig.suptitle("RS/FS template waveform summary", y=0.995)
    fig.tight_layout()
    fig.savefig(output_figure, dpi=220, bbox_inches="tight")
    plt.close(fig)
