"""Backend-owned 3D Wellbore Viewer contract models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class WbvViewerState(str, Enum):
    NOT_LOADED = "not_loaded"
    MISSING_SURVEY = "missing_survey"
    INVALID_SURVEY = "invalid_survey"
    RELATIVE_ONLY = "relative_only"
    AVAILABLE = "available"
    NEEDS_REVIEW = "needs_review"
    UNAVAILABLE = "unavailable"


class WbvCoordinateMode(str, Enum):
    UNAVAILABLE = "unavailable"
    RELATIVE = "relative"
    PROJECTED = "projected"
    GEOGRAPHIC_NORMALIZED = "geographic_normalized"


class WbvWarning(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"] = "warning"
    message: str
    target: str | None = None


class WbvAvailableLayers(BaseModel):
    trajectory: bool = False
    survey_stations: bool = False
    depth_labels: bool = False
    formation_tops: bool = False
    lithology: bool = False
    casing: bool = False
    completions: bool = False
    loaded_curves: bool = False
    curve_attributes: bool = False


class WbvSourceSession(BaseModel):
    contract_kind: str = "wdv_load_session"
    active_viewer_package_id: str | None = None
    loaded_product_count: int = 0
    source_product_ids: list[str] = Field(default_factory=list)
    depth_domain: dict[str, Any] | None = None


class WbvTrajectoryPackage(BaseModel):
    method: str | None = None
    source: str | None = None
    stations: list[dict[str, Any]] = Field(default_factory=list)
    render_points: list[dict[str, Any]] = Field(default_factory=list)


class WbvSessionContract(BaseModel):
    contract_kind: str = "wbv_session"
    contract_version: str = "wbv_session_v1"
    viewer: Literal["WBV"] = "WBV"
    active_managed_well_id: str | None = None
    well_id: str | None = None
    well_name: str | None = None
    viewer_state: WbvViewerState = WbvViewerState.NOT_LOADED
    coordinate_mode: WbvCoordinateMode = WbvCoordinateMode.UNAVAILABLE
    source_session: WbvSourceSession | None = None
    available_layers: WbvAvailableLayers = Field(default_factory=WbvAvailableLayers)
    warnings: list[WbvWarning] = Field(default_factory=list)


class WbvViewerPackageContract(BaseModel):
    contract_kind: str = "wbv_viewer_package"
    contract_version: str = "wbv_viewer_package_v1"
    viewer: Literal["WBV"] = "WBV"
    managed_well_id: str
    well_id: str
    well_name: str
    viewer_state: WbvViewerState
    coordinate_mode: WbvCoordinateMode = WbvCoordinateMode.UNAVAILABLE
    depth_unit: str = "ft"
    angle_unit: str = "deg"
    datum: dict[str, Any] = Field(default_factory=dict)
    crs: dict[str, Any] = Field(default_factory=lambda: {"epsg": None, "status": "not_available"})
    trajectory: WbvTrajectoryPackage = Field(default_factory=WbvTrajectoryPackage)
    bounding_box: dict[str, Any] = Field(default_factory=dict)
    axes: dict[str, Any] = Field(default_factory=dict)
    available_layers: WbvAvailableLayers = Field(default_factory=WbvAvailableLayers)
    markers: list[dict[str, Any]] = Field(default_factory=list)
    intervals: list[dict[str, Any]] = Field(default_factory=list)
    available_attribute_tracks: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[WbvWarning] = Field(default_factory=list)
