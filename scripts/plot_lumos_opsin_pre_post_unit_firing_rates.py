#!/usr/bin/env python
"""Plot per-unit pre/post firing rates for Lumos opsin and no-opsin wells."""

from __future__ import annotations

import argparse
import json
import re
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

from scripts.launch_step1_sorting_analyzer_browser import DEFAULT_STIM_RAW_ROOTS  # noqa: E402
from scripts.plot_lumos_opsin_pre_post_organoid_firing_rates import (  # noqa: E402
    DEFAULT_SOURCE_DIR,
    _condition_from_treatment,
    _count_relative_window,
    _read_spike_list,
    _recording_index,
)
from axion_mea.gui_stim_response import resolve_stim_sidecars  # noqa: E402


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_UNIT_METRICS = DEFAULT_JOB_DIR / "lumos_all_sorted_unit_waveform_metrics_20260709.csv"
STEM = "lumos_opsin_vs_no_opsin_per_unit_pre_post_firing_rate_20260710"
GROUP_ORDER = ["opsin", "no_opsin"]
GROUP_LABELS = {"opsin": "+ opsin", "no_opsin": "− opsin"}
WELL_COLORS = {
    "D6": "#245EA8",
    "B4": "#59636F",
    "B5": "#7A8490",
    "C3": "#9A6E55",
    "D2": "#525866",
    "E5": "#969DA6",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-metrics-csv", type=Path, default=DEFAULT_UNIT_METRICS)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_JOB_DIR / STEM)
    parser.add_argument("--window-ms", type=float, default=25.0)
    parser.add_argument("--expected-pulse-trials", type=int, default=250)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import spikeinterface.full as si

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    condition_map = _load_condition_map(args.source_dir.expanduser().resolve())
    source = pd.read_csv(args.unit_metrics_csv.expanduser().resolve())
    source = source.loc[
        source["recording"].astype(str).str.contains(
            "6_22_2026_129-8445_ventral_sosrs_opsin_day3", regex=False
        )
        & source["raw_variant"].eq("primary_raw")
        & source["KSLabel"].eq("good")
    ].copy()
    source["condition"] = source["well"].map(condition_map)
    source = source.loc[source["condition"].notna()].copy()
    if source.empty:
        raise SystemExit("No matching KSLabel=good units were found.")

    rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    analyzer_groups = list(source.groupby("analyzer_path", sort=True))
    for progress, (analyzer_path_text, group) in enumerate(analyzer_groups, start=1):
        analyzer_path = Path(str(analyzer_path_text))
        recording = str(group.iloc[0]["recording"])
        well = str(group.iloc[0]["well"])
        try:
            analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=False)
            sorting = analyzer.sorting
            sampling_frequency = float(sorting.get_sampling_frequency())
            unit_ids = list(sorting.get_unit_ids())
            resolution = resolve_stim_sidecars(
                recording,
                well,
                analyzer_path=analyzer_path,
                raw_roots=DEFAULT_STIM_RAW_ROOTS,
                plate_family="lumos_48well",
            )
            if (
                not resolution.eligibility.enabled
                or resolution.stim_events is None
                or resolution.pulse_structure is None
            ):
                raise ValueError(resolution.eligibility.message)
            pulse_onsets = np.asarray(
                [
                    float(event.event_time_s) + pulse.start_ms / 1000.0
                    for event in resolution.stim_events.itertuples(index=False)
                    for pulse in resolution.pulse_structure.pulse_epochs
                ],
                dtype=float,
            )
            if len(pulse_onsets) != args.expected_pulse_trials:
                raise ValueError(
                    f"expected {args.expected_pulse_trials} pulses, found {len(pulse_onsets)}"
                )
            exposure_s = len(pulse_onsets) * args.window_ms / 1000.0
            for _, unit_row in group.iterrows():
                unit_id = _match_unit_id(unit_ids, unit_row["unit_id"])
                spike_times = np.sort(
                    np.asarray(sorting.get_unit_spike_train(unit_id=unit_id), dtype=float)
                    / sampling_frequency
                )
                pre_count = _count_relative_window(
                    spike_times, pulse_onsets, -args.window_ms, 0.0
                )
                post_count = _count_relative_window(
                    spike_times, pulse_onsets, 0.0, args.window_ms
                )
                rows.append(
                    {
                        "unit_key": f"{recording}|{well}|{_unit_label(unit_id)}",
                        "recording": recording,
                        "recording_index": _recording_index_from_long_name(recording),
                        "well": well,
                        "organoid_id": well,
                        "condition": condition_map[well],
                        "condition_label": GROUP_LABELS[condition_map[well]],
                        "unit_id": _unit_label(unit_id),
                        "KSLabel": "good",
                        "pulse_trials": len(pulse_onsets),
                        "window_ms": args.window_ms,
                        "pre_spikes": pre_count,
                        "post_spikes": post_count,
                        "pre_rate_hz": pre_count / exposure_s,
                        "post_rate_hz": post_count / exposure_s,
                        "post_minus_pre_hz": (post_count - pre_count) / exposure_s,
                        "aligned_ttp_ms": unit_row.get("trough_to_peak_duration_ms", np.nan),
                        "template_ptp_uV": unit_row.get("template_ptp_best_channel_uV", np.nan),
                        "waveform_class": unit_row.get("rs_fs_classification", ""),
                        "analyzer_path": str(analyzer_path),
                    }
                )
            status = f"{len(group)} good units"
        except Exception as exc:  # noqa: BLE001
            status = "error"
            errors.append(
                {
                    "recording": recording,
                    "well": well,
                    "analyzer_path": str(analyzer_path),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        print(
            f"[{progress:02d}/{len(analyzer_groups):02d}] {well} "
            f"recording {_recording_index_from_long_name(recording)}: {status}",
            flush=True,
        )

    units = pd.DataFrame(rows).sort_values(
        ["condition", "well", "recording_index", "unit_id"]
    ).reset_index(drop=True)
    if units.empty:
        raise SystemExit("No per-unit rates could be calculated.")
    units.insert(0, "display_unit_id", [f"U{index:03d}" for index in range(1, len(units) + 1)])
    summary = _summary_table(units)
    unit_path = output_dir / f"{STEM}_unit_level.csv"
    summary_path = output_dir / f"{STEM}_descriptive_summary.csv"
    errors_path = output_dir / f"{STEM}_errors.csv"
    units.to_csv(unit_path, index=False)
    summary.to_csv(summary_path, index=False)
    pd.DataFrame(
        errors, columns=["recording", "well", "analyzer_path", "error"]
    ).to_csv(errors_path, index=False)

    _style(plt)
    figure_paths = _plot_unit_breakdown(plt, units, output_dir)
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "question": "per-unit opsin versus no-opsin firing rates before and after stimulation",
        "unit_selection": "KSLabel=good; primary_raw analyzer variant only",
        "unit_observation": "one Kilosort unit within one recording and well; units are not tracked across recordings",
        "condition_source": "Treatment metadata embedded in Axion spike-list export",
        "condition_map": condition_map,
        "windows_ms": {"before": [-args.window_ms, 0.0], "after": [0.0, args.window_ms]},
        "pulse_trials": args.expected_pulse_trials,
        "silent_trials": "retained",
        "important_limitation": (
            "all available opsin units are from well D6; C6 has no KSLabel=good units "
            "in the primary-variant unit table. Unit counts are not independent organoid n."
        ),
        "outputs": {
            "figures": [str(path) for path in figure_paths],
            "unit_table": str(unit_path),
            "summary": str(summary_path),
            "errors": str(errors_path),
        },
    }
    provenance_path = output_dir / f"{STEM}_provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(f"\nPer-unit observations: {len(units)}")
    print(f"Condition counts: {units['condition'].value_counts().to_dict()}")
    print(f"Wells: {units.groupby(['condition', 'well']).size().to_dict()}")
    print(f"Figure: {figure_paths[0]}")
    print(f"Unit table: {unit_path}")
    print("\nDescriptive summary:")
    print(summary.to_string(index=False))
    return 0


def _load_condition_map(source_dir: Path) -> dict[str, str]:
    spike_file = source_dir / "ventral_sosrs_opsin_day3(000)_spike_list.csv"
    _, treatment_map = _read_spike_list(spike_file)
    return {
        well: condition
        for well, treatment in treatment_map.items()
        if (condition := _condition_from_treatment(treatment)) is not None
    }


def _match_unit_id(unit_ids: list[object], requested: object) -> object:
    requested_label = _unit_label(requested)
    for unit_id in unit_ids:
        if _unit_label(unit_id) == requested_label:
            return unit_id
    raise KeyError(f"unit {requested!r} not found")


def _unit_label(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(numeric)) if np.isfinite(numeric) and numeric.is_integer() else str(value)


def _recording_index_from_long_name(recording: str) -> str:
    match = re.search(r"opsin_day3\((\d{3})\)", recording)
    return match.group(1) if match else _recording_index(recording)


def _summary_table(units: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for condition in GROUP_ORDER:
        group = units.loc[units["condition"].eq(condition)]
        for metric in ["pre_rate_hz", "post_rate_hz", "post_minus_pre_hz"]:
            values = group[metric].to_numpy(dtype=float)
            rows.append(
                {
                    "condition": condition,
                    "condition_label": GROUP_LABELS[condition],
                    "metric": metric,
                    "unit_observations": len(group),
                    "organoid_wells_represented": group["well"].nunique(),
                    "mean_hz": float(np.mean(values)),
                    "median_hz": float(np.median(values)),
                    "sem_across_units_hz": (
                        float(np.std(values, ddof=1) / np.sqrt(len(values)))
                        if len(values) > 1
                        else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows)


def _plot_unit_breakdown(plt, units: pd.DataFrame, output_dir: Path) -> list[Path]:
    fig, axes = plt.subplots(
        1,
        3,
        figsize=(14.2, 5.1),
        gridspec_kw={"width_ratios": [1.35, 1.0, 1.55]},
    )
    ax_pairs, ax_group_delta, ax_wells = axes
    x_positions = {("opsin", "pre"): 0.0, ("opsin", "post"): 1.0, ("no_opsin", "pre"): 3.0, ("no_opsin", "post"): 4.0}
    for condition in GROUP_ORDER:
        group = units.loc[units["condition"].eq(condition)].copy()
        pre_x = x_positions[(condition, "pre")]
        post_x = x_positions[(condition, "post")]
        offsets = _symmetric_offsets(len(group), width=0.25)
        for offset, row in zip(offsets, group.itertuples(index=False), strict=True):
            color = WELL_COLORS.get(row.well, "#6b7280")
            ax_pairs.plot(
                [pre_x + offset, post_x + offset],
                [row.pre_rate_hz, row.post_rate_hz],
                color=color,
                alpha=0.32,
                lw=0.65,
            )
            ax_pairs.scatter(
                [pre_x + offset, post_x + offset],
                [row.pre_rate_hz, row.post_rate_hz],
                s=15,
                color=color,
                alpha=0.82,
                edgecolor="white",
                linewidth=0.3,
                zorder=3,
            )
    ax_pairs.axvline(2.0, color="#d1d5db", lw=0.8)
    ax_pairs.set_xticks([0, 1, 3, 4])
    ax_pairs.set_xticklabels(["Before", "After", "Before", "After"])
    ax_pairs.text(0.5, 0.98, "+ opsin\n6 units · D6 only", transform=ax_pairs.get_xaxis_transform(), ha="center", va="top", color="#245EA8", fontweight="bold")
    ax_pairs.text(3.5, 0.98, "− opsin\n41 units · 5 wells", transform=ax_pairs.get_xaxis_transform(), ha="center", va="top", color="#59636F", fontweight="bold")
    ax_pairs.set_ylabel("Unit firing rate (Hz)")
    ax_pairs.set_title("A  Every unit: before versus after", loc="left", fontweight="bold")

    for group_index, condition in enumerate(GROUP_ORDER):
        group = units.loc[units["condition"].eq(condition)].copy()
        offsets = _symmetric_offsets(len(group), width=0.28)
        for offset, row in zip(offsets, group.itertuples(index=False), strict=True):
            ax_group_delta.scatter(
                group_index + offset,
                row.post_minus_pre_hz,
                s=22,
                color=WELL_COLORS.get(row.well, "#6b7280"),
                alpha=0.86,
                edgecolor="white",
                linewidth=0.4,
            )
    ax_group_delta.axhline(0, color="#6b7280", ls="--", lw=0.8)
    ax_group_delta.set_xticks([0, 1])
    ax_group_delta.set_xticklabels(["+ opsin", "− opsin"])
    ax_group_delta.set_ylabel("After − before (Hz)")
    ax_group_delta.set_title("B  Per-unit change", loc="left", fontweight="bold")

    well_order = [well for well in ["D6", "B4", "B5", "C3", "D2", "E5"] if well in set(units["well"])]
    for well_index, well in enumerate(well_order):
        group = units.loc[units["well"].eq(well)].copy()
        offsets = _symmetric_offsets(len(group), width=0.24)
        ax_wells.scatter(
            well_index + offsets,
            group["post_minus_pre_hz"],
            s=24,
            color=WELL_COLORS[well],
            alpha=0.88,
            edgecolor="white",
            linewidth=0.4,
        )
        ax_wells.text(
            well_index,
            0.98,
            f"n={len(group)}",
            transform=ax_wells.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=6.5,
            color=WELL_COLORS[well],
        )
    ax_wells.axhline(0, color="#6b7280", ls="--", lw=0.8)
    ax_wells.axvline(0.5, color="#d1d5db", lw=0.8)
    ax_wells.set_xticks(range(len(well_order)))
    ax_wells.set_xticklabels(well_order)
    ax_wells.set_ylabel("After − before (Hz)")
    ax_wells.set_title("C  Unit breakdown by organoid well", loc="left", fontweight="bold")

    for axis in axes:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#e5e7eb", lw=0.55, alpha=0.8)
        axis.set_axisbelow(True)
    handles = [
        plt.Line2D([0], [0], marker="o", linestyle="none", color=color, label=well, markersize=5)
        for well, color in WELL_COLORS.items()
        if well in set(units["well"])
    ]
    ax_wells.legend(handles=handles, title="well / organoid", frameon=False, fontsize=6.5, title_fontsize=6.5, ncol=2, loc="lower left")
    fig.suptitle(
        "Per-unit firing rates before and after optical stimulation",
        x=0.04,
        y=0.985,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    fig.text(
        0.04,
        0.94,
        "KSLabel=good · primary analyzer variant · matched 25-ms windows · all 250 pulses retained · "
        "each dot/line is one unit in one recording (units are not tracked across recordings)",
        ha="left",
        fontsize=7.5,
        color="#4b5563",
    )
    fig.subplots_adjust(left=0.065, right=0.99, bottom=0.12, top=0.84, wspace=0.34)
    paths = []
    for suffix in ["png", "pdf", "svg"]:
        path = (output_dir / STEM).with_suffix(f".{suffix}")
        kwargs = {"bbox_inches": "tight", "facecolor": "white"}
        if suffix == "png":
            kwargs["dpi"] = 500
        fig.savefig(path, **kwargs)
        paths.append(path)
    plt.close(fig)
    return paths


def _symmetric_offsets(count: int, *, width: float) -> np.ndarray:
    if count <= 1:
        return np.zeros(count)
    return np.linspace(-width, width, count)


def _style(plt) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 7.8,
            "axes.titlesize": 8.8,
            "axes.labelsize": 7.8,
            "xtick.labelsize": 7.2,
            "ytick.labelsize": 7.2,
            "axes.linewidth": 0.7,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
