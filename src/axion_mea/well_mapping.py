"""Canonical per-well Axion channel mapping for downstream ingestion."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REQUIRED_CHANNEL_MAPPING_COLUMNS = (
    "channel_index_zero_based",
    "well",
    "channel_in_well",
    "electrode_row",
    "electrode_col",
    "x_um",
    "y_um",
    "axion_well_row",
    "axion_well_col",
    "axion_electrode_col",
    "axion_electrode_row",
    "channel_achk",
    "channel_index",
)


@dataclass(frozen=True)
class AxionWellMapping:
    """Single source of truth for one exported Axion well's channel mapping.

    The mapping table order is the binary channel order. All ingestion-specific
    representations, including NWB electrode rows, Kilosort probes, and
    ProbeInterface JSON, must be derived from this object.
    """

    table: pd.DataFrame
    source_csv: Path | None = None

    @classmethod
    def from_csv(cls, path: Path) -> "AxionWellMapping":
        resolved = path.expanduser().resolve()
        return cls.from_dataframe(pd.read_csv(resolved), source_csv=resolved)

    @classmethod
    def from_dataframe(
        cls,
        table: pd.DataFrame,
        *,
        source_csv: Path | None = None,
    ) -> "AxionWellMapping":
        missing = [col for col in REQUIRED_CHANNEL_MAPPING_COLUMNS if col not in table.columns]
        if missing:
            raise ValueError(f"Channel mapping is missing required columns: {', '.join(missing)}")
        mapping = table.copy()
        mapping["channel_index_zero_based"] = mapping["channel_index_zero_based"].astype(int)
        mapping = mapping.sort_values("channel_index_zero_based").reset_index(drop=True)
        expected = np.arange(len(mapping), dtype=int)
        actual = mapping["channel_index_zero_based"].to_numpy(dtype=int)
        if not np.array_equal(actual, expected):
            raise ValueError(
                "channel_index_zero_based must be contiguous binary order "
                f"0..{len(mapping) - 1}; got {actual.tolist()}"
            )
        for col in [
            "electrode_row",
            "electrode_col",
            "axion_well_row",
            "axion_well_col",
            "axion_electrode_col",
            "axion_electrode_row",
            "channel_achk",
            "channel_index",
        ]:
            mapping[col] = mapping[col].astype(int)
        for col in ["x_um", "y_um"]:
            mapping[col] = mapping[col].astype(float)
        mapping["well"] = mapping["well"].astype(str)
        mapping["channel_in_well"] = mapping["channel_in_well"].astype(str)
        return cls(table=mapping, source_csv=source_csv)

    @property
    def well(self) -> str:
        wells = sorted(set(self.table["well"].astype(str)))
        if len(wells) != 1:
            raise ValueError(f"Expected exactly one well in mapping; found {wells}")
        return wells[0]

    @property
    def n_channels(self) -> int:
        return len(self.table)

    def dataframe(self) -> pd.DataFrame:
        """Return the canonical table with ingestion coordinate aliases."""
        table = self.table.copy()
        table["rel_x"] = table["x_um"]
        table["rel_y"] = table["y_um"]
        table["rel_z"] = 0.0
        table["nwb_x"] = table["x_um"]
        table["nwb_y"] = table["y_um"]
        table["nwb_z"] = 0.0
        return table

    def to_kilosort_probe(self) -> dict[str, Any]:
        """Return a Kilosort probe dictionary in binary channel order."""
        table = self.dataframe()
        kcoords = (
            table["kcoords"].astype(int).to_numpy()
            if "kcoords" in table.columns
            else np.zeros(self.n_channels, dtype=int)
        )
        return {
            "chanMap": np.arange(self.n_channels, dtype=np.int64),
            "xc": table["x_um"].to_numpy(dtype=np.float64),
            "yc": table["y_um"].to_numpy(dtype=np.float64),
            "kcoords": kcoords.astype(np.int64),
            "n_chan": self.n_channels,
        }

    def to_kilosort_probe_jsonable(self) -> dict[str, Any]:
        probe = self.to_kilosort_probe()
        return {
            key: value.tolist() if isinstance(value, np.ndarray) else value
            for key, value in probe.items()
        }

    def to_probeinterface_json(self) -> dict[str, Any]:
        """Return ProbeInterface JSON derived from the canonical mapping."""
        table = self.dataframe()
        return {
            "specification": "probeinterface",
            "version": "0.3.2",
            "probes": [
                {
                    "ndim": 2,
                    "si_units": "um",
                    "annotations": {
                        "name": "Axion 4x4 well",
                        "manufacturer": "Axion BioSystems",
                        "well": self.well,
                    },
                    "contact_annotations": {},
                    "contact_positions": table[["x_um", "y_um"]].to_numpy(dtype=float).tolist(),
                    "contact_plane_axes": [
                        [[1.0, 0.0], [0.0, 1.0]] for _ in range(self.n_channels)
                    ],
                    "contact_shapes": ["circle"] * self.n_channels,
                    "contact_shape_params": [{"radius": 7.5} for _ in range(self.n_channels)],
                    "device_channel_indices": np.arange(self.n_channels, dtype=int).tolist(),
                    "contact_ids": table["channel_in_well"].astype(str).tolist(),
                }
            ],
        }

    def write_probeinterface_json(self, path: Path) -> Path:
        resolved = path.expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(json.dumps(self.to_probeinterface_json(), indent=4), encoding="utf-8")
        return resolved

    def ingestion_manifest(self) -> dict[str, Any]:
        """Return a compact manifest describing all derived ingestion views."""
        return {
            "analysis_kind": "axion_well_channel_mapping",
            "source_csv": str(self.source_csv) if self.source_csv else None,
            "well": self.well,
            "n_channels": self.n_channels,
            "binary_order_column": "channel_index_zero_based",
            "coordinate_units": "um",
            "coordinate_columns": {
                "canonical": ["x_um", "y_um"],
                "nwb": ["x", "y", "z", "rel_x", "rel_y", "rel_z"],
                "probeinterface": ["contact_positions"],
                "kilosort": ["xc", "yc", "kcoords"],
            },
            "table": self.dataframe().to_dict(orient="records"),
        }
