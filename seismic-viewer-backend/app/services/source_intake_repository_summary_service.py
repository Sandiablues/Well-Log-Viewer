from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from app.services.repository_registry_service import get_repository
from app.services.package_registry_service import list_packages, list_lines, list_segy_files
from app.services.source_repository_mode_service import repository_matches_mode

try:
    from app.services.document_registry_service import list_documents  # type: ignore
except Exception:  # pragma: no cover - tolerate older local states
    list_documents = None  # type: ignore

try:
    from app.services.source_intake_document_link_service import summarize_repository_document_links  # type: ignore
except Exception:  # pragma: no cover - tolerate older local states
    summarize_repository_document_links = None  # type: ignore

SCHEMA_VERSION = "source_intake.repository_summary.v1"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_lower(value: Any) -> str:
    return _clean(value).lower()


def _count(items: Any) -> int:
    return len(items) if isinstance(items, list) else 0


def _unique_count(items: Iterable[Dict[str, Any]], keys: List[str]) -> int:
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        ident = ""
        for key in keys:
            ident = _clean(item.get(key))
            if ident:
                break
        if ident:
            seen.add(ident)
    return len(seen)


def infer_repository_mode(repo: Dict[str, Any], requested_mode: Optional[str] = None) -> str:
    requested = _clean_lower(requested_mode)
    if requested in {"2d", "3d"}:
        return requested
    if repository_matches_mode(repo, "3d"):
        return "3d"
    return "2d"


def _scope_label_from_repo(repo: Dict[str, Any], override: Optional[str] = None) -> str:
    if override:
        return override
    include = repo.get("include_subfolders")
    if include is True:
        return "root + subfolders"
    if include is False:
        return "root only"
    # Some older repo records store the latest scope in text fields only.
    for key in ("last_scan_scope_label", "scan_scope_label", "latest_scan_scope_label"):
        value = _clean(repo.get(key))
        if value:
            return value
    return "latest scan"


def _document_count(repository_id: str) -> int:
    if list_documents is not None:
        try:
            docs = list_documents(repository_id=repository_id)  # type: ignore[misc]
            if isinstance(docs, list):
                return len(docs)
        except TypeError:
            try:
                docs = list_documents()  # type: ignore[misc]
                if isinstance(docs, list):
                    return sum(1 for d in docs if isinstance(d, dict) and _clean(d.get("repository_id")) == repository_id)
            except Exception:
                pass
        except Exception:
            pass
    if summarize_repository_document_links is not None:
        try:
            summary = summarize_repository_document_links(repository_id)  # type: ignore[misc]
            if isinstance(summary, dict):
                for key in ("document_count", "total_documents", "linked_document_count"):
                    value = summary.get(key)
                    if isinstance(value, int):
                        return value
        except Exception:
            pass
    return 0


def _converted_count(segy_files: List[Dict[str, Any]]) -> int:
    converted_states = {"queued", "converting", "converted", "ready", "viewer_ready", "managed", "loaded"}
    total = 0
    for item in segy_files:
        if not isinstance(item, dict):
            continue
        values = [
            item.get("conversion_status"),
            item.get("managed_state"),
            item.get("status"),
            item.get("state"),
        ]
        if any(_clean_lower(v) in converted_states for v in values):
            total += 1
    return total


def build_repository_scan_summary(
    repository_id: str,
    *,
    mode: Optional[str] = None,
    scope_label: Optional[str] = None,
) -> Dict[str, Any]:
    clean_repo = _clean(repository_id)
    if not clean_repo:
        raise ValueError("repository_id is required")

    repo = get_repository(clean_repo)
    if not repo:
        raise FileNotFoundError(f"Repository not found: {clean_repo}")

    clean_mode = infer_repository_mode(repo, mode)
    if not repository_matches_mode(repo, clean_mode):
        raise ValueError(f"Repository {clean_repo} does not match requested mode={clean_mode}.")

    packages = list_packages(repository_id=clean_repo)
    lines = list_lines(repository_id=clean_repo)
    segy_files = list_segy_files(repository_id=clean_repo)
    documents = _document_count(clean_repo)

    package_count = _count(packages)
    line_count = _count(lines)
    segy_file_count = _count(segy_files)
    converted_count = _converted_count(segy_files)

    if clean_mode == "3d":
        # A 3D workbench candidate represents a volume candidate, not a 2D line.
        # Count unique volume/candidate identifiers where present; fall back to SEG-Y count.
        volume_count = _unique_count(
            segy_files,
            ["volume_id", "candidate_id", "source_segy_file_id", "segy_file_id", "id"],
        ) or segy_file_count
        primary_count = volume_count
        primary_label = "volumes"
        singular_primary_label = "volume"
    else:
        primary_count = line_count
        primary_label = "lines"
        singular_primary_label = "line"
        volume_count = 0

    clean_scope = _scope_label_from_repo(repo, scope_label)
    message = (
        f"Scan complete ({clean_scope}): "
        f"{package_count} packages, {primary_count} {primary_label}, "
        f"{segy_file_count} SEG-Y files, {documents} documents."
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "repository_id": clean_repo,
        "mode": clean_mode,
        "scope_label": clean_scope,
        "package_count": package_count,
        "line_count": line_count,
        "volume_count": volume_count,
        "primary_count": primary_count,
        "primary_label": primary_label,
        "singular_primary_label": singular_primary_label,
        "segy_file_count": segy_file_count,
        "candidate_count": segy_file_count,
        "document_count": documents,
        "converted_count": converted_count,
        "message": message,
    }


def decorate_repository(repo: Dict[str, Any], *, mode: Optional[str] = None) -> Dict[str, Any]:
    repository_id = _clean(repo.get("repository_id") or repo.get("id"))
    summary = build_repository_scan_summary(repository_id, mode=mode) if repository_id else {}
    result = dict(repo)
    result.update(
        {
            "package_count": summary.get("package_count", 0),
            "line_count": summary.get("line_count", 0),
            "volume_count": summary.get("volume_count", 0),
            "candidate_count": summary.get("candidate_count", 0),
            "document_count": summary.get("document_count", 0),
            "submitted_count": summary.get("converted_count", 0),
            "scan_summary": summary,
        }
    )
    return result
