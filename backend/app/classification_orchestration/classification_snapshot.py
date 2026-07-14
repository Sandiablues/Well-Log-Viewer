"""Exact classification-state snapshot and rollback support.

This service is deliberately persistence-agnostic.  Callers supply managed
records as mappings and an explicit stable identity field.  The snapshot stores
only classification-owned fields plus a deterministic checksum.

Phase 13 does not execute bulk reclassification; this module proves that a
future migration can snapshot and restore exact prior classification state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping, MutableMapping


SNAPSHOT_VERSION = "classification-state-snapshot-v1"
DEFAULT_CLASSIFICATION_FIELDS = (
    "curve_family",
    "curve_family_key",
    "curve_family_label",
    "classification_status",
    "classification_confidence",
    "classification_source",
    "classification_reasons",
    "review_required",
    "classifier_version",
    "policy_version",
    "ontology_version",
)


@dataclass(frozen=True)
class ClassificationStateSnapshot:
    identity_field: str
    fields: tuple[str, ...]
    records: tuple[Mapping[str, Any], ...]
    checksum_sha256: str
    snapshot_version: str = SNAPSHOT_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_version": self.snapshot_version,
            "identity_field": self.identity_field,
            "fields": list(self.fields),
            "records": [dict(item) for item in self.records],
            "checksum_sha256": self.checksum_sha256,
        }


def _canonical_payload(identity_field: str, fields: tuple[str, ...], records: list[dict[str, Any]]) -> bytes:
    return json.dumps(
        {
            "snapshot_version": SNAPSHOT_VERSION,
            "identity_field": identity_field,
            "fields": list(fields),
            "records": records,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def create_classification_snapshot(
    records: Iterable[Mapping[str, Any]],
    *,
    identity_field: str = "managed_curve_uid",
    fields: tuple[str, ...] = DEFAULT_CLASSIFICATION_FIELDS,
) -> ClassificationStateSnapshot:
    captured: list[dict[str, Any]] = []
    seen: set[str] = set()

    for record in records:
        identity = record.get(identity_field)
        if identity is None or str(identity).strip() == "":
            raise ValueError(f"Missing required snapshot identity field: {identity_field}")
        key = str(identity)
        if key in seen:
            raise ValueError(f"Duplicate snapshot identity: {key}")
        seen.add(key)

        item: dict[str, Any] = {identity_field: identity}
        for field in fields:
            item[field] = record.get(field)
        captured.append(item)

    captured.sort(key=lambda item: str(item[identity_field]))
    payload = _canonical_payload(identity_field, fields, captured)
    checksum = hashlib.sha256(payload).hexdigest()
    return ClassificationStateSnapshot(
        identity_field=identity_field,
        fields=fields,
        records=tuple(captured),
        checksum_sha256=checksum,
    )


def verify_classification_snapshot(snapshot: ClassificationStateSnapshot) -> bool:
    payload = _canonical_payload(
        snapshot.identity_field,
        snapshot.fields,
        [dict(item) for item in snapshot.records],
    )
    return hashlib.sha256(payload).hexdigest() == snapshot.checksum_sha256


def restore_classification_snapshot(
    live_records: Iterable[MutableMapping[str, Any]],
    snapshot: ClassificationStateSnapshot,
) -> None:
    if not verify_classification_snapshot(snapshot):
        raise ValueError("Classification snapshot checksum mismatch")

    by_id = {str(record[snapshot.identity_field]): record for record in live_records}
    snapshot_ids = {str(item[snapshot.identity_field]) for item in snapshot.records}

    missing = snapshot_ids.difference(by_id)
    if missing:
        raise KeyError(f"Live records missing snapshot identities: {sorted(missing)}")

    for item in snapshot.records:
        target = by_id[str(item[snapshot.identity_field])]
        for field in snapshot.fields:
            value = item.get(field)
            if value is None:
                target.pop(field, None)
            else:
                target[field] = value
