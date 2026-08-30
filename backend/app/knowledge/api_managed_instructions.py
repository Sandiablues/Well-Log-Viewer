"""Read-only KR managed-instruction API.

Approved KR records are exposed as explicit application instructions.  This is
not a reference-only surface: it is the read contract downstream decision
services must use before treating KR knowledge as runtime truth.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from uuid import uuid4
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .managed_storage import ManagedStorage

CONTRACT_VERSION = "kr_managed_instructions_v1"
TRUTH_RECORD_TYPES = {
    "managed_instruction",
    "curve_definition",
    "standard_mnemonic",
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
    mnemonic: str | None = None
    unit_hint: str | None = None
    description: str | None = None
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
    offset: int = 0
    limit: int = 100
    has_previous: bool = False
    has_next: bool = False
    search_ranked: bool = False
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


class CandidateInstructionCreateRequest(BaseModel):
    instruction_type: str = "application_instruction"
    subject: str
    application_area: str | None = None
    template_key: str | None = None
    track_id: str | None = None
    curve_family: str | None = None
    canonical_curve_id: str | None = None
    alias: str | None = None
    mnemonic: str | None = None
    unit_hint: str | None = None
    description: str | None = None
    must_do: str
    must_not_do: str | None = None
    allowed_use: str | None = None
    priority: int | None = None
    evidence_note: str | None = None
    change_reason: str | None = None
    supersedes_record_id: str | None = None
    reviewer: str | None = "user"


class CandidateInstructionUpdateRequest(BaseModel):
    instruction_type: str | None = None
    subject: str | None = None
    application_area: str | None = None
    template_key: str | None = None
    track_id: str | None = None
    curve_family: str | None = None
    canonical_curve_id: str | None = None
    alias: str | None = None
    mnemonic: str | None = None
    unit_hint: str | None = None
    description: str | None = None
    must_do: str | None = None
    must_not_do: str | None = None
    allowed_use: str | None = None
    priority: int | None = None
    evidence_note: str | None = None
    change_reason: str | None = None
    supersedes_record_id: str | None = None
    reviewer: str | None = "user"


class GovernanceActionRequest(BaseModel):
    reviewer: str | None = "user"
    reason: str | None = None


class GovernanceActionResponse(BaseModel):
    service: str = "kr_managed_instruction_service"
    contract_version: str = CONTRACT_VERSION
    action: str
    instruction: InstructionDetail
    superseded_instruction_id: str | None = None


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


def _knowledge_path() -> Path:
    """Return the canonical Managed-KR storage path.

    Path ownership belongs to ``ManagedStorage``.  The environment override is
    retained for isolated tests and controlled deployments, but the default is
    no longer dependent on the backend process working directory.
    """
    override = os.environ.get("WLV_KR_MANAGED_KNOWLEDGE_PATH")
    storage = ManagedStorage(
        path=Path(override).expanduser() if override else None,
    )
    return storage.path


def _load_document() -> dict[str, Any]:
    path = _knowledge_path()
    return json.loads(path.read_text())


def _save_document(data: dict[str, Any]) -> None:
    path = _knowledge_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def _load() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = _load_document()
    return data.get("records", []), data.get("evidence_records", [])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_instruction_record(record: dict[str, Any]) -> bool:
    return record.get("record_type") in TRUTH_RECORD_TYPES


def _truth(record: dict[str, Any]) -> bool:
    return (
        record.get("status") == "approved"
        and record.get("record_type") in TRUTH_RECORD_TYPES
        and record.get("runtime_eligible") is not False
        and record.get("production_eligible") is not False
    )


def _instruction_type(record_type: str, record: dict[str, Any] | None = None) -> str:
    if record and record.get("instruction_type"):
        return str(record.get("instruction_type"))
    if record_type == "managed_instruction":
        return "application_instruction"
    if record_type in {"curve_definition", "standard_mnemonic", "alias", "classification_rule", "display_rule"}:
        return "curve_instruction"
    if record_type in {"preview_template", "template_selection_rule"}:
        return "template_instruction"
    if record_type in {"preview_template_track", "track_object_type", "template_scale_default"}:
        return "track_instruction"
    if record_type == "template_curve_family_requirement":
        return "selection_instruction"
    return "application_instruction"


def _subject(record: dict[str, Any]) -> str:
    if record.get("instruction_subject"):
        return str(record.get("instruction_subject"))
    for key in ("template_label", "track_name", "display_name", "mnemonic", "alias", "curve_family", "family", "canonical_curve_id", "rule_id", "record_id"):
        value = record.get(key)
        if value:
            return str(value)
    return "unknown"


def _area(record: dict[str, Any]) -> str | None:
    if record.get("instruction_application_area"):
        return str(record.get("instruction_application_area"))
    parts: list[str] = []
    for key in ("product_group", "product_subgroup", "workflow_context", "template_key", "preferred_track_family"):
        value = record.get(key)
        if value and str(value) not in parts:
            parts.append(str(value))
    return " / ".join(parts) if parts else None


def _must_do(record: dict[str, Any]) -> str:
    if record.get("instruction_must_do"):
        return str(record.get("instruction_must_do"))
    rt = record.get("record_type")
    if rt == "curve_definition":
        return f"Treat {record.get('display_name') or record.get('canonical_curve_id')} as curve family {record.get('family') or 'unknown'}."
    if rt == "standard_mnemonic":
        return f"Resolve mnemonic {record.get('mnemonic')} to canonical curve {record.get('canonical_curve_id')}."
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
    if record.get("instruction_must_not_do"):
        return str(record.get("instruction_must_not_do"))
    rt = record.get("record_type")
    if rt in {"preview_template", "template_selection_rule", "template_curve_family_requirement"}:
        return "Do not use candidate, deprecated, or frontend-inferred rules for this decision."
    if rt in {"curve_definition", "standard_mnemonic", "alias", "classification_rule"}:
        return "Do not override this approved classification with unapproved candidate knowledge."
    return None


def _summary(record: dict[str, Any]) -> InstructionSummary:
    return InstructionSummary(
        instruction_id=str(record.get("record_id")),
        source_record_type=str(record.get("record_type")),
        instruction_type=_instruction_type(str(record.get("record_type")), record),
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
        mnemonic=record.get("mnemonic"),
        unit_hint=record.get("unit_hint") or record.get("default_unit"),
        description=(record.get("description_hint") or record.get("description")),
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
        instruction_type_counts=dict(Counter(_instruction_type(str(r.get("record_type")), r) for r in truth)),
        status_counts=dict(Counter(str(r.get("status")) for r in records)),
        runtime_eligible_count=sum(1 for r in truth if r.get("runtime_eligible") is not False),
        production_eligible_count=sum(1 for r in truth if r.get("production_eligible") is not False),
        evidence_record_count=len(evidence),
    )



_SEARCH_EXACT_FIELDS = (
    "mnemonic",
    "normalized_mnemonic",
    "alias",
    "canonical_curve_id",
    "record_id",
    "instruction_subject",
    "display_name",
    "curve_family",
    "family",
    "template_key",
    "track_id",
    "rule_id",
)

_SEARCH_PREFIX_FIELDS = (
    "mnemonic",
    "normalized_mnemonic",
    "alias",
    "canonical_curve_id",
    "instruction_subject",
    "display_name",
    "curve_family",
    "family",
    "template_key",
)

_SEARCH_TEXT_FIELDS = (
    "description",
    "description_hint",
    "instruction_must_do",
    "instruction_must_not_do",
    "instruction_application_area",
    "source_label",
    "source_reference",
    "notes",
    "change_reason",
)


def _search_value(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _search_score(record: dict[str, Any], query: str) -> int:
    """Return deterministic relevance score across the complete KR record."""
    q = query.strip().lower()
    if not q:
        return 0

    score = 0
    for key in _SEARCH_EXACT_FIELDS:
        value = _search_value(record, key).strip().lower()
        if not value:
            continue
        if value == q:
            score = max(score, 1000)
        elif value.startswith(q):
            score = max(score, 800)
        elif q in value:
            score = max(score, 600)

    for key in _SEARCH_PREFIX_FIELDS:
        value = _search_value(record, key).strip().lower()
        if value.startswith(q):
            score = max(score, 750)
        elif q in value:
            score = max(score, 500)

    for key in _SEARCH_TEXT_FIELDS:
        value = _search_value(record, key).lower()
        if q in value:
            score = max(score, 250)

    serialized = json.dumps(record, sort_keys=True, default=str).lower()
    if q in serialized:
        score = max(score, 100)

    # Prefer approved runtime truth when textual relevance is otherwise equal.
    if score and record.get("status") == "approved":
        score += 10
    if score and record.get("runtime_eligible") is not False:
        score += 5
    return score


def _record_visible_for_browse(record: dict[str, Any], approved_only: bool, status: str | None) -> bool:
    if approved_only:
        return _truth(record)
    if not _is_instruction_record(record):
        return False
    rec_status = str(record.get("status"))
    if status and rec_status != status:
        return False
    return True


def _record_visible_for_search(record: dict[str, Any], approved_only: bool, status: str | None) -> bool:
    """Search the complete managed catalogue, then honor explicit status filters.

    Search is intentionally broader than browse. Records are not discarded merely
    because their record type is outside the default instruction browse subset.
    """
    rec_status = str(record.get("status") or "")
    if status and rec_status != status:
        return False
    if approved_only and rec_status and rec_status != "approved":
        return False
    return True


@router.get("", response_model=InstructionListResponse)
def list_instructions(
    q: str | None = None,
    instruction_type: str | None = None,
    record_type: str | None = None,
    template_key: str | None = None,
    curve_family: str | None = None,
    status: str | None = None,
    approved_only: bool = True,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> InstructionListResponse:
    records, _ = _load()
    query = (q or "").strip().lower()
    ranked: list[tuple[int, InstructionSummary]] = []
    candidate_used = False
    deprecated_used = False

    for record in records:
        visible = (
            _record_visible_for_search(record, approved_only, status)
            if query
            else _record_visible_for_browse(record, approved_only, status)
        )
        if not visible:
            continue

        item = _summary(record)
        if instruction_type and item.instruction_type != instruction_type:
            continue
        if record_type:
            if record_type == "mnemonic_mapping":
                if item.source_record_type not in {"alias", "standard_mnemonic"}:
                    continue
            elif item.source_record_type != record_type:
                continue
        if template_key and item.template_key != template_key:
            continue
        if curve_family and (item.curve_family or "").lower() != curve_family.lower():
            continue

        score = _search_score(record, query) if query else 0
        if query and score <= 0:
            continue

        rec_status = str(record.get("status") or "")
        if rec_status and rec_status != "approved":
            candidate_used = True
        if rec_status in {"deprecated", "superseded"}:
            deprecated_used = True
        ranked.append((score, item))

    if query:
        ranked.sort(
            key=lambda pair: (
                -pair[0],
                pair[1].subject.lower(),
                pair[1].source_record_type,
                pair[1].instruction_id,
            )
        )
    else:
        ranked.sort(
            key=lambda pair: (
                pair[1].status,
                pair[1].instruction_type,
                pair[1].template_key or "",
                pair[1].subject,
                pair[1].instruction_id,
            )
        )

    total = len(ranked)
    page = [item for _, item in ranked[offset : offset + limit]]
    return InstructionListResponse(
        approved_only=approved_only,
        candidate_records_used=candidate_used,
        deprecated_records_used=deprecated_used,
        total_count=total,
        returned_count=len(page),
        offset=offset,
        limit=limit,
        has_previous=offset > 0,
        has_next=offset + len(page) < total,
        search_ranked=bool(query),
        instructions=page,
    )




def _manual_instruction_record(payload: CandidateInstructionCreateRequest, record_id: str | None = None, status: str = "candidate") -> dict[str, Any]:
    now = _now()
    rid = record_id or f"manual_kr_instruction_{uuid4().hex}"
    return {
        "record_id": rid,
        "record_type": "managed_instruction",
        "status": status,
        "version": 1,
        "instruction_type": payload.instruction_type,
        "instruction_subject": payload.subject,
        "instruction_application_area": payload.application_area,
        "template_key": payload.template_key,
        "track_id": payload.track_id,
        "curve_family": payload.curve_family,
        "canonical_curve_id": payload.canonical_curve_id,
        "alias": payload.alias,
        "instruction_must_do": payload.must_do,
        "instruction_must_not_do": payload.must_not_do,
        "instruction_allowed_use": payload.allowed_use,
        "instruction_priority": payload.priority,
        "supersedes_record_id": payload.supersedes_record_id,
        "runtime_eligible": False,
        "production_eligible": False,
        "created_at": now,
        "updated_at": now,
        "created_by": payload.reviewer or "user",
        "reviewed_by": None,
        "approved_by": None,
        "change_reason": payload.change_reason or "User-created candidate KR instruction.",
        "evidence_refs": [],
        "governance_history": [
            {"at": now, "by": payload.reviewer or "user", "action": "created_candidate", "reason": payload.change_reason or "User-created candidate KR instruction."}
        ],
    }


def _append_evidence(data: dict[str, Any], record: dict[str, Any], note: str | None, reviewer: str | None) -> None:
    if not note:
        return
    evidence_id = f"manual_evidence_{uuid4().hex}"
    evidence = {
        "evidence_id": evidence_id,
        "source_type": "manual_user_note",
        "source_label": "User-entered KR evidence",
        "source_reference": None,
        "confidence": 1.0,
        "notes": note,
        "created_at": _now(),
        "created_by": reviewer or "user",
    }
    data.setdefault("evidence_records", []).append(evidence)
    record.setdefault("evidence_refs", []).append(evidence_id)


def _detail_for_record(record: dict[str, Any], evidence_records: list[dict[str, Any]]) -> InstructionDetail:
    evidence_by_id = _evidence_index(evidence_records)
    evidence = [_evidence_ref(evidence_by_id[eid]) for eid in record.get("evidence_refs") or [] if eid in evidence_by_id]
    return InstructionDetail(**_summary(record).model_dump(), evidence=evidence, raw_record=record)


def _find_record(records: list[dict[str, Any]], record_id: str) -> dict[str, Any] | None:
    return next((r for r in records if r.get("record_id") == record_id), None)


@router.post("/candidates", response_model=GovernanceActionResponse)
def create_candidate_instruction(payload: CandidateInstructionCreateRequest) -> GovernanceActionResponse:
    data = _load_document()
    record = _manual_instruction_record(payload)
    _append_evidence(data, record, payload.evidence_note, payload.reviewer)
    data.setdefault("records", []).append(record)
    _save_document(data)
    return GovernanceActionResponse(action="created_candidate", instruction=_detail_for_record(record, data.get("evidence_records", [])))


@router.put("/candidates/{instruction_id}", response_model=GovernanceActionResponse)
def update_candidate_instruction(instruction_id: str, payload: CandidateInstructionUpdateRequest) -> GovernanceActionResponse:
    data = _load_document()
    records = data.setdefault("records", [])
    record = _find_record(records, instruction_id)
    if record is None or record.get("status") != "candidate" or record.get("record_type") != "managed_instruction":
        raise HTTPException(status_code=404, detail="Editable candidate instruction not found")
    field_map = {
        "instruction_type": "instruction_type",
        "subject": "instruction_subject",
        "application_area": "instruction_application_area",
        "template_key": "template_key",
        "track_id": "track_id",
        "curve_family": "curve_family",
        "canonical_curve_id": "canonical_curve_id",
        "alias": "alias",
        "must_do": "instruction_must_do",
        "must_not_do": "instruction_must_not_do",
        "allowed_use": "instruction_allowed_use",
        "priority": "instruction_priority",
        "supersedes_record_id": "supersedes_record_id",
    }
    for source, target in field_map.items():
        value = getattr(payload, source)
        if value is not None:
            record[target] = value
    _append_evidence(data, record, payload.evidence_note, payload.reviewer)
    now = _now()
    record["updated_at"] = now
    record["change_reason"] = payload.change_reason or record.get("change_reason") or "User-updated candidate KR instruction."
    record.setdefault("governance_history", []).append({"at": now, "by": payload.reviewer or "user", "action": "updated_candidate", "reason": payload.change_reason or "User-updated candidate KR instruction."})
    _save_document(data)
    return GovernanceActionResponse(action="updated_candidate", instruction=_detail_for_record(record, data.get("evidence_records", [])))


@router.post("/candidates/{instruction_id}/approve", response_model=GovernanceActionResponse)
def approve_candidate_instruction(instruction_id: str, payload: GovernanceActionRequest) -> GovernanceActionResponse:
    data = _load_document()
    records = data.setdefault("records", [])
    record = _find_record(records, instruction_id)
    if record is None or record.get("status") != "candidate" or record.get("record_type") != "managed_instruction":
        raise HTTPException(status_code=404, detail="Candidate instruction not found")
    now = _now()
    superseded_id = record.get("supersedes_record_id")
    if superseded_id:
        superseded = _find_record(records, str(superseded_id))
        if superseded is not None and superseded.get("status") == "approved":
            superseded["status"] = "superseded"
            superseded["runtime_eligible"] = False
            superseded["production_eligible"] = False
            superseded["updated_at"] = now
            superseded.setdefault("governance_history", []).append({"at": now, "by": payload.reviewer or "user", "action": "superseded", "reason": payload.reason or f"Superseded by {instruction_id}"})
    record["status"] = "approved"
    record["runtime_eligible"] = True
    record["production_eligible"] = True
    record["reviewed_by"] = payload.reviewer or "user"
    record["approved_by"] = payload.reviewer or "user"
    record["reviewed_at"] = now
    record["approved_at"] = now
    record["updated_at"] = now
    record["change_reason"] = payload.reason or "User approved candidate KR instruction."
    record.setdefault("governance_history", []).append({"at": now, "by": payload.reviewer or "user", "action": "approved_candidate", "reason": payload.reason or "User approved candidate KR instruction."})
    _save_document(data)
    return GovernanceActionResponse(action="approved_candidate", instruction=_detail_for_record(record, data.get("evidence_records", [])), superseded_instruction_id=superseded_id)


@router.post("/candidates/{instruction_id}/reject", response_model=GovernanceActionResponse)
def reject_candidate_instruction(instruction_id: str, payload: GovernanceActionRequest) -> GovernanceActionResponse:
    data = _load_document()
    record = _find_record(data.setdefault("records", []), instruction_id)
    if record is None or record.get("status") != "candidate":
        raise HTTPException(status_code=404, detail="Candidate instruction not found")
    now = _now()
    record["status"] = "rejected"
    record["runtime_eligible"] = False
    record["production_eligible"] = False
    record["reviewed_by"] = payload.reviewer or "user"
    record["reviewed_at"] = now
    record["updated_at"] = now
    record["change_reason"] = payload.reason or "User rejected candidate KR instruction."
    record.setdefault("governance_history", []).append({"at": now, "by": payload.reviewer or "user", "action": "rejected_candidate", "reason": payload.reason or "User rejected candidate KR instruction."})
    _save_document(data)
    return GovernanceActionResponse(action="rejected_candidate", instruction=_detail_for_record(record, data.get("evidence_records", [])))


@router.post("/{instruction_id}/deprecate", response_model=GovernanceActionResponse)
def deprecate_instruction(instruction_id: str, payload: GovernanceActionRequest) -> GovernanceActionResponse:
    data = _load_document()
    record = _find_record(data.setdefault("records", []), instruction_id)
    if record is None or record.get("status") != "approved" or not _is_instruction_record(record):
        raise HTTPException(status_code=404, detail="Approved instruction not found")
    now = _now()
    record["status"] = "deprecated"
    record["runtime_eligible"] = False
    record["production_eligible"] = False
    record["deprecated_at"] = now
    record["updated_at"] = now
    record["change_reason"] = payload.reason or "User deprecated approved KR instruction."
    record.setdefault("governance_history", []).append({"at": now, "by": payload.reviewer or "user", "action": "deprecated", "reason": payload.reason or "User deprecated approved KR instruction."})
    _save_document(data)
    return GovernanceActionResponse(action="deprecated", instruction=_detail_for_record(record, data.get("evidence_records", [])))


@router.get("/templates/{template_key}/decision", response_model=TemplateDecisionResponse)
def template_decision(template_key: str) -> TemplateDecisionResponse:
    records, evidence_records = _load()
    truth = [r for r in records if _truth(r)]
    template_records = [r for r in truth if r.get("template_key") == template_key]
    template_items = [_summary(r) for r in template_records if _instruction_type(str(r.get("record_type")), r) == "template_instruction"]
    track_items = [_summary(r) for r in template_records if _instruction_type(str(r.get("record_type")), r) == "track_instruction"]
    selection_items = [_summary(r) for r in template_records if _instruction_type(str(r.get("record_type")), r) == "selection_instruction"]
    families = {item.curve_family for item in selection_items if item.curve_family}
    curve_items = [
        _summary(r) for r in truth
        if _instruction_type(str(r.get("record_type")), r) == "curve_instruction"
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
    record = next((r for r in records if r.get("record_id") == instruction_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="KR instruction not found")
    evidence_by_id = _evidence_index(evidence_records)
    evidence = [_evidence_ref(evidence_by_id[eid]) for eid in record.get("evidence_refs") or [] if eid in evidence_by_id]
    detail = InstructionDetail(**_summary(record).model_dump(), evidence=evidence, raw_record=record)
    return InstructionDetailResponse(instruction=detail)
