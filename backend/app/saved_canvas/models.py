"""Clean-sheet Saved Canvas contracts.

Saved Canvas is intentionally separate from WDV recovery, committed view state,
and the legacy single saved-workspace snapshot mechanism.  Identity belongs to
the multi-well WDV workspace, never to an active/selected track or active well.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.identity.wdv_contract_v2 import CanonicalUuid7, IsoDatetimeString, WdvCanonicalSession
from app.wdv_workspace.models import WdvSavedViewState as WdvCanonicalViewState
from app.wdv_session.view_contract import WdvCanonicalSessionView

SAVED_CANVAS_CONTRACT_VERSION = "wdv_saved_canvas_v1"
SAVED_CANVAS_STORE_CONTRACT_VERSION = "wdv_saved_canvas_store_v1"
SAVED_CANVAS_SCHEMA_VERSION = 1


class SavedCanvasSnapshot(BaseModel):
    """Complete durable canvas snapshot for the current WDV architecture."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str
    source_workspace_revision: int = Field(ge=0)
    source_session_revision: int = Field(ge=0)
    common_depth_unit: Literal["m", "ft"]
    required_managed_well_uids: tuple[CanonicalUuid7, ...] = ()
    session: WdvCanonicalSession
    view_state: WdvCanonicalViewState

    @field_validator("workspace_id")
    @classmethod
    def validate_workspace_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("workspace_id must not be blank")
        return normalized


class SavedCanvasRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["wdv_saved_canvas_v1"] = SAVED_CANVAS_CONTRACT_VERSION
    schema_version: Literal[1] = SAVED_CANVAS_SCHEMA_VERSION
    saved_canvas_uid: CanonicalUuid7
    workspace_id: str
    name: str
    created_at: IsoDatetimeString
    snapshot: SavedCanvasSnapshot

    @field_validator("workspace_id", "name")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Saved Canvas workspace/name must not be blank")
        return normalized


class SavedCanvasMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    saved_canvas_uid: CanonicalUuid7
    workspace_id: str
    name: str
    created_at: IsoDatetimeString
    schema_version: Literal[1] = SAVED_CANVAS_SCHEMA_VERSION
    is_active: bool = False


class SavedCanvasCreateRequest(BaseModel):
    """Create a new immutable Saved Canvas from the exact live action boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    expected_workspace_revision: int | None = Field(default=None, ge=0)
    view_state: WdvCanonicalViewState

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Saved Canvas name must not be blank")
        if len(normalized) > 160:
            raise ValueError("Saved Canvas name must be 160 characters or fewer")
        return normalized

class SavedCanvasUpdateRequest(BaseModel):
    """Replace one Saved Canvas with a complete current canvas snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_workspace_revision: int | None = Field(default=None, ge=0)
    view_state: WdvCanonicalViewState


class SavedCanvasRestoreRequest(BaseModel):
    """Request to atomically restore one immutable Saved Canvas.

    Restore is backend-authoritative. Client revision values are accepted only
    for backward compatibility and are deliberately ignored by the restore
    transaction. Active-well/workspace context and ordinary live-session writes
    must not make a historical Saved Canvas unloadable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_workspace_revision: int | None = Field(default=None, ge=0)
    expected_session_revision: int | None = Field(default=None, ge=0)


class SavedCanvasRestoreResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    saved_canvas_uid: CanonicalUuid7
    workspace_id: str
    name: str
    restored_at: IsoDatetimeString
    session: WdvCanonicalSessionView
    view_revision: int = Field(ge=0)
    view_state: WdvCanonicalViewState
