"""
Repository Source Intake / QAQC load-sheet service.

F3K scope:
- Read-only backend summary of existing repository scan/package records.
- Uses backend-owned knowledge classifications.
- Does not register, index, convert, load, unload, or delete datasets.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from app.knowledge import (
    classify_document_name,
    classify_segy_name,
    build_qaqc_flags,
)
from app.services.source_artifact_bucket_classifier import classify_source_record


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _first_present(record: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return default


def _merge_list(existing: Any, incoming: Any) -> list[Any]:
    if not existing:
        existing_items = []
    elif isinstance(existing, list):
        existing_items = list(existing)
    else:
        existing_items = [existing]

    if not incoming:
        incoming_items = []
    elif isinstance(incoming, list):
        incoming_items = list(incoming)
    else:
        incoming_items = [incoming]

    seen = set()
    merged = []
    for item in existing_items + incoming_items:
        marker = repr(item)
        if marker in seen:
            continue
        seen.add(marker)
        merged.append(item)
    return merged


def _is_segy_like(record: dict[str, Any], filename: str, relative_path: str) -> bool:
    ext = Path(filename).suffix.lower()
    if ext in {".sgy", ".segy"}:
        return True

    combined = f"{filename} {relative_path}".lower()
    if ".sgy" in combined or ".segy" in combined:
        return True

    file_type = _safe_str(
        _first_present(record, ("file_type", "kind", "type", "category"), "")
    ).lower()

    return file_type in {"segy", "seg-y", "seismic", "seismic_file"}


def _is_document_like(record: dict[str, Any], filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in {
        ".pdf", ".doc", ".docx", ".txt", ".asc", ".csv", ".xls", ".xlsx",
        ".tif", ".tiff", ".jpg", ".jpeg", ".png", ".las", ".ukooa", ".p190",
    }


def _normalize_scan_record(record: dict[str, Any]) -> dict[str, Any]:
    path_value = _first_present(
        record,
        (
            "relative_path",
            "path",
            "file_path",
            "source_path",
            "absolute_path",
            "full_path",
        ),
        "",
    )

    filename = _first_present(
        record,
        (
            "filename",
            "file_name",
            "name",
            "basename",
        ),
        None,
    )

    if not filename and path_value:
        filename = Path(_safe_str(path_value)).name

    filename = _safe_str(filename)
    relative_path = _safe_str(path_value)

    normalized: dict[str, Any] = {
        "filename": filename,
        "relative_path": relative_path,
        "size_bytes": record.get("size_bytes") or record.get("size") or record.get("file_size"),
    }

    if not filename:
        normalized.update({
            "item_type": "unknown",
            "classification_confidence": "low",
            "classification_reasons": ["missing_filename"],
            "qaqc_flags": build_qaqc_flags({
                "candidate_kind": "unknown",
                "classification_confidence": "low",
            }),
        })
        return normalized

    if _is_segy_like(record, filename, relative_path):
        kg = classify_segy_name(filename, relative_path)

        normalized.update({
            "item_type": "segy",
            "candidate_kind": record.get("candidate_kind") or kg.get("candidate_kind"),
            "candidate_role": record.get("candidate_role") or kg.get("candidate_role"),
            "classification_source": record.get("classification_source") or kg.get("classification_source"),
            "classification_confidence": record.get("classification_confidence") or kg.get("classification_confidence"),
            "classification_reasons": _merge_list(record.get("classification_reasons"), kg.get("classification_reasons")),
            "matched_terms": _merge_list(record.get("matched_terms"), kg.get("matched_terms")),
            "processing_hints": _merge_list(record.get("processing_hints"), kg.get("processing_hints")),
        })

        normalized["qaqc_flags"] = _merge_list(
            record.get("qaqc_flags"),
            build_qaqc_flags(normalized),
        )
        return classify_source_record(normalized)

    if _is_document_like(record, filename):
        doc = classify_document_name(filename, relative_path)

        normalized.update({
            "item_type": "document",
            "document_type": record.get("document_type") or doc.get("document_type"),
            "classification_source": record.get("classification_source") or doc.get("classification_source"),
            "classification_confidence": record.get("classification_confidence") or doc.get("classification_confidence"),
            "classification_reasons": _merge_list(record.get("classification_reasons"), doc.get("classification_reasons")),
            "matched_terms": _merge_list(record.get("matched_terms"), doc.get("matched_terms")),
            "qaqc_flags": _merge_list(record.get("qaqc_flags"), []),
        })
        return classify_source_record(normalized)

    normalized.update({
        "item_type": "unknown",
        "classification_confidence": record.get("classification_confidence") or "low",
        "classification_reasons": _merge_list(record.get("classification_reasons"), ["unrecognized_file_type"]),
        "qaqc_flags": _merge_list(
            record.get("qaqc_flags"),
            build_qaqc_flags({
                "candidate_kind": "unknown",
                "classification_confidence": record.get("classification_confidence") or "low",
            }),
        ),
    })

    return classify_source_record(normalized)


def _extract_records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in (
        "files",
        "items",
        "records",
        "candidates",
        "documents",
        "segy_files",
        "supporting_documents",
        "scan_records",
        "packages",
        "lines",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    records: list[dict[str, Any]] = []
    for value in payload.values():
        if isinstance(value, list):
            records.extend([item for item in value if isinstance(item, dict)])
    return records


def _try_package_registry(repository_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Prefer existing registry service accessors where available, because this is
    more stable than guessing JSON file locations.
    """
    errors: list[str] = []
    records: list[dict[str, Any]] = []

    try:
        from app.services.package_registry_service import list_packages, list_lines, list_segy_files
    except Exception as exc:
        return [], [f"package_registry_import_failed:{exc}"]

    for label, func in (
        ("packages", list_packages),
        ("lines", list_lines),
        ("segy_files", list_segy_files),
    ):
        try:
            value = func(repository_id=repository_id)
            extracted = _extract_records_from_payload(value)
            for item in extracted:
                copied = dict(item)
                copied.setdefault("_registry_source", label)
                records.append(copied)
        except Exception as exc:
            errors.append(f"{label}:{exc}")

    return records, errors


