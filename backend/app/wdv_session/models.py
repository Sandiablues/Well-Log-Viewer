"""Backend-owned WDV layout/session state models.

These models define the canonical WDV layout/session contract.  The
frontend may render this contract and request explicit user actions, but it
must not own template-application truth or durable layout state.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.inventory.models import CanonicalUuid7


WDV_SESSION_LAYOUT_CONTRACT_VERSION = "wdv_session_layout_state_v1"


class WdvSessionCurveAssignmentState(BaseModel):
    """One curve assignment inside a backend-owned WDV track."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    assignment_id: str = Field(validation_alias=AliasChoices("assignment_id", "assignmentId"))
    managed_product_uid: CanonicalUuid7 | None = Field(default=None, validation_alias=AliasChoices("managed_product_uid", "managedProductUid"))
    managed_curve_uid: CanonicalUuid7 | None = Field(default=None, validation_alias=AliasChoices("managed_curve_uid", "managedCurveUid"))
    managed_well_uid: CanonicalUuid7 | None = Field(default=None, validation_alias=AliasChoices("managed_well_uid", "managedWellUid"))
    managed_wellbore_uid: CanonicalUuid7 | None = Field(default=None, validation_alias=AliasChoices("managed_wellbore_uid", "managedWellboreUid"))
    managed_source_uid: CanonicalUuid7 | None = Field(default=None, validation_alias=AliasChoices("managed_source_uid", "managedSourceUid"))
    curve_uid: str | None = Field(default=None, validation_alias=AliasChoices("curve_uid", "curveUid"))
    well_uid: str | None = Field(default=None, validation_alias=AliasChoices("well_uid", "wellUid", "managed_well_id", "managedWellId"))
    source_uid: str | None = Field(default=None, validation_alias=AliasChoices("source_uid", "sourceUid", "source_id", "sourceId"))
    kr_curve_type_id: str | None = Field(default=None, validation_alias=AliasChoices("kr_curve_type_id", "krCurveTypeId", "canonical_curve_type_id", "canonicalCurveTypeId"))
    observed_mnemonic: str | None = Field(default=None, validation_alias=AliasChoices("observed_mnemonic", "observedMnemonic"))
    normalized_mnemonic: str | None = Field(default=None, validation_alias=AliasChoices("normalized_mnemonic", "normalizedMnemonic"))
    curve_id: str = Field(validation_alias=AliasChoices("curve_id", "curveId"))
    product_id: str | None = Field(default=None, validation_alias=AliasChoices("product_id", "productId"))
    display_curve_id: str | None = Field(default=None, validation_alias=AliasChoices("display_curve_id", "displayCurveId"))
    mnemonic: str | None = None
    display_name: str | None = Field(default=None, validation_alias=AliasChoices("display_name", "displayName"))
    curve_family: str | None = Field(default=None, validation_alias=AliasChoices("curve_family", "curveFamily"))
    unit: str | None = None
    stack_index: int = Field(default=0, validation_alias=AliasChoices("stack_index", "stackIndex"))
    visible: bool = True
    scale_min: float | int | None = Field(default=None, validation_alias=AliasChoices("scale_min", "scaleMin"))
    scale_max: float | int | None = Field(default=None, validation_alias=AliasChoices("scale_max", "scaleMax"))
    scale_type: str | None = Field(default=None, validation_alias=AliasChoices("scale_type", "scaleType"))
    scale_direction: str | None = Field(default=None, validation_alias=AliasChoices("scale_direction", "scaleDirection"))
    color: str | None = None
    source: str = "manual_or_backend_owned"


class WdvSessionTrackLayoutState(BaseModel):
    """One backend-owned WDV display track."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    track_id: str = Field(validation_alias=AliasChoices("track_id", "trackId"))
    track_key: str | None = Field(default=None, validation_alias=AliasChoices("track_key", "trackKey"))
    track_number: int | None = Field(default=None, validation_alias=AliasChoices("track_number", "trackNumber"))
    track_name: str = Field(validation_alias=AliasChoices("track_name", "trackName", "name"))
    track_type: str = Field(default="curve", validation_alias=AliasChoices("track_type", "trackType"))
    renderer_type: str | None = Field(default=None, validation_alias=AliasChoices("renderer_type", "rendererType"))
    track_role: str | None = Field(default=None, validation_alias=AliasChoices("track_role", "trackRole"))
    width_px: int | None = Field(default=None, validation_alias=AliasChoices("width_px", "widthPx"))
    lattice: str | None = None
    lattice_source: str | None = Field(default=None, validation_alias=AliasChoices("lattice_source", "latticeSource"))
    curves: list[WdvSessionCurveAssignmentState] = Field(default_factory=list)
    source_template_key: str | None = Field(default=None, validation_alias=AliasChoices("source_template_key", "sourceTemplateKey"))
    source_application_plan_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("source_application_plan_id", "sourceApplicationPlanId"),
    )


class WdvSessionLayoutStateResponse(BaseModel):
    """Canonical backend-owned WDV layout/session state."""

    service: str = "wdv_session_layout_state_service"
    contract_version: str = WDV_SESSION_LAYOUT_CONTRACT_VERSION
    managed_well_id: str
    managed_well_uid: CanonicalUuid7 | None = None
    layout_session_id: str
    revision: int = 0
    state_status: Literal["empty", "active", "cleared"] = "empty"
    source: str = "backend_owned_session_state"
    updated_at: str
    selected_track_id: str | None = Field(default=None, validation_alias=AliasChoices("selected_track_id", "selectedTrackId"))
    tracks: list[WdvSessionTrackLayoutState] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WdvSessionLayoutPutRequest(BaseModel):
    """Replace the active backend-owned WDV layout for one managed well."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    managed_well_uid: CanonicalUuid7 | None = Field(default=None, validation_alias=AliasChoices("managed_well_uid", "managedWellUid"))
    selected_track_id: str | None = Field(default=None, validation_alias=AliasChoices("selected_track_id", "selectedTrackId"))
    tracks: list[WdvSessionTrackLayoutState] = Field(default_factory=list)
    source: str = "explicit_user_layout_update"


class WdvSessionLayoutClearRequest(BaseModel):
    """Clear the active backend-owned WDV layout for one managed well."""

    reason: str = "user_requested_clear"


# ---------------------------------------------------------------------------
# Response-only DTOs — add display labels after persistence.  These types are
# NEVER written to session_layouts.json.  model_dump() of the durable models
# above will never contain scale_min_label or scale_max_label.
# ---------------------------------------------------------------------------

class WdvSessionCurveAssignmentView(WdvSessionCurveAssignmentState):
    """Outbound response DTO — extends durable with display labels. Never persisted."""

    scale_min_label: str | None = None
    scale_max_label: str | None = None


class WdvSessionTrackLayoutView(WdvSessionTrackLayoutState):
    """Outbound response DTO — overrides curves with View type. Never persisted."""

    curves: list[WdvSessionCurveAssignmentView] = Field(default_factory=list)


class WdvSessionLayoutStateView(WdvSessionLayoutStateResponse):
    """Outbound response DTO — overrides tracks with View type. Never persisted."""

    tracks: list[WdvSessionTrackLayoutView] = Field(default_factory=list)
