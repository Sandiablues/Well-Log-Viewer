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

from .metadata_resolver import resolve_candidate_metadata
from .qaqc import run_source_intake_qaqc

from .models import (
    SourceFileCandidate,
    SourceIntakeCandidateRole,
    SourceIntakeClearResponse,
    SourceIntakeFileType,
    SourceIntakeLogHeader,
    SourceIntakeParseStatus,
    SourceIntakeParsedMetadata,
    SourceIntakeRepositoryStatus,
    SourceIntakeWellHeader,
    SourceIntakeCurveHeader,
    SourceIntakeSnapshot,
    SourceIntakeWorkbench,
    SourceIntakeWorkbenchSummary,
    SourceRepositoryCreateRequest,
    SourceRepositoryRecord,
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

    def clear_workbench_selection(self, repository_id: str | None = None) -> SourceIntakeClearResponse:
        # WLV-SOURCE-INTAKE-1 has no persisted active selection yet. This method
        # intentionally mirrors SSI Clear semantics: it is non-destructive and
        # does not delete repositories, candidates, source files, or managed data.
        return SourceIntakeClearResponse(workbench=self.get_workbench())

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
        return sorted((path for path in iterator if path.is_file()), key=lambda path: str(path).lower())

    def _candidate_for_file(self, repository_id: str, scan_id: str, root: Path, file_path: Path) -> SourceFileCandidate:
        checksum = self._sha256(file_path)
        detected_file_type, candidate_role = self._classify_file(file_path)
        review_required = candidate_role == SourceIntakeCandidateRole.OTHER_REVIEW_REQUIRED
        warnings = ["File type requires review before WMDP staging."] if review_required else []
        relative_path = str(file_path.relative_to(root))
        stat = file_path.stat()
        modified_at = utc_now_iso()
        try:
            from datetime import datetime, timezone
            modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        except Exception:
            pass

        candidate = SourceFileCandidate(
            source_file_id=f"src:{repository_id}:{checksum[:16]}",
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

        if detected_file_type == SourceIntakeFileType.LAS:
            self._attach_las_metadata(candidate, file_path)

        candidate.qaqc_status = run_source_intake_qaqc(candidate)
        candidate.review_required = candidate.review_required or candidate.qaqc_status.review_required

        return candidate

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
        if ext == "txt":
            return SourceIntakeFileType.TEXT, SourceIntakeCandidateRole.SUPPORTING_DOCUMENT_CANDIDATE
        return SourceIntakeFileType.UNKNOWN, SourceIntakeCandidateRole.OTHER_REVIEW_REQUIRED

    def _apply_counts(self, repository: SourceRepositoryRecord, candidates: list[SourceFileCandidate]) -> None:
        repository.file_count = len(candidates)
        repository.well_log_candidate_count = sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.WELL_LOG_CANDIDATE)
        repository.raster_candidate_count = sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.RASTER_IMAGE_CANDIDATE)
        repository.document_candidate_count = sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.SUPPORTING_DOCUMENT_CANDIDATE)
        repository.tabular_candidate_count = sum(1 for item in candidates if item.candidate_role == SourceIntakeCandidateRole.TABULAR_CANDIDATE)
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
