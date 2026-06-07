from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.source_intake_session_service import SourceIntakeSessionService
from app.services.source_intake_stage_workbench_service import SourceIntakeStageWorkbenchService
from app.services.source_intake_workbench_v2_service import SourceIntakeWorkbenchV2Service


router = APIRouter(prefix="/api/source-intake", tags=["source-intake-workbench"])


_source_intake_workbench_v2_service = SourceIntakeWorkbenchV2Service()
_source_intake_stage_workbench_service = SourceIntakeStageWorkbenchService(_source_intake_workbench_v2_service)
_source_intake_session_service = SourceIntakeSessionService(
    _source_intake_workbench_v2_service,
    _source_intake_stage_workbench_service,
)


class SourceIntakeStageWorkbenchRequest(BaseModel):
    mode: str
    include_subfolders: Optional[bool] = None


class SourceIntakeWorkbenchV2UseRepositoryRequest(BaseModel):
    repository_id: str
    mode: str
    include_subfolders: Optional[bool] = None


class SourceIntakeWorkbenchV2ClearSelectedRequest(BaseModel):
    candidate_ids: List[str] = Field(default_factory=list)
    repository_id: Optional[str] = None
    mode: str


@router.get("/session")
def get_source_intake_session(mode: str) -> Dict[str, object]:
    try:
        return _source_intake_session_service.get_session(mode=mode)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build Source Intake session failed: {exc}")


@router.post("/repositories/{repository_id}/stage-workbench")
def stage_source_intake_repository_workbench(
    repository_id: str,
    request: SourceIntakeStageWorkbenchRequest,
) -> Dict[str, object]:
    try:
        return _source_intake_session_service.stage_repository_workbench(
            repository_id=repository_id,
            mode=request.mode,
            include_subfolders=request.include_subfolders,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Stage Source Intake repository to workbench failed: {exc}")


@router.get("/workbench")
def get_source_intake_workbench(
    repository_id: str,
    mode: str,
    include_subfolders: Optional[bool] = None,
) -> Dict[str, object]:
    try:
        payload = _source_intake_workbench_v2_service.get_workbench(
            mode=mode,
            repository_id=repository_id,
        )
        payload["public_contract"] = "source_intake.workbench"
        return payload
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build Source Intake Workbench failed: {exc}")


@router.post("/workbench/use-repository")
def use_repository_in_source_intake_workbench(request: SourceIntakeWorkbenchV2UseRepositoryRequest) -> Dict[str, object]:
    try:
        payload = _source_intake_workbench_v2_service.use_repository(
            repository_id=request.repository_id,
            mode=request.mode,
        )
        payload["public_contract"] = "source_intake.workbench"
        return payload
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Use repository in Source Intake Workbench failed: {exc}")


@router.post("/workbench/clear-selected")
def clear_selected_source_intake_workbench(request: SourceIntakeWorkbenchV2ClearSelectedRequest) -> Dict[str, object]:
    try:
        payload = _source_intake_workbench_v2_service.clear_selected(
            candidate_ids=request.candidate_ids,
            repository_id=request.repository_id,
            mode=request.mode,
        )
        payload["public_contract"] = "source_intake.workbench"
        return payload
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Clear selected Source Intake Workbench rows failed: {exc}")


@router.get("/workbench-v2")
def get_source_intake_workbench_v2(
    repository_id: str,
    mode: str,
    include_subfolders: Optional[bool] = None,
) -> Dict[str, object]:
    try:
        return _source_intake_workbench_v2_service.get_workbench(
            mode=mode,
            repository_id=repository_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build Source Intake Workbench V2 failed: {exc}")


@router.post("/workbench-v2/use-repository")
def use_repository_in_source_intake_workbench_v2(request: SourceIntakeWorkbenchV2UseRepositoryRequest) -> Dict[str, object]:
    try:
        return _source_intake_workbench_v2_service.use_repository(
            repository_id=request.repository_id,
            mode=request.mode,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Use repository in Source Intake Workbench V2 failed: {exc}")


@router.post("/workbench-v2/clear-selected")
def clear_selected_source_intake_workbench_v2(request: SourceIntakeWorkbenchV2ClearSelectedRequest) -> Dict[str, object]:
    try:
        return _source_intake_workbench_v2_service.clear_selected(
            candidate_ids=request.candidate_ids,
            repository_id=request.repository_id,
            mode=request.mode,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Clear selected Source Intake Workbench V2 rows failed: {exc}")
