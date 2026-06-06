from __future__ import annotations

"""
Backend-owned Source Artifact Maintenance service.

This service owns maintenance semantics for source SEG-Y derived artifacts.
The frontend must not infer dependency behavior, filesystem ownership,
registry mutation, or lifecycle transitions.

Initial scope:
- read-only preflight only
- no filesystem mutation
- no registry mutation
- no lifecycle mutation
"""

from typing import Any, Dict

from app.services.source_segy_lifecycle_service import build_source_segy_lifecycle


VALID_MODES = {"2d", "3d"}
VALID_ACTIONS = {"delete"}

ARTIFACT_LABELS = {
    "index_preview": "Index / Preview",
    "fast_zarr_cache": "Fast Zarr Cache",
    "managed_zarr": "Managed Zarr",
    "managed_2d_line_zarr": "Managed 2D Line Zarr",
}

MODE_ARTIFACTS = {
    "3d": {"index_preview", "fast_zarr_cache", "managed_zarr"},
    "2d": {"managed_2d_line_zarr"},
}


def _clean_mode(mode: str) -> str:
    clean = str(mode or "3d").strip().lower()
    if clean not in VALID_MODES:
        raise ValueError(f"Unsupported maintenance mode: {mode!r}. Expected 2d or 3d.")
    return clean


def _clean_action(action: str) -> str:
    clean = str(action or "delete").strip().lower()
    if clean not in VALID_ACTIONS:
        raise ValueError(f"Unsupported maintenance action: {action!r}. Expected delete.")
    return clean


def _clean_artifact_key(artifact_key: str, mode: str) -> str:
    clean = str(artifact_key or "").strip().lower()
    allowed = MODE_ARTIFACTS[mode]
    if clean not in allowed:
        raise ValueError(
            f"Artifact {artifact_key!r} is not valid for mode={mode}. "
            f"Expected one of: {sorted(allowed)}"
        )
    return clean


def _rows_by_key(lifecycle: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = lifecycle.get("representations") or []
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("key")): row
        for row in rows
        if isinstance(row, dict) and row.get("key")
    }


def _delete_impact(artifact_key: str, mode: str) -> Dict[str, Any]:
    if artifact_key == "index_preview":
        return {
            "deletes": ["Index / Preview", "Fast Zarr Cache"],
            "preserves": ["Source SEG-Y", "Submitted handoff", "Managed Zarr"],
            "dependency_behavior": "Deleting Index / Preview also deletes any attached Fast Zarr Cache.",
            "viewer_impact": "No managed volume is removed.",
            "source_data_deleted": False,
            "submitted_handoff_deleted": False,
        }

    if artifact_key == "fast_zarr_cache":
        return {
            "deletes": ["Fast Zarr Cache"],
            "preserves": ["Source SEG-Y", "Submitted handoff", "Index / Preview", "Managed Zarr"],
            "dependency_behavior": "Deletes Fast Zarr Cache only. Preserves Index / Preview.",
            "viewer_impact": "No managed volume is removed.",
            "source_data_deleted": False,
            "submitted_handoff_deleted": False,
        }

    if artifact_key in {"managed_zarr", "managed_2d_line_zarr"}:
        label = ARTIFACT_LABELS[artifact_key]
        preserves = ["Source SEG-Y", "Submitted handoff"]
        if mode == "3d":
            preserves += ["Index / Preview", "Fast Zarr Cache"]

        return {
            "deletes": [label],
            "preserves": preserves,
            "dependency_behavior": f"Deletes {label} only. Source SEG-Y remains available for recreation.",
            "viewer_impact": "The managed dataset is removed from Managed Data and the viewer dropdown.",
            "source_data_deleted": False,
            "submitted_handoff_deleted": False,
        }

    raise ValueError(f"No delete impact rule defined for artifact: {artifact_key}")


