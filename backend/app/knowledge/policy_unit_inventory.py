"""Read-only inventory of governed WDV display-policy value units.

UNIT-2 inspects Managed Knowledge without mutating it.  Unit evidence is read
from the actual KR policy contracts:

* exact ``display_rule`` records carry ``default_unit``;
* family ``template_scale_default`` records carry ``unit_family``;
* a future explicit ``policy_value_unit`` always takes precedence.

Only unit-family tokens with one governed physical interpretation are mapped to
a canonical policy value unit.  Broad tokens such as ``length``,
``fraction_or_percent``, ``porosity_unit`` and ``engineering`` are deliberately
left for governed review; numeric bounds are never used to guess units.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from app.knowledge.managed_storage import DEFAULT_STORAGE_PATH
from app.wdv_display.policy_unit_contract import WdvPolicyUnitContract

INVENTORY_SCHEMA_VERSION = "wlv-policy-unit-inventory-v2"
EVIDENCE_CONTRACT_VERSION = "wlv-policy-unit-evidence-v2-actual-kr-schema"
DISPLAY_POLICY_RECORD_TYPES = frozenset({"template_scale_default", "display_rule"})
NON_LINE_SCALE_TYPES = frozenset(
    {"event_track", "waveform_track", "image_track", "tadpole_track"}
)

# These tokens have one explicit physical interpretation in the current KR.
# Values are normalized once more through WdvPolicyUnitContract before use.
UNAMBIGUOUS_UNIT_FAMILY_MAP: dict[str, str] = {
    "api": "gapi",
    "mv": "mv",
    "ohm_m": "ohmm",
    "g_per_cc": "g/cc",
    "us_per_ft": "us/ft",
    "barns_per_electron": "b/e",
    "md": "md",
}

# These tokens describe a dimension or multiple possible representations, not
# the physical unit of the stored scale values.
REVIEW_REQUIRED_UNIT_FAMILIES = frozenset(
    {
        "length",
        "porosity_unit",
        "fraction_or_percent",
        "engineering",
        "api_separate_channels",
        "event_or_curve",
        "waveform",
        "image",
        "degrees",
    }
)


class PolicyUnitInventoryStatus(str, Enum):
    EXPLICIT_SUPPORTED = "explicit_supported"
    EXPLICIT_UNKNOWN_UNIT = "explicit_unknown_unit"
    INFERABLE_SUPPORTED = "inferable_supported"
    AMBIGUOUS_REVIEW_REQUIRED = "ambiguous_review_required"
    NON_NUMERIC_OR_NON_LINE = "non_numeric_or_non_line"


@dataclass(frozen=True)
class PolicyUnitInventoryEntry:
    record_id: str
    record_type: str
    curve_family: str | None
    canonical_curve_id: str | None
    scale_type: str | None
    scale_min: float | None
    scale_max: float | None
    current_policy_value_unit: str | None
    normalized_policy_value_unit: str | None
    status: str
    proposed_policy_value_unit: str | None
    evidence_source: str | None
    evidence_raw_value: str | None
    evidence_normalized_unit: str | None
    reason: str


@dataclass(frozen=True)
class PolicyUnitInventoryReport:
    schema_version: str
    evidence_contract_version: str
    source_path: str
    source_sha256: str
    record_count: int
    eligible_policy_record_count: int
    status_counts: dict[str, int]
    entries: tuple[PolicyUnitInventoryEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_contract_version": self.evidence_contract_version,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "record_count": self.record_count,
            "eligible_policy_record_count": self.eligible_policy_record_count,
            "status_counts": dict(sorted(self.status_counts.items())),
            "entries": [asdict(entry) for entry in self.entries],
        }


class PolicyUnitInventoryService:
    """Build a deterministic, byte-for-byte read-only policy-unit inventory."""

    def __init__(self, *, storage_path: Path | None = None) -> None:
        self.storage_path = Path(storage_path or DEFAULT_STORAGE_PATH)

    def run(self) -> PolicyUnitInventoryReport:
        raw_bytes = self.storage_path.read_bytes()
        source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        document = json.loads(raw_bytes.decode("utf-8"))
        records = document.get("records")
        if not isinstance(records, list):
            raise ValueError("Managed knowledge document must contain a records list")

        entries = [
            self._classify(record)
            for record in records
            if self._is_eligible_policy_record(record)
        ]
        entries.sort(key=lambda item: (item.record_type, item.record_id))

        status_counts = {status.value: 0 for status in PolicyUnitInventoryStatus}
        for entry in entries:
            status_counts[entry.status] += 1

        return PolicyUnitInventoryReport(
            schema_version=INVENTORY_SCHEMA_VERSION,
            evidence_contract_version=EVIDENCE_CONTRACT_VERSION,
            source_path=str(self.storage_path.resolve()),
            source_sha256=source_sha256,
            record_count=len(records),
            eligible_policy_record_count=len(entries),
            status_counts=status_counts,
            entries=tuple(entries),
        )

    @staticmethod
    def _is_eligible_policy_record(record: Any) -> bool:
        return (
            isinstance(record, dict)
            and str(record.get("record_type") or "") in DISPLAY_POLICY_RECORD_TYPES
            and str(record.get("status") or "").strip().lower() == "approved"
            and record.get("runtime_eligible") is True
        )

    @classmethod
    def _classify(cls, record: dict[str, Any]) -> PolicyUnitInventoryEntry:
        record_type = str(record.get("record_type") or "")
        scale_min_key = "display_min" if record_type == "display_rule" else "scale_min"
        scale_max_key = "display_max" if record_type == "display_rule" else "scale_max"
        scale_min = cls._finite_float(record.get(scale_min_key))
        scale_max = cls._finite_float(record.get(scale_max_key))
        scale_type = cls._text(record.get("scale_type"))
        raw_policy_unit = cls._text(record.get("policy_value_unit"))
        normalized_policy_unit = WdvPolicyUnitContract.normalize_unit(raw_policy_unit)

        base = {
            "record_id": str(record.get("record_id") or ""),
            "record_type": record_type,
            "curve_family": cls._text(record.get("curve_family")),
            "canonical_curve_id": cls._text(record.get("canonical_curve_id")),
            "scale_type": scale_type,
            "scale_min": scale_min,
            "scale_max": scale_max,
            "current_policy_value_unit": raw_policy_unit,
            "normalized_policy_value_unit": normalized_policy_unit,
        }

        if scale_type in NON_LINE_SCALE_TYPES or scale_min is None or scale_max is None:
            return PolicyUnitInventoryEntry(
                **base,
                status=PolicyUnitInventoryStatus.NON_NUMERIC_OR_NON_LINE.value,
                proposed_policy_value_unit=None,
                evidence_source=None,
                evidence_raw_value=None,
                evidence_normalized_unit=None,
                reason="record_has_non_line_renderer_or_incomplete_numeric_bounds",
            )

        if raw_policy_unit is not None:
            if normalized_policy_unit is not None:
                return PolicyUnitInventoryEntry(
                    **base,
                    status=PolicyUnitInventoryStatus.EXPLICIT_SUPPORTED.value,
                    proposed_policy_value_unit=normalized_policy_unit,
                    evidence_source="record.policy_value_unit",
                    evidence_raw_value=raw_policy_unit,
                    evidence_normalized_unit=normalized_policy_unit,
                    reason="explicit_policy_value_unit_is_supported",
                )
            return PolicyUnitInventoryEntry(
                **base,
                status=PolicyUnitInventoryStatus.EXPLICIT_UNKNOWN_UNIT.value,
                proposed_policy_value_unit=None,
                evidence_source="record.policy_value_unit",
                evidence_raw_value=raw_policy_unit,
                evidence_normalized_unit=None,
                reason="explicit_policy_value_unit_is_not_supported_by_contract",
            )

        if record_type == "display_rule":
            raw_default_unit = cls._text(record.get("default_unit"))
            normalized = WdvPolicyUnitContract.normalize_unit(raw_default_unit)
            if normalized is not None:
                return PolicyUnitInventoryEntry(
                    **base,
                    status=PolicyUnitInventoryStatus.INFERABLE_SUPPORTED.value,
                    proposed_policy_value_unit=normalized,
                    evidence_source="display_rule.default_unit",
                    evidence_raw_value=raw_default_unit,
                    evidence_normalized_unit=normalized,
                    reason="exact_display_rule_default_unit_is_supported",
                )
            return PolicyUnitInventoryEntry(
                **base,
                status=PolicyUnitInventoryStatus.AMBIGUOUS_REVIEW_REQUIRED.value,
                proposed_policy_value_unit=None,
                evidence_source="display_rule.default_unit",
                evidence_raw_value=raw_default_unit,
                evidence_normalized_unit=None,
                reason=(
                    "exact_display_rule_default_unit_missing"
                    if raw_default_unit is None
                    else "exact_display_rule_default_unit_not_supported"
                ),
            )

        raw_unit_family = cls._text(record.get("unit_family"))
        mapped_unit = UNAMBIGUOUS_UNIT_FAMILY_MAP.get(raw_unit_family or "")
        normalized = WdvPolicyUnitContract.normalize_unit(mapped_unit)
        if normalized is not None:
            return PolicyUnitInventoryEntry(
                **base,
                status=PolicyUnitInventoryStatus.INFERABLE_SUPPORTED.value,
                proposed_policy_value_unit=normalized,
                evidence_source="template_scale_default.unit_family",
                evidence_raw_value=raw_unit_family,
                evidence_normalized_unit=normalized,
                reason="unit_family_has_one_governed_physical_interpretation",
            )

        if raw_unit_family in REVIEW_REQUIRED_UNIT_FAMILIES:
            reason = "unit_family_is_broad_or_multi_representation"
        elif raw_unit_family is None:
            reason = "unit_family_missing"
        else:
            reason = "unit_family_not_defined_in_evidence_contract"

        return PolicyUnitInventoryEntry(
            **base,
            status=PolicyUnitInventoryStatus.AMBIGUOUS_REVIEW_REQUIRED.value,
            proposed_policy_value_unit=None,
            evidence_source="template_scale_default.unit_family",
            evidence_raw_value=raw_unit_family,
            evidence_normalized_unit=None,
            reason=reason,
        )

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        return text or None

    @staticmethod
    def _finite_float(value: Any) -> float | None:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return numeric if math.isfinite(numeric) else None


def migration_manifest_candidate(report: PolicyUnitInventoryReport) -> dict[str, Any]:
    entries = [
        {
            "record_id": entry.record_id,
            "record_type": entry.record_type,
            "proposed_policy_value_unit": entry.proposed_policy_value_unit,
            "evidence_source": entry.evidence_source,
            "evidence_raw_value": entry.evidence_raw_value,
            "reason": entry.reason,
        }
        for entry in report.entries
        if entry.status == PolicyUnitInventoryStatus.INFERABLE_SUPPORTED.value
        and entry.proposed_policy_value_unit is not None
    ]
    return {
        "schema_version": "wlv-policy-unit-migration-manifest-candidate-v2",
        "source_sha256": report.source_sha256,
        "entry_count": len(entries),
        "entries": entries,
    }


def write_inventory_outputs(report: PolicyUnitInventoryReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dict = report.to_dict()
    (output_dir / "policy_unit_inventory.json").write_text(
        json.dumps(report_dict, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "policy_unit_migration_manifest_candidate.json").write_text(
        json.dumps(migration_manifest_candidate(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    fieldnames = [field.name for field in PolicyUnitInventoryEntry.__dataclass_fields__.values()]
    with (output_dir / "policy_unit_inventory.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for entry in report.entries:
            writer.writerow(asdict(entry))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-path", type=Path, default=DEFAULT_STORAGE_PATH)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    report = PolicyUnitInventoryService(storage_path=args.storage_path).run()
    write_inventory_outputs(report, args.output_dir)
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
