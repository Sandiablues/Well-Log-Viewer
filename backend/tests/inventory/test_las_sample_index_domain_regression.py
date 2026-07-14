from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from app.inventory.curve_sample_service import (
    CurveSampleServiceError,
    _read_managed_las_curve_samples,
)


def _write_store(path: Path, curve_indices: list[int]) -> None:
    payload = {
        "storage_contract": "wlv_las_samples_v1",
        "depth_values": [1000.0, 1000.5],
        "curves": [
            {
                "curve_index": curve_index,
                "mnemonic": f"C{position}",
                "values": [float(position * 10), float(position * 10 + 1)],
            }
            for position, curve_index in enumerate(curve_indices)
        ],
    }
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)


def _values(result: dict) -> list[float]:
    return [float(sample[1]) for sample in result["samples"]]


def test_zero_based_store_maps_source_indices_without_shift(tmp_path: Path) -> None:
    store = tmp_path / "zero_based.json.gz"
    _write_store(store, [0, 1])

    first = _read_managed_las_curve_samples(store, 0, 12000)
    second = _read_managed_las_curve_samples(store, 1, 12000)

    assert _values(first) == [0.0, 1.0]
    assert _values(second) == [10.0, 11.0]


def test_one_based_store_maps_source_indices_with_exact_plus_one_shift(tmp_path: Path) -> None:
    store = tmp_path / "one_based.json.gz"
    _write_store(store, [1, 2])

    first = _read_managed_las_curve_samples(store, 0, 12000)
    second = _read_managed_las_curve_samples(store, 1, 12000)

    assert _values(first) == [0.0, 1.0]
    assert _values(second) == [10.0, 11.0]


def test_ambiguous_store_is_rejected_without_guessing(tmp_path: Path) -> None:
    store = tmp_path / "ambiguous.json.gz"
    _write_store(store, [2, 3])

    with pytest.raises(CurveSampleServiceError, match="ambiguous curve index domain"):
        _read_managed_las_curve_samples(store, 0, 12000)
