from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.package_registry_service import list_segy_files, update_segy_file_conversion
from app.services.repository_registry_service import get_repository, list_repositories
from app.msi.repository import MSIRepository
from app.msi.registration_service import register_converted_segy_file
from app.services.source_intake_index_job_service import get_latest_source_intake_index_job
from app.services.source_intake_geometry_qaqc_service import load_geometry_qaqc_report
from app.services.source_repository_mode_service import filter_repositories_by_mode, repository_matches_mode
from app.services.source_intake_document_link_service import summarize_candidate_documents
from app.services.source_intake_document_assignment_service import summarize_candidate_document_assignments


_2D_KINDS = {"2d_line", "2d"}
_2D_ROLES = {"line_candidate", "line"}
_3D_KINDS = {"3d_volume", "3d"}
_3D_ROLES = {"volume_candidate", "volume"}
_REBUILDABLE_MANAGED_STATES = {"not_created", "failed", "stale", "deleted", "superseded", "unknown"}
_2D_SOURCE_STRUCTURES = {
    "single_isolated_line",
    "single_line_with_docs",
    "single_line_multi_version",
    "survey_with_line_folders",
    "survey_flat_lines",
}
_3D_SOURCE_STRUCTURES = {
    "single_3d_volume",
    "single_3d_volume_with_docs",
    "multi_version_3d_delivery",
}


def _repository_intent(repository_id: Any) -> tuple[str | None, str | None]:
    clean_repo_id = str(repository_id or "").strip()
    if not clean_repo_id:
        return None, None
    try:
        repo = get_repository(clean_repo_id)
    except Exception:
        return None, None
    if not repo:
        return None, None

    intended_use = _clean(repo.get("intended_use"))
    source_structure_type = _clean(repo.get("source_structure_type"))
    notes = str(repo.get("notes") or "").lower()

    if intended_use in {"2d_segy_intake", "2d"} or source_structure_type in _2D_SOURCE_STRUCTURES or "intended_use=2d_segy_intake" in notes:
        return "2d_line", "line_candidate"
    if intended_use in {"3d_segy_intake", "3d"} or source_structure_type in _3D_SOURCE_STRUCTURES or "intended_use=3d_segy_intake" in notes:
        return "3d_volume", "volume_candidate"
    return None, None


def _effective_candidate_classification(item: Dict[str, Any]) -> tuple[Any, Any, Any, Any, List[Any]]:
    raw_kind = item.get("candidate_kind")
    raw_role = item.get("candidate_role")
    repo_kind, repo_role = _repository_intent(item.get("repository_id"))
    reasons = list(item.get("classification_reasons") or [])

    if repo_kind and repo_role:
        if _clean(raw_kind) != repo_kind or _clean(raw_role) != repo_role:
            reasons.append(f"repository_intent_override={repo_kind}")
        return repo_kind, repo_role, "repository_intent", "high", reasons

    return raw_kind, raw_role, item.get("classification_source"), item.get("classification_confidence"), reasons


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _clean(value: Any) -> str:
    return _safe_str(value).lower()




def _parse_reset_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _record_timestamp(record):
    if not isinstance(record, dict):
        return None
    for key in [
        "created_at",
        "updated_at",
        "completed_at",
        "finished_at",
        "generated_at",
        "timestamp",
        "started_at",
        "submitted_at",
    ]:
        parsed = _parse_reset_timestamp(record.get(key))
        if parsed is not None:
            return parsed
    return None


def _source_reset_timestamp(source):
    if not isinstance(source, dict):
        return None

    explicit_reset_at = _parse_reset_timestamp(source.get("derived_state_reset_at"))
    if explicit_reset_at is not None:
        return explicit_reset_at

    conversion_state = _clean(source.get("conversion_state") or source.get("conversion_status"))
    conversion_reason = _safe_str(source.get("conversion_state_reason")).lower()
    authoritative = bool(source.get("conversion_state_authoritative"))

    # Compatibility path for source rows reset by the older Managed Data delete
    # cascade before derived_state_reset_at existed. Such rows are still
    # authoritative delete resets and must invalidate older Source Intake
    # derived state such as completed index jobs and geometry QAQC sidecars.
    if (
        authoritative
        and conversion_state in {"not_converted", "not_created", ""}
        and "delete reset" in conversion_reason
    ):
        return _parse_reset_timestamp(source.get("updated_at"))

    return None


