#!/usr/bin/env python
"""Plot all-trial versus nonempty-trial PSTHs for top Lumos good units."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
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
from axion_mea.gui_stim_response import (  # noqa: E402
    DEFAULT_RAPID_REVIEW_PULSE_TRIALS,
    DEFAULT_WAVEFORM_METRICS_CSV,
    DEFAULT_WAVEFORM_TRACES_CSV,
    OPTO_BASELINE_END_MS,
    OPTO_BASELINE_START_MS,
    OPTO_RESPONSE_END_MS,
    OPTO_RESPONSE_START_MS,
    AlignedWaveformReview,
    UnitStimResponse,
    UnitStimResponseBuilder,
    _sorting_from_analyzer,
    active_pulse_trial_response,
    load_aligned_waveform_reviews,
    resolve_stim_sidecars,
)


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_SCREEN = DEFAULT_JOB_DIR / "lumos_good_kslabel_optotag_screen_first250_20260710.csv"
STEM = "lumos_good_optotag_nonempty_trial_psth_20260710"


@dataclass(frozen=True)
class CandidatePlotData:
    review_rank: int
    recording: str
    well: str
    unit_label: str
    opto_score_hz: float
    response: UnitStimResponse
    active_response: UnitStimResponse
    waveform: AlignedWaveformReview | None
    pulse_duration_ms: float
    summary: dict[str, object]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen-csv", type=Path, default=DEFAULT_SCREEN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_JOB_DIR / STEM)
    parser.add_argument("--top-n", type=int, default=24)
    parser.add_argument("--units-per-page", type=int, default=6)
    parser.add_argument("--max-pulse-trials", type=int, default=DEFAULT_RAPID_REVIEW_PULSE_TRIALS)
    parser.add_argument("--waveform-metrics-csv", type=Path, default=DEFAULT_WAVEFORM_METRICS_CSV)
    parser.add_argument("--waveform-traces-csv", type=Path, default=DEFAULT_WAVEFORM_TRACES_CSV)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import spikeinterface.full as si

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    screen = pd.read_csv(args.screen_csv.expanduser().resolve()).head(args.top_n).copy()
    if screen.empty:
        raise SystemExit("The candidate screen is empty.")

    candidates: list[CandidatePlotData] = []
    errors: list[dict[str, object]] = []
    for progress, (_, row) in enumerate(screen.iterrows(), start=1):
        try:
            candidate = _load_candidate(si, row, args)
            candidates.append(candidate)
            status = (
                f"{candidate.summary['active_pulse_trials']}/"
                f"{candidate.summary['all_pulse_trials']} nonempty"
            )
        except Exception as exc:  # noqa: BLE001 - keep the review batch useful
            errors.append(
                {
                    "review_rank": row.get("review_rank"),
                    "recording": row.get("recording"),
                    "well": row.get("well"),
                    "unit": row.get("unit"),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            status = "error"
        print(f"[{progress:02d}/{len(screen):02d}] rank {row.get('review_rank')}: {status}", flush=True)

    if not candidates:
        raise SystemExit("No candidate figures could be constructed.")

    _style(plt)
    page_paths: list[Path] = []
    for page_number, start in enumerate(range(0, len(candidates), args.units_per_page), start=1):
        page_candidates = candidates[start : start + args.units_per_page]
        page_paths.extend(_plot_page(plt, page_candidates, output_dir, page_number))

    summary = pd.DataFrame([candidate.summary for candidate in candidates])
    summary_path = output_dir / f"{STEM}_selection_and_recalculated_metrics.csv"
    summary.to_csv(summary_path, index=False)
    errors_path = output_dir / f"{STEM}_errors.csv"
    pd.DataFrame(
        errors,
        columns=["review_rank", "recording", "well", "unit", "error"],
    ).to_csv(errors_path, index=False)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "candidate_screen": str(args.screen_csv.expanduser().resolve()),
        "selection": f"first {args.top_n} rows by existing all-trial optotag review rank",
        "all_trial_denominator": f"first {args.max_pulse_trials} pulse pseudo-trials",
        "nonempty_trial_rule": (
            "keep a pulse pseudo-trial only when the selected unit has at least one spike "
            "anywhere in its pulse-aligned analysis window"
        ),
        "important_interpretation": (
            "the nonempty-trial PSTH is conditional on unit activity and is displayed beside, "
            "not in place of, the all-trial PSTH"
        ),
        "waveform": (
            "cached trough-aligned mean best-channel waveform; baseline corrected, "
            "trough normalized, no display smoothing"
        ),
        "candidate_count": len(candidates),
        "errors": errors,
        "outputs": {
            "pages": [str(path) for path in page_paths],
            "summary": str(summary_path),
            "errors": str(errors_path),
        },
    }
    provenance_path = output_dir / f"{STEM}_provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(f"\nCandidates plotted: {len(candidates)}")
    print(f"Figure pages: {len(page_paths) // 2} PNG/PDF pairs")
    print(f"Output directory: {output_dir}")
    print(f"Recalculated metrics: {summary_path}")
    print("\nLargest nonempty-trial fractions:")
    print(
        summary[
            [
                "review_rank",
                "well",
                "unit",
                "all_pulse_trials",
                "active_pulse_trials",
                "active_trial_fraction",
                "all_trial_response_reliability",
                "active_trial_response_reliability",
                "active_psth_delta_hz",
            ]
        ]
        .sort_values(["active_trial_fraction", "active_psth_delta_hz"], ascending=False)
        .head(12)
        .to_string(index=False)
    )
    return 0


def _load_candidate(si, row: pd.Series, args: argparse.Namespace) -> CandidatePlotData:
    recording = str(row["recording"])
    well = str(row["well"])
    analyzer_path = Path(str(row["analyzer_path"]))
    analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=False)
    sorting = _sorting_from_analyzer(analyzer)
    unit_id = _match_unit_id(list(sorting.get_unit_ids()), row["unit"])
    unit_label = _unit_label(unit_id)

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
    builder = UnitStimResponseBuilder.from_analyzer(
        analyzer,
        resolution.stim_events,
        well,
        resolution.pulse_structure,
    )
    response = builder.build([unit_id], max_pulse_trials=args.max_pulse_trials)
    active_response = active_pulse_trial_response(response, builder)
    waveform = load_aligned_waveform_reviews(
        recording,
        well,
        metrics_csv=args.waveform_metrics_csv,
        traces_csv=args.waveform_traces_csv,
    ).get(unit_label)
    pulse_durations = [
        pulse.end_ms - pulse.start_ms for pulse in resolution.pulse_structure.pulse_epochs
    ]
    pulse_duration_ms = float(np.nanmedian(pulse_durations)) if pulse_durations else 0.0
    summary = _candidate_summary(row, response, active_response, waveform)
    return CandidatePlotData(
        review_rank=int(row["review_rank"]),
        recording=recording,
        well=well,
        unit_label=unit_label,
        opto_score_hz=float(row["opto_score_hz"]),
        response=response,
        active_response=active_response,
        waveform=waveform,
        pulse_duration_ms=pulse_duration_ms,
        summary=summary,
    )


def _candidate_summary(
    row: pd.Series,
    response: UnitStimResponse,
    active: UnitStimResponse,
    waveform: AlignedWaveformReview | None,
) -> dict[str, object]:
    all_total = len(response.pulse_trials)
    active_total = len(active.pulse_trials)
    response_hits = _response_hits(response.pulse_aligned_spikes)
    active_baseline = _mean_psth_rate(active.pulse_psth, OPTO_BASELINE_START_MS, OPTO_BASELINE_END_MS)
    active_post = _mean_psth_rate(active.pulse_psth, OPTO_RESPONSE_START_MS, OPTO_RESPONSE_END_MS)
    return {
        "review_rank": int(row["review_rank"]),
        "recording": str(row["recording"]),
        "well": str(row["well"]),
        "unit": str(row["unit"]),
        "KSLabel": str(row.get("KSLabel", "good")),
        "all_trial_opto_score_hz": float(row["opto_score_hz"]),
        "all_pulse_trials": all_total,
        "active_pulse_trials": active_total,
        "silent_pulse_trials_removed": all_total - active_total,
        "active_trial_fraction": active_total / all_total if all_total else 0.0,
        "response_pulse_hits": response_hits,
        "all_trial_response_reliability": response_hits / all_total if all_total else 0.0,
        "active_trial_response_reliability": response_hits / active_total if active_total else 0.0,
        "active_psth_baseline_mean_hz": active_baseline,
        "active_psth_response_mean_hz": active_post,
        "active_psth_delta_hz": active_post - active_baseline,
        "active_psth_response_peak_hz": _peak_psth_rate(
            active.pulse_psth,
            OPTO_RESPONSE_START_MS,
            OPTO_RESPONSE_END_MS,
        ),
        "aligned_ttp_ms": waveform.trough_to_peak_ms if waveform else np.nan,
        "aligned_half_width_ms": waveform.half_width_ms if waveform else np.nan,
        "aligned_ptp_uV": waveform.ptp_uv if waveform else np.nan,
        "waveform_class": waveform.rs_fs_classification if waveform else "unavailable",
    }


def _plot_page(plt, candidates: list[CandidatePlotData], output_dir: Path, page_number: int) -> list[Path]:
    fig, axes = plt.subplots(
        len(candidates),
        4,
        figsize=(15.5, 2.15 * len(candidates) + 0.9),
        squeeze=False,
        gridspec_kw={"width_ratios": [1.0, 1.35, 1.25, 1.25]},
    )
    for row_axes, candidate in zip(axes, candidates, strict=True):
        _plot_waveform(row_axes[0], candidate)
        _plot_active_raster(row_axes[1], candidate)
        psth_max = _shared_psth_max(candidate.response.pulse_psth, candidate.active_response.pulse_psth)
        _plot_psth(
            row_axes[2],
            candidate.response.pulse_psth,
            candidate.pulse_duration_ms,
            title=f"All pulses · n={len(candidate.response.pulse_trials)}",
            ymax=psth_max,
        )
        _plot_psth(
            row_axes[3],
            candidate.active_response.pulse_psth,
            candidate.pulse_duration_ms,
            title=(
                f"Nonempty only · n={len(candidate.active_response.pulse_trials)} "
                f"({candidate.summary['active_trial_fraction']:.1%})"
            ),
            ymax=psth_max,
        )

    fig.suptitle(
        "Lumos KSLabel=good optotag candidates: all 250 pulses vs nonempty-trial PSTHs",
        x=0.035,
        y=0.995,
        ha="left",
        fontsize=12,
        fontweight="bold",
    )
    fig.text(
        0.035,
        0.975,
        "Nonempty = selected unit fired at least once anywhere in the pulse-aligned window. "
        "PSTH pair shares a y-axis within each unit; nonempty PSTH is activity-conditioned.",
        ha="left",
        va="top",
        fontsize=7.5,
        color="#4b5563",
    )
    fig.subplots_adjust(left=0.055, right=0.995, bottom=0.055, top=0.945, wspace=0.30, hspace=0.62)
    base = output_dir / f"{STEM}_page_{page_number:02d}"
    paths = []
    for suffix in ("png", "pdf"):
        path = base.with_suffix(f".{suffix}")
        kwargs = {"bbox_inches": "tight", "facecolor": "white"}
        if suffix == "png":
            kwargs["dpi"] = 400
        fig.savefig(path, **kwargs)
        paths.append(path)
    plt.close(fig)
    return paths


def _plot_waveform(axis, candidate: CandidatePlotData) -> None:
    waveform = candidate.waveform
    if waveform is None:
        axis.text(0.5, 0.5, "aligned waveform\nunavailable", ha="center", va="center")
        axis.set_axis_off()
        return
    values = np.asarray(waveform.aligned_average_uv, dtype=float)
    baseline = float(np.nanmedian(values[: min(5, len(values))]))
    centered = values - baseline
    scale = abs(float(np.nanmin(centered)))
    normalized = centered / max(scale, 1e-9)
    axis.plot(waveform.time_ms, normalized, color="#d55e00", lw=1.35)
    axis.axhline(0, color="#d1d5db", lw=0.55)
    axis.axvline(0, color="#d1d5db", lw=0.55)
    axis.set_xlim(-0.85, 1.55)
    axis.set_ylim(-1.16, max(0.55, float(np.nanmax(normalized)) * 1.12))
    axis.set_title(
        f"rank {candidate.review_rank} · {candidate.well} u{candidate.unit_label} · "
        f"{waveform.rs_fs_classification}\n"
        f"TTP {waveform.trough_to_peak_ms:.2f} ms · PTP {waveform.ptp_uv:.1f} µV · "
        f"Δall {candidate.opto_score_hz:.2f} Hz",
        loc="left",
        fontweight="bold",
    )
    axis.set_xlabel("ms from trough")
    axis.set_ylabel("trough-normalized")
    _clean_axis(axis)


def _plot_active_raster(axis, candidate: CandidatePlotData) -> None:
    spikes = candidate.active_response.pulse_aligned_spikes
    trial_ids = candidate.active_response.pulse_trials["pulse_trial_index"].astype(int).tolist()
    for display_row, pulse_trial_id in enumerate(trial_ids, start=1):
        times = spikes.loc[
            spikes["pulse_trial_index"].astype(int).eq(pulse_trial_id),
            "pulse_aligned_time_ms",
        ]
        if not times.empty:
            axis.vlines(times, display_row - 0.38, display_row + 0.38, color="#111827", lw=0.55)
    _shade_windows(axis, candidate.pulse_duration_ms)
    axis.set_xlim(-25, 50)
    axis.set_ylim(0, max(len(trial_ids) + 1, 1))
    axis.set_title(
        f"Nonempty-trial raster · {len(trial_ids)}/{len(candidate.response.pulse_trials)}",
        loc="left",
    )
    axis.set_xlabel("ms from pulse")
    axis.set_ylabel("nonempty trial")
    _clean_axis(axis)


def _plot_psth(axis, psth: pd.DataFrame, pulse_duration_ms: float, *, title: str, ymax: float) -> None:
    _shade_windows(axis, pulse_duration_ms)
    axis.bar(
        psth["bin_center_ms"],
        psth["rate_hz"],
        width=1.0,
        color="#dbeafe",
        edgecolor="#93c5fd",
        linewidth=0.35,
        label="1-ms bins",
    )
    axis.plot(psth["bin_center_ms"], psth["smooth_rate_hz"], color="#0f766e", lw=1.15, label="3-ms mean")
    axis.axvline(0, color="#b91c1c", ls="--", lw=0.75)
    axis.set_xlim(-25, 50)
    axis.set_ylim(0, ymax)
    axis.set_title(title, loc="left")
    axis.set_xlabel("ms from pulse")
    axis.set_ylabel("rate (Hz)")
    _clean_axis(axis)


def _shade_windows(axis, pulse_duration_ms: float) -> None:
    axis.axvspan(OPTO_BASELINE_START_MS, OPTO_BASELINE_END_MS, color="#9ca3af", alpha=0.11, lw=0)
    axis.axvspan(OPTO_RESPONSE_START_MS, OPTO_RESPONSE_END_MS, color="#60a5fa", alpha=0.07, lw=0)
    if pulse_duration_ms > 0:
        axis.axvspan(0, pulse_duration_ms, color="#f59e0b", alpha=0.20, lw=0)


def _shared_psth_max(all_psth: pd.DataFrame, active_psth: pd.DataFrame) -> float:
    values = []
    for psth in (all_psth, active_psth):
        for column in ("rate_hz", "smooth_rate_hz"):
            if column in psth and not psth.empty:
                values.append(float(psth[column].max()))
    return max(max(values, default=1.0) * 1.08, 1.0)


def _response_hits(spikes: pd.DataFrame) -> int:
    if spikes.empty:
        return 0
    window = spikes.loc[
        (spikes["pulse_aligned_time_ms"] >= OPTO_RESPONSE_START_MS)
        & (spikes["pulse_aligned_time_ms"] <= OPTO_RESPONSE_END_MS)
    ]
    return int(window["pulse_trial_index"].nunique()) if not window.empty else 0


def _mean_psth_rate(psth: pd.DataFrame, start_ms: float, end_ms: float) -> float:
    window = psth.loc[
        (psth["bin_center_ms"] >= start_ms) & (psth["bin_center_ms"] <= end_ms),
        "rate_hz",
    ]
    return float(window.mean()) if not window.empty else 0.0


def _peak_psth_rate(psth: pd.DataFrame, start_ms: float, end_ms: float) -> float:
    window = psth.loc[
        (psth["bin_center_ms"] >= start_ms) & (psth["bin_center_ms"] <= end_ms),
        "rate_hz",
    ]
    return float(window.max()) if not window.empty else 0.0


def _match_unit_id(unit_ids: list[object], requested: object) -> object:
    requested_text = _unit_label(requested)
    for unit_id in unit_ids:
        if _unit_label(unit_id) == requested_text:
            return unit_id
    raise KeyError(f"unit {requested!r} was not found; available={unit_ids}")


def _unit_label(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if np.isfinite(numeric) and numeric.is_integer():
        return str(int(numeric))
    return str(value)


def _clean_axis(axis) -> None:
    axis.spines[["top", "right"]].set_visible(False)
    axis.tick_params(length=2.2, pad=1.5)


def _style(plt) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 6.4,
            "axes.titlesize": 7.0,
            "axes.labelsize": 6.2,
            "xtick.labelsize": 5.5,
            "ytick.labelsize": 5.5,
            "axes.linewidth": 0.6,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
