#!/usr/bin/env python
"""Explore waveform features that separate current fixed FS/borderline/RS labels.

This is an isolated analysis script. It does not modify the production
TTP-based classifier. It uses the current good-unit TTP table as the unit
universe, reopens the corresponding SortingAnalyzers, recomputes waveform
features from templates.average on the best peak-to-peak channel, and uses the
existing fixed labels only as reference labels for exploratory plots/rankings.
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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.plot_lumos_candidate_waveform_gallery import (  # noqa: E402
    _measure_spiketurnpike_waveform_metrics,
)


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_DATE_LABEL = "20260709"
CLASS_ORDER = ["FS_like", "borderline", "RS_like"]
CLASS_COLORS = {"FS_like": "#d55e00", "borderline": "#7a7a7a", "RS_like": "#0072b2"}
PAIRPLOT_FEATURES = [
    "trough_to_peak_duration_ms",
    "repolarization_time_ms",
    "spike_half_width_ms",
    "template_ptp_best_channel_uV",
    "spiketurnpike_amplitude_uV",
    "post_trough_rebound_slope_uV_per_ms",
    "waveform_asymmetry",
    "peak_to_peak_ratio",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--input-csv", type=Path)
    parser.add_argument("--rep-fraction", type=float, choices=(0.25, 0.5, 0.63), default=0.5)
    parser.add_argument("--random-state", type=int, default=13)
    args = parser.parse_args()

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import spikeinterface.full as si
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.feature_selection import f_classif, mutual_info_classif
    from sklearn.impute import SimpleImputer
    from sklearn.inspection import permutation_importance
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import LabelEncoder, StandardScaler

    job_dir = args.job_dir.expanduser().resolve()
    input_csv = args.input_csv or job_dir / (
        f"good_kslabel_ttp_distribution_template_best_ptp_{args.date_label}.csv"
    )
    source = pd.read_csv(input_csv)
    features, errors = _extract_features(si, source, rep_fraction=args.rep_fraction)
    feature_columns = _feature_columns(features)
    rank_table = _rank_features(
        features,
        feature_columns,
        random_state=args.random_state,
        LabelEncoder=LabelEncoder,
        SimpleImputer=SimpleImputer,
        StandardScaler=StandardScaler,
        RandomForestClassifier=RandomForestClassifier,
        permutation_importance=permutation_importance,
        f_classif=f_classif,
        mutual_info_classif=mutual_info_classif,
        make_pipeline=make_pipeline,
    )

    stem = f"good_kslabel_waveform_feature_separation_{args.date_label}"
    feature_csv = job_dir / f"{stem}_features.csv"
    rank_csv = job_dir / f"{stem}_feature_ranks.csv"
    class_summary_csv = job_dir / f"{stem}_class_summary.csv"
    corr_csv = job_dir / f"{stem}_correlation_matrix.csv"
    pairplot_path = job_dir / f"{stem}_pairwise_scatter_matrix.png"
    top_pairs_path = job_dir / f"{stem}_top_pairwise_scatter.png"
    corr_path = job_dir / f"{stem}_correlation_matrix.png"
    rank_path = job_dir / f"{stem}_feature_rank_bars.png"
    provenance_path = job_dir / f"{stem}_provenance.json"
    error_path = job_dir / f"{stem}_errors.txt"

    features.to_csv(feature_csv, index=False)
    rank_table.to_csv(rank_csv, index=False)
    class_summary = _class_summary(features, feature_columns)
    class_summary.to_csv(class_summary_csv, index=False)
    corr = features[feature_columns].corr(method="spearman")
    corr.to_csv(corr_csv)
    _plot_pairwise_matrix(plt, features, PAIRPLOT_FEATURES, pairplot_path)
    _plot_top_pairs(plt, features, rank_table, top_pairs_path)
    _plot_correlation_matrix(plt, corr, corr_path)
    _plot_feature_rank_bars(plt, rank_table, rank_path)

    if errors:
        error_path.write_text("\n".join(errors) + "\n", encoding="utf-8")
    provenance = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "input_csv": str(input_csv),
        "unit_count": int(len(features)),
        "class_counts": features["rs_fs_classification"].value_counts(dropna=False).to_dict(),
        "rep_fraction": args.rep_fraction,
        "feature_columns": feature_columns,
        "outputs": {
            "features_csv": str(feature_csv),
            "feature_ranks_csv": str(rank_csv),
            "class_summary_csv": str(class_summary_csv),
            "correlation_csv": str(corr_csv),
            "pairwise_scatter_matrix": str(pairplot_path),
            "top_pairwise_scatter": str(top_pairs_path),
            "correlation_matrix_png": str(corr_path),
            "feature_rank_bars": str(rank_path),
        },
        "notes": [
            "Exploratory only; production TTP-based FS/RS classifier is unchanged.",
            "Labels are existing fixed-threshold rs_fs_classification values from the current good-unit TTP table.",
            "Waveform features are recomputed from templates.average using the same best-PTP-channel logic as the waveform gallery.",
        ],
        "errors": errors,
    }
    provenance_path.write_text(json.dumps(provenance, indent=2, default=str) + "\n", encoding="utf-8")

    print(f"Input unit table: {input_csv}")
    print(f"Units analyzed: {len(features)}")
    print("Class counts:")
    print(features["rs_fs_classification"].value_counts(dropna=False).to_string())
    print(f"Feature table: {feature_csv}")
    print(f"Feature ranks: {rank_csv}")
    print(f"Pairwise scatter matrix: {pairplot_path}")
    print(f"Top pairwise scatter: {top_pairs_path}")
    print(f"Correlation matrix: {corr_path}")
    print(f"Feature rank bars: {rank_path}")
    print(f"Provenance: {provenance_path}")
    if errors:
        print(f"Skipped {len(errors)} analyzer/unit entries; details: {error_path}")
    print("\nTop ranked features:")
    print(rank_table.head(12).to_string(index=False))


def _extract_features(si, source: pd.DataFrame, *, rep_fraction: float) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict[str, object]] = []
    errors: list[str] = []
    for analyzer_path_text, group in source.groupby("analyzer_path", dropna=False):
        analyzer_path = Path(str(analyzer_path_text))
        try:
            analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
            templates_ext = analyzer.get_extension("templates")
            if templates_ext is None:
                raise ValueError("missing templates extension")
            templates = _templates_average(templates_ext)
            sampling_frequency = float(analyzer.recording.get_sampling_frequency())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{analyzer_path}: {type(exc).__name__}: {exc}")
            continue

        for _, row in group.iterrows():
            try:
                unit_index = int(row["unit_index"])
                template = np.asarray(templates[unit_index], dtype=float)
                if template.ndim != 2 or not np.isfinite(template).any():
                    raise ValueError(f"empty/nonfinite template for unit_index={unit_index}")
                channel_ptp = np.ptp(template, axis=0)
                best_channel_index = int(np.nanargmax(channel_ptp))
                best_waveform = template[:, best_channel_index]
                nbefore = int(getattr(templates_ext, "nbefore", np.nanargmin(best_waveform)))
                time_ms = (np.arange(best_waveform.size) - nbefore) / sampling_frequency * 1000.0
                metrics = _measure_spiketurnpike_waveform_metrics(
                    best_waveform,
                    time_ms,
                    rep_fraction=rep_fraction,
                )
                rows.append(_feature_row(row, analyzer_path, unit_index, best_channel_index, best_waveform, metrics))
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"{row.get('recording')} / {row.get('well')} unit={row.get('unit_id')}: "
                    f"{type(exc).__name__}: {exc}"
                )
    if not rows:
        raise SystemExit("No waveform feature rows could be extracted.")
    return pd.DataFrame(rows), errors


def _feature_row(
    row: pd.Series,
    analyzer_path: Path,
    unit_index: int,
    best_channel_index: int,
    waveform_uV: np.ndarray,
    metrics: dict[str, object],
) -> dict[str, object]:
    trough_index = int(metrics["trough_index"])
    pre_peak_index = int(metrics["pre_peak_index"])
    rebound_peak_index = int(metrics["rebound_peak_index"])
    trough_value = float(waveform_uV[trough_index]) if trough_index >= 0 else np.nan
    pre_peak_value = float(waveform_uV[pre_peak_index]) if pre_peak_index >= 0 else np.nan
    post_peak_value = float(waveform_uV[rebound_peak_index]) if rebound_peak_index >= 0 else np.nan
    pre_peak_amplitude = pre_peak_value - trough_value if np.isfinite(pre_peak_value) and np.isfinite(trough_value) else np.nan
    post_peak_amplitude = post_peak_value - trough_value if np.isfinite(post_peak_value) and np.isfinite(trough_value) else np.nan
    trough_to_peak_ms = float(metrics["trough_to_peak_duration_ms"])
    pre_to_trough_ms = float(metrics["trough_time_ms"] - metrics["pre_peak_time_ms"])
    rep_ms = float(metrics["repolarization_time_ms"])
    rep_threshold_uV = float(metrics["rep_threshold_uV"])
    amplitude_sum = pre_peak_amplitude + post_peak_amplitude
    waveform_asymmetry = (
        (post_peak_amplitude - pre_peak_amplitude) / amplitude_sum
        if np.isfinite(amplitude_sum) and amplitude_sum > 0
        else np.nan
    )
    depolarization_slope = (trough_value - pre_peak_value) / pre_to_trough_ms if pre_to_trough_ms > 0 else np.nan
    rebound_slope = post_peak_amplitude / trough_to_peak_ms if trough_to_peak_ms > 0 else np.nan
    repolarization_slope = (rep_threshold_uV - trough_value) / rep_ms if rep_ms > 0 else np.nan
    return {
        "recording": row["recording"],
        "well": row["well"],
        "plate_family": row["plate_family"],
        "unit_id": row["unit_id"],
        "unit_index": unit_index,
        "KSLabel": row["KSLabel"],
        "rs_fs_classification": row["rs_fs_classification"],
        "analyzer_path": str(analyzer_path),
        "template_reference": f"templates.average[unit_index={unit_index},channel_index={best_channel_index}]",
        "best_channel_index": best_channel_index,
        "template_ptp_best_channel_uV": float(np.ptp(waveform_uV)),
        "template_trough_best_channel_uV": trough_value,
        "template_peak_best_channel_uV": float(np.nanmax(waveform_uV)),
        "spiketurnpike_amplitude_uV": float(metrics["spiketurnpike_amplitude_uV"]),
        "trough_to_peak_duration_ms": trough_to_peak_ms,
        "repolarization_time_ms": rep_ms,
        "spike_half_width_ms": float(metrics["spike_half_width_ms"]),
        "pre_peak_value_uV": pre_peak_value,
        "post_peak_value_uV": post_peak_value,
        "pre_peak_amplitude_uV": pre_peak_amplitude,
        "post_peak_amplitude_uV": post_peak_amplitude,
        "peak1_normalized_amplitude": float(metrics["peak1_normalized_amplitude"]),
        "peak2_normalized_amplitude": float(metrics["peak2_normalized_amplitude"]),
        "peak1_to_trough_ratio": float(metrics["peak1_to_trough_ratio"]),
        "peak2_to_trough_ratio": float(metrics["peak2_to_trough_ratio"]),
        "peak_to_peak_ratio": float(metrics["peak_to_peak_ratio"]),
        "waveform_asymmetry": waveform_asymmetry,
        "pre_trough_depolarization_slope_uV_per_ms": depolarization_slope,
        "post_trough_rebound_slope_uV_per_ms": rebound_slope,
        "rep50_recovery_slope_uV_per_ms": repolarization_slope,
        "trough_index": trough_index,
        "pre_peak_index": pre_peak_index,
        "rebound_peak_index": rebound_peak_index,
        "rep_recovery_index": int(metrics["rep_recovery_index"]),
        "half_width_start_index": int(metrics["half_width_start_index"]),
        "half_width_end_index": int(metrics["half_width_end_index"]),
    }


def _templates_average(templates_ext) -> np.ndarray:
    try:
        return np.asarray(templates_ext.get_data(operator="average"), dtype=float)
    except TypeError:
        templates_data = templates_ext.get_data()
        if isinstance(templates_data, dict):
            templates_data = templates_data.get("average")
        return np.asarray(templates_data, dtype=float)


def _feature_columns(features: pd.DataFrame) -> list[str]:
    excluded = {
        "recording",
        "well",
        "plate_family",
        "unit_id",
        "unit_index",
        "KSLabel",
        "rs_fs_classification",
        "analyzer_path",
        "template_reference",
        "best_channel_index",
        "trough_index",
        "pre_peak_index",
        "rebound_peak_index",
        "rep_recovery_index",
        "half_width_start_index",
        "half_width_end_index",
    }
    return [col for col in features.columns if col not in excluded and pd.api.types.is_numeric_dtype(features[col])]


def _rank_features(
    features: pd.DataFrame,
    feature_columns: list[str],
    *,
    random_state: int,
    LabelEncoder,
    SimpleImputer,
    StandardScaler,
    RandomForestClassifier,
    permutation_importance,
    f_classif,
    mutual_info_classif,
    make_pipeline,
) -> pd.DataFrame:
    valid = features.loc[features["rs_fs_classification"].isin(CLASS_ORDER)].copy()
    x = valid[feature_columns].replace([np.inf, -np.inf], np.nan)
    y = LabelEncoder().fit_transform(valid["rs_fs_classification"])
    imputer = SimpleImputer(strategy="median")
    x_imputed = imputer.fit_transform(x)
    f_values, p_values = f_classif(x_imputed, y)
    mi_values = mutual_info_classif(x_imputed, y, random_state=random_state)
    rf = RandomForestClassifier(
        n_estimators=600,
        class_weight="balanced",
        random_state=random_state,
        min_samples_leaf=3,
    )
    pipeline = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), rf)
    pipeline.fit(x, y)
    rf_importance = pipeline.named_steps["randomforestclassifier"].feature_importances_
    perm = permutation_importance(
        pipeline,
        x,
        y,
        scoring="balanced_accuracy",
        random_state=random_state,
        n_repeats=40,
    )
    ranks = pd.DataFrame(
        {
            "feature": feature_columns,
            "anova_f": f_values,
            "anova_p": p_values,
            "mutual_info": mi_values,
            "random_forest_importance": rf_importance,
            "permutation_importance_balanced_accuracy_mean": perm.importances_mean,
            "permutation_importance_balanced_accuracy_std": perm.importances_std,
        }
    )
    for metric in [
        "anova_f",
        "mutual_info",
        "random_forest_importance",
        "permutation_importance_balanced_accuracy_mean",
    ]:
        ranks[f"{metric}_rank"] = ranks[metric].rank(ascending=False, method="min")
    rank_cols = [col for col in ranks.columns if col.endswith("_rank")]
    ranks["mean_rank"] = ranks[rank_cols].mean(axis=1)
    return ranks.sort_values(["mean_rank", "anova_p"], ignore_index=True)


def _class_summary(features: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for label in CLASS_ORDER:
        subset = features.loc[features["rs_fs_classification"].eq(label)]
        for feature in feature_columns:
            values = pd.to_numeric(subset[feature], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
            rows.append(
                {
                    "rs_fs_classification": label,
                    "feature": feature,
                    "count": int(values.size),
                    "median": float(values.median()) if not values.empty else np.nan,
                    "mean": float(values.mean()) if not values.empty else np.nan,
                    "std": float(values.std()) if values.size > 1 else np.nan,
                    "min": float(values.min()) if not values.empty else np.nan,
                    "max": float(values.max()) if not values.empty else np.nan,
                }
            )
    return pd.DataFrame(rows)


def _plot_pairwise_matrix(plt, features: pd.DataFrame, selected_features: list[str], output_path: Path) -> None:
    selected = [feature for feature in selected_features if feature in features.columns]
    n = len(selected)
    fig, axes = plt.subplots(n, n, figsize=(2.05 * n, 2.05 * n), squeeze=False)
    for row_index, y_feature in enumerate(selected):
        for col_index, x_feature in enumerate(selected):
            ax = axes[row_index, col_index]
            if row_index == col_index:
                for label in CLASS_ORDER:
                    values = features.loc[features["rs_fs_classification"].eq(label), x_feature].dropna()
                    if values.empty:
                        continue
                    ax.hist(values, bins=18, alpha=0.58, color=CLASS_COLORS[label])
            else:
                for label in CLASS_ORDER:
                    subset = features.loc[features["rs_fs_classification"].eq(label)]
                    ax.scatter(
                        subset[x_feature],
                        subset[y_feature],
                        s=13,
                        alpha=0.72,
                        linewidths=0,
                        color=CLASS_COLORS[label],
                    )
            if row_index == n - 1:
                ax.set_xlabel(_short_label(x_feature), fontsize=8)
            else:
                ax.set_xticklabels([])
            if col_index == 0:
                ax.set_ylabel(_short_label(y_feature), fontsize=8)
            else:
                ax.set_yticklabels([])
            ax.tick_params(labelsize=7, length=2)
    handles = [
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=CLASS_COLORS[label], label=label, markersize=7)
        for label in CLASS_ORDER
    ]
    fig.legend(handles=handles, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 0.975), ncol=3)
    fig.suptitle("Current good-unit waveform features by fixed TTP label", y=0.998, fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_top_pairs(plt, features: pd.DataFrame, rank_table: pd.DataFrame, output_path: Path) -> None:
    top_features = rank_table["feature"].head(6).tolist()
    pairs = list(combinations(top_features, 2))[:12]
    ncols = 4
    nrows = int(np.ceil(len(pairs) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.4 * nrows), squeeze=False)
    for axis, pair in zip(axes.ravel(), pairs, strict=False):
        x_feature, y_feature = pair
        for label in CLASS_ORDER:
            subset = features.loc[features["rs_fs_classification"].eq(label)]
            axis.scatter(
                subset[x_feature],
                subset[y_feature],
                s=20,
                alpha=0.78,
                linewidths=0,
                color=CLASS_COLORS[label],
                label=label,
            )
        axis.set_xlabel(_short_label(x_feature), fontsize=9)
        axis.set_ylabel(_short_label(y_feature), fontsize=9)
        axis.tick_params(labelsize=8)
    for axis in axes.ravel()[len(pairs) :]:
        axis.axis("off")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 0.965), ncol=3)
    fig.suptitle("Top ranked waveform-feature pairs", y=0.998, fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_correlation_matrix(plt, corr: pd.DataFrame, output_path: Path) -> None:
    labels = [_short_label(col) for col in corr.columns]
    fig, ax = plt.subplots(figsize=(max(8, 0.52 * len(labels)), max(7, 0.52 * len(labels))))
    image = ax.imshow(corr.to_numpy(), cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(np.arange(len(labels)), labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(np.arange(len(labels)), labels, fontsize=8)
    fig.colorbar(image, ax=ax, shrink=0.8, label="Spearman rho")
    ax.set_title("Waveform feature correlation matrix")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_feature_rank_bars(plt, rank_table: pd.DataFrame, output_path: Path) -> None:
    top = rank_table.head(14).iloc[::-1]
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 6.0), sharey=True)
    metrics = [
        ("anova_f", "ANOVA F"),
        ("mutual_info", "Mutual info"),
        ("random_forest_importance", "Random forest"),
    ]
    for ax, (metric, title) in zip(axes, metrics, strict=True):
        ax.barh([_short_label(value) for value in top["feature"]], top[metric], color="#4c78a8")
        ax.set_title(title)
        ax.tick_params(labelsize=8)
    fig.suptitle("Feature ranking against fixed FS/borderline/RS labels", y=0.99)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _short_label(name: str) -> str:
    replacements = {
        "trough_to_peak_duration_ms": "TTP ms",
        "repolarization_time_ms": "REP50 ms",
        "spike_half_width_ms": "half-width ms",
        "template_ptp_best_channel_uV": "PTP uV",
        "spiketurnpike_amplitude_uV": "trough amp uV",
        "post_trough_rebound_slope_uV_per_ms": "rebound slope",
        "pre_trough_depolarization_slope_uV_per_ms": "downstroke slope",
        "rep50_recovery_slope_uV_per_ms": "REP50 slope",
        "waveform_asymmetry": "asymmetry",
        "peak_to_peak_ratio": "peak ratio",
        "peak1_to_trough_ratio": "pre/trough",
        "peak2_to_trough_ratio": "post/trough",
    }
    return replacements.get(name, name.replace("_", " "))


if __name__ == "__main__":
    main()
