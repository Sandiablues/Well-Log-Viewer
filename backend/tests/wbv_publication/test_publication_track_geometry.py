from __future__ import annotations

from datetime import datetime, timezone

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import (
    WdvCanonicalAssignment,
    WdvCanonicalSession,
    WdvCanonicalTrack,
    WdvCurveSampleProvenance,
    WdvCurveSampleResponse,
)
from app.wbv_publication.adapter import WbvPublishedPackageRenderAdapter
from app.wbv_publication.models import (
    WbvOverlayPackage,
    WbvPresentationOverrides,
    WbvPublicationProvenance,
    WbvTrackPresentationOverride,
)


def _fixture():
    (
        well,
        track,
        assignment,
        curve,
        product,
        source,
        session_uid,
        package_uid,
        command_uid,
    ) = [new_uuid7_str() for _ in range(9)]

    assignment_contract = WdvCanonicalAssignment(
        assignment_uid=assignment,
        managed_curve_uid=curve,
        managed_product_uid=product,
        managed_well_uid=well,
        managed_source_uid=source,
        track_uid=track,
        observed_mnemonic="GR",
        display_name="Gamma Ray",
        unit="gAPI",
        scale_min=0,
        scale_max=100,
        scale_type="linear",
        scale_direction="normal",
        color="#00ff00",
        line_width=2,
        line_opacity=80,
    )
    session = WdvCanonicalSession(
        session_uid=session_uid,
        managed_well_uid=well,
        revision=7,
        state_status="active",
        tracks=(
            WdvCanonicalTrack(
                track_uid=track,
                managed_well_uid=well,
                track_name="Track 1",
                assignments=(assignment_contract,),
            ),
        ),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    now = datetime.now(timezone.utc).isoformat()
    package = WbvOverlayPackage(
        package_uid=package_uid,
        managed_well_uid=well,
        package_name="Published",
        source_wdv_session_uid=session_uid,
        source_wdv_revision=7,
        published_snapshot=session,
        provenance=WbvPublicationProvenance(
            published_at=now,
            published_by="test",
            publication_command_uid=command_uid,
            source_session_uid=session_uid,
            source_revision=7,
        ),
        created_at=now,
        updated_at=now,
    )

    def samples(_):
        return WdvCurveSampleResponse(
            managed_well_uid=well,
            managed_curve_uid=curve,
            managed_product_uid=product,
            managed_source_uid=source,
            observed_mnemonic="GR",
            display_name="Gamma Ray",
            depth_unit="ft",
            value_unit="gAPI",
            depth_min=1000,
            depth_max=1001,
            value_min=0,
            value_max=100,
            sample_count=2,
            returned_sample_count=2,
            provenance=WdvCurveSampleProvenance(sample_source="test"),
            samples=((1000.0, 0.0), (1001.0, 100.0)),
        )

    return package, samples


def test_published_track_geometry_compiles_into_render_contract() -> None:
    package, samples = _fixture()
    track_uid = package.published_snapshot.tracks[0].track_uid
    package = package.model_copy(
        update={
            "wbv_overrides": WbvPresentationOverrides(
                track_spacing=0.25,
                tracks=(
                    WbvTrackPresentationOverride(
                        track_uid=track_uid,
                        geometry_type="radial_panel",
                        radial_lane=3,
                        radial_offset=1.5,
                        angular_position_deg=135.0,
                        radial_width=2.0,
                        thickness=0.1,
                        orientation_mode="follow_trajectory",
                        opacity=0.5,
                    ),
                ),
            )
        }
    )

    rendered = WbvPublishedPackageRenderAdapter(samples).compile(package)
    track = rendered.tracks[0]

    assert track.geometry_type == "radial_panel"
    assert track.radial_lane == 3
    assert track.wellbore_offset == 1.5
    assert track.angular_position_deg == 135.0
    assert track.width == 2.0
    assert track.thickness == 0.1
    assert track.orientation_mode == "camera_facing"
    assert rendered.curves[0].opacity == 0.4


def test_camera_ribbon_geometry_is_persistable() -> None:
    package, _ = _fixture()
    track_uid = package.published_snapshot.tracks[0].track_uid
    override = WbvTrackPresentationOverride(
        track_uid=track_uid,
        geometry_type="camera_ribbon",
        orientation_mode="camera_facing",
    )

    assert override.geometry_type == "camera_ribbon"
    assert override.orientation_mode == "camera_facing"
