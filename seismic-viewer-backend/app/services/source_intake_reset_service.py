from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
REGISTRY_DIR = DATA_DIR / "registry"
SEGY_FILES_PATH = REGISTRY_DIR / "segy_files.json"
SOURCE_INTAKE_INDEX_JOBS_DIR = DATA_DIR / "source_intake_index_jobs"
SEGY_INDEX_DIR = DATA_DIR / "segy_index"
SOURCE_INTAKE_QAQC_DIR = DATA_DIR / "source_intake_qaqc"
SOURCE_INTAKE_DOCUMENT_ASSIGNMENTS_PATH = DATA_DIR / "source_intake_document_assignments.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _walk_values(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk_values(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _walk_values(item)
    else:
        text = _clean(value)
        if text:
            yield text


def _load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _json_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _contains_any_token(path: Path, tokens: Set[str]) -> bool:
    if any(token and token in path.name for token in tokens):
        return True
    text = _json_text(path)
    return any(token and token in text for token in tokens)


def _collect_seed_tokens(*contexts: Any) -> Set[str]:
    tokens: Set[str] = set()

    for context in contexts:
        for value in _walk_values(context):
            if not value:
                continue
            tokens.add(value)

            source_match = re.search(r"source_segy_(segy_[^:]+)", value)
            if source_match:
                tokens.add(source_match.group(1))

            zarr_match = re.search(r"zarr_([0-9a-fA-F-]{16,})", value)
            if zarr_match:
                tokens.add(zarr_match.group(1))

    return {token for token in tokens if token}


def _source_rows() -> List[Dict[str, Any]]:
    rows = _load_json(SEGY_FILES_PATH, [])
    return rows if isinstance(rows, list) else []


def _source_row_matches(row: Dict[str, Any], tokens: Set[str]) -> bool:
    if not isinstance(row, dict):
        return False

    direct_fields = [
        "segy_file_id",
        "candidate_id",
        "source_segy_file_id",
        "line_id",
        "package_id",
        "repository_id",
        "volume_id",
        "physical_volume_id",
        "representation_id",
        "msi_representation_id",
        "managed_representation_id",
        "filename",
        "display_name",
        "relative_path",
        "inferred_line_key",
        "zarr_url",
        "storage_uri",
    ]

    for field in direct_fields:
        value = _clean(row.get(field))
        if value and value in tokens:
            return True

    strong_tokens = [
        token for token in tokens
        if token.startswith(("segy_", "line_", "pkg_", "repo_", "msi_repr:", "source-intake-index-"))
        or "FN923" in token
        or "28242970" in token
    ]
    if not strong_tokens:
        return False

    text = json.dumps(row, sort_keys=True)
    return any(token and token in text for token in strong_tokens)


def _expand_from_source_registry(tokens: Set[str]) -> tuple[Set[str], List[Dict[str, Any]]]:
    expanded = set(tokens)
    matched_rows: List[Dict[str, Any]] = []

    for row in _source_rows():
        if not _source_row_matches(row, expanded):
            continue

        matched_rows.append(row)
        for value in _walk_values(row):
            if value:
                expanded.add(value)

    return expanded, matched_rows


def _reset_source_registry_rows(tokens: Set[str], reason: str) -> Dict[str, Any]:
    rows = _source_rows()
    if not rows:
        return {"updated": 0, "path": str(SEGY_FILES_PATH), "rows": []}

    updated_rows: List[str] = []
    changed = False
    reset_at = _utc_now()

    for row in rows:
        if not isinstance(row, dict) or not _source_row_matches(row, tokens):
            continue

        row_id = _clean(row.get("segy_file_id") or row.get("candidate_id"))
        updated_rows.append(row_id or _clean(row.get("filename")))

        current_generation = row.get("derived_state_generation")
        try:
            current_generation = int(current_generation or 0)
        except Exception:
            current_generation = 0

        row["derived_state_generation"] = current_generation + 1
        row["derived_state_reset_at"] = reset_at
        row["derived_state_reset_reason"] = reason
        row["index_state"] = "not_built"
        row["geometry_qaqc_state"] = "not_run"
        row["document_assignment_state"] = "cleared"

        row["conversion_status"] = "not_converted"
        row["conversion_state"] = "not_converted"
        row["conversion_state_authoritative"] = True
        row["conversion_state_reason"] = "Managed Data delete reset all Source Intake derived state."
        row["job_id"] = None
        row["zarr_url"] = None
        row["storage_uri"] = None
        row["conversion_error"] = None
        row["conversion_queued_at"] = None
        row["converted_at"] = None
        row["volume_id"] = None
        row["representation_id"] = None
        row["msi_representation_id"] = None
        row["managed_representation_id"] = None
        row["physical_volume_id"] = None
        row["viewer_ready"] = False
        row["updated_at"] = reset_at
        changed = True

    if changed:
        _save_json(SEGY_FILES_PATH, rows)

    return {
        "updated": len(updated_rows),
        "path": str(SEGY_FILES_PATH),
        "rows": updated_rows,
        "derived_state_reset_at": reset_at if updated_rows else None,
    }


