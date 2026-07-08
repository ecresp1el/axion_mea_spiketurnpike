"""Small reproducibility helpers for Step 3 downstream analysis outputs."""

from __future__ import annotations

import json
import os
import shlex
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .master_unit_table import CANONICAL_MASTER_UNIT_TABLE


DEFAULT_STEP3_REPRO_DIR = CANONICAL_MASTER_UNIT_TABLE.parent / "repro"


def command_context(parsed_args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return command and environment context for a Step 3 analysis command."""

    conda_command = ["python", *sys.argv]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cwd": str(Path.cwd()),
        "python_executable": sys.executable,
        "argv": sys.argv,
        "command": " ".join(shlex.quote(part) for part in conda_command),
        "parsed_args": parsed_args or {},
        "environment": {
            key: os.environ.get(key, "")
            for key in [
                "CONDA_BASE",
                "CONDA_DEFAULT_ENV",
                "CONDA_PREFIX",
                "CONDA_ENV",
                "PROJECT_ROOT",
                "REPO_ROOT",
                "PYTHONPATH",
            ]
        },
    }


def write_command_repro(
    *,
    repro_dir: str | Path = DEFAULT_STEP3_REPRO_DIR,
    stem: str,
    parsed_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write exact command and JSON command context under a Turbo repro folder."""

    repro_dir = Path(repro_dir)
    repro_dir.mkdir(parents=True, exist_ok=True)
    context = command_context(parsed_args=parsed_args)

    command_path = repro_dir / f"{stem}_command.sh"
    context_path = repro_dir / f"{stem}_command_context.json"
    command_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'source "${PROJECT_CONFIG:-/home/elcrespo/Desktop/githubprojects/axion_mea_spiketurnpike/config/greatlakes_project.env}"',
                'source "${CONDA_BASE}/etc/profile.d/conda.sh"',
                'conda activate "${CONDA_ENV}"',
                context["command"],
                "",
            ]
        ),
        encoding="utf-8",
    )
    command_path.chmod(0o755)
    context_path.write_text(json.dumps(context, indent=2, default=str) + "\n", encoding="utf-8")
    context["command_path"] = str(command_path)
    context["context_path"] = str(context_path)
    return context
