"""Response-only resolved canvas session DTOs (Phase 4).

These models are outbound only and must never be persisted as profile
or binding state.

Important invariants:
  - scale_min_label and scale_max_label are generated at response time.
    They are never written to shared_canvas_profiles.json or
    well_canvas_bindings.json — the underlying stored models do not even
    carry those fields.
  - ResolvedWdvCanvasSession is not a WdvCanonicalWorkspace.  It is a
    read-only view produced per-request and discarded after serialisation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .binding_models import BindingStatus


# ---------------------------------------------------------------------------
# Slot — profile structure + per-well binding state + curve display metadata
# ---------------------------------------------------------------------------

class ResolvedCanvasSlot(BaseModel):
    """Resolved slot: profile structure merged with well binding + curve metadata.

    Presence guaranteed regardless of binding_status.
    managed_curve_uid populated only when binding_status is BOUND.
    scale_min_label / scale_max_label are response-only display strings generated
    through the validated number formatter; they are never stored anywhere.
    """

    model_config = ConfigDict(frozen=True)

    slot_uid: str
    slot_key: str
    slot_order: int
    binding_status: BindingStatus

    # Curve identity — only populated when BOUND
    managed_curve_uid: str | None = None

    # Curve display metadata — only populated when BOUND and inventory supplies data
    display_name: str | None = None
    mnemonic: str | None = None
    curve_family: str | None = None
    kr_curve_type_id: str | None = None
    unit: str | None = None

    # Scale — numeric values for plotting, labels for display only
    scale_min: float | None = None
    scale_max: float | None = None
    scale_min_label: str | None = None     # response-only; not persisted
    scale_max_label: str | None = None     # response-only; not persisted

    warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Track — profile track structure with resolved slots
# ---------------------------------------------------------------------------

class ResolvedCanvasTrack(BaseModel):
    """Resolved track: profile track structure preserved regardless of slot availability.

    Track is always present.  Depth tracks carry an empty slots tuple.
    """

    model_config = ConfigDict(frozen=True)

    track_uid: str
    track_key: str | None
    track_order: int
    track_name: str
    track_type: str
    track_role: str | None
    renderer_type: str | None
    width_px: int | None
    lattice: str | None
    lattice_source: str | None
    scale_mode: str
    depth_basis: str | None
    slots: tuple[ResolvedCanvasSlot, ...]


# ---------------------------------------------------------------------------
# Binding summary — slot-level status counts for the resolved session
# ---------------------------------------------------------------------------

class BindingSummary(BaseModel):
    """Counts of each BindingStatus across all slots in the resolved session."""

    model_config = ConfigDict(frozen=True)

    total_slots: int = 0
    bound: int = 0
    unavailable: int = 0
    unresolved: int = 0
    excluded: int = 0
    incompatible: int = 0
    user_unbound: int = 0
    stale_binding: int = 0


# ---------------------------------------------------------------------------
# Resolved session — the top-level outbound DTO
# ---------------------------------------------------------------------------

class ResolvedWdvCanvasSession(BaseModel):
    """Fully resolved canvas session for one well against an active profile revision.

    This is an outbound DTO produced per-request.  It is never persisted.
    Immutable profile structure is copied from the profile revision verbatim.
    Per-well curve metadata is sourced from the injected inventory.
    """

    model_config = ConfigDict(frozen=True)

    managed_well_uid: str
    profile_uid: str
    profile_revision_uid: str
    profile_revision_number: int
    activation_scope_type: str
    activation_scope_uid: str
    resolved_tracks: tuple[ResolvedCanvasTrack, ...]
    binding_summary: BindingSummary
    warnings: tuple[str, ...] = ()
    updated_at: str
