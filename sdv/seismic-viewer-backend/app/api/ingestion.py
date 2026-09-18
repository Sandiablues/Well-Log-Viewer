from __future__ import annotations

from fastapi import APIRouter, File, Query, UploadFile

from app.services.ingestion_job_facade import (
    get_conversion_job as get_conversion_job_service,
    list_recent_jobs as list_recent_jobs_service,
    upload_segy as upload_segy_service,
)

router = APIRouter(tags=["ingestion"])


@router.post("/upload")
async def upload_segy(file: UploadFile = File(...)):
    return await upload_segy_service(file)


@router.get("/jobs")
async def list_recent_jobs(limit: int = Query(20, ge=1, le=100)):
    return list_recent_jobs_service(limit=limit)


@router.get("/jobs/{job_id}")
async def get_conversion_job(job_id: str):
    return get_conversion_job_service(job_id)
