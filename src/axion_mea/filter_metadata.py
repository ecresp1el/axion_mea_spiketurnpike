"""Parse Axion filter metadata from raw dataset descriptions."""

from __future__ import annotations

import json
import re
from typing import Mapping


SECTION_KEYS = {
    "digital_filter_settings": "Digital Filter Settings",
    "broadband_processor_high_frequency_digital_filter": (
        "Broadband Processor High Frequency Digital Filter"
    ),
    "broadband_processor_low_frequency_median_filter": (
        "Broadband Processor Low Frequency Median Filter"
    ),
}

SETTING_KEYS = {
    "High Pass Filter": "high_pass_filter",
    "High Pass Poles": "high_pass_poles",
    "High Pass Cutoff Freq.": "high_pass_cutoff_freq",
    "Low Pass Filter": "low_pass_filter",
    "Low Pass Poles": "low_pass_poles",
    "Low Pass Cutoff Freq.": "low_pass_cutoff_freq",
}

BASE_FILTER_METADATA_COLUMNS = [
    "filter_metadata_signature",
    "acquisition_analog_mode_setting",
    "acquisition_digital_high_pass_filter",
    "acquisition_digital_low_pass_filter",
    "derived_high_pass_filter",
    "derived_low_pass_filter",
    "derived_high_pass_cutoff_freqs",
    "derived_low_pass_cutoff_freqs",
    "filter_block_count",
    "filter_block_names",
    "filter_blocks_json",
]

SECTION_FILTER_METADATA_COLUMNS = [
    f"{section}_{field}"
    for section in SECTION_KEYS
    for field in (
        "high_pass_filter",
        "high_pass_poles",
        "high_pass_cutoff_freq",
        "low_pass_filter",
        "low_pass_poles",
        "low_pass_cutoff_freq",
    )
]

FILTER_METADATA_COLUMNS = BASE_FILTER_METADATA_COLUMNS + SECTION_FILTER_METADATA_COLUMNS
FILTER_METADATA_VALUE_COUNT_FIELDS = [
    field for field in FILTER_METADATA_COLUMNS if field != "filter_blocks_json"
]


def _clean(value: object | None) -> str:
    return str(value or "").strip()


def _join_values(values: list[str]) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        cleaned = _clean(value)
        if cleaned and cleaned not in seen:
            out.append(cleaned)
            seen.add(cleaned)
    return ";".join(out)


def _description_pairs(description: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw_line in re.split(r"[\r\n]+", description or ""):
        line = raw_line.strip()
        if not line:
            continue
        if "," in line:
            key, value = line.split(",", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            key, value = line, ""
        pairs.append((key.strip().rstrip(":"), value.strip()))
    return pairs


def dataset_description_setting(row: Mapping[str, object] | None, setting_name: str) -> str:
    """Return the first matching setting value from an Axion dataset description."""
    if not row:
        return ""
    for key, value in _description_pairs(_clean(row.get("dataset_description"))):
        if key.lower() == setting_name.lower():
            return value
    return ""


def _filter_value(value: str) -> str:
    return value if value else "<blank>"


def parse_axion_filter_metadata(row: Mapping[str, object] | None) -> dict[str, str]:
    """Return structured Axion acquisition and derived filter metadata fields.

    Axion stores the important numeric cutoff/pole settings in multiline
    ``dataset_description`` text. This parser preserves each named filter block
    instead of collapsing all derived filters into the first repeated setting.
    """
    source = row or {}
    pairs = _description_pairs(_clean(source.get("dataset_description")))

    values: dict[str, str] = {field: _clean(source.get(field)) for field in FILTER_METADATA_COLUMNS}
    values["acquisition_analog_mode_setting"] = (
        dataset_description_setting(source, "Analog Mode Setting")
        or _clean(source.get("metadata_analog_mode"))
        or values["acquisition_analog_mode_setting"]
    )
    values["acquisition_digital_high_pass_filter"] = (
        dataset_description_setting(source, "Digital High Pass Filter")
        or values["acquisition_digital_high_pass_filter"]
    )
    values["acquisition_digital_low_pass_filter"] = (
        dataset_description_setting(source, "Digital Low Pass Filter")
        or values["acquisition_digital_low_pass_filter"]
    )

    section_lookup = {label.lower(): key for key, label in SECTION_KEYS.items()}
    setting_lookup = {label.lower(): field for label, field in SETTING_KEYS.items()}
    blocks: dict[str, dict[str, str]] = {}
    current_section = ""
    for key, value in pairs:
        key_lc = key.lower()
        if key_lc in section_lookup:
            current_section = section_lookup[key_lc]
            blocks.setdefault(current_section, {})
            continue
        if current_section and key_lc in setting_lookup:
            blocks.setdefault(current_section, {})[setting_lookup[key_lc]] = value

    block_rows: list[dict[str, str]] = []
    for section_key, section_label in SECTION_KEYS.items():
        block = blocks.get(section_key, {})
        if not block:
            continue
        block_row = {"block_name": section_label}
        block_row.update({field: _clean(block.get(field)) for field in SETTING_KEYS.values()})
        block_rows.append(block_row)
        for field in SETTING_KEYS.values():
            values[f"{section_key}_{field}"] = block_row[field]

    values["filter_block_count"] = str(len(block_rows))
    values["filter_block_names"] = ";".join(row["block_name"] for row in block_rows)
    values["filter_blocks_json"] = (
        json.dumps(block_rows, separators=(",", ":"), sort_keys=True) if block_rows else ""
    )
    values["derived_high_pass_filter"] = _join_values(
        [row.get("high_pass_filter", "") for row in block_rows]
    ) or values["derived_high_pass_filter"]
    values["derived_low_pass_filter"] = _join_values(
        [row.get("low_pass_filter", "") for row in block_rows]
    ) or values["derived_low_pass_filter"]
    values["derived_high_pass_cutoff_freqs"] = _join_values(
        [row.get("high_pass_cutoff_freq", "") for row in block_rows]
    ) or values["derived_high_pass_cutoff_freqs"]
    values["derived_low_pass_cutoff_freqs"] = _join_values(
        [row.get("low_pass_cutoff_freq", "") for row in block_rows]
    ) or values["derived_low_pass_cutoff_freqs"]

    signature_parts = [
        f"analog={_filter_value(values['acquisition_analog_mode_setting'])}",
        f"acquisition_hp={_filter_value(values['acquisition_digital_high_pass_filter'])}",
        f"acquisition_lp={_filter_value(values['acquisition_digital_low_pass_filter'])}",
        f"filter_blocks={_filter_value(values['filter_block_names'])}",
        f"derived_hp={_filter_value(values['derived_high_pass_filter'])}",
        f"derived_hp_cutoff={_filter_value(values['derived_high_pass_cutoff_freqs'])}",
        f"derived_lp={_filter_value(values['derived_low_pass_filter'])}",
        f"derived_lp_cutoff={_filter_value(values['derived_low_pass_cutoff_freqs'])}",
    ]
    values["filter_metadata_signature"] = " | ".join(signature_parts)
    return values
