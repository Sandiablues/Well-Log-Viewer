"""Read-only KR managed-instruction API.

Approved KR records are exposed as explicit application instructions.  This is
not a reference-only surface: it is the read contract downstream decision
services must use before treating KR knowledge as runtime truth.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

CONTRACT_VERSION = "kr_managed_instructions_v1"
TRUTH_RECORD_TYPES = {
    "curve_definition",
    "alias",
    "classification_rule",
    "display_rule",
    "preview_template",
    "preview_template_track",
    "template_selection_rule",
    "template_curve_family_requirement",
    "template_scale_default",
    "track_object_type",
    "las_standard_rule",
}

router = APIRouter(prefix="/api/wlv/knowledge/instructions", tags=["knowledge-instructions"])


class EvidenceRef(BaseModel):
    evidence_id: str
    source_type: str | None = None
    source_label: str | None = None
    source_reference: str | None = None
    confidence: float | int | None = None
    notes: str | None = None


class InstructionSummary(BaseModel):
    instruction_id: str
    source_record_type: str
    instruction_type: str
    status: str
    runtime_eligible: bool
    production_eligible: bool
    subject: str
    application_area: str | None = None
    template_key: str | None = None
    track_id: str | None = None
    curve_family: str | None = None
    canonical_curve_id: str | None = None
    alias: str | None = None
    must_do: str
    must_not_do: str | None = None
    evidence_ref_count: int = 0
    approved_by: str | None = None
    updated_at: str | None = None


class InstructionDetail(InstructionSummary):
    evidence: list[EvidenceRef] = Field(default_factory=list)
    raw_record: dict[str, Any] = Field(default_factory=dict)


class InstructionListResponse(BaseModel):
    service: str = "kr_managed_instruction_service"
    contract_version: str = CONTRACT_VERSION
    approved_only: bool = True
    candidate_records_used: bool = False
    deprecated_records_used: bool = False
    total_count: int
    returned_count: int
    instructions: list[InstructionSummary]


class InstructionDetailResponse(BaseModel):
    service: str = "kr_managed_instruction_service"
    contract_version: str = CONTRACT_VERSION
    instruction: InstructionDetail


class InstructionSummaryResponse(BaseModel):
    service: str = "kr_managed_instruction_service"
    contract_version: str = CONTRACT_VERSION
    record_type_counts: dict[str, int]
    instruction_type_counts: dict[str, int]
    status_counts: dict[str, int]
    runtime_eligible_count: int
    production_eligible_count: int
    evidence_record_count: int


class TemplateDecisionResponse(BaseModel):
    service: str = "kr_managed_instruction_service"
    contract_version: str = CONTRACT_VERSION
    template_key: str
    instruction_count: int
    template_instructions: list[InstructionSummary]
    track_instructions: list[InstructionSummary]
    selection_instructions: list[InstructionSummary]
    curve_instructions: list[InstructionSummary]
    evidence: list[EvidenceRef] = Field(default_factory=list)


def _load() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = json.loads(Path("backend/data/knowledge/managed_knowledge.json").read_text())
    return data.get("records", []), data.get("evidence_records", [])


def _truth(record: dict[str, Any]) -> bool:
    return (
        record.get("status") == "approved"
        and record.get("record_type") in TRUTH_RECORD_TYPES
        and record.get("runtime_eligible") is not False
        and record.get("production_eligible") is not False
    )


def _instruction_type(record_type: str) -> str:
    if record_type in {"curve_definition", "alias", "classification_rule", "display_rule"}:
        return "curve_instruction"
    if record_type in {"preview_template", "template_selection_rule"}:
        return "template_instruction"
    if record_type in {"preview_template_track", "track_object_type", "template_scale_default"}:
        return "track_instruction"
    if record_type == "template_curve_family_requirement":
        return "selection_instruction"
    return "application_instruction"


def _subject(record: dict[str, Any]) -> str:
    for key in ("template_label", "track_name", "display_name", "alias", "curve_family", "family", "canonical_curve_id", "rule_id", "record_id"):
        value = record.get(key)
        if value:
            return str(value)
    return "unknown"


def _area(record: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for key in ("product_group", "product_subgroup", "workflow_context", "template_key", "preferred_track_family"):
        value = record.get(key)
        if value and str(value) not in parts:
            parts.append(str(value))
    return " / ".join(parts) if parts else None


def _must_do(record: dict[str, Any]) -> str:
    rt = record.get("record_type")
    if rt == "curve_definition":
        return f"Treat {record.get('display_name') or record.get('canonical_curve_id')} as curve family {record.get('family') or 'unknown'}."
    if rt == "alias":
        return f"Resolve alias {record.get('alias')} to canonical curve {record.get('canonical_curve_id')}."
    if rt == "classification_rule":
        return f"When {record.get('match_type')} matches {record.get('match_value')}, classify as {record.get('curve_family')}."
    if rt == "display_rule":
        return f"Display {record.get('canonical_curve_id')} on {record.get('preferred_track_family') or 'assigned track'} using {record.get('scale_type') or 'default'} scale."
    if rt == "preview_template":
        return f"Use template {record.get('template_key')} with required {record.get('required_curve_families') or []}, preferred {record.get('preferred_curve_families') or []}, optional {record.get('optional_curve_families') or []}."
    if rt == "template_selection_rule":
        return f"For template {record.get('template_key')}, enforce required {record.get('required_families') or []} and rank preferred {record.get('preferred_families') or []}."
    if rt == "preview_template_track":
        return f"Render track {record.get('track_id')} as {record.get('renderer_type')} for role {record.get('track_role') or record.get('track_name')}."
    if rt == "template_curve_family_requirement":
        return f"For template {record.get('template_key')} track {record.get('track_id')}, treat {record.get('curve_family')} as {record.get('requirement_level')} with policy {record.get('selection_policy') or 'backend selection'}."
    if rt == "template_scale_default":
        return f"Use {record.get('scale_type') or 'default'} display scale for {record.get('curve_family')}."
    return f"Follow approved KR record {record.get('record_id')}."


def _must_not(record: dict[str, Any]) -> str | None:
    rt = record.get("record_type")
    if rt in {"preview_template", "template_selection_rule", "template_curve_family_requirement"}:
        return "Do not use candidate, deprecated, or frontend-inferred rules for this decision."
    if rt in {"curve_definition", "alias", "classification_rule"}:
        return "Do not override this approved classification with unapproved candidate knowledge."
    return None


def _summary(record: dict[str, Any]) -> InstructionSummary:
    return InstructionSummary(
        instruction_id=str(record.get("record_id")),
        source_record_type=str(record.get("record_type")),
        instruction_type=_instruction_type(str(record.get("record_type"))),
        status=str(record.get("status")),
        runtime_eligible=record.get("runtime_eligible") is not False,
        production_eligible=record.get("production_eligible") is not False,
        subject=_subject(record),
        application_area=_area(record),
        template_key=record.get("template_key"),
        track_id=record.get("track_id"),
        curve_family=record.get("curve_family") or record.get("family"),
        canonical_curve_id=record.get("canonical_curve_id"),
        alias=record.get("alias"),
        must_do=_must_do(record),
        must_not_do=_must_not(record),
        evidence_ref_count=len(record.get("evidence_refs") or []),
        approved_by=record.get("approved_by") or record.get("reviewed_by"),
        updated_at=record.get("updated_at"),
    )


def _evidence_index(evidence_records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(e.get("evidence_id")): e for e in evidence_records if e.get("evidence_id")}


def _evidence_ref(record: dict[str, Any]) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=str(record.get("evidence_id")),
        source_type=record.get("source_type"),
        source_label=record.get("source_label"),
        source_reference=record.get("source_reference"),
        confidence=record.get("confidence"),
        notes=record.get("notes"),
    )


@router.get("/summary", response_model=InstructionSummaryResponse)
def get_summary() -> InstructionSummaryResponse:
    records, evidence = _load()
    truth = [r for r in records if _truth(r)]
    return InstructionSummaryResponse(
        record_type_counts=dict(Counter(str(r.get("record_type")) for r in records)),
        instruction_type_counts=dict(Counter(_instruction_type(str(r.get("record_type"))) for r in truth)),
        status_counts=dict(Counter(str(r.get("status")) for r in records)),
        runtime_eligible_count=sum(1 for r in truth if r.get("runtime_eligible") is not False),
        production_eligible_count=sum(1 for r in truth if r.get("production_eligible") is not False),
        evidence_record_count=len(evidence),
    )


@router.get("", response_model=InstructionListResponse)
def list_instructions(q: str | None = None, instruction_type: str | None = None, record_type: str | None = None, template_key: str | None = None, curve_family: str | None = None, limit: int = Query(default=100, ge=1, le=500)) -> InstructionListResponse:
    records, _ = _load()
    query = (q or "").strip().lower()
    out: list[InstructionSummary] = []
    for record in records:
        if not _truth(record):
            continue
        item = _summary(record)
        if instruction_type and item.instruction_type != instruction_type:
            continue
        if record_type and item.source_record_type != record_type:
            continue
        if template_key and item.template_key != template_key:
            continue
        if curve_family and (item.curve_family or "").lower() != curve_family.lower():
            continue
        if query and query not in json.dumps(record, sort_keys=True).lower():
            continue
        out.append(item)
    out.sort(key=lambda x: (x.instruction_type, x.template_key or "", x.subject, x.instruction_id))
    returned = out[:limit]
    return InstructionListResponse(total_count=len(out), returned_count=len(returned), instructions=returned)


@router.get("/templates/{template_key}/decision", response_model=TemplateDecisionResponse)
def template_decision(template_key: str) -> TemplateDecisionResponse:
    records, evidence_records = _load()
    truth = [r for r in records if _truth(r)]
    template_records = [r for r in truth if r.get("template_key") == template_key]
    template_items = [_summary(r) for r in template_records if _instruction_type(str(r.get("record_type"))) == "template_instruction"]
    track_items = [_summary(r) for r in template_records if _instruction_type(str(r.get("record_type"))) == "track_instruction"]
    selection_items = [_summary(r) for r in template_records if _instruction_type(str(r.get("record_type"))) == "selection_instruction"]
    families = {item.curve_family for item in selection_items if item.curve_family}
    curve_items = [
        _summary(r) for r in truth
        if _instruction_type(str(r.get("record_type"))) == "curve_instruction"
        and ((r.get("curve_family") or r.get("family")) in families or r.get("canonical_curve_id") in families)
    ][:100]
    evidence_by_id = _evidence_index(evidence_records)
    evidence_ids: list[str] = []
    for r in template_records:
        for eid in r.get("evidence_refs") or []:
            if eid not in evidence_ids:
                evidence_ids.append(eid)
    evidence = [_evidence_ref(evidence_by_id[eid]) for eid in evidence_ids if eid in evidence_by_id]
    return TemplateDecisionResponse(
        template_key=template_key,
        instruction_count=len(template_items) + len(track_items) + len(selection_items) + len(curve_items),
        template_instructions=template_items,
        track_instructions=track_items,
        selection_instructions=selection_items,
        curve_instructions=curve_items,
        evidence=evidence,
    )


@router.get("/{instruction_id}", response_model=InstructionDetailResponse)
def instruction_detail(instruction_id: str) -> InstructionDetailResponse:
    records, evidence_records = _load()
    record = next((r for r in records if r.get("record_id") == instruction_id and _truth(r)), None)
    if record is None:
        raise HTTPException(status_code=404, detail="KR instruction not found or not approved/runtime eligible")
    evidence_by_id = _evidence_index(evidence_records)
    evidence = [_evidence_ref(evidence_by_id[eid]) for eid in record.get("evidence_refs") or [] if eid in evidence_by_id]
    detail = InstructionDetail(**_summary(record).model_dump(), evidence=evidence, raw_record=record)
    return InstructionDetailResponse(instruction=detail)
