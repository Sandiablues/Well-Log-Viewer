from __future__ import annotations

from pathlib import Path
from typing import Any

from app.msi.repository import MSIRepository
from app.services.package_registry_service import list_segy_files
from app.services.volume_registry_service import load_volumes


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _zarr_exists(zarr_url: str | None) -> bool:
    text = _clean(zarr_url)
    if not text:
        return False

    if text.startswith("/data/zarr/"):
        return (_backend_root() / text.lstrip("/")).exists()

    if text.startswith("local://zarr/"):
        return (_backend_root() / "data" / "zarr" / text.replace("local://zarr/", "", 1)).exists()

    if text.startswith("file://"):
        return Path(text.replace("file://", "", 1)).exists()

    if "://" in text:
        return True

    return Path(text).exists()


def _volume_id_from_zarr_url(zarr_url: str | None) -> str | None:
    text = _clean(zarr_url)
    if not text:
        return None
    name = text.rstrip("/").split("/")[-1]
    if name.endswith(".zarr"):
        return name[:-5]
    return name or None


def _all_segy_files() -> list[dict[str, Any]]:
    try:
        rows = list_segy_files()
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    except TypeError:
        pass
    except Exception:
        return []

    return []


def _volume_rows_by_id() -> dict[str, dict[str, Any]]:
    payload = load_volumes()
    if isinstance(payload, dict):
        rows = [row for row in payload.values() if isinstance(row, dict)]
    elif isinstance(payload, list):
        rows = [row for row in payload if isinstance(row, dict)]
    else:
        rows = []

    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        volume_id = _clean(row.get("id") or row.get("volume_id"))
        if volume_id:
            out[volume_id] = row
    return out


def _dataset_type_from_segy(row: dict[str, Any]) -> str:
    dataset_type = _clean(row.get("dataset_type"))
    candidate_kind = _clean(row.get("candidate_kind"))

    if dataset_type in {"2d_line", "3d_volume"}:
        return dataset_type
    if candidate_kind in {"2d_line", "3d_volume"}:
        return candidate_kind
    return "unknown"


def _expected_representation_type(dataset_type: str) -> str:
    if dataset_type == "3d_volume":
        return "zarr_3d"
    if dataset_type == "2d_line":
        return "zarr_2d"
    return "unknown"


def _expected_viewer_mode(dataset_type: str) -> str:
    if dataset_type == "3d_volume":
        return "3d"
    if dataset_type == "2d_line":
        return "2d"
    return "none"


