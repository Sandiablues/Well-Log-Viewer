from pathlib import Path

from backend.app.inventory.curve_sample_service import CurveSampleService
from backend.app.inventory.models import ManagedProductGroup, ManagedProductGroupItem, ManagedWellRecord
from backend.app.inventory.repository import ManagedWellInventoryRepository


def _las_file(path: Path) -> Path:
    path.write_text(
        """~Version
VERS. 2.0 : LAS version
~Well
STRT.FT 100.0 : Start
STOP.FT 104.0 : Stop
STEP.FT 1.0 : Step
NULL. -999.25 : Null
~Curve
DEPT.FT : Depth
GR.GAPI : Gamma Ray
RXO.OHMM : Flushed Zone Resistivity
~Ascii
100.0 50.0 1.0
101.0 51.0 2.0
102.0 52.0 -999.25
103.0 53.0 4.0
104.0 54.0 5.0
""",
        encoding="utf-8",
    )
    return path


def test_curve_sample_service_returns_product_backed_las_samples(tmp_path: Path) -> None:
    las_path = _las_file(tmp_path / "sample.las")
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    record = ManagedWellRecord(
        managed_well_id="managed-well:test",
        well_id="test",
        well_name="Test Well",
        product_groups=[
            ManagedProductGroup(
                group_key="open_hole_logs",
                group_label="Open hole logs",
                items=[
                    ManagedProductGroupItem(
                        product_id="product:rxo",
                        display_name="RXO",
                        curve_name="RXO",
                        curve_type="Flushed Zone Resistivity",
                        curve_unit="OHMM",
                        product_category="open_hole_logs",
                        curve_family="Resistivity",
                        run_interval="100–104 ft",
                        provenance={"original_path": str(las_path)},
                    )
                ],
            )
        ],
    )
    repository.upsert_record(record)

    response = CurveSampleService(repository=repository).get_curve_samples("managed-well:test", "product:rxo")

    assert response["contract_kind"] == "wdv_product_curve_samples"
    assert response["product_id"] == "product:rxo"
    assert response["mnemonic"] == "RXO"
    assert response["depth_unit"] == "ft"
    assert response["value_unit"] == "OHMM"
    assert response["depth_min"] == 100.0
    assert response["depth_max"] == 104.0
    assert response["sample_count"] == 4
    assert response["samples"] == [[100.0, 1.0], [101.0, 2.0], [103.0, 4.0], [104.0, 5.0]]
