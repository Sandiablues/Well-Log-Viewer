from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict
import json
import shutil

from app.services.repository_registry_service import REGISTRY_DIR


SOURCE_REGISTRY_FILES = [
    "repositories.json",
    "packages.json",
    "lines.json",
    "segy_files.json",
    "documents.json",
    "staged_source_items.json",
]


def _count_json_value(path: Path) -> int | str:
    if not path.exists():
        return "missing"

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"unreadable: {exc}"

    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return f"dict:{len(value.keys())}"
    return type(value).__name__


def clear_source_registry(*, confirm: bool = False) -> Dict[str, Any]:
    """
    Clear Source Intake / External Source Registry state only.

    This does not delete original SEG-Y/documents, managed datasets, Zarr,
    jobs, reports, or converted outputs.
    """
    if not confirm:
        raise ValueError("Clear source registry requires confirm=true")

    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = REGISTRY_DIR.parent / "registry_backups" / f"source_registry_clear_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    before: Dict[str, Any] = {}
    after: Dict[str, Any] = {}
    cleared: list[str] = []
    missing_created: list[str] = []

    for name in SOURCE_REGISTRY_FILES:
        path = REGISTRY_DIR / name
        before[name] = _count_json_value(path)

        if path.exists():
            shutil.copy2(path, backup_dir / name)
        else:
            missing_created.append(name)

        path.write_text("[]\n", encoding="utf-8")
        cleared.append(name)
        after[name] = _count_json_value(path)

    restore_script = backup_dir / "RESTORE_SOURCE_REGISTRY_CLEAR.sh"
    restore_script.write_text(
        "#!/bin/bash\n"
        "set -e\n\n"
        f'BACKUP="{backup_dir}"\n'
        f'REGISTRY="{REGISTRY_DIR}"\n\n'
        "for f in repositories.json packages.json lines.json segy_files.json documents.json staged_source_items.json; do\n"
        '  if [ -f "$BACKUP/$f" ]; then\n'
        '    cp "$BACKUP/$f" "$REGISTRY/$f"\n'
        '    echo "Restored $f"\n'
        "  fi\n"
        "done\n\n"
        "echo\n"
        'echo "Restored source registry from:"\n'
        'echo "$BACKUP"\n'
        'echo "Restart backend after restore."\n',
        encoding="utf-8",
    )
    restore_script.chmod(0o755)

    return {
        "status": "ok",
        "cleared": cleared,
        "missing_created": missing_created,
        "before": before,
        "after": after,
        "backup_dir": str(backup_dir),
        "restore_script": str(restore_script),
        "scope": "source_intake_external_source_registry_only",
    }
