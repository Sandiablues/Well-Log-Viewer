"""Canonical UUIDv7 assignment and reconciliation for managed inventory writes.

This module is the backend-owned creation boundary for MSI identities.  It
assigns UUIDv7 values only during a durable inventory upsert and reuses existing
canonical identities when the same legacy entity is registered again.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.identity import IdentityAssignmentMetadata, LegacyIdentityAlias, new_uuid7_str

from .models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceReference,
    ManagedWellRecord,
    ViewerPackageReference,
)

_ASSIGNMENT_SOURCE = "managed_inventory_upsert_v1"


def _assignment(existing: IdentityAssignmentMetadata | None) -> IdentityAssignmentMetadata:
    return existing or IdentityAssignmentMetadata(assignment_source=_ASSIGNMENT_SOURCE)


def _aliases(
    current: Iterable[LegacyIdentityAlias],
    *values: tuple[str, str | None],
) -> list[LegacyIdentityAlias]:
    result = list(current)
    seen = {(alias.scheme, alias.value) for alias in result}
    for scheme, value in values:
        normalized = str(value).strip() if value is not None else ""
        if not normalized or (scheme, normalized) in seen:
            continue
        result.append(LegacyIdentityAlias(scheme=scheme, value=normalized))
        seen.add((scheme, normalized))
    return result


def _uid(incoming: str | None, existing: str | None) -> str:
    return incoming or existing or new_uuid7_str()


def reconcile_managed_record_identity(
    record: ManagedWellRecord,
    *,
    existing: ManagedWellRecord | None = None,
) -> ManagedWellRecord:
    """Assign or reconcile all canonical identities for one durable upsert.

    Legacy IDs remain lookup aliases.  Existing canonical UUIDv7 values always
    win over generating replacements, so repeated registration/rescan operations
    preserve entity identity.
    """

    managed_well_uid = _uid(
        record.managed_well_uid,
        existing.managed_well_uid if existing else None,
    )
    managed_wellbore_uid = _uid(
        record.managed_wellbore_uid,
        existing.managed_wellbore_uid if existing else None,
    )

    existing_sources = {
        source.source_id: source
        for source in (existing.source_references if existing else [])
    }
    reconciled_sources: list[ManagedSourceReference] = []
    source_uid_by_legacy_id: dict[str, str] = {}

    for source in record.source_references:
        previous = existing_sources.get(source.source_id)
        managed_source_uid = _uid(
            source.managed_source_uid,
            previous.managed_source_uid if previous else None,
        )
        occurrence_uid = _uid(
            source.source_occurrence_uid,
            previous.source_occurrence_uid if previous else None,
        )
        source_uid_by_legacy_id[source.source_id] = managed_source_uid
        reconciled_sources.append(
            source.model_copy(
                update={
                    "managed_source_uid": managed_source_uid,
                    "source_occurrence_uid": occurrence_uid,
                    "identity_assignment": source.identity_assignment
                    or (previous.identity_assignment if previous else None)
                    or _assignment(None),
                    "legacy_ids": _aliases(
                        source.legacy_ids
                        or (previous.legacy_ids if previous else []),
                        ("managed_source_reference_source_id_v1", source.source_id),
                    ),
                }
            )
        )

    existing_packages = {
        package.viewer_package_id: package
        for package in (existing.viewer_packages if existing else [])
    }
    reconciled_packages: list[ViewerPackageReference] = []
    for package in record.viewer_packages:
        previous = existing_packages.get(package.viewer_package_id)
        reconciled_packages.append(
            package.model_copy(
                update={
                    "viewer_package_uid": _uid(
                        package.viewer_package_uid,
                        previous.viewer_package_uid if previous else None,
                    ),
                    "representation_uid": _uid(
                        package.representation_uid,
                        previous.representation_uid if previous else None,
                    ),
                    "identity_assignment": package.identity_assignment
                    or (previous.identity_assignment if previous else None)
                    or _assignment(None),
                    "legacy_ids": _aliases(
                        package.legacy_ids
                        or (previous.legacy_ids if previous else []),
                        ("viewer_package_id_v1", package.viewer_package_id),
                        ("representation_id_v1", package.representation_id),
                    ),
                }
            )
        )

    existing_products = {
        item.product_id: item
        for group in (existing.product_groups if existing else [])
        for item in group.items
    }
    reconciled_groups: list[ManagedProductGroup] = []
    default_source_uid = (
        reconciled_sources[0].managed_source_uid if reconciled_sources else None
    )

    for group in record.product_groups:
        reconciled_items: list[ManagedProductGroupItem] = []
        for item in group.items:
            previous = existing_products.get(item.product_id)
            source_uid = (
                item.managed_source_uid
                or (previous.managed_source_uid if previous else None)
                or source_uid_by_legacy_id.get(item.source_id or "")
                or default_source_uid
                or new_uuid7_str()
            )
            reconciled_items.append(
                item.model_copy(
                    update={
                        "managed_product_uid": _uid(
                            item.managed_product_uid,
                            previous.managed_product_uid if previous else None,
                        ),
                        "managed_curve_uid": _uid(
                            item.managed_curve_uid,
                            previous.managed_curve_uid if previous else None,
                        ),
                        "managed_wellbore_uid": managed_wellbore_uid,
                        "managed_source_uid": source_uid,
                        "identity_assignment": item.identity_assignment
                        or (previous.identity_assignment if previous else None)
                        or _assignment(None),
                        "legacy_ids": _aliases(
                            item.legacy_ids
                            or (previous.legacy_ids if previous else []),
                            ("managed_product_product_id_v1", item.product_id),
                            ("wlv_curve_sha1_v1", item.curve_uid),
                        ),
                    }
                )
            )
        reconciled_groups.append(group.model_copy(update={"items": reconciled_items}))

    return record.model_copy(
        update={
            "managed_well_uid": managed_well_uid,
            "managed_wellbore_uid": managed_wellbore_uid,
            "identity_assignment": record.identity_assignment
            or (existing.identity_assignment if existing else None)
            or _assignment(None),
            "legacy_ids": _aliases(
                record.legacy_ids or (existing.legacy_ids if existing else []),
                ("managed_well_id_v1", record.managed_well_id),
                ("well_id_v1", record.well_id),
                ("wellbore_id_v1", record.wellbore_id),
            ),
            "source_references": reconciled_sources,
            "viewer_packages": reconciled_packages,
            "product_groups": reconciled_groups,
        }
    )
