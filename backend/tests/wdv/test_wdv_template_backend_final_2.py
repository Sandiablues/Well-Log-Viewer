"""Backend-only WDV template service tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.knowledge.governance import GovernanceStatus
from app.knowledge.managed_repository import ManagedKRRepository
from app.main import app
from app.wdv_templates.service import WdvTemplateService


PROJECT_ROOT = Path(__file__).resolve().parents[3]
KR_PATH = PROJECT_ROOT / "backend" / "data" / "knowledge" / "managed_knowledge.json"


def test_service_lists_twenty_approved_runtime_templates() -> None:
    service = WdvTemplateService(ManagedKRRepository(storage_path=KR_PATH))

    response = service.list_templates()

    assert response.contract_version == "wdv_backend_template_service_v1"
    assert response.template_count == 20
    assert response.knowledge_policy.approved_only is True
    assert response.knowledge_policy.candidate_records_used is False
    assert response.knowledge_policy.frontend_inference_allowed is False
    assert all(template.status == GovernanceStatus.APPROVED.value for template in response.templates)
    assert all(template.runtime_eligible for template in response.templates)
    keys = {template.template_key for template in response.templates}
    assert "open_hole_triple_combo" in keys
    assert "basic_triple_combo_openhole" not in keys


def test_service_returns_full_open_hole_triple_combo_contract() -> None:
    service = WdvTemplateService(ManagedKRRepository(storage_path=KR_PATH))

    envelope = service.get_template("open_hole_triple_combo")
    template = envelope.template

    assert template.template_key == "open_hole_triple_combo"
    assert template.template_label == "Open-Hole Triple Combo"
    assert template.workflow_context == "open_hole"
    assert template.selection_rule is not None
    assert template.selection_rule.required_families == ["gamma_ray", "resistivity"]
    assert [track.track_number for track in template.tracks] == sorted(
        track.track_number for track in template.tracks
    )
    assert {track.renderer_type for track in template.tracks} >= {"line_curve", "log_curve"}
    resistivity = next(track for track in template.tracks if track.track_key == "resistivity")
    assert resistivity.renderer_type == "log_curve"
    assert any(req.curve_family == "resistivity" for req in resistivity.requirements)
    assert any(scale.curve_family == "resistivity" for scale in template.scale_defaults)
    assert any(obj.object_type == "log_curve" for obj in template.track_object_types)


def test_reference_summary_reports_approved_kr_record_layer() -> None:
    service = WdvTemplateService(ManagedKRRepository(storage_path=KR_PATH))

    summary = service.reference_summary()

    assert summary.record_type_counts["reference_source"] == 4
    assert summary.record_type_counts["preview_template"] == 20
    assert summary.record_type_counts["preview_template_track"] == 91
    assert summary.record_type_counts["template_curve_family_requirement"] == 231
    assert summary.record_type_counts["template_scale_default"] == 22
    assert summary.record_type_counts["track_object_type"] == 11
    assert summary.record_type_counts["template_selection_rule"] == 20
    assert {source["source_file"] for source in summary.reference_sources} >= {
        "Curve_catalogue_UPDATED_CONTENT_KR.csv",
        "LAS_Standards_Staging_KR.docx",
        "standard_well_log_display_examples.pdf",
        "WDV_Preview_Template_KR_Reference.pdf",
    }


def test_api_routes_expose_approved_template_contracts() -> None:
    client = TestClient(app)

    listing = client.get("/api/wlv/wdv/templates")
    assert listing.status_code == 200
    listing_data = listing.json()
    assert listing_data["template_count"] == 20
    assert listing_data["knowledge_policy"]["candidate_records_used"] is False
    assert "preview_template" in listing_data["knowledge_policy"]["runtime_record_types"]

    detail = client.get("/api/wlv/wdv/templates/open_hole_triple_combo")
    assert detail.status_code == 200
    detail_data = detail.json()
    assert detail_data["template"]["template_key"] == "open_hole_triple_combo"
    assert detail_data["template"]["tracks"]
    assert detail_data["template"]["selection_rule"]["rule_id"] == "selection_rule_open_hole_triple_combo"

    missing = client.get("/api/wlv/wdv/templates/not_a_template")
    assert missing.status_code == 404
