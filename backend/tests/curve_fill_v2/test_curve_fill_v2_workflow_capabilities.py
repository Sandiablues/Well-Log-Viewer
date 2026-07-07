from pathlib import Path

from app.curve_fill_v2.capabilities import CanonicalCurveFillCapabilityService
from app.curve_fill_v2.canonical_service import CanonicalCurveFillService
from app.curve_fill_v2.commands import (
    CreateCurveFillRuleCommand,
    RemoveCurveFillRuleCommand,
    UpdateCurveFillRuleCommand,
)
from app.curve_fill_v2.geometry_service import CanonicalCurveFillGeometryService
from app.curve_fill_v2.models import (
    Boundary,
    Comparison,
    CurveFillRuleState,
    FillStyle,
    RuleType,
)
from app.curve_fill_v2.workflow_service import CanonicalCurveFillWorkflowService
from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import (
    WdvCanonicalAssignment,
    WdvCanonicalSession,
    WdvCanonicalTrack,
    WdvCurveSampleProvenance,
    WdvCurveSampleResponse,
)
from app.wdv_session.canonical_service import CanonicalWdvSessionService


def uid():
    return new_uuid7_str()


def assignment(track, well, mnemonic, family, unit, lo, hi, direction="normal"):
    return WdvCanonicalAssignment(
        assignment_uid=uid(),
        managed_curve_uid=uid(),
        managed_product_uid=uid(),
        managed_well_uid=well,
        managed_source_uid=uid(),
        track_uid=track,
        observed_mnemonic=mnemonic,
        normalized_mnemonic=mnemonic,
        display_name=mnemonic,
        curve_family=family,
        unit=unit,
        scale_min=lo,
        scale_max=hi,
        scale_type="linear",
        scale_direction=direction,
        display_policy_source="family",
    )


class Samples:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def get_curve_samples(self, request):
        self.calls.append(request.managed_curve_uid)
        values = self.values[request.managed_curve_uid]
        samples = tuple((float(index), float(value)) for index, value in enumerate(values))
        return WdvCurveSampleResponse(
            managed_well_uid=request.managed_well_uid,
            managed_curve_uid=request.managed_curve_uid,
            managed_product_uid=uid(),
            managed_source_uid=uid(),
            observed_mnemonic="X",
            display_name="X",
            curve_family="test",
            depth_unit="ft",
            value_unit="unit",
            depth_min=0,
            depth_max=len(values) - 1,
            value_min=min(values),
            value_max=max(values),
            sample_count=len(values),
            returned_sample_count=len(values),
            provenance=WdvCurveSampleProvenance(sample_source="test", checksum="samples-v1"),
            samples=samples,
        )


def seeded(tmp_path: Path):
    well, track = uid(), uid()
    af10 = assignment(track, well, "AF10", "resistivity", "ohm.m", 0, 10)
    af90 = assignment(track, well, "AF90", "resistivity", "ohm.m", 0, 10)
    rhoz = assignment(track, well, "RHOZ", "density", "g/cm3", 1.95, 2.95)
    nphi = assignment(track, well, "NPHI", "neutron_porosity", "v/v", 0.45, -0.15, "reversed")
    gr = assignment(track, well, "GR", "gamma_ray", "api", 0, 150)
    session = WdvCanonicalSession(
        session_uid=uid(),
        managed_well_uid=well,
        state_status="active",
        tracks=(WdvCanonicalTrack(
            track_uid=track,
            managed_well_uid=well,
            track_name="Curves",
            width_px=200,
            assignments=(af10, af90, rhoz, nphi, gr),
        ),),
        selected_track_uid=track,
        updated_at="2026-07-02T17:00:00+00:00",
    )
    sessions = CanonicalWdvSessionService(storage_path=tmp_path / "sessions.json")
    current = sessions.put_session(session)
    sample_values = {
        af10.managed_curve_uid: [2, 3, 3, 3, 2],
        af90.managed_curve_uid: [1, 4, 8, 4, 1],
        rhoz.managed_curve_uid: [2.3, 2.4, 2.6, 2.4, 2.3],
        nphi.managed_curve_uid: [0.2, 0.15, 0.05, 0.15, 0.2],
        gr.managed_curve_uid: [50, 60, 70, 60, 50],
    }
    samples = Samples(sample_values)
    commands = CanonicalCurveFillService(session_service=sessions)
    geometry = CanonicalCurveFillGeometryService(session_service=sessions, sample_service=samples)
    workflow = CanonicalCurveFillWorkflowService(command_service=commands, geometry_service=geometry)
    capabilities = CanonicalCurveFillCapabilityService(session_service=sessions)
    return well, track, af10, af90, rhoz, nphi, gr, sessions, samples, workflow, capabilities, current


