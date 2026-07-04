"""Registration bridge from WLV Source Intake to Managed Well Inventory.

This module owns the first controlled handoff from the intake workbench into
backend-managed well inventory. It does not load data into the WDV and does not
create a viewer representation/conversion.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from app.classification.well_log_classifier import classify_well_log_curve
from app.classification.well_log_vocabulary import OPEN_HOLE_SUBGROUP_LABELS, PRODUCT_GROUP_ORDER
from app.knowledge.managed_repository import ManagedKRRepository
from app.knowledge.runtime_classification_service import (
    CurveClassificationInput,
    CurveClassificationResult,
    RuntimeCurveClassificationService,
)
from app.knowledge.runtime_resolver import ApprovedKnowledgeRuntimeResolver
from app.inventory.models import (
    ManagedInventoryLifecycleState,
    ManagedWdvState,
    ManagedWmdpState,
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWellRecord,
    utc_now_iso,
)
from app.inventory.repository import ManagedWellNotFoundError
from app.inventory.service import ManagedWellInventoryService
from app.inventory.well_identity import (
    consolidate_well_metadata,
    find_record_by_canonical_name,
    managed_well_identity_from_name,
    normalize_well_name_key,
)

from .identity_gate import clean_identity_value
from .las_asset_store import LasAssetStore, LasAssetStoreError, StoredLasAsset
from .dlis_asset_store import DlisAssetStore, DlisAssetStoreError, StoredDlisAsset
from .readiness import evaluate_registration_readiness
from .models import (
    SourceFileCandidate,
    SourceIntakeCandidateRole,
    SourceIntakeParseStatus,
    SourceIntakeQaqcStatus,
    SourceIntakeReadinessState,
    SourceIntakeResolutionState,
    SourceIntakeHumanDecision,
    SourceIntakeFileType,
    SourceIntakeWellAssignmentMode,
)
from .resolution_service import is_ingestible

_ALLOWED_REGISTER_QAQC_STATUSES = {
    SourceIntakeQaqcStatus.PASS,
    SourceIntakeQaqcStatus.WARNING,
    SourceIntakeQaqcStatus.REVIEW_REQUIRED,
}


def registration_block_reason(candidate: SourceFileCandidate) -> str | None:
    """Return the established registration diagnostic for an ineligible candidate.

    Structured eligibility is computed by readiness.py. This function preserves
    the existing public/tested rejection wording consumed by registration callers.
    """
    evaluate_registration_readiness(candidate)
    if candidate.readiness_state == SourceIntakeReadinessState.READY:
        return None

    if candidate.registration_status == "registered" or candidate.resolution_state == SourceIntakeResolutionState.REGISTERED:
        return "Candidate is already registered to Managed Well Inventory."

    if candidate.resolution_state == SourceIntakeResolutionState.DUPLICATE:
        return "Candidate is an exact-content duplicate and cannot be registered again."

    if candidate.resolution_state == SourceIntakeResolutionState.EXCLUDED:
        return "Candidate is excluded from ingestion. Reopen it before registration."

    if candidate.candidate_role == SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE:
        if candidate.parser_status not in {SourceIntakeParseStatus.PARSED, SourceIntakeParseStatus.PARSED_WITH_WARNINGS}:
            return f"Geometry candidate parser_status is not registration-ready: {candidate.parser_status.value}."
        if candidate.geometry_preview is None:
            return "Geometry candidate has no parsed deviation-survey preview."
        if not candidate.geometry_preview.stations_preview:
            return "Geometry candidate preview has no station payload to register."
        if candidate.qaqc_status.status not in _ALLOWED_REGISTER_QAQC_STATUSES:
            return f"Geometry candidate QAQC status is not registration-ready: {candidate.qaqc_status.status.value}."
        if candidate.qaqc_status.failure_count > 0:
            return "Geometry candidate QAQC has failures and cannot be registered."
        if not is_ingestible(candidate):
            return (
                "Geometry candidate resolution state is not registration-ready: "
                f"{candidate.resolution_state.value}. Resolve the candidate first."
            )
        return candidate.readiness_issues[0] if candidate.readiness_issues else None

    if candidate.candidate_role != SourceIntakeCandidateRole.WELL_LOG_CANDIDATE:
        return f"Only well_log_candidate records can be registered; got {candidate.candidate_role.value}."

    if candidate.parser_status not in {SourceIntakeParseStatus.PARSED, SourceIntakeParseStatus.PARSED_WITH_WARNINGS}:
        return f"Candidate parser_status is not registration-ready: {candidate.parser_status.value}."

    if candidate.parsed_metadata is None:
        return "Candidate has no parsed well-log metadata."

    if candidate.qaqc_status.status not in _ALLOWED_REGISTER_QAQC_STATUSES:
        return f"Candidate QAQC status is not registration-ready: {candidate.qaqc_status.status.value}."

    if candidate.qaqc_status.failure_count > 0:
        return "Candidate QAQC has failures and cannot be registered."

    well_name = _resolved_value(candidate, "well_name") or candidate.parsed_metadata.well_header.well_name
    if clean_identity_value(well_name) is None:
        return "Candidate has no resolved well name."

    if not is_ingestible(candidate):
        return (
            "Candidate resolution state is not registration-ready: "
            f"{candidate.resolution_state.value}. Resolve or explicitly disposition the candidate first."
        )

    return candidate.readiness_issues[0] if candidate.readiness_issues else "Candidate is not registration-ready."

def _source_intake_provenance(candidate: SourceFileCandidate) -> dict[str, object]:
    return {
        "source_intake_candidate_id": candidate.source_file_id,
        "repository_id": candidate.repository_id,
        "scan_id": candidate.scan_id,
        "relative_path": candidate.relative_path,
        "original_path": candidate.original_path,
        "checksum": candidate.checksum,
        "parser_status": candidate.parser_status.value,
        "qaqc_status": candidate.qaqc_status.model_dump(mode="json"),
        "resolved_metadata": candidate.resolved_metadata.model_dump(mode="json") if candidate.resolved_metadata else None,
    }


def register_candidate_to_inventory(
    *,
    candidate: SourceFileCandidate,
    inventory_service: ManagedWellInventoryService,
    approved_by: str | None = None,
    approval_note: str | None = None,
) -> tuple[str, ManagedWellRecord]:
    """Create/update one Managed Well Inventory record from an intake candidate."""
    blocked = registration_block_reason(candidate)
    if blocked is not None:
        raise ValueError(blocked)

    parsed = candidate.parsed_metadata
    assert parsed is not None
    log_header = parsed.log_header
    well_header = parsed.well_header

    decision = candidate.current_decision
    assigned_existing = bool(
        decision
        and decision.decision == SourceIntakeHumanDecision.ASSIGN
        and decision.assignment_mode
        == SourceIntakeWellAssignmentMode.EXISTING_WELL
        and decision.assignment_target
    )
    human_new_well_values = (
        dict(decision.new_well_values)
        if (
            decision
            and decision.decision == SourceIntakeHumanDecision.ASSIGN
            and decision.assignment_mode
            == SourceIntakeWellAssignmentMode.NEW_WELL
        )
        else {}
    )

    source_evidence_values = {
        "well_name": (
            _clean(well_header.well_name)
            or candidate.file_name
        ),
        "uwi": _clean(well_header.uwi) or None,
        "operator": _clean(well_header.operator) or None,
        "field": _clean(well_header.field) or None,
        "block": _clean(well_header.block) or None,
        "country": _clean(well_header.country) or None,
        "depth_unit": (
            well_header.depth_unit
            or (log_header.depth_unit if log_header else None)
            or "ft"
        ),
    }

    resolved_values = {
        "well_name": _clean(_resolved_value(candidate, "well_name")),
        "uwi": _clean(_resolved_value(candidate, "uwi")),
        "operator": _clean(_resolved_value(candidate, "operator")),
        "field": _clean(_resolved_value(candidate, "field")),
        "block": _clean(_resolved_value(candidate, "block")),
    }

    incoming_values = {
        **source_evidence_values,
        **{
            key: value
            for key, value in resolved_values.items()
            if value is not None
        },
    }

    human_well_name = _clean(
        human_new_well_values.get("well_name")
        if isinstance(human_new_well_values.get("well_name"), str)
        else None
    )
    canonical_display_name = human_well_name or incoming_values["well_name"]

    existing = None
    if assigned_existing:
        managed_well_id = str(decision.assignment_target)
        existing = _get_existing_record(
            inventory_service,
            managed_well_id,
        )
        if existing is None:
            raise ValueError(
                "Assigned managed well does not exist: "
                f"{managed_well_id}"
            )
        well_id = existing.well_id
        canonical_display_name = existing.well_name
    else:
        existing = find_record_by_canonical_name(
            inventory_service.repository.list_records(),
            canonical_display_name,
        )
        if existing is not None:
            managed_well_id = existing.managed_well_id
            well_id = existing.well_id
        else:
            (
                well_id,
                managed_well_id,
                _canonical_key,
            ) = managed_well_identity_from_name(
                canonical_display_name
            )

    decision_corrections = (
        dict(decision.corrected_values)
        if decision and decision.corrected_values
        else {}
    )
    explicit_metadata = {
        key: value
        for key, value in {
            **decision_corrections,
            **human_new_well_values,
        }.items()
        if key in {"uwi", "operator", "field", "block"}
    }
    canonical_metadata, metadata_evidence, metadata_conflicts = (
        consolidate_well_metadata(
            existing=existing,
            incoming=source_evidence_values,
            explicit=explicit_metadata,
            source_id=candidate.source_file_id,
        )
    )

    well_name = (
        human_well_name
        or (existing.well_name if existing is not None else None)
        or canonical_display_name
    )
    canonical_well_key = normalize_well_name_key(well_name)
    uwi = canonical_metadata["uwi"]
    operator = canonical_metadata["operator"]
    field = canonical_metadata["field"]
    block = canonical_metadata["block"]
    provenance = _source_intake_provenance(candidate)
    las_asset: StoredLasAsset | None = None
    dlis_asset: StoredDlisAsset | None = None
    if candidate.detected_file_type == SourceIntakeFileType.DLIS:
        try:
            dlis_asset = DlisAssetStore().preserve_path(Path(candidate.original_path), source_id=candidate.source_file_id, filename=candidate.file_name)
        except DlisAssetStoreError as exc:
            raise ValueError(f"Original DLIS asset preservation failed: {exc}") from exc
        asset_payload = dlis_asset.as_dict()
        provenance = {**provenance, "dlis_asset": asset_payload, "source_format": "DLIS"}
        source_kind = ManagedSourceKind.DLIS
        source_metadata = {**provenance, "parsed_metadata": parsed.model_dump(mode="json"), "storage_uri": dlis_asset.original_uri, "dlis_asset_id": dlis_asset.asset_id}
        source_fingerprint = dlis_asset.source_fingerprint
    else:
        try:
            las_asset = LasAssetStore().preserve_path(Path(candidate.original_path), source_id=candidate.source_file_id, filename=candidate.file_name)
        except LasAssetStoreError as exc:
            raise ValueError(f"Original LAS asset preservation failed: {exc}") from exc
        asset_payload = las_asset.as_dict()
        provenance = {**provenance, "las_asset": asset_payload, "source_format": "LAS"}
        source_kind = ManagedSourceKind.LAS
        source_metadata = {**provenance, "parsed_metadata": parsed.model_dump(mode="json"), "storage_uri": las_asset.original_uri, "las_manifest_uri": las_asset.manifest_uri, "las_samples_uri": las_asset.samples_uri, "las_asset_id": las_asset.asset_id}
        source_fingerprint = las_asset.source_fingerprint
    if candidate.checksum and candidate.checksum != source_fingerprint:
        raise ValueError("Source Intake checksum does not match the preserved source content fingerprint.")
    source_reference = ManagedSourceReference(
        source_id=candidate.source_file_id, source_kind=source_kind, display_name=candidate.file_name,
        original_path=candidate.original_path, file_name=candidate.file_name,
        file_format=candidate.detected_file_type.value, checksum=source_fingerprint, metadata=source_metadata,
    )

    review_required = bool(candidate.review_required or candidate.qaqc_status.review_required)
    lifecycle_state = (
        ManagedInventoryLifecycleState.REVIEW_REQUIRED if review_required else ManagedInventoryLifecycleState.REGISTERED
    )
    now = utc_now_iso()
    created_at = now
    if existing is None:
        existing = _get_existing_record(
            inventory_service,
            managed_well_id,
        )
    if existing is not None:
        created_at = existing.created_at

    next_product_groups = _product_groups_from_candidate(candidate, las_asset=las_asset, dlis_asset=dlis_asset)
    merged_product_groups = _merge_product_groups(existing.product_groups if existing else [], next_product_groups)

    record = ManagedWellRecord(
        managed_well_id=managed_well_id,
        well_id=well_id,
        well_name=well_name,
        operator=operator,
        field=field,
        block=block,
        country=canonical_metadata["country"],
        depth_unit=canonical_metadata["depth_unit"] or "ft",
        top_depth=_merged_top_depth(
            existing.top_depth if existing else None,
            log_header.start_depth if log_header else None,
        ),
        base_depth=_merged_base_depth(
            existing.base_depth if existing else None,
            log_header.stop_depth if log_header else None,
        ),
        status=lifecycle_state,
        lifecycle_state=lifecycle_state,
        wmdp_state=ManagedWmdpState.STAGED_IN_WMDP,
        wdv_state=ManagedWdvState.NOT_LOADED,
        source_intake_candidate_id=candidate.source_file_id,
        wmdp_available=True,
        source_references=_merge_source_references(existing.source_references if existing else [], source_reference),
        viewer_packages=existing.viewer_packages if existing else [],
        product_groups=merged_product_groups,
        tags=_merge_tags(existing.tags if existing else [], ["source-intake", candidate.detected_file_type.value.lower()]),
        metadata={
            **(existing.metadata if existing else {}),
            "canonical_well_name": well_name,
            "canonical_well_key": canonical_well_key,
            "identity_source": (
                "human_wsi_well_name"
                if human_well_name
                else "normalized_well_name"
            ),
            "uwi": uwi,
            "uwi_missing": uwi is None,
            "well_metadata_evidence": metadata_evidence,
            "well_metadata_conflicts": metadata_conflicts,
            "source_intake_registered": True,
            "wmdp_state": ManagedWmdpState.STAGED_IN_WMDP.value,
            "wdv_state": ManagedWdvState.NOT_LOADED.value,
            "wmdp_available": True,
            "source_intake_provenance": provenance,
            "source_intake_candidate_id": candidate.source_file_id,
            **({"dlis_assets": _merge_las_assets((existing.metadata.get("dlis_assets", []) if existing else []), asset_payload)} if dlis_asset is not None else {"las_assets": _merge_las_assets((existing.metadata.get("las_assets", []) if existing else []), asset_payload)}),
            "approval": {
                "approved_by": approved_by,
                "approval_note": approval_note,
                "registered_at": now,
            },
            "review_required": review_required,
            "qaqc_status": candidate.qaqc_status.model_dump(mode="json"),
            "resolved_metadata": candidate.resolved_metadata.model_dump(mode="json") if candidate.resolved_metadata else None,
        },
        lifecycle_notes=_merge_lifecycle_notes(
            existing.lifecycle_notes if existing else [],
            _registration_note(candidate, uwi=uwi, approved_by=approved_by, approval_note=approval_note),
        ),
        created_at=created_at,
        updated_at=now,
    )
    return inventory_service.upsert_managed_record(record)


def _product_groups_from_candidate(
    candidate: SourceFileCandidate,
    *,
    las_asset: StoredLasAsset | None = None,
    dlis_asset: StoredDlisAsset | None = None,
) -> list[ManagedProductGroup]:
    parsed = candidate.parsed_metadata
    log_header = parsed.log_header if parsed else None
    curve_headers = parsed.curve_headers if parsed else []
    items_by_group: dict[str, list[ManagedProductGroupItem]] = {
        definition.group_key: [] for definition in PRODUCT_GROUP_ORDER
    }
    run_interval = _run_interval(log_header)
    run_date = log_header.run_date if log_header and log_header.run_date else "—"
    run_number = log_header.run_number if log_header and log_header.run_number else "—"
    context_terms = [
        candidate.file_name,
        candidate.relative_path,
        candidate.detected_file_type.value,
        log_header.service_company if log_header else None,
    ]
    provenance = _source_intake_provenance(candidate)
    if las_asset is not None:
        provenance = {**provenance, "las_asset": las_asset.as_dict(), "source_format": "LAS"}
    elif dlis_asset is not None:
        provenance = {**provenance, "dlis_asset": dlis_asset.as_dict(), "source_format": "DLIS"}
    runtime_classifications = _runtime_classifications_for_curves(
        curve_headers=curve_headers,
        context_terms=context_terms,
    )

    for index, curve in enumerate(curve_headers, start=1):
        runtime_classification = runtime_classifications[index - 1] if index - 1 < len(runtime_classifications) else None
        classification = _inventory_curve_classification_payload(
            curve=curve,
            runtime_classification=runtime_classification,
            context_terms=context_terms,
        )
        group_key = classification["product_category"] if classification["product_category"] in items_by_group else "other_review_required"
        review_required = bool(classification["review_required"] or candidate.qaqc_status.review_required)
        items_by_group[group_key].append(
            ManagedProductGroupItem(
                product_id=f"source-intake-curve:{candidate.source_file_id}:{index}:{_slug(curve.mnemonic or 'curve')}",
                display_name=curve.mnemonic or f"Curve {index}",
                curve_name=curve.mnemonic or f"Curve {index}",
                curve_type=classification["curve_description"],
                curve_description=classification["curve_description"],
                curve_unit=classification["curve_unit"],
                product_category=classification["product_category"],
                product_subgroup_key=classification["product_subgroup_key"],
                product_subgroup_label=classification["product_subgroup_label"],
                curve_family=classification["curve_family"],
                classification_confidence=classification["classification_confidence"],
                classification_source=classification["classification_source"],
                classification_reasons=classification["classification_reasons"],
                review_required=review_required,
                run_date=run_date,
                run_interval=run_interval,
                run_number=run_number,
                qa_flag="Review" if review_required else "Passed",
                selectable=True,
                source_kind=(ManagedSourceKind.DLIS.value if dlis_asset is not None else ManagedSourceKind.LAS.value),
                source_id=candidate.source_file_id,
                viewer_package_id=None,
                wmdp_state=ManagedWmdpState.STAGED_IN_WMDP,
                wdv_state=ManagedWdvState.NOT_LOADED,
                source_intake_candidate_id=candidate.source_file_id,
                provenance={
                    **provenance,
                    "source_curve_index": index - 1,
                    "source_curve_position": index,
                    "source_curve_name": curve.source_curve_name,
                    "las_samples_uri": las_asset.samples_uri if las_asset else None,
                    **(_dlis_curve_provenance(curve, parsed) if dlis_asset is not None else {}),
                },
            )
        )

    return [
        ManagedProductGroup(
            group_key=definition.group_key,
            group_label=definition.group_label,
            items=items_by_group[definition.group_key],
        )
        for definition in PRODUCT_GROUP_ORDER
    ]



def _dlis_curve_provenance(curve, parsed) -> dict[str, object]:
    parts = str(curve.source_curve_name or "").split("|", 2)
    if len(parts) != 3:
        return {}
    logical_file_id, frame_id, mnemonic = parts
    channel = next((
        item for item in getattr(parsed, "dlis_channels", [])
        if item.logical_file_id == logical_file_id
        and item.frame_id == frame_id
        and item.mnemonic == mnemonic
    ), None)
    payload: dict[str, object] = {
        "dlis_logical_file_id": logical_file_id,
        "dlis_frame_id": frame_id,
        "dlis_channel_mnemonic": mnemonic,
    }
    if channel is not None:
        payload.update({
            "dlis_channel_dimensions": list(channel.dimensions),
            "dlis_index_channel": channel.index_channel,
            "dlis_channel_sample_count": channel.sample_count,
            "dlis_channel_supported": channel.supported,
        })
    return payload


def _runtime_classifications_for_curves(*, curve_headers, context_terms: Iterable[str | None]) -> list[CurveClassificationResult]:
    # KR-MDP-CLASSIFICATION-1:
    # Source Intake registration must consume the governed runtime KR resolver
    # before falling back to the legacy limited classifier. The runtime resolver
    # uses only seed + approved managed knowledge; candidate knowledge remains
    # excluded from production classification.
    classifier = RuntimeCurveClassificationService(
        ApprovedKnowledgeRuntimeResolver(ManagedKRRepository())
    )
    inputs = [
        CurveClassificationInput(
            source_mnemonic=curve.mnemonic or "",
            curve_id=curve.mnemonic or f"curve-{index}",
            unit=curve.unit,
            description=curve.description,
            source_curve_index=index,
            context={"source_intake_context_terms": [term for term in context_terms if term]},
        )
        for index, curve in enumerate(curve_headers, start=1)
    ]
    if not inputs:
        return []
    return list(classifier.classify_curves(inputs).classifications)


def _inventory_curve_classification_payload(*, curve, runtime_classification: CurveClassificationResult | None, context_terms: Iterable[str | None]) -> dict[str, object]:
    if runtime_classification is not None and runtime_classification.resolved:
        product_category = runtime_classification.product_group or "other_review_required"
        product_subgroup_key = runtime_classification.product_subgroup
        product_subgroup_label = _product_subgroup_label(product_category, product_subgroup_key)
        display_name = runtime_classification.display_name or runtime_classification.canonical_curve_id or curve.description or curve.mnemonic or "Classified curve"
        reasons = [
            f"Runtime KR resolved mnemonic {runtime_classification.normalized_mnemonic}.",
            f"Resolution source: {runtime_classification.resolution_source}.",
        ]
        if runtime_classification.knowledge_record_id:
            reasons.append(f"Knowledge record: {runtime_classification.knowledge_record_id}.")
        if runtime_classification.canonical_curve_id:
            reasons.append(f"Canonical curve: {runtime_classification.canonical_curve_id}.")
        if runtime_classification.warnings:
            reasons.extend(runtime_classification.warnings)
        return {
            "product_category": product_category,
            "product_subgroup_key": product_subgroup_key,
            "product_subgroup_label": product_subgroup_label,
            "curve_family": runtime_classification.family or "Unclassified",
            "curve_description": display_name,
            "curve_unit": runtime_classification.default_unit or curve.unit,
            "classification_confidence": _confidence_label(runtime_classification.confidence),
            "classification_source": runtime_classification.resolution_source,
            "classification_reasons": reasons,
            "review_required": runtime_classification.requires_review,
        }

    legacy = classify_well_log_curve(
        mnemonic=curve.mnemonic,
        description=curve.description,
        unit=curve.unit,
        context_terms=context_terms,
    )
    reasons = list(legacy.classification_reasons)
    if runtime_classification is not None:
        reasons.insert(0, f"Runtime KR unresolved for mnemonic {runtime_classification.normalized_mnemonic}; used deterministic fallback classifier.")
        reasons.extend(runtime_classification.warnings)
    return {
        "product_category": legacy.product_category,
        "product_subgroup_key": legacy.product_subgroup_key,
        "product_subgroup_label": legacy.product_subgroup_label,
        "curve_family": legacy.curve_family,
        "curve_description": legacy.curve_description,
        "curve_unit": legacy.curve_unit,
        "classification_confidence": legacy.classification_confidence,
        "classification_source": legacy.classification_source,
        "classification_reasons": reasons,
        "review_required": legacy.review_required,
    }


def _confidence_label(confidence: float | None) -> str:
    value = float(confidence or 0.0)
    if value >= 0.9:
        return "high"
    if value >= 0.6:
        return "medium"
    return "low"


def _product_subgroup_label(product_category: str | None, product_subgroup_key: str | None) -> str | None:
    if not product_subgroup_key:
        return None
    if product_category == "open_hole_logs":
        return OPEN_HOLE_SUBGROUP_LABELS.get(product_subgroup_key, product_subgroup_key.replace("_", " ").title())
    return product_subgroup_key.replace("_", " ").title()


def _merge_product_groups(existing: Iterable[ManagedProductGroup], incoming: Iterable[ManagedProductGroup]) -> list[ManagedProductGroup]:
    # KR-MDP-REFRESH-MERGE-1:
    # Re-registering a Source Intake candidate must replace that candidate's
    # previous product-group items before adding the newly classified items.
    # Otherwise a curve that moves from Other to a runtime-KR group remains
    # counted in the old group and MDP displays stale classification.
    incoming_groups = list(incoming)
    incoming_candidate_ids = {
        item.source_intake_candidate_id
        for group in incoming_groups
        for item in group.items
        if item.source_intake_candidate_id
    }
    incoming_product_prefixes = tuple(
        f"source-intake-curve:{candidate_id}:"
        for candidate_id in sorted(incoming_candidate_ids)
    )

    groups: dict[str, ManagedProductGroup] = {}
    for group in existing:
        next_group = group.model_copy(deep=True) if hasattr(group, "model_copy") else group.copy(deep=True)
        if incoming_candidate_ids:
            next_group.items = [
                item
                for item in next_group.items
                if not _is_replaced_source_intake_item(
                    item,
                    incoming_candidate_ids=incoming_candidate_ids,
                    incoming_product_prefixes=incoming_product_prefixes,
                )
            ]
        groups[next_group.group_key] = next_group

    for group in incoming_groups:
        target = groups.get(group.group_key)
        if target is None:
            groups[group.group_key] = group
            continue
        items = {item.product_id: item for item in target.items}
        for item in group.items:
            items[item.product_id] = item
        target.items = list(items.values())

    ordered_keys = [definition.group_key for definition in PRODUCT_GROUP_ORDER]
    return [groups[key] for key in ordered_keys if key in groups]


def _is_replaced_source_intake_item(
    item: ManagedProductGroupItem,
    *,
    incoming_candidate_ids: set[str],
    incoming_product_prefixes: tuple[str, ...],
) -> bool:
    if item.source_intake_candidate_id and item.source_intake_candidate_id in incoming_candidate_ids:
        return True
    if incoming_product_prefixes and item.product_id.startswith(incoming_product_prefixes):
        return True
    return False

def _merge_las_assets(existing: object, asset: dict[str, object]) -> list[dict[str, object]]:
    values = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []
    keyed = {str(item.get("asset_id") or item.get("source_fingerprint")): item for item in values}
    key = str(asset.get("asset_id") or asset.get("source_fingerprint"))
    keyed[key] = asset
    return list(keyed.values())


def _registration_note(candidate: SourceFileCandidate, *, uwi: str | None, approved_by: str | None, approval_note: str | None) -> str:
    parts = [f"Registered from WLV Source Intake candidate {candidate.source_file_id}."]
    if uwi is None:
        parts.append("UWI/API was missing in source metadata and was not replaced by internal well_id.")
    if approved_by:
        parts.append(f"Approved by {approved_by}.")
    if approval_note:
        parts.append(f"Approval note: {approval_note}")
    return " ".join(parts)


def _get_existing_record(inventory_service: ManagedWellInventoryService, managed_well_id: str) -> ManagedWellRecord | None:
    try:
        return inventory_service.repository.get_record(managed_well_id)
    except ManagedWellNotFoundError:
        return None


def _merge_source_references(existing: Iterable[ManagedSourceReference], new_reference: ManagedSourceReference) -> list[ManagedSourceReference]:
    refs: dict[str, ManagedSourceReference] = {reference.source_id: reference for reference in existing}
    refs[new_reference.source_id] = new_reference
    return list(refs.values())


def _merge_tags(existing: Iterable[str], additional: Iterable[str]) -> list[str]:
    values: list[str] = []
    for value in [*existing, *additional]:
        if value and value not in values:
            values.append(value)
    return values


def _merge_lifecycle_notes(existing: Iterable[str], new_note: str) -> list[str]:
    notes = list(existing)
    if new_note not in notes:
        notes.append(new_note)
    return notes


def _resolved_value(candidate: SourceFileCandidate, field_name: str) -> str | None:
    resolved = candidate.resolved_metadata
    if resolved is None:
        return None
    field = getattr(resolved, field_name, None)
    value = getattr(field, "value", None)
    return value if isinstance(value, str) and value.strip() else None


def _merged_top_depth(
    existing_value: float | None,
    incoming_value: float | None,
) -> float | None:
    values = [
        value
        for value in (existing_value, incoming_value)
        if value is not None
    ]
    return min(values) if values else None


def _merged_base_depth(
    existing_value: float | None,
    incoming_value: float | None,
) -> float | None:
    values = [
        value
        for value in (existing_value, incoming_value)
        if value is not None
    ]
    return max(values) if values else None


def _run_interval(log_header) -> str:
    if log_header is None or log_header.start_depth is None or log_header.stop_depth is None:
        return "—"
    depth_unit = log_header.depth_unit or "ft"
    return f"{log_header.start_depth:g}–{log_header.stop_depth:g} {depth_unit}"


def _clean(value: str | None) -> str:
    return clean_identity_value(value) or ""


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "unknown"
