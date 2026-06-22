"""Per-well canvas binding domain service.

Depends on:
  - WellCanvasBindingRepository (injected — no direct JSON/file access)
  - CurveInventoryLookup (injected abstract interface — no direct inventory access)

Does not modify profile or profile revision records.
Does not write to canonical_sessions_v2_1.json or session_layouts.json.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Literal, NamedTuple

from app.identity import new_uuid7_str

from .binding_models import (
    BindingStatus,
    CurveInventoryRecord,
    WellCanvasBinding,
    WellCanvasSlotBinding,
)
from .binding_repository import (
    LocalJsonWellCanvasBindingRepository,
    WellCanvasBindingNotFound,
    WellCanvasBindingRepository,
    WellCanvasBindingRevisionConflict,
)
from .models import SharedCanvasSlot


# ---------------------------------------------------------------------------
# Inventory abstraction — injected; never coupled to JSON files directly
# ---------------------------------------------------------------------------

class WellDepthRange(NamedTuple):
    """Depth extent for a single well: (depth_min, depth_max, depth_unit).

    Both bounds are measured in *depth_unit*.  depth_max must be strictly
    greater than depth_min; both must be finite.  depth_unit must be nonblank.
    """

    depth_min: float
    depth_max: float
    depth_unit: str


class CurveInventoryLookup(ABC):
    """Narrow inventory interface consumed by the binding and resolution services.

    Concrete implementations may read from the managed inventory, a cache,
    or a test stub.  The service never accesses inventory storage directly.
    """

    @abstractmethod
    def get_curve(self, managed_curve_uid: str) -> CurveInventoryRecord | None:
        """Return a curve record or None if not found."""

    @abstractmethod
    def list_curves_for_well(
        self, managed_well_uid: str
    ) -> list[CurveInventoryRecord]:
        """Return all available curves for a well."""

    @abstractmethod
    def get_well_depth_range(
        self, managed_well_uid: str
    ) -> WellDepthRange | None:
        """Return the depth range for a well, or None if unavailable."""


# ---------------------------------------------------------------------------
# Service exceptions
# ---------------------------------------------------------------------------

class SlotValidationError(ValueError):
    """slot_uid does not belong to the referenced profile revision."""


class CrossWellCurveError(ValueError):
    """managed_curve_uid belongs to a different well than the binding."""


__all__ = [
    "CurveInventoryLookup",
    "SlotValidationError",
    "CrossWellCurveError",
    "WellBindingService",
    "WellCanvasBindingRevisionConflict",
    "WellCanvasBindingNotFound",
]


# ---------------------------------------------------------------------------
# Binding service
# ---------------------------------------------------------------------------

class WellBindingService:
    """Domain service for per-well canvas binding overlays.

    Operations:
      create_binding              — new empty overlay for a well + profile revision
      get_binding                 — retrieve by binding_uid
      get_binding_for_well_and_revision — retrieve by (well, profile revision)
      update_slot_binding         — set one slot's binding state (OCC-guarded)
      unbind_slot                 — explicitly clear one slot (USER_UNBOUND)
      list_bindings_for_well      — all overlays for a well
      list_bindings_for_revision  — all overlays for a profile revision
      check_stale                 — compare overlay's revision to current
      mark_stale                  — set overlay_status to "stale"
      resolve_slot_candidates     — rank inventory candidates for auto-resolution
    """

    def __init__(
        self,
        repository: WellCanvasBindingRepository | None = None,
        inventory: CurveInventoryLookup | None = None,
    ) -> None:
        self._repo = repository or LocalJsonWellCanvasBindingRepository()
        self._inventory = inventory  # None → skip curve-ownership validation

    # --------------------------------------------------------------- create

    def create_binding(
        self,
        *,
        managed_well_uid: str,
        profile_uid: str,
        profile_revision_uid: str,
        profile_revision_number: int,
        slot_bindings: tuple[WellCanvasSlotBinding, ...] = (),
        created_by: str = "system",
    ) -> WellCanvasBinding:
        """Create an empty (or seeded) binding overlay atomically."""
        now = self._now()
        binding = WellCanvasBinding(
            binding_uid=new_uuid7_str(),
            managed_well_uid=managed_well_uid,
            profile_uid=profile_uid,
            profile_revision_uid=profile_revision_uid,
            profile_revision_number=profile_revision_number,
            overlay_status="current",
            slot_bindings=slot_bindings,
            revision=0,
            created_at=now,
            updated_at=now,
            updated_by=created_by,
        )
        self._repo.create_binding(binding)
        return binding

    # ---------------------------------------------------------------- read

    def get_binding(self, binding_uid: str) -> WellCanvasBinding:
        binding = self._repo.get_binding(binding_uid)
        if binding is None:
            raise WellCanvasBindingNotFound(
                f"Binding not found: {binding_uid}"
            )
        return binding

    def get_binding_for_well_and_revision(
        self, managed_well_uid: str, profile_revision_uid: str
    ) -> WellCanvasBinding | None:
        return self._repo.get_binding_for_well_and_revision(
            managed_well_uid, profile_revision_uid
        )

    def list_bindings_for_well(
        self, managed_well_uid: str
    ) -> list[WellCanvasBinding]:
        return self._repo.list_bindings_for_well(managed_well_uid)

    def list_bindings_for_revision(
        self, profile_revision_uid: str
    ) -> list[WellCanvasBinding]:
        return self._repo.list_bindings_for_revision(profile_revision_uid)

    # --------------------------------------------------------------- update

    def update_slot_binding(
        self,
        *,
        binding_uid: str,
        expected_revision: int,
        slot_uid: str,
        binding_status: BindingStatus,
        managed_curve_uid: str | None = None,
        binding_source: Literal[
            "auto_resolved", "user_explicit", "system"
        ] = "user_explicit",
        confidence: float | None = None,
        reason: str | None = None,
        user_override: bool = False,
        updated_by: str = "system",
        valid_slot_uids: frozenset[str] | None = None,
    ) -> WellCanvasBinding:
        """Update one slot's binding state within an overlay.

        valid_slot_uids — when provided, slot_uid must be a member; otherwise
                          SlotValidationError is raised.

        For BOUND status with managed_curve_uid: the curve must belong to the
        overlay's managed_well_uid; otherwise CrossWellCurveError is raised.

        Raises WellCanvasBindingRevisionConflict on OCC mismatch.
        On any failure, the stored binding is not modified.
        """
        binding = self.get_binding(binding_uid)

        if valid_slot_uids is not None and slot_uid not in valid_slot_uids:
            raise SlotValidationError(
                f"slot_uid {slot_uid!r} is not a member of the profile revision "
                f"{binding.profile_revision_uid}"
            )

        if binding_status == BindingStatus.BOUND and managed_curve_uid is not None:
            self._validate_curve_ownership(
                managed_curve_uid=managed_curve_uid,
                expected_well_uid=binding.managed_well_uid,
            )

        new_slot = WellCanvasSlotBinding(
            slot_uid=slot_uid,
            managed_curve_uid=managed_curve_uid,
            binding_status=binding_status,
            binding_source=binding_source,
            confidence=confidence,
            reason=reason,
            user_override=user_override,
        )

        updated_slots = self._replace_or_append_slot(binding.slot_bindings, new_slot)
        updated = binding.model_copy(
            update={
                "slot_bindings": updated_slots,
                "revision": expected_revision + 1,
                "updated_at": self._now(),
                "updated_by": updated_by,
            }
        )
        # Concurrency check and write are atomic inside the repository.
        self._repo.update_binding(updated, expected_revision)
        return updated

    def unbind_slot(
        self,
        *,
        binding_uid: str,
        expected_revision: int,
        slot_uid: str,
        updated_by: str = "system",
        valid_slot_uids: frozenset[str] | None = None,
    ) -> WellCanvasBinding:
        """Explicitly clear one slot to USER_UNBOUND, preserving the decision."""
        return self.update_slot_binding(
            binding_uid=binding_uid,
            expected_revision=expected_revision,
            slot_uid=slot_uid,
            binding_status=BindingStatus.USER_UNBOUND,
            managed_curve_uid=None,
            binding_source="user_explicit",
            user_override=True,
            updated_by=updated_by,
            valid_slot_uids=valid_slot_uids,
        )

    # --------------------------------------------------------- stale detection

    def check_stale(
        self, binding_uid: str, current_revision_uid: str
    ) -> bool:
        """Return True when the binding's profile_revision_uid differs from current."""
        binding = self.get_binding(binding_uid)
        return binding.profile_revision_uid != current_revision_uid

    def mark_stale(
        self,
        binding_uid: str,
        *,
        updated_by: str = "system",
    ) -> WellCanvasBinding:
        """Mark a binding overlay as stale (idempotent)."""
        binding = self.get_binding(binding_uid)
        if binding.overlay_status == "stale":
            return binding
        expected = binding.revision
        updated = binding.model_copy(
            update={
                "overlay_status": "stale",
                "revision": expected + 1,
                "updated_at": self._now(),
                "updated_by": updated_by,
            }
        )
        self._repo.update_binding(updated, expected)
        return updated

    # --------------------------------------------------- resolution helper

    def resolve_slot_candidates(
        self,
        candidates: list[CurveInventoryRecord],
        slot: SharedCanvasSlot,
        managed_well_uid: str,
    ) -> WellCanvasSlotBinding:
        """Rank inventory candidates and return a slot binding.

        Scoring (higher wins):
          +4  curve_family matches slot.expected_curve_family
          +3  kr_curve_type_id matches slot.expected_curve_type
          +2  unit_family matches slot.expected_unit_family

        Returns:
          BOUND        — one candidate scores highest unambiguously
          UNRESOLVED   — multiple candidates share the top score (ambiguous)
          UNAVAILABLE  — no candidates exist for this well
        """
        well_candidates = [
            c for c in candidates if c.managed_well_uid == managed_well_uid
        ]

        if not well_candidates:
            return WellCanvasSlotBinding(
                slot_uid=slot.slot_uid,
                managed_curve_uid=None,
                binding_status=BindingStatus.UNAVAILABLE,
                binding_source="auto_resolved",
                reason="no_candidates_for_well",
            )

        scored = [
            (self._score_candidate(c, slot), c) for c in well_candidates
        ]
        top_score = max(s for s, _ in scored)
        top_candidates = [c for s, c in scored if s == top_score]

        if len(top_candidates) > 1:
            return WellCanvasSlotBinding(
                slot_uid=slot.slot_uid,
                managed_curve_uid=None,
                binding_status=BindingStatus.UNRESOLVED,
                binding_source="auto_resolved",
                reason="ambiguous_candidates",
            )

        chosen = top_candidates[0]
        return WellCanvasSlotBinding(
            slot_uid=slot.slot_uid,
            managed_curve_uid=chosen.managed_curve_uid,
            binding_status=BindingStatus.BOUND,
            binding_source="auto_resolved",
            confidence=min(1.0, top_score / 9.0) if top_score > 0 else 0.1,
        )

    # --------------------------------------------------------------- helpers

    def _validate_curve_ownership(
        self,
        *,
        managed_curve_uid: str,
        expected_well_uid: str,
    ) -> None:
        """Raise CrossWellCurveError if the curve belongs to a different well."""
        if self._inventory is None:
            return  # no inventory injected; caller is responsible for validation
        record = self._inventory.get_curve(managed_curve_uid)
        if record is None:
            raise WellCanvasBindingNotFound(
                f"Curve not found in inventory: {managed_curve_uid}"
            )
        if record.managed_well_uid != expected_well_uid:
            raise CrossWellCurveError(
                f"Curve {managed_curve_uid} belongs to well "
                f"{record.managed_well_uid!r}, not {expected_well_uid!r}"
            )

    @staticmethod
    def _replace_or_append_slot(
        current: tuple[WellCanvasSlotBinding, ...],
        new_slot: WellCanvasSlotBinding,
    ) -> tuple[WellCanvasSlotBinding, ...]:
        """Replace an existing slot binding or append if not present."""
        result = [sb for sb in current if sb.slot_uid != new_slot.slot_uid]
        result.append(new_slot)
        return tuple(result)

    @staticmethod
    def _score_candidate(
        candidate: CurveInventoryRecord, slot: SharedCanvasSlot
    ) -> int:
        score = 0
        if slot.expected_curve_family and candidate.curve_family:
            if candidate.curve_family.lower() == slot.expected_curve_family.lower():
                score += 4
        if slot.expected_curve_type and candidate.kr_curve_type_id:
            if (
                candidate.kr_curve_type_id.lower()
                == slot.expected_curve_type.lower()
            ):
                score += 3
        if slot.expected_unit_family and candidate.unit_family:
            if (
                candidate.unit_family.lower()
                == slot.expected_unit_family.lower()
            ):
                score += 2
        return score

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
