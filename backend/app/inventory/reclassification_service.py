"""Backend-owned managed-inventory curve reclassification."""
from __future__ import annotations
from dataclasses import dataclass
from app.classification.well_log_vocabulary import PRODUCT_GROUP_ORDER
from app.knowledge.managed_repository import ManagedKRRepository
from app.knowledge.runtime_classification_service import CurveClassificationInput, RuntimeCurveClassificationService
from app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver
from .models import ManagedInventorySnapshot, ManagedProductGroup, utc_now_iso
from .repository import ManagedWellInventoryRepository

@dataclass(frozen=True)
class ReclassificationResult:
    managed_well_id: str
    examined_count: int
    changed_count: int
    still_review_required: tuple[str, ...]

class ManagedCurveReclassificationService:
    def __init__(self, *, inventory_repository=None, knowledge_repository=None):
        self.inventory_repository = inventory_repository or ManagedWellInventoryRepository()
        self.classifier = RuntimeCurveClassificationService(ApprovedKnowledgeRuntimeResolver(knowledge_repository or ManagedKRRepository()))

    def reclassify_well(
        self,
        managed_well_id: str,
        *,
        target_mnemonics: set[str] | None = None,
    ) -> ReclassificationResult:
        snapshot = self.inventory_repository.snapshot()
        target = next((r for r in snapshot.records if r.managed_well_id == managed_well_id), None)
        if target is None:
            raise ValueError(f"Managed well not found: {managed_well_id}")
        items = [i for g in target.product_groups for i in g.items]
        normalized_targets = {value.strip().upper() for value in target_mnemonics or set() if value.strip()}
        selected_items = [
            item for item in items
            if not normalized_targets
            or (item.observed_mnemonic or item.display_name or item.curve_name).strip().upper() in normalized_targets
        ]
        inputs = [CurveClassificationInput(source_mnemonic=i.observed_mnemonic or i.display_name or i.curve_name, curve_id=i.product_id, unit=i.curve_unit, description=i.curve_description or i.curve_type, context={"source_kind": i.source_kind}) for i in selected_items]
        results = self.classifier.classify_curves(inputs).classifications if inputs else ()
        result_by_product_id = {result.curve_id: result for result in results}
        changed = 0
        remaining = []
        regrouped = {d.group_key: [] for d in PRODUCT_GROUP_ORDER}
        for item in items:
            result = result_by_product_id.get(item.product_id)
            next_item = item
            if result is not None and result.resolved:
                reasons = [f"Runtime KR resolved mnemonic {result.normalized_mnemonic}.", f"Resolution source: {result.resolution_source}."]
                if result.knowledge_record_id: reasons.append(f"Knowledge record: {result.knowledge_record_id}.")
                if result.canonical_curve_id: reasons.append(f"Canonical curve: {result.canonical_curve_id}.")
                reasons.extend(result.warnings)
                updates = {
                    "kr_curve_type_id": result.canonical_curve_id,
                    "curve_type": result.display_name or item.curve_type,
                    "curve_description": result.display_name or item.curve_description,
                    "curve_unit": result.default_unit or item.curve_unit,
                    "product_category": result.product_group or item.product_category,
                    "product_subgroup_key": result.product_subgroup,
                    "product_subgroup_label": result.product_subgroup.replace("_", " ").title() if result.product_subgroup else None,
                    "curve_family": result.family or item.curve_family,
                    "classification_confidence": "high" if result.confidence >= 0.9 else "medium" if result.confidence >= 0.6 else "low",
                    "classification_source": result.resolution_source,
                    "classification_reasons": reasons,
                    "review_required": result.requires_review,
                    "qa_flag": "Review" if result.requires_review else "Passed",
                }
                candidate = item.model_copy(update=updates)
                if candidate != item: changed += 1
                next_item = candidate
            if next_item.review_required:
                remaining.append(next_item.observed_mnemonic or next_item.display_name)
            key = next_item.product_category if next_item.product_category in regrouped else "other_review_required"
            regrouped[key].append(next_item)
        existing = {g.group_key: g for g in target.product_groups}
        groups = [ManagedProductGroup(group_key=d.group_key, group_label=(existing[d.group_key].group_label if d.group_key in existing else d.group_label), collapsed_by_default=(existing[d.group_key].collapsed_by_default if d.group_key in existing else True), items=regrouped[d.group_key]) for d in PRODUCT_GROUP_ORDER]
        if changed:
            updated = target.model_copy(update={"product_groups": groups, "updated_at": utc_now_iso()})
            records = [updated if r.managed_well_id == managed_well_id else r for r in snapshot.records]
            self.inventory_repository.write_snapshot(
                ManagedInventorySnapshot(
                    schema_version=snapshot.schema_version,
                    records=records,
                    updated_at=utc_now_iso(),
                )
            )
        return ReclassificationResult(managed_well_id, len(selected_items), changed, tuple(remaining))
