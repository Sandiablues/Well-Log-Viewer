from __future__ import annotations

import csv
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


END_REPOSITORY_ENV = "END_SEISMIC_DATA_REPOSITORY_PATH"
DEFAULT_BUCKET_NAME = "End_Seismic_Data_Repository"
DEFAULT_BUCKET_SCHEME = "endrepo"
ENDREPO_MANAGED_ZARR_URL_PREFIX = "/endrepo/managed/zarr"


@dataclass(frozen=True)
class ResolvedStorageUri:
    uri: str
    scheme: str
    relative_path: str
    local_path: str
    exists: bool
    is_dir: bool
    is_file: bool


def default_repository_root() -> Path:
    configured = os.environ.get(END_REPOSITORY_ENV)
    if configured:
        return Path(configured).expanduser().resolve()

    return (Path.home() / "Applications" / "MultiViewer" / DEFAULT_BUCKET_NAME).resolve()


class EndSeismicRepositoryStorageService:
    """
    Local prototype storage-mount service for the End_Seismic_Data_Repository bucket.

    This service intentionally treats the local filesystem folder as the backing
    implementation of a logical bucket. MSI and viewer services should refer to
    managed artifacts using logical URIs such as:

        endrepo://managed/zarr/3d/<volume_id>.zarr

    The service resolves those URIs to the active local mount path for this
    single-node prototype. Later enterprise deployments can keep the same URI
    contract while replacing the local resolver with object/network storage.
    """

    def __init__(self, repository_root: Path | None = None) -> None:
        self.repository_root = (repository_root or default_repository_root()).resolve()
        self.manifest_path = self.repository_root / "BUCKET_MANIFEST.json"

    def load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {}

        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def health(self) -> dict[str, Any]:
        manifest = self.load_manifest()
        required_directories = [
            "managed/zarr/3d",
            "managed/zarr/2d",
            "managed/segy_index/3d",
            "managed/segy_index/2d",
            "managed/enhanced/3d",
            "managed/enhanced/2d",
            "metadata/sidecars",
            "metadata/normalized",
            "metadata/reports",
            "metadata/evidence",
            "staging/conversion_jobs",
            "staging/tmp",
            "staging/imports",
            "manifests/datasets",
            "manifests/representations",
            "manifests/jobs",
            "logs",
        ]

        directory_status = {
            rel: (self.repository_root / rel).exists() and (self.repository_root / rel).is_dir()
            for rel in required_directories
        }

        manifest_scheme = str(manifest.get("bucket_scheme") or DEFAULT_BUCKET_SCHEME).strip()
        manifest_bucket_name = str(manifest.get("bucket_name") or DEFAULT_BUCKET_NAME).strip()

        ok = (
            self.repository_root.exists()
            and self.repository_root.is_dir()
            and self.manifest_path.exists()
            and manifest_scheme == DEFAULT_BUCKET_SCHEME
            and manifest_bucket_name == DEFAULT_BUCKET_NAME
            and all(directory_status.values())
        )

        return {
            "ok": ok,
            "service": "storage",
            "bucket_name": DEFAULT_BUCKET_NAME,
            "bucket_scheme": DEFAULT_BUCKET_SCHEME,
            "local_mount_path": str(self.repository_root),
            "manifest_path": str(self.manifest_path),
            "manifest_exists": self.manifest_path.exists(),
            "manifest_bucket_name": manifest_bucket_name or None,
            "manifest_bucket_scheme": manifest_scheme or None,
            "directory_status": directory_status,
            "missing_directories": [rel for rel, exists in directory_status.items() if not exists],
            "resolver": "local_prototype_bucket_mount",
        }

    def resolve_uri(self, uri: str) -> ResolvedStorageUri:
        clean_uri = str(uri or "").strip()
        if not clean_uri:
            raise ValueError("Storage URI is required.")

        parsed = urlparse(clean_uri)
        if parsed.scheme != DEFAULT_BUCKET_SCHEME:
            raise ValueError(f"Unsupported storage URI scheme: {parsed.scheme or '<missing>'}")

        relative_path = self._relative_path_from_endrepo_uri(parsed)
        local_path = (self.repository_root / relative_path).resolve()

        try:
            local_path.relative_to(self.repository_root)
        except ValueError as exc:
            raise ValueError("Storage URI resolves outside the mounted repository.") from exc

        return ResolvedStorageUri(
            uri=clean_uri,
            scheme=parsed.scheme,
            relative_path=relative_path,
            local_path=str(local_path),
            exists=local_path.exists(),
            is_dir=local_path.is_dir(),
            is_file=local_path.is_file(),
        )

    def managed_zarr_target(self, artifact_id: str, dimension: str) -> dict[str, Any]:
        """
        Return the backend-owned target contract for a new managed Zarr artifact.

        The logical storage URI is the durable contract. The local path is the
        current single-node backing implementation. The zarr_url is a served API
        path used by existing viewer/slice code during the local prototype phase.
        """
        clean_id = _safe_artifact_name(artifact_id)
        clean_dimension = str(dimension or "").strip().lower()

        if clean_dimension not in {"2d", "3d"}:
            raise ValueError("Managed Zarr dimension must be '2d' or '3d'.")

        name = clean_id if clean_id.endswith(".zarr") else f"{clean_id}.zarr"
        uri = f"{DEFAULT_BUCKET_SCHEME}://managed/zarr/{clean_dimension}/{name}"
        resolved = self.resolve_uri(uri)

        return {
            "ok": True,
            "service": "storage",
            "artifact_kind": "managed_zarr",
            "dimension": clean_dimension,
            "artifact_id": clean_id.removesuffix(".zarr"),
            "name": name,
            "storage_uri": uri,
            "local_path": resolved.local_path,
            "relative_path": resolved.relative_path,
            "zarr_url": f"{ENDREPO_MANAGED_ZARR_URL_PREFIX}/{clean_dimension}/{name}",
            "resolved_by": "end_seismic_repository_storage_service",
        }

    def resolve_endrepo_zarr_url(self, zarr_url: str) -> ResolvedStorageUri:
        """
        Resolve the local prototype served EndRepo Zarr URL back to storage.
        """
        text = str(zarr_url or "").strip()
        prefix = ENDREPO_MANAGED_ZARR_URL_PREFIX.rstrip("/") + "/"

        if not text.startswith(prefix):
            raise ValueError("Not an EndRepo managed Zarr URL.")

        suffix = text[len(prefix):].strip("/")
        if not suffix:
            raise ValueError("EndRepo managed Zarr URL is missing a path.")

        return self.resolve_uri(f"{DEFAULT_BUCKET_SCHEME}://managed/zarr/{suffix}")



    def inventory(self) -> dict[str, Any]:
        """
        Read-only inventory of current processed artifact storage.

        This method intentionally does not create, move, copy, delete, or
        register artifacts. It reports current legacy artifact locations and
        suggests endrepo:// targets for later migration planning.
        """
        backend_root = _backend_root()
        legacy_data_root = backend_root / "data"

        legacy_zarr_items = self._inventory_legacy_zarr(legacy_data_root / "zarr")
        legacy_zarr_tmp_items = self._inventory_generic_directory(
            artifact_kind="legacy_zarr_tmp",
            base_path=legacy_data_root / "zarr_tmp",
            current_uri_prefix=None,
            suggested_uri_prefix=None,
        )
        legacy_segy_index_items = self._inventory_generic_directory(
            artifact_kind="legacy_segy_index",
            base_path=legacy_data_root / "segy_index",
            current_uri_prefix=None,
            suggested_uri_prefix=f"{DEFAULT_BUCKET_SCHEME}://managed/segy_index",
        )
        legacy_jobs_items = self._inventory_generic_directory(
            artifact_kind="legacy_job_record",
            base_path=legacy_data_root / "jobs",
            current_uri_prefix=None,
            suggested_uri_prefix=f"{DEFAULT_BUCKET_SCHEME}://manifests/jobs",
            file_extensions={".json", ".jsonl"},
        )

        target_bucket_items = self._inventory_target_bucket()

        legacy_items = (
            legacy_zarr_items
            + legacy_zarr_tmp_items
            + legacy_segy_index_items
            + legacy_jobs_items
        )
        review_required = [item for item in legacy_items if item.migration_status == "review_required"]

        return {
            "ok": True,
            "service": "storage",
            "inventory_mode": "read_only",
            "mutates_storage": False,
            "backend_root": str(backend_root),
            "legacy_data_root": str(legacy_data_root),
            "end_repository_root": str(self.repository_root),
            "summary": {
                "legacy_zarr_count": len(legacy_zarr_items),
                "legacy_zarr_tmp_count": len(legacy_zarr_tmp_items),
                "legacy_segy_index_count": len(legacy_segy_index_items),
                "legacy_job_record_count": len(legacy_jobs_items),
                "target_bucket_item_count": len(target_bucket_items),
                "review_required_count": len(review_required),
            },
            "legacy_artifacts": {
                "zarr": [item.__dict__ for item in legacy_zarr_items],
                "zarr_tmp": [item.__dict__ for item in legacy_zarr_tmp_items],
                "segy_index": [item.__dict__ for item in legacy_segy_index_items],
                "job_records": [item.__dict__ for item in legacy_jobs_items],
            },
            "target_bucket": [item.__dict__ for item in target_bucket_items],
            "review_required": [item.__dict__ for item in review_required],
            "migration_policy": {
                "status": "plan_only",
                "copy_or_move_performed": False,
                "msi_rewrite_performed": False,
                "next_step": "Review this inventory before any artifact migration or MSI storage_uri rewrite.",
            },
            "resolved_by": "end_seismic_repository_storage_service",
        }


    def migration_plan(self) -> dict[str, Any]:
        """
        Read-only migration-plan export derived from the current storage inventory.

        This method does not create, move, copy, delete, or rewrite artifacts.
        It converts the full inventory into a compact, reviewable candidate list
        that can be inspected before any later migration execution block.
        """
        inventory = self.inventory()
        candidates: list[dict[str, Any]] = []

        legacy_artifacts = inventory.get("legacy_artifacts") or {}
        for group_name in ["zarr", "zarr_tmp", "segy_index", "job_records"]:
            group_items = legacy_artifacts.get(group_name) or []
            if not isinstance(group_items, list):
                continue
            for item in group_items:
                if not isinstance(item, dict):
                    continue
                candidates.append(_migration_candidate_from_inventory_item(item))

        summary = {
            "candidate_count": len(candidates),
            "ready_candidate_count": sum(1 for item in candidates if not item.get("review_required")),
            "review_required_count": sum(1 for item in candidates if item.get("review_required")),
            "copy_or_move_performed": False,
            "msi_rewrite_performed": False,
        }

        return {
            "ok": True,
            "service": "storage",
            "plan_mode": "read_only",
            "source_inventory": {
                "summary": inventory.get("summary"),
                "migration_policy": inventory.get("migration_policy"),
            },
            "summary": summary,
            "candidates": candidates,
            "policy": {
                "status": "plan_only",
                "copy_or_move_performed": False,
                "msi_rewrite_performed": False,
                "requires_review_before_execution": True,
                "next_step": "Review and approve the migration plan before any copy/move/MSI rewrite sprint.",
            },
            "resolved_by": "end_seismic_repository_storage_service",
        }

    def export_migration_plan_review(self) -> dict[str, Any]:
        """
        Write a review-only JSON and CSV export of the current migration plan.

        This is the only write allowed in Storage Sprint 2A-4. It writes review
        manifest files under End_Seismic_Data_Repository/manifests/ and does not
        copy, move, delete, or rewrite any seismic artifact, job artifact, or MSI
        record.
        """
        plan = self.migration_plan()
        candidates = plan.get("candidates") or []
        if not isinstance(candidates, list):
            candidates = []

        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        safe_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        export_dir = self.repository_root / "manifests" / "migration_reviews"
        export_dir.mkdir(parents=True, exist_ok=True)

        base_name = f"storage_migration_plan_review_{safe_stamp}"
        json_path = export_dir / f"{base_name}.json"
        csv_path = export_dir / f"{base_name}.csv"

        export_payload = {
            "ok": True,
            "service": "storage",
            "export_mode": "review_manifest_only",
            "generated_at": generated_at,
            "source_plan_summary": plan.get("summary"),
            "policy": {
                "status": "review_export_only",
                "copy_or_move_performed": False,
                "msi_rewrite_performed": False,
                "artifact_migration_performed": False,
                "requires_review_before_execution": True,
            },
            "candidate_count": len(candidates),
            "candidates": candidates,
            "resolved_by": "end_seismic_repository_storage_service",
        }

        json_path.write_text(json.dumps(export_payload, indent=2, sort_keys=True), encoding="utf-8")

        fieldnames = [
            "artifact_kind",
            "name",
            "current_path",
            "current_uri",
            "exists",
            "is_dir",
            "size_bytes",
            "inferred_dimension",
            "suggested_endrepo_uri",
            "migration_status",
            "confidence",
            "review_required",
            "notes",
        ]

        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for candidate in candidates:
                row = {key: candidate.get(key) for key in fieldnames}
                notes = row.get("notes")
                if isinstance(notes, list):
                    row["notes"] = " | ".join(str(item) for item in notes)
                writer.writerow(row)

        return {
            "ok": True,
            "service": "storage",
            "export_mode": "review_manifest_only",
            "generated_at": generated_at,
            "candidate_count": len(candidates),
            "json_path": str(json_path),
            "csv_path": str(csv_path),
            "json_uri": f"{DEFAULT_BUCKET_SCHEME}://manifests/migration_reviews/{json_path.name}",
            "csv_uri": f"{DEFAULT_BUCKET_SCHEME}://manifests/migration_reviews/{csv_path.name}",
            "copy_or_move_performed": False,
            "msi_rewrite_performed": False,
            "artifact_migration_performed": False,
            "resolved_by": "end_seismic_repository_storage_service",
        }


    def execute_managed_zarr_copy(self, execute: bool = False) -> dict[str, Any]:
        """
        Copy confirmed legacy Zarr artifacts into the End seismic repository.

        This is intentionally narrow and conservative:
        - only legacy_zarr candidates from the migration plan are eligible;
        - zarr_tmp, job records, SEG-Y indexes, and review-required items are ignored;
        - originals are never moved or deleted;
        - MSI records are never rewritten;
        - existing targets are skipped, not overwritten.
        """
        plan = self.migration_plan()
        candidates = plan.get("candidates") or []
        if not isinstance(candidates, list):
            candidates = []

        eligible: list[dict[str, Any]] = []
        ignored: list[dict[str, Any]] = []

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue

            artifact_kind = candidate.get("artifact_kind")
            suggested_uri = str(candidate.get("suggested_endrepo_uri") or "").strip()
            review_required = bool(candidate.get("review_required"))

            if (
                artifact_kind == "legacy_zarr"
                and not review_required
                and suggested_uri.startswith(f"{DEFAULT_BUCKET_SCHEME}://managed/zarr/")
            ):
                eligible.append(candidate)
            else:
                ignored.append({
                    "artifact_kind": artifact_kind,
                    "name": candidate.get("name"),
                    "reason": "not_managed_zarr_copy_candidate",
                })

        results: list[dict[str, Any]] = []
        copied_count = 0
        skipped_count = 0
        failed_count = 0

        for candidate in eligible:
            source_path = Path(str(candidate.get("current_path") or "")).expanduser()
            target_uri = str(candidate.get("suggested_endrepo_uri") or "").strip()
            target_resolved = self.resolve_uri(target_uri)
            target_path = Path(target_resolved.local_path)

            result = {
                "artifact_kind": candidate.get("artifact_kind"),
                "name": candidate.get("name"),
                "inferred_dimension": candidate.get("inferred_dimension"),
                "source_path": str(source_path),
                "target_uri": target_uri,
                "target_path": str(target_path),
                "action": "dry_run" if not execute else None,
                "status": None,
                "message": None,
            }

            if not source_path.exists():
                failed_count += 1
                result.update({
                    "action": "none",
                    "status": "failed",
                    "message": "Source path does not exist.",
                })
                results.append(result)
                continue

            if target_path.exists():
                skipped_count += 1
                result.update({
                    "action": "skip",
                    "status": "skipped_existing_target",
                    "message": "Target already exists; overwrite is intentionally not supported in this operation.",
                })
                results.append(result)
                continue

            if not execute:
                result.update({
                    "action": "would_copy",
                    "status": "planned",
                    "message": "Dry run only; no files copied.",
                })
                results.append(result)
                continue

            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if source_path.is_dir():
                    shutil.copytree(source_path, target_path)
                elif source_path.is_file():
                    shutil.copy2(source_path, target_path)
                else:
                    raise RuntimeError("Source is neither file nor directory.")

                copied_count += 1
                result.update({
                    "action": "copy",
                    "status": "copied",
                    "message": "Copied legacy Zarr artifact to End seismic repository.",
                })
            except Exception as exc:
                failed_count += 1
                result.update({
                    "action": "copy",
                    "status": "failed",
                    "message": str(exc),
                })

            results.append(result)

        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        safe_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        manifest_uri = None
        manifest_path = None

        if execute:
            manifest_dir = self.repository_root / "manifests" / "migration_executions"
            manifest_dir.mkdir(parents=True, exist_ok=True)
            manifest_file = manifest_dir / f"managed_zarr_copy_{safe_stamp}.json"
            manifest_payload = {
                "ok": failed_count == 0,
                "service": "storage",
                "operation": "managed_zarr_copy",
                "generated_at": generated_at,
                "execute": True,
                "summary": {
                    "eligible_count": len(eligible),
                    "copied_count": copied_count,
                    "skipped_count": skipped_count,
                    "failed_count": failed_count,
                    "ignored_count": len(ignored),
                    "copy_or_move_performed": copied_count > 0,
                    "move_performed": False,
                    "delete_performed": False,
                    "msi_rewrite_performed": False,
                },
                "results": results,
                "ignored": ignored,
                "resolved_by": "end_seismic_repository_storage_service",
            }
            manifest_file.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding="utf-8")
            manifest_path = str(manifest_file)
            manifest_uri = f"{DEFAULT_BUCKET_SCHEME}://manifests/migration_executions/{manifest_file.name}"

        return {
            "ok": failed_count == 0,
            "service": "storage",
            "operation": "managed_zarr_copy",
            "execute": bool(execute),
            "mode": "execute" if execute else "dry_run",
            "eligible_count": len(eligible),
            "copied_count": copied_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "ignored_count": len(ignored),
            "copy_or_move_performed": bool(execute and copied_count > 0),
            "move_performed": False,
            "delete_performed": False,
            "msi_rewrite_performed": False,
            "artifact_migration_scope": "managed_zarr_only",
            "manifest_path": manifest_path,
            "manifest_uri": manifest_uri,
            "results": results,
            "resolved_by": "end_seismic_repository_storage_service",
        }


    def managed_zarr_copy_status(self) -> dict[str, Any]:
        """
        Read-only verification of managed Zarr copy readiness in the End seismic repository.

        This method verifies the current legacy Zarr copy state without moving,
        deleting, copying, or rewriting MSI records. It is intended to be run
        after the managed Zarr copy operation and before any MSI storage_uri
        rewrite sprint.
        """
        plan = self.migration_plan()
        candidates = plan.get("candidates") or []
        if not isinstance(candidates, list):
            candidates = []

        rows: list[dict[str, Any]] = []
        ready_count = 0
        missing_target_count = 0
        invalid_target_count = 0
        review_required_count = 0

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue

            if candidate.get("artifact_kind") != "legacy_zarr":
                continue

            source_path = Path(str(candidate.get("current_path") or "")).expanduser()
            target_uri = str(candidate.get("suggested_endrepo_uri") or "").strip()
            source_exists = source_path.exists()
            source_is_dir = source_path.is_dir()

            review_required = bool(candidate.get("review_required")) or not target_uri
            target_path: Path | None = None
            target_exists = False
            target_is_dir = False
            target_likely_valid = False
            validation_markers: list[str] = []
            issues: list[str] = []

            if review_required:
                review_required_count += 1
                issues.append("Candidate requires review or has no suggested target URI.")
            elif target_uri:
                try:
                    resolved = self.resolve_uri(target_uri)
                    target_path = Path(resolved.local_path)
                    target_exists = resolved.exists
                    target_is_dir = resolved.is_dir
                    target_likely_valid, validation_markers = _zarr_path_likely_valid(target_path)
                except Exception as exc:
                    issues.append(f"Target URI could not be resolved: {exc}")

            if not source_exists:
                issues.append("Source legacy Zarr path does not exist.")
            if source_exists and not source_is_dir:
                issues.append("Source legacy Zarr path is not a directory.")

            if not review_required:
                if not target_exists:
                    missing_target_count += 1
                    issues.append("Target EndRepo Zarr path does not exist.")
                elif not target_is_dir:
                    invalid_target_count += 1
                    issues.append("Target EndRepo Zarr path exists but is not a directory.")
                elif not target_likely_valid:
                    invalid_target_count += 1
                    issues.append("Target EndRepo Zarr path exists but expected Zarr metadata markers were not found.")
                elif source_exists and source_is_dir:
                    ready_count += 1

            rows.append({
                "artifact_kind": candidate.get("artifact_kind"),
                "name": candidate.get("name"),
                "inferred_dimension": candidate.get("inferred_dimension"),
                "source_path": str(source_path),
                "source_exists": source_exists,
                "source_is_dir": source_is_dir,
                "target_uri": target_uri or None,
                "target_path": str(target_path) if target_path else None,
                "target_exists": target_exists,
                "target_is_dir": target_is_dir,
                "target_likely_valid": target_likely_valid,
                "validation_markers": validation_markers,
                "review_required": review_required,
                "issues": issues,
                "ready_for_msi_storage_uri_rewrite": bool(
                    source_exists
                    and source_is_dir
                    and target_exists
                    and target_is_dir
                    and target_likely_valid
                    and not review_required
                    and not issues
                ),
            })

        not_ready_count = sum(1 for row in rows if not row.get("ready_for_msi_storage_uri_rewrite"))

        return {
            "ok": True,
            "service": "storage",
            "status_mode": "read_only_verification",
            "operation": "managed_zarr_copy_status",
            "summary": {
                "managed_zarr_candidate_count": len(rows),
                "ready_for_msi_storage_uri_rewrite_count": ready_count,
                "not_ready_count": not_ready_count,
                "missing_target_count": missing_target_count,
                "invalid_target_count": invalid_target_count,
                "review_required_count": review_required_count,
                "copy_or_move_performed": False,
                "msi_rewrite_performed": False,
            },
            "rows": rows,
            "policy": {
                "status": "verification_only",
                "copy_or_move_performed": False,
                "msi_rewrite_performed": False,
                "next_step": "Review readiness before any MSI storage_uri rewrite sprint.",
            },
            "resolved_by": "end_seismic_repository_storage_service",
        }


    def _inventory_legacy_zarr(self, base_path: Path) -> list[StorageArtifactInventoryItem]:
        items: list[StorageArtifactInventoryItem] = []
        for child in _directory_children(base_path):
            if not child.name.endswith(".zarr") and not child.is_dir():
                continue

            dimension = _infer_dimension_from_metadata(child)
            suggested_uri = _zarr_target_uri(child.name, dimension)
            items.append(
                StorageArtifactInventoryItem(
                    artifact_kind="legacy_zarr",
                    current_path=str(child),
                    current_uri=f"/data/zarr/{child.name}",
                    name=child.name,
                    exists=child.exists(),
                    is_dir=child.is_dir(),
                    size_bytes=_safe_stat_size(child),
                    inferred_dimension=dimension,
                    suggested_endrepo_uri=suggested_uri,
                    migration_status="target_suggested" if suggested_uri else "review_required",
                )
            )
        return items

    def _inventory_generic_directory(
        self,
        artifact_kind: str,
        base_path: Path,
        current_uri_prefix: str | None,
        suggested_uri_prefix: str | None,
        file_extensions: set[str] | None = None,
    ) -> list[StorageArtifactInventoryItem]:
        items: list[StorageArtifactInventoryItem] = []

        for child in _directory_children(base_path):
            if file_extensions and child.suffix not in file_extensions:
                continue

            current_uri = f"{current_uri_prefix.rstrip('/')}/{child.name}" if current_uri_prefix else None
            suggested_uri = f"{suggested_uri_prefix.rstrip('/')}/{child.name}" if suggested_uri_prefix else None

            items.append(
                StorageArtifactInventoryItem(
                    artifact_kind=artifact_kind,
                    current_path=str(child),
                    current_uri=current_uri,
                    name=child.name,
                    exists=child.exists(),
                    is_dir=child.is_dir(),
                    size_bytes=_safe_stat_size(child),
                    inferred_dimension=None,
                    suggested_endrepo_uri=suggested_uri,
                    migration_status="target_suggested" if suggested_uri else "review_required",
                )
            )

        return items

    def _inventory_target_bucket(self) -> list[StorageArtifactInventoryItem]:
        target_roots = [
            ("target_zarr_3d", self.repository_root / "managed" / "zarr" / "3d", f"{DEFAULT_BUCKET_SCHEME}://managed/zarr/3d"),
            ("target_zarr_2d", self.repository_root / "managed" / "zarr" / "2d", f"{DEFAULT_BUCKET_SCHEME}://managed/zarr/2d"),
            ("target_segy_index_3d", self.repository_root / "managed" / "segy_index" / "3d", f"{DEFAULT_BUCKET_SCHEME}://managed/segy_index/3d"),
            ("target_segy_index_2d", self.repository_root / "managed" / "segy_index" / "2d", f"{DEFAULT_BUCKET_SCHEME}://managed/segy_index/2d"),
            ("target_enhanced_3d", self.repository_root / "managed" / "enhanced" / "3d", f"{DEFAULT_BUCKET_SCHEME}://managed/enhanced/3d"),
            ("target_enhanced_2d", self.repository_root / "managed" / "enhanced" / "2d", f"{DEFAULT_BUCKET_SCHEME}://managed/enhanced/2d"),
        ]

        items: list[StorageArtifactInventoryItem] = []
        for artifact_kind, root, uri_prefix in target_roots:
            for child in _directory_children(root):
                dimension = "3d" if artifact_kind.endswith("_3d") else "2d"
                items.append(
                    StorageArtifactInventoryItem(
                        artifact_kind=artifact_kind,
                        current_path=str(child),
                        current_uri=f"{uri_prefix}/{child.name}",
                        name=child.name,
                        exists=child.exists(),
                        is_dir=child.is_dir(),
                        size_bytes=_safe_stat_size(child),
                        inferred_dimension=dimension,
                        suggested_endrepo_uri=f"{uri_prefix}/{child.name}",
                        migration_status="already_in_target_bucket",
                    )
                )

        return items


    @staticmethod
    def _relative_path_from_endrepo_uri(parsed: Any) -> str:
        # urlparse("endrepo://managed/zarr/3d/a.zarr") gives:
        #   netloc="managed", path="/zarr/3d/a.zarr"
        # Treat netloc as the first path segment for bucket-style URIs.
        parts: list[str] = []

        if parsed.netloc:
            parts.append(unquote(parsed.netloc).strip("/"))

        if parsed.path:
            parts.extend(
                segment
                for segment in unquote(parsed.path).split("/")
                if segment
            )

        if parsed.params or parsed.query or parsed.fragment:
            raise ValueError("Storage URI must not include params, query, or fragment.")

        if not parts:
            raise ValueError("Storage URI must include a repository-relative path.")

        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("Storage URI contains an invalid path segment.")

        return "/".join(parts)


