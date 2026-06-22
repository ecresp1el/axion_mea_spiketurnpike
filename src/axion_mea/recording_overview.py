from __future__ import annotations
"""Recording-level CSV parsing and overview plotting utilities.

This module is the first structured stage in the pipeline. It converts Axion's
CSV exports into normalized tables that later stages can trust:

1. `read_spike_list()` parses per-spike rows plus the embedded `Well Information`
   footer that carries treatment and active/control metadata.
2. `read_spike_counts()` converts the wide spike-count export into long-format
   well-level and electrode-level tables.
3. `read_environment()` extracts environmental telemetry when the file is
   present.
4. The plotting helpers generate recording-level context plots before any
   stimulation-locked analysis is performed.
"""

import csv
import json
import math
import re
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


WELL_RE = re.compile(r"^[A-F][1-8]$")
ELECTRODE_RE = re.compile(r"^(?P<well>[A-F][1-8])_(?P<channel>\d{2})$")


def find_first_file(data_dir: Path, suffix: str) -> Path | None:
    """Return the first non-resource-fork file in `data_dir` matching `suffix`."""
    matches = sorted(
        path
        for path in data_dir.glob(f"*{suffix}")
        if not path.name.startswith("._")
    )
    return matches[0] if matches else None


def sanitize_name(name: str) -> str:
    """Convert free text into a filesystem-safe project or folder name."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return cleaned.strip("_") or "recording"


def read_spike_list(path: Path) -> tuple[pd.DataFrame, dict[str, str], pd.DataFrame]:
    """Parse the Axion spike-list export and its embedded metadata blocks.

    Returns:
    - `spikes`: one row per spike with well, electrode, time, and amplitude.
    - `recording_metadata`: key-value metadata collected from the header rows.
    - `well_metadata`: parsed `Well Information` table with treatment labels and
      activity flags when present.
    """
    recording_metadata: dict[str, str] = {}
    spike_rows: list[dict[str, object]] = []
    well_info_rows: list[list[str]] = []
    in_well_info = False

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row:
                continue

            key = row[0].strip()
            if len(row) >= 2 and key and key not in recording_metadata:
                recording_metadata[key] = row[1].strip()

            if key == "Well Information":
                in_well_info = True
                continue

            if in_well_info:
                well_info_rows.append(row)
                continue

            if len(row) == 5:
                match = ELECTRODE_RE.fullmatch(row[3].strip())
                if match is not None:
                    try:
                        time_s = float(row[2])
                        amplitude_mv = float(row[4])
                    except ValueError:
                        continue

                    spike_rows.append(
                        {
                            "time_s": time_s,
                            "well": match.group("well"),
                            "electrode": row[3].strip(),
                            "channel_in_well": match.group("channel"),
                            "amplitude_mV": amplitude_mv,
                        }
                    )
                    continue

    spikes = pd.DataFrame(spike_rows)
    well_metadata = parse_well_information(well_info_rows)
    return spikes, recording_metadata, well_metadata


def parse_well_information(rows: list[list[str]]) -> pd.DataFrame:
    """Convert the raw `Well Information` footer rows into a tidy table."""
    if not rows or not rows[0] or rows[0][0].strip() != "Well":
        return pd.DataFrame(columns=["well"])

    wells = [item.strip() for item in rows[0][1:] if item.strip()]
    data: dict[str, list[str]] = {}

    for row in rows[1:]:
        if not row:
            continue
        label = row[0].strip()
        if not label:
            continue
        values = [item.strip() for item in row[1 : 1 + len(wells)]]
        data[label] = values

    well_metadata = pd.DataFrame(data, index=wells).reset_index(names="well")

    for col in ["Active", "Control"]:
        if col in well_metadata.columns:
            well_metadata[col] = well_metadata[col].map(
                {"True": True, "False": False, "": pd.NA}
            )

    for col in well_metadata.columns:
        if well_metadata[col].dtype == object:
            well_metadata[col] = well_metadata[col].replace("", pd.NA)

    info_cols = [col for col in well_metadata.columns if col != "well"]
    keep_mask = well_metadata[info_cols].notna().any(axis=1) if info_cols else []
    return well_metadata.loc[keep_mask].reset_index(drop=True)


def read_spike_counts(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convert the wide spike-count export into long-format well and channel tables."""
    counts = pd.read_csv(path, encoding="utf-8-sig")
    start = pd.to_numeric(counts["Interval Start (S)"], errors="coerce")
    end = pd.to_numeric(counts["Interval End (S)"], errors="coerce")
    counts = counts.loc[start.notna() & end.notna()].copy()
    counts["interval_start_s"] = pd.to_numeric(counts["Interval Start (S)"])
    counts["interval_end_s"] = pd.to_numeric(counts["Interval End (S)"])

    well_cols = [
        col for col in counts.columns if isinstance(col, str) and WELL_RE.fullmatch(col)
    ]
    electrode_cols = [
        col
        for col in counts.columns
        if isinstance(col, str) and ELECTRODE_RE.fullmatch(col)
    ]

    well_frame = counts[["interval_start_s", "interval_end_s"] + well_cols].copy()
    for col in well_cols:
        well_frame[col] = pd.to_numeric(well_frame[col], errors="coerce")

    well_long = well_frame.melt(
        id_vars=["interval_start_s", "interval_end_s"],
        value_vars=well_cols,
        var_name="well",
        value_name="spike_count",
    ).dropna(subset=["spike_count"])
    well_long["spike_count"] = well_long["spike_count"].astype(int)

    electrode_frame = counts[["interval_start_s", "interval_end_s"] + electrode_cols].copy()
    for col in electrode_cols:
        electrode_frame[col] = pd.to_numeric(electrode_frame[col], errors="coerce")

    electrode_long = electrode_frame.melt(
        id_vars=["interval_start_s", "interval_end_s"],
        value_vars=electrode_cols,
        var_name="electrode",
        value_name="spike_count",
    ).dropna(subset=["spike_count"])
    electrode_long["spike_count"] = electrode_long["spike_count"].astype(int)
    electrode_long["well"] = electrode_long["electrode"].str.extract(ELECTRODE_RE)["well"]
    electrode_long["channel_in_well"] = electrode_long["electrode"].str.extract(
        ELECTRODE_RE
    )["channel"]

    return well_long, electrode_long


