from pathlib import Path

from app.curve_fill_v2.geometry_service import (
    CanonicalCurveFillGeometryService,
    ResolveCurveFillGeometryCommand,
)
from app.curve_fill_v2.models import (
    CanonicalCurveFillRule,
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
    WdvCurveSampleProvenance,
    WdvCurveSampleResponse,
)
from app.wdv_session.canonical_service import CanonicalWdvSessionService


def uid() -> str:
    return new_uuid7_str()


class Workspace:
    def __init__(self, common_depth_unit: str):
        self.common_depth_unit = common_depth_unit
        self.calls = 0

    def get_workspace(self):
        self.calls += 1
        return type("WorkspaceState", (), {"common_depth_unit": self.common_depth_unit})()


class Samples:
    def __init__(self, values):
        self.values = values
        self.requests = []

    def get_curve_samples(self, request):
        self.requests.append(request)
        vals = self.values[request.managed_curve_uid]
        samples = tuple((float(i), float(v)) for i, v in enumerate(vals))
        return WdvCurveSampleResponse(
            managed_well_uid=request.managed_well_uid,
            managed_curve_uid=request.managed_curve_uid,
            managed_product_uid=uid(),
            managed_source_uid=uid(),
            observed_mnemonic="X",
            display_name="X",
            curve_family="resistivity",
            depth_unit=request.target_depth_unit,
            value_unit="ohm.m",
            depth_min=0,
            depth_max=len(vals) - 1,
            value_min=min(vals),
            value_max=max(vals),
            sample_count=len(vals),
            returned_sample_count=len(vals),
            provenance=WdvCurveSampleProvenance(
                sample_source="test",
                checksum=f"rev-{request.target_depth_unit}",
            ),
            samples=samples,
        )


def build(tmp_path: Path, common_depth_unit: str):
    well, track, aa, ab, ca, cb = [uid() for _ in range(6)]

    def assignment(assignment_uid, curve_uid, mnemonic):
        return WdvCanonicalAssignment(
            assignment_uid=assignment_uid,
            managed_curve_uid=curve_uid,
            managed_product_uid=uid(),
            managed_well_uid=well,
            managed_source_uid=uid(),
            track_uid=track,
            observed_mnemonic=mnemonic,
            display_name=mnemonic,
            curve_family="resistivity",
            unit="ohm.m",
            scale_min=0,
            scale_max=10,
            scale_type="linear",
            scale_direction="normal",
        )

    rule = CanonicalCurveFillRule(
        rule_uid=uid(),
        managed_well_uid=well,
        track_uid=track,
        curve_a_assignment_uid=aa,
        curve_b_assignment_uid=ab,
        order=0,
        rule_type=RuleType.CONDITIONAL,
        comparison=Comparison.GREATER_THAN,
        style=FillStyle(color="#ff0000", opacity=0.5),
        state=CurveFillRuleState.PENDING_GEOMETRY,
    )

    session = WdvCanonicalSession(
        session_uid=uid(),
        managed_well_uid=well,
        revision=0,
        state_status="active",
        tracks=(
            WdvCanonicalTrack(
                track_uid=track,
                managed_well_uid=well,
                track_name="R",
                width_px=200,
                assignments=(
                    assignment(aa, ca, "AF90"),
                    assignment(ab, cb, "AF10"),
                ),
            ),
        ),
        curve_fills=(rule,),
        updated_at="2026-07-11T20:00:00+00:00",
    )

    sessions = CanonicalWdvSessionService(storage_path=tmp_path / f"sessions-{common_depth_unit}.json")
    sessions.mutate_session_transactionally(
        well,
        expected_revision=0,
        mutation=lambda _: session,
    )
    current = sessions.get_session(well)
    samples = Samples({ca: [1, 4, 8, 4, 1], cb: [2, 3, 3, 3, 2]})
    workspace = Workspace(common_depth_unit)

    service = CanonicalCurveFillGeometryService(
        session_service=sessions,
        sample_service=samples,
        workspace_service=workspace,
    )
    return service, samples, workspace, well, rule.rule_uid, current.revision


def test_curve_fill_requests_samples_in_common_depth_unit_metres(tmp_path):
    service, samples, workspace, well, rule_uid, revision = build(tmp_path, "m")

    delta = service.resolve_rule(
        well,
        ResolveCurveFillGeometryCommand(
            expected_revision=revision,
            rule_uid=rule_uid,
        ),
    )

    assert workspace.calls == 1
    assert [request.target_depth_unit for request in samples.requests] == ["m", "m"]
    assert delta.upsert[0].depth_unit == "m"


def test_curve_fill_requests_samples_in_common_depth_unit_feet(tmp_path):
    service, samples, workspace, well, rule_uid, revision = build(tmp_path, "ft")

    delta = service.resolve_rule(
        well,
        ResolveCurveFillGeometryCommand(
            expected_revision=revision,
            rule_uid=rule_uid,
        ),
    )

    assert workspace.calls == 1
    assert [request.target_depth_unit for request in samples.requests] == ["ft", "ft"]
    assert delta.upsert[0].depth_unit == "ft"