@dataclass(frozen=True)
class StorageArtifactInventoryItem:
    artifact_kind: str
    current_path: str
    current_uri: str | None
    name: str
    exists: bool
    is_dir: bool
    size_bytes: int | None
    inferred_dimension: str | None
    suggested_endrepo_uri: str | None
    migration_status: str


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _safe_artifact_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Managed artifact id is required.")

    candidate = Path(text).name
    if candidate != text or candidate in {"", ".", ".."} or ".." in Path(candidate).parts:
        raise ValueError("Managed artifact id must be a simple file/directory name.")

    return candidate


def is_endrepo_zarr_url(value: str | None) -> bool:
    text = str(value or "").strip()
    return text.startswith(ENDREPO_MANAGED_ZARR_URL_PREFIX.rstrip("/") + "/")


def endrepo_zarr_url_to_storage_uri(value: str) -> str:
    text = str(value or "").strip()
    prefix = ENDREPO_MANAGED_ZARR_URL_PREFIX.rstrip("/") + "/"

    if not text.startswith(prefix):
        raise ValueError("Not an EndRepo managed Zarr URL.")

    suffix = text[len(prefix):].strip("/")
    if not suffix:
        raise ValueError("EndRepo managed Zarr URL is missing a path.")

    return f"{DEFAULT_BUCKET_SCHEME}://managed/zarr/{suffix}"


