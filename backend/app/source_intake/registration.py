"""Registration bridge from WLV Source Intake to Managed Well Inventory.

This module owns the first controlled handoff from the intake workbench into
backend-managed well inventory. It does not load data into the WDV and does not
create a viewer representation/conversion.
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

from backend.app.classification.well_log_classifier import classify_well_log_curve
from backend.app.classification.well_log_vocabulary import PRODUCT_GROUP_ORDER
from backend.app.inventory.models import (
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
from backend.app.inventory.repository import ManagedWellNotFoundError
from backend.app.inventory.service import ManagedWellInventoryService

from .models import (
    SourceFileCandidate,
    SourceIntakeCandidateRole,
    SourceIntakeParseStatus,
    SourceIntakeQaqcStatus,
)

_ALLOWED_REGISTER_QAQC_STATUSES = {
    SourceIntakeQaqcStatus.PASS,
    SourceIntakeQaqcStatus.WARNING,
    SourceIntakeQaqcStatus.REVIEW_REQUIRED,
}


def registration_block_reason(candidate: SourceFileCandidate) -> str | None:
    """Return a durable reason when a candidate is not registration-eligible."""
    if candidate.candidate_role != SourceIntakeCandidateRole.WELL_LOG_CANDIDATE:
        return f"Only well_log_candidate records can be registered; got {candidate.candidate_role.value}."

    if candidate.parser_status not in {SourceIntakeParseStatus.PARSED, SourceIntakeParseStatus.PARSED_WITH_WARNINGS}:
        return f"Candidate parser_status is not registration-ready: {candidate.parser_status.value}."

    if candidate.parsed_metadata is None:
        return "Candidate has no parsed LAS metadata."

    if candidate.qaqc_status.status not in _ALLOWED_REGISTER_QAQC_STATUSES:
        return f"Candidate QAQC status is not registration-ready: {candidate.qaqc_status.status.value}."

    if candidate.qaqc_status.failure_count > 0:
        return "Candidate QAQC has failures and cannot be registered."

    well_name = _resolved_value(candidate, "well_name") or candidate.parsed_metadata.well_header.well_name
    if not _clean(well_name):
        return "Candidate has no resolved well name."

    return None


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

    well_name = _clean(_resolved_value(candidate, "well_name") or well_header.well_name) or candidate.file_name
    uwi = _clean(_resolved_value(candidate, "uwi") or well_header.uwi) or None
    operator = _clean(_resolved_value(candidate, "operator") or well_header.operator) or None
    field = _clean(_resolved_value(candidate, "field") or well_header.field) or None
    block = _clean(_resolved_value(candidate, "block") or well_header.block) or None

    well_id = _managed_well_identity(well_name=well_name, uwi=uwi)
    managed_well_id = f"managed-well:{well_id}"
    provenance = _source_intake_provenance(candidate)
    source_reference = ManagedSourceReference(
        source_id=candidate.source_file_id,
        source_kind=ManagedSourceKind.LAS,
        display_name=candidate.file_name,
        original_path=candidate.original_path,
        file_name=candidate.file_name,
        file_format=candidate.detected_file_type.value,
        checksum=candidate.checksum,
        metadata={**provenance, "parsed_metadata": parsed.model_dump(mode="json")},
    )

    review_required = bool(candidate.review_required or candidate.qaqc_status.review_required)
    lifecycle_state = (
        ManagedInventoryLifecycleState.REVIEW_REQUIRED if review_required else ManagedInventoryLifecycleState.REGISTERED
    )
    now = utc_now_iso()
    created_at = now
    existing = _get_existing_record(inventory_service, managed_well_id)
    if existing is not None:
        created_at = existing.created_at

    record = ManagedWellRecord(
        managed_well_id=managed_well_id,
        well_id=well_id,
        well_name=well_name,
        operator=operator,
        field=field,
        block=block,
        country=well_header.country,
        depth_unit=(well_header.depth_unit or (log_header.depth_unit if log_header else None) or "ft"),
        top_depth=log_header.start_depth if log_header else None,
        base_depth=log_header.stop_depth if log_header else None,
        status=lifecycle_state,
        lifecycle_state=lifecycle_state,
        wmdp_state=ManagedWmdpState.STAGED_IN_WMDP,
        wdv_state=ManagedWdvState.NOT_LOADED,
        source_intake_candidate_id=candidate.source_file_id,
        wmdp_available=True,
        source_references=_merge_source_references(existing.source_references if existing else [], source_reference),
        viewer_packages=existing.viewer_packages if existing else [],
        product_groups=_product_groups_from_candidate(candidate),
        tags=_merge_tags(existing.tags if existing else [], ["source-intake", "las"]),
        metadata={
            **(existing.metadata if existing else {}),
            "uwi": uwi,
            "uwi_missing": uwi is None,
            "source_intake_registered": True,
            "wmdp_state": ManagedWmdpState.STAGED_IN_WMDP.value,
            "wdv_state": ManagedWdvState.NOT_LOADED.value,
            "wmdp_available": True,
            "source_intake_provenance": provenance,
            "source_intake_candidate_id": candidate.source_file_id,
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


def _product_groups_from_candidate(candidate: SourceFileCandidate) -> list[ManagedProductGroup]:
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

    for index, curve in enumerate(curve_headers, start=1):
        classification = classify_well_log_curve(
            mnemonic=curve.mnemonic,
            description=curve.description,
            unit=curve.unit,
            context_terms=context_terms,
        )
        group_key = classification.product_category if classification.product_category in items_by_group else "other_review_required"
        review_required = bool(classification.review_required or candidate.qaqc_status.review_required)
        items_by_group[group_key].append(
            ManagedProductGroupItem(
                product_id=f"source-intake-curve:{candidate.source_file_id}:{index}:{_slug(curve.mnemonic or 'curve')}",
                display_name=curve.mnemonic or f"Curve {index}",
                curve_name=curve.mnemonic or f"Curve {index}",
                curve_type=classification.curve_description,
                curve_description=classification.curve_description,
                curve_unit=classification.curve_unit,
                product_category=classification.product_category,
                curve_family=classification.curve_family,
                classification_confidence=classification.classification_confidence,
                classification_source=classification.classification_source,
                classification_reasons=classification.classification_reasons,
                review_required=review_required,
                run_date=run_date,
                run_interval=run_interval,
                run_number=run_number,
                qa_flag="Review" if review_required else "Passed",
                selectable=True,
                source_kind=ManagedSourceKind.LAS.value,
                source_id=candidate.source_file_id,
                viewer_package_id=None,
                wmdp_state=ManagedWmdpState.STAGED_IN_WMDP,
                wdv_state=ManagedWdvState.NOT_LOADED,
                source_intake_candidate_id=candidate.source_file_id,
                provenance=provenance,
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


def _managed_well_identity(*, well_name: str, uwi: str | None) -> str:
    if uwi:
        return f"wlv-intake-uwi-{_slug(uwi)}"
    digest = hashlib.sha256(well_name.strip().lower().encode("utf-8")).hexdigest()[:10]
    return f"wlv-intake-name-{_slug(well_name)}-{digest}"


def _run_interval(log_header) -> str:
    if log_header is None or log_header.start_depth is None or log_header.stop_depth is None:
        return "—"
    depth_unit = log_header.depth_unit or "ft"
    return f"{log_header.start_depth:g}–{log_header.stop_depth:g} {depth_unit}"


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "unknown"
