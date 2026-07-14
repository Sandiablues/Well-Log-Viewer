from app.curve_fill_v2.geometry_service import CurveFillGeometryDelta
from app.curve_fill_v2.router import (
    CurveFillCommandResultView,
    workflow_create_rule,
    workflow_hydrate_rules,
    workflow_remove_rule,
    workflow_reorder_rules,
    workflow_update_rule,
)
from app.curve_fill_v2.workflow_service import CurveFillCommandResult
from app.identity.wdv_contract_v2 import (
    WdvCanonicalAssignment,
    WdvCanonicalSession,
    WdvCanonicalTrack,
)


def _uuid7(seed: int) -> str:
    return f"01900000-0000-7000-8000-{seed:012d}"


def _result() -> CurveFillCommandResult:
    well_uid = _uuid7(1)
    track_uid = _uuid7(2)
    assignment = WdvCanonicalAssignment(
        assignment_uid=_uuid7(3),
        managed_curve_uid=_uuid7(4),
        managed_product_uid=_uuid7(5),
        managed_well_uid=well_uid,
        managed_source_uid=_uuid7(6),
        track_uid=track_uid,
        observed_mnemonic="AF90",
        display_name="AF90",
        unit="ohm.m",
        scale_min=0.2,
        scale_max=2000.0,
        scale_min_label="0.2",
        scale_max_label="2000",
        scale_type="logarithmic",
        source="test",
    )
    session = WdvCanonicalSession(
        session_uid=_uuid7(7),
        managed_well_uid=well_uid,
        revision=12,
        state_status="active",
        tracks=(
            WdvCanonicalTrack(
                track_uid=track_uid,
                managed_well_uid=well_uid,
                track_name="Curves",
                track_type="curve",
                width_px=220,
                assignments=(assignment,),
            ),
        ),
        updated_at="2026-07-11T20:00:00+00:00",
    )
    return CurveFillCommandResult(
        session=session,
        geometry_delta=CurveFillGeometryDelta(
            managed_well_uid=well_uid,
            session_revision=session.revision,
        ),
    )


class _WorkflowService:
    def __init__(self, result: CurveFillCommandResult):
        self.result = result

    def create_rule(self, *_args):
        return self.result

    def update_rule(self, *_args):
        return self.result

    def remove_rule(self, *_args):
        return self.result

    def reorder_rules(self, *_args):
        return self.result

    def hydrate_rules(self, *_args):
        return self.result


def _assert_scale_view(result):
    assert isinstance(result, CurveFillCommandResultView)
    assignment = result.session.tracks[0].assignments[0]
    assert [tick.label for tick in assignment.scale_ticks] == ["0.2", "2", "20", "200", "2000"]
    assert [tick.normalized_position for tick in assignment.scale_ticks] == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_every_curve_fill_workflow_route_returns_the_backend_owned_scale_view_contract():
    service = _WorkflowService(_result())
    well_uid = service.result.session.managed_well_uid
    command = object()

    results = (
        workflow_create_rule(well_uid, command, service),
        workflow_update_rule(well_uid, command, service),
        workflow_remove_rule(well_uid, command, service),
        workflow_reorder_rules(well_uid, command, service),
        workflow_hydrate_rules(well_uid, command, service),
    )

    for result in results:
        _assert_scale_view(result)


def test_curve_fill_api_projection_does_not_mutate_the_durable_canonical_session():
    raw = _result()
    before = raw.session.model_dump(mode="json")
    projected = workflow_hydrate_rules(
        raw.session.managed_well_uid,
        object(),
        _WorkflowService(raw),
    )
    after = raw.session.model_dump(mode="json")

    assert before == after
    assert "scale_ticks" not in before["tracks"][0]["assignments"][0]
    assert projected.session.tracks[0].assignments[0].scale_ticks
