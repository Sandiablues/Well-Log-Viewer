
from __future__ import annotations

from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
import mimetypes
import os
import json
import subprocess
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.local_folder_browser_service import list_local_folders
from app.services.job_service import JobService
from app.services.conversion_job_service import ConversionJobService
from app.services.conversion_state_service import resolve_source_segy_conversion_state
from app.services.source_intake_geometry_qaqc_service import get_geometry_qaqc, run_geometry_qaqc

from app.services.repository_registry_service import (
    add_repository,
    delete_repository_cascade,
    get_repository,
    list_repositories,
    resolve_repository_path,
)
from app.services.source_repository_mode_service import (
    apply_mode_defaults_to_payload,
    encode_repository_notes,
    filter_repositories_by_mode,
)
from app.services.document_registry_service import (
    get_document,
    list_documents,
    resolve_document_path,
    scan_repository_for_documents,
)
from app.services.msi_document_attachment_service import (
    attach_document_to_managed_data,
    list_managed_document_attachments,
)
from app.services.repository_package_scanner_service import scan_repository_packages
from app.services.package_registry_service import (
    get_segy_file,
    list_lines,
    list_packages,
    list_segy_files,
    persist_repository_scan,
    update_segy_file_conversion,
)

from app.services.repository_load_sheet_service import build_repository_load_sheet
from app.msi.registration_service import register_converted_segy_file
from app.storage.service import is_endrepo_zarr_url, resolve_endrepo_zarr_url_path, storage_service

router = APIRouter(prefix="/api", tags=["data-repositories-documents"])

UPLOAD_DIR = os.environ.get("UPLOADS_DIR", "./data/uploads")
ZARR_DIR = os.environ.get("ZARR_DIR", "./data/zarr")
VOLUMES_JSON = os.environ.get("VOLUMES_JSON", "./data/volumes.json")
JOBS_DIR = os.environ.get("JOBS_DIR", "./data/jobs")
ZARR_TMP_DIR = os.environ.get("ZARR_TMP_DIR", "./data/zarr_tmp")

registry_job_service = JobService(JOBS_DIR)
registry_conversion_job_service = ConversionJobService(
    job_service=registry_job_service,
    volumes_json=VOLUMES_JSON,
)
registry_conversion_executor = ThreadPoolExecutor(max_workers=1)





def _load_registry_volumes() -> dict:
    if os.path.exists(VOLUMES_JSON):
        try:
            with open(VOLUMES_JSON, "r", encoding="utf-8") as f:
                value = json.load(f)
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}
    return {}


def _save_registry_volumes(volumes: dict) -> None:
    os.makedirs(os.path.dirname(VOLUMES_JSON), exist_ok=True)
    with open(VOLUMES_JSON, "w", encoding="utf-8") as f:
        json.dump(volumes, f, indent=2, ensure_ascii=False)




def _register_converted_segy_with_msi(segy_file: dict) -> dict:
    """
    Best-effort MSI registration for converted source-registry SEG-Y files.

    Registration failure must not make the conversion itself fail.
    """
    try:
        return register_converted_segy_file(segy_file, backend_root=Path("."))
    except Exception as exc:
        return {
            "registered": False,
            "reason": "registration_exception",
            "error": str(exc),
            "segy_file_id": segy_file.get("segy_file_id") if isinstance(segy_file, dict) else None,
        }


def _registry_lookup_by_id(items: list[dict], id_field: str, value: str | None) -> dict | None:
    if not value:
        return None
    for item in items:
        if item.get(id_field) == value:
            return item
    return None


