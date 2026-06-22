from __future__ import annotations
"""Low-level parser for Axion `.raw` stimulation tags.

This module is intentionally narrow: it does not attempt to decode the full raw
recording format. Instead, it extracts only the tag structures required by this
repository:

- stimulation waveform tags,
- stimulation channel-group tags,
- stimulation LED-group tags, and
- stimulation event tags.

Those tags are enough to recover stimulation timestamps, stimulated wells, and
the XML micro-operation program used later to reconstruct the intended opto
waveform shown in the report figures.
"""

import csv
import json
import struct
import uuid
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import BinaryIO
import xml.etree.ElementTree as ET


class EntryRecordType(IntEnum):
    """Primary and subheader record types observed in Axion raw files."""

    TERMINATE = 0x00
    NOTES_ARRAY = 0x01
    CHANNEL_ARRAY = 0x02
    BLOCK_VECTOR_HEADER = 0x03
    BLOCK_VECTOR_DATA = 0x04
    BLOCK_VECTOR_HEADER_EXTENSION = 0x05
    TAG = 0x06
    COMBINED_BLOCK_VECTOR_HEADER = 0x07
    SKIP = 0xFF


class TagType(IntEnum):
    """Known Axion tag identifiers relevant to this parser."""

    DELETED = 0
    WELL_TREATMENT = 1
    USER_ANNOTATION = 2
    SYSTEM_ANNOTATION = 3
    DATA_LOSS_EVENT = 4
    STIMULATION_EVENT = 5
    STIMULATION_CHANNEL_GROUP = 6
    STIMULATION_WAVEFORM = 7
    CALIBRATION_TAG = 8
    STIMULATION_LED_GROUP = 9
    DOSE_EVENT = 10
    STRING_DICTIONARY_KEY_PAIR = 11
    LEAP_INDUCTION_EVENT = 12
    VIABILITY_IMPEDANCE_EVENT = 13


@dataclass(frozen=True)
class EntryRecord:
    """Decoded primary-header or subheader entry descriptor."""

    record_type: EntryRecordType
    length: int

    @classmethod
    def from_uint64(cls, value: int) -> "EntryRecord":
        """Decode an Axion packed entry-record word."""
        record_id = (value >> 56) & 0xFF
        high = (value >> 32) & 0x00FF_FFFF
        low = value & 0xFFFF_FFFF
        is_infinite = high == 0x00FF_FFFF and low == 0xFFFF_FFFF
        length = -1 if is_infinite else (high << 32) | low

        try:
            record_type = EntryRecordType(record_id)
        except ValueError:
            record_type = EntryRecordType.SKIP

        return cls(record_type=record_type, length=length)


@dataclass(frozen=True)
class AxionDateTime:
    """Axion timestamp structure embedded inside tag metadata."""

    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int
    millisecond: int

    @classmethod
    def read(cls, reader: "BinaryReader") -> "AxionDateTime":
        """Read one Axion datetime block from the binary stream."""
        return cls(
            year=reader.read_u16(),
            month=reader.read_u16(),
            day=reader.read_u16(),
            hour=reader.read_u16(),
            minute=reader.read_u16(),
            second=reader.read_u16(),
            millisecond=reader.read_u16(),
        )


@dataclass(frozen=True)
class TagEntry:
    """Minimal metadata for one Axion tag revision."""

    start: int
    length: int
    tag_type: TagType
    creation_time: AxionDateTime
    tag_guid: str
    revision_number: int

    BASE_SIZE = 2 + 14 + 16 + 4

    @classmethod
    def read(cls, reader: "BinaryReader", entry_record: EntryRecord) -> "TagEntry":
        """Read the generic tag header and skip any unparsed payload bytes."""
        start = reader.tell()
        type_code = reader.read_u16()
        try:
            tag_type = TagType(type_code)
        except ValueError:
            tag_type = TagType.DELETED

        creation_time = AxionDateTime.read(reader)
        tag_guid = reader.read_guid()
        revision_number = reader.read_u32()

        remaining = entry_record.length - cls.BASE_SIZE
        if remaining > 0:
            reader.seek_relative(remaining)

        return cls(
            start=start,
            length=entry_record.length,
            tag_type=tag_type,
            creation_time=creation_time,
            tag_guid=tag_guid,
            revision_number=revision_number,
        )


