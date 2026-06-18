from __future__ import annotations

from pathlib import Path

from app.inventory.models import ManagedWellRecord
from app.inventory.repository import ManagedWellInventoryRepository
from app.wbv.models import (
    WbvManagedTrajectoryRecord,
    WbvSetActiveTrajectoryRequest,
)
from app.wbv.service import WbvService


TRAJECTORY_UID = "01976c6d-4aa7-7e43-b118-d7d30e773e81"


def _trajectory() -> dict[str, object]:
    return {
        "trajectory_id": "traj-legacy",
        "managed_trajectory_uid": TRAJECTORY_UID,
        "trajectory_name": "Canonical trajectory",
        "trajectory_type": "deviation_survey",
        "status": "approved",
        "wbv_eligible": True,
        "is_active": False,
        "coordinate_mode": "relative",
        "trajectory_package": {
            "method": "minimum_curvature",
            "source": "deviation_survey",
            "stations": [
                {"md": 0.0, "inclination": 0.0, "azimuth": 0.0},
                {"md": 100.0, "inclination": 0.0, "azimuth": 0.0},
            ],
            "render_points": [
                {"md": 0.0, "tvd": 0.0, "x": 0.0, "y": 0.0, "z": 0.0},
                {"md": 100.0, "tvd": 100.0, "x": 0.0, "y": 0.0, "z": -100.0},
            ],
        },
    }


def _service(tmp_path: Path) -> WbvService:
    repository = ManagedWellInventoryRepository(
        storage_path=tmp_path / "managed_wells.json"
    )
    repository.upsert_record(
        ManagedWellRecord(
            managed_well_id="managed-well:uid9c2",
            well_id="well-uid9c2",
            well_name="UID-9C2 Well",
            metadata={"wbv_trajectory_records": [_trajectory()]},
        )
    )
    return WbvService(repository=repository)


def test_request_prefers_managed_trajectory_uid() -> None:
    request = WbvSetActiveTrajectoryRequest(
        managed_trajectory_uid=TRAJECTORY_UID,
        trajectory_uid=TRAJECTORY_UID,
        trajectory_id="traj-legacy",
    )
    assert request.canonical_or_legacy_reference == TRAJECTORY_UID


def test_previous_canonical_and_legacy_aliases_remain_accepted() -> None:
    assert (
        WbvSetActiveTrajectoryRequest(
            trajectory_uid=TRAJECTORY_UID
        ).canonical_or_legacy_reference
        == TRAJECTORY_UID
    )
    assert (
        WbvSetActiveTrajectoryRequest(
            trajectory_id="traj-legacy"
        ).canonical_or_legacy_reference
        == "traj-legacy"
    )


def test_service_resolves_canonical_uid_before_legacy_id(tmp_path: Path) -> None:
    service = _service(tmp_path)
    response = service.set_active_trajectory(
        "managed-well:uid9c2",
        TRAJECTORY_UID,
        requested_by="uid9c2-test",
    )

    assert response.active_trajectory_uid == TRAJECTORY_UID
    assert response.active_trajectory_id == "traj-legacy"


def test_service_still_accepts_legacy_trajectory_id(tmp_path: Path) -> None:
    service = _service(tmp_path)
    response = service.set_active_trajectory(
        "managed-well:uid9c2",
        "traj-legacy",
    )
    assert response.active_trajectory_uid == TRAJECTORY_UID


def test_resolver_prefers_canonical_uuid_when_legacy_value_collides() -> None:
    canonical = WbvManagedTrajectoryRecord(
        trajectory_id="canonical-record",
        managed_trajectory_uid=TRAJECTORY_UID,
        trajectory_name="Canonical",
        status="approved",
        wbv_eligible=True,
    )
    legacy_collision = WbvManagedTrajectoryRecord(
        trajectory_id=TRAJECTORY_UID,
        trajectory_name="Legacy collision",
        status="approved",
        wbv_eligible=True,
    )

    selected = WbvService._resolve_trajectory_reference(
        [legacy_collision, canonical],
        TRAJECTORY_UID,
    )
    assert selected is canonical
