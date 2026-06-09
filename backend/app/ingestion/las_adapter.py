"""Backend-owned LAS source adapter.

This adapter intentionally implements a conservative LAS 2.x style parser for
metadata, evidence, QAQC, and curve inventory. It does not make the ingestion
architecture LAS-only and it does not depend on frontend code or viewer state.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import (
    CurveChannelArtifact,
    IngestionEvidenceKind,
    IngestionEvidenceRecord,
    IngestionQaqcFinding,
    IngestionQaqcSeverity,
    IngestionQaqcSummary,
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


@dataclass(frozen=True)
class DepthMnemonicResult:
    mnemonic: str
    explicit: bool


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

        depth_result = _depth_mnemonic(curve_lookup)
        depth_mnemonic = depth_result.mnemonic
        depth_unit = _depth_unit(curve_lookup, well_lookup)
        top_depth, base_depth, sample_count = _depth_stats(ascii_rows)
        null_value = _number(_header_value(well_lookup, "NULL"))
        header_well_name = _first_header_value(well_lookup, ("WELL", "WEL", "WELLNAME", "NAME"))
        well_name = header_well_name or _strip_extension(file_name)
        well_id = _first_header_value(well_lookup, ("UWI", "API", "WELLID", "WELL_ID")) or _slug(well_name)

        curve_channels = []
        non_depth_curve_lines: list[LasHeaderLine] = []
        for line in curve_lookup:
            mnemonic_upper = line.mnemonic.upper()
            if mnemonic_upper == depth_mnemonic.upper():
                continue
            non_depth_curve_lines.append(line)
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

        evidence = _evidence_records(
            checksum=checksum,
            file_name=file_name,
            original_path=original_path,
            well_name=header_well_name,
            well_id=str(well_id) if well_id else None,
            depth_mnemonic=depth_mnemonic,
            depth_mnemonic_explicit=depth_result.explicit,
            depth_unit=depth_unit,
            top_depth=top_depth,
            base_depth=base_depth,
            sample_count=sample_count,
            null_value=null_value,
            curve_channels=curve_channels,
            well_lines=well_lines,
            curve_lines=curve_lines,
        )
        findings = _qaqc_findings(
            header_well_name=header_well_name,
            depth_result=depth_result,
            curve_lines=non_depth_curve_lines,
            curves=curve_channels,
            top=top_depth,
            base=base_depth,
            null_value=null_value,
            evidence=evidence,
        )
        qaqc_summary = _qaqc_summary(evidence, findings, top_depth, base_depth, curve_channels)

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
                "evidence_count": len(evidence),
                "qaqc_summary": qaqc_summary.model_dump(mode="json"),
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
            "depth_mnemonic_explicit": depth_result.explicit,
            "depth_unit": depth_unit,
            "top_depth": top_depth,
            "base_depth": base_depth,
            "sample_count": sample_count,
            "null_value": null_value,
            "curve_count": len(curve_channels),
            "curve_mnemonics": [curve.mnemonic for curve in curve_channels],
            "evidence_count": len(evidence),
            "qaqc_summary": qaqc_summary.model_dump(mode="json"),
        }

        return NormalizedWellLogPackage(
            package_id=f"normalized-las:{checksum[:24]}",
            source_file=source_file,
            well_id=_slug(str(well_id)),
            well_name=str(well_name),
            curve_channels=curve_channels,
            metadata=package_metadata,
            evidence=evidence,
            qaqc_findings=findings,
            qaqc_summary=qaqc_summary,
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


def _depth_mnemonic(curves: list[LasHeaderLine]) -> DepthMnemonicResult:
    for line in curves:
        if line.mnemonic.upper() in {"DEPT", "DEPTH", "MD"}:
            return DepthMnemonicResult(mnemonic=line.mnemonic, explicit=True)
    if curves:
        return DepthMnemonicResult(mnemonic=curves[0].mnemonic, explicit=False)
    return DepthMnemonicResult(mnemonic="DEPT", explicit=False)


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


def _evidence_records(
    *,
    checksum: str,
    file_name: str,
    original_path: str | None,
    well_name: str | None,
    well_id: str | None,
    depth_mnemonic: str,
    depth_mnemonic_explicit: bool,
    depth_unit: str,
    top_depth: float | None,
    base_depth: float | None,
    sample_count: int,
    null_value: float | None,
    curve_channels: list[CurveChannelArtifact],
    well_lines: list[LasHeaderLine],
    curve_lines: list[LasHeaderLine],
) -> list[IngestionEvidenceRecord]:
    evidence: list[IngestionEvidenceRecord] = []

    def add(
        evidence_kind: IngestionEvidenceKind,
        field_path: str,
        value: Any,
        message: str,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        evidence.append(
            IngestionEvidenceRecord(
                evidence_id=f"evidence:{checksum[:16]}:{len(evidence) + 1:04d}",
                evidence_kind=evidence_kind,
                source="las_adapter",
                field_path=field_path,
                confidence=confidence,
                value=value,
                message=message,
                metadata=metadata or {},
            )
        )

    add(
        IngestionEvidenceKind.SOURCE_FINGERPRINT,
        "source_file.checksum",
        checksum,
        "SHA-256 source fingerprint calculated from source bytes.",
        metadata={"file_name": file_name, "original_path": original_path},
    )
    if well_name:
        add(IngestionEvidenceKind.METADATA_HEADER, "well_name", well_name, "Well name extracted from LAS well section.")
    if well_id:
        add(IngestionEvidenceKind.METADATA_HEADER, "well_id", well_id, "Well identifier extracted from LAS well section.")
    add(
        IngestionEvidenceKind.DEPTH_SAMPLES,
        "depth_mnemonic",
        depth_mnemonic,
        "Depth mnemonic resolved from LAS curve section.",
        confidence=1.0 if depth_mnemonic_explicit else 0.45,
        metadata={"explicit_depth_curve": depth_mnemonic_explicit},
    )
    add(IngestionEvidenceKind.UNIT, "depth_unit", depth_unit, "Depth unit resolved from LAS curve/well sections.")
    if top_depth is not None and base_depth is not None:
        add(
            IngestionEvidenceKind.DEPTH_SAMPLES,
            "depth_range",
            {"top_depth": top_depth, "base_depth": base_depth, "sample_count": sample_count},
            "Depth range calculated from LAS ASCII samples.",
        )
    if null_value is not None:
        add(IngestionEvidenceKind.NULL_VALUE, "null_value", null_value, "NULL value extracted from LAS well section.")
    add(
        IngestionEvidenceKind.CURVE_INVENTORY,
        "curve_channels",
        [curve.mnemonic for curve in curve_channels],
        "Curve inventory extracted from LAS curve section.",
        metadata={"curve_count": len(curve_channels)},
    )
    add(
        IngestionEvidenceKind.METADATA_HEADER,
        "las_sections",
        {"well_header_count": len(well_lines), "curve_header_count": len(curve_lines)},
        "LAS well and curve header lines parsed for metadata evidence.",
    )
    return evidence


def _qaqc_findings(
    *,
    header_well_name: str | None,
    depth_result: DepthMnemonicResult,
    curve_lines: list[LasHeaderLine],
    curves: list[CurveChannelArtifact],
    top: float | None,
    base: float | None,
    null_value: float | None,
    evidence: list[IngestionEvidenceRecord],
) -> list[IngestionQaqcFinding]:
    findings: list[IngestionQaqcFinding] = []

    def evidence_ids_for(field_path: str) -> list[str]:
        return [item.evidence_id for item in evidence if item.field_path == field_path]

    def add(severity: IngestionQaqcSeverity, code: str, message: str, field_path: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        findings.append(
            IngestionQaqcFinding(
                finding_id=f"qaqc:{code}:{len(findings) + 1:03d}",
                severity=severity,
                code=code,
                message=message,
                field_path=field_path,
                evidence_ids=evidence_ids_for(field_path) if field_path else [],
                metadata=metadata or {},
            )
        )

    add(IngestionQaqcSeverity.INFO, "source_fingerprint_available", "Source fingerprint evidence is available.", "source_file.checksum")
    if not header_well_name:
        add(IngestionQaqcSeverity.WARNING, "missing_well_name", "LAS well name was not found in the well section; file name fallback was used.", "well_name")
    if not depth_result.explicit:
        add(IngestionQaqcSeverity.WARNING, "missing_depth_curve", "No explicit DEPT/DEPTH/MD curve mnemonic was found; first curve was used as depth.", "depth_mnemonic")
    if not curves:
        add(IngestionQaqcSeverity.ERROR, "missing_curve_inventory", "No non-depth LAS curves were extracted.", "curve_channels")
    if top is None or base is None:
        add(IngestionQaqcSeverity.WARNING, "missing_depth_samples", "No numeric LAS ASCII depth samples were found.", "depth_range")
    elif top >= base:
        add(IngestionQaqcSeverity.ERROR, "invalid_depth_range", "LAS top depth must be less than base depth.", "depth_range")
    if null_value is None:
        add(IngestionQaqcSeverity.WARNING, "missing_null_value", "LAS NULL value was not declared in the well section.", "null_value")

    mnemonics = [line.mnemonic.upper() for line in curve_lines]
    duplicate_mnemonics = sorted({mnemonic for mnemonic in mnemonics if mnemonics.count(mnemonic) > 1})
    if duplicate_mnemonics:
        add(
            IngestionQaqcSeverity.ERROR,
            "duplicate_curve_mnemonics",
            "Duplicate non-depth LAS curve mnemonics were found.",
            "curve_channels",
            metadata={"duplicates": duplicate_mnemonics},
        )

    missing_units = [line.mnemonic for line in curve_lines if not line.unit]
    if missing_units:
        add(
            IngestionQaqcSeverity.WARNING,
            "missing_curve_units",
            "One or more non-depth LAS curves are missing units.",
            "curve_channels",
            metadata={"curves": missing_units},
        )
    return findings


def _qaqc_summary(
    evidence: list[IngestionEvidenceRecord],
    findings: list[IngestionQaqcFinding],
    top_depth: float | None,
    base_depth: float | None,
    curve_channels: list[CurveChannelArtifact],
) -> IngestionQaqcSummary:
    error_count = sum(1 for item in findings if item.severity == IngestionQaqcSeverity.ERROR)
    warning_count = sum(1 for item in findings if item.severity == IngestionQaqcSeverity.WARNING)
    info_count = sum(1 for item in findings if item.severity == IngestionQaqcSeverity.INFO)
    return IngestionQaqcSummary(
        ok=error_count == 0,
        evidence_count=len(evidence),
        finding_count=len(findings),
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        source_fingerprint_available=any(item.evidence_kind == IngestionEvidenceKind.SOURCE_FINGERPRINT for item in evidence),
        depth_range_available=top_depth is not None and base_depth is not None and top_depth < base_depth,
        curve_inventory_available=bool(curve_channels),
        viewer_package_available=False,
    )
