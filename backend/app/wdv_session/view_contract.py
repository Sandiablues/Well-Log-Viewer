from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.identity.wdv_contract_v2 import (
    WdvCanonicalAssignment,
    WdvCanonicalSession,
    WdvCanonicalTrack,
)
from app.wdv_display.number_format import format_scale_value


class WdvScaleTickView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: float
    label: str
    normalized_position: float = Field(ge=0.0, le=1.0)


class WdvCanonicalAssignmentView(WdvCanonicalAssignment):
    scale_ticks: tuple[WdvScaleTickView, ...] = ()


class WdvCanonicalTrackView(WdvCanonicalTrack):
    assignments: tuple[WdvCanonicalAssignmentView, ...] = ()


class WdvCanonicalSessionView(WdvCanonicalSession):
    tracks: tuple[WdvCanonicalTrackView, ...] = ()


def _nice_linear_step(span: float) -> float:
    raw = span / 3.0
    exponent = math.floor(math.log10(raw))
    fraction = raw / (10.0 ** exponent)
    if fraction <= 1.0:
        nice = 1.0
    elif fraction <= 2.0:
        nice = 2.0
    elif fraction <= 2.5:
        nice = 2.5
    elif fraction <= 5.0:
        nice = 5.0
    else:
        nice = 10.0
    return nice * (10.0 ** exponent)


def _linear_tick_values(low: float, high: float) -> tuple[float, ...]:
    span = high - low
    step = _nice_linear_step(span)
    values = [low]
    first = math.ceil((low - 1e-12 * span) / step) * step
    value = first
    guard = 0
    while value < high - 1e-12 * span and guard < 20:
        if value > low + 1e-12 * span:
            values.append(value)
        value += step
        guard += 1
    values.append(high)
    deduped: list[float] = []
    for candidate in values:
        if not deduped or not math.isclose(candidate, deduped[-1], rel_tol=1e-12, abs_tol=1e-12):
            deduped.append(candidate)
    return tuple(deduped)


def _log_tick_values(low: float, high: float) -> tuple[float, ...]:
    log_low = math.log10(low)
    log_high = math.log10(high)
    decades = log_high - log_low
    rounded = round(decades)
    if 1 <= rounded <= 8 and math.isclose(decades, rounded, rel_tol=1e-10, abs_tol=1e-10):
        return tuple(low * (10.0 ** index) for index in range(rounded + 1))
    values = [low]
    for power in range(math.ceil(log_low), math.floor(log_high) + 1):
        candidate = 10.0 ** power
        if low < candidate < high:
            values.append(candidate)
    values.append(high)
    if len(values) > 7:
        interior = values[1:-1]
        stride = math.ceil(len(interior) / 5)
        values = [values[0], *interior[::stride], values[-1]]
    return tuple(values)


def _base_normalized_position(
    value: float,
    *,
    left_endpoint: float,
    right_endpoint: float,
    scale_type: Literal["linear", "logarithmic"],
) -> float:
    if scale_type == "logarithmic":
        numerator = math.log10(value) - math.log10(left_endpoint)
        denominator = math.log10(right_endpoint) - math.log10(left_endpoint)
    else:
        numerator = value - left_endpoint
        denominator = right_endpoint - left_endpoint
    if denominator == 0:
        raise ValueError("WDV scale endpoints must differ")
    return numerator / denominator


def build_assignment_scale_ticks(
    assignment: WdvCanonicalAssignment,
) -> tuple[WdvScaleTickView, ...]:
    if assignment.scale_min is None or assignment.scale_max is None:
        return ()
    minimum = float(assignment.scale_min)
    maximum = float(assignment.scale_max)
    if minimum == maximum:
        return ()
    scale_type: Literal["linear", "logarithmic"] = (
        "logarithmic" if assignment.scale_type == "logarithmic" else "linear"
    )
    if scale_type == "logarithmic" and (minimum <= 0 or maximum <= 0):
        return ()

    low = min(minimum, maximum)
    high = max(minimum, maximum)
    values = _log_tick_values(low, high) if scale_type == "logarithmic" else _linear_tick_values(low, high)

    reversed_scale = assignment.scale_direction == "reversed" and minimum < maximum
    left_endpoint = maximum if reversed_scale else minimum
    right_endpoint = minimum if reversed_scale else maximum

    anchor_bias = {"left": -0.18, "center": 0.0, "right": 0.18}[assignment.position_anchor]
    offset = float(assignment.horizontal_offset_pct) / 100.0

    ticks: list[WdvScaleTickView] = []
    for value in values:
        position = _base_normalized_position(
            float(value),
            left_endpoint=left_endpoint,
            right_endpoint=right_endpoint,
            scale_type=scale_type,
        )
        display_position = min(1.0, max(0.0, position + anchor_bias + offset))
        ticks.append(
            WdvScaleTickView(
                value=float(value),
                label=format_scale_value(float(value)),
                normalized_position=float(display_position),
            )
        )
    return tuple(ticks)


def project_canonical_session_view(
    session: WdvCanonicalSession,
) -> WdvCanonicalSessionView:
    tracks = tuple(
        WdvCanonicalTrackView.model_validate(
            {
                **track.model_dump(mode="python"),
                "assignments": [
                    {
                        **assignment.model_dump(mode="python"),
                        "scale_ticks": [
                            tick.model_dump(mode="python")
                            for tick in build_assignment_scale_ticks(assignment)
                        ],
                    }
                    for assignment in track.assignments
                ],
            }
        )
        for track in session.tracks
    )
    return WdvCanonicalSessionView.model_validate(
        {
            **session.model_dump(mode="python"),
            "tracks": [track.model_dump(mode="python") for track in tracks],
        }
    )
