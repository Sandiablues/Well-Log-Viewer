from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class WbvSavedCanvasCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    snapshot: dict[str, Any]

class WbvSavedCanvasUpdateRequest(BaseModel):
    snapshot: dict[str, Any]

class WbvSavedCanvasMetadata(BaseModel):
    saved_canvas_uid: str
    name: str
    created_at: str
    updated_at: str
    schema_version: int = 1
    active: bool = False
    is_active: bool = False

class WbvSavedCanvasRecord(WbvSavedCanvasMetadata):
    snapshot: dict[str, Any]


class WbvRecoveryStateRequest(BaseModel):
    state: dict[str, Any]


class WbvRecoveryStateRecord(BaseModel):
    schema_version: int = 1
    updated_at: str | None = None
    state: dict[str, Any] = Field(default_factory=dict)
