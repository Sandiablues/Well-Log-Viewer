from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.services.volume_registry_service import load_volumes, save_volumes
from app.msi.registration_service import register_converted_segy_file


class RebuildPromotionService:
    """Backend-owned lifecycle service for staged rebuild promotion.

    The service owns filesystem safety checks, staged job lookup, and managed
    volume registration for rebuild promotion. API modules should remain thin
    route adapters.
    """

    def __init__(self, backend_root: Optional[Path] = None, endrepo_root: Optional[Path] = None) -> None:
        self.backend_root = backend_root or Path(__file__).resolve().parents[2]
        self.endrepo_root = endrepo_root or Path(__file__).resolve().parents[4] / "End_Seismic_Data_Repository"
        self.jobs_dir = self.backend_root / "data" / "jobs"
        self.staging_base = (self.endrepo_root / "staging" / "conversion_jobs" / "rebuild").resolve()
        self.staging_2d_root = (self.staging_base / "2d").resolve()
        self.staging_3d_root = (self.staging_base / "3d").resolve()
        self.managed_zarr_base = (self.endrepo_root / "managed" / "zarr").resolve()
        self.managed_2d_root = (self.managed_zarr_base / "2d").resolve()
        self.managed_3d_root = (self.managed_zarr_base / "3d").resolve()

    def utc_now(self) -> str:
        return datetime.utcnow().isoformat() + "Z"

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def _read_jobs(self) -> List[Dict[str, Any]]:
        if not self.jobs_dir.exists():
            return []
        rows: List[Dict[str, Any]] = []
        for path in sorted(self.jobs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(value, dict):
                value.setdefault("job_file", path.name)
                rows.append(value)
        return rows

    def _write_job(self, job: Dict[str, Any]) -> None:
        job_id = str(job.get("job_id") or "").strip()
        if not job_id:
            raise ValueError("Cannot write staged rebuild job without job_id.")
        path = self._job_path(job_id)
        if not path.exists():
            raise FileNotFoundError(f"Job record not found: {job_id}")
        job["updated_at"] = self.utc_now()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(job, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _normalize_mode(self, mode: Optional[str]) -> str:
        clean = str(mode or "2d").strip().lower()
        if clean not in {"2d", "3d"}:
            raise HTTPException(status_code=400, detail="Rebuild promotion mode must be 2d or 3d.")
        return clean

    def _dataset_type_for_mode(self, mode: str) -> str:
        return "3d_volume" if mode == "3d" else "2d_line"

    def _representation_type_for_mode(self, mode: str) -> str:
        return "zarr_3d" if mode == "3d" else "zarr_2d"

    def _candidate_kind_for_mode(self, mode: str) -> str:
        return "3d_volume" if mode == "3d" else "2d_line"

    def _managed_root_for_mode(self, mode: str) -> Path:
        return self.managed_3d_root if mode == "3d" else self.managed_2d_root

    def _staging_roots(self) -> List[Path]:
        return [self.staging_2d_root, self.staging_3d_root]

    def _path_is_relative_to(self, path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def compact_staged_rebuild_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        staged = job.get("staged_rebuild") if isinstance(job.get("staged_rebuild"), dict) else {}
        context = job.get("rebuild_context") if isinstance(job.get("rebuild_context"), dict) else {}
        artifact_id = (
            staged.get("artifact_id")
            or job.get("file_id")
            or (f"rebuild_{job.get('job_id')}" if job.get("job_id") else None)
        )
        source_candidate_id = (
            context.get("candidate_id")
            or staged.get("source_candidate_id")
            or job.get("source_candidate_id")
        )
        return {
            "job_id": job.get("job_id"),
            "artifact_id": artifact_id,
            "status": job.get("status"),
            "message": job.get("message"),
            "progress": job.get("progress"),
            "mode": context.get("mode") or staged.get("mode") or "2d",
            "target": staged.get("target") or context.get("target") or (
                "managed_3d_volume_zarr" if (context.get("mode") or staged.get("mode")) == "3d" else "managed_2d_line_zarr"
            ),
            "source_candidate_id": source_candidate_id,
            "prior_volume_id": context.get("prior_volume_id") or staged.get("source_volume_id"),
            "repository_id": context.get("repository_id"),
            "line_id": context.get("line_id"),
            "output_path": staged.get("output_path") or job.get("output_path"),
            "zarr_url": staged.get("zarr_url") or job.get("zarr_url"),
            "storage_uri": staged.get("storage_uri") or job.get("storage_uri"),
            "promotion_required": bool(job.get("promotion_required") or staged.get("promotion_required")),
            "promotion_options": job.get("promotion_options") or staged.get("promotion_options") or [],
            "volume": staged.get("volume") or job.get("volume"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
        }

    def latest_promotion_ready_job(self, candidate_id: str, job_id: Optional[str] = None) -> Dict[str, Any]:
        clean_candidate_id = str(candidate_id or "").strip()
        clean_job_id = str(job_id or "").strip()
        if not clean_candidate_id:
            raise HTTPException(status_code=400, detail="Candidate id is required.")

        for job in self._read_jobs():
            if not isinstance(job, dict):
                continue
            compact = self.compact_staged_rebuild_job(job)
            if str(compact.get("source_candidate_id") or "") != clean_candidate_id:
                continue
            if clean_job_id and str(compact.get("job_id") or "") != clean_job_id:
                continue
            if str(compact.get("status") or "").strip().lower() not in {"complete", "completed"}:
                continue
            if not bool(compact.get("promotion_required")):
                continue
            return job

        raise HTTPException(status_code=404, detail="No promotion-ready staged rebuild was found for this candidate.")


    def _retire_other_promotion_ready_jobs_for_candidate(
        self,
        candidate_id: str,
        promoted_job_id: str,
        promoted_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        clean_candidate_id = str(candidate_id or "").strip()
        clean_promoted_job_id = str(promoted_job_id or "").strip()
        retired: List[Dict[str, Any]] = []
        if not clean_candidate_id or not clean_promoted_job_id:
            return retired

        for other in self._read_jobs():
            if not isinstance(other, dict):
                continue
            compact = self.compact_staged_rebuild_job(other)
            other_job_id = str(compact.get("job_id") or "").strip()
            if not other_job_id or other_job_id == clean_promoted_job_id:
                continue
            if str(compact.get("source_candidate_id") or "") != clean_candidate_id:
                continue
            if str(compact.get("status") or "").strip().lower() not in {"complete", "completed"}:
                continue
            if not bool(compact.get("promotion_required")):
                continue

            delete_result: Dict[str, Any] = {"skipped": True, "reason": "no_staged_output_path"}
            try:
                staged_artifact = self.safe_staged_artifact_path(compact.get("output_path"))
                delete_result = self._delete_staged_artifacts(staged_artifact)
            except Exception as exc:
                delete_result = {"skipped": True, "error": str(exc), "output_path": compact.get("output_path")}

            staged = other.get("staged_rebuild") if isinstance(other.get("staged_rebuild"), dict) else {}
            staged_updated = dict(staged)
            staged_updated["promotion_required"] = False
            staged_updated["promotion_options"] = []
            staged_updated["superseded_by_save_as_new"] = {
                "superseded_at": self.utc_now(),
                "promoted_job_id": clean_promoted_job_id,
                "promoted_volume_id": promoted_payload.get("promoted_volume_id") or promoted_payload.get("new_volume_id"),
                "promoted_representation_id": promoted_payload.get("promoted_representation_id"),
                "promoted_display_name": promoted_payload.get("display_name"),
                "delete_staged_result": delete_result,
            }
            other["staged_rebuild"] = staged_updated
            other["status"] = "superseded"
            other["message"] = "Staged rebuild superseded by Save as new promotion for this source row."
            other["progress"] = 100
            other["progress_stage"] = "staged_rebuild_superseded_by_save_as_new"
            other["promotion_required"] = False
            other["promotion_options"] = []
            other["superseded_by_job_id"] = clean_promoted_job_id
            other["superseded_by_promoted_volume_id"] = promoted_payload.get("promoted_volume_id") or promoted_payload.get("new_volume_id")
            other["superseded_by_promoted_representation_id"] = promoted_payload.get("promoted_representation_id")
            other["superseded_by_promoted_display_name"] = promoted_payload.get("display_name")
            self._write_job(other)
            retired.append({
                "job_id": other_job_id,
                "artifact_id": compact.get("artifact_id"),
                "delete_staged_result": delete_result,
            })
        return retired

    def safe_staged_artifact_path(self, output_path: Optional[str]) -> Path:
        raw = str(output_path or "").strip()
        if not raw:
            raise HTTPException(status_code=400, detail="Staged rebuild output path is missing.")
        path = Path(raw).expanduser().resolve()
        if not any(self._path_is_relative_to(path, root) for root in self._staging_roots()):
            raise HTTPException(status_code=400, detail=f"Refusing non-staged rebuild path: {path}")
        if path.suffix != ".zarr" or not path.name.startswith("rebuild_"):
            raise HTTPException(status_code=400, detail=f"Unexpected staged rebuild artifact path: {path}")
        return path

    def safe_managed_artifact_path(self, volume_id: str, mode: str = "2d") -> Path:
        clean = str(volume_id or "").strip()
        if not clean:
            raise ValueError("Managed volume id is required.")
        clean_mode = self._normalize_mode(mode)
        root = self._managed_root_for_mode(clean_mode)
        path = (root / f"{clean}.zarr").resolve()
        if not self._path_is_relative_to(path, root):
            raise ValueError(f"Invalid managed output path: {path}")
        return path

    def safe_managed_2d_artifact_path(self, volume_id: str) -> Path:
        return self.safe_managed_artifact_path(volume_id, mode="2d")

    def _copy_sidecars(self, source_artifact: Path, target_artifact: Path) -> List[str]:
        copied: List[str] = []
        for sidecar in source_artifact.parent.glob(source_artifact.name + ".*"):
            if not sidecar.exists() or sidecar == source_artifact:
                continue
            suffix = sidecar.name[len(source_artifact.name):]
            target = target_artifact.parent / f"{target_artifact.name}{suffix}"
            if sidecar.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(sidecar, target)
            else:
                shutil.copy2(sidecar, target)
            copied.append(str(target))
        return copied

    def _delete_staged_artifacts(self, staged_artifact: Path) -> Dict[str, Any]:
        deleted: List[str] = []
        missing: List[str] = []
        if staged_artifact.exists():
            if staged_artifact.is_dir():
                shutil.rmtree(staged_artifact)
            else:
                staged_artifact.unlink()
            deleted.append(str(staged_artifact))
        else:
            missing.append(str(staged_artifact))

        for sidecar in staged_artifact.parent.glob(staged_artifact.name + ".*"):
            if sidecar.exists() and sidecar != staged_artifact:
                if sidecar.is_dir():
                    shutil.rmtree(sidecar)
                else:
                    sidecar.unlink()
                deleted.append(str(sidecar))
        return {"artifact_path": str(staged_artifact), "deleted_paths": deleted, "missing_paths": missing}

    def _volume_record_for_save_as_new(
        self,
        staged_volume: Dict[str, Any],
        compact: Dict[str, Any],
        new_volume_id: str,
        display_name: str,
        target_path: Path,
        mode: str = "2d",
    ) -> Dict[str, Any]:
        record = dict(staged_volume or {})
        if not record:
            raise HTTPException(status_code=400, detail="Staged rebuild job does not contain a volume record to promote.")
        record["id"] = new_volume_id
        record["volume_id"] = new_volume_id
        clean_mode = self._normalize_mode(mode)
        record["dataset_type"] = self._dataset_type_for_mode(clean_mode)
        record["display_name"] = display_name
        record["hidden"] = True
        record["zarr_url"] = f"/endrepo/managed/zarr/{clean_mode}/{new_volume_id}.zarr"
        record["storage_uri"] = f"endrepo://managed/zarr/{clean_mode}/{new_volume_id}.zarr"
        record["source_candidate_id"] = compact.get("source_candidate_id")
        record["source_volume_id"] = compact.get("prior_volume_id")
        record["source_repository_id"] = compact.get("repository_id")
        record["line_id"] = compact.get("line_id")
        record["representation_type"] = self._representation_type_for_mode(clean_mode)
        record["viewer_mode"] = clean_mode
        record["rebuild_promotion"] = {
            "type": "save_as_new",
            "promoted_at": self.utc_now(),
            "job_id": compact.get("job_id"),
            "artifact_id": compact.get("artifact_id"),
            "prior_volume_id": compact.get("prior_volume_id"),
            "source_candidate_id": compact.get("source_candidate_id"),
        }
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        metadata = dict(metadata)
        metadata["zarr_url"] = record["zarr_url"]
        metadata["storage_uri"] = record["storage_uri"]
        metadata["rebuild_promotion"] = record["rebuild_promotion"]
        record["metadata"] = metadata
        return record


    def overwrite_existing(self, candidate_id: str, job_id: Optional[str] = None, mode: str = "2d") -> Dict[str, Any]:
        clean_mode = self._normalize_mode(mode)

        job = self.latest_promotion_ready_job(candidate_id, job_id=job_id)
        compact = self.compact_staged_rebuild_job(job)

        prior_volume_id = str(compact.get("prior_volume_id") or "").strip()
        if not prior_volume_id:
            raise HTTPException(status_code=400, detail="Cannot overwrite existing managed output because prior_volume_id is missing.")

        staged_artifact = self.safe_staged_artifact_path(compact.get("output_path"))
        if not staged_artifact.exists():
            raise HTTPException(status_code=404, detail=f"Staged rebuild artifact is missing: {staged_artifact}")

        target_artifact = self.safe_managed_artifact_path(prior_volume_id, mode=clean_mode)
        if not target_artifact.exists():
            raise HTTPException(status_code=404, detail=f"Existing managed Zarr artifact is missing: {target_artifact}")

        backup_root = (self.staging_base / "_overwrite_backups" / clean_mode / str(compact.get("job_id") or uuid.uuid4())).resolve()
        backup_artifact = (backup_root / target_artifact.name).resolve()
        try:
            backup_artifact.relative_to(backup_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid overwrite backup path.") from exc

        backup_root.mkdir(parents=True, exist_ok=True)

        staged = job.get("staged_rebuild") if isinstance(job.get("staged_rebuild"), dict) else {}
        staged_volume = staged.get("volume") if isinstance(staged.get("volume"), dict) else job.get("volume")
        if not isinstance(staged_volume, dict):
            raise HTTPException(status_code=400, detail="Staged rebuild has no volume payload to promote.")

        volumes = load_volumes()
        if not isinstance(volumes, dict):
            raise HTTPException(status_code=500, detail="volumes.json is not a dictionary.")

        existing_volume_record = volumes.get(prior_volume_id)
        if not isinstance(existing_volume_record, dict):
            raise HTTPException(status_code=404, detail=f"Existing volume record not found: {prior_volume_id}")

        existing_display_name = (
            existing_volume_record.get("display_name")
            or existing_volume_record.get("filename")
            or staged_volume.get("display_name")
            or staged_volume.get("filename")
            or prior_volume_id
        )

        copied_sidecars: List[str] = []
        delete_result: Dict[str, Any] = {}
        backup_created = False

        try:
            if backup_artifact.exists():
                shutil.rmtree(backup_artifact)
            shutil.copytree(target_artifact, backup_artifact)
            backup_created = True

            for sidecar in target_artifact.parent.glob(target_artifact.name + ".*"):
                backup_sidecar = backup_root / sidecar.name
                if sidecar.is_dir():
                    if backup_sidecar.exists():
                        shutil.rmtree(backup_sidecar)
                    shutil.copytree(sidecar, backup_sidecar)
                else:
                    shutil.copy2(sidecar, backup_sidecar)

            shutil.rmtree(target_artifact)
            shutil.copytree(staged_artifact, target_artifact)

            # Replace sidecars for the managed artifact with the staged sidecars.
            for sidecar in target_artifact.parent.glob(target_artifact.name + ".*"):
                if sidecar.exists():
                    if sidecar.is_dir():
                        shutil.rmtree(sidecar)
                    else:
                        sidecar.unlink()
            copied_sidecars = self._copy_sidecars(staged_artifact, target_artifact)

            updated_volume_record = dict(staged_volume)
            updated_volume_record["id"] = prior_volume_id
            updated_volume_record["volume_id"] = prior_volume_id
            updated_volume_record["dataset_type"] = self._dataset_type_for_mode(clean_mode)
            updated_volume_record["display_name"] = existing_display_name
            updated_volume_record["filename"] = existing_volume_record.get("filename") or staged_volume.get("filename") or existing_display_name
            updated_volume_record["hidden"] = bool(existing_volume_record.get("hidden", True))
            updated_volume_record["zarr_url"] = f"/endrepo/managed/zarr/{clean_mode}/{prior_volume_id}.zarr"
            updated_volume_record["storage_uri"] = f"endrepo://managed/zarr/{clean_mode}/{prior_volume_id}.zarr"
            updated_volume_record["source_candidate_id"] = compact.get("source_candidate_id") or existing_volume_record.get("source_candidate_id")
            updated_volume_record["source_volume_id"] = prior_volume_id
            updated_volume_record["source_repository_id"] = compact.get("repository_id") or existing_volume_record.get("source_repository_id")
            updated_volume_record["line_id"] = compact.get("line_id") or existing_volume_record.get("line_id")
            updated_volume_record["representation_type"] = self._representation_type_for_mode(clean_mode)
            updated_volume_record["viewer_mode"] = clean_mode
            updated_volume_record["rebuild_promotion"] = {
                "type": "overwrite_existing",
                "promoted_at": self.utc_now(),
                "job_id": compact.get("job_id"),
                "artifact_id": compact.get("artifact_id"),
                "prior_volume_id": prior_volume_id,
                "source_candidate_id": compact.get("source_candidate_id"),
                "backup_artifact_path": str(backup_artifact),
            }

            metadata = updated_volume_record.get("metadata") if isinstance(updated_volume_record.get("metadata"), dict) else {}
            metadata = dict(metadata)
            metadata["zarr_url"] = updated_volume_record["zarr_url"]
            metadata["storage_uri"] = updated_volume_record["storage_uri"]
            metadata["rebuild_promotion"] = updated_volume_record["rebuild_promotion"]
            updated_volume_record["metadata"] = metadata

            volumes[prior_volume_id] = updated_volume_record
            save_volumes(volumes)

            delete_result = self._delete_staged_artifacts(staged_artifact)

            promoted_representation_id = (
                f"msi_repr:source_segy_{compact.get('source_candidate_id')}:zarr_{prior_volume_id}"
                if compact.get("source_candidate_id") else None
            )

            promoted_payload = {
                "promotion_type": "overwrite_existing",
                "promoted_at": self.utc_now(),
                "promoted_volume_id": prior_volume_id,
                "promoted_representation_id": promoted_representation_id,
                "promoted_display_name": existing_display_name,
                "display_name": existing_display_name,
                "zarr_url": updated_volume_record.get("zarr_url"),
                "storage_uri": updated_volume_record.get("storage_uri"),
                "output_path": str(target_artifact),
                "backup_artifact_path": str(backup_artifact),
                "backup_created": backup_created,
                "copied_sidecars": copied_sidecars,
                "delete_staged_result": delete_result,
                "existing_msi_identity_preserved": True,
                "source_candidate_id": compact.get("source_candidate_id"),
                "source_volume_id": prior_volume_id,
            }

            staged_updated = dict(staged)
            staged_updated["promotion_required"] = False
            staged_updated["promotion_options"] = []
            staged_updated["promoted"] = promoted_payload
            job["staged_rebuild"] = staged_updated
            job["status"] = "promoted"
            job["message"] = "Staged rebuild overwrote existing managed output. MSI representation identity was preserved."
            job["progress"] = 100
            job["progress_stage"] = "staged_rebuild_promoted_overwrite_existing"
            job["promotion_required"] = False
            job["promotion_options"] = []
            job["promoted_rebuild"] = promoted_payload
            job["promoted_volume_id"] = prior_volume_id
            job["promoted_representation_id"] = promoted_representation_id
            job["promoted_display_name"] = existing_display_name
            self._write_job(job)

            retired_related_jobs = self._retire_other_promotion_ready_jobs_for_candidate(
                candidate_id=str(compact.get("source_candidate_id") or candidate_id),
                promoted_job_id=str(compact.get("job_id") or ""),
                promoted_payload=promoted_payload,
            )
            job["retired_related_rebuild_jobs"] = retired_related_jobs
            self._write_job(job)

            return {
                "status": "overwritten_existing",
                "candidate_id": str(candidate_id),
                "job_id": compact.get("job_id"),
                "artifact_id": compact.get("artifact_id"),
                "promoted_volume_id": prior_volume_id,
                "promoted_representation_id": promoted_representation_id,
                "display_name": existing_display_name,
                "zarr_url": updated_volume_record.get("zarr_url"),
                "storage_uri": updated_volume_record.get("storage_uri"),
                "output_path": str(target_artifact),
                "backup_artifact_path": str(backup_artifact),
                "existing_msi_identity_preserved": True,
                "staged_artifact_removed": delete_result,
                "retired_related_rebuild_jobs": retired_related_jobs,
            }

        except Exception:
            # Best-effort restore of the original managed artifact if overwrite failed after backup.
            try:
                if backup_created and backup_artifact.exists():
                    if target_artifact.exists():
                        shutil.rmtree(target_artifact)
                    shutil.copytree(backup_artifact, target_artifact)
            except Exception:
                pass
            raise


    def save_as_new(self, candidate_id: str, display_name: str, job_id: Optional[str] = None, mode: str = "2d") -> Dict[str, Any]:
        clean_mode = self._normalize_mode(mode)
        clean_display_name = str(display_name or "").strip()
        if not clean_display_name:
            raise HTTPException(status_code=400, detail="A display name is required for Save as new.")

        job = self.latest_promotion_ready_job(candidate_id, job_id=job_id)
        compact = self.compact_staged_rebuild_job(job)
        staged_artifact = self.safe_staged_artifact_path(compact.get("output_path"))
        if not staged_artifact.exists():
            raise HTTPException(status_code=404, detail=f"Staged rebuild artifact is missing: {staged_artifact}")

        staged = job.get("staged_rebuild") if isinstance(job.get("staged_rebuild"), dict) else {}
        staged_volume = staged.get("volume") if isinstance(staged.get("volume"), dict) else job.get("volume")
        if not isinstance(staged_volume, dict):
            raise HTTPException(status_code=400, detail="Staged rebuild has no volume payload to promote.")

        new_volume_id = str(uuid.uuid4())
        target_artifact = self.safe_managed_artifact_path(new_volume_id, mode=clean_mode)
        target_artifact.parent.mkdir(parents=True, exist_ok=True)
        if target_artifact.exists():
            raise HTTPException(status_code=409, detail=f"Managed output already exists: {target_artifact}")

        copied_sidecars: List[str] = []
        try:
            shutil.copytree(staged_artifact, target_artifact)
            copied_sidecars = self._copy_sidecars(staged_artifact, target_artifact)

            volume_record = self._volume_record_for_save_as_new(
                staged_volume=staged_volume,
                compact=compact,
                new_volume_id=new_volume_id,
                display_name=clean_display_name,
                target_path=target_artifact,
                mode=clean_mode,
            )

            volumes = load_volumes()
            if not isinstance(volumes, dict):
                raise HTTPException(status_code=500, detail="volumes.json is not a dictionary.")
            if new_volume_id in volumes:
                raise HTTPException(status_code=409, detail=f"Volume id collision: {new_volume_id}")
            volumes[new_volume_id] = volume_record
            save_volumes(volumes)

            synthetic_segy_file_id = f"{compact.get('source_candidate_id') or 'unknown_source'}__rebuild_{new_volume_id}"
            msi_registration_payload = dict(volume_record)
            msi_registration_payload.update({
                "segy_file_id": synthetic_segy_file_id,
                "filename": clean_display_name,
                "display_name": clean_display_name,
                "volume_id": new_volume_id,
                "zarr_url": volume_record.get("zarr_url"),
                "storage_uri": volume_record.get("storage_uri"),
                "conversion_status": "ready",
                "dataset_type": self._dataset_type_for_mode(clean_mode),
                "candidate_kind": self._candidate_kind_for_mode(clean_mode),
                "candidate_role": "managed_rebuild_save_as_new",
                "repository_id": compact.get("repository_id"),
                "line_id": compact.get("line_id"),
                "job_id": compact.get("job_id"),
                "source_candidate_id": compact.get("source_candidate_id"),
                "source_volume_id": compact.get("prior_volume_id"),
                "rebuild_promotion": volume_record.get("rebuild_promotion"),
            })
            msi_result = register_converted_segy_file(
                msi_registration_payload,
                backend_root=self.backend_root,
            )
            if not msi_result.get("registered"):
                reason = msi_result.get("reason") or "unknown_msi_registration_failure"
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "Save-as-new promoted artifact but MSI registration failed.",
                        "reason": reason,
                        "msi_registration": msi_result,
                    },
                )

            promoted_representation_id = msi_result.get("representation_id")
            if not promoted_representation_id:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "MSI registration did not return a promoted representation id.",
                        "msi_registration": msi_result,
                    },
                )

            delete_result = self._delete_staged_artifacts(staged_artifact)

            promoted_payload = {
                "promotion_type": "save_as_new",
                "promoted_at": self.utc_now(),
                "new_volume_id": new_volume_id,
                "promoted_volume_id": new_volume_id,
                "promoted_representation_id": promoted_representation_id,
                "promoted_dataset_id": msi_result.get("dataset_id"),
                "display_name": clean_display_name,
                "zarr_url": volume_record.get("zarr_url"),
                "storage_uri": volume_record.get("storage_uri"),
                "output_path": str(target_artifact),
                "copied_sidecars": copied_sidecars,
                "delete_staged_result": delete_result,
                "existing_msi_unchanged": True,
                "source_candidate_id": compact.get("source_candidate_id"),
                "source_volume_id": compact.get("prior_volume_id"),
                "msi_registration": msi_result,
            }

            staged_updated = dict(staged)
            staged_updated["promotion_required"] = False
            staged_updated["promotion_options"] = []
            staged_updated["promoted"] = promoted_payload
            job["staged_rebuild"] = staged_updated
            job["status"] = "promoted"
            job["message"] = "Staged rebuild saved as new managed output. Existing MSI record was unchanged."
            job["progress"] = 100
            job["progress_stage"] = "staged_rebuild_promoted_save_as_new"
            job["promotion_required"] = False
            job["promotion_options"] = []
            job["promoted_rebuild"] = promoted_payload
            job["promoted_volume_id"] = new_volume_id
            job["promoted_representation_id"] = promoted_representation_id
            job["promoted_dataset_id"] = msi_result.get("dataset_id")
            job["promoted_display_name"] = clean_display_name
            self._write_job(job)
            retired_related_jobs = self._retire_other_promotion_ready_jobs_for_candidate(
                candidate_id=str(compact.get("source_candidate_id") or candidate_id),
                promoted_job_id=str(compact.get("job_id") or ""),
                promoted_payload=promoted_payload,
            )
            job["retired_related_rebuild_jobs"] = retired_related_jobs
            self._write_job(job)

            return {
                "status": "saved_as_new",
                "candidate_id": str(candidate_id),
                "job_id": compact.get("job_id"),
                "artifact_id": compact.get("artifact_id"),
                "new_volume_id": new_volume_id,
                "promoted_volume_id": new_volume_id,
                "promoted_representation_id": promoted_representation_id,
                "promoted_dataset_id": msi_result.get("dataset_id"),
                "display_name": clean_display_name,
                "zarr_url": volume_record.get("zarr_url"),
                "storage_uri": volume_record.get("storage_uri"),
                "output_path": str(target_artifact),
                "existing_msi_unchanged": True,
                "staged_artifact_removed": delete_result,
                "retired_related_rebuild_jobs": retired_related_jobs,
                "msi_registration": msi_result,
            }
        except Exception:
            # If registry write/promote fails, remove the partially copied managed artifact.
            try:
                if target_artifact.exists():
                    shutil.rmtree(target_artifact)
                for sidecar in target_artifact.parent.glob(target_artifact.name + ".*"):
                    if sidecar.exists():
                        if sidecar.is_dir():
                            shutil.rmtree(sidecar)
                        else:
                            sidecar.unlink()
            except Exception:
                pass
            raise
