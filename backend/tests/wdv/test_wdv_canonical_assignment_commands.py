from pathlib import Path
from types import SimpleNamespace

import pytest

from app.identity import new_uuid7_str
from app.wdv_session.canonical_command_service import (
    CanonicalWdvCommandError,
    CanonicalWdvCommandService,
)
from app.wdv_session.canonical_commands import (
    AddCurveAssignmentCommand,
    CreateTrackCommand,
    MoveCurveAssignmentCommand,
    ReorderCurveAssignmentsCommand,
    ReorderTracksCommand,
    UpdateCurveAssignmentCommand,
    UpdateTrackCommand,
)
from app.wdv_session.canonical_service import (
    CanonicalSessionRevisionConflict,
    CanonicalWdvSessionService,
)


class FakeResolver:
    def __init__(self, well_uid: str, curve_uid: str) -> None:
        self.well_uid = well_uid
        self.curve_uid = curve_uid
        self.product_uid = new_uuid7_str()
        self.source_uid = new_uuid7_str()

    def resolve_curve(self, managed_well_uid: str, managed_curve_uid: str):
        assert managed_well_uid == self.well_uid
        assert managed_curve_uid == self.curve_uid
        return SimpleNamespace(
            managed_well_uid=self.well_uid,
            managed_curve_uid=self.curve_uid,
            managed_product_uid=self.product_uid,
            managed_source_uid=self.source_uid,
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


def test_backend_issues_track_and_assignment_uids_atomically(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    service = CanonicalWdvCommandService(
        session_service=sessions,
        resolver=FakeResolver(well_uid, curve_uid),
    )

    initial = sessions.get_session(well_uid)
    created = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=initial.revision,
            track_name="Gamma Ray",
        ),
    )
    assert created.revision == 1
    assert created.tracks[0].track_uid
    assert created.selected_track_uid == created.tracks[0].track_uid

    assigned = service.add_assignment(
        well_uid,
        AddCurveAssignmentCommand(
            expected_revision=created.revision,
            track_uid=created.tracks[0].track_uid,
            managed_curve_uid=curve_uid,
            scale_min=0,
            scale_max=150,
            scale_type="linear",
        ),
    )
    assignment = assigned.tracks[0].assignments[0]
    assert assigned.revision == 2
    assert assignment.assignment_uid
    assert assignment.managed_curve_uid == curve_uid
    assert assignment.track_uid == assigned.tracks[0].track_uid


def test_stale_revision_is_rejected(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    service = CanonicalWdvCommandService(
        session_service=sessions,
        resolver=FakeResolver(well_uid, new_uuid7_str()),
    )
    initial = sessions.get_session(well_uid)
    service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=initial.revision,
            track_name="Track 1",
        ),
    )
    with pytest.raises(CanonicalSessionRevisionConflict):
        service.create_track(
            well_uid,
            CreateTrackCommand(
                expected_revision=initial.revision,
                track_name="Track 2",
            ),
        )



