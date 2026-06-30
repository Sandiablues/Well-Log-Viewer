"""Backend-owned complete-LAS reconstruction contracts."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from app.identity.wdv_contract_v2 import CanonicalUuid7, WdvCanonicalSession


class LasReconstructionCurve(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    managed_curve_uid: CanonicalUuid7
    managed_product_uid: CanonicalUuid7
    managed_source_uid: CanonicalUuid7
    product_id: str
    mnemonic: str
    display_name: str
    unit: str | None = None
    curve_family: str | None = None
    source_curve_index: int = Field(ge=0)
    source_curve_position: int = Field(ge=1)
    review_required: bool = False
    selectable: bool = True
    loaded_to_wdv: bool = False


class LasReconstructionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_kind: Literal["wdv_complete_las_reconstruction_plan"] = "wdv_complete_las_reconstruction_plan"
    contract_version: Literal["wdv_complete_las_reconstruction_v1"] = "wdv_complete_las_reconstruction_v1"
    managed_well_uid: CanonicalUuid7
    managed_well_id: str
    well_name: str
    source_id: str
    managed_source_uid: CanonicalUuid7
    original_filename: str
    asset_id: str | None = None
    source_fingerprint: str | None = None
    curve_count: int = Field(ge=0)
    eligible_curve_count: int = Field(ge=0)
    review_curve_count: int = Field(ge=0)
    curves: tuple[LasReconstructionCurve, ...] = ()
    warnings: tuple[str, ...] = ()


class LasSourceOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: str
    managed_source_uid: CanonicalUuid7
    label: str
    original_filename: str
    curve_count: int = Field(ge=0)
    asset_available: bool = False
    source_fingerprint: str | None = None


class LasSourceList(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    managed_well_uid: CanonicalUuid7
    sources: tuple[LasSourceOption, ...] = ()


class LogImageSourceOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: str
    managed_source_uid: CanonicalUuid7
    label: str
    original_filename: str
    file_format: str | None = None
    source_fingerprint: str | None = None


class LogImageSourceList(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    managed_well_uid: CanonicalUuid7
    sources: tuple[LogImageSourceOption, ...] = ()


class LoadCompleteLasCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected_revision: int = Field(ge=0)
    source_id: str = Field(min_length=1)
    command_id: CanonicalUuid7 | None = None
    placement: Literal["inventory_only", "append_tracks"] = "append_tracks"
    include_review_required: bool = False
    skip_existing_assignments: bool = True
    track_width_px: int = Field(default=150, ge=40, le=1200)


class LoadCompleteLasResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plan: LasReconstructionPlan
    loaded_product_ids: tuple[str, ...] = ()
    added_managed_curve_uids: tuple[CanonicalUuid7, ...] = ()
    skipped_existing_managed_curve_uids: tuple[CanonicalUuid7, ...] = ()
    session: WdvCanonicalSession
