#!/usr/bin/env python
"""Compare pre/post stimulation firing rates in opsin and no-opsin organoids."""

from __future__ import annotations

import argparse
import csv
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
from axion_mea.gui_stim_response import resolve_stim_sidecars  # noqa: E402


DEFAULT_SOURCE_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_files_directory/incoming/"
    "manny4tbum_20260706/6_22_2026/129-8445"
)
DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
STEM = "lumos_opsin_vs_no_opsin_organoid_pre_post_firing_rate_20260710"
ELECTRODE_RE = re.compile(r"^(?P<well>[A-H]\d{1,2})_(?P<channel>\d{2})$")
GROUP_ORDER = ["opsin", "no_opsin"]
GROUP_LABELS = {"opsin": "+ opsin", "no_opsin": "− opsin"}
PERIOD_LABELS = {"pre_rate_hz": "Before", "post_rate_hz": "After"}
PERIOD_COLORS = {
    ("opsin", "pre_rate_hz"): "#8FB8E8",
    ("opsin", "post_rate_hz"): "#245EA8",
    ("no_opsin", "pre_rate_hz"): "#C4C7CC",
    ("no_opsin", "post_rate_hz"): "#5F6772",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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

    source_dir = args.source_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    spike_files = sorted(source_dir.glob("ventral_sosrs_opsin_day3(*)_spike_list.csv"))
    if len(spike_files) != 6:
        raise ValueError(f"Expected six repeated-recording spike lists, found {len(spike_files)}")

    recording_rows: list[dict[str, object]] = []
    condition_maps: list[dict[str, str]] = []
    for index, spike_file in enumerate(spike_files, start=1):
        spikes, treatment_map = _read_spike_list(spike_file)
        condition_map = {
            well: _condition_from_treatment(treatment)
            for well, treatment in treatment_map.items()
            if _condition_from_treatment(treatment) is not None
        }
        condition_maps.append(condition_map)
        recording_stem = spike_file.name.removesuffix("_spike_list.csv")
        reference_well = next(iter(condition_map))
        resolution = resolve_stim_sidecars(
            recording_stem,
            reference_well,
            raw_roots=DEFAULT_STIM_RAW_ROOTS,
            plate_family="lumos_48well",
        )
        if (
            not resolution.eligibility.enabled
            or resolution.stim_events is None
            or resolution.pulse_structure is None
        ):
            raise ValueError(f"{recording_stem}: {resolution.eligibility.message}")
        pulse_starts_ms = [pulse.start_ms for pulse in resolution.pulse_structure.pulse_epochs]
        pulse_onsets_s = np.asarray(
            [
                float(event.event_time_s) + pulse_start_ms / 1000.0
                for event in resolution.stim_events.itertuples(index=False)
                for pulse_start_ms in pulse_starts_ms
            ],
            dtype=float,
        )
        if len(pulse_onsets_s) != args.expected_pulse_trials:
            raise ValueError(
                f"{recording_stem}: expected {args.expected_pulse_trials} pulse trials, "
                f"found {len(pulse_onsets_s)}"
            )

        for well, condition in sorted(condition_map.items()):
            well_spikes = np.sort(
                spikes.loc[spikes["well"].eq(well), "time_s"].to_numpy(dtype=float)
            )
            pre_count = _count_relative_window(
                well_spikes,
                pulse_onsets_s,
                -args.window_ms,
                0.0,
            )
            post_count = _count_relative_window(
                well_spikes,
                pulse_onsets_s,
                0.0,
                args.window_ms,
            )
            exposure_s = len(pulse_onsets_s) * args.window_ms / 1000.0
            recording_rows.append(
                {
                    "recording": recording_stem,
                    "recording_index": _recording_index(recording_stem),
                    "well": well,
                    "organoid_id": well,
                    "treatment": treatment_map[well],
                    "condition": condition,
                    "pulse_trials": len(pulse_onsets_s),
                    "window_ms": args.window_ms,
                    "pre_spikes": pre_count,
                    "post_spikes": post_count,
                    "pre_rate_hz": pre_count / exposure_s,
                    "post_rate_hz": post_count / exposure_s,
                    "post_minus_pre_hz": (post_count - pre_count) / exposure_s,
                    "source_spike_list": str(spike_file),
                    "source_raw": str(resolution.inputs.raw_file or ""),
                }
            )
        print(
            f"[{index}/6] {recording_stem}: {len(condition_map)} organoids, "
            f"{len(pulse_onsets_s)} pulse trials",
            flush=True,
        )

    _validate_condition_maps(condition_maps)
    recording_table = pd.DataFrame(recording_rows).sort_values(
        ["condition", "well", "recording_index"]
    )
    organoid_table = _aggregate_organoids(recording_table)
    group_summary = _group_summary(organoid_table)

    recording_path = output_dir / f"{STEM}_recording_level.csv"
    organoid_path = output_dir / f"{STEM}_organoid_level.csv"
    group_path = output_dir / f"{STEM}_group_summary.csv"
    recording_table.to_csv(recording_path, index=False)
    organoid_table.to_csv(organoid_path, index=False)
    group_summary.to_csv(group_path, index=False)

    _style(plt)
    figure_paths = _plot_comparison(plt, organoid_table, output_dir)
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "question": "compare organoids with opsin versus no opsin before and after stimulation",
        "source_recordings": [path.name for path in spike_files],
        "biological_unit": "one well equals one organoid",
        "repeated_recordings": (
            "six recordings (000-005) are averaged within well before group summaries; "
            "they are not treated as independent organoids"
        ),
        "condition_source": "Treatment row embedded in each Axion spike-list Well Information block",
        "condition_map": condition_maps[0],
        "spike_source": "Axion spike-list events pooled across electrodes within each well",
        "stim_source": "raw stimulation event tags and reconstructed five-pulse train template",
        "windows_ms": {"before": [-args.window_ms, 0.0], "after": [0.0, args.window_ms]},
        "pulse_trials_per_recording": args.expected_pulse_trials,
        "silent_trials": "retained",
        "filter_variants": "not used; one Axion spike-list export per biological recording",
        "outputs": {
            "figures": [str(path) for path in figure_paths],
            "recording_level": str(recording_path),
            "organoid_level": str(organoid_path),
            "group_summary": str(group_path),
        },
    }
    provenance_path = output_dir / f"{STEM}_provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(f"\nOrganoids: {organoid_table['condition'].value_counts().to_dict()}")
    print(f"Figure: {figure_paths[0]}")
    print(f"Organoid table: {organoid_path}")
    print("\nGroup summary:")
    print(group_summary.to_string(index=False))
    return 0


