#!/usr/bin/env python
"""Rank every Lumos KSLabel=good unit over the first 250 pulse trials."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
    DEFAULT_RAPID_REVIEW_PULSE_TRIALS,
    DEFAULT_WAVEFORM_METRICS_CSV,
    DEFAULT_WAVEFORM_TRACES_CSV,
    UnitStimResponseBuilder,
    _label_to_unit_groups,
    _sorting_from_analyzer,
    _unit_ids_from_sorting,
    build_rapid_opto_review_table,
    load_aligned_waveform_reviews,
    resolve_stim_sidecars,
)


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
RECORDING_NAME = "block0_None_recording1.zarr"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_AIND_RESULTS_ROOT)
    parser.add_argument("--date-label", default="20260710")
    parser.add_argument("--max-pulse-trials", type=int, default=DEFAULT_RAPID_REVIEW_PULSE_TRIALS)
    parser.add_argument("--waveform-metrics-csv", type=Path, default=DEFAULT_WAVEFORM_METRICS_CSV)
    parser.add_argument("--waveform-traces-csv", type=Path, default=DEFAULT_WAVEFORM_TRACES_CSV)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import spikeinterface.full as si

    job_dir = args.job_dir.expanduser().resolve()
    ground_truth = pd.read_csv(job_dir / "step1_v5_well_ground_truth.csv")
    wells = ground_truth.loc[
        ground_truth["plate_family"].eq("lumos_48well")
        & ground_truth["gui_analyzer_ready"].eq(True)
    ].sort_values(["recording", "well"])

    rows: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for progress, (_, well_row) in enumerate(wells.iterrows(), start=1):
        recording = str(well_row["recording"])
        well = str(well_row["well"])
        analyzer_path = (
            args.results_root.expanduser().resolve()
            / recording
            / well
            / "postprocessed"
            / RECORDING_NAME
        )
        try:
            resolution = resolve_stim_sidecars(
                recording,
                well,
                analyzer_path=analyzer_path,
                raw_roots=DEFAULT_STIM_RAW_ROOTS,
                plate_family="lumos_48well",
                plate_type_name=str(well_row.get("plate_type_name", "") or ""),
            )
            if (
                not resolution.eligibility.enabled
                or resolution.stim_events is None
                or resolution.pulse_structure is None
            ):
                raise ValueError(resolution.eligibility.message)

            analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=False)
            sorting = _sorting_from_analyzer(analyzer)
            unit_ids = _unit_ids_from_sorting(sorting)
            groups = _label_to_unit_groups(unit_ids, None)
            waveform_reviews = load_aligned_waveform_reviews(
                recording,
                well,
                metrics_csv=args.waveform_metrics_csv,
                traces_csv=args.waveform_traces_csv,
            )
            builder = UnitStimResponseBuilder.from_analyzer(
                analyzer,
                resolution.stim_events,
                well,
                resolution.pulse_structure,
            )
            table = build_rapid_opto_review_table(
                builder,
                groups,
                sorting,
                max_pulse_trials=args.max_pulse_trials,
                waveform_reviews=waveform_reviews,
            )
            for _, unit_row in table.iterrows():
                rows.append(
                    {
                        "recording": recording,
                        "well": well,
                        "analyzer_path": str(analyzer_path),
                        "train_trials": len(builder._eligible_events()),
                        "pulse_count_per_train": _uniform_pulse_count(
                            resolution.pulse_structure.pulse_count_per_train
                        ),
                        **unit_row.to_dict(),
                    }
                )
            status = f"{len(table)} good units"
        except Exception as exc:  # noqa: BLE001 - preserve the rest of the batch
            status = "error"
            errors.append(
                {
                    "recording": recording,
                    "well": well,
                    "analyzer_path": str(analyzer_path),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        print(f"[{progress:03d}/{len(wells):03d}] {recording} / {well}: {status}", flush=True)

    screen = pd.DataFrame(rows)
    if screen.empty:
        raise SystemExit("No KSLabel=good unit responses could be screened.")
    screen = screen.sort_values(
        ["opto_score_hz", "response_reliability", "response_spikes", "aligned_ptp_uV"],
        ascending=[False, False, False, False],
        na_position="last",
    ).reset_index(drop=True)
    screen.insert(0, "review_rank", np.arange(1, len(screen) + 1))
    output = job_dir / (
        f"lumos_good_kslabel_optotag_screen_first{args.max_pulse_trials}_{args.date_label}.csv"
    )
    screen.to_csv(output, index=False)

    error_output = job_dir / (
        f"lumos_good_kslabel_optotag_screen_first{args.max_pulse_trials}_{args.date_label}_errors.csv"
    )
    pd.DataFrame(errors, columns=["recording", "well", "analyzer_path", "error"]).to_csv(
        error_output,
        index=False,
    )

    print(f"\nScreened KSLabel=good units: {len(screen)}")
    print(f"Wells with errors/unavailable stim: {len(errors)}")
    print(f"Candidate screen: {output}")
    print(f"Errors: {error_output}")
    print("\nTop 25 candidates:")
    print(
        screen[
            [
                "review_rank",
                "recording",
                "well",
                "unit",
                "opto_score_hz",
                "response_reliability",
                "median_first_spike_latency_ms",
                "aligned_ttp_ms",
                "aligned_ptp_uV",
                "waveform_class",
            ]
        ]
        .head(25)
        .to_string(index=False)
    )
    return 0


def _uniform_pulse_count(values: tuple[int, ...]) -> float:
    return float(values[0]) if values and len(set(values)) == 1 else np.nan


if __name__ == "__main__":
    raise SystemExit(main())
