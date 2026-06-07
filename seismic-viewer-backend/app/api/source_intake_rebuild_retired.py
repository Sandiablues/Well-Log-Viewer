from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/api/source-intake", tags=["source-intake-rebuild-retired"])


class SourceIntakeRebuildRequest(BaseModel):
    mode: str = "2d"


class SourceIntakeDiscardRebuildRequest(BaseModel):
    mode: str = "2d"
    job_id: Optional[str] = None


class SourceIntakeSaveAsNewRebuildRequest(BaseModel):
    mode: str = "2d"
    job_id: Optional[str] = None
    display_name: str


class SourceIntakeOverwriteRebuildRequest(BaseModel):
    mode: str = "2d"
    job_id: Optional[str] = None


@router.post("/candidates/{candidate_id}/rebuild")
def rebuild_source_intake_candidate(
    candidate_id: str,
    request: SourceIntakeRebuildRequest = SourceIntakeRebuildRequest(),
) -> Dict[str, Any]:
    raise HTTPException(status_code=410, detail="Rebuild workflow has been retired for this build.")


@router.post("/candidates/{candidate_id}/rebuild/discard")
def discard_source_intake_candidate_rebuild(
    candidate_id: str,
    request: SourceIntakeDiscardRebuildRequest = SourceIntakeDiscardRebuildRequest(),
) -> Dict[str, Any]:
    raise HTTPException(status_code=410, detail="Rebuild workflow has been retired for this build.")


@router.post("/candidates/{candidate_id}/rebuild/save-as-new")
def save_as_new_source_intake_candidate_rebuild(
    candidate_id: str,
    request: SourceIntakeSaveAsNewRebuildRequest,
) -> Dict[str, Any]:
    raise HTTPException(status_code=410, detail="Rebuild workflow has been retired for this build.")


@router.post("/candidates/{candidate_id}/rebuild/overwrite-existing")
def overwrite_existing_source_intake_candidate_rebuild(
    candidate_id: str,
    request: SourceIntakeOverwriteRebuildRequest = SourceIntakeOverwriteRebuildRequest(),
) -> Dict[str, Any]:
    raise HTTPException(status_code=410, detail="Rebuild workflow has been retired for this build.")
