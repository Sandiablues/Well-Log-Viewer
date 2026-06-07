from __future__ import annotations

import json
import shutil
import uuid
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.repository_registry_service import (
    REGISTRY_DIR,
    add_repository,
    get_repository,
    list_repositories,
)
from app.services.package_registry_service import (
    list_lines,
    list_packages,
    list_segy_files,
)
from app.services.repository_load_sheet_service import build_repository_load_sheet
from app.services.source_staging_service import (
    stage_repository_selection,
    submit_staged_source_items,
)
from app.services.external_registry_submitted_view_service import build_submitted_external_registry_view
from app.services.managed_representation_request_service import ManagedRepresentationRequestService
from app.services.source_intake_repository_summary_service import build_repository_scan_summary, decorate_repository
from app.services.source_intake_index_service import (
    build_source_intake_candidate_index as build_source_intake_candidate_index_service,
    build_source_intake_indexed_preview_viewer_source,
)
from app.services.source_intake_index_job_service import (
    list_source_intake_index_jobs,
    queue_source_intake_index_job,
)
from app.services.source_repository_mode_service import (
    apply_mode_defaults_to_payload,
    encode_repository_notes,
    filter_repositories_by_mode,
    repository_matches_mode,
)
from app.services.manual_upload_source_intake_metadata_service import (
    decorate_manual_upload_repository,
    decorate_manual_upload_repositories,
)
from app.services.source_intake_document_link_service import (
    get_candidate_document_bundle,
    get_package_document_bundle,
    summarize_repository_document_links,
)
from app.services.source_intake_document_assignment_service import (
    assign_source_intake_documents,
    get_candidate_document_assignment_review,
)
from app.services.rebuild_promotion_service import RebuildPromotionService


router = APIRouter(prefix="/api/source-intake", tags=["source-intake"])


