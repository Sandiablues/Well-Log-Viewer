"""Typed trajectory contracts for the 3D Wellbore Viewer.

These models define the backend-owned deviation-survey and render-ready
trajectory objects used by WBV. They intentionally do not depend on managed
inventory persistence so the calculation layer can be tested and governed before
live ingestion or MSI/WSI attachment is introduced.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class TrajectoryCalculationMethod(str, Enum):
    MINIMUM_CURVATURE = "minimum_curvature"


class TrajectoryCoordinateMode(str, Enum):
    RELATIVE = "relative"
    UNAVAILABLE = "unavailable"


class TrajectoryQaqcIssue(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"] = "warning"
    message: str
    target: str | None = None


class DeviationSurveyStation(BaseModel):
    """Raw deviation-survey station supplied to the calculation service."""

    md: float
    inclination: float | None = None
    azimuth: float | None = None
    depth_unit: str | None = None
    angle_unit: str | None = None
    source_row: int | None = None
    source_id: str | None = None


class NormalizedSurveyStation(BaseModel):
    """Validated survey station normalized for trajectory calculation."""

    md: float
    inclination: float
    azimuth: float
    depth_unit: Literal["ft", "m"]
    angle_unit: Literal["deg"] = "deg"
    source_row: int | None = None
    source_id: str | None = None


class TrajectoryRenderPoint(BaseModel):
    """Render-ready trajectory point in a relative local coordinate frame."""

    md: float
    tvd: float
    tvdss: float | None = None
    x: float
    y: float
    z: float
    inclination: float
    azimuth: float
    dogleg_severity: float = 0.0
    source_station_index: int


class TrajectoryBoundingBox(BaseModel):
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float
    min_md: float
    max_md: float
    min_tvd: float
    max_tvd: float


class TrajectoryCalculationResult(BaseModel):
    contract_kind: str = "wbv_trajectory_calculation"
    contract_version: str = "wbv_trajectory_calculation_v1"
    method: TrajectoryCalculationMethod = TrajectoryCalculationMethod.MINIMUM_CURVATURE
    source: str = "deviation_survey"
    coordinate_mode: TrajectoryCoordinateMode = TrajectoryCoordinateMode.RELATIVE
    depth_unit: Literal["ft", "m"] = "ft"
    angle_unit: Literal["deg"] = "deg"
    stations: list[NormalizedSurveyStation] = Field(default_factory=list)
    render_points: list[TrajectoryRenderPoint] = Field(default_factory=list)
    bounding_box: TrajectoryBoundingBox | None = None
    warnings: list[TrajectoryQaqcIssue] = Field(default_factory=list)
    is_valid: bool = True

    def to_wbv_trajectory_package(self) -> dict[str, object]:
        """Return a dict compatible with the WBV viewer-package trajectory field."""

        return {
            "method": self.method.value,
            "source": self.source,
            "stations": [station.model_dump() for station in self.stations],
            "render_points": [point.model_dump() for point in self.render_points],
        }
