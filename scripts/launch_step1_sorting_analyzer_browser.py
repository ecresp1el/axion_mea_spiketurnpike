#!/usr/bin/env python
"""Browse Step 1 SortingAnalyzer outputs with a safe SpikeInterface GUI layout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_AIND_RESULTS_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind"
)
DEFAULT_CURATION_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/step1_gui_curation"
)
RECORDING_NAME = "block0_None_recording1"

STEP1_LAYOUT = {
    "zone1": ["curation", "spikelist"],
    "zone2": ["unitlist", "merge"],
    "zone3": ["trace", "spikerate"],
    "zone4": ["probe", "waveform", "maintemplate", "correlogram", "isi"],
    "zone5": ["similarity", "mainsettings"],
}

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
            "Serve a browser launcher for completed Step 1 AIND/Kilosort "
            "SortingAnalyzer outputs."
        )
    )
    parser.add_argument("--root-folder", type=Path, default=DEFAULT_AIND_RESULTS_ROOT)
    parser.add_argument("--curation-root", type=Path, default=DEFAULT_CURATION_ROOT)
    parser.add_argument("--address", default="localhost")
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--no-traces", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    analyzers = discover_analyzers(args.root_folder.expanduser().resolve())
    if not analyzers:
        raise SystemExit(f"No Step 1 analyzers found under {args.root_folder}")

    patch_probe_view_for_bokeh_compatibility()

    import panel as pn

    pn.extension()

    recordings = sorted({row["recording"] for row in analyzers})
    by_recording = {
        recording: sorted(
            [row for row in analyzers if row["recording"] == recording],
            key=lambda item: item["well"],
        )
        for recording in recordings
    }

    recording_select = pn.widgets.Select(
        name="Recording",
        options=recordings,
        value=recordings[0],
        sizing_mode="stretch_width",
    )
    well_select = pn.widgets.Select(name="Well", sizing_mode="fixed", width=120)
    open_button = pn.widgets.Button(name="Open selected well", button_type="primary", width=170)
    clear_button = pn.widgets.Button(name="Back to chooser", width=150)
    no_traces_checkbox = pn.widgets.Checkbox(name="No traces", value=args.no_traces, width=120)
    selected_path = pn.pane.Markdown("", sizing_mode="stretch_width")
    status = pn.pane.Markdown("", sizing_mode="stretch_width")
    gui_container = pn.Column(sizing_mode="stretch_both")
    window_state: dict[str, Any] = {"window": None}

    def update_wells(*_: Any) -> None:
        rows = by_recording[recording_select.value]
        options = {row["well"]: row["well"] for row in rows}
        well_select.options = options
        well_select.value = rows[0]["well"]
        update_selected_path()

    def selected_row() -> dict[str, str]:
        for row in by_recording[recording_select.value]:
            if row["well"] == well_select.value:
                return row
        raise RuntimeError("Selected well is not in the analyzer list.")

    def update_selected_path(*_: Any) -> None:
        row = selected_row()
        selected_path.object = (
            f"**Selected analyzer**  \n`{row['analyzer_path']}`  \n"
            f"**Curation JSON**  \n`{default_curation_output(row, args.curation_root)}`"
        )

    def open_selected_well(_: Any) -> None:
        row = selected_row()
        analyzer_path = Path(row["analyzer_path"])
        curation_output = default_curation_output(row, args.curation_root)
        status.object = f"Loading `{row['recording']}` / `{row['well']}`..."
        gui_container.clear()

        import spikeinterface.full as si
        from spikeinterface_gui.main import run_mainwindow

        analyzer = si.load_sorting_analyzer(analyzer_path, load_extensions=False)

        def save_curation(curation_data: dict[str, Any], output_json: Path) -> None:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            tmp = output_json.with_suffix(output_json.suffix + ".tmp")
            tmp.write_text(json.dumps(curation_data, indent=2, sort_keys=True) + "\n")
            tmp.replace(output_json)
            print(f"Saved Step 1 GUI curation JSON: {output_json}", flush=True)

        win = run_mainwindow(
            analyzer,
            mode="web",
            with_traces=not no_traces_checkbox.value,
            curation=True,
            curation_callback=save_curation,
            curation_callback_kwargs={"output_json": curation_output},
            layout=STEP1_LAYOUT,
            displayed_unit_properties=STEP1_DISPLAYED_UNIT_PROPERTIES,
            start_app=False,
            panel_window_servable=False,
            disable_save_settings_button=True,
            verbose=args.verbose,
        )
        window_state["window"] = win
        gui_container[:] = [win.main_layout]
        status.object = (
            f"Opened `{row['recording']}` / `{row['well']}`. "
            f"Manual curation saves to `{curation_output}`."
        )

    def back_to_chooser(_: Any) -> None:
        gui_container.clear()
        window_state["window"] = None
        status.object = "Choose another recording/well."

    recording_select.param.watch(update_wells, "value")
    well_select.param.watch(update_selected_path, "value")
    open_button.on_click(open_selected_well)
    clear_button.on_click(back_to_chooser)
    update_wells()

    controls = pn.Column(
        pn.Row(recording_select, well_select, no_traces_checkbox, open_button, clear_button),
        selected_path,
        status,
        sizing_mode="stretch_width",
    )
    app = pn.Column(controls, gui_container, sizing_mode="stretch_both")

    print(f"Found {len(analyzers)} Step 1 analyzers under {args.root_folder}", flush=True)
    print(f"Open on the Mac via SSH tunnel: http://localhost:{args.port}", flush=True)
    pn.serve(app, address=args.address, port=args.port, show=False, title="Step 1 SortingAnalyzer Browser")


def discover_analyzers(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pattern = f"*/*/postprocessed/{RECORDING_NAME}.zarr"
    for analyzer_path in sorted(root.glob(pattern)):
        if not ((analyzer_path / ".zattrs").exists() or (analyzer_path / ".zmetadata").exists()):
            continue
        well_dir = analyzer_path.parents[1]
        recording_dir = analyzer_path.parents[2]
        rows.append(
            {
                "recording": recording_dir.name,
                "well": well_dir.name,
                "analyzer_path": str(analyzer_path),
            }
        )
    return rows


def default_curation_output(row: dict[str, str], curation_root: Path) -> Path:
    recording = row["recording"]
    well = row["well"]
    safe_recording = recording.replace("/", "_")
    safe_well = well.replace("/", "_")
    return (
        curation_root.expanduser().resolve()
        / recording
        / well
        / f"curation_{safe_recording}_{safe_well}.json"
    )


def patch_probe_view_for_bokeh_compatibility() -> None:
    from spikeinterface_gui.probeview import ProbeView

    if getattr(ProbeView, "_axion_step1_probe_patch", False):
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
    ProbeView._axion_step1_probe_patch = True


if __name__ == "__main__":
    main()
