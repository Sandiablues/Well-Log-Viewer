"""Managed Well Inventory service boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from backend.app.wells.models import WellMultitrackV1
from backend.app.wells.seed_repository import SeedWellRepository

from .models import (
    ManagedInventoryHealth,
    ManagedInventoryStatus,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
    ManagedWellStatus,
    RegisterSeedWellResponse,
    ViewerPackageReference,
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
        records = self.repository.list_records()
        return ManagedInventoryStatus(
            ok=True,
            storage_backend="local_json",
            storage_path=str(self.repository.storage_path),
            managed_well_count=len(records),
            viewer_package_count=sum(len(record.viewer_packages) for record in records),
            source_reference_count=sum(len(record.source_references) for record in records),
        )

    def list_wells(self) -> list[ManagedWellRecord]:
        return self.repository.list_records()

    def get_well(self, managed_well_id: str) -> ManagedWellRecord:
        return self.repository.get_record(managed_well_id)

    def list_viewer_packages(self) -> list[ViewerPackageReference]:
        packages: list[ViewerPackageReference] = []
        for record in self.repository.list_records():
            packages.extend(record.viewer_packages)
        return packages

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

        record = ManagedWellRecord(
            managed_well_id=managed_well_id,
            well_id=well.well_id,
            well_name=well.well_name,
            wellbore_id=well.wellbore_id,
            wellbore_name=well.wellbore_name,
            operator=well.operator,
            field=well.field,
            country=well.country,
            depth_unit=well.depth_unit.value if hasattr(well.depth_unit, "value") else str(well.depth_unit),
            top_depth=well.depth_range.min,
            base_depth=well.depth_range.max,
            status=ManagedWellStatus.AVAILABLE,
            source_references=[
                ManagedSourceReference(
                    source_id=f"source:{well.well_id}:seed-las",
                    source_kind=ManagedSourceKind.SEED,
                    display_name=well.source_file or f"{well.well_name} seed source",
                    file_name=well.source_file,
                    file_format="LAS",
                    metadata={"source": "prototype_seed_repository"},
                )
            ],
            viewer_packages=[self._viewer_package_reference(viewer_package)],
            tags=["seed", "forge"],
            metadata={
                "api_number": well.api_number,
                "datum": well.datum,
                "kb_elevation": well.kb_elevation,
                "ground_elevation": well.ground_elevation,
            },
            created_at=existing_created_at,
            updated_at=now,
        )
        action, saved = self.repository.upsert_record(record)
        return RegisterSeedWellResponse(ok=True, action=action, record=saved)

    @staticmethod
    def _viewer_package_reference(viewer_package: WellMultitrackV1) -> ViewerPackageReference:
        return ViewerPackageReference(
            viewer_package_id=f"viewer-package:{viewer_package.representation_id}",
            viewer_package_version=viewer_package.viewer_package_version,
            dataset_id=viewer_package.dataset_id,
            representation_id=viewer_package.representation_id,
            well_id=viewer_package.well_id,
            endpoint=f"/api/wlv/wells/{viewer_package.well_id}/viewer-package",
            status=ManagedWellStatus.AVAILABLE,
        )