def _attach_registry_source_to_volume(segy_file: dict) -> dict | None:
    """
    Ensure the converted registry SEG-Y is represented in volumes.json
    as a normal Data Manager volume with external-source provenance.
    """
    volume_id = segy_file.get("volume_id")
    if not volume_id:
        return None

    volumes = _load_registry_volumes()
    volume = volumes.get(volume_id)

    if not volume:
        return None

    packages = list_packages(repository_id=segy_file.get("repository_id"))
    lines = list_lines(repository_id=segy_file.get("repository_id"))

    package = _registry_lookup_by_id(packages, "package_id", segy_file.get("package_id"))
    line = _registry_lookup_by_id(lines, "line_id", segy_file.get("line_id"))

    line_display = line.get("display_name") if line else None
    package_display = package.get("display_name") if package else None

    display_name = line_display or segy_file.get("filename") or volume.get("filename") or volume_id

    volume["id"] = volume.get("id") or volume_id
    volume["filename"] = volume.get("filename") or segy_file.get("filename")
    volume["display_name"] = volume.get("display_name") or display_name
    volume["dataset_type"] = volume.get("dataset_type") or "2d_line"
    volume["zarr_url"] = volume.get("zarr_url") or segy_file.get("zarr_url")

    volume["source"] = {
        "source_type": "external_repository",
        "repository_id": segy_file.get("repository_id"),
        "package_id": segy_file.get("package_id"),
        "line_id": segy_file.get("line_id"),
        "segy_file_id": segy_file.get("segy_file_id"),
        "package_display_name": package_display,
        "line_display_name": line_display,
        "original_filename": segy_file.get("filename"),
        "original_relative_path": segy_file.get("relative_path"),
        "conversion_status": segy_file.get("conversion_status"),
        "job_id": segy_file.get("job_id"),
    }

    metadata = volume.get("metadata") or {}
    metadata["source_type"] = "external_repository"
    metadata["repository_id"] = segy_file.get("repository_id")
    metadata["package_id"] = segy_file.get("package_id")
    metadata["line_id"] = segy_file.get("line_id")
    metadata["segy_file_id"] = segy_file.get("segy_file_id")
    metadata["package_display_name"] = package_display
    metadata["line_display_name"] = line_display
    metadata["original_filename"] = segy_file.get("filename")
    metadata["original_relative_path"] = segy_file.get("relative_path")
    volume["metadata"] = metadata

    volumes[volume_id] = volume
    _save_registry_volumes(volumes)

    return volume


class RepositoryCreateRequest(BaseModel):
    name: str
    root_path: str
    repository_type: str = "local_folder"
    read_only: bool = True
    include_subfolders: bool = False
    notes: Optional[str] = None
    source_structure_type: Optional[str] = None
    intended_use: Optional[str] = None
    workflow_mode: Optional[str] = None


@router.get("/repositories")
def api_list_repositories(mode: Optional[str] = Query(None)):
    return {
        "mode": mode,
        "repositories": filter_repositories_by_mode(list_repositories(), mode),
    }


