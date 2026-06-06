from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.external_registry_submitted_view_service import build_submitted_external_registry_view
from app.services.source_staging_service import (
    clear_staged_source_items,
    list_staged_source_items,
    stage_repository_selection,
    submit_staged_source_items,
    clear_submitted_handoff_items,
)


router = APIRouter()


class StageSelection(BaseModel):
    package_ids: list[str] = Field(default_factory=list)
    line_ids: list[str] = Field(default_factory=list)
    segy_file_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)


class ClearSubmittedHandoffRequest(BaseModel):
    mode: str = "2d"
    confirm: bool = False


class SubmitStagedItemsRequest(BaseModel):
    mode: str = "2d"


class StageRepositoryRequest(BaseModel):
    mode: str = "2d"
    selection: StageSelection = Field(default_factory=StageSelection)
    replace_existing: bool = False


@router.post("/repositories/{repository_id}/stage")
def api_stage_repository_selection(repository_id: str, request: StageRepositoryRequest) -> Dict[str, Any]:
    try:
        result = stage_repository_selection(
            repository_id=repository_id,
            mode=request.mode,
            selection=request.selection.model_dump(),
            replace_existing=request.replace_existing,
        )

        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result)

        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Stage repository selection failed: {exc}")


@router.get("/staged-source-items")
def api_list_staged_source_items(
    repository_id: Optional[str] = None,
    staged_for: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "staged_items": list_staged_source_items(
            repository_id=repository_id,
            staged_for=staged_for,
        )
    }


@router.delete("/repositories/{repository_id}/stage")
def api_clear_staged_source_items(
    repository_id: str,
    staged_for: Optional[str] = None,
) -> Dict[str, Any]:
    return clear_staged_source_items(
        repository_id=repository_id,
        staged_for=staged_for,
    )


@router.post("/repositories/{repository_id}/stage/submit")
def api_submit_staged_source_items(
    repository_id: str,
    request: SubmitStagedItemsRequest,
) -> Dict[str, Any]:
    try:
        return submit_staged_source_items(
            repository_id=repository_id,
            staged_for=request.mode,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Submit staged source items failed: {exc}")


@router.post("/repositories/{repository_id}/submitted-handoff/clear")
def api_clear_submitted_handoff(
    repository_id: str,
    request: ClearSubmittedHandoffRequest,
) -> Dict[str, Any]:
    try:
        return clear_submitted_handoff_items(
            repository_id=repository_id,
            staged_for=request.mode,
            confirm=request.confirm,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Clear submitted handoff failed: {exc}")


@router.get("/repositories/{repository_id}/external-registry/submitted-view")
def api_submitted_external_registry_view(
    repository_id: str,
    mode: str = "2d",
) -> Dict[str, Any]:
    try:
        return build_submitted_external_registry_view(
            repository_id=repository_id,
            mode=mode,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build submitted external registry view failed: {exc}")

