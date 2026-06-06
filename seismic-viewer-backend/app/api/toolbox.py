from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/toolbox", tags=["toolbox"])


def _project_root() -> Path:
    # app/api/toolbox.py -> app/api -> app -> seismic-viewer-backend -> project
    return Path(__file__).resolve().parents[3]


def _segysak_executable() -> Path:
    return _project_root() / "third_party" / "segysak_sandbox" / "venv" / "bin" / "segysak"


def _segysak_repo() -> Path:
    return _project_root() / "third_party" / "segysak_sandbox" / "segysak"


class SegySakScanRequest(BaseModel):
    path: str = Field(..., min_length=1)
    max_traces: int | None = Field(default=20000, ge=1, le=500000)
    timeout_seconds: int = Field(default=120, ge=5, le=1800)


def _segysak_base_payload() -> dict[str, Any]:
    exe = _segysak_executable()
    repo = _segysak_repo()
    return {
        "tool": "SEGY-SAK",
        "installed": exe.exists() and exe.is_file(),
        "executable": exe.exists() and exe.is_file(),
        "path": str(exe),
        "repo_path": str(repo),
        "repo_exists": repo.exists(),
        "license_note": (
            "SEGY-SAK is staged as an isolated GPL-3.0 sandbox tool and is "
            "not imported into the main backend runtime."
        ),
        "integration_mode": "isolated_subprocess_sandbox",
        "commands": ["scan", "ebcidc", "scrape", "print", "sgy", "convert"],
    }


@router.get("/segysak/status")
def segysak_status():
    exe = _segysak_executable()
    payload = _segysak_base_payload()

    if not payload["executable"]:
        payload.update({
            "ok": False,
            "version": None,
            "help_available": False,
            "message": "SEGY-SAK executable was not found in the isolated sandbox.",
        })
        return payload

    try:
        version = subprocess.run(
            [str(exe), "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        help_result = subprocess.run(
            [str(exe), "--help"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

        version_text = (version.stdout or version.stderr or "").strip()
        help_text = (help_result.stdout or help_result.stderr or "").strip()

        payload.update({
            "ok": version.returncode == 0 or help_result.returncode == 0,
            "version": version_text or "available",
            "help_available": help_result.returncode == 0,
            "help_excerpt": "\n".join(help_text.splitlines()[:18]),
            "message": (
                "SEGY-SAK sandbox is available."
                if (version.returncode == 0 or help_result.returncode == 0)
                else "SEGY-SAK executable exists but did not respond cleanly."
            ),
        })
    except Exception as exc:
        payload.update({
            "ok": False,
            "version": None,
            "help_available": False,
            "message": f"SEGY-SAK status check failed: {exc}",
        })

    return payload


@router.post("/segysak/scan")
def segysak_scan(request: SegySakScanRequest):
    """
    Run SEGY-SAK scan as a read-only isolated subprocess.

    This endpoint does not mutate Source Intake, Managed Data, MSI, or any
    loaded dataset state. It is a Toolbox diagnostic runner only.
    """
    exe = _segysak_executable()
    if not exe.exists() or not exe.is_file():
        raise HTTPException(
            status_code=503,
            detail="SEGY-SAK executable was not found in the isolated sandbox.",
        )

    segy_path = Path(request.path).expanduser()
    if not segy_path.exists() or not segy_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"SEG-Y file not found: {segy_path}",
        )

    if segy_path.suffix.lower() not in {".sgy", ".segy"}:
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a .sgy or .segy file: {segy_path}",
        )

    cmd = [str(exe), "--file", str(segy_path), "scan"]
    if request.max_traces:
        cmd.extend(["--max-traces", str(request.max_traces)])

    started = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=request.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        return {
            "ok": False,
            "timed_out": True,
            "return_code": None,
            "elapsed_seconds": round(elapsed, 3),
            "command": cmd,
            "path": str(segy_path),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or f"SEGY-SAK scan timed out after {request.timeout_seconds} seconds.",
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"SEGY-SAK scan failed to start: {exc}",
        )

    elapsed = time.monotonic() - started
    return {
        "ok": result.returncode == 0,
        "timed_out": False,
        "return_code": result.returncode,
        "elapsed_seconds": round(elapsed, 3),
        "command": cmd,
        "path": str(segy_path),
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
    }
