from pathlib import Path

import pytest

from app.identity import new_uuid7_str
from app.inventory.canonical_identity_resolver import (
    CanonicalIdentityResolutionError,
    CanonicalInventoryIdentityResolver,
)
from app.inventory.models import (
    ManagedInventorySnapshot,
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository, ManagedWellNotFoundError


def _repository(tmp_path: Path) -> tuple[ManagedWellInventoryRepository, dict[str, str]]:
    ids = {name: new_uuid7_str() for name in ("well", "wellbore", "source", "product", "curve")}
    record = ManagedWellRecord(
        managed_well_id="legacy-well-1",
        managed_well_uid=ids["well"],
        managed_wellbore_uid=ids["wellbore"],
        well_id="WELL-1",
        well_name="Well 1",
        source_references=[ManagedSourceReference(
            source_id="legacy-source-1",
            managed_source_uid=ids["source"],
            source_kind=ManagedSourceKind.LAS,
            display_name="well1.las",
        )],
        product_groups=[ManagedProductGroup(
            group_key="open_hole",
            group_label="Open Hole",
            items=[ManagedProductGroupItem(
                product_id="legacy-product-1",
                managed_product_uid=ids["product"],
                managed_curve_uid=ids["curve"],
                managed_wellbore_uid=ids["wellbore"],
                managed_source_uid=ids["source"],
                display_name="Gamma Ray",
                curve_name="GR",
                curve_type="curve",
            )],
        )],
    )
    repository = ManagedWellInventoryRepository(tmp_path / "inventory.json")
    repository.write_snapshot(ManagedInventorySnapshot(records=[record]))
    return repository, ids


def test_resolves_curve_only_by_canonical_well_and_curve_uid(tmp_path: Path) -> None:
    repository, ids = _repository(tmp_path)
    resolver = CanonicalInventoryIdentityResolver(repository)

    resolved = resolver.resolve_curve(ids["well"], ids["curve"])

    assert resolved.managed_well_uid == ids["well"]
    assert resolved.managed_curve_uid == ids["curve"]
    assert resolved.managed_product_uid == ids["product"]
    assert resolved.managed_source_uid == ids["source"]
    assert resolved.product.curve_name == "GR"


def test_rejects_legacy_well_or_curve_keys(tmp_path: Path) -> None:
    repository, ids = _repository(tmp_path)
    resolver = CanonicalInventoryIdentityResolver(repository)

    with pytest.raises(ValueError):
        resolver.resolve_curve("legacy-well-1", ids["curve"])
    with pytest.raises(ValueError):
        resolver.resolve_curve(ids["well"], "GR")


def test_readiness_report_is_clean_for_complete_inventory(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    report = CanonicalInventoryIdentityResolver(repository).readiness_report()

    assert report.ready is True
    assert report.wells_checked == 1
    assert report.products_checked == 1
    assert report.sources_checked == 1
    assert report.issues == ()


def test_readiness_report_detects_missing_curve_identity(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    snapshot = repository.snapshot()
    snapshot.records[0].product_groups[0].items[0].managed_curve_uid = None
    repository.write_snapshot(snapshot)

    report = CanonicalInventoryIdentityResolver(repository).readiness_report()

    assert report.ready is False
    assert any(issue.code == "missing_managed_curve_uid" for issue in report.issues)


def test_ambiguous_curve_uid_is_rejected(tmp_path: Path) -> None:
    repository, ids = _repository(tmp_path)
    snapshot = repository.snapshot()
    duplicate = snapshot.records[0].product_groups[0].items[0].model_copy(
        update={"product_id": "legacy-product-2", "managed_product_uid": new_uuid7_str()}
    )
    snapshot.records[0].product_groups[0].items.append(duplicate)
    repository.write_snapshot(snapshot)

    resolver = CanonicalInventoryIdentityResolver(repository)
    with pytest.raises(CanonicalIdentityResolutionError, match="Ambiguous managed_curve_uid"):
        resolver.resolve_curve(ids["well"], ids["curve"])
