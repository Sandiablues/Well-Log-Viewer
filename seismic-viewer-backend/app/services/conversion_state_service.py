from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json


ACTIVE_JOB_STATUSES = {
    "queued",
    "saving_upload",
    "reading_metadata",
    "validating_geometry",
    "converting",
    "writing_zarr",
    "validating_zarr",
    "promoting_output",
    "registering_volume",
    "registering_dataset",
}

COMPLETE_JOB_STATUSES = {"complete", "completed", "ready"}
FAILED_JOB_STATUSES = {"failed", "error", "cancelled", "canceled"}


@dataclass(frozen=True)
class ConversionState:
    status: str
    job_id: Optional[str] = None
    volume_id: Optional[str] = None
    zarr_url: Optional[str] = None
    conversion_error: Optional[str] = None
    reason: Optional[str] = None
    is_authoritative: bool = True

    def as_updates(self) -> Dict[str, Any]:
        return {
            "conversion_status": self.status,
            "job_id": self.job_id,
            "volume_id": self.volume_id,
            "zarr_url": self.zarr_url,
            "conversion_error": self.conversion_error,
        }

    def as_payload(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "job_id": self.job_id,
            "volume_id": self.volume_id,
            "zarr_url": self.zarr_url,
            "conversion_error": self.conversion_error,
            "reason": self.reason,
            "is_authoritative": self.is_authoritative,
        }


class ConversionStateResolver:
    """
    Authoritative conversion-state resolver for source SEG-Y records.

    Source SEG-Y registry fields are treated as cached references only.
    The truth is resolved from:
    - explicit job_id on the source record
    - data/jobs/<job_id>.json
    - data/volumes.json
    - physical Zarr output

    This service intentionally does NOT infer state from filename/path historical jobs.
    That prevents re-imported/re-submitted source rows from inheriting stale
    converted/converting state from previous runs.
    """

    def __init__(
        self,
        jobs_dir: str | Path = "./data/jobs",
        volumes_json: str | Path = "./data/volumes.json",
        backend_root: str | Path = ".",
    ):
        self.jobs_dir = Path(jobs_dir)
        self.volumes_json = Path(volumes_json)
        self.backend_root = Path(backend_root)

    def resolve(self, segy_file: Dict[str, Any]) -> ConversionState:
        current_status = str(segy_file.get("conversion_status") or "not_converted")
        job_id = segy_file.get("job_id") or segy_file.get("conversion_job_id")

        if not job_id:
            if current_status in {"queued", "converting", "converted", "ready"}:
                return ConversionState(
                    status="error",
                    conversion_error="Stale conversion state: no authoritative job is linked to this source SEG-Y record.",
                    reason="missing_job_id_for_active_or_converted_status",
                )

            return ConversionState(
                status=current_status if current_status not in {"", "None", "null"} else "not_converted",
                reason="no_linked_job",
            )

        job = self._read_job(str(job_id))
        if not job:
            return ConversionState(
                status="error",
                job_id=str(job_id),
                conversion_error="Stale conversion state: linked job record is missing.",
                reason="linked_job_missing",
            )

        job_status = str(job.get("status") or "").lower()

        if job_status in ACTIVE_JOB_STATUSES:
            volume_id = job.get("file_id") or segy_file.get("volume_id")
            zarr_url = (
                segy_file.get("zarr_url")
                or job.get("zarr_url")
                or (f"/data/zarr/{volume_id}.zarr" if volume_id else None)
            )

            return ConversionState(
                status="queued" if job_status == "queued" else "converting",
                job_id=str(job.get("job_id") or job_id),
                volume_id=str(volume_id) if volume_id else None,
                zarr_url=zarr_url,
                reason=f"job_status_{job_status}",
            )

        if job_status in FAILED_JOB_STATUSES:
            return ConversionState(
                status="error",
                job_id=str(job.get("job_id") or job_id),
                volume_id=segy_file.get("volume_id") or job.get("file_id"),
                zarr_url=segy_file.get("zarr_url") or job.get("zarr_url"),
                conversion_error=job.get("error") or job.get("message") or "SEG-Y conversion failed.",
                reason=f"job_status_{job_status}",
            )

        if job_status in COMPLETE_JOB_STATUSES:
            volume = job.get("volume") or {}
            volume_id = volume.get("id") or job.get("file_id") or segy_file.get("volume_id")
            zarr_url = (
                volume.get("zarr_url")
                or job.get("zarr_url")
                or segy_file.get("zarr_url")
                or (f"/data/zarr/{volume_id}.zarr" if volume_id else None)
            )

            volume_exists = self._volume_exists(str(volume_id) if volume_id else None)
            zarr_exists = self._zarr_exists(zarr_url, job)

            if volume_exists and zarr_exists:
                return ConversionState(
                    status="converted",
                    job_id=str(job.get("job_id") or job_id),
                    volume_id=str(volume_id) if volume_id else None,
                    zarr_url=zarr_url,
                    reason="job_complete_volume_and_zarr_verified",
                )

            missing = []
            if not volume_exists:
                missing.append("managed dataset record")
            if not zarr_exists:
                missing.append("Zarr output")

            return ConversionState(
                status="error",
                job_id=str(job.get("job_id") or job_id),
                volume_id=str(volume_id) if volume_id else None,
                zarr_url=zarr_url,
                conversion_error=f"Converted job exists, but {' and '.join(missing)} is missing; reconvert required.",
                reason="job_complete_but_artifact_missing",
            )

        return ConversionState(
            status="error",
            job_id=str(job.get("job_id") or job_id),
            volume_id=segy_file.get("volume_id") or job.get("file_id"),
            zarr_url=segy_file.get("zarr_url") or job.get("zarr_url"),
            conversion_error=f"Unknown conversion job status: {job_status or 'missing'}",
            reason="unknown_job_status",
        )

    def _read_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        path = self.jobs_dir / f"{job_id}.json"
        if not path.exists():
            return None

        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

        return value if isinstance(value, dict) else None

    def _read_volumes(self) -> Dict[str, Any]:
        if not self.volumes_json.exists():
            return {}

        try:
            value = json.loads(self.volumes_json.read_text(encoding="utf-8"))
        except Exception:
            return {}

        return value if isinstance(value, dict) else {}

    def _volume_exists(self, volume_id: Optional[str]) -> bool:
        if not volume_id:
            return False

        return str(volume_id) in self._read_volumes()

    def _zarr_exists(self, zarr_url: Optional[str], job: Optional[Dict[str, Any]] = None) -> bool:
        candidates: list[Path] = []

        if zarr_url:
            zarr_text = str(zarr_url)
            if zarr_text.startswith("/data/"):
                candidates.append(self.backend_root / zarr_text.lstrip("/"))
            else:
                candidates.append(Path(zarr_text))

        if job and job.get("output_path"):
            candidates.append(Path(str(job.get("output_path"))))

        return any(path.exists() for path in candidates)


def resolve_source_segy_conversion_state(
    segy_file: Dict[str, Any],
    jobs_dir: str | Path = "./data/jobs",
    volumes_json: str | Path = "./data/volumes.json",
    backend_root: str | Path = ".",
) -> ConversionState:
    return ConversionStateResolver(
        jobs_dir=jobs_dir,
        volumes_json=volumes_json,
        backend_root=backend_root,
    ).resolve(segy_file)
