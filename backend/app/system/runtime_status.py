"""
Runtime status service for the MultiViewer Well Log Viewer backend.

This module is intentionally independent from route handlers so the same
status contract can be reused by HTTP routes, maintenance scripts, and future
container health checks.
"""

from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from typing import Any

from backend.app.wells.seed_repository import SeedWellRepository

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = "8010"


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


class RuntimeStatusService:
    """Builds non-destructive runtime and service status payloads."""

    def __init__(self, repository: SeedWellRepository | None = None) -> None:
        self._repository = repository or SeedWellRepository()

    def status(self) -> dict[str, Any]:
        wells = self._repository.list_wells()
        return {
            "ok": True,
            "service": "wlv-backend",
            "scope": "runtime_ops",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "runtime": {
                "environment": _env("WLV_BACKEND_ENV", "local"),
                "python_version": platform.python_version(),
                "process_id": os.getpid(),
            },
            "network": {
                "host": _env("WLV_BACKEND_HOST", DEFAULT_HOST),
                "port": int(_env("WLV_BACKEND_PORT", DEFAULT_PORT)),
            },
            "repository": {
                "type": "seed_repository",
                "well_count": len(wells),
                "well_ids": [well.well_id for well in wells],
            },
            "contracts": {
                "health": "/api/wlv/health",
                "system_status": "/api/wlv/system/status",
                "wells": "/api/wlv/wells",
                "well_detail": "/api/wlv/wells/{well_id}",
                "curves": "/api/wlv/wells/{well_id}/curves",
                "interval_columns": "/api/wlv/wells/{well_id}/interval-columns",
                "viewer_package": "/api/wlv/wells/{well_id}/viewer-package",
            },
            "maintenance": {
                "destructive_actions_enabled": False,
                "note": "Maintenance structure is present; destructive actions are intentionally not implemented in BE-002.",
            },
        }
