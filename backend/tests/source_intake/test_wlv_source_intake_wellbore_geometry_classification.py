from pathlib import Path

from app.source_intake.models import SourceRepositoryCreateRequest
from app.source_intake.service import WlvSourceIntakeService


def _write(path: Path, text: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_source_intake_classifies_deviation_surveys_as_wellbore_geometry(tmp_path: Path) -> None:
    root = tmp_path / "Forge_21_31"
    _write(root / "FORGE_21_31_Final_Deviation_Survey.csv", "MD,INC,AZI\n0,0,0\n")
    _write(root / "FORGE_21_31_directional_survey.xlsx", "placeholder")
    _write(root / "FORGE_21_31_MD_INC_AZI.asc", "0 0 0\n")
    _write(root / "production_table.csv", "A,B\n1,2\n")
    _write(root / "field_survey_report.pdf", "%PDF")
    _write(root / "FORGE_21_31.las", "~Version\n")

    service = WlvSourceIntakeService(storage_path=tmp_path / "source_intake.json")
    repository = service.create_repository(SourceRepositoryCreateRequest(root_path=str(root), include_subfolders=True))
    result = service.scan_repository(repository.repository_id)

    roles = {candidate.file_name: candidate.candidate_role for candidate in result.candidates}

    assert roles["FORGE_21_31_Final_Deviation_Survey.csv"] == "wellbore_geometry_candidate"
    assert roles["FORGE_21_31_directional_survey.xlsx"] == "wellbore_geometry_candidate"
    assert roles["FORGE_21_31_MD_INC_AZI.asc"] == "wellbore_geometry_candidate"

    assert roles["production_table.csv"] == "tabular_candidate"
    assert roles["field_survey_report.pdf"] == "supporting_document_candidate"
    assert roles["FORGE_21_31.las"] == "well_log_candidate"

    geometry = [candidate for candidate in result.candidates if candidate.candidate_role == "wellbore_geometry_candidate"]
    assert len(geometry) == 3
    assert all(candidate.review_required for candidate in geometry)
    assert all(candidate.parser_status == "unsupported" for candidate in geometry)

    assert result.repository.wellbore_geometry_candidate_count == 3
    assert result.repository.tabular_candidate_count == 1
    assert result.repository.document_candidate_count == 1

    workbench = service.get_workbench()
    assert workbench.summary.wellbore_geometry_candidate_count == 3
    assert workbench.summary.well_log_candidate_count == 1
