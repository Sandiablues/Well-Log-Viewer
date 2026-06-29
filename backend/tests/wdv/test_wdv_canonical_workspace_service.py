from datetime import datetime, timezone

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import (
    WdvCanonicalAssignment,
    WdvCanonicalSession,
    WdvCanonicalTrack,
)
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


def test_viewer_package_accepts_foreign_well_tracks_in_shared_session() -> None:
    active_well_uid = new_uuid7_str()
    foreign_well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    assignment = WdvCanonicalAssignment(
        assignment_uid=new_uuid7_str(),
        managed_curve_uid=new_uuid7_str(),
        managed_product_uid=new_uuid7_str(),
        managed_well_uid=foreign_well_uid,
        managed_wellbore_uid=new_uuid7_str(),
        managed_source_uid=new_uuid7_str(),
        track_uid=track_uid,
        observed_mnemonic="GR",
        display_name="Foreign GR",
    )
    session = WdvCanonicalSession(
        session_uid=new_uuid7_str(),
        managed_well_uid=active_well_uid,
        state_status="active",
        tracks=(WdvCanonicalTrack(
            track_uid=track_uid,
            managed_well_uid=foreign_well_uid,
            track_name="Foreign",
            assignments=(assignment,),
        ),),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

    package = WdvCanonicalViewerPackage(
        managed_well_uid=active_well_uid,
        well_name="Active Well",
        depth_range=WdvCanonicalDepthRange(unit="ft"),
        curves=(),
        session=session,
    )
    assert package.session.tracks[0].managed_well_uid == foreign_well_uid
