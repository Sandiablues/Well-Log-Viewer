
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import uuid


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_ROOT / "data"
REGISTRY_DIR = DATA_DIR / "registry"
REPOSITORIES_PATH = REGISTRY_DIR / "repositories.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_registry() -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    if not REPOSITORIES_PATH.exists():
        REPOSITORIES_PATH.write_text("[]", encoding="utf-8")


def _read_json_list(path: Path) -> List[Dict[str, Any]]:
    _ensure_registry()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _write_json_list(path: Path, value: List[Dict[str, Any]]) -> None:
    _ensure_registry()
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")



def _parse_repository_intent(notes: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Extract first-class repository intent fields from legacy notes text.

    SourceRepositoryManager currently sends notes such as:
      source_structure_type=multi_version_3d_delivery; intended_use=3d_segy_intake

    Store these as real fields so downstream discovery/classification does not
    depend on React-side heuristics or repeated string parsing.
    """
    text = notes or ""
    result: Dict[str, Optional[str]] = {
        "source_structure_type": None,
        "intended_use": None,
    }

    for part in text.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key in result and value:
            result[key] = value

    return result


def list_repositories() -> List[Dict[str, Any]]:
    repos = _read_json_list(REPOSITORIES_PATH)
    for repo in repos:
        root_path = repo.get("root_path")
        repo["status"] = "available" if root_path and Path(root_path).exists() else "missing"
    return repos


def get_repository(repository_id: str) -> Optional[Dict[str, Any]]:
    for repo in list_repositories():
        if repo.get("repository_id") == repository_id:
            return repo
    return None


def add_repository(
    name: str,
    root_path: str,
    repository_type: str = "local_folder",
    read_only: bool = True,
    notes: Optional[str] = None,
    include_subfolders: bool = False,
) -> Dict[str, Any]:
    root = Path(root_path).expanduser().resolve()

    if not root.exists():
        raise FileNotFoundError(f"Repository root does not exist: {root}")

    if not root.is_dir():
        raise NotADirectoryError(f"Repository root is not a directory: {root}")

    repos = _read_json_list(REPOSITORIES_PATH)

    for repo in repos:
        existing_root = Path(repo.get("root_path", "")).expanduser()
        try:
            if existing_root.resolve() == root:
                repo["name"] = name or repo.get("name")
                repo["repository_type"] = repository_type or repo.get("repository_type", "local_folder")
                repo["read_only"] = bool(read_only)
                repo["include_subfolders"] = bool(include_subfolders)
                repo["notes"] = notes
                intent = _parse_repository_intent(notes)
                if intent.get("source_structure_type"):
                    repo["source_structure_type"] = intent["source_structure_type"]
                if intent.get("intended_use"):
                    repo["intended_use"] = intent["intended_use"]
                repo["status"] = "available"
                repo["updated_at"] = _utc_now()
                _write_json_list(REPOSITORIES_PATH, repos)
                return repo
        except Exception:
            pass

    intent = _parse_repository_intent(notes)

    repo = {
        "repository_id": f"repo_{uuid.uuid4().hex[:12]}",
        "name": name,
        "root_path": str(root),
        "repository_type": repository_type,
        "status": "available",
        "read_only": bool(read_only),
        "include_subfolders": bool(include_subfolders),
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "last_scanned_at": None,
        "notes": notes,
        "source_structure_type": intent.get("source_structure_type"),
        "intended_use": intent.get("intended_use"),
    }

    repos.append(repo)
    _write_json_list(REPOSITORIES_PATH, repos)
    return repo


def update_repository_scan_time(repository_id: str) -> None:
    repos = _read_json_list(REPOSITORIES_PATH)
    changed = False

    for repo in repos:
        if repo.get("repository_id") == repository_id:
            repo["last_scanned_at"] = _utc_now()
            repo["updated_at"] = _utc_now()
            changed = True
            break

    if changed:
        _write_json_list(REPOSITORIES_PATH, repos)


def resolve_repository_path(repository_id: str, relative_path: str) -> Path:
    repo = get_repository(repository_id)
    if not repo:
        raise FileNotFoundError(f"Repository not found: {repository_id}")

    root = Path(repo["root_path"]).expanduser().resolve()
    candidate = (root / relative_path).resolve()

    try:
        candidate.relative_to(root)
    except ValueError:
        raise PermissionError("Resolved path escapes repository root")

    return candidate

def delete_repository_cascade(repository_id: str) -> Dict[str, Any]:
    """
    Delete a source repository and all source-inventory records derived from it.

    This intentionally does NOT delete:
    - data/volumes.json records
    - converted Zarr folders
    - conversion jobs
    - uploaded source files

    Converted Managed Data may remain available after its original source
    repository connector is removed.
    """
    _ensure_registry()

    paths = {
        "repositories": REPOSITORIES_PATH,
        "packages": REGISTRY_DIR / "packages.json",
        "lines": REGISTRY_DIR / "lines.json",
        "segy_files": REGISTRY_DIR / "segy_files.json",
        "documents": REGISTRY_DIR / "documents.json",
    }

    repositories = _read_json_list(REPOSITORIES_PATH)
    deleted_repository = next(
        (repo for repo in repositories if repo.get("repository_id") == repository_id),
        None,
    )

    if not deleted_repository:
        return {
            "deleted": False,
            "repository_id": repository_id,
            "reason": "repository_not_found",
            "removed": {},
        }

    removed: Dict[str, int] = {}

    for key, path in paths.items():
        records = _read_json_list(path)

        if key == "repositories":
            kept = [item for item in records if item.get("repository_id") != repository_id]
        else:
            kept = [item for item in records if item.get("repository_id") != repository_id]

        removed[key] = len(records) - len(kept)
        _write_json_list(path, kept)

    return {
        "deleted": True,
        "repository_id": repository_id,
        "repository": deleted_repository,
        "removed": removed,
        "managed_data_deleted": False,
        "message": "Source repository and scanned source inventory removed. Converted Managed Data was not deleted.",
    }

