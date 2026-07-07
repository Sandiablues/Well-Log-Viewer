from pathlib import Path

from app.inventory.curve_sample_service import CurveSampleService
from app.inventory.models import ManagedProductGroup, ManagedProductGroupItem, ManagedWellRecord
from app.inventory.repository import ManagedWellInventoryRepository


def test_curve_sample_service_passes_managed_depth_unit_to_dlis_reader(monkeypatch, tmp_path: Path):
    source = tmp_path / "sample.dlis"
    source.write_bytes(b"fixture")

    captured = {}

    def fake_read_source_curve_samples(**kwargs):
        captured.update(kwargs)
        return (
            {
                "depth_unit": kwargs["target_depth_unit"],
                "value_unit": "gAPI",
                "depth_min": 100.0,
                "depth_max": 101.0,
                "value_min": 1.0,
                "value_max": 2.0,
                "robust_value_min": 1.0,
                "robust_value_max": 2.0,
                "sample_count": 2,
                "raw_numeric_sample_count": 2,
                "rejected_sample_count": 0,
                "decimation_stride": 1,
                "samples": [[100.0, 1.0], [101.0, 2.0]],
                "source_format": "DLIS",
                "dlis_logical_file_id": "LF-1",
                "dlis_frame_id": "0",
                "dlis_channel_mnemonic": "A16H",
                "dlis_index_channel": "DEPTH",
            },
            "dlis_original_path",
        )

    monkeypatch.setattr(
        "app.inventory.curve_sample_service._read_source_curve_samples",
        fake_read_source_curve_samples,
    )

    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    repository.upsert_record(
        ManagedWellRecord(
            managed_well_id="managed-well:f5",
            well_id="f5",
            well_name="15/9-F-5",
            field="Volve",
            operator="StatoilHydro ASA",
            depth_unit="m",
            top_depth=189.8904,
            base_depth=3795.0648,
            product_groups=[
                ManagedProductGroup(
                    group_key="open_hole_logs",
                    group_label="Open hole logs",
                    items=[
                        ManagedProductGroupItem(
                            product_id="product:a16h",
                            display_name="A16H",
                            curve_name="A16H",
                            curve_type="Resistivity",
                            curve_unit="ohm.m",
                            product_category="open_hole_logs",
                            curve_family="Resistivity",
                            source_kind="dlis",
                            provenance={
                                "original_path": str(source),
                                "dlis_logical_file_id": "LF-1",
                                "dlis_frame_id": "0",
                                "dlis_channel_mnemonic": "A16H",
                                "dlis_index_channel": "DEPTH",
                            },
                        )
                    ],
                )
            ],
        )
    )

    response = CurveSampleService(repository=repository).get_curve_samples(
        "managed-well:f5",
        "product:a16h",
    )

    assert captured["target_depth_unit"] == "m"
    assert response["depth_unit"] == "m"
    assert response["sample_provenance"]["dlis_index_channel"] == "DEPTH"
