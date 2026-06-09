from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.ingestion.las_adapter import LasSourceAdapter
from backend.app.ingestion.service import WellLogSourceIngestionService
from backend.app.inventory.repository import ManagedWellInventoryRepository
from backend.app.inventory.service import ManagedWellInventoryService
from backend.app.main import app

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


def _sample_las_file(tmp_path: Path) -> Path:
    path = tmp_path / "Forge_21_31.las"
    path.write_text(SAMPLE_LAS, encoding="utf-8")
    return path


def test_las_adapter_extracts_metadata_curve_inventory_and_depth_range(tmp_path: Path) -> None:
    path = _sample_las_file(tmp_path)
    package = LasSourceAdapter().parse_path(path)

    assert package.source_file.source_format == "las"
    assert package.well_id == "2700190539"
    assert package.well_name == "Forge 21-31"
    assert package.metadata["depth_unit"] == "ft"
    assert package.metadata["top_depth"] == 5300.0
    assert package.metadata["base_depth"] == 5302.0
    assert package.metadata["sample_count"] == 3
    assert package.metadata["null_value"] == -999.25
    assert [curve.mnemonic for curve in package.curve_channels] == ["GR", "RHOB", "NPHI"]
    assert all(curve.sample_count == 3 for curve in package.curve_channels)
    assert package.source_file.checksum


def test_las_registration_is_idempotent_and_registers_available_inventory_record(tmp_path: Path) -> None:
    path = _sample_las_file(tmp_path)
    inventory_path = tmp_path / "managed_wells.json"
    repository = ManagedWellInventoryRepository(storage_path=inventory_path)
    inventory_service = ManagedWellInventoryService(repository=repository)
    service = WellLogSourceIngestionService(inventory_service=inventory_service)

    from backend.app.ingestion.models import SourceRegistrationRequest

    first = service.register_source(SourceRegistrationRequest(original_path=str(path), register_to_inventory=True))
    second = service.register_source(SourceRegistrationRequest(original_path=str(path), register_to_inventory=True))

    assert first.ok is True
    assert first.action == "created"
    assert second.ok is True
    assert second.action == "updated"
    assert first.managed_record is not None
    assert first.managed_record["lifecycle_state"] == "available"
    assert first.managed_record["viewer_packages"] == []
    assert first.managed_record["source_references"][0]["source_kind"] == "las"
    assert inventory_service.status().managed_well_count == 1
    assert inventory_service.validate_inventory().ok is True


def test_register_source_endpoint_accepts_las_path(tmp_path: Path, monkeypatch) -> None:
    path = _sample_las_file(tmp_path)
    inventory_path = tmp_path / "api_managed_wells.json"

    from backend.app.ingestion import api_ingestion

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
    assert payload["ok"] is True
    assert payload["detected_format"] == "las"
    assert payload["normalized_package"]["well_name"] == "Forge 21-31"
    assert payload["managed_record"]["lifecycle_state"] == "available"
    assert payload["normalized_package"]["metadata"]["curve_count"] == 3


def test_register_source_rejects_non_las_for_now(tmp_path: Path) -> None:
    path = tmp_path / "image_log.tif"
    path.write_bytes(b"not a tiff parser block")
    response = client.post(
        "/api/wlv/ingestion/sources/register",
        json={"original_path": str(path), "register_to_inventory": True},
    )
    assert response.status_code == 400
    assert "implemented for LAS" in response.json()["detail"]
