from __future__ import annotations

from typing import Optional, Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.services.knowledge_repository_service import (
    approve_knowledge_candidate,
    export_knowledge_terms,
    get_categories,
    import_knowledge_records,
    init_knowledge_db,
    list_knowledge_candidates,
    list_knowledge_terms,
    parse_json_or_csv_bytes,
    reject_knowledge_candidate,
    upsert_knowledge_candidate,
    upsert_knowledge_term,
    update_knowledge_term_by_id,
)


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class KnowledgeTermIn(BaseModel):
    term: str
    definition: str = ""
    category: str = "uncategorized"
    knowledge_domain: str = ""
    knowledge_subtype: str = ""
    aliases: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)
    source: str = "manual"
    authority: str = "reference"
    active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)





class KnowledgeTermUpdateIn(BaseModel):
    term: str
    definition: str = ""
    category: str = "uncategorized"
    knowledge_domain: str = ""
    knowledge_subtype: str = ""
    aliases: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)
    source: str = "manual"
    authority: str = "reference"
    active: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeCandidateIn(BaseModel):
    candidate_type: str
    candidate_value: str
    suggested_canonical_term: str = ""
    category: str = "uncategorized"
    source_type: str = "usage_observation"
    source_reference: str = ""
    evidence_count: int = 1
    confidence: str = "low"
    review_status: str = "candidate"
    notes: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeCandidateDecisionIn(BaseModel):
    notes: str = ""
    promote: bool = True


@router.get("/health")
def api_knowledge_health():
    return init_knowledge_db()


@router.get("/terms")
def api_list_knowledge_terms(
    query: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    knowledge_domain: Optional[str] = Query(default=None),
    knowledge_subtype: Optional[str] = Query(default=None),
    active: Optional[bool] = Query(default=True),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    return list_knowledge_terms(
        query=query,
        category=category,
        knowledge_domain=knowledge_domain,
        knowledge_subtype=knowledge_subtype,
        active=active,
        limit=limit,
        offset=offset,
    )


@router.post("/terms")
def api_upsert_knowledge_term(term: KnowledgeTermIn):
    try:
        return upsert_knowledge_term(term.dict())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))



@router.put("/terms/{term_id}")
def api_update_knowledge_term(term_id: str, term: KnowledgeTermUpdateIn):
    try:
        return update_knowledge_term_by_id(term_id, term.dict())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/import")
async def api_import_knowledge_terms(
    file: UploadFile = File(...),
    source: str = Query(default="upload"),
):
    try:
        data = await file.read()
        records = parse_json_or_csv_bytes(data, filename=file.filename or "")
        return import_knowledge_records(
            records,
            filename=file.filename or "",
            source=source,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/categories")
def api_knowledge_categories():
    return get_categories()


@router.get("/export")
def api_export_knowledge_terms():
    return export_knowledge_terms()



@router.get("/candidates")
def api_list_knowledge_candidates(
    candidate_type: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    review_status: Optional[str] = Query(default="candidate"),
    query: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    return list_knowledge_candidates(
        candidate_type=candidate_type,
        category=category,
        review_status=review_status,
        query=query,
        limit=limit,
        offset=offset,
    )


@router.post("/candidates")
def api_upsert_knowledge_candidate(candidate: KnowledgeCandidateIn):
    try:
        return upsert_knowledge_candidate(candidate.dict())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/candidates/{candidate_id}/approve")
def api_approve_knowledge_candidate(candidate_id: str, decision: KnowledgeCandidateDecisionIn = KnowledgeCandidateDecisionIn()):
    try:
        return approve_knowledge_candidate(
            candidate_id,
            promote=decision.promote,
            notes=decision.notes,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/candidates/{candidate_id}/reject")
def api_reject_knowledge_candidate(candidate_id: str, decision: KnowledgeCandidateDecisionIn = KnowledgeCandidateDecisionIn()):
    try:
        return reject_knowledge_candidate(candidate_id, notes=decision.notes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

