"""Backend-owned lifecycle coordinator for transient WSI working data.

This service centralizes lifecycle projection and reference mutations. It does
not clear cache or source data. Source files remain external and read-only.
"""
from __future__ import annotations
from typing import Iterable
from pathlib import Path
import hashlib
import re
import shutil
from .models import (
    SourceFileCandidate,
    SourceIntakeReferenceBinding,
    SourceIntakeReferenceType,
    SourceIntakeRetentionState,
    SourceIntakeSnapshot,
    SourceIntakeSourceAccessStatus,
    utc_now_iso,
)

class SourceIntakeLifecycleService:
    """Single authority for WSI transient lifecycle transitions."""
    def synchronize_candidate(self, candidate: SourceFileCandidate) -> SourceFileCandidate:
        return candidate.synchronize_transient_lifecycle()
    def synchronize_snapshot(self, snapshot: SourceIntakeSnapshot) -> SourceIntakeSnapshot:
        for candidate in snapshot.candidates:
            self.synchronize_candidate(candidate)
        return snapshot
    def acquire_reference(self, candidate: SourceFileCandidate, reference_type: SourceIntakeReferenceType, owner_id: str, reason: str | None = None) -> SourceIntakeReferenceBinding:
        normalized = str(owner_id or "").strip()
        if not normalized:
            raise ValueError("Reference owner_id is required.")
        return candidate.acquire_reference(reference_type, normalized, reason)
    def release_reference(self, candidate: SourceFileCandidate, reference_type: SourceIntakeReferenceType, owner_id: str) -> bool:
        normalized = str(owner_id or "").strip()
        if not normalized:
            raise ValueError("Reference owner_id is required.")
        return candidate.release_reference(reference_type, normalized)
    def synchronize_inventory_record(self, candidates: Iterable[SourceFileCandidate], record: object) -> int:
        managed_well_id = str(getattr(record, "managed_well_id", "") or "").strip()
        if not managed_well_id:
            return 0
        candidate_ids: set[str] = set()
        for source_reference in getattr(record, "source_references", []) or []:
            source_id = str(getattr(source_reference, "source_id", "") or "").strip()
            if source_id:
                candidate_ids.add(source_id)
        for group in getattr(record, "product_groups", []) or []:
            for item in getattr(group, "items", []) or []:
                provenance = getattr(item, "provenance", None) or {}
                for value in (getattr(item, "source_id", None), getattr(item, "source_intake_candidate_id", None), provenance.get("source_file_id"), provenance.get("source_intake_candidate_id")):
                    normalized = str(value or "").strip()
                    if normalized:
                        candidate_ids.add(normalized)
        wmdp_state = getattr(record, "wmdp_state", None)
        wdv_state = getattr(record, "wdv_state", None)
        normalized_wmdp_state = getattr(wmdp_state, "value", wmdp_state)
        normalized_wdv_state = getattr(wdv_state, "value", wdv_state)
        matched = 0
        for candidate in candidates:
            if candidate.managed_well_id != managed_well_id and candidate.source_file_id not in candidate_ids:
                continue
            candidate.managed_well_id = managed_well_id
            candidate.managed_well_name = str(getattr(record, "well_name", "") or candidate.managed_well_name or "") or None
            candidate.wmdp_state = str(normalized_wmdp_state or "") or None
            candidate.wdv_state = str(normalized_wdv_state or "") or None
            self.synchronize_candidate(candidate)
            matched += 1
        return matched



    def inspect_external_source(self, candidate: SourceFileCandidate) -> tuple[SourceIntakeSourceAccessStatus, str | None, str]:
        """Inspect one external source without changing it."""
        reference = candidate.source_reference
        if reference is None:
            candidate.source_access_status = SourceIntakeSourceAccessStatus.INACCESSIBLE
            candidate.source_access_checked_at = utc_now_iso()
            candidate.source_access_message = "Candidate has no external source reference."
            return candidate.source_access_status, None, candidate.source_access_message
        path = Path(reference.source_uri).expanduser()
        try:
            resolved = path.resolve()
            if not resolved.exists():
                candidate.source_access_status = SourceIntakeSourceAccessStatus.MISSING
                candidate.source_access_checked_at = utc_now_iso()
                candidate.source_access_message = f"External source is missing: {resolved}"
                reference.accessible = False
                return candidate.source_access_status, None, candidate.source_access_message
            if not resolved.is_file():
                raise OSError(f"External source is not a regular file: {resolved}")
            current = self.external_source_fingerprint(resolved)
        except PermissionError as exc:
            candidate.source_access_status = SourceIntakeSourceAccessStatus.INACCESSIBLE
            candidate.source_access_checked_at = utc_now_iso()
            candidate.source_access_message = str(exc)
            reference.accessible = False
            return candidate.source_access_status, None, candidate.source_access_message
        except OSError as exc:
            candidate.source_access_status = SourceIntakeSourceAccessStatus.INACCESSIBLE
            candidate.source_access_checked_at = utc_now_iso()
            candidate.source_access_message = str(exc)
            reference.accessible = False
            return candidate.source_access_status, None, candidate.source_access_message
        expected = str(candidate.content_fingerprint or candidate.checksum or reference.fingerprint or "").lower()
        candidate.source_access_status = (
            SourceIntakeSourceAccessStatus.CHANGED if expected and current.lower() != expected else SourceIntakeSourceAccessStatus.AVAILABLE
        )
        candidate.source_access_checked_at = utc_now_iso()
        candidate.source_access_message = (
            "External source fingerprint changed." if candidate.source_access_status == SourceIntakeSourceAccessStatus.CHANGED
            else "External source is available and unchanged."
        )
        reference.accessible = True
        return candidate.source_access_status, current, candidate.source_access_message

    def prepare_for_wsi_close(self, candidate: SourceFileCandidate) -> SourceFileCandidate:
        """Release WSI ownership and calculate whether derived data is safe to clear."""
        candidate.reference_bindings = [
            binding
            for binding in candidate.reference_bindings
            if binding.reference_type != SourceIntakeReferenceType.WSI
        ]
        return candidate.synchronize_reference_summary()

    @staticmethod
    def external_source_fingerprint(source_path: Path) -> str:
        """Return the SHA-256 fingerprint of an external source without modifying it."""
        path = Path(source_path).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"External source is unavailable: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def clear_candidate_derived_data(
        self,
        candidate: SourceFileCandidate,
        *,
        las_storage_root: Path,
    ) -> bool:
        """Clear only persisted derived data owned by WLV for one candidate.

        LAS currently has a persisted manifest/sample cache. DLIS is reparsed
        directly from the external source and has no persistent DLIS-derived
        store in the current architecture, so DLIS cleanup is intentionally a
        no-op. In both cases the external source is untouched.
        """
        if candidate.active_reference_count != 0:
            raise ValueError("Cannot clear derived data while active references remain.")
        source_type = str(getattr(candidate.detected_file_type, "value", candidate.detected_file_type)).lower()
        fingerprint = str(candidate.content_fingerprint or candidate.checksum or "").strip().lower()
        if source_type == "las":
            return self.clear_las_derived_cache(fingerprint, las_storage_root)
        if source_type == "dlis":
            return False
        return False

    def clear_las_derived_cache(self, source_fingerprint: str, storage_root: Path) -> bool:
        """Clear one content-addressed LAS cache entry under the WLV cache root only."""
        fingerprint = str(source_fingerprint or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ValueError("A valid SHA-256 fingerprint is required for LAS cache cleanup.")
        root = Path(storage_root).expanduser().resolve()
        target = (root / fingerprint[:2] / fingerprint).resolve()
        if target == root or root not in target.parents:
            raise ValueError("Refusing to clear a path outside WLV LAS derived-cache storage.")
        if not target.exists():
            return False
        if not target.is_dir():
            raise ValueError("LAS derived-cache target is not a directory.")
        shutil.rmtree(target)
        return True

    def mark_cleared(self, candidate: SourceFileCandidate) -> SourceFileCandidate:
        """Record completion of cleanup for application-owned derived data."""
        if candidate.active_reference_count != 0:
            raise ValueError("Cannot mark source data cleared while active references remain.")
        candidate.retention_state = SourceIntakeRetentionState.CLEARED
        candidate.cleanup_eligible = False
        candidate.retention_reason = "WLV-owned temporary and derived data cleared."
        return candidate

    def clear_temporary_materialization(self, materialized_path: Path, temporary_root: Path) -> bool:
        """Delete only a WLV-owned browser-upload materialization.

        The target must be a strict descendant of the configured temporary root.
        External source paths can never satisfy this guard and are never touched.
        """
        target = Path(materialized_path).expanduser().resolve()
        root = Path(temporary_root).expanduser().resolve()
        if target == root or root not in target.parents:
            raise ValueError("Refusing to clear a path outside WLV temporary upload storage.")
        if not target.exists():
            return False
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return True
