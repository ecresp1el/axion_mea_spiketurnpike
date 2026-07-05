"""Public package exports for the supported repository API."""

from __future__ import annotations

from typing import TYPE_CHECKING


__all__ = ["AxionProjectBuilder", "AxionProjectSeriesBuilder", "ProjectBuildConfig"]

if TYPE_CHECKING:
    from .recording_project import AxionProjectBuilder, AxionProjectSeriesBuilder, ProjectBuildConfig


def __getattr__(name: str):
    """Load the full opto pipeline only when its public symbols are requested."""
    if name in __all__:
        from .recording_project import AxionProjectBuilder, AxionProjectSeriesBuilder, ProjectBuildConfig

        exports = {
            "AxionProjectBuilder": AxionProjectBuilder,
            "AxionProjectSeriesBuilder": AxionProjectSeriesBuilder,
            "ProjectBuildConfig": ProjectBuildConfig,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
