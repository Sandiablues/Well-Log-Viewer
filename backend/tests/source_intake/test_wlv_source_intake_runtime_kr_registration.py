from pathlib import Path

from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.source_intake.models import SourceIntakeRegisterRequest, SourceRepositoryCreateRequest
from app.source_intake.service import WlvSourceIntakeService

LAS_WITH_RUNTIME_KR_CURVES = """~Version
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
DCAL.IN : Differential Caliper
AF10.OHMM : Array Induction Four Foot Resistivity A10
WTEP.DEGF : Well Temperature
~ASCII
100.0 8.5 12.0 180.0
101.0 8.6 13.0 181.0
102.0 8.7 14.0 182.0
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _scan(tmp_path: Path, file_name: str, text: str):
    root = tmp_path / "source"
    _write(root / file_name, text)
    source = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    inventory = ManagedWellInventoryService(repository=ManagedWellInventoryRepository(tmp_path / "managed_wells.json"))
    repository = source.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    result = source.scan_repository(repository.repository_id)
    return source, inventory, result.candidates[0]


def _register(source: WlvSourceIntakeService, inventory: ManagedWellInventoryService, candidate_id: str):
    return source.register_candidates(
        SourceIntakeRegisterRequest(
            candidate_ids=[candidate_id],
            approval={"approved_by": "test", "approval_note": "runtime-kr-registration"},
        ),
        inventory_service=inventory,
    )


def _items_by_curve(record):
    return {
        item.curve_name: item
        for group in record.product_groups
        for item in group.items
    }


def _group_for_curve(record, curve_name: str):
    for group in record.product_groups:
        for item in group.items:
            if item.curve_name == curve_name:
                return group
    raise AssertionError(f"curve not found: {curve_name}")


def test_source_intake_registration_uses_runtime_kr_before_fallback_classifier(tmp_path: Path) -> None:
    source, inventory, candidate = _scan(tmp_path, "FORGE_21_31_RUNTIME_KR.las", LAS_WITH_RUNTIME_KR_CURVES)

    response = _register(source, inventory, candidate.source_file_id)

    assert response.registered_count == 1
    record = inventory.list_wells()[0]
    items = _items_by_curve(record)

    dcal = items["DCAL"]
    assert _group_for_curve(record, "DCAL").group_key == "open_hole_logs"
    assert dcal.product_category == "open_hole_logs"
    assert dcal.product_subgroup_key == "borehole_geometry_imaging"
    assert dcal.product_subgroup_label == "Borehole Geometry / Imaging"
    assert dcal.curve_family == "caliper"
    assert dcal.classification_source == "runtime_alias"
    assert dcal.classification_confidence == "high"
    assert any("Runtime KR resolved mnemonic DCAL" in reason for reason in dcal.classification_reasons)

    af10 = items["AF10"]
    assert _group_for_curve(record, "AF10").group_key == "open_hole_logs"
    assert af10.product_category == "open_hole_logs"
    assert af10.product_subgroup_key == "resistivity"
    assert af10.product_subgroup_label == "Resistivity"
    assert af10.curve_family == "resistivity"
    assert af10.classification_source == "runtime_alias"
    assert af10.classification_confidence == "high"

    # KR-MDP-REFRESH-MERGE-1-TEST-HOTFIX:
    # WTEP is now present in runtime KR and should classify as temperature,
    # not fall through to Other.
    wtep = items["WTEP"]
    assert _group_for_curve(record, "WTEP").group_key == "pressure_production_fluid_data"
    assert wtep.product_category == "pressure_production_fluid_data"
    assert wtep.product_subgroup_key == "temperature"
    assert wtep.product_subgroup_label == "Temperature"
    assert wtep.classification_source == "runtime_alias"
    assert wtep.classification_confidence == "high"
    # KR-MDP-REFRESH-MERGE-1-WTEP-REASON-HOTFIX:
    # WTEP now resolves through runtime KR.
    assert any("Runtime KR resolved mnemonic WTEP" in reason for reason in wtep.classification_reasons)
