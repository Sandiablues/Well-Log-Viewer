"""KR-5 Managed Knowledge Repository persistent storage layer.

Owns:
  - Storage path resolution (backend/data/knowledge/managed_knowledge.json)
  - Load from disk (handles missing, empty, and malformed JSON)
  - Serialize managed records and evidence to JSON-serialisable dicts
  - Deserialize dicts back into typed dataclass instances
  - Atomic save (write to .tmp then os.replace)
  - Storage health summary

Only managed/dynamic knowledge state is persisted — never copied seed
constants.  Seed records are re-derived from the seed layer at startup;
managed records are loaded from this storage and merged by the repository.

Storage document shape::

    {
        "storage_schema_version": "wlv-managed-kr-1",
        "kr_version": "kr-5",
        "updated_at": "<ISO-8601 UTC>",
        "records": [ ... ],
        "evidence_records": [ ... ]
    }
"""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .governance import GovernanceStatus
from .managed_models import (
    AliasRecord,
    ClassificationRuleRecord,
    CurveDefinitionRecord,
    DisplayRuleRecord,
    EvidenceRecord,
    TemplateRuleRecord,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STORAGE_SCHEMA_VERSION = "wlv-managed-kr-1"
KR5_VERSION = "kr-5"

# Default path: backend/data/knowledge/managed_knowledge.json
# __file__ = backend/app/knowledge/managed_storage.py
_BACKEND_DIR = Path(__file__).parent.parent.parent
DEFAULT_STORAGE_PATH: Path = (
    _BACKEND_DIR / "data" / "knowledge" / "managed_knowledge.json"
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ManagedStorageError(Exception):
    """Raised for unrecoverable storage failures (malformed JSON, etc.)."""


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _convert_for_json(obj: Any) -> Any:
    """Recursively convert datetime and GovernanceStatus for JSON serialisation."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, GovernanceStatus):
        return obj.value
    if isinstance(obj, list):
        return [_convert_for_json(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _convert_for_json(v) for k, v in obj.items()}
    return obj


def serialize_record(record: Any) -> dict[str, Any]:
    """Convert a managed record dataclass to a JSON-serialisable dict."""
    raw = dataclasses.asdict(record)
    return {k: _convert_for_json(v) for k, v in raw.items()}


def deserialize_record(data: dict[str, Any]) -> Any:
    """Reconstruct a managed record dataclass from a stored dict.

    Raises:
        ManagedStorageError: if record_type is unknown or data is malformed.
    """
    try:
        data = dict(data)  # shallow copy so we don't mutate caller's dict
        record_type = data.get("record_type", "")

        # Parse GovernanceStatus
        if "status" in data and data["status"] is not None:
            try:
                data["status"] = GovernanceStatus(data["status"])
            except ValueError as exc:
                raise ManagedStorageError(
                    f"Unknown governance status {data['status']!r}: {exc}"
                ) from exc

        # Parse datetime fields
        _DATETIME_FIELDS = (
            "created_at",
            "updated_at",
            "approved_at",
            "deprecated_at",
        )
        for field_name in _DATETIME_FIELDS:
            if field_name in data and data[field_name] is not None:
                try:
                    data[field_name] = datetime.fromisoformat(data[field_name])
                except (ValueError, TypeError) as exc:
                    raise ManagedStorageError(
                        f"Invalid datetime for {field_name!r}: {data[field_name]!r}: {exc}"
                    ) from exc

        if record_type == "curve_definition":
            return CurveDefinitionRecord(**data)
        elif record_type == "alias":
            return AliasRecord(**data)
        elif record_type == "display_rule":
            return DisplayRuleRecord(**data)
        elif record_type == "classification_rule":
            return ClassificationRuleRecord(**data)
        elif record_type == "template_rule":
            return TemplateRuleRecord(**data)
        else:
            raise ManagedStorageError(
                f"Unknown record_type {record_type!r} in storage"
            )
    except ManagedStorageError:
        raise
    except Exception as exc:
        raise ManagedStorageError(
            f"Failed to deserialise record: {exc}"
        ) from exc


def deserialize_evidence(data: dict[str, Any]) -> EvidenceRecord:
    """Reconstruct an EvidenceRecord from a stored dict."""
    try:
        data = dict(data)
        if "created_at" in data and data["created_at"] is not None:
            try:
                data["created_at"] = datetime.fromisoformat(data["created_at"])
            except (ValueError, TypeError) as exc:
                raise ManagedStorageError(
                    f"Invalid datetime for created_at: {data['created_at']!r}: {exc}"
                ) from exc
        return EvidenceRecord(**data)
    except ManagedStorageError:
        raise
    except Exception as exc:
        raise ManagedStorageError(
            f"Failed to deserialise evidence record: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# ManagedStorage
# ---------------------------------------------------------------------------


class ManagedStorage:
    """File-backed JSON storage for managed KR records.

    Usage::

        storage = ManagedStorage()  # uses DEFAULT_STORAGE_PATH
        storage = ManagedStorage(path=Path("/tmp/test_kr.json"))  # test isolation

    Load returns empty lists if the file does not exist or is empty.
    Save uses an atomic temp-file replace so partial writes never corrupt
    the storage file.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path if path is not None else DEFAULT_STORAGE_PATH

    @property
    def path(self) -> Path:
        """Resolved storage path."""
        return self._path

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self) -> tuple[list[Any], list[EvidenceRecord]]:
        """Load persisted managed records and evidence from disk.

        Returns:
            Tuple of (governed_records, evidence_records).
            Both lists are empty if the file does not exist or is empty.

        Raises:
            ManagedStorageError: if the file exists but contains malformed JSON
                or an invalid document structure.
        """
        if not self._path.exists():
            return [], []

        raw_text = self._path.read_text(encoding="utf-8")
        if not raw_text.strip():
            return [], []

        try:
            doc = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ManagedStorageError(
                f"Malformed storage JSON at {self._path}: {exc}"
            ) from exc

        if not isinstance(doc, dict):
            raise ManagedStorageError(
                f"Storage file must contain a JSON object, got {type(doc).__name__}"
            )

        raw_records = doc.get("records", [])
        raw_evidence = doc.get("evidence_records", [])

        if not isinstance(raw_records, list):
            raise ManagedStorageError("Storage 'records' field must be a JSON array")
        if not isinstance(raw_evidence, list):
            raise ManagedStorageError(
                "Storage 'evidence_records' field must be a JSON array"
            )

        records = [deserialize_record(r) for r in raw_records]
        evidence = [deserialize_evidence(e) for e in raw_evidence]

        return records, evidence

    # ------------------------------------------------------------------
    # Save (atomic)
    # ------------------------------------------------------------------

    def save(self, records: list[Any], evidence_records: list[EvidenceRecord]) -> None:
        """Atomically persist managed records and evidence to disk.

        Uses a temporary file + os.replace to ensure the storage file is
        never left in a partially-written state.

        Args:
            records:         List of governed record dataclass instances.
            evidence_records: List of EvidenceRecord instances.
        """
        doc: dict[str, Any] = {
            "storage_schema_version": STORAGE_SCHEMA_VERSION,
            "kr_version": KR5_VERSION,
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            "records": [serialize_record(r) for r in records],
            "evidence_records": [serialize_record(e) for e in evidence_records],
        }

        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        os.replace(tmp_path, self._path)  # atomic on POSIX and Windows

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Return storage health information.

        Attempts to load and count persisted records.  Returns a safe
        summary even when the storage file does not exist yet.

        Returns:
            Dict suitable for the /managed/storage/health endpoint.
        """
        storage_exists = self._path.exists()
        persisted_record_count = 0
        persisted_evidence_count = 0

        if storage_exists:
            try:
                records, evidence = self.load()
                persisted_record_count = len(records)
                persisted_evidence_count = len(evidence)
            except ManagedStorageError:
                pass  # health stays at 0 counts; caller can surface error separately

        return {
            "kr_version": KR5_VERSION,
            "storage_enabled": True,
            "storage_path": str(self._path),
            "storage_schema_version": STORAGE_SCHEMA_VERSION,
            "persisted_record_count": persisted_record_count,
            "persisted_evidence_record_count": persisted_evidence_count,
        }
