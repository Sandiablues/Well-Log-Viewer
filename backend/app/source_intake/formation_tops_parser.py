"""Strict governed parser for WLV formation-tops CSV intake."""
from __future__ import annotations
import csv
from pathlib import Path
from .models import SourceIntakeFormationTop, SourceIntakeFormationTopsPayload

class FormationTopsParseError(ValueError):
    pass

def _norm(value: str) -> str:
    return " ".join((value or "").replace("_", " ").strip().casefold().split())

ALIASES = {
    "wellbore": {"wellbore", "well", "well name"},
    "pick_status": {"pick status", "status"},
    "group": {"group", "stratigraphic group"},
    "marker_name": {"formation or marker", "formation", "marker", "marker name"},
    "marker_type": {"marker type", "pick type"},
    "md": {"md (m rt)", "md m rt", "md", "measured depth"},
    "tvd": {"tvd (m rt)", "tvd m rt", "tvd"},
    "tvdss": {"tvdss (m msl)", "tvdss m msl", "tvdss", "tvd msl"},
    "uncertainty": {"uncertainty (+/- m)", "uncertainty m", "uncertainty"},
    "source_document": {"source document", "document"},
    "source_page": {"source page", "page"},
}

def _mapping(headers: list[str]) -> dict[str, str]:
    normalized = {_norm(h): h for h in headers}
    out = {}
    for field, aliases in ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                out[field] = normalized[alias]
                break
    return out

def looks_like_formation_tops_csv(path: Path) -> bool:
    if path.suffix.lower() != ".csv":
        return False
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            headers = next(reader, [])
        m = _mapping(headers)
        return all(k in m for k in ("wellbore", "marker_name", "md"))
    except Exception:
        return False

def _float(row, key, mapping, required=False):
    raw = (row.get(mapping.get(key, "")) or "").strip()
    if not raw:
        if required:
            raise FormationTopsParseError(f"Required numeric field is blank: {key}")
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError as exc:
        raise FormationTopsParseError(f"Invalid numeric value for {key}: {raw}") from exc

def parse_formation_tops_csv(path: Path) -> SourceIntakeFormationTopsPayload:
    try:
        f = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise FormationTopsParseError(str(exc)) from exc
    with f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        mapping = _mapping(headers)
        missing = [k for k in ("wellbore", "marker_name", "md") if k not in mapping]
        if missing:
            raise FormationTopsParseError("Missing required formation-tops columns: " + ", ".join(missing))
        tops=[]; wellbores=set(); warnings=[]
        for line_no,row in enumerate(reader, start=2):
            if not any((v or "").strip() for v in row.values()):
                continue
            wellbore=(row.get(mapping["wellbore"]) or "").strip()
            marker=(row.get(mapping["marker_name"]) or "").strip()
            if not wellbore or not marker:
                raise FormationTopsParseError(f"Line {line_no}: wellbore and marker name are required")
            wellbores.add(wellbore)
            page=_float(row,"source_page",mapping)
            tops.append(SourceIntakeFormationTop(
                group=(row.get(mapping.get("group", "")) or "").strip() or None,
                marker_name=marker,
                marker_type=(row.get(mapping.get("marker_type", "")) or "Formation top").strip() or "Formation top",
                md_m_rt=_float(row,"md",mapping,required=True),
                tvd_m_rt=_float(row,"tvd",mapping),
                tvdss_m_msl=_float(row,"tvdss",mapping),
                uncertainty_m=_float(row,"uncertainty",mapping),
                pick_status=(row.get(mapping.get("pick_status", "")) or "Prognosed").strip() or "Prognosed",
                source_document=(row.get(mapping.get("source_document", "")) or "").strip() or None,
                source_page=int(page) if page is not None else None,
            ))
        if not tops:
            raise FormationTopsParseError("Formation-tops CSV contains no data rows")
        if len(wellbores) != 1:
            raise FormationTopsParseError("Mixed-well formation-tops files are not supported: " + ", ".join(sorted(wellbores)))
        md_values=[t.md_m_rt for t in tops]
        if md_values != sorted(md_values):
            warnings.append("Formation tops are not ordered by increasing MD.")
        return SourceIntakeFormationTopsPayload(wellbore=next(iter(wellbores)), row_count=len(tops), tops=tops, warnings=warnings)
