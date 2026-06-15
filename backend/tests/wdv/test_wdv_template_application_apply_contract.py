from __future__ import annotations

from app.wdv_session.service import WdvSessionLayoutStateService
from app.wdv_templates.application_apply_service import WdvTemplateApplicationApplyService
from app.wdv_templates.application_plan_service import WdvTemplateApplicationPlanService
from app.wdv_templates.models import (
    WdvRecommendedCurveResponse,
    WdvTemplateApplicationApplyRequest,
    WdvTemplateApplicationPlanEnvelope,
    WdvTemplateApplicationPlanResponse,
    WdvTemplateApplicationTrackPlanResponse,
)


def _fake_plan_envelope() -> WdvTemplateApplicationPlanEnvelope:
    gr = WdvRecommendedCurveResponse(
        product_id="gr-prod",
        curve_id="GR",
        mnemonic="GR",
        display_name="Gamma Ray",
        unit="API",
        curve_family="gamma_ray",
        raw_curve_family="gamma_ray",
        selection_reason="selected",
    )
    rt = WdvRecommendedCurveResponse(
        product_id="rt-prod",
        curve_id="RT",
        mnemonic="RT",
        display_name="Deep Resistivity",
        unit="ohm.m",
        curve_family="resistivity",
        raw_curve_family="resistivity",
        selection_reason="selected",
    )
    plan = WdvTemplateApplicationPlanResponse(
        application_plan_id="plan-test",
        plan_status="ready_for_review",
        template_key="open_hole_triple_combo",
        template_label="Open-Hole Triple Combo",
        workflow_context="open_hole",
        source_recommendation_rank=1,
        source_recommendation_score=99.0,
        apply_eligible=True,
        blocking_issues=[],
        warnings=[],
        selected_curve_count=2,
        alternate_curve_count=0,
        excluded_curve_count=0,
        selected_curves=[gr, rt],
        tracks=[
            WdvTemplateApplicationTrackPlanResponse(
                track_id="reference_depth",
                track_key="reference_depth",
                track_number=0,
                track_name="Reference / Depth",
                renderer_type="event_track",
                selected_curves=[],
            ),
            WdvTemplateApplicationTrackPlanResponse(
                track_id="gr_track",
                track_key="gr_track",
                track_number=1,
                track_name="GR",
                renderer_type="line_curve",
                selected_curves=[gr],
                scale_defaults=[{"curve_family": "gamma_ray", "scale_type": "linear", "scale_min": 0, "scale_max": 150}],
            ),
            WdvTemplateApplicationTrackPlanResponse(
                track_id="res_track",
                track_key="res_track",
                track_number=2,
                track_name="Resistivity",
                renderer_type="log_curve",
                selected_curves=[rt],
                scale_defaults=[{"curve_family": "resistivity", "scale_type": "log", "scale_min": 0.2, "scale_max": 200}],
            ),
        ],
        renderer_requirements=[],
        missing_required_families=[],
        missing_preferred_families=[],
        reason_codes=["required_families_covered"],
    )
    return WdvTemplateApplicationPlanEnvelope(plan=plan, knowledge_policy={"approved_only": True})


def test_template_application_apply_writes_backend_session_layout(monkeypatch, tmp_path):
    class FakePlanService:
        def build_from_request(self, request):
            return _fake_plan_envelope()

    layout_service = WdvSessionLayoutStateService(storage_path=tmp_path / "session_layouts.json")
    service = WdvTemplateApplicationApplyService(
        layout_service=layout_service,
        plan_service=FakePlanService(),
    )

    request = WdvTemplateApplicationApplyRequest(
        managed_well_id="managed-well-1",
        template_key="open_hole_triple_combo",
        workflow_context="open_hole",
        loaded_curve_items=[],
    )
    result = service.apply_from_request(request)

    assert result.mutation_performed is True
    assert result.contract_version == "wdv_template_application_apply_v1"
    assert result.apply_summary.track_count == 3
    assert result.apply_summary.curve_assignment_count == 2
    assert result.layout["state_status"] == "active"
    assert result.layout["source"] == "backend_template_apply:open_hole_triple_combo"
    assert result.layout["tracks"][0]["track_type"] == "depth"
    assert result.layout["tracks"][2]["lattice"] == "logarithmic"

    restored = layout_service.get_layout("managed-well-1")
    assert restored.state_status == "active"
    assert len(restored.tracks) == 3
    assert restored.tracks[1].curves[0].curve_id == "GR"
