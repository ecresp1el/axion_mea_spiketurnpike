#!/usr/bin/env python
"""Recover UnitRefine/Bombcell labels from completed AIND postprocessed output."""

from __future__ import annotations

import argparse
import json
import os
import time
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import spikeinterface as si
import spikeinterface.curation as scur
from aind_data_schema.components.identifiers import Code
from aind_data_schema.core.processing import DataProcess, ProcessStage
from aind_data_schema_models.process_names import ProcessName
from spikeinterface.core.core_tools import check_json
from spikeinterface.curation.curation_model import Curation


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


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def count_values(labels: pd.Series, values: list[str]) -> dict[str, int]:
    return {value: int(np.sum(labels == value)) for value in values}


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

    analyzer = si.load(source_analyzer)
    extension_dict = deepcopy(postprocessing_params["extensions"])
    recovery_extension_order = [
        "noise_levels",
        "waveforms",
        "templates",
        "spike_amplitudes",
        "principal_components",
        "template_similarity",
        "template_metrics",
    ]
    missing_extensions = {
        name: extension_dict[name]
        for name in recovery_extension_order
        if name in extension_dict and analyzer.get_extension(name) is None
    }
    quality_metrics_params = extension_dict.get("quality_metrics")

    started = datetime.now()
    t0 = time.perf_counter()
    for extension_name, extension_params in missing_extensions.items():
        analyzer.compute(extension_name, save=False, **extension_params)
    if quality_metrics_params is not None and analyzer.get_extension("quality_metrics") is None:
        analyzer.compute("quality_metrics", save=False, **quality_metrics_params)

    qm_ext = analyzer.get_extension("quality_metrics")
    tm_ext = analyzer.get_extension("template_metrics")
    if qm_ext is None:
        raise RuntimeError("quality_metrics extension is still missing after recovery compute")
    if tm_ext is None:
        raise RuntimeError("template_metrics extension is still missing after recovery compute")

    n_units = int(len(analyzer.unit_ids))
    qc_thresholds = curation_params["qc_thresholds"]
    qm = qm_ext.get_data()
    default_qc_labels = scur.threshold_metrics_label_units(
        qm,
        thresholds=qc_thresholds,
        pass_label=True,
        fail_label=False,
        column_name="default_qc",
    )

    unitrefine_params = curation_params.get("unitrefine", {})
    unitrefine_labels = scur.unitrefine_label_units(
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
        bombcell_labels = scur.bombcell_label_units(
            analyzer,
            thresholds=curation_params.get("bombcell"),
        )
    except Exception as exc:  # noqa: BLE001 - preserve curation provenance
        bombcell_error = repr(exc)

    all_labels = [default_qc_labels, unitrefine_labels]
    if bombcell_labels is not None:
        all_labels.append(bombcell_labels)
    all_labels_df = pd.concat(all_labels, axis=1)
    labels_csv = labels_dir / f"unit_labels_{args.recording_name}.csv"
    all_labels_df.to_csv(labels_csv, index=False)

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

    potential_merges = scur.compute_merge_unit_groups(
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
