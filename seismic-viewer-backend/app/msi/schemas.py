from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


DatasetType = Literal["2d_line", "3d_volume", "unknown"]
RepresentationType = Literal[
    "indexed_segy_2d",
    "indexed_segy_headers",
    "optimized_zarr_2d_cache",
    "optimized_zarr_3d_cache",
    "zarr_2d",
    "zarr_3d",
    "metadata_bundle",
    "unknown",
]
ViewerMode = Literal["2d", "3d", "none"]
LifecycleState = Literal[
    "not_created",
    "queued",
    "building",
    "metadata_ready",
    "viewer_ready",
    "failed",
    "stale",
    "deleted",
    "superseded",
]
JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class ManagedDataset(BaseModel):
    dataset_id: str
    dataset_type: DatasetType = "unknown"
    display_name: str
    survey_name: str | None = None
    line_name: str | None = None
    volume_name: str | None = None
    processing_stage: str | None = None
    processing_version: str | None = None
    source_reference: dict[str, Any] = Field(default_factory=dict)
    registration_state: str = "registered"
    created_at: str | None = None
    updated_at: str | None = None


class ManagedRepresentation(BaseModel):
    representation_id: str
    dataset_id: str
    representation_type: RepresentationType = "unknown"
    viewer_mode: ViewerMode = "none"
    storage_uri: str | None = None
    lifecycle_state: LifecycleState = "not_created"
    viewer_ready: bool = False
    is_preferred: bool = False
    artifact_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class ArtifactJob(BaseModel):
    job_id: str
    job_type: str
    dataset_id: str | None = None
    representation_id: str | None = None
    status: JobStatus = "queued"
    progress: float | None = None
    message: str | None = None
    logs_uri: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ViewerLoadState(BaseModel):
    load_id: str
    dataset_id: str
    representation_id: str
    viewer_mode: ViewerMode
    loaded: bool
    loaded_at: str | None = None
    unloaded_at: str | None = None


class DatasetLifecycleSummary(BaseModel):
    dataset: ManagedDataset
    representations: list[ManagedRepresentation] = Field(default_factory=list)
    loaded_representations: list[ViewerLoadState] = Field(default_factory=list)
    viewer_ready: bool = False
    preferred_representation_id: str | None = None
    available_actions: list[str] = Field(default_factory=list)


class ResolveTargetRequest(BaseModel):
    target_type: Literal["dataset", "representation"]
    target_id: str
    preferred_mode: ViewerMode | None = None


class ResolveTargetResponse(BaseModel):
    loadable: bool
    dataset_id: str | None = None
    representation_id: str | None = None
    viewer_mode: ViewerMode | None = None
    representation_type: RepresentationType | None = None
    display_name: str | None = None
    reason: str | None = None
    available_actions: list[str] = Field(default_factory=list)


class LoadedViewerTarget(BaseModel):
    dataset_id: str
    representation_id: str
    viewer_mode: ViewerMode
    representation_type: RepresentationType
    display_name: str
    storage_uri: str | None = None
