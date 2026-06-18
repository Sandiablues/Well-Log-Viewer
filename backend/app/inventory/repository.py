"""Managed Well Inventory repository.

This repository is intentionally small but durable. It owns local JSON
persistence behind a replaceable contract so the same service/API can later move
to SQLite, Postgres, or enterprise object/catalog storage.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import ValidationError

from .models import ManagedInventorySnapshot, ManagedWellRecord, utc_now_iso


class ManagedWellNotFoundError(KeyError):
    """Raised when an inventory record cannot be found."""


class ManagedInventoryStoreError(RuntimeError):
    """Raised when the local inventory store cannot be read or validated."""


class ManagedWellInventoryRepository:
    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or self.default_storage_path()

    @staticmethod
    def default_storage_path() -> Path:
        configured = os.environ.get("WLV_MANAGED_INVENTORY_PATH")
        if configured:
            return Path(configured).expanduser().resolve()
        backend_root = Path(__file__).resolve().parents[2]
        return backend_root / "data" / "managed_inventory" / "managed_wells.json"

    def health(self) -> dict[str, str]:
        return {
            "storage_backend": "local_json",
            "storage_path": str(self.storage_path),
        }

    def snapshot(self) -> ManagedInventorySnapshot:
        return self._read_snapshot()

    def list_records(self) -> list[ManagedWellRecord]:
        return self._read_snapshot().records

    def get_record(self, managed_well_id: str) -> ManagedWellRecord:
        for record in self.list_records():
            if record.managed_well_id == managed_well_id:
                return record
        raise ManagedWellNotFoundError(managed_well_id)

    def upsert_record(self, record: ManagedWellRecord) -> tuple[str, ManagedWellRecord]:
        snapshot = self._read_snapshot()
        action = "created"
        records: list[ManagedWellRecord] = []
        replaced = False
        for existing in snapshot.records:
            if existing.managed_well_id == record.managed_well_id:
                records.append(record)
                replaced = True
                action = "updated"
            else:
                records.append(existing)
        if not replaced:
            records.append(record)
        self._write_snapshot(
            snapshot.model_copy(
                update={
                    "records": records,
                    "updated_at": utc_now_iso(),
                }
            )
        )
        return action, record

    def write_snapshot(self, snapshot: ManagedInventorySnapshot) -> None:
        self._write_snapshot(snapshot)

    def _read_snapshot(self) -> ManagedInventorySnapshot:
        if not self.storage_path.exists():
            return ManagedInventorySnapshot()
        try:
            with self.storage_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return ManagedInventorySnapshot.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise ManagedInventoryStoreError(f"Invalid managed inventory store: {self.storage_path}") from exc

    def _write_snapshot(self, snapshot: ManagedInventorySnapshot) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = snapshot.model_dump(mode="json")
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(self.storage_path.parent),
            delete=False,
        ) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            tmp_name = handle.name
        Path(tmp_name).replace(self.storage_path)
