from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.inventory import dlis_sample_reader
from app.inventory.dlis_sample_reader import DlisSampleReaderError, read_dlis_curve_samples
from app.source_intake.depth_units import convert_depth_range_to_target
from app.source_intake.registration import _managed_depth_range


class _Channel:
    def __init__(self, name: str, units: str | None = None):
        self.name = name
        self.units = units
        self.dimension = []
        self.null = None


class _Frame:
    name = "FRAME"
    index = "DEPTH"

    def __init__(self, unit: str):
        self.channels = [_Channel("DEPTH", unit), _Channel("GR", "gAPI")]

    def curves(self, strict=False):
        return np.array(
            [(74760.0, 10.0), (1494120.0, 20.0)],
            dtype=[("DEPTH", "f8"), ("GR", "f8")],
        )


class _Logical:
    fileheader = SimpleNamespace(id="LF")

    def __init__(self, unit: str):
        self.frames = [_Frame(unit)]


@contextmanager
def _physical(unit: str):
    yield [_Logical(unit)]


def _patch(monkeypatch, unit: str):
    monkeypatch.setattr(
        dlis_sample_reader,
        "dlis",
        SimpleNamespace(load=lambda _: _physical(unit)),
    )


def test_scaled_dlis_depth_is_plot_ready_in_metres(monkeypatch, tmp_path: Path):
    _patch(monkeypatch, "0.1 in")
    source = tmp_path / "f5.dlis"
    source.write_bytes(b"fixture")
    result = read_dlis_curve_samples(
        source_path=source,
        curve_mnemonic="GR",
        max_samples=100,
        target_depth_unit="m",
    )
    assert result["depth_unit"] == "m"
    assert result["depth_min"] == 189.8904
    assert result["depth_max"] == 3795.0648
    assert result["samples"] == [[189.8904, 10.0], [3795.0648, 20.0]]


def test_scaled_dlis_depth_is_plot_ready_in_feet(monkeypatch, tmp_path: Path):
    _patch(monkeypatch, "0.1 in")
    source = tmp_path / "f5.dlis"
    source.write_bytes(b"fixture")
    result = read_dlis_curve_samples(
        source_path=source,
        curve_mnemonic="GR",
        max_samples=100,
        target_depth_unit="ft",
    )
    assert result["depth_unit"] == "ft"
    assert result["depth_min"] == 623.0
    assert result["depth_max"] == 12451.0


def test_unknown_dlis_depth_unit_is_rejected(monkeypatch, tmp_path: Path):
    _patch(monkeypatch, "banana")
    source = tmp_path / "bad.dlis"
    source.write_bytes(b"fixture")
    with pytest.raises(DlisSampleReaderError, match="Cannot normalize depth unit"):
        read_dlis_curve_samples(
            source_path=source,
            curve_mnemonic="GR",
            max_samples=100,
            target_depth_unit="m",
        )


def test_range_conversion_has_stable_values():
    assert convert_depth_range_to_target(10000.0, 10400.0, "cm", "m") == (100.0, 104.0)


def test_registration_merges_only_after_unit_conversion():
    candidate = SimpleNamespace(depth_normalization=None)
    existing = SimpleNamespace(depth_unit="m", top_depth=100.0, base_depth=200.0)
    incoming = SimpleNamespace(depth_unit="ft", start_depth=328.0839895, stop_depth=984.2519685)
    unit, top, base = _managed_depth_range(
        candidate=candidate,
        existing=existing,
        log_header=incoming,
        fallback_unit="ft",
    )
    assert unit == "m"
    assert top == 100.0
    assert base == 300.0
