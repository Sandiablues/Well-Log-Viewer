from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalSession, WdvCanonicalTrack
from app.saved_canvas.models import SavedCanvasCreateRequest
from app.saved_canvas.repository import SavedCanvasNotFoundError, SavedCanvasRepository
from app.saved_canvas.service import SavedCanvasService
from app.wdv_workspace.models import (
    WdvSavedDepthViewport,
    WdvSavedViewportTieGroup,
    WdvSavedViewState,
)


class FakeInventory:
    def __init__(self, active_well_uid: str):
        self.workspace_id = "default"
        self.revision = 10
        self.active_well_uid = active_well_uid

    def get_wdv_workspace(self):
        return SimpleNamespace(
            workspace_id=self.workspace_id,
            revision=self.revision,
            active_managed_well_uid=self.active_well_uid,
            common_depth_unit="m",
        )


class FakeSessionService:
    def __init__(self, session: WdvCanonicalSession):
        self.session = session

    def get_session(self, _managed_well_uid: str):
        return self.session


def make_session(*, width: int = 140):
    well_a = new_uuid7_str()
    well_b = new_uuid7_str()
    track_a = WdvCanonicalTrack(
        track_uid=new_uuid7_str(), managed_well_uid=well_a, track_name="T1", track_type="depth", width_px=72
    )
    track_b = WdvCanonicalTrack(
        track_uid=new_uuid7_str(), managed_well_uid=well_b, track_name="T2", track_type="curve", width_px=width
    )
    session = WdvCanonicalSession(
        session_uid=new_uuid7_str(),
        managed_well_uid=well_a,
        revision=21,
        state_status="active",
        selected_track_uid=track_b.track_uid,
        tracks=(track_a, track_b),
        updated_at="2026-08-16T08:00:00+00:00",
    )
    return session, track_a, track_b


def make_view(track_a, track_b, *, viewport_max: float):
    return WdvSavedViewState(
        global_viewport=WdvSavedDepthViewport(min=1000.0, max=viewport_max),
        active_track_uids=(track_b.track_uid,),
        highlighted_track_uids=(track_b.track_uid,),
        track_viewports_by_track_uid={
            track_a.track_uid: WdvSavedDepthViewport(min=1000.0, max=viewport_max),
            track_b.track_uid: WdvSavedDepthViewport(min=1000.0, max=viewport_max),
        },
    )


def canonical_payload(record):
    data = record.model_dump(mode="json")
    data.pop("saved_canvas_uid", None)
    data.pop("created_at", None)
    data["name"] = "<normalized>"
    return data


def test_a_b_c_are_independent_immutable_snapshots(tmp_path: Path):
    session, track_a, track_b = make_session()
    inventory = FakeInventory(session.managed_well_uid)
    repository = SavedCanvasRepository(tmp_path / "saved_canvases.json")
    fake_session = FakeSessionService(session)
    service = SavedCanvasService(inventory_service=inventory, session_service=fake_session, repository=repository)

    a = service.create("default", SavedCanvasCreateRequest(name="A", expected_workspace_revision=10, view_state=make_view(track_a, track_b, viewport_max=1100)))

    fake_session.session = session.model_copy(update={
        "revision": 22,
        "tracks": (track_a, track_b.model_copy(update={"width_px": 220})),
    })
    b = service.create("default", SavedCanvasCreateRequest(name="B", expected_workspace_revision=10, view_state=make_view(track_a, track_b, viewport_max=1200)))

    fake_session.session = session.model_copy(update={
        "revision": 23,
        "tracks": (track_b.model_copy(update={"width_px": 310}), track_a),
    })
    c = service.create("default", SavedCanvasCreateRequest(name="C", expected_workspace_revision=10, view_state=make_view(track_a, track_b, viewport_max=1300)))

    assert a.saved_canvas_uid != b.saved_canvas_uid != c.saved_canvas_uid
    assert canonical_payload(a) != canonical_payload(b)
    assert canonical_payload(b) != canonical_payload(c)
    assert canonical_payload(a) != canonical_payload(c)

    a_after = service.get("default", a.saved_canvas_uid)
    assert a_after == a
    assert a_after.snapshot.session.selected_track_uid is None
    assert a_after.snapshot.view_state.active_track_uids == ()
    assert a_after.snapshot.view_state.highlighted_track_uids == ()


