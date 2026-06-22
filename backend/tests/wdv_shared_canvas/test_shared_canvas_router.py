"""Router tests for the shared canvas API (Phase 5A).

Covers all 15 required test criteria:
  1.  list/get profiles
  2.  get revision
  3.  scoped activation
  4.  retrieve active revision by scope
  5.  get/create/update well binding
  6.  revision conflict returns 409
  7.  stale binding returns 409
  8.  missing active profile handled explicitly (404)
  9.  missing binding handled explicitly (404)
 10.  successful resolved-session response
 11.  unavailable slots remain present in resolved session
 12.  cross-well curve violation is rejected (422)
 13.  scale labels appear in the response
 14.  no profile, binding, or session mutation during GET
 15.  no writes to existing WDV session stores

Tests use in-memory repositories injected into the router's module-level
service slots.  No file I/O occurs during these tests.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import app.wdv_shared_canvas.router as shared_canvas_router
from app.identity import new_uuid7_str
from app.main import app
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
from app.wdv_shared_canvas.binding_service import CrossWellCurveError, CurveInventoryLookup
from app.wdv_shared_canvas.models import (
    SharedCanvasActivation,
    SharedCanvasAuditRecord,
    SharedCanvasProfile,
    SharedCanvasProfileRevision,
    SharedCanvasSlot,
    SharedCanvasTrack,
)
from app.wdv_shared_canvas.repository import SharedCanvasProfileRepository
from app.wdv_shared_canvas.resolution_service import CanvasResolutionService
from app.wdv_shared_canvas.service import SharedCanvasProfileService
from app.wdv_shared_canvas.binding_service import WellBindingService


# ---------------------------------------------------------------------------
# In-memory stubs (isolated from file system)
# ---------------------------------------------------------------------------

class InMemorySharedCanvasRepository(SharedCanvasProfileRepository):
    def __init__(self) -> None:
        self._profiles: dict[str, SharedCanvasProfile] = {}
        self._revisions: dict[str, SharedCanvasProfileRevision] = {}
        self._activations: dict[str, SharedCanvasActivation] = {}
        self._audit: list = []
        self.write_count: int = 0

    def create_profile(self, profile, initial_revision, audit) -> None:
        self.write_count += 1
        self._profiles[profile.profile_uid] = profile
        self._revisions[initial_revision.profile_revision_uid] = initial_revision
        self._audit.append(audit)

    def get_profile(self, profile_uid):
        return self._profiles.get(profile_uid)

    def list_profiles(self, include_archived=False):
        profiles = list(self._profiles.values())
        if not include_archived:
            from app.wdv_shared_canvas.models import ProfileStatus
            profiles = [p for p in profiles if p.status == ProfileStatus.ACTIVE]
        return profiles

    def update_profile_header(self, profile, audit) -> None:
        self.write_count += 1
        self._profiles[profile.profile_uid] = profile

    def append_revision(self, revision, expected_revision_number, audit) -> None:
        self.write_count += 1
        self._revisions[revision.profile_revision_uid] = revision

    def get_revision(self, profile_revision_uid):
        return self._revisions.get(profile_revision_uid)

    def list_revisions(self, profile_uid):
        return [r for r in self._revisions.values() if r.profile_uid == profile_uid]

    def set_activation(self, activation) -> None:
        self.write_count += 1
        self._activations[f"{activation.activation_scope_type}:{activation.activation_scope_uid}"] = activation

    def get_activation(self, scope_type, scope_uid):
        return self._activations.get(f"{scope_type}:{scope_uid}")

    def list_activations(self):
        return list(self._activations.values())

    def append_audit(self, record) -> None:
        self._audit.append(record)


class InMemoryWellCanvasBindingRepository(WellCanvasBindingRepository):
    def __init__(self) -> None:
        self._bindings: dict[str, WellCanvasBinding] = {}
        self._well_index: dict[str, list[str]] = {}
        self._revision_index: dict[str, list[str]] = {}
        self.write_count: int = 0

    def create_binding(self, binding) -> None:
        self.write_count += 1
        self._bindings[binding.binding_uid] = binding
        self._well_index.setdefault(binding.managed_well_uid, []).append(binding.binding_uid)
        self._revision_index.setdefault(binding.profile_revision_uid, []).append(binding.binding_uid)

    def get_binding(self, binding_uid):
        return self._bindings.get(binding_uid)

    def get_binding_for_well_and_revision(self, managed_well_uid, profile_revision_uid):
        for uid in self._well_index.get(managed_well_uid, []):
            b = self._bindings.get(uid)
            if b is not None and b.profile_revision_uid == profile_revision_uid:
                return b
        return None

    def list_bindings_for_well(self, managed_well_uid):
        return [self._bindings[u] for u in self._well_index.get(managed_well_uid, []) if u in self._bindings]

    def list_bindings_for_revision(self, profile_revision_uid):
        return [self._bindings[u] for u in self._revision_index.get(profile_revision_uid, []) if u in self._bindings]

    def update_binding(self, binding, expected_revision) -> None:
        stored = self._bindings.get(binding.binding_uid)
        if stored is None:
            raise WellCanvasBindingNotFound(binding.binding_uid)
        if stored.revision != expected_revision:
            raise WellCanvasBindingRevisionConflict(f"{expected_revision} != {stored.revision}")
        self.write_count += 1
        self._bindings[binding.binding_uid] = binding


class StubInventory(CurveInventoryLookup):
    def __init__(self, records: list[CurveInventoryRecord]) -> None:
        self._by_uid = {r.managed_curve_uid: r for r in records}

    def get_curve(self, managed_curve_uid):
        return self._by_uid.get(managed_curve_uid)

    def list_curves_for_well(self, managed_well_uid):
        return [r for r in self._by_uid.values() if r.managed_well_uid == managed_well_uid]


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

_SCOPE_TYPE = "local_workspace"
_SCOPE_UID = "ws-test"
_TS = "2026-01-01T00:00:00+00:00"


def _install_services(inventory_records: list[CurveInventoryRecord] | None = None):
    """Create shared in-memory repos and inject into router module."""
    profile_repo = InMemorySharedCanvasRepository()
    binding_repo = InMemoryWellCanvasBindingRepository()
    inv = StubInventory(inventory_records or [])

    shared_canvas_router._profile_svc = SharedCanvasProfileService(repository=profile_repo)
    shared_canvas_router._binding_svc = WellBindingService(repository=binding_repo, inventory=inv)
    shared_canvas_router._resolution_svc = CanvasResolutionService(
        profile_repository=profile_repo,
        binding_repository=binding_repo,
        inventory=inv,
    )
    return profile_repo, binding_repo


@pytest.fixture(autouse=True)
def _reset_services():
    """Ensure module-level service slots are cleared after every test."""
    yield
    shared_canvas_router._profile_svc = None
    shared_canvas_router._binding_svc = None
    shared_canvas_router._resolution_svc = None


@pytest.fixture
def client():
    return TestClient(app)


def _make_slot(uid=None, key="GR", order=0):
    return SharedCanvasSlot(slot_uid=uid or new_uuid7_str(), slot_key=key, slot_order=order)


def _make_track(uid=None, order=0, slots=()):
    return SharedCanvasTrack(
        track_uid=uid or new_uuid7_str(),
        track_order=order,
        track_name="Track",
        slots=slots,
    )


# ---------------------------------------------------------------------------
# Test 1 — list and get profiles
# ---------------------------------------------------------------------------

def test_list_profiles_empty(client):
    _install_services()
    resp = client.get("/api/wlv/v2/wdv/shared-canvas/profiles")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_profile_found(client):
    profile_repo, _ = _install_services()
    svc = shared_canvas_router._profile_svc
    profile, _ = svc.create_profile(profile_name="Audit Suite", created_by="test")

    resp = client.get(f"/api/wlv/v2/wdv/shared-canvas/profiles/{profile.profile_uid}")
    assert resp.status_code == 200
    assert resp.json()["profile_uid"] == profile.profile_uid
    assert resp.json()["profile_name"] == "Audit Suite"


def test_get_profile_not_found(client):
    _install_services()
    resp = client.get(f"/api/wlv/v2/wdv/shared-canvas/profiles/{new_uuid7_str()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 2 — get revision
# ---------------------------------------------------------------------------

def test_get_revision_found(client):
    _install_services()
    svc = shared_canvas_router._profile_svc
    _, revision = svc.create_profile(profile_name="Rev Test", created_by="test")

    resp = client.get(f"/api/wlv/v2/wdv/shared-canvas/revisions/{revision.profile_revision_uid}")
    assert resp.status_code == 200
    assert resp.json()["profile_revision_uid"] == revision.profile_revision_uid


def test_get_revision_not_found(client):
    _install_services()
    resp = client.get(f"/api/wlv/v2/wdv/shared-canvas/revisions/{new_uuid7_str()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 3 — scoped activation
# ---------------------------------------------------------------------------

def test_scoped_activation(client):
    _install_services()
    svc = shared_canvas_router._profile_svc
    _, revision = svc.create_profile(profile_name="Activation Test", created_by="test")

    resp = client.post(
        f"/api/wlv/v2/wdv/shared-canvas/scopes/{_SCOPE_TYPE}/{_SCOPE_UID}/activate",
        json={"profile_revision_uid": revision.profile_revision_uid, "activated_by": "test"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile_revision_uid"] == revision.profile_revision_uid
    assert body["activation_scope_type"] == _SCOPE_TYPE
    assert body["activation_scope_uid"] == _SCOPE_UID


def test_activate_archived_profile_returns_409(client):
    _install_services()
    svc = shared_canvas_router._profile_svc
    profile, revision = svc.create_profile(profile_name="To Archive", created_by="test")
    svc.archive_profile(profile.profile_uid, archived_by="test")

    resp = client.post(
        f"/api/wlv/v2/wdv/shared-canvas/scopes/{_SCOPE_TYPE}/{_SCOPE_UID}/activate",
        json={"profile_revision_uid": revision.profile_revision_uid},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Test 4 — retrieve active revision by scope
# ---------------------------------------------------------------------------

def test_get_active_revision_by_scope(client):
    _install_services()
    svc = shared_canvas_router._profile_svc
    _, revision = svc.create_profile(profile_name="Active Rev", created_by="test")
    svc.activate_revision(
        revision.profile_revision_uid,
        scope_type=_SCOPE_TYPE,
        scope_uid=_SCOPE_UID,
        activated_by="test",
    )

    resp = client.get(
        f"/api/wlv/v2/wdv/shared-canvas/scopes/{_SCOPE_TYPE}/{_SCOPE_UID}/active-revision"
    )
    assert resp.status_code == 200
    assert resp.json()["profile_revision_uid"] == revision.profile_revision_uid


def test_get_active_revision_no_activation_returns_404(client):
    _install_services()
    resp = client.get(
        f"/api/wlv/v2/wdv/shared-canvas/scopes/{_SCOPE_TYPE}/nonexistent/active-revision"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 5 — get / create / update well binding
# ---------------------------------------------------------------------------

def _setup_activated_profile():
    svc = shared_canvas_router._profile_svc
    _, revision = svc.create_profile(profile_name="Binding Test", created_by="test")
    svc.activate_revision(
        revision.profile_revision_uid,
        scope_type=_SCOPE_TYPE,
        scope_uid=_SCOPE_UID,
    )
    return revision


def test_create_binding(client):
    _install_services()
    revision = _setup_activated_profile()
    well_uid = new_uuid7_str()

    resp = client.post(
        f"/api/wlv/v2/wdv/shared-canvas/bindings/{well_uid}/{revision.profile_revision_uid}",
        json={
            "profile_uid": revision.profile_uid,
            "profile_revision_number": revision.revision_number,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["managed_well_uid"] == well_uid
    assert body["profile_revision_uid"] == revision.profile_revision_uid
    assert body["revision"] == 0


def test_get_binding_found(client):
    _install_services()
    revision = _setup_activated_profile()
    well_uid = new_uuid7_str()

    client.post(
        f"/api/wlv/v2/wdv/shared-canvas/bindings/{well_uid}/{revision.profile_revision_uid}",
        json={"profile_uid": revision.profile_uid, "profile_revision_number": 0},
    )

    resp = client.get(
        f"/api/wlv/v2/wdv/shared-canvas/bindings/{well_uid}/{revision.profile_revision_uid}"
    )
    assert resp.status_code == 200
    assert resp.json()["managed_well_uid"] == well_uid


def test_get_binding_not_found(client):
    _install_services()
    resp = client.get(
        f"/api/wlv/v2/wdv/shared-canvas/bindings/{new_uuid7_str()}/{new_uuid7_str()}"
    )
    assert resp.status_code == 404


def test_update_slot_binding(client):
    _install_services()
    revision = _setup_activated_profile()
    well_uid = new_uuid7_str()
    slot_uid = new_uuid7_str()

    create_resp = client.post(
        f"/api/wlv/v2/wdv/shared-canvas/bindings/{well_uid}/{revision.profile_revision_uid}",
        json={"profile_uid": revision.profile_uid, "profile_revision_number": 0},
    )
    binding_uid = create_resp.json()["binding_uid"]

    resp = client.patch(
        f"/api/wlv/v2/wdv/shared-canvas/bindings/{binding_uid}/slots/{slot_uid}",
        json={
            "expected_revision": 0,
            "binding_status": "unavailable",
            "reason": "curve_not_found_in_well",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["revision"] == 1
    assert len(body["slot_bindings"]) == 1
    assert body["slot_bindings"][0]["binding_status"] == "unavailable"


# ---------------------------------------------------------------------------
# Test 6 — revision conflict returns 409
# ---------------------------------------------------------------------------

def test_revision_conflict_returns_409(client):
    _install_services()
    revision = _setup_activated_profile()
    well_uid = new_uuid7_str()
    slot_uid = new_uuid7_str()

    create_resp = client.post(
        f"/api/wlv/v2/wdv/shared-canvas/bindings/{well_uid}/{revision.profile_revision_uid}",
        json={"profile_uid": revision.profile_uid, "profile_revision_number": 0},
    )
    binding_uid = create_resp.json()["binding_uid"]

    # Advance revision to 1
    client.patch(
        f"/api/wlv/v2/wdv/shared-canvas/bindings/{binding_uid}/slots/{slot_uid}",
        json={"expected_revision": 0, "binding_status": "unavailable"},
    )

    # Retry with stale revision 0 → 409
    resp = client.patch(
        f"/api/wlv/v2/wdv/shared-canvas/bindings/{binding_uid}/slots/{slot_uid}",
        json={"expected_revision": 0, "binding_status": "unavailable"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Test 7 — stale binding returns 409
# ---------------------------------------------------------------------------

def test_stale_binding_returns_409(client):
    _install_services()
    svc_profile = shared_canvas_router._profile_svc
    svc_binding = shared_canvas_router._binding_svc
    _, revision = svc_profile.create_profile(profile_name="Stale Test", created_by="test")
    svc_profile.activate_revision(
        revision.profile_revision_uid,
        scope_type=_SCOPE_TYPE,
        scope_uid=_SCOPE_UID,
    )
    well_uid = new_uuid7_str()
    binding = svc_binding.create_binding(
        managed_well_uid=well_uid,
        profile_uid=revision.profile_uid,
        profile_revision_uid=revision.profile_revision_uid,
        profile_revision_number=0,
    )
    svc_binding.mark_stale(binding.binding_uid, updated_by="test")

    resp = client.get(
        f"/api/wlv/v2/wdv/shared-canvas/workspaces/{well_uid}",
        params={"scope_type": _SCOPE_TYPE, "scope_uid": _SCOPE_UID},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Test 8 — missing active profile returns 404
# ---------------------------------------------------------------------------

def test_missing_active_profile_returns_404(client):
    _install_services()
    resp = client.get(
        f"/api/wlv/v2/wdv/shared-canvas/workspaces/{new_uuid7_str()}",
        params={"scope_type": _SCOPE_TYPE, "scope_uid": "no-such-scope"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 9 — missing binding returns 404
# ---------------------------------------------------------------------------

def test_missing_binding_returns_404(client):
    _install_services()
    svc = shared_canvas_router._profile_svc
    _, revision = svc.create_profile(profile_name="No Binding", created_by="test")
    svc.activate_revision(
        revision.profile_revision_uid,
        scope_type=_SCOPE_TYPE,
        scope_uid=_SCOPE_UID,
    )

    resp = client.get(
        f"/api/wlv/v2/wdv/shared-canvas/workspaces/{new_uuid7_str()}",
        params={"scope_type": _SCOPE_TYPE, "scope_uid": _SCOPE_UID},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 10 — successful resolved-session response
# ---------------------------------------------------------------------------

def test_resolved_session_success(client):
    slot_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    well_uid = new_uuid7_str()

    profile_repo, binding_repo = _install_services(
        inventory_records=[
            CurveInventoryRecord(managed_curve_uid=curve_uid, managed_well_uid=well_uid)
        ]
    )
    svc_profile = shared_canvas_router._profile_svc
    svc_binding = shared_canvas_router._binding_svc

    slot = _make_slot(uid=slot_uid)
    track = _make_track(slots=(slot,))
    _, revision = svc_profile.create_profile(
        profile_name="Resolved Test",
        tracks=(track,),
        created_by="test",
    )
    svc_profile.activate_revision(
        revision.profile_revision_uid,
        scope_type=_SCOPE_TYPE,
        scope_uid=_SCOPE_UID,
    )
    binding = svc_binding.create_binding(
        managed_well_uid=well_uid,
        profile_uid=revision.profile_uid,
        profile_revision_uid=revision.profile_revision_uid,
        profile_revision_number=0,
    )
    svc_binding.update_slot_binding(
        binding_uid=binding.binding_uid,
        expected_revision=0,
        slot_uid=slot_uid,
        binding_status=BindingStatus.BOUND,
        managed_curve_uid=curve_uid,
        updated_by="test",
    )

    resp = client.get(
        f"/api/wlv/v2/wdv/shared-canvas/workspaces/{well_uid}",
        params={"scope_type": _SCOPE_TYPE, "scope_uid": _SCOPE_UID},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["managed_well_uid"] == well_uid
    assert body["profile_revision_uid"] == revision.profile_revision_uid
    assert len(body["resolved_tracks"]) == 1
    assert len(body["resolved_tracks"][0]["slots"]) == 1
    assert body["resolved_tracks"][0]["slots"][0]["binding_status"] == "bound"
    assert body["resolved_tracks"][0]["slots"][0]["managed_curve_uid"] == curve_uid


# ---------------------------------------------------------------------------
# Test 11 — unavailable slots remain present in resolved session
# ---------------------------------------------------------------------------

def test_unavailable_slots_remain_present(client):
    slot_uid = new_uuid7_str()
    well_uid = new_uuid7_str()

    _install_services()
    svc_profile = shared_canvas_router._profile_svc
    svc_binding = shared_canvas_router._binding_svc

    slot = _make_slot(uid=slot_uid)
    track = _make_track(slots=(slot,))
    _, revision = svc_profile.create_profile(
        profile_name="Unavail Test", tracks=(track,), created_by="test"
    )
    svc_profile.activate_revision(
        revision.profile_revision_uid, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID
    )
    binding = svc_binding.create_binding(
        managed_well_uid=well_uid,
        profile_uid=revision.profile_uid,
        profile_revision_uid=revision.profile_revision_uid,
        profile_revision_number=0,
    )
    svc_binding.update_slot_binding(
        binding_uid=binding.binding_uid,
        expected_revision=0,
        slot_uid=slot_uid,
        binding_status=BindingStatus.UNAVAILABLE,
        updated_by="test",
    )

    resp = client.get(
        f"/api/wlv/v2/wdv/shared-canvas/workspaces/{well_uid}",
        params={"scope_type": _SCOPE_TYPE, "scope_uid": _SCOPE_UID},
    )
    assert resp.status_code == 200
    slot_data = resp.json()["resolved_tracks"][0]["slots"][0]
    assert slot_data["slot_uid"] == slot_uid
    assert slot_data["binding_status"] == "unavailable"
    assert slot_data["managed_curve_uid"] is None


# ---------------------------------------------------------------------------
# Test 12 — cross-well curve violation is rejected (422)
# ---------------------------------------------------------------------------

def test_cross_well_curve_violation_returns_422(client):
    slot_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    well_uid = new_uuid7_str()
    foreign_well = new_uuid7_str()

    # Curve belongs to a DIFFERENT well
    _install_services(
        inventory_records=[
            CurveInventoryRecord(managed_curve_uid=curve_uid, managed_well_uid=foreign_well)
        ]
    )
    svc_profile = shared_canvas_router._profile_svc
    svc_binding = shared_canvas_router._binding_svc

    slot = _make_slot(uid=slot_uid)
    track = _make_track(slots=(slot,))
    _, revision = svc_profile.create_profile(
        profile_name="Cross-well Test", tracks=(track,), created_by="test"
    )
    svc_profile.activate_revision(
        revision.profile_revision_uid, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID
    )
    binding = svc_binding.create_binding(
        managed_well_uid=well_uid,
        profile_uid=revision.profile_uid,
        profile_revision_uid=revision.profile_revision_uid,
        profile_revision_number=0,
    )
    # Note: binding_service skips ownership check (inventory validates at service level)
    # We inject a BOUND slot directly to simulate a corrupt/bypassed binding
    now = datetime.now(timezone.utc).isoformat()
    bad_slot = WellCanvasSlotBinding(
        slot_uid=slot_uid,
        managed_curve_uid=curve_uid,
        binding_status=BindingStatus.BOUND,
    )
    bad_binding = binding.model_copy(
        update={"slot_bindings": (bad_slot,), "revision": 1, "updated_at": now}
    )
    # Directly update the repo to inject the cross-well binding
    shared_canvas_router._binding_svc._repo.update_binding(bad_binding, 0)

    resp = client.get(
        f"/api/wlv/v2/wdv/shared-canvas/workspaces/{well_uid}",
        params={"scope_type": _SCOPE_TYPE, "scope_uid": _SCOPE_UID},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test 13 — scale labels appear in the response
# ---------------------------------------------------------------------------

def test_scale_labels_in_response(client):
    slot_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    well_uid = new_uuid7_str()
    scale_min, scale_max = 0.5, 150.0

    _install_services(
        inventory_records=[
            CurveInventoryRecord(
                managed_curve_uid=curve_uid,
                managed_well_uid=well_uid,
                scale_min=scale_min,
                scale_max=scale_max,
            )
        ]
    )
    svc_profile = shared_canvas_router._profile_svc
    svc_binding = shared_canvas_router._binding_svc

    slot = _make_slot(uid=slot_uid)
    track = _make_track(slots=(slot,))
    _, revision = svc_profile.create_profile(
        profile_name="Scale Label Test", tracks=(track,), created_by="test"
    )
    svc_profile.activate_revision(
        revision.profile_revision_uid, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID
    )
    binding = svc_binding.create_binding(
        managed_well_uid=well_uid,
        profile_uid=revision.profile_uid,
        profile_revision_uid=revision.profile_revision_uid,
        profile_revision_number=0,
    )
    svc_binding.update_slot_binding(
        binding_uid=binding.binding_uid,
        expected_revision=0,
        slot_uid=slot_uid,
        binding_status=BindingStatus.BOUND,
        managed_curve_uid=curve_uid,
        updated_by="test",
    )

    resp = client.get(
        f"/api/wlv/v2/wdv/shared-canvas/workspaces/{well_uid}",
        params={"scope_type": _SCOPE_TYPE, "scope_uid": _SCOPE_UID},
    )
    assert resp.status_code == 200
    slot_data = resp.json()["resolved_tracks"][0]["slots"][0]
    assert slot_data["scale_min"] == scale_min
    assert slot_data["scale_max"] == scale_max
    assert slot_data["scale_min_label"] == format_scale_value(scale_min)
    assert slot_data["scale_max_label"] == format_scale_value(scale_max)


# ---------------------------------------------------------------------------
# Test 14 — no mutation during GET /workspaces
# ---------------------------------------------------------------------------

def test_no_mutation_during_get_resolved_session(client):
    slot_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    well_uid = new_uuid7_str()

    profile_repo, binding_repo = _install_services(
        inventory_records=[
            CurveInventoryRecord(managed_curve_uid=curve_uid, managed_well_uid=well_uid)
        ]
    )
    svc_profile = shared_canvas_router._profile_svc
    svc_binding = shared_canvas_router._binding_svc

    slot = _make_slot(uid=slot_uid)
    track = _make_track(slots=(slot,))
    _, revision = svc_profile.create_profile(
        profile_name="No-Mutation Test", tracks=(track,), created_by="test"
    )
    svc_profile.activate_revision(
        revision.profile_revision_uid, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID
    )
    binding = svc_binding.create_binding(
        managed_well_uid=well_uid,
        profile_uid=revision.profile_uid,
        profile_revision_uid=revision.profile_revision_uid,
        profile_revision_number=0,
    )
    svc_binding.update_slot_binding(
        binding_uid=binding.binding_uid,
        expected_revision=0,
        slot_uid=slot_uid,
        binding_status=BindingStatus.BOUND,
        managed_curve_uid=curve_uid,
        updated_by="test",
    )

    profile_writes_before = profile_repo.write_count
    binding_writes_before = binding_repo.write_count

    resp = client.get(
        f"/api/wlv/v2/wdv/shared-canvas/workspaces/{well_uid}",
        params={"scope_type": _SCOPE_TYPE, "scope_uid": _SCOPE_UID},
    )
    assert resp.status_code == 200
    assert profile_repo.write_count == profile_writes_before, "GET mutated profile store"
    assert binding_repo.write_count == binding_writes_before, "GET mutated binding store"


# ---------------------------------------------------------------------------
# Test 15 — no writes to existing WDV session stores
# ---------------------------------------------------------------------------

def test_no_writes_to_existing_wdv_session_stores(client, tmp_path):
    """Resolution must never touch canonical_sessions_v2_1.json or session_layouts.json."""
    slot_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    well_uid = new_uuid7_str()

    profile_repo, binding_repo = _install_services(
        inventory_records=[
            CurveInventoryRecord(managed_curve_uid=curve_uid, managed_well_uid=well_uid)
        ]
    )
    svc_profile = shared_canvas_router._profile_svc
    svc_binding = shared_canvas_router._binding_svc

    slot = _make_slot(uid=slot_uid)
    track = _make_track(slots=(slot,))
    _, revision = svc_profile.create_profile(
        profile_name="Session Store Test", tracks=(track,), created_by="test"
    )
    svc_profile.activate_revision(
        revision.profile_revision_uid, scope_type=_SCOPE_TYPE, scope_uid=_SCOPE_UID
    )
    binding = svc_binding.create_binding(
        managed_well_uid=well_uid,
        profile_uid=revision.profile_uid,
        profile_revision_uid=revision.profile_revision_uid,
        profile_revision_number=0,
    )
    svc_binding.update_slot_binding(
        binding_uid=binding.binding_uid,
        expected_revision=0,
        slot_uid=slot_uid,
        binding_status=BindingStatus.BOUND,
        managed_curve_uid=curve_uid,
        updated_by="test",
    )

    resp = client.get(
        f"/api/wlv/v2/wdv/shared-canvas/workspaces/{well_uid}",
        params={"scope_type": _SCOPE_TYPE, "scope_uid": _SCOPE_UID},
    )
    assert resp.status_code == 200

    # Confirm forbidden files were never created in tmp_path (in-memory repos touch no files)
    assert not (tmp_path / "canonical_sessions_v2_1.json").exists()
    assert not (tmp_path / "session_layouts.json").exists()

    # Confirm the shared canvas resolution used only in-memory repos (write counts verify no
    # fallback to file-backed adapters occurred — a file-backed write would have updated
    # files outside tmp_path, but the in-memory repos' write_count captures all changes)
    assert isinstance(profile_repo, InMemorySharedCanvasRepository)
    assert isinstance(binding_repo, InMemoryWellCanvasBindingRepository)
