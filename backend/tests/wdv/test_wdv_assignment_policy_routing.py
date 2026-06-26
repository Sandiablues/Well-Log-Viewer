from pathlib import Path
from types import SimpleNamespace

from app.identity import new_uuid7_str
from app.wdv_session.canonical_commands import (
    AddCurveAssignmentCommand,
    BootstrapCurveAssignmentCommand,
    CreateConfiguredTrackCommand,
    CreateTrackCommand,
)
from app.wdv_session.canonical_command_service import CanonicalWdvCommandService
from app.wdv_session.canonical_service import CanonicalWdvSessionService


class FakeResolver:
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
                kr_curve_type_id="density",
                observed_mnemonic="RHOZ",
                curve_name="RHOZ",
                display_name="Bulk Density",
                normalized_mnemonic="RHOZ",
                curve_family="density",
                curve_type="density",
                curve_description="Bulk density",
                curve_unit="G/C3",
            ),
        )


def family_policy(_product):
    return {
        "min": 1.95,
        "max": 2.95,
        "type": "linear",
        "direction": "normal",
        "source": "managed_knowledge_family_default",
    }


def service(tmp_path: Path, well_uid: str, curve_uids: tuple[str, ...]):
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    commands = CanonicalWdvCommandService(
        session_service=sessions,
        resolver=FakeResolver(well_uid, curve_uids),
        policy_revision_fn=lambda: "policy-revision",
        display_policy_resolver=family_policy,
    )
    return sessions, commands


def assert_complete_policy(assignment) -> None:
    assert assignment.scale_min == 1.95
    assert assignment.scale_max == 2.95
    assert assignment.scale_type == "linear"
    assert assignment.scale_direction == "normal"
    assert assignment.display_policy_source == "family"
    assert assignment.display_review_required is False


def test_configured_track_routes_assignment_through_policy_helper(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    _sessions, commands = service(tmp_path, well_uid, (curve_uid,))

    result = commands.create_configured_track(
        well_uid,
        CreateConfiguredTrackCommand(
            expected_revision=0,
            track_name="Density",
            initial_managed_curve_uids=(curve_uid,),
        ),
    )

    assert_complete_policy(result.tracks[0].assignments[0])


def test_bootstrap_routes_assignment_through_policy_helper(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    _sessions, commands = service(tmp_path, well_uid, (curve_uid,))

    result = commands.bootstrap_assignment(
        well_uid,
        BootstrapCurveAssignmentCommand(
            expected_revision=0,
            managed_curve_uid=curve_uid,
        ),
    )

    assert_complete_policy(result.tracks[0].assignments[0])


def test_manual_add_routes_assignment_through_policy_helper(
    tmp_path: Path,
) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    _sessions, commands = service(tmp_path, well_uid, (curve_uid,))

    with_track = commands.create_track(
        well_uid,
        CreateTrackCommand(
            expected_revision=0,
            track_name="Density",
        ),
    )
    result = commands.add_assignment(
        well_uid,
        AddCurveAssignmentCommand(
            expected_revision=with_track.revision,
            track_uid=with_track.tracks[0].track_uid,
            managed_curve_uid=curve_uid,
        ),
    )

    assert_complete_policy(result.tracks[0].assignments[0])
