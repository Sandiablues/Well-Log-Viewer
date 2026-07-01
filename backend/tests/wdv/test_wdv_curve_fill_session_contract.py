from pathlib import Path
from types import SimpleNamespace

import pytest

from app.identity import new_uuid7_str
from app.curve_fill.models import (
    ComparisonBasis,
    ComparisonCondition,
    CurveOperand,
    FillMode,
    FillStyle,
)
from app.wdv_session.canonical_command_service import CanonicalWdvCommandService
from app.wdv_session.canonical_commands import (
    CreateConfiguredTrackCommand,
    RemoveCurveAssignmentCommand,
    RemoveCurveFillCommand,
    UpsertCurveFillCommand,
)
from app.wdv_session.canonical_service import CanonicalWdvSessionService, CanonicalSessionRevisionConflict


class Resolver:
    def __init__(self, well_uid, curves):
        self.well_uid = well_uid
        self.curves = set(curves)

    def resolve_curve(self, managed_well_uid, managed_curve_uid):
        assert managed_well_uid == self.well_uid
        if managed_curve_uid not in self.curves:
            raise ValueError("unknown curve")
        return SimpleNamespace(
            managed_well_uid=self.well_uid,
            managed_curve_uid=managed_curve_uid,
            managed_product_uid=new_uuid7_str(),
            managed_source_uid=new_uuid7_str(),
            managed_wellbore_uid=None,
            product=SimpleNamespace(
                kr_curve_type_id="resistivity",
                observed_mnemonic="RT",
                curve_name="RT",
                display_name="Resistivity",
                normalized_mnemonic="RT",
                curve_family="resistivity",
                curve_unit="ohm.m",
            ),
        )


def policy(_):
    return {"min": 0.2, "max": 2000.0, "type": "logarithmic", "direction": "normal", "source": "test"}


def setup_session(tmp_path: Path):
    well = new_uuid7_str()
    curves = (new_uuid7_str(), new_uuid7_str())
    sessions = CanonicalWdvSessionService(tmp_path / "sessions.json")
    service = CanonicalWdvCommandService(
        session_service=sessions,
        resolver=Resolver(well, curves),
        display_policy_resolver=policy,
        policy_revision_fn=lambda: "test-policy-v1",
    )
    initial = sessions.get_session(well)
    session = service.create_configured_track(
        well,
        CreateConfiguredTrackCommand(
            expected_revision=initial.revision,
            track_name="Resistivity",
            initial_managed_curve_uids=curves,
        ),
    )
    return well, curves, sessions, service, session


def fill_command(session, well, curves, **updates):
    track = session.tracks[0]
    values = dict(
        expected_revision=session.revision,
        track_uid=track.track_uid,
        owner_assignment_uid=track.assignments[0].assignment_uid,
        fill_mode=FillMode.CONDITIONAL,
        operand_a=CurveOperand(managed_well_uid=well, curve_uid=curves[0], depth_domain_uid="md", unit="ohm.m"),
        operand_b=CurveOperand(managed_well_uid=well, curve_uid=curves[1], depth_domain_uid="md", unit="ohm.m"),
        condition=ComparisonCondition.A_GREATER_THAN_B,
        comparison_basis=ComparisonBasis.ENGINEERING_VALUE,
        style=FillStyle(fill="#d8b85a", opacity=0.55),
        depth_unit="m",
    )
    values.update(updates)
    return UpsertCurveFillCommand(**values)


def test_curve_fill_persists_in_canonical_session(tmp_path: Path):
    well, curves, sessions, service, session = setup_session(tmp_path)
    updated = service.upsert_curve_fill(well, fill_command(session, well, curves))
    assert updated.revision == session.revision + 1
    assert len(updated.curve_fills) == 1
    reloaded = CanonicalWdvSessionService(tmp_path / "sessions.json").get_session(well)
    assert reloaded.curve_fills == updated.curve_fills


def test_curve_fill_command_is_revision_guarded(tmp_path: Path):
    well, curves, _, service, session = setup_session(tmp_path)
    updated = service.upsert_curve_fill(well, fill_command(session, well, curves))
    with pytest.raises(CanonicalSessionRevisionConflict):
        service.upsert_curve_fill(well, fill_command(session, well, curves))
    assert len(updated.curve_fills) == 1


def test_removing_owner_assignment_prunes_fill(tmp_path: Path):
    well, curves, _, service, session = setup_session(tmp_path)
    updated = service.upsert_curve_fill(well, fill_command(session, well, curves))
    removed = service.remove_assignment(
        well,
        RemoveCurveAssignmentCommand(
            expected_revision=updated.revision,
            assignment_uid=updated.curve_fills[0].owner_assignment_uid,
        ),
    )
    assert removed.curve_fills == ()


def test_fill_can_be_removed_explicitly(tmp_path: Path):
    well, curves, _, service, session = setup_session(tmp_path)
    updated = service.upsert_curve_fill(well, fill_command(session, well, curves))
    removed = service.remove_curve_fill(
        well,
        RemoveCurveFillCommand(
            expected_revision=updated.revision,
            fill_uid=updated.curve_fills[0].fill_uid,
        ),
    )
    assert removed.curve_fills == ()
