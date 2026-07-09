#!/usr/bin/env python
"""Browse Step 1 SortingAnalyzer outputs with a safe SpikeInterface GUI layout."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

DEFAULT_AIND_RESULTS_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/aind"
)
DEFAULT_CURATION_ROOT = Path(
    "/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/results/step1_gui_curation"
)
DEFAULT_STIM_RAW_ROOTS = [
    Path("/nfs/turbo/umms-parent/axion_mea_files_directory/incoming/manny4tbum_20260706"),
    Path("/nfs/turbo/umms-parent/axion_mea_files_directory"),
]
RECORDING_NAME = "block0_None_recording1"

STEP1_LAYOUT = {
    "zone1": ["curation", "spikelist"],
    "zone2": ["unitlist", "merge"],
    "zone3": ["trace", "spikerate", "probe", "similarity", "mainsettings"],
    "zone5": ["waveform"],
    "zone6": ["maintemplate"],
    "zone7": ["correlogram", "isi"],
}

STEP1_GUI_REMINDER = """\
### Step 1 GUI reminder

- This is early per-well QC/curation for completed Step 1 analyzers only.
- Step 2, Step 3, and full recording completion are not assumed.
- Use **Merge** and **Delete** from the unit list; use the curation panel to **Restore**, **Unmerge**, or **Unsplit**.
- Save with **Save curation**. The Step 1 analyzer stays frozen; decisions are written to the external JSON shown below.
- **Download JSON** is optional; this launcher redirects it to the same external JSON path instead of the repo.
- Treat saved decisions as per-well notes until the rest of the rerun finishes.
"""

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
    parser.add_argument(
        "--recording-prefix",
        action="append",
        default=[],
        help=(
            "Only show analyzers whose recording folder starts with this prefix. "
            "May be supplied more than once."
        ),
    )
    parser.add_argument("--address", default="localhost")
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--no-traces", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--stim-raw-root",
        type=Path,
        action="append",
        default=None,
        help=(
            "Root to search for Axion .raw files used by the Stim response tab. "
            "May be supplied more than once."
        ),
    )
    parser.add_argument(
        "--no-stim-response",
        action="store_true",
        help="Disable the Axion opto-stim response tab.",
    )
    args = parser.parse_args()

    root_folder = args.root_folder.expanduser().resolve()
    recording_prefixes = list(args.recording_prefix)
    stim_raw_roots = args.stim_raw_root if args.stim_raw_root is not None else DEFAULT_STIM_RAW_ROOTS
    state: dict[str, Any] = {
        "raw_paths": build_raw_index(stim_raw_roots),
        "analyzers": [],
        "last_refresh_message": "",
    }
    state["analyzers"] = discover_analyzers(
        root_folder,
        recording_prefixes,
        stim_raw_roots,
        raw_paths=state["raw_paths"],
    )
    analyzers = state["analyzers"]
    if not analyzers:
        prefix_text = (
            f" matching prefix(es): {', '.join(args.recording_prefix)}"
            if args.recording_prefix
            else ""
        )
        raise SystemExit(f"No Step 1 analyzers found under {root_folder}{prefix_text}")

    patch_probe_view_for_bokeh_compatibility()
    patch_curation_download_export_path()

    import panel as pn

    print(f"Found {len(analyzers)} Step 1 analyzers under {args.root_folder}", flush=True)
    if args.recording_prefix:
        print(f"Recording prefix filter: {', '.join(args.recording_prefix)}", flush=True)
    print(
        "GUI reminder: inspect only completed Step 1 analyzers; save with "
        "'Save curation' to external JSON; do not treat partial rerun review as "
        "full Step 2/Step 3 completion.",
        flush=True,
    )
    print(f"Open on the Mac via SSH tunnel: http://localhost:{args.port}", flush=True)
    pn.serve(
        {
            "/": lambda: make_chooser_app(
                state,
                root_folder,
                recording_prefixes,
                stim_raw_roots,
                args.curation_root,
                args.no_traces,
            ),
            "/gui": lambda: make_gui_app(
                state,
                args.curation_root,
                args.no_traces,
                args.verbose,
                stim_response_enabled=not args.no_stim_response,
                stim_raw_roots=stim_raw_roots,
            ),
        },
        address=args.address,
        port=args.port,
        show=False,
        title="Step 1 SortingAnalyzer Browser",
    )


def make_chooser_app(
    state: dict[str, Any],
    root_folder: Path,
    recording_prefixes: list[str],
    stim_raw_roots: list[Path],
    curation_root: Path,
    no_traces_default: bool,
):
    import panel as pn

    pn.extension()

    opto_only_checkbox = pn.widgets.Checkbox(name="Opto/Lumos eligible only", value=True, width=190)
    refresh_button = pn.widgets.Button(name="Refresh analyzers", button_type="primary", width=150)
    recording_select = pn.widgets.Select(
        name="Recording",
        options=[],
        value=None,
        sizing_mode="stretch_width",
    )
    well_select = pn.widgets.Select(name="Well", width=140)
    no_traces_checkbox = pn.widgets.Checkbox(name="No traces", value=no_traces_default, width=120)
    summary = pn.pane.Markdown("", sizing_mode="stretch_width")
    selected_path = pn.pane.Markdown("", sizing_mode="stretch_width")
    open_link = pn.pane.Markdown("", sizing_mode="stretch_width")
    by_recording: dict[str, list[dict[str, str]]] = {}

    def visible_rows() -> list[dict[str, str]]:
        rows = list(state["analyzers"])
        if opto_only_checkbox.value:
            rows = [row for row in rows if row.get("opto_eligible") == "true"]
        return rows

    def rebuild_options(*_: Any) -> None:
        nonlocal by_recording
        rows = visible_rows()
        recordings = sorted({row["recording"] for row in rows})
        by_recording = {
            recording: sorted(
                [row for row in rows if row["recording"] == recording],
                key=lambda item: item["well"],
            )
            for recording in recordings
        }
        recording_select.options = recordings
        recording_select.value = recordings[0] if recordings else None
        update_wells()

        total = len(state["analyzers"])
        opto = sum(row.get("opto_eligible") == "true" for row in state["analyzers"])
        prefix_text = ", ".join(recording_prefixes) if recording_prefixes else "none"
        summary.object = (
            f"**Visible analyzers:** {len(rows)} / {total}  \n"
            f"**Visible recordings:** {len(recordings)}  \n"
            f"**Opto/Lumos candidate analyzers:** {opto}  \n"
            f"**Prefix filter:** `{prefix_text}`  \n"
            f"{state.get('last_refresh_message', '')}"
        )

    def selected_row() -> dict[str, str]:
        if recording_select.value is None:
            raise RuntimeError("No recording is selected.")
        for row in by_recording.get(recording_select.value, []):
            if row["well"] == well_select.value:
                return row
        raise RuntimeError("Selected well is not in the analyzer list.")

    def update_wells(*_: Any) -> None:
        if recording_select.value is None:
            well_select.options = []
            well_select.value = None
            selected_path.object = "No analyzers match the current filters."
            open_link.object = ""
            return
        rows = by_recording[recording_select.value]
        well_select.options = [row["well"] for row in rows]
        well_select.value = rows[0]["well"]
        update_selected_path()

    def update_selected_path(*_: Any) -> None:
        if recording_select.value is None or well_select.value is None:
            return
        row = selected_row()
        url = (
            "/gui?"
            f"recording={quote(row['recording'])}&"
            f"well={quote(row['well'])}&"
            f"no_traces={'true' if no_traces_checkbox.value else 'false'}"
        )
        selected_path.object = (
            f"**Selected analyzer**  \n`{row['analyzer_path']}`  \n"
            f"**Curation JSON**  \n`{default_curation_output(row, curation_root)}`  \n"
            f"**Opto/Lumos candidate**  \n`{row.get('opto_eligible', 'false')}`  \n"
            f"**Opto reason**  \n`{row.get('opto_reason', '')}`  \n"
            f"**Matched raw**  \n`{row.get('stim_raw_path', '') or 'not resolved'}`"
        )
        open_link.object = f"### [Open selected well]({url})"

    def refresh_analyzers(*_: Any) -> None:
        state["raw_paths"] = build_raw_index(stim_raw_roots)
        state["analyzers"] = discover_analyzers(
            root_folder,
            recording_prefixes,
            stim_raw_roots,
            raw_paths=state["raw_paths"],
        )
        state["last_refresh_message"] = "Refreshed analyzer list from disk."
        rebuild_options()

    opto_only_checkbox.param.watch(rebuild_options, "value")
    refresh_button.on_click(refresh_analyzers)
    recording_select.param.watch(update_wells, "value")
    well_select.param.watch(update_selected_path, "value")
    no_traces_checkbox.param.watch(update_selected_path, "value")
    rebuild_options()

    return pn.Column(
        pn.pane.Markdown("# Step 1 SortingAnalyzer Browser"),
        pn.pane.Markdown(STEP1_GUI_REMINDER, sizing_mode="stretch_width"),
        pn.Row(opto_only_checkbox, refresh_button, no_traces_checkbox, sizing_mode="stretch_width"),
        summary,
        pn.Row(recording_select, well_select, sizing_mode="stretch_width"),
        selected_path,
        open_link,
        sizing_mode="stretch_width",
    )


def make_gui_app(
    state: dict[str, Any],
    curation_root: Path,
    no_traces_default: bool,
    verbose: bool,
    *,
    stim_response_enabled: bool,
    stim_raw_roots: list[Path],
):
    import panel as pn

    pn.extension()
    args = pn.state.session_args
    recording = unquote(args.get("recording", [b""])[0].decode("utf-8"))
    well = unquote(args.get("well", [b""])[0].decode("utf-8"))
    no_traces_arg = args.get("no_traces", [b"true" if no_traces_default else b"false"])[0].decode("utf-8")
    no_traces = no_traces_arg.lower() == "true"

    row = next((item for item in state["analyzers"] if item["recording"] == recording and item["well"] == well), None)
    if row is None:
        return pn.Column(
            pn.pane.Markdown("# Unknown recording/well"),
            pn.pane.Markdown(f"`recording={recording}`  \n`well={well}`"),
            pn.pane.Markdown("[Back to chooser](/)"),
        )

    import spikeinterface.full as si
    from spikeinterface_gui.main import run_mainwindow

    analyzer_path = Path(row["analyzer_path"])
    curation_output = default_curation_output(row, curation_root)
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
        with_traces=not no_traces,
        curation=True,
        curation_callback=save_curation,
        curation_callback_kwargs={"output_json": curation_output},
        layout=STEP1_LAYOUT,
        displayed_unit_properties=STEP1_DISPLAYED_UNIT_PROPERTIES,
        start_app=False,
        panel_window_servable=False,
        disable_save_settings_button=True,
        verbose=verbose,
    )

    header = pn.Row(
        pn.pane.Markdown(f"[Back to chooser](/)  \n**{recording} / {well}**"),
        sizing_mode="stretch_width",
    )
    status = pn.pane.Markdown(
        f"{STEP1_GUI_REMINDER}\n**Manual curation JSON**  \n`{curation_output}`",
        sizing_mode="stretch_width",
    )
    tabs = pn.Tabs(
        ("Curation", win.main_layout),
        sizing_mode="stretch_both",
    )
    if stim_response_enabled:
        from axion_mea.gui_stim_response import make_stim_response_panel

        stim_panel = make_stim_response_panel(
            analyzer,
            recording_name=recording,
            well=well,
            analyzer_path=analyzer_path,
            raw_roots=stim_raw_roots,
        )
        tabs.append(("Stim response", stim_panel))

    print(f"Opened Step 1 GUI: {recording} / {well}", flush=True)
    print(f"Manual curation JSON: {curation_output}", flush=True)
    if stim_response_enabled:
        print(f"Stim response raw roots: {', '.join(str(path) for path in stim_raw_roots)}", flush=True)
    return pn.Column(header, status, tabs, sizing_mode="stretch_both")


def discover_analyzers(
    root: Path,
    recording_prefixes: list[str] | None = None,
    stim_raw_roots: list[Path] | None = None,
    *,
    raw_paths: list[Path] | tuple[Path, ...] | None = None,
) -> list[dict[str, str]]:
    from axion_mea.gui_stim_response import find_matching_raw_file, is_lumos_plate

    recording_prefixes = recording_prefixes or []
    stim_raw_roots = stim_raw_roots or DEFAULT_STIM_RAW_ROOTS
    rows: list[dict[str, str]] = []
    pattern = f"*/*/postprocessed/{RECORDING_NAME}.zarr"
    for analyzer_path in sorted(root.glob(pattern)):
        if not ((analyzer_path / ".zattrs").exists() or (analyzer_path / ".zmetadata").exists()):
            continue
        well_dir = analyzer_path.parents[1]
        recording_dir = analyzer_path.parents[2]
        recording = recording_dir.name
        if recording_prefixes and not any(recording.startswith(prefix) for prefix in recording_prefixes):
            continue
        raw_path = find_matching_raw_file(recording, stim_raw_roots, raw_paths=raw_paths)
        lumos = is_lumos_plate(
            plate_family="lumos_48well" if _recording_looks_lumos(recording, raw_path) else "",
            plate_type_name="FortyEightWellLumos" if "fortyeightwell" in recording.lower() else "",
        )
        cohort_match = _recording_looks_june_july(recording, raw_path)
        opto_eligible = lumos and raw_path is not None and cohort_match
        rows.append(
            {
                "recording": recording,
                "well": well_dir.name,
                "analyzer_path": str(analyzer_path),
                "opto_eligible": "true" if opto_eligible else "false",
                "stim_raw_path": str(raw_path) if raw_path is not None else "",
                "opto_reason": (
                    "June/July Lumos raw matched"
                    if opto_eligible
                    else "not June/July Lumos with matched raw"
                ),
            }
        )
    return rows


def build_raw_index(stim_raw_roots: list[Path]) -> tuple[Path, ...]:
    from axion_mea.gui_stim_response import list_raw_files

    return list_raw_files(stim_raw_roots)


def _recording_looks_lumos(recording: str, raw_path: Path | None) -> bool:
    text = f"{recording} {raw_path or ''}".lower()
    return (
        "lumos" in text
        or "fortyeightwell" in text
        or "129-8445" in text
        or "129-8447" in text
    )


def _recording_looks_june_july(recording: str, raw_path: Path | None) -> bool:
    text = f"{recording} {raw_path or ''}".lower()
    return (
        "6_18_2026" in text
        or "6_22_2026" in text
        or "july" in text
        or "7_2026" in text
        or "2026_07" in text
    )


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


def patch_curation_download_export_path() -> None:
    """Keep the web JSON download from creating repo-local curation.json files."""
    from spikeinterface_gui.curationview import CurationView

    if getattr(CurationView, "_axion_step1_download_patch", False):
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
    CurationView._axion_step1_download_patch = True


if __name__ == "__main__":
    main()
