from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.inventory.canonical_curve_sample_service import CanonicalCurveSampleService


def _source(*, original_path=None, metadata=None):
    return SimpleNamespace(
        original_path=original_path,
        metadata=metadata or {},
    )


def test_source_record_original_path_has_precedence(tmp_path: Path) -> None:
    source_file = tmp_path / "source.dlis"
    source_file.write_bytes(b"dlis")
    stale = tmp_path / "stale.dlis"

    result = CanonicalCurveSampleService._source_path(
        source=_source(original_path=str(source_file)),
        product_provenance={"original_path": str(stale)},
    )

    assert result == source_file.resolve()


def test_source_metadata_storage_uri_is_supported(tmp_path: Path) -> None:
    source_file = tmp_path / "managed-original.dlis"
    source_file.write_bytes(b"dlis")

    result = CanonicalCurveSampleService._source_path(
        source=_source(metadata={"storage_uri": str(source_file)}),
        product_provenance={},
    )

    assert result == source_file.resolve()


def test_nested_dlis_asset_uri_is_supported(tmp_path: Path) -> None:
    source_file = tmp_path / "original.dlis"
    source_file.write_bytes(b"dlis")

    result = CanonicalCurveSampleService._source_path(
        source=_source(
            metadata={"dlis_asset": {"original_uri": str(source_file)}}
        ),
        product_provenance={},
    )

    assert result == source_file.resolve()


def test_product_provenance_remains_compatibility_fallback(tmp_path: Path) -> None:
    source_file = tmp_path / "legacy-source.las"
    source_file.write_text("~Version", encoding="utf-8")

    result = CanonicalCurveSampleService._source_path(
        source=_source(),
        product_provenance={"original_path": str(source_file)},
    )

    assert result == source_file.resolve()


def test_missing_paths_return_none(tmp_path: Path) -> None:
    result = CanonicalCurveSampleService._source_path(
        source=_source(
            original_path=str(tmp_path / "missing.dlis"),
            metadata={"storage_uri": str(tmp_path / "also-missing.dlis")},
        ),
        product_provenance={},
    )

    assert result is None
