"""WDV-BACKEND-TEMPLATE-APPLICATION-PLAN-1 tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.wdv_templates.application_plan_service import WdvTemplateApplicationPlanService
from backend.app.wdv_templates.models import (
    WdvTemplateApplicationPlanEnvelope,
    WdvTemplateApplicationPlanRequest,
    WdvTemplateApplicationPlanResponse,
    WdvTemplateApplicationTrackPlanResponse,
)

client = TestClient(app)


def _loaded_open_hole_curves() -> list[dict[str, object]]:
    return [
        {
            "product_id": "curve_gr",
            "curve_id": "curve_gr",
            "mnemonic": "GR",
            "display_name": "Gamma Ray",
            "curve_family": "gamma_ray",
            "unit": "API",
        },
        {
            "product_id": "curve_ild",
            "curve_id": "curve_ild",
            "mnemonic": "ILD",
            "display_name": "Deep Induction Resistivity",
            "curve_family": "resistivity",
            "unit": "ohm.m",
        },
        {
            "product_id": "curve_rhob",
            "curve_id": "curve_rhob",
            "mnemonic": "RHOB",
            "display_name": "Bulk Density",
            "curve_family": "density",
            "unit": "g/cc",
        },
        {
            "product_id": "curve_nphi",
            "curve_id": "curve_nphi",
            "mnemonic": "NPHI",
            "display_name": "Neutron Porosity",
            "curve_family": "neutron_porosity",
            "unit": "v/v",
        },
    ]


def test_application_plan_models_and_service_are_importable() -> None:
    assert WdvTemplateApplicationPlanService is not None
    assert WdvTemplateApplicationPlanRequest is not None
    assert WdvTemplateApplicationPlanResponse is not None
    assert WdvTemplateApplicationTrackPlanResponse is not None
    assert WdvTemplateApplicationPlanEnvelope is not None


def test_build_application_plan_endpoint_returns_non_mutating_plan() -> None:
    response = client.post(
        "/api/wlv/wdv/templates/application-plans/build",
        json={
            "template_key": "open_hole_triple_combo",
            "workflow_context": "open_hole",
            "loaded_curve_items": _loaded_open_hole_curves(),
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["service"] == "wdv_template_application_plan_service"
    assert payload["contract_version"] == "wdv_template_application_plan_v1"
    assert payload["mutation_performed"] is False
    assert payload["knowledge_policy"]["approved_only"] is True
    assert payload["knowledge_policy"]["frontend_inference_allowed"] is False

    plan = payload["plan"]
    assert plan["template_key"] == "open_hole_triple_combo"
    assert plan["template_label"]
    assert plan["application_plan_id"].startswith("wdv_template_application_plan_")
    assert plan["apply_mode"] == "review_required_non_mutating_plan"
    assert plan["selected_curve_count"] >= 4
    assert len(plan["tracks"]) >= 3
    assert any(track["track_key"] == "resistivity" for track in plan["tracks"])
    assert any(track["selected_curves"] for track in plan["tracks"])


def test_application_plan_blocks_missing_required_families() -> None:
    response = client.post(
        "/api/wlv/wdv/templates/application-plans/build",
        json={
            "template_key": "open_hole_triple_combo",
            "workflow_context": "open_hole",
            "loaded_curve_items": [
                {
                    "product_id": "curve_gr",
                    "curve_id": "curve_gr",
                    "mnemonic": "GR",
                    "display_name": "Gamma Ray",
                    "curve_family": "gamma_ray",
                    "unit": "API",
                }
            ],
        },
    )
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["apply_eligible"] is False
    assert "missing_required_families" in plan["blocking_issues"]
    assert plan["missing_required_families"]


def test_application_plan_accepts_frontend_loaded_items_alias_payload() -> None:
    response = client.post(
        "/api/wlv/wdv/templates/application-plans/build",
        json={
            "templateKey": "open_hole_triple_combo",
            "workflowContext": "open_hole",
            "loaded_items": [
                {"item_id": "gr_1", "mnemonic": "GR", "curveFamily": "gamma_ray", "unit": "API"},
                {"item_id": "ild_1", "mnemonic": "ILD", "curveFamily": "resistivity", "unit": "ohm.m"},
                {"item_id": "rhob_1", "mnemonic": "RHOB", "curveFamily": "density", "unit": "g/cc"},
                {"item_id": "nphi_1", "mnemonic": "NPHI", "curveFamily": "neutron_porosity", "unit": "v/v"},
            ],
        },
    )
    assert response.status_code == 200
    plan = response.json()["plan"]

    assert plan["template_key"] == "open_hole_triple_combo"
    assert plan["selected_curve_count"] >= 4
    assert plan["missing_required_families"] == []
    assert "missing_required_families" not in plan["blocking_issues"]
    assert any(track["selected_curves"] for track in plan["tracks"])

    selected_mnemonics = {curve["mnemonic"] for curve in plan["selected_curves"]}
    assert {"GR", "ILD", "RHOB", "NPHI"}.issubset(selected_mnemonics)


def test_application_plan_unknown_template_returns_404() -> None:
    response = client.post(
        "/api/wlv/wdv/templates/application-plans/build",
        json={
            "template_key": "not_a_real_template",
            "loaded_curve_items": _loaded_open_hole_curves(),
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "wdv_template_application_plan_not_found"
