"""KR-DATA-MODEL-1 — CuratedKRReconciliationService.

Backend-owned service that classifies each alias in a curated ImportPayload
against the existing Knowledge Repository state, distinguishing safe
broad-to-specific refinements from true unrelated alias conflicts.

Classification categories
--------------------------
  new_curve_definition   — canonical not in KR, alias not in KR.
                           Safe to stage as a new CurveDefinitionRecord candidate.

  new_alias              — canonical already in KR, alias not yet in KR.
                           Safe to stage as a new AliasRecord candidate.

  seed_confirmation      — alias already in KR pointing to the SAME canonical.
                           Import agrees with existing knowledge; no change needed.

  safe_alias_enrichment  — alias already in KR pointing to a BROAD canonical.
                           Import maps the alias to a SPECIFIC technical subtype
                           that shares the same product_subgroup as the broad
                           canonical.  This is enrichment metadata, not a conflict.
                           → Creates an AliasEnrichmentRecord (CANDIDATE).

  true_alias_conflict    — alias already in KR pointing to canonical X.
                           Import maps it to canonical Y in a DIFFERENT product
                           subgroup / curve family.  This is a genuine semantic
                           contradiction requiring manual review before staging.

  unsupported_schema_item — entry is missing required fields (canonical_curve_id,
                            display_name, family, or aliases list is empty).
                            Cannot classify; skipped with a diagnostic note.

Safe-enrichment detection algorithm
------------------------------------
For each alias that already exists in the KR (mapped to canonical E) but the
import maps to canonical I (E ≠ I):

  1. Look up the production-eligible CurveDefinitionRecord for E (the existing).
  2. Determine the existing product_subgroup P_E from that record.
  3. Take the import entry's product_subgroup P_I.
  4. If P_E == P_I  → same measurement subgroup → safe_alias_enrichment.
  5. If P_E != P_I  → different measurement domains → true_alias_conflict.
  6. If either product_subgroup is absent → fall back to comparing family
     strings: if they share a common root token → safe_alias_enrichment,
     otherwise → true_alias_conflict.

This algorithm is deterministic and requires no hard-coded parent lookup
table.  It relies on the KR taxonomy being consistent (all resistivity
subtypes share product_subgroup="resistivity", etc.).

Service contract
----------------
* PURE — does not mutate the repository.
* ``reconcile()`` — classify and return a full ReconciliationResult.
* ``create_enrichment_records()`` — produce AliasEnrichmentRecord instances
  from safe_alias_enrichments items WITHOUT staging.
* ``stage_enrichment_records()`` — add produced enrichment records as
  CANDIDATE records to the repository (the one mutating call).

No auto-approval.  All staged enrichments remain CANDIDATE.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .alias_enrichment_models import AliasEnrichmentRecord
from .governance import GovernanceStatus
from .import_models import ImportCurveDefinition, ImportPayload
from .managed_models import AliasRecord, CurveDefinitionRecord
from .managed_repository import ManagedKRRepository

KR_DATA_MODEL_1_VERSION = "kr-data-model-1"

# ---------------------------------------------------------------------------
# Classification constants
# ---------------------------------------------------------------------------

CLS_NEW_CURVE_DEFINITION = "new_curve_definition"
CLS_NEW_ALIAS = "new_alias"
CLS_SEED_CONFIRMATION = "seed_confirmation"
CLS_SAFE_ALIAS_ENRICHMENT = "safe_alias_enrichment"
CLS_TRUE_ALIAS_CONFLICT = "true_alias_conflict"
CLS_UNSUPPORTED_SCHEMA_ITEM = "unsupported_schema_item"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ReconciliationItem:
    """Classification result for a single alias in the curated catalogue."""

    alias: str
    normalized_alias: str
    import_canonical_curve_id: str
    classification: str  # one of the CLS_* constants above

    # Populated when classification != new_curve_definition
    existing_canonical_curve_id: Optional[str] = None

    # Populated for safe_alias_enrichment items
    enrichment_record: Optional[AliasEnrichmentRecord] = None

    # Human-readable diagnostic
    notes: str = ""


@dataclass
class ReconciliationResult:
    """Full reconciliation result for one ImportPayload.

    All items are grouped by classification for easy downstream handling.
    """

    kr_version: str = KR_DATA_MODEL_1_VERSION
    total_aliases_examined: int = 0

    new_curve_definitions: list[ReconciliationItem] = field(default_factory=list)
    new_aliases: list[ReconciliationItem] = field(default_factory=list)
    seed_confirmations: list[ReconciliationItem] = field(default_factory=list)
    safe_alias_enrichments: list[ReconciliationItem] = field(default_factory=list)
    true_alias_conflicts: list[ReconciliationItem] = field(default_factory=list)
    unsupported_schema_items: list[ReconciliationItem] = field(default_factory=list)

    @property
    def has_true_conflicts(self) -> bool:
        return len(self.true_alias_conflicts) > 0

    @property
    def safe_to_stage_count(self) -> int:
        """Number of alias items that can be staged without manual review."""
        return (
            len(self.new_curve_definitions)
            + len(self.new_aliases)
            + len(self.seed_confirmations)
            + len(self.safe_alias_enrichments)
        )

    def summary(self) -> dict:
        return {
            "kr_version": self.kr_version,
            "total_aliases_examined": self.total_aliases_examined,
            "new_curve_definitions": len(self.new_curve_definitions),
            "new_aliases": len(self.new_aliases),
            "seed_confirmations": len(self.seed_confirmations),
            "safe_alias_enrichments": len(self.safe_alias_enrichments),
            "true_alias_conflicts": len(self.true_alias_conflicts),
            "unsupported_schema_items": len(self.unsupported_schema_items),
            "has_true_conflicts": self.has_true_conflicts,
            "safe_to_stage_count": self.safe_to_stage_count,
        }


# ---------------------------------------------------------------------------
# CuratedKRReconciliationService
# ---------------------------------------------------------------------------


class CuratedKRReconciliationService:
    """Classify curated catalogue entries against existing KR state.

    Distinguishes safe broad-to-specific alias enrichments from true
    unrelated alias conflicts.  Does not mutate the repository (except
    via the explicit ``stage_enrichment_records`` call).

    Usage::

        service = CuratedKRReconciliationService()
        result  = service.reconcile(payload, repository)

        # Preview what would be staged:
        print(result.summary())

        # Stage only the enrichment records (not the curve defs / aliases —
        # those go through the normal KR-3 import flow):
        record_ids = service.stage_enrichment_records(result, repository)
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reconcile(
        self,
        payload: ImportPayload,
        repository: ManagedKRRepository,
    ) -> ReconciliationResult:
        """Classify every alias in ``payload`` against ``repository``.

        PURE — does not mutate ``repository``.

        Args:
            payload:    A structured import payload (need not be pre-validated).
            repository: The current ManagedKRRepository used for lookup.

        Returns:
            ReconciliationResult with all aliases classified.
        """
        result = ReconciliationResult()

        # Build lookup structures from production-eligible records
        alias_map: dict[str, str] = {}        # normalized_alias → canonical_curve_id
        curve_def_map: dict[str, CurveDefinitionRecord] = {}  # canonical_curve_id → record

        for record in repository.list_production_eligible():
            if isinstance(record, AliasRecord):
                alias_map[record.normalized_alias] = record.canonical_curve_id
            elif isinstance(record, CurveDefinitionRecord):
                curve_def_map[record.canonical_curve_id] = record

        for cd in payload.curve_definitions:
            items = self._classify_curve_definition(
                cd=cd,
                payload=payload,
                alias_map=alias_map,
                curve_def_map=curve_def_map,
            )
            for item in items:
                result.total_aliases_examined += 1
                _bucket = {
                    CLS_NEW_CURVE_DEFINITION: result.new_curve_definitions,
                    CLS_NEW_ALIAS: result.new_aliases,
                    CLS_SEED_CONFIRMATION: result.seed_confirmations,
                    CLS_SAFE_ALIAS_ENRICHMENT: result.safe_alias_enrichments,
                    CLS_TRUE_ALIAS_CONFLICT: result.true_alias_conflicts,
                    CLS_UNSUPPORTED_SCHEMA_ITEM: result.unsupported_schema_items,
                }
                _bucket[item.classification].append(item)

        return result

    def create_enrichment_records(
        self,
        result: ReconciliationResult,
        batch_id: str | None = None,
    ) -> list[AliasEnrichmentRecord]:
        """Return AliasEnrichmentRecord instances for all safe_alias_enrichment items.

        Does NOT add records to any repository.  Records have status=CANDIDATE.

        Args:
            result:   A ReconciliationResult from ``reconcile()``.
            batch_id: Optional batch identifier (auto-generated if None).

        Returns:
            List of AliasEnrichmentRecord instances ready for staging.
        """
        if batch_id is None:
            batch_id = f"enrich_{uuid.uuid4().hex[:12]}"

        records: list[AliasEnrichmentRecord] = []
        for item in result.safe_alias_enrichments:
            if item.enrichment_record is not None:
                # Stamp the batch_id into the record_id for traceability
                rec = item.enrichment_record
                # Re-ID with batch context
                rec = AliasEnrichmentRecord(
                    record_id=f"{batch_id}_{item.normalized_alias}_{rec.technical_curve_id}",
                    alias=rec.alias,
                    normalized_alias=rec.normalized_alias,
                    display_canonical_curve_id=rec.display_canonical_curve_id,
                    technical_curve_id=rec.technical_curve_id,
                    technical_display_name=rec.technical_display_name,
                    parent_canonical_curve_id=rec.parent_canonical_curve_id,
                    record_type=rec.record_type,
                    status=GovernanceStatus.CANDIDATE,
                    technical_family=rec.technical_family,
                    measurement_family=rec.measurement_family,
                    measurement_depth=rec.measurement_depth,
                    tool_family=rec.tool_family,
                    vendor_context=rec.vendor_context,
                    selection_priority=rec.selection_priority,
                    source_label=rec.source_label,
                    source_reference=rec.source_reference,
                    evidence_refs=list(rec.evidence_refs),
                    confidence=rec.confidence,
                    review_notes=rec.review_notes,
                    created_at=datetime.now(tz=timezone.utc),
                    updated_at=None,
                    change_reason=f"Auto-staged safe alias enrichment (batch={batch_id})",
                    governance_history=[],
                )
                records.append(rec)
        return records

    def stage_enrichment_records(
        self,
        result: ReconciliationResult,
        repository: ManagedKRRepository,
        batch_id: str | None = None,
    ) -> list[str]:
        """Add safe alias enrichment records to ``repository`` as CANDIDATE records.

        This is the ONE mutating call on the service.  Only safe_alias_enrichment
        items are staged.  true_alias_conflict items are NOT staged.

        Args:
            result:     A ReconciliationResult from ``reconcile()``.
            repository: The ManagedKRRepository to add candidate records to.
            batch_id:   Optional batch identifier.

        Returns:
            List of record_ids for all staged AliasEnrichmentRecord instances.
        """
        if batch_id is None:
            batch_id = f"enrich_{uuid.uuid4().hex[:12]}"

        records = self.create_enrichment_records(result, batch_id=batch_id)
        staged_ids: list[str] = []
        for record in records:
            repository._add_record(record)  # type: ignore[arg-type]
            staged_ids.append(record.record_id)
        return staged_ids

    # ------------------------------------------------------------------
    # Internal classification logic
    # ------------------------------------------------------------------

    def _classify_curve_definition(
        self,
        cd: ImportCurveDefinition,
        payload: ImportPayload,
        alias_map: dict[str, str],
        curve_def_map: dict[str, CurveDefinitionRecord],
    ) -> list[ReconciliationItem]:
        """Classify all aliases within a single ImportCurveDefinition."""
        # Validate required fields for the curve definition entry
        if (
            not cd.canonical_curve_id
            or not cd.canonical_curve_id.strip()
            or not cd.display_name
            or not cd.display_name.strip()
        ):
            # Entry is malformed — classify all aliases (or a synthetic one) as unsupported
            synthetic_alias = (cd.aliases[0] if cd.aliases else "<no_alias>")
            return [
                ReconciliationItem(
                    alias=synthetic_alias,
                    normalized_alias=synthetic_alias.strip().upper(),
                    import_canonical_curve_id=cd.canonical_curve_id or "",
                    classification=CLS_UNSUPPORTED_SCHEMA_ITEM,
                    notes=(
                        "Import curve definition is missing required fields "
                        "(canonical_curve_id or display_name)."
                    ),
                )
            ]

        if not cd.aliases:
            # No aliases to classify — this is a curve def with no alias rows
            # Treat as a structural no-op at the alias classification level;
            # record the canonical as new_curve_definition if it doesn't exist
            canonical_in_kr = cd.canonical_curve_id.strip() in curve_def_map
            return [
                ReconciliationItem(
                    alias="<no_alias>",
                    normalized_alias="<NO_ALIAS>",
                    import_canonical_curve_id=cd.canonical_curve_id.strip(),
                    classification=(
                        CLS_SEED_CONFIRMATION if canonical_in_kr
                        else CLS_NEW_CURVE_DEFINITION
                    ),
                    notes=(
                        "Curve definition has no aliases. "
                        f"Canonical {'already exists' if canonical_in_kr else 'is new'} in KR."
                    ),
                )
            ]

        items: list[ReconciliationItem] = []
        import_canonical = cd.canonical_curve_id.strip()
        import_family = (cd.family or "").strip()
        import_product_subgroup = getattr(cd, "product_subgroup", None) or ""

        for alias in cd.aliases:
            normalized = alias.strip().upper()
            item = self._classify_alias(
                alias=alias,
                normalized=normalized,
                import_canonical=import_canonical,
                import_family=import_family,
                import_display_name=cd.display_name or "",
                import_product_subgroup=import_product_subgroup,
                payload=payload,
                alias_map=alias_map,
                curve_def_map=curve_def_map,
            )
            items.append(item)

        return items

    def _classify_alias(
        self,
        alias: str,
        normalized: str,
        import_canonical: str,
        import_family: str,
        import_display_name: str,
        import_product_subgroup: str,
        payload: ImportPayload,
        alias_map: dict[str, str],
        curve_def_map: dict[str, CurveDefinitionRecord],
    ) -> ReconciliationItem:
        """Classify a single alias."""
        existing_canonical = alias_map.get(normalized)

        if existing_canonical is None:
            # Alias is not in KR at all
            canonical_in_kr = import_canonical in curve_def_map
            classification = (
                CLS_NEW_ALIAS if canonical_in_kr else CLS_NEW_CURVE_DEFINITION
            )
            return ReconciliationItem(
                alias=alias,
                normalized_alias=normalized,
                import_canonical_curve_id=import_canonical,
                classification=classification,
                notes=(
                    f"Alias '{normalized}' is new. "
                    f"Canonical '{import_canonical}' "
                    f"{'already exists' if canonical_in_kr else 'is also new'} in KR."
                ),
            )

        # Alias already exists in KR, mapped to existing_canonical
        if existing_canonical == import_canonical:
            return ReconciliationItem(
                alias=alias,
                normalized_alias=normalized,
                import_canonical_curve_id=import_canonical,
                classification=CLS_SEED_CONFIRMATION,
                existing_canonical_curve_id=existing_canonical,
                notes=(
                    f"Alias '{normalized}' already maps to '{existing_canonical}' in KR. "
                    "Import agrees — no conflict."
                ),
            )

        # Alias maps to different canonical — determine if safe refinement or conflict
        existing_def = curve_def_map.get(existing_canonical)
        classification, enrichment, notes = self._evaluate_subtype_relationship(
            alias=alias,
            normalized=normalized,
            existing_canonical=existing_canonical,
            existing_def=existing_def,
            import_canonical=import_canonical,
            import_family=import_family,
            import_display_name=import_display_name,
            import_product_subgroup=import_product_subgroup,
            payload=payload,
        )
        return ReconciliationItem(
            alias=alias,
            normalized_alias=normalized,
            import_canonical_curve_id=import_canonical,
            classification=classification,
            existing_canonical_curve_id=existing_canonical,
            enrichment_record=enrichment,
            notes=notes,
        )

    def _evaluate_subtype_relationship(
        self,
        alias: str,
        normalized: str,
        existing_canonical: str,
        existing_def: Optional[CurveDefinitionRecord],
        import_canonical: str,
        import_family: str,
        import_display_name: str,
        import_product_subgroup: str,
        payload: ImportPayload,
    ) -> tuple[str, Optional[AliasEnrichmentRecord], str]:
        """Determine safe_alias_enrichment vs true_alias_conflict.

        Algorithm (deterministic):
          Primary:  Compare product_subgroup of existing canonical def vs import entry.
                    Same product_subgroup → safe enrichment.
                    Different → true conflict.
          Fallback: If product_subgroup is unavailable, compare family tokens.
                    If existing family is a substring of import family (or vice-versa)
                    → safe enrichment (specific refines broad).
                    Otherwise → true conflict.

        Returns:
            (classification_string, AliasEnrichmentRecord_or_None, notes_string)
        """
        existing_product_subgroup = ""
        existing_family = ""

        if existing_def is not None:
            existing_product_subgroup = getattr(existing_def, "product_subgroup", "") or ""
            existing_family = getattr(existing_def, "family", "") or ""

        # --- Primary comparison: product_subgroup ---
        if existing_product_subgroup and import_product_subgroup:
            is_safe = (existing_product_subgroup == import_product_subgroup)
        elif existing_family and import_family:
            # Fallback: family token containment check
            ef = existing_family.lower()
            imf = import_family.lower()
            is_safe = (ef in imf) or (imf in ef)
        else:
            # Cannot determine — treat as conflict (conservative)
            is_safe = False

        if is_safe:
            enrichment = self._build_enrichment_record(
                alias=alias,
                normalized=normalized,
                existing_canonical=existing_canonical,
                existing_def=existing_def,
                import_canonical=import_canonical,
                import_family=import_family,
                import_display_name=import_display_name,
                import_product_subgroup=import_product_subgroup,
                payload=payload,
            )
            notes = (
                f"Alias '{normalized}': existing canonical '{existing_canonical}' "
                f"(subgroup='{existing_product_subgroup or existing_family}') "
                f"is broad; import canonical '{import_canonical}' "
                f"(subgroup='{import_product_subgroup or import_family}') "
                f"is a specific technical subtype under the same measurement family. "
                f"Classified as safe alias enrichment."
            )
            return CLS_SAFE_ALIAS_ENRICHMENT, enrichment, notes
        else:
            notes = (
                f"Alias '{normalized}': existing canonical '{existing_canonical}' "
                f"(subgroup='{existing_product_subgroup or existing_family}') "
                f"conflicts with import canonical '{import_canonical}' "
                f"(subgroup='{import_product_subgroup or import_family}'). "
                f"Different measurement domains — true alias conflict. "
                f"Requires manual review before staging."
            )
            return CLS_TRUE_ALIAS_CONFLICT, None, notes

    @staticmethod
    def _build_enrichment_record(
        alias: str,
        normalized: str,
        existing_canonical: str,
        existing_def: Optional[CurveDefinitionRecord],
        import_canonical: str,
        import_family: str,
        import_display_name: str,
        import_product_subgroup: str,
        payload: ImportPayload,
    ) -> AliasEnrichmentRecord:
        """Build a preliminary AliasEnrichmentRecord (no record_id assigned yet)."""
        source_ref = payload.source.source_reference or payload.source.source_label
        source_label = payload.source.source_label

        # Infer measurement_depth from canonical name (best-effort)
        measurement_depth: Optional[str] = None
        lower_canonical = import_canonical.lower()
        if "deep" in lower_canonical:
            measurement_depth = "deep"
        elif "medium" in lower_canonical or "medium" in lower_canonical:
            measurement_depth = "medium"
        elif "shallow" in lower_canonical or "micro" in lower_canonical:
            measurement_depth = "shallow"

        review_notes = (
            f"Curated catalogue refines broad seed '{existing_canonical}' alias. "
            f"Technical subtype: {import_canonical} ({import_display_name}). "
            f"Display canonical unchanged."
        )

        return AliasEnrichmentRecord(
            record_id=f"_pending_{normalized}_{import_canonical}",  # overwritten by caller
            alias=alias,
            normalized_alias=normalized,
            display_canonical_curve_id=existing_canonical,
            technical_curve_id=import_canonical,
            technical_display_name=import_display_name,
            parent_canonical_curve_id=existing_canonical,
            status=GovernanceStatus.CANDIDATE,
            technical_family=import_family or None,
            measurement_family=import_product_subgroup or None,
            measurement_depth=measurement_depth,
            tool_family=None,  # not in ImportCurveDefinition; can be set post-classification
            source_label=source_label,
            source_reference=source_ref,
            evidence_refs=[],
            confidence=1.0,
            review_notes=review_notes,
        )
