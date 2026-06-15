from pathlib import Path

from app.source_intake.models import SourceIntakeParseStatus, SourceRepositoryCreateRequest
from app.source_intake.service import WlvSourceIntakeService


def _write(path: Path, text: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_source_intake_expanded_parse_status_contract(tmp_path: Path) -> None:
    # WLV-WSI-PARSE-STATUS-FILENAME-1
    root = tmp_path / "well_folder"
    _write(root / "archive.zip", "zip-content")
    _write(root / "legacy.dlis", "dlis-content")
    _write(root / "legacy.lis", "lis-content")
    _write(root / "report.pdf", "%PDF")
    _write(root / "unknown.bin", "unknown")

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    result = service.scan_repository(repository.repository_id)

    statuses = {candidate.file_name: candidate.parser_status for candidate in result.candidates}

    assert statuses["archive.zip"] == SourceIntakeParseStatus.CONTAINER_PENDING_EXTRACTION
    assert statuses["legacy.dlis"] == SourceIntakeParseStatus.UNSUPPORTED
    assert statuses["legacy.lis"] == SourceIntakeParseStatus.UNSUPPORTED
    assert statuses["report.pdf"] == SourceIntakeParseStatus.UNSUPPORTED
    assert statuses["unknown.bin"] == SourceIntakeParseStatus.NOT_PARSED

    archive = next(candidate for candidate in result.candidates if candidate.file_name == "archive.zip")
    assert archive.review_required is True
    assert any("pending extraction" in warning.lower() for warning in archive.warnings)
