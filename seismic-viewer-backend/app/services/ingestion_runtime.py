from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

from app.services.conversion_job_service import ConversionJobService
from app.services.job_service import JobService


UPLOAD_DIR = os.environ.get("UPLOADS_DIR", "./data/uploads")
ZARR_DIR = os.environ.get("ZARR_DIR", "./data/zarr")
VOLUMES_JSON = os.environ.get("VOLUMES_JSON", "./data/volumes.json")
JOBS_DIR = os.environ.get("JOBS_DIR", "./data/jobs")
ZARR_TMP_DIR = os.environ.get("ZARR_TMP_DIR", "./data/zarr_tmp")

job_service = JobService(JOBS_DIR)
conversion_job_service = ConversionJobService(
    job_service=job_service,
    volumes_json=VOLUMES_JSON,
)
conversion_executor = ThreadPoolExecutor(max_workers=1)

job_service.mark_abandoned_jobs_failed()
