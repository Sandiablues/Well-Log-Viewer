
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import hashlib
import json

from app.services.repository_registry_service import REGISTRY_DIR
from app.services.repository_package_scanner_service import scan_repository_packages
from app.services.document_registry_service import (
    DOCUMENT_EXTENSIONS,
    list_documents,
    register_external_document,
)


PACKAGES_PATH = REGISTRY_DIR / "packages.json"
LINES_PATH = REGISTRY_DIR / "lines.json"
SEGY_FILES_PATH = REGISTRY_DIR / "segy_files.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_registry() -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)


def _stable_id(prefix: str, *parts: str) -> str:
    joined = "|".join(parts)
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _write_json_list(path: Path, value: List[Dict[str, Any]]) -> None:
    _ensure_registry()
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _merge_by_id(
    existing: List[Dict[str, Any]],
    incoming: List[Dict[str, Any]],
    id_field: str,
) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}

    for item in existing:
        item_id = item.get(id_field)
        if item_id:
            by_id[item_id] = item

    conversion_fields = {
        "conversion_status",
        "volume_id",
        "job_id",
        "zarr_url",
        "converted_at",
        "conversion_queued_at",
        "conversion_error",
    }

    for item in incoming:
        item_id = item.get(id_field)
        if not item_id:
            continue

        old = by_id.get(item_id, {})
        merged = {
            **old,
            **item,
            "created_at": old.get("created_at") or item.get("created_at") or _utc_now(),
            "updated_at": _utc_now(),
        }

        # A repository rescan inventories source files only.
        # It must not erase prior conversion state for SEG-Y registry records.
        if id_field == "segy_file_id" and old:
            old_status = old.get("conversion_status")
            if old_status and old_status != "not_converted":
                for field in conversion_fields:
                    if field in old:
                        merged[field] = old[field]

        by_id[item_id] = merged

    return sorted(
        by_id.values(),
        key=lambda item: (
            str(item.get("repository_id", "")),
            str(item.get("display_name", "")),
            str(item.get(id_field, "")),
        ),
    )


def _replace_repository_scan_records(
    existing: List[Dict[str, Any]],
    incoming: List[Dict[str, Any]],
    id_field: str,
    repository_id: str,
) -> List[Dict[str, Any]]:
    """
    Replace the active source-inventory records for one repository with the
    latest scan result while preserving conversion fields for matching SEG-Y
    records.

    Source Intake repository summaries must describe the current scan scope,
    not stale records from earlier scans with a different root/subfolder scope
    or older repository contents. Managed outputs remain in MSI/Managed Data;
    stale source inventory rows should not continue to drive repository-card
    counts or workbench candidates.
    """
    clean_repo = str(repository_id or "").strip()
    incoming_ids = {str(item.get(id_field) or "").strip() for item in incoming if item.get(id_field)}

    kept_other_repositories = [
        item for item in existing
        if str(item.get("repository_id") or "").strip() != clean_repo
    ]

    existing_matching_incoming = [
        item for item in existing
        if str(item.get("repository_id") or "").strip() == clean_repo
        and str(item.get(id_field) or "").strip() in incoming_ids
    ]

    refreshed_this_repository = _merge_by_id(existing_matching_incoming, incoming, id_field)
    return sorted(
        kept_other_repositories + refreshed_this_repository,
        key=lambda item: (
            str(item.get("repository_id", "")),
            str(item.get("display_name", "")),
            str(item.get(id_field, "")),
        ),
    )


def _document_relative_path_from_record(record: Dict[str, Any]) -> str:
    value = (
        record.get("relative_path")
        or record.get("path")
        or record.get("file_path")
        or record.get("source_path")
        or ""
    )
    return str(value).replace("\\", "/").strip("/")


