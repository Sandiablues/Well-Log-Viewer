from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.services.source_intake_index_service import build_source_intake_indexed_preview_viewer_source
from app.services.source_intake_index_job_service import queue_source_intake_index_job


router = APIRouter(prefix="/api/source-intake", tags=["source-intake-index-preview"])


@router.post("/candidates/{candidate_id}/build-index")
def build_source_intake_candidate_index(candidate_id: str, mode: str = "3d") -> Dict[str, Any]:
    clean_mode = str(mode or "3d").strip().lower()
    if clean_mode != "3d":
        raise HTTPException(status_code=400, detail="Build Index is only available for 3D source-intake candidates.")
    try:
        return queue_source_intake_index_job(candidate_id, mode=clean_mode)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build indexed SEG-Y preview failed: {exc}")


@router.get("/candidates/{candidate_id}/indexed-preview-viewer-source")
def get_source_intake_indexed_preview_viewer_source(candidate_id: str, mode: str = "3d") -> Dict[str, Any]:
    try:
        return build_source_intake_indexed_preview_viewer_source(candidate_id, mode=mode)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build indexed preview viewer source failed: {exc}")
