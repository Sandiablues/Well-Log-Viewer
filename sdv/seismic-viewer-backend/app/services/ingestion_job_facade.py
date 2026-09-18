from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException, UploadFile

from app.services import ingestion_runtime


def _jobs_dir() -> Path:
    return Path(ingestion_runtime.JOBS_DIR)


async def upload_segy(file: UploadFile) -> Dict[str, Any]:
    """
    Accept a SEG-Y upload and queue conversion using the ingestion runtime.

    This keeps upload/job orchestration outside the general endpoints module
    while preserving the existing conversion service and job file format.
    """
    file_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    os.makedirs(ingestion_runtime.UPLOAD_DIR, exist_ok=True)
    os.makedirs(ingestion_runtime.ZARR_DIR, exist_ok=True)
    os.makedirs(ingestion_runtime.ZARR_TMP_DIR, exist_ok=True)
    os.makedirs(ingestion_runtime.JOBS_DIR, exist_ok=True)

    file_path = os.path.join(ingestion_runtime.UPLOAD_DIR, f"{file_id}.sgy")
    output_path = os.path.join(ingestion_runtime.ZARR_DIR, f"{file_id}.zarr")
    temp_output_path = os.path.join(ingestion_runtime.ZARR_TMP_DIR, f"{file_id}.zarr.tmp")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    ingestion_runtime.job_service.create_job(
        job_id=job_id,
        file_id=file_id,
        filename=file.filename,
        input_path=file_path,
        output_path=output_path,
        temp_output_path=temp_output_path,
    )

    ingestion_runtime.conversion_executor.submit(
        ingestion_runtime.conversion_job_service.run,
        job_id,
    )

    return {
        "job_id": job_id,
        "file_id": file_id,
        "status": "queued",
        "message": "SEG-Y upload accepted. Conversion started.",
    }


def list_recent_jobs(limit: int = 20) -> Dict[str, Any]:
    """
    List recent conversion jobs.
    """
    jobs_path = _jobs_dir()
    jobs_path.mkdir(parents=True, exist_ok=True)

    jobs = []
    for path in jobs_path.glob("*.json"):
        try:
            with open(path, "r") as f:
                job = json.load(f)
            job.setdefault("job_id", path.stem)
            job["_modified_time"] = path.stat().st_mtime
            jobs.append(job)
        except Exception:
            continue

    jobs.sort(key=lambda job: job.get("_modified_time", 0), reverse=True)

    for job in jobs:
        job.pop("_modified_time", None)

    return {
        "count": len(jobs),
        "jobs": jobs[:limit],
    }


def get_conversion_job(job_id: str) -> Dict[str, Any]:
    """
    Read a single conversion job using the ingestion runtime job service.
    """
    job = ingestion_runtime.job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job
