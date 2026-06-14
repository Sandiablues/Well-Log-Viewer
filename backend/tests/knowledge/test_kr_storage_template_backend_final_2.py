"""KR/WLV template backend final storage compatibility tests.

These tests guard the backend-owned KR contract needed before the WDV template
service can consume approved preview-template records.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.app.knowledge.governance import GovernanceStatus
from backend.app.knowledge.managed_models import GenericManagedRecord
from backend.app.knowledge.managed_repository import ManagedKRRepository
from backend.app.knowledge.managed_storage import ManagedStorage, serialize_record


PROJECT_ROOT = Path(__file__).resolve().parents[3]
KR_PATH = PROJECT_ROOT / "backend" / "data" / "knowledge" / "managed_knowledge.json"


def _iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def test_storage_loads_governed_generic_records_losslessly(tmp_path: Path) -> None:
    storage_path = tmp_path / "managed_knowledge.json"
    now = _iso()
    doc = {
        "storage_schema_version": "wlv-managed-kr-1",
        "kr_version": "kr-5",
        "updated_at": now,
        "records": [
            {
                "record_id": "wdv_template_open_hole_triple_combo",
                "record_type": "preview_template",
                "template_key": "open_hole_triple_combo",
                "template_label": "Open-Hole Triple Combo",
                "workflow_context": "open_hole",
                "status": "approved",
                "created_at": now,
                "reviewed_at": now,
                "approved_at": now,
                "production_eligible": True,
                "runtime_eligible": True,
                "preview_eligible": True,
                "auto_build_eligible": True,
                "rule_status": "approved",
                "evidence_refs": ["ev1"],
            }
        ],
        "evidence_records": [
            {
                "evidence_id": "ev1",
                "record_type": "evidence",
                "source_type": "document",
                "source_label": "WDV Preview Template KR Reference",
                "source_file": "WDV_Preview_Template_KR_Reference.pdf",
                "source_storage_path": "backend/data/knowledge/reference_sources/approved/example.pdf",
                "file_sha256": "abc123",
                "file_size_bytes": 123,
                "page_count": 4,
                "status": "approved",
                "reviewed_at": now,
                "approved_at": now,
                "created_at": now,
            }
        ],
    }
    storage_path.write_text(json.dumps(doc), encoding="utf-8")

    records, evidence = ManagedStorage(path=storage_path).load()

    template = records[0]
    assert isinstance(template, GenericManagedRecord)
    assert template.record_type == "preview_template"
    assert template.status is GovernanceStatus.APPROVED
    assert template.template_key == "open_hole_triple_combo"
    assert template.data["template_key"] == "open_hole_triple_combo"
    assert template.preview_eligible is True

    serialized = serialize_record(template)
    assert serialized["template_key"] == "open_hole_triple_combo"
    assert serialized["record_type"] == "preview_template"
    assert "extra_fields" not in serialized

    assert evidence[0].source_storage_path.endswith("example.pdf")
    assert evidence[0].file_sha256 == "abc123"
    assert not hasattr(evidence[0], "status")
    evidence_serialized = serialize_record(evidence[0])
    assert evidence_serialized["status"] == "approved"
    assert evidence_serialized["approved_at"] is not None


def test_project_repository_exposes_approved_template_layer_by_record_type() -> None:
    repo = ManagedKRRepository(storage_path=KR_PATH)

    preview_templates = repo.list_records(
        record_type="preview_template",
        status=GovernanceStatus.APPROVED,
    )
    tracks = repo.list_records(
        record_type="preview_template_track",
        status=GovernanceStatus.APPROVED,
    )
    requirements = repo.list_records(
        record_type="template_curve_family_requirement",
        status=GovernanceStatus.APPROVED,
    )
    scale_defaults = repo.list_records(
        record_type="template_scale_default",
        status=GovernanceStatus.APPROVED,
    )
    object_types = repo.list_records(
        record_type="track_object_type",
        status=GovernanceStatus.APPROVED,
    )

    assert len(preview_templates) == 20
    assert len(tracks) == 91
    assert len(requirements) == 231
    assert len(scale_defaults) == 22
    assert len(object_types) == 11
    assert any(
        getattr(r, "template_key", None) == "open_hole_triple_combo"
        for r in preview_templates
    )
