from __future__ import annotations
import hashlib
import shutil
from pathlib import Path
from .models import ParsedDocument

NORMALIZATION_CONTRACT_VERSION = "wme-parsed-document-1.3-schema-resolver"

class ExtractionCache:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
    @staticmethod
    def sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    @staticmethod
    def cache_key(source_sha256: str, provider_version: str) -> str:
        payload = f"{source_sha256}|docling|{provider_version}|{NORMALIZATION_CONTRACT_VERSION}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    def entry_dir(self, cache_key: str) -> Path:
        return self.root / cache_key
    def parsed_path(self, cache_key: str) -> Path:
        return self.entry_dir(cache_key) / "parsed_document.json"
    def load(self, cache_key: str) -> ParsedDocument | None:
        path = self.parsed_path(cache_key)
        if not path.is_file(): return None
        return ParsedDocument.model_validate_json(path.read_text(encoding="utf-8"))
    def save(self, document: ParsedDocument) -> Path:
        path = self.parsed_path(document.cache_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(document.model_dump_json(indent=2), encoding="utf-8")
        return path
    def clear(self) -> None:
        if self.root.exists(): shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
