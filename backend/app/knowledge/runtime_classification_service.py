"""KR-CLASSIFY-1 — approved-only runtime curve classification service.

This module is the backend-owned product boundary for classifying well-log
curve mnemonics with runtime-safe KR knowledge.  It depends on the
KR-RUNTIME-1 ApprovedKnowledgeRuntimeResolver and therefore consumes only:

    seed + approved managed records

Candidate, rejected, and deprecated knowledge is intentionally excluded.  This
service does not mutate KR state, does not read frontend state, and does not
promote candidate knowledge.  It is designed for later LAS import, MDP, and WDV
consumers to call through backend contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .alias_enrichment_models import AliasEnrichmentRecord
from .managed_models import AliasRecord, CurveDefinitionRecord, DisplayRuleRecord, StandardMnemonicRecord
from .runtime_resolver import ApprovedKnowledgeRuntimeResolver, RuntimeKnowledgePolicy
from .contextual_curve_resolver import ContextualResolution, resolve_contextual_curve

KR_CLASSIFY_1_VERSION = "kr-classify-1"

_CLASSIFICATION_STATUS_RESOLVED = "resolved"
_CLASSIFICATION_STATUS_UNKNOWN = "unknown"
_CLASSIFICATION_STATUS_REQUIRES_REVIEW = "requires_review"

_RESOLUTION_SOURCE_STANDARD_MNEMONIC = "runtime_standard_mnemonic"
_RESOLUTION_SOURCE_ALIAS = "runtime_alias"
_RESOLUTION_SOURCE_CANONICAL = "runtime_canonical"
_RESOLUTION_SOURCE_CONTEXTUAL = "runtime_contextual_consensus"
_RESOLUTION_SOURCE_UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class CurveClassificationInput:
    """Input contract for one source curve.

    The service preserves caller-provided identity so later LAS/session layers
    can correlate the classification result back to the imported curve.
    """

    source_mnemonic: str
    curve_id: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    source_curve_index: Optional[int] = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeDisplayRule:
    """Runtime display hint attached to a classified canonical curve."""

    scale_type: str
    display_min: float
    display_max: float
    default_unit: Optional[str]
    preferred_track_family: Optional[str]
    reverse_scale: bool = False
    overlay_group: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "scale_type": self.scale_type,
            "display_min": self.display_min,
            "display_max": self.display_max,
            "default_unit": self.default_unit,
            "preferred_track_family": self.preferred_track_family,
            "reverse_scale": self.reverse_scale,
            "overlay_group": self.overlay_group,
        }


@dataclass(frozen=True)
class CurveClassificationResult:
    """Backend-owned classification result for one curve."""

    curve_id: Optional[str]
    source_curve_index: Optional[int]
    source_mnemonic: str
    normalized_mnemonic: str
    status: str
    resolved: bool
    requires_review: bool
    canonical_curve_id: Optional[str] = None
    display_name: Optional[str] = None
    family: Optional[str] = None
    product_group: Optional[str] = None
    product_subgroup: Optional[str] = None
    default_unit: Optional[str] = None
    confidence: float = 0.0
    resolution_source: str = _RESOLUTION_SOURCE_UNRESOLVED
    knowledge_record_id: Optional[str] = None
    technical_curve_id: Optional[str] = None
    technical_display_name: Optional[str] = None
    technical_family: Optional[str] = None
    measurement_family: Optional[str] = None
    measurement_depth: Optional[str] = None
    tool_family: Optional[str] = None
    display_rule: Optional[RuntimeDisplayRule] = None
    warnings: list[str] = field(default_factory=list)
    knowledge_policy: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "curve_id": self.curve_id,
            "source_curve_index": self.source_curve_index,
            "source_mnemonic": self.source_mnemonic,
            "normalized_mnemonic": self.normalized_mnemonic,
            "status": self.status,
            "resolved": self.resolved,
            "requires_review": self.requires_review,
            "canonical_curve_id": self.canonical_curve_id,
            "display_name": self.display_name,
            "family": self.family,
            "product_group": self.product_group,
            "product_subgroup": self.product_subgroup,
            "default_unit": self.default_unit,
            "confidence": self.confidence,
            "resolution_source": self.resolution_source,
            "knowledge_record_id": self.knowledge_record_id,
            "technical_curve_id": self.technical_curve_id,
            "technical_display_name": self.technical_display_name,
            "technical_family": self.technical_family,
            "measurement_family": self.measurement_family,
            "measurement_depth": self.measurement_depth,
            "tool_family": self.tool_family,
            "display_rule": self.display_rule.as_dict() if self.display_rule else None,
            "warnings": list(self.warnings),
            "knowledge_policy": dict(self.knowledge_policy),
        }


@dataclass(frozen=True)
class CurveClassificationBatchResult:
    """Ordered classification result for a curve batch."""

    classify_version: str
    curve_count: int
    resolved_count: int
    unknown_count: int
    review_required_count: int
    classifications: tuple[CurveClassificationResult, ...]
    knowledge_policy: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "classify_version": self.classify_version,
            "curve_count": self.curve_count,
            "resolved_count": self.resolved_count,
            "unknown_count": self.unknown_count,
            "review_required_count": self.review_required_count,
            "knowledge_policy": dict(self.knowledge_policy),
            "classifications": [item.as_dict() for item in self.classifications],
        }


class RuntimeCurveClassificationService:
    """Classify well-log curves using approved-only runtime KR knowledge."""

    def __init__(self, runtime_resolver: ApprovedKnowledgeRuntimeResolver) -> None:
        self._runtime_resolver = runtime_resolver

    def classify_curve(self, curve: CurveClassificationInput) -> CurveClassificationResult:
        """Classify one curve using the current approved-only runtime snapshot."""
        snapshot = self._runtime_resolver.build_snapshot()
        policy = snapshot.policy
        return self._classify_one(curve, policy)

    def classify_curves(
        self,
        curves: list[CurveClassificationInput],
    ) -> CurveClassificationBatchResult:
        """Classify a batch of curves.  Input order is preserved."""
        snapshot = self._runtime_resolver.build_snapshot()
        policy = snapshot.policy
        classifications = tuple(self._classify_one(curve, policy) for curve in curves)
        resolved_count = sum(1 for item in classifications if item.resolved)
        unknown_count = sum(1 for item in classifications if item.status == _CLASSIFICATION_STATUS_UNKNOWN)
        review_required_count = sum(1 for item in classifications if item.requires_review)
        return CurveClassificationBatchResult(
            classify_version=KR_CLASSIFY_1_VERSION,
            curve_count=len(classifications),
            resolved_count=resolved_count,
            unknown_count=unknown_count,
            review_required_count=review_required_count,
            classifications=classifications,
            knowledge_policy=policy.as_dict(),
        )

    def _classify_one(
        self,
        curve: CurveClassificationInput,
        policy: RuntimeKnowledgePolicy,
    ) -> CurveClassificationResult:
        source_mnemonic = curve.source_mnemonic or ""
        normalized = source_mnemonic.strip().upper()
        canonical_key = source_mnemonic.strip().lower()

        standard_records = self._runtime_standard_mnemonic_records()
        alias_records = self._runtime_alias_records()
        curve_defs = self._runtime_curve_definitions()
        display_rules = self._runtime_display_rules()

        matched_standard = self._find_standard_mnemonic(standard_records, source_mnemonic, normalized)
        if matched_standard is not None:
            curve_def = self._find_curve_definition(curve_defs, matched_standard.canonical_curve_id)
            if curve_def is None:
                return self._unknown_result(
                    curve,
                    normalized,
                    policy,
                    warnings=[
                        f"Runtime standard mnemonic {matched_standard.mnemonic} points to missing canonical curve "
                        f"{matched_standard.canonical_curve_id}"
                    ],
                )
            return self._resolved_result(
                curve=curve,
                normalized=normalized,
                policy=policy,
                curve_def=curve_def,
                source=_RESOLUTION_SOURCE_STANDARD_MNEMONIC,
                knowledge_record_id=matched_standard.record_id,
                confidence=float(getattr(matched_standard, "confidence", 1.0) or 1.0),
                display_rule=self._display_rule_for(display_rules, curve_def.canonical_curve_id),
                enrichment=None,
            )

        matched_alias = self._find_alias(alias_records, source_mnemonic, normalized)
        if matched_alias is not None:
            curve_def = self._find_curve_definition(curve_defs, matched_alias.canonical_curve_id)
            if curve_def is None:
                return self._unknown_result(
                    curve,
                    normalized,
                    policy,
                    warnings=[
                        f"Runtime alias {matched_alias.alias} points to missing canonical curve "
                        f"{matched_alias.canonical_curve_id}"
                    ],
                )
            enrichment = self._approved_enrichment_for_alias(
                normalized_alias=normalized,
                display_canonical_curve_id=matched_alias.canonical_curve_id,
            )
            return self._resolved_result(
                curve=curve,
                normalized=normalized,
                policy=policy,
                curve_def=curve_def,
                source=_RESOLUTION_SOURCE_ALIAS,
                knowledge_record_id=matched_alias.record_id,
                confidence=float(getattr(matched_alias, "confidence", 1.0) or 1.0),
                display_rule=self._display_rule_for(display_rules, curve_def.canonical_curve_id),
                enrichment=enrichment,
            )

        matched_curve_def = self._find_curve_definition(curve_defs, canonical_key)
        if matched_curve_def is not None:
            return self._resolved_result(
                curve=curve,
                normalized=normalized,
                policy=policy,
                curve_def=matched_curve_def,
                source=_RESOLUTION_SOURCE_CANONICAL,
                knowledge_record_id=matched_curve_def.record_id,
                confidence=1.0,
                display_rule=self._display_rule_for(display_rules, matched_curve_def.canonical_curve_id),
                enrichment=None,
            )

        contextual = resolve_contextual_curve(
            source_mnemonic=curve.source_mnemonic,
            description=curve.description,
            unit=curve.unit,
            curve_definitions=curve_defs,
        )
        if contextual is not None:
            return self._contextual_result(curve, normalized, policy, contextual, display_rules)

        return self._unknown_result(
            curve, normalized, policy,
            warnings=["No approved runtime knowledge match found"],
        )

    def _runtime_standard_mnemonic_records(self) -> list[StandardMnemonicRecord]:
        return [
            record for record in self._runtime_resolver.list_runtime_records(record_type="standard_mnemonic")
            if isinstance(record, StandardMnemonicRecord)
        ]

    def _runtime_alias_records(self) -> list[AliasRecord]:
        return [
            record for record in self._runtime_resolver.list_runtime_records(record_type="alias")
            if isinstance(record, AliasRecord)
        ]

    def _runtime_curve_definitions(self) -> list[CurveDefinitionRecord]:
        return [
            record for record in self._runtime_resolver.list_runtime_records(record_type="curve_definition")
            if isinstance(record, CurveDefinitionRecord)
        ]

    def _runtime_display_rules(self) -> list[DisplayRuleRecord]:
        return [
            record for record in self._runtime_resolver.list_runtime_records(record_type="display_rule")
            if isinstance(record, DisplayRuleRecord)
        ]

    @staticmethod
    def _find_standard_mnemonic(
        standard_records: list[StandardMnemonicRecord],
        source_mnemonic: str,
        normalized: str,
    ) -> Optional[StandardMnemonicRecord]:
        raw = source_mnemonic.strip()
        for record in standard_records:
            if record.mnemonic.strip().upper() == raw.upper():
                return record
        for record in standard_records:
            if record.normalized_mnemonic == normalized:
                return record
        return None

    @staticmethod
    def _find_alias(
        alias_records: list[AliasRecord],
        source_mnemonic: str,
        normalized: str,
    ) -> Optional[AliasRecord]:
        raw = source_mnemonic.strip()
        for record in alias_records:
            if record.alias.strip().upper() == raw.upper():
                return record
        for record in alias_records:
            if record.normalized_alias == normalized:
                return record
        return None

    @staticmethod
    def _find_curve_definition(
        curve_defs: list[CurveDefinitionRecord],
        canonical_curve_id: str,
    ) -> Optional[CurveDefinitionRecord]:
        for record in curve_defs:
            if record.canonical_curve_id == canonical_curve_id:
                return record
        return None

    @staticmethod
    def _display_rule_for(
        display_rules: list[DisplayRuleRecord],
        canonical_curve_id: str,
    ) -> Optional[RuntimeDisplayRule]:
        for record in display_rules:
            if record.canonical_curve_id == canonical_curve_id:
                return RuntimeDisplayRule(
                    scale_type=record.scale_type,
                    display_min=float(record.display_min),
                    display_max=float(record.display_max),
                    default_unit=record.default_unit,
                    preferred_track_family=record.preferred_track_family,
                    reverse_scale=bool(record.reverse_scale),
                    overlay_group=record.overlay_group,
                )
        return None

    def _approved_enrichment_for_alias(
        self,
        normalized_alias: str,
        display_canonical_curve_id: str,
    ) -> Optional[AliasEnrichmentRecord]:
        enrichments = self._runtime_resolver.list_approved_alias_enrichments(normalized_alias)
        matching = [
            item for item in enrichments
            if item.display_canonical_curve_id == display_canonical_curve_id
        ]
        if not matching:
            return None
        return sorted(matching, key=lambda item: item.selection_priority or 9999)[0]

    @staticmethod
    def _resolved_result(
        curve: CurveClassificationInput,
        normalized: str,
        policy: RuntimeKnowledgePolicy,
        curve_def: CurveDefinitionRecord,
        source: str,
        knowledge_record_id: str,
        confidence: float,
        display_rule: Optional[RuntimeDisplayRule],
        enrichment: Optional[AliasEnrichmentRecord],
    ) -> CurveClassificationResult:
        return CurveClassificationResult(
            curve_id=curve.curve_id,
            source_curve_index=curve.source_curve_index,
            source_mnemonic=curve.source_mnemonic,
            normalized_mnemonic=normalized,
            status=_CLASSIFICATION_STATUS_RESOLVED,
            resolved=True,
            requires_review=False,
            canonical_curve_id=curve_def.canonical_curve_id,
            display_name=curve_def.display_name,
            family=curve_def.family,
            product_group=curve_def.product_group,
            product_subgroup=curve_def.product_subgroup,
            default_unit=curve_def.default_unit,
            confidence=confidence,
            resolution_source=source,
            knowledge_record_id=knowledge_record_id,
            technical_curve_id=enrichment.technical_curve_id if enrichment else None,
            technical_display_name=enrichment.technical_display_name if enrichment else None,
            technical_family=enrichment.technical_family if enrichment else None,
            measurement_family=enrichment.measurement_family if enrichment else None,
            measurement_depth=enrichment.measurement_depth if enrichment else None,
            tool_family=enrichment.tool_family if enrichment else None,
            display_rule=display_rule,
            warnings=[],
            knowledge_policy=policy.as_dict(),
        )

    @staticmethod
    def _contextual_result(curve, normalized, policy, contextual: ContextualResolution, display_rules):
        display_rule = RuntimeCurveClassificationService._display_rule_for(display_rules, contextual.canonical_curve_id) if contextual.canonical_curve_id else None
        warnings = list(contextual.warnings)
        if contextual.supporting_record_ids:
            warnings.append("Supporting approved KR records: " + ", ".join(contextual.supporting_record_ids[:8]))
        return CurveClassificationResult(
            curve_id=curve.curve_id, source_curve_index=curve.source_curve_index,
            source_mnemonic=curve.source_mnemonic, normalized_mnemonic=normalized,
            status=_CLASSIFICATION_STATUS_RESOLVED, resolved=True, requires_review=False,
            canonical_curve_id=contextual.canonical_curve_id, display_name=contextual.display_name,
            family=contextual.family, product_group=contextual.product_group, product_subgroup=contextual.product_subgroup,
            default_unit=contextual.default_unit, confidence=contextual.confidence,
            resolution_source=_RESOLUTION_SOURCE_CONTEXTUAL, knowledge_record_id=contextual.knowledge_record_id,
            display_rule=display_rule, warnings=warnings, knowledge_policy=policy.as_dict(),
        )

    @staticmethod
    def _unknown_result(
        curve: CurveClassificationInput,
        normalized: str,
        policy: RuntimeKnowledgePolicy,
        warnings: list[str],
    ) -> CurveClassificationResult:
        return CurveClassificationResult(
            curve_id=curve.curve_id,
            source_curve_index=curve.source_curve_index,
            source_mnemonic=curve.source_mnemonic,
            normalized_mnemonic=normalized,
            status=_CLASSIFICATION_STATUS_UNKNOWN,
            resolved=False,
            requires_review=True,
            canonical_curve_id=None,
            confidence=0.0,
            resolution_source=_RESOLUTION_SOURCE_UNRESOLVED,
            warnings=warnings,
            knowledge_policy=policy.as_dict(),
        )
