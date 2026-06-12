from pathlib import Path

from backend.app.inventory.repository import ManagedWellInventoryRepository
from backend.app.inventory.service import ManagedWellInventoryService
from backend.app.source_intake.models import SourceIntakeRegisterRequest, SourceRepositoryCreateRequest
from backend.app.source_intake.service import WlvSourceIntakeService

LAS_STRONG_FORGE = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 100.0 : Start depth
STOP.FT 102.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. Forge 21-31 : Well name
UWI. 2700190539 : Unique well identifier
COMP. Ormat Nevada, Inc. : Company
FLD. Carson Field : Field
~Curve
DEPT.FT : Depth
GR.GAPI : Gamma Ray
DTCO.US/F : Sonic Compressional
~ASCII
100.0 50.0 80.0
101.0 51.0 81.0
102.0 52.0 82.0
"""

LAS_GENERIC_FORGE = """~Version
VERS. 2.0 : CWLS LOG ASCII STANDARD
~Well
STRT.FT 200.0 : Start depth
STOP.FT 202.0 : Stop depth
STEP.FT 1.0 : Step value
NULL. -999.25 : Null value
WELL. WELL : Well name
UWI. UNIQUE WELL ID : Unique well identifier
COMP. COMPANY : Company
FLD. FIELD : Field
~Curve
DEPT.FT : Depth
RHOB.G/C3 : Density
NPHI.V/V : Neutron Porosity
GR.GAPI : Gamma Ray
~ASCII
200.0 2.30 0.22 55.0
201.0 2.31 0.21 56.0
202.0 2.32 0.20 57.0
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _services(tmp_path: Path):
    source = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    inventory = ManagedWellInventoryService(repository=ManagedWellInventoryRepository(tmp_path / "managed_wells.json"))
    return source, inventory


def test_identity_gate_assigns_generic_las_to_single_package_well_before_registration(tmp_path: Path) -> None:
    root = tmp_path / "WLV_Data"
    _write(root / "21-31_WirelineLogs" / "Sonic Scanner" / "Ormat_Forge 21-31_Sonic.las", LAS_STRONG_FORGE)
    _write(root / "21-31_WirelineLogs" / "Triple Combo" / "DM9E_Ormat_Carson_Forge-21-31_TCOM.las", LAS_GENERIC_FORGE)

    source, inventory = _services(tmp_path)
    repository = source.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    scan = source.scan_repository(repository.repository_id)

    candidates = {candidate.file_name: candidate for candidate in scan.candidates}
    weak = candidates["DM9E_Ormat_Carson_Forge-21-31_TCOM.las"]
    assert weak.resolved_metadata is not None
    assert weak.resolved_metadata.well_name.value == "Forge 21-31"
    assert weak.resolved_metadata.uwi.value == "2700190539"
    assert weak.review_required is True
    assert any("assigned to the package well identity" in warning for warning in weak.warnings)

    response = source.register_candidates(
        SourceIntakeRegisterRequest(candidate_ids=[candidate.source_file_id for candidate in scan.candidates]),
        inventory_service=inventory,
    )

    assert response.registered_count == 2
    records = inventory.list_wells()
    assert len(records) == 1
    record = records[0]
    assert record.well_name == "Forge 21-31"
    assert record.metadata["uwi"] == "2700190539"
    assert len(record.source_references) == 2
    assert sum(len(group.items) for group in record.product_groups) == 5


def test_generic_las_without_package_identity_is_blocked_from_registration(tmp_path: Path) -> None:
    root = tmp_path / "WLV_Data"
    _write(root / "Loose" / "generic.las", LAS_GENERIC_FORGE)

    source, inventory = _services(tmp_path)
    repository = source.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    scan = source.scan_repository(repository.repository_id)
    candidate = scan.candidates[0]

    response = source.register_candidates(
        SourceIntakeRegisterRequest(candidate_ids=[candidate.source_file_id]),
        inventory_service=inventory,
    )

    assert response.registered_count == 0
    assert response.skipped_count == 1
    assert response.results[0].status == "blocked"
    assert "no resolved well name" in (response.results[0].reason or "").lower() or "generic" in (response.results[0].reason or "").lower()
    assert inventory.list_wells() == []


def test_source_intake_excludes_macos_hidden_system_files(tmp_path: Path) -> None:
    root = tmp_path / "WLV_Data"
    _write(root / ".DS_Store", "macOS junk")
    _write(root / "21-31_WirelineLogs" / ".DS_Store", "macOS junk")
    _write(root / "21-31_WirelineLogs" / "Sonic" / "Ormat_Forge 21-31_Sonic.las", LAS_STRONG_FORGE)

    source, _inventory = _services(tmp_path)
    repository = source.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    scan = source.scan_repository(repository.repository_id)

    assert [candidate.file_name for candidate in scan.candidates] == ["Ormat_Forge 21-31_Sonic.las"]
    assert scan.repository.file_count == 1
    assert scan.repository.unknown_file_count == 0
