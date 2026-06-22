from __future__ import annotations
"""Quick-look extraction of spike waveforms from Axion `.spk` files.

This module is intentionally pragmatic rather than a full production parser.
It focuses on one narrow task:

1. recover the waveform snippet attached to each detected spike in an Axion
   `.spk` file,
2. convert the snippets into microvolts using the metadata embedded in the
   same file, and
3. generate an overview figure showing many individual snippets plus the mean
   waveform.

The record layout used here was inferred directly from the user's `.spk` files:

- the main spike block is a fixed-length block-vector record,
- each spike record is 106 bytes long for the present recordings,
- the first 8 bytes store the spike sample index, and
- the final 76 bytes store 38 signed 16-bit waveform samples.

That layout is consistent with the metadata embedded in the file:

- `Sampling Frequency = 12.5 kHz`
- `Pre-Spike Duration = 0.84 ms`
- `Post-Spike Duration = 2.16 ms`

Since `(0.84 + 2.16) ms * 12.5 kHz = 37.5 samples`, the exported snippet is
interpreted here as a 38-sample waveform.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .io.raw_stim_parser import BinaryReader, EntryRecord, EntryRecordType


@dataclass(frozen=True)
class SpikeWaveformMetadata:
    """Core metadata needed to scale and label spike snippets."""

    sampling_hz: float
    voltage_scale_v_per_sample: float
    pre_spike_ms: float
    post_spike_ms: float

    @property
    def sample_count(self) -> int:
        """Return the expected waveform sample count."""
        return int(round((self.pre_spike_ms + self.post_spike_ms) * self.sampling_hz / 1000.0))

    @property
    def time_axis_ms(self) -> np.ndarray:
        """Return the snippet time axis in milliseconds."""
        dt_ms = 1000.0 / self.sampling_hz
        return np.arange(self.sample_count, dtype=float) * dt_ms - self.pre_spike_ms


@dataclass(frozen=True)
class SpikeWaveformExtraction:
    """Waveform extraction result for one `.spk` recording."""

    spk_file: Path
    recording_label: str
    metadata: SpikeWaveformMetadata
    sample_indices: np.ndarray
    waveforms_uv: np.ndarray

    @property
    def mean_waveform_uv(self) -> np.ndarray:
        """Return the mean waveform across all extracted snippets."""
        return self.waveforms_uv.mean(axis=0)

    @property
    def time_axis_ms(self) -> np.ndarray:
        """Expose the snippet time axis directly on the extraction."""
        return self.metadata.time_axis_ms


@dataclass(frozen=True)
class TroughToPeakConfig:
    """Heuristic parameters for spike-width measurements."""

    fs_rs_threshold_ms: float = 0.45


class SpikeWaveformClassifier:
    """Measure trough-to-peak latency from extracted spike snippets."""

    def __init__(self, config: TroughToPeakConfig | None = None) -> None:
        self.config = config or TroughToPeakConfig()

    def measure_extraction(self, extraction: SpikeWaveformExtraction) -> pd.DataFrame:
        """Measure trough and rebound-peak timing for every spike snippet."""
        waveforms = extraction.waveforms_uv
        time_ms = extraction.time_axis_ms
        trough_indices = np.argmin(waveforms, axis=1)
        peak_indices = np.empty(len(waveforms), dtype=int)

        for waveform_index, trough_index in enumerate(trough_indices):
            search_start = min(trough_index + 1, waveforms.shape[1] - 1)
            post_trough = waveforms[waveform_index, search_start:]
            peak_indices[waveform_index] = search_start + int(np.argmax(post_trough))

        trough_time_ms = time_ms[trough_indices]
        peak_time_ms = time_ms[peak_indices]
        trough_to_peak_ms = peak_time_ms - trough_time_ms
        waveform_class = np.where(
            trough_to_peak_ms <= self.config.fs_rs_threshold_ms,
            "FS_like",
            "RS_like",
        )

        return pd.DataFrame(
            {
                "recording_label": extraction.recording_label,
                "spk_file": str(extraction.spk_file),
                "sample_index": extraction.sample_indices.astype("uint64"),
                "trough_index": trough_indices,
                "peak_index": peak_indices,
                "trough_time_ms": trough_time_ms,
                "peak_time_ms": peak_time_ms,
                "trough_to_peak_ms": trough_to_peak_ms,
                "waveform_class": waveform_class,
            }
        )

    def measure_all(self, extractions: list[SpikeWaveformExtraction]) -> pd.DataFrame:
        """Measure trough-to-peak latency across many recordings."""
        if not extractions:
            raise ValueError("No waveform extractions were provided.")
        tables = [self.measure_extraction(extraction) for extraction in extractions]
        return pd.concat(tables, ignore_index=True)


class AxionSpikeWaveformFile:
    """Quick extractor for waveform snippets embedded in an Axion `.spk` file."""

    MAGIC_WORD = "AxionBio"
    PRIMARY_HEADER_MAX_ENTRIES = 64
    SPIKE_RECORD_PREFIX_BYTES = 30
    SPIKE_TIMESTAMP_BYTES = 8

    def __init__(self, spk_file: Path) -> None:
        self.spk_file = spk_file.expanduser().resolve()

    def extract(self) -> SpikeWaveformExtraction:
        """Extract all waveform snippets from the `.spk` file."""
        with self.spk_file.open("rb") as handle:
            reader = BinaryReader(handle)
            entries, entry_offsets = self._read_primary_header(reader)
            notes_block = self._read_first_block(handle, entries, entry_offsets, EntryRecordType.NOTES_ARRAY)
            spike_block = self._read_first_block(handle, entries, entry_offsets, EntryRecordType.BLOCK_VECTOR_DATA)
            handle.seek(0)
            file_bytes = handle.read()

        metadata = self._parse_metadata(notes_block, fallback_bytes=file_bytes)
        record_size_bytes = self.SPIKE_RECORD_PREFIX_BYTES + metadata.sample_count * 2
        if len(spike_block) % record_size_bytes != 0:
            raise ValueError(
                f"Unexpected spike block length {len(spike_block)} for inferred record size {record_size_bytes}."
            )

        spike_count = len(spike_block) // record_size_bytes
        sample_indices = np.empty(spike_count, dtype=np.uint64)
        waveform_counts = np.empty((spike_count, metadata.sample_count), dtype=np.int16)

        for record_index in range(spike_count):
            start = record_index * record_size_bytes
            record = spike_block[start : start + record_size_bytes]
            sample_indices[record_index] = np.uint64(
                int.from_bytes(record[: self.SPIKE_TIMESTAMP_BYTES], "little", signed=False)
            )
            waveform_bytes = record[self.SPIKE_RECORD_PREFIX_BYTES :]
            waveform_counts[record_index, :] = np.frombuffer(waveform_bytes, dtype="<i2", count=metadata.sample_count)

        waveforms_uv = waveform_counts.astype(np.float64) * metadata.voltage_scale_v_per_sample * 1e6
        return SpikeWaveformExtraction(
            spk_file=self.spk_file,
            recording_label=self.spk_file.stem,
            metadata=metadata,
            sample_indices=sample_indices,
            waveforms_uv=waveforms_uv,
        )

    def _read_primary_header(self, reader: BinaryReader) -> tuple[list[EntryRecord], list[int]]:
        """Read the primary header and record the body offsets for each entry."""
        magic = reader.read_ascii(len(self.MAGIC_WORD))
        if magic != self.MAGIC_WORD:
            raise ValueError(f"Unsupported file header. Expected {self.MAGIC_WORD!r}, got {magic!r}")

        reader.read_u16()  # data type
        reader.read_u16()  # version major
        reader.read_u16()  # version minor
        notes_start = reader.read_u64()
        reader.read_u32()  # notes length
        entries_start = reader.read_i64()
        entries = [EntryRecord.from_uint64(reader.read_u64()) for _ in range(self.PRIMARY_HEADER_MAX_ENTRIES)]

        offsets: list[int] = []
        current_offset = entries_start
        for entry in entries:
            offsets.append(current_offset)
            if entry.record_type == EntryRecordType.TERMINATE or entry.length < 0:
                continue
            current_offset += entry.length
        if notes_start != entries_start:
            raise ValueError(f"Unexpected notes/entry start mismatch: {notes_start} != {entries_start}")
        return entries, offsets

    @staticmethod
    def _read_first_block(
        handle,
        entries: list[EntryRecord],
        entry_offsets: list[int],
        target_type: EntryRecordType,
    ) -> bytes:
        """Return the first primary-header block for the requested record type."""
        for entry, offset in zip(entries, entry_offsets, strict=True):
            if entry.record_type == target_type:
                handle.seek(offset)
                return handle.read(entry.length)
        raise ValueError(f"Could not find block type {target_type.name} in the .spk header.")

    def _parse_metadata(self, notes_block: bytes, fallback_bytes: bytes | None = None) -> SpikeWaveformMetadata:
        """Recover sampling and waveform scaling metadata from the notes block."""
        text = notes_block.decode("utf-8", errors="ignore").replace("\x00", "")
        if "Sampling Frequency," not in text and fallback_bytes is not None:
            text = fallback_bytes.decode("utf-8", errors="ignore").replace("\x00", "")
        sampling_hz = self._parse_sampling_hz(text)
        voltage_scale = self._parse_float(text, r"Voltage Scale,([^\r\n]+)")
        pre_spike_ms = self._parse_duration_ms(text, r"Pre-Spike Duration,([^\r\n]+)")
        post_spike_ms = self._parse_duration_ms(text, r"Post-Spike Duration,([^\r\n]+)")
        return SpikeWaveformMetadata(
            sampling_hz=sampling_hz,
            voltage_scale_v_per_sample=voltage_scale,
            pre_spike_ms=pre_spike_ms,
            post_spike_ms=post_spike_ms,
        )

    @staticmethod
    def _parse_sampling_hz(text: str) -> float:
        """Parse sampling frequency strings such as `12.5 kHz`."""
        match = re.search(r"Sampling Frequency,([^\r\n]+)", text)
        if match is None:
            raise ValueError("Could not find sampling frequency in .spk notes block.")
        value_text = match.group(1).strip()
        if value_text.endswith("kHz"):
            return float(value_text[:-3].strip()) * 1000.0
        if value_text.endswith("Hz"):
            return float(value_text[:-2].strip())
        return float(value_text)

    @staticmethod
    def _parse_float(text: str, pattern: str) -> float:
        """Extract a floating-point value from the metadata text."""
        match = re.search(pattern, text)
        if match is None:
            raise ValueError(f"Could not parse float from pattern: {pattern}")
        value_text = match.group(1).strip().split()[0]
        return float(value_text)

    @staticmethod
    def _parse_duration_ms(text: str, pattern: str) -> float:
        """Extract durations like `0.84 ms` and return milliseconds."""
        match = re.search(pattern, text)
        if match is None:
            raise ValueError(f"Could not parse duration from pattern: {pattern}")
        value_text = match.group(1).strip()
        number_text, unit = value_text.split(maxsplit=1)
        value = float(number_text)
        unit = unit.strip()
        if unit == "ms":
            return value
        if unit in {"us", "µs"}:
            return value / 1000.0
        if unit == "s":
            return value * 1000.0
        raise ValueError(f"Unsupported duration unit in .spk metadata: {unit}")


class SpikeWaveformOverviewWriter:
    """Write quick-look waveform figures across one or more `.spk` files."""

    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root.expanduser().resolve()
        self.figures_dir = self.output_root / "figures"
        self.tables_dir = self.output_root / "tables"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        self.tables_dir.mkdir(parents=True, exist_ok=True)

    def write_series_overview(self, extractions: list[SpikeWaveformExtraction], max_overlay: int = 600) -> dict[str, Path]:
        """Write one overview figure across many recordings plus summary tables."""
        if not extractions:
            raise ValueError("No waveform extractions were provided.")

        ncols = min(3, len(extractions))
        nrows = int(np.ceil(len(extractions) / ncols))
        fig, axes = plt.subplots(nrows, ncols, figsize=(5.2 * ncols, 3.8 * nrows), constrained_layout=True)
        axes = np.atleast_1d(axes).ravel()

        mean_rows: list[pd.DataFrame] = []
        summary_rows: list[dict[str, object]] = []

        for axis, extraction in zip(axes, extractions, strict=False):
            if extraction is None:
                axis.set_visible(False)
                continue
            self._draw_one_panel(axis, extraction, max_overlay=max_overlay)
            mean_rows.append(
                pd.DataFrame(
                    {
                        "recording_label": extraction.recording_label,
                        "time_ms": extraction.metadata.time_axis_ms,
                        "mean_waveform_uv": extraction.mean_waveform_uv,
                    }
                )
            )
            summary_rows.append(
                {
                    "recording_label": extraction.recording_label,
                    "spk_file": str(extraction.spk_file),
                    "spike_count": int(len(extraction.sample_indices)),
                    "waveform_sample_count": int(extraction.waveforms_uv.shape[1]),
                    "sampling_hz": extraction.metadata.sampling_hz,
                    "pre_spike_ms": extraction.metadata.pre_spike_ms,
                    "post_spike_ms": extraction.metadata.post_spike_ms,
                    "peak_mean_uv": float(np.max(extraction.mean_waveform_uv)),
                    "trough_mean_uv": float(np.min(extraction.mean_waveform_uv)),
                }
            )

        for axis in axes[len(extractions) :]:
            axis.set_visible(False)

        fig.suptitle("Quick `.spk` Waveform Overview: sample spike snippets with mean waveform overlay", fontsize=14)
        figure_path = self.figures_dir / "figure__spike_waveform_overview.png"
        fig.savefig(figure_path, dpi=220, bbox_inches="tight")
        plt.close(fig)

        pooled_figure_path = self.figures_dir / "figure__spike_waveform_overview_pooled.png"
        self._write_pooled_overview(extractions, pooled_figure_path, max_overlay=max_overlay)

        mean_waveforms_path = self.tables_dir / "table__mean_spike_waveforms_long.csv"
        pd.concat(mean_rows, ignore_index=True).to_csv(mean_waveforms_path, index=False)

        summary_path = self.tables_dir / "table__spike_waveform_summary.csv"
        pd.DataFrame(summary_rows).to_csv(summary_path, index=False)

        manifest_path = self.output_root / "spike_waveform_overview_summary.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "figure": str(figure_path),
                    "pooled_figure": str(pooled_figure_path),
                    "mean_waveforms_long": str(mean_waveforms_path),
                    "summary_table": str(summary_path),
                    "recording_count": len(extractions),
                    "assumption": "Quick parser assumes fixed 106-byte spike records with waveform samples stored in the final 76 bytes.",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "figure": figure_path,
            "pooled_figure": pooled_figure_path,
            "mean_waveforms_long": mean_waveforms_path,
            "summary_table": summary_path,
            "manifest": manifest_path,
        }

    def write_trough_to_peak_overview(
        self,
        extractions: list[SpikeWaveformExtraction],
        classifier: SpikeWaveformClassifier | None = None,
        max_overlay_per_class: int = 450,
    ) -> dict[str, Path]:
        """Write quick pooled trough-to-peak classification plots and tables."""
        classifier = classifier or SpikeWaveformClassifier()
        measurements = classifier.measure_all(extractions)
        threshold_ms = classifier.config.fs_rs_threshold_ms

        measurement_path = self.tables_dir / "table__trough_to_peak_measurements.csv"
        measurements.to_csv(measurement_path, index=False)

        summary = (
            measurements.groupby("waveform_class", dropna=False)["trough_to_peak_ms"]
            .agg(["count", "mean", "median", "std", "min", "max"])
            .reset_index()
        )
        summary["threshold_ms"] = threshold_ms
        summary_path = self.tables_dir / "table__trough_to_peak_summary.csv"
        summary.to_csv(summary_path, index=False)

        overlay_figure_path = self.figures_dir / "figure__trough_to_peak_overlay_by_class.png"
        histogram_figure_path = self.figures_dir / "figure__trough_to_peak_latency_histogram.png"
        self._write_trough_to_peak_overlay(
            extractions=extractions,
            measurements=measurements,
            threshold_ms=threshold_ms,
            output_path=overlay_figure_path,
            max_overlay_per_class=max_overlay_per_class,
        )
        self._write_trough_to_peak_histogram(
            measurements=measurements,
            threshold_ms=threshold_ms,
            output_path=histogram_figure_path,
        )

        manifest_path = self.output_root / "trough_to_peak_summary.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "overlay_figure": str(overlay_figure_path),
                    "histogram_figure": str(histogram_figure_path),
                    "measurements_table": str(measurement_path),
                    "summary_table": str(summary_path),
                    "classification_threshold_ms": threshold_ms,
                    "note": "FS_like versus RS_like is a coarse heuristic based on pooled spike waveform trough-to-peak latency.",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "overlay_figure": overlay_figure_path,
            "histogram_figure": histogram_figure_path,
            "measurements_table": measurement_path,
            "summary_table": summary_path,
            "manifest": manifest_path,
        }

    @staticmethod
    def _draw_one_panel(axis: plt.Axes, extraction: SpikeWaveformExtraction, max_overlay: int) -> None:
        """Draw a representative sample of snippets plus the mean waveform."""
        waveforms = extraction.waveforms_uv
        time_ms = extraction.metadata.time_axis_ms
        rng = np.random.default_rng(20260622)
        if len(waveforms) > max_overlay:
            keep = rng.choice(len(waveforms), size=max_overlay, replace=False)
            overlay = waveforms[keep]
        else:
            overlay = waveforms

        axis.plot(time_ms, overlay.T, color="#93c5fd", alpha=0.035, linewidth=0.8)
        axis.plot(time_ms, extraction.mean_waveform_uv, color="#0057ff", linewidth=2.6, label="mean waveform")
        axis.axvline(0, color="crimson", linestyle="--", linewidth=0.9)
        axis.axhline(0, color="#cbd5e1", linewidth=0.8)
        axis.set_title(f"{extraction.recording_label}\n{len(waveforms)} detected spikes")
        axis.set_xlabel("ms around spike")
        axis.set_ylabel("uV")
        axis.legend(loc="upper right", fontsize=8)
        axis.grid(True, alpha=0.18)

    @staticmethod
    def _write_pooled_overview(
        extractions: list[SpikeWaveformExtraction],
        output_path: Path,
        max_overlay: int,
    ) -> None:
        """Write one pooled figure combining all spike snippets across recordings."""
        time_ms = extractions[0].metadata.time_axis_ms
        pooled_waveforms = np.vstack([extraction.waveforms_uv for extraction in extractions])
        pooled_mean = pooled_waveforms.mean(axis=0)

        rng = np.random.default_rng(20260622)
        if len(pooled_waveforms) > max_overlay:
            keep = rng.choice(len(pooled_waveforms), size=max_overlay, replace=False)
            overlay = pooled_waveforms[keep]
        else:
            overlay = pooled_waveforms

        fig, axis = plt.subplots(figsize=(7.0, 4.5), constrained_layout=True)
        axis.plot(time_ms, overlay.T, color="#93c5fd", alpha=0.03, linewidth=0.75)
        axis.plot(time_ms, pooled_mean, color="#0057ff", linewidth=3.0, label="overall mean waveform")
        axis.axvline(0, color="crimson", linestyle="--", linewidth=0.9)
        axis.axhline(0, color="#cbd5e1", linewidth=0.8)
        axis.set_title(f"All recordings pooled\n{len(pooled_waveforms)} detected spikes")
        axis.set_xlabel("ms around spike")
        axis.set_ylabel("uV")
        axis.legend(loc="upper right", fontsize=9)
        axis.grid(True, alpha=0.18)
        fig.savefig(output_path, dpi=240, bbox_inches="tight")
        plt.close(fig)

    @staticmethod
    def _write_trough_to_peak_overlay(
        extractions: list[SpikeWaveformExtraction],
        measurements: pd.DataFrame,
        threshold_ms: float,
        output_path: Path,
        max_overlay_per_class: int,
    ) -> None:
        """Overlay pooled spike snippets split by heuristic FS/RS classes."""
        pooled_waveforms = np.vstack([extraction.waveforms_uv for extraction in extractions])
        time_ms = extractions[0].time_axis_ms
        class_labels = measurements["waveform_class"].to_numpy()
        rng = np.random.default_rng(20260622)

        class_specs = [
            ("FS_like", "#f59e0b", "#b45309"),
            ("RS_like", "#0ea5a4", "#115e59"),
        ]

        fig, axes = plt.subplots(1, 2, figsize=(12.0, 4.4), constrained_layout=True, sharey=True)
        for axis, (class_name, light_color, dark_color) in zip(axes, class_specs, strict=True):
            class_mask = class_labels == class_name
            class_waveforms = pooled_waveforms[class_mask]
            if len(class_waveforms) == 0:
                axis.set_visible(False)
                continue

            if len(class_waveforms) > max_overlay_per_class:
                keep = rng.choice(len(class_waveforms), size=max_overlay_per_class, replace=False)
                overlay = class_waveforms[keep]
            else:
                overlay = class_waveforms

            class_latencies = measurements.loc[class_mask, "trough_to_peak_ms"].to_numpy()
            class_mean = class_waveforms.mean(axis=0)
            axis.plot(time_ms, overlay.T, color=light_color, alpha=0.035, linewidth=0.75)
            axis.plot(time_ms, class_mean, color=dark_color, linewidth=3.0)
            axis.axvline(0, color="crimson", linestyle="--", linewidth=0.9)
            axis.axhline(0, color="#cbd5e1", linewidth=0.8)
            axis.set_title(
                f"{class_name}\nN={len(class_waveforms)} | median TTP={np.median(class_latencies):.3f} ms"
            )
            axis.set_xlabel("ms around spike")
            axis.grid(True, alpha=0.18)

        axes[0].set_ylabel("uV")
        fig.suptitle(
            f"Pooled spike waveform overlays by trough-to-peak class\nthreshold = {threshold_ms:.2f} ms"
        )
        fig.savefig(output_path, dpi=240, bbox_inches="tight")
        plt.close(fig)

    @staticmethod
    def _write_trough_to_peak_histogram(
        measurements: pd.DataFrame,
        threshold_ms: float,
        output_path: Path,
    ) -> None:
        """Plot pooled trough-to-peak latency distributions."""
        fs_values = measurements.loc[measurements["waveform_class"] == "FS_like", "trough_to_peak_ms"].to_numpy()
        rs_values = measurements.loc[measurements["waveform_class"] == "RS_like", "trough_to_peak_ms"].to_numpy()
        bins = np.arange(0.0, max(measurements["trough_to_peak_ms"].max() + 0.08, 1.68), 0.08)

        fig, axis = plt.subplots(figsize=(7.4, 4.6), constrained_layout=True)
        axis.hist(rs_values, bins=bins, color="#5eead4", alpha=0.75, label=f"RS_like (n={len(rs_values)})")
        axis.hist(fs_values, bins=bins, color="#fbbf24", alpha=0.75, label=f"FS_like (n={len(fs_values)})")
        axis.axvline(threshold_ms, color="black", linestyle="--", linewidth=1.3, label=f"threshold {threshold_ms:.2f} ms")
        axis.set_xlabel("trough-to-peak latency (ms)")
        axis.set_ylabel("spike count")
        axis.set_title("Pooled trough-to-peak latency distribution")
        axis.legend(loc="upper right")
        axis.grid(True, alpha=0.18)
        fig.savefig(output_path, dpi=240, bbox_inches="tight")
        plt.close(fig)
