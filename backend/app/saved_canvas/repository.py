"""Atomic repository for immutable workspace-level Saved Canvases."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

from .models import (
    SAVED_CANVAS_STORE_CONTRACT_VERSION,
    SavedCanvasMetadata,
    SavedCanvasRecord,
)


class SavedCanvasNotFoundError(KeyError):
    pass


class SavedCanvasRepository:
    _lock = RLock()

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or (
            Path(__file__).resolve().parents[3] / "data" / "wdv" / "saved_canvases_v1.json"
        )

    def create(self, record: SavedCanvasRecord) -> SavedCanvasRecord:
        with self._lock:
            store = self._read_store()
            canvases = self._workspace_canvases(store, record.workspace_id)
            if any(item.get("saved_canvas_uid") == record.saved_canvas_uid for item in canvases):
                raise ValueError(f"Saved Canvas UID already exists: {record.saved_canvas_uid}")
            # model_dump + JSON round-trip is an explicit deep copy at the immutable boundary.
            payload = json.loads(json.dumps(record.model_dump(mode="json")))
            canvases.append(payload)
            self._set_active_uid(store, record.workspace_id, record.saved_canvas_uid)
            self._write_store(store)
        return SavedCanvasRecord.model_validate(payload)

    def list_metadata(self, workspace_id: str) -> list[SavedCanvasMetadata]:
        with self._lock:
            store = self._read_store()
            canvases = list(self._workspace_canvases(store, workspace_id, create=False))
            active_uid = self._active_uid(store, workspace_id)
        records = [SavedCanvasRecord.model_validate(item) for item in canvases]
        records.sort(key=lambda item: (item.created_at, item.saved_canvas_uid))
        return [
            SavedCanvasMetadata(
                saved_canvas_uid=item.saved_canvas_uid,
                workspace_id=item.workspace_id,
                name=item.name,
                created_at=item.created_at,
                schema_version=item.schema_version,
                is_active=str(item.saved_canvas_uid) == active_uid,
            )
            for item in records
        ]

    def replace(self, record: SavedCanvasRecord) -> SavedCanvasRecord:
        with self._lock:
            store = self._read_store()
            canvases = self._workspace_canvases(store, record.workspace_id, create=False)
            for index, item in enumerate(canvases):
                if item.get("saved_canvas_uid") != record.saved_canvas_uid:
                    continue
                payload = json.loads(json.dumps(record.model_dump(mode="json")))
                canvases[index] = payload
                self._set_active_uid(store, record.workspace_id, record.saved_canvas_uid)
                self._write_store(store)
                return SavedCanvasRecord.model_validate(payload)
        raise SavedCanvasNotFoundError(record.saved_canvas_uid)

    def set_active(self, workspace_id: str, saved_canvas_uid: str) -> None:
        with self._lock:
            store = self._read_store()
            canvases = self._workspace_canvases(store, workspace_id, create=False)
            if not any(item.get("saved_canvas_uid") == saved_canvas_uid for item in canvases):
                raise SavedCanvasNotFoundError(saved_canvas_uid)
            self._set_active_uid(store, workspace_id, saved_canvas_uid)
            self._write_store(store)

    def get(self, workspace_id: str, saved_canvas_uid: str) -> SavedCanvasRecord:
        with self._lock:
            store = self._read_store()
            for item in self._workspace_canvases(store, workspace_id, create=False):
                if item.get("saved_canvas_uid") == saved_canvas_uid:
                    return SavedCanvasRecord.model_validate(
                        json.loads(json.dumps(item))
                    )
        raise SavedCanvasNotFoundError(saved_canvas_uid)

    def delete(self, workspace_id: str, saved_canvas_uid: str) -> SavedCanvasMetadata:
        with self._lock:
            store = self._read_store()
            canvases = self._workspace_canvases(store, workspace_id, create=False)
            for index, item in enumerate(canvases):
                if item.get("saved_canvas_uid") != saved_canvas_uid:
                    continue
                record = SavedCanvasRecord.model_validate(item)
                del canvases[index]
                if self._active_uid(store, workspace_id) == saved_canvas_uid:
                    self._set_active_uid(store, workspace_id, None)
                self._write_store(store)
                return SavedCanvasMetadata(
                    saved_canvas_uid=record.saved_canvas_uid,
                    workspace_id=record.workspace_id,
                    name=record.name,
                    created_at=record.created_at,
                    schema_version=record.schema_version,
                )
        raise SavedCanvasNotFoundError(saved_canvas_uid)

    def _read_store(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return {
                "contract_version": SAVED_CANVAS_STORE_CONTRACT_VERSION,
                "workspaces": {},
            }
        raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Saved Canvas store must be a JSON object")
        if raw.get("contract_version") != SAVED_CANVAS_STORE_CONTRACT_VERSION:
            raise ValueError("Unsupported Saved Canvas store contract_version")
        workspaces = raw.get("workspaces")
        if not isinstance(workspaces, dict):
            raise ValueError("Saved Canvas store workspaces must be an object")
        return raw

    @staticmethod
    def _workspace_canvases(
        store: dict[str, Any], workspace_id: str, *, create: bool = True
    ) -> list[dict[str, Any]]:
        workspaces = store.setdefault("workspaces", {})
        entry = workspaces.get(workspace_id)
        if entry is None:
            if not create:
                return []
            entry = {"saved_canvases": []}
            workspaces[workspace_id] = entry
        if not isinstance(entry, dict):
            raise ValueError("Saved Canvas workspace entry must be an object")
        canvases = entry.setdefault("saved_canvases", [])
        if not isinstance(canvases, list):
            raise ValueError("Saved Canvas workspace collection must be a list")
        return canvases

    @staticmethod
    def _active_uid(store: dict[str, Any], workspace_id: str) -> str | None:
        entry = store.get("workspaces", {}).get(workspace_id)
        if not isinstance(entry, dict):
            return None
        raw = entry.get("active_saved_canvas_uid")
        return str(raw) if raw else None

    @staticmethod
    def _set_active_uid(
        store: dict[str, Any], workspace_id: str, saved_canvas_uid: str | None
    ) -> None:
        workspaces = store.setdefault("workspaces", {})
        entry = workspaces.setdefault(workspace_id, {"saved_canvases": []})
        if not isinstance(entry, dict):
            raise ValueError("Saved Canvas workspace entry must be an object")
        if saved_canvas_uid is None:
            entry.pop("active_saved_canvas_uid", None)
        else:
            entry["active_saved_canvas_uid"] = str(saved_canvas_uid)

    def _write_store(self, data: dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(self.storage_path.parent),
            delete=False,
        ) as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        temp_path.replace(self.storage_path)
