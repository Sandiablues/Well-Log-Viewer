from __future__ import annotations

from typing import Literal

import base64
import binascii
import io
import mimetypes
import posixpath
import zipfile
from pathlib import Path

import threading
import time
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .repository import ToolboxAiRevisionRepository, VALID_TOOLS
from .standards_repository import ToolboxAiStandardsRepository
from .qualification_provider import PROVIDERS, provider_status, run_qualification
from .qualification_evidence import EvidencePreparationError, prepare_evidence

router = APIRouter(prefix="/api/toolbox/ai-revisions", tags=["toolbox-ai-revisions"])
repository = ToolboxAiRevisionRepository()
standards_repository = ToolboxAiStandardsRepository()

_qualification_jobs: dict[str, dict] = {}
_qualification_jobs_lock = threading.Lock()

ToolName = Literal["WME", "FTM", "CDM", "LCM", "DSM", "CIM_JOIN", "CIM_AIQC"]


class StreamMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: ToolName
    authority_key: str = Field(min_length=1)
    well_name: str | None = None
    managed_well_id: str | None = None
    actor: str | None = "frontend"
    reason: str | None = None
    artifact_name: str | None = None


class SyncMutation(StreamMutation):
    revision: int = Field(ge=0)


class CorrectionMutation(StreamMutation):
    revision: int = Field(ge=0)
    reason: str = Field(min_length=1)


@router.get("")
def list_streams() -> dict:
    return {"schema_version": "toolbox_ai_revision_registry_v1", "streams": repository.list_streams()}


@router.get("/stream")
def get_stream(tool: ToolName = Query(...), authority_key: str = Query(..., min_length=1)) -> dict:
    stream = repository.get(tool, authority_key)
    if stream is None:
        return {
            "tool": tool,
            "authority_key": authority_key,
            "current_revision": 0,
            "history": [],
        }
    return stream


