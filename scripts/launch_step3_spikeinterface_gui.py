#!/usr/bin/env python
"""Launch SpikeInterface GUI for frozen Step 1 analyzers with external curation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


RESULTS_AIND_MARKER = ("results", "aind")

STEP3_LAYOUT = {
    "zone1": ["curation", "spikelist"],
    "zone2": ["unitlist", "merge"],
    "zone3": ["trace", "spikerate"],
    "zone4": ["maintemplate", "correlogram", "isi"],
    "zone5": ["similarity", "mainsettings"],
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Launch spikeinterface-gui on a Step 1 SortingAnalyzer while saving "
            "manual curation JSON outside the frozen analyzer."
        )
    )
    parser.add_argument("analyzer", type=Path, help="Step 1 SortingAnalyzer Zarr folder.")
    parser.add_argument(
        "--curation-output",
        type=Path,
        default=None,
        help="Output JSON path. Defaults under results/step3_gui_curation/<recording>/<well>/.",
    )
    parser.add_argument("--address", default="localhost", help="Panel server bind address.")
    parser.add_argument("--port", type=int, default=18765, help="Panel server port.")
    parser.add_argument("--no-traces", action="store_true", help="Disable trace view.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose GUI output.")
    args = parser.parse_args()

    analyzer_path = args.analyzer.expanduser().resolve()
    curation_output = (
        args.curation_output.expanduser().resolve()
        if args.curation_output is not None
        else default_curation_output(analyzer_path)
    )

    import spikeinterface.full as si
    from spikeinterface_gui.main import run_mainwindow

    analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=False)

    def save_curation(curation_data: dict[str, Any], output_json: Path) -> None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        tmp = output_json.with_suffix(output_json.suffix + ".tmp")
        tmp.write_text(json.dumps(curation_data, indent=2, sort_keys=True) + "\n")
        tmp.replace(output_json)
        print(f"Saved Step 3 curation JSON: {output_json}", flush=True)

    print(f"Analyzer: {analyzer_path}", flush=True)
    print(f"Curation output: {curation_output}", flush=True)
    print(f"Open on the Mac via SSH tunnel: http://localhost:{args.port}", flush=True)

    run_mainwindow(
        analyzer,
        mode="web",
        with_traces=not args.no_traces,
        curation=True,
        curation_callback=save_curation,
        curation_callback_kwargs={"output_json": curation_output},
        address=args.address,
        port=args.port,
        panel_start_server_kwargs={"show": False},
        layout=STEP3_LAYOUT,
        disable_save_settings_button=True,
        verbose=args.verbose,
    )


def default_curation_output(analyzer_path: Path) -> Path:
    parts = analyzer_path.parts
    try:
        marker_index = next(
            i
            for i in range(len(parts) - 1)
            if parts[i : i + 2] == RESULTS_AIND_MARKER
        )
        recording = parts[marker_index + 2]
        well = parts[marker_index + 3]
        project_root = Path(*parts[:marker_index])
    except (StopIteration, IndexError):
        recording = analyzer_path.parents[2].name if len(analyzer_path.parents) >= 3 else "unknown_recording"
        well = analyzer_path.parents[1].name if len(analyzer_path.parents) >= 2 else "unknown_well"
        project_root = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")

    safe_recording = recording.replace("/", "_")
    safe_well = well.replace("/", "_")
    return (
        project_root
        / "results"
        / "step3_gui_curation"
        / recording
        / well
        / f"curation_{safe_recording}_{safe_well}.json"
    )


if __name__ == "__main__":
    main()
