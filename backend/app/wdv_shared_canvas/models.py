"""Shared canvas profile domain models.

These models own display structure only.  They must never contain:
  - managed_well_uid
  - managed_curve_uid
  - source-file identity
  - per-well availability state

Per-well curve identity lives exclusively in the binding overlay (binding_models.py).
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.identity import parse_uuid7


SHARED_CANVAS_CONTRACT_VERSION = "shared_canvas_profiles_v1"


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
# Lifecycle
# ---------------------------------------------------------------------------

class ProfileStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# Slot — constraint on what curve family / type belongs in one display position
# ---------------------------------------------------------------------------

class SharedCanvasSlot(BaseModel):
    """One ordered display slot within a shared canvas track.

    Carries curve-family and type constraints for binding resolution.
    Does not carry curve UIDs or well identity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot_uid: CanonicalUuid7
    slot_key: NonBlankString
    slot_order: int = Field(ge=0)
    expected_curve_family: str | None = None
    expected_curve_type: str | None = None     # kr_curve_type_id constraint
    expected_unit_family: str | None = None
    required: bool = True
    allow_multiple: bool = False
    display_policy: Literal["normal", "header_only", "hidden"] = "normal"


# ---------------------------------------------------------------------------
# Track — shared display structure
# ---------------------------------------------------------------------------

class SharedCanvasTrack(BaseModel):
    """One shared canvas track.

    Carries track display structure (order, width, renderer, lattice, scale policy).
    Does not carry curve assignments or well identity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    track_uid: CanonicalUuid7
    track_key: str | None = None
    track_order: int = Field(ge=0)
    track_name: NonBlankString
    track_type: Literal["depth", "curve", "image", "annotation"] = "curve"
    track_role: str | None = None
    renderer_type: str | None = None
    width_px: int | None = Field(default=None, ge=1)
    lattice: Literal["linear", "logarithmic"] | None = None
    lattice_source: str | None = None
    scale_mode: Literal["shared", "per_curve", "dual", "normalized"] = "per_curve"
    depth_basis: Literal["MD", "TVD", "TVDSS"] | None = None
    slots: tuple[SharedCanvasSlot, ...] = ()

    @model_validator(mode="after")
    def validate_track_constraints(self) -> "SharedCanvasTrack":
        if self.track_type == "depth" and self.slots:
            raise ValueError("Depth tracks cannot contain slots")
        if self.depth_basis is not None and self.track_type != "depth":
            raise ValueError("depth_basis is only valid on depth tracks")
        slot_uids = [s.slot_uid for s in self.slots]
        if len(slot_uids) != len(set(slot_uids)):
            raise ValueError("Duplicate slot_uid in SharedCanvasTrack")
        slot_orders = [s.slot_order for s in self.slots]
        if len(slot_orders) != len(set(slot_orders)):
            raise ValueError("Duplicate slot_order in SharedCanvasTrack")
        return self


# ---------------------------------------------------------------------------
# Profile header
# ---------------------------------------------------------------------------

class SharedCanvasProfile(BaseModel):
    """Shared canvas profile header.

    Carries identity, name, and lifecycle state.
    Does not carry tracks — those live in SharedCanvasProfileRevision.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_uid: CanonicalUuid7
    profile_name: NonBlankString
    status: ProfileStatus = ProfileStatus.ACTIVE
    created_at: str
    created_by: NonBlankString
    archived_at: str | None = None
    archived_by: str | None = None


# ---------------------------------------------------------------------------
# Profile revision — immutable snapshot of track structure
# ---------------------------------------------------------------------------

class SharedCanvasProfileRevision(BaseModel):
    """One immutable revision of a shared canvas profile.

    A profile edit always creates a new revision.  Old revisions remain readable.
    profile_uid is stable; profile_revision_uid changes with every revision.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_revision_uid: CanonicalUuid7
    profile_uid: CanonicalUuid7
    revision_number: int = Field(ge=0)
    tracks: tuple[SharedCanvasTrack, ...]
    source_template_key: str | None = None
    previous_revision_uid: CanonicalUuid7 | None = None
    created_at: str
    created_by: NonBlankString
    change_reason: str | None = None

    @model_validator(mode="after")
    def validate_revision_graph(self) -> "SharedCanvasProfileRevision":
        track_uids = [t.track_uid for t in self.tracks]
        if len(track_uids) != len(set(track_uids)):
            raise ValueError("Duplicate track_uid in SharedCanvasProfileRevision")
        track_orders = [t.track_order for t in self.tracks]
        if len(track_orders) != len(set(track_orders)):
            raise ValueError("Duplicate track_order in SharedCanvasProfileRevision")
        if self.revision_number == 0 and self.previous_revision_uid is not None:
            raise ValueError(
                "First revision (revision_number=0) must not reference a previous revision"
            )
        if self.revision_number > 0 and self.previous_revision_uid is None:
            raise ValueError(
                "Subsequent revisions must reference a previous_revision_uid"
            )
        return self


# ---------------------------------------------------------------------------
# Activation — one active profile revision per scope
# ---------------------------------------------------------------------------

class SharedCanvasActivation(BaseModel):
    """Active profile revision for one activation scope.

    Scope examples: ('local_workspace', '<workspace_uid>'),
                    ('user', '<user_uid>'),
                    ('tenant', '<tenant_uid>').

    There is exactly one active profile revision per (scope_type, scope_uid) pair.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    activation_uid: CanonicalUuid7
    activation_scope_type: NonBlankString
    activation_scope_uid: NonBlankString
    profile_uid: CanonicalUuid7
    profile_revision_uid: CanonicalUuid7
    activated_at: str
    activated_by: NonBlankString


# ---------------------------------------------------------------------------
# Audit record
# ---------------------------------------------------------------------------

class SharedCanvasAuditRecord(BaseModel):
    """Minimal backend provenance record for one profile operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_uid: CanonicalUuid7
    actor: NonBlankString
    timestamp: str
    operation: NonBlankString
    profile_uid: CanonicalUuid7
    previous_revision_uid: CanonicalUuid7 | None = None
    resulting_revision_uid: CanonicalUuid7 | None = None
    reason: str | None = None
