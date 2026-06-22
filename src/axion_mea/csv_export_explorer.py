#!/usr/bin/env python3

from __future__ import annotations

import argparse
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Quick Axion Maestro CSV exploration."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Directory containing Axion CSV exports.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Base directory for outputs.",
    )
    parser.add_argument(
        "--top-channels-per-well",
        type=int,
        default=4,
        help="Number of top channels to plot for each active well.",
    )
    parser.add_argument(
        "--max-wells",
        type=int,
        default=8,
        help="Maximum number of active wells to include in channel plots.",
    )
    return parser.parse_args()


def find_first_file(data_dir: Path, suffix: str) -> Path | None:
    matches = sorted(
        path
        for path in data_dir.glob(f"*{suffix}")
        if not path.name.startswith("._")
    )
    return matches[0] if matches else None


def sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return cleaned.strip("_") or "recording"


def read_spike_list(path: Path) -> tuple[pd.DataFrame, dict[str, str], pd.DataFrame]:
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


def main() -> None:
    args = parse_args()
    sns.set_theme(style="whitegrid")

    data_dir = args.data_dir.expanduser().resolve()
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory does not exist: {data_dir}")

    spike_list_path = find_first_file(data_dir, "_spike_list.csv")
    spike_counts_path = find_first_file(data_dir, "_spike_counts.csv")
    env_path = find_first_file(data_dir, "_environmental_data.csv")

    if spike_list_path is None or spike_counts_path is None:
        raise FileNotFoundError(
            "Expected both *_spike_list.csv and *_spike_counts.csv in the data directory."
        )

    spikes, recording_metadata, well_metadata = read_spike_list(spike_list_path)
    well_long, electrode_long = read_spike_counts(spike_counts_path)
    env = read_environment(env_path) if env_path is not None else pd.DataFrame()

    recording_name = recording_metadata.get("Recording Name", spike_list_path.stem)
    output_dir = args.output_dir / sanitize_name(recording_name)
    output_dir.mkdir(parents=True, exist_ok=True)

    spikes.to_csv(output_dir / "spike_list_clean.csv", index=False)
    well_long.to_csv(output_dir / "well_counts_long.csv", index=False)
    electrode_long.to_csv(output_dir / "electrode_counts_long.csv", index=False)
    well_metadata.to_csv(output_dir / "well_metadata.csv", index=False)
    if not env.empty:
        env.to_csv(output_dir / "environment_clean.csv", index=False)

    with (output_dir / "recording_metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(recording_metadata, handle, indent=2)

    active_wells = pick_active_wells(well_long, well_metadata)

    save_summary(
        output_dir,
        recording_metadata,
        well_metadata,
        spikes,
        well_long,
        electrode_long,
    )
    plot_well_spikes(well_long, active_wells, output_dir / "well_spikes_over_time.png")
    plot_top_channels_by_well(
        electrode_long,
        active_wells,
        output_dir / "top_channels_by_well.png",
        max_wells=args.max_wells,
        top_channels_per_well=args.top_channels_per_well,
    )
    if not env.empty:
        plot_environment(env, output_dir / "environment_over_time.png")

    treatments = []
    if "Treatment" in well_metadata.columns:
        treatments = sorted(
            {
                value.strip()
                for value in well_metadata["Treatment"].dropna().astype(str)
                if value.strip()
            }
        )

    print(f"Data directory: {data_dir}")
    print(f"Recording name: {recording_name}")
    print(f"Output directory: {output_dir.resolve()}")
    print(f"Spike rows parsed: {len(spikes)}")
    print(f"Duration from spike counts: {well_long['interval_end_s'].max():.0f} s")
    print(f"Active wells: {', '.join(active_wells[:12])}")
    if treatments:
        print(f"Well treatments found: {', '.join(treatments)}")
    print("Note: explicit optogenetic stimulation timestamps were not found in the CSV exports.")


if __name__ == "__main__":
    main()
