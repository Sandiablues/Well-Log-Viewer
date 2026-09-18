from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, Set

from app.msi.routes import lifecycle_service, viewer_resolver
from app.services.managed_document_context_service import augment_managed_rows_with_documents
from app.services.source_intake_reset_service import reset_source_intake_candidate_derived_state
from app.services.artifact_lifecycle_service import artifact_lifecycle_service
from app.services.managed_delete_cascade_cleanup_service import cleanup_managed_delete_residuals
from app.services.managed_data_delete_service import managed_data_delete_service
from app.services.segy_index_service import SegyIndexService
from app.storage.service import is_endrepo_zarr_url, resolve_endrepo_zarr_url_path


router = APIRouter(prefix="/api/managed-data", tags=["Managed Data"])


DATA_DIR = Path(__file__).resolve().parents[2] / "data"

class ManagedDataBulkDeleteRequest(BaseModel):
    representation_ids: list[str] = Field(default_factory=list)
    dry_run: bool = False
    delete_scope: str | None = None
    confirm_count: int | None = None


class ManagedDataBulkViewerStateRequest(BaseModel):
    representation_ids: list[str] = Field(default_factory=list)
    dry_run: bool = False


def _normalize_bulk_representation_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    for value in values or []:
        clean = str(value or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)

    return out


def _managed_data_rows_by_representation_id() -> Dict[str, Dict[str, Any]]:
    rows = augment_managed_rows_with_documents(viewer_resolver.managed_volumes_compatible())
    out: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        representation_id = str(row.get("msi_representation_id") or row.get("id") or "").strip()
        if representation_id:
            out[representation_id] = row

    return out


# MD_DELETE_SCOPE_1_GUARD
def _delete_plan_representation_ids(dry_run: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()

    if not isinstance(dry_run, dict):
        return out

    operations = dry_run.get("operations")
    if isinstance(operations, dict):
        for item in operations.get("delete_records") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("record_type") or "").strip() == "msi_representation":
                rid = str(item.get("representation_id") or "").strip()
                if rid:
                    out.add(rid)

    artifacts = dry_run.get("artifacts")
    if isinstance(artifacts, dict):
        for item in artifacts.get("msi_representations") or []:
            if isinstance(item, dict):
                rid = str(item.get("representation_id") or "").strip()
                if rid:
                    out.add(rid)

    return out


# MD_DELETE_SCOPE_1_GUARD
def _guard_delete_plan_scope(
    *,
    dry_run: Dict[str, Any],
    requested_representation_ids: Iterable[str],
    action_scope: str,
) -> Set[str]:
    requested = {str(x or "").strip() for x in requested_representation_ids}
    requested = {x for x in requested if x}
    plan_ids = _delete_plan_representation_ids(dry_run)

    if not requested:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Delete request has no explicit representation ids.",
                "delete_scope_guard": "md_delete_scope_1",
                "action_scope": action_scope,
            },
        )

    if not plan_ids:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Delete dry-run did not resolve any MSI representation records.",
                "delete_scope_guard": "md_delete_scope_1",
                "action_scope": action_scope,
                "requested_representation_ids": sorted(requested),
                "planned_representation_ids": [],
                "dry_run": dry_run,
            },
        )

    unexpected = sorted(plan_ids - requested)
    missing = sorted(requested - plan_ids)

    if unexpected:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Managed Data delete refused because the backend artifact graph "
                    "would delete representations that were not explicitly requested."
                ),
                "delete_scope_guard": "md_delete_scope_1",
                "action_scope": action_scope,
                "requested_representation_ids": sorted(requested),
                "planned_representation_ids": sorted(plan_ids),
                "unexpected_representation_ids": unexpected,
                "missing_requested_representation_ids": missing,
                "dry_run": dry_run,
            },
        )

    if action_scope == "single" and plan_ids != requested:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Single-row delete refused because the delete plan is not exactly one requested representation.",
                "delete_scope_guard": "md_delete_scope_1",
                "action_scope": action_scope,
                "requested_representation_ids": sorted(requested),
                "planned_representation_ids": sorted(plan_ids),
                "missing_requested_representation_ids": missing,
                "dry_run": dry_run,
            },
        )

    return plan_ids


