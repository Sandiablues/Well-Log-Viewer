from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Literal

from app.storage.service import ENDREPO_MANAGED_ZARR_URL_PREFIX, storage_service


VALID_SORT_COLUMNS = {
    "display_name": "d.display_name COLLATE NOCASE",
    "survey_name": "coalesce(d.survey_name, d.display_name) COLLATE NOCASE",
    "line_name": "coalesce(d.line_name, d.display_name) COLLATE NOCASE",
    "volume_name": "coalesce(d.volume_name, d.display_name) COLLATE NOCASE",
    "dataset_type": "d.dataset_type COLLATE NOCASE",
    "viewer_mode": "r.viewer_mode COLLATE NOCASE",
    "representation_type": "r.representation_type COLLATE NOCASE",
    "created_at": "r.created_at",
    "updated_at": "r.updated_at",
    "loaded": "loaded",
}

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def _db_path() -> Path:
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "data" / "msi" / "msi.sqlite"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_limit(value: int | None) -> int:
    try:
        limit = int(value if value is not None else DEFAULT_LIMIT)
    except Exception:
        limit = DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


def _coerce_offset(value: int | None) -> int:
    try:
        offset = int(value if value is not None else 0)
    except Exception:
        offset = 0
    return max(0, offset)


def _storage_uri_to_zarr_url(storage_uri: str | None) -> str | None:
    text = _clean_text(storage_uri)
    if not text:
        return None

    if text.startswith("endrepo://managed/zarr/"):
        suffix = text.replace("endrepo://managed/zarr/", "", 1).strip("/")
        return f"{ENDREPO_MANAGED_ZARR_URL_PREFIX}/{suffix}"

    if text.startswith("local://zarr/"):
        name = text.replace("local://zarr/", "", 1)
        return f"/data/zarr/{name}"

    if text.startswith("/data/zarr/"):
        return text

    if text.startswith(ENDREPO_MANAGED_ZARR_URL_PREFIX.rstrip("/") + "/"):
        return text

    return None


def _volume_id_from_zarr_url(zarr_url: str | None) -> str | None:
    if not zarr_url:
        return None
    name = zarr_url.rstrip("/").split("/")[-1]
    if name.endswith(".zarr"):
        return name[:-5]
    return name or None


def _storage_uri_exists(storage_uri: str | None) -> bool:
    text = _clean_text(storage_uri)
    if not text:
        return False

    if text.startswith("endrepo://"):
        try:
            return storage_service().resolve_uri(text).exists
        except Exception:
            return False

    backend_dir = Path(__file__).resolve().parents[2]

    if text.startswith("local://zarr/"):
        name = text.replace("local://zarr/", "", 1)
        return (backend_dir / "data" / "zarr" / name).exists()

    if text.startswith("/data/zarr/"):
        return (backend_dir / text.lstrip("/")).exists()

    if text.startswith("/endrepo/managed/zarr/"):
        suffix = text.replace("/endrepo/", "", 1)
        try:
            return storage_service().resolve_uri(f"endrepo://{suffix}").exists
        except Exception:
            return False

    return False


def _make_row(row: sqlite3.Row) -> dict[str, Any]:
    source_reference = _json_loads(row["source_reference_json"])
    artifact_summary = _json_loads(row["artifact_summary_json"])
    storage_uri = row["storage_uri"]
    zarr_url = _storage_uri_to_zarr_url(storage_uri)
    representation_id = row["representation_id"]
    is_loaded = bool(row["loaded"])

    metadata = {
        "msi": True,
        "survey_name": row["survey_name"],
        "line_name": row["line_name"],
        "volume_name": row["volume_name"],
        "processing_stage": row["processing_stage"],
        "processing_version": row["processing_version"],
        "source_reference": source_reference,
        "representation": {
            "representation_type": row["representation_type"],
            "viewer_mode": row["viewer_mode"],
            "viewer_ready": bool(row["viewer_ready"]),
            "is_preferred": bool(row["is_preferred"]),
            "lifecycle_state": row["lifecycle_state"],
        },
        "artifact_summary": artifact_summary,
    }

    return {
        "id": representation_id,
        "volume_id": representation_id,
        "physical_volume_id": _volume_id_from_zarr_url(zarr_url),
        "name": row["display_name"],
        "display_name": row["display_name"],
        "filename": row["display_name"],
        "survey_name": row["survey_name"],
        "line_name": row["line_name"],
        "volume_name": row["volume_name"],
        "processing_stage": row["processing_stage"],
        "processing_version": row["processing_version"],
        "dataset_type": row["dataset_type"],
        "zarr_url": zarr_url,
        "source": "msi",
        "registry_source": "msi",
        "msi_dataset_id": row["dataset_id"],
        "msi_representation_id": representation_id,
        "viewer_mode": row["viewer_mode"],
        "representation_type": row["representation_type"],
        "storage_uri": storage_uri,
        "lifecycle_state": row["lifecycle_state"],
        "viewer_ready": bool(row["viewer_ready"]),
        "is_preferred": bool(row["is_preferred"]),
        "is_loaded": is_loaded,
        "loaded_from_msi": is_loaded,
        "hidden": not is_loaded,
        "created_at": row["representation_created_at"],
        "updated_at": row["representation_updated_at"],
        "metadata": metadata,
    }


