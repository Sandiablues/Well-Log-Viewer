from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .repository import VALID_TOOLS
from .rules_repository import DEFAULT_RULES

STANDARDS_SCHEMA_VERSION = "toolbox_ai_standards_v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ToolboxAiStandardsRepository:
    """Small immutable version store for Toolbox AI standards."""

    def __init__(
        self,
        path: Path | str | None = None,
        legacy_rules_path: Path | str | None = None,
    ) -> None:
        runtime = Path(__file__).resolve().parents[3] / "runtime"
        self.path = Path(path) if path is not None else runtime / "toolbox_ai_standards_v1.json"
        self.legacy_rules_path = (
            Path(legacy_rules_path)
            if legacy_rules_path is not None
            else runtime / "toolbox_ai_rules_v1.json"
        )
        self._lock = threading.RLock()

    @staticmethod
    def _tool(tool: str) -> str:
        value = str(tool or "").strip().upper()
        if value not in VALID_TOOLS:
            raise ValueError(f"Unsupported Toolbox AI tool: {value}")
        return value

    @staticmethod
    def _version_record(
        version: int,
        rules: dict[str, Any],
        created_by: str,
        change_note: str,
        *,
        migrated_previous_rules: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "version": int(version),
            "created_at": _utc_now(),
            "created_by": str(created_by or "operator").strip() or "operator",
            "change_note": str(change_note or "").strip(),
            "rules": deepcopy(rules),
            "migrated_previous_rules": deepcopy(migrated_previous_rules)
            if isinstance(migrated_previous_rules, dict)
            else None,
        }

    def _default_payload(self) -> dict[str, Any]:
        return {
            "schema_version": STANDARDS_SCHEMA_VERSION,
            "tools": {
                tool: {
                    "tool": tool,
                    "active_version": 1,
                    "versions": [
                        self._version_record(
                            1,
                            DEFAULT_RULES[tool],
                            "shipped-default",
                            "Initial standard",
                        )
                    ],
                }
                for tool in sorted(VALID_TOOLS)
            },
        }

    def _migrate_legacy_unlocked(self) -> dict[str, Any]:
        payload = self._default_payload()
        if not self.legacy_rules_path.exists():
            return payload
        try:
            legacy = json.loads(self.legacy_rules_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return payload
        tools = legacy.get("tools")
        if not isinstance(tools, dict):
            return payload

        for tool in VALID_TOOLS:
            legacy_record = tools.get(tool)
            if not isinstance(legacy_record, dict):
                continue
            rules = legacy_record.get("rules")
            if not isinstance(rules, dict):
                continue
            previous = legacy_record.get("previous_rules")
            payload["tools"][tool] = {
                "tool": tool,
                "active_version": 1,
                "versions": [
                    {
                        "version": 1,
                        "created_at": str(legacy_record.get("updated_at") or _utc_now()),
                        "created_by": str(legacy_record.get("updated_by") or "legacy-rules-migration"),
                        "change_note": "Migrated active rules into AI Standards Manager",
                        "rules": deepcopy(rules),
                        "migrated_previous_rules": deepcopy(previous) if isinstance(previous, dict) else None,
                    }
                ],
            }
        return payload

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            payload = self._migrate_legacy_unlocked()
            self._write_unlocked(payload)
            return payload

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Toolbox AI standards registry is unreadable: {self.path}") from exc

        if payload.get("schema_version") != STANDARDS_SCHEMA_VERSION or not isinstance(payload.get("tools"), dict):
            raise RuntimeError(f"Unsupported Toolbox AI standards registry: {self.path}")

        for tool in VALID_TOOLS:
            if tool not in payload["tools"]:
                payload["tools"][tool] = {
                    "tool": tool,
                    "active_version": 1,
                    "versions": [
                        self._version_record(1, DEFAULT_RULES[tool], "shipped-default", "Initial standard")
                    ],
                }
        return payload

    def _write_unlocked(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _summary(record: dict[str, Any]) -> dict[str, Any]:
        versions = record.get("versions") or []
        active_version = int(record.get("active_version") or 1)
        active = next(
            (item for item in versions if int(item.get("version") or 0) == active_version),
            versions[-1] if versions else None,
        )
        if active is None:
            raise RuntimeError("AI standards record has no versions")
        return {
            "tool": record["tool"],
            "active_version": active_version,
            "rules": deepcopy(active["rules"]),
            "updated_at": active["created_at"],
            "updated_by": active["created_by"],
            "change_note": active.get("change_note") or "",
            "versions": [
                {
                    "version": int(item["version"]),
                    "created_at": item["created_at"],
                    "created_by": item["created_by"],
                    "change_note": item.get("change_note") or "",
                }
                for item in versions
            ],
        }

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            payload = self._load_unlocked()
            return [self._summary(payload["tools"][tool]) for tool in sorted(VALID_TOOLS)]

    def get_active(self, tool: str) -> dict[str, Any]:
        tool = self._tool(tool)
        with self._lock:
            payload = self._load_unlocked()
            return self._summary(payload["tools"][tool])

    def get_version(self, tool: str, version: int) -> dict[str, Any]:
        tool = self._tool(tool)
        version = int(version)
        with self._lock:
            payload = self._load_unlocked()
            record = payload["tools"][tool]
            item = next(
                (entry for entry in record["versions"] if int(entry.get("version") or 0) == version),
                None,
            )
            if item is None:
                raise ValueError(f"{tool} standard version {version} does not exist")
            return {
                "tool": tool,
                "active_version": int(record["active_version"]),
                **deepcopy(item),
            }


    @staticmethod
    def _payload_references_version(value: Any, tool: str, version: int) -> bool:
        """Return True when an application artifact explicitly references this standard version."""
        if isinstance(value, dict):
            standard_value = value.get("standard_version")
            tool_value = str(value.get("tool") or "").strip().upper()
            if (
                isinstance(standard_value, (int, float, str))
                and str(standard_value).strip().isdigit()
                and int(standard_value) == version
                and (not tool_value or tool_value == tool)
            ):
                return True
            return any(
                ToolboxAiStandardsRepository._payload_references_version(child, tool, version)
                for child in value.values()
            )
        if isinstance(value, list):
            return any(
                ToolboxAiStandardsRepository._payload_references_version(child, tool, version)
                for child in value
            )
        return False

    def _reference_paths_unlocked(self, tool: str, version: int) -> list[str]:
        """Find retained runtime JSON artifacts that explicitly reference a standards version."""
        runtime = self.path.parent
        excluded = {self.path.resolve(), self.legacy_rules_path.resolve()}
        references: list[str] = []
        if not runtime.exists():
            return references

        for candidate in runtime.rglob("*.json"):
            try:
                resolved = candidate.resolve()
                if resolved in excluded or not candidate.is_file():
                    continue
                if candidate.stat().st_size > 25 * 1024 * 1024:
                    continue
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            if self._payload_references_version(payload, tool, version):
                try:
                    references.append(str(candidate.relative_to(runtime)))
                except ValueError:
                    references.append(str(candidate))
        return sorted(set(references))

    def delete_version(self, tool: str, version: int) -> dict[str, Any]:
        """Delete an inactive, unreferenced standards version without renumbering."""
        tool = self._tool(tool)
        version = int(version)

        with self._lock:
            payload = self._load_unlocked()
            record = payload["tools"][tool]
            active_version = int(record.get("active_version") or 1)

            if version == active_version:
                raise ValueError(
                    f"{tool} standard version {version} is active and cannot be deleted"
                )

            index = next(
                (
                    idx
                    for idx, item in enumerate(record.get("versions") or [])
                    if int(item.get("version") or 0) == version
                ),
                None,
            )
            if index is None:
                raise ValueError(f"{tool} standard version {version} does not exist")

            references = self._reference_paths_unlocked(tool, version)
            if references:
                preview = ", ".join(references[:3])
                suffix = "" if len(references) <= 3 else f" (+{len(references) - 3} more)"
                raise ValueError(
                    f"{tool} standard version {version} is referenced by retained audit/qualification "
                    f"artifacts and cannot be deleted: {preview}{suffix}"
                )

            del record["versions"][index]
            self._write_unlocked(payload)
            return self._summary(record)

    def save_new_version(
        self,
        tool: str,
        rules: dict[str, Any],
        *,
        created_by: str | None = None,
        change_note: str | None = None,
    ) -> dict[str, Any]:
        tool = self._tool(tool)
        if not isinstance(rules, dict):
            raise ValueError("rules must be a JSON object")

        with self._lock:
            payload = self._load_unlocked()
            record = payload["tools"][tool]
            next_version = max(int(item["version"]) for item in record["versions"]) + 1
            record["versions"].append(
                self._version_record(
                    next_version,
                    rules,
                    created_by or "operator",
                    change_note or "",
                )
            )
            record["active_version"] = next_version
            self._write_unlocked(payload)
            return self._summary(record)

    def restore_as_new_version(
        self,
        tool: str,
        source_version: int,
        *,
        created_by: str | None = None,
        change_note: str | None = None,
    ) -> dict[str, Any]:
        source = self.get_version(tool, source_version)
        note = str(change_note or "").strip() or f"Restored version {int(source_version)} as new active version"
        return self.save_new_version(
            tool,
            source["rules"],
            created_by=created_by or "operator",
            change_note=note,
        )
