from __future__ import annotations

from types import SimpleNamespace

from app.curve_fill.models import (
    ComparisonBasis,
    ComparisonCondition,
    ConstantReferenceOperand,
    CurveOperand,
    FillMode,
    FillStyle,
)
from app.curve_fill_render.service import CurveFillRenderPackageService
from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import (
    WdvCanonicalAssignment,
    WdvCanonicalCurveFill,
    WdvCanonicalSession,
    WdvCanonicalTrack,
)


def uid() -> str:
    return new_uuid7_str()


def assignment(*, well: str, track: str, curve: str, scale_min: float, scale_max: float, direction: str = "normal") -> WdvCanonicalAssignment:
    return WdvCanonicalAssignment(
        assignment_uid=uid(),
        managed_curve_uid=curve,
        managed_product_uid=uid(),
        managed_well_uid=well,
        managed_source_uid=uid(),
        track_uid=track,
        observed_mnemonic="TEST",
        display_name="Test",
        scale_min=scale_min,
        scale_max=scale_max,
        scale_min_label=str(scale_min),
        scale_max_label=str(scale_max),
        scale_type="linear",
        scale_direction=direction,
    )


class FakeSessionService:
    def __init__(self, session):
        self.session = session

    def get_session(self, managed_well_uid):
        assert managed_well_uid == self.session.managed_well_uid
        return self.session


class FakeSampleService:
    def __init__(self, samples):
        self.samples = samples

    def get_curve_samples(self, request):
        values = self.samples[str(request.managed_curve_uid)]
        return SimpleNamespace(samples=tuple(values), value_unit="unit")


def make_session(*, crossover: bool = False, constant: bool = False, gap: bool = False):
    well, track, curve_a, curve_b = uid(), uid(), uid(), uid()
    a = assignment(well=well, track=track, curve=curve_a, scale_min=0, scale_max=10)
    b = assignment(
        well=well,
        track=track,
        curve=curve_b,
        scale_min=0,
        scale_max=10,
        direction="reversed" if crossover else "normal",
    )
    operand_a = CurveOperand(managed_well_uid=well, curve_uid=curve_a, depth_domain_uid="MD", unit="unit")
    operand_b = (
        ConstantReferenceOperand(
            managed_well_uid=well,
            reference_uid="constant-5",
            depth_domain_uid="MD",
            unit="unit",
            value=5,
        )
        if constant
        else CurveOperand(managed_well_uid=well, curve_uid=curve_b, depth_domain_uid="MD", unit="unit")
    )
    fill = WdvCanonicalCurveFill(
        fill_uid=uid(),
        track_uid=track,
        owner_assignment_uid=a.assignment_uid,
        fill_mode=FillMode.CROSSOVER if crossover else FillMode.CONDITIONAL,
        operand_a=operand_a,
        operand_b=operand_b,
        condition=None if crossover else ComparisonCondition.A_GREATER_THAN_B,
        comparison_basis=(ComparisonBasis.NORMALIZED_TRACK_POSITION if crossover else ComparisonBasis.ENGINEERING_VALUE),
        overlay_policy_id="overlay-v1" if crossover else None,
        overlay_policy_revision="1" if crossover else None,
        style=FillStyle(fill="#d8b85a", opacity=0.55),
        depth_unit="ft",
    )
    session = WdvCanonicalSession(
        session_uid=uid(),
        managed_well_uid=well,
        revision=7,
        state_status="active",
        tracks=(WdvCanonicalTrack(track_uid=track, managed_well_uid=well, track_name="Track", assignments=(a, b)),),
        curve_fills=(fill,),
        updated_at="2026-07-01T20:00:00+00:00",
    )
    samples = {
        curve_a: [(100.0, 4.0), (110.0, 6.0), (120.0, 8.0)],
        curve_b: [(100.0, 7.0), (110.0, 5.0), (120.0, 3.0)],
    }
    if gap:
        samples[curve_a] = [(100.0, 4.0), (110.0, 6.0), (200.0, 8.0)]
        samples[curve_b] = [(100.0, 7.0), (110.0, 5.0), (200.0, 3.0)]
    return session, samples, fill


def test_conditional_fill_render_package_resolves_exact_crossing():
    session, samples, fill = make_session()
    package = CurveFillRenderPackageService(
        session_service=FakeSessionService(session),
        sample_service=FakeSampleService(samples),
    ).get_render_package(session.managed_well_uid)
    item = package.fills[0]
    assert item.fill_uid == fill.fill_uid
    assert item.status == "resolved"
    assert len(item.geometry.segments) == 1
    assert item.geometry.segments[0].top_depth == 107.5
    assert item.geometry.segments[0].base_depth == 120.0


def test_constant_reference_uses_owner_track_scale():
    session, samples, _ = make_session(constant=True)
    package = CurveFillRenderPackageService(
        session_service=FakeSessionService(session),
        sample_service=FakeSampleService(samples),
    ).get_render_package(session.managed_well_uid)
    segment = package.fills[0].geometry.segments[0]
    assert segment.top_depth == 105.0
    assert segment.vertices[-1].b_track_position == 0.5


def test_large_sample_gap_is_not_interpolated_across():
    session, samples, _ = make_session(gap=True)
    package = CurveFillRenderPackageService(
        session_service=FakeSessionService(session),
        sample_service=FakeSampleService(samples),
    ).get_render_package(session.managed_well_uid)
    # Exact source depths remain valid, but no synthetic depth inside the 90-ft gap is created.
    vertices = package.fills[0].geometry.segments[0].vertices
    assert all(vertex.depth not in {120.0, 150.0} for vertex in vertices)


def test_crossover_uses_backend_normalized_track_order():
    session, samples, _ = make_session(crossover=True)
    package = CurveFillRenderPackageService(
        session_service=FakeSessionService(session),
        sample_service=FakeSampleService(samples),
    ).get_render_package(session.managed_well_uid)
    assert package.fills[0].status == "resolved"
    assert package.fills[0].geometry.comparison_basis == ComparisonBasis.NORMALIZED_TRACK_POSITION
    assert len(package.fills[0].geometry.segments) == 1