def _read_source_intake_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _source_intake_rows_from_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("documents", "attachments", "assignments", "items", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        if all(isinstance(value, dict) for value in payload.values()):
            return [row for row in payload.values() if isinstance(row, dict)]
    return []


_managed_representation_request_service = ManagedRepresentationRequestService()
_rebuild_promotion_service = RebuildPromotionService()


def _safe_count(items: List[Dict[str, Any]]) -> int:
    return len(items) if isinstance(items, list) else 0


def _repository_counts(repository_id: str) -> Dict[str, Any]:
    packages = list_packages(repository_id=repository_id)
    lines = list_lines(repository_id=repository_id)
    segy_files = list_segy_files(repository_id=repository_id)

    review_required_count = sum(
        1
        for item in segy_files
        if str(item.get("candidate_kind") or "").lower() == "review_required"
        or str(item.get("candidate_role") or "").lower() == "review_required"
    )

    submitted_count = sum(
        1
        for item in segy_files
        if str(item.get("conversion_status") or "").lower() in {"queued", "converting", "converted", "ready"}
    )

    return {
        "package_count": _safe_count(packages),
        "line_count": _safe_count(lines),
        "candidate_count": _safe_count(segy_files),
        "review_required_count": review_required_count,
        "approved_count": None,
        "submitted_count": submitted_count,
    }


def _normalize_repository(repo: Dict[str, Any]) -> Dict[str, Any]:
    # MANUAL_UPLOAD_STAGING_2: promote manual-upload mode metadata before route serialization.
    repo = decorate_manual_upload_repository(repo)
    repository_id = repo.get("repository_id")
    counts = _repository_counts(str(repository_id)) if repository_id else {}
    return {
        "repository_id": repository_id,
        "name": repo.get("name"),
        "root_path": repo.get("root_path"),
        "repository_type": repo.get("repository_type"),
        "read_only": repo.get("read_only"),
        "status": repo.get("status"),
        "source_structure_type": repo.get("source_structure_type"),
        "intended_use": repo.get("intended_use"),
        "notes": repo.get("notes"),
        "created_at": repo.get("created_at"),
        "updated_at": repo.get("updated_at"),
        "last_scan_at": repo.get("last_scan_at") or repo.get("updated_at"),
        "scan_status": repo.get("scan_status"),
        **counts,
        "source": repo,
    }


def _resolve_source_path_exists(item: Dict[str, Any]) -> Optional[bool]:
    value = item.get("source_path_exists")
    if isinstance(value, bool):
        return value

    source_path = item.get("source_path") or item.get("absolute_path") or item.get("path")
    if source_path:
        try:
            return Path(str(source_path)).expanduser().exists()
        except Exception:
            return None

    repo = get_repository(str(item.get("repository_id") or "")) if item.get("repository_id") else None
    rel = item.get("relative_path")
    if repo and rel:
        root = repo.get("root_path")
        if root:
            try:
                return (Path(str(root)).expanduser() / str(rel)).exists()
            except Exception:
                return None
    return None


def _managed_state(item: Dict[str, Any]) -> str:
    status = str(item.get("conversion_status") or "not_created").lower()
    if status in {"converted", "ready", "viewer_ready"}:
        return "viewer_ready"
    if status in {"queued", "converting", "building"}:
        return "building"
    if status in {"failed", "error"}:
        return "failed"
    if status in {"deleted", "stale", "superseded"}:
        return status
    return "not_created"


def _candidate_identifier(item: Dict[str, Any]) -> Optional[str]:
    for key in ("candidate_id", "source_segy_file_id", "segy_file_id"):
        value = item.get(key)
        if value:
            return str(value)
    source = item.get("source")
    if isinstance(source, dict):
        for key in ("candidate_id", "source_segy_file_id", "segy_file_id"):
            value = source.get(key)
            if value:
                return str(value)
    return None


def _clean_candidate_token(item: Dict[str, Any], key: str) -> str:
    value = item.get(key)
    if value is None and isinstance(item.get("source"), dict):
        value = item["source"].get(key)
    return str(value or "").strip().lower()


def _is_2d_source_intake_row(item: Dict[str, Any]) -> bool:
    kind = _clean_candidate_token(item, "candidate_kind")
    role = _clean_candidate_token(item, "candidate_role")
    return kind == "2d_line" or role == "line_candidate" or "2d" in kind or "2d" in role


def _is_3d_source_intake_row(item: Dict[str, Any]) -> bool:
    kind = _clean_candidate_token(item, "candidate_kind")
    role = _clean_candidate_token(item, "candidate_role")
    return kind == "3d_volume" or role == "volume_candidate" or "3d" in kind or "3d" in role


def _has_managed_output(item: Dict[str, Any]) -> bool:
    managed = item.get("managed_output")
    if isinstance(managed, dict):
        if managed.get("viewer_ready") is True:
            return True
        for key in ("state", "status", "conversion_status", "managed_state"):
            state = str(managed.get(key) or "").strip().lower()
            if state in {"viewer_ready", "ready", "complete", "converted", "available"}:
                return True
        for key in ("volume_id", "dataset_id", "representation_id", "zarr_url", "storage_uri", "path"):
            if managed.get(key):
                return True

    state = str(item.get("managed_state") or item.get("conversion_state") or item.get("conversion_status") or "").strip().lower()
    if state in {"viewer_ready", "ready", "complete", "converted"}:
        return True

    return bool(item.get("volume_id") or item.get("zarr_url"))


def _action_contract(
    enabled: bool,
    reason: str,
    *,
    mode: Optional[str] = None,
    target: Optional[str] = None,
    url: Optional[str] = None,
    method: str = "POST",
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "enabled": bool(enabled),
        "available": bool(enabled),
        "reason": reason,
        "method": method,
    }
    if mode:
        payload["mode"] = mode
    if target:
        payload["target"] = target
    if url:
        payload["url"] = url
    return payload


def _backend_owned_rebuild_action(item: Dict[str, Any]) -> Dict[str, Any]:
    candidate_id = _candidate_identifier(item)
    source_exists = _resolve_source_path_exists(item)

    if _is_2d_source_intake_row(item):
        target = "managed_2d_line_zarr"
        if source_exists is False:
            return _action_contract(
                False,
                "Source SEG-Y path is missing; rebuild cannot be started.",
                mode="2d",
                target=target,
            )
        if not _has_managed_output(item):
            return _action_contract(
                False,
                "No managed 2D output exists yet. Use Build 2D Line first.",
                mode="2d",
                target=target,
            )
        if not candidate_id:
            return _action_contract(
                False,
                "Source Intake candidate id is missing; rebuild cannot be started.",
                mode="2d",
                target=target,
            )
        return _action_contract(
            True,
            "Managed 2D output exists; staged SEG-Y to Zarr rebuild is available.",
            mode="2d",
            target=target,
            url=f"/api/source-intake/candidates/{candidate_id}/rebuild",
        )

    if _is_3d_source_intake_row(item):
        target = "managed_3d_volume_zarr"
        if source_exists is False:
            return _action_contract(
                False,
                "Source SEG-Y path is missing; rebuild cannot be started.",
                mode="3d",
                target=target,
            )
        if not _has_managed_output(item):
            return _action_contract(
                False,
                "No managed 3D output exists yet. Use Build 3D Volume first.",
                mode="3d",
                target=target,
            )
        if not candidate_id:
            return _action_contract(
                False,
                "Source Intake candidate id is missing; rebuild cannot be started.",
                mode="3d",
                target=target,
            )
        return _action_contract(
            True,
            "Managed 3D output exists; staged SEG-Y to Zarr rebuild is available.",
            mode="3d",
            target=target,
            url=f"/api/source-intake/candidates/{candidate_id}/rebuild",
        )

    return _action_contract(False, "Unknown candidate type; rebuild is not available.")


def _looks_like_source_intake_row(value: Dict[str, Any]) -> bool:
    return bool(
        _candidate_identifier(value)
        and (value.get("candidate_kind") or value.get("candidate_role") or isinstance(value.get("source"), dict))
    )


def _apply_backend_owned_rebuild_actions(payload: Dict[str, Any]) -> Dict[str, Any]:
    staged_rebuilds_by_candidate = _latest_staged_rebuild_jobs_by_candidate()

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        if _looks_like_source_intake_row(value):
            actions = value.get("actions") if isinstance(value.get("actions"), dict) else {}
            actions = dict(actions)
            actions["rebuild"] = _backend_owned_rebuild_action(value)
            value["actions"] = actions

            value["rebuild_state"] = _rebuild_state_from_staged_result(None)
            staged_rebuild = _latest_staged_rebuild_result_for_row(value, staged_rebuilds_by_candidate)
            if staged_rebuild:
                value["staged_rebuild_result"] = staged_rebuild
                value["rebuild_state"] = _rebuild_state_from_staged_result(staged_rebuild)
                value["promotion_required"] = bool(staged_rebuild.get("promotion_required"))
                value["promotion_options"] = staged_rebuild.get("promotion_options") or []
        for child in value.values():
            if isinstance(child, (dict, list)):
                visit(child)

    if isinstance(payload, dict):
        visit(payload)
    return payload


def _resolve_rebuild_source_path(candidate: Dict[str, Any]) -> Path:
    for key in ("source_path", "absolute_path", "path", "file_path"):
        raw = candidate.get(key)
        if raw:
            path = Path(str(raw)).expanduser()
            if path.exists() and path.is_file():
                return path

    repository_id = candidate.get("repository_id")
    relative_path = candidate.get("relative_path")
    if repository_id and relative_path:
        repo = get_repository(str(repository_id))
        root_path = repo.get("root_path") if repo else None
        if root_path:
            path = (Path(str(root_path)).expanduser() / str(relative_path)).resolve()
            if path.exists() and path.is_file():
                return path

    raise HTTPException(status_code=400, detail="Could not resolve source SEG-Y path for staged rebuild.")



def _same_resolved_path(left: Any, right: Any) -> bool:
    left_text = str(left or "").strip()
    right_text = str(right or "").strip()
    if not left_text or not right_text:
        return False
    try:
        return Path(left_text).expanduser().resolve() == Path(right_text).expanduser().resolve()
    except Exception:
        return left_text == right_text


def _job_volume_id(job: Dict[str, Any]) -> str:
    for key in ("file_id", "volume_id", "promoted_volume_id"):
        value = str(job.get(key) or "").strip()
        if value:
            return value
    volume = job.get("volume") if isinstance(job.get("volume"), dict) else {}
    return str(volume.get("id") or "").strip()


def _job_has_valid_3d_geometry(job: Dict[str, Any]) -> bool:
    if not isinstance(job, dict):
        return False
    if str(job.get("expected_dataset_type") or "").strip().lower() != "3d_volume":
        return False
    if bool(job.get("staged_rebuild")):
        return False
    geometry_override = job.get("geometry_override")
    if not isinstance(geometry_override, dict):
        return False
    if not geometry_override.get("inline_byte") or not geometry_override.get("crossline_byte"):
        return False
    if not geometry_override.get("inline_count") or not geometry_override.get("crossline_count"):
        return False
    return True


def _load_json_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _find_prior_3d_rebuild_geometry(
    *,
    candidate: Dict[str, Any],
    prior_volume_id: str,
    source_path: Path,
    job_service: Any,
) -> Optional[Dict[str, Any]]:
    """
    Rebuild must preserve the validated geometry used by the original fast
    Build 3D Volume conversion. Without this, the converter re-inferrs geometry
    and can take the slow/wrong path, e.g. thousands of false inlines.
    """
    jobs_dir = getattr(job_service, "jobs_dir", None)
    if not jobs_dir:
        return None

    jobs_path = Path(jobs_dir)
    if not jobs_path.exists():
        return None

    candidate_filename = str(candidate.get("filename") or candidate.get("display_name") or "").strip()
    prior_id = str(prior_volume_id or "").strip()

    strong_matches: List[Dict[str, Any]] = []
    path_matches: List[Dict[str, Any]] = []

    for job_path in sorted(jobs_path.glob("*.json"), key=lambda value: value.stat().st_mtime, reverse=True):
        job = _load_json_file(job_path)
        if not job or not _job_has_valid_3d_geometry(job):
            continue

        job_volume_id = _job_volume_id(job)
        output_path = str(job.get("output_path") or "")
        volume = job.get("volume") if isinstance(job.get("volume"), dict) else {}
        volume_id = str(volume.get("id") or "").strip()
        input_matches = _same_resolved_path(job.get("input_path"), source_path)
        filename_matches = bool(candidate_filename and candidate_filename == str(job.get("filename") or "").strip())

        if prior_id and (job_volume_id == prior_id or volume_id == prior_id or prior_id in output_path):
            strong_matches.append({"job": job, "match_reason": "prior_volume_id"})
            continue

        if input_matches and filename_matches:
            path_matches.append({"job": job, "match_reason": "input_path_and_filename"})
        elif input_matches:
            path_matches.append({"job": job, "match_reason": "input_path"})

    selected = strong_matches[0] if strong_matches else (path_matches[0] if path_matches else None)
    if not selected:
        return None

    job = selected["job"]
    geometry_override = job.get("geometry_override") if isinstance(job.get("geometry_override"), dict) else None
    if not geometry_override:
        return None

    geometry_qaqc = job.get("geometry_qaqc") if isinstance(job.get("geometry_qaqc"), dict) else None
    return {
        "geometry_override": geometry_override,
        "geometry_qaqc": geometry_qaqc,
        "source_job_id": job.get("job_id"),
        "source_volume_id": _job_volume_id(job),
        "match_reason": selected["match_reason"],
    }


def _queue_staged_rebuild(candidate_id: str, *, expected_dataset_type: str, mode: str, target: str) -> Dict[str, Any]:
    clean_mode = str(mode or "").strip().lower()
    clean_dataset_type = str(expected_dataset_type or "").strip().lower()
    if clean_mode not in {"2d", "3d"}:
        raise HTTPException(status_code=400, detail=f"Unsupported staged rebuild mode: {mode!r}")
    if clean_dataset_type not in {"2d_line", "3d_volume"}:
        raise HTTPException(status_code=400, detail=f"Unsupported staged rebuild dataset type: {expected_dataset_type!r}")
    expected_mode = "3d" if clean_dataset_type == "3d_volume" else "2d"
    if clean_mode != expected_mode:
        raise HTTPException(status_code=400, detail=f"Staged rebuild mode/dataset mismatch: mode={clean_mode}, dataset_type={clean_dataset_type}")

    validation = _managed_representation_request_service.validate_request(candidate_id, clean_dataset_type)
    candidate = validation["candidate"]

    prior_volume_id = validation.get("prior_volume_id") or candidate.get("volume_id")
    if not prior_volume_id:
        label = "3D Volume" if clean_mode == "3d" else "2D Line"
        raise HTTPException(
            status_code=400,
            detail=f"Rebuild requires an existing managed {clean_mode.upper()} output. Use Build {label} first.",
        )

    source_path = _resolve_rebuild_source_path(candidate)

    from app.api.documents import (
        ZARR_TMP_DIR,
        registry_conversion_executor,
        registry_conversion_job_service,
        registry_job_service,
    )
    from app.storage.service import storage_service

    job_id = str(uuid.uuid4())
    artifact_id = f"rebuild_{job_id}"
    filename = str(candidate.get("filename") or candidate.get("display_name") or source_path.name)

    storage_uri = f"endrepo://staging/conversion_jobs/rebuild/{clean_mode}/{artifact_id}.zarr"
    resolved = storage_service().resolve_uri(storage_uri)
    output_path = str(resolved.local_path)
    zarr_url = f"/endrepo/staging/conversion_jobs/rebuild/{clean_mode}/{artifact_id}.zarr"
    temp_output_path = str(Path(ZARR_TMP_DIR) / f"{artifact_id}.zarr.tmp")

    inherited_geometry: Optional[Dict[str, Any]] = None
    inherited_geometry_override: Optional[Dict[str, Any]] = None
    inherited_geometry_qaqc: Optional[Dict[str, Any]] = None
    if clean_dataset_type == "3d_volume":
        inherited_geometry = _find_prior_3d_rebuild_geometry(
            candidate=candidate,
            prior_volume_id=str(prior_volume_id),
            source_path=source_path,
            job_service=registry_job_service,
        )
        if inherited_geometry:
            inherited_geometry_override = inherited_geometry.get("geometry_override") if isinstance(inherited_geometry.get("geometry_override"), dict) else None
            inherited_geometry_qaqc = inherited_geometry.get("geometry_qaqc") if isinstance(inherited_geometry.get("geometry_qaqc"), dict) else None

    job = registry_job_service.create_job(
        job_id=job_id,
        file_id=artifact_id,
        filename=filename,
        input_path=str(source_path),
        output_path=output_path,
        temp_output_path=temp_output_path,
        expected_dataset_type=clean_dataset_type,
    )

    job = registry_job_service.update_job(
        job_id,
        message=f"{clean_mode.upper()} staged rebuild queued. Existing MSI/managed output is unchanged.",
        staged_rebuild=True,
        rebuild_context={
            "candidate_id": candidate_id,
            "prior_volume_id": prior_volume_id,
            "repository_id": candidate.get("repository_id"),
            "line_id": candidate.get("line_id"),
            "source_segy_file_id": candidate.get("segy_file_id") or candidate.get("source_segy_file_id"),
            "mode": clean_mode,
            "target": target,
            "inherited_geometry_source_job_id": (inherited_geometry or {}).get("source_job_id"),
            "inherited_geometry_source_volume_id": (inherited_geometry or {}).get("source_volume_id"),
            "inherited_geometry_match_reason": (inherited_geometry or {}).get("match_reason"),
        },
        geometry_override=inherited_geometry_override,
        geometry_qaqc=inherited_geometry_qaqc,
        output_path=output_path,
        zarr_url=zarr_url,
        storage_uri=storage_uri,
        promotion_required=True,
        promotion_options=["overwrite_existing", "save_as_new", "discard"],
    ) or job

    registry_conversion_executor.submit(registry_conversion_job_service.run, job_id)

    return {
        "status": "queued",
        "service": "source_intake_staged_rebuild",
        "mode": clean_mode,
        "target": target,
        "candidate_id": candidate_id,
        "prior_volume_id": prior_volume_id,
        "job_id": job_id,
        "artifact_id": artifact_id,
        "output_path": output_path,
        "zarr_url": zarr_url,
        "storage_uri": storage_uri,
        "promotion_required": True,
        "promotion_options": ["overwrite_existing", "save_as_new", "discard"],
        "geometry_override_inherited": bool(inherited_geometry_override),
        "geometry_source_job_id": (inherited_geometry or {}).get("source_job_id"),
        "geometry_match_reason": (inherited_geometry or {}).get("match_reason"),
        "job": job,
    }


def _queue_staged_2d_rebuild(candidate_id: str) -> Dict[str, Any]:
    return _queue_staged_rebuild(
        candidate_id,
        expected_dataset_type="2d_line",
        mode="2d",
        target="managed_2d_line_zarr",
    )


def _queue_staged_3d_rebuild(candidate_id: str) -> Dict[str, Any]:
    return _queue_staged_rebuild(
        candidate_id,
        expected_dataset_type="3d_volume",
        mode="3d",
        target="managed_3d_volume_zarr",
    )


def _normalize_candidate(item: Dict[str, Any]) -> Dict[str, Any]:
    source_path_exists = _resolve_source_path_exists(item)
    candidate_kind = item.get("candidate_kind")
    managed_state = _managed_state(item)

    candidate_role = str(item.get("candidate_role") or "").strip().lower()
    candidate_kind_clean = str(candidate_kind or "").strip().lower()

    can_build_2d = None
    can_build_3d = None
    can_build_index = None
    if source_path_exists is not None and candidate_kind_clean:
        can_build_2d = (
            source_path_exists
            and managed_state != "viewer_ready"
            and (candidate_kind_clean == "2d_line" or candidate_role == "line_candidate")
        )
        can_build_3d = (
            source_path_exists
            and managed_state != "viewer_ready"
            and (candidate_kind_clean == "3d_volume" or candidate_role == "volume_candidate")
        )
        can_build_index = source_path_exists and candidate_kind_clean == "3d_volume"

    candidate_id = item.get("source_segy_file_id") or item.get("segy_file_id") or item.get("candidate_id")

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
        "candidate_kind": candidate_kind,
        "candidate_role": item.get("candidate_role"),
        "classification_source": item.get("classification_source"),
        "classification_confidence": item.get("classification_confidence"),
        "classification_reasons": item.get("classification_reasons"),
        "review_state": item.get("review_state"),
        "conversion_state": item.get("conversion_status"),
        "managed_state": managed_state,
        "volume_id": item.get("volume_id"),
        "job_id": item.get("job_id"),
        "zarr_url": item.get("zarr_url"),
        "storage_uri": item.get("storage_uri"),
        "can_build_2d": can_build_2d,
        "can_build_3d": can_build_3d,
        "can_build_index": can_build_index,
        "status_label": managed_state.replace("_", " ").title(),
        "status_reason": item.get("conversion_state_reason") or item.get("conversion_error"),
        "source": item,
    }


