from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import HTTPException

from app.services.repository_registry_service import REGISTRY_DIR
from app.storage.service import is_endrepo_zarr_url, resolve_endrepo_zarr_url_path


ZARR_DIR = os.environ.get("ZARR_DIR", "./data/zarr")
VOLUMES_JSON = os.environ.get("VOLUMES_JSON", "./data/volumes.json")
SEGY_INDEX_DIR = Path(__file__).resolve().parents[2] / "data" / "segy_index"


def load_volumes() -> Dict[str, Any]:
    if os.path.exists(VOLUMES_JSON):
        with open(VOLUMES_JSON, "r") as f:
            return json.load(f)
    return {}


def save_volumes(volumes: Dict[str, Any]) -> None:
    with open(VOLUMES_JSON, "w") as f:
        json.dump(volumes, f)




def _is_msi_representation_id(volume_id: str | None) -> bool:
    return str(volume_id or "").strip().startswith("msi_repr:")


def _reject_msi_legacy_write(volume_id: str | None, action: str) -> None:
    if _is_msi_representation_id(volume_id):
        raise ValueError(
            f"Refusing legacy volume {action} for MSI representation id. "
            "Use MSI lifecycle/metadata endpoints instead."
        )


def infer_dataset_type(volume: Dict[str, Any]) -> str:
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