@router.post("/repositories")
def api_add_repository(
    payload: RepositoryCreateRequest,
    mode: Optional[str] = Query(None),
):
    try:
        raw_payload = payload.model_dump()
        mode_payload = apply_mode_defaults_to_payload(raw_payload, mode or payload.workflow_mode)
        notes = encode_repository_notes(
            mode_payload.get("notes"),
            mode_payload.get("source_structure_type"),
            mode_payload.get("intended_use"),
        )
        repo = add_repository(
            name=mode_payload.get("name") or payload.name,
            root_path=mode_payload.get("root_path") or payload.root_path,
            repository_type=mode_payload.get("repository_type") or payload.repository_type,
            read_only=bool(mode_payload.get("read_only", payload.read_only)),
            notes=notes,
            include_subfolders=bool(mode_payload.get("include_subfolders", payload.include_subfolders)),
        )
        repo = dict(repo)
        if mode_payload.get("source_structure_type"):
            repo.setdefault("source_structure_type", mode_payload.get("source_structure_type"))
        if mode_payload.get("intended_use"):
            repo.setdefault("intended_use", mode_payload.get("intended_use"))
        if mode_payload.get("workflow_mode"):
            repo.setdefault("workflow_mode", mode_payload.get("workflow_mode"))
        return {
            "repository": repo
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/repositories/{repository_id}")
def api_get_repository(repository_id: str):
    repo = get_repository(repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return {
        "repository": repo
    }


@router.delete("/repositories/{repository_id}")
def api_delete_repository(repository_id: str):
    result = delete_repository_cascade(repository_id)
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="Repository not found")
    return result


@router.post("/repositories/{repository_id}/scan-documents")
def api_scan_repository_documents(
    repository_id: str,
    max_files: int = Query(50000, ge=1, le=500000),
):
    try:
        return scan_repository_for_documents(repository_id, max_files=max_files)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/documents")
def api_list_documents(
    repository_id: Optional[str] = None,
    linked_scope: Optional[str] = None,
):
    return {
        "documents": list_documents(
            repository_id=repository_id,
            linked_scope=linked_scope,
        )
    }




class MsiDocumentAttachmentRequest(BaseModel):
    source_path: str
    target_ids: list[str]
    scope_kind: str = "selected_data"
    survey_name: Optional[str] = None
    document_type: Optional[str] = None
    document_role: Optional[str] = "supporting_document"
    notes: Optional[str] = None


@router.get("/msi/document-attachments")
def api_list_msi_document_attachments(
    dataset_id: Optional[str] = None,
    representation_id: Optional[str] = None,
    survey_name: Optional[str] = None,
):
    try:
        return list_managed_document_attachments(
            dataset_id=dataset_id,
            representation_id=representation_id,
            survey_name=survey_name,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/msi/document-attachments")
def api_attach_msi_document(payload: MsiDocumentAttachmentRequest):
    try:
        return attach_document_to_managed_data(
            source_path=payload.source_path,
            target_ids=payload.target_ids,
            scope_kind=payload.scope_kind,
            survey_name=payload.survey_name,
            document_type=payload.document_type,
            document_role=payload.document_role,
            notes=payload.notes,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/documents/{document_id}")
def api_get_document(document_id: str):
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "document": doc
    }


@router.get("/documents/{document_id}/view")
def api_view_document(document_id: str):
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        path = resolve_document_path(document_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Document source file missing")

    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{path.name}"'
        },
    )


@router.get("/documents/{document_id}/download")
def api_download_document(document_id: str):
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        path = resolve_document_path(document_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Document source file missing")

    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{path.name}"'
        },
    )


