from __future__ import annotations

from pathlib import Path
from typing import Any

from app.msi.registration_service import register_converted_segy_file
from app.services.package_registry_service import list_segy_files
from app.storage.service import is_endrepo_zarr_url, resolve_endrepo_zarr_url_path


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

    if is_endrepo_zarr_url(text):
        try:
            return resolve_endrepo_zarr_url_path(text).exists()
        except Exception:
            return False

    if text.startswith("local://zarr/"):
        return (_backend_root() / "data" / "zarr" / text.replace("local://zarr/", "", 1)).exists()

    if text.startswith("file://"):
        return Path(text.replace("file://", "", 1)).exists()

    if "://" in text:
        return True

    return Path(text).exists()


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


def _is_registration_candidate(row: dict[str, Any]) -> bool:
    return (
        _clean(row.get("conversion_status")) in {"converted", "ready"}
        and bool(_clean(row.get("segy_file_id")))
        and bool(_clean(row.get("volume_id")))
        and bool(_clean(row.get("zarr_url")))
        and _zarr_exists(row.get("zarr_url"))
    )


def build_converted_registration_reconcile_plan() -> dict[str, Any]:
    """
    Read-only production MSI registration reconcile plan.

    This identifies converted source SEG-Y rows that are eligible for production
    MSI registration. It does not write anything.
    """
    rows = _all_segy_files()

    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for row in rows:
        status = _clean(row.get("conversion_status"))
        if status not in {"converted", "ready"}:
            continue

        item = {
            "segy_file_id": row.get("segy_file_id"),
            "filename": row.get("filename"),
            "conversion_status": row.get("conversion_status"),
            "candidate_kind": row.get("candidate_kind"),
            "candidate_role": row.get("candidate_role"),
            "volume_id": row.get("volume_id"),
            "zarr_url": row.get("zarr_url"),
            "zarr_exists": _zarr_exists(row.get("zarr_url")),
        }

        reasons: list[str] = []
        if not _clean(row.get("segy_file_id")):
            reasons.append("missing_segy_file_id")
        if not _clean(row.get("volume_id")):
            reasons.append("missing_volume_id")
        if not _clean(row.get("zarr_url")):
            reasons.append("missing_zarr_url")
        elif not _zarr_exists(row.get("zarr_url")):
            reasons.append("zarr_artifact_missing")

        if reasons:
            skipped.append({**item, "skip_reasons": reasons})
        else:
            candidates.append(item)

    return {
        "ok": True,
        "mode": "plan",
        "candidate_count": len(candidates),
        "skipped_count": len(skipped),
        "candidates": candidates,
        "skipped": skipped,
    }


def reconcile_converted_source_segy_to_msi(*, dry_run: bool = True) -> dict[str, Any]:
    """
    Production MSI registration reconciliation for converted source SEG-Y rows.

    dry_run=True:
      returns the plan only.

    dry_run=False:
      idempotently upserts converted full-Zarr rows into MSI using the normal
      production registration service. This is not test seed.
    """
    plan = build_converted_registration_reconcile_plan()

    if dry_run:
        return {
            **plan,
            "mode": "dry_run",
            "writes_performed": False,
            "test_seed": False,
        }

    results: list[dict[str, Any]] = []
    registered_count = 0
    failed_count = 0

    rows_by_id = {
        _clean(row.get("segy_file_id")): row
        for row in _all_segy_files()
        if _clean(row.get("segy_file_id"))
    }

    for candidate in plan["candidates"]:
        segy_file_id = _clean(candidate.get("segy_file_id"))
        source_row = rows_by_id.get(segy_file_id)
        if not source_row:
            result = {
                "registered": False,
                "reason": "source_row_missing_during_reconcile",
                "segy_file_id": segy_file_id,
            }
        else:
            result = register_converted_segy_file(source_row, backend_root=_backend_root())

        if result.get("registered") is True:
            registered_count += 1
        else:
            failed_count += 1

        results.append(result)

    return {
        "ok": failed_count == 0,
        "mode": "execute",
        "writes_performed": True,
        "test_seed": False,
        "candidate_count": plan["candidate_count"],
        "skipped_count": plan["skipped_count"],
        "registered_count": registered_count,
        "failed_count": failed_count,
        "results": results,
        "skipped": plan["skipped"],
    }
