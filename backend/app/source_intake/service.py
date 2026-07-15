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
from .promotion_performance import now as _perf_now, elapsed_ms as _perf_ms, write_event as _perf_event

from ..ingestion.las_adapter import LasAdapterError, LasSourceAdapter
from app.inventory.models import (
    ManagedInventoryLifecycleState,
    ManagedSourceKind,
    ManagedSourceReference,
    ManagedProductGroup,
    ManagedProductGroupItem,
    ManagedWdvState,
    ManagedWellRecord,
    ManagedWmdpState,
)
from app.wbv.models import WbvCoordinateMode, WbvManagedTrajectoryRecord, WbvManagedTrajectoryStatus
from app.identity import new_uuid7_str


from .metadata_resolver import resolve_candidate_metadata
from .lifecycle_service import SourceIntakeLifecycleService
from .las_asset_store import LasAssetStore
from .canonical_metadata import (
    canonical_metadata_from_dlis_values,
    canonical_metadata_from_las_header,
)
from .identity_gate import apply_identity_gate
from .qaqc import run_source_intake_qaqc
from .qaqc_recompute import recompute_qaqc_after_resolution
from .registration import register_candidate_to_inventory, wmd_availability_block_reason
from .readiness import evaluate_wmd_availability_readiness
from .resolution_service import (
    SourceIntakeResolutionError,
    SourceIntakeResolutionService,
    is_wmd_eligible,
    occurrence_identity,
)
from .depth_units import convert_depth_to_target
from .dlis_parser import DlisInspectionError, inspect_dlis
from .deviation_survey_parser import (
    DeviationSurveyParseError,
    parse_deviation_survey_full,
    parse_deviation_survey_preview,
)

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
    SourceIntakeHumanDecision,
    SourceIntakeWellAssignmentMode,
    SourceIntakeLogHeader,
    SourceIntakeParseStatus,
    SourceIntakeParsedMetadata,
    SourceIntakeQaqcStatus,
    SourceIntakeRegisterRequest,
    SourceIntakeRegisterResponse,
    SourceIntakeRegisterResult,
    SourceIntakeRestoreToMdpRequest,
    SourceIntakeRestoreToMdpResponse,
    SourceIntakeRestoreToMdpResult,
    SourceIntakeBulkResolutionRequest,
    SourceIntakeBulkResolutionResponse,
    SourceIntakeOccurrenceAccounting,
    SourceIntakeOverlayExportCandidate,
    SourceIntakeOverlayExportPackage,
    SourceIntakeSavedWorkspaceDeleteResponse,
    SourceIntakeSavedWorkspaceRecord,
    SourceIntakeSavedWorkspaceSaveRequest,
    SourceIntakeSavedWorkspaceRecoveryResult,
    SourceIntakeSourceAccessStatus,
    SourceIntakeSourceRecoveryResult,
    SourceIntakeSavedWorkspaceSource,
    SourceIntakeRepositoryStatus,
    SourceIntakeWellHeader,
    SourceIntakeCurveHeader,
    SourceIntakeDlisChannelHeader,
    SourceIntakeDepthNormalizationContract,
    SourceIntakeDepthNormalizationDecision,
    SourceIntakeDepthNormalizationOption,
    SourceIntakeDepthNormalizationRequest,
    SourceIntakeDepthNormalizationStatus,
    SourceIntakeReferenceBinding,
    SourceIntakeReferenceType,
    SourceMaterialization,
    ExternalSourceReference,
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
        self.lifecycle_service = SourceIntakeLifecycleService()

    def health(self) -> dict[str, object]:
        _snapshot_load_started = _perf_now()
        snapshot = self._load_snapshot()
        _perf_event("source_intake_snapshot_loaded", elapsed_ms=_perf_ms(_snapshot_load_started), snapshot_candidate_count=len(snapshot.candidates))
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

    def ingest_uploaded_files(self, files: list[tuple[str, bytes]]) -> SourceRepositoryScanResult:
        """Materialize browser uploads in an isolated WLV-owned temporary batch.

        Browsers provide bytes rather than a durable external path. The batch is
        explicitly temporary, never treated as a managed source, and is scanned
        independently so prior uploads cannot leak into a new result.
        """
        if not files:
            raise SourceIntakeError("Select at least one file to ingest.")

        upload_root = (self.storage_path.parent / "temporary_uploads").resolve()
        upload_root.mkdir(parents=True, exist_ok=True)
        batch_root = (upload_root / new_uuid7_str()).resolve()
        batch_root.mkdir(parents=True, exist_ok=False)

        try:
            for original_name, content in files:
                file_name = Path(original_name or "").name
                if not file_name or file_name in {".", ".."}:
                    raise SourceIntakeError("Every uploaded file must have a valid filename.")
                if not content:
                    raise SourceIntakeError(f"Uploaded file is empty: {file_name}")
                target = (batch_root / file_name).resolve()
                if target.parent != batch_root:
                    raise SourceIntakeError(f"Unsafe uploaded filename: {file_name}")
                target.write_bytes(content)
        except Exception:
            self.lifecycle_service.clear_temporary_materialization(batch_root, upload_root)
            raise

        repository = self.create_repository(
            SourceRepositoryCreateRequest(
                name="Direct file ingest",
                root_path=str(batch_root),
                include_subfolders=True,
            )
        )
        snapshot = self._load_snapshot()
        stored = self._get_repository(snapshot, repository.repository_id)
        stored.materialization = SourceMaterialization.TEMPORARY_UPLOAD
        stored.wlv_owned_temporary_storage = True
        self._save_snapshot(snapshot)
        return self.scan_repository(repository.repository_id, include_subfolders=True)

    def remove_repository(self, repository_id: str) -> SourceRepositoryRemoveResponse:
        # WLV-WSI-REMOVE-SOURCE-1:
        # "Remove Source" removes the Source Intake repository record and its
        # current candidate rows from WSI. It must not delete files on disk,
        # Managed Well Inventory records, MDP state, or WDV session data.
        snapshot = self._load_snapshot()
        repository = next((repo for repo in snapshot.repositories if repo.repository_id == repository_id), None)
        if repository is None:
            raise SourceIntakeError(f"Source repository not found: {repository_id}")

        repository_candidates = [
            candidate for candidate in snapshot.candidates if candidate.repository_id == repository_id
        ]
        candidate_rows_removed = len(repository_candidates)
        cleanup_deferred_count = 0
        derived_cache_entries_cleared = 0
        cleared_fingerprints: set[str] = set()

        las_cache_root = LasAssetStore().storage_root
        for candidate in repository_candidates:
            self.lifecycle_service.prepare_for_wsi_close(candidate)
            if not candidate.cleanup_eligible:
                cleanup_deferred_count += 1
                continue
            fingerprint = str(
                candidate.content_fingerprint or candidate.checksum or ""
            ).strip().lower()
            if fingerprint and fingerprint not in cleared_fingerprints:
                if self.lifecycle_service.clear_candidate_derived_data(
                    candidate,
                    las_storage_root=las_cache_root,
                ):
                    derived_cache_entries_cleared += 1
                cleared_fingerprints.add(fingerprint)
            self.lifecycle_service.mark_cleared(candidate)

        temporary_materialization_cleared = False
        if (
            repository.materialization == SourceMaterialization.TEMPORARY_UPLOAD
            and repository.wlv_owned_temporary_storage
            and cleanup_deferred_count == 0
        ):
            upload_root = (self.storage_path.parent / "temporary_uploads").resolve()
            temporary_materialization_cleared = (
                self.lifecycle_service.clear_temporary_materialization(
                    Path(repository.root_path), upload_root
                )
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
            derived_cache_entries_cleared=derived_cache_entries_cleared,
            temporary_materialization_cleared=temporary_materialization_cleared,
            cleanup_deferred_count=cleanup_deferred_count,
            message=(
                f"Removed source repository {repository.name} from Source Intake. "
                f"Removed {candidate_rows_removed} associated candidate row"
                f"{'s' if candidate_rows_removed != 1 else ''}. "
                f"Cleared {derived_cache_entries_cleared} unreferenced derived cache entr"
                f"{'ies' if derived_cache_entries_cleared != 1 else 'y'}. "
                f"Deferred cleanup for {cleanup_deferred_count} candidate"
                f"{'s' if cleanup_deferred_count != 1 else ''} still referenced downstream. "
                "External source files and managed inventory were not deleted."
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
        candidates = [self._candidate_for_file(repository, scan_id, root, file_path) for file_path in files]
        apply_identity_gate(candidates)
        for candidate in candidates:
            candidate.qaqc_status = run_source_intake_qaqc(candidate)
            candidate.review_required = candidate.review_required or candidate.qaqc_status.review_required

        candidates = self.resolution_service.initialize_candidates(candidates)

        existing_repository_candidates = {
            candidate.occurrence_id: candidate
            for candidate in snapshot.candidates
            if candidate.repository_id == repository_id and candidate.occurrence_id
        }
        reconciled_candidates = [
            self._preserve_candidate_lifecycle(
                fresh_candidate,
                existing_repository_candidates.get(fresh_candidate.occurrence_id),
            )
            for fresh_candidate in candidates
        ]
        for candidate in reconciled_candidates:
            self._reapply_current_human_decision(candidate)

        other_repository_candidates = [
            candidate
            for candidate in snapshot.candidates
            if candidate.repository_id != repository_id
        ]
        snapshot.candidates = self.resolution_service.reconcile_duplicate_groups(
            [*other_repository_candidates, *reconciled_candidates]
        )
        candidates = [
            candidate
            for candidate in snapshot.candidates
            if candidate.repository_id == repository_id
        ]

        self._apply_counts(repository, candidates)
        repository.status = SourceIntakeRepositoryStatus.SCANNED
        repository.last_scan_id = scan_id
        repository.last_scan_scope = scan_scope
        repository.updated_at = utc_now_iso()

        self._save_snapshot(snapshot)
        candidates = [evaluate_wmd_availability_readiness(candidate) for candidate in candidates]
        return SourceRepositoryScanResult(
            ok=True,
            repository=repository,
            scan_id=scan_id,
            scan_scope=scan_scope,
            file_count=len(candidates),
            candidates=candidates,
        )

    @staticmethod
    def _preserve_candidate_lifecycle(
        fresh: SourceFileCandidate,
        existing: SourceFileCandidate | None,
    ) -> SourceFileCandidate:
        """Merge fresh discovery evidence with durable candidate lifecycle truth.

        A repository scan owns current file discovery, parsing, and QAQC evidence.
        It does not own prior human resolution decisions, registration linkage,
        or managed lifecycle state. Those fields survive when the occurrence
        identity is unchanged.
        """
        if existing is None:
            return fresh

        fresh.resolution_state = existing.resolution_state
        fresh.resolution_version = existing.resolution_version
        fresh.resolved_by = existing.resolved_by
        fresh.resolved_at = existing.resolved_at
        fresh.resolution_reason = existing.resolution_reason
        fresh.current_decision = existing.current_decision
        fresh.depth_normalization = existing.depth_normalization

        fresh.registration_status = existing.registration_status
        fresh.managed_well_id = existing.managed_well_id
        fresh.managed_well_name = existing.managed_well_name
        fresh.wmdp_state = existing.wmdp_state
        fresh.wdv_state = existing.wdv_state
        fresh.working_data_state = existing.working_data_state
        fresh.retention_state = existing.retention_state
        fresh.cleanup_eligible = existing.cleanup_eligible
        fresh.retention_reason = existing.retention_reason
        fresh.reference_bindings = list(existing.reference_bindings)
        fresh.reference_counts = dict(existing.reference_counts)
        fresh.active_reference_count = existing.active_reference_count
        fresh.registered_product_count = existing.registered_product_count
        fresh.registered_curve_count = existing.registered_curve_count
        fresh.registered_trajectory_count = existing.registered_trajectory_count

        return fresh

    @staticmethod
    def _reapply_current_human_decision(
        candidate: SourceFileCandidate,
    ) -> None:
        """Reapply the current human decision to freshly recomputed QAQC.

        Rescan owns current source evidence. The most recent human decision owns
        accepted review findings and corrected metadata. Reapplying that single
        current decision prevents a rescan from reopening already reviewed
        findings without creating a QAQC history timeline.
        """
        if candidate.current_decision is None:
            return

        WlvSourceIntakeService._reapply_decision_payload(candidate)
        WlvSourceIntakeService._reapply_depth_normalization(candidate)
        recompute_qaqc_after_resolution(candidate, candidate.current_decision)

    @staticmethod
    def _reapply_decision_payload(
        candidate: SourceFileCandidate,
    ) -> None:
        """Replay durable human intent without restoring stale inferred state."""
        SourceIntakeResolutionService().reapply_current_decision(candidate)

    def rebuild_candidate_from_external_source(self, candidate_id: str) -> SourceFileCandidate:
        """Reparse one candidate from its external source reference.

        The original file remains authoritative and read-only. A changed
        fingerprint produces a fresh occurrence and does not inherit prior
        human decisions or downstream lifecycle bindings.
        """
        snapshot = self._load_snapshot()
        existing = next(
            (item for item in snapshot.candidates if item.source_file_id == candidate_id),
            None,
        )
        if existing is None:
            raise SourceIntakeError(f"Source Intake candidate not found: {candidate_id}")
        repository = self._get_repository(snapshot, existing.repository_id)
        root = Path(repository.root_path).expanduser().resolve()
        source_path = Path(existing.original_path).expanduser().resolve()
        if not source_path.is_file():
            raise SourceIntakeError(f"External source file is unavailable: {source_path}")
        try:
            source_path.relative_to(root)
        except ValueError as exc:
            raise SourceIntakeError(
                "Candidate source path is outside its external repository."
            ) from exc

        fresh = self._candidate_for_file(
            repository,
            self._scan_id(
                repository_id=repository.repository_id,
                root=root,
                scan_scope=repository.last_scan_scope or "root_only",
            ),
            root,
            source_path,
        )
        same_content = (fresh.content_fingerprint or fresh.checksum) == (
            existing.content_fingerprint or existing.checksum
        )
        if same_content:
            fresh = self._preserve_candidate_lifecycle(fresh, existing)
            self._reapply_current_human_decision(fresh)
        else:
            fresh.retention_reason = (
                "External source fingerprint changed; prior derived data and "
                "workspace decisions were invalidated before reparse."
            )

        snapshot.candidates = [
            fresh if item.source_file_id == candidate_id else item
            for item in snapshot.candidates
        ]
        snapshot.updated_at = utc_now_iso()
        self._save_snapshot(snapshot)
        return fresh

    def get_workbench(self) -> SourceIntakeWorkbench:
        snapshot = self._load_snapshot()
        candidates = [evaluate_wmd_availability_readiness(candidate) for candidate in snapshot.candidates]
        return SourceIntakeWorkbench(
            summary=self._summary(snapshot.repositories, candidates),
            repositories=snapshot.repositories,
            candidates=candidates,
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
        by_occurrence = {
            candidate.occurrence_id: candidate
            for candidate in snapshot.candidates
            if candidate.occurrence_id
        }
        for result in response.results:
            candidate = by_occurrence.get(result.occurrence_id)
            if candidate is None or candidate.current_decision is None:
                continue
            recompute_qaqc_after_resolution(candidate, candidate.current_decision)
        for candidate in snapshot.candidates:
            evaluate_wmd_availability_readiness(candidate)
        self._save_snapshot(snapshot)
        return response

    def set_depth_normalization(
        self,
        candidate_id: str,
        request: SourceIntakeDepthNormalizationRequest,
    ) -> SourceFileCandidate:
        snapshot = self._load_snapshot()
        candidate = next((item for item in snapshot.candidates if item.source_file_id == candidate_id), None)
        if candidate is None:
            raise SourceIntakeError(f"Source Intake candidate not found: {candidate_id}")
        contract = candidate.depth_normalization
        if contract is None or contract.status not in {
            SourceIntakeDepthNormalizationStatus.REVIEW_REQUIRED,
            SourceIntakeDepthNormalizationStatus.HUMAN_RESOLVED,
        }:
            raise SourceIntakeError("Candidate does not require a depth target-unit decision.")
        target = request.target_unit.strip().casefold()
        if target not in {"m", "ft"}:
            raise SourceIntakeError("Depth target unit must be 'm' or 'ft'.")
        contract.decision = SourceIntakeDepthNormalizationDecision(
            target_unit=target, actor=request.actor, reason=request.reason
        )
        contract.status = SourceIntakeDepthNormalizationStatus.HUMAN_RESOLVED
        self._reapply_depth_normalization(candidate)
        candidate.qaqc_status = run_source_intake_qaqc(candidate)
        candidate.review_required = candidate.qaqc_status.review_required
        evaluate_wmd_availability_readiness(candidate)
        self._save_snapshot(snapshot)
        return candidate

    @staticmethod
    def _reapply_depth_normalization(candidate: SourceFileCandidate) -> None:
        contract = candidate.depth_normalization
        parsed = candidate.parsed_metadata
        if contract is None or parsed is None or contract.decision is None:
            return
        target = contract.decision.target_unit
        raw_unit = contract.raw_unit
        if raw_unit is None:
            return
        for header in parsed.curve_headers:
            if header.raw_depth_unit != raw_unit:
                continue
            raw_top = getattr(header, "raw_top_depth", None)
            raw_base = getattr(header, "raw_base_depth", None)
            if raw_top is not None:
                header.top_depth = convert_depth_to_target(raw_top, raw_unit, target)
            if raw_base is not None:
                header.base_depth = convert_depth_to_target(raw_base, raw_unit, target)
            header.depth_unit = target
            header.depth_normalization_status = "human_resolved"
        starts = [item.top_depth for item in parsed.curve_headers if item.top_depth is not None]
        stops = [item.base_depth for item in parsed.curve_headers if item.base_depth is not None]
        if parsed.log_header is not None:
            parsed.log_header.start_depth = min(starts) if starts else convert_depth_to_target(contract.raw_start_depth, raw_unit, target)
            parsed.log_header.stop_depth = max(stops) if stops else convert_depth_to_target(contract.raw_stop_depth, raw_unit, target)
            parsed.log_header.depth_unit = target
        parsed.well_header.depth_unit = target
        contract.status = SourceIntakeDepthNormalizationStatus.HUMAN_RESOLVED

    def _build_overlay_export_candidate(
        self,
        candidate: SourceFileCandidate,
    ) -> SourceIntakeOverlayExportCandidate:
        if candidate.source_reference is None:
            raise SourceIntakeError(
                f"Candidate has no external source reference: {candidate.source_file_id}"
            )

        original: dict[str, object] = {}
        parsed = candidate.parsed_metadata
        if parsed is not None and parsed.well_header is not None:
            original = parsed.well_header.model_dump(mode="json")

        effective: dict[str, object] = dict(original)
        resolved = candidate.resolved_metadata
        if resolved is not None:
            for field_name in (
                "well_name",
                "uwi",
                "operator",
                "field",
                "block",
                "wellbore_name",
                "country",
                "latitude",
                "longitude",
                "producer",
                "product",
                "version",
                "creation_date",
                "run_date",
            ):
                field = getattr(resolved, field_name, None)
                if field is not None and field.value is not None:
                    effective[field_name] = field.value

        decision = candidate.current_decision
        overlay = dict(decision.corrected_values) if decision is not None else {}
        effective.update(overlay)

        accepted = set(
            decision.accepted_finding_codes
            if decision is not None
            else []
        )
        all_codes = [
            check.check_id
            for check in candidate.qaqc_status.checks
        ]
        unresolved = [
            code
            for code in all_codes
            if code not in accepted
        ]

        return SourceIntakeOverlayExportCandidate(
            candidate_id=candidate.source_file_id,
            occurrence_id=candidate.occurrence_id,
            source_reference=candidate.source_reference,
            source_fingerprint=candidate.content_fingerprint,
            source_format=candidate.detected_file_type.value,
            parser_status=candidate.parser_status,
            original_metadata=original,
            effective_metadata=effective,
            metadata_overlay=overlay,
            current_decision=decision,
            depth_normalization=candidate.depth_normalization,
            qaqc=candidate.qaqc_status,
            resolved_finding_codes=sorted(accepted),
            unresolved_finding_codes=unresolved,
        )

    def export_overlay_package(self, candidate_ids: list[str]) -> SourceIntakeOverlayExportPackage:
        """Build a read-only QAQC and metadata-overlay sidecar package."""
        selected_ids = [value for value in dict.fromkeys(candidate_ids) if str(value or "").strip()]
        if not selected_ids:
            raise SourceIntakeError("Select at least one Source Intake candidate to export.")
        snapshot = self._load_snapshot()
        by_id = {candidate.source_file_id: candidate for candidate in snapshot.candidates}
        missing = [candidate_id for candidate_id in selected_ids if candidate_id not in by_id]
        if missing:
            raise SourceIntakeError(f"Source Intake candidate not found: {missing[0]}")

        exported: list[SourceIntakeOverlayExportCandidate] = []
        for candidate_id in selected_ids:
            candidate = by_id[candidate_id]
            owner_id = f"overlay-export:{candidate_id}"
            self.lifecycle_service.acquire_reference(
                candidate,
                SourceIntakeReferenceType.EXPORT,
                owner_id,
                "QAQC and metadata-overlay sidecar export.",
            )
            try:
                exported.append(
                    self._build_overlay_export_candidate(candidate)
                )
            finally:
                self.lifecycle_service.release_reference(
                    candidate,
                    SourceIntakeReferenceType.EXPORT,
                    owner_id,
                )

        return SourceIntakeOverlayExportPackage(candidate_count=len(exported), candidates=exported)

    def save_workspace(self, request: SourceIntakeSavedWorkspaceSaveRequest) -> SourceIntakeSavedWorkspaceRecord:
        """Persist source references and working decisions, never parsed samples."""
        name = str(request.name or "").strip()
        if not name:
            raise SourceIntakeError("Saved workspace name is required.")
        selected_ids = [value for value in dict.fromkeys(request.candidate_ids) if str(value or "").strip()]
        if not selected_ids:
            raise SourceIntakeError("Select at least one Source Intake candidate for the workspace.")

        snapshot = self._load_snapshot()
        by_id = {candidate.source_file_id: candidate for candidate in snapshot.candidates}
        missing = [candidate_id for candidate_id in selected_ids if candidate_id not in by_id]
        if missing:
            raise SourceIntakeError(f"Source Intake candidate not found: {missing[0]}")

        workspace_uid = str(request.workspace_uid or "").strip() or new_uuid7_str()
        existing = next(
            (item for item in snapshot.saved_workspaces if item.workspace_uid == workspace_uid),
            None,
        )
        if existing is not None:
            previous_ids = {source.candidate_id for source in existing.sources}
            for candidate_id in previous_ids - set(selected_ids):
                candidate = by_id.get(candidate_id)
                if candidate is not None:
                    self.lifecycle_service.release_reference(
                        candidate,
                        SourceIntakeReferenceType.SAVED_WORKSPACE,
                        workspace_uid,
                    )

        sources: list[SourceIntakeSavedWorkspaceSource] = []
        for candidate_id in selected_ids:
            candidate = by_id[candidate_id]
            if candidate.source_reference is None:
                raise SourceIntakeError(f"Candidate has no external source reference: {candidate_id}")
            self.lifecycle_service.acquire_reference(
                candidate,
                SourceIntakeReferenceType.SAVED_WORKSPACE,
                workspace_uid,
                "Saved workspace retains source reference and working decisions.",
            )
            decision = candidate.current_decision
            sources.append(
                SourceIntakeSavedWorkspaceSource(
                    candidate_id=candidate.source_file_id,
                    source_reference=candidate.source_reference,
                    source_fingerprint=candidate.content_fingerprint or candidate.checksum,
                    source_format=candidate.detected_file_type.value,
                    current_decision=decision,
                    depth_normalization=candidate.depth_normalization,
                    qaqc=candidate.qaqc_status,
                    metadata_overlay=(dict(decision.corrected_values) if decision is not None else {}),
                )
            )

        now = utc_now_iso()
        record = SourceIntakeSavedWorkspaceRecord(
            workspace_uid=workspace_uid,
            name=name,
            sources=sources,
            viewer_state=dict(request.viewer_state),
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        snapshot.saved_workspaces = [
            item for item in snapshot.saved_workspaces if item.workspace_uid != workspace_uid
        ]
        snapshot.saved_workspaces.append(record)
        self._save_snapshot(snapshot)
        return record

    def list_saved_workspaces(self) -> list[SourceIntakeSavedWorkspaceRecord]:
        return self._load_snapshot().saved_workspaces

    def get_saved_workspace(self, workspace_uid: str) -> SourceIntakeSavedWorkspaceRecord:
        normalized = str(workspace_uid or "").strip()
        snapshot = self._load_snapshot()
        record = next(
            (item for item in snapshot.saved_workspaces if item.workspace_uid == normalized),
            None,
        )
        if record is None:
            raise SourceIntakeError(f"Saved workspace not found: {normalized}")
        return record

    def delete_saved_workspace(self, workspace_uid: str) -> SourceIntakeSavedWorkspaceDeleteResponse:
        normalized = str(workspace_uid or "").strip()
        snapshot = self._load_snapshot()
        record = next(
            (item for item in snapshot.saved_workspaces if item.workspace_uid == normalized),
            None,
        )
        if record is None:
            raise SourceIntakeError(f"Saved workspace not found: {normalized}")
        by_id = {candidate.source_file_id: candidate for candidate in snapshot.candidates}
        released = 0
        for source in record.sources:
            candidate = by_id.get(source.candidate_id)
            if candidate is not None and self.lifecycle_service.release_reference(
                candidate,
                SourceIntakeReferenceType.SAVED_WORKSPACE,
                normalized,
            ):
                released += 1
        snapshot.saved_workspaces = [
            item for item in snapshot.saved_workspaces if item.workspace_uid != normalized
        ]
        self._save_snapshot(snapshot)
        return SourceIntakeSavedWorkspaceDeleteResponse(
            workspace_uid=normalized,
            released_source_count=released,
        )

    def recover_candidate_source(self, candidate_id: str, *, rebuild_changed: bool = True) -> SourceIntakeSourceRecoveryResult:
        """Validate one external source and optionally reparse changed content."""
        snapshot = self._load_snapshot()
        candidate = next((item for item in snapshot.candidates if item.source_file_id == candidate_id), None)
        if candidate is None:
            raise SourceIntakeError(f"Source Intake candidate not found: {candidate_id}")
        previous = candidate.content_fingerprint or candidate.checksum
        status, current, message = self.lifecycle_service.inspect_external_source(candidate)
        if status != SourceIntakeSourceAccessStatus.CHANGED or not rebuild_changed:
            self._save_snapshot(snapshot)
            return SourceIntakeSourceRecoveryResult(
                candidate_id=candidate.source_file_id, status=status, previous_fingerprint=previous,
                current_fingerprint=current, rebuilt=False, cache_invalidated=False, message=message, candidate=candidate,
            )

        old_id = candidate.source_file_id
        old_bindings = list(candidate.reference_bindings)
        fresh = self.rebuild_candidate_from_external_source(old_id)
        refreshed = self._load_snapshot()
        rebuilt = next((item for item in refreshed.candidates if item.source_file_id == fresh.source_file_id), fresh)
        # Preserve the stable workspace candidate key and saved-workspace retention only.
        rebuilt.source_file_id = old_id
        rebuilt.reference_bindings = [
            binding for binding in old_bindings
            if binding.reference_type in {SourceIntakeReferenceType.WSI, SourceIntakeReferenceType.SAVED_WORKSPACE}
        ]
        rebuilt.current_decision = None
        rebuilt.depth_normalization = None
        rebuilt.source_access_status = SourceIntakeSourceAccessStatus.AVAILABLE
        rebuilt.source_access_checked_at = utc_now_iso()
        rebuilt.source_access_message = "Changed external source reparsed; prior transient decisions and derived state invalidated."
        rebuilt.synchronize_reference_summary()
        refreshed.candidates = [rebuilt if item.source_file_id == fresh.source_file_id else item for item in refreshed.candidates]
        for workspace in refreshed.saved_workspaces:
            for source in workspace.sources:
                if source.candidate_id == old_id:
                    source.source_fingerprint = current
                    source.source_reference = rebuilt.source_reference or source.source_reference
                    source.current_decision = None
                    source.depth_normalization = None
                    source.metadata_overlay = {}
                    source.qaqc = rebuilt.qaqc_status
        self._save_snapshot(refreshed)
        return SourceIntakeSourceRecoveryResult(
            candidate_id=old_id, status=SourceIntakeSourceAccessStatus.CHANGED,
            previous_fingerprint=previous, current_fingerprint=current, rebuilt=True,
            cache_invalidated=True, message=rebuilt.source_access_message or message, candidate=rebuilt,
        )

    def recover_saved_workspace(self, workspace_uid: str, *, rebuild_changed: bool = True) -> SourceIntakeSavedWorkspaceRecoveryResult:
        record = self.get_saved_workspace(workspace_uid)
        results = [self.recover_candidate_source(source.candidate_id, rebuild_changed=rebuild_changed) for source in record.sources]
        return SourceIntakeSavedWorkspaceRecoveryResult(
            workspace_uid=workspace_uid, source_count=len(results),
            available_count=sum(item.status == SourceIntakeSourceAccessStatus.AVAILABLE for item in results),
            changed_count=sum(item.status == SourceIntakeSourceAccessStatus.CHANGED for item in results),
            missing_count=sum(item.status == SourceIntakeSourceAccessStatus.MISSING for item in results),
            inaccessible_count=sum(item.status == SourceIntakeSourceAccessStatus.INACCESSIBLE for item in results),
            results=results,
        )

    def get_occurrence_accounting(self) -> SourceIntakeOccurrenceAccounting:
        snapshot = self._load_snapshot()
        return self.resolution_service.accounting(snapshot.candidates)

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

    def restore_candidates_to_mdp(
        self,
        request: SourceIntakeRestoreToMdpRequest,
        inventory_service: Any,
    ) -> SourceIntakeRestoreToMdpResponse:
        candidate_ids = [value for value in dict.fromkeys(request.candidate_ids) if value]
        if not candidate_ids:
            raise SourceIntakeError("Select at least one Source Intake candidate to restore to MDP.")

        snapshot = self._load_snapshot()
        candidates_by_id = {candidate.source_file_id: candidate for candidate in snapshot.candidates}
        eligible_ids: list[str] = []
        results: list[SourceIntakeRestoreToMdpResult] = []

        for candidate_id in candidate_ids:
            candidate = candidates_by_id.get(candidate_id)
            if candidate is None:
                results.append(SourceIntakeRestoreToMdpResult(
                    candidate_id=candidate_id,
                    status="blocked",
                    reason="Candidate not found in Source Intake workbench.",
                ))
                continue
            if candidate.registration_status != "registered" or not candidate.managed_well_id:
                results.append(SourceIntakeRestoreToMdpResult(
                    candidate_id=candidate_id,
                    status="blocked",
                    reason="Candidate has no retained MSI registration to restore.",
                ))
                continue
            eligible_ids.append(candidate_id)

        inventory_response = inventory_service.restore_source_candidates_to_mdp(eligible_ids) if eligible_ids else None
        restored_ids = set()
        already_visible_ids = set()
        missing_ids = set()

        if inventory_response is not None:
            missing_ids = set(inventory_response.result.missing_source_candidate_ids)
            restored_wells = set(inventory_response.result.restored_managed_well_ids)
            restored_products = set(inventory_response.result.restored_product_ids)
            already_wells = set(inventory_response.result.already_visible_managed_well_ids)
            already_products = set(inventory_response.result.already_visible_product_ids)

            for candidate_id in eligible_ids:
                candidate = candidates_by_id[candidate_id]
                if candidate_id in missing_ids:
                    continue
                record = inventory_service.get_well(candidate.managed_well_id)
                candidate.wmdp_state = record.wmdp_state.value
                candidate.wdv_state = record.wdv_state.value
                candidate.managed_well_name = record.well_name
                matching_items = [
                    item
                    for group in record.product_groups
                    for item in group.items
                    if candidate_id in {
                        item.source_id,
                        item.source_intake_candidate_id,
                        item.provenance.get("source_file_id") if item.provenance else None,
                        item.provenance.get("source_intake_candidate_id") if item.provenance else None,
                    }
                ]
                if record.managed_well_id in restored_wells or any(item.product_id in restored_products for item in matching_items):
                    restored_ids.add(candidate_id)
                    results.append(SourceIntakeRestoreToMdpResult(
                        candidate_id=candidate_id,
                        status="restored",
                        managed_well_id=record.managed_well_id,
                    ))
                elif record.managed_well_id in already_wells or any(item.product_id in already_products for item in matching_items):
                    already_visible_ids.add(candidate_id)
                    results.append(SourceIntakeRestoreToMdpResult(
                        candidate_id=candidate_id,
                        status="already_visible",
                        managed_well_id=record.managed_well_id,
                    ))
                else:
                    results.append(SourceIntakeRestoreToMdpResult(
                        candidate_id=candidate_id,
                        status="blocked",
                        managed_well_id=record.managed_well_id,
                        reason="No retained MSI product matched the selected Source Intake candidate.",
                    ))

        for candidate_id in sorted(missing_ids):
            candidate = candidates_by_id[candidate_id]
            results.append(SourceIntakeRestoreToMdpResult(
                candidate_id=candidate_id,
                status="blocked",
                managed_well_id=candidate.managed_well_id,
                reason="No retained MSI source/product identity matched this candidate.",
            ))

        self._save_snapshot(snapshot)
        blocked_count = sum(1 for result in results if result.status == "blocked")
        return SourceIntakeRestoreToMdpResponse(
            restored_count=len(restored_ids),
            already_visible_count=len(already_visible_ids),
            blocked_count=blocked_count,
            results=results,
            workbench=self.get_workbench(),
        )

    def register_candidates(self, request: SourceIntakeRegisterRequest, inventory_service=None) -> SourceIntakeRegisterResponse:
        _promotion_started = _perf_now()
        _perf_event("promotion_started", candidate_count=len(request.candidate_ids), candidate_ids=list(request.candidate_ids))
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

            qaqc_report: dict[str, object] | None = None
            if request.include_qaqc_report:
                qaqc_report = self._build_overlay_export_candidate(
                    candidate
                ).model_dump(mode="json")

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
                    qaqc_report=qaqc_report,
                )
                candidate.mark_available_to_wmd()
                candidate.managed_well_id = record.managed_well_id
                candidate.managed_well_name = record.well_name
                candidate.wmdp_state = record.wmdp_state.value if hasattr(record.wmdp_state, "value") else str(record.wmdp_state)
                candidate.wdv_state = record.wdv_state.value if hasattr(record.wdv_state, "value") else str(record.wdv_state)
                candidate.registered_product_count = 0
                candidate.registered_curve_count = 0
                candidate.registered_trajectory_count = trajectory_count
                try:
                    self.resolution_service.mark_available_to_wmd(
                        candidate,
                        actor=request.approval.approved_by,
                        reason=request.approval.approval_note,
                    )
                except SourceIntakeResolutionError as exc:
                    raise SourceIntakeError(str(exc)) from exc
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

            try:
                _candidate_register_started = _perf_now()
                action, record = register_candidate_to_inventory(
                    candidate=candidate,
                    inventory_service=inventory_service,
                    approved_by=request.approval.approved_by,
                    approval_note=request.approval.approval_note,
                    qaqc_report=qaqc_report,
                )
                _perf_event(
                    "candidate_registration_completed",
                    candidate_id=candidate.source_file_id,
                    file_name=candidate.file_name,
                    elapsed_ms=_perf_ms(_candidate_register_started),
                    product_group_count=len(record.product_groups),
                    curve_count=sum(len(group.items) for group in record.product_groups),
                )
            except ValueError as exc:
                skipped_count += 1
                results.append(
                    SourceIntakeRegisterResult(
                        candidate_id=candidate.source_file_id,
                        status="skipped",
                        reason=str(exc),
                    )
                )
                continue

            registered_curve_count = sum(
                len(group.items)
                for group in record.product_groups
            )
            registered_product_count = sum(1 for group in record.product_groups if group.items)
            candidate.mark_available_to_wmd()
            candidate.managed_well_id = record.managed_well_id
            candidate.managed_well_name = record.well_name
            candidate.wmdp_state = record.wmdp_state.value if hasattr(record.wmdp_state, "value") else str(record.wmdp_state)
            candidate.wdv_state = record.wdv_state.value if hasattr(record.wdv_state, "value") else str(record.wdv_state)
            candidate.registered_product_count = registered_product_count
            candidate.registered_curve_count = registered_curve_count
            try:
                self.resolution_service.mark_available_to_wmd(
                    candidate,
                    actor=request.approval.approved_by,
                    reason=request.approval.approval_note,
                )
            except SourceIntakeResolutionError as exc:
                raise SourceIntakeError(str(exc)) from exc
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
            _snapshot_save_started = _perf_now()
            self._save_snapshot(snapshot)
            _perf_event(
                "source_intake_snapshot_saved",
                elapsed_ms=_perf_ms(_snapshot_save_started),
            )

        # WSI-MWD-PROMOTION-RESPONSE-1:
        # Promotion is committed before this response is built. Do not rebuild
        # and serialize the entire Source Intake workbench on the POST response
        # path. The frontend performs explicit backend refreshes after success.
        _perf_event(
            "promotion_completed",
            elapsed_ms=_perf_ms(_promotion_started),
            registered_count=registered_count,
            skipped_count=skipped_count,
        )
        return SourceIntakeRegisterResponse(
            registered_count=registered_count,
            skipped_count=skipped_count,
            results=results,
            workbench=None,
        )

    def _registration_block_reason(self, candidate: SourceFileCandidate) -> str | None:
        if candidate.candidate_role == SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE:
            return self._geometry_registration_block_reason(candidate)
        return wmd_availability_block_reason(candidate)

    def _geometry_registration_block_reason(self, candidate: SourceFileCandidate) -> str | None:
        if candidate.candidate_role != SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE:
            return f"Only wellbore_geometry_candidate records can use geometry registration; got {candidate.candidate_role.value}."
        if candidate.is_available_to_wmd:
            return "Candidate is already available in WMD."
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
        qaqc_report: dict[str, object] | None = None,
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
        source_path = Path(candidate.original_path)
        if not source_path.exists():
            raise ValueError(f"Geometry source file is unavailable for full registration parse: {source_path}")
        try:
            full_survey = parse_deviation_survey_full(source_path)
        except DeviationSurveyParseError as exc:
            raise ValueError(f"Geometry source failed full registration parse: {exc}") from exc
        if full_survey.station_count != preview.station_count:
            raise ValueError(
                "Geometry source station count changed between scan and registration: "
                f"scan={preview.station_count}, registration={full_survey.station_count}."
            )

        existing = self._resolve_geometry_target_well(candidate, inventory_service)
        well_name = existing.well_name if existing is not None else self._geometry_well_name(candidate)
        well_id = existing.well_id if existing is not None else self._managed_geometry_well_id(well_name)
        managed_well_id = existing.managed_well_id if existing is not None else f"managed-well:{well_id}"

        now = utc_now_iso()
        trajectory = self._managed_trajectory_from_geometry_candidate(
            candidate,
            full_survey=full_survey,
            well_name=well_name,
            approved_at=now,
        )
        source_reference = self._geometry_source_reference(
            candidate,
            trajectory_id=trajectory.trajectory_id,
            qaqc_report=qaqc_report,
        )

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
        record.product_groups = self._merge_geometry_product_group(
            record.product_groups,
            candidate=candidate,
            trajectory=trajectory,
        )
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
        full_survey,
        well_name: str,
        approved_at: str,
    ) -> WbvManagedTrajectoryRecord:
        package = self._trajectory_package_from_full_geometry(
            candidate,
            full_survey=full_survey,
            well_name=well_name,
        )
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
            station_count=full_survey.station_count,
            md_min=full_survey.md_min,
            md_max=full_survey.md_max,
            tvd_min=full_survey.tvd_min,
            tvd_max=full_survey.tvd_max,
            geometry_class="registered_deviation_survey_full",
            coordinate_mode=WbvCoordinateMode.RELATIVE,
            trajectory_package=package,
            qa_flags=[message for message in full_survey.warnings[:10]],
            warnings=[{"code": "source_intake_geometry_warning", "severity": "warning", "message": message} for message in full_survey.warnings[:10]],
            created_at=approved_at,
            approved_at=approved_at,
        )

    def _trajectory_package_from_full_geometry(self, candidate: SourceFileCandidate, *, full_survey, well_name: str) -> dict[str, Any]:
        stations = [station.model_dump(mode="json") for station in full_survey.stations_preview]
        render_points: list[dict[str, float]] = []
        for station in full_survey.stations_preview:
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
        bbox = self._geometry_bounding_box(render_points, full_survey)
        warnings = [
            {"code": "source_intake_geometry_warning", "severity": "warning", "message": message}
            for message in full_survey.warnings[:10]
        ]
        return {
            "method": "source_intake_full_registration",
            "source": "source_intake_deviation_survey_full",
            "source_type": "deviation_survey",
            "source_intake_candidate_id": candidate.source_file_id,
            "source_file_id": candidate.source_file_id,
            "source_label": candidate.file_name,
            "well_name": well_name,
            "coordinate_mode": WbvCoordinateMode.RELATIVE.value,
            "trajectory_class": "registered_deviation_survey_full",
            "depth_unit": "ft",
            "angle_unit": "deg",
            "station_count": full_survey.station_count,
            "source_station_count": full_survey.station_count,
            "preview_station_count": candidate.geometry_preview.preview_station_count if candidate.geometry_preview else 0,
            "stations": stations,
            "render_points": render_points,
            "bounding_box": bbox,
            "column_mapping": full_survey.column_mapping.model_dump(mode="json"),
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

    def _geometry_source_reference(
        self,
        candidate: SourceFileCandidate,
        *,
        trajectory_id: str,
        qaqc_report: dict[str, object] | None = None,
    ) -> ManagedSourceReference:
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
                **(
                    {"source_intake_qaqc_report": qaqc_report}
                    if qaqc_report is not None
                    else {}
                ),
            },
        )

    def _resolve_geometry_target_well(self, candidate: SourceFileCandidate, inventory_service) -> ManagedWellRecord | None:
        decision = candidate.current_decision
        if (
            decision is not None
            and decision.decision == SourceIntakeHumanDecision.ASSIGN
            and decision.assignment_mode == SourceIntakeWellAssignmentMode.EXISTING_WELL
            and decision.assignment_target
        ):
            target_id = str(decision.assignment_target)
            try:
                return inventory_service.get_well(target_id)
            except Exception as exc:
                raise ValueError(f"Assigned managed well does not exist: {target_id}") from exc

        return self._match_existing_managed_well(candidate, inventory_service)

    @staticmethod
    def _merge_geometry_product_group(
        groups: list[ManagedProductGroup],
        *,
        candidate: SourceFileCandidate,
        trajectory: WbvManagedTrajectoryRecord,
    ) -> list[ManagedProductGroup]:
        geometry_item = ManagedProductGroupItem(
            product_id=trajectory.trajectory_id,
            display_name=trajectory.trajectory_name,
            curve_name=trajectory.trajectory_name,
            curve_type=trajectory.trajectory_type,
            curve_description="Registered wellbore deviation survey",
            curve_unit="ft",
            product_category="wellbore_geometry",
            product_subgroup_key=trajectory.trajectory_type,
            product_subgroup_label="Deviation Survey",
            curve_family="Wellbore Geometry",
            classification_confidence="high" if trajectory.wbv_eligible else "review",
            classification_source="source_intake_geometry_registration",
            classification_reasons=[
                "Parsed deviation-survey geometry was registered as a managed trajectory."
            ],
            review_required=not trajectory.wbv_eligible,
            run_interval=f"{trajectory.md_min:g}–{trajectory.md_max:g} ft",
            run_number="Available",
            qa_flag=trajectory.status.value if hasattr(trajectory.status, "value") else str(trajectory.status),
            selectable=bool(trajectory.wbv_eligible),
            source_kind="wellbore_geometry",
            source_id=candidate.source_file_id,
            wmdp_state=ManagedWmdpState.STAGED_IN_WMDP,
            wdv_state=ManagedWdvState.NOT_LOADED,
            source_intake_candidate_id=candidate.source_file_id,
            provenance={
                "source_intake_candidate_id": candidate.source_file_id,
                "repository_id": candidate.repository_id,
                "relative_path": candidate.relative_path,
                "original_path": candidate.original_path,
                "checksum": candidate.checksum,
                "trajectory_id": trajectory.trajectory_id,
                "station_count": trajectory.station_count,
            },
        )

        merged = [group.model_copy(deep=True) for group in groups]
        for group in merged:
            if group.group_key != "wellbore_geometry":
                continue
            group.group_label = "Wellbore Geometry"
            group.collapsed_by_default = False
            group.items = [
                item for item in group.items
                if item.product_id != geometry_item.product_id
            ] + [geometry_item]
            return merged

        merged.append(ManagedProductGroup(
            group_key="wellbore_geometry",
            group_label="Wellbore Geometry",
            collapsed_by_default=False,
            items=[geometry_item],
        ))
        return merged

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
            warnings = (
                candidate.parsed_metadata.warnings
                if candidate.parsed_metadata
                else []
            )

            if not warnings:
                return [
                    SourceIntakeDiagnosticFlag(
                        phase=SourceIntakeDiagnosticPhase.PARSE,
                        severity=SourceIntakeDiagnosticSeverity.WARNING,
                        code="parse_completed_with_warnings",
                        title="Parsing completed with warnings",
                        message=(
                            "The source was parsed successfully, but the parser "
                            "reported one or more warnings. Promotion remains "
                            "available unless a separate Critical Action is shown."
                        ),
                    )
                ]

            return [
                SourceIntakeDiagnosticFlag(
                    phase=SourceIntakeDiagnosticPhase.PARSE,
                    severity=SourceIntakeDiagnosticSeverity.WARNING,
                    code=f"parse_warning_{index + 1}",
                    title=f"Parsing warning {index + 1}",
                    message=warning,
                )
                for index, warning in enumerate(warnings)
            ]

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
                if check.status == SourceIntakeQaqcStatus.PASS:
                    severity = SourceIntakeDiagnosticSeverity.SUCCESS
                elif check.status == SourceIntakeQaqcStatus.FAIL:
                    severity = SourceIntakeDiagnosticSeverity.ERROR
                elif check.status in {
                    SourceIntakeQaqcStatus.WARNING,
                    SourceIntakeQaqcStatus.REVIEW_REQUIRED,
                }:
                    severity = SourceIntakeDiagnosticSeverity.WARNING

                flags.append(
                    SourceIntakeDiagnosticFlag(
                        phase=SourceIntakeDiagnosticPhase.QAQC,
                        severity=severity,
                        code=check.check_id,
                        title=self._qaqc_diagnostic_title(check.check_id),
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

    @staticmethod
    def _qaqc_diagnostic_title(check_id: str) -> str:
        governed_titles = {
            "las.metadata.present": "LAS metadata",
            "identity.well_name.present": "Well identity",
            "identity.well_name.missing": "Well name missing",
            "identity.uwi.present": "Well identifier",
            "identity.uwi.missing": "UWI/API missing",
            "identity.resolver.warning": "Identity resolution warning",
            "log.header.present": "LAS log header",
            "depth.start.present": "Start depth",
            "depth.start.missing": "Start depth missing",
            "depth.stop.present": "Stop depth",
            "depth.stop.missing": "Stop depth missing",
            "depth.step.present": "Depth step",
            "depth.step.missing": "Depth step missing",
            "depth.range.valid": "Depth range",
            "depth.range.invalid": "Invalid depth range",
            "curve.count.positive": "Curve inventory",
            "curve.count.zero": "No viewable curves",
            "curve.headers.present": "Curve headers",
            "curve.mnemonic.missing": "Curve mnemonic missing",
            "curve.mnemonic.duplicate": "Duplicate curve mnemonic",
            "curve.unit.missing": "Curve unit missing",
            "depth.target_unit.required": "Depth unit decision required",
            "depth.target_unit.resolved": "Depth unit resolved",
        }
        if check_id in governed_titles:
            return governed_titles[check_id]

        return (
            check_id
            .replace(".", " ")
            .replace("_", " ")
            .strip()
            .title()
        )

    def _mdp_diagnostic_flags(self, candidate: SourceFileCandidate) -> list[SourceIntakeDiagnosticFlag]:
        if candidate.is_available_to_wmd:
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
        if blocked_reason is None and not candidate.is_available_to_wmd:
            actions.append(
                SourceIntakeDiagnosticAction(
                    phase=SourceIntakeDiagnosticPhase.MDP_READY,
                    action_key="register_candidate",
                    label="Make Available",
                    enabled=False,
                    reason="Use the table selection and Make Available controls for this workflow.",
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
        if candidate.is_available_to_wmd:
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

    def synchronize_managed_well_reference_state(self, record: Any) -> int:
        """Synchronize WSI lifecycle state from authoritative inventory state.

        The lifecycle service owns matching and state projection. Cleanup
        remains disabled in this block.
        """
        snapshot = self._load_snapshot()
        matched = self.lifecycle_service.synchronize_inventory_record(snapshot.candidates, record)
        if matched:
            snapshot.updated_at = utc_now_iso()
            self._save_snapshot(snapshot)
        return matched

    def acquire_candidate_reference(
        self,
        candidate_id: str,
        reference_type: SourceIntakeReferenceType,
        owner_id: str,
        reason: str | None = None,
    ) -> SourceIntakeReferenceBinding:
        """Acquire an explicit retention reference without changing viewer behavior."""
        snapshot = self._load_snapshot()
        candidate = next(
            (item for item in snapshot.candidates if item.source_file_id == candidate_id),
            None,
        )
        if candidate is None:
            raise SourceIntakeError(f"Source Intake candidate not found: {candidate_id}")
        binding = self.lifecycle_service.acquire_reference(candidate, reference_type, owner_id, reason)
        snapshot.updated_at = utc_now_iso()
        self._save_snapshot(snapshot)
        return binding

    def release_candidate_reference(
        self,
        candidate_id: str,
        reference_type: SourceIntakeReferenceType,
        owner_id: str,
    ) -> SourceFileCandidate:
        """Release one explicit reference; cleanup remains disabled during reference integration."""
        snapshot = self._load_snapshot()
        candidate = next(
            (item for item in snapshot.candidates if item.source_file_id == candidate_id),
            None,
        )
        if candidate is None:
            raise SourceIntakeError(f"Source Intake candidate not found: {candidate_id}")
        self.lifecycle_service.release_reference(candidate, reference_type, owner_id)
        snapshot.updated_at = utc_now_iso()
        self._save_snapshot(snapshot)
        return candidate

    def _load_snapshot(self) -> SourceIntakeSnapshot:
        if not self.storage_path.exists():
            return SourceIntakeSnapshot()
        data = json.loads(self.storage_path.read_text())
        return SourceIntakeSnapshot(**data)

    def _save_snapshot(self, snapshot: SourceIntakeSnapshot) -> None:
        # WLV-WSI-TRANSIENT-LIFECYCLE-2: keep the additive lifecycle contract
        # synchronized with existing registration/WMD state before persistence.
        # Cleanup remains disabled until explicit reference tracking lands.
        self.lifecycle_service.synchronize_snapshot(snapshot)
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

    def _candidate_for_file(self, repository: SourceRepositoryRecord, scan_id: str, root: Path, file_path: Path) -> SourceFileCandidate:
        checksum = self._sha256(file_path)
        detected_file_type, candidate_role = self._classify_file(file_path)
        review_required = candidate_role in {
            SourceIntakeCandidateRole.OTHER_REVIEW_REQUIRED,
            SourceIntakeCandidateRole.WELLBORE_GEOMETRY_CANDIDATE,
        }
        warnings = ["File type requires review before WMDP staging."] if candidate_role == SourceIntakeCandidateRole.OTHER_REVIEW_REQUIRED else []
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
                repository_id=repository.repository_id,
                relative_path=relative_path,
                checksum=checksum,
            ),
            repository_id=repository.repository_id,
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
            source_reference=ExternalSourceReference(
                source_uri=str(file_path),
                display_name=file_path.name,
                source_format=detected_file_type.value,
                fingerprint=checksum,
                materialization=repository.materialization,
            ),
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
        elif detected_file_type == SourceIntakeFileType.DLIS:
            self._attach_dlis_metadata(candidate, file_path)

        candidate.qaqc_status = run_source_intake_qaqc(candidate)
        candidate.review_required = candidate.review_required or candidate.qaqc_status.review_required

        return candidate

    def _initial_parser_status(self, file_path: Path, detected_file_type: SourceIntakeFileType) -> SourceIntakeParseStatus:
        # WLV-WSI-PARSE-STATUS-FILENAME-1: deterministic initial parse classification.
        ext = file_path.suffix.lower().lstrip(".")
        if detected_file_type in {SourceIntakeFileType.LAS, SourceIntakeFileType.DLIS}:
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


    def _attach_dlis_metadata(self, candidate: SourceFileCandidate, file_path: Path) -> None:
        try:
            inspection = inspect_dlis(file_path)
        except DlisInspectionError as exc:
            candidate.parser_status = SourceIntakeParseStatus.PARSE_FAILED
            candidate.parse_error = str(exc)
            candidate.review_required = True
            candidate.warnings.append(f"DLIS inspection failed: {exc}")
            return
        channels = list(inspection.scalar_channels)
        top_values = [item.top_depth for item in channels if item.top_depth is not None]
        base_values = [item.base_depth for item in channels if item.base_depth is not None]
        depth_unit = next((item.depth_unit for item in channels if item.depth_unit), None)
        candidate.parsed_metadata = SourceIntakeParsedMetadata(
            parser_id=inspection.parser_id,
            source_format=inspection.source_format,
            canonical_metadata=canonical_metadata_from_dlis_values(
                {
                    "well_name": inspection.well_name,
                    "uwi": inspection.uwi,
                    "operator": inspection.operator,
                    "field": inspection.field,
                    "producer": inspection.service_company,
                },
                parser_id=inspection.parser_id,
            ),
            well_header=SourceIntakeWellHeader(
                well_name=inspection.well_name, uwi=inspection.uwi,
                operator=inspection.operator, field=inspection.field,
                depth_unit=depth_unit,
            ),
            log_header=SourceIntakeLogHeader(
                file_name=candidate.file_name, file_type=candidate.detected_file_type,
                service_company=inspection.service_company,
                start_depth=min(top_values) if top_values else None,
                stop_depth=max(base_values) if base_values else None,
                depth_unit=depth_unit, curve_count=len(channels),
            ),
            curve_headers=[SourceIntakeCurveHeader(
                mnemonic=item.mnemonic, description=item.description, unit=item.unit,
                source_curve_name=item.source_curve_name, depth_unit=item.depth_unit,
                top_depth=item.top_depth, base_depth=item.base_depth,
                sample_count=item.sample_count,
                raw_depth_unit=item.raw_depth_unit,
                depth_scale_factor=item.depth_scale_factor,
                depth_normalization_status=item.depth_normalization_status,
                depth_normalization_reason=item.depth_normalization_reason,
                raw_top_depth=item.raw_top_depth,
                raw_base_depth=item.raw_base_depth,
                curve_statistics=item.curve_statistics,
            ) for item in channels],
            logical_file_count=inspection.logical_file_count,
            frame_count=inspection.frame_count,
            dlis_channels=[SourceIntakeDlisChannelHeader(
                logical_file_id=item.logical_file_id,
                frame_id=item.frame_id,
                mnemonic=item.mnemonic,
                description=item.description,
                unit=item.unit,
                dimensions=list(item.dimensions),
                index_channel=item.index_channel,
                sample_count=item.sample_count,
                role=item.role,
                supported=item.supported,
                unsupported_reason=item.unsupported_reason,
                raw_depth_unit=item.raw_depth_unit,
                depth_scale_factor=item.depth_scale_factor,
                normalized_depth_unit=item.normalized_depth_unit,
                depth_normalization_status=item.depth_normalization_status,
                depth_normalization_reason=item.depth_normalization_reason,
            ) for item in inspection.channel_inventory],
            evidence_count=inspection.logical_file_count + inspection.frame_count + len(inspection.channel_inventory),
            warning_count=len(inspection.warnings), error_count=0,
            warnings=list(inspection.warnings),
        )
        review_channels = [item for item in inspection.channel_inventory if item.depth_normalization_status == "review_required"]
        if review_channels:
            raw_unit = review_channels[0].raw_depth_unit
            raw_ranges = [
                (item.raw_top_depth, item.raw_base_depth)
                for item in inspection.scalar_channels
                if item.raw_top_depth is not None and item.raw_base_depth is not None
            ]
            raw_start = min(item[0] for item in raw_ranges) if raw_ranges else None
            raw_stop = max(item[1] for item in raw_ranges) if raw_ranges else None
            if raw_start is not None and raw_stop is not None and raw_unit:
                candidate.depth_normalization = SourceIntakeDepthNormalizationContract(
                    raw_unit=raw_unit,
                    raw_start_depth=raw_start,
                    raw_stop_depth=raw_stop,
                    status=SourceIntakeDepthNormalizationStatus.REVIEW_REQUIRED,
                    reason="Non-standard encoded depth unit requires an explicit human target unit.",
                    options=[
                        SourceIntakeDepthNormalizationOption(
                            target_unit=target,
                            start_depth=convert_depth_to_target(raw_start, raw_unit, target),
                            stop_depth=convert_depth_to_target(raw_stop, raw_unit, target),
                        )
                        for target in ("m", "ft")
                    ],
                )
        candidate.resolved_metadata = resolve_candidate_metadata(candidate)
        candidate.parser_status = SourceIntakeParseStatus.PARSED_WITH_WARNINGS if inspection.warnings else SourceIntakeParseStatus.PARSED
        candidate.parse_error = None
        for warning in inspection.warnings:
            if warning not in candidate.warnings: candidate.warnings.append(warning)
        candidate.review_required = candidate.review_required or bool(inspection.warnings) or inspection.well_name is None


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

        parser_id = getattr(LasSourceAdapter, "adapter_id", "las_numeric_curve_adapter_v1")
        parsed = SourceIntakeParsedMetadata(
            parser_id=parser_id,
            source_format="LAS",
            canonical_metadata=canonical_metadata_from_las_header(
                well_header_raw,
                parser_id=parser_id,
            ),
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