@router.post("/documents/{document_id}/reveal")
def api_reveal_document(document_id: str):
    doc = get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        path = resolve_document_path(document_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if not path.exists():
        raise HTTPException(status_code=404, detail="Document source file missing")

    try:
        subprocess.run(["open", "-R", str(path)], check=False)
        return {
            "ok": True,
            "document_id": document_id,
            "revealed_path": str(path),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/repositories/{repository_id}/scan-packages")
def api_scan_repository_packages(
    repository_id: str,
    max_files: int = Query(100000, ge=1, le=500000),
    include_subfolders: bool | None = Query(None),
):
    try:
        return scan_repository_packages(
            repository_id,
            max_files=max_files,
            include_subfolders=include_subfolders,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/repositories/{repository_id}/persist-scan")
def api_persist_repository_scan(
    repository_id: str,
    max_files: int = Query(100000, ge=1, le=500000),
    include_subfolders: bool | None = Query(None),
):
    try:
        return persist_repository_scan(
            repository_id,
            max_files=max_files,
            include_subfolders=include_subfolders,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))



@router.get("/repositories/{repository_id}/load-sheet")
def api_get_repository_load_sheet(repository_id: str):
    """
    Read-only Source Intake / QAQC load sheet.

    Summarizes existing repository scan/package records and deterministic
    knowledge classifications. This does not register, index, convert, load,
    unload, or delete any dataset.
    """
    return build_repository_load_sheet(repository_id)


@router.get("/packages")
def api_list_packages(repository_id: Optional[str] = None):
    return {
        "packages": list_packages(repository_id=repository_id)
    }


@router.get("/lines")
def api_list_lines(
    package_id: Optional[str] = None,
    repository_id: Optional[str] = None,
):
    return {
        "lines": list_lines(package_id=package_id, repository_id=repository_id)
    }


@router.get("/segy-files")
def api_list_segy_files(
    package_id: Optional[str] = None,
    line_id: Optional[str] = None,
    repository_id: Optional[str] = None,
):
    return {
        "segy_files": list_segy_files(
            package_id=package_id,
            line_id=line_id,
            repository_id=repository_id,
        )
    }


ACTIVE_JOB_STATUSES = {
    "queued",
    "saving_upload",
    "reading_metadata",
    "validating_geometry",
    "converting",
    "writing_zarr",
    "validating_zarr",
    "promoting_output",
    "registering_volume",
    "registering_dataset",
}

FAILED_JOB_STATUSES = {"failed", "error", "cancelled", "canceled"}
COMPLETE_JOB_STATUSES = {"complete", "completed", "ready"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _registry_segy_json_path() -> Path:
    return Path("data/registry/segy_files.json")


def _direct_update_registry_segy(segy_file_id: str, **updates) -> dict:
    path = _registry_segy_json_path()
    items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    updated = None
    for item in items:
        if str(item.get("segy_file_id")) == str(segy_file_id):
            item.update({k: v for k, v in updates.items() if v is not None})
            item["updated_at"] = _utc_now_iso()
            updated = item
            break

    if updated is None:
        raise HTTPException(status_code=404, detail="SEG-Y source file not found")

    path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    return updated


def _safe_update_registry_segy(segy_file_id: str, **updates) -> dict:
    status = updates.pop("conversion_status", None) or updates.pop("status", None)
    if not status:
        current = get_segy_file(segy_file_id) or {}
        status = current.get("conversion_status") or "not_converted"

    # Explicit None means clear stale conversion_error.
    clear_error = "conversion_error" in updates and updates.get("conversion_error") is None
    error = updates.pop("conversion_error", None)

    return update_segy_file_conversion(
        segy_file_id=segy_file_id,
        conversion_status=status,
        error=error,
        clear_error=clear_error,
        **updates,
    )


def _resolve_registry_segy_source_path(segy_file: dict) -> Path:
    repository_id = segy_file.get("repository_id")
    relative_path = segy_file.get("relative_path")

    if not repository_id or not relative_path:
        raise HTTPException(status_code=400, detail="SEG-Y source record is missing repository_id or relative_path")

    # repository_registry_service.resolve_repository_path expects both the repository
    # id and the relative path. It returns the resolved source path under the
    # registered repository root.
    source_path = Path(resolve_repository_path(repository_id, relative_path))

    if not source_path.exists() or not source_path.is_file():
        raise HTTPException(status_code=404, detail=f"SEG-Y source file missing: {source_path}")

    return source_path


def _iter_registry_jobs() -> list[dict]:
    jobs = []
    for path in Path(JOBS_DIR).glob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                jobs.append(value)
        except Exception:
            continue

    jobs.sort(key=lambda job: str(job.get("updated_at") or job.get("created_at") or ""), reverse=True)
    return jobs




def _volume_record_exists(volume_id: str | None) -> bool:
    if not volume_id:
        return False

    volumes_path = Path(VOLUMES_JSON)
    if not volumes_path.exists():
        return False

    try:
        volumes = json.loads(volumes_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    return isinstance(volumes, dict) and str(volume_id) in volumes


def _zarr_path_exists(zarr_url: str | None, job: dict | None = None) -> bool:
    candidates = []

    if zarr_url:
        if zarr_url.startswith("/data/zarr/"):
            candidates.append(Path("." + zarr_url))
        elif is_endrepo_zarr_url(zarr_url):
            try:
                candidates.append(resolve_endrepo_zarr_url_path(zarr_url))
            except Exception:
                pass
        else:
            candidates.append(Path(zarr_url))

    if job and job.get("output_path"):
        candidates.append(Path(str(job.get("output_path"))))

    return any(path.exists() for path in candidates)


def _converted_artifact_is_valid(job: dict | None, segy_file: dict | None = None) -> tuple[bool, str | None]:
    file_id = None
    zarr_url = None

    if job:
        file_id = job.get("file_id")
        volume = job.get("volume") or {}
        zarr_url = volume.get("zarr_url") or job.get("zarr_url")

    if segy_file:
        file_id = file_id or segy_file.get("volume_id")
        zarr_url = zarr_url or segy_file.get("zarr_url")

    if not file_id:
        return False, "Converted status is invalid: no managed dataset id is recorded."

    if not _volume_record_exists(str(file_id)):
        return False, "Converted status is invalid: managed dataset record is missing."

    if not _zarr_path_exists(zarr_url, job):
        return False, "Converted status is invalid: converted Zarr artifact is missing."

    return True, None

def _find_latest_job_for_registry_segy(segy_file: dict) -> dict | None:
    # Job lookup must be explicit. Do not infer conversion state from old jobs
    # by filename or path; that causes newly re-submitted source files to inherit
    # stale converted/converting status from previous runs.
    job_id = segy_file.get("job_id") or segy_file.get("conversion_job_id")
    if not job_id:
        return None

    return registry_job_service.get_job(job_id)


def _job_to_registry_status(job: dict | None, current_status: str | None = None) -> tuple[str, dict]:
    if not job:
        if current_status in {"queued", "converting", "converted", "ready"}:
            return "error", {
                "job_id": None,
                "volume_id": None,
                "zarr_url": None,
                "conversion_error": "Conversion status is stale: no authoritative job is linked to this source SEG-Y record.",
            }
        return current_status or "not_converted", {}

    status = str(job.get("status") or "").lower()

    if status in COMPLETE_JOB_STATUSES:
        volume = job.get("volume") or {}
        file_id = job.get("file_id")
        zarr_url = volume.get("zarr_url") or job.get("zarr_url") or (f"/data/zarr/{file_id}.zarr" if file_id else None)
        storage_uri = volume.get("storage_uri") or job.get("storage_uri")

        valid, reason = _converted_artifact_is_valid(job)

        if not valid:
            return "error", {
                "job_id": job.get("job_id"),
                "volume_id": file_id,
                "zarr_url": zarr_url,
                "storage_uri": storage_uri,
                "conversion_error": reason or "Converted artifact is not registered or is missing.",
            }

        return "converted", {
            "job_id": job.get("job_id"),
            "volume_id": volume.get("id") or file_id,
            "zarr_url": zarr_url,
            "storage_uri": storage_uri,
            "conversion_error": None,
        }

    if status in FAILED_JOB_STATUSES:
        return "error", {
            "job_id": job.get("job_id"),
            "conversion_error": job.get("error") or job.get("message") or "SEG-Y conversion failed.",
        }

    if status in ACTIVE_JOB_STATUSES:
        mapped = "queued" if status == "queued" else "converting"
        return mapped, {
            "job_id": job.get("job_id"),
            "conversion_error": None,
        }

    return current_status or "not_converted", {
        "job_id": job.get("job_id"),
    }


def _reconcile_registry_segy_conversion_status(segy_file: dict) -> dict:
    job = _find_latest_job_for_registry_segy(segy_file)
    status, updates = _job_to_registry_status(job, segy_file.get("conversion_status"))

    updated = _safe_update_registry_segy(
        segy_file.get("segy_file_id"),
        conversion_status=status,
        **updates,
    )

    if status == "converted":
        try:
            _attach_registry_source_to_volume(updated)
        except Exception:
            pass

        updated["msi_registration"] = _register_converted_segy_with_msi(updated)

    return updated


def _resolve_geometry_qaqc_for_3d_conversion(segy_file_id: str) -> dict:
    """
    Backend gate for 3D Source Intake conversion.

    Build 3D Volume must use the same Geometry QAQC authority as Build Index.
    If no report exists, run QAQC first. If the result is not passed/high
    confidence, block conversion rather than creating a bad Zarr cube.
    """
    public = get_geometry_qaqc(segy_file_id)
    if public.get("status") == "not_run" or not public.get("selected_geometry"):
        run_geometry_qaqc(segy_file_id, include_segysak=True)
        public = get_geometry_qaqc(segy_file_id)

    selected = public.get("selected_geometry") if isinstance(public.get("selected_geometry"), dict) else None
    if not selected:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "3D Geometry QAQC did not produce selected geometry for conversion.",
                "geometry_qaqc": public,
            },
        )

    if public.get("requires_review") or public.get("status") != "passed" or public.get("confidence") != "high":
        raise HTTPException(
            status_code=400,
            detail={
                "message": "3D Geometry QAQC must pass before full Zarr conversion.",
                "geometry_qaqc": public,
            },
        )

    if selected.get("inline_byte") is None or selected.get("crossline_byte") is None:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "3D Geometry QAQC selected geometry is missing inline/crossline byte locations.",
                "geometry_qaqc": public,
            },
        )

    blocking_warnings = {
        "candidate_implies_absurd_sparse_grid",
        "candidate_headers_look_coordinate_like",
        "grid_occupancy_is_implausible",
    }
    selected_warnings = set(str(x) for x in (selected.get("warnings") or []))
    if selected_warnings.intersection(blocking_warnings):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "3D Geometry QAQC selected geometry has blocking warnings.",
                "geometry_qaqc": public,
            },
        )

    return public