def read_environment(path: Path) -> pd.DataFrame:
    """Read environmental telemetry recorded alongside the spike export."""
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row:
                continue
            if row[0].strip() == "Well Information":
                break
            rows.append(row)

    if not rows:
        return pd.DataFrame()

    header = rows[0]
    env = pd.DataFrame(rows[1:], columns=header)
    env["Time (s)"] = pd.to_numeric(env["Time (s)"], errors="coerce")
    env = env.loc[env["Time (s)"].notna()].copy()
    rename_map = {
        "Time (s)": "time_s",
        "Heater Enabled": "heater_enabled",
        "Heater Set Point (°C)": "heater_setpoint_c",
        "Plate Temperature (°C)": "plate_temperature_c",
        "Gas Mixer Enabled": "gas_mixer_enabled",
        "CO2 Set Point (% CO₂)": "co2_setpoint_pct",
        "CO2 Concentration (% CO₂)": "co2_concentration_pct",
    }
    env = env.rename(columns=rename_map)

    for col in [
        "heater_setpoint_c",
        "plate_temperature_c",
        "co2_setpoint_pct",
        "co2_concentration_pct",
    ]:
        if col in env.columns:
            env[col] = pd.to_numeric(env[col], errors="coerce")

    return env


def pick_active_wells(well_long: pd.DataFrame, well_metadata: pd.DataFrame) -> list[str]:
    """Choose wells to display in recording-level overview plots.

    The function prefers wells explicitly marked `Active == True` when that
    annotation is present, but falls back to wells with non-zero spike counts.
    """
    well_totals = (
        well_long.groupby("well", as_index=False)["spike_count"]
        .sum()
        .sort_values("spike_count", ascending=False)
    )
    active_by_spikes = well_totals.loc[well_totals["spike_count"] > 0, "well"].tolist()

    if "Active" in well_metadata.columns:
        active_flags = well_metadata.loc[well_metadata["Active"] == True, "well"].tolist()
        active_wells = [well for well in active_by_spikes if well in active_flags]
        if active_wells:
            return active_wells

    return active_by_spikes


