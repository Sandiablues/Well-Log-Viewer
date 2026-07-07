from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.inventory import dlis_sample_reader
from app.inventory.curve_sample_service import _read_las_curve_samples
from app.inventory.dlis_sample_reader import read_dlis_curve_samples


class _Channel:
    def __init__(self, name: str, *, units: str | None = None):
        self.name = name
        self.units = units
        self.dimension = []
        self.null = None


class _Frame:
    name = "FRAME-A"
    index = "DEPTH"
    channels = [_Channel("DEPTH", units="m"), _Channel("GR", units="gAPI")]

    def curves(self, strict=False):
        return np.array(
            [(779.0, 10.0), (3722.0, 20.0)],
            dtype=[("DEPTH", "f8"), ("GR", "f8")],
        )


class _LogicalFile:
    fileheader = SimpleNamespace(id="LF-1")
    frames = [_Frame()]


@contextmanager
def _physical_file():
    yield [_LogicalFile()]


def _write_las(path: Path) -> None:
    path.write_text(
        """~Version\nVERS. 2.0\n~Well\nSTRT.FT 300.5\nSTOP.FT 6076\nNULL. -999.25\n~Curve\nDEPT.FT : Depth\nGR.GAPI : Gamma Ray\n~ASCII\n300.5 10\n6076 20\n""",
        encoding="utf-8",
    )


def test_las_feet_to_metres_and_native_feet(tmp_path: Path) -> None:
    source = tmp_path / "f21-31.las"
    _write_las(source)

    metres = _read_las_curve_samples(source, "GR", 100, target_depth_unit="m")
    feet = _read_las_curve_samples(source, "GR", 100, target_depth_unit="ft")

    assert metres["depth_unit"] == "m"
    assert metres["depth_min"] == pytest.approx(91.5924)
    assert metres["depth_max"] == pytest.approx(1851.9648)
    assert metres["samples"][0] == pytest.approx([91.5924, 10.0])
    assert metres["samples"][1] == pytest.approx([1851.9648, 20.0])

    assert feet["depth_unit"] == "ft"
    assert feet["depth_min"] == pytest.approx(300.5)
    assert feet["depth_max"] == pytest.approx(6076.0)


def test_dlis_metres_to_feet_and_native_metres(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        dlis_sample_reader,
        "dlis",
        SimpleNamespace(load=lambda _: _physical_file()),
    )
    source = tmp_path / "f5.dlis"
    source.write_bytes(b"fixture")

    feet = read_dlis_curve_samples(
        source_path=source,
        curve_mnemonic="GR",
        max_samples=100,
        logical_file_id="LF-1",
        frame_id="FRAME-A",
        target_depth_unit="ft",
    )
    metres = read_dlis_curve_samples(
        source_path=source,
        curve_mnemonic="GR",
        max_samples=100,
        logical_file_id="LF-1",
        frame_id="FRAME-A",
        target_depth_unit="m",
    )

    assert feet["depth_unit"] == "ft"
    assert feet["depth_min"] == pytest.approx(2555.77427822)
    assert feet["depth_max"] == pytest.approx(12211.28608924)

    assert metres["depth_unit"] == "m"
    assert metres["depth_min"] == pytest.approx(779.0)
    assert metres["depth_max"] == pytest.approx(3722.0)


def test_mixed_las_dlis_union_is_derived_after_conversion(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        dlis_sample_reader,
        "dlis",
        SimpleNamespace(load=lambda _: _physical_file()),
    )
    las = tmp_path / "f21-31.las"
    dlis = tmp_path / "f5.dlis"
    _write_las(las)
    dlis.write_bytes(b"fixture")

    las_m = _read_las_curve_samples(las, "GR", 100, target_depth_unit="m")
    dlis_m = read_dlis_curve_samples(
        source_path=dlis,
        curve_mnemonic="GR",
        max_samples=100,
        target_depth_unit="m",
    )
    assert min(las_m["depth_min"], dlis_m["depth_min"]) == pytest.approx(91.5924)
    assert max(las_m["depth_max"], dlis_m["depth_max"]) == pytest.approx(3722.0)

    las_ft = _read_las_curve_samples(las, "GR", 100, target_depth_unit="ft")
    dlis_ft = read_dlis_curve_samples(
        source_path=dlis,
        curve_mnemonic="GR",
        max_samples=100,
        target_depth_unit="ft",
    )
    assert min(las_ft["depth_min"], dlis_ft["depth_min"]) == pytest.approx(300.5)
    assert max(las_ft["depth_max"], dlis_ft["depth_max"]) == pytest.approx(12211.28608924)
