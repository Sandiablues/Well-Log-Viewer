from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, UploadFile
from .models import ExtractionHealth, ExtractionJobStatus, ExtractionSubmission, ParsedDocument, ParsedDocumentSummary
from .service import ExtractionService
PROJECT_ROOT=Path(__file__).resolve().parents[3]
service=ExtractionService(PROJECT_ROOT)
router=APIRouter(prefix="/api/wme/extraction",tags=["wme-extraction"])
@router.get("/status",response_model=ExtractionHealth)
def extraction_status():
    available,detail=service.health(); return ExtractionHealth(available=available,ready=available,state="ready" if available else "unavailable",detail=detail)
@router.post("/documents",response_model=ExtractionSubmission)
async def submit_document(file: UploadFile=File(...)):
    if not file.filename: raise HTTPException(400,"Document filename is required")
    if not file.filename.lower().endswith(".pdf"): raise HTTPException(400,"Only PDF documents are supported")
    available,detail=service.health()
    if not available: raise HTTPException(503,detail or "Document extraction is unavailable")
    status=service.submit(service.save_upload(file.filename,await file.read())); return ExtractionSubmission(job_id=status.job_id,document_id=status.document_id,source_name=status.source_name,state=status.state,cached=status.cached)
@router.get("/jobs/{job_id}",response_model=ExtractionJobStatus)
def job_status(job_id: str):
    status=service.status(job_id)
    if not status: raise HTTPException(404,"Extraction job not found")
    return status
@router.get("/jobs/{job_id}/result",response_model=ParsedDocumentSummary)
def job_result(job_id: str):
    status=service.status(job_id)
    if not status: raise HTTPException(404,"Extraction job not found")
    if status.state=="failed": raise HTTPException(500,status.error or "Extraction failed")
    if status.state!="completed": raise HTTPException(409,"Extraction has not completed")
    result=service.result(job_id)
    if not result: raise HTTPException(500,"Extraction result is unavailable")
    return result

@router.get("/jobs/{job_id}/document",response_model=ParsedDocument)
def job_document(job_id: str):
    status=service.status(job_id)
    if not status: raise HTTPException(404,"Extraction job not found")
    if status.state=="failed": raise HTTPException(500,status.error or "Extraction failed")
    if status.state!="completed": raise HTTPException(409,"Extraction has not completed")
    document=service.document(job_id)
    if not document: raise HTTPException(500,"Structured document is unavailable")
    return document

@router.delete("/session",status_code=204)
def clear_session(): service.clear()
