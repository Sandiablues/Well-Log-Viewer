from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Any
import time

from app.identity import new_uuid7_str
from app.inventory.models import utc_now_iso
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.wdv_workspace import WdvWorkspaceService

from .contracts import (
    WbvAoiTransferResultV2,
    WbvInteractionModeRequestV2,
    WbvInteractionObservationV2,
    WbvInteractionStateV2,
    WbvSavedIntervalV2,
    WbvTrackSessionCommandV2,
)
from .projection import project_observation


@dataclass
class _TrackingSession:
    session_id: str
    managed_well_id: str
    starting_point: Any
    trajectory_points: tuple[Any, ...]
    last_sequence: int
    last_seen_monotonic: float
    live_state: WbvInteractionStateV2


class WbvInteractionDomainService:
    METADATA_KEY = "wbv_interaction_state_v2"
    SESSION_TTL_SECONDS = 120.0

    def __init__(
        self,
        repository: ManagedWellInventoryRepository | None = None,
        trajectory_package_provider: Callable[[str], Any] | None = None,
    ) -> None:
        self.repository = repository or ManagedWellInventoryRepository()
        self.trajectory_package_provider = trajectory_package_provider
        self._sessions: dict[str, _TrackingSession] = {}
        self._lock = RLock()

    def get(self, managed_well_id: str) -> WbvInteractionStateV2:
        self._expire_sessions()
        with self._lock:
            for session in self._sessions.values():
                if session.managed_well_id == managed_well_id:
                    return session.live_state
        record = self.repository.get_record(managed_well_id)
        raw = record.metadata.get(self.METADATA_KEY, {}) if isinstance(record.metadata, dict) else {}
        if isinstance(raw, dict) and raw:
            state = WbvInteractionStateV2.model_validate({"managed_well_id": managed_well_id, **raw})
            if state.active_tracking_session_id and state.active_tracking_session_id not in self._sessions:
                state = state.model_copy(update={
                    "active_tracking_session_id": None,
                    "tracking_status": "expired",
                    "revision": state.revision + 1,
                    "updated_at": utc_now_iso(),
                })
                return self._save(managed_well_id, state)
            return state
        return WbvInteractionStateV2(managed_well_id=managed_well_id, updated_at=utc_now_iso())

    def set_mode(self, managed_well_id: str, request: WbvInteractionModeRequestV2) -> WbvInteractionStateV2:
        state = self.get(managed_well_id)
        self._require_revision(state, request.expected_revision)
        return self._advance(managed_well_id, state.model_copy(update={
            "selection_mode": request.mode,
            "selected_point_visible": request.mode == "point",
            "interval_visible": request.mode == "interval",
            "active_tracking_session_id": None,
            "tracking_status": "idle",
            "fallback_status": "none",
        }))

    def observe(self, managed_well_id: str, request: WbvInteractionObservationV2) -> WbvInteractionStateV2:
        state = self.get(managed_well_id)
        self._require_revision(state, request.expected_revision)
        point = project_observation(self._trajectory_points(managed_well_id), request.observation)
        if state.selection_mode == "point" and state.selected_point_visible:
            return self._advance(managed_well_id, state.model_copy(update={
                "selected_point": point,
                "tracking_status": "committed",
                "fallback_status": "none",
            }))
        if state.selection_mode == "interval" and state.interval_visible:
            return self._apply_interval_pick(managed_well_id, state, point)
        raise ValueError("Selected Point or Interval Selection mode must be enabled before observing the trajectory.")

    def start_tracking(self, managed_well_id: str, request: WbvTrackSessionCommandV2) -> WbvInteractionStateV2:
        state = self.get(managed_well_id)
        self._require_revision(state, request.expected_revision)
        if state.selection_mode != "point" or not state.selected_point_visible:
            raise ValueError("Selected Point mode must be enabled before tracking.")
        if request.observation is None:
            raise ValueError("Tracking start requires a pointer observation.")
        trajectory_points = tuple(self._trajectory_points(managed_well_id))
        point = project_observation(trajectory_points, request.observation)
        session_id = new_uuid7_str()
        live_state = self._advance(managed_well_id, state.model_copy(update={
            "selected_point": point,
            "active_tracking_session_id": session_id,
            "tracking_status": "tracking",
            "fallback_status": "none",
        }))
        with self._lock:
            self._sessions[session_id] = _TrackingSession(
                session_id=session_id,
                managed_well_id=managed_well_id,
                starting_point=state.selected_point,
                trajectory_points=trajectory_points,
                last_sequence=request.sequence,
                last_seen_monotonic=time.monotonic(),
                live_state=live_state,
            )
        return live_state

    def update_tracking(self, managed_well_id: str, request: WbvTrackSessionCommandV2) -> WbvInteractionStateV2:
        if not request.session_id or request.observation is None:
            raise ValueError("Tracking update requires session_id and observation.")
        session = self._session(request.session_id, managed_well_id)
        state = session.live_state
        if request.sequence <= session.last_sequence:
            return state.model_copy(update={"fallback_status": "stale_command"})
        point = project_observation(
            session.trajectory_points,
            request.observation,
            enforce_activation_tolerance=False,
        )
        live_state = state.model_copy(update={
            "selected_point": point,
            "tracking_status": "tracking",
            "fallback_status": "none",
            "revision": state.revision + 1,
            "updated_at": utc_now_iso(),
        })
        with self._lock:
            session.last_sequence = request.sequence
            session.last_seen_monotonic = time.monotonic()
            session.live_state = live_state
        return live_state

    def commit_tracking(self, managed_well_id: str, request: WbvTrackSessionCommandV2) -> WbvInteractionStateV2:
        if not request.session_id:
            raise ValueError("Tracking commit requires session_id.")
        session = self._session(request.session_id, managed_well_id)
        state = session.live_state
        if request.observation is not None:
            state = state.model_copy(update={
                "selected_point": project_observation(
                    session.trajectory_points,
                    request.observation,
                    enforce_activation_tolerance=False,
                )
            })
        with self._lock:
            self._sessions.pop(request.session_id, None)
        return self._advance(managed_well_id, state.model_copy(update={
            "active_tracking_session_id": None,
            "tracking_status": "committed",
            "fallback_status": "none",
        }))

    def cancel_tracking(self, managed_well_id: str, request: WbvTrackSessionCommandV2) -> WbvInteractionStateV2:
        if not request.session_id:
            raise ValueError("Tracking cancel requires session_id.")
        session = self._session(request.session_id, managed_well_id)
        state = session.live_state
        with self._lock:
            self._sessions.pop(request.session_id, None)
        return self._advance(managed_well_id, state.model_copy(update={
            "selected_point": session.starting_point,
            "active_tracking_session_id": None,
            "tracking_status": "cancelled",
            "fallback_status": "none",
        }))

    def clear_interval(self, managed_well_id: str, expected_revision: int | None = None) -> WbvInteractionStateV2:
        state = self.get(managed_well_id)
        self._require_revision(state, expected_revision)
        return self._advance(managed_well_id, state.model_copy(update={
            "interval_draft_start": None,
            "saved_interval": None,
            "fallback_status": "none",
        }))

    def send_interval_to_wdv(self, managed_well_id: str) -> WbvAoiTransferResultV2:
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
        return WbvAoiTransferResultV2(
            workspace_id=workspace.workspace_id,
            workspace_revision=int(stored["revision"]),
            managed_well_id=managed_well_id,
            interval_id=interval.interval_id,
            top_md=interval.top_md,
            base_md=interval.base_md,
            depth_unit=interval.depth_unit,
            applied_at=now,
        )

    def _apply_interval_pick(self, managed_well_id: str, state: WbvInteractionStateV2, point: Any) -> WbvInteractionStateV2:
        now = utc_now_iso()
        if state.interval_draft_start is None:
            return self._advance(managed_well_id, state.model_copy(update={
                "interval_draft_start": point,
                "saved_interval": None,
            }))
        record = self.repository.get_record(managed_well_id)
        active = self._active_trajectory(record)
        start = state.interval_draft_start
        top_md, base_md = sorted((start.md, point.md))
        interval = WbvSavedIntervalV2(
            interval_id=state.saved_interval.interval_id if state.saved_interval else new_uuid7_str(),
            managed_well_id=managed_well_id,
            trajectory_id=str(active.get("trajectory_id") or "") or None,
            trajectory_revision_uid=str(active.get("trajectory_revision_uid") or "") or None,
            start=start,
            end=point,
            top_md=top_md,
            base_md=base_md,
            depth_unit=self._depth_unit(record),
            created_at=state.saved_interval.created_at if state.saved_interval else now,
            updated_at=now,
        )
        return self._advance(managed_well_id, state.model_copy(update={
            "interval_draft_start": None,
            "saved_interval": interval,
        }))

    def _trajectory_points(self, managed_well_id: str) -> list[Any]:
        if self.trajectory_package_provider is not None:
            contract = self.trajectory_package_provider(managed_well_id)
            trajectory = getattr(contract, "trajectory", None)
            points = getattr(trajectory, "render_points", None)
            if isinstance(points, list) and len(points) >= 2:
                return points
        record = self.repository.get_record(managed_well_id)
        active = self._active_trajectory(record)
        package = active.get("trajectory_package") if isinstance(active, dict) else None
        points = package.get("render_points", []) if isinstance(package, dict) else []
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError("Active trajectory has no authoritative render points.")
        return points

    def _advance(self, managed_well_id: str, state: WbvInteractionStateV2) -> WbvInteractionStateV2:
        return self._save(managed_well_id, state.model_copy(update={
            "revision": state.revision + 1,
            "updated_at": utc_now_iso(),
        }))

    def _save(self, managed_well_id: str, state: WbvInteractionStateV2) -> WbvInteractionStateV2:
        record = self.repository.get_record(managed_well_id)
        metadata = dict(record.metadata or {})
        payload = state.model_dump(mode="json")
        payload.pop("managed_well_id", None)
        metadata[self.METADATA_KEY] = payload
        self.repository.upsert_record(record.model_copy(update={"metadata": metadata, "updated_at": utc_now_iso()}))
        return state

    @staticmethod
    def _require_revision(state: WbvInteractionStateV2, expected: int | None) -> None:
        if expected is not None and expected != state.revision:
            raise ValueError(f"Stale interaction revision: expected {expected}, current {state.revision}.")

    def _session(self, session_id: str, managed_well_id: str) -> _TrackingSession:
        self._expire_sessions()
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None or session.managed_well_id != managed_well_id:
            raise ValueError("Tracking session is unavailable or expired.")
        return session

    def _expire_sessions(self) -> None:
        cutoff = time.monotonic() - self.SESSION_TTL_SECONDS
        with self._lock:
            expired = [key for key, value in self._sessions.items() if value.last_seen_monotonic < cutoff]
            for key in expired:
                self._sessions.pop(key, None)

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
