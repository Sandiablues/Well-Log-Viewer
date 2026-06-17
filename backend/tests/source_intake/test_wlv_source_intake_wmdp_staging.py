from pathlib import Path

from app.inventory.models import ManagedWdvState, ManagedWmdpState
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.source_intake.models import (
    SourceIntakeBulkResolutionRequest,
    SourceIntakeRegisterRequest,
    SourceIntakeResolutionAction,
    SourceIntakeResolutionDecision,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import WlvSourceIntakeService

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
RHOB.G/C3 : Standard Resolution Formation Density
~ASCII
100.0 50.0 2.30
101.0 51.0 2.35
102.0 52.0 2.40
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _register_las(tmp_path: Path):
    root = tmp_path / "source"
    _write(root / "FORGE_21_31.las", LAS_WITHOUT_UWI)
    source = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    inventory = ManagedWellInventoryService(repository=ManagedWellInventoryRepository(tmp_path / "managed_wells.json"))
    repository = source.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    scan = source.scan_repository(repository.repository_id)
    candidate = scan.candidates[0]
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
    response = source.register_candidates(
        SourceIntakeRegisterRequest(
            candidate_ids=[candidate.source_file_id],
            approval={"approved_by": "test", "approval_note": "stage-to-wmdp contract test"},
        ),
        inventory_service=inventory,
    )
    assert response.registered_count == 1
    return candidate, inventory, response


def test_registered_candidate_is_staged_in_wmdp_but_not_loaded_to_wdv(tmp_path: Path) -> None:
    candidate, inventory, response = _register_las(tmp_path)
    managed_well_id = response.results[0].managed_well_id
    assert managed_well_id is not None

    record = inventory.get_well(managed_well_id)

    assert record.wmdp_state == ManagedWmdpState.STAGED_IN_WMDP
    assert record.wdv_state == ManagedWdvState.NOT_LOADED
    assert record.wmdp_available is True
    assert record.source_intake_candidate_id == candidate.source_file_id
    assert record.metadata["wmdp_state"] == "staged_in_wmdp"
    assert record.metadata["wdv_state"] == "not_loaded"
    assert record.metadata["wmdp_available"] is True


def test_registered_products_retain_source_intake_provenance_and_wmdp_state(tmp_path: Path) -> None:
    candidate, inventory, response = _register_las(tmp_path)
    managed_well_id = response.results[0].managed_well_id
    assert managed_well_id is not None

    record = inventory.get_well(managed_well_id)
    items = [item for group in record.product_groups for item in group.items]

    assert items
    first = items[0]
    assert first.wmdp_state == ManagedWmdpState.STAGED_IN_WMDP
    assert first.wdv_state == ManagedWdvState.NOT_LOADED
    assert first.source_intake_candidate_id == candidate.source_file_id
    assert first.source_id == candidate.source_file_id
    assert first.provenance["source_intake_candidate_id"] == candidate.source_file_id
    assert first.provenance["repository_id"] == candidate.repository_id
    assert first.provenance["checksum"] == candidate.checksum


def test_missing_uwi_remains_missing_in_wmdp_staged_record(tmp_path: Path) -> None:
    _candidate, inventory, response = _register_las(tmp_path)
    managed_well_id = response.results[0].managed_well_id
    assert managed_well_id is not None

    record = inventory.get_well(managed_well_id)

    assert record.metadata["uwi"] is None
    assert record.metadata["uwi_missing"] is True
    assert record.metadata["uwi"] != record.well_id
    assert record.well_id.startswith("wlv-intake-name-")


def test_inventory_list_exposes_wmdp_staged_contract(tmp_path: Path) -> None:
    _candidate, inventory, _response = _register_las(tmp_path)

    records = inventory.list_wells()

    assert len(records) == 1
    record = records[0]
    assert record.wmdp_state == ManagedWmdpState.STAGED_IN_WMDP
    assert record.wdv_state == ManagedWdvState.NOT_LOADED
    assert record.product_groups[0].items[0].wmdp_state == ManagedWmdpState.STAGED_IN_WMDP
    assert record.product_groups[0].items[0].wdv_state == ManagedWdvState.NOT_LOADED