def _planned_managed_zarr_dimension(segy_file: dict) -> str | None:
    """
    Best-effort planning hint for queued conversion records only.
    ConversionJobService recalculates the authoritative dimension after reading
    SEG-Y metadata and owns the final EndRepo target.
    """
    candidate = str(
        segy_file.get("dataset_type")
        or segy_file.get("candidate_kind")
        or segy_file.get("candidate_role")
        or ""
    ).strip().lower()

    if candidate in {"3d", "3d_volume", "volume", "volume_candidate"}:
        return "3d"

    if candidate in {"2d", "2d_line", "line", "line_candidate"}:
        return "2d"

    return None


@router.post("/segy-files/{segy_file_id}/convert")
def api_convert_registry_segy_file(
    segy_file_id: str,
    expected_dataset_type: str | None = None,
):
    segy_file = get_segy_file(segy_file_id)
    if not segy_file:
        raise HTTPException(status_code=404, detail="SEG-Y source file not found")

    # Reconcile stale queued/converting records before deciding whether to block retry.
    if segy_file.get("conversion_status") in {"queued", "converting"}:
        segy_file = _reconcile_registry_segy_conversion_status(segy_file)

    if segy_file.get("conversion_status") in {"converted", "ready"}:
        msi_registration = _register_converted_segy_with_msi(segy_file)
        return {
            "status": "converted",
            "segy_file": segy_file,
            "job_id": segy_file.get("job_id"),
            "volume_id": segy_file.get("volume_id"),
            "zarr_url": segy_file.get("zarr_url"),
            "msi_registration": msi_registration,
            "message": "SEG-Y file is already converted.",
        }

    if segy_file.get("conversion_status") in {"queued", "converting"}:
        return {
            "status": segy_file.get("conversion_status"),
            "segy_file": segy_file,
            "message": "Conversion is already active for this SEG-Y file.",
        }

    source_path = _resolve_registry_segy_source_path(segy_file)

    file_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    filename = segy_file.get("filename") or source_path.name
    clean_expected_dataset_type = (expected_dataset_type or "").strip().lower() or None
    if clean_expected_dataset_type not in {None, "2d_line", "3d_volume"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported expected_dataset_type: {expected_dataset_type!r}",
        )

    geometry_qaqc_contract = (
        _resolve_geometry_qaqc_for_3d_conversion(segy_file_id)
        if clean_expected_dataset_type == "3d_volume"
        else None
    )

    planned_dimension = (
        "2d" if clean_expected_dataset_type == "2d_line"
        else "3d" if clean_expected_dataset_type == "3d_volume"
        else _planned_managed_zarr_dimension(segy_file)
    )
    planned_target = (
        storage_service().managed_zarr_target(file_id, planned_dimension)
        if planned_dimension in {"2d", "3d"}
        else None
    )
    output_path = (
        str(planned_target["local_path"])
        if planned_target
        else str(Path(ZARR_DIR) / f"{file_id}.zarr")
    )
    planned_zarr_url = (
        str(planned_target["zarr_url"])
        if planned_target
        else None
    )
    planned_storage_uri = (
        str(planned_target["storage_uri"])
        if planned_target
        else None
    )
    temp_output_path = str(Path(ZARR_TMP_DIR) / f"{file_id}.zarr.tmp")

    job = registry_job_service.create_job(
        job_id=job_id,
        file_id=file_id,
        filename=filename,
        input_path=str(source_path),
        output_path=output_path,
        temp_output_path=temp_output_path,
        expected_dataset_type=clean_expected_dataset_type,
    )

    if geometry_qaqc_contract:
        selected_geometry = geometry_qaqc_contract.get("selected_geometry") or {}
        job = registry_job_service.update_job(
            job_id,
            geometry_qaqc=geometry_qaqc_contract,
            geometry_override=selected_geometry,
            message=(
                "SEG-Y conversion queued with Geometry QAQC-approved 3D geometry: "
                f"inline byte {selected_geometry.get('inline_byte')}, "
                f"crossline byte {selected_geometry.get('crossline_byte')}."
            ),
        ) or job

    queued_record = _safe_update_registry_segy(
        segy_file_id,
        conversion_status="queued",
        job_id=job_id,
        volume_id=file_id,
        zarr_url=planned_zarr_url,
        storage_uri=planned_storage_uri,
        conversion_error=None,
        conversion_state_reason="conversion_queued",
        conversion_state_authoritative=True,
        conversion_queued_at=_utc_now_iso(),
    )

    registry_conversion_executor.submit(registry_conversion_job_service.run, job_id)

    return {
        "status": "queued",
        "job_id": job_id,
        "volume_id": file_id,
        "zarr_url": planned_zarr_url,
        "storage_uri": planned_storage_uri,
        "job": job,
        "segy_file": queued_record,
    }


