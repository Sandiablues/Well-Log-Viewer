from __future__ import annotations

"""
Canonical source SEG-Y lifecycle service.

This is the backend-owned lifecycle contract for source SEG-Y derived
representations. It standardizes the UI-facing lifecycle model across 2D and
3D without letting React infer state from datasets, volumes, job JSON, stale
conversion fields, or representation internals.

Block 1 scope:
- read-only lifecycle contract
- mode-aware: mode=2d or mode=3d
- wraps the existing backend command-state resolver
- exposes canonical action/delete URLs
- does not implement create/delete behavior here

Action/delete endpoint implementation belongs to the lifecycle API/router,
not the frontend.
"""

from typing import Any, Dict, List

from app.services.source_segy_edr_command_state_service import (
    build_source_segy_edr_command_state,
)
from app.services.source_segy_representation_service import (
    build_source_segy_representations_by_id,
)
from app.msi.repository import MSIRepository


VALID_MODES = {"2d", "3d"}


ACTION_BY_KEY = {
    "index_preview": "create-index",
    "fast_zarr_cache": "build-fast-zarr-cache",
    "managed_zarr": "create-managed-zarr",
}


DELETE_BY_KEY = {
    "index_preview": "index-preview",
    "fast_zarr_cache": "fast-zarr-cache",
    "managed_zarr": "managed-zarr",
}


LOADABLE_EXISTING_KEYS = {
    "index_preview",
    "fast_zarr_cache",
    "managed_zarr",
}




def _safe_msi_status_for_source(
    *,
    segy_file_id: str,
    physical_volume_id: Any = None,
) -> Dict[str, Any]:
    """
    Resolve read-only MSI registration status for a source SEG-Y full-Zarr artifact.

    This is lifecycle status plumbing only. It does not register, load, unload,
    mutate, or create MSI rows.
    """
    source_id = str(segy_file_id or "").strip()
    volume_id = str(physical_volume_id or "").strip()

    default = {
        "msi_registered": False,
        "msi_dataset_id": None,
        "msi_representation_id": None,
        "msi_registration_state": None,
        "msi_lifecycle_state": None,
        "msi_viewer_ready": False,
        "msi_is_preferred": False,
        "msi_physical_volume_id": None,
        "msi_zarr_url": None,
        "msi_storage_uri": None,
    }

    if not source_id:
        return default

    dataset_id = f"source_segy:{source_id}"

    try:
        repo = MSIRepository()

        dataset = None
        try:
            for item in repo.list_datasets():
                if getattr(item, "dataset_id", None) == dataset_id:
                    dataset = item
                    break
        except Exception:
            dataset = None

        representations = repo.list_representations(dataset_id)
        if not representations:
            return default

        selected = None

        if volume_id:
            for rep in representations:
                artifact = getattr(rep, "artifact_summary", {}) or {}
                if str(artifact.get("volume_id") or "").strip() == volume_id:
                    selected = rep
                    break

        if selected is None:
            selected = sorted(
                representations,
                key=lambda rep: (
                    1 if getattr(rep, "is_preferred", False) else 0,
                    1 if getattr(rep, "viewer_ready", False) else 0,
                    str(getattr(rep, "updated_at", "") or ""),
                ),
                reverse=True,
            )[0]

        artifact = getattr(selected, "artifact_summary", {}) or {}
        storage_uri = getattr(selected, "storage_uri", None)

        return {
            "msi_registered": True,
            "msi_dataset_id": dataset_id,
            "msi_representation_id": getattr(selected, "representation_id", None),
            "msi_registration_state": getattr(dataset, "registration_state", None) if dataset else None,
            "msi_lifecycle_state": getattr(selected, "lifecycle_state", None),
            "msi_viewer_ready": bool(getattr(selected, "viewer_ready", False)),
            "msi_is_preferred": bool(getattr(selected, "is_preferred", False)),
            "msi_physical_volume_id": artifact.get("volume_id"),
            "msi_zarr_url": artifact.get("zarr_url"),
            "msi_storage_uri": storage_uri,
        }

    except Exception as exc:
        return {
            **default,
            "msi_status_error": str(exc),
        }


def _normalize_mode(mode: str) -> str:
    clean = str(mode or "3d").strip().lower()
    if clean not in VALID_MODES:
        raise ValueError(f"Unsupported lifecycle mode: {mode!r}. Expected one of: 2d, 3d.")
    return clean


def _can_create(item: Dict[str, Any]) -> bool:
    state = str(item.get("state") or "").strip().lower()
    action_enabled = bool(item.get("action_enabled"))

    # Preserve the existing backend decision where available.
    if action_enabled:
        return True

    # Failed/missing representations are generally recreatable, but do not
    # enable action blindly unless the underlying command-state service already
    # says the action is available. This prevents invented UI behavior.
    return False


def _can_load(item: Dict[str, Any]) -> bool:
    key = str(item.get("key") or "")
    state = str(item.get("state") or "").strip().lower()
    return key in LOADABLE_EXISTING_KEYS and state == "exists"


