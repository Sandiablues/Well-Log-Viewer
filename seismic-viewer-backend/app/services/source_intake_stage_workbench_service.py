from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.repository_registry_service import get_repository
from app.services.source_repository_mode_service import repository_matches_mode
from app.services.source_intake_workbench_v2_service import SourceIntakeWorkbenchV2Service
from app.services.source_intake_repository_summary_service import build_repository_scan_summary, decorate_repository

SCHEMA_VERSION = "source_intake.stage_workbench.v1"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_mode(value: Any) -> str:
    clean = _clean(value).lower()
    if clean not in {"2d", "3d"}:
        raise ValueError("Stage Workbench mode must be '2d' or '3d'.")
    return clean


class SourceIntakeStageWorkbenchService:
    """Backend-owned Source Repository -> Workbench staging contract.

    Stage is one authoritative backend operation: validate repository/mode,
    compute canonical mode-aware summary, stage Workbench V2 active rows, and
    return both repository and workbench contracts together.
    """

    def __init__(self, workbench_service: Optional[SourceIntakeWorkbenchV2Service] = None) -> None:
        self.workbench_service = workbench_service or SourceIntakeWorkbenchV2Service()

    def stage_repository_workbench(self, *, repository_id: str, mode: str) -> Dict[str, Any]:
        clean_repo = _clean(repository_id)
        clean_mode = _clean_mode(mode)
        if not clean_repo:
            raise ValueError("repository_id is required")

        repo = get_repository(clean_repo)
        if not repo:
            raise FileNotFoundError(f"Repository not found: {clean_repo}")
        if not repository_matches_mode(repo, clean_mode):
            raise ValueError(f"Repository {clean_repo} does not match requested mode={clean_mode}.")

        scan_summary = build_repository_scan_summary(clean_repo, mode=clean_mode)
        repository = decorate_repository(repo, mode=clean_mode)
        workbench = self.workbench_service.use_repository(mode=clean_mode, repository_id=clean_repo)

        if workbench.get("schema_version") != "source_intake.workbench.v2":
            raise ValueError("Stage Workbench invariant failed: unexpected workbench schema_version.")
        if workbench.get("mode") != clean_mode or workbench.get("repository_id") != clean_repo:
            raise ValueError("Stage Workbench invariant failed: workbench payload scope does not match request.")
        rows = workbench.get("rows") if isinstance(workbench.get("rows"), list) else []
        if int(workbench.get("row_count") or 0) != len(rows):
            raise ValueError("Stage Workbench invariant failed: row_count must equal len(rows).")
        summary = workbench.get("summary") if isinstance(workbench.get("summary"), dict) else {}
        if int(summary.get("total") or len(rows)) != len(rows):
            raise ValueError("Stage Workbench invariant failed: summary.total must equal len(rows).")

        return {
            "schema_version": SCHEMA_VERSION,
            "mode": clean_mode,
            "repository_id": clean_repo,
            "repository": repository,
            "scan_summary": scan_summary,
            "workbench": workbench,
        }
