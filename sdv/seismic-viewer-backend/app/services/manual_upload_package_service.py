
from __future__ import annotations

# MANUAL_UPLOAD_STAGING_1_SERVICE

import json
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import UploadFile

from app.services.document_registry_service import (
    DOCUMENT_EXTENSIONS,
    SEGY_EXTENSIONS,
    register_external_document,
)
from app.services.repository_registry_service import (
    REGISTRY_DIR,
    add_repository,
    get_repository,
    update_repository_scan_time,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MANUAL_UPLOAD_ROOT = BACKEND_ROOT / "data" / "source_intake_manual_uploads"
PACKAGES_PATH = REGISTRY_DIR / "packages.json"
SEGY_FILES_PATH = REGISTRY_DIR / "segy_files.json"
SCHEMA_VERSION = "source_intake.manual_upload_package.v1"


class ManualUploadPackageError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("[]\n", encoding="utf-8")
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return payload if isinstance(payload, list) else []


def _write_json_list(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _safe_filename(name: str | None) -> str:
    raw = Path(str(name or "uploaded_file")).name.strip()
    raw = raw.replace("/", "_").replace("\\", "_")
    raw = "".join(ch if ch.isalnum() or ch in {".", "_", "-", " ", "(", ")"} else "_" for ch in raw)
    raw = raw.strip(" .")
    return raw or "uploaded_file"


def _unique_path(folder: Path, filename: str) -> Path:
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for idx in range(2, 10000):
        next_candidate = folder / f"{stem}_{idx}{suffix}"
        if not next_candidate.exists():
            return next_candidate
    raise ManualUploadPackageError(f"Could not create unique upload filename for {filename!r}")


async def _save_upload_file(upload: UploadFile, target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with target.open("wb") as out:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)
    if size <= 0:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        raise ManualUploadPackageError(f"Uploaded file is empty: {upload.filename or target.name}")
    return size


def _relative_to(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def _mode_tokens(mode: str) -> tuple[str, str, str]:
    clean = str(mode or "").strip().lower()
    if clean == "2d":
        return "2d", "2d_line", "line_candidate"
    if clean == "3d":
        return "3d", "3d_volume", "volume_candidate"
    if clean == "auto":
        return "auto", "review_required", "review_required"
    raise ManualUploadPackageError("mode must be '2d', '3d', or 'auto'")


def _classify_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in SEGY_EXTENSIONS:
        return "segy"
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    return "unsupported"


def _upsert_package(package: Dict[str, Any]) -> None:
    packages = _read_json_list(PACKAGES_PATH)
    packages = [row for row in packages if row.get("package_id") != package.get("package_id")]
    packages.append(package)
    _write_json_list(PACKAGES_PATH, packages)


def _append_segy_rows(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    existing = _read_json_list(SEGY_FILES_PATH)
    remove_ids = {row.get("segy_file_id") for row in rows}
    existing = [row for row in existing if row.get("segy_file_id") not in remove_ids]
    existing.extend(rows)
    _write_json_list(SEGY_FILES_PATH, existing)


def _repository_notes(mode: str, intended_use: str) -> str:
    return json.dumps(
        {
            "source_structure_type": "manual_upload_package",
            "intended_use": intended_use or f"{mode}_segy_intake",
            "workflow_mode": mode,
            "created_by": "manual_upload_staging_1",
        },
        sort_keys=True,
    )


class ManualUploadPackageService:
    # Backend-owned manual upload package staging.
    # Stores uploaded files as Source Intake records; no conversion is started.

    async def create_package(
        self,
        *,
        files: List[UploadFile],
        mode: str = "3d",
        repository_id: Optional[str] = None,
        package_name: Optional[str] = None,
        intended_use: str = "source_intake",
    ) -> Dict[str, Any]:
        if not files:
            raise ManualUploadPackageError("At least one file is required.")

        resolved_mode, candidate_kind, candidate_role = _mode_tokens(mode)
        now = _utc_now()
        package_id = f"pkg_manual_{uuid.uuid4().hex[:12]}"
        package_label = (package_name or f"Manual Upload {now[:19]}").strip()

        repo = get_repository(repository_id) if repository_id else None
        if repo:
            repo_root = Path(str(repo.get("root_path") or "")).expanduser().resolve()
            if not repo_root.exists():
                raise ManualUploadPackageError(f"Repository root does not exist: {repo_root}")
            package_rel = f"_manual_uploads/{package_id}"
            package_root = repo_root / package_rel
        else:
            package_root = (MANUAL_UPLOAD_ROOT / package_id).resolve()
            package_rel = "."
            package_root.mkdir(parents=True, exist_ok=True)
            repo = add_repository(
                name=f"Manual Upload — {package_label}",
                root_path=str(package_root),
                repository_type="manual_upload_package",
                read_only=True,
                notes=_repository_notes(resolved_mode, intended_use),
            )
            repository_id = str(repo.get("repository_id") or "")
            if not repository_id:
                raise ManualUploadPackageError("Manual upload repository creation did not return repository_id.")
            repo_root = package_root

        repository_id = str(repo.get("repository_id") or repository_id or "")
        if not repository_id:
            raise ManualUploadPackageError("repository_id could not be resolved.")

        segy_dir = package_root / "segy"
        doc_dir = package_root / "documents"
        unsupported_dir = package_root / "unsupported"
        for folder in (segy_dir, doc_dir, unsupported_dir):
            folder.mkdir(parents=True, exist_ok=True)

        uploaded_files: List[Dict[str, Any]] = []
        segy_rows: List[Dict[str, Any]] = []
        documents: List[Dict[str, Any]] = []
        unsupported: List[Dict[str, Any]] = []
        warnings: List[str] = []

        for upload in files:
            original_name = _safe_filename(upload.filename)
            classification = _classify_extension(original_name)
            target_dir = segy_dir if classification == "segy" else doc_dir if classification == "document" else unsupported_dir
            target = _unique_path(target_dir, original_name)
            size = await _save_upload_file(upload, target)
            rel = _relative_to(target, repo_root)
            mime_type = upload.content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
            file_row = {
                "filename": target.name,
                "original_filename": original_name,
                "file_role": classification,
                "relative_path": rel,
                "absolute_path": str(target),
                "size_bytes": size,
                "mime_type": mime_type,
            }
            uploaded_files.append(file_row)

            if classification == "segy":
                segy_file_id = f"segy_{uuid.uuid4().hex[:16]}"
                segy_row = {
                    "segy_file_id": segy_file_id,
                    "candidate_id": segy_file_id,
                    "source_segy_file_id": segy_file_id,
                    "repository_id": repository_id,
                    "package_id": package_id,
                    "line_id": None,
                    "filename": target.name,
                    "display_name": target.name,
                    "relative_path": rel,
                    "source_path": str(target),
                    "absolute_path": str(target),
                    "path": str(target),
                    "extension": target.suffix.lower(),
                    "size_bytes": size,
                    "modified_epoch": target.stat().st_mtime,
                    "candidate_kind": candidate_kind,
                    "candidate_role": candidate_role,
                    "classification_source": "manual_upload_package",
                    "classification_confidence": "high" if resolved_mode in {"2d", "3d"} else "review_required",
                    "classification_reasons": [
                        f"Uploaded through manual upload package endpoint as mode={resolved_mode}.",
                        "SEG-Y extension recognized; no conversion was started during upload.",
                    ],
                    "source_path_exists": True,
                    "conversion_status": "not_converted",
                    "conversion_state_reason": "manual_upload_staged_no_conversion_started",
                    "conversion_state_authoritative": True,
                    "created_at": now,
                    "updated_at": now,
                }
                segy_rows.append(segy_row)
                continue

            if classification == "document":
                try:
                    doc = register_external_document(
                        repository_id=repository_id,
                        relative_path=rel,
                        linked_scope="package",
                        package_id=package_id,
                    )
                    documents.append(doc)
                except Exception as exc:
                    warnings.append(f"Document was uploaded but could not be registered: {target.name}: {exc}")
                continue

            unsupported.append(file_row)

        package = {
            "package_id": package_id,
            "repository_id": repository_id,
            "display_name": package_label,
            "relative_path": package_rel,
            "package_key": package_id,
            "package_type": "manual_upload_package",
            "source_structure_type": "manual_upload_package",
            "intended_use": intended_use or f"{resolved_mode}_segy_intake",
            "workflow_mode": resolved_mode,
            "status": "staged",
            "segy_count": len(segy_rows),
            "document_count": len(documents),
            "unsupported_count": len(unsupported),
            "created_at": now,
            "updated_at": now,
            "source": "manual_upload_staging_1",
        }
        _upsert_package(package)
        _append_segy_rows(segy_rows)

        try:
            update_repository_scan_time(repository_id)
        except Exception:
            pass

        return {
            "schema_version": SCHEMA_VERSION,
            "package_id": package_id,
            "repository_id": repository_id,
            "mode": resolved_mode,
            "package_name": package_label,
            "staged_for_conversion": bool(segy_rows),
            "uploaded_files": uploaded_files,
            "segy_candidates": segy_rows,
            "supporting_documents": documents,
            "unsupported_files": unsupported,
            "classification_summary": {
                "segy_count": len(segy_rows),
                "document_count": len(documents),
                "unsupported_count": len(unsupported),
            },
            "next_actions": ["review", "create_index", "convert_to_zarr"] if segy_rows else ["review"],
            "conversion_started": False,
            "index_started": False,
            "msi_registration_started": False,
            "warnings": warnings,
            "storage": {
                "repository_root": str(repo_root),
                "package_root": str(package_root),
            },
        }
