"""KR-3 import staging service.

Converts a validated ImportPayload into candidate managed KR records and
a single EvidenceRecord representing the import source.

Staged records carry:
  status = GovernanceStatus.CANDIDATE
  source_type from payload.source
  source_reference from payload.source
  change_reason describing the import batch
  evidence_refs linking to the batch EvidenceRecord

Staged candidate records are NOT production-eligible.  They do not
affect KR-1 production endpoints or the classifier layer.
No approval / promotion endpoint is added in KR-3.

Call validate_import_payload() first and only call stage_import_payload()
when the validation result is valid.

Storage decision (KR-3):
  KR-3 uses the same in-memory ManagedKRRepository as KR-2.  Persistent
  file-backed candidate storage is deferred to a later block.  Staged
  candidates survive for the lifetime of the running backend process only.
  Staged candidates are NOT committed to Git.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .governance import GovernanceStatus
from .import_models import ImportPayload
from .managed_models import (
    AliasRecord,
    StandardMnemonicRecord,
    ClassificationRuleRecord,
    CurveDefinitionRecord,
    DisplayRuleRecord,
    EvidenceRecord,
    TemplateRuleRecord,
)
from .managed_repository import ManagedKRRepository


# ---------------------------------------------------------------------------
# Staging result
# ---------------------------------------------------------------------------


@dataclass
class ImportStagingResult:
    """Summary of a successful import staging operation."""

    import_batch_id: str
    candidate_record_count: int
    evidence_record_count: int
    record_ids: list[str] = field(default_factory=list)
    record_type_counts: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _generate_batch_id() -> str:
    """Return a short UUID-based batch identifier like 'kr_import_a3f1b2c9e04d'."""
    return f"kr_import_{uuid.uuid4().hex[:12]}"


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Public staging function
# ---------------------------------------------------------------------------


def stage_import_payload(
    payload: ImportPayload,
    repository: ManagedKRRepository,
    batch_id: str | None = None,
) -> ImportStagingResult:
    """Stage a validated ImportPayload as candidate records in ``repository``.

    MUTATES ``repository`` by calling _add_record() and _add_evidence().
    Always call validate_import_payload() first; this function assumes the
    payload is structurally valid.

    Args:
        payload:    A previously validated import payload.
        repository: The ManagedKRRepository to add candidate records to.
        batch_id:   Optional deterministic batch ID (useful for tests).
                    Generated automatically if None.

    Returns:
        ImportStagingResult summarising the staged records.
    """
    if batch_id is None:
        batch_id = _generate_batch_id()

    now = _utcnow()
    change_reason = f"Staged via KR-3 import (batch={batch_id})"
    record_ids: list[str] = []

    # ------------------------------------------------------------------
    # 1. Create the import source EvidenceRecord
    # ------------------------------------------------------------------
    evidence_id = f"import_evidence_{batch_id}"
    evidence_record = EvidenceRecord(
        evidence_id=evidence_id,
        source_type=payload.source.source_type,
        source_label=payload.source.source_label,
        source_reference=payload.source.source_reference,
        source_file=payload.source.source_file,
        notes=payload.source.notes,
        created_at=now,
    )
    repository._add_evidence(evidence_record)
    evidence_refs = [evidence_id]

    # ------------------------------------------------------------------
    # 2. Stage curve definitions → CurveDefinitionRecord (CANDIDATE)
    # ------------------------------------------------------------------
    curve_def_ids: list[str] = []
    for cd in payload.curve_definitions:
        record_id = f"import_{batch_id}_curve_def_{cd.canonical_curve_id}"
        record = CurveDefinitionRecord(
            record_id=record_id,
            canonical_curve_id=cd.canonical_curve_id,
            display_name=cd.display_name,
            family=cd.family,
            product_group=cd.product_group,
            product_subgroup=cd.product_subgroup,
            default_unit=cd.default_unit,
            description=cd.description,
            status=GovernanceStatus.CANDIDATE,
            version=1,
            source_type=payload.source.source_type,
            source_reference=payload.source.source_reference,
            created_at=now,
            updated_at=now,
            created_by="import",
            change_reason=change_reason,
            evidence_refs=list(evidence_refs),
        )
        repository._add_record(record)
        record_ids.append(record_id)
        curve_def_ids.append(record_id)

    # ------------------------------------------------------------------
    # 3. Stage standard mnemonics → StandardMnemonicRecord (CANDIDATE)
    # ------------------------------------------------------------------
    standard_mnemonic_ids: list[str] = []
    for cd in payload.curve_definitions:
        for mnemonic in cd.standard_mnemonics:
            normalized = mnemonic.strip().upper()
            record_id = f"import_{batch_id}_standard_mnemonic_{normalized}_{cd.canonical_curve_id}"
            record = StandardMnemonicRecord(
                record_id=record_id,
                mnemonic=mnemonic,
                normalized_mnemonic=normalized,
                canonical_curve_id=cd.canonical_curve_id,
                unit_hint=cd.default_unit,
                description_hint=cd.display_name,
                confidence=1.0,
                status=GovernanceStatus.CANDIDATE,
                evidence_refs=list(evidence_refs),
                created_at=now,
                updated_at=now,
                change_reason=change_reason,
            )
            repository._add_record(record)
            record_ids.append(record_id)
            standard_mnemonic_ids.append(record_id)

    # ------------------------------------------------------------------
    # 4. Stage aliases → AliasRecord (CANDIDATE)
    # ------------------------------------------------------------------
    alias_ids: list[str] = []
    for cd in payload.curve_definitions:
        for alias in cd.aliases:
            normalized = alias.strip().upper()
            record_id = f"import_{batch_id}_alias_{normalized}_{cd.canonical_curve_id}"
            record = AliasRecord(
                record_id=record_id,
                alias=alias,
                normalized_alias=normalized,
                canonical_curve_id=cd.canonical_curve_id,
                unit_hint=cd.default_unit,
                description_hint=cd.display_name,
                confidence=1.0,
                status=GovernanceStatus.CANDIDATE,
                evidence_refs=list(evidence_refs),
                created_at=now,
                updated_at=now,
                change_reason=change_reason,
            )
            repository._add_record(record)
            record_ids.append(record_id)
            alias_ids.append(record_id)

    # ------------------------------------------------------------------
    # 5. Stage display rules → DisplayRuleRecord (CANDIDATE)
    # ------------------------------------------------------------------
    display_rule_ids: list[str] = []
    for dr in payload.display_rules:
        record_id = f"import_{batch_id}_display_{dr.canonical_curve_id}"
        record = DisplayRuleRecord(
            record_id=record_id,
            canonical_curve_id=dr.canonical_curve_id,
            preferred_track_family=dr.preferred_track_family,
            scale_type=dr.scale_type,
            display_min=dr.display_min,
            display_max=dr.display_max,
            default_unit=dr.default_unit,
            reverse_scale=dr.reverse_scale,
            overlay_group=dr.overlay_group,
            status=GovernanceStatus.CANDIDATE,
            version=1,
            evidence_refs=list(evidence_refs),
            created_at=now,
            updated_at=now,
            change_reason=change_reason,
        )
        repository._add_record(record)
        record_ids.append(record_id)
        display_rule_ids.append(record_id)

    # ------------------------------------------------------------------
    # 6. Stage classification rules → ClassificationRuleRecord (CANDIDATE)
    # ------------------------------------------------------------------
    class_rule_ids: list[str] = []
    for cr in payload.classification_rules:
        record_id = f"import_{batch_id}_class_{cr.rule_key}"
        record = ClassificationRuleRecord(
            record_id=record_id,
            rule_key=cr.rule_key,
            match_type=cr.match_type,
            match_value=cr.match_value,
            product_group=cr.product_group,
            product_subgroup=cr.product_subgroup,
            curve_family=cr.curve_family,
            confidence=cr.confidence,
            context_requirements=list(cr.context_requirements),
            status=GovernanceStatus.CANDIDATE,
            version=1,
            evidence_refs=list(evidence_refs),
            created_at=now,
            updated_at=now,
            change_reason=change_reason,
        )
        repository._add_record(record)
        record_ids.append(record_id)
        class_rule_ids.append(record_id)

    # ------------------------------------------------------------------
    # 7. Stage template rules → TemplateRuleRecord (CANDIDATE)
    # ------------------------------------------------------------------
    template_rule_ids: list[str] = []
    for tr in payload.template_rules:
        record_id = f"import_{batch_id}_template_{tr.template_key}"
        record = TemplateRuleRecord(
            record_id=record_id,
            template_key=tr.template_key,
            template_label=tr.template_label,
            track_order=list(tr.track_order),
            required_curve_families=list(tr.required_curve_families),
            preferred_curve_families=list(tr.preferred_curve_families),
            fallback_curve_families=list(tr.fallback_curve_families),
            overlay_rules=list(tr.overlay_rules),
            missing_curve_behavior=tr.missing_curve_behavior,
            status=GovernanceStatus.CANDIDATE,
            version=1,
            evidence_refs=list(evidence_refs),
            created_at=now,
            updated_at=now,
            change_reason=change_reason,
        )
        repository._add_record(record)
        record_ids.append(record_id)
        template_rule_ids.append(record_id)

    # ------------------------------------------------------------------
    # 8. Return staging summary
    # ------------------------------------------------------------------
    record_type_counts: dict[str, int] = {
        "curve_definition": len(curve_def_ids),
        "standard_mnemonic": len(standard_mnemonic_ids),
        "alias": len(alias_ids),
        "display_rule": len(display_rule_ids),
        "classification_rule": len(class_rule_ids),
        "template_rule": len(template_rule_ids),
        "evidence": 1,
    }

    return ImportStagingResult(
        import_batch_id=batch_id,
        candidate_record_count=len(record_ids),
        evidence_record_count=1,
        record_ids=record_ids,
        record_type_counts=record_type_counts,
    )
