import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from app.services.metadata_quality_service import build_metadata_quality_report
from app.services.volume_registry_service import get_volume_info as get_resolved_volume_info
from app.msi.representation_resolver_service import resolve_msi_representation_volume


DATA_DIR = Path(os.environ.get("SEISMIC_VIEWER_DATA_DIR", "./data"))
VOLUMES_JSON = Path(os.environ.get("VOLUMES_JSON", str(DATA_DIR / "volumes.json")))
ZARR_DIR = Path(os.environ.get("ZARR_DIR", str(DATA_DIR / "zarr")))
REGISTRY_DIR = DATA_DIR / "registry"



def _physical_volume_id_from_msi_representation(volume_id: str) -> Optional[str]:
    raw = str(volume_id or "").strip()
    if not raw.startswith("msi_repr:"):
        return None

    try:
        resolved = resolve_msi_representation_volume(raw)
    except Exception:
        resolved = {}

    if isinstance(resolved, dict):
        physical_volume_id = str(resolved.get("physical_volume_id") or "").strip()
        if physical_volume_id:
            return physical_volume_id

    match = re.search(r":zarr_([0-9a-fA-F-]{16,})$", raw)
    if match:
        return match.group(1)

    return None


def _resolved_info_for_summary(requested_volume_id: str, lookup_volume_id: str) -> Dict[str, Any]:
    for candidate in [requested_volume_id, lookup_volume_id]:
        try:
            info = get_resolved_volume_info(candidate)
        except Exception:
            info = {}
        if isinstance(info, dict) and info.get("volume"):
            return info
    return {}



def _read_json(path: Path, default: Any = None) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def _read_text(path: Path) -> Optional[str]:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    return None


def _load_volumes() -> Dict[str, Any]:
    data = _read_json(VOLUMES_JSON, {})
    return data if isinstance(data, dict) else {}


def _find_volume(volume_id: str) -> Optional[Dict[str, Any]]:
    volumes = _load_volumes()

    if volume_id in volumes and isinstance(volumes[volume_id], dict):
        volume = dict(volumes[volume_id])
        volume.setdefault("id", volume_id)
        return volume

    for key, value in volumes.items():
        if isinstance(value, dict) and value.get("id") == volume_id:
            volume = dict(value)
            volume.setdefault("id", key)
            return volume

    return None


def _infer_dataset_type(volume: Dict[str, Any]) -> str:
    metadata = volume.get("metadata") or {}
    zarr_metadata = metadata.get("zarr") or {}
    shape = metadata.get("shape") or zarr_metadata.get("shape")

    if volume.get("dataset_type"):
        return volume.get("dataset_type")

    if metadata.get("is_3d") is True and isinstance(shape, list) and len(shape) == 3:
        return "3d_volume"

    if metadata.get("is_3d") is False:
        return "2d_line"

    if isinstance(shape, list) and len(shape) == 2:
        return "2d_line"

    if isinstance(shape, list) and len(shape) == 3:
        return "3d_volume"

    return "unknown"


def _display_name(volume_id: str, volume: Dict[str, Any]) -> str:
    metadata = volume.get("metadata") or {}
    source = volume.get("source") or {}

    return (
        volume.get("display_name")
        or source.get("line_display_name")
        or metadata.get("line_display_name")
        or metadata.get("display_name")
        or volume.get("filename")
        or metadata.get("original_filename")
        or volume_id
    )


def _sidecar_base(volume_id: str, volume: Dict[str, Any]) -> Path:
    zarr_url = str(volume.get("zarr_url") or "")
    if zarr_url:
        name = zarr_url.rstrip("/").split("/")[-1]
        if name:
            return ZARR_DIR / name

    zarr_path = str(volume.get("zarr_path") or "")
    if zarr_path:
        return Path(zarr_path)

    return ZARR_DIR / f"{volume_id}.zarr"


def _sidecar_paths(volume_id: str, volume: Dict[str, Any]) -> Dict[str, Path]:
    base = _sidecar_base(volume_id, volume)

    candidates = {
        "viewer_metadata": Path(str(base) + ".viewer_metadata.json"),
        "text_header": Path(str(base) + ".segy_text_header.txt"),
        "binary_header": Path(str(base) + ".segy_binary_header.json"),
        "trace_header_summary": Path(str(base) + ".trace_header_summary.json"),
        "normalized_metadata": base / ".normalized_metadata.json",
    }

    # Older/non-.zarr sidecar names exist in the project.
    # Try stripped UUID base as fallback.
    if str(base).endswith(".zarr"):
        stripped = Path(str(base)[:-5])
        fallback = {
            "viewer_metadata": Path(str(stripped) + ".viewer_metadata.json"),
            "text_header": Path(str(stripped) + ".segy_text_header.txt"),
            "binary_header": Path(str(stripped) + ".segy_binary_header.json"),
            "trace_header_summary": Path(str(stripped) + ".trace_header_summary.json"),
        }

        for key, path in fallback.items():
            if not candidates[key].exists() and path.exists():
                candidates[key] = path

    return candidates


