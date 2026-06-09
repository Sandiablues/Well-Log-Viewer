"""Backend-owned LAS source adapter.

This adapter intentionally implements a conservative LAS 2.x style parser for
metadata and curve inventory only. It does not make the ingestion architecture
LAS-only and it does not depend on frontend code or viewer state.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import (
    CurveChannelArtifact,
    NormalizedWellLogPackage,
    SourceFileRegistration,
    WellLogSourceCategory,
    WellLogSourceFormat,
)


class LasAdapterError(ValueError):
    """Raised when a LAS source cannot be parsed into a normalized package."""


@dataclass(frozen=True)
class LasHeaderLine:
    mnemonic: str
    unit: str | None
    value: str | None
    description: str | None


class LasSourceAdapter:
    adapter_id = "las_numeric_curve_adapter_v1"

    def parse_path(self, path: str | Path, display_name: str | None = None, metadata: dict[str, Any] | None = None) -> NormalizedWellLogPackage:
        source_path = Path(path).expanduser().resolve()
        if not source_path.exists() or not source_path.is_file():
            raise LasAdapterError(f"LAS source file not found: {source_path}")
        payload = source_path.read_bytes()
        return self.parse_bytes(
            payload,
            file_name=source_path.name,
            original_path=str(source_path),
            display_name=display_name or source_path.name,
            metadata=metadata or {},
        )

    def parse_bytes(
        self,
        payload: bytes,
        *,
        file_name: str,
        original_path: str | None = None,
        display_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NormalizedWellLogPackage:
        checksum = hashlib.sha256(payload).hexdigest()
        text = payload.decode("utf-8", errors="replace")
        sections = _split_las_sections(text)
        if "W" not in sections and "WELL" not in sections:
            raise LasAdapterError("LAS well section not found.")
        if "C" not in sections and "CURVE" not in sections:
            raise LasAdapterError("LAS curve section not found.")

        well_lines = _parse_header_lines(sections.get("WELL") or sections.get("W") or [])
        curve_lines = _parse_header_lines(sections.get("CURVE") or sections.get("C") or [])
        ascii_rows = _parse_ascii_rows(sections.get("ASCII") or sections.get("A") or [])

        well_lookup = {line.mnemonic.upper(): line for line in well_lines}
        curve_lookup = [line for line in curve_lines if line.mnemonic]

        depth_mnemonic = _depth_mnemonic(curve_lookup)
        depth_unit = _depth_unit(curve_lookup, well_lookup)
        top_depth, base_depth, sample_count = _depth_stats(ascii_rows)
        null_value = _number(_header_value(well_lookup, "NULL"))
        well_name = _first_header_value(well_lookup, ("WELL", "WEL", "WELLNAME", "NAME")) or _strip_extension(file_name)
        well_id = _first_header_value(well_lookup, ("UWI", "API", "WELLID", "WELL_ID")) or _slug(well_name)

        curve_channels = []
        for line in curve_lookup:
            mnemonic_upper = line.mnemonic.upper()
            if mnemonic_upper == depth_mnemonic.upper():
                continue
            artifact_id = f"curve:{checksum[:16]}:{_slug(line.mnemonic)}"
            curve_channels.append(
                CurveChannelArtifact(
                    artifact_id=artifact_id,
                    mnemonic=line.mnemonic,
                    display_name=line.description or line.mnemonic,
                    unit=line.unit,
                    depth_unit=depth_unit,
                    top_depth=top_depth,
                    base_depth=base_depth,
                    sample_count=sample_count,
                    metadata={
                        "las_value": line.value,
                        "las_description": line.description,
                    },
                )
            )

        source_file = SourceFileRegistration(
            source_file_id=f"source:sha256:{checksum}",
            display_name=display_name or file_name,
            source_format=WellLogSourceFormat.LAS,
            source_category=WellLogSourceCategory.NUMERIC_CURVE,
            original_path=original_path,
            file_name=file_name,
            byte_size=len(payload),
            checksum=checksum,
            metadata={
                "adapter_id": self.adapter_id,
                "depth_mnemonic": depth_mnemonic,
                "depth_unit": depth_unit,
                **(metadata or {}),
            },
        )

        package_metadata: dict[str, Any] = {
            "adapter_id": self.adapter_id,
            "source_fingerprint": checksum,
            "source_format": WellLogSourceFormat.LAS.value,
            "well_header": {line.mnemonic.upper(): {"unit": line.unit, "value": line.value, "description": line.description} for line in well_lines},
            "curve_header": {line.mnemonic.upper(): {"unit": line.unit, "value": line.value, "description": line.description} for line in curve_lines},
            "depth_mnemonic": depth_mnemonic,
            "depth_unit": depth_unit,
            "top_depth": top_depth,
            "base_depth": base_depth,
            "sample_count": sample_count,
            "null_value": null_value,
            "curve_count": len(curve_channels),
        }

        return NormalizedWellLogPackage(
            package_id=f"normalized-las:{checksum[:24]}",
            source_file=source_file,
            well_id=_slug(str(well_id)),
            well_name=str(well_name),
            curve_channels=curve_channels,
            metadata=package_metadata,
            qaqc_findings=_qaqc_findings(well_name, curve_channels, top_depth, base_depth),
        )


def _split_las_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("~"):
            label = stripped[1:].split(maxsplit=1)[0].upper()
            current = label
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections.setdefault(current, []).append(line)
    return sections


def _parse_header_lines(lines: list[str]) -> list[LasHeaderLine]:
    parsed: list[LasHeaderLine] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        content, description = _split_description(stripped)
        match = re.match(r"^\s*([A-Za-z0-9_\-]+)\s*(?:\.\s*([^\s]*))?\s*(.*?)\s*$", content)
        if not match:
            continue
        mnemonic = match.group(1).strip()
        unit = (match.group(2) or "").strip() or None
        value = (match.group(3) or "").strip() or None
        if mnemonic.upper() in {"WELL", "WEL", "WELLNAME", "NAME", "UWI", "API", "WELLID", "WELL_ID", "FLD", "FIELD", "COMP", "COMPANY", "NULL"}:
            parts = [part for part in (unit, value) if part]
            value = " ".join(parts) if parts else value
            unit = None
        parsed.append(LasHeaderLine(mnemonic=mnemonic, unit=unit, value=value, description=(description or None)))
    return parsed


def _split_description(line: str) -> tuple[str, str | None]:
    if ":" not in line:
        return line, None
    left, right = line.split(":", 1)
    return left.strip(), right.strip() or None


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


def _depth_mnemonic(curves: list[LasHeaderLine]) -> str:
    for line in curves:
        if line.mnemonic.upper() in {"DEPT", "DEPTH", "MD"}:
            return line.mnemonic
    if curves:
        return curves[0].mnemonic
    return "DEPT"


def _depth_unit(curves: list[LasHeaderLine], well_lookup: dict[str, LasHeaderLine]) -> str:
    for line in curves:
        if line.mnemonic.upper() in {"DEPT", "DEPTH", "MD"} and line.unit:
            return _normalize_depth_unit(line.unit)
    strt = well_lookup.get("STRT")
    if strt and strt.unit:
        return _normalize_depth_unit(strt.unit)
    return "ft"


def _normalize_depth_unit(unit: str) -> str:
    lowered = unit.lower().strip()
    if lowered in {"m", "meter", "metre", "meters", "metres"}:
        return "m"
    if lowered in {"ft", "feet", "foot", "f"}:
        return "ft"
    return lowered


def _depth_stats(rows: list[list[float]]) -> tuple[float | None, float | None, int]:
    depths = [row[0] for row in rows if row]
    if not depths:
        return None, None, 0
    return min(depths), max(depths), len(depths)


def _header_value(lookup: dict[str, LasHeaderLine], key: str) -> str | None:
    line = lookup.get(key.upper())
    return line.value if line else None


def _first_header_value(lookup: dict[str, LasHeaderLine], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _header_value(lookup, key)
        if value:
            return value
    return None


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def _strip_extension(file_name: str) -> str:
    return Path(file_name).stem


def _slug(value: str) -> str:
    candidate = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return candidate or "unknown"


def _qaqc_findings(well_name: str | None, curves: list[CurveChannelArtifact], top: float | None, base: float | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not well_name:
        findings.append({"severity": "warning", "code": "missing_well_name", "message": "LAS well name was not found."})
    if not curves:
        findings.append({"severity": "error", "code": "missing_curve_inventory", "message": "No non-depth LAS curves were extracted."})
    if top is None or base is None:
        findings.append({"severity": "warning", "code": "missing_depth_samples", "message": "No numeric LAS ASCII depth samples were found."})
    elif top >= base:
        findings.append({"severity": "error", "code": "invalid_depth_range", "message": "LAS top depth must be less than base depth."})
    return findings
