from pathlib import Path

from fastapi.testclient import TestClient

from app.ingestion.las_adapter import LasSourceAdapter
from app.ingestion.models import SourceRegistrationRequest
from app.ingestion.service import WellLogSourceIngestionService
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.main import app

client = TestClient(app)


SAMPLE_LAS = """~Version
VERS. 2.0 : CWLS LAS version
WRAP. NO : One line per depth
~Well
STRT.FT 5300.0 : Start depth
STOP.FT 5302.0 : Stop depth
STEP.FT 1.0 : Step
NULL. -999.25 : Null value
WELL. Forge 21-31 : Well name
UWI. 2700190539 : API/UWI
FLD. FORGE : Field
COMP. Utah FORGE : Operator
~Curve
DEPT.FT : Measured depth
GR.API : Gamma Ray
RHOB.G/C3 : Bulk Density
NPHI.V/V : Neutron Porosity
~ASCII
5300.0 82.1 2.51 0.12
5301.0 84.3 2.49 0.13
5302.0 85.0 2.48 0.14
"""


LAS_WITH_QAQC_WARNINGS = """~Version
VERS. 2.0 : CWLS LAS version
WRAP. NO : One line per depth
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step
~Curve
DEPTH.FT : Measured depth
GR. : Gamma Ray
GR.API : Duplicate Gamma Ray
~ASCII
100.0 80.1 81.2
101.0 82.3 83.4
102.0 84.5 85.6
"""


def _write_las(tmp_path: Path, content: str, name: str = "Forge_21_31.las") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_las_adapter_returns_evidence_and_qaqc_summary(tmp_path: Path) -> None:
    package = LasSourceAdapter().parse_path(_write_las(tmp_path, SAMPLE_LAS))

    assert package.qaqc_summary.ok is True
    assert package.qaqc_summary.source_fingerprint_available is True
    assert package.qaqc_summary.depth_range_available is True
    assert package.qaqc_summary.curve_inventory_available is True
    assert package.qaqc_summary.evidence_count >= 6
    assert {item.evidence_kind.value for item in package.evidence} >= {
        "source_fingerprint",
        "metadata_header",
        "curve_inventory",
        "depth_samples",
        "null_value",
    }
    assert any(item.field_path == "source_file.checksum" for item in package.evidence)
    assert any(item.code == "source_fingerprint_available" for item in package.qaqc_findings)


def test_las_adapter_flags_missing_units_duplicate_curves_and_missing_null(tmp_path: Path) -> None:
    package = LasSourceAdapter().parse_path(_write_las(tmp_path, LAS_WITH_QAQC_WARNINGS, "warning_case.las"))
    codes = {finding.code for finding in package.qaqc_findings}

    assert package.qaqc_summary.ok is False
    assert "missing_well_name" in codes
    assert "missing_null_value" in codes
    assert "missing_curve_units" in codes
    assert "duplicate_curve_mnemonics" in codes
    assert package.qaqc_summary.error_count >= 1
    assert package.qaqc_summary.warning_count >= 3


def test_las_registration_persists_ingestion_evidence_to_inventory(tmp_path: Path) -> None:
    path = _write_las(tmp_path, SAMPLE_LAS)
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "managed_wells.json")
    inventory_service = ManagedWellInventoryService(repository=repository)
    service = WellLogSourceIngestionService(inventory_service=inventory_service)

    response = service.register_source(SourceRegistrationRequest(original_path=str(path), register_to_inventory=True))

    assert response.ok is True
    assert response.qaqc_summary.source_fingerprint_available is True
    assert response.evidence
    assert response.managed_record is not None
    metadata = response.managed_record["metadata"]
    assert metadata["source_fingerprint"]
    assert metadata["ingestion_evidence"]
    assert metadata["ingestion_qaqc_summary"]["source_fingerprint_available"] is True
    assert inventory_service.validate_inventory().ok is True


def test_register_source_endpoint_returns_evidence_and_qaqc_summary(tmp_path: Path) -> None:
    path = _write_las(tmp_path, SAMPLE_LAS)
    inventory_path = tmp_path / "api_managed_wells.json"

    from app.ingestion import api_ingestion

    api_ingestion._service = WellLogSourceIngestionService(
        inventory_service=ManagedWellInventoryService(
            repository=ManagedWellInventoryRepository(storage_path=inventory_path)
        )
    )

    response = client.post(
        "/api/wlv/ingestion/sources/register",
        json={"original_path": str(path), "register_to_inventory": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence"]
    assert payload["qaqc_summary"]["source_fingerprint_available"] is True
    assert payload["normalized_package"]["evidence"]
    assert payload["managed_record"]["metadata"]["ingestion_evidence"]
