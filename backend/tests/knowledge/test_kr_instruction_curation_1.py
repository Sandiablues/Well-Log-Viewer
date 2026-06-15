
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _seed(path: Path) -> None:
    data = {
        "records": [
            {
                "record_id": "approved_curve_cali",
                "record_type": "managed_instruction",
                "status": "approved",
                "instruction_type": "curve_instruction",
                "instruction_subject": "CALI",
                "instruction_application_area": "WDV curve classification",
                "curve_family": "caliper",
                "alias": "CALI",
                "instruction_must_do": "Treat CALI as measured caliper.",
                "instruction_must_not_do": "Do not treat CALI as bit size.",
                "runtime_eligible": True,
                "production_eligible": True,
                "evidence_refs": ["ev_seed"],
                "governance_history": [],
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "approved_by": "seed",
                "change_reason": "seed",
            }
        ],
        "evidence_records": [
            {
                "evidence_id": "ev_seed",
                "source_type": "manual_seed",
                "source_label": "Seed evidence",
                "source_reference": "seed",
                "confidence": 1.0,
                "notes": "seed",
            }
        ],
    }
    path.write_text(json.dumps(data))


def test_create_candidate_instruction_is_not_runtime_truth(tmp_path: Path, monkeypatch) -> None:
    store = tmp_path / "managed_knowledge.json"
    _seed(store)
    monkeypatch.setenv("WLV_KR_MANAGED_KNOWLEDGE_PATH", str(store))

    response = client.post(
        "/api/wlv/knowledge/instructions/candidates",
        json={
            "instruction_type": "curve_instruction",
            "subject": "BS",
            "application_area": "WDV template selection",
            "curve_family": "bit_size",
            "alias": "BS",
            "must_do": "Use BS as a borehole reference overlay.",
            "must_not_do": "Do not use BS as a caliper substitute.",
            "evidence_note": "Manual expert correction.",
        },
    )
    assert response.status_code == 200
    created = response.json()["instruction"]
    assert created["status"] == "candidate"
    assert created["runtime_eligible"] is False
    assert created["production_eligible"] is False

    approved_only = client.get("/api/wlv/knowledge/instructions", params={"q": "BS"})
    assert approved_only.status_code == 200
    assert approved_only.json()["returned_count"] == 0

    review_list = client.get("/api/wlv/knowledge/instructions", params={"approved_only": False, "status": "candidate", "q": "BS"})
    assert review_list.status_code == 200
    assert review_list.json()["returned_count"] == 1


def test_approve_candidate_promotes_truth_and_supersedes_old_record(tmp_path: Path, monkeypatch) -> None:
    store = tmp_path / "managed_knowledge.json"
    _seed(store)
    monkeypatch.setenv("WLV_KR_MANAGED_KNOWLEDGE_PATH", str(store))

    create = client.post(
        "/api/wlv/knowledge/instructions/candidates",
        json={
            "instruction_type": "curve_instruction",
            "subject": "CALI correction",
            "application_area": "WDV curve classification",
            "curve_family": "caliper",
            "alias": "CALI",
            "must_do": "Treat CALI as measured caliper.",
            "must_not_do": "Do not treat CALI as bit size or generic borehole reference.",
            "supersedes_record_id": "approved_curve_cali",
            "change_reason": "Tighten approved caliper instruction.",
        },
    )
    assert create.status_code == 200
    candidate_id = create.json()["instruction"]["instruction_id"]

    approve = client.post(f"/api/wlv/knowledge/instructions/candidates/{candidate_id}/approve", json={"reviewer": "Bwana", "reason": "Approved correction."})
    assert approve.status_code == 200
    approved = approve.json()["instruction"]
    assert approved["status"] == "approved"
    assert approved["runtime_eligible"] is True
    assert approve.json()["superseded_instruction_id"] == "approved_curve_cali"

    data = json.loads(store.read_text())
    old = next(r for r in data["records"] if r["record_id"] == "approved_curve_cali")
    assert old["status"] == "superseded"
    assert old["runtime_eligible"] is False


def test_reject_and_deprecate_remove_records_from_runtime_truth(tmp_path: Path, monkeypatch) -> None:
    store = tmp_path / "managed_knowledge.json"
    _seed(store)
    monkeypatch.setenv("WLV_KR_MANAGED_KNOWLEDGE_PATH", str(store))

    create = client.post(
        "/api/wlv/knowledge/instructions/candidates",
        json={"subject": "Bad candidate", "must_do": "Do something", "must_not_do": "Do not do something"},
    )
    candidate_id = create.json()["instruction"]["instruction_id"]
    reject = client.post(f"/api/wlv/knowledge/instructions/candidates/{candidate_id}/reject", json={"reviewer": "Bwana", "reason": "Not correct."})
    assert reject.status_code == 200
    assert reject.json()["instruction"]["status"] == "rejected"

    deprecate = client.post("/api/wlv/knowledge/instructions/approved_curve_cali/deprecate", json={"reviewer": "Bwana", "reason": "Obsolete."})
    assert deprecate.status_code == 200
    assert deprecate.json()["instruction"]["status"] == "deprecated"

    approved_only = client.get("/api/wlv/knowledge/instructions", params={"q": "CALI"})
    assert approved_only.status_code == 200
    assert approved_only.json()["returned_count"] == 0