@router.post("/allocate")
def allocate(request: StreamMutation) -> dict:
    try:
        return repository.allocate(
            request.tool,
            request.authority_key,
            reason=request.reason,
            artifact_name=request.artifact_name,
            actor=request.actor,
            well_name=request.well_name,
            managed_well_id=request.managed_well_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/synchronize")
def synchronize(request: SyncMutation) -> dict:
    try:
        return repository.synchronize(
            request.tool,
            request.authority_key,
            request.revision,
            reason=request.reason,
            artifact_name=request.artifact_name,
            actor=request.actor,
            well_name=request.well_name,
            managed_well_id=request.managed_well_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/correct")
def correct(request: CorrectionMutation) -> dict:
    try:
        return repository.correct(
            request.tool,
            request.authority_key,
            request.revision,
            reason=request.reason,
            actor=request.actor,
            well_name=request.well_name,
            managed_well_id=request.managed_well_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class StandardVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules: dict
    created_by: str | None = "operator"
    change_note: str | None = ""


class StandardRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_version: int = Field(ge=1)
    created_by: str | None = "operator"
    change_note: str | None = ""


@router.get("/standards")
def list_ai_standards() -> dict:
    return {"schema_version": "toolbox_ai_standards_v1", "tools": standards_repository.list()}


@router.get("/standards/{tool}")
def get_active_ai_standard(tool: ToolName) -> dict:
    try:
        return standards_repository.get_active(tool)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/standards/{tool}/versions/{version}")
def get_ai_standard_version(tool: ToolName, version: int) -> dict:
    try:
        return standards_repository.get_version(tool, version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/standards/{tool}/versions")
def create_ai_standard_version(tool: ToolName, request: StandardVersionCreate) -> dict:
    try:
        return standards_repository.save_new_version(
            tool,
            request.rules,
            created_by=request.created_by,
            change_note=request.change_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/standards/{tool}/restore")
def restore_ai_standard_version(tool: ToolName, request: StandardRestore) -> dict:
    try:
        return standards_repository.restore_as_new_version(
            tool,
            request.source_version,
            created_by=request.created_by,
            change_note=request.change_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

class QualificationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_package: dict
    answer_key: dict
    evidence_files: list[dict] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=lambda: list(PROVIDERS))
    judges: list[str] = Field(default_factory=lambda: list(PROVIDERS))


@router.get("/qualification/providers")
def get_qualification_provider_status() -> dict:
    return {
        "schema_version": "multiviewer_ai_provider_status_v0_1",
        "providers": provider_status(),
    }


# Standard paid API rates in USD per 1M text tokens.
# These are deliberately isolated here so the estimator is easy to update.
_CANDIDATE_RATE_CARDS = {
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20, "max_output_tokens": None},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00, "max_output_tokens": 64000},
    "gemini-3.6-flash": {"input": 0.75, "output": 3.75, "max_output_tokens": None},
}

_OUTPUT_PROJECTION_LEVELS = (4000, 8000, 16000, 32000, 64000)

class QualificationEstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_package: dict
    evidence_files: list[dict] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=lambda: list(PROVIDERS))



class QualificationPrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_package: dict
    evidence_files: list[dict] = Field(default_factory=list)


class ZipExpandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archive_name: str = Field(min_length=1)
    content_base64: str = Field(min_length=1)


_ZIP_ALLOWED_EXTENSIONS = {
    ".pdf", ".csv", ".xlsx", ".xls", ".txt", ".json",
    ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif",
}
_ZIP_MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
_ZIP_MAX_MEMBER_COUNT = 250
_ZIP_MAX_MEMBER_BYTES = 128 * 1024 * 1024
_ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


def _safe_zip_member_name(raw_name: str) -> str:
    normalized = posixpath.normpath(str(raw_name or "").replace("\\", "/")).lstrip("/")
    if not normalized or normalized in {".", ".."}:
        raise ValueError("empty ZIP member path")
    if normalized.startswith("../") or "/../" in f"/{normalized}":
        raise ValueError(f"unsafe ZIP member path: {raw_name!r}")
    return normalized


@router.post("/qualification/expand-zip")
def expand_ai_qualification_zip(request: ZipExpandRequest) -> dict:
    try:
        compressed = base64.b64decode(request.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="ZIP payload is not valid base64.") from exc

    if len(compressed) > _ZIP_MAX_ARCHIVE_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"ZIP archive exceeds {_ZIP_MAX_ARCHIVE_BYTES // (1024 * 1024)} MiB compressed limit.",
        )

    try:
        archive = zipfile.ZipFile(io.BytesIO(compressed))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=422, detail="Supporting-file archive is not a valid ZIP file.") from exc

    members = [info for info in archive.infolist() if not info.is_dir()]
    if len(members) > _ZIP_MAX_MEMBER_COUNT:
        raise HTTPException(
            status_code=422,
            detail=f"ZIP contains {len(members)} files; maximum is {_ZIP_MAX_MEMBER_COUNT}.",
        )

    total_uncompressed = sum(max(0, int(info.file_size)) for info in members)
    if total_uncompressed > _ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"ZIP expands to more than "
                f"{_ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES // (1024 * 1024)} MiB."
            ),
        )

    expanded: list[dict] = []
    skipped: list[dict] = []

    for info in members:
        try:
            member_name = _safe_zip_member_name(info.filename)
        except ValueError as exc:
            skipped.append({"member": str(info.filename), "reason": str(exc)})
            continue

        leaf = posixpath.basename(member_name)
        if leaf.startswith(".") or member_name.startswith("__MACOSX/"):
            # macOS ZIP metadata/resource-fork entries are implementation noise.
            # Ignore them silently: they are not source evidence and must not
            # appear in skipped-file counts, provenance, or operator review.
            continue

        extension = Path(member_name).suffix.lower()
        if extension == ".zip":
            skipped.append({"member": member_name, "reason": "nested ZIP archives are not expanded"})
            continue
        if extension not in _ZIP_ALLOWED_EXTENSIONS:
            skipped.append({"member": member_name, "reason": f"unsupported file type {extension or '(none)'}"})
            continue
        if info.flag_bits & 0x1:
            skipped.append({"member": member_name, "reason": "encrypted ZIP member"})
            continue
        if int(info.file_size) > _ZIP_MAX_MEMBER_BYTES:
            skipped.append({
                "member": member_name,
                "reason": f"member exceeds {_ZIP_MAX_MEMBER_BYTES // (1024 * 1024)} MiB limit",
            })
            continue

        try:
            data = archive.read(info)
        except (RuntimeError, zipfile.BadZipFile) as exc:
            skipped.append({"member": member_name, "reason": f"could not read member: {exc}"})
            continue

        mime_type = mimetypes.guess_type(member_name)[0] or "application/octet-stream"
        expanded.append({
            "archive_name": request.archive_name,
            "member_name": member_name,
            "source_name": f"{request.archive_name}::{member_name}",
            "type": mime_type,
            "size": len(data),
            "content_base64": base64.b64encode(data).decode("ascii"),
        })

    if not expanded:
        raise HTTPException(
            status_code=422,
            detail="ZIP contains no supported, readable CDM supporting files.",
        )

    return {
        "schema_version": "multiviewer_ai_zip_expansion_v0_1",
        "archive_name": request.archive_name,
        "member_count": len(members),
        "expanded_count": len(expanded),
        "skipped_count": len(skipped),
        "expanded_files": expanded,
        "skipped_files": skipped,
        "policy": {
            "nested_zip": "reported_not_expanded",
            "path_handling": "in_memory_only_no_filesystem_extraction",
            "source_naming": "archive.zip::member/path.ext",
        },
    }


