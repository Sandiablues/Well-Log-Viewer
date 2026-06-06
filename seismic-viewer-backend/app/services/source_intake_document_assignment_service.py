from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from app.services.document_registry_service import list_documents
from app.services.package_registry_service import list_packages, list_segy_files
from app.services.repository_registry_service import get_repository

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_ASSIGNMENT_PATH = _DATA_DIR / "source_intake_document_assignments.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _norm_mode(value: Any) -> str:
    raw = _clean(value).lower()
    if raw in {"2d", "2d_line", "2d_segy_intake"}:
        return "2d"
    if raw in {"3d", "3d_volume", "3d_segy_intake"}:
        return "3d"
    return ""


def _norm_path(value: Any) -> str:
    return _clean(value).replace("\\", "/").strip("/")


def _parent_dir(relative_path: Any) -> str:
    path = _norm_path(relative_path)
    if not path or "/" not in path:
        return ""
    return path.rsplit("/", 1)[0]


def _load_store() -> Dict[str, Any]:
    if not _ASSIGNMENT_PATH.exists():
        return {"schema_version": "source_intake.document_assignments.v2", "assignments": []}
    try:
        data = json.loads(_ASSIGNMENT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": "source_intake.document_assignments.v2", "assignments": []}
    if not isinstance(data, dict):
        return {"schema_version": "source_intake.document_assignments.v2", "assignments": []}
    data["schema_version"] = "source_intake.document_assignments.v2"
    data.setdefault("assignments", [])
    if not isinstance(data["assignments"], list):
        data["assignments"] = []
    return data


def _save_store(data: Dict[str, Any]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now()
    tmp = _ASSIGNMENT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(_ASSIGNMENT_PATH)


def _candidate_source(candidate_id: str) -> Optional[Dict[str, Any]]:
    clean_candidate_id = _clean(candidate_id)
    for item in list_segy_files():
        if clean_candidate_id in {
            _clean(item.get("segy_file_id")),
            _clean(item.get("source_segy_file_id")),
            _clean(item.get("candidate_id")),
        }:
            return item
    return None


def _candidate_key(item: Dict[str, Any], candidate_id: Any = None) -> str:
    return _clean(candidate_id) or _clean(item.get("segy_file_id")) or _clean(item.get("source_segy_file_id")) or _clean(item.get("candidate_id"))


def _package_by_id(package_id: str) -> Optional[Dict[str, Any]]:
    clean_package_id = _clean(package_id)
    if not clean_package_id:
        return None
    for package in list_packages():
        if _clean(package.get("package_id")) == clean_package_id:
            return package
    return None


def _candidate_mode(candidate: Dict[str, Any]) -> str:
    kind = _clean(candidate.get("candidate_kind") or candidate.get("candidate_role")).lower()
    if "3d" in kind or "volume" in kind:
        return "3d"
    if "2d" in kind or "line" in kind:
        return "2d"

    repo_id = _clean(candidate.get("repository_id"))
    if repo_id:
        repo = get_repository(repo_id)
        intended = _clean((repo or {}).get("intended_use")).lower()
        if "3d" in intended:
            return "3d"
        if "2d" in intended:
            return "2d"
    return ""


def _line_ids_for_package(repository_id: str, package_id: str) -> List[str]:
    out: List[str] = []
    for item in list_segy_files(repository_id=repository_id):
        if package_id and _clean(item.get("package_id")) != package_id:
            continue
        line_id = _clean(item.get("line_id"))
        if line_id and line_id not in out:
            out.append(line_id)
    return out


def _document_url(doc: Dict[str, Any], document_id: str, kind: str) -> Optional[str]:
    raw = doc.get(f"{kind}_url")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if not document_id:
        return None
    if kind == "view":
        return f"/api/documents/{document_id}/view"
    if kind == "download":
        return f"/api/documents/{document_id}/download"
    if kind == "reveal":
        return f"/api/documents/{document_id}/reveal"
    return None


def _document_is_candidate_option(doc: Dict[str, Any], candidate: Dict[str, Any], requested_mode: str) -> bool:
    if _clean(doc.get("repository_id")) != _clean(candidate.get("repository_id")):
        return False

    candidate_mode = _candidate_mode(candidate)
    if requested_mode and candidate_mode and requested_mode != candidate_mode:
        return False

    candidate_package_id = _clean(candidate.get("package_id"))
    candidate_line_id = _clean(candidate.get("line_id"))
    doc_package_id = _clean(doc.get("package_id"))
    doc_line_id = _clean(doc.get("line_id"))

    if doc_line_id and candidate_line_id and doc_line_id == candidate_line_id:
        return True

    if candidate_mode == "3d":
        # 3D source deliveries commonly keep the SEG-Y volume at repository root or in a
        # data folder while reports live in sibling REPORT_* folders. Package-id equality
        # is therefore too narrow for 3D. Keep the hard mode/repository boundary, but
        # allow all documents in the same 3D source repository to be review candidates.
        return True

    # The default safe boundary for 2D is package/survey local. This prevents documents
    # from another package in the same repository from appearing in a 2D line picker.
    if doc_package_id and candidate_package_id:
        return doc_package_id == candidate_package_id

    candidate_package = _package_by_id(candidate_package_id)
    candidate_package_path = _norm_path((candidate_package or {}).get("relative_path"))
    doc_rel = _norm_path(doc.get("relative_path"))
    if candidate_package_path and (doc_rel == candidate_package_path or doc_rel.startswith(candidate_package_path + "/")):
        return True

    # Do not show repository-wide/unscoped documents by default for 2D. They need
    # explicit repository-level review so they are not accidentally assigned widely.
    return False


def _assignment_applies_to_candidate(assignment: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
    if _clean(assignment.get("repository_id")) != _clean(candidate.get("repository_id")):
        return False
    scope_type = _clean(assignment.get("scope_type"))
    scope_id = _clean(assignment.get("scope_id"))
    if scope_type == "repository":
        return scope_id == _clean(candidate.get("repository_id"))
    if scope_type == "survey":
        return scope_id == _clean(candidate.get("package_id"))
    if scope_type == "line":
        return scope_id == _clean(candidate.get("line_id"))
    if scope_type == "candidate":
        return scope_id == _candidate_key(candidate)
    return False


def _effective_assignments(candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
    store = _load_store()
    assignments = [a for a in store.get("assignments", []) if isinstance(a, dict)]
    return [a for a in assignments if _assignment_applies_to_candidate(a, candidate)]


def _effective_assigned_document_ids(candidate: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for assignment in _effective_assignments(candidate):
        if _clean(assignment.get("status")) != "assigned":
            continue
        doc_id = _clean(assignment.get("document_id"))
        if doc_id and doc_id not in ids:
            ids.append(doc_id)
    return ids


def _document_public_row(doc: Dict[str, Any], *, candidate: Dict[str, Any], assignments: List[Dict[str, Any]]) -> Dict[str, Any]:
    doc_id = _clean(doc.get("document_id"))
    package_id = _clean(candidate.get("package_id"))
    line_id = _clean(candidate.get("line_id"))
    doc_package_id = _clean(doc.get("package_id"))
    doc_line_id = _clean(doc.get("line_id"))
    candidate_dir = _parent_dir(candidate.get("relative_path"))
    doc_rel = _norm_path(doc.get("relative_path"))
    doc_dir = _parent_dir(doc_rel)

    candidate_mode = _candidate_mode(candidate)
    suggested_scope = "survey"
    match_reason = "document belongs to the same survey/package as the selected SEG-Y candidate"
    match_confidence = "high" if package_id and doc_package_id == package_id else "medium"
    if candidate_mode == "3d":
        suggested_scope = "survey"
        if package_id and doc_package_id == package_id:
            match_reason = "document is in the same 3D package as the selected volume"
            match_confidence = "high"
        else:
            match_reason = "document is in the same 3D source repository as the selected volume"
            match_confidence = "medium"
    elif line_id and doc_line_id == line_id:
        suggested_scope = "line"
        match_reason = "document.line_id matches candidate.line_id"
        match_confidence = "high"
    elif candidate_dir and (doc_dir == candidate_dir or doc_rel.startswith(candidate_dir + "/")):
        suggested_scope = "line"
        match_reason = "document is in the same source folder as the SEG-Y candidate"
        match_confidence = "medium"

    all_doc_assignments = [a for a in assignments if _clean(a.get("document_id")) == doc_id]
    matching = [a for a in all_doc_assignments if _assignment_applies_to_candidate(a, candidate)]
    elsewhere = [a for a in all_doc_assignments if not _assignment_applies_to_candidate(a, candidate)]

    non_geo = any(_clean(a.get("status")) == "non_geophysical" for a in matching)
    assigned = any(_clean(a.get("status")) == "assigned" for a in matching)
    assigned_elsewhere = any(_clean(a.get("status")) == "assigned" for a in elsewhere)

    assignment_state = (
        "non_geophysical"
        if non_geo
        else "assigned_current"
        if assigned
        else "assigned_elsewhere"
        if assigned_elsewhere
        else "unassigned"
    )
    package = _package_by_id(doc_package_id)
    view_url = _document_url(doc, doc_id, "view")
    download_url = _document_url(doc, doc_id, "download")
    reveal_url = _document_url(doc, doc_id, "reveal")

    return {
        "document_id": doc.get("document_id"),
        "filename": doc.get("filename"),
        "relative_path": doc.get("relative_path"),
        "document_type": doc.get("document_type"),
        "document_role": doc.get("document_role") or doc.get("document_type"),
        "repository_id": doc.get("repository_id"),
        "package_id": doc.get("package_id"),
        "package_name": (package or {}).get("display_name") or (package or {}).get("package_key"),
        "line_id": doc.get("line_id"),
        "mime_type": doc.get("mime_type"),
        "view_url": view_url,
        "download_url": download_url,
        "reveal_url": reveal_url,
        "open_url": view_url,
        "suggested_scope": suggested_scope,
        "match_reason": match_reason,
        "match_confidence": match_confidence,
        "assigned": assigned,
        "non_geophysical": non_geo,
        "assigned_to_current_candidate": assigned,
        "assigned_elsewhere": assigned_elsewhere,
        "assignment_state": assignment_state,
        "assigned_scopes": [
            {
                "scope_type": a.get("scope_type"),
                "scope_id": a.get("scope_id"),
                "status": a.get("status"),
                "candidate_id": a.get("candidate_id"),
                "package_id": a.get("package_id"),
                "line_id": a.get("line_id"),
            }
            for a in matching
        ],
        "all_assigned_scopes": [
            {
                "scope_type": a.get("scope_type"),
                "scope_id": a.get("scope_id"),
                "status": a.get("status"),
                "candidate_id": a.get("candidate_id"),
                "package_id": a.get("package_id"),
                "line_id": a.get("line_id"),
            }
            for a in all_doc_assignments
        ],
    }


def _assignment_actions_for_candidate(candidate: Dict[str, Any], mode: str) -> List[Dict[str, Any]]:
    """
    Display-ready document assignment actions for the selected Source Intake
    candidate. The backend owns the 2D/3D scope semantics so the frontend does
    not have to translate volume workflows into line-oriented actions.
    """
    clean_mode = _norm_mode(mode) or _candidate_mode(candidate)
    if clean_mode == "3d":
        return [
            {
                "action": "this_volume",
                "label": "Assign to this volume",
                "scope_type": "candidate",
                "description": "Assign selected documents to only this 3D volume candidate.",
                "requires_document_ids": True,
                "requires_line_ids": False,
            },
            {
                "action": "all_volumes_in_package",
                "label": "Assign to all volumes in package",
                "scope_type": "survey",
                "description": "Assign selected documents to all 3D volume candidates in this package.",
                "requires_document_ids": True,
                "requires_line_ids": False,
            },
            {
                "action": "repository_3d",
                "label": "Assign to 3D repository",
                "scope_type": "repository",
                "description": "Assign selected documents to all candidates in this 3D source repository.",
                "requires_document_ids": True,
                "requires_line_ids": False,
            },
            {
                "action": "non_geophysical",
                "label": "Mark non-geophysical",
                "scope_type": "repository",
                "description": "Mark selected documents as non-geophysical evidence for this source repository.",
                "requires_document_ids": True,
                "requires_line_ids": False,
            },
            {
                "action": "clear",
                "label": "Clear assignment",
                "scope_type": "candidate",
                "description": "Clear the selected document assignments for this 3D volume candidate.",
                "requires_document_ids": False,
                "requires_line_ids": False,
            },
        ]
    return [
        {
            "action": "this_line",
            "label": "Assign to this line",
            "scope_type": "line",
            "description": "Assign selected documents to only this 2D line candidate.",
            "requires_document_ids": True,
            "requires_line_ids": False,
        },
        {
            "action": "selected_lines",
            "label": "Assign to selected lines",
            "scope_type": "line",
            "description": "Assign selected documents to the selected 2D lines in this package.",
            "requires_document_ids": True,
            "requires_line_ids": True,
        },
        {
            "action": "survey_all_lines",
            "label": "Assign to survey / all lines",
            "scope_type": "survey",
            "description": "Assign selected documents to all 2D lines in this package/survey.",
            "requires_document_ids": True,
            "requires_line_ids": False,
        },
        {
            "action": "non_geophysical",
            "label": "Mark non-geophysical",
            "scope_type": "repository",
            "description": "Mark selected documents as non-geophysical evidence for this source repository.",
            "requires_document_ids": True,
            "requires_line_ids": False,
        },
        {
            "action": "clear",
            "label": "Clear assignment",
            "scope_type": "line",
            "description": "Clear the selected document assignments for this candidate.",
            "requires_document_ids": False,
            "requires_line_ids": False,
        },
    ]


def get_candidate_document_assignment_review(candidate_id: str, selected_line_ids: Optional[List[str]] = None, mode: Optional[str] = None) -> Dict[str, Any]:
    candidate = _candidate_source(candidate_id)
    if not candidate:
        raise FileNotFoundError(f"Source Intake candidate not found: {candidate_id}")

    requested_mode = _norm_mode(mode)
    candidate_mode = _candidate_mode(candidate)
    if requested_mode and candidate_mode and requested_mode != candidate_mode:
        raise ValueError(f"Candidate {candidate_id} is {candidate_mode}, not requested mode={requested_mode}")

    repository_id = _clean(candidate.get("repository_id"))
    package_id = _clean(candidate.get("package_id"))
    line_id = _clean(candidate.get("line_id"))
    candidate_key = _candidate_key(candidate, candidate_id)
    store = _load_store()
    assignments = [a for a in store.get("assignments", []) if isinstance(a, dict)]
    all_documents = list_documents(repository_id=repository_id) if repository_id else []
    documents = [doc for doc in all_documents if _clean(doc.get("document_id")) and _document_is_candidate_option(doc, candidate, requested_mode)]
    document_rows = [_document_public_row(doc, candidate=candidate, assignments=assignments) for doc in documents]
    document_rows.sort(key=lambda row: (0 if row.get("assigned") else 1, 0 if row.get("match_confidence") == "high" else 1 if row.get("match_confidence") == "medium" else 2, str(row.get("filename") or "").lower()))
    effective_ids = _effective_assigned_document_ids(candidate)
    effective_ids = [doc_id for doc_id in effective_ids if any(_clean(row.get("document_id")) == doc_id for row in document_rows)]
    non_geo_count = sum(1 for row in document_rows if row.get("non_geophysical"))
    assigned_elsewhere_count = sum(1 for row in document_rows if row.get("assigned_elsewhere"))
    package = _package_by_id(package_id)
    return {
        "schema_version": "source_intake.document_assignment_review.v2",
        "candidate_id": candidate_key,
        "repository_id": repository_id,
        "package_id": package_id,
        "package_name": (package or {}).get("display_name") or (package or {}).get("package_key"),
        "line_id": line_id,
        "mode": candidate_mode or requested_mode,
        "filename": candidate.get("filename") or candidate.get("display_name"),
        "selected_line_ids": selected_line_ids or [],
        "available_line_ids_for_package": _line_ids_for_package(repository_id, package_id) if repository_id and package_id else [],
        "summary": {
            "discovered_document_count": len(document_rows),
            "repository_document_count": len(all_documents),
            "effective_document_count": len(effective_ids),
            "assigned_document_count": len(effective_ids),
            "unassigned_document_count": max(0, len(document_rows) - len(effective_ids) - assigned_elsewhere_count - non_geo_count),
            "assigned_elsewhere_document_count": assigned_elsewhere_count,
            "non_geophysical_count": non_geo_count,
            "scope_boundary": "same_3d_repository" if candidate_mode == "3d" else "same_repository_same_package",
        },
        "assignment_actions": _assignment_actions_for_candidate(candidate, candidate_mode or requested_mode),
        "documents": document_rows,
    }


def _new_assignment(document_id: str, repository_id: str, scope_type: str, scope_id: str, status: str, candidate_id: str, package_id: Optional[str], line_id: Optional[str]) -> Dict[str, Any]:
    return {
        "assignment_id": f"docassign_{uuid4().hex}",
        "document_id": document_id,
        "repository_id": repository_id,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "status": status,
        "candidate_id": candidate_id,
        "package_id": package_id,
        "line_id": line_id,
        "created_at": _now(),
    }


def _valid_document_ids_for_candidate(candidate: Dict[str, Any], requested_mode: str) -> Set[str]:
    repository_id = _clean(candidate.get("repository_id"))
    return {
        _clean(doc.get("document_id"))
        for doc in (list_documents(repository_id=repository_id) if repository_id else [])
        if _clean(doc.get("document_id")) and _document_is_candidate_option(doc, candidate, requested_mode)
    }


def assign_source_intake_documents(payload: Dict[str, Any]) -> Dict[str, Any]:
    candidate_id = _clean(payload.get("candidate_id"))
    raw_action = _clean(payload.get("action")).lower()
    requested_mode = _norm_mode(payload.get("mode"))
    document_ids = [_clean(x) for x in payload.get("document_ids") or [] if _clean(x)]
    line_ids = [_clean(x) for x in payload.get("line_ids") or [] if _clean(x)]
    validate_only = bool(payload.get("validate_only"))

    if not candidate_id:
        raise ValueError("candidate_id is required")

    candidate = _candidate_source(candidate_id)
    if not candidate:
        raise FileNotFoundError(f"Source Intake candidate not found: {candidate_id}")

    candidate_mode = _candidate_mode(candidate)
    if requested_mode and candidate_mode and requested_mode != candidate_mode:
        raise ValueError(f"Candidate {candidate_id} is {candidate_mode}, not requested mode={requested_mode}")

    action = raw_action
    if candidate_mode == "3d" and action == "this_line":
        # Compatibility bridge for older callers. Public review contracts expose
        # this as `this_volume`; frontend should not rely on the line wording.
        action = "this_volume"

    allowed_2d = {"survey_all_lines", "selected_lines", "this_line", "non_geophysical", "clear"}
    allowed_3d = {"this_volume", "all_volumes_in_package", "repository_3d", "non_geophysical", "clear"}
    allowed = allowed_3d if candidate_mode == "3d" else allowed_2d
    if action not in allowed:
        raise ValueError(f"Unsupported document assignment action for {candidate_mode or 'unknown'} workflow: {raw_action}")
    if action != "clear" and not document_ids:
        raise ValueError("At least one document_id is required")

    repository_id = _clean(candidate.get("repository_id"))
    package_id = _clean(candidate.get("package_id"))
    line_id = _clean(candidate.get("line_id"))
    candidate_key = _candidate_key(candidate, candidate_id)

    allowed_doc_ids = _valid_document_ids_for_candidate(candidate, requested_mode or candidate_mode)
    if document_ids:
        invalid = [doc_id for doc_id in document_ids if doc_id not in allowed_doc_ids]
        if invalid:
            raise ValueError(f"Document assignment rejected; document(s) are outside this candidate/package/mode boundary: {', '.join(invalid)}")

    available_line_ids = set(_line_ids_for_package(repository_id, package_id)) if repository_id and package_id else set()
    if action == "selected_lines":
        invalid_lines = [lid for lid in line_ids if lid not in available_line_ids]
        if invalid_lines:
            raise ValueError(f"Selected line assignment rejected; line(s) are outside this candidate package: {', '.join(invalid_lines)}")
        if not line_ids:
            raise ValueError("line_ids are required for selected-line assignment")

    store = _load_store()
    assignments = [a for a in store.get("assignments", []) if isinstance(a, dict)]
    target_lines = set(line_ids)
    effective_doc_ids = set(_effective_assigned_document_ids(candidate))

    def keep_assignment(a: Dict[str, Any]) -> bool:
        if _clean(a.get("repository_id")) != repository_id:
            return True
        doc_id = _clean(a.get("document_id"))
        if document_ids and doc_id not in document_ids:
            return True
        if action == "clear":
            if document_ids:
                return doc_id not in document_ids
            return not _assignment_applies_to_candidate(a, candidate)
        if action == "survey_all_lines" or action == "all_volumes_in_package":
            return not (doc_id in document_ids and _clean(a.get("scope_type")) == "survey" and _clean(a.get("scope_id")) == package_id)
        if action == "selected_lines":
            return not (doc_id in document_ids and _clean(a.get("scope_type")) == "line" and _clean(a.get("scope_id")) in target_lines)
        if action == "this_line":
            return not (doc_id in document_ids and _clean(a.get("scope_type")) == "line" and _clean(a.get("scope_id")) == line_id)
        if action == "this_volume":
            return not (doc_id in document_ids and _clean(a.get("scope_type")) == "candidate" and _clean(a.get("scope_id")) == candidate_key)
        if action == "repository_3d":
            return not (doc_id in document_ids and _clean(a.get("scope_type")) == "repository" and _clean(a.get("scope_id")) == repository_id and _clean(a.get("status")) == "assigned")
        if action == "non_geophysical":
            return not (doc_id in document_ids and _clean(a.get("scope_type")) == "repository" and _clean(a.get("status")) == "non_geophysical")
        return True

    new_assignments = [a for a in assignments if keep_assignment(a)]
    new_records: List[Dict[str, Any]] = []

    if action == "survey_all_lines":
        if not package_id:
            raise ValueError("candidate package_id is required for survey-level assignment")
        for doc_id in document_ids:
            new_records.append(_new_assignment(doc_id, repository_id, "survey", package_id, "assigned", candidate_key, package_id, None))
    elif action == "selected_lines":
        for doc_id in document_ids:
            for target_line_id in line_ids:
                new_records.append(_new_assignment(doc_id, repository_id, "line", target_line_id, "assigned", candidate_key, package_id, target_line_id))
    elif action == "this_line":
        if not line_id:
            raise ValueError("candidate line_id is required for line assignment")
        for doc_id in document_ids:
            new_records.append(_new_assignment(doc_id, repository_id, "line", line_id, "assigned", candidate_key, package_id, line_id))
    elif action == "this_volume":
        for doc_id in document_ids:
            new_records.append(_new_assignment(doc_id, repository_id, "candidate", candidate_key, "assigned", candidate_key, package_id, line_id))
    elif action == "all_volumes_in_package":
        if not package_id:
            raise ValueError("candidate package_id is required for package-level 3D assignment")
        for doc_id in document_ids:
            new_records.append(_new_assignment(doc_id, repository_id, "survey", package_id, "assigned", candidate_key, package_id, None))
    elif action == "repository_3d":
        for doc_id in document_ids:
            new_records.append(_new_assignment(doc_id, repository_id, "repository", repository_id, "assigned", candidate_key, package_id, None))
    elif action == "non_geophysical":
        for doc_id in document_ids:
            new_records.append(_new_assignment(doc_id, repository_id, "repository", repository_id, "non_geophysical", candidate_key, package_id, None))
    elif action == "clear" and not document_ids:
        document_ids = sorted(effective_doc_ids)

    if not validate_only:
        new_assignments.extend(new_records)
        store["assignments"] = new_assignments
        _save_store(store)

    return {
        "status": "ok",
        "schema_version": "source_intake.document_assignment_result.v2",
        "action": action,
        "requested_action": raw_action,
        "mode": candidate_mode or requested_mode,
        "dry_run": validate_only,
        "created_assignment_count": len(new_records),
        "candidate_id": candidate_key,
        "repository_id": repository_id,
        "package_id": package_id,
        "line_id": line_id,
        "document_ids": document_ids,
        "line_ids": line_ids,
        "review": get_candidate_document_assignment_review(candidate_key, selected_line_ids=line_ids, mode=requested_mode or candidate_mode),
    }


def get_candidate_effective_supporting_documents(candidate_id: str, mode: Optional[str] = None) -> Dict[str, Any]:
    """
    Resolve the assigned/effective supporting documents for a Source Intake
    candidate. This is read-only and is used by Managed Data / Info page
    contracts to expose documents without duplicating files or mutating
    canonical metadata.
    """
    candidate = _candidate_source(candidate_id)
    if not candidate:
        return {
            "schema_version": "source_intake.effective_supporting_documents.v1",
            "candidate_id": _clean(candidate_id),
            "mode": _norm_mode(mode),
            "document_count": 0,
            "supporting_document_count": 0,
            "supporting_documents": [],
            "document_assignment_status": "candidate_not_found",
        }

    requested_mode = _norm_mode(mode)
    candidate_mode = _candidate_mode(candidate)
    if requested_mode and candidate_mode and requested_mode != candidate_mode:
        return {
            "schema_version": "source_intake.effective_supporting_documents.v1",
            "candidate_id": _candidate_key(candidate, candidate_id),
            "mode": candidate_mode,
            "document_count": 0,
            "supporting_document_count": 0,
            "supporting_documents": [],
            "document_assignment_status": "mode_mismatch",
        }

    review = get_candidate_document_assignment_review(
        _candidate_key(candidate, candidate_id),
        selected_line_ids=[],
        mode=requested_mode or candidate_mode,
    )

    assigned_docs: List[Dict[str, Any]] = []
    for doc in review.get("documents", []) or []:
        if not isinstance(doc, dict):
            continue
        if not doc.get("assigned"):
            continue
        row = dict(doc)
        row["assignment_source"] = "source_intake_document_assignments"
        row["effective_for_candidate_id"] = _candidate_key(candidate, candidate_id)
        assigned_docs.append(row)

    return {
        "schema_version": "source_intake.effective_supporting_documents.v1",
        "candidate_id": _candidate_key(candidate, candidate_id),
        "repository_id": review.get("repository_id"),
        "package_id": review.get("package_id"),
        "line_id": review.get("line_id"),
        "mode": review.get("mode") or candidate_mode or requested_mode,
        "document_count": len(assigned_docs),
        "supporting_document_count": len(assigned_docs),
        "supporting_documents": assigned_docs,
        "document_assignment_status": "assigned" if assigned_docs else "unassigned",
        "summary": review.get("summary") or {},
    }

def summarize_candidate_document_assignments(item: Dict[str, Any], *, candidate_id: Any = None) -> Dict[str, Any]:
    candidate_key = _candidate_key(item, candidate_id)
    repository_id = _clean(item.get("repository_id"))
    candidate_mode = _candidate_mode(item)
    documents = [doc for doc in (list_documents(repository_id=repository_id) if repository_id else []) if _document_is_candidate_option(doc, item, candidate_mode)]
    valid_ids = {_clean(doc.get("document_id")) for doc in documents}
    effective_ids = [doc_id for doc_id in _effective_assigned_document_ids(item) if doc_id in valid_ids]
    non_geo_count = sum(1 for a in _effective_assignments(item) if _clean(a.get("status")) == "non_geophysical")
    return {
        "candidate_id": candidate_key,
        "document_count": len(effective_ids),
        "supporting_document_count": len(effective_ids),
        "assigned_document_count": len(effective_ids),
        "effective_document_count": len(effective_ids),
        "discovered_document_count": len(documents),
        "non_geophysical_document_count": non_geo_count,
        "evidence_status": "assigned" if effective_ids else "unassigned",
        "supporting_documents": [],
        "document_assignment_status": "assigned" if effective_ids else "unassigned",
    }
