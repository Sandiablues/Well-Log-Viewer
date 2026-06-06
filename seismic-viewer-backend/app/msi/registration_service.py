from __future__ import annotations

from pathlib import Path
from typing import Any

from .repository import MSIRepository
from app.storage.service import endrepo_zarr_url_to_storage_uri, is_endrepo_zarr_url, resolve_endrepo_zarr_url_path
from app.services.metadata_identity_extraction_service import resolve_canonical_identity


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _storage_uri_from_zarr_url(zarr_url: str, explicit_storage_uri: str | None = None) -> str:
    explicit = _clean(explicit_storage_uri)
    if explicit:
        return explicit
    if is_endrepo_zarr_url(zarr_url):
        return endrepo_zarr_url_to_storage_uri(zarr_url)
    if zarr_url.startswith("/data/zarr/"):
        return "local://zarr/" + zarr_url.replace("/data/zarr/", "", 1)
    if zarr_url.startswith("local://zarr/"):
        return zarr_url
    return zarr_url


def _zarr_exists(zarr_url: str, backend_root: Path | None = None) -> bool:
    root = backend_root or Path(__file__).resolve().parents[2]

    if zarr_url.startswith("/data/zarr/"):
        return (root / zarr_url.lstrip("/")).exists()

    if is_endrepo_zarr_url(zarr_url):
        try:
            return resolve_endrepo_zarr_url_path(zarr_url).exists()
        except Exception:
            return False

    if zarr_url.startswith("local://zarr/"):
        return (root / "data" / "zarr" / zarr_url.replace("local://zarr/", "", 1)).exists()

    return Path(zarr_url).exists()


def _dataset_type_from_segy(segy_file: dict[str, Any]) -> str:
    candidate_kind = _clean(segy_file.get("candidate_kind"))
    dataset_type = _clean(segy_file.get("dataset_type"))

    if dataset_type in {"2d_line", "3d_volume"}:
        return dataset_type

    if candidate_kind in {"2d_line", "3d_volume"}:
        return candidate_kind

    return "unknown"



def _expected_endrepo_dimension_for_dataset_type(dataset_type: str) -> str | None:
    if dataset_type == "2d_line":
        return "2d"
    if dataset_type == "3d_volume":
        return "3d"
    return None


def _endrepo_dimension_from_zarr_url(zarr_url: str | None) -> str | None:
    text = str(zarr_url or "").strip()
    if "/managed/zarr/2d/" in text:
        return "2d"
    if "/managed/zarr/3d/" in text:
        return "3d"
    return None


def _endrepo_dimension_from_storage_uri(storage_uri: str | None) -> str | None:
    text = str(storage_uri or "").strip()
    if text.startswith("endrepo://managed/zarr/2d/"):
        return "2d"
    if text.startswith("endrepo://managed/zarr/3d/"):
        return "3d"
    return None


def _representation_type(dataset_type: str) -> tuple[str, str]:
    if dataset_type == "3d_volume":
        return "zarr_3d", "3d"
    if dataset_type == "2d_line":
        return "zarr_2d", "2d"
    return "unknown", "none"