@router.post("/qualification/prepare")
def prepare_ai_qualification_evidence(request: QualificationPrepareRequest) -> dict:
    try:
        deterministic_enabled = bool(request.candidate_package.get("deterministic_screening_enabled", True))
        deterministic_profile = request.candidate_package.get("deterministic_screening_profile")
        prepared, summaries = prepare_evidence(
            request.evidence_files,
            deterministic_enabled=deterministic_enabled,
            deterministic_profile=deterministic_profile if isinstance(deterministic_profile, dict) else {},
        )
    except EvidencePreparationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "schema_version": "multiviewer_ai_evidence_preparation_v0_2",
        "deterministic_screening_enabled": deterministic_enabled,
        "evidence_preparation": summaries,
        "prepared_evidence": prepared,
        "estimated_evidence_tokens": sum(int(item.get("estimated_tokens") or 0) for item in summaries),
    }


@router.post("/qualification/estimate")
def estimate_ai_qualification(request: QualificationEstimateRequest) -> dict:
    requested = [item for item in request.providers if item in PROVIDERS]
    if not requested:
        raise HTTPException(status_code=422, detail="Select at least one configured candidate provider.")

    try:
        deterministic_enabled = bool(request.candidate_package.get("deterministic_screening_enabled", True))
        deterministic_profile = request.candidate_package.get("deterministic_screening_profile")
        _prepared, summaries = prepare_evidence(
            request.evidence_files,
            deterministic_enabled=deterministic_enabled,
            deterministic_profile=deterministic_profile if isinstance(deterministic_profile, dict) else {},
        )
    except EvidencePreparationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    evidence_tokens = sum(int(item.get("estimated_tokens") or 0) for item in summaries)

    # AI standard + task + schema/prompt overhead. This is intentionally a transparent
    # estimate rather than pretending to be provider-exact tokenization.
    import json as _json
    package_tokens = max(1, round(len(_json.dumps(request.candidate_package, ensure_ascii=False)) / 4))
    prompt_overhead_tokens = 1200
    estimated_input_tokens = evidence_tokens + package_tokens + prompt_overhead_tokens

    status = provider_status()
    rows = []
    low_total = 0.0
    high_total = 0.0

    # Quantify the same input payload recursively across progressively larger
    # output sizes. These are projections, not execution caps.
    projection_totals = {tokens: 0.0 for tokens in _OUTPUT_PROJECTION_LEVELS}
    projection_totals_if_gemini_free = {tokens: 0.0 for tokens in _OUTPUT_PROJECTION_LEVELS}

    for provider in requested:
        info = status.get(provider, {})
        model = str(info.get("candidate_model") or info.get("model") or "")
        rates = _CANDIDATE_RATE_CARDS.get(model)
        if rates is None:
            rows.append({
                "provider": provider,
                "label": info.get("label", provider),
                "model": model,
                "estimated_input_tokens": estimated_input_tokens,
                "cost_low_usd": None,
                "cost_high_usd": None,
                "cost_projections": [],
                "note": "No local rate card for this model.",
            })
            continue

        input_cost = (estimated_input_tokens / 1_000_000) * rates["input"]
        projections = []
        for output_tokens in _OUTPUT_PROJECTION_LEVELS:
            cost = input_cost + (output_tokens / 1_000_000) * rates["output"]
            projections.append({
                "output_tokens": output_tokens,
                "cost_usd": round(cost, 6),
            })
            projection_totals[output_tokens] += cost
            if provider == "gemini":
                # If the request is actually served under an eligible Gemini Free tier,
                # billed token cost is $0. Keep paid-equivalent exposure visible separately.
                projection_totals_if_gemini_free[output_tokens] += 0.0
            else:
                projection_totals_if_gemini_free[output_tokens] += cost

        expected_low = projections[1]["cost_usd"]  # 8k output
        expected_high = projections[2]["cost_usd"]  # 16k output
        rows.append({
            "provider": provider,
            "label": info.get("label", provider),
            "model": model,
            "estimated_input_tokens": estimated_input_tokens,
            "execution_output_policy": "provider_maximum",
            "known_max_output_tokens": rates.get("max_output_tokens"),
            "cost_low_usd": expected_low,
            "cost_high_usd": expected_high,
            "cost_projections": projections,
            "gemini_free_tier_possible": provider == "gemini",
            "gemini_free_tier_billed_cost_usd": 0.0 if provider == "gemini" else None,
        })

    total_projections = [
        {
            "output_tokens_per_model": output_tokens,
            "paid_equivalent_total_usd": round(projection_totals[output_tokens], 6),
            "total_if_gemini_free_usd": round(projection_totals_if_gemini_free[output_tokens], 6),
        }
        for output_tokens in _OUTPUT_PROJECTION_LEVELS
    ]
    low_total = projection_totals[8000]
    high_total = projection_totals[16000]

    return {
        "schema_version": "multiviewer_ai_qualification_estimate_v0_1",
        "evidence_preparation": summaries,
        "estimated_evidence_tokens": evidence_tokens,
        "estimated_package_tokens": package_tokens,
        "estimated_input_tokens_per_candidate": estimated_input_tokens,
        "providers": rows,
        "estimated_total_low_usd": round(low_total, 6),
        "estimated_total_high_usd": round(high_total, 6),
        "total_cost_projections": total_projections,
        "execution_output_policy": "provider_maximum",
        "judges_included": False,
        "note": (
            "Estimate only. Execution no longer uses MultiViewer's old 4k output cap. "
            "OpenAI is uncapped locally, Claude Haiku 4.5 uses its 64k technical maximum, "
            "and Gemini uses its model-reported outputTokenLimit when available."
        ),
    }


