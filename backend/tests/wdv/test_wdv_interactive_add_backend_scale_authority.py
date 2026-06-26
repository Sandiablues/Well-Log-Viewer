from pathlib import Path
from types import SimpleNamespace

from app.identity import new_uuid7_str
from app.wdv_session.canonical_command_service import CanonicalWdvCommandService
from app.wdv_session.canonical_commands import AddCurveAssignmentCommand, CreateTrackCommand
from app.wdv_session.canonical_service import CanonicalWdvSessionService


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


def governed_density_policy(_product):
    return {
        "min": 1.95,
        "max": 2.95,
        "type": "linear",
        "direction": "normal",
        "source": "managed_knowledge_family_default",
    }


def test_interactive_add_uses_backend_policy_not_client_scales(tmp_path: Path) -> None:
    well_uid = new_uuid7_str()
    curve_uid = new_uuid7_str()
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    service = CanonicalWdvCommandService(
        session_service=sessions,
        resolver=FakeResolver(well_uid, curve_uid),
        display_policy_resolver=governed_density_policy,
    )

    created = service.create_track(
        well_uid,
        CreateTrackCommand(expected_revision=0, track_name="Density"),
    )
    track_uid = created.tracks[0].track_uid

    assigned = service.add_assignment(
        well_uid,
        AddCurveAssignmentCommand(
            expected_revision=created.revision,
            track_uid=track_uid,
            managed_curve_uid=curve_uid,
            scale_min=-999.0,
            scale_max=999.0,
            scale_type="logarithmic",
            scale_direction="reversed",
        ),
    )

    assignment = assigned.tracks[0].assignments[0]
    assert assignment.managed_curve_uid == curve_uid
    assert assignment.track_uid == track_uid
    assert assignment.scale_min == 1.95
    assert assignment.scale_max == 2.95
    assert assignment.scale_type == "linear"
    assert assignment.scale_direction == "normal"
