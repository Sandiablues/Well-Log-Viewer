from datetime import datetime, timezone

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalSession
from app.identity.wdv_viewer_package_v21 import (
    WdvCanonicalDepthRange,
    WdvCanonicalViewerPackage,
)
from app.wdv_workspace.service import CanonicalWdvWorkspaceService


class FakeViewerPackageService:
    def __init__(self, package: WdvCanonicalViewerPackage) -> None:
        self.package = package
        self.calls: list[str] = []

    def generate(self, managed_well_uid: str) -> WdvCanonicalViewerPackage:
        self.calls.append(managed_well_uid)
        return self.package


def test_workspace_service_returns_single_validated_aggregate() -> None:
    well_uid = new_uuid7_str()
    package = WdvCanonicalViewerPackage(
        managed_well_uid=well_uid,
        well_name="Test Well",
        depth_range=WdvCanonicalDepthRange(unit="ft"),
        session=WdvCanonicalSession(
            session_uid=new_uuid7_str(),
            managed_well_uid=well_uid,
            state_status="empty",
            updated_at=datetime.now(timezone.utc).isoformat(),
        ),
    )
    fake = FakeViewerPackageService(package)
    service = CanonicalWdvWorkspaceService(fake)

    workspace = service.get_workspace(well_uid)

    assert fake.calls == [well_uid]
    assert workspace.managed_well_uid == well_uid
    assert workspace.session.managed_well_uid == well_uid
    assert workspace.curve_registry == ()
