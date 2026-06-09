"""System/runtime API routes for the WLV backend."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .runtime_status import RuntimeStatusService

router = APIRouter(prefix="/api/wlv/system", tags=["wlv-system"])
_status_service = RuntimeStatusService()


@router.get("/status", summary="WLV backend runtime and service status")
def get_system_status() -> dict[str, Any]:
    return _status_service.status()
