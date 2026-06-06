from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.document_registry_service import list_documents
from app.services.package_registry_service import list_packages, list_segy_files


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _norm_path(value: Any) -> str:
    return _clean(value).replace("\\", "/").strip("/")


def _parent_dir(relative_path: Any) -> str:
    path = _norm_path(relative_path)
    if not path or "/" not in path:
        return ""
    return path.rsplit("/", 1)[0]


def _document_status(doc: Dict[str, Any]) -> str:
    status = _clean(doc.get("status")).lower()
    if status:
        return status
    return "available"


def _evidence_status_for_documents(docs: List[Dict[str, Any]]) -> str:
    if not docs:
        return "not_linked"

    statuses = {_document_status(doc) for doc in docs}
    if "missing" in statuses or "unresolved" in statuses:
        return "review_required"

    return "linked"


def _document_public_row(doc: Dict[str, Any], *, match_scope: str, match_reason: str, match_confidence: str) -> Dict[str, Any]:
    return {
        "document_id": doc.get("document_id"),
        "filename": doc.get("filename"),
        "relative_path": doc.get("relative_path"),
        "document_type": doc.get("document_type"),
        "document_role": doc.get("document_role") or doc.get("document_type"),
        "repository_id": doc.get("repository_id"),
        "package_id": doc.get("package_id"),
        "line_id": doc.get("line_id"),
        "volume_id": doc.get("volume_id"),
        "linked_scope": doc.get("linked_scope"),
        "match_scope": match_scope,
        "match_reason": match_reason,
        "match_confidence": match_confidence,
        "status": _document_status(doc),
        "mime_type": doc.get("mime_type"),
        "view_url": doc.get("view_url"),
        "download_url": doc.get("download_url"),
        "reveal_url": doc.get("reveal_url"),
    }


def _dedupe_documents(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        key = _clean(row.get("document_id")) or f"{row.get('repository_id')}:{row.get('relative_path')}"
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _candidate_source(candidate_id: str) -> Optional[Dict[str, Any]]:
    clean_candidate_id = _clean(candidate_id)
    for item in list_segy_files():
        if clean_candidate_id in {
            _clean(item.get("segy_file_id")),
            _clean(item.get("source_segy_file_id")),
            _clean(item.get("candidate_id")),
        }:
            return item
    return None


def match_documents_for_candidate_item(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    repository_id = _clean(item.get("repository_id"))
    package_id = _clean(item.get("package_id"))
    line_id = _clean(item.get("line_id"))
    candidate_dir = _parent_dir(item.get("relative_path"))

    if not repository_id:
        return []

    documents = list_documents(repository_id=repository_id)
    matches: List[Dict[str, Any]] = []

    for doc in documents:
        doc_package_id = _clean(doc.get("package_id"))
        doc_line_id = _clean(doc.get("line_id"))
        doc_rel = _norm_path(doc.get("relative_path"))
        doc_dir = _parent_dir(doc_rel)

        if line_id and doc_line_id == line_id:
            matches.append(_document_public_row(
                doc,
                match_scope="line",
                match_reason="document.line_id matches candidate.line_id",
                match_confidence="high",
            ))
            continue

        if package_id and doc_package_id == package_id:
            matches.append(_document_public_row(
                doc,
                match_scope="package",
                match_reason="document.package_id matches candidate.package_id",
                match_confidence="high",
            ))
            continue

        if candidate_dir and (doc_dir == candidate_dir or doc_rel.startswith(candidate_dir + "/")):
            matches.append(_document_public_row(
                doc,
                match_scope="folder",
                match_reason="document is in the same source folder as the SEG-Y candidate",
                match_confidence="medium",
            ))
            continue

    return _dedupe_documents(matches)


def get_candidate_document_bundle(candidate_id: str) -> Dict[str, Any]:
    item = _candidate_source(candidate_id)
    if not item:
        raise FileNotFoundError(f"Source Intake candidate not found: {candidate_id}")

    documents = match_documents_for_candidate_item(item)
    return {
        "candidate_id": candidate_id,
        "repository_id": item.get("repository_id"),
        "package_id": item.get("package_id"),
        "line_id": item.get("line_id"),
        "filename": item.get("filename") or item.get("display_name"),
        "document_count": len(documents),
        "evidence_status": _evidence_status_for_documents(documents),
        "documents": documents,
    }


def get_package_document_bundle(package_id: str) -> Dict[str, Any]:
    clean_package_id = _clean(package_id)
    if not clean_package_id:
        raise FileNotFoundError("package_id is required")

    package = None
    for pkg in list_packages():
        if _clean(pkg.get("package_id")) == clean_package_id:
            package = pkg
            break

    if not package:
        raise FileNotFoundError(f"Source Intake package not found: {package_id}")

    repository_id = _clean(package.get("repository_id"))
    documents = []
    if repository_id:
        for doc in list_documents(repository_id=repository_id):
            if _clean(doc.get("package_id")) == clean_package_id:
                documents.append(_document_public_row(
                    doc,
                    match_scope="package",
                    match_reason="document.package_id matches requested package_id",
                    match_confidence="high",
                ))

    documents = _dedupe_documents(documents)
    return {
        "package_id": package_id,
        "repository_id": repository_id,
        "display_name": package.get("display_name"),
        "document_count": len(documents),
        "evidence_status": _evidence_status_for_documents(documents),
        "documents": documents,
    }


def summarize_candidate_documents(item: Dict[str, Any], *, candidate_id: Any = None) -> Dict[str, Any]:
    candidate_key = _clean(candidate_id) or _clean(item.get("segy_file_id")) or _clean(item.get("source_segy_file_id")) or _clean(item.get("candidate_id"))
    try:
        documents = match_documents_for_candidate_item(item)
    except Exception:
        documents = []

    preview = documents[:5]
    return {
        "candidate_id": candidate_key,
        "document_count": len(documents),
        "evidence_status": _evidence_status_for_documents(documents),
        "supporting_documents": preview,
        "supporting_document_count": len(documents),
    }


def summarize_repository_document_links(repository_id: str) -> Dict[str, Any]:
    clean_repository_id = _clean(repository_id)
    if not clean_repository_id:
        raise FileNotFoundError("repository_id is required")

    candidates = list_segy_files(repository_id=clean_repository_id)
    rows = []
    total_links = 0

    for item in candidates:
        candidate_id = _clean(item.get("segy_file_id")) or _clean(item.get("source_segy_file_id")) or _clean(item.get("candidate_id"))
        summary = summarize_candidate_documents(item, candidate_id=candidate_id)
        total_links += int(summary.get("document_count") or 0)
        rows.append({
            "candidate_id": candidate_id,
            "filename": item.get("filename") or item.get("display_name"),
            "package_id": item.get("package_id"),
            "line_id": item.get("line_id"),
            "document_count": summary.get("document_count"),
            "evidence_status": summary.get("evidence_status"),
            "supporting_documents": summary.get("supporting_documents"),
        })

    return {
        "repository_id": clean_repository_id,
        "candidate_count": len(candidates),
        "total_document_links": total_links,
        "rows": rows,
    }
