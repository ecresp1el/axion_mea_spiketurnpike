#!/usr/bin/env python3
"""Audit pairwise and three-feature separation of the locked CytoView RS/FS labels."""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

JOB_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_ACTIVITY_DIR = (
    JOB_ROOT
    / "cytoview_dv_sua_spontaneous_activity_20260710_template_ptp_ge10uV_"
    "isi2ms_le3pct_exclude2_dorsal_drivers_20260710_082420"
)
DEFAULT_ALIGNMENT_DIR = JOB_ROOT / "waveform_alignment_feature_audit_20260709_cytoview"
STEM = "cytoview_rsfs_feature_separability_20260710"
CLASS_ORDER = ["FS", "RS"]
CLASS_COLORS = {"FS": "#E76F51", "RS": "#277DA1"}


FEATURES = [
    # Aligned waveform metrics. TTP is the sole class-defining feature.
    ("aligned_trough_to_peak_duration_ms", "Trough-to-peak", "TTP (ms)", "waveform"),
    ("after_spike_half_width_ms", "Spike half-width", "Half-width (ms)", "waveform"),
    ("after_repolarization_time_ms", "Repolarization time", "Repolarization time (ms)", "waveform"),
    ("after_template_ptp_best_channel_uV", "Template PTP", "Template PTP (µV)", "waveform"),
    ("after_spiketurnpike_amplitude_uV", "Spike amplitude", "Spike amplitude (µV)", "waveform"),
    ("after_pre_peak_amplitude_uV", "Pre-peak amplitude", "Pre-peak amplitude (µV)", "waveform"),
    ("after_post_peak_amplitude_uV", "Post-peak amplitude", "Post-peak amplitude (µV)", "waveform"),
    ("after_depolarization_slope_uV_per_ms", "Depolarization slope", "Depolarization slope (µV/ms)", "waveform"),
    ("after_post_trough_rebound_slope_uV_per_ms", "Rebound slope", "Rebound slope (µV/ms)", "waveform"),
    ("after_rep50_recovery_slope_uV_per_ms", "Rep50 recovery slope", "Rep50 recovery slope (µV/ms)", "waveform"),
    ("aligned_waveform_asymmetry", "Waveform asymmetry", "Waveform asymmetry", "waveform"),
    ("after_peak_to_peak_ratio", "Peak-to-peak ratio", "Peak-to-peak ratio", "waveform"),
    # Unit-level firing metrics used in the current classification display/audit.
    ("source_firing_rate_hz", "Legacy firing rate", "Legacy firing rate (Hz)", "firing"),
    ("inverse_isi_gaussian_temporal_mean_hz", "Smoothed inverse-ISI mean", "Smoothed inverse-ISI mean (Hz)", "firing"),
    ("inverse_isi_gaussian_temporal_median_hz", "Smoothed inverse-ISI median", "Smoothed inverse-ISI median (Hz)", "firing"),
    ("inverse_isi_gaussian_temporal_p99_hz", "Smoothed inverse-ISI P99", "Smoothed inverse-ISI P99 (Hz)", "firing"),
    ("inverse_isi_gaussian_temporal_p99_9_hz", "Smoothed inverse-ISI P99.9", "Smoothed inverse-ISI P99.9 (Hz)", "firing"),
    ("inverse_isi_gaussian_temporal_max_hz", "Smoothed inverse-ISI maximum", "Smoothed inverse-ISI maximum (Hz)", "firing"),
]
FEATURE_COLUMNS = [feature[0] for feature in FEATURES]
SHORT_LABEL = {feature[0]: feature[1] for feature in FEATURES}
AXIS_LABEL = {feature[0]: feature[2] for feature in FEATURES}
FEATURE_TYPE = {feature[0]: feature[3] for feature in FEATURES}
TTP = "aligned_trough_to_peak_duration_ms"
ALGEBRAIC_TTP_PAIR = frozenset(
    ["after_post_peak_amplitude_uV", "after_post_trough_rebound_slope_uV_per_ms"]
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activity-dir", type=Path, default=DEFAULT_ACTIVITY_DIR)
    parser.add_argument("--alignment-dir", type=Path, default=DEFAULT_ALIGNMENT_DIR)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--fs-cutoff-ms", type=float, default=0.50)
    parser.add_argument("--cv-folds", type=int, default=5)
    parser.add_argument("--cv-repeats", type=int, default=5)
    parser.add_argument("--random-state", type=int, default=20260710)
    parser.add_argument("--n-jobs", type=int, default=2)
    parser.add_argument("--export-formats", default="png,pdf,svg")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    units = _load_units(args.activity_dir, args.alignment_dir, args.fs_cutoff_ms)

    manifest = _feature_manifest(units)
    pair_ranking = _rank_pairs(units, args)
    triple_ranking, triple_importance = _rank_triples(units, args)
    importance_summary = _summarize_importance(triple_ranking, triple_importance)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    _set_style(plt)
    matrix_paths = _plot_scatter_matrix(
        plt, Line2D, units, output_dir / f"{STEM}_complete_pairwise_scatter_matrix", args.export_formats
    )
    top_pair_paths = _plot_top_pairs(
        plt, units, pair_ranking.head(10), output_dir, args.export_formats
    )
    top_pair_sheet_paths = _plot_top_pair_sheet(
        plt,
        Line2D,
        units,
        pair_ranking.head(10),
        output_dir / f"{STEM}_top10_feature_pairs",
        args.export_formats,
    )
    triple_summary_paths = _plot_triple_summary(
        plt,
        triple_ranking.head(10),
        triple_importance,
        output_dir / f"{STEM}_top10_LDA_triples_and_importance",
        args.export_formats,
    )

    unit_path = output_dir / f"{STEM}_unit_feature_matrix.csv"
    manifest_path = output_dir / f"{STEM}_feature_manifest.csv"
    pair_path = output_dir / f"{STEM}_all_pairwise_rankings.csv"
    top_pair_path = output_dir / f"{STEM}_top10_feature_pairs.csv"
    triple_path = output_dir / f"{STEM}_all_three_feature_LDA_rankings.csv"
    top_triple_path = output_dir / f"{STEM}_top10_three_feature_LDA.csv"
    triple_importance_path = output_dir / f"{STEM}_all_three_feature_LDA_importance_long.csv"
    importance_summary_path = output_dir / f"{STEM}_LDA_feature_importance_summary.csv"
    units[["unit_key", "recording_well_id", "recording", "well", "region_call", "raw_variant", "unit_id", "rs_fs_class", *FEATURE_COLUMNS]].to_csv(unit_path, index=False)
    manifest.to_csv(manifest_path, index=False)
    pair_ranking.to_csv(pair_path, index=False)
    pair_ranking.head(10).to_csv(top_pair_path, index=False)
    triple_ranking.to_csv(triple_path, index=False)
    triple_ranking.head(10).to_csv(top_triple_path, index=False)
    triple_importance.to_csv(triple_importance_path, index=False)
    importance_summary.to_csv(importance_summary_path, index=False)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "activity_dir": str(Path(args.activity_dir).expanduser().resolve()),
        "alignment_dir": str(Path(args.alignment_dir).expanduser().resolve()),
        "population": {
            "units": int(len(units)),
            "class_counts": units["rs_fs_class"].value_counts().to_dict(),
            "class_rule": f"FS if aligned TTP <= {args.fs_cutoff_ms:.2f} ms; RS otherwise",
            "processing_versions": "retained as separate recording/well observations; LFP-only excluded upstream",
        },
        "feature_scope": {
            "count": len(FEATURES),
            "waveform_count": int(sum(kind == "waveform" for *_, kind in FEATURES)),
            "firing_count": int(sum(kind == "firing" for *_, kind in FEATURES)),
            "burst_metrics": "excluded because they summarize network activity rather than unit classification",
        },
        "pairwise_methods": {
            "fisher_discriminant_ratio": "trace(S_between)/trace(S_within) after z-scoring each pair",
            "mahalanobis_distance": "class-centroid distance using regularized pooled within-class covariance after z-scoring",
            "roc_auc": (
                f"mean repeated {args.cv_repeats}x{args.cv_folds}-fold stratified CV ROC AUC; "
                "StandardScaler + class-balanced logistic regression"
            ),
            "silhouette": "Euclidean silhouette of locked classes after z-scoring",
            "overall_rank": "ascending mean of the four descending metric-specific ranks",
        },
        "three_feature_method": {
            "model": "StandardScaler + linear discriminant analysis",
            "roc_auc": f"mean repeated {args.cv_repeats}x{args.cv_folds}-fold stratified CV ROC AUC",
            "importance": "absolute standardized full-data LDA coefficient normalized to sum to one within each triple",
        },
        "interpretation_warning": (
            "The labels were created from TTP, so separation involving TTP is tautological, not independent validation. "
            "The post-peak amplitude/rebound-slope pair algebraically reconstructs TTP and is explicitly flagged. "
            "All other rankings are same-dataset descriptive associations with the locked labels."
        ),
        "outputs": {
            "unit_feature_matrix": str(unit_path),
            "feature_manifest": str(manifest_path),
            "all_pairwise_rankings": str(pair_path),
            "top10_pair_rankings": str(top_pair_path),
            "all_triple_rankings": str(triple_path),
            "top10_triple_rankings": str(top_triple_path),
            "triple_importance_long": str(triple_importance_path),
            "importance_summary": str(importance_summary_path),
            "scatter_matrix": [str(path) for path in matrix_paths],
            "top10_pair_sheet": [str(path) for path in top_pair_sheet_paths],
            "top_pair_individual_plots": [str(path) for path in top_pair_paths],
            "triple_summary": [str(path) for path in triple_summary_paths],
        },
    }
    provenance_path = output_dir / f"{STEM}_provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    print(f"Units: {len(units)}; classes: {units['rs_fs_class'].value_counts().to_dict()}")
    print(f"Features: {len(FEATURES)}; pairs: {len(pair_ranking)}; triples: {len(triple_ranking)}")
    print("Top pair:", pair_ranking.iloc[0][["feature_1_label", "feature_2_label", "cv_roc_auc_mean"]].to_dict())
    print("Top triple:", triple_ranking.iloc[0][["feature_1_label", "feature_2_label", "feature_3_label", "cv_roc_auc_mean"]].to_dict())
    print(f"Provenance: {provenance_path}")
    return 0


