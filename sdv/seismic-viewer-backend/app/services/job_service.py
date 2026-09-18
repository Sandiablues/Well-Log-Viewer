import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class JobService:
    def __init__(self, jobs_dir: str = "./data/jobs"):
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def utc_now(self) -> str:
        return datetime.utcnow().isoformat() + "Z"

    def create_job(
        self,
        job_id: str,
        file_id: str,
        filename: str,
        input_path: str,
        output_path: str,
        temp_output_path: str,
        expected_dataset_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        job = {
            "job_id": job_id,
            "file_id": file_id,
            "filename": filename,
            "status": "queued",
            "message": "SEG-Y upload accepted. Conversion queued.",
            "progress": None,
            "created_at": self.utc_now(),
            "updated_at": self.utc_now(),
            "input_path": input_path,
            "output_path": output_path,
            "temp_output_path": temp_output_path,
            "expected_dataset_type": expected_dataset_type,
            "volume": None,
            "error": None,
        }

        self.save_job(job)
        return job

    def save_job(self, job: Dict[str, Any]) -> None:
        with self._lock:
            job["updated_at"] = self.utc_now()
            path = self._job_path(job["job_id"])
            tmp_path = path.with_suffix(".json.tmp")

            with open(tmp_path, "w") as f:
                json.dump(job, f, indent=2)

            tmp_path.replace(path)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        path = self._job_path(job_id)

        if not path.exists():
            return None

        with open(path, "r") as f:
            return json.load(f)

    def update_job(self, job_id: str, **updates) -> Optional[Dict[str, Any]]:
        job = self.get_job(job_id)

        if not job:
            return None

        job.update(updates)
        self.save_job(job)
        return job

    def mark_abandoned_jobs_failed(self) -> None:
        active_statuses = {
            "queued",
            "saving_upload",
            "reading_metadata",
            "validating_geometry",
            "converting",
            "writing_zarr",
            "validating_zarr",
            "promoting_output",
            "registering_volume",
        }

        for path in self.jobs_dir.glob("*.json"):
            try:
                with open(path, "r") as f:
                    job = json.load(f)

                if job.get("status") in active_statuses:
                    job["status"] = "failed"
                    job["message"] = "Job was interrupted before completion."
                    job["error"] = "Backend restarted or job was abandoned before conversion completed."
                    self.save_job(job)

            except Exception:
                continue
