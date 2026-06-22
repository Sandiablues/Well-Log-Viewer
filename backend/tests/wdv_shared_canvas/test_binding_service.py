"""Tests for WellBindingService (Phase 3 — per-well binding layer).

Covers all 20 required test criteria:
  1.  create_binding — returns WellCanvasBinding with revision=0
  2.  get_binding — retrieves by binding_uid
  3.  get_binding — raises WellCanvasBindingNotFound for unknown uid
  4.  get_binding_for_well_and_revision — returns None when not found
  5.  get_binding_for_well_and_revision — returns binding for matching (well, rev)
  6.  update_slot_binding — sets BOUND status with curve uid
  7.  update_slot_binding — increments revision counter
  8.  update_slot_binding — raises WellCanvasBindingRevisionConflict on stale revision
  9.  update_slot_binding — raises SlotValidationError when slot_uid not in valid set
 10.  update_slot_binding — raises CrossWellCurveError when curve belongs to another well
 11.  unbind_slot — sets USER_UNBOUND status, clears curve uid
 12.  unbind_slot — sets user_override=True
 13.  list_bindings_for_well — returns all overlays for a well
 14.  list_bindings_for_revision — returns all overlays for a profile revision
 15.  check_stale — returns True when revision uid differs
 16.  check_stale — returns False when revision uid matches
 17.  mark_stale — sets overlay_status to "stale"
 18.  mark_stale — is idempotent (calling twice does not error; revision increments once)
 19.  resolve_slot_candidates — returns BOUND for unambiguous top-scoring candidate
 20.  resolve_slot_candidates — UNRESOLVED for tied candidates; UNAVAILABLE when none
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.identity import new_uuid7_str
from app.wdv_shared_canvas.binding_models import (
    BindingStatus,
    CurveInventoryRecord,
    WellCanvasBinding,
    WellCanvasSlotBinding,
)
from app.wdv_shared_canvas.binding_repository import (
    LocalJsonWellCanvasBindingRepository,
    WellCanvasBindingNotFound,
    WellCanvasBindingRepository,
    WellCanvasBindingRevisionConflict,
)
from app.wdv_shared_canvas.binding_service import (
    CrossWellCurveError,
    CurveInventoryLookup,
    SlotValidationError,
    WellBindingService,
)
from app.wdv_shared_canvas.models import SharedCanvasSlot


# ---------------------------------------------------------------------------
# In-memory repository — used for all tests
# ---------------------------------------------------------------------------

class InMemoryWellCanvasBindingRepository(WellCanvasBindingRepository):
    """Fast, isolated in-memory implementation for unit tests."""

    def __init__(self) -> None:
        self._bindings: dict[str, WellCanvasBinding] = {}
        self._well_index: dict[str, list[str]] = {}
        self._revision_index: dict[str, list[str]] = {}

    def create_binding(self, binding: WellCanvasBinding) -> None:
        if binding.binding_uid in self._bindings:
            raise ValueError(f"Binding {binding.binding_uid} already exists")
        self._bindings[binding.binding_uid] = binding
        self._well_index.setdefault(binding.managed_well_uid, []).append(
            binding.binding_uid
        )
        self._revision_index.setdefault(binding.profile_revision_uid, []).append(
            binding.binding_uid
        )

    def get_binding(self, binding_uid: str) -> WellCanvasBinding | None:
        return self._bindings.get(binding_uid)

    def get_binding_for_well_and_revision(
        self, managed_well_uid: str, profile_revision_uid: str
    ) -> WellCanvasBinding | None:
        for uid in self._well_index.get(managed_well_uid, []):
            b = self._bindings.get(uid)
            if b is not None and b.profile_revision_uid == profile_revision_uid:
                return b
        return None

    def list_bindings_for_well(self, managed_well_uid: str) -> list[WellCanvasBinding]:
        return [
            self._bindings[uid]
            for uid in self._well_index.get(managed_well_uid, [])
            if uid in self._bindings
        ]

    def list_bindings_for_revision(
        self, profile_revision_uid: str
    ) -> list[WellCanvasBinding]:
        return [
            self._bindings[uid]
            for uid in self._revision_index.get(profile_revision_uid, [])
            if uid in self._bindings
        ]

    def update_binding(
        self, binding: WellCanvasBinding, expected_revision: int
    ) -> None:
        stored = self._bindings.get(binding.binding_uid)
        if stored is None:
            raise WellCanvasBindingNotFound(
                f"Binding not found: {binding.binding_uid}"
            )
        if stored.revision != expected_revision:
            raise WellCanvasBindingRevisionConflict(
                f"Expected revision {expected_revision}, found {stored.revision}"
            )
        self._bindings[binding.binding_uid] = binding


# ---------------------------------------------------------------------------
# In-memory inventory stub
# ---------------------------------------------------------------------------

class StubInventory(CurveInventoryLookup):
    """Test stub for CurveInventoryLookup."""

    def __init__(self, records: list[CurveInventoryRecord]) -> None:
        self._by_uid: dict[str, CurveInventoryRecord] = {
            r.managed_curve_uid: r for r in records
        }
        self._by_well: dict[str, list[CurveInventoryRecord]] = {}
        for r in records:
            self._by_well.setdefault(r.managed_well_uid, []).append(r)

    def get_curve(self, managed_curve_uid: str) -> CurveInventoryRecord | None:
        return self._by_uid.get(managed_curve_uid)

    def list_curves_for_well(
        self, managed_well_uid: str
    ) -> list[CurveInventoryRecord]:
        return self._by_well.get(managed_well_uid, [])

    def get_well_depth_range(self, managed_well_uid: str):  # type: ignore[override]
        return None  # never called by WellBindingService; required by ABC


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo() -> InMemoryWellCanvasBindingRepository:
    return InMemoryWellCanvasBindingRepository()


@pytest.fixture
def svc(repo: InMemoryWellCanvasBindingRepository) -> WellBindingService:
    return WellBindingService(repository=repo, inventory=None)


@pytest.fixture
def well_uid() -> str:
    return new_uuid7_str()


@pytest.fixture
def profile_uid() -> str:
    return new_uuid7_str()


@pytest.fixture
def rev_uid() -> str:
    return new_uuid7_str()


@pytest.fixture
def slot_uid() -> str:
    return new_uuid7_str()


@pytest.fixture
def curve_uid() -> str:
    return new_uuid7_str()


def _make_slot(slot_uid: str, **kwargs) -> SharedCanvasSlot:
    return SharedCanvasSlot(
        slot_uid=slot_uid,
        slot_key="GR",
        slot_order=0,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Test 1 — create_binding returns WellCanvasBinding with revision=0
# ---------------------------------------------------------------------------

def test_create_binding_revision_zero(svc, well_uid, profile_uid, rev_uid):
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
        created_by="test",
    )
    assert isinstance(binding, WellCanvasBinding)
    assert binding.revision == 0
    assert binding.overlay_status == "current"
    assert binding.managed_well_uid == well_uid
    assert binding.profile_revision_uid == rev_uid
    assert binding.slot_bindings == ()


# ---------------------------------------------------------------------------
# Test 2 — get_binding retrieves by binding_uid
# ---------------------------------------------------------------------------

def test_get_binding_round_trip(svc, well_uid, profile_uid, rev_uid):
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
    )
    fetched = svc.get_binding(binding.binding_uid)
    assert fetched.binding_uid == binding.binding_uid


# ---------------------------------------------------------------------------
# Test 3 — get_binding raises WellCanvasBindingNotFound for unknown uid
# ---------------------------------------------------------------------------

def test_get_binding_not_found(svc):
    with pytest.raises(WellCanvasBindingNotFound):
        svc.get_binding(new_uuid7_str())


# ---------------------------------------------------------------------------
# Test 4 — get_binding_for_well_and_revision returns None when not found
# ---------------------------------------------------------------------------

def test_get_binding_for_well_and_revision_none(svc, well_uid, rev_uid):
    result = svc.get_binding_for_well_and_revision(well_uid, rev_uid)
    assert result is None


# ---------------------------------------------------------------------------
# Test 5 — get_binding_for_well_and_revision returns correct binding
# ---------------------------------------------------------------------------

def test_get_binding_for_well_and_revision_found(svc, well_uid, profile_uid, rev_uid):
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
    )
    fetched = svc.get_binding_for_well_and_revision(well_uid, rev_uid)
    assert fetched is not None
    assert fetched.binding_uid == binding.binding_uid


# ---------------------------------------------------------------------------
# Test 6 — update_slot_binding sets BOUND status with curve uid
# ---------------------------------------------------------------------------

def test_update_slot_binding_bound(svc, well_uid, profile_uid, rev_uid, slot_uid, curve_uid):
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
    )
    updated = svc.update_slot_binding(
        binding_uid=binding.binding_uid,
        expected_revision=0,
        slot_uid=slot_uid,
        binding_status=BindingStatus.BOUND,
        managed_curve_uid=curve_uid,
        binding_source="user_explicit",
        updated_by="test",
    )
    assert len(updated.slot_bindings) == 1
    sb = updated.slot_bindings[0]
    assert sb.binding_status == BindingStatus.BOUND
    assert sb.managed_curve_uid == curve_uid
    assert sb.slot_uid == slot_uid


# ---------------------------------------------------------------------------
# Test 7 — update_slot_binding increments revision counter
# ---------------------------------------------------------------------------

def test_update_slot_binding_increments_revision(svc, well_uid, profile_uid, rev_uid, slot_uid, curve_uid):
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
    )
    assert binding.revision == 0
    updated = svc.update_slot_binding(
        binding_uid=binding.binding_uid,
        expected_revision=0,
        slot_uid=slot_uid,
        binding_status=BindingStatus.BOUND,
        managed_curve_uid=curve_uid,
        updated_by="test",
    )
    assert updated.revision == 1
    # Second update should require expected_revision=1
    updated2 = svc.update_slot_binding(
        binding_uid=binding.binding_uid,
        expected_revision=1,
        slot_uid=slot_uid,
        binding_status=BindingStatus.BOUND,
        managed_curve_uid=curve_uid,
        updated_by="test",
    )
    assert updated2.revision == 2


# ---------------------------------------------------------------------------
# Test 8 — update_slot_binding raises WellCanvasBindingRevisionConflict on stale
# ---------------------------------------------------------------------------

def test_update_slot_binding_occ_conflict(svc, well_uid, profile_uid, rev_uid, slot_uid, curve_uid):
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
    )
    # Advance revision to 1
    svc.update_slot_binding(
        binding_uid=binding.binding_uid,
        expected_revision=0,
        slot_uid=slot_uid,
        binding_status=BindingStatus.BOUND,
        managed_curve_uid=curve_uid,
        updated_by="test",
    )
    # Now try again with stale expected_revision=0
    with pytest.raises(WellCanvasBindingRevisionConflict):
        svc.update_slot_binding(
            binding_uid=binding.binding_uid,
            expected_revision=0,  # stale
            slot_uid=slot_uid,
            binding_status=BindingStatus.BOUND,
            managed_curve_uid=curve_uid,
            updated_by="test",
        )


# ---------------------------------------------------------------------------
# Test 9 — update_slot_binding raises SlotValidationError for unknown slot_uid
# ---------------------------------------------------------------------------

def test_update_slot_binding_invalid_slot(svc, well_uid, profile_uid, rev_uid, slot_uid, curve_uid):
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
    )
    known_slot = new_uuid7_str()
    with pytest.raises(SlotValidationError):
        svc.update_slot_binding(
            binding_uid=binding.binding_uid,
            expected_revision=0,
            slot_uid=slot_uid,  # not in valid set
            binding_status=BindingStatus.BOUND,
            managed_curve_uid=curve_uid,
            valid_slot_uids=frozenset({known_slot}),
            updated_by="test",
        )


# ---------------------------------------------------------------------------
# Test 10 — update_slot_binding raises CrossWellCurveError for foreign curve
# ---------------------------------------------------------------------------

def test_update_slot_binding_cross_well_error(well_uid, profile_uid, rev_uid, slot_uid, curve_uid):
    other_well_uid = new_uuid7_str()
    # curve belongs to a different well
    inventory = StubInventory([
        CurveInventoryRecord(
            managed_curve_uid=curve_uid,
            managed_well_uid=other_well_uid,
        )
    ])
    svc = WellBindingService(repository=InMemoryWellCanvasBindingRepository(), inventory=inventory)
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
    )
    with pytest.raises(CrossWellCurveError):
        svc.update_slot_binding(
            binding_uid=binding.binding_uid,
            expected_revision=0,
            slot_uid=slot_uid,
            binding_status=BindingStatus.BOUND,
            managed_curve_uid=curve_uid,
            updated_by="test",
        )


# ---------------------------------------------------------------------------
# Test 11 — unbind_slot sets USER_UNBOUND, clears managed_curve_uid
# ---------------------------------------------------------------------------

def test_unbind_slot_sets_user_unbound(svc, well_uid, profile_uid, rev_uid, slot_uid, curve_uid):
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
    )
    # First bind it
    bound = svc.update_slot_binding(
        binding_uid=binding.binding_uid,
        expected_revision=0,
        slot_uid=slot_uid,
        binding_status=BindingStatus.BOUND,
        managed_curve_uid=curve_uid,
        updated_by="test",
    )
    # Now unbind it
    unbound = svc.unbind_slot(
        binding_uid=binding.binding_uid,
        expected_revision=bound.revision,
        slot_uid=slot_uid,
        updated_by="test",
    )
    sb = next(s for s in unbound.slot_bindings if s.slot_uid == slot_uid)
    assert sb.binding_status == BindingStatus.USER_UNBOUND
    assert sb.managed_curve_uid is None


# ---------------------------------------------------------------------------
# Test 12 — unbind_slot sets user_override=True
# ---------------------------------------------------------------------------

def test_unbind_slot_sets_user_override(svc, well_uid, profile_uid, rev_uid, slot_uid):
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
    )
    result = svc.unbind_slot(
        binding_uid=binding.binding_uid,
        expected_revision=0,
        slot_uid=slot_uid,
        updated_by="test",
    )
    sb = next(s for s in result.slot_bindings if s.slot_uid == slot_uid)
    assert sb.user_override is True
    assert sb.binding_source == "user_explicit"


# ---------------------------------------------------------------------------
# Test 13 — list_bindings_for_well returns all overlays for a well
# ---------------------------------------------------------------------------

def test_list_bindings_for_well(svc, well_uid, profile_uid):
    rev1 = new_uuid7_str()
    rev2 = new_uuid7_str()
    b1 = svc.create_binding(managed_well_uid=well_uid, profile_uid=profile_uid, profile_revision_uid=rev1, profile_revision_number=0)
    b2 = svc.create_binding(managed_well_uid=well_uid, profile_uid=profile_uid, profile_revision_uid=rev2, profile_revision_number=1)
    # Binding for a different well — must not appear
    other_well = new_uuid7_str()
    svc.create_binding(managed_well_uid=other_well, profile_uid=profile_uid, profile_revision_uid=new_uuid7_str(), profile_revision_number=0)

    result = svc.list_bindings_for_well(well_uid)
    uids = {b.binding_uid for b in result}
    assert b1.binding_uid in uids
    assert b2.binding_uid in uids
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Test 14 — list_bindings_for_revision returns all overlays for a profile revision
# ---------------------------------------------------------------------------

def test_list_bindings_for_revision(svc, profile_uid, rev_uid):
    well1 = new_uuid7_str()
    well2 = new_uuid7_str()
    b1 = svc.create_binding(managed_well_uid=well1, profile_uid=profile_uid, profile_revision_uid=rev_uid, profile_revision_number=0)
    b2 = svc.create_binding(managed_well_uid=well2, profile_uid=profile_uid, profile_revision_uid=rev_uid, profile_revision_number=0)
    # Different revision — must not appear
    svc.create_binding(managed_well_uid=well1, profile_uid=profile_uid, profile_revision_uid=new_uuid7_str(), profile_revision_number=1)

    result = svc.list_bindings_for_revision(rev_uid)
    uids = {b.binding_uid for b in result}
    assert b1.binding_uid in uids
    assert b2.binding_uid in uids
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Test 15 — check_stale returns True when revision uid differs
# ---------------------------------------------------------------------------

def test_check_stale_returns_true_when_different(svc, well_uid, profile_uid, rev_uid):
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
    )
    newer_rev_uid = new_uuid7_str()
    assert svc.check_stale(binding.binding_uid, newer_rev_uid) is True


# ---------------------------------------------------------------------------
# Test 16 — check_stale returns False when revision uid matches
# ---------------------------------------------------------------------------

def test_check_stale_returns_false_when_same(svc, well_uid, profile_uid, rev_uid):
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
    )
    assert svc.check_stale(binding.binding_uid, rev_uid) is False


# ---------------------------------------------------------------------------
# Test 17 — mark_stale sets overlay_status to "stale"
# ---------------------------------------------------------------------------

def test_mark_stale_sets_status(svc, well_uid, profile_uid, rev_uid):
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
    )
    assert binding.overlay_status == "current"
    staled = svc.mark_stale(binding.binding_uid, updated_by="test")
    assert staled.overlay_status == "stale"


# ---------------------------------------------------------------------------
# Test 18 — mark_stale is idempotent (revision increments only once)
# ---------------------------------------------------------------------------

def test_mark_stale_idempotent(svc, well_uid, profile_uid, rev_uid):
    binding = svc.create_binding(
        managed_well_uid=well_uid,
        profile_uid=profile_uid,
        profile_revision_uid=rev_uid,
        profile_revision_number=0,
    )
    first = svc.mark_stale(binding.binding_uid, updated_by="test")
    second = svc.mark_stale(binding.binding_uid, updated_by="test")
    assert first.overlay_status == "stale"
    assert second.overlay_status == "stale"
    # Second call short-circuits; revision should be same as after first call
    assert second.revision == first.revision


# ---------------------------------------------------------------------------
# Test 19 — resolve_slot_candidates returns BOUND for unambiguous top scorer
# ---------------------------------------------------------------------------

def test_resolve_slot_candidates_bound(well_uid):
    svc = WellBindingService(repository=InMemoryWellCanvasBindingRepository(), inventory=None)
    slot = _make_slot(new_uuid7_str(), expected_curve_family="GAMMA_RAY", expected_curve_type="GR", expected_unit_family="GAPI")
    curve_a = new_uuid7_str()
    curve_b = new_uuid7_str()
    # curve_a matches all three → score 9; curve_b matches only family → score 4
    candidates = [
        CurveInventoryRecord(managed_curve_uid=curve_a, managed_well_uid=well_uid,
                             curve_family="GAMMA_RAY", kr_curve_type_id="GR", unit_family="GAPI"),
        CurveInventoryRecord(managed_curve_uid=curve_b, managed_well_uid=well_uid,
                             curve_family="GAMMA_RAY", kr_curve_type_id=None, unit_family=None),
    ]
    result = svc.resolve_slot_candidates(candidates, slot, well_uid)
    assert result.binding_status == BindingStatus.BOUND
    assert result.managed_curve_uid == curve_a
    assert result.confidence is not None and result.confidence > 0


# ---------------------------------------------------------------------------
# Test 20 — resolve_slot_candidates: UNRESOLVED for ties; UNAVAILABLE for no well match
# ---------------------------------------------------------------------------

def test_resolve_slot_candidates_unresolved_and_unavailable(well_uid):
    svc = WellBindingService(repository=InMemoryWellCanvasBindingRepository(), inventory=None)
    slot = _make_slot(new_uuid7_str(), expected_curve_family="GAMMA_RAY")

    # UNRESOLVED — two candidates score equally (family match only, score=4 each)
    curve_a = new_uuid7_str()
    curve_b = new_uuid7_str()
    tied = [
        CurveInventoryRecord(managed_curve_uid=curve_a, managed_well_uid=well_uid, curve_family="GAMMA_RAY"),
        CurveInventoryRecord(managed_curve_uid=curve_b, managed_well_uid=well_uid, curve_family="GAMMA_RAY"),
    ]
    unresolved = svc.resolve_slot_candidates(tied, slot, well_uid)
    assert unresolved.binding_status == BindingStatus.UNRESOLVED
    assert unresolved.managed_curve_uid is None

    # UNAVAILABLE — all candidates belong to a different well
    other_well = new_uuid7_str()
    foreign = [
        CurveInventoryRecord(managed_curve_uid=new_uuid7_str(), managed_well_uid=other_well, curve_family="GAMMA_RAY"),
    ]
    unavailable = svc.resolve_slot_candidates(foreign, slot, well_uid)
    assert unavailable.binding_status == BindingStatus.UNAVAILABLE
    assert unavailable.managed_curve_uid is None


# ---------------------------------------------------------------------------
# Bonus: LocalJsonWellCanvasBindingRepository honours OCC (isolated file)
# ---------------------------------------------------------------------------

def test_local_json_repo_occ_conflict(tmp_path):
    store = tmp_path / "well_canvas_bindings.json"
    repo = LocalJsonWellCanvasBindingRepository(storage_path=store)
    svc = WellBindingService(repository=repo, inventory=None)
    well = new_uuid7_str()
    profile = new_uuid7_str()
    rev = new_uuid7_str()
    slot = new_uuid7_str()
    curve = new_uuid7_str()

    binding = svc.create_binding(
        managed_well_uid=well,
        profile_uid=profile,
        profile_revision_uid=rev,
        profile_revision_number=0,
    )
    # Advance to revision 1
    svc.update_slot_binding(
        binding_uid=binding.binding_uid,
        expected_revision=0,
        slot_uid=slot,
        binding_status=BindingStatus.BOUND,
        managed_curve_uid=curve,
        updated_by="test",
    )
    # Attempt with stale revision 0
    with pytest.raises(WellCanvasBindingRevisionConflict):
        svc.update_slot_binding(
            binding_uid=binding.binding_uid,
            expected_revision=0,
            slot_uid=slot,
            binding_status=BindingStatus.BOUND,
            managed_curve_uid=curve,
            updated_by="test",
        )
    # Confirm stored revision is still 1 (not corrupted)
    stored = svc.get_binding(binding.binding_uid)
    assert stored.revision == 1
