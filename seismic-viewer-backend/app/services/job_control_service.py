from __future__ import annotations

# JOB_CONTROL_1_SERVICE

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"

ACTIVE_STATUSES = {
    "queued",
    "saving_upload",
    "reading_metadata",
    "validating_geometry",
    "converting",
    "writing_zarr",
    "validating_zarr",
    "promoting_output",
    "registering_volume",
    "running",
    "processing",
    "indexing",
    "rebuilding",
}

TERMINAL_STATUSES = {
    "completed",
    "complete",
    "converted",
    "ready",
    "failed",
    "error",
    "cancelled",
    "canceled",
    "force_stopped",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


def safe_stat(path: Path) -> Optional[os.stat_result]:
    try:
        return path.stat()
    except Exception:
        return None


def resolve_runtime_path(raw: Optional[str]) -> Optional[Path]:
    if not raw:
        return None

    value = str(raw)
    if value.startswith("data/"):
        return BACKEND_ROOT / value

    path = Path(value)
    if path.is_absolute():
        return path

    return BACKEND_ROOT / path


def path_stats(path: Optional[Path]) -> Dict[str, Any]:
    if path is None:
        return {
            "path": None,
            "exists": False,
            "size_bytes": 0,
            "file_count": 0,
            "last_write_epoch": None,
            "seconds_since_last_write": None,
        }

    now = time.time()
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "size_bytes": 0,
            "file_count": 0,
            "last_write_epoch": None,
            "seconds_since_last_write": None,
        }

    if path.is_file():
        st = safe_stat(path)
        if not st:
            return {
                "path": str(path),
                "exists": True,
                "size_bytes": 0,
                "file_count": 0,
                "last_write_epoch": None,
                "seconds_since_last_write": None,
            }
        return {
            "path": str(path),
            "exists": True,
            "size_bytes": st.st_size,
            "file_count": 1,
            "last_write_epoch": st.st_mtime,
            "seconds_since_last_write": max(0, int(now - st.st_mtime)),
        }

    total_size = 0
    file_count = 0
    last_write_epoch = None
    try:
        for root, _, files in os.walk(path):
            for name in files:
                fp = Path(root) / name
                st = safe_stat(fp)
                if not st:
                    continue
                total_size += st.st_size
                file_count += 1
                if last_write_epoch is None or st.st_mtime > last_write_epoch:
                    last_write_epoch = st.st_mtime
    except Exception:
        pass

    return {
        "path": str(path),
        "exists": True,
        "size_bytes": total_size,
        "file_count": file_count,
        "last_write_epoch": last_write_epoch,
        "seconds_since_last_write": None if last_write_epoch is None else max(0, int(now - last_write_epoch)),
    }


def normalized_status(job: Dict[str, Any]) -> str:
    status = str(job.get("status") or job.get("state") or "unknown").lower()
    if status in {"complete", "completed", "converted", "ready"}:
        return "completed"
    if status in {"cancelled", "canceled"}:
        return "cancelled"
    if status in {"failed", "error"} or job.get("error"):
        return "failed"
    if status in ACTIVE_STATUSES:
        return status
    return status or "unknown"


def health_for_job(job: Dict[str, Any], temp: Dict[str, Any], output: Dict[str, Any]) -> Tuple[str, str]:
    status = normalized_status(job)
    if status == "failed":
        return "failed", "Job reports failed/error status or has an error field."
    if status in {"completed", "cancelled", "force_stopped"}:
        return status, f"Job reports terminal status: {status}."
    if output.get("exists"):
        return "output_exists", "Output artifact exists."
    if status in ACTIVE_STATUSES:
        if temp.get("exists"):
            seconds = temp.get("seconds_since_last_write")
            if seconds is not None and seconds <= 180:
                return "running", "Temporary artifact has recent writes."
            return "possibly_stalled", "Temporary artifact exists but has no recent writes."
        return "active_no_artifact_evidence", "Job reports active status but has no temporary artifact evidence."
    return "unknown", "No clear runtime health evidence."


def job_identity(path: Path, job: Dict[str, Any]) -> str:
    return str(job.get("job_id") or job.get("id") or path.stem)


