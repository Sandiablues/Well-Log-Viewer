from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.services.source_intake_geometry_qaqc_service import (
    get_geometry_qaqc as get_source_intake_geometry_qaqc_service,
    run_geometry_qaqc as run_source_intake_geometry_qaqc_service,
)


router = APIRouter(prefix="/api/source-intake", tags=["source-intake-geometry-qaqc"])


@router.get("/candidates/{candidate_id}/geometry-qaqc")
def get_source_intake_candidate_geometry_qaqc(candidate_id: str) -> Dict[str, Any]:
    try:
        return get_source_intake_geometry_qaqc_service(candidate_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Get Source Intake geometry QAQC failed: {exc}")


@router.post("/candidates/{candidate_id}/geometry-qaqc/run")
def run_source_intake_candidate_geometry_qaqc(candidate_id: str) -> Dict[str, Any]:
    try:
        return run_source_intake_geometry_qaqc_service(candidate_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Run Source Intake geometry QAQC failed: {exc}")
