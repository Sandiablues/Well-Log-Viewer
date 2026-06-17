from pathlib import Path

from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest,
    SourceIntakeRegisterRequest,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionDecision,
    SourceIntakeResolutionState,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import WlvSourceIntakeService

LAS_WITH_UWI = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. Forge 21-31 : Well name
UWI. 1234567890 : Unique well identifier
COMP. Ormat Nevada, Inc. : Company
FLD. Carson Field : Field
BLOCK. Carson Block : Block
~Curve
DEPT.FT : Depth
GR.GAPI : Gamma Ray
RHOB.G/C3 : Standard Resolution Formation Density
~ASCII
100.0 50.0 2.30
101.0 51.0 2.35
102.0 52.0 2.40
"""

LAS_WITHOUT_UWI = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. Forge 21-31 : Well name
COMP. Ormat Nevada, Inc. : Company
FLD. Carson Field : Field
BLOCK. Carson Block : Block
~Curve
DEPT.FT : Depth
GR.GAPI : Gamma Ray
~ASCII
100.0 50.0
101.0 51.0
102.0 52.0
"""

INVALID_LAS = """~Version
VERS. 2.0
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _services(tmp_path: Path):
    source = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    inventory = ManagedWellInventoryService(repository=ManagedWellInventoryRepository(tmp_path / "managed_wells.json"))
    return source, inventory


def _scan(tmp_path: Path, file_name: str, text: str):
    root = tmp_path / "source"
    _write(root / file_name, text)
    source, inventory = _services(tmp_path)
    repository = source.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    result = source.scan_repository(repository.repository_id)
    return source, inventory, result.candidates[0]


def _register(source: WlvSourceIntakeService, inventory: ManagedWellInventoryService, candidate_id: str):
    return source.register_candidates(
        SourceIntakeRegisterRequest(
            candidate_ids=[candidate_id],
            approval={"approved_by": "test", "approval_note": "unit-test approval"},
        ),
        inventory_service=inventory,
    )


def test_passing_las_candidate_registers_to_managed_inventory(tmp_path: Path) -> None:
    source, inventory, candidate = _scan(tmp_path, "FORGE_21_31.las", LAS_WITH_UWI)

    response = _register(source, inventory, candidate.source_file_id)

    assert response.registered_count == 1
    assert response.skipped_count == 0
    result = response.results[0]
    assert result.status == "registered"
    assert result.managed_well_id
    assert result.registered_curve_count == 2

    records = inventory.list_wells()
    assert len(records) == 1
    record = records[0]
    assert record.well_name == "Forge 21-31"
    assert record.metadata["uwi"] == "1234567890"
    assert record.source_references[0].source_id == candidate.source_file_id
    assert record.product_groups[0].items[0].curve_name == "GR"
    persisted = source.get_workbench().candidates[0]
    assert persisted.resolution_state == SourceIntakeResolutionState.REGISTERED
    assert persisted.resolution_history[-1].action == SourceIntakeResolutionAction.REGISTERED


def test_missing_uwi_candidate_registers_without_using_internal_well_id_as_uwi(tmp_path: Path) -> None:
    source, inventory, candidate = _scan(tmp_path, "FORGE_21_31.las", LAS_WITHOUT_UWI)
    source.resolve_candidates(
        SourceIntakeBulkResolutionRequest(
            decisions=[
                SourceIntakeResolutionDecision(
                    occurrence_id=candidate.occurrence_id,
                    action=SourceIntakeResolutionAction.WARNING_ACCEPTED,
                    actor="test",
                    reason="Missing UWI reviewed and accepted.",
                    accepted_warning_codes=["missing_uwi"],
                )
            ]
        )
    )

    response = _register(source, inventory, candidate.source_file_id)

    assert response.registered_count == 1
    record = inventory.list_wells()[0]
    assert record.well_name == "Forge 21-31"
    assert record.metadata["uwi"] is None
    assert record.metadata["uwi_missing"] is True
    assert record.well_id.startswith("wlv-intake-name-")
    assert record.metadata["uwi"] != record.well_id
    assert any("UWI/API was missing" in note for note in record.lifecycle_notes)


def test_failed_qaqc_candidate_is_blocked_from_registration(tmp_path: Path) -> None:
    source, inventory, candidate = _scan(tmp_path, "bad.las", INVALID_LAS)

    response = _register(source, inventory, candidate.source_file_id)

    assert response.registered_count == 0
    assert response.skipped_count == 1
    assert response.results[0].status == "blocked"
    assert "parser_status" in response.results[0].reason
    assert inventory.list_wells() == []


def test_unknown_non_log_candidate_is_blocked_from_registration(tmp_path: Path) -> None:
    source, inventory, candidate = _scan(tmp_path, "mystery.bin", "not a log")

    response = _register(source, inventory, candidate.source_file_id)

    assert response.registered_count == 0
    assert response.skipped_count == 1
    assert response.results[0].status == "blocked"
    assert "well_log_candidate" in response.results[0].reason
    assert inventory.list_wells() == []


def test_register_response_is_idempotent_and_updates_existing_record(tmp_path: Path) -> None:
    source, inventory, candidate = _scan(tmp_path, "FORGE_21_31.las", LAS_WITH_UWI)

    first = _register(source, inventory, candidate.source_file_id)
    second = _register(source, inventory, candidate.source_file_id)

    assert first.results[0].action == "created"
    assert second.results[0].action == "updated"
    assert first.results[0].managed_well_id == second.results[0].managed_well_id
    assert len(inventory.list_wells()) == 1


def test_registered_inventory_is_visible_through_inventory_service(tmp_path: Path) -> None:
    source, inventory, candidate = _scan(tmp_path, "FORGE_21_31.las", LAS_WITH_UWI)
    response = _register(source, inventory, candidate.source_file_id)

    managed_well_id = response.results[0].managed_well_id
    assert managed_well_id is not None
    detail = inventory.get_well(managed_well_id)

    assert detail.well_name == "Forge 21-31"
    assert detail.source_references[0].file_format == "LAS"
    assert sum(len(group.items) for group in detail.product_groups) == 2


def test_unresolved_warning_candidate_is_blocked_until_resolution(tmp_path: Path) -> None:
    source, inventory, candidate = _scan(tmp_path, "FORGE_21_31.las", LAS_WITHOUT_UWI)

    response = _register(source, inventory, candidate.source_file_id)

    assert response.registered_count == 0
    assert response.skipped_count == 1
    assert response.results[0].status == "blocked"
    assert "resolution state" in response.results[0].reason
    assert inventory.list_wells() == []


def test_occurrence_accounting_balances_after_registration(tmp_path: Path) -> None:
    source, inventory, candidate = _scan(tmp_path, "FORGE_21_31.las", LAS_WITH_UWI)
    before = source.get_occurrence_accounting()
    assert before.total_occurrences == 1
    assert before.ingestible_count == 1
    assert before.balanced is True

    response = _register(source, inventory, candidate.source_file_id)
    assert response.registered_count == 1

    after = source.get_occurrence_accounting()
    assert after.total_occurrences == 1
    assert after.registered_count == 1
    assert after.accounted_count == 1
    assert after.unaccounted_count == 0
    assert after.balanced is True
