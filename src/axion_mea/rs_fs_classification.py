"""Table-first RS/FS classification for the canonical Step 3 dataset."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .master_unit_table import CANONICAL_MASTER_UNIT_TABLE, load_canonical_master_unit_table


DEFAULT_RS_FS_SUMMARY_CSV = CANONICAL_MASTER_UNIT_TABLE.with_name(
    "master_waveform_metrics_table_rs_fs_summary.csv"
)


@dataclass(frozen=True)
class RSFSClassificationConfig:
    """Heuristic waveform-width boundaries for RS/FS annotation."""

    trough_to_peak_threshold_ms: float = 0.45
    sampling_frequency_hz: float = 12500.0
    classification_margin_samples: float = 1.0
    fs_label: str = "FS_like"
    rs_label: str = "RS_like"
    borderline_label: str = "borderline"
    unknown_label: str = "unknown"

    @property
    def sample_dt_ms(self) -> float:
        return 1000.0 / self.sampling_frequency_hz

    @property
    def margin_ms(self) -> float:
        return self.classification_margin_samples * self.sample_dt_ms

    @property
    def fs_upper_bound_ms(self) -> float:
        return self.trough_to_peak_threshold_ms - self.margin_ms

    @property
    def rs_lower_bound_ms(self) -> float:
        return self.trough_to_peak_threshold_ms + self.margin_ms

    def provenance(self) -> dict[str, Any]:
        out = asdict(self)
        out["sample_dt_ms"] = self.sample_dt_ms
        out["fs_upper_bound_ms"] = self.fs_upper_bound_ms
        out["rs_lower_bound_ms"] = self.rs_lower_bound_ms
        out["rule"] = (
            "FS_like if trough_to_peak_duration_ms <= fs_upper_bound_ms; "
            "RS_like if trough_to_peak_duration_ms >= rs_lower_bound_ms; "
            "borderline if between those bounds; unknown if missing."
        )
        return out


def classify_rs_fs(
    table: pd.DataFrame,
    config: RSFSClassificationConfig | None = None,
) -> pd.DataFrame:
    """Return a copy of the canonical table with RS/FS labels filled."""

    config = config or RSFSClassificationConfig()
    out = table.copy()
    if "trough_to_peak_duration_ms" not in out.columns:
        raise ValueError("Missing required column: trough_to_peak_duration_ms")
    if "rs_fs_classification" not in out.columns:
        raise ValueError("Missing required column: rs_fs_classification")

    ttp = pd.to_numeric(out["trough_to_peak_duration_ms"], errors="coerce")
    labels = np.full(len(out), config.borderline_label, dtype=object)
    labels[ttp.isna().to_numpy()] = config.unknown_label
    labels[(ttp <= config.fs_upper_bound_ms).fillna(False).to_numpy()] = config.fs_label
    labels[(ttp >= config.rs_lower_bound_ms).fillna(False).to_numpy()] = config.rs_label
    out["rs_fs_classification"] = labels
    return out


def summarize_rs_fs(table: pd.DataFrame, config: RSFSClassificationConfig | None = None) -> pd.DataFrame:
    """Summarize RS/FS calls and waveform metrics for an annotated table."""

    config = config or RSFSClassificationConfig()
    if "rs_fs_classification" not in table.columns:
        raise ValueError("Missing required column: rs_fs_classification")

    table_with_well_key = table.copy()
    table_with_well_key["_recording_well_key"] = (
        table_with_well_key["recording"].astype(str) + "\t" + table_with_well_key["well"].astype(str)
    )
    summary = (
        table_with_well_key.groupby("rs_fs_classification", dropna=False)
        .agg(
            unit_count=("unit_id", "size"),
            recording_count=("recording", "nunique"),
            well_count=("_recording_well_key", "nunique"),
            median_trough_to_peak_duration_ms=("trough_to_peak_duration_ms", "median"),
            mean_trough_to_peak_duration_ms=("trough_to_peak_duration_ms", "mean"),
            median_firing_rate_hz=("firing_rate_hz", "median"),
            median_waveform_asymmetry=("waveform_asymmetry", "median"),
            median_repolarization_slope=("repolarization_slope", "median"),
        )
        .reset_index()
    )
    summary["trough_to_peak_threshold_ms"] = config.trough_to_peak_threshold_ms
    summary["fs_upper_bound_ms"] = config.fs_upper_bound_ms
    summary["rs_lower_bound_ms"] = config.rs_lower_bound_ms
    return summary.sort_values("unit_count", ascending=False, ignore_index=True)


def annotate_canonical_table_rs_fs(
    input_csv: str | Path = CANONICAL_MASTER_UNIT_TABLE,
    output_csv: str | Path | None = None,
    summary_csv: str | Path = DEFAULT_RS_FS_SUMMARY_CSV,
    config: RSFSClassificationConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Annotate the canonical Step 3 table and write RS/FS summary output."""

    config = config or RSFSClassificationConfig()
    input_csv = Path(input_csv)
    output_csv = Path(output_csv) if output_csv is not None else input_csv
    summary_csv = Path(summary_csv)

    table = load_canonical_master_unit_table(input_csv)
    annotated = classify_rs_fs(table, config=config)
    summary = summarize_rs_fs(annotated, config=config)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    _write_csv_atomic(annotated, output_csv)
    _write_csv_atomic(summary, summary_csv)
    return annotated, summary


def _write_csv_atomic(table: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    table.to_csv(tmp, index=False)
    tmp.replace(path)