def register_converted_segy_file(
    segy_file: dict[str, Any],
    *,
    backend_root: Path | None = None,
) -> dict[str, Any]:
    """
    Register a converted source-registry SEG-Y file into MSI.

    Scope for Block 1F-A:
    - full Zarr artifacts only
    - viewer-ready only
    - idempotent upsert
    - no viewer load state
    """
    segy_file_id = _clean(segy_file.get("segy_file_id"))
    filename = _clean(segy_file.get("filename")) or segy_file_id
    volume_id = _clean(segy_file.get("volume_id"))
    zarr_url = _clean(segy_file.get("zarr_url"))
    conversion_status = _clean(segy_file.get("conversion_status"))

    if conversion_status not in {"converted", "ready"}:
        return {
            "registered": False,
            "reason": "not_converted",
            "conversion_status": conversion_status,
        }

    if not segy_file_id:
        return {"registered": False, "reason": "missing_segy_file_id"}

    if not volume_id:
        return {
            "registered": False,
            "reason": "missing_volume_id",
            "segy_file_id": segy_file_id,
        }

    if not zarr_url:
        return {
            "registered": False,
            "reason": "missing_zarr_url",
            "segy_file_id": segy_file_id,
            "volume_id": volume_id,
        }

    if not _zarr_exists(zarr_url, backend_root=backend_root):
        return {
            "registered": False,
            "reason": "zarr_artifact_missing",
            "segy_file_id": segy_file_id,
            "volume_id": volume_id,
            "zarr_url": zarr_url,
        }

    dataset_type = _dataset_type_from_segy(segy_file)
    representation_type, viewer_mode = _representation_type(dataset_type)
    storage_uri = _storage_uri_from_zarr_url(zarr_url, segy_file.get("storage_uri"))

    expected_endrepo_dimension = _expected_endrepo_dimension_for_dataset_type(dataset_type)
    actual_endrepo_dimension = _endrepo_dimension_from_zarr_url(zarr_url)
    actual_storage_dimension = _endrepo_dimension_from_storage_uri(storage_uri)
    if actual_endrepo_dimension and expected_endrepo_dimension and actual_endrepo_dimension != expected_endrepo_dimension:
        return {
            "registered": False,
            "reason": "zarr_url_dataset_type_dimension_mismatch",
            "segy_file_id": segy_file_id,
            "volume_id": volume_id,
            "dataset_type": dataset_type,
            "expected_dimension": expected_endrepo_dimension,
            "actual_dimension": actual_endrepo_dimension,
            "zarr_url": zarr_url,
        }

    if actual_storage_dimension and expected_endrepo_dimension and actual_storage_dimension != expected_endrepo_dimension:
        return {
            "registered": False,
            "reason": "storage_uri_dataset_type_dimension_mismatch",
            "segy_file_id": segy_file_id,
            "volume_id": volume_id,
            "dataset_type": dataset_type,
            "expected_dimension": expected_endrepo_dimension,
            "actual_dimension": actual_storage_dimension,
            "storage_uri": storage_uri,
        }

    if actual_endrepo_dimension and actual_storage_dimension and actual_endrepo_dimension != actual_storage_dimension:
        return {
            "registered": False,
            "reason": "zarr_url_storage_uri_dimension_mismatch",
            "segy_file_id": segy_file_id,
            "volume_id": volume_id,
            "dataset_type": dataset_type,
            "zarr_url_dimension": actual_endrepo_dimension,
            "storage_uri_dimension": actual_storage_dimension,
            "zarr_url": zarr_url,
            "storage_uri": storage_uri,
        }

    if representation_type == "unknown" or viewer_mode == "none":
        return {
            "registered": False,
            "reason": "unsupported_dataset_type",
            "segy_file_id": segy_file_id,
            "dataset_type": dataset_type,
        }

    dataset_id = f"source_segy:{segy_file_id}"
    representation_id = f"msi_repr:source_segy_{segy_file_id}:zarr_{volume_id}"

    source_reference = {
        "source_system": "existing_source_registry",
        "source_segy_file_id": segy_file_id,
        "filename": filename,
        "relative_path": segy_file.get("relative_path"),
        "repository_id": segy_file.get("repository_id"),
        "package_id": segy_file.get("package_id"),
        "line_id": segy_file.get("line_id"),
        "candidate_kind": segy_file.get("candidate_kind"),
        "candidate_role": segy_file.get("candidate_role"),
        "conversion_status": conversion_status,
        "volume_id": volume_id,
        "zarr_url": zarr_url,
        "job_id": segy_file.get("job_id"),
    }

    metadata_identity = resolve_canonical_identity(
        source_reference,
        segy_file=segy_file,
        backend_root=backend_root,
    )
    if metadata_identity.get("identity_candidates"):
        source_reference["identity_candidates"] = metadata_identity.get("identity_candidates")
    if metadata_identity.get("identity_extraction"):
        source_reference["identity_extraction"] = metadata_identity.get("identity_extraction")
    for key in (
        "survey_name_source", "survey_name_evidence", "survey_name_matched_alias", "survey_name_confidence",
        "line_name_source", "line_name_evidence", "line_name_matched_alias", "line_name_confidence",
        "volume_name_source", "volume_name_evidence", "volume_name_matched_alias", "volume_name_confidence",
    ):
        if metadata_identity.get(key):
            source_reference[key] = metadata_identity.get(key)

    artifact_summary = {
        "source": "conversion_registration",
        "artifact_role": "full_zarr",
        "volume_id": volume_id,
        "zarr_url": zarr_url,
        "storage_uri": storage_uri,
        "job_id": segy_file.get("job_id"),
        "conversion_status": conversion_status,
    }

    dataset = {
        "dataset_id": dataset_id,
        "dataset_type": dataset_type,
        "display_name": filename or dataset_id,
        "survey_name": segy_file.get("survey_name") or metadata_identity.get("survey_name"),
        "line_name": segy_file.get("line_name") or metadata_identity.get("line_name"),
        "volume_name": segy_file.get("volume_name") or metadata_identity.get("volume_name"),
        "source_reference": source_reference,
        "registration_state": "registered",
    }

    representation = {
        "representation_id": representation_id,
        "dataset_id": dataset_id,
        "representation_type": representation_type,
        "viewer_mode": viewer_mode,
        "storage_uri": storage_uri,
        "lifecycle_state": "viewer_ready",
        "viewer_ready": True,
        "is_preferred": True,
        "artifact_summary": artifact_summary,
    }

    repo = MSIRepository()
    result = repo.upsert_managed_inventory([dataset], [representation])

    return {
        "registered": True,
        "dataset_id": dataset_id,
        "representation_id": representation_id,
        "dataset_type": dataset_type,
        "representation_type": representation_type,
        "viewer_mode": viewer_mode,
        "volume_id": volume_id,
        "zarr_url": zarr_url,
        **result,
    }
