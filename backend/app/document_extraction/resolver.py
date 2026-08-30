from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

from schema import FIELD_RULES, FieldRule

AUTHORITY_CAPTION = "multiviewer_schema_authority"


def clean(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", text)


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).casefold()).strip()


ALIASES: list[tuple[str, FieldRule]] = sorted(
    ((norm(alias), rule) for rule in FIELD_RULES for alias in rule.aliases),
    key=lambda item: len(item[0]),
    reverse=True,
)
ALIAS_MAP = {alias: rule for alias, rule in ALIASES}


@dataclass
class Candidate:
    field_key: str
    output_label: str
    value: str
    page_number: int
    table_id: str | None
    row: int | None
    column: int | None
    source_label: str
    source_kind: str
    coordinate_context: str | None
    status: str
    confidence: float
    evidence: str


def detect_status(text: str) -> str:
    n = norm(text)
    if any(x in n for x in ("actual", "as drilled", "as built", "end of well", "completed")):
        return "actual"
    if any(x in n for x in ("planned", "proposed", "forecast", "program", "programme")):
        return "planned"
    return "unknown"


def detect_coordinate_context(text: str) -> str | None:
    n = norm(text)
    for context, tokens in (
        ("wellhead", ("wellhead", "surface location", "surface position")),
        ("slot_centre", ("slot centre", "slot center")),
        ("site", ("site position", "site coordinates")),
        ("structure_centre", ("structure centre", "structure center")),
        ("bottomhole", ("bottomhole", "bottom hole")),
        ("target", ("target position", "target coordinates")),
    ):
        if any(token in n for token in tokens):
            return context
    return None


def strip_trailing_label(value: str) -> str:
    result = clean(value)
    n = norm(result)
    for alias, _rule in ALIASES:
        if not alias:
            continue
        if n == alias:
            return ""
        if n.endswith(" " + alias):
            words = result.split()
            alias_words = alias.split()
            if len(words) > len(alias_words):
                return clean(" ".join(words[:-len(alias_words)]))
    return result


def parse_number(value: str) -> float | None:
    text = clean(value).replace(" ", "")
    if not text:
        return None
    if text.count(",") == 1 and "." not in text:
        left, right = text.split(",", 1)
        text = left + "." + right if len(right) <= 3 else left + right
    else:
        text = text.replace(",", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def unit_from(value: str, default: str | None = None) -> str | None:
    n = norm(value)
    if re.search(r"\bft\b|feet|foot", n):
        return "ft"
    if re.search(r"\bm\b|metre|meter", n):
        return "m"
    return default


def fmt_num(number: float, max_decimals: int = 3) -> str:
    return f"{number:.{max_decimals}f}".rstrip("0").rstrip(".")


def validate_value(rule: FieldRule, raw_value: str, context_text: str) -> str | None:
    value = strip_trailing_label(raw_value).strip(" :-|")
    if not value:
        return None
    n = norm(value)
    context_n = norm(context_text)
    if any(token in context_n for token in rule.rejected_context):
        return None
    if rule.required_context and not any(token in context_n for token in rule.required_context):
        return None
    kind = rule.value_kind
    if kind == "well_id":
        if len(value) > 80 or not re.search(r"[A-Za-z0-9]", value): return None
    elif kind == "identifier":
        if len(value) > 80 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./_ -]{0,79}", value): return None
    elif kind == "organization":
        if len(value) < 3 or len(value) > 120 or re.fullmatch(r"[A-Z]{2,4}", value): return None
    elif kind == "country":
        if len(value) < 3 or len(value) > 60 or any(ch.isdigit() for ch in value): return None
    elif kind == "status":
        if len(value) > 80: return None
    elif kind in {"depth", "elevation", "offset"}:
        number = parse_number(value)
        if number is None: return None
        if kind == "depth" and not (-1000 <= number <= 30000): return None
        if kind == "elevation" and not (-1000 <= number <= 3000): return None
        if kind == "offset" and not (-100000 <= number <= 100000): return None
        unit = unit_from(value, "m")
        value = f"{fmt_num(number)} {unit}"
    elif kind == "northing":
        number = parse_number(value)
        if number is None or not (-10_000_000 <= number <= 10_000_000): return None
        value = f"{fmt_num(number, 2)} {unit_from(value, 'm')}"
    elif kind == "easting":
        number = parse_number(value)
        if number is None or not (-10_000_000 <= number <= 10_000_000): return None
        value = f"{fmt_num(number, 2)} {unit_from(value, 'm')}"
    elif kind == "latitude":
        if not (re.search(r"[NS]", value, re.I) or (parse_number(value) is not None and -90 <= parse_number(value) <= 90)): return None
    elif kind == "longitude":
        if not (re.search(r"[EW]", value, re.I) or (parse_number(value) is not None and -180 <= parse_number(value) <= 180)): return None
    elif kind == "utm_zone":
        match = re.search(r"\b(?:zone\s*)?(\d{1,2}\s*[C-HJ-NP-X]?)\b", value, re.I)
        if not match: return None
        value = re.sub(r"\s+", "", match.group(1)).upper()
    elif kind == "epsg":
        match = re.search(r"\b(?:EPSG\s*[:#]?\s*)?(\d{4,6})\b", value, re.I)
        if not match: return None
        value = match.group(1)
    elif kind == "north_reference":
        match = re.search(r"\b(grid|true|magnetic)\b", value, re.I)
        if not match: return None
        value = match.group(1).title()
    elif kind == "angle":
        number = parse_number(value)
        if number is None or not (-360 <= number <= 360): return None
        value = f"{fmt_num(number, 2)}°"
    elif kind == "integer":
        number = parse_number(value)
        if number is None or number < 0 or number > 1_000_000: return None
        value = str(int(round(number)))
    elif kind == "depth_unit":
        unit = unit_from(value)
        if not unit: return None
        value = unit
    elif kind == "method":
        if len(value) > 100: return None
        if "minimum curvature" in n: value = "Minimum Curvature"
    elif kind == "reference":
        if len(value) > 160 or not re.search(r"rt|rkb|kb|rotary table|kelly bushing|msl|mean sea level", n): return None
    else:
        if len(value) > 180: return None
    return clean(value)


