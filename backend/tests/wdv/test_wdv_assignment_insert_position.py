from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.identity import new_uuid7_str
from app.wdv_session.canonical_command_service import (
    CanonicalWdvCommandError,
    CanonicalWdvCommandService,
)
from app.wdv_session.canonical_commands import (
    AddCurveAssignmentCommand,
    CreateTrackCommand,
)
from app.wdv_session.canonical_service import CanonicalWdvSessionService



def resolve_test_display_policy(_product):
    return {
        "min": 0.0,
        "max": 200.0,
        "type": "linear",
        "direction": "normal",
        "source": "test_policy",
    }

class MultiCurveResolver:
    def __init__(self, well_uid: str, curve_uids: tuple[str, ...]) -> None:
        self.well_uid = well_uid
        self.curve_uids = set(curve_uids)

    def resolve_curve(self, managed_well_uid: str, managed_curve_uid: str):
        assert managed_well_uid == self.well_uid
        assert managed_curve_uid in self.curve_uids
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


def _service(tmp_path: Path):
    well_uid = new_uuid7_str()
    curve_uids = (new_uuid7_str(), new_uuid7_str())
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    service = CanonicalWdvCommandService(
        session_service=sessions,
        resolver=MultiCurveResolver(well_uid, curve_uids),
        display_policy_resolver=resolve_test_display_policy,
    )
    created = service.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=0,
            track_name="Curves",
        ),
    )
    return well_uid, curve_uids, sessions, service, created


def test_add_assignment_inserts_at_requested_stack_index(
    tmp_path: Path,
) -> None:
    well_uid, curve_uids, _, service, created = _service(tmp_path)
    track_uid = created.tracks[0].track_uid

    first = service.add_assignment(
        well_uid,
        AddCurveAssignmentCommand(
            expected_revision=created.revision,
            track_uid=track_uid,
            managed_curve_uid=curve_uids[0],
        ),
    )
    inserted = service.add_assignment(
        well_uid,
        AddCurveAssignmentCommand(
            expected_revision=first.revision,
            track_uid=track_uid,
            managed_curve_uid=curve_uids[1],
            target_stack_index=0,
        ),
    )

    assignments = inserted.tracks[0].assignments
    assert inserted.revision == first.revision + 1
    assert [item.managed_curve_uid for item in assignments] == [
        curve_uids[1],
        curve_uids[0],
    ]
    assert [item.stack_index for item in assignments] == [0, 1]


def test_invalid_insert_position_leaves_session_unchanged(
    tmp_path: Path,
) -> None:
    well_uid, curve_uids, sessions, service, created = _service(tmp_path)
    track_uid = created.tracks[0].track_uid

    first = service.add_assignment(
        well_uid,
        AddCurveAssignmentCommand(
            expected_revision=created.revision,
            track_uid=track_uid,
            managed_curve_uid=curve_uids[0],
        ),
    )

    with pytest.raises(
        CanonicalWdvCommandError,
        match="target_stack_index",
    ):
        service.add_assignment(
            well_uid,
            AddCurveAssignmentCommand(
                expected_revision=first.revision,
                track_uid=track_uid,
                managed_curve_uid=curve_uids[1],
                target_stack_index=3,
            ),
        )

    persisted = sessions.get_session(well_uid)
    assert persisted.revision == first.revision
    assert len(persisted.tracks[0].assignments) == 1
    assert persisted.tracks[0].assignments[0].managed_curve_uid == curve_uids[0]


def test_assignment_insert_command_replay_does_not_duplicate(
    tmp_path: Path,
) -> None:
    well_uid, curve_uids, sessions, service, created = _service(tmp_path)
    command_id = new_uuid7_str()
    command = AddCurveAssignmentCommand(
        expected_revision=created.revision,
        command_id=command_id,
        track_uid=created.tracks[0].track_uid,
        managed_curve_uid=curve_uids[0],
        target_stack_index=0,
    )

    first = service.add_assignment(well_uid, command)
    replay = service.add_assignment(well_uid, command)

    assert replay == first
    persisted = sessions.get_session(well_uid)
    assert persisted.revision == first.revision
    assert len(persisted.tracks[0].assignments) == 1


def test_assignment_insert_position_rejects_negative_index() -> None:
    with pytest.raises(ValidationError):
        AddCurveAssignmentCommand(
            expected_revision=0,
            track_uid=new_uuid7_str(),
            managed_curve_uid=new_uuid7_str(),
            target_stack_index=-1,
        )
