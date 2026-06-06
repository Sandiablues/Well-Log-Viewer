from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.artifact_lifecycle_service import artifact_lifecycle_service


router = APIRouter(prefix="/api/artifacts", tags=["artifact-lifecycle"])


class ArtifactDeleteDryRunRequest(BaseModel):
    scope_type: str
    scope_id: str


class ArtifactDeleteExecuteRequest(BaseModel):
    scope_type: str
    scope_id: str
    confirm_delete_derived_artifacts: bool = False


@router.get("/health")
def artifact_lifecycle_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "artifact_lifecycle",
        "schema_version": "artifact.lifecycle.service.v1",
        "mode": "graph_resolver_with_guarded_delete_execution",
    }


@router.get("/graph/source-candidate/{candidate_id}")
def graph_for_source_candidate(candidate_id: str) -> Dict[str, Any]:
    try:
        return artifact_lifecycle_service.graph_for_source_candidate(candidate_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build artifact graph for source candidate failed: {exc}") from exc


@router.get("/graph/msi-dataset/{dataset_id}")
def graph_for_msi_dataset(dataset_id: str) -> Dict[str, Any]:
    try:
        return artifact_lifecycle_service.graph_for_msi_dataset(dataset_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build artifact graph for MSI dataset failed: {exc}") from exc


@router.get("/graph/msi-representation/{representation_id}")
def graph_for_msi_representation(representation_id: str) -> Dict[str, Any]:
    try:
        return artifact_lifecycle_service.graph_for_msi_representation(representation_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build artifact graph for MSI representation failed: {exc}") from exc


@router.get("/graph/validate/source-candidate/{candidate_id}")
def validate_source_candidate_graph(candidate_id: str) -> Dict[str, Any]:
    try:
        return artifact_lifecycle_service.validate_source_candidate(candidate_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Validate artifact graph for source candidate failed: {exc}") from exc



@router.post("/graph/delete-dry-run")
def delete_graph_dry_run(request: ArtifactDeleteDryRunRequest) -> Dict[str, Any]:
    try:
        return artifact_lifecycle_service.delete_dry_run(request.scope_type, request.scope_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Build artifact delete dry-run failed: {exc}") from exc


@router.post("/graph/delete")
def delete_graph_execute(request: ArtifactDeleteExecuteRequest) -> Dict[str, Any]:
    try:
        return artifact_lifecycle_service.delete_graph(
            request.scope_type,
            request.scope_id,
            confirm_delete_derived_artifacts=request.confirm_delete_derived_artifacts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Execute artifact graph delete failed: {exc}") from exc
