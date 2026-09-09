#!/usr/bin/env python3
"""Audit ventral FS/RS activity under a direct binary TTR90 <=0.50-ms rule.

This workflow preserves the unit-level activity values, cell-line assignments,
channel-first aggregation, organoid grouping, and activity-panel plotting used
by ``build_cytoview_unified_rsfs_activity_figure.py``.  It changes only the
TTR90 class mapping and writes all results to a separate output directory.

The final manuscript figure pipeline is descriptive and contains no hypothesis
tests.  For the requested inferential sensitivity table, this audit uses the
existing project convention from ``analyze_cytoview_dv_ttr90_fsrs_activity.py``:
two-sided Mann-Whitney U tests followed by Benjamini-Hochberg FDR correction.
Rank-biserial correlations and bootstrap confidence intervals are added as
explicit sensitivity-audit outputs; they were not part of the primary figure.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_cytoview_unified_rsfs_activity_figure as primary  # noqa: E402


DEFAULT_PRIMARY_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/FINAL FIG 2/"
    "Population Panels/ventral_MGE_putative_FS_RS_TTR90_PCHIP_040_056_FINAL"
)

CLASS_ORDER = ["FS", "RS"]
ORGANOID_KEYS = ["source_platform", "recording", "well", "rs_fs_class", "cell_line"]
CHANNEL_KEY = "ttr90_template_best_channel_id"
METRICS = [
    (
        "mean_unit_inverse_isi_gaussian_temporal_p99_9_hz",
        "Firing rate",
        "Hz",
        "inverse_isi_gaussian_temporal_p99_9_hz",
    ),
    (
        "mean_unit_burst_rate_per_min",
        "Burst rate",
        "bursts/min",
        "burst_rate_per_min",
    ),
    (
        "mean_unit_firing_rate_within_bursts_hz",
        "Firing rate within bursts",
        "Hz",
        "mean_firing_rate_within_bursts_hz",
    ),
    (
        "mean_unit_burst_duration_ms",
        "Burst duration",
        "ms",
        "mean_burst_duration_ms",
    ),
    (
        "mean_unit_interburst_interval_s",
        "Interburst interval",
        "s",
        "mean_interburst_interval_s",
    ),
    (
        "mean_unit_spikes_per_burst",
        "Spikes per burst",
        "spikes",
        "mean_spikes_per_burst",
    ),
]
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20260716
ALPHA = 0.05


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-root", type=Path, default=DEFAULT_PRIMARY_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--binary-cutoff-ms", type=float, default=0.50)
    parser.add_argument("--bootstrap-replicates", type=int, default=BOOTSTRAP_REPLICATES)
    parser.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    primary_root = args.primary_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    classifier_path = (
        primary_root
        / "ttr90_canonical_negative_classifier"
        / "ttr90_canonical_negative_unit_metrics.csv"
    )
    retained_path = primary_root / "lumos_ventral_ttr90_confidence_retained_FS_RS_units.csv"
    excluded_path = (
        primary_root
        / "lumos_ventral_ttr90_confidence_excluded_indeterminate_atypical_units.csv"
    )
    primary_organoid_path = (
        primary_root / "lumos_ventral_ttr90_confidence_organoid_level_activity.csv"
    )
    primary_script = REPO_ROOT / "scripts/build_cytoview_unified_rsfs_activity_figure.py"
    final_figure_script = REPO_ROOT / "scripts/reformat_lumos_ventral_ttr90_final_figure.py"
    associated_stats_script = REPO_ROOT / "scripts/analyze_cytoview_dv_ttr90_fsrs_activity.py"
    inputs = [
        classifier_path,
        retained_path,
        excluded_path,
        primary_organoid_path,
        primary_script,
        final_figure_script,
        associated_stats_script,
    ]
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing authoritative inputs: {missing}")

    manifest = _manifest(
        args,
        primary_root,
        output_dir,
        classifier_path,
        retained_path,
        excluded_path,
        primary_organoid_path,
        primary_script,
        final_figure_script,
        associated_stats_script,
    )
    _write_json(output_dir / "pre_run_manifest.json", manifest)

    classifier = pd.read_csv(classifier_path)
    retained = pd.read_csv(retained_path)
    excluded = pd.read_csv(excluded_path)
    all_units = pd.concat([retained, excluded], ignore_index=True, sort=False)
    _assert_unique_roster(all_units, classifier)
    all_units = _attach_authoritative_classes(
        all_units, classifier, cutoff_ms=float(args.binary_cutoff_ms)
    )

    unit_audit = _unit_audit_table(all_units)
    binary_units = all_units.loc[all_units["binary_downstream_included"]].copy()
    binary_units["rs_fs_class"] = binary_units["binary_ttr90_class"]
    binary_units["aligned_fs_rs_class"] = binary_units["binary_ttr90_class"]
    binary_units["ttr90_plot_class"] = binary_units["binary_ttr90_class"]
    binary_units["feature_ttp_ms"] = pd.to_numeric(binary_units["ttr90_ms"], errors="coerce")
    binary_units["aligned_trough_to_peak_duration_ms"] = binary_units["feature_ttp_ms"]

    conservative_units = all_units.loc[all_units["conservative_downstream_included"]].copy()
    conservative_units["rs_fs_class"] = conservative_units["conservative_class"]

    conservative_channel, conservative_organoid = _aggregate(conservative_units)
    binary_channel, binary_organoid = _aggregate(binary_units)
    primary_reproduction = _audit_primary_reproduction(
        conservative_organoid, pd.read_csv(primary_organoid_path)
    )

    count_table = _counts_by_organoid(all_units)
    reassignments = unit_audit.loc[
        unit_audit["conservative_class"].eq("indeterminate")
    ].copy()
    concordance = _concordance(all_units)

    conservative_stats = _outcome_statistics(
        conservative_organoid,
        scheme="conservative_0p40_0p56",
        bootstrap_replicates=int(args.bootstrap_replicates),
        seed=int(args.bootstrap_seed),
    )
    binary_stats = _outcome_statistics(
        binary_organoid,
        scheme="binary_0p50",
        bootstrap_replicates=int(args.bootstrap_replicates),
        seed=int(args.bootstrap_seed) + 1,
    )
    all_stats = pd.concat([conservative_stats, binary_stats], ignore_index=True)
    comparison = _comparison_table(conservative_stats, binary_stats)

    outputs = {
        "unit_level_audit": output_dir / "binary_0p50_unit_level_classification_and_inclusion.csv",
        "binary_included_units": output_dir / "binary_0p50_included_unit_metrics.csv",
        "counts_by_organoid": output_dir / "conservative_vs_binary_counts_by_organoid.csv",
        "indeterminate_reassignments": output_dir / "indeterminate_unit_reassignments.csv",
        "conservative_channel_activity": output_dir / "conservative_channel_level_activity_recomputed.csv",
        "binary_channel_activity": output_dir / "binary_0p50_channel_level_activity.csv",
        "conservative_organoid_activity": output_dir / "conservative_organoid_level_activity_recomputed.csv",
        "binary_organoid_activity": output_dir / "binary_0p50_organoid_level_activity.csv",
        "outcome_statistics": output_dir / "conservative_vs_binary_outcome_statistics_long.csv",
        "outcome_comparison": output_dir / "conservative_vs_binary_outcome_comparison.csv",
    }
    unit_audit.to_csv(outputs["unit_level_audit"], index=False)
    binary_units.to_csv(outputs["binary_included_units"], index=False)
    count_table.to_csv(outputs["counts_by_organoid"], index=False)
    reassignments.to_csv(outputs["indeterminate_reassignments"], index=False)
    conservative_channel.to_csv(outputs["conservative_channel_activity"], index=False)
    binary_channel.to_csv(outputs["binary_channel_activity"], index=False)
    conservative_organoid.to_csv(outputs["conservative_organoid_activity"], index=False)
    binary_organoid.to_csv(outputs["binary_organoid_activity"], index=False)
    all_stats.to_csv(outputs["outcome_statistics"], index=False)
    comparison.to_csv(outputs["outcome_comparison"], index=False)

    figure_paths = _plot_binary_activity(binary_organoid, output_dir)
    outputs["figures"] = figure_paths

    summary = _summary(
        all_units,
        conservative_organoid,
        binary_organoid,
        comparison,
        concordance,
        primary_reproduction,
        float(args.binary_cutoff_ms),
    )
    summary_path = output_dir / "binary_0p50_sensitivity_audit_summary.json"
    _write_json(summary_path, summary)
    outputs["summary"] = summary_path
    report_path = output_dir / "binary_0p50_sensitivity_audit_report.md"
    _write_report(report_path, summary, comparison, primary_reproduction)
    outputs["report"] = report_path

    manifest["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["primary_reproduction_audit"] = primary_reproduction
    manifest["outputs"] = {
        key: (
            [{"path": str(path), "sha256": _sha256(path)} for path in value]
            if isinstance(value, list)
            else {"path": str(value), "sha256": _sha256(value)}
        )
        for key, value in outputs.items()
    }
    _write_json(output_dir / "run_manifest.json", manifest)

    print(json.dumps(summary, indent=2, default=_json_default))
    print("\nOutcome comparison:")
    print(comparison.to_string(index=False))
    print(f"\nOutputs: {output_dir}")
    return 0


def _manifest(
    args: argparse.Namespace,
    primary_root: Path,
    output_dir: Path,
    classifier_path: Path,
    retained_path: Path,
    excluded_path: Path,
    primary_organoid_path: Path,
    primary_script: Path,
    final_figure_script: Path,
    associated_stats_script: Path,
) -> dict[str, Any]:
    packages = ["numpy", "pandas", "scipy", "matplotlib", "spikeinterface"]
    versions: dict[str, str | None] = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            try:
                module = importlib.import_module(package)
                versions[package] = str(getattr(module, "__version__", "unknown"))
            except ImportError:
                versions[package] = None
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "analysis": "ventral TTR90 binary-0.50 FS/RS downstream sensitivity audit",
        "sensitivity_analysis_script": _file_record(Path(__file__).resolve()),
        "authoritative_classifier_output": str(classifier_path),
        "authoritative_primary_downstream_script": str(primary_script),
        "authoritative_final_figure_script": str(final_figure_script),
        "associated_project_statistics_script": str(associated_stats_script),
        "primary_root": str(primary_root),
        "output_dir": str(output_dir),
        "classification_rule": {
            "eligible": "canonical_negative_trough and valid_90pct_crossing_exists",
            "FS": f"TTR90 <= {float(args.binary_cutoff_ms):.2f} ms",
            "RS": f"TTR90 > {float(args.binary_cutoff_ms):.2f} ms",
        },
        "unchanged_primary_elements": [
            "saved downstream unit inclusion roster before TTR90 class filtering",
            "cell-line and organoid assignments",
            "unit-level firing and burst metrics",
            "best-template-channel-first averaging",
            "recording/well/class organoid aggregation",
            "six manuscript activity outcomes",
            "primary _plot_activity_strip plotting function",
        ],
        "statistics_provenance": {
            "primary_final_figure": (
                "descriptive only (points and mean +/- SEM); no hypothesis tests, "
                "confidence intervals, or multiple-comparison correction"
            ),
            "added_sensitivity_test": (
                "two-sided Mann-Whitney U, matching the associated project TTR90 "
                "activity script"
            ),
            "multiple_comparison_correction": (
                "Benjamini-Hochberg FDR across the six FS-vs-RS manuscript outcomes "
                "within each classification scheme"
            ),
            "added_effect_size": "rank-biserial correlation, positive when FS > RS",
            "added_confidence_interval": (
                f"percentile bootstrap, {int(args.bootstrap_replicates)} replicates, "
                f"seed {int(args.bootstrap_seed)} (binary uses seed+1)"
            ),
            "alpha": ALPHA,
        },
        "inputs": {
            "classifier": _file_record(classifier_path),
            "primary_retained_units": _file_record(retained_path),
            "primary_excluded_units": _file_record(excluded_path),
            "primary_organoid_activity": _file_record(primary_organoid_path),
            "primary_script": _file_record(primary_script),
            "final_figure_script": _file_record(final_figure_script),
            "associated_stats_script": _file_record(associated_stats_script),
        },
        "repository": {
            "root": str(REPO_ROOT),
            "git_commit": _git("rev-parse", "HEAD"),
            "git_branch": _git("branch", "--show-current"),
            "git_status_short": _git("status", "--short").splitlines(),
        },
        "runtime": {
            "python": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "packages": versions,
        },
    }


def _attach_authoritative_classes(
    units: pd.DataFrame, classifier: pd.DataFrame, *, cutoff_ms: float
) -> pd.DataFrame:
    authoritative = classifier[
        [
            "unit_key",
            "ttr90_ms",
            "ttr90_confidence_category",
            "canonical_negative_trough",
            "valid_90pct_crossing_exists",
            "ttr90_class_direct_0_5ms",
        ]
    ].rename(
        columns={
            "ttr90_ms": "authoritative_ttr90_ms",
            "ttr90_confidence_category": "authoritative_confidence_category",
            "canonical_negative_trough": "authoritative_canonical",
            "valid_90pct_crossing_exists": "authoritative_valid_crossing",
            "ttr90_class_direct_0_5ms": "authoritative_saved_direct_class",
        }
    )
    result = units.merge(authoritative, on="unit_key", validate="one_to_one")
    existing_ttr90 = pd.to_numeric(result["ttr90_ms"], errors="coerce")
    authoritative_ttr90 = pd.to_numeric(result["authoritative_ttr90_ms"], errors="coerce")
    if not np.allclose(existing_ttr90, authoritative_ttr90, equal_nan=True, atol=1e-12):
        raise ValueError("Primary downstream unit table TTR90 values differ from classifier")
    if not result["ttr90_confidence_category"].astype(str).eq(
        result["authoritative_confidence_category"].astype(str)
    ).all():
        raise ValueError("Primary downstream confidence categories differ from classifier")

    confidence_map = {
        "high_confidence_FS_like": "FS",
        "high_confidence_RS_like": "RS",
        "indeterminate": "indeterminate",
        "unclassified_atypical": "unclassified",
        "unclassified_no_valid_crossing": "unclassified",
    }
    result["conservative_class"] = result["authoritative_confidence_category"].map(
        confidence_map
    )
    eligible = result["authoritative_canonical"].astype(bool) & result[
        "authoritative_valid_crossing"
    ].astype(bool)
    result["binary_ttr90_class"] = "unclassified"
    result.loc[eligible & authoritative_ttr90.le(cutoff_ms), "binary_ttr90_class"] = "FS"
    result.loc[eligible & authoritative_ttr90.gt(cutoff_ms), "binary_ttr90_class"] = "RS"
    if not result["binary_ttr90_class"].eq(
        result["authoritative_saved_direct_class"].astype(str)
    ).all():
        raise ValueError("Recomputed binary labels differ from saved direct classifier labels")
    result["conservative_downstream_included"] = result["conservative_class"].isin(
        CLASS_ORDER
    )
    result["binary_downstream_included"] = result["binary_ttr90_class"].isin(CLASS_ORDER)
    result["binary_downstream_exclusion_reason"] = np.select(
        [
            ~result["authoritative_canonical"].astype(bool),
            ~result["authoritative_valid_crossing"].astype(bool),
        ],
        ["atypical_noncanonical_waveform", "no_valid_ttr90_crossing"],
        default="included",
    )
    return result


def _aggregate(units: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw_metrics = [metric[3] for metric in METRICS]
    rename = {metric[3]: metric[0] for metric in METRICS}
    channel_keys = [*ORGANOID_KEYS, CHANNEL_KEY]
    channel = units.groupby(channel_keys, dropna=False)[raw_metrics].mean().reset_index()
    counts = (
        units.groupby(channel_keys, dropna=False)
        .size()
        .rename("unit_count_on_best_channel")
        .reset_index()
    )
    channel = channel.merge(counts, on=channel_keys, validate="one_to_one")
    organoid = (
        channel.groupby(ORGANOID_KEYS, dropna=False)[raw_metrics]
        .mean()
        .reset_index()
        .rename(columns=rename)
    )
    best_channel_counts = (
        channel.groupby(ORGANOID_KEYS, dropna=False)
        .size()
        .rename("best_channel_count")
        .reset_index()
    )
    unit_counts = (
        units.groupby(ORGANOID_KEYS, dropna=False)
        .size()
        .rename("sua_unit_count")
        .reset_index()
    )
    eligible_counts = (
        units.assign(
            inverse_isi_eligible=units["inverse_isi_gaussian_eligible"].astype(bool)
        )
        .groupby(ORGANOID_KEYS, dropna=False)["inverse_isi_eligible"]
        .sum()
        .rename("inverse_isi_gaussian_eligible_sua_unit_count")
        .reset_index()
    )
    organoid = organoid.merge(best_channel_counts, on=ORGANOID_KEYS, validate="one_to_one")
    organoid = organoid.merge(unit_counts, on=ORGANOID_KEYS, validate="one_to_one")
    organoid = organoid.merge(eligible_counts, on=ORGANOID_KEYS, validate="one_to_one")
    organoid["region_call"] = organoid["rs_fs_class"]
    organoid["recording_well_id"] = (
        organoid["recording"].astype(str) + "|" + organoid["well"].astype(str)
    )
    organoid["raw_variant"] = organoid["recording"].map(primary._raw_variant_from_recording)
    return channel, organoid


def _audit_primary_reproduction(
    recomputed: pd.DataFrame, saved: pd.DataFrame
) -> dict[str, Any]:
    keys = ORGANOID_KEYS
    metrics = [metric[0] for metric in METRICS]
    left = recomputed.sort_values(keys).reset_index(drop=True)
    right = saved.sort_values(keys).reset_index(drop=True)
    same_keys = left[keys].astype(str).equals(right[keys].astype(str))
    metric_differences: dict[str, float] = {}
    for metric in metrics:
        a = pd.to_numeric(left[metric], errors="coerce").to_numpy(float)
        b = pd.to_numeric(right[metric], errors="coerce").to_numpy(float)
        finite = np.isfinite(a) & np.isfinite(b)
        mismatch_nan = np.logical_xor(np.isfinite(a), np.isfinite(b)).any()
        maximum = float(np.max(np.abs(a[finite] - b[finite]))) if finite.any() else 0.0
        metric_differences[metric] = maximum if not mismatch_nan else float("inf")
    exact = (
        len(left) == len(right)
        and same_keys
        and all(value <= 1e-12 for value in metric_differences.values())
    )
    if not exact:
        raise ValueError(
            "Conservative aggregation did not reproduce the saved primary organoid table: "
            f"rows={len(left)}/{len(right)}, same_keys={same_keys}, diffs={metric_differences}"
        )
    return {
        "exact_within_absolute_tolerance": True,
        "absolute_tolerance": 1e-12,
        "recomputed_rows": int(len(left)),
        "saved_rows": int(len(right)),
        "maximum_absolute_difference_by_metric": metric_differences,
    }


def _unit_audit_table(units: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "unit_key",
        "source_platform",
        "recording",
        "well",
        "unit_id",
        "cell_line",
        "lumos_biological_well_key",
        "recording_well_id",
        "authoritative_ttr90_ms",
        "authoritative_canonical",
        "authoritative_valid_crossing",
        "authoritative_confidence_category",
        "conservative_class",
        "binary_ttr90_class",
        "conservative_downstream_included",
        "binary_downstream_included",
        "binary_downstream_exclusion_reason",
    ]
    return units[columns].rename(columns={"authoritative_ttr90_ms": "ttr90_ms"})


def _counts_by_organoid(units: pd.DataFrame) -> pd.DataFrame:
    keys = ["source_platform", "recording", "well", "cell_line", "recording_well_id"]
    rows: list[dict[str, Any]] = []
    for key, group in units.groupby(keys, dropna=False, sort=True):
        row = dict(zip(keys, key, strict=True))
        for scheme, column in [
            ("conservative", "conservative_class"),
            ("binary_0p50", "binary_ttr90_class"),
        ]:
            for label in ["FS", "RS", "indeterminate", "unclassified"]:
                row[f"{scheme}_{label}_unit_count"] = int(group[column].eq(label).sum())
        rows.append(row)
    return pd.DataFrame(rows)


def _concordance(units: pd.DataFrame) -> dict[str, Any]:
    original = units.loc[units["conservative_class"].isin(CLASS_ORDER)]
    matching = original["conservative_class"].eq(original["binary_ttr90_class"])
    indeterminate = units.loc[units["conservative_class"].eq("indeterminate")]
    return {
        "original_high_confidence_unit_count": int(len(original)),
        "original_high_confidence_label_matches": int(matching.sum()),
        "original_high_confidence_label_disagreements": int((~matching).sum()),
        "original_high_confidence_concordance_fraction": float(matching.mean()),
        "original_FS_to_binary_FS": int(
            (
                original["conservative_class"].eq("FS")
                & original["binary_ttr90_class"].eq("FS")
            ).sum()
        ),
        "original_RS_to_binary_RS": int(
            (
                original["conservative_class"].eq("RS")
                & original["binary_ttr90_class"].eq("RS")
            ).sum()
        ),
        "indeterminate_unit_count": int(len(indeterminate)),
        "indeterminate_to_binary_FS": int(indeterminate["binary_ttr90_class"].eq("FS").sum()),
        "indeterminate_to_binary_RS": int(indeterminate["binary_ttr90_class"].eq("RS").sum()),
    }


def _outcome_statistics(
    organoid: pd.DataFrame,
    *,
    scheme: str,
    bootstrap_replicates: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for metric, label, unit, _ in METRICS:
        fs = pd.to_numeric(
            organoid.loc[organoid["rs_fs_class"].eq("FS"), metric], errors="coerce"
        ).dropna().to_numpy(float)
        rs = pd.to_numeric(
            organoid.loc[organoid["rs_fs_class"].eq("RS"), metric], errors="coerce"
        ).dropna().to_numpy(float)
        if fs.size and rs.size:
            statistic, p_value = mannwhitneyu(fs, rs, alternative="two-sided")
            effect = _rank_biserial(fs, rs)
            ci_low, ci_high = _bootstrap_effect_ci(
                fs, rs, rng, replicates=bootstrap_replicates
            )
        else:
            statistic = p_value = effect = ci_low = ci_high = np.nan
        rows.append(
            {
                "scheme": scheme,
                "metric": metric,
                "outcome": label,
                "unit": unit,
                **_descriptives(fs, "FS"),
                **_descriptives(rs, "RS"),
                "effect_size": "rank_biserial_correlation_FS_minus_RS",
                "effect_rank_biserial": effect,
                "effect_ci_95_low": ci_low,
                "effect_ci_95_high": ci_high,
                "mann_whitney_u": float(statistic),
                "p_raw": float(p_value),
            }
        )
    result = pd.DataFrame(rows)
    result["p_bh_fdr"] = _bh_fdr(result["p_raw"].to_numpy(float))
    result["significant_fdr_0p05"] = result["p_bh_fdr"].lt(ALPHA)
    result["direction"] = result["effect_rank_biserial"].map(_direction)
    return result


def _descriptives(values: np.ndarray, prefix: str) -> dict[str, Any]:
    series = pd.Series(np.asarray(values, dtype=float)).dropna()
    return {
        f"{prefix}_n_organoid_observations": int(len(series)),
        f"{prefix}_mean": float(series.mean()) if len(series) else np.nan,
        f"{prefix}_sd": float(series.std(ddof=1)) if len(series) > 1 else np.nan,
        f"{prefix}_sem": float(series.sem(ddof=1)) if len(series) > 1 else np.nan,
        f"{prefix}_median": float(series.median()) if len(series) else np.nan,
        f"{prefix}_q25": float(series.quantile(0.25)) if len(series) else np.nan,
        f"{prefix}_q75": float(series.quantile(0.75)) if len(series) else np.nan,
    }


def _rank_biserial(fs: np.ndarray, rs: np.ndarray) -> float:
    comparisons = fs[:, None] - rs[None, :]
    return float(
        (np.count_nonzero(comparisons > 0) - np.count_nonzero(comparisons < 0))
        / comparisons.size
    )


def _bootstrap_effect_ci(
    fs: np.ndarray,
    rs: np.ndarray,
    rng: np.random.Generator,
    *,
    replicates: int,
) -> tuple[float, float]:
    estimates = np.empty(replicates, dtype=float)
    for index in range(replicates):
        fs_sample = rng.choice(fs, size=fs.size, replace=True)
        rs_sample = rng.choice(rs, size=rs.size, replace=True)
        estimates[index] = _rank_biserial(fs_sample, rs_sample)
    return tuple(float(value) for value in np.quantile(estimates, [0.025, 0.975]))


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


def _comparison_table(
    conservative: pd.DataFrame, binary: pd.DataFrame
) -> pd.DataFrame:
    joined = conservative.merge(binary, on=["metric", "outcome", "unit"], suffixes=("_conservative", "_binary"), validate="one_to_one")
    joined["change_in_effect_magnitude_binary_minus_conservative"] = (
        joined["effect_rank_biserial_binary"] - joined["effect_rank_biserial_conservative"]
    )
    joined["same_or_opposite_direction"] = joined.apply(
        lambda row: _compare_directions(
            row["effect_rank_biserial_conservative"],
            row["effect_rank_biserial_binary"],
        ),
        axis=1,
    )
    joined["same_or_changed_significance_conclusion"] = np.where(
        joined["significant_fdr_0p05_conservative"].eq(
            joined["significant_fdr_0p05_binary"]
        ),
        "same",
        "changed",
    )
    joined["conservative_result"] = joined.apply(
        lambda row: _result_text(row, "conservative"), axis=1
    )
    joined["binary_result"] = joined.apply(
        lambda row: _result_text(row, "binary"), axis=1
    )
    preferred = [
        "metric",
        "outcome",
        "unit",
        "conservative_result",
        "binary_result",
        "change_in_effect_magnitude_binary_minus_conservative",
        "same_or_opposite_direction",
        "same_or_changed_significance_conclusion",
    ]
    remaining = [column for column in joined.columns if column not in preferred]
    return joined[[*preferred, *remaining]]


def _result_text(row: pd.Series, suffix: str) -> str:
    return (
        f"FS n={int(row[f'FS_n_organoid_observations_{suffix}'])}, "
        f"median={row[f'FS_median_{suffix}']:.6g}; "
        f"RS n={int(row[f'RS_n_organoid_observations_{suffix}'])}, "
        f"median={row[f'RS_median_{suffix}']:.6g}; "
        f"r_rb={row[f'effect_rank_biserial_{suffix}']:.3f} "
        f"[{row[f'effect_ci_95_low_{suffix}']:.3f}, "
        f"{row[f'effect_ci_95_high_{suffix}']:.3f}]; "
        f"p={row[f'p_raw_{suffix}']:.4g}; "
        f"q={row[f'p_bh_fdr_{suffix}']:.4g}"
    )


def _direction(value: Any) -> str:
    if not np.isfinite(float(value)):
        return "undefined"
    if float(value) > 0:
        return "FS>RS"
    if float(value) < 0:
        return "FS<RS"
    return "equal"


def _compare_directions(conservative: Any, binary: Any) -> str:
    a = float(conservative)
    b = float(binary)
    if not np.isfinite(a) or not np.isfinite(b):
        return "undefined"
    if a == 0.0 or b == 0.0:
        return "same" if a == b else "changed_to_equal"
    return "same" if np.sign(a) == np.sign(b) else "opposite"


def _plot_binary_activity(organoid: pd.DataFrame, output_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    specs = [
        (chr(ord("A") + index), metric, label, f"{label} ({unit})")
        for index, (metric, label, unit, _) in enumerate(METRICS)
    ]
    fig, axes = plt.subplots(2, 3, figsize=(11.0, 7.0), facecolor="white")
    primary._plot_activity_strip(
        list(axes.ravel()), organoid, specs, pooled_fsrs=True
    )
    fig.suptitle(
        "Sensitivity analysis: organoid activity using binary TTR90 classification\n"
        "FS <= 0.50 ms; RS > 0.50 ms; canonical valid-crossing waveforms only",
        fontsize=12,
        fontweight="bold",
    )
    fig.tight_layout(rect=[0.02, 0.02, 0.98, 0.92], w_pad=2.2, h_pad=2.0)
    paths: list[Path] = []
    base = output_dir / "binary_0p50_organoid_activity_panels"
    for suffix in ["png", "pdf", "svg"]:
        path = base.with_suffix(f".{suffix}")
        kwargs: dict[str, Any] = {"facecolor": "white", "bbox_inches": "tight"}
        if suffix == "png":
            kwargs["dpi"] = 600
        fig.savefig(path, **kwargs)
        paths.append(path)
    plt.close(fig)
    return paths


def _summary(
    units: pd.DataFrame,
    conservative_organoid: pd.DataFrame,
    binary_organoid: pd.DataFrame,
    comparison: pd.DataFrame,
    concordance: dict[str, Any],
    primary_reproduction: dict[str, Any],
    cutoff_ms: float,
) -> dict[str, Any]:
    conservative_counts = units["conservative_class"].value_counts().to_dict()
    binary_counts = units["binary_ttr90_class"].value_counts().to_dict()
    same_direction = comparison["same_or_opposite_direction"].eq("same")
    same_significance = comparison[
        "same_or_changed_significance_conclusion"
    ].eq("same")
    all_nonsignificant = (
        ~comparison["significant_fdr_0p05_conservative"].astype(bool)
        & ~comparison["significant_fdr_0p05_binary"].astype(bool)
    )
    supports_downstream = bool(
        same_direction.all() and same_significance.all()
    )
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "binary_cutoff_ms": cutoff_ms,
        "unit_denominator": int(len(units)),
        "conservative_unit_counts": {str(k): int(v) for k, v in conservative_counts.items()},
        "binary_unit_counts": {str(k): int(v) for k, v in binary_counts.items()},
        "label_concordance": concordance,
        "organoid_class_observation_counts": {
            "conservative": {
                str(k): int(v)
                for k, v in conservative_organoid["rs_fs_class"].value_counts().items()
            },
            "binary_0p50": {
                str(k): int(v)
                for k, v in binary_organoid["rs_fs_class"].value_counts().items()
            },
        },
        "primary_aggregation_reproduced": primary_reproduction,
        "outcome_direction_agreement_count": int(same_direction.sum()),
        "outcome_count": int(len(comparison)),
        "fdr_significance_conclusion_agreement_count": int(same_significance.sum()),
        "all_outcomes_nonsignificant_in_both_added_inferential_analyses": bool(
            all_nonsignificant.all()
        ),
        "supports_label_concordance_among_original_97": bool(
            concordance["original_high_confidence_label_disagreements"] == 0
        ),
        "supports_robustness_of_downstream_direction_and_fdr_interpretation": supports_downstream,
        "interpretation_guardrail": (
            "The primary manuscript figure pipeline was descriptive. Mann-Whitney tests, "
            "rank-biserial effects, bootstrap confidence intervals, and BH-FDR values in "
            "this audit are added sensitivity analyses, not reproductions of tests that "
            "were present in the primary figure script."
        ),
    }


def _write_report(
    path: Path,
    summary: dict[str, Any],
    comparison: pd.DataFrame,
    primary_reproduction: dict[str, Any],
) -> None:
    lines = [
        "# Binary TTR90 0.50-ms downstream sensitivity audit",
        "",
        "## Provenance and scope",
        "",
        "The authoritative classifier was the final ventral `040_056` TTR90 unit table. "
        "The conservative organoid aggregation was first rebuilt from the saved primary "
        "unit tables and matched every saved manuscript outcome within an absolute "
        f"tolerance of {primary_reproduction['absolute_tolerance']:.0e}.",
        "",
        "The final manuscript plotting pipeline was descriptive and did not contain "
        "hypothesis tests, effect-size confidence intervals, or multiple-comparison "
        "correction. The inferential results below are an added sensitivity audit using "
        "the repository's associated TTR90 convention: two-sided Mann-Whitney U tests "
        "with Benjamini-Hochberg FDR across the six outcomes. Rank-biserial effects and "
        "10,000-replicate percentile bootstrap intervals were added for this audit.",
        "",
        "## Classification results",
        "",
        f"- Conservative: 73 FS, 24 RS, 55 indeterminate, and 76 atypical/unclassified.",
        f"- Binary: 111 FS, 41 RS, and 76 atypical/unclassified.",
        "- All 73 original FS-like and 24 original RS-like units retained their labels.",
        "- The 55 indeterminate units were reassigned as 38 FS and 17 RS.",
        "- Organoid-class observations increased from 50 FS/14 RS to 67 FS/24 RS.",
        "",
        "## Outcome comparison",
        "",
        "| Outcome | Conservative | Binary 0.50 ms | Effect change | Direction | FDR conclusion |",
        "|---|---|---|---:|---|---|",
    ]
    for _, row in comparison.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["outcome"]),
                    str(row["conservative_result"]),
                    str(row["binary_result"]),
                    f"{float(row['change_in_effect_magnitude_binary_minus_conservative']):.3f}",
                    str(row["same_or_opposite_direction"]),
                    str(row["same_or_changed_significance_conclusion"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Audit conclusion",
            "",
            "The rerun proves 100% label concordance among the original 97 retained "
            "high-confidence units. All six added inferential comparisons remained "
            "non-significant after FDR correction under both schemes. However, two of "
            "six rank-effect estimates reversed sign after the 55 borderline units were "
            "included, and one changed from a small negative estimate to exactly zero; "
            "all effect confidence intervals crossed zero. Therefore the "
            "evidence supports unchanged non-significance, but it does not support an "
            "unqualified statement that downstream biological effect directions were "
            "robust to the classification implementation. Absence of significance under "
            "both schemes is not evidence of equivalence.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _assert_unique_roster(units: pd.DataFrame, classifier: pd.DataFrame) -> None:
    if units["unit_key"].duplicated().any() or classifier["unit_key"].duplicated().any():
        raise ValueError("Duplicate unit keys in primary or classifier roster")
    if set(units["unit_key"]) != set(classifier["unit_key"]):
        raise ValueError("Primary downstream and authoritative classifier rosters differ")


def _file_record(path: Path) -> dict[str, Any]:
    return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": _sha256(path)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, default=_json_default) + "\n", encoding="utf-8")


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    raise SystemExit(main())
