"""Backend-owned identity gate for WLV Source Intake registration.

The gate prevents weak/generic LAS header values such as WELL, UNIQUE WELL ID,
FIELD, and COMPANY from creating separate managed wells. It does not promote
records to managed inventory; it only enriches intake candidates with a resolved
identity decision and evidence before registration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .models import (
    SourceFileCandidate,
    SourceIntakeEvidenceRecord,
    SourceIntakeResolvedField,
    SourceIntakeResolvedMetadata,
)

_GENERIC_IDENTITY_VALUES = {
    "",
    "-",
    "na",
    "n/a",
    "none",
    "null",
    "unknown",
    "unk",
    "well",
    "wellname",
    "wellid",
    "uniquewellid",
    "uniqueid",
    "uwi",
    "api",
    "field",
    "company",
    "operator",
    "country",
}


@dataclass(frozen=True)
class _StrongIdentity:
    well_name: str
    uwi: str | None
    operator: str | None
    field: str | None
    block: str | None
    source_candidate_id: str
    source_path: str


def is_generic_identity_value(value: object | None) -> bool:
    """Return True when a source value is a placeholder, not real metadata."""
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    return _normalize(text) in _GENERIC_IDENTITY_VALUES


def clean_identity_value(value: object | None) -> str | None:
    """Clean a metadata value and drop generic placeholders."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or is_generic_identity_value(text):
        return None
    return text


def apply_identity_gate(candidates: list[SourceFileCandidate]) -> None:
    """Apply package-aware identity decisions before registration.

    Strong LAS identities remain authoritative. Weak/generic LAS identities are
    not allowed to pass through as WELL / UNIQUE WELL ID / FIELD / COMPANY.
    When a weak candidate is in the same package as a strong identity, and the
    path/filename evidence supports the same well, the candidate is assigned to
    that package identity with review evidence.
    """
    strong_identities = _strong_identities(candidates)
    if not strong_identities:
        _mark_generic_candidates_for_review(candidates)
        return

    for candidate in candidates:
        if candidate.parsed_metadata is None:
            continue
        if not _has_curve_payload(candidate):
            continue
        if not _has_weak_or_generic_identity(candidate):
            continue

        matches = _matching_strong_identities(candidate, strong_identities)
        if len(matches) != 1:
            _mark_candidate_identity_review(candidate, "Weak/generic LAS identity could not be assigned to one unique package well.")
            continue

        _assign_candidate_to_identity(candidate, matches[0])


def _strong_identities(candidates: Iterable[SourceFileCandidate]) -> list[_StrongIdentity]:
    identities: list[_StrongIdentity] = []
    seen: set[tuple[str, str | None]] = set()
    for candidate in candidates:
        resolved = candidate.resolved_metadata
        if candidate.parsed_metadata is None or resolved is None:
            continue
        well_name = clean_identity_value(resolved.well_name.value)
        uwi = clean_identity_value(resolved.uwi.value)
        if not well_name or not uwi:
            continue
        key = (_normalize(well_name), _normalize(uwi) if uwi else None)
        if key in seen:
            continue
        seen.add(key)
        identities.append(
            _StrongIdentity(
                well_name=well_name,
                uwi=uwi,
                operator=clean_identity_value(resolved.operator.value),
                field=clean_identity_value(resolved.field.value),
                block=clean_identity_value(resolved.block.value),
                source_candidate_id=candidate.source_file_id,
                source_path=candidate.relative_path,
            )
        )
    return identities


def _matching_strong_identities(candidate: SourceFileCandidate, identities: list[_StrongIdentity]) -> list[_StrongIdentity]:
    path_text = f"{candidate.relative_path} {candidate.file_name}"
    direct = [identity for identity in identities if _path_supports_identity(path_text, identity.well_name)]
    if direct:
        return direct
    if len(identities) == 1:
        return identities
    return []


