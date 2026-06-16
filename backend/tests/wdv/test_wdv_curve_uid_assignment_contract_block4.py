from __future__ import annotations

from app.wdv_session.service import WdvSessionLayoutStateService
from app.wdv_templates.application_apply_service import WdvTemplateApplicationApplyService
from app.wdv_templates.models import (
    WdvRecommendedCurveResponse,
    WdvTemplateApplicationApplyRequest,
    WdvTemplateApplicationPlanEnvelope,
    WdvTemplateApplicationPlanResponse,
    WdvTemplateApplicationTrackPlanResponse,
)


def _uid_plan_envelope() -> WdvTemplateApplicationPlanEnvelope:
    gr = WdvRecommendedCurveResponse(
        product_id="product:gr:upper",
        curve_uid="wlv_curve:gr_upper",
        well_uid="well:forge",
        source_uid="source:las:forge",
        kr_curve_type_id="gamma_ray",
        observed_mnemonic="ECGR",
        normalized_mnemonic="ECGR",
        curve_id="ECGR",
        mnemonic="ECGR",
        display_name="ECGR Gamma Ray",
        unit="API",
        curve_family="gamma_ray",
        raw_curve_family="gamma_ray",
        selection_reason="selected",
    )
    plan = WdvTemplateApplicationPlanResponse(
        application_plan_id="plan-uid-block4",
        plan_status="ready_for_review",
        template_key="open_hole_triple_combo",
        template_label="Open-Hole Triple Combo",
        workflow_context="open_hole",
        source_recommendation_rank=1,
        source_recommendation_score=99.0,
        apply_eligible=True,
        blocking_issues=[],
        warnings=[],
        selected_curve_count=1,
        alternate_curve_count=0,
        excluded_curve_count=0,
        selected_curves=[gr],
        tracks=[
            WdvTemplateApplicationTrackPlanResponse(
                track_id="gr_track",
                track_key="gr_track",
                track_number=1,
                track_name="GR",
                renderer_type="line_curve",
                selected_curves=[gr],
                scale_defaults=[{"curve_family": "gamma_ray", "scale_type": "linear", "scale_min": 0, "scale_max": 150}],
            ),
        ],
        renderer_requirements=[],
        missing_required_families=[],
        missing_preferred_families=[],
        reason_codes=["required_families_covered"],
    )
    return WdvTemplateApplicationPlanEnvelope(plan=plan, knowledge_policy={"approved_only": True})


def test_template_apply_writes_uid_identity_into_session_assignment(tmp_path):
    class FakePlanService:
        def build_from_request(self, request):
            return _uid_plan_envelope()

    layout_service = WdvSessionLayoutStateService(storage_path=tmp_path / "session_layouts.json")
    service = WdvTemplateApplicationApplyService(
        layout_service=layout_service,
        plan_service=FakePlanService(),
    )

    service.apply_from_request(
        WdvTemplateApplicationApplyRequest(
            managed_well_id="managed-well-uid-block4",
            template_key="open_hole_triple_combo",
            workflow_context="open_hole",
            loaded_curve_items=[],
        )
    )

    restored = layout_service.get_layout("managed-well-uid-block4")
    assignment = restored.tracks[0].curves[0]

    assert assignment.curve_uid == "wlv_curve:gr_upper"
    assert assignment.product_id == "product:gr:upper"
    assert assignment.curve_id == "ECGR"
    assert assignment.kr_curve_type_id == "gamma_ray"
    assert assignment.observed_mnemonic == "ECGR"
    assert assignment.normalized_mnemonic == "ECGR"
    assert assignment.well_uid == "well:forge"
    assert assignment.source_uid == "source:las:forge"
    assert "wlv_curve:gr_upper" in assignment.assignment_id
