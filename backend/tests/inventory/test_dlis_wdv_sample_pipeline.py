from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.inventory import dlis_sample_reader
from app.inventory.curve_sample_service import CurveSampleService
from app.inventory.dlis_sample_reader import DlisSampleReaderError, read_dlis_curve_samples
from app.inventory.models import ManagedProductGroup, ManagedProductGroupItem, ManagedWellRecord
from app.inventory.repository import ManagedWellInventoryRepository


class _Channel:
    def __init__(self, name, *, units=None, dimension=None, null=None):
        self.name = name
        self.units = units
        self.dimension = dimension or []
        self.null = null


class _Frame:
    name = "FRAME-A"
    index = "DEPTH"

    def __init__(self, *, multidimensional=False):
        dimension = [2, 2] if multidimensional else []
        self.channels = [
            _Channel("DEPTH", units="cm"),
            _Channel("GR", units="gAPI", dimension=dimension, null=-888.0),
        ]
        self._multidimensional = multidimensional

    def curves(self, strict=False):
        if self._multidimensional:
            return np.array(
                [(10000.0, np.ones((2, 2)))],
                dtype=[("DEPTH", "f8"), ("GR", "f8", (2, 2))],
            )
        return np.array(
            [
                (10000.0, 10.0),
                (10100.0, -888.0),
                (10200.0, -999.25),
                (10300.0, np.nan),
                (10400.0, 14.0),
            ],
            dtype=[("DEPTH", "f8"), ("GR", "f8")],
        )


class _LogicalFile:
    fileheader = SimpleNamespace(id="LF-1")

    def __init__(self, *, multidimensional=False):
        self.frames = [_Frame(multidimensional=multidimensional)]


@contextmanager
def _physical_file(*, multidimensional=False):
    yield [_LogicalFile(multidimensional=multidimensional)]


def _patch_dlis(monkeypatch, *, multidimensional=False):
    monkeypatch.setattr(
        dlis_sample_reader,
        "dlis",
        SimpleNamespace(load=lambda _: _physical_file(multidimensional=multidimensional)),
    )


def test_dlis_reader_returns_common_statistics_and_exact_provenance(monkeypatch, tmp_path: Path):
    _patch_dlis(monkeypatch)
    source = tmp_path / "sample.dlis"
    source.write_bytes(b"fixture")

    result = read_dlis_curve_samples(
        source_path=source,
        curve_mnemonic="GR",
        channel_mnemonic="GR",
        logical_file_id="LF-1",
        frame_id="FRAME-A",
        max_samples=1,
    )

    assert result["source_format"] == "DLIS"
    assert result["dlis_logical_file_id"] == "LF-1"
    assert result["dlis_frame_id"] == "FRAME-A"
    assert result["dlis_channel_mnemonic"] == "GR"
    assert result["dlis_index_channel"] == "DEPTH"
    assert result["depth_unit"] == "m"
    assert result["depth_min"] == 100.0
    assert result["depth_max"] == 104.0
    assert result["sample_count"] == 2
    assert result["raw_numeric_sample_count"] == 4
    assert result["rejected_null_count"] == 1
    assert result["rejected_sentinel_count"] == 1
    assert result["rejected_nonfinite_count"] == 1
    assert result["samples"] == [[100.0, 10.0], [104.0, 14.0]]


def test_dlis_reader_rejects_multidimensional_channel(monkeypatch, tmp_path: Path):
    _patch_dlis(monkeypatch, multidimensional=True)
    source = tmp_path / "sample.dlis"
    source.write_bytes(b"fixture")

    with pytest.raises(DlisSampleReaderError, match="not scalar"):
        read_dlis_curve_samples(
            source_path=source,
            curve_mnemonic="GR",
            logical_file_id="LF-1",
            frame_id="FRAME-A",
            max_samples=100,
        )


def test_product_sample_service_uses_same_wdv_contract_for_dlis(monkeypatch, tmp_path: Path):
    _patch_dlis(monkeypatch)
    source = tmp_path / "sample.dlis"
    source.write_bytes(b"fixture")
    repository = ManagedWellInventoryRepository(storage_path=tmp_path / "inventory.json")
    repository.upsert_record(ManagedWellRecord(
        managed_well_id="managed-well:dlis",
        well_id="dlis",
        well_name="DLIS Well",
        product_groups=[ManagedProductGroup(
            group_key="open_hole_logs",
            group_label="Open hole logs",
            items=[ManagedProductGroupItem(
                product_id="product:gr",
                display_name="GR",
                curve_name="GR",
                curve_type="Gamma Ray",
                curve_unit="gAPI",
                product_category="open_hole_logs",
                curve_family="Gamma Ray",
                source_kind="dlis",
                provenance={
                    "original_path": str(source),
                    "dlis_logical_file_id": "LF-1",
                    "dlis_frame_id": "FRAME-A",
                    "dlis_channel_mnemonic": "GR",
                    "dlis_index_channel": "DEPTH",
                },
            )],
        )],
    ))

    response = CurveSampleService(repository=repository).get_curve_samples(
        "managed-well:dlis", "product:gr", max_samples=100
    )

    assert response["contract_kind"] == "wdv_product_curve_samples"
    assert response["contract_version"] == "wdv_product_curve_samples_v1"
    assert response["sample_source"] == "dlis_original_path"
    assert response["source_format"] == "DLIS"
    assert response["sample_provenance"] == {
        "dlis_logical_file_id": "LF-1",
        "dlis_frame_id": "FRAME-A",
        "dlis_channel_mnemonic": "GR",
        "dlis_index_channel": "DEPTH",
    }
    assert response["depth_unit"] == "m"
    assert response["value_unit"] == "gAPI"
    assert response["sample_count"] == 2
    assert response["samples"] == [[100.0, 10.0], [104.0, 14.0]]
