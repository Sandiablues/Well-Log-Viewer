from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from app.storage.service import is_endrepo_zarr_url, resolve_endrepo_zarr_url_path
from typing import Any, Dict, List, Optional

from app.services.job_control_service import get_job as get_job_control_detail, list_jobs as list_job_control_records

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/system", tags=["system"])

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
ZARR_DIR = DATA_DIR / "zarr"
ZARR_TMP_DIR = DATA_DIR / "zarr_tmp"
REGISTRY_DIR = DATA_DIR / "registry"
VOLUMES_FILE = DATA_DIR / "volumes.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return fallback


def _safe_stat(path: Path) -> Optional[os.stat_result]:
    try:
        return path.stat()
    except Exception:
        return None


def _dir_size_and_count(path: Path) -> Dict[str, Any]:
    total_size = 0
    file_count = 0
    last_write_epoch = None

    if not path.exists():
        return {
            "exists": False,
            "size_bytes": 0,
            "file_count": 0,
            "last_write_epoch": None,
            "seconds_since_last_write": None,
        }

    if path.is_file():
        st = _safe_stat(path)
        if not st:
            return {
                "exists": True,
                "size_bytes": 0,
                "file_count": 0,
                "last_write_epoch": None,
                "seconds_since_last_write": None,
            }

        now = time.time()
        return {
            "exists": True,
            "size_bytes": st.st_size,
            "file_count": 1,
            "last_write_epoch": st.st_mtime,
            "seconds_since_last_write": max(0, int(now - st.st_mtime)),
        }

    try:
        for root, _, files in os.walk(path):
            for name in files:
                fp = Path(root) / name
                st = _safe_stat(fp)
                if not st:
                    continue
                total_size += st.st_size
                file_count += 1
                if last_write_epoch is None or st.st_mtime > last_write_epoch:
                    last_write_epoch = st.st_mtime
    except Exception:
        pass

    now = time.time()
    return {
        "exists": True,
        "size_bytes": total_size,
        "file_count": file_count,
        "last_write_epoch": last_write_epoch,
        "seconds_since_last_write": None if last_write_epoch is None else max(0, int(now - last_write_epoch)),
    }


def _resolve_project_path(raw: Optional[str]) -> Optional[Path]:
    if not raw:
        return None

    raw = str(raw)

    if raw.startswith("/data/zarr/"):
        return ZARR_DIR / raw.split("/data/zarr/", 1)[1]

    if is_endrepo_zarr_url(raw):
        try:
            return resolve_endrepo_zarr_url_path(raw)
        except Exception:
            return Path(raw)

    if raw.startswith("data/"):
        return BACKEND_ROOT / raw

    p = Path(raw)
    if p.is_absolute():
        return p

    return BACKEND_ROOT / p


def _job_health(job: Dict[str, Any], temp_stats: Dict[str, Any], final_path: Optional[Path]) -> Dict[str, str]:
    status = str(job.get("status") or "").lower()
    error = job.get("error")

    if error or status in {"failed", "error"}:
        return {
            "health": "failed",
            "health_reason": "Job reports an error or failed status.",
        }

    if status in {"completed", "complete", "converted", "ready"}:
        return {
            "health": "complete",
            "health_reason": "Job reports completed/converted status.",
        }

    if final_path and final_path.exists():
        return {
            "health": "complete",
            "health_reason": "Final output path exists.",
        }

    if status in {"converting", "queued", "running", "processing"}:
        if temp_stats.get("exists") and temp_stats.get("last_write_epoch"):
            seconds = temp_stats.get("seconds_since_last_write")
            if seconds is not None and seconds <= 180:
                return {
                    "health": "running",
                    "health_reason": "Temporary Zarr output has recent writes.",
                }

            return {
                "health": "possibly_stalled",
                "health_reason": "Temporary Zarr output exists but has no recent writes.",
            }

        return {
            "health": "unknown",
            "health_reason": "Job is active but no temporary output evidence was found.",
        }

    return {
        "health": "unknown",
        "health_reason": "No clear health evidence.",
    }


def _load_registry_file(name: str) -> List[Dict[str, Any]]:
    data = _read_json(REGISTRY_DIR / name, [])

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ("items", "repositories", "packages", "lines", "segy_files", "documents"):
            if isinstance(data.get(key), list):
                return data[key]

    return []


def _get_id(item: Dict[str, Any]) -> Optional[str]:
    for key in ("repository_id", "repo_id", "id", "uuid"):
        if item.get(key):
            return str(item.get(key))
    return None


