from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.zarr_slice_service import (
    clear_slice_cache as clear_slice_cache_service,
    get_raw_zarr_slice as get_raw_zarr_slice_service,
    get_slice_cache_info as get_slice_cache_info_service,
)

router = APIRouter(tags=["slices"])


@router.get("/slice")
def get_raw_zarr_slice(
    zarr_path: str = Query(..., description="Zarr path, e.g. /data/zarr/f3_seismic.zarr"),
    dim: int = Query(..., ge=0, le=2, description="0=inline, 1=crossline, 2=time/depth"),
    index: int = Query(..., ge=0, description="Slice index along selected dimension"),
):
    return get_raw_zarr_slice_service(
        zarr_path=zarr_path,
        dim=dim,
        index=index,
    )


@router.get("/slice/cache-info")
def get_slice_cache_info():
    return get_slice_cache_info_service()


@router.post("/slice/clear-cache")
def clear_slice_cache():
    return clear_slice_cache_service()