def recognized_label(cell: str) -> tuple[FieldRule, str] | None:
    n = norm(cell).rstrip()
    if n in ALIAS_MAP:
        return ALIAS_MAP[n], cell
    # Normalization already removes punctuation. Prefix matching is deliberately
    # forbidden because values such as "Zone 31N" must never become labels.
    return None


def table_context(table: dict[str, Any], page_text: str) -> str:
    rows = table.get("rows") or []
    flat = " ".join(clean(v) for row in rows for v in row if clean(v))
    return clean(page_text + " " + flat)


def extract_table_candidates(pages: list[dict[str, Any]], tables: list[dict[str, Any]]) -> list[Candidate]:
    page_texts = {int(p.get("page_number") or 0): clean(p.get("text") or "") for p in pages}
    out: list[Candidate] = []
    for table in tables:
        page = int(table.get("page_number") or 0)
        rows = table.get("rows") or []
        context = table_context(table, page_texts.get(page, ""))
        status = detect_status(context)
        coord_ctx = detect_coordinate_context(context)
        for r_idx, row in enumerate(rows):
            cells = [clean(v) for v in row]
            c = 0
            while c < len(cells):
                detected = recognized_label(cells[c])
                if not detected:
                    c += 1
                    continue
                rule, source_label = detected
                value_parts: list[str] = []
                j = c + 1
                while j < len(cells):
                    if recognized_label(cells[j]):
                        break
                    if cells[j]:
                        value_parts.append(cells[j])
                    # A label/value pair should be local. Permit at most two value cells.
                    if len(value_parts) >= 2:
                        break
                    j += 1
                raw_value = clean(" ".join(value_parts))
                value = validate_value(rule, raw_value, context)
                if value:
                    local_ctx = coord_ctx
                    label_n = norm(source_label)
                    if "wellhead" in label_n or "surface" in label_n:
                        local_ctx = "wellhead"
                    confidence = 0.96
                    if status == "planned": confidence -= 0.20
                    if rule.coordinate_context and local_ctx != rule.coordinate_context:
                        confidence -= 0.18
                    out.append(Candidate(rule.key, rule.output_label, value, page, table.get("table_id"), r_idx, c, source_label, "table", local_ctx, status, confidence, clean(" | ".join(cells))))
                c = max(j, c + 1)
    return out


def extract_text_candidates(pages: list[dict[str, Any]]) -> list[Candidate]:
    out: list[Candidate] = []
    for page in pages:
        page_no = int(page.get("page_number") or 0)
        text = str(page.get("text") or "")
        lines = [clean(line) for line in text.splitlines() if clean(line)]
        context = clean(" ".join(lines[:80]))
        status = detect_status(context)
        coord_ctx = detect_coordinate_context(context)
        for idx, line in enumerate(lines):
            # Complete-label line: "Water depth: 91 m"
            for alias, rule in ALIASES:
                pattern = rf"^\s*{re.escape(alias)}\s*[:=\-]\s*(.+)$"
                match = re.match(pattern, norm(line), re.I)
                if not match:
                    continue
                raw = line.split(":", 1)[1] if ":" in line else re.split(r"[=\-]", line, maxsplit=1)[-1]
                value = validate_value(rule, raw, context)
                if value:
                    out.append(Candidate(rule.key, rule.output_label, value, page_no, None, None, None, alias, "text", coord_ctx, status, 0.82, line))
                break
            # Two-line label then value.
            detected = recognized_label(line.rstrip(":"))
            if detected and idx + 1 < len(lines):
                rule, source_label = detected
                if recognized_label(lines[idx + 1]):
                    continue
                value = validate_value(rule, lines[idx + 1], context)
                if value:
                    confidence = 0.78
                    if rule.coordinate_context and coord_ctx != rule.coordinate_context:
                        confidence -= 0.15
                    out.append(Candidate(rule.key, rule.output_label, value, page_no, None, None, None, source_label, "text_pair", coord_ctx, status, confidence, line + " | " + lines[idx + 1]))
    return out


