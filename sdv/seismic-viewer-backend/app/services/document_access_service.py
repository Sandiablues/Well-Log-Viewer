from __future__ import annotations

# DOCUMENT_ACCESS_UNIFICATION_FINAL_SERVICE

from pathlib import Path
from typing import Any, Iterable
import json
import mimetypes

from fastapi import HTTPException
from fastapi.responses import FileResponse

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = BACKEND_ROOT / "data"
MULTIVIEWER_ROOT = Path.home() / "Applications/MultiViewer"


def document_access_urls(document_id: str) -> dict[str, str]:
    clean = str(document_id or "").strip()
    if not clean:
        return {}
    return {
        "open_url": f"/api/documents/{clean}/open",
        "view_url": f"/api/documents/{clean}/view",
        "download_url": f"/api/documents/{clean}/download",
    }


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _document_store_paths() -> list[Path]:
    return [
        DATA_ROOT / "registry/documents.json",
        DATA_ROOT / "registry/document_assignments.json",
        DATA_ROOT / "source_intake_document_assignments.json",
        DATA_ROOT / "msi_document_attachments.json",
        DATA_ROOT / "registry/msi_document_attachments.json",
    ]


def _matching_records(document_id: str) -> list[dict[str, Any]]:
    clean = str(document_id or "").strip()
    if not clean:
        return []

    matches: list[dict[str, Any]] = []
    for path in _document_store_paths():
        if not path.exists():
            continue
        data = _load_json(path)
        if data is None:
            continue

        if isinstance(data, dict) and isinstance(data.get(clean), dict):
            row = dict(data[clean])
            row.setdefault("document_id", clean)
            row.setdefault("_registry_path", str(path))
            matches.append(row)

        for row in _walk_dicts(data):
            if str(row.get("document_id") or "").strip() == clean:
                copy = dict(row)
                copy.setdefault("_registry_path", str(path))
                matches.append(copy)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in matches:
        key = json.dumps(row, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    return deduped


def _candidate_path_values(row: dict[str, Any]) -> list[str]:
    keys = [
        "managed_path",
        "absolute_path",
        "file_path",
        "source_path",
        "storage_path",
        "local_path",
        "path",
        "relative_path",
        "stored_path",
        "upload_path",
        "original_path",
    ]
    values: list[str] = []
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values


def _base_dirs(row: dict[str, Any]) -> list[Path]:
    bases = [
        Path.cwd(),
        BACKEND_ROOT,
        DATA_ROOT,
        DATA_ROOT / "documents",
        DATA_ROOT / "documents/managed_uploads",
        DATA_ROOT / "uploads",
        DATA_ROOT / "source_intake_manual_uploads",
        DATA_ROOT / "managed_documents",
        DATA_ROOT / "md_documents",
        MULTIVIEWER_ROOT,
        MULTIVIEWER_ROOT / "End_Seismic_Data_Repository",
    ]
    for key in ("repository_root", "package_root", "root_path", "base_path", "folder_path"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            bases.append(Path(value).expanduser())

    result: list[Path] = []
    seen: set[str] = set()
    for base in bases:
        try:
            marker = str(base.expanduser())
        except Exception:
            marker = str(base)
        if marker not in seen:
            seen.add(marker)
            result.append(base.expanduser())
    return result


def _existing_file_from_value(value: str, row: dict[str, Any]) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    if raw.startswith("file://"):
        raw = raw[7:]
    if raw.startswith("endrepo://"):
        raw = raw.replace("endrepo://", "End_Seismic_Data_Repository/", 1)

    path = Path(raw).expanduser()
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        for base in _base_dirs(row):
            candidates.append(base / path)

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        except Exception:
            continue
    return None


def _find_by_filename(row: dict[str, Any]) -> Path | None:
    filename = row.get("filename") or row.get("name") or row.get("original_filename")
    if not isinstance(filename, str) or not filename.strip():
        return None
    target = filename.strip()
    roots = [
        DATA_ROOT / "documents/managed_uploads",
        DATA_ROOT / "documents",
        DATA_ROOT,
        MULTIVIEWER_ROOT / "End_Seismic_Data_Repository",
    ]
    for root in roots:
        if not root.exists():
            continue
        try:
            for candidate in root.rglob(target):
                if candidate.is_file():
                    return candidate.resolve()
        except Exception:
            continue
    return None


def resolve_registered_document_path(document_id: str) -> Path:
    clean = str(document_id or "").strip()
    if not clean:
        raise HTTPException(status_code=404, detail="Document id is required")

    records = _matching_records(clean)
    if not records:
        raise HTTPException(status_code=404, detail=f"Registered document not found: {clean}")

    for row in records:
        for value in _candidate_path_values(row):
            path = _existing_file_from_value(value, row)
            if path is not None:
                return path

    for row in records:
        path = _find_by_filename(row)
        if path is not None:
            return path

    raise HTTPException(status_code=404, detail=f"Registered document file is not available: {clean}")


def registered_document_file_response(document_id: str, *, disposition: str) -> FileResponse:
    if disposition not in {"inline", "attachment"}:
        disposition = "inline"
    path = resolve_registered_document_path(document_id)
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(
        str(path),
        media_type=media_type,
        filename=path.name,
        content_disposition_type=disposition,
    )
