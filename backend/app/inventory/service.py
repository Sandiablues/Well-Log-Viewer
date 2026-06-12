"""Managed Well Inventory service boundary."""

from __future__ import annotations

from collections import Counter
import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from backend.app.wells.models import Curve, WellMultitrackV1
from backend.app.wells.seed_repository import SeedWellRepository
from backend.app.classification.well_log_classifier import classify_well_log_curve
from backend.app.classification.well_log_vocabulary import PRODUCT_GROUP_ORDER
from backend.app.knowledge.curve_knowledge import normalize_viewer_package_for_wdv

from .models import (
    InventoryValidationSeverity,
    ManagedInventoryHealth,
    ManagedInventoryLifecycleState,
    ManagedInventoryMaintenanceStatus,
    ManagedInventoryStatus,
    ManagedInventoryValidationIssue,
    ManagedInventoryValidationResult,
    LoadManagedWellToWdvResponse,
    LoadManagedWellToWdvResult,
    UnloadManagedWellFromWdvResponse,
    UnloadManagedWellFromWdvResult,
    RemoveManagedDataFromMdpResponse,
    RemoveManagedDataFromMdpResult,
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
    ManagedWdvState,
    ManagedWmdpState,
    RegisterSeedWellResponse,
    ViewerPackageReference,
    utc_now_iso,
)
from .repository import ManagedWellInventoryRepository, ManagedWellNotFoundError


class ManagedWellInventoryService:
    def __init__(
        self,
        repository: ManagedWellInventoryRepository | None = None,
        seed_repository: SeedWellRepository | None = None,
    ) -> None:
        self.repository = repository or ManagedWellInventoryRepository()
        self.seed_repository = seed_repository or SeedWellRepository()

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

    def list_wells(self) -> list[ManagedWellRecord]:
        return [
            self._with_product_groups(record)
            for record in self.repository.list_records()
            if record.wmdp_available and record.wmdp_state != ManagedWmdpState.REMOVED_FROM_WMDP
        ]

    def get_well(self, managed_well_id: str) -> ManagedWellRecord:
        return self._with_product_groups(self.repository.get_record(managed_well_id))

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
        record = self.repository.get_record(managed_well_id)
        loaded_items = self._loaded_wdv_product_items(record)
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
            if not isinstance(existing_session, dict) or existing_product_ids != loaded_product_ids or session_depth_stale:
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
        record.updated_at = utc_now_iso()
        return self.repository.upsert_record(record)

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
        representations or mutate source-intake records. Only one managed well
        may be loaded at a time.
        """
        selected_product_ids = set(product_ids or [])
        records = self.repository.list_records()
        target = None

        for record in records:
            if record.managed_well_id == managed_well_id:
                target = record
                break

        if target is None:
            raise ManagedWellNotFoundError(managed_well_id)

        unloaded_managed_well_ids: list[str] = []
        for record in records:
            if record.managed_well_id == managed_well_id:
                continue
            if record.wdv_state != ManagedWdvState.NOT_LOADED:
                unloaded_managed_well_ids.append(record.managed_well_id)
            record.wdv_state = ManagedWdvState.NOT_LOADED
            for group in record.product_groups:
                for item in group.items:
                    item.wdv_state = ManagedWdvState.NOT_LOADED
            self.repository.upsert_record(record)

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
        target.updated_at = utc_now_iso()
        _action, saved = self.repository.upsert_record(target)

        return LoadManagedWellToWdvResponse(
            result=LoadManagedWellToWdvResult(
                managed_well_id=saved.managed_well_id,
                loaded_product_ids=loaded_product_ids,
                unloaded_managed_well_ids=unloaded_managed_well_ids,
                active_viewer_package_id=active_package_id,
            ),
            record=saved,
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
        selected_well_ids = set(managed_well_ids or [])
        selected_product_ids = set(product_ids or [])

        if not selected_well_ids and not selected_product_ids:
            raise ValueError("Select at least one managed well or product to remove from MDP.")

        records = self.repository.list_records()
        known_well_ids = {record.managed_well_id for record in records}
        missing_well_ids = sorted(selected_well_ids - known_well_ids)
        if missing_well_ids:
            raise ManagedWellNotFoundError(missing_well_ids[0])

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
                self._sync_wdv_load_session_for_record(record)
                record.updated_at = utc_now_iso()
                _action, saved = self.repository.upsert_record(record)
                touched_records.append(saved)

        missing_product_ids = sorted(selected_product_ids - set(removed_product_ids))
        if missing_product_ids and not touched_records:
            raise ManagedWellNotFoundError(missing_product_ids[0])

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
        selected_product_ids = set(product_ids or [])
        record = self.repository.get_record(managed_well_id)

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
        self._sync_wdv_load_session_for_record(record)
        record.updated_at = utc_now_iso()
        _action, saved = self.repository.upsert_record(record)

        return UnloadManagedWellFromWdvResponse(
            result=UnloadManagedWellFromWdvResult(
                managed_well_id=saved.managed_well_id,
                unloaded_product_ids=unloaded_product_ids,
                remaining_loaded_product_ids=remaining_loaded_product_ids,
                wdv_state=saved.wdv_state,
            ),
            record=saved,
        )

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
        product_ids = [item.product_id for item in loaded_items]
        loaded_curve_items = [self._wdv_curve_contract_from_product_item(item) for item in loaded_items]
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
        }

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

    def _wdv_curve_contract_from_product_item(self, item: ManagedProductGroupItem) -> dict[str, Any]:
        curve_id = str(item.curve_name or item.display_name or item.product_id).strip() or item.product_id
        scale = self._wdv_default_scale(item)
        return {
            "product_id": item.product_id,
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
            "scale": scale,
            "scale_type": scale["type"],
            "display_min": scale["min"],
            "display_max": scale["max"],
            "is_renderable": True,
            "support_status": "renderable",
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

    def _wdv_load_session_reference(self, record: ManagedWellRecord, contract: dict[str, Any]) -> ViewerPackageReference:
        session_id = str(contract["representation_id"])
        return ViewerPackageReference(
            viewer_package_id=session_id,
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
    def _wdv_default_scale(item: ManagedProductGroupItem) -> dict[str, Any]:
        key = f"{item.curve_name} {item.curve_family} {item.curve_type} {item.curve_unit}".lower()
        if "resist" in key or "ohmm" in key:
            return {"type": "log", "min": 0.2, "max": 2000.0}
        if "gamma" in key or "gapi" in key:
            return {"type": "linear", "min": 0.0, "max": 200.0}
        if "density" in key or "g/c" in key:
            return {"type": "linear", "min": 1.95, "max": 2.95}
        if "neutron" in key or "porosity" in key or "cfcf" in key:
            return {"type": "linear", "min": 0.45, "max": -0.15}
        if "sonic" in key or "delta-t" in key or "us/f" in key:
            return {"type": "linear", "min": 140.0, "max": 40.0}
        if "caliper" in key or " in" in key:
            return {"type": "linear", "min": 6.0, "max": 16.0}
        if "pressure" in key or "psi" in key:
            return {"type": "linear", "min": 0.0, "max": 10000.0}
        if "temperature" in key or "deg" in key:
            return {"type": "linear", "min": 0.0, "max": 500.0}
        return {"type": "linear", "min": 0.0, "max": 150.0}

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
        return ManagedProductGroupItem(
            product_id=f"curve:{viewer_package_reference.well_id}:{curve.curve_id}",
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
