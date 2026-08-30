"""Backend-owned Curve Fill paint catalogue and managed raster registry."""
from __future__ import annotations

import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

class PatternPaint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    pattern_uid: str
    label: str
    kind: str

class RasterPaint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    raster_asset_uid: str
    label: str
    managed_well_uid: str
    image_url: str
    top_depth: float
    base_depth: float
    depth_unit: str
    horizontal_fit: str = "cover"

_BASE_PATTERNS = (
    PatternPaint(pattern_uid="hatch-45-v1", label="Diagonal hatch", kind="hatch_45"),
    PatternPaint(pattern_uid="crosshatch-v1", label="Crosshatch", kind="crosshatch"),
    PatternPaint(pattern_uid="dots-v1", label="Dots", kind="dots"),
    PatternPaint(pattern_uid="bricks-v1", label="Bricks", kind="bricks"),
    PatternPaint(pattern_uid="stipple-v1", label="Stipple", kind="stipple"),
    PatternPaint(pattern_uid="lithology-column-v1", label="Loaded lithology column", kind="lithology_column"),
)

def lithology_catalogue_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "data"
        / "knowledge"
        / "lithology"
        / "lithology-catalogue.json"
    )

def load_lithology_patterns() -> tuple[PatternPaint, ...]:
    path = lithology_catalogue_path()
    if not path.is_file():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        PatternPaint(
            pattern_uid=item["id"],
            label=f'{item["name"]} · FGDC {item["fgdcCode"]}',
            kind="lithology_svg",
        )
        for item in payload.get("entries", ())
        if item.get("status") == "active"
    )

PATTERNS = _BASE_PATTERNS + load_lithology_patterns()

def raster_registry_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "curve_fill" / "raster_assets.json"

def load_rasters(managed_well_uid: str) -> tuple[RasterPaint, ...]:
    path = raster_registry_path()
    if not path.exists():
        return ()
    payload = json.loads(path.read_text())
    assets = tuple(RasterPaint.model_validate(item) for item in payload.get("assets", ()))
    return tuple(item for item in assets if item.managed_well_uid == managed_well_uid)

def pattern_by_uid(uid: str) -> PatternPaint:
    item = next((x for x in PATTERNS if x.pattern_uid == uid), None)
    if item is None:
        raise ValueError(f"Unknown approved pattern_uid: {uid}")
    return item

def raster_by_uid(managed_well_uid: str, uid: str) -> RasterPaint:
    item = next((x for x in load_rasters(managed_well_uid) if x.raster_asset_uid == uid), None)
    if item is None:
        raise ValueError(f"Unknown or incompatible raster_asset_uid: {uid}")
    if item.base_depth <= item.top_depth:
        raise ValueError("Raster asset requires base_depth greater than top_depth")
    return item
