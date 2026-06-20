"""Atomic managed-well purge and WSI reset lifecycle service.

This service owns the destructive boundary between Managed Well Inventory,
WDV workspace/session state, and Source Intake registration state. It targets
one canonical managed well only and preserves all unrelated records.
"""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.source_intake.models import (
    SourceIntakeResolutionState,
    SourceIntakeSnapshot,
    utc_now_iso as source_intake_utc_now_iso,
)
from app.source_intake.readiness import evaluate_registration_readiness

from .models import ManagedInventorySnapshot, ManagedWellRecord, utc_now_iso
from .repository import (
    ManagedInventoryStoreError,
    ManagedWellInventoryRepository,
    ManagedWellNotFoundError,
)


class ManagedWellPurgeRequest(BaseModel):
    confirm: Literal["PURGE_AND_RESET"]
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    dry_run: bool = False


class ManagedWellPurgeResponse(BaseModel):
    ok: bool = True
    action: str = "purge_managed_well_and_reset_wsi"
    destructive: bool = True
    dry_run: bool
    managed_well_id: str
    managed_well_uid: str
    well_name: str
    removed_msi_record_count: int
    removed_product_count: int
    removed_source_reference_count: int
    removed_viewer_package_count: int
    removed_workspace_loaded_count: int
    removed_canonical_session_count: int
    removed_command_receipt_group_count: int
    reset_source_candidate_count: int
    preserved_msi_record_count: int
    preserved_source_candidate_count: int
    audit: dict[str, Any] = Field(default_factory=dict)


