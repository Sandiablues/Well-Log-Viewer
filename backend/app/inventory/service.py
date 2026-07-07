"""Managed Well Inventory service boundary."""

from __future__ import annotations

from collections import Counter
import hashlib
import math
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from app.wells.models import Curve, WellMultitrackV1
from app.identity import new_uuid7_str
from app.wells.seed_repository import SeedWellRepository
from app.classification.well_log_classifier import classify_well_log_curve
from app.classification.well_log_vocabulary import PRODUCT_GROUP_ORDER
from app.knowledge.curve_knowledge import normalize_viewer_package_for_wdv

from app.wdv_display.policy_service import WdvCurveDisplayPolicyService
from .models import (
    InventoryValidationSeverity,
    ManagedInventoryHealth,
    ManagedInventoryLifecycleState,
    ManagedInventoryMaintenanceStatus,
    ManagedInventoryStatus,
    ManagedInventorySnapshot,
    ManagedInventoryValidationIssue,
    ManagedInventoryValidationResult,
    LoadManagedWellToWdvResponse,
    WmdDownstreamRecoveryStatus,
    ExecuteWmdCleanupResponse,
    RebuildWmdPayloadResponse,
    RebuildWmdPayloadResult,
    ExecuteWmdCleanupResult,
    LoadManagedWellToWdvResult,
    BulkLoadWdvWorkspaceResponse,
    BulkLoadWdvWellResult,
    BulkLoadWdvWellSelection,
    BulkUnloadWdvWorkspaceResponse,
    BulkUnloadWdvWellResult,
    UnloadManagedWellFromWdvResponse,
    UnloadManagedWellFromWdvResult,
    RemoveManagedDataFromMdpResponse,
    RemoveManagedDataFromMdpResult,
    RestoreManagedDataToMdpResponse,
    RestoreManagedDataToMdpResult,
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
    ManagedWdvState,
    ManagedWmdpState,
    RegisterSeedWellResponse,
    ViewerPackageReference,
    WmdReferenceType,
    WmdRetentionState,
    WmdSourceRecoveryState,
    WmdWorkingState,
    WdvWorkspaceStateResponse,
    utc_now_iso,
)
from .repository import ManagedWellInventoryRepository, ManagedWellNotFoundError
from .curve_sample_service import CurveSampleService, CurveSampleServiceError
from .identity_reconciliation import reconcile_managed_record_identity
from .wdv_workspace import WdvWorkspaceService, wdv_curve_counts
from .wmd_lifecycle_service import WmdLifecycleService


