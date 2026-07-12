from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.source_intake import dlis_parser
from app.source_intake.depth_units import requires_human_target_unit


class _Channel:
    def __init__(self, name: str, *, units: str | None = None):
        self.name = name
        self.units = units
        self.long_name = name
        self.dimension = []


class _Frame:
    name = "0"
    index = "DEPTH"

    def __init__(self, rows: list[tuple[float, float]]):
        self.channels = [
            _Channel("DEPTH", units="mm"),
            _Channel("GR", units="gAPI"),
        ]
        self._rows = rows

    def curves(self, strict=False):
        return np.array(self._rows, dtype=[("DEPTH", "f8"), ("GR", "f8")])


class _LogicalFile:
    def __init__(self, logical_file_id: str, rows: list[tuple[float, float]]):
        self.fileheader = SimpleNamespace(id=logical_file_id)
        self.origins = []
        self.frames = [_Frame(rows)]


@contextmanager
def _two_logical_files():
    yield [
        _LogicalFile(
            "Fil#1_alle_MWD.logdata",
            [(196500.0, 10.0), (196600.0, 11.0), (196700.0, 12.0)],
        ),
        _LogicalFile(
            "Run3.logdata",
            [(2538500.0, 20.0), (2538600.0, 21.0)],
        ),
    ]


def test_explicit_mm_is_authoritative_metric_and_does_not_require_human_target():
    assert requires_human_target_unit("mm") is False


def test_scaled_imperial_f10_policy_remains_human_target_selection():
    assert requires_human_target_unit("0.1 in") is True


def test_multilogical_duplicate_frame_and_channel_names_remain_scoped(
    monkeypatch, tmp_path: Path
):
    source = tmp_path / "multi-logical.dlis"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(
        dlis_parser,
        "dlis",
        SimpleNamespace(load=lambda _: _two_logical_files()),
    )

    result = dlis_parser.inspect_dlis(source)

    assert result.logical_file_count == 2
    assert result.frame_count == 2

    gamma = [item for item in result.scalar_channels if item.mnemonic == "GR"]
    assert len(gamma) == 2

    assert [item.source_curve_name for item in gamma] == [
        "Fil#1_alle_MWD.logdata|0|GR",
        "Run3.logdata|0|GR",
    ]
    assert [item.sample_count for item in gamma] == [3, 2]
    assert [item.depth_unit for item in gamma] == ["m", "m"]
    assert gamma[0].top_depth == pytest.approx(196.5)
    assert gamma[0].base_depth == pytest.approx(196.7)
    assert gamma[1].top_depth == pytest.approx(2538.5)
    assert gamma[1].base_depth == pytest.approx(2538.6)
    assert all(item.depth_normalization_status == "supported" for item in gamma)
    assert all(item.depth_normalization_reason is None for item in gamma)

    inventory_gamma = [
        item for item in result.channel_inventory if item.mnemonic == "GR"
    ]
    assert [(item.logical_file_id, item.frame_id) for item in inventory_gamma] == [
        ("Fil#1_alle_MWD.logdata", "0"),
        ("Run3.logdata", "0"),
    ]
    assert all(item.supported is True for item in inventory_gamma)
    assert not any("human must choose" in warning for warning in result.warnings)