def _read_spike_list(path: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    spike_rows: list[dict[str, object]] = []
    well_info_rows: list[list[str]] = []
    in_well_info = False
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            key = row[0].strip()
            if key == "Well Information":
                in_well_info = True
                continue
            if in_well_info:
                well_info_rows.append(row)
                continue
            if len(row) != 5:
                continue
            match = ELECTRODE_RE.fullmatch(row[3].strip())
            if match is None:
                continue
            try:
                time_s = float(row[2])
            except ValueError:
                continue
            spike_rows.append({"time_s": time_s, "well": match.group("well")})

    treatment_map = _parse_treatment_map(well_info_rows)
    return pd.DataFrame(spike_rows, columns=["time_s", "well"]), treatment_map


def _parse_treatment_map(rows: list[list[str]]) -> dict[str, str]:
    if not rows or rows[0][0].strip() != "Well":
        raise ValueError("Spike-list Well Information block is missing")
    wells = [value.strip() for value in rows[0][1:] if value.strip()]
    treatment_row = next((row for row in rows[1:] if row and row[0].strip() == "Treatment"), None)
    if treatment_row is None:
        raise ValueError("Spike-list Treatment row is missing")
    treatments = [value.strip() for value in treatment_row[1 : 1 + len(wells)]]
    return {well: treatment for well, treatment in zip(wells, treatments, strict=True) if treatment}


def _condition_from_treatment(value: object) -> str | None:
    normalized = str(value).strip().lower().replace("_", " ")
    if "no opsin" in normalized:
        return "no_opsin"
    if "opsin" in normalized:
        return "opsin"
    return None


def _count_relative_window(
    sorted_spike_times_s: np.ndarray,
    onsets_s: np.ndarray,
    start_ms: float,
    end_ms: float,
) -> int:
    starts = onsets_s + start_ms / 1000.0
    ends = onsets_s + end_ms / 1000.0
    left = np.searchsorted(sorted_spike_times_s, starts, side="left")
    right = np.searchsorted(sorted_spike_times_s, ends, side="left")
    return int(np.sum(right - left))


def _recording_index(recording: str) -> str:
    match = re.search(r"\((\d{3})\)$", recording)
    return match.group(1) if match else recording


def _validate_condition_maps(condition_maps: list[dict[str, str]]) -> None:
    reference = condition_maps[0]
    if any(condition_map != reference for condition_map in condition_maps[1:]):
        raise ValueError("Opsin/no-opsin well assignments differ across repeated recordings")
    expected = {"C6": "opsin", "D6": "opsin"}
    if any(reference.get(well) != condition for well, condition in expected.items()):
        raise ValueError(f"Unexpected opsin mapping: {reference}")


def _aggregate_organoids(recording_table: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (condition, well), group in recording_table.groupby(["condition", "well"], sort=True):
        rows.append(
            {
                "condition": condition,
                "condition_label": GROUP_LABELS[condition],
                "well": well,
                "organoid_id": well,
                "repeated_recordings": group["recording_index"].nunique(),
                "pulse_trials_total": int(group["pulse_trials"].sum()),
                "pre_rate_hz": float(group["pre_rate_hz"].mean()),
                "post_rate_hz": float(group["post_rate_hz"].mean()),
                "post_minus_pre_hz": float(group["post_minus_pre_hz"].mean()),
                "pre_rate_sd_across_recordings_hz": float(group["pre_rate_hz"].std(ddof=1)),
                "post_rate_sd_across_recordings_hz": float(group["post_rate_hz"].std(ddof=1)),
            }
        )
    return pd.DataFrame(rows).sort_values(["condition", "well"]).reset_index(drop=True)


def _group_summary(organoids: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for condition in GROUP_ORDER:
        group = organoids.loc[organoids["condition"].eq(condition)]
        n = len(group)
        for metric in ["pre_rate_hz", "post_rate_hz", "post_minus_pre_hz"]:
            values = group[metric].to_numpy(dtype=float)
            rows.append(
                {
                    "condition": condition,
                    "condition_label": GROUP_LABELS[condition],
                    "metric": metric,
                    "organoid_n": n,
                    "mean_hz": float(np.mean(values)),
                    "sem_hz": float(np.std(values, ddof=1) / np.sqrt(n)) if n > 1 else np.nan,
                    "median_hz": float(np.median(values)),
                }
            )
    return pd.DataFrame(rows)


def _plot_comparison(plt, organoids: pd.DataFrame, output_dir: Path) -> list[Path]:
    fig, (ax_pairs, ax_delta) = plt.subplots(
        1,
        2,
        figsize=(9.4, 4.7),
        gridspec_kw={"width_ratios": [1.55, 1.0]},
    )
    x_map = {
        ("opsin", "pre_rate_hz"): 0.0,
        ("opsin", "post_rate_hz"): 1.0,
        ("no_opsin", "pre_rate_hz"): 3.0,
        ("no_opsin", "post_rate_hz"): 4.0,
    }
    for condition in GROUP_ORDER:
        group = organoids.loc[organoids["condition"].eq(condition)].sort_values("well")
        pre_x = x_map[(condition, "pre_rate_hz")]
        post_x = x_map[(condition, "post_rate_hz")]
        for index, row in enumerate(group.itertuples(index=False)):
            offset = (index - (len(group) - 1) / 2.0) * 0.045
            ax_pairs.plot(
                [pre_x + offset, post_x + offset],
                [row.pre_rate_hz, row.post_rate_hz],
                color=PERIOD_COLORS[(condition, "post_rate_hz")],
                alpha=0.42,
                lw=0.9,
                zorder=1,
            )
            ax_pairs.scatter(
                [pre_x + offset, post_x + offset],
                [row.pre_rate_hz, row.post_rate_hz],
                c=[PERIOD_COLORS[(condition, "pre_rate_hz")], PERIOD_COLORS[(condition, "post_rate_hz")]],
                s=32,
                edgecolor="white",
                linewidth=0.55,
                zorder=3,
            )
        for metric in ["pre_rate_hz", "post_rate_hz"]:
            x = x_map[(condition, metric)]
            values = group[metric].to_numpy(dtype=float)
            mean = float(np.mean(values))
            sem = float(np.std(values, ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0.0
            ax_pairs.errorbar(
                x,
                mean,
                yerr=sem,
                fmt="D",
                markersize=6.0,
                color="#111827",
                markerfacecolor=PERIOD_COLORS[(condition, metric)],
                markeredgecolor="#111827",
                elinewidth=1.1,
                capsize=3,
                zorder=5,
            )
    ax_pairs.set_xticks([0, 1, 3, 4])
    ax_pairs.set_xticklabels(["Before", "After", "Before", "After"])
    current_bottom, current_top = ax_pairs.get_ylim()
    ax_pairs.set_ylim(min(0.0, current_bottom), current_top * 1.16)
    ax_pairs.text(0.5, 0.96, "+ opsin\nn=2 organoids", transform=ax_pairs.get_xaxis_transform(), ha="center", va="top", fontweight="bold", color="#245EA8")
    ax_pairs.text(3.5, 0.96, "− opsin\nn=7 organoids", transform=ax_pairs.get_xaxis_transform(), ha="center", va="top", fontweight="bold", color="#5F6772")
    ax_pairs.axvline(2.0, color="#d1d5db", lw=0.8)
    ax_pairs.set_ylabel("Well-wide firing rate (spikes/s)")
    ax_pairs.set_title("A  Before versus after stimulation", loc="left", y=1.03, fontweight="bold")

    for condition_index, condition in enumerate(GROUP_ORDER):
        group = organoids.loc[organoids["condition"].eq(condition)].sort_values("well")
        values = group["post_minus_pre_hz"].to_numpy(dtype=float)
        offsets = np.linspace(-0.10, 0.10, len(group)) if len(group) > 1 else np.array([0.0])
        color = PERIOD_COLORS[(condition, "post_rate_hz")]
        ax_delta.scatter(
            condition_index + offsets,
            values,
            s=42,
            color=color,
            edgecolor="white",
            linewidth=0.65,
            zorder=3,
        )
        for x, (_, row) in zip(condition_index + offsets, group.iterrows(), strict=True):
            ax_delta.text(x + 0.025, row["post_minus_pre_hz"], row["well"], fontsize=6.0, va="center")
        mean = float(np.mean(values))
        sem = float(np.std(values, ddof=1) / np.sqrt(len(values))) if len(values) > 1 else 0.0
        ax_delta.errorbar(
            condition_index,
            mean,
            yerr=sem,
            fmt="D",
            markersize=6.5,
            color="#111827",
            markerfacecolor=color,
            markeredgecolor="#111827",
            elinewidth=1.1,
            capsize=3,
            zorder=5,
        )
    ax_delta.axhline(0, color="#6b7280", ls="--", lw=0.8)
    ax_delta.set_xticks([0, 1])
    ax_delta.set_xticklabels(["+ opsin", "− opsin"])
    ax_delta.set_ylabel("After − before (spikes/s)")
    ax_delta.set_title("B  Stimulation-associated change", loc="left", fontweight="bold")

    for axis in (ax_pairs, ax_delta):
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", color="#e5e7eb", lw=0.55, alpha=0.8)
        axis.set_axisbelow(True)
    fig.suptitle(
        "Organoid firing rates before and after optical stimulation",
        x=0.055,
        y=0.985,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.935,
        "Axion well-level spikes · matched 25-ms windows · all 250 pulse trials retained · "
        "each point is one well/organoid averaged across six repeated recordings",
        ha="left",
        fontsize=7.5,
        color="#4b5563",
    )
    fig.subplots_adjust(left=0.10, right=0.985, bottom=0.13, top=0.84, wspace=0.34)
    paths = []
    for suffix in ("png", "pdf", "svg"):
        path = (output_dir / STEM).with_suffix(f".{suffix}")
        kwargs = {"bbox_inches": "tight", "facecolor": "white"}
        if suffix == "png":
            kwargs["dpi"] = 500
        fig.savefig(path, **kwargs)
        paths.append(path)
    plt.close(fig)
    return paths


def _style(plt) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.0,
            "axes.titlesize": 9.0,
            "axes.labelsize": 8.0,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "axes.linewidth": 0.7,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
