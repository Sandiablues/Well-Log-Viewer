from pathlib import Path

import pytest

from app.curve_fill_v2.canonical_service import (
    CanonicalCurveFillCommandError,
    CanonicalCurveFillService,
)
from app.curve_fill_v2.commands import (
    CreateCurveFillRuleCommand,
    RemoveCurveFillRuleCommand,
    ReorderCurveFillRulesCommand,
    UpdateCurveFillRuleCommand,
)
from app.curve_fill_v2.models import (
    Boundary,
    Comparison,
    CurveFillRuleState,
    FillStyle,
    RuleType,
)
from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import (
    WdvCanonicalAssignment,
    WdvCanonicalSession,
    WdvCanonicalTrack,
)
from app.wdv_session.canonical_command_service import CanonicalWdvCommandService
from app.wdv_session.canonical_commands import (
    ClearCanvasCommand,
    RemoveCurveAssignmentCommand,
    RemoveTrackCommand,
)
from app.wdv_workspace.transaction_service import CanonicalWdvWorkspaceTransactionService
from app.wdv_session.canonical_service import (
    CanonicalSessionCommandReplayConflict,
    CanonicalSessionRevisionConflict,
    CanonicalWdvSessionService,
)


def assignment(track_uid: str, well_uid: str, mnemonic: str, family: str, unit: str):
    return WdvCanonicalAssignment(
        assignment_uid=new_uuid7_str(),
        managed_curve_uid=new_uuid7_str(),
        managed_product_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        managed_source_uid=new_uuid7_str(),
        track_uid=track_uid,
        observed_mnemonic=mnemonic,
        display_name=mnemonic,
        curve_family=family,
        unit=unit,
        scale_min=0.0 if family != "density" else 1.95,
        scale_max=100.0 if family != "density" else 2.95,
        scale_type="linear",
        scale_direction="normal",
        display_policy_source="family",
    )


def seeded(tmp_path: Path):
    well_uid = new_uuid7_str()
    track_uid = new_uuid7_str()
    af10 = assignment(track_uid, well_uid, "AF10", "resistivity", "ohm.m")
    af90 = assignment(track_uid, well_uid, "AF90", "resistivity", "ohm.m")
    rhoz = assignment(track_uid, well_uid, "RHOZ", "density", "g/cm3")
    nphi = assignment(track_uid, well_uid, "NPHI", "neutron_porosity", "v/v")
    track = WdvCanonicalTrack(
        track_uid=track_uid,
        managed_well_uid=well_uid,
        track_name="Curves",
        assignments=(af10, af90, rhoz, nphi),
    )
    session = WdvCanonicalSession(
        session_uid=new_uuid7_str(),
        managed_well_uid=well_uid,
        state_status="active",
        tracks=(track,),
        selected_track_uid=track_uid,
        updated_at="2026-07-02T17:00:00+00:00",
    )
    store = tmp_path / "sessions.json"
    session_service = CanonicalWdvSessionService(storage_path=store)
    persisted = session_service.put_session(session)
    fill_service = CanonicalCurveFillService(session_service=session_service)
    return well_uid, track_uid, af10, af90, rhoz, nphi, session_service, fill_service, persisted


def style(color="#ff0000"):
    return FillStyle(color=color, opacity=0.5)


def create_conditional(fill_service, well_uid, track_uid, a, b, revision, **extra):
    return fill_service.create_rule(
        well_uid,
        CreateCurveFillRuleCommand(
            expected_revision=revision,
            track_uid=track_uid,
            curve_a_assignment_uid=a.assignment_uid,
            curve_b_assignment_uid=b.assignment_uid,
            rule_type=RuleType.CONDITIONAL,
            comparison=Comparison.GREATER_THAN,
            style=style(),
            **extra,
        ),
    )


def test_create_persists_across_service_restart(tmp_path: Path):
    well, track, af10, af90, *_rest, session_service, fill_service, current = seeded(tmp_path)
    updated = create_conditional(fill_service, well, track, af90, af10, current.revision)
    assert updated.revision == current.revision + 1
    assert len(updated.curve_fills) == 1
    rule = updated.curve_fills[0]
    assert rule.state == CurveFillRuleState.PENDING_GEOMETRY
    restarted = CanonicalWdvSessionService(storage_path=session_service.storage_path)
    loaded = restarted.get_session(well)
    assert loaded.curve_fills == updated.curve_fills


def test_multiple_rules_order_update_delete_and_reorder(tmp_path: Path):
    well, track, af10, af90, *_rest, session_service, fill_service, current = seeded(tmp_path)
    first = create_conditional(fill_service, well, track, af90, af10, current.revision)
    second = fill_service.create_rule(
        well,
        CreateCurveFillRuleCommand(
            expected_revision=first.revision,
            track_uid=track,
            curve_a_assignment_uid=af90.assignment_uid,
            rule_type=RuleType.TO_BOUNDARY,
            boundary=Boundary.RIGHT,
            style=style("#00ff00"),
        ),
    )
    assert [r.order for r in second.curve_fills] == [0, 1]
    reordered = fill_service.reorder_rules(
        well,
        ReorderCurveFillRulesCommand(
            expected_revision=second.revision,
            track_uid=track,
            rule_uids=(second.curve_fills[1].rule_uid, second.curve_fills[0].rule_uid),
        ),
    )
    assert [r.style.color for r in reordered.curve_fills] == ["#00ff00", "#ff0000"]
    changed = fill_service.update_rule(
        well,
        UpdateCurveFillRuleCommand(
            expected_revision=reordered.revision,
            rule_uid=reordered.curve_fills[0].rule_uid,
            enabled=False,
        ),
    )
    assert changed.curve_fills[0].state == CurveFillRuleState.DISABLED
    removed = fill_service.remove_rule(
        well,
        RemoveCurveFillRuleCommand(
            expected_revision=changed.revision,
            rule_uid=changed.curve_fills[0].rule_uid,
        ),
    )
    assert len(removed.curve_fills) == 1
    assert removed.curve_fills[0].order == 0


