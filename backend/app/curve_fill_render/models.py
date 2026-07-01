from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict

from app.curve_fill.models import CurveFillResolveResponse


class CurveFillRenderItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fill_uid: str
    track_uid: str
    owner_assignment_uid: str
    status: Literal["resolved", "disabled", "unresolved"]
    geometry: CurveFillResolveResponse | None = None
    reason_code: str | None = None
    reason: str | None = None


class CurveFillRenderPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["wdv_curve_fill_render_package_v1"] = "wdv_curve_fill_render_package_v1"
    managed_well_uid: str
    session_uid: str
    session_revision: int
    display_policy_revision: str | None = None
    fills: tuple[CurveFillRenderItem, ...]
    warnings: tuple[str, ...] = ()
