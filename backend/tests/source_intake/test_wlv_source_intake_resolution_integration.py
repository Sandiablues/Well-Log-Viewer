
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionDecision,
    SourceIntakeResolutionState,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import WlvSourceIntakeService


LAS_WARNING = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. WELL : Generic well name
~Curve
DEPT.FT : Depth
GR. : Gamma Ray
~ASCII
100.0 50.0
101.0 51.0
102.0 52.0
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_scan_assigns_occurrence_identity_and_duplicate_group(tmp_path: Path) -> None:
    root = tmp_path / "source"
    _write(root / "a" / "same.las", LAS_WARNING)
    _write(root / "b" / "same.las", LAS_WARNING)
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True)
    )

    result = service.scan_repository(repository.repository_id)

    assert len(result.candidates) == 2
    first, second = result.candidates
    assert first.source_file_id == first.occurrence_id
    assert second.source_file_id == second.occurrence_id
    assert first.occurrence_id != second.occurrence_id
    assert first.content_fingerprint == second.content_fingerprint
    assert first.duplicate_group_id == second.duplicate_group_id
    assert {
        first.resolution_state,
        second.resolution_state,
    } == {
        SourceIntakeResolutionState.UNRESOLVED,
        SourceIntakeResolutionState.DUPLICATE,
    }

    reloaded = service.get_workbench().candidates
    assert [row.model_dump(mode="json") for row in reloaded] == [
        row.model_dump(mode="json") for row in result.candidates
    ]


def test_resolution_decision_is_persisted_and_audited(tmp_path: Path) -> None:
    root = tmp_path / "source"
    _write(root / "warning.las", LAS_WARNING)
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True)
    )
    candidate = service.scan_repository(repository.repository_id).candidates[0]

    response = service.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.METADATA_OVERRIDE,
                    actor="reviewer",
                    reason="Resolved generic well identity.",
                    resolved_values={"well_name": "Forge 21-31"},
                )
            ]
        )
    )

    assert response.resolved_count == 1
    persisted = service.get_workbench().candidates[0]
    assert persisted.resolution_state == SourceIntakeResolutionState.RESOLVED
    assert persisted.resolved_metadata.well_name.value == "Forge 21-31"
    assert persisted.resolution_history[-1].actor == "reviewer"
    assert persisted.resolution_history[-1].reason == "Resolved generic well identity."


def test_resolve_api_rejects_unknown_occurrence(monkeypatch, tmp_path: Path) -> None:
    from app.source_intake import router as router_module

    monkeypatch.setattr(
        router_module,
        "_service",
        WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json"),
    )
    client = TestClient(app)
    response = client.post(
        "/api/wlv/source-intake/resolve",
        json={
            "decisions": [
                {
                    "occurrence_id": "occ:missing",
                    "action": "warning_accepted",
                    "actor": "reviewer",
                    "reason": "Reviewed.",
                    "accepted_warning_codes": ["optional_warning"],
                }
            ]
        },
    )
    assert response.status_code == 400
    assert "Unknown occurrence_id" in response.json()["detail"]