def _is_record_valid_after_reset(source, record):
    reset_at = _source_reset_timestamp(source)
    if reset_at is None:
        return True

    record_at = _record_timestamp(record)
    if record_at is None:
        return False

    return record_at >= reset_at


def _source_reset_active(source):
    return _source_reset_timestamp(source) is not None

class SourceIntakeWorkbenchService:
    """
    Backend-owned Source Intake workbench row builder.

    This service consolidates the former load-sheet/candidate-review/conversion
    readiness view into one source-side row contract for the future Selection
    and Conversion table. It is read-only in Block 1: it does not approve,
    exclude, convert, register, load, unload, or delete data.
    """

    def __init__(self, msi_repo: MSIRepository | None = None) -> None:
        self.msi_repo = msi_repo or MSIRepository()

    def build_workbench(self, repository_id: str | None = None, mode: str | None = None) -> Dict[str, Any]:
        source_items: list[Dict[str, Any]] = []

        if repository_id:
            repo = get_repository(repository_id)
            if repo and not repository_matches_mode(repo, mode):
                source_items = []
            else:
                source_items = list_segy_files(repository_id=repository_id)
        elif mode:
            repositories = filter_repositories_by_mode(list_repositories(), mode)
            for repo in repositories:
                repo_id = repo.get("repository_id")
                if repo_id:
                    source_items.extend(list_segy_files(repository_id=str(repo_id)))
        else:
            source_items = list_segy_files(repository_id=repository_id)

        rows = [self._row_from_source(item) for item in source_items]
        if mode == "2d":
            rows = [row for row in rows if _safe_str(row.get("candidate_kind")).lower() in {"2d_line", "2d"} or _safe_str(row.get("candidate_role")).lower() in {"line_candidate", "line"}]
        elif mode == "3d":
            rows = [row for row in rows if _safe_str(row.get("candidate_kind")).lower() in {"3d_volume", "3d"} or _safe_str(row.get("candidate_role")).lower() in {"volume_candidate", "volume"}]

        rows.sort(key=lambda row: (_safe_str(row.get("filename")).lower(), _safe_str(row.get("candidate_id"))))

        summary = self._summary(rows)

        return {
            "repository_id": repository_id,
            "mode": mode,
            "row_count": len(rows),
            "summary": summary,
            "toolbar": {
                "selected_count": 0,
                "available_actions": [],
                "selection_model": "frontend_local",
            },
            "columns": [
                "select",
                "status",
                "type",
                "file",
                "survey",
                "line_or_volume",
                "qaqc",
                "conversion",
                "managed_output",
            ],
            "rows": rows,
        }

    def build_repository_workbench(self, repository_id: str, mode: str | None = None) -> Dict[str, Any]:
        repo = get_repository(repository_id)
        if not repo:
            raise FileNotFoundError(f"Repository not found: {repository_id}")
        if not repository_matches_mode(repo, mode):
            raise FileNotFoundError(f"Repository {repository_id} does not match requested mode={mode}")
        payload = self.build_workbench(repository_id=repository_id, mode=mode)
        payload["repository"] = repo
        return payload

    def _row_from_source(self, item: Dict[str, Any]) -> Dict[str, Any]:
        # Work on a copy so opportunistic reconciliation can safely enrich this
        # row contract without mutating the caller's in-memory list. Durable
        # registry/MSI updates are performed only inside _reconcile_completed_job.
        item = dict(item)
        candidate_id = item.get("segy_file_id") or item.get("source_segy_file_id") or item.get("candidate_id")
        (
            candidate_kind,
            candidate_role,
            classification_source,
            classification_confidence,
            classification_reasons,
        ) = _effective_candidate_classification(item)

        reconciliation = self._reconcile_completed_job(
            item,
            candidate_id=candidate_id,
            candidate_kind=candidate_kind,
            candidate_role=candidate_role,
        )
        if isinstance(reconciliation.get("item"), dict):
            item = reconciliation["item"]
            candidate_id = item.get("segy_file_id") or item.get("source_segy_file_id") or item.get("candidate_id")

        source_path_exists = self._source_path_exists(item)
        managed = self._managed_output(candidate_id)
        managed_state = managed.get("state", "unknown")
        conversion_state = self._conversion_state(item, managed_state)
        qaqc_state, qaqc_flags = self._qaqc_state(item, source_path_exists)
        geometry_qaqc = load_geometry_qaqc_report(candidate_id) if candidate_id else None
        if geometry_qaqc and not _is_record_valid_after_reset(item, geometry_qaqc):
            geometry_qaqc = None
        if geometry_qaqc:
            geometry_status = _clean(geometry_qaqc.get("status"))
            if geometry_status in {"passed", "review_required", "failed"}:
                qaqc_state = geometry_status
            geometry_summary = _safe_str(geometry_qaqc.get("summary"))
            if geometry_summary:
                severity = "warning" if qaqc_state == "review_required" else "error" if qaqc_state == "failed" else "info"
                qaqc_flags = list(qaqc_flags) + [{
                    "severity": severity,
                    "code": "geometry_qaqc",
                    "message": geometry_summary,
                }]
        try:
            document_summary = summarize_candidate_document_assignments(item, candidate_id=candidate_id)
        except Exception:
            document_summary = summarize_candidate_documents(item, candidate_id=candidate_id)

        # Source reset state invalidates derived artifacts such as conversion,
        # index, and geometry QAQC records. It must not erase backend-owned
        # supporting-document assignments from the Source Intake workbench row.
        # Document assignments are independently persisted in
        # source_intake_document_assignments.json and are still valid after a
        # conversion/delete reset.

        status = self._status(item, source_path_exists, managed_state, conversion_state, qaqc_state)
        actions = self._actions(
            candidate_id=candidate_id,
            candidate_kind=candidate_kind,
            candidate_role=candidate_role,
            source_path_exists=source_path_exists,
            managed_state=managed_state,
        )
        job = self._job_summary(item.get("job_id"))
        index_job = get_latest_source_intake_index_job(candidate_id)
        if index_job and not _is_record_valid_after_reset(item, index_job):
            index_job = None
        job_state = _clean(job.get("state"))
        active_conversion_job_states = {
            "queued",
            "pending",
            "submitted",
            "started",
            "running",
            "building",
            "converting",
            "in_progress",
            "reading_metadata",
            "validating_zarr",
            "promoting_output",
        }

        # A completed source-index preview job must not mask an active managed
        # SEG-Y -> Zarr conversion job. The row progress meter should show the
        # active conversion progress when conversion is running; source-index
        # progress is only the fallback when there is no active conversion job.
        if index_job and job_state not in active_conversion_job_states:
            job = {
                "job_id": index_job.get("job_id"),
                "job_type": index_job.get("job_type") or "source_intake_build_index",
                "state": index_job.get("status") or index_job.get("state"),
                "progress": index_job.get("progress"),
                "message": index_job.get("message") or index_job.get("error"),
                "dataset_id": index_job.get("dataset_id"),
            }

        return {
            "candidate_id": candidate_id,
            "repository_id": item.get("repository_id"),
            "package_id": item.get("package_id"),
            "line_id": item.get("line_id"),
            "source_segy_file_id": item.get("segy_file_id") or item.get("source_segy_file_id"),
            "filename": item.get("filename") or item.get("display_name"),
            "display_name": item.get("display_name") or item.get("filename"),
            "relative_path": item.get("relative_path"),
            "source_path_exists": source_path_exists,
            "selected": False,
            "status": status,
            "candidate_kind": candidate_kind,
            "candidate_role": candidate_role,
            "classification_source": classification_source,
            "classification_confidence": classification_confidence,
            "classification_reasons": classification_reasons,
            "review_state": item.get("review_state") or self._default_review_state(candidate_kind, candidate_role),
            "qaqc_state": qaqc_state,
            "qaqc_flags": qaqc_flags,
            "geometry_qaqc": geometry_qaqc,
            "conversion_state": conversion_state,
            "managed_state": managed_state,
            "survey_name": item.get("survey_name"),
            "line_name": item.get("line_name"),
            "volume_name": item.get("volume_name"),
            "processing_stage": item.get("processing_stage"),
            "processing_version": item.get("processing_version"),
            "evidence_status": document_summary.get("evidence_status") or item.get("evidence_status") or "unknown",
            "document_count": document_summary.get("document_count"),
            "supporting_document_count": document_summary.get("supporting_document_count"),
            "supporting_documents": document_summary.get("supporting_documents") or [],
            "actions": actions,
            "job": job,
            "managed_output": managed,
            "source": item,
            "reconciliation": reconciliation,
        }


    def _reconcile_completed_job(
        self,
        item: Dict[str, Any],
        *,
        candidate_id: Any,
        candidate_kind: Any,
        candidate_role: Any,
    ) -> Dict[str, Any]:
        """
        Reconcile a completed conversion job back into the source registry and MSI.

        This is intentionally idempotent. It does not start conversion and it does
        not create a second Zarr output. It only observes a completed job record,
        records the completed artifact against the source SEG-Y row, and upserts
        the corresponding MSI dataset/representation.
        """
        clean_candidate_id = _safe_str(candidate_id)

        authoritative_reset = bool(item.get("conversion_state_authoritative"))
        conversion_status = _clean(item.get("conversion_status"))
        if authoritative_reset and conversion_status in {"not_converted", "deleted", "reset", "not_built"}:
            return {
                "attempted": False,
                "reason": "source_conversion_state_authoritatively_reset",
                "conversion_status": conversion_status,
            }

        clean_job_id = _safe_str(item.get("job_id"))
        if not clean_candidate_id or not clean_job_id:
            return {"attempted": False, "reason": "missing_candidate_or_job"}

        job = self._job_payload(clean_job_id)
        if not job:
            return {"attempted": False, "reason": "job_not_found", "job_id": clean_job_id}

        job_state = _clean(job.get("status") or job.get("state"))
        if job_state not in {"complete", "completed", "success", "succeeded"}:
            return {"attempted": False, "reason": "job_not_complete", "job_id": clean_job_id, "job_state": job_state}

        existing_managed = self._managed_output(clean_candidate_id)
        if existing_managed.get("viewer_ready") is True:
            return {
                "attempted": False,
                "reason": "already_viewer_ready",
                "job_id": clean_job_id,
                "managed_output": existing_managed,
            }

        volume = job.get("volume") if isinstance(job.get("volume"), dict) else {}
        volume_id = _safe_str(item.get("volume_id") or job.get("file_id") or volume.get("id") or volume.get("volume_id"))
        zarr_url = _safe_str(item.get("zarr_url") or job.get("zarr_url") or volume.get("zarr_url"))
        storage_uri = _safe_str(item.get("storage_uri") or job.get("storage_uri") or volume.get("storage_uri"))

        if not zarr_url:
            zarr_url = self._zarr_url_from_output_path(job.get("output_path"))
        if not storage_uri:
            storage_uri = self._storage_uri_from_zarr_url(zarr_url)

        if not volume_id or not zarr_url:
            return {
                "attempted": True,
                "registered": False,
                "reason": "completed_job_missing_artifact_identity",
                "job_id": clean_job_id,
                "volume_id": volume_id or None,
                "zarr_url": zarr_url or None,
            }

        dataset_type = _safe_str(
            item.get("dataset_type")
            or job.get("expected_dataset_type")
            or volume.get("dataset_type")
            or candidate_kind
        )

        reconciled = dict(item)
        reconciled.update(
            {
                "segy_file_id": clean_candidate_id,
                "source_segy_file_id": clean_candidate_id,
                "candidate_kind": candidate_kind,
                "candidate_role": candidate_role,
                "dataset_type": dataset_type,
                "conversion_status": "converted",
                "volume_id": volume_id,
                "job_id": clean_job_id,
                "zarr_url": zarr_url,
                "storage_uri": storage_uri,
                "conversion_error": None,
                "conversion_state_reason": "Reconciled from completed conversion job.",
            }
        )

        try:
            updated = update_segy_file_conversion(
                clean_candidate_id,
                conversion_status="converted",
                volume_id=volume_id,
                job_id=clean_job_id,
                zarr_url=zarr_url,
                storage_uri=storage_uri,
                clear_error=True,
                conversion_state_reason="Reconciled from completed conversion job.",
                conversion_state_authoritative=True,
                converted_at=job.get("updated_at") or job.get("completed_at"),
            )
            if isinstance(updated, dict):
                updated = dict(updated)
                updated.update(
                    {
                        "candidate_kind": candidate_kind,
                        "candidate_role": candidate_role,
                        "dataset_type": dataset_type,
                        "storage_uri": storage_uri,
                    }
                )
                reconciled.update(updated)
        except Exception as exc:
            return {
                "attempted": True,
                "registered": False,
                "reason": "source_registry_update_failed",
                "job_id": clean_job_id,
                "error": str(exc),
                "item": reconciled,
            }

        try:
            registration = register_converted_segy_file(reconciled)
        except Exception as exc:
            return {
                "attempted": True,
                "registered": False,
                "reason": "msi_registration_exception",
                "job_id": clean_job_id,
                "error": str(exc),
                "item": reconciled,
            }

        return {
            "attempted": True,
            "registered": bool(registration.get("registered")),
            "reason": registration.get("reason"),
            "job_id": clean_job_id,
            "volume_id": volume_id,
            "zarr_url": zarr_url,
            "storage_uri": storage_uri,
            "registration": registration,
            "item": reconciled,
        }

    @staticmethod
    def _zarr_url_from_output_path(value: Any) -> str:
        text = _safe_str(value)
        if not text:
            return ""
        marker = "/End_Seismic_Data_Repository/"
        if marker in text:
            return "/endrepo/" + text.split(marker, 1)[1].lstrip("/")
        path = Path(text)
        name = path.name
        if name.endswith(".zarr"):
            parts = [p for p in path.parts]
            if "managed" in parts and "zarr" in parts:
                try:
                    idx = parts.index("managed")
                    return "/endrepo/" + "/".join(parts[idx:])
                except Exception:
                    return ""
        return ""

    @staticmethod
    def _storage_uri_from_zarr_url(zarr_url: Any) -> str:
        text = _safe_str(zarr_url)
        if text.startswith("/endrepo/"):
            return "endrepo://" + text.replace("/endrepo/", "", 1)
        if text.startswith("/data/zarr/"):
            return "local://zarr/" + text.replace("/data/zarr/", "", 1)
        return ""

    @staticmethod
    def _job_payload(job_id: Any) -> Dict[str, Any] | None:
        clean_job_id = _safe_str(job_id)
        if not clean_job_id:
            return None
        jobs_dir = Path(__file__).resolve().parents[2] / "data" / "jobs"
        path = jobs_dir / f"{clean_job_id}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _source_path_exists(self, item: Dict[str, Any]) -> Optional[bool]:
        value = item.get("source_path_exists")
        if isinstance(value, bool):
            return value

        for key in ("source_path", "absolute_path", "path", "file_path"):
            raw = item.get(key)
            if raw:
                try:
                    p = Path(str(raw)).expanduser()
                    return p.exists() and p.is_file()
                except Exception:
                    return None

        repo_id = item.get("repository_id")
        relative_path = item.get("relative_path")
        if repo_id and relative_path:
            try:
                repo = get_repository(str(repo_id))
                root_path = repo.get("root_path") if repo else None
                if root_path:
                    p = Path(str(root_path)).expanduser() / str(relative_path)
                    return p.exists() and p.is_file()
            except Exception:
                return None

        return None

    def _managed_output(self, candidate_id: Any) -> Dict[str, Any]:
        clean_id = _safe_str(candidate_id)
        if not clean_id:
            return self._empty_managed_output("unknown")

        dataset_id = f"source_segy:{clean_id}"
        dataset = self.msi_repo.get_dataset(dataset_id)
        if not dataset:
            return self._empty_managed_output("not_created")

        representations = self.msi_repo.list_representations(dataset_id)
        if not representations:
            return self._empty_managed_output("not_created", dataset_id=dataset_id)

        preferred = sorted(
            representations,
            key=lambda rep: (
                1 if getattr(rep, "is_preferred", False) else 0,
                1 if getattr(rep, "viewer_ready", False) else 0,
                str(getattr(rep, "updated_at", "") or ""),
            ),
            reverse=True,
        )[0]

        artifact = getattr(preferred, "artifact_summary", {}) or {}
        lifecycle_state = _safe_str(getattr(preferred, "lifecycle_state", None)) or "unknown"
        viewer_ready = bool(getattr(preferred, "viewer_ready", False))
        state = "viewer_ready" if viewer_ready and lifecycle_state == "viewer_ready" else lifecycle_state

        return {
            "state": state,
            "dataset_id": dataset_id,
            "representation_id": getattr(preferred, "representation_id", None),
            "viewer_ready": viewer_ready,
            "viewer_mode": getattr(preferred, "viewer_mode", None),
            "representation_type": getattr(preferred, "representation_type", None),
            "storage_uri": getattr(preferred, "storage_uri", None),
            "zarr_url": artifact.get("zarr_url"),
            "physical_volume_id": artifact.get("volume_id"),
            "display_name": getattr(dataset, "display_name", None),
            "is_preferred": bool(getattr(preferred, "is_preferred", False)),
            "lifecycle_state": lifecycle_state,
        }

    @staticmethod
    def _empty_managed_output(state: str, dataset_id: str | None = None) -> Dict[str, Any]:
        return {
            "state": state,
            "dataset_id": dataset_id,
            "representation_id": None,
            "viewer_ready": False,
            "viewer_mode": None,
            "representation_type": None,
            "storage_uri": None,
            "zarr_url": None,
            "physical_volume_id": None,
            "display_name": None,
            "is_preferred": False,
            "lifecycle_state": state,
        }

    @staticmethod
    def _default_review_state(candidate_kind: Any, candidate_role: Any) -> str:
        kind = _clean(candidate_kind)
        role = _clean(candidate_role)
        if kind in {"2d_line", "3d_volume", "supporting_document"} or role in {"line_candidate", "volume_candidate"}:
            return "classified"
        return "review_required"

    @staticmethod
    def _conversion_state(item: Dict[str, Any], managed_state: str) -> str:
        raw = _clean(item.get("conversion_status"))
        if raw:
            if raw in {"converted", "ready", "viewer_ready"}:
                return "complete"
            if raw in {"queued", "converting", "building", "running"}:
                return "building"
            if raw in {"failed", "error"}:
                return "failed"
            return raw
        if managed_state == "viewer_ready":
            return "complete"
        if managed_state in {"failed", "stale", "deleted"}:
            return managed_state
        return "not_built"

    @staticmethod
    def _qaqc_state(item: Dict[str, Any], source_path_exists: Optional[bool]) -> tuple[str, List[Dict[str, Any]]]:
        flags: List[Dict[str, Any]] = []
        if source_path_exists is False:
            flags.append({"severity": "error", "code": "source_missing", "message": "Source file is missing."})
        elif source_path_exists is None:
            flags.append({"severity": "warning", "code": "source_unverified", "message": "Source path could not be verified."})

        kind = _clean(item.get("candidate_kind"))
        role = _clean(item.get("candidate_role"))
        if not kind and not role:
            flags.append({"severity": "warning", "code": "classification_missing", "message": "Candidate classification is missing."})

        if any(flag["severity"] == "error" for flag in flags):
            return "blocked", flags
        if flags:
            return "review_required", flags
        return "ready", flags

    @staticmethod
    def _status(
        item: Dict[str, Any],
        source_path_exists: Optional[bool],
        managed_state: str,
        conversion_state: str,
        qaqc_state: str,
    ) -> Dict[str, Any]:
        if source_path_exists is False:
            return {"state": "blocked", "label": "Source Missing", "reason": "Source file is missing."}
        if managed_state == "viewer_ready":
            return {"state": "managed", "label": "Viewer Ready", "reason": "Managed representation is viewer-ready."}
        if conversion_state == "building":
            return {"state": "building", "label": "Building", "reason": "Conversion job is running."}
        if conversion_state == "complete":
            return {"state": "complete", "label": "Conversion Complete", "reason": "Conversion completed; managed output is not viewer-ready yet."}
        if conversion_state == "failed" or managed_state == "failed":
            return {"state": "failed", "label": "Failed", "reason": item.get("conversion_error") or item.get("conversion_state_reason")}
        if qaqc_state == "review_required":
            return {"state": "review_required", "label": "Review Required", "reason": "One or more QAQC checks need review."}
        if qaqc_state == "blocked":
            return {"state": "blocked", "label": "Blocked", "reason": "QAQC blocks conversion."}
        return {"state": "ready", "label": "Ready", "reason": "Ready for selection and conversion."}

    def _actions(
        self,
        *,
        candidate_id: Any,
        candidate_kind: Any,
        candidate_role: Any,
        source_path_exists: Optional[bool],
        managed_state: str,
    ) -> Dict[str, Dict[str, Any]]:
        clean_id = _safe_str(candidate_id)
        kind = _clean(candidate_kind)
        role = _clean(candidate_role)
        source_ok = source_path_exists is True
        rebuildable = managed_state in _REBUILDABLE_MANAGED_STATES

        is_2d = kind in _2D_KINDS or role in _2D_ROLES
        is_3d = kind in _3D_KINDS or role in _3D_ROLES

        build_2d_enabled = bool(clean_id and source_ok and is_2d and rebuildable)
        build_3d_enabled = bool(clean_id and source_ok and is_3d and rebuildable)
        build_index_enabled = bool(clean_id and source_ok and (is_2d or is_3d or kind == "review_required"))

        return {
            "approve": {"enabled": False, "url": None, "reason": "Approve action is not implemented in this block."},
            "exclude": {"enabled": False, "url": None, "reason": "Exclude action is not implemented in this block."},
            "build_2d_line": {
                "enabled": build_2d_enabled,
                "url": f"/api/source-intake/candidates/{clean_id}/build-2d-line" if build_2d_enabled else None,
                "reason": None if build_2d_enabled else self._build_disabled_reason("2d_line", source_ok, is_2d, managed_state),
            },
            "build_3d_volume": {
                "enabled": build_3d_enabled,
                "url": f"/api/source-intake/candidates/{clean_id}/build-3d-volume" if build_3d_enabled else None,
                "reason": None if build_3d_enabled else self._build_disabled_reason("3d_volume", source_ok, is_3d, managed_state),
            },
            "geometry_qaqc": {
                "enabled": bool(clean_id and source_ok),
                "url": f"/api/source-intake/candidates/{clean_id}/geometry-qaqc/run" if clean_id and source_ok else None,
                "reason": None if clean_id and source_ok else "Geometry QAQC requires an available source file.",
            },
            "build_index": {
                "enabled": build_index_enabled,
                "url": f"/api/source-intake/candidates/{clean_id}/build-index" if build_index_enabled else None,
                "reason": None if build_index_enabled else "Index build is unavailable for this row state.",
            },
            "rebuild": {
                "enabled": build_2d_enabled or build_3d_enabled,
                "url": None,
                "reason": None if (build_2d_enabled or build_3d_enabled) else "Rebuild is unavailable for this row state.",
            },
        }

    @staticmethod
    def _build_disabled_reason(target: str, source_ok: bool, compatible: bool, managed_state: str) -> str:
        if not source_ok:
            return "Source file is not available."
        if not compatible:
            return f"Candidate is not compatible with {target}."
        if managed_state == "viewer_ready":
            return "Managed representation is already viewer-ready."
        return "Action is not available for this row state."

    def _job_summary(self, job_id: Any) -> Dict[str, Any]:
        clean_job_id = _safe_str(job_id)
        if not clean_job_id:
            return {"job_id": None, "state": None, "progress": None, "message": None}

        payload = self._job_payload(clean_job_id)
        if payload is None:
            return {"job_id": clean_job_id, "state": "unknown", "progress": None, "message": None}

        return {
            "job_id": clean_job_id,
            "state": payload.get("status") or payload.get("state"),
            "progress": payload.get("progress"),
            "message": payload.get("message") or payload.get("error"),
        }

    @staticmethod
    def _summary(rows: List[Dict[str, Any]]) -> Dict[str, int]:
        result = {
            "total": len(rows),
            "ready": 0,
            "review_required": 0,
            "building": 0,
            "complete": 0,
            "managed": 0,
            "failed": 0,
            "blocked": 0,
            "two_d": 0,
            "three_d": 0,
        }
        for row in rows:
            state = _clean((row.get("status") or {}).get("state"))
            if state in result:
                result[state] += 1
            kind = _clean(row.get("candidate_kind"))
            role = _clean(row.get("candidate_role"))
            if kind in _2D_KINDS or role in _2D_ROLES:
                result["two_d"] += 1
            if kind in _3D_KINDS or role in _3D_ROLES:
                result["three_d"] += 1
        return result
