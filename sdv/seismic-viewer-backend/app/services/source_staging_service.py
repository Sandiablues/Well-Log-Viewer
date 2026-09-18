from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import json

from app.services.repository_registry_service import REGISTRY_DIR, get_repository
from app.services.package_registry_service import list_packages, list_lines, list_segy_files
from app.services.document_registry_service import list_documents


STAGED_SOURCE_ITEMS_PATH = REGISTRY_DIR / "staged_source_items.json"

VALID_STAGE_MODES = {"2d", "3d"}
VALID_SOURCE_ITEM_TYPES = {"package", "line", "segy_file", "document"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_registry() -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    if not STAGED_SOURCE_ITEMS_PATH.exists():
        STAGED_SOURCE_ITEMS_PATH.write_text("[]", encoding="utf-8")


def _read_staged_items() -> List[Dict[str, Any]]:
    _ensure_registry()
    try:
        value = json.loads(STAGED_SOURCE_ITEMS_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _write_staged_items(value: List[Dict[str, Any]]) -> None:
    _ensure_registry()
    STAGED_SOURCE_ITEMS_PATH.write_text(
        json.dumps(value, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _stable_stage_id(repository_id: str, staged_for: str, item_type: str, item_id: str) -> str:
    joined = f"{repository_id}|{staged_for}|{item_type}|{item_id}"
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]
    return f"stage_{digest}"


def _repository_mode(repo: Dict[str, Any]) -> str:
    intended = str(repo.get("intended_use") or "").lower()
    structure = str(repo.get("source_structure_type") or "").lower()
    notes = str(repo.get("notes") or "").lower()
    text = f"{intended} {structure} {notes}"

    if "3d" in text:
        return "3d"
    return "2d"


def _validate_repository_mode(repo: Dict[str, Any], mode: str) -> None:
    if mode not in VALID_STAGE_MODES:
        raise ValueError(f"Invalid stage mode: {mode}")

    repo_mode = _repository_mode(repo)

    if repo_mode != mode:
        raise ValueError(
            f"Repository mode mismatch. Repository appears to be {repo_mode}, "
            f"but staging request was {mode}."
        )


def _by_id(records: List[Dict[str, Any]], id_field: str) -> Dict[str, Dict[str, Any]]:
    return {
        str(item.get(id_field)): item
        for item in records
        if item.get(id_field)
    }


def _selected_ids(selection: Dict[str, Any], key: str) -> List[str]:
    value = selection.get(key) or []
    if not isinstance(value, list):
        raise ValueError(f"Selection field must be a list: {key}")

    clean: List[str] = []
    seen: set[str] = set()

    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        clean.append(text)

    return clean


def _stage_record(
    *,
    repository_id: str,
    staged_for: str,
    item_type: str,
    item_id: str,
    source: Dict[str, Any],
) -> Dict[str, Any]:
    if item_type not in VALID_SOURCE_ITEM_TYPES:
        raise ValueError(f"Invalid staged item type: {item_type}")

    now = _utc_now()

    display_name = (
        source.get("display_name")
        or source.get("filename")
        or source.get("line_key")
        or item_id
    )

    record = {
        "staged_item_id": _stable_stage_id(repository_id, staged_for, item_type, item_id),
        "repository_id": repository_id,
        "staged_for": staged_for,
        "source_item_type": item_type,
        "source_item_id": item_id,
        "package_id": source.get("package_id") if item_type != "package" else item_id,
        "line_id": source.get("line_id") if item_type not in {"line"} else item_id,
        "segy_file_id": item_id if item_type == "segy_file" else source.get("segy_file_id"),
        "document_id": item_id if item_type == "document" else source.get("document_id"),
        "relative_path": source.get("relative_path"),
        "filename": source.get("filename"),
        "display_name": display_name,
        "source_status": source.get("status"),
        "candidate_kind": source.get("candidate_kind"),
        "candidate_role": source.get("candidate_role"),
        "document_type": source.get("document_type"),
        "conversion_status": source.get("conversion_status"),
        "staging_status": "staged",
        "staged_at": now,
        "updated_at": now,
    }

    return record


def stage_repository_selection(
    repository_id: str,
    *,
    mode: str,
    selection: Dict[str, Any],
    replace_existing: bool = False,
) -> Dict[str, Any]:
    """
    Persist a selected Source Intake handoff set.

    This does not index, convert, load, unload, or delete data. It creates a
    backend-owned staging registry that downstream External Data Registry /
    indexing / conversion workflows can consume.
    """
    repo = get_repository(repository_id)
    if not repo:
        raise FileNotFoundError(f"Repository not found: {repository_id}")

    _validate_repository_mode(repo, mode)

    package_ids = _selected_ids(selection, "package_ids")
    line_ids = _selected_ids(selection, "line_ids")
    segy_file_ids = _selected_ids(selection, "segy_file_ids")
    document_ids = _selected_ids(selection, "document_ids")

    packages = _by_id(list_packages(repository_id=repository_id), "package_id")
    lines = _by_id(list_lines(repository_id=repository_id), "line_id")
    segy_files = _by_id(list_segy_files(repository_id=repository_id), "segy_file_id")
    documents = _by_id(list_documents(repository_id=repository_id), "document_id")

    errors: List[Dict[str, Any]] = []
    incoming: List[Dict[str, Any]] = []

    def require(item_type: str, item_id: str, records: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        record = records.get(item_id)
        if not record:
            errors.append({
                "source_item_type": item_type,
                "source_item_id": item_id,
                "error": "Item not found in repository registry",
            })
            return None
        return record

    for item_id in package_ids:
        record = require("package", item_id, packages)
        if record:
            incoming.append(_stage_record(
                repository_id=repository_id,
                staged_for=mode,
                item_type="package",
                item_id=item_id,
                source=record,
            ))

    for item_id in line_ids:
        record = require("line", item_id, lines)
        if record:
            incoming.append(_stage_record(
                repository_id=repository_id,
                staged_for=mode,
                item_type="line",
                item_id=item_id,
                source=record,
            ))

    for item_id in segy_file_ids:
        record = require("segy_file", item_id, segy_files)
        if record:
            incoming.append(_stage_record(
                repository_id=repository_id,
                staged_for=mode,
                item_type="segy_file",
                item_id=item_id,
                source=record,
            ))

    for item_id in document_ids:
        record = require("document", item_id, documents)
        if record:
            incoming.append(_stage_record(
                repository_id=repository_id,
                staged_for=mode,
                item_type="document",
                item_id=item_id,
                source=record,
            ))

    if errors:
        return {
            "status": "error",
            "repository_id": repository_id,
            "staged_for": mode,
            "staged_count": 0,
            "errors": errors,
        }

    existing = _read_staged_items()

    if replace_existing:
        existing = [
            item for item in existing
            if not (
                item.get("repository_id") == repository_id
                and item.get("staged_for") == mode
            )
        ]

    by_stage_id = {
        item.get("staged_item_id"): item
        for item in existing
        if item.get("staged_item_id")
    }

    for item in incoming:
        old = by_stage_id.get(item["staged_item_id"], {})
        by_stage_id[item["staged_item_id"]] = {
            **old,
            **item,
            "created_at": old.get("created_at") or item.get("staged_at") or _utc_now(),
            "updated_at": _utc_now(),
        }

    staged_items = sorted(
        by_stage_id.values(),
        key=lambda item: (
            str(item.get("repository_id", "")),
            str(item.get("staged_for", "")),
            str(item.get("source_item_type", "")),
            str(item.get("display_name", "")),
        ),
    )

    _write_staged_items(staged_items)

    staged_for_repo = [
        item for item in staged_items
        if item.get("repository_id") == repository_id and item.get("staged_for") == mode
    ]

    return {
        "status": "ok",
        "repository_id": repository_id,
        "staged_for": mode,
        "requested_count": len(package_ids) + len(line_ids) + len(segy_file_ids) + len(document_ids),
        "staged_count": len(incoming),
        "total_staged_for_repository": len(staged_for_repo),
        "staged_items": incoming,
        "errors": [],
        "registry_path": str(STAGED_SOURCE_ITEMS_PATH),
    }


def list_staged_source_items(
    repository_id: Optional[str] = None,
    staged_for: Optional[str] = None,
) -> List[Dict[str, Any]]:
    items = _read_staged_items()

    if repository_id:
        items = [item for item in items if item.get("repository_id") == repository_id]

    if staged_for:
        items = [item for item in items if item.get("staged_for") == staged_for]

    return items


def clear_staged_source_items(
    repository_id: str,
    staged_for: Optional[str] = None,
) -> Dict[str, Any]:
    items = _read_staged_items()
    kept: List[Dict[str, Any]] = []
    removed: List[Dict[str, Any]] = []

    for item in items:
        matches_repo = item.get("repository_id") == repository_id
        matches_mode = staged_for is None or item.get("staged_for") == staged_for

        if matches_repo and matches_mode:
            removed.append(item)
        else:
            kept.append(item)

    if removed:
        _write_staged_items(kept)

    return {
        "status": "ok",
        "repository_id": repository_id,
        "staged_for": staged_for,
        "removed_count": len(removed),
    }


def submit_staged_source_items(
    repository_id: str,
    staged_for: str = "2d",
) -> Dict[str, Any]:
    """
    Mark currently staged source items as submitted to the External Data Registry handoff.

    This does not index, convert, load, unload, or delete data. It only advances
    staged source records from a selected/staged state into a submitted handoff state
    that the External Data Registry can consume.
    """
    repo = get_repository(repository_id)
    if not repo:
        raise FileNotFoundError(f"Repository not found: {repository_id}")

    if staged_for not in VALID_STAGE_MODES:
        raise ValueError(f"Invalid stage mode: {staged_for}")

    _validate_repository_mode(repo, staged_for)

    items = _read_staged_items()
    now = _utc_now()

    submitted_count = 0
    submitted_segy_count = 0
    submitted_document_count = 0
    submitted_package_count = 0
    submitted_line_count = 0

    for item in items:
        if item.get("repository_id") != repository_id:
            continue
        if item.get("staged_for") != staged_for:
            continue
        if item.get("staging_status") not in {"staged", "submitted"}:
            continue

        item["staging_status"] = "submitted"
        item["external_registry_status"] = "ready"
        item["submitted_at"] = item.get("submitted_at") or now
        item["updated_at"] = now

        submitted_count += 1

        item_type = item.get("source_item_type")
        if item_type == "segy_file":
            submitted_segy_count += 1
        elif item_type == "document":
            submitted_document_count += 1
        elif item_type == "package":
            submitted_package_count += 1
        elif item_type == "line":
            submitted_line_count += 1

    if submitted_count == 0:
        return {
            "status": "empty",
            "repository_id": repository_id,
            "staged_for": staged_for,
            "submitted_count": 0,
            "submitted_segy_count": 0,
            "submitted_document_count": 0,
            "submitted_package_count": 0,
            "submitted_line_count": 0,
            "message": "No staged items were available to submit.",
        }

    _write_staged_items(items)

    return {
        "status": "ok",
        "repository_id": repository_id,
        "staged_for": staged_for,
        "submitted_count": submitted_count,
        "submitted_segy_count": submitted_segy_count,
        "submitted_document_count": submitted_document_count,
        "submitted_package_count": submitted_package_count,
        "submitted_line_count": submitted_line_count,
        "external_registry_status": "ready",
        "submitted_at": now,
    }


def clear_submitted_handoff_items(
    repository_id: str,
    staged_for: str = "2d",
    confirm: bool = False,
) -> Dict[str, Any]:
    """
    Clear only the submitted External Data Registry handoff records for a repository.

    This preserves:
    - registered source repositories
    - packages
    - lines
    - source SEG-Y records
    - supporting document records
    - original files
    - Managed Data / Zarr / jobs / converted datasets
    """
    if not confirm:
        raise ValueError("Clear submitted handoff requires confirm=true")

    repo = get_repository(repository_id)
    if not repo:
        raise FileNotFoundError(f"Repository not found: {repository_id}")

    if staged_for not in VALID_STAGE_MODES:
        raise ValueError(f"Invalid stage mode: {staged_for}")

    _validate_repository_mode(repo, staged_for)

    items = _read_staged_items()

    retained = []
    cleared = []

    for item in items:
        matches_repository = item.get("repository_id") == repository_id
        matches_mode = item.get("staged_for") == staged_for
        is_submitted_handoff = (
            item.get("staging_status") == "submitted"
            and item.get("external_registry_status") == "ready"
        )

        if matches_repository and matches_mode and is_submitted_handoff:
            cleared.append(item)
        else:
            retained.append(item)

    _write_staged_items(retained)

    return {
        "status": "ok",
        "repository_id": repository_id,
        "staged_for": staged_for,
        "cleared_count": len(cleared),
        "cleared_segy_count": sum(1 for item in cleared if item.get("source_item_type") == "segy_file"),
        "cleared_document_count": sum(1 for item in cleared if item.get("source_item_type") == "document"),
        "preserved": [
            "registered source repository",
            "packages",
            "lines",
            "source SEG-Y records",
            "supporting document records",
            "original files",
            "Managed Data",
            "Zarr",
            "jobs",
            "converted datasets",
        ],
        "scope": "submitted_external_registry_handoff_only",
    }

