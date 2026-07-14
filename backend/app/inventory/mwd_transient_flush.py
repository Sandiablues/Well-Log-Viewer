"""Atomic global transient MWD flush lifecycle service."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from pydantic import BaseModel, Field
from app.source_intake.models import SourceIntakeResolutionState, SourceIntakeSnapshot, utc_now_iso as source_intake_utc_now_iso
from app.source_intake.readiness import evaluate_registration_readiness
from .managed_well_purge import ManagedWellPurgeService
from .models import ManagedInventorySnapshot, utc_now_iso
from .repository import ManagedInventoryStoreError, ManagedWellInventoryRepository


class MwdTransientFlushRequest(BaseModel):
    confirm: Literal["FLUSH_MWD_TRANSIENT_DATA"]
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    dry_run: bool = False


class MwdTransientFlushResponse(BaseModel):
    ok: bool = True
    action: str = "flush_mwd_transient_data"
    destructive: bool = True
    dry_run: bool
    removed_managed_well_count: int
    removed_product_count: int
    removed_source_reference_count: int
    removed_viewer_package_count: int
    removed_workspace_loaded_count: int
    removed_canonical_session_count: int
    removed_command_receipt_group_count: int
    reset_source_candidate_count: int
    preserved_source_candidate_count: int
    audit: dict[str, Any] = Field(default_factory=dict)


class MwdTransientFlushService:
    """Backend-owned, global destructive flush for transient MWD state."""

    _lock = RLock()

    def __init__(self, repository: ManagedWellInventoryRepository | None = None, *, source_intake_path: Path | None = None, workspace_path: Path | None = None, canonical_session_path: Path | None = None) -> None:
        self.repository = repository or ManagedWellInventoryRepository()
        backend_root = Path(__file__).resolve().parents[2]
        self.source_intake_path = source_intake_path or (backend_root / "data" / "source_intake" / "source_intake.json")
        self.workspace_path = workspace_path or self.repository.storage_path.with_name("wdv_workspace.json")
        self.canonical_session_path = canonical_session_path or self._canonical_session_path(backend_root)

    @staticmethod
    def _canonical_session_path(backend_root: Path) -> Path:
        override = os.environ.get("WLV_WDV_CANONICAL_SESSION_STORE")
        if override:
            return Path(override).expanduser().resolve()
        return backend_root / "data" / "wdv" / "canonical_sessions_v2_1.json"

    def flush(self, *, request: MwdTransientFlushRequest) -> MwdTransientFlushResponse:
        if request.confirm != "FLUSH_MWD_TRANSIENT_DATA":
            raise ValueError("Explicit FLUSH_MWD_TRANSIENT_DATA confirmation is required.")

        with self._lock:
            inventory_before = self.repository.snapshot()
            source_before = self._read_source_snapshot()
            workspace_before = ManagedWellPurgeService._read_json_optional(self.workspace_path, default={})
            canonical_before = ManagedWellPurgeService._read_json_optional(
                self.canonical_session_path,
                default={"schema_version": "wdv_canonical_sessions_v2_1", "sessions": {}, "command_receipts": {}},
            )

            managed_well_ids = {record.managed_well_id for record in inventory_before.records}
            managed_well_uids = {str(record.managed_well_uid) for record in inventory_before.records if record.managed_well_uid is not None}

            inventory_after = inventory_before.model_copy(update={"records": [], "updated_at": utc_now_iso()})
            source_after, reset_candidate_ids = self._reset_linked_source_candidates(
                source_before,
                managed_well_ids=managed_well_ids,
                actor=request.actor,
                reason=request.reason,
            )
            workspace_after, workspace_removed = self._empty_workspace(workspace_before)
            canonical_after, session_removed, receipts_removed = self._remove_managed_canonical_state(
                canonical_before,
                managed_well_uids=managed_well_uids,
            )

            self._validate_transition(
                inventory_after=inventory_after,
                source_before=source_before,
                source_after=source_after,
                reset_candidate_ids=reset_candidate_ids,
                managed_well_ids=managed_well_ids,
                managed_well_uids=managed_well_uids,
                workspace_after=workspace_after,
                canonical_after=canonical_after,
            )

            response = self._response(
                request=request,
                inventory_before=inventory_before,
                source_after=source_after,
                reset_candidate_ids=reset_candidate_ids,
                workspace_removed=workspace_removed,
                session_removed=session_removed,
                receipts_removed=receipts_removed,
            )
            if request.dry_run:
                return response

            payloads: dict[Path, bytes] = {
                self.repository.storage_path: ManagedWellPurgeService._json_bytes(inventory_after.model_dump(mode="json")),
                self.source_intake_path: ManagedWellPurgeService._json_bytes(source_after.model_dump(mode="json")),
                self.workspace_path: ManagedWellPurgeService._json_bytes(workspace_after),
            }
            if self.canonical_session_path.exists() or session_removed or receipts_removed:
                payloads[self.canonical_session_path] = ManagedWellPurgeService._json_bytes(canonical_after)

            originals = {path: path.read_bytes() if path.exists() else None for path in payloads}
            try:
                ManagedWellPurgeService._promote_all(payloads)
                self._post_write_validate(managed_well_uids=managed_well_uids, reset_candidate_ids=reset_candidate_ids)
            except Exception as exc:
                ManagedWellPurgeService._restore_all(originals)
                raise ManagedInventoryStoreError("Global transient MWD flush failed; all touched stores were restored.") from exc
            return response

    @staticmethod
    def _reset_linked_source_candidates(snapshot: SourceIntakeSnapshot, *, managed_well_ids: set[str], actor: str, reason: str) -> tuple[SourceIntakeSnapshot, set[str]]:
        candidates = []
        reset_ids: set[str] = set()
        for original in snapshot.candidates:
            candidate = deepcopy(original)
            if candidate.managed_well_id in managed_well_ids:
                reset_ids.add(candidate.source_file_id)
                candidate.registration_status = "not_registered"
                candidate.resolution_state = SourceIntakeResolutionState.RESOLVED
                candidate.managed_well_id = None
                candidate.managed_well_name = None
                candidate.wmdp_state = None
                candidate.wdv_state = None
                candidate.registered_product_count = 0
                candidate.registered_curve_count = 0
                candidate.registered_trajectory_count = 0
                candidate.resolved_by = actor
                candidate.resolved_at = source_intake_utc_now_iso()
                candidate.resolution_reason = reason
                evaluate_registration_readiness(candidate)
            candidates.append(candidate)
        return snapshot.model_copy(update={"candidates": candidates, "updated_at": source_intake_utc_now_iso()}), reset_ids

    @staticmethod
    def _empty_workspace(workspace: dict[str, Any]) -> tuple[dict[str, Any], int]:
        removed = max(len(list(workspace.get("loaded_managed_well_ids") or [])), len(list(workspace.get("loaded_managed_well_uids") or [])))
        updated = dict(workspace)
        updated.update({
            "schema_version": str(workspace.get("schema_version") or "wlv_wdv_workspace_v2"),
            "workspace_id": str(workspace.get("workspace_id") or "default"),
            "revision": int(workspace.get("revision", 0) or 0) + 1,
            "active_managed_well_id": None,
            "active_managed_well_uid": None,
            "loaded_managed_well_ids": [],
            "loaded_managed_well_uids": [],
            "updated_at": utc_now_iso(),
        })
        return updated, removed

    @staticmethod
    def _remove_managed_canonical_state(store: dict[str, Any], *, managed_well_uids: set[str]) -> tuple[dict[str, Any], int, int]:
        updated = deepcopy(store)
        sessions = updated.setdefault("sessions", {})
        receipts = updated.setdefault("command_receipts", {})
        session_removed = sum(1 for uid in managed_well_uids if uid in sessions)
        receipts_removed = sum(1 for uid in managed_well_uids if uid in receipts)
        for uid in managed_well_uids:
            sessions.pop(uid, None)
            receipts.pop(uid, None)
        return updated, session_removed, receipts_removed

    @staticmethod
    def _validate_transition(*, inventory_after: ManagedInventorySnapshot, source_before: SourceIntakeSnapshot, source_after: SourceIntakeSnapshot, reset_candidate_ids: set[str], managed_well_ids: set[str], managed_well_uids: set[str], workspace_after: dict[str, Any], canonical_after: dict[str, Any]) -> None:
        if inventory_after.records:
            raise ValueError("Managed inventory is not empty after flush planning.")
        before_by_id = {candidate.source_file_id: candidate for candidate in source_before.candidates}
        after_by_id = {candidate.source_file_id: candidate for candidate in source_after.candidates}
        if set(before_by_id) != set(after_by_id):
            raise ValueError("Source Intake candidate membership changed during flush.")
        for candidate_id, before in before_by_id.items():
            after = after_by_id[candidate_id]
            if candidate_id not in reset_candidate_ids:
                if before.model_dump(mode="json") != after.model_dump(mode="json"):
                    raise ValueError("Unrelated Source Intake candidate changed during flush planning.")
                continue
            if before.managed_well_id not in managed_well_ids:
                raise ValueError("A reset Source Intake candidate was not linked to flushed managed data.")
            if after.managed_well_id is not None or after.registration_status != "not_registered" or after.resolution_state != SourceIntakeResolutionState.RESOLVED:
                raise ValueError("A reset Source Intake candidate is not reloadable.")
            if any(value != 0 for value in (after.registered_product_count, after.registered_curve_count, after.registered_trajectory_count)):
                raise ValueError("A reset Source Intake candidate retains registered object counts.")
        if list(workspace_after.get("loaded_managed_well_ids") or []) or list(workspace_after.get("loaded_managed_well_uids") or []):
            raise ValueError("WDV workspace still contains managed wells.")
        if workspace_after.get("active_managed_well_id") is not None or workspace_after.get("active_managed_well_uid") is not None:
            raise ValueError("WDV workspace still has an active managed well.")
        sessions = canonical_after.get("sessions") or {}
        receipts = canonical_after.get("command_receipts") or {}
        if managed_well_uids & set(map(str, sessions.keys())) or managed_well_uids & set(map(str, receipts.keys())):
            raise ValueError("Canonical WDV state remains for flushed managed wells.")

    @staticmethod
    def _response(*, request: MwdTransientFlushRequest, inventory_before: ManagedInventorySnapshot, source_after: SourceIntakeSnapshot, reset_candidate_ids: set[str], workspace_removed: int, session_removed: int, receipts_removed: int) -> MwdTransientFlushResponse:
        return MwdTransientFlushResponse(
            dry_run=request.dry_run,
            removed_managed_well_count=len(inventory_before.records),
            removed_product_count=sum(len(group.items) for record in inventory_before.records for group in record.product_groups),
            removed_source_reference_count=sum(len(record.source_references) for record in inventory_before.records),
            removed_viewer_package_count=sum(len(record.viewer_packages) for record in inventory_before.records),
            removed_workspace_loaded_count=workspace_removed,
            removed_canonical_session_count=session_removed,
            removed_command_receipt_group_count=receipts_removed,
            reset_source_candidate_count=len(reset_candidate_ids),
            preserved_source_candidate_count=len(source_after.candidates) - len(reset_candidate_ids),
            audit={
                "actor": request.actor,
                "reason": request.reason,
                "target_managed_well_ids": sorted(record.managed_well_id for record in inventory_before.records),
                "target_managed_well_uids": sorted(str(record.managed_well_uid) for record in inventory_before.records if record.managed_well_uid is not None),
                "reset_source_candidate_ids": sorted(reset_candidate_ids),
            },
        )

    def _post_write_validate(self, *, managed_well_uids: set[str], reset_candidate_ids: set[str]) -> None:
        if self.repository.snapshot().records:
            raise ValueError("Managed inventory is not empty after committed flush.")
        source = self._read_source_snapshot()
        for candidate in source.candidates:
            if candidate.source_file_id in reset_candidate_ids and (candidate.managed_well_id is not None or candidate.registration_status != "not_registered"):
                raise ValueError("A reset Source Intake candidate remains linked after committed flush.")
        workspace = ManagedWellPurgeService._read_json_optional(self.workspace_path, default={})
        if list(workspace.get("loaded_managed_well_ids") or []) or list(workspace.get("loaded_managed_well_uids") or []):
            raise ValueError("WDV workspace survived committed flush.")
        canonical = ManagedWellPurgeService._read_json_optional(self.canonical_session_path, default={"sessions": {}, "command_receipts": {}})
        sessions = canonical.get("sessions") or {}
        receipts = canonical.get("command_receipts") or {}
        if managed_well_uids & set(map(str, sessions.keys())) or managed_well_uids & set(map(str, receipts.keys())):
            raise ValueError("Canonical WDV state survived committed flush.")

    def _read_source_snapshot(self) -> SourceIntakeSnapshot:
        if not self.source_intake_path.exists():
            raise ManagedInventoryStoreError(f"Source Intake store not found: {self.source_intake_path}")
        try:
            return SourceIntakeSnapshot.model_validate(json.loads(self.source_intake_path.read_text()))
        except Exception as exc:
            raise ManagedInventoryStoreError(f"Invalid Source Intake store: {self.source_intake_path}") from exc
