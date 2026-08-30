"""Read-only external LIS/LTI source reference contract."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

class LisAssetStoreError(ValueError): pass

@dataclass(frozen=True)
class StoredLisAsset:
    asset_id: str
    source_fingerprint: str
    original_uri: str
    byte_size: int
    created: bool
    def as_dict(self) -> dict[str, Any]:
        return {"asset_id":self.asset_id,"source_fingerprint":self.source_fingerprint,
                "original_uri":self.original_uri,"byte_size":self.byte_size,"created":self.created,
                "storage_contract":"wlv_external_lis_reference_v1","source_ownership":"external",
                "access_mode":"read_only","source_copied":False}

class LisAssetStore:
    def preserve_path(self, source_path: Path, *, source_id: str, filename: str|None=None) -> StoredLisAsset:
        path=Path(source_path).expanduser().resolve()
        if not path.is_file(): raise LisAssetStoreError(f"LIS/LTI source file is unavailable: {path}")
        try: payload=path.read_bytes()
        except OSError as exc: raise LisAssetStoreError(f"Could not read LIS/LTI source file: {path}") from exc
        fingerprint=hashlib.sha256(payload).hexdigest()
        return StoredLisAsset(asset_id=f"lis-asset:sha256:{fingerprint}",source_fingerprint=fingerprint,
                              original_uri=str(path),byte_size=len(payload),created=False)