class ManagedWellPurgeService:
    """Backend-owned, one-well destructive lifecycle operation."""

    _lock = RLock()

    def __init__(
        self,
        repository: ManagedWellInventoryRepository | None = None,
        *,
        source_intake_path: Path | None = None,
        workspace_path: Path | None = None,
        canonical_session_path: Path | None = None,
    ) -> None:
        self.repository = repository or ManagedWellInventoryRepository()
        backend_root = Path(__file__).resolve().parents[2]
        self.source_intake_path = source_intake_path or (
            backend_root / "data" / "source_intake" / "source_intake.json"
        )
        self.workspace_path = workspace_path or self.repository.storage_path.with_name(
            "wdv_workspace.json"
        )
        self.canonical_session_path = canonical_session_path or self._canonical_session_path(
            backend_root
        )

    @staticmethod
    def _canonical_session_path(backend_root: Path) -> Path:
        override = os.environ.get("WLV_WDV_CANONICAL_SESSION_STORE")
        if override:
            return Path(override).expanduser().resolve()
        return backend_root / "data" / "wdv" / "canonical_sessions_v2_1.json"

    def purge_and_reset(
        self,
        *,
        well_reference: str,
        request: ManagedWellPurgeRequest,
    ) -> ManagedWellPurgeResponse:
        if request.confirm != "PURGE_AND_RESET":
            raise ValueError("Explicit PURGE_AND_RESET confirmation is required.")

        with self._lock:
            inventory_before = self.repository.snapshot()
            source_before = self._read_source_snapshot()
            workspace_before = self._read_json_optional(self.workspace_path, default={})
            canonical_before = self._read_json_optional(
                self.canonical_session_path,
                default={"schema_version": "wdv_canonical_sessions_v2_1", "sessions": {}, "command_receipts": {}},
            )

            target = self._resolve_target(well_reference, inventory_before.records)
            if target.managed_well_uid is None:
                raise ValueError(
                    f"Managed well lacks canonical UUIDv7 identity: {target.managed_well_id}"
                )

            target_uid = str(target.managed_well_uid)
            linked_candidates = [
                candidate
                for candidate in source_before.candidates
                if candidate.managed_well_id == target.managed_well_id
            ]
            if not linked_candidates:
                raise ValueError(
                    "No Source Intake candidates are linked to the target managed well; "
                    "purge would make controlled reload impossible."
                )

            inventory_after = self._inventory_without_target(inventory_before, target)
            source_after = self._source_reset_for_target(
                source_before,
                target=target,
                actor=request.actor,
                reason=request.reason,
            )
            workspace_after, workspace_removed = self._workspace_without_target(
                workspace_before,
                target=target,
                remaining_records=inventory_after.records,
            )
            canonical_after, session_removed, receipts_removed = self._canonical_without_target(
                canonical_before,
                target_uid=target_uid,
            )

            self._validate_transition(
                target=target,
                inventory_before=inventory_before,
                inventory_after=inventory_after,
                source_before=source_before,
                source_after=source_after,
                workspace_after=workspace_after,
                canonical_after=canonical_after,
            )

            response = self._response(
                request=request,
                target=target,
                inventory_after=inventory_after,
                source_before=source_before,
                source_after=source_after,
                linked_candidates=linked_candidates,
                workspace_removed=workspace_removed,
                session_removed=session_removed,
                receipts_removed=receipts_removed,
            )
            if request.dry_run:
                return response

            payloads: dict[Path, bytes] = {
                self.repository.storage_path: self._json_bytes(
                    inventory_after.model_dump(mode="json")
                ),
                self.source_intake_path: self._json_bytes(
                    source_after.model_dump(mode="json")
                ),
                self.workspace_path: self._json_bytes(workspace_after),
            }
            if self.canonical_session_path.exists() or session_removed or receipts_removed:
                payloads[self.canonical_session_path] = self._json_bytes(canonical_after)

            originals = {
                path: path.read_bytes() if path.exists() else None
                for path in payloads
            }

            try:
                self._promote_all(payloads)
                self._post_write_validate(target)
            except Exception as exc:
                self._restore_all(originals)
                raise ManagedInventoryStoreError(
                    "Managed-well purge failed; all touched stores were restored."
                ) from exc

            return response

    @staticmethod
    def _resolve_target(
        reference: str,
        records: list[ManagedWellRecord],
    ) -> ManagedWellRecord:
        matches = [
            record
            for record in records
            if reference in {
                record.managed_well_id,
                str(record.managed_well_uid or ""),
                record.well_id,
            }
        ]
        if len(matches) != 1:
            if not matches:
                raise ManagedWellNotFoundError(reference)
            raise ValueError(f"Managed well reference is ambiguous: {reference}")
        return matches[0]

    @staticmethod
    def _inventory_without_target(
        snapshot: ManagedInventorySnapshot,
        target: ManagedWellRecord,
    ) -> ManagedInventorySnapshot:
        remaining = [
            deepcopy(record)
            for record in snapshot.records
            if record.managed_well_id != target.managed_well_id
        ]
        return snapshot.model_copy(
            update={"records": remaining, "updated_at": utc_now_iso()}
        )

    @staticmethod
    def _source_reset_for_target(
        snapshot: SourceIntakeSnapshot,
        *,
        target: ManagedWellRecord,
        actor: str,
        reason: str,
    ) -> SourceIntakeSnapshot:
        candidates = []
        for original in snapshot.candidates:
            candidate = deepcopy(original)
            if candidate.managed_well_id == target.managed_well_id:
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
        return snapshot.model_copy(
            update={
                "candidates": candidates,
                "updated_at": source_intake_utc_now_iso(),
            }
        )

    @staticmethod
    def _workspace_without_target(
        workspace: dict[str, Any],
        *,
        target: ManagedWellRecord,
        remaining_records: list[ManagedWellRecord],
    ) -> tuple[dict[str, Any], int]:
        target_uid = str(target.managed_well_uid)
        ids = [
            value
            for value in list(workspace.get("loaded_managed_well_ids") or [])
            if value != target.managed_well_id
        ]
        uids = [
            value
            for value in list(workspace.get("loaded_managed_well_uids") or [])
            if str(value) != target_uid
        ]
        removed = int(
            target.managed_well_id in list(workspace.get("loaded_managed_well_ids") or [])
            or target_uid in [str(value) for value in list(workspace.get("loaded_managed_well_uids") or [])]
        )

        by_id = {record.managed_well_id: record for record in remaining_records}
        valid_pairs = [
            (managed_id, str(by_id[managed_id].managed_well_uid))
            for managed_id in ids
            if managed_id in by_id and by_id[managed_id].managed_well_uid is not None
        ]
        ids = [item[0] for item in valid_pairs]
        uids = [item[1] for item in valid_pairs]

        active_id = workspace.get("active_managed_well_id")
        active_uid = str(workspace.get("active_managed_well_uid") or "")
        if active_id == target.managed_well_id or active_uid == target_uid:
            active_id = ids[0] if ids else None
            active_uid = uids[0] if uids else None
        elif active_id not in ids:
            active_id = ids[0] if ids else None
            active_uid = uids[0] if uids else None
        else:
            active_uid = str(by_id[active_id].managed_well_uid)

        updated = dict(workspace)
        updated.update(
            {
                "schema_version": str(workspace.get("schema_version") or "wlv_wdv_workspace_v2"),
                "workspace_id": str(workspace.get("workspace_id") or "default"),
                "revision": int(workspace.get("revision", 0) or 0) + 1,
                "active_managed_well_id": active_id,
                "active_managed_well_uid": active_uid,
                "loaded_managed_well_ids": ids,
                "loaded_managed_well_uids": uids,
                "updated_at": utc_now_iso(),
            }
        )
        return updated, removed

    @staticmethod
    def _canonical_without_target(
        store: dict[str, Any],
        *,
        target_uid: str,
    ) -> tuple[dict[str, Any], int, int]:
        updated = deepcopy(store)
        sessions = updated.setdefault("sessions", {})
        receipts = updated.setdefault("command_receipts", {})
        session_removed = int(target_uid in sessions)
        receipts_removed = int(target_uid in receipts)
        sessions.pop(target_uid, None)
        receipts.pop(target_uid, None)
        return updated, session_removed, receipts_removed

    @staticmethod
    def _validate_transition(
        *,
        target: ManagedWellRecord,
        inventory_before: ManagedInventorySnapshot,
        inventory_after: ManagedInventorySnapshot,
        source_before: SourceIntakeSnapshot,
        source_after: SourceIntakeSnapshot,
        workspace_after: dict[str, Any],
        canonical_after: dict[str, Any],
    ) -> None:
        target_uid = str(target.managed_well_uid)
        before_other = {
            record.managed_well_id: record.model_dump(mode="json")
            for record in inventory_before.records
            if record.managed_well_id != target.managed_well_id
        }
        after_other = {
            record.managed_well_id: record.model_dump(mode="json")
            for record in inventory_after.records
        }
        if before_other != after_other:
            raise ValueError("Unrelated MSI records changed during purge planning.")

        if any(
            record.managed_well_id == target.managed_well_id
            for record in inventory_after.records
        ):
            raise ValueError("Target MSI record remains after purge planning.")

        before_unrelated = {
            candidate.source_file_id: candidate.model_dump(mode="json")
            for candidate in source_before.candidates
            if candidate.managed_well_id != target.managed_well_id
        }
        after_unrelated = {
            candidate.source_file_id: candidate.model_dump(mode="json")
            for candidate in source_after.candidates
            if candidate.source_file_id in before_unrelated
        }
        if before_unrelated != after_unrelated:
            raise ValueError("Unrelated Source Intake candidates changed during purge planning.")

        linked_after = [
            candidate
            for candidate in source_after.candidates
            if candidate.source_file_id
            in {
                item.source_file_id
                for item in source_before.candidates
                if item.managed_well_id == target.managed_well_id
            }
        ]
        if not linked_after:
            raise ValueError("Target Source Intake candidates were not preserved.")
        for candidate in linked_after:
            if candidate.managed_well_id is not None:
                raise ValueError("A target Source Intake candidate remains linked to MSI.")
            if candidate.registration_status != "not_registered":
                raise ValueError("A target Source Intake candidate remains registered.")
            if candidate.resolution_state != SourceIntakeResolutionState.RESOLVED:
                raise ValueError("A target Source Intake candidate is not reloadable.")

        if target.managed_well_id in list(workspace_after.get("loaded_managed_well_ids") or []):
            raise ValueError("Target remains in WDV workspace by legacy ID.")
        if target_uid in [str(value) for value in list(workspace_after.get("loaded_managed_well_uids") or [])]:
            raise ValueError("Target remains in WDV workspace by UUIDv7.")

        if target_uid in (canonical_after.get("sessions") or {}):
            raise ValueError("Target canonical session remains.")
        if target_uid in (canonical_after.get("command_receipts") or {}):
            raise ValueError("Target canonical command receipts remain.")

    def _response(
        self,
        *,
        request: ManagedWellPurgeRequest,
        target: ManagedWellRecord,
        inventory_after: ManagedInventorySnapshot,
        source_before: SourceIntakeSnapshot,
        source_after: SourceIntakeSnapshot,
        linked_candidates: list[Any],
        workspace_removed: int,
        session_removed: int,
        receipts_removed: int,
    ) -> ManagedWellPurgeResponse:
        product_count = sum(
            len(group.items)
            for group in target.product_groups
        )
        linked_ids = {candidate.source_file_id for candidate in linked_candidates}
        return ManagedWellPurgeResponse(
            dry_run=request.dry_run,
            managed_well_id=target.managed_well_id,
            managed_well_uid=str(target.managed_well_uid),
            well_name=target.well_name,
            removed_msi_record_count=1,
            removed_product_count=product_count,
            removed_source_reference_count=len(target.source_references),
            removed_viewer_package_count=len(target.viewer_packages),
            removed_workspace_loaded_count=workspace_removed,
            removed_canonical_session_count=session_removed,
            removed_command_receipt_group_count=receipts_removed,
            reset_source_candidate_count=len(linked_candidates),
            preserved_msi_record_count=len(inventory_after.records),
            preserved_source_candidate_count=len(source_after.candidates) - len(linked_ids),
            audit={
                "actor": request.actor,
                "reason": request.reason,
                "target_source_candidate_ids": sorted(linked_ids),
                "inventory_path": str(self.repository.storage_path),
                "source_intake_path": str(self.source_intake_path),
                "workspace_path": str(self.workspace_path),
                "canonical_session_path": str(self.canonical_session_path),
            },
        )

    def _post_write_validate(self, target: ManagedWellRecord) -> None:
        inventory = self.repository.snapshot()
        source = self._read_source_snapshot()
        workspace = self._read_json_optional(self.workspace_path, default={})
        canonical = self._read_json_optional(
            self.canonical_session_path,
            default={"sessions": {}, "command_receipts": {}},
        )
        if any(
            record.managed_well_id == target.managed_well_id
            for record in inventory.records
        ):
            raise ValueError("Target MSI record survived committed purge.")
        for candidate in source.candidates:
            if candidate.managed_well_id == target.managed_well_id:
                raise ValueError("Target Source Intake linkage survived committed purge.")
        if target.managed_well_id in list(workspace.get("loaded_managed_well_ids") or []):
            raise ValueError("Target WDV workspace linkage survived committed purge.")
        target_uid = str(target.managed_well_uid)
        if target_uid in (canonical.get("sessions") or {}):
            raise ValueError("Target canonical session survived committed purge.")
        if target_uid in (canonical.get("command_receipts") or {}):
            raise ValueError("Target canonical receipts survived committed purge.")

    def _read_source_snapshot(self) -> SourceIntakeSnapshot:
        if not self.source_intake_path.exists():
            raise ManagedInventoryStoreError(
                f"Source Intake store not found: {self.source_intake_path}"
            )
        try:
            return SourceIntakeSnapshot.model_validate(
                json.loads(self.source_intake_path.read_text())
            )
        except Exception as exc:
            raise ManagedInventoryStoreError(
                f"Invalid Source Intake store: {self.source_intake_path}"
            ) from exc

    @staticmethod
    def _read_json_optional(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return deepcopy(default)
        try:
            data = json.loads(path.read_text())
        except Exception as exc:
            raise ManagedInventoryStoreError(f"Invalid JSON store: {path}") from exc
        if not isinstance(data, dict):
            raise ManagedInventoryStoreError(f"JSON store must be an object: {path}")
        return data

    @staticmethod
    def _json_bytes(payload: dict[str, Any]) -> bytes:
        return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")

    @staticmethod
    def _promote_all(payloads: dict[Path, bytes]) -> None:
        staged: dict[Path, Path] = {}
        try:
            for path, payload in payloads.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    "wb",
                    dir=str(path.parent),
                    delete=False,
                ) as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                    staged[path] = Path(handle.name)
            for path, staged_path in staged.items():
                staged_path.replace(path)
        finally:
            for staged_path in staged.values():
                if staged_path.exists():
                    staged_path.unlink()

    @staticmethod
    def _restore_all(originals: dict[Path, bytes | None]) -> None:
        for path, payload in originals.items():
            if payload is None:
                if path.exists():
                    path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "wb",
                dir=str(path.parent),
                delete=False,
            ) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                tmp = Path(handle.name)
            tmp.replace(path)
