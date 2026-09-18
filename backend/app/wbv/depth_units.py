"""WBV canonical depth-unit foundation.

This module is intentionally not wired into current WBV runtime behavior.

Rules:
- canonical runtime depth unit is metres;
- display-unit switching must not mutate model-space geometry;
- source scientific values retain provenance;
- conversion to display units happens only at presentation/input boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

CanonicalDepthUnit = Literal["m"]
DisplayDepthUnit = Literal["m", "ft"]
SourceDepthUnit = Literal["m", "ft"]

WBV_CANONICAL_DEPTH_UNIT: CanonicalDepthUnit = "m"
METRES_TO_FEET = 3.280839895013123
FEET_TO_METRES = 1.0 / METRES_TO_FEET


def _finite(value: float, name: str = "value") -> float:
    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError(f"{name} must be finite")
    return numeric


def normalize_depth_unit(value: object) -> DisplayDepthUnit | None:
    raw = str(value or "").strip().lower()
    if raw in {"m", "meter", "meters", "metre", "metres"}:
        return "m"
    if raw in {"ft", "foot", "feet"}:
        return "ft"
    return None


def source_depth_to_canonical(value: float, source_unit: SourceDepthUnit) -> float:
    numeric = _finite(value)
    return numeric if source_unit == "m" else numeric * FEET_TO_METRES


def canonical_depth_to_display(value_m: float, display_unit: DisplayDepthUnit) -> float:
    numeric = _finite(value_m, "value_m")
    return numeric if display_unit == "m" else numeric * METRES_TO_FEET


def display_depth_to_canonical(value: float, display_unit: DisplayDepthUnit) -> float:
    numeric = _finite(value)
    return numeric if display_unit == "m" else numeric * FEET_TO_METRES


@dataclass(frozen=True)
class CanonicalDepthInterval:
    top_md_m: float
    base_md_m: float


@dataclass(frozen=True)
class DisplayDepthInterval:
    top_md: float
    base_md: float
    depth_unit: DisplayDepthUnit


def canonical_interval_to_display(
    interval: CanonicalDepthInterval,
    display_unit: DisplayDepthUnit,
) -> DisplayDepthInterval:
    return DisplayDepthInterval(
        top_md=canonical_depth_to_display(interval.top_md_m, display_unit),
        base_md=canonical_depth_to_display(interval.base_md_m, display_unit),
        depth_unit=display_unit,
    )


def display_interval_to_canonical(
    top_md: float,
    base_md: float,
    display_unit: DisplayDepthUnit,
) -> CanonicalDepthInterval:
    return CanonicalDepthInterval(
        top_md_m=display_depth_to_canonical(top_md, display_unit),
        base_md_m=display_depth_to_canonical(base_md, display_unit),
    )


def canonical_coordinate_readout_to_display(
    value_m: float,
    display_unit: DisplayDepthUnit,
) -> float:
    """For UI/readout only. Never apply to renderer/model-space coordinates."""
    return canonical_depth_to_display(value_m, display_unit)


def canonical_dogleg_to_display(
    degrees_per_30m: float,
    display_unit: DisplayDepthUnit,
) -> float:
    numeric = _finite(degrees_per_30m, "degrees_per_30m")
    if display_unit == "m":
        return numeric
    metres_per_100ft = 100.0 * FEET_TO_METRES
    return numeric * (metres_per_100ft / 30.0)