def _repo_key(item: Dict[str, Any]) -> Optional[str]:
    for key in ("repository_id", "repo_id", "source_repository_id"):
        if item.get(key):
            return str(item.get(key))
    return None


def _repositories_summary() -> List[Dict[str, Any]]:
    repositories = _load_registry_file("repositories.json")
    packages = _load_registry_file("packages.json")
    lines = _load_registry_file("lines.json")
    segy_files = _load_registry_file("segy_files.json")
    documents = _load_registry_file("documents.json")

    summaries = []

    for repo in repositories:
        rid = _get_id(repo)
        summaries.append({
            "repository_id": rid,
            "name": repo.get("name") or repo.get("label") or repo.get("path") or rid,
            "status": repo.get("status") or "available",
            "last_scanned_at": repo.get("last_scanned_at") or repo.get("last_scan_at") or repo.get("updated_at"),
            "package_count": sum(1 for x in packages if _repo_key(x) == rid),
            "line_count": sum(1 for x in lines if _repo_key(x) == rid),
            "segy_file_count": sum(1 for x in segy_files if _repo_key(x) == rid),
            "document_count": sum(1 for x in documents if _repo_key(x) == rid),
        })

    return summaries


def _extract_sample_interval_us(meta: Dict[str, Any]) -> Optional[float]:
    candidates = [
        meta.get("sample_interval_us"),
        meta.get("sample_interval"),
        meta.get("sample_rate_us"),
    ]

    binary_header = meta.get("binary_header")
    if isinstance(binary_header, dict):
        candidates.append(binary_header.get("sample_interval_us"))

    trace_header = meta.get("trace_header")
    if isinstance(trace_header, dict):
        candidates.append(trace_header.get("sample_interval_us"))

    viewer_metadata = meta.get("viewer_metadata")
    if isinstance(viewer_metadata, dict):
        candidates.append(viewer_metadata.get("sample_interval_us"))

    for value in candidates:
        try:
            if value is not None:
                return float(value)
        except Exception:
            continue

    return None


def _volume_id(volume: Dict[str, Any]) -> Optional[str]:
    for key in ("volume_id", "id", "uuid"):
        if volume.get(key):
            return str(volume.get(key))
    return None


def _volume_filename(volume: Dict[str, Any]) -> str:
    return str(
        volume.get("filename")
        or volume.get("file_name")
        or volume.get("name")
        or volume.get("display_name")
        or "unknown"
    )


def _volume_zarr_path(volume: Dict[str, Any]) -> Optional[Path]:
    raw = volume.get("zarr_path") or volume.get("zarr_url") or volume.get("path")
    if not raw:
        return None

    return _resolve_project_path(str(raw))


def _warnings() -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []

    volumes_data = _read_json(VOLUMES_FILE, [])

    if isinstance(volumes_data, dict):
        volumes = volumes_data.get("volumes") or volumes_data.get("items") or []
    else:
        volumes = volumes_data

    if not isinstance(volumes, list):
        return warnings

    filename_counts: Dict[str, int] = {}

    for volume in volumes:
        if isinstance(volume, dict):
            fname = _volume_filename(volume)
            filename_counts[fname] = filename_counts.get(fname, 0) + 1

    for volume in volumes:
        if not isinstance(volume, dict):
            continue

        vid = _volume_id(volume)
        fname = _volume_filename(volume)

        is_visible = bool(volume.get("visible", True))
        is_2d = volume.get("is_3d") is False or str(volume.get("dataset_type", "")).lower() == "2d"

        source_keys = [
            volume.get("source"),
            volume.get("source_metadata"),
            volume.get("source_repository_id"),
            volume.get("repository_id"),
            volume.get("registry_item_id"),
        ]

        if is_visible and is_2d and not any(source_keys):
            warnings.append({
                "level": "warning",
                "type": "missing_source_metadata",
                "message": "Visible 2D volume has no repository source metadata.",
                "volume_id": vid,
                "filename": fname,
            })

        if filename_counts.get(fname, 0) > 1:
            warnings.append({
                "level": "warning",
                "type": "duplicate_visible_filename",
                "message": "Duplicate volume filename found in managed data.",
                "volume_id": vid,
                "filename": fname,
                "count": filename_counts.get(fname),
            })

        interval = _extract_sample_interval_us(volume)
        if interval is not None and interval < 250:
            warnings.append({
                "level": "warning",
                "type": "suspicious_sample_interval",
                "message": "Sample interval is suspiciously low for seismic display.",
                "volume_id": vid,
                "filename": fname,
                "sample_interval_us": interval,
            })

        zarr_path = _volume_zarr_path(volume)
        if zarr_path and zarr_path.exists():
            for sidecar in [
                ".viewer_metadata.json",
                ".segy_text_header.txt",
                ".segy_binary_header.json",
                ".trace_header_summary.json",
            ]:
                if not (zarr_path / sidecar).exists():
                    warnings.append({
                        "level": "info",
                        "type": "missing_sidecar",
                        "message": f"Missing expected sidecar: {sidecar}",
                        "volume_id": vid,
                        "filename": fname,
                        "sidecar": sidecar,
                    })

    return warnings


