"""Managed lithology catalogue routes for the WLV Knowledge Repository."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator

router = APIRouter(prefix="/api/wlv/knowledge/lithology", tags=["wlv-knowledge-lithology"])
_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "lithology"
_CATALOGUE = _DATA_DIR / "lithology-catalogue.json"
_PALETTE = _DATA_DIR / "lithology-colour-palette.json"
_PATTERN_DIR = _DATA_DIR / "patterns"
_AUDIT_LOG = _DATA_DIR / "lithology-catalogue-audit.jsonl"
_BACKUP_DIR = _DATA_DIR / "backups"
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9:_-]{2,79}$")
_WRITE_LOCK = threading.RLock()


class PatternReference(BaseModel):
    asset: str
    defaultScale: float = Field(default=1.0, gt=0.0, le=100.0)

    @field_validator("asset")
    @classmethod
    def validate_asset(cls, value: str) -> str:
        name = Path(value.strip()).name
        if not name.lower().endswith(".svg"):
            raise ValueError("Pattern asset must be an SVG")
        return f"patterns/{name}"


class LithologyWriteRequest(BaseModel):
    id: str
    fgdcCode: int = Field(ge=1, le=999999)
    name: str = Field(min_length=1, max_length=160)
    formalName: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=2000)
    category: str = Field(min_length=1, max_length=80)
    subcategory: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field(default_factory=list, max_length=100)
    pattern: PatternReference
    defaultBackground: str
    defaultPattern: str
    sourceStandard: str = Field(min_length=1, max_length=160)
    sourceSeries: str = Field(default="custom", max_length=160)
    sourceRepository: str = Field(default="MultiViewer", max_length=240)
    status: Literal["active", "deprecated"] = "active"

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip().lower().replace(" ", "-")
        if not _SAFE_ID.fullmatch(normalized):
            raise ValueError("ID must use lowercase letters, numbers, colon, underscore or hyphen")
        return normalized

    @field_validator("name", "formalName", "description", "category", "subcategory", "sourceStandard", "sourceSeries", "sourceRepository")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("Value cannot be blank")
        return cleaned

    @field_validator("defaultBackground", "defaultPattern")
    @classmethod
    def validate_colour(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not _HEX.fullmatch(normalized):
            raise ValueError("Colours must use #RRGGBB")
        return normalized

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, values: list[str]) -> list[str]:
        unique: dict[str, str] = {}
        for raw in values:
            value = " ".join(raw.strip().split())
            if value:
                unique.setdefault(value.casefold(), value)
        return list(unique.values())

    @model_validator(mode="after")
    def validate_colours(self) -> "LithologyWriteRequest":
        if self.defaultBackground == self.defaultPattern:
            raise ValueError("Background and pattern colours must differ")
        return self


@lru_cache(maxsize=1)
def _catalogue() -> dict[str, Any]:
    return json.loads(_CATALOGUE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _palette() -> dict[str, Any]:
    return json.loads(_PALETTE.read_text(encoding="utf-8"))


def _invalidate() -> None:
    _catalogue.cache_clear()
    _palette.cache_clear()


def _entry(lithology_id: str) -> dict[str, Any]:
    for item in _catalogue().get("entries", []):
        if item.get("id") == lithology_id:
            return item
    raise HTTPException(status_code=404, detail="Lithology not found")


def _pattern_path(asset: str) -> Path:
    name = Path(asset).name
    path = (_PATTERN_DIR / name).resolve()
    if path.parent != _PATTERN_DIR.resolve():
        raise HTTPException(status_code=422, detail="Invalid pattern asset")
    if not path.is_file():
        raise HTTPException(status_code=422, detail="Pattern asset not found")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _next_version(current: str) -> str:
    parts = current.split(".")
    try:
        values = [int(part) for part in parts]
    except ValueError:
        return f"{current}.1"
    while len(values) < 3:
        values.append(0)
    values[-1] += 1
    return ".".join(str(value) for value in values)


def _atomic_write(document: dict[str, Any], *, action: str, lithology_id: str, before: dict[str, Any] | None, after: dict[str, Any] | None) -> None:
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = _BACKUP_DIR / f"lithology-catalogue-{stamp}.json"
    shutil.copy2(_CATALOGUE, backup)

    document["entryCount"] = len(document.get("entries", []))
    document["version"] = _next_version(str(document.get("version") or "1.0.0"))
    document["updatedAt"] = datetime.now(timezone.utc).isoformat()

    fd, temp_name = tempfile.mkstemp(prefix="lithology-catalogue-", suffix=".json", dir=str(_DATA_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, _CATALOGUE)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

    audit = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "lithologyId": lithology_id,
        "catalogueVersion": document["version"],
        "backup": str(backup),
        "before": before,
        "after": after,
    }
    with _AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(audit, ensure_ascii=False, sort_keys=True) + "\n")
    _invalidate()


def _build_entry(payload: LithologyWriteRequest) -> dict[str, Any]:
    pattern_path = _pattern_path(payload.pattern.asset)
    palette_ids = {
        str(item.get("hex", "")).upper(): str(item.get("id", ""))
        for item in _palette().get("colors", [])
    }
    return {
        "id": payload.id,
        "fgdcCode": payload.fgdcCode,
        "name": payload.name,
        "formalName": payload.formalName,
        "description": payload.description,
        "category": payload.category,
        "subcategory": payload.subcategory,
        "aliases": payload.aliases,
        "pattern": {
            "asset": payload.pattern.asset,
            "format": "image/svg+xml",
            "sha256": _sha256(pattern_path),
            "defaultScale": payload.pattern.defaultScale,
        },
        "colors": {
            "defaultBackgroundPaletteId": palette_ids.get(payload.defaultBackground, "custom"),
            "defaultPatternPaletteId": palette_ids.get(payload.defaultPattern, "custom"),
            "defaultBackground": payload.defaultBackground,
            "defaultPattern": payload.defaultPattern,
        },
        "source": {
            "standard": payload.sourceStandard,
            "series": payload.sourceSeries,
            "repository": payload.sourceRepository,
        },
        "status": payload.status,
    }


def _validate_uniqueness(entries: list[dict[str, Any]], candidate: dict[str, Any], *, original_id: str | None = None) -> None:
    for item in entries:
        if original_id is not None and item.get("id") == original_id:
            continue
        if item.get("id") == candidate["id"]:
            raise HTTPException(status_code=409, detail="Lithology ID already exists")
        if int(item.get("fgdcCode", -1)) == int(candidate["fgdcCode"]):
            raise HTTPException(status_code=409, detail="FGDC/custom code already exists")
        if str(item.get("name", "")).casefold() == candidate["name"].casefold():
            raise HTTPException(status_code=409, detail="Lithology name already exists")


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "wlv-kr-lithology",
        "catalogueVersion": _catalogue().get("version"),
        "entryCount": len(_catalogue().get("entries", [])),
        "colorCount": len(_palette().get("colors", [])),
    }


@router.get("/catalogue")
def catalogue() -> dict[str, Any]:
    return _catalogue()


@router.get("/palette")
def palette() -> dict[str, Any]:
    return _palette()


@router.get("/patterns")
def patterns() -> dict[str, Any]:
    return {
        "patterns": [
            {"asset": f"patterns/{path.name}", "name": path.stem}
            for path in sorted(_PATTERN_DIR.glob("*.svg"), key=lambda item: item.name.casefold())
        ]
    }


@router.get("/entries/{lithology_id}")
def detail(lithology_id: str) -> dict[str, Any]:
    return _entry(lithology_id)


@router.post("/entries", status_code=status.HTTP_201_CREATED)
def create_entry(payload: LithologyWriteRequest) -> dict[str, Any]:
    with _WRITE_LOCK:
        document = json.loads(_CATALOGUE.read_text(encoding="utf-8"))
        entries = document.setdefault("entries", [])
        candidate = _build_entry(payload)
        _validate_uniqueness(entries, candidate)
        entries.append(candidate)
        entries.sort(key=lambda item: (int(item.get("fgdcCode", 999999)), str(item.get("name", "")).casefold()))
        _atomic_write(document, action="create", lithology_id=candidate["id"], before=None, after=candidate)
        return candidate


@router.put("/entries/{lithology_id}")
def update_entry(lithology_id: str, payload: LithologyWriteRequest) -> dict[str, Any]:
    with _WRITE_LOCK:
        document = json.loads(_CATALOGUE.read_text(encoding="utf-8"))
        entries = document.setdefault("entries", [])
        index = next((i for i, item in enumerate(entries) if item.get("id") == lithology_id), None)
        if index is None:
            raise HTTPException(status_code=404, detail="Lithology not found")
        before = entries[index]
        candidate = _build_entry(payload)
        _validate_uniqueness(entries, candidate, original_id=lithology_id)
        entries[index] = candidate
        entries.sort(key=lambda item: (int(item.get("fgdcCode", 999999)), str(item.get("name", "")).casefold()))
        _atomic_write(document, action="update", lithology_id=lithology_id, before=before, after=candidate)
        return candidate


@router.delete("/entries/{lithology_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(lithology_id: str) -> Response:
    with _WRITE_LOCK:
        document = json.loads(_CATALOGUE.read_text(encoding="utf-8"))
        entries = document.setdefault("entries", [])
        index = next((i for i, item in enumerate(entries) if item.get("id") == lithology_id), None)
        if index is None:
            raise HTTPException(status_code=404, detail="Lithology not found")
        before = entries.pop(index)
        # Pattern assets are catalogue resources and are never deleted by this endpoint.
        # This prevents shared or standard SVG assets from being removed accidentally.
        _atomic_write(document, action="delete", lithology_id=lithology_id, before=before, after=None)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/entries/{lithology_id}/pattern.svg")
def pattern(lithology_id: str, background: str | None = Query(default=None), foreground: str | None = Query(default=None)) -> Response:
    item = _entry(lithology_id)
    path = _pattern_path(item["pattern"]["asset"])

    bg = background or item["colors"]["defaultBackground"]
    fg = foreground or item["colors"]["defaultPattern"]
    if not _HEX.fullmatch(bg) or not _HEX.fullmatch(fg):
        raise HTTPException(status_code=422, detail="Colors must use #RRGGBB")

    svg = path.read_text(encoding="utf-8")
    svg = re.sub(r"^\s*<\?xml[^>]*>\s*", "", svg, count=1)
    svg = re.sub(r"<metadata\b.*?</metadata>\s*", "", svg, flags=re.DOTALL)
    svg = re.sub(r"var\(--lithology-outline,\s*#[0-9A-Fa-f]{6}\)", fg, svg)
    svg = re.sub(r"var\(--lithology-fill,\s*(?:transparent|#[0-9A-Fa-f]{6})\)", bg, svg)
    svg = re.sub(r"var\(--lithology-outline-width,\s*([0-9.]+)\)", r"\1", svg)

    root_match = re.search(r"<svg\b[^>]*>", svg)
    if root_match is None:
        raise HTTPException(status_code=500, detail="Pattern asset has no SVG root element")
    root_tag = root_match.group(0)
    view_box_match = re.search(r'viewBox="([^"]+)"', root_tag)
    if view_box_match and len(view_box_match.group(1).split()) == 4:
        x, y, width, height = view_box_match.group(1).split()
    else:
        x = y = "0"
        width_match = re.search(r'width="([^"]+)"', root_tag)
        height_match = re.search(r'height="([^"]+)"', root_tag)
        width = width_match.group(1) if width_match else "100%"
        height = height_match.group(1) if height_match else "100%"
    background_rect = f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{bg}" stroke="none"/>'
    svg = svg[:root_match.end()] + background_rect + svg[root_match.end():]
    try:
        ET.fromstring(svg)
    except ET.ParseError as exc:
        raise HTTPException(status_code=500, detail=f"Pattern SVG is invalid after rendering: {exc}") from exc

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache", "X-Content-Type-Options": "nosniff"},
    )
