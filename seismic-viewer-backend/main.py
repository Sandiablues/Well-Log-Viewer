from app.storage.service import storage_service
from fastapi.responses import FileResponse
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
# Legacy endpoints router intentionally not mounted; routes moved to bounded modules.
from app.api.document_evidence import router as document_evidence_router
from app.api.documents import router as documents_router
from app.api.system import router as system_router
from app.api import segy_index
from app.api import runtime_identity
from app.api import ingestion
from app.api import slices
from app.api import sections2d
from app.api import volumes
from app.api import volume_metadata
from app.api.datasets import router as datasets_router
from app.api.source_segy_representations import router as source_segy_representations_router
from app.api.source_segy_lifecycle import router as source_segy_lifecycle_router
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

UPLOAD_DIR = BASE_DIR / "data" / "uploads"
ZARR_DIR = BASE_DIR / "data" / "zarr"
ENDREPO_MANAGED_ZARR_DIR = storage_service().repository_root / "managed" / "zarr"
FRONTEND_DIST = BASE_DIR / "packaged_dist"


from app.api import knowledge as knowledge_api
from app.api import source_staging
from app.api import source_intake
from app.api import source_intake_documents
from app.api import managed_data
from app.api import source_registry_admin
from app.api import toolbox
from app.msi.routes import router as msi_router
from app.storage.routes import router as storage_router
from app.api.artifact_lifecycle import router as artifact_lifecycle_router
from app.api import artifact_lifecycle
app = FastAPI(title="Seismic Viewer API")

app.include_router(documents_router)
app.include_router(system_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ZARR_DIR.mkdir(parents=True, exist_ok=True)
ENDREPO_MANAGED_ZARR_DIR.mkdir(parents=True, exist_ok=True)

app.include_router(runtime_identity.router, prefix="/api")

app.mount(
    "/endrepo/managed/zarr",
    StaticFiles(directory=str(ENDREPO_MANAGED_ZARR_DIR)),
    name="endrepo_managed_zarr_data",
)

app.mount(
    "/data/zarr",
    StaticFiles(directory=str(ZARR_DIR)),
    name="zarr_data",
)

app.include_router(ingestion.router, prefix="/api")
app.include_router(slices.router, prefix="/api")
app.include_router(sections2d.router, prefix="/api")
app.include_router(volumes.router, prefix="/api")
app.include_router(volume_metadata.router, prefix="/api")
# app.include_router(api_router, prefix="/api")  # retired in E16
app.include_router(document_evidence_router)
app.include_router(segy_index.router)
app.include_router(datasets_router, prefix="/api/datasets", tags=["datasets"])
app.include_router(source_segy_representations_router)
app.include_router(source_segy_lifecycle_router)

app.include_router(knowledge_api.router)
app.include_router(source_staging.router, prefix="/api", tags=["source-staging"])
app.include_router(source_intake_documents.router)
app.include_router(source_intake.router)
app.include_router(managed_data.router)
app.include_router(source_registry_admin.router, prefix="/api", tags=["source-registry-admin"])
app.include_router(toolbox.router)
app.include_router(msi_router)
app.include_router(artifact_lifecycle.router)
app.include_router(storage_router)
app.include_router(artifact_lifecycle_router)
@app.get("/build-info.json")
async def get_build_info():
    build_info_path = FRONTEND_DIST / "build-info.json"
    if build_info_path.exists() and build_info_path.is_file():
        return FileResponse(build_info_path)
    return {"detail": "build-info.json not found in packaged frontend bundle."}

# DOCUMENT-ADD-MD-3B — multipart upload endpoint for MD Add Documents.
# Backend/MSI remains authoritative for document storage and attachment records.
from fastapi import File as _DocumentAddFile, Form as _DocumentAddForm, UploadFile as _DocumentAddUploadFile, HTTPException as _DocumentAddHTTPException
import json as _document_add_json


@app.post("/api/msi/document-attachments/upload")
async def upload_msi_document_attachments(
    files: list[_DocumentAddUploadFile] = _DocumentAddFile(...),
    target_ids: str = _DocumentAddForm(...),
    scope_kind: str = _DocumentAddForm("selected_data"),
    attachment_scope: str = _DocumentAddForm("dataset"),
    relationship_type: str = _DocumentAddForm("line_volume_specific"),
    survey_name: str = _DocumentAddForm(""),
    document_type: str = _DocumentAddForm("unknown"),
    document_role: str = _DocumentAddForm("supporting_document"),
    source: str = _DocumentAddForm("manual_upload"),
    notes: str = _DocumentAddForm(""),
):
    try:
        parsed_target_ids = _document_add_json.loads(target_ids)
        if not isinstance(parsed_target_ids, list):
            raise ValueError("target_ids must be a JSON array")
        uploaded_documents = []
        for upload in files:
            content = await upload.read()
            uploaded_documents.append({
                "filename": upload.filename or "uploaded_document",
                "mime_type": upload.content_type or "application/octet-stream",
                "content": content,
            })
        from app.services.msi_document_attachment_service import attach_uploaded_documents_to_managed_data
        return attach_uploaded_documents_to_managed_data(
            uploaded_documents=uploaded_documents,
            target_ids=[str(value) for value in parsed_target_ids],
            scope_kind=scope_kind,
            survey_name=survey_name or None,
            document_type=document_type or None,
            document_role=document_role or None,
            notes=notes or None,
        )
    except Exception as exc:
        raise _DocumentAddHTTPException(status_code=400, detail=str(exc)) from exc

# DOCUMENT_ACCESS_UNIFICATION_FINAL_ROUTES
# Single backend document-access contract for SR/Source Intake and MD uploads.
@app.get("/api/documents/{document_id}/open")
def open_registered_document_unified(document_id: str):
    from app.services.document_access_service import registered_document_file_response
    return registered_document_file_response(document_id, disposition="inline")


@app.get("/api/documents/{document_id}/view")
def view_registered_document_unified(document_id: str):
    from app.services.document_access_service import registered_document_file_response
    return registered_document_file_response(document_id, disposition="inline")


@app.get("/api/documents/{document_id}/download")
def download_registered_document_unified(document_id: str):
    from app.services.document_access_service import registered_document_file_response
    return registered_document_file_response(document_id, disposition="attachment")


if FRONTEND_DIST.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIST), html=True),
        name="frontend",
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
@app.get("/")
async def serve_frontend_root():
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"detail": "Frontend build not found. Run npm run build in seismic-viewer-frontend."}


@app.get("/{full_path:path}")
async def serve_frontend_app(full_path: str):
    # Do not intercept API or data routes.
    if full_path.startswith("api/") or full_path.startswith("data/"):
        return {"detail": "Not found"}

    requested_path = FRONTEND_DIST / full_path
    if requested_path.exists() and requested_path.is_file():
        return FileResponse(requested_path)

    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path)

    return {"detail": "Frontend build not found. Run npm run build in seismic-viewer-frontend."}
