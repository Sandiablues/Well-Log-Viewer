from pathlib import Path

from app.identity import new_uuid7_str
from app.wbv_layout.models import WbvLayoutCommandRequest
from app.wbv_layout.repository import WbvTrackLayoutRepository
from app.wbv_layout.service import WbvTrackLayoutService


def test_add_track_uses_only_track_type_and_three_positions(tmp_path: Path):
    well_uid = new_uuid7_str()
    service = WbvTrackLayoutService(WbvTrackLayoutRepository(tmp_path / "layouts.json"))
    layout = service.get_layout(well_uid)

    layout = service.command(
        well_uid,
        WbvLayoutCommandRequest(
            expected_revision=layout.revision,
            command="add_track",
            track_type="curve",
            position="right",
        ),
    )
    layout = service.command(
        well_uid,
        WbvLayoutCommandRequest(
            expected_revision=layout.revision,
            command="add_track",
            track_type="lithology",
            position="center",
        ),
    )

    assert [track.track_type for track in layout.tracks] == ["curve", "lithology"]
    assert [track.position for track in layout.tracks] == ["right", "center"]


def test_track_order_defines_proximity_with_distance_then_gap(tmp_path: Path):
    well_uid = new_uuid7_str()
    service = WbvTrackLayoutService(WbvTrackLayoutRepository(tmp_path / "layouts.json"))
    layout = service.get_layout(well_uid)

    for name in ("Track 1", "Track 2", "Track 3"):
        layout = service.command(
            well_uid,
            WbvLayoutCommandRequest(
                expected_revision=layout.revision,
                command="add_track",
                track_type="curve",
                position="right",
                display_name=name,
            ),
        )

    first, second, third = layout.tracks
    layout = service.command(
        well_uid,
        WbvLayoutCommandRequest(
            expected_revision=layout.revision,
            command="update_track",
            track_uid=first.track_uid,
            distance_from_wellbore=0.2,
            width=1.0,
        ),
    )
    layout = service.command(
        well_uid,
        WbvLayoutCommandRequest(
            expected_revision=layout.revision,
            command="update_track",
            track_uid=second.track_uid,
            previous_track_gap=0.1,
            width=1.5,
        ),
    )
    layout = service.command(
        well_uid,
        WbvLayoutCommandRequest(
            expected_revision=layout.revision,
            command="update_track",
            track_uid=third.track_uid,
            previous_track_gap=0.25,
        ),
    )

    assert layout.tracks[0].distance_from_wellbore == 0.2
    assert layout.tracks[1].previous_track_gap == 0.1
    assert layout.tracks[2].previous_track_gap == 0.25

    layout = service.command(
        well_uid,
        WbvLayoutCommandRequest(
            expected_revision=layout.revision,
            command="move_up",
            track_uid=third.track_uid,
        ),
    )
    assert [track.display_name for track in layout.tracks] == ["Track 1", "Track 3", "Track 2"]


def test_ensure_curve_capacity_creates_only_curve_tracks(tmp_path: Path):
    well_uid = new_uuid7_str()
    service = WbvTrackLayoutService(WbvTrackLayoutRepository(tmp_path / "layouts.json"))
    layout = service.ensure_curve_capacity(well_uid, 3)

    assert len(layout.tracks) == 3
    assert all(track.track_type == "curve" for track in layout.tracks)
    assert [track.position for track in layout.tracks] == ["right", "left", "right"]
    assert [track.display_order for track in layout.tracks] == [0, 1, 2]


def test_repository_migrates_legacy_positions_and_gap(tmp_path: Path):
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    storage = tmp_path / "layouts.json"
    storage.write_text(
        """{
  "contract_version": "wbv_track_layout_store_v1",
  "layouts": {
    "%s": {
      "contract_version": "wbv_track_layout_v1",
      "managed_well_uid": "%s",
      "revision": 1,
      "tracks": [{
        "track_uid": "%s",
        "display_name": "Legacy",
        "track_type": "curve",
        "display_order": 0,
        "visible": true,
        "position": "front",
        "angular_position_deg": 90,
        "distance_from_wellbore": 0.15,
        "width": 1,
        "opacity": 1
      }]
    }
  }
}
""" % (well_uid, well_uid, track_uid)
    )

    layout = WbvTrackLayoutRepository(storage).get(well_uid)

    assert layout is not None
    assert layout.tracks[0].position == "center"
    assert layout.tracks[0].previous_track_gap == 0.05


def test_track_background_is_backend_owned_and_uses_single_opacity(tmp_path: Path):
    well_uid = new_uuid7_str()
    service = WbvTrackLayoutService(WbvTrackLayoutRepository(tmp_path / "layouts.json"))
    layout = service.get_layout(well_uid)
    layout = service.command(
        well_uid,
        WbvLayoutCommandRequest(
            expected_revision=layout.revision,
            command="add_track",
            track_type="curve",
        ),
    )
    track = layout.tracks[0]
    layout = service.command(
        well_uid,
        WbvLayoutCommandRequest(
            expected_revision=layout.revision,
            command="update_track",
            track_uid=track.track_uid,
            background_mode="solid",
            background_color="#123456",
            opacity=0.4,
        ),
    )

    updated = layout.tracks[0]
    assert updated.background_mode == "solid"
    assert updated.background_color == "#123456"
    assert updated.opacity == 0.4


def test_outline_and_grid_are_simple_backend_owned_track_controls(tmp_path: Path):
    well_uid = new_uuid7_str()
    service = WbvTrackLayoutService(WbvTrackLayoutRepository(tmp_path / "layouts.json"))
    layout = service.get_layout(well_uid)
    layout = service.command(
        well_uid,
        WbvLayoutCommandRequest(
            expected_revision=layout.revision,
            command="add_track",
            track_type="curve",
        ),
    )
    track = layout.tracks[0]
    assert track.outline_visible is True
    assert track.grid_mode == "off"

    layout = service.command(
        well_uid,
        WbvLayoutCommandRequest(
            expected_revision=layout.revision,
            command="update_track",
            track_uid=track.track_uid,
            outline_visible=False,
            grid_mode="logarithmic",
        ),
    )

    updated = layout.tracks[0]
    assert updated.outline_visible is False
    assert updated.grid_mode == "logarithmic"
