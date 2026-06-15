"""Backend-owned runtime seed trajectory resolver for WBV.

This resolver is intentionally narrow. It supports controlled prototype seed
trajectory packages that were extracted and normalized before runtime. WBV still
never parses raw DLIS/LIS files in the live viewer path and it never fabricates a
trajectory from frontend or curve state.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.inventory.models import ManagedWellRecord

_REGISTRY_PATH = Path(__file__).with_name("trajectory_seed_registry.json")
_FIXTURE_DIR = Path(__file__).with_name("fixtures")


def resolve_seed_trajectory_package(record: ManagedWellRecord) -> dict[str, Any]:
    """Return a backend-owned seed trajectory package for a matched record.

    Empty dict means no governed seed package applies. Callers must continue to
    report missing_survey in that case.
    """

    for entry in _load_registry().get("packages", []):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status") or "").strip().lower() not in {"prototype_seed", "approved"}:
            continue
        selectors = entry.get("selectors")
        if not isinstance(selectors, dict) or not _matches_record(record, selectors):
            continue
        package_file = str(entry.get("package_file") or "").strip()
        if not package_file:
            continue
        package_path = (_FIXTURE_DIR / package_file).resolve()
        if _FIXTURE_DIR.resolve() not in package_path.parents:
            continue
        if not package_path.exists():
            continue
        raw = json.loads(package_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        raw.setdefault("runtime_seed_package_id", str(entry.get("package_id") or ""))
        raw.setdefault("runtime_seed_status", str(entry.get("status") or "prototype_seed"))
        raw.setdefault("runtime_seed_reason", str(entry.get("reason") or ""))
        return raw
    return {}


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Any]:
    if not _REGISTRY_PATH.exists():
        return {"packages": []}
    raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {"packages": []}


def _matches_record(record: ManagedWellRecord, selectors: dict[str, Any]) -> bool:
    text_values = {
        "well_names": record.well_name,
        "well_ids": record.well_id,
        "managed_well_ids": record.managed_well_id,
    }
    for selector_key, record_value in text_values.items():
        allowed = selectors.get(selector_key)
        if isinstance(allowed, list) and _matches_any(record_value, allowed):
            return True

    suffix_values = {
        "well_id_suffixes": record.well_id,
        "managed_well_id_suffixes": record.managed_well_id,
    }
    for selector_key, record_value in suffix_values.items():
        allowed = selectors.get(selector_key)
        if isinstance(allowed, list) and _endswith_any(record_value, allowed):
            return True

    return False


def _matches_any(value: str | None, candidates: list[Any]) -> bool:
    normalized_value = _normalize(value)
    return bool(normalized_value) and any(normalized_value == _normalize(candidate) for candidate in candidates)


def _endswith_any(value: str | None, candidates: list[Any]) -> bool:
    normalized_value = _normalize(value)
    return bool(normalized_value) and any(normalized_value.endswith(_normalize(candidate)) for candidate in candidates if _normalize(candidate))


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
