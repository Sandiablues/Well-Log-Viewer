from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional
from datetime import datetime, timezone

REPOSITORY_MODE_2D = "2d"
REPOSITORY_MODE_3D = "3d"

INTENDED_USE_2D = "2d_segy_intake"
INTENDED_USE_3D = "3d_segy_intake"

SOURCE_STRUCTURE_2D = "survey_with_line_folders"
SOURCE_STRUCTURE_3D = "multi_version_3d_delivery"

_2D_SOURCE_STRUCTURES = {
    "single_isolated_line",
    "single_line_with_docs",
    "single_line_multi_version",
    "survey_with_line_folders",
    "survey_flat_lines",
}
_3D_SOURCE_STRUCTURES = {
    "single_3d_volume",
    "single_3d_volume_with_docs",
    "multi_version_3d_delivery",
}


def normalize_repository_mode(mode: Any) -> Optional[str]:
    clean = str(mode or "").strip().lower()
    if clean in {"2d", "2d_line", "line", "lines", "2d_segy_intake"}:
        return REPOSITORY_MODE_2D
    if clean in {"3d", "3d_volume", "volume", "volumes", "3d_segy_intake"}:
        return REPOSITORY_MODE_3D
    return None


def repository_mode(repo: dict[str, Any] | None) -> Optional[str]:
    if not isinstance(repo, dict):
        return None

    explicit = normalize_repository_mode(repo.get("workflow_mode") or repo.get("mode"))
    if explicit:
        return explicit

    intended_use = str(repo.get("intended_use") or "").strip().lower()
    source_structure_type = str(repo.get("source_structure_type") or "").strip().lower()
    notes = str(repo.get("notes") or "").strip().lower()

    if intended_use == INTENDED_USE_2D or source_structure_type in _2D_SOURCE_STRUCTURES or "intended_use=2d_segy_intake" in notes:
        return REPOSITORY_MODE_2D
    if intended_use == INTENDED_USE_3D or source_structure_type in _3D_SOURCE_STRUCTURES or "intended_use=3d_segy_intake" in notes:
        return REPOSITORY_MODE_3D
    return None


# MANUAL_UPLOAD_STAGING_2B_MODE_CONTRACT
def _manual_upload_workflow_mode_from_repository(repo):
    """Return explicit manual-upload workflow mode from backend-owned repo metadata.

    Manual upload repositories are Source Intake repositories whose workflow
    mode is stored in top-level fields or JSON notes. Mode validation must read
    that backend-owned metadata centrally instead of requiring every caller to
    decorate repositories first.
    """
    if not isinstance(repo, dict):
        return ""

    def clean(value):
        return str(value or "").strip().lower()

    notes = repo.get("notes")
    parsed_notes = {}
    if isinstance(notes, dict):
        parsed_notes = dict(notes)
    elif isinstance(notes, str) and notes.strip():
        try:
            parsed = json.loads(notes)
            if isinstance(parsed, dict):
                parsed_notes = parsed
        except Exception:
            parsed_notes = {}

    repository_type = clean(repo.get("repository_type"))
    source_structure_type = clean(repo.get("source_structure_type") or parsed_notes.get("source_structure_type"))
    created_by = clean(parsed_notes.get("created_by"))
    is_manual = (
        repository_type == "manual_upload_package"
        or source_structure_type == "manual_upload_package"
        or created_by == "manual_upload_staging_1"
    )
    if not is_manual:
        return ""

    for value in (
        repo.get("workflow_mode"),
        parsed_notes.get("workflow_mode"),
        repo.get("mode"),
        parsed_notes.get("mode"),
    ):
        mode = clean(value)
        if mode in {"2d", "3d"}:
            return mode
    return ""

def repository_matches_mode(repo: dict[str, Any] | None, mode: Any) -> bool:
    # MANUAL_UPLOAD_STAGING_2B_MODE_CONTRACT: centralize manual-upload repo mode validation.
    manual_upload_mode = _manual_upload_workflow_mode_from_repository(repo)
    if manual_upload_mode:
        requested_mode = str(mode or "").strip().lower()
        return requested_mode == manual_upload_mode

    normalized = normalize_repository_mode(mode)
    if normalized is None:
        return True
    return repository_mode(repo) == normalized