def _remove_source_intake_index_jobs(tokens: Set[str]) -> Dict[str, Any]:
    removed: List[str] = []
    dataset_ids: Set[str] = set()

    if SOURCE_INTAKE_INDEX_JOBS_DIR.exists():
        for path in sorted(SOURCE_INTAKE_INDEX_JOBS_DIR.glob("*.json")):
            job = _load_json(path, {})
            if not isinstance(job, dict):
                continue

            text = json.dumps(job, sort_keys=True)
            if not any(token and (token in text or token in path.name) for token in tokens):
                continue

            dataset_id = _clean(job.get("dataset_id"))
            if dataset_id:
                dataset_ids.add(dataset_id)

            try:
                path.unlink()
                removed.append(str(path))
            except Exception as exc:
                removed.append(f"FAILED:{path}:{exc}")

    return {
        "removed": removed,
        "dataset_ids": sorted(dataset_ids),
    }


def _remove_segy_index_dirs(tokens: Set[str], dataset_ids: Iterable[str]) -> Dict[str, Any]:
    removed: List[str] = []
    all_dataset_ids = {_clean(x) for x in dataset_ids if _clean(x)}

    for dataset_id in sorted(all_dataset_ids):
        path = SEGY_INDEX_DIR / dataset_id
        if path.exists() and path.is_dir():
            try:
                shutil.rmtree(path)
                removed.append(str(path))
            except Exception as exc:
                removed.append(f"FAILED:{path}:{exc}")

    if SEGY_INDEX_DIR.exists():
        for index_json in sorted(SEGY_INDEX_DIR.glob("*/segy_index.json")):
            parent = index_json.parent
            if str(parent) in removed:
                continue
            if _contains_any_token(index_json, tokens):
                try:
                    shutil.rmtree(parent)
                    removed.append(str(parent))
                except Exception as exc:
                    removed.append(f"FAILED:{parent}:{exc}")

    return {"removed": removed}


def _remove_geometry_qaqc(tokens: Set[str]) -> Dict[str, Any]:
    removed: List[str] = []

    if SOURCE_INTAKE_QAQC_DIR.exists():
        for path in sorted(SOURCE_INTAKE_QAQC_DIR.glob("*.json")):
            if _contains_any_token(path, tokens):
                try:
                    path.unlink()
                    removed.append(str(path))
                except Exception as exc:
                    removed.append(f"FAILED:{path}:{exc}")

    return {"removed": removed}


def _clear_document_assignments(tokens: Set[str]) -> Dict[str, Any]:
    payload = _load_json(SOURCE_INTAKE_DOCUMENT_ASSIGNMENTS_PATH, None)
    if not isinstance(payload, dict):
        return {"removed": 0, "path": str(SOURCE_INTAKE_DOCUMENT_ASSIGNMENTS_PATH)}

    assignments = payload.get("assignments")
    if not isinstance(assignments, list):
        return {"removed": 0, "path": str(SOURCE_INTAKE_DOCUMENT_ASSIGNMENTS_PATH)}

    kept: List[Any] = []
    removed = 0

    for assignment in assignments:
        if not isinstance(assignment, dict):
            kept.append(assignment)
            continue

        assignment_values = {
            _clean(assignment.get("candidate_id")),
            _clean(assignment.get("source_segy_file_id")),
            _clean(assignment.get("line_id")),
            _clean(assignment.get("package_id")),
            _clean(assignment.get("repository_id")),
            _clean(assignment.get("scope_id")),
            _clean(assignment.get("document_id")),
        }

        if any(value and value in tokens for value in assignment_values):
            removed += 1
            continue

        kept.append(assignment)

    if removed:
        payload["assignments"] = kept
        payload["updated_at"] = _utc_now()
        _save_json(SOURCE_INTAKE_DOCUMENT_ASSIGNMENTS_PATH, payload)

    return {
        "removed": removed,
        "path": str(SOURCE_INTAKE_DOCUMENT_ASSIGNMENTS_PATH),
    }


def reset_source_intake_candidate_derived_state(*contexts: Any, reason: str = "managed_data_delete") -> Dict[str, Any]:
    # Service boundary for current application-development delete semantics:
    # Managed Data delete removes all derived SI/MSI/viewer state for the
    # dataset. The original source SEG-Y file is never deleted.
    seed_tokens = _collect_seed_tokens(*contexts)
    expanded_tokens, matched_source_rows = _expand_from_source_registry(seed_tokens)

    registry_result = _reset_source_registry_rows(expanded_tokens, reason)
    index_job_result = _remove_source_intake_index_jobs(expanded_tokens)

    dataset_ids = set(index_job_result.get("dataset_ids") or [])
    for token in expanded_tokens:
        if re.fullmatch(r"[0-9a-fA-F]{8,}|[0-9a-fA-F-]{16,}", token):
            dataset_ids.add(token)

    segy_index_result = _remove_segy_index_dirs(expanded_tokens, dataset_ids)
    qaqc_result = _remove_geometry_qaqc(expanded_tokens)
    documents_result = _clear_document_assignments(expanded_tokens)

    return {
        "reason": reason,
        "seed_token_count": len(seed_tokens),
        "token_count": len(expanded_tokens),
        "matched_source_rows": [
            {
                "segy_file_id": row.get("segy_file_id"),
                "filename": row.get("filename"),
                "repository_id": row.get("repository_id"),
                "package_id": row.get("package_id"),
                "line_id": row.get("line_id"),
            }
            for row in matched_source_rows
        ],
        "registry": registry_result,
        "index_jobs": index_job_result,
        "segy_index": segy_index_result,
        "geometry_qaqc": qaqc_result,
        "document_assignments": documents_result,
    }
