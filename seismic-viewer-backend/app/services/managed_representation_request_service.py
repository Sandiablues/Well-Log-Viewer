from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException

from app.services.package_registry_service import get_segy_file
from app.services.repository_registry_service import get_repository


_ALLOWED_TARGETS = {"2d_line", "3d_volume"}
_2D_KINDS = {"2d_line", "2d"}
_2D_ROLES = {"line_candidate", "line"}
_3D_KINDS = {"3d_volume", "3d"}
_3D_ROLES = {"volume_candidate", "volume"}
_2D_SOURCE_STRUCTURES = {"single_isolated_line", "single_line_with_docs", "single_line_multi_version", "survey_with_line_folders", "survey_flat_lines"}
_3D_SOURCE_STRUCTURES = {"single_3d_volume", "single_3d_volume_with_docs", "multi_version_3d_delivery"}


def _repository_target(candidate: Dict[str, Any]) -> tuple[str | None, str | None]:
    repository_id = candidate.get("repository_id")
    if not repository_id:
        return None, None
    repo = get_repository(str(repository_id))
    if not repo:
        return None, None

    intended_use = str(repo.get("intended_use") or "").strip().lower()
    source_structure_type = str(repo.get("source_structure_type") or "").strip().lower()
    notes = str(repo.get("notes") or "").lower()

    if intended_use in {"2d_segy_intake", "2d"} or source_structure_type in _2D_SOURCE_STRUCTURES or "intended_use=2d_segy_intake" in notes:
        return "2d_line", "line_candidate"
    if intended_use in {"3d_segy_intake", "3d"} or source_structure_type in _3D_SOURCE_STRUCTURES or "intended_use=3d_segy_intake" in notes:
        return "3d_volume", "volume_candidate"
    return None, None


class ManagedRepresentationRequestService:
    """
    Service boundary for requests that turn Source Intake candidates into
    managed representations.

    This service owns request validation and target-type ownership before the
    existing conversion path is invoked. Conversion internals are intentionally
    not changed in this block.
    """

    def get_source_candidate(self, candidate_id: str) -> Dict[str, Any]:
        candidate = get_segy_file(candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail=f"Source candidate not found: {candidate_id}")
        return candidate

    def source_path_exists(self, candidate: Dict[str, Any]) -> Optional[bool]:
        value = candidate.get("source_path_exists")
        if isinstance(value, bool):
            return value

        for key in ("source_path", "absolute_path", "path", "file_path"):
            raw = candidate.get(key)
            if raw:
                try:
                    return Path(str(raw)).expanduser().exists()
                except Exception:
                    return None

        repository_id = candidate.get("repository_id")
        relative_path = candidate.get("relative_path")
        if repository_id and relative_path:
            repo = get_repository(str(repository_id))
            root_path = repo.get("root_path") if repo else None
            if root_path:
                try:
                    return (Path(str(root_path)).expanduser() / str(relative_path)).exists()
                except Exception:
                    return None

        return None

    def _candidate_kind(self, candidate: Dict[str, Any]) -> str:
        repo_kind, _ = _repository_target(candidate)
        return str(repo_kind or candidate.get("candidate_kind") or candidate.get("dataset_type") or "").strip().lower()

    def _candidate_role(self, candidate: Dict[str, Any]) -> str:
        _, repo_role = _repository_target(candidate)
        return str(repo_role or candidate.get("candidate_role") or "").strip().lower()

    def _candidate_label(self, candidate: Dict[str, Any]) -> str:
        return str(
            candidate.get("display_name")
            or candidate.get("filename")
            or candidate.get("segy_file_id")
            or candidate.get("source_segy_file_id")
            or "source candidate"
        )

    def _is_target_compatible(self, candidate: Dict[str, Any], target_type: str) -> bool:
        kind = self._candidate_kind(candidate)
        role = self._candidate_role(candidate)

        if target_type == "2d_line":
            return kind in _2D_KINDS or role in _2D_ROLES

        if target_type == "3d_volume":
            return kind in _3D_KINDS or role in _3D_ROLES

        return False

    def validate_request(self, candidate_id: str, target_type: str) -> Dict[str, Any]:
        clean_target = str(target_type or "").strip().lower()
        if clean_target not in _ALLOWED_TARGETS:
            raise HTTPException(status_code=400, detail=f"Unsupported managed representation target: {target_type!r}")

        candidate = self.get_source_candidate(candidate_id)

        source_exists = self.source_path_exists(candidate)
        if source_exists is False:
            raise HTTPException(
                status_code=400,
                detail=f"Source file is missing for candidate: {self._candidate_label(candidate)}",
            )
        if source_exists is None:
            raise HTTPException(
                status_code=400,
                detail=f"Could not verify source file path for candidate: {self._candidate_label(candidate)}",
            )

        if not self._is_target_compatible(candidate, clean_target):
            kind = self._candidate_kind(candidate) or "unknown"
            role = self._candidate_role(candidate) or "unknown"
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Candidate is not eligible for {clean_target} build: "
                    f"candidate_kind={kind}, candidate_role={role}"
                ),
            )

        # Important: prior failed/stale/deleted managed representations must not
        # block a clean rebuild request. MSI/reconcile state is handled after
        # conversion and registration; request validation is based on the source
        # candidate and explicit target compatibility only.
        return {
            "candidate": candidate,
            "candidate_id": candidate_id,
            "target_type": clean_target,
            "candidate_kind": self._candidate_kind(candidate),
            "candidate_role": self._candidate_role(candidate),
            "source_path_exists": source_exists,
            "prior_conversion_status": candidate.get("conversion_status"),
            "prior_volume_id": candidate.get("volume_id"),
        }

    def build_managed_representation(self, candidate_id: str, target_type: str) -> Dict[str, Any]:
        validation = self.validate_request(candidate_id, target_type)

        # Existing conversion route still owns job creation/execution in this
        # boundary block. The service owns request validation and target type
        # selection, then delegates explicitly.
        from app.api.documents import api_convert_registry_segy_file

        result = api_convert_registry_segy_file(
            candidate_id,
            expected_dataset_type=validation["target_type"],
        )

        return {
            "status": "ok",
            "service": "ManagedRepresentationRequestService",
            "candidate_id": candidate_id,
            "target_type": validation["target_type"],
            "candidate_kind": validation["candidate_kind"],
            "candidate_role": validation["candidate_role"],
            "source_path_exists": validation["source_path_exists"],
            "prior_conversion_status": validation.get("prior_conversion_status"),
            "prior_volume_id": validation.get("prior_volume_id"),
            "action_result": result,
        }

    def build_2d_line(self, candidate_id: str) -> Dict[str, Any]:
        return self.build_managed_representation(candidate_id, "2d_line")

    def build_3d_volume(self, candidate_id: str) -> Dict[str, Any]:
        return self.build_managed_representation(candidate_id, "3d_volume")
