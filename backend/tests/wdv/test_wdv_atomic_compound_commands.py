from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.identity import new_uuid7_str
from app.main import app
from app.wdv_session.canonical_command_service import (
    CanonicalWdvCommandError,
    CanonicalWdvCommandService,
)
from app.wdv_session.canonical_commands import (
    CreateConfiguredTrackCommand,
    CreateTrackCommand,
    ResetCurveTrackWidthsCommand,
    TrackInsertPosition,
    UpdateTrackCommand,
)
from app.wdv_session.canonical_service import (
    CanonicalSessionCommandReplayConflict,
    CanonicalWdvSessionService,
)


class MultiCurveResolver:
    def __init__(self, well_uid: str, curve_uids: tuple[str, ...]) -> None:
        self.well_uid = well_uid
        self.curve_uids = set(curve_uids)

    def resolve_curve(self, managed_well_uid: str, managed_curve_uid: str):
        if managed_well_uid != self.well_uid:
            raise ValueError("wrong well")
        if managed_curve_uid not in self.curve_uids:
            raise ValueError(f"unknown curve: {managed_curve_uid}")
        return SimpleNamespace(
            managed_well_uid=self.well_uid,
            managed_curve_uid=managed_curve_uid,
            managed_product_uid=new_uuid7_str(),
            managed_source_uid=new_uuid7_str(),
            managed_wellbore_uid=None,
            product=SimpleNamespace(
                kr_curve_type_id="gamma_ray",
                observed_mnemonic="GR",
                curve_name="GR",
                display_name="Gamma Ray",
                normalized_mnemonic="GR",
                curve_family="gamma_ray",
                curve_unit="API",
            ),
        )


def _service(tmp_path: Path, well_uid: str, curve_uids: tuple[str, ...]):
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    service = CanonicalWdvCommandService(
        session_service=sessions,
        resolver=MultiCurveResolver(well_uid, curve_uids),
    )
    return sessions, service


def test_configured_track_create_is_atomic_and_revision_single_step(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    curves = (new_uuid7_str(), new_uuid7_str())
    sessions, service = _service(tmp_path, well_uid, curves)

    initial = sessions.get_session(well_uid)
    first = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=initial.revision,
            track_name="Existing A",
        ),
    )
    second = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=first.revision,
            track_name="Existing B",
        ),
    )

    created = service.create_configured_track(
        well_uid,
        CreateConfiguredTrackCommand(
            expected_revision=second.revision,
            command_id=new_uuid7_str(),
            track_name="Configured",
            width_px=240,
            lattice="linear",
            scale_mode="per_curve",
            insert_position=TrackInsertPosition(
                mode="before_track",
                reference_track_uid=second.tracks[1].track_uid,
            ),
            initial_managed_curve_uids=curves,
            select_created_track=True,
        ),
    )

    assert created.revision == second.revision + 1
    assert [track.track_name for track in created.tracks] == [
        "Existing A",
        "Configured",
        "Existing B",
    ]
    assert [track.track_number for track in created.tracks] == [0, 1, 2]

    configured = created.tracks[1]
    assert configured.width_px == 240
    assert configured.lattice == "linear"
    assert configured.scale_mode == "per_curve"
    assert created.selected_track_uid == configured.track_uid
    assert [
        assignment.managed_curve_uid
        for assignment in configured.assignments
    ] == list(curves)
    assert [
        assignment.stack_index
        for assignment in configured.assignments
    ] == [0, 1]
    assert all(
        assignment.track_uid == configured.track_uid
        for assignment in configured.assignments
    )


def test_configured_track_failure_leaves_workspace_unchanged(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    known_curve = new_uuid7_str()
    unknown_curve = new_uuid7_str()
    sessions, service = _service(tmp_path, well_uid, (known_curve,))

    before = sessions.get_session(well_uid)

    with pytest.raises(ValueError, match="unknown curve"):
        service.create_configured_track(
            well_uid,
            CreateConfiguredTrackCommand(
                expected_revision=before.revision,
                command_id=new_uuid7_str(),
                track_name="Must Roll Back",
                initial_managed_curve_uids=(known_curve, unknown_curve),
            ),
        )

    after = sessions.get_session(well_uid)
    assert after == before


def test_configured_track_invalid_reference_leaves_workspace_unchanged(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    sessions, service = _service(tmp_path, well_uid, ())
    before = sessions.get_session(well_uid)

    with pytest.raises(CanonicalWdvCommandError, match="Unknown reference_track_uid"):
        service.create_configured_track(
            well_uid,
            CreateConfiguredTrackCommand(
                expected_revision=before.revision,
                command_id=new_uuid7_str(),
                track_name="Bad Reference",
                insert_position=TrackInsertPosition(
                    mode="after_track",
                    reference_track_uid=new_uuid7_str(),
                ),
            ),
        )

    assert sessions.get_session(well_uid) == before


def test_configured_track_command_replay_returns_same_graph(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    command_id = new_uuid7_str()
    sessions, service = _service(tmp_path, well_uid, (curve_uid,))

    command = CreateConfiguredTrackCommand(
        expected_revision=0,
        command_id=command_id,
        track_name="Replay Safe",
        initial_managed_curve_uids=(curve_uid,),
    )
    first = service.create_configured_track(well_uid, command)
    replay = service.create_configured_track(well_uid, command)

    assert replay == first
    assert replay.revision == 1
    assert replay.tracks[0].track_uid == first.tracks[0].track_uid
    assert (
        replay.tracks[0].assignments[0].assignment_uid
        == first.tracks[0].assignments[0].assignment_uid
    )
    assert sessions.get_session(well_uid).revision == 1

    with pytest.raises(CanonicalSessionCommandReplayConflict):
        service.create_configured_track(
            well_uid,
            command.model_copy(update={"track_name": "Different"}),
        )


def test_reset_curve_track_widths_is_atomic_and_respects_visibility(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    sessions, service = _service(tmp_path, well_uid, ())

    current = sessions.get_session(well_uid)
    visible_curve = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=current.revision,
            track_name="Visible Curve",
            track_type="curve",
            width_px=180,
        ),
    )
    hidden_curve = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=visible_curve.revision,
            track_name="Hidden Curve",
            track_type="curve",
            width_px=190,
        ),
    )
    hidden_uid = hidden_curve.tracks[1].track_uid
    hidden_curve = service.update_track(
        well_uid,
        UpdateTrackCommand(
            expected_revision=hidden_curve.revision,
            track_uid=hidden_uid,
            visible=False,
        ),
    )
    with_depth = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=hidden_curve.revision,
            track_name="Depth",
            track_type="depth",
            width_px=80,
        ),
    )

    reset = service.reset_curve_track_widths(
        well_uid,
        ResetCurveTrackWidthsCommand(
            expected_revision=with_depth.revision,
            command_id=new_uuid7_str(),
            width_px=260,
            visible_curve_tracks_only=True,
        ),
    )

    assert reset.revision == with_depth.revision + 1
    by_name = {track.track_name: track for track in reset.tracks}
    assert by_name["Visible Curve"].width_px == 260
    assert by_name["Hidden Curve"].width_px == 190
    assert by_name["Depth"].width_px == 80


def test_compound_routes_are_registered() -> None:
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    assert (
        "/api/wlv/v2/wdv/session-commands/"
        "{managed_well_uid}/tracks/configured"
    ) in paths
    assert (
        "/api/wlv/v2/wdv/session-commands/"
        "{managed_well_uid}/tracks/reset-curve-widths"
    ) in paths