def normalize_volume_record(volume: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(volume)
    normalized["dataset_type"] = infer_dataset_type(normalized)
    return normalized


def list_volumes() -> List[Dict[str, Any]]:
    volumes = load_volumes()
    return [normalize_volume_record(volume) for volume in volumes.values()]


def get_volume_metadata(volume_id: str) -> Dict[str, Any]:
    volumes = load_volumes()
    if volume_id not in volumes:
        raise HTTPException(status_code=404, detail="Volume not found")

    volume = normalize_volume_record(volumes[volume_id])
    return volume["metadata"]


def update_volume(volume_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    _reject_msi_legacy_write(volume_id, "update")
    volumes = load_volumes()

    if volume_id not in volumes:
        raise HTTPException(status_code=404, detail="Volume not found")

    allowed_fields = {
        "display_name",
        "hidden",
        "description",
    }

    for key, value in updates.items():
        if key in allowed_fields:
            volumes[volume_id][key] = value

    save_volumes(volumes)
    return volumes[volume_id]



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def invalidate_source_segy_for_deleted_volume(volume_id: str, zarr_url: str | None = None) -> Dict[str, Any]:
    """
    Invalidate external source SEG-Y conversion state when its Managed Data
    converted dataset is deleted.

    The source SEG-Y record remains available for retry/reconversion.
    """
    segy_path = REGISTRY_DIR / "segy_files.json"

    if not segy_path.exists():
        return {"matched": 0, "updated": 0}

    try:
        rows = json.loads(segy_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"matched": 0, "updated": 0, "error": f"Could not read segy_files.json: {exc}"}

    if not isinstance(rows, list):
        return {"matched": 0, "updated": 0, "error": "segy_files.json is not a list"}

    matched = 0
    updated = 0
    now = _utc_now_iso()
    reason = "managed_zarr_deleted_reconvert_available"

    for row in rows:
        row_volume_id = str(row.get("volume_id") or "")
        row_zarr_url = str(row.get("zarr_url") or "")

        matches_volume = row_volume_id == str(volume_id)
        matches_zarr = bool(zarr_url and row_zarr_url == str(zarr_url))

        if not (matches_volume or matches_zarr):
            continue

        matched += 1

        needs_update = (
            row.get("conversion_status") != "reconvert_required"
            or row.get("conversion_error") is not None
            or row.get("volume_id") is not None
            or row.get("zarr_url") is not None
            or row.get("conversion_state_reason") != reason
        )

        if needs_update:
            row["conversion_status"] = "reconvert_required"
            row["conversion_error"] = None
            row["volume_id"] = None
            row["zarr_url"] = None
            row["conversion_state_reason"] = reason
            row["conversion_state_authoritative"] = True
            row["updated_at"] = now
            updated += 1

    if updated:
        tmp = segy_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(segy_path)

    return {
        "matched": matched,
        "updated": updated,
    }


def delete_volume(volume_id: str) -> Dict[str, Any]:
    _reject_msi_legacy_write(volume_id, "delete")
    volumes = load_volumes()

    if volume_id not in volumes:
        raise HTTPException(status_code=404, detail="Volume not found")

    volume = volumes[volume_id]
    zarr_url = volume.get("zarr_url")

    deleted_paths = []

    if zarr_url and zarr_url.startswith("/data/zarr/"):
        zarr_name = zarr_url.replace("/data/zarr/", "", 1)
        zarr_path = Path(ZARR_DIR) / zarr_name

        if zarr_path.exists():
            shutil.rmtree(zarr_path)
            deleted_paths.append(str(zarr_path))

        for sidecar in Path(ZARR_DIR).glob(zarr_name + ".*"):
            if sidecar.exists():
                sidecar.unlink()
                deleted_paths.append(str(sidecar))
    elif zarr_url and is_endrepo_zarr_url(zarr_url):
        # EndRepo artifact deletion is intentionally not implemented in this block.
        # The registry row may be removed, but bucket artifact lifecycle remains
        # backend-managed by a later explicit storage/MSI lifecycle block.
        pass

    del volumes[volume_id]
    save_volumes(volumes)

    source_segy_invalidation = invalidate_source_segy_for_deleted_volume(
        volume_id=volume_id,
        zarr_url=zarr_url,
    )

    return {
        "deleted": True,
        "volume_id": volume_id,
        "deleted_paths": deleted_paths,
        "source_segy_invalidation": source_segy_invalidation,
    }


def volume_sidecar_paths(volume: Dict[str, Any]) -> Dict[str, Path]:
    zarr_url = volume.get("zarr_url", "")

    if zarr_url.startswith("/data/zarr/"):
        zarr_name = zarr_url.replace("/data/zarr/", "", 1)
        base = Path(ZARR_DIR) / zarr_name
    elif is_endrepo_zarr_url(zarr_url):
        base = resolve_endrepo_zarr_url_path(zarr_url)
    else:
        raise HTTPException(status_code=400, detail="Volume does not have a valid Zarr URL")

    return {
        "viewer_metadata": Path(str(base) + ".viewer_metadata.json"),
        "text_header": Path(str(base) + ".segy_text_header.txt"),
        "binary_header": Path(str(base) + ".segy_binary_header.json"),
        "trace_header_summary": Path(str(base) + ".trace_header_summary.json"),
    }



def _safe_json_load(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _source_header_tokens_from_volume(volume: Dict[str, Any]) -> set[str]:
    tokens: set[str] = set()

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text:
            tokens.add(text)

    metadata = volume.get("metadata") if isinstance(volume.get("metadata"), dict) else {}
    geometry_qaqc = volume.get("geometry_qaqc") if isinstance(volume.get("geometry_qaqc"), dict) else metadata.get("geometry_qaqc")
    if not isinstance(geometry_qaqc, dict):
        geometry_qaqc = {}

    for value in [
        volume.get("id"),
        volume.get("filename"),
        volume.get("display_name"),
        metadata.get("source_candidate_id"),
        metadata.get("source_segy_file_id"),
        metadata.get("source_path"),
        metadata.get("source_relative_path"),
        geometry_qaqc.get("candidate_id"),
        geometry_qaqc.get("source_path"),
    ]:
        add(value)

    source = geometry_qaqc.get("source") if isinstance(geometry_qaqc.get("source"), dict) else {}
    for value in [
        source.get("path"),
        source.get("relative_path"),
        source.get("filename"),
        source.get("repository_id"),
    ]:
        add(value)

    return tokens


def _find_source_intake_index_for_volume(volume: Dict[str, Any]) -> tuple[Path | None, Dict[str, Any] | None]:
    tokens = _source_header_tokens_from_volume(volume)
    if not tokens or not SEGY_INDEX_DIR.exists():
        return None, None

    filename_tokens = {Path(token).name for token in tokens if token}
    strong_tokens = {token for token in tokens if token.startswith("segy_") or "/" in token or token.endswith((".sgy", ".segy", ".SGY", ".SEGY"))}

    for index_path in sorted(SEGY_INDEX_DIR.glob("*/segy_index.json")):
        payload = _safe_json_load(index_path)
        if not isinstance(payload, dict):
            continue

        values = {
            str(payload.get("dataset_id") or ""),
            str(payload.get("source_path") or ""),
            str(payload.get("source_file_name") or ""),
            str(payload.get("source_relative_path") or ""),
        }

        payload_text = json.dumps(payload, sort_keys=True)

        if any(token and token in values for token in tokens):
            return index_path.parent, payload

        if any(token and token in payload_text for token in strong_tokens):
            return index_path.parent, payload

        source_file_name = str(payload.get("source_file_name") or "").strip()
        if source_file_name and source_file_name in filename_tokens:
            return index_path.parent, payload

    return None, None


def _trace_summary_from_index(index_summary: Dict[str, Any], geometry_qaqc: Dict[str, Any]) -> Dict[str, Any]:
    selected = geometry_qaqc.get("selected_candidate") or geometry_qaqc.get("selected_geometry") or {}
    return {
        "source": "source_intake_index",
        "dataset_id": index_summary.get("dataset_id"),
        "source_path": index_summary.get("source_path"),
        "trace_count": index_summary.get("trace_count"),
        "sample_count": index_summary.get("sample_count"),
        "sample_interval_us": index_summary.get("sample_interval_us"),
        "sample_interval_ms": index_summary.get("sample_interval_ms"),
        "inline_header_byte": index_summary.get("inline_header_byte") or selected.get("inline_byte"),
        "crossline_header_byte": index_summary.get("crossline_header_byte") or selected.get("crossline_byte"),
        "inline_count": index_summary.get("inline_count"),
        "crossline_count": index_summary.get("crossline_count"),
        "inline_min": index_summary.get("inline_min"),
        "inline_max": index_summary.get("inline_max"),
        "crossline_min": index_summary.get("crossline_min"),
        "crossline_max": index_summary.get("crossline_max"),
        "valid_trace_header_count": index_summary.get("valid_trace_header_count"),
        "invalid_trace_header_count": index_summary.get("invalid_trace_header_count"),
        "geometry_source": index_summary.get("geometry_source"),
        "geometry_qaqc_status": geometry_qaqc.get("status"),
        "geometry_qaqc_summary": geometry_qaqc.get("summary"),
        "selected_candidate": selected,
    }


def _trace_summary_from_geometry_qaqc(geometry_qaqc: Dict[str, Any]) -> Dict[str, Any] | None:
    if not isinstance(geometry_qaqc, dict) or not geometry_qaqc:
        return None

    segy = geometry_qaqc.get("segy") if isinstance(geometry_qaqc.get("segy"), dict) else {}
    selected = geometry_qaqc.get("selected_candidate") or geometry_qaqc.get("selected_geometry") or {}
    header_stats = geometry_qaqc.get("header_stats") if isinstance(geometry_qaqc.get("header_stats"), dict) else {}

    return {
        "source": "source_intake_geometry_qaqc",
        "candidate_id": geometry_qaqc.get("candidate_id"),
        "source_path": geometry_qaqc.get("source_path"),
        "trace_count": segy.get("trace_count"),
        "sample_count": segy.get("sample_count"),
        "sample_min": segy.get("sample_min"),
        "sample_max": segy.get("sample_max"),
        "inline_header_byte": selected.get("inline_byte"),
        "crossline_header_byte": selected.get("crossline_byte"),
        "selected_candidate": selected,
        "header_stats": header_stats,
        "geometry_qaqc_status": geometry_qaqc.get("status"),
        "geometry_qaqc_summary": geometry_qaqc.get("summary"),
    }


def _attach_source_intake_header_fallback(info: Dict[str, Any]) -> Dict[str, Any]:
    volume = info.get("volume") if isinstance(info.get("volume"), dict) else {}
    metadata = volume.get("metadata") if isinstance(volume.get("metadata"), dict) else {}
    geometry_qaqc = volume.get("geometry_qaqc") if isinstance(volume.get("geometry_qaqc"), dict) else metadata.get("geometry_qaqc")
    if not isinstance(geometry_qaqc, dict):
        geometry_qaqc = {}

    index_dir, index_summary = _find_source_intake_index_for_volume(volume)
    header_sources = dict(info.get("header_evidence_sources") or {})
    sidecars = dict(info.get("sidecars") or {})

    if index_dir and isinstance(index_summary, dict):
        text_path = index_dir / "segy_text_header.txt"
        binary_path = index_dir / "segy_binary_header.json"

        if info.get("text_header") is None and text_path.exists():
            info["text_header"] = text_path.read_text(encoding="utf-8", errors="replace")
            sidecars["text_header"] = {
                "exists": True,
                "filename": text_path.name,
                "path": str(text_path),
                "source": "source_intake_index",
            }
            header_sources["text_header"] = "source_intake_index"

        if info.get("binary_header") is None and binary_path.exists():
            binary_header = _safe_json_load(binary_path)
            if isinstance(binary_header, dict):
                info["binary_header"] = binary_header
                sidecars["binary_header"] = {
                    "exists": True,
                    "filename": binary_path.name,
                    "path": str(binary_path),
                    "source": "source_intake_index",
                }
                header_sources["binary_header"] = "source_intake_index"

        if info.get("trace_header_summary") is None:
            info["trace_header_summary"] = _trace_summary_from_index(index_summary, geometry_qaqc)
            sidecars["trace_header_summary"] = {
                "exists": True,
                "filename": "segy_index.json",
                "path": str(index_dir / "segy_index.json"),
                "source": "source_intake_index",
            }
            header_sources["trace_header_summary"] = "source_intake_index"

    if info.get("trace_header_summary") is None:
        trace_summary = _trace_summary_from_geometry_qaqc(geometry_qaqc)
        if trace_summary:
            info["trace_header_summary"] = trace_summary
            sidecars["trace_header_summary"] = {
                "exists": True,
                "filename": "geometry_qaqc",
                "source": "source_intake_geometry_qaqc",
            }
            header_sources["trace_header_summary"] = "source_intake_geometry_qaqc"

    if header_sources:
        info["header_evidence_sources"] = header_sources
        info["sidecars"] = sidecars

    return info


def get_volume_info(volume_id: str) -> Dict[str, Any]:
    volumes = load_volumes()

    if volume_id not in volumes:
        raise HTTPException(status_code=404, detail="Volume not found")

    volume = volumes[volume_id]
    sidecars = volume_sidecar_paths(volume)

    info: Dict[str, Any] = {
        "volume": volume,
        "sidecars": {
            key: {
                "exists": path.exists(),
                "filename": path.name,
            }
            for key, path in sidecars.items()
        },
    }

    viewer_metadata_path = sidecars["viewer_metadata"]
    if viewer_metadata_path.exists():
        with open(viewer_metadata_path, "r") as f:
            info["viewer_metadata"] = json.load(f)
    else:
        info["viewer_metadata"] = None

    binary_header_path = sidecars["binary_header"]
    if binary_header_path.exists():
        with open(binary_header_path, "r") as f:
            info["binary_header"] = json.load(f)
    else:
        info["binary_header"] = None

    trace_summary_path = sidecars["trace_header_summary"]
    if trace_summary_path.exists():
        with open(trace_summary_path, "r") as f:
            info["trace_header_summary"] = json.load(f)
    else:
        info["trace_header_summary"] = None

    text_header_path = sidecars["text_header"]
    if text_header_path.exists():
        info["text_header"] = text_header_path.read_text(encoding="utf-8", errors="replace")
    else:
        info["text_header"] = None

    return _attach_source_intake_header_fallback(info)
