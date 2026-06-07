from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter

from app.services.source_intake_index_job_service import list_source_intake_index_jobs


router = APIRouter(prefix="/api/source-intake", tags=["source-intake-jobs"])


def _read_jobs() -> List[Dict[str, Any]]:
    jobs_dir = Path(__file__).resolve().parents[2] / "data" / "jobs"
    if not jobs_dir.exists():
        return []
    records: List[Dict[str, Any]] = []
    for path in sorted(jobs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                value.setdefault("job_file", path.name)
                records.append(value)
        except Exception:
            continue
    return records


@router.get("/jobs")
def list_source_intake_jobs() -> Dict[str, Any]:
    return {"jobs": [*_read_jobs(), *list_source_intake_index_jobs()]}