def test_list_is_workspace_level_and_independent_of_active_well(tmp_path: Path):
    session, track_a, track_b = make_session()
    inventory = FakeInventory(session.managed_well_uid)
    service = SavedCanvasService(
        inventory_service=inventory,
        session_service=FakeSessionService(session),
        repository=SavedCanvasRepository(tmp_path / "saved_canvases.json"),
    )
    saved = service.create("default", SavedCanvasCreateRequest(name="Canvas", expected_workspace_revision=10, view_state=make_view(track_a, track_b, viewport_max=1200)))
    before = service.list("default")
    inventory.active_well_uid = new_uuid7_str()
    inventory.revision = 11
    after = service.list("default")
    assert before == after
    assert after[0].saved_canvas_uid == saved.saved_canvas_uid


def test_delete_is_physical_and_does_not_reappear(tmp_path: Path):
    session, track_a, track_b = make_session()
    inventory = FakeInventory(session.managed_well_uid)
    path = tmp_path / "saved_canvases.json"
    service = SavedCanvasService(
        inventory_service=inventory,
        session_service=FakeSessionService(session),
        repository=SavedCanvasRepository(path),
    )
    saved = service.create("default", SavedCanvasCreateRequest(name="Delete Me", expected_workspace_revision=10, view_state=make_view(track_a, track_b, viewport_max=1200)))
    service.delete("default", saved.saved_canvas_uid)
    assert service.list("default") == []
    with pytest.raises(SavedCanvasNotFoundError):
        service.get("default", saved.saved_canvas_uid)
    raw = json.loads(path.read_text())
    assert raw["workspaces"]["default"]["saved_canvases"] == []


def test_lock_and_tie_are_preserved_in_immutable_snapshot(tmp_path: Path):
    session, track_a, track_b = make_session()
    inventory = FakeInventory(session.managed_well_uid)
    service = SavedCanvasService(
        inventory_service=inventory,
        session_service=FakeSessionService(session),
        repository=SavedCanvasRepository(tmp_path / "saved_canvases.json"),
    )
    locked_range = WdvSavedDepthViewport(min=1010.0, max=1060.0)
    tie_range = WdvSavedDepthViewport(min=1020.0, max=1080.0)
    view = WdvSavedViewState(
        global_viewport=WdvSavedDepthViewport(min=1000.0, max=1100.0),
        locked_track_uids=(track_b.track_uid,),
        locked_viewports_by_track_uid={track_b.track_uid: locked_range},
        track_viewports_by_track_uid={
            track_a.track_uid: tie_range,
            track_b.track_uid: locked_range,
        },
        viewport_tie_groups=(
            WdvSavedViewportTieGroup(
                group_id="tie-1",
                leader_track_uid=track_a.track_uid,
                member_track_uids=(track_a.track_uid, track_b.track_uid),
                viewport=tie_range,
            ),
        ),
        viewport_tie_suspended_track_uids=(track_b.track_uid,),
    )
    saved = service.create(
        "default",
        SavedCanvasCreateRequest(name="Lock Tie", expected_workspace_revision=10, view_state=view),
    )
    restored_record = service.get("default", saved.saved_canvas_uid)
    assert restored_record.snapshot.view_state.locked_track_uids == (track_b.track_uid,)
    assert restored_record.snapshot.view_state.locked_viewports_by_track_uid[track_b.track_uid] == locked_range
    assert restored_record.snapshot.view_state.viewport_tie_groups[0].leader_track_uid == track_a.track_uid
    assert restored_record.snapshot.view_state.viewport_tie_groups[0].member_track_uids == (track_a.track_uid, track_b.track_uid)
    assert restored_record.snapshot.view_state.viewport_tie_suspended_track_uids == (track_b.track_uid,)
