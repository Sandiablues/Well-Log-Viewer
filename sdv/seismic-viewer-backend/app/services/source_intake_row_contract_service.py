from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
JOBS_DIR = DATA_DIR / "jobs"

# REBUILD-REMOVAL-2B: rebuild workflow is disabled at the row-contract boundary.
# Historical rebuild job files remain on disk for audit, but they must not
# influence active Source Intake rows, progress labels, or action contracts.
_REBUILD_WORKFLOW_ENABLED = False
_REBUILD_DISABLED_REASON = "Rebuild workflow has been retired for this build."

_ACTIVE_JOB_STATES = {
    "queued",
    "pending",
    "submitted",
    "started",
    "running",
    "building",
    "converting",
    "in_progress",
    "reading_metadata",
    "validating_zarr",
    "promoting_output",
}
_COMPLETE_JOB_STATES = {"complete", "completed", "success", "succeeded"}
_FAILED_JOB_STATES = {"failed", "error", "errored", "cancelled", "canceled"}

_2D_KINDS = {"2d_line", "2d"}
_2D_ROLES = {"line_candidate", "line"}
_3D_KINDS = {"3d_volume", "3d"}
_3D_ROLES = {"volume_candidate", "volume"}

_CANONICAL_LIFECYCLE_STATES = {
    "viewer_ready",
    "not_converted",
    "rebuilding",
    "staged_ready",
    "promotion_complete",
    "discarded",
    "failed",
    "blocked",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_lower(value: Any) -> str:
    return _clean(value).lower()


def _candidate_id(row: Dict[str, Any]) -> str:
    for key in ("candidate_id", "source_segy_file_id", "segy_file_id", "id"):
        value = _clean(row.get(key))
        if value:
            return value
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    for key in ("candidate_id", "source_segy_file_id", "segy_file_id", "id"):
        value = _clean(source.get(key))
        if value:
            return value
    return ""


def _dimension(row: Dict[str, Any]) -> str:
    kind = _clean_lower(row.get("candidate_kind"))
    role = _clean_lower(row.get("candidate_role"))
    if kind in _2D_KINDS or role in _2D_ROLES:
        return "2d"
    if kind in _3D_KINDS or role in _3D_ROLES:
        return "3d"
    return "unknown"


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_percent(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return 0.0
    if number > 100:
        return 100.0
    return number


def _job_timestamp(job: Dict[str, Any]) -> str:
    for key in ("updated_at", "completed_at", "finished_at", "created_at", "started_at"):
        value = _clean(job.get(key))
        if value:
            return value
    return ""


# INDEX-RECOVERY-6: completed indexed-preview terminal presentation
def _completed_index_preview_state(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Return completed Source Intake index job state without changing the canonical
    row lifecycle. Indexed preview is a source-side preview artifact, not a
    managed Zarr/viewer-ready MSI lifecycle state.
    """
    job = _as_dict(row.get("job"))
    last_action = _as_dict(row.get("last_action"))

    candidates = [job, last_action]
    for item in candidates:
        item_type = _clean_lower(item.get("job_type") or item.get("type"))
        item_state = _clean_lower(item.get("state") or item.get("status"))
        message = str(item.get("message") or "")

        is_index_type = (
            "index" in item_type
            or "indexed" in item_type
            or "indexed" in message.lower()
            or "index complete" in message.lower()
        )
        is_complete = item_state in {"complete", "completed", "ready", "succeeded", "success"}

        if is_index_type and is_complete:
            dataset_id = (
                item.get("dataset_id")
                or job.get("dataset_id")
                or last_action.get("dataset_id")
            )
            return {
                "job_id": item.get("job_id") or job.get("job_id") or last_action.get("job_id"),
                "dataset_id": dataset_id,
                "message": message or "Indexed preview is available.",
                "progress": item.get("progress") if item.get("progress") is not None else 100,
            }

    return None


def _source_intake_candidate_id(row: Dict[str, Any]) -> Optional[str]:
    candidate_id = (
        row.get("candidate_id")
        or row.get("segy_file_id")
        or row.get("source_segy_file_id")
        or row.get("id")
    )
    return str(candidate_id).strip() if candidate_id else None


class SourceIntakeRowContractService:
    """Backend-owned row contract enricher for Source Intake Workbench V2.

    This service adds canonical lifecycle, progress, presentation, and action
    contracts to row-builder output. It is intentionally additive for SI-1:
    existing row fields remain present for frontend compatibility, but the new
    fields become the backend-owned source of truth for future frontend cleanup.
    """

    def enrich_rows(self, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        staged_by_candidate = self._latest_staged_rebuilds_by_candidate() if _REBUILD_WORKFLOW_ENABLED else {}
        enriched: List[Dict[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            row = dict(raw)
            candidate_id = _candidate_id(row)
            staged = staged_by_candidate.get(candidate_id) if candidate_id else None
            row["dimension"] = _dimension(row)
            if staged and _REBUILD_WORKFLOW_ENABLED:
                row["staged_rebuild_result"] = staged
                row["promotion_required"] = bool(staged.get("promotion_required"))
                row["promotion_options"] = staged.get("promotion_options") or []
            else:
                row.pop("staged_rebuild_result", None)
                row.pop("promotion_required", None)
                row.pop("promotion_options", None)
            lifecycle = self._lifecycle(row, staged if _REBUILD_WORKFLOW_ENABLED else None)
            staged_resolution = self._staged_rebuild_resolution(row, staged if _REBUILD_WORKFLOW_ENABLED else None, lifecycle)
            if staged_resolution:
                row["staged_rebuild"] = staged_resolution
                row["next_action"] = staged_resolution.get("next_action")
            else:
                row.pop("staged_rebuild", None)
                row.pop("next_action", None)
            progress = self._progress(row, lifecycle, staged if _REBUILD_WORKFLOW_ENABLED else None)
            presentation = self._presentation(row, lifecycle)
            row["lifecycle"] = lifecycle
            row["progress"] = progress
            row["presentation"] = presentation
            row["last_action"] = self._last_action(row, staged if _REBUILD_WORKFLOW_ENABLED else None)
            row["actions"] = self._actions(row, lifecycle)
            row["action_contract"] = {
                "schema_version": "source_intake.row_actions.v1",
                "row_level": row["actions"],
            }
            self._assert_row_contract(row)
            enriched.append(row)
        return enriched

    def _lifecycle(self, row: Dict[str, Any], staged: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        status = _as_dict(row.get("status"))
        status_state = _clean_lower(status.get("state"))
        status_reason = status.get("reason")
        managed_state = _clean_lower(row.get("managed_state"))
        conversion_state = _clean_lower(row.get("conversion_state"))
        job = _as_dict(row.get("job"))
        job_state = _clean_lower(job.get("state") or job.get("status"))
        staged_status = _clean_lower(staged.get("status") if isinstance(staged, dict) else None)
        staged_stage = _clean_lower(staged.get("progress_stage") if isinstance(staged, dict) else None)

        if job_state in _ACTIVE_JOB_STATES:
            return self._lifecycle_payload(
                "rebuilding",
                "Rebuilding",
                job.get("message") or "A conversion or rebuild job is running.",
                active=True,
            )

        if staged and staged_status in _ACTIVE_JOB_STATES:
            return self._lifecycle_payload(
                "rebuilding",
                "Rebuilding",
                staged.get("message") or "A staged rebuild is running.",
                active=True,
            )

        if staged and bool(staged.get("promotion_required")) and staged_status in _COMPLETE_JOB_STATES:
            return self._lifecycle_payload(
                "staged_ready",
                "Staged Rebuild Ready",
                "A staged rebuild completed and is waiting for promotion.",
                terminal=False,
            )

        if staged and "discard" in staged_stage:
            return self._lifecycle_payload(
                "discarded",
                "Rebuild Discarded",
                "The latest staged rebuild was discarded.",
                terminal=True,
            )

        if staged and "promoted" in staged_stage and not bool(staged.get("promotion_required")):
            if managed_state == "viewer_ready":
                return self._lifecycle_payload(
                    "viewer_ready",
                    "Viewer Ready",
                    "Managed representation is viewer-ready after promotion.",
                    terminal=True,
                )
            return self._lifecycle_payload(
                "promotion_complete",
                "Promotion Complete",
                "Staged rebuild promotion completed.",
                terminal=True,
            )

        if staged and staged_status in _FAILED_JOB_STATES and bool(staged.get("promotion_required")):
            return self._lifecycle_payload(
                "failed",
                "Rebuild Failed",
                staged.get("message") or staged.get("error") or "The latest unresolved staged rebuild failed.",
                failed=True,
                terminal=True,
            )

        if job_state in _FAILED_JOB_STATES and managed_state != "viewer_ready":
            return self._lifecycle_payload(
                "failed",
                "Failed",
                job.get("message") or job.get("error") or status_reason or "The latest unresolved job failed.",
                failed=True,
                terminal=True,
            )

        if managed_state == "viewer_ready":
            return self._lifecycle_payload(
                "viewer_ready",
                "Viewer Ready",
                "Managed representation is viewer-ready.",
                terminal=True,
            )

        if status_state == "blocked":
            return self._lifecycle_payload(
                "blocked",
                status.get("label") or "Blocked",
                status_reason or "Backend checks block conversion.",
                terminal=True,
            )

        if conversion_state == "building" or status_state == "building":
            return self._lifecycle_payload(
                "rebuilding",
                "Building",
                status_reason or "A build job is running.",
                active=True,
            )

        if conversion_state == "failed" or managed_state == "failed" or status_state == "failed":
            return self._lifecycle_payload(
                "failed",
                status.get("label") or "Failed",
                status_reason or "Backend conversion or managed output state is failed.",
                failed=True,
                terminal=True,
            )

        return self._lifecycle_payload(
            "not_converted",
            status.get("label") or "Not Converted",
            status_reason or "No managed viewer-ready representation exists yet.",
            terminal=False,
        )

    @staticmethod
    def _lifecycle_payload(
        state: str,
        label: str,
        reason: Any,
        *,
        active: bool = False,
        failed: bool = False,
        terminal: bool = False,
    ) -> Dict[str, Any]:
        return {
            "schema_version": "source_intake.row_lifecycle.v1",
            "state": state,
            "label": label,
            "reason": _clean(reason),
            "active": bool(active),
            "failed": bool(failed),
            "terminal": bool(terminal),
        }

    def _last_action(self, row: Dict[str, Any], staged: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Return secondary last-action history for UI/debugging.

        This is deliberately separate from lifecycle/progress.  A completed
        index job may be useful history, but it must not override a later
        canonical viewer_ready / managed state on the row.
        """
        job = _as_dict(row.get("job"))
        if isinstance(staged, dict) and staged:
            staged_state = _clean_lower(staged.get("status") or staged.get("state"))
            return {
                "schema_version": "source_intake.row_last_action.v1",
                "type": "staged_rebuild",
                "state": staged_state or None,
                "message": staged.get("message") or staged.get("error"),
                "progress": staged.get("progress"),
                "updated_at": staged.get("updated_at") or staged.get("completed_at") or staged.get("created_at"),
                "job_id": staged.get("job_id") or staged.get("id"),
            }

        if not job:
            return {
                "schema_version": "source_intake.row_last_action.v1",
                "type": None,
                "state": None,
                "message": None,
                "progress": None,
                "updated_at": None,
                "job_id": None,
            }

        job_type = _clean_lower(job.get("type") or job.get("job_type") or job.get("action"))
        message = _clean(job.get("message") or job.get("error"))
        if not job_type:
            lowered = message.lower()
            if "index" in lowered or "indexed" in lowered:
                job_type = "index"
            elif "zarr" in lowered or "convert" in lowered or "conversion" in lowered:
                job_type = "conversion"
            elif "rebuild" in lowered:
                job_type = "rebuild"

        return {
            "schema_version": "source_intake.row_last_action.v1",
            "type": job_type or None,
            "state": _clean_lower(job.get("state") or job.get("status")) or None,
            "message": message or None,
            "progress": job.get("progress"),
            "updated_at": job.get("updated_at") or job.get("completed_at") or job.get("created_at"),
            "job_id": job.get("job_id") or job.get("id"),
        }

    def _staged_rebuild_resolution(
        self,
        row: Dict[str, Any],
        staged: Optional[Dict[str, Any]],
        lifecycle: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        # Backend-owned staged rebuild resolution contract. A row can have
        # a current viewer-ready managed output and a newer staged rebuild
        # waiting for promotion. The frontend should render this object
        # rather than infer staged rebuild semantics from labels or job JSON.
        if not isinstance(staged, dict) or not staged:
            return None
        if _clean_lower(lifecycle.get("state")) != "staged_ready":
            return None
        if not bool(staged.get("promotion_required")):
            return None

        candidate_id = _candidate_id(row)
        dimension = _dimension(row)
        mode = dimension if dimension in {"2d", "3d"} else _clean_lower(staged.get("mode")) or None
        job_id = _clean(staged.get("job_id") or staged.get("id"))
        managed_output = _as_dict(row.get("managed_output"))
        managed_state = _clean_lower(row.get("managed_state"))
        current_viewer_ready = managed_state == "viewer_ready" or bool(managed_output.get("viewer_ready"))

        current_output = {
            "state": "viewer_ready" if current_viewer_ready else managed_state or "not_managed",
            "viewer_ready": bool(current_viewer_ready),
            "representation_id": managed_output.get("representation_id") or managed_output.get("msi_representation_id"),
            "dataset_id": managed_output.get("dataset_id"),
            "storage_uri": managed_output.get("storage_uri"),
            "zarr_url": managed_output.get("zarr_url"),
            "display_name": managed_output.get("display_name") or row.get("filename") or row.get("file_name") or row.get("display_name"),
            "is_preferred": managed_output.get("is_preferred"),
        }

        staged_artifact = {
            "state": "ready",
            "job_id": job_id or None,
            "artifact_id": staged.get("artifact_id"),
            "status": staged.get("status"),
            "progress": staged.get("progress"),
            "output_path": staged.get("output_path"),
            "completed_at": staged.get("completed_at"),
            "updated_at": staged.get("updated_at"),
            "message": staged.get("message"),
        }

        base_payload = {"mode": mode, "job_id": job_id or None}
        available_resolutions = []

        if candidate_id and current_viewer_ready:
            available_resolutions.append({
                "action": "overwrite_current",
                "label": "Overwrite current managed output",
                "method": "POST",
                "url": f"/api/source-intake/candidates/{candidate_id}/rebuild/overwrite-existing",
                "description": "Promote the staged rebuild and replace the current managed output.",
                "requires_display_name": False,
                "payload": dict(base_payload),
            })

        if candidate_id:
            save_payload = dict(base_payload)
            save_payload["display_name"] = ""
            available_resolutions.append({
                "action": "save_as_new",
                "label": "Save staged rebuild as new managed output",
                "method": "POST",
                "url": f"/api/source-intake/candidates/{candidate_id}/rebuild/save-as-new",
                "description": "Promote the staged rebuild as a separate managed output.",
                "requires_display_name": True,
                "payload": save_payload,
            })
            available_resolutions.append({
                "action": "discard_staged",
                "label": "Discard staged rebuild",
                "method": "POST",
                "url": f"/api/source-intake/candidates/{candidate_id}/rebuild/discard",
                "description": "Delete the staged rebuild artifact and keep the current managed output unchanged.",
                "requires_display_name": False,
                "payload": dict(base_payload),
            })

        return {
            "schema_version": "source_intake.staged_rebuild_resolution.v1",
            "state": "ready",
            "label": "Staged Rebuild Ready",
            "detail": "A newer staged rebuild exists. The current managed output remains viewer-ready until the staged rebuild is resolved.",
            "promotion_required": True,
            "mode": mode,
            "candidate_id": candidate_id or None,
            "job_id": job_id or None,
            "current_managed_output": current_output,
            "staged_artifact": staged_artifact,
            "available_resolutions": available_resolutions,
            "next_action": {
                "label": "Resolve staged rebuild",
                "required": True,
                "action_group": "staged_rebuild_resolution",
                "reason": "Choose overwrite, save-as-new, or discard before starting another rebuild.",
            },
        }

    def _progress(
        self,
        row: Dict[str, Any],
        lifecycle: Dict[str, Any],
        staged: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Return canonical progress display for the row.

        Canonical lifecycle drives progress label/detail. Job messages are used
        only while an active job is running, or for non-managed rows where no
        higher-priority lifecycle state exists.  This prevents stale index-build
        messages from remaining as the primary row detail after Zarr/managed
        output is already viewer-ready.
        """
        job = _as_dict(row.get("job"))
        state = _clean_lower(lifecycle.get("state"))
        lifecycle_label = lifecycle.get("label")
        lifecycle_reason = lifecycle.get("reason")
        lifecycle_active = bool(lifecycle.get("active"))
        lifecycle_failed = bool(lifecycle.get("failed"))
        lifecycle_terminal = bool(lifecycle.get("terminal"))

        index_terminal = _completed_index_preview_state(row)
        if index_terminal and state == "not_converted":
            return {
                "schema_version": "source_intake.row_progress.v1",
                "visible": True,
                "label": "Indexed Preview Available",
                "percent": 100.0,
                "active": False,
                "failed": False,
                "terminal": True,
                "detail": index_terminal.get("message") or "Indexed preview is available.",
                "state": "not_converted",
            }

        if isinstance(staged, dict) and state == "staged_ready":
            source = staged
        elif lifecycle_active:
            source = job
        else:
            source = {}

        raw_percent = source.get("progress") if isinstance(source, dict) else None
        percent = _coerce_percent(raw_percent)
        if percent is None:
            if state in {"viewer_ready", "promotion_complete", "staged_ready", "discarded"}:
                percent = 100.0
            elif state == "failed":
                percent = 100.0
            elif state == "not_converted":
                percent = 0.0
            else:
                percent = None

        if lifecycle_active and isinstance(source, dict):
            detail = source.get("message") or lifecycle_reason
        else:
            detail = lifecycle_reason

        return {
            "schema_version": "source_intake.row_progress.v1",
            "visible": True,
            "label": lifecycle_label,
            "percent": percent,
            "active": lifecycle_active,
            "failed": lifecycle_failed,
            "terminal": lifecycle_terminal,
            "detail": _clean(detail),
            "state": state,
        }

    def _presentation(self, row: Dict[str, Any], lifecycle: Dict[str, Any]) -> Dict[str, Any]:
        managed_state = _clean_lower(row.get("managed_state"))
        geometry = _as_dict(row.get("geometry_qaqc"))
        geometry_status = _clean_lower(geometry.get("status"))
        if geometry_status == "passed":
            geometry_label = "Geometry Passed"
        elif geometry_status == "review_required":
            geometry_label = "Geometry Review"
        elif geometry_status == "failed":
            geometry_label = "Geometry Failed"
        elif geometry_status:
            geometry_label = geometry_status.replace("_", " ").title()
        else:
            geometry_label = "Geometry Not Run"

        document_count = row.get("supporting_document_count")
        if document_count is None:
            document_count = row.get("document_count")
        try:
            doc_count_int = int(document_count or 0)
        except (TypeError, ValueError):
            doc_count_int = 0
        document_label = str(doc_count_int)
        document_subtitle = "Document" if doc_count_int == 1 else "Documents"

        return {
            "schema_version": "source_intake.row_presentation.v1",
            "status_label": lifecycle.get("label"),
            "status_reason": lifecycle.get("reason"),
            "managed_output_label": "Viewer Ready" if managed_state == "viewer_ready" else "Not Managed",
            "geometry_qaqc_label": geometry_label,
            "document_label": document_label,
            "document_subtitle": document_subtitle,
            "dimension_label": {"2d": "2D", "3d": "3D"}.get(_dimension(row), "Review"),
        }

    def _actions(self, row: Dict[str, Any], lifecycle: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        actions = row.get("actions") if isinstance(row.get("actions"), dict) else {}
        result: Dict[str, Dict[str, Any]] = {}
        for name, value in actions.items():
            result[name] = dict(value) if isinstance(value, dict) else {"enabled": False, "url": None, "reason": "Invalid action contract."}

        candidate_id = _candidate_id(row)
        source_ok = row.get("source_path_exists") is True
        dimension = _dimension(row)
        managed_state = _clean_lower(row.get("managed_state"))
        managed_output = _as_dict(row.get("managed_output"))
        has_managed_output = managed_state == "viewer_ready" or bool(
            managed_output.get("representation_id")
            or managed_output.get("msi_representation_id")
            or managed_output.get("volume_id")
            or managed_output.get("storage_uri")
            or managed_output.get("zarr_url")
        )
        # Rebuild workflow is retired in this build. Do not expose rebuild or
        # staged-rebuild resolution actions from the backend contract. Historical
        # staged rebuild jobs remain available for audit only.
        result.pop("rebuild", None)
        result.pop("resolve_staged_rebuild", None)
        result.pop("overwrite_staged_rebuild", None)
        result.pop("save_staged_rebuild_as_new", None)
        result.pop("discard_staged_rebuild", None)

        index_terminal = _completed_index_preview_state(row)
        if index_terminal:
            candidate_id = _source_intake_candidate_id(row)
            actions["build_index"] = {
                "enabled": False,
                "url": None,
                "reason": "Indexed preview already exists for this Source Intake candidate.",
            }
            actions["view_indexed_preview"] = {
                "enabled": bool(candidate_id),
                "url": (
                    f"/api/source-intake/candidates/{candidate_id}/indexed-preview-viewer-source"
                    if candidate_id
                    else None
                ),
                "reason": None if candidate_id else "Missing Source Intake candidate id.",
                "dataset_id": index_terminal.get("dataset_id"),
            }

        for required in ("build_2d_line", "build_3d_volume", "build_index", "geometry_qaqc"):
            result.setdefault(required, {"enabled": False, "url": None, "reason": "Action is not available for this row."})
        return result

    def _latest_staged_rebuilds_by_candidate(self) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        if not JOBS_DIR.exists():
            return result
        for path in JOBS_DIR.glob("*.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(job, dict):
                continue
            compact = self._compact_staged_rebuild_job(job)
            if not compact:
                continue
            candidate_ids = self._candidate_ids_from_job(job, compact)
            for candidate_id in candidate_ids:
                previous = result.get(candidate_id)
                if not previous or _job_timestamp(compact) >= _job_timestamp(previous):
                    result[candidate_id] = compact
        return result

    def _compact_staged_rebuild_job(self, job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        staged = job.get("staged_rebuild") if isinstance(job.get("staged_rebuild"), dict) else {}
        progress_stage = _clean_lower(job.get("progress_stage"))
        is_staged = bool(staged) or bool(job.get("promotion_required")) or "staged_rebuild" in progress_stage
        if not is_staged:
            return None
        status = _clean_lower(job.get("status") or job.get("state"))
        return {
            "schema_version": "source_intake.staged_rebuild_result.v1",
            "job_id": job.get("job_id") or job.get("id"),
            "status": status,
            "progress": job.get("progress"),
            "message": job.get("message") or job.get("error"),
            "progress_stage": job.get("progress_stage"),
            "promotion_required": bool(job.get("promotion_required") or staged.get("promotion_required")),
            "promotion_options": job.get("promotion_options") or staged.get("promotion_options") or [],
            "output_path": job.get("output_path") or staged.get("output_path"),
            "updated_at": job.get("updated_at") or job.get("completed_at") or job.get("created_at"),
            "completed_at": job.get("completed_at"),
            "created_at": job.get("created_at"),
            "source_candidate_id": staged.get("source_candidate_id") or job.get("source_candidate_id"),
            "candidate_id": job.get("candidate_id"),
        }

    def _candidate_ids_from_job(self, job: Dict[str, Any], compact: Dict[str, Any]) -> List[str]:
        staged = job.get("staged_rebuild") if isinstance(job.get("staged_rebuild"), dict) else {}
        raw_values = [
            compact.get("source_candidate_id"),
            compact.get("candidate_id"),
            staged.get("source_candidate_id"),
            staged.get("candidate_id"),
            job.get("source_candidate_id"),
            job.get("candidate_id"),
            job.get("source_segy_file_id"),
            job.get("segy_file_id"),
        ]
        seen = set()
        result = []
        for value in raw_values:
            clean = _clean(value)
            if clean and clean not in seen:
                seen.add(clean)
                result.append(clean)
        return result

    def _assert_row_contract(self, row: Dict[str, Any]) -> None:
        lifecycle = _as_dict(row.get("lifecycle"))
        state = _clean_lower(lifecycle.get("state"))
        if state not in _CANONICAL_LIFECYCLE_STATES:
            raise ValueError(f"Invalid Source Intake row lifecycle state: {state!r}")
        progress = _as_dict(row.get("progress"))
        presentation = _as_dict(row.get("presentation"))
        actions = row.get("actions") if isinstance(row.get("actions"), dict) else {}
        if not progress or not presentation or not actions:
            raise ValueError("Source Intake row contract missing progress, presentation, or actions.")
        if bool(row.get("promotion_required")) and state == "failed":
            raise ValueError("Invalid Source Intake row contract: promotion_required with failed lifecycle.")
