from pathlib import Path

from app.inventory.models import (
    ManagedCurveStatisticsContract,
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedWellRecord,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


def _record_with_item(*, statistics=None):
    item = ManagedProductGroupItem(
        product_id="curve:test:gr",
        display_name="GR",
        curve_name="GR",
        curve_type="Gamma Ray",
        curve_unit="gAPI",
        curve_family="Gamma Ray",
        curve_statistics=statistics,
        provenance={"checksum": "source-checksum"},
    )
    record = ManagedWellRecord(
        managed_well_id="managed-well:test",
        well_id="well:test",
        well_name="Test Well",
        depth_unit="m",
        product_groups=[
            ManagedProductGroup(
                group_key="open_hole_logs",
                group_label="Open Hole Logs",
                items=[item],
            )
        ],
    )
    return record, item


def test_persisted_statistics_fast_path_does_not_read_curve_samples(tmp_path: Path, monkeypatch) -> None:
    repository = ManagedWellInventoryRepository(
        storage_path=tmp_path / "inventory.json"
    )
    service = ManagedWellInventoryService(repository=repository)

    statistics = ManagedCurveStatisticsContract(
        statistics_status="available",
        depth_min=1000.0,
        depth_max=1100.0,
        value_min=10.0,
        value_max=120.0,
        robust_value_min=15.0,
        robust_value_max=100.0,
        value_p01=11.0,
        value_p05=15.0,
        value_p50=50.0,
        value_p95=100.0,
        value_p99=115.0,
        valid_sample_count=1001,
        raw_numeric_sample_count=1010,
        rejected_sample_count=9,
        rejected_null_count=5,
        rejected_sentinel_count=2,
        rejected_nonfinite_count=1,
        rejected_plausibility_count=0,
        rejected_row_count=1,
        source_checksum="source-checksum",
    )
    record, item = _record_with_item(statistics=statistics)

    def fail_if_called(**_kwargs):
        raise AssertionError(
            "CurveSampleService must not be called when persisted statistics exist."
        )

    monkeypatch.setattr(
        service.curve_sample_service,
        "get_curve_samples",
        fail_if_called,
    )

    result = service._wdv_curve_sample_statistics(record, item)

    assert result == {
        "statistics_status": "available",
        "observed_min": 10.0,
        "observed_max": 120.0,
        "robust_observed_min": 15.0,
        "robust_observed_max": 100.0,
        "observed_p01": 11.0,
        "observed_p05": 15.0,
        "observed_p50": 50.0,
        "observed_p95": 100.0,
        "observed_p99": 115.0,
        "depth_min": 1000.0,
        "depth_max": 1100.0,
        "valid_sample_count": 1001,
        "raw_numeric_sample_count": 1010,
        "rejected_sample_count": 9,
        "rejected_null_count": 5,
        "rejected_sentinel_count": 2,
        "rejected_nonfinite_count": 1,
        "rejected_plausibility_count": 0,
        "rejected_row_count": 1,
    }


def test_legacy_record_without_persisted_statistics_uses_existing_sample_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = ManagedWellInventoryRepository(
        storage_path=tmp_path / "inventory.json"
    )
    service = ManagedWellInventoryService(repository=repository)
    record, item = _record_with_item(statistics=None)

    calls = []

    def fake_get_curve_samples(**kwargs):
        calls.append(kwargs)
        return {
            "value_min": 1.0,
            "value_max": 9.0,
            "robust_value_min": 2.0,
            "robust_value_max": 8.0,
            "value_p01": 1.1,
            "value_p05": 2.0,
            "value_p50": 5.0,
            "value_p95": 8.0,
            "value_p99": 8.9,
            "depth_min": 100.0,
            "depth_max": 200.0,
            "sample_count": 50,
            "raw_numeric_sample_count": 52,
            "rejected_sample_count": 2,
            "rejected_null_count": 1,
            "rejected_sentinel_count": 1,
            "rejected_plausibility_count": 0,
        }

    monkeypatch.setattr(
        service.curve_sample_service,
        "get_curve_samples",
        fake_get_curve_samples,
    )

    result = service._wdv_curve_sample_statistics(record, item)

    assert len(calls) == 1
    assert calls[0] == {
        "managed_well_id": record.managed_well_id,
        "product_id": item.product_id,
        "max_samples": 12000,
    }
    assert result["statistics_status"] == "available"
    assert result["valid_sample_count"] == 50
    assert result["observed_p05"] == 2.0


def test_persisted_unavailable_statistics_remain_authoritative_and_do_not_fall_back(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = ManagedWellInventoryRepository(
        storage_path=tmp_path / "inventory.json"
    )
    service = ManagedWellInventoryService(repository=repository)

    statistics = ManagedCurveStatisticsContract(
        statistics_status="unavailable",
        valid_sample_count=0,
        raw_numeric_sample_count=4,
        rejected_sample_count=4,
        rejected_nonfinite_count=4,
    )
    record, item = _record_with_item(statistics=statistics)

    def fail_if_called(**_kwargs):
        raise AssertionError(
            "Persisted statistics presence is authoritative; no hidden source reread is allowed."
        )

    monkeypatch.setattr(
        service.curve_sample_service,
        "get_curve_samples",
        fail_if_called,
    )

    result = service._wdv_curve_sample_statistics(record, item)

    assert result["statistics_status"] == "unavailable"
    assert result["valid_sample_count"] == 0
    assert result["rejected_sample_count"] == 4