def add_generic_derived_candidates(candidates: list[Candidate], pages: list[dict[str, Any]], tables: list[dict[str, Any]]) -> None:
    # Derive final MD/TVD only from rows that explicitly contain TD/Total Depth and MD/TVD headings.
    for table in tables:
        rows = [[clean(v) for v in row] for row in (table.get("rows") or [])]
        page = int(table.get("page_number") or 0)
        header_text = " ".join(" ".join(row) for row in rows[:3])
        status = detect_status(header_text)
        for row in rows:
            row_n = [norm(v) for v in row]
            joined = " ".join(row_n)
            if not re.search(r"\b(td|total depth|final depth)\b", joined):
                continue
            nums = [(idx, parse_number(value)) for idx, value in enumerate(row)]
            nums = [(idx, value) for idx, value in nums if value is not None]
            if len(nums) < 2:
                continue
            # Prefer explicit MD/TVD position from header, otherwise first two plausible numbers.
            md_idx = next((i for i, value in enumerate(row_n) if value in {"md", "measured depth", "final md"}), None)
            tvd_idx = next((i for i, value in enumerate(row_n) if value in {"tvd", "vertical depth", "final tvd"}), None)
            values = [v for _i, v in nums if 100 <= v <= 30000]
            if len(values) < 2:
                continue
            md, tvd = max(values), min(values)
            if tvd > md:
                continue
            evidence = " | ".join(row)
            candidates.append(Candidate("final_md", "Final MD", f"{fmt_num(md)} m", page, table.get("table_id"), None, None, "TD", "derived_table", None, status, 0.90, evidence))
            candidates.append(Candidate("final_tvd", "Final TVD", f"{fmt_num(tvd)} m", page, table.get("table_id"), None, None, "TD", "derived_table", None, status, 0.90, evidence))


def candidate_score(candidate: Candidate) -> float:
    score = candidate.confidence
    if candidate.source_kind == "table": score += 0.04
    if candidate.status == "actual": score += 0.05
    if candidate.status == "planned": score -= 0.20
    if candidate.field_key in {"latitude", "longitude", "northing", "easting"}:
        priority = {"wellhead": 0.12, "slot_centre": 0.08, "site": 0.04, "structure_centre": 0.0, "bottomhole": -0.08, None: -0.12}
        score += priority.get(candidate.coordinate_context, -0.10)
    return score


def resolve_document(pages: list[dict[str, Any]], tables: list[dict[str, Any]], diagnostics_path: Path | None = None) -> list[dict[str, Any]]:
    candidates = extract_table_candidates(pages, tables) + extract_text_candidates(pages)
    add_generic_derived_candidates(candidates, pages, tables)

    grouped: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.field_key, []).append(candidate)

    winners: list[Candidate] = []
    for key, values in grouped.items():
        values.sort(key=lambda item: (candidate_score(item), item.page_number), reverse=True)
        best = values[0]
        # Conservative automatic authority threshold.
        if candidate_score(best) < 0.84:
            continue
        # Do not auto-resolve close conflicts to different values.
        distinct = []
        for item in values:
            if item.value not in [v.value for v in distinct]:
                distinct.append(item)
        if len(distinct) > 1 and candidate_score(distinct[0]) - candidate_score(distinct[1]) < 0.08:
            continue
        winners.append(best)

    by_page: dict[int, list[list[str]]] = {}
    for winner in winners:
        by_page.setdefault(winner.page_number, []).append([winner.output_label, winner.value])

    tables_out: list[dict[str, Any]] = []
    for index, page in enumerate(sorted(by_page), start=1):
        rows = by_page[page]
        tables_out.append({
            "table_id": f"mv_schema_authority_{index:03d}",
            "page_number": page,
            "caption": AUTHORITY_CAPTION,
            "cells": [
                {"row": r, "column": c, "text": value, "bbox": None, "is_header": False}
                for r, row in enumerate(rows)
                for c, value in enumerate(row)
            ],
            "rows": rows,
        })

    if diagnostics_path:
        diagnostics_path.write_text(json.dumps({
            "candidate_count": len(candidates),
            "winner_count": len(winners),
            "candidates": [asdict(c) | {"score": candidate_score(c)} for c in candidates],
            "winners": [asdict(c) | {"score": candidate_score(c)} for c in winners],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    return tables_out
