from pathlib import Path

from fastapi.testclient import TestClient

from app.inventory import api_inventory
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.main import app
from app.source_intake import router as source_intake_router
from app.source_intake.service import WlvSourceIntakeService


LAS_TEMPLATE = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. {well_name} : Well name
{uwi_line}COMP. Test Operator : Company
FLD. Test Field : Field
~Curve
DEPT.FT : Depth
{curve}.UNIT : Test curve
~ASCII
100.0 1.0
101.0 2.0
102.0 3.0
"""


def _write_las(
    path: Path,
    *,
    well_name: str,
    curve: str,
    uwi: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        LAS_TEMPLATE.format(
            well_name=well_name,
            curve=curve,
            uwi_line=(
                f"UWI. {uwi} : Unique well identifier\n"
                if uwi
                else ""
            ),
        )
    )


def _install_temp_services(tmp_path: Path) -> None:
    source_service = WlvSourceIntakeService(
        storage_path=tmp_path / "source_intake.json"
    )
    inventory_service = ManagedWellInventoryService(
        repository=ManagedWellInventoryRepository(
            tmp_path / "managed_wells.json"
        )
    )

    source_intake_router._service = source_service
    source_intake_router._inventory_service = inventory_service
    api_inventory._service = inventory_service


def _candidate_by_name(client: TestClient, file_name: str) -> dict:
    response = client.get("/api/wlv/source-intake/workbench")
    assert response.status_code == 200
    candidates = response.json()["candidates"]
    return next(
        item for item in candidates
        if item["file_name"] == file_name
    )


def _register(
    client: TestClient,
    candidate_id: str,
) -> dict:
    response = client.post(
        "/api/wlv/source-intake/register",
        json={
            "candidate_ids": [candidate_id],
            "approval": {
                "approved_by": "runtime-api-test",
                "approval_note": "Block H runtime validation",
            },
        },
    )
    assert response.status_code == 200
    return response.json()


def test_runtime_http_human_decision_lifecycle(tmp_path: Path) -> None:
    _install_temp_services(tmp_path)
    client = TestClient(app)

    source_root = tmp_path / "source"

    _write_las(
        source_root / "base.las",
        well_name="Base Well",
        curve="GR",
        uwi="BASE-001",
    )
    _write_las(
        source_root / "existing-target.las",
        well_name="Different Source Name",
        curve="CALI",
    )
    _write_las(
        source_root / "new-well.las",
        well_name="WELL",
        curve="RHOB",
    )
    _write_las(
        source_root / "clear.las",
        well_name="WELL",
        curve="NPHI",
    )
    _write_las(
        source_root / "exclude.las",
        well_name="Excluded Source",
        curve="DT",
    )

    create_repository = client.post(
        "/api/wlv/source-intake/repositories",
        json={
            "root_path": str(source_root),
            "name": "runtime-api-source",
            "include_subfolders": True,
        },
    )
    assert create_repository.status_code == 200
    repository = create_repository.json()

    scan = client.post(
        f"/api/wlv/source-intake/repositories/"
        f"{repository['repository_id']}/scan",
    )
    assert scan.status_code == 200
    assert scan.json()["file_count"] == 5

    workbench = client.get("/api/wlv/source-intake/workbench")
    assert workbench.status_code == 200
    assert len(workbench.json()["candidates"]) == 5

    empty_inventory = client.get("/api/wlv/inventory/wells")
    assert empty_inventory.status_code == 200
    assert empty_inventory.json() == []

    base = _candidate_by_name(client, "base.las")
    base_registration = _register(
        client,
        base["source_file_id"],
    )
    assert base_registration["registered_count"] == 1
    target_managed_well_id = (
        base_registration["results"][0]["managed_well_id"]
    )
    assert target_managed_well_id

    inventory_after_base = client.get("/api/wlv/inventory/wells")
    assert inventory_after_base.status_code == 200
    assert len(inventory_after_base.json()) == 1

    existing = _candidate_by_name(
        client,
        "existing-target.las",
    )
    assign_existing = client.post(
        "/api/wlv/source-intake/resolve",
        json={
            "decisions": [
                {
                    "occurrence_id": existing["occurrence_id"],
                    "action": "well_assigned",
                    "actor": "runtime-api-test",
                    "reason": "Assign to selected existing well.",
                    "assignment_mode": "existing_well",
                    "target_managed_well_id": (
                        target_managed_well_id
                    ),
                }
            ]
        },
    )
    assert assign_existing.status_code == 200
    assert assign_existing.json()["resolved_count"] == 1

    refreshed_existing = _candidate_by_name(
        client,
        "existing-target.las",
    )
    assert (
        refreshed_existing["current_decision"]["decision"]
        == "assign"
    )
    assert (
        refreshed_existing["current_decision"]
        ["assignment_target"]
        == target_managed_well_id
    )

    existing_registration = _register(
        client,
        refreshed_existing["source_file_id"],
    )
    assert existing_registration["registered_count"] == 1
    assert (
        existing_registration["results"][0]["managed_well_id"]
        == target_managed_well_id
    )

    new_candidate = _candidate_by_name(
        client,
        "new-well.las",
    )
    create_new = client.post(
        "/api/wlv/source-intake/resolve",
        json={
            "decisions": [
                {
                    "occurrence_id": new_candidate["occurrence_id"],
                    "action": "well_assigned",
                    "actor": "runtime-api-test",
                    "reason": "Create confirmed new well.",
                    "assignment_mode": "new_well",
                    "new_well_values": {
                        "well_name": "Confirmed New Well",
                        "uwi": "NEW-002",
                        "operator": "Confirmed Operator",
                        "field": "Confirmed Field",
                    },
                }
            ]
        },
    )
    assert create_new.status_code == 200
    assert create_new.json()["resolved_count"] == 1

    refreshed_new = _candidate_by_name(
        client,
        "new-well.las",
    )
    assert (
        refreshed_new["resolved_metadata"]["well_name"]["value"]
        == "Confirmed New Well"
    )

    new_registration = _register(
        client,
        refreshed_new["source_file_id"],
    )
    assert new_registration["registered_count"] == 1
    assert (
        new_registration["results"][0]["managed_well_id"]
        != target_managed_well_id
    )

    clear_candidate = _candidate_by_name(
        client,
        "clear.las",
    )
    temporary_assignment = client.post(
        "/api/wlv/source-intake/resolve",
        json={
            "decisions": [
                {
                    "occurrence_id": clear_candidate["occurrence_id"],
                    "action": "well_assigned",
                    "actor": "runtime-api-test",
                    "reason": "Temporary assignment.",
                    "assignment_mode": "new_well",
                    "new_well_values": {
                        "well_name": "Temporary Well",
                    },
                }
            ]
        },
    )
    assert temporary_assignment.status_code == 200

    clear_decision = client.post(
        "/api/wlv/source-intake/resolve",
        json={
            "decisions": [
                {
                    "occurrence_id": clear_candidate["occurrence_id"],
                    "action": "reopened",
                    "actor": "runtime-api-test",
                    "reason": "Leave unresolved.",
                }
            ]
        },
    )
    assert clear_decision.status_code == 200

    refreshed_clear = _candidate_by_name(
        client,
        "clear.las",
    )
    assert (
        refreshed_clear["current_decision"]["decision"]
        == "clear_decision"
    )
    assert refreshed_clear["readiness_state"] == "review_required"

    clear_registration = _register(
        client,
        refreshed_clear["source_file_id"],
    )
    assert clear_registration["registered_count"] == 0
    assert clear_registration["skipped_count"] == 1

    exclude_candidate = _candidate_by_name(
        client,
        "exclude.las",
    )
    exclude = client.post(
        "/api/wlv/source-intake/resolve",
        json={
            "decisions": [
                {
                    "occurrence_id": exclude_candidate["occurrence_id"],
                    "action": "excluded",
                    "actor": "runtime-api-test",
                    "reason": "Not valid for this intake.",
                }
            ]
        },
    )
    assert exclude.status_code == 200
    assert exclude.json()["resolved_count"] == 1

    refreshed_exclude = _candidate_by_name(
        client,
        "exclude.las",
    )
    assert refreshed_exclude["readiness_state"] == "excluded"
    assert (
        refreshed_exclude["current_decision"]["decision"]
        == "exclude"
    )

    exclude_registration = _register(
        client,
        refreshed_exclude["source_file_id"],
    )
    assert exclude_registration["registered_count"] == 0
    assert exclude_registration["skipped_count"] == 1

    final_inventory = client.get("/api/wlv/inventory/wells")
    assert final_inventory.status_code == 200
    records = final_inventory.json()
    assert len(records) == 2

    base_record = next(
        record
        for record in records
        if record["managed_well_id"]
        == target_managed_well_id
    )
    assert len(base_record["source_references"]) == 2

    new_record = next(
        record
        for record in records
        if record["managed_well_id"]
        != target_managed_well_id
    )
    assert new_record["well_name"] == "Confirmed New Well"
    assert new_record["metadata"]["uwi"] == "NEW-002"

    final_workbench = client.get(
        "/api/wlv/source-intake/workbench"
    )
    assert final_workbench.status_code == 200
    candidates = final_workbench.json()["candidates"]

    registered_names = {
        item["file_name"]
        for item in candidates
        if item["registration_status"] == "registered"
    }
    assert registered_names == {
        "base.las",
        "existing-target.las",
        "new-well.las",
    }

    unresolved = next(
        item for item in candidates
        if item["file_name"] == "clear.las"
    )
    excluded = next(
        item for item in candidates
        if item["file_name"] == "exclude.las"
    )

    assert unresolved["readiness_state"] == "review_required"
    assert excluded["readiness_state"] == "excluded"