def _first_number(*values: Any) -> Optional[float]:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _geometry(volume: Dict[str, Any], viewer_metadata: Any, binary_header: Any, trace_header_summary: Any) -> Dict[str, Any]:
    metadata = volume.get("metadata") or {}
    zarr_metadata = metadata.get("zarr") or {}

    viewer = viewer_metadata if isinstance(viewer_metadata, dict) else {}
    binary = binary_header if isinstance(binary_header, dict) else {}
    trace = trace_header_summary if isinstance(trace_header_summary, dict) else {}

    shape = (
        metadata.get("shape")
        or zarr_metadata.get("shape")
        or viewer.get("shape")
        or viewer.get("zarr_shape")
    )

    sample_interval_ms = _first_number(
        metadata.get("sample_interval_ms"),
        metadata.get("sample_rate"),
        zarr_metadata.get("sample_interval_ms"),
        zarr_metadata.get("sample_rate"),
        viewer.get("sample_interval_ms"),
        viewer.get("sample_rate"),
    )

    if sample_interval_ms is None:
        sample_interval_us = _first_number(
            binary.get("sample_interval_us"),
            viewer.get("sample_interval_us"),
            trace.get("sample_interval_us"),
        )
        if sample_interval_us is not None:
            sample_interval_ms = sample_interval_us / 1000.0

    sample_count = (
        metadata.get("sample_count")
        or zarr_metadata.get("sample_count")
        or (shape[-1] if isinstance(shape, list) and shape else None)
    )

    trace_count = (
        metadata.get("trace_count")
        or zarr_metadata.get("trace_count")
        or viewer.get("trace_count")
    )

    inline_range = metadata.get("inline_range")
    if inline_range is None and trace.get("inline_min_sampled") is not None and trace.get("inline_max_sampled") is not None:
        inline_range = [trace.get("inline_min_sampled"), trace.get("inline_max_sampled")]

    crossline_range = metadata.get("crossline_range")
    if crossline_range is None and trace.get("crossline_min_sampled") is not None and trace.get("crossline_max_sampled") is not None:
        crossline_range = [trace.get("crossline_min_sampled"), trace.get("crossline_max_sampled")]

    sample_range_ms = metadata.get("sample_range_ms") or metadata.get("time_range_ms")
    if sample_range_ms is None and sample_interval_ms is not None and sample_count:
        # Use zero-based display range for viewer geometry. Textual-header Z ranges remain evidence only.
        sample_range_ms = [0.0, float(sample_interval_ms) * (int(sample_count) - 1)]

    return {
        "shape": shape,
        "axis_order": zarr_metadata.get("axis_order") or metadata.get("axis_order") or viewer.get("axis_order"),
        "sample_interval_ms": sample_interval_ms,
        "sample_rate_ms": sample_interval_ms,
        "trace_count": trace_count,
        "sample_count": sample_count,
        "inline_range": inline_range,
        "crossline_range": crossline_range,
        "sample_range_ms": sample_range_ms,
        "time_range_ms": sample_range_ms,
        "geometry_status": metadata.get("geometry_source") or zarr_metadata.get("geometry_source") or "unknown",
    }