def test_revision_guard_and_command_replay(tmp_path: Path):
    well, track, af10, af90, *_rest, _session_service, fill_service, current = seeded(tmp_path)
    command_id = new_uuid7_str()
    command = CreateCurveFillRuleCommand(
        expected_revision=current.revision,
        command_id=command_id,
        track_uid=track,
        curve_a_assignment_uid=af90.assignment_uid,
        curve_b_assignment_uid=af10.assignment_uid,
        rule_type=RuleType.CONDITIONAL,
        comparison=Comparison.GREATER_THAN,
        style=style(),
    )
    first = fill_service.create_rule(well, command)
    replay = fill_service.create_rule(well, command)
    assert replay.revision == first.revision
    assert replay.curve_fills == first.curve_fills
    with pytest.raises(CanonicalSessionRevisionConflict):
        create_conditional(fill_service, well, track, af90, af10, current.revision)
    with pytest.raises(CanonicalSessionCommandReplayConflict):
        fill_service.create_rule(
            well,
            command.model_copy(update={"style": style("#00ff00")}),
        )


def test_cross_track_is_rejected_but_mixed_units_are_allowed(tmp_path: Path):
    well, track, af10, af90, *_rest, session_service, fill_service, current = seeded(tmp_path)
    other_track_uid = new_uuid7_str()
    other = assignment(other_track_uid, well, "GR", "gamma_ray", "api")
    track2 = WdvCanonicalTrack(
        track_uid=other_track_uid,
        managed_well_uid=well,
        track_name="Other",
        assignments=(other,),
    )
    current = session_service.mutate_session_transactionally(
        well,
        expected_revision=current.revision,
        mutation=lambda s: s.model_copy(update={"tracks": (*s.tracks, track2)}),
    )
    with pytest.raises(CanonicalCurveFillCommandError):
        create_conditional(fill_service, well, track, af90, other, current.revision)
    mixed = create_conditional(fill_service, well, track, af90, _rest[1], current.revision)
    assert mixed.curve_fills[0].rule_type == RuleType.CONDITIONAL


def test_generic_crossover_accepts_any_curve_pair(tmp_path: Path):
    well, track, af10, af90, rhoz, nphi, _session_service, fill_service, current = seeded(tmp_path)
    updated = fill_service.create_rule(
        well,
        CreateCurveFillRuleCommand(
            expected_revision=current.revision,
            track_uid=track,
            curve_a_assignment_uid=rhoz.assignment_uid,
            curve_b_assignment_uid=nphi.assignment_uid,
            rule_type=RuleType.CROSSOVER,
            overlay_policy_uid="density-neutron-overlay-v1",
            overlay_policy_revision="approved-2026-07-01",
            style=style(),
        ),
    )
    assert updated.curve_fills[0].rule_type == RuleType.CROSSOVER
    second = fill_service.create_rule(
        well,
        CreateCurveFillRuleCommand(
            expected_revision=updated.revision,
            track_uid=track,
            curve_a_assignment_uid=af90.assignment_uid,
            curve_b_assignment_uid=af10.assignment_uid,
            rule_type=RuleType.CROSSOVER,
            overlay_policy_uid="generic-visual-crossover-v1",
            overlay_policy_revision="approved-2026-07-05",
            style=style(),
        ),
    )
    assert len(second.curve_fills) == 2


def test_assignment_track_and_canvas_cleanup_are_atomic(tmp_path: Path):
    well, track, af10, af90, *_rest, session_service, fill_service, current = seeded(tmp_path)
    with_rule = create_conditional(fill_service, well, track, af90, af10, current.revision)
    commands = CanonicalWdvCommandService(session_service=session_service, transaction_service=CanonicalWdvWorkspaceTransactionService(session_service=session_service, workspace_service=None))
    after_assignment = commands.remove_assignment(
        well,
        RemoveCurveAssignmentCommand(
            expected_revision=with_rule.revision,
            assignment_uid=af10.assignment_uid,
        ),
    )
    assert after_assignment.curve_fills == ()

    recreated = fill_service.create_rule(
        well,
        CreateCurveFillRuleCommand(
            expected_revision=after_assignment.revision,
            track_uid=track,
            curve_a_assignment_uid=af90.assignment_uid,
            rule_type=RuleType.TO_BOUNDARY,
            boundary=Boundary.RIGHT,
            style=style(),
        ),
    )
    after_track = commands.remove_track(
        well,
        RemoveTrackCommand(expected_revision=recreated.revision, track_uid=track),
    )
    assert after_track.curve_fills == ()
    assert after_track.tracks == ()


def test_clear_canvas_removes_all_rules(tmp_path: Path):
    well, track, af10, af90, *_rest, session_service, fill_service, current = seeded(tmp_path)
    with_rule = create_conditional(fill_service, well, track, af90, af10, current.revision)
    commands = CanonicalWdvCommandService(session_service=session_service, transaction_service=CanonicalWdvWorkspaceTransactionService(session_service=session_service, workspace_service=None))
    cleared = commands.clear_canvas(
        well,
        ClearCanvasCommand(expected_revision=with_rule.revision),
    )
    assert cleared.state_status == "empty"
    assert cleared.curve_fills == ()
