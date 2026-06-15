from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_instruction_summary_exposes_approved_truth_inventory() -> None:
    response = client.get("/api/wlv/knowledge/instructions/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "kr_managed_instruction_service"
    assert data["contract_version"] == "kr_managed_instructions_v1"
    assert data["runtime_eligible_count"] > 0
    assert data["production_eligible_count"] > 0
    assert data["record_type_counts"].get("preview_template", 0) >= 20
    assert data["instruction_type_counts"].get("template_instruction", 0) >= 20


def test_instruction_list_is_approved_only_and_searchable() -> None:
    response = client.get("/api/wlv/knowledge/instructions", params={"q": "caliper", "limit": 25})
    assert response.status_code == 200
    data = response.json()
    assert data["approved_only"] is True
    assert data["candidate_records_used"] is False
    assert data["deprecated_records_used"] is False
    assert data["returned_count"] > 0
    assert all(item["status"] == "approved" for item in data["instructions"])
    assert any("caliper" in item["must_do"].lower() or "caliper" in item["subject"].lower() for item in data["instructions"])


def test_instruction_detail_includes_evidence_and_raw_record() -> None:
    list_response = client.get("/api/wlv/knowledge/instructions", params={"record_type": "preview_template", "limit": 1})
    assert list_response.status_code == 200
    item = list_response.json()["instructions"][0]
    detail_response = client.get(f"/api/wlv/knowledge/instructions/{item['instruction_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["instruction"]
    assert detail["instruction_id"] == item["instruction_id"]
    assert detail["raw_record"]["record_type"] == "preview_template"
    assert detail["evidence_ref_count"] >= 1
    assert len(detail["evidence"]) >= 1


def test_template_decision_view_groups_template_track_selection_instructions() -> None:
    response = client.get("/api/wlv/knowledge/instructions/templates/open_hole_triple_combo/decision")
    assert response.status_code == 200
    data = response.json()
    assert data["template_key"] == "open_hole_triple_combo"
    assert data["instruction_count"] > 0
    assert len(data["template_instructions"]) >= 1
    assert len(data["track_instructions"]) >= 1
    assert len(data["selection_instructions"]) >= 1
    families = {item.get("curve_family") for item in data["selection_instructions"]}
    assert "gamma_ray" in families
    assert "resistivity" in families
    assert len(data["evidence"]) >= 1
