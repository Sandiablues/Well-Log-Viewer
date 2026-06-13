from pathlib import Path

from backend.app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWdvState,
    ManagedWellRecord,
)
from backend.app.inventory.repository import ManagedWellInventoryRepository
from backend.app.inventory.service import ManagedWellInventoryService
from backend.app.wbv.models import WbvViewerState
from backend.app.wbv.service import WbvService


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
            ),
            ManagedProductGroup(
                group_key="supporting_documents",
                group_label="Supporting documents",
                items=[
                    ManagedProductGroupItem(
                        product_id=f"doc:{managed_well_id}",
                        display_name="Report.pdf",
                        curve_name="Report.pdf",
                        curve_type="PDF",
                        product_category="supporting_documents",
                        curve_family="Supporting Document",
                        source_kind=ManagedSourceKind.DOCUMENT.value,
                    )
                ],
            ),
        ],
    )


def test_wbv_session_returns_not_loaded_when_no_wdv_well_is_loaded(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = WbvService(repository=repository)

    session = service.get_session()

    assert session.contract_kind == "wbv_session"
    assert session.viewer == "WBV"
    assert session.viewer_state == WbvViewerState.NOT_LOADED
    assert session.active_managed_well_id is None
    assert session.available_layers.trajectory is False
    assert session.available_layers.loaded_curves is False
    assert session.warnings[0].code == "no_loaded_wdv_well"


def test_wbv_session_uses_backend_wdv_load_session_as_source_authority(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    inventory = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a", ["GR", "RT"]))

    inventory.load_managed_well_to_wdv("managed-well:a", product_ids=["GR"])
    session = WbvService(repository=repository).get_session()

    assert session.viewer_state == WbvViewerState.MISSING_SURVEY
    assert session.active_managed_well_id == "managed-well:a"
    assert session.source_session is not None
    assert session.source_session.contract_kind == "wdv_load_session"
    assert session.source_session.active_viewer_package_id is not None
    assert session.source_session.source_product_ids == ["GR"]
    assert session.available_layers.loaded_curves is True
    assert session.available_layers.trajectory is False
    assert any(warning.code == "missing_deviation_survey" for warning in session.warnings)


def test_wbv_viewer_package_does_not_fabricate_trajectory_without_survey(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    inventory = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a", ["GR", "RT"]))

    inventory.load_managed_well_to_wdv("managed-well:a", product_ids=["GR", "RT"])
    package = WbvService(repository=repository).get_viewer_package("managed-well:a")

    assert package.contract_kind == "wbv_viewer_package"
    assert package.viewer_state == WbvViewerState.MISSING_SURVEY
    assert package.trajectory.stations == []
    assert package.trajectory.render_points == []
    assert package.available_layers.trajectory is False
    assert package.available_layers.curve_attributes is True
    assert [track["product_id"] for track in package.available_attribute_tracks] == ["GR", "RT"]


def test_wbv_viewer_package_reports_unloaded_well_as_not_loaded(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    repository.upsert_record(_record("managed-well:a", ["GR"]))

    package = WbvService(repository=repository).get_viewer_package("managed-well:a")

    assert package.viewer_state == WbvViewerState.NOT_LOADED
    assert package.trajectory.render_points == []
    assert package.available_layers.loaded_curves is False
    assert package.warnings[0].code == "managed_well_not_loaded_to_wdv"


def test_wbv_viewer_package_can_surface_future_backend_owned_trajectory_package(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    inventory = ManagedWellInventoryService(repository=repository)
    record = _record("managed-well:a", ["GR"])
    record.metadata["wbv_trajectory_package"] = {
        "method": "minimum_curvature",
        "source": "deviation_survey",
        "stations": [{"md": 0.0, "inclination": 0.0, "azimuth": 0.0}],
        "render_points": [{"md": 0.0, "tvd": 0.0, "x": 0.0, "y": 0.0, "z": 0.0}],
    }
    repository.upsert_record(record)

    inventory.load_managed_well_to_wdv("managed-well:a", product_ids=["GR"])
    package = WbvService(repository=repository).get_viewer_package("managed-well:a")

    assert package.viewer_state == WbvViewerState.RELATIVE_ONLY
    assert package.available_layers.trajectory is True
    assert package.available_layers.survey_stations is True
    assert package.trajectory.method == "minimum_curvature"
    assert package.trajectory.render_points == [{"md": 0.0, "tvd": 0.0, "x": 0.0, "y": 0.0, "z": 0.0}]
