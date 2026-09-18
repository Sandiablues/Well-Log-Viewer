from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.source_registry_admin_service import clear_source_registry


router = APIRouter()


class ClearSourceRegistryRequest(BaseModel):
    confirm: bool = False


@router.post("/source-registry/clear")
def api_clear_source_registry(request: ClearSourceRegistryRequest) -> Dict[str, Any]:
    try:
        return clear_source_registry(confirm=request.confirm)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Clear source registry failed: {exc}")
