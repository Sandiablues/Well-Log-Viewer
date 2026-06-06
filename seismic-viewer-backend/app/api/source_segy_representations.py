from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.services.source_segy_edr_command_state_service import build_source_segy_edr_command_state
from app.services.source_segy_representation_service import (
    build_source_segy_representations_by_id,
    index_source_segy_preview_by_id,
)

router = APIRouter(prefix="/api/segy-files", tags=["source-segy-representations"])


@router.get("/{segy_file_id}/representations")
def get_source_segy_representations(segy_file_id: str, mode: str = "3d") -> Dict[str, Any]:
    try:
        return build_source_segy_representations_by_id(segy_file_id, mode=mode)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



@router.get("/{segy_file_id}/edr-command-state")
def get_source_segy_edr_command_state(segy_file_id: str, mode: str = "3d") -> Dict[str, Any]:
    try:
        return build_source_segy_edr_command_state(segy_file_id, mode=mode)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{segy_file_id}/index")
def index_source_segy_preview(segy_file_id: str, mode: str = "3d") -> Dict[str, Any]:
    try:
        return index_source_segy_preview_by_id(segy_file_id, mode=mode)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

