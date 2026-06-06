from __future__ import annotations

from typing import Any, Dict
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.services.job_service import JobService
from app.services.indexed_optimized_cache_service import IndexedOptimizedCacheService

from app.services.dataset_registry_service import (
    list_indexed_datasets,
    get_dataset,
    get_dataset_info,
    get_metadata_summary,
    get_metadata_completeness,
    get_normalized_metadata,
    update_dataset,
    delete_dataset,
)

router = APIRouter()

_dataset_job_service = JobService()
_indexed_cache_service = IndexedOptimizedCacheService(_dataset_job_service)
_indexed_cache_executor = ThreadPoolExecutor(max_workers=1)


@router.get("")
def list_datasets() -> Dict[str, Any]:
    datasets = list_indexed_datasets()
    return {
        "datasets": datasets,
        "count": len(datasets),
        "registry_version": "0.1",
    }


@router.get("/")
def list_datasets_slash() -> Dict[str, Any]:
    return list_datasets()


@router.patch("/{dataset_id}")
def patch_dataset(dataset_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return update_dataset(dataset_id, updates)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{dataset_id}")
def remove_dataset(dataset_id: str) -> Dict[str, Any]:
    try:
        return delete_dataset(dataset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{dataset_id}")
def read_dataset(dataset_id: str) -> Dict[str, Any]:
    try:
        return get_dataset(dataset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{dataset_id}/info")
def read_dataset_info(dataset_id: str) -> Dict[str, Any]:
    try:
        return get_dataset_info(dataset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{dataset_id}/metadata-summary")
def read_dataset_metadata_summary(dataset_id: str) -> Dict[str, Any]:
    try:
        return get_metadata_summary(dataset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{dataset_id}/metadata-completeness")
def read_dataset_metadata_completeness(dataset_id: str) -> Dict[str, Any]:
    try:
        return get_metadata_completeness(dataset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{dataset_id}/metadata/normalized")
def read_dataset_normalized_metadata(dataset_id: str) -> Dict[str, Any]:
    try:
        return get_normalized_metadata(dataset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))



@router.post("/{dataset_id}/optimized-cache/build")
def build_dataset_optimized_cache(dataset_id: str) -> Dict[str, Any]:
    try:
        result = _indexed_cache_service.queue_build(dataset_id)
        job_id = result.get("job_id")
        if result.get("status") == "queued" and job_id:
            _indexed_cache_executor.submit(_indexed_cache_service.run, job_id)
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{dataset_id}/optimized-cache/status")
def read_dataset_optimized_cache_status(dataset_id: str) -> Dict[str, Any]:
    try:
        return _indexed_cache_service.get_status(dataset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{dataset_id}/metadata-score-report", response_class=HTMLResponse)
def read_dataset_metadata_score_report(dataset_id: str) -> HTMLResponse:
    from fastapi.responses import HTMLResponse
    from app.reports.metadata_score_report import render_indexed_dataset_metadata_score_report

    return HTMLResponse(render_indexed_dataset_metadata_score_report(dataset_id))
