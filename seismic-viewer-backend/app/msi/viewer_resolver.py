from __future__ import annotations

import json
from pathlib import Path

from .repository import MSIRepository
from .lifecycle_service import MSILifecycleService
from .schemas import ResolveTargetRequest, ResolveTargetResponse, LoadedViewerTarget
from app.storage.service import ENDREPO_MANAGED_ZARR_URL_PREFIX, storage_service


class MSIViewerResolver:
    """
    Resolves frontend/viewer requests to backend-approved viewer targets.

    The viewer should open targets returned here instead of choosing raw paths,
    artifact folders, or representation types itself.
    """

    def __init__(self, repo: MSIRepository | None = None) -> None:
        self.repo = repo or MSIRepository()
        self.lifecycle_service = MSILifecycleService(self.repo)

    def resolve(self, request: ResolveTargetRequest) -> ResolveTargetResponse:
        if request.target_type == "representation":
            representation = self.repo.get_representation(request.target_id)
            if not representation:
                return ResolveTargetResponse(
                    loadable=False,
                    reason=f"Representation not found: {request.target_id}",
                )

            dataset = self.repo.get_dataset(representation.dataset_id)
            if not dataset:
                return ResolveTargetResponse(
                    loadable=False,
                    representation_id=representation.representation_id,
                    reason=f"Dataset not found for representation: {representation.representation_id}",
                )

            if not representation.viewer_ready or representation.lifecycle_state != "viewer_ready":
                lifecycle = self.lifecycle_service.lifecycle(dataset.dataset_id)
                return ResolveTargetResponse(
                    loadable=False,
                    dataset_id=dataset.dataset_id,
                    representation_id=representation.representation_id,
                    reason="Representation is not viewer-ready.",
                    available_actions=lifecycle.available_actions if lifecycle else [],
                )

            if request.preferred_mode and request.preferred_mode != "none":
                if representation.viewer_mode != request.preferred_mode:
                    return ResolveTargetResponse(
                        loadable=False,
                        dataset_id=dataset.dataset_id,
                        representation_id=representation.representation_id,
                        reason=f"Representation is not compatible with preferred mode: {request.preferred_mode}",
                    )

            return ResolveTargetResponse(
                loadable=True,
                dataset_id=dataset.dataset_id,
                representation_id=representation.representation_id,
                viewer_mode=representation.viewer_mode,
                representation_type=representation.representation_type,
                display_name=dataset.display_name,
            )

        dataset = self.repo.get_dataset(request.target_id)
        if not dataset:
            return ResolveTargetResponse(
                loadable=False,
                dataset_id=request.target_id,
                reason=f"Dataset not found: {request.target_id}",
            )

        representations = self.repo.list_representations(dataset.dataset_id)
        preferred = self.lifecycle_service._preferred_representation(
            representations,
            request.preferred_mode if request.preferred_mode != "none" else None,
        )

        lifecycle = self.lifecycle_service.lifecycle(dataset.dataset_id)

        if not preferred:
            return ResolveTargetResponse(
                loadable=False,
                dataset_id=dataset.dataset_id,
                reason="No viewer-ready representation exists.",
                available_actions=lifecycle.available_actions if lifecycle else [],
            )

        return ResolveTargetResponse(
            loadable=True,
            dataset_id=dataset.dataset_id,
            representation_id=preferred.representation_id,
            viewer_mode=preferred.viewer_mode,
            representation_type=preferred.representation_type,
            display_name=dataset.display_name,
        )



    def managed_volumes_compatible(self) -> list[dict]:
        """
        Return MSI catalog rows in a legacy Volume-compatible shape for Managed Data.

        This is intentionally different from loaded_volumes_compatible():
        - managed_volumes_compatible exposes available MSI viewer-ready representations
        - loaded_volumes_compatible exposes only representations currently loaded into viewer availability

        The frontend row id uses representation_id to avoid collision with legacy /api/volumes records.
        """
        from .repository import MSIRepository

        repo = MSIRepository()
        legacy_volumes_by_id = self._legacy_volume_by_id()

        datasets = repo.list_datasets()
        loaded_by_representation_id = {
            load.representation_id: load
            for load in repo.list_loaded_states()
            if load.loaded
        }

        out: list[dict] = []

        for dataset in datasets:
            representations = repo.list_representations(dataset.dataset_id)

            viewer_ready = [
                rep for rep in representations
                if (
                    rep.viewer_ready
                    and rep.viewer_mode in {"2d", "3d"}
                    and str(getattr(rep, "lifecycle_state", "") or "").strip() == "viewer_ready"
                    and self._storage_uri_exists(getattr(rep, "storage_uri", None))
                )
            ]

            if not viewer_ready:
                continue

            preferred = self._preferred_managed_representation(viewer_ready)
            if preferred is None:
                continue

            storage_uri = preferred.storage_uri or ""
            zarr_url = self._storage_uri_to_zarr_url(storage_uri)

            if not zarr_url:
                continue

            is_loaded = preferred.representation_id in loaded_by_representation_id

            row = self._make_msi_volume_compatible_row(
                dataset_id=dataset.dataset_id,
                representation_id=preferred.representation_id,
                display_name=dataset.display_name,
                dataset_type=dataset.dataset_type,
                viewer_mode=preferred.viewer_mode,
                representation_type=preferred.representation_type,
                storage_uri=storage_uri,
                zarr_url=zarr_url,
                is_loaded=is_loaded,
                hidden=not is_loaded,
                metadata={
                    "msi": True,
                    "survey_name": dataset.survey_name,
                    "line_name": dataset.line_name,
                    "volume_name": dataset.volume_name,
                    "processing_stage": dataset.processing_stage,
                    "processing_version": dataset.processing_version,
                    "source_reference": dataset.source_reference,
                    "representation": {
                        "representation_type": preferred.representation_type,
                        "viewer_mode": preferred.viewer_mode,
                        "viewer_ready": preferred.viewer_ready,
                        "is_preferred": preferred.is_preferred,
                        "lifecycle_state": preferred.lifecycle_state,
                    },
                },
            )

            legacy_volume_id = self._source_reference_volume_id(dataset)
            legacy_volume = legacy_volumes_by_id.get(legacy_volume_id or "")
            enriched = self._merge_legacy_volume_compat_fields(row, legacy_volume)
            self._validate_msi_volume_compatible_row(enriched)
            out.append(enriched)

        return out


    def _legacy_volume_by_id(self) -> dict[str, dict]:
        """
        Read legacy volume registry for compatibility enrichment only.

        MSI remains authoritative for lifecycle/load state. Legacy volume rows are
        used here only to preserve the existing viewer contract fields such as
        metadata.shape, metadata.zarr.shape, optimized_cache, and filename.
        """
        backend_dir = Path(__file__).resolve().parents[2]
        volumes_path = backend_dir / "data" / "volumes.json"

        if not volumes_path.exists():
            return {}

        try:
            raw = json.loads(volumes_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

        if isinstance(raw, dict):
            rows = raw.get("volumes") if isinstance(raw.get("volumes"), list) else list(raw.values())
        elif isinstance(raw, list):
            rows = raw
        else:
            rows = []

        out: dict[str, dict] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            volume_id = str(row.get("id") or row.get("volume_id") or "").strip()
            if volume_id:
                out[volume_id] = row

        return out

    @staticmethod
    def _source_reference_volume_id(dataset: object) -> str | None:
        source_reference = getattr(dataset, "source_reference", None)
        if not isinstance(source_reference, dict):
            return None

        value = source_reference.get("volume_id")
        if value is None:
            return None

        text = str(value).strip()
        return text or None

    @staticmethod
    def _merge_legacy_volume_compat_fields(row: dict, legacy_volume: dict | None) -> dict:
        if not legacy_volume:
            return row

        legacy_metadata = legacy_volume.get("metadata") if isinstance(legacy_volume.get("metadata"), dict) else {}
        row_metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}

        merged = {
            **row,
            "filename": row.get("filename") or legacy_volume.get("filename"),
            "display_name": row.get("display_name") or legacy_volume.get("display_name") or legacy_volume.get("filename"),
            "dataset_type": row.get("dataset_type") or legacy_volume.get("dataset_type"),
            "zarr_url": row.get("zarr_url") or legacy_volume.get("zarr_url"),
            "optimized_cache": legacy_volume.get("optimized_cache"),
            "optimized_cache_status": legacy_volume.get("optimized_cache_status"),
            "read_mode": row.get("read_mode") or legacy_volume.get("read_mode") or "zarr",
            "metadata": {
                **legacy_metadata,
                **row_metadata,
                "shape": row_metadata.get("shape") or legacy_metadata.get("shape"),
                "zarr": {
                    **(legacy_metadata.get("zarr") if isinstance(legacy_metadata.get("zarr"), dict) else {}),
                    **(row_metadata.get("zarr") if isinstance(row_metadata.get("zarr"), dict) else {}),
                },
            },
        }

        return merged

    @staticmethod
    def _preferred_managed_representation(representations: list) -> object | None:
        if not representations:
            return None

        rank_by_type = {
            "zarr_3d": 100,
            "zarr_2d": 95,
            "optimized_zarr_3d_cache": 80,
            "optimized_zarr_2d_cache": 75,
            "indexed_segy_2d": 50,
        }

        return sorted(
            representations,
            key=lambda rep: (
                1 if getattr(rep, "is_preferred", False) else 0,
                rank_by_type.get(str(getattr(rep, "representation_type", "")), 0),
                1 if getattr(rep, "storage_uri", None) else 0,
            ),
            reverse=True,
        )[0]


    def _make_msi_volume_compatible_row(
        self,
        *,
        dataset_id: str,
        representation_id: str,
        display_name: str,
        dataset_type: str,
        viewer_mode: str | None,
        representation_type: str | None,
        storage_uri: str | None,
        zarr_url: str | None,
        is_loaded: bool,
        hidden: bool,
        metadata: dict | None = None,
    ) -> dict:
        """
        Build the canonical frontend-compatible MSI row.

        MSI identity contract:
        - id == msi_representation_id
        - volume_id == msi_representation_id
        - physical_volume_id == underlying Zarr artifact id
        - managed and loaded rows for the same representation upsert into the
          same frontend row instead of creating duplicates.
        """
        physical_volume_id = self._volume_id_from_zarr_url(zarr_url)

        row = {
            "id": representation_id,
            "volume_id": representation_id,
            "physical_volume_id": physical_volume_id,
            "name": display_name,
            "display_name": display_name,
            "filename": display_name,
            "survey_name": (metadata or {}).get("survey_name"),
            "line_name": (metadata or {}).get("line_name"),
            "volume_name": (metadata or {}).get("volume_name"),
            "processing_stage": (metadata or {}).get("processing_stage"),
            "processing_version": (metadata or {}).get("processing_version"),
            "dataset_type": dataset_type,
            "zarr_url": zarr_url,
            "source": "msi",
            "registry_source": "msi",
            "msi_dataset_id": dataset_id,
            "msi_representation_id": representation_id,
            "viewer_mode": viewer_mode,
            "representation_type": representation_type,
            "storage_uri": storage_uri,
            "is_loaded": bool(is_loaded),
            "loaded_from_msi": bool(is_loaded),
            "hidden": bool(hidden),
            "metadata": metadata or {},
        }

        self._validate_msi_volume_compatible_row(row)
        return row

    @staticmethod
    def _validate_msi_volume_compatible_row(row: dict) -> None:
        representation_id = row.get("msi_representation_id")

        if not representation_id:
            raise ValueError("MSI compatible row missing msi_representation_id")

        if row.get("id") != representation_id:
            raise ValueError(
                "MSI compatible row id must equal msi_representation_id: "
                f"id={row.get('id')!r}, msi_representation_id={representation_id!r}"
            )

        if row.get("volume_id") != representation_id:
            raise ValueError(
                "MSI compatible row volume_id must equal msi_representation_id: "
                f"volume_id={row.get('volume_id')!r}, msi_representation_id={representation_id!r}"
            )

        if row.get("source") != "msi" or row.get("registry_source") != "msi":
            raise ValueError("MSI compatible row must be marked source=msi and registry_source=msi")

        if not row.get("zarr_url"):
            raise ValueError("MSI compatible row missing zarr_url")

        if not row.get("storage_uri"):
            raise ValueError("MSI compatible row missing storage_uri")


    def loaded_volumes_compatible(self) -> list[dict]:
        """
        Return MSI loaded viewer targets in a legacy Volume-compatible shape.

        Purpose:
        - allow the existing viewer dropdown contract to consume MSI-owned load state
        - expose only MSI loaded representations
        - do not infer loadability from files/folders in the frontend
        """
        loaded_targets = self.loaded_targets()
        out: list[dict] = []

        for target in loaded_targets:
            representation_id = target.representation_id
            dataset_id = target.dataset_id
            storage_uri = target.storage_uri or ""
            display_name = target.display_name or dataset_id
            dataset = self.repo.get_dataset(dataset_id)

            zarr_url = self._storage_uri_to_zarr_url(storage_uri)

            dataset_type = "unknown"
            if target.representation_type == "zarr_3d" or target.viewer_mode == "3d":
                dataset_type = "3d_volume"
            elif target.representation_type == "zarr_2d" or target.viewer_mode == "2d":
                dataset_type = "2d_line"

            out.append(
                self._make_msi_volume_compatible_row(
                    dataset_id=dataset_id,
                    representation_id=representation_id,
                    display_name=display_name,
                    dataset_type=dataset_type,
                    viewer_mode=target.viewer_mode,
                    representation_type=target.representation_type,
                    storage_uri=storage_uri,
                    zarr_url=zarr_url,
                    is_loaded=True,
                    hidden=False,
                    metadata={
                        "msi": True,
                        "survey_name": dataset.survey_name if dataset else None,
                        "line_name": dataset.line_name if dataset else None,
                        "volume_name": dataset.volume_name if dataset else None,
                        "processing_stage": dataset.processing_stage if dataset else None,
                        "processing_version": dataset.processing_version if dataset else None,
                        "source_reference": dataset.source_reference if dataset else {},
                    },
                )
            )

        return out


    def compatibility_identity_audit(self) -> dict:
        managed = self.managed_volumes_compatible()
        loaded = self.loaded_volumes_compatible()

        rows = [
            {"source_endpoint": "managed", **row}
            for row in managed
        ] + [
            {"source_endpoint": "loaded", **row}
            for row in loaded
        ]

        issues = []
        by_representation: dict[str, list[dict]] = {}

        for row in rows:
            rep = row.get("msi_representation_id")
            by_representation.setdefault(str(rep), []).append(row)

            if row.get("id") != rep:
                issues.append({
                    "issue": "id_mismatch",
                    "endpoint": row.get("source_endpoint"),
                    "id": row.get("id"),
                    "msi_representation_id": rep,
                })

            if row.get("volume_id") != rep:
                issues.append({
                    "issue": "volume_id_mismatch",
                    "endpoint": row.get("source_endpoint"),
                    "volume_id": row.get("volume_id"),
                    "msi_representation_id": rep,
                })

            if row.get("source") != "msi" or row.get("registry_source") != "msi":
                issues.append({
                    "issue": "source_marker_mismatch",
                    "endpoint": row.get("source_endpoint"),
                    "source": row.get("source"),
                    "registry_source": row.get("registry_source"),
                })

        by_representation_summary = {}
        for rep, rep_rows in by_representation.items():
            row_ids = sorted({
                str(row.get("id"))
                for row in rep_rows
                if row.get("id")
            })
            physical_ids = sorted({
                str(row.get("physical_volume_id"))
                for row in rep_rows
                if row.get("physical_volume_id")
            })

            if len(row_ids) > 1:
                issues.append({
                    "issue": "representation_has_multiple_frontend_ids",
                    "msi_representation_id": rep,
                    "row_ids": row_ids,
                })

            by_representation_summary[rep] = {
                "row_count": len(rep_rows),
                "row_ids": row_ids,
                "physical_volume_ids": physical_ids,
                "endpoints": sorted({str(row.get("source_endpoint")) for row in rep_rows}),
            }

        return {
            "ok": len(issues) == 0,
            "managed_count": len(managed),
            "loaded_count": len(loaded),
            "issues": issues,
            "by_representation": by_representation_summary,
        }



    @staticmethod
    def _storage_uri_exists(storage_uri: str | None) -> bool:
        text = str(storage_uri or "").strip()
        if not text:
            return False

        if text.startswith("endrepo://"):
            try:
                return storage_service().resolve_uri(text).exists
            except Exception:
                return False

        if text.startswith("local://zarr/"):
            backend_dir = Path(__file__).resolve().parents[2]
            name = text.replace("local://zarr/", "", 1)
            return (backend_dir / "data" / "zarr" / name).exists()

        if text.startswith("/data/zarr/"):
            backend_dir = Path(__file__).resolve().parents[2]
            return (backend_dir / text.lstrip("/")).exists()

        if text.startswith("/endrepo/managed/zarr/"):
            # Convert local prototype EndRepo URL back into its logical URI.
            suffix = text.replace("/endrepo/", "", 1)
            try:
                return storage_service().resolve_uri(f"endrepo://{suffix}").exists
            except Exception:
                return False

        return False


    @staticmethod
    def _storage_uri_to_zarr_url(storage_uri: str) -> str | None:
        if not storage_uri:
            return None

        if storage_uri.startswith("endrepo://managed/zarr/"):
            suffix = storage_uri.replace("endrepo://managed/zarr/", "", 1).strip("/")
            return f"{ENDREPO_MANAGED_ZARR_URL_PREFIX}/{suffix}"

        if storage_uri.startswith("local://zarr/"):
            name = storage_uri.replace("local://zarr/", "", 1)
            return f"/data/zarr/{name}"

        if storage_uri.startswith("/data/zarr/"):
            return storage_uri

        if storage_uri.startswith(ENDREPO_MANAGED_ZARR_URL_PREFIX.rstrip("/") + "/"):
            return storage_uri

        return None

    @staticmethod
    def _volume_id_from_zarr_url(zarr_url: str | None) -> str | None:
        if not zarr_url:
            return None

        name = zarr_url.rstrip("/").split("/")[-1]
        if name.endswith(".zarr"):
            return name[:-5]

        return name or None

    def loaded_targets(self) -> list[LoadedViewerTarget]:
        loads = self.repo.list_loaded_states()
        targets: list[LoadedViewerTarget] = []

        for load in loads:
            dataset = self.repo.get_dataset(load.dataset_id)
            representation = self.repo.get_representation(load.representation_id)

            if not dataset or not representation:
                continue

            if not representation.viewer_ready or representation.lifecycle_state != "viewer_ready":
                continue

            targets.append(
                LoadedViewerTarget(
                    dataset_id=dataset.dataset_id,
                    representation_id=representation.representation_id,
                    viewer_mode=representation.viewer_mode,
                    representation_type=representation.representation_type,
                    display_name=dataset.display_name,
                    storage_uri=representation.storage_uri,
                )
            )

        return targets
