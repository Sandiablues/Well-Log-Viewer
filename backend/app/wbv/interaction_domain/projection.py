from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Sequence

from .contracts import WbvAuthoritativePointV2, WbvScreenObservationV2

TARGET_WELL_HEIGHT = 5.35


@dataclass(frozen=True)
class _Projected:
    x: float
    y: float
    visible: bool


def _number(point: Any, key: str, default: float | None = None) -> float | None:
    raw = point.get(key) if isinstance(point, dict) else getattr(point, key, None)
    if isinstance(raw, (int, float)) and math.isfinite(float(raw)):
        return float(raw)
    return default


def _first_number(point: Any, *keys: str) -> float | None:
    for key in keys:
        value = _number(point, key)
        if value is not None:
            return value
    return None


def _render_xyz(point: Any) -> tuple[float, float, float]:
    """Mirror the established WBV renderer scene contract exactly."""

    east = _first_number(point, "x", "east_departure")
    north = _first_number(point, "y", "north_departure")
    depth = _first_number(point, "tvd", "md")
    if depth is None:
        z = _number(point, "z")
        depth = abs(z) if z is not None else 0.0
    return east or 0.0, -depth, north or 0.0


def normalized_trajectory(points: Sequence[Any]) -> list[tuple[float, float, float]]:
    if len(points) < 2:
        raise ValueError("Active trajectory requires at least two render points.")
    raw = [_render_xyz(point) for point in points]
    min_x, max_x = min(p[0] for p in raw), max(p[0] for p in raw)
    min_y, max_y = min(p[1] for p in raw), max(p[1] for p in raw)
    min_z, max_z = min(p[2] for p in raw), max(p[2] for p in raw)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    center_z = (min_z + max_z) / 2.0
    scale = TARGET_WELL_HEIGHT / max(1.0, abs(max_y - min_y))
    return [
        ((x - center_x) * scale, (y - center_y) * scale, (z - center_z) * scale)
        for x, y, z in raw
    ]


def _project(point: tuple[float, float, float], matrix: Sequence[float], width: float, height: float) -> _Projected:
    x, y, z = point
    clip_x = matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12]
    clip_y = matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13]
    clip_z = matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14]
    clip_w = matrix[3] * x + matrix[7] * y + matrix[11] * z + matrix[15]
    if abs(clip_w) < 1e-12:
        return _Projected(0.0, 0.0, False)
    ndc_x, ndc_y, ndc_z = clip_x / clip_w, clip_y / clip_w, clip_z / clip_w
    return _Projected(
        x=(ndc_x + 1.0) * 0.5 * width,
        y=(1.0 - ndc_y) * 0.5 * height,
        visible=-1.05 <= ndc_z <= 1.05,
    )


def _nearest_on_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> tuple[float, float]:
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    ratio = 0.0 if denom <= 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    nx, ny = ax + ratio * dx, ay + ratio * dy
    return ratio, math.hypot(px - nx, py - ny)


def _lerp(a: float | None, b: float | None, ratio: float) -> float | None:
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return a + (b - a) * ratio


def project_observation(
    points: Sequence[Any],
    observation: WbvScreenObservationV2,
    *,
    enforce_activation_tolerance: bool = True,
) -> WbvAuthoritativePointV2:
    normalized = normalized_trajectory(points)
    projected = [
        _project(point, observation.view_projection_matrix, observation.viewport_width_px, observation.viewport_height_px)
        for point in normalized
    ]
    best: tuple[int, float, float] | None = None
    for index in range(len(projected) - 1):
        first, second = projected[index], projected[index + 1]
        if not first.visible and not second.visible:
            continue
        ratio, distance = _nearest_on_segment(
            observation.pointer_x_px, observation.pointer_y_px,
            first.x, first.y, second.x, second.y,
        )
        if best is None or distance < best[2]:
            best = (index, ratio, distance)
    if best is None:
        raise ValueError("Pointer observation could not be projected onto the active trajectory.")
    index, ratio, distance = best
    if enforce_activation_tolerance and distance > observation.activation_tolerance_px:
        raise ValueError("Pointer observation is outside the governed trajectory activation tolerance.")
    first, second = points[index], points[index + 1]
    def value(key: str) -> float | None:
        return _lerp(_number(first, key), _number(second, key), ratio)
    md, tvd, x, y, z = value("md"), value("tvd"), value("x"), value("y"), value("z")
    if md is None or tvd is None or x is None or y is None or z is None:
        raise ValueError("Active trajectory is missing authoritative point fields.")
    return WbvAuthoritativePointV2(
        md=md, tvd=tvd, tvdss=value("tvdss"), inclination=value("inclination"),
        azimuth=value("azimuth"), dogleg_severity=value("dogleg_severity"),
        x=x, y=y, z=z, segment_index=index, segment_ratio=ratio,
        screen_distance_px=distance,
    )
