#!/usr/bin/env python
"""Categorize visual rebound-peak validity for one representative well."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from axion_mea.master_unit_table import CANONICAL_MASTER_UNIT_TABLE
from axion_mea.step3_repro import DEFAULT_STEP3_REPRO_DIR, write_command_repro


DEFAULT_INPUT_CSV = CANONICAL_MASTER_UNIT_TABLE.with_name("representative_well_B3_dominant_template_audit.csv")
DEFAULT_OUTPUT_CSV = CANONICAL_MASTER_UNIT_TABLE.with_name(
    "representative_well_B3_rebound_peak_biological_validity.csv"
)
DEFAULT_PROVENANCE_JSON = CANONICAL_MASTER_UNIT_TABLE.with_name(
    "representative_well_B3_rebound_peak_biological_validity_provenance.json"
)
DEFAULT_FIGURE = (
    CANONICAL_MASTER_UNIT_TABLE.parent
    / "figures"
    / "rs_fs_waveforms"
    / "figure__representative_well_B3_rebound_peak_biological_validity.png"
)


# Manual visual review of figure__representative_well_B3_dominant_templates_trough_peak.png,
# supported by peak-edge and post-peak-support diagnostics from the audit CSV.
AMBIGUOUS_UNITS = {
    0: "low_amplitude_noisy_rebound",
    2: "edge_limited_late_rebound",
    57: "late_rebound_limited_return_to_baseline",
    66: "edge_limited_no_visible_return_after_peak",
    95: "weak_noisy_late_rebound",
    97: "small_amplitude_late_rebound",
    123: "edge_limited_late_rebound",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record biological-validity categories for detected rebound peaks in representative well B3."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--provenance-json", type=Path, default=DEFAULT_PROVENANCE_JSON)
    parser.add_argument("--output-figure", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument("--repro-dir", type=Path, default=DEFAULT_STEP3_REPRO_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audit = pd.read_csv(args.input_csv)
    categorized = categorize(audit)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    args.provenance_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_figure.parent.mkdir(parents=True, exist_ok=True)
    categorized.to_csv(args.output_csv, index=False)
    plot_summary(categorized, args.output_figure)

    command_repro = write_command_repro(
        repro_dir=args.repro_dir,
        stem="audit_representative_well_rebound_peak_biological_validity",
        parsed_args={key: str(value) for key, value in vars(args).items()},
    )
    summary = build_summary(categorized)
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "question": "Do detected rebound peaks in one representative well correspond to visually expected biological rebound peaks?",
        "expected_result": (
            "If current Step 1 template features are biologically acceptable, most Kilosort-good units "
            "should have a visible post-trough rebound peak and only a small minority should be ambiguous."
        ),
        "input_csv": str(args.input_csv),
        "output_csv": str(args.output_csv),
        "output_figure": str(args.output_figure),
        "summary": summary,
        "category_rules": {
            "biologically_well_measured": "Detected rebound peak visually matches the expected post-trough rebound peak.",
            "ambiguous": "Detected rebound peak is edge-limited, weak/noisy, late with limited return, or otherwise visually uncertain.",
        },
        "manual_ambiguous_units": AMBIGUOUS_UNITS,
        "command_repro": command_repro,
    }
    args.provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Wrote biological validity CSV: {args.output_csv}")
    print(f"Wrote biological validity figure: {args.output_figure}")
    print(f"Wrote biological validity provenance: {args.provenance_json}")
    print(json.dumps(summary, indent=2))


def categorize(audit: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in audit.sort_values("unit_id").iterrows():
        unit_id = int(row["unit_id"])
        waveform = np.asarray(json.loads(row["waveform_json"]), dtype=float)
        trough_index = int(row["trough_index"])
        peak_index = int(row["peak_index"])
        centered = waveform - float(np.nanmedian(waveform[: min(5, len(waveform))]))
        amplitude_range = float(np.nanmax(centered) - np.nanmin(centered))
        post_peak_support_samples = int(len(waveform) - peak_index - 1)
        peak_at_edge = bool(peak_index >= len(waveform) - 2)
        peak_minus_end_median5 = float(centered[peak_index] - np.nanmedian(centered[-5:]))

        ambiguity = AMBIGUOUS_UNITS.get(unit_id)
        biological_validity = "ambiguous" if ambiguity else "biologically_well_measured"
        rows.append(
            {
                "recording": row["recording"],
                "well": row["well"],
                "unit_id": unit_id,
                "rs_fs_classification": row["rs_fs_classification"],
                "template_reference": row["template_reference"],
                "trough_index": trough_index,
                "peak_index": peak_index,
                "trough_to_peak_duration_ms": row["trough_to_peak_duration_ms_recomputed"],
                "biological_validity": biological_validity,
                "ambiguity_category": ambiguity or "",
                "amplitude_range": amplitude_range,
                "post_peak_support_samples": post_peak_support_samples,
                "peak_at_edge": peak_at_edge,
                "peak_minus_end_median5": peak_minus_end_median5,
            }
        )
    return pd.DataFrame(rows)


def build_summary(categorized: pd.DataFrame) -> dict[str, object]:
    validity_counts = categorized["biological_validity"].value_counts().to_dict()
    ambiguity_counts = (
        categorized.loc[categorized["biological_validity"] == "ambiguous", "ambiguity_category"]
        .value_counts()
        .to_dict()
    )
    return {
        "unit_count": int(len(categorized)),
        "biologically_well_measured_count": int(validity_counts.get("biologically_well_measured", 0)),
        "ambiguous_count": int(validity_counts.get("ambiguous", 0)),
        "biologically_well_measured_fraction": float(validity_counts.get("biologically_well_measured", 0) / len(categorized)),
        "ambiguous_fraction": float(validity_counts.get("ambiguous", 0) / len(categorized)),
        "ambiguity_counts": ambiguity_counts,
        "ambiguous_units": categorized.loc[
            categorized["biological_validity"] == "ambiguous",
            ["unit_id", "ambiguity_category", "trough_to_peak_duration_ms"],
        ].to_dict(orient="records"),
    }


def plot_summary(categorized: pd.DataFrame, output_figure: Path) -> None:
    counts = categorized["biological_validity"].value_counts().reindex(
        ["biologically_well_measured", "ambiguous"], fill_value=0
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].bar(counts.index, counts.values, color=["#0072b2", "#d55e00"])
    axes[0].set_ylabel("Kilosort-good units")
    axes[0].set_title("Representative well B3 rebound-peak validity")
    axes[0].tick_params(axis="x", rotation=20)

    ambiguous = categorized.loc[categorized["biological_validity"] == "ambiguous"]
    if ambiguous.empty:
        axes[1].text(0.5, 0.5, "No ambiguous units", ha="center", va="center")
        axes[1].axis("off")
    else:
        text = "\n".join(
            f"u{int(row.unit_id)}: {row.ambiguity_category}"
            for _, row in ambiguous.sort_values("unit_id").iterrows()
        )
        axes[1].text(0.0, 1.0, text, ha="left", va="top", fontsize=9)
        axes[1].axis("off")
        axes[1].set_title("Ambiguous units")
    fig.tight_layout()
    fig.savefig(output_figure, dpi=220, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
