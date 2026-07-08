"""Table-first RS/FS plots for the canonical Step 3 dataset."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .master_unit_table import CANONICAL_MASTER_UNIT_TABLE, load_canonical_master_unit_table
from .rs_fs_classification import RSFSClassificationConfig


DEFAULT_RS_FS_FIGURE_DIR = CANONICAL_MASTER_UNIT_TABLE.parent / "figures" / "rs_fs_classification"

CLASS_COLORS = {
    "FS_like": "#d55e00",
    "RS_like": "#0072b2",
    "borderline": "#7a7a7a",
    "unknown": "#bdbdbd",
}

CLASS_ORDER = ["FS_like", "borderline", "RS_like", "unknown"]


def write_rs_fs_plots(
    table: pd.DataFrame | None = None,
    input_csv: str | Path = CANONICAL_MASTER_UNIT_TABLE,
    output_dir: str | Path = DEFAULT_RS_FS_FIGURE_DIR,
    config: RSFSClassificationConfig | None = None,
) -> dict[str, Path]:
    """Write RS/FS sanity-check plots from the canonical table."""

    config = config or RSFSClassificationConfig()
    table = load_canonical_master_unit_table(input_csv) if table is None else table.copy()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = {
        "trough_to_peak_histogram": output_dir / "figure__rs_fs_trough_to_peak_histogram.png",
        "feature_space": output_dir / "figure__rs_fs_feature_space.png",
        "firing_rate_by_class": output_dir / "figure__rs_fs_firing_rate_by_class.png",
        "class_counts": output_dir / "figure__rs_fs_class_counts.png",
    }
    _plot_trough_to_peak_histogram(table, outputs["trough_to_peak_histogram"], config)
    _plot_feature_space(table, outputs["feature_space"], config)
    _plot_firing_rate_by_class(table, outputs["firing_rate_by_class"])
    _plot_class_counts(table, outputs["class_counts"])
    return outputs


def _plot_trough_to_peak_histogram(table: pd.DataFrame, output_path: Path, config: RSFSClassificationConfig) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 5.0))
    valid = table.dropna(subset=["trough_to_peak_duration_ms"])
    bins = np.arange(0.0, max(5.0, float(valid["trough_to_peak_duration_ms"].max()) + 0.16), 0.08)
    for label in CLASS_ORDER:
        values = valid.loc[valid["rs_fs_classification"] == label, "trough_to_peak_duration_ms"]
        if values.empty:
            continue
        ax.hist(
            values,
            bins=bins,
            alpha=0.72,
            color=CLASS_COLORS.get(label, "#555555"),
            label=f"{label} (n={len(values)})",
        )
    ax.axvline(config.fs_upper_bound_ms, color="#1f1f1f", linestyle="--", linewidth=1.3)
    ax.axvline(config.rs_lower_bound_ms, color="#1f1f1f", linestyle="--", linewidth=1.3)
    ax.set_xlabel("Trough-to-peak duration (ms)")
    ax.set_ylabel("Unit count")
    ax.set_title("RS/FS classification by trough-to-peak duration")
    ax.legend(frameon=False)
    _save(fig, output_path)


def _plot_feature_space(table: pd.DataFrame, output_path: Path, config: RSFSClassificationConfig) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.8), sharex=True)
    for ax, y_col, ylabel in [
        (axes[0], "waveform_asymmetry", "Waveform asymmetry"),
        (axes[1], "repolarization_slope", "Repolarization slope"),
    ]:
        for label in CLASS_ORDER:
            subset = table.loc[table["rs_fs_classification"] == label]
            if subset.empty:
                continue
            ax.scatter(
                subset["trough_to_peak_duration_ms"],
                subset[y_col],
                s=18,
                alpha=0.72,
                linewidths=0,
                color=CLASS_COLORS.get(label, "#555555"),
                label=label,
            )
        ax.axvline(config.fs_upper_bound_ms, color="#1f1f1f", linestyle="--", linewidth=1.2)
        ax.axvline(config.rs_lower_bound_ms, color="#1f1f1f", linestyle="--", linewidth=1.2)
        ax.set_xlabel("Trough-to-peak duration (ms)")
        ax.set_ylabel(ylabel)
    axes[1].set_yscale("symlog", linthresh=1.0)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="upper center", ncol=4)
    fig.suptitle("RS/FS waveform feature space", y=0.99)
    _save(fig, output_path)


def _plot_firing_rate_by_class(table: pd.DataFrame, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.8, 4.8))
    data = [
        table.loc[table["rs_fs_classification"] == label, "firing_rate_hz"].dropna().to_numpy()
        for label in CLASS_ORDER
        if not table.loc[table["rs_fs_classification"] == label, "firing_rate_hz"].dropna().empty
    ]
    labels = [
        label
        for label in CLASS_ORDER
        if not table.loc[table["rs_fs_classification"] == label, "firing_rate_hz"].dropna().empty
    ]
    parts = ax.violinplot(data, showmeans=False, showmedians=True, showextrema=False)
    for body, label in zip(parts["bodies"], labels, strict=True):
        body.set_facecolor(CLASS_COLORS.get(label, "#555555"))
        body.set_edgecolor("none")
        body.set_alpha(0.7)
    parts["cmedians"].set_color("#1f1f1f")
    ax.set_xticks(range(1, len(labels) + 1), labels)
    ax.set_ylabel("Firing rate (Hz)")
    ax.set_title("Firing rate distribution by RS/FS class")
    _save(fig, output_path)


def _plot_class_counts(table: pd.DataFrame, output_path: Path) -> None:
    counts = table["rs_fs_classification"].value_counts().reindex(CLASS_ORDER).dropna().astype(int)
    fig, ax = plt.subplots(figsize=(7.0, 4.8))
    ax.bar(
        counts.index,
        counts.values,
        color=[CLASS_COLORS.get(label, "#555555") for label in counts.index],
        width=0.72,
    )
    for index, value in enumerate(counts.values):
        ax.text(index, value, str(value), ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("Unit count")
    ax.set_title("RS/FS class counts")
    _save(fig, output_path)


def _save(fig: plt.Figure, output_path: Path) -> None:
    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
