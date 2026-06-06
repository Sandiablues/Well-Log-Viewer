from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.services.repository_registry_service import get_repository
from app.services.source_repository_mode_service import repository_matches_mode
from app.services.source_intake_repository_summary_service import decorate_repository
from app.services.source_intake_stage_workbench_service import SourceIntakeStageWorkbenchService
from app.services.source_intake_workbench_v2_service import SourceIntakeWorkbenchV2Service

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
STATE_PATH = DATA_DIR / "source_intake_session_state.json"
SCHEMA_VERSION = "source_intake.session.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_mode(value: Any) -> str:
    clean = _clean(value).lower()
    if clean not in {"2d", "3d"}:
        raise ValueError("Source Intake session mode must be '2d' or '3d'.")
    return clean


def _empty_workbench(mode: str) -> Dict[str, Any]:
    return {
        "schema_version": "source_intake.workbench.v2",
        "mode": mode,
        "repository_id": None,
        "scope": f"{mode}:__none__",
        "state": "empty",
        "operation": "session_empty",
        "rows": [],
        "row_count": 0,
        "summary": {
            "total": 0,
            "ready": 0,
            "review_required": 0,
            "building": 0,
            "complete": 0,
            "managed": 0,
            "failed": 0,
            "blocked": 0,
            "two_d": 0,
            "three_d": 0,
        },
        "monitoring": {
            "schema_version": "source_intake.monitoring.v1",
            "has_active_jobs": False,
            "active_job_count": 0,
            "active_candidate_ids": [],
            "poll_interval_ms": 0,
            "strategy": "poll_workbench_while_active",
            "active_rows": [],
        },
        "actions": {},
        "toolbar": {
            "selected_count": 0,
            "available_actions": [],
            "selection_model": "frontend_local",
        },
        "active_candidate_ids": [],
        "generated_at": _utc_now(),
    }


class SourceIntakeSessionService:
    """Backend-owned Source Intake active session contract.

    Persists the active Source Intake repository per mode so the Sources page
    can restore Workbench V2 after viewer navigation. The service stores only
    the active repository pointer; Workbench V2 remains the source of row truth.
    """

    def __init__(
        self,
        workbench_service: Optional[SourceIntakeWorkbenchV2Service] = None,
        stage_service: Optional[SourceIntakeStageWorkbenchService] = None,
    ) -> None:
        self.workbench_service = workbench_service or SourceIntakeWorkbenchV2Service()
        self.stage_service = stage_service or SourceIntakeStageWorkbenchService(self.workbench_service)

    def stage_repository_workbench(self, *, repository_id: str, mode: str) -> Dict[str, Any]:
        clean_mode = _clean_mode(mode)
        clean_repo = self._require_repository(repository_id)
        result = self.stage_service.stage_repository_workbench(
            repository_id=clean_repo,
            mode=clean_mode,
        )
        self._set_active_repository(clean_mode, clean_repo)
        result = dict(result)
        result["session"] = self.get_session(mode=clean_mode)
        return result

    def get_session(self, *, mode: str) -> Dict[str, Any]:
        clean_mode = _clean_mode(mode)
        active_repo = self._get_active_repository(clean_mode)
        if not active_repo:
            return self._payload(clean_mode, None, None, _empty_workbench(clean_mode), state="empty")

        repo = get_repository(active_repo)
        if not repo or not repository_matches_mode(repo, clean_mode):
            self._clear_active_repository(clean_mode)
            return self._payload(clean_mode, None, None, _empty_workbench(clean_mode), state="empty")

        repository = decorate_repository(repo, mode=clean_mode)
        workbench = self.workbench_service.get_workbench(mode=clean_mode, repository_id=active_repo)
        self._validate_workbench_scope(workbench, clean_mode, active_repo)
        return self._payload(clean_mode, active_repo, repository, workbench, state="active")

    def _payload(
        self,
        mode: str,
        active_repository_id: Optional[str],
        repository: Optional[Dict[str, Any]],
        workbench: Dict[str, Any],
        *,
        state: str,
    ) -> Dict[str, Any]:
        rows = workbench.get("rows") if isinstance(workbench.get("rows"), list) else []
        if int(workbench.get("row_count") or 0) != len(rows):
            raise ValueError("Source Intake session invariant failed: workbench.row_count must equal len(rows).")
        return {
            "schema_version": SCHEMA_VERSION,
            "mode": mode,
            "state": state,
            "active_repository_id": active_repository_id,
            "repository_id": active_repository_id,
            "repository": repository,
            "workbench": workbench,
            "monitoring": workbench.get("monitoring"),
            "state_path": str(STATE_PATH),
            "generated_at": _utc_now(),
        }

    def _validate_workbench_scope(self, workbench: Dict[str, Any], mode: str, repository_id: str) -> None:
        if workbench.get("schema_version") != "source_intake.workbench.v2":
            raise ValueError("Source Intake session invariant failed: unexpected Workbench V2 schema.")
        if workbench.get("mode") != mode:
            raise ValueError("Source Intake session invariant failed: workbench mode mismatch.")
        if workbench.get("repository_id") != repository_id:
            raise ValueError("Source Intake session invariant failed: workbench repository mismatch.")
        rows = workbench.get("rows") if isinstance(workbench.get("rows"), list) else []
        if int(workbench.get("row_count") or 0) != len(rows):
            raise ValueError("Source Intake session invariant failed: workbench row_count mismatch.")
        summary = workbench.get("summary") if isinstance(workbench.get("summary"), dict) else {}
        if int(summary.get("total") if summary.get("total") is not None else len(rows)) != len(rows):
            raise ValueError("Source Intake session invariant failed: workbench summary.total mismatch.")

    def _require_repository(self, repository_id: str) -> str:
        clean = _clean(repository_id)
        if not clean:
            raise ValueError("repository_id is required")
        repo = get_repository(clean)
        if not repo:
            raise FileNotFoundError(f"Repository not found: {clean}")
        return clean

    def _state(self) -> Dict[str, Any]:
        if not STATE_PATH.exists():
            return {"schema_version": SCHEMA_VERSION, "modes": {}}
        try:
            payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"schema_version": SCHEMA_VERSION, "modes": {}}
        if not isinstance(payload, dict):
            return {"schema_version": SCHEMA_VERSION, "modes": {}}
        payload["schema_version"] = SCHEMA_VERSION
        if not isinstance(payload.get("modes"), dict):
            payload["modes"] = {}
        return payload

    def _save_state(self, payload: Dict[str, Any]) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(STATE_PATH.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(STATE_PATH)

    def _set_active_repository(self, mode: str, repository_id: str) -> None:
        state = self._state()
        modes = state.setdefault("modes", {})
        modes[mode] = {"mode": mode, "active_repository_id": repository_id, "updated_at": _utc_now()}
        self._save_state(state)

    def _clear_active_repository(self, mode: str) -> None:
        state = self._state()
        modes = state.setdefault("modes", {})
        modes.pop(mode, None)
        self._save_state(state)

    def _get_active_repository(self, mode: str) -> Optional[str]:
        state = self._state()
        modes = state.get("modes") if isinstance(state.get("modes"), dict) else {}
        entry = modes.get(mode) if isinstance(modes, dict) else None
        if not isinstance(entry, dict):
            return None
        repo_id = _clean(entry.get("active_repository_id"))
        return repo_id or None
