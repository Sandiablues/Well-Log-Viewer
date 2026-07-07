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


def wdv_curve_counts(record: ManagedWellRecord) -> tuple[int, int, int]:
    loaded_ids = [
        item.product_id
        for group in record.product_groups
        for item in group.items
        if item.wdv_state == ManagedWdvState.LOADED_TO_WDV
    ]
    loaded_set = set(loaded_ids)
    session = record.metadata.get("wdv_load_session_contract") if isinstance(record.metadata, dict) else None
    raw_items = session.get("loaded_curve_items", []) if isinstance(session, dict) else []
    viewer_items = [
        item for item in raw_items
        if isinstance(item, dict) and str(item.get("product_id") or "") in loaded_set
    ]
    viewer_count = len(viewer_items)
    displayable_count = sum(1 for item in viewer_items if item.get("is_renderable") is True)
    if not viewer_items and loaded_ids:
        viewer_count = len(loaded_ids)
        displayable_count = len(loaded_ids)
    return len(loaded_ids), viewer_count, displayable_count


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

    def set_common_depth_unit(self, common_depth_unit: str) -> WdvWorkspaceStateResponse:
        unit = str(common_depth_unit).strip().casefold()
        if unit not in {"m", "ft"}:
            raise ValueError("Common Depth Unit must be m or ft.")
        records = self.repository.list_records()
        return self.reconcile(records, preferred_common_depth_unit=unit)

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
        preferred_common_depth_unit: str | None = None,
    ) -> WdvWorkspaceStateResponse:
        records = records if records is not None else self.repository.list_records()
        summaries = [self._summary(record) for record in records if self._loaded_product_ids(record)]
        summaries.sort(key=lambda item: (item.well_name.lower(), item.managed_well_id))
        loaded_ids = [item.managed_well_id for item in summaries]
        loaded_uids = [str(item.managed_well_uid) for item in summaries]
        by_id = {item.managed_well_id: item for item in summaries}
        by_uid = {str(item.managed_well_uid): item for item in summaries}

        with self._lock:
            stored = self._read_store()
            previous_active_uid = str(stored.get("active_managed_well_uid") or "") or None
            previous_active_id = str(stored.get("active_managed_well_id") or "") or None
            stored_common_depth_unit = str(stored.get("common_depth_unit") or "m").casefold()
            if stored_common_depth_unit not in {"m", "ft"}:
                stored_common_depth_unit = "m"
            common_depth_unit = preferred_common_depth_unit or stored_common_depth_unit

            preferred_summary = by_uid.get(str(preferred_active or "")) or by_id.get(str(preferred_active or ""))
            previous_summary = by_uid.get(str(previous_active_uid or "")) or by_id.get(str(previous_active_id or ""))
            active_summary = preferred_summary or previous_summary or (summaries[0] if summaries else None)
            active_id = active_summary.managed_well_id if active_summary else None
            active_uid = active_summary.managed_well_uid if active_summary else None

            previous_loaded_ids = stored.get("loaded_managed_well_ids", [])
            previous_loaded_uids = stored.get("loaded_managed_well_uids", [])
            changed = (
                active_id != previous_active_id
                or str(active_uid or "") != str(previous_active_uid or "")
                or loaded_ids != previous_loaded_ids
                or loaded_uids != previous_loaded_uids
                or common_depth_unit != stored_common_depth_unit
                or stored.get("schema_version") != WDV_WORKSPACE_CONTRACT_VERSION
            )
            revision = int(stored.get("revision", 0) or 0) + (1 if changed else 0)
            updated_at = utc_now_iso() if changed else str(stored.get("updated_at") or utc_now_iso())

            data = {
                "schema_version": WDV_WORKSPACE_CONTRACT_VERSION,
                "workspace_id": "default",
                "revision": revision,
                "active_managed_well_id": active_id,
                "active_managed_well_uid": str(active_uid) if active_uid else None,
                "common_depth_unit": common_depth_unit,
                "loaded_managed_well_ids": loaded_ids,
                "loaded_managed_well_uids": loaded_uids,
                "updated_at": updated_at,
            }
            self._write_store(data)

        return WdvWorkspaceStateResponse(
            workspace_id="default",
            revision=revision,
            active_managed_well_id=active_id,
            active_managed_well_uid=active_uid,
            common_depth_unit=common_depth_unit,
            loaded_wells=summaries,
            active_aoi=stored.get("active_aoi") if isinstance(stored.get("active_aoi"), dict) else None,
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
        if record.managed_well_uid is None:
            raise ValueError(
                f"Loaded WDV well is missing canonical managed_well_uid: {record.managed_well_id}"
            )
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
                "active_managed_well_uid": None,
                "common_depth_unit": "m",
                "loaded_managed_well_ids": [],
                "loaded_managed_well_uids": [],
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
                "active_managed_well_uid": None,
                "common_depth_unit": "m",
                "loaded_managed_well_ids": [],
                "loaded_managed_well_uids": [],
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
