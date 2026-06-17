from pathlib import Path

from app.source_intake.models import SourceRepositoryCreateRequest
from app.source_intake.service import WlvSourceIntakeService


def test_geometry_candidate_message_matches_available_registration(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    source = root / "FORGE_deviation_survey.csv"
    source.write_text(
        "MD,INC,AZI,TVD,X_OFFSET,Y_OFFSET\n"
        "0,0,0,0,0,0\n"
        "100,1,20,99.9,1,2\n"
        "200,2,25,199.7,4,6\n"
    )

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(
        SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True)
    )
    candidate = service.scan_repository(repository.repository_id).candidates[0]

    combined = "\n".join(
        candidate.warnings
        + candidate.qaqc_status.messages
        + [check.message for check in candidate.qaqc_status.checks]
    ).lower()

    assert "registration remains reserved" not in combined
    assert "registration is still disabled" not in combined
    assert "review the parsed trajectory" in combined
    assert candidate.geometry_preview is not None
    assert candidate.geometry_preview.station_count == 3
