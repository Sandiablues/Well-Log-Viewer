"""Phase 2 tests — Shared Canvas Profile Foundation.

Coverage:
  1.  create_profile creates a profile record
  2.  initial immutable revision is created alongside the profile
  3.  profile_uid is stable across revisions
  4.  profile_revision_uid changes on append_revision
  5.  revision_number increments monotonically
  6.  previous revision remains readable after append
  7.  optimistic concurrency conflict is rejected
  8.  shared profile contains no managed_well_uid field
  9.  shared profile contains no managed_curve_uid field
  10. track and slot UIDs are valid UUIDv7
  11. activation is scoped (different scope_uid → independent activations)
  12. only one active revision exists per activation scope
  13. different scopes may activate different profiles independently
  14. archived profile cannot be activated
  15. archived profile cannot receive a new revision
  16. atomic write: file exists and is valid JSON after create
  17. list_profiles and list_activations return expected records
  18. service works through the abstract repository interface
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.identity import is_uuid7, new_uuid7_str
from app.wdv_shared_canvas.models import (
    SharedCanvasActivation,
    SharedCanvasAuditRecord,
    SharedCanvasProfile,
    SharedCanvasProfileRevision,
    SharedCanvasSlot,
    SharedCanvasTrack,
)
from app.wdv_shared_canvas.repository import (
    LocalJsonSharedCanvasRepository,
    SharedCanvasProfileNotFound,
    SharedCanvasProfileRepository,
    SharedCanvasRevisionConflict,
)
from app.wdv_shared_canvas.service import (
    SharedCanvasArchivedError,
    SharedCanvasProfileService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_slot(order: int = 0) -> SharedCanvasSlot:
    return SharedCanvasSlot(
        slot_uid=new_uuid7_str(),
        slot_key=f"slot_{order}",
        slot_order=order,
        expected_curve_family="GR",
    )


def make_track(order: int = 0, *, with_slots: bool = True) -> SharedCanvasTrack:
    return SharedCanvasTrack(
        track_uid=new_uuid7_str(),
        track_key=f"track_{order}",
        track_order=order,
        track_name=f"Track {order}",
        renderer_type="line",
        width_px=220,
        slots=(make_slot(0),) if with_slots else (),
    )


def make_service(tmp_path: Path) -> SharedCanvasProfileService:
    repo = LocalJsonSharedCanvasRepository(tmp_path / "shared_canvas_profiles.json")
    return SharedCanvasProfileService(repository=repo)


# ---------------------------------------------------------------------------
# 1. create_profile creates a profile record
# ---------------------------------------------------------------------------

def test_create_profile_returns_profile(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    profile, _ = svc.create_profile(profile_name="Petrophysics Standard")
    assert profile.profile_uid
    assert profile.profile_name == "Petrophysics Standard"
    assert profile.status == "active"

    retrieved = svc.get_profile(profile.profile_uid)
    assert retrieved.profile_uid == profile.profile_uid
    assert retrieved.profile_name == "Petrophysics Standard"


# ---------------------------------------------------------------------------
# 2. Initial immutable revision is created alongside the profile
# ---------------------------------------------------------------------------

def test_initial_revision_created_with_profile(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    tracks = (make_track(0), make_track(1))
    profile, revision = svc.create_profile(
        profile_name="Wellbore View",
        tracks=tracks,
    )

    assert revision.profile_revision_uid
    assert revision.profile_uid == profile.profile_uid
    assert revision.revision_number == 0
    assert revision.previous_revision_uid is None
    assert len(revision.tracks) == 2

    retrieved = svc.get_revision(revision.profile_revision_uid)
    assert retrieved.profile_revision_uid == revision.profile_revision_uid


# ---------------------------------------------------------------------------
# 3. profile_uid is stable across revisions
# ---------------------------------------------------------------------------

def test_profile_uid_stable_across_revisions(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    profile, rev0 = svc.create_profile(
        profile_name="Stable Test",
        tracks=(make_track(0),),
    )
    original_uid = profile.profile_uid

    rev1 = svc.append_revision(
        profile_uid=original_uid,
        expected_revision_number=0,
        tracks=(make_track(0), make_track(1)),
        change_reason="Added second track",
    )

    assert rev1.profile_uid == original_uid
    assert svc.get_profile(original_uid).profile_uid == original_uid


# ---------------------------------------------------------------------------
# 4. profile_revision_uid changes on append_revision
# ---------------------------------------------------------------------------

def test_revision_uid_changes_on_append(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    profile, rev0 = svc.create_profile(
        profile_name="UID Change Test",
        tracks=(make_track(0),),
    )
    rev1 = svc.append_revision(
        profile_uid=profile.profile_uid,
        expected_revision_number=0,
        tracks=(make_track(0), make_track(1)),
    )

    assert rev1.profile_revision_uid != rev0.profile_revision_uid


# ---------------------------------------------------------------------------
# 5. revision_number increments monotonically
# ---------------------------------------------------------------------------

def test_revision_number_increments(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    profile, rev0 = svc.create_profile(
        profile_name="Increment Test",
        tracks=(make_track(0),),
    )
    assert rev0.revision_number == 0

    rev1 = svc.append_revision(
        profile_uid=profile.profile_uid,
        expected_revision_number=0,
        tracks=(make_track(0), make_track(1)),
    )
    assert rev1.revision_number == 1

    rev2 = svc.append_revision(
        profile_uid=profile.profile_uid,
        expected_revision_number=1,
        tracks=(make_track(0), make_track(1), make_track(2)),
    )
    assert rev2.revision_number == 2


# ---------------------------------------------------------------------------
# 6. Previous revision remains readable after append
# ---------------------------------------------------------------------------

def test_previous_revision_remains_readable(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    profile, rev0 = svc.create_profile(
        profile_name="History Test",
        tracks=(make_track(0),),
    )
    rev1 = svc.append_revision(
        profile_uid=profile.profile_uid,
        expected_revision_number=0,
        tracks=(make_track(0), make_track(1)),
    )

    # rev0 must still be readable
    old = svc.get_revision(rev0.profile_revision_uid)
    assert old.revision_number == 0
    assert len(old.tracks) == 1

    # rev1 is the new head
    current = svc.get_revision(rev1.profile_revision_uid)
    assert current.revision_number == 1
    assert len(current.tracks) == 2

    # list_revisions returns both in order
    all_revisions = svc.list_revisions(profile.profile_uid)
    assert len(all_revisions) == 2
    assert all_revisions[0].revision_number == 0
    assert all_revisions[1].revision_number == 1


# ---------------------------------------------------------------------------
# 7. Optimistic concurrency conflict is rejected
# ---------------------------------------------------------------------------

def test_optimistic_concurrency_conflict_rejected(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    profile, rev0 = svc.create_profile(
        profile_name="Concurrency Test",
        tracks=(make_track(0),),
    )

    # First append succeeds
    svc.append_revision(
        profile_uid=profile.profile_uid,
        expected_revision_number=0,
        tracks=(make_track(0), make_track(1)),
    )

    # Second append with stale expected_revision_number=0 must fail
    with pytest.raises(SharedCanvasRevisionConflict):
        svc.append_revision(
            profile_uid=profile.profile_uid,
            expected_revision_number=0,
            tracks=(make_track(0),),
        )


# ---------------------------------------------------------------------------
# 8. Shared profile contains no managed_well_uid field
# ---------------------------------------------------------------------------

def test_shared_profile_has_no_well_uid_field() -> None:
    field_names = set(SharedCanvasProfile.model_fields)
    assert "managed_well_uid" not in field_names
    assert "well_uid" not in field_names


def test_shared_canvas_track_has_no_well_uid_field() -> None:
    field_names = set(SharedCanvasTrack.model_fields)
    assert "managed_well_uid" not in field_names
    assert "well_uid" not in field_names


def test_shared_canvas_revision_has_no_well_uid_field() -> None:
    field_names = set(SharedCanvasProfileRevision.model_fields)
    assert "managed_well_uid" not in field_names
    assert "well_uid" not in field_names


# ---------------------------------------------------------------------------
# 9. Shared profile contains no managed_curve_uid field
# ---------------------------------------------------------------------------

def test_shared_profile_has_no_curve_uid_field() -> None:
    for model in (
        SharedCanvasProfile,
        SharedCanvasProfileRevision,
        SharedCanvasTrack,
        SharedCanvasSlot,
    ):
        field_names = set(model.model_fields)
        assert "managed_curve_uid" not in field_names, (
            f"{model.__name__} must not contain managed_curve_uid"
        )
        assert "curve_uid" not in field_names, (
            f"{model.__name__} must not contain curve_uid"
        )


# ---------------------------------------------------------------------------
# 10. Track and slot UIDs are valid UUIDv7
# ---------------------------------------------------------------------------

def test_track_and_slot_uids_are_uuid7(tmp_path: Path) -> None:
    slot = make_slot(0)
    track = SharedCanvasTrack(
        track_uid=new_uuid7_str(),
        track_key="gr_track",
        track_order=0,
        track_name="GR Track",
        slots=(slot,),
    )
    svc = make_service(tmp_path)
    profile, revision = svc.create_profile(
        profile_name="UUID7 Test",
        tracks=(track,),
    )

    assert is_uuid7(profile.profile_uid)
    assert is_uuid7(revision.profile_revision_uid)

    persisted_revision = svc.get_revision(revision.profile_revision_uid)
    persisted_track = persisted_revision.tracks[0]
    persisted_slot = persisted_track.slots[0]

    assert is_uuid7(persisted_track.track_uid)
    assert is_uuid7(persisted_slot.slot_uid)


# ---------------------------------------------------------------------------
# 11. Activation is scoped
# ---------------------------------------------------------------------------

def test_activation_is_scoped(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    profile_a, rev_a = svc.create_profile(
        profile_name="Profile A",
        tracks=(make_track(0),),
    )
    profile_b, rev_b = svc.create_profile(
        profile_name="Profile B",
        tracks=(make_track(0),),
    )

    scope_uid_1 = new_uuid7_str()
    scope_uid_2 = new_uuid7_str()

    svc.activate_revision(
        rev_a.profile_revision_uid,
        scope_type="local_workspace",
        scope_uid=scope_uid_1,
        activated_by="user",
    )
    svc.activate_revision(
        rev_b.profile_revision_uid,
        scope_type="local_workspace",
        scope_uid=scope_uid_2,
        activated_by="user",
    )

    active_1 = svc.get_active_revision(
        scope_type="local_workspace", scope_uid=scope_uid_1
    )
    active_2 = svc.get_active_revision(
        scope_type="local_workspace", scope_uid=scope_uid_2
    )

    assert active_1 is not None
    assert active_2 is not None
    assert active_1.profile_revision_uid == rev_a.profile_revision_uid
    assert active_2.profile_revision_uid == rev_b.profile_revision_uid


# ---------------------------------------------------------------------------
# 12. Only one active revision per activation scope
# ---------------------------------------------------------------------------

def test_only_one_active_revision_per_scope(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    profile, rev0 = svc.create_profile(
        profile_name="Activation Override Test",
        tracks=(make_track(0),),
    )
    rev1 = svc.append_revision(
        profile_uid=profile.profile_uid,
        expected_revision_number=0,
        tracks=(make_track(0), make_track(1)),
    )

    scope_uid = new_uuid7_str()
    scope_type = "local_workspace"

    svc.activate_revision(
        rev0.profile_revision_uid,
        scope_type=scope_type,
        scope_uid=scope_uid,
        activated_by="user",
    )
    assert svc.get_active_revision(
        scope_type=scope_type, scope_uid=scope_uid
    ).profile_revision_uid == rev0.profile_revision_uid

    # Activating rev1 must replace rev0 for the same scope
    svc.activate_revision(
        rev1.profile_revision_uid,
        scope_type=scope_type,
        scope_uid=scope_uid,
        activated_by="user",
    )
    active = svc.get_active_revision(scope_type=scope_type, scope_uid=scope_uid)
    assert active.profile_revision_uid == rev1.profile_revision_uid


# ---------------------------------------------------------------------------
# 13. Different scopes may activate different profiles independently
# ---------------------------------------------------------------------------

def test_different_scopes_activate_independently(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    profile_x, rev_x = svc.create_profile(
        profile_name="Profile X", tracks=(make_track(0),)
    )
    profile_y, rev_y = svc.create_profile(
        profile_name="Profile Y", tracks=(make_track(0),)
    )

    scope_a = new_uuid7_str()
    scope_b = new_uuid7_str()

    svc.activate_revision(
        rev_x.profile_revision_uid,
        scope_type="local_workspace",
        scope_uid=scope_a,
        activated_by="user",
    )
    svc.activate_revision(
        rev_y.profile_revision_uid,
        scope_type="local_workspace",
        scope_uid=scope_b,
        activated_by="user",
    )

    # Changing scope_b must not affect scope_a
    active_a = svc.get_active_revision(
        scope_type="local_workspace", scope_uid=scope_a
    )
    active_b = svc.get_active_revision(
        scope_type="local_workspace", scope_uid=scope_b
    )
    assert active_a.profile_uid == profile_x.profile_uid
    assert active_b.profile_uid == profile_y.profile_uid


# ---------------------------------------------------------------------------
# 14. Archived profile cannot be activated
# ---------------------------------------------------------------------------

def test_archived_profile_cannot_be_activated(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    profile, revision = svc.create_profile(
        profile_name="To Be Archived",
        tracks=(make_track(0),),
    )
    svc.archive_profile(profile.profile_uid, archived_by="admin")

    with pytest.raises(SharedCanvasArchivedError):
        svc.activate_revision(
            revision.profile_revision_uid,
            scope_type="local_workspace",
            scope_uid=new_uuid7_str(),
            activated_by="user",
        )


# ---------------------------------------------------------------------------
# 15. Archived profile cannot receive a new revision
# ---------------------------------------------------------------------------

def test_archived_profile_cannot_receive_new_revision(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    profile, revision = svc.create_profile(
        profile_name="Archived No Revision",
        tracks=(make_track(0),),
    )
    svc.archive_profile(profile.profile_uid, archived_by="admin")

    with pytest.raises(SharedCanvasArchivedError):
        svc.append_revision(
            profile_uid=profile.profile_uid,
            expected_revision_number=0,
            tracks=(make_track(0), make_track(1)),
        )


# ---------------------------------------------------------------------------
# 16. Atomic write: file exists and is valid JSON after create
# ---------------------------------------------------------------------------

def test_atomic_write_produces_valid_json(tmp_path: Path) -> None:
    store_path = tmp_path / "shared_canvas_profiles.json"
    repo = LocalJsonSharedCanvasRepository(store_path)
    svc = SharedCanvasProfileService(repository=repo)

    assert not store_path.exists()
    svc.create_profile(profile_name="Atomic Test", tracks=(make_track(0),))
    assert store_path.exists()

    raw = json.loads(store_path.read_text(encoding="utf-8"))
    assert raw["schema_version"] == "shared_canvas_profiles_v1"
    assert len(raw["profiles"]) == 1
    assert len(raw["revisions"]) == 1
    assert len(raw["audit"]) == 1


# ---------------------------------------------------------------------------
# 17. list_profiles and list_activations return expected records
# ---------------------------------------------------------------------------

def test_list_profiles_and_activations(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    p1, r1 = svc.create_profile(profile_name="Profile One", tracks=(make_track(0),))
    p2, r2 = svc.create_profile(profile_name="Profile Two", tracks=(make_track(0),))
    p3, r3 = svc.create_profile(profile_name="Profile Three", tracks=(make_track(0),))
    svc.archive_profile(p3.profile_uid, archived_by="admin")

    active = svc.list_profiles(include_archived=False)
    assert len(active) == 2
    assert all(p.status == "active" for p in active)

    all_profiles = svc.list_profiles(include_archived=True)
    assert len(all_profiles) == 3

    scope_uid = new_uuid7_str()
    svc.activate_revision(
        r1.profile_revision_uid,
        scope_type="local_workspace",
        scope_uid=scope_uid,
        activated_by="user",
    )
    activations = svc.list_activations()
    assert len(activations) == 1
    assert activations[0].profile_uid == p1.profile_uid


# ---------------------------------------------------------------------------
# 18. Service works through the abstract repository interface
# ---------------------------------------------------------------------------

class InMemorySharedCanvasRepository(SharedCanvasProfileRepository):
    """Minimal in-memory implementation for interface compliance testing."""

    def __init__(self) -> None:
        self._profiles: dict[str, Any] = {}
        self._revisions: dict[str, Any] = {}
        self._revision_index: dict[str, list[str]] = {}
        self._activations: dict[str, Any] = {}
        self._audit: list[Any] = []

    def create_profile(self, profile, initial_revision, audit) -> None:
        self._profiles[profile.profile_uid] = profile.model_dump(mode="json")
        self._revisions[initial_revision.profile_revision_uid] = (
            initial_revision.model_dump(mode="json")
        )
        self._revision_index.setdefault(profile.profile_uid, []).append(
            initial_revision.profile_revision_uid
        )
        self._audit.append(audit.model_dump(mode="json"))

    def get_profile(self, profile_uid):
        raw = self._profiles.get(profile_uid)
        return SharedCanvasProfile.model_validate(raw) if raw else None

    def list_profiles(self, include_archived=False):
        profiles = [
            SharedCanvasProfile.model_validate(v)
            for v in self._profiles.values()
        ]
        if not include_archived:
            profiles = [p for p in profiles if p.status == "active"]
        return sorted(profiles, key=lambda p: p.created_at)

    def update_profile_header(self, profile, audit) -> None:
        self._profiles[profile.profile_uid] = profile.model_dump(mode="json")
        self._audit.append(audit.model_dump(mode="json"))

    def append_revision(self, revision, expected_revision_number, audit) -> None:
        ordered = self._revision_index.get(revision.profile_uid, [])
        if not ordered:
            raise SharedCanvasProfileNotFound(revision.profile_uid)
        last_raw = self._revisions[ordered[-1]]
        current = int(last_raw["revision_number"])
        if current != expected_revision_number:
            raise SharedCanvasRevisionConflict(
                f"Expected {expected_revision_number}, found {current}"
            )
        self._revisions[revision.profile_revision_uid] = (
            revision.model_dump(mode="json")
        )
        self._revision_index[revision.profile_uid].append(
            revision.profile_revision_uid
        )
        self._audit.append(audit.model_dump(mode="json"))

    def get_revision(self, profile_revision_uid):
        raw = self._revisions.get(profile_revision_uid)
        return SharedCanvasProfileRevision.model_validate(raw) if raw else None

    def list_revisions(self, profile_uid):
        return [
            SharedCanvasProfileRevision.model_validate(self._revisions[uid])
            for uid in self._revision_index.get(profile_uid, [])
            if uid in self._revisions
        ]

    def set_activation(self, activation) -> None:
        key = f"{activation.activation_scope_type}:{activation.activation_scope_uid}"
        self._activations[key] = activation.model_dump(mode="json")

    def get_activation(self, scope_type, scope_uid):
        raw = self._activations.get(f"{scope_type}:{scope_uid}")
        return SharedCanvasActivation.model_validate(raw) if raw else None

    def list_activations(self):
        return [
            SharedCanvasActivation.model_validate(v)
            for v in self._activations.values()
        ]

    def append_audit(self, record) -> None:
        self._audit.append(record.model_dump(mode="json"))


def test_service_works_through_abstract_repository_interface() -> None:
    """Service operates correctly with any SharedCanvasProfileRepository implementation."""
    repo: SharedCanvasProfileRepository = InMemorySharedCanvasRepository()
    svc = SharedCanvasProfileService(repository=repo)

    profile, rev0 = svc.create_profile(
        profile_name="Interface Test",
        tracks=(make_track(0),),
        created_by="test_actor",
    )
    assert svc.get_profile(profile.profile_uid).profile_name == "Interface Test"

    rev1 = svc.append_revision(
        profile_uid=profile.profile_uid,
        expected_revision_number=0,
        tracks=(make_track(0), make_track(1)),
        change_reason="Added track",
    )
    assert rev1.revision_number == 1
    assert rev1.previous_revision_uid == rev0.profile_revision_uid

    # Old revision still accessible
    assert svc.get_revision(rev0.profile_revision_uid).revision_number == 0

    # Activate via interface
    scope_uid = new_uuid7_str()
    svc.activate_revision(
        rev1.profile_revision_uid,
        scope_type="local_workspace",
        scope_uid=scope_uid,
        activated_by="test_actor",
    )
    active = svc.get_active_revision(
        scope_type="local_workspace", scope_uid=scope_uid
    )
    assert active is not None
    assert active.profile_revision_uid == rev1.profile_revision_uid