def resolve_endrepo_zarr_url_path(value: str) -> Path:
    return Path(storage_service().resolve_endrepo_zarr_url(value).local_path)


def _safe_stat_size(path: Path) -> int | None:
    try:
        if path.is_file():
            return path.stat().st_size
    except OSError:
        return None
    return None


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        if path.exists() and path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def _infer_dimension_from_metadata(path: Path) -> str | None:
    candidates = [
        path / "viewer_metadata.json",
        path / ".zattrs",
        path / "zarr.json",
    ]

    for candidate in candidates:
        payload = _read_json_file(candidate)
        if not payload:
            continue

        if payload.get("is_3d") is True:
            return "3d"
        if payload.get("is_3d") is False:
            return "2d"

        shape = payload.get("shape")
        if isinstance(shape, list):
            if len(shape) >= 3:
                return "3d"
            if len(shape) == 2:
                return "2d"

        zarr_meta = payload.get("zarr")
        if isinstance(zarr_meta, dict):
            if zarr_meta.get("is_3d") is True:
                return "3d"
            if zarr_meta.get("is_3d") is False:
                return "2d"
            zarr_shape = zarr_meta.get("shape")
            if isinstance(zarr_shape, list):
                if len(zarr_shape) >= 3:
                    return "3d"
                if len(zarr_shape) == 2:
                    return "2d"

    return None


