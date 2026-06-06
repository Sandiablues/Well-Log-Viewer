from __future__ import annotations

from typing import Any
from pathlib import Path
from urllib.parse import quote
import json

from fastapi import HTTPException

from app.msi.representation_resolver_service import resolve_msi_representation_volume
from app.msi.repository import MSIRepository
from app.reports.metadata_score_report import render_volume_metadata_score_report
from app.services.metadata_agent_service import build_normalized_metadata, get_normalized_metadata
from app.services.metadata_summary_service import build_metadata_summary
from app.services.metadata_quality_service import build_metadata_quality_report
from app.services.msi_document_attachment_service import list_managed_document_attachments
from app.services.repository_registry_service import REGISTRY_DIR


def _resolve_representation(representation_id: str) -> dict[str, Any]:
    resolved = resolve_msi_representation_volume(representation_id)
    physical_volume_id = str(resolved.get("physical_volume_id") or "").strip()

    if not physical_volume_id:
        raise HTTPException(
            status_code=409,
            detail=f"MSI representation has no physical volume id: {representation_id}",
        )

    return resolved


def _physical_volume_id_for_representation(representation_id: str) -> str:
    return str(_resolve_representation(representation_id).get("physical_volume_id") or "").strip()


def _first_text_value(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _source_name_from_dataset_and_summary(dataset: Any, summary: dict[str, Any]) -> str | None:
    source_reference = getattr(dataset, "source_reference", None) or {}
    source = summary.get("source") or {}

    return _first_text_value(
        source.get("filename"),
        source.get("line_display_name"),
        source.get("line_id"),
        source_reference.get("filename"),
        source_reference.get("source_file_name"),
        source_reference.get("source_relative_path"),
        source_reference.get("relative_path"),
        source_reference.get("path"),
        summary.get("display_name"),
        getattr(dataset, "display_name", None),
    )


def _attachment_document_key(item: dict[str, Any]) -> tuple[str, str]:
    document_id = str(item.get("document_id") or "").strip()
    filename = str(item.get("filename") or item.get("original_filename") or "").strip()
    return (document_id, filename)

def _add_document_access_urls(item: dict[str, Any]) -> dict[str, Any]:
    # DOCUMENT_ACCESS_UNIFICATION_FINAL: Info Page uses unified document access URLs.
    # INFO_DOCS_LINKS_1: Info Page Supporting Documents need explicit backend
    # open/download URLs. Documents may come from current MSI attachments or
    # stable Source Intake assignments, but both resolve through document_id.
    document_id = str(item.get("document_id") or "").strip()
    if not document_id:
        return item
    encoded = quote(document_id, safe="")
    item.setdefault("open_url", f"/api/documents/{encoded}/open")
    item.setdefault("view_url", item.get("open_url"))
    item.setdefault("download_url", f"/api/documents/{encoded}/download")
    return item


def _document_from_msi_attachment(attachment: dict[str, Any]) -> dict[str, Any] | None:
    document = attachment.get("document") if isinstance(attachment.get("document"), dict) else {}
    document_id = str(attachment.get("document_id") or document.get("document_id") or "").strip()
    filename = str(document.get("filename") or attachment.get("filename") or "").strip()

    if not document_id and not filename:
        return None

    item = dict(document)
    item.update({
        "document_id": document_id or item.get("document_id"),
        "filename": filename or item.get("filename"),
        "document_type": item.get("document_type") or attachment.get("document_type") or "unknown",
        "document_role": attachment.get("document_role") or item.get("document_role") or "supporting_document",
        "attachment_id": attachment.get("attachment_id"),
        "attachment_scope": attachment.get("scope_kind"),
        "scope_basis": attachment.get("scope_basis"),
        "dataset_id": attachment.get("dataset_id"),
        "representation_id": attachment.get("representation_id"),
        "survey_name": attachment.get("survey_name"),
        "line_name": attachment.get("line_name"),
        "volume_name": attachment.get("volume_name"),
        "relationship_reason": attachment.get("relationship_reason"),
        "status": attachment.get("status") or item.get("status") or "attached",
        "source": "msi_document_attachment",
    })
    _add_document_access_urls(item)
    return item


# INFO_DOCS_LIFECYCLE_1: resolve supporting documents through stable Source Intake
# assignment identity as well as volatile MSI representation attachments.
def _read_json_file(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload
    except Exception:
        return default


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _rows_from_payload(payload: Any, preferred_keys: tuple[str, ...] = ("assignments", "documents", "attachments", "items", "rows")) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in preferred_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        if all(isinstance(value, dict) for value in payload.values()):
            return [row for row in payload.values() if isinstance(row, dict)]
    return []


def _document_registry_by_id() -> dict[str, dict[str, Any]]:
    documents = _rows_from_payload(_read_json_file(REGISTRY_DIR / "documents.json", []))
    out: dict[str, dict[str, Any]] = {}
    for document in documents:
        document_id = _clean_text(document.get("document_id"))
        if document_id:
            out[document_id] = document
    return out


def _source_intake_assignments() -> list[dict[str, Any]]:
    path = REGISTRY_DIR.parent / "source_intake_document_assignments.json"
    return _rows_from_payload(_read_json_file(path, {}))


def _source_reference_ids(source_reference: dict[str, Any] | None, dataset_id: str | None) -> dict[str, str]:
    source = source_reference if isinstance(source_reference, dict) else {}
    source_segy_file_id = _clean_text(
        source.get("source_segy_file_id")
        or source.get("source_candidate_id")
        or source.get("candidate_id")
        or source.get("segy_file_id")
    )
    return {
        "dataset_id": _clean_text(dataset_id),
        "source_segy_file_id": source_segy_file_id,
        "candidate_id": _clean_text(source.get("candidate_id") or source.get("source_candidate_id") or source_segy_file_id),
        "package_id": _clean_text(source.get("package_id")),
        "repository_id": _clean_text(source.get("repository_id")),
        "line_id": _clean_text(source.get("line_id")),
    }


def _assignment_matches_source(assignment: dict[str, Any], ids: dict[str, str]) -> bool:
    source_segy_file_id = ids.get("source_segy_file_id") or ""
    candidate_id = ids.get("candidate_id") or source_segy_file_id
    package_id = ids.get("package_id") or ""
    repository_id = ids.get("repository_id") or ""
    line_id = ids.get("line_id") or ""

    assignment_candidate = _clean_text(
        assignment.get("candidate_id")
        or assignment.get("source_candidate_id")
        or assignment.get("source_segy_file_id")
        or assignment.get("segy_file_id")
    )
    if source_segy_file_id and assignment_candidate and assignment_candidate == source_segy_file_id:
        return True
    if candidate_id and assignment_candidate and assignment_candidate == candidate_id:
        return True

    assignment_repository = _clean_text(assignment.get("repository_id"))
    assignment_package = _clean_text(assignment.get("package_id"))
    assignment_line = _clean_text(assignment.get("line_id"))

    if repository_id and assignment_repository and assignment_repository != repository_id:
        return False
    if package_id and assignment_package and assignment_package == package_id:
        if not assignment_line or not line_id or assignment_line == line_id:
            return True

    return False


def _document_from_source_assignment(
    assignment: dict[str, Any],
    document_by_id: dict[str, dict[str, Any]],
    *,
    dataset_id: str | None,
    representation_id: str,
) -> dict[str, Any] | None:
    document_id = _clean_text(assignment.get("document_id"))
    if not document_id:
        return None
    document = dict(document_by_id.get(document_id) or {})
    if not document:
        return None

    filename = _clean_text(document.get("filename") or document.get("name"))
    if not filename:
        return None

    document.update({
        "document_id": document_id,
        "filename": filename,
        "document_type": document.get("document_type") or assignment.get("document_type") or "unknown",
        "document_role": document.get("document_role") or assignment.get("document_role") or "supporting_document",
        "dataset_id": dataset_id,
        "representation_id": representation_id,
        "repository_id": assignment.get("repository_id") or document.get("repository_id"),
        "package_id": assignment.get("package_id") or document.get("package_id"),
        "line_id": assignment.get("line_id") or document.get("line_id"),
        "source_candidate_id": assignment.get("candidate_id") or assignment.get("source_candidate_id"),
        "source_segy_file_id": assignment.get("source_segy_file_id") or assignment.get("candidate_id"),
        "attachment_scope": assignment.get("assignment_scope") or assignment.get("scope") or "source_intake_assignment",
        "scope_basis": "source_intake_stable_identity",
        "relationship_reason": "resolved_from_source_intake_document_assignment",
        "status": assignment.get("status") or document.get("status") or "attached",
        "source": "source_intake_document_assignment",
    })
    _add_document_access_urls(document)
    return document


def _list_source_assignment_documents(
    *,
    dataset_id: str | None,
    representation_id: str,
    source_reference: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    ids = _source_reference_ids(source_reference, dataset_id)
    if not any(ids.get(key) for key in ("source_segy_file_id", "candidate_id", "package_id")):
        return []

    document_by_id = _document_registry_by_id()
    if not document_by_id:
        return []

    documents: list[dict[str, Any]] = []
    for assignment in _source_intake_assignments():
        if not _assignment_matches_source(assignment, ids):
            continue
        document = _document_from_source_assignment(
            assignment,
            document_by_id,
            dataset_id=dataset_id,
            representation_id=representation_id,
        )
        if document:
            documents.append(document)
    return documents



def _list_representation_attachment_documents(
    *,
    dataset_id: str | None,
    representation_id: str,
    source_reference: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    # INFO_DOCS_LIFECYCLE_1: documents are resolved from both current MSI
    # attachment rows and stable Source Intake assignment rows. Representation
    # IDs are volatile across delete/reset/reconversion; Source Intake candidate
    # and package IDs are the durable lineage.
    attachments: list[dict[str, Any]] = []
    seen_attachment_ids: set[str] = set()

    queries: list[dict[str, str]] = []
    if dataset_id:
        queries.append({"dataset_id": dataset_id})
    if representation_id:
        queries.append({"representation_id": representation_id})

    for query in queries:
        try:
            payload = list_managed_document_attachments(**query)
        except Exception:
            continue
        for attachment in payload.get("attachments") or []:
            if not isinstance(attachment, dict):
                continue
            attachment_id = str(attachment.get("attachment_id") or "").strip()
            if attachment_id and attachment_id in seen_attachment_ids:
                continue
            if attachment_id:
                seen_attachment_ids.add(attachment_id)
            attachments.append(attachment)

    documents = [doc for doc in (_document_from_msi_attachment(item) for item in attachments) if doc]
    documents.extend(
        _list_source_assignment_documents(
            dataset_id=dataset_id,
            representation_id=representation_id,
            source_reference=source_reference,
        )
    )
    return documents


def _merge_msi_attachment_documents_into_summary(
    summary: dict[str, Any],
    *,
    dataset_id: str | None,
    representation_id: str,
    source_reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attachment_documents = _list_representation_attachment_documents(
        dataset_id=dataset_id,
        representation_id=representation_id,
        source_reference=source_reference,
    )
    if not attachment_documents:
        return summary

    merged = dict(summary)
    documents_block = dict(merged.get("documents") or {})
    supporting_documents = list(documents_block.get("supporting_documents") or [])
    seen = {_attachment_document_key(doc) for doc in supporting_documents if isinstance(doc, dict)}

    added_count = 0
    for document in attachment_documents:
        key = _attachment_document_key(document)
        if key in seen:
            continue
        supporting_documents.append(document)
        seen.add(key)
        added_count += 1

    documents_block["supporting_documents"] = supporting_documents
    documents_block["supporting_links"] = list(documents_block.get("supporting_links") or [])
    documents_block["msi_attachment_count"] = len(attachment_documents)
    documents_block["msi_attachment_added_count"] = added_count
    merged["documents"] = documents_block

    warnings = [
        warning for warning in list(merged.get("warnings") or [])
        if warning != "No supporting documents linked to this dataset."
    ]
    merged["warnings"] = warnings
    return merged


def get_representation_metadata_summary(representation_id: str) -> dict[str, Any]:
    resolved = _resolve_representation(representation_id)
    physical_volume_id = str(resolved.get("physical_volume_id") or "").strip()
    dataset_id = str(resolved.get("dataset_id") or "").strip()

    summary, error = build_metadata_summary(physical_volume_id)
    if error:
        raise HTTPException(status_code=404, detail=error)

    dataset = MSIRepository().get_dataset(dataset_id) if dataset_id else None
    managed_display_name = getattr(dataset, "display_name", None) if dataset else None
    original_source_name = _source_name_from_dataset_and_summary(dataset, summary) if dataset else summary.get("display_name")
    source_reference = getattr(dataset, "source_reference", None) or {}

    summary = _merge_msi_attachment_documents_into_summary(
        summary,
        dataset_id=dataset_id or None,
        representation_id=representation_id,
        source_reference=source_reference,
    )

    # E2E-1C_METADATA_COMPLETENESS_DOCUMENT_AUTHORITY:
    # MSI metadata summary is enriched with MSI/source-intake document context
    # after the physical-volume metadata summary is built. The completeness
    # score must be recalculated after that enrichment so the Missing list uses
    # the same backend document authority as the Supporting Documents section.
    summary["metadata_quality"] = build_metadata_quality_report(summary)

    return {
        **summary,
        "_msi": {
            "representation_id": representation_id,
            "dataset_id": dataset_id or None,
            "physical_volume_id": physical_volume_id,
            "managed_display_name": managed_display_name,
            "original_source_name": original_source_name,
            "display_name_override": source_reference.get("display_name_override") is True,
            "resolved_by": "msi_representation_metadata_service",
        },
    }


def get_representation_normalized_metadata(representation_id: str) -> dict[str, Any]:
    physical_volume_id = _physical_volume_id_for_representation(representation_id)

    try:
        normalized = get_normalized_metadata(physical_volume_id)
        if normalized is None:
            normalized = build_normalized_metadata(physical_volume_id)

        return {
            "volume_id": physical_volume_id,
            "msi_representation_id": representation_id,
            "physical_volume_id": physical_volume_id,
            "normalized_metadata": normalized,
            "resolved_by": "msi_representation_metadata_service",
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to get or build normalized metadata for "
                f"msi_representation_id={representation_id}, "
                f"physical_volume_id={physical_volume_id}: {exc}"
            ),
        )


def render_representation_metadata_score_report(representation_id: str) -> str:
    physical_volume_id = _physical_volume_id_for_representation(representation_id)
    return render_volume_metadata_score_report(physical_volume_id)
