"""Per-well canvas binding repository interface and local JSON adapter.

The abstract base class defines the storage contract.
LocalJsonWellCanvasBindingRepository provides the desktop adapter.

The binding service depends only on WellCanvasBindingRepository.
No service code calls JSON or file paths directly.

Writes exclusively to well_canvas_bindings.json.
Never writes to canonical_sessions_v2_1.json or session_layouts.json.
"""

from __future__ import annotations

import json
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from threading import RLock
from typing import Any

from .binding_models import (
    WELL_CANVAS_BINDING_CONTRACT_VERSION,
    WellCanvasBinding,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class WellCanvasBindingRevisionConflict(ValueError):
    """Optimistic concurrency conflict on binding update."""


class WellCanvasBindingNotFound(KeyError):
    """Requested binding does not exist in the repository."""


# ---------------------------------------------------------------------------
# Abstract repository contract
# ---------------------------------------------------------------------------

class WellCanvasBindingRepository(ABC):
    """Storage-independent contract for per-well canvas binding persistence.

    All write operations must be atomic within the storage backend.
    update_binding must check the optimistic concurrency revision inside
    the same atomic operation as the write.
    """

    @abstractmethod
    def create_binding(self, binding: WellCanvasBinding) -> None:
        """Persist a new binding overlay atomically."""

    @abstractmethod
    def get_binding(self, binding_uid: str) -> WellCanvasBinding | None:
        """Return a binding by UID or None."""

    @abstractmethod
    def get_binding_for_well_and_revision(
        self,
        managed_well_uid: str,
        profile_revision_uid: str,
    ) -> WellCanvasBinding | None:
        """Return the binding for a specific (well, profile revision) pair or None."""

    @abstractmethod
    def list_bindings_for_well(
        self, managed_well_uid: str
    ) -> list[WellCanvasBinding]:
        """Return all bindings for a well, any revision."""

    @abstractmethod
    def list_bindings_for_revision(
        self, profile_revision_uid: str
    ) -> list[WellCanvasBinding]:
        """Return all bindings for a profile revision, any well."""

    @abstractmethod
    def update_binding(
        self,
        binding: WellCanvasBinding,
        expected_revision: int,
    ) -> None:
        """Replace a binding atomically.

        Raises WellCanvasBindingRevisionConflict if the stored revision
        does not equal expected_revision.
        """


# ---------------------------------------------------------------------------
# Local JSON adapter
# ---------------------------------------------------------------------------

class LocalJsonWellCanvasBindingRepository(WellCanvasBindingRepository):
    """Desktop-grade JSON adapter for well canvas binding persistence.

    Storage layout (well_canvas_bindings.json):
      {
        "schema_version": "well_canvas_bindings_v1",
        "bindings":        { "<binding_uid>": { ...WellCanvasBinding... } },
        "well_index":      { "<managed_well_uid>": ["<binding_uid>", ...] },
        "revision_index":  { "<profile_revision_uid>": ["<binding_uid>", ...] }
      }

    Guarantees:
      - Process-level RLock guards all reads and writes.
      - Optimistic concurrency check occurs inside the same lock as the write.
      - Writes use atomic temporary-file replacement.
      - Never writes to canonical_sessions_v2_1.json or session_layouts.json.
    """

    _lock: RLock = RLock()

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or self._default_storage_path()

    @staticmethod
    def _default_storage_path() -> Path:
        override = os.environ.get("WLV_WELL_CANVAS_BINDINGS_STORE")
        if override:
            return Path(override).expanduser().resolve()
        return (
            Path(__file__).resolve().parents[3]
            / "data"
            / "wdv"
            / "well_canvas_bindings.json"
        )

    # ------------------------------------------------------------------ reads

    def get_binding(self, binding_uid: str) -> WellCanvasBinding | None:
        raw = self._read_store()["bindings"].get(binding_uid)
        return WellCanvasBinding.model_validate(raw) if raw is not None else None

    def get_binding_for_well_and_revision(
        self,
        managed_well_uid: str,
        profile_revision_uid: str,
    ) -> WellCanvasBinding | None:
        store = self._read_store()
        for uid in store["well_index"].get(managed_well_uid, []):
            raw = store["bindings"].get(uid)
            if raw and raw.get("profile_revision_uid") == profile_revision_uid:
                return WellCanvasBinding.model_validate(raw)
        return None

    def list_bindings_for_well(
        self, managed_well_uid: str
    ) -> list[WellCanvasBinding]:
        store = self._read_store()
        result: list[WellCanvasBinding] = []
        for uid in store["well_index"].get(managed_well_uid, []):
            raw = store["bindings"].get(uid)
            if raw:
                result.append(WellCanvasBinding.model_validate(raw))
        return result

    def list_bindings_for_revision(
        self, profile_revision_uid: str
    ) -> list[WellCanvasBinding]:
        store = self._read_store()
        result: list[WellCanvasBinding] = []
        for uid in store["revision_index"].get(profile_revision_uid, []):
            raw = store["bindings"].get(uid)
            if raw:
                result.append(WellCanvasBinding.model_validate(raw))
        return result

    # ----------------------------------------------------------------- writes

    def create_binding(self, binding: WellCanvasBinding) -> None:
        with self._lock:
            store = self._read_store()
            if binding.binding_uid in store["bindings"]:
                raise ValueError(
                    f"Binding {binding.binding_uid} already exists"
                )
            store["bindings"][binding.binding_uid] = binding.model_dump(mode="json")
            store["well_index"].setdefault(
                binding.managed_well_uid, []
            ).append(binding.binding_uid)
            store["revision_index"].setdefault(
                binding.profile_revision_uid, []
            ).append(binding.binding_uid)
            self._write_store(store)

    def update_binding(
        self,
        binding: WellCanvasBinding,
        expected_revision: int,
    ) -> None:
        with self._lock:
            store = self._read_store()
            current_raw = store["bindings"].get(binding.binding_uid)
            if current_raw is None:
                raise WellCanvasBindingNotFound(
                    f"Binding not found: {binding.binding_uid}"
                )
            stored_revision = int(current_raw.get("revision", 0))
            if stored_revision != expected_revision:
                raise WellCanvasBindingRevisionConflict(
                    f"Expected revision {expected_revision}, "
                    f"found {stored_revision}"
                )
            store["bindings"][binding.binding_uid] = binding.model_dump(mode="json")
            self._write_store(store)

    # ---------------------------------------------------------------- helpers

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
        raw.setdefault("schema_version", WELL_CANVAS_BINDING_CONTRACT_VERSION)
        raw.setdefault("bindings", {})
        raw.setdefault("well_index", {})
        raw.setdefault("revision_index", {})
        return raw

    @staticmethod
    def _empty_store() -> dict[str, Any]:
        return {
            "schema_version": WELL_CANVAS_BINDING_CONTRACT_VERSION,
            "bindings": {},
            "well_index": {},
            "revision_index": {},
        }

    def _write_store(self, data: dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data["schema_version"] = WELL_CANVAS_BINDING_CONTRACT_VERSION
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