def style(color="#ff0000"):
    return FillStyle(color=color, opacity=0.5)


def test_capabilities_are_assignment_addressed_and_backend_resolved(tmp_path):
    well, track, af10, af90, rhoz, nphi, gr, *_rest, capabilities, _current = seeded(tmp_path)
    result = capabilities.get_capabilities(well, track_uid=track, curve_a_assignment_uid=af90.assignment_uid)
    conditional = next(mode for mode in result.modes if mode.rule_type == RuleType.CONDITIONAL)
    by_uid = {item.assignment_uid: item for item in conditional.curve_b_operands}
    assert by_uid[af10.assignment_uid].eligible is True
    assert by_uid[gr.assignment_uid].eligible is True
    assert by_uid[gr.assignment_uid].disable_reason is None
    crossover = next(mode for mode in result.modes if mode.rule_type == RuleType.CROSSOVER)
    assert crossover.eligible is True
    assert crossover.overlay_policy_uid == "generic-visual-crossover-v1"
    assert all(item.eligible for item in crossover.curve_b_operands)


def test_density_capabilities_expose_every_curve_pair(tmp_path):
    well, track, af10, af90, rhoz, nphi, gr, *_rest, capabilities, _current = seeded(tmp_path)
    result = capabilities.get_capabilities(well, track_uid=track, curve_a_assignment_uid=rhoz.assignment_uid)
    crossover = next(mode for mode in result.modes if mode.rule_type == RuleType.CROSSOVER)
    operands = {item.assignment_uid: item for item in crossover.curve_b_operands}
    assert crossover.eligible is True
    assert operands[nphi.assignment_uid].eligible is True
    assert operands[af10.assignment_uid].eligible is True
    assert all(item.disable_reason is None for item in operands.values())


def test_create_workflow_returns_resolved_session_and_only_new_geometry(tmp_path):
    well, track, af10, af90, *_rest, sessions, samples, workflow, _capabilities, current = seeded(tmp_path)
    result = workflow.create_rule(
        well,
        CreateCurveFillRuleCommand(
            expected_revision=current.revision,
            track_uid=track,
            curve_a_assignment_uid=af90.assignment_uid,
            curve_b_assignment_uid=af10.assignment_uid,
            rule_type=RuleType.CONDITIONAL,
            comparison=Comparison.GREATER_THAN,
            style=style(),
        ),
    )
    assert len(result.session.curve_fills) == 1
    assert result.session.curve_fills[0].state == CurveFillRuleState.RESOLVED
    assert len(result.geometry_delta.upsert) == 1
    assert result.geometry_delta.remove == ()
    assert result.geometry_delta.session_revision == result.session.revision
    assert len(samples.calls) == 2
    assert sessions.get_session(well) == result.session


def test_geometry_failure_keeps_created_rule_and_returns_remove_delta(tmp_path):
    well, track, af10, af90, *_rest, sessions, samples, workflow, _capabilities, current = seeded(tmp_path)
    del samples.values[af10.managed_curve_uid]
    result = workflow.create_rule(
        well,
        CreateCurveFillRuleCommand(
            expected_revision=current.revision,
            track_uid=track,
            curve_a_assignment_uid=af90.assignment_uid,
            curve_b_assignment_uid=af10.assignment_uid,
            rule_type=RuleType.CONDITIONAL,
            comparison=Comparison.GREATER_THAN,
            style=style(),
        ),
    )
    rule = result.session.curve_fills[0]
    assert rule.state == CurveFillRuleState.INVALID
    assert rule.state_reason
    assert result.geometry_delta.upsert == ()
    assert result.geometry_delta.remove == (rule.rule_uid,)
    assert sessions.get_session(well).curve_fills[0].rule_uid == rule.rule_uid


def test_update_disabled_removes_only_target_geometry_without_sample_io(tmp_path):
    well, track, af10, af90, *_rest, _sessions, samples, workflow, _capabilities, current = seeded(tmp_path)
    created = workflow.create_rule(
        well,
        CreateCurveFillRuleCommand(
            expected_revision=current.revision,
            track_uid=track,
            curve_a_assignment_uid=af90.assignment_uid,
            rule_type=RuleType.TO_BOUNDARY,
            boundary=Boundary.RIGHT,
            style=style(),
        ),
    )
    calls = len(samples.calls)
    rule_uid = created.session.curve_fills[0].rule_uid
    result = workflow.update_rule(
        well,
        UpdateCurveFillRuleCommand(
            expected_revision=created.session.revision,
            rule_uid=rule_uid,
            enabled=False,
        ),
    )
    assert result.session.curve_fills[0].state == CurveFillRuleState.DISABLED
    assert result.geometry_delta.remove == (rule_uid,)
    assert len(samples.calls) == calls


