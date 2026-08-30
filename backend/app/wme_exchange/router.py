from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/wme/exchange", tags=["wme-exchange"])

_ALLOWED_SUPPORT_SUFFIXES = {".pdf", ".xlsx", ".xls", ".csv", ".txt"}
_MAX_FILE_BYTES = 150 * 1024 * 1024
_MAX_PACKAGE_BYTES = 500 * 1024 * 1024


def _safe_name(value: str, fallback: str) -> str:
    name = Path(value or fallback).name
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return clean or fallback


async def _read_limited(upload: UploadFile, *, allowed_suffixes: set[str]) -> bytes:
    filename = _safe_name(upload.filename or "file", "file")
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_suffixes:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")
    payload = await upload.read(_MAX_FILE_BYTES + 1)
    if len(payload) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds 150 MB limit: {filename}")
    return payload


@router.post("/package")
async def build_ai_package(
    context_workbook: UploadFile = File(...),
    supporting_files: list[UploadFile] = File(default=[]),
    job_manifest: str = Form(...),
) -> StreamingResponse:
    try:
        manifest = json.loads(job_manifest)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid WME job manifest JSON.") from exc

    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="WME job manifest must be an object.")

    context_name = _safe_name(context_workbook.filename or "Well_Info_Context.xlsx", "Well_Info_Context.xlsx")
    context_bytes = await _read_limited(context_workbook, allowed_suffixes={".xlsx"})

    support_payloads: list[tuple[str, bytes]] = []
    total_bytes = len(context_bytes)
    seen_names: set[str] = set()
    for upload in supporting_files:
        name = _safe_name(upload.filename or "supporting_file", "supporting_file")
        base = name
        index = 2
        while name.lower() in seen_names:
            stem = Path(base).stem
            suffix = Path(base).suffix
            name = f"{stem}_{index}{suffix}"
            index += 1
        seen_names.add(name.lower())
        payload = await _read_limited(upload, allowed_suffixes=_ALLOWED_SUPPORT_SUFFIXES)
        total_bytes += len(payload)
        if total_bytes > _MAX_PACKAGE_BYTES:
            raise HTTPException(status_code=413, detail="AI package exceeds the 500 MB limit.")
        support_payloads.append((name, payload))

    now = datetime.now(timezone.utc)
    job_id = f"wme-{now.strftime('%Y%m%dT%H%M%SZ')}"
    manifest = {
        **manifest,
        "package_type": "multiviewer-wme-ai-package",
        "package_version": "1.0.0",
        "job_id": job_id,
        "created_at": now.isoformat(),
        "context_workbook": f"context/{context_name}",
        "supporting_documents": [f"supporting_documents/{name}" for name, _ in support_payloads],
        "return_requirement": "Return the completed Context workbook only. Preserve Field Key and known Value columns.",
    }

    instructions = """# MultiViewer WME External AI Instructions

1. Open the workbook in `context/` and review the supporting documents.
2. Do not change `Field Key`, `Value`, `Source`, or other known-context columns.
3. Populate only the columns prefixed `AI`.
4. Recommend values only where supported by explicit evidence.
5. For every recommendation provide:
   - AI Recommended Value
   - AI Unit, where applicable
   - AI Source (supporting document filename)
   - AI Source Reference (page, sheet, table, or section)
   - AI Evidence (the decisive label/value evidence)
   - AI Confidence
   - AI Status: proposed, unresolved, or conflict
6. Do not infer missing values without explicit evidence.
7. Distinguish actual, planned, proposed, and forecast values in AI Evidence or AI Status.
8. Preserve the workbook structure and return the completed `.xlsx` Context workbook to the user.
"""

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        archive.writestr("AI_INSTRUCTIONS.md", instructions)
        archive.writestr(f"context/{context_name}", context_bytes)
        for name, payload in support_payloads:
            archive.writestr(f"supporting_documents/{name}", payload)
    output.seek(0)

    identity = str(manifest.get("well_name") or manifest.get("wellbore_name") or "well")
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", identity).strip("_") or "well"
    filename = f"WME_AI_PACKAGE_{stem}_{now.strftime('%Y%m%d_%H%M%S')}.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(output, media_type="application/zip", headers=headers)
