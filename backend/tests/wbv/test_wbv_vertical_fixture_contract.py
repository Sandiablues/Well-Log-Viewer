import json
from pathlib import Path

from backend.app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from backend.app.inventory.repository import ManagedWellInventoryRepository
from backend.app.inventory.service import ManagedWellInventoryService
from backend.app.wbv.models import WbvCoordinateMode, WbvViewerState
from backend.app.wbv.service import WbvService


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "forge_21_31_downlog_vertical_wbv_trajectory_package.json"


def _trajectory_fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _record(managed_well_id: str, product_ids: list[str]) -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id=managed_well_id,
        well_id=managed_well_id.replace("managed-well:", ""),
        well_name=managed_well_id,
        source_references=[
            ManagedSourceReference(
                source_id=f"source:{managed_well_id}",
                source_kind=ManagedSourceKind.LAS,
                display_name=f"{managed_well_id}.las",
            )
        ],
        product_groups=[
            ManagedProductGroup(
                group_key="open_hole_logs",
                group_label="Open hole logs",
                items=[
                    ManagedProductGroupItem(
                        product_id=product_id,
                        display_name=product_id,
                        curve_name=product_id,
                        curve_type="Gamma Ray",
                        curve_description="Gamma Ray",
                        curve_unit="API",
                        product_category="open_hole_logs",
                        curve_family="Gamma Ray",
                        review_required=False,
                        source_kind=ManagedSourceKind.LAS.value,
                    )
                    for product_id in product_ids
                ],
            )
        ],
    )


def test_downlog_vertical_fixture_surfaces_as_available_vertical_wbv_package(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    inventory = ManagedWellInventoryService(repository=repository)
    record = _record("managed-well:forge-21-31", ["GR"])
    record.metadata["wbv_trajectory_package"] = _trajectory_fixture()
    repository.upsert_record(record)

    inventory.load_managed_well_to_wdv("managed-well:forge-21-31", product_ids=["GR"])
    package = WbvService(repository=repository).get_viewer_package("managed-well:forge-21-31")

    assert package.viewer_state == WbvViewerState.AVAILABLE_VERTICAL
    assert package.coordinate_mode == WbvCoordinateMode.RELATIVE
    assert package.available_layers.trajectory is True
    assert package.available_layers.depth_labels is True
    assert package.available_layers.loaded_curves is True
    assert package.trajectory.trajectory_class == "vertical_trajectory_candidate"
    assert package.trajectory.viewer_state == "available_vertical"
    assert package.trajectory.source_station_count == 4317
    assert package.trajectory.station_count == len(package.trajectory.render_points)
    assert len(package.trajectory.render_points) >= 100
    assert package.bounding_box["md"]["min"] == package.trajectory.render_points[0]["md"]
    assert package.bounding_box["md"]["max"] >= package.trajectory.render_points[-1]["md"]
    assert any(warning.code == "vertical_trajectory_candidate" for warning in package.warnings)
    assert any(warning.code == "duplicate_depth_rows_collapsed" for warning in package.warnings)
    assert not any(warning.code == "missing_deviation_survey" for warning in package.warnings)


def test_downlog_vertical_fixture_surfaces_through_active_wbv_session(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    inventory = ManagedWellInventoryService(repository=repository)
    record = _record("managed-well:forge-21-31", ["GR"])
    record.metadata["wbv_trajectory_package"] = _trajectory_fixture()
    repository.upsert_record(record)

    inventory.load_managed_well_to_wdv("managed-well:forge-21-31", product_ids=["GR"])
    session = WbvService(repository=repository).get_session()

    assert session.viewer_state == WbvViewerState.AVAILABLE_VERTICAL
    assert session.coordinate_mode == WbvCoordinateMode.RELATIVE
    assert session.available_layers.trajectory is True
    assert session.available_layers.loaded_curves is True
    assert any(warning.code == "vertical_trajectory_candidate" for warning in session.warnings)
