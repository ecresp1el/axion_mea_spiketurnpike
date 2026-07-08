#!/usr/bin/env python
"""Recover UnitRefine/Bombcell labels from completed AIND postprocessed output."""

from __future__ import annotations

import argparse
import inspect
import json
import os
import time
import traceback
import warnings
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import spikeinterface as si
import spikeinterface.curation as scur
import spikeinterface.metrics.quality as sqm
from aind_data_schema.components.identifiers import Code
from aind_data_schema.core.processing import DataProcess, ProcessStage
from aind_data_schema_models.process_names import ProcessName
from spikeinterface.curation.model_based_curation import load_model
from spikeinterface.core.core_tools import check_json
from spikeinterface.curation.curation_model import Curation
from spikeinterface.curation.unitrefine_curation import get_model_based_classification_kwargs
from spikeinterface.metrics.quality.quality_metrics import ComputeQualityMetrics


DEFAULT_CURATION_DICT = {
    "format_version": "2",
    "label_definitions": {
        "quality": {
            "label_options": ["good", "MUA", "noise"],
            "exclusive": True,
        },
    },
    "manual_labels": [],
    "removed": [],
    "merges": [],
    "splits": [],
}

URL = "https://github.com/AllenNeuralDynamics/aind-ephys-curation"
VERSION = "2.0-recovery"

UNITREFINE_FALLBACK_REQUIRED_COLUMNS = [
    "amplitude_cutoff",
    "amplitude_cv_median",
    "amplitude_cv_range",
    "amplitude_median",
    "drift_ptp",
    "drift_std",
    "drift_mad",
    "firing_range",
    "firing_rate",
    "isi_violations_ratio",
    "isi_violations_count",
    "num_spikes",
    "presence_ratio",
    "rp_contamination",
    "rp_violations",
    "sliding_rp_violation",
    "snr",
    "sync_spike_2",
    "sync_spike_4",
    "sync_spike_8",
    "d_prime",
    "isolation_distance",
    "l_ratio",
    "silhouette",
    "nn_hit_rate",
    "nn_miss_rate",
    "exp_decay",
    "half_width",
    "num_negative_peaks",
    "num_positive_peaks",
    "peak_to_valley",
    "peak_trough_ratio",
    "recovery_slope",
    "repolarization_slope",
    "spread",
    "velocity_above",
    "velocity_below",
]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def count_values(labels: pd.Series, values: list[str]) -> dict[str, int]:
    return {value: int(np.sum(labels == value)) for value in values}


