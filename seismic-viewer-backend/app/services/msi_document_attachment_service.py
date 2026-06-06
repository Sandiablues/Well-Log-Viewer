from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import uuid

from app.msi.repository import MSIRepository
from app.services.repository_registry_service import REGISTRY_DIR
from app.services.document_registry_service import get_document, register_managed_document_copy, register_managed_document_upload

ATTACHMENTS_PATH = REGISTRY_DIR / "msi_document_attachments.json"
SCHEMA_VERSION = "msi.document_attachments.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_store() -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    if not ATTACHMENTS_PATH.exists():
        ATTACHMENTS_PATH.write_text("[]", encoding="utf-8")


def _read_store() -> List[Dict[str, Any]]:
    _ensure_store()
    try:
        payload = json.loads(ATTACHMENTS_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def _write_store(rows: List[Dict[str, Any]]) -> None:
    _ensure_store()
    ATTACHMENTS_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _dataset_for_target(repo: MSIRepository, target_id: str) -> Dict[str, Any]:
    target_id = _clean(target_id)
    if not target_id:
        raise ValueError("target_id is required")

    representation = repo.get_representation(target_id)
    if representation:
        dataset = repo.get_dataset(representation.dataset_id)
        if not dataset:
            raise ValueError(f"Dataset not found for representation: {target_id}")
        return {
            "target_input_id": target_id,
            "target_kind": "msi_representation",
            "representation_id": representation.representation_id,
            "dataset_id": dataset.dataset_id,
            "display_name": dataset.display_name,
            "survey_name": dataset.survey_name,
            "line_name": dataset.line_name,
            "volume_name": dataset.volume_name,
        }

    dataset = repo.get_dataset(target_id)
    if dataset:
        return {
            "target_input_id": target_id,
            "target_kind": "msi_dataset",
            "representation_id": None,
            "dataset_id": dataset.dataset_id,
            "display_name": dataset.display_name,
            "survey_name": dataset.survey_name,
            "line_name": dataset.line_name,
            "volume_name": dataset.volume_name,
        }

    raise ValueError(f"MSI target not found: {target_id}")


def list_managed_document_attachments(
    *,
    dataset_id: Optional[str] = None,
    representation_id: Optional[str] = None,
    survey_name: Optional[str] = None,
) -> Dict[str, Any]:
    rows = _read_store()
    if dataset_id:
        rows = [row for row in rows if row.get("dataset_id") == dataset_id]
    if representation_id:
        rows = [row for row in rows if row.get("representation_id") == representation_id]
    if survey_name:
        needle = survey_name.strip().lower()
        rows = [row for row in rows if str(row.get("survey_name") or "").strip().lower() == needle]

    enriched = []
    for row in rows:
        item = dict(row)
        doc_id = item.get("document_id")
        if doc_id:
            doc = get_document(doc_id)
            if doc:
                item["document"] = doc
        enriched.append(item)

    return {
        "schema_version": SCHEMA_VERSION,
        "attachments": enriched,
        "attachment_count": len(enriched),
    }


def attach_document_to_managed_data(
    *,
    source_path: str,
    target_ids: List[str],
    scope_kind: str,
    survey_name: Optional[str] = None,
    document_type: Optional[str] = None,
    document_role: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    clean_targets = [_clean(value) for value in target_ids if _clean(value)]
    if not clean_targets:
        raise ValueError("At least one target_id is required")

    scope_kind = _clean(scope_kind) or "selected_data"
    if scope_kind not in {"selected_data", "survey"}:
        raise ValueError(f"Unsupported document attachment scope_kind: {scope_kind}")

    source = Path(source_path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Document file not found: {source}")

    repo = MSIRepository()
    targets = [_dataset_for_target(repo, target_id) for target_id in clean_targets]

    document = register_managed_document_copy(
        source_path=str(source),
        document_type=document_type,
        linked_scope="msi_dataset",
        notes=notes,
    )

    now = _utc_now()
    existing = _read_store()
    created: List[Dict[str, Any]] = []
    existing_keys = {
        (row.get("document_id"), row.get("dataset_id"), row.get("representation_id"))
        for row in existing
    }

    for target in targets:
        key = (document.get("document_id"), target.get("dataset_id"), target.get("representation_id"))
        if key in existing_keys:
            continue
        row = {
            "attachment_id": f"docatt_{uuid.uuid4().hex[:12]}",
            "schema_version": SCHEMA_VERSION,
            "document_id": document.get("document_id"),
            "dataset_id": target.get("dataset_id"),
            "representation_id": target.get("representation_id"),
            "target_kind": target.get("target_kind"),
            "target_input_id": target.get("target_input_id"),
            "display_name": target.get("display_name"),
            "survey_name": survey_name or target.get("survey_name"),
            "line_name": target.get("line_name"),
            "volume_name": target.get("volume_name"),
            "scope_kind": scope_kind,
            "scope_basis": "survey_name" if scope_kind == "survey" else "selected_rows",
            "document_type": document.get("document_type"),
            "document_role": _clean(document_role) or "supporting_document",
            "relationship_reason": "manual_md_add_documents",
            "status": "attached",
            "created_at": now,
            "updated_at": now,
            "notes": notes,
        }
        existing.append(row)
        created.append(row)

    if created:
        _write_store(existing)

    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "document": document,
        "created_count": len(created),
        "skipped_existing_count": len(targets) - len(created),
        "attachments": created,
        "target_count": len(targets),
        "scope_kind": scope_kind,
    }



def attach_uploaded_documents_to_managed_data(
    *,
    uploaded_documents: List[Dict[str, Any]],
    target_ids: List[str],
    scope_kind: str,
    survey_name: Optional[str] = None,
    document_type: Optional[str] = None,
    document_role: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    clean_targets = [_clean(value) for value in target_ids if _clean(value)]
    if not clean_targets:
        raise ValueError("At least one target_id is required")

    scope_kind = _clean(scope_kind) or "selected_data"
    if scope_kind not in {"selected_data", "survey"}:
        raise ValueError(f"Unsupported document attachment scope_kind: {scope_kind}")

    repo = MSIRepository()
    targets = [_dataset_for_target(repo, target_id) for target_id in clean_targets]
    existing = _read_store()
    existing_keys = {
        (row.get("document_id"), row.get("dataset_id"), row.get("representation_id"))
        for row in existing
    }
    uploaded_results: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    created: List[Dict[str, Any]] = []
    now = _utc_now()

    for upload in uploaded_documents:
        filename = _clean(upload.get("filename")) or "uploaded_document"
        content = upload.get("content") or b""
        mime_type = _clean(upload.get("mime_type")) or None
        try:
            document = register_managed_document_upload(
                filename=filename,
                content=content,
                mime_type=mime_type,
                document_type=document_type,
                linked_scope="msi_dataset",
                notes=notes,
            )
        except Exception as exc:
            rejected.append({"original_filename": filename, "reason": str(exc), "status": "rejected"})
            continue

        attached_dataset_ids: List[str] = []
        for target in targets:
            key = (document.get("document_id"), target.get("dataset_id"), target.get("representation_id"))
            if key in existing_keys:
                continue
            row = {
                "attachment_id": f"docatt_{uuid.uuid4().hex[:12]}",
                "schema_version": SCHEMA_VERSION,
                "document_id": document.get("document_id"),
                "dataset_id": target.get("dataset_id"),
                "representation_id": target.get("representation_id"),
                "target_kind": target.get("target_kind"),
                "target_input_id": target.get("target_input_id"),
                "display_name": target.get("display_name"),
                "survey_name": survey_name or target.get("survey_name"),
                "line_name": target.get("line_name"),
                "volume_name": target.get("volume_name"),
                "scope_kind": scope_kind,
                "scope_basis": "survey_name" if scope_kind == "survey" else "selected_rows",
                "document_type": document.get("document_type"),
                "document_role": _clean(document_role) or "supporting_document",
                "relationship_reason": "manual_md_add_documents_upload",
                "status": "attached",
                "created_at": now,
                "updated_at": now,
                "notes": notes,
            }
            existing.append(row)
            existing_keys.add(key)
            created.append(row)
            attached_dataset_ids.append(str(target.get("dataset_id")))

        uploaded_results.append({
            "document_id": document.get("document_id"),
            "original_filename": document.get("filename"),
            "stored_filename": Path(str(document.get("managed_path") or "")).name,
            "mime_type": document.get("mime_type"),
            "size_bytes": document.get("size_bytes"),
            "checksum": document.get("checksum"),
            "attachment_scope": "survey" if scope_kind == "survey" else "dataset",
            "relationship_type": "survey_wide" if scope_kind == "survey" else "line_volume_specific",
            "attached_dataset_ids": attached_dataset_ids,
            "survey_name": survey_name,
            "status": "attached",
            "attachment_count": len(attached_dataset_ids),
        })

    if created:
        _write_store(existing)

    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "uploaded_documents": uploaded_results,
        "rejected_documents": rejected,
        "created_count": len(created),
        "target_count": len(targets),
        "attached_dataset_count": len({row.get("dataset_id") for row in created}),
        "scope_kind": scope_kind,
    }

