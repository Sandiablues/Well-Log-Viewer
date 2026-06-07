from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.repository_registry_service import REGISTRY_DIR, get_repository
from app.services.source_intake_document_assignment_service import (
    assign_source_intake_documents,
    get_candidate_document_assignment_review,
)
from app.services.source_intake_document_link_service import (
    get_candidate_document_bundle,
    get_package_document_bundle,
    summarize_repository_document_links,
)


router = APIRouter(prefix="/api/source-intake", tags=["source-intake-documents"])


class SourceIntakeDocumentAssignmentRequest(BaseModel):
    candidate_id: Optional[str] = None
    mode: Optional[str] = None
    action: str
    document_ids: List[str] = Field(default_factory=list)
    line_ids: List[str] = Field(default_factory=list)
    validate_only: bool = False


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


def _source_intake_document_record(document_id: str) -> Dict[str, Any]:
    target = str(document_id or "").strip()
    if not target:
        raise HTTPException(status_code=404, detail="Document id is required")
    documents = _source_intake_rows_from_payload(_read_source_intake_json(REGISTRY_DIR / "documents.json", []))
    for document in documents:
        if str(document.get("document_id") or "").strip() == target:
            return document
    raise HTTPException(status_code=404, detail=f"Source Intake document not found: {document_id}")


def _resolve_source_intake_document_path(document_id: str) -> Path:
    document = _source_intake_document_record(document_id)

    for key in ("source_path", "absolute_path", "path", "file_path"):
        raw = str(document.get(key) or "").strip()
        if raw:
            candidate = Path(raw).expanduser()
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()

    repository_id = str(document.get("repository_id") or "").strip()
    relative_path = str(document.get("relative_path") or document.get("path") or "").strip()
    if repository_id and relative_path:
        repository = get_repository(repository_id)
        root_path = str((repository or {}).get("root_path") or "").strip()
        if root_path:
            root = Path(root_path).expanduser().resolve()
            candidate = (root / relative_path).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                raise HTTPException(status_code=400, detail="Document path escapes registered repository root")
            if candidate.exists() and candidate.is_file():
                return candidate

    raise HTTPException(status_code=404, detail=f"Registered document file is not available: {document_id}")


def _source_intake_document_file_response(document_id: str, *, disposition: str) -> FileResponse:
    path = _resolve_source_intake_document_path(document_id)
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(
        str(path),
        media_type=media_type,
        filename=path.name,
        content_disposition_type=disposition,
    )


@router.get("/documents/{document_id}/open")
def open_source_intake_document(document_id: str):
    return _source_intake_document_file_response(document_id, disposition="inline")


@router.get("/documents/{document_id}/download")
def download_source_intake_document(document_id: str):
    return _source_intake_document_file_response(document_id, disposition="attachment")


@router.get("/packages/{package_id}/documents")
def get_source_intake_package_documents(package_id: str) -> Dict[str, Any]:
    try:
        return get_package_document_bundle(package_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build package document bundle failed: {exc}")


@router.get("/candidates/{candidate_id}/documents")
def get_source_intake_candidate_documents(candidate_id: str) -> Dict[str, Any]:
    try:
        return get_candidate_document_bundle(candidate_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build candidate document bundle failed: {exc}")


@router.get("/repositories/{repository_id}/document-links")
def get_source_intake_repository_document_links(repository_id: str) -> Dict[str, Any]:
    try:
        return summarize_repository_document_links(repository_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build repository document links failed: {exc}")


@router.get("/candidates/{candidate_id}/document-assignment-review")
def get_source_intake_candidate_document_assignment_review(candidate_id: str, mode: Optional[str] = None) -> Dict[str, Any]:
    try:
        return get_candidate_document_assignment_review(candidate_id, mode=mode)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build document assignment review failed: {exc}")


@router.get("/candidates/{candidate_id}/document-options")
def get_source_intake_candidate_document_options(candidate_id: str, mode: Optional[str] = None) -> Dict[str, Any]:
    try:
        review = get_candidate_document_assignment_review(candidate_id, mode=mode)
        return {
            "schema_version": "source_intake.document_options.v1",
            "candidate_id": candidate_id,
            "mode": mode,
            "candidate": review.get("candidate"),
            "options": review.get("options") or [],
            "assigned_document_ids": review.get("assigned_document_ids") or [],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build document options failed: {exc}")


@router.get("/candidates/{candidate_id}/document-assignments")
def get_source_intake_candidate_document_assignments(candidate_id: str, mode: Optional[str] = None) -> Dict[str, Any]:
    try:
        review = get_candidate_document_assignment_review(candidate_id, mode=mode)
        return {
            "schema_version": "source_intake.document_assignments.v1",
            "candidate_id": candidate_id,
            "mode": mode,
            "assigned_document_ids": review.get("assigned_document_ids") or [],
            "assignments": review.get("assignments") or [],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build document assignments failed: {exc}")


@router.post("/candidates/{candidate_id}/document-assignments")
def post_source_intake_candidate_document_assignments(candidate_id: str, request: SourceIntakeDocumentAssignmentRequest) -> Dict[str, Any]:
    try:
        payload = request.model_dump()
        payload["candidate_id"] = candidate_id
        return assign_source_intake_documents(payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Assign source-intake documents failed: {exc}")


@router.post("/document-assignments")
def post_source_intake_document_assignments(request: SourceIntakeDocumentAssignmentRequest) -> Dict[str, Any]:
    try:
        return assign_source_intake_documents(request.model_dump())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Assign source-intake documents failed: {exc}")
