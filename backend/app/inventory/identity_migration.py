"""Versioned UUIDv7 migration for the Managed Well Inventory.

The migration assigns canonical identities exactly once, preserves legacy
identifiers as aliases, validates relationship/uniqueness invariants, creates a
byte-for-byte backup before persistence, and restores the original store if
post-write validation fails.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable

from app.identity import IdentityAssignmentMetadata, LegacyIdentityAlias, new_uuid7_str

from .models import (
    ManagedInventorySnapshot,
    ManagedProductGroupItem,
    ManagedSourceReference,
    ManagedWellRecord,
    ViewerPackageReference,
    utc_now_iso,
)
from .repository import ManagedWellInventoryRepository

UUID7_INVENTORY_SCHEMA_VERSION = "wlv_managed_inventory_v3_uuid7"
MIGRATION_NAME = "wlv_uid_3_managed_inventory_uuid7"


class ManagedInventoryIdentityMigrationError(RuntimeError):
    """Raised when the UUIDv7 migration cannot complete safely."""


@dataclass(frozen=True)
class IdentityMigrationSummary:
    ok: bool
    migration: str
    dry_run: bool
    source_schema_version: str
    target_schema_version: str
    records_checked: int
    identities_assigned: int
    aliases_added: int
    records_written: int
    backup_path: str | None
    changed: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "migration": self.migration,
            "dry_run": self.dry_run,
            "source_schema_version": self.source_schema_version,
            "target_schema_version": self.target_schema_version,
            "records_checked": self.records_checked,
            "identities_assigned": self.identities_assigned,
            "aliases_added": self.aliases_added,
            "records_written": self.records_written,
            "backup_path": self.backup_path,
            "changed": self.changed,
        }


@dataclass
class _MigrationCounters:
    identities_assigned: int = 0
    aliases_added: int = 0


class ManagedInventoryIdentityMigrationService:
    """Assign canonical UUIDv7 identities to persisted MSI records."""

    def __init__(
        self,
        repository: ManagedWellInventoryRepository | None = None,
        *,
        uid_factory: Callable[[], str] = new_uuid7_str,
        now_factory: Callable[[], str] = utc_now_iso,
    ) -> None:
        self.repository = repository or ManagedWellInventoryRepository()
        self.uid_factory = uid_factory
        self.now_factory = now_factory

    def migrate(self, *, dry_run: bool = False) -> IdentityMigrationSummary:
        source = self.repository.snapshot()
        source_schema_version = source.schema_version
        counters = _MigrationCounters()
        migrated = source.model_copy(deep=True)

        assignment = IdentityAssignmentMetadata(
            assigned_at=self.now_factory(),
            assignment_source=MIGRATION_NAME,
        )

        uid_by_legacy_key: dict[tuple[str, str], str] = {}

        for record in migrated.records:
            self._migrate_record(record, assignment, uid_by_legacy_key, counters)

        migrated.schema_version = UUID7_INVENTORY_SCHEMA_VERSION
        self._validate_snapshot(migrated)

        source_payload = source.model_dump(mode="json")
        migrated_payload = migrated.model_dump(mode="json")
        changed = source_payload != migrated_payload

        if changed:
            migrated.updated_at = self.now_factory()
            migrated_payload = migrated.model_dump(mode="json")

        if dry_run or not changed:
            return IdentityMigrationSummary(
                ok=True,
                migration=MIGRATION_NAME,
                dry_run=dry_run,
                source_schema_version=source_schema_version,
                target_schema_version=UUID7_INVENTORY_SCHEMA_VERSION,
                records_checked=len(source.records),
                identities_assigned=counters.identities_assigned,
                aliases_added=counters.aliases_added,
                records_written=0,
                backup_path=None,
                changed=changed,
            )

        backup_path = self._create_backup()
        try:
            self.repository.write_snapshot(migrated)
            persisted = self.repository.snapshot()
            self._validate_snapshot(persisted)
            if persisted.model_dump(mode="json") != migrated_payload:
                raise ManagedInventoryIdentityMigrationError(
                    "Persisted inventory does not match validated migration payload"
                )
        except Exception as exc:
            self._restore_backup(backup_path)
            if isinstance(exc, ManagedInventoryIdentityMigrationError):
                raise
            raise ManagedInventoryIdentityMigrationError(
                "UUIDv7 inventory migration failed; original store restored"
            ) from exc

        return IdentityMigrationSummary(
            ok=True,
            migration=MIGRATION_NAME,
            dry_run=False,
            source_schema_version=source_schema_version,
            target_schema_version=UUID7_INVENTORY_SCHEMA_VERSION,
            records_checked=len(source.records),
            identities_assigned=counters.identities_assigned,
            aliases_added=counters.aliases_added,
            records_written=len(migrated.records),
            backup_path=str(backup_path) if backup_path else None,
            changed=True,
        )

    def _migrate_record(
        self,
        record: ManagedWellRecord,
        assignment: IdentityAssignmentMetadata,
        uid_by_legacy_key: dict[tuple[str, str], str],
        counters: _MigrationCounters,
    ) -> None:
        record.managed_well_uid = self._assign_uid(
            record.managed_well_uid,
            "managed_well_id",
            record.managed_well_id,
            uid_by_legacy_key,
            counters,
        )
        record.managed_wellbore_uid = self._assign_uid(
            record.managed_wellbore_uid,
            "managed_wellbore_locator",
            record.wellbore_id or record.managed_well_id,
            uid_by_legacy_key,
            counters,
        )
        if record.identity_assignment is None:
            record.identity_assignment = assignment
        record.legacy_ids = self._add_alias(
            record.legacy_ids,
            "managed_well_id",
            record.managed_well_id,
            counters,
        )
        record.legacy_ids = self._add_alias(
            record.legacy_ids,
            "well_id",
            record.well_id,
            counters,
        )

        for source in record.source_references:
            self._migrate_source(source, assignment, uid_by_legacy_key, counters)

        for package in record.viewer_packages:
            self._migrate_viewer_package(package, assignment, uid_by_legacy_key, counters)

        for group in record.product_groups:
            for item in group.items:
                self._migrate_product(
                    item,
                    record,
                    assignment,
                    uid_by_legacy_key,
                    counters,
                )

    def _migrate_source(
        self,
        source: ManagedSourceReference,
        assignment: IdentityAssignmentMetadata,
        uid_by_legacy_key: dict[tuple[str, str], str],
        counters: _MigrationCounters,
    ) -> None:
        source.managed_source_uid = self._assign_uid(
            source.managed_source_uid,
            "source_id",
            source.source_id,
            uid_by_legacy_key,
            counters,
        )
        source.source_occurrence_uid = self._assign_uid(
            source.source_occurrence_uid,
            "source_occurrence",
            source.source_id,
            uid_by_legacy_key,
            counters,
        )
        if source.identity_assignment is None:
            source.identity_assignment = assignment
        source.legacy_ids = self._add_alias(
            source.legacy_ids,
            "source_id",
            source.source_id,
            counters,
        )

    def _migrate_viewer_package(
        self,
        package: ViewerPackageReference,
        assignment: IdentityAssignmentMetadata,
        uid_by_legacy_key: dict[tuple[str, str], str],
        counters: _MigrationCounters,
    ) -> None:
        package.viewer_package_uid = self._assign_uid(
            package.viewer_package_uid,
            "viewer_package_id",
            package.viewer_package_id,
            uid_by_legacy_key,
            counters,
        )
        package.representation_uid = self._assign_uid(
            package.representation_uid,
            "representation_id",
            package.representation_id,
            uid_by_legacy_key,
            counters,
        )
        if package.identity_assignment is None:
            package.identity_assignment = assignment
        package.legacy_ids = self._add_alias(
            package.legacy_ids,
            "viewer_package_id",
            package.viewer_package_id,
            counters,
        )
        package.legacy_ids = self._add_alias(
            package.legacy_ids,
            "representation_id",
            package.representation_id,
            counters,
        )

    def _migrate_product(
        self,
        item: ManagedProductGroupItem,
        record: ManagedWellRecord,
        assignment: IdentityAssignmentMetadata,
        uid_by_legacy_key: dict[tuple[str, str], str],
        counters: _MigrationCounters,
    ) -> None:
        item.managed_product_uid = self._assign_uid(
            item.managed_product_uid,
            "product_id",
            item.product_id,
            uid_by_legacy_key,
            counters,
        )
        curve_locator = item.curve_uid or item.product_id
        item.managed_curve_uid = self._assign_uid(
            item.managed_curve_uid,
            "curve_locator",
            curve_locator,
            uid_by_legacy_key,
            counters,
        )
        if item.managed_wellbore_uid is None:
            item.managed_wellbore_uid = record.managed_wellbore_uid
            counters.identities_assigned += 1

        source_locator = item.source_uid or item.source_id
        if item.managed_source_uid is None and source_locator:
            item.managed_source_uid = self._assign_uid(
                None,
                "source_id",
                source_locator,
                uid_by_legacy_key,
                counters,
            )

        if item.identity_assignment is None:
            item.identity_assignment = assignment
        item.legacy_ids = self._add_alias(
            item.legacy_ids,
            "product_id",
            item.product_id,
            counters,
        )
        if item.curve_uid:
            item.legacy_ids = self._add_alias(
                item.legacy_ids,
                "wlv_curve_sha1_v1",
                item.curve_uid,
                counters,
            )

    def _assign_uid(
        self,
        current: str | None,
        scheme: str,
        legacy_value: str,
        uid_by_legacy_key: dict[tuple[str, str], str],
        counters: _MigrationCounters,
    ) -> str:
        if current:
            uid_by_legacy_key.setdefault((scheme, legacy_value), current)
            return current
        key = (scheme, legacy_value)
        uid = uid_by_legacy_key.get(key)
        if uid is None:
            uid = self.uid_factory()
            uid_by_legacy_key[key] = uid
        counters.identities_assigned += 1
        return uid

    @staticmethod
    def _add_alias(
        aliases: list[LegacyIdentityAlias],
        scheme: str,
        value: str | None,
        counters: _MigrationCounters,
    ) -> list[LegacyIdentityAlias]:
        if not value:
            return aliases
        if any(alias.scheme == scheme and alias.value == value for alias in aliases):
            return aliases
        counters.aliases_added += 1
        return [*aliases, LegacyIdentityAlias(scheme=scheme, value=value)]

    def _validate_snapshot(self, snapshot: ManagedInventorySnapshot) -> None:
        if snapshot.schema_version != UUID7_INVENTORY_SCHEMA_VERSION:
            raise ManagedInventoryIdentityMigrationError("Unexpected target schema version")

        well_uids: set[str] = set()
        wellbore_uids: set[str] = set()
        product_uids: set[str] = set()
        curve_uids: set[str] = set()

        for record in snapshot.records:
            self._require(record.managed_well_uid, "managed_well_uid")
            self._require(record.managed_wellbore_uid, "managed_wellbore_uid")
            self._add_unique(well_uids, record.managed_well_uid, "managed_well_uid")
            self._add_unique(wellbore_uids, record.managed_wellbore_uid, "managed_wellbore_uid")

            for source in record.source_references:
                self._require(source.managed_source_uid, "managed_source_uid")
                self._require(source.source_occurrence_uid, "source_occurrence_uid")

            for package in record.viewer_packages:
                self._require(package.viewer_package_uid, "viewer_package_uid")
                self._require(package.representation_uid, "representation_uid")

            for group in record.product_groups:
                for item in group.items:
                    self._require(item.managed_product_uid, "managed_product_uid")
                    self._require(item.managed_curve_uid, "managed_curve_uid")
                    if item.managed_wellbore_uid != record.managed_wellbore_uid:
                        raise ManagedInventoryIdentityMigrationError(
                            f"Product {item.product_id} does not reference its parent wellbore"
                        )
                    self._add_unique(product_uids, item.managed_product_uid, "managed_product_uid")
                    self._add_unique(curve_uids, item.managed_curve_uid, "managed_curve_uid")

    @staticmethod
    def _require(value: str | None, field: str) -> None:
        if not value:
            raise ManagedInventoryIdentityMigrationError(f"Missing required {field}")

    @staticmethod
    def _add_unique(target: set[str], value: str, field: str) -> None:
        if value in target:
            raise ManagedInventoryIdentityMigrationError(f"Duplicate {field}: {value}")
        target.add(value)

    def _create_backup(self) -> Path | None:
        storage = self.repository.storage_path
        if not storage.exists():
            return None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = storage.with_name(f"{storage.name}.pre_uuid7_{stamp}.bak")
        backup.write_bytes(storage.read_bytes())
        return backup

    def _restore_backup(self, backup_path: Path | None) -> None:
        storage = self.repository.storage_path
        if backup_path is None:
            if storage.exists():
                storage.unlink()
            return
        payload = backup_path.read_bytes()
        storage.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("wb", dir=str(storage.parent), delete=False) as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        os.replace(temp_path, storage)
