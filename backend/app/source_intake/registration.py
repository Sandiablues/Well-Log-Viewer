"""Registration bridge from WLV Source Intake to Managed Well Inventory.

This module owns the first controlled handoff from the intake workbench into
backend-managed well inventory. It does not load data into the WDV and does not
create a viewer representation/conversion.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable
from app.source_intake.promotion_performance import now as _perf_now, elapsed_ms as _perf_ms, write_event as _perf_event

from app.classification.well_log_classifier import classify_well_log_curve
from app.classification_orchestration.general_family_projection import (
    project_general_curve_family,
    project_mwd_product_group,
)
from app.classification_orchestration.source_intake_bridge import (
    apply_source_intake_authority_outcome,
    build_source_intake_authority_outcomes,
)
from app.classification_orchestration.family_registry import canonical_family_key
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
from .depth_units import (
    UnsupportedDepthUnitError,
    convert_depth_range_to_target,
    depth_unit_conversion,
)
from .las_asset_store import LasAssetStore, LasAssetStoreError, StoredLasAsset
from .dlis_asset_store import DlisAssetStore, DlisAssetStoreError, StoredDlisAsset
from .readiness import evaluate_wmd_availability_readiness
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
from .resolution_service import is_wmd_eligible

_ALLOWED_REGISTER_QAQC_STATUSES = {
    SourceIntakeQaqcStatus.PASS,
    SourceIntakeQaqcStatus.WARNING,
    SourceIntakeQaqcStatus.REVIEW_REQUIRED,
}


def wmd_availability_block_reason(candidate: SourceFileCandidate) -> str | None:
    """Return the established registration diagnostic for an ineligible candidate.

    Structured eligibility is computed by readiness.py. This function preserves
    the existing public/tested rejection wording consumed by registration callers.
    """
    evaluate_wmd_availability_readiness(candidate)
    if candidate.readiness_state == SourceIntakeReadinessState.READY:
        return None

    depth_contract = candidate.depth_normalization
    if depth_contract is not None and getattr(depth_contract.status, "value", depth_contract.status) != "human_resolved":
        return "Depth target unit must be resolved to metres or feet before WMD availability."

    if candidate.is_available_to_wmd or candidate.resolution_state == SourceIntakeResolutionState.REGISTERED:
        return "Candidate is already registered in MWD."

    if candidate.resolution_state == SourceIntakeResolutionState.DUPLICATE:
        return "Candidate is an exact-content duplicate and cannot be made available again."

    if candidate.resolution_state == SourceIntakeResolutionState.EXCLUDED:
        return "Candidate is excluded from ingestion. Reopen it before WMD availability."

    if candidate.candidate_role == SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE:
        if candidate.parser_status not in {SourceIntakeParseStatus.PARSED, SourceIntakeParseStatus.PARSED_WITH_WARNINGS}:
            return f"Geometry candidate parser_status is not WMD-ready: {candidate.parser_status.value}."
        if candidate.geometry_preview is None:
            return "Geometry candidate has no parsed deviation-survey preview."
        if not candidate.geometry_preview.stations_preview:
            return "Geometry candidate preview has no station payload to register."
        if candidate.qaqc_status.status not in _ALLOWED_REGISTER_QAQC_STATUSES:
            return f"Geometry candidate QAQC status is not WMD-ready: {candidate.qaqc_status.status.value}."
        if candidate.qaqc_status.failure_count > 0:
            return "Geometry candidate QAQC has failures and cannot be made available."
        if not is_wmd_eligible(candidate):
            return (
                "Geometry candidate resolution state is not WMD-ready: "
                f"{candidate.resolution_state.value}. Resolve the candidate first."
            )
        return candidate.readiness_issues[0] if candidate.readiness_issues else None

    if candidate.candidate_role != SourceIntakeCandidateRole.WELL_LOG_CANDIDATE:
        return f"Only well_log_candidate records can be registered; got {candidate.candidate_role.value}."

    if candidate.parser_status not in {SourceIntakeParseStatus.PARSED, SourceIntakeParseStatus.PARSED_WITH_WARNINGS}:
        return f"Candidate parser_status is not WMD-ready: {candidate.parser_status.value}."

    if candidate.parsed_metadata is None:
        return "Candidate has no parsed well-log metadata."

    if candidate.qaqc_status.status not in _ALLOWED_REGISTER_QAQC_STATUSES:
        return f"Candidate QAQC status is not WMD-ready: {candidate.qaqc_status.status.value}."

    if candidate.qaqc_status.failure_count > 0:
        return "Candidate QAQC has failures and cannot be made available."

    well_name = _resolved_value(candidate, "well_name") or candidate.parsed_metadata.well_header.well_name
    if clean_identity_value(well_name) is None:
        return "Candidate has no resolved well name."

    if not is_wmd_eligible(candidate):
        return (
            "Candidate resolution state is not WMD-ready: "
            f"{candidate.resolution_state.value}. Resolve or explicitly disposition the candidate first."
        )

    return candidate.readiness_issues[0] if candidate.readiness_issues else "Candidate is not WMD-ready."


def registration_block_reason(candidate: SourceFileCandidate) -> str | None:
    """Compatibility alias for legacy API and test callers."""
    return wmd_availability_block_reason(candidate)

def _source_intake_provenance(candidate: SourceFileCandidate) -> dict[str, object]:
    depth_contract = candidate.depth_normalization
    depth_decision = depth_contract.decision if depth_contract is not None else None
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
        "depth_normalization": (
            {
                "raw_unit": depth_contract.raw_unit,
                "raw_start_depth": depth_contract.raw_start_depth,
                "raw_stop_depth": depth_contract.raw_stop_depth,
                "status": getattr(depth_contract.status, "value", depth_contract.status),
                "reason": depth_contract.reason,
                "selected_target_unit": depth_decision.target_unit if depth_decision is not None else None,
                "decision_actor": depth_decision.actor if depth_decision is not None else None,
                "decision_timestamp": str(depth_decision.decided_at) if depth_decision is not None else None,
                "decision_reason": depth_decision.reason if depth_decision is not None else None,
            }
            if depth_contract is not None
            else None
        ),
    }


def register_candidate_to_inventory(
    *,
    candidate: SourceFileCandidate,
    inventory_service: ManagedWellInventoryService,
    approved_by: str | None = None,
    approval_note: str | None = None,
) -> tuple[str, ManagedWellRecord]:
    """Create/update one Managed Well Inventory record from an intake candidate."""
    blocked = wmd_availability_block_reason(candidate)
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
        _repository_list_started = _perf_now()
        _repository_records = inventory_service.repository.list_records()
        _perf_event(
            "managed_inventory_repository_listed",
            candidate_id=candidate.source_file_id,
            elapsed_ms=_perf_ms(_repository_list_started),
            managed_well_count=len(_repository_records),
        )
        existing = find_record_by_canonical_name(
            _repository_records,
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
            raise ValueError(f"External DLIS source reference failed: {exc}") from exc
        asset_payload = dlis_asset.as_dict()
        provenance = {**provenance, "dlis_asset": asset_payload, "source_format": "DLIS"}
        source_kind = ManagedSourceKind.DLIS
        source_metadata = {
            **provenance,
            "parsed_metadata": parsed.model_dump(mode="json"),
            "canonical_source_metadata": (
                parsed.canonical_metadata.model_dump(mode="json")
                if parsed.canonical_metadata is not None
                else None
            ),
            "storage_uri": dlis_asset.original_uri,
            "dlis_asset_id": dlis_asset.asset_id,
        }
        source_fingerprint = dlis_asset.source_fingerprint
    else:
        try:
            las_asset = LasAssetStore().preserve_path(Path(candidate.original_path), source_id=candidate.source_file_id, filename=candidate.file_name)
        except LasAssetStoreError as exc:
            raise ValueError(f"External LAS source reference failed: {exc}") from exc
        asset_payload = las_asset.as_dict()
        provenance = {**provenance, "las_asset": asset_payload, "source_format": "LAS"}
        source_kind = ManagedSourceKind.LAS
        source_metadata = {
            **provenance,
            "parsed_metadata": parsed.model_dump(mode="json"),
            "canonical_source_metadata": (
                parsed.canonical_metadata.model_dump(mode="json")
                if parsed.canonical_metadata is not None
                else None
            ),
            "storage_uri": las_asset.original_uri,
            "las_manifest_uri": las_asset.manifest_uri,
            "las_samples_uri": las_asset.samples_uri,
            "las_asset_id": las_asset.asset_id,
        }
        source_fingerprint = las_asset.source_fingerprint
    if candidate.checksum and candidate.checksum != source_fingerprint:
        raise ValueError("Source Intake checksum does not match the external source content fingerprint.")
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

    managed_depth_unit, managed_top_depth, managed_base_depth = _managed_depth_range(
        candidate=candidate,
        existing=existing,
        log_header=log_header,
        fallback_unit=canonical_metadata["depth_unit"],
    )

    _product_groups_started = _perf_now()
    next_product_groups = _product_groups_from_candidate(
        candidate,
        las_asset=las_asset,
        dlis_asset=dlis_asset,
        managed_depth_unit=managed_depth_unit,
        managed_top_depth=managed_top_depth,
        managed_base_depth=managed_base_depth,
    )
    _perf_event(
        "managed_product_groups_constructed",
        candidate_id=candidate.source_file_id,
        elapsed_ms=_perf_ms(_product_groups_started),
        group_count=len(next_product_groups),
        curve_count=sum(len(group.items) for group in next_product_groups),
    )

    _product_merge_started = _perf_now()
    merged_product_groups = _merge_product_groups(
        existing.product_groups if existing else [],
        next_product_groups,
    )
    # Final WSI well-log presentation projection after merge:
    # stale legacy containers cannot override the accepted per-curve general family.
    # This remains upstream of generic inventory persistence so geometry/identity
    # contracts are not rewritten.
    merged_product_groups = _rebuild_classified_well_log_groups_from_general_family(
        merged_product_groups
    )
    _perf_event(
        "managed_product_groups_merged",
        candidate_id=candidate.source_file_id,
        elapsed_ms=_perf_ms(_product_merge_started),
        existing_curve_count=sum(
            len(group.items) for group in (existing.product_groups if existing else [])
        ),
        merged_curve_count=sum(len(group.items) for group in merged_product_groups),
    )

    record = ManagedWellRecord(
        managed_well_id=managed_well_id,
        well_id=well_id,
        well_name=well_name,
        operator=operator,
        field=field,
        block=block,
        country=canonical_metadata["country"],
        depth_unit=managed_depth_unit,
        top_depth=managed_top_depth,
        base_depth=managed_base_depth,
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
    _upsert_started = _perf_now()
    _upsert_result = inventory_service.upsert_managed_record(record)
    _perf_event(
        "managed_inventory_upsert_completed",
        candidate_id=candidate.source_file_id,
        elapsed_ms=_perf_ms(_upsert_started),
        action=_upsert_result[0],
        managed_well_id=_upsert_result[1].managed_well_id,
    )
    return _upsert_result



def _rebuild_classified_well_log_groups_from_general_family(
    product_groups: list[ManagedProductGroup],
) -> list[ManagedProductGroup]:
    """Re-bucket only governed WSI well-log curve items after merge.

    This is intentionally narrower than the generic inventory persistence boundary.

    Eligibility for regrouping:
      * the item carries the general-family projection contract; and
      * it carries the unified classification contract; and
      * it is a WDV-eligible curve with a resolved general family.

    Non-well-log items, geometry-owned items, unclassified items, and records
    without the classification/projection contracts retain their existing
    group/subgroup placement unchanged.
    """
    items_by_group: dict[str, list[ManagedProductGroupItem]] = {
        definition.group_key: [] for definition in PRODUCT_GROUP_ORDER
    }

    for source_group in product_groups:
        source_group_key = (
            source_group.group_key
            if source_group.group_key in items_by_group
            else "other_review_required"
        )

        for item in source_group.items:
            target_group_key = source_group_key

            has_general_family_contract = bool(
                item.general_curve_family_projection_version
                and item.general_curve_family_key
                and item.general_curve_family
            )
            has_classification_contract = bool(item.classification_contract_version)
            resolved_general_family = (
                str(item.general_curve_family_key or "").strip().lower()
                not in {"", "unclassified", "unknown"}
            )

            if (
                has_general_family_contract
                and has_classification_contract
                and bool(item.display_in_wdv)
                and resolved_general_family
            ):
                projected_group = project_mwd_product_group(
                    current_product_category=item.product_category,
                    measurement_domain_key=item.measurement_domain_key,
                    general_family_key=item.general_curve_family_key,
                    display_in_wdv=True,
                )
                if projected_group in items_by_group:
                    target_group_key = projected_group

                # MWD and WDV consume the exact same persisted GENERAL family.
                item.product_category = target_group_key
                item.product_subgroup_key = item.general_curve_family_key
                item.product_subgroup_label = item.general_curve_family

            items_by_group[target_group_key].append(item)

    return [
        ManagedProductGroup(
            group_key=definition.group_key,
            group_label=definition.group_label,
            items=items_by_group[definition.group_key],
        )
        for definition in PRODUCT_GROUP_ORDER
    ]


def _product_groups_from_candidate(
    candidate: SourceFileCandidate,
    *,
    las_asset: StoredLasAsset | None = None,
    dlis_asset: StoredDlisAsset | None = None,
    managed_depth_unit: str,
    managed_top_depth: float | None,
    managed_base_depth: float | None,
) -> list[ManagedProductGroup]:
    parsed = candidate.parsed_metadata
    log_header = parsed.log_header if parsed else None
    curve_headers = parsed.curve_headers if parsed else []
    items_by_group: dict[str, list[ManagedProductGroupItem]] = {
        definition.group_key: [] for definition in PRODUCT_GROUP_ORDER
    }
    run_interval = _managed_run_interval(
        managed_top_depth,
        managed_base_depth,
        managed_depth_unit,
    )
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
    _runtime_classification_started = _perf_now()
    runtime_classifications = _runtime_classifications_for_curves(
        curve_headers=curve_headers,
        context_terms=context_terms,
    )
    _perf_event(
        "runtime_kr_classification_completed",
        candidate_id=candidate.source_file_id,
        elapsed_ms=_perf_ms(_runtime_classification_started),
        curve_count=len(curve_headers),
        resolved_count=sum(1 for item in runtime_classifications if item.resolved),
    )

    _authority_started = _perf_now()
    authority_outcomes = build_source_intake_authority_outcomes(
        curve_headers=curve_headers,
        context_terms=context_terms,
        source_kind=(ManagedSourceKind.DLIS.value if dlis_asset is not None else ManagedSourceKind.LAS.value),
        source_uid=candidate.source_file_id,
        runtime_classifications=runtime_classifications,
    )
    _perf_event(
        "classification_authority_evaluation_completed",
        candidate_id=candidate.source_file_id,
        elapsed_ms=_perf_ms(_authority_started),
        outcome_count=len(authority_outcomes),
    )
    authority_by_index = {item.curve_index: item for item in authority_outcomes}
    _curve_item_build_started = _perf_now()

    # The runtime batch observer has already compared every curve against the
    # deterministic classifier using one shared KR snapshot/registry. Suppress
    # duplicate per-curve observer work while building managed items; this does
    # not change classification authority or any persisted classification value.
    from app.classification_orchestration.live_shadow_observer import suppress_shadow_observer

    with suppress_shadow_observer():
        for index, curve in enumerate(curve_headers, start=1):
            runtime_classification = runtime_classifications[index - 1] if index - 1 < len(runtime_classifications) else None
            classification = _inventory_curve_classification_payload(
                curve=curve,
                runtime_classification=runtime_classification,
                context_terms=context_terms,
            )
            classification = apply_source_intake_authority_outcome(
                classification,
                authority_by_index.get(index),
            )
            review_required = bool(classification["review_required"] or candidate.qaqc_status.review_required)
            general_family = project_general_curve_family(
                classification.get("curve_family_key"),
                classification.get("curve_family"),
            )
            display_in_wdv = bool(classification.get("display_in_wdv", True))
            # The accepted backend measurement-domain contract may resolve a curve
            # that the legacy product-category path left in Other / Review required.
            # Project only that stale review bucket into the governed MWD product
            # group. No mnemonic or frontend inference is permitted.
            projected_product_category = project_mwd_product_group(
                current_product_category=classification.get("product_category"),
                measurement_domain_key=classification.get("measurement_domain_key"),
                general_family_key=general_family.family_key,
                display_in_wdv=display_in_wdv,
            )
            group_key = (
                projected_product_category
                if projected_product_category in items_by_group
                else "other_review_required"
            )
            # MWD and WDV must present the same GENERAL CURVE FAMILY category.
            # Detailed subtype/classification remains on curve_family/curve_family_key.
            mwd_subgroup_key = (
                general_family.family_key
                if display_in_wdv and general_family.family_key != "unclassified"
                else classification.get("product_subgroup_key")
            )
            mwd_subgroup_label = (
                general_family.family_label
                if display_in_wdv and general_family.family_key != "unclassified"
                else classification.get("product_subgroup_label")
            )
            items_by_group[group_key].append(
                ManagedProductGroupItem(
                product_id=f"source-intake-curve:{candidate.source_file_id}:{index}:{_slug(curve.mnemonic or 'curve')}",
                display_name=curve.mnemonic or f"Curve {index}",
                curve_name=curve.mnemonic or f"Curve {index}",
                curve_type=classification["curve_description"],
                curve_description=classification["curve_description"],
                curve_unit=classification["curve_unit"],
                product_category=projected_product_category,
                product_subgroup_key=mwd_subgroup_key,
                product_subgroup_label=mwd_subgroup_label,
                curve_family=classification["curve_family"],
                curve_family_key=classification.get("curve_family_key"),
                general_curve_family=general_family.family_label,
                general_curve_family_key=general_family.family_key,
                general_curve_family_projection_version=general_family.projection_version,
                measurement_domain_key=classification.get("measurement_domain_key"),
                measurement_domain_label=classification.get("measurement_domain_label"),
                destination_key=classification.get("destination_key"),
                destination_owner=classification.get("destination_owner"),
                display_in_wdv=bool(classification.get("display_in_wdv", True)),
                classification_contract_version=classification.get("classification_contract_version"),
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
                curve_statistics=(
                    {
                        **curve.curve_statistics,
                        "source_checksum": candidate.checksum,
                    }
                    if curve.curve_statistics is not None
                    else None
                ),
                provenance={
                    **provenance,
                    "source_curve_index": index - 1,
                    "source_curve_position": index,
                    "source_curve_name": curve.source_curve_name,
                    "las_samples_uri": las_asset.samples_uri if las_asset else None,
                    **(
                        _dlis_curve_provenance(
                            curve,
                            parsed,
                            managed_depth_unit=managed_depth_unit,
                            managed_top_depth=managed_top_depth,
                            managed_base_depth=managed_base_depth,
                        )
                        if dlis_asset is not None
                        else {}
                    ),
                },
            )
        )

    _result_groups = [
        ManagedProductGroup(
            group_key=definition.group_key,
            group_label=definition.group_label,
            items=items_by_group[definition.group_key],
        )
        for definition in PRODUCT_GROUP_ORDER
    ]
    _perf_event(
        "managed_curve_items_constructed",
        candidate_id=candidate.source_file_id,
        elapsed_ms=_perf_ms(_curve_item_build_started),
        curve_count=len(curve_headers),
        group_count=len(_result_groups),
    )
    return _result_groups



def _dlis_curve_provenance(
    curve,
    parsed,
    *,
    managed_depth_unit: str,
    managed_top_depth: float | None,
    managed_base_depth: float | None,
) -> dict[str, object]:
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
            "dlis_raw_depth_unit": channel.raw_depth_unit,
            "dlis_depth_scale_factor": channel.depth_scale_factor,
            "dlis_parser_normalized_depth_unit": channel.normalized_depth_unit,
            "managed_depth_unit": managed_depth_unit,
            "managed_top_depth": managed_top_depth,
            "managed_base_depth": managed_base_depth,
        })
    return payload


def _runtime_classifications_for_curves(*, curve_headers, context_terms: Iterable[str | None]) -> list[CurveClassificationResult]:
    # KR-MDP-CLASSIFICATION-1:
    # Source Intake registration must consume the governed runtime KR resolver
    # before falling back to the compatibility classifier. The runtime resolver
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
            "curve_family_key": canonical_family_key(runtime_classification.family) or "unclassified",
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
        "curve_family_key": canonical_family_key(legacy.curve_family) or "unclassified",
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
    # WMD-IDEMPOTENCY-1 + KR-MDP-REFRESH-MERGE-1:
    # Re-registering the same source content must replace previous managed curve
    # rows even when Source Intake creates a new occurrence/candidate id for the
    # same physical LAS/DLIS file. Candidate-id replacement remains necessary
    # for ordinary refreshes, while source fingerprint replacement prevents a
    # second full inventory from being appended under a new occurrence id.
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
    incoming_fingerprints = {
        fingerprint
        for group in incoming_groups
        for item in group.items
        for fingerprint in _source_fingerprints_from_item(item)
    }

    groups: dict[str, ManagedProductGroup] = {}
    for group in existing:
        next_group = group.model_copy(deep=True) if hasattr(group, "model_copy") else group.copy(deep=True)
        next_group.items = [
            item
            for item in next_group.items
            if not _is_replaced_source_intake_item(
                item,
                incoming_candidate_ids=incoming_candidate_ids,
                incoming_product_prefixes=incoming_product_prefixes,
                incoming_fingerprints=incoming_fingerprints,
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


def _source_fingerprints_from_item(item: ManagedProductGroupItem) -> set[str]:
    provenance = item.provenance if isinstance(item.provenance, dict) else {}
    values: list[object] = [
        provenance.get("checksum"),
        provenance.get("source_fingerprint"),
        provenance.get("fingerprint"),
    ]
    for asset_key in ("dlis_asset", "las_asset"):
        asset = provenance.get(asset_key)
        if isinstance(asset, dict):
            values.extend([
                asset.get("source_fingerprint"),
                asset.get("checksum"),
                asset.get("fingerprint"),
            ])
    fingerprints: set[str] = set()
    for value in values:
        text = str(value or "").strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", text):
            fingerprints.add(text)
    return fingerprints


def _is_replaced_source_intake_item(
    item: ManagedProductGroupItem,
    *,
    incoming_candidate_ids: set[str],
    incoming_product_prefixes: tuple[str, ...],
    incoming_fingerprints: set[str],
) -> bool:
    if item.source_intake_candidate_id and item.source_intake_candidate_id in incoming_candidate_ids:
        return True
    if incoming_product_prefixes and item.product_id.startswith(incoming_product_prefixes):
        return True
    if incoming_fingerprints and (_source_fingerprints_from_item(item) & incoming_fingerprints):
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
    # Same physical source content may be re-scanned under a new Source Intake
    # occurrence id. Do not retain two active managed source references for one
    # content checksum.
    new_checksum = str(new_reference.checksum or "").strip().lower()
    refs: dict[str, ManagedSourceReference] = {}
    for reference in existing:
        reference_checksum = str(reference.checksum or "").strip().lower()
        if reference.source_id == new_reference.source_id:
            continue
        if new_checksum and reference_checksum == new_checksum:
            continue
        refs[reference.source_id] = reference
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


def _managed_depth_range(
    *,
    candidate: SourceFileCandidate,
    existing: ManagedWellRecord | None,
    log_header,
    fallback_unit: str | None,
) -> tuple[str, float | None, float | None]:
    """Normalize an incoming range before combining it with a managed well."""
    contract = candidate.depth_normalization
    selected_target = (
        contract.decision.target_unit.strip().casefold()
        if contract is not None and contract.decision is not None
        else None
    )

    existing_unit = str(existing.depth_unit or "").strip().casefold() if existing else None
    target_unit = existing_unit or selected_target
    if target_unit not in {"m", "ft"}:
        fallback = depth_unit_conversion(fallback_unit)
        if not fallback.supported or fallback.normalized_unit not in {"m", "ft"}:
            raise ValueError(f"Cannot establish managed depth unit from {fallback_unit!r}.")
        target_unit = fallback.normalized_unit

    incoming_top = log_header.start_depth if log_header is not None else None
    incoming_base = log_header.stop_depth if log_header is not None else None
    incoming_unit = log_header.depth_unit if log_header is not None else target_unit

    try:
        normalized_top, normalized_base = convert_depth_range_to_target(
            incoming_top, incoming_base, incoming_unit, target_unit
        )
    except UnsupportedDepthUnitError as exc:
        raise ValueError(str(exc)) from exc

    return (
        target_unit,
        _merged_top_depth(existing.top_depth if existing else None, normalized_top),
        _merged_base_depth(existing.base_depth if existing else None, normalized_base),
    )

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


def _managed_run_interval(
    top_depth: float | None,
    base_depth: float | None,
    depth_unit: str,
) -> str:
    if top_depth is None or base_depth is None:
        return "—"
    if depth_unit not in {"m", "ft"}:
        raise ValueError(f"Unsupported managed depth unit: {depth_unit!r}")
    return f"{top_depth:g}–{base_depth:g} {depth_unit}"


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
