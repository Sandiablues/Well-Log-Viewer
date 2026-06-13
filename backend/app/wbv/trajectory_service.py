"""Minimum-curvature trajectory calculation service for WBV.

This module is deliberately independent from inventory persistence. It accepts a
station list, validates it, and returns a backend-owned relative trajectory
package. Later blocks may attach the resulting package to ManagedWellRecord
metadata, but this calculation layer must remain deterministic and testable on
its own.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from .trajectory_models import (
    DeviationSurveyStation,
    NormalizedSurveyStation,
    TrajectoryBoundingBox,
    TrajectoryCalculationMethod,
    TrajectoryCalculationResult,
    TrajectoryCoordinateMode,
    TrajectoryQaqcIssue,
    TrajectoryRenderPoint,
)

_DEPTH_UNIT_ALIASES = {
    "ft": "ft",
    "foot": "ft",
    "feet": "ft",
    "f": "ft",
    "m": "m",
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",
}

_ANGLE_UNIT_ALIASES = {
    "deg": "deg",
    "degree": "deg",
    "degrees": "deg",
    "rad": "rad",
    "radian": "rad",
    "radians": "rad",
}


def calculate_minimum_curvature_trajectory(
    stations: Sequence[DeviationSurveyStation | dict[str, object]],
    *,
    depth_unit: str | None = None,
    angle_unit: str | None = None,
    source: str = "deviation_survey",
) -> TrajectoryCalculationResult:
    """Calculate a relative wellbore trajectory using minimum curvature.

    The returned local coordinate frame is:
    - x: east/west relative offset, positive east
    - y: north/south relative offset, positive north
    - z: negative TVD, suitable for 3D scene coordinates

    The service returns validation warnings instead of fabricating usable output
    when critical inputs are missing or unsafe.
    """

    raw_stations = [_coerce_station(station) for station in stations]
    normalized_depth_unit = _normalize_depth_unit(depth_unit) if depth_unit else None
    normalized_angle_unit = _normalize_angle_unit(angle_unit) if angle_unit else None
    warnings: list[TrajectoryQaqcIssue] = []

    if len(raw_stations) < 2:
        warnings.append(
            TrajectoryQaqcIssue(
                code="insufficient_survey_stations",
                severity="error",
                message="At least two deviation-survey stations are required to calculate a WBV trajectory.",
                target="stations",
            )
        )
        return _invalid_result(depth_unit=normalized_depth_unit or "ft", warnings=warnings, source=source)

    if normalized_depth_unit is None:
        normalized_depth_unit = _infer_depth_unit(raw_stations)
    if normalized_depth_unit is None:
        normalized_depth_unit = "ft"
        warnings.append(
            TrajectoryQaqcIssue(
                code="depth_unit_defaulted",
                severity="warning",
                message="No depth unit was supplied with the survey; defaulted to feet for relative trajectory calculation.",
                target="depth_unit",
            )
        )

    if normalized_angle_unit is None:
        normalized_angle_unit = _infer_angle_unit(raw_stations)
    if normalized_angle_unit is None:
        normalized_angle_unit = "deg"
        warnings.append(
            TrajectoryQaqcIssue(
                code="angle_unit_defaulted",
                severity="warning",
                message="No angle unit was supplied with the survey; defaulted to degrees for trajectory calculation.",
                target="angle_unit",
            )
        )

    unit_errors = _validate_station_units(raw_stations, normalized_depth_unit, normalized_angle_unit)
    warnings.extend(unit_errors)

    normalized, validation_warnings = _normalize_stations(
        raw_stations,
        depth_unit=normalized_depth_unit,
        angle_unit=normalized_angle_unit,
    )
    warnings.extend(validation_warnings)

    has_error = any(issue.severity == "error" for issue in warnings)
    if has_error:
        return _invalid_result(depth_unit=normalized_depth_unit, warnings=warnings, source=source)

    if normalized[0].md != 0.0:
        warnings.append(
            TrajectoryQaqcIssue(
                code="first_station_not_zero",
                severity="warning",
                message="First deviation-survey station is not at MD 0; calculated coordinates are relative to the first station.",
                target="stations[0].md",
            )
        )

    render_points = _calculate_render_points(normalized)
    bounding_box = _bounding_box(render_points)

    return TrajectoryCalculationResult(
        method=TrajectoryCalculationMethod.MINIMUM_CURVATURE,
        source=source,
        coordinate_mode=TrajectoryCoordinateMode.RELATIVE,
        depth_unit=normalized_depth_unit,
        angle_unit="deg",
        stations=normalized,
        render_points=render_points,
        bounding_box=bounding_box,
        warnings=warnings,
        is_valid=True,
    )


def _coerce_station(station: DeviationSurveyStation | dict[str, object]) -> DeviationSurveyStation:
    if isinstance(station, DeviationSurveyStation):
        return station
    return DeviationSurveyStation(**station)


def _normalize_depth_unit(value: str | None) -> str | None:
    if value is None:
        return None
    return _DEPTH_UNIT_ALIASES.get(str(value).strip().lower())


def _normalize_angle_unit(value: str | None) -> str | None:
    if value is None:
        return None
    return _ANGLE_UNIT_ALIASES.get(str(value).strip().lower())


def _infer_depth_unit(stations: Sequence[DeviationSurveyStation]) -> str | None:
    for station in stations:
        unit = _normalize_depth_unit(station.depth_unit)
        if unit:
            return unit
    return None


def _infer_angle_unit(stations: Sequence[DeviationSurveyStation]) -> str | None:
    for station in stations:
        unit = _normalize_angle_unit(station.angle_unit)
        if unit:
            return unit
    return None


def _validate_station_units(
    stations: Sequence[DeviationSurveyStation],
    depth_unit: str,
    angle_unit: str,
) -> list[TrajectoryQaqcIssue]:
    issues: list[TrajectoryQaqcIssue] = []
    for index, station in enumerate(stations):
        station_depth_unit = _normalize_depth_unit(station.depth_unit) if station.depth_unit else depth_unit
        if station_depth_unit is None:
            issues.append(
                TrajectoryQaqcIssue(
                    code="unsupported_depth_unit",
                    severity="error",
                    message=f"Station {index} has unsupported depth unit {station.depth_unit!r}.",
                    target=f"stations[{index}].depth_unit",
                )
            )
        elif station_depth_unit != depth_unit:
            issues.append(
                TrajectoryQaqcIssue(
                    code="inconsistent_depth_unit",
                    severity="error",
                    message=f"Station {index} depth unit {station.depth_unit!r} does not match calculation unit {depth_unit!r}.",
                    target=f"stations[{index}].depth_unit",
                )
            )

        station_angle_unit = _normalize_angle_unit(station.angle_unit) if station.angle_unit else angle_unit
        if station_angle_unit is None:
            issues.append(
                TrajectoryQaqcIssue(
                    code="unsupported_angle_unit",
                    severity="error",
                    message=f"Station {index} has unsupported angle unit {station.angle_unit!r}.",
                    target=f"stations[{index}].angle_unit",
                )
            )
        elif station_angle_unit != angle_unit:
            issues.append(
                TrajectoryQaqcIssue(
                    code="inconsistent_angle_unit",
                    severity="error",
                    message=f"Station {index} angle unit {station.angle_unit!r} does not match calculation unit {angle_unit!r}.",
                    target=f"stations[{index}].angle_unit",
                )
            )
    return issues


def _normalize_stations(
    stations: Sequence[DeviationSurveyStation],
    *,
    depth_unit: str,
    angle_unit: str,
) -> tuple[list[NormalizedSurveyStation], list[TrajectoryQaqcIssue]]:
    normalized: list[NormalizedSurveyStation] = []
    issues: list[TrajectoryQaqcIssue] = []
    previous_md: float | None = None

    for index, station in enumerate(stations):
        target = f"stations[{index}]"
        if not math.isfinite(station.md):
            issues.append(
                TrajectoryQaqcIssue(
                    code="invalid_md",
                    severity="error",
                    message=f"Station {index} MD must be a finite number.",
                    target=f"{target}.md",
                )
            )
            continue
        if station.md < 0:
            issues.append(
                TrajectoryQaqcIssue(
                    code="negative_md",
                    severity="error",
                    message=f"Station {index} MD is negative; WBV trajectory calculation requires non-negative MD.",
                    target=f"{target}.md",
                )
            )
        if previous_md is not None and station.md <= previous_md:
            issues.append(
                TrajectoryQaqcIssue(
                    code="non_monotonic_md",
                    severity="error",
                    message="Deviation-survey MD values must be strictly increasing.",
                    target=f"{target}.md",
                )
            )
        previous_md = station.md

        if station.inclination is None:
            issues.append(
                TrajectoryQaqcIssue(
                    code="missing_inclination",
                    severity="error",
                    message=f"Station {index} is missing inclination.",
                    target=f"{target}.inclination",
                )
            )
            continue
        if station.azimuth is None:
            issues.append(
                TrajectoryQaqcIssue(
                    code="missing_azimuth",
                    severity="error",
                    message=f"Station {index} is missing azimuth.",
                    target=f"{target}.azimuth",
                )
            )
            continue

        inclination = float(station.inclination)
        azimuth = float(station.azimuth)
        if angle_unit == "rad":
            inclination = math.degrees(inclination)
            azimuth = math.degrees(azimuth)

        if not math.isfinite(inclination):
            issues.append(
                TrajectoryQaqcIssue(
                    code="invalid_inclination",
                    severity="error",
                    message=f"Station {index} inclination must be finite.",
                    target=f"{target}.inclination",
                )
            )
        elif inclination < 0.0 or inclination > 180.0:
            issues.append(
                TrajectoryQaqcIssue(
                    code="inclination_out_of_range",
                    severity="error",
                    message=f"Station {index} inclination must be between 0 and 180 degrees.",
                    target=f"{target}.inclination",
                )
            )

        if not math.isfinite(azimuth):
            issues.append(
                TrajectoryQaqcIssue(
                    code="invalid_azimuth",
                    severity="error",
                    message=f"Station {index} azimuth must be finite.",
                    target=f"{target}.azimuth",
                )
            )

        if any(issue.target and issue.target.startswith(target) and issue.severity == "error" for issue in issues):
            continue

        normalized.append(
            NormalizedSurveyStation(
                md=station.md,
                inclination=inclination,
                azimuth=azimuth % 360.0,
                depth_unit=depth_unit,  # type: ignore[arg-type]
                angle_unit="deg",
                source_row=station.source_row,
                source_id=station.source_id,
            )
        )

    if len(normalized) != len(stations):
        issues.append(
            TrajectoryQaqcIssue(
                code="survey_station_validation_failed",
                severity="error",
                message="One or more deviation-survey stations failed validation; no trajectory was calculated.",
                target="stations",
            )
        )

    return normalized, issues


def _calculate_render_points(stations: Sequence[NormalizedSurveyStation]) -> list[TrajectoryRenderPoint]:
    points: list[TrajectoryRenderPoint] = [
        TrajectoryRenderPoint(
            md=stations[0].md,
            tvd=0.0,
            x=0.0,
            y=0.0,
            z=-0.0,
            inclination=stations[0].inclination,
            azimuth=stations[0].azimuth,
            dogleg_severity=0.0,
            source_station_index=0,
        )
    ]

    tvd = 0.0
    x = 0.0
    y = 0.0

    for index in range(1, len(stations)):
        previous = stations[index - 1]
        current = stations[index]
        delta_md = current.md - previous.md

        inc1 = math.radians(previous.inclination)
        inc2 = math.radians(current.inclination)
        azi1 = math.radians(previous.azimuth)
        azi2 = math.radians(current.azimuth)

        dogleg = _dogleg_angle(inc1, inc2, azi1, azi2)
        ratio_factor = _ratio_factor(dogleg)

        delta_tvd = 0.5 * delta_md * (math.cos(inc1) + math.cos(inc2)) * ratio_factor
        delta_north = 0.5 * delta_md * (
            math.sin(inc1) * math.cos(azi1) + math.sin(inc2) * math.cos(azi2)
        ) * ratio_factor
        delta_east = 0.5 * delta_md * (
            math.sin(inc1) * math.sin(azi1) + math.sin(inc2) * math.sin(azi2)
        ) * ratio_factor

        tvd += delta_tvd
        x += delta_east
        y += delta_north
        dogleg_severity = math.degrees(dogleg) / delta_md * 100.0 if delta_md > 0 else 0.0

        points.append(
            TrajectoryRenderPoint(
                md=current.md,
                tvd=tvd,
                x=x,
                y=y,
                z=-tvd,
                inclination=current.inclination,
                azimuth=current.azimuth,
                dogleg_severity=dogleg_severity,
                source_station_index=index,
            )
        )

    return points


def _dogleg_angle(inc1: float, inc2: float, azi1: float, azi2: float) -> float:
    cosine = math.cos(inc1) * math.cos(inc2) + math.sin(inc1) * math.sin(inc2) * math.cos(azi2 - azi1)
    return math.acos(max(-1.0, min(1.0, cosine)))


def _ratio_factor(dogleg: float) -> float:
    if abs(dogleg) < 1.0e-12:
        return 1.0
    return (2.0 / dogleg) * math.tan(dogleg / 2.0)


def _bounding_box(points: Sequence[TrajectoryRenderPoint]) -> TrajectoryBoundingBox:
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    zs = [point.z for point in points]
    mds = [point.md for point in points]
    tvds = [point.tvd for point in points]
    return TrajectoryBoundingBox(
        min_x=min(xs),
        max_x=max(xs),
        min_y=min(ys),
        max_y=max(ys),
        min_z=min(zs),
        max_z=max(zs),
        min_md=min(mds),
        max_md=max(mds),
        min_tvd=min(tvds),
        max_tvd=max(tvds),
    )


def _invalid_result(
    *,
    depth_unit: str,
    warnings: list[TrajectoryQaqcIssue],
    source: str,
) -> TrajectoryCalculationResult:
    return TrajectoryCalculationResult(
        method=TrajectoryCalculationMethod.MINIMUM_CURVATURE,
        source=source,
        coordinate_mode=TrajectoryCoordinateMode.UNAVAILABLE,
        depth_unit=depth_unit,  # type: ignore[arg-type]
        angle_unit="deg",
        stations=[],
        render_points=[],
        bounding_box=None,
        warnings=warnings,
        is_valid=False,
    )
