from __future__ import annotations

# MANUAL_UPLOAD_STAGING_2_METADATA

import json
from typing import Any, Dict, Iterable, List, Optional


_MANUAL_REPOSITORY_TYPE = "manual_upload_package"
_SOURCE_INTAKE_GENERIC_USE = {"", "source_intake", "manual_upload", "manual_upload_package"}
_MODE_TO_INTENDED_USE = {
    "2d": "2d_segy_intake",
    "3d": "3d_segy_intake",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_lower(value: Any) -> str:
    return _clean(value).lower()


def _parse_notes(notes: Any) -> Dict[str, Any]:
    if isinstance(notes, dict):
        return dict(notes)
    if not isinstance(notes, str) or not notes.strip():
        return {}
    try:
        parsed = json.loads(notes)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def manual_upload_workflow_mode(repo: Dict[str, Any]) -> str:
    """Return the declared manual-upload workflow mode, if available."""
    if not isinstance(repo, dict):
        return ""
    notes = _parse_notes(repo.get("notes"))
    for value in (repo.get("workflow_mode"), notes.get("workflow_mode"), repo.get("mode"), notes.get("mode")):
        mode = _clean_lower(value)
        if mode in {"2d", "3d"}:
            return mode
    return ""


def is_manual_upload_repository(repo: Dict[str, Any]) -> bool:
    if not isinstance(repo, dict):
        return False
    notes = _parse_notes(repo.get("notes"))
    return (
        _clean_lower(repo.get("repository_type")) == _MANUAL_REPOSITORY_TYPE
        or _clean_lower(repo.get("source_structure_type")) == _MANUAL_REPOSITORY_TYPE
        or _clean_lower(notes.get("source_structure_type")) == _MANUAL_REPOSITORY_TYPE
        or _clean_lower(notes.get("created_by")) == "manual_upload_staging_1"
    )


def decorate_manual_upload_repository(repo: Dict[str, Any]) -> Dict[str, Any]:
    """Make manual upload repositories visible to Source Intake mode filtering.

    Manual upload repositories were created with their mode stored in notes, not
    in the top-level repository fields used by Source Intake filters. This
    decorator promotes backend-owned metadata into the route/service contract
    without changing frontend behavior or starting conversion.
    """
    if not isinstance(repo, dict):
        return repo
    if not is_manual_upload_repository(repo):
        return repo

    notes = _parse_notes(repo.get("notes"))
    mode = manual_upload_workflow_mode(repo)
    decorated = dict(repo)
    decorated.setdefault("source_structure_type", _MANUAL_REPOSITORY_TYPE)
    decorated["source_structure_type"] = decorated.get("source_structure_type") or _MANUAL_REPOSITORY_TYPE
    if mode:
        decorated["workflow_mode"] = mode
        intended_use = _clean_lower(decorated.get("intended_use") or notes.get("intended_use"))
        if intended_use in _SOURCE_INTAKE_GENERIC_USE:
            decorated["intended_use"] = _MODE_TO_INTENDED_USE[mode]
        else:
            decorated.setdefault("intended_use", intended_use)
    decorated["manual_upload_repository"] = True
    decorated["manual_upload_metadata_source"] = "repository_notes"
    return decorated


def decorate_manual_upload_repositories(repositories: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [decorate_manual_upload_repository(repo) for repo in list(repositories or [])]
