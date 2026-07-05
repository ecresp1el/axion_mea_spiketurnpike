#!/usr/bin/env python3
"""Check that the Kilosort environment can see PyTorch and the GPU."""

from __future__ import annotations

import importlib.metadata
import sys


def main() -> None:
    print(f"python: {sys.version.split()[0]}")
    for package in ["numpy", "pandas", "torch", "kilosort"]:
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            version = "NOT INSTALLED"
        print(f"{package}: {version}")

    try:
        import torch
    except Exception as exc:
        print(f"torch import failed: {exc!r}")
        raise SystemExit(1) from exc

    print(f"torch cuda available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"torch cuda device count: {torch.cuda.device_count()}")
        print(f"torch cuda device 0: {torch.cuda.get_device_name(0)}")

    try:
        from kilosort.run_kilosort import run_kilosort  # noqa: F401
    except Exception as exc:
        print(f"kilosort run_kilosort import failed: {exc!r}")
        raise SystemExit(1) from exc

    print("kilosort import check: ok")


if __name__ == "__main__":
    main()
