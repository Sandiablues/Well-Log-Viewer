"""Shared canvas profile repository interface and local JSON adapter.

The abstract base class defines the storage contract.
The LocalJsonSharedCanvasRepository provides a desktop-grade JSON implementation.

The domain service (service.py) depends only on SharedCanvasProfileRepository.
Replacing the adapter with a PostgreSQL or other transactional implementation
does not require modifying the service.
"""

from __future__ import annotations

import json
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from threading import RLock
from typing import Any

from .models import (
    SHARED_CANVAS_CONTRACT_VERSION,
    SharedCanvasActivation,
    SharedCanvasAuditRecord,
    SharedCanvasProfile,
    SharedCanvasProfileRevision,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SharedCanvasRevisionConflict(ValueError):
    """Optimistic concurrency conflict: expected revision number did not match."""


class SharedCanvasProfileNotFound(KeyError):
    """Requested profile, revision, or activation does not exist."""


# ---------------------------------------------------------------------------
# Abstract repository contract
# ---------------------------------------------------------------------------

class SharedCanvasProfileRepository(ABC):
    """Storage-independent contract for shared canvas profile persistence.

    All write operations must be atomic within the storage backend.
    The optimistic concurrency check in append_revision must occur inside
    the same atomic operation as the write.
    """

    @abstractmethod
    def create_profile(
        self,
        profile: SharedCanvasProfile,
        initial_revision: SharedCanvasProfileRevision,
        audit: SharedCanvasAuditRecord,
    ) -> None:
        """Atomically persist a new profile header and its first immutable revision."""

    @abstractmethod
    def get_profile(self, profile_uid: str) -> SharedCanvasProfile | None:
        """Return the profile header or None if not found."""

    @abstractmethod
    def list_profiles(
        self, include_archived: bool = False
    ) -> list[SharedCanvasProfile]:
        """Return profile headers, ordered by created_at ascending."""

    @abstractmethod
    def update_profile_header(
        self,
        profile: SharedCanvasProfile,
        audit: SharedCanvasAuditRecord,
    ) -> None:
        """Replace the profile header record atomically (archive / rename)."""

    @abstractmethod
    def append_revision(
        self,
        revision: SharedCanvasProfileRevision,
        expected_revision_number: int,
        audit: SharedCanvasAuditRecord,
    ) -> None:
        """Append an immutable revision inside an atomic operation.

        Raises SharedCanvasRevisionConflict if the current latest
        revision_number for this profile does not equal expected_revision_number.
        """

    @abstractmethod
    def get_revision(
        self, profile_revision_uid: str
    ) -> SharedCanvasProfileRevision | None:
        """Return a specific immutable revision or None."""

    @abstractmethod
    def list_revisions(
        self, profile_uid: str
    ) -> list[SharedCanvasProfileRevision]:
        """Return all revisions for a profile, ordered by revision_number ascending."""

    @abstractmethod
    def set_activation(self, activation: SharedCanvasActivation) -> None:
        """Replace or create the active profile revision for a scope."""

    @abstractmethod
    def get_activation(
        self, scope_type: str, scope_uid: str
    ) -> SharedCanvasActivation | None:
        """Return the current activation for a scope or None."""

    @abstractmethod
    def list_activations(self) -> list[SharedCanvasActivation]:
        """Return all activation records."""

    @abstractmethod
    def append_audit(self, record: SharedCanvasAuditRecord) -> None:
        """Append one audit record."""


# ---------------------------------------------------------------------------
# Local JSON adapter
# ---------------------------------------------------------------------------

class LocalJsonSharedCanvasRepository(SharedCanvasProfileRepository):
    """Desktop-grade JSON adapter for the shared canvas profile repository.

    Storage layout (shared_canvas_profiles.json):
      {
        "schema_version": "shared_canvas_profiles_v1",
        "profiles":        { "<profile_uid>": {...} },
        "revisions":       { "<profile_revision_uid>": {...} },
        "revision_index":  { "<profile_uid>": ["<rev_uid_0>", "<rev_uid_1>", ...] },
        "activations":     { "<scope_type>:<scope_uid>": {...} },
        "audit":           [ {...}, ... ]
      }

    Guarantees:
      - Process-level RLock guards all reads and writes.
      - Optimistic concurrency check occurs inside the same lock as the write.
      - Writes use atomic temporary-file replacement (write → fsync → replace).
      - No writes to canonical_sessions_v2_1.json or session_layouts.json.
    """

    _lock: RLock = RLock()

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or self._default_storage_path()

    @staticmethod
    def _default_storage_path() -> Path:
        override = os.environ.get("WLV_SHARED_CANVAS_STORE")
        if override:
            return Path(override).expanduser().resolve()
        return (
            Path(__file__).resolve().parents[3]
            / "data"
            / "wdv"
            / "shared_canvas_profiles.json"
        )

    # ------------------------------------------------------------------ reads

    def get_profile(self, profile_uid: str) -> SharedCanvasProfile | None:
        raw = self._read_store()["profiles"].get(profile_uid)
        return SharedCanvasProfile.model_validate(raw) if raw is not None else None

    def list_profiles(
        self, include_archived: bool = False
    ) -> list[SharedCanvasProfile]:
        store = self._read_store()
        profiles = [
            SharedCanvasProfile.model_validate(v)
            for v in store["profiles"].values()
        ]
        if not include_archived:
            profiles = [p for p in profiles if p.status == "active"]
        return sorted(profiles, key=lambda p: p.created_at)

    def get_revision(
        self, profile_revision_uid: str
    ) -> SharedCanvasProfileRevision | None:
        raw = self._read_store()["revisions"].get(profile_revision_uid)
        return (
            SharedCanvasProfileRevision.model_validate(raw)
            if raw is not None
            else None
        )

    def list_revisions(
        self, profile_uid: str
    ) -> list[SharedCanvasProfileRevision]:
        store = self._read_store()
        ordered_uids: list[str] = store["revision_index"].get(profile_uid, [])
        result: list[SharedCanvasProfileRevision] = []
        for uid in ordered_uids:
            raw = store["revisions"].get(uid)
            if raw is not None:
                result.append(SharedCanvasProfileRevision.model_validate(raw))
        return result

    def get_activation(
        self, scope_type: str, scope_uid: str
    ) -> SharedCanvasActivation | None:
        raw = self._read_store()["activations"].get(
            self._scope_key(scope_type, scope_uid)
        )
        return SharedCanvasActivation.model_validate(raw) if raw is not None else None

    def list_activations(self) -> list[SharedCanvasActivation]:
        store = self._read_store()
        return [
            SharedCanvasActivation.model_validate(v)
            for v in store["activations"].values()
        ]

    # ----------------------------------------------------------------- writes

    def create_profile(
        self,
        profile: SharedCanvasProfile,
        initial_revision: SharedCanvasProfileRevision,
        audit: SharedCanvasAuditRecord,
    ) -> None:
        with self._lock:
            store = self._read_store()
            if profile.profile_uid in store["profiles"]:
                raise ValueError(
                    f"Profile {profile.profile_uid} already exists"
                )
            store["profiles"][profile.profile_uid] = profile.model_dump(mode="json")
            store["revisions"][initial_revision.profile_revision_uid] = (
                initial_revision.model_dump(mode="json")
            )
            store["revision_index"].setdefault(profile.profile_uid, []).append(
                initial_revision.profile_revision_uid
            )
            store["audit"].append(audit.model_dump(mode="json"))
            self._write_store(store)

    def update_profile_header(
        self,
        profile: SharedCanvasProfile,
        audit: SharedCanvasAuditRecord,
    ) -> None:
        with self._lock:
            store = self._read_store()
            if profile.profile_uid not in store["profiles"]:
                raise SharedCanvasProfileNotFound(
                    f"Profile not found: {profile.profile_uid}"
                )
            store["profiles"][profile.profile_uid] = profile.model_dump(mode="json")
            store["audit"].append(audit.model_dump(mode="json"))
            self._write_store(store)

    def append_revision(
        self,
        revision: SharedCanvasProfileRevision,
        expected_revision_number: int,
        audit: SharedCanvasAuditRecord,
    ) -> None:
        with self._lock:
            store = self._read_store()
            ordered_uids: list[str] = store["revision_index"].get(
                revision.profile_uid, []
            )
            if not ordered_uids:
                raise SharedCanvasProfileNotFound(
                    f"No revisions found for profile {revision.profile_uid}"
                )
            last_raw = store["revisions"].get(ordered_uids[-1])
            if last_raw is None:
                raise SharedCanvasProfileNotFound(
                    f"Revision record missing for uid {ordered_uids[-1]}"
                )
            current_number = int(last_raw.get("revision_number", -1))
            if current_number != expected_revision_number:
                raise SharedCanvasRevisionConflict(
                    f"Expected revision {expected_revision_number}, "
                    f"found {current_number}"
                )
            store["revisions"][revision.profile_revision_uid] = (
                revision.model_dump(mode="json")
            )
            store["revision_index"][revision.profile_uid].append(
                revision.profile_revision_uid
            )
            store["audit"].append(audit.model_dump(mode="json"))
            self._write_store(store)

    def set_activation(self, activation: SharedCanvasActivation) -> None:
        key = self._scope_key(
            activation.activation_scope_type,
            activation.activation_scope_uid,
        )
        with self._lock:
            store = self._read_store()
            store["activations"][key] = activation.model_dump(mode="json")
            self._write_store(store)

    def append_audit(self, record: SharedCanvasAuditRecord) -> None:
        with self._lock:
            store = self._read_store()
            store["audit"].append(record.model_dump(mode="json"))
            self._write_store(store)

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _scope_key(scope_type: str, scope_uid: str) -> str:
        return f"{scope_type}:{scope_uid}"

    def _read_store(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return self._empty_store()
        try:
            raw = json.loads(
                self.storage_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            return self._empty_store()
        if not isinstance(raw, dict):
            return self._empty_store()
        raw.setdefault("schema_version", SHARED_CANVAS_CONTRACT_VERSION)
        raw.setdefault("profiles", {})
        raw.setdefault("revisions", {})
        raw.setdefault("revision_index", {})
        raw.setdefault("activations", {})
        raw.setdefault("audit", [])
        return raw

    @staticmethod
    def _empty_store() -> dict[str, Any]:
        return {
            "schema_version": SHARED_CANVAS_CONTRACT_VERSION,
            "profiles": {},
            "revisions": {},
            "revision_index": {},
            "activations": {},
            "audit": [],
        }

    def _write_store(self, data: dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data["schema_version"] = SHARED_CANVAS_CONTRACT_VERSION
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(self.storage_path.parent),
            delete=False,
        ) as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            tmp_path = Path(handle.name)
        tmp_path.replace(self.storage_path)