def test_track_update_reorder_and_assignment_display_edits(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    service = CanonicalWdvCommandService(
        session_service=sessions,
        resolver=FakeResolver(well_uid, curve_uid),
    )

    initial = sessions.get_session(well_uid)
    first = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=initial.revision,
            track_name="Track A",
        ),
    )
    second = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=first.revision,
            track_name="Track B",
        ),
    )
    track_a, track_b = second.tracks

    updated = service.update_track(
        well_uid,
        UpdateTrackCommand(
            expected_revision=second.revision,
            track_uid=track_a.track_uid,
            track_name="Gamma",
            width_px=300,
            visible=False,
            lattice="logarithmic",
            lattice_source="user_override",
            lattice_override=True,
            scale_mode="dual",
        ),
    )
    changed = updated.tracks[0]
    assert changed.track_name == "Gamma"
    assert changed.width_px == 300
    assert changed.visible is False
    assert changed.lattice == "logarithmic"
    assert changed.lattice_override is True
    assert changed.scale_mode == "dual"

    reordered = service.reorder_tracks(
        well_uid,
        ReorderTracksCommand(
            expected_revision=updated.revision,
            track_uids=(track_b.track_uid, track_a.track_uid),
        ),
    )
    assert [track.track_uid for track in reordered.tracks] == [
        track_b.track_uid,
        track_a.track_uid,
    ]
    assert [track.track_number for track in reordered.tracks] == [0, 1]

    assigned = service.add_assignment(
        well_uid,
        AddCurveAssignmentCommand(
            expected_revision=reordered.revision,
            track_uid=track_a.track_uid,
            managed_curve_uid=curve_uid,
            scale_min=0,
            scale_max=200,
            scale_type="linear",
        ),
    )
    assignment = next(
        track for track in assigned.tracks if track.track_uid == track_a.track_uid
    ).assignments[0]

    edited = service.update_assignment(
        well_uid,
        UpdateCurveAssignmentCommand(
            expected_revision=assigned.revision,
            assignment_uid=assignment.assignment_uid,
            visible=False,
            scale_min=10,
            scale_max=150,
            scale_direction="reversed",
            range_mode="fixed",
            color="#123456",
            line_visible=False,
            line_style="dash",
            line_width=2.5,
            line_opacity=65,
            position_anchor="right",
            horizontal_offset_pct=20,
            clip_to_track=False,
            fill_side="left",
            fill_color="#654321",
            fill_opacity=40,
            infill_source="solid",
            infill_pattern="dense",
            infill_interval_column="lithology",
            display_priority="foreground",
            show_qaqc_warnings=False,
            show_null_gaps=False,
            show_out_of_range=False,
        ),
    )
    changed_assignment = next(
        track for track in edited.tracks if track.track_uid == track_a.track_uid
    ).assignments[0]
    assert changed_assignment.visible is False
    assert changed_assignment.scale_min == 10
    assert changed_assignment.scale_max == 150
    assert changed_assignment.scale_direction == "reversed"
    assert changed_assignment.color == "#123456"
    assert changed_assignment.line_visible is False
    assert changed_assignment.line_opacity == 65
    assert changed_assignment.position_anchor == "right"
    assert changed_assignment.horizontal_offset_pct == 20
    assert changed_assignment.clip_to_track is False
    assert changed_assignment.fill_side == "left"
    assert changed_assignment.fill_opacity == 40
    assert changed_assignment.display_priority == "foreground"
    assert changed_assignment.show_qaqc_warnings is False


def test_assignment_move_preserves_uid_and_normalizes_stacks(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    service = CanonicalWdvCommandService(
        session_service=sessions,
        resolver=FakeResolver(well_uid, curve_uid),
    )

    initial = sessions.get_session(well_uid)
    first = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=initial.revision,
            track_name="Source",
        ),
    )
    second = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=first.revision,
            track_name="Target",
        ),
    )
    source_track, target_track = second.tracks
    assigned = service.add_assignment(
        well_uid,
        AddCurveAssignmentCommand(
            expected_revision=second.revision,
            track_uid=source_track.track_uid,
            managed_curve_uid=curve_uid,
            scale_min=0,
            scale_max=200,
            scale_type="linear",
        ),
    )
    assignment = assigned.tracks[0].assignments[0]

    moved = service.move_assignment(
        well_uid,
        MoveCurveAssignmentCommand(
            expected_revision=assigned.revision,
            assignment_uid=assignment.assignment_uid,
            target_track_uid=target_track.track_uid,
            target_stack_index=0,
        ),
    )

    source = next(
        track for track in moved.tracks if track.track_uid == source_track.track_uid
    )
    target = next(
        track for track in moved.tracks if track.track_uid == target_track.track_uid
    )
    assert source.assignments == ()
    assert target.assignments[0].assignment_uid == assignment.assignment_uid
    assert target.assignments[0].track_uid == target_track.track_uid
    assert target.assignments[0].stack_index == 0
    assert moved.selected_track_uid == target_track.track_uid


def test_persistent_edit_commands_reject_invalid_graph_requests(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    service = CanonicalWdvCommandService(
        session_service=sessions,
        resolver=FakeResolver(well_uid, new_uuid7_str()),
    )
    initial = sessions.get_session(well_uid)
    created = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=initial.revision,
            track_name="Track",
        ),
    )

    with pytest.raises(CanonicalWdvCommandError):
        service.reorder_tracks(
            well_uid,
            ReorderTracksCommand(
                expected_revision=created.revision,
                track_uids=(),
            ),
        )

    with pytest.raises(CanonicalWdvCommandError):
        service.move_assignment(
            well_uid,
            MoveCurveAssignmentCommand(
                expected_revision=created.revision,
                assignment_uid=new_uuid7_str(),
                target_track_uid=created.tracks[0].track_uid,
                target_stack_index=0,
            ),
        )
