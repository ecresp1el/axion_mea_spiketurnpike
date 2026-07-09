#!/usr/bin/env python
"""Explore a two-component GMM split of current good-unit TTP values.

This is intentionally isolated from the production FS/RS classification code. It
reads the current good-unit TTP table, fits a 2-component Gaussian Mixture Model,
finds the weighted-density intersection, assigns posterior-probability labels,
and compares those exploratory labels against the current fixed-threshold labels.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from axion_mea.rs_fs_classification import RSFSClassificationConfig  # noqa: E402


DEFAULT_JOB_DIR = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/jobs/"
    "step1_nonlfp_th5_v5_ground_truth_latest"
)
DEFAULT_DATE_LABEL = "20260709"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, default=DEFAULT_JOB_DIR)
    parser.add_argument("--date-label", default=DEFAULT_DATE_LABEL)
    parser.add_argument("--input-csv", type=Path)
    parser.add_argument("--posterior-threshold", type=float, default=0.8)
    parser.add_argument("--random-state", type=int, default=13)
    parser.add_argument("--n-init", type=int, default=50)
    args = parser.parse_args()

    if not 0.5 < args.posterior_threshold < 1.0:
        raise SystemExit("--posterior-threshold must be > 0.5 and < 1.0 for a 2-component GMM.")

    from sklearn.mixture import GaussianMixture

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    job_dir = args.job_dir.expanduser().resolve()
    input_csv = args.input_csv or job_dir / (
        f"good_kslabel_ttp_distribution_template_best_ptp_{args.date_label}.csv"
    )
    table = pd.read_csv(input_csv)
    finite = table.dropna(subset=["trough_to_peak_duration_ms"]).copy()
    if finite.empty:
        raise SystemExit(f"No finite trough_to_peak_duration_ms values found in {input_csv}")

    x = finite["trough_to_peak_duration_ms"].astype(float).to_numpy().reshape(-1, 1)
    model = GaussianMixture(
        n_components=2,
        covariance_type="full",
        n_init=args.n_init,
        random_state=args.random_state,
    )
    model.fit(x)
    params = _ordered_gmm_params(model)
    posterior = model.predict_proba(x)[:, params["order"]]
    fs_posterior = posterior[:, 0]
    rs_posterior = posterior[:, 1]
    gmm_classification = np.full(len(finite), "borderline", dtype=object)
    gmm_classification[fs_posterior > args.posterior_threshold] = "FS_like"
    gmm_classification[rs_posterior > args.posterior_threshold] = "RS_like"

    fixed_labels = _fixed_labels(finite["trough_to_peak_duration_ms"])
    if "rs_fs_classification" in finite.columns:
        fixed_labels = finite["rs_fs_classification"].astype(str).to_numpy()

    boundary = _component_intersection(
        means=params["means"],
        sigmas=params["sigmas"],
        weights=params["weights"],
        observed_min=float(np.nanmin(x)),
        observed_max=float(np.nanmax(x)),
    )

    out = finite.copy()
    out["gmm_fs_posterior"] = fs_posterior
    out["gmm_rs_posterior"] = rs_posterior
    out["gmm_max_posterior"] = np.maximum(fs_posterior, rs_posterior)
    out["gmm_rs_fs_classification"] = gmm_classification
    out["fixed_threshold_rs_fs_classification"] = fixed_labels
    out["gmm_decision_boundary_ms"] = boundary["boundary_ms"]
    out["gmm_boundary_rs_fs_classification"] = np.where(
        out["trough_to_peak_duration_ms"].astype(float) <= float(boundary["boundary_ms"]),
        "FS_like",
        "RS_like",
    )

    output_stem = (
        f"good_kslabel_ttp_gmm_2component_posterior{_threshold_label(args.posterior_threshold)}_"
        f"{args.date_label}"
    )
    posterior_csv = job_dir / f"{output_stem}_unit_posteriors.csv"
    counts_csv = job_dir / f"{output_stem}_counts.csv"
    comparison_csv = job_dir / f"{output_stem}_fixed_vs_gmm_counts.csv"
    boundary_comparison_csv = job_dir / f"{output_stem}_fixed_vs_boundary_counts.csv"
    boundary_json = job_dir / f"{output_stem}_boundary.json"
    figure_path = job_dir / f"{output_stem}.png"

    out.to_csv(posterior_csv, index=False)
    counts = _counts_table(out)
    counts.to_csv(counts_csv, index=False)
    comparison = pd.crosstab(
        out["fixed_threshold_rs_fs_classification"],
        out["gmm_rs_fs_classification"],
        rownames=["fixed_threshold"],
        colnames=["gmm_posterior"],
        dropna=False,
    )
    comparison.to_csv(comparison_csv)
    boundary_comparison = pd.crosstab(
        out["fixed_threshold_rs_fs_classification"],
        out["gmm_boundary_rs_fs_classification"],
        rownames=["fixed_threshold"],
        colnames=["gmm_boundary"],
        dropna=False,
    )
    boundary_comparison.to_csv(boundary_comparison_csv)
    boundary_payload = _boundary_payload(
        args,
        input_csv,
        posterior_csv,
        counts_csv,
        comparison_csv,
        boundary_comparison_csv,
        figure_path,
        params,
        boundary,
        out,
    )
    boundary_json.write_text(json.dumps(boundary_payload, indent=2, default=str) + "\n", encoding="utf-8")
    _plot_gmm(plt, out, params, boundary, figure_path)

    print(f"Input TTP table: {input_csv}")
    print(f"Units fit: {len(out)}")
    print(f"GMM boundary: {boundary['boundary_ms']:.6g} ms ({boundary['selection_reason']})")
    print(f"Unit posterior CSV: {posterior_csv}")
    print(f"Counts CSV: {counts_csv}")
    print(f"Fixed-vs-GMM comparison CSV: {comparison_csv}")
    print(f"Fixed-vs-boundary comparison CSV: {boundary_comparison_csv}")
    print(f"Boundary/provenance JSON: {boundary_json}")
    print(f"GMM figure: {figure_path}")
    print("\nGMM counts:")
    print(out["gmm_rs_fs_classification"].value_counts().to_string())
    print("\nFixed-threshold counts:")
    print(out["fixed_threshold_rs_fs_classification"].value_counts().to_string())
    print("\nFixed threshold vs GMM:")
    print(comparison.to_string())
    print("\nFixed threshold vs GMM boundary:")
    print(boundary_comparison.to_string())


def _ordered_gmm_params(model) -> dict[str, np.ndarray]:
    means = model.means_.reshape(-1)
    variances = model.covariances_.reshape(-1)
    sigmas = np.sqrt(variances)
    weights = model.weights_.reshape(-1)
    order = np.argsort(means)
    return {
        "order": order,
        "means": means[order],
        "variances": variances[order],
        "sigmas": sigmas[order],
        "weights": weights[order],
    }


def _component_intersection(
    *,
    means: np.ndarray,
    sigmas: np.ndarray,
    weights: np.ndarray,
    observed_min: float,
    observed_max: float,
) -> dict[str, object]:
    mean_low, mean_high = float(means[0]), float(means[1])
    sigma_low, sigma_high = float(sigmas[0]), float(sigmas[1])
    weight_low, weight_high = float(weights[0]), float(weights[1])
    roots = _weighted_gaussian_intersection_roots(mean_low, sigma_low, weight_low, mean_high, sigma_high, weight_high)
    finite_roots = [float(root) for root in roots if np.isfinite(root)]
    between_means = [root for root in finite_roots if mean_low <= root <= mean_high]
    if between_means:
        boundary = min(between_means, key=lambda root: abs(root - (mean_low + mean_high) / 2.0))
        reason = "root_between_component_means"
    elif finite_roots:
        data_range_roots = [root for root in finite_roots if observed_min <= root <= observed_max]
        candidates = data_range_roots or finite_roots
        boundary = min(candidates, key=lambda root: abs(root - (mean_low + mean_high) / 2.0))
        reason = "nearest_root_to_midpoint"
    else:
        boundary = (mean_low + mean_high) / 2.0
        reason = "fallback_midpoint_no_finite_root"
    return {
        "boundary_ms": float(boundary),
        "all_intersection_roots_ms": finite_roots,
        "selection_reason": reason,
    }


def _weighted_gaussian_intersection_roots(
    mean_1: float,
    sigma_1: float,
    weight_1: float,
    mean_2: float,
    sigma_2: float,
    weight_2: float,
) -> list[float]:
    if sigma_1 <= 0 or sigma_2 <= 0 or weight_1 <= 0 or weight_2 <= 0:
        return []
    variance_1 = sigma_1**2
    variance_2 = sigma_2**2
    constant = math.log(weight_1 / sigma_1) - math.log(weight_2 / sigma_2)
    a = (1.0 / (2.0 * variance_2)) - (1.0 / (2.0 * variance_1))
    b = (mean_1 / variance_1) - (mean_2 / variance_2)
    c = (mean_2**2 / (2.0 * variance_2)) - (mean_1**2 / (2.0 * variance_1)) + constant
    if abs(a) < 1e-12:
        if abs(b) < 1e-12:
            return []
        return [-c / b]
    discriminant = b**2 - 4.0 * a * c
    if discriminant < 0:
        return []
    sqrt_discriminant = math.sqrt(discriminant)
    return [(-b - sqrt_discriminant) / (2.0 * a), (-b + sqrt_discriminant) / (2.0 * a)]


def _fixed_labels(ttp_ms: pd.Series) -> np.ndarray:
    config = RSFSClassificationConfig()
    values = pd.to_numeric(ttp_ms, errors="coerce")
    labels = np.full(len(values), config.borderline_label, dtype=object)
    labels[values.isna().to_numpy()] = config.unknown_label
    labels[(values <= config.fs_upper_bound_ms).fillna(False).to_numpy()] = config.fs_label
    labels[(values >= config.rs_lower_bound_ms).fillna(False).to_numpy()] = config.rs_label
    return labels


def _counts_table(table: pd.DataFrame) -> pd.DataFrame:
    gmm_counts = table["gmm_rs_fs_classification"].value_counts(dropna=False).rename("gmm_count")
    boundary_counts = table["gmm_boundary_rs_fs_classification"].value_counts(dropna=False).rename("gmm_boundary_count")
    fixed_counts = table["fixed_threshold_rs_fs_classification"].value_counts(dropna=False).rename("fixed_count")
    counts = pd.concat([gmm_counts, boundary_counts, fixed_counts], axis=1).fillna(0).astype(int)
    counts.index.name = "classification"
    return counts.reset_index()


def _boundary_payload(
    args: argparse.Namespace,
    input_csv: Path,
    posterior_csv: Path,
    counts_csv: Path,
    comparison_csv: Path,
    boundary_comparison_csv: Path,
    figure_path: Path,
    params: dict[str, np.ndarray],
    boundary: dict[str, object],
    table: pd.DataFrame,
) -> dict[str, object]:
    config = RSFSClassificationConfig()
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": str(Path(__file__).resolve()),
        "input_csv": str(input_csv),
        "outputs": {
            "unit_posteriors_csv": str(posterior_csv),
            "counts_csv": str(counts_csv),
            "fixed_vs_gmm_counts_csv": str(comparison_csv),
            "fixed_vs_boundary_counts_csv": str(boundary_comparison_csv),
            "figure": str(figure_path),
        },
        "posterior_threshold": args.posterior_threshold,
        "random_state": args.random_state,
        "n_init": args.n_init,
        "gmm_components_ordered_by_ttp_mean": [
            {
                "component": "FS_like_low_ttp",
                "mean_ms": float(params["means"][0]),
                "sigma_ms": float(params["sigmas"][0]),
                "variance_ms2": float(params["variances"][0]),
                "weight": float(params["weights"][0]),
            },
            {
                "component": "RS_like_high_ttp",
                "mean_ms": float(params["means"][1]),
                "sigma_ms": float(params["sigmas"][1]),
                "variance_ms2": float(params["variances"][1]),
                "weight": float(params["weights"][1]),
            },
        ],
        "inferred_boundary": boundary,
        "fixed_threshold_classifier": config.provenance(),
        "unit_count": int(len(table)),
        "gmm_counts": table["gmm_rs_fs_classification"].value_counts(dropna=False).to_dict(),
        "gmm_boundary_counts": table["gmm_boundary_rs_fs_classification"].value_counts(dropna=False).to_dict(),
        "fixed_threshold_counts": table["fixed_threshold_rs_fs_classification"].value_counts(dropna=False).to_dict(),
    }


def _plot_gmm(plt, table: pd.DataFrame, params: dict[str, np.ndarray], boundary: dict[str, object], output_path: Path) -> None:
    config = RSFSClassificationConfig()
    values = table["trough_to_peak_duration_ms"].astype(float).to_numpy()
    x_min = max(0.0, float(np.nanmin(values)) - 0.08)
    x_max = float(np.nanmax(values)) + 0.16
    x_grid = np.linspace(x_min, x_max, 900)
    component_low = params["weights"][0] * _normal_pdf(x_grid, params["means"][0], params["sigmas"][0])
    component_high = params["weights"][1] * _normal_pdf(x_grid, params["means"][1], params["sigmas"][1])
    combined = component_low + component_high

    fig, ax = plt.subplots(figsize=(9.5, 5.8))
    bins = np.arange(0.0, max(2.0, x_max + config.sample_dt_ms), config.sample_dt_ms)
    ax.hist(values, bins=bins, density=True, alpha=0.34, color="#8a8a8a", label=f"TTP histogram (n={len(values)})")
    ax.plot(x_grid, component_low, color="#d55e00", linewidth=2.2, label="GMM low-TTP component")
    ax.plot(x_grid, component_high, color="#0072b2", linewidth=2.2, label="GMM high-TTP component")
    ax.plot(x_grid, combined, color="#1f1f1f", linewidth=2.4, label="GMM combined density")
    ax.axvline(float(boundary["boundary_ms"]), color="#6a3d9a", linewidth=2.0, linestyle="-.", label="GMM density intersection")
    ax.axvline(config.fs_upper_bound_ms, color="#1f1f1f", linestyle="--", linewidth=1.1, alpha=0.75, label="Fixed FS bound")
    ax.axvline(config.rs_lower_bound_ms, color="#1f1f1f", linestyle=":", linewidth=1.4, alpha=0.75, label="Fixed RS bound")

    text = (
        f"GMM boundary = {float(boundary['boundary_ms']):.3f} ms\n"
        f"low mean = {params['means'][0]:.3f} ms, high mean = {params['means'][1]:.3f} ms\n"
        f"posterior labels: {table['gmm_rs_fs_classification'].value_counts().to_dict()}\n"
        f"boundary labels: {table['gmm_boundary_rs_fs_classification'].value_counts().to_dict()}\n"
        f"fixed labels: {table['fixed_threshold_rs_fs_classification'].value_counts().to_dict()}"
    )
    ax.text(
        0.985,
        0.96,
        text,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "0.72", "alpha": 0.94},
    )
    ax.set_xlabel("Trough-to-peak time (ms)")
    ax.set_ylabel("Density")
    ax.set_title("Exploratory 2-component GMM on current KSLabel=good TTP values")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _normal_pdf(x: np.ndarray, mean: float, sigma: float) -> np.ndarray:
    return np.exp(-0.5 * ((x - mean) / sigma) ** 2) / (sigma * np.sqrt(2.0 * np.pi))


def _threshold_label(value: float) -> str:
    return str(value).replace(".", "p")


if __name__ == "__main__":
    main()
