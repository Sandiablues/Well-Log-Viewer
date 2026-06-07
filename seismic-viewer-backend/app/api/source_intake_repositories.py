from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.repository_registry_service import (
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
from app.services.source_intake_repository_summary_service import build_repository_scan_summary
from app.services.source_repository_mode_service import (
    apply_mode_defaults_to_payload,
    encode_repository_notes,
    filter_repositories_by_mode,
)
from app.services.manual_upload_source_intake_metadata_service import (
    decorate_manual_upload_repository,
    decorate_manual_upload_repositories,
)


router = APIRouter(prefix="/api/source-intake", tags=["source-intake-repositories"])


class SourceIntakeRepositoryCreateRequest(BaseModel):
    name: str
    root_path: str
    repository_type: str = "local_folder"
    read_only: bool = True
    notes: Optional[str] = None
    source_structure_type: Optional[str] = None
    intended_use: Optional[str] = None
    workflow_mode: Optional[str] = None


class SourceIntakeStageSelection(BaseModel):
    package_ids: List[str] = Field(default_factory=list)
    line_ids: List[str] = Field(default_factory=list)
    segy_file_ids: List[str] = Field(default_factory=list)
    document_ids: List[str] = Field(default_factory=list)


class SourceIntakeStageRequest(BaseModel):
    mode: str = "2d"
    selection: SourceIntakeStageSelection = Field(default_factory=SourceIntakeStageSelection)
    replace_existing: bool = False


class SourceIntakeSubmitRequest(BaseModel):
    mode: str = "2d"


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
    normalized = _normalize_repository(repo)
    repository_id = str(normalized.get("repository_id") or "").strip()
    if not repository_id:
        return normalized

    try:
        summary = build_repository_scan_summary(repository_id, mode=mode)
    except Exception:
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


@router.get("/repositories")
def list_source_intake_repositories(mode: Optional[str] = Query(None)) -> Dict[str, Any]:
    repositories = filter_repositories_by_mode(decorate_manual_upload_repositories(list_repositories()), mode)
    return _with_repository_folder_summaries({
        "mode": mode,
        "repositories": [
            _repository_with_single_source_summary(repo, mode=mode)
            for repo in repositories
        ],
    })


@router.post("/repositories")
def create_source_intake_repository(
    payload: SourceIntakeRepositoryCreateRequest,
    mode: Optional[str] = Query(None),
) -> Dict[str, Any]:
    try:
        raw_payload = payload.model_dump()
        mode_payload = apply_mode_defaults_to_payload(raw_payload, mode or payload.workflow_mode)
        notes = encode_repository_notes(
            mode_payload.get("notes"),
            mode_payload.get("source_structure_type"),
            mode_payload.get("intended_use"),
        )
        repo = add_repository(
            name=mode_payload.get("name") or payload.name,
            root_path=mode_payload.get("root_path") or payload.root_path,
            repository_type=mode_payload.get("repository_type") or payload.repository_type,
            read_only=bool(mode_payload.get("read_only", payload.read_only)),
            notes=notes,
        )
        repo = dict(repo)
        if mode_payload.get("source_structure_type"):
            repo.setdefault("source_structure_type", mode_payload.get("source_structure_type"))
        if mode_payload.get("intended_use"):
            repo.setdefault("intended_use", mode_payload.get("intended_use"))
        if mode_payload.get("workflow_mode"):
            repo.setdefault("workflow_mode", mode_payload.get("workflow_mode"))
        return {"repository": _normalize_repository(repo)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/packages")
def list_source_intake_packages(repository_id: Optional[str] = None) -> Dict[str, Any]:
    return {"packages": list_packages(repository_id=repository_id)}


@router.get("/lines")
def list_source_intake_lines(
    repository_id: Optional[str] = None,
    package_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {"lines": list_lines(repository_id=repository_id, package_id=package_id)}


@router.get("/segy-files")
def list_source_intake_segy_files(
    repository_id: Optional[str] = None,
    package_id: Optional[str] = None,
    line_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "segy_files": list_segy_files(
            repository_id=repository_id,
            package_id=package_id,
            line_id=line_id,
        )
    }


@router.get("/repositories/{repository_id}")
def get_source_intake_repository(repository_id: str, mode: Optional[str] = Query(None)) -> Dict[str, Any]:
    repo = get_repository(repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    repo = decorate_manual_upload_repository(repo)
    return {"repository": _repository_with_single_source_summary(repo, mode=mode)}


@router.get("/repositories/{repository_id}/load-sheet")
def get_source_intake_load_sheet(repository_id: str) -> Dict[str, Any]:
    try:
        return build_repository_load_sheet(repository_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/repositories/{repository_id}/stage")
def stage_source_intake_repository(repository_id: str, request: SourceIntakeStageRequest) -> Dict[str, Any]:
    try:
        result = stage_repository_selection(
            repository_id=repository_id,
            mode=request.mode,
            selection=request.selection.model_dump(),
            replace_existing=request.replace_existing,
        )
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result)
        return result
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Stage source intake repository failed: {exc}")


@router.post("/repositories/{repository_id}/stage/submit")
def submit_source_intake_repository(repository_id: str, request: SourceIntakeSubmitRequest) -> Dict[str, Any]:
    try:
        return submit_staged_source_items(repository_id=repository_id, staged_for=request.mode)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Submit source intake repository failed: {exc}")


@router.get("/candidates")
def list_source_intake_candidates(repository_id: Optional[str] = None) -> Dict[str, Any]:
    files = list_segy_files(repository_id=repository_id)
    return {"candidates": [_normalize_candidate(item) for item in files]}


@router.get("/candidates/{candidate_id}")
def get_source_intake_candidate(candidate_id: str) -> Dict[str, Any]:
    for item in list_segy_files():
        if candidate_id in {item.get("segy_file_id"), item.get("source_segy_file_id"), item.get("candidate_id")}:
            return {"candidate": _normalize_candidate(item)}
    raise HTTPException(status_code=404, detail="Source Intake candidate not found")


@router.get("/repositories/{repository_id}/candidates")
def list_source_intake_repository_candidates(repository_id: str) -> Dict[str, Any]:
    files = list_segy_files(repository_id=repository_id)
    return {"candidates": [_normalize_candidate(item) for item in files]}


@router.get("/repositories/{repository_id}/submitted-view")
def get_source_intake_submitted_view(repository_id: str, mode: str = Query("2d")) -> Dict[str, Any]:
    try:
        return build_submitted_external_registry_view(repository_id=repository_id, mode=mode)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build Source Intake submitted view failed: {exc}")
