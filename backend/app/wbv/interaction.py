"""Backend-owned WBV point/interval selection and WDV AOI transfer."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from app.inventory.models import utc_now_iso
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.wdv_workspace import WdvWorkspaceService


class WbvPickedPoint(BaseModel):
    md: float
    tvd: float | None = None
    tvdss: float | None = None
    inclination: float | None = None
    azimuth: float | None = None
    dogleg_severity: float | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None


class WbvSavedInterval(BaseModel):
    interval_id: str
    managed_well_id: str
    trajectory_id: str | None = None
    trajectory_revision_uid: str | None = None
    start: WbvPickedPoint
    end: WbvPickedPoint
    top_md: float
    base_md: float
    depth_unit: str
    created_at: str
    updated_at: str


class WbvInteractionState(BaseModel):
    contract_kind: str = "wbv_interaction_state"
    contract_version: str = "wbv_interaction_state_v1"
    managed_well_id: str
    selection_mode: Literal["none", "point", "interval"] = "none"
    selected_point_visible: bool = False
    interval_visible: bool = False
    selected_point: WbvPickedPoint | None = None
    interval_draft_start: WbvPickedPoint | None = None
    saved_interval: WbvSavedInterval | None = None
    updated_at: str


class WbvSelectionModeRequest(BaseModel):
    mode: Literal["none", "point", "interval"]


class WbvPointSelectionRequest(BaseModel):
    point: WbvPickedPoint


class WbvIntervalPickRequest(BaseModel):
    point: WbvPickedPoint


class WbvAoiTransferResult(BaseModel):
    contract_kind: str = "wbv_to_wdv_aoi"
    contract_version: str = "wbv_to_wdv_aoi_v1"
    command_status: Literal["applied"] = "applied"
    workspace_id: str
    workspace_revision: int
    managed_well_id: str
    interval_id: str
    top_md: float
    base_md: float
    depth_unit: str
    source_viewer: Literal["WBV"] = "WBV"
    applied_at: str


class WbvInteractionService:
    METADATA_KEY = "wbv_interaction_state_v1"

    def __init__(
        self,
        repository: ManagedWellInventoryRepository | None = None,
        trajectory_package_provider: Callable[[str], Any] | None = None,
    ) -> None:
        self.repository = repository or ManagedWellInventoryRepository()
        self.trajectory_package_provider = trajectory_package_provider

    def get(self, managed_well_id: str) -> WbvInteractionState:
        record = self.repository.get_record(managed_well_id)
        raw = record.metadata.get(self.METADATA_KEY, {}) if isinstance(record.metadata, dict) else {}
        if isinstance(raw, dict) and raw:
            return WbvInteractionState.model_validate({"managed_well_id": managed_well_id, **raw})
        return WbvInteractionState(managed_well_id=managed_well_id, updated_at=utc_now_iso())

    def set_mode(self, managed_well_id: str, mode: str) -> WbvInteractionState:
        state = self.get(managed_well_id)
        update = {
            "selection_mode": mode,
            "selected_point_visible": mode == "point",
            "interval_visible": mode == "interval",
            "updated_at": utc_now_iso(),
        }
        return self._save(managed_well_id, state.model_copy(update=update))

    def select_point(self, managed_well_id: str, point: WbvPickedPoint) -> WbvInteractionState:
        state = self.get(managed_well_id)
        if state.selection_mode != "point" or not state.selected_point_visible:
            raise ValueError("Selected Point mode must be enabled before selecting a point.")
        self._validate_md(managed_well_id, point.md)
        return self._save(managed_well_id, state.model_copy(update={"selected_point": point, "updated_at": utc_now_iso()}))

    def pick_interval(self, managed_well_id: str, point: WbvPickedPoint) -> WbvInteractionState:
        state = self.get(managed_well_id)
        if state.selection_mode != "interval" or not state.interval_visible:
            raise ValueError("Interval Selection mode must be enabled before selecting interval endpoints.")
        self._validate_md(managed_well_id, point.md)
        now = utc_now_iso()
        if state.interval_draft_start is None:
            return self._save(managed_well_id, state.model_copy(update={"interval_draft_start": point, "updated_at": now}))
        start = state.interval_draft_start
        record = self.repository.get_record(managed_well_id)
        active = self._active_trajectory(record)
        top_md, base_md = sorted((start.md, point.md))
        existing_created = state.saved_interval.created_at if state.saved_interval else now
        interval = WbvSavedInterval(
            interval_id=state.saved_interval.interval_id if state.saved_interval else f"wbv-interval:{uuid4()}",
            managed_well_id=managed_well_id,
            trajectory_id=str(active.get("trajectory_id") or "") or None,
            trajectory_revision_uid=str(active.get("trajectory_revision_uid") or "") or None,
            start=start,
            end=point,
            top_md=top_md,
            base_md=base_md,
            depth_unit=self._depth_unit(record),
            created_at=existing_created,
            updated_at=now,
        )
        return self._save(managed_well_id, state.model_copy(update={"interval_draft_start": None, "saved_interval": interval, "updated_at": now}))

    def clear_interval(self, managed_well_id: str) -> WbvInteractionState:
        state = self.get(managed_well_id)
        return self._save(managed_well_id, state.model_copy(update={"interval_draft_start": None, "saved_interval": None, "updated_at": utc_now_iso()}))

    def send_interval_to_wdv(self, managed_well_id: str) -> WbvAoiTransferResult:
        state = self.get(managed_well_id)
        interval = state.saved_interval
        if interval is None:
            raise ValueError("A completed saved interval is required before sending an AOI to WDV.")
        workspace_service = WdvWorkspaceService(self.repository)
        workspace = workspace_service.get_workspace()
        if workspace.active_managed_well_id != managed_well_id:
            raise ValueError("WBV interval well must match the backend-owned active WDV well.")
        stored = workspace_service._read_store()
        now = utc_now_iso()
        stored["active_aoi"] = {
            "contract_kind": "wdv_active_aoi",
            "contract_version": "wdv_active_aoi_v1",
            "source_viewer": "WBV",
            "workspace_id": workspace.workspace_id,
            "managed_well_id": managed_well_id,
            "interval_id": interval.interval_id,
            "top_md": interval.top_md,
            "base_md": interval.base_md,
            "depth_unit": interval.depth_unit,
            "trajectory_id": interval.trajectory_id,
            "trajectory_revision_uid": interval.trajectory_revision_uid,
            "applied_at": now,
        }
        stored["revision"] = int(stored.get("revision", 0) or 0) + 1
        stored["updated_at"] = now
        workspace_service._write_store(stored)
        return WbvAoiTransferResult(
            workspace_id=workspace.workspace_id,
            workspace_revision=int(stored["revision"]),
            managed_well_id=managed_well_id,
            interval_id=interval.interval_id,
            top_md=interval.top_md,
            base_md=interval.base_md,
            depth_unit=interval.depth_unit,
            applied_at=now,
        )

    def _save(self, managed_well_id: str, state: WbvInteractionState) -> WbvInteractionState:
        record = self.repository.get_record(managed_well_id)
        metadata = dict(record.metadata or {})
        payload = state.model_dump(mode="json")
        payload.pop("managed_well_id", None)
        metadata[self.METADATA_KEY] = payload
        self.repository.upsert_record(record.model_copy(update={"metadata": metadata, "updated_at": utc_now_iso()}))
        return state

    def _validate_md(self, managed_well_id: str, md: float) -> None:
        values = self._canonical_md_values(managed_well_id)
        if not values:
            raise ValueError("Active trajectory has no canonical MD samples.")
        if md < min(values) or md > max(values):
            raise ValueError("Selected MD is outside the active trajectory range.")

    def _canonical_md_values(self, managed_well_id: str) -> list[float]:
        """Resolve MD from the same backend viewer package rendered by WBV.

        The interaction service must not inspect a narrower metadata path than the
        viewer service. Viewer-package resolution includes the active managed
        trajectory, legacy trajectory package, and governed runtime seed fallback.
        """
        if self.trajectory_package_provider is not None:
            contract = self.trajectory_package_provider(managed_well_id)
            trajectory = getattr(contract, "trajectory", None)
            points = getattr(trajectory, "render_points", None)
            values = self._md_values(points)
            if values:
                return values

        record = self.repository.get_record(managed_well_id)
        active = self._active_trajectory(record)
        package = active.get("trajectory_package") if isinstance(active, dict) else None
        points = package.get("render_points", []) if isinstance(package, dict) else []
        return self._md_values(points)

    @staticmethod
    def _md_values(points: Any) -> list[float]:
        if not isinstance(points, list):
            return []
        values: list[float] = []
        for point in points:
            if isinstance(point, dict):
                value = point.get("md")
            else:
                value = getattr(point, "md", None)
            if isinstance(value, (int, float)):
                values.append(float(value))
        return values

    @staticmethod
    def _active_trajectory(record: Any) -> dict[str, Any]:
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        rows = metadata.get("managed_trajectories", [])
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("is_active") is True:
                    return row
        package = metadata.get("wbv_trajectory_package")
        return {"trajectory_package": package} if isinstance(package, dict) else {}

    @staticmethod
    def _depth_unit(record: Any) -> str:
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        return str(metadata.get("wbv_display_depth_unit") or metadata.get("depth_unit") or "ft")
