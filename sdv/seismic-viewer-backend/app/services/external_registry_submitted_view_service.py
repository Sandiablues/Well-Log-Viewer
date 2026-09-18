from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json

from app.services.repository_registry_service import REGISTRY_DIR
from app.services.conversion_state_service import resolve_source_segy_conversion_state




def _write_json_list(name: str, value: List[Dict[str, Any]]) -> None:
    path = REGISTRY_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)

def _read_json_list(name: str) -> List[Dict[str, Any]]:
    path = REGISTRY_DIR / name
    if not path.exists():
        return []

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    return value if isinstance(value, list) else []




def _reconcile_submitted_segy_conversion_states(
    segy_files: List[Dict[str, Any]],
    submitted_segy_ids: set[str],
) -> List[Dict[str, Any]]:
    """
    Ensure External Registry never displays stale cached conversion status.

    The submitted view must use authoritative conversion state:
    explicit job_id + job record + Managed Data record + Zarr artifact.
    """
    changed = False

    for row in segy_files:
        if str(row.get("segy_file_id")) not in submitted_segy_ids:
            continue

        state = resolve_source_segy_conversion_state(
            row,
            jobs_dir="./data/jobs",
            volumes_json="./data/volumes.json",
            backend_root=".",
        )

        updates = state.as_updates()

        for key, value in updates.items():
            if row.get(key) != value:
                row[key] = value
                changed = True

        row["conversion_state_reason"] = state.reason
        row["conversion_state_authoritative"] = state.is_authoritative

    if changed:
        _write_json_list("segy_files.json", segy_files)

    return segy_files

def _by_id(items: List[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    return {
        str(item.get(key)): item
        for item in items
        if item.get(key)
    }


def build_submitted_external_registry_view(
    repository_id: str,
    mode: str = "2d",
) -> Dict[str, Any]:
    """
    Backend-owned External Data Registry view.

    This returns only QAQC-submitted / ready handoff records for the selected
    repository. It does not expose all scanned source inventory by default.
    """
    repositories = _read_json_list("repositories.json")
    packages = _read_json_list("packages.json")
    lines = _read_json_list("lines.json")
    segy_files = _read_json_list("segy_files.json")
    documents = _read_json_list("documents.json")
    staged_items = _read_json_list("staged_source_items.json")

    repository = next(
        (repo for repo in repositories if str(repo.get("repository_id")) == str(repository_id)),
        None,
    )

    submitted = [
        item for item in staged_items
        if str(item.get("repository_id")) == str(repository_id)
        and str(item.get("staged_for") or mode) == str(mode)
        and item.get("staging_status") == "submitted"
        and item.get("external_registry_status") == "ready"
    ]

    package_ids = {str(item.get("package_id")) for item in submitted if item.get("package_id")}
    line_ids = {str(item.get("line_id")) for item in submitted if item.get("line_id")}
    segy_ids = {str(item.get("segy_file_id")) for item in submitted if item.get("segy_file_id")}
    document_ids = {str(item.get("document_id")) for item in submitted if item.get("document_id")}

    segy_files = _reconcile_submitted_segy_conversion_states(segy_files, segy_ids)

    submitted_packages = [
        pkg for pkg in packages
        if str(pkg.get("repository_id")) == str(repository_id)
        and str(pkg.get("package_id")) in package_ids
    ]

    submitted_lines = [
        line for line in lines
        if str(line.get("repository_id")) == str(repository_id)
        and str(line.get("line_id")) in line_ids
    ]

    submitted_segy_files = [
        segy for segy in segy_files
        if str(segy.get("repository_id")) == str(repository_id)
        and str(segy.get("segy_file_id")) in segy_ids
    ]

    submitted_documents = [
        doc for doc in documents
        if str(doc.get("repository_id")) == str(repository_id)
        and str(doc.get("document_id")) in document_ids
    ]

    package_by_id = _by_id(submitted_packages, "package_id")
    line_by_id = _by_id(submitted_lines, "line_id")

    for pkg in submitted_packages:
        pid = str(pkg.get("package_id"))
        pkg["submitted_segy_count"] = sum(
            1 for item in submitted
            if str(item.get("package_id")) == pid and item.get("source_item_type") == "segy_file"
        )
        pkg["submitted_document_count"] = sum(
            1 for item in submitted
            if str(item.get("package_id")) == pid and item.get("source_item_type") == "document"
        )

    for line in submitted_lines:
        lid = str(line.get("line_id"))
        line["submitted_segy_count"] = sum(
            1 for item in submitted
            if str(item.get("line_id")) == lid and item.get("source_item_type") == "segy_file"
        )

    return {
        "status": "ok",
        "repository": repository,
        "mode": mode,
        "packages": submitted_packages,
        "lines": submitted_lines,
        "segy_files": submitted_segy_files,
        "documents": submitted_documents,
        "submitted_items": submitted,
        "summary": {
            "submitted_item_count": len(submitted),
            "submitted_package_count": len(package_ids),
            "submitted_line_count": len(line_ids),
            "submitted_segy_count": len(segy_ids),
            "submitted_document_count": len(document_ids),
        },
        "lookups": {
            "package_by_id": package_by_id,
            "line_by_id": line_by_id,
        },
    }
