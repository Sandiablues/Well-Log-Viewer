
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.source_intake.models import SourceRepositoryCreateRequest
from app.source_intake.service import WlvSourceIntakeService


LAS = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. Forge 21-31 : Well name
UWI. 1234567890 : Unique well identifier
~Curve
DEPT.FT : Depth
GR.GAPI : Gamma Ray
~ASCII
100.0 50.0
101.0 51.0
102.0 52.0
"""


def test_accounting_api_reports_every_occurrence(monkeypatch, tmp_path: Path) -> None:
    from app.source_intake import router as router_module

    root = tmp_path / "source"
    root.mkdir()
    (root / "well.las").write_text(LAS)
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True)
    )
    service.scan_repository(repository.repository_id)
    monkeypatch.setattr(router_module, "_service", service)

    response = TestClient(app).get("/api/wlv/source-intake/accounting")

    assert response.status_code == 200
    body = response.json()
    assert body["total_occurrences"] == 1
    assert body["accounted_count"] == 1
    assert body["unaccounted_count"] == 0
    assert body["balanced"] is True
