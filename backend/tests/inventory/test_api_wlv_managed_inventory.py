from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.inventory.repository import ManagedWellInventoryRepository
from backend.app.inventory.service import ManagedWellInventoryService
from backend.app.inventory import api_inventory
from backend.app.main import app


def _install_temp_inventory(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(tmp_path / "managed_wells.json")
    api_inventory._service = ManagedWellInventoryService(repository=repository)


def test_inventory_health_and_empty_status(tmp_path: Path) -> None:
    _install_temp_inventory(tmp_path)
    client = TestClient(app)

    health = client.get("/api/wlv/inventory/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert health.json()["service"] == "wlv-managed-inventory"

    status = client.get("/api/wlv/inventory/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["ok"] is True
    assert payload["managed_well_count"] == 0
    assert payload["viewer_package_count"] == 0


def test_register_seed_well_is_idempotent_and_persistent(tmp_path: Path) -> None:
    _install_temp_inventory(tmp_path)
    client = TestClient(app)

    first = client.post("/api/wlv/inventory/wells/register-seed")
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["ok"] is True
    assert first_payload["action"] == "created"
    assert first_payload["record"]["managed_well_id"] == "managed-well:forge-21-31"
    assert first_payload["record"]["well_name"] == "Forge 21-31"
    assert len(first_payload["record"]["source_references"]) == 1
    assert len(first_payload["record"]["viewer_packages"]) == 1

    second = client.post("/api/wlv/inventory/wells/register-seed")
    assert second.status_code == 200
    assert second.json()["action"] == "updated"

    wells = client.get("/api/wlv/inventory/wells")
    assert wells.status_code == 200
    assert len(wells.json()) == 1

    detail = client.get("/api/wlv/inventory/wells/managed-well:forge-21-31")
    assert detail.status_code == 200
    assert detail.json()["well_id"] == "forge-21-31"

    packages = client.get("/api/wlv/inventory/viewer-packages")
    assert packages.status_code == 200
    assert len(packages.json()) == 1
    assert packages.json()[0]["endpoint"] == "/api/wlv/wells/forge-21-31/viewer-package"


def test_missing_managed_well_returns_404(tmp_path: Path) -> None:
    _install_temp_inventory(tmp_path)
    client = TestClient(app)

    response = client.get("/api/wlv/inventory/wells/not-present")
    assert response.status_code == 404

def test_managed_well_viewer_package_endpoint_returns_contract(tmp_path: Path) -> None:
    _install_temp_inventory(tmp_path)
    client = TestClient(app)

    register = client.post("/api/wlv/inventory/wells/register-seed")
    assert register.status_code == 200

    response = client.get("/api/wlv/inventory/wells/managed-well:forge-21-31/viewer-package")
    assert response.status_code == 200
    payload = response.json()
    assert payload["viewer_package_version"] == "well_multitrack_v1"
    assert payload["well_id"] == "forge-21-31"
    assert payload["dataset_id"] == "seed-dataset-forge-21-31"
    assert len(payload["tracks"]) >= 1


def test_managed_well_viewer_package_endpoint_returns_404_when_missing(tmp_path: Path) -> None:
    _install_temp_inventory(tmp_path)
    client = TestClient(app)

    response = client.get("/api/wlv/inventory/wells/not-present/viewer-package")
    assert response.status_code == 404



def test_managed_well_product_groups_are_backend_owned(tmp_path: Path) -> None:
    _install_temp_inventory(tmp_path)
    client = TestClient(app)

    register = client.post("/api/wlv/inventory/wells/register-seed")
    assert register.status_code == 200
    record = register.json()["record"]
    assert record.get("uwi") is None
    groups = record["product_groups"]
    assert [group["group_key"] for group in groups] == [
        "open_hole_logs",
        "cased_hole_logs",
        "rasters_images",
        "other",
        "supporting_documents",
    ]
    open_hole = groups[0]
    assert open_hole["group_label"] == "Open hole logs"
    assert open_hole["collapsed_by_default"] is True
    assert len(open_hole["items"]) >= 10
    first_curve = open_hole["items"][0]
    assert {
        "product_id",
        "display_name",
        "curve_name",
        "curve_type",
        "run_date",
        "run_interval",
        "run_number",
        "qa_flag",
        "selectable",
        "source_kind",
        "source_id",
        "viewer_package_id",
    }.issubset(first_curve.keys())
    assert "block" in record
    assert record["operator"] == "Ormat Nevada, Inc."
    assert first_curve["curve_name"] == "GR"
    assert first_curve["curve_type"] == "Gamma ray"
    assert first_curve["run_date"] == "—"
    assert first_curve["run_interval"] == "300.5–6076 ft"
    assert first_curve["run_number"] == "ONE"
    assert first_curve["qa_flag"] == "Passed"

    detail = client.get("/api/wlv/inventory/wells/managed-well:forge-21-31")
    assert detail.status_code == 200
    assert detail.json()["product_groups"][0]["items"][0]["curve_name"] == "GR"
