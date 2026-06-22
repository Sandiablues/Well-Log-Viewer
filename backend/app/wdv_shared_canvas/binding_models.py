"""Per-well canvas binding overlay domain models.

These models carry well and curve identity exclusively.
The shared profile and profile revision models must remain
free of managed_well_uid and managed_curve_uid.

BindingStatus describes the state of one slot within a well's binding overlay.
WellCanvasSlotBinding carries the slot-level state and optional curve reference.
WellCanvasBinding is the durable per-well overlay keyed to a profile revision.
CurveInventoryRecord is the lookup result shape used by the binding service.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.identity import parse_uuid7


WELL_CANVAS_BINDING_CONTRACT_VERSION = "well_canvas_bindings_v1"


def _uuid7(value: str) -> str:
    return str(parse_uuid7(value))


def _non_blank(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must not be blank")
    return normalized


CanonicalUuid7 = Annotated[str, AfterValidator(_uuid7)]
NonBlankString = Annotated[str, AfterValidator(_non_blank)]


# ---------------------------------------------------------------------------
# Binding status
# ---------------------------------------------------------------------------

class BindingStatus(str, Enum):
    """Backend-owned state for one canvas slot within a well binding overlay."""

    BOUND = "bound"                  # resolved to a durable curve UID for this well
    UNAVAILABLE = "unavailable"      # well is loaded; curve absent for this well
    UNRESOLVED = "unresolved"        # candidates found but no durable UID confirmed
    EXCLUDED = "excluded"            # explicitly excluded from display
    INCOMPATIBLE = "incompatible"    # unit or family mismatch; not usable
    USER_UNBOUND = "user_unbound"    # user explicitly cleared this slot
    STALE_BINDING = "stale_binding"  # profile revision changed; binding needs review


# ---------------------------------------------------------------------------
# Slot binding
# ---------------------------------------------------------------------------

class WellCanvasSlotBinding(BaseModel):
    """One slot's binding state within a per-well overlay.

    BOUND slots must carry a managed_curve_uid belonging to the overlay's well.
    All other statuses must not carry a managed_curve_uid.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_uid: CanonicalUuid7
    managed_curve_uid: CanonicalUuid7 | None = None
    binding_status: BindingStatus
    binding_source: Literal["auto_resolved", "user_explicit", "system"] = "auto_resolved"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str | None = None
    user_override: bool = False

    @model_validator(mode="after")
    def validate_slot_binding_consistency(self) -> "WellCanvasSlotBinding":
        if self.binding_status == BindingStatus.BOUND:
            if self.managed_curve_uid is None:
                raise ValueError("BOUND slot binding requires managed_curve_uid")
        else:
            if self.managed_curve_uid is not None:
                raise ValueError(
                    f"Non-BOUND slot must not carry managed_curve_uid "
                    f"(status={self.binding_status})"
                )
        return self


# ---------------------------------------------------------------------------
# Well binding overlay
# ---------------------------------------------------------------------------

class WellCanvasBinding(BaseModel):
    """Per-well binding overlay connecting a well's curves to a profile revision.

    revision is an optimistic concurrency counter incremented on every update.
    The shared profile and profile revision models must not be modified
    by any operation on this model.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    binding_uid: CanonicalUuid7
    managed_well_uid: CanonicalUuid7
    profile_uid: CanonicalUuid7
    profile_revision_uid: CanonicalUuid7
    profile_revision_number: int = Field(ge=0)
    overlay_status: Literal["current", "stale", "pending"] = "current"
    slot_bindings: tuple[WellCanvasSlotBinding, ...]
    revision: int = Field(default=0, ge=0)      # optimistic concurrency counter
    created_at: str
    updated_at: str
    updated_by: NonBlankString

    @model_validator(mode="after")
    def validate_binding_graph(self) -> "WellCanvasBinding":
        slot_uids = [sb.slot_uid for sb in self.slot_bindings]
        if len(slot_uids) != len(set(slot_uids)):
            raise ValueError("Duplicate slot_uid in WellCanvasBinding slot_bindings")
        bound = [
            sb for sb in self.slot_bindings
            if sb.binding_status == BindingStatus.BOUND
        ]
        for sb in bound:
            if sb.managed_curve_uid is None:
                raise ValueError(
                    "BOUND slot binding in WellCanvasBinding must have managed_curve_uid"
                )
        return self


# ---------------------------------------------------------------------------
# Inventory lookup shape
# ---------------------------------------------------------------------------

class CurveInventoryRecord(BaseModel):
    """Result shape for curve inventory queries used in binding resolution.

    This is a pure data transfer type.  It does not own inventory storage.
    The concrete inventory source is injected into the binding service.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    managed_curve_uid: CanonicalUuid7
    managed_well_uid: CanonicalUuid7
    curve_family: str | None = None
    kr_curve_type_id: str | None = None
    unit_family: str | None = None
    normalized_mnemonic: str | None = None
    observed_mnemonic: str | None = None
    run: str | None = None
    interval: str | None = None
