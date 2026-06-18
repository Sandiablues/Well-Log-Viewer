"""Backend-owned 3D Wellbore Viewer contract models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.inventory.models import CanonicalUuid7


class WbvViewerState(str, Enum):
    NOT_LOADED = "not_loaded"
    MISSING_SURVEY = "missing_survey"
    INVALID_SURVEY = "invalid_survey"
    RELATIVE_ONLY = "relative_only"
    AVAILABLE = "available"
    AVAILABLE_VERTICAL = "available_vertical"
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
    trajectory_class: str | None = None
    viewer_state: str | None = None
    station_count: int | None = None
    source_station_count: int | None = None
    fixture_sampling: dict[str, Any] = Field(default_factory=dict)
    stations: list[dict[str, Any]] = Field(default_factory=list)
    render_points: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)


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

class WbvManagedTrajectoryStatus(str, Enum):
    CANDIDATE = "candidate"
    PARSED = "parsed"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    SYNTHETIC_DEMO = "synthetic_demo"


class WbvManagedTrajectoryRecord(BaseModel):
    """Backend-owned managed wellbore geometry record surfaced to MDP/WBV.

    A well may have many records, but only one approved/eligible trajectory is
    active at a time for WBV rendering and WDV correlation.
    """

    trajectory_id: str
    managed_trajectory_uid: CanonicalUuid7 | None = None
    trajectory_revision_uid: CanonicalUuid7 | None = None
    representation_uid: CanonicalUuid7 | None = None
    source_occurrence_uid: CanonicalUuid7 | None = None
    revision_number: int = 1
    revision_fingerprint: str | None = None
    supersedes_trajectory_revision_uid: CanonicalUuid7 | None = None
    trajectory_name: str
    trajectory_type: str = "deviation_survey"
    status: WbvManagedTrajectoryStatus = WbvManagedTrajectoryStatus.CANDIDATE
    wbv_eligible: bool = False
    is_active: bool = False
    is_canonical: bool = False
    is_synthetic: bool = False
    source_file_id: str | None = None
    source_label: str | None = None
    station_count: int | None = None
    md_min: float | None = None
    md_max: float | None = None
    tvd_min: float | None = None
    tvd_max: float | None = None
    geometry_class: str | None = None
    coordinate_mode: WbvCoordinateMode = WbvCoordinateMode.UNAVAILABLE
    trajectory_package: dict[str, Any] = Field(default_factory=dict)
    qa_flags: list[str] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    supersedes_trajectory_id: str | None = None
    created_at: str | None = None
    approved_at: str | None = None


class WbvTrajectoryListContract(BaseModel):
    contract_kind: str = "wbv_trajectory_list"
    contract_version: str = "wbv_trajectory_list_v1"
    viewer: Literal["WBV"] = "WBV"
    managed_well_id: str
    well_id: str
    well_name: str
    active_trajectory_id: str | None = None
    active_trajectory_uid: CanonicalUuid7 | None = None
    geometry_status: str = "missing"
    wbv_ready: bool = False
    trajectories: list[WbvManagedTrajectoryRecord] = Field(default_factory=list)
    warnings: list[WbvWarning] = Field(default_factory=list)


class WbvSetActiveTrajectoryRequest(BaseModel):
    trajectory_id: str | None = None
    trajectory_uid: CanonicalUuid7 | None = None
    requested_by: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def require_trajectory_reference(self) -> "WbvSetActiveTrajectoryRequest":
        if not self.trajectory_uid and not str(self.trajectory_id or "").strip():
            raise ValueError("trajectory_uid or trajectory_id is required")
        return self

    @property
    def canonical_or_legacy_reference(self) -> str:
        return str(self.trajectory_uid or self.trajectory_id)


class WbvSetActiveTrajectoryResponse(BaseModel):
    contract_kind: str = "wbv_set_active_trajectory"
    contract_version: str = "wbv_set_active_trajectory_v1"
    viewer: Literal["WBV"] = "WBV"
    managed_well_id: str
    active_trajectory_id: str
    active_trajectory_uid: CanonicalUuid7 | None = None
    active_trajectory_name: str
    geometry_status: str
    wbv_ready: bool
    trajectories: list[WbvManagedTrajectoryRecord] = Field(default_factory=list)

