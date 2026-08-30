from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, field_validator


class WbvScreenObservationV2(BaseModel):
    """Raw browser observation; never a frontend-derived trajectory answer."""

    pointer_x_px: float
    pointer_y_px: float
    viewport_width_px: float = Field(gt=0)
    viewport_height_px: float = Field(gt=0)
    view_projection_matrix: list[float] = Field(min_length=16, max_length=16)
    activation_tolerance_px: float = Field(default=20.0, gt=0, le=100.0)

    @field_validator("view_projection_matrix")
    @classmethod
    def finite_matrix(cls, value: list[float]) -> list[float]:
        import math
        if not all(math.isfinite(item) for item in value):
            raise ValueError("view_projection_matrix must contain only finite values")
        return value


class WbvAuthoritativePointV2(BaseModel):
    md: float
    tvd: float
    tvdss: float | None = None
    inclination: float | None = None
    azimuth: float | None = None
    dogleg_severity: float | None = None
    x: float
    y: float
    z: float
    segment_index: int
    segment_ratio: float
    screen_distance_px: float


class WbvSavedIntervalV2(BaseModel):
    interval_id: str
    managed_well_id: str
    trajectory_id: str | None = None
    trajectory_revision_uid: str | None = None
    start: WbvAuthoritativePointV2
    end: WbvAuthoritativePointV2
    top_md: float
    base_md: float
    depth_unit: str
    created_at: str
    updated_at: str


class WbvInteractionStateV2(BaseModel):
    contract_kind: Literal["wbv_interaction_state"] = "wbv_interaction_state"
    contract_version: Literal["wbv_interaction_state_v2"] = "wbv_interaction_state_v2"
    managed_well_id: str
    revision: int = 0
    selection_mode: Literal["none", "point", "interval"] = "none"
    selected_point_visible: bool = False
    interval_visible: bool = False
    selected_point: WbvAuthoritativePointV2 | None = None
    interval_draft_start: WbvAuthoritativePointV2 | None = None
    saved_interval: WbvSavedIntervalV2 | None = None
    active_tracking_session_id: str | None = None
    tracking_status: Literal["idle", "tracking", "committed", "cancelled", "expired"] = "idle"
    fallback_status: Literal["none", "backend_unavailable", "trajectory_unavailable", "stale_command"] = "none"
    updated_at: str


class WbvInteractionModeRequestV2(BaseModel):
    mode: Literal["none", "point", "interval"]
    expected_revision: int | None = None


class WbvInteractionObservationV2(BaseModel):
    observation: WbvScreenObservationV2
    expected_revision: int | None = None


class WbvTrackSessionCommandV2(BaseModel):
    session_id: str | None = None
    sequence: int = Field(default=0, ge=0)
    observation: WbvScreenObservationV2 | None = None
    expected_revision: int | None = None


class WbvAoiTransferResultV2(BaseModel):
    contract_kind: Literal["wbv_to_wdv_aoi"] = "wbv_to_wdv_aoi"
    contract_version: Literal["wbv_to_wdv_aoi_v2"] = "wbv_to_wdv_aoi_v2"
    command_status: Literal["applied"] = "applied"
    workspace_id: str
    workspace_revision: int
    managed_well_id: str
    interval_id: str
    top_md: float
    base_md: float
    depth_unit: str
    source_viewer: Literal["WBV"] = "WBV"
    applied_at: str