def _load_json(path: Path) -> Any:
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_scan_files(repository_id: str) -> list[Path]:
    backend_root = Path(__file__).resolve().parents[2]
    data_root = backend_root / "data"

    candidates = [
        data_root / "repositories" / repository_id / "scan.json",
        data_root / "repositories" / repository_id / "scan_results.json",
        data_root / "repositories" / repository_id / "package_scan.json",
        data_root / "repositories" / repository_id / "repository_scan.json",
        data_root / "repository_scans" / f"{repository_id}.json",
        data_root / "source_repositories" / repository_id / "scan.json",
        data_root / "source_repositories" / repository_id / "scan_results.json",
    ]

    if data_root.exists():
        for name in (
            "scan.json",
            "scan_results.json",
            "package_scan.json",
            "repository_scan.json",
        ):
            candidates.extend(data_root.glob(f"**/{repository_id}/**/{name}"))
            candidates.extend(data_root.glob(f"**/{repository_id}_{name}"))

    seen = set()
    unique = []
    for path in candidates:
        marker = str(path)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(path)

    return unique


def _records_from_scan_files(repository_id: str) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    errors: list[str] = []

    for path in _candidate_scan_files(repository_id):
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = _load_json(path)
            records = _extract_records_from_payload(payload)
            if records:
                return records, str(path), errors
        except Exception as exc:
            errors.append(f"{path}:{exc}")

    return [], None, errors


def _document_belongs_to_package(doc: dict[str, Any], package: dict[str, Any]) -> bool:
    package_id = _safe_str(package.get("package_id")).strip()
    package_path = _safe_str(package.get("relative_path")).strip().lower()
    package_name = _safe_str(package.get("display_name")).strip().lower()

    doc_package_id = _safe_str(doc.get("package_id")).strip()
    doc_rel = _safe_str(doc.get("relative_path")).strip().lower()
    doc_name = _safe_str(doc.get("filename")).strip().lower()

    if package_id and doc_package_id and package_id == doc_package_id:
        return True

    if package_path:
        if doc_rel == package_path or doc_rel.startswith(f"{package_path}/"):
            return True

    if package_name:
        if doc_rel.startswith(f"{package_name}/") or doc_name.startswith(package_name):
            return True

    return False


