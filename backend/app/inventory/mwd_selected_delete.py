"""Backend-owned destructive deletion of selected transient MWD records."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any

from app.source_intake.models import (
    SourceIntakeResolutionState,
    SourceIntakeSnapshot,
    utc_now_iso as source_intake_utc_now_iso,
)
from app.source_intake.readiness import evaluate_registration_readiness

from .managed_well_purge import ManagedWellPurgeService
from .models import (
    ManagedInventorySnapshot,
    ManagedProductGroup,
    ManagedWdvState,
    ManagedWellRecord,
    RemoveManagedDataFromMdpResponse,
    RemoveManagedDataFromMdpResult,
    utc_now_iso,
)
from .repository import (
    ManagedInventoryStoreError,
    ManagedWellInventoryRepository,
    ManagedWellNotFoundError,
)


class SelectedManagedDataDeleteService:
    """Delete exactly the selected transient managed wells/products.

    This service owns a single atomic transition across managed inventory,
    Source Intake linkage, WDV workspace, and canonical transient WDV state.
    Original source files are never opened or changed.
    """

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
        self.canonical_session_path = canonical_session_path or ManagedWellPurgeService._canonical_session_path(
            backend_root
        )

    def delete_selected(
        self,
        *,
        managed_well_ids: list[str] | None = None,
        product_ids: list[str] | None = None,
        actor: str = "mwd-ui",
        reason: str = "Remove selected from MWD",
    ) -> RemoveManagedDataFromMdpResponse:
        well_references = [str(value) for value in (managed_well_ids or []) if str(value).strip()]
        product_references = [str(value) for value in (product_ids or []) if str(value).strip()]
        if not well_references and not product_references:
            raise ValueError("Select at least one managed well or product to delete from MWD.")

        with self._lock:
            inventory_before = self.repository.snapshot()
            source_before = ManagedWellPurgeService._read_json_optional(
                self.source_intake_path,
                default={"schema_version": "wlv_source_intake_v1", "candidates": []},
            )
            source_snapshot = SourceIntakeSnapshot.model_validate(source_before)
            workspace_before = ManagedWellPurgeService._read_json_optional(
                self.workspace_path,
                default={},
            )
            canonical_before = ManagedWellPurgeService._read_json_optional(
                self.canonical_session_path,
                default={
                    "schema_version": "wdv_canonical_sessions_v2_1",
                    "sessions": {},
                    "command_receipts": {},
                },
            )

            resolved_well_ids = self._resolve_well_ids(inventory_before.records, well_references)
            product_owners = self._resolve_product_owners(
                inventory_before.records,
                product_references,
            )

            unresolved_product_references = self._unresolved_product_references(
                inventory_before.records,
                product_references,
            )
            removed_well_ids: list[str] = []
            removed_product_ids: list[str] = []
            touched_well_ids: set[str] = set()
            removed_candidate_ids: set[str] = set()
            records_after: list[ManagedWellRecord] = []

            for original in inventory_before.records:
                record = deepcopy(original)
                full_delete = record.managed_well_id in resolved_well_ids
                selected_for_record = {
                    product_id
                    for product_id, owner_id in product_owners.items()
                    if owner_id == record.managed_well_id
                }

                if full_delete:
                    removed_well_ids.append(record.managed_well_id)
                    touched_well_ids.add(record.managed_well_id)
                    for group in record.product_groups:
                        for item in group.items:
                            removed_product_ids.append(item.product_id)
                            if item.source_intake_candidate_id:
                                removed_candidate_ids.add(item.source_intake_candidate_id)
                    if record.source_intake_candidate_id:
                        removed_candidate_ids.add(record.source_intake_candidate_id)
                    continue

                if not selected_for_record:
                    records_after.append(record)
                    continue

                touched_well_ids.add(record.managed_well_id)
                groups_after: list[ManagedProductGroup] = []
                for group in record.product_groups:
                    retained_items = []
                    for item in group.items:
                        if item.product_id in selected_for_record:
                            removed_product_ids.append(item.product_id)
                            if item.source_intake_candidate_id:
                                removed_candidate_ids.add(item.source_intake_candidate_id)
                        else:
                            retained_items.append(item)
                    if retained_items:
                        groups_after.append(group.model_copy(update={"items": retained_items}))

                remaining_items = [
                    item
                    for group in groups_after
                    for item in group.items
                ]
                if not remaining_items:
                    removed_well_ids.append(record.managed_well_id)
                    if record.source_intake_candidate_id:
                        removed_candidate_ids.add(record.source_intake_candidate_id)
                    continue

                remaining_source_ids = {
                    value
                    for item in remaining_items
                    for value in (
                        item.source_id,
                        item.source_intake_candidate_id,
                    )
                    if value
                }
                remaining_source_uids = {
                    str(item.managed_source_uid)
                    for item in remaining_items
                    if item.managed_source_uid is not None
                }
                source_references = [
                    ref
                    for ref in record.source_references
                    if (
                        ref.source_id in remaining_source_ids
                        or (
                            ref.managed_source_uid is not None
                            and str(ref.managed_source_uid) in remaining_source_uids
                        )
                    )
                ]

                curve_count = sum(
                    1 for item in remaining_items if item.managed_curve_uid is not None
                )
                record = record.model_copy(
                    update={
                        "product_groups": groups_after,
                        "source_references": source_references,
                        "viewer_packages": [],
                        "wdv_state": ManagedWdvState.NOT_LOADED,
                        "loaded_product_count": 0,
                        "viewer_curve_count": curve_count,
                        "displayable_curve_count": curve_count,
                        "updated_at": utc_now_iso(),
                        "metadata": {
                            key: value
                            for key, value in record.metadata.items()
                            if key not in {
                                "wdv_load_session",
                                "wdv_load_session_contract",
                                "active_viewer_package_id",
                            }
                        },
                    }
                )
                records_after.append(record)

            if unresolved_product_references:
                raise ManagedWellNotFoundError(unresolved_product_references[0])

            if not touched_well_ids:
                missing = well_references[0] if well_references else product_references[0]
                raise ManagedWellNotFoundError(missing)

            inventory_after = inventory_before.model_copy(
                update={"records": records_after, "updated_at": utc_now_iso()}
            )
            source_after = self._update_source_candidates(
                source_snapshot,
                records_after=records_after,
                touched_well_ids=touched_well_ids,
                removed_candidate_ids=removed_candidate_ids,
                actor=actor,
                reason=reason,
            )

            workspace_after = deepcopy(workspace_before)
            canonical_after = deepcopy(canonical_before)
            for original in inventory_before.records:
                if original.managed_well_id not in touched_well_ids:
                    continue
                workspace_after, _ = ManagedWellPurgeService._workspace_without_target(
                    workspace_after,
                    target=original,
                    remaining_records=records_after,
                )
                if original.managed_well_uid is not None:
                    canonical_after, _, _ = ManagedWellPurgeService._canonical_without_target(
                        canonical_after,
                        target_uid=str(original.managed_well_uid),
                    )

            self._validate(
                inventory_before=inventory_before,
                inventory_after=inventory_after,
                selected_well_ids=resolved_well_ids,
                selected_product_ids=set(product_owners),
                touched_well_ids=touched_well_ids,
            )

            payloads: dict[Path, bytes] = {
                self.repository.storage_path: ManagedWellPurgeService._json_bytes(
                    inventory_after.model_dump(mode="json")
                ),
                self.source_intake_path: ManagedWellPurgeService._json_bytes(
                    source_after.model_dump(mode="json")
                ),
                self.workspace_path: ManagedWellPurgeService._json_bytes(workspace_after),
            }
            if self.canonical_session_path.exists():
                payloads[self.canonical_session_path] = ManagedWellPurgeService._json_bytes(
                    canonical_after
                )

            originals = {
                path: path.read_bytes() if path.exists() else None
                for path in payloads
            }
            try:
                ManagedWellPurgeService._promote_all(payloads)
            except Exception as exc:
                ManagedWellPurgeService._restore_all(originals)
                raise ManagedInventoryStoreError(
                    "Selected MWD deletion failed; all touched stores were restored."
                ) from exc

            remaining_by_id = {
                record.managed_well_id: record for record in records_after
            }
            touched_remaining = [
                remaining_by_id[well_id]
                for well_id in sorted(touched_well_ids)
                if well_id in remaining_by_id
            ]
            return RemoveManagedDataFromMdpResponse(
                action="deleted_from_mwd",
                result=RemoveManagedDataFromMdpResult(
                    removed_managed_well_ids=sorted(set(removed_well_ids)),
                    removed_product_ids=sorted(set(removed_product_ids)),
                    unloaded_managed_well_ids=sorted(touched_well_ids),
                    retained_msi_records=False,
                ),
                records=touched_remaining,
            )

    @staticmethod
    def _resolve_well_ids(
        records: list[ManagedWellRecord],
        references: list[str],
    ) -> set[str]:
        resolved: set[str] = set()
        for reference in references:
            matches = [
                record
                for record in records
                if reference in {
                    record.managed_well_id,
                    str(record.managed_well_uid or ""),
                }
            ]
            if not matches:
                raise ManagedWellNotFoundError(reference)
            resolved.add(matches[0].managed_well_id)
        return resolved

    @staticmethod
    def _unresolved_product_references(
        records: list[ManagedWellRecord],
        references: list[str],
    ) -> list[str]:
        unresolved: list[str] = []
        for reference in references:
            matched = False
            for record in records:
                for group in record.product_groups:
                    for item in group.items:
                        if reference in {
                            item.product_id,
                            str(item.managed_product_uid or ""),
                            str(item.managed_curve_uid or ""),
                        }:
                            matched = True
                            break
                    if matched:
                        break
                if matched:
                    break
            if not matched:
                unresolved.append(reference)
        return unresolved

    @staticmethod
    def _resolve_product_owners(
        records: list[ManagedWellRecord],
        references: list[str],
    ) -> dict[str, str]:
        owners: dict[str, str] = {}
        for reference in references:
            found = None
            for record in records:
                for group in record.product_groups:
                    for item in group.items:
                        if reference in {
                            item.product_id,
                            str(item.managed_product_uid or ""),
                            str(item.managed_curve_uid or ""),
                        }:
                            found = (item.product_id, record.managed_well_id)
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                owners[found[0]] = found[1]
        return owners

    @staticmethod
    def _candidate_inventory(records: list[ManagedWellRecord]) -> dict[str, list[Any]]:
        by_candidate: dict[str, list[Any]] = {}
        for record in records:
            for group in record.product_groups:
                for item in group.items:
                    candidate_id = item.source_intake_candidate_id
                    if candidate_id:
                        by_candidate.setdefault(candidate_id, []).append(item)
        return by_candidate

    @classmethod
    def _update_source_candidates(
        cls,
        snapshot: SourceIntakeSnapshot,
        *,
        records_after: list[ManagedWellRecord],
        touched_well_ids: set[str],
        removed_candidate_ids: set[str],
        actor: str,
        reason: str,
    ) -> SourceIntakeSnapshot:
        remaining_by_candidate = cls._candidate_inventory(records_after)
        candidates = []
        for original in snapshot.candidates:
            candidate = deepcopy(original)
            candidate_id = candidate.source_file_id
            linked_to_touched_well = candidate.managed_well_id in touched_well_ids
            was_touched = linked_to_touched_well or candidate_id in removed_candidate_ids
            if not was_touched:
                candidates.append(candidate)
                continue

            remaining = remaining_by_candidate.get(candidate_id, [])
            if not remaining:
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
            else:
                candidate.registered_product_count = len(remaining)
                candidate.registered_curve_count = sum(
                    1 for item in remaining if item.managed_curve_uid is not None
                )
                candidate.wdv_state = None
                candidate.resolved_by = actor
                candidate.resolved_at = source_intake_utc_now_iso()
                candidate.resolution_reason = reason
            candidates.append(candidate)

        return snapshot.model_copy(
            update={
                "candidates": candidates,
                "updated_at": source_intake_utc_now_iso(),
            }
        )

    @staticmethod
    def _validate(
        *,
        inventory_before: ManagedInventorySnapshot,
        inventory_after: ManagedInventorySnapshot,
        selected_well_ids: set[str],
        selected_product_ids: set[str],
        touched_well_ids: set[str],
    ) -> None:
        after_by_id = {
            record.managed_well_id: record for record in inventory_after.records
        }
        for well_id in selected_well_ids:
            if well_id in after_by_id:
                raise ValueError(f"Selected managed well remains after deletion: {well_id}")

        remaining_product_ids = {
            item.product_id
            for record in inventory_after.records
            for group in record.product_groups
            for item in group.items
        }
        undeleted = selected_product_ids & remaining_product_ids
        if undeleted:
            raise ValueError(
                f"Selected managed products remain after deletion: {sorted(undeleted)}"
            )

        before_unrelated = {
            record.managed_well_id: record.model_dump(mode="json")
            for record in inventory_before.records
            if record.managed_well_id not in touched_well_ids
        }
        after_unrelated = {
            record.managed_well_id: record.model_dump(mode="json")
            for record in inventory_after.records
            if record.managed_well_id not in touched_well_ids
        }
        if before_unrelated != after_unrelated:
            raise ValueError("Unrelated managed records changed during selected deletion.")
