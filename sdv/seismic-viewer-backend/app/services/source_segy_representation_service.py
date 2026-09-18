from __future__ import annotations

"""
Source SEG-Y representation service.

Read-only lifecycle/status contract for representations derived from a source
SEG-Y record.

This service deliberately does not index, build cache, convert, load, unload,
archive, or delete. It gives the 3D EDR a stable backend-owned decision model.

Representation types:
- indexed_preview
- optimized_cache
- zarr_full_conversion

Identity rule:
source_repository_id + source_segy_file_id + representation_type
should resolve to at most one active representation unless explicit versioning
is introduced later.
"""

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.services.dataset_registry_service import list_indexed_datasets
from app.services.volume_registry_service import load_volumes
from app.services.conversion_state_service import resolve_source_segy_conversion_state
from app.services.source_staging_service import list_staged_source_items
from app.services.package_registry_service import list_segy_files
from app.services.repository_registry_service import list_repositories, get_repository
from app.services.segy_index_service import SegyIndexService
from app.storage.service import is_endrepo_zarr_url, resolve_endrepo_zarr_url_path


ACTIVE_STATUSES = {
    "queued",
    "converting",
    "reading_index",
    "validating_zarr",
    "promoting_output",
}


def _field(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    if is_dataclass(value):
        return asdict(value).get(key, default)
    return getattr(value, key, default)


def _first_field(value: Any, keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        result = _field(value, key, None)
        if result is not None:
            return result
    return default


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _norm_path(value: Any) -> str:
    if not value:
        return ""
    try:
        return str(Path(str(value)).expanduser().resolve())
    except Exception:
        return str(value)


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _zarr_url_exists(zarr_url: Any) -> bool:
    text = _safe_str(zarr_url)
    if not text:
        return False

    if text.startswith("/data/zarr/"):
        return (_backend_root() / text.lstrip("/")).exists()

    if is_endrepo_zarr_url(text):
        try:
            return resolve_endrepo_zarr_url_path(text).exists()
        except Exception:
            return False

    if text.startswith("file://"):
        return Path(text.replace("file://", "", 1)).exists()

    # Object-store/archive URIs will be verified by archive/storage adapters later.
    if "://" in text:
        return True

    return False


def _all_source_segy_files() -> List[Dict[str, Any]]:
    """
    Resolve source SEG-Y rows from package registry, not API route functions.

    Supports both implementations:
    - list_segy_files() with no repository argument
    - list_segy_files(repository_id=...)
    """
    try:
        records = list_segy_files()
        if isinstance(records, list):
            return [x for x in records if isinstance(x, dict)]
    except TypeError:
        pass

    all_records: List[Dict[str, Any]] = []

    repos_payload = list_repositories()
    if isinstance(repos_payload, dict):
        repos = repos_payload.get("repositories", [])
    else:
        repos = repos_payload or []

    for repo in repos:
        if not isinstance(repo, dict):
            continue
        repo_id = repo.get("repository_id")
        if not repo_id:
            continue

        try:
            records = list_segy_files(repository_id=repo_id)
        except TypeError:
            records = list_segy_files(repo_id)
        except Exception:
            records = []

        if isinstance(records, list):
            all_records.extend([x for x in records if isinstance(x, dict)])

    return all_records


def get_source_segy_file(segy_file_id: str) -> Dict[str, Any]:
    clean_id = _safe_str(segy_file_id)

    for record in _all_source_segy_files():
        if _safe_str(record.get("segy_file_id")) == clean_id:
            return record

    raise FileNotFoundError(f"SEG-Y source record not found: {clean_id}")


def _source_path(record: Dict[str, Any]) -> str:
    """
    Resolve the physical source SEG-Y path from deterministic backend-owned state.

    Priority:
    1. explicit absolute/source/file path if already present
    2. repository.root_path + record.relative_path

    The frontend must not provide this path for indexing/conversion actions.
    """
    explicit = _norm_path(
        record.get("absolute_path")
        or record.get("source_path")
        or record.get("path")
        or record.get("file_path")
    )

    if explicit:
        return explicit

    repo_id = record.get("repository_id")
    relative_path = record.get("relative_path")

    if not repo_id or not relative_path:
        return ""

    try:
        repo = get_repository(str(repo_id))
    except Exception:
        repo = None

    if not isinstance(repo, dict):
        return ""

    root_path = repo.get("root_path")
    if not root_path:
        return ""

    return _norm_path(Path(str(root_path)).expanduser() / str(relative_path))


def _source_path_exists(record: Dict[str, Any]) -> bool:
    source_path = _source_path(record)
    return bool(source_path and Path(source_path).exists() and Path(source_path).is_file())




def _source_identity(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_repository_id": record.get("repository_id"),
        "source_segy_file_id": record.get("segy_file_id"),
        "source_relative_path": record.get("relative_path"),
        "source_path": _source_path(record),
        "source_path_exists": _source_path_exists(record),
        "filename": record.get("filename"),
        "candidate_kind": record.get("candidate_kind"),
        "candidate_role": record.get("candidate_role"),
    }


def _is_submitted_for_mode(record: Dict[str, Any], mode: str) -> bool:
    segy_file_id = _safe_str(record.get("segy_file_id"))
    repo_id = _safe_str(record.get("repository_id"))

    try:
        items = list_staged_source_items()
    except TypeError:
        try:
            items = list_staged_source_items(repository_id=repo_id)
        except Exception:
            items = []
    except Exception:
        items = []

    if isinstance(items, dict):
        items = items.get("items") or items.get("staged_source_items") or []

    if not isinstance(items, list):
        return False

    for item in items:
        if not isinstance(item, dict):
            continue

        if _safe_str(item.get("staged_for")) != _safe_str(mode):
            continue

        if _safe_str(item.get("staging_status")) != "submitted":
            continue

        if item.get("source_item_type") != "segy_file":
            continue

        if _safe_str(item.get("segy_file_id") or item.get("source_item_id")) == segy_file_id:
            return True

    return False


def _is_3d_volume_candidate(record: Dict[str, Any]) -> bool:
    return (
        record.get("candidate_kind") == "3d_volume"
        and record.get("candidate_role") == "volume_candidate"
    )


def _is_2d_line_candidate(record: Dict[str, Any]) -> bool:
    return (
        record.get("candidate_kind") == "2d_line"
        and record.get("candidate_role") == "line_candidate"
    )


def _find_indexed_dataset(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    source_path = _source_path(record)
    filename = _safe_str(record.get("filename"))
    size = record.get("size_bytes")

    for dataset in list_indexed_datasets():
        if not isinstance(dataset, dict):
            continue

        ds_path = _norm_path(dataset.get("source_path"))
        if source_path and ds_path and source_path == ds_path:
            return dataset

        # Fallback only when path is unavailable.
        if not source_path and filename:
            if _safe_str(dataset.get("filename")) == filename:
                if size is None or dataset.get("source_size_bytes") in {None, size}:
                    return dataset

    return None


def _volume_records() -> List[Dict[str, Any]]:
    payload = load_volumes()
    if isinstance(payload, dict):
        return [x for x in payload.values() if isinstance(x, dict)]
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    return []


def _find_full_volume(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    volume_id = _safe_str(record.get("volume_id"))
    zarr_url = _safe_str(record.get("zarr_url"))
    segy_file_id = _safe_str(record.get("segy_file_id"))
    repo_id = _safe_str(record.get("repository_id"))
    source_path = _source_path(record)

    for volume in _volume_records():
        vid = _safe_str(volume.get("id") or volume.get("volume_id"))
        vzarr = _safe_str(volume.get("zarr_url"))

        if volume_id and vid == volume_id:
            return volume

        if zarr_url and vzarr == zarr_url:
            return volume

        if segy_file_id and _safe_str(volume.get("source_segy_file_id")) == segy_file_id:
            if not repo_id or _safe_str(volume.get("source_repository_id")) == repo_id:
                return volume

        metadata = volume.get("metadata") if isinstance(volume.get("metadata"), dict) else {}
        vsource_path = _norm_path(
            volume.get("source_path")
            or metadata.get("source_path")
            or metadata.get("input_path")
        )

        if source_path and vsource_path and source_path == vsource_path:
            return volume

    return None


def _conversion_status(record: Dict[str, Any]) -> Dict[str, Any]:
    state = resolve_source_segy_conversion_state(record)

    status = (
        _first_field(state, ["conversion_status", "status"], None)
        or record.get("conversion_status")
        or "not_converted"
    )

    return {
        "status": status,
        "job_id": _first_field(state, ["job_id"], record.get("job_id")),
        "volume_id": _first_field(state, ["volume_id"], record.get("volume_id")),
        "zarr_url": _first_field(state, ["zarr_url"], record.get("zarr_url")),
        "reason": _first_field(state, ["conversion_state_reason", "reason"], None),
        "authoritative": bool(_first_field(state, ["conversion_state_authoritative", "authoritative"], False)),
        "raw_state_type": type(state).__name__,
    }


def build_source_segy_representations(record: Dict[str, Any], mode: str = "3d") -> Dict[str, Any]:
    clean_mode = _safe_str(mode).lower()
    submitted = _is_submitted_for_mode(record, clean_mode)
    is_3d_candidate = _is_3d_volume_candidate(record)
    is_2d_candidate = _is_2d_line_candidate(record)
    is_mode_candidate = (
        (clean_mode == "3d" and is_3d_candidate)
        or (clean_mode == "2d" and is_2d_candidate)
    )

    indexed = _find_indexed_dataset(record)
    volume = _find_full_volume(record)
    conversion = _conversion_status(record)

    indexed_status = "available" if indexed else "not_built"

    optimized_cache = indexed.get("optimized_cache") if isinstance(indexed, dict) else None
    if not isinstance(optimized_cache, dict):
        optimized_cache = {}

    optimized_status = (
        indexed.get("optimized_cache_status")
        if isinstance(indexed, dict)
        else None
    ) or optimized_cache.get("status") or "not_built"

    if optimized_status in {"", "none", "not_started"}:
        optimized_status = "not_built"

    full_status = conversion["status"]

    full_zarr_url = (
        volume.get("zarr_url")
        if isinstance(volume, dict)
        else conversion.get("zarr_url")
    )

    full_volume_id = (
        volume.get("id") or volume.get("volume_id")
        if isinstance(volume, dict)
        else conversion.get("volume_id")
    )

    full_exists = _zarr_url_exists(full_zarr_url)

    # If the source record still remembers a completed conversion job but the
    # managed volume record and/or Zarr artifact has been deleted, do not expose
    # the stale volume_id/zarr_url as an available representation.
    #
    # This commonly happens during reload/retest flows:
    # - user deletes Managed Data record
    # - source SEG-Y still has historical conversion state
    # - EDR should offer reconversion, not display a dead artifact as if usable
    stale_full_conversion = bool(
        full_status in {"converted", "ready", "error"}
        and not full_exists
    )

    if stale_full_conversion:
        full_status = "reconvert_required"
        full_volume_id = None
        full_zarr_url = None

    return {
        "status": "ok",
        "mode": mode,
        "source": _source_identity(record),
        "is_submitted": submitted,
        "is_3d_volume_candidate": is_3d_candidate,
        "is_2d_line_candidate": is_2d_candidate,
        "representations": {
            "indexed_preview": {
                "representation_type": "indexed_preview",
                "status": indexed_status,
                "available": bool(indexed),
                "dataset_id": indexed.get("dataset_id") if isinstance(indexed, dict) else None,
                "legacy_volume_id": indexed.get("legacy_volume_id") if isinstance(indexed, dict) else None,
                "artifact_status": "available" if indexed else "not_built",
                "action_available": bool(submitted and is_3d_candidate and not indexed),
            },
            "optimized_cache": {
                "representation_type": "optimized_cache",
                "status": optimized_status,
                "available": bool(
                    optimized_cache.get("zarr_url")
                    and optimized_status in {"available", "ready", "converted"}
                    and _zarr_url_exists(optimized_cache.get("zarr_url"))
                ),
                "dataset_id": indexed.get("dataset_id") if isinstance(indexed, dict) else None,
                "job_id": optimized_cache.get("job_id"),
                "cache_id": optimized_cache.get("cache_id"),
                "zarr_url": optimized_cache.get("zarr_url"),
                "artifact_status": optimized_status,
                "action_available": bool(
                    submitted
                    and is_3d_candidate
                    and indexed
                    and optimized_status not in ACTIVE_STATUSES
                    and optimized_status not in {"available", "ready", "converted"}
                ),
            },
            "zarr_full_conversion": {
                "representation_type": "zarr_full_conversion",
                "status": full_status,
                "available": bool(full_status in {"converted", "ready"} and full_exists),
                "volume_id": full_volume_id,
                "job_id": conversion.get("job_id"),
                "zarr_url": full_zarr_url,
                "artifact_status": (
                    "available"
                    if full_exists
                    else ("missing" if full_status in {"converted", "ready"} else full_status)
                ),
                "state_reason": conversion.get("reason"),
                "authoritative": conversion.get("authoritative"),
                "raw_state_type": conversion.get("raw_state_type"),
                "action_available": bool(
                    submitted
                    and is_mode_candidate
                    and full_status not in ACTIVE_STATUSES
                    and full_status not in {"converted", "ready"}
                ),
            },
        },
    }


def build_source_segy_representations_by_id(segy_file_id: str, mode: str = "3d") -> Dict[str, Any]:
    record = get_source_segy_file(segy_file_id)
    return build_source_segy_representations(record, mode=mode)


def index_source_segy_preview_by_id(segy_file_id: str, mode: str = "3d") -> Dict[str, Any]:
    """
    Build or return the indexed SEG-Y preview representation for a submitted source SEG-Y.

    This action:
    - resolves the source path server-side
    - requires submitted 3D volume-candidate status for 3D mode
    - does not build optimized cache
    - does not write volumes.json
    - does not perform full Zarr conversion
    - returns the updated representation contract

    Duplicate guard:
    If an indexed dataset already exists for the source SEG-Y, return existing status.
    """
    record = get_source_segy_file(segy_file_id)

    if _safe_str(mode) != "3d":
        raise ValueError(f"Unsupported representation indexing mode: {mode}")

    if not _is_submitted_for_mode(record, mode):
        raise PermissionError(
            f"SEG-Y source record is not submitted for {mode} EDR handoff: {segy_file_id}"
        )

    if not _is_3d_volume_candidate(record):
        raise ValueError(
            f"SEG-Y source record is not a confirmed 3D volume candidate: {segy_file_id}"
        )

    source_path = _source_path(record)

    if not source_path:
        raise FileNotFoundError(
            f"Source SEG-Y path could not be resolved from repository root + relative path: {segy_file_id}"
        )

    source_file = Path(source_path)

    if not source_file.exists() or not source_file.is_file():
        raise FileNotFoundError(f"Source SEG-Y file does not exist: {source_path}")

    existing = _find_indexed_dataset(record)

    if existing:
        return {
            "status": "ok",
            "action": "index_preview",
            "created": False,
            "message": "Indexed preview already exists for this source SEG-Y.",
            "dataset_id": existing.get("dataset_id"),
            "representations": build_source_segy_representations(record, mode=mode),
        }

    index = SegyIndexService.build_index(source_path)

    # Preserve source-registry linkage in the indexed record for future lifecycle/archive work.
    SegyIndexService.update_index(index["dataset_id"], {
        "source_repository_id": record.get("repository_id"),
        "source_segy_file_id": record.get("segy_file_id"),
        "source_relative_path": record.get("relative_path"),
        "representation_type": "indexed_preview",
        "lifecycle_status": "active",
    })

    return {
        "status": "ok",
        "action": "index_preview",
        "created": True,
        "message": "Indexed SEG-Y preview created.",
        "dataset_id": index.get("dataset_id"),
        "index": index,
        "representations": build_source_segy_representations(record, mode=mode),
    }

