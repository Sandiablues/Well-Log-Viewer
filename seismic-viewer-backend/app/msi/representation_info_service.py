from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.msi.representation_resolver_service import resolve_msi_representation_volume
from app.services.volume_registry_service import get_volume_info


def get_representation_info(representation_id: str) -> dict[str, Any]:
    resolved = resolve_msi_representation_volume(representation_id)

    physical_volume_id = str(resolved.get("physical_volume_id") or "").strip()
    dataset_id = resolved.get("dataset_id")

    if not physical_volume_id:
        raise HTTPException(
            status_code=409,
            detail=f"MSI representation has no physical volume id: {representation_id}",
        )

    payload = get_volume_info(physical_volume_id)

    if not isinstance(payload, dict):
        return {
            "volume_info": payload,
            "msi_representation_id": representation_id,
            "msi_dataset_id": dataset_id,
            "physical_volume_id": physical_volume_id,
            "resolved_by": "msi_representation_info_service",
        }

    volume_payload = payload.get("volume") if isinstance(payload.get("volume"), dict) else {}
    volume_metadata = volume_payload.get("metadata") if isinstance(volume_payload.get("metadata"), dict) else {}

    # MSI-native info exposes the resolved physical volume metadata as a
    # first-class top-level metadata object so Info panels do not have to infer
    # geometry truth from MSI managed-list rows or legacy bridge details.
    metadata = dict(payload.get("metadata") or volume_metadata or {})
    metadata["msi_representation_id"] = representation_id
    metadata["msi_dataset_id"] = dataset_id
    metadata["physical_volume_id"] = physical_volume_id

    return {
        **payload,
        "metadata": metadata,
        "msi_representation_id": representation_id,
        "msi_dataset_id": dataset_id,
        "physical_volume_id": physical_volume_id,
        "resolved_by": "msi_representation_info_service",
        "info_contract": "msi_representation_info_v1",
    }
