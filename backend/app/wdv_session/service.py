"""Backend-owned WDV layout/session state service."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from .models import (
    WDV_SESSION_LAYOUT_CONTRACT_VERSION,
    WdvSessionLayoutPutRequest,
    WdvSessionLayoutStateResponse,
)


class WdvSessionLayoutStateService:
    """Durable local backend-owned WDV layout/session state service.

    This is intentionally lightweight JSON storage for the local/dev profile,
    but the contract and service boundary are enterprise-shaped: callers use
    a backend API and do not depend on frontend-local layout truth.
    """

    _lock = RLock()

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or self.default_storage_path()

    @staticmethod
    def default_storage_path() -> Path:
        override = os.environ.get("WLV_WDV_SESSION_LAYOUT_STORE")
        if override:
            return Path(override).expanduser().resolve()
        return Path(__file__).resolve().parents[3] / "data" / "wdv" / "session_layouts.json"

    def get_layout(self, managed_well_id: str) -> WdvSessionLayoutStateResponse:
        data = self._read_store()
        session = data.get("sessions", {}).get(managed_well_id)
        if not session:
            return self._empty_session(managed_well_id)
        return WdvSessionLayoutStateResponse.model_validate(session)

    def put_layout(
        self,
        managed_well_id: str,
        request: WdvSessionLayoutPutRequest,
    ) -> WdvSessionLayoutStateResponse:
        self._validate_layout_request(request)
        with self._lock:
            data = self._read_store()
            sessions = data.setdefault("sessions", {})
            current_revision = int(sessions.get(managed_well_id, {}).get("revision", 0) or 0)
            session = WdvSessionLayoutStateResponse(
                managed_well_id=managed_well_id,
                layout_session_id=f"wdv_layout_session:{managed_well_id}",
                revision=current_revision + 1,
                state_status="active" if request.tracks else "empty",
                source=request.source,
                updated_at=self._now(),
                selected_track_id=request.selected_track_id,
                tracks=request.tracks,
                warnings=[],
            )
            sessions[managed_well_id] = session.model_dump(mode="json")
            self._write_store(data)
            return session

    def clear_layout(self, managed_well_id: str, reason: str = "user_requested_clear") -> WdvSessionLayoutStateResponse:
        with self._lock:
            data = self._read_store()
            sessions = data.setdefault("sessions", {})
            current_revision = int(sessions.get(managed_well_id, {}).get("revision", 0) or 0)
            session = WdvSessionLayoutStateResponse(
                managed_well_id=managed_well_id,
                layout_session_id=f"wdv_layout_session:{managed_well_id}",
                revision=current_revision + 1,
                state_status="cleared",
                source=reason,
                updated_at=self._now(),
                selected_track_id=None,
                tracks=[],
                warnings=[],
            )
            sessions[managed_well_id] = session.model_dump(mode="json")
            self._write_store(data)
            return session

    def _empty_session(self, managed_well_id: str) -> WdvSessionLayoutStateResponse:
        return WdvSessionLayoutStateResponse(
            managed_well_id=managed_well_id,
            layout_session_id=f"wdv_layout_session:{managed_well_id}",
            revision=0,
            state_status="empty",
            source="backend_owned_session_state",
            updated_at=self._now(),
            selected_track_id=None,
            tracks=[],
            warnings=[],
        )

    def _read_store(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return {"schema_version": WDV_SESSION_LAYOUT_CONTRACT_VERSION, "sessions": {}}
        try:
            raw = json.loads(self.storage_path.read_text())
        except json.JSONDecodeError:
            return {"schema_version": WDV_SESSION_LAYOUT_CONTRACT_VERSION, "sessions": {}}
        if not isinstance(raw, dict):
            return {"schema_version": WDV_SESSION_LAYOUT_CONTRACT_VERSION, "sessions": {}}
        raw.setdefault("schema_version", WDV_SESSION_LAYOUT_CONTRACT_VERSION)
        raw.setdefault("sessions", {})
        return raw

    def _write_store(self, data: dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data["schema_version"] = WDV_SESSION_LAYOUT_CONTRACT_VERSION
        data.setdefault("sessions", {})
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(self.storage_path.parent),
            delete=False,
        ) as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            tmp_name = handle.name
        Path(tmp_name).replace(self.storage_path)

    def _validate_layout_request(self, request: WdvSessionLayoutPutRequest) -> None:
        track_ids: set[str] = set()
        assignment_ids: set[str] = set()
        for track in request.tracks:
            if track.track_id in track_ids:
                raise ValueError(f"Duplicate WDV track_id in layout request: {track.track_id}")
            track_ids.add(track.track_id)
            for curve in track.curves:
                if curve.assignment_id in assignment_ids:
                    raise ValueError(f"Duplicate WDV assignment_id in layout request: {curve.assignment_id}")
                assignment_ids.add(curve.assignment_id)
        if request.selected_track_id and request.selected_track_id not in track_ids:
            raise ValueError("selected_track_id must refer to a track in the supplied layout")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
