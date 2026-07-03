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
    WdvCanonicalAssignment,
    WdvCanonicalSession,
)
from app.wdv_display.policy_service import compute_display_policy_revision


AssignmentPolicyRefreshFn = Callable[
    [WdvCanonicalAssignment],
    WdvCanonicalAssignment,
]


class CanonicalSessionRevisionConflict(ValueError):
    pass


class CanonicalSessionCommandReplayConflict(ValueError):
    pass


def _refresh_assignments_and_stamp(
    session: WdvCanonicalSession,
    display_policy_revision: str,
    assignment_policy_refresh_fn: AssignmentPolicyRefreshFn,
) -> WdvCanonicalSession:
    """Re-resolve every assignment from current backend policy and explicit intent."""
    tracks = tuple(
        track.model_copy(
            update={
                "assignments": tuple(
                    assignment_policy_refresh_fn(assignment)
                    for assignment in track.assignments
                )
            }
        )
        for track in session.tracks
    )
    return session.model_copy(
        update={
            "tracks": tracks,
            "display_policy_revision": display_policy_revision,
        }
    )


def _migrate_legacy_session_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """One-time storage-boundary conversion; legacy state never enters runtime."""
    migrated = json.loads(json.dumps(raw))
    migrated.setdefault("curve_fills", [])
    session_well_uid = migrated.get("managed_well_uid")
    for track in migrated.get("tracks", []):
        if not track.get("managed_well_uid"):
            assignments = track.get("assignments", [])
            track["managed_well_uid"] = (
                assignments[0].get("managed_well_uid") if assignments else session_well_uid
            )
        for assignment in track.get("assignments", []):
            if "range_override_mode" in assignment:
                continue
            legacy_manual = assignment.get("display_policy_source") == "user_override"
            if legacy_manual:
                assignment["range_override_mode"] = "manual"
                assignment["manual_scale_min"] = assignment.get("scale_min")
                assignment["manual_scale_max"] = assignment.get("scale_max")
                assignment["effective_range_source"] = "manual"
                assignment["display_policy_source"] = None
            else:
                assignment["range_override_mode"] = "governed"
                assignment["manual_scale_min"] = None
                assignment["manual_scale_max"] = None
                assignment["effective_range_source"] = "governed"
            assignment.setdefault("override_warning_code", None)
            assignment.setdefault("override_warning_message", None)
    return migrated


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class CanonicalWdvSessionService:
    _lock = RLock()

    def __init__(
        self,
        storage_path: Path | None = None,
        *,
        policy_revision_fn: Callable[[], str] | None = None,
        assignment_policy_refresh_fn: AssignmentPolicyRefreshFn | None = None,
    ) -> None:
        self.storage_path = storage_path or self.default_storage_path()
        self._policy_revision_fn: Callable[[], str] = (
            policy_revision_fn
            if policy_revision_fn is not None
            else compute_display_policy_revision
        )
        self._assignment_policy_refresh_fn = assignment_policy_refresh_fn

    def configure_policy_refresh(
        self,
        *,
        policy_revision_fn: Callable[[], str],
        assignment_policy_refresh_fn: AssignmentPolicyRefreshFn,
    ) -> None:
        """Attach the backend policy-refresh authority to this session service."""
        self._policy_revision_fn = policy_revision_fn
        self._assignment_policy_refresh_fn = assignment_policy_refresh_fn

    @staticmethod
    def default_storage_path() -> Path:
        override = os.environ.get("WLV_WDV_CANONICAL_SESSION_STORE")
        if override:
            return Path(override).expanduser().resolve()
        return Path(__file__).resolve().parents[3] / "data" / "wdv" / "canonical_sessions_v2_1.json"

    @staticmethod
    def unified_multiwell_enabled() -> bool:
        return os.environ.get("WLV_UNIFIED_MULTIWELL_SESSION", "1").strip().lower() not in {
            "0", "false", "no", "off"
        }

    def _storage_key(self, well_uid: str) -> str:
        return "__unified_wdv_canvas__" if self.unified_multiwell_enabled() else well_uid

    @staticmethod
    def _project_working_well(session: WdvCanonicalSession, well_uid: str) -> WdvCanonicalSession:
        return session if session.managed_well_uid == well_uid else session.model_copy(
            update={"managed_well_uid": well_uid}
        )

    def get_session(self, managed_well_uid: str) -> WdvCanonicalSession:
        """Return the canonical session for a well, creating an empty one if absent.

        When a non-empty session's stored ``display_policy_revision`` differs
        from the current revision, backend-owned assignments are re-resolved,
        explicit user overrides are retained, and legacy assignments keep their
        compatibility behavior. The refreshed session is persisted atomically.

        Idempotency rules:
        - Matching revision → no mutation.
        - Empty session (no assignments) → no policy lookup or mutation.\n        - Standalone services without a configured refresher keep the prior\n          stale-override lifecycle unchanged.
        """
        well_uid = str(parse_uuid7(managed_well_uid))
        storage_key = self._storage_key(well_uid)
        with self._lock:
            store = self._read_store()
            raw = store["sessions"].get(storage_key)
            if raw is None and storage_key != well_uid:
                raw = store["sessions"].get(well_uid)
                if raw is not None:
                    store["sessions"][storage_key] = raw
                    self._write_store(store)
            if raw is not None:
                session = WdvCanonicalSession.model_validate(_migrate_legacy_session_payload(raw))
            else:
                empty = self._empty_session(well_uid)
                store["sessions"][storage_key] = empty.model_dump(mode="json")
                self._write_store(store)
                session = empty

            has_assignments = any(
                track.assignments for track in session.tracks
            )
            if has_assignments and self._assignment_policy_refresh_fn is not None:
                current_revision = self._policy_revision_fn()
                if session.display_policy_revision != current_revision:
                    session = self.mutate_session_transactionally(
                        managed_well_uid,
                        expected_revision=session.revision,
                        mutation=lambda current: _refresh_assignments_and_stamp(
                            current,
                            current_revision,
                            self._assignment_policy_refresh_fn,
                        ),
                    )
            return self._project_working_well(session, well_uid)


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

    def promote_command_receipt_session(
        self,
        managed_well_uid: str,
        *,
        command_id: str,
        command_fingerprint: str,
        session: WdvCanonicalSession,
    ) -> None:
        """Atomically promote a command receipt to a later canonical session.

        Compound backend workflows may persist the command mutation first and
        then promote derived backend-owned state (for example resolved geometry
        metadata). Replays must return the final canonical state, not the
        intermediate mutation revision.
        """
        well_uid = str(parse_uuid7(managed_well_uid))
        storage_key = self._storage_key(well_uid)
        with self._lock:
            store = self._read_store()
            receipts_by_well = store.setdefault("command_receipts", {})
            well_receipts = receipts_by_well.setdefault(storage_key, {})
            receipt = well_receipts.get(command_id)
            if receipt is None:
                raise CanonicalSessionCommandReplayConflict(
                    "Cannot promote an unknown command receipt"
                )
            if receipt.get("fingerprint") != command_fingerprint:
                raise CanonicalSessionCommandReplayConflict(
                    "command_id was already used with a different payload"
                )
            validated = WdvCanonicalSession.model_validate(
                session.model_dump(mode="json")
            )
            if validated.managed_well_uid != well_uid:
                raise ValueError("Receipt promotion session belongs to a different managed well")
            receipt["session"] = validated.model_dump(mode="json")
            self._write_store(store)

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
        storage_key = self._storage_key(well_uid)
        if (command_id is None) != (command_fingerprint is None):
            raise ValueError(
                "command_id and command_fingerprint must be supplied together"
            )

        with self._lock:
            store = self._read_store()
            receipts_by_well = store.setdefault("command_receipts", {})

            if command_id is not None:
                well_receipts = receipts_by_well.get(storage_key, {})
                receipt = well_receipts.get(command_id)
                if receipt is not None:
                    if receipt.get("fingerprint") != command_fingerprint:
                        raise CanonicalSessionCommandReplayConflict(
                            "command_id was already used with a different payload"
                        )
                    return self._project_working_well(
                        WdvCanonicalSession.model_validate(receipt["session"]), well_uid
                    )

            raw = store["sessions"].get(storage_key)
            if raw is None and storage_key != well_uid:
                raw = store["sessions"].get(well_uid)
            current = (
                self._empty_session(well_uid)
                if raw is None
                else self._project_working_well(
                    WdvCanonicalSession.model_validate(_migrate_legacy_session_payload(raw)),
                    well_uid,
                )
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
            store["sessions"][storage_key] = persisted_json
            if command_id is not None:
                well_receipts = receipts_by_well.setdefault(storage_key, {})
                well_receipts[command_id] = {
                    "fingerprint": command_fingerprint,
                    "session": persisted_json,
                }
            self._write_store(store)
            return persisted

    def put_session(self, session: WdvCanonicalSession) -> WdvCanonicalSession:
        with self._lock:
            store = self._read_store()
            storage_key = self._storage_key(session.managed_well_uid)
            current = store["sessions"].get(storage_key)
            revision = int(current.get("revision", -1)) + 1 if current else 0
            persisted = session.model_copy(
                update={
                    "revision": revision,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            store["sessions"][storage_key] = persisted.model_dump(mode="json")
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
            store["sessions"][self._storage_key(well_uid)] = cleared.model_dump(mode="json")
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
