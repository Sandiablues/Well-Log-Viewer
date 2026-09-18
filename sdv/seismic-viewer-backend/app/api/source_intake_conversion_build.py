from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.services.managed_representation_request_service import ManagedRepresentationRequestService


router = APIRouter(prefix="/api/source-intake", tags=["source-intake-conversion-build"])

_managed_representation_request_service = ManagedRepresentationRequestService()


@router.post("/candidates/{candidate_id}/build-2d-line")
def build_source_intake_candidate_2d_line(candidate_id: str) -> Dict[str, Any]:
    try:
        return _managed_representation_request_service.build_2d_line(candidate_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build 2D managed representation failed: {exc}")


@router.post("/candidates/{candidate_id}/build-3d-volume")
def build_source_intake_candidate_3d_volume(candidate_id: str) -> Dict[str, Any]:
    try:
        return _managed_representation_request_service.build_3d_volume(candidate_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build 3D managed representation failed: {exc}")
