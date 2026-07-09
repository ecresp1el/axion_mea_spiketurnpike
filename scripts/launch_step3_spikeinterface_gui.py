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
    "zone3": ["trace", "spikerate", "probe", "similarity", "mainsettings"],
    "zone5": ["waveform"],
    "zone6": ["maintemplate"],
    "zone7": ["correlogram", "isi"],
}

STEP3_GUI_REMINDER = (
    "GUI reminder: curate one completed Step 1 analyzer at a time; use Merge/Delete "
    "from the unit list; use Restore/Unmerge/Unsplit from the curation panel; save "
    "with 'Save curation' to external JSON so the frozen Step 1 analyzer is not "
    "modified."
)

STEP1_DISPLAYED_UNIT_PROPERTIES = [
    "KSLabel",
    "Amplitude",
    "ContamPct",
    "classifier_label",
    "classifier_probability",
    "original_cluster_id",
    "firing_rate",
    "num_spikes",
    "x",
    "y",
]


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
    patch_probe_view_for_bokeh_compatibility()
    patch_curation_download_export_path()

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
    print(STEP3_GUI_REMINDER, flush=True)
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
        displayed_unit_properties=STEP1_DISPLAYED_UNIT_PROPERTIES,
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


def patch_probe_view_for_bokeh_compatibility() -> None:
    """Keep the web probe view alive if Bokeh drops expected CDS columns.

    spikeinterface-gui 0.13.1 can hit KeyError('alpha') in the Panel probe view
    with newer Bokeh/Panel. The view is display-only here, so repairing the
    ColumnDataSource columns before its normal patch calculation is enough.
    """
    from spikeinterface_gui.probeview import ProbeView

    if getattr(ProbeView, "_axion_step3_probe_patch", False):
        return

    original = ProbeView._panel_compute_unit_glyph_patches

    def patched_panel_compute_unit_glyph_patches(self):
        data = self.glyphs_data_source.data
        unit_ids = list(self.controller.unit_ids)
        n_units = len(unit_ids)

        alpha_selected = getattr(self, "alpha_selected", 1)
        alpha_unselected = getattr(self, "alpha_unselected", 0.3)
        size_selected = getattr(self, "unit_marker_size_selected", 20)
        size_unselected = getattr(self, "unit_marker_size_unselected", 15)

        def visibility(unit_id):
            return bool(self.controller.get_unit_visibility(unit_id))

        if "alpha" not in data or len(data["alpha"]) != n_units:
            data["alpha"] = [
                alpha_selected if visibility(unit_id) else alpha_unselected
                for unit_id in unit_ids
            ]
        if "size" not in data or len(data["size"]) != n_units:
            data["size"] = [
                size_selected if visibility(unit_id) else size_unselected
                for unit_id in unit_ids
            ]
        if "color" not in data or len(data["color"]) != n_units:
            data["color"] = [self.get_unit_color(unit_id) for unit_id in unit_ids]
        if "line_color" not in data or len(data["line_color"]) != n_units:
            data["line_color"] = [
                "black" if visibility(unit_id) else self.get_unit_color(unit_id)
                for unit_id in unit_ids
            ]

        return original(self)

    ProbeView._panel_compute_unit_glyph_patches = patched_panel_compute_unit_glyph_patches
    ProbeView._axion_step3_probe_patch = True


def patch_curation_download_export_path() -> None:
    """Keep the web JSON download from creating repo-local curation.json files."""
    from spikeinterface_gui.curationview import CurationView

    if getattr(CurationView, "_axion_step3_download_patch", False):
        return

    def patched_panel_generate_json(self):
        callback_kwargs = getattr(self.controller, "curation_callback_kwargs", None) or {}
        export_path = Path(callback_kwargs.get("output_json", "curation.json"))
        export_path.parent.mkdir(parents=True, exist_ok=True)

        curation_model = self.controller.construct_final_curation()
        with export_path.open("w") as f:
            f.write(curation_model.model_dump_json(indent=4))

        self.controller.current_curation_saved = True
        self.refresh()
        return export_path

    CurationView._panel_generate_json = patched_panel_generate_json
    CurationView._axion_step3_download_patch = True


if __name__ == "__main__":
    main()
