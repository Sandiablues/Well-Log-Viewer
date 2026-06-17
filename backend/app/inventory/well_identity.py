"""Canonical managed-well identity and metadata consolidation.

The Managed Well Inventory groups Source Intake candidates by an authoritative
well name. UWI and other metadata remain well-level attributes and evidence;
they do not independently create additional managed-well records.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Iterable

from .models import ManagedWellRecord


_CANONICAL_FIELDS = ("uwi", "operator", "field", "block", "country", "depth_unit")


def normalize_well_name_key(value: str) -> str:
    """Return a stable comparison key while preserving display text elsewhere."""
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = " ".join(normalized.split())
    if not normalized:
        raise ValueError("Canonical well name is empty after normalization.")
    return normalized


def managed_well_identity_from_name(well_name: str) -> tuple[str, str, str]:
    """Return well_id, managed_well_id, and canonical name key."""
    canonical_key = normalize_well_name_key(well_name)
    slug = re.sub(r"[^a-z0-9]+", "-", canonical_key).strip("-") or "unknown"
    digest = hashlib.sha256(canonical_key.encode("utf-8")).hexdigest()[:12]
    well_id = f"wlv-intake-name-{slug}-{digest}"
    return well_id, f"managed-well:{well_id}", canonical_key


def record_canonical_well_key(record: ManagedWellRecord) -> str:
    stored = record.metadata.get("canonical_well_key")
    if isinstance(stored, str) and stored.strip():
        return stored.strip()
    return normalize_well_name_key(record.well_name)


def find_record_by_canonical_name(
    records: Iterable[ManagedWellRecord],
    well_name: str,
) -> ManagedWellRecord | None:
    """Find exactly one record with the normalized canonical well name.

    Multiple matches are not merged implicitly because that would be a
    destructive consolidation decision.
    """
    key = normalize_well_name_key(well_name)
    matches = [
        record
        for record in records
        if record_canonical_well_key(record) == key
    ]
    if len(matches) > 1:
        ids = ", ".join(sorted(record.managed_well_id for record in matches))
        raise ValueError(
            "Multiple managed wells already share canonical well name "
            f"{well_name!r}: {ids}. Consolidate those records before "
            "registering additional candidates."
        )
    return matches[0] if matches else None


def consolidate_well_metadata(
    *,
    existing: ManagedWellRecord | None,
    incoming: dict[str, Any],
    explicit: dict[str, Any],
    source_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return canonical fields, evidence, and current conflicts.

    Explicit human values are authoritative. Otherwise an existing canonical
    value is retained, missing values are filled from incoming evidence, and
    disagreements are retained as current conflicts against the same well.
    """
    existing_metadata = existing.metadata if existing is not None else {}
    prior_evidence = existing_metadata.get("well_metadata_evidence")
    evidence: dict[str, list[dict[str, Any]]] = {
        field: list(entries)
        for field, entries in prior_evidence.items()
        if field in _CANONICAL_FIELDS and isinstance(entries, list)
    } if isinstance(prior_evidence, dict) else {}

    canonical: dict[str, Any] = {}
    conflicts: dict[str, Any] = {}

    for field in _CANONICAL_FIELDS:
        existing_value = _clean_value(
            existing_metadata.get(field)
            if field in existing_metadata
            else getattr(existing, field, None) if existing is not None else None
        )
        incoming_value = _clean_value(incoming.get(field))
        explicit_value = _clean_value(explicit.get(field))

        canonical_value = explicit_value or existing_value or incoming_value
        canonical[field] = canonical_value

        field_evidence = evidence.setdefault(field, [])
        if existing_value is not None:
            _append_evidence(
                field_evidence,
                value=existing_value,
                source_id="managed-inventory",
                authority="canonical",
            )
        if incoming_value is not None:
            _append_evidence(
                field_evidence,
                value=incoming_value,
                source_id=source_id,
                authority="source",
            )
        if explicit_value is not None:
            _append_evidence(
                field_evidence,
                value=explicit_value,
                source_id=source_id,
                authority="human",
            )

        distinct_values = _distinct_values(
            entry.get("value")
            for entry in field_evidence
            if isinstance(entry, dict)
        )
        if len(distinct_values) > 1:
            conflicts[field] = {
                "canonical_value": canonical_value,
                "candidate_values": distinct_values,
                "status": "review_required",
            }

    return canonical, evidence, conflicts


def _clean_value(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return cleaned or None
    return value


def _append_evidence(
    entries: list[dict[str, Any]],
    *,
    value: Any,
    source_id: str,
    authority: str,
) -> None:
    candidate = {
        "value": value,
        "source_id": source_id,
        "authority": authority,
    }
    if candidate not in entries:
        entries.append(candidate)


def _distinct_values(values: Iterable[Any]) -> list[Any]:
    output: list[Any] = []
    for value in values:
        if value is None:
            continue
        if value not in output:
            output.append(value)
    return output