def _load_units(activity_dir: Path, alignment_dir: Path, fs_cutoff_ms: float) -> pd.DataFrame:
    activity_dir = Path(activity_dir).expanduser().resolve()
    alignment_dir = Path(alignment_dir).expanduser().resolve()
    activity_stem = "cytoview_dv_sua_spontaneous_activity_20260710"
    units = pd.read_csv(activity_dir / f"{activity_stem}_unit_metrics.csv")
    paired = pd.read_csv(
        alignment_dir / "waveform_alignment_feature_audit_20260709_paired_unit_metrics.csv"
    )
    waveform_columns = [column for column, *rest in FEATURES if column.startswith("after_")]
    units = units.merge(
        paired[["unit_key", *waveform_columns]],
        on="unit_key",
        how="left",
        validate="one_to_one",
    )
    units = units.loc[units["aligned_fs_rs_class"].isin(CLASS_ORDER)].copy()
    units["rs_fs_class"] = units["aligned_fs_rs_class"]
    expected = np.where(
        pd.to_numeric(units[TTP], errors="coerce").le(fs_cutoff_ms), "FS", "RS"
    )
    if not np.array_equal(expected, units["rs_fs_class"].to_numpy()):
        raise ValueError("Stored classes do not match the requested aligned TTP cutoff")
    for column in FEATURE_COLUMNS:
        units[column] = pd.to_numeric(units[column], errors="coerce")
    return units