@dataclass(frozen=True)
class ChannelMapping:
    """One electrode mapping inside a stimulation channel group."""

    well_column: int
    well_row: int
    electrode_column: int
    electrode_row: int
    channel_achk: int
    channel_index: int
    aux_data: int

    @classmethod
    def read(cls, reader: "BinaryReader") -> "ChannelMapping":
        """Read one channel mapping structure."""
        return cls(
            well_column=reader.read_u8(),
            well_row=reader.read_u8(),
            electrode_column=reader.read_u8(),
            electrode_row=reader.read_u8(),
            channel_achk=reader.read_u8(),
            channel_index=reader.read_u8(),
            aux_data=reader.read_u16(),
        )


@dataclass(frozen=True)
class LedPosition:
    """One LED position inside a stimulation LED group."""

    well_column: int
    well_row: int
    led_color: int

    @classmethod
    def read(cls, reader: "BinaryReader") -> "LedPosition":
        """Read one LED position structure."""
        return cls(
            well_column=reader.read_u8(),
            well_row=reader.read_u8(),
            led_color=reader.read_u16(),
        )


@dataclass(frozen=True)
class StimulationEventData:
    """Event-program block referenced by stimulation events."""

    event_data_id: int
    stimulation_duration_s: float
    artifact_elimination_duration_s: float
    channel_array_ids: list[int]
    description: str


@dataclass(frozen=True)
class StimulationWaveformTag:
    """Waveform-program tag containing block metadata and XML micro-ops."""

    tag_guid: str
    blocks_by_id: dict[int, StimulationEventData]
    micro_ops: str

    @classmethod
    def read(cls, reader: "BinaryReader", tag_entry: TagEntry) -> "StimulationWaveformTag":
        """Read one stimulation waveform tag from the raw file."""
        reader.seek_absolute(tag_entry.start + TagEntry.BASE_SIZE)
        version = reader.read_u16()
        if version != 0:
            raise ValueError(f"Unsupported StimulationWaveform version: {version}")

        block_count = reader.read_u16()
        blocks_by_id: dict[int, StimulationEventData] = {}
        for _ in range(block_count):
            event_data_id = reader.read_u16()
            reader.read_u16()  # block type, unused in the MATLAB loader
            stim_duration = reader.read_f64()
            artifact_duration = reader.read_f64()
            channel_array_ids = [value for value in (reader.read_u16(), reader.read_u16()) if value != 0]
            description = reader.read_utf8()
            blocks_by_id[event_data_id] = StimulationEventData(
                event_data_id=event_data_id,
                stimulation_duration_s=stim_duration,
                artifact_elimination_duration_s=artifact_duration,
                channel_array_ids=channel_array_ids,
                description=description,
            )

        micro_ops = reader.read_utf8()
        return cls(tag_guid=tag_entry.tag_guid, blocks_by_id=blocks_by_id, micro_ops=micro_ops)


@dataclass(frozen=True)
class StimulationChannelsTag:
    """Electrode stimulation group definitions referenced by events."""

    tag_guid: str
    groups_by_id: dict[int, list[ChannelMapping]]

    @classmethod
    def read(cls, reader: "BinaryReader", tag_entry: TagEntry) -> "StimulationChannelsTag":
        """Read one stimulation-channel-group tag."""
        reader.seek_absolute(tag_entry.start + TagEntry.BASE_SIZE)
        version = reader.read_u16()
        if version != 0:
            raise ValueError(f"Unsupported StimulationChannels version: {version}")

        reader.read_u16()  # reserved
        tag_end = tag_entry.start + tag_entry.length
        groups_by_id: dict[int, list[ChannelMapping]] = {}

        while (tag_end - reader.tell()) >= 20:
            group_id = reader.read_u32()
            reader.read_u32()  # plate type
            num_channels = reader.read_u32()
            groups_by_id[group_id] = [ChannelMapping.read(reader) for _ in range(num_channels)]

        return cls(tag_guid=tag_entry.tag_guid, groups_by_id=groups_by_id)


