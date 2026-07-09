#!/usr/bin/env python
"""Refresh Lumos GUI-ready optotag screen and manual curation guide."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.launch_step1_sorting_analyzer_browser import (  # noqa: E402
    DEFAULT_AIND_RESULTS_ROOT,
    DEFAULT_STIM_RAW_ROOTS,
)
from axion_mea.gui_stim_response import (  # noqa: E402
    OPTO_BASELINE_END_MS,
    OPTO_BASELINE_START_MS,
    OPTO_RESPONSE_END_MS,
    OPTO_RESPONSE_START_MS,
    TRAIN_TRIAL_BASELINE_END_MS,
    TRAIN_TRIAL_BASELINE_START_MS,
    TRAIN_TRIAL_RESPONSE_END_MS,
    TRAIN_TRIAL_RESPONSE_START_MS,
    UnitStimResponseBuilder,
    _label_to_unit_groups,
    _sorting_from_analyzer,
    _unit_ids_from_sorting,
    rank_opto_tagged_unit_groups,
    resolve_stim_sidecars,
)


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
RECORDING_NAME = "block0_None_recording1.zarr"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_AIND_RESULTS_ROOT)
    parser.add_argument("--date-label", default="20260709")
    parser.add_argument("--gui-base-url", default="http://localhost:18765")
    args = parser.parse_args()

    import spikeinterface.full as si

    job_dir = args.job_dir.expanduser().resolve()
    ground_truth = pd.read_csv(job_dir / "step1_v5_well_ground_truth.csv")
    lumos_ready = ground_truth.loc[
        ground_truth["plate_family"].eq("lumos_48well")
        & ground_truth["gui_analyzer_ready"].eq(True)
    ].copy()
    lumos_ready = lumos_ready.sort_values(["recording", "well"]).reset_index(drop=True)

    rows: list[dict[str, object]] = []
    for index, row in lumos_ready.iterrows():
        recording = str(row["recording"])
        well = str(row["well"])
        analyzer_path = (
            args.results_root.expanduser().resolve()
            / recording
            / well
            / "postprocessed"
            / RECORDING_NAME
        )
        base = _base_row(recording, well)

        try:
            resolution = resolve_stim_sidecars(
                recording,
                well,
                analyzer_path=analyzer_path,
                raw_roots=DEFAULT_STIM_RAW_ROOTS,
                plate_family="lumos_48well",
                plate_type_name=str(row.get("plate_type_name", "") or ""),
            )
            if (
                not resolution.eligibility.enabled
                or resolution.stim_events is None
                or resolution.pulse_structure is None
            ):
                rows.append(_empty_row(base, "stim_unavailable", resolution.eligibility.message))
                continue

            analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=False)
            sorting = _sorting_from_analyzer(analyzer)
            unit_ids = _unit_ids_from_sorting(sorting)
            label_to_units = _label_to_unit_groups(unit_ids, None)
            builder = UnitStimResponseBuilder.from_analyzer(
                analyzer,
                resolution.stim_events,
                well,
                resolution.pulse_structure,
            )
            ranked = rank_opto_tagged_unit_groups(builder, label_to_units, limit=1)
            if not ranked:
                raise RuntimeError("no units available for ranking")

            score = ranked[0]
            response = builder.build(score.unit_ids)
            post_counts = _pulse_window_counts(
                response.pulse_aligned_spikes,
                OPTO_RESPONSE_START_MS,
                OPTO_RESPONSE_END_MS,
                first_n_pulses=250,
            )
            pulse_response_signal = _psth_window_signal(
                response.pulse_psth,
                OPTO_RESPONSE_START_MS,
                OPTO_RESPONSE_END_MS,
            )
            pulse_durations = [pulse.end_ms - pulse.start_ms for pulse in resolution.pulse_structure.pulse_epochs]
            pulse_duration_ms = float(np.nanmedian(pulse_durations)) if pulse_durations else np.nan
            during_counts = _pulse_window_counts(
                response.pulse_aligned_spikes,
                0.0,
                pulse_duration_ms if not math.isnan(pulse_duration_ms) else 0.0,
                first_n_pulses=250,
            )
            pulse_during_signal = _psth_window_signal(
                response.pulse_psth,
                0.0,
                pulse_duration_ms if not math.isnan(pulse_duration_ms) else 0.0,
            )
            train_response_counts = _train_window_counts(
                response.train_aligned_spikes,
                response.train_trials,
                TRAIN_TRIAL_RESPONSE_START_MS,
                TRAIN_TRIAL_RESPONSE_END_MS,
            )
            train_response_signal = _psth_window_signal(
                response.train_psth,
                TRAIN_TRIAL_RESPONSE_START_MS,
                TRAIN_TRIAL_RESPONSE_END_MS,
            )
            train_baseline_counts = _train_window_counts(
                response.train_aligned_spikes,
                response.train_trials,
                TRAIN_TRIAL_BASELINE_START_MS,
                TRAIN_TRIAL_BASELINE_END_MS,
            )
            train_baseline_signal = _psth_window_signal(
                response.train_psth,
                TRAIN_TRIAL_BASELINE_START_MS,
                TRAIN_TRIAL_BASELINE_END_MS,
            )
            pulse_count_values = tuple(response.pulse_structure.pulse_count_per_train or ())
            pulse_count = (
                int(pulse_count_values[0])
                if pulse_count_values and len(set(pulse_count_values)) == 1
                else np.nan
            )

            rows.append(
                {
                    **base,
                    "status": "ok",
                    "top_unit": score.unit_label,
                    "score_hz": score.score_hz,
                    "post_rate_hz": score.post_rate_hz,
                    "baseline_rate_hz": score.baseline_rate_hz,
                    "baseline_spikes": score.baseline_spikes,
                    "post_spikes_score_window": score.post_spikes,
                    "train_trials": len(response.train_trials),
                    "pulse_trials": len(response.pulse_trials),
                    "pulse_count_per_train": pulse_count,
                    "pulse_duration_ms": pulse_duration_ms,
                    "post_window_pulse_spikes": post_counts["spikes"],
                    "post_window_train_hits": post_counts["train_hits"],
                    "post_window_train_reliability": post_counts["train_reliability"],
                    "post_window_pulse_hits": post_counts["pulse_hits"],
                    "post_window_pulse_reliability_250": post_counts["pulse_reliability"],
                    "pulse_response_peak_raw_rate_hz": pulse_response_signal["peak_raw_rate_hz"],
                    "pulse_response_peak_smooth_rate_hz": pulse_response_signal["peak_smooth_rate_hz"],
                    "during_stim_spikes": during_counts["spikes"],
                    "during_stim_train_hits": during_counts["train_hits"],
                    "during_stim_train_reliability": during_counts["train_reliability"],
                    "during_stim_pulse_hits": during_counts["pulse_hits"],
                    "during_stim_pulse_reliability_250": during_counts["pulse_reliability"],
                    "pulse_during_peak_raw_rate_hz": pulse_during_signal["peak_raw_rate_hz"],
                    "pulse_during_peak_smooth_rate_hz": pulse_during_signal["peak_smooth_rate_hz"],
                    "train_response_spikes": train_response_counts["spikes"],
                    "train_response_trial_hits": train_response_counts["trial_hits"],
                    "train_response_trial_reliability": train_response_counts["trial_reliability"],
                    "train_response_rate_hz": train_response_counts["rate_hz"],
                    "train_response_peak_raw_rate_hz": train_response_signal["peak_raw_rate_hz"],
                    "train_response_peak_smooth_rate_hz": train_response_signal["peak_smooth_rate_hz"],
                    "train_baseline_spikes": train_baseline_counts["spikes"],
                    "train_baseline_trial_hits": train_baseline_counts["trial_hits"],
                    "train_baseline_trial_reliability": train_baseline_counts["trial_reliability"],
                    "train_baseline_rate_hz": train_baseline_counts["rate_hz"],
                    "train_baseline_peak_raw_rate_hz": train_baseline_signal["peak_raw_rate_hz"],
                    "train_baseline_peak_smooth_rate_hz": train_baseline_signal["peak_smooth_rate_hz"],
                    "reason": resolution.eligibility.message,
                }
            )
        except Exception as exc:  # noqa: BLE001 - keep batch refresh going
            rows.append(_empty_row(base, "error", f"{type(exc).__name__}: {exc}"))

        print(f"[{index + 1:02d}/{len(lumos_ready)}] {recording} / {well} -> {rows[-1]['status']}", flush=True)

    screen = pd.DataFrame(rows)
    screen_path = job_dir / f"lumos_gui_ready_trial_tag_screen_250pulse_jitterwin_{args.date_label}.csv"
    screen.to_csv(screen_path, index=False)

    guide = _build_guide(screen, args.gui_base_url)
    guide_path = job_dir / f"lumos_manual_spike_sorting_guide_jitterwin_{args.date_label}.csv"
    guide.to_csv(guide_path, index=False)

    print(f"Screen CSV: {screen_path}")
    print(f"Guide CSV: {guide_path}")
    print(screen["status"].value_counts(dropna=False).to_string())
    print("\nTop guide rows:")
    print(
        guide[
            [
                "review_rank",
                "review_tier",
                "recording",
                "well",
                "top_unit",
                "review_sort_peak_raw_response_hz",
                "score_hz",
                "train_response_trial_reliability",
                "train_response_peak_smooth_rate_hz",
                "post_window_pulse_reliability_250",
                "pulse_response_peak_smooth_rate_hz",
            ]
        ]
        .head(12)
        .to_string(index=False)
    )


def _base_row(recording: str, well: str) -> dict[str, object]:
    column = _well_column(well)
    return {
        "recording": recording,
        "well": well,
        "well_column": column,
        "june_july_column4_8_prior": bool(4 <= column <= 8) if not math.isnan(column) else False,
        "baseline_window_ms": f"{OPTO_BASELINE_START_MS:g}..{OPTO_BASELINE_END_MS:g}",
        "post_window_ms": f"{OPTO_RESPONSE_START_MS:g}..{OPTO_RESPONSE_END_MS:g}",
        "train_baseline_window_ms": f"{TRAIN_TRIAL_BASELINE_START_MS:g}..{TRAIN_TRIAL_BASELINE_END_MS:g}",
        "train_response_window_ms": f"{TRAIN_TRIAL_RESPONSE_START_MS:g}..{TRAIN_TRIAL_RESPONSE_END_MS:g}",
        "first_n_pulse_trials": 250,
    }


def _empty_row(base: dict[str, object], status: str, reason: str) -> dict[str, object]:
    numeric_fields = [
        "top_unit",
        "score_hz",
        "post_rate_hz",
        "baseline_rate_hz",
        "baseline_spikes",
        "post_spikes_score_window",
        "train_trials",
        "pulse_trials",
        "pulse_count_per_train",
        "pulse_duration_ms",
        "post_window_pulse_spikes",
        "post_window_train_hits",
        "post_window_train_reliability",
        "post_window_pulse_hits",
        "post_window_pulse_reliability_250",
        "pulse_response_peak_raw_rate_hz",
        "pulse_response_peak_smooth_rate_hz",
        "during_stim_spikes",
        "during_stim_train_hits",
        "during_stim_train_reliability",
        "during_stim_pulse_hits",
        "during_stim_pulse_reliability_250",
        "pulse_during_peak_raw_rate_hz",
        "pulse_during_peak_smooth_rate_hz",
        "train_response_spikes",
        "train_response_trial_hits",
        "train_response_trial_reliability",
        "train_response_rate_hz",
        "train_response_peak_raw_rate_hz",
        "train_response_peak_smooth_rate_hz",
        "train_baseline_spikes",
        "train_baseline_trial_hits",
        "train_baseline_trial_reliability",
        "train_baseline_rate_hz",
        "train_baseline_peak_raw_rate_hz",
        "train_baseline_peak_smooth_rate_hz",
    ]
    row = {**base, "status": status, "reason": reason}
    row.update({field: np.nan for field in numeric_fields})
    if status == "stim_unavailable":
        row["train_trials"] = 0
        row["pulse_trials"] = 0
    return row


def _well_column(well: str) -> float:
    digits = "".join(ch for ch in str(well) if ch.isdigit())
    return float(int(digits)) if digits else np.nan


def _pulse_window_counts(
    spikes: pd.DataFrame,
    window_start_ms: float,
    window_end_ms: float,
    *,
    first_n_pulses: int | None,
) -> dict[str, float | int]:
    if spikes.empty:
        return _hit_counts(0, 0, 0, 0)
    pulse_ids = sorted(spikes["pulse_trial_index"].dropna().astype(int).unique().tolist())
    if first_n_pulses is not None:
        pulse_ids = pulse_ids[:first_n_pulses]
    subset = spikes.loc[spikes["pulse_trial_index"].astype(int).isin(set(pulse_ids))].copy()
    in_window = subset.loc[
        (subset["pulse_aligned_time_ms"] >= window_start_ms)
        & (subset["pulse_aligned_time_ms"] <= window_end_ms)
    ]
    train_total = int(subset["train_trial_index"].nunique()) if not subset.empty else 0
    train_hits = int(in_window["train_trial_index"].nunique()) if not in_window.empty else 0
    pulse_hits = int(in_window["pulse_trial_index"].nunique()) if not in_window.empty else 0
    return _hit_counts(len(in_window), train_hits, train_total, pulse_hits, pulse_total=len(pulse_ids))


def _train_window_counts(
    spikes: pd.DataFrame,
    train_trials: tuple[int, ...],
    window_start_ms: float,
    window_end_ms: float,
) -> dict[str, float | int]:
    trial_total = len(train_trials)
    if spikes.empty:
        spikes_count = 0
        trial_hits = 0
    else:
        in_window = spikes.loc[
            (spikes["aligned_time_ms"] >= window_start_ms)
            & (spikes["aligned_time_ms"] <= window_end_ms)
        ]
        spikes_count = int(len(in_window))
        trial_hits = int(in_window["trial_index"].nunique()) if not in_window.empty else 0
    duration_s = trial_total * max(window_end_ms - window_start_ms, 0.0) / 1000.0
    return {
        "spikes": spikes_count,
        "trial_hits": trial_hits,
        "trial_reliability": trial_hits / trial_total if trial_total else 0.0,
        "rate_hz": spikes_count / duration_s if duration_s > 0 else 0.0,
    }


def _psth_window_signal(
    psth: pd.DataFrame,
    window_start_ms: float,
    window_end_ms: float,
) -> dict[str, float]:
    if psth.empty:
        return {"peak_raw_rate_hz": 0.0, "peak_smooth_rate_hz": 0.0}
    in_window = psth.loc[
        (psth["bin_center_ms"] >= window_start_ms)
        & (psth["bin_center_ms"] <= window_end_ms)
    ]
    if in_window.empty:
        return {"peak_raw_rate_hz": 0.0, "peak_smooth_rate_hz": 0.0}
    return {
        "peak_raw_rate_hz": float(in_window["rate_hz"].max()),
        "peak_smooth_rate_hz": float(in_window["smooth_rate_hz"].max()),
    }


def _hit_counts(
    spikes: int,
    train_hits: int,
    train_total: int,
    pulse_hits: int,
    *,
    pulse_total: int = 0,
) -> dict[str, float | int]:
    return {
        "spikes": int(spikes),
        "train_hits": int(train_hits),
        "train_reliability": train_hits / train_total if train_total else 0.0,
        "pulse_hits": int(pulse_hits),
        "pulse_reliability": pulse_hits / pulse_total if pulse_total else 0.0,
    }


def _build_guide(screen: pd.DataFrame, gui_base_url: str) -> pd.DataFrame:
    guide = screen.copy()
    for column in (
        "score_hz",
        "post_window_pulse_reliability_250",
        "during_stim_pulse_reliability_250",
        "train_response_trial_reliability",
        "train_response_rate_hz",
        "train_response_peak_raw_rate_hz",
        "train_response_peak_smooth_rate_hz",
        "pulse_response_peak_raw_rate_hz",
        "pulse_response_peak_smooth_rate_hz",
        "pulse_during_peak_raw_rate_hz",
        "pulse_during_peak_smooth_rate_hz",
        "well_column",
    ):
        guide[column] = pd.to_numeric(guide[column], errors="coerce")
    guide["review_sort_peak_raw_response_hz"] = guide["pulse_response_peak_raw_rate_hz"].fillna(0.0)
    guide["review_tier"] = guide.apply(_review_tier, axis=1)
    guide["review_action"] = guide.apply(_review_action, axis=1)
    guide["review_reason"] = guide.apply(_review_reason, axis=1)
    guide["gui_url"] = guide.apply(lambda row: _gui_url(row, gui_base_url), axis=1)
    tier_order = {
        "1_review_D2_possible_real": 1,
        "1_strong_opto_candidate": 2,
        "2_expected_column_high_reliability": 3,
        "3_review_outside_prior_or_moderate_score": 4,
        "4_lower_priority_ok": 5,
        "9_no_usable_stim_metadata": 9,
    }
    guide["_tier_order"] = guide["review_tier"].map(tier_order).fillna(99)
    guide["_status_order"] = np.where(guide["status"].eq("ok"), 0, 1)
    guide = guide.sort_values(
        [
            "_status_order",
            "review_sort_peak_raw_response_hz",
            "post_window_pulse_reliability_250",
            "train_response_peak_raw_rate_hz",
            "score_hz",
            "_tier_order",
        ],
        ascending=[True, False, False, False, False, False],
    ).reset_index(drop=True)
    guide.insert(0, "review_rank", np.arange(1, len(guide) + 1))
    columns = [
        "review_rank",
        "review_tier",
        "review_action",
        "review_reason",
        "recording",
        "well",
        "well_column",
        "june_july_column4_8_prior",
        "status",
        "top_unit",
        "review_sort_peak_raw_response_hz",
        "score_hz",
        "post_rate_hz",
        "baseline_rate_hz",
        "post_window_pulse_reliability_250",
        "during_stim_pulse_reliability_250",
        "train_response_trial_reliability",
        "train_response_rate_hz",
        "train_response_peak_raw_rate_hz",
        "train_response_peak_smooth_rate_hz",
        "train_baseline_rate_hz",
        "train_baseline_peak_raw_rate_hz",
        "train_baseline_peak_smooth_rate_hz",
        "pulse_response_peak_raw_rate_hz",
        "pulse_response_peak_smooth_rate_hz",
        "pulse_during_peak_raw_rate_hz",
        "pulse_during_peak_smooth_rate_hz",
        "train_trials",
        "pulse_trials",
        "baseline_window_ms",
        "post_window_ms",
        "train_baseline_window_ms",
        "train_response_window_ms",
        "gui_url",
        "reason",
    ]
    return guide[columns]


def _review_tier(row: pd.Series) -> str:
    if row["status"] != "ok":
        return "9_no_usable_stim_metadata"
    if str(row["well"]) == "D2" and row["score_hz"] >= 0.3:
        return "1_review_D2_possible_real"
    if row["score_hz"] >= 0.8:
        return "1_strong_opto_candidate"
    if bool(row["june_july_column4_8_prior"]) and row["post_window_pulse_reliability_250"] >= 0.8:
        return "2_expected_column_high_reliability"
    if row["post_window_pulse_reliability_250"] >= 0.8 or row["score_hz"] >= 0.3:
        return "3_review_outside_prior_or_moderate_score"
    return "4_lower_priority_ok"


def _review_action(row: pd.Series) -> str:
    if row["status"] != "ok":
        return "Skip for optotag review until stim metadata issue is resolved."
    if str(row["well"]) == "D2":
        return "Review carefully; D2 may be real despite being outside the column 4-8 prior."
    if bool(row["june_july_column4_8_prior"]):
        return "Review as expected opto-expression-region candidate."
    return "Review as possible control/outside-prior response; do not discard automatically."


def _review_reason(row: pd.Series) -> str:
    if row["status"] != "ok":
        return str(row.get("reason", ""))
    reasons = ["column_4_8_prior" if row["june_july_column4_8_prior"] else "outside_column_4_8_prior"]
    if str(row["well"]) == "D2":
        reasons.append("D2_possible_real")
    if row["score_hz"] >= 0.8:
        reasons.append("high_score")
    if row["post_window_pulse_reliability_250"] >= 0.8:
        reasons.append("high_250pulse_response_reliability")
    if row["train_response_trial_reliability"] >= 0.8:
        reasons.append("high_train_trial_response_reliability")
    if row["during_stim_pulse_reliability_250"] >= 0.2:
        reasons.append("during_stim_spiking_present")
    return ";".join(reasons)


def _gui_url(row: pd.Series, gui_base_url: str) -> str:
    return (
        f"{gui_base_url.rstrip('/')}/gui?"
        f"recording={quote(str(row['recording']))}&"
        f"well={quote(str(row['well']))}&"
        "no_traces=false"
    )


if __name__ == "__main__":
    main()