def build_source_artifact_maintenance_preflight(
    *,
    segy_file_id: str,
    artifact_key: str,
    action: str = "delete",
    mode: str = "3d",
) -> Dict[str, Any]:
    clean_mode = _clean_mode(mode)
    clean_action = _clean_action(action)
    clean_key = _clean_artifact_key(artifact_key, clean_mode)

    lifecycle = build_source_segy_lifecycle(segy_file_id=segy_file_id, mode=clean_mode)
    row = _rows_by_key(lifecycle).get(clean_key)

    allowed = False
    if row and clean_action == "delete":
        # Normal lifecycle deliberately hides destructive raw delete URLs.
        # Maintenance authorization is owned here and is based on artifact state.
        state = str(row.get("state") or "").strip().lower()
        allowed = state == "exists"

    reason = (
        "Action is allowed by the backend maintenance contract."
        if allowed
        else f"{ARTIFACT_LABELS[clean_key]} is not currently deletable."
    )

    return {
        "status": "ok",
        "source_id": segy_file_id,
        "mode": clean_mode,
        "artifact_key": clean_key,
        "artifact_label": ARTIFACT_LABELS[clean_key],
        "action": clean_action,
        "allowed": allowed,
        "reason": reason,
        "requires_confirmation": True,
        "impact": _delete_impact(clean_key, clean_mode),
        "lifecycle_row": row,
        "lifecycle_monitor": lifecycle.get("monitor"),
    }

from app.services.source_segy_representation_service import build_source_segy_representations_by_id
from app.services.dataset_registry_service import delete_dataset, delete_dataset_optimized_cache
from app.services.volume_registry_service import delete_volume as delete_volume_service


def _maintenance_representations(segy_file_id: str, mode: str) -> Dict[str, Any]:
    payload = build_source_segy_representations_by_id(segy_file_id, mode=mode)
    reps = payload.get("representations") or {}
    if not isinstance(reps, dict):
        raise ValueError("Malformed representation payload; expected representations dictionary.")
    return reps


def _maintenance_dataset_id(segy_file_id: str, mode: str) -> str:
    reps = _maintenance_representations(segy_file_id, mode)
    indexed = reps.get("indexed_preview") or {}
    dataset_id = indexed.get("dataset_id")
    if not dataset_id:
        raise FileNotFoundError(f"Indexed preview dataset is not available for source SEG-Y: {segy_file_id}")
    return str(dataset_id)


def _maintenance_volume_id(segy_file_id: str, mode: str) -> str:
    reps = _maintenance_representations(segy_file_id, mode)
    managed = reps.get("zarr_full_conversion") or {}
    volume_id = managed.get("volume_id")
    if not volume_id:
        raise FileNotFoundError(f"Managed Zarr volume is not available for source SEG-Y: {segy_file_id}")
    return str(volume_id)


def execute_source_artifact_maintenance(
    *,
    segy_file_id: str,
    artifact_key: str,
    action: str = "delete",
    mode: str = "3d",
    confirm: bool = False,
) -> Dict[str, Any]:
    """
    Execute backend-owned source artifact maintenance.

    This is the managed-service boundary for destructive derived-artifact actions.
    Frontend callers must not call raw delete URLs directly.
    """
    if not confirm:
        raise PermissionError("Maintenance execution requires confirm=true.")

    preflight = build_source_artifact_maintenance_preflight(
        segy_file_id=segy_file_id,
        artifact_key=artifact_key,
        action=action,
        mode=mode,
    )

    if not preflight.get("allowed"):
        raise PermissionError(preflight.get("reason") or "Maintenance action is not currently allowed.")

    clean_mode = preflight["mode"]
    clean_key = preflight["artifact_key"]
    clean_action = preflight["action"]

    if clean_action != "delete":
        raise ValueError(f"Unsupported maintenance action: {clean_action}")

    if clean_key == "index_preview":
        raw_result = delete_dataset(_maintenance_dataset_id(segy_file_id, clean_mode))
    elif clean_key == "fast_zarr_cache":
        raw_result = delete_dataset_optimized_cache(_maintenance_dataset_id(segy_file_id, clean_mode))
    elif clean_key in {"managed_zarr", "managed_2d_line_zarr"}:
        raw_result = delete_volume_service(_maintenance_volume_id(segy_file_id, clean_mode))
    else:
        raise ValueError(f"Unsupported artifact key: {clean_key}")

    lifecycle_after = build_source_segy_lifecycle(segy_file_id=segy_file_id, mode=clean_mode)

    return {
        "status": "ok",
        "source_id": segy_file_id,
        "mode": clean_mode,
        "artifact_key": clean_key,
        "artifact_label": preflight.get("artifact_label"),
        "action": clean_action,
        "preflight": preflight,
        "action_result": {
            **raw_result,
            "artifact_key": clean_key,
            "artifact_label": preflight.get("artifact_label"),
            "action": clean_action,
            "dependency_behavior": preflight.get("impact", {}).get("dependency_behavior"),
            "preserved_source_segy": True,
            "preserved_submitted_handoff": True,
        },
        "lifecycle_after": lifecycle_after,
    }
