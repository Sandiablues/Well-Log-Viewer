"""
MultiViewer Well Log Viewer — backend application entry point.

This app exposes the WLV backend-owned API contracts. It intentionally keeps
frontend prototype behavior unchanged; the frontend migration to these
contracts is a later block.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .wells.api_wlv import router as wlv_router
from .system.api_system import router as system_router
from .inventory.api_inventory import router as inventory_router
from .wbv.router import router as wbv_router
from .ingestion.api_ingestion import router as ingestion_router
from .source_intake.router import router as source_intake_router
from .wdv_templates.router import router as wdv_template_router
from .wdv_session.router import router as wdv_session_router
from .inventory.canonical_curve_sample_router import router as canonical_curve_sample_router
from .wdv_session.canonical_router import router as canonical_wdv_session_router
from .wdv_session.canonical_command_router import router as canonical_wdv_command_router
from .wells.canonical_viewer_package_router import router as canonical_viewer_package_router
from .wdv_workspace.router import router as canonical_wdv_workspace_router
from .wdv_templates.canonical_apply_router import router as canonical_template_command_router
from .knowledge.api_knowledge import router as knowledge_router
from .knowledge.api_managed_knowledge import router as managed_knowledge_router
from .knowledge.api_managed_knowledge import resolve_router as resolve_knowledge_router
from .knowledge.api_managed_instructions import router as managed_instruction_router
from .wdv_shared_canvas.router import router as shared_canvas_router

app = FastAPI(
    title="MultiViewer Well Log Viewer Backend",
    version="0.1.0",
    description="Backend-owned well/log/curve/interval/viewer-package contracts for WLV.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, object]:
    return {"ok": True, "service": "wlv-backend", "scope": "backend_foundation"}


app.include_router(system_router)
app.include_router(knowledge_router)
app.include_router(managed_knowledge_router)
app.include_router(resolve_knowledge_router)
app.include_router(managed_instruction_router)
app.include_router(inventory_router)
app.include_router(wbv_router)
app.include_router(ingestion_router)
app.include_router(source_intake_router)
app.include_router(wdv_session_router)
app.include_router(canonical_wdv_session_router)
app.include_router(canonical_wdv_command_router)
app.include_router(canonical_curve_sample_router)
app.include_router(canonical_viewer_package_router)
app.include_router(canonical_wdv_workspace_router)
app.include_router(canonical_template_command_router)
app.include_router(wdv_template_router)
app.include_router(shared_canvas_router)
app.include_router(wlv_router)
