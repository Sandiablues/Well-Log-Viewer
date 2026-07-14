from app.identity.wdv_contract_v2 import WdvCanonicalAssignment, WdvCanonicalSession, WdvCanonicalTrack
from app.wdv_session.view_contract import build_assignment_scale_ticks, project_canonical_session_view


def _uuid7(seed: int) -> str:
    return f"01900000-0000-7000-8000-{seed:012d}"


def _assignment(
    *,
    scale_min: float,
    scale_max: float,
    scale_type: str,
    scale_direction: str = "normal",
    position_anchor: str = "center",
    horizontal_offset_pct: float = 0.0,
) -> WdvCanonicalAssignment:
    return WdvCanonicalAssignment(
        assignment_uid=_uuid7(3),
        managed_curve_uid=_uuid7(4),
        managed_product_uid=_uuid7(5),
        managed_well_uid=_uuid7(1),
        managed_source_uid=_uuid7(6),
        track_uid=_uuid7(2),
        observed_mnemonic="TEST",
        display_name="TEST",
        unit="API",
        scale_min=scale_min,
        scale_max=scale_max,
        scale_min_label=str(scale_min),
        scale_max_label=str(scale_max),
        scale_type=scale_type,
        scale_direction=scale_direction,
        position_anchor=position_anchor,
        horizontal_offset_pct=horizontal_offset_pct,
        source="test",
    )


def test_linear_ticks_are_backend_owned_and_span_the_plot_frame():
    ticks = build_assignment_scale_ticks(_assignment(scale_min=0.0, scale_max=150.0, scale_type="linear"))
    assert [tick.label for tick in ticks] == ["0", "50", "100", "150"]
    assert [tick.normalized_position for tick in ticks] == [0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0]


def test_log_ticks_use_decade_ratio_from_the_actual_lower_endpoint():
    ticks = build_assignment_scale_ticks(_assignment(scale_min=0.2, scale_max=2000.0, scale_type="logarithmic"))
    assert [tick.label for tick in ticks] == ["0.2", "2", "20", "200", "2000"]
    assert [tick.normalized_position for tick in ticks] == [0.0, 0.25, 0.5, 0.75, 1.0]


def test_reversed_scale_positions_are_backend_owned():
    ticks = build_assignment_scale_ticks(_assignment(scale_min=0.0, scale_max=150.0, scale_type="linear", scale_direction="reversed"))
    assert ticks[0].normalized_position == 1.0
    assert ticks[-1].normalized_position == 0.0


def test_position_anchor_and_offset_follow_curve_renderer_semantics():
    ticks = build_assignment_scale_ticks(_assignment(scale_min=0.0, scale_max=100.0, scale_type="linear", position_anchor="right", horizontal_offset_pct=10.0))
    assert ticks[0].normalized_position == 0.28
    assert ticks[-1].normalized_position == 1.0


def test_projection_adds_ticks_without_mutating_persisted_session_contract():
    assignment = _assignment(scale_min=0.0, scale_max=150.0, scale_type="linear")
    track = WdvCanonicalTrack(
        track_uid=assignment.track_uid,
        managed_well_uid=assignment.managed_well_uid,
        track_name="Curves",
        track_type="curve",
        width_px=220,
        assignments=(assignment,),
    )
    session = WdvCanonicalSession(
        session_uid=_uuid7(7),
        managed_well_uid=assignment.managed_well_uid,
        revision=1,
        state_status="active",
        tracks=(track,),
        updated_at="2026-07-11T16:00:00+00:00",
    )
    before = session.model_dump(mode="json")
    view = project_canonical_session_view(session)
    after = session.model_dump(mode="json")
    assert before == after
    assert "scale_ticks" not in before["tracks"][0]["assignments"][0]
    assert len(view.tracks[0].assignments[0].scale_ticks) == 4
