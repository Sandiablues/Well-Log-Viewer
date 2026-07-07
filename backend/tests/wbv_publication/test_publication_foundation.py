from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalAssignment, WdvCanonicalSession, WdvCanonicalTrack
from app.wbv_publication.models import WbvPublishAsNewRequest, WbvPublishPreviewRequest
from app.wbv_publication.repository import WbvOverlayPackageRepository
from app.wbv_publication.service import WbvOverlayPublicationService


def _assignment(well_uid: str, track_uid: str) -> WdvCanonicalAssignment:
    return WdvCanonicalAssignment(
        assignment_uid=new_uuid7_str(),
        track_uid=track_uid,
        managed_curve_uid=new_uuid7_str(),
        managed_product_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        managed_source_uid=new_uuid7_str(),
        observed_mnemonic="GR",
        display_name="Gamma Ray",
        unit="gAPI",
        stack_index=0,
        visible=True,
        scale_min=0.0,
        scale_max=150.0,
        scale_type="linear",
        scale_direction="normal",
        color="#00ff00",
        line_width=1.0,
        line_opacity=100,
    )


def _session() -> WdvCanonicalSession:
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    assignment = _assignment(well_uid, track_uid)
    return WdvCanonicalSession(
        session_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        revision=7,
        state_status="active",
        tracks=(WdvCanonicalTrack(
            track_uid=track_uid,
            managed_well_uid=well_uid,
            track_name="Track 1",
            assignments=(assignment,),
        ),),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


class StubSessionService:
    def __init__(self, session: WdvCanonicalSession) -> None:
        self.session = session

    def get_session(self, managed_well_uid: str) -> WdvCanonicalSession:
        assert managed_well_uid == self.session.managed_well_uid
        return self.session


def test_publish_as_new_retains_immutable_wdv_snapshot(tmp_path: Path) -> None:
    session = _session()
    repository = WbvOverlayPackageRepository(tmp_path / "packages.json")
    service = WbvOverlayPublicationService(repository, StubSessionService(session))
    command_uid = new_uuid7_str()

    preview = service.preview(session.managed_well_uid, WbvPublishPreviewRequest(package_name="Triple Combo"))
    assert preview.publishable is True
    assert preview.assignment_count == 1

    package = service.publish_as_new(
        session.managed_well_uid,
        WbvPublishAsNewRequest(
            package_name="Triple Combo",
            command_uid=command_uid,
            activate=True,
        ),
    )
    assert package.source_wdv_revision == 7
    assert package.published_snapshot == session
    assert package.status == "active"

    reloaded = WbvOverlayPackageRepository(tmp_path / "packages.json").get(package.package_uid)
    assert reloaded == package

    replay = service.publish_as_new(
        session.managed_well_uid,
        WbvPublishAsNewRequest(
            package_name="Ignored replay name",
            command_uid=command_uid,
            activate=False,
        ),
    )
    assert replay.package_uid == package.package_uid


def test_only_one_active_package_per_well(tmp_path: Path) -> None:
    session = _session()
    service = WbvOverlayPublicationService(
        WbvOverlayPackageRepository(tmp_path / "packages.json"),
        StubSessionService(session),
    )
    first = service.publish_as_new(
        session.managed_well_uid,
        WbvPublishAsNewRequest(package_name="A", command_uid=new_uuid7_str(), activate=True),
    )
    second = service.publish_as_new(
        session.managed_well_uid,
        WbvPublishAsNewRequest(package_name="B", command_uid=new_uuid7_str(), activate=True),
    )
    packages = service.list_packages(session.managed_well_uid).packages
    by_uid = {item.package_uid: item for item in packages}
    assert by_uid[first.package_uid].status == "inactive"
    assert by_uid[second.package_uid].status == "active"
