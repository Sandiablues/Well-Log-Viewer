from types import SimpleNamespace

import pytest

from app.depth_reference import (
    build_well_depth_contract,
    convert_depth,
    make_source_depth_contract,
    transform_sample_payload,
    well_depth_contract_from_record,
)


def source(unit, minimum, maximum, *, raw_unit=None, raw_minimum=None, raw_maximum=None, basis="source_native"):
    return make_source_depth_contract(
        raw_unit=raw_unit or unit,
        raw_minimum=minimum if raw_minimum is None else raw_minimum,
        raw_maximum=maximum if raw_maximum is None else raw_maximum,
        normalized_unit=unit,
        normalized_minimum=minimum,
        normalized_maximum=maximum,
        basis=basis,
    )


def test_scaled_point_one_inch_is_physical_and_converts_without_numeric_merge():
    assert convert_depth(74760.0, "0.1 in", "m") == pytest.approx(189.8904)
    assert convert_depth(1494120.0, "0.1 in", "m") == pytest.approx(3795.0648)


def test_mixed_native_units_aggregate_into_one_explicit_well_reference():
    metric = source("m", 100.0, 2000.0)
    imperial = source("ft", 500.0, 10000.0)
    contract = build_well_depth_contract(
        existing_contract={"unit": "m"},
        existing_well_unit="0.1 in",
        source_contracts=[metric, imperial],
    )
    assert contract["unit"] == "m"
    assert contract["minimum"] == pytest.approx(100.0)
    assert contract["maximum"] == pytest.approx(3048.0)


def test_raw_scaled_samples_are_normalized_then_rendered_in_well_unit():
    contract = source(
        "m", 189.8904, 3795.0648,
        raw_unit="0.1 in", raw_minimum=74760.0, raw_maximum=1494120.0,
        basis="human_resolved",
    )
    parsed = {
        "depth_unit": "0.1 in",
        "depth_min": 74760.0,
        "depth_max": 1494120.0,
        "samples": [[74760.0, 1.0], [1494120.0, 2.0]],
    }
    result = transform_sample_payload(parsed, source_contract=contract, target_unit="m")
    assert result["depth_unit"] == "m"
    assert result["depth_min"] == pytest.approx(189.8904)
    assert result["depth_max"] == pytest.approx(3795.0648)
    assert result["samples"][0][0] == pytest.approx(189.8904)


def test_feet_samples_from_another_source_are_rendered_in_same_metric_wdv_domain():
    parsed = {
        "depth_unit": "ft",
        "depth_min": 4593.0,
        "depth_max": 9538.5,
        "samples": [[4593.0, 1.0], [9538.5, 2.0]],
    }
    result = transform_sample_payload(parsed, source_contract=None, target_unit="m")
    assert result["depth_unit"] == "m"
    assert result["depth_min"] == pytest.approx(1399.9464)
    assert result["depth_max"] == pytest.approx(2907.3348)


def test_well_contract_includes_legacy_scaled_source_once_well_unit_is_explicit():
    resolved = source("m", 189.8904, 3795.0648, basis="human_resolved")
    sources = [
        SimpleNamespace(metadata={
            "parsed_metadata": {"log_header": {
                "start_depth": 74760.0,
                "stop_depth": 1494120.0,
                "depth_unit": "0.1 in",
            }}
        }),
        SimpleNamespace(metadata={"depth_reference": resolved}),
    ]
    well = SimpleNamespace(
        metadata={"depth_reference": {"unit": "m"}},
        depth_unit="0.1 in",
        source_references=sources,
    )
    contract = well_depth_contract_from_record(well)
    assert contract["unit"] == "m"
    assert contract["minimum"] == pytest.approx(189.8904)
    assert contract["maximum"] == pytest.approx(3795.0648)
    assert contract["source_contract_count"] == 2

def test_migration_service_uses_repository_snapshot_contract(tmp_path):
    from app.inventory.models import ManagedInventorySnapshot
    from app.inventory.repository import ManagedWellInventoryRepository
    from app.source_intake.managed_depth_contract_service import ManagedDepthContractMigrationService

    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    repository.write_snapshot(ManagedInventorySnapshot(records=[]))

    migrated = ManagedDepthContractMigrationService(repository).migrate([])

    assert migrated.records == []
    assert repository.snapshot().records == []