def _read_jobs() -> List[Dict[str, Any]]:
    jobs_dir = Path(__file__).resolve().parents[2] / "data" / "jobs"
    if not jobs_dir.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for path in sorted(jobs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                value.setdefault("job_file", path.name)
                rows.append(value)
        except Exception:
            continue
    return rows



def _compact_staged_rebuild_job(job: Dict[str, Any]) -> Dict[str, Any]:
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
        "target": staged.get("target") or context.get("target") or ("managed_3d_volume_zarr" if (context.get("mode") or staged.get("mode")) == "3d" else "managed_2d_line_zarr"),
        "source_candidate_id": source_candidate_id,
        "prior_volume_id": context.get("prior_volume_id") or staged.get("source_volume_id"),
        "repository_id": context.get("repository_id"),
        "line_id": context.get("line_id"),
        "output_path": staged.get("output_path") or job.get("output_path"),
        "zarr_url": staged.get("zarr_url") or job.get("zarr_url"),
        "storage_uri": staged.get("storage_uri") or job.get("storage_uri"),
        "promotion_required": bool(job.get("promotion_required") or staged.get("promotion_required")),
        "promotion_options": job.get("promotion_options") or staged.get("promotion_options") or ["overwrite_existing", "save_as_new", "discard"],
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
    }



