from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import shutil
from pathlib import Path

from app.services.segy_index_service import SegyIndexService, SEGY_INDEX_DIR
from app.metadata import build_indexed_segy_normalized_metadata


def _strip_indexed_prefix(dataset_id: str) -> str:
    prefix = "indexed-segy-"
    if dataset_id.startswith(prefix):
        return dataset_id[len(prefix):]
    return dataset_id


def _record_length_ms(index: Dict[str, Any]) -> Optional[float]:
    sample_count = index.get("sample_count")
    sample_interval_ms = index.get("sample_interval_ms")
    if isinstance(sample_count, int) and isinstance(sample_interval_ms, (int, float)):
        return (sample_count - 1) * float(sample_interval_ms)
    return None


def _time_range_ms(index: Dict[str, Any]) -> Optional[List[float]]:
    end = _record_length_ms(index)
    if end is None:
        return None
    return [0, end]


def _sample_index_range(index: Dict[str, Any]) -> Optional[List[int]]:
    sample_count = index.get("sample_count")
    if isinstance(sample_count, int) and sample_count > 0:
        return [0, sample_count - 1]
    return None


def _expected_trace_positions(index: Dict[str, Any]) -> Optional[int]:
    inline_count = index.get("inline_count")
    crossline_count = index.get("crossline_count")
    if isinstance(inline_count, int) and isinstance(crossline_count, int):
        return inline_count * crossline_count
    return None


def _missing_trace_positions(index: Dict[str, Any]) -> Optional[int]:
    expected = _expected_trace_positions(index)
    trace_count = index.get("trace_count")
    if isinstance(expected, int) and isinstance(trace_count, int):
        return expected - trace_count
    return None


def _load_index(dataset_id: str) -> Dict[str, Any]:
    clean_id = _strip_indexed_prefix(dataset_id)
    index = SegyIndexService.load_index(clean_id)
    return _enrich_index_with_sidecars(index)


