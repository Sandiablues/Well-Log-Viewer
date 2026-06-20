"""Canonical UUIDv7 WDV session persistence service."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from collections.abc import Callable
from typing import Any

from app.identity import new_uuid7_str, parse_uuid7
from app.identity.wdv_contract_v2 import (
    WDV_SESSION_CONTRACT_VERSION,
    WdvCanonicalSession,
)


class CanonicalSessionRevisionConflict(ValueError):
    pass


class CanonicalSessionCommandReplayConflict(ValueError):
    pass


class CanonicalWdvSessionService:
    _lock = RLock()

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or self.default_storage_path()

    @staticmethod
    def default_storage_path() -> Path:
        override = os.environ.get("WLV_WDV_CANONICAL_SESSION_STORE")
        if override:
            return Path(override).expanduser().resolve()
        return Path(__file__).resolve().parents[3] / "data" / "wdv" / "canonical_sessions_v2_1.json"

    def get_session(self, managed_well_uid: str) -> WdvCanonicalSession:
        well_uid = str(parse_uuid7(managed_well_uid))
        with self._lock:
            store = self._read_store()
            raw = store["sessions"].get(well_uid)
            if raw is not None:
                return WdvCanonicalSession.model_validate(raw)

            empty = self._empty_session(well_uid)
            store["sessions"][well_uid] = empty.model_dump(mode="json")
            self._write_store(store)
            return empty


    def mutate_session(
        self,
        managed_well_uid: str,
        expected_revision: int,
        mutation,
    ) -> WdvCanonicalSession:
        return self.mutate_session_transactionally(
            managed_well_uid,
            expected_revision=expected_revision,
            mutation=mutation,
        )

    def mutate_session_transactionally(
        self,
        managed_well_uid: str,
        *,
        expected_revision: int,
        mutation: Callable[[WdvCanonicalSession], WdvCanonicalSession],
        validator: Callable[[WdvCanonicalSession], object] | None = None,
        command_id: str | None = None,
        command_fingerprint: str | None = None,
    ) -> WdvCanonicalSession:
        """Atomically validate and persist one revision-guarded mutation.

        When ``command_id`` is supplied, the command receipt is written in the
        same JSON promotion as the session. Replaying the same command returns
        the original persisted result without incrementing the revision.
        """
        well_uid = str(parse_uuid7(managed_well_uid))
        if (command_id is None) != (command_fingerprint is None):
            raise ValueError(
                "command_id and command_fingerprint must be supplied together"
            )

        with self._lock:
            store = self._read_store()
            receipts_by_well = store.setdefault("command_receipts", {})

            if command_id is not None:
                well_receipts = receipts_by_well.get(well_uid, {})
                receipt = well_receipts.get(command_id)
                if receipt is not None:
                    if receipt.get("fingerprint") != command_fingerprint:
                        raise CanonicalSessionCommandReplayConflict(
                            "command_id was already used with a different payload"
                        )
                    return WdvCanonicalSession.model_validate(
                        receipt["session"]
                    )

            raw = store["sessions"].get(well_uid)
            current = (
                self._empty_session(well_uid)
                if raw is None
                else WdvCanonicalSession.model_validate(raw)
            )
            if current.revision != expected_revision:
                raise CanonicalSessionRevisionConflict(
                    f"Expected revision {expected_revision}, found {current.revision}"
                )

            updated = mutation(current)
            if updated.managed_well_uid != well_uid:
                raise ValueError(
                    "Mutation returned a session for a different managed well"
                )
            persisted_candidate = updated.model_copy(
                update={
                    "revision": current.revision + 1,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            persisted = WdvCanonicalSession.model_validate(
                persisted_candidate.model_dump(mode="json")
            )

            if validator is not None:
                validator(persisted)

            persisted_json = persisted.model_dump(mode="json")
            store["sessions"][well_uid] = persisted_json
            if command_id is not None:
                well_receipts = receipts_by_well.setdefault(well_uid, {})
                well_receipts[command_id] = {
                    "fingerprint": command_fingerprint,
                    "session": persisted_json,
                }
            self._write_store(store)
            return persisted

    def put_session(self, session: WdvCanonicalSession) -> WdvCanonicalSession:
        with self._lock:
            store = self._read_store()
            current = store["sessions"].get(session.managed_well_uid)
            revision = int(current.get("revision", -1)) + 1 if current else 0
            persisted = session.model_copy(
                update={
                    "revision": revision,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            store["sessions"][session.managed_well_uid] = persisted.model_dump(mode="json")
            self._write_store(store)
            return persisted

    def clear_session(self, managed_well_uid: str, reason: str) -> WdvCanonicalSession:
        well_uid = str(parse_uuid7(managed_well_uid))
        current = self.get_session(well_uid)
        cleared = WdvCanonicalSession(
            session_uid=current.session_uid,
            managed_well_uid=well_uid,
            revision=current.revision + 1,
            state_status="cleared",
            source=reason.strip() or "user_requested_clear",
            tracks=(),
            selected_track_uid=None,
            warnings=(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            store = self._read_store()
            store["sessions"][well_uid] = cleared.model_dump(mode="json")
            self._write_store(store)
        return cleared

    def _empty_session(self, managed_well_uid: str) -> WdvCanonicalSession:
        return WdvCanonicalSession(
            session_uid=new_uuid7_str(),
            managed_well_uid=managed_well_uid,
            revision=0,
            state_status="empty",
            source="backend_owned_session_state",
            tracks=(),
            selected_track_uid=None,
            warnings=(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _read_store(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return {
                "schema_version": WDV_SESSION_CONTRACT_VERSION,
                "sessions": {},
                "command_receipts": {},
            }
        raw = json.loads(self.storage_path.read_text())
        if not isinstance(raw, dict) or not isinstance(raw.get("sessions", {}), dict):
            raise ValueError("Canonical WDV session store is malformed")
        raw.setdefault("schema_version", WDV_SESSION_CONTRACT_VERSION)
        raw.setdefault("sessions", {})
        receipts = raw.setdefault("command_receipts", {})
        if not isinstance(receipts, dict):
            raise ValueError("Canonical WDV command receipt store is malformed")
        return raw

    def _write_store(self, data: dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data["schema_version"] = WDV_SESSION_CONTRACT_VERSION
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(self.storage_path.parent), delete=False
        ) as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temp_path = Path(handle.name)
        temp_path.replace(self.storage_path)