def _document_records_from_package(pkg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Scanner packages may expose documents under different keys depending on
    the scan path. Normalize those shapes here and persist only known
    document extensions. This keeps package counts and document registry
    records aligned without treating package document_count as truth.
    """
    records: List[Dict[str, Any]] = []

    for key in ("documents", "supporting_documents", "document_files", "other_files"):
        value = pkg.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    records.append(item)

    unique: Dict[str, Dict[str, Any]] = {}

    for record in records:
        rel = _document_relative_path_from_record(record)
        filename = str(record.get("filename") or Path(rel).name or "")
        suffix = Path(filename or rel).suffix.lower()

        if not rel:
            continue

        if suffix not in DOCUMENT_EXTENSIONS:
            continue

        unique[rel] = record

    return list(unique.values())


def _register_scanned_documents(
    *,
    repository_id: str,
    package_id_by_relative_path: Dict[str, str],
    scan_packages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    registered: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for pkg in scan_packages:
        package_rel = str(pkg.get("relative_path") or "").replace("\\", "/").strip("/")
        package_id = package_id_by_relative_path.get(package_rel)

        for doc_record in _document_records_from_package(pkg):
            rel = _document_relative_path_from_record(doc_record)
            if not rel:
                continue

            try:
                doc = register_external_document(
                    repository_id=repository_id,
                    relative_path=rel,
                    linked_scope="package",
                    package_id=package_id,
                    line_id=None,
                    volume_id=None,
                )

                # Preserve scanner/KM enrichment where available.
                updates = {}
                for key in (
                    "document_type",
                    "classification_source",
                    "classification_confidence",
                    "classification_reasons",
                    "matched_terms",
                    "qaqc_flags",
                ):
                    if doc_record.get(key) not in (None, "", []):
                        updates[key] = doc_record.get(key)

                if updates:
                    from app.services import document_registry_service as _doc_registry

                    docs = _doc_registry._read_documents()
                    for existing in docs:
                        if existing.get("document_id") == doc.get("document_id"):
                            existing.update(updates)
                            existing["updated_at"] = _utc_now()
                            doc.update(updates)
                            break
                    _doc_registry._write_documents(docs)

                registered.append(doc)
            except Exception as exc:
                errors.append({
                    "relative_path": rel,
                    "error": str(exc),
                })

    return {
        "registered_count": len(registered),
        "errors": errors,
    }


def persist_repository_scan(repository_id: str, max_files: int = 100000, include_subfolders: bool | None = None) -> Dict[str, Any]:
    """
    Scan a repository and persist package/line/SEG-Y file registries.

    This does not convert data and does not mutate the source repository.
    """
    scan = scan_repository_packages(
        repository_id=repository_id,
        max_files=max_files,
        include_subfolders=include_subfolders,
    )
    now = _utc_now()

    incoming_packages: List[Dict[str, Any]] = []
    incoming_lines: List[Dict[str, Any]] = []
    incoming_segy_files: List[Dict[str, Any]] = []
    package_id_by_relative_path: Dict[str, str] = {}

    for pkg in scan.get("packages", []):
        package_id = _stable_id(
            "pkg",
            repository_id,
            pkg.get("relative_path", ""),
            pkg.get("display_name", ""),
        )

        package_id_by_relative_path[str(pkg.get("relative_path", "")).replace("\\", "/").strip("/")] = package_id

        incoming_packages.append({
            "package_id": package_id,
            "repository_id": repository_id,
            "display_name": pkg.get("display_name"),
            "relative_path": pkg.get("relative_path", ""),
            "package_key": pkg.get("package_key"),
            "package_type": pkg.get("package_type"),
            "segy_count": pkg.get("segy_count", 0),
            "document_count": pkg.get("document_count", 0),
            "line_count": pkg.get("line_count", 0),
            "other_files_count": pkg.get("other_files_count", 0),
            "scan_status": "scanned",
            "last_scanned_at": now,
            "created_at": now,
            "updated_at": now,
        })

        for line in pkg.get("lines", []):
            line_id = _stable_id(
                "line",
                repository_id,
                package_id,
                line.get("line_key", ""),
            )

            incoming_lines.append({
                "line_id": line_id,
                "package_id": package_id,
                "repository_id": repository_id,
                "line_key": line.get("line_key"),
                "display_name": line.get("display_name"),
                "line_identity_status": line.get("line_identity_status"),
                "version_status": line.get("version_status"),
                "segy_count": line.get("segy_count", 0),
                "created_at": now,
                "updated_at": now,
                "last_scanned_at": now,
            })

            for segy in line.get("segy_files", []):
                segy_file_id = _stable_id(
                    "segy",
                    repository_id,
                    package_id,
                    line_id,
                    segy.get("relative_path", ""),
                    str(segy.get("size_bytes")),
                )

                incoming_segy_files.append({
                    "segy_file_id": segy_file_id,
                    "repository_id": repository_id,
                    "package_id": package_id,
                    "line_id": line_id,
                    "filename": segy.get("filename"),
                    "relative_path": segy.get("relative_path"),
                    "extension": segy.get("extension"),
                    "size_bytes": segy.get("size_bytes"),
                    "modified_epoch": segy.get("modified_epoch"),
                    "inferred_line_key": segy.get("inferred_line_key"),
                    "survey_name": segy.get("survey_name"),
                    "line_name": segy.get("line_name"),
                    "volume_name": segy.get("volume_name"),
                    "identity_candidates": segy.get("identity_candidates", []),
                    "identity_extraction": segy.get("identity_extraction", {}),
                    "relationship_status": segy.get("relationship_status"),
                    "candidate_kind": segy.get("candidate_kind", "unknown"),
                    "candidate_role": segy.get("candidate_role", "review_required"),
                    "classification_source": segy.get("classification_source", "unclassified"),
                    "classification_confidence": segy.get("classification_confidence", "low"),
                    "classification_reasons": segy.get("classification_reasons", []),
                    # Important: a scan only inventories source files.
                    # It must not reset conversion state for existing records.
                    "conversion_status": "not_converted",
                    "volume_id": None,
                    "created_at": now,
                    "updated_at": now,
                    "last_scanned_at": now,
                })

    existing_packages = _read_json_list(PACKAGES_PATH)
    existing_lines = _read_json_list(LINES_PATH)
    existing_segy_files = _read_json_list(SEGY_FILES_PATH)

    packages = _replace_repository_scan_records(existing_packages, incoming_packages, "package_id", repository_id)
    lines = _replace_repository_scan_records(existing_lines, incoming_lines, "line_id", repository_id)
    segy_files = _replace_repository_scan_records(existing_segy_files, incoming_segy_files, "segy_file_id", repository_id)

    _write_json_list(PACKAGES_PATH, packages)
    _write_json_list(LINES_PATH, lines)
    _write_json_list(SEGY_FILES_PATH, segy_files)

    document_persistence = _register_scanned_documents(
        repository_id=repository_id,
        package_id_by_relative_path=package_id_by_relative_path,
        scan_packages=scan.get("packages", []),
    )

    return {
        "repository_id": repository_id,
        "summary": {
            **(scan.get("summary", {}) or {}),
            "document_registry_count": len(list_documents(repository_id=repository_id)),
            "document_persisted_count": document_persistence.get("registered_count", 0),
            "document_persistence_error_count": len(document_persistence.get("errors", [])),
        },
        "document_persistence": document_persistence,
        "persisted": {
            "packages_written": len(incoming_packages),
            "lines_written": len(incoming_lines),
            "segy_files_written": len(incoming_segy_files),
            "packages_registry_total": len(packages),
            "lines_registry_total": len(lines),
            "segy_files_registry_total": len(segy_files),
        },
        "registry_paths": {
            "packages": str(PACKAGES_PATH),
            "lines": str(LINES_PATH),
            "segy_files": str(SEGY_FILES_PATH),
        },
        "warnings": scan.get("warnings", []),
    }


def list_packages(repository_id: str | None = None) -> List[Dict[str, Any]]:
    packages = _read_json_list(PACKAGES_PATH)
    if repository_id:
        packages = [p for p in packages if p.get("repository_id") == repository_id]
    return packages


def list_lines(package_id: str | None = None, repository_id: str | None = None) -> List[Dict[str, Any]]:
    lines = _read_json_list(LINES_PATH)

    if package_id:
        lines = [l for l in lines if l.get("package_id") == package_id]

    if repository_id:
        lines = [l for l in lines if l.get("repository_id") == repository_id]

    return lines


def list_segy_files(
    package_id: str | None = None,
    line_id: str | None = None,
    repository_id: str | None = None,
) -> List[Dict[str, Any]]:
    files = _read_json_list(SEGY_FILES_PATH)

    if package_id:
        files = [f for f in files if f.get("package_id") == package_id]

    if line_id:
        files = [f for f in files if f.get("line_id") == line_id]

    if repository_id:
        files = [f for f in files if f.get("repository_id") == repository_id]

    return files

def get_segy_file(segy_file_id: str) -> Dict[str, Any] | None:
    for item in _read_json_list(SEGY_FILES_PATH):
        if item.get("segy_file_id") == segy_file_id:
            return item
    return None


def update_segy_file_conversion(
    segy_file_id: str,
    conversion_status: str,
    volume_id: str | None = None,
    job_id: str | None = None,
    zarr_url: str | None = None,
    storage_uri: str | None = None,
    error: str | None = None,
    clear_error: bool = False,
    conversion_state_reason: str | None = None,
    conversion_state_authoritative: bool | None = None,
    conversion_queued_at: str | None = None,
    converted_at: str | None = None,
) -> Dict[str, Any]:
    files = _read_json_list(SEGY_FILES_PATH)
    updated: Dict[str, Any] | None = None

    for item in files:
        if item.get("segy_file_id") == segy_file_id:
            item["conversion_status"] = conversion_status
            item["updated_at"] = _utc_now()

            if volume_id is not None:
                item["volume_id"] = volume_id

            if job_id is not None:
                item["job_id"] = job_id

            if zarr_url is not None:
                item["zarr_url"] = zarr_url

            if storage_uri is not None:
                item["storage_uri"] = storage_uri

            if clear_error:
                item["conversion_error"] = None
            elif error is not None:
                item["conversion_error"] = error

            if conversion_state_reason is not None:
                item["conversion_state_reason"] = conversion_state_reason

            if conversion_state_authoritative is not None:
                item["conversion_state_authoritative"] = conversion_state_authoritative

            if conversion_queued_at is not None:
                item["conversion_queued_at"] = conversion_queued_at
            elif conversion_status in {"queued", "converting"}:
                item["conversion_queued_at"] = item.get("conversion_queued_at") or _utc_now()

            if converted_at is not None:
                item["converted_at"] = converted_at
            elif conversion_status in {"converted", "ready"}:
                item["converted_at"] = _utc_now()

            updated = item
            break

    if updated is None:
        raise FileNotFoundError(f"SEG-Y file not found in registry: {segy_file_id}")

    _write_json_list(SEGY_FILES_PATH, files)
    return updated


def reset_segy_file_conversion_state(
    segy_file_id: str,
    *,
    reason: str = "managed_data_full_delete",
) -> Dict[str, Any]:
    """
    Reset a source SEG-Y registry row after full managed artifact deletion.

    This intentionally clears the source-to-managed conversion linkage so
    historical completed jobs cannot auto-recreate Managed Data rows and the
    row can be converted again through Source Intake.
    """
    clean_id = str(segy_file_id or "").strip()
    if not clean_id:
        raise ValueError("segy_file_id is required")

    files = _read_json_list(SEGY_FILES_PATH)
    updated: Dict[str, Any] | None = None

    for item in files:
        if item.get("segy_file_id") == clean_id:
            item["conversion_status"] = "not_converted"
            item["volume_id"] = None
            item["job_id"] = None
            item["zarr_url"] = None
            item["storage_uri"] = None
            item["representation_id"] = None
            item["msi_representation_id"] = None
            item["managed_representation_id"] = None
            item["physical_volume_id"] = None
            item["viewer_ready"] = False
            item["conversion_error"] = None
            item["converted_at"] = None
            item["conversion_queued_at"] = None
            item["conversion_state_reason"] = reason
            item["conversion_state_authoritative"] = True
            item["updated_at"] = _utc_now()
            updated = item
            break

    if updated is None:
        raise FileNotFoundError(f"SEG-Y file not found in registry: {clean_id}")

    _write_json_list(SEGY_FILES_PATH, files)
    return updated

