from datetime import datetime, timezone

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalSession
from app.identity.wdv_viewer_package_v21 import WdvCanonicalDepthRange, WdvCanonicalViewerPackage
from app.wdv_workspace.service import CanonicalWdvWorkspaceService


class FakeViewerPackageService:
    def __init__(self, package: WdvCanonicalViewerPackage) -> None:
        self.package = package

    def generate(self, managed_well_uid: str) -> WdvCanonicalViewerPackage:
        return self.package


class FakeSessionService:
    def __init__(self, recovery: dict | None) -> None:
        self.recovery = recovery

    def get_workspace_recovery_state(self, managed_well_uid: str) -> dict | None:
        return self.recovery


def make_service(*, revision: int, recovery: dict | None) -> CanonicalWdvWorkspaceService:
    well_uid = new_uuid7_str()
    session = WdvCanonicalSession(
        session_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        revision=revision,
        state_status="empty",
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    package = WdvCanonicalViewerPackage(
        managed_well_uid=well_uid,
        well_name="Recovery Authority Test",
        depth_range=WdvCanonicalDepthRange(unit="m"),
        session=session,
    )
    return CanonicalWdvWorkspaceService(
        viewer_package_service=FakeViewerPackageService(package),
        session_service=FakeSessionService(recovery),
    )


def valid_view_state() -> dict:
    return {
        "depth_unit": "m",
        "global_viewport": {"min": 1000.0, "max": 1100.0},
        "group_viewport": None,
        "active_track_uids": [],
        "highlighted_track_uids": [],
        "locked_track_uids": [],
        "locked_viewports_by_track_uid": {},
        "presentation_state": {},
    }


def test_recovery_is_available_only_for_exact_canonical_revision() -> None:
    service = make_service(
        revision=7,
        recovery={"saved_at": "2026-08-13T07:30:00+00:00", "session_revision": 7, "view_state": valid_view_state()},
    )
    result = service.get_recovery_state(service.viewer_package_service.package.managed_well_uid)
    assert result["available"] is True
    assert result["stale"] is False
    assert result["session_revision"] == 7
    assert result["current_session_revision"] == 7
    assert result["view_state"]["global_viewport"] == {"min": 1000.0, "max": 1100.0}


def test_stale_recovery_is_not_exposed_to_frontend() -> None:
    service = make_service(
        revision=8,
        recovery={"saved_at": "2026-08-13T07:30:00+00:00", "session_revision": 7, "view_state": valid_view_state()},
    )
    result = service.get_recovery_state(service.viewer_package_service.package.managed_well_uid)
    assert result["available"] is False
    assert result["stale"] is True
    assert result["session_revision"] == 7
    assert result["current_session_revision"] == 8
    assert result["view_state"] is None


def test_missing_recovery_revision_is_treated_as_stale() -> None:
    service = make_service(
        revision=8,
        recovery={"saved_at": "2026-08-13T07:30:00+00:00", "view_state": valid_view_state()},
    )
    result = service.get_recovery_state(service.viewer_package_service.package.managed_well_uid)
    assert result["available"] is False
    assert result["stale"] is True
    assert result["session_revision"] is None
    assert result["current_session_revision"] == 8
    assert result["view_state"] is None


def test_stale_recovery_payload_is_not_parsed() -> None:
    service = make_service(
        revision=9,
        recovery={"saved_at": "2026-08-13T07:30:00+00:00", "session_revision": 8, "view_state": {"corrupt": True}},
    )
    result = service.get_recovery_state(service.viewer_package_service.package.managed_well_uid)
    assert result["available"] is False
    assert result["stale"] is True
    assert result["view_state"] is None


def test_absent_recovery_is_unavailable_but_not_stale() -> None:
    service = make_service(revision=3, recovery=None)
    result = service.get_recovery_state(service.viewer_package_service.package.managed_well_uid)
    assert result == {
        "available": False,
        "saved_at": None,
        "session_revision": None,
        "current_session_revision": None,
        "stale": False,
        "view_state": None,
    }
