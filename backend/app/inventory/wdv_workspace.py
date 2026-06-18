"""Backend-owned multi-well WDV workspace state.

The managed inventory owns which products are loaded. This service owns the
workspace-level active-well selection and exposes an aggregate contract for all
loaded wells. Local JSON is only a storage profile; callers depend on the
service/API boundary.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

from .models import (
    ManagedWdvState,
    ManagedWellRecord,
    WDV_WORKSPACE_CONTRACT_VERSION,
    WdvWorkspaceLoadedWellSummary,
    WdvWorkspaceStateResponse,
    utc_now_iso,
)
from .repository import ManagedWellInventoryRepository, ManagedWellNotFoundError
from .wdv_viewer_package import summarize_wdv_viewer_package


def wdv_curve_counts(record: ManagedWellRecord) -> tuple[int, int, int]:
    loaded_ids = [
        item.product_id
        for group in record.product_groups
        for item in group.items
        if item.wdv_state == ManagedWdvState.LOADED_TO_WDV
    ]
    package = record.metadata.get("wdv_load_session_contract") if isinstance(record.metadata, dict) else None
    return summarize_wdv_viewer_package(
        package if isinstance(package, dict) else None,
        loaded_ids,
    )


class WdvWorkspaceService:
    _lock = RLock()

    def __init__(
        self,
        repository: ManagedWellInventoryRepository,
        storage_path: Path | None = None,
    ) -> None:
        self.repository = repository
        self.storage_path = storage_path or repository.storage_path.with_name("wdv_workspace.json")

    def get_workspace(self) -> WdvWorkspaceStateResponse:
        records = self.repository.list_records()
        return self.reconcile(records)

    def set_active_well(self, managed_well_reference: str) -> WdvWorkspaceStateResponse:
        records = self.repository.list_records()
        target = self._resolve_reference(managed_well_reference, records)
        loaded_ids = {record.managed_well_id for record in records if self._loaded_product_ids(record)}
        if target.managed_well_id not in loaded_ids:
            raise ValueError("Active WDV well must already be loaded into the WDV workspace.")
        return self.reconcile(records, preferred_active=target.managed_well_id)

    def reconcile(
        self,
        records: list[ManagedWellRecord] | None = None,
        preferred_active: str | None = None,
    ) -> WdvWorkspaceStateResponse:
        records = records if records is not None else self.repository.list_records()
        summaries = [self._summary(record) for record in records if self._loaded_product_ids(record)]
        summaries.sort(key=lambda item: (item.well_name.lower(), item.managed_well_id))
        loaded_ids = [item.managed_well_id for item in summaries]

        with self._lock:
            stored = self._read_store()
            previous_active = stored.get("active_managed_well_id")
            if preferred_active in loaded_ids:
                active = preferred_active
            elif previous_active in loaded_ids:
                active = previous_active
            else:
                active = loaded_ids[0] if loaded_ids else None

            previous_loaded_ids = stored.get("loaded_managed_well_ids", [])
            changed = (
                active != previous_active
                or loaded_ids != previous_loaded_ids
            )
            revision = int(stored.get("revision", 0) or 0) + (1 if changed else 0)
            updated_at = utc_now_iso() if changed else str(stored.get("updated_at") or utc_now_iso())

            data = {
                "schema_version": WDV_WORKSPACE_CONTRACT_VERSION,
                "workspace_id": "default",
                "revision": revision,
                "active_managed_well_id": active,
                "loaded_managed_well_ids": loaded_ids,
                "updated_at": updated_at,
            }
            self._write_store(data)

        return WdvWorkspaceStateResponse(
            workspace_id="default",
            revision=revision,
            active_managed_well_id=active,
            loaded_wells=summaries,
            updated_at=updated_at,
        )

    @staticmethod
    def _loaded_product_ids(record: ManagedWellRecord) -> list[str]:
        return [
            item.product_id
            for group in record.product_groups
            for item in group.items
            if item.wdv_state == ManagedWdvState.LOADED_TO_WDV
        ]

    def _summary(self, record: ManagedWellRecord) -> WdvWorkspaceLoadedWellSummary:
        product_ids = self._loaded_product_ids(record)
        loaded_product_count, viewer_curve_count, displayable_curve_count = wdv_curve_counts(record)
        endpoint = (
            f"/api/wlv/inventory/wells/{record.managed_well_id}/viewer-package"
            if product_ids
            else None
        )
        return WdvWorkspaceLoadedWellSummary(
            managed_well_id=record.managed_well_id,
            managed_well_uid=record.managed_well_uid,
            well_name=record.well_name,
            loaded_product_ids=product_ids,
            loaded_product_count=loaded_product_count,
            viewer_curve_count=viewer_curve_count,
            displayable_curve_count=displayable_curve_count,
            loaded_curve_count=displayable_curve_count,
            viewer_package_endpoint=endpoint,
        )

    @staticmethod
    def _resolve_reference(
        reference: str,
        records: list[ManagedWellRecord],
    ) -> ManagedWellRecord:
        for record in records:
            if reference in {
                record.managed_well_id,
                str(record.managed_well_uid or ""),
                record.well_id,
            }:
                return record
        raise ManagedWellNotFoundError(reference)

    def _read_store(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return {
                "schema_version": WDV_WORKSPACE_CONTRACT_VERSION,
                "workspace_id": "default",
                "revision": 0,
                "active_managed_well_id": None,
                "loaded_managed_well_ids": [],
                "updated_at": utc_now_iso(),
            }
        try:
            raw = json.loads(self.storage_path.read_text())
        except (OSError, json.JSONDecodeError):
            return {
                "schema_version": WDV_WORKSPACE_CONTRACT_VERSION,
                "workspace_id": "default",
                "revision": 0,
                "active_managed_well_id": None,
                "loaded_managed_well_ids": [],
                "updated_at": utc_now_iso(),
            }
        return raw if isinstance(raw, dict) else {}

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
            tmp_name = handle.name
        Path(tmp_name).replace(self.storage_path)
