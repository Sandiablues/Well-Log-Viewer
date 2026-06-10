from pathlib import Path

from backend.app.inventory.repository import ManagedWellInventoryRepository
from backend.app.inventory.service import ManagedWellInventoryService
from backend.app.source_intake.models import SourceIntakeRegisterRequest, SourceRepositoryCreateRequest
from backend.app.source_intake.service import WlvSourceIntakeService

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


def test_registered_candidate_state_is_returned_and_persisted_in_workbench(tmp_path: Path) -> None:
    root = tmp_path / "source"
    _write(root / "FORGE_21_31.las", LAS_WITHOUT_UWI)

    source = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    inventory = ManagedWellInventoryService(repository=ManagedWellInventoryRepository(tmp_path / "managed_wells.json"))

    repository = source.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    scan = source.scan_repository(repository.repository_id)
    candidate = scan.candidates[0]

    response = source.register_candidates(
        SourceIntakeRegisterRequest(candidate_ids=[candidate.source_file_id]),
        inventory_service=inventory,
    )

    assert response.registered_count == 1
    assert response.workbench is not None

    updated = next(item for item in response.workbench.candidates if item.source_file_id == candidate.source_file_id)
    assert updated.registration_status == "registered"
    assert updated.managed_well_id == response.results[0].managed_well_id
    assert updated.wmdp_state == "staged_in_wmdp"
    assert updated.wdv_state == "not_loaded"
    assert updated.registered_curve_count == 2
    assert updated.registered_product_count >= 1

    reloaded = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json").get_workbench()
    persisted = next(item for item in reloaded.candidates if item.source_file_id == candidate.source_file_id)
    assert persisted.registration_status == "registered"
    assert persisted.wmdp_state == "staged_in_wmdp"
    assert persisted.wdv_state == "not_loaded"
    assert persisted.registered_curve_count == 2
