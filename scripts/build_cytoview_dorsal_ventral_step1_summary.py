#!/usr/bin/env python
"""Build current Step 1 Cytoview dorsal/ventral unit summaries.

This script intentionally uses Step 1 assets only:

- current Step 1 well ledger
- current Step 1 SortingAnalyzer outputs
- Cytoview dorsal/ventral batch/plate-map plan

It does not read downstream/IAN master tables. Firing rate and ISI metrics are
computed directly from Step 1 spike trains. TTP/FS/RS is computed directly from
Step 1 ``templates.average`` best-PTP-channel waveforms using the current
SpikeTurnpike-compatible landmark logic.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.launch_step1_sorting_analyzer_browser import DEFAULT_AIND_RESULTS_ROOT  # noqa: E402
from scripts.plot_lumos_candidate_waveform_gallery import (  # noqa: E402
    _measure_spiketurnpike_waveform_metrics,
)


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_DATE_LABEL = "20260709"
RECORDING_NAME = "block0_None_recording1.zarr"
CLASS_ORDER = ["FS_like", "borderline", "RS_like", "unknown"]
REGION_ORDER = ["dorsal", "ventral", "unknown"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_AIND_RESULTS_ROOT)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--rep-fraction", type=float, choices=(0.25, 0.5, 0.63), default=0.5)
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import spikeinterface.full as si

    job_dir = args.job_dir.expanduser().resolve()
    results_root = args.results_root.expanduser().resolve()
    ground_truth_path = job_dir / "step1_v5_well_ground_truth.csv"
    region_plan_path = job_dir / f"cytoview_platemap_dorsal_ventral_priority_{args.date_label}.csv"
    batch_plan_path = job_dir / f"cytoview_platemap_dorsal_ventral_priority_{args.date_label}_batch_plan.csv"
    override_path = job_dir / f"cytoview_dorsal_ventral_region_overrides_{args.date_label}.csv"

    ground_truth = pd.read_csv(ground_truth_path)
    region_map = _load_region_map(region_plan_path, batch_plan_path)
    region_overrides = _load_region_overrides(override_path)
    cytoview = ground_truth.loc[ground_truth["plate_family"].astype(str).eq("cytoview_6well")].copy()
    ready = cytoview.loc[_truthy_series(cytoview["gui_analyzer_ready"])].copy()
    ready = ready.sort_values(["recording", "well"]).reset_index(drop=True)

    rows: list[dict[str, object]] = []
    errors: list[str] = []
    for _, well_row in ready.iterrows():
        analyzer_path = (
            results_root
            / str(well_row["recording"])
            / str(well_row["well"])
            / "postprocessed"
            / RECORDING_NAME
        )
        try:
            rows.extend(
                _rows_for_analyzer(
                    si,
                    well_row,
                    analyzer_path,
                    region_map=region_map,
                    region_overrides=region_overrides,
                    rep_fraction=args.rep_fraction,
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                f"{well_row.get('recording')} / {well_row.get('well')}: "
                f"{type(exc).__name__}: {exc}"
            )

    if not rows:
        raise SystemExit("No units could be measured from current GUI-ready Cytoview Step 1 analyzers.")

    units = pd.DataFrame(rows)
    status = _status_summary(cytoview, ready, units, errors, region_map, region_overrides)
    well_summary = _well_summary(units, ready)
    region_summary = _region_summary(units)
    per_well_fraction_summary = _per_well_class_fraction_summary(well_summary)

    stem = f"cytoview_dorsal_ventral_step1_{args.date_label}"
    unit_csv = job_dir / f"{stem}_unit_metrics.csv"
    well_csv = job_dir / f"{stem}_well_summary.csv"
    region_csv = job_dir / f"{stem}_region_summary.csv"
    per_well_fraction_csv = job_dir / f"{stem}_per_well_class_fraction_summary.csv"
    status_csv = job_dir / f"{stem}_asset_status.csv"
    figure_png = job_dir / f"{stem}_current_good_units.png"
    provenance_json = job_dir / f"{stem}_provenance.json"
    error_path = job_dir / f"{stem}_errors.txt"

    units.to_csv(unit_csv, index=False)
    well_summary.to_csv(well_csv, index=False)
    region_summary.to_csv(region_csv, index=False)
    per_well_fraction_summary.to_csv(per_well_fraction_csv, index=False)
    status.to_csv(status_csv, index=False)
    _plot_current_good_units(plt, units, figure_png)
    if errors:
        error_path.write_text("\n".join(errors) + "\n", encoding="utf-8")

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "ground_truth_csv": str(ground_truth_path),
        "region_plan_csv": str(region_plan_path),
        "batch_plan_csv": str(batch_plan_path),
        "region_override_csv": str(override_path) if override_path.exists() else "",
        "region_override_rows": int(len(region_overrides)),
        "step1_only": True,
        "cytoview_well_rows": int(len(cytoview)),
        "gui_ready_cytoview_wells_scanned": int(len(ready)),
        "unit_rows": int(len(units)),
        "good_unit_rows": int(units["KSLabel"].astype(str).str.lower().eq("good").sum()),
        "outputs": {
            "unit_metrics_csv": str(unit_csv),
            "well_summary_csv": str(well_csv),
            "region_summary_csv": str(region_csv),
            "per_well_class_fraction_summary_csv": str(per_well_fraction_csv),
            "asset_status_csv": str(status_csv),
            "figure_png": str(figure_png),
        },
        "notes": [
            "No downstream/IAN master tables are used as inputs.",
            "A wells are ventral and B wells are dorsal when exact plan rows are unavailable.",
            "Manual region overrides are applied after the plan/fallback mapping.",
            "Main biological summaries should focus on KSLabel=good units.",
            "Rows reflect only Cytoview wells with currently GUI-ready Step 1 analyzers.",
        ],
        "errors": errors,
    }
    provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Cytoview Step 1 rows in ledger: {len(cytoview)}")
    print(f"GUI-ready Cytoview wells scanned: {len(ready)}")
    print(f"Unit rows measured: {len(units)}")
    print(f"KSLabel=good rows: {units['KSLabel'].astype(str).str.lower().eq('good').sum()}")
    print(f"Unit metrics CSV: {unit_csv}")
    print(f"Well summary CSV: {well_csv}")
    print(f"Region summary CSV: {region_csv}")
    print(f"Per-well class fraction summary CSV: {per_well_fraction_csv}")
    print(f"Asset status CSV: {status_csv}")
    print(f"Figure PNG: {figure_png}")
    print(f"Provenance: {provenance_json}")
    print(f"Region override rows loaded: {len(region_overrides)}")
    if errors:
        print(f"Skipped {len(errors)} analyzer(s); details: {error_path}")
    print("\nCurrent KSLabel=good region summary:")
    print(region_summary.to_string(index=False))


def _rows_for_analyzer(
    si,
    well_row: pd.Series,
    analyzer_path: Path,
    *,
    region_map: dict[tuple[str, str], dict[str, object]],
    region_overrides: list[dict[str, str]],
    rep_fraction: float,
) -> list[dict[str, object]]:
    analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
    sorting = analyzer.sorting
    unit_ids = list(sorting.get_unit_ids())
    templates_ext = analyzer.get_extension("templates")
    if templates_ext is None:
        raise ValueError("missing templates extension")
    templates = _templates_average(templates_ext)
    if templates.ndim != 3:
        raise ValueError(f"expected templates units x samples x channels, found {templates.shape}")
    if templates.shape[0] != len(unit_ids):
        raise ValueError(f"template unit count {templates.shape[0]} does not match unit count {len(unit_ids)}")

    sampling_frequency = float(analyzer.recording.get_sampling_frequency())
    duration_s = _recording_duration_s(analyzer)
    kslabels = _unit_property_array(sorting, "KSLabel", unit_ids, default="")
    contam_pct = _unit_property_array(sorting, "ContamPct", unit_ids, default=np.nan)
    amplitudes = _unit_property_array(sorting, "Amplitude", unit_ids, default=np.nan)

    recording = str(well_row["recording"])
    well = str(well_row["well"])
    region_info = _region_info_for_well(recording, well, region_map, region_overrides)
    out: list[dict[str, object]] = []
    for unit_index, unit_id in enumerate(unit_ids):
        template = np.asarray(templates[unit_index], dtype=float)
        if template.ndim != 2 or not np.isfinite(template).any():
            continue
        channel_ptp = np.ptp(template, axis=0)
        if not np.isfinite(channel_ptp).any():
            continue
        best_channel_index = int(np.nanargmax(channel_ptp))
        best_waveform = template[:, best_channel_index]
        nbefore = int(getattr(templates_ext, "nbefore", np.nanargmin(best_waveform)))
        time_ms = (np.arange(template.shape[0]) - nbefore) / sampling_frequency * 1000.0
        waveform_metrics = _measure_spiketurnpike_waveform_metrics(
            best_waveform,
            time_ms,
            rep_fraction=rep_fraction,
        )
        spike_train = np.asarray(sorting.get_unit_spike_train(unit_id=unit_id), dtype=float)
        isi = _isi_metrics(spike_train, sampling_frequency)
        spike_count = int(spike_train.size)
        firing_rate_hz = spike_count / duration_s if duration_s > 0 else np.nan
        out.append(
            {
                "recording": recording,
                "well": well,
                "region_call": region_info["region_call"],
                "region_source": region_info["region_source"],
                "original_region_call": region_info["original_region_call"],
                "region_override_applied": region_info["region_override_applied"],
                "region_override_reason": region_info["region_override_reason"],
                "plate_id": region_info.get("plate_id", ""),
                "planned_cytoview_batch": region_info.get("planned_cytoview_batch", np.nan),
                "raw_variant": str(well_row.get("raw_variant", "")),
                "ground_truth_status": str(well_row.get("ground_truth_status", "")),
                "unit_id": unit_id,
                "unit_index": unit_index,
                "KSLabel": _normalize_label(kslabels[unit_index]),
                "ContamPct": _safe_float(contam_pct[unit_index]),
                "Amplitude": _safe_float(amplitudes[unit_index]),
                "spike_count": spike_count,
                "recording_duration_s": duration_s,
                "firing_rate_hz": firing_rate_hz,
                **isi,
                "template_reference": f"templates.average[unit_index={unit_index},channel_index={best_channel_index}]",
                "best_channel_index": best_channel_index,
                "template_ptp_best_channel_uV": float(np.ptp(best_waveform)),
                "template_trough_best_channel_uV": float(np.nanmin(best_waveform)),
                "template_peak_best_channel_uV": float(np.nanmax(best_waveform)),
                "trough_to_peak_duration_ms": waveform_metrics["trough_to_peak_duration_ms"],
                "rs_fs_classification": waveform_metrics["tentative_rs_fs_classification"],
                "repolarization_time_ms": waveform_metrics["repolarization_time_ms"],
                "analyzer_path": str(analyzer_path),
            }
        )
    return out


def _load_region_map(*paths: Path) -> dict[tuple[str, str], dict[str, object]]:
    region_map: dict[tuple[str, str], dict[str, object]] = {}
    for path in paths:
        if not path.exists():
            continue
        table = pd.read_csv(path)
        required = {"recording", "well", "region_call"}
        if not required.issubset(table.columns):
            continue
        for _, row in table.iterrows():
            key = (str(row["recording"]), str(row["well"]))
            region_map[key] = {
                "region_call": str(row["region_call"]),
                "region_source": str(path.name),
                "plate_id": str(row.get("plate_id", "")),
                "planned_cytoview_batch": row.get("planned_cytoview_batch", np.nan),
            }
    return region_map


def _load_region_overrides(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    table = pd.read_csv(path).fillna("")
    required = {"recording_contains", "well", "region_call_override", "reason"}
    if not required.issubset(table.columns):
        raise ValueError(f"region override CSV missing required columns: {path}")
    overrides: list[dict[str, str]] = []
    for _, row in table.iterrows():
        overrides.append(
            {
                "recording_contains": str(row["recording_contains"]),
                "well": str(row["well"]).upper(),
                "region_call_override": str(row["region_call_override"]),
                "reason": str(row["reason"]),
            }
        )
    return overrides


def _region_info_for_well(
    recording: str,
    well: str,
    region_map: dict[tuple[str, str], dict[str, object]],
    region_overrides: list[dict[str, str]],
) -> dict[str, object]:
    info = dict(region_map.get((recording, well), _fallback_region_info(well)))
    info["original_region_call"] = info["region_call"]
    info["region_override_applied"] = False
    info["region_override_reason"] = ""
    well_upper = str(well).upper()
    for override in region_overrides:
        if override["well"] != well_upper:
            continue
        if override["recording_contains"] not in str(recording):
            continue
        info["region_call"] = override["region_call_override"]
        info["region_source"] = "manual_region_override_after_plan"
        info["region_override_applied"] = True
        info["region_override_reason"] = override["reason"]
        break
    return info


def _fallback_region_info(well: str) -> dict[str, object]:
    well = str(well).upper()
    if well.startswith("A"):
        region = "ventral"
    elif well.startswith("B"):
        region = "dorsal"
    else:
        region = "unknown"
    return {
        "region_call": region,
        "region_source": "well_row_fallback_A_ventral_B_dorsal",
        "original_region_call": region,
        "region_override_applied": False,
        "region_override_reason": "",
        "plate_id": "",
        "planned_cytoview_batch": np.nan,
    }


def _recording_duration_s(analyzer) -> float:
    recording = analyzer.recording
    sampling_frequency = float(recording.get_sampling_frequency())
    try:
        total_samples = sum(
            recording.get_num_samples(segment_index=index)
            for index in range(recording.get_num_segments())
        )
    except TypeError:
        total_samples = recording.get_num_samples()
    return float(total_samples) / sampling_frequency if sampling_frequency > 0 else np.nan


def _isi_metrics(spike_train: np.ndarray, sampling_frequency: float) -> dict[str, object]:
    if spike_train.size < 2 or sampling_frequency <= 0:
        return {
            "isi_count": max(int(spike_train.size) - 1, 0),
            "isi_median_ms": np.nan,
            "isi_mean_ms": np.nan,
            "isi_cv": np.nan,
            "isi_lt_2ms_count": 0,
            "isi_lt_2ms_fraction": np.nan,
        }
    isi_ms = np.diff(np.sort(spike_train)) / sampling_frequency * 1000.0
    mean = float(np.nanmean(isi_ms)) if isi_ms.size else np.nan
    std = float(np.nanstd(isi_ms, ddof=1)) if isi_ms.size > 1 else np.nan
    return {
        "isi_count": int(isi_ms.size),
        "isi_median_ms": float(np.nanmedian(isi_ms)) if isi_ms.size else np.nan,
        "isi_mean_ms": mean,
        "isi_cv": std / mean if np.isfinite(std) and np.isfinite(mean) and mean > 0 else np.nan,
        "isi_lt_2ms_count": int(np.sum(isi_ms < 2.0)),
        "isi_lt_2ms_fraction": float(np.mean(isi_ms < 2.0)) if isi_ms.size else np.nan,
    }


def _status_summary(
    cytoview: pd.DataFrame,
    ready: pd.DataFrame,
    units: pd.DataFrame,
    errors: list[str],
    region_map: dict[tuple[str, str], dict[str, object]],
    region_overrides: list[dict[str, str]],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    rows.extend(
        [
            {"section": "asset_status", "metric": "cytoview_ledger_rows", "group": "all", "value": int(len(cytoview))},
            {"section": "asset_status", "metric": "cytoview_gui_ready_rows", "group": "all", "value": int(len(ready))},
            {"section": "asset_status", "metric": "step1_unit_rows_measured", "group": "all", "value": int(len(units))},
            {
                "section": "asset_status",
                "metric": "step1_good_unit_rows_measured",
                "group": "all",
                "value": int(units["KSLabel"].astype(str).str.lower().eq("good").sum()),
            },
            {"section": "asset_status", "metric": "analyzer_load_errors", "group": "all", "value": int(len(errors))},
            {"section": "asset_status", "metric": "region_map_rows", "group": "all", "value": int(len(region_map))},
            {"section": "asset_status", "metric": "region_override_rules", "group": "all", "value": int(len(region_overrides))},
            {
                "section": "asset_status",
                "metric": "unit_rows_with_region_override",
                "group": "all",
                "value": int(units["region_override_applied"].astype(bool).sum()),
            },
        ]
    )
    for status, count in cytoview["ground_truth_status"].value_counts(dropna=False).items():
        rows.append({"section": "ledger", "metric": "ground_truth_status", "group": str(status), "value": int(count)})
    for label, count in units["KSLabel"].value_counts(dropna=False).items():
        rows.append({"section": "units", "metric": "kslabel", "group": str(label), "value": int(count)})
    ready_regions = ready.assign(
        region_call=ready.apply(
            lambda row: _region_info_for_well(
                str(row["recording"]),
                str(row["well"]),
                region_map,
                region_overrides,
            )["region_call"],
            axis=1,
        )
    )
    for region, count in ready_regions["region_call"].value_counts(dropna=False).items():
        rows.append({"section": "ready_wells", "metric": "region_call", "group": str(region), "value": int(count)})
    return pd.DataFrame(rows)


def _well_summary(units: pd.DataFrame, ready: pd.DataFrame) -> pd.DataFrame:
    good = units.loc[units["KSLabel"].astype(str).str.lower().eq("good")].copy()
    rows: list[dict[str, object]] = []
    for (recording, well), group in units.groupby(["recording", "well"], dropna=False):
        good_group = good.loc[good["recording"].eq(recording) & good["well"].eq(well)]
        region = str(group["region_call"].iloc[0]) if not group.empty else "unknown"
        row = {
            "recording": recording,
            "well": well,
            "region_call": region,
            "all_unit_count": int(len(group)),
            "good_unit_count": int(len(good_group)),
            "good_median_firing_rate_hz": _median(good_group["firing_rate_hz"]),
            "good_mean_firing_rate_hz": _mean(good_group["firing_rate_hz"]),
            "good_median_isi_ms": _median(good_group["isi_median_ms"]),
        }
        for label in CLASS_ORDER:
            row[f"good_{label}_count"] = int(good_group["rs_fs_classification"].eq(label).sum())
        denom = row["good_unit_count"]
        row["good_FS_like_fraction"] = row["good_FS_like_count"] / denom if denom else np.nan
        row["good_RS_like_fraction"] = row["good_RS_like_count"] / denom if denom else np.nan
        row["good_borderline_fraction"] = row["good_borderline_count"] / denom if denom else np.nan
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["region_call", "recording", "well"]).reset_index(drop=True)


def _region_summary(units: pd.DataFrame) -> pd.DataFrame:
    good = units.loc[units["KSLabel"].astype(str).str.lower().eq("good")].copy()
    rows: list[dict[str, object]] = []
    for region in REGION_ORDER:
        subset = good.loc[good["region_call"].eq(region)].copy()
        if subset.empty and region == "unknown":
            continue
        row = {
            "region_call": region,
            "good_unit_count": int(len(subset)),
            "recording_count": int(subset["recording"].nunique()) if not subset.empty else 0,
            "well_count": int(subset[["recording", "well"]].drop_duplicates().shape[0]) if not subset.empty else 0,
            "median_firing_rate_hz": _median(subset["firing_rate_hz"]),
            "mean_firing_rate_hz": _mean(subset["firing_rate_hz"]),
            "median_isi_ms": _median(subset["isi_median_ms"]),
            "median_ttp_ms": _median(subset["trough_to_peak_duration_ms"]),
        }
        for label in CLASS_ORDER:
            row[f"{label}_count"] = int(subset["rs_fs_classification"].eq(label).sum())
        denom = row["good_unit_count"]
        row["FS_like_fraction"] = row["FS_like_count"] / denom if denom else np.nan
        row["borderline_fraction"] = row["borderline_count"] / denom if denom else np.nan
        row["RS_like_fraction"] = row["RS_like_count"] / denom if denom else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _plot_current_good_units(plt, units: pd.DataFrame, output_path: Path) -> None:
    good = units.loc[units["KSLabel"].astype(str).str.lower().eq("good")].copy()
    if good.empty:
        return
    colors = {"FS_like": "#d55e00", "borderline": "#777777", "RS_like": "#0072b2", "unknown": "#bbbbbb"}
    region_colors = {"dorsal": "#2a9d8f", "ventral": "#6a4c93", "unknown": "#888888"}
    region_summary = _region_summary(units)
    well_summary = _well_summary(units, good)
    region_summary = region_summary.loc[region_summary["region_call"].isin(REGION_ORDER)].copy()

    fig, axes = plt.subplots(2, 2, figsize=(12.8, 9.2))
    axes = axes.ravel()

    # FS/borderline/RS proportions among KSLabel=good units.
    x = np.arange(len(region_summary))
    bottom = np.zeros(len(region_summary))
    for label in ["FS_like", "borderline", "RS_like"]:
        values = region_summary[f"{label}_fraction"].fillna(0.0).to_numpy()
        axes[0].bar(x, values, bottom=bottom, color=colors[label], label=label)
        for xi, yi, bi, count in zip(x, values, bottom, region_summary[f"{label}_count"], strict=False):
            if yi >= 0.055:
                axes[0].text(
                    xi,
                    bi + yi / 2.0,
                    f"{int(count)}\n{yi:.0%}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white" if label != "borderline" else "black",
                )
        bottom += values
    axes[0].set_xticks(
        x,
        [
            f"{row.region_call}\n{int(row.good_unit_count)} good units\n{int(row.well_count)} wells"
            for row in region_summary.itertuples()
        ],
    )
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("Fraction of KSLabel=good units")
    axes[0].set_title("FS/borderline/RS proportions")
    axes[0].legend(frameon=False, fontsize=8)

    # Good-unit yield per GUI-ready well.
    yield_ymax = float(well_summary["good_unit_count"].max()) + 3.0
    for region_index, region in enumerate(region_summary["region_call"]):
        subset = well_summary.loc[well_summary["region_call"].eq(region), "good_unit_count"].dropna()
        if subset.empty:
            continue
        all_region_units = units.loc[units["region_call"].eq(region)]
        good_region_units = good.loc[good["region_call"].eq(region)]
        good_fraction = len(good_region_units) / len(all_region_units) if len(all_region_units) else np.nan
        jitter = _deterministic_jitter(len(subset), width=0.12)
        axes[1].scatter(
            np.full(len(subset), region_index) + jitter,
            subset,
            s=34,
            alpha=0.72,
            color=region_colors.get(str(region), "#888888"),
            edgecolor="white",
            linewidth=0.4,
        )
        axes[1].hlines(
            subset.median(),
            region_index - 0.23,
            region_index + 0.23,
            color="black",
            linewidth=2,
            label="median" if region_index == 0 else None,
        )
        axes[1].text(
            region_index,
            yield_ymax - 0.15,
            f"good/all sorted {good_fraction:.0%}\nmedian/well {subset.median():.1f}\nmean/well {subset.mean():.1f}",
            ha="center",
            va="top",
            fontsize=8,
        )
    axes[1].set_xticks(np.arange(len(region_summary)), region_summary["region_call"])
    axes[1].set_ylim(-0.5, yield_ymax)
    axes[1].set_ylabel("KSLabel=good units per well")
    axes[1].set_title("Good-unit yield and good/all-sorted fraction")
    axes[1].grid(axis="y", color="0.9")

    # Overall firing-rate distribution across all KSLabel=good units.
    for region, subset in good.groupby("region_call", dropna=False):
        region_index = REGION_ORDER.index(region) if region in REGION_ORDER else len(REGION_ORDER) - 1
        jitter = _deterministic_jitter(len(subset), width=0.16)
        axes[2].scatter(
            np.full(len(subset), region_index) + jitter,
            subset["firing_rate_hz"],
            s=20,
            alpha=0.62,
            color=region_colors.get(str(region), "#888888"),
            edgecolor="none",
        )
        median = pd.to_numeric(subset["firing_rate_hz"], errors="coerce").median()
        axes[2].hlines(median, region_index - 0.26, region_index + 0.26, color="black", linewidth=2)
    axes[2].set_xticks(np.arange(len(region_summary)), region_summary["region_call"])
    axes[2].set_ylabel("Firing rate (Hz)")
    axes[2].set_title("All KSLabel=good firing rates")
    axes[2].grid(axis="y", color="0.9")

    # Mean and median firing-rate summaries.
    bar_width = 0.34
    mean_values = region_summary["mean_firing_rate_hz"].to_numpy(dtype=float)
    median_values = region_summary["median_firing_rate_hz"].to_numpy(dtype=float)
    axes[3].bar(x - bar_width / 2, median_values, width=bar_width, color="#4c78a8", label="median")
    axes[3].bar(x + bar_width / 2, mean_values, width=bar_width, color="#f58518", label="mean")
    for xi, median_value, mean_value in zip(x, median_values, mean_values, strict=False):
        axes[3].text(xi - bar_width / 2, median_value, f"{median_value:.2f}", ha="center", va="bottom", fontsize=8)
        axes[3].text(xi + bar_width / 2, mean_value, f"{mean_value:.2f}", ha="center", va="bottom", fontsize=8)
    axes[3].set_xticks(x, region_summary["region_call"])
    axes[3].set_ylabel("Firing rate (Hz)")
    axes[3].set_title("Overall firing-rate summary")
    axes[3].legend(frameon=False, fontsize=8)
    axes[3].grid(axis="y", color="0.9")

    for ax in axes:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.suptitle(
        "Current Step 1 Cytoview dorsal/ventral snapshot; KSLabel=good, GUI-ready wells only",
        y=1.01,
        fontsize=13,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _deterministic_jitter(n: int, width: float) -> np.ndarray:
    if n <= 1:
        return np.zeros(n)
    return np.linspace(-width, width, n)


def _templates_average(templates_ext) -> np.ndarray:
    try:
        return np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        templates_data = templates_ext.get_data()
        if isinstance(templates_data, dict):
            templates_data = templates_data.get("average")
        return np.asarray(templates_data, dtype=float)


def _unit_property_array(sorting, name: str, unit_ids: list[object], default: object) -> list[object]:
    values = sorting.get_property(name)
    if values is None:
        return [default] * len(unit_ids)
    values = list(values)
    if len(values) != len(unit_ids):
        return [default] * len(unit_ids)
    return values


def _truthy_series(values: pd.Series) -> pd.Series:
    if values.dtype == bool:
        return values.fillna(False)
    return values.astype(str).str.lower().isin({"true", "1", "yes", "y"})


def _normalize_label(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return value.tobytes().decode("utf-8")
    return str(value)


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _median(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    return float(values.median()) if not values.empty else np.nan


def _mean(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else np.nan


if __name__ == "__main__":
    main()