def _conversion_jobs() -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []

    if not JOBS_DIR.exists():
        return jobs

    job_paths = sorted(
        JOBS_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )

    for path in job_paths:
        job = _read_json(path, {})
        if not isinstance(job, dict):
            continue

        job_id = str(job.get("job_id") or job.get("id") or path.stem)

        temp_path = _resolve_project_path(job.get("temp_output_path"))
        output_path = _resolve_project_path(job.get("output_path") or job.get("zarr_path") or job.get("zarr_url"))

        if temp_path:
            temp_stats = _dir_size_and_count(temp_path)
        else:
            temp_stats = {
                "exists": False,
                "size_bytes": 0,
                "file_count": 0,
                "last_write_epoch": None,
                "seconds_since_last_write": None,
            }

        health = _job_health(job, temp_stats, output_path)

        jobs.append({
            "job_id": job_id,
            "filename": job.get("filename") or job.get("file_name") or job.get("input_filename"),
            "status": job.get("status"),
            "message": job.get("message"),
            "progress": job.get("progress"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "input_path": job.get("input_path"),
            "output_path": job.get("output_path") or job.get("zarr_path") or job.get("zarr_url"),
            "temp_output_path": job.get("temp_output_path"),
            "temp_exists": temp_stats.get("exists"),
            "temp_size_bytes": temp_stats.get("size_bytes"),
            "temp_file_count": temp_stats.get("file_count"),
            "last_write_epoch": temp_stats.get("last_write_epoch"),
            "seconds_since_last_write": temp_stats.get("seconds_since_last_write"),
            "health": health["health"],
            "health_reason": health["health_reason"],
            "error": job.get("error"),
        })

    return jobs


@router.get("/monitor")
def get_system_monitor() -> Dict[str, Any]:
    zarr_tmp_stats = _dir_size_and_count(ZARR_TMP_DIR)

    return {
        "backend": {
            "status": "online",
            "timestamp": _utc_now(),
            "backend_root": str(BACKEND_ROOT),
            "data_dir": str(DATA_DIR),
            "zarr_dir": str(ZARR_DIR),
            "zarr_tmp_dir": str(ZARR_TMP_DIR),
            "zarr_tmp_size_bytes": zarr_tmp_stats.get("size_bytes"),
            "zarr_tmp_file_count": zarr_tmp_stats.get("file_count"),
        },
        "conversion_jobs": _conversion_jobs(),
        "repositories": _repositories_summary(),
        "warnings": _warnings(),
    }

# JOB_CONTROL_1_ROUTES
@router.get("/jobs")
def get_system_jobs(limit: int = 100, include_raw: bool = False) -> Dict[str, Any]:
    """Return portable read-only job inventory.

    JOB_CONTROL_1 deliberately exposes inventory only. Cancel/force-stop actions
    are disabled until job execution ownership and runtime adapters are added.
    """
    safe_limit = max(1, min(int(limit or 100), 500))
    return list_job_control_records(limit=safe_limit, include_raw=include_raw)


# JOB_RETENTION_1_ROUTES
@router.get("/jobs/retention-policy")
def get_job_retention_policy() -> Dict[str, Any]:
    from app.services.job_history_retention_service import retention_policy
    return retention_policy()


@router.post("/jobs/prune")
def prune_system_job_history(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from app.services.job_history_retention_service import DEFAULT_KEEP_LATEST, prune_job_history

    request = payload if isinstance(payload, dict) else {}
    keep_latest = int(request.get("keep_latest") or DEFAULT_KEEP_LATEST)
    dry_run = request.get("dry_run", True)
    if isinstance(dry_run, str):
        dry_run = dry_run.strip().lower() not in {"false", "0", "no"}

    return prune_job_history(keep_latest=keep_latest, dry_run=bool(dry_run))


@router.get("/jobs/{job_id}")
def get_system_job(job_id: str, include_raw: bool = False) -> Dict[str, Any]:
    job = get_job_control_detail(job_id=job_id, include_raw=include_raw)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job

