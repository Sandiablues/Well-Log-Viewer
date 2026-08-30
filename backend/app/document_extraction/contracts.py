from __future__ import annotations
from pathlib import Path
from typing import Protocol
from .models import ParsedDocument

class DocumentExtractionProvider(Protocol):
    name: str
    def available(self) -> tuple[bool, str | None]: ...
    def parse_document(self, source_path: Path, output_dir: Path, document_id: str, source_sha256: str, cache_key: str) -> ParsedDocument: ...
