"""Read-only external DLIS source reference contract.

WLV never copies, moves, modifies, or deletes the source file. This adapter
fingerprints the external file and returns a reference to its authoritative
location. Parsed/indexed data is handled separately as disposable derived data.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DlisAssetStoreError(ValueError):
    pass


@dataclass(frozen=True)
class StoredDlisAsset:
    asset_id: str
    source_fingerprint: str
    original_uri: str
    byte_size: int
    created: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "source_fingerprint": self.source_fingerprint,
            "original_uri": self.original_uri,
            "byte_size": self.byte_size,
            "created": self.created,
            "storage_contract": "wlv_external_dlis_reference_v1",
            "source_ownership": "external",
            "access_mode": "read_only",
            "source_copied": False,
        }


class DlisAssetStore:
    """Compatibility adapter returning an external read-only DLIS reference."""

    def __init__(self, storage_root: Path | None = None) -> None:
        # Kept for call compatibility. Block 1 deliberately does not use it.
        self.storage_root = Path(storage_root) if storage_root is not None else None

    def preserve_path(
        self,
        source_path: Path,
        *,
        source_id: str,
        filename: str | None = None,
    ) -> StoredDlisAsset:
        path = Path(source_path).expanduser().resolve()
        if not path.is_file():
            raise DlisAssetStoreError(f"DLIS source file is unavailable: {path}")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise DlisAssetStoreError(f"Could not read DLIS source file: {path}") from exc
        fingerprint = hashlib.sha256(payload).hexdigest()
        return StoredDlisAsset(
            asset_id=f"dlis-asset:sha256:{fingerprint}",
            source_fingerprint=fingerprint,
            original_uri=str(path),
            byte_size=len(payload),
            created=False,
        )