def _source(volume: Dict[str, Any]) -> Dict[str, Any]:
    metadata = volume.get("metadata") or {}
    source = volume.get("source") or {}

    source_type = source.get("source_type") or metadata.get("source_type") or "manual_upload"
    source_type_text = str(source_type or "").strip() or "manual_upload"
    source_type_normalized = source_type_text.lower()

    repository_id = source.get("repository_id") or metadata.get("repository_id")
    package_id = source.get("package_id") or metadata.get("package_id")
    line_id = source.get("line_id") or metadata.get("line_id")
    segy_file_id = source.get("segy_file_id") or metadata.get("segy_file_id")

    manual_upload_types = {
        "manual_upload",
        "manual_upload_package",
        "uploaded_file",
        "direct_upload",
        "local_upload",
    }
    repository_backed_types = {
        "external_repository",
        "source_repository",
        "source_intake_repository",
        "repository",
    }

    is_manual_upload = source_type_normalized in manual_upload_types
    repository_required = source_type_normalized in repository_backed_types

    if repository_id:
        lineage_status = "repository_linked"
        lineage_message = "Source Repository lineage is linked."
    elif is_manual_upload:
        lineage_status = "manual_upload"
        lineage_message = "Manual Upload lineage; Source Repository metadata is not applicable."
    elif repository_required:
        lineage_status = "missing_repository_metadata"
        lineage_message = "Repository-backed dataset is missing Source Repository metadata."
    else:
        lineage_status = "non_repository_source"
        lineage_message = "Dataset source is not linked to a Source Repository."

    return {
        "source_type": source_type_text,
        "filename": source.get("original_filename") or metadata.get("original_filename") or volume.get("filename"),
        "repository_id": repository_id,
        "package_id": package_id,
        "line_id": line_id,
        "segy_file_id": segy_file_id,
        "package_display_name": source.get("package_display_name") or metadata.get("package_display_name"),
        "line_display_name": source.get("line_display_name") or metadata.get("line_display_name"),
        "relative_path": source.get("original_relative_path") or metadata.get("original_relative_path"),
        "conversion_status": source.get("conversion_status") or metadata.get("conversion_status"),
        "job_id": source.get("job_id") or metadata.get("job_id"),
        "lineage_status": lineage_status,
        "lineage_message": lineage_message,
        "repository_required": repository_required,
        "repository_metadata_applicable": repository_required or bool(repository_id),
    }


def _registry_json(name: str) -> Any:
    return _read_json(REGISTRY_DIR / name, [])


def _matching_documents(source: Dict[str, Any]) -> list:
    repository_id = str(source.get("repository_id") or "").strip()
    if not repository_id:
        return []

    documents = _registry_json("documents.json")
    if not isinstance(documents, list):
        return []

    package_id = str(source.get("package_id") or "").strip().lower()
    line_id = str(source.get("line_id") or "").strip().lower()
    segy_file_id = str(source.get("segy_file_id") or "").strip().lower()
    rel = str(source.get("relative_path") or "").strip()
    package_token = rel.split("/")[0].strip().lower() if "/" in rel else ""
    package_display = str(source.get("package_display_name") or "").strip().lower()
    tokens = [x for x in {package_token, package_display} if x]

    matched = []

    for doc in documents:
        if not isinstance(doc, dict):
            continue

        if str(doc.get("repository_id") or "").strip() != repository_id:
            continue

        doc_package_id = str(doc.get("package_id") or "").strip().lower()
        doc_line_id = str(doc.get("line_id") or "").strip().lower()
        doc_segy_file_id = str(doc.get("segy_file_id") or "").strip().lower()
        doc_rel = str(doc.get("relative_path") or "").strip().lower()
        filename = str(doc.get("filename") or "").strip().lower()

        if package_id and doc_package_id and doc_package_id == package_id:
            matched.append(doc)
            continue

        if line_id and doc_line_id and doc_line_id == line_id:
            matched.append(doc)
            continue

        if segy_file_id and doc_segy_file_id and doc_segy_file_id == segy_file_id:
            matched.append(doc)
            continue

        for token in tokens:
            if doc_rel == token or doc_rel.startswith(f"{token}/") or filename.startswith(token) or token in filename:
                matched.append(doc)
                break

    return matched


def _text_readability(text: Optional[str]) -> Dict[str, Any]:
    if not text:
        return {
            "readable": False,
            "replacement_char_count": 0,
            "replacement_char_ratio": 0.0,
        }

    replacement_count = text.count("\ufffd")
    total = max(len(text), 1)
    ratio = replacement_count / total

    # Conservative threshold: if many replacement characters appear, the sidecar
    # exists but should not be treated as human-readable evidence.
    return {
        "readable": ratio < 0.02,
        "replacement_char_count": replacement_count,
        "replacement_char_ratio": ratio,
    }

def _warnings(source: Dict[str, Any], headers: Dict[str, Any], geometry: Dict[str, Any], documents: list) -> list:
    warnings = []

    if headers.get("text_header_available") and headers.get("text_header_readable") is False:
        warnings.append("Textual header sidecar exists but appears unreadable or incorrectly decoded.")

    if not headers.get("binary_header_available"):
        warnings.append("Binary header sidecar is missing.")

    if not headers.get("trace_header_summary_available"):
        warnings.append("Trace header summary sidecar is missing.")

    if geometry.get("geometry_status") in (None, "", "unknown", "fallback"):
        warnings.append("Geometry status is unknown or fallback-derived.")

    # E2E-1B_METADATA_WARNING_SEMANTICS:
    # Lack of Source Repository metadata is a warning only for datasets whose
    # lineage claims repository-backed intake. Manual Upload is a valid MSI
    # lineage and must not be presented as a repository-metadata defect.
    if source.get("repository_required") and not source.get("repository_id"):
        warnings.append("Repository-backed dataset is missing Source Repository metadata.")

    if not documents:
        warnings.append("No supporting documents linked to this dataset.")

    return warnings