def log(message: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {message}", flush=True)


def timed_step(label: str, func, *args, **kwargs):
    log(f"START {label}")
    start = time.perf_counter()
    try:
        result = func(*args, **kwargs)
    except Exception:
        log(f"FAILED {label} after {time.perf_counter() - start:.2f}s")
        raise
    log(f"DONE {label} in {time.perf_counter() - start:.2f}s")
    return result


def quality_metric_column_map() -> tuple[dict[str, str], dict[str, list[str]]]:
    column_to_metric = {}
    metric_to_columns = {}
    for metric in ComputeQualityMetrics.metric_list:
        columns = list(metric.metric_columns.keys())
        metric_to_columns[metric.metric_name] = columns
        for column in columns:
            column_to_metric[column] = metric.metric_name
    return column_to_metric, metric_to_columns


def threshold_metric_columns(thresholds: dict | None) -> set[str]:
    if not thresholds:
        return set()
    columns = set()
    for section in thresholds.values():
        if isinstance(section, dict) and {"greater", "less", "abs"}.intersection(section):
            continue
        elif isinstance(section, dict):
            columns.update(str(metric) for metric in section)
    return columns


def load_unitrefine_required_columns(unitrefine_params: dict) -> tuple[list[str], dict[str, object]]:
    classifiers = {
        "noise_neural_classifier": unitrefine_params.get(
            "noise_neural_classifier", "SpikeInterface/UnitRefine_noise_neural_classifier"
        ),
        "sua_mua_classifier": unitrefine_params.get(
            "sua_mua_classifier", "SpikeInterface/UnitRefine_sua_mua_classifier"
        ),
    }
    required_columns = set()
    model_reports = {}
    for label, classifier in classifiers.items():
        if classifier is None:
            model_reports[label] = {"classifier": None, "status": "skipped"}
            continue
        try:
            model, model_info = load_model(
                trust_model=True,
                **get_model_based_classification_kwargs(classifier),
            )
            features = [str(feature) for feature in model.feature_names_in_]
            required_columns.update(features)
            model_reports[label] = {
                "classifier": str(classifier),
                "status": "loaded",
                "required_columns": features,
                "model_info_requirements": (model_info or {}).get("requirements", {}),
            }
        except Exception:  # noqa: BLE001 - diagnostic fallback must not block metric discovery
            tb = traceback.format_exc()
            log(f"Failed to load UnitRefine model {classifier}; using fallback feature list")
            log(tb)
            required_columns.update(UNITREFINE_FALLBACK_REQUIRED_COLUMNS)
            model_reports[label] = {
                "classifier": str(classifier),
                "status": "fallback",
                "required_columns": UNITREFINE_FALLBACK_REQUIRED_COLUMNS,
                "traceback": tb,
            }
    return sorted(required_columns), model_reports


def metrics_for_columns(columns: set[str], column_to_metric: dict[str, str]) -> tuple[set[str], list[str]]:
    metric_names = set()
    unmapped_columns = []
    for column in sorted(columns):
        metric_name = column_to_metric.get(column)
        if metric_name is None:
            unmapped_columns.append(column)
        else:
            metric_names.add(metric_name)
    return metric_names, unmapped_columns


def metric_traceback(analyzer, metric_name: str, metric_params: dict, job_kwargs: dict) -> str:
    metric = ComputeQualityMetrics.get_metric_by_name(metric_name)
    tmp_data = {}
    if metric.needs_tmp_data:
        extension = ComputeQualityMetrics(analyzer)
        tmp_data = extension._prepare_data(analyzer, unit_ids=analyzer.unit_ids)
    metric.compute(
        analyzer,
        unit_ids=analyzer.unit_ids,
        metric_params=metric_params,
        tmp_data=tmp_data,
        job_kwargs=job_kwargs,
        periods=None,
    )
    return ""


def sanitize_quality_metric_params(metric_params: dict) -> dict:
    """Drop params not accepted by the installed SI metric functions.

    SI 0.104.8 mutates metric class default param dictionaries in place, and
    several metrics inherit the same empty default dict. Copy those defaults
    before computing so one metric's compatibility params cannot leak into
    another metric in the same process.
    """
    for metric in ComputeQualityMetrics.metric_list:
        metric.metric_params = deepcopy(metric.metric_params)

    sanitized = {}
    for metric_name, params in metric_params.items():
        metric = ComputeQualityMetrics.get_metric_by_name(metric_name)
        signature = inspect.signature(metric.metric_function)
        if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
            sanitized[metric_name] = deepcopy(params)
            continue
        allowed = set(signature.parameters)
        sanitized[metric_name] = {key: value for key, value in params.items() if key in allowed}
    return sanitized


def audit_unitrefine_features(analyzer, unitrefine_columns: list[str]) -> dict:
    combined_metrics = analyzer.get_metrics_extension_data()
    compatibility_columns = {
        "half_width": "trough_half_width",
        "peak_to_valley": "peak_to_trough_duration",
        "peak_trough_ratio": "peak_after_to_trough_ratio",
    }
    missing_features = []
    all_nan_features = []
    successful_features = []
    feature_columns = {}
    for feature in unitrefine_columns:
        column = feature if feature in combined_metrics.columns else compatibility_columns.get(feature)
        if column not in combined_metrics.columns:
            missing_features.append(feature)
            feature_columns[feature] = None
        else:
            feature_columns[feature] = column
            if combined_metrics[column].isna().all():
                all_nan_features.append(feature)
            else:
                successful_features.append(feature)
    return {
        "feature_names_in": unitrefine_columns,
        "missing_features": missing_features,
        "all_nan_features": all_nan_features,
        "successfully_computed_features": successful_features,
        "feature_to_computed_column": feature_columns,
        "combined_metric_columns": combined_metrics.columns.tolist(),
    }


def compute_quality_metrics_diagnostic(
    analyzer,
    quality_metrics_params: dict,
    curation_params: dict,
    output_dir: Path,
    metrics_to_run: list[str] | str | None = None,
    diagnostic_filename: str = "quality_metrics_diagnostic.json",
) -> dict:
    column_to_metric, metric_to_columns = quality_metric_column_map()
    available_metrics = sqm.get_quality_metric_list()
    requested_metrics = quality_metrics_params.get("metric_names") or available_metrics
    metric_params = sanitize_quality_metric_params(deepcopy(quality_metrics_params.get("metric_params", {})))
    other_quality_kwargs = {
        key: value
        for key, value in quality_metrics_params.items()
        if key not in {"metric_names", "metric_params", "metrics_to_compute", "delete_existing_metrics"}
    }

    unitrefine_params = curation_params.get("unitrefine", {})
    unitrefine_columns, unitrefine_model_reports = load_unitrefine_required_columns(unitrefine_params)
    unitrefine_metrics, unitrefine_non_quality_columns = metrics_for_columns(
        set(unitrefine_columns),
        column_to_metric,
    )

    default_qc_columns = set(curation_params.get("qc_thresholds", {}))
    default_qc_metrics, default_qc_non_quality_columns = metrics_for_columns(default_qc_columns, column_to_metric)

    bombcell_columns = threshold_metric_columns(curation_params.get("bombcell"))
    bombcell_metrics, bombcell_non_quality_columns = metrics_for_columns(bombcell_columns, column_to_metric)

    log(f"SpikeInterface version: {si.__version__}")
    log(f"Available quality metrics: {available_metrics}")
    log(f"UnitRefine required quality metrics: {sorted(unitrefine_metrics)}")
    log(f"UnitRefine non-quality/template metric columns: {unitrefine_non_quality_columns}")
    log(f"Bombcell required quality metrics: {sorted(bombcell_metrics)}")
    log(f"Bombcell non-quality/template metric columns: {bombcell_non_quality_columns}")
    log(f"Default QC required quality metrics: {sorted(default_qc_metrics)}")
    required_metric_names = unitrefine_metrics | default_qc_metrics | bombcell_metrics
    required_metrics = [metric for metric in requested_metrics if metric in required_metric_names]
    optional_metrics = [metric for metric in requested_metrics if metric not in required_metric_names]
    if metrics_to_run == "required":
        metrics_to_run = required_metrics
    elif metrics_to_run == "optional":
        metrics_to_run = optional_metrics
    elif metrics_to_run is None:
        metrics_to_run = requested_metrics

    log(f"Configured quality metrics: {requested_metrics}")
    log(f"Required pre-classifier quality metrics: {required_metrics}")
    log(f"Optional post-classifier quality metrics: {optional_metrics}")
    log(f"Quality metrics in this pass: {metrics_to_run}")

    completed_metrics = []
    failed_metrics = []
    skipped_metrics = []
    metric_runs = []
    qm_start = time.perf_counter()
    quality_job_kwargs = dict(si.get_global_job_kwargs())

    for metric_name in metrics_to_run:
        metric_start_elapsed = time.perf_counter() - qm_start
        log(
            "QUALITY_METRIC START "
            f"metric={metric_name} "
            f"elapsed_since_quality_start={metric_start_elapsed:.2f}s"
        )
        metric_start = time.perf_counter()
        metric_record = {
            "metric": metric_name,
            "status": "unknown",
            "start_elapsed_seconds": round(metric_start_elapsed, 2),
            "runtime_seconds": None,
            "warnings": [],
            "traceback": "",
            "columns": metric_to_columns.get(metric_name, []),
        }
        try:
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                analyzer.compute(
                    "quality_metrics",
                    metric_names=[metric_name],
                    metrics_to_compute=[metric_name],
                    delete_existing_metrics=False,
                    save=False,
                    metric_params={metric_name: metric_params.get(metric_name, {})},
                    **other_quality_kwargs,
                )
            metric_record["warnings"] = [str(warning.message) for warning in caught_warnings]
            error_warnings = [
                message
                for message in metric_record["warnings"]
                if f"Error computing metric {metric_name}:" in message
            ]
            dependency_warnings = [
                message
                for message in metric_record["warnings"]
                if "will not be computed due to missing dependencies" in message
            ]
            qm_ext = analyzer.get_extension("quality_metrics")
            qm_data = qm_ext.get_data() if qm_ext is not None else pd.DataFrame()
            expected_columns = metric_to_columns.get(metric_name, [])
            missing_columns = [column for column in expected_columns if column not in qm_data.columns]
            metric_record["missing_columns"] = missing_columns
            metric_record["runtime_seconds"] = round(time.perf_counter() - metric_start, 2)
            if error_warnings:
                try:
                    metric_traceback(
                        analyzer,
                        metric_name,
                        metric_params.get(metric_name, {}),
                        quality_job_kwargs,
                    )
                except Exception:  # noqa: BLE001 - this is the traceback diagnostic path
                    metric_record["traceback"] = traceback.format_exc()
                    log(metric_record["traceback"])
                metric_record["status"] = "failed"
                failed_metrics.append(metric_record)
                log(
                    "QUALITY_METRIC FAILED "
                    f"metric={metric_name} "
                    f"runtime={metric_record['runtime_seconds']:.2f}s "
                    f"warnings={error_warnings}"
                )
            elif missing_columns:
                metric_record["status"] = "skipped"
                metric_record["reason"] = "missing output columns after compute"
                skipped_metrics.append(metric_record)
                log(
                    "QUALITY_METRIC SKIPPED "
                    f"metric={metric_name} "
                    f"runtime={metric_record['runtime_seconds']:.2f}s "
                    f"missing_columns={missing_columns} "
                    f"warnings={dependency_warnings}"
                )
            else:
                metric_record["status"] = "completed"
                completed_metrics.append(metric_name)
                log(
                    "QUALITY_METRIC DONE "
                    f"metric={metric_name} "
                    f"runtime={metric_record['runtime_seconds']:.2f}s"
                )
        except Exception:  # noqa: BLE001 - continue per diagnostic requirements
            metric_record["runtime_seconds"] = round(time.perf_counter() - metric_start, 2)
            metric_record["status"] = "failed"
            metric_record["traceback"] = traceback.format_exc()
            failed_metrics.append(metric_record)
            log(
                "QUALITY_METRIC FAILED "
                f"metric={metric_name} "
                f"runtime={metric_record['runtime_seconds']:.2f}s"
            )
            log(metric_record["traceback"])
        metric_runs.append(metric_record)

    total_runtime = round(time.perf_counter() - qm_start, 2)
    qm_ext = analyzer.get_extension("quality_metrics")
    computed_columns = qm_ext.get_data().columns.tolist() if qm_ext is not None else []
    unitrefine_feature_audit = audit_unitrefine_features(analyzer, unitrefine_columns)
    diagnostic = {
        "spikeinterface_version": si.__version__,
        "available_quality_metrics": available_metrics,
        "configured_quality_metrics": requested_metrics,
        "metrics_run_in_this_pass": metrics_to_run,
        "required_pre_classifier_quality_metrics": required_metrics,
        "optional_post_classifier_quality_metrics": optional_metrics,
        "unitrefine_required_columns": unitrefine_columns,
        "unitrefine_required_quality_metrics": sorted(unitrefine_metrics),
        "unitrefine_non_quality_or_template_columns": unitrefine_non_quality_columns,
        "unitrefine_model_reports": unitrefine_model_reports,
        "unitrefine_feature_audit": unitrefine_feature_audit,
        "bombcell_required_columns": sorted(bombcell_columns),
        "bombcell_required_quality_metrics": sorted(bombcell_metrics),
        "bombcell_non_quality_or_template_columns": bombcell_non_quality_columns,
        "default_qc_required_columns": sorted(default_qc_columns),
        "default_qc_required_quality_metrics": sorted(default_qc_metrics),
        "completed_metrics": completed_metrics,
        "failed_metrics": failed_metrics,
        "skipped_metrics": skipped_metrics,
        "metric_runs": metric_runs,
        "computed_quality_metric_columns": computed_columns,
        "total_runtime_seconds": total_runtime,
    }
    diagnostic_path = output_dir / diagnostic_filename
    diagnostic_path.write_text(json.dumps(check_json(diagnostic), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    log(
        "QUALITY_METRIC SUMMARY "
        f"completed={completed_metrics} "
        f"failed={[record['metric'] for record in failed_metrics]} "
        f"skipped={[record.get('metric') for record in skipped_metrics]} "
        f"total_runtime={total_runtime:.2f}s"
    )
    log(f"UNITREFINE FEATURE AUDIT missing={unitrefine_feature_audit['missing_features']}")
    log(f"UNITREFINE FEATURE AUDIT all_nan={unitrefine_feature_audit['all_nan_features']}")
    log(
        "UNITREFINE FEATURE AUDIT successful="
        f"{unitrefine_feature_audit['successfully_computed_features']}"
    )
    return diagnostic


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-results-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--params-json", required=True, type=Path)
    parser.add_argument("--recording", required=True)
    parser.add_argument("--well", required=True)
    parser.add_argument("--recording-name", default="block0_None_recording1")
    parser.add_argument("--n-jobs", type=int, default=int(os.environ.get("N_JOBS_EXT", "2")))
    args = parser.parse_args()

    params = load_json(args.params_json)
    postprocessing_params = deepcopy(params["postprocessing"])
    curation_params = deepcopy(params["curation"])

    source_analyzer = args.source_results_dir / "postprocessed" / f"{args.recording_name}.zarr"
    if not source_analyzer.is_dir():
        raise FileNotFoundError(f"Missing source postprocessed analyzer: {source_analyzer}")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    labels_dir = args.output_dir / "curation"
    labels_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "provenance").mkdir(exist_ok=True)

    si.set_global_job_kwargs(
        n_jobs=args.n_jobs,
        chunk_duration=postprocessing_params.get("job_kwargs", {}).get("chunk_duration", "1s"),
        progress_bar=False,
    )

    log(f"Loading source analyzer: {source_analyzer}")
    analyzer = si.load(source_analyzer)
    log(
        "Loaded analyzer "
        f"units={len(analyzer.unit_ids)} "
        f"channels={analyzer.recording.get_num_channels() if analyzer.recording is not None else 'missing'} "
        f"sampling_frequency={analyzer.recording.get_sampling_frequency() if analyzer.recording is not None else 'missing'}"
    )
    extension_dict = deepcopy(postprocessing_params["extensions"])
    recovery_extension_order = [
        "noise_levels",
        "waveforms",
        "templates",
        "spike_locations",
        "spike_amplitudes",
        "principal_components",
        "template_similarity",
        "template_metrics",
    ]
    missing_extensions = {
        name: extension_dict[name]
        for name in recovery_extension_order
        if name in extension_dict and (analyzer.get_extension(name) is None or name == "templates")
    }
    quality_metrics_params = extension_dict.get("quality_metrics")
    log(f"Existing extensions: {analyzer.get_loaded_extension_names()}")
    log(f"Missing recovery extensions to compute: {list(missing_extensions.keys())}")
    log(f"Will compute quality_metrics: {quality_metrics_params is not None and analyzer.get_extension('quality_metrics') is None}")

    started = datetime.now()
    t0 = time.perf_counter()
    for extension_name, extension_params in missing_extensions.items():
        timed_step(
            f"compute extension {extension_name}",
            analyzer.compute,
            extension_name,
            save=False,
            **extension_params,
        )
    if quality_metrics_params is not None and analyzer.get_extension("quality_metrics") is None:
        quality_metrics_diagnostic = compute_quality_metrics_diagnostic(
            analyzer,
            quality_metrics_params,
            curation_params,
            args.output_dir,
            metrics_to_run="required",
            diagnostic_filename="quality_metrics_required_diagnostic.json",
        )
    else:
        quality_metrics_diagnostic = {
            "status": "not_computed",
            "reason": "quality_metrics_params_missing_or_extension_already_present",
            "spikeinterface_version": si.__version__,
            "available_quality_metrics": sqm.get_quality_metric_list(),
        }
    optional_quality_metrics_diagnostic = {"status": "not_computed", "reason": "no_optional_metrics_attempted"}

    qm_ext = analyzer.get_extension("quality_metrics")
    tm_ext = analyzer.get_extension("template_metrics")
    if qm_ext is None:
        raise RuntimeError("quality_metrics extension is still missing after recovery compute")
    if tm_ext is None:
        raise RuntimeError("template_metrics extension is still missing after recovery compute")

    n_units = int(len(analyzer.unit_ids))
    qc_thresholds = curation_params["qc_thresholds"]
    qm = qm_ext.get_data()
    default_qc_labels = timed_step(
        "default QC threshold labels",
        scur.threshold_metrics_label_units,
        qm,
        thresholds=qc_thresholds,
        pass_label=True,
        fail_label=False,
        column_name="default_qc",
    )

    unitrefine_params = curation_params.get("unitrefine", {})
    unitrefine_labels = timed_step(
        "UnitRefine labeling",
        scur.unitrefine_label_units,
        analyzer,
        noise_neural_classifier=unitrefine_params.get(
            "noise_neural_classifier", "SpikeInterface/UnitRefine_noise_neural_classifier"
        ),
        sua_mua_classifier=unitrefine_params.get(
            "sua_mua_classifier", "SpikeInterface/UnitRefine_sua_mua_classifier"
        ),
    )

    bombcell_labels = None
    bombcell_error = ""
    try:
        bombcell_labels = timed_step(
            "Bombcell labeling",
            scur.bombcell_label_units,
            analyzer,
            thresholds=curation_params.get("bombcell"),
        )
    except Exception as exc:  # noqa: BLE001 - preserve curation provenance
        bombcell_error = repr(exc)
        log(f"Bombcell labeling failed but will be preserved in provenance: {bombcell_error}")

    all_labels = [default_qc_labels, unitrefine_labels]
    if bombcell_labels is not None:
        all_labels.append(bombcell_labels)
    all_labels_df = pd.concat(all_labels, axis=1)
    labels_csv = labels_dir / f"unit_labels_{args.recording_name}.csv"
    all_labels_df.to_csv(labels_csv, index=False)

    optional_metrics = quality_metrics_diagnostic.get("optional_post_classifier_quality_metrics", [])
    if quality_metrics_params is not None and optional_metrics:
        optional_quality_metrics_diagnostic = compute_quality_metrics_diagnostic(
            analyzer,
            quality_metrics_params,
            curation_params,
            args.output_dir,
            metrics_to_run=optional_metrics,
            diagnostic_filename="quality_metrics_optional_diagnostic.json",
        )

    noise_strategy = curation_params.get("noise_strategy")
    if noise_strategy == "bombcell":
        if bombcell_labels is None:
            raise RuntimeError("bombcell noise strategy requested but Bombcell labeling failed")
        noise_units = analyzer.unit_ids[all_labels_df["bombcell_label"] == "noise"]
    elif noise_strategy == "unitrefine":
        noise_units = analyzer.unit_ids[all_labels_df["unitrefine_label"] == "noise"]
    elif noise_strategy == "bombcell+unitrefine":
        if bombcell_labels is None:
            raise RuntimeError("bombcell+unitrefine strategy requested but Bombcell labeling failed")
        noise_units = analyzer.unit_ids[
            (all_labels_df["unitrefine_label"] == "noise")
            & (all_labels_df["bombcell_label"] == "noise")
        ]
    else:
        noise_units = []

    if len(noise_units) > 0:
        neural_units = [unit_id for unit_id in analyzer.unit_ids if unit_id not in noise_units]
        analyzer_for_merge = analyzer.select_units(unit_ids=neural_units)
    else:
        analyzer_for_merge = analyzer

    potential_merges = timed_step(
        "SLAy merge candidate computation",
        scur.compute_merge_unit_groups,
        analyzer_for_merge,
        preset="slay",
        steps_params=curation_params.get("slay"),
    )
    with (labels_dir / f"unit_merges_{args.recording_name}.json").open("w", encoding="utf-8") as handle:
        json.dump(check_json(potential_merges), handle, indent=2)

    curation_dict = deepcopy(DEFAULT_CURATION_DICT)
    curation_dict["unit_ids"] = analyzer.unit_ids
    curation_dict["removed"] = list(noise_units)
    for unit_id in noise_units:
        curation_dict["manual_labels"].append({"unit_id": unit_id, "quality": ["noise"]})
    curation_dict["merges"] = [{"unit_ids": list(merge)} for merge in potential_merges]
    curation_model = Curation(**curation_dict)
    curation_json = labels_dir / f"curation_{args.recording_name}.json"
    curation_json.write_text(curation_model.model_dump_json(indent=4), encoding="utf-8")

    elapsed = round(time.perf_counter() - t0, 2)
    unitrefine_counts = count_values(unitrefine_labels["unitrefine_label"], ["sua", "mua", "noise"])
    bombcell_counts = (
        count_values(bombcell_labels["bombcell_label"], ["good", "mua", "noise", "non_soma"])
        if bombcell_labels is not None
        else {}
    )
    summary = {
        "recording": args.recording,
        "well": args.well,
        "recording_name": args.recording_name,
        "source_results_dir": str(args.source_results_dir),
        "output_dir": str(args.output_dir),
        "source_analyzer": str(source_analyzer),
        "recovery_analyzer": "",
        "recovery_mode": "in_memory_extensions_from_source_analyzer",
        "n_units": n_units,
        "missing_extensions_computed": list(missing_extensions.keys())
        + (["quality_metrics"] if quality_metrics_params is not None else []),
        "quality_metrics_diagnostic": quality_metrics_diagnostic,
        "quality_metrics_optional_diagnostic": optional_quality_metrics_diagnostic,
        "default_qc_pass": int(np.sum(default_qc_labels["default_qc"])),
        "default_qc_fail": int(n_units - np.sum(default_qc_labels["default_qc"])),
        "unitrefine_counts": unitrefine_counts,
        "bombcell_counts": bombcell_counts,
        "bombcell_error": bombcell_error,
        "noise_strategy": noise_strategy,
        "noise_units_removed": len(noise_units),
        "slay_merge_groups": len(potential_merges),
        "labels_csv": str(labels_csv),
        "curation_json": str(curation_json),
        "elapsed_seconds": elapsed,
    }
    (args.output_dir / "classification_recovery_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    process = DataProcess(
        process_type=ProcessName.EPHYS_CURATION,
        stage=ProcessStage.PROCESSING,
        name="Axion recovered UnitRefine/Bombcell curation",
        experimenters=["AIND Pipeline", "Axion MEA bridge"],
        code=Code(url=URL, version=VERSION, parameters=curation_params),
        start_date_time=started,
        end_date_time=started + timedelta(seconds=int(elapsed)),
        output_path=str(args.output_dir),
        output_parameters=summary,
        notes="Recovered missing quality_metrics/template_metrics from an existing postprocessed analyzer.",
    )
    (args.output_dir / "data_process_unit_classification_recovery.json").write_text(
        process.model_dump_json(indent=3),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
