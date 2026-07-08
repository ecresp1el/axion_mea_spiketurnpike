"""Build and load the canonical Step 3 master waveform metrics table.

This module intentionally stops short of a general analysis object model. It
loads only the assets needed to create the canonical Step 3 dataset: one row
per Kilosort good unit, with firing-rate and template waveform metrics. After
that CSV exists, downstream biological analyses should load it directly instead
of reopening every completed well unless they explicitly need per-well assets.
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_STEP2_MANIFEST = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "aind_unit_classification_step2_full_20260708_153945/step2_full_manifest.csv"
)

CANONICAL_MASTER_UNIT_TABLE = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/"
    "downstream/master_waveform_metrics_table.csv"
)

RECORDING_NAME = "block0_None_recording1"

MASTER_UNIT_TABLE_COLUMNS = [
    "recording",
    "well",
    "unit_id",
    "spike_count",
    "firing_rate_hz",
    "template_reference",
    "trough_to_peak_duration_ms",
    "waveform_asymmetry",
    "repolarization_slope",
    "rs_fs_classification",
    "optotag_status",
    "default_qc",
    "unitrefine_label",
    "unitrefine_probability",
    "bombcell_label",
]

STEP2_LABEL_COLUMNS = [
    "default_qc",
    "unitrefine_label",
    "unitrefine_probability",
    "bombcell_label",
]


def load_step2_manifest(path: str | Path = DEFAULT_STEP2_MANIFEST) -> pd.DataFrame:
    """Load the frozen Step 2 manifest used as the downstream well universe."""

    return pd.read_csv(Path(path))


def load_canonical_master_unit_table(path: str | Path = CANONICAL_MASTER_UNIT_TABLE) -> pd.DataFrame:
    """Load the canonical Step 3 dataset for downstream biological analyses."""

    return pd.read_csv(Path(path))


def paths_from_manifest_row(row: pd.Series | dict[str, Any], recording_name: str = RECORDING_NAME) -> dict[str, Path]:
    """Return the minimum file paths needed for one manifest row."""

    source_results_dir = Path(str(row["source_results_dir"]))
    recovery_output_dir = Path(str(row["recovery_output_dir"]))
    return {
        "source_results_dir": source_results_dir,
        "recovery_output_dir": recovery_output_dir,
        "curated_sorting": source_results_dir / "curated" / recording_name,
        "analyzer_zarr": source_results_dir / "postprocessed" / f"{recording_name}.zarr",
        "step2_labels_csv": recovery_output_dir / "curation" / f"unit_labels_{recording_name}.csv",
    }


def is_completed_well(paths: dict[str, Path], require_step2_labels: bool = False) -> bool:
    """Return whether a well has the persisted assets required by this table."""

    required = [
        paths["curated_sorting"] / "si_folder.json",
        paths["curated_sorting"] / "properties" / "KSLabel.npy",
        paths["analyzer_zarr"] / ".zattrs",
        paths["analyzer_zarr"] / "extensions" / "templates" / ".zattrs",
    ]
    if require_step2_labels:
        required.append(paths["step2_labels_csv"])
    return all(path.exists() for path in required)


def load_master_unit_table(
    manifest: pd.DataFrame | None = None,
    manifest_path: str | Path = DEFAULT_STEP2_MANIFEST,
    *,
    require_step2_labels: bool = False,
    recording_name: str = RECORDING_NAME,
    progress: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the master table for all completed wells in a manifest.

    Returns
    -------
    table:
        One row per Kilosort good unit.
    skipped_wells:
        One row per manifest well skipped because required assets were missing
        or because loading failed.
    """

    if manifest is None:
        manifest = load_step2_manifest(manifest_path)

    tables: list[pd.DataFrame] = []
    skipped: list[dict[str, Any]] = []
    total_wells = len(manifest)
    for well_number, (_, row) in enumerate(manifest.iterrows(), start=1):
        started = perf_counter()
        recording = row.get("recording", "")
        well = row.get("well", "")
        if progress:
            print(f"[{well_number}/{total_wells}] START {recording} {well}", flush=True)

        paths = paths_from_manifest_row(row, recording_name=recording_name)
        if not is_completed_well(paths, require_step2_labels=require_step2_labels):
            skipped.append(
                {
                    "recording": recording,
                    "well": well,
                    "reason": "missing_required_assets",
                }
            )
            if progress:
                elapsed = perf_counter() - started
                print(f"[{well_number}/{total_wells}] SKIP {recording} {well} missing_required_assets {elapsed:.2f}s", flush=True)
            continue

        try:
            table = load_master_unit_table_for_well(
                row,
                require_step2_labels=require_step2_labels,
                recording_name=recording_name,
            )
        except Exception as exc:  # noqa: BLE001 - collect failures across a batch table build
            skipped.append(
                {
                    "recording": recording,
                    "well": well,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            if progress:
                elapsed = perf_counter() - started
                print(
                    f"[{well_number}/{total_wells}] FAIL {recording} {well} "
                    f"{type(exc).__name__}: {exc} {elapsed:.2f}s",
                    flush=True,
                )
            continue

        if not table.empty:
            tables.append(table)
        if progress:
            elapsed = perf_counter() - started
            print(f"[{well_number}/{total_wells}] DONE {recording} {well} rows={len(table)} {elapsed:.2f}s", flush=True)

    if tables:
        out = pd.concat(tables, ignore_index=True)
        out = out[MASTER_UNIT_TABLE_COLUMNS]
    else:
        out = pd.DataFrame(columns=MASTER_UNIT_TABLE_COLUMNS)
    return out, pd.DataFrame(skipped, columns=["recording", "well", "reason"])


def load_master_unit_table_for_well(
    row: pd.Series | dict[str, Any],
    *,
    require_step2_labels: bool = False,
    recording_name: str = RECORDING_NAME,
) -> pd.DataFrame:
    """Build the master table rows for one completed well."""

    si = _load_spikeinterface()
    paths = paths_from_manifest_row(row, recording_name=recording_name)
    sorting = si.load(paths["curated_sorting"])
    analyzer = si.load(paths["analyzer_zarr"])

    unit_ids = list(sorting.unit_ids)
    analyzer_unit_ids = list(analyzer.unit_ids)
    sampling_frequency = _sampling_frequency(analyzer, sorting)
    duration_s = _recording_duration_seconds(analyzer)
    ks_labels = _property_by_unit(sorting, "KSLabel", unit_ids)
    templates = _load_average_templates(analyzer)

    step2_labels = _load_step2_labels(paths["step2_labels_csv"], unit_ids, require_step2_labels=require_step2_labels)
    rows = []
    for unit_index, unit_id in enumerate(unit_ids):
        ks_label = _normalise_label(ks_labels.get(unit_id, ""))
        if ks_label.lower() != "good":
            continue

        spike_count = _spike_count(sorting, unit_id)
        metrics = _template_metrics_for_unit(
            templates=templates,
            unit_id=unit_id,
            analyzer_unit_ids=analyzer_unit_ids,
            sampling_frequency=sampling_frequency,
        )
        row_values: dict[str, Any] = {
            "recording": row["recording"],
            "well": row["well"],
            "unit_id": _python_scalar(unit_id),
            "spike_count": spike_count,
            "firing_rate_hz": spike_count / duration_s if duration_s and duration_s > 0 else np.nan,
            "template_reference": metrics["template_reference"],
            "trough_to_peak_duration_ms": metrics["trough_to_peak_duration_ms"],
            "waveform_asymmetry": metrics["waveform_asymmetry"],
            "repolarization_slope": metrics["repolarization_slope"],
            "rs_fs_classification": pd.NA,
            "optotag_status": pd.NA,
        }
        for column in STEP2_LABEL_COLUMNS:
            row_values[column] = step2_labels.get(unit_id, {}).get(column, pd.NA)
        rows.append(row_values)

    return pd.DataFrame(rows, columns=MASTER_UNIT_TABLE_COLUMNS)


def _load_spikeinterface():
    try:
        import spikeinterface as si
    except ImportError as exc:
        raise ImportError(
            "Building the master unit table requires SpikeInterface. Run this "
            "inside the AIND SpikeInterface container used for the frozen outputs."
        ) from exc
    return si


def _sampling_frequency(analyzer, sorting) -> float:
    if getattr(analyzer, "recording", None) is not None:
        return float(analyzer.recording.get_sampling_frequency())
    if hasattr(sorting, "get_sampling_frequency"):
        return float(sorting.get_sampling_frequency())
    raise ValueError("Could not determine sampling frequency from analyzer or sorting.")


def _recording_duration_seconds(analyzer) -> float:
    recording = getattr(analyzer, "recording", None)
    if recording is None:
        raise ValueError("Analyzer does not include a recording; cannot compute firing rates.")
    if hasattr(recording, "get_total_duration"):
        return float(recording.get_total_duration())
    sampling_frequency = float(recording.get_sampling_frequency())
    return sum(
        float(recording.get_num_samples(segment_index=segment_index)) / sampling_frequency
        for segment_index in range(recording.get_num_segments())
    )


def _property_by_unit(sorting, property_name: str, unit_ids: list[Any]) -> dict[Any, Any]:
    values = sorting.get_property(property_name)
    if values is None:
        raise ValueError(f"Sorting is missing required property {property_name!r}.")
    if len(values) != len(unit_ids):
        raise ValueError(
            f"Sorting property {property_name!r} has {len(values)} values for {len(unit_ids)} unit IDs."
        )
    return dict(zip(unit_ids, values, strict=True))


def _load_average_templates(analyzer) -> np.ndarray:
    extension = analyzer.get_extension("templates")
    if extension is None:
        raise ValueError("Analyzer is missing the persisted templates extension.")
    try:
        templates = extension.get_data(operator="average")
    except TypeError:
        templates = extension.get_data()
        if isinstance(templates, dict):
            templates = templates.get("average")
    if templates is None:
        raise ValueError("Templates extension did not return average templates.")
    templates = np.asarray(templates)
    if templates.ndim != 3:
        raise ValueError(f"Expected templates with shape (units, samples, channels), found {templates.shape}.")
    return templates


def _load_step2_labels(
    path: Path,
    unit_ids: list[Any],
    *,
    require_step2_labels: bool,
) -> dict[Any, dict[str, Any]]:
    if not path.exists():
        if require_step2_labels:
            raise FileNotFoundError(f"Missing Step 2 labels CSV: {path}")
        return {}
    labels = pd.read_csv(path)
    if len(labels) != len(unit_ids):
        if require_step2_labels:
            raise ValueError(f"Step 2 labels row count {len(labels)} does not match {len(unit_ids)} units: {path}")
        return {}
    out: dict[Any, dict[str, Any]] = {}
    for unit_id, (_, label_row) in zip(unit_ids, labels.iterrows(), strict=True):
        out[unit_id] = {column: label_row[column] if column in labels.columns else pd.NA for column in STEP2_LABEL_COLUMNS}
    return out


def _spike_count(sorting, unit_id: Any) -> int:
    total = 0
    for segment_index in range(sorting.get_num_segments()):
        spikes = sorting.get_unit_spike_train(unit_id=unit_id, segment_index=segment_index)
        total += int(len(spikes))
    return total


def _template_metrics_for_unit(
    *,
    templates: np.ndarray,
    unit_id: Any,
    analyzer_unit_ids: list[Any],
    sampling_frequency: float,
) -> dict[str, Any]:
    try:
        template_unit_index = analyzer_unit_ids.index(unit_id)
    except ValueError as exc:
        raise ValueError(f"Unit {unit_id!r} is missing from analyzer unit IDs.") from exc

    template = np.asarray(templates[template_unit_index], dtype=float)
    channel_amplitudes = np.nanmax(template, axis=0) - np.nanmin(template, axis=0)
    if not np.isfinite(channel_amplitudes).any():
        return _empty_template_metrics(unit_id, template_unit_index)

    channel_index = int(np.nanargmax(channel_amplitudes))
    waveform = template[:, channel_index]
    if not np.isfinite(waveform).any():
        return _empty_template_metrics(unit_id, template_unit_index, channel_index)

    trough_index = int(np.nanargmin(waveform))
    if trough_index >= waveform.size - 1:
        post_peak_index = trough_index
    else:
        post_peak_index = trough_index + int(np.nanargmax(waveform[trough_index:]))
    pre_peak_index = int(np.nanargmax(waveform[: trough_index + 1])) if trough_index > 0 else trough_index

    trough_value = float(waveform[trough_index])
    pre_peak_amplitude = float(waveform[pre_peak_index] - trough_value)
    post_peak_amplitude = float(waveform[post_peak_index] - trough_value)
    duration_ms = (post_peak_index - trough_index) * 1000.0 / sampling_frequency
    asymmetry_denominator = pre_peak_amplitude + post_peak_amplitude
    waveform_asymmetry = (
        (post_peak_amplitude - pre_peak_amplitude) / asymmetry_denominator
        if asymmetry_denominator > 0
        else np.nan
    )
    repolarization_slope = post_peak_amplitude / duration_ms if duration_ms > 0 else np.nan
    return {
        "template_reference": f"templates.average[unit_index={template_unit_index},channel_index={channel_index}]",
        "trough_to_peak_duration_ms": duration_ms if duration_ms > 0 else np.nan,
        "waveform_asymmetry": waveform_asymmetry,
        "repolarization_slope": repolarization_slope,
    }


def _empty_template_metrics(unit_id: Any, unit_index: int, channel_index: int | None = None) -> dict[str, Any]:
    reference = f"templates.average[unit_index={unit_index}"
    if channel_index is not None:
        reference += f",channel_index={channel_index}"
    reference += "]"
    return {
        "template_reference": reference,
        "trough_to_peak_duration_ms": np.nan,
        "waveform_asymmetry": np.nan,
        "repolarization_slope": np.nan,
    }


def _normalise_label(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return value.tobytes().decode("utf-8")
    return str(value)


def _python_scalar(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value
