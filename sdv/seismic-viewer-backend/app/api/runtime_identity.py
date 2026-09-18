from __future__ import annotations

import hashlib
import inspect
import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter()


def _file_info(path_value: str | None) -> Dict[str, Any]:
    if not path_value:
        return {"path": None, "exists": False}

    path = Path(path_value).resolve()
    info: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
    }

    if path.exists() and path.is_file():
        data = path.read_bytes()
        info.update(
            {
                "size": len(data),
                "sha256_12": hashlib.sha256(data).hexdigest()[:12],
                "mtime": path.stat().st_mtime,
            }
        )

    return info


@router.get("/runtime/identity")
def runtime_identity() -> Dict[str, Any]:
    import main
    import app.api.endpoints as endpoints
    import app.reports.metadata_score_report as report

    loader_source = inspect.getsource(report._load_volume_payload)

    return {
        "status": "ok",
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "cwd": os.getcwd(),
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "main": _file_info(getattr(main, "__file__", None)),
        "endpoints": _file_info(getattr(endpoints, "__file__", None)),
        "metadata_score_report": _file_info(getattr(report, "__file__", None)),
        "report_loader_flags": {
            "uses_build_metadata_summary": "build_metadata_summary" in loader_source,
            "contains_missing_viewer_metadata": "missing_viewer_metadata" in loader_source,
            "contains_converted_volume_resolved": "converted_volume_resolved" in loader_source,
        },
    }


@router.get("/runtime/routes")
def runtime_routes() -> Dict[str, Any]:
    import main

    routes = []
    for route in main.app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/"):
            endpoint = getattr(route, "endpoint", None)
            routes.append(
                {
                    "path": path,
                    "methods": sorted(getattr(route, "methods", []) or []),
                    "endpoint_name": getattr(endpoint, "__name__", None),
                    "endpoint_module": getattr(endpoint, "__module__", None),
                }
            )

    return {
        "status": "ok",
        "pid": os.getpid(),
        "route_count": len(routes),
        "routes": routes,
    }
