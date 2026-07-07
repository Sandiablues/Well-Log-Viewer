"""Read-only external LAS reference plus disposable parsed representation.

The authoritative LAS source remains at its external path. WLV fingerprints and
parses it read-only, then stores only derived manifest/sample cache data.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.wells.las_import_service import LasImportResult, LasImportService
from app.wells.models import MsiSourceRef


class LasAssetStoreError(ValueError):
    """Raised when a LAS asset cannot be preserved safely."""


@dataclass(frozen=True)
class StoredLasAsset:
    asset_id: str
    source_fingerprint: str
    original_uri: str
    manifest_uri: str
    samples_uri: str
    byte_size: int
    curve_count: int
    sample_count: int
    created: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "source_fingerprint": self.source_fingerprint,
            "original_uri": self.original_uri,
            "manifest_uri": self.manifest_uri,
            "samples_uri": self.samples_uri,
            "byte_size": self.byte_size,
            "curve_count": self.curve_count,
            "sample_count": self.sample_count,
            "created": self.created,
        }


class LasAssetStore:
    """External LAS reference with content-addressed derived cache."""

    def __init__(self, storage_root: Path | None = None, parser: LasImportService | None = None) -> None:
        if storage_root is None:
            backend_root = Path(__file__).resolve().parents[2]
            storage_root = backend_root / "data" / "las_assets"
        self.storage_root = Path(storage_root)
        self.parser = parser or LasImportService()

    def preserve_path(self, source_path: Path, *, source_id: str, filename: str | None = None) -> StoredLasAsset:
        path = Path(source_path).expanduser().resolve()
        if not path.is_file():
            raise LasAssetStoreError(f"LAS source file is unavailable: {path}")
        try:
            source_bytes = path.read_bytes()
        except OSError as exc:
            raise LasAssetStoreError(f"Could not read LAS source file: {path}") from exc
        result = self.parser.import_from_bytes(
            source_bytes,
            MsiSourceRef(source_id=source_id, filename=filename or path.name),
        )
        return self.preserve_result(
            result, filename=filename or path.name, source_uri=str(path)
        )

    def preserve_result(
        self, result: LasImportResult, *, filename: str, source_uri: str | None = None
    ) -> StoredLasAsset:
        fingerprint = hashlib.sha256(result.source_bytes).hexdigest()
        if fingerprint != result.source_fingerprint:
            raise LasAssetStoreError("LAS parser fingerprint does not match original source bytes.")
        asset_id = f"las-asset:sha256:{fingerprint}"
        asset_dir = self.storage_root / fingerprint[:2] / fingerprint
        external_uri = str(Path(source_uri).expanduser().resolve()) if source_uri else ""
        manifest_path = asset_dir / "manifest.json"
        samples_path = asset_dir / "samples.json.gz"
        created = not manifest_path.exists()
        asset_dir.mkdir(parents=True, exist_ok=True)

        manifest = result.as_dict(include_samples=False)
        manifest.update({
            "asset_id": asset_id,
            "original_filename": filename,
            "original_uri": external_uri,
            "samples_uri": str(samples_path),
            "byte_size": len(result.source_bytes),
            "storage_contract": "wlv_external_las_reference_v1",
            "source_ownership": "external",
            "access_mode": "read_only",
            "source_copied": False,
        })
        samples = {
            "storage_contract": "wlv_las_samples_v1",
            "asset_id": asset_id,
            "source_fingerprint": fingerprint,
            "depth_mnemonic": result.depth_mnemonic,
            "depth_unit": result.depth_unit,
            "depth_values": result.depth_values,
            "curves": [curve.as_dict() for curve in result.curves],
        }
        self._atomic_write_json(manifest_path, manifest)
        self._atomic_write_gzip_json(samples_path, samples)

        return StoredLasAsset(
            asset_id=asset_id,
            source_fingerprint=fingerprint,
            original_uri=external_uri,
            manifest_uri=str(manifest_path),
            samples_uri=str(samples_path),
            byte_size=len(result.source_bytes),
            curve_count=result.curve_count,
            sample_count=result.sample_count,
            created=created,
        )

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
        os.replace(temp, path)

    @staticmethod
    def _atomic_write_gzip_json(path: Path, payload: dict[str, Any]) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        with gzip.open(temp, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"), allow_nan=False)
        os.replace(temp, path)
