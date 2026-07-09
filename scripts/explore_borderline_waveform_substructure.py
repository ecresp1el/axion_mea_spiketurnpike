#!/usr/bin/env python
"""Explore non-TTP waveform substructure within current borderline units.

This script is deliberately isolated from the production TTP-based classifier.
It keeps TTP as the primary classifier, filters only the current borderline
units, then fits exploratory unsupervised models using non-TTP waveform metrics
such as REP50, half-width, rebound/recovery slopes, amplitudes, and ratios.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_DATE_LABEL = "20260709"
DEFAULT_FEATURES = [
    "repolarization_time_ms",
    "spike_half_width_ms",
    "post_trough_rebound_slope_uV_per_ms",
    "rep50_recovery_slope_uV_per_ms",
    "pre_trough_depolarization_slope_uV_per_ms",
    "post_peak_value_uV",
    "post_peak_amplitude_uV",
    "peak1_to_trough_ratio",
    "peak2_to_trough_ratio",
    "peak_to_peak_ratio",
    "waveform_asymmetry",
    "template_ptp_best_channel_uV",
    "spiketurnpike_amplitude_uV",
]
CLUSTER_COLORS = {
    "FS_like_candidate": "#d55e00",
    "RS_like_candidate": "#0072b2",
    "ambiguous_borderline": "#7a7a7a",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--features-csv", type=Path)
    parser.add_argument("--posterior-threshold", type=float, default=0.8)
    parser.add_argument("--random-state", type=int, default=13)
    parser.add_argument(
        "--feature-columns",
        default=",".join(DEFAULT_FEATURES),
        help="Comma-separated non-TTP features to use for clustering.",
    )
    args = parser.parse_args()

    if not 0.5 < args.posterior_threshold < 1.0:
        raise SystemExit("--posterior-threshold must be > 0.5 and < 1.0.")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.decomposition import PCA
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import silhouette_score
    from sklearn.mixture import GaussianMixture
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    job_dir = args.job_dir.expanduser().resolve()
    features_csv = args.features_csv or job_dir / (
        f"good_kslabel_waveform_feature_separation_{args.date_label}_features.csv"
    )
    table = pd.read_csv(features_csv)
    borderline = table.loc[table["rs_fs_classification"].eq("borderline")].copy()
    if borderline.empty:
        raise SystemExit(f"No borderline units found in {features_csv}")

    requested_features = [feature.strip() for feature in args.feature_columns.split(",") if feature.strip()]
    feature_columns = [
        feature
        for feature in requested_features
        if feature in borderline.columns and pd.api.types.is_numeric_dtype(borderline[feature])
    ]
    if len(feature_columns) < 2:
        raise SystemExit(f"Need at least two numeric feature columns; found {feature_columns}")

    x_raw = borderline[feature_columns].replace([np.inf, -np.inf], np.nan)
    preprocessor = make_pipeline(SimpleImputer(strategy="median"), StandardScaler())
    x = preprocessor.fit_transform(x_raw)

    model_selection = _fit_gmm_model_selection(GaussianMixture, silhouette_score, x, args.random_state)
    gmm = GaussianMixture(n_components=2, covariance_type="full", n_init=50, random_state=args.random_state)
    raw_cluster = gmm.fit_predict(x)
    posterior_raw = gmm.predict_proba(x)
    pca = PCA(n_components=2, random_state=args.random_state)
    pcs = pca.fit_transform(x)

    labels, posterior = _label_clusters(borderline, raw_cluster, posterior_raw)
    max_posterior = posterior.max(axis=1)
    exploratory_labels = np.where(max_posterior >= args.posterior_threshold, labels, "ambiguous_borderline")

    out = borderline.copy()
    out["borderline_gmm_raw_cluster"] = raw_cluster
    out["borderline_gmm_label"] = labels
    out["borderline_exploratory_label"] = exploratory_labels
    out["borderline_gmm_max_posterior"] = max_posterior
    out["borderline_fs_candidate_posterior"] = posterior[:, 0]
    out["borderline_rs_candidate_posterior"] = posterior[:, 1]
    out["borderline_pca1"] = pcs[:, 0]
    out["borderline_pca2"] = pcs[:, 1]

    stem = f"borderline_waveform_substructure_non_ttp_{args.date_label}"
    unit_csv = job_dir / f"{stem}_unit_assignments.csv"
    summary_csv = job_dir / f"{stem}_cluster_summary.csv"
    feature_diff_csv = job_dir / f"{stem}_feature_differences.csv"
    model_selection_csv = job_dir / f"{stem}_gmm_model_selection.csv"
    pca_png = job_dir / f"{stem}_pca.png"
    pair_png = job_dir / f"{stem}_pairwise_features.png"
    feature_png = job_dir / f"{stem}_feature_distributions.png"
    corr_png = job_dir / f"{stem}_correlation_matrix.png"
    provenance_json = job_dir / f"{stem}_provenance.json"

    out.to_csv(unit_csv, index=False)
    summary = _cluster_summary(out, feature_columns)
    summary.to_csv(summary_csv, index=False)
    feature_diff = _feature_differences(out, feature_columns)
    feature_diff.to_csv(feature_diff_csv, index=False)
    model_selection.to_csv(model_selection_csv, index=False)

    _plot_pca(plt, out, pca, pca_png)
    _plot_pairwise_features(plt, out, feature_columns, pair_png)
    _plot_feature_distributions(plt, out, feature_columns, feature_png)
    _plot_correlation_matrix(plt, borderline[feature_columns].corr(method="spearman"), corr_png)

    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "input_features_csv": str(features_csv),
        "unit_count": int(len(out)),
        "posterior_threshold": args.posterior_threshold,
        "feature_columns": feature_columns,
        "class_counts": out["borderline_exploratory_label"].value_counts(dropna=False).to_dict(),
        "raw_gmm_counts": out["borderline_gmm_label"].value_counts(dropna=False).to_dict(),
        "model_selection": model_selection.to_dict(orient="records"),
        "pca_explained_variance_ratio": pca.explained_variance_ratio_.tolist(),
        "outputs": {
            "unit_assignments_csv": str(unit_csv),
            "cluster_summary_csv": str(summary_csv),
            "feature_differences_csv": str(feature_diff_csv),
            "model_selection_csv": str(model_selection_csv),
            "pca_png": str(pca_png),
            "pairwise_features_png": str(pair_png),
            "feature_distributions_png": str(feature_png),
            "correlation_matrix_png": str(corr_png),
        },
        "notes": [
            "Exploratory only; production TTP classifier is unchanged.",
            "TTP is not used as a clustering feature.",
            "Candidate labels are assigned by cluster profile: shorter REP/half-width and steeper rebound/recovery slopes are named FS_like_candidate.",
        ],
    }
    provenance_json.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Input features: {features_csv}")
    print(f"Borderline units analyzed: {len(out)}")
    print(f"Features used: {', '.join(feature_columns)}")
    print("Exploratory labels:")
    print(out["borderline_exploratory_label"].value_counts(dropna=False).to_string())
    print("\nRaw GMM labels:")
    print(out["borderline_gmm_label"].value_counts(dropna=False).to_string())
    print("\nGMM model selection:")
    print(model_selection.to_string(index=False))
    print("\nLargest feature differences:")
    print(feature_diff.head(12).to_string(index=False))
    print(f"\nUnit assignments: {unit_csv}")
    print(f"Cluster summary: {summary_csv}")
    print(f"Feature differences: {feature_diff_csv}")
    print(f"PCA plot: {pca_png}")
    print(f"Pairwise plot: {pair_png}")
    print(f"Feature distributions: {feature_png}")
    print(f"Correlation plot: {corr_png}")
    print(f"Provenance: {provenance_json}")


def _fit_gmm_model_selection(GaussianMixture, silhouette_score, x: np.ndarray, random_state: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for n_components in range(1, min(5, x.shape[0]) + 1):
        model = GaussianMixture(
            n_components=n_components,
            covariance_type="full",
            n_init=50,
            random_state=random_state,
        )
        labels = model.fit_predict(x)
        silhouette = np.nan
        if n_components > 1 and len(np.unique(labels)) > 1:
            silhouette = float(silhouette_score(x, labels))
        rows.append(
            {
                "n_components": n_components,
                "bic": float(model.bic(x)),
                "aic": float(model.aic(x)),
                "silhouette": silhouette,
            }
        )
    return pd.DataFrame(rows)


def _label_clusters(
    borderline: pd.DataFrame,
    raw_cluster: np.ndarray,
    posterior_raw: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    profiles = []
    for cluster in sorted(np.unique(raw_cluster)):
        subset = borderline.iloc[np.flatnonzero(raw_cluster == cluster)]
        score_parts = []
        for feature, direction in [
            ("repolarization_time_ms", -1.0),
            ("spike_half_width_ms", -1.0),
            ("post_trough_rebound_slope_uV_per_ms", 1.0),
            ("rep50_recovery_slope_uV_per_ms", 1.0),
        ]:
            if feature in subset.columns:
                score_parts.append(direction * float(pd.to_numeric(subset[feature], errors="coerce").median()))
        profiles.append((cluster, float(np.nanmean(score_parts)) if score_parts else 0.0))
    fs_cluster = max(profiles, key=lambda item: item[1])[0]
    rs_cluster = min(profiles, key=lambda item: item[1])[0]
    cluster_to_label = {fs_cluster: "FS_like_candidate", rs_cluster: "RS_like_candidate"}
    labels = np.asarray([cluster_to_label[cluster] for cluster in raw_cluster], dtype=object)
    fs_column = int(np.flatnonzero(np.asarray(sorted(np.unique(raw_cluster))) == fs_cluster)[0])
    rs_column = int(np.flatnonzero(np.asarray(sorted(np.unique(raw_cluster))) == rs_cluster)[0])
    posterior = np.column_stack([posterior_raw[:, fs_column], posterior_raw[:, rs_column]])
    return labels, posterior


def _cluster_summary(table: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for label in ["FS_like_candidate", "ambiguous_borderline", "RS_like_candidate"]:
        subset = table.loc[table["borderline_exploratory_label"].eq(label)]
        for feature in feature_columns + ["trough_to_peak_duration_ms"]:
            values = pd.to_numeric(subset[feature], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
            rows.append(
                {
                    "borderline_exploratory_label": label,
                    "feature": feature,
                    "count": int(values.size),
                    "median": float(values.median()) if not values.empty else np.nan,
                    "mean": float(values.mean()) if not values.empty else np.nan,
                    "min": float(values.min()) if not values.empty else np.nan,
                    "max": float(values.max()) if not values.empty else np.nan,
                }
            )
    return pd.DataFrame(rows)


def _feature_differences(table: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    fs = table.loc[table["borderline_gmm_label"].eq("FS_like_candidate")]
    rs = table.loc[table["borderline_gmm_label"].eq("RS_like_candidate")]
    rows: list[dict[str, object]] = []
    for feature in feature_columns:
        fs_values = pd.to_numeric(fs[feature], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        rs_values = pd.to_numeric(rs[feature], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        pooled = pd.to_numeric(table[feature], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        fs_median = float(fs_values.median()) if not fs_values.empty else np.nan
        rs_median = float(rs_values.median()) if not rs_values.empty else np.nan
        pooled_std = float(pooled.std()) if pooled.size > 1 else np.nan
        rows.append(
            {
                "feature": feature,
                "fs_candidate_median": fs_median,
                "rs_candidate_median": rs_median,
                "median_difference_fs_minus_rs": fs_median - rs_median,
                "absolute_median_difference": abs(fs_median - rs_median),
                "standardized_median_difference": (fs_median - rs_median) / pooled_std
                if np.isfinite(pooled_std) and pooled_std > 0
                else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    return out.sort_values("absolute_median_difference", ascending=False, ignore_index=True)


def _plot_pca(plt, table: pd.DataFrame, pca, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 5.5))
    for label in ["FS_like_candidate", "ambiguous_borderline", "RS_like_candidate"]:
        subset = table.loc[table["borderline_exploratory_label"].eq(label)]
        if subset.empty:
            continue
        ax.scatter(
            subset["borderline_pca1"],
            subset["borderline_pca2"],
            s=48,
            alpha=0.82,
            linewidths=0,
            color=CLUSTER_COLORS[label],
            label=f"{label} (n={len(subset)})",
        )
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0] * 100:.1f}% var)")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1] * 100:.1f}% var)")
    ax.set_title("Borderline-only non-TTP waveform feature PCA")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_pairwise_features(plt, table: pd.DataFrame, feature_columns: list[str], output_path: Path) -> None:
    selected = [
        feature
        for feature in [
            "repolarization_time_ms",
            "spike_half_width_ms",
            "post_trough_rebound_slope_uV_per_ms",
            "rep50_recovery_slope_uV_per_ms",
            "post_peak_value_uV",
            "waveform_asymmetry",
        ]
        if feature in feature_columns
    ]
    pairs = list(combinations(selected, 2))[:12]
    ncols = 4
    nrows = int(np.ceil(len(pairs) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.25 * ncols, 3.35 * nrows), squeeze=False)
    for axis, (x_feature, y_feature) in zip(axes.ravel(), pairs, strict=False):
        for label in ["FS_like_candidate", "ambiguous_borderline", "RS_like_candidate"]:
            subset = table.loc[table["borderline_exploratory_label"].eq(label)]
            if subset.empty:
                continue
            axis.scatter(
                subset[x_feature],
                subset[y_feature],
                s=32,
                alpha=0.82,
                linewidths=0,
                color=CLUSTER_COLORS[label],
                label=label,
            )
        axis.set_xlabel(_short_label(x_feature), fontsize=9)
        axis.set_ylabel(_short_label(y_feature), fontsize=9)
        axis.tick_params(labelsize=8)
    for axis in axes.ravel()[len(pairs) :]:
        axis.axis("off")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 0.965), ncol=3)
    fig.suptitle("Borderline-only pairwise non-TTP waveform metrics", y=0.998, fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_feature_distributions(plt, table: pd.DataFrame, feature_columns: list[str], output_path: Path) -> None:
    selected = [feature for feature in DEFAULT_FEATURES[:10] if feature in feature_columns]
    ncols = 3
    nrows = int(np.ceil(len(selected) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.7 * ncols, 3.2 * nrows), squeeze=False)
    for axis, feature in zip(axes.ravel(), selected, strict=False):
        positions = []
        labels = []
        data = []
        colors = []
        for index, label in enumerate(["FS_like_candidate", "ambiguous_borderline", "RS_like_candidate"], start=1):
            values = table.loc[table["borderline_exploratory_label"].eq(label), feature].dropna().to_numpy()
            if values.size == 0:
                continue
            positions.append(index)
            labels.append(label.replace("_candidate", "").replace("_borderline", ""))
            data.append(values)
            colors.append(CLUSTER_COLORS[label])
        parts = axis.violinplot(data, positions=positions, showmedians=True, showextrema=False)
        for body, color in zip(parts["bodies"], colors, strict=True):
            body.set_facecolor(color)
            body.set_edgecolor("none")
            body.set_alpha(0.65)
        parts["cmedians"].set_color("#1f1f1f")
        axis.set_xticks(positions, labels, rotation=25, ha="right", fontsize=8)
        axis.set_title(_short_label(feature), fontsize=10)
        axis.tick_params(axis="y", labelsize=8)
    for axis in axes.ravel()[len(selected) :]:
        axis.axis("off")
    fig.suptitle("Borderline-only feature distributions by exploratory subgroup", y=0.995, fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.965))
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_correlation_matrix(plt, corr: pd.DataFrame, output_path: Path) -> None:
    labels = [_short_label(col) for col in corr.columns]
    fig, ax = plt.subplots(figsize=(max(8, 0.55 * len(labels)), max(7, 0.55 * len(labels))))
    image = ax.imshow(corr.to_numpy(), cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(np.arange(len(labels)), labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(np.arange(len(labels)), labels, fontsize=8)
    fig.colorbar(image, ax=ax, shrink=0.82, label="Spearman rho")
    ax.set_title("Borderline-only non-TTP waveform feature correlations")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _short_label(name: str) -> str:
    return {
        "repolarization_time_ms": "REP50 ms",
        "spike_half_width_ms": "half-width ms",
        "post_trough_rebound_slope_uV_per_ms": "rebound slope",
        "rep50_recovery_slope_uV_per_ms": "REP50 slope",
        "pre_trough_depolarization_slope_uV_per_ms": "downstroke slope",
        "post_peak_value_uV": "post peak uV",
        "post_peak_amplitude_uV": "post amp uV",
        "peak1_to_trough_ratio": "pre/trough",
        "peak2_to_trough_ratio": "post/trough",
        "peak_to_peak_ratio": "peak ratio",
        "waveform_asymmetry": "asymmetry",
        "template_ptp_best_channel_uV": "PTP uV",
        "spiketurnpike_amplitude_uV": "trough amp uV",
    }.get(name, name.replace("_", " "))


if __name__ == "__main__":
    main()
