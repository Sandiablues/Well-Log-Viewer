"""UID-2 contract tests for canonical UUIDv7 fields on MSI models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.identity import new_uuid7_str
from app.inventory.models import (
    ManagedInventorySnapshot,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
    ViewerPackageReference,
)


def legacy_well_payload() -> dict[str, object]:
    return {
        "managed_well_id": "managed-well:legacy-1",
        "well_id": "legacy-well-1",
        "well_name": "Legacy Well",
    }


def test_legacy_inventory_payload_remains_valid_without_uuid_generation() -> None:
    record = ManagedWellRecord.model_validate(legacy_well_payload())

    assert record.managed_well_uid is None
    assert record.managed_wellbore_uid is None
    assert record.identity_assignment is None
    assert record.legacy_ids == []


def test_snapshot_schema_version_is_not_migrated_by_contract_expansion() -> None:
    snapshot = ManagedInventorySnapshot(
        records=[ManagedWellRecord.model_validate(legacy_well_payload())]
    )

    assert snapshot.schema_version == "wlv_managed_inventory_v2"


def test_managed_well_accepts_and_normalizes_uuid7_identity_fields() -> None:
    well_uid = new_uuid7_str()
    wellbore_uid = new_uuid7_str()
    record = ManagedWellRecord(
        **legacy_well_payload(),
        managed_well_uid=well_uid.upper(),
        managed_wellbore_uid=wellbore_uid,
        identity_assignment={"assignment_source": "uid-2-contract-test"},
        legacy_ids=[
            {"scheme": "managed_well_id_v2", "value": "managed-well:legacy-1"}
        ],
    )

    assert record.managed_well_uid == well_uid
    assert record.managed_wellbore_uid == wellbore_uid
    assert record.identity_assignment is not None
    assert record.identity_assignment.assignment_source == "uid-2-contract-test"
    assert record.legacy_ids[0].value == "managed-well:legacy-1"


def test_source_reference_separates_managed_source_and_occurrence_identity() -> None:
    managed_source_uid = new_uuid7_str()
    source_occurrence_uid = new_uuid7_str()
    source = ManagedSourceReference(
        source_id="occ:legacy-source",
        managed_source_uid=managed_source_uid,
        source_occurrence_uid=source_occurrence_uid,
        source_kind=ManagedSourceKind.LAS,
        display_name="legacy.las",
    )

    assert source.managed_source_uid == managed_source_uid
    assert source.source_occurrence_uid == source_occurrence_uid
    assert source.source_id == "occ:legacy-source"


def test_product_item_carries_distinct_product_curve_wellbore_and_source_uids() -> None:
    values = [new_uuid7_str() for _ in range(4)]
    item = ManagedProductGroupItem(
        product_id="source-intake-curve:legacy",
        managed_product_uid=values[0],
        managed_curve_uid=values[1],
        managed_wellbore_uid=values[2],
        managed_source_uid=values[3],
        display_name="GR",
        curve_name="GR",
        curve_type="gamma_ray",
    )

    assert item.managed_product_uid == values[0]
    assert item.managed_curve_uid == values[1]
    assert item.managed_wellbore_uid == values[2]
    assert item.managed_source_uid == values[3]
    assert item.product_id == "source-intake-curve:legacy"


def test_viewer_package_separates_package_and_representation_uids() -> None:
    package_uid = new_uuid7_str()
    representation_uid = new_uuid7_str()
    package = ViewerPackageReference(
        viewer_package_id="legacy-viewer-package",
        viewer_package_uid=package_uid,
        representation_uid=representation_uid,
        viewer_package_version="well_multitrack_v1",
        dataset_id="legacy-dataset",
        representation_id="legacy-representation",
        well_id="legacy-well",
        endpoint="/api/example",
    )

    assert package.viewer_package_uid == package_uid
    assert package.representation_uid == representation_uid
    assert package.representation_id == "legacy-representation"


def test_non_uuid7_values_are_rejected_for_canonical_fields() -> None:
    with pytest.raises(ValidationError):
        ManagedWellRecord(
            **legacy_well_payload(),
            managed_well_uid="550e8400-e29b-41d4-a716-446655440000",
        )
