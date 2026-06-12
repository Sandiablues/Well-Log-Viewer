"""Product-id-backed WDV curve sample service.

This service is the WDV rendering data boundary for managed loaded curves. The
frontend must not render managed product curves from prototype fixture aliases.
It should request samples by product_id and render only samples returned by this
backend-owned service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import math
import re

from .models import ManagedProductGroupItem, ManagedWellRecord
from .repository import ManagedWellInventoryRepository, ManagedWellNotFoundError


class CurveSampleServiceError(ValueError):
    """Raised when product-backed curve samples cannot be safely returned."""


class CurveSampleService:
    def __init__(self, repository: ManagedWellInventoryRepository | None = None) -> None:
        self.repository = repository or ManagedWellInventoryRepository()

    def get_curve_samples(self, managed_well_id: str, product_id: str, max_samples: int = 12000) -> dict[str, Any]:
        record = self.repository.get_record(managed_well_id)
        item = self._find_product_item(record, product_id)
        source_path = self._source_path_for_item(item)
        if source_path is None:
            raise CurveSampleServiceError(f"No readable LAS source path is available for product: {product_id}")

        parsed = _read_las_curve_samples(
            source_path=source_path,
            curve_mnemonic=item.curve_name or item.display_name,
            max_samples=max_samples,
        )

        return {
            "ok": True,
            "contract_kind": "wdv_product_curve_samples",
            "contract_version": "wdv_product_curve_samples_v1",
            "managed_well_id": record.managed_well_id,
            "well_id": record.well_id,
            "well_name": record.well_name,
            "product_id": item.product_id,
            "curve_id": item.curve_name,
            "mnemonic": item.curve_name,
            "display_name": item.display_name,
            "curve_family": item.curve_family,
            "source_id": item.source_id,
            "source_intake_candidate_id": item.source_intake_candidate_id,
            "source_path": str(source_path),
            "sample_source": "las_original_path",
            "depth_unit": parsed["depth_unit"],
            "value_unit": parsed["value_unit"] or item.curve_unit or "",
            "depth_min": parsed["depth_min"],
            "depth_max": parsed["depth_max"],
            "value_min": parsed["value_min"],
            "value_max": parsed["value_max"],
            "sample_count": parsed["sample_count"],
            "returned_sample_count": len(parsed["samples"]),
            "decimation_stride": parsed["decimation_stride"],
            "samples": parsed["samples"],
        }

    def _find_product_item(self, record: ManagedWellRecord, product_id: str) -> ManagedProductGroupItem:
        for group in record.product_groups:
            for item in group.items:
                if item.product_id == product_id:
                    return item
        raise ManagedWellNotFoundError(product_id)

    @staticmethod
    def _source_path_for_item(item: ManagedProductGroupItem) -> Path | None:
        provenance = item.provenance if isinstance(item.provenance, dict) else {}
        candidates = [
            provenance.get("original_path"),
            provenance.get("path"),
            provenance.get("source_path"),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(str(candidate)).expanduser()
            if path.exists() and path.is_file():
                return path.resolve()
        return None


def _read_las_curve_samples(source_path: Path, curve_mnemonic: str, max_samples: int) -> dict[str, Any]:
    text = source_path.read_text(encoding="utf-8", errors="replace")
    sections = _split_las_sections(text)
    curve_lines = _parse_curve_section(sections.get("C") or sections.get("CURVE") or [])
    well_lines = _parse_well_section(sections.get("W") or sections.get("WELL") or [])
    rows = _parse_ascii_rows(sections.get("A") or sections.get("ASCII") or [])
    if not curve_lines:
        raise CurveSampleServiceError(f"LAS curve section is empty: {source_path}")
    if not rows:
        raise CurveSampleServiceError(f"LAS ASCII sample section is empty: {source_path}")

    depth_index = _depth_column_index(curve_lines)
    curve_index = _curve_column_index(curve_lines, curve_mnemonic)
    depth_unit = _normalize_depth_unit(curve_lines[depth_index].get("unit") or well_lines.get("STRT", {}).get("unit") or "ft")
    value_unit = curve_lines[curve_index].get("unit")
    null_header = well_lines.get("NULL", {})
    # LAS NULL is commonly written as `NULL. -999.25 : ...`. The existing
    # header parser treats the value after the dot as the unit token when no
    # separate value token exists, so check both fields. Returning LAS nulls as
    # real samples would render false spikes in the WDV.
    null_value = _float_or_none(null_header.get("value") or null_header.get("unit"))

    samples: list[list[float]] = []
    for row in rows:
        if len(row) <= max(depth_index, curve_index):
            continue
        depth = row[depth_index]
        value = row[curve_index]
        if not math.isfinite(depth) or not math.isfinite(value):
            continue
        if null_value is not None and abs(value - null_value) <= 1e-9:
            continue
        samples.append([depth, value])

    if not samples:
        raise CurveSampleServiceError(f"No numeric samples found for curve {curve_mnemonic}: {source_path}")

    stride = max(1, math.ceil(len(samples) / max_samples)) if max_samples > 0 else 1
    returned = samples[::stride]
    if returned[-1] != samples[-1]:
        returned.append(samples[-1])

    depths = [sample[0] for sample in samples]
    values = [sample[1] for sample in samples]
    return {
        "depth_unit": depth_unit,
        "value_unit": value_unit,
        "depth_min": min(depths),
        "depth_max": max(depths),
        "value_min": min(values),
        "value_max": max(values),
        "sample_count": len(samples),
        "decimation_stride": stride,
        "samples": returned,
    }


def _split_las_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("~"):
            current = stripped[1:].split(maxsplit=1)[0].upper()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections.setdefault(current, []).append(line)
    return sections


def _parse_curve_section(lines: list[str]) -> list[dict[str, str | None]]:
    output: list[dict[str, str | None]] = []
    for line in lines:
        parsed = _parse_las_header_line(line)
        if parsed and parsed["mnemonic"]:
            output.append(parsed)
    return output


def _parse_well_section(lines: list[str]) -> dict[str, dict[str, str | None]]:
    output: dict[str, dict[str, str | None]] = {}
    for line in lines:
        parsed = _parse_las_header_line(line)
        if parsed and parsed["mnemonic"]:
            output[str(parsed["mnemonic"]).upper()] = parsed
    return output


def _parse_las_header_line(raw: str) -> dict[str, str | None] | None:
    stripped = raw.strip()
    if not stripped or stripped.startswith("#"):
        return None
    left = stripped.split(":", 1)[0].strip()
    match = re.match(r"^\s*([A-Za-z0-9_\-]+)\s*(?:\.\s*([^\s]*))?\s*(.*?)\s*$", left)
    if not match:
        return None
    mnemonic = match.group(1).strip()
    unit = (match.group(2) or "").strip() or None
    value = (match.group(3) or "").strip() or None
    return {"mnemonic": mnemonic, "unit": unit, "value": value}


def _parse_ascii_rows(lines: list[str]) -> list[list[float]]:
    rows: list[list[float]] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        values: list[float] = []
        for token in stripped.replace(",", " ").split():
            try:
                values.append(float(token))
            except ValueError:
                values = []
                break
        if values:
            rows.append(values)
    return rows


def _depth_column_index(curves: list[dict[str, str | None]]) -> int:
    for index, line in enumerate(curves):
        if str(line.get("mnemonic") or "").upper() in {"DEPT", "DEPTH", "MD"}:
            return index
    return 0


def _curve_column_index(curves: list[dict[str, str | None]], curve_mnemonic: str) -> int:
    requested = str(curve_mnemonic or "").upper()
    for index, line in enumerate(curves):
        if str(line.get("mnemonic") or "").upper() == requested:
            return index
    available = ", ".join(str(line.get("mnemonic")) for line in curves[:40])
    raise CurveSampleServiceError(f"Curve {curve_mnemonic} was not found in LAS curve section. Available: {available}")


def _float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def _normalize_depth_unit(unit: str) -> str:
    lowered = unit.lower().strip()
    if lowered in {"m", "meter", "metre", "meters", "metres"}:
        return "m"
    if lowered in {"ft", "feet", "foot", "f"}:
        return "ft"
    return lowered or "ft"
