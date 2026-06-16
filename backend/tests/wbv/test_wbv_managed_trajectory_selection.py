from pathlib import Path

import pytest

from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService
from app.wbv.models import WbvViewerState
from app.wbv.service import WbvService


def _trajectory_package(md_max: float) -> dict[str, object]:
    return {
        "method": "minimum_curvature",
        "source": "deviation_survey",
        "coordinate_mode": "relative",
        "stations": [
            {"md": 0.0, "inclination": 0.0, "azimuth": 0.0},
            {"md": md_max, "inclination": 0.0, "azimuth": 0.0},
        ],
        "render_points": [
            {"md": 0.0, "tvd": 0.0, "x": 0.0, "y": 0.0, "z": 0.0},
            {"md": md_max, "tvd": md_max, "x": 0.0, "y": 0.0, "z": -md_max},
        ],
        "bounding_box": {"md": {"min": 0.0, "max": md_max}, "tvd": {"min": 0.0, "max": md_max}},
    }


def _record(managed_well_id: str) -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id=managed_well_id,
        well_id=managed_well_id.replace("managed-well:", ""),
        well_name="Trajectory Test Well",
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
                        product_id="GR",
                        display_name="GR",
                        curve_name="GR",
                        curve_type="Gamma Ray",
                        curve_description="Gamma Ray",
                        curve_unit="API",
                        product_category="open_hole_logs",
                        curve_family="Gamma Ray",
                        review_required=False,
                        source_kind=ManagedSourceKind.LAS.value,
                    )
                ],
            )
        ],
        metadata={
            "wbv_trajectory_records": [
                {
                    "trajectory_id": "traj-prelim",
                    "trajectory_name": "Preliminary deviation survey",
                    "trajectory_type": "deviation_survey",
                    "status": "approved",
                    "wbv_eligible": True,
                    "is_active": False,
                    "is_canonical": False,
                    "source_label": "prelim.csv",
                    "station_count": 2,
                    "md_min": 0.0,
                    "md_max": 1000.0,
                    "coordinate_mode": "relative",
                    "trajectory_package": _trajectory_package(1000.0),
                },
                {
                    "trajectory_id": "traj-final",
                    "trajectory_name": "Final corrected deviation survey",
                    "trajectory_type": "deviation_survey",
                    "status": "approved",
                    "wbv_eligible": True,
                    "is_active": False,
                    "is_canonical": True,
                    "source_label": "final.csv",
                    "station_count": 2,
                    "md_min": 0.0,
                    "md_max": 1200.0,
                    "coordinate_mode": "relative",
                    "trajectory_package": _trajectory_package(1200.0),
                },
                {
                    "trajectory_id": "traj-review",
                    "trajectory_name": "Report extracted survey requiring review",
                    "trajectory_type": "deviation_survey",
                    "status": "review_required",
                    "wbv_eligible": False,
                    "source_label": "report.pdf",
                },
            ]
        },
    )


def test_multiple_approved_trajectories_require_active_selection(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    repository.upsert_record(_record("managed-well:a"))

    payload = WbvService(repository=repository).list_trajectories("managed-well:a")

    assert payload.contract_kind == "wbv_trajectory_list"
    assert payload.active_trajectory_id == "traj-final"
    assert payload.geometry_status == "active_trajectory_selected"
    assert payload.wbv_ready is True
    assert [trajectory.trajectory_id for trajectory in payload.trajectories] == ["traj-prelim", "traj-final", "traj-review"]


def test_set_active_trajectory_updates_backend_owned_package(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    inventory = ManagedWellInventoryService(repository=repository)
    repository.upsert_record(_record("managed-well:a"))
    inventory.load_managed_well_to_wdv("managed-well:a", product_ids=["GR"])

    service = WbvService(repository=repository)
    response = service.set_active_trajectory("managed-well:a", "traj-prelim", requested_by="test")
    package = service.get_viewer_package("managed-well:a")
    persisted = repository.get_record("managed-well:a")

    assert response.active_trajectory_id == "traj-prelim"
    assert response.wbv_ready is True
    assert persisted.metadata["active_trajectory_id"] == "traj-prelim"
    assert package.viewer_state == WbvViewerState.RELATIVE_ONLY
    assert package.trajectory.render_points[-1]["md"] == 1000.0


def test_review_required_trajectory_cannot_be_set_active(tmp_path: Path) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    repository.upsert_record(_record("managed-well:a"))

    with pytest.raises(ValueError, match="Only approved/synthetic-demo"):
        WbvService(repository=repository).set_active_trajectory("managed-well:a", "traj-review")
