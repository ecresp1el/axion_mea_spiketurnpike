#!/usr/bin/env python3
"""Build SUA-only CytoView dorsal/ventral spontaneous-activity metrics and plots."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from axion_mea.spontaneous_activity import (  # noqa: E402
    BurstDetectionParameters,
    summarize_smoothed_inverse_isi_rate,
    summarize_unit_activity,
)


DEFAULT_JOB_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_UNIT_METRICS = DEFAULT_JOB_ROOT / "cytoview_dorsal_ventral_step1_20260709_unit_metrics.csv"
DEFAULT_ALIGNED_METRICS = (
    DEFAULT_JOB_ROOT
    / "waveform_alignment_feature_audit_20260709_cytoview"
    / "waveform_alignment_feature_audit_20260709_paired_unit_metrics.csv"
)
REGION_ORDER = ["dorsal", "ventral"]
REGION_COLORS = {"dorsal": "#2A9D8F", "ventral": "#6A4C93"}
VARIANT_MARKERS = {
    "primary_raw": "o",
    "filter_200Hz-3kHz": "s",
    "broadband_processor_raw": "^",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-metrics-csv", type=Path, default=DEFAULT_UNIT_METRICS)
    parser.add_argument("--aligned-metrics-csv", type=Path, default=DEFAULT_ALIGNED_METRICS)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--date-label", default="20260710")
    parser.add_argument("--kslabel", default="good", choices=("good", "mua"))
    parser.add_argument("--fs-cutoff-ms", type=float, default=0.50)
    parser.add_argument("--min-template-ptp-uv", type=float, default=None)
    parser.add_argument("--max-contam-pct", type=float, default=None)
    parser.add_argument("--max-isi-lt-2ms-fraction", type=float, default=None)
    parser.add_argument("--max-isi-ms", type=float, default=100.0)
    parser.add_argument("--min-spikes-per-burst", type=int, default=3)
    parser.add_argument("--min-burst-duration-ms", type=float, default=100.0)
    parser.add_argument("--inverse-isi-gaussian-sigma-ms", type=float, default=50.0)
    parser.add_argument("--inverse-isi-evaluation-bin-ms", type=float, default=1.0)
    parser.add_argument("--min-spikes-for-smoothed-rate", type=int, default=30)
    parser.add_argument("--export-formats", default="png,pdf,svg")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import spikeinterface.full as si

    unit_metrics_path = args.unit_metrics_csv.expanduser().resolve()
    aligned_metrics_path = args.aligned_metrics_csv.expanduser().resolve()
    source_all = pd.read_csv(unit_metrics_path)
    source_all["KSLabel"] = source_all["KSLabel"].astype(str).str.lower()
    source_all["lfp_like_excluded"] = source_all.apply(_is_lfp_like_row, axis=1)
    lfp_excluded = source_all.loc[source_all["lfp_like_excluded"]].copy()
    recording_well_universe = _recording_well_universe(
        source_all.loc[~source_all["lfp_like_excluded"]].copy()
    )
    source_kslabel = source_all.loc[
        source_all["KSLabel"].eq(args.kslabel) & ~source_all["lfp_like_excluded"]
    ].copy()
    quality_columns = [
        "template_ptp_best_channel_uV",
        "ContamPct",
        "isi_lt_2ms_fraction",
    ]
    missing_quality_columns = [column for column in quality_columns if column not in source_kslabel]
    if missing_quality_columns:
        raise ValueError(f"Source metrics are missing quality columns: {missing_quality_columns}")
    template_ptp_uV = pd.to_numeric(
        source_kslabel["template_ptp_best_channel_uV"], errors="coerce"
    )
    if args.min_template_ptp_uv is None:
        template_pass = pd.Series(True, index=source_kslabel.index)
    else:
        if not np.isfinite(args.min_template_ptp_uv) or args.min_template_ptp_uv < 0:
            raise ValueError("--min-template-ptp-uv must be finite and >= 0")
        template_pass = template_ptp_uV.ge(args.min_template_ptp_uv)
    template_excluded = source_kslabel.loc[~template_pass].copy()
    source_after_template = source_kslabel.loc[template_pass].copy()

    if args.max_contam_pct is None:
        contamination_pass = pd.Series(True, index=source_after_template.index)
    else:
        if not np.isfinite(args.max_contam_pct) or args.max_contam_pct < 0:
            raise ValueError("--max-contam-pct must be finite and >= 0")
        contamination_pass = pd.to_numeric(
            source_after_template["ContamPct"], errors="coerce"
        ).le(args.max_contam_pct)
    contamination_excluded = source_after_template.loc[~contamination_pass].copy()
    source_after_contamination = source_after_template.loc[contamination_pass].copy()

    if args.max_isi_lt_2ms_fraction is None:
        refractory_pass = pd.Series(True, index=source_after_contamination.index)
    else:
        if (
            not np.isfinite(args.max_isi_lt_2ms_fraction)
            or args.max_isi_lt_2ms_fraction < 0
            or args.max_isi_lt_2ms_fraction > 1
        ):
            raise ValueError("--max-isi-lt-2ms-fraction must be finite and between 0 and 1")
        refractory_pass = pd.to_numeric(
            source_after_contamination["isi_lt_2ms_fraction"], errors="coerce"
        ).le(args.max_isi_lt_2ms_fraction)
    refractory_excluded = source_after_contamination.loc[~refractory_pass].copy()
    source = source_after_contamination.loc[refractory_pass].copy()
    if source.empty:
        raise SystemExit(f"No non-LFP KSLabel={args.kslabel} units found in {unit_metrics_path}")
    source["unit_key"] = source.apply(_unit_key, axis=1)
    if source["unit_key"].duplicated().any():
        raise ValueError("Source unit keys are not unique")

    aligned = pd.read_csv(aligned_metrics_path)
    aligned["KSLabel"] = aligned["KSLabel"].astype(str).str.lower()
    aligned = aligned.loc[aligned["KSLabel"].eq(args.kslabel)].copy()
    aligned_columns = [
        "unit_key",
        "usable_snippets",
        "after_trough_to_peak_duration_ms",
        "after_waveform_asymmetry",
        "after_post_trough_rebound_slope_uV_per_ms",
        "after_rep50_recovery_slope_uV_per_ms",
    ]
    missing_aligned_columns = [column for column in aligned_columns if column not in aligned.columns]
    if missing_aligned_columns:
        raise ValueError(f"Aligned table is missing columns: {missing_aligned_columns}")
    aligned = aligned[aligned_columns].drop_duplicates("unit_key")
    source = source.merge(aligned, on="unit_key", how="left", validate="one_to_one")
    source["aligned_fs_rs_class"] = np.where(
        pd.to_numeric(source["after_trough_to_peak_duration_ms"], errors="coerce").le(args.fs_cutoff_ms),
        "FS",
        "RS",
    )
    source.loc[source["after_trough_to_peak_duration_ms"].isna(), "aligned_fs_rs_class"] = "unclassified"

    parameters = BurstDetectionParameters(
        max_isi_ms=args.max_isi_ms,
        min_spikes=args.min_spikes_per_burst,
        min_duration_ms=args.min_burst_duration_ms,
    )
    parameters.validate()

    unit_rows: list[dict[str, object]] = []
    burst_rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for analyzer_path_text, analyzer_group in source.groupby("analyzer_path", sort=False):
        analyzer_path = Path(str(analyzer_path_text))
        try:
            analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
            sorting = analyzer.sorting
            sampling_frequency = float(analyzer.recording.get_sampling_frequency())
            recording_duration_s = float(analyzer.recording.get_total_duration())
            unit_id_map = {str(unit_id): unit_id for unit_id in sorting.get_unit_ids()}
            for _, source_row in analyzer_group.iterrows():
                unit_id = unit_id_map.get(_unit_id_text(source_row["unit_id"]))
                if unit_id is None:
                    raise ValueError(f"unit {source_row['unit_id']} missing from sorting")
                spike_samples = np.asarray(sorting.get_unit_spike_train(unit_id), dtype=np.int64)
                spike_times_s = spike_samples.astype(float) / sampling_frequency
                summary, events = summarize_unit_activity(spike_times_s, recording_duration_s, parameters)
                smoothed_rate_summary = summarize_smoothed_inverse_isi_rate(
                    spike_times_s,
                    recording_duration_s,
                    gaussian_sigma_ms=args.inverse_isi_gaussian_sigma_ms,
                    evaluation_bin_ms=args.inverse_isi_evaluation_bin_ms,
                    min_spikes=args.min_spikes_for_smoothed_rate,
                )
                if int(summary["spike_count_recomputed"]) != int(source_row["spike_count"]):
                    raise ValueError(
                        f"spike count mismatch for {source_row['unit_key']}: "
                        f"{summary['spike_count_recomputed']} != {source_row['spike_count']}"
                    )

                recording_well_id = f"{source_row['recording']}|{source_row['well']}"
                base = {
                    "recording_well_id": recording_well_id,
                    "organoid_well": str(source_row["well"]),
                    "unit_key": source_row["unit_key"],
                    "recording": source_row["recording"],
                    "well": source_row["well"],
                    "region_call": source_row["region_call"],
                    "region_source": source_row.get("region_source", ""),
                    "region_override_applied": source_row.get("region_override_applied", False),
                    "plate_id": source_row.get("plate_id", ""),
                    "raw_variant": source_row.get("raw_variant", ""),
                    "recording_duration_s": recording_duration_s,
                    "unit_id": source_row["unit_id"],
                    "KSLabel": source_row["KSLabel"],
                    "analyzer_path": str(analyzer_path),
                    "sampling_frequency_hz": sampling_frequency,
                    "source_spike_count": int(source_row["spike_count"]),
                    "source_firing_rate_hz": float(source_row["firing_rate_hz"]),
                    "template_ptp_best_channel_uV": float(
                        source_row["template_ptp_best_channel_uV"]
                    ),
                    "template_ptp_minimum_uV": (
                        float(args.min_template_ptp_uv)
                        if args.min_template_ptp_uv is not None
                        else np.nan
                    ),
                    "source_ContamPct": float(source_row["ContamPct"]),
                    "maximum_ContamPct": (
                        float(args.max_contam_pct) if args.max_contam_pct is not None else np.nan
                    ),
                    "source_isi_lt_2ms_fraction": float(source_row["isi_lt_2ms_fraction"]),
                    "maximum_isi_lt_2ms_fraction": (
                        float(args.max_isi_lt_2ms_fraction)
                        if args.max_isi_lt_2ms_fraction is not None
                        else np.nan
                    ),
                    "aligned_usable_snippets": source_row.get("usable_snippets", np.nan),
                    "aligned_trough_to_peak_duration_ms": source_row.get(
                        "after_trough_to_peak_duration_ms", np.nan
                    ),
                    "aligned_waveform_asymmetry": source_row.get("after_waveform_asymmetry", np.nan),
                    "aligned_repolarization_slope_uV_per_ms": source_row.get(
                        "after_post_trough_rebound_slope_uV_per_ms", np.nan
                    ),
                    "aligned_rep50_recovery_slope_uV_per_ms": source_row.get(
                        "after_rep50_recovery_slope_uV_per_ms", np.nan
                    ),
                    "aligned_fs_rs_cutoff_ms": float(args.fs_cutoff_ms),
                    "aligned_fs_rs_class": source_row["aligned_fs_rs_class"],
                }
                unit_rows.append({**base, **summary, **smoothed_rate_summary})
                for event in events:
                    burst_rows.append({**base, **event.to_dict()})
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "analyzer_path": str(analyzer_path),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    if errors:
        pd.DataFrame(errors).to_csv(output_dir / "analysis_errors.csv", index=False)
        raise RuntimeError(f"Encountered {len(errors)} analyzer errors; see analysis_errors.csv")

    units = pd.DataFrame(unit_rows).sort_values(["region_call", "recording", "well", "unit_id"])
    bursts = pd.DataFrame(burst_rows).sort_values(
        ["region_call", "recording", "well", "unit_id", "burst_index"]
    )
    wells = _aggregate_recording_wells(units, recording_well_universe)
    region_summary = _aggregate_regions(wells)
    figure_source = _figure_source_data(wells)
    denominator = _denominator_flow(
        source_all,
        source_kslabel,
        source_after_template,
        source_after_contamination,
        source,
        template_excluded,
        contamination_excluded,
        refractory_excluded,
        units,
        wells,
        lfp_excluded,
        args.kslabel,
        args.min_template_ptp_uv,
        args.max_contam_pct,
        args.max_isi_lt_2ms_fraction,
    )

    stem = f"cytoview_dv_sua_spontaneous_activity_{args.date_label}"
    output_paths = {
        "unit_metrics": output_dir / f"{stem}_unit_metrics.csv",
        "burst_events": output_dir / f"{stem}_burst_events_long.csv.gz",
        "recording_well_summary": output_dir / f"{stem}_recording_well_summary.csv",
        "region_summary": output_dir / f"{stem}_region_summary.csv",
        "figure_source_data": output_dir / f"{stem}_figure_source_data.csv",
        "firing_rate_comparison_source_data": output_dir / f"{stem}_firing_rate_comparison_source_data.csv",
        "panel_e_smoothed_rate_versions_source_data": output_dir
        / f"{stem}_panel_e_smoothed_rate_versions_source_data.csv",
        "denominator_flow": output_dir / f"{stem}_denominator_flow.csv",
        "provenance": output_dir / f"{stem}_provenance.json",
    }
    units.to_csv(output_paths["unit_metrics"], index=False)
    bursts.to_csv(output_paths["burst_events"], index=False, compression="gzip")
    wells.to_csv(output_paths["recording_well_summary"], index=False)
    region_summary.to_csv(output_paths["region_summary"], index=False)
    figure_source.to_csv(output_paths["figure_source_data"], index=False)
    firing_rate_comparison_source = _firing_rate_comparison_source_data(wells)
    firing_rate_comparison_source.to_csv(
        output_paths["firing_rate_comparison_source_data"], index=False
    )
    panel_e_smoothed_rate_source = _panel_e_smoothed_rate_versions_source_data(wells)
    panel_e_smoothed_rate_source.to_csv(
        output_paths["panel_e_smoothed_rate_versions_source_data"], index=False
    )
    denominator.to_csv(output_paths["denominator_flow"], index=False)

    figure_paths = _plot_panel_e(
        plt,
        Line2D,
        wells,
        output_dir / stem,
        parameters=parameters,
        export_formats=args.export_formats,
        method_note=_quality_filter_note(
            args.min_template_ptp_uv,
            args.max_contam_pct,
            args.max_isi_lt_2ms_fraction,
        ),
    )
    firing_rate_comparison_paths = _plot_firing_rate_comparison(
        plt,
        Line2D,
        wells,
        output_dir / f"{stem}_firing_rate_method_comparison",
        gaussian_sigma_ms=args.inverse_isi_gaussian_sigma_ms,
        evaluation_bin_ms=args.inverse_isi_evaluation_bin_ms,
        min_spikes=args.min_spikes_for_smoothed_rate,
        quality_filter_note=_quality_filter_note(
            args.min_template_ptp_uv,
            args.max_contam_pct,
            args.max_isi_lt_2ms_fraction,
        ),
        export_formats=args.export_formats,
    )
    smoothed_rate_panel_e_paths: dict[str, list[Path]] = {}
    for temporal_summary, metric in _smoothed_rate_metrics().items():
        smoothed_rate_panel_e_paths[temporal_summary] = _plot_panel_e(
            plt,
            Line2D,
            wells,
            output_dir / f"{stem}_panel_e_smoothed_inverse_isi_temporal_{temporal_summary}",
            parameters=parameters,
            export_formats=args.export_formats,
            specs=_panel_specs_with_smoothed_rate(temporal_summary, metric),
            method_note=(
                _quality_filter_note(
                    args.min_template_ptp_uv,
                    args.max_contam_pct,
                    args.max_isi_lt_2ms_fraction,
                )
                + (
                    "; "
                    if any(
                        value is not None
                        for value in [
                            args.min_template_ptp_uv,
                            args.max_contam_pct,
                            args.max_isi_lt_2ms_fraction,
                        ]
                    )
                    else ""
                )
                + f"E1 inverse-ISI temporal {temporal_summary}, >= {args.min_spikes_for_smoothed_rate} "
                f"spikes/unit, Gaussian sigma = {args.inverse_isi_gaussian_sigma_ms:g} ms; "
                "E2-E6 unchanged"
            ),
        )
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "git_commit": _git_output(["rev-parse", "HEAD"]),
        "git_status": _git_output(["status", "--short"]),
        "unit_metrics_csv": str(unit_metrics_path),
        "unit_metrics_sha256": _sha256(unit_metrics_path),
        "aligned_metrics_csv": str(aligned_metrics_path),
        "aligned_metrics_sha256": _sha256(aligned_metrics_path),
        "kslabel": args.kslabel,
        "recording_version_policy": (
            "keep every spike-bearing primary/filter/BroadbandProcessor/round2 version as a separate recording; "
            "exclude only rows whose explicit raw_variant metadata is LFP/low-frequency-only"
        ),
        "lfp_filter_uses_recording_name": False,
        "one_well_equals_one_organoid": True,
        "unit_quality_filters": {
            "metric": "live average-template peak-to-peak amplitude on the best channel",
            "source_column": "template_ptp_best_channel_uV",
            "minimum_uV_inclusive": args.min_template_ptp_uv,
            "maximum_ContamPct_inclusive": args.max_contam_pct,
            "maximum_isi_lt_2ms_fraction_inclusive": args.max_isi_lt_2ms_fraction,
            "rule": _quality_filter_note(
                args.min_template_ptp_uv,
                args.max_contam_pct,
                args.max_isi_lt_2ms_fraction,
            ) or "no added unit-quality filter",
            "KSLabel_units_before_filter": int(len(source_kslabel)),
            "weak_template_units_excluded_sequentially": int(len(template_excluded)),
            "contamination_units_excluded_sequentially": int(len(contamination_excluded)),
            "refractory_units_excluded_sequentially": int(len(refractory_excluded)),
            "units_excluded_total": int(len(source_kslabel) - len(source)),
            "units_retained": int(len(source)),
        },
        "recording_well_observation_count": int(len(wells)),
        "unit_count": int(len(units)),
        "burst_count": int(len(bursts)),
        "lfp_like_source_rows_excluded": int(len(lfp_excluded)),
        "aligned_fs_rs": {
            "waveform_state": "aligned before feature extraction",
            "cutoff_ms": float(args.fs_cutoff_ms),
            "FS_rule": f"aligned TTP <= {args.fs_cutoff_ms:.2f} ms",
            "RS_rule": f"aligned TTP > {args.fs_cutoff_ms:.2f} ms",
            "class_counts": units["aligned_fs_rs_class"].value_counts(dropna=False).to_dict(),
        },
        "burst_detection": {
            "method": "contiguous adjacent-ISI threshold",
            "max_isi_ms": parameters.max_isi_ms,
            "min_spikes": parameters.min_spikes,
            "min_duration_ms": parameters.min_duration_ms,
            "within_burst_firing_rate": "spike_count / burst_duration_s",
            "interburst_interval": "next burst start - previous burst end",
        },
        "inverse_isi_gaussian_firing_rate": {
            "unit_inclusion": f"at least {args.min_spikes_for_smoothed_rate} detected spikes",
            "instantaneous_rate": "1 / adjacent interspike interval, held across that interval",
            "evaluation_bin_ms": float(args.inverse_isi_evaluation_bin_ms),
            "gaussian_sigma_ms": float(args.inverse_isi_gaussian_sigma_ms),
            "gaussian_truncate_sigma": 4.0,
            "outside_first_to_last_spike": "zero rate",
            "temporal_summaries": ["mean", "median", "maximum"],
            "legacy_count_duration_rate_retained": True,
        },
        "aggregation": {
            "primary_observation": "recording version + well; one well equals one organoid",
            "burst_rate": "mean per-unit burst rate within recording/well; zero-burst units retained",
            "conditional_metrics": "mean per-unit summaries among units for which the metric is defined",
        },
        "outputs": {key: str(value) for key, value in output_paths.items()} | {
            "figures": [str(path) for path in figure_paths],
            "firing_rate_method_comparison_figures": [
                str(path) for path in firing_rate_comparison_paths
            ],
            "panel_e_smoothed_rate_version_figures": {
                summary: [str(path) for path in paths]
                for summary, paths in smoothed_rate_panel_e_paths.items()
            },
        },
    }
    output_paths["provenance"].write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"SUA units: {len(units)}")
    print(f"Recording/well organoids: {len(wells)}")
    print(f"Dorsal/ventral organoids: {wells['region_call'].value_counts().to_dict()}")
    print(f"Accepted bursts: {len(bursts)}")
    print(f"Aligned class counts: {units['aligned_fs_rs_class'].value_counts().to_dict()}")
    print("\nRegion-level recording/well summary:")
    print(region_summary.to_string(index=False))
    print("\nFigures:")
    for path in figure_paths:
        print(path)
    print("\nFiring-rate method comparison figures:")
    for path in firing_rate_comparison_paths:
        print(path)
    print("\nPanel E smoothed-rate versions:")
    for temporal_summary, paths in smoothed_rate_panel_e_paths.items():
        print(temporal_summary)
        for path in paths:
            print(path)
    return 0


def _aggregate_recording_wells(units: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    group_columns = [
        "recording_well_id",
        "recording",
        "well",
        "organoid_well",
        "region_call",
        "region_source",
        "region_override_applied",
        "plate_id",
        "raw_variant",
        "recording_duration_s",
    ]
    for keys, group in units.groupby(group_columns, dropna=False, sort=True):
        row = dict(zip(group_columns, keys, strict=True))
        row.update(
            {
                "sua_unit_count": int(len(group)),
                "recording_well_has_sua": True,
                "fs_unit_count_aligned_0p50": int(group["aligned_fs_rs_class"].eq("FS").sum()),
                "rs_unit_count_aligned_0p50": int(group["aligned_fs_rs_class"].eq("RS").sum()),
                "mean_unit_firing_rate_hz": _mean(group["firing_rate_hz_recomputed"]),
                "median_unit_firing_rate_hz": _median(group["firing_rate_hz_recomputed"]),
                "summed_unit_firing_rate_hz": float(group["firing_rate_hz_recomputed"].sum()),
                "inverse_isi_gaussian_eligible_sua_unit_count": int(
                    group["inverse_isi_gaussian_eligible"].sum()
                ),
                "mean_unit_inverse_isi_gaussian_temporal_mean_hz": _mean(
                    group["inverse_isi_gaussian_temporal_mean_hz"]
                ),
                "mean_unit_inverse_isi_gaussian_temporal_median_hz": _mean(
                    group["inverse_isi_gaussian_temporal_median_hz"]
                ),
                "mean_unit_inverse_isi_gaussian_temporal_max_hz": _mean(
                    group["inverse_isi_gaussian_temporal_max_hz"]
                ),
                "mean_unit_burst_rate_per_min": _mean(group["burst_rate_per_min"]),
                "median_unit_burst_rate_per_min": _median(group["burst_rate_per_min"]),
                "total_unit_bursts": int(group["burst_count"].sum()),
                "burst_positive_unit_count": int(group["burst_positive"].sum()),
                "burst_positive_unit_fraction": float(group["burst_positive"].mean()),
                "mean_unit_firing_rate_within_bursts_hz": _mean(
                    group["mean_firing_rate_within_bursts_hz"]
                ),
                "units_contributing_within_burst_rate": _finite_count(
                    group["mean_firing_rate_within_bursts_hz"]
                ),
                "mean_unit_burst_duration_ms": _mean(group["mean_burst_duration_ms"]),
                "units_contributing_burst_duration": _finite_count(group["mean_burst_duration_ms"]),
                "mean_unit_interburst_interval_s": _mean(group["mean_interburst_interval_s"]),
                "units_contributing_interburst_interval": _finite_count(
                    group["mean_interburst_interval_s"]
                ),
                "mean_unit_spikes_per_burst": _mean(group["mean_spikes_per_burst"]),
                "units_contributing_spikes_per_burst": _finite_count(group["mean_spikes_per_burst"]),
                "mean_unit_fraction_spikes_in_bursts": _mean(group["fraction_spikes_in_bursts"]),
            }
        )
        rows.append(row)
    observed = pd.DataFrame(rows)
    missing = universe.loc[~universe["recording_well_id"].isin(observed["recording_well_id"])].copy()
    if not missing.empty:
        zero_columns: dict[str, int | float | bool] = {
            "sua_unit_count": 0,
            "recording_well_has_sua": False,
            "fs_unit_count_aligned_0p50": 0,
            "rs_unit_count_aligned_0p50": 0,
            "mean_unit_firing_rate_hz": np.nan,
            "median_unit_firing_rate_hz": np.nan,
            "summed_unit_firing_rate_hz": np.nan,
            "inverse_isi_gaussian_eligible_sua_unit_count": 0,
            "mean_unit_inverse_isi_gaussian_temporal_mean_hz": np.nan,
            "mean_unit_inverse_isi_gaussian_temporal_median_hz": np.nan,
            "mean_unit_inverse_isi_gaussian_temporal_max_hz": np.nan,
            "mean_unit_burst_rate_per_min": np.nan,
            "median_unit_burst_rate_per_min": np.nan,
            "total_unit_bursts": 0,
            "burst_positive_unit_count": 0,
            "burst_positive_unit_fraction": np.nan,
            "mean_unit_fraction_spikes_in_bursts": np.nan,
        }
        conditional_columns = [
            "mean_unit_firing_rate_within_bursts_hz",
            "mean_unit_burst_duration_ms",
            "mean_unit_interburst_interval_s",
            "mean_unit_spikes_per_burst",
        ]
        conditional_count_columns = [
            "units_contributing_within_burst_rate",
            "units_contributing_burst_duration",
            "units_contributing_interburst_interval",
            "units_contributing_spikes_per_burst",
        ]
        for column, value in zero_columns.items():
            missing[column] = value
        for column in conditional_columns:
            missing[column] = np.nan
        for column in conditional_count_columns:
            missing[column] = 0
        observed = pd.concat([observed, missing[observed.columns]], ignore_index=True)
    return observed.sort_values(["region_call", "recording", "well"]).reset_index(drop=True)


def _recording_well_universe(source: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "recording",
        "well",
        "region_call",
        "region_source",
        "region_override_applied",
        "plate_id",
        "raw_variant",
        "recording_duration_s",
    ]
    universe = source[columns].drop_duplicates().copy()
    universe["recording_well_id"] = universe["recording"].astype(str) + "|" + universe["well"].astype(str)
    universe["organoid_well"] = universe["well"].astype(str)
    if universe["recording_well_id"].duplicated().any():
        duplicated = universe.loc[universe["recording_well_id"].duplicated(False), "recording_well_id"].tolist()
        raise ValueError(f"Recording/well universe has conflicting metadata: {duplicated[:5]}")
    ordered = [
        "recording_well_id",
        "recording",
        "well",
        "organoid_well",
        "region_call",
        "region_source",
        "region_override_applied",
        "plate_id",
        "raw_variant",
        "recording_duration_s",
    ]
    return universe[ordered].sort_values(["region_call", "recording", "well"]).reset_index(drop=True)


def _aggregate_regions(wells: pd.DataFrame) -> pd.DataFrame:
    metrics = [
        "mean_unit_firing_rate_hz",
        "mean_unit_inverse_isi_gaussian_temporal_mean_hz",
        "mean_unit_inverse_isi_gaussian_temporal_median_hz",
        "mean_unit_inverse_isi_gaussian_temporal_max_hz",
        "mean_unit_burst_rate_per_min",
        "mean_unit_firing_rate_within_bursts_hz",
        "mean_unit_burst_duration_ms",
        "mean_unit_interburst_interval_s",
        "mean_unit_spikes_per_burst",
        "mean_unit_fraction_spikes_in_bursts",
    ]
    rows: list[dict[str, object]] = []
    for region in REGION_ORDER:
        group = wells.loc[wells["region_call"].eq(region)]
        row: dict[str, object] = {
            "region_call": region,
            "recording_well_organoid_count": int(len(group)),
            "sua_unit_count": int(group["sua_unit_count"].sum()),
        }
        for metric in metrics:
            values = pd.to_numeric(group[metric], errors="coerce").dropna().to_numpy(dtype=float)
            row[f"{metric}__n"] = int(values.size)
            row[f"{metric}__mean"] = float(np.mean(values)) if values.size else np.nan
            row[f"{metric}__median"] = float(np.median(values)) if values.size else np.nan
            row[f"{metric}__sem"] = _sem(values)
        rows.append(row)
    return pd.DataFrame(rows)


def _figure_source_data(wells: pd.DataFrame) -> pd.DataFrame:
    specs = _panel_specs()
    rows: list[dict[str, object]] = []
    id_columns = [
        "recording_well_id",
        "recording",
        "well",
        "organoid_well",
        "region_call",
        "plate_id",
        "raw_variant",
        "sua_unit_count",
    ]
    for panel, metric, title, ylabel in specs:
        for _, row in wells.iterrows():
            rows.append(
                {column: row[column] for column in id_columns}
                | {
                    "panel": panel,
                    "metric": metric,
                    "panel_title": title,
                    "y_label": ylabel,
                    "value": row[metric],
                }
            )
    return pd.DataFrame(rows)


def _firing_rate_comparison_source_data(wells: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    id_columns = [
        "recording_well_id",
        "recording",
        "well",
        "organoid_well",
        "region_call",
        "plate_id",
        "raw_variant",
        "sua_unit_count",
        "inverse_isi_gaussian_eligible_sua_unit_count",
    ]
    for metric, method, temporal_summary, title, ylabel in _firing_rate_comparison_specs():
        for _, row in wells.iterrows():
            rows.append(
                {column: row[column] for column in id_columns}
                | {
                    "metric": metric,
                    "method": method,
                    "temporal_summary": temporal_summary,
                    "panel_title": title,
                    "y_label": ylabel,
                    "value": row[metric],
                }
            )
    return pd.DataFrame(rows)


def _panel_e_smoothed_rate_versions_source_data(wells: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for temporal_summary, metric in _smoothed_rate_metrics().items():
        frame = _figure_source_data_from_specs(
            wells,
            _panel_specs_with_smoothed_rate(temporal_summary, metric),
        )
        frames.append(frame.assign(firing_rate_temporal_summary=temporal_summary))
    return pd.concat(frames, ignore_index=True)


def _figure_source_data_from_specs(
    wells: pd.DataFrame,
    specs: list[tuple[str, str, str, str]],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    id_columns = [
        "recording_well_id",
        "recording",
        "well",
        "organoid_well",
        "region_call",
        "plate_id",
        "raw_variant",
        "sua_unit_count",
        "inverse_isi_gaussian_eligible_sua_unit_count",
    ]
    for panel, metric, title, ylabel in specs:
        for _, row in wells.iterrows():
            rows.append(
                {column: row[column] for column in id_columns}
                | {
                    "panel": panel,
                    "metric": metric,
                    "panel_title": title,
                    "y_label": ylabel,
                    "value": row[metric],
                }
            )
    return pd.DataFrame(rows)


def _denominator_flow(
    source_all: pd.DataFrame,
    source_kslabel: pd.DataFrame,
    source_after_template: pd.DataFrame,
    source_after_contamination: pd.DataFrame,
    source: pd.DataFrame,
    template_excluded: pd.DataFrame,
    contamination_excluded: pd.DataFrame,
    refractory_excluded: pd.DataFrame,
    units: pd.DataFrame,
    wells: pd.DataFrame,
    lfp_excluded: pd.DataFrame,
    kslabel: str,
    min_template_ptp_uv: float | None,
    max_contam_pct: float | None,
    max_isi_lt_2ms_fraction: float | None,
) -> pd.DataFrame:
    rows = [
        ("all_current_cytoview_unit_rows", len(source_all), "all KS labels and recording versions"),
        ("explicit_lfp_like_rows_excluded", len(lfp_excluded), "exclude only explicit LFP/low-frequency rows"),
        (
            f"KSLabel_{kslabel}_rows_selected_before_template_filter",
            len(source_kslabel),
            "SUA is KSLabel=good for this run",
        ),
        (
            "weak_template_rows_excluded",
            len(template_excluded),
            (
                f"exclude template PTP < {min_template_ptp_uv:g} uV or undefined"
                if min_template_ptp_uv is not None
                else "no template-amplitude filter"
            ),
        ),
        (
            f"KSLabel_{kslabel}_rows_after_template_filter",
            len(source_after_template),
            "units entering contamination filter",
        ),
        (
            "high_contamination_rows_excluded",
            len(contamination_excluded),
            (
                f"exclude ContamPct > {max_contam_pct:g} or undefined"
                if max_contam_pct is not None
                else "no ContamPct filter"
            ),
        ),
        (
            f"KSLabel_{kslabel}_rows_after_contamination_filter",
            len(source_after_contamination),
            "units entering short-ISI filter",
        ),
        (
            "refractory_violation_rows_excluded",
            len(refractory_excluded),
            (
                f"exclude fraction of ISIs <2 ms > {max_isi_lt_2ms_fraction:g} or undefined"
                if max_isi_lt_2ms_fraction is not None
                else "no short-ISI filter"
            ),
        ),
        (
            f"KSLabel_{kslabel}_rows_after_all_quality_filters",
            len(source),
            "units entering spike-train and burst analysis",
        ),
        ("live_spike_train_rows_measured", len(units), "must match selected SUA rows"),
        ("all_non_lfp_recording_well_organoids", len(wells), "one well equals one organoid; no recording-kind filter"),
        ("recording_well_organoids_with_sua", int(wells["recording_well_has_sua"].sum()), "at least one KSLabel=good unit"),
        ("recording_well_organoids_with_no_sua", int((~wells["recording_well_has_sua"]).sum()), "retained with zero unconditional SUA activity"),
    ]
    return pd.DataFrame(rows, columns=["stage", "count", "rule"])


def _plot_panel_e(
    plt,
    Line2D,
    wells: pd.DataFrame,
    output_base: Path,
    *,
    parameters,
    export_formats: str,
    specs: list[tuple[str, str, str, str]] | None = None,
    method_note: str | None = None,
) -> list[Path]:
    specs = _panel_specs() if specs is None else specs
    fig, axes = plt.subplots(2, 3, figsize=(14.5, 8.8), constrained_layout=False)
    fig.patch.set_facecolor("white")
    rng = np.random.default_rng(20260710)
    for ax, (panel, metric, title, ylabel) in zip(axes.ravel(), specs, strict=True):
        ax.set_facecolor("white")
        for region_index, region in enumerate(REGION_ORDER):
            subset = wells.loc[wells["region_call"].eq(region)].copy()
            jitter = rng.uniform(-0.10, 0.10, size=len(subset))
            for point_index, (_, row) in enumerate(subset.iterrows()):
                value = float(row[metric]) if pd.notna(row[metric]) else np.nan
                if not np.isfinite(value):
                    continue
                marker = VARIANT_MARKERS.get(str(row["raw_variant"]), "D")
                ax.scatter(
                    region_index + jitter[point_index],
                    value,
                    s=42,
                    marker=marker,
                    facecolor=REGION_COLORS[region],
                    edgecolor="white",
                    linewidth=0.7,
                    alpha=0.82,
                    zorder=3,
                )
            values = pd.to_numeric(subset[metric], errors="coerce").dropna().to_numpy(dtype=float)
            if values.size:
                mean = float(np.mean(values))
                sem = _sem(values)
                ax.errorbar(
                    region_index,
                    mean,
                    yerr=sem if np.isfinite(sem) else None,
                    fmt="D",
                    markersize=6,
                    color="black",
                    markerfacecolor="white",
                    markeredgewidth=1.2,
                    capsize=4,
                    linewidth=1.3,
                    zorder=5,
                )
        counts = [
            int(
                pd.to_numeric(
                    wells.loc[wells["region_call"].eq(region), metric],
                    errors="coerce",
                )
                .notna()
                .sum()
            )
            for region in REGION_ORDER
        ]
        ax.set_xticks([0, 1], [f"Dorsal\nn={counts[0]}", f"Ventral\nn={counts[1]}"])
        ax.set_xlim(-0.38, 1.38)
        ax.set_ylabel(ylabel)
        ax.set_title(f"{panel}  {title}", loc="left", fontsize=11, fontweight="bold")
        ax.grid(axis="y", color="#D9D9D9", linewidth=0.8, alpha=0.8)
        ax.spines[["top", "right"]].set_visible(False)

    variant_handles = [
        Line2D(
            [0],
            [0],
            marker=marker,
            linestyle="none",
            markerfacecolor="#777777",
            markeredgecolor="white",
            markersize=7,
            label=label,
        )
        for label, marker in VARIANT_MARKERS.items()
    ]
    mean_handle = Line2D(
        [0], [0], marker="D", linestyle="none", markerfacecolor="white", markeredgecolor="black", label="Mean +/- SEM"
    )
    fig.legend(handles=variant_handles + [mean_handle], loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.945))
    fig.suptitle(
        "SUA spontaneous activity in dorsal and ventral forebrain organoids",
        fontsize=15,
        fontweight="bold",
        y=0.995,
    )
    fig.text(
        0.5,
        0.955,
        (
            f"KSLabel=good; each point is one recording/well organoid; spike-bearing versions remain separate; "
            f"bursts: ISI <= {parameters.max_isi_ms:g} ms, >= {parameters.min_spikes} spikes, "
            f"duration >= {parameters.min_duration_ms:g} ms"
            + (f"; {method_note}" if method_note else "")
        ),
        ha="center",
        va="top",
        fontsize=9,
    )
    fig.tight_layout(rect=(0.02, 0.03, 0.98, 0.91), h_pad=2.0, w_pad=2.0)
    output_paths: list[Path] = []
    for suffix in [item.strip().lower() for item in export_formats.split(",") if item.strip()]:
        path = output_base.with_suffix(f".{suffix}")
        save_args = {"bbox_inches": "tight", "facecolor": "white", "transparent": False}
        if suffix == "png":
            save_args["dpi"] = 300
        fig.savefig(path, **save_args)
        output_paths.append(path)
    plt.close(fig)
    return output_paths


def _plot_firing_rate_comparison(
    plt,
    Line2D,
    wells: pd.DataFrame,
    output_base: Path,
    *,
    gaussian_sigma_ms: float,
    evaluation_bin_ms: float,
    min_spikes: int,
    quality_filter_note: str,
    export_formats: str,
) -> list[Path]:
    specs = _firing_rate_comparison_specs()
    fig, axes = plt.subplots(2, 2, figsize=(10.6, 8.8), constrained_layout=False)
    fig.patch.set_facecolor("white")
    rng = np.random.default_rng(20260710)
    for ax, (metric, _, _, title, ylabel) in zip(axes.ravel(), specs, strict=True):
        ax.set_facecolor("white")
        for region_index, region in enumerate(REGION_ORDER):
            subset = wells.loc[wells["region_call"].eq(region)].copy()
            jitter = rng.uniform(-0.10, 0.10, size=len(subset))
            for point_index, (_, row) in enumerate(subset.iterrows()):
                value = float(row[metric]) if pd.notna(row[metric]) else np.nan
                if not np.isfinite(value):
                    continue
                ax.scatter(
                    region_index + jitter[point_index],
                    value,
                    s=42,
                    marker=VARIANT_MARKERS.get(str(row["raw_variant"]), "D"),
                    facecolor=REGION_COLORS[region],
                    edgecolor="white",
                    linewidth=0.7,
                    alpha=0.82,
                    zorder=3,
                )
            values = pd.to_numeric(subset[metric], errors="coerce").dropna().to_numpy(dtype=float)
            if values.size:
                mean = float(np.mean(values))
                sem = _sem(values)
                ax.errorbar(
                    region_index,
                    mean,
                    yerr=sem if np.isfinite(sem) else None,
                    fmt="D",
                    markersize=6,
                    color="black",
                    markerfacecolor="white",
                    markeredgewidth=1.2,
                    capsize=4,
                    linewidth=1.3,
                    zorder=5,
                )
        counts = [
            int(
                pd.to_numeric(
                    wells.loc[wells["region_call"].eq(region), metric], errors="coerce"
                ).notna().sum()
            )
            for region in REGION_ORDER
        ]
        ax.set_xticks([0, 1], [f"Dorsal\nn={counts[0]}", f"Ventral\nn={counts[1]}"])
        ax.set_xlim(-0.38, 1.38)
        ax.set_ylabel(ylabel)
        ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
        ax.grid(axis="y", color="#D9D9D9", linewidth=0.8, alpha=0.8)
        ax.spines[["top", "right"]].set_visible(False)

    variant_handles = [
        Line2D(
            [0], [0], marker=marker, linestyle="none", markerfacecolor="#777777",
            markeredgecolor="white", markersize=7, label=label,
        )
        for label, marker in VARIANT_MARKERS.items()
    ]
    mean_handle = Line2D(
        [0], [0], marker="D", linestyle="none", markerfacecolor="white",
        markeredgecolor="black", label="Regional mean +/- SEM",
    )
    fig.legend(
        handles=variant_handles + [mean_handle],
        loc="upper center",
        ncol=4,
        frameon=False,
        bbox_to_anchor=(0.5, 0.94),
    )
    fig.suptitle(
        "Comparison of SUA firing-rate quantification methods",
        fontsize=15,
        fontweight="bold",
        y=0.995,
    )
    fig.text(
        0.5,
        0.955,
        (
            "Each point is one recording/well organoid; legacy count/duration retained; "
            f"inverse-ISI trace requires >= {min_spikes} spikes, Gaussian sigma = "
            f"{gaussian_sigma_ms:g} ms, evaluation bin = {evaluation_bin_ms:g} ms"
            + (f"; {quality_filter_note}" if quality_filter_note else "")
        ),
        ha="center",
        va="top",
        fontsize=9,
    )
    fig.tight_layout(rect=(0.02, 0.03, 0.98, 0.90), h_pad=2.0, w_pad=2.0)
    output_paths: list[Path] = []
    for suffix in [item.strip().lower() for item in export_formats.split(",") if item.strip()]:
        path = output_base.with_suffix(f".{suffix}")
        save_args = {"bbox_inches": "tight", "facecolor": "white", "transparent": False}
        if suffix == "png":
            save_args["dpi"] = 300
        fig.savefig(path, **save_args)
        output_paths.append(path)
    plt.close(fig)
    return output_paths


def _panel_specs() -> list[tuple[str, str, str, str]]:
    return [
        ("E1", "mean_unit_firing_rate_hz", "Overall mean firing rate", "Mean SUA firing rate (Hz)"),
        ("E2", "mean_unit_burst_rate_per_min", "Burst rate", "Mean SUA burst rate (bursts/min)"),
        (
            "E3",
            "mean_unit_firing_rate_within_bursts_hz",
            "Firing rate within bursts",
            "Mean within-burst firing rate (Hz)",
        ),
        ("E4", "mean_unit_burst_duration_ms", "Burst duration", "Mean burst duration (ms)"),
        (
            "E5",
            "mean_unit_interburst_interval_s",
            "Inter-burst interval",
            "Mean inter-burst interval (s)",
        ),
        ("E6", "mean_unit_spikes_per_burst", "Spikes per burst", "Mean spikes per burst"),
    ]


def _smoothed_rate_metrics() -> dict[str, str]:
    return {
        "mean": "mean_unit_inverse_isi_gaussian_temporal_mean_hz",
        "median": "mean_unit_inverse_isi_gaussian_temporal_median_hz",
        "maximum": "mean_unit_inverse_isi_gaussian_temporal_max_hz",
    }


def _panel_specs_with_smoothed_rate(
    temporal_summary: str,
    metric: str,
) -> list[tuple[str, str, str, str]]:
    return [
        (
            "E1",
            metric,
            f"Overall firing rate\nSmoothed inverse-ISI: {temporal_summary}",
            f"SUA temporal {temporal_summary} firing rate (Hz)",
        ),
        *_panel_specs()[1:],
    ]


def _firing_rate_comparison_specs() -> list[tuple[str, str, str, str, str]]:
    return [
        (
            "mean_unit_firing_rate_hz",
            "spike_count_divided_by_recording_duration",
            "global_mean",
            "Legacy: spike count / duration",
            "Mean SUA firing rate (Hz)",
        ),
        (
            "mean_unit_inverse_isi_gaussian_temporal_mean_hz",
            "inverse_isi_gaussian_sigma_50ms",
            "temporal_mean",
            "Smoothed inverse-ISI: temporal mean",
            "Mean SUA firing rate (Hz)",
        ),
        (
            "mean_unit_inverse_isi_gaussian_temporal_median_hz",
            "inverse_isi_gaussian_sigma_50ms",
            "temporal_median",
            "Smoothed inverse-ISI: temporal median",
            "Median SUA firing rate (Hz)",
        ),
        (
            "mean_unit_inverse_isi_gaussian_temporal_max_hz",
            "inverse_isi_gaussian_sigma_50ms",
            "temporal_maximum",
            "Smoothed inverse-ISI: temporal maximum",
            "Maximum SUA firing rate (Hz)",
        ),
    ]


def _is_lfp_like_row(row: pd.Series) -> bool:
    # Do not infer recording inclusion from recording names. A row is excluded
    # only when the explicit raw_variant metadata says it is LFP/low-frequency.
    raw_variant = str(row.get("raw_variant", "")).strip().lower()
    return raw_variant in {
        "lfp",
        "lfp_raw",
        "low_frequency",
        "low_frequency_raw",
        "median_downsampled_lfp",
    }


def _unit_key(row: pd.Series) -> str:
    return f"{row['recording']}|{row['well']}|{_unit_id_text(row['unit_id'])}"


def _unit_id_text(value: object) -> str:
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return str(value)


def _quality_filter_note(
    minimum_template_ptp_uV: float | None,
    maximum_contam_pct: float | None,
    maximum_isi_lt_2ms_fraction: float | None,
) -> str:
    rules: list[str] = []
    if minimum_template_ptp_uV is not None:
        rules.append(f"template PTP >= {minimum_template_ptp_uV:g} uV")
    if maximum_contam_pct is not None:
        rules.append(f"ContamPct <= {maximum_contam_pct:g}%")
    if maximum_isi_lt_2ms_fraction is not None:
        rules.append(f"ISIs <2 ms <= {100 * maximum_isi_lt_2ms_fraction:g}%")
    return "; ".join(rules)


def _mean(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    return float(np.mean(values)) if values.size else np.nan


def _median(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    return float(np.median(values)) if values.size else np.nan


def _finite_count(series: pd.Series) -> int:
    return int(np.isfinite(pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)).sum())


def _sem(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return np.nan
    return float(np.std(values, ddof=1) / math.sqrt(values.size))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_output(arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or result.stderr.strip()


if __name__ == "__main__":
    raise SystemExit(main())
