from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.source_intake import dlis_parser
from app.source_intake.models import SourceIntakeParsedMetadata


class _Channel:
    def __init__(self, name, *, units=None, long_name=None, dimension=None):
        self.name = name
        self.units = units
        self.long_name = long_name
        self.dimension = dimension or []


class _Frame:
    name = "FRAME-A"
    index = "DEPTH"

    def __init__(self):
        self.channels = [
            _Channel("DEPTH", units="m", long_name="Measured Depth"),
            _Channel("GR", units="gAPI", long_name="Gamma Ray"),
            _Channel("IMG", units=None, long_name="Borehole Image", dimension=[4, 4]),
        ]

    def curves(self, strict=False):
        return np.array(
            [(100.0, 10.0, np.ones((4, 4))), (101.0, 11.0, np.ones((4, 4)))],
            dtype=[("DEPTH", "f8"), ("GR", "f8"), ("IMG", "f8", (4, 4))],
        )


class _LogicalFile:
    fileheader = SimpleNamespace(id="LF-1")
    origins = [SimpleNamespace(
        well_name="TEST-1", well_id="UWI-1", company="Operator",
        field_name="Field", producer_name="Service",
    )]
    frames = [_Frame()]


@contextmanager
def _physical_file():
    yield [_LogicalFile()]


def test_dlis_inventory_preserves_all_channels_and_keeps_scalar_ingestible(monkeypatch, tmp_path):
    source = tmp_path / "sample.dlis"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(dlis_parser, "dlis", SimpleNamespace(load=lambda _: _physical_file()))

    result = dlis_parser.inspect_dlis(source)

    assert result.logical_file_count == 1
    assert result.frame_count == 1
    assert [item.mnemonic for item in result.channel_inventory] == ["DEPTH", "GR", "IMG"]
    assert [item.mnemonic for item in result.scalar_channels] == ["GR"]

    depth, gamma, image = result.channel_inventory
    assert depth.role == "index" and depth.supported is True
    assert gamma.index_channel == "DEPTH" and gamma.sample_count == 2
    assert gamma.dimensions == () and gamma.supported is True
    assert image.dimensions == (4, 4)
    assert image.supported is False
    assert image.unsupported_reason == "multidimensional_channel"
    assert result.non_scalar_channel_count == 1
    assert any("scalar channels remain ingestible" in message for message in result.warnings)


def test_dlis_metadata_contract_is_backward_compatible_and_serializable():
    legacy = SourceIntakeParsedMetadata(parser_id="legacy", source_format="LAS")
    assert legacy.logical_file_count == 0
    assert legacy.frame_count == 0
    assert legacy.dlis_channels == []

    payload = SourceIntakeParsedMetadata(
        parser_id="dlis_frame_channel_adapter_v1",
        source_format="DLIS",
        logical_file_count=1,
        frame_count=1,
        dlis_channels=[{
            "logical_file_id": "LF-1",
            "frame_id": "FRAME-A",
            "mnemonic": "IMG",
            "dimensions": [4, 4],
            "index_channel": "DEPTH",
            "sample_count": 2,
            "role": "curve",
            "supported": False,
            "unsupported_reason": "multidimensional_channel",
        }],
    ).model_dump(mode="json")
    assert payload["dlis_channels"][0]["dimensions"] == [4, 4]
    assert payload["dlis_channels"][0]["supported"] is False


def test_dlis_registration_provenance_uses_backend_channel_contract():
    from app.source_intake.models import SourceIntakeCurveHeader
    from app.source_intake.registration import _dlis_curve_provenance

    parsed = SourceIntakeParsedMetadata(
        parser_id="dlis_frame_channel_adapter_v1",
        source_format="DLIS",
        dlis_channels=[{
            "logical_file_id": "LF-1",
            "frame_id": "FRAME-A",
            "mnemonic": "GR",
            "unit": "gAPI",
            "dimensions": [],
            "index_channel": "DEPTH",
            "sample_count": 200,
            "role": "curve",
            "supported": True,
        }],
    )
    curve = SourceIntakeCurveHeader(
        mnemonic="GR",
        source_curve_name="LF-1|FRAME-A|GR",
    )
    assert _dlis_curve_provenance(curve, parsed) == {
        "dlis_logical_file_id": "LF-1",
        "dlis_frame_id": "FRAME-A",
        "dlis_channel_mnemonic": "GR",
        "dlis_channel_dimensions": [],
        "dlis_index_channel": "DEPTH",
        "dlis_channel_sample_count": 200,
        "dlis_channel_supported": True,
    }