def _feature_manifest(units: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column, short, axis, kind in FEATURES:
        rows.append(
            {
                "feature": column,
                "short_label": short,
                "axis_label": axis,
                "feature_type": kind,
                "nonmissing_units": int(units[column].notna().sum()),
                "missing_units": int(units[column].isna().sum()),
                "class_defining": column == TTP,
                "current_figure_role": (
                    "RS/FS class-defining threshold" if column == TTP else
                    "Panel A point-size encoding" if column == "inverse_isi_gaussian_temporal_p99_9_hz" else
                    "candidate classification feature audit"
                ),
            }
        )
    return pd.DataFrame(rows)


def _complete_xy(units: pd.DataFrame, features: tuple[str, ...]):
    from sklearn.preprocessing import StandardScaler

    frame = units[["rs_fs_class", *features]].dropna()
    x = StandardScaler().fit_transform(frame[list(features)].to_numpy(float))
    y = frame["rs_fs_class"].eq("FS").astype(int).to_numpy()
    return frame, x, y


def _pair_scores(units: pd.DataFrame, pair: tuple[str, str], args: argparse.Namespace) -> dict[str, object]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import silhouette_score
    from sklearn.model_selection import RepeatedStratifiedKFold, cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    frame, x, y = _complete_xy(units, pair)
    x_fs, x_rs = x[y == 1], x[y == 0]
    p_fs, p_rs = len(x_fs) / len(x), len(x_rs) / len(x)
    mu_fs, mu_rs = x_fs.mean(axis=0), x_rs.mean(axis=0)
    between = p_fs * p_rs * float(np.sum((mu_fs - mu_rs) ** 2))
    within = p_fs * float(np.mean(np.sum((x_fs - mu_fs) ** 2, axis=1))) + p_rs * float(
        np.mean(np.sum((x_rs - mu_rs) ** 2, axis=1))
    )
    fisher = between / max(within, 1e-12)
    cov_fs = np.cov(x_fs, rowvar=False)
    cov_rs = np.cov(x_rs, rowvar=False)
    pooled = ((len(x_fs) - 1) * cov_fs + (len(x_rs) - 1) * cov_rs) / max(
        len(x_fs) + len(x_rs) - 2, 1
    )
    pooled = np.atleast_2d(pooled) + np.eye(2) * 1e-6
    delta = mu_fs - mu_rs
    mahalanobis = float(np.sqrt(max(delta @ np.linalg.pinv(pooled) @ delta, 0.0)))
    silhouette = float(silhouette_score(x, y))
    cv = RepeatedStratifiedKFold(
        n_splits=args.cv_folds,
        n_repeats=args.cv_repeats,
        random_state=args.random_state,
    )
    estimator = make_pipeline(
        StandardScaler(),
        LogisticRegression(class_weight="balanced", max_iter=5000, random_state=args.random_state),
    )
    auc = cross_val_score(
        estimator, frame[list(pair)].to_numpy(float), y, cv=cv, scoring="roc_auc", n_jobs=args.n_jobs
    )
    pair_set = frozenset(pair)
    return {
        "feature_1": pair[0],
        "feature_2": pair[1],
        "feature_1_label": SHORT_LABEL[pair[0]],
        "feature_2_label": SHORT_LABEL[pair[1]],
        "feature_1_type": FEATURE_TYPE[pair[0]],
        "feature_2_type": FEATURE_TYPE[pair[1]],
        "pair_type": "+".join(sorted({FEATURE_TYPE[pair[0]], FEATURE_TYPE[pair[1]]})),
        "n_complete": len(frame),
        "n_fs": int(y.sum()),
        "n_rs": int((1 - y).sum()),
        "fisher_discriminant_ratio": fisher,
        "mahalanobis_distance": mahalanobis,
        "cv_roc_auc_mean": float(np.mean(auc)),
        "cv_roc_auc_sd": float(np.std(auc, ddof=1)),
        "silhouette_score": silhouette,
        "contains_class_defining_ttp": TTP in pair_set,
        "algebraically_reconstructs_ttp": pair_set == ALGEBRAIC_TTP_PAIR,
    }


def _rank_pairs(units: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    rows = [_pair_scores(units, pair, args) for pair in itertools.combinations(FEATURE_COLUMNS, 2)]
    ranking = pd.DataFrame(rows)
    score_columns = [
        "fisher_discriminant_ratio",
        "mahalanobis_distance",
        "cv_roc_auc_mean",
        "silhouette_score",
    ]
    for score in score_columns:
        ranking[f"rank_{score}"] = ranking[score].rank(method="min", ascending=False).astype(int)
    ranking["mean_metric_rank"] = ranking[[f"rank_{score}" for score in score_columns]].mean(axis=1)
    ranking = ranking.sort_values(
        ["mean_metric_rank", "cv_roc_auc_mean", "mahalanobis_distance"],
        ascending=[True, False, False],
    ).reset_index(drop=True)
    ranking.insert(0, "overall_rank", np.arange(1, len(ranking) + 1))
    ranking["interpretation_flag"] = np.select(
        [ranking["contains_class_defining_ttp"], ranking["algebraically_reconstructs_ttp"]],
        ["contains label-defining TTP; tautological separation", "algebraically reconstructs label-defining TTP"],
        default="same-dataset descriptive association",
    )
    return ranking


def _triple_scores(units: pd.DataFrame, triple: tuple[str, str, str], args: argparse.Namespace):
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.model_selection import RepeatedStratifiedKFold, cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    frame, x, y = _complete_xy(units, triple)
    cv = RepeatedStratifiedKFold(
        n_splits=args.cv_folds,
        n_repeats=args.cv_repeats,
        random_state=args.random_state,
    )
    estimator = make_pipeline(StandardScaler(), LinearDiscriminantAnalysis())
    auc = cross_val_score(
        estimator, frame[list(triple)].to_numpy(float), y, cv=cv, scoring="roc_auc", n_jobs=args.n_jobs
    )
    lda = LinearDiscriminantAnalysis().fit(x, y)
    absolute = np.abs(np.ravel(lda.coef_))
    normalized = absolute / max(float(absolute.sum()), 1e-12)
    triple_id = " | ".join(triple)
    triple_set = frozenset(triple)
    row = {
        "triple_id": triple_id,
        **{f"feature_{index}": feature for index, feature in enumerate(triple, start=1)},
        **{f"feature_{index}_label": SHORT_LABEL[feature] for index, feature in enumerate(triple, start=1)},
        "n_complete": len(frame),
        "n_fs": int(y.sum()),
        "n_rs": int((1 - y).sum()),
        "cv_roc_auc_mean": float(np.mean(auc)),
        "cv_roc_auc_sd": float(np.std(auc, ddof=1)),
        "contains_class_defining_ttp": TTP in triple_set,
        "contains_algebraic_ttp_reconstruction_pair": ALGEBRAIC_TTP_PAIR.issubset(triple_set),
    }
    importance_rows = [
        {
            "triple_id": triple_id,
            "feature": feature,
            "feature_label": SHORT_LABEL[feature],
            "standardized_LDA_coefficient": float(coefficient),
            "absolute_standardized_LDA_coefficient": float(abs(coefficient)),
            "normalized_absolute_importance": float(importance),
        }
        for feature, coefficient, importance in zip(triple, np.ravel(lda.coef_), normalized, strict=True)
    ]
    return row, importance_rows


def _rank_triples(units: pd.DataFrame, args: argparse.Namespace):
    rows = []
    importance_rows = []
    for triple in itertools.combinations(FEATURE_COLUMNS, 3):
        row, importance = _triple_scores(units, triple, args)
        rows.append(row)
        importance_rows.extend(importance)
    ranking = pd.DataFrame(rows).sort_values(
        ["cv_roc_auc_mean", "cv_roc_auc_sd"], ascending=[False, True]
    ).reset_index(drop=True)
    ranking.insert(0, "LDA_rank", np.arange(1, len(ranking) + 1))
    ranking["interpretation_flag"] = np.select(
        [ranking["contains_class_defining_ttp"], ranking["contains_algebraic_ttp_reconstruction_pair"]],
        ["contains label-defining TTP; tautological separation", "contains pair that algebraically reconstructs label-defining TTP"],
        default="same-dataset descriptive association",
    )
    importance = pd.DataFrame(importance_rows).merge(
        ranking[["triple_id", "LDA_rank", "cv_roc_auc_mean"]], on="triple_id", validate="many_to_one"
    )
    return ranking, importance


def _summarize_importance(ranking: pd.DataFrame, importance: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for feature in FEATURE_COLUMNS:
        subset = importance.loc[importance["feature"].eq(feature)]
        rows.append(
            {
                "feature": feature,
                "feature_label": SHORT_LABEL[feature],
                "feature_type": FEATURE_TYPE[feature],
                "class_defining": feature == TTP,
                "triple_count": len(subset),
                "mean_normalized_absolute_importance_all_triples": subset["normalized_absolute_importance"].mean(),
                "mean_normalized_absolute_importance_top10": subset.loc[subset["LDA_rank"].le(10), "normalized_absolute_importance"].mean(),
                "mean_normalized_absolute_importance_top50": subset.loc[subset["LDA_rank"].le(50), "normalized_absolute_importance"].mean(),
                "frequency_in_top10": int(subset.loc[subset["LDA_rank"].le(10), "triple_id"].nunique()),
                "frequency_in_top50": int(subset.loc[subset["LDA_rank"].le(50), "triple_id"].nunique()),
                "best_triple_rank_containing_feature": int(subset["LDA_rank"].min()),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["frequency_in_top10", "mean_normalized_absolute_importance_top10", "frequency_in_top50"],
        ascending=False,
    )


def _set_style(plt) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 7,
            "axes.titlesize": 8,
            "axes.labelsize": 7,
            "xtick.labelsize": 6,
            "ytick.labelsize": 6,
            "axes.linewidth": 0.7,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _save_figure(fig, output_base: Path, export_formats: str, *, png_dpi: int = 600):
    paths = []
    for suffix in [value.strip().lower() for value in export_formats.split(",") if value.strip()]:
        path = output_base.with_suffix(f".{suffix}")
        kwargs = {"bbox_inches": "tight", "facecolor": "white", "transparent": False}
        if suffix == "png":
            kwargs["dpi"] = png_dpi
        fig.savefig(path, **kwargs)
        paths.append(path)
    return paths


def _scatter(ax, units: pd.DataFrame, x_feature: str, y_feature: str, *, title: str | None = None):
    frame = units[["rs_fs_class", x_feature, y_feature]].dropna()
    for class_label in CLASS_ORDER:
        subset = frame.loc[frame["rs_fs_class"].eq(class_label)]
        ax.scatter(
            subset[x_feature],
            subset[y_feature],
            s=18,
            color=CLASS_COLORS[class_label],
            alpha=0.72,
            edgecolor="white",
            linewidth=0.35,
            label=class_label,
        )
    if title:
        ax.set_title(title, loc="left", fontweight="bold")
    ax.set_xlabel(AXIS_LABEL[x_feature])
    ax.set_ylabel(AXIS_LABEL[y_feature])
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="#E5E5E5", lw=0.5, alpha=0.7)
    ax.set_axisbelow(True)


def _plot_scatter_matrix(plt, Line2D, units: pd.DataFrame, output_base: Path, export_formats: str):
    count = len(FEATURE_COLUMNS)
    fig, axes = plt.subplots(count, count, figsize=(25, 25), squeeze=False)
    for row, y_feature in enumerate(FEATURE_COLUMNS):
        for column, x_feature in enumerate(FEATURE_COLUMNS):
            ax = axes[row, column]
            if row < column:
                ax.set_axis_off()
                continue
            if row == column:
                for class_label in CLASS_ORDER:
                    values = units.loc[units["rs_fs_class"].eq(class_label), x_feature].dropna()
                    ax.hist(values, bins=18, density=True, histtype="step", lw=0.8, color=CLASS_COLORS[class_label])
            else:
                frame = units[["rs_fs_class", x_feature, y_feature]].dropna()
                for class_label in CLASS_ORDER:
                    subset = frame.loc[frame["rs_fs_class"].eq(class_label)]
                    ax.scatter(subset[x_feature], subset[y_feature], s=3.2, alpha=0.50, color=CLASS_COLORS[class_label], linewidth=0)
            ax.spines[["top", "right"]].set_visible(False)
            ax.tick_params(labelsize=3.6, length=1.4, pad=0.8)
            if row != count - 1:
                ax.set_xticklabels([])
            else:
                ax.set_xlabel(SHORT_LABEL[x_feature], fontsize=4.2, rotation=35, ha="right")
            if column != 0:
                ax.set_yticklabels([])
            else:
                ax.set_ylabel(SHORT_LABEL[y_feature], fontsize=4.2)
    handles = [
        Line2D([0], [0], marker="o", linestyle="none", color=CLASS_COLORS[label], markersize=5, label=f"{label} (n={int(units['rs_fs_class'].eq(label).sum())})")
        for label in CLASS_ORDER
    ]
    fig.legend(handles=handles, loc="upper right", frameon=False, ncol=2, fontsize=8)
    fig.suptitle(
        "Complete pairwise matrix of aligned waveform and unit firing metrics",
        x=0.06,
        y=0.995,
        ha="left",
        fontsize=12,
        fontweight="bold",
    )
    fig.subplots_adjust(left=0.07, right=0.99, bottom=0.07, top=0.98, wspace=0.10, hspace=0.10)
    paths = _save_figure(fig, output_base, export_formats, png_dpi=300)
    plt.close(fig)
    return paths


def _plot_top_pairs(plt, units: pd.DataFrame, top: pd.DataFrame, output_dir: Path, export_formats: str):
    all_paths = []
    for _, row in top.iterrows():
        fig, ax = plt.subplots(figsize=(3.55, 3.15))
        _scatter(ax, units, row["feature_1"], row["feature_2"], title=f"Rank {int(row['overall_rank'])}: {row['feature_1_label']} × {row['feature_2_label']}")
        ax.text(
            0.02,
            0.98,
            f"Fisher={row['fisher_discriminant_ratio']:.2f}  Mahalanobis={row['mahalanobis_distance']:.2f}\nCV AUC={row['cv_roc_auc_mean']:.3f}  Silhouette={row['silhouette_score']:.2f}  n={int(row['n_complete'])}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=5.8,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.82, pad=1.5),
        )
        ax.legend(frameon=False, loc="lower right", fontsize=6)
        fig.tight_layout()
        base = output_dir / f"{STEM}_top_pair_{int(row['overall_rank']):02d}"
        all_paths.extend(_save_figure(fig, base, export_formats))
        plt.close(fig)
    return all_paths


def _plot_top_pair_sheet(plt, Line2D, units: pd.DataFrame, top: pd.DataFrame, output_base: Path, export_formats: str):
    fig, axes = plt.subplots(2, 5, figsize=(16, 6.2))
    for ax, (_, row) in zip(axes.ravel(), top.iterrows(), strict=True):
        _scatter(ax, units, row["feature_1"], row["feature_2"], title=f"{int(row['overall_rank'])}. {row['feature_1_label']} × {row['feature_2_label']}")
        ax.text(0.02, 0.98, f"AUC {row['cv_roc_auc_mean']:.3f} | F {row['fisher_discriminant_ratio']:.2f}\nM {row['mahalanobis_distance']:.2f} | S {row['silhouette_score']:.2f}", transform=ax.transAxes, ha="left", va="top", fontsize=5.5, bbox=dict(facecolor="white", edgecolor="none", alpha=0.80, pad=1))
    handles = [Line2D([0], [0], marker="o", linestyle="none", color=CLASS_COLORS[label], markersize=5, label=label) for label in CLASS_ORDER]
    fig.legend(handles=handles, frameon=False, loc="lower center", ncol=2)
    fig.suptitle("Top 10 pairwise feature combinations by mean separability rank", x=0.03, ha="left", fontweight="bold", fontsize=11)
    fig.subplots_adjust(left=0.06, right=0.99, bottom=0.12, top=0.91, wspace=0.38, hspace=0.42)
    paths = _save_figure(fig, output_base, export_formats)
    plt.close(fig)
    return paths


def _plot_triple_summary(plt, top: pd.DataFrame, importance: pd.DataFrame, output_base: Path, export_formats: str):
    top = top.copy()
    labels = [f"{int(row.LDA_rank)}. {row.feature_1_label} + {row.feature_2_label} + {row.feature_3_label}" for row in top.itertuples()]
    selected_features = [feature for feature in FEATURE_COLUMNS if feature in set(top[["feature_1", "feature_2", "feature_3"]].to_numpy().ravel())]
    matrix = np.zeros((len(top), len(selected_features)))
    for row_index, triple_id in enumerate(top["triple_id"]):
        values = importance.loc[importance["triple_id"].eq(triple_id)].set_index("feature")["normalized_absolute_importance"]
        for column_index, feature in enumerate(selected_features):
            matrix[row_index, column_index] = float(values.get(feature, 0.0))
    fig, (ax_auc, ax_heat) = plt.subplots(1, 2, figsize=(14, 5.8), gridspec_kw={"width_ratios": [1.05, 1.55]})
    y = np.arange(len(top))
    ax_auc.barh(y, top["cv_roc_auc_mean"], xerr=top["cv_roc_auc_sd"], color="#5B7FA3", alpha=0.88, error_kw={"lw": 0.7})
    ax_auc.set_yticks(y, labels)
    ax_auc.invert_yaxis()
    ax_auc.set_xlim(max(0.45, float(top["cv_roc_auc_mean"].min()) - 0.05), 1.01)
    ax_auc.set_xlabel("Repeated-CV ROC AUC")
    ax_auc.set_title("Top three-feature LDA models", loc="left", fontweight="bold")
    ax_auc.spines[["top", "right"]].set_visible(False)
    image = ax_heat.imshow(matrix, aspect="auto", cmap="Blues", vmin=0, vmax=max(0.5, float(matrix.max())))
    ax_heat.set_yticks(y, [str(int(rank)) for rank in top["LDA_rank"]])
    ax_heat.set_xticks(np.arange(len(selected_features)), [SHORT_LABEL[feature] for feature in selected_features], rotation=40, ha="right")
    ax_heat.set_xlabel("Normalized |standardized LDA coefficient|")
    ax_heat.set_ylabel("LDA rank")
    ax_heat.set_title("Within-model feature importance", loc="left", fontweight="bold")
    fig.colorbar(image, ax=ax_heat, fraction=0.035, pad=0.02)
    fig.suptitle("Three-feature classification audit", x=0.04, ha="left", fontsize=11, fontweight="bold")
    fig.subplots_adjust(left=0.28, right=0.98, bottom=0.25, top=0.88, wspace=0.28)
    paths = _save_figure(fig, output_base, export_formats)
    plt.close(fig)
    return paths


if __name__ == "__main__":
    raise SystemExit(main())