def build_msi_ownership_audit() -> dict[str, Any]:
    """
    Read-only MSI ownership audit.

    This audits converted full-Zarr source SEG-Y records against:
    - legacy volume registry
    - MSI dataset rows
    - MSI representation rows
    - physical Zarr artifact existence

    It does not mutate anything.
    """
    repo = MSIRepository()
    volumes_by_id = _volume_rows_by_id()

    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    converted = [
        row for row in _all_segy_files()
        if _clean(row.get("conversion_status")) in {"converted", "ready"}
        and (_clean(row.get("volume_id")) or _clean(row.get("zarr_url")))
    ]

    for segy in converted:
        segy_file_id = _clean(segy.get("segy_file_id"))
        filename = segy.get("filename")
        volume_id = _clean(segy.get("volume_id")) or _volume_id_from_zarr_url(segy.get("zarr_url"))
        zarr_url = _clean(segy.get("zarr_url"))
        dataset_type = _dataset_type_from_segy(segy)

        dataset_id = f"source_segy:{segy_file_id}" if segy_file_id else None
        expected_representation_id = (
            f"msi_repr:source_segy_{segy_file_id}:zarr_{volume_id}"
            if segy_file_id and volume_id
            else None
        )

        legacy_volume = volumes_by_id.get(volume_id or "")
        legacy_exists = bool(legacy_volume)

        msi_dataset = None
        try:
            for item in repo.list_datasets():
                if getattr(item, "dataset_id", None) == dataset_id:
                    msi_dataset = item
                    break
        except Exception:
            msi_dataset = None

        msi_representations = []
        if dataset_id:
            try:
                msi_representations = repo.list_representations(dataset_id)
            except Exception:
                msi_representations = []

        selected_rep = None
        for rep in msi_representations:
            if getattr(rep, "representation_id", None) == expected_representation_id:
                selected_rep = rep
                break

        if selected_rep is None and msi_representations:
            selected_rep = sorted(
                msi_representations,
                key=lambda rep: (
                    1 if getattr(rep, "is_preferred", False) else 0,
                    1 if getattr(rep, "viewer_ready", False) else 0,
                    str(getattr(rep, "updated_at", "") or ""),
                ),
                reverse=True,
            )[0]

        rep_artifact = getattr(selected_rep, "artifact_summary", {}) if selected_rep else {}
        if not isinstance(rep_artifact, dict):
            rep_artifact = {}

        msi_representation_id = getattr(selected_rep, "representation_id", None) if selected_rep else None
        msi_volume_id = _clean(rep_artifact.get("volume_id"))
        msi_zarr_url = _clean(rep_artifact.get("zarr_url"))

        row_issues: list[str] = []

        if not segy_file_id:
            row_issues.append("missing_source_segy_file_id")
        if not volume_id:
            row_issues.append("missing_source_volume_id")
        if not zarr_url:
            row_issues.append("missing_source_zarr_url")
        if zarr_url and not _zarr_exists(zarr_url):
            row_issues.append("source_zarr_artifact_missing")
        if not legacy_exists:
            row_issues.append("legacy_volume_row_missing")
        if not msi_dataset:
            row_issues.append("msi_dataset_missing")
        if not selected_rep:
            row_issues.append("msi_representation_missing")
        if expected_representation_id and msi_representation_id and expected_representation_id != msi_representation_id:
            row_issues.append("msi_representation_id_mismatch")
        if selected_rep and getattr(selected_rep, "representation_type", None) != _expected_representation_type(dataset_type):
            row_issues.append("msi_representation_type_mismatch")
        if selected_rep and getattr(selected_rep, "viewer_mode", None) != _expected_viewer_mode(dataset_type):
            row_issues.append("msi_viewer_mode_mismatch")
        if selected_rep and not bool(getattr(selected_rep, "viewer_ready", False)):
            row_issues.append("msi_not_viewer_ready")
        if selected_rep and getattr(selected_rep, "lifecycle_state", None) != "viewer_ready":
            row_issues.append("msi_lifecycle_not_viewer_ready")
        if selected_rep and volume_id and msi_volume_id and volume_id != msi_volume_id:
            row_issues.append("msi_physical_volume_id_mismatch")
        if selected_rep and zarr_url and msi_zarr_url and zarr_url != msi_zarr_url:
            row_issues.append("msi_zarr_url_mismatch")
        if selected_rep and msi_zarr_url and not _zarr_exists(msi_zarr_url):
            row_issues.append("msi_zarr_artifact_missing")

        status = "ok" if not row_issues else "issue"

        audit_row = {
            "status": status,
            "issues": row_issues,
            "segy_file_id": segy_file_id,
            "filename": filename,
            "dataset_type": dataset_type,
            "source_conversion_status": segy.get("conversion_status"),
            "source_volume_id": volume_id,
            "source_zarr_url": zarr_url,
            "source_zarr_exists": _zarr_exists(zarr_url),
            "legacy_volume_exists": legacy_exists,
            "legacy_volume_hidden": legacy_volume.get("hidden") if legacy_volume else None,
            "msi_dataset_exists": bool(msi_dataset),
            "msi_dataset_id": dataset_id,
            "msi_registration_state": getattr(msi_dataset, "registration_state", None) if msi_dataset else None,
            "msi_representation_exists": bool(selected_rep),
            "expected_msi_representation_id": expected_representation_id,
            "msi_representation_id": msi_representation_id,
            "msi_representation_type": getattr(selected_rep, "representation_type", None) if selected_rep else None,
            "msi_viewer_mode": getattr(selected_rep, "viewer_mode", None) if selected_rep else None,
            "msi_lifecycle_state": getattr(selected_rep, "lifecycle_state", None) if selected_rep else None,
            "msi_viewer_ready": bool(getattr(selected_rep, "viewer_ready", False)) if selected_rep else False,
            "msi_is_preferred": bool(getattr(selected_rep, "is_preferred", False)) if selected_rep else False,
            "msi_physical_volume_id": msi_volume_id or None,
            "msi_zarr_url": msi_zarr_url or None,
            "msi_zarr_exists": _zarr_exists(msi_zarr_url) if msi_zarr_url else False,
            "legacy_msi_identity_match": bool(
                volume_id
                and msi_volume_id
                and volume_id == msi_volume_id
            ),
        }

        rows.append(audit_row)

        for issue in row_issues:
            issues.append({
                "issue": issue,
                "segy_file_id": segy_file_id,
                "filename": filename,
                "source_volume_id": volume_id,
                "expected_msi_representation_id": expected_representation_id,
            })

    rows.sort(key=lambda item: (item["status"], item.get("filename") or ""))

    return {
        "ok": len(issues) == 0,
        "converted_source_count": len(converted),
        "audited_count": len(rows),
        "issue_count": len(issues),
        "issues": issues,
        "rows": rows,
    }
