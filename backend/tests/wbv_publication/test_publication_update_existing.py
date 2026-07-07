from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalAssignment, WdvCanonicalSession, WdvCanonicalTrack
from app.wbv_publication.models import (
    WbvCurvePresentationOverride,
    WbvPresentationOverrides,
    WbvPublishAsNewRequest,
    WbvTrackPresentationOverride,
    WbvUpdateExistingRequest,
)
from app.wbv_publication.repository import WbvOverlayPackageRepository
from app.wbv_publication.service import WbvOverlayPublicationService


def _assignment(well_uid: str, track_uid: str, mnemonic: str = "GR") -> WdvCanonicalAssignment:
    return WdvCanonicalAssignment(
        assignment_uid=new_uuid7_str(),
        track_uid=track_uid,
        managed_curve_uid=new_uuid7_str(),
        managed_product_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        managed_source_uid=new_uuid7_str(),
        observed_mnemonic=mnemonic,
        display_name=mnemonic,
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


def _session(well_uid: str, session_uid: str, revision: int, tracks: tuple[WdvCanonicalTrack, ...]) -> WdvCanonicalSession:
    return WdvCanonicalSession(
        session_uid=session_uid,
        managed_well_uid=well_uid,
        revision=revision,
        state_status="active",
        tracks=tracks,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


class MutableSessionService:
    def __init__(self, session: WdvCanonicalSession) -> None:
        self.session = session

    def get_session(self, managed_well_uid: str) -> WdvCanonicalSession:
        assert managed_well_uid == self.session.managed_well_uid
        return self.session


def test_update_existing_increments_revision_preserves_compatible_overrides_and_history(tmp_path: Path) -> None:
    well_uid, session_uid = new_uuid7_str(), new_uuid7_str()
    retained_track_uid, removed_track_uid = new_uuid7_str(), new_uuid7_str()
    retained_assignment = _assignment(well_uid, retained_track_uid, "GR")
    removed_assignment = _assignment(well_uid, removed_track_uid, "SP")
    initial = _session(
        well_uid,
        session_uid,
        7,
        (
            WdvCanonicalTrack(track_uid=retained_track_uid, managed_well_uid=well_uid, track_name="Track 1", assignments=(retained_assignment,)),
            WdvCanonicalTrack(track_uid=removed_track_uid, managed_well_uid=well_uid, track_name="Track 2", assignments=(removed_assignment,)),
        ),
    )
    sessions = MutableSessionService(initial)
    repository = WbvOverlayPackageRepository(tmp_path / "packages.json")
    service = WbvOverlayPublicationService(repository, sessions)
    package = service.publish_as_new(
        well_uid,
        WbvPublishAsNewRequest(package_name="Published", command_uid=new_uuid7_str(), activate=True),
    )
    package = package.model_copy(update={
        "wbv_overrides": WbvPresentationOverrides(
            tracks=(
                WbvTrackPresentationOverride(track_uid=retained_track_uid, radial_lane=1),
                WbvTrackPresentationOverride(track_uid=removed_track_uid, radial_lane=2),
            ),
            curves=(
                WbvCurvePresentationOverride(assignment_uid=retained_assignment.assignment_uid, radial_exaggeration=2),
                WbvCurvePresentationOverride(assignment_uid=removed_assignment.assignment_uid, radial_exaggeration=3),
            ),
        )
    })
    repository.replace_existing(package, expected_package_revision=1)

    added_track_uid = new_uuid7_str()
    added_assignment = _assignment(well_uid, added_track_uid, "RHOB")
    changed_retained_assignment = retained_assignment.model_copy(update={"line_width": 2.0})
    sessions.session = _session(
        well_uid,
        session_uid,
        8,
        (
            WdvCanonicalTrack(track_uid=retained_track_uid, managed_well_uid=well_uid, track_name="Track 1", assignments=(changed_retained_assignment,)),
            WdvCanonicalTrack(track_uid=added_track_uid, managed_well_uid=well_uid, track_name="Track 3", assignments=(added_assignment,)),
        ),
    )

    preview = service.preview_update(well_uid, package.package_uid)
    assert preview.update_available is True
    assert preview.changes.tracks_added == (added_track_uid,)
    assert preview.changes.tracks_removed == (removed_track_uid,)
    assert retained_assignment.assignment_uid in preview.changes.assignments_changed
    assert preview.changes.retained_track_override_count == 1
    assert preview.changes.dropped_track_override_count == 1

    command_uid = new_uuid7_str()
    result = service.update_existing(
        well_uid,
        package.package_uid,
        WbvUpdateExistingRequest(
            command_uid=command_uid,
            expected_package_revision=1,
            activate=True,
        ),
    )
    updated = result.package
    assert updated.package_revision == 2
    assert updated.source_wdv_revision == 8
    assert len(updated.revision_history) == 1
    assert updated.revision_history[0].published_snapshot == initial
    updated_track_overrides = {item.track_uid: item for item in updated.wbv_overrides.tracks}
    assert set(updated_track_overrides) == {retained_track_uid, added_track_uid}
    assert updated_track_overrides[retained_track_uid].radial_lane == 1
    assert updated_track_overrides[added_track_uid].destination_track_uid is not None
    assert (
        updated_track_overrides[added_track_uid].destination_track_uid
        != updated_track_overrides[retained_track_uid].destination_track_uid
    )
    assert [item.assignment_uid for item in updated.wbv_overrides.curves] == [retained_assignment.assignment_uid]
    assert updated.provenance.operation == "update_existing"

    reloaded = WbvOverlayPackageRepository(tmp_path / "packages.json").get(package.package_uid)
    assert reloaded == updated

    replay = service.update_existing(
        well_uid,
        package.package_uid,
        WbvUpdateExistingRequest(command_uid=command_uid, expected_package_revision=1, activate=True),
    )
    assert replay.package == updated


def test_update_existing_rejects_stale_package_revision(tmp_path: Path) -> None:
    well_uid, session_uid, track_uid = new_uuid7_str(), new_uuid7_str(), new_uuid7_str()
    assignment = _assignment(well_uid, track_uid)
    session = _session(
        well_uid,
        session_uid,
        1,
        (WdvCanonicalTrack(track_uid=track_uid, managed_well_uid=well_uid, track_name="Track", assignments=(assignment,)),),
    )
    service = WbvOverlayPublicationService(
        WbvOverlayPackageRepository(tmp_path / "packages.json"),
        MutableSessionService(session),
    )
    package = service.publish_as_new(
        well_uid,
        WbvPublishAsNewRequest(package_name="Published", command_uid=new_uuid7_str()),
    )
    with pytest.raises(ValueError, match="Stale package revision"):
        service.update_existing(
            well_uid,
            package.package_uid,
            WbvUpdateExistingRequest(
                command_uid=new_uuid7_str(),
                expected_package_revision=99,
            ),
        )


def test_update_preview_returns_false_boolean_when_source_is_unchanged(tmp_path: Path) -> None:
    well_uid, session_uid, track_uid = new_uuid7_str(), new_uuid7_str(), new_uuid7_str()
    assignment = _assignment(well_uid, track_uid)
    session = _session(
        well_uid,
        session_uid,
        5,
        (
            WdvCanonicalTrack(
                track_uid=track_uid,
                managed_well_uid=well_uid,
                track_name="Track",
                assignments=(assignment,),
            ),
        ),
    )
    service = WbvOverlayPublicationService(
        WbvOverlayPackageRepository(tmp_path / "packages.json"),
        MutableSessionService(session),
    )
    package = service.publish_as_new(
        well_uid,
        WbvPublishAsNewRequest(
            command_uid=new_uuid7_str(),
            package_name="No Change",
            activate=True,
        ),
    )

    preview = service.preview_update(well_uid, package.package_uid)

    assert preview.update_available is False
    assert isinstance(preview.update_available, bool)