def filter_repositories_by_mode(repositories: Iterable[dict[str, Any]], mode: Any) -> list[dict[str, Any]]:
    normalized = normalize_repository_mode(mode)
    rows = list(repositories or [])
    if normalized is None:
        return rows
    return [repo for repo in rows if repository_mode(repo) == normalized]


def apply_mode_defaults_to_payload(payload: dict[str, Any], mode: Any) -> dict[str, Any]:
    normalized = normalize_repository_mode(mode)
    result = dict(payload or {})
    if normalized == REPOSITORY_MODE_2D:
        result.setdefault("name", "2D Source Repository")
        result.setdefault("source_structure_type", SOURCE_STRUCTURE_2D)
        result.setdefault("intended_use", INTENDED_USE_2D)
        result.setdefault("workflow_mode", REPOSITORY_MODE_2D)
    elif normalized == REPOSITORY_MODE_3D:
        result.setdefault("name", "3D Source Repository")
        result.setdefault("source_structure_type", SOURCE_STRUCTURE_3D)
        result.setdefault("intended_use", INTENDED_USE_3D)
        result.setdefault("workflow_mode", REPOSITORY_MODE_3D)
    return result


def encode_repository_notes(notes: Any, source_structure_type: Any, intended_use: Any) -> str:
    base = str(notes or "").strip()
    tokens: list[str] = []
    if source_structure_type:
        tokens.append(f"source_structure_type={source_structure_type}")
    if intended_use:
        tokens.append(f"intended_use={intended_use}")
    if not tokens:
        return base
    prefix = "; ".join(tokens)
    if not base:
        return prefix
    if prefix in base:
        return base
    return f"{prefix}; {base}"


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def ensure_default_2d_repository(project_root: Path) -> dict[str, Any]:
    registry_path = project_root / "seismic-viewer-backend/data/registry/repositories.json"
    rows = _load_json(registry_path)
    if not isinstance(rows, list):
        rows = []

    if any(repository_mode(row) == REPOSITORY_MODE_2D for row in rows):
        return {"changed": False, "reason": "2D repository already present", "repository_count": len(rows)}

    backup_root = project_root / "seismic-viewer-backend/data/registry_backups"
    candidates: list[dict[str, Any]] = []
    for path in sorted(backup_root.glob("source_registry_clear_*/repositories.json")):
        try:
            data = _load_json(path)
        except Exception:
            continue
        if isinstance(data, list):
            for row in data:
                if repository_mode(row) == REPOSITORY_MODE_2D:
                    candidate = dict(row)
                    candidate["_restore_source"] = str(path)
                    candidates.append(candidate)

    if candidates:
        preferred = sorted(
            candidates,
            key=lambda row: (
                "2D_Tests_for_backend" not in str(row.get("root_path") or ""),
                str(row.get("updated_at") or row.get("created_at") or ""),
            ),
        )[0]
        restored = {k: v for k, v in preferred.items() if not k.startswith("_")}
        restore_source = preferred.get("_restore_source")
    else:
        restored = {
            "repository_id": "repo_restored_2d_source_repository",
            "name": "2D Source Repository",
            "root_path": str(Path.home() / "Desktop/Seismic_Viewer/TEST_DATA/2D_Tests_for_backend"),
            "repository_type": "local_folder",
            "status": "available",
            "read_only": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        restore_source = "default"

    restored["name"] = restored.get("name") or "2D Source Repository"
    restored["source_structure_type"] = SOURCE_STRUCTURE_2D
    restored["intended_use"] = INTENDED_USE_2D
    restored["workflow_mode"] = REPOSITORY_MODE_2D
    restored["notes"] = encode_repository_notes(
        restored.get("notes"),
        restored.get("source_structure_type"),
        restored.get("intended_use"),
    )
    restored["updated_at"] = datetime.now(timezone.utc).isoformat()
    restored["status"] = restored.get("status") or "available"
    restored["repository_type"] = restored.get("repository_type") or "local_folder"
    restored["read_only"] = True if restored.get("read_only") is None else restored.get("read_only")

    backup_dir = project_root / "seismic-viewer-backend/data/registry_backups" / f"mode_isolation_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    if registry_path.exists():
        (backup_dir / "repositories.before_6n.json").write_text(registry_path.read_text(encoding="utf-8"), encoding="utf-8")

    rows.append(restored)
    _write_json(registry_path, rows)

    return {
        "changed": True,
        "reason": "Restored missing 2D source repository",
        "restore_source": restore_source,
        "repository": restored,
        "repository_count": len(rows),
    }
