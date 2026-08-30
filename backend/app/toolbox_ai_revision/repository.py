from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_TOOLS = frozenset({"WME", "FTM", "CDM", "LCM", "DSM", "CIM_JOIN", "CIM_AIQC"})
SCHEMA_VERSION = "toolbox_ai_revision_registry_v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


class ToolboxAiRevisionRepository:
    """Atomic, inspectable JSON-backed authority for Toolbox AI revision streams."""

    def __init__(self, path: Path | str | None = None) -> None:
        if path is None:
            path = Path(__file__).resolve().parents[3] / "runtime" / "toolbox_ai_revision_registry_v1.json"
        self.path = Path(path)
        self._lock = threading.RLock()

    def _empty(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "streams": {}}

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Toolbox AI revision registry is unreadable: {self.path}") from exc
        if payload.get("schema_version") != SCHEMA_VERSION or not isinstance(payload.get("streams"), dict):
            raise RuntimeError(f"Toolbox AI revision registry has an unsupported schema: {self.path}")
        return payload

    def _write_unlocked(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _stream_id(tool: str, authority_key: str) -> str:
        tool = _text(tool).upper()
        authority_key = _text(authority_key)
        if tool not in VALID_TOOLS:
            raise ValueError(f"Unsupported Toolbox AI revision tool: {tool}")
        if not authority_key:
            raise ValueError("authority_key is required")
        return f"{tool}::{authority_key}"

    @staticmethod
    def _new_stream(tool: str, authority_key: str, well_name: str | None, managed_well_id: str | None) -> dict[str, Any]:
        now = _utc_now()
        return {
            "tool": tool,
            "authority_key": authority_key,
            "managed_well_id": _text(managed_well_id) or None,
            "well_name": _text(well_name) or None,
            "current_revision": 0,
            "created_at": now,
            "updated_at": now,
            "history": [],
        }

    def list_streams(self) -> list[dict[str, Any]]:
        with self._lock:
            payload = self._load_unlocked()
            result = [deepcopy(value) for value in payload["streams"].values()]
            result.sort(key=lambda row: (row.get("tool", ""), row.get("authority_key", "")))
            return result

    def get(self, tool: str, authority_key: str) -> dict[str, Any] | None:
        sid = self._stream_id(tool, authority_key)
        with self._lock:
            payload = self._load_unlocked()
            value = payload["streams"].get(sid)
            return deepcopy(value) if value is not None else None

    def _ensure(
        self,
        payload: dict[str, Any],
        tool: str,
        authority_key: str,
        well_name: str | None = None,
        managed_well_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        sid = self._stream_id(tool, authority_key)
        tool = _text(tool).upper()
        authority_key = _text(authority_key)
        stream = payload["streams"].get(sid)
        if stream is None:
            stream = self._new_stream(tool, authority_key, well_name, managed_well_id)
            payload["streams"][sid] = stream
        else:
            if _text(well_name):
                stream["well_name"] = _text(well_name)
            if _text(managed_well_id):
                stream["managed_well_id"] = _text(managed_well_id)
        return sid, stream

    @staticmethod
    def _history(
        stream: dict[str, Any],
        *,
        revision: int,
        action: str,
        reason: str | None,
        artifact_name: str | None,
        actor: str | None,
        previous_revision: int,
    ) -> None:
        stream["history"].append(
            {
                "revision": revision,
                "previous_revision": previous_revision,
                "action": action,
                "timestamp": _utc_now(),
                "reason": _text(reason) or None,
                "artifact_name": _text(artifact_name) or None,
                "actor": _text(actor) or None,
            }
        )
        stream["updated_at"] = _utc_now()

    def synchronize(
        self,
        tool: str,
        authority_key: str,
        revision: int,
        *,
        reason: str | None = None,
        artifact_name: str | None = None,
        actor: str | None = None,
        well_name: str | None = None,
        managed_well_id: str | None = None,
    ) -> dict[str, Any]:
        revision = int(revision)
        if revision < 0:
            raise ValueError("revision must be >= 0")
        with self._lock:
            payload = self._load_unlocked()
            _, stream = self._ensure(payload, tool, authority_key, well_name, managed_well_id)
            previous = int(stream["current_revision"])
            if revision > previous:
                stream["current_revision"] = revision
                self._history(
                    stream,
                    revision=revision,
                    previous_revision=previous,
                    action="synchronize",
                    reason=reason,
                    artifact_name=artifact_name,
                    actor=actor,
                )
                self._write_unlocked(payload)
            return deepcopy(stream)

    def allocate(
        self,
        tool: str,
        authority_key: str,
        *,
        reason: str | None = None,
        artifact_name: str | None = None,
        actor: str | None = None,
        well_name: str | None = None,
        managed_well_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            payload = self._load_unlocked()
            _, stream = self._ensure(payload, tool, authority_key, well_name, managed_well_id)
            previous = int(stream["current_revision"])
            revision = previous + 1
            stream["current_revision"] = revision
            self._history(
                stream,
                revision=revision,
                previous_revision=previous,
                action="allocate_export",
                reason=reason or "AI package export",
                artifact_name=artifact_name,
                actor=actor,
            )
            self._write_unlocked(payload)
            return deepcopy(stream)

    def correct(
        self,
        tool: str,
        authority_key: str,
        revision: int,
        *,
        reason: str,
        actor: str | None = None,
        well_name: str | None = None,
        managed_well_id: str | None = None,
    ) -> dict[str, Any]:
        revision = int(revision)
        if revision < 0:
            raise ValueError("revision must be >= 0")
        if not _text(reason):
            raise ValueError("reason is required for an explicit correction")
        with self._lock:
            payload = self._load_unlocked()
            _, stream = self._ensure(payload, tool, authority_key, well_name, managed_well_id)
            previous = int(stream["current_revision"])
            stream["current_revision"] = revision
            self._history(
                stream,
                revision=revision,
                previous_revision=previous,
                action="explicit_correction",
                reason=reason,
                artifact_name=None,
                actor=actor,
            )
            self._write_unlocked(payload)
            return deepcopy(stream)
