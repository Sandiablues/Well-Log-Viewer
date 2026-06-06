from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from .repository import MSIRepository


MAX_DISPLAY_NAME_LENGTH = 240


class DatasetDisplayNameUpdateRequest(BaseModel):
    display_name: str


class DatasetMetadataUpdateRequest(BaseModel):
    survey_name: str | None = None
    line_name: str | None = None
    volume_name: str | None = None
    processing_stage: str | None = None
    processing_version: str | None = None


class AdminDatasetFieldsUpdateRequest(BaseModel):
    updates: dict[str, Any]
    reason: str
    evidence_ref: str | None = None


ADMIN_DATASET_EDITABLE_FIELDS = (
    "display_name",
    "survey_name",
    "line_name",
    "volume_name",
    "processing_stage",
    "processing_version",
)

ADMIN_REJECTED_SYSTEM_FIELDS = (
    "dataset_id",
    "representation_id",
    "physical_volume_id",
    "source_volume_id",
    "source_registry_id",
    "storage_uri",
    "zarr_url",
    "artifact_path",
    "created_at",
    "updated_at",
    "lifecycle_state",
    "viewer_ready",
    "loaded",
    "loaded_at",
    "unloaded_at",
    "checksum",
    "hash",
    "geometry",
    "shape",
    "source_reference",
    "artifact_summary",
    "registration_state",
    "dataset_type",
    "representation_type",
    "viewer_mode",
    "is_preferred",
)


DATASET_METADATA_FIELDS = (
    "survey_name",
    "line_name",
    "volume_name",
    "processing_stage",
    "processing_version",
)

MAX_DATASET_METADATA_VALUE_LENGTH = 160


def _validated_optional_metadata_value(field_name: str, value: str | None) -> str | None:
    if value is None:
        return None

    clean_value = str(value).strip()

    if not clean_value:
        return None

    if len(clean_value) > MAX_DATASET_METADATA_VALUE_LENGTH:
        raise ValueError(f"{field_name} must be {MAX_DATASET_METADATA_VALUE_LENGTH} characters or fewer")

    if any(ord(char) < 32 or ord(char) == 127 for char in clean_value):
        raise ValueError(f"{field_name} cannot contain control characters")

    return clean_value


def _explicit_model_fields(request: DatasetMetadataUpdateRequest) -> set[str]:
    fields_set = getattr(request, "model_fields_set", None)
    if fields_set is None:
        fields_set = getattr(request, "__fields_set__", set())
    return {str(field_name) for field_name in fields_set}


def _validated_dataset_metadata_updates(request: DatasetMetadataUpdateRequest) -> dict[str, str | None]:
    explicit_fields = _explicit_model_fields(request)

    provided = {
        field_name: getattr(request, field_name)
        for field_name in DATASET_METADATA_FIELDS
        if field_name in explicit_fields
    }

    if not provided:
        raise ValueError("At least one editable dataset metadata field is required")

    return {
        field_name: _validated_optional_metadata_value(field_name, value)
        for field_name, value in provided.items()
    }



def require_admin_action_signal(value: str | bool | None) -> None:
    if value is True:
        return

    if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"}:
        return

    raise HTTPException(
        status_code=403,
        detail="MSI controlled metadata edits require X-MSI-Admin-Action: true",
    )


def _validate_admin_reason(value: str) -> str:
    clean_reason = str(value or "").strip()

    if not clean_reason:
        raise ValueError("reason is required for MSI admin field updates")

    if len(clean_reason) > 500:
        raise ValueError("reason must be 500 characters or fewer")

    if any(ord(char) < 32 or ord(char) == 127 for char in clean_reason):
        raise ValueError("reason cannot contain control characters")

    return clean_reason


def _validate_evidence_ref(value: str | None) -> str | None:
    if value is None:
        return None

    clean_value = str(value).strip()

    if not clean_value:
        return None

    if len(clean_value) > 500:
        raise ValueError("evidence_ref must be 500 characters or fewer")

    if any(ord(char) < 32 or ord(char) == 127 for char in clean_value):
        raise ValueError("evidence_ref cannot contain control characters")

    return clean_value


def _validated_admin_dataset_updates(request: AdminDatasetFieldsUpdateRequest) -> tuple[dict[str, str | None], str, str | None, list[str]]:
    if not isinstance(request.updates, dict) or not request.updates:
        raise ValueError("updates must include at least one field")

    rejected_fields = sorted(
        str(field_name)
        for field_name in request.updates
        if str(field_name) not in ADMIN_DATASET_EDITABLE_FIELDS
    )

    if rejected_fields:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "One or more fields are not editable through MSI admin field update",
                "rejected_fields": rejected_fields,
                "allowed_fields": list(ADMIN_DATASET_EDITABLE_FIELDS),
                "system_fields": list(ADMIN_REJECTED_SYSTEM_FIELDS),
            },
        )

    clean_updates: dict[str, str | None] = {}

    for field_name, raw_value in request.updates.items():
        key = str(field_name)
        if key == "display_name":
            clean_updates[key] = _validated_display_name(str(raw_value or ""))
        else:
            clean_updates[key] = _validated_optional_metadata_value(key, raw_value)

    return (
        clean_updates,
        _validate_admin_reason(request.reason),
        _validate_evidence_ref(request.evidence_ref),
        [],
    )


