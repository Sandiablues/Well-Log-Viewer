from pathlib import Path

from app.inventory.models import (
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


def _record() -> ManagedWellRecord:
    return ManagedWellRecord(
        managed_well_id="managed-well:test",
        well_id="test",
        well_name="Test Well",
        depth_unit="ft",
        source_references=[
            ManagedSourceReference(
                source_id="source:test",
                source_kind=ManagedSourceKind.LAS,
                display_name="test.las",
            )
        ],
        product_groups=[
            ManagedProductGroup(
                group_key="open_hole_logs",
                group_label="Open hole logs",
                items=[
                    ManagedProductGroupItem(
                        product_id="curve:test:sp",
                        display_name="SP",
                        curve_name="SP",
                        curve_type="Spontaneous Potential",
                        curve_description="Spontaneous Potential",
                        curve_unit="mV",
                        product_category="open_hole_logs",
                        curve_family="spontaneous_potential",
                        review_required=False,
                        source_kind=ManagedSourceKind.LAS.value,
                        provenance={"checksum": "abc123"},
                    )
                ],
            )
        ],
    )


def test_wdv_curve_contract_exposes_backend_sample_access(tmp_path: Path, monkeypatch) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    record = _record()
    repository.upsert_record(record)

    monkeypatch.setattr(
        service,
        "_wdv_curve_sample_statistics",
        lambda _record, _item: {
            "statistics_status": "available",
            "valid_sample_count": 255,
            "depth_min": 1000.0,
            "depth_max": 1254.0,
            "observed_min": -20.0,
            "observed_max": 80.0,
            "robust_observed_min": -10.0,
            "robust_observed_max": 70.0,
            "rejected_sample_count": 0,
        },
    )

    contract = service._wdv_curve_contract_from_product_item(
        record,
        record.product_groups[0].items[0],
    )

    assert contract["is_renderable"] is True
    assert contract["support_status"] == "renderable"
    assert contract["samples_url"].endswith("curve-samples?product_id=curve%3Atest%3Asp")
    assert contract["sample_access"]["status"] == "available"
    assert contract["sample_access"]["sample_count"] == 255
    assert contract["sample_access"]["depth_min"] == 1000.0
    assert contract["sample_access"]["depth_max"] == 1254.0
    assert contract["sample_access"]["revision"] == contract["sample_revision"]


def test_wdv_curve_contract_blocks_missing_samples(tmp_path: Path, monkeypatch) -> None:
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    service = ManagedWellInventoryService(repository=repository)
    record = _record()
    repository.upsert_record(record)

    monkeypatch.setattr(
        service,
        "_wdv_curve_sample_statistics",
        lambda _record, _item: {
            "statistics_status": "unavailable",
            "valid_sample_count": 0,
            "statistics_error": "missing source",
        },
    )

    contract = service._wdv_curve_contract_from_product_item(
        record,
        record.product_groups[0].items[0],
    )

    assert contract["is_renderable"] is False
    assert contract["support_status"] == "samples_unavailable"
    assert contract["sample_access"]["status"] == "unavailable"
    assert contract["sample_access"]["sample_count"] == 0
