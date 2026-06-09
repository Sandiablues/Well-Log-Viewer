from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.inventory import api_inventory
from backend.app.inventory.models import (
    ManagedInventoryLifecycleState,
    ManagedInventorySnapshot,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
    ViewerPackageReference,
)
from backend.app.inventory.repository import ManagedWellInventoryRepository
from backend.app.inventory.service import ManagedWellInventoryService
from backend.app.main import app


def _install_temp_inventory(tmp_path: Path) -> ManagedWellInventoryRepository:
    repository = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    api_inventory._service = ManagedWellInventoryService(repository=repository)
    return repository


def test_register_seed_sets_viewer_ready_lifecycle_and_is_idempotent(tmp_path: Path) -> None:
    _install_temp_inventory(tmp_path)
    client = TestClient(app)

    first = client.post("/api/wlv/inventory/wells/register-seed")
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["action"] == "created"
    assert first_payload["record"]["status"] == "viewer_ready"
    assert first_payload["record"]["lifecycle_state"] == "viewer_ready"

    second = client.post("/api/wlv/inventory/wells/register-seed")
    assert second.status_code == 200
    assert second.json()["action"] == "updated"

    status = client.get("/api/wlv/inventory/status")
    assert status.status_code == 200
    assert status.json()["lifecycle_counts"] == {"viewer_ready": 1}


def test_inventory_validate_endpoint_reports_clean_seed_inventory(tmp_path: Path) -> None:
    _install_temp_inventory(tmp_path)
    client = TestClient(app)

    client.post("/api/wlv/inventory/wells/register-seed")
    response = client.get("/api/wlv/inventory/validate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error_count"] == 0
    assert payload["warning_count"] == 0
    assert payload["managed_well_count"] == 1
    assert payload["lifecycle_counts"] == {"viewer_ready": 1}


def test_inventory_validate_reports_invalid_records_without_mutating_store(tmp_path: Path) -> None:
    repository = _install_temp_inventory(tmp_path)
    client = TestClient(app)

    invalid = ManagedWellRecord(
        managed_well_id="managed-well:bad",
        well_id="bad-well",
        well_name="Bad Well",
        top_depth=100.0,
        base_depth=50.0,
        status=ManagedInventoryLifecycleState.VIEWER_READY,
        lifecycle_state=ManagedInventoryLifecycleState.VIEWER_READY,
        source_references=[],
        viewer_packages=[],
    )
    repository.write_snapshot(ManagedInventorySnapshot(records=[invalid]))

    response = client.get("/api/wlv/inventory/validate")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    codes = {issue["code"] for issue in payload["issues"]}
    assert "invalid_depth_range" in codes
    assert "viewer_ready_without_package" in codes
    assert "missing_source_reference" in codes

    reread = repository.get_record("managed-well:bad")
    assert reread.top_depth == 100.0
    assert reread.base_depth == 50.0


def test_inventory_reload_stability_and_duplicate_detection(tmp_path: Path) -> None:
    storage_path = tmp_path / "managed_wells.json"
    repository = ManagedWellInventoryRepository(storage_path)

    source = ManagedSourceReference(
        source_id="source:dup:seed-las",
        source_kind=ManagedSourceKind.SEED,
        display_name="duplicate seed source",
        file_format="LAS",
    )
    package = ViewerPackageReference(
        viewer_package_id="viewer-package:dup",
        viewer_package_version="well_multitrack_v1",
        dataset_id="dataset-dup",
        representation_id="representation-dup",
        well_id="dup-well",
        endpoint="/api/wlv/wells/dup-well/viewer-package",
    )
    record = ManagedWellRecord(
        managed_well_id="managed-well:dup",
        well_id="dup-well",
        well_name="Duplicate Well",
        status=ManagedInventoryLifecycleState.VIEWER_READY,
        lifecycle_state=ManagedInventoryLifecycleState.VIEWER_READY,
        source_references=[source],
        viewer_packages=[package],
    )
    repository.write_snapshot(ManagedInventorySnapshot(records=[record, record]))

    reloaded_repository = ManagedWellInventoryRepository(storage_path)
    api_inventory._service = ManagedWellInventoryService(repository=reloaded_repository)
    client = TestClient(app)

    response = client.get("/api/wlv/inventory/validate")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    codes = {issue["code"] for issue in payload["issues"]}
    assert "duplicate_managed_well_id" in codes
    assert "duplicate_well_id" in codes
    assert "duplicate_viewer_package_id" in codes
    assert payload["managed_well_count"] == 2


def test_inventory_maintenance_status_is_non_destructive(tmp_path: Path) -> None:
    _install_temp_inventory(tmp_path)
    client = TestClient(app)

    client.post("/api/wlv/inventory/wells/register-seed")
    response = client.get("/api/wlv/inventory/maintenance/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["destructive_actions_enabled"] is False
    assert payload["managed_well_count"] == 1
    assert payload["validate_endpoint"] == "/api/wlv/inventory/validate"
