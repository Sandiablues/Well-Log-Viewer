from pathlib import Path

import pytest

from app.source_intake.models import (
    SourceIntakeDiagnosticPhase,
    SourceIntakeDiagnosticSeverity,
    SourceRepositoryCreateRequest,
)
from app.source_intake.service import SourceIntakeError, WlvSourceIntakeService


def _write(path: Path, text: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_candidate_diagnostics_returns_backend_owned_phase_flags(tmp_path: Path) -> None:
    # WLV-WSI-FLAGS-DETAIL-1
    root = tmp_path / "well_folder"
    archive = root / "logs_archive.zip"
    _write(archive, "zip-content")

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root)))
    scan = service.scan_repository(repository.repository_id)

    candidate = scan.candidates[0]
    diagnostics = service.get_candidate_diagnostics(candidate.source_file_id)

    assert diagnostics.ok is True
    assert diagnostics.candidate_id == candidate.source_file_id
    assert diagnostics.summary.file_name == "logs_archive.zip"
    assert diagnostics.summary.relative_path == "logs_archive.zip"

    parse_flags = [flag for flag in diagnostics.flags if flag.phase == SourceIntakeDiagnosticPhase.PARSE]
    mdp_flags = [flag for flag in diagnostics.flags if flag.phase == SourceIntakeDiagnosticPhase.MDP_READY]

    assert any(flag.code == "container_pending_extraction" for flag in parse_flags)
    assert any(flag.severity == SourceIntakeDiagnosticSeverity.BLOCKER for flag in parse_flags)
    assert any(flag.code == "mdp_registration_blocked" for flag in mdp_flags)
    assert diagnostics.mdp_ready_status in {"blocked", "needs_review"}

    actions = {action.action_key: action for action in diagnostics.actions}
    assert "extract_container" in actions
    assert actions["extract_container"].enabled is False
    assert actions["extract_container"].reason


def test_candidate_diagnostics_rejects_unknown_candidate(tmp_path: Path) -> None:
    # WLV-WSI-FLAGS-DETAIL-1
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")

    with pytest.raises(SourceIntakeError):
        service.get_candidate_diagnostics("missing-candidate")