def test_remove_succeeds_without_geometry_or_sample_access(tmp_path):
    well, track, af10, af90, *_rest, _sessions, samples, workflow, _capabilities, current = seeded(tmp_path)
    created = workflow.create_rule(
        well,
        CreateCurveFillRuleCommand(
            expected_revision=current.revision,
            track_uid=track,
            curve_a_assignment_uid=af90.assignment_uid,
            rule_type=RuleType.TO_BOUNDARY,
            boundary=Boundary.LEFT,
            style=style(),
        ),
    )
    samples.values.clear()
    rule_uid = created.session.curve_fills[0].rule_uid
    result = workflow.remove_rule(
        well,
        RemoveCurveFillRuleCommand(
            expected_revision=created.session.revision,
            rule_uid=rule_uid,
        ),
    )
    assert result.session.curve_fills == ()
    assert result.geometry_delta.remove == (rule_uid,)


def test_create_command_replay_does_not_duplicate_rule_or_advance_revision(tmp_path):
    well, track, af10, af90, *_rest, _sessions, _samples, workflow, _capabilities, current = seeded(tmp_path)
    command = CreateCurveFillRuleCommand(
        expected_revision=current.revision,
        command_id=uid(),
        track_uid=track,
        curve_a_assignment_uid=af90.assignment_uid,
        curve_b_assignment_uid=af10.assignment_uid,
        rule_type=RuleType.CONDITIONAL,
        comparison=Comparison.GREATER_THAN,
        style=style(),
    )
    first = workflow.create_rule(well, command)
    replay = workflow.create_rule(well, command)
    assert len(replay.session.curve_fills) == 1
    assert replay.session.revision == first.session.revision
    assert replay.geometry_delta.upsert == ()
    assert replay.geometry_delta.remove == ()

from app.curve_fill_v2.workflow_service import HydrateCurveFillRulesCommand


def test_hydrate_resolves_all_enabled_rules_and_returns_one_delta(tmp_path):
    well, track, af10, af90, *_rest, sessions, samples, workflow, _capabilities, current = seeded(tmp_path)
    first = workflow.command_service.create_rule(
        well,
        CreateCurveFillRuleCommand(
            expected_revision=current.revision,
            track_uid=track,
            curve_a_assignment_uid=af90.assignment_uid,
            curve_b_assignment_uid=af10.assignment_uid,
            rule_type=RuleType.CONDITIONAL,
            comparison=Comparison.GREATER_THAN,
            style=style('#ff0000'),
        ),
    )
    second = workflow.command_service.create_rule(
        well,
        CreateCurveFillRuleCommand(
            expected_revision=first.revision,
            track_uid=track,
            curve_a_assignment_uid=af90.assignment_uid,
            rule_type=RuleType.TO_BOUNDARY,
            boundary=Boundary.RIGHT,
            style=style('#00ff00'),
        ),
    )
    result = workflow.hydrate_rules(
        well,
        HydrateCurveFillRulesCommand(expected_revision=second.revision),
    )
    assert len(result.geometry_delta.upsert) == 2
    assert result.geometry_delta.remove == ()
    assert all(rule.state == CurveFillRuleState.RESOLVED for rule in result.session.curve_fills)
    assert result.geometry_delta.session_revision == result.session.revision
    assert sessions.get_session(well) == result.session
    assert len(samples.calls) == 3


def test_hydrate_returns_remove_for_disabled_rule_without_sample_io(tmp_path):
    well, track, af10, af90, *_rest, _sessions, samples, workflow, _capabilities, current = seeded(tmp_path)
    created = workflow.create_rule(
        well,
        CreateCurveFillRuleCommand(
            expected_revision=current.revision,
            track_uid=track,
            curve_a_assignment_uid=af90.assignment_uid,
            rule_type=RuleType.TO_BOUNDARY,
            boundary=Boundary.LEFT,
            style=style(),
        ),
    )
    disabled = workflow.command_service.update_rule(
        well,
        UpdateCurveFillRuleCommand(
            expected_revision=created.session.revision,
            rule_uid=created.session.curve_fills[0].rule_uid,
            enabled=False,
        ),
    )
    calls = len(samples.calls)
    result = workflow.hydrate_rules(
        well,
        HydrateCurveFillRulesCommand(expected_revision=disabled.revision),
    )
    assert result.geometry_delta.upsert == ()
    assert result.geometry_delta.remove == (disabled.curve_fills[0].rule_uid,)
    assert len(samples.calls) == calls
