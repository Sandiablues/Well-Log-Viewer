"""Backend-owned transient lifecycle projection for WMD working data.

Cleanup eligibility is projected only after WMD data is removed and every
explicit WMD, WDV, WBV, export, and saved-workspace reference is released.
Cleanup execution clears only WLV-owned transient WMD viewer payloads. It never
modifies or deletes external sources, source references, fingerprints, QAQC, or metadata overlays.
"""

from __future__ import annotations

from app.identity import new_uuid7_str

from .models import (
    ManagedProductGroupItem,
    ManagedWellRecord,
    ManagedWdvState,
    ManagedWmdpState,
    WmdReferenceBinding,
    WmdReferenceType,
    WmdRetentionState,
    WmdWorkingState,
    utc_now_iso,
)


class WmdLifecycleService:
    """Own WMD reference bindings and project lifecycle from those bindings."""

    @staticmethod
    def _normalized_owner(owner_id: str) -> str:
        value = str(owner_id or "").strip()
        if not value:
            raise ValueError("WMD reference owner_id is required")
        return value

    def acquire_reference(
        self,
        target: ManagedWellRecord | ManagedProductGroupItem,
        reference_type: WmdReferenceType,
        owner_id: str,
        reason: str | None = None,
    ) -> WmdReferenceBinding:
        owner = self._normalized_owner(owner_id)
        for binding in target.wmd_references:
            if binding.reference_type == reference_type and binding.owner_id == owner:
                return binding
        binding = WmdReferenceBinding(
            reference_uid=new_uuid7_str(),
            reference_type=reference_type,
            owner_id=owner,
            reason=reason,
        )
        target.wmd_references.append(binding)
        return binding

    def release_reference(
        self,
        target: ManagedWellRecord | ManagedProductGroupItem,
        reference_type: WmdReferenceType,
        owner_id: str,
    ) -> bool:
        owner = self._normalized_owner(owner_id)
        before = len(target.wmd_references)
        target.wmd_references = [
            binding
            for binding in target.wmd_references
            if not (
                binding.reference_type == reference_type
                and binding.owner_id == owner
            )
        ]
        return len(target.wmd_references) != before

    @staticmethod
    def _active_reference_types(
        target: ManagedWellRecord | ManagedProductGroupItem,
    ) -> set[WmdReferenceType]:
        return {binding.reference_type for binding in target.wmd_references}

    @staticmethod
    def _reference_reason(reference_types: set[WmdReferenceType]) -> str:
        return "referenced_by_" + ",".join(
            sorted(reference_type.value for reference_type in reference_types)
        )

    def project_item(self, item: ManagedProductGroupItem) -> ManagedProductGroupItem:
        active_types = self._active_reference_types(item)
        removed = item.wmdp_state == ManagedWmdpState.REMOVED_FROM_WMDP

        if removed and active_types:
            return item.model_copy(
                update={
                    "wmd_working_state": WmdWorkingState.IN_USE,
                    "wmd_retention_state": WmdRetentionState.ACTIVE,
                    "wmd_cleanup_eligible": False,
                    "wmd_retention_reason": self._reference_reason(active_types),
                }
            )

        downstream_types = active_types - {WmdReferenceType.WMD}
        if downstream_types:
            return item.model_copy(
                update={
                    "wmd_working_state": WmdWorkingState.IN_USE,
                    "wmd_retention_state": WmdRetentionState.ACTIVE,
                    "wmd_cleanup_eligible": False,
                    "wmd_retention_reason": self._reference_reason(downstream_types),
                }
            )

        if item.wdv_state == ManagedWdvState.LOADED_TO_WDV:
            return item.model_copy(
                update={
                    "wmd_working_state": WmdWorkingState.IN_USE,
                    "wmd_retention_state": WmdRetentionState.ACTIVE,
                    "wmd_cleanup_eligible": False,
                    "wmd_retention_reason": "referenced_by_wdv",
                }
            )

        if removed:
            return item.model_copy(
                update={
                    "wmd_working_state": WmdWorkingState.ELIGIBLE_FOR_CLEANUP,
                    "wmd_retention_state": WmdRetentionState.ELIGIBLE_FOR_CLEANUP,
                    "wmd_cleanup_eligible": True,
                    "wmd_retention_reason": "removed_from_wmd_no_active_references",
                }
            )

        return item.model_copy(
            update={
                "wmd_working_state": WmdWorkingState.AVAILABLE,
                "wmd_retention_state": WmdRetentionState.ACTIVE,
                "wmd_cleanup_eligible": False,
                "wmd_retention_reason": "available_in_wmd",
            }
        )

    def project_record(self, record: ManagedWellRecord) -> ManagedWellRecord:
        groups = [
            group.model_copy(
                update={"items": [self.project_item(item) for item in group.items]}
            )
            for group in record.product_groups
        ]
        active_types = self._active_reference_types(record)
        removed = (
            record.wmdp_state == ManagedWmdpState.REMOVED_FROM_WMDP
            or not record.wmdp_available
        )
        item_reference_types = {
            binding.reference_type
            for group in groups
            for item in group.items
            for binding in item.wmd_references
        }
        all_reference_types = active_types | item_reference_types

        if removed and all_reference_types:
            state = WmdWorkingState.IN_USE
            retention = WmdRetentionState.ACTIVE
            reason = self._reference_reason(all_reference_types)
        else:
            downstream_types = active_types - {WmdReferenceType.WMD}
            if downstream_types:
                state = WmdWorkingState.IN_USE
                retention = WmdRetentionState.ACTIVE
                reason = self._reference_reason(downstream_types)
            elif record.wdv_state == ManagedWdvState.LOADED_TO_WDV:
                state = WmdWorkingState.IN_USE
                retention = WmdRetentionState.ACTIVE
                reason = "referenced_by_wdv"
            elif removed:
                state = WmdWorkingState.ELIGIBLE_FOR_CLEANUP
                retention = WmdRetentionState.ELIGIBLE_FOR_CLEANUP
                reason = "removed_from_wmd_no_active_references"
            else:
                state = WmdWorkingState.AVAILABLE
                retention = WmdRetentionState.ACTIVE
                reason = "available_in_wmd"

        return record.model_copy(
            update={
                "product_groups": groups,
                "wmd_working_state": state,
                "wmd_retention_state": retention,
                "wmd_cleanup_eligible": (
                    retention == WmdRetentionState.ELIGIBLE_FOR_CLEANUP
                ),
                "wmd_retention_reason": reason,
            }
        )

    @staticmethod
    def _clear_item_payload(item: ManagedProductGroupItem) -> ManagedProductGroupItem:
        """Clear viewer-only WMD payload while retaining identity and rebuild provenance."""
        return item.model_copy(
            update={
                "viewer_package_id": None,
                "wdv_state": ManagedWdvState.NOT_LOADED,
                "wmd_working_state": WmdWorkingState.CLEARED,
                "wmd_retention_state": WmdRetentionState.CLEARED,
                "wmd_cleanup_eligible": False,
                "wmd_retention_reason": "wlv_owned_transient_wmd_payload_cleared",
                "wmd_references": [],
            }
        )

    def execute_cleanup(
        self,
        record: ManagedWellRecord,
        product_ids: set[str] | None = None,
    ) -> tuple[ManagedWellRecord, list[str], bool]:
        """Clear only eligible WLV-owned transient WMD viewer payloads.

        Product rows, canonical identities, external source references, source
        fingerprints, provenance, QAQC state, and metadata overlays are retained
        so the working representation remains rebuildable.
        """
        projected = self.project_record(record)
        requested = set(product_ids or ())
        if product_ids is None and not projected.wmd_cleanup_eligible:
            raise ValueError("WMD record is not eligible for cleanup.")

        cleared_ids: list[str] = []
        groups = []
        for group in projected.product_groups:
            items = []
            for item in group.items:
                selected = product_ids is None or item.product_id in requested
                if selected:
                    if not item.wmd_cleanup_eligible:
                        raise ValueError(
                            f"WMD product is not eligible for cleanup: {item.product_id}"
                        )
                    item = self._clear_item_payload(item)
                    cleared_ids.append(item.product_id)
                items.append(item)
            groups.append(group.model_copy(update={"items": items}))

        if requested - set(cleared_ids):
            missing = sorted(requested - set(cleared_ids))
            raise ValueError("WMD products not found: " + ", ".join(missing))

        record_payload_cleared = product_ids is None
        metadata = dict(projected.metadata)
        if record_payload_cleared:
            for key in (
                "viewer_package_contract",
                "wdv_load_session_contract",
                "wdv_render_package",
            ):
                metadata.pop(key, None)

        all_items_cleared = all(
            item.wmd_retention_state == WmdRetentionState.CLEARED
            for group in groups
            for item in group.items
        )
        update = {
            "product_groups": groups,
            "viewer_packages": [] if record_payload_cleared else projected.viewer_packages,
            "metadata": metadata,
            "wdv_state": ManagedWdvState.NOT_LOADED if record_payload_cleared else projected.wdv_state,
        }
        if record_payload_cleared or all_items_cleared:
            update.update(
                {
                    "wmd_working_state": WmdWorkingState.CLEARED,
                    "wmd_retention_state": WmdRetentionState.CLEARED,
                    "wmd_cleanup_eligible": False,
                    "wmd_retention_reason": "wlv_owned_transient_wmd_payload_cleared",
                    "wmd_references": [],
                }
            )

        return projected.model_copy(update=update), cleared_ids, record_payload_cleared

    @staticmethod
    def _rebuild_item_payload(item: ManagedProductGroupItem) -> ManagedProductGroupItem:
        """Restore transient WMD availability without changing durable identity."""
        return item.model_copy(
            update={
                "viewer_package_id": None,
                "wmdp_state": ManagedWmdpState.STAGED_IN_WMDP,
                "wdv_state": ManagedWdvState.NOT_LOADED,
                "wmd_working_state": WmdWorkingState.AVAILABLE,
                "wmd_retention_state": WmdRetentionState.ACTIVE,
                "wmd_cleanup_eligible": False,
                "wmd_retention_reason": "rebuilt_from_retained_source_provenance",
                "wmd_references": [],
            }
        )

    def rebuild_cleared_payload(
        self,
        record: ManagedWellRecord,
        product_ids: set[str] | None = None,
    ) -> tuple[ManagedWellRecord, list[str]]:
        """Restore cleared transient WMD payload state from retained provenance.

        Source readability and fingerprint verification are performed by the
        inventory service before this state transition is persisted.
        """
        requested = set(product_ids or ())
        rebuilt_ids: list[str] = []
        groups = []

        for group in record.product_groups:
            items = []
            for item in group.items:
                selected = product_ids is None or item.product_id in requested
                if selected:
                    if item.wmd_retention_state != WmdRetentionState.CLEARED:
                        raise ValueError(
                            f"WMD product is not cleared and cannot be rebuilt: {item.product_id}"
                        )
                    item = self._rebuild_item_payload(item)
                    rebuilt_ids.append(item.product_id)
                items.append(item)
            groups.append(group.model_copy(update={"items": items}))

        if requested - set(rebuilt_ids):
            missing = sorted(requested - set(rebuilt_ids))
            raise ValueError("WMD products not found: " + ", ".join(missing))
        if not rebuilt_ids:
            raise ValueError("No cleared WMD products are available to rebuild.")

        metadata = dict(record.metadata)
        metadata["wmd_rebuild_contract"] = {
            "contract_version": "wmd_rebuild_v1",
            "rebuilt_product_ids": list(rebuilt_ids),
            "rebuilt_at": utc_now_iso(),
            "source_authority": "external_read_only",
            "identities_preserved": True,
        }

        rebuilt = record.model_copy(
            update={
                "product_groups": groups,
                "metadata": metadata,
                "wmdp_available": True,
                "wmdp_state": ManagedWmdpState.STAGED_IN_WMDP,
                "wdv_state": ManagedWdvState.NOT_LOADED,
                "wmd_working_state": WmdWorkingState.AVAILABLE,
                "wmd_retention_state": WmdRetentionState.ACTIVE,
                "wmd_cleanup_eligible": False,
                "wmd_retention_reason": "rebuilt_from_retained_source_provenance",
                "wmd_references": [],
                "viewer_packages": [],
            }
        )
        return rebuilt, rebuilt_ids

