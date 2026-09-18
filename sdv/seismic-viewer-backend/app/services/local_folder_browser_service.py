from __future__ import annotations

from pathlib import Path
from typing import Any
import os


def _home() -> Path:
    return Path.home().resolve()


def _default_start_path() -> Path:
    candidates = [
        _home() / "Desktop",
        _home() / "Documents",
        _home(),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
    return _home()


def _folder_roots() -> list[dict[str, str]]:
    roots: list[dict[str, str]] = []

    candidates = [
        ("Home", _home()),
        ("Desktop", _home() / "Desktop"),
        ("Documents", _home() / "Documents"),
        ("Downloads", _home() / "Downloads"),
        ("Applications", Path("/Applications")),
        ("Volumes", Path("/Volumes")),
    ]

    seen: set[str] = set()

    for name, path in candidates:
        try:
            resolved = path.resolve()
            if not resolved.exists() or not resolved.is_dir():
                continue
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            roots.append({
                "name": name,
                "path": key,
                "kind": "root",
            })
        except Exception:
            continue

    try:
        volumes = Path("/Volumes")
        if volumes.exists() and volumes.is_dir():
            for child in sorted(volumes.iterdir(), key=lambda p: p.name.lower()):
                try:
                    if child.is_dir():
                        key = str(child.resolve())
                        if key not in seen:
                            seen.add(key)
                            roots.append({
                                "name": child.name,
                                "path": key,
                                "kind": "volume",
                            })
                except Exception:
                    continue
    except Exception:
        pass

    return roots


def _resolve_browse_path(path_value: str | None) -> Path:
    if not path_value or not str(path_value).strip():
        return _default_start_path()

    expanded = Path(os.path.expanduser(str(path_value).strip()))
    if not expanded.is_absolute():
        expanded = _home() / expanded

    resolved = expanded.resolve()

    if not resolved.exists():
        raise FileNotFoundError(f"Folder does not exist: {resolved}")

    if not resolved.is_dir():
        raise NotADirectoryError(f"Path is not a folder: {resolved}")

    return resolved


def _file_role(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix in {".sgy", ".segy"}:
        return "segy"

    if suffix in {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".rtf", ".las", ".nav", ".ukooa", ".p190"}:
        return "document"

    return "other"


def list_local_folders(path_value: str | None = None) -> dict[str, Any]:
    """
    Local desktop folder/content browser for Source Intake.

    This lists child folders and files for inspection only. It does not
    scan/register/import data. The scan itself remains owned by
    repository_package_scanner_service.
    """
    current = _resolve_browse_path(path_value)
    parent = current.parent if current.parent != current else None

    entries: list[dict[str, Any]] = []

    try:
        children = list(current.iterdir())
    except PermissionError as exc:
        raise PermissionError(f"Permission denied: {current}") from exc

    for child in children:
        try:
            name = child.name
            hidden = name.startswith(".")

            # Keep hidden folders/files out by default to reduce noise and avoid runtime/dev internals.
            if hidden:
                continue

            resolved = child.resolve()

            if child.is_dir():
                entries.append({
                    "name": name,
                    "path": str(resolved),
                    "kind": "folder",
                })
                continue

            if child.is_file():
                try:
                    size_bytes = child.stat().st_size
                except OSError:
                    size_bytes = None

                entries.append({
                    "name": name,
                    "path": str(resolved),
                    "kind": "file",
                    "extension": child.suffix.lower(),
                    "size_bytes": size_bytes,
                    "file_role": _file_role(child),
                })
        except PermissionError:
            continue
        except OSError:
            continue

    entries.sort(key=lambda item: (0 if item.get("kind") == "folder" else 1, item["name"].lower()))

    return {
        "status": "ok",
        "current_path": str(current),
        "parent_path": str(parent) if parent else None,
        "roots": _folder_roots(),
        "entries": entries,
    }
