
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import mimetypes
import shutil
import hashlib
import uuid

from app.services.repository_registry_service import (
    REGISTRY_DIR,
    get_repository,
    resolve_repository_path,
    update_repository_scan_time,
)


DOCUMENTS_PATH = REGISTRY_DIR / "documents.json"

SEGY_EXTENSIONS = {".sgy", ".segy"}

DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".text",
    ".csv",
    ".tsv",
    ".xlsx",
    ".xls",
    ".docx",
    ".doc",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".gif",
    ".json",
    ".xml",
    ".las",
    ".asc",
    ".dat",
    ".nav",
    ".ukooa",
    ".p190",
    ".vel",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_registry() -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    if not DOCUMENTS_PATH.exists():
        DOCUMENTS_PATH.write_text("[]", encoding="utf-8")


def _read_documents() -> List[Dict[str, Any]]:
    _ensure_registry()
    try:
        value = json.loads(DOCUMENTS_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _write_documents(value: List[Dict[str, Any]]) -> None:
    _ensure_registry()
    DOCUMENTS_PATH.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def classify_document_type(filename: str) -> str:
    name = filename.lower()

    if "processing" in name or "process" in name or "proc" in name:
        return "processing_report"
    if "observer" in name or "obs" in name:
        return "observer_log"
    if "navigation" in name or "nav" in name or "ukooa" in name or "p190" in name:
        return "navigation"
    if "velocity" in name or "vel" in name:
        return "velocity"
    if "acquisition" in name or "acq" in name:
        return "acquisition_report"
    if "map" in name or "location" in name:
        return "map"
    if name.endswith(".las"):
        return "well_log"
    if name.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif")):
        return "image"
    if name.endswith((".csv", ".xlsx", ".xls")):
        return "spreadsheet_or_table"
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith((".txt", ".text")):
        return "text"

    return "unknown"


def list_documents(
    repository_id: Optional[str] = None,
    linked_scope: Optional[str] = None,
) -> List[Dict[str, Any]]:
    docs = _read_documents()

    if repository_id:
        docs = [d for d in docs if d.get("repository_id") == repository_id]

    if linked_scope:
        docs = [d for d in docs if d.get("linked_scope") == linked_scope]

    for doc in docs:
        try:
            path = resolve_document_path(doc["document_id"])
            doc["status"] = "available" if path.exists() else "missing"
            doc["mime_type"] = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            doc["view_url"] = f"/api/documents/{doc['document_id']}/view"
            doc["download_url"] = f"/api/documents/{doc['document_id']}/download"
            doc["reveal_url"] = f"/api/documents/{doc['document_id']}/reveal"
        except Exception:
            doc["status"] = "unresolved"

    return docs


def get_document(document_id: str) -> Optional[Dict[str, Any]]:
    for doc in list_documents():
        if doc.get("document_id") == document_id:
            return doc
    return None


def resolve_document_path(document_id: str) -> Path:
    raw_docs = _read_documents()
    doc = next((d for d in raw_docs if d.get("document_id") == document_id), None)

    if not doc:
        raise FileNotFoundError(f"Document not found: {document_id}")

    storage_mode = doc.get("storage_mode", "external_linked")

    if storage_mode == "external_linked":
        return resolve_repository_path(doc["repository_id"], doc["relative_path"])

    if storage_mode == "managed_copy":
        managed_path = doc.get("managed_path")
        if not managed_path:
            raise FileNotFoundError(f"Managed path missing for document: {document_id}")
        return Path(managed_path).expanduser().resolve()

    raise ValueError(f"Unsupported document storage_mode: {storage_mode}")


def _existing_key(doc: Dict[str, Any]) -> Tuple[str, str]:
    return (doc.get("repository_id", ""), doc.get("relative_path", ""))


def register_external_document(
    repository_id: str,
    relative_path: str,
    linked_scope: str = "unassigned",
    package_id: Optional[str] = None,
    line_id: Optional[str] = None,
    volume_id: Optional[str] = None,
) -> Dict[str, Any]:
    repo = get_repository(repository_id)
    if not repo:
        raise FileNotFoundError(f"Repository not found: {repository_id}")

    resolved = resolve_repository_path(repository_id, relative_path)

    if not resolved.exists():
        raise FileNotFoundError(f"Document file not found: {resolved}")

    docs = _read_documents()
    key = (repository_id, relative_path)

    for doc in docs:
        if _existing_key(doc) == key:
            doc["filename"] = resolved.name
            doc["document_type"] = classify_document_type(resolved.name)
            doc["linked_scope"] = linked_scope or doc.get("linked_scope", "unassigned")
            doc["package_id"] = package_id
            doc["line_id"] = line_id
            doc["volume_id"] = volume_id
            doc["updated_at"] = _utc_now()
            _write_documents(docs)
            return doc

    stat = resolved.stat()

    doc = {
        "document_id": f"doc_{uuid.uuid4().hex[:12]}",
        "filename": resolved.name,
        "document_type": classify_document_type(resolved.name),
        "storage_mode": "external_linked",
        "repository_id": repository_id,
        "relative_path": relative_path,
        "linked_scope": linked_scope,
        "package_id": package_id,
        "line_id": line_id,
        "volume_id": volume_id,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "notes": None,
    }

    docs.append(doc)
    _write_documents(docs)
    return doc


def register_managed_document_copy(
    *,
    source_path: str,
    document_type: Optional[str] = None,
    linked_scope: str = "msi_dataset",
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    source = Path(source_path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Document file not found: {source}")

    ext = source.suffix.lower()
    if ext in SEGY_EXTENSIONS:
        raise ValueError("SEG-Y files cannot be registered as supporting documents")
    if ext and ext not in DOCUMENT_EXTENSIONS:
        raise ValueError(f"Unsupported document extension for managed copy: {ext}")

    managed_root = REGISTRY_DIR.parent / "documents" / "managed_uploads"
    managed_root.mkdir(parents=True, exist_ok=True)

    document_id = f"doc_{uuid.uuid4().hex[:12]}"
    safe_name = source.name.replace("/", "_").replace("\\", "_")
    target = managed_root / f"{document_id}_{safe_name}"
    shutil.copy2(source, target)
    stat = target.stat()

    docs = _read_documents()
    now = _utc_now()
    doc = {
        "document_id": document_id,
        "filename": source.name,
        "document_type": document_type or classify_document_type(source.name),
        "storage_mode": "managed_copy",
        "managed_path": str(target),
        "original_path": str(source),
        "linked_scope": linked_scope,
        "package_id": None,
        "line_id": None,
        "volume_id": None,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "created_at": now,
        "updated_at": now,
        "notes": notes,
    }
    docs.append(doc)
    _write_documents(docs)
    return doc



def _sha256_bytes(data: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return "sha256:" + digest.hexdigest()


def register_managed_document_upload(
    *,
    filename: str,
    content: bytes,
    mime_type: Optional[str] = None,
    document_type: Optional[str] = None,
    linked_scope: str = "msi_dataset",
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    safe_source_name = Path(filename or "uploaded_document").name.replace("/", "_").replace("\\", "_")
    ext = Path(safe_source_name).suffix.lower()
    if ext in SEGY_EXTENSIONS:
        raise ValueError("SEG-Y files cannot be registered as supporting documents")
    if ext and ext not in DOCUMENT_EXTENSIONS:
        raise ValueError(f"Unsupported document extension for managed upload: {ext}")
    if not content:
        raise ValueError(f"Uploaded document is empty: {safe_source_name}")

    managed_root = REGISTRY_DIR.parent / "documents" / "managed_uploads"
    managed_root.mkdir(parents=True, exist_ok=True)

    document_id = f"doc_{uuid.uuid4().hex[:12]}"
    target = managed_root / f"{document_id}_{safe_source_name}"
    target.write_bytes(content)
    stat = target.stat()

    docs = _read_documents()
    now = _utc_now()
    doc = {
        "document_id": document_id,
        "filename": safe_source_name,
        "document_type": document_type or classify_document_type(safe_source_name),
        "storage_mode": "managed_copy",
        "managed_path": str(target),
        "original_path": None,
        "linked_scope": linked_scope,
        "package_id": None,
        "line_id": None,
        "volume_id": None,
        "size_bytes": stat.st_size,
        "checksum": _sha256_bytes(content),
        "mime_type": mime_type or mimetypes.guess_type(safe_source_name)[0] or "application/octet-stream",
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "created_at": now,
        "updated_at": now,
        "notes": notes,
    }
    docs.append(doc)
    _write_documents(docs)
    return doc


def scan_repository_for_documents(repository_id: str, max_files: int = 50000) -> Dict[str, Any]:
    repo = get_repository(repository_id)
    if not repo:
        raise FileNotFoundError(f"Repository not found: {repository_id}")

    root = Path(repo["root_path"]).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Repository root missing: {root}")

    registered = []
    skipped_segy = 0
    skipped_other = 0
    scanned = 0
    warnings = []

    for path in root.rglob("*"):
        if scanned >= max_files:
            warnings.append(f"Scan stopped at max_files={max_files}")
            break

        if not path.is_file():
            continue

        scanned += 1
        ext = path.suffix.lower()

        if ext in SEGY_EXTENSIONS:
            skipped_segy += 1
            continue

        if ext not in DOCUMENT_EXTENSIONS:
            skipped_other += 1
            continue

        try:
            rel = str(path.relative_to(root))
            doc = register_external_document(
                repository_id=repository_id,
                relative_path=rel,
                linked_scope="unassigned",
            )
            registered.append(doc)
        except Exception as exc:
            warnings.append(f"Failed to register {path}: {exc}")

    update_repository_scan_time(repository_id)

    return {
        "repository_id": repository_id,
        "repository_name": repo.get("name"),
        "root_path": str(root),
        "scanned_files": scanned,
        "registered_documents": len(registered),
        "skipped_segy_files": skipped_segy,
        "skipped_other_files": skipped_other,
        "warnings": warnings,
        "documents": registered,
    }

def upsert_scanned_document(
    *,
    repository_id: str,
    relative_path: str,
    linked_scope: str = "package_candidate",
    package_id: Optional[str] = None,
    line_id: Optional[str] = None,
    volume_id: Optional[str] = None,
    document_type: Optional[str] = None,
    classification_source: Optional[str] = None,
    classification_confidence: Optional[str] = None,
    classification_reasons: Optional[List[str]] = None,
    matched_terms: Optional[List[str]] = None,
    qaqc_flags: Optional[List[Dict[str, Any]]] = None,
    extension: Optional[str] = None,
    size_bytes: Optional[int] = None,
    modified_epoch: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Upsert one supporting document discovered by the repository package scanner.

    This is intentionally registry-level persistence. It does not rescan the
    filesystem and it does not copy source files. The source file remains
    externally linked under the source repository root.
    """
    normalized_relative_path = str(relative_path or "").replace("\\", "/").strip("/")
    if not normalized_relative_path:
        raise ValueError("relative_path is required for scanned document persistence")

    doc = register_external_document(
        repository_id=repository_id,
        relative_path=normalized_relative_path,
        linked_scope=linked_scope or "package_candidate",
        package_id=package_id,
        line_id=line_id,
        volume_id=volume_id,
    )

    docs = _read_documents()

    for existing in docs:
        if existing.get("document_id") != doc.get("document_id"):
            continue

        if document_type:
            existing["document_type"] = document_type
        if classification_source:
            existing["classification_source"] = classification_source
        if classification_confidence:
            existing["classification_confidence"] = classification_confidence
        if classification_reasons is not None:
            existing["classification_reasons"] = classification_reasons
        if matched_terms is not None:
            existing["matched_terms"] = matched_terms
        if qaqc_flags is not None:
            existing["qaqc_flags"] = qaqc_flags
        if extension:
            existing["extension"] = extension
        if size_bytes is not None:
            existing["size_bytes"] = size_bytes
        if modified_epoch is not None:
            existing["modified_epoch"] = modified_epoch

        existing["linked_scope"] = linked_scope or existing.get("linked_scope", "package_candidate")
        existing["package_id"] = package_id
        existing["line_id"] = line_id
        existing["volume_id"] = volume_id
        existing["storage_mode"] = "external_linked"
        existing["updated_at"] = _utc_now()

        doc = existing
        break

    _write_documents(docs)
    return doc


def prune_repository_documents(
    *,
    repository_id: str,
    keep_relative_paths: List[str],
) -> Dict[str, Any]:
    """
    Remove document registry rows for this repository that are no longer present
    in the latest repository scan snapshot.

    This keeps documents.json aligned with the repository inventory scan rather
    than accumulating stale source-document links.
    """
    keep = {
        str(path or "").replace("\\", "/").strip("/")
        for path in keep_relative_paths
        if str(path or "").strip()
    }

    docs = _read_documents()
    kept_docs: List[Dict[str, Any]] = []
    removed_docs: List[Dict[str, Any]] = []

    for doc in docs:
        if doc.get("repository_id") != repository_id:
            kept_docs.append(doc)
            continue

        rel = str(doc.get("relative_path") or "").replace("\\", "/").strip("/")
        if rel in keep:
            kept_docs.append(doc)
        else:
            removed_docs.append(doc)

    if removed_docs:
        _write_documents(kept_docs)

    return {
        "removed_count": len(removed_docs),
        "removed": [
            {
                "document_id": doc.get("document_id"),
                "filename": doc.get("filename"),
                "relative_path": doc.get("relative_path"),
            }
            for doc in removed_docs
        ],
    }