def query_managed_data_rows(
    *,
    q: str | None = None,
    dataset_type: str | None = None,
    viewer_mode: str | None = None,
    representation_type: str | None = None,
    loaded: bool | None = None,
    limit: int | None = None,
    offset: int | None = None,
    sort_by: str = "display_name",
    sort_dir: Literal["asc", "desc"] = "asc",
    viewer_ready_only: bool = True,
    storage_exists_only: bool = True,
) -> dict[str, Any]:
    clean_limit = _coerce_limit(limit)
    clean_offset = _coerce_offset(offset)
    clean_sort_by = sort_by if sort_by in VALID_SORT_COLUMNS else "display_name"
    clean_sort_dir = "DESC" if str(sort_dir or "").lower() == "desc" else "ASC"

    where = []
    params: list[Any] = []

    if viewer_ready_only:
        where.append("r.viewer_ready = 1")
        where.append("r.lifecycle_state = 'viewer_ready'")
        where.append("r.viewer_mode IN ('2d', '3d')")

    q_text = _clean_text(q)
    if q_text:
        like = f"%{q_text.lower()}%"
        where.append(
            """
            (
                lower(d.display_name) LIKE ?
                OR lower(coalesce(d.survey_name, '')) LIKE ?
                OR lower(coalesce(d.line_name, '')) LIKE ?
                OR lower(coalesce(d.volume_name, '')) LIKE ?
                OR lower(coalesce(d.processing_stage, '')) LIKE ?
                OR lower(coalesce(d.processing_version, '')) LIKE ?
                OR lower(d.dataset_id) LIKE ?
                OR lower(r.representation_id) LIKE ?
                OR lower(coalesce(r.representation_type, '')) LIKE ?
                OR lower(coalesce(r.viewer_mode, '')) LIKE ?
            )
            """
        )
        params.extend([like] * 10)

    for column, value in [
        ("d.dataset_type", dataset_type),
        ("r.viewer_mode", viewer_mode),
        ("r.representation_type", representation_type),
    ]:
        text = _clean_text(value)
        if text:
            where.append(f"{column} = ?")
            params.append(text)

    if loaded is not None:
        where.append("coalesce(l.loaded, 0) = ?")
        params.append(1 if loaded else 0)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    base_from = f"""
        FROM msi_representations r
        JOIN msi_datasets d ON d.dataset_id = r.dataset_id
        LEFT JOIN msi_viewer_loads l
            ON l.representation_id = r.representation_id
            AND l.loaded = 1
        {where_sql}
    """

    order_sql = VALID_SORT_COLUMNS[clean_sort_by]

    with _connect() as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) AS count {base_from}",
            params,
        ).fetchone()
        total_count = int(count_row["count"] if count_row else 0)

        rows = conn.execute(
            f"""
            SELECT
                d.dataset_id,
                d.dataset_type,
                d.display_name,
                d.survey_name,
                d.line_name,
                d.volume_name,
                d.processing_stage,
                d.processing_version,
                d.source_reference_json,
                d.registration_state,
                r.representation_id,
                r.representation_type,
                r.viewer_mode,
                r.storage_uri,
                r.lifecycle_state,
                r.viewer_ready,
                r.is_preferred,
                r.artifact_summary_json,
                r.created_at AS representation_created_at,
                r.updated_at AS representation_updated_at,
                coalesce(l.loaded, 0) AS loaded
            {base_from}
            ORDER BY {order_sql} {clean_sort_dir}, r.representation_id COLLATE NOCASE ASC
            LIMIT ? OFFSET ?
            """,
            [*params, clean_limit, clean_offset],
        ).fetchall()

    candidate_rows = [_make_row(row) for row in rows]

    if storage_exists_only:
        # Storage existence cannot currently be expressed portably in SQL because
        # URI resolution is storage-provider dependent. Apply it only to the
        # returned page. The DB query remains bounded by limit/offset.
        candidate_rows = [
            row for row in candidate_rows
            if _storage_uri_exists(row.get("storage_uri"))
            and row.get("zarr_url")
        ]

    return {
        "rows": candidate_rows,
        "total_count": total_count,
        "limit": clean_limit,
        "offset": clean_offset,
        "returned_count": len(candidate_rows),
        "has_more": clean_offset + clean_limit < total_count,
        "sort_by": clean_sort_by,
        "sort_dir": clean_sort_dir.lower(),
        "filters": {
            "q": q_text,
            "dataset_type": _clean_text(dataset_type) or None,
            "viewer_mode": _clean_text(viewer_mode) or None,
            "representation_type": _clean_text(representation_type) or None,
            "loaded": loaded,
            "viewer_ready_only": viewer_ready_only,
            "storage_exists_only": storage_exists_only,
        },
        "source": "msi_sql_query",
    }
