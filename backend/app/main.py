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


app.include_router(wlv_router)