def build_metadata_summary(volume_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    requested_volume_id = str(volume_id or "").strip()
    physical_volume_id = _physical_volume_id_from_msi_representation(requested_volume_id)
    lookup_volume_id = physical_volume_id or requested_volume_id

    volume = _find_volume(lookup_volume_id)
    if not volume:
        return None, "Volume not found"

    sidecars = _sidecar_paths(lookup_volume_id, volume)

    viewer_metadata = _read_json(sidecars["viewer_metadata"], None)
    binary_header = _read_json(sidecars["binary_header"], None)
    trace_header_summary = _read_json(sidecars["trace_header_summary"], None)
    text_header = _read_text(sidecars["text_header"])
    normalized_metadata = _read_json(sidecars["normalized_metadata"], None)

    # Metadata Summary must use the same resolved header evidence as the Info Page.
    # This is important for MSI/managed Zarr rows where the visible dataset id may
    # differ from the physical volume id and where source-intake header evidence is
    # attached by the /info resolver.
    resolved_info = _resolved_info_for_summary(requested_volume_id, lookup_volume_id)

    if isinstance(resolved_info.get("viewer_metadata"), dict):
        viewer_metadata = resolved_info.get("viewer_metadata")

    if isinstance(resolved_info.get("binary_header"), dict):
        binary_header = resolved_info.get("binary_header")

    if isinstance(resolved_info.get("trace_header_summary"), dict):
        trace_header_summary = resolved_info.get("trace_header_summary")

    if isinstance(resolved_info.get("text_header"), str) and resolved_info.get("text_header"):
        text_header = resolved_info.get("text_header")

    resolved_sidecars = resolved_info.get("sidecars") if isinstance(resolved_info.get("sidecars"), dict) else {}

    source = _source(volume)
    geometry = _geometry(volume, viewer_metadata, binary_header, trace_header_summary)

    text_readability = _text_readability(text_header)

    sidecar_paths = {key: str(path) for key, path in sidecars.items()}
    for key, value in resolved_sidecars.items():
        if isinstance(value, dict):
            path_value = value.get("path") or value.get("filename")
            if path_value:
                sidecar_paths[key] = str(path_value)

    headers = {
        "viewer_metadata_available": viewer_metadata is not None,
        "text_header_available": text_header is not None,
        "text_header_readable": text_readability["readable"],
        "text_header_replacement_char_count": text_readability["replacement_char_count"],
        "text_header_replacement_char_ratio": text_readability["replacement_char_ratio"],
        "binary_header_available": binary_header is not None,
        "trace_header_summary_available": trace_header_summary is not None,
        "normalized_metadata_available": normalized_metadata is not None,
        "sidecar_paths": sidecar_paths,
        "text_header_preview": text_header[:1200] if text_header else None,
        "binary_header_summary": binary_header if isinstance(binary_header, dict) else None,
        "trace_header_summary": trace_header_summary if isinstance(trace_header_summary, dict) else None,
        "header_evidence_sources": resolved_info.get("header_evidence_sources") or {},
    }

    supporting_documents = _matching_documents(source)

    resolution_status = {
        "name": "registry_confirmed" if source.get("line_display_name") or source.get("package_display_name") else "filename_inferred",
        "geometry": geometry.get("geometry_status") or "unknown",
        "sample_rate": "binary_or_viewer_metadata" if geometry.get("sample_interval_ms") is not None else "unknown",
    }

    summary = {
        "volume_id": requested_volume_id,
        "physical_volume_id": physical_volume_id,
        "dataset_type": _infer_dataset_type(volume),
        "display_name": _display_name(lookup_volume_id, volume),
        "source": source,
        "geometry": geometry,
        "headers": headers,
        "documents": {
            "supporting_documents": supporting_documents,
            "supporting_links": [],
        },
        "warnings": _warnings(source, headers, geometry, supporting_documents),
        "resolution_status": resolution_status,
    }

    summary["metadata_quality"] = build_metadata_quality_report(summary)

    return summary, None
