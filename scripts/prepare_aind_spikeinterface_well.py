#!/usr/bin/env python3
"""Prepare AIND SpikeInterface input params for one exported Axion well."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from axion_mea.well_mapping import AxionWellMapping


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write ProbeInterface and AIND params files for one Axion binary well."
    )
    parser.add_argument("--recording-stem", required=True)
    parser.add_argument("--well", required=True)
    parser.add_argument("--binary-file", type=Path, required=True)
    parser.add_argument("--channel-mapping", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--export-manifest", type=Path, default=None)
    parser.add_argument("--params-template", type=Path, default=REPO_ROOT / "config/aind_axion_lumos_params.json")
    parser.add_argument("--fs", type=float, default=12500.0)
    parser.add_argument("--dtype", default="int16")
    parser.add_argument("--num-channels", type=int, default=16)
    parser.add_argument("--gain-to-uV", type=float, default=None)
    parser.add_argument("--offset-to-uV", type=float, default=0.0)
    parser.add_argument("--is-filtered", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    binary_file = args.binary_file.expanduser().resolve()
    channel_mapping_path = args.channel_mapping.expanduser().resolve()
    well_mapping = AxionWellMapping.from_csv(channel_mapping_path)
    if well_mapping.n_channels != args.num_channels:
        raise SystemExit(
            f"Channel mapping has {well_mapping.n_channels} rows, expected {args.num_channels}: "
            f"{channel_mapping_path}"
        )
    if well_mapping.well != args.well:
        raise SystemExit(
            f"Channel mapping is for well {well_mapping.well}, not requested well {args.well}."
        )

    probe_path = output_dir / f"{args.recording_stem}_{args.well}_probeinterface.json"
    params_path = output_dir / f"{args.recording_stem}_{args.well}_aind_spikeinterface_params.json"
    env_path = output_dir / "run_aind_spikeinterface.env"

    gain_to_uv = args.gain_to_uV
    export_manifest_path = args.export_manifest.expanduser().resolve() if args.export_manifest else None
    if gain_to_uv is None and export_manifest_path is not None and export_manifest_path.exists():
        export_manifest = json.loads(export_manifest_path.read_text(encoding="utf-8"))
        voltage_scale = export_manifest.get("voltage_scale_v_per_sample")
        if voltage_scale is not None:
            gain_to_uv = float(voltage_scale) * 1e6

    well_mapping.write_probeinterface_json(probe_path)
    mapping_manifest_path = output_dir / f"{args.recording_stem}_{args.well}_channel_mapping_manifest.json"
    mapping_manifest_path.write_text(
        json.dumps(well_mapping.ingestion_manifest(), indent=2),
        encoding="utf-8",
    )

    params = json.loads(args.params_template.expanduser().resolve().read_text(encoding="utf-8"))
    job_dispatch = dict(params.get("job_dispatch", {}))
    job_dispatch["input"] = "spikeinterface"
    job_dispatch["spikeinterface_info"] = {
        "reader_type": "binary",
        "reader_kwargs": {
            "file_paths": [str(binary_file)],
            "sampling_frequency": args.fs,
            "dtype": args.dtype,
            "num_channels": args.num_channels,
            "time_axis": 0,
            "gain_to_uV": gain_to_uv,
            "offset_to_uV": args.offset_to_uV,
            "is_filtered": args.is_filtered,
        },
        "probe_paths": str(probe_path),
        "session_names": f"{args.recording_stem}_{args.well}",
    }
    params["job_dispatch"] = job_dispatch
    params_path.write_text(json.dumps(params, indent=2), encoding="utf-8")

    env_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                'source "${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"',
                f'export RECORDING_STEM="{args.recording_stem}"',
                f'export WELL="{args.well}"',
                "# NWB_FILE is still staged by the current launcher, but job_dispatch uses the SpikeInterface params below.",
                f'export NWB_FILE="${{PROJECT_ROOT}}/data/interim/nwb/{args.recording_stem}/{args.well}/{args.recording_stem}_{args.well}.nwb"',
                'export AIND_RUNMODE="${AIND_RUNMODE:-full}"',
                'export AIND_SORTER="${AIND_SORTER:-kilosort4}"',
                f'export AIND_PARAMS_FILE="{params_path}"',
                'export AIND_ALLOW_OVERWRITE="true"',
                'export AIND_RESUME="true"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env_path.chmod(0o755)

    print(json.dumps({
        "probeinterface_json": str(probe_path),
        "channel_mapping_manifest": str(mapping_manifest_path),
        "aind_params_file": str(params_path),
        "aind_env_file": str(env_path),
        "gain_to_uV": gain_to_uv,
        "export_manifest": str(export_manifest_path) if export_manifest_path else None,
    }, indent=2))


if __name__ == "__main__":
    main()
