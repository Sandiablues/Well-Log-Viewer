from pathlib import Path

from app.source_intake.service import WlvSourceIntakeService


def test_direct_file_ingest_uses_normal_source_intake_scan(tmp_path: Path) -> None:
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")

    result = service.ingest_uploaded_files([
        ("quick.las", b"~Version Information\nVERS. 2.0\n~Well Information\nWELL. QUICK\n~Curve Information\nDEPT.M\nGR.API\n~ASCII\n1000 50\n"),
    ])

    assert result.ok is True
    assert result.file_count == 1
    assert result.repository.name == "Direct file ingest"
    assert result.repository.include_subfolders is True
    assert len(result.candidates) == 1
    assert result.candidates[0].file_name == "quick.las"
    assert result.candidates[0].repository_id == result.repository.repository_id


def test_direct_file_ingest_rejects_empty_upload(tmp_path: Path) -> None:
    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")

    try:
        service.ingest_uploaded_files([("empty.las", b"")])
    except ValueError as exc:
        assert "empty" in str(exc).lower()
    else:
        raise AssertionError("Expected empty upload to be rejected")