@router.post("/segy-files/{segy_file_id}/refresh-status")
def api_refresh_registry_segy_file_status(segy_file_id: str):
    segy_file = get_segy_file(segy_file_id)
    if not segy_file:
        raise HTTPException(status_code=404, detail="SEG-Y source file not found")

    state = resolve_source_segy_conversion_state(
        segy_file,
        jobs_dir=JOBS_DIR,
        volumes_json=VOLUMES_JSON,
        backend_root=".",
    )

    updated = _safe_update_registry_segy(
        segy_file_id,
        **state.as_updates(),
    )

    msi_registration = None
    if updated.get("conversion_status") in {"converted", "ready"}:
        try:
            _attach_registry_source_to_volume(updated)
        except Exception:
            pass
        msi_registration = _register_converted_segy_with_msi(updated)

    return {
        "status": updated.get("conversion_status"),
        "job_id": updated.get("job_id"),
        "volume_id": updated.get("volume_id"),
        "zarr_url": updated.get("zarr_url"),
        "conversion_error": updated.get("conversion_error"),
        "reason": state.reason,
        "is_authoritative": state.is_authoritative,
        "msi_registration": msi_registration,
        "segy_file": updated,
    }





def _volume_doc_source(volume: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize source linkage fields for a managed volume or indexed pseudo-volume.

    Returns repository/package/line/path hints used by /api/volumes/{id}/documents.
    Missing fields are allowed; the route can then return an empty document list
    instead of throwing an internal server error.
    """
    if not isinstance(volume, dict):
        return {}

    metadata = volume.get("metadata") if isinstance(volume.get("metadata"), dict) else {}
    source = volume.get("source") if isinstance(volume.get("source"), dict) else {}

    def first(*values):
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    return {
        "repository_id": first(
            source.get("repository_id"),
            metadata.get("repository_id"),
            volume.get("repository_id"),
        ),
        "package_id": first(
            source.get("package_id"),
            metadata.get("package_id"),
            volume.get("package_id"),
        ),
        "line_id": first(
            source.get("line_id"),
            metadata.get("line_id"),
            volume.get("line_id"),
        ),
        "source_relative_path": first(
            source.get("source_relative_path"),
            source.get("original_relative_path"),
            metadata.get("source_relative_path"),
            metadata.get("original_relative_path"),
            volume.get("source_relative_path"),
            volume.get("relative_path"),
            volume.get("filename"),
        ),
        "filename": first(
            source.get("filename"),
            metadata.get("source_file_name"),
            volume.get("filename"),
            volume.get("display_name"),
        ),
    }


def _volume_doc_get_volume(volume_id: str) -> Dict[str, Any]:
    """
    Resolve a managed volume row for document-link lookup.

    This helper keeps /api/volumes/{volume_id}/documents from depending on
    frontend assumptions. It supports the current volumes.json registry shape:
    either a dict keyed by volume id or a list of volume records.
    """
    from pathlib import Path
    import json

    clean_id = str(volume_id or "").strip()
    if not clean_id:
        raise HTTPException(status_code=400, detail="volume_id is required")

    volumes_path = Path(__file__).resolve().parents[2] / "data" / "volumes.json"
    if not volumes_path.exists():
        raise HTTPException(status_code=404, detail="Volume registry not found")

    try:
        registry = json.loads(volumes_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read volume registry: {exc}")

    volume = None

    if isinstance(registry, dict):
        direct = registry.get(clean_id)
        if isinstance(direct, dict):
            volume = direct
        else:
            for candidate in registry.values():
                if isinstance(candidate, dict) and str(candidate.get("id") or "") == clean_id:
                    volume = candidate
                    break
    elif isinstance(registry, list):
        for candidate in registry:
            if isinstance(candidate, dict) and str(candidate.get("id") or "") == clean_id:
                volume = candidate
                break

    if not isinstance(volume, dict):
        raise HTTPException(status_code=404, detail=f"Volume not found: {clean_id}")

    if not volume.get("id"):
        volume = {**volume, "id": clean_id}

    return volume


def build_volume_documents_payload(volume_id: str):
    volume = _volume_doc_get_volume(volume_id)
    source = _volume_doc_source(volume)

    repository_id = source.get("repository_id")
    if not repository_id:
        return {
            "volume_id": volume_id,
            "source": source,
            "documents": [],
            "warning": "Selected volume has no repository source metadata.",
        }

    docs = list_documents(repository_id=repository_id)

    scoped_docs = [
        doc for doc in docs
        if _volume_doc_matches(doc, source)
    ]

    return {
        "volume_id": volume_id,
        "source": source,
        "documents": scoped_docs,
        "document_count": len(scoped_docs),
    }


@router.get("/volumes/{volume_id}/documents")
def api_list_volume_documents(volume_id: str):
    return build_volume_documents_payload(volume_id)

@router.get("/local-folders")
def api_list_local_folders(path: str | None = None):
    """
    Browse local folders for Source Intake root selection.

    This is intentionally read-only. It does not scan, register, index,
    convert, load, unload, or delete data.
    """
    try:
        return list_local_folders(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Folder browse failed: {exc}")


