from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalAssignment, WdvCanonicalSession, WdvCanonicalTrack
from app.wbv_publication.models import (
    WbvPackageLifecycleRequest,
    WbvPresentationOverrides,
    WbvPresentationOverridesUpdateRequest,
    WbvPublishAsNewRequest,
    WbvTrackPresentationOverride,
)
from app.wbv_publication.repository import WbvOverlayPackageRepository
from app.wbv_publication.service import WbvOverlayPublicationService


def _session() -> WdvCanonicalSession:
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    assignment = WdvCanonicalAssignment(
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


def test_archive_clears_assignments_and_restore_preserves_snapshot(tmp_path: Path) -> None:
    session = _session()
    repository = WbvOverlayPackageRepository(tmp_path / "packages.json")
    service = WbvOverlayPublicationService(repository, StubSessionService(session))
    package = service.publish_as_new(
        session.managed_well_uid,
        WbvPublishAsNewRequest(
            package_name="Published",
            command_uid=new_uuid7_str(),
            activate=True,
        ),
    )
    source_track_uid = session.tracks[0].track_uid
    destination_track_uid = new_uuid7_str()
    package = service.update_presentation_overrides(
        session.managed_well_uid,
        package.package_uid,
        WbvPresentationOverridesUpdateRequest(
            expected_package_revision=package.package_revision,
            overrides=WbvPresentationOverrides(
                package_visible=True,
                tracks=(WbvTrackPresentationOverride(
                    track_uid=source_track_uid,
                    destination_track_uid=destination_track_uid,
                ),),
            ),
        ),
    )

    archived = service.change_lifecycle(
        session.managed_well_uid,
        package.package_uid,
        WbvPackageLifecycleRequest(
            expected_package_revision=package.package_revision,
            action="archive",
        ),
    )

    assert archived.status == "archived"
    assert archived.package_revision == package.package_revision + 1
    assert archived.wbv_overrides.package_visible is False
    assert archived.wbv_overrides.tracks[0].destination_track_uid is None
    assert archived.published_snapshot == session
    assert service.list_packages(session.managed_well_uid).packages == ()
    assert service.list_packages(session.managed_well_uid, include_archived=True).packages == (archived,)

    restored = service.change_lifecycle(
        session.managed_well_uid,
        archived.package_uid,
        WbvPackageLifecycleRequest(
            expected_package_revision=archived.package_revision,
            action="restore",
        ),
    )

    assert restored.status == "inactive"
    assert restored.package_revision == archived.package_revision + 1
    assert restored.published_snapshot == session
    assert restored.wbv_overrides.package_visible is False
    assert restored.wbv_overrides.tracks[0].destination_track_uid is None
