from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.services.package_registry_service import list_segy_files
from app.services.repository_registry_service import get_repository
from app.services.segy_index_service import SegyIndexService
from app.services.source_segy_representation_service import (
    build_source_segy_representations,
)
from app.services.source_intake_geometry_qaqc_service import (
    get_geometry_qaqc,
    run_geometry_qaqc,
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_lower(value: Any) -> str:
    return _clean(value).lower()


def _candidate_ids(record: Dict[str, Any]) -> set[str]:
    return {
        _clean(record.get("segy_file_id")),
        _clean(record.get("source_segy_file_id")),
        _clean(record.get("candidate_id")),
    } - {""}


def _find_candidate(candidate_id: str) -> Dict[str, Any]:
    clean_id = _clean(candidate_id)
    if not clean_id:
        raise ValueError("Source Intake candidate_id is required.")

    for record in list_segy_files():
        if clean_id in _candidate_ids(record):
            return record

    raise FileNotFoundError(f"Source Intake candidate not found: {candidate_id}")


def _resolve_source_path(record: Dict[str, Any]) -> str:
    direct = (
        record.get("source_path")
        or record.get("absolute_path")
        or record.get("path")
    )
    if direct:
        return str(Path(str(direct)).expanduser())

    repository_id = record.get("repository_id")
    relative_path = record.get("relative_path")

    if repository_id and relative_path:
        repo = get_repository(str(repository_id))
        root_path = repo.get("root_path") if repo else None
        if root_path:
            return str(Path(str(root_path)).expanduser() / str(relative_path))

    raise FileNotFoundError(
        "Source SEG-Y path could not be resolved from candidate record."
    )


def _source_segy_file_id(record: Dict[str, Any], fallback: str) -> str:
    return (
        _clean(record.get("segy_file_id"))
        or _clean(record.get("source_segy_file_id"))
        or _clean(record.get("candidate_id"))
        or fallback
    )


def _find_existing_index(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    source_id = _source_segy_file_id(record, "")
    if not source_id:
        return None

    # Prefer the existing representation contract because it already knows
    # how to discover indexed datasets linked to source SEG-Y records.
    try:
        representations = build_source_segy_representations(record, mode="3d")
    except Exception:
        return None

    indexed = (
        representations
        .get("representations", {})
        .get("indexed_preview", {})
    )

    if indexed.get("available") and indexed.get("dataset_id"):
        return {
            "dataset_id": indexed.get("dataset_id"),
            "representations": representations,
        }

    return None



def _approved_geometry_for_index(candidate_id: str) -> Dict[str, Any]:
    """
    Return the backend-approved geometry for Source Intake Build Index.

    If no QAQC report exists, run QAQC automatically. Build Index may only
    proceed when the normalized public QAQC contract says geometry is passed,
    high-confidence, and not review-required.
    """
    report = get_geometry_qaqc(candidate_id)
    if _clean_lower(report.get("status")) == "not_run":
        run_geometry_qaqc(candidate_id)
        report = get_geometry_qaqc(candidate_id)

    selected = report.get("selected_geometry") if isinstance(report.get("selected_geometry"), dict) else None
    if not selected:
        raise ValueError("Geometry QAQC did not provide selected_geometry. Run Geometry QAQC and review the report before Build Index.")

    if report.get("requires_review"):
        raise ValueError("Geometry QAQC requires review before Build Index. View the Geometry QAQC report and resolve warnings first.")

    if _clean_lower(report.get("status")) != "passed":
        raise ValueError(f"Geometry QAQC status is not passed: {report.get('status')!r}")

    if _clean_lower(report.get("confidence")) != "high":
        raise ValueError(f"Geometry QAQC confidence is not high: {report.get('confidence')!r}")

    inline_byte = selected.get("inline_byte")
    crossline_byte = selected.get("crossline_byte")
    if inline_byte is None or crossline_byte is None:
        raise ValueError("Geometry QAQC selected geometry is missing inline_byte or crossline_byte.")

    warnings = list(report.get("warnings") or []) + list(selected.get("warnings") or [])
    fatal_warnings = {
        "candidate_implies_absurd_sparse_grid",
        "candidate_headers_look_coordinate_like",
        "grid_occupancy_is_implausible",
        "one_or_both_candidate_headers_do_not_vary",
    }
    if any(str(w) in fatal_warnings for w in warnings):
        raise ValueError(f"Geometry QAQC selected geometry contains blocking warnings: {warnings}")

    return {
        "inline_byte": int(inline_byte),
        "crossline_byte": int(crossline_byte),
        "report": report,
        "selected_geometry": selected,
    }


def _existing_index_matches_geometry(dataset_id: str, geometry: Dict[str, Any]) -> bool:
    try:
        index = SegyIndexService.load_index(dataset_id)
    except Exception:
        return False

    expected_inline = int(geometry["inline_byte"])
    expected_crossline = int(geometry["crossline_byte"])

    actual_inline = index.get("inline_header_byte")
    actual_crossline = index.get("crossline_header_byte")

    if actual_inline is None or actual_crossline is None:
        return False

    try:
        return int(actual_inline) == expected_inline and int(actual_crossline) == expected_crossline
    except Exception:
        return False

def build_source_intake_candidate_index(
    candidate_id: str,
    mode: str = "3d",
) -> Dict[str, Any]:
    """
    Build or return a Source Intake indexed SEG-Y preview.

    This is intentionally Source Intake-native and does not require the
    legacy EDR submitted handoff state. It validates the candidate directly
    from Source Intake classification and source-path availability.
    """
    clean_mode = _clean_lower(mode)
    if clean_mode != "3d":
        raise ValueError(f"Unsupported Source Intake index mode: {mode!r}")

    record = _find_candidate(candidate_id)

    candidate_kind = _clean_lower(record.get("candidate_kind"))
    candidate_role = _clean_lower(record.get("candidate_role"))

    if candidate_kind != "3d_volume" or candidate_role != "volume_candidate":
        raise ValueError(
            "Source Intake Build Index currently requires a confirmed "
            f"3D volume candidate. candidate_kind={candidate_kind!r}, "
            f"candidate_role={candidate_role!r}"
        )

    source_path = _resolve_source_path(record)
    source_file = Path(source_path)

    if not source_file.exists() or not source_file.is_file():
        raise FileNotFoundError(f"Source SEG-Y file does not exist: {source_path}")

    approved_geometry = _approved_geometry_for_index(_clean(candidate_id))

    existing = _find_existing_index(record)
    if existing and _existing_index_matches_geometry(str(existing.get("dataset_id")), approved_geometry):
        return {
            "status": "ok",
            "action": "source_intake_index_preview",
            "created": False,
            "message": "Indexed preview already exists for this Source Intake candidate with approved Geometry QAQC.",
            "candidate_id": _clean(candidate_id),
            "source_segy_file_id": _source_segy_file_id(record, _clean(candidate_id)),
            "dataset_id": existing.get("dataset_id"),
            "geometry_qaqc": approved_geometry.get("report"),
            "representations": existing.get("representations"),
        }

    # If an index exists but does not record/match the approved QAQC geometry,
    # rebuild it in-place using the same deterministic dataset id. This avoids
    # keeping bad coordinate-derived indexes alive after the QAQC gate is added.
    dataset_id = existing.get("dataset_id") if existing else None
    index = SegyIndexService.build_index(
        source_path,
        dataset_id=str(dataset_id) if dataset_id else None,
        inline_byte=approved_geometry["inline_byte"],
        crossline_byte=approved_geometry["crossline_byte"],
        geometry_qaqc=approved_geometry.get("report"),
    )

    source_id = _source_segy_file_id(record, _clean(candidate_id))
    SegyIndexService.update_index(index["dataset_id"], {
        "geometry_qaqc": approved_geometry.get("report"),
        "geometry_source": "source_intake_geometry_qaqc",
        "inline_header_byte": approved_geometry["inline_byte"],
        "crossline_header_byte": approved_geometry["crossline_byte"],
        "source_repository_id": record.get("repository_id"),
        "source_segy_file_id": source_id,
        "source_relative_path": record.get("relative_path"),
        "representation_type": "indexed_preview",
        "lifecycle_status": "active",
        "source_intake_candidate_id": _clean(candidate_id),
        "source_intake_mode": clean_mode,
    })

    refreshed_index = SegyIndexService.load_index(index["dataset_id"])
    representations = build_source_segy_representations(record, mode=clean_mode)

    return {
        "status": "ok",
        "action": "source_intake_index_preview",
        "created": True,
        "message": "Source Intake indexed SEG-Y preview created using approved Geometry QAQC.",
        "geometry_qaqc": approved_geometry.get("report"),
        "selected_geometry": approved_geometry.get("selected_geometry"),
        "candidate_id": _clean(candidate_id),
        "source_segy_file_id": source_id,
        "dataset_id": refreshed_index.get("dataset_id") or index.get("dataset_id"),
        "index": refreshed_index,
        "representations": representations,
    }

def build_source_intake_indexed_preview_viewer_source(
    candidate_id: str,
    mode: str = "3d",
) -> Dict[str, Any]:
    """
    Return a Data View handoff object for an existing indexed SEG-Y preview.

    This does not create an index. The index must already exist. It does not
    register anything in Managed Data and does not create a managed Zarr volume.
    """
    clean_mode = _clean_lower(mode)
    if clean_mode != "3d":
        raise ValueError(f"Unsupported indexed preview viewer mode: {mode!r}")

    record = _find_candidate(candidate_id)

    candidate_kind = _clean_lower(record.get("candidate_kind"))
    candidate_role = _clean_lower(record.get("candidate_role"))

    if candidate_kind != "3d_volume" or candidate_role != "volume_candidate":
        raise ValueError(
            "Indexed preview viewer source currently requires a confirmed "
            f"3D volume candidate. candidate_kind={candidate_kind!r}, "
            f"candidate_role={candidate_role!r}"
        )

    existing = _find_existing_index(record)
    if not existing or not existing.get("dataset_id"):
        raise FileNotFoundError(
            f"Indexed preview is not available for Source Intake candidate: {candidate_id}"
        )

    dataset_id = _clean(existing.get("dataset_id"))
    index = SegyIndexService.load_index(dataset_id)

    shape = index.get("shape")
    axis_order = index.get("axis_order", ["inline", "crossline", "sample"])
    source_id = _source_segy_file_id(record, _clean(candidate_id))
    display_name = record.get("display_name") or record.get("filename") or source_id

    return {
        "status": "ok",
        "viewer_source": {
            "display_name": f"{display_name} — Indexed Preview",
            "viewer_mode": "3d",
            "viewer_source_type": "indexed_segy",
            "representation_type": "indexed_preview",
            "dataset_id": dataset_id,
            "source_segy_file_id": source_id,
            "candidate_id": _clean(candidate_id),
            "source_repository_id": record.get("repository_id"),
            "source_relative_path": record.get("relative_path"),
            "read_mode": "indexed_segy",
            "metadata_url": f"/api/segy-index/{dataset_id}",
            "slice_url": f"/api/segy-index/{dataset_id}/slice",
            "slice_request": {
                "inline": {"dim": 0, "query": f"/api/segy-index/{dataset_id}/slice?dim=0&index={{index}}"},
                "crossline": {"dim": 1, "query": f"/api/segy-index/{dataset_id}/slice?dim=1&index={{index}}"},
            },
            "supported_slice_dims": [0, 1],
            "unsupported_slice_dims": [2],
            "unsupported_reason": {
                "2": "Indexed SEG-Y time/depth slices are deferred; use managed Zarr or optimized cache for time-slice browsing."
            },
            "shape": shape,
            "axis_order": axis_order,
            "inline_count": index.get("inline_count"),
            "crossline_count": index.get("crossline_count"),
            "sample_count": index.get("sample_count"),
            "inline_min": index.get("inline_min"),
            "inline_max": index.get("inline_max"),
            "crossline_min": index.get("crossline_min"),
            "crossline_max": index.get("crossline_max"),
            "sample_interval_ms": index.get("sample_interval_ms"),
            "geometry_source": "indexed_segy_headers",
            "data_type": "float32",
        },
    }

