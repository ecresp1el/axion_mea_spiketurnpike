"""Metadata-locked Axion plate profiles for downstream pipeline config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PlateProfile:
    family: str
    plate_map: Path
    electrode_geometry: Path
    params_template: Path
    n_chan_bin: int
    well_dimensions: str
    electrode_dimensions: str
    num_channels: str
    dmin: int
    dminx: int
    max_channel_distance: int
    x_centers: int
    nearest_templates: int
    nearest_chans: int
    whitening_range: int
    min_template_size: int = 50
    nblocks: int = 0
    nt: int = 31
    nt0min: str = ""
    do_car: str = "true"
    invert_sign: str = "false"
    th_universal: int = 9
    th_learned: int = 8
    th_single_ch: int = 6

    def env_values(self) -> dict[str, str]:
        return {
            "PLATE_FAMILY": self.family,
            "PLATE_MAP": str(self.plate_map.resolve()),
            "ELECTRODE_GEOMETRY": str(self.electrode_geometry.resolve()),
            "PARAMS_TEMPLATE": str(self.params_template.resolve()),
            "N_CHAN_BIN": str(self.n_chan_bin),
            "NBLOCKS": str(self.nblocks),
            "NT": str(self.nt),
            "NT0MIN": self.nt0min,
            "DMIN": str(self.dmin),
            "DMINX": str(self.dminx),
            "MAX_CHANNEL_DISTANCE": str(self.max_channel_distance),
            "X_CENTERS": str(self.x_centers),
            "NEAREST_TEMPLATES": str(self.nearest_templates),
            "NEAREST_CHANS": str(self.nearest_chans),
            "MIN_TEMPLATE_SIZE": str(self.min_template_size),
            "WHITENING_RANGE": str(self.whitening_range),
            "DO_CAR": self.do_car,
            "INVERT_SIGN": self.invert_sign,
            "TH_UNIVERSAL": str(self.th_universal),
            "TH_LEARNED": str(self.th_learned),
            "TH_SINGLE_CH": str(self.th_single_ch),
        }


LUMOS_48 = PlateProfile(
    family="lumos_48well",
    plate_map=REPO_ROOT / "metadata" / "plate_maps" / "axion_48_well_opto_plate_map.csv",
    electrode_geometry=REPO_ROOT / "metadata" / "plate_maps" / "axion_per_well_4x4_electrode_geometry.csv",
    params_template=REPO_ROOT / "config" / "aind_axion_lumos_params.json",
    n_chan_bin=16,
    well_dimensions="[6 8]",
    electrode_dimensions="[6 8 4 4]",
    num_channels="768",
    dmin=350,
    dminx=350,
    max_channel_distance=400,
    x_centers=4,
    nearest_templates=16,
    nearest_chans=5,
    whitening_range=8,
)


CYTOVIEW_6 = PlateProfile(
    family="cytoview_6well",
    plate_map=REPO_ROOT / "metadata" / "plate_maps" / "axion_6_well_plate_map.csv",
    electrode_geometry=REPO_ROOT / "metadata" / "plate_maps" / "axion_per_well_8x8_electrode_geometry.csv",
    params_template=REPO_ROOT / "config" / "aind_axion_cytoview6_params.json",
    n_chan_bin=64,
    well_dimensions="[2 3]",
    electrode_dimensions="[2 3 8 8]",
    num_channels="384",
    dmin=300,
    dminx=300,
    max_channel_distance=350,
    x_centers=8,
    nearest_templates=64,
    nearest_chans=5,
    whitening_range=16,
)


def _clean(value: object) -> str:
    return str(value or "").strip()


def profile_from_metadata(metadata: dict[str, object]) -> PlateProfile:
    """Return the supported profile dictated by raw metadata."""
    plate_type = _clean(
        metadata.get("plate_type_name") or metadata.get("raw_plate_type_name")
    )
    well_dimensions = _clean(metadata.get("well_dimensions"))
    electrode_dimensions = _clean(metadata.get("electrode_dimensions"))
    num_channels = _clean(metadata.get("num_channels"))

    if (
        "SixWell" in plate_type
        or (
            well_dimensions == CYTOVIEW_6.well_dimensions
            and electrode_dimensions == CYTOVIEW_6.electrode_dimensions
            and num_channels == CYTOVIEW_6.num_channels
        )
    ):
        return CYTOVIEW_6

    if (
        "FortyEightWell" in plate_type
        or (
            well_dimensions == LUMOS_48.well_dimensions
            and electrode_dimensions == LUMOS_48.electrode_dimensions
            and num_channels == LUMOS_48.num_channels
        )
    ):
        return LUMOS_48

    raise ValueError(
        "Unsupported or unknown Axion plate metadata: "
        f"plate_type_name={plate_type!r}, "
        f"well_dimensions={well_dimensions!r}, "
        f"electrode_dimensions={electrode_dimensions!r}, "
        f"num_channels={num_channels!r}."
    )