def _dataset_metadata_response(dataset, *, representation_id: str | None = None) -> dict[str, Any]:
    response = {
        "ok": True,
        "dataset_id": dataset.dataset_id,
        "survey_name": dataset.survey_name,
        "line_name": dataset.line_name,
        "volume_name": dataset.volume_name,
        "processing_stage": dataset.processing_stage,
        "processing_version": dataset.processing_version,
        "updated_at": dataset.updated_at,
        "resolved_by": "msi_dataset_admin_service",
    }

    if representation_id is not None:
        response["representation_id"] = representation_id

    return response


def _validated_display_name(value: str) -> str:
    display_name = str(value or "").strip()

    if not display_name:
        raise ValueError("display_name is required")

    if len(display_name) > MAX_DISPLAY_NAME_LENGTH:
        raise ValueError(f"display_name must be {MAX_DISPLAY_NAME_LENGTH} characters or fewer")

    if any(ord(char) < 32 or ord(char) == 127 for char in display_name):
        raise ValueError("display_name cannot contain control characters")

    return display_name


def update_dataset_display_name(
    dataset_id: str,
    request: DatasetDisplayNameUpdateRequest,
    *,
    repo: MSIRepository | None = None,
) -> dict[str, Any]:
    repository = repo or MSIRepository()

    try:
        dataset = repository.update_dataset_display_name(
            dataset_id=dataset_id,
            display_name=_validated_display_name(request.display_name),
        )
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)

    return {
        "ok": True,
        "dataset_id": dataset.dataset_id,
        "display_name": dataset.display_name,
        "updated_at": dataset.updated_at,
        "resolved_by": "msi_dataset_admin_service",
    }


def update_representation_display_name(
    representation_id: str,
    request: DatasetDisplayNameUpdateRequest,
    *,
    repo: MSIRepository | None = None,
) -> dict[str, Any]:
    repository = repo or MSIRepository()
    clean_representation_id = str(representation_id or "").strip()

    if not clean_representation_id:
        raise HTTPException(status_code=400, detail="representation_id is required")

    representation = repository.get_representation(clean_representation_id)

    if not representation:
        raise HTTPException(status_code=404, detail=f"Representation not found: {clean_representation_id}")

    try:
        dataset = repository.update_dataset_display_name(
            dataset_id=representation.dataset_id,
            display_name=_validated_display_name(request.display_name),
        )
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)

    return {
        "ok": True,
        "dataset_id": dataset.dataset_id,
        "representation_id": representation.representation_id,
        "display_name": dataset.display_name,
        "updated_at": dataset.updated_at,
        "resolved_by": "msi_dataset_admin_service",
    }



def admin_update_dataset_fields(
    dataset_id: str,
    request: AdminDatasetFieldsUpdateRequest,
    *,
    repo: MSIRepository | None = None,
) -> dict[str, Any]:
    repository = repo or MSIRepository()

    try:
        updates, reason, evidence_ref, rejected_fields = _validated_admin_dataset_updates(request)
        dataset = repository.admin_update_dataset_fields(
            dataset_id=dataset_id,
            updates=updates,
            reason=reason,
            evidence_ref=evidence_ref,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)

    return {
        "ok": True,
        "admin_edit": True,
        "dataset_id": dataset.dataset_id,
        "updated_fields": sorted(updates.keys()),
        "rejected_fields": rejected_fields,
        "display_name": dataset.display_name,
        "survey_name": dataset.survey_name,
        "line_name": dataset.line_name,
        "volume_name": dataset.volume_name,
        "processing_stage": dataset.processing_stage,
        "processing_version": dataset.processing_version,
        "updated_at": dataset.updated_at,
        "resolved_by": "msi_dataset_admin_service",
    }


def admin_update_representation_dataset_fields(
    representation_id: str,
    request: AdminDatasetFieldsUpdateRequest,
    *,
    repo: MSIRepository | None = None,
) -> dict[str, Any]:
    repository = repo or MSIRepository()
    clean_representation_id = str(representation_id or "").strip()

    if not clean_representation_id:
        raise HTTPException(status_code=400, detail="representation_id is required")

    representation = repository.get_representation(clean_representation_id)

    if not representation:
        raise HTTPException(status_code=404, detail=f"Representation not found: {clean_representation_id}")

    response = admin_update_dataset_fields(
        representation.dataset_id,
        request,
        repo=repository,
    )
    response["representation_id"] = representation.representation_id
    return response


def update_dataset_descriptive_metadata(
    dataset_id: str,
    request: DatasetMetadataUpdateRequest,
    *,
    repo: MSIRepository | None = None,
) -> dict[str, Any]:
    repository = repo or MSIRepository()

    try:
        dataset = repository.update_dataset_descriptive_metadata(
            dataset_id=dataset_id,
            updates=_validated_dataset_metadata_updates(request),
        )
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)

    return _dataset_metadata_response(dataset)


def update_representation_dataset_metadata(
    representation_id: str,
    request: DatasetMetadataUpdateRequest,
    *,
    repo: MSIRepository | None = None,
) -> dict[str, Any]:
    repository = repo or MSIRepository()
    clean_representation_id = str(representation_id or "").strip()

    if not clean_representation_id:
        raise HTTPException(status_code=400, detail="representation_id is required")

    representation = repository.get_representation(clean_representation_id)

    if not representation:
        raise HTTPException(status_code=404, detail=f"Representation not found: {clean_representation_id}")

    try:
        dataset = repository.update_dataset_descriptive_metadata(
            dataset_id=representation.dataset_id,
            updates=_validated_dataset_metadata_updates(request),
        )
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)

    return _dataset_metadata_response(dataset, representation_id=representation.representation_id)
