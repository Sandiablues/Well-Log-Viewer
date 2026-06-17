"""WLV Source Intake service.

The service is the WLV analogue of Seismic Source Intake for discovery and
candidate creation, but it deliberately has no conversion lifecycle. Later
blocks will parse, classify, QAQC, register to MSI / Managed Well Inventory,
stage to WMDP, and load selected data to WDV.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Any

from ..ingestion.las_adapter import LasAdapterError, LasSourceAdapter
from app.inventory.models import (
    ManagedInventoryLifecycleState,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedWdvState,
    ManagedWellRecord,
    ManagedWmdpState,
)
from app.wbv.models import WbvCoordinateMode, WbvManagedTrajectoryRecord, WbvManagedTrajectoryStatus


from .metadata_resolver import resolve_candidate_metadata
from .identity_gate import apply_identity_gate
from .qaqc import run_source_intake_qaqc
from .registration import register_candidate_to_inventory, registration_block_reason
from .resolution_service import (
    SourceIntakeResolutionError,
    SourceIntakeResolutionService,
    occurrence_identity,
)
from .deviation_survey_parser import DeviationSurveyParseError, parse_deviation_survey_preview

from .models import (
    SourceFileCandidate,
    SourceIntakeCandidateDiagnosticSummary,
    SourceIntakeCandidateDiagnostics,
    SourceIntakeCandidateRole,
    SourceIntakeClearResponse,
    SourceIntakeDiagnosticAction,
    SourceIntakeDiagnosticFlag,
    SourceIntakeDiagnosticPhase,
    SourceIntakeDiagnosticSeverity,
    SourceIntakeFileType,
    SourceIntakeLogHeader,
    SourceIntakeParseStatus,
    SourceIntakeParsedMetadata,
    SourceIntakeQaqcStatus,
    SourceIntakeRegisterRequest,
    SourceIntakeRegisterResponse,
    SourceIntakeRegisterResult,
    SourceIntakeBulkResolutionRequest,
    SourceIntakeBulkResolutionResponse,
    SourceIntakeRepositoryStatus,
    SourceIntakeWellHeader,
    SourceIntakeCurveHeader,
    SourceIntakeSnapshot,
    SourceIntakeWorkbench,
    SourceIntakeWorkbenchSummary,
    SourceRepositoryCreateRequest,
    SourceRepositoryRecord,
    SourceRepositoryRemoveResponse,
    SourceRepositoryScanResult,
    utc_now_iso,
)


class SourceIntakeError(ValueError):
    """Raised when source intake cannot complete a requested operation."""


class WlvSourceIntakeService:
    """Backend-owned WLV source intake discovery service."""

    def __init__(self, storage_path: Path | None = None) -> None:
        if storage_path is None:
            backend_root = Path(__file__).resolve().parents[2]
            storage_path = backend_root / "data" / "source_intake" / "source_intake.json"
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.resolution_service = SourceIntakeResolutionService()

    def health(self) -> dict[str, object]:
        snapshot = self._load_snapshot()
        return {
            "ok": True,
            "service": "wlv-source-intake",
            "scope": "source_intake_foundation",
            "storage_backend": "local_json",
            "storage_path": str(self.storage_path),
            "repository_count": len(snapshot.repositories),
            "candidate_count": len(snapshot.candidates),
            "conversion_step_enabled": False,
            "reserved_future_representation_step": True,
        }

    def create_repository(self, request: SourceRepositoryCreateRequest) -> SourceRepositoryRecord:
        root = Path(request.root_path).expanduser().resolve()
        if not root.exists():
            raise SourceIntakeError(f"Source repository path does not exist: {root}")
        if not root.is_dir():
            raise SourceIntakeError(f"Source repository path is not a folder: {root}")

        snapshot = self._load_snapshot()
        repository_id = self._repository_id(root)
        existing = next((repo for repo in snapshot.repositories if repo.repository_id == repository_id), None)
        now = utc_now_iso()

        if existing is not None:
            existing.name = request.name or root.name or existing.name
            existing.root_path = str(root)
            existing.include_subfolders = request.include_subfolders
            existing.status = SourceIntakeRepositoryStatus.AVAILABLE
            existing.updated_at = now
            self._save_snapshot(snapshot)
            return existing

        record = SourceRepositoryRecord(
            repository_id=repository_id,
            name=request.name or root.name or str(root),
            root_path=str(root),
            include_subfolders=request.include_subfolders,
            status=SourceIntakeRepositoryStatus.AVAILABLE,
        )
        snapshot.repositories.append(record)
        self._save_snapshot(snapshot)
        return record

    def list_repositories(self) -> list[SourceRepositoryRecord]:
        return self._load_snapshot().repositories

    def remove_repository(self, repository_id: str) -> SourceRepositoryRemoveResponse:
        # WLV-WSI-REMOVE-SOURCE-1:
        # "Remove Source" removes the Source Intake repository record and its
        # current candidate rows from WSI. It must not delete files on disk,
        # Managed Well Inventory records, MDP state, or WDV session data.
        snapshot = self._load_snapshot()
        repository = next((repo for repo in snapshot.repositories if repo.repository_id == repository_id), None)
        if repository is None:
            raise SourceIntakeError(f"Source repository not found: {repository_id}")

        candidate_rows_removed = sum(
            1 for candidate in snapshot.candidates if candidate.repository_id == repository_id
        )
        snapshot.repositories = [
            repo for repo in snapshot.repositories if repo.repository_id != repository_id
        ]
        snapshot.candidates = [
            candidate for candidate in snapshot.candidates if candidate.repository_id != repository_id
        ]
        snapshot.updated_at = utc_now_iso()
        self._save_snapshot(snapshot)

        return SourceRepositoryRemoveResponse(
            repository_id=repository_id,
            repository_removed=True,
            candidate_rows_removed=candidate_rows_removed,
            message=(
                f"Removed source repository {repository.name} from Source Intake. "
                f"Removed {candidate_rows_removed} associated candidate row"
                f"{'s' if candidate_rows_removed != 1 else ''}. "
                "Source files and managed inventory were not deleted."
            ),
            workbench=self.get_workbench(),
        )

    def scan_repository(self, repository_id: str, include_subfolders: bool | None = None) -> SourceRepositoryScanResult:
        snapshot = self._load_snapshot()
        repository = self._get_repository(snapshot, repository_id)
        root = Path(repository.root_path)
        if not root.exists() or not root.is_dir():
            repository.status = SourceIntakeRepositoryStatus.MISSING
            repository.updated_at = utc_now_iso()
            self._save_snapshot(snapshot)
            raise SourceIntakeError(f"Source repository path is unavailable: {root}")

        use_subfolders = repository.include_subfolders if include_subfolders is None else include_subfolders
        scan_scope = "root_plus_subfolders" if use_subfolders else "root_only"
        scan_id = self._scan_id(repository_id=repository_id, root=root, scan_scope=scan_scope)

        files = list(self._iter_files(root, include_subfolders=use_subfolders))
        candidates = [self._candidate_for_file(repository.repository_id, scan_id, root, file_path) for file_path in files]
        apply_identity_gate(candidates)
        for candidate in candidates:
            candidate.qaqc_status = run_source_intake_qaqc(candidate)
            candidate.review_required = candidate.review_required or candidate.qaqc_status.review_required

        candidates = self.resolution_service.initialize_candidates(candidates)

        snapshot.candidates = [candidate for candidate in snapshot.candidates if candidate.repository_id != repository_id]
        snapshot.candidates.extend(candidates)

        self._apply_counts(repository, candidates)
        repository.status = SourceIntakeRepositoryStatus.SCANNED
        repository.last_scan_id = scan_id
        repository.last_scan_scope = scan_scope
        repository.updated_at = utc_now_iso()

        self._save_snapshot(snapshot)
        return SourceRepositoryScanResult(
            ok=True,
            repository=repository,
            scan_id=scan_id,
            scan_scope=scan_scope,
            file_count=len(candidates),
            candidates=candidates,
        )

    def get_workbench(self) -> SourceIntakeWorkbench:
        snapshot = self._load_snapshot()
        return SourceIntakeWorkbench(
            summary=self._summary(snapshot.repositories, snapshot.candidates),
            repositories=snapshot.repositories,
            candidates=snapshot.candidates,
        )

    def get_candidate_diagnostics(self, candidate_id: str) -> SourceIntakeCandidateDiagnostics:
        # WLV-WSI-FLAGS-DETAIL-1:
        # The backend owns diagnostic phase flags and action descriptors. The
        # frontend renders this contract and does not infer parse, QAQC, or MDP
        # readiness truth.
        snapshot = self._load_snapshot()
        candidate = next((item for item in snapshot.candidates if item.source_file_id == candidate_id), None)
        if candidate is None:
            raise SourceIntakeError(f"Source Intake candidate not found: {candidate_id}")
        return self._candidate_diagnostics(candidate)

    def resolve_candidates(
        self,
        request: SourceIntakeBulkResolutionRequest,
    ) -> SourceIntakeBulkResolutionResponse:
        """Persist backend-owned post-scan review decisions."""
        snapshot = self._load_snapshot()
        try:
            response = self.resolution_service.apply_bulk(snapshot.candidates, request)
        except SourceIntakeResolutionError as exc:
            raise SourceIntakeError(str(exc)) from exc
        self._save_snapshot(snapshot)
        return response

    def clear_workbench_selection(
        self,
        repository_id: str | None = None,
        candidate_ids: list[str] | None = None,
    ) -> SourceIntakeClearResponse:
        # WLV-WSI-CLEAR-CANDIDATE-ROWS-1:
        # "Clear Selection" means remove selected rows from the active Source
        # Intake candidate register. It must not delete source files, source
        # repositories, Managed Well Inventory records, WMDP state, or WDV state.
        snapshot = self._load_snapshot()
        selected_ids = {candidate_id for candidate_id in (candidate_ids or []) if candidate_id}

        if not selected_ids:
            return SourceIntakeClearResponse(workbench=self.get_workbench())

        before_count = len(snapshot.candidates)
        affected_repository_ids = {
            candidate.repository_id
            for candidate in snapshot.candidates
            if candidate.source_file_id in selected_ids
        }
        if repository_id:
            affected_repository_ids.add(repository_id)

        snapshot.candidates = [
            candidate
            for candidate in snapshot.candidates
            if candidate.source_file_id not in selected_ids
        ]
        rows_removed = before_count - len(snapshot.candidates)

        if rows_removed > 0:
            for repository in snapshot.repositories:
                if repository.repository_id in affected_repository_ids:
                    repository_candidates = [
                        candidate
                        for candidate in snapshot.candidates
                        if candidate.repository_id == repository.repository_id
                    ]
                    self._apply_counts(repository, repository_candidates)
                    repository.updated_at = utc_now_iso()
            self._save_snapshot(snapshot)

        return SourceIntakeClearResponse(
            action="clear_candidate_register_rows",
            destructive=False,
            records_deleted=rows_removed,
            message=(
                f"Removed {rows_removed} selected candidate row"
                f"{'s' if rows_removed != 1 else ''} from the Source Intake register. "
                "Source files and managed inventory were not deleted."
            ),
            workbench=self.get_workbench(),
        )

    def register_candidates(self, request: SourceIntakeRegisterRequest, inventory_service=None) -> SourceIntakeRegisterResponse:
        """Register approved intake candidates to Managed Well Inventory.

        This is the first controlled handoff from Source Intake into MSI/WMDP
        managed inventory. It does not load the WDV and does not create a viewer
        representation/conversion.
        """
        if inventory_service is None:
            from app.inventory.service import ManagedWellInventoryService
            inventory_service = ManagedWellInventoryService()

        snapshot = self._load_snapshot()
        candidates_by_id = {candidate.source_file_id: candidate for candidate in snapshot.candidates}
        results: list[SourceIntakeRegisterResult] = []
        registered_count = 0
        skipped_count = 0
        snapshot_changed = False

        for candidate_id in request.candidate_ids:
            candidate = candidates_by_id.get(candidate_id)
            if candidate is None:
                skipped_count += 1
                results.append(SourceIntakeRegisterResult(
                    candidate_id=candidate_id,
                    status="skipped",
                    reason="Candidate not found in Source Intake workbench.",
                ))
                continue

            if candidate.candidate_role == SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE:
                blocked_reason = self._registration_block_reason(candidate)
                if blocked_reason is not None:
                    skipped_count += 1
                    results.append(SourceIntakeRegisterResult(
                        candidate_id=candidate.source_file_id,
                        status="blocked",
                        reason=blocked_reason,
                    ))
                    continue

                action, record, trajectory_count = self._register_geometry_candidate_to_inventory(
                    candidate=candidate,
                    inventory_service=inventory_service,
                    approved_by=request.approval.approved_by,
                    approval_note=request.approval.approval_note,
                )
                candidate.registration_status = "registered"
                candidate.managed_well_id = record.managed_well_id
                candidate.managed_well_name = record.well_name
                candidate.wmdp_state = record.wmdp_state.value if hasattr(record.wmdp_state, "value") else str(record.wmdp_state)
                candidate.wdv_state = record.wdv_state.value if hasattr(record.wdv_state, "value") else str(record.wdv_state)
                candidate.registered_product_count = 0
                candidate.registered_curve_count = 0
                candidate.registered_trajectory_count = trajectory_count
                snapshot_changed = True
                registered_count += 1
                results.append(SourceIntakeRegisterResult(
                    candidate_id=candidate.source_file_id,
                    status="registered",
                    reason=None,
                    managed_well_id=record.managed_well_id,
                    well_id=record.well_id,
                    well_name=record.well_name,
                    registered_product_count=0,
                    registered_curve_count=0,
                    registered_trajectory_count=trajectory_count,
                    action=action,
                ))
                continue

            blocked_reason = self._registration_block_reason(candidate)
            if blocked_reason is not None:
                skipped_count += 1
                results.append(SourceIntakeRegisterResult(
                    candidate_id=candidate.source_file_id,
                    status="blocked",
                    reason=blocked_reason,
                ))
                continue

            action, record = register_candidate_to_inventory(
                candidate=candidate,
                inventory_service=inventory_service,
                approved_by=request.approval.approved_by,
                approval_note=request.approval.approval_note,
            )
            registered_curve_count = sum(len(group.items) for group in record.product_groups)
            registered_product_count = sum(1 for group in record.product_groups if group.items)
            candidate.registration_status = "registered"
            candidate.managed_well_id = record.managed_well_id
            candidate.managed_well_name = record.well_name
            candidate.wmdp_state = record.wmdp_state.value if hasattr(record.wmdp_state, "value") else str(record.wmdp_state)
            candidate.wdv_state = record.wdv_state.value if hasattr(record.wdv_state, "value") else str(record.wdv_state)
            candidate.registered_product_count = registered_product_count
            candidate.registered_curve_count = registered_curve_count
            snapshot_changed = True
            registered_count += 1
            results.append(SourceIntakeRegisterResult(
                candidate_id=candidate.source_file_id,
                status="registered",
                reason=None,
                managed_well_id=record.managed_well_id,
                well_id=record.well_id,
                well_name=record.well_name,
                registered_product_count=registered_product_count,
                registered_curve_count=registered_curve_count,
                action=action,
            ))

        if snapshot_changed:
            self._save_snapshot(snapshot)

        return SourceIntakeRegisterResponse(
            registered_count=registered_count,
            skipped_count=skipped_count,
            results=results,
            workbench=self.get_workbench(),
        )

    def _registration_block_reason(self, candidate: SourceFileCandidate) -> str | None:
        if candidate.candidate_role == SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE:
            return self._geometry_registration_block_reason(candidate)
        return registration_block_reason(candidate)

    def _geometry_registration_block_reason(self, candidate: SourceFileCandidate) -> str | None:
        if candidate.candidate_role != SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE:
            return f"Only wellbore_geometry_candidate records can use geometry registration; got {candidate.candidate_role.value}."
        if candidate.registration_status == "registered":
            return "Candidate is already registered to Managed Well Inventory."
        if candidate.parser_status not in {SourceIntakeParseStatus.PARSED, SourceIntakeParseStatus.PARSED_WITH_WARNINGS}:
            return f"Geometry candidate parser_status is not registration-ready: {candidate.parser_status.value}."
        if candidate.geometry_preview is None:
            return "Geometry candidate has no parsed deviation-survey preview."
        if not candidate.geometry_preview.stations_preview:
            return "Geometry candidate preview has no station payload to register."
        if candidate.qaqc_status.status not in {
            SourceIntakeQaqcStatus.PASS,
            SourceIntakeQaqcStatus.WARNING,
            SourceIntakeQaqcStatus.REVIEW_REQUIRED,
        }:
            return f"Geometry candidate QAQC status is not registration-ready: {candidate.qaqc_status.status.value}."
        if candidate.qaqc_status.failure_count > 0:
            return "Geometry candidate QAQC has failures and cannot be registered."
        return None

    def _register_geometry_candidate_to_inventory(
        self,
        *,
        candidate: SourceFileCandidate,
        inventory_service,
        approved_by: str | None = None,
        approval_note: str | None = None,
    ) -> tuple[str, ManagedWellRecord, int]:
        """Promote a parsed Source Intake geometry candidate into managed WBV trajectory metadata.

        GEOM-4 registers approved parsed deviation-survey previews as managed
        wellbore geometry records. It does not set the active trajectory and it
        does not load WBV/WDV.
        """
        blocked = self._geometry_registration_block_reason(candidate)
        if blocked is not None:
            raise ValueError(blocked)
        preview = candidate.geometry_preview
        assert preview is not None

        existing = self._match_existing_managed_well(candidate, inventory_service)
        well_name = existing.well_name if existing is not None else self._geometry_well_name(candidate)
        well_id = existing.well_id if existing is not None else self._managed_geometry_well_id(well_name)
        managed_well_id = existing.managed_well_id if existing is not None else f"managed-well:{well_id}"

        now = utc_now_iso()
        trajectory = self._managed_trajectory_from_geometry_candidate(candidate, well_name=well_name, approved_at=now)
        source_reference = self._geometry_source_reference(candidate, trajectory_id=trajectory.trajectory_id)

        if existing is not None:
            record = existing.model_copy(deep=True)
            action = "updated"
            existing_refs = list(record.source_references or [])
            if not any(ref.source_id == source_reference.source_id for ref in existing_refs):
                existing_refs.append(source_reference)
            record.source_references = existing_refs
            metadata = dict(record.metadata) if isinstance(record.metadata, dict) else {}
            lifecycle_notes = list(record.lifecycle_notes or [])
            product_groups = list(record.product_groups or [])
            created_at = record.created_at
        else:
            action = "created"
            metadata = {}
            lifecycle_notes = []
            product_groups = []
            created_at = now
            record = ManagedWellRecord(
                managed_well_id=managed_well_id,
                well_id=well_id,
                well_name=well_name,
                depth_unit="ft",
                status=ManagedInventoryLifecycleState.REGISTERED,
                lifecycle_state=ManagedInventoryLifecycleState.REGISTERED,
                wmdp_state=ManagedWmdpState.STAGED_IN_WMDP,
                wdv_state=ManagedWdvState.NOT_LOADED,
                source_intake_candidate_id=candidate.source_file_id,
                wmdp_available=True,
                source_references=[source_reference],
                product_groups=product_groups,
                tags=["source-intake", "wellbore-geometry"],
                metadata=metadata,
                lifecycle_notes=lifecycle_notes,
                created_at=created_at,
                updated_at=now,
            )

        existing_trajectories = self._metadata_trajectory_records(metadata)
        next_trajectories = [item for item in existing_trajectories if item.trajectory_id != trajectory.trajectory_id]
        next_trajectories.append(trajectory)
        metadata["wbv_trajectory_records"] = [item.model_dump(mode="json") for item in next_trajectories]
        metadata["wellbore_geometry_status"] = "registered_trajectory_available"
        metadata["wellbore_geometry_registered_count"] = len(next_trajectories)
        metadata["source_intake_geometry_registration"] = {
            "source_intake_candidate_id": candidate.source_file_id,
            "trajectory_id": trajectory.trajectory_id,
            "registered_at": now,
            "approved_by": approved_by,
            "approval_note": approval_note,
            "parser_status": candidate.parser_status.value,
            "qaqc_status": candidate.qaqc_status.model_dump(mode="json"),
        }
        metadata["wmdp_state"] = ManagedWmdpState.STAGED_IN_WMDP.value
        metadata["wdv_state"] = ManagedWdvState.NOT_LOADED.value
        metadata["wmdp_available"] = True

        tags = list(getattr(record, "tags", []) or [])
        for tag in ["source-intake", "wellbore-geometry"]:
            if tag not in tags:
                tags.append(tag)
        record.tags = tags
        record.metadata = metadata
        record.wmdp_state = ManagedWmdpState.STAGED_IN_WMDP
        record.wdv_state = ManagedWdvState.NOT_LOADED
        record.wmdp_available = True
        record.source_intake_candidate_id = candidate.source_file_id
        record.updated_at = now
        record.lifecycle_notes = lifecycle_notes + [
            f"Registered Source Intake wellbore geometry candidate {candidate.source_file_id} as trajectory {trajectory.trajectory_id}."
        ]

        result = inventory_service.upsert_managed_record(record)
        if isinstance(result, tuple):
            _, saved = result
            return action, saved, len(next_trajectories)
        return action, result, len(next_trajectories)

    def _managed_trajectory_from_geometry_candidate(
        self,
        candidate: SourceFileCandidate,
        *,
        well_name: str,
        approved_at: str,
    ) -> WbvManagedTrajectoryRecord:
        preview = candidate.geometry_preview
        assert preview is not None
        package = self._trajectory_package_from_geometry_preview(candidate, well_name=well_name)
        trajectory_id = f"traj:source-intake:{hashlib.sha1(candidate.source_file_id.encode('utf-8')).hexdigest()[:16]}"
        status = WbvManagedTrajectoryStatus.APPROVED
        return WbvManagedTrajectoryRecord(
            trajectory_id=trajectory_id,
            trajectory_name=f"{candidate.file_name} deviation survey",
            trajectory_type="deviation_survey",
            status=status,
            wbv_eligible=bool(package.get("render_points")),
            is_active=False,
            is_canonical=False,
            is_synthetic=False,
            source_file_id=candidate.source_file_id,
            source_label=candidate.file_name,
            station_count=preview.station_count,
            md_min=preview.md_min,
            md_max=preview.md_max,
            tvd_min=preview.tvd_min,
            tvd_max=preview.tvd_max,
            geometry_class="registered_deviation_survey_preview",
            coordinate_mode=WbvCoordinateMode.RELATIVE,
            trajectory_package=package,
            qa_flags=[message for message in preview.warnings[:10]],
            warnings=[{"code": "source_intake_preview_warning", "severity": "warning", "message": message} for message in preview.warnings[:10]],
            created_at=approved_at,
            approved_at=approved_at,
        )

    def _trajectory_package_from_geometry_preview(self, candidate: SourceFileCandidate, *, well_name: str) -> dict[str, Any]:
        preview = candidate.geometry_preview
        assert preview is not None
        stations = [station.model_dump(mode="json") for station in preview.stations_preview]
        render_points: list[dict[str, float]] = []
        for station in preview.stations_preview:
            tvd = station.tvd if station.tvd is not None else station.md
            x_value = station.x_offset if station.x_offset is not None else station.easting if station.easting is not None else 0.0
            y_value = station.y_offset if station.y_offset is not None else station.northing if station.northing is not None else 0.0
            render_points.append(
                {
                    "md": float(station.md),
                    "tvd": float(tvd),
                    "x": float(x_value),
                    "y": float(y_value),
                    "z": -float(tvd),
                }
            )
        bbox = self._geometry_bounding_box(render_points, preview)
        warnings = [
            {"code": "source_intake_preview_limited", "severity": "warning", "message": "Registered trajectory uses the bounded Source Intake preview station payload; full-station promotion can be added in a later block."}
        ]
        warnings.extend({"code": "source_intake_preview_warning", "severity": "warning", "message": message} for message in preview.warnings[:10])
        return {
            "method": "source_intake_preview_registration",
            "source": "source_intake_deviation_survey_preview",
            "source_type": "deviation_survey",
            "source_intake_candidate_id": candidate.source_file_id,
            "source_file_id": candidate.source_file_id,
            "source_label": candidate.file_name,
            "well_name": well_name,
            "coordinate_mode": WbvCoordinateMode.RELATIVE.value,
            "trajectory_class": "registered_deviation_survey_preview",
            "depth_unit": "ft",
            "angle_unit": "deg",
            "station_count": preview.station_count,
            "source_station_count": preview.station_count,
            "preview_station_count": preview.preview_station_count,
            "stations": stations,
            "render_points": render_points,
            "bounding_box": bbox,
            "column_mapping": preview.column_mapping.model_dump(mode="json"),
            "warnings": warnings,
        }

    @staticmethod
    def _geometry_bounding_box(render_points: list[dict[str, float]], preview) -> dict[str, Any]:
        box: dict[str, Any] = {
            "md": {"min": preview.md_min, "max": preview.md_max},
        }
        if preview.tvd_min is not None and preview.tvd_max is not None:
            box["tvd"] = {"min": preview.tvd_min, "max": preview.tvd_max}
        if render_points:
            for key in ["x", "y", "z"]:
                values = [point[key] for point in render_points]
                box[key] = {"min": min(values), "max": max(values)}
        return box

    def _geometry_source_reference(self, candidate: SourceFileCandidate, *, trajectory_id: str) -> ManagedSourceReference:
        return ManagedSourceReference(
            source_id=candidate.source_file_id,
            source_kind=ManagedSourceKind.DOCUMENT,
            display_name=candidate.file_name,
            original_path=candidate.original_path,
            file_name=candidate.file_name,
            file_format=candidate.detected_file_type.value,
            checksum=candidate.checksum,
            metadata={
                "source_intake_candidate_id": candidate.source_file_id,
                "repository_id": candidate.repository_id,
                "scan_id": candidate.scan_id,
                "relative_path": candidate.relative_path,
                "original_path": candidate.original_path,
                "checksum": candidate.checksum,
                "managed_record_class": "wellbore_geometry",
                "managed_record_type": "deviation_survey",
                "trajectory_id": trajectory_id,
                "parser_status": candidate.parser_status.value,
                "geometry_preview": candidate.geometry_preview.model_dump(mode="json") if candidate.geometry_preview else None,
            },
        )

    def _match_existing_managed_well(self, candidate: SourceFileCandidate, inventory_service) -> ManagedWellRecord | None:
        records = inventory_service.list_wells()
        if not records:
            return None
        candidate_text = self._normalize_identity_text(" ".join([candidate.file_name, candidate.relative_path]))
        for record in records:
            record_key = self._normalize_identity_text(record.well_name)
            if record_key and record_key in candidate_text:
                return record
        candidate_name = self._normalize_identity_text(self._geometry_well_name(candidate))
        for record in records:
            if self._normalize_identity_text(record.well_name) == candidate_name:
                return record
        return None

    @staticmethod
    def _metadata_trajectory_records(metadata: dict[str, Any]) -> list[WbvManagedTrajectoryRecord]:
        raw = metadata.get("wbv_trajectory_records") if isinstance(metadata, dict) else None
        records: list[WbvManagedTrajectoryRecord] = []
        if not isinstance(raw, list):
            return records
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                records.append(WbvManagedTrajectoryRecord(**item))
            except Exception:
                continue
        return records

    def _geometry_well_name(self, candidate: SourceFileCandidate) -> str:
        resolved = candidate.resolved_metadata.well_name.value if candidate.resolved_metadata and candidate.resolved_metadata.well_name else None
        if resolved:
            return str(resolved)
        stem = Path(candidate.file_name).stem
        cleaned = stem
        for token in [
            "final", "corrected", "preliminary", "prelim", "deviation", "directional", "survey",
            "trajectory", "wellbore", "geometry", "md", "inc", "incl", "azi", "azimuth", "tvd",
        ]:
            cleaned = cleaned.replace(token, " ").replace(token.upper(), " ").replace(token.title(), " ")
        cleaned = " ".join(part for part in cleaned.replace("_", " ").replace("-", " ").split() if part)
        return cleaned or stem

    @staticmethod
    def _managed_geometry_well_id(well_name: str) -> str:
        normalized = WlvSourceIntakeService._normalize_identity_text(well_name) or "geometry-well"
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
        return f"wlv-intake-name-{digest}"

    @staticmethod
    def _normalize_identity_text(value: str | None) -> str:
        return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())

    def _candidate_diagnostics(self, candidate: SourceFileCandidate) -> SourceIntakeCandidateDiagnostics:
        flags: list[SourceIntakeDiagnosticFlag] = []
        flags.extend(self._parse_diagnostic_flags(candidate))
        flags.extend(self._qaqc_diagnostic_flags(candidate))
        flags.extend(self._mdp_diagnostic_flags(candidate))

        return SourceIntakeCandidateDiagnostics(
            candidate_id=candidate.source_file_id,
            summary=SourceIntakeCandidateDiagnosticSummary(
                candidate_id=candidate.source_file_id,
                file_name=candidate.file_name,
                relative_path=candidate.relative_path,
                original_path=candidate.original_path,
                detected_file_type=candidate.detected_file_type,
                candidate_role=candidate.candidate_role,
                well_name=self._candidate_well_name(candidate),
                curve_count=self._candidate_curve_count(candidate),
                registration_status=candidate.registration_status,
                managed_well_id=candidate.managed_well_id,
                managed_well_name=candidate.managed_well_name,
            ),
            parse_status=candidate.parser_status,
            qaqc_status=candidate.qaqc_status,
            mdp_ready_status=self._mdp_ready_status(candidate),
            flags=flags,
            actions=self._diagnostic_actions(candidate),
        )

    def _parse_diagnostic_flags(self, candidate: SourceFileCandidate) -> list[SourceIntakeDiagnosticFlag]:
        status = candidate.parser_status
        if status == SourceIntakeParseStatus.PARSED:
            return [
                SourceIntakeDiagnosticFlag(
                    phase=SourceIntakeDiagnosticPhase.PARSE,
                    severity=SourceIntakeDiagnosticSeverity.SUCCESS,
                    code="parse_complete",
                    title="Parsed",
                    message="Content extraction completed and produced structured metadata.",
                )
            ]

        if status == SourceIntakeParseStatus.PARSED_WITH_WARNINGS:
            flags = [
                SourceIntakeDiagnosticFlag(
                    phase=SourceIntakeDiagnosticPhase.PARSE,
                    severity=SourceIntakeDiagnosticSeverity.WARNING,
                    code="parse_completed_with_warnings",
                    title="Parsed with warnings",
                    message="Content extraction completed, but parser warnings remain.",
                )
            ]
            for index, warning in enumerate(candidate.parsed_metadata.warnings if candidate.parsed_metadata else []):
                flags.append(
                    SourceIntakeDiagnosticFlag(
                        phase=SourceIntakeDiagnosticPhase.PARSE,
                        severity=SourceIntakeDiagnosticSeverity.WARNING,
                        code=f"parse_warning_{index + 1}",
                        title="Parser warning",
                        message=warning,
                    )
                )
            return flags

        if status == SourceIntakeParseStatus.PARSE_FAILED:
            return [
                SourceIntakeDiagnosticFlag(
                    phase=SourceIntakeDiagnosticPhase.PARSE,
                    severity=SourceIntakeDiagnosticSeverity.BLOCKER,
                    code="parse_failed",
                    title="Parse failed",
                    message=candidate.parse_error or "A parser attempted extraction and failed.",
                )
            ]

        if status == SourceIntakeParseStatus.UNSUPPORTED:
            return [
                SourceIntakeDiagnosticFlag(
                    phase=SourceIntakeDiagnosticPhase.PARSE,
                    severity=SourceIntakeDiagnosticSeverity.BLOCKER,
                    code="parse_unsupported",
                    title="Parser unsupported",
                    message=(
                        f"{candidate.detected_file_type.value} files are recognized, but no Source Intake parser "
                        "is currently implemented for this format."
                    ),
                )
            ]

        if status == SourceIntakeParseStatus.CONTAINER_PENDING_EXTRACTION:
            return [
                SourceIntakeDiagnosticFlag(
                    phase=SourceIntakeDiagnosticPhase.PARSE,
                    severity=SourceIntakeDiagnosticSeverity.BLOCKER,
                    code="container_pending_extraction",
                    title="Container pending extraction",
                    message="Archive/container content must be extracted and classified before it can be parsed or registered.",
                )
            ]

        return [
            SourceIntakeDiagnosticFlag(
                phase=SourceIntakeDiagnosticPhase.PARSE,
                severity=SourceIntakeDiagnosticSeverity.INFO,
                code="not_parsed",
                title="Not parsed",
                message="The file has been discovered, but content extraction has not completed yet.",
            )
        ]

    def _qaqc_diagnostic_flags(self, candidate: SourceFileCandidate) -> list[SourceIntakeDiagnosticFlag]:
        qaqc = candidate.qaqc_status
        flags: list[SourceIntakeDiagnosticFlag] = []

        if qaqc.checks:
            for check in qaqc.checks:
                severity = SourceIntakeDiagnosticSeverity.INFO
                if check.status == SourceIntakeQaqcStatus.FAIL:
                    severity = SourceIntakeDiagnosticSeverity.ERROR
                elif check.status in {SourceIntakeQaqcStatus.WARNING, SourceIntakeQaqcStatus.REVIEW_REQUIRED}:
                    severity = SourceIntakeDiagnosticSeverity.WARNING

                flags.append(
                    SourceIntakeDiagnosticFlag(
                        phase=SourceIntakeDiagnosticPhase.QAQC,
                        severity=severity,
                        code=check.check_id,
                        title=f"QAQC {check.status.value.replace('_', ' ')}",
                        message=check.message,
                        field_name=check.field_name,
                    )
                )

        if not flags:
            if qaqc.status == SourceIntakeQaqcStatus.PASS:
                flags.append(
                    SourceIntakeDiagnosticFlag(
                        phase=SourceIntakeDiagnosticPhase.QAQC,
                        severity=SourceIntakeDiagnosticSeverity.SUCCESS,
                        code="qaqc_pass",
                        title="QAQC passed",
                        message="No blocking QAQC findings are reported for this candidate.",
                    )
                )
            elif qaqc.status == SourceIntakeQaqcStatus.NOT_CHECKED:
                flags.append(
                    SourceIntakeDiagnosticFlag(
                        phase=SourceIntakeDiagnosticPhase.QAQC,
                        severity=SourceIntakeDiagnosticSeverity.INFO,
                        code="qaqc_not_checked",
                        title="QAQC not checked",
                        message="QAQC has not reported checks for this candidate yet.",
                    )
                )

        existing_messages = {flag.message for flag in flags}
        for index, message in enumerate(qaqc.messages):
            if message not in existing_messages:
                flags.append(
                    SourceIntakeDiagnosticFlag(
                        phase=SourceIntakeDiagnosticPhase.QAQC,
                        severity=SourceIntakeDiagnosticSeverity.WARNING,
                        code=f"qaqc_message_{index + 1}",
                        title="QAQC message",
                        message=message,
                    )
                )

        return flags

    def _mdp_diagnostic_flags(self, candidate: SourceFileCandidate) -> list[SourceIntakeDiagnosticFlag]:
        if candidate.registration_status == "registered":
            return [
                SourceIntakeDiagnosticFlag(
                    phase=SourceIntakeDiagnosticPhase.MDP_READY,
                    severity=SourceIntakeDiagnosticSeverity.SUCCESS,
                    code="registered_to_inventory",
                    title="Registered",
                    message=(
                        f"Candidate is registered to Managed Well Inventory"
                        f"{f' as {candidate.managed_well_name}' if candidate.managed_well_name else ''}."
                    ),
                )
            ]

        blocked_reason = self._registration_block_reason(candidate)
        if blocked_reason is not None:
            return [
                SourceIntakeDiagnosticFlag(
                    phase=SourceIntakeDiagnosticPhase.MDP_READY,
                    severity=SourceIntakeDiagnosticSeverity.BLOCKER,
                    code="mdp_registration_blocked",
                    title="Not ready for MDP",
                    message=blocked_reason,
                )
            ]

        return [
            SourceIntakeDiagnosticFlag(
                phase=SourceIntakeDiagnosticPhase.MDP_READY,
                severity=SourceIntakeDiagnosticSeverity.SUCCESS,
                code="mdp_ready",
                title="Ready for MDP",
                message="Candidate has the required backend-owned state for registration to Managed Well Inventory.",
            )
        ]

    def _diagnostic_actions(self, candidate: SourceFileCandidate) -> list[SourceIntakeDiagnosticAction]:
        actions: list[SourceIntakeDiagnosticAction] = []

        if candidate.parser_status == SourceIntakeParseStatus.CONTAINER_PENDING_EXTRACTION:
            actions.append(
                SourceIntakeDiagnosticAction(
                    phase=SourceIntakeDiagnosticPhase.PARSE,
                    action_key="extract_container",
                    label="Extract container",
                    enabled=False,
                    reason="Container extraction workflow is reserved for a later WSI representation/extraction block.",
                )
            )

        if candidate.parser_status == SourceIntakeParseStatus.PARSE_FAILED:
            actions.append(
                SourceIntakeDiagnosticAction(
                    phase=SourceIntakeDiagnosticPhase.PARSE,
                    action_key="retry_parse",
                    label="Retry parse",
                    enabled=False,
                    reason="Retry parse is not yet exposed as a Source Intake action.",
                )
            )

        if candidate.parser_status == SourceIntakeParseStatus.UNSUPPORTED:
            actions.append(
                SourceIntakeDiagnosticAction(
                    phase=SourceIntakeDiagnosticPhase.PARSE,
                    action_key="review_parser_support",
                    label="Review parser support",
                    enabled=False,
                    reason="Parser support must be added through the governed backend intake/parser layer.",
                )
            )

        if candidate.review_required or candidate.qaqc_status.review_required:
            actions.append(
                SourceIntakeDiagnosticAction(
                    phase=SourceIntakeDiagnosticPhase.QAQC,
                    action_key="review_metadata",
                    label="Review metadata",
                    enabled=False,
                    reason="Metadata review/approval action is planned but not enabled in this block.",
                )
            )

        blocked_reason = self._registration_block_reason(candidate)
        if blocked_reason is None and candidate.registration_status != "registered":
            actions.append(
                SourceIntakeDiagnosticAction(
                    phase=SourceIntakeDiagnosticPhase.MDP_READY,
                    action_key="register_candidate",
                    label="Register selected",
                    enabled=False,
                    reason="Use the table Select + Register Selected controls for this workflow.",
                )
            )

        if not actions:
            actions.append(
                SourceIntakeDiagnosticAction(
                    phase=SourceIntakeDiagnosticPhase.EVIDENCE,
                    action_key="no_action_required",
                    label="No action required",
                    enabled=False,
                    reason="No specific action is required for the current diagnostic state.",
                )
            )

        return actions

    def _mdp_ready_status(self, candidate: SourceFileCandidate) -> str:
        if candidate.registration_status == "registered":
            return "registered"
        blocked_reason = self._registration_block_reason(candidate)
        if blocked_reason is None:
            return "ready"
        if candidate.review_required or candidate.qaqc_status.review_required:
            return "needs_review"
        return "blocked"

    def _candidate_curve_count(self, candidate: SourceFileCandidate) -> int:
        if candidate.parsed_metadata is None:
            return 0
        if candidate.parsed_metadata.log_header is not None:
            return candidate.parsed_metadata.log_header.curve_count
        return len(candidate.parsed_metadata.curve_headers)

    def _candidate_well_name(self, candidate: SourceFileCandidate) -> str | None:
        if candidate.resolved_metadata and candidate.resolved_metadata.well_name.value:
            return candidate.resolved_metadata.well_name.value
        if candidate.parsed_metadata and candidate.parsed_metadata.well_header.well_name:
            return candidate.parsed_metadata.well_header.well_name
        return candidate.managed_well_name

    def _load_snapshot(self) -> SourceIntakeSnapshot:
        if not self.storage_path.exists():
            return SourceIntakeSnapshot()
        data = json.loads(self.storage_path.read_text())
        return SourceIntakeSnapshot(**data)

    def _save_snapshot(self, snapshot: SourceIntakeSnapshot) -> None:
        snapshot.updated_at = utc_now_iso()
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        if hasattr(snapshot, "model_dump_json"):
            payload = snapshot.model_dump_json(indent=2)
        else:
            payload = snapshot.json(indent=2)
        self.storage_path.write_text(payload)

    def _get_repository(self, snapshot: SourceIntakeSnapshot, repository_id: str) -> SourceRepositoryRecord:
        for repository in snapshot.repositories:
            if repository.repository_id == repository_id:
                return repository
        raise SourceIntakeError(f"Source repository not found: {repository_id}")

    def _iter_files(self, root: Path, include_subfolders: bool) -> Iterable[Path]:
        iterator = root.rglob("*") if include_subfolders else root.iterdir()
        return sorted(
            (path for path in iterator if path.is_file() and not _is_ignored_source_file(path)),
            key=lambda path: str(path).lower(),
        )

    def _candidate_for_file(self, repository_id: str, scan_id: str, root: Path, file_path: Path) -> SourceFileCandidate:
        checksum = self._sha256(file_path)
        detected_file_type, candidate_role = self._classify_file(file_path)
        review_required = candidate_role in {
            SourceIntakeCandidateRole.OTHER_REVIEW_REQUIRED,
            SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE,
        }
        warnings = ["File type requires review before WMDP staging."] if candidate_role == SourceIntakeCandidateRole.OTHER_REVIEW_REQUIRED else []
        if candidate_role == SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE:
            warnings.append(
                "Wellbore geometry candidate detected; structured deviation-survey preview is enabled, while trajectory registration remains reserved for a later Source Intake block."
            )
        relative_path = str(file_path.relative_to(root))
        stat = file_path.stat()
        modified_at = utc_now_iso()
        try:
            from datetime import datetime, timezone
            modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        except Exception:
            pass

        candidate = SourceFileCandidate(
            source_file_id=occurrence_identity(
                repository_id=repository_id,
                relative_path=relative_path,
                checksum=checksum,
            ),
            repository_id=repository_id,
            scan_id=scan_id,
            file_name=file_path.name,
            original_path=str(file_path),
            relative_path=relative_path,
            file_extension=file_path.suffix.lower().lstrip("."),
            detected_file_type=detected_file_type,
            candidate_role=candidate_role,
            size_bytes=stat.st_size,
            modified_at=modified_at,
            checksum=checksum,
            review_required=review_required,
            warnings=warnings,
        )

        # WLV-WSI-PARSE-STATUS-FILENAME-1:
        # Parser status is backend-owned and separate from QAQC status.
        # Discovery alone is not "parsed"; unsupported/container states are
        # explicit so the UI does not show every non-LAS record as Not Parsed.
        candidate.parser_status = self._initial_parser_status(file_path, detected_file_type)
        if candidate.candidate_role == SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE:
            self._attach_deviation_survey_preview(candidate, file_path)
        elif candidate.parser_status == SourceIntakeParseStatus.CONTAINER_PENDING_EXTRACTION:
            candidate.review_required = True
            candidate.warnings.append("Container/archive candidate pending extraction and child-file classification.")
        elif candidate.parser_status == SourceIntakeParseStatus.UNSUPPORTED:
            candidate.warnings.append(f"No Source Intake parser is currently implemented for {detected_file_type.value} files.")

        if detected_file_type == SourceIntakeFileType.LAS:
            self._attach_las_metadata(candidate, file_path)

        candidate.qaqc_status = run_source_intake_qaqc(candidate)
        candidate.review_required = candidate.review_required or candidate.qaqc_status.review_required

        return candidate

    def _initial_parser_status(self, file_path: Path, detected_file_type: SourceIntakeFileType) -> SourceIntakeParseStatus:
        # WLV-WSI-PARSE-STATUS-FILENAME-1: deterministic initial parse classification.
        ext = file_path.suffix.lower().lstrip(".")
        if detected_file_type == SourceIntakeFileType.LAS:
            return SourceIntakeParseStatus.NOT_PARSED
        if ext in {"zip", "tar", "tgz", "gz", "gzip", "7z", "rar"}:
            return SourceIntakeParseStatus.CONTAINER_PENDING_EXTRACTION
        if detected_file_type != SourceIntakeFileType.UNKNOWN:
            return SourceIntakeParseStatus.UNSUPPORTED
        return SourceIntakeParseStatus.NOT_PARSED


    def _attach_deviation_survey_preview(self, candidate: SourceFileCandidate, file_path: Path) -> None:
        """Attach a structured deviation-survey preview to a geometry candidate.

        WLV-GEOM-3 stops at backend-owned parser preview and QAQC. It does not
        register a trajectory into MSI and does not make the record WBV-loadable.
        """
        ext = file_path.suffix.lower().lstrip(".")
        if ext not in {"csv", "txt", "asc", "xlsx", "xls"}:
            candidate.parser_status = SourceIntakeParseStatus.UNSUPPORTED
            candidate.warnings.append(
                f"Wellbore Geometry candidate uses {candidate.detected_file_type.value}; structured deviation-survey preview supports CSV, TXT/ASC, and XLSX only."
            )
            return

        try:
            preview = parse_deviation_survey_preview(file_path)
        except DeviationSurveyParseError as exc:
            candidate.parser_status = SourceIntakeParseStatus.PARSE_FAILED
            candidate.parse_error = str(exc)
            candidate.review_required = True
            candidate.warnings.append(f"Deviation survey preview parse failed: {exc}")
            return

        candidate.geometry_preview = preview
        candidate.parser_status = (
            SourceIntakeParseStatus.PARSED_WITH_WARNINGS
            if preview.warning_count or preview.error_count
            else SourceIntakeParseStatus.PARSED
        )
        candidate.review_required = True
        for message in preview.warnings:
            if message not in candidate.warnings:
                candidate.warnings.append(message)

    def _attach_las_metadata(self, candidate: SourceFileCandidate, file_path: Path) -> None:
        """Parse LAS headers into the three-level source-intake metadata model.

        This is metadata extraction only. It does not stage to WMDP, does not
        create MSI records, and does not create a representation/conversion.
        """
        try:
            package = LasSourceAdapter().parse_path(file_path)
        except LasAdapterError as exc:
            candidate.parser_status = SourceIntakeParseStatus.PARSE_FAILED
            candidate.parse_error = str(exc)
            candidate.review_required = True
            candidate.warnings.append(f"LAS metadata parse failed: {exc}")
            return

        well_header_raw = _metadata_dict(package.metadata.get("well_header"))
        null_value = _numeric_header_value(well_header_raw, "NULL")
        start_depth = _numeric_header_value(well_header_raw, "STRT", "START", "START_DEPTH")
        stop_depth = _numeric_header_value(well_header_raw, "STOP", "STOP_DEPTH")
        step = _numeric_header_value(well_header_raw, "STEP", "STEP_VALUE")
        depth_unit = _string_value(package.metadata.get("depth_unit"))

        warning_messages = [finding.message for finding in package.qaqc_findings if getattr(finding.severity, "value", finding.severity) == "warning"]
        error_messages = [finding.message for finding in package.qaqc_findings if getattr(finding.severity, "value", finding.severity) == "error"]

        parsed = SourceIntakeParsedMetadata(
            parser_id=getattr(LasSourceAdapter, "adapter_id", "las_numeric_curve_adapter_v1"),
            source_format="LAS",
            well_header=SourceIntakeWellHeader(
                well_name=package.well_name,
                uwi=_first_header_text(well_header_raw, "UWI", "API", "WELLID", "WELL_ID"),
                operator=_first_header_text(well_header_raw, "COMP", "COMPANY", "OPERATOR", "OPER"),
                field=_first_header_text(well_header_raw, "FLD", "FIELD"),
                block=_first_header_text(well_header_raw, "BLOCK", "BLK", "LICENSE", "LICENCE"),
                country=_first_header_text(well_header_raw, "CTRY", "COUNTRY"),
                depth_unit=depth_unit,
            ),
            log_header=SourceIntakeLogHeader(
                file_name=candidate.file_name,
                file_type=candidate.detected_file_type,
                run_date=_first_header_text(well_header_raw, "DATE", "LOG_DATE", "RUN_DATE"),
                run_number=_first_header_text(well_header_raw, "RUN", "RUNNO", "RUN_NO", "RUN_NUMBER"),
                service_company=_first_header_text(well_header_raw, "SRVC", "SERVICE", "SERVICE_COMPANY"),
                start_depth=start_depth if start_depth is not None else package.metadata.get("top_depth"),
                stop_depth=stop_depth if stop_depth is not None else package.metadata.get("base_depth"),
                step=step,
                null_value=null_value,
                depth_unit=depth_unit,
                curve_count=len(package.curve_channels),
            ),
            curve_headers=[
                SourceIntakeCurveHeader(
                    mnemonic=curve.mnemonic,
                    description=curve.display_name,
                    unit=curve.unit,
                    source_curve_name=curve.mnemonic,
                    depth_unit=curve.depth_unit,
                    top_depth=curve.top_depth,
                    base_depth=curve.base_depth,
                    sample_count=curve.sample_count,
                )
                for curve in package.curve_channels
            ],
            evidence_count=len(package.evidence),
            warning_count=len(warning_messages),
            error_count=len(error_messages),
            warnings=warning_messages + error_messages,
        )

        candidate.parsed_metadata = parsed
        candidate.resolved_metadata = resolve_candidate_metadata(candidate)
        candidate.parser_status = (
            SourceIntakeParseStatus.PARSE_FAILED if error_messages
            else SourceIntakeParseStatus.PARSED_WITH_WARNINGS if warning_messages
            else SourceIntakeParseStatus.PARSED
        )
        candidate.parse_error = "; ".join(error_messages) if error_messages else None
        candidate.review_required = candidate.review_required or bool(error_messages)
        if candidate.resolved_metadata is not None:
            candidate.review_required = candidate.review_required or candidate.resolved_metadata.review_required
        for message in parsed.warnings:
            if message not in candidate.warnings:
                candidate.warnings.append(message)
        if candidate.resolved_metadata is not None:
            for message in candidate.resolved_metadata.warnings:
                if message not in candidate.warnings:
                    candidate.warnings.append(message)

    def _classify_file(self, path: Path) -> tuple[SourceIntakeFileType, SourceIntakeCandidateRole]:
        ext = path.suffix.lower().lstrip(".")
        if ext == "las":
            return SourceIntakeFileType.LAS, SourceIntakeCandidateRole.WELL_LOG_CANDIDATE
        if ext == "dlis":
            return SourceIntakeFileType.DLIS, SourceIntakeCandidateRole.WELL_LOG_CANDIDATE
        if ext == "lis":
            return SourceIntakeFileType.LIS, SourceIntakeCandidateRole.WELL_LOG_CANDIDATE

        if self._looks_like_wellbore_geometry_candidate(path):
            file_type = self._file_type_for_geometry_extension(ext)
            return file_type, SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE

        if ext == "cgm":
            return SourceIntakeFileType.CGM, SourceIntakeCandidateRole.RASTER_IMAGE_CANDIDATE
        if ext in {"tif", "tiff"}:
            return SourceIntakeFileType.TIFF, SourceIntakeCandidateRole.RASTER_IMAGE_CANDIDATE
        if ext in {"png", "jpg", "jpeg"}:
            return SourceIntakeFileType.IMAGE, SourceIntakeCandidateRole.RASTER_IMAGE_CANDIDATE
        if ext == "pdf":
            return SourceIntakeFileType.PDF, SourceIntakeCandidateRole.SUPPORTING_DOCUMENT_CANDIDATE
        if ext in {"doc", "docx"}:
            return SourceIntakeFileType.WORD, SourceIntakeCandidateRole.SUPPORTING_DOCUMENT_CANDIDATE
        if ext in {"xls", "xlsx"}:
            return SourceIntakeFileType.EXCEL, SourceIntakeCandidateRole.TABULAR_CANDIDATE
        if ext == "csv":
            return SourceIntakeFileType.CSV, SourceIntakeCandidateRole.TABULAR_CANDIDATE
        if ext in {"txt", "asc"}:
            return SourceIntakeFileType.TEXT, SourceIntakeCandidateRole.SUPPORTING_DOCUMENT_CANDIDATE
        return SourceIntakeFileType.UNKNOWN, SourceIntakeCandidateRole.OTHER_REVIEW_REQUIRED

    def _looks_like_wellbore_geometry_candidate(self, path: Path) -> bool:
        # WLV-GEOM-2: deterministic Source Intake classification only.
        # This detects likely deviation/directional-survey source files for the
        # Wellbore Geometry bucket. It does not parse stations or register a
        # trajectory into MSI/MDP.
        ext = path.suffix.lower().lstrip(".")
        if ext not in {"csv", "xls", "xlsx", "txt", "asc", "pdf", "doc", "docx"}:
            return False

        normalized = " ".join(path.with_suffix("").parts).lower()
        separators = "_-./\\()[]{}"
        for separator in separators:
            normalized = normalized.replace(separator, " ")
        normalized = " ".join(normalized.split())

        strong_phrases = {
            "deviation survey",
            "deviation",
            "directional survey",
            "dir survey",
            "trajectory",
            "well path",
            "borehole survey",
            "survey station",
            "survey stations",
            "mwd survey",
            "gyro survey",
        }
        if any(phrase in normalized for phrase in strong_phrases):
            return True

        md_terms = {"md", "measured depth"}
        inclination_terms = {"inc", "incl", "inclination"}
        azimuth_terms = {"azi", "azim", "azimuth"}
        if any(term in normalized for term in md_terms) and any(term in normalized for term in inclination_terms) and any(term in normalized for term in azimuth_terms):
            return True

        if "tvd" in normalized and any(term in normalized for term in {"northing", "easting", "x y z", "xyz"}):
            return True

        return False

    def _file_type_for_geometry_extension(self, ext: str) -> SourceIntakeFileType:
        if ext == "csv":
            return SourceIntakeFileType.CSV
        if ext in {"xls", "xlsx"}:
            return SourceIntakeFileType.EXCEL
        if ext in {"txt", "asc"}:
            return SourceIntakeFileType.TEXT
        if ext == "pdf":
            return SourceIntakeFileType.PDF
        if ext in {"doc", "docx"}:
            return SourceIntakeFileType.WORD
        return SourceIntakeFileType.UNKNOWN

    def _apply_counts(self, repository: SourceRepositoryRecord, candidates: list[SourceFileCandidate]) -> None:
        repository.file_count = len(candidates)
        repository.well_log_candidate_count = sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.WELL_LOG_CANDIDATE)
        repository.raster_candidate_count = sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.RASTER_IMAGE_CANDIDATE)
        repository.document_candidate_count = sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.SUPPORTING_DOCUMENT_CANDIDATE)
        repository.tabular_candidate_count = sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.TABULAR_CANDIDATE)
        repository.wellbore_geometry_candidate_count = sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE)
        repository.unknown_file_count = sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.OTHER_REVIEW_REQUIRED)
        repository.review_required_count = sum(1 for item in candidates if item.review_required)
        repository.warnings = []
        if repository.review_required_count:
            repository.warnings.append(f"{repository.review_required_count} discovered file(s) require review.")

    def _summary(self, repositories: list[SourceRepositoryRecord], candidates: list[SourceFileCandidate]) -> SourceIntakeWorkbenchSummary:
        return SourceIntakeWorkbenchSummary(
            repository_count=len(repositories),
            file_count=len(candidates),
            well_log_candidate_count=sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.WELL_LOG_CANDIDATE),
            raster_candidate_count=sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.RASTER_IMAGE_CANDIDATE),
            document_candidate_count=sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.SUPPORTING_DOCUMENT_CANDIDATE),
            tabular_candidate_count=sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.TABULAR_CANDIDATE),
            wellbore_geometry_candidate_count=sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE),
            unknown_file_count=sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.OTHER_REVIEW_REQUIRED),
            review_required_count=sum(1 for item in candidates if item.review_required),
        )

    def _repository_id(self, root: Path) -> str:
        digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:12]
        return f"wlv-src-repo:{digest}"

    def _scan_id(self, repository_id: str, root: Path, scan_scope: str) -> str:
        seed = f"{repository_id}:{root}:{scan_scope}:{utc_now_iso()}"
        return f"wlv-scan:{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()



def _metadata_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _header_entry(header: dict[str, Any], key: str) -> dict[str, Any] | None:
    entry = header.get(key.upper())
    return entry if isinstance(entry, dict) else None


def _first_header_text(header: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        entry = _header_entry(header, key)
        if not entry:
            continue
        unit = entry.get("unit")
        value = entry.get("value")
        parts = [str(part).strip() for part in (unit, value) if part is not None and str(part).strip()]
        if parts:
            return " ".join(parts)
    return None


def _numeric_header_value(header: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        entry = _header_entry(header, key)
        if not entry:
            continue
        for candidate in (entry.get("value"), entry.get("unit")):
            if candidate is None or str(candidate).strip() == "":
                continue
            try:
                return float(str(candidate).split()[0])
            except (TypeError, ValueError, IndexError):
                continue
    return None


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None



def _is_ignored_source_file(path: Path) -> bool:
    ignored_names = {".ds_store", "thumbs.db", "desktop.ini"}
    ignored_dirs = {"__macosx", ".git", ".svn", ".hg"}
    parts = [part.lower() for part in path.parts]
    if any(part in ignored_dirs for part in parts):
        return True
    if path.name.lower() in ignored_names:
        return True
    return False