def _package_qaqc_flags(
    *,
    package: dict[str, Any],
    segy_items: list[dict[str, Any]],
    document_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []

    if not segy_items:
        flags.append({
            "code": "no_segy_files",
            "severity": "review",
            "message": "No SEG-Y files are associated with this package.",
        })

    if not document_items:
        flags.append({
            "code": "no_supporting_documents",
            "severity": "review",
            "message": "No supporting documents are associated with this package.",
        })

    if any(item.get("candidate_role") == "review_required" for item in segy_items):
        flags.append({
            "code": "segy_review_required",
            "severity": "review",
            "message": "One or more SEG-Y candidates require classification review.",
        })

    package_type = _safe_str(package.get("package_type"))
    if package_type == "documents_only":
        flags.append({
            "code": "documents_only_package",
            "severity": "review",
            "message": "Package contains supporting documents but no SEG-Y candidates.",
        })

    return flags



def _normalize_relative_path(value: Any) -> str:
    text = _safe_str(value).replace("\\", "/").strip("/")
    parts = [part for part in text.split("/") if part and part not in {".", ".."}]
    return "/".join(parts)


def _tree_node_id_for_path(relative_path: str, fallback_prefix: str = "node") -> str:
    import hashlib

    normalized = _normalize_relative_path(relative_path)
    if not normalized:
        return "root"

    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{fallback_prefix}_{digest}"


def _make_tree_node(
    *,
    name: str,
    node_type: str,
    relative_path: str,
    node_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    node = {
        "node_id": node_id or _tree_node_id_for_path(relative_path),
        "name": name,
        "node_type": node_type,
        "relative_path": _normalize_relative_path(relative_path),
        "children": [],
    }

    if extra:
        for key, value in extra.items():
            if value not in (None, ""):
                node[key] = value

    return node


def _insert_tree_path(
    root_node: dict[str, Any],
    *,
    relative_path: str,
    leaf_type: str,
    leaf_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, list[str]]:
    """
    Insert one scanned item into the repository tree.

    Returns:
      tree_node_id, tree_path_node_ids

    The tree is derived from persisted relative_path values, not live filesystem
    crawling. This keeps the Source Intake / QAQC view tied to the scan snapshot.
    """
    normalized = _normalize_relative_path(relative_path)
    if not normalized:
        return "root", ["root"]

    parts = normalized.split("/")
    current = root_node
    current_path_parts: list[str] = []
    path_node_ids = ["root"]

    for index, part in enumerate(parts):
        current_path_parts.append(part)
        current_rel = "/".join(current_path_parts)
        is_leaf = index == len(parts) - 1

        if is_leaf:
            node_type = leaf_type
            node_id = leaf_id or _tree_node_id_for_path(current_rel, leaf_type)
            node_extra = extra or {}
        else:
            node_type = "folder"
            node_id = _tree_node_id_for_path(current_rel, "folder")
            node_extra = {}

        children = current.setdefault("children", [])
        existing = next(
            (
                child for child in children
                if child.get("relative_path") == current_rel and child.get("node_type") == node_type
            ),
            None,
        )

        if existing is None:
            existing = _make_tree_node(
                name=part,
                node_type=node_type,
                relative_path=current_rel,
                node_id=node_id,
                extra=node_extra,
            )
            children.append(existing)
        else:
            if node_extra:
                for key, value in node_extra.items():
                    if value not in (None, ""):
                        existing[key] = value

        path_node_ids.append(existing["node_id"])
        current = existing

    return current["node_id"], path_node_ids


def _sort_tree(node: dict[str, Any]) -> dict[str, Any]:
    children = node.get("children") or []

    def sort_key(child: dict[str, Any]):
        node_type = child.get("node_type") or ""
        type_order = {
            "folder": 0,
            "segy_file": 1,
            "document": 2,
            "unknown": 3,
        }.get(node_type, 9)
        return (type_order, str(child.get("name") or "").lower())

    children.sort(key=sort_key)
    for child in children:
        _sort_tree(child)

    return node



def build_repository_load_sheet(repository_id: str) -> dict[str, Any]:
    """
    Build a read-only Source Intake / QAQC load sheet for a repository.

    Package-centered contract:
    - packages are review rows
    - SEG-Y files and documents are children/evidence
    - no registration/index/convert/load/unload side effects
    """
    errors: list[str] = []

    try:
        from app.services.repository_registry_service import get_repository
        from app.services.package_registry_service import list_packages, list_segy_files
        from app.services.document_registry_service import list_documents
    except Exception as exc:
        return {
            "repository_id": repository_id,
            "status": "service_import_failed",
            "load_errors": [str(exc)],
            "summary": {
                "package_count": 0,
                "segy_items": 0,
                "document_items": 0,
                "review_required_items": 0,
            },
            "packages": [],
            "items": [],
        }

    repository = get_repository(repository_id)
    if not repository:
        return {
            "repository_id": repository_id,
            "status": "repository_not_found",
            "load_errors": ["repository_not_found"],
            "summary": {
                "package_count": 0,
                "segy_items": 0,
                "document_items": 0,
                "review_required_items": 0,
            },
            "packages": [],
            "items": [],
        }

    repository_tree = _make_tree_node(
        name=repository.get("name") or repository_id,
        node_type="repository",
        relative_path="",
        node_id="root",
        extra={
            "repository_id": repository_id,
            "root_path": repository.get("root_path"),
        },
    )

    try:
        packages_raw = list_packages(repository_id=repository_id)
    except Exception as exc:
        packages_raw = []
        errors.append(f"packages:{exc}")

    try:
        segy_raw = list_segy_files(repository_id=repository_id)
    except Exception as exc:
        segy_raw = []
        errors.append(f"segy_files:{exc}")

    try:
        documents_raw = list_documents(repository_id=repository_id)
    except Exception as exc:
        documents_raw = []
        errors.append(f"documents:{exc}")

    segy_by_package: dict[str, list[dict[str, Any]]] = {}
    for record in segy_raw:
        normalized = _normalize_scan_record(record)
        normalized["segy_file_id"] = record.get("segy_file_id")
        normalized["package_id"] = record.get("package_id")
        normalized["line_id"] = record.get("line_id")
        normalized["conversion_status"] = record.get("conversion_status")
        normalized["volume_id"] = record.get("volume_id")
        normalized["job_id"] = record.get("job_id")
        normalized["zarr_url"] = record.get("zarr_url")
        tree_node_id, tree_path = _insert_tree_path(
            repository_tree,
            relative_path=record.get("relative_path") or normalized.get("relative_path") or normalized.get("filename") or "",
            leaf_type="segy_file",
            leaf_id=record.get("segy_file_id"),
            extra={
                "segy_file_id": record.get("segy_file_id"),
                "package_id": record.get("package_id"),
                "line_id": record.get("line_id"),
                "candidate_kind": normalized.get("candidate_kind"),
                "candidate_role": normalized.get("candidate_role"),
                "artifact_bucket": normalized.get("artifact_bucket"),
                "artifact_class": normalized.get("artifact_class"),
                "artifact_subtype": normalized.get("artifact_subtype"),
                "intake_role": normalized.get("intake_role"),
                "classification_confidence": normalized.get("classification_confidence"),
            },
        )
        normalized["tree_node_id"] = tree_node_id
        normalized["tree_path"] = tree_path
        normalized["source_record"] = {
            "segy_file_id": record.get("segy_file_id"),
            "package_id": record.get("package_id"),
            "line_id": record.get("line_id"),
        }
        segy_by_package.setdefault(_safe_str(record.get("package_id")), []).append(normalized)

    normalized_documents: list[dict[str, Any]] = []
    for record in documents_raw:
        normalized = _normalize_scan_record(record)
        normalized["document_id"] = record.get("document_id")
        normalized["package_id"] = record.get("package_id")
        normalized["line_id"] = record.get("line_id")
        normalized["volume_id"] = record.get("volume_id")
        normalized["view_url"] = record.get("view_url")
        normalized["download_url"] = record.get("download_url")
        normalized["reveal_url"] = record.get("reveal_url")
        normalized["linked_scope"] = record.get("linked_scope")

        tree_node_id, tree_path = _insert_tree_path(
            repository_tree,
            relative_path=record.get("relative_path") or normalized.get("relative_path") or normalized.get("filename") or "",
            leaf_type="document",
            leaf_id=record.get("document_id"),
            extra={
                "document_id": record.get("document_id"),
                "package_id": record.get("package_id"),
                "line_id": record.get("line_id"),
                "document_type": normalized.get("document_type"),
                "artifact_bucket": normalized.get("artifact_bucket"),
                "artifact_class": normalized.get("artifact_class"),
                "artifact_subtype": normalized.get("artifact_subtype"),
                "intake_role": normalized.get("intake_role"),
                "classification_confidence": normalized.get("classification_confidence"),
            },
        )
        normalized["tree_node_id"] = tree_node_id
        normalized["tree_path"] = tree_path

        normalized_documents.append(normalized)

    package_rows: list[dict[str, Any]] = []
    flat_items: list[dict[str, Any]] = []

    for package in packages_raw:
        package_rel = _normalize_relative_path(package.get("relative_path") or package.get("display_name") or "")
        if package_rel:
            _insert_tree_path(
                repository_tree,
                relative_path=package_rel,
                leaf_type="folder",
                leaf_id=_tree_node_id_for_path(package_rel, "folder"),
                extra={
                    "package_id": package.get("package_id"),
                    "package_type": package.get("package_type"),
                },
            )

        package_id = _safe_str(package.get("package_id"))
        segy_items = sorted(
            segy_by_package.get(package_id, []),
            key=lambda item: _safe_str(item.get("filename")).lower(),
        )

        document_items = sorted(
            [
                doc for doc in normalized_documents
                if _document_belongs_to_package(doc, package)
            ],
            key=lambda item: _safe_str(item.get("filename")).lower(),
        )

        flags = _package_qaqc_flags(
            package=package,
            segy_items=segy_items,
            document_items=document_items,
        )

        candidate_kind_counts = Counter(item.get("candidate_kind") or "none" for item in segy_items)
        document_type_counts = Counter(item.get("document_type") or "none" for item in document_items)
        artifact_bucket_counts = Counter(
            item.get("artifact_bucket") or "none"
            for item in segy_items + document_items
        )

        review_required_count = 0
        for item in segy_items + document_items:
            item_flags = item.get("qaqc_flags") or []
            if item.get("candidate_role") == "review_required":
                review_required_count += 1
                continue
            if any(
                isinstance(flag, dict) and flag.get("severity") in {"review", "warning"}
                for flag in item_flags
            ):
                review_required_count += 1

        package_tree_rel = _normalize_relative_path(package.get("relative_path") or package.get("display_name") or "")
        package_row = {
            "package_id": package.get("package_id"),
            "repository_id": package.get("repository_id"),
            "display_name": package.get("display_name"),
            "relative_path": package.get("relative_path"),
            "tree_node_id": _tree_node_id_for_path(package_tree_rel, "folder") if package_tree_rel else "root",
            "package_type": package.get("package_type"),
            "scan_status": package.get("scan_status"),
            "last_scanned_at": package.get("last_scanned_at"),
            "counts": {
                "segy": len(segy_items),
                "documents": len(document_items),
                "review_required": review_required_count,
                "candidate_kind_counts": dict(candidate_kind_counts),
                "document_type_counts": dict(document_type_counts),
                "artifact_bucket_counts": dict(artifact_bucket_counts),
            },
            "segy_files": segy_items,
            "documents": document_items,
            "qaqc_flags": flags,
        }

        package_rows.append(package_row)
        flat_items.extend(segy_items)
        flat_items.extend(document_items)

    unassigned_documents = [
        doc for doc in normalized_documents
        if not any(
            _document_belongs_to_package(doc, package)
            for package in packages_raw
        )
    ]

    total_review_required = sum(
        row["counts"]["review_required"] + len(row.get("qaqc_flags") or [])
        for row in package_rows
    )

    candidate_kind_counts = Counter()
    document_type_counts = Counter()
    artifact_bucket_counts = Counter()
    for row in package_rows:
        candidate_kind_counts.update(row["counts"]["candidate_kind_counts"])
        document_type_counts.update(row["counts"]["document_type_counts"])
        artifact_bucket_counts.update(row["counts"].get("artifact_bucket_counts") or {})

    status = "ok" if package_rows or flat_items or unassigned_documents else "scan_not_found"

    return {
        "repository_id": repository_id,
        "repository": {
            "repository_id": repository.get("repository_id"),
            "name": repository.get("name"),
            "root_path": repository.get("root_path"),
            "source_structure_type": repository.get("source_structure_type"),
            "intended_use": repository.get("intended_use"),
            "status": repository.get("status"),
            "last_scanned_at": repository.get("last_scanned_at"),
        },
        "status": status,
        "source": "package_registry_service",
        "load_errors": errors,
        "summary": {
            "package_count": len(package_rows),
            "segy_items": sum(row["counts"]["segy"] for row in package_rows),
            "document_items": sum(row["counts"]["documents"] for row in package_rows) + len(unassigned_documents),
            "unassigned_document_items": len(unassigned_documents),
            "review_required_items": total_review_required,
            "candidate_kind_counts": dict(candidate_kind_counts),
            "document_type_counts": dict(document_type_counts),
            "artifact_bucket_counts": dict(artifact_bucket_counts),
        },
        "packages": package_rows,
        "unassigned_documents": unassigned_documents,
        "items": flat_items,
        "repository_tree": _sort_tree(repository_tree),
    }

