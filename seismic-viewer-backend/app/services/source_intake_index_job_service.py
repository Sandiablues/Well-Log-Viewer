from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.services.source_intake_index_service import build_source_intake_candidate_index


JOB_DIR = Path(__file__).resolve().parents[2] / "data" / "source_intake_index_jobs"
JOB_DIR.mkdir(parents=True, exist_ok=True)
_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_path(job_id: str) -> Path:
    return JOB_DIR / f"{job_id}.json"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _save_job(job: Dict[str, Any]) -> Dict[str, Any]:
    job["updated_at"] = _utc_now()
    path = _job_path(str(job["job_id"]))
    tmp = path.with_suffix(".json.tmp")
    with _LOCK:
        tmp.write_text(json.dumps(job, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    return job


def _load_job(path: Path) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(value, dict):
        return None
    value.setdefault("job_file", path.name)
    return value


def list_source_intake_index_jobs() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(JOB_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        job = _load_job(path)
        if job:
            rows.append(job)
    return rows


def get_latest_source_intake_index_job(candidate_id: str) -> Optional[Dict[str, Any]]:
    clean_candidate = _clean(candidate_id)
    if not clean_candidate:
        return None

    for job in list_source_intake_index_jobs():
        if _clean(job.get("candidate_id")) == clean_candidate or _clean(job.get("source_segy_file_id")) == clean_candidate:
            return job
    return None


def _update_job(job_id: str, **updates: Any) -> Dict[str, Any]:
    path = _job_path(job_id)
    job = _load_job(path)
    if not job:
        raise FileNotFoundError(f"Source Intake index job not found: {job_id}")
    job.update(updates)
    return _save_job(job)


def _run_index_job(job_id: str, candidate_id: str, mode: str) -> None:
    try:
        _update_job(
            job_id,
            status="running",
            state="running",
            progress=10,
            message="Resolving Source Intake SEG-Y candidate.",
        )
        _update_job(
            job_id,
            status="running",
            state="running",
            progress=25,
            message="Building indexed SEG-Y preview.",
        )

        result = build_source_intake_candidate_index(candidate_id, mode=mode)

        created = bool(result.get("created"))
        dataset_id = result.get("dataset_id")
        _update_job(
            job_id,
            status="running",
            state="running",
            progress=92,
            message="Validating indexed SEG-Y preview.",
            dataset_id=dataset_id,
            result=result,
        )
        _update_job(
            job_id,
            status="complete",
            state="complete",
            progress=100,
            message=(
                "3D index complete. View Indexed Preview is available."
                if created
                else "3D index already existed. View Indexed Preview is available."
            ),
            dataset_id=dataset_id,
            result=result,
            completed_at=_utc_now(),
        )
    except Exception as exc:
        try:
            _update_job(
                job_id,
                status="failed",
                state="failed",
                progress=100,
                message="3D index build failed.",
                error=str(exc),
                completed_at=_utc_now(),
            )
        except Exception:
            pass


def queue_source_intake_index_job(candidate_id: str, mode: str = "3d") -> Dict[str, Any]:
    clean_candidate = _clean(candidate_id)
    clean_mode = _clean(mode).lower() or "3d"
    if not clean_candidate:
        raise ValueError("Source Intake candidate_id is required.")
    if clean_mode != "3d":
        raise ValueError(f"Unsupported Source Intake index mode: {mode!r}")

    existing = get_latest_source_intake_index_job(clean_candidate)
    if existing and _clean(existing.get("status")).lower() in {"queued", "running", "pending", "submitted", "started", "in_progress"}:
        return {
            "status": "accepted",
            "action": "source_intake_index_preview_job",
            "queued": False,
            "job": existing,
            "job_id": existing.get("job_id"),
            "candidate_id": clean_candidate,
            "message": "Build Index job is already running for this Source Intake candidate.",
        }

    job_id = f"source-intake-index-{uuid4()}"
    job = {
        "job_id": job_id,
        "job_type": "source_intake_build_index",
        "action": "source_intake_index_preview",
        "candidate_id": clean_candidate,
        "source_segy_file_id": clean_candidate,
        "mode": clean_mode,
        "status": "queued",
        "state": "queued",
        "progress": 5,
        "message": "Build Index queued.",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "dataset_id": None,
        "result": None,
        "error": None,
    }
    _save_job(job)

    worker = threading.Thread(target=_run_index_job, args=(job_id, clean_candidate, clean_mode), daemon=True)
    worker.start()

    return {
        "status": "accepted",
        "action": "source_intake_index_preview_job",
        "queued": True,
        "job": job,
        "job_id": job_id,
        "candidate_id": clean_candidate,
        "message": "Build Index submitted. Watch the row progress meter for completion.",
    }
