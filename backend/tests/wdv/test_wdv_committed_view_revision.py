from pathlib import Path

import pytest

from app.identity import new_uuid7_str
from app.wdv_session.canonical_service import (
    CanonicalSessionRevisionConflict,
    CanonicalViewRevisionConflict,
    CanonicalWdvSessionService,
)
from app.wdv_workspace.models import WdvSavedViewState
from app.wdv_workspace.service import CanonicalWdvWorkspaceService


def _view_state() -> WdvSavedViewState:
    return WdvSavedViewState(
        global_viewport={"min": 1000.0, "max": 1100.0},
    )


def _services(tmp_path: Path):
    session_service = CanonicalWdvSessionService(
        storage_path=tmp_path / "canonical_sessions.json"
    )
    workspace_service = CanonicalWdvWorkspaceService(
        session_service=session_service,
    )
    return session_service, workspace_service


def test_committed_view_has_independent_monotonic_revision(tmp_path: Path):
    session_service, workspace_service = _services(tmp_path)
    well_uid = new_uuid7_str()
    session = session_service.get_session(well_uid)

    first = workspace_service.commit_view_state(
        well_uid,
        expected_session_revision=session.revision,
        expected_view_revision=-1,
        view_state=_view_state(),
    )
    assert first["view_revision"] == 0
    assert first["session_revision"] == session.revision

    second = workspace_service.commit_view_state(
        well_uid,
        expected_session_revision=session.revision,
        expected_view_revision=0,
        view_state=_view_state(),
    )
    assert second["view_revision"] == 1


def test_stale_view_revision_is_rejected(tmp_path: Path):
    session_service, workspace_service = _services(tmp_path)
    well_uid = new_uuid7_str()
    session = session_service.get_session(well_uid)
    workspace_service.commit_view_state(
        well_uid,
        expected_session_revision=session.revision,
        expected_view_revision=-1,
        view_state=_view_state(),
    )

    with pytest.raises(CanonicalViewRevisionConflict):
        workspace_service.commit_view_state(
            well_uid,
            expected_session_revision=session.revision,
            expected_view_revision=-1,
            view_state=_view_state(),
        )


def test_stale_session_revision_is_rejected(tmp_path: Path):
    session_service, workspace_service = _services(tmp_path)
    well_uid = new_uuid7_str()
    session = session_service.get_session(well_uid)
    advanced = session_service.mutate_session_transactionally(
        well_uid,
        expected_revision=session.revision,
        mutation=lambda current: current,
    )

    with pytest.raises(CanonicalSessionRevisionConflict):
        workspace_service.commit_view_state(
            well_uid,
            expected_session_revision=session.revision,
            expected_view_revision=-1,
            view_state=_view_state(),
        )
    assert advanced.revision == session.revision + 1


def test_old_session_view_becomes_stale_and_new_chain_restarts(tmp_path: Path):
    session_service, workspace_service = _services(tmp_path)
    well_uid = new_uuid7_str()
    session = session_service.get_session(well_uid)
    workspace_service.commit_view_state(
        well_uid,
        expected_session_revision=session.revision,
        expected_view_revision=-1,
        view_state=_view_state(),
    )

    advanced = session_service.mutate_session_transactionally(
        well_uid,
        expected_revision=session.revision,
        mutation=lambda current: current,
    )
    stale = workspace_service.get_committed_view_state(well_uid)
    assert stale["available"] is False
    assert stale["stale"] is True
    assert stale["view_revision"] == -1

    fresh = workspace_service.commit_view_state(
        well_uid,
        expected_session_revision=advanced.revision,
        expected_view_revision=-1,
        view_state=_view_state(),
    )
    assert fresh["view_revision"] == 0
