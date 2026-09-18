from __future__ import annotations

# JOB_RETENTION_1_SERVICE

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
JOB_PRUNE_SUMMARY_DIR = DATA_DIR / "job_prune_summaries"

DEFAULT_KEEP_LATEST = 100

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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def retention_policy() -> Dict[str, Any]:
    return {
        "schema_version": "system.job_history.retention_policy.v1",
        "policy_name": "keep_latest_non_running_job_records",
        "default_keep_latest": DEFAULT_KEEP_LATEST,
        "job_record_dir": str(JOBS_DIR),
        "summary_dir": str(JOB_PRUNE_SUMMARY_DIR),
        "rules": {
            "keep_latest_total_target": DEFAULT_KEEP_LATEST,
            "never_delete_running_jobs": True,
            "preserve_invalid_json": True,
            "delete_only_json_files_under_jobs_dir": True,
            "default_prune_mode": "dry_run",
        },
        "active_statuses": sorted(ACTIVE_STATUSES),
    }


def _safe_stat(path: Path) -> Optional[Any]:
    try:
        return path.stat()
    except Exception:
        return None


def _is_under_directory(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except Exception:
        return False


def _read_job(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
        return {"_invalid_job_record": True, "_invalid_reason": "JSON payload is not an object."}
    except Exception as exc:
        return {"_invalid_job_record": True, "_invalid_reason": repr(exc)}


def _normalized_status(job: Dict[str, Any]) -> str:
    if job.get("_invalid_job_record"):
        return "invalid"

    status = str(job.get("status") or job.get("state") or "unknown").lower()
    if status in {"complete", "completed", "converted", "ready"}:
        return "completed"
    if status in {"cancelled", "canceled"}:
        return "cancelled"
    if status in {"failed", "error"} or job.get("error"):
        return "failed"
    return status or "unknown"


def _job_id(path: Path, job: Dict[str, Any]) -> str:
    return str(job.get("job_id") or job.get("id") or path.stem)


def _job_record(path: Path) -> Dict[str, Any]:
    st = _safe_stat(path)
    job = _read_job(path)
    status = _normalized_status(job)
    return {
        "job_id": _job_id(path, job),
        "path": str(path),
        "filename": path.name,
        "status": status,
        "is_running": status in ACTIVE_STATUSES,
        "is_invalid": bool(job.get("_invalid_job_record")),
        "record_modified_epoch": None if st is None else st.st_mtime,
        "size_bytes": None if st is None else st.st_size,
        "reason": None,
    }


def _job_records(jobs_dir: Path) -> List[Dict[str, Any]]:
    if not jobs_dir.exists():
        return []

    records: List[Dict[str, Any]] = []
    for path in jobs_dir.glob("*.json"):
        if not path.is_file():
            continue
        if not _is_under_directory(path, jobs_dir):
            continue
        records.append(_job_record(path))

    records.sort(
        key=lambda item: float(item.get("record_modified_epoch") or 0),
        reverse=True,
    )
    return records


def prune_job_history(
    keep_latest: int = DEFAULT_KEEP_LATEST,
    dry_run: bool = True,
    jobs_dir: Optional[Path] = None,
    summary_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    jobs_root = jobs_dir or JOBS_DIR
    summary_root = summary_dir or JOB_PRUNE_SUMMARY_DIR

    safe_keep_latest = max(1, int(keep_latest or DEFAULT_KEEP_LATEST))
    jobs_root.mkdir(parents=True, exist_ok=True)

    records = _job_records(jobs_root)

    running = [item for item in records if item["is_running"]]
    invalid = [item for item in records if item["is_invalid"]]
    non_running_valid = [
        item for item in records
        if not item["is_running"] and not item["is_invalid"]
    ]

    keep_slots_for_non_running = max(0, safe_keep_latest - len(running) - len(invalid))
    keep_non_running = non_running_valid[:keep_slots_for_non_running]
    prune_candidates = non_running_valid[keep_slots_for_non_running:]

    preserved_by_id = {item["path"] for item in running + invalid + keep_non_running}

    preserved: List[Dict[str, Any]] = []
    for item in records:
        copy = dict(item)
        if item["path"] in preserved_by_id:
            if item["is_running"]:
                copy["reason"] = "preserved_running_job"
            elif item["is_invalid"]:
                copy["reason"] = "preserved_invalid_json"
            else:
                copy["reason"] = "preserved_recent_job"
            preserved.append(copy)

    pruned: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for item in prune_candidates:
        path = Path(str(item["path"]))
        planned = dict(item)
        planned["reason"] = "oldest_non_running_beyond_keep_latest"
        if dry_run:
            planned["deleted"] = False
            pruned.append(planned)
            continue

        try:
            if path.suffix != ".json":
                raise RuntimeError("Refusing to delete non-json job file.")
            if not _is_under_directory(path, jobs_root):
                raise RuntimeError("Refusing to delete file outside jobs directory.")
            if not path.exists():
                planned["deleted"] = False
                planned["missing_at_delete_time"] = True
            else:
                path.unlink()
                planned["deleted"] = True
            pruned.append(planned)
        except Exception as exc:
            error = dict(planned)
            error["deleted"] = False
            error["error"] = repr(exc)
            errors.append(error)

    summary: Dict[str, Any] = {
        "schema_version": "system.job_history.prune_result.v1",
        "generated_at": utc_now(),
        "dry_run": bool(dry_run),
        "keep_latest": safe_keep_latest,
        "jobs_dir": str(jobs_root),
        "jobs_seen": len(records),
        "running_seen": len(running),
        "invalid_seen": len(invalid),
        "preserved": len(preserved),
        "would_prune": len(prune_candidates) if dry_run else 0,
        "pruned": 0 if dry_run else sum(1 for item in pruned if item.get("deleted")),
        "errors": errors,
        "preserved_jobs": preserved,
        "prune_candidates": pruned if dry_run else [],
        "pruned_jobs": [] if dry_run else pruned,
        "safety": {
            "running_jobs_deleted": False,
            "invalid_json_deleted": False,
            "delete_scope": "json_files_under_jobs_dir_only",
        },
        "summary_path": None,
    }

    if not dry_run:
        summary_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        summary_path = summary_root / f"job_prune_summary_{stamp}.json"
        summary["summary_path"] = str(summary_path)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    return summary
