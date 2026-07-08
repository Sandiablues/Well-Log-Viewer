"""WLV KR-6 — Backend Knowledge Resolution Service.

Backend-owned service that resolves a curve mnemonic into a stable, structured
contract using only production-eligible managed knowledge (seed + approved).

Architecture contract
---------------------
* Backend owns resolution truth.
* Frontend renders backend contracts only.
* Candidates, rejected, and deprecated records are NEVER used for resolution.
* Seed records are valid production knowledge.
* Approved managed records override or extend seed records.
* Display rules are returned when an approved or seed display rule exists for
  the resolved canonical curve.
* The service is offline-capable: no network calls, no external deps.
* Storage is replaceable — the service depends only on ManagedKRRepository,
  not on any specific storage implementation.

Resolution priority chain
--------------------------
1. Standard mnemonic match — StandardMnemonicRecord.mnemonic/normalized_mnemonic
                              status in {SEED, APPROVED}
2. Alias match             — AliasRecord.alias/normalized_alias
                              status in {SEED, APPROVED}
3. Canonical ID match       — CurveDefinitionRecord.canonical_curve_id == lower(mnemonic)
                              status in {SEED, APPROVED}

Candidates, rejected, and deprecated records do not participate in any step.

Batch endpoint
--------------
``resolve_curves`` accepts a list of CurveResolveInput and returns an ordered
list of CurveResolveResult.  Input order is strictly preserved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .governance import GovernanceStatus, PRODUCTION_STATUSES
from .managed_models import AliasRecord, CurveDefinitionRecord, DisplayRuleRecord, StandardMnemonicRecord
from .managed_repository import GovernedRecord, ManagedKRRepository

KR6_VERSION = "kr-6"

# ---------------------------------------------------------------------------
# Resolution source labels
# ---------------------------------------------------------------------------

_SOURCE_SEED_STANDARD_MNEMONIC = "seed_standard_mnemonic"
_SOURCE_MANAGED_STANDARD_MNEMONIC = "managed_standard_mnemonic"
_SOURCE_SEED_ALIAS = "seed_alias"
_SOURCE_MANAGED_ALIAS = "managed_alias"
_SOURCE_SEED_CANONICAL = "seed_canonical"
_SOURCE_MANAGED_CANONICAL = "managed_canonical"
_SOURCE_UNRESOLVED = "unresolved"


# ---------------------------------------------------------------------------
# Input / output dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CurveResolveInput:
    """Input contract for a single mnemonic resolution request."""

    mnemonic: str
    unit: Optional[str] = None
    description: Optional[str] = None
    context: Optional[dict] = field(default_factory=dict)


@dataclass
class DisplayRuleResult:
    """Resolved display rule for a canonical curve."""

    scale_type: str
    recommended_min: float
    recommended_max: float
    unit: Optional[str]
    preferred_track_family: Optional[str] = None


@dataclass
class CurveResolveResult:
    """Resolution result for a single mnemonic.

    When resolved=True, canonical_curve_id and all classification fields are
    populated.  When resolved=False, only mnemonic, normalized_mnemonic, and
    warnings are meaningful.
    """

    resolved: bool
    mnemonic: str
    normalized_mnemonic: str

    # Populated on success
    canonical_curve_id: Optional[str] = None
    display_name: Optional[str] = None
    family: Optional[str] = None
    product_group: Optional[str] = None
    product_subgroup: Optional[str] = None
    default_unit: Optional[str] = None
    confidence: float = 0.0
    resolution_source: str = _SOURCE_UNRESOLVED
    record_id: Optional[str] = None
    display_rule: Optional[DisplayRuleResult] = None

    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# KnowledgeResolutionService
# ---------------------------------------------------------------------------


class KnowledgeResolutionService:
    """Backend-owned curve mnemonic resolution service (KR-6).

    Resolves a mnemonic into a stable backend contract using only
    production-eligible managed knowledge (status ∈ {SEED, APPROVED}).

    Candidates, rejected, and deprecated records are always excluded.

    Usage::

        service = KnowledgeResolutionService(repo)
        result  = service.resolve_curve(CurveResolveInput(mnemonic="GR"))
        results = service.resolve_curves([CurveResolveInput(mnemonic="GR"), ...])
    """

    def __init__(self, repository: ManagedKRRepository) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_curve(self, input_: CurveResolveInput) -> CurveResolveResult:
        """Resolve a single mnemonic.  Never raises; unresolvable → resolved=False."""
        return self._resolve_one(input_)

    def resolve_curves(self, inputs: list[CurveResolveInput]) -> list[CurveResolveResult]:
        """Resolve a batch of mnemonics.  Input order is strictly preserved."""
        return [self._resolve_one(inp) for inp in inputs]

    # ------------------------------------------------------------------
    # Internal resolution logic
    # ------------------------------------------------------------------

    def _resolve_one(self, input_: CurveResolveInput) -> CurveResolveResult:
        """Execute the resolution priority chain for one mnemonic."""
        raw_mnemonic = input_.mnemonic or ""
        normalized = raw_mnemonic.strip().upper()

        # Build production-eligible index
        standard_records, alias_records, curve_def_records, display_rule_records = self._load_production_records()

        # ------------------------------------------------------------------
        # Step 1: Standard mnemonic match
        # ------------------------------------------------------------------
        matched_standard = self._find_standard_mnemonic(standard_records, raw_mnemonic, normalized)
        if matched_standard is not None:
            return self._result_from_standard_mnemonic(
                matched_standard, raw_mnemonic, normalized,
                curve_def_records, display_rule_records,
            )

        # ------------------------------------------------------------------
        # Step 2: Alias match (exact then normalized)
        # ------------------------------------------------------------------
        matched_alias = self._find_alias(alias_records, raw_mnemonic, normalized)
        if matched_alias is not None:
            return self._result_from_alias(
                matched_alias, raw_mnemonic, normalized,
                curve_def_records, display_rule_records,
            )

        # ------------------------------------------------------------------
        # Step 3: Canonical curve ID match
        # ------------------------------------------------------------------
        lower_mnemonic = raw_mnemonic.strip().lower()
        matched_def = self._find_canonical(curve_def_records, lower_mnemonic)
        if matched_def is not None:
            return self._result_from_curve_def(
                matched_def, raw_mnemonic, normalized, display_rule_records,
            )

        # ------------------------------------------------------------------
        # Unresolved
        # ------------------------------------------------------------------
        return CurveResolveResult(
            resolved=False,
            mnemonic=raw_mnemonic,
            normalized_mnemonic=normalized,
            canonical_curve_id=None,
            confidence=0.0,
            resolution_source=_SOURCE_UNRESOLVED,
            warnings=["No approved knowledge match found"],
        )

    # ------------------------------------------------------------------
    # Production-eligible record loading
    # ------------------------------------------------------------------

    def _load_production_records(
        self,
    ) -> tuple[list[StandardMnemonicRecord], list[AliasRecord], list[CurveDefinitionRecord], list[DisplayRuleRecord]]:
        """Load all production-eligible records, split by type.

        Production-eligible = status in {SEED, APPROVED}.
        Candidate, rejected, deprecated records are EXCLUDED.
        """
        all_production: list[GovernedRecord] = self._repo.list_production_eligible()

        standard_records: list[StandardMnemonicRecord] = []
        alias_records: list[AliasRecord] = []
        curve_def_records: list[CurveDefinitionRecord] = []
        display_rule_records: list[DisplayRuleRecord] = []

        for record in all_production:
            if isinstance(record, StandardMnemonicRecord):
                standard_records.append(record)
            elif isinstance(record, AliasRecord):
                alias_records.append(record)
            elif isinstance(record, CurveDefinitionRecord):
                curve_def_records.append(record)
            elif isinstance(record, DisplayRuleRecord):
                display_rule_records.append(record)

        return standard_records, alias_records, curve_def_records, display_rule_records

    # ------------------------------------------------------------------
    # Standard mnemonic matching
    # ------------------------------------------------------------------

    def _find_standard_mnemonic(
        self,
        standard_records: list[StandardMnemonicRecord],
        raw_mnemonic: str,
        normalized: str,
    ) -> Optional[StandardMnemonicRecord]:
        exact = [
            r for r in standard_records
            if r.mnemonic.strip().upper() == normalized
        ]
        if exact:
            return max(exact, key=lambda r: r.confidence)
        norm_match = [
            r for r in standard_records
            if r.normalized_mnemonic == normalized
        ]
        if norm_match:
            return max(norm_match, key=lambda r: r.confidence)
        return None

    # ------------------------------------------------------------------
    # Alias matching — Steps 1 and 2
    # ------------------------------------------------------------------

    def _find_alias(
        self,
        alias_records: list[AliasRecord],
        raw_mnemonic: str,
        normalized: str,
    ) -> Optional[AliasRecord]:
        """Return the first matching production-eligible alias, or None.

        Priority:
          1. Exact match: record.alias == raw_mnemonic (case-insensitive via normalized)
          2. Normalized match: record.normalized_alias == normalized

        Both steps only consider SEED and APPROVED aliases (already filtered by
        _load_production_records).  Confidence is used as a tiebreaker within
        each step (higher confidence wins).
        """
        # Step 1: exact alias match (compare normalised form both sides to handle
        # mixed-case inputs; the record stores the original alias, normalised_alias
        # is the upper-case canonical form)
        exact: list[AliasRecord] = [
            r for r in alias_records
            if r.alias.strip().upper() == normalized
        ]
        if exact:
            return max(exact, key=lambda r: r.confidence)

        # Step 2: normalized alias match
        norm_match: list[AliasRecord] = [
            r for r in alias_records
            if r.normalized_alias == normalized
        ]
        if norm_match:
            return max(norm_match, key=lambda r: r.confidence)

        return None

    # ------------------------------------------------------------------
    # Canonical curve definition matching — Step 3
    # ------------------------------------------------------------------

    def _find_canonical(
        self,
        curve_def_records: list[CurveDefinitionRecord],
        lower_mnemonic: str,
    ) -> Optional[CurveDefinitionRecord]:
        """Return the first production-eligible CurveDefinitionRecord whose
        canonical_curve_id matches lower_mnemonic, or None.
        """
        for record in curve_def_records:
            if record.canonical_curve_id.strip().lower() == lower_mnemonic:
                return record
        return None

    # ------------------------------------------------------------------
    # Result builders
    # ------------------------------------------------------------------

    def _result_from_standard_mnemonic(
        self,
        standard: StandardMnemonicRecord,
        raw_mnemonic: str,
        normalized: str,
        curve_def_records: list[CurveDefinitionRecord],
        display_rule_records: list[DisplayRuleRecord],
    ) -> CurveResolveResult:
        """Build a resolved result from a matched StandardMnemonicRecord."""
        resolution_source = (
            _SOURCE_SEED_STANDARD_MNEMONIC
            if standard.status == GovernanceStatus.SEED
            else _SOURCE_MANAGED_STANDARD_MNEMONIC
        )

        curve_def = self._find_curve_def_by_id(curve_def_records, standard.canonical_curve_id)
        display_rule = self._find_display_rule(display_rule_records, standard.canonical_curve_id)

        return CurveResolveResult(
            resolved=True,
            mnemonic=raw_mnemonic,
            normalized_mnemonic=normalized,
            canonical_curve_id=standard.canonical_curve_id,
            display_name=curve_def.display_name if curve_def else None,
            family=curve_def.family if curve_def else None,
            product_group=curve_def.product_group if curve_def else None,
            product_subgroup=curve_def.product_subgroup if curve_def else None,
            default_unit=curve_def.default_unit if curve_def else standard.unit_hint,
            confidence=standard.confidence,
            resolution_source=resolution_source,
            record_id=standard.record_id,
            display_rule=display_rule,
            warnings=[],
        )

    def _result_from_alias(
        self,
        alias: AliasRecord,
        raw_mnemonic: str,
        normalized: str,
        curve_def_records: list[CurveDefinitionRecord],
        display_rule_records: list[DisplayRuleRecord],
    ) -> CurveResolveResult:
        """Build a resolved result from a matched AliasRecord."""
        resolution_source = (
            _SOURCE_SEED_ALIAS
            if alias.status == GovernanceStatus.SEED
            else _SOURCE_MANAGED_ALIAS
        )

        # Find the corresponding CurveDefinitionRecord
        curve_def = self._find_curve_def_by_id(curve_def_records, alias.canonical_curve_id)

        # Find display rule
        display_rule = self._find_display_rule(display_rule_records, alias.canonical_curve_id)

        return CurveResolveResult(
            resolved=True,
            mnemonic=raw_mnemonic,
            normalized_mnemonic=normalized,
            canonical_curve_id=alias.canonical_curve_id,
            display_name=curve_def.display_name if curve_def else None,
            family=curve_def.family if curve_def else None,
            product_group=curve_def.product_group if curve_def else None,
            product_subgroup=curve_def.product_subgroup if curve_def else None,
            default_unit=curve_def.default_unit if curve_def else alias.unit_hint,
            confidence=alias.confidence,
            resolution_source=resolution_source,
            record_id=alias.record_id,
            display_rule=display_rule,
            warnings=[],
        )

    def _result_from_curve_def(
        self,
        curve_def: CurveDefinitionRecord,
        raw_mnemonic: str,
        normalized: str,
        display_rule_records: list[DisplayRuleRecord],
    ) -> CurveResolveResult:
        """Build a resolved result from a matched CurveDefinitionRecord."""
        resolution_source = (
            _SOURCE_SEED_CANONICAL
            if curve_def.status == GovernanceStatus.SEED
            else _SOURCE_MANAGED_CANONICAL
        )

        display_rule = self._find_display_rule(display_rule_records, curve_def.canonical_curve_id)

        return CurveResolveResult(
            resolved=True,
            mnemonic=raw_mnemonic,
            normalized_mnemonic=normalized,
            canonical_curve_id=curve_def.canonical_curve_id,
            display_name=curve_def.display_name,
            family=curve_def.family,
            product_group=curve_def.product_group,
            product_subgroup=curve_def.product_subgroup,
            default_unit=curve_def.default_unit,
            confidence=1.0,
            resolution_source=resolution_source,
            record_id=curve_def.record_id,
            display_rule=display_rule,
            warnings=[],
        )

    # ------------------------------------------------------------------
    # Lookup helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_curve_def_by_id(
        curve_def_records: list[CurveDefinitionRecord],
        canonical_curve_id: str,
    ) -> Optional[CurveDefinitionRecord]:
        """Return the production-eligible CurveDefinitionRecord for a canonical ID."""
        for record in curve_def_records:
            if record.canonical_curve_id == canonical_curve_id:
                return record
        return None

    @staticmethod
    def _find_display_rule(
        display_rule_records: list[DisplayRuleRecord],
        canonical_curve_id: str,
    ) -> Optional[DisplayRuleResult]:
        """Return a DisplayRuleResult for the canonical curve ID, or None.

        Only production-eligible display rules are considered.
        Approved managed rules take priority over seed rules for the same
        canonical_curve_id (list_production_eligible already merges seed +
        managed with managed-takes-precedence semantics via the repository).
        """
        for record in display_rule_records:
            if record.canonical_curve_id == canonical_curve_id:
                return DisplayRuleResult(
                    scale_type=record.scale_type,
                    recommended_min=float(record.display_min),
                    recommended_max=float(record.display_max),
                    unit=record.default_unit,
                    preferred_track_family=record.preferred_track_family,
                )
        return None