@dataclass(frozen=True)
class StimulationLedsTag:
    """Optical stimulation group definitions referenced by events."""

    tag_guid: str
    groups_by_id: dict[int, list[LedPosition]]

    @classmethod
    def read(cls, reader: "BinaryReader", tag_entry: TagEntry) -> "StimulationLedsTag":
        """Read one stimulation-LED-group tag."""
        reader.seek_absolute(tag_entry.start + TagEntry.BASE_SIZE)
        version = reader.read_u16()
        if version != 0:
            raise ValueError(f"Unsupported StimulationLeds version: {version}")

        expected_groups = reader.read_u16()
        tag_end = tag_entry.start + tag_entry.length
        groups_by_id: dict[int, list[LedPosition]] = {}

        while (tag_end - reader.tell()) >= 20:
            group_id = reader.read_u32()
            reader.read_u32()  # plate type
            num_leds = reader.read_u32()
            groups_by_id[group_id] = [LedPosition.read(reader) for _ in range(num_leds)]

        if len(groups_by_id) != expected_groups:
            raise ValueError(
                f"LED group count mismatch: expected {expected_groups}, got {len(groups_by_id)}"
            )

        return cls(tag_guid=tag_entry.tag_guid, groups_by_id=groups_by_id)


@dataclass(frozen=True)
class StimulationEventTag:
    """One stimulation event linking time, waveform program, and target group."""

    tag_guid: str
    event_time_s: float
    event_time_sample: int
    event_duration_samples: int
    waveform_tag_guid: str
    channels_tag_guid: str
    event_data_id: int
    sequence_number: int

    @classmethod
    def read(cls, reader: "BinaryReader", tag_entry: TagEntry) -> "StimulationEventTag":
        """Read one stimulation event tag."""
        reader.seek_absolute(tag_entry.start + TagEntry.BASE_SIZE)
        sampling_frequency = reader.read_f64()
        event_time_sample = reader.read_i64()
        event_duration_samples = reader.read_i64()
        version = reader.read_u16()
        if version != 0:
            raise ValueError(f"Unsupported StimulationEvent version: {version}")

        reader.read_u16()  # reserved
        waveform_tag_guid = reader.read_guid()
        channels_tag_guid = reader.read_guid()
        event_data_id = reader.read_u16()
        sequence_number = reader.read_u16()

        return cls(
            tag_guid=tag_entry.tag_guid,
            event_time_s=(event_time_sample / sampling_frequency),
            event_time_sample=event_time_sample,
            event_duration_samples=event_duration_samples,
            waveform_tag_guid=waveform_tag_guid,
            channels_tag_guid=channels_tag_guid,
            event_data_id=event_data_id,
            sequence_number=sequence_number,
        )


@dataclass(frozen=True)
class StimulationEventSummary:
    """Normalized stimulation event row exported to CSV and JSON."""

    event_time_s: float
    event_time_sample: int
    sequence_number: int
    source_kind: str
    stimulation_duration_s: float | None
    artifact_elimination_duration_s: float | None
    event_description: str
    waveform_tag_guid: str
    channels_tag_guid: str
    event_data_id: int
    stimulated_wells: list[str] = field(default_factory=list)
    led_positions: list[dict[str, int]] = field(default_factory=list)
    channel_mappings: list[dict[str, int]] = field(default_factory=list)


@dataclass(frozen=True)
class OpticalOnInterval:
    """One optical-on interval reconstructed from the micro-operation XML."""

    start_ms: float
    end_ms: float
    intensity: float


