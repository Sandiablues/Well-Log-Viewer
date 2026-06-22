"""Tests for CanvasResolutionService (Phase 4 — session resolution).

Covers all 25 required test criteria:
  1.  resolve one well with all slots bound
  2.  preserve profile track order
  3.  preserve profile slot order
  4.  preserve empty track structure (depth track with no slots)
  5.  unavailable slot remains present
  6.  unresolved slot remains present
  7.  excluded slot remains present
  8.  user-unbound slot remains present
  9.  incompatible slot remains present
 10.  bound curve from selected well succeeds
 11.  curve from another well is rejected
 12.  stale binding (overlay_status="stale") is rejected
 13.  profile revision mismatch is rejected (stale check)
 14.  missing binding overlay is handled explicitly
 15.  missing active profile is handled explicitly
 16.  archived profile cannot resolve as active
 17.  numeric scales remain numeric (float)
 18.  scale labels generated through the validated formatter
 19.  no display labels written into profile or binding persistence
 20.  resolution does not mutate profile state
 21.  resolution does not mutate binding state
 22.  different wells resolve the same shared canvas structure
 23.  different wells receive only their own curve UIDs
 24.  one well missing a curve does not alter the other well's resolution
 25.  binding summary counts statuses correctly
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.identity import new_uuid7_str
from app.wdv_display.number_format import format_scale_value
from app.wdv_shared_canvas.binding_models import (
    BindingStatus,
    CurveInventoryRecord,
    WellCanvasBinding,
    WellCanvasSlotBinding,
)
from app.wdv_shared_canvas.binding_repository import (
    WellCanvasBindingNotFound,
    WellCanvasBindingRepository,
    WellCanvasBindingRevisionConflict,
)
from app.wdv_shared_canvas.binding_service import CrossWellCurveError, CurveInventoryLookup, WellDepthRange
from app.wdv_shared_canvas.models import (
    ProfileStatus,
    SharedCanvasActivation,
    SharedCanvasAuditRecord,
    SharedCanvasProfile,
    SharedCanvasProfileRevision,
    SharedCanvasSlot,
    SharedCanvasTrack,
)
from app.wdv_shared_canvas.repository import SharedCanvasProfileRepository
from app.wdv_shared_canvas.resolution_service import (
    ArchivedProfileResolutionError,
    CanvasResolutionService,
    MissingActiveProfileError,
    MissingBindingError,
    MissingWellDepthRangeError,
    StaleBindingError,
)
from app.wdv_shared_canvas.session_models import ResolvedWdvCanvasSession


# ---------------------------------------------------------------------------
# In-memory profile repository stub
# ---------------------------------------------------------------------------

class InMemorySharedCanvasRepository(SharedCanvasProfileRepository):
    """Minimal in-memory profile repository for resolution tests."""

    def __init__(self) -> None:
        self._profiles: dict[str, SharedCanvasProfile] = {}
        self._revisions: dict[str, SharedCanvasProfileRevision] = {}
        self._activations: dict[str, SharedCanvasActivation] = {}
        self._audit: list[SharedCanvasAuditRecord] = []
        self.write_count: int = 0

    # -- direct test helper --
    def seed(
        self,
        profile: SharedCanvasProfile,
        revision: SharedCanvasProfileRevision,
        activation: SharedCanvasActivation | None = None,
    ) -> None:
        self._profiles[profile.profile_uid] = profile
        self._revisions[revision.profile_revision_uid] = revision
        if activation is not None:
            key = f"{activation.activation_scope_type}:{activation.activation_scope_uid}"
            self._activations[key] = activation

    # -- abstract interface --
    def create_profile(self, profile, initial_revision, audit) -> None:
        self.write_count += 1
        self._profiles[profile.profile_uid] = profile
        self._revisions[initial_revision.profile_revision_uid] = initial_revision
        self._audit.append(audit)

    def get_profile(self, profile_uid: str) -> SharedCanvasProfile | None:
        return self._profiles.get(profile_uid)

    def list_profiles(self, include_archived: bool = False) -> list[SharedCanvasProfile]:
        return list(self._profiles.values())

    def update_profile_header(self, profile, audit) -> None:
        self.write_count += 1
        self._profiles[profile.profile_uid] = profile

    def append_revision(self, revision, expected_revision_number, audit) -> None:
        self.write_count += 1
        self._revisions[revision.profile_revision_uid] = revision

    def get_revision(self, profile_revision_uid: str) -> SharedCanvasProfileRevision | None:
        return self._revisions.get(profile_revision_uid)

    def list_revisions(self, profile_uid: str) -> list[SharedCanvasProfileRevision]:
        return [r for r in self._revisions.values() if r.profile_uid == profile_uid]

    def set_activation(self, activation: SharedCanvasActivation) -> None:
        self.write_count += 1
        key = f"{activation.activation_scope_type}:{activation.activation_scope_uid}"
        self._activations[key] = activation

    def get_activation(self, scope_type: str, scope_uid: str) -> SharedCanvasActivation | None:
        return self._activations.get(f"{scope_type}:{scope_uid}")

    def list_activations(self) -> list[SharedCanvasActivation]:
        return list(self._activations.values())

    def append_audit(self, record) -> None:
        self._audit.append(record)


# ---------------------------------------------------------------------------
# In-memory binding repository stub
# ---------------------------------------------------------------------------

class InMemoryWellCanvasBindingRepository(WellCanvasBindingRepository):
    """Minimal in-memory binding repository for resolution tests."""

    def __init__(self) -> None:
        self._bindings: dict[str, WellCanvasBinding] = {}
        self._well_index: dict[str, list[str]] = {}
        self._revision_index: dict[str, list[str]] = {}
        self.write_count: int = 0

    # -- direct test helper --
    def seed(
        self,
        managed_well_uid: str,
        profile_revision_uid: str,
        binding: WellCanvasBinding,
    ) -> None:
        """Insert a binding directly; index under the given (well, rev) pair.

        The binding's internal profile_revision_uid may differ from the index key —
        this allows testing the revision-mismatch stale check.
        """
        self._bindings[binding.binding_uid] = binding
        self._well_index.setdefault(managed_well_uid, []).append(binding.binding_uid)
        self._revision_index.setdefault(profile_revision_uid, []).append(binding.binding_uid)

    # -- abstract interface --
    def create_binding(self, binding: WellCanvasBinding) -> None:
        self.write_count += 1
        self._bindings[binding.binding_uid] = binding
        self._well_index.setdefault(binding.managed_well_uid, []).append(binding.binding_uid)
        self._revision_index.setdefault(binding.profile_revision_uid, []).append(binding.binding_uid)

    def get_binding(self, binding_uid: str) -> WellCanvasBinding | None:
        return self._bindings.get(binding_uid)

    def get_binding_for_well_and_revision(
        self, managed_well_uid: str, profile_revision_uid: str
    ) -> WellCanvasBinding | None:
        for uid in self._well_index.get(managed_well_uid, []):
            b = self._bindings.get(uid)
            if b is not None:
                # Match on the revision_index key (not b.profile_revision_uid) to allow
                # the seeded mismatch scenario for test 13.
                if uid in self._revision_index.get(profile_revision_uid, []):
                    return b
        return None

    def list_bindings_for_well(self, managed_well_uid: str) -> list[WellCanvasBinding]:
        return [self._bindings[u] for u in self._well_index.get(managed_well_uid, []) if u in self._bindings]

    def list_bindings_for_revision(self, profile_revision_uid: str) -> list[WellCanvasBinding]:
        return [self._bindings[u] for u in self._revision_index.get(profile_revision_uid, []) if u in self._bindings]

    def update_binding(self, binding: WellCanvasBinding, expected_revision: int) -> None:
        stored = self._bindings.get(binding.binding_uid)
        if stored is None:
            raise WellCanvasBindingNotFound(binding.binding_uid)
        if stored.revision != expected_revision:
            raise WellCanvasBindingRevisionConflict(f"{expected_revision} != {stored.revision}")
        self.write_count += 1
        self._bindings[binding.binding_uid] = binding


# ---------------------------------------------------------------------------
# Inventory stub
# ---------------------------------------------------------------------------

_DEFAULT_DEPTH_RANGE = WellDepthRange(0.0, 5000.0, "ft")


class StubInventory(CurveInventoryLookup):
    """In-process inventory stub.

    depth_ranges: per-well overrides.  Pass ``{well_uid: None}`` to simulate
    a missing depth range for that well.  Any well not in the dict gets the
    default valid range ``(0.0, 5000.0, "ft")``.
    """

    def __init__(
        self,
        records: list[CurveInventoryRecord],
        depth_ranges: dict[str, WellDepthRange | None] | None = None,
    ) -> None:
        self._by_uid = {r.managed_curve_uid: r for r in records}
        self._depth_ranges: dict[str, WellDepthRange | None] = depth_ranges or {}

    def get_curve(self, managed_curve_uid: str) -> CurveInventoryRecord | None:
        return self._by_uid.get(managed_curve_uid)

    def list_curves_for_well(self, managed_well_uid: str) -> list[CurveInventoryRecord]:
        return [r for r in self._by_uid.values() if r.managed_well_uid == managed_well_uid]

    def get_well_depth_range(self, managed_well_uid: str) -> WellDepthRange | None:
        if managed_well_uid in self._depth_ranges:
            return self._depth_ranges[managed_well_uid]
        return _DEFAULT_DEPTH_RANGE


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

_TS = "2026-01-01T00:00:00+00:00"
_SCOPE_TYPE = "local_workspace"
_SCOPE_UID = "ws-test"


def _profile(uid: str | None = None, status: ProfileStatus = ProfileStatus.ACTIVE) -> SharedCanvasProfile:
    return SharedCanvasProfile(
        profile_uid=uid or new_uuid7_str(),
        profile_name="Test Profile",
        status=status,
        created_at=_TS,
        created_by="test",
    )


def _revision(
    profile_uid: str,
    tracks: tuple[SharedCanvasTrack, ...] = (),
    rev_uid: str | None = None,
    revision_number: int = 0,
) -> SharedCanvasProfileRevision:
    return SharedCanvasProfileRevision(
        profile_revision_uid=rev_uid or new_uuid7_str(),
        profile_uid=profile_uid,
        revision_number=revision_number,
        tracks=tracks,
        created_at=_TS,
        created_by="test",
    )


def _activation(
    profile_uid: str,
    rev_uid: str,
    scope_type: str = _SCOPE_TYPE,
    scope_uid: str = _SCOPE_UID,
) -> SharedCanvasActivation:
    return SharedCanvasActivation(
        activation_uid=new_uuid7_str(),
        activation_scope_type=scope_type,
        activation_scope_uid=scope_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        activated_at=_TS,
        activated_by="test",
    )


def _slot(
    uid: str | None = None,
    key: str = "GR",
    order: int = 0,
    **kwargs,
) -> SharedCanvasSlot:
    return SharedCanvasSlot(
        slot_uid=uid or new_uuid7_str(),
        slot_key=key,
        slot_order=order,
        **kwargs,
    )


def _track(
    uid: str | None = None,
    order: int = 0,
    slots: tuple[SharedCanvasSlot, ...] = (),
    name: str = "Track",
    track_type: str = "curve",
) -> SharedCanvasTrack:
    return SharedCanvasTrack(
        track_uid=uid or new_uuid7_str(),
        track_order=order,
        track_name=name,
        track_type=track_type,
        slots=slots,
    )


def _binding(
    well_uid: str,
    profile_uid: str,
    rev_uid: str,
    slot_bindings: tuple[WellCanvasSlotBinding, ...] = (),
    overlay_status: str = "current",
    revision_uid_override: str | None = None,
) -> WellCanvasBinding:
    now = datetime.now(timezone.utc).isoformat()
    return WellCanvasBinding(
        binding_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=revision_uid_override or rev_uid,
        profile_revision_number=0,
        overlay_status=overlay_status,
        slot_bindings=slot_bindings,
        revision=0,
        created_at=now,
        updated_at=now,
        updated_by="test",
    )


def _slot_binding(
    slot_uid: str,
    status: BindingStatus,
    curve_uid: str | None = None,
    reason: str | None = None,
) -> WellCanvasSlotBinding:
    return WellCanvasSlotBinding(
        slot_uid=slot_uid,
        managed_curve_uid=curve_uid,
        binding_status=status,
        reason=reason,
    )


def _curve(
    curve_uid: str,
    well_uid: str,
    scale_min: float | None = None,
    scale_max: float | None = None,
    **kwargs,
) -> CurveInventoryRecord:
    return CurveInventoryRecord(
        managed_curve_uid=curve_uid,
        managed_well_uid=well_uid,
        scale_min=scale_min,
        scale_max=scale_max,
        **kwargs,
    )


def _make_basic_scene(
    slots: tuple[SharedCanvasSlot, ...] | None = None,
    tracks: tuple[SharedCanvasTrack, ...] | None = None,
    well_uid: str | None = None,
    slot_bindings: tuple[WellCanvasSlotBinding, ...] = (),
    overlay_status: str = "current",
    inventory_records: list[CurveInventoryRecord] | None = None,
    profile_status: ProfileStatus = ProfileStatus.ACTIVE,
) -> tuple[
    CanvasResolutionService,
    InMemorySharedCanvasRepository,
    InMemoryWellCanvasBindingRepository,
    str,   # well_uid
    str,   # profile_uid
    str,   # rev_uid
]:
    """Build a complete in-memory resolution scenario."""
    w = well_uid or new_uuid7_str()
    p_uid = new_uuid7_str()
    r_uid = new_uuid7_str()

    if tracks is None:
        default_slots = slots if slots is not None else ()
        tracks = (_track(slots=default_slots),) if default_slots else ()

    prof = _profile(uid=p_uid, status=profile_status)
    rev = _revision(p_uid, tracks=tracks, rev_uid=r_uid)
    act = _activation(p_uid, r_uid)
    bind = _binding(w, p_uid, r_uid, slot_bindings=slot_bindings, overlay_status=overlay_status)

    profile_repo = InMemorySharedCanvasRepository()
    binding_repo = InMemoryWellCanvasBindingRepository()
    profile_repo.seed(prof, rev, act)
    binding_repo.seed(w, r_uid, bind)

    inv = StubInventory(inventory_records or [])
    svc = CanvasResolutionService(
        profile_repository=profile_repo,
        binding_repository=binding_repo,
        inventory=inv,
    )
    return svc, profile_repo, binding_repo, w, p_uid, r_uid


# ---------------------------------------------------------------------------
# Test 1 — resolve one well with all slots bound
# ---------------------------------------------------------------------------

def test_resolve_all_slots_bound():
    slot_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    well_uid = new_uuid7_str()

    slot = _slot(uid=slot_uid, key="GR", order=0)
    slot_bindings = (_slot_binding(slot_uid, BindingStatus.BOUND, curve_uid=curve_uid),)
    inventory_records = [_curve(curve_uid, well_uid)]

    svc, _, _, w, _, _ = _make_basic_scene(
        slots=(slot,),
        well_uid=well_uid,
        slot_bindings=slot_bindings,
        inventory_records=inventory_records,
    )
    session = svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    assert isinstance(session, ResolvedWdvCanvasSession)
    assert len(session.resolved_tracks) == 1
    resolved_slot = session.resolved_tracks[0].slots[0]
    assert resolved_slot.binding_status == BindingStatus.BOUND
    assert resolved_slot.managed_curve_uid == curve_uid


# ---------------------------------------------------------------------------
# Test 2 — preserve profile track order
# ---------------------------------------------------------------------------

def test_track_order_preserved():
    t0 = _track(order=0, name="First")
    t1 = _track(order=1, name="Second")
    t2 = _track(order=2, name="Third")
    # Feed in reverse order — should come out in profile order
    tracks = (t2, t0, t1)

    svc, _, _, w, _, _ = _make_basic_scene(tracks=tracks, slot_bindings=())
    session = svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    orders = [t.track_order for t in session.resolved_tracks]
    assert orders == [0, 1, 2]
    names = [t.track_name for t in session.resolved_tracks]
    assert names == ["First", "Second", "Third"]


# ---------------------------------------------------------------------------
# Test 3 — preserve profile slot order
# ---------------------------------------------------------------------------

def test_slot_order_preserved():
    slot0 = _slot(order=0, key="GR")
    slot1 = _slot(order=1, key="DT")
    slot2 = _slot(order=2, key="NPHI")
    track = _track(slots=(slot2, slot0, slot1))  # stored out of order
    slot_bindings = (
        _slot_binding(slot0.slot_uid, BindingStatus.UNAVAILABLE),
        _slot_binding(slot1.slot_uid, BindingStatus.UNAVAILABLE),
        _slot_binding(slot2.slot_uid, BindingStatus.UNAVAILABLE),
    )

    svc, _, _, w, _, _ = _make_basic_scene(
        tracks=(track,), slot_bindings=slot_bindings
    )
    session = svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    resolved_orders = [s.slot_order for s in session.resolved_tracks[0].slots]
    assert resolved_orders == [0, 1, 2]


# ---------------------------------------------------------------------------
# Test 4 — preserve empty track structure (depth track with no slots)
# ---------------------------------------------------------------------------

def test_empty_track_structure_preserved():
    depth_track = _track(order=0, name="Depth", track_type="depth")
    curve_track = _track(order=1, name="Curves", slots=())

    svc, _, _, w, _, _ = _make_basic_scene(tracks=(depth_track, curve_track))
    session = svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    assert len(session.resolved_tracks) == 2
    assert session.resolved_tracks[0].track_type == "depth"
    assert session.resolved_tracks[0].slots == ()
    assert session.resolved_tracks[1].track_name == "Curves"


# ---------------------------------------------------------------------------
# Tests 5–9 — non-BOUND statuses are present in the resolved result
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", [
    BindingStatus.UNAVAILABLE,
    BindingStatus.UNRESOLVED,
    BindingStatus.EXCLUDED,
    BindingStatus.USER_UNBOUND,
    BindingStatus.INCOMPATIBLE,
])
def test_non_bound_slot_remains_present(status):
    slot_uid = new_uuid7_str()
    slot = _slot(uid=slot_uid)
    slot_bindings = (_slot_binding(slot_uid, status),)

    svc, _, _, w, _, _ = _make_basic_scene(slots=(slot,), slot_bindings=slot_bindings)
    session = svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    assert len(session.resolved_tracks[0].slots) == 1
    resolved = session.resolved_tracks[0].slots[0]
    assert resolved.slot_uid == slot_uid
    assert resolved.binding_status == status
    assert resolved.managed_curve_uid is None


# ---------------------------------------------------------------------------
# Test 10 — bound curve from selected well succeeds
# ---------------------------------------------------------------------------

def test_bound_curve_same_well_succeeds():
    slot_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    well_uid = new_uuid7_str()
    slot = _slot(uid=slot_uid)
    slot_bindings = (_slot_binding(slot_uid, BindingStatus.BOUND, curve_uid=curve_uid),)
    inventory_records = [_curve(curve_uid, well_uid)]

    svc, _, _, w, _, _ = _make_basic_scene(
        slots=(slot,), well_uid=well_uid, slot_bindings=slot_bindings,
        inventory_records=inventory_records,
    )
    session = svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)
    assert session.resolved_tracks[0].slots[0].managed_curve_uid == curve_uid


# ---------------------------------------------------------------------------
# Test 11 — curve from another well is rejected
# ---------------------------------------------------------------------------

def test_bound_curve_foreign_well_raises():
    slot_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    well_uid = new_uuid7_str()
    foreign_well = new_uuid7_str()
    slot = _slot(uid=slot_uid)
    slot_bindings = (_slot_binding(slot_uid, BindingStatus.BOUND, curve_uid=curve_uid),)
    # Curve is registered under a different well
    inventory_records = [_curve(curve_uid, foreign_well)]

    svc, _, _, w, _, _ = _make_basic_scene(
        slots=(slot,), well_uid=well_uid, slot_bindings=slot_bindings,
        inventory_records=inventory_records,
    )
    with pytest.raises(CrossWellCurveError):
        svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)


# ---------------------------------------------------------------------------
# Test 12 — stale binding (overlay_status="stale") is rejected
# ---------------------------------------------------------------------------

def test_stale_binding_overlay_status_rejected():
    svc, _, _, w, _, _ = _make_basic_scene(overlay_status="stale")
    with pytest.raises(StaleBindingError):
        svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)


# ---------------------------------------------------------------------------
# Test 13 — profile revision mismatch is rejected
# ---------------------------------------------------------------------------

def test_profile_revision_mismatch_rejected():
    """Binding stored with an old rev_uid but indexed under the active rev_uid."""
    old_rev_uid = new_uuid7_str()
    p_uid = new_uuid7_str()
    r_uid = new_uuid7_str()
    w = new_uuid7_str()

    prof = _profile(uid=p_uid)
    rev = _revision(p_uid, rev_uid=r_uid)
    act = _activation(p_uid, r_uid)
    # Binding carries old_rev_uid internally but is indexed under r_uid
    bind = _binding(w, p_uid, r_uid, revision_uid_override=old_rev_uid)

    profile_repo = InMemorySharedCanvasRepository()
    binding_repo = InMemoryWellCanvasBindingRepository()
    profile_repo.seed(prof, rev, act)
    binding_repo.seed(w, r_uid, bind)

    svc = CanvasResolutionService(
        profile_repository=profile_repo,
        binding_repository=binding_repo,
        inventory=StubInventory([]),
    )
    with pytest.raises(StaleBindingError):
        svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)


# ---------------------------------------------------------------------------
# Test 14 — missing binding overlay is handled explicitly
# ---------------------------------------------------------------------------

def test_missing_binding_raises():
    p_uid = new_uuid7_str()
    r_uid = new_uuid7_str()
    w = new_uuid7_str()

    prof = _profile(uid=p_uid)
    rev = _revision(p_uid, rev_uid=r_uid)
    act = _activation(p_uid, r_uid)

    profile_repo = InMemorySharedCanvasRepository()
    binding_repo = InMemoryWellCanvasBindingRepository()  # empty — no binding
    profile_repo.seed(prof, rev, act)

    svc = CanvasResolutionService(
        profile_repository=profile_repo,
        binding_repository=binding_repo,
        inventory=StubInventory([]),
    )
    with pytest.raises(MissingBindingError):
        svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)


# ---------------------------------------------------------------------------
# Test 15 — missing active profile is handled explicitly
# ---------------------------------------------------------------------------

def test_missing_active_profile_raises():
    profile_repo = InMemorySharedCanvasRepository()  # no activation seeded
    binding_repo = InMemoryWellCanvasBindingRepository()
    svc = CanvasResolutionService(
        profile_repository=profile_repo,
        binding_repository=binding_repo,
        inventory=StubInventory([]),
    )
    with pytest.raises(MissingActiveProfileError):
        svc.resolve(
            managed_well_uid=new_uuid7_str(),
            scope_type=_SCOPE_TYPE,
            scope_uid=_SCOPE_UID,
        )


# ---------------------------------------------------------------------------
# Test 16 — archived profile cannot resolve as active
# ---------------------------------------------------------------------------

def test_archived_profile_cannot_resolve():
    svc, _, _, w, _, _ = _make_basic_scene(
        profile_status=ProfileStatus.ARCHIVED
    )
    with pytest.raises(ArchivedProfileResolutionError):
        svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)


# ---------------------------------------------------------------------------
# Test 17 — numeric scales remain numeric (float)
# ---------------------------------------------------------------------------

def test_numeric_scales_are_float():
    slot_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    well_uid = new_uuid7_str()
    slot = _slot(uid=slot_uid)
    slot_bindings = (_slot_binding(slot_uid, BindingStatus.BOUND, curve_uid=curve_uid),)
    inventory_records = [_curve(curve_uid, well_uid, scale_min=0.0, scale_max=150.0)]

    svc, _, _, w, _, _ = _make_basic_scene(
        slots=(slot,), well_uid=well_uid, slot_bindings=slot_bindings,
        inventory_records=inventory_records,
    )
    session = svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)
    rs = session.resolved_tracks[0].slots[0]
    assert isinstance(rs.scale_min, float)
    assert isinstance(rs.scale_max, float)
    assert rs.scale_min == 0.0
    assert rs.scale_max == 150.0


# ---------------------------------------------------------------------------
# Test 18 — scale labels generated through the validated formatter
# ---------------------------------------------------------------------------

def test_scale_labels_use_validated_formatter():
    slot_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    well_uid = new_uuid7_str()
    scale_min, scale_max = 0.5, 38.86
    slot = _slot(uid=slot_uid)
    slot_bindings = (_slot_binding(slot_uid, BindingStatus.BOUND, curve_uid=curve_uid),)
    inventory_records = [_curve(curve_uid, well_uid, scale_min=scale_min, scale_max=scale_max)]

    svc, _, _, w, _, _ = _make_basic_scene(
        slots=(slot,), well_uid=well_uid, slot_bindings=slot_bindings,
        inventory_records=inventory_records,
    )
    session = svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)
    rs = session.resolved_tracks[0].slots[0]
    assert rs.scale_min_label == format_scale_value(scale_min)
    assert rs.scale_max_label == format_scale_value(scale_max)


# ---------------------------------------------------------------------------
# Test 19 — no display labels written into profile or binding persistence
# ---------------------------------------------------------------------------

def test_scale_labels_not_written_to_persistence():
    """Resolution must not call any write method on profile or binding repos."""
    slot_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    well_uid = new_uuid7_str()
    slot = _slot(uid=slot_uid)
    slot_bindings = (_slot_binding(slot_uid, BindingStatus.BOUND, curve_uid=curve_uid),)
    inventory_records = [_curve(curve_uid, well_uid, scale_min=1.0, scale_max=100.0)]

    svc, profile_repo, binding_repo, w, _, _ = _make_basic_scene(
        slots=(slot,), well_uid=well_uid, slot_bindings=slot_bindings,
        inventory_records=inventory_records,
    )
    before_profile_writes = profile_repo.write_count
    before_binding_writes = binding_repo.write_count

    svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    assert profile_repo.write_count == before_profile_writes, "profile repo was written during resolution"
    assert binding_repo.write_count == before_binding_writes, "binding repo was written during resolution"


# ---------------------------------------------------------------------------
# Test 20 — resolution does not mutate profile state
# ---------------------------------------------------------------------------

def test_resolution_does_not_mutate_profile():
    svc, profile_repo, _, w, p_uid, r_uid = _make_basic_scene()
    revision_before = profile_repo.get_revision(r_uid)
    profile_before = profile_repo.get_profile(p_uid)

    svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    assert profile_repo.get_revision(r_uid) is revision_before
    assert profile_repo.get_profile(p_uid) is profile_before


# ---------------------------------------------------------------------------
# Test 21 — resolution does not mutate binding state
# ---------------------------------------------------------------------------

def test_resolution_does_not_mutate_binding():
    slot_uid = new_uuid7_str()
    slot = _slot(uid=slot_uid)
    slot_bindings = (_slot_binding(slot_uid, BindingStatus.UNAVAILABLE),)

    svc, _, binding_repo, w, _, r_uid = _make_basic_scene(
        slots=(slot,), slot_bindings=slot_bindings
    )
    bindings_before = binding_repo.list_bindings_for_revision(r_uid)
    revision_before = bindings_before[0].revision

    svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    bindings_after = binding_repo.list_bindings_for_revision(r_uid)
    assert bindings_after[0].revision == revision_before


# ---------------------------------------------------------------------------
# Tests 22–24 — multi-well resolution
# ---------------------------------------------------------------------------

def _build_multi_well_scene(
    slot_uid: str,
    well_a: str,
    curve_a: str,
    well_b: str,
    curve_b: str,
):
    """Shared profile + two well bindings + per-well inventory."""
    p_uid = new_uuid7_str()
    r_uid = new_uuid7_str()
    slot = _slot(uid=slot_uid)
    track = _track(slots=(slot,))

    prof = _profile(uid=p_uid)
    rev = _revision(p_uid, tracks=(track,), rev_uid=r_uid)
    act = _activation(p_uid, r_uid)

    binding_a = _binding(
        well_a, p_uid, r_uid,
        slot_bindings=(_slot_binding(slot_uid, BindingStatus.BOUND, curve_uid=curve_a),),
    )
    binding_b = _binding(
        well_b, p_uid, r_uid,
        slot_bindings=(_slot_binding(slot_uid, BindingStatus.BOUND, curve_uid=curve_b),),
    )

    profile_repo = InMemorySharedCanvasRepository()
    binding_repo = InMemoryWellCanvasBindingRepository()
    profile_repo.seed(prof, rev, act)
    binding_repo.seed(well_a, r_uid, binding_a)
    binding_repo.seed(well_b, r_uid, binding_b)

    inv = StubInventory([
        _curve(curve_a, well_a),
        _curve(curve_b, well_b),
    ])
    svc = CanvasResolutionService(
        profile_repository=profile_repo,
        binding_repository=binding_repo,
        inventory=inv,
    )
    return svc


def test_two_wells_same_canvas_structure():
    """Test 22 — different wells resolve the same shared canvas structure."""
    slot_uid = new_uuid7_str()
    well_a, well_b = new_uuid7_str(), new_uuid7_str()
    curve_a, curve_b = new_uuid7_str(), new_uuid7_str()
    svc = _build_multi_well_scene(slot_uid, well_a, curve_a, well_b, curve_b)

    session_a = svc.resolve(managed_well_uid=well_a, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)
    session_b = svc.resolve(managed_well_uid=well_b, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    # Same structural shape
    assert len(session_a.resolved_tracks) == len(session_b.resolved_tracks)
    assert len(session_a.resolved_tracks[0].slots) == len(session_b.resolved_tracks[0].slots)
    assert session_a.profile_revision_uid == session_b.profile_revision_uid


def test_two_wells_own_curve_uids():
    """Test 23 — each well's resolved slots carry only that well's curve UIDs."""
    slot_uid = new_uuid7_str()
    well_a, well_b = new_uuid7_str(), new_uuid7_str()
    curve_a, curve_b = new_uuid7_str(), new_uuid7_str()
    svc = _build_multi_well_scene(slot_uid, well_a, curve_a, well_b, curve_b)

    session_a = svc.resolve(managed_well_uid=well_a, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)
    session_b = svc.resolve(managed_well_uid=well_b, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    uid_a = session_a.resolved_tracks[0].slots[0].managed_curve_uid
    uid_b = session_b.resolved_tracks[0].slots[0].managed_curve_uid
    assert uid_a == curve_a
    assert uid_b == curve_b
    assert uid_a != uid_b


def test_one_well_missing_curve_does_not_affect_other():
    """Test 24 — well B missing a curve leaves well A's resolution unaffected."""
    slot_uid = new_uuid7_str()
    well_a, well_b = new_uuid7_str(), new_uuid7_str()
    curve_a = new_uuid7_str()
    p_uid = new_uuid7_str()
    r_uid = new_uuid7_str()

    slot = _slot(uid=slot_uid)
    track = _track(slots=(slot,))
    prof = _profile(uid=p_uid)
    rev = _revision(p_uid, tracks=(track,), rev_uid=r_uid)
    act = _activation(p_uid, r_uid)

    binding_a = _binding(
        well_a, p_uid, r_uid,
        slot_bindings=(_slot_binding(slot_uid, BindingStatus.BOUND, curve_uid=curve_a),),
    )
    binding_b = _binding(
        well_b, p_uid, r_uid,
        slot_bindings=(_slot_binding(slot_uid, BindingStatus.UNAVAILABLE),),
    )

    profile_repo = InMemorySharedCanvasRepository()
    binding_repo = InMemoryWellCanvasBindingRepository()
    profile_repo.seed(prof, rev, act)
    binding_repo.seed(well_a, r_uid, binding_a)
    binding_repo.seed(well_b, r_uid, binding_b)

    inv = StubInventory([_curve(curve_a, well_a)])
    svc = CanvasResolutionService(
        profile_repository=profile_repo,
        binding_repository=binding_repo,
        inventory=inv,
    )

    session_a = svc.resolve(managed_well_uid=well_a, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)
    session_b = svc.resolve(managed_well_uid=well_b, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    # Well A: BOUND with its curve
    assert session_a.resolved_tracks[0].slots[0].binding_status == BindingStatus.BOUND
    assert session_a.resolved_tracks[0].slots[0].managed_curve_uid == curve_a

    # Well B: UNAVAILABLE — track and slot still present
    assert len(session_b.resolved_tracks) == 1
    assert session_b.resolved_tracks[0].slots[0].binding_status == BindingStatus.UNAVAILABLE


# ---------------------------------------------------------------------------
# Test 25 — binding summary counts statuses correctly
# ---------------------------------------------------------------------------

def test_binding_summary_counts():
    s_bound = new_uuid7_str()
    s_unavail = new_uuid7_str()
    s_unresolved = new_uuid7_str()
    s_excluded = new_uuid7_str()
    curve_uid = new_uuid7_str()
    well_uid = new_uuid7_str()

    slots = (
        _slot(uid=s_bound, order=0),
        _slot(uid=s_unavail, order=1),
        _slot(uid=s_unresolved, order=2),
        _slot(uid=s_excluded, order=3),
    )
    slot_bindings = (
        _slot_binding(s_bound, BindingStatus.BOUND, curve_uid=curve_uid),
        _slot_binding(s_unavail, BindingStatus.UNAVAILABLE),
        _slot_binding(s_unresolved, BindingStatus.UNRESOLVED),
        _slot_binding(s_excluded, BindingStatus.EXCLUDED),
    )
    inventory_records = [_curve(curve_uid, well_uid)]

    svc, _, _, w, _, _ = _make_basic_scene(
        slots=slots,
        well_uid=well_uid,
        slot_bindings=slot_bindings,
        inventory_records=inventory_records,
    )
    session = svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    summary = session.binding_summary
    assert summary.total_slots == 4
    assert summary.bound == 1
    assert summary.unavailable == 1
    assert summary.unresolved == 1
    assert summary.excluded == 1
    assert summary.user_unbound == 0
    assert summary.incompatible == 0


# ---------------------------------------------------------------------------
# Tests 26–30 — depth-range amendment
# ---------------------------------------------------------------------------

def test_depth_range_present_in_resolved_session():
    """Test 26 — valid depth range appears verbatim in the resolved session."""
    svc, _, _, w, _, _ = _make_basic_scene()
    session = svc.resolve(managed_well_uid=w, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    assert session.depth_min == 0.0
    assert session.depth_max == 5000.0
    assert session.depth_unit == "ft"


def test_custom_depth_range_in_resolved_session():
    """Test 27 — custom per-well depth range propagates correctly."""
    well_uid = new_uuid7_str()
    custom_range = WellDepthRange(100.5, 3200.0, "m")

    p_uid = new_uuid7_str()
    r_uid = new_uuid7_str()
    prof = _profile(uid=p_uid)
    rev = _revision(p_uid, rev_uid=r_uid)
    act = _activation(p_uid, r_uid)
    bind = _binding(well_uid, p_uid, r_uid)

    profile_repo = InMemorySharedCanvasRepository()
    binding_repo = InMemoryWellCanvasBindingRepository()
    profile_repo.seed(prof, rev, act)
    binding_repo.seed(well_uid, r_uid, bind)

    inv = StubInventory([], depth_ranges={well_uid: custom_range})
    svc = CanvasResolutionService(
        profile_repository=profile_repo,
        binding_repository=binding_repo,
        inventory=inv,
    )
    session = svc.resolve(managed_well_uid=well_uid, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)

    assert session.depth_min == 100.5
    assert session.depth_max == 3200.0
    assert session.depth_unit == "m"


def test_missing_depth_range_raises():
    """Test 28 — inventory returning None raises MissingWellDepthRangeError."""
    well_uid = new_uuid7_str()
    p_uid = new_uuid7_str()
    r_uid = new_uuid7_str()
    prof = _profile(uid=p_uid)
    rev = _revision(p_uid, rev_uid=r_uid)
    act = _activation(p_uid, r_uid)
    bind = _binding(well_uid, p_uid, r_uid)

    profile_repo = InMemorySharedCanvasRepository()
    binding_repo = InMemoryWellCanvasBindingRepository()
    profile_repo.seed(prof, rev, act)
    binding_repo.seed(well_uid, r_uid, bind)

    inv = StubInventory([], depth_ranges={well_uid: None})
    svc = CanvasResolutionService(
        profile_repository=profile_repo,
        binding_repository=binding_repo,
        inventory=inv,
    )
    with pytest.raises(MissingWellDepthRangeError):
        svc.resolve(managed_well_uid=well_uid, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)


def test_reversed_depth_range_raises():
    """Test 29 — depth_max <= depth_min raises MissingWellDepthRangeError."""
    well_uid = new_uuid7_str()
    reversed_range = WellDepthRange(5000.0, 0.0, "ft")  # max < min

    p_uid = new_uuid7_str()
    r_uid = new_uuid7_str()
    prof = _profile(uid=p_uid)
    rev = _revision(p_uid, rev_uid=r_uid)
    act = _activation(p_uid, r_uid)
    bind = _binding(well_uid, p_uid, r_uid)

    profile_repo = InMemorySharedCanvasRepository()
    binding_repo = InMemoryWellCanvasBindingRepository()
    profile_repo.seed(prof, rev, act)
    binding_repo.seed(well_uid, r_uid, bind)

    inv = StubInventory([], depth_ranges={well_uid: reversed_range})
    svc = CanvasResolutionService(
        profile_repository=profile_repo,
        binding_repository=binding_repo,
        inventory=inv,
    )
    with pytest.raises(MissingWellDepthRangeError):
        svc.resolve(managed_well_uid=well_uid, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)


def test_blank_depth_unit_raises():
    """Test 30 — blank depth_unit raises MissingWellDepthRangeError."""
    well_uid = new_uuid7_str()
    blank_unit_range = WellDepthRange(0.0, 5000.0, "   ")  # whitespace-only unit

    p_uid = new_uuid7_str()
    r_uid = new_uuid7_str()
    prof = _profile(uid=p_uid)
    rev = _revision(p_uid, rev_uid=r_uid)
    act = _activation(p_uid, r_uid)
    bind = _binding(well_uid, p_uid, r_uid)

    profile_repo = InMemorySharedCanvasRepository()
    binding_repo = InMemoryWellCanvasBindingRepository()
    profile_repo.seed(prof, rev, act)
    binding_repo.seed(well_uid, r_uid, bind)

    inv = StubInventory([], depth_ranges={well_uid: blank_unit_range})
    svc = CanvasResolutionService(
        profile_repository=profile_repo,
        binding_repository=binding_repo,
        inventory=inv,
    )
    with pytest.raises(MissingWellDepthRangeError):
        svc.resolve(managed_well_uid=well_uid, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID)