def _path_supports_identity(path_text: str, well_name: str) -> bool:
    normalized_path = _normalize(path_text)
    normalized_well = _normalize(well_name)
    if normalized_well and normalized_well in normalized_path:
        return True
    match = re.search(r"(\d{1,3})\D+(\d{1,3})", well_name)
    if not match:
        return False
    compact = "".join(match.groups())
    return compact in normalized_path


def _has_curve_payload(candidate: SourceFileCandidate) -> bool:
    parsed = candidate.parsed_metadata
    if parsed is None:
        return False
    if parsed.log_header is not None and parsed.log_header.curve_count > 0:
        return True
    return bool(parsed.curve_headers)


def _has_weak_or_generic_identity(candidate: SourceFileCandidate) -> bool:
    resolved = candidate.resolved_metadata
    parsed = candidate.parsed_metadata
    if resolved is not None:
        values = [
            resolved.well_name.value,
            resolved.uwi.value,
            resolved.operator.value,
            resolved.field.value,
        ]
        return any(is_generic_identity_value(value) for value in values[:2]) or all(
            is_generic_identity_value(value) for value in values[:4]
        )
    if parsed is None:
        return False
    header = parsed.well_header
    return is_generic_identity_value(header.well_name) or is_generic_identity_value(header.uwi)


def _assign_candidate_to_identity(candidate: SourceFileCandidate, identity: _StrongIdentity) -> None:
    message = (
        "Weak/generic LAS identity was assigned to the package well identity "
        f"{identity.well_name!r} before managed-inventory registration."
    )
    evidence_source = "source-intake package identity gate"
    candidate.resolved_metadata = SourceIntakeResolvedMetadata(
        resolver_id="wlv_source_intake_identity_gate_v1",
        well_name=_field("well_name", identity.well_name, evidence_source, candidate.relative_path, identity, message, review=True),
        uwi=_field("uwi", identity.uwi, evidence_source, candidate.relative_path, identity, message, review=True),
        operator=_field("operator", identity.operator, evidence_source, candidate.relative_path, identity, message, review=True),
        field=_field("field", identity.field, evidence_source, candidate.relative_path, identity, message, review=True),
        block=_field("block", identity.block, evidence_source, candidate.relative_path, identity, message, review=True),
        review_required=True,
        warning_count=1,
        warnings=[message],
        evidence_count=5,
    )
    candidate.review_required = True
    if message not in candidate.warnings:
        candidate.warnings.append(message)


def _field(
    field_name: str,
    value: str | None,
    source: str,
    source_path: str,
    identity: _StrongIdentity,
    message: str,
    *,
    review: bool,
) -> SourceIntakeResolvedField:
    confidence = "package_high" if value else "missing"
    evidence_value = value
    evidence = SourceIntakeEvidenceRecord(
        field_name=field_name,
        value=evidence_value,
        source=source,
        source_path=source_path,
        confidence=confidence,
        message=(
            f"{message} identity_source_candidate={identity.source_candidate_id}; "
            f"identity_source_path={identity.source_path}"
        ),
    )
    return SourceIntakeResolvedField(
        field_name=field_name,
        value=value,
        source=source if value else "missing",
        confidence=confidence,
        review_required=review,
        evidence=[evidence],
        warnings=[message] if review and field_name in {"well_name", "uwi"} else [],
    )


def _mark_generic_candidates_for_review(candidates: Iterable[SourceFileCandidate]) -> None:
    for candidate in candidates:
        if candidate.parsed_metadata is None or not _has_curve_payload(candidate):
            continue
        if _has_weak_or_generic_identity(candidate):
            _mark_candidate_identity_review(candidate, "Weak/generic LAS identity requires review before registration.")


def _mark_candidate_identity_review(candidate: SourceFileCandidate, message: str) -> None:
    candidate.review_required = True
    if message not in candidate.warnings:
        candidate.warnings.append(message)
    if candidate.resolved_metadata is not None and message not in candidate.resolved_metadata.warnings:
        candidate.resolved_metadata.review_required = True
        candidate.resolved_metadata.warning_count += 1
        candidate.resolved_metadata.warnings.append(message)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())