def save_summary(
    output_dir: Path,
    recording_metadata: dict[str, str],
    well_metadata: pd.DataFrame,
    spikes: pd.DataFrame,
    well_long: pd.DataFrame,
    electrode_long: pd.DataFrame,
) -> None:
    """Write a compact JSON summary of the recording-level CSV stage."""
    summary = {
        "recording_name": recording_metadata.get("Recording Name", output_dir.name),
        "description": recording_metadata.get("Description", ""),
        "spike_rows": int(len(spikes)),
        "duration_s": float(well_long["interval_end_s"].max()) if not well_long.empty else 0.0,
        "active_wells_by_spikes": (
            well_long.groupby("well")["spike_count"]
            .sum()
            .sort_values(ascending=False)
            .loc[lambda s: s > 0]
            .to_dict()
        ),
        "top_electrodes": (
            electrode_long.groupby("electrode")["spike_count"]
            .sum()
            .sort_values(ascending=False)
            .head(20)
            .to_dict()
        ),
    }

    if not well_metadata.empty:
        summary["well_annotations"] = (
            well_metadata.astype(object).fillna("").to_dict(orient="records")
        )

    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)


def plot_well_spikes(
    well_long: pd.DataFrame, active_wells: list[str], output_path: Path
) -> None:
    """Render well-level spike activity as a heatmap plus line overview."""
    if not active_wells:
        return

    pivot = (
        well_long[well_long["well"].isin(active_wells)]
        .pivot(index="interval_start_s", columns="well", values="spike_count")
        .fillna(0)
    )
    pivot = pivot.loc[:, active_wells]

    fig, axes = plt.subplots(
        2,
        1,
        figsize=(14, 8),
        gridspec_kw={"height_ratios": [1.2, 1]},
        constrained_layout=True,
    )

    sns.heatmap(
        pivot.T,
        ax=axes[0],
        cmap="mako",
        cbar_kws={"label": "spikes / second"},
    )
    axes[0].set_title("Spike Counts Over Time by Well")
    axes[0].set_xlabel("interval start (s)")
    axes[0].set_ylabel("well")

    for well in active_wells:
        axes[1].plot(
            pivot.index,
            pivot[well],
            linewidth=1.2,
            label=well,
        )
    axes[1].set_title("Active Wells")
    axes[1].set_xlabel("time (s)")
    axes[1].set_ylabel("spikes / second")
    axes[1].legend(ncol=min(4, len(active_wells)), fontsize=8)

    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_top_channels_by_well(
    electrode_long: pd.DataFrame,
    active_wells: list[str],
    output_path: Path,
    max_wells: int,
    top_channels_per_well: int,
) -> None:
    """Plot the most active channels inside each selected well."""
    wells_to_plot = active_wells[:max_wells]
    if not wells_to_plot:
        return

    ncols = 2
    nrows = math.ceil(len(wells_to_plot) / ncols)
    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(14, 4 * nrows),
        constrained_layout=True,
        squeeze=False,
    )

    for axis, well in zip(axes.ravel(), wells_to_plot):
        well_df = electrode_long.loc[electrode_long["well"] == well].copy()
        top_channels = (
            well_df.groupby("electrode")["spike_count"]
            .sum()
            .sort_values(ascending=False)
            .head(top_channels_per_well)
            .index
            .tolist()
        )

        plot_df = well_df.loc[well_df["electrode"].isin(top_channels)]
        if plot_df.empty:
            axis.set_visible(False)
            continue

        sns.lineplot(
            data=plot_df,
            x="interval_start_s",
            y="spike_count",
            hue="electrode",
            ax=axis,
            linewidth=1.1,
        )
        axis.set_title(f"{well}: top channels")
        axis.set_xlabel("time (s)")
        axis.set_ylabel("spikes / second")
        axis.legend(fontsize=8)

    for axis in axes.ravel()[len(wells_to_plot) :]:
        axis.set_visible(False)

    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_environment(env: pd.DataFrame, output_path: Path) -> None:
    """Render temperature and CO2 traces when environmental data exists."""
    if env.empty:
        return

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), constrained_layout=True)

    if {"time_s", "plate_temperature_c", "heater_setpoint_c"}.issubset(env.columns):
        axes[0].plot(env["time_s"], env["plate_temperature_c"], label="plate temp")
        axes[0].plot(env["time_s"], env["heater_setpoint_c"], label="setpoint")
        axes[0].set_ylabel("deg C")
        axes[0].set_title("Temperature")
        axes[0].legend()

    if {"time_s", "co2_concentration_pct", "co2_setpoint_pct"}.issubset(env.columns):
        axes[1].plot(env["time_s"], env["co2_concentration_pct"], label="CO2 measured")
        axes[1].plot(env["time_s"], env["co2_setpoint_pct"], label="CO2 setpoint")
        axes[1].set_ylabel("% CO2")
        axes[1].set_xlabel("time (s)")
        axes[1].set_title("CO2")
        axes[1].legend()

    fig.savefig(output_path, dpi=180)
    plt.close(fig)