class ManagedWellInventoryService:
    def __init__(
        self,
        repository: ManagedWellInventoryRepository | None = None,
        seed_repository: SeedWellRepository | None = None,
        workspace_service: WdvWorkspaceService | None = None,
        source_intake_service: Any | None = None,
    ) -> None:
        use_default_source_intake = repository is None
        self.repository = repository or ManagedWellInventoryRepository()
        self.seed_repository = seed_repository or SeedWellRepository()
        self.curve_sample_service = CurveSampleService(repository=self.repository)
        self.workspace_service = workspace_service or WdvWorkspaceService(repository=self.repository)
        self.wmd_lifecycle_service = WmdLifecycleService()
        self._source_intake_service = source_intake_service
        self._use_default_source_intake = use_default_source_intake

    def _source_intake_reference_service(self) -> Any | None:
        if self._source_intake_service is not None:
            return self._source_intake_service
        if not self._use_default_source_intake:
            return None
        from app.source_intake.service import WlvSourceIntakeService

        self._source_intake_service = WlvSourceIntakeService()
        return self._source_intake_service

    def _sync_source_intake_reference_state(self, record: ManagedWellRecord) -> None:
        service = self._source_intake_reference_service()
        if service is not None:
            service.synchronize_managed_well_reference_state(record)

    def _sync_source_intake_reference_states(self, records: list[ManagedWellRecord]) -> None:
        for record in records:
            self._sync_source_intake_reference_state(record)

    def _acquire_wmd_reference(self, record: ManagedWellRecord) -> None:
        self.wmd_lifecycle_service.acquire_reference(
            record, WmdReferenceType.WMD, record.managed_well_id, "available_in_wmd"
        )
        for group in record.product_groups:
            for item in group.items:
                if item.wmdp_state != ManagedWmdpState.REMOVED_FROM_WMDP:
                    self.wmd_lifecycle_service.acquire_reference(
                        item, WmdReferenceType.WMD, record.managed_well_id, "available_in_wmd"
                    )

    def _release_wmd_reference(self, record: ManagedWellRecord, product_ids: set[str] | None = None) -> None:
        if product_ids is None:
            self.wmd_lifecycle_service.release_reference(
                record, WmdReferenceType.WMD, record.managed_well_id
            )
        for group in record.product_groups:
            for item in group.items:
                if product_ids is None or item.product_id in product_ids:
                    self.wmd_lifecycle_service.release_reference(
                        item, WmdReferenceType.WMD, record.managed_well_id
                    )

    def _acquire_wdv_reference(self, record: ManagedWellRecord, product_ids: set[str]) -> None:
        owner_id = f"wdv-workspace:{record.managed_well_id}"
        self.wmd_lifecycle_service.acquire_reference(
            record, WmdReferenceType.WDV, owner_id, "loaded_to_wdv"
        )
        for group in record.product_groups:
            for item in group.items:
                if item.product_id in product_ids:
                    self.wmd_lifecycle_service.acquire_reference(
                        item, WmdReferenceType.WDV, owner_id, "loaded_to_wdv"
                    )

    def _release_wdv_reference(self, record: ManagedWellRecord, product_ids: set[str] | None = None) -> None:
        owner_id = f"wdv-workspace:{record.managed_well_id}"
        for group in record.product_groups:
            for item in group.items:
                if product_ids is None or item.product_id in product_ids:
                    self.wmd_lifecycle_service.release_reference(
                        item, WmdReferenceType.WDV, owner_id
                    )
        if not any(
            binding.reference_type == WmdReferenceType.WDV
            for group in record.product_groups
            for item in group.items
            for binding in item.wmd_references
        ):
            self.wmd_lifecycle_service.release_reference(
                record, WmdReferenceType.WDV, owner_id
            )

    def acquire_wmd_consumer_reference(
        self,
        managed_well_id: str,
        reference_type: WmdReferenceType,
        owner_id: str,
        product_ids: list[str] | None = None,
        reason: str | None = None,
    ) -> ManagedWellRecord:
        if reference_type == WmdReferenceType.WMD:
            raise ValueError("Use WMD availability transitions for WMD ownership")
        record = self._resolve_managed_well_reference(
            managed_well_id, self.repository.list_records()
        )
        selected = set(self._resolve_product_references(record, product_ids or []))
        self.wmd_lifecycle_service.acquire_reference(record, reference_type, owner_id, reason)
        for group in record.product_groups:
            for item in group.items:
                if not selected or item.product_id in selected:
                    self.wmd_lifecycle_service.acquire_reference(
                        item, reference_type, owner_id, reason
                    )
        record.updated_at = utc_now_iso()
        record = self.wmd_lifecycle_service.project_record(record)
        _action, saved = self.repository.upsert_record(record)
        return saved

    def release_wmd_consumer_reference(
        self,
        managed_well_id: str,
        reference_type: WmdReferenceType,
        owner_id: str,
        product_ids: list[str] | None = None,
    ) -> ManagedWellRecord:
        record = self._resolve_managed_well_reference(
            managed_well_id, self.repository.list_records()
        )
        selected = set(self._resolve_product_references(record, product_ids or []))
        for group in record.product_groups:
            for item in group.items:
                if not selected or item.product_id in selected:
                    self.wmd_lifecycle_service.release_reference(
                        item, reference_type, owner_id
                    )
        if not any(
            binding.reference_type == reference_type and binding.owner_id == owner_id
            for group in record.product_groups
            for item in group.items
            for binding in item.wmd_references
        ):
            self.wmd_lifecycle_service.release_reference(record, reference_type, owner_id)
        record.updated_at = utc_now_iso()
        record = self.wmd_lifecycle_service.project_record(record)
        _action, saved = self.repository.upsert_record(record)
        return saved


    def _downstream_recovery_status_for_record(
        self,
        record: ManagedWellRecord,
        product_ids: set[str] | None = None,
    ) -> WmdDownstreamRecoveryStatus:
        items = [item for group in record.product_groups for item in group.items]
        if product_ids:
            items = [item for item in items if item.product_id in product_ids]
        blocked = [
            item.product_id
            for item in items
            if item.wmd_source_recovery_state != WmdSourceRecoveryState.AVAILABLE
            or item.wmd_working_state == WmdWorkingState.CLEARED
            or item.wmd_retention_state == WmdRetentionState.CLEARED
        ]
        record_blocked = (
            record.wmd_source_recovery_state != WmdSourceRecoveryState.AVAILABLE
            or record.wmd_working_state == WmdWorkingState.CLEARED
            or record.wmd_retention_state == WmdRetentionState.CLEARED
        )
        allowed = not record_blocked and not blocked
        message = None if allowed else (
            record.wmd_source_recovery_message
            or "Transient WMD payload is unavailable. Restore the original unchanged source and rebuild before downstream use."
        )
        return WmdDownstreamRecoveryStatus(
            managed_well_id=record.managed_well_id,
            source_recovery_state=record.wmd_source_recovery_state,
            payload_available=allowed,
            wdv_load_allowed=allowed,
            wbv_load_allowed=allowed,
            export_allowed=allowed,
            saved_workspace_resume_allowed=allowed,
            blocked_product_ids=blocked,
            recovery_message=message,
        )

    def reconcile_wbv_session_reference(
        self,
        active_managed_well_id: str | None,
        *,
        owner_id: str = "wbv-session:default",
    ) -> ManagedWellRecord | None:
        """Align the single backend-owned WBV session reference with WDV active well.

        WBV does not own an independent durable well selection. The active WDV
        workspace well is the authority. This command releases stale WBV
        references from every other record, validates downstream availability,
        and acquires a WBV reference only for the active well and its currently
        loaded WDV products.
        """
        records = self.repository.list_records()
        active: ManagedWellRecord | None = None
        if active_managed_well_id:
            active = self._resolve_managed_well_reference(active_managed_well_id, records)
            self._require_downstream_payload_available(active)

        saved_active: ManagedWellRecord | None = None
        for record in records:
            changed = False
            is_active = active is not None and record.managed_well_id == active.managed_well_id
            loaded_product_ids = {
                item.product_id
                for group in record.product_groups
                for item in group.items
                if item.wdv_state == ManagedWdvState.LOADED_TO_WDV
            }

            for group in record.product_groups:
                for item in group.items:
                    should_hold = is_active and item.product_id in loaded_product_ids
                    if should_hold:
                        before = len(item.wmd_references)
                        self.wmd_lifecycle_service.acquire_reference(
                            item, WmdReferenceType.WBV, owner_id, "active_wbv_session"
                        )
                        changed = changed or len(item.wmd_references) != before
                    else:
                        changed = self.wmd_lifecycle_service.release_reference(
                            item, WmdReferenceType.WBV, owner_id
                        ) or changed

            if is_active and loaded_product_ids:
                before = len(record.wmd_references)
                self.wmd_lifecycle_service.acquire_reference(
                    record, WmdReferenceType.WBV, owner_id, "active_wbv_session"
                )
                changed = changed or len(record.wmd_references) != before
            else:
                changed = self.wmd_lifecycle_service.release_reference(
                    record, WmdReferenceType.WBV, owner_id
                ) or changed

            if changed:
                record.updated_at = utc_now_iso()
                record = self.wmd_lifecycle_service.project_record(record)
                _action, record = self.repository.upsert_record(record)
            if is_active:
                saved_active = record

        return saved_active

    def reconcile_saved_workspace_references(
        self,
        workspace_uid: str,
        well_product_references: dict[str, list[str] | None],
    ) -> list[ManagedWellRecord]:
        """Reconcile WMD retention for one backend-owned saved workspace.

        The supplied selection is authoritative for this workspace owner. Stale
        bindings are released from every other well/product before requested
        bindings are acquired. Every requested well is checked against the frozen
        WMD downstream-recovery contract, so a saved workspace cannot retain or
        resume stale, cleared, missing, changed, or inaccessible payloads.
        """
        owner_id = str(workspace_uid or "").strip()
        if not owner_id:
            raise ValueError("Saved workspace UUIDv7 owner is required.")

        records = self.repository.list_records()
        requested: dict[str, set[str]] = {}
        for well_reference, product_references in well_product_references.items():
            record = self._resolve_managed_well_reference(well_reference, records)
            selected = set(self._resolve_product_references(record, product_references or []))
            if not selected:
                selected = {
                    item.product_id
                    for group in record.product_groups
                    for item in group.items
                    if item.wdv_state == ManagedWdvState.LOADED_TO_WDV
                }
            self._require_downstream_payload_available(record, selected or None)
            requested[record.managed_well_id] = selected

        saved: list[ManagedWellRecord] = []
        for record in records:
            selected = requested.get(record.managed_well_id, set())
            changed = False
            for group in record.product_groups:
                for item in group.items:
                    should_hold = item.product_id in selected
                    if should_hold:
                        before = len(item.wmd_references)
                        self.wmd_lifecycle_service.acquire_reference(
                            item,
                            WmdReferenceType.SAVED_WORKSPACE,
                            owner_id,
                            "saved_workspace_resume",
                        )
                        changed = changed or len(item.wmd_references) != before
                    else:
                        changed = self.wmd_lifecycle_service.release_reference(
                            item, WmdReferenceType.SAVED_WORKSPACE, owner_id
                        ) or changed

            if selected:
                before = len(record.wmd_references)
                self.wmd_lifecycle_service.acquire_reference(
                    record,
                    WmdReferenceType.SAVED_WORKSPACE,
                    owner_id,
                    "saved_workspace_resume",
                )
                changed = changed or len(record.wmd_references) != before
            else:
                changed = self.wmd_lifecycle_service.release_reference(
                    record, WmdReferenceType.SAVED_WORKSPACE, owner_id
                ) or changed

            if changed:
                record.updated_at = utc_now_iso()
                record = self.wmd_lifecycle_service.project_record(record)
                _action, record = self.repository.upsert_record(record)
            if selected:
                saved.append(record)
        return saved

    def release_saved_workspace_references(
        self, workspace_uid: str
    ) -> list[ManagedWellRecord]:
        """Release all WMD bindings owned by a deleted saved workspace."""
        return self.reconcile_saved_workspace_references(workspace_uid, {})

    def reconcile_export_references(
        self,
        export_uid: str,
        well_product_references: dict[str, list[str] | None],
    ) -> list[ManagedWellRecord]:
        """Acquire exactly the WMD payload references needed by one export job.

        The export UUIDv7 is the owner. Reconciliation is idempotent, rejects
        blocked/cleared payloads before acquisition, and releases stale bindings
        previously owned by the same export.
        """
        owner_id = str(export_uid or "").strip()
        if not owner_id:
            raise ValueError("Export UUIDv7 owner is required.")

        records = self.repository.list_records()
        requested: dict[str, set[str]] = {}
        for well_reference, product_references in well_product_references.items():
            record = self._resolve_managed_well_reference(well_reference, records)
            selected = set(self._resolve_product_references(record, product_references or []))
            if not selected:
                selected = {
                    item.product_id
                    for group in record.product_groups
                    for item in group.items
                    if item.wdv_state == ManagedWdvState.LOADED_TO_WDV
                }
            self._require_downstream_payload_available(record, selected or None)
            requested[record.managed_well_id] = selected

        saved: list[ManagedWellRecord] = []
        for record in records:
            selected = requested.get(record.managed_well_id, set())
            changed = False
            for group in record.product_groups:
                for item in group.items:
                    if item.product_id in selected:
                        before = len(item.wmd_references)
                        self.wmd_lifecycle_service.acquire_reference(
                            item, WmdReferenceType.EXPORT, owner_id, "active_export"
                        )
                        changed = changed or len(item.wmd_references) != before
                    else:
                        changed = self.wmd_lifecycle_service.release_reference(
                            item, WmdReferenceType.EXPORT, owner_id
                        ) or changed

            if selected:
                before = len(record.wmd_references)
                self.wmd_lifecycle_service.acquire_reference(
                    record, WmdReferenceType.EXPORT, owner_id, "active_export"
                )
                changed = changed or len(record.wmd_references) != before
            else:
                changed = self.wmd_lifecycle_service.release_reference(
                    record, WmdReferenceType.EXPORT, owner_id
                ) or changed

            if changed:
                record.updated_at = utc_now_iso()
                record = self.wmd_lifecycle_service.project_record(record)
                _action, record = self.repository.upsert_record(record)
            if selected:
                saved.append(record)
        return saved

    def release_export_references(self, export_uid: str) -> list[ManagedWellRecord]:
        """Release all WMD bindings owned by a completed or failed export job."""
        return self.reconcile_export_references(export_uid, {})

    def reset_viewer_session_references(
        self, *, owner_id: str = "wbv-session:default"
    ) -> list[ManagedWellRecord]:
        """Release transient WBV session bindings without unloading WDV workspace data.

        Page exit and viewer-session reset must not erase the backend-persisted WDV
        workspace. Only the ephemeral WBV session owner is released.
        """
        touched: list[ManagedWellRecord] = []
        for record in self.repository.list_records():
            changed = False
            for group in record.product_groups:
                for item in group.items:
                    changed = self.wmd_lifecycle_service.release_reference(
                        item, WmdReferenceType.WBV, owner_id
                    ) or changed
            changed = self.wmd_lifecycle_service.release_reference(
                record, WmdReferenceType.WBV, owner_id
            ) or changed
            if changed:
                record.updated_at = utc_now_iso()
                record = self.wmd_lifecycle_service.project_record(record)
                _action, record = self.repository.upsert_record(record)
                touched.append(record)
        return touched

    def reconcile_stale_consumer_references(
        self,
        *,
        active_export_owner_ids: set[str],
        active_saved_workspace_owner_ids: set[str],
        active_wbv_owner_ids: set[str],
    ) -> list[ManagedWellRecord]:
        """Release stale transient consumer bindings using backend-authoritative owner sets.

        WMD and WDV bindings are deliberately excluded: WMD availability and the
        persistent WDV workspace have separate lifecycle commands.
        """
        active_by_type = {
            WmdReferenceType.EXPORT: {str(v) for v in active_export_owner_ids},
            WmdReferenceType.SAVED_WORKSPACE: {str(v) for v in active_saved_workspace_owner_ids},
            WmdReferenceType.WBV: {str(v) for v in active_wbv_owner_ids},
        }
        touched: list[ManagedWellRecord] = []
        for record in self.repository.list_records():
            changed = False
            for group in record.product_groups:
                for item in group.items:
                    for binding in list(item.wmd_references):
                        allowed = active_by_type.get(binding.reference_type)
                        if allowed is not None and binding.owner_id not in allowed:
                            changed = self.wmd_lifecycle_service.release_reference(
                                item, binding.reference_type, binding.owner_id
                            ) or changed
            for binding in list(record.wmd_references):
                allowed = active_by_type.get(binding.reference_type)
                if allowed is not None and binding.owner_id not in allowed:
                    changed = self.wmd_lifecycle_service.release_reference(
                        record, binding.reference_type, binding.owner_id
                    ) or changed
            if changed:
                record.updated_at = utc_now_iso()
                record = self.wmd_lifecycle_service.project_record(record)
                _action, record = self.repository.upsert_record(record)
                touched.append(record)
        return touched

    def get_wmd_downstream_recovery_status(
        self, managed_well_id: str, product_ids: list[str] | None = None
    ) -> WmdDownstreamRecoveryStatus:
        record = self._resolve_managed_well_reference(
            managed_well_id, self.repository.list_records()
        )
        selected = set(self._resolve_product_references(record, product_ids or []))
        return self._downstream_recovery_status_for_record(record, selected or None)

    def _require_downstream_payload_available(
        self, record: ManagedWellRecord, product_ids: set[str] | None = None
    ) -> None:
        status = self._downstream_recovery_status_for_record(record, product_ids)
        if not status.payload_available:
            blocked = ", ".join(status.blocked_product_ids) or record.managed_well_id
            raise ValueError(
                f"WMD downstream payload unavailable for {blocked}: {status.recovery_message}"
            )

    def health(self) -> ManagedInventoryHealth:
        return ManagedInventoryHealth()

    def status(self) -> ManagedInventoryStatus:
        snapshot = self.repository.snapshot()
        records = snapshot.records
        return ManagedInventoryStatus(
            ok=True,
            storage_backend="local_json",
            storage_path=str(self.repository.storage_path),
            schema_version=snapshot.schema_version,
            managed_well_count=len(records),
            viewer_package_count=sum(len(record.viewer_packages) for record in records),
            source_reference_count=sum(len(record.source_references) for record in records),
            lifecycle_counts=self._lifecycle_counts(records),
        )

    def maintenance_status(self) -> ManagedInventoryMaintenanceStatus:
        status = self.status()
        return ManagedInventoryMaintenanceStatus(
            ok=True,
            storage_backend=status.storage_backend,
            storage_path=status.storage_path,
            managed_well_count=status.managed_well_count,
            lifecycle_counts=status.lifecycle_counts,
            notes=[
                "Non-destructive maintenance status only.",
                "Use inventory validation before future destructive lifecycle actions are enabled.",
                "Local JSON storage is isolated behind the repository boundary for later DB/object-storage migration.",
            ],
        )

    def backfill_inventory_identity_contract(self, *, dry_run: bool = False) -> dict[str, Any]:
        """Backfill non-identity curve metadata on managed inventory records.

        This is a backend-owned inventory maintenance operation. It does not
        change WDV track assignments, preset behavior, or frontend state. It
        only ensures existing managed curve rows carry the identity fields
        introduced by the UID contract.
        """
        snapshot = self.repository.snapshot()
        normalized_records: list[ManagedWellRecord] = []
        changed_product_ids: list[str] = []

        for record in snapshot.records:
            prepared = self._with_product_groups(record)
            normalized = self._with_inventory_identity_contract(prepared)
            normalized_records.append(normalized)

            before_items = {
                item.product_id: item
                for group in prepared.product_groups
                for item in group.items
            }
            for group in normalized.product_groups:
                for item in group.items:
                    before = before_items.get(item.product_id)
                    if before is None:
                        changed_product_ids.append(item.product_id)
                        continue
                    if (
                        before.curve_uid != item.curve_uid
                        or before.well_uid != item.well_uid
                        or before.source_uid != item.source_uid
                        or before.observed_mnemonic != item.observed_mnemonic
                        or before.normalized_mnemonic != item.normalized_mnemonic
                    ):
                        changed_product_ids.append(item.product_id)

        unique_changed_product_ids = self._unique_non_empty(changed_product_ids)
        changed = bool(unique_changed_product_ids)
        if changed and not dry_run:
            self.repository.write_snapshot(
                ManagedInventorySnapshot(records=normalized_records, updated_at=utc_now_iso())
            )

        return {
            "ok": True,
            "dry_run": dry_run,
            "records_checked": len(snapshot.records),
            "records_written": 0 if dry_run or not changed else len(normalized_records),
            "product_identity_updates": len(unique_changed_product_ids),
            "updated_product_ids": unique_changed_product_ids,
        }

    def execute_wmd_cleanup(
        self,
        managed_well_id: str,
        product_ids: list[str] | None = None,
    ) -> ExecuteWmdCleanupResponse:
        """Persist guarded cleanup of WLV-owned transient WMD viewer payloads."""
        record = self._resolve_managed_well_reference(
            managed_well_id, self.repository.list_records()
        )
        record = self._with_inventory_identity_contract(
            self._with_product_groups(record)
        )
        selected = (
            self._resolve_product_references(record, product_ids)
            if product_ids
            else None
        )
        cleared, cleared_ids, record_payload_cleared = (
            self.wmd_lifecycle_service.execute_cleanup(record, selected)
        )
        cleared.updated_at = utc_now_iso()
        _action, persisted = self.repository.upsert_record(cleared)
        self._sync_source_intake_reference_state(persisted)
        return ExecuteWmdCleanupResponse(
            result=ExecuteWmdCleanupResult(
                managed_well_id=persisted.managed_well_id,
                cleared_product_ids=cleared_ids,
                cleared_record_payload=record_payload_cleared,
                external_sources_touched=False,
            ),
            record=persisted,
        )


    @staticmethod
    def _source_candidates_for_rebuild(
        record: ManagedWellRecord,
        item: ManagedProductGroupItem,
    ) -> list[Path]:
        provenance = item.provenance if isinstance(item.provenance, dict) else {}
        candidates = [
            provenance.get("original_path"),
            provenance.get("source_path"),
            provenance.get("path"),
        ]
        matching_reference = next(
            (
                source
                for source in record.source_references
                if item.source_id and source.source_id == item.source_id
            ),
            None,
        )
        if matching_reference is not None:
            candidates.append(matching_reference.original_path)
        paths: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(str(candidate)).expanduser()
            key = str(path)
            if key not in seen:
                seen.add(key)
                paths.append(path)
        return paths

    @staticmethod
    def _expected_source_fingerprint(
        record: ManagedWellRecord,
        item: ManagedProductGroupItem,
    ) -> str | None:
        provenance = item.provenance if isinstance(item.provenance, dict) else {}
        asset = provenance.get("las_asset")
        values = [
            provenance.get("source_fingerprint"),
            provenance.get("fingerprint"),
            provenance.get("checksum"),
            asset.get("source_fingerprint") if isinstance(asset, dict) else None,
        ]
        matching_reference = next(
            (
                source
                for source in record.source_references
                if item.source_id and source.source_id == item.source_id
            ),
            None,
        )
        if matching_reference is not None:
            values.append(matching_reference.checksum)
        for value in values:
            text = str(value or "").strip().lower()
            if re.fullmatch(r"[0-9a-f]{64}", text):
                return text
        return None

    @staticmethod
    def _sha256_read_only(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _inspect_source_for_rebuild(
        self,
        record: ManagedWellRecord,
        item: ManagedProductGroupItem,
    ) -> tuple[WmdSourceRecoveryState, Path | None, str | None, str]:
        candidates = self._source_candidates_for_rebuild(record, item)
        if not candidates:
            return (
                WmdSourceRecoveryState.MISSING,
                None,
                None,
                f"No authoritative external source reference is retained for WMD product: {item.product_id}",
            )

        existing = [path for path in candidates if path.exists()]
        if not existing:
            return (
                WmdSourceRecoveryState.MISSING,
                None,
                None,
                f"Authoritative external source is missing for WMD product: {item.product_id}",
            )

        path = existing[0]
        if not path.is_file():
            return (
                WmdSourceRecoveryState.INACCESSIBLE,
                path,
                None,
                f"Authoritative external source is inaccessible for WMD product: {item.product_id}",
            )
        try:
            resolved = path.resolve(strict=True)
            actual = self._sha256_read_only(resolved)
        except (OSError, PermissionError):
            return (
                WmdSourceRecoveryState.INACCESSIBLE,
                path,
                None,
                f"Authoritative external source is inaccessible for WMD product: {item.product_id}",
            )

        expected = self._expected_source_fingerprint(record, item)
        if expected is not None and actual != expected:
            return (
                WmdSourceRecoveryState.CHANGED,
                resolved,
                actual,
                f"Authoritative source fingerprint changed for WMD product: {item.product_id}",
            )
        return (
            WmdSourceRecoveryState.AVAILABLE,
            resolved,
            actual,
            "Authoritative external source is available and fingerprint-verified.",
        )

    def _persist_wmd_source_recovery_state(
        self,
        record: ManagedWellRecord,
        item_states: dict[str, tuple[WmdSourceRecoveryState, str | None, str]],
    ) -> ManagedWellRecord:
        checked_at = utc_now_iso()
        groups: list[ManagedProductGroup] = []
        for group in record.product_groups:
            items: list[ManagedProductGroupItem] = []
            for item in group.items:
                state = item_states.get(item.product_id)
                if state is None:
                    items.append(item)
                    continue
                recovery_state, observed, message = state
                items.append(
                    item.model_copy(
                        update={
                            "wmd_source_recovery_state": recovery_state,
                            "wmd_source_checked_at": checked_at,
                            "wmd_source_recovery_message": message,
                            "wmd_observed_source_fingerprint": observed,
                            "wmd_working_state": WmdWorkingState.CLEARED,
                            "wmd_retention_state": WmdRetentionState.CLEARED,
                            "wmd_cleanup_eligible": False,
                            "wmd_retention_reason": f"rebuild_blocked_source_{recovery_state.value}",
                        }
                    )
                )
            groups.append(group.model_copy(update={"items": items}))

        states = {value[0] for value in item_states.values()}
        aggregate = (
            WmdSourceRecoveryState.CHANGED
            if WmdSourceRecoveryState.CHANGED in states
            else WmdSourceRecoveryState.INACCESSIBLE
            if WmdSourceRecoveryState.INACCESSIBLE in states
            else WmdSourceRecoveryState.MISSING
            if WmdSourceRecoveryState.MISSING in states
            else WmdSourceRecoveryState.AVAILABLE
        )
        messages = [value[2] for value in item_states.values()]
        observed_values = [value[1] for value in item_states.values() if value[1]]
        updated = record.model_copy(
            update={
                "product_groups": groups,
                "wmd_source_recovery_state": aggregate,
                "wmd_source_checked_at": checked_at,
                "wmd_source_recovery_message": "; ".join(messages),
                "wmd_observed_source_fingerprint": observed_values[0] if len(set(observed_values)) == 1 else None,
                "wmd_working_state": WmdWorkingState.CLEARED,
                "wmd_retention_state": WmdRetentionState.CLEARED,
                "wmd_cleanup_eligible": False,
                "wmd_retention_reason": f"rebuild_blocked_source_{aggregate.value}",
                "updated_at": checked_at,
            }
        )
        _action, persisted = self.repository.upsert_record(updated)
        self._sync_source_intake_reference_state(persisted)
        return persisted

    def rebuild_wmd_payload(
        self,
        managed_well_id: str,
        product_ids: list[str] | None = None,
    ) -> RebuildWmdPayloadResponse:
        """Rebuild cleared transient WMD payload state from retained source provenance."""
        record = self._resolve_managed_well_reference(
            managed_well_id, self.repository.list_records()
        )
        record = self._with_inventory_identity_contract(
            self._with_product_groups(record)
        )
        selected = (
            self._resolve_product_references(record, product_ids)
            if product_ids
            else None
        )
        selected_items = [
            item
            for group in record.product_groups
            for item in group.items
            if selected is None or item.product_id in selected
        ]
        if not selected_items:
            raise ValueError("No WMD products were selected for rebuild.")

        verified: list[str] = []
        identity_before = {
            item.product_id: (
                str(item.managed_product_uid or ""),
                str(item.managed_curve_uid or ""),
                str(item.curve_uid or ""),
            )
            for item in selected_items
        }
        recovery_states: dict[str, tuple[WmdSourceRecoveryState, str | None, str]] = {}
        available_paths: dict[str, Path] = {}
        for item in selected_items:
            if item.wmd_retention_state != WmdRetentionState.CLEARED:
                raise ValueError(
                    f"WMD product is not cleared and cannot be rebuilt: {item.product_id}"
                )
            state, source_path, observed, message = self._inspect_source_for_rebuild(record, item)
            recovery_states[item.product_id] = (state, observed, message)
            if state == WmdSourceRecoveryState.AVAILABLE and source_path is not None:
                available_paths[item.product_id] = source_path

        blocked = {
            product_id: state
            for product_id, state in recovery_states.items()
            if state[0] != WmdSourceRecoveryState.AVAILABLE
        }
        if blocked:
            self._persist_wmd_source_recovery_state(record, recovery_states)
            messages = [state[2] for state in blocked.values()]
            raise ValueError("; ".join(messages))

        for item in selected_items:
            # Prove the retained source/provenance path can supply samples before
            # changing lifecycle state. This reparses LAS/DLIS read-only.
            try:
                self.curve_sample_service.get_curve_samples(
                    managed_well_id=record.managed_well_id,
                    product_id=item.product_id,
                    max_samples=32,
                )
            except (CurveSampleServiceError, OSError, PermissionError) as exc:
                message = f"Authoritative external source is inaccessible for WMD product: {item.product_id}"
                recovery_states[item.product_id] = (
                    WmdSourceRecoveryState.INACCESSIBLE,
                    recovery_states[item.product_id][1],
                    message,
                )
                self._persist_wmd_source_recovery_state(record, recovery_states)
                raise ValueError(message) from exc
            verified.append(recovery_states[item.product_id][1] or "")

        rebuilt, rebuilt_ids = self.wmd_lifecycle_service.rebuild_cleared_payload(
            record, selected
        )
        self._acquire_wmd_reference(rebuilt)
        rebuilt = self.wmd_lifecycle_service.project_record(rebuilt)
        checked_at = utc_now_iso()
        rebuilt_groups: list[ManagedProductGroup] = []
        for group in rebuilt.product_groups:
            rebuilt_groups.append(
                group.model_copy(
                    update={
                        "items": [
                            item.model_copy(
                                update={
                                    "wmd_source_recovery_state": WmdSourceRecoveryState.AVAILABLE,
                                    "wmd_source_checked_at": checked_at,
                                    "wmd_source_recovery_message": "Authoritative external source is available and fingerprint-verified.",
                                    "wmd_observed_source_fingerprint": recovery_states[item.product_id][1],
                                }
                            )
                            if item.product_id in rebuilt_ids
                            else item
                            for item in group.items
                        ]
                    }
                )
            )
        rebuilt = rebuilt.model_copy(
            update={
                "product_groups": rebuilt_groups,
                "wmd_source_recovery_state": WmdSourceRecoveryState.AVAILABLE,
                "wmd_source_checked_at": checked_at,
                "wmd_source_recovery_message": "Authoritative external source is available and fingerprint-verified.",
                "wmd_observed_source_fingerprint": verified[0] if len(set(verified)) == 1 else None,
            }
        )
        rebuilt.updated_at = checked_at
        _action, persisted = self.repository.upsert_record(rebuilt)
        self._sync_source_intake_reference_state(persisted)

        identity_after = {
            item.product_id: (
                str(item.managed_product_uid or ""),
                str(item.managed_curve_uid or ""),
                str(item.curve_uid or ""),
            )
            for group in persisted.product_groups
            for item in group.items
            if item.product_id in rebuilt_ids
        }
        identities_preserved = all(
            identity_after.get(product_id) == identity_before.get(product_id)
            for product_id in rebuilt_ids
        )
        if not identities_preserved:
            raise ValueError("WMD rebuild changed durable product or curve identity.")

        return RebuildWmdPayloadResponse(
            result=RebuildWmdPayloadResult(
                managed_well_id=persisted.managed_well_id,
                rebuilt_product_ids=rebuilt_ids,
                source_fingerprints_verified=verified,
                identities_preserved=True,
                external_sources_touched=False,
            ),
            record=persisted,
        )

    def list_wells(self) -> list[ManagedWellRecord]:
        return [
            self.wmd_lifecycle_service.project_record(
                self._with_inventory_identity_contract(self._with_product_groups(record))
            )
            for record in self.repository.list_records()
            if record.wmdp_available and record.wmdp_state != ManagedWmdpState.REMOVED_FROM_WMDP
        ]

    def get_well(self, managed_well_id: str) -> ManagedWellRecord:
        return self.wmd_lifecycle_service.project_record(
            self._with_inventory_identity_contract(
                self._with_product_groups(self.repository.get_record(managed_well_id))
            )
        )

    def list_viewer_packages(self) -> list[ViewerPackageReference]:
        packages: list[ViewerPackageReference] = []
        for record in self.repository.list_records():
            packages.extend(record.viewer_packages)
        return packages

    def get_viewer_package_contract(self, managed_well_id: str) -> dict[str, Any]:
        """Return the backend-owned WDV viewer package/session contract.

        WDV must not infer loaded curves from MDP rows. Managed Inventory owns
        the load/session contract. If legacy state has products marked
        loaded_to_wdv without a materialized WDV package, this method repairs
        that invalid lifecycle state by creating the package from backend-owned
        product state and persisting it before returning the contract.
        """
        record = self._with_inventory_identity_contract(self.repository.get_record(managed_well_id))
        loaded_items = self._loaded_wdv_product_items(record)
        self._require_downstream_payload_available(
            record, {item.product_id for item in loaded_items} or None
        )
        if loaded_items:
            existing_session = record.metadata.get("wdv_load_session_contract")
            existing_product_ids = []
            if isinstance(existing_session, dict):
                existing_product_ids = [str(pid) for pid in existing_session.get("source_product_ids", [])]
            loaded_product_ids = [item.product_id for item in loaded_items]
            session_depth_stale = (
                isinstance(existing_session, dict)
                and not self._wdv_session_depth_domain_is_current(existing_session, record, loaded_items)
            )
            session_identity_stale = (
                isinstance(existing_session, dict)
                and not self._wdv_session_identity_contract_is_current(existing_session, record, loaded_items)
            )
            if (
                not isinstance(existing_session, dict)
                or existing_product_ids != loaded_product_ids
                or session_depth_stale
                or session_identity_stale
            ):
                self._sync_wdv_load_session_for_record(record)
                record.updated_at = utc_now_iso()
                _action, record = self.repository.upsert_record(record)
                existing_session = record.metadata.get("wdv_load_session_contract")
            if isinstance(existing_session, dict):
                return existing_session

        contract = record.metadata.get("viewer_package_contract")
        if isinstance(contract, dict):
            return self._viewer_package_contract_for_wdv(record=record, contract=contract)
        raise ManagedWellNotFoundError(f"{managed_well_id}/viewer-package")

    def _viewer_package_contract_for_wdv(self, record: ManagedWellRecord, contract: dict[str, Any]) -> dict[str, Any]:
        loaded_curve_names = {
            item.curve_name
            for group in record.product_groups
            for item in group.items
            if self._is_wdv_loadable_product(item)
            and item.wdv_state == ManagedWdvState.LOADED_TO_WDV
            and item.curve_name
        }

        if record.wdv_state != ManagedWdvState.LOADED_TO_WDV or not loaded_curve_names:
            return normalize_viewer_package_for_wdv(contract)

        filtered = dict(contract)
        filtered_tracks: list[dict[str, Any]] = []

        for raw_track in contract.get("tracks", []):
            if not isinstance(raw_track, dict):
                continue
            curves = raw_track.get("curves", [])
            if not curves:
                filtered_tracks.append(dict(raw_track))
                continue
            filtered_curves = [
                curve
                for curve in curves
                if isinstance(curve, dict)
                and str(curve.get("curve_id") or curve.get("mnemonic") or "") in loaded_curve_names
            ]
            if filtered_curves:
                next_track = dict(raw_track)
                next_track["curves"] = filtered_curves
                filtered_tracks.append(next_track)

        filtered["tracks"] = filtered_tracks
        filtered["wmdp_loaded_curve_names"] = sorted(loaded_curve_names)
        return normalize_viewer_package_for_wdv(filtered)

    def upsert_managed_record(self, record: ManagedWellRecord) -> tuple[str, ManagedWellRecord]:
        """Upsert a managed well record built by another backend service.

        This preserves the inventory service as the write boundary while keeping
        ingestion/import logic outside the API route layer.
        """
        try:
            existing_record = self.repository.get_record(record.managed_well_id)
        except ManagedWellNotFoundError:
            existing_record = None

        normalized_record = self.wmd_lifecycle_service.project_record(
            self._with_inventory_identity_contract(record)
        )
        normalized_record = reconcile_managed_record_identity(
            normalized_record,
            existing=existing_record,
        )
        normalized_record.updated_at = utc_now_iso()
        return self.repository.upsert_record(normalized_record)

    def register_seed_well(self, well_id: str = SeedWellRepository.WELL_ID) -> RegisterSeedWellResponse:
        well = self.seed_repository.get_well(well_id)
        viewer_package = self.seed_repository.get_viewer_package(well_id)
        managed_well_id = f"managed-well:{well.well_id}"
        now = datetime.now(timezone.utc).isoformat()

        existing_created_at = now
        try:
            existing = self.repository.get_record(managed_well_id)
            existing_created_at = existing.created_at
        except ManagedWellNotFoundError:
            existing = None

        lifecycle_state = ManagedInventoryLifecycleState.VIEWER_READY
        source_references = [
            ManagedSourceReference(
                source_id=f"source:{well.well_id}:seed-las",
                source_kind=ManagedSourceKind.SEED,
                display_name=well.source_file or f"{well.well_name} seed source",
                file_name=well.source_file,
                file_format="LAS",
                metadata={"source": "prototype_seed_repository"},
            )
        ]
        viewer_package_reference = self._viewer_package_reference(viewer_package)
        primary_log_file = well.log_files[0] if well.log_files else None
        run_number = primary_log_file.run_number if primary_log_file else "—"
        run_date = getattr(primary_log_file, "run_date", None) or getattr(primary_log_file, "date", None) or "—"
        record = ManagedWellRecord(
            managed_well_id=managed_well_id,
            well_id=well.well_id,
            well_name=well.well_name,
            wellbore_id=well.wellbore_id,
            wellbore_name=well.wellbore_name,
            operator=well.operator,
            field=well.field,
            block=getattr(well, "block", None),
            country=well.country,
            depth_unit=well.depth_unit.value if hasattr(well.depth_unit, "value") else str(well.depth_unit),
            top_depth=well.depth_range.min,
            base_depth=well.depth_range.max,
            status=lifecycle_state,
            lifecycle_state=lifecycle_state,
            source_references=source_references,
            viewer_packages=[viewer_package_reference],
            product_groups=self._product_groups_from_viewer_package(
                viewer_package=viewer_package,
                viewer_package_reference=viewer_package_reference,
                source_references=source_references,
                run_date=run_date or "—",
                run_number=run_number or "—",
            ),
            tags=["seed", "forge"],
            metadata={
                "api_number": well.api_number,
                "datum": well.datum,
                "kb_elevation": well.kb_elevation,
                "ground_elevation": well.ground_elevation,
                "viewer_package_contract": viewer_package.model_dump(mode="json"),
            },
            lifecycle_notes=["Registered from deterministic seed repository."],
            created_at=existing_created_at,
            updated_at=now,
        )
        action, saved = self.repository.upsert_record(record)
        return RegisterSeedWellResponse(ok=True, action=action, record=saved)


    def load_managed_well_to_wdv(
        self,
        managed_well_id: str,
        product_ids: list[str] | None = None,
    ) -> LoadManagedWellToWdvResponse:
        """Mark one managed well, and optionally selected products, as loaded to WDV.

        The Managed Well Inventory remains authoritative for WMDP/WDV state.
        Loading is deliberately state-only here: it does not generate viewer
        representations or mutate source-intake records. Loading is additive:
        other managed wells already loaded into the WDV workspace remain loaded.
        """
        records = self.repository.list_records()
        target = self._resolve_managed_well_reference(managed_well_id, records)
        selected_product_ids = self._resolve_product_references(
            target,
            product_ids or [],
        )
        self._require_downstream_payload_available(
            target, set(selected_product_ids) or None
        )

        unloaded_managed_well_ids: list[str] = []

        loadable_items = [
            item
            for group in target.product_groups
            for item in group.items
            if self._is_wdv_loadable_product(item)
        ]

        if selected_product_ids:
            loadable_items = [item for item in loadable_items if item.product_id in selected_product_ids]

        loaded_product_ids = [item.product_id for item in loadable_items]
        loaded_product_id_set = set(loaded_product_ids)

        target.wdv_state = ManagedWdvState.LOADED_TO_WDV
        for group in target.product_groups:
            for item in group.items:
                if item.product_id in loaded_product_id_set:
                    item.wdv_state = ManagedWdvState.LOADED_TO_WDV
                else:
                    item.wdv_state = ManagedWdvState.NOT_LOADED

        active_package_id = self._sync_wdv_load_session_for_record(target)
        self._acquire_wmd_reference(target)
        self._acquire_wdv_reference(target, loaded_product_id_set)
        target.updated_at = utc_now_iso()
        target = self.wmd_lifecycle_service.project_record(target)
        _action, saved = self.repository.upsert_record(target)
        self.workspace_service.reconcile(
            self.repository.list_records(),
            preferred_active=saved.managed_well_id,
        )
        self._sync_source_intake_reference_state(saved)

        return LoadManagedWellToWdvResponse(
            result=LoadManagedWellToWdvResult(
                managed_well_id=saved.managed_well_id,
                loaded_product_ids=loaded_product_ids,
                unloaded_managed_well_ids=unloaded_managed_well_ids,
                active_viewer_package_id=active_package_id,
            ),
            record=saved,
        )

    def bulk_load_wdv_workspace(
        self,
        selections: list[BulkLoadWdvWellSelection],
    ) -> BulkLoadWdvWorkspaceResponse:
        """Atomically add multiple managed wells/products to the WDV workspace.

        All references are resolved and validated before the inventory snapshot is
        written. Existing loaded wells remain loaded. The managed inventory is
        written once, then the workspace is reconciled once.
        """
        snapshot = self.repository.snapshot()
        records = snapshot.records
        prepared: list[tuple[ManagedWellRecord, list[str], bool]] = []
        seen_well_ids: set[str] = set()

        for selection in selections:
            target = self._resolve_managed_well_reference(selection.well_reference, records)
            if target.managed_well_id in seen_well_ids:
                raise ValueError(f"Duplicate managed well selection: {target.managed_well_id}")
            seen_well_ids.add(target.managed_well_id)

            selected_product_ids = self._resolve_product_references(
                target,
                selection.product_references,
            )
            self._require_downstream_payload_available(
                target, set(selected_product_ids) or None
            )
            loadable_items = [
                item
                for group in target.product_groups
                for item in group.items
                if self._is_wdv_loadable_product(item)
            ]
            if selected_product_ids:
                loadable_items = [
                    item for item in loadable_items if item.product_id in selected_product_ids
                ]
            if not loadable_items:
                raise ValueError(
                    f"Managed well has no selected WDV-loadable products: {target.managed_well_id}"
                )

            loaded_product_ids = [item.product_id for item in loadable_items]
            currently_loaded_ids = {
                item.product_id
                for group in target.product_groups
                for item in group.items
                if item.wdv_state == ManagedWdvState.LOADED_TO_WDV
            }
            already_loaded = set(loaded_product_ids).issubset(currently_loaded_ids)
            prepared.append((target, loaded_product_ids, already_loaded))

        now = utc_now_iso()
        prepared_by_id = {record.managed_well_id: (record, ids, already) for record, ids, already in prepared}
        updated_records: list[ManagedWellRecord] = []
        results: list[BulkLoadWdvWellResult] = []

        for record in records:
            prepared_item = prepared_by_id.get(record.managed_well_id)
            if prepared_item is None:
                updated_records.append(record)
                continue

            target, loaded_product_ids, already_loaded = prepared_item
            loaded_set = set(loaded_product_ids)
            target.wdv_state = ManagedWdvState.LOADED_TO_WDV
            for group in target.product_groups:
                for item in group.items:
                    if item.product_id in loaded_set:
                        item.wdv_state = ManagedWdvState.LOADED_TO_WDV
            self._acquire_wmd_reference(target)
            self._acquire_wdv_reference(target, loaded_set)
            target = self.wmd_lifecycle_service.project_record(target)
            target.updated_at = now
            updated_records.append(target)
            results.append(
                BulkLoadWdvWellResult(
                    managed_well_id=target.managed_well_id,
                    managed_well_uid=target.managed_well_uid,
                    well_name=target.well_name,
                    status="already_loaded" if already_loaded else "loaded",
                    loaded_product_ids=loaded_product_ids,
                )
            )

        self.repository.write_snapshot(
            snapshot.model_copy(update={"records": updated_records, "updated_at": now})
        )
        self._sync_source_intake_reference_states([item[0] for item in prepared])

        previous_workspace = self.workspace_service.get_workspace()
        loaded_record_ids = {
            record.managed_well_id
            for record in updated_records
            if any(
                item.wdv_state == ManagedWdvState.LOADED_TO_WDV
                for group in record.product_groups
                for item in group.items
            )
        }
        preferred_active = previous_workspace.active_managed_well_id
        if preferred_active not in loaded_record_ids:
            preferred_active = prepared[0][0].managed_well_id

        active_record = next(
            record for record in updated_records if record.managed_well_id == preferred_active
        )
        self._sync_wdv_load_session_for_record(active_record)
        workspace = self.workspace_service.reconcile(
            updated_records,
            preferred_active=preferred_active,
        )

        loaded_count = sum(1 for item in results if item.status == "loaded")
        already_loaded_count = sum(1 for item in results if item.status == "already_loaded")
        return BulkLoadWdvWorkspaceResponse(
            requested_count=len(selections),
            loaded_count=loaded_count,
            already_loaded_count=already_loaded_count,
            results=results,
            workspace=workspace,
        )

    def bulk_unload_wdv_workspace(
        self,
        selections: list[BulkLoadWdvWellSelection],
    ) -> BulkUnloadWdvWorkspaceResponse:
        snapshot = self.repository.snapshot()
        records = snapshot.records
        prepared: list[tuple[ManagedWellRecord, list[str], bool]] = []
        seen: set[str] = set()

        for selection in selections:
            target = self._resolve_managed_well_reference(selection.well_reference, records)
            if target.managed_well_id in seen:
                raise ValueError(f"Duplicate managed well selection: {target.managed_well_id}")
            seen.add(target.managed_well_id)
            selected_ids = self._resolve_product_references(target, selection.product_references)
            loaded_items = self._loaded_wdv_product_items(target)
            target_items = [item for item in loaded_items if item.product_id in selected_ids] if selected_ids else loaded_items
            unload_ids = [item.product_id for item in target_items]
            prepared.append((target, unload_ids, not unload_ids))

        previous = self.workspace_service.get_workspace()
        now = utc_now_iso()
        prepared_by_id = {record.managed_well_id: (record, ids, already) for record, ids, already in prepared}
        updated_records: list[ManagedWellRecord] = []
        results: list[BulkUnloadWdvWellResult] = []

        for record in records:
            prepared_item = prepared_by_id.get(record.managed_well_id)
            if prepared_item is None:
                updated_records.append(record)
                continue
            target, unload_ids, already_unloaded = prepared_item
            unload_set = set(unload_ids)
            for group in target.product_groups:
                for item in group.items:
                    if item.product_id in unload_set:
                        item.wdv_state = ManagedWdvState.NOT_LOADED
            remaining = [item.product_id for item in self._loaded_wdv_product_items(target)]
            target.wdv_state = ManagedWdvState.LOADED_TO_WDV if remaining else ManagedWdvState.NOT_LOADED
            self._release_wdv_reference(target, unload_set)
            self._sync_wdv_load_session_for_record(target)
            target = self.wmd_lifecycle_service.project_record(target)
            target.updated_at = now
            updated_records.append(target)
            results.append(BulkUnloadWdvWellResult(
                managed_well_id=target.managed_well_id,
                managed_well_uid=target.managed_well_uid,
                well_name=target.well_name,
                status="already_unloaded" if already_unloaded else "unloaded",
                unloaded_product_ids=unload_ids,
                remaining_loaded_product_ids=remaining,
            ))

        self.repository.write_snapshot(snapshot.model_copy(update={"records": updated_records, "updated_at": now}))
        self._sync_source_intake_reference_states([item[0] for item in prepared])
        remaining_ids = {record.managed_well_id for record in updated_records if self._loaded_wdv_product_items(record)}
        preferred_active = previous.active_managed_well_id if previous.active_managed_well_id in remaining_ids else None
        workspace = self.workspace_service.reconcile(updated_records, preferred_active=preferred_active)
        self.reconcile_wbv_session_reference(workspace.active_managed_well_id)
        return BulkUnloadWdvWorkspaceResponse(
            requested_count=len(selections),
            unloaded_count=sum(1 for item in results if item.status == "unloaded"),
            already_unloaded_count=sum(1 for item in results if item.status == "already_unloaded"),
            results=results,
            workspace=workspace,
        )

    def get_wdv_workspace(self) -> WdvWorkspaceStateResponse:
        return self.workspace_service.get_workspace()

    def set_active_wdv_well(self, managed_well_reference: str) -> WdvWorkspaceStateResponse:
        workspace = self.workspace_service.set_active_well(managed_well_reference)
        self.reconcile_wbv_session_reference(workspace.active_managed_well_id)
        return workspace

    def set_common_depth_unit(self, common_depth_unit: str) -> WdvWorkspaceStateResponse:
        return self.workspace_service.set_common_depth_unit(common_depth_unit)

    def restore_source_candidates_to_mdp(
        self,
        source_candidate_ids: list[str],
    ) -> RestoreManagedDataToMdpResponse:
        """Restore retained MSI products for selected WSI candidates to MDP visibility.

        Source candidate identity is matched only against persisted MSI source
        references and product provenance. No filename or display-name inference
        is allowed. The operation is additive and idempotent.
        """
        candidate_ids = [value for value in dict.fromkeys(source_candidate_ids) if value]
        if not candidate_ids:
            raise ValueError("Select at least one Source Intake candidate to restore to MDP.")

        records = self.repository.list_records()
        matched_candidates: set[str] = set()
        restored_well_ids: list[str] = []
        restored_product_ids: list[str] = []
        already_visible_well_ids: list[str] = []
        already_visible_product_ids: list[str] = []
        touched_records: list[ManagedWellRecord] = []

        for record in records:
            source_reference_ids = {
                ref.source_id
                for ref in record.source_references
                if ref.source_id
            }
            record_candidate_ids = set(candidate_ids) & source_reference_ids
            matched_items: list[ManagedProductGroupItem] = []

            for group in record.product_groups:
                for item in group.items:
                    item_candidate_ids = {
                        value
                        for value in (
                            item.source_id,
                            item.source_intake_candidate_id,
                            item.provenance.get("source_file_id") if item.provenance else None,
                            item.provenance.get("source_intake_candidate_id") if item.provenance else None,
                        )
                        if value
                    }
                    overlap = set(candidate_ids) & item_candidate_ids
                    if overlap:
                        matched_items.append(item)
                        record_candidate_ids.update(overlap)

            if not record_candidate_ids:
                continue

            matched_candidates.update(record_candidate_ids)
            record_changed = False

            for item in matched_items:
                if item.wmdp_state == ManagedWmdpState.REMOVED_FROM_WMDP:
                    item.wmdp_state = ManagedWmdpState.STAGED_IN_WMDP
                    item.wdv_state = ManagedWdvState.NOT_LOADED
                    restored_product_ids.append(item.product_id)
                    record_changed = True
                else:
                    already_visible_product_ids.append(item.product_id)

            # A candidate may map to a retained managed well even when no product
            # rows exist (for example a future well-level source type). Restore
            # the well projection without inventing products.
            if record.wmdp_state == ManagedWmdpState.REMOVED_FROM_WMDP or not record.wmdp_available:
                record.wmdp_state = ManagedWmdpState.STAGED_IN_WMDP
                record.wmdp_available = True
                record.wdv_state = ManagedWdvState.NOT_LOADED
                restored_well_ids.append(record.managed_well_id)
                record_changed = True
            else:
                already_visible_well_ids.append(record.managed_well_id)

            if record_changed:
                self._acquire_wmd_reference(record)
                record.updated_at = utc_now_iso()
                record = self.wmd_lifecycle_service.project_record(record)
                _action, saved = self.repository.upsert_record(record)
                touched_records.append(saved)

        missing = sorted(set(candidate_ids) - matched_candidates)
        self.workspace_service.reconcile(self.repository.list_records())
        self._sync_source_intake_reference_states(touched_records)

        return RestoreManagedDataToMdpResponse(
            result=RestoreManagedDataToMdpResult(
                restored_managed_well_ids=sorted(set(restored_well_ids)),
                restored_product_ids=sorted(set(restored_product_ids)),
                already_visible_managed_well_ids=sorted(set(already_visible_well_ids)),
                already_visible_product_ids=sorted(set(already_visible_product_ids)),
                missing_source_candidate_ids=missing,
            ),
            records=touched_records,
        )

    def remove_managed_data_from_mdp(
        self,
        managed_well_ids: list[str] | None = None,
        product_ids: list[str] | None = None,
    ) -> RemoveManagedDataFromMdpResponse:
        """Remove selected managed data from the MDP while retaining MSI records.

        This is a non-destructive MDP visibility transition. It also unloads the
        same wells/products from WDV so the viewer cannot retain data that the
        user removed from the Managed Data Page. Source files, source-intake
        history, viewer-package metadata, and the MSI record remain intact.
        """
        well_references = list(managed_well_ids or [])
        product_references = list(product_ids or [])

        if not well_references and not product_references:
            raise ValueError("Select at least one managed well or product to remove from MDP.")

        records = self.repository.list_records()
        selected_well_ids = {
            self._resolve_managed_well_reference(reference, records).managed_well_id
            for reference in well_references
        }
        selected_product_ids = self._resolve_product_references_across_records(
            records,
            product_references,
        )

        touched_records: list[ManagedWellRecord] = []
        removed_well_ids: list[str] = []
        removed_product_ids: list[str] = []
        unloaded_well_ids: list[str] = []

        for record in records:
            full_well_remove = record.managed_well_id in selected_well_ids
            product_removed_for_record = False

            if full_well_remove:
                record.wmdp_available = False
                record.wmdp_state = ManagedWmdpState.REMOVED_FROM_WMDP
                if record.wdv_state != ManagedWdvState.NOT_LOADED:
                    unloaded_well_ids.append(record.managed_well_id)
                record.wdv_state = ManagedWdvState.NOT_LOADED
                removed_well_ids.append(record.managed_well_id)

            for group in record.product_groups:
                for item in group.items:
                    remove_item = full_well_remove or item.product_id in selected_product_ids
                    if not remove_item:
                        continue
                    item.wmdp_state = ManagedWmdpState.REMOVED_FROM_WMDP
                    if item.wdv_state != ManagedWdvState.NOT_LOADED and record.managed_well_id not in unloaded_well_ids:
                        unloaded_well_ids.append(record.managed_well_id)
                    item.wdv_state = ManagedWdvState.NOT_LOADED
                    product_removed_for_record = True
                    if item.product_id not in removed_product_ids:
                        removed_product_ids.append(item.product_id)

            if selected_product_ids and product_removed_for_record and not full_well_remove:
                remaining_mdp_items = [
                    item
                    for group in record.product_groups
                    for item in group.items
                    if item.wmdp_state != ManagedWmdpState.REMOVED_FROM_WMDP
                ]
                remaining_loaded_items = [
                    item
                    for item in remaining_mdp_items
                    if self._is_wdv_loadable_product(item) and item.wdv_state == ManagedWdvState.LOADED_TO_WDV
                ]
                record.wdv_state = (
                    ManagedWdvState.LOADED_TO_WDV
                    if remaining_loaded_items
                    else ManagedWdvState.NOT_LOADED
                )

            if full_well_remove or product_removed_for_record:
                removed_for_record = {
                    item.product_id
                    for group in record.product_groups
                    for item in group.items
                    if item.wmdp_state == ManagedWmdpState.REMOVED_FROM_WMDP
                }
                self._release_wdv_reference(record, None if full_well_remove else removed_for_record)
                self._release_wmd_reference(record, None if full_well_remove else removed_for_record)
                self._sync_wdv_load_session_for_record(record)
                record.updated_at = utc_now_iso()
                record = self.wmd_lifecycle_service.project_record(record)
                _action, saved = self.repository.upsert_record(record)
                touched_records.append(saved)

        missing_product_ids = sorted(selected_product_ids - set(removed_product_ids))
        if missing_product_ids and not touched_records:
            raise ManagedWellNotFoundError(missing_product_ids[0])

        self._sync_source_intake_reference_states(touched_records)

        return RemoveManagedDataFromMdpResponse(
            result=RemoveManagedDataFromMdpResult(
                removed_managed_well_ids=removed_well_ids,
                removed_product_ids=removed_product_ids,
                unloaded_managed_well_ids=sorted(set(unloaded_well_ids)),
                retained_msi_records=True,
            ),
            records=touched_records,
        )

    def unload_managed_well_from_wdv(
        self,
        managed_well_id: str,
        product_ids: list[str] | None = None,
    ) -> UnloadManagedWellFromWdvResponse:
        """Mark selected managed well data as unloaded from WDV.

        Unload is a non-destructive WDV state transition. It does not remove
        Managed Well Inventory records, WMDP staging state, source-intake
        records, source files, or viewer-package metadata. If product_ids is
        empty, the whole managed well is unloaded from WDV. If product_ids is
        supplied, only those products are unloaded and the well remains
        loaded_to_wdv while any loadable product remains loaded.
        """
        records = self.repository.list_records()
        record = self._resolve_managed_well_reference(managed_well_id, records)
        selected_product_ids = self._resolve_product_references(
            record,
            product_ids or [],
        )

        loadable_items = [
            item
            for group in record.product_groups
            for item in group.items
            if self._is_wdv_loadable_product(item)
        ]

        if selected_product_ids:
            target_items = [item for item in loadable_items if item.product_id in selected_product_ids]
        else:
            target_items = loadable_items

        unloaded_product_ids = [item.product_id for item in target_items]
        unloaded_product_id_set = set(unloaded_product_ids)

        for group in record.product_groups:
            for item in group.items:
                if item.product_id in unloaded_product_id_set:
                    item.wdv_state = ManagedWdvState.NOT_LOADED

        remaining_loaded_product_ids = [
            item.product_id
            for group in record.product_groups
            for item in group.items
            if self._is_wdv_loadable_product(item) and item.wdv_state == ManagedWdvState.LOADED_TO_WDV
        ]

        record.wdv_state = (
            ManagedWdvState.LOADED_TO_WDV
            if remaining_loaded_product_ids
            else ManagedWdvState.NOT_LOADED
        )
        self._release_wdv_reference(record, unloaded_product_id_set)
        self._sync_wdv_load_session_for_record(record)
        record.updated_at = utc_now_iso()
        record = self.wmd_lifecycle_service.project_record(record)
        _action, saved = self.repository.upsert_record(record)
        self.workspace_service.reconcile(self.repository.list_records())
        self._sync_source_intake_reference_state(saved)

        return UnloadManagedWellFromWdvResponse(
            result=UnloadManagedWellFromWdvResult(
                managed_well_id=saved.managed_well_id,
                unloaded_product_ids=unloaded_product_ids,
                remaining_loaded_product_ids=remaining_loaded_product_ids,
                wdv_state=saved.wdv_state,
            ),
            record=saved,
        )

    @staticmethod
    def _legacy_alias_values(value: Any) -> set[str]:
        aliases = getattr(value, "legacy_ids", None)
        if not isinstance(aliases, list):
            return set()
        return {
            str(alias.value).strip()
            for alias in aliases
            if str(getattr(alias, "value", "") or "").strip()
        }

    def _resolve_managed_well_reference(
        self,
        reference: str,
        records: list[ManagedWellRecord] | None = None,
    ) -> ManagedWellRecord:
        normalized = str(reference or "").strip()
        if not normalized:
            raise ManagedWellNotFoundError(reference)

        candidates = records if records is not None else self.repository.list_records()
        for record in candidates:
            references = {
                record.managed_well_id,
                record.well_id,
                str(record.managed_well_uid or ""),
                *self._legacy_alias_values(record),
            }
            if normalized in references:
                return record
        raise ManagedWellNotFoundError(normalized)

    def _resolve_product_references(
        self,
        record: ManagedWellRecord,
        references: list[str],
    ) -> set[str]:
        normalized = {str(value).strip() for value in references if str(value).strip()}
        if not normalized:
            return set()

        resolved: set[str] = set()
        for group in record.product_groups:
            for item in group.items:
                candidates = {
                    item.product_id,
                    str(item.managed_product_uid or ""),
                    str(item.managed_curve_uid or ""),
                    str(item.curve_uid or ""),
                    *self._legacy_alias_values(item),
                }
                if normalized.intersection(candidates):
                    resolved.add(item.product_id)

        missing = sorted(
            reference
            for reference in normalized
            if not any(
                reference in {
                    item.product_id,
                    str(item.managed_product_uid or ""),
                    str(item.managed_curve_uid or ""),
                    str(item.curve_uid or ""),
                    *self._legacy_alias_values(item),
                }
                for group in record.product_groups
                for item in group.items
            )
        )
        if missing:
            raise ManagedWellNotFoundError(missing[0])
        return resolved

    def _resolve_product_references_across_records(
        self,
        records: list[ManagedWellRecord],
        references: list[str],
    ) -> set[str]:
        normalized = {str(value).strip() for value in references if str(value).strip()}
        if not normalized:
            return set()

        resolved: set[str] = set()
        matched: set[str] = set()
        for record in records:
            for group in record.product_groups:
                for item in group.items:
                    candidates = {
                        item.product_id,
                        str(item.managed_product_uid or ""),
                        str(item.managed_curve_uid or ""),
                        str(item.curve_uid or ""),
                        *self._legacy_alias_values(item),
                    }
                    overlap = normalized.intersection(candidates)
                    if overlap:
                        resolved.add(item.product_id)
                        matched.update(overlap)

        missing = sorted(normalized - matched)
        if missing:
            raise ManagedWellNotFoundError(missing[0])
        return resolved

    def _loaded_wdv_product_items(self, record: ManagedWellRecord) -> list[ManagedProductGroupItem]:
        return [
            item
            for group in record.product_groups
            for item in group.items
            if self._is_wdv_loadable_product(item) and item.wdv_state == ManagedWdvState.LOADED_TO_WDV
        ]

    def _sync_wdv_load_session_for_record(self, record: ManagedWellRecord) -> str | None:
        """Create/update/clear the backend-owned WDV load session package.

        This method is the inventory lifecycle gate for WDV availability. A
        record may not remain loaded_to_wdv without a WDV-loadable package.
        """
        loaded_items = self._loaded_wdv_product_items(record)
        if not loaded_items:
            record.metadata.pop("wdv_load_session", None)
            record.metadata.pop("wdv_load_session_contract", None)
            record.viewer_packages = [
                package
                for package in record.viewer_packages
                if not package.viewer_package_id.startswith("wdv-load-session:")
            ]
            if record.wdv_state == ManagedWdvState.LOADED_TO_WDV:
                record.wdv_state = ManagedWdvState.NOT_LOADED
            return None

        record.wdv_state = ManagedWdvState.LOADED_TO_WDV
        contract = self._build_wdv_load_session_contract(record, loaded_items)
        reference = self._wdv_load_session_reference(record, contract)
        contract["viewer_package_uid"] = str(reference.viewer_package_uid) if reference.viewer_package_uid else None
        contract["representation_uid"] = str(reference.representation_uid) if reference.representation_uid else None
        record.metadata["wdv_load_session"] = {
            "session_id": contract["representation_id"],
            "managed_well_id": record.managed_well_id,
            "loaded_product_count": len(loaded_items),
            "source_product_ids": contract["source_product_ids"],
            "updated_at": contract["updated_at"],
            "contract_version": "wdv_load_session_v1",
        }
        record.metadata["wdv_load_session_contract"] = contract
        retained_packages = [
            package
            for package in record.viewer_packages
            if not package.viewer_package_id.startswith("wdv-load-session:")
        ]
        record.viewer_packages = [reference, *retained_packages]
        return reference.viewer_package_id

    def _build_wdv_load_session_contract(
        self,
        record: ManagedWellRecord,
        loaded_items: list[ManagedProductGroupItem],
    ) -> dict[str, Any]:
        # Deferred import: avoids circular dependency at module load time.
        # policy_service imports inventory.models, not inventory.service.
        from app.wdv_display.policy_service import (
            WDV_DISPLAY_POLICY_CONTRACT_VERSION as _DPCV,
            compute_display_policy_revision as _compute_dpr,
        )
        product_ids = [item.product_id for item in loaded_items]
        loaded_curve_items = [self._wdv_curve_contract_from_product_item(record, item) for item in loaded_items]
        loaded_curve_names = [
            str(curve.get("mnemonic") or curve.get("curve_id") or curve.get("display_name") or "").strip()
            for curve in loaded_curve_items
        ]
        loaded_curve_names = [name for name in loaded_curve_names if name]
        source_candidate_ids = self._unique_non_empty([item.source_intake_candidate_id for item in loaded_items])
        source_ids = self._unique_non_empty([item.source_id for item in loaded_items])
        session_hash = hashlib.sha1("|".join(product_ids).encode("utf-8")).hexdigest()[:16]
        session_id = f"wdv-load-session:{record.well_id}:{session_hash}"
        depth_unit = record.depth_unit or "ft"
        depth_min, depth_max, depth_domain_source, depth_contributing_product_ids = self._wdv_loaded_depth_domain(
            record,
            loaded_items,
        )

        # Loaded products are WDV inventory, not visible display layout.
        # A fresh MDP load must populate loaded_curve_items for the left panel
        # while leaving visible curve tracks empty until the user manually
        # assigns curves to tracks in the WDV.
        tracks: list[dict[str, Any]] = [
            {
                "track_id": "depth",
                "track_type": "depth",
                "title": "Depth",
                "curves": [],
            }
        ]
        visible_tracks: list[dict[str, Any]] = []

        return {
            "viewer_package_version": "well_multitrack_v1",
            "contract_kind": "wdv_load_session",
            "contract_version": "wdv_load_session_v1",
            "dataset_id": record.managed_well_id,
            "representation_id": session_id,
            "wdv_session_id": session_id,
            "managed_well_id": record.managed_well_id,
            "managed_well_uid": str(record.managed_well_uid) if record.managed_well_uid else None,
            "managed_wellbore_uid": str(record.managed_wellbore_uid) if record.managed_wellbore_uid else None,
            "well_id": record.well_id,
            "well_name": record.well_name,
            "wellbore_id": record.wellbore_id or record.well_id,
            "wellbore_name": record.wellbore_name or record.well_name,
            "operator": record.operator,
            "field": record.field,
            "country": record.country,
            "display_domain": "MD",
            "depth_unit": depth_unit,
            "depth_range": {"min": depth_min, "max": depth_max},
            "depth_domain": {
                "min": depth_min,
                "max": depth_max,
                "unit": depth_unit,
                "source": depth_domain_source,
                "contributing_product_ids": depth_contributing_product_ids,
            },
            "tracks": tracks,
            "visible_tracks": visible_tracks,
            "display_tracks": visible_tracks,
            "track_layout_state": "manual_empty",
            "source_product_ids": product_ids,
            "source_candidate_ids": source_candidate_ids,
            "source_ids": source_ids,
            "loaded_product_count": len(product_ids),
            "loaded_curve_names": loaded_curve_names,
            "mdp_loaded_curve_names": loaded_curve_names,
            "wmdp_loaded_curve_names": loaded_curve_names,
            "loaded_curve_items": loaded_curve_items,
            "unsupported_products": [],
            "messages": [],
            "created_by": "ManagedWellInventoryService._build_wdv_load_session_contract",
            "updated_at": utc_now_iso(),
            # Display-policy cache identity stamps.  The contract_version identifies
            # the schema of these fields; the revision is a content-based SHA-256 of
            # the approved governed records that influence policy resolution.  Both
            # must match in _wdv_session_identity_contract_is_current() for the
            # cached contract to be reused without a rebuild.
            "display_policy_contract_version": _DPCV,
            "display_policy_revision": _compute_dpr(),
        }

    @staticmethod
    def _wdv_session_identity_contract_is_current(
        session: dict[str, Any],
        record: ManagedWellRecord,
        loaded_items: list[ManagedProductGroupItem],
        *,
        storage: "ManagedStorage | None" = None,
    ) -> bool:
        if not record.managed_well_uid or session.get("managed_well_uid") != str(record.managed_well_uid):
            return False
        if record.managed_wellbore_uid and session.get("managed_wellbore_uid") != str(record.managed_wellbore_uid):
            return False
        if not session.get("viewer_package_uid") or not session.get("representation_uid"):
            return False

        raw_items = session.get("loaded_curve_items")
        if not isinstance(raw_items, list) or len(raw_items) != len(loaded_items):
            return False
        by_product_id = {
            str(item.get("product_id") or ""): item
            for item in raw_items
            if isinstance(item, dict)
        }
        for item in loaded_items:
            contract_item = by_product_id.get(item.product_id)
            if contract_item is None:
                return False
            if item.managed_product_uid and contract_item.get("managed_product_uid") != str(item.managed_product_uid):
                return False
            if item.managed_curve_uid and contract_item.get("managed_curve_uid") != str(item.managed_curve_uid):
                return False
            if item.managed_source_uid and contract_item.get("managed_source_uid") != str(item.managed_source_uid):
                return False
            sample_access = contract_item.get("sample_access")
            if not contract_item.get("samples_url") or not contract_item.get("sample_revision"):
                return False
            if not isinstance(sample_access, dict) or sample_access.get("contract_version") != "wdv_curve_samples_v1":
                return False

        # Display-policy cache identity: schema version + content-based revision.
        # Both must be present and match the current backend state.  Missing stamps
        # indicate a pre-C1 contract; mismatched revision means KR content or the
        # resolver algorithm has changed since the contract was built.  Either
        # condition forces a rebuild via the current WdvCurveDisplayPolicyService.
        from app.wdv_display.policy_service import (
            WDV_DISPLAY_POLICY_CONTRACT_VERSION,
            compute_display_policy_revision,
        )
        if session.get("display_policy_contract_version") != WDV_DISPLAY_POLICY_CONTRACT_VERSION:
            return False
        if session.get("display_policy_revision") != compute_display_policy_revision(storage=storage):
            return False

        return True

    def _wdv_session_depth_domain_is_current(
        self,
        session: dict[str, Any],
        record: ManagedWellRecord,
        loaded_items: list[ManagedProductGroupItem],
    ) -> bool:
        expected_min, expected_max, _source, _contributors = self._wdv_loaded_depth_domain(record, loaded_items)
        raw_domain = session.get("depth_domain") if isinstance(session.get("depth_domain"), dict) else session.get("depth_range")
        if not isinstance(raw_domain, dict):
            return False
        try:
            existing_min = float(raw_domain.get("min"))
            existing_max = float(raw_domain.get("max"))
        except (TypeError, ValueError):
            return False
        return abs(existing_min - expected_min) <= 0.01 and abs(existing_max - expected_max) <= 0.01

    def _wdv_loaded_depth_domain(
        self,
        record: ManagedWellRecord,
        loaded_items: list[ManagedProductGroupItem],
    ) -> tuple[float, float, str, list[str]]:
        intervals: list[tuple[float, float, str]] = []
        for item in loaded_items:
            interval = self._depth_interval_from_product_item(item)
            if interval is None:
                continue
            top, base = interval
            intervals.append((top, base, item.product_id))

        if intervals:
            return (
                min(top for top, _base, _product_id in intervals),
                max(base for _top, base, _product_id in intervals),
                "union_loaded_curve_intervals",
                self._unique_non_empty([product_id for _top, _base, product_id in intervals]),
            )

        depth_min = float(record.top_depth) if record.top_depth is not None else self._min_loaded_depth(loaded_items)
        depth_max = float(record.base_depth) if record.base_depth is not None else self._max_loaded_depth(loaded_items)
        if depth_max <= depth_min:
            depth_min, depth_max = 0.0, 1.0
        return depth_min, depth_max, "managed_well_record_depth_range", []

    @staticmethod
    def _depth_interval_from_product_item(item: ManagedProductGroupItem) -> tuple[float, float] | None:
        if item.run_interval:
            values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", str(item.run_interval))]
            if len(values) >= 2:
                top = min(values[0], values[1])
                base = max(values[0], values[1])
                if base > top:
                    return top, base

        value = item.provenance.get("parsed_metadata", {}) if isinstance(item.provenance, dict) else {}
        log_header = value.get("log_header", {}) if isinstance(value, dict) else {}
        if isinstance(log_header, dict):
            start = log_header.get("start_depth")
            stop = log_header.get("stop_depth")
            if isinstance(start, (int, float)) and isinstance(stop, (int, float)):
                top = min(float(start), float(stop))
                base = max(float(start), float(stop))
                if base > top:
                    return top, base
        return None


    def _wdv_curve_contract_from_product_item(self, record: ManagedWellRecord, item: ManagedProductGroupItem) -> dict[str, Any]:
        curve_id = str(item.curve_name or item.display_name or item.product_id).strip() or item.product_id
        sample_stats = self._wdv_curve_sample_statistics(record, item)
        scale = self._wdv_display_scale_contract(item, sample_stats)
        warnings = list(scale.get("warnings") or [])
        if sample_stats.get("statistics_status") != "available":
            warnings.append(str(sample_stats.get("statistics_status") or "statistics_unavailable"))
        sample_count = int(sample_stats.get("valid_sample_count") or 0)
        sample_available = sample_stats.get("statistics_status") == "available" and sample_count > 0
        samples_url = (
            f"/api/wlv/inventory/wells/{quote(record.managed_well_id, safe='')}/curve-samples"
            f"?product_id={quote(item.product_id, safe='')}"
        )
        provenance = item.provenance if isinstance(item.provenance, dict) else {}
        source_checksum = str(provenance.get("checksum") or provenance.get("fingerprint") or "")
        sample_revision = hashlib.sha256(
            f"{record.managed_well_id}|{item.product_id}|{source_checksum}|{sample_count}".encode("utf-8")
        ).hexdigest()[:20]

        return {
            "product_id": item.product_id,
            "managed_product_uid": str(item.managed_product_uid) if item.managed_product_uid else None,
            "managed_curve_uid": str(item.managed_curve_uid) if item.managed_curve_uid else None,
            "managed_wellbore_uid": str(item.managed_wellbore_uid or record.managed_wellbore_uid) if (item.managed_wellbore_uid or record.managed_wellbore_uid) else None,
            "managed_source_uid": str(item.managed_source_uid) if item.managed_source_uid else None,
            "curve_uid": (
                item.curve_uid
                or (str(item.managed_curve_uid) if item.managed_curve_uid else None)
                or item.product_id
            ),
            "well_uid": item.well_uid or self._managed_well_identity(record),
            "source_uid": item.source_uid or item.source_id,
            "kr_curve_type_id": item.kr_curve_type_id,
            "observed_mnemonic": item.observed_mnemonic or item.curve_name,
            "normalized_mnemonic": item.normalized_mnemonic or self._normalized_mnemonic(item.curve_name),
            "curve_id": curve_id,
            "display_curve_id": curve_id,
            "canonical_curve_id": self._canonical_curve_id_for_product_item(item),
            "original_mnemonic": curve_id,
            "mnemonic": curve_id,
            "normalized_name": item.curve_type or item.display_name or curve_id,
            "display_name": item.display_name or curve_id,
            "description": item.curve_description or item.curve_type,
            "curve_family": item.curve_family,
            "track_family": self._track_family_for_product_item(item),
            "unit": item.curve_unit or "",
            "scale": {"type": scale["type"], "min": scale["min"], "max": scale["max"]},
            "scale_type": scale["type"],
            "scale_direction": scale["direction"],
            # Backward-compatible display_min/display_max remain the rendered
            # left/right track values. Explicit numeric_* and *_left/right
            # fields remove the previous ambiguity for reversed scales.
            "display_min": scale["min"],
            "display_max": scale["max"],
            "display_left_value": scale.get("display_left_value", scale["min"]),
            "display_right_value": scale.get("display_right_value", scale["max"]),
            "numeric_min": scale.get("numeric_min"),
            "numeric_max": scale.get("numeric_max"),
            "scale_source": scale["source"],
            "display_scale_mode": scale.get("display_mode", scale.get("source")),
            "recommended_display_scale_mode": scale.get("recommended_display_mode", scale.get("display_mode", scale.get("source"))),
            "standard_display_min": scale.get("standard_min"),
            "standard_display_max": scale.get("standard_max"),
            "standard_display_left_value": scale.get("standard_display_left_value", scale.get("standard_min")),
            "standard_display_right_value": scale.get("standard_display_right_value", scale.get("standard_max")),
            "standard_numeric_min": scale.get("standard_numeric_min"),
            "standard_numeric_max": scale.get("standard_numeric_max"),
            "standard_scale_type": scale.get("standard_type", scale.get("type")),
            "standard_scale_direction": scale.get("standard_direction", scale.get("direction")),
            "robust_observed_display_min": scale.get("robust_observed_min"),
            "robust_observed_display_max": scale.get("robust_observed_max"),
            "robust_observed_display_left_value": scale.get("robust_observed_display_left_value", scale.get("robust_observed_min")),
            "robust_observed_display_right_value": scale.get("robust_observed_display_right_value", scale.get("robust_observed_max")),
            "robust_observed_numeric_min": scale.get("robust_observed_numeric_min"),
            "robust_observed_numeric_max": scale.get("robust_observed_numeric_max"),
            "robust_observed_scale_type": scale.get("robust_observed_type", scale.get("type")),
            "robust_observed_scale_direction": scale.get("robust_observed_direction", scale.get("direction")),
            "scale_warnings": warnings,
            "observed_min": sample_stats.get("observed_min"),
            "observed_max": sample_stats.get("observed_max"),
            "robust_observed_min": sample_stats.get("robust_observed_min"),
            "robust_observed_max": sample_stats.get("robust_observed_max"),
            "observed_p01": sample_stats.get("observed_p01"),
            "observed_p05": sample_stats.get("observed_p05"),
            "observed_p50": sample_stats.get("observed_p50"),
            "observed_p95": sample_stats.get("observed_p95"),
            "observed_p99": sample_stats.get("observed_p99"),
            "visual_span_ratio": scale.get("visual_span_ratio"),
            "observed_valid_sample_count": sample_stats.get("valid_sample_count", 0),
            "observed_raw_numeric_sample_count": sample_stats.get("raw_numeric_sample_count", 0),
            "observed_rejected_sample_count": sample_stats.get("rejected_sample_count", 0),
            "observed_rejected_null_count": sample_stats.get("rejected_null_count", 0),
            "observed_rejected_sentinel_count": sample_stats.get("rejected_sentinel_count", 0),
            "observed_rejected_plausibility_count": sample_stats.get("rejected_plausibility_count", 0),
            "observed_statistics_status": sample_stats.get("statistics_status"),
            "samples_url": samples_url,
            "sample_revision": sample_revision,
            "sample_access": {
                "contract_version": "wdv_curve_samples_v1",
                "endpoint": samples_url,
                "status": "available" if sample_available else "unavailable",
                "sample_count": sample_count,
                "depth_min": sample_stats.get("depth_min"),
                "depth_max": sample_stats.get("depth_max"),
                "depth_unit": record.depth_unit or "ft",
                "value_unit": item.curve_unit or "",
                "revision": sample_revision,
            },
            "is_renderable": sample_available,
            "support_status": "renderable" if sample_available else "samples_unavailable",
            "source_kind": item.source_kind,
            "source_id": item.source_id,
            "source_intake_candidate_id": item.source_intake_candidate_id,
            "qa_flag": item.qa_flag,
            "review_required": item.review_required,
            "run_date": item.run_date,
            "run_interval": item.run_interval,
            "run_number": item.run_number,
            "provenance": item.provenance,
        }

    def _wdv_curve_sample_statistics(self, record: ManagedWellRecord, item: ManagedProductGroupItem) -> dict[str, Any]:
        try:
            payload = self.curve_sample_service.get_curve_samples(
                managed_well_id=record.managed_well_id,
                product_id=item.product_id,
                max_samples=12000,
            )
        except (CurveSampleServiceError, ManagedWellNotFoundError, FileNotFoundError, OSError, ValueError) as exc:
            return {
                "statistics_status": "unavailable",
                "statistics_error": f"{type(exc).__name__}: {exc}",
                "valid_sample_count": 0,
                "raw_numeric_sample_count": 0,
                "rejected_sample_count": 0,
            }

        return {
            "statistics_status": "available",
            "observed_min": payload.get("value_min"),
            "observed_max": payload.get("value_max"),
            "robust_observed_min": payload.get("robust_value_min", payload.get("value_min")),
            "robust_observed_max": payload.get("robust_value_max", payload.get("value_max")),
            "observed_p01": payload.get("value_p01"),
            "observed_p05": payload.get("value_p05"),
            "observed_p50": payload.get("value_p50"),
            "observed_p95": payload.get("value_p95"),
            "observed_p99": payload.get("value_p99"),
            "depth_min": payload.get("depth_min"),
            "depth_max": payload.get("depth_max"),
            "valid_sample_count": payload.get("sample_count", 0),
            "raw_numeric_sample_count": payload.get("raw_numeric_sample_count", payload.get("sample_count", 0)),
            "rejected_sample_count": payload.get("rejected_sample_count", 0),
            "rejected_null_count": payload.get("rejected_null_count", 0),
            "rejected_sentinel_count": payload.get("rejected_sentinel_count", 0),
            "rejected_plausibility_count": payload.get("rejected_plausibility_count", 0),
        }

    @classmethod
    def _wdv_display_scale_contract(
        cls,
        item: ManagedProductGroupItem,
        sample_stats: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return WdvCurveDisplayPolicyService.resolve(item, sample_stats)

    @staticmethod
    def _wdv_default_scale(item: ManagedProductGroupItem) -> dict[str, Any]:
        scale = WdvCurveDisplayPolicyService.resolve(item, {})
        return {"type": scale["type"], "min": scale["min"], "max": scale["max"]}

    def _wdv_load_session_reference(self, record: ManagedWellRecord, contract: dict[str, Any]) -> ViewerPackageReference:
        session_id = str(contract["representation_id"])
        existing = next(
            (package for package in record.viewer_packages if package.viewer_package_id == session_id),
            None,
        )
        return ViewerPackageReference(
            viewer_package_id=session_id,
            viewer_package_uid=(existing.viewer_package_uid if existing and existing.viewer_package_uid else new_uuid7_str()),
            representation_uid=(existing.representation_uid if existing and existing.representation_uid else new_uuid7_str()),
            viewer_package_version=str(contract.get("viewer_package_version") or "well_multitrack_v1"),
            dataset_id=record.managed_well_id,
            representation_id=session_id,
            well_id=record.well_id,
            uwi=record.metadata.get("uwi") if isinstance(record.metadata, dict) else None,
            endpoint=f"/api/wlv/inventory/wells/{record.managed_well_id}/viewer-package",
            status=ManagedInventoryLifecycleState.VIEWER_READY,
        )

    @staticmethod
    def _unique_non_empty(values: list[Any]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            unique.append(text)
        return unique

    @staticmethod
    def _canonical_curve_id_for_product_item(item: ManagedProductGroupItem) -> str:
        key = str(item.curve_family or item.curve_type or item.curve_name or item.product_id).lower()
        if "gamma" in key:
            return "gamma_ray"
        if "resist" in key:
            return "resistivity"
        if "density" in key:
            return "density"
        if "neutron" in key:
            return "neutron_porosity"
        if "sonic" in key or "delta-t" in key:
            return "sonic"
        if "caliper" in key or "borehole" in key:
            return "caliper"
        if "pressure" in key:
            return "pressure"
        if "temperature" in key:
            return "temperature"
        return "curve"

    @staticmethod
    def _track_family_for_product_item(item: ManagedProductGroupItem) -> str:
        key = str(item.curve_family or item.product_category or "").lower()
        if "gamma" in key or "spontaneous" in key:
            return "gamma_ray_sp"
        if "resist" in key:
            return "resistivity"
        if "density" in key or "neutron" in key or "porosity" in key:
            return "density_neutron"
        if "sonic" in key:
            return "sonic"
        if "caliper" in key or "borehole" in key:
            return "borehole"
        return str(item.product_category or "loaded_curves")

    @staticmethod
    def _min_loaded_depth(items: list[ManagedProductGroupItem]) -> float:
        values: list[float] = []
        for item in items:
            value = item.provenance.get("parsed_metadata", {}) if isinstance(item.provenance, dict) else {}
            log_header = value.get("log_header", {}) if isinstance(value, dict) else {}
            start = log_header.get("start_depth") if isinstance(log_header, dict) else None
            if isinstance(start, (int, float)):
                values.append(float(start))
        return min(values) if values else 0.0

    @staticmethod
    def _max_loaded_depth(items: list[ManagedProductGroupItem]) -> float:
        values: list[float] = []
        for item in items:
            value = item.provenance.get("parsed_metadata", {}) if isinstance(item.provenance, dict) else {}
            log_header = value.get("log_header", {}) if isinstance(value, dict) else {}
            stop = log_header.get("stop_depth") if isinstance(log_header, dict) else None
            if isinstance(stop, (int, float)):
                values.append(float(stop))
        return max(values) if values else 1.0

    @staticmethod
    def _is_wdv_loadable_product(item: ManagedProductGroupItem) -> bool:
        if item.selectable is False:
            return False
        if item.product_category == "supporting_documents":
            return False
        source_kind = (item.source_kind or "").lower()
        if source_kind in {ManagedSourceKind.DOCUMENT.value, "pdf", "doc", "docx"}:
            return False
        return True

    def validate_inventory(self) -> ManagedInventoryValidationResult:
        snapshot = self.repository.snapshot()
        records = snapshot.records
        issues: list[ManagedInventoryValidationIssue] = []

        managed_ids = Counter(record.managed_well_id for record in records)
        well_ids = Counter(record.well_id for record in records)
        viewer_package_ids = Counter(
            package.viewer_package_id for record in records for package in record.viewer_packages
        )
        source_ids = Counter(source.source_id for record in records for source in record.source_references)

        for managed_well_id, count in managed_ids.items():
            if count > 1:
                issues.append(self._issue("error", "duplicate_managed_well_id", f"Duplicate managed_well_id appears {count} times.", managed_well_id, "managed_well_id"))
        for well_id, count in well_ids.items():
            if count > 1:
                issues.append(self._issue("warning", "duplicate_well_id", f"well_id appears in {count} managed records.", well_id, "well_id"))
        for package_id, count in viewer_package_ids.items():
            if count > 1:
                issues.append(self._issue("error", "duplicate_viewer_package_id", f"viewer_package_id appears {count} times.", None, "viewer_package_id"))
        for source_id, count in source_ids.items():
            if count > 1:
                issues.append(self._issue("warning", "duplicate_source_id", f"source_id appears {count} times.", None, "source_id"))

        for record in records:
            issues.extend(self._validate_record(record))

        error_count = sum(1 for issue in issues if issue.severity == InventoryValidationSeverity.ERROR)
        warning_count = sum(1 for issue in issues if issue.severity == InventoryValidationSeverity.WARNING)
        return ManagedInventoryValidationResult(
            ok=error_count == 0,
            storage_backend="local_json",
            storage_path=str(self.repository.storage_path),
            schema_version=snapshot.schema_version,
            managed_well_count=len(records),
            viewer_package_count=sum(len(record.viewer_packages) for record in records),
            source_reference_count=sum(len(record.source_references) for record in records),
            lifecycle_counts=self._lifecycle_counts(records),
            issue_count=len(issues),
            error_count=error_count,
            warning_count=warning_count,
            issues=issues,
        )


    def _with_inventory_identity_contract(self, record: ManagedWellRecord) -> ManagedWellRecord:
        """Return record with backend curve metadata normalized.

        The UID belongs to managed inventory, not to the WDV display layer. This
        helper intentionally does not create WDV assignments and does not choose
        preset candidates. It fills non-identity metadata required by downstream contracts. It must
        preserve any existing legacy curve UID but must not create a new one.
        """
        if not record.product_groups:
            return record

        default_source_uid = None
        if record.source_references:
            default_source_uid = record.source_references[0].source_id

        changed = False
        normalized_groups: list[ManagedProductGroup] = []

        for group in record.product_groups:
            normalized_items: list[ManagedProductGroupItem] = []
            for item in group.items:
                if not self._is_wdv_loadable_product(item):
                    normalized_items.append(item)
                    continue

                observed_mnemonic = item.observed_mnemonic or item.curve_name or item.display_name
                normalized_mnemonic = item.normalized_mnemonic or self._normalized_mnemonic(observed_mnemonic)
                source_uid = item.source_uid or item.source_id or default_source_uid
                well_uid = item.well_uid or record.well_id or record.managed_well_id
                updates: dict[str, Any] = {}
                if item.well_uid != well_uid:
                    updates["well_uid"] = well_uid
                if item.source_uid != source_uid:
                    updates["source_uid"] = source_uid
                if item.observed_mnemonic != observed_mnemonic:
                    updates["observed_mnemonic"] = observed_mnemonic
                if item.normalized_mnemonic != normalized_mnemonic:
                    updates["normalized_mnemonic"] = normalized_mnemonic

                if updates:
                    changed = True
                    normalized_items.append(item.model_copy(update=updates))
                else:
                    normalized_items.append(item)

            if normalized_items != group.items:
                changed = True
                normalized_groups.append(group.model_copy(update={"items": normalized_items}))
            else:
                normalized_groups.append(group)

        normalized_record = record.model_copy(update={"product_groups": normalized_groups}) if changed else record
        loaded_product_count, viewer_curve_count, displayable_curve_count = wdv_curve_counts(normalized_record)
        updates: dict[str, Any] = {
            "loaded_product_count": loaded_product_count,
            "viewer_curve_count": viewer_curve_count,
            "displayable_curve_count": displayable_curve_count,
        }
        if changed:
            updates["updated_at"] = utc_now_iso()
        return normalized_record.model_copy(update=updates)

    def _with_product_groups(self, record: ManagedWellRecord) -> ManagedWellRecord:
        """Return a record with backend-owned product_groups populated."""
        if record.product_groups:
            return record
        contract = record.metadata.get("viewer_package_contract")
        if not isinstance(contract, dict):
            return record
        viewer_package = WellMultitrackV1.model_validate(contract)
        viewer_package_reference = record.viewer_packages[0] if record.viewer_packages else self._viewer_package_reference(viewer_package)
        return record.model_copy(
            update={
                "product_groups": self._product_groups_from_viewer_package(
                    viewer_package=viewer_package,
                    viewer_package_reference=viewer_package_reference,
                    source_references=record.source_references,
                    run_date="—",
                    run_number="—",
                )
            }
        )

    def _product_groups_from_viewer_package(
        self,
        *,
        viewer_package: WellMultitrackV1,
        viewer_package_reference: ViewerPackageReference,
        source_references: list[ManagedSourceReference],
        run_date: str = "—",
        run_number: str = "—",
    ) -> list[ManagedProductGroup]:
        source_id = source_references[0].source_id if source_references else None
        run_interval = self._run_interval(viewer_package)
        items_by_group: dict[str, list[ManagedProductGroupItem]] = {
            definition.group_key: [] for definition in PRODUCT_GROUP_ORDER
        }

        context_terms = [
            viewer_package_reference.viewer_package_id,
            viewer_package_reference.dataset_id,
            viewer_package_reference.representation_id,
            *(source.display_name for source in source_references),
            *(source.file_name for source in source_references if source.file_name),
        ]

        for track in viewer_package.tracks:
            for curve in track.curves:
                item = self._product_item_from_curve(
                    curve=curve,
                    run_interval=run_interval,
                    run_date=run_date,
                    run_number=run_number,
                    source_id=source_id,
                    viewer_package_reference=viewer_package_reference,
                    context_terms=context_terms,
                )
                group_key = item.product_category if item.product_category in items_by_group else "other_review_required"
                items_by_group[group_key].append(item)

        supporting_document_items = [
            ManagedProductGroupItem(
                product_id=f"source-reference:{source.source_id}",
                display_name=source.display_name,
                curve_name=source.display_name,
                curve_type=source.file_format or (source.source_kind.value if hasattr(source.source_kind, "value") else str(source.source_kind)),
                curve_description=source.file_format or (source.source_kind.value if hasattr(source.source_kind, "value") else str(source.source_kind)),
                curve_unit=None,
                product_category="supporting_documents",
                product_subgroup_key=None,
                product_subgroup_label=None,
                curve_family="Supporting Document",
                classification_confidence="high",
                classification_source="managed_source_reference",
                classification_reasons=["Source reference was registered as a supporting inventory item."],
                review_required=False,
                run_date="—",
                run_interval="—",
                run_number="—",
                qa_flag="Pending",
                selectable=True,
                source_kind=source.source_kind.value if hasattr(source.source_kind, "value") else str(source.source_kind),
                source_id=source.source_id,
                viewer_package_id=None,
            )
            for source in source_references
        ]
        items_by_group["supporting_documents"].extend(supporting_document_items)

        return [
            ManagedProductGroup(
                group_key=definition.group_key,
                group_label=definition.group_label,
                items=items_by_group[definition.group_key],
            )
            for definition in PRODUCT_GROUP_ORDER
        ]

    @staticmethod
    def _product_item_from_curve(
        *,
        curve: Curve,
        run_interval: str,
        run_date: str,
        run_number: str,
        source_id: str | None,
        viewer_package_reference: ViewerPackageReference,
        context_terms: list[str | None] | None = None,
    ) -> ManagedProductGroupItem:
        curve_name = curve.mnemonic or curve.normalized_name or curve.curve_id
        curve_description = ManagedWellInventoryService._curve_description(curve)
        curve_unit = ManagedWellInventoryService._curve_unit(curve)
        classification = classify_well_log_curve(
            mnemonic=curve_name,
            description=curve_description,
            unit=curve_unit,
            context_terms=context_terms or [],
        )
        product_id = f"curve:{viewer_package_reference.well_id}:{curve.curve_id}"
        return ManagedProductGroupItem(
            product_id=product_id,
            well_uid=viewer_package_reference.well_id,
            source_uid=source_id,
            kr_curve_type_id=ManagedWellInventoryService._kr_curve_type_id_from_classification(classification),
            observed_mnemonic=curve_name,
            normalized_mnemonic=ManagedWellInventoryService._normalized_mnemonic(curve_name),
            display_name=curve_name,
            curve_name=curve_name,
            curve_type=classification.curve_description,
            curve_description=classification.curve_description,
            curve_unit=classification.curve_unit,
            product_category=classification.product_category,
            product_subgroup_key=classification.product_subgroup_key,
            product_subgroup_label=classification.product_subgroup_label,
            curve_family=classification.curve_family,
            classification_confidence=classification.classification_confidence,
            classification_source=classification.classification_source,
            classification_reasons=classification.classification_reasons,
            review_required=classification.review_required,
            run_date=run_date or "—",
            run_interval=run_interval,
            run_number=run_number or "—",
            qa_flag="Review" if classification.review_required else "Passed",
            selectable=True,
            source_kind=ManagedSourceKind.LAS.value,
            source_id=source_id,
            viewer_package_id=viewer_package_reference.viewer_package_id,
        )

    @staticmethod
    def _managed_well_identity(record: ManagedWellRecord | Any) -> str | None:
        """Return the stable well identity available on a managed record.

        Some backend contract builders operate on partial record projections.
        Identity resolution must therefore tolerate absent optional attributes
        while remaining deterministic from the product item when no well
        identity is available.
        """

        return (
            getattr(record, "well_id", None)
            or getattr(record, "managed_well_id", None)
        )

    @staticmethod
    def _normalized_mnemonic(value: str | None) -> str | None:
        text = str(value or "").strip().upper()
        return text or None

    @staticmethod
    def _kr_curve_type_id_from_classification(classification: Any) -> str | None:
        for attr in ("canonical_curve_id", "curve_family", "product_subgroup_key", "product_category"):
            value = getattr(classification, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip().lower().replace("-", "_").replace("/", "_").replace(" ", "_")
        return None

    @staticmethod
    def _curve_description(curve: Curve) -> str | None:
        for attr in ("description", "display_name", "long_name", "normalized_name"):
            value = getattr(curve, attr, None)
            if isinstance(value, str) and value.strip() and value.strip().upper() != (curve.mnemonic or "").upper():
                return value.strip()
        metadata = getattr(curve, "metadata", None)
        if isinstance(metadata, dict):
            for key in ("description", "long_name", "curve_description"):
                value = metadata.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @staticmethod
    def _curve_unit(curve: Curve) -> str | None:
        value = getattr(curve, "unit", None)
        if isinstance(value, str) and value.strip():
            return value.strip()
        metadata = getattr(curve, "metadata", None)
        if isinstance(metadata, dict):
            value = metadata.get("unit")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _curve_type_label(curve: Curve) -> str:
        mnemonic = (curve.mnemonic or curve.curve_id).upper()
        if mnemonic in {"GR", "CGR", "SGR"}:
            return "Gamma ray"
        if mnemonic in {"SP"}:
            return "Spontaneous potential"
        if mnemonic in {"AF90", "AT90", "ILD", "ILM", "LLD", "LLS", "RT", "RXO"}:
            return "Resistivity"
        if mnemonic in {"RHOB", "RHOZ", "DEN"}:
            return "Density"
        if mnemonic in {"NPHI", "TNPH", "NPOR"}:
            return "Neutron porosity"
        if mnemonic in {"DT", "DTCO", "DTSM", "DTC", "DTS"}:
            return "Sonic"
        if mnemonic in {"CALI", "CAL", "HCAL"}:
            return "Caliper"
        if mnemonic in {"PEF", "PE"}:
            return "Photoelectric factor"
        return curve.normalized_name or mnemonic.title()

    @staticmethod
    def _run_interval(viewer_package: WellMultitrackV1) -> str:
        depth_unit = viewer_package.depth_unit.value if hasattr(viewer_package.depth_unit, "value") else str(viewer_package.depth_unit)
        return f"{viewer_package.depth_range.min:g}–{viewer_package.depth_range.max:g} {depth_unit}"

    @staticmethod
    def _viewer_package_reference(viewer_package: WellMultitrackV1) -> ViewerPackageReference:
        return ViewerPackageReference(
            viewer_package_id=f"viewer-package:{viewer_package.representation_id}",
            viewer_package_version=viewer_package.viewer_package_version,
            dataset_id=viewer_package.dataset_id,
            representation_id=viewer_package.representation_id,
            well_id=viewer_package.well_id,
            endpoint=f"/api/wlv/wells/{viewer_package.well_id}/viewer-package",
            status=ManagedInventoryLifecycleState.VIEWER_READY,
        )

    @staticmethod
    def _lifecycle_counts(records: list[ManagedWellRecord]) -> dict[str, int]:
        counts = Counter(record.lifecycle_state.value for record in records)
        return dict(sorted(counts.items()))

    @staticmethod
    def _issue(
        severity: str,
        code: str,
        message: str,
        managed_well_id: str | None = None,
        field: str | None = None,
    ) -> ManagedInventoryValidationIssue:
        return ManagedInventoryValidationIssue(
            severity=InventoryValidationSeverity(severity),
            code=code,
            message=message,
            managed_well_id=managed_well_id,
            field=field,
        )

    def _validate_record(self, record: ManagedWellRecord) -> list[ManagedInventoryValidationIssue]:
        issues: list[ManagedInventoryValidationIssue] = []
        if not record.managed_well_id.strip():
            issues.append(self._issue("error", "missing_managed_well_id", "Managed well id is required.", field="managed_well_id"))
        if not record.well_id.strip():
            issues.append(self._issue("error", "missing_well_id", "Well id is required.", record.managed_well_id, "well_id"))
        if not record.well_name.strip():
            issues.append(self._issue("error", "missing_well_name", "Well name is required.", record.managed_well_id, "well_name"))
        if record.top_depth is not None and record.base_depth is not None and record.top_depth >= record.base_depth:
            issues.append(self._issue("error", "invalid_depth_range", "Top depth must be less than base depth.", record.managed_well_id, "depth_range"))
        if record.status != record.lifecycle_state:
            issues.append(self._issue("warning", "status_lifecycle_mismatch", "status and lifecycle_state should remain aligned.", record.managed_well_id, "status"))
        if record.lifecycle_state == ManagedInventoryLifecycleState.VIEWER_READY and not record.viewer_packages:
            issues.append(self._issue("error", "viewer_ready_without_package", "viewer_ready records require at least one viewer package.", record.managed_well_id, "viewer_packages"))
        loaded_wdv_items = self._loaded_wdv_product_items(record)
        if loaded_wdv_items and not isinstance(record.metadata.get("wdv_load_session_contract"), dict):
            issues.append(self._issue("error", "wdv_loaded_without_session", "loaded_to_wdv products require a backend-owned WDV load session package.", record.managed_well_id, "metadata.wdv_load_session_contract"))
        if not record.source_references:
            issues.append(self._issue("warning", "missing_source_reference", "Managed record has no source references.", record.managed_well_id, "source_references"))
        for source in record.source_references:
            if not source.source_id.strip():
                issues.append(self._issue("error", "missing_source_id", "Source reference id is required.", record.managed_well_id, "source_id"))
            if not source.display_name.strip():
                issues.append(self._issue("warning", "missing_source_display_name", "Source display name is empty.", record.managed_well_id, "source_references.display_name"))
            if source.source_kind == ManagedSourceKind.LAS and not source.checksum:
                issues.append(self._issue("warning", "las_source_missing_checksum", "LAS source references should retain a source fingerprint/checksum.", record.managed_well_id, "source_references.checksum"))
        if "ingested-source" in record.tags or record.metadata.get("source_format") == "las":
            if not record.metadata.get("source_fingerprint"):
                issues.append(self._issue("warning", "ingested_source_missing_fingerprint", "Ingested sources should retain source fingerprint evidence.", record.managed_well_id, "metadata.source_fingerprint"))
            if not record.metadata.get("ingestion_evidence"):
                issues.append(self._issue("warning", "ingested_source_missing_evidence", "Ingested sources should retain extraction evidence records.", record.managed_well_id, "metadata.ingestion_evidence"))
            if not record.metadata.get("ingestion_qaqc_summary"):
                issues.append(self._issue("warning", "ingested_source_missing_qaqc_summary", "Ingested sources should retain an ingestion QAQC summary.", record.managed_well_id, "metadata.ingestion_qaqc_summary"))
        for package in record.viewer_packages:
            if not package.viewer_package_id.strip():
                issues.append(self._issue("error", "missing_viewer_package_id", "Viewer package id is required.", record.managed_well_id, "viewer_package_id"))
            if package.well_id != record.well_id:
                issues.append(self._issue("error", "viewer_package_well_mismatch", "Viewer package well_id does not match managed record well_id.", record.managed_well_id, "viewer_packages.well_id"))
            if not package.endpoint.startswith("/api/wlv/"):
                issues.append(self._issue("warning", "non_wlv_viewer_package_endpoint", "Viewer package endpoint should be a WLV API path.", record.managed_well_id, "viewer_packages.endpoint"))
        return issues