class BinaryReader:
    """Small helper around a binary file handle using Axion's little-endian layout."""

    def __init__(self, handle: BinaryIO) -> None:
        """Wrap an already-open binary handle."""
        self._handle = handle

    def tell(self) -> int:
        """Return the current stream offset."""
        return self._handle.tell()

    def seek_absolute(self, offset: int) -> None:
        """Seek to an absolute byte offset."""
        self._handle.seek(offset)

    def seek_relative(self, offset: int) -> None:
        """Seek relative to the current stream position."""
        self._handle.seek(offset, 1)

    def read_exact(self, size: int) -> bytes:
        """Read exactly `size` bytes or raise `EOFError`."""
        data = self._handle.read(size)
        if len(data) != size:
            raise EOFError(f"Expected {size} bytes, got {len(data)}")
        return data

    def read_u8(self) -> int:
        """Read one unsigned byte."""
        return struct.unpack("<B", self.read_exact(1))[0]

    def read_u16(self) -> int:
        """Read one unsigned 16-bit integer."""
        return struct.unpack("<H", self.read_exact(2))[0]

    def read_u32(self) -> int:
        """Read one unsigned 32-bit integer."""
        return struct.unpack("<I", self.read_exact(4))[0]

    def read_u64(self) -> int:
        """Read one unsigned 64-bit integer."""
        return struct.unpack("<Q", self.read_exact(8))[0]

    def read_i64(self) -> int:
        """Read one signed 64-bit integer."""
        return struct.unpack("<q", self.read_exact(8))[0]

    def read_f64(self) -> float:
        """Read one float64 value."""
        return struct.unpack("<d", self.read_exact(8))[0]

    def read_ascii(self, size: int) -> str:
        """Read a fixed-width ASCII field."""
        return self.read_exact(size).decode("ascii")

    def read_utf8(self) -> str:
        """Read Axion's length-prefixed UTF-8 string format."""
        byte_count = struct.unpack("<i", self.read_exact(4))[0]
        return self.read_exact(byte_count).decode("utf-8")

    def read_guid(self) -> str:
        """Read a little-endian GUID and format it as a standard UUID string."""
        return str(uuid.UUID(bytes_le=self.read_exact(16)))


