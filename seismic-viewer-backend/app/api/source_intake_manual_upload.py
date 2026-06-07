from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi import File as ManualUploadFile
from fastapi import Form as ManualUploadForm
from fastapi import UploadFile as ManualUploadUploadFile

from app.services.manual_upload_package_service import ManualUploadPackageService


router = APIRouter(prefix="/api/source-intake", tags=["source-intake-manual-upload"])


@router.post("/manual-upload-package")
async def create_manual_upload_package(
    files: List[ManualUploadUploadFile] = ManualUploadFile(...),
    mode: str = ManualUploadForm("3d"),
    repository_id: Optional[str] = ManualUploadForm(None),
    package_name: Optional[str] = ManualUploadForm(None),
    intended_use: str = ManualUploadForm("source_intake"),
) -> Dict[str, Any]:
    """Stage manually uploaded SEG-Y files and supporting documents.

    This route must not start indexing, conversion, or MSI registration.
    """
    try:
        service = ManualUploadPackageService()
        return await service.create_package(
            files=files,
            mode=mode,
            repository_id=repository_id,
            package_name=package_name,
            intended_use=intended_use,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
