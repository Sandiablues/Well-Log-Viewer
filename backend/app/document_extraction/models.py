from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

ExtractionState = Literal["queued", "preparing", "converting", "normalizing", "completed", "failed"]

class ExtractionHealth(BaseModel):
    available: bool
    ready: bool
    provider: str = "docling"
    state: str
    detail: str | None = None

class ExtractionJobStatus(BaseModel):
    job_id: str
    document_id: str
    source_name: str
    state: ExtractionState
    stage: str
    elapsed_seconds: float = 0.0
    cached: bool = False
    page_count: int | None = None
    table_count: int | None = None
    error: str | None = None

class ParsedDocumentSummary(BaseModel):
    document_id: str
    source_name: str
    source_sha256: str
    provider: str
    provider_version: str | None = None
    page_count: int
    table_count: int
    cache_key: str
    cache_hit: bool
    output_path: str

class ExtractionSubmission(BaseModel):
    job_id: str
    document_id: str
    source_name: str
    state: ExtractionState
    cached: bool

class ParsedEvidence(BaseModel):
    page_number: int
    text: str
    bbox: dict[str, Any] | None = None
    table_id: str | None = None
    row: int | None = None
    column: int | None = None

class ParsedCell(BaseModel):
    row: int
    column: int
    text: str
    bbox: dict[str, Any] | None = None
    is_header: bool = False

class ParsedTable(BaseModel):
    table_id: str
    page_number: int | None = None
    caption: str | None = None
    cells: list[ParsedCell] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)

class ParsedPage(BaseModel):
    page_number: int
    text: str = ""
    headings: list[ParsedEvidence] = Field(default_factory=list)
    paragraphs: list[ParsedEvidence] = Field(default_factory=list)
    table_ids: list[str] = Field(default_factory=list)

class ParsedDocument(BaseModel):
    document_id: str
    source_name: str
    source_sha256: str
    provider: str
    provider_version: str | None = None
    page_count: int
    pages: list[ParsedPage] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    raw_document_path: str
    cache_key: str
