#!/usr/bin/env python3
"""Compare channel-weighted TTR90 FS/RS activity in dorsal and ventral CytoView."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from axion_mea.spontaneous_activity import summarize_smoothed_inverse_isi_rate  # noqa: E402

PROJECT_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder"
)
JOB_ROOT = PROJECT_ROOT / "jobs/step1_nonlfp_th5_v5_ground_truth_latest"
PANEL_ROOT = PROJECT_ROOT / "FINAL FIG 2/Population Panels"
ACTIVITY_SOURCE = (
    JOB_ROOT
    / "cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_isi2ms_le3pct_20260710_071723"
    / "cytoview_dv_sua_spontaneous_activity_20260710_unit_metrics.csv"
)
VENTRAL_ROOT = PANEL_ROOT / "ventral_MGE_putative_FS_RS_robust_PCHIP_FINAL"
DORSAL_ROOT = PANEL_ROOT / "dorsal_forebrain_putative_FS_RS_TTR90_classifier_FINAL"

CLASS_MAP = {
    "high_confidence_FS_like": "FS",
    "high_confidence_RS_like": "RS",
}
GROUP_ORDER = [
    ("dorsal", "FS"),
    ("dorsal", "RS"),
    ("ventral", "FS"),
    ("ventral", "RS"),
]
METRICS = [
    ("legacy_firing_rate_hz", "Overall firing rate", "Hz"),
    ("inverse_isi_gaussian_temporal_p99_9_hz", "Smoothed inverse-ISI P99.9", "Hz"),
    ("burst_rate_per_min", "Burst rate", "bursts/min"),
    ("mean_firing_rate_within_bursts_hz", "MFR/Burst", "Hz"),
    ("mean_burst_duration_ms", "Burst duration", "ms"),
    ("mean_interburst_interval_s", "Inter-burst interval", "s"),
    ("mean_spikes_per_burst", "Spikes/burst", "spikes"),
]
COMPARISONS = [
    ("dorsal_FS_vs_RS", ("dorsal", "FS"), ("dorsal", "RS")),
    ("ventral_FS_vs_RS", ("ventral", "FS"), ("ventral", "RS")),
    ("FS_dorsal_vs_ventral", ("dorsal", "FS"), ("ventral", "FS")),
    ("RS_dorsal_vs_ventral", ("dorsal", "RS"), ("ventral", "RS")),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    source = pd.read_csv(ACTIVITY_SOURCE)
    source = source.loc[source["region_call"].isin(["dorsal", "ventral"])].copy()
    source["region"] = source["region_call"]
    source["legacy_firing_rate_hz"] = pd.to_numeric(
        source["firing_rate_hz_recomputed"], errors="coerce"
    )

    ventral = _load_classifier(VENTRAL_ROOT, "ventral")
    dorsal = _load_classifier(DORSAL_ROOT, "dorsal")
    classifier = pd.concat([dorsal, ventral], ignore_index=True)
    classifier["rs_fs_class"] = classifier["ttr90_confidence_category"].map(CLASS_MAP)
    classifier = classifier.loc[classifier["rs_fs_class"].isin(["FS", "RS"])].copy()

    unit_columns = [
        "unit_key",
        "legacy_firing_rate_hz",
        "burst_rate_per_min",
        "mean_firing_rate_within_bursts_hz",
        "mean_burst_duration_ms",
        "mean_interburst_interval_s",
        "mean_spikes_per_burst",
    ]
    units = classifier.merge(
        source[unit_columns],
        on="unit_key",
        how="left",
        validate="one_to_one",
    )
    if units["analyzer_path"].isna().any():
        missing = units.loc[units["analyzer_path"].isna(), "unit_key"].tolist()
        raise ValueError(f"activity metadata missing for {len(missing)} units: {missing[:10]}")

    p999 = _recompute_p999(units)
    units = units.merge(p999, on="unit_key", validate="one_to_one")
    for metric, _, _ in METRICS:
        units[metric] = pd.to_numeric(units[metric], errors="coerce")

    channel_keys = [
        "region",
        "recording",
        "well",
        "rs_fs_class",
        "template_best_channel_id",
    ]
    channel = (
        units.groupby(channel_keys, dropna=False)
        .agg(
            unit_count=("unit_key", "size"),
            **{metric: (metric, "mean") for metric, _, _ in METRICS},
        )
        .reset_index()
    )
    organoid_keys = ["region", "recording", "well", "rs_fs_class"]
    organoid = (
        channel.groupby(organoid_keys, dropna=False)
        .agg(
            unit_count=("unit_count", "sum"),
            best_channel_count=("template_best_channel_id", "size"),
            **{metric: (metric, "mean") for metric, _, _ in METRICS},
        )
        .reset_index()
    )

    group_summary = _group_summary(organoid)
    tests = _tests(organoid)
    tests["fdr_bh_q"] = _bh_fdr(tests["p_value"].to_numpy(float))

    units.to_csv(output_dir / "cytoview_dv_ttr90_high_confidence_unit_metrics.csv", index=False)
    channel.to_csv(output_dir / "cytoview_dv_ttr90_channel_metrics.csv", index=False)
    organoid.to_csv(output_dir / "cytoview_dv_ttr90_organoid_class_metrics.csv", index=False)
    group_summary.to_csv(output_dir / "cytoview_dv_ttr90_group_summary.csv", index=False)
    tests.to_csv(output_dir / "cytoview_dv_ttr90_comparisons.csv", index=False)
    figure_paths = _plot(organoid, output_dir)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "unit_count": int(len(units)),
        "unit_counts": {
            f"{region}_{class_label}": int(
                (units["region"].eq(region) & units["rs_fs_class"].eq(class_label)).sum()
            )
            for region, class_label in GROUP_ORDER
        },
        "organoid_class_observation_counts": {
            f"{region}_{class_label}": int(
                (
                    organoid["region"].eq(region)
                    & organoid["rs_fs_class"].eq(class_label)
                ).sum()
            )
            for region, class_label in GROUP_ORDER
        },
        "aggregation": (
            "unit metrics averaged within best-template channel and class; channel means "
            "then averaged within recording/well organoid and class"
        ),
        "processing_versions": "non-LFP recording versions retained as separate observations",
        "p999_method": {
            "source": "recomputed from spike times",
            "gaussian_sigma_ms": 50.0,
            "evaluation_bin_ms": 1.0,
            "minimum_spikes": 30,
        },
        "figures": [str(path) for path in figure_paths],
    }
    (output_dir / "cytoview_dv_ttr90_activity_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))
    print("\nGroup summary:")
    print(group_summary.to_string(index=False))
    print("\nComparisons:")
    print(tests.to_string(index=False))
    return 0


def _load_classifier(root: Path, region: str) -> pd.DataFrame:
    metrics = pd.read_csv(
        root
        / "ttr90_canonical_negative_classifier"
        / "ttr90_canonical_negative_unit_metrics.csv"
    )
    audit = pd.read_csv(
        root / "waveform_source_audit" / "waveform_source_audit_unit_metrics.csv",
        usecols=["unit_key", "template_best_channel_id", "template_best_channel_index"],
    )
    if region == "ventral":
        metrics = metrics.loc[metrics["source_platform"].eq("CytoView")].copy()
    metrics["region"] = region
    return metrics.merge(audit, on="unit_key", validate="one_to_one")


def _recompute_p999(units: pd.DataFrame) -> pd.DataFrame:
    import spikeinterface.full as si

    rows: list[dict[str, object]] = []
    for analyzer_number, (path_text, group) in enumerate(
        units.groupby("analyzer_path", sort=False), start=1
    ):
        print(
            f"[{analyzer_number}/{units['analyzer_path'].nunique()}] "
            f"{path_text} ({len(group)} units)",
            flush=True,
        )
        analyzer = si.load_sorting_analyzer(Path(str(path_text)), load_extensions=True)
        sorting = analyzer.sorting
        sampling_frequency = float(analyzer.recording.get_sampling_frequency())
        duration_s = float(analyzer.recording.get_total_duration())
        unit_ids = {_unit_token(value): value for value in sorting.get_unit_ids()}
        for _, row in group.iterrows():
            token = _unit_token(row["unit_id"])
            if token not in unit_ids:
                raise ValueError(f"unit {row['unit_id']} missing in {path_text}")
            frames = np.asarray(
                sorting.get_unit_spike_train(unit_ids[token]), dtype=np.int64
            )
            spike_times_s = frames / sampling_frequency
            result = summarize_smoothed_inverse_isi_rate(
                spike_times_s,
                duration_s,
                gaussian_sigma_ms=50.0,
                evaluation_bin_ms=1.0,
                min_spikes=30,
            )
            rows.append(
                {
                    "unit_key": row["unit_key"],
                    "inverse_isi_gaussian_temporal_p99_9_hz": result[
                        "inverse_isi_gaussian_temporal_p99_9_hz"
                    ],
                    "p999_recomputed_spike_count": int(frames.size),
                    "p999_recomputed_duration_s": duration_s,
                }
            )
    result = pd.DataFrame(rows)
    if len(result) != len(units) or result["unit_key"].nunique() != len(units):
        raise ValueError("P99.9 recomputation did not preserve the unit roster")
    return result


def _unit_token(value: object) -> str:
    text = str(value)
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return text


def _group_summary(organoid: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metric, label, unit in METRICS:
        for region, class_label in GROUP_ORDER:
            values = pd.to_numeric(
                organoid.loc[
                    organoid["region"].eq(region)
                    & organoid["rs_fs_class"].eq(class_label),
                    metric,
                ],
                errors="coerce",
            ).dropna()
            rows.append(
                {
                    "metric": metric,
                    "metric_label": label,
                    "metric_unit": unit,
                    "region": region,
                    "rs_fs_class": class_label,
                    "organoid_observation_count": int(len(values)),
                    "mean": float(values.mean()) if len(values) else np.nan,
                    "sem": float(values.sem()) if len(values) > 1 else np.nan,
                    "median": float(values.median()) if len(values) else np.nan,
                    "q25": float(values.quantile(0.25)) if len(values) else np.nan,
                    "q75": float(values.quantile(0.75)) if len(values) else np.nan,
                }
            )
    return pd.DataFrame(rows)


def _tests(organoid: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metric, label, unit in METRICS:
        for comparison, group_a, group_b in COMPARISONS:
            a = pd.to_numeric(
                organoid.loc[
                    organoid["region"].eq(group_a[0])
                    & organoid["rs_fs_class"].eq(group_a[1]),
                    metric,
                ],
                errors="coerce",
            ).dropna()
            b = pd.to_numeric(
                organoid.loc[
                    organoid["region"].eq(group_b[0])
                    & organoid["rs_fs_class"].eq(group_b[1]),
                    metric,
                ],
                errors="coerce",
            ).dropna()
            if len(a) and len(b):
                statistic, p_value = mannwhitneyu(a, b, alternative="two-sided")
            else:
                statistic, p_value = np.nan, np.nan
            rows.append(
                {
                    "metric": metric,
                    "metric_label": label,
                    "metric_unit": unit,
                    "comparison": comparison,
                    "group_a": f"{group_a[0]}_{group_a[1]}",
                    "group_b": f"{group_b[0]}_{group_b[1]}",
                    "group_a_n": int(len(a)),
                    "group_b_n": int(len(b)),
                    "group_a_median": float(a.median()) if len(a) else np.nan,
                    "group_b_median": float(b.median()) if len(b) else np.nan,
                    "mann_whitney_u": float(statistic),
                    "p_value": float(p_value),
                }
            )
    return pd.DataFrame(rows)


def _bh_fdr(p_values: np.ndarray) -> np.ndarray:
    result = np.full(p_values.shape, np.nan, dtype=float)
    finite = np.flatnonzero(np.isfinite(p_values))
    if finite.size == 0:
        return result
    order = finite[np.argsort(p_values[finite])]
    ranked = p_values[order] * finite.size / np.arange(1, finite.size + 1)
    adjusted = np.minimum.accumulate(ranked[::-1])[::-1]
    result[order] = np.minimum(adjusted, 1.0)
    return result


def _plot(organoid: pd.DataFrame, output_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"FS": "#B8742A", "RS": "#58758E"}
    markers = {"dorsal": "o", "ventral": "s"}
    fig, axes = plt.subplots(1, len(METRICS), figsize=(17.5, 3.7), constrained_layout=True)
    rng = np.random.default_rng(20260714)
    for axis, (metric, label, unit) in zip(axes, METRICS, strict=True):
        for position, (region, class_label) in enumerate(GROUP_ORDER):
            values = pd.to_numeric(
                organoid.loc[
                    organoid["region"].eq(region)
                    & organoid["rs_fs_class"].eq(class_label),
                    metric,
                ],
                errors="coerce",
            ).dropna()
            jitter = rng.uniform(-0.08, 0.08, len(values))
            axis.scatter(
                position + jitter,
                values,
                s=20,
                marker=markers[region],
                color=colors[class_label],
                alpha=0.58,
                linewidths=0,
            )
            if len(values):
                axis.errorbar(
                    position,
                    values.mean(),
                    yerr=values.sem() if len(values) > 1 else 0,
                    fmt="D",
                    ms=4.2,
                    mfc="white",
                    mec="#222222",
                    ecolor="#222222",
                    capsize=2.5,
                    lw=0.8,
                    zorder=4,
                )
        axis.set_xticks(range(4), ["D FS", "D RS", "V FS", "V RS"], rotation=40, ha="right")
        axis.set_title(label, fontsize=8)
        axis.set_ylabel(unit, fontsize=7)
        axis.spines[["top", "right"]].set_visible(False)
        axis.tick_params(labelsize=6.3, length=2.5)
        axis.grid(axis="y", color="#E5E5E5", lw=0.5)
    fig.suptitle(
        "Channel-weighted organoid activity of high-confidence TTR90 FS/RS units",
        fontsize=10,
    )
    png = output_dir / "cytoview_dv_ttr90_fsrs_activity_comparison.png"
    pdf = output_dir / "cytoview_dv_ttr90_fsrs_activity_comparison.pdf"
    svg = output_dir / "cytoview_dv_ttr90_fsrs_activity_comparison.svg"
    fig.savefig(png, dpi=600, facecolor="white")
    fig.savefig(pdf, facecolor="white")
    fig.savefig(svg, facecolor="white")
    plt.close(fig)
    return [png, pdf, svg]


if __name__ == "__main__":
    raise SystemExit(main())