def _rebuild_state_from_staged_result(staged: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(staged, dict) or not staged:
        return {
            "status": "none",
            "promotion_required": False,
            "promotion_options": [],
        }

    raw_status = str(staged.get("status") or "").strip().lower()
    promotion_required = bool(staged.get("promotion_required"))
    promotion_options = staged.get("promotion_options") or []

    if raw_status in {"complete", "completed"} and promotion_required:
        state_status = "staged_ready"
    elif raw_status in {"complete", "completed"}:
        state_status = "complete"
    elif raw_status in {"queued", "submitted", "pending", "running", "building", "converting", "processing", "in_progress", "started"}:
        state_status = "rebuilding"
    elif raw_status in {"failed", "error"}:
        state_status = "failed"
    else:
        state_status = raw_status or "unknown"

    return {
        "status": state_status,
        "job_status": staged.get("status"),
        "job_id": staged.get("job_id"),
        "artifact_id": staged.get("artifact_id"),
        "source_candidate_id": staged.get("source_candidate_id"),
        "prior_volume_id": staged.get("prior_volume_id"),
        "repository_id": staged.get("repository_id"),
        "line_id": staged.get("line_id"),
        "mode": staged.get("mode") or "2d",
        "target": staged.get("target") or "managed_2d_line_zarr",
        "promotion_required": promotion_required,
        "promotion_options": promotion_options,
        "zarr_url": staged.get("zarr_url"),
        "storage_uri": staged.get("storage_uri"),
        "output_path": staged.get("output_path"),
        "message": staged.get("message"),
        "progress": staged.get("progress"),
        "created_at": staged.get("created_at"),
        "updated_at": staged.get("updated_at"),
    }


def _latest_staged_rebuild_jobs_by_candidate() -> Dict[str, Dict[str, Any]]:
    staged_by_candidate: Dict[str, Dict[str, Any]] = {}

    active_statuses = {"queued", "submitted", "pending", "running", "building", "converting", "processing", "in_progress", "started"}
    ready_statuses = {"complete", "completed"}
    failed_statuses = {"failed", "error"}
    terminal_hidden_statuses = {"promoted", "discarded", "superseded", "cancelled", "canceled"}

    for job in _read_jobs():
        if not isinstance(job, dict):
            continue

        message = str(job.get("message") or "").lower()
        progress_stage = str(job.get("progress_stage") or "").lower()
        is_staged = bool(
            job.get("staged_rebuild")
            or job.get("rebuild_context")
            or job.get("promotion_required")
            or "staged rebuild" in message
            or "staged_rebuild" in progress_stage
        )
        if not is_staged:
            continue

        compact = _compact_staged_rebuild_job(job)
        status = str(compact.get("status") or "").strip().lower()
        promotion_required = bool(compact.get("promotion_required"))

        should_surface = (
            status in active_statuses
            or status in failed_statuses
            or (status in ready_statuses and promotion_required)
        )
        if not should_surface or status in terminal_hidden_statuses:
            continue

        candidate_ids = [
            compact.get("source_candidate_id"),
            (job.get("rebuild_context") or {}).get("candidate_id") if isinstance(job.get("rebuild_context"), dict) else None,
            (job.get("staged_rebuild") or {}).get("source_candidate_id") if isinstance(job.get("staged_rebuild"), dict) else None,
        ]

        for raw_candidate_id in candidate_ids:
            candidate_id = str(raw_candidate_id or "").strip()
            if candidate_id and candidate_id not in staged_by_candidate:
                staged_by_candidate[candidate_id] = compact

    return staged_by_candidate


def _candidate_identifiers_for_staged_lookup(item: Dict[str, Any]) -> List[str]:
    identifiers: List[str] = []

    for raw in (
        _candidate_identifier(item),
        item.get("candidate_id"),
        item.get("source_segy_file_id"),
        item.get("segy_file_id"),
    ):
        value = str(raw or "").strip()
        if value and value not in identifiers:
            identifiers.append(value)

    source = item.get("source")
    if isinstance(source, dict):
        for raw in (
            _candidate_identifier(source),
            source.get("candidate_id"),
            source.get("source_segy_file_id"),
            source.get("segy_file_id"),
        ):
            value = str(raw or "").strip()
            if value and value not in identifiers:
                identifiers.append(value)

    return identifiers


def _latest_staged_rebuild_result_for_row(
    item: Dict[str, Any],
    staged_rebuilds_by_candidate: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    for candidate_id in _candidate_identifiers_for_staged_lookup(item):
        staged = staged_rebuilds_by_candidate.get(candidate_id)
        if staged:
            return staged
    return None



def _jobs_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "jobs"


def _write_job_record(job: Dict[str, Any]) -> None:
    job_id = str(job.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("Cannot write job record without job_id.")
    job["updated_at"] = datetime.utcnow().isoformat() + "Z"
    path = _jobs_dir() / f"{job_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Job record not found: {job_id}")
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _endrepo_root() -> Path:
    return Path(__file__).resolve().parents[4] / "End_Seismic_Data_Repository"


def _path_is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_staged_rebuild_artifact_path(output_path: Optional[str]) -> Optional[Path]:
    raw = str(output_path or "").strip()
    if not raw:
        return None

    path = Path(raw).expanduser().resolve()
    staging_base = (_endrepo_root() / "staging" / "conversion_jobs" / "rebuild").resolve()
    allowed_roots = [
        (staging_base / "2d").resolve(),
        (staging_base / "3d").resolve(),
    ]

    if not any(_path_is_relative_to(path, root) for root in allowed_roots):
        raise ValueError(f"Refusing to discard non-staged rebuild path: {path}")

    if path.suffix != ".zarr" or not path.name.startswith("rebuild_"):
        raise ValueError(f"Refusing to discard unexpected staged rebuild artifact: {path}")

    return path


def _delete_staged_rebuild_artifacts(output_path: Optional[str]) -> Dict[str, Any]:
    artifact_path = _safe_staged_rebuild_artifact_path(output_path)
    if artifact_path is None:
        return {"deleted_paths": [], "missing_paths": [], "artifact_path": None}

    deleted_paths: List[str] = []
    missing_paths: List[str] = []

    if artifact_path.exists():
        if artifact_path.is_dir():
            shutil.rmtree(artifact_path)
        else:
            artifact_path.unlink()
        deleted_paths.append(str(artifact_path))
    else:
        missing_paths.append(str(artifact_path))

    # Sidecars are promoted next to the staged .zarr directory using the same
    # basename, e.g. rebuild_<job>.zarr.segy_text_header.txt.
    for sidecar in artifact_path.parent.glob(artifact_path.name + ".*"):
        if sidecar.exists() and sidecar != artifact_path:
            if sidecar.is_dir():
                shutil.rmtree(sidecar)
            else:
                sidecar.unlink()
            deleted_paths.append(str(sidecar))

    return {
        "artifact_path": str(artifact_path),
        "deleted_paths": deleted_paths,
        "missing_paths": missing_paths,
    }


def _discard_staged_rebuild(candidate_id: str, request: SourceIntakeDiscardRebuildRequest) -> Dict[str, Any]:
    clean_candidate_id = str(candidate_id or "").strip()
    requested_job_id = str(request.job_id or "").strip()
    clean_mode = str(request.mode or "2d").strip().lower()

    if clean_mode not in {"2d", "3d"}:
        raise HTTPException(status_code=400, detail="Discard staged rebuild mode must be 2d or 3d.")

    if not clean_candidate_id:
        raise HTTPException(status_code=400, detail="Candidate id is required.")

    matching_jobs: List[Dict[str, Any]] = []
    for job in _read_jobs():
        if not isinstance(job, dict):
            continue
        compact = _compact_staged_rebuild_job(job)
        if str(compact.get("source_candidate_id") or "") != clean_candidate_id:
            continue
        if requested_job_id and str(compact.get("job_id") or "") != requested_job_id:
            continue
        if str(compact.get("status") or "").strip().lower() not in {"complete", "completed"}:
            continue
        if not bool(compact.get("promotion_required")):
            continue
        matching_jobs.append(job)

    if not matching_jobs:
        raise HTTPException(status_code=404, detail="No promotion-ready staged rebuild was found for this candidate.")

    job = matching_jobs[0]
    compact = _compact_staged_rebuild_job(job)
    delete_result = _delete_staged_rebuild_artifacts(compact.get("output_path"))

    staged = job.get("staged_rebuild") if isinstance(job.get("staged_rebuild"), dict) else {}
    if staged:
        staged = dict(staged)
        staged["promotion_required"] = False
        staged["promotion_options"] = []
        staged["discarded_at"] = datetime.utcnow().isoformat() + "Z"
        staged["discard_result"] = delete_result
        job["staged_rebuild"] = staged

    job["status"] = "discarded"
    job["message"] = "Staged rebuild discarded. Existing MSI record was unchanged."
    job["progress"] = 100
    job["progress_stage"] = "staged_rebuild_discarded"
    job["promotion_required"] = False
    job["promotion_options"] = []
    job["discarded_rebuild"] = compact
    job["discard_result"] = delete_result

    _write_job_record(job)

    return {
        "status": "discarded",
        "candidate_id": clean_candidate_id,
        "job_id": compact.get("job_id"),
        "artifact_id": compact.get("artifact_id"),
        "existing_msi_unchanged": True,
        "discard_result": delete_result,
    }



def _repository_folder_summary(repository: Dict[str, Any]) -> Dict[str, Any]:
    root_path = str(repository.get("root_path") or "").strip()
    main_count = 1 if root_path else 0
    subfolder_count = 0

    if root_path:
        try:
            root = Path(root_path).expanduser()
            if root.exists() and root.is_dir():
                subfolder_count = sum(1 for child in root.iterdir() if child.is_dir())
        except Exception:
            subfolder_count = 0

    return {
        "main": main_count,
        "subfolders": subfolder_count,
        "label": f"{main_count} main / {subfolder_count} subfolders",
    }


def _repository_with_single_source_summary(repo: Dict[str, Any], mode: Optional[str] = None) -> Dict[str, Any]:
    """Return repository payload decorated from the canonical backend scan summary.

    This is the single-source summary bridge for Source Intake repository cards.
    The same summary builder is used by stage-workbench, so the repository list
    and Stage response cannot diverge on package/line-volume/SEG-Y/document counts.
    """
    normalized = _normalize_repository(repo)
    repository_id = str(normalized.get("repository_id") or "").strip()
    if not repository_id:
        return normalized

    try:
        summary = build_repository_scan_summary(repository_id, mode=mode)
    except Exception:
        # Keep repository listing resilient; callers still receive the base repo.
        return normalized

    if not isinstance(summary, dict):
        return normalized

    normalized.update({
        "scan_summary": summary,
        "package_count": summary.get("package_count", normalized.get("package_count", 0)),
        "line_count": summary.get("line_count", normalized.get("line_count", 0)),
        "volume_count": summary.get("volume_count", normalized.get("volume_count", 0)),
        "candidate_count": summary.get("candidate_count", normalized.get("candidate_count", 0)),
        "segy_file_count": summary.get("segy_file_count", normalized.get("candidate_count", 0)),
        "document_count": summary.get("document_count", 0),
        "converted_count": summary.get("converted_count", normalized.get("submitted_count", 0)),
        "submitted_count": summary.get("converted_count", normalized.get("submitted_count", 0)),
        "last_scan_scope_label": summary.get("scope_label"),
    })
    return normalized


def _with_repository_folder_summaries(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload

    repositories = payload.get("repositories")
    if not isinstance(repositories, list):
        return payload

    updated = dict(payload)
    updated["repositories"] = [
        {**repo, "folder_summary": _repository_folder_summary(repo)}
        if isinstance(repo, dict)
        else repo
        for repo in repositories
    ]
    return updated



@router.post("/candidates/{candidate_id}/build-2d-line")
def build_source_intake_candidate_2d_line(candidate_id: str) -> Dict[str, Any]:
    try:
        return _managed_representation_request_service.build_2d_line(candidate_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build 2D managed representation failed: {exc}")


@router.post("/candidates/{candidate_id}/build-3d-volume")
def build_source_intake_candidate_3d_volume(candidate_id: str) -> Dict[str, Any]:
    try:
        return _managed_representation_request_service.build_3d_volume(candidate_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build 3D managed representation failed: {exc}")



@router.post("/candidates/{candidate_id}/build-index")
def build_source_intake_candidate_index(candidate_id: str, mode: str = "3d") -> Dict[str, Any]:
    clean_mode = str(mode or "3d").strip().lower()
    if clean_mode != "3d":
        raise HTTPException(status_code=400, detail="Build Index is only available for 3D source-intake candidates.")
    try:
        return queue_source_intake_index_job(candidate_id, mode=clean_mode)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build indexed SEG-Y preview failed: {exc}")


@router.get("/candidates/{candidate_id}/indexed-preview-viewer-source")
def get_source_intake_indexed_preview_viewer_source(candidate_id: str, mode: str = "3d") -> Dict[str, Any]:
    try:
        return build_source_intake_indexed_preview_viewer_source(candidate_id, mode=mode)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build indexed preview viewer source failed: {exc}")
