from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from app.services.source_intake_workbench_service import SourceIntakeWorkbenchService
from app.services.source_intake_row_contract_service import SourceIntakeRowContractService
from app.services.repository_registry_service import get_repository
from app.services.package_registry_service import list_segy_files
from app.services.source_repository_mode_service import repository_matches_mode
from app.services.manual_upload_source_intake_metadata_service import decorate_manual_upload_repository


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
STATE_PATH = DATA_DIR / "source_intake_workbench_v2_state.json"
SCHEMA_VERSION = "source_intake.workbench.v2"


_SUMMARY_KEYS = [
    "total",
    "ready",
    "review_required",
    "building",
    "complete",
    "managed",
    "failed",
    "blocked",
    "two_d",
    "three_d",
]


_2D_KINDS = {"2d_line", "2d"}
_2D_ROLES = {"line_candidate", "line"}
_3D_KINDS = {"3d_volume", "3d"}
_3D_ROLES = {"volume_candidate", "volume"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_lower(value: Any) -> str:
    return _clean(value).lower()


def _scope_key(mode: Optional[str], repository_id: Optional[str]) -> str:
    clean_mode = _clean_lower(mode) or "__any__"
    clean_repo = _clean(repository_id) or "__global__"
    return f"{clean_mode}:{clean_repo}"


def _row_candidate_id(row: Dict[str, Any]) -> str:
    for key in ("candidate_id", "source_segy_file_id", "segy_file_id", "id"):
        value = _clean(row.get(key))
        if value:
            return value
    return ""




# INDEX_RECOVERY_2_CANONICAL_CLASSIFICATION_HELPERS
# Workbench V2 must not invent candidate dimensionality from stale row state.
# Package registry / Source Intake candidate records are the authoritative
# classification source for candidate_kind / candidate_role.
def _canonical_records_by_candidate_id() -> Dict[str, Dict[str, Any]]:
    records: Dict[str, Dict[str, Any]] = {}
    try:
        source_records = list_segy_files()
    except Exception:
        return records

    for record in source_records or []:
        if not isinstance(record, dict):
            continue
        ids = {
            _clean(record.get("candidate_id")),
            _clean(record.get("source_segy_file_id")),
            _clean(record.get("segy_file_id")),
        } - {""}
        for candidate_id in ids:
            records[candidate_id] = record
    return records


def _merge_canonical_candidate_record(
    row: Dict[str, Any],
    canonical_records: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    candidate_id = _row_candidate_id(row)
    record = canonical_records.get(candidate_id)
    if not record:
        return row

    merged = dict(row)

    for key in (
        "candidate_kind",
        "candidate_role",
        "classification_source",
        "classification_confidence",
        "classification_reasons",
        "source_path_exists",
        "repository_id",
        "package_id",
        "package_name",
        "line_id",
        "relative_path",
        "source_path",
        "absolute_path",
    ):
        if key in record:
            merged[key] = record.get(key)

    # Preserve display name from the row unless missing, but keep source ids and
    # classification from the authoritative candidate record.
    for key in ("filename", "file_name", "display_name"):
        if not _clean(merged.get(key)) and _clean(record.get(key)):
            merged[key] = record.get(key)

    source = merged.get("source") if isinstance(merged.get("source"), dict) else {}
    source = dict(source)
    for key in (
        "candidate_id",
        "source_segy_file_id",
        "segy_file_id",
        "candidate_kind",
        "candidate_role",
        "classification_source",
        "classification_confidence",
        "classification_reasons",
        "source_path_exists",
        "repository_id",
        "package_id",
        "package_name",
        "line_id",
        "relative_path",
        "source_path",
        "absolute_path",
        "filename",
        "file_name",
        "display_name",
    ):
        if key in record:
            source[key] = record.get(key)
    merged["source"] = source
    merged["classification_authority"] = "package_registry"
    return merged


def _row_matches_requested_mode(row: Dict[str, Any], mode: str) -> bool:
    kind = _clean_lower(row.get("candidate_kind"))
    role = _clean_lower(row.get("candidate_role"))

    if mode == "3d":
        # Strict by design: rows rejected by Source Intake classification as 2D
        # or excluded must not surface as active 3D Build Index / Build Volume
        # candidates.
        return kind == "3d_volume" and role == "volume_candidate"

    if mode == "2d":
        return kind in _2D_KINDS or role in _2D_ROLES

    return False


def _empty_summary() -> Dict[str, int]:
    return {key: 0 for key in _SUMMARY_KEYS}


def _summary_from_rows(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    result = _empty_summary()
    result["total"] = len(rows)
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = row.get("status") if isinstance(row.get("status"), dict) else {}
        state = _clean_lower(status.get("state"))
        if state in result:
            result[state] += 1

        kind = _clean_lower(row.get("candidate_kind"))
        role = _clean_lower(row.get("candidate_role"))
        if kind in _2D_KINDS or role in _2D_ROLES:
            result["two_d"] += 1
        if kind in _3D_KINDS or role in _3D_ROLES:
            result["three_d"] += 1
    return result


_ACTIVE_MONITORING_STATES = {
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
    "rebuilding",
}


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _row_monitoring_state(row: Dict[str, Any]) -> Dict[str, Any]:
    candidate_id = _row_candidate_id(row)
    progress = _dict(row.get("progress"))
    lifecycle = _dict(row.get("lifecycle"))
    job = _dict(row.get("job"))

    progress_state = _clean_lower(progress.get("state"))
    lifecycle_state = _clean_lower(lifecycle.get("state"))
    job_state = _clean_lower(job.get("state") or job.get("status"))

    active = bool(
        progress.get("active")
        or lifecycle.get("active")
        or progress_state in _ACTIVE_MONITORING_STATES
        or lifecycle_state in _ACTIVE_MONITORING_STATES
        or job_state in _ACTIVE_MONITORING_STATES
    )

    return {
        "candidate_id": candidate_id,
        "job_id": job.get("job_id"),
        "job_state": job_state or None,
        "progress_state": progress_state or None,
        "lifecycle_state": lifecycle_state or None,
        "progress_percent": progress.get("percent"),
        "message": progress.get("detail") or job.get("message"),
        "active": active,
    }


def _monitoring_from_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    active_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        state = _row_monitoring_state(row)
        if state.get("active"):
            active_rows.append(state)

    active_candidate_ids = [
        str(row.get("candidate_id") or "").strip()
        for row in active_rows
        if str(row.get("candidate_id") or "").strip()
    ]

    return {
        "schema_version": "source_intake.monitoring.v1",
        "has_active_jobs": bool(active_rows),
        "active_job_count": len(active_rows),
        "active_candidate_ids": active_candidate_ids,
        "poll_interval_ms": 1500 if active_rows else 0,
        "strategy": "poll_workbench_while_active",
        "active_rows": active_rows,
    }


class SourceIntakeWorkbenchV2Service:
    """Backend-owned Source Intake Workbench V2 working-set service.

    V2 stores the active working set as candidate IDs scoped by mode and
    repository_id. It does not use V1 hidden-row state, cleared_from_workbench,
    flushed workbench state, or restore-cleared behavior.

    Clear is non-destructive: it only removes IDs from the V2 active set.
    """

    def __init__(self, row_builder: SourceIntakeWorkbenchService | None = None) -> None:
        self.row_builder = row_builder or SourceIntakeWorkbenchService()
        self.row_contract_service = SourceIntakeRowContractService()

    def get_workbench(self, *, mode: Optional[str], repository_id: Optional[str]) -> Dict[str, Any]:
        clean_mode = self._require_mode(mode)
        clean_repo = self._require_repository(repository_id)
        self._validate_repository_mode(clean_repo, clean_mode)
        active_ids = self._active_ids(clean_mode, clean_repo)
        return self._payload(clean_mode, clean_repo, active_ids, operation="get")

    def use_repository(self, *, mode: Optional[str], repository_id: Optional[str]) -> Dict[str, Any]:
        clean_mode = self._require_mode(mode)
        clean_repo = self._require_repository(repository_id)
        self._validate_repository_mode(clean_repo, clean_mode)

        source_payload = self.row_builder.build_repository_workbench(clean_repo, mode=clean_mode)
        all_ids = [_row_candidate_id(row) for row in source_payload.get("rows", []) if isinstance(row, dict)]
        active_ids = [candidate_id for candidate_id in all_ids if candidate_id]
        self._set_active_ids(clean_mode, clean_repo, active_ids)
        return self._payload(clean_mode, clean_repo, active_ids, operation="use_repository")

    def clear_selected(
        self,
        *,
        mode: Optional[str],
        repository_id: Optional[str],
        candidate_ids: Iterable[str],
    ) -> Dict[str, Any]:
        clean_mode = self._require_mode(mode)
        clean_repo = self._require_repository(repository_id)
        self._validate_repository_mode(clean_repo, clean_mode)

        remove_ids = {_clean(candidate_id) for candidate_id in candidate_ids if _clean(candidate_id)}
        active_ids = self._active_ids(clean_mode, clean_repo)
        remaining_ids = [candidate_id for candidate_id in active_ids if candidate_id not in remove_ids]
        self._set_active_ids(clean_mode, clean_repo, remaining_ids)
        payload = self._payload(clean_mode, clean_repo, remaining_ids, operation="clear_selected")
        payload["cleared_candidate_ids"] = sorted(remove_ids.intersection(set(active_ids)))
        payload["cleared_count"] = len(payload["cleared_candidate_ids"])
        return payload

    def _payload(self, mode: str, repository_id: str, active_ids: List[str], *, operation: str) -> Dict[str, Any]:
        source_payload = self.row_builder.build_repository_workbench(repository_id, mode=mode)
        active_set = set(active_ids)
        canonical_records = _canonical_records_by_candidate_id()
        source_rows = [
            _merge_canonical_candidate_record(row, canonical_records)
            for row in source_payload.get("rows", [])
            if isinstance(row, dict)
        ]
        rows = [
            row
            for row in source_rows
            if _row_candidate_id(row) in active_set
            and _row_matches_requested_mode(row, mode)
        ]
        filtered_ids = {_row_candidate_id(row) for row in rows}
        active_ids = [candidate_id for candidate_id in active_ids if candidate_id in filtered_ids]
        rows.sort(key=lambda row: active_ids.index(_row_candidate_id(row)) if _row_candidate_id(row) in active_ids else len(active_ids))
        rows = self.row_contract_service.enrich_rows(rows)
        summary = _summary_from_rows(rows)
        monitoring = _monitoring_from_rows(rows)
        row_count = len(rows)

        if row_count != len(rows) or summary.get("total") != len(rows):
            raise ValueError("Workbench V2 invariant failed: row_count and summary.total must equal len(rows).")

        payload = {
            "schema_version": SCHEMA_VERSION,
            "mode": mode,
            "repository_id": repository_id,
            "scope": _scope_key(mode, repository_id),
            "state": "active",
            "operation": operation,
            "rows": rows,
            "row_count": row_count,
            "summary": summary,
            "monitoring": monitoring,
            "actions": {
                "use_repository": {
                    "enabled": True,
                    "method": "POST",
                    "url": "/api/source-intake/workbench/use-repository",
                },
                "clear_selected": {
                    "enabled": True,
                    "method": "POST",
                    "url": "/api/source-intake/workbench/clear-selected",
                },
                "refresh": {
                    "enabled": True,
                    "method": "GET",
                    "url": f"/api/source-intake/workbench?mode={mode}&repository_id={repository_id}",
                },
            },
            "toolbar": {
                "selected_count": 0,
                "available_actions": ["clear_selected"],
                "selection_model": "frontend_local",
            },
            "columns": source_payload.get("columns") or [],
            "repository": source_payload.get("repository"),
            "active_candidate_ids": list(active_ids),
            "state_path": str(STATE_PATH),
            "generated_at": _utc_now(),
        }
        return payload

    def _active_ids(self, mode: str, repository_id: str) -> List[str]:
        state = self._load_state()
        scopes = state.get("scopes") if isinstance(state.get("scopes"), dict) else {}
        scope = scopes.get(_scope_key(mode, repository_id)) if isinstance(scopes, dict) else None
        if not isinstance(scope, dict):
            return []
        raw_ids = scope.get("active_candidate_ids")
        if not isinstance(raw_ids, list):
            return []
        seen: Set[str] = set()
        result: List[str] = []
        for value in raw_ids:
            candidate_id = _clean(value)
            if candidate_id and candidate_id not in seen:
                seen.add(candidate_id)
                result.append(candidate_id)
        return result

    def _set_active_ids(self, mode: str, repository_id: str, candidate_ids: List[str]) -> None:
        clean_ids: List[str] = []
        seen: Set[str] = set()
        for value in candidate_ids:
            candidate_id = _clean(value)
            if candidate_id and candidate_id not in seen:
                seen.add(candidate_id)
                clean_ids.append(candidate_id)

        state = self._load_state()
        scopes = state.setdefault("scopes", {})
        if not isinstance(scopes, dict):
            scopes = {}
            state["scopes"] = scopes
        scopes[_scope_key(mode, repository_id)] = {
            "mode": mode,
            "repository_id": repository_id,
            "active_candidate_ids": clean_ids,
            "updated_at": _utc_now(),
        }
        self._save_state(state)

    def _load_state(self) -> Dict[str, Any]:
        if not STATE_PATH.exists():
            return {"schema_version": SCHEMA_VERSION, "scopes": {}}
        try:
            payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"schema_version": SCHEMA_VERSION, "scopes": {}}
        if not isinstance(payload, dict):
            return {"schema_version": SCHEMA_VERSION, "scopes": {}}
        payload["schema_version"] = SCHEMA_VERSION
        payload.setdefault("scopes", {})
        return payload

    def _save_state(self, payload: Dict[str, Any]) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(STATE_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(STATE_PATH)

    def _require_mode(self, mode: Optional[str]) -> str:
        clean_mode = _clean_lower(mode)
        if clean_mode not in {"2d", "3d"}:
            raise ValueError("Workbench V2 mode must be '2d' or '3d'.")
        return clean_mode

    def _require_repository(self, repository_id: Optional[str]) -> str:
        clean_repo = _clean(repository_id)
        if not clean_repo:
            raise ValueError("Workbench V2 repository_id is required.")
        return clean_repo

    def _validate_repository_mode(self, repository_id: str, mode: str) -> None:
        repo = get_repository(repository_id)
        if not repo:
            raise FileNotFoundError(f"Repository not found: {repository_id}")
        # MANUAL_UPLOAD_STAGING_2: manual-upload repositories carry workflow mode
        # in backend notes; decorate before mode validation.
        repo = decorate_manual_upload_repository(repo)
        if not repository_matches_mode(repo, mode):
            raise ValueError(f"Repository {repository_id} does not match requested mode={mode}.")