def _enrich_index_with_sidecars(index: Dict[str, Any]) -> Dict[str, Any]:
    dataset_id = index.get("dataset_id")
    if not dataset_id:
        return index

    index_dir = SEGY_INDEX_DIR / dataset_id

    text_header_path = index_dir / "segy_text_header.txt"
    if text_header_path.exists() and not index.get("text_header"):
        index["text_header"] = text_header_path.read_text(encoding="utf-8", errors="replace")

    text_decode_path = index_dir / "segy_text_header_decode.json"
    if text_decode_path.exists() and not index.get("text_header_decode"):
        try:
            decode = json.loads(text_decode_path.read_text(encoding="utf-8"))
            index["text_header_decode"] = decode
            index["text_header_encoding"] = decode.get("selected_encoding")
            index["text_header_confidence"] = decode.get("confidence")
        except Exception:
            pass

    binary_header_path = index_dir / "segy_binary_header.json"
    if binary_header_path.exists() and not index.get("binary_header"):
        try:
            index["binary_header"] = json.loads(binary_header_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    if not index.get("trace_header_summary"):
        index["trace_header_summary"] = {
            "trace_count": index.get("trace_count"),
            "inline_count": index.get("inline_count"),
            "crossline_count": index.get("crossline_count"),
            "sample_count": index.get("sample_count"),
            "inline_min": index.get("inline_min"),
            "inline_max": index.get("inline_max"),
            "crossline_min": index.get("crossline_min"),
            "crossline_max": index.get("crossline_max"),
            "sample_index_range": _sample_index_range(index),
            "sample_interval_ms": index.get("sample_interval_ms"),
            "time_range_ms": _time_range_ms(index),
            "valid_trace_header_count": index.get("valid_trace_header_count"),
            "invalid_trace_header_count": index.get("invalid_trace_header_count"),
        }

    return index



def _optimized_cache_from_index(index: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return the attached optimized-cache object for an indexed SEG-Y dataset.

    DatasetRegistryService owns the managed dataset API shape. It should expose
    optimized cache availability as first-class dataset state, while leaving
    persistence ownership in SegyIndexService.
    """
    cache = index.get("optimized_cache")
    if not isinstance(cache, dict):
        cache = {}

    status = index.get("optimized_cache_status") or cache.get("status") or "not_started"

    result: Dict[str, Any] = {
        "status": status,
        **cache,
    }

    # Keep the common access fields predictable for UI consumers.
    result["status"] = status
    result.setdefault("zarr_url", cache.get("zarr_url"))
    result.setdefault("path", cache.get("path"))
    result.setdefault("job_id", cache.get("job_id") or index.get("optimized_cache_job_id"))
    result.setdefault("validated", cache.get("validated", False))
    result.setdefault("worker", cache.get("worker"))

    return result

def _canonical_dataset_from_index(index: Dict[str, Any]) -> Dict[str, Any]:
    dataset_id = index["dataset_id"]
    shape = index.get("shape")

    return {
        "dataset_id": dataset_id,
        "id": dataset_id,
        "legacy_volume_id": f"indexed-segy-{dataset_id}",
        "display_name": index.get("display_name") or f"{_short_name(index)} — Indexed SEG-Y mode",
        "filename": index.get("source_file_name") or dataset_id,
        "hidden": bool(index.get("hidden", False)),
        "description": index.get("description"),
        "source_path": index.get("source_path"),
        "dataset_type": "3d_volume" if index.get("is_3d") else "unknown",
        "source_format": "segy",
        "read_mode": "indexed_segy",
        "storage_status": "indexed",
        "optimized_cache_status": index.get("optimized_cache_status", "not_started"),
        "optimized_cache": _optimized_cache_from_index(index),
        "metadata_status": "provisional",
        "evidence_status": "headers_only",
        "zarr_url": f"indexed-segy://{dataset_id}",
        "shape": shape,
        "axis_order": index.get("axis_order", ["inline", "crossline", "sample"]),
        "sample_interval_ms": index.get("sample_interval_ms"),
        "sample_count": index.get("sample_count"),
        "trace_count": index.get("trace_count"),
        "inline_count": index.get("inline_count"),
        "crossline_count": index.get("crossline_count"),
        "inline_range": _range(index.get("inline_min"), index.get("inline_max")),
        "crossline_range": _range(index.get("crossline_min"), index.get("crossline_max")),
        "sample_index_range": _sample_index_range(index),
        "time_range_ms": _time_range_ms(index),
        "info_url": f"/api/datasets/{dataset_id}/info",
        "slice_url": f"/api/datasets/{dataset_id}/slice",
        "metadata_summary_url": f"/api/datasets/{dataset_id}/metadata-summary",
        "metadata_completeness_url": f"/api/datasets/{dataset_id}/metadata-completeness",
        "metadata": _normalized_metadata_from_index(index),
    }



def _optimized_cache_is_available(index: Dict[str, Any]) -> bool:
    cache = index.get("optimized_cache")
    if not isinstance(cache, dict):
        cache = {}

    status = index.get("optimized_cache_status") or cache.get("status")
    zarr_url = cache.get("zarr_url")
    validated = bool(cache.get("validated"))

    return bool(status in {"available", "ready", "converted"} and zarr_url and validated)


def _normalize_indexed_metadata_for_optimized_cache(
    index: Dict[str, Any],
    normalized: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Correct indexed SEG-Y normalized metadata when an optimized cache is available.

    The normalized metadata builder may initially describe an indexed preview before
    the optimized cache exists. Once the cache is available and validated, the
    metadata should no longer report optimized_zarr_cache as missing or incomplete.
    """
    if not _optimized_cache_is_available(index):
        return normalized

    result = dict(normalized)

    conversion = dict(result.get("conversion") or {})
    conversion["optimized_cache_status"] = "available"
    result["conversion"] = conversion

    evidence = dict(result.get("evidence") or {})
    sources = dict(evidence.get("sources") or {})
    sources["optimized_zarr_cache"] = True
    evidence["sources"] = sources
    result["evidence"] = evidence

    quality = dict(result.get("quality") or {})

    missing_fields = quality.get("missing_fields")
    if isinstance(missing_fields, list):
        quality["missing_fields"] = [
            item for item in missing_fields if item != "optimized_zarr_cache"
        ]

    warnings = quality.get("warnings")
    if isinstance(warnings, list):
        quality["warnings"] = [
            item for item in warnings
            if "Optimized Zarr cache has not been completed" not in str(item)
        ]

    quality["technical_readiness"] = "indexed_optimized_cache_available"
    result["quality"] = quality

    return result

def _short_name(index: Dict[str, Any]) -> str:
    name = index.get("source_file_name") or index.get("dataset_id") or "Indexed SEG-Y"
    if name.startswith("Poststack_Final_Migration-Full_"):
        name = name.replace("Poststack_Final_Migration-Full_", "")
    if "-Final_Migration-Full-" in name:
        return name.split("-Final_Migration-Full-")[0]
    return Path(name).stem


def _range(a: Any, b: Any) -> Optional[List[Any]]:
    if a is None or b is None:
        return None
    return [a, b]


def _normalized_metadata_from_index(index: Dict[str, Any]) -> Dict[str, Any]:
    normalized = build_indexed_segy_normalized_metadata(index)
    return _normalize_indexed_metadata_for_optimized_cache(index, normalized)


def get_normalized_metadata(dataset_id: str) -> Dict[str, Any]:
    index = _load_index(dataset_id)
    normalized = _normalize_indexed_metadata_for_optimized_cache(
        index,
        build_indexed_segy_normalized_metadata(index),
    )
    clean_id = _strip_indexed_prefix(dataset_id)

    return {
        "dataset_id": clean_id,
        "volume_id": f"indexed-segy-{clean_id}",
        "metadata_status": normalized.get("metadata_status", "provisional"),
        "evidence_status": normalized.get("evidence_status", "headers_only"),
        "source": "indexed_segy_headers",
        "normalized_metadata": normalized,
        "warnings": normalized.get("quality", {}).get("warnings", []),
    }


def list_indexed_datasets() -> List[Dict[str, Any]]:
    datasets: List[Dict[str, Any]] = []
    if not SEGY_INDEX_DIR.exists():
        return datasets

    for child in sorted(SEGY_INDEX_DIR.iterdir()):
        if not child.is_dir():
            continue
        try:
            index = SegyIndexService.load_index(child.name)
            datasets.append(_canonical_dataset_from_index(index))
        except Exception:
            continue

    return datasets


def get_dataset(dataset_id: str) -> Dict[str, Any]:
    index = _load_index(dataset_id)
    return _canonical_dataset_from_index(index)
def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _data_root() -> Path:
    return _backend_root() / "data"


def _safe_delete_app_owned_path(path_value: Any) -> Optional[str]:
    """
    Delete only paths owned by the app under seismic-viewer-backend/data.

    This deliberately refuses to delete source SEG-Y files outside backend/data.
    """
    if not path_value:
        return None

    candidate = Path(str(path_value))
    if not candidate.is_absolute():
        candidate = _backend_root() / candidate

    try:
        resolved = candidate.resolve()
        data_root = _data_root().resolve()
    except Exception:
        return None

    if resolved != data_root and data_root not in resolved.parents:
        return None

    if not candidate.exists():
        return None

    if candidate.is_dir():
        shutil.rmtree(candidate)
    else:
        candidate.unlink()

    return str(candidate)


def _delete_optimized_cache_artifacts(index: Dict[str, Any]) -> List[str]:
    deleted_paths: List[str] = []

    cache = index.get("optimized_cache")
    if not isinstance(cache, dict):
        cache = {}

    # Main optimized Zarr cache folder.
    deleted = _safe_delete_app_owned_path(cache.get("path"))
    if deleted:
        deleted_paths.append(deleted)

    # Explicit sidecars.
    sidecars = cache.get("sidecars")
    if isinstance(sidecars, dict):
        for sidecar_path in sidecars.values():
            deleted = _safe_delete_app_owned_path(sidecar_path)
            if deleted:
                deleted_paths.append(deleted)

    # Defensive sidecar cleanup by cache path stem, still app-owned only.
    cache_path = cache.get("path")
    if cache_path:
        p = Path(str(cache_path))
        zarr_name = p.name
        zarr_dir = _data_root() / "zarr"
        if zarr_name and zarr_dir.exists():
            for sidecar in zarr_dir.glob(zarr_name + ".*"):
                deleted = _safe_delete_app_owned_path(sidecar)
                if deleted:
                    deleted_paths.append(deleted)

    return sorted(set(deleted_paths))



def delete_dataset_optimized_cache(dataset_id: str) -> Dict[str, Any]:
    """
    Delete only the optimized Fast Zarr Cache for an indexed SEG-Y dataset.

    Ownership boundary:
    - Deletes optimized-cache artifacts using the existing app-owned safe-delete helper.
    - Preserves the indexed preview directory and segy_index.json.
    - Clears optimized-cache metadata from the index record.
    - Preserves the original source SEG-Y.
    """
    clean_id = _strip_indexed_prefix(dataset_id)
    index_dir = SEGY_INDEX_DIR / clean_id
    index_path = index_dir / "segy_index.json"

    if not index_path.exists():
        raise FileNotFoundError(f"Indexed dataset not found: {clean_id}")

    index = _load_index(clean_id)
    display_name = index.get("display_name") or index.get("source_file_name") or clean_id

    deleted_paths = _delete_optimized_cache_artifacts(index)

    updated_index = SegyIndexService.update_index(clean_id, {
        "optimized_cache": {},
        "optimized_cache_status": "not_built",
        "optimized_cache_job_id": None,
    })

    return {
        "deleted": True,
        "dataset_id": clean_id,
        "display_name": display_name,
        "deleted_paths": sorted(set(deleted_paths)),
        "index_preserved": str(index_dir),
        "message": "Fast Zarr Cache deleted. Indexed SEG-Y preview was preserved.",
        "dataset": _canonical_dataset_from_index(_enrich_index_with_sidecars(updated_index)),
    }


def delete_dataset(dataset_id: str) -> Dict[str, Any]:
    """
    Deterministically delete an indexed SEG-Y managed dataset.

    Ownership boundary:
    - Indexed dataset registry is the SEG-Y index directory:
      data/segy_index/<dataset_id>/
    - Optimized cache artifacts are app-owned outputs under backend/data.
    - Original source SEG-Y is preserved.

    This is intentionally NOT a generic JSON search.
    """
    clean_id = _strip_indexed_prefix(dataset_id)
    index_dir = SEGY_INDEX_DIR / clean_id
    index_path = index_dir / "segy_index.json"

    if not index_path.exists():
        raise FileNotFoundError(f"Indexed dataset not found: {clean_id}")

    index = _load_index(clean_id)
    source_path = index.get("source_path")
    display_name = index.get("display_name") or index.get("source_file_name") or clean_id

    deleted_paths = _delete_optimized_cache_artifacts(index)

    # Remove the deterministic indexed dataset registry directory.
    deleted_index_dir = None
    if index_dir.exists():
        shutil.rmtree(index_dir)
        deleted_index_dir = str(index_dir)
        deleted_paths.append(deleted_index_dir)

    return {
        "deleted": True,
        "dataset_id": clean_id,
        "legacy_volume_id": f"indexed-segy-{clean_id}",
        "display_name": display_name,
        "deleted_index_dir": deleted_index_dir,
        "deleted_paths": sorted(set(deleted_paths)),
        "source_path_preserved": source_path,
        "message": "Indexed SEG-Y dataset deleted. Original source SEG-Y was preserved.",
    }





def update_dataset(dataset_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update safe mutable indexed-dataset fields.

    Indexed dataset persistence lives in segy_index.json.
    SegyIndexService owns the write boundary.
    DatasetRegistryService owns the canonical API shape.
    """
    clean_id = _strip_indexed_prefix(dataset_id)

    allowed = {"hidden", "display_name", "description"}
    safe_updates: Dict[str, Any] = {}

    for key, value in updates.items():
        if key not in allowed:
            continue

        if key == "hidden":
            safe_updates[key] = bool(value)
        elif key in {"display_name", "description"}:
            safe_updates[key] = str(value).strip() if value is not None else None

    if not safe_updates:
        return get_dataset(clean_id)

    updated_index = SegyIndexService.update_index(clean_id, safe_updates)
    return _canonical_dataset_from_index(_enrich_index_with_sidecars(updated_index))


def get_dataset_info(dataset_id: str) -> Dict[str, Any]:
    index = _load_index(dataset_id)
    dataset = _canonical_dataset_from_index(index)

    return {
        "dataset": dataset,
        "volume": {
            "id": dataset["legacy_volume_id"],
            "dataset_id": dataset["dataset_id"],
            "filename": dataset["filename"],
            "display_name": dataset["display_name"],
            "dataset_type": dataset["dataset_type"],
            "zarr_url": dataset["zarr_url"],
            "read_mode": dataset["read_mode"],
            "optimized_cache_status": dataset["optimized_cache_status"],
            "optimized_cache": dataset.get("optimized_cache"),
            "metadata": dataset["metadata"],
        },
        "metadata": dataset["metadata"],
        "text_header": index.get("text_header"),
        "text_header_decode": index.get("text_header_decode"),
        "binary_header": index.get("binary_header"),
        "trace_header_summary": index.get("trace_header_summary"),
        "conversion_info": {
            "read_mode": "indexed_segy",
            "source_format": "SEG-Y",
            "target_format": "indexed_segy_preview",
            "optimized_cache_status": index.get("optimized_cache_status", "not_started"),
            "optimized_cache": _optimized_cache_from_index(index),
            "geometry_source": "indexed_segy_headers",
            "input_trace_count": index.get("trace_count"),
            "expected_trace_positions": _expected_trace_positions(index),
            "missing_trace_positions": _missing_trace_positions(index),
        },
        "indexed_segy": index,
    }


def get_metadata_summary(dataset_id: str) -> Dict[str, Any]:
    index = _load_index(dataset_id)
    dataset = _canonical_dataset_from_index(index)
    metadata = dataset["metadata"]

    return {
        "dataset_id": dataset["dataset_id"],
        "display_name": dataset["display_name"],
        "dataset_type": dataset["dataset_type"],
        "metadata_status": "provisional",
        "status_label": "Indexed SEG-Y preview",
        "summary": "Fast SEG-Y index is available. Geometry and headers are available from SEG-Y evidence. Optimized Zarr cache and document validation are not complete.",
        "source": {
            "source_type": "indexed_segy",
            "source_format": "SEG-Y",
            "filename": dataset["filename"],
            "source_path": dataset["source_path"],
        },
        "geometry": metadata["geometry"],
        "headers": metadata["headers"],
        "conversion": metadata["conversion"],
        "documents": {
            "supporting_documents": [],
            "document_validation_status": "not_started",
        },
        "warnings": metadata["quality"]["warnings"],
    }


def get_metadata_completeness(dataset_id: str) -> Dict[str, Any]:
    index = _load_index(dataset_id)

    has_geometry = bool(index.get("shape")) and index.get("trace_count") is not None
    has_text = bool(index.get("text_header"))
    has_binary = bool(index.get("binary_header"))
    has_trace_summary = bool(index.get("trace_header_summary"))

    score = 0
    score += 35 if has_geometry else 0
    score += 20 if has_text else 0
    score += 15 if has_binary else 0
    score += 20 if has_trace_summary else 0
    score += 0  # documents not scanned yet
    score = min(score, 90)  # indexed-only metadata should not score as fully validated

    return {
        "dataset_id": _strip_indexed_prefix(dataset_id),
        "metadata_status": "provisional",
        "evidence_status": "headers_only",
        "completeness": {
            "percent": score,
            "status": "indexed_provisional",
            "categories": {
                "geometry": {
                    "score": 1.0 if has_geometry else 0.0,
                    "status": "available" if has_geometry else "missing",
                },
                "headers": {
                    "score": sum([has_text, has_binary, has_trace_summary]) / 3,
                    "status": "available" if has_text and has_binary and has_trace_summary else "partial",
                },
                "documents": {
                    "score": 0.0,
                    "status": "not_started",
                },
                "optimized_cache": {
                    "score": 0.0,
                    "status": index.get("optimized_cache_status", "not_started"),
                },
            },
            "missing_fields": [
                "optimized_zarr_cache",
                "document_validation",
                "business_metadata",
                "crs_validation",
            ],
            "derived_fields": [
                "shape",
                "inline_range",
                "crossline_range",
                "sample_interval_ms",
                "time_range_ms",
                "trace_count",
            ],
        },
        "summary": "Indexed SEG-Y metadata is available and usable for preview, but remains provisional until optimized cache and document validation are complete.",
    }