def _clean_delete_value(value: Any) -> str:
    return str(value or "").strip()


def _walk_delete_values(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_delete_values(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _walk_delete_values(item)
    else:
        text = _clean_delete_value(value)
        if text:
            yield text


def _collect_delete_identity_values(
    representation_id: str,
    delete_result: Dict[str, Any],
    pre_delete_context: Dict[str, Any] | None = None,
) -> Set[str]:
    values: Set[str] = set()

    for payload in [delete_result, pre_delete_context or {}]:
        for value in _walk_delete_values(payload):
            if value:
                values.add(value)

    rid = _clean_delete_value(representation_id)
    if rid:
        values.add(rid)

        source_match = re.search(r"source_segy_(segy_[^:]+)", rid)
        if source_match:
            values.add(source_match.group(1))

        zarr_match = re.search(r"zarr_([0-9a-fA-F-]{16,})", rid)
        if zarr_match:
            values.add(zarr_match.group(1))

    return {v for v in values if v}


def _json_file_matches_values(path: Path, values: Set[str]) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False

    return any(value and value in text for value in values)


def _remove_file(path: Path, removed: list[str]) -> None:
    try:
        if path.exists() and path.is_file():
            path.unlink()
            removed.append(str(path))
    except Exception as exc:
        removed.append(f"FAILED:{path}:{exc}")


def _remove_tree(path: Path, removed: list[str]) -> None:
    try:
        if path.exists() and path.is_dir():
            shutil.rmtree(path)
            removed.append(str(path))
    except Exception as exc:
        removed.append(f"FAILED:{path}:{exc}")


def _clear_source_intake_document_assignments(values: Set[str], removed: list[str]) -> None:
    assignments_path = DATA_DIR / "source_intake_document_assignments.json"
    if not assignments_path.exists():
        return

    try:
        payload = json.loads(assignments_path.read_text(encoding="utf-8"))
    except Exception as exc:
        removed.append(f"FAILED:{assignments_path}:read:{exc}")
        return

    assignments = payload.get("assignments")
    if not isinstance(assignments, list):
        return

    kept = []
    removed_count = 0

    for assignment in assignments:
        if not isinstance(assignment, dict):
            kept.append(assignment)
            continue

        assignment_values = {
            str(assignment.get("candidate_id") or ""),
            str(assignment.get("source_segy_file_id") or ""),
            str(assignment.get("line_id") or ""),
            str(assignment.get("package_id") or ""),
            str(assignment.get("repository_id") or ""),
            str(assignment.get("scope_id") or ""),
        }

        if any(value and value in assignment_values for value in values):
            removed_count += 1
            continue

        kept.append(assignment)

    if removed_count:
        payload["assignments"] = kept
        assignments_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        removed.append(f"{assignments_path}::removed_assignments={removed_count}")


def _resolve_storage_artifact_paths(delete_result: Dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for value in _walk_delete_values(delete_result):
        text = _clean_delete_value(value)
        if not text:
            continue

        if is_endrepo_zarr_url(text):
            try:
                paths.append(resolve_endrepo_zarr_url_path(text))
            except Exception:
                pass
            continue

        if text.startswith("endrepo://managed/zarr/"):
            relative = text.replace("endrepo://", "", 1)
            paths.append(DATA_DIR / relative)
            continue

        if text.startswith("/endrepo/"):
            paths.append(DATA_DIR / text.lstrip("/"))
            continue

        if text.startswith("/data/"):
            paths.append(Path(__file__).resolve().parents[2] / text.lstrip("/"))
            continue

        if text.startswith("local://zarr/"):
            paths.append(DATA_DIR / "zarr" / text.replace("local://zarr/", "", 1))
            continue

    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _delete_source_side_artifacts_for_managed_delete(
    representation_id: str,
    delete_result: Dict[str, Any],
    pre_delete_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    values = _collect_delete_identity_values(representation_id, delete_result, pre_delete_context)
    removed_files: list[str] = []
    removed_dirs: list[str] = []

    _clear_source_intake_document_assignments(values, removed_files)

    segy_index_dir = getattr(SegyIndexService, "SEGY_INDEX_DIR", DATA_DIR / "segy_index")
    if not isinstance(segy_index_dir, Path):
        segy_index_dir = Path(segy_index_dir)

    if segy_index_dir.exists():
        for index_json in sorted(segy_index_dir.glob("*/segy_index.json")):
            if _json_file_matches_values(index_json, values):
                _remove_tree(index_json.parent, removed_dirs)

    index_job_dir = DATA_DIR / "source_intake_index_jobs"
    if index_job_dir.exists():
        for job_json in sorted(index_job_dir.glob("*.json")):
            if _json_file_matches_values(job_json, values):
                _remove_file(job_json, removed_files)

    qaqc_dir = DATA_DIR / "source_intake_qaqc"
    if qaqc_dir.exists():
        for qaqc_json in sorted(qaqc_dir.glob("*.json")):
            if any(value and value in qaqc_json.name for value in values) or _json_file_matches_values(qaqc_json, values):
                _remove_file(qaqc_json, removed_files)

    for artifact_path in _resolve_storage_artifact_paths(delete_result):
        if artifact_path.exists():
            if artifact_path.is_dir():
                _remove_tree(artifact_path, removed_dirs)
            elif artifact_path.is_file():
                _remove_file(artifact_path, removed_files)

    return {
        "identity_values": sorted(values),
        "removed_files": removed_files,
        "removed_directories": removed_dirs,
        "removed_file_count": len([x for x in removed_files if not x.startswith("FAILED:")]),
        "removed_directory_count": len([x for x in removed_dirs if not x.startswith("FAILED:")]),
    }




@router.get("")
def list_managed_data():
    """Return MSI-backed managed data rows for the viewer/Managed Data UI."""
    return augment_managed_rows_with_documents(viewer_resolver.managed_volumes_compatible())


@router.get("/")
def list_managed_data_slash():
    """Trailing-slash alias for Managed Data rows."""
    return augment_managed_rows_with_documents(viewer_resolver.managed_volumes_compatible())


@router.get("/loaded")
def list_loaded_managed_data():
    """Return MSI-backed managed data rows currently loaded into viewer selection."""
    return augment_managed_rows_with_documents(viewer_resolver.loaded_volumes_compatible())


@router.post("/{representation_id:path}/load")
def load_managed_data_representation(representation_id: str):
    """Load an MSI representation into the viewer selection."""
    try:
        return lifecycle_service.load_representation(representation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{representation_id:path}/unload")
def unload_managed_data_representation(representation_id: str):
    """Unload an MSI representation from the viewer selection."""
    try:
        return lifecycle_service.unload_representation(representation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))





def _bulk_viewer_state_response(
    request: ManagedDataBulkViewerStateRequest,
    *,
    action: str,
    load: bool,
) -> Dict[str, Any]:
    representation_ids = _normalize_bulk_representation_ids(request.representation_ids)

    if not representation_ids:
        raise HTTPException(status_code=400, detail="representation_ids is required")

    rows_by_id = _managed_data_rows_by_representation_id()
    missing_ids = [rid for rid in representation_ids if rid not in rows_by_id]

    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "One or more Managed Data representations were not found",
                "missing_representation_ids": missing_ids,
            },
        )

    targets = [
        {
            "representation_id": rid,
            "display_name": rows_by_id[rid].get("display_name") or rows_by_id[rid].get("name"),
            "dataset_type": rows_by_id[rid].get("dataset_type"),
            "viewer_mode": rows_by_id[rid].get("viewer_mode"),
            "representation_type": rows_by_id[rid].get("representation_type"),
            "is_loaded": bool(rows_by_id[rid].get("is_loaded")),
        }
        for rid in representation_ids
    ]

    actionable_targets = [
        target for target in targets
        if bool(target.get("is_loaded")) != bool(load)
    ]

    if request.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "action": action,
            "action_scope": "managed_data_viewer_catalog",
            "requested_count": len(representation_ids),
            "valid_count": len(targets),
            "actionable_count": len(actionable_targets),
            "targets": targets,
            "actionable_targets": actionable_targets,
        }

    results: list[Dict[str, Any]] = []
    errors: list[Dict[str, Any]] = []

    for rid in representation_ids:
        try:
            result = load_managed_data_representation(rid) if load else unload_managed_data_representation(rid)
            results.append(
                {
                    "representation_id": rid,
                    "ok": True,
                    "result": result,
                }
            )
        except HTTPException as exc:
            errors.append(
                {
                    "representation_id": rid,
                    "ok": False,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "representation_id": rid,
                    "ok": False,
                    "status_code": 500,
                    "detail": str(exc),
                }
            )

    return {
        "ok": not errors,
        "dry_run": False,
        "action": action,
        "action_scope": "managed_data_viewer_catalog",
        "requested_count": len(representation_ids),
        "succeeded_count": len(results),
        "failed_count": len(errors),
        "results": results,
        "errors": errors,
    }


@router.post("/bulk/load-selected")
def bulk_load_selected_managed_data(request: ManagedDataBulkViewerStateRequest) -> Dict[str, Any]:
    """Bulk-load explicitly selected MSI representations into the viewer catalog/dropdown."""
    return _bulk_viewer_state_response(request, action="load_selected", load=True)


@router.post("/bulk/unload-selected")
def bulk_unload_selected_managed_data(request: ManagedDataBulkViewerStateRequest) -> Dict[str, Any]:
    """Bulk-unload explicitly selected MSI representations from the viewer catalog/dropdown."""
    return _bulk_viewer_state_response(request, action="unload_selected", load=False)


# MD_DELETE_SCOPE_FINAL_API
@router.post("/bulk/delete-selected")
def bulk_delete_selected_managed_data(request: ManagedDataBulkDeleteRequest) -> Dict[str, Any]:
    representation_ids = _normalize_bulk_representation_ids(request.representation_ids)
    if not representation_ids:
        raise HTTPException(status_code=400, detail="representation_ids is required")

    delete_scope = str(request.delete_scope or ("single" if len(representation_ids) == 1 else "selected")).strip()
    confirm_count = request.confirm_count if request.confirm_count is not None else len(representation_ids)

    try:
        if request.dry_run:
            return managed_data_delete_service.plan_delete(
                representation_ids,
                delete_scope=delete_scope,
                confirm_count=confirm_count,
            )
        result = managed_data_delete_service.execute_delete(
            representation_ids,
            delete_scope=delete_scope,
            confirm_count=confirm_count,
            delete_orphan_managed_documents=True,
        )
    except KeyError as exc:
        detail_text = str(exc)
        try:
            detail = json.loads(detail_text.strip("'"))
        except Exception:
            detail = detail_text
        raise HTTPException(status_code=404, detail=detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Managed Data isolated delete failed: {exc}") from exc

    if not result.get("ok", False):
        raise HTTPException(status_code=409, detail=result)
    return result

# MD_DELETE_SCOPE_FINAL_API
@router.delete("/{representation_id:path}")
def delete_managed_data_representation(representation_id: str):
    clean_representation_id = str(representation_id or "").strip()
    if not clean_representation_id:
        raise HTTPException(status_code=400, detail="representation_id is required")
    try:
        result = managed_data_delete_service.execute_delete(
            [clean_representation_id],
            delete_scope="single",
            confirm_count=1,
            delete_orphan_managed_documents=True,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Representation not found: {clean_representation_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Managed Data isolated delete failed: {exc}") from exc

    if not result.get("ok", False):
        raise HTTPException(status_code=409, detail=result)
    return result

@router.get("/query")
def query_managed_data_enterprise(
    q: str | None = None,
    dataset_type: str | None = None,
    viewer_mode: str | None = None,
    representation_type: str | None = None,
    loaded: bool | None = None,
    limit: int = 100,
    offset: int = 0,
    sort_by: str = "display_name",
    sort_dir: str = "asc",
):
    """
    Enterprise-shaped Managed Data query endpoint.

    This is the backend-owned paged/searchable MSI workbench contract.
    The legacy GET /api/managed-data endpoint remains available for
    compatibility, but scalable MD UI should use this route.
    """
    from app.services.managed_data_query_service import query_managed_data_rows

    return query_managed_data_rows(
        q=q,
        dataset_type=dataset_type,
        viewer_mode=viewer_mode,
        representation_type=representation_type,
        loaded=loaded,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_dir="desc" if str(sort_dir or "").lower() == "desc" else "asc",
    )

