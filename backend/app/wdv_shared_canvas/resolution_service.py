"""Shared canvas session resolution service (Phase 4).

Resolves:
  active shared canvas profile revision
  + per-well binding overlay
  + curve inventory metadata
→ ResolvedWdvCanvasSession (response-only DTO, never persisted)

Contract:
  - Read-only: does not mutate profile, revision, or binding records.
  - Cross-well safe: raises CrossWellCurveError if a bound curve uid belongs
    to a well other than the requested managed_well_uid.
  - Stale-safe: raises StaleBindingError if the binding overlay is stale or
    its profile_revision_uid does not match the active activation.
  - Structurally complete: every shared track and slot is present in the result
    regardless of binding or curve availability.
  - Scale labels: generated through app.wdv_display.number_format.format_scale_value
    at response time; never written to any store.

Does not write to canonical_sessions_v2_1.json, session_layouts.json,
shared_canvas_profiles.json, or well_canvas_bindings.json.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from app.wdv_display.number_format import format_scale_value

from .binding_models import BindingStatus, WellCanvasSlotBinding
from .binding_repository import (
    LocalJsonWellCanvasBindingRepository,
    WellCanvasBindingRepository,
)
from .binding_service import CrossWellCurveError, CurveInventoryLookup, WellDepthRange
from .models import ProfileStatus, SharedCanvasSlot
from .repository import LocalJsonSharedCanvasRepository, SharedCanvasProfileRepository
from .session_models import (
    BindingSummary,
    ResolvedCanvasSlot,
    ResolvedCanvasTrack,
    ResolvedWdvCanvasSession,
)


# ---------------------------------------------------------------------------
# Service exceptions
# ---------------------------------------------------------------------------

class StaleBindingError(ValueError):
    """Raised when the binding overlay is stale or mismatches the active revision.

    Policy: resolution is rejected entirely.  No partial session is returned.
    Callers must refresh the binding (re-run auto-resolution) before retrying.
    """


class MissingBindingError(KeyError):
    """No binding overlay exists for (managed_well_uid, profile_revision_uid)."""


class MissingActiveProfileError(KeyError):
    """No active profile activation for the requested (scope_type, scope_uid)."""


class ArchivedProfileResolutionError(ValueError):
    """The activated profile is archived; archived profiles cannot be resolved."""


class MissingWellDepthRangeError(ValueError):
    """Raised when a valid depth range cannot be obtained for the requested well.

    This includes: inventory not available, inventory returned None, non-finite
    bounds, depth_max <= depth_min, or blank depth_unit.
    """


__all__ = [
    "CanvasResolutionService",
    "StaleBindingError",
    "MissingBindingError",
    "MissingActiveProfileError",
    "ArchivedProfileResolutionError",
    "MissingWellDepthRangeError",
    "CrossWellCurveError",
]


# ---------------------------------------------------------------------------
# Resolution service
# ---------------------------------------------------------------------------

class CanvasResolutionService:
    """Read-only service that produces a ResolvedWdvCanvasSession per request.

    Inject an InMemory repository for unit tests; the local JSON adapters are
    used as defaults for the desktop application.

    Resolution is stateless: each call to resolve() loads fresh data from the
    injected repositories and builds a new DTO.  It never writes to any store.
    """

    def __init__(
        self,
        profile_repository: SharedCanvasProfileRepository | None = None,
        binding_repository: WellCanvasBindingRepository | None = None,
        inventory: CurveInventoryLookup | None = None,
    ) -> None:
        self._profile_repo = profile_repository or LocalJsonSharedCanvasRepository()
        self._binding_repo = binding_repository or LocalJsonWellCanvasBindingRepository()
        self._inventory = inventory  # None → skip curve metadata + ownership check

    # ------------------------------------------------------------------

    def resolve(
        self,
        *,
        managed_well_uid: str,
        scope_type: str,
        scope_uid: str,
    ) -> ResolvedWdvCanvasSession:
        """Resolve the active canvas profile against one well's binding overlay.

        Raises:
            MissingActiveProfileError  — no activation for (scope_type, scope_uid),
                                         or the profile / revision record is absent.
            ArchivedProfileResolutionError — the activated profile is archived.
            MissingBindingError        — no binding for (well, profile revision).
            StaleBindingError          — binding is stale or revision mismatch.
            CrossWellCurveError        — a BOUND slot references a curve from
                                         a different well (requires inventory).
        """
        now = self._now()

        # ── Step 1: activation ──────────────────────────────────────────────
        activation = self._profile_repo.get_activation(scope_type, scope_uid)
        if activation is None:
            raise MissingActiveProfileError(
                f"No active profile for scope ({scope_type!r}, {scope_uid!r})"
            )

        # ── Step 2: profile header ──────────────────────────────────────────
        profile = self._profile_repo.get_profile(activation.profile_uid)
        if profile is None:
            raise MissingActiveProfileError(
                f"Profile record missing: {activation.profile_uid}"
            )
        if profile.status == ProfileStatus.ARCHIVED:
            raise ArchivedProfileResolutionError(
                f"Profile {profile.profile_uid!r} is archived and cannot be resolved"
            )

        # ── Step 3: profile revision ────────────────────────────────────────
        revision = self._profile_repo.get_revision(activation.profile_revision_uid)
        if revision is None:
            raise MissingActiveProfileError(
                f"Profile revision record missing: {activation.profile_revision_uid}"
            )

        # ── Step 4: binding overlay ─────────────────────────────────────────
        binding = self._binding_repo.get_binding_for_well_and_revision(
            managed_well_uid, activation.profile_revision_uid
        )
        if binding is None:
            raise MissingBindingError(
                f"No binding overlay for well {managed_well_uid!r} "
                f"and revision {activation.profile_revision_uid!r}"
            )

        # ── Step 5: stale check ─────────────────────────────────────────────
        # Stale if the overlay was explicitly marked stale, OR if the binding
        # was created against a different revision than the current activation.
        if (
            binding.overlay_status == "stale"
            or binding.profile_revision_uid != activation.profile_revision_uid
        ):
            raise StaleBindingError(
                f"Binding {binding.binding_uid!r} is stale "
                f"(overlay_status={binding.overlay_status!r}, "
                f"binding_revision={binding.profile_revision_uid!r}, "
                f"active_revision={activation.profile_revision_uid!r})"
            )

        # ── Step 6: depth range ─────────────────────────────────────────────
        depth_min, depth_max, depth_unit = self._resolve_depth_range(managed_well_uid)

        # ── Step 7: resolve tracks in profile order ─────────────────────────
        slot_binding_map: dict[str, WellCanvasSlotBinding] = {
            sb.slot_uid: sb for sb in binding.slot_bindings
        }

        resolved_tracks: list[ResolvedCanvasTrack] = []
        all_statuses: list[BindingStatus] = []
        session_warnings: list[str] = []

        for track in sorted(revision.tracks, key=lambda t: t.track_order):
            resolved_slots: list[ResolvedCanvasSlot] = []
            for slot in sorted(track.slots, key=lambda s: s.slot_order):
                resolved_slot = self._resolve_slot(
                    slot=slot,
                    slot_binding_map=slot_binding_map,
                    managed_well_uid=managed_well_uid,
                )
                resolved_slots.append(resolved_slot)
                all_statuses.append(resolved_slot.binding_status)

            resolved_tracks.append(
                ResolvedCanvasTrack(
                    track_uid=track.track_uid,
                    track_key=track.track_key,
                    track_order=track.track_order,
                    track_name=track.track_name,
                    track_type=track.track_type,
                    track_role=track.track_role,
                    renderer_type=track.renderer_type,
                    width_px=track.width_px,
                    lattice=track.lattice,
                    lattice_source=track.lattice_source,
                    scale_mode=track.scale_mode,
                    depth_basis=track.depth_basis,
                    slots=tuple(resolved_slots),
                )
            )

        return ResolvedWdvCanvasSession(
            managed_well_uid=managed_well_uid,
            profile_uid=activation.profile_uid,
            profile_revision_uid=activation.profile_revision_uid,
            profile_revision_number=revision.revision_number,
            activation_scope_type=activation.activation_scope_type,
            activation_scope_uid=activation.activation_scope_uid,
            resolved_tracks=tuple(resolved_tracks),
            binding_summary=self._build_summary(all_statuses),
            warnings=tuple(session_warnings),
            updated_at=now,
            depth_min=depth_min,
            depth_max=depth_max,
            depth_unit=depth_unit,
        )

    # ---------------------------------------------------------------- helpers

    def _resolve_depth_range(self, managed_well_uid: str) -> tuple[float, float, str]:
        """Fetch and validate depth range from inventory.

        Raises MissingWellDepthRangeError if the range is absent or invalid.
        """
        if self._inventory is None:
            raise MissingWellDepthRangeError(
                f"No inventory available to supply depth range for well {managed_well_uid!r}"
            )
        depth_range: WellDepthRange | None = self._inventory.get_well_depth_range(managed_well_uid)
        if depth_range is None:
            raise MissingWellDepthRangeError(
                f"Inventory returned no depth range for well {managed_well_uid!r}"
            )
        depth_min, depth_max, depth_unit = depth_range
        if not math.isfinite(depth_min) or not math.isfinite(depth_max):
            raise MissingWellDepthRangeError(
                f"Depth range for well {managed_well_uid!r} contains non-finite bounds: "
                f"({depth_min}, {depth_max})"
            )
        if depth_max <= depth_min:
            raise MissingWellDepthRangeError(
                f"depth_max ({depth_max}) must be strictly greater than "
                f"depth_min ({depth_min}) for well {managed_well_uid!r}"
            )
        if not depth_unit or not depth_unit.strip():
            raise MissingWellDepthRangeError(
                f"depth_unit must be nonblank for well {managed_well_uid!r}"
            )
        return depth_min, depth_max, depth_unit

    def _resolve_slot(
        self,
        slot: SharedCanvasSlot,
        slot_binding_map: dict[str, WellCanvasSlotBinding],
        managed_well_uid: str,
    ) -> ResolvedCanvasSlot:
        """Resolve one profile slot against the binding map."""
        slot_binding = slot_binding_map.get(slot.slot_uid)

        # No binding entry for this slot — treat as UNAVAILABLE
        if slot_binding is None:
            return ResolvedCanvasSlot(
                slot_uid=slot.slot_uid,
                slot_key=slot.slot_key,
                slot_order=slot.slot_order,
                binding_status=BindingStatus.UNAVAILABLE,
                warnings=("slot_not_in_binding_overlay",),
            )

        # Non-BOUND statuses — return structure with optional reason warning
        if slot_binding.binding_status != BindingStatus.BOUND:
            w = (slot_binding.reason,) if slot_binding.reason else ()
            return ResolvedCanvasSlot(
                slot_uid=slot.slot_uid,
                slot_key=slot.slot_key,
                slot_order=slot.slot_order,
                binding_status=slot_binding.binding_status,
                warnings=w,
            )

        # BOUND — fetch curve metadata and validate ownership
        curve_uid = slot_binding.managed_curve_uid  # guaranteed non-None by model validator
        assert curve_uid is not None  # satisfies type-checker

        record = self._inventory.get_curve(curve_uid) if self._inventory is not None else None

        if record is not None:
            # Cross-well leakage guard
            if record.managed_well_uid != managed_well_uid:
                raise CrossWellCurveError(
                    f"Curve {curve_uid!r} belongs to well {record.managed_well_uid!r}, "
                    f"not the requested well {managed_well_uid!r}"
                )
            scale_min = record.scale_min
            scale_max = record.scale_max
            return ResolvedCanvasSlot(
                slot_uid=slot.slot_uid,
                slot_key=slot.slot_key,
                slot_order=slot.slot_order,
                binding_status=BindingStatus.BOUND,
                managed_curve_uid=curve_uid,
                display_name=record.display_name,
                mnemonic=record.observed_mnemonic,
                curve_family=record.curve_family,
                kr_curve_type_id=record.kr_curve_type_id,
                unit=record.unit,
                scale_min=scale_min,
                scale_max=scale_max,
                scale_min_label=self._safe_label(scale_min),
                scale_max_label=self._safe_label(scale_max),
            )

        # inventory not injected or curve record absent — return uid only
        return ResolvedCanvasSlot(
            slot_uid=slot.slot_uid,
            slot_key=slot.slot_key,
            slot_order=slot.slot_order,
            binding_status=BindingStatus.BOUND,
            managed_curve_uid=curve_uid,
        )

    @staticmethod
    def _safe_label(value: float | None) -> str | None:
        """Call format_scale_value only for finite floats; return None otherwise."""
        if value is None or not math.isfinite(value):
            return None
        return format_scale_value(value)

    @staticmethod
    def _build_summary(statuses: list[BindingStatus]) -> BindingSummary:
        counts: dict[BindingStatus, int] = {s: 0 for s in BindingStatus}
        for s in statuses:
            counts[s] += 1
        return BindingSummary(
            total_slots=len(statuses),
            bound=counts[BindingStatus.BOUND],
            unavailable=counts[BindingStatus.UNAVAILABLE],
            unresolved=counts[BindingStatus.UNRESOLVED],
            excluded=counts[BindingStatus.EXCLUDED],
            incompatible=counts[BindingStatus.INCOMPATIBLE],
            user_unbound=counts[BindingStatus.USER_UNBOUND],
            stale_binding=counts[BindingStatus.STALE_BINDING],
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
