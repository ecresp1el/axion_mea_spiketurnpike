#!/usr/bin/env python3
"""Preserve the AIND analyzer and give its recording a durable results path."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_equal(left, right, description: str) -> None:
    try:
        if isinstance(left, dict):
            if left.keys() != right.keys():
                raise AssertionError("Dictionary keys differ")
            for key in left:
                check_equal(left[key], right[key], f"{description}.{key}")
        elif isinstance(left, (list, tuple)):
            if len(left) != len(right):
                raise AssertionError("Sequence lengths differ")
            for index, (a, b) in enumerate(zip(left, right)):
                check_equal(a, b, f"{description}[{index}]")
        else:
            np.testing.assert_equal(left, right)
    except (AssertionError, TypeError) as exc:
        raise ValueError(f"Preservation check failed: {description}") from exc


def verify_recordings(original, durable) -> list[dict]:
    for method in ("get_num_segments", "get_num_channels", "get_sampling_frequency", "get_dtype",
                   "get_channel_ids", "get_channel_gains", "get_channel_offsets", "get_channel_locations"):
        check_equal(getattr(original, method)(), getattr(durable, method)(), method)
    check_equal(original.get_probegroup().to_dict(), durable.get_probegroup().to_dict(), "probe")
    check_equal(sorted(original.get_property_keys()), sorted(durable.get_property_keys()), "recording properties")
    for name in original.get_property_keys():
        check_equal(original.get_property(name), durable.get_property(name), f"recording property {name}")
    windows = []
    for segment in range(original.get_num_segments()):
        count = original.get_num_samples(segment_index=segment)
        check_equal(count, durable.get_num_samples(segment_index=segment), "recording samples")
        for start in sorted({0, count // 2, max(0, count - 32)}):
            window = {"segment_index": segment, "start_frame": start, "end_frame": min(start + 32, count)}
            for scaled in (False, True):
                check_equal(original.get_traces(**window, return_in_uV=scaled),
                            durable.get_traces(**window, return_in_uV=scaled), "recording traces")
            windows.append(window)
    return windows


def verify_analyzers(original, durable) -> list[str]:
    check_equal(original.sorting.unit_ids, durable.sorting.unit_ids, "unit IDs")
    check_equal(original.sorting.to_spike_vector(), durable.sorting.to_spike_vector(), "spike vector")
    check_equal(sorted(original.sorting.get_property_keys()), sorted(durable.sorting.get_property_keys()), "unit properties")
    for name in original.sorting.get_property_keys():
        check_equal(original.sorting.get_property(name), durable.sorting.get_property(name), f"unit property {name}")
    check_equal(original.return_in_uV, durable.return_in_uV, "analyzer voltage units")
    check_equal(original.sparsity is None, durable.sparsity is None, "analyzer sparsity presence")
    if original.sparsity is not None:
        check_equal(original.sparsity.mask, durable.sparsity.mask, "analyzer sparsity mask")
    extensions = sorted(original.get_saved_extension_names())
    check_equal(extensions, sorted(durable.get_saved_extension_names()), "saved extensions")
    for name in extensions:
        left, right = original.get_extension(name), durable.get_extension(name)
        check_equal(left.params, right.params, f"{name} parameters")
        check_equal(left.data, right.data, f"{name} data")
    return extensions


def finalize(results_dir: Path, source_binary: Path | None = None) -> dict:
    import spikeinterface as si

    results_dir = results_dir.expanduser().resolve()
    if source_binary is not None:
        source_binary = Path(source_binary).expanduser().resolve()
    analyzers = sorted((results_dir / "postprocessed").glob("*.zarr"))
    if len(analyzers) != 1:
        raise ValueError(f"Expected one analyzer, found {len(analyzers)}")
    analyzer_path = analyzers[0]
    original = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
    if not original.has_recording():
        raise ValueError("Original analyzer recording must be available for preservation checks")
    recording = original.recording
    if not isinstance(recording, si.BinaryFolderRecording):
        raise ValueError("Expected AIND BinaryFolderRecording")
    source_folder = Path(recording.to_dict()["kwargs"]["folder_path"]).resolve()
    durable_folder = results_dir / "preprocessed" / analyzer_path.stem
    pending_recording = durable_folder.with_name(durable_folder.name + ".pending")
    pending_analyzer = analyzer_path.with_name(analyzer_path.stem + ".pending.zarr")
    backup = results_dir / "repro/analyzer_before_durable_recording" / analyzer_path.name
    report_path = results_dir / "durable_recording_report.json"
    for path in (durable_folder, pending_recording, pending_analyzer, backup, report_path):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing preservation artifact: {path}")
    for path in recording.get_binary_description()["file_paths"]:
        Path(path).resolve().relative_to(source_folder)

    durable_folder.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_folder, pending_recording)
    source_files = sorted(p.relative_to(source_folder) for p in source_folder.rglob("*") if p.is_file())
    copied_files = sorted(p.relative_to(pending_recording) for p in pending_recording.rglob("*") if p.is_file())
    check_equal(source_files, copied_files, "recording file inventory")
    hashes = {}
    for relative in source_files:
        source_hash = sha256(source_folder / relative)
        check_equal(source_hash, sha256(pending_recording / relative), f"file checksum {relative}")
        hashes[relative.as_posix()] = source_hash
    pending_recording.rename(durable_folder)
    durable_recording = si.read_binary_folder(durable_folder)
    windows = verify_recordings(recording, durable_recording)
    source_binary_hash = None
    if source_binary is not None:
        description = durable_recording.get_binary_description()
        if len(description["file_paths"]) != 1 or description["file_offset"] != 0:
            raise ValueError("Source-count comparison requires a single binary with zero offset")
        source_binary_hash = sha256(source_binary)
        trace_relative = Path(description["file_paths"][0]).relative_to(durable_folder).as_posix()
        check_equal(source_binary_hash, hashes[trace_relative], "original staged int32 counts")

    # Public load(recording=...) and save_as copy extension data; no recomputation is requested.
    rebound = si.SortingAnalyzer.load(analyzer_path, recording=durable_recording, load_extensions=True)
    rebound.save_as(format="zarr", folder=pending_analyzer)
    saved = si.load_sorting_analyzer(pending_analyzer, load_extensions=True)
    extensions = verify_analyzers(original, saved)
    verify_recordings(recording, saved.recording)
    if Path(saved.recording.to_dict()["kwargs"]["folder_path"]).resolve() != durable_folder:
        raise ValueError("Saved analyzer did not preserve its durable recording reference")

    backup.parent.mkdir(parents=True, exist_ok=True)
    analyzer_path.rename(backup)
    try:
        pending_analyzer.rename(analyzer_path)
    except BaseException:
        backup.rename(analyzer_path)
        raise
    final = si.load_sorting_analyzer(analyzer_path, load_extensions=True)
    verify_analyzers(original, final)
    verify_recordings(recording, final.recording)
    report = {
        "status": "validated", "finalized_at_utc": datetime.now(timezone.utc).isoformat(),
        "spikeinterface_version": si.__version__, "source_recording_folder": str(source_folder),
        "durable_recording_folder": str(durable_folder), "analyzer": str(analyzer_path),
        "original_analyzer_backup": str(backup), "file_sha256": hashes,
        "original_staged_binary": str(source_binary) if source_binary else None,
        "original_staged_binary_sha256": source_binary_hash,
        "unit_count": len(final.unit_ids), "spike_count": len(final.sorting.to_spike_vector()),
        "unchanged_extensions": extensions, "trace_windows": windows,
        "verification": "All copied files checksum-identical; recording metadata, calibrated trace windows, "
                        "spike vector, unit properties, sparsity, extension data and parameters unchanged.",
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--source-binary", type=Path)
    args = parser.parse_args()
    print(json.dumps(finalize(args.results_dir, args.source_binary), indent=2))


if __name__ == "__main__":
    main()