@router.post("/qualification/run")
def run_ai_qualification(request: QualificationRunRequest) -> dict:
    requested_providers = [item for item in request.providers if item in PROVIDERS]
    requested_judges = [item for item in request.judges if item in PROVIDERS]
    if not requested_providers:
        raise HTTPException(status_code=422, detail="Select at least one configured candidate provider.")
    return run_qualification(
        request.candidate_package,
        request.answer_key,
        requested_providers,
        requested_judges,
        evidence_files=request.evidence_files,
    )

def _qualification_event_message(event: str, payload: dict) -> str:
    provider_labels = {
        "openai": "OpenAI",
        "anthropic": "Claude",
        "gemini": "Gemini",
    }
    provider = str(payload.get("provider") or "")
    label = provider_labels.get(provider, provider or "Provider")

    if event == "run_started":
        judges = int(payload.get("judge_count", 0) or 0)
        if judges:
            return (
                f"Discovery started — {payload.get('provider_count', 0)} candidate models, "
                f"{judges} optional judges, {payload.get('evidence_count', 0)} evidence files."
            )
        return (
            f"Discovery started — {payload.get('provider_count', 0)} candidate models, "
            f"{payload.get('evidence_count', 0)} evidence files. No automatic judges."
        )
    if event == "evidence_prepared":
        name = str(payload.get("name") or "Evidence")
        original_mib = float(payload.get("original_size") or 0) / (1024 * 1024)
        total_pages = payload.get("total_pages")
        selected_pages = payload.get("selected_page_count")
        tokens = int(payload.get("estimated_tokens") or 0)
        if payload.get("mode") == "deterministic_pdf_text":
            return (
                f"Deterministic screening: {name} {original_mib:.1f} MB / {total_pages} pages "
                f"→ {selected_pages} selected pages → ~{tokens:,} estimated tokens."
            )
        if payload.get("mode") == "full_pdf_text":
            return (
                f"Direct evidence path: {name} {original_mib:.1f} MB / {total_pages} pages "
                f"→ all {selected_pages} text pages → ~{tokens:,} estimated tokens."
            )
        return f"Evidence prepared: {name} → ~{tokens:,} estimated tokens."
    if event == "evidence_preparation_failed":
        return f"Evidence preprocessing stopped the run: {payload.get('message', 'Unknown error')}"
    if event == "timeout_selected":
        seconds = int(payload.get("timeout_seconds") or 0)
        stage = str(payload.get("stage") or "provider").capitalize()
        return f"{stage} timeout set to {seconds} seconds based on evidence size."
    if event == "candidate_started":
        return f"Candidate {payload.get('index')}/{payload.get('total')}: {label} started."
    if event == "candidate_completed":
        finding_count = int(payload.get("finding_count") or 0)
        unresolved_count = int(payload.get("unresolved_evidence_count") or 0)
        conflict_count = int(payload.get("conflict_count") or 0)
        suffix = (
            f", {unresolved_count} unresolved, {conflict_count} conflicts"
            if unresolved_count or conflict_count
            else ""
        )
        if bool(payload.get("review_required")) or finding_count == 0:
            return (
                f"Candidate {payload.get('index')}/{payload.get('total')}: {label} completed "
                f"({finding_count} findings{suffix}) — Review required."
            )
        return (
            f"Candidate {payload.get('index')}/{payload.get('total')}: {label} completed "
            f"({finding_count} findings{suffix})."
        )
    if event == "candidate_failed":
        return f"Candidate {label} failed: {payload.get('message', 'Unknown provider error')}"
    if event == "judge_stage_started":
        return (
            f"Candidate stage complete. Starting {payload.get('judge_count', 0)} blinded judges "
            f"against {payload.get('candidate_count', 0)} candidate results."
        )
    if event == "judge_started":
        return f"Judge {payload.get('index')}/{payload.get('total')}: {label} started blinded review."
    if event == "judge_completed":
        return (
            f"Judge {payload.get('index')}/{payload.get('total')}: {label} completed "
            f"({payload.get('score_count', 0)} candidate scores)."
        )
    if event == "judge_failed":
        return f"Judge {label} failed: {payload.get('message', 'Unknown provider error')}"
    if event == "run_completed":
        return (
            f"Discovery complete — {payload.get('candidate_count', 0)} candidates, "
            f"{payload.get('error_count', 0)} errors."
        )
    return event.replace("_", " ").capitalize()


