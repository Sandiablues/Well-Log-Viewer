from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.services.source_segy_representation_service import (
    build_source_segy_representations_by_id,
)


RUNNING_STATES = {
    "queued",
    "running",
    "converting",
    "reading_index",
    "reading index",
    "validating_zarr",
    "validating zarr",
    "promoting_output",
    "promoting output",
}

FAILED_STATES = {"failed", "error"}


def _safe_status(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", " ")


def _representation_state(
    rep: Dict[str, Any],
    *,
    kind: str,
) -> Dict[str, Any]:
    raw_status = _safe_status(rep.get("status") or rep.get("artifact_status"))
    available = bool(rep.get("available"))
    action_available = bool(rep.get("action_available"))

    if available:
        state = "exists"
        status_label = "Exists"
    elif raw_status in FAILED_STATES:
        state = "failed"
        status_label = "Failed"
    elif raw_status in RUNNING_STATES:
        state = "running"
        status_label = "In progress"
    elif raw_status == "reconvert required":
        state = "missing"
        status_label = "Missing"
    elif kind == "managed_zarr":
        state = "not_converted"
        status_label = "Not converted"
    else:
        state = "not_created"
        status_label = "Not created"

    return {
        "state": state,
        "status_label": status_label,
        "action_enabled": action_available,
        "raw_status": raw_status or None,
    }




def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _jobs_dir() -> Path:
    return _backend_root() / "data" / "jobs"


def _load_job(job_id: Any) -> Dict[str, Any] | None:
    if not job_id:
        return None

    path = _jobs_dir() / f"{job_id}.json"
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def _job_is_active(job: Dict[str, Any]) -> bool:
    status = _safe_status(job.get("status"))
    return bool(status and status not in {"complete", "completed", "available", "failed", "error", "cancelled"})


def _active_job_from_representations(reps: Dict[str, Any]) -> Dict[str, Any] | None:
    candidates = [
        ("create_managed_zarr", "Creating managed Zarr", reps.get("zarr_full_conversion") or {}),
        ("build_fast_zarr_cache", "Building fast Zarr cache", reps.get("optimized_cache") or {}),
        ("index_preview", "Creating index / preview", reps.get("indexed_preview") or {}),
    ]

    for action, label, rep in candidates:
        job = _load_job(rep.get("job_id"))
        if not job or not _job_is_active(job):
            continue

        progress = job.get("progress")
        try:
            progress_value = max(0, min(100, int(float(progress))))
        except Exception:
            progress_value = None

        return {
            "job_id": job.get("job_id"),
            "action": action,
            "label": label,
            "status": job.get("status"),
            "progress": progress_value,
            "message": job.get("message") or label,
        }

    return None


def _monitor(representations: List[Dict[str, Any]]) -> Dict[str, str]:
    by_key = {item["key"]: item for item in representations}

    index_state = by_key.get("index_preview", {}).get("state")
    cache_state = by_key.get("fast_zarr_cache", {}).get("state")
    managed_state = by_key.get("managed_zarr", {}).get("state")

    if any(item.get("state") == "failed" for item in representations):
        return {
            "state": "failed",
            "label": "Action failed",
            "message": "One representation failed. Refresh or retry the relevant action.",
        }

    if index_state == "running":
        return {
            "state": "running",
            "label": "Creating index",
            "message": "Index / preview creation is running.",
        }

    if cache_state == "running":
        return {
            "state": "running",
            "label": "Building fast Zarr cache",
            "message": "Fast Zarr cache creation is running.",
        }

    if managed_state == "running":
        return {
            "state": "running",
            "label": "Creating managed Zarr",
            "message": "Managed Zarr conversion is running.",
        }

    if managed_state == "missing":
        return {
            "state": "warning",
            "label": "Managed Zarr missing",
            "message": "The managed Zarr artifact was deleted and can be recreated.",
        }

    if index_state == "exists" and cache_state == "exists" and managed_state == "exists":
        return {
            "state": "complete",
            "label": "All representations available",
            "message": "Index / preview, fast Zarr cache, and managed Zarr all exist.",
        }

    if index_state == "exists" and cache_state == "exists":
        return {
            "state": "ready",
            "label": "Fast Zarr cache available",
            "message": "Index / preview and fast Zarr cache exist. Managed Zarr can still be created if needed.",
        }

    if index_state == "exists":
        return {
            "state": "ready",
            "label": "Index available",
            "message": "Index / preview exists. Fast Zarr cache or managed Zarr can be created.",
        }

    return {
        "state": "ready",
        "label": "Ready",
        "message": "Create an index / preview, build a fast Zarr cache, or create managed Zarr.",
    }


def build_source_segy_edr_command_state(
    segy_file_id: str,
    mode: str = "3d",
) -> Dict[str, Any]:
    """
    Build the simplified command-state contract for the 3D EDR UI.

    This is intentionally display-focused:
    - no raw volume IDs
    - no job IDs
    - no Zarr paths
    - no classification diagnostics
    - no stale source conversion status as primary UI state

    The detailed representation endpoint remains available for diagnostics.
    """
    payload = build_source_segy_representations_by_id(segy_file_id, mode=mode)

    source = payload.get("source") or {}
    reps = payload.get("representations") or {}

    index = _representation_state(reps.get("indexed_preview") or {}, kind="index_preview")
    cache = _representation_state(reps.get("optimized_cache") or {}, kind="fast_zarr_cache")
    managed = _representation_state(reps.get("zarr_full_conversion") or {}, kind="managed_zarr")

    representations: List[Dict[str, Any]] = [
        {
            "key": "index_preview",
            "label": "Index / Preview",
            "status_label": index["status_label"],
            "state": index["state"],
            "action_label": "Create Index / Preview",
            "action_enabled": index["action_enabled"],
            "action": "index_preview",
        },
        {
            "key": "fast_zarr_cache",
            "label": "Fast Zarr Cache",
            "status_label": cache["status_label"],
            "state": cache["state"],
            "action_label": "Build Fast Zarr Cache",
            "action_enabled": cache["action_enabled"],
            "action": "build_fast_zarr_cache",
        },
        {
            "key": "managed_zarr",
            "label": "Managed Zarr",
            "status_label": managed["status_label"],
            "state": managed["state"],
            "action_label": "Create Managed Zarr",
            "action_enabled": managed["action_enabled"],
            "action": "create_managed_zarr",
        },
    ]

    active_job = _active_job_from_representations(reps)

    return {
        "status": "ok",
        "mode": mode,
        "source": {
            "segy_file_id": source.get("source_segy_file_id") or segy_file_id,
            "filename": source.get("filename"),
            "source_path_exists": bool(source.get("source_path_exists")),
            "candidate_kind": source.get("candidate_kind"),
            "candidate_role": source.get("candidate_role"),
        },
        "representations": representations,
        "monitor": _monitor(representations),
        "active_job": active_job,
    }
