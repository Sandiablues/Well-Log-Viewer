from __future__ import annotations

# MD_DELETE_SCOPE_FINAL_SERVICE
# MD_DELETE_SCOPE_FINAL_2_ROUTE_OWNERSHIP

import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Literal

from app.msi.repository import MSIRepository, utc_now
from app.services.managed_delete_cascade_cleanup_service import cleanup_managed_delete_residuals
from app.services.source_intake_reset_service import reset_source_intake_candidate_derived_state
from app.storage.service import is_endrepo_zarr_url, resolve_endrepo_zarr_url_path

DeleteScope = Literal["single", "selected"]
MANAGED_ZARR_SIDECAR_SUFFIXES = (
    ".viewer_metadata.json",
    ".trace_header_summary.json",
    ".segy_binary_header.json",
    ".segy_text_header.txt",
)


@dataclass(frozen=True)
class DeleteTarget:
    representation_id: str
    dataset_id: str
    representation_type: str | None
    viewer_mode: str | None
    storage_uri: str | None
    lifecycle_state: str | None
    artifact_summary: Dict[str, Any]
    dataset_display_name: str | None
    dataset_type: str | None
    source_reference: Dict[str, Any]
    physical_volume_id: str | None


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _json_loads(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return {}
    try:
        return json.loads(str(value))
    except Exception:
        return {}


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        clean = _clean(value)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


def _physical_volume_id_from_representation(representation_id: str, artifact_summary: Dict[str, Any]) -> str:
    explicit = _clean(artifact_summary.get("volume_id") or artifact_summary.get("physical_volume_id"))
    if explicit:
        return explicit
    text = _clean(representation_id)
    if ":zarr_" in text:
        return text.rsplit(":zarr_", 1)[1].strip()
    return ""


def _sidecar_paths_for_artifact_path(path: Path) -> list[Path]:
    raw = str(path)
    return [Path(raw + suffix) for suffix in MANAGED_ZARR_SIDECAR_SUFFIXES if not raw.endswith(suffix)]


class ManagedDataDeleteService:
    schema_version = "managed_data.delete_scope_final.v1"
    guard_name = "md_delete_scope_final"

    def __init__(self, repository: MSIRepository | None = None) -> None:
        self.repository = repository or MSIRepository()

    def normalize_representation_ids(self, values: Iterable[str]) -> list[str]:
        return _dedupe(values)

    def _validate_scope(self, representation_ids: list[str], delete_scope: str, confirm_count: int | None = None) -> DeleteScope:
        if not representation_ids:
            raise ValueError("representation_ids is required")
        if delete_scope not in {"single", "selected"}:
            raise ValueError("delete_scope must be 'single' or 'selected'")
        if delete_scope == "single" and len(representation_ids) != 1:
            raise ValueError("delete_scope=single requires exactly one representation_id")
        if confirm_count is not None and int(confirm_count) != len(representation_ids):
            raise ValueError(f"confirm_count mismatch: expected {len(representation_ids)}, got {confirm_count}")
        return delete_scope  # type: ignore[return-value]

    def _load_targets(self, representation_ids: list[str]) -> list[DeleteTarget]:
        placeholders = ",".join("?" for _ in representation_ids)
        with self.repository.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT r.representation_id, r.dataset_id, r.representation_type,
                       r.viewer_mode, r.storage_uri, r.lifecycle_state,
                       r.artifact_summary_json,
                       d.display_name AS dataset_display_name,
                       d.dataset_type AS dataset_type,
                       d.source_reference_json AS source_reference_json
                FROM msi_representations r
                LEFT JOIN msi_datasets d ON d.dataset_id = r.dataset_id
                WHERE r.representation_id IN ({placeholders})
                """,
                representation_ids,
            ).fetchall()
        by_id: dict[str, sqlite3.Row] = {row["representation_id"]: row for row in rows}
        missing = [rid for rid in representation_ids if rid not in by_id]
        if missing:
            raise KeyError(json.dumps({"missing_representation_ids": missing}))

        targets: list[DeleteTarget] = []
        for rid in representation_ids:
            row = by_id[rid]
            artifact_summary = _json_loads(row["artifact_summary_json"])
            if not isinstance(artifact_summary, dict):
                artifact_summary = {}
            source_reference = _json_loads(row["source_reference_json"])
            if not isinstance(source_reference, dict):
                source_reference = {}
            targets.append(DeleteTarget(
                representation_id=rid,
                dataset_id=_clean(row["dataset_id"]),
                representation_type=row["representation_type"],
                viewer_mode=row["viewer_mode"],
                storage_uri=row["storage_uri"],
                lifecycle_state=row["lifecycle_state"],
                artifact_summary=artifact_summary,
                dataset_display_name=row["dataset_display_name"],
                dataset_type=row["dataset_type"],
                source_reference=source_reference,
                physical_volume_id=_physical_volume_id_from_representation(rid, artifact_summary) or None,
            ))
        return targets

    def _resolve_storage_paths_for_target(self, target: DeleteTarget) -> list[str]:
        raw_values: list[str] = []
        if target.storage_uri:
            raw_values.append(target.storage_uri)
        for key in ("zarr_url", "storage_uri", "path", "local_path", "volume_path"):
            value = target.artifact_summary.get(key)
            if isinstance(value, str):
                raw_values.append(value)
        paths: list[Path] = []
        for value in raw_values:
            text = _clean(value)
            if not text:
                continue
            try:
                if is_endrepo_zarr_url(text):
                    paths.append(resolve_endrepo_zarr_url_path(text))
                    continue
                if text.startswith("endrepo://"):
                    pseudo_url = "/" + text.replace("endrepo://", "endrepo/", 1)
                    if is_endrepo_zarr_url(pseudo_url):
                        paths.append(resolve_endrepo_zarr_url_path(pseudo_url))
                        continue
                if text.startswith("/"):
                    paths.append(Path(text).expanduser().resolve())
            except Exception:
                continue
        out: list[str] = []
        seen: set[str] = set()
        for path in paths:
            p = str(path)
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def _target_summary(self, target: DeleteTarget) -> Dict[str, Any]:
        return {
            "representation_id": target.representation_id,
            "dataset_id": target.dataset_id,
            "display_name": target.dataset_display_name,
            "dataset_type": target.dataset_type,
            "representation_type": target.representation_type,
            "viewer_mode": target.viewer_mode,
            "physical_volume_id": target.physical_volume_id,
            "storage_uri": target.storage_uri,
            "planned_storage_paths": self._resolve_storage_paths_for_target(target),
        }

    def plan_delete(self, representation_ids: Iterable[str], *, delete_scope: str, confirm_count: int | None = None) -> Dict[str, Any]:
        requested = self.normalize_representation_ids(representation_ids)
        scope = self._validate_scope(requested, delete_scope, confirm_count)
        targets = self._load_targets(requested)
        planned_ids = [target.representation_id for target in targets]
        if planned_ids != requested:
            raise ValueError("planned representation IDs do not exactly match requested IDs")
        return {
            "ok": True,
            "schema_version": self.schema_version,
            "dry_run": True,
            "delete_scope": scope,
            "delete_scope_guard": self.guard_name,
            "requested_count": len(requested),
            "planned_representation_count": len(planned_ids),
            "requested_representation_ids": requested,
            "planned_representation_ids": planned_ids,
            "graph_traversal": False,
            "source_candidate_traversal": False,
            "targets": [self._target_summary(target) for target in targets],
            "blocked": False,
            "blocked_reason": None,
        }

    # MD_DELETE_WORKBENCH_RESET_1
    def _reset_source_intake_state_for_target(self, target: DeleteTarget) -> Dict[str, Any]:
        """Reset only the Source Intake candidate behind this deleted representation.

        Keep this context deliberately narrow. Do not pass repository_id,
        package_id, or line_id because those can match sibling candidates in the
        same source package. The reset service already knows how to derive the
        source SEG-Y id from an MSI representation id shaped like
        msi_repr:source_segy_segy_xxx:zarr_yyy.
        """
        source = target.source_reference if isinstance(target.source_reference, dict) else {}
        artifact = target.artifact_summary if isinstance(target.artifact_summary, dict) else {}

        source_segy_file_id = _clean(
            source.get("source_segy_file_id")
            or source.get("segy_file_id")
            or source.get("candidate_id")
            or artifact.get("source_segy_file_id")
            or artifact.get("segy_file_id")
            or artifact.get("candidate_id")
        )

        reset_context = {
            "representation_id": target.representation_id,
            "msi_representation_id": target.representation_id,
            "dataset_id": target.dataset_id,
            "physical_volume_id": target.physical_volume_id,
            "volume_id": target.physical_volume_id,
            "source_segy_file_id": source_segy_file_id or None,
            "candidate_id": source_segy_file_id or None,
            "storage_uri": target.storage_uri,
            "zarr_url": artifact.get("zarr_url") if isinstance(artifact.get("zarr_url"), str) else None,
        }

        return reset_source_intake_candidate_derived_state(
            reset_context,
            reason="managed_data_isolated_delete_reset_workbench_state",
        )

    def execute_delete(self, representation_ids: Iterable[str], *, delete_scope: str, confirm_count: int, delete_orphan_managed_documents: bool = True) -> Dict[str, Any]:
        requested = self.normalize_representation_ids(representation_ids)
        scope = self._validate_scope(requested, delete_scope, confirm_count)
        targets = self._load_targets(requested)
        planned_ids = [target.representation_id for target in targets]
        if planned_ids != requested:
            raise ValueError("planned representation IDs do not exactly match requested IDs")

        with self.repository.connect() as conn:
            before_ids = {row["representation_id"] for row in conn.execute("SELECT representation_id FROM msi_representations").fetchall()}
            for target in targets:
                conn.execute("DELETE FROM msi_viewer_loads WHERE representation_id = ?", (target.representation_id,))
                conn.execute("DELETE FROM msi_artifact_jobs WHERE representation_id = ?", (target.representation_id,))
                conn.execute("DELETE FROM msi_representations WHERE representation_id = ?", (target.representation_id,))
            dataset_results: list[Dict[str, Any]] = []
            for dataset_id in sorted({target.dataset_id for target in targets if target.dataset_id}):
                remaining = conn.execute("SELECT COUNT(*) AS count FROM msi_representations WHERE dataset_id = ?", (dataset_id,)).fetchone()
                remaining_count = int(remaining["count"] if remaining else 0)
                dataset_deleted = False
                if remaining_count == 0:
                    conn.execute("DELETE FROM msi_artifact_jobs WHERE dataset_id = ?", (dataset_id,))
                    conn.execute("DELETE FROM msi_datasets WHERE dataset_id = ?", (dataset_id,))
                    dataset_deleted = True
                dataset_results.append({"dataset_id": dataset_id, "remaining_representations_for_dataset": remaining_count, "dataset_deleted": dataset_deleted})
            after_ids = {row["representation_id"] for row in conn.execute("SELECT representation_id FROM msi_representations").fetchall()}

        requested_set = set(requested)
        removed_ids = sorted(before_ids - after_ids)
        unexpected_removed_ids = sorted(set(removed_ids) - requested_set)
        missing_requested_removals = sorted(requested_set & after_ids)
        cleanup_results: list[Dict[str, Any]] = []
        source_intake_reset_results: list[Dict[str, Any]] = []
        if not unexpected_removed_ids:
            for target in targets:
                cleanup = cleanup_managed_delete_residuals(
                    representation_id=target.representation_id,
                    dataset_id=target.dataset_id,
                    physical_volume_id=target.physical_volume_id or "",
                    delete_orphan_managed_documents=delete_orphan_managed_documents,
                )
                direct_cleanup = self._cleanup_direct_storage_paths(target)
                cleanup_results.append({"representation_id": target.representation_id, "managed_delete_residuals": cleanup, "direct_storage_cleanup": direct_cleanup})
                source_intake_reset_results.append({
                    "representation_id": target.representation_id,
                    "reset_result": self._reset_source_intake_state_for_target(target),
                })
        ok = not unexpected_removed_ids and not missing_requested_removals
        return {
            "ok": ok,
            "schema_version": self.schema_version,
            "dry_run": False,
            "status": "deleted" if ok else "delete_scope_violation",
            "delete_scope": scope,
            "delete_scope_guard": self.guard_name,
            "graph_traversal": False,
            "source_candidate_traversal": False,
            "requested_count": len(requested),
            "deleted_count": len(removed_ids),
            "requested_representation_ids": requested,
            "planned_representation_ids": planned_ids,
            "deleted_representation_ids": removed_ids,
            "unexpected_removed_representation_ids": unexpected_removed_ids,
            "missing_requested_removals": missing_requested_removals,
            "targets": [self._target_summary(target) for target in targets],
            "dataset_results": dataset_results,
            "cleanup_results": cleanup_results,
            "source_intake_reset_results": source_intake_reset_results,
            "deleted_at": utc_now(),
        }

    def _cleanup_direct_storage_paths(self, target: DeleteTarget) -> Dict[str, Any]:
        results: list[Dict[str, Any]] = []
        for raw in self._resolve_storage_paths_for_target(target):
            path = Path(raw)
            results.append(self._remove_path_if_safe(path))
            for sidecar in _sidecar_paths_for_artifact_path(path):
                results.append(self._remove_path_if_safe(sidecar))
        return {"path_results": results, "removed_count": len([r for r in results if r.get("removed")])}

    def _remove_path_if_safe(self, path: Path) -> Dict[str, Any]:
        text = str(path)
        if "/End_Seismic_Data_Repository/managed/zarr/" not in text and "/seismic-viewer-backend/data/zarr" not in text:
            return {"path": text, "removed": False, "reason": "not_app_managed_zarr_path"}
        try:
            if not path.exists():
                return {"path": text, "removed": False, "reason": "missing"}
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            return {"path": text, "removed": True}
        except Exception as exc:
            return {"path": text, "removed": False, "reason": str(exc)}


managed_data_delete_service = ManagedDataDeleteService()