def _append_qualification_job_event(job_id: str, event: str, payload: dict) -> None:
    entry = {
        "seq": 0,
        "timestamp": time.time(),
        "event": event,
        "message": _qualification_event_message(event, payload),
        "payload": payload,
    }
    with _qualification_jobs_lock:
        job = _qualification_jobs.get(job_id)
        if job is None:
            return
        entry["seq"] = len(job["events"]) + 1
        job["events"].append(entry)
        job["updated_at"] = entry["timestamp"]


def _execute_qualification_job(job_id: str, request_payload: dict) -> None:
    try:
        result = run_qualification(
            request_payload["candidate_package"],
            request_payload["answer_key"],
            request_payload["providers"],
            request_payload["judges"],
            evidence_files=request_payload.get("evidence_files", []),
            progress_callback=lambda event, payload: _append_qualification_job_event(
                job_id, event, payload
            ),
        )
        with _qualification_jobs_lock:
            job = _qualification_jobs.get(job_id)
            if job is not None:
                job["status"] = "completed"
                job["result"] = result
                job["updated_at"] = time.time()
    except Exception as exc:
        _append_qualification_job_event(
            job_id,
            "run_failed",
            {"message": str(exc)},
        )
        with _qualification_jobs_lock:
            job = _qualification_jobs.get(job_id)
            if job is not None:
                job["status"] = "failed"
                job["error"] = str(exc)
                job["updated_at"] = time.time()


@router.post("/qualification/run/start")
def start_ai_qualification(request: QualificationRunRequest) -> dict:
    requested_providers = [item for item in request.providers if item in PROVIDERS]
    requested_judges = [item for item in request.judges if item in PROVIDERS]
    if not requested_providers:
        raise HTTPException(status_code=422, detail="Select at least one configured candidate provider.")

    job_id = uuid.uuid4().hex
    now = time.time()
    with _qualification_jobs_lock:
        _qualification_jobs[job_id] = {
            "job_id": job_id,
            "status": "running",
            "created_at": now,
            "updated_at": now,
            "events": [],
            "result": None,
            "error": None,
        }

    payload = {
        "candidate_package": request.candidate_package,
        "answer_key": request.answer_key,
        "evidence_files": request.evidence_files,
        "providers": requested_providers,
        "judges": requested_judges,
    }
    thread = threading.Thread(
        target=_execute_qualification_job,
        args=(job_id, payload),
        daemon=True,
    )
    thread.start()

    return {
        "schema_version": "multiviewer_ai_qualification_job_v0_1",
        "job_id": job_id,
        "status": "running",
    }


@router.get("/qualification/run/status/{job_id}")
def get_ai_qualification_status(job_id: str) -> dict:
    with _qualification_jobs_lock:
        job = _qualification_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Qualification job not found.")
        return {
            "schema_version": "multiviewer_ai_qualification_job_status_v0_1",
            "job_id": job["job_id"],
            "status": job["status"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "events": list(job["events"]),
            "result": job["result"] if job["status"] == "completed" else None,
            "error": job["error"],
        }

@router.delete("/standards/{tool}/versions/{version}")
def delete_toolbox_ai_standard_version(tool: str, version: int):
    """Delete one inactive, unreferenced AI standards version."""
    try:
        return standards_repository.delete_version(tool, version)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