def _zarr_target_uri(name: str, dimension: str | None) -> str | None:
    if dimension not in {"2d", "3d"}:
        return None
    return f"{DEFAULT_BUCKET_SCHEME}://managed/zarr/{dimension}/{name}"


def _directory_children(path: Path) -> list[Path]:
    try:
        if path.exists() and path.is_dir():
            return sorted(path.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return []
    return []



def _migration_candidate_from_inventory_item(item: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a verbose inventory item into a compact read-only migration-plan candidate.

    This function is intentionally read-only. It does not touch storage, MSI,
    manifests, or artifact files.
    """
    artifact_kind = str(item.get("artifact_kind") or "").strip()
    migration_status = str(item.get("migration_status") or "").strip()
    suggested_uri = item.get("suggested_endrepo_uri")
    inferred_dimension = item.get("inferred_dimension")

    notes: list[str] = []
    review_required = False
    confidence = "medium"

    if migration_status == "review_required" or not suggested_uri:
        review_required = True
        confidence = "low"
        notes.append("No safe target URI could be inferred automatically.")

    if artifact_kind == "legacy_zarr":
        if inferred_dimension in {"2d", "3d"} and suggested_uri:
            confidence = "high"
            notes.append("Converted Zarr artifact with inferred 2D/3D target location.")
        else:
            review_required = True
            confidence = "low"
            notes.append("Zarr artifact requires review because 2D/3D dimension could not be inferred.")
    elif artifact_kind == "legacy_zarr_tmp":
        review_required = True
        confidence = "low"
        notes.append("Temporary Zarr artifact should be reviewed before any migration decision.")
    elif artifact_kind == "legacy_segy_index":
        if suggested_uri:
            confidence = "medium"
            notes.append("SEG-Y index artifact target suggested from legacy index location.")
        else:
            review_required = True
            confidence = "low"
            notes.append("SEG-Y index artifact requires review because no target URI was inferred.")
    elif artifact_kind == "legacy_job_record":
        confidence = "medium"
        notes.append("Job record can be copied to manifests/jobs if retained as historical conversion evidence.")
    else:
        review_required = True
        confidence = "low"
        notes.append("Unknown artifact kind requires manual review.")

    if migration_status == "already_in_target_bucket":
        review_required = False
        confidence = "high"
        notes.append("Artifact already appears to live in the End seismic repository target bucket.")

    return {
        "artifact_kind": artifact_kind,
        "current_path": item.get("current_path"),
        "current_uri": item.get("current_uri"),
        "name": item.get("name"),
        "exists": bool(item.get("exists")),
        "is_dir": bool(item.get("is_dir")),
        "size_bytes": item.get("size_bytes"),
        "inferred_dimension": inferred_dimension,
        "suggested_endrepo_uri": suggested_uri,
        "migration_status": migration_status,
        "confidence": confidence,
        "review_required": review_required,
        "notes": notes,
    }

def storage_service() -> EndSeismicRepositoryStorageService:
    return EndSeismicRepositoryStorageService()
