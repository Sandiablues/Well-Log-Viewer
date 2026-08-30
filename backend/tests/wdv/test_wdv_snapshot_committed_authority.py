from pathlib import Path

import pytest

from app.identity import new_uuid7_str
from app.wdv_session.canonical_service import (
    CanonicalViewRevisionConflict,
    CanonicalWdvSessionService,
)


def _service(tmp_path: Path) -> CanonicalWdvSessionService:
    return CanonicalWdvSessionService(storage_path=tmp_path / "canonical_sessions.json")


def _view(minimum: float, maximum: float) -> dict:
    return {
        "depth_unit": "m",
        "global_viewport": {"min": minimum, "max": maximum},
        "group_viewport": None,
        "active_track_uids": [],
        "highlighted_track_uids": [],
        "locked_track_uids": [],
        "locked_viewports_by_track_uid": {},
        "track_viewports_by_track_uid": {},
        "viewport_tie_groups": [],
        "viewport_tie_suspended_track_uids": [],
        "presentation_state": {},
    }


def test_explicit_snapshot_copies_exact_committed_view(tmp_path: Path):
    service = _service(tmp_path)
    well_uid = new_uuid7_str()
    session = service.get_session(well_uid)
    committed = service.commit_workspace_view_state(
        well_uid,
        expected_session_revision=session.revision,
        expected_view_revision=-1,
        view_state=_view(1000.0, 1100.0),
    )

    saved = service.save_workspace_snapshot_from_committed_view(
        well_uid,
        expected_revision=session.revision,
        expected_view_revision=committed["view_revision"],
    )

    assert saved["view_state"] == committed["view_state"]
    assert saved["view_revision"] == committed["view_revision"]
    stored = service.get_workspace_snapshot(well_uid)
    assert stored is not None
    assert stored["view_state"] == committed["view_state"]


def test_recovery_copies_exact_committed_view(tmp_path: Path):
    service = _service(tmp_path)
    well_uid = new_uuid7_str()
    session = service.get_session(well_uid)
    committed = service.commit_workspace_view_state(
        well_uid,
        expected_session_revision=session.revision,
        expected_view_revision=-1,
        view_state=_view(2000.0, 2010.0),
    )

    recovery = service.save_workspace_recovery_from_committed_view(
        well_uid,
        expected_revision=session.revision,
        expected_view_revision=committed["view_revision"],
    )

    assert recovery["view_state"] == committed["view_state"]
    assert recovery["view_revision"] == committed["view_revision"]
    stored = service.get_workspace_recovery_state(well_uid)
    assert stored is not None
    assert stored["view_state"] == committed["view_state"]


def test_snapshot_rejects_stale_expected_view_revision(tmp_path: Path):
    service = _service(tmp_path)
    well_uid = new_uuid7_str()
    session = service.get_session(well_uid)
    service.commit_workspace_view_state(
        well_uid,
        expected_session_revision=session.revision,
        expected_view_revision=-1,
        view_state=_view(1000.0, 1100.0),
    )

    with pytest.raises(CanonicalViewRevisionConflict):
        service.save_workspace_snapshot_from_committed_view(
            well_uid,
            expected_revision=session.revision,
            expected_view_revision=-1,
        )


def test_recovery_requires_a_committed_view(tmp_path: Path):
    service = _service(tmp_path)
    well_uid = new_uuid7_str()
    session = service.get_session(well_uid)

    with pytest.raises(CanonicalViewRevisionConflict):
        service.save_workspace_recovery_from_committed_view(
            well_uid,
            expected_revision=session.revision,
            expected_view_revision=-1,
        )