def _can_delete(item: Dict[str, Any]) -> bool:
    """
    Normal lifecycle status must not expose destructive raw delete actions.

    Artifact deletion is owned by SourceArtifactMaintenanceService via
    preflight/execute endpoints. The lifecycle contract may still report
    state and safe create/recreate actions, but it should not hand frontend
    panels raw delete URLs.
    """
    return False


def _can_archive(item: Dict[str, Any]) -> bool:
    key = str(item.get("key") or "")
    state = str(item.get("state") or "").strip().lower()

    # Archive is lifecycle semantics for durable managed volumes first.
    # Do not expose archive for cache/index in the initial canonical contract.
    return key == "managed_zarr" and state == "exists"


def _representation_to_lifecycle(
    *,
    segy_file_id: str,
    item: Dict[str, Any],
) -> Dict[str, Any]:
    key = str(item.get("key") or "")
    action_slug = ACTION_BY_KEY.get(key)
    delete_slug = DELETE_BY_KEY.get(key)

    action_url = (
        f"/api/segy-files/{segy_file_id}/actions/{action_slug}"
        if action_slug
        else None
    )
    delete_url = (
        f"/api/segy-files/{segy_file_id}/representations/{delete_slug}"
        if delete_slug
        else None
    )

    can_create = _can_create(item)
    can_load = _can_load(item)
    can_delete = _can_delete(item)
    can_archive = _can_archive(item)

    # Do not hand the frontend enabled URLs for actions that the backend
    # currently considers disabled.
    if not can_create:
        action_url = None

    if not can_delete:
        delete_url = None

    row = {
        "key": key,
        "label": item.get("label") or key,
        "state": item.get("state"),
        "status_label": item.get("status_label"),
        "can_create": can_create,
        "can_load": can_load,
        "can_delete": can_delete,
        "can_archive": can_archive,
        "action_url": action_url,
        "delete_url": delete_url,
    }

    # Preserve read-only artifact identity/status fields for lifecycle consumers.
    # These fields are not commands; they let the UI show backend-owned status
    # without inferring from separate registries.
    for field in [
        "volume_id",
        "zarr_url",
        "job_id",
        "dataset_id",
        "representation_type",
        "artifact_status",
        "status",
        "available",
    ]:
        if field in item:
            row[field] = item.get(field)

    if key == "managed_zarr":
        msi_status = _safe_msi_status_for_source(
            segy_file_id=segy_file_id,
            physical_volume_id=item.get("volume_id"),
        )
        row.update(msi_status)

        # Some 3D command-state rows report managed_zarr exists but omit the
        # physical artifact identity. Fill read-only identity from MSI so 3D
        # lifecycle matches the 2D lifecycle contract.
        if not row.get("volume_id"):
            row["volume_id"] = msi_status.get("msi_physical_volume_id")
        if not row.get("zarr_url"):
            row["zarr_url"] = msi_status.get("msi_zarr_url")

    return row


def _raw_status_to_state(
    rep: Dict[str, Any],
    *,
    managed: bool = False,
) -> Dict[str, str]:
    raw_status = str(rep.get("status") or rep.get("artifact_status") or "").strip().lower().replace("_", " ")
    available = bool(rep.get("available"))

    if available:
        return {"state": "exists", "status_label": "Exists"}

    if raw_status in {"queued", "running", "converting", "reading metadata", "reading index", "validating zarr", "promoting output"}:
        return {"state": "running", "status_label": "In progress"}

    if raw_status in {"failed", "error"}:
        return {"state": "failed", "status_label": "Failed"}

    if raw_status in {"reconvert required", "missing"}:
        return {"state": "missing", "status_label": "Missing"}

    if managed:
        return {"state": "not_converted", "status_label": "Not converted"}

    return {"state": "not_created", "status_label": "Not created"}




RECREATABLE_MANAGED_2D_STATES = {
    "not_created",
    "not_converted",
    "missing",
    "failed",
}


def _can_create_managed_2d(
    *,
    source: Dict[str, Any],
    managed: Dict[str, Any],
    state: str,
) -> bool:
    """
    Backend-owned create/recreate gate for managed 2D line Zarr.

    The previous lifecycle contract delegated this entirely to the derived
    source-representation flag `action_available`. That flag can become false
    when an old failed/missing MSI/source representation exists, producing the
    invalid state observed during testing:

        state = missing / reconvert_required / failed
        can_create = false
        action_url = null

    A managed 2D line can be created or recreated when the source candidate is
    still a valid 2D line candidate, the source file exists, and no conversion
    is currently running or available. The lower action endpoint still performs
    authoritative validation before creating the job.
    """
    clean_state = str(state or "").strip().lower()

    if bool(managed.get("action_available")):
        return True

    if clean_state not in RECREATABLE_MANAGED_2D_STATES:
        return False

    candidate_kind = str(source.get("candidate_kind") or "").strip().lower()
    candidate_role = str(source.get("candidate_role") or "").strip().lower()
    source_path_exists = bool(source.get("source_path_exists"))

    is_2d_candidate = candidate_kind == "2d_line" or candidate_role == "line_candidate"

    return bool(source_path_exists and is_2d_candidate)


