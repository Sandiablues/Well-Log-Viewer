from pathlib import Path
from uuid import uuid4

import pytest

from app.curve_fill_v2.geometry_service import (
    CanonicalCurveFillGeometryService,
    CurveFillGeometryCommandError,
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


def uid(): return new_uuid7_str()


class Samples:
    def __init__(self, values): self.values = values; self.calls=[]
    def get_curve_samples(self, request):
        self.calls.append(request.managed_curve_uid)
        vals=self.values[request.managed_curve_uid]
        samples=tuple((float(i), float(v)) for i,v in enumerate(vals))
        return WdvCurveSampleResponse(
            managed_well_uid=request.managed_well_uid,
            managed_curve_uid=request.managed_curve_uid,
            managed_product_uid=uid(), managed_source_uid=uid(),
            observed_mnemonic='X', display_name='X', curve_family='resistivity',
            depth_unit='ft', value_unit='ohm.m', depth_min=0, depth_max=len(vals)-1,
            value_min=min(vals), value_max=max(vals), sample_count=len(vals),
            returned_sample_count=len(vals), provenance=WdvCurveSampleProvenance(sample_source='test', checksum='rev1'),
            samples=samples,
        )


def build(tmp_path: Path):
    well, track, aa, ab, ca, cb = [uid() for _ in range(6)]
    def assignment(au, cu, mnemonic):
        return WdvCanonicalAssignment(
            assignment_uid=au, managed_curve_uid=cu, managed_product_uid=uid(),
            managed_well_uid=well, managed_source_uid=uid(), track_uid=track,
            observed_mnemonic=mnemonic, display_name=mnemonic, curve_family='resistivity', unit='ohm.m',
            scale_min=0, scale_max=10, scale_type='linear', scale_direction='normal',
        )
    rule=CanonicalCurveFillRule(
        rule_uid=uid(), managed_well_uid=well, track_uid=track,
        curve_a_assignment_uid=aa, curve_b_assignment_uid=ab, order=0,
        rule_type=RuleType.CONDITIONAL, comparison=Comparison.GREATER_THAN,
        style=FillStyle(color='#ff0000', opacity=.5), state=CurveFillRuleState.PENDING_GEOMETRY,
    )
    session=WdvCanonicalSession(
        session_uid=uid(), managed_well_uid=well, revision=0, state_status='active',
        tracks=(WdvCanonicalTrack(track_uid=track, managed_well_uid=well, track_name='R', width_px=200,
            assignments=(assignment(aa,ca,'AF90'), assignment(ab,cb,'AF10'))),),
        curve_fills=(rule,), updated_at='2026-07-02T17:00:00+00:00',
    )
    store=tmp_path/'sessions.json'
    svc=CanonicalWdvSessionService(storage_path=store)
    svc.mutate_session_transactionally(well, expected_revision=0, mutation=lambda _: session)
    current=svc.get_session(well)
    samples=Samples({ca:[1,4,8,4,1], cb:[2,3,3,3,2]})
    return well, rule.rule_uid, svc, samples, current


def test_resolve_returns_incremental_upsert_and_persists_resolved_state(tmp_path):
    well, rule_uid, sessions, samples, current=build(tmp_path)
    service=CanonicalCurveFillGeometryService(session_service=sessions, sample_service=samples)
    delta=service.resolve_rule(well, ResolveCurveFillGeometryCommand(expected_revision=current.revision, rule_uid=rule_uid))
    assert len(delta.upsert)==1 and delta.remove==()
    assert delta.upsert[0].polygons
    persisted=sessions.get_session(well)
    rule=persisted.curve_fills[0]
    assert rule.state==CurveFillRuleState.RESOLVED
    assert rule.geometry_revision==delta.upsert[0].geometry_revision
    assert delta.session_revision==persisted.revision
    assert len(samples.calls)==2


def test_resolution_is_dependency_deterministic(tmp_path):
    well, rule_uid, sessions, samples, current=build(tmp_path)
    service=CanonicalCurveFillGeometryService(session_service=sessions, sample_service=samples)
    first=service.resolve_rule(well, ResolveCurveFillGeometryCommand(expected_revision=current.revision, rule_uid=rule_uid))
    invalidated=service.invalidate_rule(well, expected_revision=first.session_revision, rule_uid=rule_uid)
    second=service.resolve_rule(well, ResolveCurveFillGeometryCommand(expected_revision=invalidated.session_revision, rule_uid=rule_uid))
    assert first.upsert[0].dependency_key==second.upsert[0].dependency_key
    assert first.upsert[0].geometry_revision==second.upsert[0].geometry_revision


def test_invalidate_removes_only_target_rule_geometry(tmp_path):
    well, rule_uid, sessions, samples, current=build(tmp_path)
    service=CanonicalCurveFillGeometryService(session_service=sessions, sample_service=samples)
    delta=service.invalidate_rule(well, expected_revision=current.revision, rule_uid=rule_uid)
    assert delta.remove==(rule_uid,) and delta.upsert==()
    assert sessions.get_session(well).curve_fills[0].state==CurveFillRuleState.PENDING_GEOMETRY


def test_resolution_failure_marks_rule_invalid_but_does_not_remove_it(tmp_path):
    well, rule_uid, sessions, samples, current=build(tmp_path)
    samples.values.clear()
    service=CanonicalCurveFillGeometryService(session_service=sessions, sample_service=samples)
    with pytest.raises(CurveFillGeometryCommandError):
        service.resolve_rule(well, ResolveCurveFillGeometryCommand(expected_revision=current.revision, rule_uid=rule_uid))
    rule=sessions.get_session(well).curve_fills[0]
    assert rule.state==CurveFillRuleState.INVALID
    assert rule.state_reason


def test_stale_revision_rejected_before_sample_io(tmp_path):
    well, rule_uid, sessions, samples, current=build(tmp_path)
    service=CanonicalCurveFillGeometryService(session_service=sessions, sample_service=samples)
    with pytest.raises(Exception, match='Expected revision'):
        service.resolve_rule(well, ResolveCurveFillGeometryCommand(expected_revision=999, rule_uid=rule_uid))
    assert samples.calls==[]