class AxionStimFile:
    """Stim-tag focused view over one Axion raw file."""

    MAGIC_WORD = "AxionBio"
    PRIMARY_HEADER_MAX_ENTRIES = 123
    SUBHEADER_MAX_ENTRIES = 126

    def __init__(self, path: str | Path) -> None:
        """Initialize parser state for one raw file path."""
        self.path = Path(path).expanduser().resolve()
        self.primary_data_type: int | None = None
        self.header_version_major: int | None = None
        self.header_version_minor: int | None = None
        self.entries_start: int | None = None

        self._latest_tag_entries: dict[str, TagEntry] = {}
        self.waveform_tags: dict[str, StimulationWaveformTag] = {}
        self.channel_group_tags: dict[str, StimulationChannelsTag] = {}
        self.led_group_tags: dict[str, StimulationLedsTag] = {}
        self.stimulation_events: list[StimulationEventTag] = []

    def parse(self) -> None:
        """Read the raw file headers and cache the latest stimulation tags."""
        with self.path.open("rb") as handle:
            reader = BinaryReader(handle)
            entry_records = self._read_primary_header(reader)
            self._collect_latest_tag_entries(reader, entry_records)
            self._load_stimulation_tags(reader)

    def summarize_stimulation_events(self) -> list[StimulationEventSummary]:
        """Resolve raw stimulation tags into normalized event summaries."""
        summaries: list[StimulationEventSummary] = []
        for event in sorted(self.stimulation_events, key=lambda item: item.event_time_s):
            waveform = self.waveform_tags.get(event.waveform_tag_guid)
            event_data = waveform.blocks_by_id.get(event.event_data_id) if waveform else None

            source_kind = "unlinked"
            led_positions: list[dict[str, int]] = []
            channel_mappings: list[dict[str, int]] = []

            led_group = self.led_group_tags.get(event.channels_tag_guid)
            if led_group is not None:
                source_kind = "led"
                if event_data is not None:
                    for group_id in event_data.channel_array_ids:
                        for led in led_group.groups_by_id.get(group_id, []):
                            led_positions.append(asdict(led))
                else:
                    for led_group_rows in led_group.groups_by_id.values():
                        for led in led_group_rows:
                            led_positions.append(asdict(led))

            channel_group = self.channel_group_tags.get(event.channels_tag_guid)
            if channel_group is not None:
                source_kind = "electrode"
                if event_data is not None:
                    for group_id in event_data.channel_array_ids:
                        for mapping in channel_group.groups_by_id.get(group_id, []):
                            channel_mappings.append(asdict(mapping))

            stimulated_wells = sorted(
                {
                    self._well_name_from_position(led["well_row"], led["well_column"])
                    for led in led_positions
                }
            )

            summaries.append(
                StimulationEventSummary(
                    event_time_s=event.event_time_s,
                    event_time_sample=event.event_time_sample,
                    sequence_number=event.sequence_number,
                    source_kind=source_kind,
                    stimulation_duration_s=(
                        event_data.stimulation_duration_s if event_data is not None else None
                    ),
                    artifact_elimination_duration_s=(
                        event_data.artifact_elimination_duration_s
                        if event_data is not None
                        else None
                    ),
                    event_description=event_data.description if event_data is not None else "",
                    waveform_tag_guid=event.waveform_tag_guid,
                    channels_tag_guid=event.channels_tag_guid,
                    event_data_id=event.event_data_id,
                    stimulated_wells=stimulated_wells,
                    led_positions=led_positions,
                    channel_mappings=channel_mappings,
                )
            )
        return summaries

    def write_event_csv(self, output_path: str | Path) -> None:
        """Export normalized stimulation events as a flat CSV table."""
        summaries = self.summarize_stimulation_events()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "event_time_s",
                    "event_time_sample",
                    "sequence_number",
                    "source_kind",
                    "stimulation_duration_s",
                    "artifact_elimination_duration_s",
                    "event_description",
                    "event_data_id",
                    "waveform_tag_guid",
                    "channels_tag_guid",
                    "stimulated_wells",
                    "led_count",
                    "channel_mapping_count",
                ]
            )
            for summary in summaries:
                writer.writerow(
                    [
                        f"{summary.event_time_s:.9f}",
                        summary.event_time_sample,
                        summary.sequence_number,
                        summary.source_kind,
                        summary.stimulation_duration_s,
                        summary.artifact_elimination_duration_s,
                        summary.event_description,
                        summary.event_data_id,
                        summary.waveform_tag_guid,
                        summary.channels_tag_guid,
                        ";".join(summary.stimulated_wells),
                        len(summary.led_positions),
                        len(summary.channel_mappings),
                    ]
                )

    def write_event_json(self, output_path: str | Path) -> None:
        """Export normalized stimulation events as structured JSON."""
        summaries = self.summarize_stimulation_events()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump([asdict(summary) for summary in summaries], handle, indent=2)

    def opto_on_intervals_ms(self) -> list[OpticalOnInterval]:
        """Return the first waveform-program optical intervals found in the file."""
        intervals: list[OpticalOnInterval] = []
        for waveform_tag in self.waveform_tags.values():
            if waveform_tag.micro_ops.strip():
                intervals = self._parse_micro_ops_intervals(waveform_tag.micro_ops)
                if intervals:
                    return intervals
        return intervals

    def _read_primary_header(self, reader: BinaryReader) -> list[EntryRecord]:
        """Read the fixed-width primary header and its entry descriptors."""
        magic = reader.read_ascii(len(self.MAGIC_WORD))
        if magic != self.MAGIC_WORD:
            raise ValueError(f"Unsupported file header. Expected {self.MAGIC_WORD!r}, got {magic!r}")

        self.primary_data_type = reader.read_u16()
        self.header_version_major = reader.read_u16()
        self.header_version_minor = reader.read_u16()

        reader.read_u64()  # notes start
        reader.read_u32()  # notes length
        self.entries_start = struct.unpack("<q", reader.read_exact(8))[0]

        entry_records = [
            EntryRecord.from_uint64(reader.read_u64())
            for _ in range(self.PRIMARY_HEADER_MAX_ENTRIES)
        ]
        reader.seek_absolute(self.entries_start)
        return entry_records

    def _collect_latest_tag_entries(
        self, reader: BinaryReader, entry_records: list[EntryRecord]
    ) -> None:
        """Walk the header chain and keep only the latest revision of each tag GUID."""
        terminated = False
        current_entry_records = entry_records

        while not terminated:
            for entry_record in current_entry_records:
                if entry_record.record_type == EntryRecordType.TERMINATE:
                    terminated = True
                    break

                if entry_record.length < 0:
                    raise ValueError("Infinite-length entry records are not supported in this parser.")

                if entry_record.record_type == EntryRecordType.TAG:
                    tag_entry = TagEntry.read(reader, entry_record)
                    previous = self._latest_tag_entries.get(tag_entry.tag_guid)
                    if previous is None or tag_entry.revision_number > previous.revision_number:
                        self._latest_tag_entries[tag_entry.tag_guid] = tag_entry
                else:
                    reader.seek_relative(entry_record.length)

            if not terminated:
                magic = reader.read_ascii(len(self.MAGIC_WORD))
                if magic != self.MAGIC_WORD:
                    raise ValueError(f"Bad subheader magic word at offset {reader.tell() - len(self.MAGIC_WORD)}")

                current_entry_records = [
                    EntryRecord.from_uint64(reader.read_u64())
                    for _ in range(self.SUBHEADER_MAX_ENTRIES)
                ]
                reader.seek_relative(8)  # crc32 + reserved bytes

    def _load_stimulation_tags(self, reader: BinaryReader) -> None:
        """Decode cached tag entries into typed stimulation tag objects."""
        for tag_entry in self._latest_tag_entries.values():
            if tag_entry.tag_type == TagType.STIMULATION_WAVEFORM:
                waveform_tag = StimulationWaveformTag.read(reader, tag_entry)
                self.waveform_tags[waveform_tag.tag_guid] = waveform_tag
            elif tag_entry.tag_type == TagType.STIMULATION_CHANNEL_GROUP:
                channels_tag = StimulationChannelsTag.read(reader, tag_entry)
                self.channel_group_tags[channels_tag.tag_guid] = channels_tag
            elif tag_entry.tag_type == TagType.STIMULATION_LED_GROUP:
                leds_tag = StimulationLedsTag.read(reader, tag_entry)
                self.led_group_tags[leds_tag.tag_guid] = leds_tag
            elif tag_entry.tag_type == TagType.STIMULATION_EVENT:
                self.stimulation_events.append(StimulationEventTag.read(reader, tag_entry))

    @staticmethod
    def _well_name_from_position(well_row: int, well_column: int) -> str:
        """Convert Axion numeric well coordinates to names like `D6`."""
        return f"{chr(ord('A') + well_row - 1)}{well_column}"

    def _parse_micro_ops_intervals(self, micro_ops_xml: str) -> list[OpticalOnInterval]:
        """Extract optical-on intervals from the waveform-program XML."""
        root = ET.fromstring(micro_ops_xml)
        trial_loop = self._find_trial_loop(root)
        if trial_loop is None:
            return []

        context = {
            "time_ms": 0.0,
            "intensity": 0.0,
            "anchor_seen": False,
            "stop": False,
            "intervals": [],
        }
        self._process_children_once(trial_loop, context)
        return context["intervals"]

    def _find_trial_loop(self, root: ET.Element) -> ET.Element | None:
        """Locate the XML loop corresponding to one stimulation trial."""
        for element in root.iter():
            if self._local_name(element.tag) != "loop":
                continue
            if any(self._local_name(child.tag) == "tag" for child in list(element)):
                return element
        return None

    def _process_children_once(self, parent: ET.Element, context: dict[str, object]) -> None:
        """Execute one pass through the XML micro-op children to build intervals."""
        for child in list(parent):
            if context["stop"]:
                return

            name = self._local_name(child.tag)
            if name == "tag":
                if context["anchor_seen"]:
                    context["stop"] = True
                    return
                context["anchor_seen"] = True
                context["time_ms"] = 0.0
            elif name == "tlcset":
                context["intensity"] = float(child.attrib.get("intensity", "0"))
            elif name == "delay":
                duration_ms = self._parse_duration_ms(child.attrib.get("duration", "0 ms"))
                start_ms = float(context["time_ms"])
                end_ms = start_ms + duration_ms
                # Only delays that occur while intensity is non-zero are treated
                # as optical-on intervals.
                if context["anchor_seen"] and float(context["intensity"]) > 0:
                    context["intervals"].append(
                        OpticalOnInterval(
                            start_ms=start_ms,
                            end_ms=end_ms,
                            intensity=float(context["intensity"]),
                        )
                    )
                context["time_ms"] = end_ms
            elif name == "loop":
                repetitions = int(child.attrib.get("repetitions", "1"))
                for _ in range(repetitions):
                    self._process_children_once(child, context)
                    if context["stop"]:
                        return

    @staticmethod
    def _parse_duration_ms(text: str) -> float:
        """Convert XML duration strings such as `500 us` or `40 ms` into ms."""
        value_str, unit = text.strip().split(maxsplit=1)
        value = float(value_str)
        unit = unit.strip()
        if unit in {"µs", "us"}:
            return value / 1000.0
        if unit == "ms":
            return value
        if unit == "s":
            return value * 1000.0
        raise ValueError(f"Unsupported duration unit: {unit}")

    @staticmethod
    def _local_name(tag: str) -> str:
        """Strip any XML namespace prefix from a tag name."""
        return tag.split("}", 1)[-1]