def normalize_job(path: Path, include_raw: bool = False) -> Dict[str, Any]:
    job = read_json(path, {})
    if not isinstance(job, dict):
        job = {"error": "Job record was not a JSON object."}

    job_id = job_identity(path, job)
    status = normalized_status(job)

    temp_path = resolve_runtime_path(job.get("temp_output_path") or job.get("temp_path"))
    output_path = resolve_runtime_path(
        job.get("output_path")
        or job.get("zarr_path")
        or job.get("zarr_url")
        or job.get("storage_uri")
    )
    input_path = resolve_runtime_path(job.get("input_path") or job.get("source_path"))

    temp = path_stats(temp_path)
    output = path_stats(output_path)
    input_stats = path_stats(input_path)
    health, health_reason = health_for_job(job, temp, output)

    st = safe_stat(path)

    actions = {
        "can_cancel": False,
        "can_force_stop": False,
        "can_cleanup_temp": bool(temp.get("exists")) and status not in ACTIVE_STATUSES,
        "reason": "JOB_CONTROL_1 is read-only inventory. Control actions are intentionally not enabled yet.",
    }

    item: Dict[str, Any] = {
        "schema_version": "system.job_control.job.v1",
        "job_id": job_id,
        "job_record_path": str(path),
        "job_type": job.get("job_type") or job.get("type") or "conversion_or_processing",
        "status": job.get("status") or job.get("state") or "unknown",
        "normalized_status": status,
        "health": health,
        "health_reason": health_reason,
        "progress": job.get("progress"),
        "message": job.get("message"),
        "error": job.get("error"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "updated_at": job.get("updated_at"),
        "finished_at": job.get("finished_at") or job.get("completed_at"),
        "record_modified_epoch": None if not st else st.st_mtime,
        "ids": {
            "file_id": job.get("file_id"),
            "dataset_id": job.get("dataset_id"),
            "candidate_id": job.get("candidate_id"),
            "repository_id": job.get("repository_id"),
            "volume_id": job.get("volume_id") or job.get("id"),
        },
        "paths": {
            "input_path": job.get("input_path") or job.get("source_path"),
            "output_path": job.get("output_path") or job.get("zarr_path") or job.get("zarr_url") or job.get("storage_uri"),
            "temp_output_path": job.get("temp_output_path") or job.get("temp_path"),
        },
        "artifact_status": {
            "input": input_stats,
            "temp": temp,
            "output": output,
        },
        "runtime": {
            "runtime_type": "local_backend_job_record",
            "worker_ref": job.get("worker_ref"),
            "pid": job.get("pid"),
            "process_group": job.get("process_group"),
            "host": job.get("host"),
            "note": "PID/process fields are diagnostic only and are not the public control contract.",
        },
        "actions": actions,
    }

    if include_raw:
        item["raw"] = job

    return item


def list_jobs(limit: int = 100, include_raw: bool = False) -> Dict[str, Any]:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    paths = sorted(
        JOBS_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )
    jobs = [normalize_job(p, include_raw=include_raw) for p in paths[: max(0, limit)]]
    active_count = sum(1 for j in jobs if str(j.get("normalized_status")) in ACTIVE_STATUSES)
    stalled_count = sum(1 for j in jobs if j.get("health") == "possibly_stalled")
    failed_count = sum(1 for j in jobs if j.get("normalized_status") == "failed")
    return {
        "schema_version": "system.job_control.list.v1",
        "generated_at": utc_now(),
        "runtime_profile": "local_desktop",
        "control_mode": "read_only_inventory",
        "job_count": len(jobs),
        "total_job_records": len(paths),
        "active_count": active_count,
        "possibly_stalled_count": stalled_count,
        "failed_count": failed_count,
        "jobs": jobs,
        "actions": {
            "cancel_available": False,
            "force_stop_available": False,
            "cleanup_available": False,
            "reason": "JOB_CONTROL_1 exposes inventory only. Cancel/force-stop will be added in a later backend-owned block.",
        },
    }


def get_job(job_id: str, include_raw: bool = False) -> Optional[Dict[str, Any]]:
    if not job_id or "/" in job_id or ".." in job_id:
        return None
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    return normalize_job(path, include_raw=include_raw)
