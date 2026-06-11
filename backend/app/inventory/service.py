"""Managed Well Inventory service boundary."""

from __future__ import annotations

from collections import Counter
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
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
    ManagedWdvState,
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
        return [self._with_product_groups(record) for record in self.repository.list_records()]

    def get_well(self, managed_well_id: str) -> ManagedWellRecord:
        return self._with_product_groups(self.repository.get_record(managed_well_id))

    def list_viewer_packages(self) -> list[ViewerPackageReference]:
        packages: list[ViewerPackageReference] = []
        for record in self.repository.list_records():
            packages.extend(record.viewer_packages)
        return packages

    def get_viewer_package_contract(self, managed_well_id: str) -> dict[str, Any]:
        """Return the backend-owned viewer package contract for a managed well.

        Managed Inventory remains the lookup authority. The full viewer package
        contract is stored in record metadata by registration/ingestion services,
        while viewer_packages holds lightweight package references for lists.

        If WMDP has loaded only selected curve products to WDV, the returned
        package is filtered to those loaded curves. This keeps the WDV display
        controlled by WMDP state instead of frontend fallback/demo state.
        """
        record = self.repository.get_record(managed_well_id)
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

        target.updated_at = utc_now_iso()
        _action, saved = self.repository.upsert_record(target)
        active_package_id = saved.viewer_packages[0].viewer_package_id if saved.viewer_packages else None

        return LoadManagedWellToWdvResponse(
            result=LoadManagedWellToWdvResult(
                managed_well_id=saved.managed_well_id,
                loaded_product_ids=loaded_product_ids,
                unloaded_managed_well_ids=unloaded_managed_well_ids,
                active_viewer_package_id=active_package_id,
            ),
            record=saved,
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