def _build_2d_lifecycle(segy_file_id: str) -> Dict[str, Any]:
    """
    2D lifecycle contract.

    Important: do not copy 3D rows blindly. Current backend evidence supports
    managed 2D line conversion, while index-preview and fast-cache are still
    3D-index-service semantics. Add 2D index/cache only after those services
    are verified for 2D line geometry.
    """
    payload = build_source_segy_representations_by_id(segy_file_id, mode="2d")
    source = payload.get("source") or {}
    reps = payload.get("representations") or {}
    managed = reps.get("zarr_full_conversion") or {}

    source_id = source.get("source_segy_file_id") or segy_file_id
    state = _raw_status_to_state(managed, managed=True)

    can_create = _can_create_managed_2d(
        source=source,
        managed=managed,
        state=state["state"],
    )
    can_load = state["state"] == "exists"
    can_delete = state["state"] == "exists"
    can_archive = state["state"] == "exists"

    active_job = None
    job_id = managed.get("job_id")
    if state["state"] == "running" and job_id:
        active_job = {
            "job_id": job_id,
            "action": "create_managed_2d_line_zarr",
            "label": "Creating managed 2D line Zarr",
            "status": managed.get("status") or managed.get("artifact_status"),
            "progress": None,
            "message": "2D line conversion is running.",
        }

    row = {
        "key": "managed_2d_line_zarr",
        "label": "Managed 2D Line Zarr",
        "state": state["state"],
        "status_label": state["status_label"],
        "can_create": can_create,
        "can_load": can_load,
        "can_delete": can_delete,
        "can_archive": can_archive,
        "action_url": f"/api/segy-files/{source_id}/actions/create-managed-2d-line-zarr" if can_create else None,
        "delete_url": f"/api/segy-files/{source_id}/representations/managed-2d-line-zarr" if can_delete else None,
        "volume_id": managed.get("volume_id"),
        "zarr_url": managed.get("zarr_url"),
        "job_id": managed.get("job_id"),
        "representation_type": managed.get("representation_type"),
        "artifact_status": managed.get("artifact_status"),
        "status": managed.get("status"),
        "available": managed.get("available"),
    }

    row.update(
        _safe_msi_status_for_source(
            segy_file_id=source_id,
            physical_volume_id=managed.get("volume_id"),
        )
    )

    if state["state"] == "running":
        monitor = {
            "state": "running",
            "label": "Creating managed 2D line Zarr",
            "message": "Managed 2D line conversion is running.",
        }
    elif state["state"] == "exists":
        monitor = {
            "state": "complete",
            "label": "Managed 2D line available",
            "message": "Managed 2D Line Zarr exists.",
        }
    elif state["state"] == "missing":
        monitor = {
            "state": "warning",
            "label": "Managed 2D line missing",
            "message": "The managed 2D line artifact is missing and can be recreated.",
        }
    else:
        monitor = {
            "state": "ready",
            "label": "Ready",
            "message": "Create Managed 2D Line Zarr.",
        }

    return {
        "status": "ok",
        "source_id": source_id,
        "mode": "2d",
        "display_name": source.get("filename"),
        "source": {
            "segy_file_id": source_id,
            "filename": source.get("filename"),
            "source_path_exists": bool(source.get("source_path_exists")),
            "candidate_kind": source.get("candidate_kind"),
            "candidate_role": source.get("candidate_role"),
        },
        "representations": [row],
        "active_job": active_job,
        "monitor": monitor,
    }


def _build_3d_lifecycle(segy_file_id: str) -> Dict[str, Any]:
    command_state = build_source_segy_edr_command_state(
        segy_file_id,
        mode="3d",
    )

    source = command_state.get("source") or {}
    source_id = source.get("segy_file_id") or segy_file_id

    raw_representations = command_state.get("representations") or []
    if not isinstance(raw_representations, list):
        raw_representations = []

    representations: List[Dict[str, Any]] = [
        _representation_to_lifecycle(
            segy_file_id=source_id,
            item=item,
        )
        for item in raw_representations
        if isinstance(item, dict)
    ]

    return {
        "status": "ok",
        "source_id": source_id,
        "mode": "3d",
        "display_name": source.get("filename"),
        "source": {
            "segy_file_id": source_id,
            "filename": source.get("filename"),
            "source_path_exists": bool(source.get("source_path_exists")),
            "candidate_kind": source.get("candidate_kind"),
            "candidate_role": source.get("candidate_role"),
        },
        "representations": representations,
        "active_job": command_state.get("active_job"),
        "monitor": command_state.get("monitor"),
    }


def build_source_segy_lifecycle(
    segy_file_id: str,
    mode: str = "3d",
) -> Dict[str, Any]:
    clean_mode = _normalize_mode(mode)

    if clean_mode == "2d":
        return _build_2d_lifecycle(segy_file_id)

    return _build_3d_lifecycle(segy_file_id)
