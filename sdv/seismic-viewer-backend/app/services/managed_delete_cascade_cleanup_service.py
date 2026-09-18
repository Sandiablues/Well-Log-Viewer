from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import json
import shutil

from app.services.repository_registry_service import REGISTRY_DIR
from app.services.document_registry_service import DOCUMENTS_PATH
from app.storage.service import is_endrepo_zarr_url, resolve_endrepo_zarr_url_path


DATA_DIR = REGISTRY_DIR.parent
ATTACHMENTS_PATH = REGISTRY_DIR / "msi_document_attachments.json"
VOLUMES_PATH = DATA_DIR / "volumes.json"

# MD_DELETE_CASCADE_1B_SIDECARS
# Managed Zarr deletion must also remove sibling metadata/header sidecars.
MANAGED_ZARR_SIDECAR_SUFFIXES = (
    ".viewer_metadata.json",
    ".trace_header_summary.json",
    ".segy_binary_header.json",
    ".segy_text_header.txt",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _extract_source_segy_file_id(representation_id: str, dataset_id: str | None = None) -> str:
    dataset_text = _clean(dataset_id)
    if dataset_text.startswith("source_segy:"):
        return dataset_text.split(":", 1)[1]

    text = _clean(representation_id)
    marker = "msi_repr:source_segy_"
    if text.startswith(marker) and ":zarr_" in text:
        return text[len(marker):].split(":zarr_", 1)[0].strip()

    return ""


def _extract_physical_volume_id(representation_id: str, physical_volume_id: str | None = None) -> str:
    explicit = _clean(physical_volume_id)
    if explicit:
        return explicit

    text = _clean(representation_id)
    if ":zarr_" in text:
        return text.rsplit(":zarr_", 1)[1].strip()

    return ""


def _remove_path(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {"path": str(path), "removed": False, "reason": "missing"}
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return {"path": str(path), "removed": True}
    except Exception as exc:
        return {"path": str(path), "removed": False, "reason": str(exc)}


def _sidecar_paths_for_artifact_path(path: Path) -> list[Path]:
    """
    Return sibling metadata/header sidecars for a managed Zarr artifact path.

    The main Zarr directory can already be gone by the time residual cleanup runs,
    so sidecar discovery must be name-based and must not depend on path.exists().
    """
    raw = str(path)
    candidates: list[Path] = []
    for suffix in MANAGED_ZARR_SIDECAR_SUFFIXES:
        if raw.endswith(suffix):
            continue
        candidates.append(Path(raw + suffix))

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _remove_sidecars_for_artifact_path(path: Path) -> list[Dict[str, Any]]:
    return [_remove_path(sidecar) for sidecar in _sidecar_paths_for_artifact_path(path)]


def _artifact_paths_from_volume_entry(entry: Dict[str, Any]) -> list[Path]:
    paths: list[Path] = []

    zarr_url = _clean(entry.get("zarr_url"))
    if zarr_url and is_endrepo_zarr_url(zarr_url):
        try:
            paths.append(resolve_endrepo_zarr_url_path(zarr_url))
        except Exception:
            pass

    for key in ("storage_uri", "volume_path", "path", "local_path"):
        value = _clean(entry.get(key))
        if value.startswith("/"):
            paths.append(Path(value).expanduser().resolve())

    metadata = entry.get("metadata")
    if isinstance(metadata, dict):
        for value in metadata.values():
            if isinstance(value, str) and value.startswith("/"):
                paths.append(Path(value).expanduser().resolve())

    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        text = str(path)
        if text not in seen:
            seen.add(text)
            deduped.append(path)
    return deduped


def cleanup_volume_registry_record(
    *,
    physical_volume_id: str | None,
    delete_artifact_paths: bool = True,
) -> Dict[str, Any]:
    target = _clean(physical_volume_id)
    result: Dict[str, Any] = {
        "path": str(VOLUMES_PATH),
        "physical_volume_id": target,
        "removed_count": 0,
        "removed_entries": [],
        "artifact_path_results": [],
        "artifact_sidecar_results": [],
    }
    if not target:
        result["skipped"] = "missing_physical_volume_id"
        return result

    payload = _read_json(VOLUMES_PATH, None)
    if payload is None:
        result["skipped"] = "volumes_json_missing_or_unreadable"
        return result

    removed_entries: list[Dict[str, Any]] = []

    def is_match(entry: Any, key: str | None = None) -> bool:
        if key == target:
            return True
        if isinstance(entry, dict):
            return (
                _clean(entry.get("id")) == target
                or _clean(entry.get("volume_id")) == target
                or _clean(entry.get("physical_volume_id")) == target
            )
        return False

    if isinstance(payload, dict):
        kept: Dict[str, Any] = {}
        for key, entry in payload.items():
            if is_match(entry, key):
                if isinstance(entry, dict):
                    removed_entries.append(entry)
                else:
                    removed_entries.append({"key": key, "value": entry})
                continue
            kept[key] = entry
        if len(kept) != len(payload):
            _write_json(VOLUMES_PATH, kept)

    elif isinstance(payload, list):
        kept_list = []
        for entry in payload:
            if is_match(entry):
                if isinstance(entry, dict):
                    removed_entries.append(entry)
                else:
                    removed_entries.append({"value": entry})
                continue
            kept_list.append(entry)
        if len(kept_list) != len(payload):
            _write_json(VOLUMES_PATH, kept_list)
    else:
        result["skipped"] = "unsupported_volumes_json_shape"
        return result

    result["removed_count"] = len(removed_entries)
    result["removed_entries"] = [
        {
            "id": entry.get("id") if isinstance(entry, dict) else None,
            "display_name": (entry.get("display_name") or entry.get("filename")) if isinstance(entry, dict) else None,
            "zarr_url": entry.get("zarr_url") if isinstance(entry, dict) else None,
            "storage_uri": entry.get("storage_uri") if isinstance(entry, dict) else None,
        }
        for entry in removed_entries
    ]

    if delete_artifact_paths:
        seen_paths: set[str] = set()
        for entry in removed_entries:
            if not isinstance(entry, dict):
                continue
            for path in _artifact_paths_from_volume_entry(entry):
                text = str(path)
                if text in seen_paths:
                    continue
                seen_paths.add(text)
                result["artifact_path_results"].append(_remove_path(path))
                result["artifact_sidecar_results"].extend(_remove_sidecars_for_artifact_path(path))

    return result


def cleanup_document_attachments_for_deleted_target(
    *,
    representation_id: str,
    dataset_id: str | None = None,
    delete_orphan_managed_documents: bool = True,
) -> Dict[str, Any]:
    clean_rep = _clean(representation_id)
    clean_dataset = _clean(dataset_id)

    result: Dict[str, Any] = {
        "path": str(ATTACHMENTS_PATH),
        "representation_id": clean_rep,
        "dataset_id": clean_dataset or None,
        "removed_attachment_count": 0,
        "removed_attachment_ids": [],
        "removed_document_ids": [],
        "removed_document_files": [],
        "skipped_document_ids": [],
    }

    rows = _read_json(ATTACHMENTS_PATH, [])
    if not isinstance(rows, list):
        result["skipped"] = "attachments_store_not_list"
        return result

    removed_rows: list[Dict[str, Any]] = []
    kept_rows: list[Dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            kept_rows.append(row)
            continue

        row_rep = _clean(row.get("representation_id"))
        row_target = _clean(row.get("target_input_id"))
        row_dataset = _clean(row.get("dataset_id"))

        remove = False
        if clean_rep and (row_rep == clean_rep or row_target == clean_rep):
            remove = True
        elif clean_dataset and row_dataset == clean_dataset:
            remove = True

        if remove:
            removed_rows.append(row)
        else:
            kept_rows.append(row)

    if removed_rows:
        _write_json(ATTACHMENTS_PATH, kept_rows)

    removed_doc_ids = sorted({
        _clean(row.get("document_id"))
        for row in removed_rows
        if _clean(row.get("document_id"))
    })

    result["removed_attachment_count"] = len(removed_rows)
    result["removed_attachment_ids"] = [
        _clean(row.get("attachment_id"))
        for row in removed_rows
        if _clean(row.get("attachment_id"))
    ]

    if not delete_orphan_managed_documents or not removed_doc_ids:
        return result

    remaining_doc_ids = {
        _clean(row.get("document_id"))
        for row in kept_rows
        if isinstance(row, dict) and _clean(row.get("document_id"))
    }

    docs = _read_json(DOCUMENTS_PATH, [])
    if not isinstance(docs, list):
        result["document_cleanup_skipped"] = "documents_store_not_list"
        return result

    target_doc_ids = [doc_id for doc_id in removed_doc_ids if doc_id not in remaining_doc_ids]
    target_set = set(target_doc_ids)

    kept_docs = []
    changed_docs = False

    for doc in docs:
        if not isinstance(doc, dict):
            kept_docs.append(doc)
            continue

        doc_id = _clean(doc.get("document_id"))
        if doc_id not in target_set:
            kept_docs.append(doc)
            continue

        storage_mode = _clean(doc.get("storage_mode"))
        managed_path = _clean(doc.get("managed_path"))

        if storage_mode != "managed_copy":
            result["skipped_document_ids"].append({
                "document_id": doc_id,
                "reason": "not_managed_copy",
                "storage_mode": storage_mode,
            })
            kept_docs.append(doc)
            continue

        if managed_path:
            remove_result = _remove_path(Path(managed_path).expanduser().resolve())
            result["removed_document_files"].append(remove_result)

        result["removed_document_ids"].append(doc_id)
        changed_docs = True

    if changed_docs:
        _write_json(DOCUMENTS_PATH, kept_docs)

    return result


def cleanup_managed_delete_residuals(
    *,
    representation_id: str,
    dataset_id: str | None = None,
    physical_volume_id: str | None = None,
    delete_orphan_managed_documents: bool = True,
) -> Dict[str, Any]:
    clean_rep = _clean(representation_id)
    clean_dataset = _clean(dataset_id)
    clean_physical = _extract_physical_volume_id(clean_rep, physical_volume_id)
    source_segy_file_id = _extract_source_segy_file_id(clean_rep, clean_dataset)

    attachments = cleanup_document_attachments_for_deleted_target(
        representation_id=clean_rep,
        dataset_id=clean_dataset,
        delete_orphan_managed_documents=delete_orphan_managed_documents,
    )
    volume_registry = cleanup_volume_registry_record(
        physical_volume_id=clean_physical,
        delete_artifact_paths=True,
    )

    return {
        "ok": True,
        "cleanup_scope": "managed_data_delete_residuals",
        "representation_id": clean_rep,
        "dataset_id": clean_dataset or None,
        "physical_volume_id": clean_physical or None,
        "source_segy_file_id": source_segy_file_id or None,
        "document_attachment_cleanup": attachments,
        "volume_registry_cleanup": volume_registry,
    }
